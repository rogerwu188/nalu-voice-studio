import CryptoKit
import Foundation
import Testing
@testable import NaluVoiceStudio

@MainActor @Test func acceptedRecordingTranscriptionPreservesSourceAndCleansTemporaryInput() async throws {
    // The injected recognizer tests orchestration only; no Apple permission or ASR QA claim.
    var header = Array("RIFF".utf8)
    func append(_ value: Int, _ count: Int) {
        header += (0..<count).map { UInt8((value >> ($0 * 8)) & 255) }
    }
    append(36 + 192000, 4); header += Array("WAVEfmt ".utf8)
    append(16, 4); append(1, 2); append(2, 2); append(48000, 4); append(192000, 4)
    append(4, 2); append(16, 2); header += Array("data".utf8); append(192000, 4)
    let data = Data(header) + Data(repeating: 0, count: 192000)
    let sha = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    let audio = AcceptedEpisodeAudio(data: data, sha256: sha, takeID: "take", reviewID: "review", sampleCount: 48000)
    let result = FinalMasterRecognitionResult(transcript: "海边", segments: [
        SemanticASRSegmentDraft(startSeconds: 0.1, endSeconds: 0.8, text: "海边", confidence: 0.9)],
        recognizerVersion: "synthetic-test", generatedAt: "2026-09-07T08:00:00Z")
    var path: URL?
    let transcriber = EpisodeRecordingTranscriber { file in
        path = file
        #expect(try Data(contentsOf: file) == data)
        let permissions = try FileManager.default.attributesOfItem(atPath: file.path)[.posixPermissions] as? NSNumber
        #expect(permissions?.intValue == 0o600)
        return result
    }
    let draft = try await transcriber.transcribe(audio)
    #expect(draft.sourceAudioSHA256 == sha && draft.takeID == "take" && draft.reviewID == "review")
    #expect(draft.segments == result.segments && draft.localRecognition)
    #expect(!draft.captionsApproved && !draft.speechAlignmentVerified)
    #expect(!FileManager.default.fileExists(atPath: path!.deletingLastPathComponent().path))
    let failing = EpisodeRecordingTranscriber { file in
        path = file; throw FinalMasterSpeechError.emptyResult
    }
    do { _ = try await failing.transcribe(audio); Issue.record("failed recognition must not produce captions") } catch {}
    #expect(!FileManager.default.fileExists(atPath: path!.deletingLastPathComponent().path))
    for segment in [SemanticASRSegmentDraft(startSeconds: -1, endSeconds: 0.8, text: "海", confidence: 1),
                    SemanticASRSegmentDraft(startSeconds: 0.1, endSeconds: 2, text: "海", confidence: 1),
                    SemanticASRSegmentDraft(startSeconds: 0.1, endSeconds: 0.8, text: "海", confidence: .nan)] {
        #expect(throws: (any Error).self) {
            try EpisodeRecordingTranscript.draft(audio: audio, result: FinalMasterRecognitionResult(
                transcript: "海", segments: [segment], recognizerVersion: "synthetic-test", generatedAt: result.generatedAt))
        }
    }
}
