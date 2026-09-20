import Foundation
import XCTest
@testable import NaluVoiceStudio

final class ScriptApprovalSnapshotTests: XCTestCase {
    @MainActor func testApprovalRejectsUnreviewedOrUnsavedSnapshotBeforeNetwork() async {
        for mismatch in ["content", "summary", "revision", "episode"] {
            let model = VoiceInterviewViewModel(runtime: RuntimeClient(
                baseURL: URL(string: "http://127.0.0.1:8765")!, accessCheck: {
                    XCTFail("Invalid approval must not reach runtime transport")
                    return false
                }))
            model.selectedEpisodeID = "episode-A"
            model.scriptRevisions = [ScriptRevision(
                episodeID: "episode-A", revision: 2, content: "已保存正文",
                summaryForVoiceReview: "已保存摘要", sourceTranscript: "",
                narrativeMetadata: [:], authoringProvenance: nil,
                approvedAt: nil, createdAt: "2026-09-20T00:00:00Z")]
            model.viewedScriptRevision = mismatch == "revision" ? 1 : 2
            model.scriptContent = mismatch == "content" ? "尚未保存的新结尾" : "已保存正文"
            model.scriptSummary = mismatch == "summary" ? "尚未保存的新摘要" : "已保存摘要"
            if mismatch == "episode" { model.selectedEpisodeID = "episode-B" }
            let content = model.scriptContent
            let summary = model.scriptSummary
            await model.approveScriptVisually()
            XCTAssertEqual(model.errorMessage,
                "请先保存修改，并查看最新保存的剧本和摘要，再确认批准。您的修改仍然保留。")
            XCTAssertEqual(model.scriptContent, content)
            XCTAssertEqual(model.scriptSummary, summary)
            XCTAssertNil(model.scriptRevisions.last?.approvedAt)
        }
    }
}
