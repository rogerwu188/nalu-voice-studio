import Foundation
import Observation

@MainActor @Observable final class RecordingCaptionModel {
    let transcript: RecordingTranscriptRecord
    private let runtime: RuntimeClient
    var texts: [String]
    private var timedSegments: [SemanticASRSegmentDraft]
    var busy = false
    var loaded = false
    var recovery: RecordingCaptionRecovery?
    var pending: RecordingCaptionSubmission?
    var attempted = false
    var notice = "正在读取字幕确认记录。"

    init(transcript: RecordingTranscriptRecord, runtime: RuntimeClient = RuntimeClient()) {
        self.transcript = transcript; self.runtime = runtime
        texts = transcript.payload.segments.map(\.text)
        timedSegments = transcript.payload.segments
    }

    var readback: String { (pending?.segments.map(\.text) ?? texts).joined(separator: " ") }

    func load() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let value = try await runtime.recoverCaptionReview(transcript: transcript)
            let firstLoad = recovery == nil
            recovery = value; loaded = true
            if let pending {
                if value.applies_to_current_transcript, let p = value.latest_review?.payload,
                   p.segments == pending.segments, p.confirmation == pending.confirmation,
                   p.reviewed_by == pending.reviewed_by,
                   p.expected_previous_review_id == pending.expected_previous_review_id {
                    self.pending = nil
                    attempted = false
                    notice = "已找到刚才保存的字幕确认。"
                } else { notice = "还没有找到刚才的确认，修改已保留，可以重试保存。" }
            } else if firstLoad, value.applies_to_current_transcript, let words = value.latest_review?.payload.segments {
                texts = words.map(\.text)
                timedSegments = words
                notice = "已恢复确认过的字幕。您仍可以修改后再次确认。"
            } else {
                notice = "请核对字幕，错字可以直接修改；时间保留不变。"
            }
        } catch {
            loaded = false
            notice = "没有读到字幕确认记录。修改已保留，请再核对一次。"
        }
    }

    func prepare() -> Bool {
        guard loaded, !busy, pending == nil, texts.count == timedSegments.count else { return false }
        let words = zip(timedSegments, texts).map { word, text in
            SemanticASRSegmentDraft(startSeconds: word.startSeconds, endSeconds: word.endSeconds,
                text: text.trimmingCharacters(in: .whitespacesAndNewlines), confidence: nil)
        }
        let draft = RecordingCaptionSubmission(expected_transcript_sha256: transcript.payload.transcript_sha256,
            expected_previous_review_id: recovery?.latest_review?.id, segments: words,
            reviewed_by: "local-user", confirmation: "我已核对并确认这段录音的字幕。")
        do { try draft.validate(sampleCount: transcript.payload.sample_count) }
        catch { notice = "请保留每一段字幕的文字，并缩短过长的内容。"; return false }
        pending = draft
        attempted = false
        return true
    }

    func cancelUnsubmitted() {
        guard !busy, !attempted else { return }
        pending = nil
    }

    func confirm() async {
        guard !busy, let pending else { return }
        busy = true
        attempted = true
        defer { busy = false }
        do {
            let saved = try await runtime.saveCaptionReview(transcript: transcript, draft: pending)
            recovery = RecordingCaptionRecovery(current_transcript_id: transcript.id, latest_review: saved,
                applies_to_current_transcript: true, captions_approved: true)
            self.pending = nil
            attempted = false
            notice = "这段字幕已确认。成片仍需混音和最终检查。"
        } catch {
            notice = "字幕确认结果尚未核实。修改已保留，请核对记录或重试原来的保存。"
        }
    }
}
