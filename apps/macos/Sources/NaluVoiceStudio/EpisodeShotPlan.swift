import Foundation
import Observation

struct EpisodeDirectorDraft: Codable, Equatable {
    struct Camera: Codable, Equatable {
        var shot_scale: String
        var camera_height: String
        var camera_side: String
        var axis_relation: String
        var motion_family: String
        var motion_direction: String
        var start_framing: String
        var end_framing: String
        var motivation: String
        var lens_intent: String
    }
    struct Delta: Codable, Equatable {
        struct Dimension: Codable, Equatable { var dimension: String; var entry: String; var exit: String }
        var mode: String
        var dimensions: [Dimension]
        var hold_reason: String?
    }
    struct Prop: Codable, Equatable {
        struct Endpoint: Codable, Equatable { var owner: String; var hand: String; var position: String; var disposition: String }
        var design_key: String
        var entry: Endpoint
        var exit: Endpoint
        var transition_description: String
    }
    var camera: Camera
    var state_delta: Delta
    var props: [Prop]
    var visible_character_counts: [String: Int]
    var combat_or_chase: Bool
    var prior_event_relation: String
    var continuation_action: String?
}

struct EpisodeShot: Codable, Equatable {
    var source_excerpt: String
    var scene: String
    var duration_seconds: Int
    var entry_state: String
    var action: String
    var exit_state: String
    var camera: String
    var director: EpisodeDirectorDraft? = nil
    var dialogue_or_narration: String
    var sound: String
    var image_prompt: String
    var video_prompt: String
    var reference_asset_ids: [String]
    var visual_asset_keys: [String]? = nil
    var transition: String

    var readback: String {
        "在\(scene)，用\(duration_seconds)秒。\(action)。对白或旁白：\(dialogue_or_narration)。"
    }
}

struct EpisodeVisualAsset: Codable, Equatable {
    var key: String
    var kind: String
    var name: String
    var description: String
    var source_excerpt: String
    var existing_asset_id: String?
}

struct EpisodeShotPlan: Codable, Equatable {
    var summary: String
    var shots: [EpisodeShot]
    // Optional decoding preserves old saved plans; new designs survive edits.
    var visual_assets: [EpisodeVisualAsset]? = nil

    func directorReadback(for index: Int) -> String {
        guard shots.indices.contains(index) else { return "" }
        guard let director = shots[index].director else {
            return "拍摄细节还需要按当前描述整理，不能沿用修改前的专业参数。"
        }
        let names = Dictionary((visual_assets ?? []).map { ($0.key, $0.name) }, uniquingKeysWith: { first, _ in first })
        let c = director.camera
        var parts = ["拟定的拍法，可以继续修改：",
            "画面范围：\(c.shot_scale)。拍摄高度：\(c.camera_height)。从哪边拍：\(c.camera_side)。左右方向关系：\(c.axis_relation)。",
            "镜头怎么动：\(c.motion_family)，方向：\(c.motion_direction)。开始画面：\(c.start_framing)。结束画面：\(c.end_framing)。",
            "这样拍的用意：\(c.motivation)。希望呈现的远近感觉：\(c.lens_intent)。"]
        parts += director.state_delta.dimensions.map { "状态从“\($0.entry)”到“\($0.exit)”。" }
        if let reason = director.state_delta.hold_reason { parts.append("保持这个状态的原因：\(reason)。") }
        parts += director.visible_character_counts.keys.sorted().map { "画面中的\(names[$0] ?? "待确认人物")：\(director.visible_character_counts[$0] ?? 0)位。" }
        for prop in director.props {
            func describe(_ endpoint: EpisodeDirectorDraft.Prop.Endpoint) -> String {
                let owner = endpoint.owner == "none" ? "无人持有" : names[endpoint.owner] ?? "待确认人物"
                return "\(owner)，\(endpoint.hand)，位置\(endpoint.position)，状态\(endpoint.disposition)"
            }
            parts.append("\(names[prop.design_key] ?? "待确认道具")：开始\(describe(prop.entry))；结束\(describe(prop.exit))。\(prop.transition_description)。")
        }
        parts.append(director.combat_or_chase ? "这段包含打斗或追逐的创作安排。" : "这段不安排打斗或追逐。")
        let relations = ["UNKNOWN": "与上一集的关系尚待确认", "CONTINUING": "继续上一集尚未结束的事情",
                         "RESOLVED": "上一集的事情已经结束", "ELAPSED": "距离上一集已经过了一段时间"]
        parts.append(relations[director.prior_event_relation] ?? "跨集关系需要核对")
        if let action = director.continuation_action { parts.append("接下来的动作：\(action)。") }
        parts.append("这些是创作安排，不代表图片已经核验或费用已经批准。")
        return parts.joined(separator: "\n")
    }

