import Foundation
import Observation
import SwiftUI
import WebKit

enum RealtimeVoiceState: Equatable {
    case off
    case connecting
    case reconnecting
    case listening
    case thinking
    case speaking
    case unavailable(String)

    var label: String {
        switch self {
        case .off: "自然语音未开启"
        case .connecting: "正在连接自然语音…"
        case .reconnecting: "连接中断，正在尝试恢复…"
        case .listening: "正在听您说话"
        case .thinking: "正在想怎么回答"
        case .speaking: "Nalu 正在回答，可以随时插话"
        case .unavailable(let reason): "自然语音不可用：\(reason)"
        }
    }

    var systemImage: String {
        switch self {
        case .off: "waveform.slash"
        case .connecting: "arrow.triangle.2.circlepath"
        case .reconnecting: "wifi.exclamationmark"
        case .listening: "ear.fill"
        case .thinking: "ellipsis.bubble.fill"
        case .speaking: "speaker.wave.3.fill"
        case .unavailable: "exclamationmark.triangle.fill"
        }
    }

    var isActive: Bool {
        switch self {
        case .connecting, .reconnecting, .listening, .thinking, .speaking: true
        case .off, .unavailable: false
        }
    }
}

enum RealtimeSessionLimit {
    static let choices = [5, 10, 20]

    static func normalized(_ minutes: Int) -> Int {
        choices.contains(minutes) ? minutes : 10
    }

    static func elapsedLabel(seconds: Int, limitMinutes: Int) -> String {
        let safeSeconds = max(0, seconds)
        return String(
            format: "%02d:%02d / %d:00",
            safeSeconds / 60,
            safeSeconds % 60,
            normalized(limitMinutes)
        )
    }
}

struct RealtimeSessionConfiguration {
    static let model = "gpt-realtime-2.1"
    static let interviewToolName = "record_interview_answer"

    static var interviewTool: [String: Any] {
        [
            "type": "function",
            "name": interviewToolName,
            "description": """
            Record a direct answer to Nalu's current unfinished interview or reversible planning
            task, apply an explicit interview pause/resume/repeat/go-back command, or pass the exact
            phrases “暂停本集制作”, “确认暂停本集制作”, “不暂停”, or “恢复本集制作” to the local
            safety controller. Production pause requires the controller's second verbal confirmation.
            A season or script approval may be recorded only when the visible app has armed that
            exact approval task. Do not call this for questions, complaints, unrelated corrections,
            small talk, deletion, paid generation, biometric consent, or publishing requests.
            """,
            "parameters": [
                "type": "object",
                "properties": [
                    "answer": [
                        "type": "string",
                        "description": "The user's direct answer, preserving their meaning.",
                    ]
                ],
                "required": ["answer"],
                "additionalProperties": false,
            ],
        ]
    }

    static func requestBody(instructions: String) throws -> Data {
        try JSONSerialization.data(
            withJSONObject: [
                "session": [
                    "type": "realtime",
                    "model": model,
                    "instructions": instructions,
                    "output_modalities": ["audio"],
                    "max_output_tokens": 512,
                    "tools": [interviewTool],
                    "tool_choice": "auto",
                    "audio": [
                        "input": [
                            "transcription": [
                                "model": "gpt-4o-mini-transcribe",
                                "language": "zh",
                            ],
                            "turn_detection": [
                                "type": "semantic_vad",
                                "eagerness": "low",
                                "create_response": true,
                                "interrupt_response": true,
                            ],
                        ],
                        "output": ["voice": "marin"],
                    ],
                ]
            ]
        )
    }
}

struct RealtimeClientSecretEnvelope: Decodable {
    struct Session: Decodable {
        let type: String
        let model: String
    }

    let value: String
    let expiresAt: TimeInterval
    let session: Session

    private enum CodingKeys: String, CodingKey {
        case value
        case expiresAt = "expires_at"
        case session
    }
}

enum RealtimeAPIContract {
    static let clientSecretsURL = URL(
        string: "https://api.openai.com/v1/realtime/client_secrets"
    )!
    static let callsURL = "https://api.openai.com/v1/realtime/calls"
    static let dataChannelLabel = "oai-events"
    static let minimumClientSecretLifetime: TimeInterval = 5
    static let maximumClientSecretBytes = 4_096

