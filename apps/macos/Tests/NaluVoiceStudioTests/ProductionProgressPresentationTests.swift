import XCTest
@testable import NaluVoiceStudio

final class ProductionProgressPresentationTests: XCTestCase {
    func testRunningTaskLooksAliveAndExplainsSafePause() {
        let presentation = ProductionProgressPresentation(
            progress: progress(runStatus: "running", stage: "generation", canCancel: true)
        )

        XCTAssertEqual(presentation.attention, .working)
        XCTAssertTrue(presentation.moves)
        XCTAssertTrue(presentation.reassurance.contains("没有停"))
        XCTAssertTrue(presentation.nextStep.contains("安全暂停"))
    }

    func testAmbiguousChargeNeverLooksLikeOrdinaryActiveWork() {
        let presentation = ProductionProgressPresentation(
            progress: progress(
                runStatus: "running",
                stage: "charge_reconciliation",
                canCancel: false
            )
        )

        XCTAssertEqual(presentation.attention, .needsConfirmation)
        XCTAssertFalse(presentation.moves)
        XCTAssertTrue(presentation.reassurance.contains("没有重复扣费"))
        XCTAssertTrue(presentation.nextStep.contains("不会自动重试"))
    }

    func testCancelledTaskExplainsThatRecoveryIsAvailable() {
        let presentation = ProductionProgressPresentation(
            progress: progress(
                runStatus: "cancelled",
                stage: "cancelled",
                canCancel: false,
                canResume: true
            )
        )

        XCTAssertEqual(presentation.attention, .stopped)
        XCTAssertFalse(presentation.moves)
        XCTAssertTrue(presentation.nextStep.contains("恢复"))
    }

    private func progress(
        runStatus: String?,
        stage: String,
        canCancel: Bool,
        canResume: Bool = false
    ) -> EpisodeProductionProgress {
        EpisodeProductionProgress(
            episodeID: "ep_1",
            episodeNumber: 1,
            title: "第一集",
            episodeStatus: "generating",
            runID: "run_1",
            runStatus: runStatus,
            stage: stage,
            progressPercent: 55,
            currentAction: "正在制作",
            explanation: "正在生成镜头",
            canCancel: canCancel,
            canResume: canResume,
            updatedAt: "2026-08-30T00:00:00Z"
        )
    }
}
