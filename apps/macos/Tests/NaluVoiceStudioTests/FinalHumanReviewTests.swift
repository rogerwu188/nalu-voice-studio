import Foundation
import Testing
@testable import NaluVoiceStudio

private final class FinalReviewProtocol: URLProtocol, @unchecked Sendable {
    static var body = Data()
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

@Suite(.serialized) struct FinalHumanReviewTests {
    @Test func decodesServerResponseWithoutSubmissionOnlyFields() async throws {
        let payload: [String: Any] = [
            "schema_version": "nalu.final-qa-evidence/v1", "run_id": "run_test",
            "master_sha256": String(repeating: "a", count: 64),
            "original_resolution_reviewed": true, "picture_passed": false,
            "audio_sync_passed": true, "captions_passed": true,
            "continuity_passed": true, "safety_passed": true,
            "reviewed_by": "test-reviewer", "review_channel": "human_original_resolution",
            "reviewed_at": "2026-09-16T00:00:00Z", "notes": "Synthetic contract fixture"
        ]
        let bytes = try JSONSerialization.data(withJSONObject: payload)
        let result = try JSONDecoder().decode(FinalHumanReviewResult.self, from: bytes)
        #expect(result.runID == "run_test")
        #expect(result.picturePassed == false)
        #expect(result.originalResolutionReviewed)
        try result.validate(runID: "run_test")
        #expect(throws: (any Error).self) { try result.validate(runID: "another-run") }

        var submission = payload
        submission["idempotency_key"] = "stable-review-key"
        submission["output_seal_sha256"] = String(repeating: "b", count: 64)
        let draft = try JSONDecoder().decode(FinalHumanReviewDraft.self,
            from: JSONSerialization.data(withJSONObject: submission))
        try result.validate(runID: "run_test", submitted: draft)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = FinalHumanReviewStore(directory: directory)
        #expect(try store.save(draft).pending == draft)
        #expect(try store.save(draft).pending == draft)
        let reopened = FinalHumanReviewStore(directory: directory)
        var laterSubmission = submission
        laterSubmission["reviewed_at"] = "2026-09-19T12:00:00Z"
        let later = try JSONDecoder().decode(FinalHumanReviewDraft.self,
            from: JSONSerialization.data(withJSONObject: laterSubmission))
        #expect(try reopened.requestForRetry(later) == draft)
        laterSubmission["picture_passed"] = true
        let changedDecision = try JSONDecoder().decode(FinalHumanReviewDraft.self,
            from: JSONSerialization.data(withJSONObject: laterSubmission))
        #expect(throws: (any Error).self) { try reopened.requestForRetry(changedDecision) }
        let loaded = try reopened.load(runID: draft.runID, masterSHA256: draft.masterSHA256,
                                       outputSealSHA256: draft.outputSealSHA256)
        #expect(loaded?.pending == draft)
        #expect(loaded?.confirmed == nil)
        var state = FinalHumanReviewState()
        #expect(state.confirmed == nil)
        #expect(try state.prepare(draft) == draft)
        #expect(try state.prepare(draft) == draft)
        var alteredSubmission = submission
        alteredSubmission["idempotency_key"] = "new-key"
        let altered = try JSONDecoder().decode(FinalHumanReviewDraft.self,
            from: JSONSerialization.data(withJSONObject: alteredSubmission))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [FinalReviewProtocol.self]
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true })
        FinalReviewProtocol.body = bytes
        FinalReviewProtocol.requests = []
        let response = try await runtime.submitFinalHumanReview(runID: draft.runID, draft: draft, store: store)
        #expect(response == result)
        let recovery = try await runtime.recoverFinalHumanReview(runID: draft.runID,
            masterSHA256: draft.masterSHA256, outputSealSHA256: draft.outputSealSHA256, store: reopened)
        #expect(recovery == result)
        #expect(FinalReviewProtocol.requests.map { $0.httpMethod } == ["POST", "GET"])
        do {
            _ = try await runtime.submitFinalHumanReview(runID: draft.runID, draft: altered, store: reopened)
            Issue.record("conflicting local request was submitted")
        } catch {}
        #expect(FinalReviewProtocol.requests.count == 2)
        #expect(throws: (any Error).self) { try reopened.save(altered) }
        #expect(throws: (any Error).self) { try state.prepare(altered) }
        #expect(state.pending == draft)
        guard let checkpoint = try state.pendingCheckpoint() else {
            Issue.record("pending review checkpoint was unexpectedly empty")
            return
        }
        var recovered = FinalHumanReviewState()
        try recovered.restorePending(checkpoint, runID: draft.runID,
            masterSHA256: draft.masterSHA256, outputSealSHA256: draft.outputSealSHA256)
        #expect(recovered.pending == draft)
        #expect(recovered.confirmed == nil)
        #expect(throws: (any Error).self) {
            try recovered.restorePending(checkpoint, runID: "other",
                masterSHA256: draft.masterSHA256, outputSealSHA256: draft.outputSealSHA256)
        }
        #expect(recovered.pending == draft)
        #expect(throws: (any Error).self) {
            try recovered.restorePending(Data("invalid".utf8), runID: draft.runID,
                masterSHA256: draft.masterSHA256, outputSealSHA256: draft.outputSealSHA256)
        }
        #expect(recovered.pending == draft)
        try state.confirm(result)
        #expect(try state.pendingCheckpoint() == nil)
        #expect(state.pending == nil)
        #expect(state.confirmed?.picturePassed == false)
        #expect(throws: (any Error).self) { try state.prepare(draft) }

        for field in ["master_sha256", "picture_passed", "reviewed_by", "reviewed_at", "notes"] {
            var changed = payload
            if field == "picture_passed" { changed[field] = true }
            else { changed[field] = "changed" }
            let mismatch = try JSONDecoder().decode(FinalHumanReviewResult.self,
                from: JSONSerialization.data(withJSONObject: changed))
            #expect(throws: (any Error).self) {
                try mismatch.validate(runID: "run_test", submitted: draft)
            }
        }
    }
}
