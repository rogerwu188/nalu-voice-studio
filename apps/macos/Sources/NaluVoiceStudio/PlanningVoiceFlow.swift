import Foundation

enum PlanningVoiceMode: Equatable, Sendable {
    case seasonPlan
    case episodePlan
    case seasonApproval
    case scriptDraft
    case scriptApproval
    case continuityConfirmation

    var prompt: String {
        switch self {
        case .seasonPlan:
            "请用一两句话告诉我：这一季从哪里开始，最后走到哪里？"
        case .episodePlan:
            "请告诉我这一集发生什么，最重要的转折和结尾是什么？"
        case .seasonApproval:
            "如果您同意当前分集计划，请明确说“我确认这个分集计划”；如果还要修改，请说“不确认”。"
        case .scriptDraft:
            "请把这一集要说的话讲给我听。我会把它保存成新的剧本版本，不会覆盖旧版本。"
        case .scriptApproval:
            "如果您同意当前剧本，请明确说“我确认这个剧本”；如果还要修改，请说“不确认”。"
        case .continuityConfirmation:
            "如果刚才朗读的本集结尾正确，请明确说“我确认这个结尾交接卡”；如果还要修改，请说“不确认”。"
        }
    }
}

enum PlanningVoiceAction: Equatable, Sendable {
    case updateSeason(summary: String, transcript: String)
    case updateEpisode(summary: String, transcript: String)
    case approveSeason(confirmation: String)
    case updateScript(content: String, transcript: String)
    case approveScript(confirmation: String)
    case confirmContinuity(confirmation: String)
    case respond(String)
}

struct PlanningVoiceFlow: Sendable {
    private(set) var mode: PlanningVoiceMode?

    mutating func begin(_ mode: PlanningVoiceMode) -> String {
        self.mode = mode
        return mode.prompt
    }

    mutating func consume(
        _ transcript: String,
        guardianRequired: Bool,
        guardianConfirmed: Bool
    ) -> PlanningVoiceAction {
        let spoken = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !spoken.isEmpty, let mode else {
            return .respond("我没有听到内容，请再说一次。")
        }
        switch mode {
        case .seasonPlan:
            self.mode = nil
            return .updateSeason(summary: spoken, transcript: spoken)
        case .episodePlan:
            self.mode = nil
            return .updateEpisode(summary: spoken, transcript: spoken)
        case .scriptDraft:
            self.mode = nil
            return .updateScript(content: spoken, transcript: spoken)
        case .seasonApproval:
            if guardianRequired && !guardianConfirmed {
                self.mode = nil
                return .respond("这是儿童项目。监护人未确认在场，我不会批准分集计划。")
            }
            let negative = ["不确认", "不同意", "取消", "还要改", "再修改", "不可以"]
            if negative.contains(where: spoken.contains) {
                self.mode = nil
                return .respond("好的，我没有批准。我们可以继续修改分集计划。")
            }
            let positive = ["我确认", "我同意", "确认这个", "同意这个", "就按这个"]
            if positive.contains(where: spoken.contains) {
                self.mode = nil
                return .approveSeason(confirmation: spoken)
            }
            return .respond("为了避免误操作，请明确说“我确认这个分集计划”，或者说“不确认”。")
        case .scriptApproval:
            if guardianRequired && !guardianConfirmed {
                self.mode = nil
                return .respond("这是儿童项目。监护人未确认在场，我不会批准剧本。")
            }
            let negative = ["不确认", "不同意", "取消", "还要改", "再修改", "不可以"]
            if negative.contains(where: spoken.contains) {
                self.mode = nil
                return .respond("好的，我没有批准剧本。我们可以继续修改。")
            }
            let positive = ["我确认", "我同意", "确认这个", "同意这个", "就按这个"]
            if positive.contains(where: spoken.contains) {
                self.mode = nil
                return .approveScript(confirmation: spoken)
            }
            return .respond("为了避免误操作，请明确说“我确认这个剧本”，或者说“不确认”。")
        case .continuityConfirmation:
            if guardianRequired && !guardianConfirmed {
                self.mode = nil
                return .respond("这是儿童项目。监护人未确认在场，我不会保存结尾交接卡。")
            }
            let negative = ["不确认", "不同意", "取消", "还要改", "再修改", "不可以"]
            if negative.contains(where: spoken.contains) {
                self.mode = nil
                return .respond("好的，我没有保存交接卡。您可以继续修改，修改后请重新朗读。")
            }
            let positive = ["我确认", "我同意", "确认这个", "同意这个", "就按这个"]
            if positive.contains(where: spoken.contains) {
                self.mode = nil
                return .confirmContinuity(confirmation: spoken)
            }
            return .respond("为了避免误操作，请明确说“我确认这个结尾交接卡”，或者说“不确认”。")
        }
    }
}
