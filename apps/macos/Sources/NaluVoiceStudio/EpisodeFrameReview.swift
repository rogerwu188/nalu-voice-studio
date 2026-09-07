import Foundation
import Observation

struct FrameProductionEvent: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    private enum CodingKeys: String, CodingKey { case id, run_id, event_type, payload }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        run_id = try values.decode(String.self, forKey: .run_id)
        event_type = try values.decode(String.self, forKey: .event_type)
        if ["image_task_prepared", "image_task_submitted", "image_submit_intent", "image_submit_unconfirmed",
            "image_result_materialized", "image_frame_reviewed", "reference_asset_registered"].contains(event_type) {
            payload = try values.decode(Payload.self, forKey: .payload)
        } else { payload = Payload() }
    }
    struct Payload: Decodable, Sendable {
        var task_key: String?
        var image_task_key: String?
        var approved_shot_index: Int?
        var approved_plan_event_id: String?
        var request_sha256: String?
        var materialization_sha256: String?
        var materialization_id: String?
        var decision: String?
        var visual_asset_key: String?
        var purpose: String?
        var review_id: String?
        var asset_id: String?
        var image: ImageInfo?
    }
    struct ImageInfo: Decodable, Sendable { let sha256: String }
}

struct SavedImageProgress: Decodable, Sendable {
    enum Phase: String, Decodable, Sendable { case waiting, provider_failed, ready_for_review }
    let run_id: String
    let submission_id: String
    let phase: Phase
    let materialization_id: String?
    let generation_performed: Bool
}

struct FrameReviewDraft: Encodable, Sendable {
    let preparation_id: String
    let expected_materialization_sha256: String
    let expected_review_event_id: String?
    let decision: String
    let reviewed_by = "nalu-native-user"
    let confirmation: String
}

struct ReferencePermissionDraft: Encodable, Sendable {
    let consent_granted = true
    let confirmed_by = "nalu-native-user"
    let statement = "用户已查看生成参考图，并明确同意将其用于本项目；涉及真人形象时已取得本人或合法授权人的同意。"
    let guardian_approved: Bool
}

@MainActor @Observable final class EpisodeFrameReviewModel {
    let runID: String
    let planID: String
    let shotIndex: Int
    let referenceKey: String?
    private let runtime: RuntimeClient
    private let providerKey: () async throws -> String?
    var busy = false
    var loaded = false
    var imageData: Data?
    var preparation: FrameProductionEvent?
    var materialization: FrameProductionEvent?
    var latestReview: FrameProductionEvent?
    var notice: String?
    var registeredAssetID: String?

    init(runID: String, planID: String, shotIndex: Int, referenceKey: String? = nil, runtime: RuntimeClient = RuntimeClient(),
         providerKey: @escaping () async throws -> String? = {
             try await Task.detached {
                 try KeychainSecretStore().secret(for: .seedance, allowAuthenticationUI: false)
             }.value
         }) {
        self.runID = runID; self.planID = planID; self.shotIndex = shotIndex; self.referenceKey = referenceKey; self.runtime = runtime
        self.providerKey = providerKey
    }

    var canReview: Bool { !busy && imageData != nil && materialization != nil && preparation != nil }
    var canRegister: Bool { canReview && referenceKey != nil && registeredAssetID == nil
        && latestReview?.payload.decision == "accept" && latestReview?.payload.materialization_id == materialization?.id }

