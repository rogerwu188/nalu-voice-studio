import XCTest
@testable import NaluVoiceStudio

final class InteractiveStoryTests: XCTestCase {
    func testRuntimeStateDecodesPendingAndAnsweredTurns() throws {
        let data = Data(#"{"revision":3,"summary":"童年","episode_drafts":[{"episode_number":1,"title":"海边","outline":"遇见外婆","script":"外景 海边"}],"turns":[{"turn_id":"a","text":"我小时候住海边","source_mode":"narrated_story","status":"answered","answer":{"reply":"后来呢？","summary":"童年","episode_drafts":[],"outcome":"answered"}},{"turn_id":"b","text":"网上找资料","source_mode":"web_source","status":"pending"}]}"#.utf8)
        let state = try JSONDecoder().decode(InteractiveStoryState.self, from: data)
        XCTAssertEqual(state.revision, 3)
        XCTAssertEqual(state.turns.first?.answer?.reply, "后来呢？")
        XCTAssertNil(state.turns.last?.answer)
        XCTAssertEqual(state.episode_drafts.first?.script, "外景 海边")
    }

    @MainActor
    func testExistingProjectNeverResumesAtCreateProjectPrompt() {
        let model = VoiceInterviewViewModel()
        model.selectedProjectID = "synthetic-project"
        XCTAssertFalse(model.currentInterviewPrompt.contains("创建新项目"))
        XCTAssertTrue(model.currentInterviewPrompt.contains("继续讲故事"))
    }
}
