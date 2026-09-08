import Foundation

enum NovelImportControl: String, Sendable {
    case pause, resume

    static func parse(_ text: String) -> Self? {
        let value = text.filter { !$0.isWhitespace && !"，。！？,.!?".contains($0) }
        if ["暂停抓取", "停止抓取", "暂停下载小说", "先别抓取了", "暂停导入小说"].contains(value) { return .pause }
        if ["继续抓取", "恢复抓取", "继续下载小说", "继续导入小说", "恢复下载小说"].contains(value) { return .resume }
        return nil
    }
}

struct NovelImportStatus: Decodable, Sendable {
    struct Chapter: Decodable, Sendable {
        let url: String
        let title: String
        let status: String
    }
    let status: String
    let source_url: String
    let completed_chapters: Int
    let chapters: [Chapter]

    var progressText: String {
        "已保存 \(completed_chapters) / \(chapters.count) 章到这台 Mac"
    }
}

struct NovelImportDraft: Encodable {
    let source_url: String
}
