import AVKit
import SwiftUI

@MainActor struct RepairVideoReviewView: View {
    let runID: String
    let shotIndex: Int
    let onRead: (String) -> Void
    @State private var state: RepairVideoReviewState?
    @State private var player: AVPlayer?
    @State private var localURL: URL?
    @State private var busy = false
    @State private var notice: String?
    @State private var active = false
    private let runtime = RuntimeClient()

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let state {
                Text("这版修订 · 原镜头").naluFont(.headline)
                if state.candidates.items.contains(where: { $0.shot_index == shotIndex && $0.status == "available_for_review" }) {
                    if let player {
                        VideoPlayer(player: player).frame(minHeight: 180, idealHeight: 260)
                        Button("从头播放原镜头", systemImage: "play.fill") {
                            player.seek(to: .zero)
                            player.play()
                        }.buttonStyle(.bordered).controlSize(.large)
                        Button("暂停", systemImage: "pause.fill") { player.pause() }
                            .buttonStyle(.bordered).controlSize(.large)
                        Toggle("我已看过这个原镜头", isOn: Binding(
                            get: { self.state?.canAccept(shotIndex) == true },
                            set: { value in if value { try? self.state?.markViewed(shotIndex) } }))
                            .disabled(busy || state.canAccept(shotIndex))
                    } else {
                        Button("查看原镜头", systemImage: "play.rectangle") { Task { await openClip() } }
                            .buttonStyle(.bordered).controlSize(.large).disabled(busy)
                    }
                    if let decision = state.currentDecision(for: shotIndex) {
                        Text(decision.payload.adopted ? "已确认：这版使用原镜头" : "已确认：这版不使用原镜头")
                            .naluFont(.body)
                    }
                    Button("这版使用原镜头", systemImage: "checkmark.circle") { Task { await decide(true) } }
                        .buttonStyle(.borderedProminent).controlSize(.large)
                        .disabled(busy || !state.canAccept(shotIndex))
                    Button("这版不使用原镜头") { Task { await decide(false) } }
                        .buttonStyle(.bordered).controlSize(.large).disabled(busy)
                    Text("这里只确认复用，不会生成新视频或发布。").naluFont(.body)
                } else {
                    Text("这个镜头需要重新制作，请使用下面的画面准备入口。").naluFont(.body)
                }
            }
            if busy { ProgressView("正在读取或保存原镜头选择") }
            if let notice {
                Text(notice).naluFont(.body)
                Button("重新读取原镜头状态") { Task { await load() } }.disabled(busy)
                Button("读给我听", systemImage: "speaker.wave.2") { onRead(notice) }
            }
        }
        .task { active = true; await load() }
        .onDisappear { active = false; cleanUp() }
    }

    private func load() async {
        guard !busy else { return }; busy = true; defer { busy = false }
        do {
            guard try await runtime.hasRepairSource(runID: runID) else { return }
            let candidates = try await runtime.repairVideoCandidates(runID: runID)
            let decisions = try await runtime.repairVideoDecisions(runID: runID)
            guard active, !Task.isCancelled else { return }
            cleanUp()
            state = try RepairVideoReviewState(candidates: candidates, decisions: decisions)
            notice = nil
        } catch { if active { notice = "原镜头状态未能读取。可以重新读取，已有制作进度保留。" } }
    }

    private func openClip() async {
        guard !busy, let state else { return }; busy = true; defer { busy = false }
        do {
            let url = try await runtime.downloadRepairVideo(candidates: state.candidates, shotIndex: shotIndex)
            guard active, !Task.isCancelled else { try? FileManager.default.removeItem(at: url); return }
            cleanUp(); localURL = url; player = AVPlayer(url: url); notice = nil
        } catch { if active { notice = "原镜头暂时无法播放。请重新读取状态后再试；没有确认复用。" } }
    }

    private func decide(_ accept: Bool) async {
        guard !busy, let state, !accept || state.canAccept(shotIndex) else { return }
        busy = true; defer { busy = false }
        do {
            let saved = try await runtime.reviewRepairVideo(candidates: state.candidates, shotIndex: shotIndex,
                previousID: state.previousID(for: shotIndex), accept: accept)
            guard active else { return }
            try self.state?.record(saved); notice = nil
        } catch { if active { notice = "选择尚未核实，请重新读取状态后再操作，不会自动重复提交。" } }
    }

    private func cleanUp() {
        player?.pause(); player = nil
        if let localURL { try? FileManager.default.removeItem(at: localURL) }
        localURL = nil
    }
}
