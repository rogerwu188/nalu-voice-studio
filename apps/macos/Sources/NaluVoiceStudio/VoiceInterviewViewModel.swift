import Foundation
import Observation

@MainActor
@Observable
final class VoiceInterviewViewModel {
    var projects: [NaluProject] = []
    var selectedProjectID: String?
    var seasons: [NaluSeason] = []
    var episodes: [NaluEpisode] = []
    var selectedEpisodeID: String?
    var messages: [InterviewMessage] = [
        InterviewMessage(
            speaker: .nalu,
            text: "您好，我是 Nalu。我们可以从一段回忆、一个人物，或者一个故事想法开始。您想讲什么？"
        )
    ]
    var transcript = ""
    var transcriptConfidence: Float = 0
    var isListening = false
    var isInterviewPaused = false
    var runtimeStatus = "正在连接本地制片厂…"
    var errorMessage: String?

    private let runtime = RuntimeClient()
    private let speech = SpeechRecorder()
    private var projectDraft = ProjectDraft()
    private var interviewStep = InterviewStep.idle
    private var interviewHistory: [InterviewSnapshot] = []

    func load() async {
        do {
            let health = try await runtime.health()
            runtimeStatus = "本地制片厂已就绪 · \(health.version)"
            projects = try await runtime.listProjects()
            if let first = projects.first { await selectProject(first.id) }
        } catch {
            runtimeStatus = "本地制片厂尚未启动"
            errorMessage = error.localizedDescription
        }
    }

    func toggleListening() async {
        if isListening {
            speech.stop()
            isListening = false
            commitTranscript()
            return
        }
        guard await speech.requestAuthorization() else {
            errorMessage = "需要麦克风和语音识别权限，才能听您讲故事。"
            return
        }
        do {
            transcript = ""
            try speech.start { [weak self] text, confidence in
                self?.transcript = text
                self?.transcriptConfidence = confidence
            }
            isListening = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func commitTranscript() {
        let spoken = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !spoken.isEmpty else { return }
        if transcriptConfidence > 0 && transcriptConfidence < 0.2 {
            messages.append(
                .init(speaker: .nalu, text: "刚才这句话我没有听清楚。请慢一点，再说一次。")
            )
            transcript = ""
            transcriptConfidence = 0
            return
        }
        messages.append(InterviewMessage(speaker: .user, text: spoken))
        transcript = ""
        transcriptConfidence = 0
        if handleVoiceCommand(spoken) { return }
        advanceInterview(with: spoken)
    }

    func beginProject() {
        projectDraft = ProjectDraft()
        interviewStep = .premise
        interviewHistory = []
        isInterviewPaused = false
        messages = [
            InterviewMessage(
                speaker: .nalu,
                text: "我们慢慢来。请先告诉我，这个故事主要讲什么？可以是一段真实回忆，也可以是全新的故事。"
            )
        ]
    }

    func selectProject(_ projectID: String) async {
        selectedProjectID = projectID
        do {
            seasons = try await runtime.listSeasons(projectID: projectID)
            if let season = seasons.first {
                episodes = try await runtime.listEpisodes(seasonID: season.id)
                selectedEpisodeID = episodes.first?.id
            } else {
                episodes = []
                selectedEpisodeID = nil
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func advanceInterview(with answer: String) {
        if isInterviewPaused {
            messages.append(.init(speaker: .nalu, text: "采访还在暂停中。准备好后请说“继续”。"))
            return
        }
        interviewHistory.append(.init(step: interviewStep, draft: projectDraft))
        switch interviewStep {
        case .idle:
            messages.append(.init(speaker: .nalu, text: "我记下来了。需要建立新项目时，请点左侧的“创建新项目”。"))
        case .premise:
            projectDraft.description = answer
            interviewStep = .title
            messages.append(.init(speaker: .nalu, text: "很好。您想给这个系列取什么名字？"))
        case .title:
            projectDraft.title = answer
            interviewStep = .episodeCount
            messages.append(.init(speaker: .nalu, text: "这个系列先计划做多少集？您可以说，例如“十集”。"))
        case .episodeCount:
            projectDraft.plannedEpisodeCount = episodeCount(from: answer)
            interviewStep = .creating
            messages.append(.init(speaker: .nalu, text: "好的，我正在建立项目、第一季和分集计划。"))
            Task { await createInterviewedProject() }
        case .creating:
            messages.append(.init(speaker: .nalu, text: "项目正在建立，请稍等一下。"))
        }
    }

    private func createInterviewedProject() async {
        do {
            let plan = try await runtime.createProjectPlan(
                ProjectPlanDraft(project: projectDraft, seasonTitle: "第一季")
            )
            projects = try await runtime.listProjects()
            await selectProject(plan.project.id)
            interviewStep = .idle
            messages.append(
                .init(
                    speaker: .nalu,
                    text: "项目“\(plan.project.title)”已经建立，共 \(plan.episodes.count) 集。接下来我们逐集完善故事。"
                )
            )
        } catch {
            interviewStep = .episodeCount
            errorMessage = error.localizedDescription
        }
    }

    private func episodeCount(from answer: String) -> Int {
        let digits = answer.filter(\.isNumber)
        if let value = Int(digits) {
            return min(max(value, 1), 50)
        }
        let common = [("二十", 20), ("十二", 12), ("十", 10), ("九", 9), ("八", 8),
                      ("七", 7), ("六", 6), ("五", 5), ("四", 4), ("三", 3),
                      ("两", 2), ("二", 2), ("一", 1)]
        return common.first(where: { answer.contains($0.0) })?.1 ?? 6
    }

    func repeatCurrentQuestion() {
        messages.append(.init(speaker: .nalu, text: prompt(for: interviewStep)))
    }

    private func handleVoiceCommand(_ spoken: String) -> Bool {
        if spoken.contains("暂停") {
            isInterviewPaused = true
            messages.append(.init(speaker: .nalu, text: "好的，已经暂停。准备好后说“继续”就可以。"))
            return true
        }
        if spoken.contains("继续") && isInterviewPaused {
            isInterviewPaused = false
            messages.append(.init(speaker: .nalu, text: "我们继续。\(prompt(for: interviewStep))"))
            return true
        }
        if spoken.contains("再说一遍") || spoken.contains("重复问题") {
            repeatCurrentQuestion()
            return true
        }
        if spoken.contains("上一步") || spoken.contains("返回") || spoken.contains("重新说") {
            guard let previous = interviewHistory.popLast() else {
                messages.append(.init(speaker: .nalu, text: "现在已经是第一步了。"))
                return true
            }
            interviewStep = previous.step
            projectDraft = previous.draft
            isInterviewPaused = false
            messages.append(.init(speaker: .nalu, text: "好的，我们回到上一步。\(prompt(for: interviewStep))"))
            return true
        }
        return false
    }

    private func prompt(for step: InterviewStep) -> String {
        switch step {
        case .idle: "请点左侧的“创建新项目”，我们从头开始。"
        case .premise: "请告诉我，这个故事主要讲什么？"
        case .title: "您想给这个系列取什么名字？"
        case .episodeCount: "这个系列先计划做多少集？"
        case .creating: "项目正在建立，请稍等一下。"
        }
    }
}

private enum InterviewStep {
    case idle, premise, title, episodeCount, creating
}

private struct InterviewSnapshot {
    let step: InterviewStep
    let draft: ProjectDraft
}
