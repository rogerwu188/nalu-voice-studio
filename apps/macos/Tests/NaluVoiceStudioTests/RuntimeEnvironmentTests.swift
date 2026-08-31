import XCTest
@testable import NaluVoiceStudio

final class RuntimeEnvironmentTests: XCTestCase {
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
