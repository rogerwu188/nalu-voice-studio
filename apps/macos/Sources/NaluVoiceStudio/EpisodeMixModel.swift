import Foundation
import Observation

@MainActor @Observable final class EpisodeMixModel {
    private let prepareMix: @MainActor ([EpisodeSoundSourceReceipt.Source]) async throws -> EpisodePreparedMix
    private let renderMix: @MainActor (EpisodePreparedMix) async throws -> EpisodeRenderedMix
    private(set) var busy = false
    private(set) var prepared: EpisodePreparedMix?
    private(set) var result: EpisodeRenderedMix?
    private(set) var attempted = false
    private(set) var notice = "声音素材准备好后，可以核对并合成这一集。"

    init(sound: EpisodeSoundPlan, runtime: RuntimeClient = RuntimeClient(),
         prepareMix: (@MainActor ([EpisodeSoundSourceReceipt.Source]) async throws -> EpisodePreparedMix)? = nil,
         renderMix: (@MainActor (EpisodePreparedMix) async throws -> EpisodeRenderedMix)? = nil) {
        self.prepareMix = prepareMix ?? { sources in
            let current = try await runtime.prepareEpisodeDialogue(sound: sound)
            let dialogue = try await runtime.stageEpisodeDialogue(sound: sound, preparation: current)
            return try await runtime.prepareEpisodeMix(sound: sound, dialogue: dialogue, sources: sources)
        }
        self.renderMix = renderMix ?? { try await runtime.renderEpisodeMix($0) }
    }

    func prepare(sources: [EpisodeSoundSourceReceipt.Source]) async {
        guard !busy, !attempted, prepared == nil else { return }
        busy = true
        notice = "正在核对已确认的剪辑、配音、字幕和声音素材。"
        defer { busy = false }
        do {
            let mix = try await prepareMix(sources)
            try Task.checkCancellation()
            prepared = mix
            notice = "制作方案已准备好。确认后会在这台 Mac 合成视频，不会自动发布。"
        } catch {
            notice = "还不能合成。请核对每段录音、字幕和声音素材是否已确认，再重新核对；已有内容保留。"
        }
    }

    func renderConfirmed() async {
        guard !busy, result == nil, let prepared else { return }
        busy = true; attempted = true
        notice = "正在本机合成这一集，可能需要一些时间。完成后仍要检查画面、声音和字幕。"
        defer { busy = false }
        do {
            let rendered = try await renderMix(prepared)
            try rendered.validate(prepared)
            try Task.checkCancellation()
            result = rendered
            notice = "这一集已合成，等待成片检查；尚未验收，也没有发布。"
        } catch {
            notice = "合成结果还未核实。原制作方案已保留，可重试核对同一版。关闭页面不代表后台已停止。"
        }
    }

    func changeSelection() {
        guard !busy, !attempted else { return }
        prepared = nil
        notice = "可以调整素材。调整后需要重新核对制作方案。"
    }
}
