import Foundation
import Vision

enum LocalTextRecognizer {
    static func recognize(in imageData: Data) async -> String {
        await Task.detached(priority: .userInitiated) {
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
            request.usesLanguageCorrection = true
            let handler = VNImageRequestHandler(data: imageData, options: [:])
            do {
                try handler.perform([request])
            } catch {
                return ""
            }
            return (request.results ?? [])
                .compactMap { $0.topCandidates(1).first?.string }
                .joined(separator: "\n")
        }.value
    }
}

