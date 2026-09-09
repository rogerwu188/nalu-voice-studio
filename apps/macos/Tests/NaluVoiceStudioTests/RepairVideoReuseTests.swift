import Foundation
import Testing
@testable import NaluVoiceStudio

private final class RepairReadProtocol: URLProtocol, @unchecked Sendable {
    static var body = Data("null".utf8)
    static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200,
            httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct RepairVideoReuseTests {
    @Test func openingOrdinaryRunDoesNotCreateRepairOrProduction() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [RepairReadProtocol.self]
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true })
        RepairReadProtocol.requests = []
        RepairReadProtocol.body = Data("null".utf8)
        let ordinary = try await runtime.hasRepairSource(runID: "ordinary")
        #expect(!ordinary)
        RepairReadProtocol.body = Data(#"{"source_run_id":"parent"}"#.utf8)
        #expect(try await runtime.hasRepairSource(runID: "child"))
        #expect(RepairReadProtocol.requests.map { $0.httpMethod } == ["GET", "GET"])
        #expect(RepairReadProtocol.requests.map { $0.url!.path } == [
            "/v1/production-runs/ordinary/repair-shot-draft/context",
            "/v1/production-runs/child/repair-shot-draft/context"])
    }
    @Test func restoredDecisionRequiresSourceAndCannotGrantProductionAuthority() throws {
        let sha = String(repeating: "a", count: 64)
        let item = RepairVideoCandidate(shot_index: 0, status: "available_for_review", requires_review: true,
            source_run_id: "parent", source_review_id: "source-review", source_review_sha256: sha,
            materialization_id: "media", video_sha256: sha)
        let valid = RepairVideoDecision(id: "decision", run_id: "child", event_type: "repair_video_reviewed",
            payload: .init(shot_index: 0, candidate: item, plan_id: "plan", plan_sha256: sha,
                decision: "accept", adopted: true, generation_performed: false, paid_approved: false,
                master_accepted: false, review_sha256: sha))
        try valid.validate(runID: "child")
        let candidates = RepairVideoCandidates(run_id: "child", source_run_id: "parent", plan_event_id: "plan",
            plan_sha256: sha, candidates_sha256: sha, items: [item], adopted: false, generation_performed: false)
        var state = try RepairVideoReviewState(candidates: candidates, decisions: [])
        #expect(!state.canAccept(0))
        #expect(throws: (any Error).self) { try state.record(valid) }
        try state.markViewed(0)
        try state.record(valid)
        #expect(state.currentDecision(for: 0)?.id == valid.id)
        let restored = try RepairVideoReviewState(candidates: candidates, decisions: [valid])
        #expect(restored.currentDecision(for: 0)?.id == valid.id)
        #expect(!restored.canAccept(0)) // A saved decision is not a new playback event.
        var changedPlan = candidates
        changedPlan.plan_event_id = "new-plan"
        let revised = try RepairVideoReviewState(candidates: changedPlan, decisions: [valid])
        #expect(revised.currentDecision(for: 0) == nil)
        #expect(revised.previousID(for: 0) == valid.id) // Preserve CAS for replacing the old receipt.
        #expect(throws: (any Error).self) { try state.markViewed(99) }
        var missing = valid
        missing.payload.candidate.video_sha256 = nil
        var selfReference = valid
        selfReference.payload.candidate.source_run_id = "child"
        var paid = valid
        paid.payload.paid_approved = true
        var wrongDecision = valid
        wrongDecision.payload.decision = "reject"
        var emptyPlan = valid
        emptyPlan.payload.plan_id = ""
        for invalid in [missing, selfReference, paid, wrongDecision, emptyPlan] {
            #expect(throws: (any Error).self) { try invalid.validate(runID: "child") }
        }
    }

    @Test func candidatesRejectWrongScopeAndMissingSourceEvidence() throws {
        let hash = String(repeating: "a", count: 64)
        let item = RepairVideoCandidate(shot_index: 0, status: "available_for_review", requires_review: true,
            source_run_id: "parent", source_review_id: "review", source_review_sha256: hash,
            materialization_id: "media", video_sha256: hash)
        let valid = RepairVideoCandidates(run_id: "child", source_run_id: "parent", plan_event_id: "plan",
            plan_sha256: hash, candidates_sha256: hash, items: [item], adopted: false, generation_performed: false)
        try valid.validate(runID: "child")
        var malformed = valid
        malformed.items[0].video_sha256 = nil
        var reordered = valid
        reordered.items[0].shot_index = 1
        var unexpected = valid
        unexpected.generation_performed = true
        for invalid in [malformed, reordered, unexpected] {
            #expect(throws: (any Error).self) { try invalid.validate(runID: "child") }
        }
        #expect(throws: (any Error).self) { try valid.validate(runID: "another") }
    }
}
