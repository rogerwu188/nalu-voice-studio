import Foundation
import XCTest
@testable import NaluVoiceStudio

final class EpisodeOutputHandoffTests: XCTestCase {
    func testQualityFailureDoesNotExposeProviderTextOrClaimApproval() {
        let repeated = EpisodeOutputQualityFailure(codes: ["video:VIDEO_FRAME_REPEAT_EXCESSIVE"])
        XCTAssertTrue(repeated.userMessage.contains("画面重复过多"))
        XCTAssertTrue(repeated.userMessage.contains("尚未验收"))
        let unknown = EpisodeOutputQualityFailure(codes: ["secret-file-path-private-diagnostic"])
        XCTAssertFalse(unknown.userMessage.contains("secret-file"))
        XCTAssertTrue(unknown.userMessage.contains("不是让您重新讲故事"))
    }
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
