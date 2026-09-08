import SwiftUI

@MainActor struct EpisodeSoundSelectionPanel: View {
    @State private var model: EpisodeSoundSelectionModel
    @State private var operation: Task<Void, Never>?
    let onRead: (String) -> Void

    init(sound: EpisodeSoundPlan, onRead: @escaping (String) -> Void) {
        _model = State(initialValue: EpisodeSoundSelectionModel(sound: sound))
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
        }.naluFont(.body).accessibilityIdentifier("nalu.episode.sound-selection")
            .task { await model.load() }
            .onDisappear { operation?.cancel(); operation = nil }
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
}
