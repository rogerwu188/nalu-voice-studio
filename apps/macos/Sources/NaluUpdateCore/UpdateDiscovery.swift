import CryptoKit
import Foundation

public struct UpdateDiscoveryConfiguration: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let enabled: Bool
    public let origin: String
    public let maxManifestBytes: UInt64
    public let maxPackageBytes: UInt64

    public init(
        schemaVersion: String = "nalu.update-discovery/v1",
        enabled: Bool,
        origin: String,
        maxManifestBytes: UInt64 = 65_536,
        maxPackageBytes: UInt64 = 2_147_483_648
    ) {
        self.schemaVersion = schemaVersion
        self.enabled = enabled
        self.origin = origin
        self.maxManifestBytes = maxManifestBytes
        self.maxPackageBytes = maxPackageBytes
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case enabled, origin
        case maxManifestBytes = "max_manifest_bytes"
        case maxPackageBytes = "max_package_bytes"
    }
}

public enum UpdateDiscoveryPhase: String, Codable, Sendable {
    case manifestDownloaded = "manifest_downloaded"
    case packageDownloaded = "package_downloaded"
    case verified
}

public struct UpdateDiscoveryRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let transactionID: String
    public let idempotencyKeySHA256: String
    public let requestSHA256: String
    public let origin: String
    public let installedBuild: UInt64
    public let manifestPath: String
    public let packagePath: String
    public let manifestSHA256: String
    public let packageSHA256: String
    public let packageSize: UInt64
    public var phase: UpdateDiscoveryPhase
    public var updatedAt: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case transactionID = "transaction_id"
        case idempotencyKeySHA256 = "idempotency_key_sha256"
        case requestSHA256 = "request_sha256"
        case origin
        case installedBuild = "installed_build"
        case manifestPath = "manifest_path"
        case packagePath = "package_path"
        case manifestSHA256 = "manifest_sha256"
        case packageSHA256 = "package_sha256"
        case packageSize = "package_size"
        case phase
        case updatedAt = "updated_at"
    }
}

public protocol UpdateResourceFetching: Sendable {
    func fetch(_ source: URL, to destination: URL, maximumBytes: UInt64) throws
}

public enum UpdateDiscoveryError: Error, Equatable, LocalizedError {
    case discoveryDisabled
    case invalidConfiguration
    case invalidIdempotencyKey
    case idempotencyConflict
    case unsafePath
    case invalidState
    case manifestTooLarge
    case packageTooLarge
    case downloadedResourceMissing
    case downloadedResourceTooLarge

    public var errorDescription: String? {
        switch self {
        case .discoveryDisabled: "Update discovery is disabled."
        case .invalidConfiguration: "The update discovery configuration is invalid."
        case .invalidIdempotencyKey: "A stable update discovery idempotency key is required."
        case .idempotencyConflict: "The discovery idempotency key was reused for another request."
        case .unsafePath: "The update discovery path is unsafe."
        case .invalidState: "The update discovery transaction is in an invalid state."
        case .manifestTooLarge: "The update manifest exceeds its configured limit."
        case .packageTooLarge: "The update package exceeds its configured limit."
        case .downloadedResourceMissing: "The downloaded update resource is missing."
        case .downloadedResourceTooLarge: "The downloaded update resource exceeds its limit."
        }
    }
}

public final class UpdateDiscoveryTransaction: @unchecked Sendable {
    private let root: URL
    private let fetcher: any UpdateResourceFetching
    private let fileManager: FileManager
    private let encoder: JSONEncoder
    private let decoder = JSONDecoder()

    public init(
        root: URL,
        fetcher: any UpdateResourceFetching,
        fileManager: FileManager = .default
    ) throws {
        guard root.isFileURL, root.standardizedFileURL.path != "/" else {
            throw UpdateDiscoveryError.unsafePath
        }
        self.root = root.standardizedFileURL
        self.fetcher = fetcher
        self.fileManager = fileManager
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try fileManager.createDirectory(at: self.root, withIntermediateDirectories: true)
        try fileManager.createDirectory(
            at: self.root.appendingPathComponent("downloads", isDirectory: true),
            withIntermediateDirectories: true
        )
    }

