import Foundation
import XCTest
@testable import NaluVoiceStudio

final class EpisodeOutputHandoffTests: XCTestCase {
    func testRequiresAllFourArtifactsAndSafePaths() throws {
        let sha = String(repeating: "a", count: 64)
        var object: [String: Any] = [:]
        for (field, kind) in ["master": "master_video", "captions": "captions",
                              "postproduction_manifest": "postproduction_manifest", "shot_manifest": "shot_manifest"] {
            object[field] = ["kind": kind, "relative_path": "render/\(field)",
                             "sha256": sha, "media_type": "application/octet-stream"]
        }
        func data() throws -> Data { try JSONSerialization.data(withJSONObject: object) }
        let plan = try EpisodeOutputHandoff(materialization: data())
        XCTAssertEqual(plan.masterSHA, sha)
        XCTAssertEqual(plan.body, try EpisodeOutputHandoff(materialization: data()).body)
        let body = try JSONSerialization.jsonObject(with: plan.body) as! [String: Any]
        XCTAssertEqual((body["artifacts"] as? [[String: String]])?.count, 4)
        object.removeValue(forKey: "shot_manifest")
        XCTAssertThrowsError(try EpisodeOutputHandoff(materialization: data()))
        object["shot_manifest"] = ["kind": "shot_manifest", "relative_path": "../outside",
                                   "sha256": sha, "media_type": "application/json"]
        XCTAssertThrowsError(try EpisodeOutputHandoff(materialization: data()))
    }
}
