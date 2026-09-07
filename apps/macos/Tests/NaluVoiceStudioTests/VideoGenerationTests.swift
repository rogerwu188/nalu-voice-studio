import Foundation
import Testing
@testable import NaluVoiceStudio

private final class VideoGenerationProtocol: URLProtocol, @unchecked Sendable {
    static var responses: [(Int, Data)] = []
    static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        let next = Self.responses.isEmpty ? (500, Data()) : Self.responses.removeFirst()
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: next.0,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: next.1)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct VideoGenerationTests {
    private let prepSHA = String(repeating: "a", count: 64)
    private let requestSHA = String(repeating: "b", count: 64)
    private func data(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed]) }
    private func reservation() -> [String: Any] {
        ["id": "reserved", "run_id": "run", "event_type": "video_estimate_reserved", "payload": [
            "preparation_id": "prepared", "preparation_sha256": prepSHA, "task_key": "shot", "request_sha256": requestSHA,
            "estimated_credits": 156, "confirmed_run_budget_credits": 1000, "pricing_quote_id": "quote", "guardian_approval": false,
            "published_price_observed": true, "generation_performed": false]]
    }
    private func binding(_ state: String = "submitted") -> [String: Any] {
        ["id": "binding", "run_id": "run", "task_key": "shot", "request_sha256": requestSHA,
         "state": state, "provider_task_id": "fixture-task"]
    }
    private func run(dry: Bool = false) throws -> Data {
        try data(["id": "run", "project_id": "project", "season_id": "season", "episode_id": "episode",
                  "status": "waiting_for_approval", "dry_run": dry, "requested_model": "seedance-2.0-pro",
                  "estimated_budget_credits": 1000, "package_path": "/fixture", "created_at": "fixture", "updated_at": "fixture"])
    }
    private func price() throws -> VideoPriceObservation {
        try JSONDecoder().decode(VideoPriceObservation.self, from: data([
            "id": "quote", "run_id": "run", "event_type": "video_price_observed", "payload": [
                "preparation_id": "prepared", "preparation_sha256": prepSHA, "estimated_credits": 156, "duration_seconds": 6,
                "expires_at": ISO8601DateFormatter().string(from: Date().addingTimeInterval(600)),
                "published_price_observed": true, "provider_charge_cap_guaranteed": false, "generation_performed": false]]))
    }
    @MainActor private func model(key: @escaping () async throws -> String?) throws -> VideoGenerationModel {
        let prepared = try JSONDecoder().decode(FrameProductionEvent.self, from: data([
            "id": "prepared", "run_id": "run", "event_type": "video_task_prepared", "payload": [
                "task_key": "shot", "request_sha256": requestSHA, "preparation_sha256": prepSHA]]))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [VideoGenerationProtocol.self]
        let client = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true })
        return VideoGenerationModel(prepared: prepared, runtime: client, key: key)
    }

    @MainActor @Test func onlyFinalConfirmationReservesAndSubmits() async throws {
        VideoGenerationProtocol.requests = []
        VideoGenerationProtocol.responses = [(200, try data([])), (200, try run()), (200, try data(reservation())),
            (200, try data(NSNull())), (200, try data(binding()))]
        var reads = 0
        let model = try model { reads += 1; return "synthetic-key" }
        await model.load()
        #expect(model.loaded && reads == 0)
        let quote = try price()
        #expect(await model.review(price: quote, guardianApproved: false))
        #expect(VideoGenerationProtocol.requests.map(\.httpMethod) == ["GET", "GET"])
        #expect(model.readback.contains("156"))
        await model.confirm()
        #expect(reads == 1 && model.submission?.state == "submitted")
        #expect(VideoGenerationProtocol.requests.map(\.httpMethod) == ["GET", "GET", "POST", "GET", "POST"])
        await model.confirm()
        #expect(VideoGenerationProtocol.requests.count == 5)
    }

    @MainActor @Test func lostDispatchResponseRecoversReadOnlyAfterRestart() async throws {
        VideoGenerationProtocol.requests = []
        VideoGenerationProtocol.responses = [(200, try data([])), (200, try run()), (200, try data(reservation())),
            (200, try data(NSNull())), (503, Data()), (200, try data([reservation()])), (200, try data(binding("ambiguous_charge")))]
        var reads = 0
        let first = try model { reads += 1; return "synthetic-key" }
        await first.load()
        let quote = try price()
        #expect(await first.review(price: quote, guardianApproved: false))
        await first.confirm()
        #expect(first.reservation != nil && !first.canResume)
        let restarted = try model { reads += 1; return "must-not-be-read" }
        await restarted.load()
        #expect(restarted.submission?.state == "ambiguous_charge")
        #expect(reads == 1 && !restarted.canResume)
        #expect(VideoGenerationProtocol.requests.filter { $0.url?.path.hasSuffix("/submit") == true }.count == 1)
        #expect(VideoGenerationProtocol.requests.suffix(2).allSatisfy { $0.httpMethod == "GET" })
    }

    @MainActor @Test func dryRunAndUnreadableHistoryNeverDispatch() async throws {
        VideoGenerationProtocol.requests = []
        VideoGenerationProtocol.responses = [(409, Data()), (200, try data([])), (200, try run(dry: true))]
        let model = try model { Issue.record("must not read key"); return nil }
        await model.load()
        #expect(!model.loaded)
        await model.confirm()
        await model.load()
        let quote = try price()
        #expect(!(await model.review(price: quote, guardianApproved: false)))
        await model.confirm()
        #expect(VideoGenerationProtocol.requests.allSatisfy { $0.httpMethod == "GET" })
    }
}
