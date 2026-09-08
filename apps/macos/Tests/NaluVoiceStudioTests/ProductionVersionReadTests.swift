import Foundation
import Testing
@testable import NaluVoiceStudio

private final class VersionReadProtocol: URLProtocol, @unchecked Sendable {
    static var data = Data()
    static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct ProductionVersionReadTests {
    @MainActor @Test func historyIsReadOnlyAndRejectsWrongIdentityOrDuplicates() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [VersionReadProtocol.self]
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
                                    session: URLSession(configuration: configuration), accessCheck: { true })
        func run(_ id: String, episode: String = "episode") -> ProductionRun {
            ProductionRun(id: id, projectID: "project", seasonID: "season", episodeID: episode,
                status: "qa_review", dryRun: true, requestedModel: "sd2", estimatedBudgetCredits: nil,
                packagePath: "/unused", error: nil, createdAt: "2026-09-08", updatedAt: "2026-09-08")
        }
        VersionReadProtocol.requests = []
        VersionReadProtocol.data = try JSONEncoder().encode([run("child"), run("parent")])
        let saved = try await runtime.productionVersions(projectID: "project", seasonID: "season", episodeID: "episode")
        #expect(saved.map(\.id) == ["child", "parent"])
        for invalid in [[run("foreign", episode: "another")], [run("same"), run("same")]] {
            VersionReadProtocol.data = try JSONEncoder().encode(invalid)
            var rejected = false
            do { _ = try await runtime.productionVersions(projectID: "project", seasonID: "season", episodeID: "episode") }
            catch { rejected = true }
            #expect(rejected)
        }
        #expect(VersionReadProtocol.requests.count == 3)
        #expect(VersionReadProtocol.requests.allSatisfy {
            $0.httpMethod == "GET" && $0.url?.path == "/v1/episodes/episode/production-runs"
        })
    }
}
