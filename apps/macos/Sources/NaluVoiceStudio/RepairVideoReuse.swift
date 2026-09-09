import Foundation

struct RepairVideoCandidate: Codable, Equatable, Identifiable {
    var shot_index: Int
    var status: String
    var requires_review: Bool
    var reason: String?
    var source_run_id: String?
    var source_review_id: String?
    var source_review_sha256: String?
    var materialization_id: String?
    var video_sha256: String?
    var id: Int { shot_index }
}

struct RepairVideoCandidates: Codable {
    var run_id: String
    var source_run_id: String
    var plan_event_id: String
    var plan_sha256: String
    var candidates_sha256: String
    var items: [RepairVideoCandidate]
    var adopted: Bool
    var generation_performed: Bool

    func validate(runID: String) throws {
        guard run_id == runID, source_run_id != runID, !source_run_id.isEmpty,
              !plan_event_id.isEmpty, !adopted, !generation_performed,
              EpisodeDialogueStageReceipt.validSHA(plan_sha256),
              EpisodeDialogueStageReceipt.validSHA(candidates_sha256),
              !items.isEmpty, items.count <= 120,
              items.map(\.shot_index) == Array(0..<items.count) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        for item in items {
            guard item.requires_review, ["needs_new_video", "available_for_review"].contains(item.status) else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            if item.status == "available_for_review" {
                guard item.source_run_id == source_run_id, let review = item.source_review_id, !review.isEmpty,
                      let media = item.materialization_id, !media.isEmpty,
                      let hash = item.video_sha256, EpisodeDialogueStageReceipt.validSHA(hash),
                      let receipt = item.source_review_sha256, EpisodeDialogueStageReceipt.validSHA(receipt) else {
                    throw LibrarySnapshotRefreshError.contextChanged
                }
            }
        }
    }
}

struct RepairVideoDecision: Codable, Identifiable {
    struct Payload: Codable {
        var shot_index: Int
        var candidate: RepairVideoCandidate
        var plan_id: String
        var plan_sha256: String
        var decision: String
        var adopted: Bool
        var generation_performed: Bool
        var paid_approved: Bool
        var master_accepted: Bool
        var review_sha256: String
    }
    var id: String
    var run_id: String
    var event_type: String
    var payload: Payload

    func validate(runID: String) throws {
        let p = payload
        guard run_id == runID, event_type == "repair_video_reviewed", !id.isEmpty,
              !p.plan_id.isEmpty, p.shot_index >= 0, p.shot_index < 120,
              p.candidate.shot_index == p.shot_index,
              p.candidate.status == "available_for_review", p.candidate.requires_review,
              let source = p.candidate.source_run_id, !source.isEmpty, source != runID,
              let review = p.candidate.source_review_id, !review.isEmpty,
              let media = p.candidate.materialization_id, !media.isEmpty,
              let videoSHA = p.candidate.video_sha256, EpisodeDialogueStageReceipt.validSHA(videoSHA),
              let sourceSHA = p.candidate.source_review_sha256, EpisodeDialogueStageReceipt.validSHA(sourceSHA),
              ["accept", "reject"].contains(p.decision), p.adopted == (p.decision == "accept"),
              !p.generation_performed, !p.paid_approved, !p.master_accepted,
              EpisodeDialogueStageReceipt.validSHA(p.plan_sha256),
              EpisodeDialogueStageReceipt.validSHA(p.review_sha256) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }
}

struct RepairVideoDecisionRequest: Codable {
    var expected_candidates_sha256: String
    var shot_index: Int
    var expected_review_id: String?
    var decision: String
    var reviewed_by: String
    var confirmation: String
}

/// Keeps historical CAS receipts separate from approval of the current plan.
struct RepairVideoReviewState {
    let candidates: RepairVideoCandidates
    private(set) var decisions: [Int: RepairVideoDecision] = [:]
    private(set) var viewedShots: Set<Int> = []

    init(candidates: RepairVideoCandidates, decisions: [RepairVideoDecision]) throws {
        try candidates.validate(runID: candidates.run_id)
        self.candidates = candidates
        for decision in decisions {
            try decision.validate(runID: candidates.run_id)
            guard self.decisions[decision.payload.shot_index] == nil else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            self.decisions[decision.payload.shot_index] = decision
        }
    }

    func currentDecision(for shot: Int) -> RepairVideoDecision? {
        guard let saved = decisions[shot], saved.payload.plan_id == candidates.plan_event_id,
              saved.payload.plan_sha256 == candidates.plan_sha256,
              saved.payload.candidate == candidates.items.first(where: { $0.shot_index == shot }) else { return nil }
        return saved
    }

    func previousID(for shot: Int) -> String? { decisions[shot]?.id }

    mutating func markViewed(_ shot: Int) throws {
        guard candidates.items.contains(where: { $0.shot_index == shot && $0.status == "available_for_review" }) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        viewedShots.insert(shot)
    }

    func canAccept(_ shot: Int) -> Bool { viewedShots.contains(shot) }

    mutating func record(_ decision: RepairVideoDecision) throws {
        try decision.validate(runID: candidates.run_id)
        let p = decision.payload
        guard p.plan_id == candidates.plan_event_id, p.plan_sha256 == candidates.plan_sha256,
              p.candidate == candidates.items.first(where: { $0.shot_index == p.shot_index }),
              !p.adopted || canAccept(p.shot_index) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        decisions[p.shot_index] = decision
    }
}
