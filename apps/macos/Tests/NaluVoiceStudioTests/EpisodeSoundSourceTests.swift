import Foundation
import Testing
@testable import NaluVoiceStudio

struct EpisodeSoundSourceTests {
    @MainActor @Test func qaCanReadSoundAssetsWithoutAllowingTerminalOrUnknownRuns() {
        #expect(EpisodeSoundSelectionModel.readableRunStatuses.contains("qa_review"))
        for state in ["cancelled", "failed", "published", "unknown"] {
            #expect(!EpisodeSoundSelectionModel.readableRunStatuses.contains(state))
        }
    }

    private let sha = String(repeating: "a", count: 64)

    @MainActor @Test func selectionPreservesExactRetryAndNeverClaimsAnIncompleteMix() async throws {
        let sha = self.sha
        let sound = try JSONDecoder().decode(EpisodeSoundPlan.self, from: JSONSerialization.data(withJSONObject: [
            "id": "sound", "run_id": "run", "event_type": "episode_sound_plan_drafted",
            "payload": ["episode_id": "episode", "edit_id": "edit", "edit_sha256": sha, "plan_id": "plan",
                "plan_sha256": sha, "sound_plan_sha256": sha, "duration_seconds": 13,
                "cues": [["shot_index": 0, "start_seconds": 0, "end_seconds": 13,
                          "dialogue_or_narration": "海边", "sound_direction": "海浪"]],
                "caption_srt_draft": "", "caption_timing_basis": "draft", "audio_generated": false,
                "captions_approved": false, "speech_alignment_verified": false, "edit_approved": true,
                "edit_review_id": "review", "generation_performed": false, "master_accepted": false]]))
        let asset = try JSONDecoder().decode(NaluAsset.self, from: JSONSerialization.data(withJSONObject: [
            "id": "asset", "project_id": "project", "kind": "archive_audio", "name": "海浪",
            "local_uri": "file:///unused/fixture.wav", "subject_name": "", "metadata": ["sha256": sha],
            "consent_granted": true, "consent_scope": "project_only", "guardian_approved": true, "created_at": "fixture"]))
        var available = [asset]
        var requests: [EpisodeSoundSourceDraft] = []
        var fail = true
        let model = EpisodeSoundSelectionModel(sound: sound, loadAssets: { available }, stage: { draft in
            requests.append(draft)
            if fail { throw URLError(.timedOut) }
            var binding = try JSONSerialization.jsonObject(with: JSONEncoder().encode(draft)) as! [String: Any]
            binding["consent_record_id"] = "grant"; binding["duration_seconds"] = 13
            let source: [String: Any] = ["layer": draft.layer.rawValue,
                "source_relative_path": "provider-results/authorized-sound/\(sha)/source.audio",
                "source_sha256": sha, "source_cue_sha256s": [sha], "source_in_seconds": draft.source_in_seconds,
                "gain_db": draft.gain_db]
            return try JSONDecoder().decode(EpisodeSoundSourceReceipt.self, from: JSONSerialization.data(withJSONObject: [
                "id": "receipt", "run_id": "run", "event_type": "episode_sound_source_staged",
                "payload": ["binding": binding, "source": source, "source_binding_sha256": sha,
                            "generation_performed": false, "master_accepted": false]]))
        })
        #expect(requests.isEmpty && model.mixSources == nil)
        await model.load()
        model.select("asset", for: .music)
        await model.prepare(.music, sourceIn: 1, gainDB: -12)
        #expect(model.pending == requests.first && model.receipts.isEmpty)
        model.select("", for: .music)
        await model.load()
        #expect(model.selections[.music] == "asset" && model.pending != nil)
        fail = false
        await model.prepare(.music, sourceIn: 0, gainDB: 0)
        #expect(requests.count == 2 && requests[0] == requests[1])
        #expect(model.pending == nil && model.receipts[.music] != nil && model.mixSources == nil)
        for role in [EpisodeSoundRole.ambience, .foley, .sfx] {
            model.select("asset", for: role)
            await model.prepare(role)
        }
        #expect(model.mixSources?.count == 4)
        fail = true
        await model.prepare(.music, sourceIn: 2, gainDB: -6)
        #expect(model.receipts[.music] == nil && model.mixSources == nil)
        model.chooseAgain()
        #expect(model.pending == nil && model.mixSources == nil)
        fail = false
        await model.prepare(.music, sourceIn: 2, gainDB: -6)
        #expect(model.mixSources?.count == 4)
        available = []
        await model.load()
        #expect(model.receipts.isEmpty && model.mixSources == nil && model.selections[.music] == "asset")
    }

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
