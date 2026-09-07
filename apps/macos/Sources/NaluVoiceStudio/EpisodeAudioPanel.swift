import AVFoundation
import CryptoKit
import SwiftUI

// Extend the incumbent native Operate surface: no IDs, no professional form.
@MainActor struct EpisodeAudioPanel: View {
    @State private var model: EpisodeAudioModel
    @State private var showingConfirmation = false
    @State private var player: AVAudioPlayer?
    @State private var auditionTask: Task<Void, Never>?
    @State private var playbackNotice = "试听不会自动确认配音。"
    @State private var playing = false
    let onRead: (String) -> Void

    init(sound: EpisodeSoundPlan, onRead: @escaping (String) -> Void) {
        _model = State(initialValue: EpisodeAudioModel(sound: sound))
        self.onRead = onRead
    }

    var body: some View {
        DisclosureGroup("给这集配上录音") {
            VStack(alignment: .leading, spacing: 12) {
                Text(model.notice).fixedSize(horizontal: false, vertical: true)
                if model.busy { ProgressView("正在读取或保存录音素材") }
                Button("刷新可用录音", systemImage: "arrow.clockwise") {
                    stop()
                    Task { await model.load(); onRead(model.notice) }
                }.disabled(model.busy)
                Text(playbackNotice).fixedSize(horizontal: false, vertical: true)
                if playing {
                    Button("停止试听", systemImage: "stop.fill") { stop() }
                }
                ForEach(model.sound.payload.cues) { cue in
                    VStack(alignment: .leading, spacing: 8) {
                        Text("第 \(cue.shot_index + 1) 段 · \(cue.end_seconds - cue.start_seconds, specifier: "%.1f") 秒")
                        Text(cue.dialogue_or_narration.isEmpty ? "这一段没有旁白文字。" : cue.dialogue_or_narration)
                            .fixedSize(horizontal: false, vertical: true)
                        Button("读一下这一段", systemImage: "speaker.wave.2") { stop(); onRead(cue.dialogue_or_narration) }
                        Picker("使用哪段录音", selection: Binding(get: { model.selectedAssetID(cue.id) }, set: { model.select($0, for: cue.id); stop() })) {
                            Text("请选择录音").tag("")
                            ForEach(model.recordings) { recording in Text(recording.name).tag(recording.id) }
                        }.disabled(!model.loaded || model.busy || model.pending != nil)
                        if let recording = selected(cue.id) {
                            Text("从录音第 \(model.sourceOffset(cue.id), specifier: "%.1f") 秒开始")
                            ViewThatFits(in: .horizontal) {
                                HStack { offsetControls(cue.id) }
                                VStack(alignment: .leading) { offsetControls(cue.id) }
                            }.disabled(model.busy || !model.loaded || model.pending != nil)
                            Button("试听这段录音", systemImage: "play.fill") { audition(recording, cue: cue) }
                                .disabled(model.busy || !model.loaded)
                            Button("把录音用于这一段", systemImage: "link") {
                                stop()
                                if model.begin(shotIndex: cue.id, assetID: recording.id, sourceIn: model.sourceOffset(cue.id)) {
                                    onRead(model.readback); showingConfirmation = true
                                }
                            }.buttonStyle(.borderedProminent)
                                .disabled(model.busy || !model.loaded || model.pending != nil)
                        }
                        if model.attached[cue.id] != nil { Text("已绑定录音素材 · 尚待试听确认与字幕核对") }
                    }.padding(.vertical, 8)
                }
                if model.pending != nil {
                    Button(model.uncertain ? "重试绑定刚才的录音" : "继续确认录音", systemImage: "arrow.clockwise") {
                        stop(); onRead(model.readback); showingConfirmation = true
                    }.disabled(model.busy)
                }
            }.buttonStyle(.bordered).controlSize(.large).padding(.vertical, 8)
        }.naluFont(.body).accessibilityIdentifier("nalu.episode.audio")
        .task { await model.load() }
        .onDisappear { stop() }
        .confirmationDialog(model.readback, isPresented: $showingConfirmation, titleVisibility: .visible) {
            Button("确认绑定录音素材") { Task { await model.confirm(); onRead(model.notice) } }
                .disabled(model.busy || model.pending == nil)
            Button(model.uncertain ? "稍后核对" : "先不选择", role: .cancel) { model.cancelUnsubmitted() }
        }
    }

    private func selected(_ index: Int) -> NaluAsset? {
        model.recordings.first { $0.id == model.selectedAssetID(index) }
    }

    @ViewBuilder private func offsetControls(_ index: Int) -> some View {
        Button("早半秒") { stop(); model.setOffset(max(0, model.sourceOffset(index) - 0.5), for: index) }
        Button("晚半秒") { stop(); model.setOffset(min(1800, model.sourceOffset(index) + 0.5), for: index) }
        Button("从头开始") { stop(); model.setOffset(0, for: index) }
    }

    private func stop() {
        auditionTask?.cancel(); auditionTask = nil
        player?.stop(); player = nil; playing = false
        playbackNotice = "试听已停止；没有改变配音确认。"
    }

    private func audition(_ recording: NaluAsset, cue: EpisodeSoundPlan.Cue) {
        stop(); playbackNotice = "正在读取录音…"
        let sourceIn = model.sourceOffset(cue.id)
        auditionTask = Task {
            do {
                let data = try await Task.detached(priority: .userInitiated) {
                    try EpisodeAudioPreview.read(recording)
                }.value
                guard !Task.isCancelled else { return }
                let audio = try AVAudioPlayer(data: data)
                let duration = cue.end_seconds - cue.start_seconds
                guard sourceIn.isFinite, sourceIn >= 0, audio.duration.isFinite,
                      audio.duration >= sourceIn + duration, audio.prepareToPlay() else {
                    throw LibrarySnapshotRefreshError.contextChanged
                }
                audio.currentTime = sourceIn
                guard audio.play() else { throw LibrarySnapshotRefreshError.contextChanged }
                player = audio; playing = true
                playbackNotice = "正在试听：\(recording.name) · 第 \(cue.id + 1) 段"
                while audio.isPlaying && audio.currentTime < sourceIn + duration {
                    try await Task.sleep(nanoseconds: 100_000_000)
                }
                audio.stop(); player = nil; playing = false
                playbackNotice = "试听结束。这里只播放录音，没有自动采用或确认字幕。"
            } catch {
                guard !Task.isCancelled else { return }
                player?.stop(); player = nil; playing = false
                playbackNotice = "这段录音暂时无法试听或时长不足。请换一段或重新导入，原文件保留。"
            }
        }
    }
}

enum EpisodeAudioPreview {
    static func read(_ recording: NaluAsset) throws -> Data {
        guard recording.consentGranted, ["archive_audio", "voice_reference"].contains(recording.kind),
              let url = URL(string: recording.localURI), url.isFileURL,
              url.host == nil || url.host == "" || url.host == "localhost",
              url.standardizedFileURL == url.resolvingSymlinksInPath().standardizedFileURL,
              case .string(let expected) = recording.metadata["sha256"] else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let size = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
        guard size.isRegularFile == true, let count = size.fileSize, count > 0, count <= 100 * 1024 * 1024 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let data = try Data(contentsOf: url)
        guard data.count == count, SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == expected else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        return data
    }
}
