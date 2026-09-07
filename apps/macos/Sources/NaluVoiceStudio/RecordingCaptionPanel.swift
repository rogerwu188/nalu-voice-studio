import SwiftUI

@MainActor struct RecordingCaptionPanel: View {
    @State private var model: RecordingCaptionModel
    @State private var confirming = false
    let onRead: (String) -> Void

    init(transcript: RecordingTranscriptRecord, onRead: @escaping (String) -> Void) {
        _model = State(initialValue: RecordingCaptionModel(transcript: transcript))
        self.onRead = onRead
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("核对这段字幕").fontWeight(.semibold)
            Text(model.notice).fixedSize(horizontal: false, vertical: true)
            if model.busy { ProgressView("正在保存或核对字幕") }
            DisclosureGroup("有错字？展开修改") {
                ForEach(model.texts.indices, id: \.self) { index in
                    TextField("第 \(index + 1) 段字幕", text: $model.texts[index], axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .accessibilityLabel("第 \(index + 1) 段字幕")
                        .disabled(model.busy || model.pending != nil || !model.loaded)
                }
            }
            Button("读一下修正后的字幕", systemImage: "speaker.wave.2") { onRead(model.readback) }
                .disabled(model.busy)
            Button(model.pending == nil ? "字幕对了，确认保存" : "继续保存刚才的字幕", systemImage: "checkmark.circle") {
                if model.pending != nil || model.prepare() {
                    onRead(model.readback + "。确认用这些字幕吗？")
                    confirming = true
                } else { onRead(model.notice) }
            }.buttonStyle(.borderedProminent).disabled(model.busy || !model.loaded)
                .accessibilityIdentifier("nalu.episode.caption.confirm")
            Button("核对已保存的字幕确认", systemImage: "arrow.clockwise") {
                Task { await model.load(); onRead(model.notice) }
            }.disabled(model.busy)
        }.naluFont(.body).buttonStyle(.bordered).controlSize(.large)
            .task { await model.load() }
            .confirmationDialog("确认使用刚才朗读的字幕？", isPresented: $confirming, titleVisibility: .visible) {
                Button("确认保存字幕") { Task { await model.confirm(); onRead(model.notice) } }
                Button("稍后再确认", role: .cancel) { model.cancelUnsubmitted() }
            }
    }
}
