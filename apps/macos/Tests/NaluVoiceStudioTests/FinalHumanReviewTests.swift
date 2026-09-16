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
    }
}
