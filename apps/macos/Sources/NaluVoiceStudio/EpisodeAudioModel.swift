import Foundation
import Observation

@MainActor @Observable final class EpisodeAudioModel {
    let sound: EpisodeSoundPlan
    private let runtime: RuntimeClient
    private(set) var recordings: [NaluAsset] = []
    private(set) var loaded = false
    private(set) var busy = false
    private(set) var pending: EpisodeAudioTakeDraft?
    private(set) var uncertain = false
    private(set) var attached: [Int: EpisodeAudioTake] = [:]
    private(set) var readback = ""
    private(set) var notice = "请选择已经导入并授权的录音。这里只准备配音素材，还需要试听和核对字幕。"

    init(sound: EpisodeSoundPlan, runtime: RuntimeClient = RuntimeClient()) {
        self.sound = sound; self.runtime = runtime
    }

    func load() async {
        guard !busy else { return }
        busy = true; loaded = false
        defer { busy = false }
        do {
            try sound.validateCueWindows()
            let run = try await runtime.productionRun(runID: sound.run_id)
            guard run.id == sound.run_id, run.episodeID == sound.payload.episode_id,
                  !["cancelled", "failed"].contains(run.status), sound.payload.edit_approved else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            let assets = try await runtime.listAssets(projectID: run.projectID)
            guard !Task.isCancelled, assets.allSatisfy({ $0.projectID == run.projectID }) else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            recordings = assets.filter {
                ["archive_audio", "voice_reference"].contains($0.kind) && $0.consentGranted
                    && ($0.episodeID == nil || $0.episodeID == run.episodeID)
                    && ($0.seasonID == nil || $0.seasonID == run.seasonID)
                    && Self.sha($0) != nil
            }
            loaded = true
            notice = recordings.isEmpty
                ? "还没有可用的授权录音。请先通过资料入口添加音频并确认使用授权。"
                : "已找到可用录音。选一段配音和对应录音，Nalu 会先读给您确认。"
            if uncertain { notice = "刚才的录音绑定结果还未核实，请重试同一选择，不要重复换录音。" }
        } catch { notice = "录音资料暂时无法读取。请重试；原录音、剪辑和待确认选择都保留。" }
    }

    func begin(shotIndex: Int, assetID: String, sourceIn: Double = 0) -> Bool {
        guard loaded, !busy, pending == nil, sound.payload.cues.indices.contains(shotIndex),
              sourceIn.isFinite, (0...1800).contains(sourceIn),
              let recording = recordings.first(where: { $0.id == assetID }), let sha = Self.sha(recording) else { return false }
        pending = EpisodeAudioTakeDraft(sound_plan_id: sound.id, expected_sound_plan_sha256: sound.payload.sound_plan_sha256,
            shot_index: shotIndex, asset_id: recording.id, expected_asset_sha256: sha, source_in_seconds: sourceIn)
        let duration = sound.payload.cues[shotIndex].end_seconds - sound.payload.cues[shotIndex].start_seconds
        readback = "把录音‘\(recording.name)’从第 \(sourceIn.formatted()) 秒起的约 \(duration.formatted()) 秒，用作第 \(shotIndex + 1) 段的配音素材。不会克隆声音或自动发行，还要试听和核对字幕。确认吗？"
        return true
    }

    func cancelUnsubmitted() {
        guard !busy, !uncertain else { return }
        pending = nil
    }

    func confirm() async {
        guard !busy, let pending else { return }
        busy = true; uncertain = true
        defer { busy = false }
        do {
            let take = try await runtime.attachEpisodeAudio(sound: sound, draft: pending)
            attached[pending.shot_index] = take
            self.pending = nil; uncertain = false
            notice = "录音素材已绑定到这一段。下一步试听并核对实际说话与字幕，还没有确认最终配音。"
        } catch {
            notice = "录音绑定还未核实。可以重试同一选择；不会重复生成声音，原素材保留。"
        }
    }

    private static func sha(_ asset: NaluAsset) -> String? {
        guard case .string(let value) = asset.metadata["sha256"], value.count == 64,
              value.allSatisfy({ "0123456789abcdef".contains($0) }) else { return nil }
        return value
    }
}
