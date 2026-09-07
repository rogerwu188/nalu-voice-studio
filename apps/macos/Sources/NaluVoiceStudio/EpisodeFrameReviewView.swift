import SwiftUI

// Operate extension: retain Nalu's system colors, scalable type and large native
// controls. One exact image follows its shot; no professional form or paid action.
// Empty/error states are explicit. Native capture/finish review remains required.
@MainActor struct EpisodeFrameReviewView: View {
    @State private var model: EpisodeFrameReviewModel
    @State private var showPermission = false
    let referenceName: String?
    let guardianRequired: Bool
    let onRead: (String) -> Void
    let onRegistered: () -> Void

    init(runID: String, planID: String, shotIndex: Int, referenceKey: String? = nil, referenceName: String? = nil,
         guardianRequired: Bool = false, onRead: @escaping (String) -> Void = { _ in }, onRegistered: @escaping () -> Void = {}) {
        _model = State(initialValue: EpisodeFrameReviewModel(runID: runID, planID: planID, shotIndex: shotIndex, referenceKey: referenceKey))
        self.referenceName = referenceName; self.guardianRequired = guardianRequired
        self.onRead = onRead; self.onRegistered = onRegistered
    }

    private var permissionText: String {
        "同意将这张生成参考图用于本项目？涉及真人形象时，请确认已取得本人或合法授权人的同意。这不代表同意付费或发行。"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(referenceName.map { "看看\($0)的参考图" } ?? "看看这个镜头的第一张画面").naluFont(.headline)
            if model.busy { ProgressView("正在核对画面，请稍等") }
            if let data = model.imageData, let image = NSImage(data: data) {
                Image(nsImage: image).resizable().scaledToFit()
                    .frame(maxWidth: .infinity, maxHeight: 340)
                    .accessibilityLabel(referenceName.map { "\($0)的生成参考图" } ?? "当前镜头待确认的首帧图片")
                Text(referenceName == nil ? "请看看人物、地点和动作开始前的样子是否符合您的想法。"
                     : "这张是生成的创作参考，不是历史原照。请确认外观是否符合您的想法。")
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
                if referenceName == nil {
                    if model.videoPreparation != nil {
                        Text("视频任务资料已备好 · 尚未生成，等待费用确认").naluFont(.headline)
                        Button("查看这个镜头的预计费用", systemImage: "creditcard") {
                            Task {
                                await model.observeVideoPrice()
                                if let notice = model.notice { onRead(notice) }
                            }
                        }
                        .buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
                        if let price = model.videoPrice {
                            Text("公开价格估算：\(price.payload.estimated_credits) 积分 / \(price.payload.duration_seconds) 秒。不是实际扣费上限；尚未授权生成。")
                                .naluFont(.body)
                        }
                    } else {
                        Button("下一步：准备这个镜头的视频", systemImage: "film") {
                            Task {
                                await model.prepareVideo()
                                if let notice = model.notice { onRead(notice) }
                            }
                        }
                        .buttonStyle(.borderedProminent).controlSize(.large).disabled(!model.canPrepareVideo)
                        Text("先确认“这张可以”。这一步只整理任务，不会扣费或发布。").naluFont(.body)
                    }
                }
                if referenceName != nil {
                    Button("听听如何确认", systemImage: "speaker.wave.2") { onRead(permissionText) }
                        .buttonStyle(.bordered).controlSize(.large)
                    if model.registeredAssetID != nil {
                        Text("这张已经登记为项目素材 · 使用时仍会核对授权").naluFont(.body)
                    } else {
                        Button("同意用于本项目", systemImage: "folder.badge.plus") { showPermission = true }
                            .buttonStyle(.borderedProminent).controlSize(.large).disabled(!model.canRegister)
                        Text("先点“这张可以”，再确认使用范围；不需要填写表格。").naluFont(.body)
                    }
                }
            }
            if let notice = model.notice { Text(notice).naluFont(.body).textSelection(.enabled) }
            Button("重新读取画面", systemImage: "arrow.clockwise") { Task { await model.load() } }
                .buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
        }
        .padding(.vertical, 12)
        .accessibilityIdentifier(model.referenceKey.map { "nalu.episode.reference-review.\($0)" } ?? "nalu.episode.frame-review")
        .task { await model.load() }
        .confirmationDialog(permissionText, isPresented: $showPermission, titleVisibility: .visible) {
            Button(guardianRequired ? "我是监护人，同意用于本项目" : "确认同意用于本项目") {
                Task {
                    await model.registerReference(guardianApproved: guardianRequired)
                    if model.registeredAssetID != nil { onRegistered() }
                }
            }
            Button("先不使用", role: .cancel) {}
        }
    }
}

@MainActor struct EpisodeReferenceCollectionView: View {
    let runID: String
    let planID: String
    let designs: [EpisodeVisualAsset]
    let guardianRequired: Bool
    let onRead: (String) -> Void
    let onRegistered: () -> Void
    @State private var selected = 0

    var body: some View {
        DisclosureGroup("先看看人物和场景参考图") {
            Picker("看哪份参考素材", selection: $selected) {
                ForEach(designs.indices, id: \.self) { index in Text(designs[index].name).tag(index) }
            }.controlSize(.large)
            if designs.indices.contains(selected) {
                let design = designs[selected]
                Text(design.description).naluFont(.body)
                EpisodeFrameReviewView(runID: runID, planID: planID, shotIndex: 0,
                    referenceKey: design.key, referenceName: design.name, guardianRequired: guardianRequired,
                    onRead: onRead, onRegistered: onRegistered)
                    .id("\(runID)-\(planID)-\(design.key)")
            }
        }
    }
}
