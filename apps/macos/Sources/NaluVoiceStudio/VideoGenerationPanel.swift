import SwiftUI

@MainActor struct VideoGenerationPanel: View {
    @State private var model: VideoGenerationModel
    @State private var showConfirmation = false
    let price: VideoPriceObservation?
    let guardianRequired: Bool
    let onRead: (String) -> Void

    init(prepared: FrameProductionEvent, price: VideoPriceObservation?, guardianRequired: Bool,
         onRead: @escaping (String) -> Void) {
        _model = State(initialValue: VideoGenerationModel(prepared: prepared))
        self.price = price; self.guardianRequired = guardianRequired; self.onRead = onRead
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if model.busy { ProgressView("正在核对这个镜头的制作记录") }
            if let notice = model.notice { Text(notice).naluFont(.body).textSelection(.enabled) }
            if model.reservation == nil {
                Button("确认费用并生成这个镜头", systemImage: "film") {
                    guard let price else { return }
                    Task {
                        if await model.review(price: price, guardianApproved: guardianRequired) {
                            onRead(model.readback)
                            showConfirmation = true
                        } else if let notice = model.notice { onRead(notice) }
                    }
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
                .disabled(!model.loaded || model.busy || price?.isCurrent != true)
                Text("先查看当前预计费用。下一步会朗读费用，您再次确认后才提交生成。").naluFont(.body)
            } else if model.canResume {
                Button("按已确认费用继续这个镜头", systemImage: "play.circle") {
                    onRead(model.readback)
                    showConfirmation = true
                }
                .buttonStyle(.borderedProminent).controlSize(.large)
            }
            Button("核对提交状态", systemImage: "arrow.clockwise") {
                Task { await model.load(); if let notice = model.notice { onRead(notice) } }
            }
            .buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
            .accessibilityHint("只核对已保存的提交状态，不会重新生成或扣费")
            if let binding = model.submission, binding.provider_task_id?.isEmpty == false {
                VideoCandidatePanel(binding: binding, onRead: onRead).id(binding.id)
            }
        }
        .accessibilityIdentifier("nalu.shot.video-generation")
        .task { await model.load() }
        .onChange(of: price?.id) { _, _ in
            showConfirmation = false
            model.draft = nil
        }
        .confirmationDialog(model.readback, isPresented: $showConfirmation, titleVisibility: .visible) {
            Button(guardianRequired ? "我是监护人，确认费用并提交生成" : "确认费用并提交生成") {
                Task { await model.confirm(); if let notice = model.notice { onRead(notice) } }
            }
            Button("先不生成", role: .cancel) { model.draft = nil }
        }
    }
}
