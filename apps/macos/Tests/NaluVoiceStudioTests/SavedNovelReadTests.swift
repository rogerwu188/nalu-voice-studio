import Foundation
import Testing
@testable import NaluVoiceStudio

private final class SavedNovelReadProtocol: URLProtocol, @unchecked Sendable {
    static var body = "null"
    static var status = 200
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

@Suite(.serialized) struct SavedNovelReadTests {
    @MainActor @Test func savedSourceReadDistinguishesAbsenceFromFailureWithoutImporting() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SavedNovelReadProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
                                    session: session, accessCheck: { true })
        SavedNovelReadProtocol.requests = []
        SavedNovelReadProtocol.status = 200
        SavedNovelReadProtocol.body = "null"
        let missing = try await runtime.savedNovelImport(projectID: "project")
        #expect(missing == nil)
        SavedNovelReadProtocol.body = #"{"status":"complete","source_url":"https://example.com/book","completed_chapters":1,"chapters":[{"url":"https://example.com/1","title":"第一章","status":"complete"}]}"#
        let saved = try await runtime.savedNovelImport(projectID: "project")
        #expect(saved?.completed_chapters == 1)
        #expect(saved?.chapters.first?.title == "第一章")
        for (status, body) in [(503, #"{"detail":"unavailable"}"#), (200, "{broken")] {
            SavedNovelReadProtocol.status = status
            SavedNovelReadProtocol.body = body
            var rejected = false
            do { _ = try await runtime.savedNovelImport(projectID: "project") }
            catch { rejected = true }
            #expect(rejected)
        }
        #expect(SavedNovelReadProtocol.requests.count == 4)
        #expect(SavedNovelReadProtocol.requests.allSatisfy {
            $0.httpMethod == "GET" && $0.url?.path == "/v1/projects/project/novel-import"
        })
    }
}
