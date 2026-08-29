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
    var isInterviewPaused: Bool { interviewFlow.isPaused }
    var runtimeStatus = "正在连接本地制片厂…"
    var errorMessage: String?

    private let runtime = RuntimeClient()
    private let speech = SpeechRecorder()
    private var interviewFlow = InterviewFlow()

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
        handle(interviewFlow.consume(spoken))
    }

    func beginProject() {
        messages = [
            InterviewMessage(
                speaker: .nalu,
                text: interviewFlow.begin()
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

    private func handle(_ action: InterviewFlowAction) {
        switch action {
        case .respond(let message):
            messages.append(.init(speaker: .nalu, text: message))
        case .create(let draft, let message):
            messages.append(.init(speaker: .nalu, text: message))
            Task { await createInterviewedProject(draft) }
        }
    }

    private func createInterviewedProject(_ draft: ProjectDraft) async {
        do {
            let plan = try await runtime.createProjectPlan(
                ProjectPlanDraft(project: draft, seasonTitle: "第一季")
            )
            projects = try await runtime.listProjects()
            await selectProject(plan.project.id)
            interviewFlow.creationSucceeded()
            messages.append(
                .init(
                    speaker: .nalu,
                    text: "项目“\(plan.project.title)”已经建立，共 \(plan.episodes.count) 集。接下来我们逐集完善故事。"
                )
            )
        } catch {
            interviewFlow.creationFailed()
            errorMessage = error.localizedDescription
        }
    }

    func repeatCurrentQuestion() {
        messages.append(.init(speaker: .nalu, text: interviewFlow.prompt))
    }
}
