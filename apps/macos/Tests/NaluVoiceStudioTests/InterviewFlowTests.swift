import XCTest
@testable import NaluVoiceStudio

final class InterviewFlowTests: XCTestCase {
    func testCompletesVoiceOnlyProjectSetup() {
        var flow = InterviewFlow()
        XCTAssertTrue(flow.begin().contains("长辈"))
        XCTAssertEqual(flow.step, .audience)

        assertResponse(flow.consume("家里老人使用"), contains: "广告片")
        XCTAssertEqual(flow.draft.audienceMode, "older_adult")

        assertResponse(flow.consume("连续短剧"), contains: "故事")

        assertResponse(flow.consume("我想讲年轻时离开故乡的经历"), contains: "名字")
        XCTAssertEqual(flow.draft.description, "我想讲年轻时离开故乡的经历")
        XCTAssertEqual(flow.step, .title)

        assertResponse(flow.consume("我的远方"), contains: "多少集")
        guard case .create(let draft, _) = flow.consume("十二集") else {
            return XCTFail("expected an atomic project creation action")
        }
        XCTAssertEqual(draft.title, "我的远方")
        XCTAssertEqual(draft.plannedEpisodeCount, 12)
        XCTAssertEqual(flow.step, .creating)
    }

    func testPauseResumeRepeatAndCorrectionPreserveAnswers() {
        var flow = InterviewFlow()
        _ = flow.begin()
        _ = flow.consume("我自己使用")
        _ = flow.consume("短剧")
        _ = flow.consume("第一版故事")

        assertResponse(flow.consume("暂停"), contains: "已经暂停")
        XCTAssertTrue(flow.isPaused)
        assertResponse(flow.consume("这句话不能当标题"), contains: "暂停中")
        XCTAssertEqual(flow.step, .title)

        assertResponse(flow.consume("继续"), contains: "名字")
        XCTAssertFalse(flow.isPaused)
        assertResponse(flow.consume("再说一遍"), contains: "名字")
        XCTAssertEqual(flow.step, .title)

        _ = flow.consume("旧标题")
        assertResponse(flow.consume("返回上一步"), contains: "名字")
        XCTAssertEqual(flow.step, .title)
        _ = flow.consume("新标题")
        guard case .create(let draft, _) = flow.consume("3集") else {
            return XCTFail("expected corrected project creation action")
        }
        XCTAssertEqual(draft.description, "第一版故事")
        XCTAssertEqual(draft.title, "新标题")
        XCTAssertEqual(draft.plannedEpisodeCount, 3)
    }

    func testEpisodeCountIsBoundedAndUnderstandsCommonChinese() {
        XCTAssertEqual(InterviewFlow.episodeCount(from: "十二集"), 12)
        XCTAssertEqual(InterviewFlow.episodeCount(from: "两集"), 2)
        XCTAssertEqual(InterviewFlow.episodeCount(from: "0"), 1)
        XCTAssertEqual(InterviewFlow.episodeCount(from: "99集"), 50)
        XCTAssertEqual(InterviewFlow.episodeCount(from: "没有说清"), 6)
    }

    func testChildProjectCannotPassGuardianSetupWithoutExplicitConsent() {
        var flow = InterviewFlow()
        _ = flow.begin()
        assertResponse(flow.consume("是孩子使用"), contains: "监护人")
        XCTAssertEqual(flow.step, .guardianName)
        assertResponse(flow.consume("妈妈李女士"), contains: "确认")
        XCTAssertEqual(flow.step, .guardianConsent)

        assertResponse(flow.consume("我还没想好"), contains: "不能继续")
        XCTAssertEqual(flow.step, .guardianConsent)
        assertResponse(flow.consume("我同意并确认"), contains: "动画")
        XCTAssertEqual(flow.step, .creativeFormat)
        assertResponse(flow.consume("动画片"), contains: "动画")
        XCTAssertEqual(flow.step, .premise)
        XCTAssertEqual(flow.draft.audienceMode, "child")
        XCTAssertEqual(flow.draft.creativeFormat, "animation_series")
        XCTAssertEqual(flow.draft.projectBible["guardian_name"], "妈妈李女士")
        XCTAssertEqual(flow.draft.projectBible["guardian_setup_approved"], "true")
    }

    func testCommercialIntentCreatesAnUnassignedFailClosedRoute() {
        var flow = InterviewFlow()
        _ = flow.begin()
        _ = flow.consume("我自己使用")
        assertResponse(flow.consume("我要给护肤品做广告片"), contains: "广告创作简报")
        XCTAssertEqual(flow.draft.creativeFormat, "commercial_campaign")
        XCTAssertEqual(flow.draft.productionPipeline, "unassigned")
    }

    func testConversationInterruptionIsAnsweredWithoutAdvancingOrPollutingDraft() {
        var flow = InterviewFlow()
        _ = flow.begin()
        _ = flow.consume("我自己使用")
        XCTAssertEqual(flow.step, .creativeFormat)

        assertResponse(
            flow.consume("哈喽，你在干什么？你为什么不和我交互？"),
            contains: "先回答"
        )
        XCTAssertEqual(flow.step, .creativeFormat)
        XCTAssertEqual(flow.draft.creativeFormat, "short_drama_series")

        assertResponse(
            flow.consume("我在问你问题，希望你先跟我交流沟通"),
            contains: "您不必顺着固定流程"
        )
        XCTAssertEqual(flow.step, .creativeFormat)

        assertResponse(flow.consume("动画片"), contains: "主要角色")
        XCTAssertEqual(flow.step, .premise)
        XCTAssertEqual(flow.draft.creativeFormat, "animation_series")
    }

    private func assertResponse(
        _ action: InterviewFlowAction,
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
