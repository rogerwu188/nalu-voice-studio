import AVFoundation

@MainActor
final class SpeechPlayback: NSObject, @preconcurrency AVSpeechSynthesizerDelegate {
    private let synthesizer = AVSpeechSynthesizer()
    private var activeUtterance: AVSpeechUtterance?
    private var completion: ((Bool) -> Void)?

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    func speak(
        _ text: String,
        rate: Float = 0.42,
        completion: ((Bool) -> Void)? = nil
    ) {
        let cleaned = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else {
            completion?(false)
            return
        }
        synthesizer.stopSpeaking(at: .immediate)
        let utterance = AVSpeechUtterance(string: cleaned)
        activeUtterance = utterance
        self.completion = completion
        utterance.voice = AVSpeechSynthesisVoice(language: "zh-CN")
        utterance.rate = min(max(rate, 0.30), 0.54)
        synthesizer.speak(utterance)
    }

    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
    }

    func speechSynthesizer(
        _ synthesizer: AVSpeechSynthesizer,
        didFinish utterance: AVSpeechUtterance
    ) {
        finish(utterance, completed: true)
    }

    func speechSynthesizer(
        _ synthesizer: AVSpeechSynthesizer,
        didCancel utterance: AVSpeechUtterance
    ) {
        finish(utterance, completed: false)
    }

    private func finish(_ utterance: AVSpeechUtterance, completed: Bool) {
        guard utterance === activeUtterance else { return }
        let callback = completion
        activeUtterance = nil
        completion = nil
        callback?(completed)
    }
}
