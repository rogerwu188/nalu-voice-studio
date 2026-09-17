import Foundation
import Testing
@testable import NaluVoiceStudio

struct FinalHumanReviewTests {
    @Test func decodesServerResponseWithoutSubmissionOnlyFields() throws {
        let payload: [String: Any] = [
            "schema_version": "nalu.final-qa-evidence/v1", "run_id": "run_test",
            "master_sha256": String(repeating: "a", count: 64),
            "original_resolution_reviewed": true, "picture_passed": false,
            "audio_sync_passed": true, "captions_passed": true,
            "continuity_passed": true, "safety_passed": true,
            "reviewed_by": "test-reviewer", "review_channel": "human_original_resolution",
            "reviewed_at": "2026-09-16T00:00:00Z", "notes": "Synthetic contract fixture"
        ]
        let bytes = try JSONSerialization.data(withJSONObject: payload)
        let result = try JSONDecoder().decode(FinalHumanReviewResult.self, from: bytes)
        #expect(result.runID == "run_test")
        #expect(result.picturePassed == false)
        #expect(result.originalResolutionReviewed)
        try result.validate(runID: "run_test")
        #expect(throws: (any Error).self) { try result.validate(runID: "another-run") }

        var submission = payload
        submission["idempotency_key"] = "stable-review-key"
        submission["output_seal_sha256"] = String(repeating: "b", count: 64)
        let draft = try JSONDecoder().decode(FinalHumanReviewDraft.self,
            from: JSONSerialization.data(withJSONObject: submission))
        try result.validate(runID: "run_test", submitted: draft)

        for field in ["master_sha256", "picture_passed", "reviewed_by", "reviewed_at", "notes"] {
            var changed = payload
            if field == "picture_passed" { changed[field] = true }
            else { changed[field] = "changed" }
            let mismatch = try JSONDecoder().decode(FinalHumanReviewResult.self,
                from: JSONSerialization.data(withJSONObject: changed))
            #expect(throws: (any Error).self) {
                try mismatch.validate(runID: "run_test", submitted: draft)
            }
        }
    }
}
