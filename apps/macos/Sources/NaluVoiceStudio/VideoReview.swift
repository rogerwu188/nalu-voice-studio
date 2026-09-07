import Foundation

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
