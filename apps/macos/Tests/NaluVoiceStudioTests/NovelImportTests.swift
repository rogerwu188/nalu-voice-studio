import XCTest
@testable import NaluVoiceStudio

final class NovelImportTests: XCTestCase {
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
