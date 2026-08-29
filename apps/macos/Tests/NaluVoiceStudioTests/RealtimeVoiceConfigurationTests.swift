import XCTest
@testable import NaluVoiceStudio

final class RealtimeVoiceConfigurationTests: XCTestCase {
    func testSessionUsesCurrentRealtimeModelAndSlowSpeakerVAD() throws {
        let data = try RealtimeSessionConfiguration.requestBody(
            instructions: "先回答，再回到采访。"
        )
        let root = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        let session = try XCTUnwrap(root["session"] as? [String: Any])
        XCTAssertEqual(session["model"] as? String, "gpt-realtime-2.1")
        XCTAssertEqual(session["instructions"] as? String, "先回答，再回到采访。")

        let audio = try XCTUnwrap(session["audio"] as? [String: Any])
        let input = try XCTUnwrap(audio["input"] as? [String: Any])
        let vad = try XCTUnwrap(input["turn_detection"] as? [String: Any])
        XCTAssertEqual(vad["type"] as? String, "semantic_vad")
        XCTAssertEqual(vad["eagerness"] as? String, "low")
        XCTAssertEqual(vad["interrupt_response"] as? Bool, true)
        XCTAssertEqual(vad["create_response"] as? Bool, true)
        XCTAssertEqual((audio["output"] as? [String: Any])?["voice"] as? String, "marin")

        let tools = try XCTUnwrap(session["tools"] as? [[String: Any]])
        XCTAssertEqual(tools.count, 1)
        XCTAssertEqual(tools[0]["name"] as? String, "record_interview_answer")
        XCTAssertEqual(session["tool_choice"] as? String, "auto")
        let parameters = try XCTUnwrap(tools[0]["parameters"] as? [String: Any])
        XCTAssertEqual(parameters["additionalProperties"] as? Bool, false)
    }

    func testVisibleStatesDescribeConnectionAndInterruption() {
        XCTAssertEqual(RealtimeVoiceState.listening.label, "正在听您说话")
        XCTAssertTrue(RealtimeVoiceState.speaking.label.contains("随时插话"))
        XCTAssertFalse(RealtimeVoiceState.off.isActive)
        XCTAssertTrue(RealtimeVoiceState.connecting.isActive)
        XCTAssertTrue(RealtimeVoiceState.reconnecting.isActive)
        XCTAssertTrue(RealtimeVoiceState.reconnecting.label.contains("恢复"))
    }

    func testToolResultIsAJSONStringWithVisibleConfirmationFlag() throws {
        let result = RealtimeInterviewToolResult(
            accepted: false,
            message: "请回到界面确认",
            nextPrompt: "",
            requiresVisibleConfirmation: true
        )
        let data = try XCTUnwrap(result.jsonString().data(using: .utf8))
        let decoded = try JSONDecoder().decode(RealtimeInterviewToolResult.self, from: data)
        XCTAssertEqual(decoded, result)
    }

    func testJavaScriptStringLiteralEscapesSecretsAndToolOutput() throws {
        let literal = try XCTUnwrap(
            RealtimeJavaScriptBridge.stringLiteral("ek_test_'\"\\\n</script>")
        )
        let data = try XCTUnwrap(literal.data(using: .utf8))
        XCTAssertEqual(try JSONDecoder().decode(String.self, from: data), "ek_test_'\"\\\n</script>")
    }

    func testInterviewToolCallAllowsOnlyExactNarrowSchema() throws {
        let valid = RealtimeInterviewToolCall.parse([
            "name": "record_interview_answer",
            "callID": "call_123",
            "arguments": #"{"answer":"  我自己使用  "}"#,
        ])
        XCTAssertEqual(valid, RealtimeInterviewToolCall(callID: "call_123", answer: "我自己使用"))

        XCTAssertNil(RealtimeInterviewToolCall.parse([
            "name": "delete_project",
            "callID": "call_456",
            "arguments": #"{"answer":"删除"}"#,
        ]))
        XCTAssertNil(RealtimeInterviewToolCall.parse([
            "name": "record_interview_answer",
            "callID": "call_789",
            "arguments": #"{"answer":"同意","publish":true}"#,
        ]))
        XCTAssertNil(RealtimeInterviewToolCall.parse([
            "name": "record_interview_answer",
            "callID": String(repeating: "x", count: 513),
            "arguments": #"{"answer":"我自己使用"}"#,
        ]))
    }

    func testSessionLimitIsBoundedAndReadable() {
        XCTAssertEqual(RealtimeSessionLimit.normalized(5), 5)
        XCTAssertEqual(RealtimeSessionLimit.normalized(20), 20)
        XCTAssertEqual(RealtimeSessionLimit.normalized(60), 10)
        XCTAssertEqual(
            RealtimeSessionLimit.elapsedLabel(seconds: 125, limitMinutes: 10),
            "02:05 / 10:00"
        )
    }
}
