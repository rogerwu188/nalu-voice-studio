import Foundation
import Testing
@testable import NaluVoiceStudio

struct ProductionAuthorizationTests {
    private func conversation(child: Bool = false) -> ProductionBudgetConversation {
        ProductionBudgetConversation(runID: "run-one", episodeID: "episode-one", preview: .init(
            source_event_id: "approved-plan", expected_plan_sha256: String(repeating: "a", count: 64),
            expected_package_sha256: String(repeating: "b", count: 64),
            expected_library_sha256: String(repeating: "c", count: 64)), guardianRequired: child)
    }

    @Test func amountParsingDoesNotInventUnitsOrInterpretAmbiguousAmounts() {
        for (spoken, expected) in [("本集预算一千积分", 1000), ("预算改为两千五百积分", 2500),
                                   ("１２３积分", 123), ("一千零五积分", 1005), ("十五积分", 15),
                                   ("一万两千积分", 12000), ("预算是1000000积分", 1000000)] {
            #expect(ProductionBudgetConversation.budget(spoken) == expected)
        }
        for spoken in ["一千五积分", "1.5积分", "预算-100积分", "100元", "预算一千积分吗", "一百二百积分",
                       "零积分", "0积分", "1000001积分", "100积分或200积分", "预算一千积分并立即扣费", "十万积分"] {
            #expect(ProductionBudgetConversation.budget(spoken) == nil)
        }
    }

    @Test func readbackMustPrecedeExplicitApprovalAndUnrelatedQuestionsRemainUnrelated() {
        var state = conversation()
        if case .submit = state.answer("确认本集预算") { Issue.record("no amount was read back") }
        if case .reply(let readback) = state.answer("本集预算1000积分") {
            #expect(readback.contains("1000"))
            #expect(readback.contains("不是人民币"))
            #expect(readback.contains("不会生成或扣费"))
        } else { Issue.record("must read back instead of submitting") }
        for question in ["不同意", "不确认本集预算", "为什么这个故事要拍六集", "你好吗"] {
            if case .submit = state.answer(question) { Issue.record("not consent") }
        }
        if case .unrelated = state.answer("为什么这个故事要拍六集") {} else { Issue.record("answer the question normally") }
        _ = state.answer("预算改为500积分")
        if case .submit(let draft) = state.answer("确认本集预算") {
            #expect(draft.confirmed_run_budget_credits == 500)
            #expect(draft.source_event_id == "approved-plan")
            #expect(!draft.guardian_approval)
            if case .submit(let retry) = state.answer("重试制作确认") { #expect(retry == draft) }
            else { Issue.record("retry must retain the identical request") }
            if case .submit = state.answer("预算改为900积分") { Issue.record("cannot replace uncertain request") }
        } else { Issue.record("explicit confirmation should submit") }
    }

    @Test func childNeedsExplicitGuardianAndCancellationNeverSubmits() {
        var state = conversation(child: true)
        _ = state.answer("1000积分")
        if case .submit = state.answer("确认本集预算") { Issue.record("guardian not confirmed") }
        if case .submit(let draft) = state.answer("我是监护人，确认本集预算") {
            #expect(draft.guardian_approval)
        } else { Issue.record("guardian confirmation missing") }
        if case .cancel = state.answer("取消制作确认") {} else { Issue.record("must stop this conversation") }
    }
}
