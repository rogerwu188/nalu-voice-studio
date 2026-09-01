import CryptoKit
import Foundation
import Speech

private struct RecognitionRequest: Decodable {
    let schemaVersion: String
    let masterPath: String
    let sourceMasterSHA256: String
    let locale: String
    let requiresOnDeviceRecognition: Bool
    let networkFallbackAllowed: Bool

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case masterPath = "master_path"
        case sourceMasterSHA256 = "source_master_sha256"
        case locale
        case requiresOnDeviceRecognition = "requires_on_device_recognition"
        case networkFallbackAllowed = "network_fallback_allowed"
    }
}

private struct RecognitionSegment: Encodable {
    let startSeconds: Double
    let endSeconds: Double
    let text: String
    let confidence: Double

    enum CodingKeys: String, CodingKey {
        case startSeconds = "start_seconds"
        case endSeconds = "end_seconds"
        case text, confidence
    }
}

private struct RecognitionResult: Encodable {
    let schemaVersion = "nalu.apple-speech-result/v1"
    let sourceMasterSHA256: String
    let transcript: String
    let segments: [RecognitionSegment]
    let recognizerVersion: String
    let locale: String
    let generatedAt: String
    let localRecognition = true
    let networkUsed = false

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sourceMasterSHA256 = "source_master_sha256"
        case transcript, segments
        case recognizerVersion = "recognizer_version"
        case locale
        case generatedAt = "generated_at"
        case localRecognition = "local_recognition"
        case networkUsed = "network_used"
    }
}

private enum RecognizerFailure: LocalizedError {
    case invalidRequest
    case unsafeMaster
    case masterDigestMismatch
    case permissionDenied
    case recognizerUnavailable
    case onDeviceUnavailable
    case emptyResult

    var errorDescription: String? {
        switch self {
        case .invalidRequest: "invalid local recognition request"
        case .unsafeMaster: "sealed master is missing or unsafe"
        case .masterDigestMismatch: "sealed master digest mismatch"
        case .permissionDenied: "Speech recognition permission is not authorized"
        case .recognizerUnavailable: "Simplified Chinese speech recognizer is unavailable"
        case .onDeviceUnavailable: "Apple on-device speech recognition is unavailable"
        case .emptyResult: "Apple on-device speech recognition returned no transcript"
        }
    }
}

private func sha256(_ url: URL) throws -> String {
    guard
        url.isFileURL,
        let values = try? url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey]),
        values.isRegularFile == true,
        values.isSymbolicLink != true,
        let stream = InputStream(url: url)
    else { throw RecognizerFailure.unsafeMaster }
    stream.open()
    defer { stream.close() }
    var digest = SHA256()
    var buffer = [UInt8](repeating: 0, count: 1_048_576)
    while stream.hasBytesAvailable {
        let count = stream.read(&buffer, maxLength: buffer.count)
        if count < 0 { throw stream.streamError ?? RecognizerFailure.unsafeMaster }
        if count == 0 { break }
        digest.update(data: Data(buffer[0..<count]))
    }
    return digest.finalize().map { String(format: "%02x", $0) }.joined()
}

private func speechAuthorizationGranted() async -> Bool {
    if SFSpeechRecognizer.authorizationStatus() == .authorized { return true }
    return await withCheckedContinuation { continuation in
        SFSpeechRecognizer.requestAuthorization { status in
            continuation.resume(returning: status == .authorized)
        }
    }
}

private func recognize(_ input: RecognitionRequest) async throws -> RecognitionResult {
    guard
        input.schemaVersion == "nalu.apple-speech-request/v1",
        input.locale == "zh-CN",
        input.requiresOnDeviceRecognition,
        !input.networkFallbackAllowed,
        input.sourceMasterSHA256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil
    else { throw RecognizerFailure.invalidRequest }
    let master = URL(fileURLWithPath: input.masterPath).standardizedFileURL
    guard try sha256(master) == input.sourceMasterSHA256 else {
        throw RecognizerFailure.masterDigestMismatch
    }
    guard await speechAuthorizationGranted() else { throw RecognizerFailure.permissionDenied }
    guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: input.locale)),
          recognizer.isAvailable
    else { throw RecognizerFailure.recognizerUnavailable }
    guard recognizer.supportsOnDeviceRecognition else {
        throw RecognizerFailure.onDeviceUnavailable
    }
    let request = SFSpeechURLRecognitionRequest(url: master)
    request.shouldReportPartialResults = false
    request.requiresOnDeviceRecognition = true
    request.taskHint = .dictation
    let result: SFSpeechRecognitionResult = try await withCheckedThrowingContinuation {
        continuation in
        var finished = false
        var task: SFSpeechRecognitionTask?
        task = recognizer.recognitionTask(with: request) { result, error in
            guard !finished else { return }
            if let error {
                finished = true
                task?.cancel()
                continuation.resume(throwing: error)
                return
            }
            guard let result, result.isFinal else { return }
            finished = true
            task?.finish()
            continuation.resume(returning: result)
        }
    }
    guard try sha256(master) == input.sourceMasterSHA256 else {
        throw RecognizerFailure.masterDigestMismatch
    }
    let transcription = result.bestTranscription
    let transcript = transcription.formattedString.trimmingCharacters(
        in: .whitespacesAndNewlines
    )
    guard !transcript.isEmpty else { throw RecognizerFailure.emptyResult }
    let segments = transcription.segments.map {
        RecognitionSegment(
            startSeconds: $0.timestamp,
            endSeconds: $0.timestamp + $0.duration,
            text: $0.substring,
            confidence: Double($0.confidence)
        )
    }
    return RecognitionResult(
        sourceMasterSHA256: input.sourceMasterSHA256,
        transcript: transcript,
        segments: segments,
        recognizerVersion: "Apple Speech on-device; \(ProcessInfo.processInfo.operatingSystemVersionString)",
        locale: input.locale,
        generatedAt: ISO8601DateFormatter().string(from: Date())
    )
}

@main
private enum NaluSemanticRecognizerMain {
    static func main() async {
        do {
            let request = try JSONDecoder().decode(
                RecognitionRequest.self,
                from: FileHandle.standardInput.readDataToEndOfFile()
            )
            let result = try await recognize(request)
            try FileHandle.standardOutput.write(contentsOf: JSONEncoder().encode(result))
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            FileHandle.standardError.write(Data((message + "\n").utf8))
            exit(1)
        }
    }
}
