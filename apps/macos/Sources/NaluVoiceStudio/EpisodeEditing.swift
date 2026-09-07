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

@MainActor @Observable final class EpisodeEditingModel {
    let runID: String
    let planID: String
    let planSHA: String
    private let runtime: RuntimeClient
    private(set) var inputs: EpisodeEditingEvent?
    private(set) var saved: EpisodeEditingEvent?
    private(set) var cuts: [EpisodeEditCut] = []
    private(set) var busy = false
    private(set) var notice = "先播放并采用本集每个镜头，再整理剪辑。原视频会保留。"

    init(runID: String, planID: String, planSHA: String, runtime: RuntimeClient = RuntimeClient()) {
        self.runID = runID; self.planID = planID; self.planSHA = planSHA; self.runtime = runtime
    }

    func load() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let result = try await runtime.stageEpisodeInputs(runID: runID, planID: planID, planSHA: planSHA)
            // Reload never discards local edits when the source version is unchanged.
            if inputs?.payload.input_sha256 != result.payload.input_sha256 {
                guard cuts.isEmpty else {
                    notice = "视频版本变了。您的剪辑调整仍保留，请先核对新旧素材。"
                    return
                }
                cuts = result.payload.items.map { EpisodeEditCut(shot_index: $0.shot_index,
                    source_in_seconds: 0, source_out_seconds: $0.source_duration_seconds) }
            }
            inputs = result
            notice = "素材已整理。可逐镜头去掉多余的开头或结尾，再保存剪辑草稿。"
        } catch { notice = "暂时无法整理：请先确认每个镜头都已采用。已有剪辑和原视频没有丢失。" }
    }

    func trim(index: Int, beginning: Bool) {
        guard !busy, cuts.indices.contains(index), cuts[index].source_out_seconds - cuts[index].source_in_seconds > 0.5 else { return }
        if beginning { cuts[index].source_in_seconds += 0.5 } else { cuts[index].source_out_seconds -= 0.5 }
        saved = nil
    }

    func reset(index: Int) {
        guard !busy, cuts.indices.contains(index), let item = inputs?.payload.items[index] else { return }
        cuts[index] = EpisodeEditCut(shot_index: index, source_in_seconds: 0, source_out_seconds: item.source_duration_seconds)
        saved = nil
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
            saved = try await runtime.saveEpisodeEdit(inputs: inputs, cuts: cuts)
            notice = "剪辑草稿已保存，约 \(Int((saved?.payload.edited_duration_seconds ?? 0).rounded())) 秒。还需预览确认、对齐字幕和配音，不会自动发行。"
        } catch { notice = "这次保存未成功，您的调整仍保留。可以重试；没有覆盖原视频。" }
    }
}
