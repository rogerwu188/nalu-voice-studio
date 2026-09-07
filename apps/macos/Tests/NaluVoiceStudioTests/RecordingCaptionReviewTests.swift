import Foundation
import Testing
@testable import NaluVoiceStudio

@Test func captionCorrectionsStayInsideRecording() throws {
    func draft(_ words: [SemanticASRSegmentDraft]) -> RecordingCaptionSubmission {
        RecordingCaptionSubmission(expected_transcript_sha256: String(repeating: "a", count: 64),
            expected_previous_review_id: nil, segments: words, reviewed_by: "local-user", confirmation: "确认字幕")
    }
    let word = SemanticASRSegmentDraft(startSeconds: 0, endSeconds: 1, text: "修正", confidence: nil)
    try draft([word]).validate(sampleCount: 48000)
    for words in [[], [word, word],
                  [SemanticASRSegmentDraft(startSeconds: -1, endSeconds: 1, text: "错", confidence: nil)],
                  [SemanticASRSegmentDraft(startSeconds: 0, endSeconds: 2, text: "错", confidence: nil)],
                  [SemanticASRSegmentDraft(startSeconds: 0, endSeconds: .nan, text: "错", confidence: nil)],
                  [SemanticASRSegmentDraft(startSeconds: 0, endSeconds: 1, text: " ", confidence: nil)],
                  [SemanticASRSegmentDraft(startSeconds: 0, endSeconds: 1, text: "错", confidence: 2)]] {
        #expect(throws: (any Error).self) { try draft(words).validate(sampleCount: 48000) }
    }
    #expect(throws: (any Error).self) { try draft([word]).validate(sampleCount: 0) }
    let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(draft([word]))) as! [String: Any]
    #expect(encoded["expected_transcript_sha256"] as? String == String(repeating: "a", count: 64))
    #expect((encoded["segments"] as? [[String: Any]])?.first?["end_seconds"] as? Double == 1)
}
