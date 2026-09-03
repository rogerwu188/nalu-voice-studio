import Foundation
import XCTest
@testable import NaluVoiceStudio

final class ContinuityFormDraftTests: XCTestCase {
    func testStructuredDraftRoundTripsCharactersPropsAndHooks() {
        var draft = ContinuityFormDraft()
        draft.sceneLocation = "老火车站"
        draft.storyTime = "1986年冬夜"
        draft.weather = "大雪"
        draft.unresolvedHooks = "父亲的信还没有打开、姐姐没有说出真相"
        draft.characters = [
            ContinuityCharacterEntry(
                name: "林叔",
                location: "候车室",
                wardrobe: "蓝色外套、旧围巾",
                injuries: "左手包扎",
                heldProps: "旧皮箱",
                relationships: "小梅：已经和解的姐姐",
                revealedFacts: "父亲留下了一封信"
            )
        ]
        draft.props = [
            ContinuityPropEntry(
                name: "旧皮箱",
                owner: "林叔",
                location: "候车室",
                condition: "锁扣损坏"
            )
        ]

        XCTAssertTrue(draft.hasContent)
        XCTAssertEqual(draft.hooks, ["父亲的信还没有打开", "姐姐没有说出真相"])
        XCTAssertEqual(draft.state.characters["林叔"]?.wardrobe, ["蓝色外套", "旧围巾"])
        XCTAssertEqual(
            draft.state.characters["林叔"]?.relationships,
            ["小梅": "已经和解的姐姐"]
        )
        XCTAssertEqual(draft.state.props["旧皮箱"]?.owner, "林叔")

        let restored = ContinuityFormDraft(
            state: draft.state,
            unresolvedHooks: draft.hooks
        )
        XCTAssertEqual(restored.state, draft.state)
        XCTAssertEqual(restored.hooks, draft.hooks)
    }

    func testScriptRevisionDecodesBoundContinuityMetadata() throws {
        let data = Data(
            """
            {
              "episode_id": "ep-2",
              "revision": 3,
              "content": "第二集",
              "summary_for_voice_review": "从车站继续出发",
              "source_transcript": "",
              "narrative_metadata": {
                "opening_continuity": {"story_time": "1986年冬夜"}
              },
              "approved_at": null,
              "created_at": "2026-08-29T00:00:00Z"
            }
            """.utf8
        )

        let revision = try JSONDecoder().decode(ScriptRevision.self, from: data)
        guard case .object(let opening) = revision.narrativeMetadata["opening_continuity"] else {
            return XCTFail("expected opening continuity metadata")
        }
        XCTAssertEqual(opening["story_time"], .string("1986年冬夜"))
        XCTAssertNil(revision.authoringProvenance)
    }

    func testScriptDraftDeclaresOriginAndResponseDecodesProvenance() throws {
        let draft = ScriptRevisionDraft(
            content: "用户键盘输入",
            summaryForVoiceReview: "用户输入",
            sourceTranscript: "",
            narrativeMetadata: [:],
            authoring: ScriptAuthoringDraft(origin: "user_text")
        )
        let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(draft))
        let object = try XCTUnwrap(encoded as? [String: Any])
        let authoring = try XCTUnwrap(object["authoring"] as? [String: Any])
        XCTAssertEqual(authoring["origin"] as? String, "user_text")

        let digest = String(repeating: "a", count: 64)
        let data = Data(
            """
            {
              "episode_id": "ep-3",
              "revision": 1,
              "content": "用户键盘输入",
              "summary_for_voice_review": "用户输入",
              "source_transcript": "",
              "narrative_metadata": {},
              "authoring_provenance": {
                "schema_version": "nalu.script-authoring-provenance/v1",
                "origin": "user_text",
                "content_sha256": "\(digest)",
                "source_transcript_sha256": "\(digest)",
                "external_writer": null,
                "verification_status": "user_attested",
                "writer_receipt_verified": false,
                "network_call_performed_by_runtime": false,
                "provenance_sha256": "\(digest)"
              },
              "approved_at": null,
              "created_at": "2026-09-03T00:00:00Z"
            }
            """.utf8
        )
        let revision = try JSONDecoder().decode(ScriptRevision.self, from: data)
        XCTAssertEqual(revision.authoringProvenance?.origin, "user_text")
        XCTAssertEqual(revision.authoringProvenance?.verificationStatus, "user_attested")
        XCTAssertFalse(revision.authoringProvenance?.writerReceiptVerified ?? true)
    }
}
