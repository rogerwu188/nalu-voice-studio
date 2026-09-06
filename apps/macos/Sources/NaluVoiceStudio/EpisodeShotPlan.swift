import Foundation
import Observation

struct EpisodeShot: Codable, Equatable {
    var source_excerpt: String
    var scene: String
    var duration_seconds: Int
    var entry_state: String
    var action: String
    var exit_state: String
    var camera: String
    var dialogue_or_narration: String
    var sound: String
    var image_prompt: String
    var video_prompt: String
    var reference_asset_ids: [String]
    var transition: String

    var readback: String {
        "在\(scene)，用\(duration_seconds)秒。\(action)。对白或旁白：\(dialogue_or_narration)。"
    }
}

struct EpisodeShotPlan: Codable, Equatable {
    var summary: String
    var shots: [EpisodeShot]
}

struct EpisodeShotPlanEvent: Decodable {
    var id: String
    var run_id: String
    var payload: Payload
    struct Payload: Decodable {
        var plan: EpisodeShotPlan
        var plan_sha256: String
        var approved: Bool
    }
}

struct EpisodeShotReview: Encodable {
    var expected_plan_sha256: String
    var action: String
    var plan: EpisodeShotPlan?
    var reviewed_by = "nalu-native-user"
    var confirmation: String
}

@MainActor @Observable
final class EpisodeShotPlanModel {
    private let runtime: RuntimeClient
    let runID: String
    var event: EpisodeShotPlanEvent?
    var editedPlan: EpisodeShotPlan?
    var busy = false
    var loaded = false
    var notice: String?
    var generationAttempted = false

    init(runID: String, runtime: RuntimeClient = RuntimeClient()) {
        self.runID = runID
        self.runtime = runtime
    }

    var hasEdits: Bool { editedPlan != event?.payload.plan }
    var canApprove: Bool { event != nil && !hasEdits && event?.payload.approved == false && !busy }

    func load() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let saved = try await runtime.currentShotPlan(runID: runID)
            guard !Task.isCancelled else { return }
            event = saved
            editedPlan = saved?.payload.plan
            loaded = true
            notice = nil
        } catch {
            notice = "暂时无法读取本集分镜。请稍后点“读取已保存方案”；没有重新生成。"
        }
    }

    func generate() async {
        guard loaded, event == nil, !busy, !generationAttempted else { return }
        busy = true
        defer { busy = false }
        do {
            let endpoint = try AIServiceEndpoint.current()
            guard endpoint.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) == "https://hopsapi.com/v1",
                  let key = try KeychainSecretStore().secret(for: .openAIRealtime), !key.isEmpty else {
                notice = "分镜生成需要已配置的 Hops 模型服务。现有剧本仍然保留。"
                return
            }
            let model = try AIServiceModels.load(for: endpoint).research
            generationAttempted = true
            let saved = try await runtime.generateShotPlan(runID: runID, model: model, apiKey: key)
            event = saved
            editedPlan = saved.payload.plan
            notice = "分镜已保存，请听一听或看一看，再确认。还没有生成视频。"
        } catch {
            notice = "这次分镜生成尚未确认成功。请先读取已保存方案；不会自动重复调用模型，剧本没有丢失。"
        }
    }

    func review(approve: Bool) async {
        guard let event, let editedPlan, !busy, !approve || canApprove else { return }
        busy = true
        defer { busy = false }
        do {
            let saved = try await runtime.reviewShotPlan(runID: runID, eventID: event.id,
                request: .init(expected_plan_sha256: event.payload.plan_sha256,
                    action: approve ? "approve" : "revise", plan: approve ? nil : editedPlan,
                    confirmation: approve ? "用户确认当前保存的本集分镜" : "用户保存本集分镜修改"))
            self.event = saved
            self.editedPlan = saved.payload.plan
            notice = approve ? "本集分镜已确认，下一步准备画面；还没有扣费制作视频。" : "修改已保存，请重新确认这个版本。"
        } catch {
            notice = "这次保存或确认未成功，可能是版本已变化。您的修改仍在这里，请先保留，再读取已保存方案核对。"
        }
    }
}
