import CryptoKit
import Foundation

actor RuntimeClient {
    private let baseURL: URL
    private let session: URLSession
    private let accessCheck: @Sendable () async -> Bool
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(
        baseURL: URL? = nil,
        session: URLSession? = nil,
        accessCheck: @escaping @Sendable () async -> Bool = {
            await RuntimeSupervisor.shared.ownsReadyRuntime
        }
    ) {
        self.baseURL = baseURL ?? (try? RuntimeEndpointConfiguration.baseURL(
            inherited: ProcessInfo.processInfo.environment
        )) ?? URL(string: "http://127.0.0.1:8765")!
        self.accessCheck = accessCheck
        if let session {
            self.session = session
            return
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 10
        self.session = URLSession(configuration: configuration)
    }

    func health() async throws -> RuntimeHealth {
        let (data, response) = try await authorizedData(
            from: baseURL.appending(path: "health")
        )
        try validate(response, data: data)
        return try decoder.decode(RuntimeHealth.self, from: data)
    }

    func storageDiagnostics() async throws -> StorageDiagnostics {
        try await get("v1/diagnostics/storage")
    }

    func listProjects(includeArchived: Bool = false) async throws -> [NaluProject] {
        var components = URLComponents(
            url: baseURL.appending(path: "v1/projects"), resolvingAgainstBaseURL: false
        )!
        if includeArchived {
            components.queryItems = [URLQueryItem(name: "include_archived", value: "true")]
        }
        let (data, response) = try await authorizedData(from: components.url!)
        try validate(response, data: data)
        return try decoder.decode([NaluProject].self, from: data)
    }

    func renameProject(id: String, title: String) async throws -> NaluProject {
        try await send("v1/projects/\(id)", method: "PATCH", body: ProjectRenameDraft(title: title))
    }

    func archiveProject(id: String, archived: Bool = true) async throws -> NaluProject {
        try await post(
            "v1/projects/\(id)/archive", body: ProjectArchiveDraft(archived: archived)
        )
    }

    func exportProject(id: String) async throws -> Data {
        let (data, response) = try await authorizedData(
            from: baseURL.appending(path: "v1/projects/\(id)/export")
        )
        try validate(response, data: data)
        return data
    }

    func restoreProject(data: Data) async throws -> NaluProject {
        var request = URLRequest(url: baseURL.appending(path: "v1/project-imports"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = data
        let (responseData, response) = try await authorizedData(for: request)
        try validate(response, data: responseData)
        return try decoder.decode(NaluProject.self, from: responseData)
    }

    func listAssets(projectID: String) async throws -> [NaluAsset] {
        try await get("v1/projects/\(projectID)/assets")
    }

    func importAsset(
        projectID: String,
        data: Data,
        filename: String,
        contentType: String,
        kind: String,
        name: String,
        subjectName: String,
        seasonID: String?,
        episodeID: String?,
        consentGranted: Bool,
        guardianApproved: Bool,
        consentStatement: String
    ) async throws -> NaluAsset {
        var components = URLComponents(
            url: baseURL.appending(path: "v1/projects/\(projectID)/asset-imports"),
            resolvingAgainstBaseURL: false
        )!
        var items = [
            URLQueryItem(name: "filename", value: filename),
            URLQueryItem(name: "kind", value: kind),
            URLQueryItem(name: "name", value: name),
            URLQueryItem(name: "subject_name", value: subjectName),
            URLQueryItem(name: "consent_granted", value: consentGranted ? "true" : "false"),
            URLQueryItem(name: "consent_scope", value: "project_only"),
            URLQueryItem(name: "guardian_approved", value: guardianApproved ? "true" : "false"),
            URLQueryItem(name: "consent_granted_by", value: consentGranted ? "local-user" : ""),
            URLQueryItem(name: "consent_statement", value: consentStatement),
        ]
        if let seasonID { items.append(URLQueryItem(name: "season_id", value: seasonID)) }
        if let episodeID { items.append(URLQueryItem(name: "episode_id", value: episodeID)) }
        components.queryItems = items
        var request = URLRequest(url: components.url!)
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        request.httpBody = data
        let (responseData, response) = try await authorizedData(for: request)
        try validate(response, data: responseData)
        return try decoder.decode(NaluAsset.self, from: responseData)
    }

    func revokeAssetConsent(assetID: String) async throws -> AssetConsentRecord {
        try await post(
            "v1/assets/\(assetID)/consent-revocations",
            body: AssetConsentRevocationDraft(
                requestedBy: "local-user", reason: "用户在本机撤销素材授权"
            )
        )
    }

    func privacyExport(projectID: String) async throws -> Data {
        let (data, response) = try await authorizedData(
            from: baseURL.appending(path: "v1/projects/\(projectID)/privacy-export")
        )
        try validate(response, data: data)
        return data
    }

    func assetDependencies(assetID: String) async throws -> AssetDependencyReport {
        try await get("v1/assets/\(assetID)/dependencies")
    }

    func deleteAsset(assetID: String) async throws {
        var request = URLRequest(url: baseURL.appending(path: "v1/assets/\(assetID)"))
        request.httpMethod = "DELETE"
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
    }

    func projectDeletionPreview(projectID: String) async throws -> ProjectDeletionPreview {
        try await get("v1/projects/\(projectID)/deletion-preview")
    }

    func deleteProject(
        projectID: String, confirmationTitle: String, deleteProductionSnapshots: Bool
    ) async throws -> ProjectDeletionResult {
        try await send(
            "v1/projects/\(projectID)",
            method: "DELETE",
            body: ProjectDeletionDraft(
                confirmationTitle: confirmationTitle,
                requestedBy: "local-user",
                deleteProductionSnapshots: deleteProductionSnapshots
            )
        )
    }

    func createProject(_ draft: ProjectDraft) async throws -> NaluProject {
        try await post("v1/projects", body: draft)
    }

    func interactiveStory(projectID: String) async throws -> InteractiveStoryState {
        try await get("v1/projects/\(projectID)/interactive-story")
    }

    func readSourceText(projectID: String, url: String) async throws -> PublicSourceText {
        var components = URLComponents(url: baseURL.appending(path: "v1/projects/\(projectID)/source-text"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "url", value: url)]
        var request = URLRequest(url: components.url!)
        request.timeoutInterval = 60
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(PublicSourceText.self, from: data)
    }

    func appendStoryInput(projectID: String, input: InteractiveStoryInput) async throws -> InteractiveStoryState {
        try await post("v1/projects/\(projectID)/interactive-story/turns", body: input)
    }

    func saveStoryAnswer(
        projectID: String, turnID: String, answer: InteractiveStoryAnswerRequest
    ) async throws -> InteractiveStoryState {
        try await post("v1/projects/\(projectID)/interactive-story/turns/\(turnID)/answer", body: answer)
    }

    func generateStoryAnswer(projectID: String, turnID: String, revision: Int,
                             model: String, apiKey: String) async throws -> InteractiveStoryState {
        var request = URLRequest(url: baseURL.appending(path:
            "v1/projects/\(projectID)/interactive-story/turns/\(turnID)/generate"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "X-Nalu-Writer-Key")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "expected_revision": revision, "model": model,
        ])
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(InteractiveStoryState.self, from: data)
    }

    func currentShotPlan(runID: String) async throws -> EpisodeShotPlanEvent? {
        try await get("v1/production-runs/\(runID)/shot-plans/current")
    }

    func prepareReviewedVideo(runID: String, planID: String, draft: ReviewedVideoDraft) async throws -> FrameProductionEvent {
        try await post("v1/production-runs/\(runID)/shot-plans/\(planID)/video-preparations", body: draft)
    }

    func prepareContinuousVideo(runID: String, planID: String, planSHA: String, shotIndex: Int) async throws -> FrameProductionEvent {
        struct Draft: Encodable { let expected_plan_sha256: String; let shot_index: Int }
        let saved: FrameProductionEvent = try await post(
            "v1/production-runs/\(runID)/shot-plans/\(planID)/continuation-preparations",
            body: Draft(expected_plan_sha256: planSHA, shot_index: shotIndex))
        guard saved.run_id == runID, saved.event_type == "video_task_prepared",
              saved.payload.approved_plan_event_id == planID, saved.payload.approved_plan_sha256 == planSHA,
              saved.payload.approved_shot_index == shotIndex, saved.payload.approved_tail_id?.isEmpty == false,
              saved.payload.approved_tail_sha256?.count == 64,
              saved.payload.generation_performed == false, saved.payload.paid_approved == false,
              !Task.isCancelled else { throw LibrarySnapshotRefreshError.contextChanged }
        return saved
    }

    func stageEpisodeInputs(runID: String, planID: String, planSHA: String) async throws -> EpisodeEditingEvent {
        let result: EpisodeEditingEvent = try await post("v1/production-runs/\(runID)/accepted-episode-inputs", body: [String: String]())
        try validateEpisodeEditing(result, runID: runID, planID: planID, planSHA: planSHA)
        guard result.event_type == "postproduction_shot_inputs_staged", result.payload.input_sha256?.count == 64 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        return result
    }

    func retimeEpisodeSound(edit: EpisodeEditingEvent, review: EpisodeEditReview? = nil) async throws {
        struct Draft: Encodable {
            let expected_plan_sha256: String; let edit_id: String; let expected_edit_sha256: String
            let expected_edit_review_id: String?
        }
        struct Receipt: Decodable {
            let run_id: String
            let event_type: String
            let payload: Payload
            struct Payload: Decodable {
                let edit_id: String
                let edit_sha256: String
                let plan_id: String
                let plan_sha256: String
                let duration_seconds: Double
                let caption_timing_basis: String
                let audio_generated: Bool
                let captions_approved: Bool
                let speech_alignment_verified: Bool
                let edit_approved: Bool
                let edit_review_id: String?
                let generation_performed: Bool
                let master_accepted: Bool
            }
        }
        guard edit.event_type == "postproduction_edit_drafted", let sha = edit.payload.edit_sha256,
              sha.count == 64 else { throw LibrarySnapshotRefreshError.contextChanged }
        if let review {
            try validateEpisodeEditReview(review, edit: edit)
            guard review.payload.edit_approved else { throw LibrarySnapshotRefreshError.contextChanged }
        }
        let receipt: Receipt = try await post("v1/production-runs/\(edit.run_id)/sound-plan-drafts",
            body: Draft(expected_plan_sha256: edit.payload.plan_sha256, edit_id: edit.id, expected_edit_sha256: sha,
                        expected_edit_review_id: review?.id))
        let sound = receipt.payload
        guard !Task.isCancelled, receipt.run_id == edit.run_id, receipt.event_type == "episode_sound_plan_drafted",
              sound.edit_id == edit.id, sound.edit_sha256 == sha, sound.plan_id == edit.payload.plan_id,
              sound.plan_sha256 == edit.payload.plan_sha256,
              sound.duration_seconds == edit.payload.edited_duration_seconds,
              sound.caption_timing_basis == (review == nil ? "DRAFT_EDIT_WINDOWS_NOT_SPEECH_ALIGNMENT" : "APPROVED_EDIT_WINDOWS_NOT_SPEECH_ALIGNMENT"),
              sound.edit_review_id == review?.id,
              !sound.audio_generated, !sound.captions_approved, !sound.speech_alignment_verified,
              sound.edit_approved == (review != nil), !sound.generation_performed, !sound.master_accepted else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }

    func latestEpisodeEdit(inputs: EpisodeEditingEvent) async throws -> EpisodeEditingEvent? {
        let events: [EpisodeEditEnvelope] = try await get("v1/production-runs/\(inputs.run_id)/events")
        let edits = events.compactMap(\.edit)
        guard edits.allSatisfy({ $0.run_id == inputs.run_id }) else { throw LibrarySnapshotRefreshError.contextChanged }
        guard let latest = edits.last(where: { $0.payload.plan_id == inputs.payload.plan_id }) else { return nil }
        try validateSavedEpisodeEdit(latest, inputs: inputs)
        return latest
    }

    private func validateSavedEpisodeEdit(_ result: EpisodeEditingEvent, inputs: EpisodeEditingEvent) throws {
        try validateEpisodeEditing(result, runID: inputs.run_id, planID: inputs.payload.plan_id, planSHA: inputs.payload.plan_sha256)
        guard result.event_type == "postproduction_edit_drafted",
              result.payload.source_input_sha256 == inputs.payload.input_sha256,
              result.payload.source_input_sha256?.count == 64,
              result.payload.edit_sha256?.count == 64, result.payload.edit_approved == false,
              result.payload.items.map(\.task_key) == inputs.payload.items.map(\.task_key),
              result.payload.shots.count == inputs.payload.items.count,
              zip(result.payload.shots, inputs.payload.items).allSatisfy({ source, item in
                  let start = source.source_in_seconds, end = source.source_out_seconds
                  return start.isFinite && end.isFinite && start >= 0 && end > start &&
                    end <= item.source_duration_seconds && (start > 0.05 || end < item.source_duration_seconds - 0.05)
              }), let duration = result.payload.edited_duration_seconds, duration.isFinite, duration > 0 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        // Backend rounds each clip at the fixed 24fps edit contract.
        let expectedDuration = result.payload.shots.reduce(0.0) { total, shot in
            total + ((shot.source_out_seconds - shot.source_in_seconds) * 24).rounded(.toNearestOrEven) / 24
        }
        guard abs(duration - expectedDuration) < 0.000001 else { throw LibrarySnapshotRefreshError.contextChanged }
    }

    func saveEpisodeEdit(inputs: EpisodeEditingEvent, cuts: [EpisodeEditCut]) async throws -> EpisodeEditingEvent {
        struct Draft: Encodable { let expected_input_sha256: String; let cuts: [EpisodeEditCut] }
        guard let sha = inputs.payload.input_sha256, sha.count == 64 else { throw LibrarySnapshotRefreshError.contextChanged }
        let result: EpisodeEditingEvent = try await post("v1/production-runs/\(inputs.run_id)/episode-edit-drafts",
            body: Draft(expected_input_sha256: sha, cuts: cuts))
        try validateSavedEpisodeEdit(result, inputs: inputs)
        try validateEpisodeEditing(result, runID: inputs.run_id, planID: inputs.payload.plan_id, planSHA: inputs.payload.plan_sha256)
        guard result.event_type == "postproduction_edit_drafted", result.payload.source_input_sha256 == sha,
              result.payload.edit_sha256?.count == 64, result.payload.edit_approved == false,
              result.payload.edited_duration_seconds.map({ $0.isFinite && $0 > 0 }) == true,
              result.payload.items.map(\.task_key) == inputs.payload.items.map(\.task_key),
              result.payload.shots.count == cuts.count,
              zip(result.payload.shots, cuts).allSatisfy({ source, cut in
                  source.source_in_seconds == cut.source_in_seconds && source.source_out_seconds == cut.source_out_seconds
              }) else { throw LibrarySnapshotRefreshError.contextChanged }
        return result
    }

    private func validateEpisodeEditing(_ event: EpisodeEditingEvent, runID: String, planID: String, planSHA: String) throws {
        let payload = event.payload
        guard !Task.isCancelled, event.run_id == runID, payload.plan_id == planID, payload.plan_sha256 == planSHA,
              !payload.generation_performed, !payload.master_accepted, !payload.items.isEmpty,
              payload.items.count == payload.shots.count, payload.items.count <= 120,
              payload.items.map(\.shot_index) == Array(payload.items.indices),
              Set(payload.items.map(\.task_key)).count == payload.items.count,
              zip(payload.items, payload.shots).allSatisfy({ item, source in
                  item.task_key == source.shot_id && item.source_duration_seconds.isFinite && item.source_duration_seconds > 0
              }) else { throw LibrarySnapshotRefreshError.contextChanged }
    }

    func observeVideoPrice(runID: String, preparationID: String) async throws -> VideoPriceObservation {
        try await post("v1/production-runs/\(runID)/video-task-preparations/\(preparationID)/price-observations",
                       body: [String: String]())
    }

    func productionRun(runID: String) async throws -> ProductionRun {
        try await get("v1/production-runs/\(runID)")
    }

    func reserveVideoCost(runID: String, preparationID: String, approval: VideoCostApproval) async throws -> VideoCostReservation {
        let saved: VideoCostReservation = try await post(
            "v1/production-runs/\(runID)/video-task-preparations/\(preparationID)/estimate-approvals", body: approval)
        guard saved.run_id == runID, saved.event_type == "video_estimate_reserved",
              saved.payload.preparation_id == preparationID,
              saved.payload.preparation_sha256 == approval.preparation_sha256,
              saved.payload.estimated_credits == approval.estimated_credits,
              saved.payload.confirmed_run_budget_credits == approval.confirmed_run_budget_credits,
              saved.payload.guardian_approval == approval.guardian_approval,
              saved.payload.pricing_quote_id == approval.pricing_quote_id,
              saved.payload.published_price_observed, !saved.payload.generation_performed,
              !Task.isCancelled else { throw LibrarySnapshotRefreshError.contextChanged }
        return saved
    }

    func savedVideoReservations(runID: String) async throws -> [VideoCostReservation] {
        let events: [VideoReservationEnvelope] = try await get("v1/production-runs/\(runID)/events")
        return events.compactMap(\.reservation)
    }

    /// Explicit submission only. Recovery uses observeVideoSubmission, never an
    /// automatic repeat POST. The runtime retains the durable single-attempt key.
    func submitReservedVideo(_ reservation: VideoCostReservation, apiKey: String) async throws -> VideoSubmissionObservation {
        var request = URLRequest(url: baseURL.appending(path:
            "v1/production-runs/\(reservation.run_id)/video-reservations/\(reservation.id)/submit"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue(apiKey, forHTTPHeaderField: "X-Nalu-Provider-Key")
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        let saved = try decoder.decode(VideoSubmissionObservation.self, from: data)
        try validateVideoSubmission(saved, reservation: reservation)
        return saved
    }

    /// Local SQLite observation: no key lookup, no provider HTTP or production.
    func observeVideoSubmission(_ reservation: VideoCostReservation) async throws -> VideoSubmissionObservation? {
        let saved: VideoSubmissionObservation? = try await get(
            "v1/production-runs/\(reservation.run_id)/video-reservations/\(reservation.id)/submission")
        if let saved { try validateVideoSubmission(saved, reservation: reservation) }
        return saved
    }

    /// Query only the already-bound provider task. Never resubmit generation.
    func refreshVideoTask(_ binding: VideoSubmissionObservation, apiKey: String) async throws -> VideoTaskObservation {
        guard let taskID = binding.provider_task_id, !taskID.isEmpty else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var request = URLRequest(url: baseURL.appending(path:
            "v1/production-runs/\(binding.run_id)/tasks/\(binding.id)/refresh"))
        request.httpMethod = "POST"
        request.setValue(apiKey, forHTTPHeaderField: "X-Nalu-Provider-Key")
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        let saved = try decoder.decode(VideoTaskObservation.self, from: data)
        guard saved.run_id == binding.run_id, saved.event_type == "provider_task_observed",
              saved.payload.binding_id == binding.id, saved.payload.task_id == taskID,
              ["pending", "processing", "completed", "failed", "error"].contains(saved.payload.status),
              !saved.payload.billing_verified, !saved.payload.generation_performed,
              !saved.payload.master_accepted, !Task.isCancelled else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        return saved
    }

    /// Download recovery is a separate idempotent operation without a provider key.
    func materializeVideo(_ observation: VideoTaskObservation, binding: VideoSubmissionObservation,
                          resultIndex: Int = 0) async throws -> VideoCandidate {
        guard observation.run_id == binding.run_id, observation.event_type == "provider_task_observed",
              observation.payload.binding_id == binding.id,
              observation.payload.task_id == binding.provider_task_id,
              observation.payload.status == "completed", (0..<4).contains(resultIndex),
              observation.payload.result_urls.indices.contains(resultIndex),
              !observation.payload.billing_verified, !observation.payload.generation_performed,
              !observation.payload.master_accepted else { throw LibrarySnapshotRefreshError.contextChanged }
        var components = URLComponents(url: baseURL.appending(path:
            "v1/production-runs/\(binding.run_id)/video-observations/\(observation.id)/materialize"),
            resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "result_index", value: String(resultIndex))]
        var request = URLRequest(url: components.url!)
        request.httpMethod = "POST"
        request.timeoutInterval = 180
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        let saved = try decoder.decode(VideoCandidate.self, from: data)
        guard saved.run_id == binding.run_id, saved.event_type == "video_result_materialized",
              saved.payload.observation_id == observation.id,
              saved.payload.observation_sha256 == observation.payload.observation_sha256,
              saved.payload.binding_id == binding.id, saved.payload.result_index == resultIndex,
              saved.payload.task_key == binding.task_key, saved.payload.request_sha256 == binding.request_sha256,
              saved.payload.video_downloaded, !saved.payload.generation_performed,
              !saved.payload.billing_verified, !saved.payload.visual_semantics_verified,
              !saved.payload.master_accepted, !Task.isCancelled else { throw LibrarySnapshotRefreshError.contextChanged }
        return saved
    }

    /// A shot's latest review can refer to a different candidate. Preserve its
    /// ID for compare-and-swap; do not pretend the current preview was adopted.
    func latestVideoReview(_ binding: VideoSubmissionObservation) async throws -> VideoReviewReceipt? {
        let events: [VideoReviewEnvelope] = try await get("v1/production-runs/\(binding.run_id)/events")
        let latest = events.compactMap(\.review).last { $0.payload.task_key == binding.task_key }
        if let latest { try validateVideoReview(latest, binding: binding) }
        return latest
    }

    func reviewVideo(_ candidate: VideoCandidate, binding: VideoSubmissionObservation,
                     draft: VideoReviewDraft) async throws -> VideoReviewReceipt {
        try validateVideoCandidate(candidate, binding: binding)
        guard let digest = candidate.payload.materialization_sha256,
              draft.expected_materialization_sha256 == digest,
              candidate.payload.video != nil else { throw LibrarySnapshotRefreshError.contextChanged }
        let saved: VideoReviewReceipt = try await post(
            "v1/production-runs/\(binding.run_id)/video-results/\(candidate.id)/reviews", body: draft)
        try validateVideoReview(saved, binding: binding)
        guard saved.payload.materialization_id == candidate.id,
              saved.payload.materialization_sha256 == digest,
              saved.payload.video_sha256 == candidate.payload.video?.sha256,
              saved.payload.preparation_id == draft.preparation_id,
              saved.payload.decision == draft.decision,
              saved.payload.reviewed_by == draft.reviewed_by,
              saved.payload.confirmation == draft.confirmation else { throw LibrarySnapshotRefreshError.contextChanged }
        return saved
    }

    private func validateVideoReview(_ review: VideoReviewReceipt, binding: VideoSubmissionObservation) throws {
        guard review.run_id == binding.run_id, review.event_type == "video_shot_reviewed",
              review.payload.binding_id == binding.id, review.payload.task_key == binding.task_key,
              review.payload.request_sha256 == binding.request_sha256,
              review.payload.user_approved == (review.payload.decision == .accept),
              !review.payload.visual_semantics_verified, !review.payload.audio_verified,
              !review.payload.billing_verified, !review.payload.master_accepted,
              !review.payload.generation_performed, !Task.isCancelled else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }

    func savedVideoCandidates(_ binding: VideoSubmissionObservation) async throws -> [VideoCandidate] {
        let events: [VideoCandidateEnvelope] = try await get("v1/production-runs/\(binding.run_id)/events")
        let saved = events.compactMap(\.candidate).filter { $0.payload.binding_id == binding.id }
        for candidate in saved { try validateVideoCandidate(candidate, binding: binding) }
        return saved
    }

    private func validateVideoCandidate(_ candidate: VideoCandidate, binding: VideoSubmissionObservation) throws {
        guard candidate.run_id == binding.run_id, candidate.event_type == "video_result_materialized",
              candidate.payload.binding_id == binding.id, candidate.payload.task_key == binding.task_key,
              candidate.payload.request_sha256 == binding.request_sha256, candidate.payload.video_downloaded,
              !candidate.payload.generation_performed, !candidate.payload.billing_verified,
              !candidate.payload.master_accepted, !candidate.payload.visual_semantics_verified,
              !Task.isCancelled else { throw LibrarySnapshotRefreshError.contextChanged }
    }

    func latestEpisodeEditReview(edit: EpisodeEditingEvent) async throws -> EpisodeEditReview? {
        let events: [EpisodeEditReviewEnvelope] = try await get("v1/production-runs/\(edit.run_id)/events")
        guard let latest = events.compactMap(\.review).last(where: { $0.payload.edit_id == edit.id }) else { return nil }
        try validateEpisodeEditReview(latest, edit: edit)
        return latest
    }

    func reviewEpisodeEdit(edit: EpisodeEditingEvent, picture: EpisodePicture,
                           draft: EpisodeEditReviewDraft) async throws -> EpisodeEditReview {
        guard picture.editSHA == edit.payload.edit_sha256, draft.expected_edit_sha256 == picture.editSHA,
              draft.preview_id == picture.receiptID, draft.expected_preview_sha256 == picture.sha256 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let saved: EpisodeEditReview = try await post("v1/production-runs/\(edit.run_id)/episode-edit-drafts/\(edit.id)/reviews", body: draft)
        try validateEpisodeEditReview(saved, edit: edit)
        guard saved.payload.preview_id == picture.receiptID, saved.payload.preview_sha256 == picture.sha256,
              saved.payload.decision == draft.decision, saved.payload.reviewed_by == draft.reviewed_by,
              saved.payload.confirmation == draft.confirmation else { throw LibrarySnapshotRefreshError.contextChanged }
        return saved
    }

    private func validateEpisodeEditReview(_ review: EpisodeEditReview, edit: EpisodeEditingEvent) throws {
        let p = review.payload
        guard !Task.isCancelled, review.run_id == edit.run_id, review.event_type == "postproduction_edit_reviewed",
              p.edit_id == edit.id, p.edit_sha256 == edit.payload.edit_sha256,
              p.duration_confirmed_seconds == edit.payload.edited_duration_seconds,
              p.edit_approved == (p.decision == .accept), !p.audio_approved, !p.captions_approved,
              !p.master_accepted, !p.generation_performed,
              p.viewing_evidence == "USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY" else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }

    func downloadEpisodePicturePreview(edit: EpisodeEditingEvent) async throws -> EpisodePicture {
        guard edit.event_type == "postproduction_edit_drafted", let sha = edit.payload.edit_sha256,
              sha.count == 64, edit.payload.edit_approved == false, !edit.payload.master_accepted else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var request = URLRequest(url: baseURL.appending(path:
            "v1/production-runs/\(edit.run_id)/episode-edit-drafts/\(edit.id)/picture-preview"))
        request.httpMethod = "POST"
        request.timeoutInterval = 330
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(["expected_edit_sha256": sha])
        try await requireOwnedRuntime()
        let (temporary, response) = try await session.download(for: request)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let size = try FileManager.default.attributesOfItem(atPath: temporary.path)[.size] as? NSNumber
        guard let size, (12...128_000_000).contains(size.intValue), !Task.isCancelled else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let bytes = try Data(contentsOf: temporary, options: .mappedIfSafe)
        let receiptID = try EpisodePictureValidation.validate(bytes: bytes, response: response, editSHA: sha)
        let destination = FileManager.default.temporaryDirectory.appending(path: "nalu-episode-preview-\(UUID().uuidString).mp4")
        try FileManager.default.copyItem(at: temporary, to: destination)
        do { try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path) }
        catch { try? FileManager.default.removeItem(at: destination); throw error }
        return EpisodePicture(fileURL: destination, receiptID: receiptID,
            sha256: SHA256.hash(data: bytes).map({ String(format: "%02x", $0) }).joined(), editSHA: sha)
    }

    func downloadVideoCandidate(_ candidate: VideoCandidate, binding: VideoSubmissionObservation) async throws -> URL {
        try validateVideoCandidate(candidate, binding: binding)
        guard let media = candidate.payload.video, (12...128_000_000).contains(media.byte_size),
              media.sha256.count == 64 else { throw LibrarySnapshotRefreshError.contextChanged }
        var request = URLRequest(url: baseURL.appending(path:
            "v1/production-runs/\(binding.run_id)/video-results/\(candidate.id)/content"))
        request.timeoutInterval = 180
        try await requireOwnedRuntime()
        let (temporary, response) = try await session.download(for: request)
        defer { try? FileManager.default.removeItem(at: temporary) }
        guard let http = response as? HTTPURLResponse, http.statusCode == 200,
              http.mimeType == "video/mp4", !Task.isCancelled else {
            throw RuntimeError.requestFailed("本地视频暂时无法读取，请重试取回视频。")
        }
        let size = try FileManager.default.attributesOfItem(atPath: temporary.path)[.size] as? NSNumber
        guard size?.intValue == media.byte_size else { throw LibrarySnapshotRefreshError.contextChanged }
        let bytes = try Data(contentsOf: temporary, options: .mappedIfSafe)
        guard SHA256.hash(data: bytes).map({ String(format: "%02x", $0) }).joined() == media.sha256 else {
            throw RuntimeError.requestFailed("视频校验不一致，已停止播放。原生成任务保留。")
        }
        let destination = FileManager.default.temporaryDirectory.appending(path: "nalu-preview-\(UUID().uuidString).mp4")
        try FileManager.default.copyItem(at: temporary, to: destination)
        do { try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path) }
        catch { try? FileManager.default.removeItem(at: destination); throw error }
        return destination
    }

    private func validateVideoSubmission(_ saved: VideoSubmissionObservation, reservation: VideoCostReservation) throws {
        guard saved.run_id == reservation.run_id, saved.task_key == reservation.payload.task_key,
              saved.request_sha256 == reservation.payload.request_sha256, !Task.isCancelled else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
    }

    func productionAuthorizationPreview(runID: String) async throws -> LibrarySnapshotRefreshPreview {
        try await get("v1/production-runs/\(runID)/library-snapshot-refresh")
    }

    func authorizeProduction(runID: String, draft: ProductionAuthorizationDraft) async throws -> EpisodeShotPlanEvent {
        let saved: EpisodeShotPlanEvent = try await post("v1/production-runs/\(runID)/production-authorization", body: draft)
        guard saved.run_id == runID, saved.payload.approved,
              saved.payload.production_authorization == draft, !Task.isCancelled else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        return saved
    }

    func refreshConfirmedLibrary(runID: String) async throws -> EpisodeShotPlanEvent {
        let path = "v1/production-runs/\(runID)/library-snapshot-refresh"
        let preview: LibrarySnapshotRefreshPreview = try await get(path)
        guard preview.run_id == runID, !Task.isCancelled else { throw LibrarySnapshotRefreshError.contextChanged }
        var expectedID = preview.request.source_event_id
        var expectedSHA = preview.request.expected_plan_sha256
        if preview.refresh_required {
            let saved: EpisodeShotPlanEvent = try await post(path, body: preview.request)
            guard saved.run_id == runID, saved.payload.approved, !Task.isCancelled else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            expectedID = saved.id
            expectedSHA = saved.payload.plan_sha256
        }
        guard let current = try await currentShotPlan(runID: runID), current.run_id == runID,
              current.id == expectedID, current.payload.plan_sha256 == expectedSHA,
              current.payload.approved, !Task.isCancelled else { throw LibrarySnapshotRefreshError.contextChanged }
        return current
    }

    func frameProductionEvents(runID: String) async throws -> [FrameProductionEvent] {
        try await get("v1/production-runs/\(runID)/events")
    }

    func advanceSavedImage(runID: String, submissionID: String, apiKey: String) async throws -> SavedImageProgress {
        var request = URLRequest(url: baseURL.appending(path:
            "v1/production-runs/\(runID)/image-tasks/\(submissionID)/advance"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue(apiKey, forHTTPHeaderField: "X-Nalu-Provider-Key")
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(SavedImageProgress.self, from: data)
    }

    func prepareReviewedShotFrame(runID: String, planID: String, shotIndex: Int) async throws -> FrameProductionEvent {
        try await post("v1/production-runs/\(runID)/shot-plans/\(planID)/opening-frame-preparations",
                       body: ["shot_index": shotIndex])
    }

    func savedFrameBytes(runID: String, materializationID: String, expectedSHA: String) async throws -> Data {
        let (data, response) = try await authorizedData(from: baseURL.appending(path:
            "v1/production-runs/\(runID)/image-results/\(materializationID)/content"))
        try validate(response, data: data)
        let sha = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard data.count <= 15_000_000, sha == expectedSHA else {
            throw RuntimeError.requestFailed("首帧校验不一致，请重新读取")
        }
        return data
    }

    func prepareReviewedReference(runID: String, planID: String, key: String) async throws -> FrameProductionEvent {
        try await post("v1/production-runs/\(runID)/shot-plans/\(planID)/reference-image-preparations",
                       body: ["visual_asset_key": key])
    }

    func registerReviewedReference(runID: String, reviewID: String, guardianApproved: Bool) async throws -> NaluAsset {
        try await post("v1/production-runs/\(runID)/reference-reviews/\(reviewID)/asset",
                       body: ReferencePermissionDraft(guardian_approved: guardianApproved))
    }

    func reviewSavedFrame(runID: String, materializationID: String, draft: FrameReviewDraft) async throws -> FrameProductionEvent {
        try await post("v1/production-runs/\(runID)/image-results/\(materializationID)/review", body: draft)
    }

    func reviewShotPlan(runID: String, eventID: String, request: EpisodeShotReview) async throws -> EpisodeShotPlanEvent {
        try await post("v1/production-runs/\(runID)/shot-plans/\(eventID)/review", body: request)
    }

    func prepareShotCharacterCards(runID: String, eventID: String, planSHA: String) async throws -> ShotCharacterCards {
        try await post("v1/production-runs/\(runID)/shot-plans/\(eventID)/character-cards",
            body: ["expected_plan_sha256": planSHA])
    }

    func generateShotPlan(runID: String, model: String, apiKey: String) async throws -> EpisodeShotPlanEvent {
        var request = URLRequest(url: baseURL.appending(path: "v1/production-runs/\(runID)/shot-plans"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "X-Nalu-Writer-Key")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["model": model])
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(EpisodeShotPlanEvent.self, from: data)
    }

    func refreshDirector(runID: String, eventID: String, planSHA: String, model: String,
                         apiKey: String) async throws -> EpisodeShotPlanEvent {
        var request = URLRequest(url: baseURL.appending(path: "v1/production-runs/\(runID)/shot-plans/\(eventID)/director-refresh"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "X-Nalu-Writer-Key")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["model": model, "expected_plan_sha256": planSHA])
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(EpisodeShotPlanEvent.self, from: data)
    }

    func prepareEpisodeProduction(episodeID: String, approvedRevision: Int) async throws -> ProductionRun {
        var request = URLRequest(url: baseURL.appending(path: "v1/episodes/\(episodeID)/production-runs"))
        request.httpMethod = "POST"
        request.timeoutInterval = 120
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("native-preflight-\(episodeID)-r\(approvedRevision)", forHTTPHeaderField: "Idempotency-Key")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "dry_run": true, "paid_generation_approved": false,
        ])
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(ProductionRun.self, from: data)
    }

    func createFeedback(_ draft: FeedbackDraft) async throws -> FeedbackItem {
        try await post("v1/feedback", body: draft)
    }

    func createFeedbackReviewBundle(
        feedbackID: String, draft: FeedbackReviewBundleDraft
    ) async throws -> FeedbackReviewBundle {
        try await post("v1/feedback/\(feedbackID)/review-bundle", body: draft)
    }

    func feedbackReleaseReadiness(
        feedbackID: String
    ) async throws -> FeedbackGovernedReleaseReadiness {
        try await get("v1/feedback/\(feedbackID)/release-readiness")
    }

    func createMemoryCard(projectID: String, draft: MemoryCardDraft) async throws -> MemoryCard {
        try await post("v1/projects/\(projectID)/memory-cards", body: draft)
    }

    func listMemoryCards(projectID: String) async throws -> [MemoryCard] {
        try await get("v1/projects/\(projectID)/memory-cards")
    }

    func memoryGraphConflicts(memoryID: String) async throws -> MemoryGraphConflictReport {
        try await get("v1/memory-cards/\(memoryID)/conflicts")
    }

    func documentaryReadiness(projectID: String) async throws -> DocumentaryReadinessReport {
        try await get("v1/projects/\(projectID)/documentary-readiness")
    }

    func listLibraryEntities(projectID: String) async throws -> [LibraryEntity] {
        try await get("v1/projects/\(projectID)/library-entities")
    }

    func createLibraryEntity(
        projectID: String, draft: LibraryEntityCreateDraft
    ) async throws -> LibraryEntity {
        try await post("v1/projects/\(projectID)/library-entities", body: draft)
    }

    func createLibraryRevision(
        entityID: String, draft: LibraryEntityRevisionDraft
    ) async throws -> LibraryEntity {
        try await post("v1/library-entities/\(entityID)/revisions", body: draft)
    }

    func confirmLibraryEntity(
        entityID: String, draft: LibraryEntityConfirmationDraft
    ) async throws -> LibraryEntityConfirmationRecord {
        try await post("v1/library-entities/\(entityID)/confirmations", body: draft)
    }

    func updateMemoryCard(id: String, draft: MemoryCardUpdateDraft) async throws -> MemoryCard {
        try await send("v1/memory-cards/\(id)", method: "PATCH", body: draft)
    }

    func confirmMemoryCard(id: String, revision: Int) async throws -> MemoryCard {
        try await post(
            "v1/memory-cards/\(id)/confirm",
            body: MemoryCardConfirmationDraft(
                confirmedBy: "本人",
                reviewedRevision: revision,
                reviewChannel: "voice_and_visual",
                spokenConfirmation: "我确认这张记忆卡并归档"
            )
        )
    }

    func createProjectPlan(_ draft: ProjectPlanDraft) async throws -> ProjectPlan {
        try await post("v1/project-plans", body: draft)
    }

    func listSeasons(projectID: String) async throws -> [NaluSeason] {
        try await get("v1/projects/\(projectID)/seasons")
    }

    func createSeason(projectID: String, draft: SeasonDraft) async throws -> NaluSeason {
        try await post("v1/projects/\(projectID)/seasons", body: draft)
    }

    func updateSeasonPlan(
        seasonID: String, summary: String, sourceTranscript: String = ""
    ) async throws -> NaluSeason {
        try await send(
            "v1/seasons/\(seasonID)",
            method: "PATCH",
            body: SeasonPlanUpdateDraft(
                seasonArc: ["summary": .string(summary)],
                sourceTranscript: sourceTranscript
            )
        )
    }

    func approveSeasonPlan(
        seasonID: String, planRevision: Int, confirmation: String, reviewChannel: String,
        guardianApproval: Bool
    ) async throws -> SeasonPlanApproval {
        try await post(
            "v1/seasons/\(seasonID)/plan-approvals",
            body: SeasonPlanApprovalDraft(
                approvedBy: "local-user",
                planRevision: planRevision,
                spokenConfirmation: confirmation,
                reviewChannel: reviewChannel,
                guardianApproval: guardianApproval
            )
        )
    }

    func listEpisodes(seasonID: String) async throws -> [NaluEpisode] {
        try await get("v1/seasons/\(seasonID)/episodes")
    }

    func listEpisodeProgress(seasonID: String) async throws -> [EpisodeProductionProgress] {
        try await get("v1/seasons/\(seasonID)/production-progress")
    }

    func publicationLearning(projectID: String) async throws -> [PublicationLearningRecord] {
        let strategies: [DirectorStrategyRevision] = try await get(
            "v1/projects/\(projectID)/director-strategies"
        )
        var records: [PublicationLearningRecord] = []
        records.reserveCapacity(strategies.count)
        for strategy in strategies {
            let metrics: PublicationMetricsSnapshot = try await get(
                "v1/publication-metrics/\(strategy.sourceMetricsID)"
            )
            records.append(
                try PublicationLearningRecord(
                    validating: strategy,
                    metrics: metrics,
                    projectID: projectID
                )
            )
        }
        return records
    }

    func cancelProductionRun(runID: String) async throws -> ProductionRun {
        try await post(
            "v1/production-runs/\(runID)/cancel",
            body: ProductionRunActionDraft(
                requestedBy: "local-user",
                reason: "用户在 Nalu macOS 应用中要求暂停"
            )
        )
    }

    func resumeProductionRun(runID: String) async throws -> ProductionRun {
        try await post(
            "v1/production-runs/\(runID)/resume",
            body: ProductionRunResumeDraft(
                requestedBy: "local-user",
                reason: "用户在 Nalu macOS 应用中要求继续",
                resumeFromPreflight: true
            )
        )
    }

    func createEpisode(seasonID: String, draft: EpisodeDraft) async throws -> NaluEpisode {
        try await post("v1/seasons/\(seasonID)/episodes", body: draft)
    }

    func resolveReviewEpisode(seasonID: String, draft: EpisodeDraft) async throws -> NaluEpisode {
        if let existing = try await listEpisodes(seasonID: seasonID).first(where: {
            $0.seasonID == seasonID && $0.episodeNumber == draft.episodeNumber
        }) { return existing }
        do {
            return try await createEpisode(seasonID: seasonID, draft: draft)
        } catch {
            let creationError = error
            try Task.checkCancellation()
            // A lost response or another window may have created this numbered
            // episode. Reconcile using reads only; never repeat the POST here.
            if let recovered = try? await listEpisodes(seasonID: seasonID).first(where: {
                $0.seasonID == seasonID && $0.episodeNumber == draft.episodeNumber
            }) { return recovered }
            throw creationError
        }
    }

    func updateEpisodePlan(
        episodeID: String, logline: String, outlineSummary: String,
        sourceTranscript: String = ""
    ) async throws -> NaluEpisode {
        try await send(
            "v1/episodes/\(episodeID)",
            method: "PATCH",
            body: EpisodePlanUpdateDraft(
                logline: logline,
                outline: ["summary": .string(outlineSummary)],
                sourceTranscript: sourceTranscript
            )
        )
    }

    func listScripts(episodeID: String) async throws -> [ScriptRevision] {
        try await get("v1/episodes/\(episodeID)/scripts")
    }

    func createScript(
        episodeID: String, content: String, summary: String, sourceTranscript: String = "",
        narrativeMetadata: [String: JSONValue] = [:], authoringOrigin: String,
        externalWriter: ExternalWriterDeclaration? = nil, idempotencyKey: String? = nil
    ) async throws -> ScriptRevision {
        try await post(
            "v1/episodes/\(episodeID)/scripts",
            body: ScriptRevisionDraft(
                content: content,
                summaryForVoiceReview: summary,
                sourceTranscript: sourceTranscript,
                narrativeMetadata: narrativeMetadata,
                authoring: ScriptAuthoringDraft(origin: authoringOrigin, external_writer: externalWriter),
                idempotencyKey: idempotencyKey
            )
        )
    }

    func reconcileInteractiveReceipt(episodeID: String, revision: Int, receipt: String) async throws {
        var components = URLComponents(url: baseURL.appending(path:
            "v1/episodes/\(episodeID)/scripts/\(revision)/writer-receipt-reconciliations"), resolvingAgainstBaseURL: false)!
        components.queryItems = [.init(name: "reconciled_by", value: "nalu-interactive-writer-adapter")]
        var request = URLRequest(url: components.url!)
        request.httpMethod = "POST"
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.httpBody = Data(receipt.utf8)
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
    }

    func listContinuitySnapshots(episodeID: String) async throws -> [ContinuitySnapshot] {
        try await get("v1/episodes/\(episodeID)/continuity-snapshots")
    }

    func inheritedContinuity(episodeID: String) async throws -> InheritedContinuityResult {
        try await get("v1/episodes/\(episodeID)/inherited-continuity")
    }

    func createContinuitySnapshot(
        episodeID: String, draft: ContinuitySnapshotDraft
    ) async throws -> ContinuitySnapshot {
        try await post("v1/episodes/\(episodeID)/continuity-snapshots", body: draft)
    }

    func continuityExtractionProposal(
        episodeID: String
    ) async throws -> ContinuityExtractionProposal {
        try await get("v1/episodes/\(episodeID)/continuity-extraction-proposal")
    }

    func confirmContinuityExtraction(
        episodeID: String, draft: ContinuityExtractionConfirmationDraft
    ) async throws -> ContinuityExtractionConfirmationResult {
        try await post(
            "v1/episodes/\(episodeID)/continuity-extraction-confirmations",
            body: draft
        )
    }

    func continuityPreflight(
        episodeID: String, draft: ContinuityPreflightDraft
    ) async throws -> ContinuityPreflightResult {
        try await post("v1/episodes/\(episodeID)/continuity-preflight", body: draft)
    }

    func approveScript(
        episodeID: String, revision: Int, confirmation: String, guardianApproval: Bool
    ) async throws -> ScriptRevision {
        try await post(
            "v1/episodes/\(episodeID)/scripts/\(revision)/approve",
            body: ScriptApprovalDraft(
                approvedBy: "local-user",
                spokenConfirmation: confirmation,
                guardianApproval: guardianApproval
            )
        )
    }

    func revokeScript(episodeID: String, revision: Int) async throws -> ScriptRevision {
        try await post(
            "v1/episodes/\(episodeID)/scripts/\(revision)/revoke",
            body: ScriptRevocationDraft(
                requestedBy: "local-user",
                reason: "用户要求继续修改剧本"
            )
        )
    }

    func downloadSealedMaster(runID: String) async throws -> SealedMasterDownload {
        let sourceURL = baseURL.appending(path: "v1/production-runs/\(runID)/sealed-master")
        var request = URLRequest(url: sourceURL)
        request.timeoutInterval = 600
        try await requireOwnedRuntime()
        let (temporaryDownload, response) = try await session.download(for: request)
        guard let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode),
              let expectedSHA = http.value(forHTTPHeaderField: "X-Nalu-Master-SHA256"),
              expectedSHA.count == 64 else {
            throw RuntimeError.requestFailed("无法取得当前封存成片或其校验摘要")
        }
        let directory = FileManager.default.temporaryDirectory
            .appending(path: "NaluSemanticMediaQA", directoryHint: .isDirectory)
        try FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        let destination = directory.appending(path: UUID().uuidString + ".mp4")
        var keepDestination = false
        defer {
            if !keepDestination {
                try? FileManager.default.removeItem(at: destination)
            }
        }
        try FileManager.default.copyItem(at: temporaryDownload, to: destination)
        let data = try Data(contentsOf: destination, options: .mappedIfSafe)
        let actualSHA = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard actualSHA == expectedSHA.lowercased() else {
            throw RuntimeError.requestFailed("成片下载后的摘要不一致，声音检查已经停止")
        }
        keepDestination = true
        return SealedMasterDownload(fileURL: destination, sha256: actualSHA)
    }

    func submitSemanticMediaQA(
        runID: String, draft: SemanticMediaQADraft
    ) async throws -> SemanticMediaQAResult {
        try await post("v1/production-runs/\(runID)/semantic-media-qa", body: draft)
    }

    private func get<Response: Decodable>(_ path: String) async throws -> Response {
        let (data, response) = try await authorizedData(from: baseURL.appending(path: path))
        try validate(response, data: data)
        return try decoder.decode(Response.self, from: data)
    }

    private func post<Body: Encodable, Response: Decodable>(
        _ path: String, body: Body
    ) async throws -> Response {
        try await send(path, method: "POST", body: body)
    }

    private func send<Body: Encodable, Response: Decodable>(
        _ path: String, method: String, body: Body
    ) async throws -> Response {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(Response.self, from: data)
    }

    private func validate(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Unknown runtime error"
            throw RuntimeError.requestFailed(message)
        }
    }

    private func authorizedData(from url: URL) async throws -> (Data, URLResponse) {
        try await requireOwnedRuntime()
        return try await session.data(from: url)
    }

    private func authorizedData(for request: URLRequest) async throws -> (Data, URLResponse) {
        try await requireOwnedRuntime()
        return try await session.data(for: request)
    }

    private func requireOwnedRuntime() async throws {
        guard await accessCheck() else {
            throw RuntimeError.unmanagedRuntimeAccessDenied
        }
    }
}

enum RuntimeError: LocalizedError {
    case requestFailed(String)
    case unmanagedRuntimeAccessDenied

    var errorDescription: String? {
        switch self {
        case .requestFailed(let message): message
        case .unmanagedRuntimeAccessDenied:
            "此窗口没有启动并持有自己的本地制片厂，因此不会读取或修改另一窗口的项目。"
        }
    }
}