    func assetReadback(for index: Int) -> String {
        guard shots.indices.contains(index) else { return "" }
        let keys = Set(shots[index].visual_asset_keys ?? [])
        let selected = (visual_assets ?? []).filter { keys.contains($0.key) }
        guard !selected.isEmpty else { return "" }
        let details = selected.map { asset in
            let role = asset.kind == "character_image" ? "人物" : asset.kind == "scene_reference" ? "场景" : "道具"
            return "\(role)：\(asset.name)。\(asset.description)"
        }.joined(separator: "\n")
        return "这个镜头需要准备的素材：\n" + details + "\n这些是待制作的设计，不是已生成的图片；人物授权和费用仍需另外确认。"
    }
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
    private let writerConfiguration: () async throws -> (model: String, key: String)?
    let runID: String
    var event: EpisodeShotPlanEvent?
    var editedPlan: EpisodeShotPlan?
    var busy = false
    var loaded = false
    var notice: String?
    var generationAttempted = false

    init(runID: String, runtime: RuntimeClient = RuntimeClient(),
         writerConfiguration: @escaping () async throws -> (model: String, key: String)? = {
             let endpoint = try AIServiceEndpoint.current()
             guard endpoint.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) == "https://hopsapi.com/v1" else { return nil }
             let model = try AIServiceModels.load(for: endpoint).research
             let key = try await Task.detached {
                 try KeychainSecretStore().secret(for: .openAIRealtime, allowAuthenticationUI: false)
             }.value
             guard let key, !key.isEmpty else { return nil }
             return (model, key)
         }) {
        self.runID = runID
        self.runtime = runtime
        self.writerConfiguration = writerConfiguration
    }

    var hasEdits: Bool { editedPlan != event?.payload.plan }
    var needsDirector: Bool {
        guard let plan = event?.payload.plan, !(plan.visual_assets ?? []).isEmpty else { return false }
        return plan.shots.contains { $0.director == nil }
    }
    var canApprove: Bool { event != nil && !hasEdits && !needsDirector && event?.payload.approved == false && !busy }

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
            if !approve && needsDirector { await enrichSavedPlan(saved) }
        } catch {
            notice = "这次保存或确认未成功，可能是版本已变化。您的修改仍在这里，请先保留，再读取已保存方案核对。"
        }
    }

    func continueDirector() async {
        guard let event, needsDirector, !hasEdits, !busy else { return }
        busy = true
        defer { busy = false }
        await enrichSavedPlan(event)
    }

    private func enrichSavedPlan(_ source: EpisodeShotPlanEvent) async {
        notice = "您的修改已保存，正在按这个版本整理拍摄细节。"
        do {
            guard let configuration = try await writerConfiguration() else {
                notice = "您的修改已保存。暂时无法使用已配置的模型服务，拍摄细节还没整理；可以继续改故事，服务恢复后再点“继续整理拍法”。"
                return
            }
            guard !Task.isCancelled, event?.id == source.id, !hasEdits else { return }
            let refreshed = try await runtime.refreshDirector(runID: runID, eventID: source.id,
                planSHA: source.payload.plan_sha256, model: configuration.model, apiKey: configuration.key)
            guard !Task.isCancelled, event?.id == source.id, !hasEdits else { return }
            guard refreshed.run_id == runID, !refreshed.payload.approved,
                  refreshed.payload.plan.shots.allSatisfy({ $0.director != nil }) else {
                throw URLError(.badServerResponse)
            }
            event = refreshed
            editedPlan = refreshed.payload.plan
            notice = "修改和拍摄细节已保存，请听一听或看一看，再确认这个版本。还没有制作视频。"
        } catch {
            notice = "您的修改已保存。拍摄细节尚未确认整理成功；可以读取已保存方案核对。继续整理会核对原来的请求，不会自动重复调用模型。"
        }
    }
}
