import Foundation
import Testing
@testable import NaluVoiceStudio

@MainActor
struct FinalReviewViewingGateTests {
    @Test func unviewedRunCannotSubmit() async {
        let model = VoiceInterviewViewModel()
        await model.submitFinalHumanReview(runID: "unviewed", picturePassed: true,
            audioSyncPassed: true, captionsPassed: true, continuityPassed: true, safetyPassed: true)
        #expect(model.errorMessage == "请先观看并明确确认当前版本的原尺寸成片，再提交人工验收。")
    }

    @Test func viewingAnotherRunDoesNotAuthorizeSubmission() async {
        let model = VoiceInterviewViewModel()
        model.recordFinalMasterPlayback(runID: "version-a", master: "a", seal: "s")
        model.markFinalHumanReviewViewed(runID: "version-a")
        await model.submitFinalHumanReview(runID: "version-b", picturePassed: true,
            audioSyncPassed: true, captionsPassed: true, continuityPassed: true, safetyPassed: true)
        #expect(model.errorMessage == "请先观看并明确确认当前版本的原尺寸成片，再提交人工验收。")
        #expect(!model.viewedFinalHumanReviewRunIDs.contains("version-b"))
    }

    @Test func emptyRunCannotBeAcknowledged() {
        let model = VoiceInterviewViewModel()
        model.markFinalHumanReviewViewed(runID: "  ")
        #expect(model.viewedFinalHumanReviewRunIDs.isEmpty)
    }

    @Test func playbackDoesNotAutomaticallyApproveAndChangedMasterInvalidatesAcknowledgement() {
        let model = VoiceInterviewViewModel()
        model.markFinalHumanReviewViewed(runID: "run")
        #expect(model.viewedFinalHumanReviewRunIDs.isEmpty)
        model.recordFinalMasterPlayback(runID: "run", master: "a", seal: "s")
        #expect(model.viewedFinalHumanReviewRunIDs.isEmpty)
        model.markFinalHumanReviewViewed(runID: "run")
        #expect(model.viewedFinalHumanReviewRunIDs.contains("run"))
        model.recordFinalMasterPlayback(runID: "run", master: "b", seal: "t")
        #expect(model.viewedFinalHumanReviewRunIDs.isEmpty)
    }
}
