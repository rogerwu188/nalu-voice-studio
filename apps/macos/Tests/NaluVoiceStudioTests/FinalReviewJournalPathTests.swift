import CryptoKit
import Foundation
import Testing
@testable import NaluVoiceStudio

struct FinalReviewJournalPathTests {
    @Test func danglingJournalIsNotAnAbsentReview() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let store = FinalHumanReviewStore(directory: root)
        let sha = String(repeating: "a", count: 64)
        if let _ = try store.load(runID: "run", masterSHA256: sha, outputSealSHA256: sha) {
            Issue.record("absent journal unexpectedly recovered a state")
        }
        let name = SHA256.hash(data: Data("run".utf8)).map { String(format: "%02x", $0) }.joined()
        let journal = root.appendingPathComponent(name + ".json")
        try FileManager.default.createSymbolicLink(at: journal,
            withDestinationURL: root.appendingPathComponent("missing.json"))
        #expect(throws: (any Error).self) {
            try store.load(runID: "run", masterSHA256: sha, outputSealSHA256: sha)
        }
        #expect(try FileManager.default.destinationOfSymbolicLink(atPath: journal.path)
            == root.appendingPathComponent("missing.json").path)
    }
}
