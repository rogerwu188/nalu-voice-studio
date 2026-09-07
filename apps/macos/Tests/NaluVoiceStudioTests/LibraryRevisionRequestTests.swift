import Foundation
import Testing
@testable import NaluVoiceStudio

struct LibraryRevisionRequestTests {
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