    static func validatedClientSecret(from data: Data, now: Date = Date()) throws -> String {
        guard let envelope = try? JSONDecoder().decode(
            RealtimeClientSecretEnvelope.self,
            from: data
        ) else {
            throw RealtimeVoiceError.invalidSessionResponse
        }
        let trimmedValue = envelope.value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmedValue == envelope.value,
              !trimmedValue.isEmpty,
              trimmedValue.utf8.count <= maximumClientSecretBytes,
              envelope.expiresAt.isFinite,
              envelope.expiresAt - now.timeIntervalSince1970 >= minimumClientSecretLifetime,
              envelope.session.type == "realtime",
              envelope.session.model == RealtimeSessionConfiguration.model else {
            throw RealtimeVoiceError.invalidSessionResponse
        }
        return trimmedValue
    }
}

struct RealtimeInterviewToolResult: Codable, Equatable {
    let accepted: Bool
    let message: String
    let nextPrompt: String
    let requiresVisibleConfirmation: Bool

    func jsonString() -> String {
        guard let data = try? JSONEncoder().encode(self),
              let value = String(data: data, encoding: .utf8) else {
            return #"{"accepted":false,"message":"本地结果编码失败。","nextPrompt":"","requiresVisibleConfirmation":true}"#
        }
        return value
    }
}

enum RealtimeJavaScriptBridge {
    static func stringLiteral(_ value: String) -> String? {
        guard let data = try? JSONEncoder().encode(value) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

struct RealtimeInterviewToolCall: Equatable {
    let callID: String
    let answer: String

    static func parse(_ payload: [String: Any]) -> RealtimeInterviewToolCall? {
        guard payload["name"] as? String == RealtimeSessionConfiguration.interviewToolName,
              let callID = payload["callID"] as? String,
              !callID.isEmpty,
              callID.utf8.count <= 512,
              let arguments = payload["arguments"] as? String,
              arguments.utf8.count <= 8_192,
              let data = arguments.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              object.keys.allSatisfy({ $0 == "answer" }),
              let rawAnswer = object["answer"] as? String else { return nil }
        let answer = rawAnswer.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !answer.isEmpty, answer.count <= 2_000 else { return nil }
        return RealtimeInterviewToolCall(callID: callID, answer: answer)
    }
}

actor RealtimeSessionBroker {
    private let keychain = KeychainSecretStore()
    private let session: URLSession

    init(session: URLSession? = nil) {
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 20
            configuration.waitsForConnectivity = false
            self.session = URLSession(configuration: configuration)
        }
    }

    func createClientSecret(instructions: String) async throws -> String {
        guard let apiKey = try keychain.secret(for: .openAIRealtime) else {
            throw RealtimeVoiceError.missingCredential
        }
        var request = URLRequest(url: RealtimeAPIContract.clientSecretsURL)
        request.httpMethod = "POST"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try RealtimeSessionConfiguration.requestBody(
            instructions: instructions
        )
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode) else {
            throw RealtimeVoiceError.sessionRequestFailed
        }
        return try RealtimeAPIContract.validatedClientSecret(from: data)
    }
}

enum RealtimeVoiceError: LocalizedError {
    case missingCredential
    case sessionRequestFailed
    case invalidSessionResponse
    case webViewNotReady

    var errorDescription: String? {
        switch self {
        case .missingCredential: "请先在“模型密钥”中保存 OpenAI Realtime API 密钥。"
        case .sessionRequestFailed: "OpenAI 没有建立实时语音会话。请检查网络、密钥和账户余额。"
        case .invalidSessionResponse: "实时语音会话凭证格式不正确。"
        case .webViewNotReady: "实时语音组件尚未准备好，请稍后再试。"
        }
    }
}

