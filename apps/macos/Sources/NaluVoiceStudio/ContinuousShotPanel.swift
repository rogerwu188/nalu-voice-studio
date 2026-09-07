import SwiftUI

@MainActor struct ContinuousShotPanel: View {
    let runID: String
    let planID: String
    let planSHA: String
    let shotIndex: Int
    let guardianRequired: Bool
    let onRead: (String) -> Void
    @State private var prepared: FrameProductionEvent?
    @State private var price: VideoPriceObservation?
    @State private var busy = false
    @State private var notice = "这个镜头接着上一镜头拍。先播放并采用上一镜头，Nalu 会自动取它的最后一帧继续。"
    private let runtime = RuntimeClient()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(notice).naluFont(.body)
            if busy { ProgressView("正在核对上一镜头并准备连续拍摄") }
            Button("接着上一镜头准备视频", systemImage: "film.stack") {
                Task {
                    guard !busy else { return }
                    busy = true; price = nil
                    defer { busy = false }
                    do {
                        prepared = try await runtime.prepareContinuousVideo(runID: runID, planID: planID,
                            planSHA: planSHA, shotIndex: shotIndex)
                        notice = "已用上一镜头的真实尾帧准备好。接下来核对费用，再确认生成。"
                    } catch {
                        prepared = nil
                        notice = "暂时不能继续。请先播放并采用上一镜头，再试一次；分镜和原视频保留，没有提交生成。"
                    }
                    onRead(notice)
                }
            }.buttonStyle(.borderedProminent).controlSize(.large).disabled(busy)
            if let prepared {
                Button("查看这个镜头的预计费用", systemImage: "creditcard") {
                    Task {
                        guard !busy else { return }
                        busy = true; price = nil
                        defer { busy = false }
                        do {
                            let observed = try await runtime.observeVideoPrice(runID: runID, preparationID: prepared.id)
                            guard observed.payload.preparation_id == prepared.id,
                                  observed.payload.preparation_sha256 == prepared.payload.preparation_sha256 else {
                                throw LibrarySnapshotRefreshError.contextChanged
                            }
                            price = observed
                            notice = "预计 \(observed.payload.estimated_credits) 积分，不是实际扣费上限。请核对后确认。"
                        } catch { notice = "这次费用查询未成功，请再试一次。没有提交生成。" }
                        onRead(notice)
                    }
                }.buttonStyle(.bordered).controlSize(.large).disabled(busy)
                VideoGenerationPanel(prepared: prepared, price: price, guardianRequired: guardianRequired, onRead: onRead)
                    .id(prepared.id)
            }
        }.accessibilityIdentifier("nalu.shot.continuation")
    }
}
