import AVFoundation

@MainActor
final class SpeechPlayback {
    private let synthesizer = AVSpeechSynthesizer()

    func speak(_ text: String, rate: Float = 0.42) {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        synthesizer.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: cleaned)
        utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN")
        utterance.rate = min(max(rate, 0.30), 0.54)
        synthesizer.speak(utterance)
    }

    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
    }
}
