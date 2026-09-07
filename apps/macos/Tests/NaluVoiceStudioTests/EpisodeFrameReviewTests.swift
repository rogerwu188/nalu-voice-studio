import CryptoKit
import Foundation
import Testing
@testable import NaluVoiceStudio

private final class FrameReviewProtocol: URLProtocol, @unchecked Sendable {
    static var requests: [URLRequest] = []
    static var events = Data()
    static var image = Data("synthetic-image-bytes".utf8)
    static var review = Data()
    static var fail = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        let path = request.url!.path
        let body = path.hasSuffix("/events") ? Self.events : path.hasSuffix("/content") ? Self.image : Self.review
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.fail ? 409 : 200,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct EpisodeFrameReviewTests {
    private func event(_ id: String, _ type: String, _ payload: [String: Any]) -> [String: Any] {
        ["id": id, "run_id": "run-one", "event_type": type, "payload": payload]
    }
    private func runtime() -> RuntimeClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [FrameReviewProtocol.self]
        return RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true })
    }
    private func setup() throws {
        FrameReviewProtocol.requests = []; FrameReviewProtocol.fail = false
        FrameReviewProtocol.image = Data("synthetic-image-bytes".utf8)
        let sha = SHA256.hash(data: FrameReviewProtocol.image).map { String(format: "%02x", $0) }.joined()
        FrameReviewProtocol.events = try JSONSerialization.data(withJSONObject: [
            event("unrelated", "other_event", ["image": "unrelated payload shape"]),
            event("prep", "image_task_prepared", ["approved_plan_event_id": "plan", "approved_shot_index": 0,
                "request_sha256": "request", "image_task_key": "E01-U01-entry"]),
            event("material", "image_result_materialized", ["request_sha256": "request", "task_key": "E01-U01-entry",
                "materialization_sha256": String(repeating: "a", count: 64), "image": ["sha256": sha]])])
        FrameReviewProtocol.review = try JSONSerialization.data(withJSONObject:
            event("review", "image_frame_reviewed", ["decision": "accept", "materialization_id": "material", "task_key": "E01-U01-entry"]))
    }
    @MainActor @Test func exactImageReviewDoesNotUseProviderCredentials() async throws {
        try setup()
        let model = EpisodeFrameReviewModel(runID: "run-one", planID: "plan", shotIndex: 0, runtime: runtime())
        await model.load()
        #expect(model.canReview)
        #expect(model.imageData == FrameReviewProtocol.image)
        await model.review(accept: true)
        #expect(model.latestReview?.id == "review")
        #expect(FrameReviewProtocol.requests.last?.url?.path == "/v1/production-runs/run-one/image-results/material/review")
        #expect(FrameReviewProtocol.requests.allSatisfy { $0.value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil })
        FrameReviewProtocol.fail = true
        await model.review(accept: false)
        #expect(!model.canReview)
        #expect(model.imageData == nil)
        #expect(model.latestReview?.payload.decision == "accept")
    }
    @MainActor @Test func wrongShotAndChangedBytesCannotBeConfirmed() async throws {
        try setup()
        let wrong = EpisodeFrameReviewModel(runID: "run-one", planID: "plan", shotIndex: 1, runtime: runtime())
        await wrong.load()
        #expect(!wrong.canReview)
        #expect(FrameReviewProtocol.requests.count == 1)
        let model = EpisodeFrameReviewModel(runID: "run-one", planID: "plan", shotIndex: 0, runtime: runtime())
        FrameReviewProtocol.image = Data("changed".utf8)
        await model.load()
        #expect(!model.canReview)
        #expect(model.notice != nil)
        #expect(FrameReviewProtocol.requests.allSatisfy { $0.httpMethod == "GET" })
    }
}
