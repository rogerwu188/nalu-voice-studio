import AppKit
import Foundation
import Observation

enum RuntimeStartupPolicy {
    static let pollIntervalMilliseconds: Int64 = 100
    static let maximumWaitSeconds = 180
    static let maximumAttempts =
        maximumWaitSeconds * 1_000 / Int(pollIntervalMilliseconds)
}

enum RuntimeReuseDecision: Equatable {
    case useManagedRuntime
    case startBundledRuntime
}

enum RuntimeReusePolicy {
    static func decide(
        supervisorReady: Bool,
        managedProcessRunning: Bool,
        loopbackRuntimeHealthy: Bool,
        localQAEnabled: Bool
    ) throws -> RuntimeReuseDecision {
        if supervisorReady && managedProcessRunning && loopbackRuntimeHealthy {
            return .useManagedRuntime
        }
        if loopbackRuntimeHealthy {
            throw localQAEnabled
                ? RuntimeSupervisorError.localQARuntimeAlreadyRunning
                : RuntimeSupervisorError.unmanagedRuntimeAlreadyRunning
        }
        return .startBundledRuntime
    }
}

enum RuntimeProcessTerminator {
    static let gracefulWaitAttempts = 100
    static let waitIntervalSeconds = 0.05

    static func stop(_ process: Process) {
        guard process.isRunning else { return }
        process.terminate()
        waitForExit(process)
        if process.isRunning {
            process.interrupt()
            waitForExit(process)
        }
    }

    private static func waitForExit(_ process: Process) {
        for _ in 0..<gracefulWaitAttempts where process.isRunning {
            Thread.sleep(forTimeInterval: waitIntervalSeconds)
        }
    }
}

enum RuntimeApplicationSupportResolver {
    static let localQAFlag = "NALU_ENABLE_LOCAL_QA"
    static let localQAPath = "NALU_LOCAL_QA_APPLICATION_SUPPORT"

    static func resolve(
        inherited: [String: String],
        defaultURL: URL,
        temporaryDirectory: URL = FileManager.default.temporaryDirectory,
        fileManager: FileManager = .default
    ) throws -> URL {
        guard inherited[localQAFlag] == "1" else { return defaultURL }
        guard let rawPath = inherited[localQAPath], !rawPath.isEmpty else {
            throw RuntimeApplicationSupportError.missingLocalQAPath
        }

        let candidate = URL(fileURLWithPath: rawPath, isDirectory: true)
            .standardizedFileURL.resolvingSymlinksInPath()
        let temporaryRoot = temporaryDirectory.standardizedFileURL.resolvingSymlinksInPath()
        let prefix = temporaryRoot.path.hasSuffix("/")
            ? temporaryRoot.path : temporaryRoot.path + "/"
        guard candidate.path.hasPrefix(prefix) else {
            throw RuntimeApplicationSupportError.localQAPathOutsideTemporaryDirectory
        }
        var isDirectory: ObjCBool = false
        guard fileManager.fileExists(atPath: candidate.path, isDirectory: &isDirectory),
              isDirectory.boolValue
        else {
            throw RuntimeApplicationSupportError.localQAPathDoesNotExist
        }
        return candidate
    }
}

enum RuntimeApplicationSupportError: LocalizedError {
    case missingLocalQAPath
    case localQAPathOutsideTemporaryDirectory
    case localQAPathDoesNotExist

    var errorDescription: String? {
        switch self {
        case .missingLocalQAPath:
            "已启用本地 QA，但没有指定隔离资料目录。"
        case .localQAPathOutsideTemporaryDirectory:
            "本地 QA 资料目录必须位于 macOS 临时目录内。"
        case .localQAPathDoesNotExist:
            "本地 QA 资料目录不存在或不是文件夹。"
        }
    }
}

@MainActor
final class RuntimeTerminationSignal: NSObject {
    private let notificationCenter: NotificationCenter
    private let onTermination: () -> Void

