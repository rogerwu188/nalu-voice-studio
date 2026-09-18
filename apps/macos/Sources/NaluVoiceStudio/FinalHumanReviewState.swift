import Foundation

/// Explicit user decisions only. Downloading or playing media never approves it.
struct FinalHumanReviewState {
    private(set) var pending: FinalHumanReviewDraft?
    private(set) var confirmed: FinalHumanReviewResult?

    /// Checkpoint only the exact pending request, never infer a confirmed decision.
    func pendingCheckpoint() throws -> Data? {
        guard let pending else { return nil }
        return try JSONEncoder().encode(pending)
    }

    mutating func restorePending(_ data: Data, runID: String,
                                 masterSHA256: String, outputSealSHA256: String) throws {
        let draft = try JSONDecoder().decode(FinalHumanReviewDraft.self, from: data)
        guard draft.runID == runID, draft.masterSHA256 == masterSHA256,
              draft.outputSealSHA256 == outputSealSHA256 else {
            throw RuntimeError.requestFailed("保存的审核属于其他成片，未恢复或重新提交。")
        }
        _ = try prepare(draft)
    }

    mutating func prepare(_ draft: FinalHumanReviewDraft) throws -> FinalHumanReviewDraft {
        guard !draft.idempotencyKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              draft.idempotencyKey.count <= 200,
              draft.outputSealSHA256.count == 64,
              draft.outputSealSHA256.allSatisfy({ "0123456789abcdef".contains($0) }) else {
            throw RuntimeError.requestFailed("审核重试标识或成片封存摘要无效。")
        }
        let expected = try JSONDecoder().decode(FinalHumanReviewResult.self,
            from: JSONEncoder().encode(draft))
        try expected.validate(runID: draft.runID)
        guard confirmed == nil else {
            throw RuntimeError.requestFailed("这份审核已经保存，请创建修订版本后再审核。")
        }
        if let pending {
            guard pending == draft else {
                throw RuntimeError.requestFailed("上次提交结果尚未确认，请先恢复原审核记录。")
            }
            return pending
        }
        pending = draft
        return draft
    }

    mutating func confirm(_ result: FinalHumanReviewResult) throws {
        guard let pending else {
            throw RuntimeError.requestFailed("没有待核对的审核提交。")
        }
        try result.validate(runID: pending.runID, submitted: pending)
        confirmed = result
        self.pending = nil
    }
}
