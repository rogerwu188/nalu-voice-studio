import AVKit
import SwiftUI

// Operate: extend the existing shot-plan surface with reversible plain-language
// cuts. Inherit Nalu typography and native controls. Original media stays intact;
// saving is a draft, never an implied preview, approval, render or release.
@MainActor struct EpisodeEditingPanel: View {
    @State private var model: EpisodeEditingModel
    @State private var player: AVPlayer?
    @State private var previewTask: Task<Void, Never>?
    let onRead: (String) -> Void

    init(runID: String, planID: String, planSHA: String, onRead: @escaping (String) -> Void) {
        _model = State(initialValue: EpisodeEditingModel(runID: runID, planID: planID, planSHA: planSHA))
        self.onRead = onRead
    }

    var body: some View {
        DisclosureGroup("把本集镜头剪在一起") {
            VStack(alignment: .leading, spacing: 12) {
                Text(model.notice).naluFont(.body).fixedSize(horizontal: false, vertical: true)
                if model.busy { ProgressView("正在保存和核对本集素材") }
                Button("整理本集已采用的视频", systemImage: "film.stack") {
                    Task { await model.load(); onRead(model.notice) }
                }.buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
                ForEach(model.cuts.indices, id: \.self) { index in
                    let cut = model.cuts[index]
                    VStack(alignment: .leading, spacing: 8) {
                        Text("镜头 \(index + 1)：保留 \(cut.source_in_seconds, specifier: "%.1f") 到 \(cut.source_out_seconds, specifier: "%.1f") 秒")
                            .naluFont(.body)
                        ViewThatFits(in: .horizontal) {
                            HStack { controls(index: index) }
                            VStack(alignment: .leading) { controls(index: index) }
                        }.buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
                    }.padding(.vertical, 6)
                }
                if !model.cuts.isEmpty {
                    Text("每个镜头需选出保留片段。这里只保存草稿，原视频不变；成片预览和确认尚未完成。")
                        .naluFont(.body).fixedSize(horizontal: false, vertical: true)
                    Button("保存这些剪辑调整", systemImage: "square.and.arrow.down") {
                        Task { await model.save(); onRead(model.notice) }
                    }.buttonStyle(.borderedProminent).controlSize(.large).disabled(!model.canSave)
                }
                if model.saved != nil {
                    Button("制作无配音画面预览", systemImage: "play.rectangle") {
                        previewTask = Task { await model.preview(); if !Task.isCancelled { onRead(model.notice) } }
                    }.buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
                }
                if let player {
                    Text("画面预览 · 尚未配音或验收").naluFont(.body)
                    VideoPlayer(player: player).frame(minHeight: 240, idealHeight: 360)
                        .accessibilityLabel("本集剪辑画面预览，没有配音，不是最终成片")
                    Button("从头播放剪辑预览", systemImage: "play.fill") {
                        player.seek(to: .zero); player.play()
                    }.buttonStyle(.borderedProminent).controlSize(.large)
                }
            }.padding(.vertical, 8)
        }.naluFont(.body).accessibilityIdentifier("nalu.episode.editing")
        .onChange(of: model.previewURL) { _, url in
            player?.pause(); player = url.map { AVPlayer(url: $0) }
        }
        .onDisappear {
            previewTask?.cancel(); previewTask = nil
            player?.pause(); player = nil
            model.discardPreview()
        }
    }

    @ViewBuilder private func controls(index: Int) -> some View {
        Button("去掉开头半秒") { model.trim(index: index, beginning: true) }
        Button("去掉结尾半秒") { model.trim(index: index, beginning: false) }
        Button("恢复这个镜头") { model.reset(index: index) }
    }
}
