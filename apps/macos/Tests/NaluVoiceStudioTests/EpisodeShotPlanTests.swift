import CryptoKit
import Foundation
import Testing
@testable import NaluVoiceStudio

private final class ShotReviewProtocol: URLProtocol, @unchecked Sendable {
    static var requests: [URLRequest] = []
    static var response = Data()
    static var status = 200
    static var queued: [(Int, Data)] = []
    static var bodies: [Data] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        var body = request.httpBody ?? Data()
        if body.isEmpty, let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            while true {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count <= 0 { break }
                body.append(contentsOf: buffer.prefix(count))
            }
        }
        Self.bodies.append(body)
        let next = Self.queued.isEmpty ? (Self.status, Self.response) : Self.queued.removeFirst()
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: next.0,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: next.1)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized)
struct EpisodeShotPlanTests {
    @Test func picturePreviewRejectsWrongEditContentAndMasterClaims() throws {
        // Header/content validator fixture only, not a playable-video QA claim.
        let bytes = Data([0, 0, 0, 12]) + Data("ftypisom".utf8)
        let sha = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        let editSHA = String(repeating: "a", count: 64)
        let headers = ["Content-Type": "video/mp4", "X-Nalu-Edit-SHA256": editSHA,
            "X-Nalu-Preview-Receipt-ID": "evt_preview",
            "X-Nalu-Preview-SHA256": sha, "X-Nalu-Preview-Audio": "none", "X-Nalu-Master-Accepted": "false"]
        func response(_ values: [String: String], status: Int = 200) -> HTTPURLResponse {
            HTTPURLResponse(url: URL(string: "http://127.0.0.1/preview")!, statusCode: status,
                httpVersion: nil, headerFields: values)!
        }
        try EpisodePictureValidation.validate(bytes: bytes, response: response(headers), editSHA: editSHA)
        for field in headers.keys {
            var wrong = headers; wrong[field] = ""
            #expect(throws: (any Error).self) {
                try EpisodePictureValidation.validate(bytes: bytes, response: response(wrong), editSHA: editSHA)
            }
        }
        #expect(throws: (any Error).self) {
            try EpisodePictureValidation.validate(bytes: bytes, response: response(headers, status: 409), editSHA: editSHA)
        }
        #expect(throws: (any Error).self) {
            try EpisodePictureValidation.validate(bytes: Data(), response: response(headers), editSHA: editSHA)
        }
        #expect(throws: (any Error).self) {
            try EpisodePictureValidation.validate(bytes: bytes + Data([1]), response: response(headers), editSHA: editSHA)
        }
    }

    @MainActor @Test func episodeEditingPreservesCutsOnFailedSaveAndRejectsForeignContext() async throws {
        func response(edited: Bool, plan: String = "plan") throws -> Data {
            var payload: [String: Any] = ["plan_id": plan, "plan_sha256": "plan-sha",
                "items": [["shot_index": 0, "task_key": "shot", "source_duration_seconds": 8]],
                "shots": [["shot_id": "shot", "source_in_seconds": edited ? 0.5 : 0, "source_out_seconds": 8]],
                "generation_performed": false, "master_accepted": false]
            if edited {
                payload["source_input_sha256"] = String(repeating: "a", count: 64)
                payload["edit_sha256"] = String(repeating: "b", count: 64)
                payload["edit_approved"] = false; payload["edited_duration_seconds"] = 7.5
            } else { payload["input_sha256"] = String(repeating: "a", count: 64) }
            return try JSONSerialization.data(withJSONObject: ["id": edited ? "edit" : "inputs", "run_id": "run",
                "event_type": edited ? "postproduction_edit_drafted" : "postproduction_shot_inputs_staged", "payload": payload])
        }
        ShotReviewProtocol.requests = []; ShotReviewProtocol.bodies = []
        ShotReviewProtocol.queued = [(200, try response(edited: false)), (200, Data("[]".utf8)), (503, Data()),
            (200, try response(edited: false)), (200, try response(edited: true)), (503, Data()),
            (200, try response(edited: false, plan: "foreign"))]
        let model = EpisodeEditingModel(runID: "run", planID: "plan", planSHA: "plan-sha", runtime: runtime())
        #expect(ShotReviewProtocol.requests.isEmpty)
        await model.load()
        #expect(!model.canSave) // Never manufacture a cut to bypass whole-source QA.
        model.trim(index: 0, beginning: true)
        #expect(model.canSave)
        #expect(ShotReviewProtocol.requests.count == 2) // Staging + read-only recovery; local editing is not submission.
        await model.save()
        #expect(model.saved == nil && model.cuts[0].source_in_seconds == 0.5)
        await model.load()
        #expect(model.cuts[0].source_in_seconds == 0.5) // Reload preserves unsaved edits.
        await model.save()
        #expect(model.saved?.id == "edit")
        #expect(model.notice.contains("剪辑已保存") && model.notice.contains("暂未同步"))
        let first = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies[2]) as! NSDictionary
        let retry = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies[4]) as! NSDictionary
        #expect(first == retry)
        await model.load()
        #expect(model.inputs?.payload.plan_id == "plan" && model.cuts[0].source_in_seconds == 0.5)
        #expect(ShotReviewProtocol.requests.allSatisfy { $0.value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil })
        model.reset(index: 0)
        #expect(!model.canSave && model.saved == nil)
        let savedEdit = try JSONSerialization.jsonObject(with: response(edited: true))
        let history = try JSONSerialization.data(withJSONObject: [
            ["event_type": "unrelated_event", "payload": ["not": "an edit"]], savedEdit])
        ShotReviewProtocol.queued = [(200, try response(edited: false)), (200, history)]
        let restarted = EpisodeEditingModel(runID: "run", planID: "plan", planSHA: "plan-sha", runtime: runtime())
        await restarted.load()
        #expect(restarted.saved?.id == "edit" && restarted.cuts.first?.source_in_seconds == 0.5)
        #expect(ShotReviewProtocol.requests.last?.httpMethod == "GET")
        #expect(ShotReviewProtocol.requests.last?.url?.path.hasSuffix("production-runs/run/events") == true)
        #expect(ShotReviewProtocol.requests.filter { $0.url?.path.hasSuffix("episode-edit-drafts") == true }.count == 2)
        // A stale or malformed saved draft must not replace missing/local edits.
        for field in ["source_input_sha256", "edited_duration_seconds"] {
            var broken = savedEdit as! [String: Any]
            var payload = broken["payload"] as! [String: Any]
            if field == "source_input_sha256" { payload[field] = "stale" }
            else { payload[field] = 99 }
            broken["payload"] = payload
            ShotReviewProtocol.queued = [(200, try response(edited: false)),
                (200, try JSONSerialization.data(withJSONObject: [broken]))]
            let invalid = EpisodeEditingModel(runID: "run", planID: "plan", planSHA: "plan-sha", runtime: runtime())
            await invalid.load()
            #expect(invalid.saved == nil && invalid.inputs == nil && invalid.cuts.isEmpty)
        }
        func soundResponse(editID: String) throws -> Data {
            try JSONSerialization.data(withJSONObject: ["run_id": "run", "event_type": "episode_sound_plan_drafted",
                "payload": ["edit_id": editID, "edit_sha256": String(repeating: "b", count: 64),
                    "plan_id": "plan", "plan_sha256": "plan-sha", "duration_seconds": 7.5,
                    "caption_timing_basis": "DRAFT_EDIT_WINDOWS_NOT_SPEECH_ALIGNMENT",
                    "audio_generated": false, "captions_approved": false, "speech_alignment_verified": false,
                    "edit_approved": false, "generation_performed": false, "master_accepted": false]])
        }
        ShotReviewProtocol.queued = [(200, try response(edited: true)), (200, try soundResponse(editID: "edit"))]
        await restarted.save()
        #expect(restarted.notice.contains("已按新时长整理"))
        let soundRequest = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies.last!) as! [String: Any]
        #expect(soundRequest["edit_id"] as? String == "edit")
        #expect(soundRequest["expected_edit_sha256"] as? String == String(repeating: "b", count: 64))
        ShotReviewProtocol.queued = [(200, try response(edited: true)), (200, try soundResponse(editID: "foreign"))]
        await restarted.save()
        #expect(restarted.saved?.id == "edit" && restarted.notice.contains("暂未同步"))
        let edit = try #require(restarted.saved)
        let picture = EpisodePicture(fileURL: URL(fileURLWithPath: "/tmp/synthetic-preview-not-played.mp4"),
            receiptID: "preview", sha256: String(repeating: "c", count: 64), editSHA: String(repeating: "b", count: 64))
        func reviewResponse(previewID: String = "preview") throws -> Data {
            try JSONSerialization.data(withJSONObject: ["id": "review", "run_id": "run", "event_type": "postproduction_edit_reviewed",
                "payload": ["edit_id": "edit", "edit_sha256": picture.editSHA, "preview_id": previewID,
                    "preview_sha256": picture.sha256, "decision": "accept", "reviewed_by": "synthetic-qa",
                    "confirmation": "合成确认，非实际用户验收", "edit_approved": true, "duration_confirmed_seconds": 7.5,
                    "viewing_evidence": "USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY", "audio_approved": false,
                    "captions_approved": false, "master_accepted": false, "generation_performed": false]])
        }
        let reviewHistory = try JSONSerialization.data(withJSONObject: [JSONSerialization.jsonObject(with: reviewResponse())])
        ShotReviewProtocol.queued = [(200, Data("[]".utf8)), (200, try reviewResponse()), (200, reviewHistory),
            (200, try reviewResponse(previewID: "foreign"))]
        let reviewClient = runtime()
        #expect(try await reviewClient.latestEpisodeEditReview(edit: edit) == nil)
        let draft = EpisodeEditReviewDraft(expected_edit_sha256: picture.editSHA, preview_id: picture.receiptID,
            expected_preview_sha256: picture.sha256, expected_review_id: nil, decision: .accept,
            reviewed_by: "synthetic-qa", confirmation: "合成确认，非实际用户验收")
        let accepted = try await reviewClient.reviewEpisodeEdit(edit: edit, picture: picture, draft: draft)
        #expect(accepted.payload.edit_approved)
        let recovered = try await reviewClient.latestEpisodeEditReview(edit: edit)
        #expect(recovered?.id == accepted.id)
        do {
            _ = try await reviewClient.reviewEpisodeEdit(edit: edit, picture: picture, draft: draft)
            Issue.record("foreign preview must not become an accepted edit")
        } catch {}
        let sentReview = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies.last!) as! [String: Any]
        #expect(sentReview["preview_id"] as? String == picture.receiptID)
        #expect(sentReview["expected_preview_sha256"] as? String == picture.sha256)
        #expect(ShotReviewProtocol.requests.last?.url?.path.hasSuffix("episode-edit-drafts/edit/reviews") == true)
        #expect(ShotReviewProtocol.requests.last?.value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil)
        ShotReviewProtocol.queued = [(200, Data("[]".utf8)), (503, Data()), (200, Data("[]".utf8))]
        let reviewModel = EpisodeEditReviewModel(edit: edit, picture: picture, runtime: runtime())
        #expect(!reviewModel.begin(.accept))
        await reviewModel.load()
        let requestCount = ShotReviewProtocol.requests.count
        #expect(reviewModel.begin(.accept))
        #expect(reviewModel.readback.contains("不会自动发行"))
        #expect(ShotReviewProtocol.requests.count == requestCount)
        let pending = try #require(reviewModel.pending)
        await reviewModel.confirm()
        #expect(reviewModel.uncertain && reviewModel.pending != nil)
        reviewModel.cancelUnsubmitted()
        #expect(reviewModel.pending != nil && !reviewModel.begin(.reject))
        await reviewModel.load()
        #expect(reviewModel.uncertain && reviewModel.pending != nil)
        var recorded = try JSONSerialization.jsonObject(with: reviewResponse()) as! [String: Any]
        var recordedPayload = recorded["payload"] as! [String: Any]
        recordedPayload["reviewed_by"] = pending.reviewed_by
        recordedPayload["confirmation"] = pending.confirmation
        recorded["payload"] = recordedPayload
        ShotReviewProtocol.queued = [(200, try JSONSerialization.data(withJSONObject: recorded)), (503, Data())]
        await reviewModel.confirm()
        #expect(!reviewModel.uncertain && reviewModel.pending == nil && reviewModel.latest?.payload.edit_approved == true)
        #expect(reviewModel.soundPreparationPending && reviewModel.notice.contains("不需要重新确认"))
        let resent = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies[ShotReviewProtocol.bodies.count - 2]) as! [String: Any]
        #expect(resent["confirmation"] as? String == pending.confirmation)
        #expect(resent["expected_review_id"] == nil)
        var soundReceipt = try JSONSerialization.jsonObject(with: soundResponse(editID: "edit")) as! [String: Any]
        var approvedSound = soundReceipt["payload"] as! [String: Any]
        approvedSound["edit_approved"] = true
        approvedSound["edit_review_id"] = "review"
        approvedSound["caption_timing_basis"] = "APPROVED_EDIT_WINDOWS_NOT_SPEECH_ALIGNMENT"
        soundReceipt["payload"] = approvedSound
        ShotReviewProtocol.queued = [(200, try JSONSerialization.data(withJSONObject: soundReceipt))]
        let beforeSoundRetry = ShotReviewProtocol.requests.count
        await reviewModel.retrySoundPreparation()
        #expect(!reviewModel.soundPreparationPending && reviewModel.latest?.id == "review")
        #expect(ShotReviewProtocol.requests.count == beforeSoundRetry + 1)
        #expect(ShotReviewProtocol.requests.last?.url?.path.hasSuffix("sound-plan-drafts") == true)
        let approvedRequest = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies.last!) as! [String: Any]
        #expect(approvedRequest["expected_edit_review_id"] as? String == "review")
        let afterConfirmed = ShotReviewProtocol.requests.count
        #expect(reviewModel.begin(.reject))
        #expect(reviewModel.readback.contains("不会自动付费重做"))
        reviewModel.cancelUnsubmitted()
        #expect(reviewModel.pending == nil && !reviewModel.uncertain)
        #expect(ShotReviewProtocol.requests.count == afterConfirmed)
        #expect(reviewModel.latest?.payload.edit_approved == true)
        let restoredReview = EpisodeEditReviewModel(edit: edit, picture: picture, runtime: runtime())
        #expect(!restoredReview.canPrepareSound)
        let restoredHistory = try JSONSerialization.data(withJSONObject: [recorded])
        ShotReviewProtocol.queued = [(200, restoredHistory)]
        let beforeRecovery = ShotReviewProtocol.requests.count
        await restoredReview.load()
        #expect(restoredReview.canPrepareSound)
        #expect(ShotReviewProtocol.requests.count == beforeRecovery + 1)
        #expect(ShotReviewProtocol.requests.last?.httpMethod == "GET")
        ShotReviewProtocol.queued = [(200, try JSONSerialization.data(withJSONObject: soundReceipt))]
        await restoredReview.retrySoundPreparation()
        #expect(restoredReview.latest?.id == "review" && !restoredReview.soundPreparationPending)
        #expect(ShotReviewProtocol.requests.last?.url?.path.hasSuffix("sound-plan-drafts") == true)
        ShotReviewProtocol.queued = [(503, Data())]
        await restoredReview.load()
        #expect(!restoredReview.canPrepareSound)
        let afterFailedRecovery = ShotReviewProtocol.requests.count
        await restoredReview.retrySoundPreparation()
        #expect(ShotReviewProtocol.requests.count == afterFailedRecovery)
    }

    @MainActor @Test func continuousPreparationCarriesPlanAndRejectsForeignTailResponse() async throws {
        func response(index: Int = 1) throws -> Data {
            try JSONSerialization.data(withJSONObject: ["id": "prepared", "run_id": "run", "event_type": "video_task_prepared",
                "payload": ["approved_plan_event_id": "plan", "approved_plan_sha256": "plan-sha", "approved_shot_index": index,
                    "approved_tail_id": "tail", "approved_tail_sha256": String(repeating: "a", count: 64),
                    "generation_performed": false, "paid_approved": false]])
        }
        ShotReviewProtocol.requests = []; ShotReviewProtocol.bodies = []
        ShotReviewProtocol.queued = [(200, try response()), (200, try response(index: 2))]
        let client = runtime()
        let prepared = try await client.prepareContinuousVideo(runID: "run", planID: "plan", planSHA: "plan-sha", shotIndex: 1)
        #expect(prepared.payload.approved_tail_id == "tail")
        do { _ = try await client.prepareContinuousVideo(runID: "run", planID: "plan", planSHA: "plan-sha", shotIndex: 1)
            Issue.record("wrong shot must not become actionable") } catch {}
        #expect(ShotReviewProtocol.requests.allSatisfy { $0.value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil })
        #expect(ShotReviewProtocol.requests[0].url?.path.hasSuffix("shot-plans/plan/continuation-preparations") == true)
        let body = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies[0]) as! [String: Any]
        #expect(body["expected_plan_sha256"] as? String == "plan-sha")
        #expect(body["shot_index"] as? Int == 1)
        #expect(body["approved_tail_id"] == nil) // Runtime resolves it, not the elder.
    }

    @MainActor @Test func videoDecisionRecoveryAndSubmissionPreserveExactCandidate() async throws {
        let binding = VideoSubmissionObservation(id: "binding", run_id: "run", task_key: "shot",
            request_sha256: "request", state: "submitted", provider_task_id: "task")
        let candidateData = try JSONSerialization.data(withJSONObject: ["id": "candidate", "run_id": "run", "event_type": "video_result_materialized",
            "payload": ["observation_id": "obs", "observation_sha256": "obs-sha", "binding_id": "binding", "result_index": 0,
                "task_key": "shot", "request_sha256": "request", "materialization_sha256": "materialization",
                "video": ["sha256": "video", "byte_size": 128], "video_downloaded": true, "generation_performed": false,
                "billing_verified": false, "visual_semantics_verified": false, "master_accepted": false]])
        let candidate = try JSONDecoder().decode(VideoCandidate.self, from: candidateData)
        func receipt(candidateID: String = "candidate", accepted: Bool = true) -> [String: Any] {
            ["id": "review", "run_id": "run", "event_type": "video_shot_reviewed", "payload": [
                "task_key": "shot", "materialization_id": candidateID, "materialization_sha256": "materialization",
                "video_sha256": "video", "preparation_id": "prep", "preparation_sha256": "prep-sha", "request_sha256": "request",
                "binding_id": "binding", "decision": "accept", "reviewed_by": "user", "confirmation": "采用这个镜头",
                "user_approved": accepted, "visual_semantics_verified": false, "audio_verified": false,
                "billing_verified": false, "master_accepted": false, "generation_performed": false]]
        }
        let draft = VideoReviewDraft(preparation_id: "prep", expected_materialization_sha256: "materialization",
            expected_review_event_id: "previous", decision: .accept, reviewed_by: "user", confirmation: "采用这个镜头")
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.bodies = []
        ShotReviewProtocol.queued = [(200, try JSONSerialization.data(withJSONObject: [receipt()])),
            (200, try JSONSerialization.data(withJSONObject: receipt())),
            (200, try JSONSerialization.data(withJSONObject: receipt(candidateID: "foreign"))),
            (200, try JSONSerialization.data(withJSONObject: [receipt(accepted: false)]))]
        let client = runtime()
        let previous = try await client.latestVideoReview(binding)
        #expect(previous?.id == "review")
        let saved = try await client.reviewVideo(candidate, binding: binding, draft: draft)
        #expect(saved.payload.user_approved)
        do { _ = try await client.reviewVideo(candidate, binding: binding, draft: draft); Issue.record("foreign candidate") } catch {}
        do { _ = try await client.latestVideoReview(binding); Issue.record("inconsistent decision") } catch {}
        #expect(ShotReviewProtocol.requests.map(\.httpMethod) == ["GET", "POST", "POST", "GET"])
        #expect(ShotReviewProtocol.requests[1].url?.path.hasSuffix("video-results/candidate/reviews") == true)
        #expect(ShotReviewProtocol.requests.allSatisfy { $0.value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil })
        let body = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies[1]) as! [String: Any]
        #expect(body["expected_review_event_id"] as? String == "previous")
        let prepared = try JSONDecoder().decode(FrameProductionEvent.self, from: JSONSerialization.data(withJSONObject: [
            "id": "prep", "run_id": "run", "event_type": "video_task_prepared",
            "payload": ["task_key": "shot", "request_sha256": "request", "preparation_sha256": "prep-sha"]]))
        var modelReceipt = receipt()
        var payload = modelReceipt["payload"] as! [String: Any]
        payload["reviewed_by"] = "nalu-native-user"
        modelReceipt["payload"] = payload
        ShotReviewProtocol.requests = []; ShotReviewProtocol.bodies = []
        ShotReviewProtocol.queued = [(200, Data("[]".utf8)), (503, Data()),
            (200, try JSONSerialization.data(withJSONObject: modelReceipt)),
            (200, try JSONSerialization.data(withJSONObject: [modelReceipt]))]
        let model = VideoReviewModel(candidate: candidate, prepared: prepared, binding: binding, runtime: client)
        #expect(!model.begin(.accept))
        await model.load()
        #expect(model.loaded && model.begin(.accept))
        #expect(ShotReviewProtocol.requests.count == 1) // No POST for readback.
        await model.confirm()
        #expect(model.pending != nil && model.latest == nil)
        #expect(!model.begin(.reject)) // Do not replace an unresolved intent.
        await model.confirm()
        #expect(model.pending == nil && model.latest?.payload.user_approved == true)
        let firstAttempt = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies[1]) as! NSDictionary
        let retryAttempt = try JSONSerialization.jsonObject(with: ShotReviewProtocol.bodies[2]) as! NSDictionary
        #expect(firstAttempt == retryAttempt)
        let restarted = VideoReviewModel(candidate: candidate, prepared: prepared, binding: binding, runtime: client)
        await restarted.load()
        #expect(restarted.notice.contains("已记录为采用"))
        #expect(ShotReviewProtocol.requests.map(\.httpMethod) == ["GET", "POST", "POST", "GET"])
    }

    @MainActor @Test func previewOpeningIsLocalAndPendingQueryDoesNotGenerate() async throws {
        let binding = VideoSubmissionObservation(id: "binding", run_id: "run", task_key: "shot",
            request_sha256: "request", state: "submitted", provider_task_id: "provider-task")
        let pending = try JSONSerialization.data(withJSONObject: ["id": "obs", "run_id": "run", "event_type": "provider_task_observed",
            "payload": ["binding_id": "binding", "task_id": "provider-task", "status": "processing",
                "result_urls": [], "observation_sha256": "digest", "billing_verified": false,
                "generation_performed": false, "master_accepted": false]])
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, Data("[]".utf8)), (200, Data("[]".utf8)), (200, pending), (503, Data())]
        var reads = 0
        let model = VideoCandidateModel(binding: binding, runtime: runtime(), key: { reads += 1; return "fixture-key" })
        await model.restore()
        #expect(reads == 0 && model.fileURL == nil && !model.busy)
        #expect(ShotReviewProtocol.requests.map(\.httpMethod) == ["GET"])
        await model.refresh()
        #expect(reads == 1 && model.notice.contains("还在生成") && model.fileURL == nil)
        #expect(ShotReviewProtocol.requests.map(\.httpMethod) == ["GET", "GET", "POST"])
        #expect(ShotReviewProtocol.requests.last?.url?.path.hasSuffix("tasks/binding/refresh") == true)
        await model.refresh()
        #expect(reads == 1 && model.notice.contains("原任务保留") && !model.busy)
        #expect(ShotReviewProtocol.requests.count == 4)
    }

    @MainActor @Test func candidateRecoveryQueriesOnlyExistingTaskAndDownloadsWithoutKey() async throws {
        let binding = VideoSubmissionObservation(id: "binding", run_id: "run", task_key: "shot",
            request_sha256: "request", state: "submitted", provider_task_id: "provider-task")
        func observation(_ task: String = "provider-task", status: String = "completed") throws -> Data {
            try JSONSerialization.data(withJSONObject: ["id": "obs", "run_id": "run", "event_type": "provider_task_observed",
                "payload": ["binding_id": "binding", "task_id": task, "status": status,
                    "result_urls": ["https://example.org/video.mp4"], "observation_sha256": "digest",
                    "billing_verified": false, "generation_performed": false, "master_accepted": false]])
        }
        func candidate(_ task: String = "shot") throws -> Data {
            try JSONSerialization.data(withJSONObject: ["id": "candidate", "run_id": "run", "event_type": "video_result_materialized",
                "payload": ["binding_id": "binding", "observation_id": "obs", "observation_sha256": "digest",
                    "result_index": 0, "task_key": task, "request_sha256": "request", "video_downloaded": true,
                    "billing_verified": false, "generation_performed": false, "visual_semantics_verified": false,
                    "master_accepted": false]])
        }
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try observation()), (200, try candidate()), (200, try candidate("foreign")),
            (200, try observation("foreign"))]
        let client = runtime()
        let observed = try await client.refreshVideoTask(binding, apiKey: "synthetic-key")
        let saved = try await client.materializeVideo(observed, binding: binding)
        #expect(saved.id == "candidate")
        do { _ = try await client.materializeVideo(observed, binding: binding); Issue.record("foreign candidate") } catch {}
        do { _ = try await client.refreshVideoTask(binding, apiKey: "synthetic-key"); Issue.record("foreign task") } catch {}
        let pending = try JSONDecoder().decode(VideoTaskObservation.self, from: observation(status: "processing"))
        do { _ = try await client.materializeVideo(pending, binding: binding); Issue.record("pending media") } catch {}
        do { _ = try await client.materializeVideo(observed, binding: binding, resultIndex: 1); Issue.record("missing result") } catch {}
        #expect(ShotReviewProtocol.requests.count == 4)
        #expect(ShotReviewProtocol.requests[0].url?.path.hasSuffix("tasks/binding/refresh") == true)
        #expect(ShotReviewProtocol.requests[0].value(forHTTPHeaderField: "X-Nalu-Provider-Key") == "synthetic-key")
        #expect(ShotReviewProtocol.requests[1].url?.path.hasSuffix("video-observations/obs/materialize") == true)
        #expect(ShotReviewProtocol.requests[1].url?.query == "result_index=0")
        #expect(ShotReviewProtocol.requests[1].value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil)
        #expect(!ShotReviewProtocol.requests.contains { $0.url?.path.hasSuffix("/submit") == true })
    }

    private func videoReservationFixture() throws -> Data {
        try JSONSerialization.data(withJSONObject: ["id": "reservation-one", "run_id": "run-one", "event_type": "video_estimate_reserved",
            "payload": ["preparation_id": "prep-one", "preparation_sha256": String(repeating: "a", count: 64),
                "estimated_credits": 156, "confirmed_run_budget_credits": 1000, "pricing_quote_id": "quote-one",
                "guardian_approval": false, "task_key": "shot-one", "request_sha256": String(repeating: "b", count: 64),
                "published_price_observed": true, "generation_performed": false]])
    }

    @MainActor @Test func videoCostDispatchAndRecoveryAreSeparateBoundRequests() async throws {
        let approval = VideoCostApproval(preparation_sha256: String(repeating: "a", count: 64), estimated_credits: 156,
            confirmed_run_budget_credits: 1000, approved_by: "fixture-user", confirmation: "测试确认", guardian_approval: false,
            pricing_quote_id: "quote-one")
        let receipt = try JSONSerialization.data(withJSONObject: ["id": "binding-one", "run_id": "run-one", "task_key": "shot-one",
            "request_sha256": String(repeating: "b", count: 64), "state": "ambiguous_charge"])
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try videoReservationFixture()), (200, receipt), (200, receipt), (200, Data("null".utf8))]
        let client = runtime()
        let reservation = try await client.reserveVideoCost(runID: "run-one", preparationID: "prep-one", approval: approval)
        #expect(ShotReviewProtocol.requests.count == 1)
        #expect(ShotReviewProtocol.requests[0].value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil)
        let submitted = try await client.submitReservedVideo(reservation, apiKey: "synthetic-test-key")
        #expect(submitted.state == "ambiguous_charge")
        let recovered = try await client.observeVideoSubmission(reservation)
        #expect(recovered?.id == submitted.id)
        let absent = try await client.observeVideoSubmission(reservation)
        #expect(absent == nil)
        #expect(ShotReviewProtocol.requests.map(\.httpMethod) == ["POST", "POST", "GET", "GET"])
        #expect(ShotReviewProtocol.requests[1].url?.path.hasSuffix("reservation-one/submit") == true)
        #expect(ShotReviewProtocol.requests[1].value(forHTTPHeaderField: "X-Nalu-Provider-Key") == "synthetic-test-key")
        #expect(ShotReviewProtocol.requests[2].url?.path.hasSuffix("reservation-one/submission") == true)
        #expect(ShotReviewProtocol.requests[2].value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil)
    }

    @MainActor @Test func videoReservationRejectsChangedEstimateAndObservationRejectsForeignTask() async throws {
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try videoReservationFixture())]
        let different = VideoCostApproval(preparation_sha256: String(repeating: "a", count: 64), estimated_credits: 200,
            confirmed_run_budget_credits: 1000, approved_by: "fixture-user", confirmation: "测试确认", guardian_approval: false,
            pricing_quote_id: "quote-one")
        do { _ = try await runtime().reserveVideoCost(runID: "run-one", preparationID: "prep-one", approval: different)
            Issue.record("changed estimate must not be actionable") } catch {}
        let reservation = try JSONDecoder().decode(VideoCostReservation.self, from: videoReservationFixture())
        let foreign = try JSONSerialization.data(withJSONObject: ["id": "foreign", "run_id": "run-one", "task_key": "another-shot",
            "request_sha256": String(repeating: "b", count: 64), "state": "submitted", "provider_task_id": "fixture-task"])
        ShotReviewProtocol.queued = [(200, foreign), (503, Data())]
        do { _ = try await runtime().observeVideoSubmission(reservation); Issue.record("foreign shot") } catch {}
        do { _ = try await runtime().observeVideoSubmission(reservation); Issue.record("unavailable observation") } catch {}
        #expect(ShotReviewProtocol.requests.map(\.httpMethod) == ["POST", "GET", "GET"])
    }

    @MainActor @Test func productionAuthorizationBindsReceiptWithoutProviderKeyOrDispatch() async throws {
        let draft = ProductionAuthorizationDraft(source_event_id: "saved-plan",
            expected_plan_sha256: String(repeating: "a", count: 64), expected_package_sha256: String(repeating: "b", count: 64),
            confirmed_run_budget_credits: 1000, confirmation: "确认本集预算", guardian_approval: false)
        var record = try JSONSerialization.jsonObject(with: fixture(approved: true)) as! [String: Any]
        var payload = record["payload"] as! [String: Any]
        payload["production_authorization"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(draft))
        record["payload"] = payload
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try JSONSerialization.data(withJSONObject: record))]
        let saved = try await runtime().authorizeProduction(runID: "run-one", draft: draft)
        #expect(saved.payload.production_authorization == draft)
        #expect(ShotReviewProtocol.requests.count == 1)
        #expect(ShotReviewProtocol.requests[0].httpMethod == "POST")
        #expect(ShotReviewProtocol.requests[0].url?.path.hasSuffix("run-one/production-authorization") == true)
        #expect(ShotReviewProtocol.requests[0].value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil)
        #expect(ShotReviewProtocol.requests[0].value(forHTTPHeaderField: "X-Nalu-Writer-Key") == nil)
        // A successful HTTP response without this precise approval is not success.
        ShotReviewProtocol.queued = [(200, try fixture(approved: true))]
        do { _ = try await runtime().authorizeProduction(runID: "run-one", draft: draft); Issue.record("missing receipt") }
        catch {}
        record["run_id"] = "foreign-run"
        ShotReviewProtocol.queued = [(200, try JSONSerialization.data(withJSONObject: record))]
        do { _ = try await runtime().authorizeProduction(runID: "run-one", draft: draft); Issue.record("foreign receipt") }
        catch {}
    }

    private func refreshPreview(required: Bool, runID: String = "run-one") throws -> Data {
        try JSONSerialization.data(withJSONObject: ["run_id": runID, "refresh_required": required, "request": [
            "source_event_id": "saved-plan", "expected_plan_sha256": String(repeating: "a", count: 64),
            "expected_package_sha256": String(repeating: "b", count: 64),
            "expected_library_sha256": String(repeating: "c", count: 64)]])
    }

    @MainActor @Test func libraryRefreshUsesBoundPreviewThenReloadWithoutModelKey() async throws {
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try refreshPreview(required: true)),
                                    (200, try fixture(approved: true)), (200, try fixture(approved: true))]
        let result = try await runtime().refreshConfirmedLibrary(runID: "run-one")
        #expect(result.payload.approved)
        #expect(ShotReviewProtocol.requests.map(\.httpMethod) == ["GET", "POST", "GET"])
        #expect(ShotReviewProtocol.requests[1].url?.path.hasSuffix("run-one/library-snapshot-refresh") == true)
        #expect(ShotReviewProtocol.requests.last?.url?.path.hasSuffix("run-one/shot-plans/current") == true)
        #expect(ShotReviewProtocol.requests.allSatisfy {
            $0.value(forHTTPHeaderField: "X-Nalu-Writer-Key") == nil && $0.value(forHTTPHeaderField: "X-Nalu-Provider-Key") == nil
        })
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try refreshPreview(required: false)), (200, try fixture(approved: true))]
        _ = try await runtime().refreshConfirmedLibrary(runID: "run-one")
        #expect(ShotReviewProtocol.requests.map(\.httpMethod) == ["GET", "GET"])
    }

    @MainActor @Test func libraryRefreshRejectsForeignPreviewAndUnapprovedReload() async throws {
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try refreshPreview(required: true, runID: "another-run"))]
        do { _ = try await runtime().refreshConfirmedLibrary(runID: "run-one"); Issue.record("must reject foreign run") }
        catch { #expect(ShotReviewProtocol.requests.count == 1) }
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try refreshPreview(required: false)), (200, try fixture())]
        do { _ = try await runtime().refreshConfirmedLibrary(runID: "run-one"); Issue.record("must reject unapproved plan") }
        catch { #expect(ShotReviewProtocol.requests.count == 2) }
    }

    @MainActor @Test func libraryRefreshPreservesUnsavedShotEditsUntilExplicitReload() async throws {
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try fixture(approved: true))]
        let model = EpisodeShotPlanModel(runID: "run-one", runtime: runtime())
        await model.load()
        model.editedPlan?.shots[0].video_prompt = "老人刚说的修改"
        await model.reloadAfterLibraryRefresh()
        #expect(model.editedPlan?.shots[0].video_prompt == "老人刚说的修改")
        #expect(model.snapshotRefreshPending)
        #expect(ShotReviewProtocol.requests.count == 1)
        #expect(await model.prepareCharacterCards() == nil)
        ShotReviewProtocol.queued = [(200, try fixture(approved: true))]
        await model.load()
        #expect(!model.snapshotRefreshPending)
        #expect(!model.hasEdits)
    }

    @MainActor @Test func characterPreparationUsesApprovedSourceAndPreservesPlanOnFailure() async throws {
        ShotReviewProtocol.requests = []
        let cards = try JSONSerialization.data(withJSONObject: ["run_id": "run-one", "payload": [
            "plan_event_id": "saved-plan", "plan_sha256": String(repeating: "a", count: 64),
            "bindings": [["entity_id": "grandma", "revision": 1]], "readback": "外婆的待确认草稿",
            "characters_auto_confirmed": false]])
        ShotReviewProtocol.queued = [(200, try fixture(approved: true)), (200, cards),
                                    (409, Data("{\"detail\":\"source changed\"}".utf8))]
        let model = EpisodeShotPlanModel(runID: "run-one", runtime: runtime())
        await model.load()
        let prepared = await model.prepareCharacterCards()
        #expect(prepared?.payload.bindings.first?.entity_id == "grandma")
        #expect(ShotReviewProtocol.requests.last?.url?.path.hasSuffix("saved-plan/character-cards") == true)
        #expect(ShotReviewProtocol.requests.last?.value(forHTTPHeaderField: "X-Nalu-Writer-Key") == nil)
        #expect(await model.prepareCharacterCards() == nil)
        #expect(model.event?.payload.approved == true)
        #expect(model.notice?.contains("分镜已确认并保存") == true)
    }

    @MainActor @Test func characterPreparationRejectsUnapprovedPlanWithoutRequest() async throws {
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [(200, try fixture())]
        let model = EpisodeShotPlanModel(runID: "run-one", runtime: runtime())
        await model.load()
        #expect(await model.prepareCharacterCards() == nil)
        #expect(ShotReviewProtocol.requests.count == 1)
    }

    private func designedFixture(id: String, prompt: String, complete: Bool = false) throws -> Data {
        var root = try JSONSerialization.jsonObject(with: fixture()) as! [String: Any]
        var payload = root["payload"] as! [String: Any]
        var plan = payload["plan"] as! [String: Any]
        var shots = plan["shots"] as! [[String: Any]]
        shots[0]["video_prompt"] = prompt
        shots[0]["visual_asset_keys"] = ["grandma"]
        if complete {
            let camera = Dictionary(uniqueKeysWithValues: ["shot_scale", "camera_height", "camera_side", "axis_relation",
                "motion_family", "motion_direction", "start_framing", "end_framing", "motivation", "lens_intent"].map { ($0, "创作选择") })
            shots[0]["director"] = ["camera": camera,
                "state_delta": ["mode": "CHANGE", "dimensions": [["dimension": "POSTURE", "entry": "低头", "exit": "抬头"]]],
                "props": [], "visible_character_counts": ["grandma": 1], "combat_or_chase": false,
                "prior_event_relation": "UNKNOWN"] as [String: Any]
        }
        plan["shots"] = shots
        plan["visual_assets"] = [["key": "grandma", "kind": "character_image", "name": "外婆",
                                  "description": "待确认", "source_excerpt": "外婆看海"]]
        payload["plan"] = plan
        root["payload"] = payload
        root["id"] = id
        return try JSONSerialization.data(withJSONObject: root)
    }

    @MainActor @Test func savingEditsAutomaticallyEnrichesOnlyAfterDurableSave() async throws {
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [
            (200, try designedFixture(id: "original", prompt: "原描述", complete: true)),
            (200, try designedFixture(id: "user-edit", prompt: "从手部开始")),
            (200, try designedFixture(id: "enriched", prompt: "从手部开始", complete: true))]
        let model = EpisodeShotPlanModel(runID: "run-one", runtime: runtime(),
            writerConfiguration: { ("fixture-model", "synthetic-writer-key") })
        await model.load()
        model.editedPlan?.shots[0].video_prompt = "从手部开始"
        await model.review(approve: false)
        #expect(ShotReviewProtocol.requests.count == 3)
        #expect(ShotReviewProtocol.requests[1].url?.path.hasSuffix("original/review") == true)
        let refresh = ShotReviewProtocol.requests[2]
        #expect(refresh.url?.path.hasSuffix("user-edit/director-refresh") == true)
        #expect(refresh.value(forHTTPHeaderField: "X-Nalu-Writer-Key") == "synthetic-writer-key")
        #expect(model.event?.id == "enriched")
        #expect(model.editedPlan?.shots[0].video_prompt == "从手部开始")
        #expect(model.canApprove && !model.needsDirector)
        #expect(model.notice?.contains("再确认") == true)
        await model.continueDirector()
        #expect(ShotReviewProtocol.requests.count == 3)
    }

    @MainActor @Test func failedEnrichmentKeepsSavedEditAndLoadDoesNotRetry() async throws {
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [
            (200, try designedFixture(id: "original", prompt: "原描述", complete: true)),
            (200, try designedFixture(id: "user-edit", prompt: "保留我的修改")),
            (502, Data("{\"detail\":\"writer_http_401\"}".utf8)),
            (200, try designedFixture(id: "user-edit", prompt: "保留我的修改"))]
        let model = EpisodeShotPlanModel(runID: "run-one", runtime: runtime(),
            writerConfiguration: { ("fixture-model", "synthetic-writer-key") })
        await model.load()
        model.editedPlan?.shots[0].video_prompt = "保留我的修改"
        await model.review(approve: false)
        #expect(model.event?.id == "user-edit")
        #expect(model.editedPlan?.shots[0].video_prompt == "保留我的修改")
        #expect(model.needsDirector && !model.canApprove && !model.hasEdits)
        #expect(model.notice?.contains("您的修改已保存") == true)
        await model.review(approve: true)
        #expect(ShotReviewProtocol.requests.count == 3)
        await model.load()
        #expect(ShotReviewProtocol.requests.count == 4)
        #expect(ShotReviewProtocol.requests.filter { $0.url?.path.hasSuffix("director-refresh") == true }.count == 1)
    }

    @MainActor @Test func unavailableWriterDoesNotDiscardSavedRevisionOrAskForNewKey() async throws {
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.queued = [
            (200, try designedFixture(id: "original", prompt: "原描述", complete: true)),
            (200, try designedFixture(id: "user-edit", prompt: "新的描述"))]
        let model = EpisodeShotPlanModel(runID: "run-one", runtime: runtime(), writerConfiguration: { nil })
        await model.load()
        model.editedPlan?.shots[0].video_prompt = "新的描述"
        await model.review(approve: false)
        #expect(model.event?.id == "user-edit")
        #expect(model.editedPlan?.shots[0].video_prompt == "新的描述")
        #expect(ShotReviewProtocol.requests.count == 2)
        #expect(model.notice?.contains("继续改故事") == true)
    }

    @Test func structuredDirectorDraftSurvivesNativeRoundTrip() throws {
        var shot = try JSONDecoder().decode(EpisodeShotPlanEvent.self, from: fixture()).payload.plan.shots[0]
        let camera = Dictionary(uniqueKeysWithValues: ["shot_scale", "camera_height", "camera_side", "axis_relation",
            "motion_family", "motion_direction", "start_framing", "end_framing", "motivation", "lens_intent"].map { ($0, "待确认创作选择") })
        let object: [String: Any] = ["camera": camera,
            "state_delta": ["mode": "CHANGE", "dimensions": [["dimension": "POSTURE", "entry": "低头", "exit": "抬头"]]],
            "props": [], "visible_character_counts": ["grandma": 1], "combat_or_chase": false,
            "prior_event_relation": "UNKNOWN"]
        shot.director = try JSONDecoder().decode(EpisodeDirectorDraft.self, from: JSONSerialization.data(withJSONObject: object))
        let restored = try JSONDecoder().decode(EpisodeShot.self, from: JSONEncoder().encode(shot))
        #expect(restored.director == shot.director)
        #expect(restored.director?.visible_character_counts == ["grandma": 1])
        #expect(restored.director?.camera.motion_family == "待确认创作选择")
        let plan = EpisodeShotPlan(summary: "海边", shots: [restored], visual_assets: [
            EpisodeVisualAsset(key: "grandma", kind: "character_image", name: "外婆", description: "待确认",
                source_excerpt: "外婆看海", existing_asset_id: nil)])
        #expect(plan.directorReadback(for: 0).contains("外婆：1位"))
        #expect(plan.directorReadback(for: 0).contains("与上一集的关系尚待确认"))
        #expect(plan.directorReadback(for: 0).contains("不代表图片已经核验"))
        #expect(!plan.directorReadback(for: 0).contains("grandma"))
        #expect(plan.directorReadback(for: 99).isEmpty)
    }

    private func fixture(approved: Bool = false) throws -> Data {
        let shot = EpisodeShot(source_excerpt: "外婆看海", scene: "海边", duration_seconds: 12,
            entry_state: "站在岸边", action: "抬头", exit_state: "看海", camera: "中景",
            dialogue_or_narration: "我回来了", sound: "海浪", image_prompt: "入镜首帧",
            video_prompt: "缓缓抬头", reference_asset_ids: [], transition: "scene_start")
        let plan = try JSONSerialization.jsonObject(with: JSONEncoder().encode(EpisodeShotPlan(summary: "回到海边", shots: [shot])))
        return try JSONSerialization.data(withJSONObject: ["id": "saved-plan", "run_id": "run-one",
            "payload": ["plan": plan, "plan_sha256": String(repeating: "a", count: 64), "approved": approved]])
    }

    private func runtime() -> RuntimeClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ShotReviewProtocol.self]
        return RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true })
    }

    @MainActor @Test func loadEditConfirmUsesCurrentVersionWithoutModelCalls() async throws {
        ShotReviewProtocol.requests = []
        ShotReviewProtocol.status = 200
        ShotReviewProtocol.response = try fixture()
        let model = EpisodeShotPlanModel(runID: "run-one", runtime: runtime())
        await model.load()
        #expect(model.canApprove)
        model.editedPlan?.shots[0].video_prompt = "从手部开始"
        #expect(model.hasEdits)
        #expect(!model.canApprove)
        await model.review(approve: true)
        #expect(ShotReviewProtocol.requests.count == 1)
        ShotReviewProtocol.status = 409
        await model.review(approve: false)
        #expect(model.editedPlan?.shots[0].video_prompt == "从手部开始")
        #expect(model.notice?.contains("修改仍在这里") == true)
        ShotReviewProtocol.status = 200
        await model.load()
        ShotReviewProtocol.response = try fixture(approved: true)
        await model.review(approve: true)
        #expect(model.event?.payload.approved == true)
        #expect(!model.canApprove)
        #expect(ShotReviewProtocol.requests.last?.url?.path == "/v1/production-runs/run-one/shot-plans/saved-plan/review")
        #expect(ShotReviewProtocol.requests.allSatisfy { $0.value(forHTTPHeaderField: "X-Nalu-Writer-Key") == nil })
    }

    @Test func exactReviewEncodingDoesNotAttachPlanToApproval() throws {
        let request = EpisodeShotReview(expected_plan_sha256: String(repeating: "b", count: 64),
            action: "approve", plan: nil, confirmation: "确认当前版本")
        let body = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as! [String: Any]
        #expect(body["plan"] == nil)
        #expect(body["action"] as? String == "approve")
        #expect(body["paid_generation_approved"] == nil)
    }

    @Test func referenceDesignsSurviveEditingAndReadbackWithoutBecomingAssets() throws {
        let old = try JSONDecoder().decode(EpisodeShotPlanEvent.self, from: fixture()).payload.plan
        #expect(old.visual_assets == nil && old.assetReadback(for: 0).isEmpty)
        var plan = old
        plan.visual_assets = [.init(key: "grandma", kind: "character_image", name: "外婆", description: "外貌待确认",
                                    source_excerpt: "外婆看海", existing_asset_id: nil)]
        plan.shots[0].visual_asset_keys = ["grandma"]
        plan.shots[0].video_prompt = "保留这个修改"
        let restored = try JSONDecoder().decode(EpisodeShotPlan.self, from: JSONEncoder().encode(plan))
        #expect(restored == plan)
        #expect(restored.shots[0].reference_asset_ids.isEmpty)
        #expect(restored.assetReadback(for: 0).contains("外婆"))
        #expect(restored.assetReadback(for: 0).contains("不是已生成的图片"))
        #expect(restored.assetReadback(for: 99).isEmpty)
    }
}
