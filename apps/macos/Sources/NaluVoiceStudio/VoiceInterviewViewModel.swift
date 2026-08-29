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
    var isListening = false
    var runtimeStatus = "正在连接本地制片厂…"
    var errorMessage: String?

    private let runtime = RuntimeClient()
    private let speech = SpeechRecorder()
    private var projectDraft = ProjectDraft()
    private var interviewStep = InterviewStep.idle

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
            try speech.start { [weak self] text in self?.transcript = text }
            isListening = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func commitTranscript() {
        let spoken = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !spoken.isEmpty else { return }
        messages.append(InterviewMessage(speaker: .user, text: spoken))
        transcript = ""
        advanceInterview(with: spoken)
    }

    func beginProject() {
        projectDraft = ProjectDraft()
        interviewStep = .premise
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
        if let value = answer.firstMatch(of: /\d+/).flatMap({ Int($0.output) }) {
            return min(max(value, 1), 50)
        }
        let common = ["一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
                      "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
                      "十二": 12, "二十": 20]
        return common.first(where: { answer.contains($0.key) })?.value ?? 6
    }
}

private enum InterviewStep {
    case idle, premise, title, episodeCount, creating
}
