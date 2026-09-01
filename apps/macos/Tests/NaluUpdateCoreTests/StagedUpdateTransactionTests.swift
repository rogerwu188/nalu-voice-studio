import Foundation
import Testing
@testable import NaluUpdateCore

struct StagedUpdateTransactionTests {
    private struct Fixture {
        let root: URL
        let state: URL
        let live: URL
        let candidate: URL
        let protectedData: URL
        let verified: VerifiedUpdate
    }

    private func fixture(suffix: String = "one") throws -> Fixture {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("nalu-update-transaction-\(UUID().uuidString)")
        let state = root.appendingPathComponent("state")
        let live = root.appendingPathComponent("Applications/Nalu Voice Studio.app")
        let candidate = root.appendingPathComponent("candidate-\(suffix)/Nalu Voice Studio.app")
        let protectedData = root.appendingPathComponent("Application Support/Nalu Voice Studio")
        for directory in [live, candidate, protectedData] {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        try Data("old app".utf8).write(to: live.appendingPathComponent("marker"))
        try Data("new app \(suffix)".utf8).write(to: candidate.appendingPathComponent("marker"))
        try Data("sqlite project bytes".utf8).write(
            to: protectedData.appendingPathComponent("nalu.sqlite3")
        )
        let manifest = UpdateManifest(
            channel: "test",
            version: "0.2.0",
            build: 2,
            releaseCommit: String(repeating: "b", count: 40),
            packageSHA256: String(repeating: "c", count: 64),
            packageSize: 1,
            createdAt: "2026-08-31T00:00:00Z",
            expiresAt: "2026-09-02T00:00:00Z",
            signatureBase64: "fixture"
        )
        return Fixture(
            root: root,
            state: state,
            live: live,
            candidate: candidate,
            protectedData: protectedData,
            verified: VerifiedUpdate(
                manifest: manifest,
                manifestSHA256: String(repeating: "d", count: 64),
                packageURL: root.appendingPathComponent("package.zip")
            )
        )
    }

    private func marker(_ application: URL) throws -> String {
        try String(contentsOf: application.appendingPathComponent("marker"), encoding: .utf8)
    }

    @Test func prepareActivateCommitAndReplayPreserveProjectData() throws {
        let value = try fixture()
        defer { try? FileManager.default.removeItem(at: value.root) }
        let transaction = try StagedUpdateTransaction(root: value.state)
        let before = try transaction.treeDigest(value.protectedData)
        let prepared = try transaction.prepare(
            verifiedUpdate: value.verified,
            liveApplication: value.live,
            candidateApplication: value.candidate,
            protectedData: value.protectedData,
            installedBuild: 1,
            idempotencyKey: "update-checkpoint-one"
        )
        let replay = try transaction.prepare(
            verifiedUpdate: value.verified,
            liveApplication: value.live,
            candidateApplication: value.candidate,
            protectedData: value.protectedData,
            installedBuild: 1,
            idempotencyKey: "update-checkpoint-one"
        )
        #expect(replay == prepared)
        #expect(try transaction.activate(transactionID: prepared.transactionID).phase == .awaitingHealth)
        #expect(try marker(value.live) == "new app one")
        #expect(try transaction.commit(transactionID: prepared.transactionID).phase == .committed)
        #expect(try transaction.commit(transactionID: prepared.transactionID).phase == .committed)
        #expect(try transaction.treeDigest(value.protectedData) == before)
    }

    @Test func crashAfterOldAppMoveRecoversOldApp() throws {
        let value = try fixture()
        defer { try? FileManager.default.removeItem(at: value.root) }
        let transaction = try StagedUpdateTransaction(root: value.state)
        let prepared = try transaction.prepare(
            verifiedUpdate: value.verified,
            liveApplication: value.live,
            candidateApplication: value.candidate,
            protectedData: value.protectedData,
            installedBuild: 1,
            idempotencyKey: "update-crash-after-backup"
        )
        enum SimulatedCrash: Error, Equatable { case now }
        #expect(throws: SimulatedCrash.now) {
            try transaction.activate(transactionID: prepared.transactionID) { phase in
                if phase == .liveMovedToBackup { throw SimulatedCrash.now }
            }
        }
        let restarted = try StagedUpdateTransaction(root: value.state)
        #expect(try restarted.recover(transactionID: prepared.transactionID).phase == .rolledBack)
        #expect(try marker(value.live) == "old app")
        #expect(try restarted.recover(transactionID: prepared.transactionID).phase == .rolledBack)
    }

    @Test func missingHealthConfirmationRollsBackCandidate() throws {
        let value = try fixture()
        defer { try? FileManager.default.removeItem(at: value.root) }
        let transaction = try StagedUpdateTransaction(root: value.state)
        let prepared = try transaction.prepare(
            verifiedUpdate: value.verified,
            liveApplication: value.live,
            candidateApplication: value.candidate,
            protectedData: value.protectedData,
            installedBuild: 1,
            idempotencyKey: "update-health-timeout"
        )
        _ = try transaction.activate(transactionID: prepared.transactionID)
        #expect(try marker(value.live) == "new app one")
        #expect(try transaction.recover(transactionID: prepared.transactionID).phase == .rolledBack)
        #expect(try marker(value.live) == "old app")
        #expect(FileManager.default.fileExists(atPath: prepared.quarantineAppPath))
    }

    @Test func idempotencyConflictAndProtectedDataMutationFailClosed() throws {
        let value = try fixture()
        defer { try? FileManager.default.removeItem(at: value.root) }
        let transaction = try StagedUpdateTransaction(root: value.state)
        let prepared = try transaction.prepare(
            verifiedUpdate: value.verified,
            liveApplication: value.live,
            candidateApplication: value.candidate,
            protectedData: value.protectedData,
            installedBuild: 1,
            idempotencyKey: "update-conflict-key"
        )
        let other = try fixture(suffix: "two")
        defer { try? FileManager.default.removeItem(at: other.root) }
        #expect(throws: UpdateTransactionError.idempotencyConflict) {
            try transaction.prepare(
                verifiedUpdate: value.verified,
                liveApplication: value.live,
                candidateApplication: other.candidate,
                protectedData: value.protectedData,
                installedBuild: 1,
                idempotencyKey: "update-conflict-key"
            )
        }
        try Data("changed".utf8).write(
            to: value.protectedData.appendingPathComponent("nalu.sqlite3")
        )
        #expect(throws: UpdateTransactionError.protectedDataChanged) {
            try transaction.activate(transactionID: prepared.transactionID)
        }
        #expect(try marker(value.live) == "old app")
    }
}
