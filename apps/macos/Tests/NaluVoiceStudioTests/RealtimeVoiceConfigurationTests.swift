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
    }

    func testVisibleStatesDescribeConnectionAndInterruption() {
        XCTAssertEqual(RealtimeVoiceState.listening.label, "正在听您说话")
        XCTAssertTrue(RealtimeVoiceState.speaking.label.contains("随时插话"))
        XCTAssertFalse(RealtimeVoiceState.off.isActive)
        XCTAssertTrue(RealtimeVoiceState.connecting.isActive)
    }
}
