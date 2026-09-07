import Foundation
import Speech

enum FinalMasterSpeechError: LocalizedError {
    case permissionDenied
    case recognizerUnavailable
    case onDeviceRecognitionUnavailable
    case emptyResult
    case timedOut

    var errorDescription: String? {
        switch self {
        case .permissionDenied: "没有语音识别权限，成片声音检查不会继续"
        case .recognizerUnavailable: "本机中文语音识别暂时不可用"
        case .onDeviceRecognitionUnavailable: "这台 Mac 不支持本机成片识别，Nalu 不会改用云端"
        case .emptyResult: "没有从成片中识别出可核对的中文内容"
        case .timedOut: "本机语音识别等待超时，原录音保留，可以稍后重试"
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
    private var activeWait: SpeechRecognitionWait<FinalMasterRecognitionResult>?

    func recognize(fileURL: URL) async throws -> FinalMasterRecognitionResult {
        let permission = SpeechRecognitionWait<Bool>()
        let authorized = try await permission.run(timeoutNanoseconds: 120_000_000_000) { complete in
            SFSpeechRecognizer.requestAuthorization { status in
                complete(.success(status == .authorized))
            }
            return {} // The app cannot dismiss macOS's permission dialog.
        }
        try Task.checkCancellation()
        guard authorized else { throw FinalMasterSpeechError.permissionDenied }
        guard let recognizer, recognizer.isAvailable else {
            throw FinalMasterSpeechError.recognizerUnavailable
        }
        guard recognizer.supportsOnDeviceRecognition else {
            throw FinalMasterSpeechError.onDeviceRecognitionUnavailable
        }
        activeWait?.cancel()
        let wait = SpeechRecognitionWait<FinalMasterRecognitionResult>()
        activeWait = wait
        defer { if activeWait === wait { activeWait = nil } }
        let request = SFSpeechURLRecognitionRequest(url: fileURL)
        request.shouldReportPartialResults = false
        request.requiresOnDeviceRecognition = true
        request.taskHint = .dictation
        return try await wait.run(timeoutNanoseconds: 180_000_000_000) { complete in
            let task = recognizer.recognitionTask(with: request) { result, error in
                if let error {
                    complete(.failure(error))
                    return
                }
                guard let result, result.isFinal else { return }
                let transcription = result.bestTranscription
                let transcript = transcription.formattedString.trimmingCharacters(
                    in: .whitespacesAndNewlines
                )
                guard !transcript.isEmpty else {
                    complete(.failure(FinalMasterSpeechError.emptyResult))
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
                complete(.success(FinalMasterRecognitionResult(
                        transcript: transcript,
                        segments: segments,
                        recognizerVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                        generatedAt: ISO8601DateFormatter().string(from: Date())
                    )))
            }
            return { task.cancel() }
        }
    }
}
