import Foundation
import Testing
@testable import NaluVoiceStudio

struct HookClosureModelTests {
    @Test func encodesVersionedHookReviewInPreflight() throws {
        let review = ContinuityHookReviewDraft(
            inheritedSnapshotID: "con_1",
            resolutions: [
                ContinuityHookResolutionDraft(
                    hook: "父亲的信还没有打开",
                    disposition: "resolved",
                    explanation: "本集打开了信"
                )
            ],
            reviewedBy: "local-user",
            spokenConfirmation: "我确认这份悬念安排",
            guardianApproval: false
        )
        let draft = ContinuityPreflightDraft(
            openingState: ContinuityState(sceneLocation: "旧火车站"),
            transitionExplanations: [:],
            override: nil,
            hookReview: review
        )

        let object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(draft))
            as? [String: Any]
        let encodedReview = object?["hook_review"] as? [String: Any]
        #expect(encodedReview?["schema_version"] as? String == "nalu.continuity-hook-review/v1")
        #expect(encodedReview?["inherited_snapshot_id"] as? String == "con_1")
        let resolutions = encodedReview?["resolutions"] as? [[String: Any]]
        #expect(resolutions?.first?["disposition"] as? String == "resolved")
    }

    @Test @MainActor func editingHookResolutionInvalidatesPriorConfirmation() {
        let model = VoiceInterviewViewModel()
        model.continuityHookResolutions = [
            ContinuityHookResolutionDraft(
                hook: "父亲的信还没有打开",
                disposition: "carry_forward",
                explanation: ""
            )
        ]
        model.continuityHookConfirmation = "我确认这份悬念安排"

        model.updateHookResolution(
            hook: "父亲的信还没有打开",
            disposition: "resolved"
        )

        #expect(model.continuityHookResolutions[0].disposition == "resolved")
        #expect(model.continuityHookConfirmation.isEmpty)
    }

    @Test @MainActor func voiceReviewAsksDispositionReasonAndExplicitConfirmation() async {
        let model = VoiceInterviewViewModel()
        model.continuityHookResolutions = [
            ContinuityHookResolutionDraft(
                hook: "父亲的信还没有打开",
                disposition: "",
                explanation: ""
            )
        ]
        await model.beginHookVoiceReview(startLocalCapture: false)

        model.transcript = "这个悬念在本集解决"
        model.transcriptConfidence = 1
        model.commitTranscript()
        #expect(model.continuityHookResolutions[0].disposition == "resolved")

        model.transcript = "林叔在火车上打开了信"
        model.transcriptConfidence = 1
        model.commitTranscript()
        #expect(model.continuityHookResolutions[0].explanation == "林叔在火车上打开了信")

        model.transcript = "我确认这份悬念安排"
        model.transcriptConfidence = 1
        model.commitTranscript()
        #expect(model.continuityHookConfirmation == "我确认这份悬念安排")
    }
}
