import SwiftUI

@MainActor struct EpisodeAudioReviewPanel: View {
    @State private var model: EpisodeAudioReviewModel
    @State private var showingConfirmation = false
    let onRead: (String) -> Void

    init(sound: EpisodeSoundPlan, take: EpisodeAudioTake, onRead: @escaping (String) -> Void) {
        _model = State(initialValue: EpisodeAudioReviewModel(sound: sound, take: take))
        self.onRead = onRead
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(model.notice).fixedSize(horizontal: false, vertical: true)
            if model.busy { ProgressView("正在核对录音确认结果") }
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
        }.naluFont(.body).buttonStyle(.bordered).controlSize(.large)
            .accessibilityIdentifier("nalu.episode.audio.review")
            .task { await model.load() }
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
}
