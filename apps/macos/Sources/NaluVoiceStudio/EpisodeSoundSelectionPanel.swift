import SwiftUI

@MainActor struct EpisodeSoundSelectionPanel: View {
    @State private var model: EpisodeSoundSelectionModel
    @State private var operation: Task<Void, Never>?
    @State private var mix: EpisodeMixModel
    @State private var mixTask: Task<Void, Never>?
    @State private var confirmingRender = false
    @State private var confirmingRepair = false
    let onRead: (String) -> Void

    init(sound: EpisodeSoundPlan, onRead: @escaping (String) -> Void) {
        _model = State(initialValue: EpisodeSoundSelectionModel(sound: sound))
        _mix = State(initialValue: EpisodeMixModel(sound: sound))
        self.onRead = onRead
    }

    var body: some View {
        DisclosureGroup("使用已有配乐和环境声") {
            VStack(alignment: .leading, spacing: 12) {
                Text("这里只使用您已添加并授权的音频。每段需要覆盖本集时长；不会自动购买或生成声音。")
                    .fixedSize(horizontal: false, vertical: true)
                Text(model.notice).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("nalu.episode.sound.notice")
                if model.busy { ProgressView("正在核对和准备声音素材") }
                Button("刷新声音素材", systemImage: "arrow.clockwise") {
                    perform { await model.load() }
                }.disabled(model.busy || operation != nil)
                Button("读一下当前情况", systemImage: "speaker.wave.2") { onRead(model.notice) }
                if model.loaded && model.assets.isEmpty {
                    Text("请用页面上的“选择家庭资料”添加音频，确认授权后，再回来刷新。")
                        .fixedSize(horizontal: false, vertical: true)
                }
                ForEach(EpisodeSoundRole.allCases, id: \.self) { role in
                    VStack(alignment: .leading, spacing: 8) {
                        Picker(role.title, selection: Binding(
                            get: { model.selections[role] ?? "" },
                            set: { model.select($0, for: role) })) {
                            Text("请选择已有音频").tag("")
                            if let selected = model.selections[role], !selected.isEmpty,
                               !model.assets.contains(where: { $0.id == selected }) {
                                Text("原来的素材暂时不可用，请重新选择").tag(selected)
                            }
                            ForEach(model.assets) { asset in Text(asset.name).tag(asset.id) }
                        }.disabled(!model.loaded || model.busy || operation != nil || model.pending != nil)
                            .accessibilityIdentifier("nalu.episode.sound.\(role.rawValue).selection")
                        if let receipt = model.receipts[role] {
                            Label("\(role.title)已准备好", systemImage: "checkmark.circle")
                            if let asset = model.assets.first(where: { $0.id == receipt.payload.binding.asset_id }) {
                                Text(asset.name).fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        Button(model.pending?.layer == role ? "重试准备刚才的\(role.title)" : "准备\(role.title)",
                               systemImage: "waveform") {
                            perform { await model.prepare(role) }
                        }.disabled(!canPrepare(role))
                            .accessibilityIdentifier("nalu.episode.sound.\(role.rawValue).prepare")
                    }.padding(.vertical, 8)
                }
                if model.pending != nil {
                    Button("重新选择声音素材", systemImage: "arrow.uturn.backward") {
                        model.chooseAgain(); onRead(model.notice)
                    }.disabled(model.busy || operation != nil)
                }
                if model.mixSources != nil {
                    Text("这些声音素材已准备好。配音、字幕与最终混音仍需核对，这还不是成片。")
                        .fixedSize(horizontal: false, vertical: true)
                }
            }.buttonStyle(.bordered).controlSize(.large).padding(.vertical, 8)
                .disabled(mix.busy || mix.prepared != nil)
            VStack(alignment: .leading, spacing: 12) {
                Text(mix.notice).fixedSize(horizontal: false, vertical: true)
                if mix.busy { ProgressView("正在准备或合成本集视频") }
                if let repair = mix.repairPlan {
                    ForEach(repair.repair_tasks.indices, id: \.self) { index in
                        Text(repair.repair_tasks[index].required_action)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if mix.repairVersion == nil {
                        Button("保留原片，准备修订版", systemImage: "doc.on.doc") {
                            onRead("原成片会保留。这一步只准备修订版本，不会扣费、生成视频或发行。确认准备吗？")
                            confirmingRepair = true
                        }.buttonStyle(.borderedProminent)
                            .disabled(mix.busy || mixTask != nil)
                            .accessibilityIdentifier("nalu.episode.mix.prepare-repair")
                    } else {
                        Text("请返回本集制作进度，查看新版本并继续核对制作方案。")
                            .fixedSize(horizontal: false, vertical: true)
                    }
                } else if mix.prepared == nil {
                    Button("核对本集并准备合成", systemImage: "film.stack") {
                        guard let sources = model.mixSources else { return }
                        runMix { await mix.prepare(sources: sources) }
                    }.disabled(model.mixSources == nil || operation != nil || mix.busy || mixTask != nil)
                } else if mix.result == nil {
                    Button(mix.attempted ? "重试核对同一版合成" : "合成这一集", systemImage: "film") {
                        onRead("将使用刚才核对的方案，在本机合成这一集。不会发布。确认开始吗？")
                        confirmingRender = true
                    }.buttonStyle(.borderedProminent).disabled(mix.busy || mixTask != nil)
                        .accessibilityIdentifier("nalu.episode.mix.render")
                    if !mix.attempted {
                        Button("先调整素材", systemImage: "pencil") { mix.changeSelection(); onRead(mix.notice) }
                            .disabled(mix.busy || mixTask != nil)
                    }
                }
                Button("读一下合成进度", systemImage: "speaker.wave.2") { onRead(mix.notice) }
            }.buttonStyle(.bordered).controlSize(.large).padding(.vertical, 8)
        }.naluFont(.body).accessibilityIdentifier("nalu.episode.sound-selection")
            .task { await model.load(); await mix.restoreRepair() }
            .onDisappear { operation?.cancel(); operation = nil; mixTask?.cancel(); mixTask = nil }
            .confirmationDialog("在这台 Mac 合成这一集？完成后仍需检查，不会自动发布。",
                                isPresented: $confirmingRender, titleVisibility: .visible) {
                Button("确认，开始合成") { runMix { await mix.renderConfirmed() } }
                    .disabled(mix.busy || mixTask != nil)
                Button("先不合成", role: .cancel) {}
            }
            .confirmationDialog("保留原成片，准备一个修订版本？不会扣费、生成视频或发行。",
                                isPresented: $confirmingRepair, titleVisibility: .visible) {
                Button("确认，准备修订版") {
                    runMix { await mix.prepareRepairConfirmed(confirmation: "用户确认保留原成片并准备修订版本，不授权付费生成或发行") }
                }.disabled(mix.busy || mixTask != nil)
                Button("先不修订", role: .cancel) {}
            }
    }

    private func canPrepare(_ role: EpisodeSoundRole) -> Bool {
        guard model.loaded, !model.busy, operation == nil else { return false }
        if let pending = model.pending { return pending.layer == role }
        return model.assets.contains { $0.id == model.selections[role] }
    }

    private func perform(_ action: @escaping @MainActor () async -> Void) {
        guard operation == nil else { return }
        operation = Task {
            await action()
            guard !Task.isCancelled else { return }
            operation = nil
            onRead(model.notice)
        }
    }

    private func runMix(_ action: @escaping @MainActor () async -> Void) {
        guard mixTask == nil else { return }
        mixTask = Task {
            await action()
            guard !Task.isCancelled else { return }
            mixTask = nil
            onRead(mix.notice)
        }
    }
}
