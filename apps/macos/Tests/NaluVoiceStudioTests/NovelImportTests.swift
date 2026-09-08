import XCTest
@testable import NaluVoiceStudio

final class NovelImportTests: XCTestCase {
    func testImportControlsAreNotStoryText() {
        XCTAssertEqual(NovelImportControl.parse("暂停抓取。"), .pause)
        XCTAssertEqual(NovelImportControl.parse("继续下载小说！"), .resume)
        XCTAssertEqual(NovelImportControl.parse(" 恢复 抓取 "), .resume)
        for text in ["爷爷说暂停抓取", "不要继续抓取", "继续讲故事", "停止制作视频", "下载小说并发布"] {
            XCTAssertNil(NovelImportControl.parse(text), text)
        }
    }
}
