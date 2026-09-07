import Foundation
import Observation

/// Provider completion is not creative acceptance or verified billing.
struct VideoTaskObservation: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let binding_id: String
        let task_id: String
        let status: String
        let result_urls: [String]
        let observation_sha256: String
        let billing_verified: Bool
        let generation_performed: Bool
        let master_accepted: Bool
    }
}

struct VideoCandidateEnvelope: Decodable {
    let candidate: VideoCandidate?
    private enum CodingKeys: String, CodingKey { case event_type }
    init(from decoder: Decoder) throws {
        let type = try decoder.container(keyedBy: CodingKeys.self).decode(String.self, forKey: .event_type)
        candidate = type == "video_result_materialized" ? try VideoCandidate(from: decoder) : nil
    }
}

@MainActor @Observable final class VideoCandidateModel {
    let binding: VideoSubmissionObservation
    private let runtime: RuntimeClient
    private let key: () async throws -> String?
    var busy = false
    var notice = "可以查询这个镜头的生成进度。"
    var fileURL: URL?

    init(binding: VideoSubmissionObservation, runtime: RuntimeClient = RuntimeClient(),
         key: @escaping () async throws -> String? = {
             try await Task.detached { try KeychainSecretStore().secret(for: .seedance, allowAuthenticationUI: false) }.value
         }) {
        self.binding = binding; self.runtime = runtime; self.key = key
    }

    /// Opening/reopening uses only saved local receipts. It never queries or generates.
    func restore() async {
        guard !busy, fileURL == nil else { return }
        busy = true; defer { busy = false }
        do {
            if let candidate = try await runtime.savedVideoCandidates(binding).first {
                try await open(candidate)
            }
        } catch { notice = "本地视频暂时无法读取。可以再试一次，原任务不会重新生成。" }
    }

    func refresh() async {
        guard !busy else { return }
        busy = true; defer { busy = false }
        notice = "正在查询已有镜头，不会重新提交生成。"
        do {
            if let saved = try await runtime.savedVideoCandidates(binding).first {
                try await open(saved); return
            }
            guard let secret = try await key(), !secret.isEmpty else {
                notice = "暂时无法读取已保存的制作凭据，原任务保留。"; return
            }
            let observed = try await runtime.refreshVideoTask(binding, apiKey: secret)
            guard observed.payload.status == "completed" else {
                notice = ["failed", "error"].contains(observed.payload.status)
                    ? "这个镜头生成失败。任务记录已保留，没有自动重做。"
                    : "这个镜头还在生成。稍后可以再次查询，不会重复生成。"
                return
            }
            notice = "镜头已生成，正在取回视频。"
            let candidate = try await runtime.materializeVideo(observed, binding: binding)
            try await open(candidate)
        } catch { notice = "这次查询或取回视频未成功。原任务保留，再试一次不会重新生成。" }
    }

    private func open(_ candidate: VideoCandidate) async throws {
        let url = try await runtime.downloadVideoCandidate(candidate, binding: binding)
        guard !Task.isCancelled else { try? FileManager.default.removeItem(at: url); return }
        discardPlayback()
        fileURL = url
        notice = "视频已取回，可以播放查看。它还不是已验收的成片，不会自动发行。"
    }

    func discardPlayback() {
        if let fileURL { try? FileManager.default.removeItem(at: fileURL) }
        fileURL = nil
    }
}

struct VideoCandidate: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let observation_id: String
        let observation_sha256: String
        let binding_id: String
        let result_index: Int
        let task_key: String
        let request_sha256: String
        let video_downloaded: Bool
        let generation_performed: Bool
        let billing_verified: Bool
        let visual_semantics_verified: Bool
        let master_accepted: Bool
        let materialization_sha256: String?
        let video: Media?
    }
    struct Media: Decodable, Sendable {
        let sha256: String
        let byte_size: Int
    }
}
