import Foundation
import Observation

struct EpisodeDialogueStageDraft: Codable, Sendable, Equatable {
    let sound_plan_id: String
    let expected_sound_plan_sha256: String
    let expected_lineage_sha256: String
}

struct EpisodeDialoguePreparation: Sendable {
    let draft: EpisodeDialogueStageDraft
    let captionsSHA256: String
}

struct EpisodeDialogueStageReceipt: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let run_id: String
        let staging_sha256: String
        let master_accepted: Bool
        let lineage: Lineage
        let files: [String: File]
    }
    struct File: Decodable, Sendable {
        let relative_path: String
        let sha256: String
        let byte_size: Int
    }
    struct Lineage: Decodable, Sendable {
        let sound_plan_id: String
        let sound_plan_sha256: String
        let lineage_sha256: String
        let dialogue_sha256: String
        let captions_sha256: String
        let master_accepted: Bool
        let speech_alignment_verified: Bool
        let other_audio_layers_generated: Bool
    }

    static func validSHA(_ text: String) -> Bool {
        text.count == 64 && text.allSatisfy { "0123456789abcdef".contains($0) }
    }

    func validate(runID: String, preparation: EpisodeDialoguePreparation) throws {
        let p = payload, l = p.lineage, d = preparation.draft
        guard !id.isEmpty, run_id == runID, p.run_id == runID,
              event_type == "episode_dialogue_staged", !p.master_accepted,
              Self.validSHA(p.staging_sha256), l.sound_plan_id == d.sound_plan_id,
              l.sound_plan_sha256 == d.expected_sound_plan_sha256,
              l.lineage_sha256 == d.expected_lineage_sha256,
              l.captions_sha256 == preparation.captionsSHA256,
              !l.master_accepted, !l.speech_alignment_verified, !l.other_audio_layers_generated,
              Self.validSHA(l.dialogue_sha256), Self.validSHA(l.captions_sha256),
              Set(p.files.keys) == Set(["dialogue.wav", "captions.vtt", "lineage.json"]) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        for (name, file) in p.files {
            guard file.relative_path == "provider-results/adopted-dialogue/\(d.expected_lineage_sha256)/\(name)",
                  Self.validSHA(file.sha256), file.byte_size > 0 else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
        }
        guard p.files["dialogue.wav"]?.sha256 == l.dialogue_sha256,
              p.files["captions.vtt"]?.sha256 == l.captions_sha256 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }
}

@MainActor @Observable final class EpisodeDialogueStageModel {
    let sound: EpisodeSoundPlan
    private let runtime: RuntimeClient
    private(set) var busy = false
    private(set) var pending: EpisodeDialoguePreparation?
    private(set) var receipt: EpisodeDialogueStageReceipt?
    private(set) var notice = "确认每段录音和字幕后，Nalu 会自动整理这一集的配音与字幕。"

    init(sound: EpisodeSoundPlan, runtime: RuntimeClient = RuntimeClient()) {
        self.sound = sound
        self.runtime = runtime
    }

    func prepare() async {
        guard !busy else { return }
        busy = true
        receipt = nil
        notice = "正在核对这一集的录音和字幕，并保存到本机制作目录。"
        defer { busy = false }
        do {
            if pending == nil { pending = try await runtime.prepareEpisodeDialogue(sound: sound) }
            guard let pending else { return }
            receipt = try await runtime.stageEpisodeDialogue(sound: sound, preparation: pending)
            self.pending = nil
            notice = "这一版配音和字幕已准备好。视频尚未完成；接下来还要准备配乐与音效、合成和检查。"
        } catch {
            notice = pending == nil
                ? "这次还没准备好。请先确认每段录音和字幕，再试一次；已有故事和素材都还在。"
                : "保存结果还未核对。请重试同一版；如果已修改录音或字幕，请重新核对当前版本。"
        }
    }

    func refreshCurrentVersion() {
        guard !busy else { return }
        pending = nil
        receipt = nil
        notice = "下次会重新核对当前录音和字幕；不会删除已保存的素材。"
    }
}
