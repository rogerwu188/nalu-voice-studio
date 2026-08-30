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

    func testScriptDictationAndApprovalAreExplicit() {
        var flow = PlanningVoiceFlow()
        _ = flow.begin(.scriptDraft)
        XCTAssertEqual(
            flow.consume("清晨，主人公走进车站", guardianRequired: false, guardianConfirmed: false),
            .updateScript(
                content: "清晨，主人公走进车站",
                transcript: "清晨，主人公走进车站"
            )
        )
        _ = flow.begin(.scriptApproval)
        assertResponse(
            flow.consume("差不多吧", guardianRequired: false, guardianConfirmed: false),
            contains: "明确说"
        )
        XCTAssertEqual(
            flow.consume("我确认这个剧本", guardianRequired: false, guardianConfirmed: false),
            .approveScript(confirmation: "我确认这个剧本")
        )

        _ = flow.begin(.scriptApproval)
        assertResponse(
            flow.consume("我确认这个剧本", guardianRequired: true, guardianConfirmed: false),
            contains: "不会批准剧本"
        )
    }

    func testContinuityConfirmationIsExplicitAndGuardianProtected() {
        var flow = PlanningVoiceFlow()
        XCTAssertTrue(flow.begin(.continuityConfirmation).contains("结尾交接卡"))
        assertResponse(
            flow.consume("应该没问题", guardianRequired: false, guardianConfirmed: false),
            contains: "明确说"
        )
        XCTAssertEqual(flow.mode, .continuityConfirmation)
        XCTAssertEqual(
            flow.consume(
                "我确认这个结尾交接卡",
                guardianRequired: false,
                guardianConfirmed: false
            ),
            .confirmContinuity(confirmation: "我确认这个结尾交接卡")
        )
        XCTAssertNil(flow.mode)

        _ = flow.begin(.continuityConfirmation)
        assertResponse(
            flow.consume(
                "我确认这个结尾交接卡",
                guardianRequired: true,
                guardianConfirmed: false
            ),
            contains: "监护人未确认"
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
