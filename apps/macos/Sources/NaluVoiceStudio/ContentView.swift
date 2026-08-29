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
    @State private var scopeAssetToEpisode = false
    @State private var isExportingPrivacy = false
    @State private var privacyDocument: PrivacyExportDocument?

    var body: some View {
        HSplitView {
            sidebar.frame(minWidth: 260, idealWidth: 290, maxWidth: 340)
            interview
        }
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
                        Text("计划 \(project.plannedEpisodeCount) 集")
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
            if let project = selectedProject {
                Button(
                    project.archivedAt == nil ? "归档这个项目" : "移回项目列表",
                    systemImage: project.archivedAt == nil ? "archivebox" : "tray.and.arrow.up"
                ) {
                    Task { await model.setSelectedProjectArchived(project.archivedAt == nil) }
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
                    Text(model.runtimeStatus).foregroundStyle(.secondary)
                }
                Spacer()
                Button("再说一遍", action: repeatQuestion).controlSize(.large)
            }
            .padding(24)
            Divider()
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
            ScrollView {
                LazyVStack(spacing: 18) {
                    ForEach(model.messages) { message in
                        bubble(message)
                    }
                }
                .padding(28)
            }
            if !model.transcript.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(model.transcript).font(.title3)
                    if model.transcriptConfidence > 0 {
                        Text(model.transcriptConfidence < 0.2 ? "我可能没听清" : "我听清了")
                            .font(.caption)
                            .foregroundStyle(model.transcriptConfidence < 0.2 ? .orange : .secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .background(Color.blue.opacity(0.08))
                .padding(.horizontal, 24)
            }
            if let planningVoiceLabel = model.planningVoiceLabel {
                Label("当前语音任务：\(planningVoiceLabel)", systemImage: "waveform.badge.mic")
                    .font(.headline)
                    .foregroundStyle(.blue)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 24)
                    .padding(.top, 12)
            }
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
            DisclosureGroup("人物、声音和参考素材", isExpanded: $isAssetEditorExpanded) {
                assetEditor
                    .padding(.top, 10)
            }
            .font(.headline)
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
            Toggle("只用于当前选中的这一集", isOn: $scopeAssetToEpisode)
                .disabled(selectedEpisode == nil)
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
        guard !assetName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return false
        }
        guard !scopeAssetToEpisode || selectedEpisode != nil else { return false }
        guard assetIsBiometric else { return true }
        guard assetConsentGranted,
              !assetSubjectName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !assetConsentStatement.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return false
        }
        return selectedProject?.audienceMode != "child" || assetGuardianApproved
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
            let importedEpisodeScope = scopeAssetToEpisode
            Task {
                await model.importAsset(
                    data: data,
                    filename: url.lastPathComponent,
                    contentType: contentType,
                    kind: importedKind,
                    name: importedName,
                    subjectName: importedSubjectName,
                    scopeToSelectedEpisode: importedEpisodeScope,
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
        guard let episodeID = asset.episodeID,
              let episode = model.episodes.first(where: { $0.id == episodeID }) else {
            return "整个项目"
        }
        return "第 \(episode.episodeNumber) 集"
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
        model.beginProject()
    }

    private func repeatQuestion() {
        model.repeatCurrentQuestion()
    }

    private func toggleMicrophone() {
        Task { await model.toggleListening() }
    }
}
