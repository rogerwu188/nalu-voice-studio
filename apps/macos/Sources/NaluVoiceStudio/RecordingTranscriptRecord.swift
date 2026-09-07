import Foundation

struct RecordingTranscriptSubmission: Encodable, Sendable {
    let expected_take_sha256: String
    let expected_review_id: String
    let source_audio_sha256: String
    let sample_count: Int
    let transcript: String
    let segments: [SemanticASRSegmentDraft]
    let recognizer_id: String
    let recognizer_version: String
    let generated_at: String
    let local_recognition: Bool

    init(take: EpisodeAudioTake, draft: EpisodeRecordingTranscript) {
        expected_take_sha256 = take.payload.take_sha256; expected_review_id = draft.reviewID
        source_audio_sha256 = draft.sourceAudioSHA256; sample_count = draft.sampleCount
        transcript = draft.transcript; segments = draft.segments; recognizer_id = draft.recognizerID
        recognizer_version = draft.recognizerVersion; generated_at = draft.generatedAt; local_recognition = draft.localRecognition
    }
}

struct RecordingTranscriptRecord: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload

    struct Payload: Decodable, Sendable {
        let take_id: String
        let expected_take_sha256: String
        let expected_review_id: String
        let source_audio_sha256: String
        let sample_count: Int
        let transcript: String
        let segments: [SemanticASRSegmentDraft]
        let recognizer_id: String
        let recognizer_version: String
        let generated_at: String
        let local_recognition: Bool
        let captions_approved: Bool
        let speech_alignment_verified: Bool
        let master_accepted: Bool
        let recognition_evidence: String
        let transcript_sha256: String
    }

    func validate(take: EpisodeAudioTake, reviewID: String) throws {
        let p = payload
        guard !Task.isCancelled, !id.isEmpty, run_id == take.run_id, event_type == "episode_recording_transcribed",
              p.take_id == take.id, p.expected_take_sha256 == take.payload.take_sha256,
              p.expected_review_id == reviewID, p.sample_count == take.payload.decoded_sample_count,
              p.source_audio_sha256.count == 64, p.source_audio_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              p.transcript_sha256.count == 64, p.transcript_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              p.recognizer_id == "apple-speech-on-device", p.local_recognition,
              p.recognition_evidence == "CLIENT_REPORTED_LOCAL_ASR_DRAFT",
              !p.captions_approved, !p.speech_alignment_verified, !p.master_accepted,
              !p.transcript.isEmpty, p.transcript.count <= 24000, !p.segments.isEmpty, p.segments.count <= 4000,
              !p.recognizer_version.isEmpty else { throw LibrarySnapshotRefreshError.contextChanged }
        var end = 0.0
        for word in p.segments {
            guard word.startSeconds.isFinite, word.endSeconds.isFinite, word.startSeconds >= end,
                  word.endSeconds > word.startSeconds, word.endSeconds <= Double(p.sample_count) / 48000,
                  !word.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  word.confidence.map({ $0.isFinite && (0...1).contains($0) }) ?? true else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            end = word.endSeconds
        }
    }
}
