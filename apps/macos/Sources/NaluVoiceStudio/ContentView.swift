import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @Environment(VoiceInterviewViewModel.self) private var model
    @State private var isRenamingProject = false
    @State private var renameTitle = ""
    @State private var isImportingProject = false
    @State private var isExportingProject = false
    @State private var exportDocument: ProjectBackupDocument?
    @State private var isScriptEditorExpanded = false
    @State private var isAssetEditorExpanded = false
    @State private var isImportingAsset = false
    @State private var assetKind = "character_image"
    @State private var assetName = ""
    @State private var assetSubjectName = ""
    @State private var assetConsentGranted = false
    @State private var assetGuardianApproved = false
    @State private var assetConsentStatement = ""
    @State private var assetScope = "project"
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
                model.errorMessage = error.localizedDescription
            }
            await model.load()
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
                }
                Spacer()
                Button("添加照片 / 视频", systemImage: "photo.badge.plus") {
                    assetKind = "character_image"
                    isAssetEditorExpanded = true
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(selectedProject == nil)
                Button("再说一遍", action: repeatQuestion).controlSize(.large)
            }
            .padding(24)
            Divider()
            if selectedProject != nil {
                DisclosureGroup(
                    "上传人物照片、家庭视频、声音或参考资料",
                    isExpanded: $isAssetEditorExpanded
                ) {
                    assetEditor.padding(.top, 10)
                }
                .font(.headline)
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                .background(Color.blue.opacity(0.06))
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
                    Task { await model.beginSeasonPlanDictation() }
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
                    Task { await model.beginSeasonPlanVoiceApproval() }
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
                        Task { await model.beginEpisodePlanDictation() }
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
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 14)
        .background(Color.secondary.opacity(0.04))
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
                    Task { await model.beginScriptDictation() }
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
                    Task { await model.beginScriptVoiceApproval() }
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

    private var assetEditor: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("文件会复制到这个项目的本地目录，不会只记住原文件位置。")
                .font(.body)
                .foregroundStyle(.secondary)
            HStack {
                Picker("素材类型", selection: $assetKind) {
                    ForEach(assetKindOptions, id: \.value) { option in
                        Text(option.label).tag(option.value)
                    }
                }
                .frame(maxWidth: 260)
                TextField("素材名称", text: $assetName)
                    .textFieldStyle(.roundedBorder)
            }
            if assetIsBiometric {
                TextField("照片或声音属于谁", text: $assetSubjectName)
                    .textFieldStyle(.roundedBorder)
                Toggle("本人或合法授权人同意用于本项目短剧制作", isOn: $assetConsentGranted)
                TextField("请写明授权范围，例如：同意把这张照片用于《我的故事》", text: $assetConsentStatement)
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
            HStack {
                Button("选择并复制文件", systemImage: "plus.rectangle.on.folder") {
                    isImportingAsset = true
                }
                .buttonStyle(.borderedProminent)
                .disabled(!assetImportIsReady)
                if assetIsBiometric && !assetConsentGranted {
                    Label("人物照片和声音必须先取得明确授权", systemImage: "hand.raised.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }
            if model.assets.isEmpty {
                Text("这个项目还没有素材。")
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
                        }
                        Spacer()
                        if assetIsBiometricKind(asset.kind) && asset.consentGranted {
                            Button("撤销授权", role: .destructive) {
                                Task { await model.revokeAssetConsent(asset.id) }
                            }
                        }
                        Button("检查删除", systemImage: "trash") {
                            inspectAssetDependencies(asset.id)
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

            Toggle("允许把脱敏后的文字加入待审核改进队列", isOn: $feedbackShareAuthorized)
            Text("默认只保存在本机；不会上传照片、视频、声音、密钥，也不会未经审核自动修改程序。")
                .font(.callout)
                .foregroundStyle(.secondary)
            if selectedProject?.audienceMode == "child", feedbackShareAuthorized {
                Toggle("监护人同意提交这条改进意见", isOn: $feedbackGuardianApproved)
            }
            HStack {
                Button("取消", role: .cancel) { isPresentingFeedback = false }
                Spacer()
                Button("保存意见") {
                    Task {
                        if await model.saveFeedback(
                            category: feedbackCategory,
                            shareAuthorized: feedbackShareAuthorized,
                            guardianApproval: feedbackGuardianApproved
                        ) {
                            isPresentingFeedback = false
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
            }
        }
        .padding(28)
        .frame(minWidth: 680, minHeight: 560)
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

    private var exportFilename: String {
        let title = selectedProject?.title ?? "Nalu项目"
        return "\(title)-Nalu备份.json"
    }

    private var privacyExportFilename: String {
        let title = selectedProject?.title ?? "Nalu项目"
        return "\(title)-Nalu隐私包.zip"
    }

    private var assetKindOptions: [(value: String, label: String)] {
        [
            ("character_image", "人物照片"),
            ("voice_reference", "人物声音"),
            ("scene_reference", "场景参考"),
            ("prop_reference", "道具参考"),
            ("style_reference", "画面风格参考"),
            ("source_document", "文字或 PDF 资料"),
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
        switch assetKind {
        case "character_image": [.image]
        case "voice_reference": [.audio]
        case "scene_reference", "prop_reference", "style_reference": [.image, .movie]
        case "source_document": [.plainText, .pdf, .json]
        default: [.data]
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

    private func presentProviderCredentials() {
        refreshCredentialStatus()
        seedanceSecretDraft = ""
        minimaxSecretDraft = ""
        openAIRealtimeSecretDraft = ""
        isPresentingProviderCredentials = true
    }

    private func refreshCredentialStatus() {
        do {
            seedanceIsConfigured = try keychain.contains(.seedance)
            minimaxIsConfigured = try keychain.contains(.minimax)
            openAIRealtimeIsConfigured = try keychain.contains(.openAIRealtime)
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
            let importedName = assetName
            let importedSubjectName = assetSubjectName
            let importedKind = assetKind
            let importedConsent = assetConsentGranted
            let importedGuardianApproval = assetGuardianApproved
            let importedConsentStatement = assetConsentStatement
            let importedScope = assetScope
            Task {
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
                    consentStatement: importedConsentStatement
                )
            }
        } catch {
            model.errorMessage = error.localizedDescription
        }
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
        case "scene_reference": "photo.on.rectangle"
        case "prop_reference": "shippingbox"
        case "style_reference": "paintpalette"
        default: "doc.text"
        }
    }

    private func beginProject() {
        Task { await model.beginProject() }
    }

    private func projectSummary(_ project: NaluProject) -> String {
        switch project.creativeFormat {
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
