import Foundation
import Observation

private enum MemoryIntakeStep {
    case description
    case approximateDate
    case place
    case storyRelevance
}

private enum LibraryIntakeStep {
    case name
    case description
    case confirmation
    case correctionDescription
    case correctionRetry
}

private enum HookReviewVoiceStep {
    case disposition(Int)
    case explanation(Int)
    case confirmation
}

@MainActor
@Observable
final class VoiceInterviewViewModel {
    var projects: [NaluProject] = []
    var selectedProjectID: String? {
        didSet {
            if selectedProjectID != oldValue { projectSelectionGeneration = UUID() }
        }
    }
    private var projectSelectionGeneration = UUID()
    var seasons: [NaluSeason] = []
    var episodes: [NaluEpisode] = []
    var episodeProgressByID: [String: EpisodeProductionProgress] = [:]
    var productionProgressLastRefreshedAt: Date?
    var productionProgressRefreshWarning: String?
    var productionRunActionInProgress: String?
    var semanticMediaQARunInProgress: String?
    var semanticMediaQAStatusByRunID: [String: String] = [:]
    var publicationLearning: [PublicationLearningPresentation] = []
    var publicationLearningIsLoading = false
    var publicationLearningWarning: String?
    private var pendingVoiceRunCancellationID: String?
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
    var storageDiagnostics: StorageDiagnostics?
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
    var continuityExtractionProposal: ContinuityExtractionProposal?
    var reviewedContinuityExtractionHash: String?
    var isReadingEndingContinuity = false
    var continuityExtractionChangeSummary = ""
    var continuityHookResolutions: [ContinuityHookResolutionDraft] = []
    var continuityHookConfirmation = ""
    var continuityPreflightResult: ContinuityPreflightResult?
    var continuityTransitionExplanation = ""
    var continuityOverrideReason = ""
    var continuityOverrideConfirmation = ""
    var continuityStatus = "尚未检查跨集连续性"
    var assets: [NaluAsset] = []
    var memoryCards: [MemoryCard] = []
    var memoryConflictReports: [String: MemoryGraphConflictReport] = [:]
    var documentaryReadiness: DocumentaryReadinessReport?
    var libraryEntities: [LibraryEntity] = []
    var libraryDraftKind = "character"
    var libraryDraftName = ""
    var libraryDraftDescription = ""
    var reviewedMemoryCardIDs: Set<String> = []
    var memoryCorrectionCardID: String?
    var memoryConfirmationCardID: String?
    private var memoryIntakeCardID: String?
    private var memoryIntakeStep: MemoryIntakeStep?
    private var libraryIntakeStep: LibraryIntakeStep?
    private var libraryIntakeEntityID: String?
    private var shotCharacterReviewQueue: [String] = []
    private var shotCharacterReviewRunID: String?
    private var librarySnapshotRefreshing = false
    var shotPlanRefreshRevisionByRunID: [String: Int] = [:]
    private var productionBudgetConversation: ProductionBudgetConversation?
    var productionAuthorizationBusy = false
    private var libraryCorrectionEntity: LibraryEntity?
    private var pendingLibraryCorrection: LibraryEntityRevisionDraft?
    private var libraryCorrectionSaving = false
    private var hookReviewVoiceStep: HookReviewVoiceStep?
    private var hookReviewShouldCapture = false
    var draftProjectID: String?
    var feedbackDraftText = ""
    var isCapturingFeedback = false
    var feedbackWasDictated = false
    var feedbackReleaseReadiness: FeedbackGovernedReleaseReadiness?
    var comfortPreferences = VoiceInterviewViewModel.loadComfortPreferences()
    var planningVoiceLabel: String? { planningVoiceFlow.mode?.prompt }
    var assistantActionStatus: String?

    var continuityExtractionWasEdited: Bool {
        guard let proposal = continuityExtractionProposal else { return false }
        return endingContinuityDraft.state != proposal.state
            || endingContinuityDraft.hooks != proposal.unresolvedHooks
    }

    var canConfirmContinuityExtraction: Bool {
        guard let proposal = continuityExtractionProposal else { return false }
        return reviewedContinuityExtractionHash == proposal.proposalSHA256
            && endingContinuityDraft.hasContent
            && (!continuityExtractionWasEdited
                || !continuityExtractionChangeSummary.trimmingCharacters(
                    in: .whitespacesAndNewlines
                ).isEmpty)
    }

    private let runtime: RuntimeClient

    init(runtime: RuntimeClient = RuntimeClient()) {
        self.runtime = runtime
    }
    private let speech = SpeechRecorder()
    private let speechPlayback = SpeechPlayback()
    private var localVoiceEnabled = false

    func setLocalVoiceEnabled(_ enabled: Bool) {
        localVoiceEnabled = enabled
        speechPlayback.isEnabled = enabled
        if !enabled && isListening {
            speech.stop()
            isListening = false
        }
    }
    private let webResearch = OpenAIWebResearchClient()
    private let storyWriter = InteractiveStoryWriter()
    private let finalMasterSpeechRecognizer = FinalMasterSpeechRecognizer()
    private var interviewFlow = InterviewFlow()
    private var planningVoiceFlow = PlanningVoiceFlow()
    private var acceptedContinuityDraft: ContinuityPreflightDraft?

    func load() async {
        do {
            let health = try await runtime.health()
            runtimeStatus = "本地制片厂已就绪 · \(health.version)"
            await refreshStorageDiagnostics()
            projects = try await runtime.listProjects(includeArchived: includeArchivedProjects)
            if let first = projects.first { await selectProject(first.id) }
        } catch {
            runtimeStatus = "本地制片厂尚未启动"
            errorMessage = error.localizedDescription
        }
    }

    func refreshStorageDiagnostics() async {
        do {
            storageDiagnostics = try await runtime.storageDiagnostics()
        } catch {
            // Runtime health remains the authoritative connection signal. A transient
            // diagnostics failure should not interrupt the user's interview.
        }
    }

    func toggleListening() async {
        if isListening {
            speech.stop()
            isListening = false
            commitTranscript()
            return
        }
        guard localVoiceEnabled else {
            errorMessage = "当前使用 GPT 实时语音。请通过底部按钮连接，或明确切换到本机听写与朗读。"
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
            self.messages.append(
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
        if handleProductionBudgetAnswer(spoken) { return }
        if let number = Self.interactiveDraftSelection(spoken) {
            Task { await adoptInteractiveDraft(number: number) }
            return
        }
        if let request = AssistantActionRouter.route(spoken) {
            handleAssistantAction(request)
            return
        }
        if let response = handleProductionVoiceCommand(spoken) {
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
            return
        }
        if let hookReviewVoiceStep {
            handleHookReviewVoiceAnswer(spoken, step: hookReviewVoiceStep)
            return
        }
        if let libraryIntakeStep {
            handleLibraryIntakeAnswer(spoken, step: libraryIntakeStep)
            return
        }
        if let memoryIntakeCardID, let memoryIntakeStep {
            handleMemoryIntakeAnswer(
                spoken,
                memoryID: memoryIntakeCardID,
                step: memoryIntakeStep
            )
            return
        }
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
                || planningVoiceFlow.mode == .continuityConfirmation
                ? guardianConfirmedForScript : guardianConfirmedForPlan
            handle(
                planningVoiceFlow.consume(
                    spoken,
                    guardianRequired: selectedProject?.audienceMode == "child",
                    guardianConfirmed: guardianConfirmed
                )
            )
        } else {
            handleInteractiveStoryInput(spoken)
        }
    }

    private func queueStorySupplement(_ spoken: String, turnID: String, sourceMode: String = "narrated_story") {
        guard let projectID = selectedProjectID else {
            transcript = spoken
            messages.append(.init(speaker: .nalu, text: "项目正在建立，这句补充留在输入区，还没有发送。"))
            return
        }
        let generation = projectSelectionGeneration
        Task {
            do {
                var input = InteractiveStoryInput(turn_id: turnID, expected_revision: 0,
                    text: spoken, source_mode: sourceMode)
                input.queue_only = true
                _ = try await runtime.appendStoryInput(projectID: projectID, input: input)
                guard projectSelectionGeneration == generation else { return }
                messages.append(.init(speaker: .nalu, text: "这句补充已记在本机，我会接着处理。"))
                await drainStorySupplements(projectID: projectID, generation: generation)
            } catch {
                guard projectSelectionGeneration == generation else { return }
                transcript = spoken
                messages.append(.init(speaker: .nalu, text: "这句补充还没存好，已留在输入区，没有丢弃。"))
            }
        }
    }

    private func drainStorySupplements(projectID: String?, generation: UUID) async {
        guard let projectID, selectedProjectID == projectID,
              projectSelectionGeneration == generation, assistantActionStatus == nil else { return }
        guard let state = try? await runtime.interactiveStory(projectID: projectID),
              let next = state.queued_inputs?.first,
              selectedProjectID == projectID, projectSelectionGeneration == generation,
              assistantActionStatus == nil else { return }
        if next.source_mode == "web_source" {
            handleAssistantAction(.webResearch(query: next.text), turnID: next.turn_id)
        } else {
            handleInteractiveStoryInput(next.text, turnID: next.turn_id)
        }
    }

    private func handleInteractiveStoryInput(_ spoken: String, turnID: String = UUID().uuidString) {
        guard assistantActionStatus == nil else {
            queueStorySupplement(spoken, turnID: turnID)
            return
        }
        assistantActionStatus = "正在理解您的故事、整理分集…"
        let initialGeneration = projectSelectionGeneration
        let initialProjectID = selectedProjectID
        Task {
            var projectID = initialProjectID
            var generation = initialGeneration
            var revision: Int?
            var runtimeOwnedWriter = false
            defer {
                Task { await drainStorySupplements(projectID: projectID, generation: generation) }
            }
            do {
                if projectID == nil {
                    var draft = ProjectDraft()
                    draft.title = "未命名故事"
                    let project = try await runtime.createProject(draft)
                    guard projectSelectionGeneration == initialGeneration else {
                        assistantActionStatus = nil
                        return
                    }
                    projects = try await runtime.listProjects(includeArchived: includeArchivedProjects)
                    await selectProject(project.id)
                    projectID = project.id
                    generation = projectSelectionGeneration
                    messages.append(.init(speaker: .user, text: spoken))
                }
                guard let projectID else { throw InteractiveStoryWriter.WriterError.unavailable }
                let existing = try await runtime.interactiveStory(projectID: projectID)
                if let waiting = existing.queued_inputs, !waiting.isEmpty,
                   !waiting.contains(where: { $0.turn_id == turnID }) {
                    var input = InteractiveStoryInput(turn_id: turnID, expected_revision: existing.revision,
                        text: spoken, source_mode: "narrated_story")
                    input.queue_only = true
                    _ = try await runtime.appendStoryInput(projectID: projectID, input: input)
                    assistantActionStatus = nil
                    return // defer drains saved supplements before this newer input
                }
                let state = try await runtime.appendStoryInput(projectID: projectID,
                    input: .init(turn_id: turnID, expected_revision: existing.revision,
                                 text: spoken, source_mode: "narrated_story"))
                revision = state.revision
                let endpoint = try AIServiceEndpoint.current()
                let answer: InteractiveStoryAnswer
                if endpoint.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) == "https://hopsapi.com/v1" {
                    runtimeOwnedWriter = true
                    guard let key = try KeychainSecretStore().secret(for: .openAIRealtime), !key.isEmpty
                    else { throw InteractiveStoryWriter.WriterError.unavailable }
                    let model = try AIServiceModels.load(for: endpoint).research
                    let saved = try await runtime.generateStoryAnswer(projectID: projectID,
                        turnID: turnID, revision: state.revision, model: model, apiKey: key)
                    guard let generated = saved.turns.last?.answer else {
                        throw InteractiveStoryWriter.WriterError.invalidResponse
                    }
                    answer = generated
                } else {
                    // Other configured providers retain their existing path;
                    // never silently fall back after a Hops request failure.
                    let result = try await storyWriter.write(state: state)
                    answer = result.answer
                    _ = try await runtime.saveStoryAnswer(projectID: projectID, turnID: turnID,
                        answer: .init(expected_revision: state.revision, reply: answer.reply,
                                      summary: answer.summary, episode_drafts: answer.episode_drafts,
                                      outcome: "answered", external_writer: result.declaration,
                                      writer_response_json: result.responseJSON))
                }
                assistantActionStatus = nil
                guard projectSelectionGeneration == generation else { return }
                let drafts = answer.episode_drafts.map {
                    "第\($0.episode_number)集《\($0.title)》草稿\n\($0.outline)\n\n\($0.script)"
                }.joined(separator: "\n\n")
                messages.append(.init(speaker: .nalu, text: answer.reply + (drafts.isEmpty ? "" : "\n\n" + drafts + "\n\n您可以继续说哪里要改；要放进分集审阅，请说“采用第1集草稿”（换成对应集数）。")))
                speechPlayback.speak(answer.reply, rate: comfortPreferences.speechRate)
            } catch {
                if !runtimeOwnedWriter, let projectID, let revision {
                    _ = try? await runtime.saveStoryAnswer(projectID: projectID, turnID: turnID,
                        answer: .init(expected_revision: revision,
                                      reply: "编剧请求未完成，原有故事和草稿保留。", summary: "",
                                      episode_drafts: [], outcome: "writer_failed"))
                }
                assistantActionStatus = nil
                guard projectSelectionGeneration == generation else { return }
                let reply = "这次编剧请求没有完成，已有内容没有清空。我没有自动重复请求。您可以继续补充故事。"
                messages.append(.init(speaker: .nalu, text: reply))
                speechPlayback.speak(reply, rate: comfortPreferences.speechRate)
            }
        }
    }

