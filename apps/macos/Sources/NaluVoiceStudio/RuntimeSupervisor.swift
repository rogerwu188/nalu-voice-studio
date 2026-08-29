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

        let process = Process()
        process.executableURL = executable
        var environment = ProcessInfo.processInfo.environment
        environment["NALU_DATA_ROOT"] = applicationSupport.appending(path: "data").path
        environment["NALU_DATABASE_PATH"] = applicationSupport.appending(path: "nalu.sqlite3").path
        environment["NALU_REPOSITORY_ROOT"] = resources
            .appending(path: "runtime-resources").path
        process.environment = environment
        try process.run()
        self.process = process

        for _ in 0..<80 {
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
