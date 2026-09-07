import Foundation
import Observation

enum VideoReviewDecision: String, Codable, Sendable { case accept, reject }

struct VideoReviewDraft: Encodable, Sendable {
    let preparation_id: String
    let expected_materialization_sha256: String
    let expected_review_event_id: String?
    let decision: VideoReviewDecision
    let reviewed_by: String
    let confirmation: String
}

struct VideoReviewReceipt: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let task_key: String
        let materialization_id: String
        let materialization_sha256: String
        let video_sha256: String
        let preparation_id: String
        let preparation_sha256: String
        let request_sha256: String
        let binding_id: String
        let decision: VideoReviewDecision
        let reviewed_by: String
        let confirmation: String
        let user_approved: Bool
        let visual_semantics_verified: Bool
        let audio_verified: Bool
        let billing_verified: Bool
        let master_accepted: Bool
        let generation_performed: Bool
    }
}

struct VideoReviewEnvelope: Decodable {
    let review: VideoReviewReceipt?
    private enum CodingKeys: String, CodingKey { case event_type }
    init(from decoder: Decoder) throws {
        let type = try decoder.container(keyedBy: CodingKeys.self).decode(String.self, forKey: .event_type)
        review = type == "video_shot_reviewed" ? try VideoReviewReceipt(from: decoder) : nil
    }
}

@MainActor @Observable final class VideoReviewModel {
    let candidate: VideoCandidate
    let prepared: FrameProductionEvent
    let binding: VideoSubmissionObservation
    private let runtime: RuntimeClient
    var busy = false
    var loaded = false
    var latest: VideoReviewReceipt?
    var pending: VideoReviewDraft?
    var notice = "正在读取这个镜头的采用记录。"

    init(candidate: VideoCandidate, prepared: FrameProductionEvent, binding: VideoSubmissionObservation,
         runtime: RuntimeClient = RuntimeClient()) {
        self.candidate = candidate; self.prepared = prepared; self.binding = binding; self.runtime = runtime
    }

    var readback: String {
        pending?.decision == .accept
            ? "您要采用刚才播放的这个镜头。它仍需后期检查，不会自动发行。确认采用吗？"
            : "您要把刚才播放的这个镜头退回修改。视频保留，不会自动付费重做。确认退回吗？"
    }

    func load() async {
        guard !busy else { return }
        busy = true; loaded = false; defer { busy = false }
        do {
            latest = try await runtime.latestVideoReview(binding)
            guard !Task.isCancelled else { return }
            pending = nil; loaded = true
            if latest?.payload.materialization_id == candidate.id {
                notice = latest?.payload.decision == .accept ? "这个视频已记录为采用，仍需后期检查。" : "这个视频已退回修改，原视频保留。"
            } else { notice = "请播放查看这个视频，再选择采用或退回修改。" }
        } catch { notice = "暂时无法读取采用记录。请点核对采用记录，不会重新生成。" }
    }

    func begin(_ decision: VideoReviewDecision) -> Bool {
        guard loaded, !busy, pending == nil,
              prepared.run_id == binding.run_id, prepared.event_type == "video_task_prepared",
              prepared.payload.task_key == binding.task_key, prepared.payload.request_sha256 == binding.request_sha256,
              candidate.run_id == binding.run_id, candidate.payload.binding_id == binding.id,
              candidate.payload.request_sha256 == binding.request_sha256,
              let digest = candidate.payload.materialization_sha256 else { return false }
        pending = VideoReviewDraft(preparation_id: prepared.id, expected_materialization_sha256: digest,
            expected_review_event_id: latest?.id, decision: decision, reviewed_by: "nalu-native-user",
            confirmation: decision == .accept ? "采用这个镜头" : "退回修改这个镜头")
        return true
    }

    func confirm() async {
        guard !busy, let pending else { return }
        busy = true; defer { busy = false }
        do {
            let receipt = try await runtime.reviewVideo(candidate, binding: binding, draft: pending)
            guard receipt.payload.preparation_sha256 == prepared.payload.preparation_sha256 else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            latest = receipt; self.pending = nil
            notice = receipt.payload.decision == .accept ? "已记下：采用这个镜头。接下来继续制作和后期检查。" : "已记下：这个镜头需要修改。视频保留，没有自动重做。"
        } catch {
            notice = "这次确认结果未核实。可以重试同一确认，或核对采用记录；不会重新生成视频。"
        }
    }
}
