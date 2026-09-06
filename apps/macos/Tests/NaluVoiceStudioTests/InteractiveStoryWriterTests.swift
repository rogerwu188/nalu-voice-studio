import XCTest
@testable import NaluVoiceStudio

final class InteractiveStoryWriterTests: XCTestCase {
    func testRequestUsesConfiguredHostAndCarriesPreviousSourceContext() throws {
        let state = InteractiveStoryState(revision: 2, turns: [
            .init(turn_id: "source", text: "查找老照片", source_mode: "web_source", status: "answered",
                  answer: .init(reply: "来源 https://example.com/archive", summary: "", episode_drafts: [], outcome: "answered")),
        ], summary: "外婆住在海边", episode_drafts: [])
        let request = try InteractiveStoryWriter.makeRequest(state: state, apiKey: "fixture-key",
            endpoint: AIServiceEndpoint("https://hopsapi.com/v1"), model: "fixture-model")
        XCTAssertEqual(request.url?.absoluteString, "https://hopsapi.com/v1/chat/completions")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(request.httpBody)) as? [String: Any])
        XCTAssertEqual(body["model"] as? String, "fixture-model")
        XCTAssertEqual(body["store"] as? Bool, false)
        let messages = try XCTUnwrap(body["messages"] as? [[String: String]])
        XCTAssertTrue(messages.last?["content"]?.contains("外婆住在海边") == true)
        XCTAssertTrue(messages.last?["content"]?.contains("example.com") == true)
    }

    func testParsesConcreteEpisodeDraftAndRejectsTruncation() throws {
        let answer = InteractiveStoryAnswer(reply: "第一集这样写，您想改哪里？", summary: "海边童年",
            episode_drafts: [.init(episode_number: 1, title: "海边", outline: "外婆带我看海", script: "外景 海边 清晨\n外婆：慢慢走。")], outcome: "answered")
        let content = String(decoding: try JSONEncoder().encode(answer), as: UTF8.self)
        func response(_ finish: String) throws -> Data {
            try JSONSerialization.data(withJSONObject: ["choices": [["finish_reason": finish, "message": ["content": content]]]])
        }
        XCTAssertEqual(try InteractiveStoryWriter.parseResponse(response("stop")), answer)
        XCTAssertThrowsError(try InteractiveStoryWriter.parseResponse(response("length")))
    }

    func testRefusesEmptyScriptsAndModelPretendingApproval() throws {
        for outcome in ["answered", "approved"] {
            let answer = InteractiveStoryAnswer(reply: "好了", summary: "", episode_drafts: [
                .init(episode_number: 1, title: "海边", outline: "童年", script: "")
            ], outcome: outcome)
            let content = String(decoding: try JSONEncoder().encode(answer), as: UTF8.self)
            let data = try JSONSerialization.data(withJSONObject: ["choices": [["finish_reason": "stop", "message": ["content": content]]]])
            XCTAssertThrowsError(try InteractiveStoryWriter.parseResponse(data))
        }
    }
}