@MainActor
@Observable
final class RealtimeVoiceCoordinator: NSObject, WKScriptMessageHandler,
    WKNavigationDelegate, WKUIDelegate {
    var state: RealtimeVoiceState = .off
    var sessionStartedAt: Date?
    var sessionElapsedSeconds = 0
    var sessionLimitMinutes = 10
    var retryAllowed = false
    var onUserTranscript: ((String) -> Void)?
    var onAssistantTranscript: ((String) -> Void)?
    var onInterviewAnswer: ((String) -> RealtimeInterviewToolResult)?

    private let broker = RealtimeSessionBroker()
    private weak var webView: WKWebView?
    private var isPageReady = false
    private var pendingToken: String?
    private var completedToolCallIDs: Set<String> = []
    private var lastInstructions: String?
    private var sessionClock: Task<Void, Never>?
    private var dataChannelReady = false
    private var pendingSpokenPrompt: String?

    func attach(_ webView: WKWebView) {
        guard self.webView !== webView else { return }
        self.webView = webView
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.configuration.userContentController.removeScriptMessageHandler(
            forName: "naluRealtime"
        )
        webView.configuration.userContentController.add(self, name: "naluRealtime")
        webView.loadHTMLString(Self.webRTCPage, baseURL: URL(string: "https://api.openai.com"))
    }

    func start(instructions: String, limitMinutes: Int = 10) async {
        guard webView != nil else {
            state = .unavailable(RealtimeVoiceError.webViewNotReady.localizedDescription)
            return
        }
        stopSessionClock()
        sessionStartedAt = nil
        sessionElapsedSeconds = 0
        sessionLimitMinutes = RealtimeSessionLimit.normalized(limitMinutes)
        lastInstructions = instructions
        completedToolCallIDs.removeAll()
        dataChannelReady = false
        retryAllowed = false
        state = .connecting
        do {
            let token = try await broker.createClientSecret(instructions: instructions)
            pendingToken = token
            startWebRTCIfReady()
        } catch {
            state = .unavailable(error.localizedDescription)
            retryAllowed = true
        }
    }

    func retry() async {
        guard retryAllowed, let lastInstructions else { return }
        await start(instructions: lastInstructions, limitMinutes: sessionLimitMinutes)
    }

    func speakPrompt(_ prompt: String) {
        guard state.isActive else { return }
        guard dataChannelReady else {
            pendingSpokenPrompt = prompt
            return
        }
        sendSpokenPrompt(prompt)
    }

    private func sendSpokenPrompt(_ prompt: String) {
        guard let promptJSON = RealtimeJavaScriptBridge.stringLiteral(prompt) else { return }
        webView?.evaluateJavaScript("window.naluRealtime.speakPrompt(\(promptJSON))") {
            _, error in
            if let error {
                Task { @MainActor in
                    self.failSession(reason: error.localizedDescription, allowRetry: true)
                }
            }
        }
    }

    func stop() {
        webView?.evaluateJavaScript("window.naluRealtime.stop()")
        pendingToken = nil
        sessionStartedAt = nil
        sessionElapsedSeconds = 0
        stopSessionClock()
        completedToolCallIDs.removeAll()
        dataChannelReady = false
        pendingSpokenPrompt = nil
        lastInstructions = nil
        retryAllowed = false
        state = .off
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        isPageReady = true
        startWebRTCIfReady()
    }

    func webView(
        _ webView: WKWebView,
        requestMediaCapturePermissionFor origin: WKSecurityOrigin,
        initiatedByFrame frame: WKFrameInfo,
        type: WKMediaCaptureType,
        decisionHandler: @escaping (WKPermissionDecision) -> Void
    ) {
        // macOS still owns the app-level microphone permission. This grants the
        // embedded, non-persistent WebRTC view only after Nalu's explicit cloud
        // audio consent sheet has initiated a session.
        decisionHandler(state == .connecting ? .grant : .deny)
    }

    func userContentController(
        _ userContentController: WKUserContentController,
        didReceive message: WKScriptMessage
    ) {
        guard let payload = message.body as? [String: Any],
              let kind = payload["kind"] as? String else { return }
        if kind == "status", let value = payload["value"] as? String {
            switch value {
            case "connected", "listening":
                dataChannelReady = true
                if sessionStartedAt == nil {
                    sessionStartedAt = Date()
                    startSessionClock()
                }
                state = .listening
                if let pendingSpokenPrompt {
                    self.pendingSpokenPrompt = nil
                    sendSpokenPrompt(pendingSpokenPrompt)
                }
            case "thinking": state = .thinking
            case "speaking": state = .speaking
            case "reconnecting": state = .reconnecting
            case "off": state = .off
            default: break
            }
            return
        }
        if kind == "user", let text = payload["text"] as? String, !text.isEmpty {
            onUserTranscript?(text)
        } else if kind == "assistant",
                  let text = payload["text"] as? String, !text.isEmpty {
            onAssistantTranscript?(text)
        } else if kind == "error", let text = payload["text"] as? String {
            failSession(reason: text, allowRetry: true)
        } else if kind == "tool" {
            handleToolCall(payload)
        }
    }

    private func startSessionClock() {
        stopSessionClock()
        sessionClock = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self, !Task.isCancelled, self.state.isActive else { break }
                self.sessionElapsedSeconds += 1
                if self.sessionElapsedSeconds >= self.sessionLimitMinutes * 60 {
                    self.failSession(
                        reason: "已达到本次 \(self.sessionLimitMinutes) 分钟上限，已自动断开。",
                        allowRetry: false
                    )
                    break
                }
            }
        }
    }

    private func stopSessionClock() {
        sessionClock?.cancel()
        sessionClock = nil
    }

    private func failSession(reason: String, allowRetry: Bool) {
        webView?.evaluateJavaScript("window.naluRealtime.stop(false)")
        pendingToken = nil
        stopSessionClock()
        dataChannelReady = false
        retryAllowed = allowRetry
        state = .unavailable(reason)
    }

    private func handleToolCall(_ payload: [String: Any]) {
        guard let callID = payload["callID"] as? String,
              !callID.isEmpty,
              !completedToolCallIDs.contains(callID) else { return }
        completedToolCallIDs.insert(callID)

        let rejected = RealtimeInterviewToolResult(
            accepted: false,
            message: "这个语音操作没有被允许，请回到可见界面确认。",
            nextPrompt: "",
            requiresVisibleConfirmation: true
        )
        guard let call = RealtimeInterviewToolCall.parse(payload),
              let onInterviewAnswer else {
            completeToolCall(callID: callID, result: rejected)
            return
        }
        completeToolCall(callID: callID, result: onInterviewAnswer(call.answer))
    }

    private func completeToolCall(callID: String, result: RealtimeInterviewToolResult) {
        guard let callIDJSON = RealtimeJavaScriptBridge.stringLiteral(callID),
              let outputJSON = RealtimeJavaScriptBridge.stringLiteral(result.jsonString()) else {
            return
        }
        webView?.evaluateJavaScript(
            "window.naluRealtime.completeToolCall(\(callIDJSON), \(outputJSON))"
        ) { _, error in
            if let error {
                Task { @MainActor in
                    self.failSession(reason: error.localizedDescription, allowRetry: true)
                }
            }
        }
    }

    private func startWebRTCIfReady() {
        guard isPageReady, let token = pendingToken, let webView else { return }
        pendingToken = nil
        guard let tokenJSON = RealtimeJavaScriptBridge.stringLiteral(token) else {
            state = .unavailable(RealtimeVoiceError.invalidSessionResponse.localizedDescription)
            return
        }
        webView.evaluateJavaScript("window.naluRealtime.start(\(tokenJSON))") { _, error in
            if let error {
                Task { @MainActor in
                    self.failSession(reason: error.localizedDescription, allowRetry: true)
                }
            }
        }
    }

    static let webRTCPage = #"""
    <!doctype html><html><body><script>
    window.naluRealtime = (() => {
      let pc = null, dc = null, stream = null, audio = null, disconnectTimer = null;
      let responseActive = false;
      const post = (kind, value) => window.webkit.messageHandlers.naluRealtime.postMessage({kind, value});
      async function start(token) {
        try {
          stop();
          post("status", "connecting");
          pc = new RTCPeerConnection();
          pc.onconnectionstatechange = () => {
            if (!pc) return;
            if (pc.connectionState === "connected") {
              if (disconnectTimer) clearTimeout(disconnectTimer);
              disconnectTimer = null;
              post("status", "connected");
            } else if (pc.connectionState === "disconnected") {
              post("status", "reconnecting");
              if (disconnectTimer) clearTimeout(disconnectTimer);
              disconnectTimer = setTimeout(() => {
                if (pc && pc.connectionState === "disconnected") {
                  post("error", "网络连接中断，请检查网络后重新连接");
                }
              }, 3000);
            } else if (pc.connectionState === "failed") {
              post("error", "实时语音连接已失败，请重新连接");
            }
          };
          audio = document.createElement("audio");
          audio.autoplay = true;
          document.body.appendChild(audio);
          pc.ontrack = event => { audio.srcObject = event.streams[0]; };
          stream = await navigator.mediaDevices.getUserMedia({audio: true});
          pc.addTrack(stream.getTracks()[0]);
          dc = pc.createDataChannel("\#(RealtimeAPIContract.dataChannelLabel)");
          dc.addEventListener("open", () => post("status", "connected"));
          dc.addEventListener("message", event => {
            const value = JSON.parse(event.data);
            if (value.type === "input_audio_buffer.speech_started") post("status", "listening");
            if (value.type === "input_audio_buffer.speech_stopped") post("status", "thinking");
            if (value.type === "response.created") {
              responseActive = true;
              post("status", "thinking");
            }
            if (value.type === "response.output_audio.delta") post("status", "speaking");
            if (value.type === "conversation.item.input_audio_transcription.completed") {
              post("user", value.transcript || "");
            }
            if (value.type === "response.output_audio_transcript.done") {
              post("assistant", value.transcript || "");
              post("status", "listening");
            }
            if (value.type === "response.done") {
              responseActive = false;
              const calls = value.response?.output?.filter(item => item.type === "function_call") || [];
              calls.forEach(call => window.webkit.messageHandlers.naluRealtime.postMessage({
                kind: "tool", name: call.name || "", callID: call.call_id || "",
                arguments: call.arguments || "{}"
              }));
            }
            if (value.type === "error") {
              post("error", value.error?.message || value.message || "实时语音发生错误");
            }
          });
          const offer = await pc.createOffer();
          await pc.setLocalDescription(offer);
          const response = await fetch("\#(RealtimeAPIContract.callsURL)", {
            method: "POST", body: offer.sdp,
            headers: {Authorization: `Bearer ${token}`, "Content-Type": "application/sdp"}
          });
          if (!response.ok) throw new Error("实时语音连接失败（" + response.status + "）");
          await pc.setRemoteDescription({type: "answer", sdp: await response.text()});
        } catch (error) {
          post("error", error.message || "实时语音连接失败");
          stop(false);
        }
      }
      function stop(notify = true) {
        if (disconnectTimer) clearTimeout(disconnectTimer);
        disconnectTimer = null;
        if (dc) dc.close();
        if (pc) pc.close();
        if (stream) stream.getTracks().forEach(track => track.stop());
        if (audio) audio.remove();
        pc = dc = stream = audio = null;
        responseActive = false;
        if (notify) post("status", "off");
      }
      function completeToolCall(callID, output) {
        if (!dc || dc.readyState !== "open") {
          post("error", "语音采访结果无法返回，请重新连接");
          return;
        }
        dc.send(JSON.stringify({
          type: "conversation.item.create",
          item: {type: "function_call_output", call_id: callID, output}
        }));
        dc.send(JSON.stringify({type: "response.create"}));
      }
      function speakPrompt(prompt) {
        if (!dc || dc.readyState !== "open") {
          post("error", "自然语音尚未准备好，请稍后再试");
          return;
        }
        const createPromptResponse = () => {
          if (!dc || dc.readyState !== "open") return;
          post("status", "thinking");
          dc.send(JSON.stringify({
            type: "response.create",
            response: {
              instructions: "请用简短、舒缓的中文原样询问用户这个问题，不要补充别的问题：" + prompt,
              tool_choice: "none"
            }
          }));
        };
        if (responseActive) {
          dc.send(JSON.stringify({type: "response.cancel"}));
          responseActive = false;
          setTimeout(createPromptResponse, 100);
        } else {
          createPromptResponse();
        }
      }
      return {start, stop, completeToolCall, speakPrompt};
    })();
    </script></body></html>
    """#
}

struct RealtimeWebRTCContainer: NSViewRepresentable {
    let coordinator: RealtimeVoiceCoordinator

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.mediaTypesRequiringUserActionForPlayback = []
        let view = WKWebView(frame: .zero, configuration: configuration)
        coordinator.attach(view)
        return view
    }

    func updateNSView(_ nsView: WKWebView, context: Context) {}
}
