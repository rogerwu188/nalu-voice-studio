import Foundation

struct EpisodeOutputQualityFailure: Error {
    let repeatedFrames: Bool

    init(codes: [String]) {
        repeatedFrames = codes.contains("video:VIDEO_FRAME_REPEAT_EXCESSIVE")
    }

    var userMessage: String {
        if repeatedFrames {
            return "视频已经合成并保留，但画面重复过多，未通过检查。需要修复镜头后制作新版本；反复重试这一版不会改善画面。尚未验收，也没有发布。"
        }
        return "视频已经合成并保留，但画面、声音或字幕检查未通过。需要查看检查结果并修复后制作新版本；不是让您重新讲故事。尚未验收，也没有发布。"
    }
}

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