    static func interactiveDraftSelection(_ text: String) -> Int? {
        // Dictation routinely adds spaces and terminal punctuation. Match a whole
        // explicit review request, never a substring of a negation or question.
        let cleaned = text.filter { !$0.isWhitespace }
            .trimmingCharacters(in: CharacterSet(charactersIn: "。.!！"))
        let patterns = [
            "^(?:请|请帮我|帮我)?采用第([0-9]{1,3}|[一二三四五六七八九十两]{1,3})集草稿$",
            "^(?:请|请帮我|帮我)?把第([0-9]{1,3}|[一二三四五六七八九十两]{1,3})集草稿(?:放进|放入|送去|送交)(?:分集|剧本)?审阅$",
        ]
        let digits: [String: Int] = ["一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                                   "五": 5, "六": 6, "七": 7, "八": 8, "九": 9]
        for pattern in patterns {
            guard let expression = try? NSRegularExpression(pattern: pattern),
                  let match = expression.firstMatch(in: cleaned, range: NSRange(cleaned.startIndex..., in: cleaned)),
                  let range = Range(match.range(at: 1), in: cleaned) else { continue }
            let number = String(cleaned[range])
            if let value = Int(number) { return (1...999).contains(value) ? value : nil }
            if let value = digits[number] { return value }
            let parts = number.components(separatedBy: "十")
            guard parts.count == 2,
                  let tens = parts[0].isEmpty ? 1 : digits[parts[0]],
                  let units = parts[1].isEmpty ? 0 : digits[parts[1]] else { return nil }
            return tens * 10 + units
        }
        return nil
    }

    private func adoptInteractiveDraft(number: Int) async {
        guard let projectID = selectedProjectID, assistantActionStatus == nil else { return }
        let generation = projectSelectionGeneration
        let requestedSeason = episodes.first(where: { $0.id == selectedEpisodeID })?.seasonID
        assistantActionStatus = "正在把草稿放入本集剧本审阅…"
        defer { assistantActionStatus = nil }
        do {
            let state = try await runtime.interactiveStory(projectID: projectID)
            guard let draft = state.episode_drafts.first(where: { $0.episode_number == number }),
                  let writer = state.draft_writers?[String(number)] ?? nil else {
                throw InteractiveStoryWriter.WriterError.invalidResponse
            }
            let available = try await runtime.listSeasons(projectID: projectID)
            let season: NaluSeason
            if let matching = available.first(where: { $0.id == requestedSeason }) {
                season = matching
            } else if available.count == 1, let only = available.first {
                season = only
            } else if available.isEmpty {
                season = try await runtime.createSeason(projectID: projectID,
                    draft: .init(title: "第一季", seasonNumber: 1,
                                 plannedEpisodeCount: max(number, state.episode_drafts.count)))
            } else { throw InteractiveStoryWriter.WriterError.invalidResponse }
            let episode = try await runtime.resolveReviewEpisode(seasonID: season.id,
                draft: .init(title: draft.title, episodeNumber: number, logline: draft.outline,
                             targetSeconds: 60))
            let revisions = try await runtime.listScripts(episodeID: episode.id)
            let script: ScriptRevision
            if let existing = revisions.first(where: { $0.content == draft.script &&
                $0.authoringProvenance?.externalWriter?.receiptSHA256 == writer.receiptSHA256 }) {
                script = existing
            } else {
                script = try await runtime.createScript(episodeID: episode.id, content: draft.script,
                    summary: draft.outline, sourceTranscript: state.summary,
                    authoringOrigin: "external_ai_generated", externalWriter: writer,
                    idempotencyKey: "interactive-" + writer.receiptSHA256)
            }
            if let receipt = state.draft_receipts?[String(number)] ?? nil {
                try await runtime.reconcileInteractiveReceipt(episodeID: episode.id,
                    revision: script.revision, receipt: receipt)
            }
            guard projectSelectionGeneration == generation else { return }
            await selectProject(projectID)
            selectEpisode(episode.id)
            let reply = "第\(number)集草稿已放进剧本审阅，尚未批准或启动付费制作。请核对内容，您也可以继续告诉我哪里要改。"
            messages.append(.init(speaker: .nalu, text: reply))
            speechPlayback.speak(reply, rate: comfortPreferences.speechRate)
        } catch {
            guard projectSelectionGeneration == generation else { return }
            messages.append(.init(speaker: .nalu, text: "这份草稿还没有成功放进分集审阅。原草稿保留，没有启动制作。请确认已选择季和对应的草稿。"))
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
        feedbackReleaseReadiness = nil
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
            var reviewBundlePrepared = false
            var reviewBundlePreparationFailed = false
            if saved.status == "ready_for_review" {
                let preparation = FeedbackReviewPreparation.infer(
                    category: category,
                    message: saved.message,
                    screen: "interview"
                )
                do {
                    let bundle = try await runtime.createFeedbackReviewBundle(
                        feedbackID: saved.id,
                        draft: FeedbackReviewBundleDraft(
                            preparedBy: "local-user",
                            expectedBehavior: preparation.expectedBehavior,
                            actualBehavior: preparation.actualBehavior,
                            reproductionSteps: preparation.reproductionSteps,
                            confirmationText: "我确认生成审核包"
                        )
                    )
                    reviewBundlePrepared = !bundle.networkCallPerformed
                        && bundle.attachments.isEmpty
                } catch {
                    reviewBundlePreparationFailed = true
                    errorMessage = error.localizedDescription
                }
            }
            let responseText: String
            if reviewBundlePrepared {
                responseText = "意见已脱敏，Nalu 也替您整理好了本地审核资料。没有上传声音、照片或项目内容；任何程序改动仍需测试和人工审核。"
            } else if reviewBundlePreparationFailed {
                responseText = "意见已经安全保存在本机，但审核资料还没有整理好。以后可以重试，不需要您重新说一遍。"
            } else if saved.status == "ready_for_review" {
                responseText = "意见已脱敏并进入待审核改进队列。任何程序改动仍需测试和审核。"
            } else {
                responseText = "意见只保存在这台 Mac 上，不会自动上传。"
            }
            messages.append(
                .init(
                    speaker: .nalu,
                    text: responseText
                )
            )
            do {
                let readiness = try await runtime.feedbackReleaseReadiness(
                    feedbackID: saved.id
                )
                feedbackReleaseReadiness = readiness
                let missingCount = readiness.checks.filter { $0.status == "missing" }.count
                let readinessText = readiness.readyForAuthorizedRollout
                    ? "这条意见的发布前证据已经齐全，但还没有真正发布。仍需管理员授权、真实分阶段发布和安装后健康确认。"
                    : "这条意见已经记下，目前还有 \(missingCount) 项流程没有完成。Nalu 不会把已记录或已审核误说成已经修好。"
                messages.append(.init(speaker: .nalu, text: readinessText))
                speechPlayback.speak(readinessText, rate: comfortPreferences.speechRate)
            } catch {
                errorMessage = "意见已保存，但暂时无法读取改进进度：\(error.localizedDescription)"
            }
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func readFeedbackReleaseReadiness() {
        guard let readiness = feedbackReleaseReadiness else { return }
        let missing = readiness.checks.filter { $0.status == "missing" }
        let summary: String
        if readiness.readyForAuthorizedRollout {
            summary = "发布前证据已经齐全，但这条意见还没有发布。还需要管理员授权、真实分阶段发布和安装后健康确认。"
        } else {
            let first = missing.prefix(3).map(\.explanation).joined(separator: "；")
            summary = "这条意见还没有修好。目前缺少 \(missing.count) 项。\(first)"
        }
        speechPlayback.speak(summary, rate: comfortPreferences.speechRate)
    }

    func beginLibraryVoiceIntake(kind: String) async {
        guard selectedProjectID != nil else { return }
        libraryDraftKind = kind
        libraryDraftName = ""
        libraryDraftDescription = ""
        libraryIntakeEntityID = nil
        libraryIntakeStep = .name
        let prompt = "我们来添加一份项目级\(libraryKindLabel(kind))设定。请先告诉我，它叫什么名字？"
        messages.append(.init(speaker: .nalu, text: prompt))
        speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
        if !isListening { await toggleListening() }
    }

    @discardableResult
    func createLibraryEntity(sourceChannel: String = "visual") async -> LibraryEntity? {
        guard let projectID = selectedProjectID else { return nil }
        let name = libraryDraftName.trimmingCharacters(in: .whitespacesAndNewlines)
        let description = libraryDraftDescription.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty, !description.isEmpty else {
            errorMessage = "请先填写名称，并用一句话说明这份设定。"
            return nil
        }
        do {
            let created = try await runtime.createLibraryEntity(
                projectID: projectID,
                draft: LibraryEntityCreateDraft(
                    kind: libraryDraftKind,
                    name: name,
                    description: description,
                    attributes: [:],
                    sourceAssetIDs: [],
                    sourceMemoryIDs: [],
                    sourceChannel: sourceChannel,
                    changeSummary: sourceChannel == "voice" ? "用户语音建立草稿" : "用户在本机建立草稿"
                )
            )
            libraryEntities = try await runtime.listLibraryEntities(projectID: projectID)
            return created
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func confirmLibraryEntity(_ entityID: String, reviewChannel: String = "visual") async {
        guard let projectID = selectedProjectID,
              let entity = libraryEntities.first(where: { $0.id == entityID }) else { return }
        let generation = projectSelectionGeneration
        do {
            _ = try await runtime.confirmLibraryEntity(
                entityID: entityID,
                draft: LibraryEntityConfirmationDraft(
                    confirmedBy: "local-user",
                    reviewedRevision: entity.currentRevision,
                    reviewChannel: reviewChannel,
                    spokenConfirmation: "我确认这份项目设定"
                )
            )
            let refreshedEntities = try await runtime.listLibraryEntities(projectID: projectID)
            guard selectedProjectID == projectID, projectSelectionGeneration == generation else { return }
            libraryEntities = refreshedEntities
            let response = "已确认\(entity.current.name)。以后每一集都会继承这个版本，修改时会另存新版本。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
            if shotCharacterReviewQueue.first == entityID {
                shotCharacterReviewQueue.removeFirst()
                await promptNextShotCharacter()
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func beginProductionAuthorization(runID: String, planID: String, planSHA: String) async {
        guard let projectID = selectedProjectID, let episodeID = selectedEpisodeID,
              !productionAuthorizationBusy else { return }
        guard libraryIntakeStep == nil, !librarySnapshotRefreshing else {
            productionBudgetReply("请先完成正在核对的人物资料，原分镜会保留。")
            return
        }
        if let pending = productionBudgetConversation, pending.runID == runID,
           pending.episodeID == episodeID, pending.submittedDraft != nil {
            productionBudgetReply("上一次制作确认尚待核对。请说“重试制作确认”，会使用原来的预算和确认，不会新建任务。")
            return
        }
        let generation = projectSelectionGeneration
        productionAuthorizationBusy = true
        defer { if projectSelectionGeneration == generation { productionAuthorizationBusy = false } }
        do {
            let run = try await runtime.productionRun(runID: runID)
            guard run.id == runID, run.projectID == projectID, run.episodeID == episodeID,
                  selectedEpisodeID == episodeID, selectedProjectID == projectID,
                  projectSelectionGeneration == generation else { return }
            if !run.dryRun {
                guard run.status == "waiting_for_approval", let budget = run.estimatedBudgetCredits, budget > 0 else {
                    productionBudgetReply("本集已有制作记录，需要先核对当前进度或恢复状态。这里没有改动预算或重复提交。")
                    return
                }
                productionBudgetReply("本集已有制作授权，预计预算是 \(budget) 积分。接下来逐个镜头核对画面和费用，不需要重建项目。")
                return
            }
            let preview = try await runtime.productionAuthorizationPreview(runID: runID)
            guard projectSelectionGeneration == generation, selectedEpisodeID == episodeID else { return }
            guard preview.run_id == runID, !preview.refresh_required,
                  preview.request.source_event_id == planID, preview.request.expected_plan_sha256 == planSHA else {
                productionBudgetReply("本集人物或分镜已经变化。请先核对本集人物并读取保存方案，再确认预算；剧本没有丢失。")
                return
            }
            let conversation = ProductionBudgetConversation(runID: runID, episodeID: episodeID, preview: preview.request,
                guardianRequired: projects.first(where: { $0.id == projectID })?.audienceMode == "child")
            productionBudgetConversation = conversation
            productionBudgetReply(conversation.opening)
        } catch {
            guard projectSelectionGeneration == generation, selectedEpisodeID == episodeID else { return }
            productionBudgetReply("暂时无法核对本集制作状态。原剧本和分镜保留，请稍后再点“确认本集制作预算”。")
        }
    }

    private func productionBudgetReply(_ text: String) {
        messages.append(.init(speaker: .nalu, text: text))
        speechPlayback.speak(text, rate: comfortPreferences.speechRate)
    }

    private func handleProductionBudgetAnswer(_ spoken: String) -> Bool {
        guard var conversation = productionBudgetConversation else { return false }
        guard conversation.episodeID == selectedEpisodeID else {
            productionBudgetConversation = nil
            return false
        }
        if productionAuthorizationBusy {
            productionBudgetReply("正在保存刚才的制作确认，请稍等；不会重复提交。")
            return true
        }
        let answer = conversation.answer(spoken)
        productionBudgetConversation = conversation
        switch answer {
        case .reply(let text): productionBudgetReply(text)
        case .cancel:
            productionBudgetConversation = nil
            productionBudgetReply("已停止这次制作确认。原故事、剧本和分镜都保留；已保存的授权不会因此撤销。")
        case .unrelated: return false
        case .submit(let draft):
            productionAuthorizationBusy = true
            Task { await saveProductionAuthorization(conversation: conversation, draft: draft) }
        }
        return true
    }

    private func saveProductionAuthorization(conversation: ProductionBudgetConversation, draft: ProductionAuthorizationDraft) async {
        let generation = projectSelectionGeneration
        defer { if projectSelectionGeneration == generation { productionAuthorizationBusy = false } }
        guard conversation.episodeID == selectedEpisodeID else { return }
        productionBudgetReply("正在保存本集制作确认。这里不会提交图片、视频或产生扣费。")
        do {
            _ = try await runtime.authorizeProduction(runID: conversation.runID, draft: draft)
            guard projectSelectionGeneration == generation, selectedEpisodeID == conversation.episodeID else { return }
            productionBudgetConversation = nil
            shotPlanRefreshRevisionByRunID[conversation.runID, default: 0] += 1
            productionBudgetReply("本集制作预算已确认，原剧本和分镜保留。接下来核对人物和镜头画面，并在生成前确认具体费用。现在还没有生成或扣费。")
        } catch {
            guard projectSelectionGeneration == generation, selectedEpisodeID == conversation.episodeID else { return }
            productionBudgetReply("暂时没有核对到保存结果。原制作任务和预算确认保留，您可以说“重试制作确认”，用同一份确认核对，不会新建制作任务。")
        }
    }

    func beginShotCharacterReview(_ entityIDs: [String], runID: String) async {
        guard let projectID = selectedProjectID, !librarySnapshotRefreshing else { return }
        let generation = projectSelectionGeneration
        do {
            let run = try await runtime.productionRun(runID: runID)
            guard run.id == runID, run.projectID == projectID, selectedProjectID == projectID,
                  projectSelectionGeneration == generation else { return }
            let entities = try await runtime.listLibraryEntities(projectID: projectID)
            guard selectedProjectID == projectID, projectSelectionGeneration == generation,
                  entityIDs.allSatisfy({ id in entities.contains(where: { $0.id == id && $0.kind == "character" }) }) else { return }
            libraryEntities = entities
            shotCharacterReviewRunID = runID
            shotCharacterReviewQueue = entityIDs.filter { id in
                entities.contains { $0.id == id && $0.confirmedRevision != $0.currentRevision }
            }
            await promptNextShotCharacter()
        } catch {
            guard projectSelectionGeneration == generation else { return }
            errorMessage = "人物草稿已保留，暂时无法读取。分镜没有丢失，可以稍后再核对本集人物。"
        }
    }

    private func promptNextShotCharacter() async {
        libraryIntakeEntityID = nil
        libraryIntakeStep = nil
        if shotCharacterReviewQueue.isEmpty {
            await refreshReviewedCharacterSnapshot()
            return
        }
        guard let id = shotCharacterReviewQueue.first,
              let entity = libraryEntities.first(where: { $0.id == id }) else { return }
        libraryIntakeEntityID = id
        libraryIntakeStep = .confirmation
        let prompt = "我们核对一位人物：\(entity.current.name)，\(entity.current.description)。这是待确认的草稿，不代表真人授权。正确请说“我确认这份项目设定”；不正确请说“不要确认”，我们先保留草稿。"
        messages.append(.init(speaker: .nalu, text: prompt))
        speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
    }

    private func refreshReviewedCharacterSnapshot() async {
        guard let runID = shotCharacterReviewRunID, let projectID = selectedProjectID,
              !librarySnapshotRefreshing else { return }
        let generation = projectSelectionGeneration
        librarySnapshotRefreshing = true
        defer { if projectSelectionGeneration == generation { librarySnapshotRefreshing = false } }
        let waiting = "人物已确认，正在更新本集制作资料。原剧本和分镜会保留，不会在这里生成或收费。"
        messages.append(.init(speaker: .nalu, text: waiting))
        speechPlayback.speak(waiting, rate: comfortPreferences.speechRate)
        do {
            _ = try await runtime.refreshConfirmedLibrary(runID: runID)
            guard projectSelectionGeneration == generation, selectedProjectID == projectID,
                  shotCharacterReviewRunID == runID else { return }
            shotPlanRefreshRevisionByRunID[runID, default: 0] += 1
            shotCharacterReviewRunID = nil
            let response = "本集制作资料已更新，已确认的分镜保留。接下来可以准备本集人物图片和镜头画面。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        } catch {
            guard projectSelectionGeneration == generation, selectedProjectID == projectID else { return }
            let response = "人物确认和剧本都已保存，制作资料暂时没有更新成功。请再点“核对本集人物”重试，不用重讲故事或重填密钥。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        }
    }

    func speakLibraryEntity(_ entityID: String) {
        guard let entity = libraryEntities.first(where: { $0.id == entityID }) else { return }
        let status = entity.confirmedRevision == entity.currentRevision
            ? "当前版本已经确认。" : "当前版本还没有确认，不会进入生产。"
        speechPlayback.speak(
            "\(libraryKindLabel(entity.kind))，\(entity.current.name)。\(entity.current.description)。\(status)",
            rate: comfortPreferences.speechRate
        )
    }

    private func handleLibraryIntakeAnswer(_ spoken: String, step: LibraryIntakeStep) {
        guard !libraryCorrectionSaving else {
            speechPlayback.speak("正在保存您刚才的修改，请稍等。旧资料仍然保留。", rate: comfortPreferences.speechRate)
            return
        }
        switch step {
        case .name:
            libraryDraftName = spoken
            libraryIntakeStep = .description
            let prompt = "好的，\(spoken)。请用一两句话说明它的样子、作用，或者需要一直保持的特点。"
            messages.append(.init(speaker: .nalu, text: prompt))
            speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
        case .description:
            libraryDraftDescription = spoken
            Task {
                guard let created = await createLibraryEntity(sourceChannel: "voice") else {
                    libraryIntakeStep = nil
                    return
                }
                libraryIntakeEntityID = created.id
                libraryIntakeStep = .confirmation
                let prompt = "我整理的是：\(created.current.name)，\(created.current.description)。正确请说“我确认这份项目设定”；不正确可以说“不要确认”。"
                messages.append(.init(speaker: .nalu, text: prompt))
                speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
            }
        case .confirmation:
            if LibraryVoiceCorrection.requestsChange(spoken), let id = libraryIntakeEntityID,
               let entity = libraryEntities.first(where: { $0.id == id }) {
                libraryCorrectionEntity = entity
                pendingLibraryCorrection = nil
                libraryIntakeStep = .correctionDescription
                let prompt = "好的，先不确认。请把\(entity.current.name)修改后的完整描述说一遍；我会另存新版本，再读给您听，原来的资料保留。"
                messages.append(.init(speaker: .nalu, text: prompt))
                speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
                return
            }
            let entityID = libraryIntakeEntityID
            libraryIntakeEntityID = nil
            libraryIntakeStep = nil
            guard !["不要", "不确认", "不同意", "不对", "还没", "别确认"].contains(where: spoken.contains),
                  spoken.contains("我确认") || spoken.contains("我同意") else {
                shotCharacterReviewQueue = []
                shotCharacterReviewRunID = nil
                let response = "没有听到明确确认，所以这份设定仍是草稿，不会进入生产。"
                messages.append(.init(speaker: .nalu, text: response))
                speechPlayback.speak(response, rate: comfortPreferences.speechRate)
                return
            }
            if let entityID { Task { await confirmLibraryEntity(entityID, reviewChannel: "voice") } }
        case .correctionDescription:
            if ["取消修改", "先不改了"].contains(where: spoken.contains) {
                libraryCorrectionEntity = nil
                pendingLibraryCorrection = nil
                libraryIntakeStep = .confirmation
                return
            }
            guard let entity = libraryCorrectionEntity,
                  let draft = LibraryVoiceCorrection.draft(for: entity, description: spoken) else {
                speechPlayback.speak("请说一段完整的人物描述，长度控制在一万字以内。", rate: comfortPreferences.speechRate)
                return
            }
            pendingLibraryCorrection = draft
            Task { await saveLibraryVoiceCorrection() }
        case .correctionRetry:
            if spoken.contains("重试") || spoken.contains("再保存") {
                Task { await saveLibraryVoiceCorrection() }
            } else if spoken.contains("取消修改") {
                pendingLibraryCorrection = nil
                libraryCorrectionEntity = nil
                libraryIntakeEntityID = nil
                libraryIntakeStep = nil
                shotCharacterReviewQueue = []
            } else {
                speechPlayback.speak("刚才的修改仍保留在这次对话里。您可以说“重试保存”，或者“取消修改”。", rate: comfortPreferences.speechRate)
            }
        }
    }

    private func saveLibraryVoiceCorrection() async {
        guard !libraryCorrectionSaving, let entity = libraryCorrectionEntity,
              selectedProjectID == entity.projectID, let draft = pendingLibraryCorrection else { return }
        let generation = projectSelectionGeneration
        libraryCorrectionSaving = true
        defer { if projectSelectionGeneration == generation { libraryCorrectionSaving = false } }
        do {
            let updated = try await runtime.createLibraryRevision(entityID: entity.id, draft: draft)
            guard projectSelectionGeneration == generation, selectedProjectID == entity.projectID else { return }
            guard updated.id == entity.id, updated.projectID == entity.projectID,
                  updated.currentRevision == entity.currentRevision + 1,
                  updated.current.description == draft.description else { throw URLError(.badServerResponse) }
            if let index = libraryEntities.firstIndex(where: { $0.id == updated.id }) { libraryEntities[index] = updated }
            pendingLibraryCorrection = nil
            libraryCorrectionEntity = nil
            libraryIntakeEntityID = updated.id
            libraryIntakeStep = .confirmation
            let prompt = "修改已另存第\(updated.currentRevision)版：\(updated.current.name)，\(updated.current.description)。正确请说“我确认这份项目设定”；还要改可以说“我要修改”。旧版本仍然保留。"
            messages.append(.init(speaker: .nalu, text: prompt))
            speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
        } catch {
            guard projectSelectionGeneration == generation else { return }
            libraryIntakeStep = .correctionRetry
            let prompt = "这次修改还没有确认保存成功，可能是资料版本发生变化。您刚才说的是：\(draft.description)。内容仍保留在这次对话里，可以说“重试保存”；不会覆盖后来的修改。"
            messages.append(.init(speaker: .nalu, text: prompt))
            speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
        }
    }

    private func libraryKindLabel(_ kind: String) -> String {
        switch kind {
        case "character": return "人物"
        case "scene": return "场景"
        case "prop": return "道具"
        case "voice": return "声音"
        case "style": return "画面风格"
        default: return "项目"
        }
    }

    func selectProject(_ projectID: String) async {
        let switchedProject = selectedProjectID != projectID
        selectedProjectID = projectID
        // Also supersede a concurrent reload of the same project.
        projectSelectionGeneration = UUID()
        let generation = projectSelectionGeneration
        if switchedProject { messages = [] }
        shotCharacterReviewQueue = []
        shotCharacterReviewRunID = nil
        librarySnapshotRefreshing = false
        productionBudgetConversation = nil
        productionAuthorizationBusy = false
        shotPlanRefreshRevisionByRunID = [:]
        libraryIntakeEntityID = nil
        libraryIntakeStep = nil
        libraryCorrectionEntity = nil
        pendingLibraryCorrection = nil
        libraryCorrectionSaving = false
        let isDocumentary = selectedProject?.creativeFormat == "documentary_series"
        pendingVoiceRunCancellationID = nil
        memoryConflictReports = [:]
        publicationLearning = []
        publicationLearningWarning = nil
        publicationLearningIsLoading = false
        assets = []
        memoryCards = []
        libraryEntities = []
        documentaryReadiness = nil
        seasons = []
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
        productionProgressLastRefreshedAt = nil
        productionProgressRefreshWarning = nil
        do {
            let loadedAssets = try await runtime.listAssets(projectID: projectID)
            guard projectSelectionGeneration == generation else { return }
            let loadedMemories = try await runtime.listMemoryCards(projectID: projectID)
            guard projectSelectionGeneration == generation else { return }
            let loadedLibrary = try await runtime.listLibraryEntities(projectID: projectID)
            guard projectSelectionGeneration == generation else { return }
            if isDocumentary {
                let readiness = try await runtime.documentaryReadiness(projectID: projectID)
                guard projectSelectionGeneration == generation else { return }
                documentaryReadiness = readiness
            } else {
                documentaryReadiness = nil
            }
            let loadedSeasons = try await runtime.listSeasons(projectID: projectID)
            guard projectSelectionGeneration == generation else { return }
            if let season = loadedSeasons.first {
                let loadedEpisodes = try await runtime.listEpisodes(seasonID: season.id)
                guard projectSelectionGeneration == generation else { return }
                let progress = try await runtime.listEpisodeProgress(seasonID: season.id)
                guard projectSelectionGeneration == generation else { return }
                episodes = loadedEpisodes
                episodeProgressByID = Dictionary(
                    uniqueKeysWithValues: progress.map { ($0.episodeID, $0) }
                )
                productionProgressLastRefreshedAt = Date()
                productionProgressRefreshWarning = nil
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
                productionProgressLastRefreshedAt = nil
                productionProgressRefreshWarning = nil
                selectedEpisodeID = nil
                scriptRevisions = []
                scriptContent = ""
                scriptSummary = ""
                viewedScriptRevision = nil
                seasonPlanSummary = ""
                episodeLogline = ""
                episodeOutlineSummary = ""
            }
            assets = loadedAssets
            memoryCards = loadedMemories
            libraryEntities = loadedLibrary
            seasons = loadedSeasons
            if switchedProject {
                do {
                    let story = try await runtime.interactiveStory(projectID: projectID)
                    guard projectSelectionGeneration == generation else { return }
                    messages = story.conversationMessages()
                    if messages.isEmpty {
                        messages = [.init(speaker: .nalu, text: "我们可以从您的故事开始，也可以先找您想用的网上资料。请告诉我。")]
                    }
                } catch {
                    guard projectSelectionGeneration == generation else { return }
                    messages = [.init(speaker: .nalu, text: "这个项目的历史对话暂时没有读到；我没有删除它。请稍后重新打开项目。")]
                }
            }
            await refreshPublicationLearning(projectID: projectID)
        } catch {
            guard projectSelectionGeneration == generation else { return }
            errorMessage = error.localizedDescription
        }
    }

    func refreshPublicationLearning() async {
        guard let selectedProjectID else { return }
        await refreshPublicationLearning(projectID: selectedProjectID)
    }

    private func refreshPublicationLearning(projectID: String) async {
        let generation = projectSelectionGeneration
        publicationLearningIsLoading = true
        defer {
            if projectSelectionGeneration == generation { publicationLearningIsLoading = false }
        }
        do {
            let records = try await runtime.publicationLearning(projectID: projectID)
            guard selectedProjectID == projectID, projectSelectionGeneration == generation else { return }
            publicationLearning = records.map { record in
                PublicationLearningPresentation(
                    record: record,
                    targetEpisode: episodes.first(where: {
                        $0.id == record.strategy.targetEpisodeID
                    })
                )
            }
            publicationLearningWarning = nil
        } catch {
            guard selectedProjectID == projectID, projectSelectionGeneration == generation else { return }
            publicationLearning = []
            publicationLearningWarning = "反馈记录暂时无法安全核验；没有触发发布、制作或付费操作。"
        }
    }

    func readShotPlanText(_ text: String) {
        speechPlayback.speak(text, rate: comfortPreferences.speechRate)
    }

    func speakLatestPublicationLearning() {
        guard let latest = publicationLearning.last else { return }
        messages.append(.init(speaker: .nalu, text: latest.spokenSummary))
        speechPlayback.speak(latest.spokenSummary, rate: comfortPreferences.speechRate)
    }

    func refreshProductionProgress(seasonID: String) async {
        do {
            let progress = try await runtime.listEpisodeProgress(seasonID: seasonID)
            guard seasons.contains(where: { $0.id == seasonID }) else { return }
            episodeProgressByID = Dictionary(
                uniqueKeysWithValues: progress.map { ($0.episodeID, $0) }
            )
            productionProgressLastRefreshedAt = Date()
            productionProgressRefreshWarning = nil
        } catch {
            guard seasons.contains(where: { $0.id == seasonID }) else { return }
            productionProgressRefreshWarning = "状态暂时没有更新，Nalu 会继续自动重试。"
        }
    }

    func cancelProductionRun(runID: String) async {
        guard productionRunActionInProgress == nil else { return }
        productionRunActionInProgress = runID
        defer { productionRunActionInProgress = nil }
        do {
            _ = try await runtime.cancelProductionRun(runID: runID)
            if let seasonID = seasons.first?.id {
                await refreshProductionProgress(seasonID: seasonID)
            }
            messages.append(
                .init(
                    speaker: .nalu,
                    text: "已经安全暂停。本集进度和制作记录都保存在这台 Mac 上，稍后可以继续。"
                )
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func resumeProductionRun(runID: String) async {
        guard productionRunActionInProgress == nil else { return }
        productionRunActionInProgress = runID
        defer { productionRunActionInProgress = nil }
        do {
            _ = try await runtime.resumeProductionRun(runID: runID)
            if let seasonID = seasons.first?.id {
                await refreshProductionProgress(seasonID: seasonID)
            }
            messages.append(
                .init(
                    speaker: .nalu,
                    text: "已经从安全检查开始恢复。任何可能产生费用的提交仍然要等您再次确认。"
                )
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func verifyFinalMaster(runID: String) async {
        guard productionRunActionInProgress == nil,
              semanticMediaQARunInProgress == nil else { return }
        semanticMediaQARunInProgress = runID
        semanticMediaQAStatusByRunID[runID] = "正在安全下载当前封存成片…"
        defer { semanticMediaQARunInProgress = nil }

        var downloadedFile: URL?
        do {
            let download = try await runtime.downloadSealedMaster(runID: runID)
            downloadedFile = download.fileURL
            semanticMediaQAStatusByRunID[runID] = "正在这台 Mac 上识别成片声音，不会上传录音…"
            let recognition = try await finalMasterSpeechRecognizer.recognize(
                fileURL: download.fileURL
            )
            semanticMediaQAStatusByRunID[runID] = "正在核对台词和每个镜头切点…"
            let report = try await runtime.submitSemanticMediaQA(
                runID: runID,
                draft: recognition.semanticQADraft(masterSHA256: download.sha256)
            )
            let response: String
            if report.status == "PASS" {
                semanticMediaQAStatusByRunID[runID] = "本机声音和镜头切点自动检查通过"
                response = "本机自动检查通过：成片中的中文台词与字幕一致，镜头切点也能正常解码。接下来仍要由您查看原尺寸成片，确认内容和观感。"
            } else {
                let count = report.failures.count
                semanticMediaQAStatusByRunID[runID] = "发现 \(count) 项需要修复，尚未进入发行"
                response = "自动检查发现 \(count) 项需要修复，Nalu 已经安全停在发行之前，并保留了修复证据。"
            }
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        } catch {
            let response = "成片自动检查没有完成：\(error.localizedDescription)。没有改用云端识别，也没有进入发行。"
            semanticMediaQAStatusByRunID[runID] = response
            errorMessage = error.localizedDescription
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        }
        if let downloadedFile {
            try? FileManager.default.removeItem(at: downloadedFile)
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
            continuityExtractionProposal = nil
            reviewedContinuityExtractionHash = nil
            isReadingEndingContinuity = false
            continuityExtractionChangeSummary = ""
            continuityHookResolutions = inheritedResult.snapshot?.unresolvedHooks.map {
                ContinuityHookResolutionDraft(
                    hook: $0, disposition: "", explanation: ""
                )
            } ?? []
            continuityHookConfirmation = ""
            hookReviewVoiceStep = nil
            hookReviewShouldCapture = false
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
                planRevision: season.planRevision,
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

    func beginContinuityVoiceConfirmation(startLocalCapture: Bool = true) async {
        guard canConfirmContinuityExtraction else {
            errorMessage = "请先朗读核对；如果修改过内容，请填写修改说明并重新朗读。"
            return
        }
        await beginPlanningVoice(
            .continuityConfirmation, startLocalCapture: startLocalCapture
        )
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
            if let hookReview = acceptedContinuityDraft.hookReview {
                narrativeMetadata["continuity_hook_review"] = .object([
                    "schema_version": .string(hookReview.schemaVersion),
                    "inherited_snapshot_id": .string(hookReview.inheritedSnapshotID),
                    "resolutions": .array(hookReview.resolutions.map { resolution in
                        .object([
                            "hook": .string(resolution.hook),
                            "disposition": .string(resolution.disposition),
                            "explanation": .string(resolution.explanation),
                        ])
                    }),
                    "reviewed_by": .string(hookReview.reviewedBy),
                    "spoken_confirmation": .string(hookReview.spokenConfirmation),
                    "guardian_approval": .bool(hookReview.guardianApproval),
                ])
            }
        }
        if endingContinuityDraft.hasContent {
            narrativeMetadata["ending_continuity"] = endingContinuityDraft.state.jsonValue
            narrativeMetadata["ending_unresolved_hooks"] = .array(
                endingContinuityDraft.hooks.map(JSONValue.string)
            )
        }
        do {
            _ = try await runtime.createScript(
                episodeID: episodeID,
                content: content,
                summary: summary,
                sourceTranscript: sourceTranscript,
                narrativeMetadata: narrativeMetadata,
                authoringOrigin: sourceTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
                    .isEmpty ? "user_text" : "user_dictation"
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

    func prepareEndingContinuityFromApprovedScript() async {
        guard let episodeID = selectedEpisodeID else { return }
        do {
            let proposal = try await runtime.continuityExtractionProposal(
                episodeID: episodeID
            )
            guard selectedEpisodeID == episodeID else { return }
            continuityExtractionProposal = proposal
            endingContinuityDraft = ContinuityFormDraft(
                state: proposal.state,
                unresolvedHooks: proposal.unresolvedHooks
            )
            reviewedContinuityExtractionHash = nil
            isReadingEndingContinuity = false
            continuityExtractionChangeSummary = ""
            let response = "我已经从第 \(proposal.scriptRevision) 版定稿剧本整理好结尾草稿。请先按朗读核对；没有听完或内容有变化时，我不会替您确认。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func confirmExtractedEndingContinuity(
        confirmation: String = "我确认这份本集结尾交接卡",
        reviewChannel: String = "voice_and_visual"
    ) async {
        guard let episodeID = selectedEpisodeID,
              let proposal = continuityExtractionProposal else { return }
        guard reviewedContinuityExtractionHash == proposal.proposalSHA256 else {
            errorMessage = "请先朗读并核对这份结尾草稿；修改后需要重新朗读。"
            return
        }
        let changeSummary = continuityExtractionChangeSummary.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        guard !continuityExtractionWasEdited || !changeSummary.isEmpty else {
            errorMessage = "修改了整理结果时，请简单说明改了什么。"
            return
        }
        do {
            _ = try await runtime.confirmContinuityExtraction(
                episodeID: episodeID,
                draft: ContinuityExtractionConfirmationDraft(
                    reviewedScriptRevision: proposal.scriptRevision,
                    proposalSHA256: proposal.proposalSHA256,
                    reviewedState: endingContinuityDraft.state,
                    unresolvedHooks: endingContinuityDraft.hooks,
                    confirmedBy: "local-user",
                    spokenConfirmation: confirmation,
                    reviewChannel: reviewChannel,
                    guardianApproval: guardianConfirmedForScript,
                    changeSummary: changeSummary
                )
            )
            await loadContinuity(episodeID: episodeID)
            let response = "您核对过的本集结尾已经保存为不可变交接卡，下一集只会继承这份确认结果。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
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
        var hookReview: ContinuityHookReviewDraft?
        if let inherited = inheritedContinuity, !inherited.unresolvedHooks.isEmpty {
            let confirmation = continuityHookConfirmation.trimmingCharacters(
                in: .whitespacesAndNewlines
            )
            let validDispositions = Set(["carry_forward", "resolved", "abandoned"])
            guard continuityHookResolutions.count == inherited.unresolvedHooks.count,
                  Set(continuityHookResolutions.map(\.hook)) == Set(inherited.unresolvedHooks),
                  continuityHookResolutions.allSatisfy({ resolution in
                      validDispositions.contains(resolution.disposition)
                          && (resolution.disposition == "carry_forward"
                              || !resolution.explanation.trimmingCharacters(
                                  in: .whitespacesAndNewlines
                              ).isEmpty)
                  }),
                  confirmation.contains("我确认") || confirmation.contains("我同意") else {
                errorMessage = "请逐个选择悬念是继续保留、本集解决或不再继续；解决或放弃时要说明原因，最后明确说或输入“我确认”。"
                return
            }
            hookReview = ContinuityHookReviewDraft(
                inheritedSnapshotID: inherited.id,
                resolutions: continuityHookResolutions,
                reviewedBy: "local-user",
                spokenConfirmation: confirmation,
                guardianApproval: guardianConfirmedForScript
            )
        }
        let draft = ContinuityPreflightDraft(
            openingState: openingContinuityDraft.state,
            transitionExplanations: explanations,
            override: override,
            hookReview: hookReview
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

    func updateHookResolution(
        hook: String, disposition: String? = nil, explanation: String? = nil
    ) {
        guard let index = continuityHookResolutions.firstIndex(where: { $0.hook == hook }) else {
            return
        }
        if let disposition { continuityHookResolutions[index].disposition = disposition }
        if let explanation { continuityHookResolutions[index].explanation = explanation }
        continuityHookConfirmation = ""
        continuityPreflightResult = nil
        acceptedContinuityDraft = nil
    }

    func updateHookConfirmation(_ confirmation: String) {
        continuityHookConfirmation = confirmation
        continuityPreflightResult = nil
        acceptedContinuityDraft = nil
    }

    func beginHookVoiceReview(startLocalCapture: Bool = true) async {
        guard !continuityHookResolutions.isEmpty else { return }
        continuityHookConfirmation = ""
        hookReviewShouldCapture = startLocalCapture
        hookReviewVoiceStep = .disposition(0)
        presentHookVoicePrompt(hookDispositionPrompt(at: 0))
        if startLocalCapture, !isListening { await toggleListening() }
    }

    private func handleHookReviewVoiceAnswer(
        _ spoken: String, step: HookReviewVoiceStep
    ) {
        switch step {
        case .disposition(let index):
            let disposition: String?
            if ["继续", "保留", "后面", "下一集"].contains(where: spoken.contains) {
                disposition = "carry_forward"
            } else if ["解决", "揭晓", "打开", "交代"].contains(where: spoken.contains) {
                disposition = "resolved"
            } else if ["放弃", "删除", "不再继续", "不要了"].contains(where: spoken.contains) {
                disposition = "abandoned"
            } else {
                presentHookVoicePrompt("我没有听清选择。请说：继续保留、本集解决，或者不再继续。")
                restartHookVoiceCapture()
                return
            }
            let hook = continuityHookResolutions[index].hook
            updateHookResolution(hook: hook, disposition: disposition)
            if disposition == "carry_forward" {
                advanceHookVoice(after: index)
            } else {
                hookReviewVoiceStep = .explanation(index)
                presentHookVoicePrompt(
                    disposition == "resolved"
                        ? "请告诉我，这个悬念在本集怎样解决？"
                        : "请告诉我，为什么决定不再继续这个悬念？"
                )
            }
        case .explanation(let index):
            let hook = continuityHookResolutions[index].hook
            updateHookResolution(hook: hook, explanation: spoken)
            advanceHookVoice(after: index)
        case .confirmation:
            if ["不确认", "不同意", "还要改", "取消"].contains(where: spoken.contains) {
                hookReviewVoiceStep = .disposition(0)
                continuityHookConfirmation = ""
                presentHookVoicePrompt("好的，没有确认。我们从第一个悬念重新核对。" + hookDispositionPrompt(at: 0))
            } else if spoken.contains("我确认") || spoken.contains("我同意") {
                if selectedProject?.audienceMode == "child" && !guardianConfirmedForScript {
                    hookReviewVoiceStep = nil
                    hookReviewShouldCapture = false
                    presentHookVoicePrompt("这是儿童项目。监护人没有确认在场，我不会保存这份悬念安排。")
                    return
                }
                updateHookConfirmation(spoken)
                hookReviewVoiceStep = nil
                hookReviewShouldCapture = false
                presentHookVoicePrompt("悬念安排已经由您确认。现在可以检查本集开场。")
                return
            } else {
                presentHookVoicePrompt("为了避免误操作，请明确说：我确认这份悬念安排；或者说：不确认。")
            }
        }
        restartHookVoiceCapture()
    }

    private func advanceHookVoice(after index: Int) {
        let next = index + 1
        if next < continuityHookResolutions.count {
            hookReviewVoiceStep = .disposition(next)
            presentHookVoicePrompt(hookDispositionPrompt(at: next))
        } else {
            hookReviewVoiceStep = .confirmation
            presentHookVoicePrompt(
                hookReviewSpeechSummary()
                    + "如果都正确，请明确说：我确认这份悬念安排。"
            )
        }
    }

    private func hookDispositionPrompt(at index: Int) -> String {
        let hook = continuityHookResolutions[index].hook
        return "上一集留下的悬念是：\(hook)。这一集要继续保留、本集解决，还是不再继续？"
    }

    private func presentHookVoicePrompt(_ prompt: String) {
        messages.append(.init(speaker: .nalu, text: prompt))
        speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
    }

    private func restartHookVoiceCapture() {
        guard hookReviewShouldCapture else { return }
        Task { if !isListening { await toggleListening() } }
    }

    func speakHookReview() {
        guard !continuityHookResolutions.isEmpty else { return }
        speechPlayback.speak(
            hookReviewSpeechSummary(), rate: comfortPreferences.speechRate
        )
    }

    private func hookReviewSpeechSummary() -> String {
        let parts = continuityHookResolutions.map { resolution in
            let action: String
            switch resolution.disposition {
            case "resolved": action = "本集解决"
            case "abandoned": action = "审阅后不再继续"
            case "carry_forward": action = "继续留到后面"
            default: action = "还没有选择"
            }
            let reason = resolution.explanation.isEmpty
                ? "" : "，说明是\(resolution.explanation)"
            return "悬念，\(resolution.hook)，安排为\(action)\(reason)"
        }
        return "请核对上一集留下的悬念。" + parts.joined(separator: "。") + "。"
    }

    func speakEndingContinuity() {
        let summary = continuitySpeechSummary(endingContinuityDraft, prefix: "本集结尾")
        guard let proposal = continuityExtractionProposal else {
            speechPlayback.speak(summary, rate: comfortPreferences.speechRate)
            return
        }
        reviewedContinuityExtractionHash = nil
        isReadingEndingContinuity = true
        let reviewedDraft = endingContinuityDraft
        speechPlayback.speak(
            summary,
            rate: comfortPreferences.speechRate
        ) { [weak self] completed in
            guard let self else { return }
            self.completeEndingContinuityReadback(
                proposalSHA256: proposal.proposalSHA256,
                reviewedDraft: reviewedDraft,
                completed: completed
            )
        }
    }

    func completeEndingContinuityReadback(
        proposalSHA256: String,
        reviewedDraft: ContinuityFormDraft,
        completed: Bool
    ) {
        isReadingEndingContinuity = false
        guard completed,
              continuityExtractionProposal?.proposalSHA256 == proposalSHA256,
              endingContinuityDraft == reviewedDraft else { return }
        reviewedContinuityExtractionHash = proposalSHA256
        messages.append(
            .init(
                speaker: .nalu,
                text: "朗读完成。如果内容正确，请确认并保存交接卡；发现错误可以修改，改后我会重新朗读。"
            )
        )
    }

    func invalidateEndingContinuityReadback() {
        reviewedContinuityExtractionHash = nil
        isReadingEndingContinuity = false
        speechPlayback.stop()
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
            if !character.heldProps.isEmpty { detail += "，拿着 \(character.heldProps)" }
            if !character.relationships.isEmpty {
                detail += "，人物关系是 \(character.relationships)"
            }
            if !character.revealedFacts.isEmpty {
                detail += "，已经知道 \(character.revealedFacts)"
            }
            parts.append(detail)
        }
        for prop in draft.props where !prop.name.isEmpty {
            var detail = "道具 \(prop.name)"
            if !prop.owner.isEmpty { detail += "属于 \(prop.owner)" }
            if !prop.location.isEmpty { detail += "，在 \(prop.location)" }
            if !prop.condition.isEmpty { detail += "，状态是 \(prop.condition)" }
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
                memoryConflictReports = [:]
                libraryEntities = []
                publicationLearning = []
                publicationLearningWarning = nil
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

    func restoreProject(from data: Data) async -> Bool {
        do {
            let project = try await runtime.restoreProject(data: data)
            includeArchivedProjects = project.archivedAt != nil
            await reloadProjects()
            await selectProject(project.id)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
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
            let card = try await runtime.createMemoryCard(
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
            memoryIntakeCardID = card.id
            memoryIntakeStep = .description
            let response = "资料已复制到本机。我先按“只供理解和核对”建好草稿，没有替您同意人脸或声音生成。请告诉我，这份资料里发生了什么？"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
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

    func speakMemoryConflict(_ memoryID: String) {
        guard let report = memoryConflictReports[memoryID], report.blocking else { return }
        messages.append(.init(speaker: .nalu, text: report.spokenSummary))
        speechPlayback.speak(report.spokenSummary, rate: comfortPreferences.speechRate)
    }

    func beginMemoryCorrection(_ memoryID: String) async {
        memoryIntakeCardID = nil
        memoryIntakeStep = nil
        memoryCorrectionCardID = memoryID
        memoryConfirmationCardID = nil
        let response = "请说要修改哪一项，例如：地点不是西湖，是灵隐寺；或者年份改成一九八零年。"
        messages.append(.init(speaker: .nalu, text: response))
        speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        if !isListening { await toggleListening() }
    }

    func beginMemoryVoiceConfirmation(_ memoryID: String) async {
        memoryIntakeCardID = nil
        memoryIntakeStep = nil
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
            let report = try await runtime.memoryGraphConflicts(memoryID: memoryID)
            memoryConflictReports[memoryID] = report
            if report.blocking {
                messages.append(.init(speaker: .nalu, text: report.spokenSummary))
                speechPlayback.speak(report.spokenSummary, rate: comfortPreferences.speechRate)
                return
            }
            _ = try await runtime.confirmMemoryCard(id: memoryID, revision: card.currentRevision)
            memoryCards = try await runtime.listMemoryCards(projectID: projectID)
            memoryConflictReports.removeValue(forKey: memoryID)
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
        changeSummary: String = "用户在本机修改记忆卡",
        announceReview: Bool = true
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
            memoryConflictReports.removeValue(forKey: id)
            await refreshDocumentaryReadiness()
            reviewedMemoryCardIDs.remove(id)
            if announceReview {
                let response = "修改已保存为新版本。请重新听我朗读，再确认归档。"
                messages.append(.init(speaker: .nalu, text: response))
                speechPlayback.speak(response, rate: comfortPreferences.speechRate)
            }
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
        let generation = projectSelectionGeneration
        guard let projectID = selectedProjectID,
              selectedProject?.creativeFormat == "documentary_series" else {
            documentaryReadiness = nil
            return
        }
        do {
            let readiness = try await runtime.documentaryReadiness(
                projectID: projectID
            )
            guard projectSelectionGeneration == generation else { return }
            documentaryReadiness = readiness
        } catch {
            guard projectSelectionGeneration == generation else { return }
            errorMessage = error.localizedDescription
        }
    }

    private func handleMemoryIntakeAnswer(
        _ spoken: String,
        memoryID: String,
        step: MemoryIntakeStep
    ) {
        guard let card = memoryCards.first(where: { $0.id == memoryID }) else {
            memoryIntakeCardID = nil
            memoryIntakeStep = nil
            return
        }
        let answer = ["不知道", "记不清", "不清楚"].contains(where: spoken.contains)
            ? "" : spoken
        var description = card.description
        var date = card.approximateDate
        var place = card.place
        var relevance = card.storyRelevance
        switch step {
        case .description: description = answer
        case .approximateDate: date = answer
        case .place: place = answer
        case .storyRelevance: relevance = answer
        }

        Task {
            let saved = await updateMemoryCard(
                id: memoryID,
                title: card.title,
                description: description,
                approximateDate: date,
                place: place,
                storyRelevance: relevance,
                allowedUse: card.allowedUse,
                sourceChannel: "voice",
                changeSummary: "Nalu 语音建档：\(spoken)",
                announceReview: false
            )
            guard saved else { return }
            let next: MemoryIntakeStep?
            let prompt: String?
            switch step {
            case .description:
                next = .approximateDate
                prompt = "好的。大约是什么时候？记不清可以直接说记不清。"
            case .approximateDate:
                next = .place
                prompt = "这份资料和哪个地方有关？不知道也可以直接说不知道。"
            case .place:
                next = .storyRelevance
                prompt = "最后一个问题：为什么这份资料对您的故事重要？"
            case .storyRelevance:
                next = nil
                prompt = nil
            }
            memoryIntakeStep = next
            if let prompt {
                messages.append(.init(speaker: .nalu, text: prompt))
                speechPlayback.speak(prompt, rate: comfortPreferences.speechRate)
            } else {
                memoryIntakeCardID = nil
                speakMemoryCard(memoryID)
            }
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
        guard let projectID = selectedProjectID,
              assets.contains(where: { $0.id == assetID && $0.projectID == projectID }) else { return }
        let generation = projectSelectionGeneration
        do {
            try await runtime.deleteAsset(assetID: assetID)
            guard projectSelectionGeneration == generation else { return }
            let refreshedAssets = try await runtime.listAssets(projectID: projectID)
            guard projectSelectionGeneration == generation else { return }
            let refreshedCards = try await runtime.listMemoryCards(projectID: projectID)
            guard projectSelectionGeneration == generation else { return }
            assets = refreshedAssets
            memoryCards = refreshedCards
            await refreshDocumentaryReadiness()
            guard projectSelectionGeneration == generation else { return }
            messages.append(.init(speaker: .nalu, text: "本地素材和素材记录已经删除。"))
        } catch {
            guard projectSelectionGeneration == generation else { return }
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
        case .confirmContinuity(let confirmation):
            messages.append(.init(speaker: .nalu, text: "我听到了明确确认，正在保存结尾交接卡。"))
            Task {
                await confirmExtractedEndingContinuity(
                    confirmation: confirmation, reviewChannel: "voice"
                )
            }
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
        if let routed = AssistantActionRouter.route(answer) {
            let protected: Bool
            if case .requiresConfirmation = routed { protected = true } else { protected = false }
            return RealtimeInterviewToolResult(
                accepted: false,
                message: protected
                    ? "这个要求需要可见确认，我没有把它当成采访答案，也没有执行。"
                    : "这是一项联网查找，不是采访答案。请改用只读联网工具。",
                nextPrompt: currentInterviewPrompt,
                requiresVisibleConfirmation: protected
            )
        }
        if let response = handleProductionVoiceCommand(answer) {
            return RealtimeInterviewToolResult(
                accepted: true,
                message: response,
                nextPrompt: currentInterviewPrompt,
                requiresVisibleConfirmation: false
            )
        }
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

    func performRealtimeWebResearch(_ query: String) async -> RealtimeInterviewToolResult {
        guard !AssistantActionRouter.requiresConfirmation(query) else {
            return .init(
                accepted: false,
                message: "这个要求包含下载、登录、付款、发布或其他外部改变，我没有执行。请回到可见界面确认具体操作。",
                nextPrompt: currentInterviewPrompt,
                requiresVisibleConfirmation: true
            )
        }
        guard assistantActionStatus == nil else {
            return .init(
                accepted: false,
                message: "上一项联网查找仍在进行，请等结果出现后再试。",
                nextPrompt: currentInterviewPrompt,
                requiresVisibleConfirmation: false
            )
        }
        assistantActionStatus = "正在替您上网查找…"
        defer { assistantActionStatus = nil }
        do {
            let result = try await webResearch.research(query)
            let visibleResult = result.conversationText(resumePrompt: currentInterviewPrompt)
            messages.append(.init(speaker: .nalu, text: visibleResult))
            return .init(
                accepted: true,
                message: "已经完成只读联网查找，详细结果和来源显示在对话中。\(result.answer) 我们再接着刚才的创作。",
                nextPrompt: currentInterviewPrompt,
                requiresVisibleConfirmation: false
            )
        } catch {
            return .init(
                accepted: false,
                message: WebResearchError.publicDescription(for: error),
                nextPrompt: currentInterviewPrompt,
                requiresVisibleConfirmation: error is WebResearchError
            )
        }
    }

    private func recordRealtimePlanningAnswer(_ answer: String) -> RealtimeInterviewToolResult {
        let guardianConfirmed = planningVoiceFlow.mode == .scriptApproval
            || planningVoiceFlow.mode == .continuityConfirmation
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
        case .confirmContinuity(let confirmation):
            Task {
                await confirmExtractedEndingContinuity(
                    confirmation: confirmation, reviewChannel: "voice_and_visual"
                )
            }
            return .init(
                accepted: true,
                message: "已收到明确确认，正在保存结尾交接卡；最终以界面状态为准。",
                nextPrompt: "要继续下一集，还是再查看本集结尾？",
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
        if let prompt = planningVoiceFlow.mode?.prompt { return prompt }
        if selectedProjectID != nil, interviewFlow.step == .idle {
            return "您可以继续讲故事，或告诉我想用哪份资料来编写这一集。"
        }
        return interviewFlow.prompt
    }

    private func handleAssistantAction(_ request: AssistantActionRequest, turnID: String = UUID().uuidString) {
        switch request {
        case .requiresConfirmation(let description):
            if AssistantActionRouter.requestsNovelImport(description),
               AssistantActionRouter.sourceURL(in: description) != nil {
                handleAssistantAction(.webResearch(query: description), turnID: turnID)
                return
            }
            let response = "我先帮您查找公开来源。下载整份资料、登录、购买或发布会另行确认，不影响现在先查找。"
            messages.append(.init(speaker: .nalu, text: response))
            handleAssistantAction(.webResearch(query: description), turnID: turnID)
        case .webResearch(let query):
            guard assistantActionStatus == nil else {
                queueStorySupplement(query, turnID: turnID, sourceMode: "web_source")
                return
            }
            assistantActionStatus = "正在替您上网查找…"
            let novelImportRequested = AssistantActionRouter.requestsNovelImport(query)
                && AssistantActionRouter.sourceURL(in: query) != nil
            let startMessage = novelImportRequested
                ? "好的，我按您提供的网址识别小说目录，把可访问的章节保存到这台 Mac。不会购买或发布。"
                : "好的，我现在替您上网查找。查找期间不会改变您的故事，也不会自动下载或发布任何内容。"
            messages.append(.init(speaker: .nalu, text: startMessage))
            speechPlayback.speak(startMessage, rate: comfortPreferences.speechRate)
            let resumePrompt = selectedProjectID == nil
                ? "您想采用哪份来源？也可以继续讲故事，我们把内容整理成分集剧本。"
                : currentInterviewPrompt
            let originalProjectID = selectedProjectID
            let originalGeneration = projectSelectionGeneration
            Task {
                var projectID = originalProjectID
                var generation = originalGeneration
                var savedRevision: Int?
                defer {
                    Task { await drainStorySupplements(projectID: projectID, generation: generation) }
                }
                do {
                    if projectID == nil {
                        var draft = ProjectDraft()
                        draft.title = "资料故事"
                        let created = try await runtime.createProject(draft)
                        guard projectSelectionGeneration == originalGeneration else {
                            assistantActionStatus = nil
                            return
                        }
                        projects = try await runtime.listProjects(includeArchived: includeArchivedProjects)
                        await selectProject(created.id)
                        projectID = created.id
                        generation = projectSelectionGeneration
                        messages.append(.init(speaker: .user, text: query))
                    }
                    if let projectID {
                        let state = try await runtime.interactiveStory(projectID: projectID)
                        if let waiting = state.queued_inputs, !waiting.isEmpty,
                           !waiting.contains(where: { $0.turn_id == turnID }) {
                            var input = InteractiveStoryInput(turn_id: turnID, expected_revision: state.revision,
                                text: query, source_mode: "web_source")
                            input.queue_only = true
                            _ = try await runtime.appendStoryInput(projectID: projectID, input: input)
                            assistantActionStatus = nil
                            return
                        }
                        let saved = try await runtime.appendStoryInput(
                            projectID: projectID,
                            input: InteractiveStoryInput(
                                turn_id: turnID, expected_revision: state.revision,
                                text: query, source_mode: "web_source"
                            )
                        )
                        savedRevision = saved.revision
                    }
                    let result: WebResearchResult
                    var sourceWritingReady = !novelImportRequested
                    if novelImportRequested, let sourceURL = AssistantActionRouter.sourceURL(in: query), let projectID {
                        guard let catalogURL = URL(string: sourceURL) else { throw WebResearchError.invalidResponse }
                        var imported = try await runtime.startNovelImport(projectID: projectID, sourceURL: sourceURL)
                        while imported.status == "ready" {
                            guard projectSelectionGeneration == generation, !Task.isCancelled else {
                                assistantActionStatus = nil
                                return
                            }
                            assistantActionStatus = imported.progressText
                            imported = try await runtime.fetchNextNovelChapter(projectID: projectID)
                            if imported.status == "ready" {
                                try await Task.sleep(for: .seconds(1))
                            }
                        }
                        let ending = imported.status == "complete"
                            ? "本次识别到的章节已保存；尚未核实是否覆盖全书，也没有自动生成或批准剧本。"
                            : "本次导入暂停或未完成，已保存章节保留，不会从头重复下载。"
                        sourceWritingReady = imported.status == "complete"
                        result = WebResearchResult(answer: imported.progressText + "。" + ending,
                            sources: [.init(title: "小说目录", url: catalogURL)])
                    } else if let sourceURL = AssistantActionRouter.sourceURL(in: query), let projectID {
                        let source = try await runtime.readSourceText(projectID: projectID, url: sourceURL)
                        guard let url = URL(string: source.url) else { throw WebResearchError.invalidResponse }
                        result = WebResearchResult(
                            answer: "已读取这个网页的文字节选（不是整本书，也未确认改编授权）：\n" + String(source.text.prefix(8000)),
                            sources: [.init(title: "用户指定网页", url: url)])
                    } else {
                        result = try await webResearch.research(query)
                    }
                    let response = result.conversationText(resumePrompt: resumePrompt)
                    if let projectID, let savedRevision {
                        _ = try await runtime.saveStoryAnswer(
                            projectID: projectID, turnID: turnID,
                            answer: InteractiveStoryAnswerRequest(
                                expected_revision: savedRevision, reply: response,
                                summary: "", episode_drafts: [], outcome: "answered"
                            )
                        )
                    }
                    assistantActionStatus = nil
                    guard projectSelectionGeneration == generation else { return }
                    messages.append(.init(speaker: .nalu, text: response))
                    if AssistantActionRouter.requestsSourceWriting(query) && sourceWritingReady {
                        // Continue the user's existing writing request with the persisted
                        // source context, without routing it back through web search.
                        handleInteractiveStoryInput(query)
                        return
                    }
                    speechPlayback.speak(
                        "我查到了。\(result.answer) 我们再接着刚才的创作。\(resumePrompt)",
                        rate: comfortPreferences.speechRate
                    )
                } catch {
                    if let projectID, let savedRevision {
                        _ = try? await runtime.saveStoryAnswer(
                            projectID: projectID, turnID: turnID,
                            answer: InteractiveStoryAnswerRequest(
                                expected_revision: savedRevision,
                                reply: "这次查找尚未完成。原有故事和剧本保留；可以提供网址、资料文字，或继续讲述。",
                                summary: "", episode_drafts: [], outcome: "lookup_failed"
                            )
                        )
                    }
                    assistantActionStatus = nil
                    guard projectSelectionGeneration == generation else { return }
                    let response = "这次查找尚未完成，您的故事没有清空。您可以把网址或资料文字给我，也可以继续讲述；不需要新建项目。"
                    messages.append(.init(speaker: .nalu, text: response))
                    speechPlayback.speak(response, rate: comfortPreferences.speechRate)
                }
            }
        }
    }

    private func handleProductionVoiceCommand(_ spoken: String) -> String? {
        guard let command = ProductionVoiceCommandParser.parse(
            spoken,
            awaitingPauseConfirmation: pendingVoiceRunCancellationID != nil
        ) else { return nil }

        switch command {
        case .requestStart:
            guard let episodeID = selectedEpisodeID,
                  let episode = episodes.first(where: { $0.id == episodeID }),
                  let seasonID = episode.seasonID,
                  let revision = episode.approvedScriptRevision else {
                return "请先选择这一集并确认剧本，再说“开始本集制作”。您的故事和草稿都保留着。"
            }
            guard productionRunActionInProgress == nil else {
                return "正在处理这次制作请求，请稍等，不会重复提交。"
            }
            productionRunActionInProgress = episodeID
            let generation = projectSelectionGeneration
            Task {
                defer { productionRunActionInProgress = nil }
                do {
                    let run = try await runtime.prepareEpisodeProduction(
                        episodeID: episodeID, approvedRevision: revision)
                    guard generation == projectSelectionGeneration else { return }
                    await refreshProductionProgress(seasonID: seasonID)
                    let reply = run.error == nil
                        ? "本集制作准备已有结果，请看制作进度。现在还没有生成视频或扣费；实际生成需要确认费用。"
                        : "本集制作准备遇到问题，请看制作进度中的原因。剧本保留，没有扣费。"
                    messages.append(.init(speaker: .nalu, text: reply))
                    speechPlayback.speak(reply, rate: comfortPreferences.speechRate)
                } catch {
                    guard generation == projectSelectionGeneration else { return }
                    errorMessage = error.localizedDescription
                    messages.append(.init(speaker: .nalu, text: "这次制作准备尚未确认成功，剧本没有丢失，也没有提交付费生成。请查看错误提示。"))
                }
            }
            return "开始检查本集剧本和制作素材，暂不扣费。"
        case .requestPause:
            guard let progress = selectedEpisodeProductionProgress else {
                return "这一集还没有正在运行的制作任务。采访进度没有改变。"
            }
            guard progress.canCancel, let runID = progress.runID else {
                if progress.stage == "charge_reconciliation" {
                    return "现在正在核对是否扣费，不能暂停，也绝不会自动重复提交。核对清楚后我会告诉您。"
                }
                return "当前步骤不能安全暂停。我没有改动制作状态。"
            }
            pendingVoiceRunCancellationID = runID
            return "可以暂停，已有进度会保留。请再明确说一次“确认暂停本集制作”；如果不想暂停，请说“不暂停”。"
        case .confirmPause:
            guard let runID = pendingVoiceRunCancellationID else {
                return "现在没有等待确认的暂停操作。"
            }
            pendingVoiceRunCancellationID = nil
            Task { await cancelProductionRun(runID: runID) }
            return "收到明确确认，正在安全暂停；请以界面状态变为“已安全暂停”为准。"
        case .cancelPause:
            pendingVoiceRunCancellationID = nil
            return "好的，不暂停，制作继续。"
        case .clarifyPause:
            return "我还没有暂停。要暂停请说“确认暂停本集制作”；不暂停请说“不暂停”。"
        case .requestResume:
            guard let progress = selectedEpisodeProductionProgress,
                  progress.canResume,
                  let runID = progress.runID else {
                return "这一集现在没有可以恢复的制作任务。我没有提交任何付费操作。"
            }
            Task { await resumeProductionRun(runID: runID) }
            return "正在从安全检查恢复；任何可能产生费用的提交仍要等您再次确认。"
        }
    }

    private var selectedEpisodeProductionProgress: EpisodeProductionProgress? {
        guard let selectedEpisodeID else { return nil }
        return episodeProgressByID[selectedEpisodeID]
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
        try? ComfortPreferencesStore.save(comfortPreferences)
    }

    private static func loadComfortPreferences() -> ComfortPreferences {
        ComfortPreferencesStore.load()
    }

    private var selectedProject: NaluProject? {
        projects.first { $0.id == selectedProjectID }
    }
}
