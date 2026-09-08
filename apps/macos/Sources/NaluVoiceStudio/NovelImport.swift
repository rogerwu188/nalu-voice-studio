import Foundation

struct NovelSourceChoice: Codable, Equatable, Sendable {
    let sources: [WebResearchSource]
    let writingRequested: Bool

    func importQuery(for text: String) -> String? {
        let value = text.filter { !$0.isWhitespace && !"，。！？,.!?".contains($0) }
        let choices = ["第一个", "第二个", "第三个", "第四个", "第五个"]
        guard let index = choices.firstIndex(where: {
            value == $0 || value == "选择" + $0 || value == "用" + $0
        }), sources.indices.contains(index) else { return nil }
        return "导入小说 " + sources[index].url.absoluteString
            + (writingRequested ? "，然后生成分集剧本草稿" : "")
    }

    var prompt: String {
        "找到以下候选来源，还没有抓取正文。请说‘选择第一个’或其他编号，也可以提供另一个网址：\n"
            + sources.enumerated().map { "\($0.offset + 1). \($0.element.title) — \($0.element.url.absoluteString)" }.joined(separator: "\n")
    }
}

enum NovelImportControl: String, Sendable {
    case pause, resume

    static func resumeQuery(sourceURL: String, previousRequest: String?) -> String {
        let writingRequested = previousRequest.map {
            AssistantActionRouter.sourceURL(in: $0) == sourceURL
                && AssistantActionRouter.requestsSourceWriting($0)
        } ?? false
        return "继续导入小说 " + sourceURL
            + (writingRequested ? "，然后生成分集剧本草稿" : "")
    }

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
