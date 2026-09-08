import Foundation
import Testing
@testable import NaluVoiceStudio

private final class OutputProtocol: URLProtocol, @unchecked Sendable {
    static var responses: [(Int, Data)] = []
    static var paths: [String] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.paths.append(request.url!.lastPathComponent)
        guard !Self.responses.isEmpty else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse)); return
        }
        let (status, data) = Self.responses.removeFirst()
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor func verifyOutputTransport(_ mix: EpisodePreparedMix) async throws {
    let sha = String(repeating: "a", count: 64)
    func encode(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value) }
    var rendered: [String: Any] = ["schema_version": "nalu.postproduction-materialization/v1",
        "run_id": mix.runID, "episode_id": mix.episodeID, "plan_sha256": sha, "result_sha256": sha]
    for (field, kind) in ["master": "master_video", "captions": "captions",
                          "shot_manifest": "shot_manifest", "postproduction_manifest": "postproduction_manifest"] {
        rendered[field] = ["kind": kind, "relative_path": "render/\(field)", "media_type": "application/octet-stream", "sha256": sha]
    }
    let report: [String: Any] = ["run_id": mix.runID, "output_seal_sha256": sha,
                                "master_sha256": sha, "status": "PASS"]
    for mode in ["success", "quality", "missingRepair", "wrongMaster"] {
        OutputProtocol.paths = []
        OutputProtocol.responses = [(201, try encode(rendered)),
            (201, try encode(["run_id": mix.runID, "manifest_sha256": sha])),
            (200, try encode(report))]
        var decoded = report
        if mode == "wrongMaster" { decoded["master_sha256"] = String(repeating: "b", count: 64) }
        if mode == "quality" || mode == "missingRepair" {
            decoded["status"] = "FAIL"
            decoded["failures"] = ["video:VIDEO_FRAME_REPEAT_EXCESSIVE"]
        }
        OutputProtocol.responses.append((200, try encode(decoded)))
        if mode == "quality" {
            OutputProtocol.responses.append((200, try encode([
                "schema_version": "nalu.postproduction-repair-plan/v1", "run_id": mix.runID,
                "output_seal_sha256": sha, "master_sha256": sha, "plan_sha256": sha,
                "repair_tasks": [["code": "frame_repeat", "target": "video", "issue": "repeat",
                                  "required_action": "repair", "release_blocking": true]]])))
        } else if mode == "missingRepair" {
            OutputProtocol.responses.append((503, Data()))
        }
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [OutputProtocol.self]
        let session = URLSession(configuration: config)
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!, session: session, accessCheck: { true })
        do {
            _ = try await runtime.renderEpisodeMix(mix)
            #expect(mode == "success")
        } catch let failure as EpisodeOutputQualityFailure {
            #expect(mode == "quality" || mode == "missingRepair")
            #expect(failure.repeatedFrames)
            #expect((failure.repairPlan != nil) == (mode == "quality"))
        } catch {
            #expect(mode == "wrongMaster")
        }
        #expect(OutputProtocol.responses.isEmpty)
        #expect(Array(OutputProtocol.paths.prefix(4)) == ["postproduction-materializations", "rendered-output-seal", "media-structure-qa", "decoded-media-qa"])
        #expect(OutputProtocol.paths.count == ((mode == "quality" || mode == "missingRepair") ? 5 : 4))
        session.invalidateAndCancel()
    }
}
