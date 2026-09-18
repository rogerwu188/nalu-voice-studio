import CryptoKit
import Darwin
import Foundation

/// Write-once local submission journal. A lost reply must reuse the saved request.
struct FinalHumanReviewStore {
    let directory: URL

    private func path(runID: String) -> URL {
        let name = SHA256.hash(data: Data(runID.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(name + ".json")
    }

    func load(runID: String, masterSHA256: String, outputSealSHA256: String) throws -> FinalHumanReviewState? {
        let url = path(runID: runID)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        guard attributes[.type] as? FileAttributeType == .typeRegular else {
            throw RuntimeError.requestFailed("审核保存路径不安全，已停止恢复。")
        }
        var state = FinalHumanReviewState()
        try state.restorePending(Data(contentsOf: url), runID: runID,
            masterSHA256: masterSHA256, outputSealSHA256: outputSealSHA256)
        return state
    }

    func save(_ draft: FinalHumanReviewDraft) throws -> FinalHumanReviewState {
        var state = FinalHumanReviewState()
        _ = try state.prepare(draft)
        let manager = FileManager.default
        try manager.createDirectory(at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700])
        let attributes = try manager.attributesOfItem(atPath: directory.path)
        guard attributes[.type] as? FileAttributeType == .typeDirectory else {
            throw RuntimeError.requestFailed("审核保存目录不安全。")
        }
        let temporary = directory.appendingPathComponent(UUID().uuidString + ".tmp")
        defer { try? manager.removeItem(at: temporary) }
        let bytes = try JSONEncoder().encode(draft)
        try bytes.write(to: temporary, options: .withoutOverwriting)
        try manager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: temporary.path)
        let handle = try FileHandle(forWritingTo: temporary)
        defer { try? handle.close() }
        try handle.synchronize()
        // link publishes a complete file without overwriting a competing writer.
        if link(temporary.path, path(runID: draft.runID).path) != 0 && errno != EEXIST {
            throw RuntimeError.requestFailed("审核尚未安全保存，未提交。")
        }
        let descriptor = open(directory.path, O_RDONLY | O_NOFOLLOW)
        guard descriptor >= 0 else {
            throw RuntimeError.requestFailed("无法同步审核目录，未提交。")
        }
        defer { close(descriptor) }
        guard fsync(descriptor) == 0 else {
            throw RuntimeError.requestFailed("审核目录同步失败，未提交。")
        }
        guard let saved = try load(runID: draft.runID, masterSHA256: draft.masterSHA256,
                                  outputSealSHA256: draft.outputSealSHA256),
              saved.pending == draft else {
            throw RuntimeError.requestFailed("已有不同的审核请求，请先恢复核对。")
        }
        return saved
    }
}
