import XCTest
@testable import NaluVoiceStudio

final class ProductionVoiceCommandTests: XCTestCase {
    func testBarePauseStillBelongsToInterviewFlow() {
        XCTAssertNil(
            ProductionVoiceCommandParser.parse(
                "暂停",
                awaitingPauseConfirmation: false
            )
        )
    }

    func testProductionPauseRequiresSpecificPhraseAndSecondConfirmation() {
        XCTAssertEqual(
            ProductionVoiceCommandParser.parse(
                "请暂停本集制作",
                awaitingPauseConfirmation: false
            ),
            .requestPause
        )
        XCTAssertEqual(
            ProductionVoiceCommandParser.parse(
                "我确认暂停本集制作",
                awaitingPauseConfirmation: true
            ),
            .confirmPause
        )
    }

    func testUserCanCancelPendingPause() {
        XCTAssertEqual(
            ProductionVoiceCommandParser.parse(
                "不用了，不暂停",
                awaitingPauseConfirmation: true
            ),
            .cancelPause
        )
    }

    func testResumeIsExplicitAndUnrelatedSpeechIsNotCaptured() {
        XCTAssertEqual(
            ProductionVoiceCommandParser.parse(
                "恢复本集制作",
                awaitingPauseConfirmation: false
            ),
            .requestResume
        )
        XCTAssertNil(
            ProductionVoiceCommandParser.parse(
                "我们继续讲小时候的故事",
                awaitingPauseConfirmation: false
            )
        )
    }
}
