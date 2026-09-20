import Foundation
import XCTest
@testable import NaluVoiceStudio

final class ScriptApprovalSnapshotTests: XCTestCase {
    @MainActor func testLateApprovalFailureDoesNotReplaceNewProjectState() async {
        let started = expectation(description: "approval started")
        let gate = AsyncStream<Void>.makeStream()
        let model = VoiceInterviewViewModel(runtime: RuntimeClient(
            baseURL: URL(string: "http://127.0.0.1:8765")!, accessCheck: {
                started.fulfill()
                for await _ in gate.stream {}
                return false
            }))
        model.selectedProjectID = "project-A"
        model.selectedEpisodeID = "episode-A"
        model.scriptRevisions = [ScriptRevision(
            episodeID: "episode-A", revision: 2, content: "已保存正文",
            summaryForVoiceReview: "已保存摘要", sourceTranscript: "",
            narrativeMetadata: [:], authoringProvenance: nil,
            approvedAt: nil, createdAt: "2026-09-20T00:00:00Z")]
        model.viewedScriptRevision = 2
        model.scriptContent = "已保存正文"
        model.scriptSummary = "已保存摘要"
        let task = Task { await model.approveScriptVisually() }
        await fulfillment(of: [started], timeout: 10)
        model.selectedProjectID = "project-B"
        model.selectedEpisodeID = "episode-B"
        model.scriptContent = "新项目未保存内容"
        model.errorMessage = "新项目自己的提示"
        let messages = model.messages.map(\.text)
        gate.continuation.finish()
        await task.value
        XCTAssertEqual(model.scriptContent, "新项目未保存内容")
        XCTAssertEqual(model.errorMessage, "新项目自己的提示")
        XCTAssertEqual(model.messages.map(\.text), messages)
    }

    @MainActor func testSavedLatestSnapshotCanReachRuntimeAuthorization() async {
        let reached = expectation(description: "matching snapshot reaches runtime authorization")
        let model = VoiceInterviewViewModel(runtime: RuntimeClient(
            baseURL: URL(string: "http://127.0.0.1:8765")!, accessCheck: {
                reached.fulfill()
                return false // Stop before any real network request; this tests the editor guard.
            }))
        model.selectedEpisodeID = "episode-A"
        model.scriptRevisions = [ScriptRevision(
            episodeID: "episode-A", revision: 2, content: "已保存正文",
            summaryForVoiceReview: "已保存摘要", sourceTranscript: "",
            narrativeMetadata: [:], authoringProvenance: nil,
            approvedAt: nil, createdAt: "2026-09-20T00:00:00Z")]
        model.viewedScriptRevision = 2
        model.scriptContent = "已保存正文"
        model.scriptSummary = "已保存摘要"
        await model.approveScriptVisually()
        await fulfillment(of: [reached], timeout: 10)
        XCTAssertEqual(model.scriptContent, "已保存正文")
        XCTAssertNil(model.scriptRevisions.last?.approvedAt)
    }

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
