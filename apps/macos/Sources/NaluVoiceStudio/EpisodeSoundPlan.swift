import Foundation

struct EpisodeAudioTakeDraft: Encodable, Sendable {
    let sound_plan_id: String
    let expected_sound_plan_sha256: String
    let shot_index: Int
    let asset_id: String
    let expected_asset_sha256: String
    let source_in_seconds: Double
}

struct EpisodeAudioTake: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let take_sha256: String
        let sound_plan_id: String
        let expected_sound_plan_sha256: String
        let shot_index: Int
        let asset_id: String
        let expected_asset_sha256: String
        let source_in_seconds: Double
        let edit_review_id: String
        let edit_sha256: String
        let start_seconds: Double
        let duration_seconds: Double
        let decoded_sample_count: Int
        let sample_rate_hz: Int
        let channels: Int
        let speech_alignment_verified: Bool
        let audio_approved: Bool
        let captions_approved: Bool
        let master_accepted: Bool
        let generation_performed: Bool
    }
}

struct EpisodeSoundPlan: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload

    struct Cue: Decodable, Sendable, Identifiable {
        let shot_index: Int
        let start_seconds: Double
        let end_seconds: Double
        let dialogue_or_narration: String
        let sound_direction: String
        var id: Int { shot_index }
    }

    struct Payload: Decodable, Sendable {
        let episode_id: String
        let edit_id: String
        let edit_sha256: String
        let plan_id: String
        let plan_sha256: String
        let sound_plan_sha256: String
        let duration_seconds: Double
        let cues: [Cue]
        let caption_srt_draft: String
        let caption_timing_basis: String
        let audio_generated: Bool
        let captions_approved: Bool
        let speech_alignment_verified: Bool
        let edit_approved: Bool
        let edit_review_id: String?
        let generation_performed: Bool
        let master_accepted: Bool
    }

    func validateCueWindows() throws {
        guard !id.isEmpty, !payload.episode_id.isEmpty,
              payload.sound_plan_sha256.count == 64,
              payload.sound_plan_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              !payload.cues.isEmpty, payload.cues.count <= 120,
              payload.duration_seconds.isFinite, payload.duration_seconds > 0 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var cursor = 0.0
        for (index, cue) in payload.cues.enumerated() {
            guard cue.shot_index == index, cue.start_seconds.isFinite, cue.end_seconds.isFinite,
                  abs(cue.start_seconds - cursor) < 0.000001, cue.end_seconds > cue.start_seconds,
                  cue.end_seconds - cue.start_seconds <= 300 else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            cursor = cue.end_seconds
        }
        guard abs(cursor - payload.duration_seconds) < 0.000001 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }
}
