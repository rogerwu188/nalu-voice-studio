import AVFoundation
import Foundation
import Observation

struct EpisodeEditCut: Codable, Equatable, Sendable {
    let shot_index: Int
    var source_in_seconds: Double
    var source_out_seconds: Double
}

struct EpisodeEditingEvent: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Item: Decodable, Sendable {
        let shot_index: Int
        let task_key: String
        let source_duration_seconds: Double
    }
    struct Source: Decodable, Sendable {
        let shot_id: String
        let source_in_seconds: Double
        let source_out_seconds: Double
    }
    struct Payload: Decodable, Sendable {
        let plan_id: String
        let plan_sha256: String
        let input_sha256: String?
        let source_input_sha256: String?
        let edit_sha256: String?
        let items: [Item]
        let shots: [Source]
        let edited_duration_seconds: Double?
        let edit_approved: Bool?
        let generation_performed: Bool
        let master_accepted: Bool
    }
}

struct EpisodeEditEnvelope: Decodable {
    let edit: EpisodeEditingEvent?
    private enum CodingKeys: String, CodingKey { case event_type }
    init(from decoder: Decoder) throws {
        let type = try decoder.container(keyedBy: CodingKeys.self).decode(String.self, forKey: .event_type)
        edit = type == "postproduction_edit_drafted" ? try EpisodeEditingEvent(from: decoder) : nil
    }
}

struct EpisodeInputEnvelope: Decodable {
    let inputs: EpisodeEditingEvent?
    private enum CodingKeys: String, CodingKey { case event_type }
    init(from decoder: Decoder) throws {
        let type = try decoder.container(keyedBy: CodingKeys.self).decode(String.self, forKey: .event_type)
        inputs = type == "postproduction_shot_inputs_staged" ? try EpisodeEditingEvent(from: decoder) : nil
    }
}

@MainActor @Observable final class EpisodeEditingModel {
    let runID: String
    let planID: String
    let planSHA: String
    private let runtime: RuntimeClient
    private(set) var inputs: EpisodeEditingEvent?
    private(set) var saved: EpisodeEditingEvent?
    private(set) var cuts: [EpisodeEditCut] = []
    private(set) var busy = false
    private(set) var picture: EpisodePicture?
    var previewURL: URL? { picture?.fileURL }
    private(set) var notice = "先播放并采用本集每个镜头，再整理剪辑。原视频会保留。"

    init(runID: String, planID: String, planSHA: String, runtime: RuntimeClient = RuntimeClient()) {
        self.runID = runID; self.planID = planID; self.planSHA = planSHA; self.runtime = runtime
    }

    func load() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let existing = try await runtime.recoverEpisodeInputs(runID: runID, planID: planID, planSHA: planSHA)
            let result: EpisodeEditingEvent
            if let existing {
                result = existing
            } else {
                result = try await runtime.stageEpisodeInputs(runID: runID, planID: planID, planSHA: planSHA)
            }
            // Reload never discards local edits when the source version is unchanged.
            if inputs?.payload.input_sha256 != result.payload.input_sha256 {
                guard cuts.isEmpty else {
                    notice = "视频版本变了。您的剪辑调整仍保留，请先核对新旧素材。"
                    return
                }
                let recovered = try await runtime.latestEpisodeEdit(inputs: result)
                if let recovered {
                    cuts = recovered.payload.shots.enumerated().map { index, source in
                        EpisodeEditCut(shot_index: index, source_in_seconds: source.source_in_seconds,
                            source_out_seconds: source.source_out_seconds)
                    }
                    saved = recovered
                } else {
                    cuts = result.payload.items.map { EpisodeEditCut(shot_index: $0.shot_index,
                        source_in_seconds: 0, source_out_seconds: $0.source_duration_seconds) }
                }
            }
            inputs = result
            notice = saved == nil ? "素材已整理。可逐镜头去掉多余的开头或结尾，再保存剪辑草稿。"
                : "已恢复保存的剪辑草稿。您可以接着修改；草稿还不是确认后的成片。"
        } catch { notice = "暂时无法整理：请先确认每个镜头都已采用。已有剪辑和原视频没有丢失。" }
    }

    func trim(index: Int, beginning: Bool) {
        guard !busy, cuts.indices.contains(index), cuts[index].source_out_seconds - cuts[index].source_in_seconds > 0.5 else { return }
        if beginning { cuts[index].source_in_seconds += 0.5 } else { cuts[index].source_out_seconds -= 0.5 }
        saved = nil; discardPreview()
    }

    func reset(index: Int) {
        guard !busy, cuts.indices.contains(index), let item = inputs?.payload.items[index] else { return }
        cuts[index] = EpisodeEditCut(shot_index: index, source_in_seconds: 0, source_out_seconds: item.source_duration_seconds)
        saved = nil; discardPreview()
    }

    var canSave: Bool {
        guard !busy, let inputs, cuts.count == inputs.payload.items.count, !cuts.isEmpty else { return false }
        return zip(cuts, inputs.payload.items).allSatisfy { cut, item in
            cut.source_out_seconds > cut.source_in_seconds &&
            (cut.source_in_seconds > 0.05 || cut.source_out_seconds < item.source_duration_seconds - 0.05)
        }
    }

    func save() async {
        guard canSave, let inputs else { return }
        busy = true
        defer { busy = false }
        do {
            let edit = try await runtime.saveEpisodeEdit(inputs: inputs, cuts: cuts)
            saved = edit
            do {
                try await runtime.retimeEpisodeSound(edit: edit)
                notice = "剪辑草稿已保存，约 \(Int((edit.payload.edited_duration_seconds ?? 0).rounded())) 秒。字幕和声音清单已按新时长整理；仍需预览确认、配音和逐句对齐，不会自动发行。"
            } catch {
                notice = "剪辑已保存，但字幕时间线暂未同步。您的调整和视频都保留；再次保存可重试，不会重新生成视频。"
            }
        } catch { notice = "这次保存未成功，您的调整仍保留。可以重试；没有覆盖原视频。" }
    }

    func preview() async {
        guard !busy, let edit = saved else { return }
        busy = true
        discardPreview()
        notice = "正在本机拼接画面预览，没有配音，也不会提交新的生成任务。"
        defer { busy = false }
        do {
            let downloaded = try await runtime.downloadEpisodePicturePreview(edit: edit)
            let file = downloaded.fileURL
            do {
                let asset = AVURLAsset(url: file)
                let playable = try await asset.load(.isPlayable)
                let duration = try await asset.load(.duration)
                guard playable, duration.seconds.isFinite, let expected = edit.payload.edited_duration_seconds,
                      abs(duration.seconds - expected) < 0.1 else { throw LibrarySnapshotRefreshError.contextChanged }
            } catch {
                try? FileManager.default.removeItem(at: file)
                throw error
            }
            guard !Task.isCancelled, saved?.payload.edit_sha256 == edit.payload.edit_sha256 else {
                try? FileManager.default.removeItem(at: file)
                return
            }
            picture = downloaded
            notice = "无配音画面预览已准备好。请播放检查顺序和节奏；这不是最终成片。"
        } catch { notice = "这次画面预览未成功，剪辑草稿仍保留。可以重试；不会重新生成镜头。" }
    }

    func discardPreview() {
        if let previewURL { try? FileManager.default.removeItem(at: previewURL) }
        picture = nil
    }
}
