import CryptoKit
import Foundation
#if canImport(NaluUpdateCore)
import NaluUpdateCore
#endif

guard CommandLine.arguments.count == 9 else {
    FileHandle.standardError.write(Data(
        "usage: signer <package> <manifest> <trust> <version> <build> <channel> <commit> <now>\n".utf8
    ))
    exit(2)
}

let package = URL(fileURLWithPath: CommandLine.arguments[1])
let manifestURL = URL(fileURLWithPath: CommandLine.arguments[2])
let trustURL = URL(fileURLWithPath: CommandLine.arguments[3])
let version = CommandLine.arguments[4]
guard let build = UInt64(CommandLine.arguments[5]) else { exit(2) }
let channel = CommandLine.arguments[6]
let commit = CommandLine.arguments[7]
let formatter = ISO8601DateFormatter()
guard let now = formatter.date(from: CommandLine.arguments[8]) else { exit(2) }
let packageData = try Data(contentsOf: package)
let privateKey = Curve25519.Signing.PrivateKey()
let unsigned = UpdateManifest(
    channel: channel,
    version: version,
    build: build,
    releaseCommit: commit,
    packageSHA256: UpdateManifestVerifier.sha256(packageData),
    packageSize: UInt64(packageData.count),
    createdAt: formatter.string(from: now.addingTimeInterval(-60)),
    expiresAt: formatter.string(from: now.addingTimeInterval(3600)),
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
    channel: channel,
    publicKeyBase64: privateKey.publicKey.rawRepresentation.base64EncodedString(),
    requireNotarization: false
)
let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
try encoder.encode(manifest).write(to: manifestURL, options: .atomic)
try encoder.encode(trust).write(to: trustURL, options: .atomic)
