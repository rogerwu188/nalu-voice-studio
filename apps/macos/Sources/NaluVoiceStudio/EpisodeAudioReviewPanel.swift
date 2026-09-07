import SwiftUI

@MainActor struct EpisodeAudioReviewPanel: View {
    @State private var model: EpisodeAudioReviewModel
    @State private var showingConfirmation = false
    @State private var transcriptTask: Task<Void, Never>?
    let onRead: (String) -> Void

    init(sound: EpisodeSoundPlan, take: EpisodeAudioTake, onRead: @escaping (String) -> Void) {
        _model = State(initialValue: EpisodeAudioReviewModel(sound: sound, take: take))
        self.onRead = onRead
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.notice).fixedSize(horizontal: false, vertical: true)
            if model.busy { ProgressView(transcriptTask == nil ? "正在核对录音确认结果" : "正在处理字幕草稿") }
            if model.pending == nil {
                Button("听过了，采用这段录音", systemImage: "checkmark.circle") { begin(.accept) }
                    .buttonStyle(.borderedProminent)
                    .disabled(!model.loaded || model.busy || model.latest?.take_approved == true)
                    .accessibilityIdentifier("nalu.episode.audio.accept")
                Button("这段录音还要调整", systemImage: "pencil") { begin(.reject) }
                    .disabled(!model.loaded || model.busy)
            } else {
                Button(model.uncertain ? "重试刚才的录音确认" : "继续确认录音", systemImage: "arrow.clockwise") {
                    onRead(model.readback); showingConfirmation = true
                }.disabled(model.busy)
            }
            Button("核对录音确认记录", systemImage: "list.bullet.clipboard") {
                Task { await model.load(); onRead(model.notice) }
            }.disabled(model.busy)
                .accessibilityIdentifier("nalu.episode.audio.recover-review")
            if model.loaded, model.latest?.take_approved == true {
                Divider()
                Text("从这段录音整理字幕").fontWeight(.semibold)
                Text("只在这台 Mac 上识别。识别后先保存草稿，核对后才能用于成片。")
                    .fixedSize(horizontal: false, vertical: true)
                if model.hasUnsavedTranscript {
                    Button("重试保存字幕，不重新识别", systemImage: "arrow.clockwise") {
                        performTranscriptWork { await model.savePendingTranscript() }
                    }.disabled(model.busy)
                } else {
                    Button(model.transcriptReceipt == nil ? "把录音整理成字幕" : "重新识别这段录音", systemImage: "text.bubble") {
                        performTranscriptWork { await model.prepareTranscript() }
                    }.buttonStyle(.borderedProminent).disabled(!model.canPrepareTranscript)
                        .accessibilityIdentifier("nalu.episode.transcript.start")
                }
                Button("恢复已保存的字幕草稿", systemImage: "arrow.clockwise") {
                    performTranscriptWork { await model.recoverTranscript() }
                }.disabled(model.busy || model.pending != nil || model.uncertain)
                if transcriptTask != nil {
                    Button("停止这次字幕处理", systemImage: "stop.fill") { transcriptTask?.cancel() }
                        .accessibilityIdentifier("nalu.episode.transcript.cancel")
                }
                if let text = model.transcriptReceipt?.payload.transcript ?? model.transcript?.transcript {
                    Text(model.hasUnsavedTranscript ? "字幕草稿 · 保存尚未确认" : "字幕草稿 · 已保存，尚待核对")
                    Text(text).fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                    Button("读一下字幕草稿", systemImage: "speaker.wave.2") { onRead(text) }.disabled(model.busy)
                    DisclosureGroup("查看本段录音中的时间") {
                        let words = model.transcriptReceipt?.payload.segments ?? model.transcript?.segments ?? []
                        ForEach(Array(words.enumerated()), id: \.offset) { _, word in
                            Text("\(word.startSeconds, specifier: "%.2f")–\(word.endSeconds, specifier: "%.2f") 秒：\(word.text)")
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                if let receipt = model.transcriptReceipt {
                    RecordingCaptionPanel(transcript: receipt, onRead: onRead)
                        .id(receipt.id)
                        .disabled(model.busy || model.pending != nil)
                }
            }
        }.naluFont(.body).buttonStyle(.bordered).controlSize(.large)
            .accessibilityIdentifier("nalu.episode.audio.review")
            .task { await model.load(); await model.recoverTranscript() }
            .onDisappear { transcriptTask?.cancel(); transcriptTask = nil }
            .confirmationDialog(model.readback, isPresented: $showingConfirmation, titleVisibility: .visible) {
                Button(model.pending?.decision == .accept ? "确认采用这段录音" : "确认需要调整") {
                    Task { await model.confirm(); onRead(model.notice) }
                }.disabled(model.busy || model.pending == nil)
                Button(model.uncertain ? "稍后核对" : "先不决定", role: .cancel) { model.cancelUnsubmitted() }
            }
    }

    private func begin(_ decision: EpisodeAudioReviewDraft.Decision) {
        if model.begin(decision) { onRead(model.readback); showingConfirmation = true }
    }

    private func performTranscriptWork(_ work: @escaping @MainActor () async -> Void) {
        guard transcriptTask == nil, !model.busy else { return }
        onRead("正在处理这段录音的字幕，原录音会保留。")
        transcriptTask = Task {
            defer { transcriptTask = nil }
            await work()
            if !Task.isCancelled { onRead(model.notice) }
        }
    }
}