    func load() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        // Old bytes must never remain actionable after a failed refresh.
        imageData = nil; materialization = nil; preparation = nil; latestReview = nil; registeredAssetID = nil
        do {
            var events = try await runtime.frameProductionEvents(runID: runID)
            guard !Task.isCancelled else { return }
            // Recompile locally even when an old record exists: newly registered
            // references change the request. This never submits a provider task.
            let prepared: FrameProductionEvent
            if let referenceKey {
                prepared = try await runtime.prepareReviewedReference(runID: runID, planID: planID, key: referenceKey)
            } else {
                prepared = try await runtime.prepareReviewedShotFrame(runID: runID, planID: planID, shotIndex: shotIndex)
            }
            guard !Task.isCancelled else { return }
            guard prepared.run_id == runID, prepared.event_type == "image_task_prepared",
                  prepared.payload.request_sha256?.isEmpty == false,
                  prepared.payload.image_task_key?.isEmpty == false,
                  prepared.payload.approved_plan_event_id == planID,
                  (referenceKey != nil ? (prepared.payload.visual_asset_key == referenceKey && prepared.payload.purpose == "visual_reference")
                    : prepared.payload.approved_shot_index == shotIndex) else {
                throw RuntimeError.requestFailed("首帧任务不属于当前镜头")
            }
            preparation = prepared
            func matches(_ event: FrameProductionEvent) -> Bool {
                event.run_id == runID && event.payload.request_sha256 == prepared.payload.request_sha256
                    && event.payload.task_key == prepared.payload.image_task_key
            }
            if !events.contains(where: { $0.event_type == "image_result_materialized" && matches($0) }),
               let submission = events.last(where: { ["image_task_submitted", "image_submit_intent", "image_submit_unconfirmed"].contains($0.event_type)
                   && matches($0) }) {
                guard submission.event_type == "image_task_submitted" else {
                    loaded = true
                    notice = "这次图片提交的结果还需要核对。不会重新提交，您的剧本和素材都还在。"
                    return
                }
                guard let key = try await providerKey(), !key.isEmpty else {
                    loaded = true
                    notice = "原图片任务已保留，目前无法读取制作进度。不会重新生成；已有画面仍可查看。"
                    return
                }
                guard !Task.isCancelled else { return }
                let progress = try await runtime.advanceSavedImage(runID: runID, submissionID: submission.id, apiKey: key)
                guard !Task.isCancelled else { return }
                guard progress.run_id == runID, progress.submission_id == submission.id, !progress.generation_performed else {
                    throw RuntimeError.requestFailed("图片进度与当前任务不一致")
                }
                guard progress.phase == .ready_for_review else {
                    loaded = true
                    notice = progress.phase == .waiting ? "图片还在制作中。稍后点“重新读取画面”可继续查看同一个任务，不会重复生成。"
                        : "这次图片制作未成功。剧本和素材已保留，不会自动扣费重做。"
                    return
                }
                events = try await runtime.frameProductionEvents(runID: runID)
                guard !Task.isCancelled else { return }
                guard events.contains(where: { $0.id == progress.materialization_id
                    && $0.event_type == "image_result_materialized" && matches($0) }) else {
                    throw RuntimeError.requestFailed("图片结果尚未核对成功")
                }
            }
            guard let saved = events.last(where: { $0.run_id == runID && $0.event_type == "image_result_materialized"
                && $0.payload.request_sha256 == prepared.payload.request_sha256
                && $0.payload.task_key == prepared.payload.image_task_key }),
                let sha = saved.payload.image?.sha256 else {
                loaded = true
                notice = (referenceKey == nil ? "首帧任务已准备" : "参考图任务已准备")
                    + "，尚未取得可查看的图片。后续仍需制作检查和费用确认；这次准备和读取没有发起新的生成或扣费。"
                return
            }
            let data = try await runtime.savedFrameBytes(runID: runID, materializationID: saved.id, expectedSHA: sha)
            guard !Task.isCancelled else { return }
            preparation = prepared; materialization = saved; imageData = data
            latestReview = events.last(where: { $0.run_id == runID && $0.event_type == "image_frame_reviewed"
                && $0.payload.task_key == saved.payload.task_key })
            registeredAssetID = events.last(where: { $0.run_id == runID && $0.event_type == "reference_asset_registered"
                && $0.payload.review_id == latestReview?.id && $0.payload.visual_asset_key == referenceKey })?.payload.asset_id
            loaded = true; notice = nil
        } catch {
            notice = "这张画面暂时无法核对，请点“重新读取画面”。没有重新生成或改变您的确认。"
        }
    }

    func review(accept: Bool) async {
        guard canReview, let preparation, let materialization,
              let sha = materialization.payload.materialization_sha256 else { return }
        busy = true
        defer { busy = false }
        do {
            latestReview = try await runtime.reviewSavedFrame(runID: runID, materializationID: materialization.id,
                draft: .init(preparation_id: preparation.id, expected_materialization_sha256: sha,
                    expected_review_event_id: latestReview?.id, decision: accept ? "accept" : "reject",
                    confirmation: accept ? "用户查看当前画面后选择这张可以" : "用户查看当前画面后要求修改"))
            registeredAssetID = nil
            notice = accept ? "已记下您认可这张画面。后续制作仍需质量检查，不会因此直接扣费。"
                : "已记下这张需要修改。图片和剧本都会保留，不会自动重新生成。"
        } catch {
            imageData = nil
            notice = "这次确认尚未成功，可能是画面或分镜版本变了。请重新读取画面后核对。"
        }
    }

    func registerReference(guardianApproved: Bool) async {
        guard canRegister, let latestReview else { return }
        busy = true
        defer { busy = false }
        do {
            let asset = try await runtime.registerReviewedReference(runID: runID, reviewID: latestReview.id, guardianApproved: guardianApproved)
            registeredAssetID = asset.id
            notice = "已保存为本项目参考素材，后续镜头会复用。尚未生成或发布视频。"
        } catch {
            notice = "素材登记尚未确认。请重新读取画面后核对；不会自动重新生成图片。"
        }
    }
}
