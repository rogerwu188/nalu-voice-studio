import Foundation
import Testing
@testable import NaluVoiceStudio

private final class ShotReviewProtocol: URLProtocol, @unchecked Sendable {
    static var requests: [URLRequest] = []
    static var response = Data()
    static var status = 200
    static var queued: [(Int, Data)] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
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
