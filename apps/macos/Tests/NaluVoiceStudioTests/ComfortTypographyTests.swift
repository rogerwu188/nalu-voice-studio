import XCTest
@testable import NaluVoiceStudio

final class ComfortTypographyTests: XCTestCase {
    func testEveryStyleActuallyGrowsAtEachComfortLevel() {
        for style in ComfortTextStyle.allCases {
            for level in 0..<3 {
                XCTAssertGreaterThan(style.pointSize(level: level + 1), style.pointSize(level: level))
            }
            XCTAssertEqual(style.pointSize(level: 1), style.baseSize)
            XCTAssertEqual(style.pointSize(level: 3), style.baseSize * 1.4, accuracy: 0.001)
        }
    }

    func testStoredOutOfRangeLevelsRemainBounded() {
        for style in ComfortTextStyle.allCases {
            XCTAssertEqual(style.pointSize(level: Int.min), style.pointSize(level: 0))
            XCTAssertEqual(style.pointSize(level: Int.max), style.pointSize(level: 3))
        }
    }
}
