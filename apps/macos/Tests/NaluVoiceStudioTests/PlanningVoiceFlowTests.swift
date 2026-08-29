import XCTest
@testable import NaluVoiceStudio

final class PlanningVoiceFlowTests: XCTestCase {
    func testSeasonAndEpisodeDictationReturnSourceTranscript() {
        var flow = PlanningVoiceFlow()
        XCTAssertTrue(flow.begin(.seasonPlan).contains("这一季"))
        XCTAssertEqual(
            flow.consume("从离乡开始，在团圆结束", guardianRequired: false, guardianConfirmed: false),
            .updateSeason(summary: "从离乡开始，在团圆结束", transcript: "从离乡开始，在团圆结束")
        )
        XCTAssertNil(flow.mode)

        _ = flow.begin(.episodePlan)
        XCTAssertEqual(
            flow.consume("主人公错过火车后遇见老友", guardianRequired: false, guardianConfirmed: false),
            .updateEpisode(
                summary: "主人公错过火车后遇见老友",
                transcript: "主人公错过火车后遇见老友"
            )
        )
    }

    func testApprovalRequiresExplicitPositiveLanguage() {
        var flow = PlanningVoiceFlow()
        _ = flow.begin(.seasonApproval)
        assertResponse(
            flow.consume("听起来还行", guardianRequired: false, guardianConfirmed: false),
            contains: "明确说"
        )
        XCTAssertEqual(flow.mode, .seasonApproval)
        XCTAssertEqual(
            flow.consume(
                "我确认这个分集计划",
                guardianRequired: false,
                guardianConfirmed: false
            ),
            .approveSeason(confirmation: "我确认这个分集计划")
        )
        XCTAssertNil(flow.mode)
    }

    func testChildApprovalFailsClosedWithoutGuardianPresence() {
        var flow = PlanningVoiceFlow()
        _ = flow.begin(.seasonApproval)
        assertResponse(
            flow.consume(
                "我确认这个分集计划",
                guardianRequired: true,
                guardianConfirmed: false
            ),
            contains: "不会批准"
        )
        XCTAssertNil(flow.mode)
    }

    private func assertResponse(
        _ action: PlanningVoiceAction,
        contains expected: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        guard case .respond(let message) = action else {
            return XCTFail("expected response action", file: file, line: line)
        }
        XCTAssertTrue(message.contains(expected), file: file, line: line)
    }
}
