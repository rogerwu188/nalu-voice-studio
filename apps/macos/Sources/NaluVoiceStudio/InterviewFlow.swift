import Foundation

enum InterviewStep: Equatable {
    case idle, audience, guardianName, guardianConsent, premise, title, episodeCount, creating
}

enum InterviewFlowAction {
    case respond(String)
    case create(ProjectDraft, String)
}

struct InterviewFlow {
    private(set) var draft = ProjectDraft()
    private(set) var step = InterviewStep.idle
    private(set) var isPaused = false
    private var history: [Snapshot] = []

    mutating func begin() -> String {
        draft = ProjectDraft()
        step = .audience
        isPaused = false
        history = []
        return "我们慢慢来。请先告诉我，是您自己使用、家里长辈使用，还是小朋友和监护人一起使用？"
    }

    mutating func consume(_ spoken: String) -> InterviewFlowAction {
        if spoken.contains("暂停") {
            isPaused = true
            return .respond("好的，已经暂停。准备好后说“继续”就可以。")
        }
        if spoken.contains("继续"), isPaused {
            isPaused = false
            return .respond("我们继续。\(prompt)")
        }
        if spoken.contains("再说一遍") || spoken.contains("重复问题") {
            return .respond(prompt)
        }
        if spoken.contains("上一步") || spoken.contains("返回") || spoken.contains("重新说") {
            guard let previous = history.popLast() else {
                return .respond("现在已经是第一步了。")
            }
            step = previous.step
            draft = previous.draft
            isPaused = false
            return .respond("好的，我们回到上一步。\(prompt)")
        }
        if isPaused {
            return .respond("采访还在暂停中。准备好后请说“继续”。")
        }

        history.append(Snapshot(step: step, draft: draft))
        switch step {
        case .idle:
            return .respond("我记下来了。需要建立新项目时，请点左侧的“创建新项目”。")
        case .audience:
            if spoken.contains("小朋友") || spoken.contains("孩子") || spoken.contains("儿童") {
                draft.audienceMode = "child"
                step = .guardianName
                return .respond("好的。为了保护小朋友，请监护人告诉我您的称呼。")
            }
            if spoken.contains("长辈") || spoken.contains("老人") || spoken.contains("老年") {
                draft.audienceMode = "older_adult"
            } else if spoken.contains("一家") || spoken.contains("全家") {
                draft.audienceMode = "family"
            } else {
                draft.audienceMode = "general"
            }
            step = .premise
            return .respond("明白了。请告诉我，这个故事主要讲什么？")
        case .guardianName:
            draft.projectBible["guardian_name"] = spoken
            step = .guardianConsent
            return .respond("请监护人确认：您同意陪同孩子创作，并在使用照片、声音或发布作品前再次授权吗？")
        case .guardianConsent:
            let approved = spoken.contains("同意") || spoken.contains("确认") || spoken.contains("可以")
            guard approved else {
                return .respond("没有监护人明确同意，我不能继续儿童项目。您可以说“我同意”，或者返回上一步。")
            }
            draft.projectBible["guardian_setup_approved"] = "true"
            step = .premise
            return .respond("谢谢您的确认。现在请告诉我，这个故事主要讲什么？")
        case .premise:
            draft.description = spoken
            step = .title
            return .respond("很好。您想给这个系列取什么名字？")
        case .title:
            draft.title = spoken
            step = .episodeCount
            return .respond("这个系列先计划做多少集？您可以说，例如“十集”。")
        case .episodeCount:
            draft.plannedEpisodeCount = Self.episodeCount(from: spoken)
            step = .creating
            return .create(draft, "好的，我正在建立项目、第一季和分集计划。")
        case .creating:
            return .respond("项目正在建立，请稍等一下。")
        }
    }

    mutating func creationSucceeded() {
        step = .idle
        history = []
    }

    mutating func creationFailed() {
        step = .episodeCount
    }

    var prompt: String {
        switch step {
        case .idle: "请点左侧的“创建新项目”，我们从头开始。"
        case .audience: "是您自己使用、家里长辈使用，还是小朋友和监护人一起使用？"
        case .guardianName: "请监护人告诉我您的称呼。"
        case .guardianConsent: "请监护人明确说是否同意陪同孩子创作。"
        case .premise: "请告诉我，这个故事主要讲什么？"
        case .title: "您想给这个系列取什么名字？"
        case .episodeCount: "这个系列先计划做多少集？"
        case .creating: "项目正在建立，请稍等一下。"
        }
    }

    static func episodeCount(from answer: String) -> Int {
        let digits = answer.filter(\.isNumber)
        if let value = Int(digits) {
            return min(max(value, 1), 50)
        }
        let common = [("二十", 20), ("十二", 12), ("十", 10), ("九", 9), ("八", 8),
                      ("七", 7), ("六", 6), ("五", 5), ("四", 4), ("三", 3),
                      ("两", 2), ("二", 2), ("一", 1)]
        return common.first(where: { answer.contains($0.0) })?.1 ?? 6
    }

    private struct Snapshot {
        let step: InterviewStep
        let draft: ProjectDraft
    }
}
