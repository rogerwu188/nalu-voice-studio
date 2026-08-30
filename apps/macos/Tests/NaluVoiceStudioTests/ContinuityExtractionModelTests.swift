import Foundation
import Testing
@testable import NaluVoiceStudio

struct ContinuityExtractionModelTests {
    @Test func decodesVersionBoundExtractionProposal() throws {
        let data = Data(
            #"""
            {
              "schema_version":"nalu.continuity-extraction/v1",
              "episode_id":"ep_1",
              "script_revision":3,
              "proposal_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              "source":"approved_script_metadata",
              "state":{
                "characters":{"林叔":{"location":"旧火车站","wardrobe":["蓝色外套"]}},
                "props":{},
                "scene_location":"旧火车站",
                "story_time":"1986年冬夜",
                "weather":"大雪"
              },
              "unresolved_hooks":["父亲的信没有打开"],
              "extracted_paths":["characters.林叔","scene_location","story_time","weather","unresolved_hooks"],
              "spoken_summary":"请核对本集结尾。"
            }
            """#.utf8
        )

        let proposal = try JSONDecoder().decode(ContinuityExtractionProposal.self, from: data)

        #expect(proposal.scriptRevision == 3)
        #expect(proposal.state.characters["林叔"]?.location == "旧火车站")
        #expect(proposal.unresolvedHooks == ["父亲的信没有打开"])
        #expect(proposal.extractedPaths.count == 5)
    }

    @Test @MainActor func confirmationRequiresReviewAndExplainedEdits() {
        let proposal = ContinuityExtractionProposal(
            schemaVersion: "nalu.continuity-extraction/v1",
            episodeID: "ep_1",
            scriptRevision: 2,
            proposalSHA256: String(repeating: "b", count: 64),
            source: "approved_script_metadata",
            state: ContinuityState(sceneLocation: "旧火车站", weather: "大雪"),
            unresolvedHooks: ["信还没有打开"],
            extractedPaths: ["scene_location", "weather", "unresolved_hooks"],
            spokenSummary: "请核对"
        )
        let model = VoiceInterviewViewModel()
        model.continuityExtractionProposal = proposal
        model.endingContinuityDraft = ContinuityFormDraft(
            state: proposal.state,
            unresolvedHooks: proposal.unresolvedHooks
        )

        #expect(!model.canConfirmContinuityExtraction)
        model.reviewedContinuityExtractionHash = proposal.proposalSHA256
        #expect(model.canConfirmContinuityExtraction)

        model.endingContinuityDraft.weather = "小雪"
        model.reviewedContinuityExtractionHash = nil
        #expect(model.continuityExtractionWasEdited)
        #expect(!model.canConfirmContinuityExtraction)
        model.continuityExtractionChangeSummary = "核对后改为小雪"
        model.reviewedContinuityExtractionHash = proposal.proposalSHA256
        #expect(model.canConfirmContinuityExtraction)
    }

    @Test @MainActor func readbackUnlocksOnlyAfterUninterruptedMatchingSpeech() {
        let proposal = ContinuityExtractionProposal(
            schemaVersion: "nalu.continuity-extraction/v1",
            episodeID: "ep_1",
            scriptRevision: 2,
            proposalSHA256: String(repeating: "c", count: 64),
            source: "approved_script_metadata",
            state: ContinuityState(sceneLocation: "旧火车站", weather: "大雪"),
            unresolvedHooks: ["信还没有打开"],
            extractedPaths: ["scene_location", "weather", "unresolved_hooks"],
            spokenSummary: "请核对"
        )
        let model = VoiceInterviewViewModel()
        model.continuityExtractionProposal = proposal
        model.endingContinuityDraft = ContinuityFormDraft(
            state: proposal.state,
            unresolvedHooks: proposal.unresolvedHooks
        )
        let spokenDraft = model.endingContinuityDraft

        model.isReadingEndingContinuity = true
        model.completeEndingContinuityReadback(
            proposalSHA256: proposal.proposalSHA256,
            reviewedDraft: spokenDraft,
            completed: false
        )
        #expect(!model.isReadingEndingContinuity)
        #expect(!model.canConfirmContinuityExtraction)

        model.isReadingEndingContinuity = true
        model.endingContinuityDraft.weather = "小雪"
        model.completeEndingContinuityReadback(
            proposalSHA256: proposal.proposalSHA256,
            reviewedDraft: spokenDraft,
            completed: true
        )
        #expect(model.reviewedContinuityExtractionHash == nil)

        let correctedDraft = model.endingContinuityDraft
        model.completeEndingContinuityReadback(
            proposalSHA256: proposal.proposalSHA256,
            reviewedDraft: correctedDraft,
            completed: true
        )
        #expect(model.reviewedContinuityExtractionHash == proposal.proposalSHA256)
    }
}
