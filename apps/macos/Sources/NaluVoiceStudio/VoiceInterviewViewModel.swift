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
    var selectedProjectID: String?
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
    private var hookReviewVoiceStep: HookReviewVoiceStep?
    private var hookReviewShouldCapture = false
    var draftProjectID: String?
    var feedbackDraftText = ""
    var isCapturingFeedback = false
    var feedbackWasDictated = false
    var feedbackReleaseReadiness: FeedbackGovernedReleaseReadiness?
    var comfortPreferences = VoiceInterviewViewModel.loadComfortPreferences()
    var planningVoiceLabel: String? { planningVoiceFlow.mode?.prompt }

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

    private let runtime = RuntimeClient()
    private let speech = SpeechRecorder()
    private let speechPlayback = SpeechPlayback()
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
            libraryEntities = try await runtime.listLibraryEntities(projectID: projectID)
            let response = "已确认\(entity.current.name)。以后每一集都会继承这个版本，修改时会另存新版本。"
            messages.append(.init(speaker: .nalu, text: response))
            speechPlayback.speak(response, rate: comfortPreferences.speechRate)
        } catch {
            errorMessage = error.localizedDescription
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
            let entityID = libraryIntakeEntityID
            libraryIntakeEntityID = nil
            libraryIntakeStep = nil
            guard spoken.contains("我确认") || spoken.contains("我同意") else {
                let response = "没有听到明确确认，所以这份设定仍是草稿，不会进入生产。"
                messages.append(.init(speaker: .nalu, text: response))
                speechPlayback.speak(response, rate: comfortPreferences.speechRate)
                return
            }
            if let entityID { Task { await confirmLibraryEntity(entityID, reviewChannel: "voice") } }
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
        selectedProjectID = projectID
        pendingVoiceRunCancellationID = nil
        memoryConflictReports = [:]
        publicationLearning = []
        publicationLearningWarning = nil
        do {
            assets = try await runtime.listAssets(projectID: projectID)
            memoryCards = try await runtime.listMemoryCards(projectID: projectID)
            libraryEntities = try await runtime.listLibraryEntities(projectID: projectID)
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
            await refreshPublicationLearning(projectID: projectID)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshPublicationLearning() async {
        guard let selectedProjectID else { return }
        await refreshPublicationLearning(projectID: selectedProjectID)
    }

    private func refreshPublicationLearning(projectID: String) async {
        publicationLearningIsLoading = true
        defer {
            if selectedProjectID == projectID { publicationLearningIsLoading = false }
        }
        do {
            let records = try await runtime.publicationLearning(projectID: projectID)
            guard selectedProjectID == projectID else { return }
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
            guard selectedProjectID == projectID else { return }
            publicationLearning = []
            publicationLearningWarning = "反馈记录暂时无法安全核验；没有触发发布、制作或付费操作。"
        }
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
        planningVoiceFlow.mode?.prompt ?? interviewFlow.prompt
    }

    private func handleProductionVoiceCommand(_ spoken: String) -> String? {
        guard let command = ProductionVoiceCommandParser.parse(
            spoken,
            awaitingPauseConfirmation: pendingVoiceRunCancellationID != nil
        ) else { return nil }

        switch command {
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
