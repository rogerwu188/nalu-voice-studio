import CryptoKit
import Foundation

public struct UpdateTrustConfiguration: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let enabled: Bool
    public let channel: String
    public let publicKeyBase64: String
    public let requireNotarization: Bool

    public init(
        schemaVersion: String = "nalu.update-trust/v1",
        enabled: Bool,
        channel: String,
        publicKeyBase64: String,
        requireNotarization: Bool
    ) {
        self.schemaVersion = schemaVersion
        self.enabled = enabled
        self.channel = channel
        self.publicKeyBase64 = publicKeyBase64
        self.requireNotarization = requireNotarization
    }
}

public struct UpdateManifest: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let channel: String
    public let version: String
    public let build: UInt64
    public let bundleIdentifier: String
    public let releaseCommit: String
    public let packageSHA256: String
    public let packageSize: UInt64
    public let createdAt: String
    public let expiresAt: String
    public let signatureBase64: String

    public init(
        schemaVersion: String = "nalu.update-manifest/v1",
        channel: String,
        version: String,
        build: UInt64,
        bundleIdentifier: String = "studio.nalu.voice",
        releaseCommit: String,
        packageSHA256: String,
        packageSize: UInt64,
        createdAt: String,
        expiresAt: String,
        signatureBase64: String
    ) {
        self.schemaVersion = schemaVersion
        self.channel = channel
        self.version = version
        self.build = build
        self.bundleIdentifier = bundleIdentifier
        self.releaseCommit = releaseCommit
        self.packageSHA256 = packageSHA256
        self.packageSize = packageSize
        self.createdAt = createdAt
        self.expiresAt = expiresAt
        self.signatureBase64 = signatureBase64
    }

    public func canonicalPayload() throws -> Data {
        let payload: [String: Any] = [
            "build": build,
            "bundle_identifier": bundleIdentifier,
            "channel": channel,
            "created_at": createdAt,
            "expires_at": expiresAt,
            "package_sha256": packageSHA256,
            "package_size": packageSize,
            "release_commit": releaseCommit,
            "schema_version": schemaVersion,
            "version": version,
        ]
        return try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case channel, version, build
        case bundleIdentifier = "bundle_identifier"
        case releaseCommit = "release_commit"
        case packageSHA256 = "package_sha256"
        case packageSize = "package_size"
        case createdAt = "created_at"
        case expiresAt = "expires_at"
        case signatureBase64 = "signature_base64"
    }
}

public struct VerifiedUpdate: Equatable, Sendable {
    public let manifest: UpdateManifest
    public let manifestSHA256: String
    public let packageURL: URL

    public init(manifest: UpdateManifest, manifestSHA256: String, packageURL: URL) {
        self.manifest = manifest
        self.manifestSHA256 = manifestSHA256
        self.packageURL = packageURL
    }
}

public enum UpdateVerificationError: Error, Equatable, LocalizedError {
    case updatesDisabled
    case invalidTrustConfiguration
    case unsupportedManifest
    case channelMismatch
    case invalidVersion
    case downgradeOrReplay
    case invalidTimestamp
    case notYetValid
    case expired
    case invalidReleaseCommit
    case invalidPackageDigest
    case invalidSignature
    case packageMissing
    case packageSizeMismatch
    case packageDigestMismatch

    public var errorDescription: String? {
        switch self {
        case .updatesDisabled: "Automatic updates are disabled."
        case .invalidTrustConfiguration: "The update trust configuration is invalid."
        case .unsupportedManifest: "The update manifest schema or bundle is unsupported."
        case .channelMismatch: "The update channel is not trusted."
        case .invalidVersion: "The update version is invalid."
        case .downgradeOrReplay: "The update is not newer than the installed build."
        case .invalidTimestamp: "The update timestamps are invalid."
        case .notYetValid: "The update manifest is not valid yet."
        case .expired: "The update manifest has expired."
        case .invalidReleaseCommit: "The release commit is invalid."
        case .invalidPackageDigest: "The package digest is invalid."
        case .invalidSignature: "The update manifest signature is invalid."
        case .packageMissing: "The update package is missing."
        case .packageSizeMismatch: "The update package size does not match."
        case .packageDigestMismatch: "The update package digest does not match."
        }
    }
}

