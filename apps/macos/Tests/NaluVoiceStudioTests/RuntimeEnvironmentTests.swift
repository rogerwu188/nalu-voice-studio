import XCTest
@testable import NaluVoiceStudio

final class RuntimeEnvironmentTests: XCTestCase {
    @MainActor
    func testApplicationTerminationStopsRuntimeSynchronously() {
        let notificationCenter = NotificationCenter()
        let notificationName = Notification.Name("NaluRuntimeTerminationTest")
        var events = ["before"]
        let signal = RuntimeTerminationSignal(
            notificationCenter: notificationCenter,
            notificationName: notificationName
        ) {
            events.append("terminated")
        }

        notificationCenter.post(name: notificationName, object: nil)
        events.append("after")

        XCTAssertEqual(events, ["before", "terminated", "after"])
        withExtendedLifetime(signal) {}
    }

    func testColdUniversalRuntimeGetsBoundedOlderMacStartupWindow() {
        XCTAssertEqual(RuntimeStartupPolicy.pollIntervalMilliseconds, 100)
        XCTAssertEqual(RuntimeStartupPolicy.maximumWaitSeconds, 180)
        XCTAssertEqual(RuntimeStartupPolicy.maximumAttempts, 1_800)
    }

    func testRuntimeEnvironmentDoesNotInheritSecrets() {
        let environment = RuntimeEnvironmentBuilder.build(
            inherited: [
                "PATH": "/usr/bin",
                "OPENAI_API_KEY": "must-not-leak",
                "PRIVATE_TOKEN": "must-not-leak",
                "LANG": "zh_CN.UTF-8",
            ],
            applicationSupport: URL(fileURLWithPath: "/tmp/Nalu Support"),
            resources: URL(fileURLWithPath: "/Applications/Nalu.app/Contents/Resources")
        )
        XCTAssertEqual(environment["PATH"], "/usr/bin")
        XCTAssertEqual(environment["LANG"], "zh_CN.UTF-8")
        XCTAssertNil(environment["OPENAI_API_KEY"])
        XCTAssertNil(environment["PRIVATE_TOKEN"])
        XCTAssertEqual(environment["NALU_DATABASE_PATH"], "/tmp/Nalu Support/nalu.sqlite3")
    }

    func testLocalQARootRequiresExplicitFlagAndExistingTemporaryDirectory() throws {
        let fileManager = FileManager.default
        let temporaryRoot = fileManager.temporaryDirectory
            .appending(path: "nalu-runtime-root-tests-\(UUID().uuidString)", directoryHint: .isDirectory)
        let fixture = temporaryRoot.appending(path: "fixture", directoryHint: .isDirectory)
        try fileManager.createDirectory(at: fixture, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: temporaryRoot) }
        let defaultURL = URL(fileURLWithPath: "/Users/example/Library/Application Support/Nalu Voice Studio")

        XCTAssertEqual(
            try RuntimeApplicationSupportResolver.resolve(
                inherited: [RuntimeApplicationSupportResolver.localQAPath: fixture.path],
                defaultURL: defaultURL,
                temporaryDirectory: temporaryRoot
            ),
            defaultURL
        )
        XCTAssertEqual(
            try RuntimeApplicationSupportResolver.resolve(
                inherited: [
                    RuntimeApplicationSupportResolver.localQAFlag: "1",
                    RuntimeApplicationSupportResolver.localQAPath: fixture.path,
                ],
                defaultURL: defaultURL,
                temporaryDirectory: temporaryRoot
            ),
            fixture.standardizedFileURL.resolvingSymlinksInPath()
        )
    }

    func testLocalQARootFailsClosedOutsideTemporaryDirectory() throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appending(path: "nalu-runtime-root-tests-\(UUID().uuidString)", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        XCTAssertThrowsError(
            try RuntimeApplicationSupportResolver.resolve(
                inherited: [
                    RuntimeApplicationSupportResolver.localQAFlag: "1",
                    RuntimeApplicationSupportResolver.localQAPath: "/Users/example/Nalu QA",
                ],
                defaultURL: URL(fileURLWithPath: "/tmp/default"),
                temporaryDirectory: temporaryRoot
            )
        )
        XCTAssertThrowsError(
            try RuntimeApplicationSupportResolver.resolve(
                inherited: [RuntimeApplicationSupportResolver.localQAFlag: "1"],
                defaultURL: URL(fileURLWithPath: "/tmp/default"),
                temporaryDirectory: temporaryRoot
            )
        )
    }
}
