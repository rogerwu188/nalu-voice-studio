import Foundation

struct EpisodeMixRequest: Encodable, Sendable {
    let staging_id: String
    let expected_staging_sha256: String
    let requested_by = "nalu-native-user"
    let sound_layers: [EpisodeSoundSourceReceipt.Source]
}

// Keep the exact prepared body for an explicit retry, not a reconstructed plan.
struct EpisodePreparedMix: Sendable {
    let body: Data
    let runID: String
    let episodeID: String

    init(body: Data, sound: EpisodeSoundPlan, dialogue: EpisodeDialogueStageReceipt,
         sources: [EpisodeSoundSourceReceipt.Source]) throws {
        let validSHA = EpisodeDialogueStageReceipt.validSHA
        guard body.count <= 2_000_000, dialogue.run_id == sound.run_id,
              dialogue.payload.lineage.sound_plan_id == sound.id,
              dialogue.payload.lineage.sound_plan_sha256 == sound.payload.sound_plan_sha256,
              !dialogue.payload.master_accepted,
              let json = try JSONSerialization.jsonObject(with: body) as? [String: Any],
              json["adopted_dialogue_staging_id"] as? String == dialogue.id,
              json["expected_dialogue_staging_sha256"] as? String == dialogue.payload.staging_sha256,
              json["requested_by"] as? String == "nalu-native-user",
              json["captions_source_relative_path"] as? String == dialogue.payload.files["captions.vtt"]?.relative_path,
              json["captions_source_sha256"] as? String == dialogue.payload.lineage.captions_sha256,
              let subtitleSHA = json["subtitle_contract_sha256"] as? String, validSHA(subtitleSHA),
              let shots = json["shots"] as? [[String: Any]], shots.count == sound.payload.cues.count,
              let audio = json["audio_layers"] as? [[String: Any]], audio.count == 5,
              sources.count == 4, Set(sources.map(\.layer)) == Set(EpisodeSoundRole.allCases),
              let spoken = audio.first(where: { $0["layer"] as? String == "dialogue" }),
              spoken["source_relative_path"] as? String == dialogue.payload.files["dialogue.wav"]?.relative_path,
              spoken["source_sha256"] as? String == dialogue.payload.lineage.dialogue_sha256,
              spoken["source_in_seconds"] as? Double == 0,
              spoken["gain_db"] as? Double == 0 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let selected = try audio.filter { $0["layer"] as? String != "dialogue" }.map {
            try JSONDecoder().decode(EpisodeSoundSourceReceipt.Source.self,
                                     from: JSONSerialization.data(withJSONObject: $0))
        }
        guard selected.count == sources.count, Set(selected.map(\.layer)).count == 4,
              sources.allSatisfy({ selected.contains($0) }),
              json["width"] as? Int == 1920, json["height"] as? Int == 1080,
              json["audio_sample_rate_hz"] as? Int == 48000, json["audio_channels"] as? Int == 2,
              json["pixel_format"] as? String == "yuv420p" else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        self.body = body; runID = sound.run_id; episodeID = sound.payload.episode_id
    }
}

struct EpisodeRenderedMix: Decodable, Sendable {
    let schema_version: String
    let run_id: String
    let episode_id: String
    let plan_sha256: String
    let result_sha256: String
    let master: [String: JSONValue]

    func validate(_ mix: EpisodePreparedMix) throws {
        guard schema_version == "nalu.postproduction-materialization/v1",
              run_id == mix.runID, episode_id == mix.episodeID,
              EpisodeDialogueStageReceipt.validSHA(plan_sha256),
              EpisodeDialogueStageReceipt.validSHA(result_sha256), !master.isEmpty else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }
}
