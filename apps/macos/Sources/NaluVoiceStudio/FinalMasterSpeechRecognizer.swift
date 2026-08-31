import Foundation
import Speech

enum FinalMasterSpeechError: LocalizedError {
    case permissionDenied
    case recognizerUnavailable
    case onDeviceRecognitionUnavailable
    case emptyResult

    var errorDescription: String? {
        switch self {
        case .permissionDenied: "没有语音识别权限，成片声音检查不会继续"
        case .recognizerUnavailable: "本机中文语音识别暂时不可用"
        case .onDeviceRecognitionUnavailable: "这台 Mac 不支持本机成片识别，Nalu 不会改用云端"
        case .emptyResult: "没有从成片中识别出可核对的中文内容"
        }
    }
}

struct FinalMasterRecognitionResult: Equatable, Sendable {
    let transcript: String
    let segments: [SemanticASRSegmentDraft]
    let recognizerVersion: String
    let generatedAt: String

    func semanticQADraft(masterSHA256: String) -> SemanticMediaQADraft {
        SemanticMediaQADraft(
            sourceMasterSHA256: masterSHA256,
            transcript: transcript,
            segments: segments,
            recognizerID: "apple-speech-on-device",
            recognizerVersion: recognizerVersion,
            locale: "zh-CN",
            localRecognition: true,
            generatedAt: generatedAt
        )
    }
}

@MainActor
final class FinalMasterSpeechRecognizer {
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN"))
    private var activeTask: SFSpeechRecognitionTask?

    func recognize(fileURL: URL) async throws -> FinalMasterRecognitionResult {
        let authorized = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status == .authorized)
            }
        }
        guard authorized else { throw FinalMasterSpeechError.permissionDenied }
        guard let recognizer, recognizer.isAvailable else {
            throw FinalMasterSpeechError.recognizerUnavailable
        }
        guard recognizer.supportsOnDeviceRecognition else {
            throw FinalMasterSpeechError.onDeviceRecognitionUnavailable
        }
        activeTask?.cancel()
        let request = SFSpeechURLRecognitionRequest(url: fileURL)
        request.shouldReportPartialResults = false
        request.requiresOnDeviceRecognition = true
        request.taskHint = .dictation
        return try await withCheckedThrowingContinuation { continuation in
            var finished = false
            activeTask = recognizer.recognitionTask(with: request) { [weak self] result, error in
                guard !finished else { return }
                if let error {
                    finished = true
                    self?.activeTask = nil
                    continuation.resume(throwing: error)
                    return
                }
                guard let result, result.isFinal else { return }
                let transcription = result.bestTranscription
                let transcript = transcription.formattedString.trimmingCharacters(
                    in: .whitespacesAndNewlines
                )
                guard !transcript.isEmpty else {
                    finished = true
                    self?.activeTask = nil
                    continuation.resume(throwing: FinalMasterSpeechError.emptyResult)
                    return
                }
                let segments = transcription.segments.map { segment in
                    SemanticASRSegmentDraft(
                        startSeconds: segment.timestamp,
                        endSeconds: segment.timestamp + segment.duration,
                        text: segment.substring,
                        confidence: Double(segment.confidence)
                    )
                }
                finished = true
                self?.activeTask = nil
                continuation.resume(
                    returning: FinalMasterRecognitionResult(
                        transcript: transcript,
                        segments: segments,
                        recognizerVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                        generatedAt: ISO8601DateFormatter().string(from: Date())
                    )
                )
            }
        }
    }
}
