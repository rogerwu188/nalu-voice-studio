import XCTest
@testable import NaluVoiceStudio

final class FinalMasterSpeechRecognizerTests: XCTestCase {
    func testRecognitionResultBuildsFailClosedLocalSemanticEvidence() {
        let result = FinalMasterRecognitionResult(
            transcript: "我们回家了",
            segments: [
                SemanticASRSegmentDraft(
                    startSeconds: 0.5,
                    endSeconds: 1.8,
                    text: "我们回家了",
                    confidence: 0.92
                )
            ],
            recognizerVersion: "macOS test",
            generatedAt: "2026-08-31T00:00:00Z"
        )

        let draft = result.semanticQADraft(masterSHA256: String(repeating: "a", count: 64))

        XCTAssertEqual(draft.recognizerID, "apple-speech-on-device")
        XCTAssertEqual(draft.locale, "zh-CN")
        XCTAssertTrue(draft.localRecognition)
        XCTAssertEqual(draft.transcript, "我们回家了")
        XCTAssertEqual(draft.segments.count, 1)
    }
}
