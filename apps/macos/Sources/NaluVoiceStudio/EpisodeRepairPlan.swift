import Foundation

struct EpisodeRepairPlan: Decodable, Sendable {
    struct Item: Decodable, Sendable {
        let code: String
        let target: String
        let issue: String
        let required_action: String
        let release_blocking: Bool
    }
    let schema_version: String
    let run_id: String
    let output_seal_sha256: String
    let master_sha256: String?
    let plan_sha256: String
    let repair_tasks: [Item]

    func validate(runID: String, sealSHA: String, masterSHA: String) throws {
        guard schema_version == "nalu.postproduction-repair-plan/v1",
              run_id == runID, output_seal_sha256 == sealSHA, master_sha256 == masterSHA,
              EpisodeDialogueStageReceipt.validSHA(plan_sha256),
              !repair_tasks.isEmpty, repair_tasks.allSatisfy(\.release_blocking) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }
}
