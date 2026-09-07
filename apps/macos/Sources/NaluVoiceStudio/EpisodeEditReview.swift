import Foundation

struct EpisodeEditReviewDraft: Encodable, Sendable {
    let expected_edit_sha256: String
    let preview_id: String
    let expected_preview_sha256: String
    let expected_review_id: String?
    let decision: VideoReviewDecision
    let reviewed_by: String
    let confirmation: String
}

struct EpisodeEditReview: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let edit_id: String
        let edit_sha256: String
        let preview_id: String
        let preview_sha256: String
        let decision: VideoReviewDecision
        let reviewed_by: String
        let confirmation: String
        let edit_approved: Bool
        let duration_confirmed_seconds: Double
        let viewing_evidence: String
        let audio_approved: Bool
        let captions_approved: Bool
        let master_accepted: Bool
        let generation_performed: Bool
    }
}

struct EpisodeEditReviewEnvelope: Decodable {
    let review: EpisodeEditReview?
    private enum CodingKeys: String, CodingKey { case event_type }
    init(from decoder: Decoder) throws {
        let type = try decoder.container(keyedBy: CodingKeys.self).decode(String.self, forKey: .event_type)
        review = type == "postproduction_edit_reviewed" ? try EpisodeEditReview(from: decoder) : nil
    }
}
