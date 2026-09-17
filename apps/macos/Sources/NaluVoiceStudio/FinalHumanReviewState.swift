import Foundation

/// Explicit user decisions only. Downloading or playing media never approves it.
struct FinalHumanReviewState {
    private(set) var pending: FinalHumanReviewDraft?
    private(set) var confirmed: FinalHumanReviewResult?

    mutating func prepare(_ draft: FinalHumanReviewDraft) throws -> FinalHumanReviewDraft {
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
