import CryptoKit
import Foundation
import Testing
@testable import NaluUpdateCore

private final class FixtureFetcher: UpdateResourceFetching, @unchecked Sendable {
    private let responses: [String: Data]
    private let lock = NSLock()
    private var fetched: [String] = []

    init(responses: [String: Data]) {
        self.responses = responses
    }

    func fetch(_ source: URL, to destination: URL, maximumBytes: UInt64) throws {
        guard let data = responses[source.absoluteString] else {
            throw CocoaError(.fileNoSuchFile)
        }
        try data.write(to: destination, options: .atomic)
        lock.lock()
        fetched.append(source.absoluteString)
        lock.unlock()
    }

    var requests: [String] {
        lock.lock()
        defer { lock.unlock() }
        return fetched
    }
}

struct UpdateDiscoveryTests {
    private let now = ISO8601DateFormatter().date(from: "2026-09-01T00:00:00Z")!

    private func signedFixture(
        package: Data = Data("exact package".utf8),
        declaredSize: UInt64? = nil,
        declaredDigest: String? = nil
    ) throws -> (manifest: UpdateManifest, manifestData: Data, trust: UpdateTrustConfiguration) {
        let privateKey = Curve25519.Signing.PrivateKey()
        let unsigned = UpdateManifest(
            channel: "test",
            version: "0.2.0",
            build: 20,
            releaseCommit: String(repeating: "b", count: 40),
            packageSHA256: declaredDigest ?? UpdateManifestVerifier.sha256(package),
            packageSize: declaredSize ?? UInt64(package.count),
            createdAt: "2026-08-31T23:00:00Z",
            expiresAt: "2026-09-02T00:00:00Z",
            signatureBase64: ""
        )
        let signature = try privateKey.signature(for: unsigned.canonicalPayload())
        let manifest = UpdateManifest(
            channel: unsigned.channel,
            version: unsigned.version,
            build: unsigned.build,
            releaseCommit: unsigned.releaseCommit,
            packageSHA256: unsigned.packageSHA256,
            packageSize: unsigned.packageSize,
            createdAt: unsigned.createdAt,
            expiresAt: unsigned.expiresAt,
            signatureBase64: signature.base64EncodedString()
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return (
            manifest,
            try encoder.encode(manifest),
            UpdateTrustConfiguration(
                enabled: true,
                channel: "test",
                publicKeyBase64: privateKey.publicKey.rawRepresentation.base64EncodedString(),
                requireNotarization: false
            )
        )
    }

    private func configuration(
        enabled: Bool = true,
        origin: String = "https://updates.nalu.invalid/v1/",
        maxManifestBytes: UInt64 = 65_536,
        maxPackageBytes: UInt64 = 1_048_576
    ) -> UpdateDiscoveryConfiguration {
        UpdateDiscoveryConfiguration(
            enabled: enabled,
            origin: origin,
            maxManifestBytes: maxManifestBytes,
            maxPackageBytes: maxPackageBytes
        )
    }

    @Test func exactHTTPSFixtureDownloadsAtomicallyAndReplaysIdempotently() throws {
        let package = Data("exact package".utf8)
        let fixture = try signedFixture(package: package)
        let origin = "https://updates.nalu.invalid/v1/"
        let packageURL = "\(origin)packages/\(fixture.manifest.packageSHA256).zip"
        let fetcher = FixtureFetcher(responses: [
            "\(origin)manifest.json": fixture.manifestData,
            packageURL: package,
        ])
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("nalu-discovery-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let transaction = try UpdateDiscoveryTransaction(root: root, fetcher: fetcher)

        let first = try transaction.discover(
            configuration: configuration(),
            trust: fixture.trust,
            installedBuild: 10,
            idempotencyKey: "discovery-test-key-0001",
            now: now
        )
        let replay = try transaction.discover(
            configuration: configuration(),
            trust: fixture.trust,
            installedBuild: 10,
            idempotencyKey: "discovery-test-key-0001",
            now: now
        )

        #expect(first.phase == .verified)
        #expect(replay == first)
        #expect(fetcher.requests == ["\(origin)manifest.json", packageURL])
        #expect(try Data(contentsOf: URL(fileURLWithPath: first.packagePath)) == package)
        #expect(!FileManager.default.fileExists(atPath: first.packagePath + ".partial"))
    }

    @Test func disabledAndNonHTTPSOriginsFailBeforeFetching() throws {
        let fixture = try signedFixture()
        let fetcher = FixtureFetcher(responses: [:])
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("nalu-discovery-policy-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let transaction = try UpdateDiscoveryTransaction(root: root, fetcher: fetcher)

        #expect(throws: UpdateDiscoveryError.discoveryDisabled) {
            try transaction.discover(
                configuration: configuration(enabled: false),
                trust: fixture.trust,
                installedBuild: 10,
                idempotencyKey: "discovery-test-key-0002",
                now: now
            )
        }
        #expect(throws: UpdateDiscoveryError.invalidConfiguration) {
            try transaction.discover(
                configuration: configuration(origin: "http://updates.nalu.invalid/v1/"),
                trust: fixture.trust,
                installedBuild: 10,
                idempotencyKey: "discovery-test-key-0003",
                now: now
            )
        }
        #expect(fetcher.requests.isEmpty)
    }

    @Test func declaredOversizePackageStopsBeforePackageFetch() throws {
        let digest = String(repeating: "a", count: 64)
        let fixture = try signedFixture(declaredSize: 2_000_000, declaredDigest: digest)
        let origin = "https://updates.nalu.invalid/v1/"
        let fetcher = FixtureFetcher(responses: ["\(origin)manifest.json": fixture.manifestData])
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("nalu-discovery-size-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let transaction = try UpdateDiscoveryTransaction(root: root, fetcher: fetcher)

        #expect(throws: UpdateDiscoveryError.packageTooLarge) {
            try transaction.discover(
                configuration: configuration(maxPackageBytes: 1_048_576),
                trust: fixture.trust,
                installedBuild: 10,
                idempotencyKey: "discovery-test-key-0004",
                now: now
            )
        }
        #expect(fetcher.requests == ["\(origin)manifest.json"])
    }

    @Test func corruptedPackageAndChangedReplayFailClosed() throws {
        let fixture = try signedFixture()
        let origin = "https://updates.nalu.invalid/v1/"
        let fetcher = FixtureFetcher(responses: [
            "\(origin)manifest.json": fixture.manifestData,
            "\(origin)packages/\(fixture.manifest.packageSHA256).zip": Data("wrong".utf8),
        ])
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("nalu-discovery-corrupt-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let transaction = try UpdateDiscoveryTransaction(root: root, fetcher: fetcher)
        #expect(throws: UpdateVerificationError.packageSizeMismatch) {
            try transaction.discover(
                configuration: configuration(),
                trust: fixture.trust,
                installedBuild: 10,
                idempotencyKey: "discovery-test-key-0005",
                now: now
            )
        }
        #expect(throws: UpdateDiscoveryError.idempotencyConflict) {
            try transaction.discover(
                configuration: configuration(),
                trust: fixture.trust,
                installedBuild: 11,
                idempotencyKey: "discovery-test-key-0005",
                now: now
            )
        }
    }

    @Test func fetcherCannotSmuggleMoreBytesThanLimit() throws {
        let fixture = try signedFixture()
        let origin = "https://updates.nalu.invalid/v1/"
        let fetcher = FixtureFetcher(responses: [
            "\(origin)manifest.json": Data(repeating: 0x41, count: 2_000),
        ])
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("nalu-discovery-overflow-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: root) }
        let transaction = try UpdateDiscoveryTransaction(root: root, fetcher: fetcher)
        #expect(throws: UpdateDiscoveryError.downloadedResourceTooLarge) {
            try transaction.discover(
                configuration: configuration(maxManifestBytes: 1_024),
                trust: fixture.trust,
                installedBuild: 10,
                idempotencyKey: "discovery-test-key-0006",
                now: now
            )
        }
    }
}
