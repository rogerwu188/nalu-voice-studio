import Foundation

struct EpisodeOutputHandoff {
    let body: Data
    let masterSHA: String

    init(materialization: Data) throws {
        guard let object = try JSONSerialization.jsonObject(with: materialization) as? [String: Any] else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let kinds = ["master": "master_video", "captions": "captions",
                     "postproduction_manifest": "postproduction_manifest", "shot_manifest": "shot_manifest"]
        var candidates: [[String: String]] = []
        var master = ""
        for field in kinds.keys.sorted() {
            guard let artifact = object[field] as? [String: Any],
                  let kind = artifact["kind"] as? String, kind == kinds[field],
                  let path = artifact["relative_path"] as? String, !path.isEmpty,
                  !path.hasPrefix("/"), !path.contains("\\"),
                  !path.components(separatedBy: "/").contains(where: { ["", ".", ".."].contains($0) }),
                  let media = artifact["media_type"] as? String, !media.isEmpty,
                  let sha = artifact["sha256"] as? String, EpisodeDialogueStageReceipt.validSHA(sha) else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            if field == "master" { master = sha }
            candidates.append(["kind": kind, "relative_path": path, "media_type": media])
        }
        guard Set(candidates.compactMap { $0["relative_path"] }).count == 4 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        masterSHA = master
        body = try JSONSerialization.data(withJSONObject: ["artifacts": candidates, "sealed_by": "nalu-native-user"], options: [.sortedKeys])
    }
}
