import SwiftUI
import UniformTypeIdentifiers

private enum ContinuityEditorKind {
    case opening
    case ending
}

struct ContentView: View {
    @Environment(VoiceInterviewViewModel.self) private var model
    @State private var isRenamingProject = false
    @State private var renameTitle = ""
    @State private var isImportingProject = false
    @State private var isExportingProject = false
    @State private var exportDocument: ProjectBackupDocument?
    @State private var isScriptEditorExpanded = false
    @State private var isContinuityExpanded = false
    @State private var isLibraryEditorExpanded = false
    @State private var isContinuityOverrideExpanded = false
    @State private var isPresentingAssetEditor = false
    @State private var isImportingAsset = false
    @State private var isAutomaticAssetImport = true
    @State private var isAdvancedAssetEditorExpanded = false
    @State private var assetKind = "source_document"
    @State private var assetName = ""
    @State private var assetSubjectName = ""
    @State private var assetConsentGranted = false
    @State private var assetGuardianApproved = false
    @State private var assetConsentStatement = ""
    @State private var assetScope = "project"
    @State private var assetMemoryDescription = ""
    @State private var assetMemoryDate = ""
    @State private var assetMemoryPlace = ""
    @State private var assetMemoryRelationship = ""
    @State private var assetMemoryStoryRelevance = ""
    @State private var assetMemoryAllowedUse = "reference_only"
    @State private var isExportingPrivacy = false
    @State private var privacyDocument: PrivacyExportDocument?
    @State private var deletionPreview: ProjectDeletionPreview?
    @State private var isPresentingProjectDeletion = false
    @State private var projectDeletionConfirmation = ""
    @State private var deleteProductionSnapshots = false
    @State private var assetDependencyReport: AssetDependencyReport?
    @State private var isPresentingAssetDependencies = false
    @State private var isPresentingProviderCredentials = false
    @State private var seedanceSecretDraft = ""
    @State private var minimaxSecretDraft = ""
    @State private var openAIRealtimeSecretDraft = ""
    @State private var seedanceIsConfigured = false
    @State private var minimaxIsConfigured = false
    @State private var openAIRealtimeIsConfigured = false
    @State private var isPresentingFeedback = false
    @State private var feedbackCategory = "usability"
    @State private var feedbackShareAuthorized = false
    @State private var feedbackGuardianApproved = false
    @State private var isPresentingMemoryEditor = false
    @State private var editingMemoryID: String?
    @State private var editingMemoryTitle = ""
    @State private var editingMemoryDescription = ""
    @State private var editingMemoryDate = ""
    @State private var editingMemoryPlace = ""
    @State private var editingMemoryStoryRelevance = ""
    @State private var editingMemoryAllowedUse = "reference_only"
    @State private var realtimeVoice = RealtimeVoiceCoordinator()
    @State private var isPresentingRealtimeConsent = false
    @State private var realtimeCloudConsent = false
    @State private var realtimeGuardianConsent = false
    @State private var realtimeCredentialIsConfigured = false
    @State private var realtimeSessionLimitMinutes = 10
    @State private var runPendingCancelID: String?
    private let keychain = KeychainSecretStore()

