import Foundation

struct RecordingCaptionSubmission: Encodable, Sendable {
    let expected_transcript_sha256: String
    let expected_previous_review_id: String?
    let segments: [SemanticASRSegmentDraft]
    let reviewed_by: String
    let confirmation: String

    func validate(sampleCount: Int) throws {
        guard expected_transcript_sha256.count == 64,
              expected_transcript_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              !reviewed_by.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              reviewed_by.count <= 160, !confirmation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              confirmation.count <= 2000, (1...14_400_000).contains(sampleCount),
              !segments.isEmpty, segments.count <= 4000,
              segments.map(\.text).joined(separator: " ").count <= 24000 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var end = 0.0
        for word in segments {
            guard word.startSeconds.isFinite, word.endSeconds.isFinite, word.startSeconds >= end,
                  word.endSeconds > word.startSeconds, word.endSeconds <= Double(sampleCount) / 48000,
                  !word.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, word.text.count <= 2000,
                  word.confidence.map({ $0.isFinite && (0...1).contains($0) }) ?? true else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            end = word.endSeconds
        }
    }
}

struct RecordingCaptionReview: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let take_id: String
        let transcript_id: String
        let expected_transcript_sha256: String
        let expected_previous_review_id: String?
        let source_audio_sha256: String
        let expected_review_id: String
        let segments: [SemanticASRSegmentDraft]
        let reviewed_by: String
        let confirmation: String
        let captions_approved: Bool
        let speech_alignment_verified: Bool
        let master_accepted: Bool
        let review_evidence: String
        let review_sha256: String
    }
}

struct RecordingCaptionRecovery: Decodable, Sendable {
    let current_transcript_id: String
    let latest_review: RecordingCaptionReview?
    let applies_to_current_transcript: Bool
    let captions_approved: Bool

    func validate(transcript: RecordingTranscriptRecord) throws {
        guard !Task.isCancelled, current_transcript_id == transcript.id else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let applies = latest_review?.payload.transcript_id == transcript.id
        guard applies_to_current_transcript == applies, captions_approved == applies else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        guard let latest = latest_review else { return }
        let p = latest.payload
        guard !latest.id.isEmpty, latest.run_id == transcript.run_id,
              latest.event_type == "episode_transcript_reviewed", p.take_id == transcript.payload.take_id,
              !p.transcript_id.isEmpty, p.captions_approved, !p.speech_alignment_verified, !p.master_accepted,
              p.review_evidence == "USER_ATTESTATION_NOT_ALIGNMENT_PROOF",
              p.review_sha256.count == 64, p.review_sha256.allSatisfy({ "0123456789abcdef".contains($0) }) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        if applies {
            guard p.expected_transcript_sha256 == transcript.payload.transcript_sha256,
                  p.source_audio_sha256 == transcript.payload.source_audio_sha256,
                  p.expected_review_id == transcript.payload.expected_review_id else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            try RecordingCaptionSubmission(expected_transcript_sha256: p.expected_transcript_sha256,
                expected_previous_review_id: p.expected_previous_review_id, segments: p.segments,
                reviewed_by: p.reviewed_by, confirmation: p.confirmation).validate(sampleCount: transcript.payload.sample_count)
        }
    }
}
