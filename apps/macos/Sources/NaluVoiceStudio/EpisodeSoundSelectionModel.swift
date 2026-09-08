import Foundation
import Observation

@MainActor @Observable final class EpisodeSoundSelectionModel {
    // Reading assets during QA does not authorize staging, rendering or release.
    static let readableRunStatuses: Set<String> = ["preflight", "waiting_for_approval", "running", "qa_review"]
    let sound: EpisodeSoundPlan
    private let loadAssets: @MainActor () async throws -> [NaluAsset]
    private let stage: @MainActor (EpisodeSoundSourceDraft) async throws -> EpisodeSoundSourceReceipt
    private(set) var assets: [NaluAsset] = []
    private(set) var selections: [EpisodeSoundRole: String] = [:]
    private(set) var receipts: [EpisodeSoundRole: EpisodeSoundSourceReceipt] = [:]
    private(set) var pending: EpisodeSoundSourceDraft?
    private(set) var loaded = false
    private(set) var busy = false
    private(set) var notice = "请选择这集要用的声音素材。不会自动生成或扣费。"

    init(sound: EpisodeSoundPlan, runtime: RuntimeClient = RuntimeClient(),
         loadAssets: (@MainActor () async throws -> [NaluAsset])? = nil,
         stage: (@MainActor (EpisodeSoundSourceDraft) async throws -> EpisodeSoundSourceReceipt)? = nil) {
        self.sound = sound
        self.loadAssets = loadAssets ?? {
            let run = try await runtime.productionRun(runID: sound.run_id)
            guard run.id == sound.run_id, run.episodeID == sound.payload.episode_id,
                  Self.readableRunStatuses.contains(run.status) else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            let all = try await runtime.listAssets(projectID: run.projectID)
            guard all.allSatisfy({ $0.projectID == run.projectID }) else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            return all.filter { $0.episodeID == nil || $0.episodeID == run.episodeID }
                .filter { $0.seasonID == nil || $0.seasonID == run.seasonID }
        }
        self.stage = stage ?? { try await runtime.stageEpisodeSoundSource(sound: sound, draft: $0) }
    }

    static func sha(_ asset: NaluAsset) -> String? {
        guard case .string(let value) = asset.metadata["sha256"], EpisodeDialogueStageReceipt.validSHA(value) else { return nil }
        return value
    }

    func load() async {
        guard !busy else { return }
        busy = true; loaded = false
        defer { busy = false }
        do {
            try sound.validateCueWindows()
            guard sound.payload.edit_approved else { throw LibrarySnapshotRefreshError.contextChanged }
            let fetched = try await loadAssets()
            try Task.checkCancellation()
            assets = fetched.filter { $0.kind == "archive_audio" && $0.consentGranted && Self.sha($0) != nil }
            // Keep user choices, but discard ready receipts whose source is no
            // longer available. The backend rechecks exact consent at mixing.
            receipts = receipts.filter { _, receipt in
                assets.contains { $0.id == receipt.payload.binding.asset_id
                    && Self.sha($0) == receipt.payload.binding.expected_asset_sha256 }
            }
            loaded = true
            notice = assets.isEmpty ? "还没有可用的声音素材。请先添加音频并确认使用授权。"
                : "声音素材已刷新，原来的选择保留。请确认每种声音的用途后准备。"
        } catch {
            notice = "暂时无法核对声音素材。您的选择还在，请刷新后继续。"
        }
    }

    func select(_ assetID: String, for role: EpisodeSoundRole) {
        guard loaded, !busy, pending == nil, assetID.isEmpty || assets.contains(where: { $0.id == assetID }) else { return }
        if selections[role] != assetID { receipts[role] = nil }
        selections[role] = assetID
    }

    func prepare(_ role: EpisodeSoundRole, sourceIn: Double = 0, gainDB: Double = 0) async {
        guard loaded, !busy else { return }
        if let pending, pending.layer != role { return }
        if pending == nil {
            guard let asset = assets.first(where: { $0.id == selections[role] }), let sha = Self.sha(asset) else {
                notice = "请选择当前可用的\(role.title)素材。"; return
            }
            let draft = EpisodeSoundSourceDraft(sound_plan_id: sound.id,
                expected_sound_plan_sha256: sound.payload.sound_plan_sha256, layer: role, asset_id: asset.id,
                expected_asset_sha256: sha, source_in_seconds: sourceIn, gain_db: gainDB)
            do { try draft.validate() } catch { notice = "声音起点或音量不合适，请调整后再试。"; return }
            // A changed offset/gain on the same asset is a new choice too.
            // Never fall back to its old receipt after an uncertain request.
            receipts[role] = nil
            pending = draft
        }
        guard let draft = pending else { return }
        busy = true
        notice = "正在准备\(role.title)，检查授权、文件和时长。"
        defer { busy = false }
        do {
            let receipt = try await stage(draft)
            try Task.checkCancellation()
            try receipt.validate(runID: sound.run_id, draft: draft,
                                 duration: sound.payload.duration_seconds, cueCount: sound.payload.cues.count)
            receipts[role] = receipt; pending = nil
            notice = "\(role.title)素材已准备好，尚未完成混音或成片验收。"
        } catch {
            notice = "\(role.title)还未准备成功或结果未核实。可重试同一选择；短音频请换较长素材，不会自动补齐。"
        }
    }

    func chooseAgain() {
        guard !busy else { return }
        pending = nil
        notice = "可以重新选择。已保存的素材不会删除；新选择需要重新准备。"
    }

    var mixSources: [EpisodeSoundSourceReceipt.Source]? {
        guard loaded, !busy, pending == nil else { return nil }
        let values = EpisodeSoundRole.allCases.compactMap { role -> EpisodeSoundSourceReceipt.Source? in
            guard let receipt = receipts[role], receipt.payload.binding.asset_id == selections[role] else { return nil }
            return receipt.payload.source
        }
        return values.count == EpisodeSoundRole.allCases.count ? values : nil
    }
}
