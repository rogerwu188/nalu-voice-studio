import Foundation
import Observation

struct VideoReservationEnvelope: Decodable {
    let reservation: VideoCostReservation?
    private enum CodingKeys: String, CodingKey { case event_type }
    init(from decoder: Decoder) throws {
        let kind = try decoder.container(keyedBy: CodingKeys.self).decode(String.self, forKey: .event_type)
        if kind == "video_estimate_reserved" { reservation = try VideoCostReservation(from: decoder) }
        else { reservation = nil }
    }
}

struct VideoCostApproval: Codable, Equatable, Sendable {
    let preparation_sha256: String
    let estimated_credits: Int
    let confirmed_run_budget_credits: Int
    let approved_by: String
    let confirmation: String
    let guardian_approval: Bool
    let pricing_quote_id: String
}

struct VideoCostReservation: Decodable, Sendable {
    let id: String
    let run_id: String
    let event_type: String
    let payload: Payload
    struct Payload: Decodable, Sendable {
        let preparation_id: String
        let preparation_sha256: String
        let estimated_credits: Int
        let confirmed_run_budget_credits: Int
        let pricing_quote_id: String
        let guardian_approval: Bool
        let task_key: String
        let request_sha256: String
        let published_price_observed: Bool
        let generation_performed: Bool
    }
}

struct VideoSubmissionObservation: Decodable, Sendable {
    let id: String
    let run_id: String
    let task_key: String
    let request_sha256: String
    let state: String
    let provider_task_id: String?
}

@MainActor @Observable final class VideoGenerationModel {
    let prepared: FrameProductionEvent
    private let runtime: RuntimeClient
    private let key: () async throws -> String?
    var busy = false
    var loaded = false
    var reservation: VideoCostReservation?
    var submission: VideoSubmissionObservation?
    var draft: VideoCostApproval?
    var notice: String?
    var observationKnown = false

    init(prepared: FrameProductionEvent, runtime: RuntimeClient = RuntimeClient(),
         key: @escaping () async throws -> String? = {
             try await Task.detached { try KeychainSecretStore().secret(for: .seedance, allowAuthenticationUI: false) }.value
         }) {
        self.prepared = prepared; self.runtime = runtime; self.key = key
    }

    var canResume: Bool { loaded && !busy && reservation != nil && observationKnown && submission == nil }
    var readback: String {
        let amount = reservation?.payload.estimated_credits ?? draft?.estimated_credits
        let budget = reservation?.payload.confirmed_run_budget_credits ?? draft?.confirmed_run_budget_credits
        guard let amount, let budget else { return "请先查看当前费用并确认本集制作预算。" }
        return "这个镜头预计 \(amount) 积分，本集已确认的预计预算为 \(budget) 积分。实际账单可能不同，这不是服务商保证的扣费上限。确认后会提交生成并可能收费，不会自动发行。"
    }

    func load() async {
        guard !busy else { return }
        busy = true; loaded = false; observationKnown = false; draft = nil
        defer { busy = false }
        do {
            let saved = try await runtime.savedVideoReservations(runID: prepared.run_id)
            let matches = saved.filter { $0.payload.task_key == prepared.payload.task_key }
            guard matches.count <= 1 else { throw LibrarySnapshotRefreshError.contextChanged }
            if let found = matches.first {
                guard found.run_id == prepared.run_id, found.payload.preparation_id == prepared.id,
                      found.payload.preparation_sha256 == prepared.payload.preparation_sha256,
                      found.payload.request_sha256 == prepared.payload.request_sha256 else {
                    throw LibrarySnapshotRefreshError.contextChanged
                }
                reservation = found
                submission = try await runtime.observeVideoSubmission(found)
                observationKnown = true
                notice = submissionMessage
            } else {
                reservation = nil; submission = nil
                notice = nil
            }
            guard !Task.isCancelled else { return }
            loaded = true
        } catch {
            notice = "暂时无法核对镜头的已有费用或提交记录。请先重新核对，不会重新生成。"
        }
    }

    func review(price: VideoPriceObservation, guardianApproved: Bool) async -> Bool {
        guard loaded, !busy, reservation == nil else { return false }
        busy = true; draft = nil
        defer { busy = false }
        do {
            let run = try await runtime.productionRun(runID: prepared.run_id)
            guard run.id == prepared.run_id, !run.dryRun, run.status == "waiting_for_approval",
                  let budget = run.estimatedBudgetCredits, budget > 0,
                  price.run_id == prepared.run_id, price.payload.preparation_id == prepared.id,
                  price.event_type == "video_price_observed", !price.payload.provider_charge_cap_guaranteed,
                  price.payload.preparation_sha256 == prepared.payload.preparation_sha256,
                  price.payload.published_price_observed, !price.payload.generation_performed,
                  price.payload.estimated_credits > 0, price.payload.estimated_credits <= budget,
                  price.isCurrent, !Task.isCancelled else { throw LibrarySnapshotRefreshError.contextChanged }
            draft = VideoCostApproval(preparation_sha256: price.payload.preparation_sha256,
                estimated_credits: price.payload.estimated_credits, confirmed_run_budget_credits: budget,
                approved_by: "nalu-native-user", confirmation: "用户明确确认本镜头预计费用并同意提交生成。",
                guardian_approval: guardianApproved, pricing_quote_id: price.id)
            notice = readback
            return true
        } catch {
            notice = "请先确认本集制作预算，并重新查看当前镜头费用。原画面和任务保留，没有提交生成。"
            return false
        }
    }

    /// Called only by the final confirmation action, never by load/refresh.
    func confirm() async {
        guard loaded, !busy, (draft != nil || canResume) else { return }
        busy = true
        defer { busy = false }
        do {
            if reservation == nil {
                guard let draft else { return }
                reservation = try await runtime.reserveVideoCost(runID: prepared.run_id, preparationID: prepared.id, approval: draft)
                self.draft = nil
            }
            guard let reservation else { return }
            guard reservation.payload.task_key == prepared.payload.task_key,
                  reservation.payload.request_sha256 == prepared.payload.request_sha256 else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            // A receipt may have arrived after the dialog opened. Reconcile
            // before any secret lookup or submission.
            submission = try await runtime.observeVideoSubmission(reservation)
            observationKnown = true
            if submission != nil { notice = submissionMessage; return }
            guard !Task.isCancelled, let secret = try await key(), !secret.isEmpty else {
                notice = "费用确认已保留，但当前无法读取已保存的模型密钥。没有提交生成；稍后核对后可继续原任务。"
                return
            }
            observationKnown = false
            submission = try await runtime.submitReservedVideo(reservation, apiKey: secret)
            observationKnown = true
            notice = submissionMessage
        } catch {
            observationKnown = false
            notice = "这次提交结果尚未核对。费用和任务记录保留，请点“核对提交状态”；不会自动重新提交或扣费。"
        }
    }

    var submissionMessage: String {
        guard let submission else { return "费用确认已保存，目前没有查到提交记录。继续前会再核对一次原任务。" }
        switch submission.state {
        case "submitted": return "镜头任务已提交，正在等待生成结果；不要重复提交。"
        case "completed": return "已记录生成完成状态，仍需取回视频并检查质量，尚未形成可发行成片。"
        case "ambiguous_charge": return "服务商是否接单或扣费还不确定，任务已保留等待核对，不会自动重发。"
        case "zero_charge_failed": return "镜头任务已记录为未扣费失败；不会自动重新生成。"
        case "cancelled": return "镜头任务已记录为取消；已有记录保留，不会重新提交。"
        default: return "已有镜头任务记录，正在等待状态核对，不会重新提交。"
        }
    }
}
