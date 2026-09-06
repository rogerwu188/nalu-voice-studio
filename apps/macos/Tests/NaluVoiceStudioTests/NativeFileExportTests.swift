import XCTest
@testable import NaluVoiceStudio

final class NativeFileExportTests: XCTestCase {
    func testSuggestedFilenameKeepsReadableProjectTitle() {
        XCTAssertEqual(
            NativeFileExport.suggestedFilename(
                title: "海边的外婆（第一季）",
                suffix: "Nalu备份.json"
            ),
            "海边的外婆（第一季）-Nalu备份.json"
        )
    }

    func testSuggestedFilenameCannotTurnTitleIntoAPath() {
        XCTAssertEqual(
            NativeFileExport.suggestedFilename(
                title: "  ../家庭/故事:\n第一季  ",
                suffix: "Nalu备份.json"
            ),
            "家庭-故事- 第一季-Nalu备份.json"
        )
    }

    func testSuggestedFilenameUsesFallbackAndBoundsLongTitles() {
        XCTAssertEqual(
            NativeFileExport.suggestedFilename(title: " /:\n ", suffix: "Nalu隐私包.zip"),
            "Nalu项目-Nalu隐私包.zip"
        )
        let filename = NativeFileExport.suggestedFilename(
            title: String(repeating: "海", count: 120),
            suffix: "Nalu备份.json"
        )
        XCTAssertEqual(filename.filter { $0 == "海" }.count, 80)
        XCTAssertTrue(filename.hasSuffix("-Nalu备份.json"))
    }
}
