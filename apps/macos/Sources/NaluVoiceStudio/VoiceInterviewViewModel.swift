import Foundation
import Observation

@MainActor
@Observable
final class VoiceInterviewViewModel {
    var projects: [NaluProject] = []
    var selectedProjectID: String?
    var messages: [InterviewMessage] = [
        InterviewMessage(
            speaker: .nalu,
            text: "您好，我是 Nalu。我们可以从一段回忆、一个人物，或者一个故事想法开始。您想讲什么？"
        )
    ]
    var transcript = ""
    var isListening = false
    var runtimeStatus = "正在连接本地制片厂…"
    var errorMessage: String?

    private let runtime = RuntimeClient()
    private let speech = SpeechRecorder()

    func load() async {
        do {
            let health = try await runtime.health()
            runtimeStatus = "本地制片厂已就绪 · \(health.version)"
            projects = try await runtime.listProjects()
        } catch {
            runtimeStatus = "本地制片厂尚未启动"
            errorMessage = error.localizedDescription
        }
    }

    func toggleListening() async {
        if isListening {
            speech.stop()
            isListening = false
            commitTranscript()
            return
        }
        guard await speech.requestAuthorization() else {
            errorMessage = "需要麦克风和语音识别权限，才能听您讲故事。"
            return
        }
        do {
            transcript = ""
            try speech.start { [weak self] text in self?.transcript = text }
            isListening = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func commitTranscript() {
        let spoken = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !spoken.isEmpty else { return }
        messages.append(InterviewMessage(speaker: .user, text: spoken))
        messages.append(
            InterviewMessage(
                speaker: .nalu,
                text: "我记下来了。接下来我会帮您整理成项目总纲，再和您一起规划每一集。"
            )
        )
        transcript = ""
    }
}
