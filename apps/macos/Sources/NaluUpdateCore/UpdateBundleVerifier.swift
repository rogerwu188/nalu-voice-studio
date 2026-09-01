import Foundation

public enum UpdateBundleVerificationError: Error, Equatable, LocalizedError {
    case applicationMissing
    case invalidMetadata
    case metadataMismatch
    case signatureInvalid
    case notarizationInvalid

    public var errorDescription: String? {
        switch self {
        case .applicationMissing: "The staged application is missing."
        case .invalidMetadata: "The staged application metadata is invalid."
        case .metadataMismatch: "The staged application does not match the update manifest."
        case .signatureInvalid: "The staged application code signature is invalid."
        case .notarizationInvalid: "The staged application is not accepted by Gatekeeper."
        }
    }
}

public enum UpdateBundleVerifier {
    public static func verify(
        application: URL,
        manifest: UpdateManifest,
        requireNotarization: Bool
    ) throws {
        let infoURL = application.appendingPathComponent("Contents/Info.plist")
        guard application.path.hasSuffix(".app"),
              FileManager.default.fileExists(atPath: infoURL.path),
              let info = NSDictionary(contentsOf: infoURL) as? [String: Any],
              let bundleID = info["CFBundleIdentifier"] as? String,
              let version = info["CFBundleShortVersionString"] as? String,
              let buildText = info["CFBundleVersion"] as? String,
              let build = UInt64(buildText)
        else { throw UpdateBundleVerificationError.invalidMetadata }
        guard bundleID == manifest.bundleIdentifier,
              version == manifest.version,
              build == manifest.build
        else { throw UpdateBundleVerificationError.metadataMismatch }
        guard run("/usr/bin/codesign", ["--verify", "--deep", "--strict", application.path]) == 0
        else { throw UpdateBundleVerificationError.signatureInvalid }
        if requireNotarization {
            guard run("/usr/sbin/spctl", ["--assess", "--type", "execute", application.path]) == 0
            else { throw UpdateBundleVerificationError.notarizationInvalid }
        }
    }

    private static func run(_ executable: String, _ arguments: [String]) -> Int32 {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus
        } catch {
            return -1
        }
    }
}