    public func discover(
        configuration: UpdateDiscoveryConfiguration,
        trust: UpdateTrustConfiguration,
        installedBuild: UInt64,
        idempotencyKey: String,
        now: Date = Date()
    ) throws -> UpdateDiscoveryRecord {
        let origin = try validatedOrigin(configuration)
        guard idempotencyKey.count >= 16 else {
            throw UpdateDiscoveryError.invalidIdempotencyKey
        }
        let keyHash = sha256(Data(idempotencyKey.utf8))
        let transactionID = String(keyHash.prefix(32))
        let requestData = try JSONSerialization.data(
            withJSONObject: [
                "configuration": try canonicalConfiguration(configuration),
                "installed_build": installedBuild,
                "trust": String(decoding: try encoder.encode(trust), as: UTF8.self),
            ],
            options: [.sortedKeys]
        )
        let requestHash = sha256(requestData)
        let state = stateURL(transactionID)
        if fileManager.fileExists(atPath: state.path) {
            var record = try load(transactionID: transactionID)
            guard record.requestSHA256 == requestHash,
                  record.origin == origin.absoluteString,
                  record.installedBuild == installedBuild
            else {
                throw UpdateDiscoveryError.idempotencyConflict
            }
            let manifest = try decodeManifest(URL(fileURLWithPath: record.manifestPath))
            let manifestSHA = try UpdateManifestVerifier.verifyManifest(
                manifest: manifest,
                trust: trust,
                installedBuild: installedBuild,
                now: now
            )
            guard manifestSHA == record.manifestSHA256,
                  manifest.packageSHA256 == record.packageSHA256,
                  manifest.packageSize == record.packageSize
            else { throw UpdateDiscoveryError.invalidState }
            if record.phase == .manifestDownloaded {
                try downloadPackage(manifest, origin: origin, record: &record)
            }
            return try finishVerification(record: &record, manifest: manifest, trust: trust, now: now)
        }

        let directory = downloadDirectory(transactionID)
        guard !fileManager.fileExists(atPath: directory.path) else {
            throw UpdateDiscoveryError.invalidState
        }
        try fileManager.createDirectory(at: directory, withIntermediateDirectories: false)
        let manifestURL = directory.appendingPathComponent("manifest.json")
        try fetchAtomically(
            origin.appendingPathComponent("manifest.json", isDirectory: false),
            to: manifestURL,
            maximumBytes: configuration.maxManifestBytes
        )
        let manifest = try decodeManifest(manifestURL)
        let manifestSHA = try UpdateManifestVerifier.verifyManifest(
            manifest: manifest,
            trust: trust,
            installedBuild: installedBuild,
            now: now
        )
        guard manifest.packageSize <= configuration.maxPackageBytes else {
            throw UpdateDiscoveryError.packageTooLarge
        }
        var record = UpdateDiscoveryRecord(
            schemaVersion: "nalu.update-discovery-record/v1",
            transactionID: transactionID,
            idempotencyKeySHA256: keyHash,
            requestSHA256: requestHash,
            origin: origin.absoluteString,
            installedBuild: installedBuild,
            manifestPath: manifestURL.path,
            packagePath: directory.appendingPathComponent("package.zip").path,
            manifestSHA256: manifestSHA,
            packageSHA256: manifest.packageSHA256,
            packageSize: manifest.packageSize,
            phase: .manifestDownloaded,
            updatedAt: timestamp()
        )
        try save(record)
        try downloadPackage(manifest, origin: origin, record: &record)
        return try finishVerification(record: &record, manifest: manifest, trust: trust, now: now)
    }

    public func load(transactionID: String) throws -> UpdateDiscoveryRecord {
        guard transactionID.count == 32,
              transactionID.allSatisfy({ $0.isHexDigit && !$0.isUppercase })
        else { throw UpdateDiscoveryError.invalidState }
        let record = try decoder.decode(
            UpdateDiscoveryRecord.self,
            from: Data(contentsOf: stateURL(transactionID))
        )
        guard record.schemaVersion == "nalu.update-discovery-record/v1",
              record.transactionID == transactionID,
              URL(fileURLWithPath: record.manifestPath).standardizedFileURL.path
                .hasPrefix(downloadDirectory(transactionID).path + "/"),
              URL(fileURLWithPath: record.packagePath).standardizedFileURL.path
                .hasPrefix(downloadDirectory(transactionID).path + "/")
        else { throw UpdateDiscoveryError.invalidState }
        return record
    }

