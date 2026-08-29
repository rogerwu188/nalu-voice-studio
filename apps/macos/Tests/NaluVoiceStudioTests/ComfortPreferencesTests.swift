import XCTest
@testable import NaluVoiceStudio

final class ComfortPreferencesTests: XCTestCase {
    func testExplicitComfortCommandsAreBoundedAndReversible() {
        var preferences = ComfortPreferences()

        XCTAssertNotNil(preferences.consume("我看不清字，请字大一点"))
        XCTAssertEqual(preferences.textLevel, 2)
        _ = preferences.consume("字大一点")
        _ = preferences.consume("字大一点")
        XCTAssertEqual(preferences.textLevel, 3)

        let originalRate = preferences.speechRate
        XCTAssertNotNil(preferences.consume("请说慢一点"))
        XCTAssertLessThan(preferences.speechRate, originalRate)

        XCTAssertNotNil(preferences.consume("恢复舒适设置"))
        XCTAssertEqual(preferences, ComfortPreferences())
        XCTAssertNil(preferences.consume("这是故事里的一句话"))
    }
}
