import XCTest
@testable import NaluVoiceStudio

final class NativeConversationQAScenarioTests: XCTestCase {
    func testScenarioIsAbsentByDefault() throws {
        XCTAssertFalse(try NativeConversationQAScenario.isRequested(inherited: [:]))
    }

    func testScenarioRejectsMissingIsolationFlagAndUnknownName() {
        XCTAssertThrowsError(
            try NativeConversationQAScenario.isRequested(
                inherited: [
                    NativeConversationQAScenario.environmentKey:
                        NativeConversationQAScenario.conversationScroll,
                ]
            )
        )
        XCTAssertThrowsError(
            try NativeConversationQAScenario.isRequested(
                inherited: [
                    NativeConversationQAScenario.environmentKey: "unknown",
                    RuntimeApplicationSupportResolver.localQAFlag: "1",
                ]
            )
        )
    }

    func testScenarioRejectsNonTemporaryApplicationSupport() {
        XCTAssertThrowsError(
            try NativeConversationQAScenario.isRequested(
                inherited: [
                    NativeConversationQAScenario.environmentKey:
                        NativeConversationQAScenario.conversationScroll,
                    RuntimeApplicationSupportResolver.localQAFlag: "1",
                    RuntimeApplicationSupportResolver.localQAPath: "/Users/example/Nalu QA",
                ]
            )
        )
    }

    func testScenarioAcceptsExistingTemporaryIsolationAndHasLongFinalTurn() throws {
        let root = FileManager.default.temporaryDirectory.appending(
            path: "nalu-conversation-qa-tests-\(UUID().uuidString)",
            directoryHint: .isDirectory
        )
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        XCTAssertTrue(
            try NativeConversationQAScenario.isRequested(
                inherited: [
                    NativeConversationQAScenario.environmentKey:
                        NativeConversationQAScenario.conversationScroll,
                    RuntimeApplicationSupportResolver.localQAFlag: "1",
                    RuntimeApplicationSupportResolver.localQAPath: root.path,
                ]
            )
        )

        let fixture = NativeConversationQAScenario.fixture()
        XCTAssertGreaterThanOrEqual(fixture.messages.count, 18)
        XCTAssertEqual(fixture.messages.last?.speaker, .user)
        XCTAssertTrue(
            fixture.finalTranscript.hasPrefix(NativeConversationQAScenario.finalTranscriptPrefix)
        )
        XCTAssertNotEqual(fixture.firstTranscript, fixture.finalTranscript)
        XCTAssertGreaterThan(fixture.confidence, 0.9)
    }
}
