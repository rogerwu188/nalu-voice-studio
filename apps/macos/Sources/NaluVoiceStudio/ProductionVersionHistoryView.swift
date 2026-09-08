import AVKit
import SwiftUI

// Operate: extend the existing large-type disclosure panels. History is an
// inspection surface, never a replacement binding for active production.
@MainActor struct ProductionVersionHistoryView: View {
    let projectID: String
    let seasonID: String
    let episodeID: String
    let currentRunID: String
    let onRead: (String) -> Void
    private let runtime = RuntimeClient()
    @State private var expanded = false
    @State private var versions: [ProductionRun] = []
    @State private var selectedID = ""
    @State private var busy = false
    @State private var notice = "查看以前保存的版本，不会改变当前制作，也不会生成或发行。"
    @State private var player: AVPlayer?
    @State private var localFile: URL?
    @State private var generation = 0

    var body: some View {
        DisclosureGroup("查看本集以前的版本", isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: 12) {
                Text(notice).naluFont(.body).fixedSize(horizontal: false, vertical: true)
                if busy { ProgressView("正在读取保存的版本") }
                Button("读取版本列表", systemImage: "arrow.clockwise") {
                    Task { await load() }
                }.controlSize(.large).disabled(busy)
                if !versions.isEmpty {
                    Picker("查看哪个版本", selection: $selectedID) {
                        ForEach(Array(versions.enumerated()), id: \.element.id) { index, run in
                            Text("第 \(versions.count - index) 版" + (run.id == currentRunID ? " · 当前制作" : " · 以前保存")
                                 + (run.dryRun ? " · 准备记录" : "")).tag(run.id)
                        }
                    }.controlSize(.large).disabled(busy)
                    Button("查看这版保存的视频", systemImage: "play.rectangle") {
                        Task { await inspect() }
                    }.controlSize(.large).disabled(busy || selectedID.isEmpty)
                }
                Button("读一下当前情况", systemImage: "speaker.wave.2") { onRead(notice) }
                    .controlSize(.large)
                if let player {
                    Text("仅供查看，播放不代表验收通过").naluFont(.body)
                    Button("从头播放这版视频", systemImage: "play.fill") {
                        player.seek(to: .zero); player.play()
                    }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                    .accessibilityIdentifier("nalu.episode.version-history.play")
                    Button("暂停视频", systemImage: "pause.fill") { player.pause() }
                        .buttonStyle(.bordered).controlSize(.large)
                        .accessibilityIdentifier("nalu.episode.version-history.pause")
                    VideoPlayer(player: player).frame(minHeight: 240, idealHeight: 360)
                        .accessibilityLabel("这版保存的视频，仅供查看，未代表验收通过")
                }
            }.padding(.top, 12)
        }
        .naluFont(.body)
        .accessibilityIdentifier("nalu.episode.version-history")
        .onChange(of: selectedID) { _, _ in clearPreview() }
        .onDisappear { generation += 1; clearPreview() }
    }

    private func clearPreview() {
        player?.pause(); player = nil
        if let localFile { try? FileManager.default.removeItem(at: localFile) }
        localFile = nil
    }

    private func load() async {
        guard !busy else { return }
        busy = true
        let token = generation
        defer { busy = false }
        do {
            let saved = try await runtime.productionVersions(projectID: projectID, seasonID: seasonID, episodeID: episodeID)
            guard token == generation else { return }
            versions = saved
            if !saved.contains(where: { $0.id == selectedID }) { selectedID = saved.first?.id ?? "" }
            notice = saved.isEmpty ? "这集还没有制作版本。" : "已找到 \(saved.count) 个版本。选择后可以查看保存的视频；当前制作不会改变。"
        } catch {
            guard token == generation else { return }
            notice = "暂时无法读取版本。请重试读取列表，原来的制作和成片没有改变。"
        }
    }

    private func inspect() async {
        guard !busy, versions.contains(where: { $0.id == selectedID }) else { return }
        busy = true; clearPreview()
        let token = generation
        let runID = selectedID
        defer { busy = false }
        do {
            let file = try await runtime.downloadSealedMaster(runID: runID)
            guard token == generation, selectedID == runID else {
                try? FileManager.default.removeItem(at: file.fileURL); return
            }
            localFile = file.fileURL
            player = AVPlayer(url: file.fileURL)
            notice = "这版保存的视频已核对文件并打开。请按播放查看；没有更改当前制作，也没有通过验收或发行。"
        } catch {
            guard token == generation else { return }
            notice = "这版还没有可读取的封存视频，或文件核对没有通过。您可以选择其他版本；原记录保留。"
        }
    }
}
