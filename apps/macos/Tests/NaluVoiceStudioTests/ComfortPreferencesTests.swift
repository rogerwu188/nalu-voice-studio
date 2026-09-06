import XCTest
@testable import NaluVoiceStudio

final class ComfortPreferencesTests: XCTestCase {
    func testQAComfortPreferencesAreIsolatedAndPersistAcrossLoads() throws {
        let suite = "nalu-comfort-tests-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let directory = FileManager.default.temporaryDirectory
            .appending(path: "nalu-comfort-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let environment = ["NALU_ENABLE_LOCAL_QA": "1",
                           "NALU_LOCAL_QA_APPLICATION_SUPPORT": directory.path]
        var real = ComfortPreferences()
        real.textLevel = 3
        try ComfortPreferencesStore.save(real, inherited: [:], defaults: defaults)
        XCTAssertEqual(ComfortPreferencesStore.load(inherited: environment, defaults: defaults),
                       ComfortPreferences())
        var qa = ComfortPreferences()
        qa.textLevel = 0
        try ComfortPreferencesStore.save(qa, inherited: environment, defaults: defaults)
        XCTAssertEqual(ComfortPreferencesStore.load(inherited: environment, defaults: defaults), qa)
        XCTAssertEqual(ComfortPreferencesStore.load(inherited: [:], defaults: defaults), real)
    }

    func testInvalidQADoesNotReadOrWriteRealPreferences() throws {
        let suite = "nalu-comfort-invalid-\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        var real = ComfortPreferences()
        real.textLevel = 3
        try ComfortPreferencesStore.save(real, inherited: [:], defaults: defaults)
        let environment = ["NALU_ENABLE_LOCAL_QA": "1"]
        XCTAssertEqual(ComfortPreferencesStore.load(inherited: environment, defaults: defaults),
                       ComfortPreferences())
        XCTAssertThrowsError(try ComfortPreferencesStore.save(
            ComfortPreferences(), inherited: environment, defaults: defaults
        ))
        XCTAssertEqual(ComfortPreferencesStore.load(inherited: [:], defaults: defaults), real)
    }

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
