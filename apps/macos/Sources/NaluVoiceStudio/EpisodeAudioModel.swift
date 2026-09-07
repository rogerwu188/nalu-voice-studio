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
    private var selections: [Int: String] = [:]
    private var offsets: [Int: Double] = [:]
    private var editedSelections = Set<Int>()

    func selectedAssetID(_ index: Int) -> String { selections[index] ?? "" }
    func sourceOffset(_ index: Int) -> Double { offsets[index] ?? 0 }

    func select(_ assetID: String, for index: Int) {
        guard loaded, !busy, pending == nil, sound.payload.cues.indices.contains(index),
              assetID.isEmpty || recordings.contains(where: { $0.id == assetID }) else { return }
        selections[index] = assetID; offsets[index] = 0; editedSelections.insert(index)
    }

    func setOffset(_ value: Double, for index: Int) {
        guard loaded, !busy, pending == nil, sound.payload.cues.indices.contains(index),
              value.isFinite, (0...1800).contains(value), !selectedAssetID(index).isEmpty else { return }
        offsets[index] = value; editedSelections.insert(index)
    }
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
            let available = assets.filter {
                ["archive_audio", "voice_reference"].contains($0.kind) && $0.consentGranted
                    && ($0.episodeID == nil || $0.episodeID == run.episodeID)
                    && ($0.seasonID == nil || $0.seasonID == run.seasonID)
                    && Self.sha($0) != nil
            }
            let recovered = try await runtime.recoverEpisodeAudio(sound: sound)
            guard !Task.isCancelled, recovered.allSatisfy({ take in
                available.contains { $0.id == take.payload.asset_id && Self.sha($0) == take.payload.expected_asset_sha256 }
            }) else { throw LibrarySnapshotRefreshError.contextChanged }
            recordings = available
            attached = Dictionary(uniqueKeysWithValues: recovered.map { ($0.payload.shot_index, $0) })
            for take in recovered where !editedSelections.contains(take.payload.shot_index) {
                selections[take.payload.shot_index] = take.payload.asset_id
                offsets[take.payload.shot_index] = take.payload.source_in_seconds
            }
            loaded = true
            notice = recordings.isEmpty
                ? "还没有可用的授权录音。请先通过资料入口添加音频并确认使用授权。"
                : "已找到可用录音。选一段配音和对应录音，Nalu 会先读给您确认。"
            if let pending, uncertain {
                if let saved = attached[pending.shot_index], saved.payload.asset_id == pending.asset_id,
                   saved.payload.expected_asset_sha256 == pending.expected_asset_sha256,
                   saved.payload.source_in_seconds == pending.source_in_seconds {
                    self.pending = nil; uncertain = false
                    notice = "已找回刚才绑定的录音，不需要重复提交。接下来试听并核对字幕。"
                } else {
                    notice = "刚才的录音绑定结果还未核实，请重试同一选择，不要重复换录音。"
                }
            } else if !attached.isEmpty {
                notice = "已恢复各段保存的录音素材，您可以继续试听和核对；还不是最终配音验收。"
            }
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
            selections[pending.shot_index] = take.payload.asset_id
            offsets[pending.shot_index] = take.payload.source_in_seconds
            editedSelections.remove(pending.shot_index)
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
