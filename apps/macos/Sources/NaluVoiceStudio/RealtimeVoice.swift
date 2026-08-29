import Foundation
import Observation
import SwiftUI
import WebKit

enum RealtimeVoiceState: Equatable {
    case off
    case connecting
    case listening
    case thinking
    case speaking
    case unavailable(String)

    var label: String {
        switch self {
        case .off: "自然语音未开启"
        case .connecting: "正在连接自然语音…"
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
        case .listening: "ear.fill"
        case .thinking: "ellipsis.bubble.fill"
        case .speaking: "speaker.wave.3.fill"
        case .unavailable: "exclamationmark.triangle.fill"
        }
    }

    var isActive: Bool {
        switch self {
        case .connecting, .listening, .thinking, .speaking: true
        case .off, .unavailable: false
        }
    }
}

struct RealtimeSessionConfiguration {
    static let model = "gpt-realtime-2.1"

    static func requestBody(instructions: String) throws -> Data {
        try JSONSerialization.data(
            withJSONObject: [
                "session": [
                    "type": "realtime",
                    "model": model,
                    "instructions": instructions,
                    "output_modalities": ["audio"],
                    "max_output_tokens": 512,
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
        let url = URL(string: "https://api.openai.com/v1/realtime/client_secrets")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try RealtimeSessionConfiguration.requestBody(
            instructions: instructions
        )
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode) else {
            throw RealtimeVoiceError.sessionRequestFailed
        }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let value = object["value"] as? String,
              !value.isEmpty else {
            throw RealtimeVoiceError.invalidSessionResponse
        }
        return value
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
final class RealtimeVoiceCoordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
    var state: RealtimeVoiceState = .off
    var sessionStartedAt: Date?
    var onUserTranscript: ((String) -> Void)?
    var onAssistantTranscript: ((String) -> Void)?

    private let broker = RealtimeSessionBroker()
    private weak var webView: WKWebView?
    private var isPageReady = false
    private var pendingToken: String?

    func attach(_ webView: WKWebView) {
        guard self.webView !== webView else { return }
        self.webView = webView
        webView.navigationDelegate = self
        webView.configuration.userContentController.removeScriptMessageHandler(
            forName: "naluRealtime"
        )
        webView.configuration.userContentController.add(self, name: "naluRealtime")
        webView.loadHTMLString(Self.webRTCPage, baseURL: URL(string: "https://api.openai.com"))
    }

    func start(instructions: String) async {
        guard webView != nil else {
            state = .unavailable(RealtimeVoiceError.webViewNotReady.localizedDescription)
            return
        }
        state = .connecting
        do {
            let token = try await broker.createClientSecret(instructions: instructions)
            pendingToken = token
            startWebRTCIfReady()
        } catch {
            state = .unavailable(error.localizedDescription)
        }
    }

    func stop() {
        webView?.evaluateJavaScript("window.naluRealtime.stop()")
        pendingToken = nil
        sessionStartedAt = nil
        state = .off
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        isPageReady = true
        startWebRTCIfReady()
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
                if sessionStartedAt == nil { sessionStartedAt = Date() }
                state = .listening
            case "thinking": state = .thinking
            case "speaking": state = .speaking
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
            state = .unavailable(text)
        }
    }

    private func startWebRTCIfReady() {
        guard isPageReady, let token = pendingToken, let webView else { return }
        pendingToken = nil
        guard let tokenData = try? JSONSerialization.data(withJSONObject: token),
              let tokenJSON = String(data: tokenData, encoding: .utf8) else {
            state = .unavailable(RealtimeVoiceError.invalidSessionResponse.localizedDescription)
            return
        }
        webView.evaluateJavaScript("window.naluRealtime.start(\(tokenJSON))") { _, error in
            if let error {
                Task { @MainActor in
                    self.state = .unavailable(error.localizedDescription)
                }
            }
        }
    }

    private static let webRTCPage = #"""
    <!doctype html><html><body><script>
    window.naluRealtime = (() => {
      let pc = null, dc = null, stream = null, audio = null;
      const post = (kind, value) => window.webkit.messageHandlers.naluRealtime.postMessage({kind, value});
      async function start(token) {
        try {
          stop();
          post("status", "connecting");
          pc = new RTCPeerConnection();
          audio = document.createElement("audio");
          audio.autoplay = true;
          document.body.appendChild(audio);
          pc.ontrack = event => { audio.srcObject = event.streams[0]; };
          stream = await navigator.mediaDevices.getUserMedia({audio: true});
          pc.addTrack(stream.getTracks()[0]);
          dc = pc.createDataChannel("oai-events");
          dc.addEventListener("open", () => post("status", "connected"));
          dc.addEventListener("message", event => {
            const value = JSON.parse(event.data);
            if (value.type === "input_audio_buffer.speech_started") post("status", "listening");
            if (value.type === "input_audio_buffer.speech_stopped") post("status", "thinking");
            if (value.type === "response.created") post("status", "thinking");
            if (value.type === "response.output_audio.delta") post("status", "speaking");
            if (value.type === "conversation.item.input_audio_transcription.completed") {
              post("user", value.transcript || "");
            }
            if (value.type === "response.output_audio_transcript.done") {
              post("assistant", value.transcript || "");
              post("status", "listening");
            }
            if (value.type === "error") post("error", value.error?.message || "实时语音发生错误");
          });
          const offer = await pc.createOffer();
          await pc.setLocalDescription(offer);
          const response = await fetch("https://api.openai.com/v1/realtime/calls", {
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
        if (dc) dc.close();
        if (pc) pc.close();
        if (stream) stream.getTracks().forEach(track => track.stop());
        if (audio) audio.remove();
        pc = dc = stream = audio = null;
        if (notify) post("status", "off");
      }
      return {start, stop};
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
