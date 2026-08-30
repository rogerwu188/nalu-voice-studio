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
    var inheritedContinuity: ContinuitySnapshot?
    var continuitySnapshots: [ContinuitySnapshot] = []
    var openingContinuityDraft = ContinuityFormDraft()
    var endingContinuityDraft = ContinuityFormDraft()
    var continuityPreflightResult: ContinuityPreflightResult?
    var continuityTransitionExplanation = ""
    var continuityOverrideReason = ""
    var continuityOverrideConfirmation = ""
    var continuityStatus = "尚未检查跨集连续性"
    var assets: [NaluAsset] = []
    var memoryCards: [MemoryCard] = []
    var documentaryReadiness: DocumentaryReadinessReport?
    var reviewedMemoryCardIDs: Set<String> = []
    var memoryCorrectionCardID: String?
    var memoryConfirmationCardID: String?
    var draftProjectID: String?
    var feedbackDraftText = ""
    var isCapturingFeedback = false
    var feedbackWasDictated = false
    var comfortPreferences = VoiceInterviewViewModel.loadComfortPreferences()
    var planningVoiceLabel: String? { planningVoiceFlow.mode?.prompt }

    private let runtime = RuntimeClient()
    private let speech = SpeechRecorder()
    private let speechPlayback = SpeechPlayback()
    private var interviewFlow = InterviewFlow()
    private var planningVoiceFlow = PlanningVoiceFlow()
    private var acceptedContinuityDraft: ContinuityPreflightDraft?

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
        if applyComfortCommand(spoken) { return }
        if let memoryConfirmationCardID {
            self.memoryConfirmationCardID = nil
            guard spoken.contains("确认") && spoken.contains("归档") else {
                let response = "我没有听到明确的“确认归档”，所以没有归档。您可以重新朗读后再确认。"
                messages.append(.init(speaker: .nalu, text: response))
                speechPlayback.speak(response, rate: comfortPreferences.speechRate)
                return
            }
            Task { await confirmMemoryCard(memoryConfirmationCardID) }
            return
        }
        if let memoryCorrectionCardID {
            self.memoryCorrectionCardID = nil
            handleMemoryCorrection(spoken, memoryID: memoryCorrectionCardID)
            return
        }
        if isCapturingFeedback {
            feedbackDraftText = spoken
            feedbackWasDictated = true
            isCapturingFeedback = false
            messages.append(
                .init(
                    speaker: .nalu,
                    text: "谢谢，我已经把这条意见放进本机反馈草稿。保存前您还可以修改。"
                )
            )
            return
        }
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
            let action = interviewFlow.consume(spoken)
            handle(action)
            if interviewFlow.step == .episodeCount,
               !interviewFlow.draft.title.isEmpty {
                Task { await renameDraftProjectDuringInterview() }
            }
        }
    }

    func beginProject() async {
        planningVoiceFlow = PlanningVoiceFlow()
        messages = [
            InterviewMessage(
                speaker: .nalu,
                text: interviewFlow.begin()
            )
        ]
        if let draftProjectID,
           projects.contains(where: { $0.id == draftProjectID }) {
            await selectProject(draftProjectID)
            return
        }
        do {
            var draft = ProjectDraft()
            draft.title = "未命名故事"
            draft.description = "语音采访进行中"
            draft.projectBible["draft_state"] = "voice_interview"
            let project = try await runtime.createProject(draft)
            draftProjectID = project.id
            projects = try await runtime.listProjects(includeArchived: includeArchivedProjects)
            await selectProject(project.id)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func beginFeedbackDictation() async {
        isCapturingFeedback = true
        feedbackWasDictated = false
        messages.append(
            .init(
                speaker: .nalu,
                text: "请告诉我哪里不好用、哪里出错，或者您希望增加什么。我会先记在本机。"
            )
        )
        if !isListening { await toggleListening() }
    }

    func saveFeedback(
        category: String, shareAuthorized: Bool, guardianApproval: Bool
    ) async -> Bool {
        let cleaned = feedbackDraftText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else {
            errorMessage = "请先说出或写下您的意见。"
            return false
        }
        do {
            let saved = try await runtime.createFeedback(
                FeedbackDraft(
                    projectID: selectedProjectID,
                    category: category,
                    message: cleaned,
                    source: feedbackWasDictated ? "voice" : "text",
                    screen: "interview",
                    shareAuthorized: shareAuthorized,
                    guardianApproval: guardianApproval
                )
            )
            feedbackDraftText = ""
            feedbackWasDictated = false
            messages.append(
                .init(
                    speaker: .nalu,
                    text: saved.status == "ready_for_review"
                        ? "意见已脱敏并进入待审核改进队列。任何程序改动仍需测试和审核。"
                        : "意见只保存在这台 Mac 上，不会自动上传。"
                )
            )
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func selectProject(_ projectID: String) async {
        selectedProjectID = projectID
        do {
            assets = try await runtime.listAssets(projectID: projectID)
            memoryCards = try await runtime.listMemoryCards(projectID: projectID)
            if selectedProject?.creativeFormat == "documentary_series" {
                documentaryReadiness = try await runtime.documentaryReadiness(
                    projectID: projectID
                )
            } else {
                documentaryReadiness = nil
            }
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
        Task { await loadContinuity(episodeID: episodeID) }
    }

    private func loadContinuity(episodeID: String) async {
        do {
            async let snapshotsRequest = runtime.listContinuitySnapshots(episodeID: episodeID)
            async let inheritedRequest = runtime.inheritedContinuity(episodeID: episodeID)
            let (snapshots, inheritedResult) = try await (snapshotsRequest, inheritedRequest)
            guard selectedEpisodeID == episodeID else { return }
            continuitySnapshots = snapshots
            inheritedContinuity = inheritedResult.snapshot
            endingContinuityDraft = snapshots.last.map(ContinuityFormDraft.init(snapshot:))
                ?? ContinuityFormDraft()
            openingContinuityDraft = inheritedResult.snapshot.map(
                ContinuityFormDraft.init(snapshot:)
            ) ?? ContinuityFormDraft()
            continuityPreflightResult = nil
            acceptedContinuityDraft = nil
            continuityTransitionExplanation = ""
            continuityOverrideReason = ""
            continuityOverrideConfirmation = ""
            continuityStatus = inheritedResult.snapshot == nil
                ? "这是本季第一集，没有上一集交接卡"
                : "已带入上一集交接卡，请核对本集开场"
        } catch {
            errorMessage = error.localizedDescription
        }
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

    func beginSeasonPlanDictation(startLocalCapture: Bool = true) async {
        await beginPlanningVoice(.seasonPlan, startLocalCapture: startLocalCapture)
    }

    func beginEpisodePlanDictation(startLocalCapture: Bool = true) async {
        guard selectedEpisodeID != nil else { return }
        await beginPlanningVoice(.episodePlan, startLocalCapture: startLocalCapture)
    }

    func beginSeasonPlanVoiceApproval(startLocalCapture: Bool = true) async {
        await beginPlanningVoice(.seasonApproval, startLocalCapture: startLocalCapture)
    }

    func beginScriptDictation(startLocalCapture: Bool = true) async {
        guard selectedEpisodeID != nil else { return }
        await beginPlanningVoice(.scriptDraft, startLocalCapture: startLocalCapture)
    }

    func beginScriptVoiceApproval(startLocalCapture: Bool = true) async {
        guard !scriptRevisions.isEmpty else { return }
        await beginPlanningVoice(.scriptApproval, startLocalCapture: startLocalCapture)
    }

    private func beginPlanningVoice(
        _ mode: PlanningVoiceMode, startLocalCapture: Bool
    ) async {
        let prompt = planningVoiceFlow.begin(mode)
        messages.append(.init(speaker: .nalu, text: prompt))
        if startLocalCapture, !isListening { await toggleListening() }
    }

    func saveScriptRevision(sourceTranscript: String = "") async {
        guard let episodeID = selectedEpisodeID else { return }
        let content = scriptContent.trimmingCharacters(in: .whitespacesAndNewlines)
        let summary = scriptSummary.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty, !summary.isEmpty else {
            errorMessage = "请先填写剧本和朗读摘要。"
            return
        }
        var narrativeMetadata: [String: JSONValue] = [:]
        if inheritedContinuity != nil {
            guard let acceptedContinuityDraft,
                  continuityPreflightResult?.canProceed == true,
                  acceptedContinuityDraft.openingState == openingContinuityDraft.state else {
                errorMessage = "请先检查本集开场连续性；修改开场后需要重新检查。"
                return
            }
            narrativeMetadata["opening_continuity"] = acceptedContinuityDraft.openingState.jsonValue
            narrativeMetadata["continuity_transition_explanations"] = .object(
                acceptedContinuityDraft.transitionExplanations.mapValues(JSONValue.string)
            )
            if let override = acceptedContinuityDraft.override {
                narrativeMetadata["continuity_override"] = .object([
                    "schema_version": .string(override.schemaVersion),
                    "conflict_paths": .array(override.conflictPaths.map(JSONValue.string)),
                    "reason": .string(override.reason),
                    "reviewed_by": .string(override.reviewedBy),
                    "spoken_confirmation": .string(override.spokenConfirmation),
                ])
            }
        }
        do {
            _ = try await runtime.createScript(
                episodeID: episodeID,
                content: content,
                summary: summary,
                sourceTranscript: sourceTranscript,
                narrativeMetadata: narrativeMetadata
            )
            await loadScripts(episodeID: episodeID)
            if let projectID = selectedProjectID { await selectProject(projectID) }
            if episodes.contains(where: { $0.id == episodeID }) { selectEpisode(episodeID) }
            messages.append(.init(speaker: .nalu, text: "新的剧本版本已经保存在本机，旧版本仍然保留。"))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveEndingContinuity() async {
        guard let episodeID = selectedEpisodeID else { return }
        guard endingContinuityDraft.hasContent else {
            errorMessage = "请至少填写人物、道具、地点、时间天气或一个未解悬念。"
            return
        }
        do {
            _ = try await runtime.createContinuitySnapshot(
                episodeID: episodeID,
                draft: ContinuitySnapshotDraft(
                    sourceEpisodeID: nil,
                    state: endingContinuityDraft.state,
                    unresolvedHooks: endingContinuityDraft.hooks
                )
            )
            await loadContinuity(episodeID: episodeID)
            messages.append(
                .init(speaker: .nalu, text: "本集结尾交接卡已经保存。后续修改会建立新快照，不会改写旧记录。")
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func checkOpeningContinuity(
        applyExplanation: Bool = false, applyOverride: Bool = false
    ) async {
        guard let episodeID = selectedEpisodeID else { return }
        let currentPaths = continuityPreflightResult?.conflicts.map(\.path) ?? []
        let explanation = continuityTransitionExplanation.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        let explanations = applyExplanation && !explanation.isEmpty
            ? Dictionary(uniqueKeysWithValues: currentPaths.map { ($0, explanation) }) : [:]
        var override: ContinuityOverrideDraft?
        if applyOverride {
            let reason = continuityOverrideReason.trimmingCharacters(in: .whitespacesAndNewlines)
            let confirmation = continuityOverrideConfirmation.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            guard !currentPaths.isEmpty, !reason.isEmpty,
                  confirmation.contains("我确认") || confirmation.contains("我同意") else {
                errorMessage = "强制覆盖需要填写原因，并明确输入“我确认”或“我同意”。"
                return
            }
            override = ContinuityOverrideDraft(
                conflictPaths: currentPaths,
                reason: reason,
                reviewedBy: "local-user",
                spokenConfirmation: confirmation
            )
        }
        let draft = ContinuityPreflightDraft(
            openingState: openingContinuityDraft.state,
            transitionExplanations: explanations,
            override: override
        )
        do {
            let result = try await runtime.continuityPreflight(
                episodeID: episodeID, draft: draft
            )
            continuityPreflightResult = result
            if result.canProceed {
                acceptedContinuityDraft = draft
                continuityStatus = result.conflicts.isEmpty
                    ? "开场与上一集一致，可以保存剧本"
                    : "所有变化已说明并记录，可以保存剧本"
            } else {
                acceptedContinuityDraft = nil
                continuityStatus = "发现 \(result.conflicts.count) 处变化，请逐项核对"
            }
        } catch {
            acceptedContinuityDraft = nil
            errorMessage = error.localizedDescription
        }
    }

    func speakOpeningContinuity() {
        speechPlayback.speak(
            continuitySpeechSummary(openingContinuityDraft, prefix: "本集开场"),
            rate: comfortPreferences.speechRate
        )
    }

    func speakEndingContinuity() {
        speechPlayback.speak(
            continuitySpeechSummary(endingContinuityDraft, prefix: "本集结尾"),
            rate: comfortPreferences.speechRate
        )
    }

    private func continuitySpeechSummary(
        _ draft: ContinuityFormDraft, prefix: String
    ) -> String {
        var parts = [prefix]
        if !draft.sceneLocation.isEmpty { parts.append("场景在 \(draft.sceneLocation)") }
        if !draft.storyTime.isEmpty { parts.append("时间是 \(draft.storyTime)") }
        if !draft.weather.isEmpty { parts.append("天气是 \(draft.weather)") }
        for character in draft.characters where !character.name.isEmpty {
            var detail = character.name
            if !character.location.isEmpty { detail += "在 \(character.location)" }
            if !character.wardrobe.isEmpty { detail += "，穿着 \(character.wardrobe)" }
            if !character.injuries.isEmpty { detail += "，伤势是 \(character.injuries)" }
            parts.append(detail)
        }
        for prop in draft.props where !prop.name.isEmpty {
            var detail = "道具 \(prop.name)"
            if !prop.owner.isEmpty { detail += "属于 \(prop.owner)" }
            if !prop.location.isEmpty { detail += "，在 \(prop.location)" }
            parts.append(detail)
        }
        if !draft.unresolvedHooks.isEmpty { parts.append("未解悬念：\(draft.unresolvedHooks)") }
        return parts.joined(separator: "。") + "。"
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
        speechPlayback.speak(scriptSummary, rate: comfortPreferences.speechRate)
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
                assets = []
                memoryCards = []
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

    func importAsset(
        data: Data,
        filename: String,
        contentType: String,
        kind: String,
        name: String,
        subjectName: String,
        scope: String,
        consentGranted: Bool,
        guardianApproved: Bool,
        consentStatement: String,
        memoryDescription: String,
        memoryDate: String,
        memoryPlace: String,
        memoryRelationship: String,
        memoryStoryRelevance: String,
        memoryAllowedUse: String,
        recognizedText: String
    ) async {
        guard let projectID = selectedProjectID else { return }
        do {
            let asset = try await runtime.importAsset(
                projectID: projectID,
                data: data,
                filename: filename,
                contentType: contentType,
                kind: kind,
                name: name,
                subjectName: subjectName,
                seasonID: scope == "season" ? seasons.first?.id : nil,
                episodeID: scope == "episode" ? selectedEpisodeID : nil,
                consentGranted: consentGranted,
                guardianApproved: guardianApproved,
                consentStatement: consentStatement
            )
            let people = subjectName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                ? []
                : [
                    MemoryPersonDraft(
                        name: subjectName,
                        relationship: memoryRelationship,
                        note: "用户在导入素材时提供"
                    )
                ]
            _ = try await runtime.createMemoryCard(
                projectID: projectID,
                draft: MemoryCardDraft(
                    assetID: asset.id,
                    title: name,
                    description: memoryDescription,
                    ocrText: recognizedText,
                    spokenContext: memoryDescription,
                    approximateDate: memoryDate,
                    place: memoryPlace,
                    people: people,
                    storyRelevance: memoryStoryRelevance,
                    allowedUse: memoryAllowedUse
                )
            )
            assets = try await runtime.listAssets(projectID: projectID)
            memoryCards = try await runtime.listMemoryCards(projectID: projectID)
            await refreshDocumentaryReadiness()
            messages.append(
                .init(
                    speaker: .nalu,
                    text: "素材已复制到本机，并建立了一张待确认的记忆卡。请先听我复述，再确认归档。"
                )
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func speakMemoryCard(_ memoryID: String) {
        guard let card = memoryCards.first(where: { $0.id == memoryID }) else { return }
        let summary = memoryCardReadback(card)
        messages.append(.init(speaker: .nalu, text: summary))
        speechPlayback.speak(summary, rate: comfortPreferences.speechRate)
        reviewedMemoryCardIDs.insert(memoryID)
    }

    func beginMemoryCorrection(_ memoryID: String) async {
        memoryCorrectionCardID = memoryID
        memoryConfirmationCardID = nil
        let response = "请说要修改哪一项，例如：地点不是西湖，是灵隐寺；或者年份改成一九八零年。"
        messages.append(.init(speaker: .nalu, text: response))
        speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        if !isListening { await toggleListening() }
    }

    func beginMemoryVoiceConfirmation(_ memoryID: String) async {
        guard reviewedMemoryCardIDs.contains(memoryID) else {
            speakMemoryCard(memoryID)
            return
        }
        memoryConfirmationCardID = memoryID
        memoryCorrectionCardID = nil
        let response = "内容正确时，请明确说：我确认这张记忆卡并归档。"
        messages.append(.init(speaker: .nalu, text: response))
        speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        if !isListening { await toggleListening() }
    }

    func confirmMemoryCard(_ memoryID: String) async {
        guard let projectID = selectedProjectID else { return }
        guard reviewedMemoryCardIDs.contains(memoryID) else {
            let response = "请先按朗读，听完当前内容，再确认归档。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
            return
        }
        guard let card = memoryCards.first(where: { $0.id == memoryID }) else { return }
        do {
            _ = try await runtime.confirmMemoryCard(id: memoryID, revision: card.currentRevision)
            memoryCards = try await runtime.listMemoryCards(projectID: projectID)
            await refreshDocumentaryReadiness()
            reviewedMemoryCardIDs.remove(memoryID)
            let response = "这张记忆卡已经由您确认归档，可以作为剧本事实来源。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func updateMemoryCard(
        id: String,
        title: String,
        description: String,
        approximateDate: String,
        place: String,
        storyRelevance: String,
        allowedUse: String,
        sourceChannel: String = "visual",
        changeSummary: String = "用户在本机修改记忆卡"
    ) async -> Bool {
        guard let projectID = selectedProjectID else { return false }
        do {
            _ = try await runtime.updateMemoryCard(
                id: id,
                draft: MemoryCardUpdateDraft(
                    title: title,
                    description: description,
                    approximateDate: approximateDate,
                    place: place,
                    storyRelevance: storyRelevance,
                    allowedUse: allowedUse,
                    sourceChannel: sourceChannel,
                    changeSummary: changeSummary
                )
            )
            memoryCards = try await runtime.listMemoryCards(projectID: projectID)
            await refreshDocumentaryReadiness()
            reviewedMemoryCardIDs.remove(id)
            let response = "修改已保存为新版本。请重新听我朗读，再确认归档。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func speakDocumentaryReadiness() {
        guard let documentaryReadiness else { return }
        let summary = documentaryReadiness.spokenSummary
        messages.append(.init(speaker: .nalu, text: summary))
        speechPlayback.speak(summary, rate: comfortPreferences.speechRate)
    }

    private func refreshDocumentaryReadiness() async {
        guard let projectID = selectedProjectID,
              selectedProject?.creativeFormat == "documentary_series" else {
            documentaryReadiness = nil
            return
        }
        do {
            documentaryReadiness = try await runtime.documentaryReadiness(
                projectID: projectID
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func handleMemoryCorrection(_ spoken: String, memoryID: String) {
        guard let card = memoryCards.first(where: { $0.id == memoryID }),
              let correction = MemoryCorrectionParser.parse(spoken) else {
            let response = "我还不能确定要改哪一项，所以没有修改。请说“地点改成……”或“年份改成……”。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
            return
        }
        var title = card.title
        var description = card.description
        var date = card.approximateDate
        var place = card.place
        var relevance = card.storyRelevance
        switch correction.field {
        case .title: title = correction.value
        case .description: description = correction.value
        case .approximateDate: date = correction.value
        case .place: place = correction.value
        case .storyRelevance: relevance = correction.value
        }
        Task {
            _ = await updateMemoryCard(
                id: memoryID,
                title: title,
                description: description,
                approximateDate: date,
                place: place,
                storyRelevance: relevance,
                allowedUse: card.allowedUse,
                sourceChannel: "voice",
                changeSummary: spoken
            )
        }
    }

    private func memoryCardReadback(_ card: MemoryCard) -> String {
        var details = ["这张记忆卡的标题是：\(card.title)。"]
        if !card.approximateDate.isEmpty {
            details.append("时间是：\(card.approximateDate)。")
        }
        if !card.place.isEmpty { details.append("地点是：\(card.place)。") }
        if !card.people.isEmpty {
            let people = card.people.map {
                $0.relationship.isEmpty ? $0.name : "\($0.name)，关系是\($0.relationship)"
            }.joined(separator: "；")
            details.append("相关人物有：\(people)。")
        }
        if !card.description.isEmpty { details.append("您的说明是：\(card.description)。") }
        if !card.ocrText.isEmpty { details.append("手写或图片文字识别为：\(card.ocrText)。") }
        details.append(
            card.confirmationStatus == "confirmed"
                ? "这张卡已经确认归档。"
                : "这张卡还没有归档。内容正确时，请按确认归档；不正确时先修改。"
        )
        return details.joined(separator: " ")
    }

    func revokeAssetConsent(_ assetID: String) async {
        guard let projectID = selectedProjectID else { return }
        do {
            _ = try await runtime.revokeAssetConsent(assetID: assetID)
            assets = try await runtime.listAssets(projectID: projectID)
            await refreshDocumentaryReadiness()
            messages.append(.init(speaker: .nalu, text: "素材授权已撤销，后续生产将拒绝使用。"))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func exportPrivacyBundle() async -> Data? {
        guard let projectID = selectedProjectID else { return nil }
        do {
            return try await runtime.privacyExport(projectID: projectID)
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func assetDependencies(_ assetID: String) async -> AssetDependencyReport? {
        do {
            return try await runtime.assetDependencies(assetID: assetID)
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func deleteAsset(_ assetID: String) async {
        guard let projectID = selectedProjectID else { return }
        do {
            try await runtime.deleteAsset(assetID: assetID)
            assets = try await runtime.listAssets(projectID: projectID)
            memoryCards = try await runtime.listMemoryCards(projectID: projectID)
            await refreshDocumentaryReadiness()
            messages.append(.init(speaker: .nalu, text: "本地素材和素材记录已经删除。"))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectedProjectDeletionPreview() async -> ProjectDeletionPreview? {
        guard let projectID = selectedProjectID else { return nil }
        do {
            return try await runtime.projectDeletionPreview(projectID: projectID)
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func deleteSelectedProject(
        confirmationTitle: String, deleteProductionSnapshots: Bool
    ) async -> ProjectDeletionResult? {
        guard let projectID = selectedProjectID else { return nil }
        do {
            let result = try await runtime.deleteProject(
                projectID: projectID,
                confirmationTitle: confirmationTitle,
                deleteProductionSnapshots: deleteProductionSnapshots
            )
            guard result.deleted, result.verifiedAbsent else {
                errorMessage = "本地制片厂没有确认项目已完整删除。"
                return nil
            }
            selectedProjectID = nil
            await reloadProjects()
            messages.append(
                .init(
                    speaker: .nalu,
                    text: "项目、\(result.removedAssetCount) 个素材和 \(result.removedProductionRunCount) 个制作快照已从本机删除。"
                )
            )
            return result
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    private func handle(_ action: InterviewFlowAction) {
        switch action {
        case .respond(let message):
            messages.append(.init(speaker: .nalu, text: message))
            speechPlayback.speak(message, rate: comfortPreferences.speechRate)
        case .create(let draft, let message):
            messages.append(.init(speaker: .nalu, text: message))
            speechPlayback.speak(message, rate: comfortPreferences.speechRate)
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
                ProjectPlanDraft(
                    project: draft,
                    seasonTitle: "第一季",
                    projectID: draftProjectID
                )
            )
            draftProjectID = nil
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

    private func renameDraftProjectDuringInterview() async {
        guard let draftProjectID else { return }
        do {
            _ = try await runtime.renameProject(
                id: draftProjectID, title: interviewFlow.draft.title
            )
            projects = try await runtime.listProjects(includeArchived: includeArchivedProjects)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func repeatCurrentQuestion() {
        let prompt = planningVoiceFlow.mode?.prompt ?? interviewFlow.prompt
        messages.append(.init(speaker: .nalu, text: prompt))
        speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
    }

    func receiveRealtimeTranscript(_ text: String, from speaker: InterviewMessage.Speaker) {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        messages.append(.init(speaker: speaker, text: cleaned))
    }

    func recordRealtimeFlowAnswer(_ answer: String) -> RealtimeInterviewToolResult {
        if planningVoiceFlow.mode != nil {
            return recordRealtimePlanningAnswer(answer)
        }
        let action = interviewFlow.consume(answer)
        switch action {
        case .respond(let message):
            // Realtime will speak the returned message. Avoid a second local TTS voice.
            if interviewFlow.step == .episodeCount,
               !interviewFlow.draft.title.isEmpty {
                Task { await renameDraftProjectDuringInterview() }
            }
            return RealtimeInterviewToolResult(
                accepted: true,
                message: message,
                nextPrompt: interviewFlow.prompt,
                requiresVisibleConfirmation: false
            )
        case .create(let draft, let message):
            messages.append(.init(speaker: .nalu, text: message))
            Task { await createInterviewedProject(draft) }
            return RealtimeInterviewToolResult(
                accepted: true,
                message: message,
                nextPrompt: "项目建立后，请继续逐集完善故事。",
                requiresVisibleConfirmation: false
            )
        }
    }

    private func recordRealtimePlanningAnswer(_ answer: String) -> RealtimeInterviewToolResult {
        let guardianConfirmed = planningVoiceFlow.mode == .scriptApproval
            ? guardianConfirmedForScript : guardianConfirmedForPlan
        let action = planningVoiceFlow.consume(
            answer,
            guardianRequired: selectedProject?.audienceMode == "child",
            guardianConfirmed: guardianConfirmed
        )
        switch action {
        case .updateSeason(let summary, let transcript):
            seasonPlanSummary = summary
            Task { await saveSeasonPlan(sourceTranscript: transcript) }
            return .init(
                accepted: true,
                message: "新的季纲版本正在保存，旧版本不会被覆盖。",
                nextPrompt: "您还想修改哪一集？",
                requiresVisibleConfirmation: false
            )
        case .updateEpisode(let summary, let transcript):
            episodeOutlineSummary = summary
            if episodeLogline.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                episodeLogline = summary
            }
            Task { await saveSelectedEpisodePlan(sourceTranscript: transcript) }
            return .init(
                accepted: true,
                message: "本集的新规划版本正在保存。",
                nextPrompt: "您还想补充这一集的什么内容？",
                requiresVisibleConfirmation: false
            )
        case .updateScript(let content, let transcript):
            scriptContent = content
            scriptSummary = String(content.prefix(120))
            Task { await saveScriptRevision(sourceTranscript: transcript) }
            return .init(
                accepted: true,
                message: "新的剧本版本正在保存，旧版本仍然保留。",
                nextPrompt: "您还想修改这版剧本的哪里？",
                requiresVisibleConfirmation: false
            )
        case .approveSeason(let confirmation):
            Task {
                await approveSeasonPlan(
                    confirmation: confirmation, reviewChannel: "voice_realtime"
                )
            }
            return .init(
                accepted: true,
                message: "已收到明确确认，正在提交当前分集计划批准；最终以界面状态为准。",
                nextPrompt: "接下来要继续修改哪一集？",
                requiresVisibleConfirmation: false
            )
        case .approveScript(let confirmation):
            Task { await approveCurrentScript(confirmation: confirmation) }
            return .init(
                accepted: true,
                message: "已收到明确确认，正在提交当前剧本批准；最终以界面状态为准。",
                nextPrompt: "要继续查看下一集，还是先修改当前剧本？",
                requiresVisibleConfirmation: false
            )
        case .respond(let message):
            return .init(
                accepted: true,
                message: message,
                nextPrompt: planningVoiceFlow.mode?.prompt ?? "",
                requiresVisibleConfirmation: false
            )
        }
    }

    var currentInterviewPrompt: String {
        planningVoiceFlow.mode?.prompt ?? interviewFlow.prompt
    }

    func makeTextLarger() {
        _ = applyComfortCommand("字大一点")
    }

    func resetComfortPreferences() {
        comfortPreferences = ComfortPreferences()
        persistComfortPreferences()
        messages.append(.init(speaker: .nalu, text: "文字大小和朗读速度已经恢复默认。"))
    }

    private func applyComfortCommand(_ spoken: String) -> Bool {
        guard let response = comfortPreferences.consume(spoken) else { return false }
        persistComfortPreferences()
        messages.append(.init(speaker: .nalu, text: response))
        speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        return true
    }

    private func persistComfortPreferences() {
        guard let data = try? JSONEncoder().encode(comfortPreferences) else { return }
        UserDefaults.standard.set(data, forKey: "nalu.comfort-preferences.v1")
    }

    private static func loadComfortPreferences() -> ComfortPreferences {
        guard let data = UserDefaults.standard.data(forKey: "nalu.comfort-preferences.v1"),
              let preferences = try? JSONDecoder().decode(
                ComfortPreferences.self, from: data
              ) else {
            return ComfortPreferences()
        }
        return preferences
    }

    private var selectedProject: NaluProject? {
        projects.first { $0.id == selectedProjectID }
    }
}
