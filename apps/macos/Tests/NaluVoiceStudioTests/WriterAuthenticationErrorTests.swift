import Foundation
import Testing
@testable import NaluVoiceStudio

private final class WriterAuthenticationErrorProtocol: URLProtocol, @unchecked Sendable {
    static var status = 502
    static var body = #"{"detail":"writer_http_401"}"#
    static var requests: [URLRequest] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(Self.body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@Suite(.serialized)
struct WriterAuthenticationErrorTests {
    @MainActor @Test func knownUpstream401GetsActionableMessageWithoutRetry() async throws {
        WriterAuthenticationErrorProtocol.status = 502
        WriterAuthenticationErrorProtocol.body = #"{"detail":"writer_http_401"}"#
        WriterAuthenticationErrorProtocol.requests = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [WriterAuthenticationErrorProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: session, accessCheck: { true })

        do {
            _ = try await runtime.generateStoryAnswer(projectID: "project", turnID: "turn",
                revision: 2, model: "gpt-5.4-mini", apiKey: "test-only")
            Issue.record("Upstream authentication rejection must fail closed")
        } catch {
            #expect(error.localizedDescription.contains("已保存的账号凭据（401）"))
            #expect(error.localizedDescription.contains("无需重新输入已保存的密钥"))
            #expect(!error.localizedDescription.contains("test-only"))
            #expect(InteractiveWriterFailureMessage.userMessage(for: error) == error.localizedDescription)
        }
        #expect(WriterAuthenticationErrorProtocol.requests.count == 1)
        #expect(WriterAuthenticationErrorProtocol.requests.first?.httpMethod == "POST")
        #expect(WriterAuthenticationErrorProtocol.requests.first?.url?.path ==
                "/v1/projects/project/interactive-story/turns/turn/generate")
    }

    @MainActor @Test func otherRuntimeFailuresDoNotMasqueradeAsAuthenticationErrors() async throws {
        WriterAuthenticationErrorProtocol.status = 502
        WriterAuthenticationErrorProtocol.body = #"{"detail":"writer_transport_failed"}"#
        WriterAuthenticationErrorProtocol.requests = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [WriterAuthenticationErrorProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: session, accessCheck: { true })

        do {
            _ = try await runtime.generateStoryAnswer(projectID: "project", turnID: "turn",
                revision: 2, model: "gpt-5.4-mini", apiKey: "test-only")
            Issue.record("Unexpected upstream failure must remain an error")
        } catch {
            #expect(!error.localizedDescription.contains("账号凭据（401）"))
            #expect(InteractiveWriterFailureMessage.userMessage(for: error) ==
                    "这次编剧请求没有完成，已有内容没有清空。我没有自动重复请求。您可以继续补充故事。")
        }
        #expect(WriterAuthenticationErrorProtocol.requests.count == 1)
    }
}
