import Foundation

enum EpisodeSoundRole: String, Codable, CaseIterable, Sendable {
    case ambience, foley, music, sfx

    var title: String {
        switch self {
        case .ambience: "环境声音"
        case .foley: "动作声音"
        case .music: "背景音乐"
        case .sfx: "特殊音效"
        }
    }
}

struct EpisodeSoundSourceDraft: Codable, Equatable, Sendable {
    let sound_plan_id: String
    let expected_sound_plan_sha256: String
    let layer: EpisodeSoundRole
    let asset_id: String
    let expected_asset_sha256: String
    let source_in_seconds: Double
    let gain_db: Double

    func validate() throws {
        guard !sound_plan_id.isEmpty, sound_plan_id.count <= 160,
              !asset_id.isEmpty, asset_id.count <= 160,
              EpisodeDialogueStageReceipt.validSHA(expected_sound_plan_sha256),
              EpisodeDialogueStageReceipt.validSHA(expected_asset_sha256),
              source_in_seconds.isFinite, (0...1800).contains(source_in_seconds),
              gain_db.isFinite, (-60...12).contains(gain_db) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }
}

struct EpisodeSoundSourceReceipt: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload

    struct Payload: Decodable, Sendable {
        let binding: Binding
        let source: Source
        let source_binding_sha256: String
        let generation_performed: Bool
        let master_accepted: Bool
    }
    struct Binding: Decodable, Sendable {
        let sound_plan_id: String
        let expected_sound_plan_sha256: String
        let layer: EpisodeSoundRole
        let asset_id: String
        let expected_asset_sha256: String
        let source_in_seconds: Double
        let gain_db: Double
        let consent_record_id: String
        let duration_seconds: Double

        var draft: EpisodeSoundSourceDraft {
            .init(sound_plan_id: sound_plan_id, expected_sound_plan_sha256: expected_sound_plan_sha256,
                  layer: layer, asset_id: asset_id, expected_asset_sha256: expected_asset_sha256,
                  source_in_seconds: source_in_seconds, gain_db: gain_db)
        }
    }
    struct Source: Codable, Equatable, Sendable {
        let layer: EpisodeSoundRole
        let source_relative_path: String
        let source_sha256: String
        let source_cue_sha256s: [String]
        let source_in_seconds: Double
        let gain_db: Double
    }

    func validate(runID: String, draft: EpisodeSoundSourceDraft, duration: Double, cueCount: Int) throws {
        try draft.validate()
        let b = payload.binding, s = payload.source
        let components = s.source_relative_path.split(separator: "/", omittingEmptySubsequences: false)
        guard !id.isEmpty, run_id == runID, event_type == "episode_sound_source_staged",
              !payload.generation_performed, !payload.master_accepted,
              EpisodeDialogueStageReceipt.validSHA(payload.source_binding_sha256),
              b.draft == draft, !b.consent_record_id.isEmpty,
              b.duration_seconds.isFinite, duration.isFinite, duration > 0, duration <= 1800,
              abs(b.duration_seconds - duration) < 0.000001,
              s.layer == draft.layer, s.source_sha256 == draft.expected_asset_sha256,
              s.source_in_seconds == draft.source_in_seconds, s.gain_db == draft.gain_db,
              cueCount > 0, s.source_cue_sha256s.count == cueCount,
              Set(s.source_cue_sha256s).count == cueCount,
              s.source_cue_sha256s.allSatisfy(EpisodeDialogueStageReceipt.validSHA),
              components.count == 4, components[0] == "provider-results", components[1] == "authorized-sound",
              EpisodeDialogueStageReceipt.validSHA(String(components[2])), components[3] == "source.audio" else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }
}
