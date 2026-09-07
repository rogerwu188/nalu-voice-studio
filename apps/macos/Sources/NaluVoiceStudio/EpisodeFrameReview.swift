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
            "image_result_materialized", "image_frame_reviewed", "reference_asset_registered", "video_task_prepared"].contains(event_type) {
            payload = try values.decode(Payload.self, forKey: .payload)
        } else { payload = Payload() }
    }
    struct Payload: Decodable, Sendable {
        var task_key: String?
        var image_task_key: String?
        var approved_shot_index: Int?
        var approved_plan_event_id: String?
        var approved_plan_sha256: String?
        var approved_frame_review_id: String?
        var approved_tail_id: String?
        var approved_tail_sha256: String?
        var frame_materialization_id: String?
        var preparation_sha256: String?
        var user_approved: Bool?
        var paid_approved: Bool?
        var generation_performed: Bool?
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

struct ReviewedVideoDraft: Encodable, Sendable {
    let expected_plan_sha256: String
    let shot_index: Int
    let approved_frame_review_id: String
}

struct VideoPriceObservation: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let preparation_id: String
        let preparation_sha256: String
        let estimated_credits: Int
        let duration_seconds: Int
        let expires_at: String
        let published_price_observed: Bool
        let provider_charge_cap_guaranteed: Bool
        let generation_performed: Bool
    }
    var isCurrent: Bool {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: payload.expires_at) ?? ISO8601DateFormatter().date(from: payload.expires_at)
        return date.map { $0 > Date() } ?? false
    }
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
    var videoPreparation: FrameProductionEvent?
    var videoPrice: VideoPriceObservation?

    init(runID: String, planID: String, shotIndex: Int, referenceKey: String? = nil, runtime: RuntimeClient = RuntimeClient(),
         providerKey: @escaping () async throws -> String? = {
             try await Task.detached {
                 try KeychainSecretStore().secret(for: .seedance, allowAuthenticationUI: false)
             }.value
         }) {
        self.runID = runID; self.planID = planID; self.shotIndex = shotIndex; self.referenceKey = referenceKey; self.runtime = runtime
        self.providerKey = providerKey
    }

    var canReview: Bool { !busy && imageData != nil && materialization != nil && preparation != nil && videoPreparation == nil }
    var canPrepareVideo: Bool { canReview && referenceKey == nil && latestReview?.payload.decision == "accept"
        && latestReview?.payload.user_approved == true && latestReview?.payload.materialization_id == materialization?.id
        && latestReview?.payload.approved_plan_event_id == planID && latestReview?.payload.approved_plan_sha256 != nil }
    var canRegister: Bool { canReview && referenceKey != nil && registeredAssetID == nil
        && latestReview?.payload.decision == "accept" && latestReview?.payload.materialization_id == materialization?.id }

    func load() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        // Old bytes must never remain actionable after a failed refresh.
        imageData = nil; materialization = nil; preparation = nil; latestReview = nil; registeredAssetID = nil; videoPreparation = nil
        videoPrice = nil
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
            if referenceKey == nil, let review = latestReview, let materialization {
                videoPreparation = events.last(where: { matchesVideoPreparation($0, reviewID: review.id, materializationID: materialization.id) })
            }
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

    private func matchesVideoPreparation(_ event: FrameProductionEvent, reviewID: String, materializationID: String) -> Bool {
        event.run_id == runID && event.event_type == "video_task_prepared"
            && event.payload.approved_plan_event_id == planID && event.payload.approved_shot_index == shotIndex
            && event.payload.approved_frame_review_id == reviewID && event.payload.frame_materialization_id == materializationID
            && event.payload.paid_approved == false && event.payload.generation_performed == false
            && event.payload.preparation_sha256?.isEmpty == false
    }

    func prepareVideo() async {
        guard canPrepareVideo, let review = latestReview, let materialization,
              let sha = review.payload.approved_plan_sha256 else { return }
        busy = true
        defer { busy = false }
        do {
            guard let plan = try await runtime.currentShotPlan(runID: runID), plan.run_id == runID,
                  plan.id == planID, plan.payload.approved, plan.payload.plan_sha256 == sha,
                  !Task.isCancelled else { throw LibrarySnapshotRefreshError.contextChanged }
            let saved = try await runtime.prepareReviewedVideo(runID: runID, planID: planID,
                draft: .init(expected_plan_sha256: sha, shot_index: shotIndex, approved_frame_review_id: review.id))
            guard !Task.isCancelled, latestReview?.id == review.id, self.materialization?.id == materialization.id,
                  saved.payload.approved_plan_sha256 == sha,
                  matchesVideoPreparation(saved, reviewID: review.id, materializationID: materialization.id) else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            videoPreparation = saved
            notice = "这个镜头的视频任务资料已备好，尚未扣费或生成。下一步需要核对费用并明确同意。"
        } catch {
            notice = "视频任务尚未准备成功，可能需要补齐拍摄细节或重新核对画面。已确认的图片和剧本保留，没有提交付费生成。请重新读取画面后再试。"
        }
    }

    func observeVideoPrice() async {
        guard !busy, let prepared = videoPreparation else { return }
        busy = true; videoPrice = nil
        defer { busy = false }
        do {
            let price = try await runtime.observeVideoPrice(runID: runID, preparationID: prepared.id)
            guard !Task.isCancelled, videoPreparation?.id == prepared.id,
                  price.run_id == runID, price.event_type == "video_price_observed",
                  price.payload.preparation_id == prepared.id,
                  price.payload.preparation_sha256 == prepared.payload.preparation_sha256,
                  price.payload.published_price_observed, !price.payload.provider_charge_cap_guaranteed,
                  !price.payload.generation_performed, price.payload.estimated_credits > 0, price.isCurrent else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            videoPrice = price
            notice = "按当前公开价格，这个\(price.payload.duration_seconds)秒镜头预计使用\(price.payload.estimated_credits)积分。实际账单可能不同；目前没有扣费或生成。"
        } catch {
            notice = "暂时无法核实这个镜头的当前价格。视频任务资料仍保留，没有提交生成或扣费。可以稍后重新查看费用。"
        }
    }
}
