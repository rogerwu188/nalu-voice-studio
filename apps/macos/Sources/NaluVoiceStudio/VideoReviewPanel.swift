import SwiftUI

@MainActor struct VideoReviewPanel: View {
    @State private var model: VideoReviewModel
    @State private var showingConfirmation = false
    let onRead: (String) -> Void

    init(candidate: VideoCandidate, prepared: FrameProductionEvent, binding: VideoSubmissionObservation,
         onRead: @escaping (String) -> Void) {
        _model = State(initialValue: VideoReviewModel(candidate: candidate, prepared: prepared, binding: binding))
        self.onRead = onRead
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if model.busy { ProgressView("正在保存或核对镜头决定") }
            Text(model.notice).naluFont(.body)
            if model.pending == nil {
                Button("采用这个镜头", systemImage: "checkmark.circle") { begin(.accept) }
                    .buttonStyle(.borderedProminent).controlSize(.large).disabled(!model.loaded || model.busy)
                Button("这个镜头要修改", systemImage: "pencil") { begin(.reject) }
                    .buttonStyle(.bordered).controlSize(.large).disabled(!model.loaded || model.busy)
            } else {
                Button("重试刚才的确认", systemImage: "arrow.clockwise") {
                    onRead(model.readback); showingConfirmation = true
                }.buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
            }
            Button("核对采用记录", systemImage: "list.bullet.clipboard") {
                Task { await model.load(); onRead(model.notice) }
            }.buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
        }
        .accessibilityIdentifier("nalu.shot.video-review")
        .task { await model.load() }
        .confirmationDialog(model.readback, isPresented: $showingConfirmation, titleVisibility: .visible) {
            Button(model.pending?.decision == .accept ? "确认采用" : "确认退回修改") {
                Task { await model.confirm(); onRead(model.notice) }
            }
            Button("先不决定", role: .cancel) { model.pending = nil }
        }
    }

    private func begin(_ decision: VideoReviewDecision) {
        if model.begin(decision) { onRead(model.readback); showingConfirmation = true }
    }
}
