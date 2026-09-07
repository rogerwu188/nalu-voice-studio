import AVKit
import SwiftUI

@MainActor struct VideoCandidatePanel: View {
    @State private var model: VideoCandidateModel
    @State private var player: AVPlayer?
    @State private var operation: Task<Void, Never>?
    let onRead: (String) -> Void

    init(binding: VideoSubmissionObservation, onRead: @escaping (String) -> Void) {
        _model = State(initialValue: VideoCandidateModel(binding: binding))
        self.onRead = onRead
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if model.busy { ProgressView("正在取回这个镜头的进度或视频") }
            Text(model.notice).naluFont(.body)
            if let player {
                VideoPlayer(player: player).frame(minHeight: 240, idealHeight: 360)
                    .accessibilityLabel("当前镜头视频预览，尚未验收")
                Button("从头播放这个镜头", systemImage: "play.fill") {
                    player.seek(to: .zero); player.play()
                }.buttonStyle(.borderedProminent).controlSize(.large)
            }
            Button("查看生成进度并取回视频", systemImage: "arrow.down.circle") {
                operation = Task { await model.refresh(); if !Task.isCancelled { onRead(model.notice) } }
            }.buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
                .accessibilityHint("查询原来的任务，不会重新生成或自动发行")
        }
        .accessibilityIdentifier("nalu.shot.video-candidate")
        .task { await model.restore() }
        .onChange(of: model.fileURL) { _, url in
            player?.pause()
            player = url.map { AVPlayer(url: $0) }
        }
        .onDisappear {
            operation?.cancel(); operation = nil
            player?.pause(); player = nil
            model.discardPlayback()
        }
    }
}
