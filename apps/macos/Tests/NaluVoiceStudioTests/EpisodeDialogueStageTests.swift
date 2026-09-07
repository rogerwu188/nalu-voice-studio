import CryptoKit
import Foundation
import Testing
@testable import NaluVoiceStudio

private final class DialogueProtocol: URLProtocol, @unchecked Sendable {
    static var responses: [(Int, Data, [String: String])] = []
    static var requests: [URLRequest] = []
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
        let (status, data, headers) = Self.responses.removeFirst()
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status,
            httpVersion: nil, headerFields: headers)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct EpisodeDialogueStageTests {
    @MainActor @Test func failedStagingRetriesExactVersionWithoutAnotherExport() async throws {
        let sha = String(repeating: "a", count: 64)
        let sound = try JSONDecoder().decode(EpisodeSoundPlan.self, from: JSONSerialization.data(withJSONObject: [
            "id": "sound", "run_id": "run", "event_type": "episode_sound_plan_drafted",
            "payload": ["episode_id": "episode", "edit_id": "edit", "edit_sha256": sha, "plan_id": "plan",
                "plan_sha256": sha, "sound_plan_sha256": sha, "duration_seconds": 1,
                "cues": [["shot_index": 0, "start_seconds": 0, "end_seconds": 1,
                          "dialogue_or_narration": "海边", "sound_direction": "海浪"]],
                "caption_srt_draft": "", "caption_timing_basis": "draft", "audio_generated": false,
                "captions_approved": false, "speech_alignment_verified": false, "edit_approved": true,
                "edit_review_id": "review", "generation_performed": false, "master_accepted": false]]))
        let captions = Data("WEBVTT\n\n00:00:00.100 --> 00:00:00.900\n海边\n".utf8)
        let captionSHA = SHA256.hash(data: captions).map { String(format: "%02x", $0) }.joined()
        let preparation = EpisodeDialoguePreparation(draft: .init(sound_plan_id: "sound",
            expected_sound_plan_sha256: sha, expected_lineage_sha256: sha), captionsSHA256: captionSHA)
        var files: [String: Any] = [:]
        for name in ["dialogue.wav", "captions.vtt", "lineage.json"] {
            files[name] = ["relative_path": "provider-results/adopted-dialogue/\(sha)/\(name)",
                           "sha256": name == "captions.vtt" ? captionSHA : sha, "byte_size": 100]
        }
        let receipt: [String: Any] = ["id": "stage", "run_id": "run", "event_type": "episode_dialogue_staged",
            "payload": ["run_id": "run", "staging_sha256": sha, "master_accepted": false, "files": files,
                "lineage": ["sound_plan_id": "sound", "sound_plan_sha256": sha, "lineage_sha256": sha,
                    "dialogue_sha256": sha, "captions_sha256": captionSHA, "master_accepted": false,
                    "speech_alignment_verified": false, "other_audio_layers_generated": false]]]
        let data = try JSONSerialization.data(withJSONObject: receipt)
        let decoded = try JSONDecoder().decode(EpisodeDialogueStageReceipt.self, from: data)
        try decoded.validate(runID: "run", preparation: preparation)
        #expect(throws: (any Error).self) { try decoded.validate(runID: "foreign", preparation: preparation) }
        #expect(throws: (any Error).self) {
            try decoded.validate(runID: "run", preparation: .init(draft: preparation.draft, captionsSHA256: sha))
        }
        DialogueProtocol.requests = []
        DialogueProtocol.bodies = []
        DialogueProtocol.responses = [(200, captions, ["X-Nalu-Sound-Plan-ID": "sound",
            "X-Nalu-Master-Accepted": "false", "X-Nalu-Lineage-SHA256": sha, "X-Nalu-Artifact-SHA256": captionSHA]),
            (503, Data(), [:]), (200, data, [:])]
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [DialogueProtocol.self]
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: configuration), accessCheck: { true })
        let model = EpisodeDialogueStageModel(sound: sound, runtime: runtime)
        #expect(DialogueProtocol.requests.isEmpty)
        await model.prepare()
        #expect(model.pending?.draft == preparation.draft && model.receipt == nil && !model.busy)
        await model.prepare()
        #expect(model.pending == nil && model.receipt?.id == "stage")
        #expect(model.notice.contains("视频尚未完成"))
        #expect(DialogueProtocol.requests.map(\.httpMethod) == ["GET", "POST", "POST"])
        #expect(DialogueProtocol.requests[1].url == DialogueProtocol.requests[2].url)
        #expect(try JSONDecoder().decode(EpisodeDialogueStageDraft.self, from: DialogueProtocol.bodies[1]) == preparation.draft)
        #expect(try JSONDecoder().decode(EpisodeDialogueStageDraft.self, from: DialogueProtocol.bodies[2]) == preparation.draft)
        #expect(DialogueProtocol.requests.allSatisfy { $0.value(forHTTPHeaderField: "X-Nalu-Writer-Key") == nil })
        model.refreshCurrentVersion()
        #expect(model.receipt == nil && model.pending == nil)
    }
}
