import Foundation

enum InterviewStep: Equatable {
    case idle, audience, guardianName, guardianConsent, creativeFormat, premise, title
    case episodeCount, creating
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
        if let interruption = InterviewInterruptionRouter.response(
            for: spoken, resumePrompt: prompt
        ) {
            return .respond(interruption)
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
            step = .creativeFormat
            return .respond("明白了。您想做剧情化自传、真实资料纪录片、动画片，还是广告片？")
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
            step = .creativeFormat
            return .respond("谢谢您的确认。小朋友想做连续动画、故事短剧、纪录片，还是一条广告片？")
        case .creativeFormat:
            if spoken.contains("广告") || spoken.contains("宣传片") {
                draft.creativeFormat = "commercial_campaign"
                draft.productionPipeline = "unassigned"
                draft.plannedEpisodeCount = 1
                step = .premise
                return .respond("好的，我们先建立广告创作简报。请告诉我产品、观众和最想表达的重点。")
            }
            if spoken.contains("动画") || spoken.contains("卡通") {
                draft.creativeFormat = "animation_series"
                draft.productionPipeline = "qingshan-short-drama"
                step = .premise
                return .respond("好的，我们来做动画系列。请告诉我主要角色和故事想法。")
            }
            if spoken.contains("纪录") || spoken.contains("口述史") || spoken.contains("真实资料") {
                draft.creativeFormat = "documentary_series"
                draft.productionPipeline = "unassigned"
                let hybrid = spoken.contains("重现") || spoken.contains("混合")
                    || spoken.contains("纪实剧情")
                draft.projectBible["documentary_mode"] = hybrid
                    ? "archival_with_reenactment" : "archival_voiceover"
                draft.projectBible["generated_reenactment_label_required"] = "true"
                step = .premise
                return .respond(
                    hybrid
                        ? "好的，我们做真实资料加少量剧情重现的纪实系列。请先说最想保存的真实经历，以及手上有哪些照片、录音、手稿或家庭视频。"
                        : "好的，我们做照片、家庭视频和画外音为主的纪录片系列。请先说最想保存的真实经历，以及手上有哪些资料。"
                )
            }
            draft.creativeFormat = "short_drama_series"
            draft.productionPipeline = "qingshan-short-drama"
            step = .premise
            return .respond("好的，我们来做连续短剧。请告诉我，这个故事主要讲什么？")
        case .premise:
            draft.description = spoken
            step = .title
            return .respond("很好。您想给这个项目取什么名字？")
        case .title:
            draft.title = spoken
            step = .episodeCount
            if draft.creativeFormat == "commercial_campaign" {
                return .respond("这次先做几条成片版本？例如可以说“一条主片和两条短版，共三条”。")
            }
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
        case .creativeFormat: "您想做剧情化自传、真实资料纪录片、动画片，还是广告片？"
        case .premise: "请告诉我，这个故事主要讲什么？"
        case .title: "您想给这个项目取什么名字？"
        case .episodeCount:
            draft.creativeFormat == "commercial_campaign"
                ? "这次先做几条成片版本？"
                : "这个系列先计划做多少集？"
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
