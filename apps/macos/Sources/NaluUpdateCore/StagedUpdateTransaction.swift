import CryptoKit
import Foundation

public enum UpdateTransactionPhase: String, Codable, Sendable {
    case prepared
    case liveMovedToBackup = "live_moved_to_backup"
    case awaitingHealth = "awaiting_health"
    case committed
    case rolledBack = "rolled_back"
}

public struct UpdateTransactionRecord: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let transactionID: String
    public let idempotencyKeySHA256: String
    public let requestSHA256: String
    public let manifestSHA256: String
    public let fromBuild: UInt64
    public let toBuild: UInt64
    public let liveAppPath: String
    public let incomingAppPath: String
    public let backupAppPath: String
    public let quarantineAppPath: String
    public let protectedDataPath: String
    public let protectedDataSHA256: String
    public var phase: UpdateTransactionPhase
    public var updatedAt: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case transactionID = "transaction_id"
        case idempotencyKeySHA256 = "idempotency_key_sha256"
        case requestSHA256 = "request_sha256"
        case manifestSHA256 = "manifest_sha256"
        case fromBuild = "from_build"
        case toBuild = "to_build"
        case liveAppPath = "live_app_path"
        case incomingAppPath = "incoming_app_path"
        case backupAppPath = "backup_app_path"
        case quarantineAppPath = "quarantine_app_path"
        case protectedDataPath = "protected_data_path"
        case protectedDataSHA256 = "protected_data_sha256"
        case phase
        case updatedAt = "updated_at"
    }
}

public enum UpdateTransactionError: Error, Equatable, LocalizedError {
    case invalidIdempotencyKey
    case unsafePath
    case liveApplicationMissing
    case candidateApplicationMissing
    case idempotencyConflict
    case invalidState
    case protectedDataChanged
    case recoveryImpossible

    public var errorDescription: String? {
        switch self {
        case .invalidIdempotencyKey: "A stable idempotency key is required."
        case .unsafePath: "The update path is outside the controlled local transaction root."
        case .liveApplicationMissing: "The installed application is missing."
        case .candidateApplicationMissing: "The staged application is missing."
        case .idempotencyConflict: "The idempotency key was reused for another update."
        case .invalidState: "The update transaction is in an invalid state."
        case .protectedDataChanged: "Protected local project data changed during the update."
        case .recoveryImpossible: "The previous application cannot be restored safely."
        }
    }
}

public final class StagedUpdateTransaction: @unchecked Sendable {
    public typealias Failpoint = @Sendable (UpdateTransactionPhase) throws -> Void

