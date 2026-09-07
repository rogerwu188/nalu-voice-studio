import Foundation

/// Provider completion is not creative acceptance or verified billing.
struct VideoTaskObservation: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let binding_id: String
        let task_id: String
        let status: String
        let result_urls: [String]
        let observation_sha256: String
        let billing_verified: Bool
        let generation_performed: Bool
        let master_accepted: Bool
    }
}

struct VideoCandidate: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let observation_id: String
        let observation_sha256: String
        let binding_id: String
        let result_index: Int
        let task_key: String
        let request_sha256: String
        let video_downloaded: Bool
        let generation_performed: Bool
        let billing_verified: Bool
        let visual_semantics_verified: Bool
        let master_accepted: Bool
    }
}
