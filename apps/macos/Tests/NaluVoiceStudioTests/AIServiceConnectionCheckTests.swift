import XCTest
@testable import NaluVoiceStudio

final class AIServiceConnectionCheckTests: XCTestCase {
    func testSavedSelectionsAreCheckedIndividuallyWithoutClaimingSupport() throws {
        let data = Data(#"{"data":[{"id":"query"}]}"#.utf8)
        let result = try AIServiceModelList.summary(data, secret: "private-key", savedModels:
            AIServiceModels(research: "query", realtime: "voice", transcription: "transcribe"))
        XCTAssertTrue(result.contains("已保存的查询模型：列表中可见（功能未验证）"))
        XCTAssertTrue(result.contains("已保存的实时语音模型：列表中未找到，请向服务商核实"))
        XCTAssertTrue(result.contains("已保存的转写模型：列表中未找到，请向服务商核实"))
    }

    func testMembershipUsesFullListNotTenDisplayedNames() throws {
        let ids = (0..<15).map { ["id": "model-\($0)"] }
        let bytes = try JSONSerialization.data(withJSONObject: ["data": ids])
        let result = try AIServiceModelList.summary(bytes, secret: "private-key", savedModels:
            AIServiceModels(research: "model-14", realtime: "model-13", transcription: "model-12"))
        XCTAssertFalse(result.contains("未找到"))
        XCTAssertFalse(result.contains("model-14"))
        XCTAssertTrue(result.contains("功能未验证"))
    }

    func testSavedSelectionNeverEchoesCredential() throws {
        let bytes = Data(#"{"data":[{"id":"private-key"}]}"#.utf8)
        let result = try AIServiceModelList.summary(bytes, secret: "private-key", savedModels:
            AIServiceModels(research: "private-key"))
        XCTAssertFalse(result.contains("private-key"))
        XCTAssertTrue(result.contains("已保存的查询模型：列表中未找到"))
    }

    func testSuccessfulModelListDoesNotClaimRealtimeAcceptance() throws {
        let data = Data(#"{"data":[{"id":"gpt-realtime-2.1"},{"id":"gpt-test"}]}"#.utf8)
        let result = try AIServiceModelList.summary(data, secret: "test-secret")
        XCTAssertTrue(result.contains("2 个模型"))
        XCTAssertTrue(result.contains("gpt-realtime-2.1"))
        XCTAssertTrue(result.contains("不代表"))
    }

    func testMalformedAndOversizedListsFail() {
        XCTAssertThrowsError(try AIServiceModelList.summary(Data("{}".utf8), secret: "test"))
        XCTAssertThrowsError(try AIServiceModelList.summary(Data(repeating: 0, count: 1_000_001), secret: "test"))
    }

    func testProviderEchoesAndMarkupAreNotDisplayed() throws {
        let data = Data(#"{"data":[{"id":"sk-sensitive"},{"id":"secret-echo"},{"id":"<script>"},{"id":"safe-model"}]}"#.utf8)
        let result = try AIServiceModelList.summary(data, secret: "secret-echo")
        XCTAssertFalse(result.contains("sk-sensitive"))
        XCTAssertFalse(result.contains("secret-echo"))
        XCTAssertFalse(result.contains("<script>"))
        XCTAssertTrue(result.contains("safe-model"))
    }
}
