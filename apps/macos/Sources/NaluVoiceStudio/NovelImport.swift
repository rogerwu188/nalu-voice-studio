import Foundation

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