    private func validatedOrigin(_ configuration: UpdateDiscoveryConfiguration) throws -> URL {
        guard configuration.enabled else { throw UpdateDiscoveryError.discoveryDisabled }
        guard configuration.schemaVersion == "nalu.update-discovery/v1",
              configuration.maxManifestBytes >= 1_024,
              configuration.maxManifestBytes <= 1_048_576,
              configuration.maxPackageBytes >= 1_048_576,
              configuration.maxPackageBytes <= 10_737_418_240,
              var components = URLComponents(string: configuration.origin),
              components.scheme == "https",
              components.host?.isEmpty == false,
              components.user == nil,
              components.password == nil,
              components.query == nil,
              components.fragment == nil,
              !components.percentEncodedPath.contains("%")
        else { throw UpdateDiscoveryError.invalidConfiguration }
        if components.path.isEmpty { components.path = "/" }
        guard components.path.hasSuffix("/"),
              !components.path.contains(".."),
              let origin = components.url
        else { throw UpdateDiscoveryError.invalidConfiguration }
        return origin
    }

    private func canonicalConfiguration(_ configuration: UpdateDiscoveryConfiguration) throws -> String {
        let data = try encoder.encode(configuration)
        return String(decoding: data, as: UTF8.self)
    }

    private func decodeManifest(_ url: URL) throws -> UpdateManifest {
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
        guard values.isRegularFile == true else {
            throw UpdateDiscoveryError.downloadedResourceMissing
        }
        guard let size = values.fileSize, size >= 0, size <= 1_048_576 else {
            throw UpdateDiscoveryError.manifestTooLarge
        }
        return try decoder.decode(UpdateManifest.self, from: Data(contentsOf: url))
    }

    private func downloadPackage(
        _ manifest: UpdateManifest,
        origin: URL,
        record: inout UpdateDiscoveryRecord
    ) throws {
        guard record.phase == .manifestDownloaded else { return }
        let packageURL = URL(fileURLWithPath: record.packagePath)
        let remote = origin
            .appendingPathComponent("packages", isDirectory: true)
            .appendingPathComponent("\(manifest.packageSHA256).zip", isDirectory: false)
        try fetchAtomically(remote, to: packageURL, maximumBytes: manifest.packageSize)
        record.phase = .packageDownloaded
        record.updatedAt = timestamp()
        try save(record)
    }

    private func finishVerification(
        record: inout UpdateDiscoveryRecord,
        manifest: UpdateManifest,
        trust: UpdateTrustConfiguration,
        now: Date
    ) throws -> UpdateDiscoveryRecord {
        guard record.phase == .packageDownloaded || record.phase == .verified else {
            throw UpdateDiscoveryError.invalidState
        }
        _ = try UpdateManifestVerifier.verify(
            manifest: manifest,
            packageURL: URL(fileURLWithPath: record.packagePath),
            trust: trust,
            installedBuild: record.installedBuild,
            now: now
        )
        if record.phase != .verified {
            record.phase = .verified
            record.updatedAt = timestamp()
            try save(record)
        }
        return record
    }

    private func fetchAtomically(_ source: URL, to destination: URL, maximumBytes: UInt64) throws {
        guard !fileManager.fileExists(atPath: destination.path) else {
            throw UpdateDiscoveryError.invalidState
        }
        let partial = destination.appendingPathExtension("partial")
        if fileManager.fileExists(atPath: partial.path) {
            try fileManager.removeItem(at: partial)
        }
        do {
            try fetcher.fetch(source, to: partial, maximumBytes: maximumBytes)
            let values = try partial.resourceValues(forKeys: [.isRegularFileKey, .fileSizeKey])
            guard values.isRegularFile == true, let size = values.fileSize, size >= 0 else {
                throw UpdateDiscoveryError.downloadedResourceMissing
            }
            guard UInt64(size) <= maximumBytes else {
                throw UpdateDiscoveryError.downloadedResourceTooLarge
            }
            try fileManager.moveItem(at: partial, to: destination)
        } catch {
            try? fileManager.removeItem(at: partial)
            throw error
        }
    }

    private func save(_ record: UpdateDiscoveryRecord) throws {
        let destination = stateURL(record.transactionID)
        let temporary = destination.appendingPathExtension("tmp")
        try encoder.encode(record).write(to: temporary, options: .atomic)
        if fileManager.fileExists(atPath: destination.path) {
            _ = try fileManager.replaceItemAt(destination, withItemAt: temporary)
        } else {
            try fileManager.moveItem(at: temporary, to: destination)
        }
    }

    private func stateURL(_ transactionID: String) -> URL {
        root.appendingPathComponent("\(transactionID).json")
    }

    private func downloadDirectory(_ transactionID: String) -> URL {
        root.appendingPathComponent("downloads/\(transactionID)", isDirectory: true)
    }

    private func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func timestamp() -> String {
        ISO8601DateFormatter().string(from: Date())
    }
}
