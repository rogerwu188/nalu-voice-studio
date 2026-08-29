import XCTest
@testable import NaluVoiceStudio

final class MemoryCorrectionParserTests: XCTestCase {
    func testParsesPlainLanguageMemoryCorrections() {
        XCTAssertEqual(
            MemoryCorrectionParser.parse("地点不是西湖，是灵隐寺"),
            MemoryCorrection(field: .place, value: "灵隐寺")
        )
        XCTAssertEqual(
            MemoryCorrectionParser.parse("年份改成1980年春天"),
            MemoryCorrection(field: .approximateDate, value: "1980年春天")
        )
        XCTAssertEqual(
            MemoryCorrectionParser.parse("标题改为第一次全家旅行"),
            MemoryCorrection(field: .title, value: "第一次全家旅行")
        )
        XCTAssertNil(MemoryCorrectionParser.parse("我想再讲一段故事"))
    }
}

