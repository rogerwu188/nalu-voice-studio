import Foundation
import Testing
@testable import NaluVoiceStudio

private final class ShotReviewProtocol: URLProtocol, @unchecked Sendable {
    static var requests: [URLRequest] = []
    static var response = Data()
    static var status = 200
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.response)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized)
struct EpisodeShotPlanTests {
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
