import SwiftUI

// Operate extension: retain Nalu's system colors, scalable type and large native
// controls. One exact image follows its shot; no professional form or paid action.
// Empty/error states are explicit. Native capture/finish review remains required.
@MainActor struct EpisodeFrameReviewView: View {
    @State private var model: EpisodeFrameReviewModel

    init(runID: String, planID: String, shotIndex: Int) {
        _model = State(initialValue: EpisodeFrameReviewModel(runID: runID, planID: planID, shotIndex: shotIndex))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("看看这个镜头的第一张画面").naluFont(.headline)
            if model.busy { ProgressView("正在核对画面，请稍等") }
            if let data = model.imageData, let image = NSImage(data: data) {
                Image(nsImage: image).resizable().scaledToFit()
                    .frame(maxWidth: .infinity, maxHeight: 340)
                    .accessibilityLabel("当前镜头待确认的首帧图片")
                Text("请看看人物、地点和动作开始前的样子是否符合您的想法。")
                    .naluFont(.body)
                if model.latestReview?.payload.materialization_id == model.materialization?.id {
                    Text(model.latestReview?.payload.decision == "accept" ? "您已认可这张 · 仍待制作质量检查" : "您希望修改这张画面")
                        .naluFont(.headline)
                }
                Button("这张可以", systemImage: "checkmark.circle") {
                    Task { await model.review(accept: true) }
                }
                .buttonStyle(.borderedProminent).controlSize(.large).disabled(!model.canReview)
                Button("这张需要修改", systemImage: "arrow.uturn.backward") {
                    Task { await model.review(accept: false) }
                }
                .buttonStyle(.bordered).controlSize(.large).disabled(!model.canReview)
            }
            if let notice = model.notice { Text(notice).naluFont(.body).textSelection(.enabled) }
            Button("重新读取画面", systemImage: "arrow.clockwise") { Task { await model.load() } }
                .buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
        }
        .padding(.vertical, 12)
        .accessibilityIdentifier("nalu.episode.frame-review")
        .task { await model.load() }
    }
}
