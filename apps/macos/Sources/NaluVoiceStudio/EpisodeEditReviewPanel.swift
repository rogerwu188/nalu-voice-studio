import SwiftUI

@MainActor struct EpisodeEditReviewPanel: View {
    @State private var model: EpisodeEditReviewModel
    @State private var showingConfirmation = false
    let onRead: (String) -> Void

    init(edit: EpisodeEditingEvent, picture: EpisodePicture, onRead: @escaping (String) -> Void) {
        _model = State(initialValue: EpisodeEditReviewModel(edit: edit, picture: picture))
        self.onRead = onRead
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.notice).naluFont(.body).fixedSize(horizontal: false, vertical: true)
            if model.busy { ProgressView("正在保存或核对剪辑决定") }
            if model.pending == nil {
                Button("看过了，采用这个剪辑", systemImage: "checkmark.circle") { begin(.accept) }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .disabled(!model.loaded || model.busy)
                Button("这个剪辑还要修改", systemImage: "pencil") { begin(.reject) }
                    .buttonStyle(.bordered).controlSize(.large)
                    .disabled(!model.loaded || model.busy)
            } else {
                Button(model.uncertain ? "重试刚才的确认" : "继续确认", systemImage: "arrow.clockwise") {
                    onRead(model.readback)
                    showingConfirmation = true
                }.buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
            }
            Button("核对剪辑确认记录", systemImage: "list.bullet.clipboard") {
                Task { await model.load(); onRead(model.notice) }
            }.buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
        }
        .accessibilityIdentifier("nalu.episode.edit-review")
        .task { await model.load() }
        .confirmationDialog(model.readback, isPresented: $showingConfirmation, titleVisibility: .visible) {
            Button(model.pending?.decision == .accept ? "确认采用剪辑和时长" : "确认退回修改") {
                Task { await model.confirm(); onRead(model.notice) }
            }.disabled(model.busy || model.pending == nil)
            Button(model.uncertain ? "稍后核对" : "先不决定", role: .cancel) {
                model.cancelUnsubmitted()
            }
        }
    }

    private func begin(_ decision: VideoReviewDecision) {
        if model.begin(decision) {
            onRead(model.readback)
            showingConfirmation = true
        }
    }
}
