import XCTest
@testable import NaluVoiceStudio

final class RuntimeEnvironmentTests: XCTestCase {
    func testAlternatePortRequiresIsolatedQA() throws {
        XCTAssertEqual(try RuntimeEndpointConfiguration.port(inherited: [
            "NALU_LOCAL_QA_PORT": "18766",
        ]), 8765)
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        var env = [
            "NALU_ENABLE_LOCAL_QA": "1",
            "NALU_LOCAL_QA_APPLICATION_SUPPORT": root.path,
            "NALU_LOCAL_QA_PORT": "18766",
        ]
        XCTAssertEqual(try RuntimeEndpointConfiguration.baseURL(inherited: env).absoluteString,
                       "http://127.0.0.1:18766")
        for invalid in ["8765", "80", "65536", "018766", " 18766", ""] {
            env["NALU_LOCAL_QA_PORT"] = invalid
            XCTAssertThrowsError(try RuntimeEndpointConfiguration.port(inherited: env))
        }
        env["NALU_LOCAL_QA_PORT"] = "18766"
        env["NALU_LOCAL_QA_APPLICATION_SUPPORT"] = "/Users/example/data"
        XCTAssertThrowsError(try RuntimeEndpointConfiguration.port(inherited: env))
    }

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

    func testRuntimeProcessTerminatorWaitsForChildExit() throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/sleep")
        process.arguments = ["30"]
        try process.run()

        RuntimeProcessTerminator.stop(process)

        XCTAssertFalse(process.isRunning)
    }

    func testColdUniversalRuntimeGetsBoundedOlderMacStartupWindow() {
        XCTAssertEqual(RuntimeStartupPolicy.pollIntervalMilliseconds, 100)
        XCTAssertEqual(RuntimeStartupPolicy.maximumWaitSeconds, 180)
        XCTAssertEqual(RuntimeStartupPolicy.maximumAttempts, 1_800)
    }

    func testOnlyRuntimeOwnedByThisSupervisorCanBeReused() throws {
        XCTAssertEqual(
            try RuntimeReusePolicy.decide(
                supervisorReady: true,
                managedProcessRunning: true,
                loopbackRuntimeHealthy: true,
                localQAEnabled: false
            ),
            .useManagedRuntime
        )
        XCTAssertEqual(
            try RuntimeReusePolicy.decide(
                supervisorReady: false,
                managedProcessRunning: false,
                loopbackRuntimeHealthy: false,
                localQAEnabled: false
            ),
            .startBundledRuntime
        )

        XCTAssertThrowsError(
            try RuntimeReusePolicy.decide(
                supervisorReady: false,
                managedProcessRunning: false,
                loopbackRuntimeHealthy: true,
                localQAEnabled: false
            )
        ) { error in
            guard case RuntimeSupervisorError.unmanagedRuntimeAlreadyRunning = error else {
                return XCTFail("unexpected error: \(error)")
            }
        }
        XCTAssertThrowsError(
            try RuntimeReusePolicy.decide(
                supervisorReady: false,
                managedProcessRunning: false,
                loopbackRuntimeHealthy: true,
                localQAEnabled: true
            )
        ) { error in
            guard case RuntimeSupervisorError.localQARuntimeAlreadyRunning = error else {
                return XCTFail("unexpected error: \(error)")
            }
        }
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
        XCTAssertEqual(
            environment["NALU_SEMANTIC_RECOGNIZER_BINARY"],
            "/Applications/Nalu.app/Contents/Resources/recognizers/nalu-semantic-recognizer"
        )
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
