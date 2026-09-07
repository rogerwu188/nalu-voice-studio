import Foundation
import Observation

struct EpisodeEditReviewDraft: Encodable, Sendable {
    let expected_edit_sha256: String
    let preview_id: String
    let expected_preview_sha256: String
    let expected_review_id: String?
    let decision: VideoReviewDecision
    let reviewed_by: String
    let confirmation: String
}

struct EpisodeEditReview: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let edit_id: String
        let edit_sha256: String
        let preview_id: String
        let preview_sha256: String
        let decision: VideoReviewDecision
        let reviewed_by: String
        let confirmation: String
        let edit_approved: Bool
        let duration_confirmed_seconds: Double
        let viewing_evidence: String
        let audio_approved: Bool
        let captions_approved: Bool
        let master_accepted: Bool
        let generation_performed: Bool
    }
}

struct EpisodeEditReviewEnvelope: Decodable {
    let review: EpisodeEditReview?
    private enum CodingKeys: String, CodingKey { case event_type }
    init(from decoder: Decoder) throws {
        let type = try decoder.container(keyedBy: CodingKeys.self).decode(String.self, forKey: .event_type)
        review = type == "postproduction_edit_reviewed" ? try EpisodeEditReview(from: decoder) : nil
    }
}

@MainActor @Observable final class EpisodeEditReviewModel {
    let edit: EpisodeEditingEvent
    let picture: EpisodePicture
    private let runtime: RuntimeClient
    private(set) var busy = false
    private(set) var loaded = false
    private(set) var latest: EpisodeEditReview?
    private(set) var pending: EpisodeEditReviewDraft?
    private(set) var uncertain = false
    private(set) var notice = "请先播放画面预览，再确认是否采用这个剪辑。"

    init(edit: EpisodeEditingEvent, picture: EpisodePicture, runtime: RuntimeClient = RuntimeClient()) {
        self.edit = edit; self.picture = picture; self.runtime = runtime
    }

    var readback: String {
        let seconds = Int((edit.payload.edited_duration_seconds ?? 0).rounded())
        return pending?.decision == .accept
            ? "您确认已查看这版约 \(seconds) 秒的画面，并采用它的剪辑和时长。还需要配音、字幕和成片检查，不会自动发行。确认吗？"
            : "您要将这版剪辑退回修改。原视频和剪辑记录保留，不会自动付费重做。确认吗？"
    }

    func load() async {
        guard !busy else { return }
        busy = true; loaded = false
        defer { busy = false }
        do {
            let result = try await runtime.latestEpisodeEditReview(edit: edit)
            guard !Task.isCancelled else { return }
            latest = result; loaded = true
            // An uncertain POST is resolved only by its exact recorded decision.
            if let pending, uncertain {
                if result?.payload.preview_id == pending.preview_id,
                   result?.payload.preview_sha256 == pending.expected_preview_sha256,
                   result?.payload.decision == pending.decision,
                   result?.payload.confirmation == pending.confirmation,
                   result?.payload.reviewed_by == pending.reviewed_by {
                    self.pending = nil; uncertain = false
                } else {
                    if let result, result.id != pending.expected_review_id {
                        self.pending = nil; uncertain = false
                        notice = "记录中已有新的决定。请核对当前结果后，再决定是否修改；不会重放过期确认。"
                        return
                    }
                    notice = "尚未找到刚才那次确认的结果。请重试同一确认，不要重复作出相反决定。"
                    return
                }
            }
            notice = result?.payload.edit_approved == true
                ? "这版画面剪辑已采用；配音、字幕和成片仍待验收。"
                : "请播放并查看当前剪辑，再选择采用或退回修改。"
        } catch { notice = "确认记录暂时无法读取。您可以重试核对，原视频与剪辑均保留。" }
    }

    func begin(_ decision: VideoReviewDecision) -> Bool {
        guard loaded, !busy, pending == nil, picture.editSHA == edit.payload.edit_sha256,
              picture.fileURL.isFileURL, !picture.receiptID.isEmpty else { return false }
        pending = EpisodeEditReviewDraft(expected_edit_sha256: picture.editSHA, preview_id: picture.receiptID,
            expected_preview_sha256: picture.sha256, expected_review_id: latest?.id, decision: decision,
            reviewed_by: "nalu-native-user", confirmation: decision == .accept
                ? "已查看此画面预览，确认采用此剪辑及其时长；不代表配音、字幕、成片或发行验收"
                : "已查看此画面预览，退回修改剪辑，不自动付费重做")
        return true
    }

    func cancelUnsubmitted() {
        guard !busy, !uncertain else { return }
        pending = nil
    }

    func confirm() async {
        guard !busy, let pending else { return }
        busy = true; uncertain = true
        defer { busy = false }
        do {
            latest = try await runtime.reviewEpisodeEdit(edit: edit, picture: picture, draft: pending)
            self.pending = nil; uncertain = false
            notice = latest?.payload.edit_approved == true
                ? "已记录：采用这版画面剪辑和时长。下一步继续配音、字幕和成片检查。"
                : "已记录：剪辑需要修改。原素材保留，没有自动重做。"
        } catch { notice = "确认结果还未核实。请重试同一确认或核对记录；已保存的剪辑不会丢失。" }
    }
}
