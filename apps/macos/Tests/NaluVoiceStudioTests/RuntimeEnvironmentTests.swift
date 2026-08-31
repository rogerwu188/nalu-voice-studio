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
}
