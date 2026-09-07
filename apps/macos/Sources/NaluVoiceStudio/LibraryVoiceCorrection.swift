import Foundation

enum LibraryVoiceCorrection {
    static func requestsChange(_ text: String) -> Bool {
        ["我要修改", "我想修改", "改一下", "改一改", "说错了", "不对", "修改人物"].contains(where: text.contains)
    }

    static func draft(for entity: LibraryEntity, description: String) -> LibraryEntityRevisionDraft? {
        let text = description.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, text.count <= 10_000 else { return nil }
        return LibraryEntityRevisionDraft(name: entity.current.name, description: text,
            attributes: entity.current.attributes, sourceAssetIDs: entity.current.sourceAssetIDs,
            sourceMemoryIDs: entity.current.sourceMemoryIDs, sourceChannel: "voice",
            changeSummary: "用户重新口述完整描述，另存版本并等待确认",
            expectedCurrentRevision: entity.currentRevision)
    }
}