    init(
        notificationCenter: NotificationCenter = .default,
        notificationName: Notification.Name = NSApplication.willTerminateNotification,
        onTermination: @escaping () -> Void
    ) {
        self.notificationCenter = notificationCenter
        self.onTermination = onTermination
        super.init()
        notificationCenter.addObserver(
            self,
            selector: #selector(handleTermination),
            name: notificationName,
            object: nil
        )
    }

    deinit {
        notificationCenter.removeObserver(self)
    }

    @objc private func handleTermination() {
        // Do not enqueue a Task here. Once NSApplication terminates, the main
        // event loop may never execute it and the bundled Runtime becomes orphaned.
        onTermination()
    }
}

@MainActor
@Observable
final class RuntimeSupervisor {
    static let shared = RuntimeSupervisor()

    private(set) var isReady = false
    private var process: Process?
    private var terminationSignal: RuntimeTerminationSignal?

    private init() {
        terminationSignal = RuntimeTerminationSignal { [weak self] in
            self?.stop()
        }
    }

    func stop() {
        if let process { RuntimeProcessTerminator.stop(process) }
        process = nil
        isReady = false
    }

    func start() async throws {
        let inheritedEnvironment = ProcessInfo.processInfo.environment
        let localQAEnabled = inheritedEnvironment[
            RuntimeApplicationSupportResolver.localQAFlag
        ] == "1"
        let reuseDecision = try RuntimeReusePolicy.decide(
            supervisorReady: isReady,
            managedProcessRunning: process?.isRunning == true,
            loopbackRuntimeHealthy: await runtimeIsHealthy(),
            localQAEnabled: localQAEnabled
        )
        if reuseDecision == .useManagedRuntime {
            return
        }
        if isReady || process != nil { stop() }
        guard let resources = Bundle.main.resourceURL else {
            throw RuntimeSupervisorError.resourcesMissing
        }
        let executable = resources.appending(path: "runtime/nalu-runtime")
        guard FileManager.default.isExecutableFile(atPath: executable.path) else {
            throw RuntimeSupervisorError.runtimeMissing(executable.path)
        }

        let defaultApplicationSupport = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        ).appending(path: "Nalu Voice Studio", directoryHint: .isDirectory)
        let applicationSupport = try RuntimeApplicationSupportResolver.resolve(
            inherited: inheritedEnvironment,
            defaultURL: defaultApplicationSupport
        )
        try FileManager.default.createDirectory(
            at: applicationSupport, withIntermediateDirectories: true
        )
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o700], ofItemAtPath: applicationSupport.path
        )

        let process = Process()
        process.executableURL = executable
        process.environment = RuntimeEnvironmentBuilder.build(
            inherited: inheritedEnvironment,
            applicationSupport: applicationSupport,
            resources: resources
        )
        try process.run()
        self.process = process

        // The universal one-file Runtime can take more than a minute to unpack and
        // load its FFmpeg libraries on a cold or older Mac. Keep the UI responsive
        // while polling, but retain a finite fail-closed startup deadline.
        for _ in 0..<RuntimeStartupPolicy.maximumAttempts {
            if await runtimeIsHealthy() {
                isReady = true
                return
            }
            if !process.isRunning { break }
            try await Task.sleep(
                for: .milliseconds(RuntimeStartupPolicy.pollIntervalMilliseconds)
            )
        }
        stop()
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
    case localQARuntimeAlreadyRunning
    case unmanagedRuntimeAlreadyRunning

    var errorDescription: String? {
        switch self {
        case .resourcesMissing: "应用资源目录不存在。"
        case .runtimeMissing(let path): "内置制片厂 Runtime 不存在：\(path)"
        case .startupTimedOut: "内置制片厂启动超时。"
        case .localQARuntimeAlreadyRunning:
            "本地 QA 不能连接已经运行的制片厂。请先退出其他 Nalu 窗口，再重新打开 QA。"
        case .unmanagedRuntimeAlreadyRunning:
            "检测到另一份 Nalu 制片厂正在运行。为保护本地项目资料，本窗口不会连接它；请先退出其他 Nalu 窗口后重试。"
        }
    }
}
