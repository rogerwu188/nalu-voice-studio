import XCTest
@testable import NaluVoiceStudio

final class LibraryEntityModelTests: XCTestCase {
    func testCreateDraftUsesRuntimeContractKeys() throws {
        let draft = LibraryEntityCreateDraft(
            kind: "character",
            name: "林叔",
            description: "戴旧眼镜，穿蓝色外套。",
            attributes: [:],
            sourceAssetIDs: [],
            sourceMemoryIDs: [],
            sourceChannel: "voice",
            changeSummary: "用户语音建立草稿"
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(draft))
                as? [String: Any]
        )
        XCTAssertEqual(object["source_channel"] as? String, "voice")
        XCTAssertEqual(object["change_summary"] as? String, "用户语音建立草稿")
        XCTAssertNotNil(object["source_asset_ids"])
        XCTAssertNil(object["sourceChannel"])
    }

    func testLibraryEntityDecodesConfirmationState() throws {
        let data = Data(
            """
            {
              "id":"lib_1","project_id":"prj_1","kind":"character",
              "stable_name":"林叔","current_revision":2,"confirmed_revision":1,
              "current":{
                "entity_id":"lib_1","revision":2,"name":"林叔",
                "description":"第二版人物设定","attributes":{},
                "source_asset_ids":[],"source_memory_ids":[],
                "source_channel":"voice","change_summary":"补充衣着",
                "created_at":"2026-08-29T00:00:00Z"
              },
              "created_at":"2026-08-29T00:00:00Z",
              "updated_at":"2026-08-29T00:01:00Z"
            }
            """.utf8
        )
        let entity = try JSONDecoder().decode(LibraryEntity.self, from: data)
        XCTAssertEqual(entity.currentRevision, 2)
        XCTAssertEqual(entity.confirmedRevision, 1)
        XCTAssertNotEqual(entity.currentRevision, entity.confirmedRevision)
    }
}
