import Foundation
import Testing
@testable import NaluVoiceStudio

private final class PreparationProtocol: URLProtocol, @unchecked Sendable {
    static var requests: [URLRequest] = []
    static var bodies: [Data] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        var sent = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open()
            defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 1024)
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                guard count > 0 else { break }
                sent.append(contentsOf: buffer.prefix(count))
            }
        }
        Self.bodies.append(sent)
        let body = """
        {"id":"run-fixture","project_id":"project","season_id":"season","episode_id":"episode",
        "status":"preflight_passed","dry_run":true,"requested_model":"seedance-2.0-pro",
        "estimated_budget_credits":null,"package_path":"fixture.json","error":null,
        "created_at":"fixture","updated_at":"fixture"}
        """
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 201,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized)
struct ProductionPreparationTests {
    @Test func preparationReusesRevisionIdentityAndCannotApprovePayment() async throws {
        PreparationProtocol.requests = []
        PreparationProtocol.bodies = []
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [PreparationProtocol.self]
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true })
        for _ in 0..<2 {
            let result = try await runtime.prepareEpisodeProduction(episodeID: "episode", approvedRevision: 2)
            #expect(result.dryRun)
        }
        #expect(PreparationProtocol.requests.count == 2)
        for request in PreparationProtocol.requests {
            #expect(request.url?.path == "/v1/episodes/episode/production-runs")
            #expect(request.value(forHTTPHeaderField: "Idempotency-Key") == "native-preflight-episode-r2")
            #expect(request.httpMethod == "POST")
        }
        for data in PreparationProtocol.bodies {
            let body = try JSONSerialization.jsonObject(with: data) as! [String: Bool]
            #expect(body == ["dry_run": true, "paid_generation_approved": false])
        }
    }

    @Test func episodeDecodesApprovedRevision() throws {
        let data = Data("""
        {"id":"episode","season_id":"season","title":"One","episode_number":1,
        "logline":"","outline":{},"target_seconds":60,"status":"script_approved","approved_script_revision":2}
        """.utf8)
        let episode = try JSONDecoder().decode(NaluEpisode.self, from: data)
        #expect(episode.approvedScriptRevision == 2)
    }
}
