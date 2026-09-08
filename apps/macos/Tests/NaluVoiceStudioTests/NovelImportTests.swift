import XCTest
@testable import NaluVoiceStudio

final class NovelImportTests: XCTestCase {
    func testResumePreservesOnlySameSourceWritingRequest() {
        let url = "https://example.org/book"
        let original = "导入小说 \(url)，然后生成分集剧本草稿"
        let resumed = NovelImportControl.resumeQuery(sourceURL: url, previousRequest: original)
        XCTAssertTrue(AssistantActionRouter.requestsSourceWriting(resumed))
        XCTAssertEqual(NovelImportControl.resumeQuery(sourceURL: url, previousRequest: resumed), resumed)
        for request in [nil, "导入小说 \(url)", "导入小说 https://example.org/other，然后生成分集剧本草稿"] as [String?] {
            XCTAssertEqual(NovelImportControl.resumeQuery(sourceURL: url, previousRequest: request),
                           "继续导入小说 " + url)
        }
    }
    func testNaturalNovelWritingSearchRequiresActualImport() {
        for text in ["找一本小说，拿来写剧本", "网上找到这个小说，把它作为整个剧本", "帮我找小说改编成连续剧"] {
            XCTAssertTrue(AssistantActionRouter.requestsNovelImport(text), text)
            XCTAssertEqual(AssistantActionRouter.route(text), .webResearch(query: text))
        }
        for text in ["只查小说在哪里", "不要下载小说", "搜索小说然后发布", "找这篇文章作为剧本"] {
            XCTAssertFalse(AssistantActionRouter.requestsNovelImport(text), text)
        }
        let choice = NovelSourceChoice(sources: [.init(title: "目录", url: URL(string: "https://example.org/book")!)], writingRequested: true)
        let query = choice.importQuery(for: "第一个")!
        XCTAssertTrue(AssistantActionRouter.requestsNovelImport(query))
        XCTAssertTrue(AssistantActionRouter.requestsSourceWriting(query))
        XCTAssertEqual(AssistantActionRouter.sourceURL(in: query), "https://example.org/book")
    }
    func testSourceSelectionRequiresExplicitExistingChoice() {
        let choice = NovelSourceChoice(sources: [
            .init(title: "目录", url: URL(string: "https://example.org/book")!)
        ], writingRequested: true)
        XCTAssertEqual(choice.importQuery(for: "选择第一个。"),
            "导入小说 https://example.org/book，然后生成分集剧本草稿")
        for text in ["第二个", "不要选择第一个", "爷爷说第一个", "第一个并发布", "好的"] {
            XCTAssertNil(choice.importQuery(for: text))
        }
        XCTAssertTrue(choice.prompt.contains("还没有抓取正文"))
        let importOnly = NovelSourceChoice(sources: choice.sources, writingRequested: false)
        XCTAssertEqual(importOnly.importQuery(for: "用第一个"), "导入小说 https://example.org/book")
    }
    func testImportControlsAreNotStoryText() {
        XCTAssertEqual(NovelImportControl.parse("暂停抓取。"), .pause)
        XCTAssertEqual(NovelImportControl.parse("继续下载小说！"), .resume)
        XCTAssertEqual(NovelImportControl.parse(" 恢复 抓取 "), .resume)
        for text in ["爷爷说暂停抓取", "不要继续抓取", "继续讲故事", "停止制作视频", "下载小说并发布"] {
            XCTAssertNil(NovelImportControl.parse(text), text)
        }
    }
}
