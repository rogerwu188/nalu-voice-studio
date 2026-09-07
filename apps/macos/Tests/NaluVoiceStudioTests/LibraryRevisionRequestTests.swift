import Foundation
import Testing
@testable import NaluVoiceStudio

struct LibraryRevisionRequestTests {
    @Test func spokenCorrectionRetainsIdentitySourcesAndExpectedRevision() throws {
        let revision: [String: Any] = ["entity_id": "grandma", "revision": 3, "name": "外婆",
            "description": "原来的完整描述", "attributes": ["aliases": ["奶奶"]],
            "source_asset_ids": ["photo-one"], "source_memory_ids": ["memory-one"],
            "source_channel": "voice", "change_summary": "原资料", "created_at": "2026-09-07T00:00:00Z"]
        let data = try JSONSerialization.data(withJSONObject: ["id": "grandma", "project_id": "project-one",
            "kind": "character", "stable_name": "外婆", "current_revision": 3, "confirmed_revision": 2,
            "current": revision, "created_at": "2026-09-07T00:00:00Z", "updated_at": "2026-09-07T00:00:00Z"])
        let entity = try JSONDecoder().decode(LibraryEntity.self, from: data)
        let draft = try #require(LibraryVoiceCorrection.draft(for: entity, description: "  新的完整描述  "))
        #expect(draft.name == "外婆")
        #expect(draft.description == "新的完整描述")
        #expect(draft.expectedCurrentRevision == 3)
        #expect(draft.sourceAssetIDs == ["photo-one"] && draft.sourceMemoryIDs == ["memory-one"])
        #expect(entity.current.description == "原来的完整描述" && entity.confirmedRevision == 2)
        #expect(LibraryVoiceCorrection.draft(for: entity, description: "   ") == nil)
        #expect(LibraryVoiceCorrection.draft(for: entity, description: String(repeating: "字", count: 10_001)) == nil)
        #expect(LibraryVoiceCorrection.requestsChange("不对，我要修改"))
        #expect(!LibraryVoiceCorrection.requestsChange("我确认这份项目设定"))
        #expect(!LibraryVoiceCorrection.requestsChange("取消修改"))
    }

    @Test func correctionCanBindTheVersionThatWasReadAloud() throws {
        var request = LibraryEntityRevisionDraft(name: "外婆", description: "用户重新口述的完整描述",
            attributes: [:], sourceAssetIDs: ["photo-one"], sourceMemoryIDs: ["memory-one"],
            sourceChannel: "voice", changeSummary: "语音修改，等待重新确认")
        let legacy = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as! [String: Any]
        #expect(legacy["expected_current_revision"] == nil)
        request.expectedCurrentRevision = 3
        let body = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as! [String: Any]
        #expect(body["expected_current_revision"] as? Int == 3)
        #expect(body["source_asset_ids"] as? [String] == ["photo-one"])
        #expect(body["source_memory_ids"] as? [String] == ["memory-one"])
        #expect(body["confirmed_revision"] == nil)
        let restored = try JSONDecoder().decode(LibraryEntityRevisionDraft.self, from: JSONEncoder().encode(request))
        #expect(restored.expectedCurrentRevision == 3)
    }
}