public enum UpdateManifestVerifier {
    private static let iso8601 = ISO8601DateFormatter()
    private static let versionPattern = try! NSRegularExpression(
        pattern: #"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$"#
    )
    private static let shaPattern = try! NSRegularExpression(pattern: #"^[0-9a-f]{64}$"#)
    private static let commitPattern = try! NSRegularExpression(pattern: #"^[0-9a-f]{40}$"#)

    public static func verify(
        manifest: UpdateManifest,
        packageURL: URL,
        trust: UpdateTrustConfiguration,
        installedBuild: UInt64,
        now: Date = Date()
    ) throws -> VerifiedUpdate {
        let manifestSHA256 = try verifyManifest(
            manifest: manifest,
            trust: trust,
            installedBuild: installedBuild,
            now: now
        )
        guard packageURL.isFileURL,
              FileManager.default.fileExists(atPath: packageURL.path)
        else { throw UpdateVerificationError.packageMissing }
        let values = try packageURL.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
        guard values.isRegularFile == true,
              let fileSize = values.fileSize,
              fileSize >= 0,
              UInt64(fileSize) == manifest.packageSize
        else { throw UpdateVerificationError.packageSizeMismatch }
        guard try sha256(of: packageURL) == manifest.packageSHA256 else {
            throw UpdateVerificationError.packageDigestMismatch
        }
        return VerifiedUpdate(
            manifest: manifest,
            manifestSHA256: manifestSHA256,
            packageURL: packageURL
        )
    }

    public static func verifyManifest(
        manifest: UpdateManifest,
        trust: UpdateTrustConfiguration,
        installedBuild: UInt64,
        now: Date = Date()
    ) throws -> String {
        guard trust.enabled else { throw UpdateVerificationError.updatesDisabled }
        guard trust.schemaVersion == "nalu.update-trust/v1",
              trust.channel == "stable" || trust.channel == "test",
              let publicKeyData = Data(base64Encoded: trust.publicKeyBase64),
              publicKeyData.count == 32
        else { throw UpdateVerificationError.invalidTrustConfiguration }
        guard manifest.schemaVersion == "nalu.update-manifest/v1",
              manifest.bundleIdentifier == "studio.nalu.voice"
        else { throw UpdateVerificationError.unsupportedManifest }
        guard manifest.channel == trust.channel else {
            throw UpdateVerificationError.channelMismatch
        }
        guard matches(versionPattern, manifest.version) else {
            throw UpdateVerificationError.invalidVersion
        }
        guard manifest.build > installedBuild else {
            throw UpdateVerificationError.downgradeOrReplay
        }
        guard let created = iso8601.date(from: manifest.createdAt),
              let expires = iso8601.date(from: manifest.expiresAt),
              created < expires
        else { throw UpdateVerificationError.invalidTimestamp }
        guard created <= now.addingTimeInterval(300) else {
            throw UpdateVerificationError.notYetValid
        }
        guard expires > now else { throw UpdateVerificationError.expired }
        guard matches(commitPattern, manifest.releaseCommit) else {
            throw UpdateVerificationError.invalidReleaseCommit
        }
        guard matches(shaPattern, manifest.packageSHA256) else {
            throw UpdateVerificationError.invalidPackageDigest
        }
        guard let signature = Data(base64Encoded: manifest.signatureBase64),
              let publicKey = try? Curve25519.Signing.PublicKey(rawRepresentation: publicKeyData),
              publicKey.isValidSignature(signature, for: try manifest.canonicalPayload())
        else { throw UpdateVerificationError.invalidSignature }
        return sha256(try manifest.canonicalPayload())
    }

    public static func sha256(of url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var hasher = SHA256()
        while true {
            let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
            if data.isEmpty { break }
            hasher.update(data: data)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    public static func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func matches(_ expression: NSRegularExpression, _ value: String) -> Bool {
        expression.firstMatch(
            in: value,
            range: NSRange(value.startIndex..., in: value)
        ) != nil
    }
}
