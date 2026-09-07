import Foundation

struct VideoCostApproval: Codable, Equatable, Sendable {
    let preparation_sha256: String
    let estimated_credits: Int
    let confirmed_run_budget_credits: Int
    let approved_by: String
    let confirmation: String
    let guardian_approval: Bool
    let pricing_quote_id: String
}

struct VideoCostReservation: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let preparation_id: String
        let preparation_sha256: String
        let estimated_credits: Int
        let confirmed_run_budget_credits: Int
        let pricing_quote_id: String
        let guardian_approval: Bool
        let task_key: String
        let request_sha256: String
        let published_price_observed: Bool
        let generation_performed: Bool
    }
}

struct VideoSubmissionObservation: Decodable, Sendable {
    let id: String
    let run_id: String
    let task_key: String
    let request_sha256: String
    let state: String
    let provider_task_id: String?
}
