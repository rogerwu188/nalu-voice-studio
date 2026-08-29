import AppKit
import Foundation
import Observation

@MainActor
@Observable
final class RuntimeSupervisor {
    static let shared = RuntimeSupervisor()

    private(set) var isReady = false
    private var process: Process?
    private var terminationObserver: NSObjectProtocol?

    private init() {
        terminationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.process?.terminate()
        }
    }

    func start() async throws {
        if await runtimeIsHealthy() {
            isReady = true
            return
        }
        guard let resources = Bundle.main.resourceURL else {
            throw RuntimeSupervisorError.resourcesMissing
        }
        let executable = resources.appending(path: "runtime/nalu-runtime")
        guard FileManager.default.isExecutableFile(atPath: executable.path) else {
            throw RuntimeSupervisorError.runtimeMissing(executable.path)
        }

        let applicationSupport = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        ).appending(path: "Nalu Voice Studio", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(
            at: applicationSupport, withIntermediateDirectories: true
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o700], ofItemAtPath: applicationSupport.path
        )

        let process = Process()
        process.executableURL = executable
        process.environment = RuntimeEnvironmentBuilder.build(
            inherited: ProcessInfo.processInfo.environment,
            applicationSupport: applicationSupport,
            resources: resources
        )
        try process.run()
        self.process = process

        // The bundled one-file Runtime may need several seconds to unpack on a
        // cold Mac. Keep polling quickly, but allow enough room for first launch.
        for _ in 0..<300 {
            if await runtimeIsHealthy() {
                isReady = true
                return
            }
            if !process.isRunning { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        process.terminate()
        throw RuntimeSupervisorError.startupTimedOut
    }

    private func runtimeIsHealthy() async -> Bool {
        guard let url = URL(string: "http://127.0.0.1:8765/health") else { return false }
        var request = URLRequest(url: url)
        request.timeoutInterval = 0.5
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
}

enum RuntimeSupervisorError: LocalizedError {
    case resourcesMissing
    case runtimeMissing(String)
    case startupTimedOut

    var errorDescription: String? {
        switch self {
        case .resourcesMissing: "应用资源目录不存在。"
        case .runtimeMissing(let path): "内置制片厂 Runtime 不存在：\(path)"
        case .startupTimedOut: "内置制片厂启动超时。"
        }
    }
}
