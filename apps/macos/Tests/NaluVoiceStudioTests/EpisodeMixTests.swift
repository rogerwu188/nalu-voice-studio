import Foundation
import Testing
@testable import NaluVoiceStudio

struct EpisodeMixTests {
    @Test func preparedMixBindsSelectedSourcesAndKeepsExactBody() throws {
        let sha = String(repeating: "a", count: 64)
        let sound = EpisodeSoundPlan(id: "sound", run_id: "run", event_type: "episode_sound_plan_drafted",
            payload: .init(episode_id: "episode", edit_id: "edit", edit_sha256: sha, plan_id: "plan",
                plan_sha256: sha, sound_plan_sha256: sha, duration_seconds: 13,
                cues: [.init(shot_index: 0, start_seconds: 0, end_seconds: 13, dialogue_or_narration: "海边", sound_direction: "海浪")],
                caption_srt_draft: "", caption_timing_basis: "draft", audio_generated: false,
                captions_approved: false, speech_alignment_verified: false, edit_approved: true,
                edit_review_id: "review", generation_performed: false, master_accepted: false))
        let root = "provider-results/adopted-dialogue/\(sha)"
        let receipt = EpisodeDialogueStageReceipt(id: "stage", run_id: "run", event_type: "episode_dialogue_staged",
            payload: .init(run_id: "run", staging_sha256: sha, master_accepted: false,
                lineage: .init(sound_plan_id: "sound", sound_plan_sha256: sha, lineage_sha256: sha,
                    dialogue_sha256: sha, captions_sha256: sha, master_accepted: false,
                    speech_alignment_verified: false, other_audio_layers_generated: false),
                files: ["dialogue.wav": .init(relative_path: "\(root)/dialogue.wav", sha256: sha, byte_size: 1),
                        "captions.vtt": .init(relative_path: "\(root)/captions.vtt", sha256: sha, byte_size: 1)]))
        let sources = EpisodeSoundRole.allCases.map {
            EpisodeSoundSourceReceipt.Source(layer: $0,
                source_relative_path: "provider-results/authorized-sound/\(sha)/source.audio",
                source_sha256: sha, source_cue_sha256s: [sha], source_in_seconds: 0, gain_db: -12)
        }
        let others = try sources.map { try JSONSerialization.jsonObject(with: JSONEncoder().encode($0)) }
        let original: [String: Any] = [
            "adopted_dialogue_staging_id": "stage", "expected_dialogue_staging_sha256": sha,
            "requested_by": "nalu-native-user", "captions_source_relative_path": "\(root)/captions.vtt",
            "captions_source_sha256": sha, "subtitle_contract_sha256": sha, "shots": [["shot_id": "shot"]],
            "audio_layers": others + [["layer": "dialogue", "source_relative_path": "\(root)/dialogue.wav",
                "source_sha256": sha, "source_in_seconds": 0, "gain_db": 0]],
            "width": 1920, "height": 1080, "audio_sample_rate_hz": 48000,
            "audio_channels": 2, "pixel_format": "yuv420p"]
        for change in ["none", "stage", "caption", "size", "layers", "caller"] {
            var json = original
            if change == "stage" { json["adopted_dialogue_staging_id"] = "other" }
            if change == "caption" { json["captions_source_sha256"] = String(repeating: "b", count: 64) }
            if change == "size" { json["width"] = 3840 }
            if change == "layers" { json["audio_layers"] = others }
            if change == "caller" { json["requested_by"] = "other" }
            let bytes = try JSONSerialization.data(withJSONObject: json, options: [.prettyPrinted])
            if change == "none" {
                let mix = try EpisodePreparedMix(body: bytes, sound: sound, dialogue: receipt, sources: sources)
                #expect(mix.body == bytes && mix.runID == "run" && mix.episodeID == "episode")
                let wrong = EpisodeRenderedMix(schema_version: "nalu.postproduction-materialization/v1",
                    run_id: "other", episode_id: "episode", plan_sha256: sha, result_sha256: sha, master: ["sha256": .string(sha)])
                #expect(throws: (any Error).self) { try wrong.validate(mix) }
            } else {
                #expect(throws: (any Error).self) {
                    try EpisodePreparedMix(body: bytes, sound: sound, dialogue: receipt, sources: sources)
                }
            }
        }
    }
}
