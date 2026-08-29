import Foundation
import Observation

@MainActor
@Observable
final class VoiceInterviewViewModel {
    var projects: [NaluProject] = []
    var selectedProjectID: String?
    var seasons: [NaluSeason] = []
    var episodes: [NaluEpisode] = []
    var episodeProgressByID: [String: EpisodeProductionProgress] = [:]
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
    var includeArchivedProjects = false
    var seasonPlanSummary = ""
    var episodeLogline = ""
    var episodeOutlineSummary = ""
    var guardianConfirmedForPlan = false
    var scriptRevisions: [ScriptRevision] = []
    var scriptContent = ""
    var scriptSummary = ""
    var viewedScriptRevision: Int?
    var guardianConfirmedForScript = false
    var planningVoiceLabel: String? { planningVoiceFlow.mode?.prompt }

    private let runtime = RuntimeClient()
    private let speech = SpeechRecorder()
    private let speechPlayback = SpeechPlayback()
    private var interviewFlow = InterviewFlow()
    private var planningVoiceFlow = PlanningVoiceFlow()

    func load() async {
        do {
            let health = try await runtime.health()
            runtimeStatus = "本地制片厂已就绪 · \(health.version)"
            projects = try await runtime.listProjects(includeArchived: includeArchivedProjects)
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
        if planningVoiceFlow.mode != nil {
            let guardianConfirmed = planningVoiceFlow.mode == .scriptApproval
                ? guardianConfirmedForScript : guardianConfirmedForPlan
            handle(
                planningVoiceFlow.consume(
                    spoken,
                    guardianRequired: selectedProject?.audienceMode == "child",
                    guardianConfirmed: guardianConfirmed
                )
            )
        } else {
            handle(interviewFlow.consume(spoken))
        }
    }

    func beginProject() {
        planningVoiceFlow = PlanningVoiceFlow()
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
                let progress = try await runtime.listEpisodeProgress(seasonID: season.id)
                episodeProgressByID = Dictionary(
                    uniqueKeysWithValues: progress.map { ($0.episodeID, $0) }
                )
                seasonPlanSummary = season.seasonArc["summary"]?.displayText ?? ""
                if let first = episodes.first {
                    selectEpisode(first.id)
                } else {
                    selectedEpisodeID = nil
                    episodeLogline = ""
                    episodeOutlineSummary = ""
                }
            } else {
                episodes = []
                episodeProgressByID = [:]
                selectedEpisodeID = nil
                scriptRevisions = []
                scriptContent = ""
                scriptSummary = ""
                viewedScriptRevision = nil
                seasonPlanSummary = ""
                episodeLogline = ""
                episodeOutlineSummary = ""
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectEpisode(_ episodeID: String) {
        selectedEpisodeID = episodeID
        guard let episode = episodes.first(where: { $0.id == episodeID }) else { return }
        episodeLogline = episode.logline
        episodeOutlineSummary = episode.outline["summary"]?.displayText ?? ""
        Task { await loadScripts(episodeID: episodeID) }
    }

    private func loadScripts(episodeID: String) async {
        do {
            let revisions = try await runtime.listScripts(episodeID: episodeID)
            guard selectedEpisodeID == episodeID else { return }
            scriptRevisions = revisions
            if let latest = revisions.last {
                viewedScriptRevision = latest.revision
                scriptContent = latest.content
                scriptSummary = latest.summaryForVoiceReview
            } else {
                viewedScriptRevision = nil
                scriptContent = ""
                scriptSummary = ""
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func viewScriptRevision(_ revision: Int) {
        guard let script = scriptRevisions.first(where: { $0.revision == revision }) else {
            return
        }
        viewedScriptRevision = revision
        scriptContent = script.content
        scriptSummary = script.summaryForVoiceReview
    }

    func saveSeasonPlan(sourceTranscript: String = "") async {
        guard let season = seasons.first else { return }
        do {
            _ = try await runtime.updateSeasonPlan(
                seasonID: season.id,
                summary: seasonPlanSummary,
                sourceTranscript: sourceTranscript
            )
            if let projectID = selectedProjectID { await selectProject(projectID) }
            if !sourceTranscript.isEmpty {
                messages.append(.init(speaker: .nalu, text: "新的季纲版本已经安全保存在本机。"))
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func approveSeasonPlanVisually() async {
        await approveSeasonPlan(
            confirmation: "我已查看并确认当前分集计划", reviewChannel: "visual"
        )
    }

    private func approveSeasonPlan(
        confirmation: String, reviewChannel: String
    ) async {
        guard let season = seasons.first else { return }
        do {
            _ = try await runtime.approveSeasonPlan(
                seasonID: season.id,
                confirmation: confirmation,
                reviewChannel: reviewChannel,
                guardianApproval: guardianConfirmedForPlan
            )
            if let projectID = selectedProjectID { await selectProject(projectID) }
            messages.append(.init(speaker: .nalu, text: "当前分集计划已经确认并记录。"))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveSelectedEpisodePlan(sourceTranscript: String = "") async {
        guard let selectedEpisodeID else { return }
        do {
            _ = try await runtime.updateEpisodePlan(
                episodeID: selectedEpisodeID,
                logline: episodeLogline,
                outlineSummary: episodeOutlineSummary,
                sourceTranscript: sourceTranscript
            )
            if let projectID = selectedProjectID {
                let episodeID = selectedEpisodeID
                await selectProject(projectID)
                if episodes.contains(where: { $0.id == episodeID }) { selectEpisode(episodeID) }
            }
            if !sourceTranscript.isEmpty {
                messages.append(.init(speaker: .nalu, text: "本集的新规划版本已经安全保存在本机。"))
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func beginSeasonPlanDictation() async {
        await beginPlanningVoice(.seasonPlan)
    }

    func beginEpisodePlanDictation() async {
        guard selectedEpisodeID != nil else { return }
        await beginPlanningVoice(.episodePlan)
    }

    func beginSeasonPlanVoiceApproval() async {
        await beginPlanningVoice(.seasonApproval)
    }

    func beginScriptDictation() async {
        guard selectedEpisodeID != nil else { return }
        await beginPlanningVoice(.scriptDraft)
    }

    func beginScriptVoiceApproval() async {
        guard !scriptRevisions.isEmpty else { return }
        await beginPlanningVoice(.scriptApproval)
    }

    private func beginPlanningVoice(_ mode: PlanningVoiceMode) async {
        let prompt = planningVoiceFlow.begin(mode)
        messages.append(.init(speaker: .nalu, text: prompt))
        if !isListening { await toggleListening() }
    }

    func saveScriptRevision(sourceTranscript: String = "") async {
        guard let episodeID = selectedEpisodeID else { return }
        let content = scriptContent.trimmingCharacters(in: .whitespacesAndNewlines)
        let summary = scriptSummary.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty, !summary.isEmpty else {
            errorMessage = "请先填写剧本和朗读摘要。"
            return
        }
        do {
            _ = try await runtime.createScript(
                episodeID: episodeID,
                content: content,
                summary: summary,
                sourceTranscript: sourceTranscript
            )
            await loadScripts(episodeID: episodeID)
            if let projectID = selectedProjectID { await selectProject(projectID) }
            if episodes.contains(where: { $0.id == episodeID }) { selectEpisode(episodeID) }
            messages.append(.init(speaker: .nalu, text: "新的剧本版本已经保存在本机，旧版本仍然保留。"))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func approveScriptVisually() async {
        await approveCurrentScript(
            confirmation: "我已查看并确认当前剧本"
        )
    }

    private func approveCurrentScript(confirmation: String) async {
        guard let episodeID = selectedEpisodeID, let latest = scriptRevisions.last else { return }
        do {
            _ = try await runtime.approveScript(
                episodeID: episodeID,
                revision: latest.revision,
                confirmation: confirmation,
                guardianApproval: guardianConfirmedForScript
            )
            await loadScripts(episodeID: episodeID)
            if let projectID = selectedProjectID { await selectProject(projectID) }
            if episodes.contains(where: { $0.id == episodeID }) { selectEpisode(episodeID) }
            messages.append(.init(speaker: .nalu, text: "当前剧本版本已经确认，可以进入制作准备。"))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func revokeCurrentScriptApproval() async {
        guard let episodeID = selectedEpisodeID,
              let approved = scriptRevisions.last(where: { $0.approvedAt != nil }) else { return }
        do {
            _ = try await runtime.revokeScript(
                episodeID: episodeID, revision: approved.revision
            )
            await loadScripts(episodeID: episodeID)
            if let projectID = selectedProjectID { await selectProject(projectID) }
            if episodes.contains(where: { $0.id == episodeID }) { selectEpisode(episodeID) }
            messages.append(.init(speaker: .nalu, text: "批准已撤销。这一集不会进入生产，可以继续修改。"))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func speakCurrentScriptSummary() {
        speechPlayback.speak(scriptSummary)
    }

    func reloadProjects() async {
        do {
            projects = try await runtime.listProjects(includeArchived: includeArchivedProjects)
            if let selectedProjectID,
               projects.contains(where: { $0.id == selectedProjectID }) {
                await selectProject(selectedProjectID)
            } else if let first = projects.first {
                await selectProject(first.id)
            } else {
                selectedProjectID = nil
                seasons = []
                episodes = []
                episodeProgressByID = [:]
                selectedEpisodeID = nil
                scriptRevisions = []
                scriptContent = ""
                scriptSummary = ""
                viewedScriptRevision = nil
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func renameSelectedProject(to title: String) async {
        guard let selectedProjectID else { return }
        let cleaned = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        do {
            _ = try await runtime.renameProject(id: selectedProjectID, title: cleaned)
            await reloadProjects()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func setSelectedProjectArchived(_ archived: Bool) async {
        guard let selectedProjectID else { return }
        do {
            _ = try await runtime.archiveProject(id: selectedProjectID, archived: archived)
            await reloadProjects()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func exportSelectedProject() async -> Data? {
        guard let selectedProjectID else { return nil }
        do {
            return try await runtime.exportProject(id: selectedProjectID)
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func restoreProject(from data: Data) async {
        do {
            let project = try await runtime.restoreProject(data: data)
            includeArchivedProjects = project.archivedAt != nil
            await reloadProjects()
            await selectProject(project.id)
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

    private func handle(_ action: PlanningVoiceAction) {
        switch action {
        case .updateSeason(let summary, let sourceTranscript):
            seasonPlanSummary = summary
            messages.append(.init(speaker: .nalu, text: "好的，我记下了，正在保存新的季纲版本。"))
            Task { await saveSeasonPlan(sourceTranscript: sourceTranscript) }
        case .updateEpisode(let summary, let sourceTranscript):
            episodeOutlineSummary = summary
            if episodeLogline.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                episodeLogline = summary
            }
            messages.append(.init(speaker: .nalu, text: "好的，我记下了，正在保存本集的新规划。"))
            Task { await saveSelectedEpisodePlan(sourceTranscript: sourceTranscript) }
        case .approveSeason(let confirmation):
            messages.append(.init(speaker: .nalu, text: "我听到了明确确认，正在记录当前分集计划。"))
            Task {
                await approveSeasonPlan(
                    confirmation: confirmation, reviewChannel: "voice"
                )
            }
        case .updateScript(let content, let sourceTranscript):
            scriptContent = content
            scriptSummary = String(content.prefix(120))
            messages.append(.init(speaker: .nalu, text: "我记下了，正在保存为新的剧本版本。"))
            Task { await saveScriptRevision(sourceTranscript: sourceTranscript) }
        case .approveScript(let confirmation):
            messages.append(.init(speaker: .nalu, text: "我听到了明确确认，正在记录剧本批准。"))
            Task { await approveCurrentScript(confirmation: confirmation) }
        case .respond(let message):
            messages.append(.init(speaker: .nalu, text: message))
        }
    }

    private func createInterviewedProject(_ draft: ProjectDraft) async {
        do {
            let plan = try await runtime.createProjectPlan(
                ProjectPlanDraft(project: draft, seasonTitle: "第一季")
            )
            projects = try await runtime.listProjects(includeArchived: includeArchivedProjects)
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
        messages.append(
            .init(speaker: .nalu, text: planningVoiceFlow.mode?.prompt ?? interviewFlow.prompt)
        )
    }

    private var selectedProject: NaluProject? {
        projects.first { $0.id == selectedProjectID }
    }
}
