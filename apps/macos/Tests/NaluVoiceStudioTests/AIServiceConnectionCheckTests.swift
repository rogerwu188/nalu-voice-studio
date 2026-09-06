import XCTest
@testable import NaluVoiceStudio

final class AIServiceConnectionCheckTests: XCTestCase {
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