    var body: some View {
        HSplitView {
            sidebar.frame(minWidth: 260, idealWidth: 290, maxWidth: 340)
            interview
        }
        .dynamicTypeSize(preferredDynamicTypeSize)
        .task {
            do {
                try await RuntimeSupervisor.shared.start()
            } catch {
                model.runtimeStatus = "本窗口未连接本地制片厂"
                model.errorMessage = error.localizedDescription
                return
            }
            await model.load()
            do {
                try NativeConversationQAScenario.installIfRequested(on: model)
            } catch {
                model.errorMessage = error.localizedDescription
            }
        }
        .task(id: selectedSeason?.id) {
            guard let seasonID = selectedSeason?.id else { return }
            while !Task.isCancelled {
                await model.refreshProductionProgress(seasonID: seasonID)
                do {
                    try await Task.sleep(for: .seconds(4))
                } catch {
                    return
                }
            }
        }
        .task {
            while !Task.isCancelled {
                await model.refreshStorageDiagnostics()
                do {
                    try await Task.sleep(for: .seconds(60))
                } catch {
                    return
                }
            }
        }
        .fileImporter(
            isPresented: $isImportingProject,
            allowedContentTypes: [.json],
            allowsMultipleSelection: false,
            onCompletion: importProject
        )
        .fileExporter(
            isPresented: $isExportingProject,
            document: exportDocument,
            contentType: .json,
            defaultFilename: exportFilename
        ) { result in
            if case .failure(let error) = result {
                model.errorMessage = error.localizedDescription
            }
        }
        .fileImporter(
            isPresented: $isImportingAsset,
            allowedContentTypes: allowedAssetContentTypes,
            allowsMultipleSelection: false,
            onCompletion: importAsset
        )
        .fileExporter(
            isPresented: $isExportingPrivacy,
            document: privacyDocument,
            contentType: .zip,
            defaultFilename: privacyExportFilename
        ) { result in
            if case .failure(let error) = result {
                model.errorMessage = error.localizedDescription
            }
        }
        .alert("给项目换个名字", isPresented: $isRenamingProject) {
            TextField("项目名称", text: $renameTitle)
            Button("取消", role: .cancel) {}
            Button("保存") {
                Task { await model.renameSelectedProject(to: renameTitle) }
            }
        } message: {
            Text("原来的分集、人物素材和制作记录都会保留。")
        }
        .sheet(isPresented: $isPresentingProjectDeletion) {
            projectDeletionSheet
        }
        .sheet(isPresented: $isPresentingProviderCredentials) {
            providerCredentialsSheet
        }
        .sheet(isPresented: $isPresentingFeedback) {
            feedbackSheet
        }
        .sheet(isPresented: $isPresentingMemoryEditor) {
            memoryEditorSheet
        }
        .sheet(isPresented: $isPresentingAssetEditor) {
            assetEditorSheet
        }
        .sheet(isPresented: $isPresentingRealtimeConsent) {
            realtimeConsentSheet
        }
        .alert("删除素材前的依赖检查", isPresented: $isPresentingAssetDependencies) {
            Button("取消", role: .cancel) { assetDependencyReport = nil }
            if assetDependencyReport?.canDelete == true,
               let assetID = assetDependencyReport?.assetID {
                Button("删除本地素材", role: .destructive) {
                    Task { await model.deleteAsset(assetID) }
                }
            }
        } message: {
            Text(assetDependencyMessage)
        }
        .confirmationDialog(
            "暂停这一集的制作？",
            isPresented: Binding(
                get: { runPendingCancelID != nil },
                set: { if !$0 { runPendingCancelID = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("安全暂停", role: .destructive) {
                guard let runID = runPendingCancelID else { return }
                runPendingCancelID = nil
                Task { await model.cancelProductionRun(runID: runID) }
            }
            Button("继续制作", role: .cancel) { runPendingCancelID = nil }
        } message: {
            Text("进度和已有结果都会保留。计费状态不明确时，Nalu 不会提供暂停按钮。")
        }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("Nalu 语音短剧工坊", systemImage: "waveform.circle.fill")
                .font(.title2.bold())
                .padding(.top, 22)
                .padding(.horizontal, 18)
            Text("我的短剧项目")
                .font(.headline)
                .padding(.horizontal, 18)
            List(model.projects) { project in
                Button {
                    Task { await model.selectProject(project.id) }
                } label: {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(project.title).font(.headline)
                        Text(projectSummary(project))
                            .foregroundStyle(.secondary)
                        if project.archivedAt != nil {
                            Label("已归档", systemImage: "archivebox")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .buttonStyle(.plain)
                .padding(.vertical, 5)
            }
            Toggle("显示已归档项目", isOn: archivedProjectsBinding)
                .toggleStyle(.switch)
                .padding(.horizontal, 18)
            HStack(spacing: 10) {
                Button("改名", systemImage: "pencil", action: presentRename)
                    .disabled(selectedProject == nil)
                Button("备份", systemImage: "square.and.arrow.up", action: exportProject)
                    .disabled(selectedProject == nil)
                Button("恢复", systemImage: "square.and.arrow.down") {
                    isImportingProject = true
                }
            }
            .controlSize(.large)
            .padding(.horizontal, 18)
            Button("隐私包", systemImage: "lock.doc", action: exportPrivacy)
                .controlSize(.large)
                .padding(.horizontal, 18)
                .disabled(selectedProject == nil)
            Button("模型密钥", systemImage: "key") {
                presentProviderCredentials()
            }
            .controlSize(.large)
            .padding(.horizontal, 18)
            Button("告诉 Nalu 哪里不好用", systemImage: "bubble.left.and.exclamationmark.bubble.right") {
                isPresentingFeedback = true
            }
            .controlSize(.large)
            .padding(.horizontal, 18)
            HStack {
                Button("字大一点", systemImage: "textformat.size.larger") {
                    model.makeTextLarger()
                }
                Button("恢复字号", systemImage: "arrow.counterclockwise") {
                    model.resetComfortPreferences()
                }
            }
            .controlSize(.large)
            .padding(.horizontal, 18)
            if let project = selectedProject {
                Button(
                    project.archivedAt == nil ? "归档这个项目" : "移回项目列表",
                    systemImage: project.archivedAt == nil ? "archivebox" : "tray.and.arrow.up"
                ) {
                    Task { await model.setSelectedProjectArchived(project.archivedAt == nil) }
                }
                .controlSize(.large)
                .padding(.horizontal, 18)
                Button("彻底删除这个项目", systemImage: "trash", role: .destructive) {
                    prepareProjectDeletion()
                }
                .controlSize(.large)
                .padding(.horizontal, 18)
            }
            Button(action: beginProject) {
                Label("创建新项目", systemImage: "plus.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(18)
        }
    }

    private var interview: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading) {
                    Text("和 Nalu 讲故事").font(.title.bold())
                    RuntimeStatusBadge(status: model.runtimeStatus)
                    if let diagnostics = model.storageDiagnostics {
                        StorageStatusBadge(diagnostics: diagnostics)
                    }
                }
                Spacer()
                Button("选择家庭资料", systemImage: "photo.badge.plus") {
                    beginAutomaticAssetImport()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(selectedProject == nil)
                .accessibilityHint("直接打开文件选择器，资料名称和归档草稿由 Nalu 整理")
                Button("管理资料", systemImage: "tray.full") {
                    assetKind = "source_document"
                    isAdvancedAssetEditorExpanded = false
                    isPresentingAssetEditor = true
                }
                .controlSize(.large)
                .disabled(selectedProject == nil)
                Button(
                    realtimeVoice.state.isActive ? "结束自然语音" : "自然语音对话",
                    systemImage: realtimeVoice.state.isActive
                        ? "phone.down.fill" : "waveform.and.mic"
                ) {
                    if realtimeVoice.state.isActive {
                        realtimeVoice.stop()
                    } else {
                        presentRealtimeConsent()
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(realtimeVoice.state.isActive ? .red : .purple)
                .controlSize(.large)
                Button("再说一遍", action: repeatQuestion).controlSize(.large)
            }
            .padding(24)
            Divider()
            RealtimeWebRTCContainer(coordinator: realtimeVoice)
                .frame(width: 1, height: 1)
                .opacity(0.01)
                .accessibilityHidden(true)
            if realtimeVoice.state != .off {
                HStack(spacing: 12) {
                    if realtimeVoice.state.isActive {
                        ProgressView()
                            .controlSize(.small)
                            .accessibilityLabel("自然语音正在运行")
                    } else {
                        Image(systemName: realtimeVoice.state.systemImage)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(realtimeVoice.state.label).font(.headline)
                        if realtimeVoice.sessionStartedAt != nil {
                            Text(
                                "本次时长 " + RealtimeSessionLimit.elapsedLabel(
                                    seconds: realtimeVoice.sessionElapsedSeconds,
                                    limitMinutes: realtimeVoice.sessionLimitMinutes
                                )
                            )
                            .font(.caption.monospacedDigit())
                        }
                    }
                    Spacer()
                    if realtimeVoice.retryAllowed {
                        Button("重新连接", systemImage: "arrow.clockwise") {
                            Task { await realtimeVoice.retry() }
                        }
                        .controlSize(.large)
                    }
                }
                .foregroundStyle(realtimeVoice.state.isActive ? .purple : .orange)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 24)
                .padding(.vertical, 10)
                .background(Color.purple.opacity(0.07))
                Divider()
            }
            if let progress = selectedEpisodeProgress {
                ProductionProgressStatusView(
                    progress: progress,
                    lastRefreshedAt: model.productionProgressLastRefreshedAt,
                    refreshWarning: model.productionProgressRefreshWarning,
                    actionInProgress: model.productionRunActionInProgress == progress.runID,
                    mediaCheckInProgress: model.semanticMediaQARunInProgress == progress.runID,
                    mediaCheckStatus: progress.runID.flatMap {
                        model.semanticMediaQAStatusByRunID[$0]
                    },
                    onCancel: progress.runID.map { runID in
                        { runPendingCancelID = runID }
                    },
                    onResume: progress.runID.map { runID in
                        { Task { await model.resumeProductionRun(runID: runID) } }
                    },
                    onVerifyFinalMedia: progress.runID.map { runID in
                        { Task { await model.verifyFinalMaster(runID: runID) } }
                    }
                )
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                Divider()
            }
            if selectedProject != nil {
                PublicationLearningView(
                    items: model.publicationLearning,
                    isLoading: model.publicationLearningIsLoading,
                    warning: model.publicationLearningWarning,
                    onReadLatest: model.speakLatestPublicationLearning,
                    onRefresh: { Task { await model.refreshPublicationLearning() } }
                )
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                Divider()
            }
            if selectedProject != nil {
                Button {
                    beginAutomaticAssetImport()
                } label: {
                    HStack(spacing: 14) {
                        Image(systemName: "photo.stack.fill")
                            .font(.title2)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("添加一张照片、手稿或家庭视频")
                                .font(.headline)
                            Text("Nalu 会陪您说明人物、时间和地点，再朗读给您确认归档")
                                .font(.body)
                                .opacity(0.9)
                        }
                        Spacer()
                        Image(systemName: "chevron.right.circle.fill")
                            .font(.title2)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .accessibilityHint("直接打开文件选择器，选择后 Nalu 会用语音逐项确认")
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                Divider()
            }
            if selectedProject != nil {
                DisclosureGroup(
                    "项目人物、场景、道具和声音",
                    isExpanded: $isLibraryEditorExpanded
                ) {
                    libraryEditor
                        .padding(.top, 10)
                }
                .font(.headline)
                .padding(.horizontal, 24)
                .padding(.vertical, 14)
                .background(Color.secondary.opacity(0.04))
                Divider()
            }
            if !model.episodes.isEmpty {
                ScrollView(.horizontal) {
                    HStack(spacing: 10) {
                        ForEach(model.episodes) { episode in
                            Button {
                                model.selectEpisode(episode.id)
                            } label: {
                                VStack(alignment: .leading, spacing: 5) {
                                    Text("第 \(episode.episodeNumber) 集")
                                        .font(.headline)
                                    if let progress = model.episodeProgressByID[episode.id] {
                                        ProgressView(value: Double(progress.progressPercent), total: 100)
                                            .frame(width: 105)
                                        Text("\(progress.currentAction) · \(progress.progressPercent)%")
                                            .font(.caption)
                                    }
                                }
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(episode.id == model.selectedEpisodeID ? .blue : .gray)
                            .controlSize(.large)
                            .help(episode.status)
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 12)
                }
                Divider()
            }
            if !model.seasons.isEmpty {
                planningEditor
                Divider()
            }
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 18) {
                        ForEach(model.messages) { message in
                            bubble(message)
                        }
                        if !model.transcript.isEmpty {
                            VStack(alignment: .leading, spacing: 6) {
                                Label("正在把您的话记下来", systemImage: "quote.bubble.fill")
                                    .font(.headline)
                                    .foregroundStyle(.blue)
                                Text(model.transcript).font(.title3)
                                if model.transcriptConfidence > 0 {
                                    Text(model.transcriptConfidence < 0.2 ? "我可能没听清" : "我听清了")
                                        .font(.caption)
                                        .foregroundStyle(
                                            model.transcriptConfidence < 0.2 ? .orange : .secondary
                                        )
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(18)
                            .background(Color.blue.opacity(0.10), in: RoundedRectangle(cornerRadius: 16))
                            .accessibilityIdentifier("nalu.conversation.live-transcript")
                        }
                        Color.clear.frame(height: 1).id("conversation-bottom")
                    }
                    .padding(28)
                }
                .onChange(of: model.messages.count) {
                    withAnimation { proxy.scrollTo("conversation-bottom", anchor: .bottom) }
                }
                .onChange(of: model.transcript) {
                    withAnimation(.easeOut(duration: 0.18)) {
                        proxy.scrollTo("conversation-bottom", anchor: .bottom)
                    }
                }
                .accessibilityIdentifier("nalu.conversation.scroll")
            }
            if let planningVoiceLabel = model.planningVoiceLabel {
                Label("当前语音任务：\(planningVoiceLabel)", systemImage: "waveform.badge.mic")
                    .font(.headline)
                    .foregroundStyle(.blue)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 24)
                    .padding(.top, 12)
            }
            VoiceActivityStatus(isListening: model.isListening)
            Button(action: toggleMicrophone) {
                Label(
                    model.isListening ? "说完了" : "按一下，然后开始说",
                    systemImage: model.isListening ? "stop.circle.fill" : "mic.circle.fill"
                )
                .font(.title2.bold())
                .frame(maxWidth: .infinity, minHeight: 58)
            }
            .buttonStyle(.borderedProminent)
            .tint(model.isListening ? .red : .blue)
            .padding(24)
            .disabled(realtimeVoice.state.isActive)
        }
        .alert("Nalu 需要您的帮助", isPresented: errorBinding) {
            Button("知道了", role: .cancel) { model.errorMessage = nil }
        } message: {
            Text(model.errorMessage ?? "")
        }
    }

    private var planningEditor: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("本季与分集规划", systemImage: "list.bullet.rectangle.portrait")
                    .font(.headline)
                Spacer()
                Text(seasonPlanStatus)
                    .foregroundStyle(seasonPlanIsCurrent ? .green : .orange)
            }
            TextField("用一两句话说明这一季从哪里开始、在哪里结束", text: seasonPlanBinding)
                .textFieldStyle(.roundedBorder)
                .font(.title3)
            HStack {
                Button("保存季纲") { Task { await model.saveSeasonPlan() } }
                    .buttonStyle(.borderedProminent)
                Button("用语音讲季纲", systemImage: "mic") {
                    Task {
                        await model.beginSeasonPlanDictation(
                            startLocalCapture: !realtimeVoice.state.isActive
                        )
                        if realtimeVoice.state.isActive {
                            realtimeVoice.speakPrompt(model.currentInterviewPrompt)
                        }
                    }
                }
                if selectedProject?.audienceMode == "child" {
                    Toggle("监护人已在场确认", isOn: guardianPlanBinding)
                }
                Button("我已看过并确认") {
                    Task { await model.approveSeasonPlanVisually() }
                }
                .disabled(
                    !seasonPlanCanApprove
                        || (selectedProject?.audienceMode == "child"
                            && !model.guardianConfirmedForPlan)
                )
                Button("用语音确认", systemImage: "waveform") {
                    Task {
                        await model.beginSeasonPlanVoiceApproval(
                            startLocalCapture: !realtimeVoice.state.isActive
                        )
                        if realtimeVoice.state.isActive {
                            realtimeVoice.speakPrompt(model.currentInterviewPrompt)
                        }
                    }
                }
                .disabled(
                    !seasonPlanCanApprove
                        || (selectedProject?.audienceMode == "child"
                            && !model.guardianConfirmedForPlan)
                )
            }
            if let episode = selectedEpisode {
                Divider()
                Text("第 \(episode.episodeNumber) 集 · \(episode.title)")
                    .font(.headline)
                if let progress = selectedEpisodeProgress {
                    HStack(spacing: 12) {
                        ProgressView(value: Double(progress.progressPercent), total: 100)
                            .frame(maxWidth: 240)
                        Text("\(progress.progressPercent)% · \(progress.currentAction)")
                            .font(.headline)
                    }
                    Text(progress.explanation)
                        .foregroundStyle(.secondary)
                }
                TextField("这一集发生什么", text: episodeLoglineBinding)
                    .textFieldStyle(.roundedBorder)
                TextField("起因、转折和结尾", text: episodeOutlineBinding, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(2...4)
                HStack {
                    Button("保存本集规划") {
                        Task { await model.saveSelectedEpisodePlan() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(!episodePlanIsEditable)
                Button("用语音讲本集", systemImage: "mic") {
                        Task {
                            await model.beginEpisodePlanDictation(
                                startLocalCapture: !realtimeVoice.state.isActive
                            )
                            if realtimeVoice.state.isActive {
                                realtimeVoice.speakPrompt(model.currentInterviewPrompt)
                            }
                        }
                    }
                    .disabled(!episodePlanIsEditable)
                    if !episodePlanIsEditable {
                        Label("本集已批准或进入制作，规划已锁定", systemImage: "lock.fill")
                            .foregroundStyle(.secondary)
                    }
                }
                DisclosureGroup("剧本创作与确认", isExpanded: $isScriptEditorExpanded) {
                    scriptEditor
                        .padding(.top, 10)
                }
                .font(.headline)
                DisclosureGroup("跨集连续性与本集交接", isExpanded: $isContinuityExpanded) {
                    continuityEditor
                        .padding(.top, 10)
                }
                .font(.headline)
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 14)
        .background(Color.secondary.opacity(0.04))
    }

    private var libraryEditor: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("这些是整个项目共用的设定。只有您明确确认的版本，才会进入后面的分集和制作。")
                .font(.body)
                .foregroundStyle(.secondary)
            HStack(alignment: .top, spacing: 10) {
                Picker(
                    "类型",
                    selection: Binding(
                        get: { model.libraryDraftKind },
                        set: { model.libraryDraftKind = $0 }
                    )
                ) {
                    ForEach(libraryKindOptions, id: \.value) { option in
                        Text(option.label).tag(option.value)
                    }
                }
                .frame(width: 150)
                TextField(
                    "名称，例如：年轻时的父亲",
                    text: Binding(
                        get: { model.libraryDraftName },
                        set: { model.libraryDraftName = $0 }
                    )
                )
                TextField(
                    "需要每一集保持一致的特点",
                    text: Binding(
                        get: { model.libraryDraftDescription },
                        set: { model.libraryDraftDescription = $0 }
                    ),
                    axis: .vertical
                )
                .lineLimit(1...3)
            }
            .textFieldStyle(.roundedBorder)
            HStack {
                Button("保存为待确认草稿", systemImage: "square.and.arrow.down") {
                    Task { await model.createLibraryEntity() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(
                    model.libraryDraftName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || model.libraryDraftDescription.trimmingCharacters(
                            in: .whitespacesAndNewlines
                        ).isEmpty
                )
                Menu("用语音添加", systemImage: "waveform.badge.mic") {
                    ForEach(libraryKindOptions, id: \.value) { option in
                        Button(option.label) {
                            Task { await model.beginLibraryVoiceIntake(kind: option.value) }
                        }
                    }
                }
                .controlSize(.large)
            }
            if model.libraryEntities.isEmpty {
                Label(
                    "还没有项目级设定。可以先从主角、重要地点或旁白声音开始。",
                    systemImage: "books.vertical"
                )
                .font(.body)
                .foregroundStyle(.secondary)
                .padding(.vertical, 8)
            } else {
                ForEach(model.libraryEntities) { entity in
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: libraryKindIcon(entity.kind))
                            .font(.title2)
                            .foregroundStyle(.blue)
                            .frame(width: 30)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("\(libraryKindLabel(entity.kind)) · \(entity.current.name)")
                                .font(.headline)
                            Text(entity.current.description)
                                .font(.body)
                            Label(
                                entity.confirmedRevision == entity.currentRevision
                                    ? "当前第 \(entity.currentRevision) 版已确认"
                                    : "第 \(entity.currentRevision) 版等待确认，不会进入生产",
                                systemImage: entity.confirmedRevision == entity.currentRevision
                                    ? "checkmark.seal.fill" : "exclamationmark.shield.fill"
                            )
                            .font(.caption)
                            .foregroundStyle(
                                entity.confirmedRevision == entity.currentRevision ? .green : .orange
                            )
                        }
                        Spacer()
                        Button("朗读", systemImage: "speaker.wave.2.fill") {
                            model.speakLibraryEntity(entity.id)
                        }
                        if entity.confirmedRevision != entity.currentRevision {
                            Button("我确认当前版本", systemImage: "checkmark.seal") {
                                Task { await model.confirmLibraryEntity(entity.id) }
                            }
                            .buttonStyle(.borderedProminent)
                        }
                    }
                    .padding(12)
                    .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
                }
            }
        }
    }

    private var scriptEditor: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !model.scriptRevisions.isEmpty {
                ScrollView(.horizontal) {
                    HStack {
                        ForEach(model.scriptRevisions) { script in
                            Button("第 \(script.revision) 版\(script.approvedAt == nil ? "" : " · 已批准")") {
                                model.viewScriptRevision(script.revision)
                            }
                            .buttonStyle(.bordered)
                            .tint(
                                script.revision == model.viewedScriptRevision ? .blue : .gray
                            )
                        }
                    }
                }
            } else {
                Text("还没有剧本。您可以直接说，也可以输入第一版。")
                    .foregroundStyle(.secondary)
            }
            TextEditor(text: scriptContentBinding)
                .font(.body)
                .frame(minHeight: 110, maxHeight: 180)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.secondary.opacity(0.3)))
            TextField("给长辈和孩子听的简短摘要", text: scriptSummaryBinding, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(2...4)
            HStack {
                Button("保存为新版本") {
                    Task { await model.saveScriptRevision() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!scriptCanCreateRevision)
                Button("用语音讲剧本", systemImage: "mic") {
                    Task {
                        await model.beginScriptDictation(
                            startLocalCapture: !realtimeVoice.state.isActive
                        )
                        if realtimeVoice.state.isActive {
                            realtimeVoice.speakPrompt(model.currentInterviewPrompt)
                        }
                    }
                }
                .disabled(!scriptCanCreateRevision)
                Button("朗读摘要", systemImage: "speaker.wave.2") {
                    model.speakCurrentScriptSummary()
                }
                .disabled(model.scriptSummary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            HStack {
                if selectedProject?.audienceMode == "child" {
                    Toggle("监护人确认本集剧本", isOn: guardianScriptBinding)
                }
                Button("批准当前剧本") {
                    Task { await model.approveScriptVisually() }
                }
                .disabled(!scriptCanApprove)
                Button("用语音批准", systemImage: "waveform") {
                    Task {
                        await model.beginScriptVoiceApproval(
                            startLocalCapture: !realtimeVoice.state.isActive
                        )
                        if realtimeVoice.state.isActive {
                            realtimeVoice.speakPrompt(model.currentInterviewPrompt)
                        }
                    }
                }
                .disabled(!scriptCanApprove)
                if scriptHasApproval {
                    Button("撤销批准", role: .destructive) {
                        Task { await model.revokeCurrentScriptApproval() }
                    }
                }
            }
            if !scriptIsLatestViewed {
                Label("正在查看旧版本；旧版本不能批准，保存会创建一个新的最新版本。", systemImage: "clock.arrow.circlepath")
                    .font(.caption)
                    .foregroundStyle(.orange)
            }
        }
        .font(.body)
    }

    private var continuityEditor: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(model.continuityStatus, systemImage: continuityStatusIcon)
                .font(.headline)
                .foregroundStyle(continuityStatusColor)
            if model.inheritedContinuity == nil {
                Text("本季第一集不需要核对上一集。完成本集剧本后，请保存结尾交接卡。")
                    .foregroundStyle(.secondary)
            } else {
                GroupBox("一、本集开场核对") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Nalu 已带入上一集最后状态。请只修改本集开场确实发生变化的地方。")
                            .foregroundStyle(.secondary)
                        if !model.continuityHookResolutions.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Label(
                                    "上一集留下 \(model.continuityHookResolutions.count) 个悬念",
                                    systemImage: "questionmark.bubble.fill"
                                )
                                .font(.headline)
                                Text("Nalu 会把选择写进剧本。悬念不能悄悄消失。")
                                    .foregroundStyle(.secondary)
                                ForEach(model.continuityHookResolutions) { resolution in
                                    VStack(alignment: .leading, spacing: 8) {
                                        Text(resolution.hook).font(.body.weight(.semibold))
                                        Picker(
                                            "这一集怎样处理",
                                            selection: Binding(
                                                get: { resolution.disposition },
                                                set: {
                                                    model.updateHookResolution(
                                                        hook: resolution.hook,
                                                        disposition: $0
                                                    )
                                                }
                                            )
                                        ) {
                                            Text("请选择").tag("")
                                            Text("继续留到后面").tag("carry_forward")
                                            Text("在本集解决").tag("resolved")
                                            Text("审阅后不再继续").tag("abandoned")
                                        }
                                        .pickerStyle(.segmented)
                                        if ["resolved", "abandoned"].contains(
                                            resolution.disposition
                                        ) {
                                            TextField(
                                                resolution.disposition == "resolved"
                                                    ? "怎样解决的"
                                                    : "为什么不再继续",
                                                text: Binding(
                                                    get: { resolution.explanation },
                                                    set: {
                                                        model.updateHookResolution(
                                                            hook: resolution.hook,
                                                            explanation: $0
                                                        )
                                                    }
                                                ),
                                                axis: .vertical
                                            )
                                            .textFieldStyle(.roundedBorder)
                                        }
                                    }
                                    .padding(12)
                                    .background(
                                        Color.orange.opacity(0.08),
                                        in: RoundedRectangle(cornerRadius: 12)
                                    )
                                }
                                HStack {
                                    Button("用语音逐个回答", systemImage: "waveform.badge.mic") {
                                        Task { await model.beginHookVoiceReview() }
                                    }
                                    .buttonStyle(.borderedProminent)
                                    Button("朗读悬念安排", systemImage: "speaker.wave.2") {
                                        model.speakHookReview()
                                    }
                                }
                                TextField(
                                    "听完后说或输入：我确认这份悬念安排",
                                    text: Binding(
                                        get: { model.continuityHookConfirmation },
                                        set: { model.updateHookConfirmation($0) }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                                if selectedProject?.audienceMode == "child" {
                                    Label(
                                        "儿童项目还需要上方的监护人确认",
                                        systemImage: "person.badge.shield.checkmark.fill"
                                    )
                                    .foregroundStyle(.secondary)
                                }
                            }
                            .padding(14)
                            .background(
                                Color.orange.opacity(0.05),
                                in: RoundedRectangle(cornerRadius: 14)
                            )
                        }
                        continuityForm(.opening)
                        HStack {
                            Button("朗读本集开场", systemImage: "speaker.wave.2") {
                                model.speakOpeningContinuity()
                            }
                            Button("检查与上一集是否连得上", systemImage: "checkmark.shield") {
                                Task { await model.checkOpeningContinuity() }
                            }
                            .buttonStyle(.borderedProminent)
                        }
                        if let result = model.continuityPreflightResult {
                            continuityResult(result)
                        }
                    }
                    .padding(.top, 6)
                }
            }
            GroupBox("二、保存本集结尾交接卡") {
                VStack(alignment: .leading, spacing: 12) {
                    Text("让 Nalu 先从已确认剧本整理，您只需要听一遍、改错并确认。没有确认前，下一集不会继承。")
                        .foregroundStyle(.secondary)
                    Button("从定稿剧本整理结尾", systemImage: "wand.and.stars") {
                        Task { await model.prepareEndingContinuityFromApprovedScript() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(selectedEpisode?.status != "script_approved")
                    .accessibilityHint("从当前已确认的剧本整理人物、道具、时间和未解悬念，不会自动确认")
                    if selectedEpisode?.status != "script_approved" {
                        Label("请先确认本集剧本，Nalu 才能整理结尾。", systemImage: "lock.fill")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let proposal = model.continuityExtractionProposal {
                        let proposalWasReviewed = model.reviewedContinuityExtractionHash
                            == proposal.proposalSHA256
                        Label(
                            model.isReadingEndingContinuity
                                ? "正在逐项朗读，请听完"
                                : proposalWasReviewed
                                    ? "朗读完成，内容可以确认"
                                    : "已从第 \(proposal.scriptRevision) 版定稿整理 \(proposal.extractedPaths.count) 项，等待您朗读核对",
                            systemImage: proposalWasReviewed
                                ? "checkmark.seal.fill" : "waveform"
                        )
                        .font(.headline)
                        .foregroundStyle(
                            proposalWasReviewed ? .green : .orange
                        )
                        .accessibilityLabel(
                            model.isReadingEndingContinuity
                                ? "正在逐项朗读，请听完"
                                : proposalWasReviewed
                                    ? "朗读完成，内容可以确认"
                                    : "已整理结尾，等待朗读核对"
                        )
                        ContinuityEvidenceView(evidence: proposal.evidence ?? [])
                        continuityForm(.ending)
                        if model.continuityExtractionWasEdited {
                            TextField(
                                "简单说明改了什么，例如：天气不是大雪，是小雪",
                                text: Binding(
                                    get: { model.continuityExtractionChangeSummary },
                                    set: { model.continuityExtractionChangeSummary = $0 }
                                ),
                                axis: .vertical
                            )
                            .textFieldStyle(.roundedBorder)
                        }
                        Button(
                            model.isReadingEndingContinuity ? "正在朗读…" : "朗读本集结尾",
                            systemImage: model.isReadingEndingContinuity
                                ? "waveform" : "speaker.wave.2"
                        ) {
                            model.speakEndingContinuity()
                        }
                        .buttonStyle(.bordered)
                        .disabled(model.isReadingEndingContinuity)
                        HStack {
                            Button("确认并保存交接卡", systemImage: "checkmark.seal.fill") {
                                Task { await model.confirmExtractedEndingContinuity() }
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(!model.canConfirmContinuityExtraction)
                            .accessibilityHint("只保存刚刚朗读核对过的当前结尾状态")
                            Button("用语音确认", systemImage: "waveform.badge.mic") {
                                Task {
                                    await model.beginContinuityVoiceConfirmation(
                                        startLocalCapture: !realtimeVoice.state.isActive
                                    )
                                    if realtimeVoice.state.isActive {
                                        realtimeVoice.speakPrompt(model.currentInterviewPrompt)
                                    }
                                }
                            }
                            .disabled(!model.canConfirmContinuityExtraction)
                            .accessibilityHint("听到提示后说：我确认这个结尾交接卡")
                        }
                        if !proposalWasReviewed {
                            Text(
                                model.isReadingEndingContinuity
                                    ? "朗读结束后，确认按钮会自动亮起。"
                                    : "请先按“朗读本集结尾”。修改任何内容后，需要重新朗读。"
                            )
                                .font(.caption)
                                .foregroundStyle(.orange)
                        }
                    } else {
                        DisclosureGroup("高级：没有定稿剧本时手动填写") {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("通常不需要填写这些内容。只有无法先确认剧本时，才使用这个入口。")
                                    .foregroundStyle(.secondary)
                                continuityForm(.ending)
                                HStack {
                                    Button("朗读本集结尾", systemImage: "speaker.wave.2") {
                                        model.speakEndingContinuity()
                                    }
                                    Button("手动保存交接卡", systemImage: "tray.and.arrow.down.fill") {
                                        Task { await model.saveEndingContinuity() }
                                    }
                                    .buttonStyle(.bordered)
                                }
                            }
                            .padding(.top, 8)
                        }
                    }
                    if !model.continuitySnapshots.isEmpty {
                        Label(
                            "本集已保存 \(model.continuitySnapshots.count) 个历史快照，旧快照不会被覆盖",
                            systemImage: "lock.doc.fill"
                        )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }
                }
                .padding(.top, 6)
            }
        }
        .font(.body)
    }

    @ViewBuilder
    private func continuityResult(_ result: ContinuityPreflightResult) -> some View {
        if result.canProceed {
            Label("检查通过：这份开场状态会随下一版剧本一起锁定", systemImage: "checkmark.seal.fill")
                .foregroundStyle(.green)
        } else {
            VStack(alignment: .leading, spacing: 10) {
                if !["accepted", "not_required"].contains(result.hookReviewStatus) {
                    Label("上一集悬念还没有逐项确认", systemImage: "questionmark.bubble.fill")
                        .foregroundStyle(.orange)
                    Text(result.explanation).foregroundStyle(.secondary)
                }
                if !result.conflicts.isEmpty {
                    Label("发现 \(result.conflicts.count) 处没有说明的变化", systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                }
                ForEach(result.conflicts) { conflict in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(continuityPathLabel(conflict.path)).font(.headline)
                        Text("上一集：\(conflict.inheritedValue.readableText)")
                        Text("本集开场：\(conflict.proposedValue.readableText)")
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.orange.opacity(0.09), in: RoundedRectangle(cornerRadius: 10))
                }
                if !result.conflicts.isEmpty {
                    TextField(
                        "说明中间发生了什么，例如：开场字幕说明三个月后",
                        text: continuityTransitionExplanationBinding,
                        axis: .vertical
                    )
                    .textFieldStyle(.roundedBorder)
                    Button("记录这个剧情解释并重新检查") {
                        Task { await model.checkOpeningContinuity(applyExplanation: true) }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(
                        model.continuityTransitionExplanation.trimmingCharacters(
                            in: .whitespacesAndNewlines
                        ).isEmpty
                    )
                    DisclosureGroup("高级：审阅后强制覆盖", isExpanded: $isContinuityOverrideExpanded) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("只有剧情确实故意不连续时使用。覆盖记录会绑定到当前剧本版本。")
                                .foregroundStyle(.red)
                            TextField("为什么必须覆盖", text: continuityOverrideReasonBinding)
                                .textFieldStyle(.roundedBorder)
                            TextField(
                                "完整输入：我确认这些变化可以覆盖",
                                text: continuityOverrideConfirmationBinding
                            )
                            .textFieldStyle(.roundedBorder)
                            Button("确认覆盖并重新检查", role: .destructive) {
                                Task { await model.checkOpeningContinuity(applyOverride: true) }
                            }
                        }
                        .padding(.top, 8)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func continuityForm(_ kind: ContinuityEditorKind) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                TextField("故事地点", text: continuityTextBinding(kind, \.sceneLocation))
                TextField("故事时间", text: continuityTextBinding(kind, \.storyTime))
                TextField("天气", text: continuityTextBinding(kind, \.weather))
            }
            .textFieldStyle(.roundedBorder)
            ForEach(continuityDraft(kind).characters) { character in
                characterContinuityRow(kind, character: character)
            }
            Button("添加人物状态", systemImage: "person.badge.plus") {
                mutateContinuityDraft(kind) { $0.characters.append(.init()) }
            }
            ForEach(continuityDraft(kind).props) { prop in
                propContinuityRow(kind, prop: prop)
            }
            Button("添加道具状态", systemImage: "shippingbox.and.arrow.backward") {
                mutateContinuityDraft(kind) { $0.props.append(.init()) }
            }
            if kind == .ending {
                TextField(
                    "还没解决的悬念，用顿号分开",
                    text: continuityTextBinding(kind, \.unresolvedHooks),
                    axis: .vertical
                )
                .textFieldStyle(.roundedBorder)
            }
        }
    }

    private func characterContinuityRow(
        _ kind: ContinuityEditorKind, character: ContinuityCharacterEntry
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                TextField("人物名称", text: characterBinding(kind, character.id, \.name))
                TextField("人物在哪里", text: characterBinding(kind, character.id, \.location))
                Button("移除", systemImage: "minus.circle", role: .destructive) {
                    mutateContinuityDraft(kind) {
                        $0.characters.removeAll { $0.id == character.id }
                    }
                }
            }
            HStack {
                TextField("穿着，用顿号分开", text: characterBinding(kind, character.id, \.wardrobe))
                TextField("伤势，用顿号分开", text: characterBinding(kind, character.id, \.injuries))
                TextField("手持道具，用顿号分开", text: characterBinding(kind, character.id, \.heldProps))
            }
            HStack {
                TextField("关系，例如：小梅：姐姐", text: characterBinding(kind, character.id, \.relationships))
                TextField("已经公开的事实", text: characterBinding(kind, character.id, \.revealedFacts))
            }
        }
        .textFieldStyle(.roundedBorder)
        .padding(10)
        .background(Color.blue.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
    }

    private func propContinuityRow(
        _ kind: ContinuityEditorKind, prop: ContinuityPropEntry
    ) -> some View {
        HStack {
            TextField("道具名称", text: propBinding(kind, prop.id, \.name))
            TextField("现在属于谁", text: propBinding(kind, prop.id, \.owner))
            TextField("道具在哪里", text: propBinding(kind, prop.id, \.location))
            TextField("状态，例如：锁扣损坏", text: propBinding(kind, prop.id, \.condition))
            Button("移除", systemImage: "minus.circle", role: .destructive) {
                mutateContinuityDraft(kind) { $0.props.removeAll { $0.id == prop.id } }
            }
        }
        .textFieldStyle(.roundedBorder)
        .padding(10)
        .background(Color.purple.opacity(0.05), in: RoundedRectangle(cornerRadius: 10))
    }

    private var assetEditor: some View {
        VStack(alignment: .leading, spacing: 10) {
            if selectedProject?.creativeFormat == "documentary_series" {
                documentaryReadinessPanel
                    .padding(.bottom, 8)
            }
            VStack(alignment: .leading, spacing: 12) {
                Text("不用填写表格")
                    .font(.title2.bold())
                Text("您只要选择照片、手稿、录音或家庭视频。Nalu 会在本机识别并建立草稿，再用语音问您缺少的内容。")
                    .font(.body)
                Label(
                    "第一次导入只供理解和核对，不会自动同意用人脸或声音生成画面。",
                    systemImage: "lock.shield.fill"
                )
                .font(.callout)
                .foregroundStyle(.secondary)
                Button("选择家庭资料，让 Nalu 整理", systemImage: "plus.rectangle.on.folder") {
                    isAutomaticAssetImport = true
                    isImportingAsset = true
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .keyboardShortcut("u", modifiers: [.command])
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.blue.opacity(0.07), in: RoundedRectangle(cornerRadius: 14))

            DisclosureGroup(
                "我想自己修改资料类型、范围或授权",
                isExpanded: $isAdvancedAssetEditorExpanded
            ) {
                advancedAssetEditor
                    .padding(.top, 12)
            }
            .font(.headline)
            .padding(.vertical, 8)
            if model.assets.isEmpty {
                Text("还没有资料。按上面的蓝色按钮选择一份就可以。")
                    .font(.body)
                    .foregroundStyle(.secondary)
            } else {
                Divider()
                ForEach(model.assets) { asset in
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: assetIcon(asset.kind))
                            .font(.title2)
                            .foregroundStyle(.blue)
                            .frame(width: 28)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(asset.name).font(.body.bold())
                            Text("\(assetKindLabel(asset.kind)) · \(assetScopeLabel(asset))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if assetIsBiometricKind(asset.kind) {
                                Label(
                                    asset.consentGranted ? "授权有效" : "授权已撤销",
                                    systemImage: asset.consentGranted
                                        ? "checkmark.shield.fill" : "xmark.shield.fill"
                                )
                                .font(.caption)
                                .foregroundStyle(asset.consentGranted ? .green : .red)
                            }
                            if let card = model.memoryCards.first(where: { $0.assetID == asset.id }) {
                                Label(
                                    card.confirmationStatus == "confirmed"
                                        ? "记忆卡已确认归档" : "记忆卡等待朗读确认",
                                    systemImage: card.confirmationStatus == "confirmed"
                                        ? "checkmark.seal.fill" : "ear.badge.waveform"
                                )
                                .font(.caption)
                                .foregroundStyle(
                                    card.confirmationStatus == "confirmed" ? .green : .orange
                                )
                                Text(memoryCardSummary(card))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                                if let report = model.memoryConflictReports[card.id], report.blocking {
                                    Label(
                                        "发现 \(report.conflicts.count) 处资料对不上，尚未归档",
                                        systemImage: "exclamationmark.triangle.fill"
                                    )
                                    .font(.caption.bold())
                                    .foregroundStyle(.red)
                                    .accessibilityHint("按右侧朗读矛盾，可听取两份资料哪里不同")
                                }
                            }
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 8) {
                            if let card = model.memoryCards.first(where: { $0.assetID == asset.id }) {
                                HStack {
                                    Button("朗读", systemImage: "speaker.wave.2.fill") {
                                        model.speakMemoryCard(card.id)
                                    }
                                    Button("修改", systemImage: "pencil") {
                                        presentMemoryEditor(card)
                                    }
                                }
                                HStack {
                                    Button("语音修改", systemImage: "waveform.badge.mic") {
                                        Task { await model.beginMemoryCorrection(card.id) }
                                    }
                                    if card.confirmationStatus != "confirmed" {
                                        Button("语音确认", systemImage: "checkmark.seal") {
                                            Task { await model.beginMemoryVoiceConfirmation(card.id) }
                                        }
                                    }
                                }
                                if card.confirmationStatus != "confirmed" {
                                    Button("确认归档", systemImage: "checkmark.seal") {
                                        Task { await model.confirmMemoryCard(card.id) }
                                    }
                                    .buttonStyle(.borderedProminent)
                                    if model.memoryConflictReports[card.id]?.blocking == true {
                                        Button("朗读矛盾", systemImage: "speaker.wave.2.fill") {
                                            model.speakMemoryConflict(card.id)
                                        }
                                        .accessibilityHint("朗读冲突内容，并告诉您需要修改哪张记忆卡")
                                    }
                                }
                            }
                            HStack {
                                if assetIsBiometricKind(asset.kind) && asset.consentGranted {
                                    Button("撤销授权", role: .destructive) {
                                        Task { await model.revokeAssetConsent(asset.id) }
                                    }
                                }
                                Button("检查删除", systemImage: "trash") {
                                    inspectAssetDependencies(asset.id)
                                }
                            }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .font(.body)
        .onChange(of: assetKind) {
            assetConsentGranted = false
            assetGuardianApproved = false
            assetConsentStatement = ""
            assetSubjectName = ""
        }
    }

    private var advancedAssetEditor: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("这些是专业设置。大多数情况下不需要修改。")
                .font(.body)
                .foregroundStyle(.secondary)
            HStack {
                Picker("资料类型", selection: $assetKind) {
                    ForEach(assetKindOptions, id: \.value) { option in
                        Text(option.label).tag(option.value)
                    }
                }
                .frame(maxWidth: 280)
                TextField("资料名称", text: $assetName)
                    .textFieldStyle(.roundedBorder)
            }
            if assetIsBiometric {
                TextField("照片或声音属于谁", text: $assetSubjectName)
                    .textFieldStyle(.roundedBorder)
                Toggle("本人或合法授权人明确同意用于生成", isOn: $assetConsentGranted)
                TextField("授权范围，例如：同意把这张照片用于《我的故事》", text: $assetConsentStatement)
                    .textFieldStyle(.roundedBorder)
                if selectedProject?.audienceMode == "child" {
                    Toggle("监护人已在场并同意儿童肖像或声音使用", isOn: $assetGuardianApproved)
                }
            }
            Picker("使用范围", selection: $assetScope) {
                Text("整个项目").tag("project")
                Text("当前这一季").tag("season")
                Text("当前这一集").tag("episode")
            }
            .pickerStyle(.segmented)
            TextField("这是什么、发生了什么", text: $assetMemoryDescription)
                .textFieldStyle(.roundedBorder)
            HStack {
                TextField("大约什么时候", text: $assetMemoryDate)
                    .textFieldStyle(.roundedBorder)
                TextField("在哪里", text: $assetMemoryPlace)
                    .textFieldStyle(.roundedBorder)
            }
            TextField("这份资料对故事有什么意义", text: $assetMemoryStoryRelevance)
                .textFieldStyle(.roundedBorder)
            Picker("允许怎样使用", selection: $assetMemoryAllowedUse) {
                Text("只供理解和核对").tag("reference_only")
                Text("可用于编写剧本").tag("story_development")
                Text("可用于生成画面").tag("visual_generation")
            }
            .pickerStyle(.segmented)
            HStack {
                Button("按这些设置选择文件", systemImage: "slider.horizontal.3") {
                    isAutomaticAssetImport = false
                    isImportingAsset = true
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .disabled(!assetImportIsReady)
                if assetIsBiometric && !assetConsentGranted {
                    Label("人物照片和声音必须先取得明确授权", systemImage: "hand.raised.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }
        }
        .font(.body)
    }

    @ViewBuilder
    private var documentaryReadinessPanel: some View {
        if let report = model.documentaryReadiness {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.title)
                        .foregroundStyle(.blue)
                        .frame(width: 34)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("纪录片资料准备")
                            .font(.title2.bold())
                        Label(
                            report.canPlanChapters
                                ? "资料已足够开始规划章节"
                                : "请先说明并确认一份真实资料",
                            systemImage: report.canPlanChapters
                                ? "checkmark.circle.fill" : "exclamationmark.circle.fill"
                        )
                        .font(.title3.bold())
                        .foregroundStyle(report.canPlanChapters ? .green : .orange)
                    }
                    Spacer()
                    Button("朗读准备情况", systemImage: "speaker.wave.2.fill") {
                        model.speakDocumentaryReadiness()
                    }
                    .controlSize(.large)
                }

                Text(
                    "共有 \(report.evidence.count) 份本地资料；"
                    + "\(report.confirmedNarrativeSourceCount) 份已确认可作为故事依据；"
                    + "\(report.draftOrUnlinkedSourceCount) 份仍需说明或确认。"
                )
                .font(.body)

                if report.generatedReenactmentLabelRequired {
                    Label(
                        "这个项目允许少量剧情重现。生成画面必须明确标注“剧情重现”，不能冒充历史影像。",
                        systemImage: "exclamationmark.triangle.fill"
                    )
                    .font(.body.bold())
                    .foregroundStyle(.orange)
                }

                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    Text("接下来 Nalu 会这样问")
                        .font(.headline)
                    ForEach(Array(report.nextQuestions.prefix(2)), id: \.self) { question in
                        Label(question, systemImage: "questionmark.bubble")
                            .font(.body)
                    }
                }

                Label(
                    "现在只开放资料整理和章节规划。纪录片生产线通过真实性与发行检查前，不会开始生成成片。",
                    systemImage: "lock.shield.fill"
                )
                .font(.callout)
                .foregroundStyle(.secondary)
            }
            .padding(18)
            .background(Color.blue.opacity(0.07), in: RoundedRectangle(cornerRadius: 14))
            .accessibilityElement(children: .contain)
        } else {
            HStack(spacing: 12) {
                ProgressView()
                Text("正在检查纪录片资料…")
                    .font(.body)
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 14))
        }
    }

    private var assetEditorSheet: some View {
        VStack(spacing: 0) {
            HStack(spacing: 14) {
                Image(systemName: "photo.stack.fill")
                    .font(.title)
                    .foregroundStyle(.blue)
                VStack(alignment: .leading, spacing: 3) {
                    Text("管理家庭资料")
                        .font(.title2.bold())
                    Text("查看已经归档的资料；专业类型和授权设置在需要时再展开。")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("完成", systemImage: "xmark.circle.fill") {
                    isPresentingAssetEditor = false
                }
                .controlSize(.large)
            }
            .padding(24)
            Divider()
            ScrollView {
                assetEditor
                    .padding(24)
            }
        }
        .frame(minWidth: 760, minHeight: 640)
    }

    private var realtimeConsentSheet: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("开启自然语音对话", systemImage: "waveform.and.mic")
                .font(.title2.bold())
                .foregroundStyle(.purple)
            Text("开启后可以像打电话一样交谈：您可以停顿、插话、问问题，Nalu 会先回答，再回到创作流程。")
                .font(.title3)
            GroupBox("开启前请您知道") {
                VStack(alignment: .leading, spacing: 10) {
                    Label("麦克风声音会发送给 OpenAI Realtime 处理", systemImage: "icloud.and.arrow.up")
                    Label("这会使用您的 OpenAI API 额度并可能产生费用", systemImage: "creditcard")
                    Label("音频不写入项目 SQLite、备份或反馈记录", systemImage: "externaldrive.badge.checkmark")
                    Label("随时点“结束自然语音”即可断开，并回到本机按键模式", systemImage: "phone.down")
                }
                .padding(.top, 5)
            }
            Toggle("我知道声音会离开这台 Mac，并同意开启这次云端语音会话", isOn: $realtimeCloudConsent)
                .font(.headline)
            Picker("本次最长时长", selection: $realtimeSessionLimitMinutes) {
                ForEach(RealtimeSessionLimit.choices, id: \.self) { minutes in
                    Text("\(minutes) 分钟").tag(minutes)
                }
            }
            .pickerStyle(.segmented)
            Text("到达上限会自动断开，避免忘记关闭。实际费用由您的 OpenAI 账户用量决定。")
                .font(.caption)
                .foregroundStyle(.secondary)
            if selectedProject?.audienceMode == "child" {
                Toggle("监护人正在现场，并同意孩子开启这次云端语音会话", isOn: $realtimeGuardianConsent)
                    .font(.headline)
            }
            if !realtimeCredentialIsConfigured {
                Label("尚未设置 OpenAI Realtime 密钥", systemImage: "key.slash")
                    .foregroundStyle(.orange)
                Button("先设置模型密钥", systemImage: "key.fill") {
                    isPresentingRealtimeConsent = false
                    presentProviderCredentials()
                }
                .controlSize(.large)
            }
            HStack {
                Button("取消", role: .cancel) {
                    isPresentingRealtimeConsent = false
                }
                Spacer()
                Button("同意并开始自然语音", systemImage: "waveform.and.mic") {
                    beginRealtimeVoice()
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(
                    !realtimeCredentialIsConfigured
                        || !realtimeCloudConsent
                        || (selectedProject?.audienceMode == "child" && !realtimeGuardianConsent)
                )
            }
        }
        .padding(28)
        .frame(minWidth: 650)
        .interactiveDismissDisabled(realtimeCloudConsent)
    }

    private var projectDeletionSheet: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("永久删除本机项目", systemImage: "exclamationmark.triangle.fill")
                .font(.title2.bold())
                .foregroundStyle(.red)
            if let preview = deletionPreview {
                Text("将删除“\(preview.projectTitle)”以及 \(preview.assetCount) 个本地素材。")
                    .font(.title3)
                if preview.productionRunCount > 0 {
                    Text("还包括 \(preview.productionRunCount) 个不可变制作快照和对应工作目录。")
                        .font(.headline)
                        .foregroundStyle(.red)
                    Toggle(
                        "我确认同时删除这些制作快照",
                        isOn: $deleteProductionSnapshots
                    )
                }
                Text("为防止误删，请完整输入项目名称：\(preview.projectTitle)")
                    .foregroundStyle(.secondary)
                TextField("项目名称", text: $projectDeletionConfirmation)
                    .textFieldStyle(.roundedBorder)
                    .font(.title3)
                HStack {
                    Button("取消", role: .cancel) {
                        isPresentingProjectDeletion = false
                    }
                    Spacer()
                    Button("永久删除", role: .destructive) {
                        executeProjectDeletion()
                    }
                    .disabled(!projectDeletionIsReady)
                }
            } else {
                ProgressView("正在核对本地素材和制作快照…")
            }
        }
        .padding(28)
        .frame(minWidth: 540)
        .interactiveDismissDisabled(deletionPreview != nil)
    }

    private var providerCredentialsSheet: some View {
        VStack(alignment: .leading, spacing: 20) {
            Label("模型服务密钥", systemImage: "key.fill")
                .font(.title2.bold())
            Text("密钥只保存在当前 Mac 用户的系统钥匙串中，不写入 SQLite、项目备份、隐私包或 Runtime 启动参数。")
                .foregroundStyle(.secondary)
            credentialEditor(
                credential: .seedance,
                draft: $seedanceSecretDraft,
                configured: seedanceIsConfigured
            )
            Divider()
            credentialEditor(
                credential: .minimax,
                draft: $minimaxSecretDraft,
                configured: minimaxIsConfigured
            )
            Divider()
            credentialEditor(
                credential: .openAIRealtime,
                draft: $openAIRealtimeSecretDraft,
                configured: openAIRealtimeIsConfigured
            )
            Text("保存密钥不会触发付费调用。模型适配器和付费事务还需要独立授权。")
                .font(.caption)
                .foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button("完成") { isPresentingProviderCredentials = false }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(28)
        .frame(minWidth: 600)
    }

    private var feedbackSheet: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("告诉 Nalu，怎样才能更好用", systemImage: "ear.badge.waveform")
                .font(.title2.bold())
            Text("可以说哪里看不清、哪里不会用、哪里出错，或者希望增加什么。")
                .font(.title3)
            Picker("意见类型", selection: $feedbackCategory) {
                Text("不好用").tag("usability")
                Text("出错了").tag("bug")
                Text("想加功能").tag("feature_request")
                Text("需要改正").tag("correction")
                Text("我的习惯").tag("preference")
            }
            .pickerStyle(.segmented)

            TextEditor(
                text: Binding(
                    get: { model.feedbackDraftText },
                    set: {
                        model.feedbackDraftText = $0
                        model.feedbackWasDictated = false
                    }
                )
            )
            .font(.title3)
            .frame(minHeight: 130)
            .padding(8)
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.secondary.opacity(0.4)))

            Button {
                Task {
                    if model.isListening {
                        await model.toggleListening()
                    } else {
                        await model.beginFeedbackDictation()
                    }
                }
            } label: {
                Label(
                    model.isListening ? "说完了，保存这句话" : "按一下，用语音告诉 Nalu",
                    systemImage: model.isListening ? "stop.circle.fill" : "mic.circle.fill"
                )
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(model.isListening ? .red : .blue)
            .controlSize(.large)

            Toggle("允许脱敏并由 Nalu 自动整理本地审核资料", isOn: $feedbackShareAuthorized)
            Text("Nalu 会替您填写专业审核资料。默认只保存在本机；不会上传照片、视频、声音、密钥，也不会未经审核自动修改程序。")
                .font(.callout)
                .foregroundStyle(.secondary)
            if selectedProject?.audienceMode == "child", feedbackShareAuthorized {
                Toggle("监护人同意提交这条改进意见", isOn: $feedbackGuardianApproved)
            }
            if let readiness = model.feedbackReleaseReadiness {
                VStack(alignment: .leading, spacing: 10) {
                    Label("这条意见的改进进度", systemImage: "checklist")
                        .font(.headline)
                    Text(
                        readiness.readyForAuthorizedRollout
                            ? "发布前证据已齐，但仍未发布。"
                            : "已经记录，不代表已经修好。"
                    )
                    .font(.title3.bold())
                    .foregroundStyle(readiness.released ? .green : .orange)
                    ForEach(readiness.checks) { check in
                        Label(
                            check.explanation,
                            systemImage: check.status == "satisfied"
                                ? "checkmark.circle.fill" : "clock.badge.exclamationmark"
                        )
                        .foregroundStyle(check.status == "satisfied" ? .green : .secondary)
                    }
                    Button("朗读改进进度", systemImage: "speaker.wave.2.fill") {
                        model.readFeedbackReleaseReadiness()
                    }
                    .controlSize(.large)
                }
                .padding(14)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 14))
                .accessibilityElement(children: .contain)
            }
            HStack {
                Button("取消", role: .cancel) { isPresentingFeedback = false }
                Spacer()
                if model.feedbackReleaseReadiness == nil {
                    Button("保存意见") {
                        Task {
                            if await model.saveFeedback(
                                category: feedbackCategory,
                                shareAuthorized: feedbackShareAuthorized,
                                guardianApproval: feedbackGuardianApproved
                            ) {
                                feedbackShareAuthorized = false
                                feedbackGuardianApproved = false
                            }
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(
                        model.feedbackDraftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            || (selectedProject?.audienceMode == "child"
                                && feedbackShareAuthorized && !feedbackGuardianApproved)
                    )
                } else {
                    Button("完成") { isPresentingFeedback = false }
                        .buttonStyle(.borderedProminent)
                        .keyboardShortcut(.defaultAction)
                }
            }
        }
        .padding(28)
        .frame(minWidth: 680, minHeight: 560)
    }

    private var memoryEditorSheet: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("修改记忆卡", systemImage: "photo.badge.checkmark")
                .font(.title2.bold())
            Text("保存修改会建立新版本，并撤销原来的确认。请重新朗读核对后再归档。")
                .foregroundStyle(.secondary)
            TextField("记忆卡标题", text: $editingMemoryTitle)
                .textFieldStyle(.roundedBorder)
            TextEditor(text: $editingMemoryDescription)
                .font(.title3)
                .frame(minHeight: 100)
                .padding(8)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(.secondary.opacity(0.4)))
            HStack {
                TextField("大约什么时候", text: $editingMemoryDate)
                    .textFieldStyle(.roundedBorder)
                TextField("在哪里", text: $editingMemoryPlace)
                    .textFieldStyle(.roundedBorder)
            }
            TextField("对故事有什么意义", text: $editingMemoryStoryRelevance)
                .textFieldStyle(.roundedBorder)
            Picker("允许怎样使用", selection: $editingMemoryAllowedUse) {
                Text("只供理解和核对").tag("reference_only")
                Text("可用于编写剧本").tag("story_development")
                Text("可用于生成画面").tag("visual_generation")
            }
            .pickerStyle(.segmented)
            HStack {
                Button("取消", role: .cancel) { isPresentingMemoryEditor = false }
                Spacer()
                Button("保存为新版本") {
                    saveMemoryEdits()
                }
                .buttonStyle(.borderedProminent)
                .disabled(
                    editingMemoryID == nil
                        || editingMemoryTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                )
            }
        }
        .padding(28)
        .frame(minWidth: 650, minHeight: 520)
    }

    private func credentialEditor(
        credential: ProviderCredential,
        draft: Binding<String>,
        configured: Bool
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(credential.label).font(.headline)
                Spacer()
                Label(
                    configured ? "已存入钥匙串" : "尚未配置",
                    systemImage: configured ? "checkmark.shield.fill" : "shield"
                )
                .foregroundStyle(configured ? .green : .secondary)
            }
            SecureField(configured ? "输入新密钥可替换现有值" : "粘贴 API 密钥", text: draft)
                .textFieldStyle(.roundedBorder)
            HStack {
                Button(configured ? "替换密钥" : "保存到钥匙串") {
                    saveCredential(credential, secret: draft.wrappedValue)
                }
                .disabled(draft.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if configured {
                    Button("从钥匙串移除", role: .destructive) {
                        removeCredential(credential)
                    }
                }
            }
        }
    }

    private func bubble(_ message: InterviewMessage) -> some View {
        HStack(alignment: .top, spacing: 12) {
            if message.speaker == .user { Spacer(minLength: 80) }
            if message.speaker == .nalu {
                Image(systemName: "waveform.circle.fill")
                    .font(.title)
                    .foregroundStyle(.blue)
            }
            Text(message.text)
                .font(.title3)
                .lineSpacing(7)
                .padding(18)
                .background(bubbleColor(message), in: RoundedRectangle(cornerRadius: 18))
            if message.speaker == .nalu { Spacer(minLength: 80) }
        }
    }

    private func bubbleColor(_ message: InterviewMessage) -> Color {
        message.speaker == .nalu ? Color.blue.opacity(0.10) : Color.green.opacity(0.12)
    }

    private var errorBinding: Binding<Bool> {
        Binding(
            get: { model.errorMessage != nil },
            set: { if !$0 { model.errorMessage = nil } }
        )
    }

    private var archivedProjectsBinding: Binding<Bool> {
        Binding(
            get: { model.includeArchivedProjects },
            set: { value in
                model.includeArchivedProjects = value
                Task { await model.reloadProjects() }
            }
        )
    }

    private var selectedProject: NaluProject? {
        model.projects.first { $0.id == model.selectedProjectID }
    }

    private var preferredDynamicTypeSize: DynamicTypeSize {
        switch model.comfortPreferences.textLevel {
        case 0: .large
        case 1: .xLarge
        case 2: .xxLarge
        default: .xxxLarge
        }
    }

    private var selectedSeason: NaluSeason? { model.seasons.first }

    private var selectedEpisode: NaluEpisode? {
        model.episodes.first { $0.id == model.selectedEpisodeID }
    }

    private var selectedEpisodeProgress: EpisodeProductionProgress? {
        guard let selectedEpisodeID = model.selectedEpisodeID else { return nil }
        return model.episodeProgressByID[selectedEpisodeID]
    }

    private var seasonPlanIsCurrent: Bool {
        guard let season = selectedSeason else { return false }
        return season.planRevision == season.approvedPlanRevision
    }

    private var seasonPlanCanApprove: Bool {
        guard let season = selectedSeason else { return false }
        return season.planRevision > 0 && !seasonPlanIsCurrent
    }

    private var seasonPlanStatus: String {
        guard let season = selectedSeason else { return "" }
        if seasonPlanIsCurrent { return "第 \(season.planRevision) 版已确认" }
        return "第 \(season.planRevision) 版等待确认"
    }

    private var episodePlanIsEditable: Bool {
        guard let status = selectedEpisode?.status else { return false }
        return ["planned", "script_draft", "script_review"].contains(status)
    }

    private var scriptIsLatestViewed: Bool {
        model.viewedScriptRevision == model.scriptRevisions.last?.revision
    }

    private var scriptHasApproval: Bool {
        model.scriptRevisions.contains { $0.approvedAt != nil }
    }

    private var scriptCanCreateRevision: Bool {
        guard let status = selectedEpisode?.status else { return false }
        return ["planned", "script_draft", "script_review", "script_approved"].contains(status)
    }

    private var scriptCanApprove: Bool {
        guard selectedEpisode?.status == "script_review",
              !model.scriptRevisions.isEmpty,
              scriptIsLatestViewed else { return false }
        if selectedProject?.audienceMode == "child" && !model.guardianConfirmedForScript {
            return false
        }
        return model.scriptRevisions.last?.approvedAt == nil
    }

    private var seasonPlanBinding: Binding<String> {
        Binding(get: { model.seasonPlanSummary }, set: { model.seasonPlanSummary = $0 })
    }

    private var episodeLoglineBinding: Binding<String> {
        Binding(get: { model.episodeLogline }, set: { model.episodeLogline = $0 })
    }

    private var episodeOutlineBinding: Binding<String> {
        Binding(
            get: { model.episodeOutlineSummary },
            set: { model.episodeOutlineSummary = $0 }
        )
    }

    private var guardianPlanBinding: Binding<Bool> {
        Binding(
            get: { model.guardianConfirmedForPlan },
            set: { model.guardianConfirmedForPlan = $0 }
        )
    }

    private var guardianScriptBinding: Binding<Bool> {
        Binding(
            get: { model.guardianConfirmedForScript },
            set: { model.guardianConfirmedForScript = $0 }
        )
    }

    private var scriptContentBinding: Binding<String> {
        Binding(get: { model.scriptContent }, set: { model.scriptContent = $0 })
    }

    private var scriptSummaryBinding: Binding<String> {
        Binding(get: { model.scriptSummary }, set: { model.scriptSummary = $0 })
    }

    private var continuityTransitionExplanationBinding: Binding<String> {
        Binding(
            get: { model.continuityTransitionExplanation },
            set: { model.continuityTransitionExplanation = $0 }
        )
    }

    private var continuityOverrideReasonBinding: Binding<String> {
        Binding(
            get: { model.continuityOverrideReason },
            set: { model.continuityOverrideReason = $0 }
        )
    }

    private var continuityOverrideConfirmationBinding: Binding<String> {
        Binding(
            get: { model.continuityOverrideConfirmation },
            set: { model.continuityOverrideConfirmation = $0 }
        )
    }

    private var continuityStatusIcon: String {
        if model.continuityPreflightResult?.canProceed == true { return "checkmark.circle.fill" }
        if model.continuityPreflightResult?.canProceed == false {
            return "exclamationmark.triangle.fill"
        }
        return model.inheritedContinuity == nil ? "1.circle.fill" : "arrow.right.circle.fill"
    }

    private var continuityStatusColor: Color {
        if model.continuityPreflightResult?.canProceed == true { return .green }
        if model.continuityPreflightResult?.canProceed == false { return .orange }
        return .blue
    }

    private func continuityDraft(_ kind: ContinuityEditorKind) -> ContinuityFormDraft {
        switch kind {
        case .opening: model.openingContinuityDraft
        case .ending: model.endingContinuityDraft
        }
    }

    private func mutateContinuityDraft(
        _ kind: ContinuityEditorKind,
        _ change: (inout ContinuityFormDraft) -> Void
    ) {
        switch kind {
        case .opening: change(&model.openingContinuityDraft)
        case .ending:
            change(&model.endingContinuityDraft)
            model.invalidateEndingContinuityReadback()
        }
    }

    private func continuityTextBinding(
        _ kind: ContinuityEditorKind,
        _ keyPath: WritableKeyPath<ContinuityFormDraft, String>
    ) -> Binding<String> {
        Binding(
            get: { continuityDraft(kind)[keyPath: keyPath] },
            set: { value in
                mutateContinuityDraft(kind) { $0[keyPath: keyPath] = value }
            }
        )
    }

    private func characterBinding(
        _ kind: ContinuityEditorKind, _ id: UUID,
        _ keyPath: WritableKeyPath<ContinuityCharacterEntry, String>
    ) -> Binding<String> {
        Binding(
            get: {
                continuityDraft(kind).characters.first(where: { $0.id == id })?[keyPath: keyPath]
                    ?? ""
            },
            set: { value in
                mutateContinuityDraft(kind) { draft in
                    guard let index = draft.characters.firstIndex(where: { $0.id == id }) else {
                        return
                    }
                    draft.characters[index][keyPath: keyPath] = value
                }
            }
        )
    }

    private func propBinding(
        _ kind: ContinuityEditorKind, _ id: UUID,
        _ keyPath: WritableKeyPath<ContinuityPropEntry, String>
    ) -> Binding<String> {
        Binding(
            get: {
                continuityDraft(kind).props.first(where: { $0.id == id })?[keyPath: keyPath]
                    ?? ""
            },
            set: { value in
                mutateContinuityDraft(kind) { draft in
                    guard let index = draft.props.firstIndex(where: { $0.id == id }) else {
                        return
                    }
                    draft.props[index][keyPath: keyPath] = value
                }
            }
        )
    }

    private func continuityPathLabel(_ path: String) -> String {
        let labels = [
            "scene_location": "故事地点",
            "story_time": "故事时间",
            "weather": "天气",
            "location": "人物或道具位置",
            "wardrobe": "人物穿着",
            "injuries": "人物伤势",
            "held_props": "手持道具",
            "relationships": "人物关系",
            "revealed_facts": "已经公开的事实",
            "owner": "道具归属",
            "condition": "道具状态",
        ]
        let finalComponent = path.split(separator: ".").last.map(String.init) ?? path
        return labels[finalComponent].map { "\($0)（\(path)）" } ?? path
    }

    private var exportFilename: String {
        let title = selectedProject?.title ?? "Nalu项目"
        return "\(title)-Nalu备份.json"
    }

    private var privacyExportFilename: String {
        let title = selectedProject?.title ?? "Nalu项目"
        return "\(title)-Nalu隐私包.zip"
    }

    private var libraryKindOptions: [(value: String, label: String)] {
        [
            ("character", "人物"),
            ("scene", "场景"),
            ("prop", "道具"),
            ("voice", "声音"),
            ("style", "画面风格"),
        ]
    }

    private func libraryKindLabel(_ kind: String) -> String {
        libraryKindOptions.first(where: { $0.value == kind })?.label ?? "项目设定"
    }

    private func libraryKindIcon(_ kind: String) -> String {
        switch kind {
        case "character": return "person.crop.rectangle.stack"
        case "scene": return "mountain.2"
        case "prop": return "shippingbox"
        case "voice": return "waveform"
        case "style": return "paintpalette"
        default: return "books.vertical"
        }
    }

    private var assetKindOptions: [(value: String, label: String)] {
        [
            ("source_document", "照片、手稿或文件（只归档）"),
            ("archive_audio", "录音资料（只归档）"),
            ("archive_video", "家庭视频（只归档）"),
            ("character_image", "人物照片"),
            ("voice_reference", "人物声音"),
            ("scene_reference", "场景参考"),
            ("prop_reference", "道具参考"),
            ("style_reference", "画面风格参考"),
        ]
    }

    private var assetIsBiometric: Bool { assetIsBiometricKind(assetKind) }

    private var assetImportIsReady: Bool {
        PrivacySafety.canImportAsset(
            kind: assetKind,
            name: assetName,
            subjectName: assetSubjectName,
            consentGranted: assetConsentGranted,
            consentStatement: assetConsentStatement,
            guardianRequired: selectedProject?.audienceMode == "child",
            guardianApproved: assetGuardianApproved,
            scope: assetScope,
            selectedSeasonID: selectedSeason?.id,
            selectedEpisodeID: selectedEpisode?.id
        )
    }

    private var allowedAssetContentTypes: [UTType] {
        if isAutomaticAssetImport {
            return [.image, .movie, .audio, .plainText, .pdf, .json]
        }
        switch assetKind {
        case "character_image": return [.image]
        case "voice_reference": return [.audio]
        case "archive_audio": return [.audio]
        case "archive_video": return [.movie]
        case "scene_reference", "prop_reference", "style_reference": return [.image, .movie]
        case "source_document": return [.image, .plainText, .pdf, .json]
        default: return [.data]
        }
    }

    private var projectDeletionIsReady: Bool {
        PrivacySafety.canDeleteProject(
            preview: deletionPreview,
            confirmationTitle: projectDeletionConfirmation,
            deleteProductionSnapshots: deleteProductionSnapshots
        )
    }

    private var assetDependencyMessage: String {
        guard let report = assetDependencyReport else { return "尚未取得依赖报告。" }
        if report.productionRunIDs.isEmpty { return report.explanation }
        return "\(report.explanation)\n制作快照：\(report.productionRunIDs.joined(separator: "、"))"
    }

    private func presentRename() {
        guard let project = selectedProject else { return }
        renameTitle = project.title
        isRenamingProject = true
    }

    private func exportProject() {
        Task {
            guard let data = await model.exportSelectedProject() else { return }
            exportDocument = ProjectBackupDocument(data: data)
            isExportingProject = true
        }
    }

    private func exportPrivacy() {
        Task {
            guard let data = await model.exportPrivacyBundle() else { return }
            privacyDocument = PrivacyExportDocument(data: data)
            isExportingPrivacy = true
        }
    }

    private func prepareProjectDeletion() {
        deletionPreview = nil
        projectDeletionConfirmation = ""
        deleteProductionSnapshots = false
        isPresentingProjectDeletion = true
        Task {
            guard let preview = await model.selectedProjectDeletionPreview() else {
                isPresentingProjectDeletion = false
                return
            }
            deletionPreview = preview
        }
    }

    private func executeProjectDeletion() {
        guard projectDeletionIsReady else { return }
        let confirmation = projectDeletionConfirmation
        let deleteSnapshots = deleteProductionSnapshots
        Task {
            guard await model.deleteSelectedProject(
                confirmationTitle: confirmation,
                deleteProductionSnapshots: deleteSnapshots
            ) != nil else { return }
            isPresentingProjectDeletion = false
            deletionPreview = nil
            projectDeletionConfirmation = ""
            deleteProductionSnapshots = false
        }
    }

    private func inspectAssetDependencies(_ assetID: String) {
        Task {
            guard let report = await model.assetDependencies(assetID) else { return }
            assetDependencyReport = report
            isPresentingAssetDependencies = true
        }
    }

    private func presentMemoryEditor(_ card: MemoryCard) {
        editingMemoryID = card.id
        editingMemoryTitle = card.title
        editingMemoryDescription = card.description
        editingMemoryDate = card.approximateDate
        editingMemoryPlace = card.place
        editingMemoryStoryRelevance = card.storyRelevance
        editingMemoryAllowedUse = card.allowedUse
        isPresentingMemoryEditor = true
    }

    private func saveMemoryEdits() {
        guard let editingMemoryID else { return }
        Task {
            if await model.updateMemoryCard(
                id: editingMemoryID,
                title: editingMemoryTitle,
                description: editingMemoryDescription,
                approximateDate: editingMemoryDate,
                place: editingMemoryPlace,
                storyRelevance: editingMemoryStoryRelevance,
                allowedUse: editingMemoryAllowedUse
            ) {
                isPresentingMemoryEditor = false
                self.editingMemoryID = nil
            }
        }
    }

    private func presentProviderCredentials() {
        refreshCredentialStatus()
        seedanceSecretDraft = ""
        minimaxSecretDraft = ""
        openAIRealtimeSecretDraft = ""
        isPresentingProviderCredentials = true
    }

    private func presentRealtimeConsent() {
        do {
            realtimeCredentialIsConfigured = try keychain.contains(.openAIRealtime)
        } catch {
            realtimeCredentialIsConfigured = false
            model.errorMessage = error.localizedDescription
        }
        realtimeCloudConsent = false
        realtimeGuardianConsent = false
        isPresentingRealtimeConsent = true
    }

    private func beginRealtimeVoice() {
        guard realtimeCloudConsent,
              realtimeCredentialIsConfigured,
              selectedProject?.audienceMode != "child" || realtimeGuardianConsent else {
            return
        }
        isPresentingRealtimeConsent = false
        realtimeVoice.onUserTranscript = { text in
            model.receiveRealtimeTranscript(text, from: InterviewMessage.Speaker.user)
        }
        realtimeVoice.onAssistantTranscript = { text in
            model.receiveRealtimeTranscript(text, from: InterviewMessage.Speaker.nalu)
        }
        realtimeVoice.onInterviewAnswer = { answer in
            model.recordRealtimeFlowAnswer(answer)
        }
        let projectName = selectedProject?.title ?? "尚未命名的故事"
        let currentPrompt = model.currentInterviewPrompt
        let instructions = """
        你是 Nalu，一位耐心、简洁、适合老年人和儿童的中文语音采访者。
        当前项目叫“\(projectName)”。当前尚未完成的问题是：“\(currentPrompt)”
        这是会话开始时的问题。每次本地工具返回后，工具结果里的 nextPrompt 是最新权威；
        后续不要再回到旧问题，也不要凭记忆跳过本地采访步骤。
        用户不必服从固定流程。用户提出问题、质疑、闲聊或纠正时，必须先直接回答当下内容，
        不要答非所问；回答清楚后，再用一句自然的话回到尚未完成的问题。
        只有用户直接回答当前问题、回答界面刚刚明确开启的季纲/本集/剧本/批准任务，或明确说
        暂停、继续、重复问题、返回上一步，或明确说“暂停本集制作”“确认暂停本集制作”
        “不暂停”“恢复本集制作”时，才调用 record_interview_answer；调用后等本地结果
        返回，再简短复述结果并询问 nextPrompt。
        用户只是提问、抱怨、闲聊或纠正你的回答时不要调用工具。
        一次只问一个问题，句子简短，语速舒缓。允许用户停顿和随时插话。
        只有本地工具结果 accepted=true 才能说已经开始保存或批准。不得声称已经付费生成、删除、
        使用生物特征素材或发布任何内容；这些操作必须回到可见界面另行确认。
        """
        Task {
            await realtimeVoice.start(
                instructions: instructions,
                limitMinutes: realtimeSessionLimitMinutes
            )
        }
    }

    private func refreshCredentialStatus() {
        do {
            seedanceIsConfigured = try keychain.contains(.seedance)
            minimaxIsConfigured = try keychain.contains(.minimax)
            openAIRealtimeIsConfigured = try keychain.contains(.openAIRealtime)
            realtimeCredentialIsConfigured = openAIRealtimeIsConfigured
        } catch {
            model.errorMessage = error.localizedDescription
        }
    }

    private func saveCredential(_ credential: ProviderCredential, secret: String) {
        do {
            try keychain.set(secret, for: credential)
            if credential == .seedance { seedanceSecretDraft = "" }
            if credential == .minimax { minimaxSecretDraft = "" }
            if credential == .openAIRealtime { openAIRealtimeSecretDraft = "" }
            refreshCredentialStatus()
        } catch {
            model.errorMessage = error.localizedDescription
        }
    }

    private func removeCredential(_ credential: ProviderCredential) {
        do {
            try keychain.remove(credential)
            refreshCredentialStatus()
        } catch {
            model.errorMessage = error.localizedDescription
        }
    }

    private func importProject(_ result: Result<[URL], Error>) {
        do {
            guard let url = try result.get().first else { return }
            let accessing = url.startAccessingSecurityScopedResource()
            defer { if accessing { url.stopAccessingSecurityScopedResource() } }
            let data = try Data(contentsOf: url)
            Task { await model.restoreProject(from: data) }
        } catch {
            model.errorMessage = error.localizedDescription
        }
    }

    private func importAsset(_ result: Result<[URL], Error>) {
        do {
            guard let url = try result.get().first else { return }
            let accessing = url.startAccessingSecurityScopedResource()
            defer { if accessing { url.stopAccessingSecurityScopedResource() } }
            let data = try Data(contentsOf: url)
            let contentType = UTType(filenameExtension: url.pathExtension)?.preferredMIMEType
                ?? "application/octet-stream"
            let automaticImport = isAutomaticAssetImport
            let inferredName = url.deletingPathExtension().lastPathComponent
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let importedName = automaticImport
                ? (inferredName.isEmpty ? "家庭资料" : inferredName) : assetName
            let importedSubjectName = automaticImport ? "" : assetSubjectName
            let importedKind = automaticImport
                ? automaticAssetKind(for: contentType) : assetKind
            let importedConsent = automaticImport ? false : assetConsentGranted
            let importedGuardianApproval = automaticImport ? false : assetGuardianApproved
            let importedConsentStatement = automaticImport ? "" : assetConsentStatement
            let importedScope = automaticImport ? "project" : assetScope
            let memoryDescription = automaticImport ? "" : assetMemoryDescription
            let memoryDate = automaticImport ? "" : assetMemoryDate
            let memoryPlace = automaticImport ? "" : assetMemoryPlace
            let memoryRelationship = automaticImport ? "" : assetMemoryRelationship
            let memoryStoryRelevance = automaticImport ? "" : assetMemoryStoryRelevance
            let memoryAllowedUse = automaticImport ? "reference_only" : assetMemoryAllowedUse
            Task {
                let recognizedText = contentType.hasPrefix("image/")
                    ? await LocalTextRecognizer.recognize(in: data)
                    : ""
                await model.importAsset(
                    data: data,
                    filename: url.lastPathComponent,
                    contentType: contentType,
                    kind: importedKind,
                    name: importedName,
                    subjectName: importedSubjectName,
                    scope: importedScope,
                    consentGranted: importedConsent,
                    guardianApproved: importedGuardianApproval,
                    consentStatement: importedConsentStatement,
                    memoryDescription: automaticImport && !recognizedText.isEmpty
                        ? "Nalu 已在本机识别到图片文字，等待您用语音说明。"
                        : memoryDescription,
                    memoryDate: memoryDate,
                    memoryPlace: memoryPlace,
                    memoryRelationship: memoryRelationship,
                    memoryStoryRelevance: memoryStoryRelevance,
                    memoryAllowedUse: memoryAllowedUse,
                    recognizedText: recognizedText
                )
            }
        } catch {
            model.errorMessage = error.localizedDescription
        }
    }

    private func beginAutomaticAssetImport() {
        assetKind = "source_document"
        isAutomaticAssetImport = true
        isImportingAsset = true
    }

    private func automaticAssetKind(for contentType: String) -> String {
        if contentType.hasPrefix("audio/") { return "archive_audio" }
        if contentType.hasPrefix("video/") { return "archive_video" }
        return "source_document"
    }

    private func assetIsBiometricKind(_ kind: String) -> Bool {
        kind == "character_image" || kind == "voice_reference"
    }

    private func assetKindLabel(_ kind: String) -> String {
        assetKindOptions.first(where: { $0.value == kind })?.label ?? kind
    }

    private func assetScopeLabel(_ asset: NaluAsset) -> String {
        if let episodeID = asset.episodeID,
           let episode = model.episodes.first(where: { $0.id == episodeID }) {
            return "第 \(episode.episodeNumber) 集"
        }
        if asset.seasonID != nil { return "当前季" }
        return "整个项目"
    }

    private func assetIcon(_ kind: String) -> String {
        switch kind {
        case "character_image": "person.crop.rectangle"
        case "voice_reference": "waveform"
        case "archive_audio": "waveform.circle"
        case "archive_video": "video"
        case "scene_reference": "photo.on.rectangle"
        case "prop_reference": "shippingbox"
        case "style_reference": "paintpalette"
        default: "doc.text"
        }
    }

    private func memoryCardSummary(_ card: MemoryCard) -> String {
        [card.approximateDate, card.place, card.description]
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }

    private func beginProject() {
        Task { await model.beginProject() }
    }

    private func projectSummary(_ project: NaluProject) -> String {
        switch project.creativeFormat {
        case "documentary_series":
            return "纪录片系列 · 计划 \(project.plannedEpisodeCount) 章"
        case "animation_series":
            return "动画系列 · 计划 \(project.plannedEpisodeCount) 集"
        case "commercial_campaign":
            return "广告项目 · 计划 \(project.plannedEpisodeCount) 条成片"
        default:
            return "短剧系列 · 计划 \(project.plannedEpisodeCount) 集"
        }
    }

    private func repeatQuestion() {
        model.repeatCurrentQuestion()
    }

    private func toggleMicrophone() {
        Task { await model.toggleListening() }
    }
}
