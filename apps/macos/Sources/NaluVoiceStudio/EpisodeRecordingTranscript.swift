import CryptoKit
import Foundation

struct EpisodeRecordingTranscript: Encodable, Sendable {
    let takeID: String
    let reviewID: String
    let sourceAudioSHA256: String
    let sampleCount: Int
    let transcript: String
    let segments: [SemanticASRSegmentDraft]
    let recognizerID: String
    let recognizerVersion: String
    let generatedAt: String
    let localRecognition = true
    let captionsApproved = false
    let speechAlignmentVerified = false

    static func draft(audio: AcceptedEpisodeAudio, result: FinalMasterRecognitionResult) throws -> Self {
        let duration = Double(audio.sampleCount) / 48000
        guard !audio.takeID.isEmpty, !audio.reviewID.isEmpty,
              (1...14_400_000).contains(audio.sampleCount),
              !result.transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              result.transcript.count <= 24000, !result.segments.isEmpty, result.segments.count <= 4000,
              !result.recognizerVersion.isEmpty,
              ISO8601DateFormatter().date(from: result.generatedAt) != nil else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var previousEnd = 0.0
        for segment in result.segments {
            guard segment.startSeconds.isFinite, segment.endSeconds.isFinite,
                  segment.startSeconds >= previousEnd, segment.endSeconds > segment.startSeconds,
                  segment.endSeconds <= duration,
                  !segment.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  segment.text.count <= 2000,
                  segment.confidence.map({ $0.isFinite && (0...1).contains($0) }) ?? true else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            previousEnd = segment.endSeconds
        }
        return Self(takeID: audio.takeID, reviewID: audio.reviewID, sourceAudioSHA256: audio.sha256,
            sampleCount: audio.sampleCount, transcript: result.transcript, segments: result.segments,
            recognizerID: "apple-speech-on-device", recognizerVersion: result.recognizerVersion,
            generatedAt: result.generatedAt)
    }
}

@MainActor final class EpisodeRecordingTranscriber {
    private let recognize: (URL) async throws -> FinalMasterRecognitionResult

    init(recognize: @escaping (URL) async throws -> FinalMasterRecognitionResult = { url in
        try await FinalMasterSpeechRecognizer().recognize(fileURL: url)
    }) { self.recognize = recognize }

    func transcribe(_ audio: AcceptedEpisodeAudio) async throws -> EpisodeRecordingTranscript {
        guard !Task.isCancelled, (1...14_400_000).contains(audio.sampleCount),
              audio.data.count == 44 + audio.sampleCount * 4,
              SHA256.hash(data: audio.data).map({ String(format: "%02x", $0) }).joined() == audio.sha256 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        // Private transient input only. Do not put family audio into backups or
        // retain a file after the on-device recognizer has returned/failed.
        let folder = FileManager.default.temporaryDirectory.appending(path: "nalu-recording-asr-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false,
                                                attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: folder) }
        let file = folder.appending(path: "accepted.wav")
        try audio.data.write(to: file, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
        let result = try await recognize(file)
        try Task.checkCancellation()
        return try EpisodeRecordingTranscript.draft(audio: audio, result: result)
    }
}
