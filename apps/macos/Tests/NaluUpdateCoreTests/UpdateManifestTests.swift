import CryptoKit
import Foundation
import Testing
@testable import NaluUpdateCore

struct UpdateManifestTests {
    @Test func packagedSnakeCaseTrustConfigurationDecodesFailClosed() throws {
        let data = Data(#"""
        {
          "schema_version": "nalu.update-trust/v1",
          "enabled": false,
          "channel": "stable",
          "public_key_base64": "",
          "require_notarization": true
        }
        """#.utf8)

        let trust = try JSONDecoder().decode(UpdateTrustConfiguration.self, from: data)

        #expect(trust.schemaVersion == "nalu.update-trust/v1")
        #expect(!trust.enabled)
        #expect(trust.channel == "stable")
        #expect(trust.publicKeyBase64.isEmpty)
        #expect(trust.requireNotarization)
    }

    private func fixture(
        packageData: Data = Data("signed package".utf8),
        build: UInt64 = 11,
        createdAt: String = "2026-08-31T20:00:00Z",
        expiresAt: String = "2026-09-02T20:00:00Z"
    ) throws -> (
        manifest: UpdateManifest,
        package: URL,
        trust: UpdateTrustConfiguration,
        privateKey: Curve25519.Signing.PrivateKey,
        root: URL
    ) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("nalu-update-manifest-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let package = root.appendingPathComponent("Nalu.zip")
        try packageData.write(to: package)
        let privateKey = Curve25519.Signing.PrivateKey()
        let unsigned = UpdateManifest(
            channel: "test",
            version: "0.2.0-rc1",
            build: build,
            releaseCommit: String(repeating: "a", count: 40),
            packageSHA256: UpdateManifestVerifier.sha256(packageData),
            packageSize: UInt64(packageData.count),
            createdAt: createdAt,
            expiresAt: expiresAt,
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
        let trust = UpdateTrustConfiguration(
            enabled: true,
            channel: "test",
            publicKeyBase64: privateKey.publicKey.rawRepresentation.base64EncodedString(),
            requireNotarization: false
        )
        return (manifest, package, trust, privateKey, root)
    }

    @Test func validSignedManifestAndExactPackagePass() throws {
        let value = try fixture()
        defer { try? FileManager.default.removeItem(at: value.root) }

        let verified = try UpdateManifestVerifier.verify(
            manifest: value.manifest,
            packageURL: value.package,
            trust: value.trust,
            installedBuild: 10,
            now: ISO8601DateFormatter().date(from: "2026-09-01T00:00:00Z")!
        )

        #expect(verified.manifest.build == 11)
        #expect(verified.manifestSHA256.count == 64)
    }

    @Test func disabledTrustAndWrongChannelFailClosed() throws {
        let value = try fixture()
        defer { try? FileManager.default.removeItem(at: value.root) }
        let now = ISO8601DateFormatter().date(from: "2026-09-01T00:00:00Z")!
        let disabled = UpdateTrustConfiguration(
            enabled: false,
            channel: "test",
            publicKeyBase64: value.trust.publicKeyBase64,
            requireNotarization: false
        )
        #expect(throws: UpdateVerificationError.updatesDisabled) {
            try UpdateManifestVerifier.verify(
                manifest: value.manifest,
                packageURL: value.package,
                trust: disabled,
                installedBuild: 10,
                now: now
            )
        }
        let stable = UpdateTrustConfiguration(
            enabled: true,
            channel: "stable",
            publicKeyBase64: value.trust.publicKeyBase64,
            requireNotarization: true
        )
        #expect(throws: UpdateVerificationError.channelMismatch) {
            try UpdateManifestVerifier.verify(
                manifest: value.manifest,
                packageURL: value.package,
                trust: stable,
                installedBuild: 10,
                now: now
            )
        }
    }

    @Test func tamperDowngradeExpiryAndPackageMutationAreRejected() throws {
        let value = try fixture()
        defer { try? FileManager.default.removeItem(at: value.root) }
        let now = ISO8601DateFormatter().date(from: "2026-09-01T00:00:00Z")!
        let tampered = UpdateManifest(
            channel: value.manifest.channel,
            version: value.manifest.version,
            build: 12,
            releaseCommit: value.manifest.releaseCommit,
            packageSHA256: value.manifest.packageSHA256,
            packageSize: value.manifest.packageSize,
            createdAt: value.manifest.createdAt,
            expiresAt: value.manifest.expiresAt,
            signatureBase64: value.manifest.signatureBase64
        )
        #expect(throws: UpdateVerificationError.invalidSignature) {
            try UpdateManifestVerifier.verify(
                manifest: tampered,
                packageURL: value.package,
                trust: value.trust,
                installedBuild: 10,
                now: now
            )
        }
        #expect(throws: UpdateVerificationError.downgradeOrReplay) {
            try UpdateManifestVerifier.verify(
                manifest: value.manifest,
                packageURL: value.package,
                trust: value.trust,
                installedBuild: 11,
                now: now
            )
        }
        let expired = try fixture(
            createdAt: "2026-08-29T00:00:00Z",
            expiresAt: "2026-08-30T00:00:00Z"
        )
        defer { try? FileManager.default.removeItem(at: expired.root) }
        #expect(throws: UpdateVerificationError.expired) {
            try UpdateManifestVerifier.verify(
                manifest: expired.manifest,
                packageURL: expired.package,
                trust: expired.trust,
                installedBuild: 10,
                now: now
            )
        }
        try Data("mutated package".utf8).write(to: value.package)
        #expect(throws: UpdateVerificationError.packageSizeMismatch) {
            try UpdateManifestVerifier.verify(
                manifest: value.manifest,
                packageURL: value.package,
                trust: value.trust,
                installedBuild: 10,
                now: now
            )
        }
    }
}
