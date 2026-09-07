import Foundation

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
