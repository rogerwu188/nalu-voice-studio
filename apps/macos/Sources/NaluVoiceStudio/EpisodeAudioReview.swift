import Foundation
import Observation

struct EpisodeAudioReviewRecovery: Decodable, Sendable {
    let current_take_id: String
    let current_take_sha256: String
    let latest_review: EpisodeAudioReview?
    let applies_to_current_take: Bool
    let take_approved: Bool
}

struct EpisodeAudioReviewDraft: Encodable, Sendable {
    enum Decision: String, Codable, Sendable { case accept, reject }
    let expected_take_sha256: String
    let expected_review_id: String?
    let decision: Decision
    let reviewed_by: String
    let confirmation: String
}

struct EpisodeAudioReview: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload

    struct Payload: Decodable, Sendable {
        let take_id: String
        let take_sha256: String
        let sound_plan_id: String
        let sound_plan_sha256: String
        let edit_review_id: String
        let edit_sha256: String
        let shot_index: Int
        let asset_id: String
        let asset_sha256: String
        let source_in_seconds: Double
        let duration_seconds: Double
        let decision: EpisodeAudioReviewDraft.Decision
        let reviewed_by: String
        let confirmation: String
        let review_sha256: String
        let take_approved: Bool
        let listening_evidence: String
        let speech_alignment_verified: Bool
        let final_mix_approved: Bool
        let captions_approved: Bool
        let master_accepted: Bool
        let generation_performed: Bool
    }
}

@MainActor @Observable final class EpisodeAudioReviewModel {
    let sound: EpisodeSoundPlan
    let take: EpisodeAudioTake
    private let runtime: RuntimeClient
    private(set) var busy = false
    private(set) var loaded = false
    private(set) var latest: EpisodeAudioReviewRecovery?
    private(set) var pending: EpisodeAudioReviewDraft?
    private(set) var uncertain = false
    private(set) var notice = "请先试听这段录音，再确认是否采用。还需要字幕和成片检查。"

    init(sound: EpisodeSoundPlan, take: EpisodeAudioTake, runtime: RuntimeClient = RuntimeClient()) {
        self.sound = sound; self.take = take; self.runtime = runtime
    }

    var readback: String {
        let window = "从第 \(take.payload.source_in_seconds.formatted()) 秒开始的约 \(take.payload.duration_seconds.formatted()) 秒录音"
        return pending?.decision == .accept
            ? "您确认已试听并采用\(window)。还需要字幕、混音和成片检查，不会自动发行。确认吗？"
            : "您要退回\(window)。原录音保留，不会自动生成或付费重做。确认吗？"
    }

    func load() async {
        guard !busy else { return }
        busy = true; loaded = false
        defer { busy = false }
        do {
            let recovered = try await runtime.recoverEpisodeAudioReview(sound: sound, take: take)
            guard !Task.isCancelled else { return }
            latest = recovered; loaded = true
            if let pending, uncertain, recovered.applies_to_current_take,
               let review = recovered.latest_review,
               review.payload.decision == pending.decision,
               review.payload.reviewed_by == pending.reviewed_by,
               review.payload.confirmation == pending.confirmation {
                self.pending = nil; uncertain = false
                notice = "已找回刚才的确认结果，不需要重复提交。"
            } else if uncertain {
                notice = "刚才的确认结果尚未核实，请保留同一选择重试；原录音不变。"
            } else if recovered.take_approved {
                notice = "这段录音已采用；字幕、混音和成片检查仍未完成。"
            } else {
                notice = "当前录音尚未采用。请试听后确认；旧录音的确认不会自动沿用。"
            }
        } catch { notice = "暂时无法核对录音确认结果。请重试，原素材和待确认选择都保留。" }
    }

    func begin(_ decision: EpisodeAudioReviewDraft.Decision) -> Bool {
        guard loaded, !busy, pending == nil, let latest else { return false }
        pending = EpisodeAudioReviewDraft(expected_take_sha256: take.payload.take_sha256,
            expected_review_id: latest.latest_review?.id, decision: decision,
            reviewed_by: "local-user", confirmation: decision == .accept
                ? "我已试听并确认采用这一段录音。" : "这段录音需要调整，暂不采用。")
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
            let review = try await runtime.reviewEpisodeAudio(sound: sound, take: take, draft: pending)
            latest = EpisodeAudioReviewRecovery(current_take_id: take.id, current_take_sha256: take.payload.take_sha256,
                latest_review: review, applies_to_current_take: true, take_approved: review.payload.take_approved)
            self.pending = nil; uncertain = false; loaded = true
            notice = review.payload.take_approved
                ? "录音采用已保存。接下来核对字幕和混音，不会自动发行。"
                : "已记录需要调整。原录音和剪辑都保留。"
        } catch { notice = "确认是否保存还未核实。请先核对保存结果，或重试同一确认。" }
    }
}
