import XCTest
@testable import NaluVoiceStudio

final class AIServiceModelsTests: XCTestCase {
    func testSelectionsAreScopedToProviderAndPersist() throws {
        let suite = "nalu-model-tests-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let provider = try AIServiceEndpoint("https://hopsapi.com/v1")
        let other = try AIServiceEndpoint(AIServiceEndpoint.official)
        let selected = AIServiceModels(research: "gpt-5.4", realtime: "provider-realtime", transcription: "provider-transcribe")
        try selected.save(for: provider, defaults: defaults)
        XCTAssertEqual(try AIServiceModels.load(for: provider, defaults: defaults), selected)
        XCTAssertEqual(try AIServiceModels.load(for: other, defaults: defaults), AIServiceModels())
        XCTAssertEqual(try AIServiceModels.load(for: AIServiceEndpoint("https://hopsapi.com/v1/"), defaults: defaults), selected)
    }

    func testInvalidModelIDsAreRejected() {
        for name in ["", "sk-secret", "model with space", "model\n", "<script>", String(repeating: "a", count: 129)] {
            XCTAssertThrowsError(try AIServiceModels(research: name).validated())
        }
    }

    func testInvalidSavePreservesPreviousConfiguration() throws {
        let suite = "nalu-model-rejection-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let endpoint = try AIServiceEndpoint("https://hopsapi.com/v1")
        let original = AIServiceModels(research: "chosen-research")
        try original.save(for: endpoint, defaults: defaults)
        XCTAssertThrowsError(try AIServiceModels(realtime: "").save(for: endpoint, defaults: defaults))
        XCTAssertEqual(try AIServiceModels.load(for: endpoint, defaults: defaults), original)
    }

    func testRealtimeResponseMustMatchRequestedModel() throws {
        let now = Date()
        let data = try JSONSerialization.data(withJSONObject: [
            "value": "ephemeral-test-value", "expires_at": now.timeIntervalSince1970 + 60,
            "session": ["type": "realtime", "model": "selected-voice"]
        ])
        XCTAssertEqual(try RealtimeAPIContract.validatedClientSecret(
            from: data, now: now, expectedModel: "selected-voice"), "ephemeral-test-value")
        XCTAssertThrowsError(try RealtimeAPIContract.validatedClientSecret(
            from: data, now: now, expectedModel: "other-voice"))
    }

    func testRealtimePayloadUsesDistinctExplicitModels() throws {
        let models = AIServiceModels(research: "research", realtime: "voice", transcription: "transcribe")
        let data = try RealtimeSessionConfiguration.requestBody(instructions: "test", models: models)
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let session = try XCTUnwrap(root["session"] as? [String: Any])
        XCTAssertEqual(session["model"] as? String, "voice")
        let audio = try XCTUnwrap(session["audio"] as? [String: Any])
        let input = try XCTUnwrap(audio["input"] as? [String: Any])
        let transcription = try XCTUnwrap(input["transcription"] as? [String: Any])
        XCTAssertEqual(transcription["model"] as? String, "transcribe")
    }
}
