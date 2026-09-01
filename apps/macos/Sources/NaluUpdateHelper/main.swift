import Foundation
#if canImport(NaluUpdateCore)
import NaluUpdateCore
#endif

private struct Arguments {
    let command: String
    let values: [String: String]

    init(_ raw: [String]) throws {
        guard let command = raw.first else { throw HelperError.usage }
        self.command = command
        var parsed: [String: String] = [:]
        var index = 1
        while index < raw.count {
            let key = raw[index]
            guard key.hasPrefix("--"), index + 1 < raw.count else {
                throw HelperError.usage
            }
            parsed[String(key.dropFirst(2))] = raw[index + 1]
            index += 2
        }
        values = parsed
    }

    func require(_ key: String) throws -> String {
        guard let value = values[key], !value.isEmpty else { throw HelperError.missing(key) }
        return value
    }
}

private enum HelperError: Error, LocalizedError {
    case usage
    case missing(String)
    case invalidBuild
    case extractionFailed
    case extractedApplicationMissing

    var errorDescription: String? {
        switch self {
        case .usage:
            "Usage: nalu-update-helper verify|stage|confirm|recover --key value ..."
        case .missing(let key): "Missing --\(key)."
        case .invalidBuild: "The installed build is invalid."
        case .extractionFailed: "The update package could not be extracted."
        case .extractedApplicationMissing: "The update package contains no Nalu application."
        }
    }
}

private func decode<T: Decodable>(_ type: T.Type, at url: URL) throws -> T {
    try JSONDecoder().decode(type, from: Data(contentsOf: url))
}

private func encode(_ record: UpdateTransactionRecord) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    FileHandle.standardOutput.write(try encoder.encode(record))
    FileHandle.standardOutput.write(Data("\n".utf8))
}

private func verifiedUpdate(_ arguments: Arguments) throws -> (VerifiedUpdate, UpdateTrustConfiguration) {
    let manifestURL = URL(fileURLWithPath: try arguments.require("manifest"))
    let packageURL = URL(fileURLWithPath: try arguments.require("package"))
    let trustURL = URL(fileURLWithPath: try arguments.require("trust-config"))
    guard let build = UInt64(try arguments.require("installed-build")) else {
        throw HelperError.invalidBuild
    }
    let manifest = try decode(UpdateManifest.self, at: manifestURL)
    let trust = try decode(UpdateTrustConfiguration.self, at: trustURL)
    return (
        try UpdateManifestVerifier.verify(
            manifest: manifest,
            packageURL: packageURL,
            trust: trust,
            installedBuild: build
        ),
        trust
    )
}

private func extract(_ package: URL, into root: URL) throws -> URL {
    let extraction = root.appendingPathComponent("extract-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: extraction, withIntermediateDirectories: true)
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
    process.arguments = ["-x", "-k", package.path, extraction.path]
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    try process.run()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else { throw HelperError.extractionFailed }
    let direct = extraction.appendingPathComponent("Nalu Voice Studio.app")
    if FileManager.default.fileExists(atPath: direct.path) { return direct }
    guard let enumerator = FileManager.default.enumerator(
        at: extraction,
        includingPropertiesForKeys: [.isDirectoryKey],
        options: [.skipsHiddenFiles]
    ) else { throw HelperError.extractedApplicationMissing }
    for case let item as URL in enumerator where item.lastPathComponent == "Nalu Voice Studio.app" {
        return item
    }
    throw HelperError.extractedApplicationMissing
}

private func run() throws {
    let arguments = try Arguments(Array(CommandLine.arguments.dropFirst()))
    switch arguments.command {
    case "verify":
        let (verified, _) = try verifiedUpdate(arguments)
        print("{\"manifest_sha256\":\"\(verified.manifestSHA256)\",\"status\":\"verified\"}")
    case "stage":
        let (verified, trust) = try verifiedUpdate(arguments)
        let stateRoot = URL(fileURLWithPath: try arguments.require("state-root"))
        let candidate = try extract(verified.packageURL, into: stateRoot)
        try UpdateBundleVerifier.verify(
            application: candidate,
            manifest: verified.manifest,
            requireNotarization: trust.requireNotarization
        )
        let transaction = try StagedUpdateTransaction(root: stateRoot)
        let prepared = try transaction.prepare(
            verifiedUpdate: verified,
            liveApplication: URL(fileURLWithPath: try arguments.require("live-app")),
            candidateApplication: candidate,
            protectedData: URL(fileURLWithPath: try arguments.require("protected-data")),
            installedBuild: UInt64(try arguments.require("installed-build"))!,
            idempotencyKey: try arguments.require("idempotency-key")
        )
        try encode(try transaction.activate(transactionID: prepared.transactionID))
    case "confirm":
        let transaction = try StagedUpdateTransaction(
            root: URL(fileURLWithPath: try arguments.require("state-root"))
        )
        try encode(try transaction.commit(transactionID: try arguments.require("transaction-id")))
    case "recover":
        let transaction = try StagedUpdateTransaction(
            root: URL(fileURLWithPath: try arguments.require("state-root"))
        )
        try encode(try transaction.recover(transactionID: try arguments.require("transaction-id")))
    default:
        throw HelperError.usage
    }
}

do {
    try run()
} catch {
    let message = (error as? LocalizedError)?.errorDescription ?? String(describing: error)
    FileHandle.standardError.write(Data("nalu-update-helper: \(message)\n".utf8))
    exit(1)
}