    private let root: URL
    private let fileManager: FileManager
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    public init(root: URL, fileManager: FileManager = .default) throws {
        guard root.isFileURL, root.standardizedFileURL.path != "/" else {
            throw UpdateTransactionError.unsafePath
        }
        self.root = root.standardizedFileURL
        self.fileManager = fileManager
        encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        decoder = JSONDecoder()
        try fileManager.createDirectory(at: self.root, withIntermediateDirectories: true)
        try fileManager.createDirectory(
            at: self.root.appendingPathComponent("incoming", isDirectory: true),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(
            at: self.root.appendingPathComponent("backups", isDirectory: true),
            withIntermediateDirectories: true
        )
        try fileManager.createDirectory(
            at: self.root.appendingPathComponent("quarantine", isDirectory: true),
            withIntermediateDirectories: true
        )
    }

    public func prepare(
        verifiedUpdate: VerifiedUpdate,
        liveApplication: URL,
        candidateApplication: URL,
        protectedData: URL,
        installedBuild: UInt64,
        idempotencyKey: String
    ) throws -> UpdateTransactionRecord {
        guard idempotencyKey.count >= 16 else {
            throw UpdateTransactionError.invalidIdempotencyKey
        }
        let live = liveApplication.standardizedFileURL
        let candidate = candidateApplication.standardizedFileURL
        let protected = protectedData.standardizedFileURL
        guard live.isFileURL, candidate.isFileURL, protected.isFileURL,
              live.path.hasSuffix(".app"), candidate.path.hasSuffix(".app"),
              live.path != candidate.path
        else { throw UpdateTransactionError.unsafePath }
        guard fileManager.fileExists(atPath: live.path) else {
            throw UpdateTransactionError.liveApplicationMissing
        }
        guard fileManager.fileExists(atPath: candidate.path) else {
            throw UpdateTransactionError.candidateApplicationMissing
        }
        let keyHash = sha256(Data(idempotencyKey.utf8))
        let transactionID = String(keyHash.prefix(32))
        let stateURL = stateURL(for: transactionID)
        let request: [String: Any] = [
            "candidate": candidate.path,
            "from_build": installedBuild,
            "live": live.path,
            "manifest_sha256": verifiedUpdate.manifestSHA256,
            "protected_data": protected.path,
            "to_build": verifiedUpdate.manifest.build,
        ]
        let requestData = try JSONSerialization.data(withJSONObject: request, options: [.sortedKeys])
        let requestHash = sha256(requestData)
        if fileManager.fileExists(atPath: stateURL.path) {
            let existing = try load(transactionID: transactionID)
            guard existing.requestSHA256 == requestHash else {
                throw UpdateTransactionError.idempotencyConflict
            }
            return existing
        }
        let incoming = root.appendingPathComponent("incoming/\(transactionID).app")
        let backup = root.appendingPathComponent("backups/\(transactionID).app")
        let quarantine = root.appendingPathComponent("quarantine/\(transactionID).app")
        guard !fileManager.fileExists(atPath: incoming.path),
              !fileManager.fileExists(atPath: backup.path),
              !fileManager.fileExists(atPath: quarantine.path)
        else { throw UpdateTransactionError.invalidState }
        try fileManager.copyItem(at: candidate, to: incoming)
        let record = UpdateTransactionRecord(
            schemaVersion: "nalu.update-transaction/v1",
            transactionID: transactionID,
            idempotencyKeySHA256: keyHash,
            requestSHA256: requestHash,
            manifestSHA256: verifiedUpdate.manifestSHA256,
            fromBuild: installedBuild,
            toBuild: verifiedUpdate.manifest.build,
            liveAppPath: live.path,
            incomingAppPath: incoming.path,
            backupAppPath: backup.path,
            quarantineAppPath: quarantine.path,
            protectedDataPath: protected.path,
            protectedDataSHA256: try treeDigest(protected),
            phase: .prepared,
            updatedAt: timestamp()
        )
        try save(record)
        return record
    }

    public func activate(
        transactionID: String,
        failpoint: Failpoint? = nil
    ) throws -> UpdateTransactionRecord {
        var record = try load(transactionID: transactionID)
        if record.phase == .awaitingHealth || record.phase == .committed { return record }
        guard record.phase == .prepared || record.phase == .liveMovedToBackup else {
            throw UpdateTransactionError.invalidState
        }
        try requireProtectedDataUnchanged(record)
        let live = URL(fileURLWithPath: record.liveAppPath)
        let incoming = URL(fileURLWithPath: record.incomingAppPath)
        let backup = URL(fileURLWithPath: record.backupAppPath)
        if record.phase == .prepared {
            guard fileManager.fileExists(atPath: live.path),
                  fileManager.fileExists(atPath: incoming.path),
                  !fileManager.fileExists(atPath: backup.path)
            else { throw UpdateTransactionError.invalidState }
            try fileManager.moveItem(at: live, to: backup)
            record.phase = .liveMovedToBackup
            record.updatedAt = timestamp()
            try save(record)
            try failpoint?(.liveMovedToBackup)
        }
        guard !fileManager.fileExists(atPath: live.path),
              fileManager.fileExists(atPath: incoming.path),
              fileManager.fileExists(atPath: backup.path)
        else { throw UpdateTransactionError.invalidState }
        try fileManager.moveItem(at: incoming, to: live)
        record.phase = .awaitingHealth
        record.updatedAt = timestamp()
        try save(record)
        try failpoint?(.awaitingHealth)
        try requireProtectedDataUnchanged(record)
        return record
    }

    public func commit(transactionID: String) throws -> UpdateTransactionRecord {
        var record = try load(transactionID: transactionID)
        if record.phase == .committed { return record }
        guard record.phase == .awaitingHealth else {
            throw UpdateTransactionError.invalidState
        }
        try requireProtectedDataUnchanged(record)
        guard fileManager.fileExists(atPath: record.liveAppPath),
              fileManager.fileExists(atPath: record.backupAppPath)
        else { throw UpdateTransactionError.recoveryImpossible }
        record.phase = .committed
        record.updatedAt = timestamp()
        try save(record)
        return record
    }

    public func rollback(transactionID: String) throws -> UpdateTransactionRecord {
        var record = try load(transactionID: transactionID)
        if record.phase == .rolledBack { return record }
        guard record.phase == .liveMovedToBackup || record.phase == .awaitingHealth else {
            throw UpdateTransactionError.invalidState
        }
        try requireProtectedDataUnchanged(record)
        let live = URL(fileURLWithPath: record.liveAppPath)
        let backup = URL(fileURLWithPath: record.backupAppPath)
        let quarantine = URL(fileURLWithPath: record.quarantineAppPath)
        guard fileManager.fileExists(atPath: backup.path) else {
            throw UpdateTransactionError.recoveryImpossible
        }
        if fileManager.fileExists(atPath: live.path) {
            guard !fileManager.fileExists(atPath: quarantine.path) else {
                throw UpdateTransactionError.recoveryImpossible
            }
            try fileManager.moveItem(at: live, to: quarantine)
        }
        try fileManager.moveItem(at: backup, to: live)
        record.phase = .rolledBack
        record.updatedAt = timestamp()
        try save(record)
        return record
    }

    public func recover(transactionID: String) throws -> UpdateTransactionRecord {
        let record = try load(transactionID: transactionID)
        switch record.phase {
        case .liveMovedToBackup, .awaitingHealth:
            return try rollback(transactionID: transactionID)
        case .prepared, .committed, .rolledBack:
            return record
        }
    }

    public func load(transactionID: String) throws -> UpdateTransactionRecord {
        guard transactionID.count == 32,
              transactionID.allSatisfy({ $0.isHexDigit && !$0.isUppercase })
        else { throw UpdateTransactionError.invalidState }
        let record = try decoder.decode(
            UpdateTransactionRecord.self,
            from: Data(contentsOf: stateURL(for: transactionID))
        )
        guard record.schemaVersion == "nalu.update-transaction/v1",
              record.transactionID == transactionID
        else { throw UpdateTransactionError.invalidState }
        return record
    }

    public func treeDigest(_ url: URL) throws -> String {
        guard url.isFileURL else { throw UpdateTransactionError.unsafePath }
        if !fileManager.fileExists(atPath: url.path) { return sha256(Data("missing".utf8)) }
        let keys: [URLResourceKey] = [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey]
        guard let enumerator = fileManager.enumerator(
            at: url,
            includingPropertiesForKeys: keys,
            options: []
        ) else { throw UpdateTransactionError.unsafePath }
        var entries: [Data] = []
        for case let item as URL in enumerator {
            let values = try item.resourceValues(forKeys: Set(keys))
            if values.isSymbolicLink == true { throw UpdateTransactionError.unsafePath }
            guard values.isRegularFile == true else { continue }
            let relative = String(item.path.dropFirst(url.path.count)).trimmingCharacters(
                in: CharacterSet(charactersIn: "/")
            )
            let digest = try UpdateManifestVerifier.sha256(of: item)
            entries.append(Data("\(relative)\u{0}\(values.fileSize ?? 0)\u{0}\(digest)\n".utf8))
        }
        return sha256(entries.sorted { $0.lexicographicallyPrecedes($1) }.reduce(Data(), +))
    }

    private func requireProtectedDataUnchanged(_ record: UpdateTransactionRecord) throws {
        guard try treeDigest(URL(fileURLWithPath: record.protectedDataPath)) ==
            record.protectedDataSHA256
        else { throw UpdateTransactionError.protectedDataChanged }
    }

    private func save(_ record: UpdateTransactionRecord) throws {
        let destination = stateURL(for: record.transactionID)
        let temporary = destination.appendingPathExtension("tmp")
        try encoder.encode(record).write(to: temporary, options: .atomic)
        if fileManager.fileExists(atPath: destination.path) {
            _ = try fileManager.replaceItemAt(destination, withItemAt: temporary)
        } else {
            try fileManager.moveItem(at: temporary, to: destination)
        }
    }

    private func stateURL(for transactionID: String) -> URL {
        root.appendingPathComponent("\(transactionID).json")
    }

    private func sha256(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private func timestamp() -> String {
        ISO8601DateFormatter().string(from: Date())
    }
}
