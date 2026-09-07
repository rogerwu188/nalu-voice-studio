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
        if ["image_task_prepared", "image_result_materialized", "image_frame_reviewed"].contains(event_type) {
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
        var image: ImageInfo?
    }
    struct ImageInfo: Decodable, Sendable { let sha256: String }
}

struct FrameReviewDraft: Encodable, Sendable {
    let preparation_id: String
    let expected_materialization_sha256: String
    let expected_review_event_id: String?
    let decision: String
    let reviewed_by = "nalu-native-user"
    let confirmation: String
}

@MainActor @Observable final class EpisodeFrameReviewModel {
    let runID: String
    let planID: String
    let shotIndex: Int
    private let runtime: RuntimeClient
    var busy = false
    var loaded = false
    var imageData: Data?
    var preparation: FrameProductionEvent?
    var materialization: FrameProductionEvent?
    var latestReview: FrameProductionEvent?
    var notice: String?

    init(runID: String, planID: String, shotIndex: Int, runtime: RuntimeClient = RuntimeClient()) {
        self.runID = runID; self.planID = planID; self.shotIndex = shotIndex; self.runtime = runtime
    }

    var canReview: Bool { !busy && imageData != nil && materialization != nil && preparation != nil }

    func load() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        // Old bytes must never remain actionable after a failed refresh.
        imageData = nil; materialization = nil; preparation = nil; latestReview = nil
        do {
            let events = try await runtime.frameProductionEvents(runID: runID)
            guard !Task.isCancelled else { return }
            // Recompile locally even when an old record exists: newly registered
            // references change the request. This never submits a provider task.
            let prepared = try await runtime.prepareReviewedShotFrame(runID: runID, planID: planID, shotIndex: shotIndex)
            guard !Task.isCancelled else { return }
            guard prepared.run_id == runID, prepared.event_type == "image_task_prepared",
                  prepared.payload.approved_plan_event_id == planID, prepared.payload.approved_shot_index == shotIndex else {
                throw RuntimeError.requestFailed("首帧任务不属于当前镜头")
            }
            preparation = prepared
            guard let saved = events.last(where: { $0.run_id == runID && $0.event_type == "image_result_materialized"
                && $0.payload.request_sha256 == prepared.payload.request_sha256
                && $0.payload.task_key == prepared.payload.image_task_key }),
                let sha = saved.payload.image?.sha256 else {
                loaded = true; notice = "首帧任务已准备，尚未取得可查看的图片。后续仍需制作检查和费用确认；这次准备和读取没有发起新的生成或扣费。"; return
            }
            let data = try await runtime.savedFrameBytes(runID: runID, materializationID: saved.id, expectedSHA: sha)
            guard !Task.isCancelled else { return }
            preparation = prepared; materialization = saved; imageData = data
            latestReview = events.last(where: { $0.run_id == runID && $0.event_type == "image_frame_reviewed"
                && $0.payload.task_key == saved.payload.task_key })
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
                    confirmation: accept ? "用户查看当前首帧后选择这张可以" : "用户查看当前首帧后要求修改"))
            notice = accept ? "已记下您认可这张首帧。后续制作仍需质量检查，不会因此直接扣费。"
                : "已记下这张需要修改。图片和剧本都会保留，不会自动重新生成。"
        } catch {
            imageData = nil
            notice = "这次确认尚未成功，可能是画面或分镜版本变了。请重新读取画面后核对。"
        }
    }
}
