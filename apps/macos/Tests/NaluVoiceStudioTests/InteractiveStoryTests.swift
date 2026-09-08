import XCTest
@testable import NaluVoiceStudio

final class InteractiveStoryTests: XCTestCase {
    func testEpisodeRetainsRuntimeSeasonIdentifier() throws {
        let data = Data(#"{"id":"episode","season_id":"season-two","title":"第二季开篇","episode_number":1,"logline":"","outline":{},"target_seconds":60,"status":"draft"}"#.utf8)
        XCTAssertEqual(try JSONDecoder().decode(NaluEpisode.self, from: data).seasonID, "season-two")
    }

    func testRestoreIncludesScriptsAndDoesNotPretendPendingCallSucceeded() {
        let state = InteractiveStoryState(revision: 3, turns: [
            .init(turn_id: "one", text: "外婆的故事", source_mode: "narrated_story", status: "answered",
                  answer: .init(reply: "请核对", summary: "", episode_drafts: [
                    .init(episode_number: 1, title: "海边", outline: "童年", script: "外婆牵着我的手。")
                  ], outcome: "answered")),
            .init(turn_id: "two", text: "改成下雨天", source_mode: "narrated_story", status: "pending", answer: nil),
        ], summary: "", episode_drafts: [])
        let restored = state.conversationMessages()
        XCTAssertEqual(restored.count, 4)
        XCTAssertEqual(restored.first?.text, "外婆的故事")
        XCTAssertTrue(restored[1].text.contains("外婆牵着我的手。"))
        XCTAssertTrue(restored.last?.text.contains("没有自动重复调用") == true)
    }

    @MainActor
    func testAdoptionRequiresExplicitEpisodeSelectionNotVagueAgreement() {
        XCTAssertEqual(VoiceInterviewViewModel.interactiveDraftSelection("采用第一集草稿"), 1)
        XCTAssertEqual(VoiceInterviewViewModel.interactiveDraftSelection("采用第12集草稿"), 12)
        XCTAssertNil(VoiceInterviewViewModel.interactiveDraftSelection("不要采用第1集草稿"))
        XCTAssertNil(VoiceInterviewViewModel.interactiveDraftSelection("好的"))
        for (text, number) in [("请采用第一集草稿。", 1), ("采用第 12 集草稿！", 12),
                               ("请把第十一集草稿放进审阅。", 11),
                               ("帮我把第二十三集草稿放入分集审阅", 23),
                               ("采用第十集草稿", 10)] {
            XCTAssertEqual(VoiceInterviewViewModel.interactiveDraftSelection(text), number, text)
        }
        for text in ["先别采用第一集草稿", "采用第一集草稿吗？", "采用第零集草稿",
                     "采用第0集草稿", "采用第1集草稿然后发布", "把第一集草稿放进审阅之前再改一下",
                     "我说过采用第1集草稿", "采用第一二集草稿"] {
            XCTAssertNil(VoiceInterviewViewModel.interactiveDraftSelection(text), text)
        }
    }

    func testRuntimeStateDecodesPendingAndAnsweredTurns() throws {
        let data = Data(#"{"revision":3,"summary":"童年","episode_drafts":[{"episode_number":1,"title":"海边","outline":"遇见外婆","script":"外景 海边"}],"turns":[{"turn_id":"a","text":"我小时候住海边","source_mode":"narrated_story","status":"answered","answer":{"reply":"后来呢？","summary":"童年","episode_drafts":[],"outcome":"answered"}},{"turn_id":"b","text":"网上找资料","source_mode":"web_source","status":"pending"}]}"#.utf8)
        let state = try JSONDecoder().decode(InteractiveStoryState.self, from: data)
        XCTAssertEqual(state.revision, 3)
        XCTAssertEqual(state.turns.first?.answer?.reply, "后来呢？")
        XCTAssertNil(state.turns.last?.answer)
        XCTAssertEqual(state.episode_drafts.first?.script, "外景 海边")
    }

    @MainActor
    func testUnsentInputRemainsWithItsProject() {
        let model = VoiceInterviewViewModel()
        model.selectedProjectID = "project-a"
        model.transcript = "导入小说 https://example.org/a"
        model.transcriptConfidence = 0.7
        model.selectedProjectID = "project-b"
        XCTAssertTrue(model.transcript.isEmpty)
        model.transcript = "乙项目的故事"
        model.selectedProjectID = "project-a"
        XCTAssertEqual(model.transcript, "导入小说 https://example.org/a")
        XCTAssertEqual(model.transcriptConfidence, 0.7)
        model.selectedProjectID = "project-b"
        XCTAssertEqual(model.transcript, "乙项目的故事")
    }

    @MainActor
    func testTypedInputKeepsRejectedTextAndDoesNotUseSpeechConfidence() {
        let model = VoiceInterviewViewModel()
        model.transcript = "   "
        XCTAssertFalse(model.submitTypedTranscript())
        model.transcript = String(repeating: "字", count: 2001)
        XCTAssertFalse(model.submitTypedTranscript())
        XCTAssertEqual(model.transcript.count, 2001)
        model.transcript = "字大一点"
        model.isListening = true
        XCTAssertFalse(model.submitTypedTranscript())
        XCTAssertEqual(model.transcript, "字大一点")
        model.isListening = false
        model.transcriptConfidence = 0.1
        XCTAssertTrue(model.submitTypedTranscript())
        XCTAssertTrue(model.transcript.isEmpty)
        XCTAssertFalse(model.messages.contains { $0.text.contains("没有听清楚") })
    }

    @MainActor
    func testExistingProjectNeverResumesAtCreateProjectPrompt() {
        let model = VoiceInterviewViewModel()
        model.selectedProjectID = "synthetic-project"
        XCTAssertFalse(model.currentInterviewPrompt.contains("创建新项目"))
        XCTAssertTrue(model.currentInterviewPrompt.contains("继续讲故事"))
    }
}
