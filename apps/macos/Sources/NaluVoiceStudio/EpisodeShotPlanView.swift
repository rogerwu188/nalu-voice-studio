import SwiftUI

// Operate: extend the existing native episode panel, system colors and large
// controls. Read one shot at a time; preserve unsaved edits and exact-version
// approval. No new visual identity or claim that a plan is a generated video.
@MainActor struct EpisodeShotPlanView: View {
    @State private var model: EpisodeShotPlanModel
    @State private var selectedShot = 0
    @State private var showGenerationConfirmation = false
    @State private var showReloadConfirmation = false
    @State private var expanded = false
    @State private var referenceRevision = 0
    let onRead: (String) -> Void
    let guardianRequired: Bool
    let refreshRevision: Int
    let onCharactersPrepared: ([String]) async -> Void

    init(runID: String, guardianRequired: Bool = false, refreshRevision: Int = 0, onRead: @escaping (String) -> Void,
         onCharactersPrepared: @escaping ([String]) async -> Void = { _ in }) {
        _model = State(initialValue: EpisodeShotPlanModel(runID: runID))
        self.onRead = onRead
        self.guardianRequired = guardianRequired
        self.refreshRevision = refreshRevision
        self.onCharactersPrepared = onCharactersPrepared
    }

    var body: some View {
        DisclosureGroup("本集怎么拍 · 分镜方案", isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 14) {
                if model.busy {
                    ProgressView("正在处理本集分镜，请稍等")
                }
                if let notice = model.notice {
                    Text(notice).naluFont(.body).textSelection(.enabled)
                }
                if let plan = model.editedPlan, !plan.shots.isEmpty {
                    Text(plan.summary).naluFont(.body).textSelection(.enabled)
                    Text(model.event?.payload.approved == true && !model.hasEdits
                         ? "已确认 · 等待准备画面" : "待确认 · 还没有生成视频")
                        .naluFont(.headline)
                    Picker("看哪一个镜头", selection: $selectedShot) {
                        ForEach(plan.shots.indices, id: \.self) { index in
                            Text("镜头 \(index + 1) · \(plan.shots[index].duration_seconds) 秒").tag(index)
                        }
                    }
                    .controlSize(.large)
                    if plan.shots.indices.contains(selectedShot) {
                        let shot = plan.shots[selectedShot]
                        Text("剧本原文：\(shot.source_excerpt)").naluFont(.body).textSelection(.enabled)
                        if !plan.assetReadback(for: selectedShot).isEmpty {
                            Text(plan.assetReadback(for: selectedShot)).naluFont(.body).textSelection(.enabled)
                        }
                        Button("听听这个镜头", systemImage: "speaker.wave.2") {
                            onRead(shot.readback + "拍摄描述：" + shot.video_prompt + "\n" + plan.assetReadback(for: selectedShot)
                                + "\n" + plan.directorReadback(for: selectedShot))
                        }
                        .buttonStyle(.bordered).controlSize(.large)
                        DisclosureGroup("看看具体怎么拍") {
                            Text(plan.directorReadback(for: selectedShot)).naluFont(.body).textSelection(.enabled)
                        }
                        Text("想拍成什么样？可以直接修改下面的话。")
                            .naluFont(.body)
                        TextField("这个镜头的拍摄描述", text: shotText(\.video_prompt), axis: .vertical)
                            .lineLimit(3...10).textFieldStyle(.roundedBorder).naluFont(.body)
                            .disabled(model.busy)
                        DisclosureGroup("查看动作与声音") {
                            Text("动作：\(shot.action)\n对白或旁白：\(shot.dialogue_or_narration)\n声音：\(shot.sound)")
                                .naluFont(.body).textSelection(.enabled)
                        }
                        if let event = model.event, event.payload.approved && !model.hasEdits && !model.snapshotRefreshPending {
                            let designs = (plan.visual_assets ?? []).filter {
                                (shot.visual_asset_keys ?? []).contains($0.key) && $0.existing_asset_id == nil
                            }
                            if !designs.isEmpty {
                                EpisodeReferenceCollectionView(runID: model.runID, planID: event.id, designs: designs,
                                    guardianRequired: guardianRequired, onRead: onRead, onRegistered: { referenceRevision += 1 })
                                    .id("\(event.id)-\(selectedShot)-references")
                            }
                            EpisodeFrameReviewView(runID: model.runID, planID: event.id, shotIndex: selectedShot, onRead: onRead)
                                .id("\(model.runID)-\(event.id)-\(selectedShot)-\(referenceRevision)")
                        }
                    }
                    Button("保存修改并整理拍法", systemImage: "square.and.arrow.down") {
                        Task { await model.review(approve: false) }
                    }
                    .buttonStyle(.bordered).controlSize(.large)
                    .disabled(!model.hasEdits || model.busy)
                    Text("先保存您的话，再用已配置的模型整理需要更新的拍摄细节，可能产生模型费用；不会直接生成视频。")
                        .naluFont(.body)
                    if model.needsDirector && !model.hasEdits {
                        Button("继续整理拍法", systemImage: "film.stack") {
                            Task { await model.continueDirector() }
                        }
                        .buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
                    }
                    Button("确认这个版本的分镜", systemImage: "checkmark.circle") {
                        Task {
                            await model.review(approve: true)
                            if let cards = await model.prepareCharacterCards() {
                                await onCharactersPrepared(cards.payload.bindings.map(\.entity_id))
                            }
                        }
                    }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .disabled(!model.canApprove)
                    if model.event?.payload.approved == true && !model.hasEdits && !model.snapshotRefreshPending {
                        Button("核对本集人物", systemImage: "person.crop.rectangle") {
                            Task {
                                if let cards = await model.prepareCharacterCards() {
                                    await onCharactersPrepared(cards.payload.bindings.map(\.entity_id))
                                }
                            }
                        }
                        .buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
                    }
                    if model.hasEdits {
                        Text("您改过内容，请先保存，再确认。") .naluFont(.body)
                    }
                } else if model.loaded {
                    Text("剧本已经有制作记录。下一步让 Nalu 把它拆成一个个镜头，再交给您确认。")
                        .naluFont(.body)
                    Button("生成本集分镜", systemImage: "film.stack") {
                        showGenerationConfirmation = true
                    }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .disabled(model.busy || model.generationAttempted)
                }
                Button("读取已保存方案", systemImage: "arrow.clockwise") {
                    if model.hasEdits { showReloadConfirmation = true }
                    else { Task { await model.load(); selectedShot = 0 } }
                }
                .buttonStyle(.bordered).controlSize(.large).disabled(model.busy)
            }
            .padding(.top, 12)
        }
        .naluFont(.headline)
        .accessibilityIdentifier("nalu.episode.shot-plan")
        .task { await model.load() }
        .onChange(of: refreshRevision) { _, _ in
            Task { await model.reloadAfterLibraryRefresh() }
        }
        .confirmationDialog("调用已配置的模型生成本集分镜？可能产生模型费用，不会生成或发布视频。",
                            isPresented: $showGenerationConfirmation) {
            Button("生成分镜") { Task { await model.generate() } }
            Button("先不生成", role: .cancel) {}
        }
        .confirmationDialog("读取保存版本会放弃这次尚未保存的修改。继续吗？", isPresented: $showReloadConfirmation) {
            Button("放弃未保存修改并读取", role: .destructive) {
                Task { await model.load(); selectedShot = 0 }
            }
            Button("继续修改", role: .cancel) {}
        }
    }

    private func shotText(_ keyPath: WritableKeyPath<EpisodeShot, String>) -> Binding<String> {
        Binding(get: {
            guard let plan = model.editedPlan, plan.shots.indices.contains(selectedShot) else { return "" }
            return plan.shots[selectedShot][keyPath: keyPath]
        }, set: { value in
            guard var plan = model.editedPlan, plan.shots.indices.contains(selectedShot) else { return }
            plan.shots[selectedShot][keyPath: keyPath] = value
            model.editedPlan = plan
        })
    }
}
