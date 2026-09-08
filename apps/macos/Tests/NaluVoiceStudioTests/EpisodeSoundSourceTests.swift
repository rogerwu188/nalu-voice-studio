import Foundation
import Testing
@testable import NaluVoiceStudio

struct EpisodeSoundSourceTests {
    private let sha = String(repeating: "a", count: 64)

    @Test func receiptMustMatchSelectedRoleAssetAndTimeline() throws {
        let draft = EpisodeSoundSourceDraft(sound_plan_id: "sound", expected_sound_plan_sha256: sha,
            layer: .music, asset_id: "asset", expected_asset_sha256: sha, source_in_seconds: 0, gain_db: -12)
        let originalBinding: [String: Any] = ["sound_plan_id": "sound", "expected_sound_plan_sha256": sha,
            "layer": "music", "asset_id": "asset", "expected_asset_sha256": sha,
            "source_in_seconds": 0, "gain_db": -12, "consent_record_id": "grant", "duration_seconds": 13]
        let originalSource: [String: Any] = ["layer": "music", "source_relative_path": "provider-results/authorized-sound/\(sha)/source.audio",
            "source_sha256": sha, "source_cue_sha256s": [sha], "source_in_seconds": 0, "gain_db": -12]
        for change in ["none", "role", "asset", "duration", "consent", "path", "gain", "hash", "cues", "master"] {
            var binding = originalBinding, source = originalSource
            if change == "role" { source["layer"] = "foley" }
            if change == "asset" { binding["asset_id"] = "other" }
            if change == "duration" { binding["duration_seconds"] = 12 }
            if change == "consent" { binding["consent_record_id"] = "" }
            if change == "path" { source["source_relative_path"] = "provider-results/authorized-sound/../source.audio" }
            if change == "gain" { source["gain_db"] = 0 }
            if change == "hash" { source["source_sha256"] = String(repeating: "b", count: 64) }
            if change == "cues" { source["source_cue_sha256s"] = [String]() }
            let data = try JSONSerialization.data(withJSONObject: ["id": "receipt", "run_id": "run",
                "event_type": "episode_sound_source_staged", "payload": ["binding": binding, "source": source,
                    "source_binding_sha256": sha, "generation_performed": false, "master_accepted": change == "master"]])
            let receipt = try JSONDecoder().decode(EpisodeSoundSourceReceipt.self, from: data)
            if change == "none" {
                try receipt.validate(runID: "run", draft: draft, duration: 13, cueCount: 1)
                #expect(try JSONDecoder().decode(EpisodeSoundSourceReceipt.Source.self,
                    from: JSONEncoder().encode(receipt.payload.source)) == receipt.payload.source)
            } else {
                #expect(throws: (any Error).self) {
                    try receipt.validate(runID: "run", draft: draft, duration: 13, cueCount: 1)
                }
            }
        }
    }

    @Test func draftRejectsInvalidOffsetsAndGains() throws {
        for (offset, gain) in [(Double.nan, 0.0), (Double.infinity, 0.0), (-1.0, 0.0), (0.0, 13.0), (0.0, Double.nan)] {
            let draft = EpisodeSoundSourceDraft(sound_plan_id: "sound", expected_sound_plan_sha256: sha,
                layer: .ambience, asset_id: "asset", expected_asset_sha256: sha, source_in_seconds: offset, gain_db: gain)
            #expect(throws: (any Error).self) { try draft.validate() }
        }
        #expect(EpisodeSoundRole.allCases.count == 4)
        #expect(EpisodeSoundRole.allCases.allSatisfy { !$0.title.isEmpty })
    }
}
