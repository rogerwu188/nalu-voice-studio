import XCTest
@testable import NaluVoiceStudio

final class InterviewFlowTests: XCTestCase {
    func testCompletesVoiceOnlyProjectSetup() {
        var flow = InterviewFlow()
        XCTAssertTrue(flow.begin().contains("故事"))
        XCTAssertEqual(flow.step, .premise)

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
