import CryptoKit
import Foundation

actor RuntimeClient {
    private let baseURL: URL
    private let session: URLSession
    private let accessCheck: @Sendable () async -> Bool
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    func controlNovelImport(projectID: String, action: NovelImportControl) async throws -> NovelImportStatus {
        var request = URLRequest(url: baseURL.appending(path: "v1/projects/\(projectID)/novel-import/\(action.rawValue)"))
        request.httpMethod = "POST"
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(NovelImportStatus.self, from: data)
    }

    func startNovelImport(projectID: String, sourceURL: String) async throws -> NovelImportStatus {
        var request = URLRequest(url: baseURL.appending(path: "v1/projects/\(projectID)/novel-import"))
        request.httpMethod = "POST"
        request.timeoutInterval = 600
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(NovelImportDraft(source_url: sourceURL))
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(NovelImportStatus.self, from: data)
    }

    func fetchNextNovelChapter(projectID: String) async throws -> NovelImportStatus {
        var request = URLRequest(url: baseURL.appending(path: "v1/projects/\(projectID)/novel-import/fetch-next"))
        request.httpMethod = "POST"
        request.timeoutInterval = 90
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        return try decoder.decode(NovelImportStatus.self, from: data)
    }

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

    func prepareEpisodeDialogue(sound: EpisodeSoundPlan) async throws -> EpisodeDialoguePreparation {
        try sound.validateCueWindows()
        guard !sound.run_id.isEmpty, sound.payload.edit_approved else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var components = URLComponents(url: baseURL.appending(path: "v1/production-runs/\(sound.run_id)/adopted-dialogue"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "sound_plan_id", value: sound.id),
            URLQueryItem(name: "expected_sound_plan_sha256", value: sound.payload.sound_plan_sha256),
            URLQueryItem(name: "artifact", value: "captions")]
        var request = URLRequest(url: components.url!)
        request.timeoutInterval = 300
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        guard !Task.isCancelled, let http = response as? HTTPURLResponse,
              http.value(forHTTPHeaderField: "X-Nalu-Sound-Plan-ID") == sound.id,
              http.value(forHTTPHeaderField: "X-Nalu-Master-Accepted") == "false",
              let lineage = http.value(forHTTPHeaderField: "X-Nalu-Lineage-SHA256"),
              EpisodeDialogueStageReceipt.validSHA(lineage),
              let sha = http.value(forHTTPHeaderField: "X-Nalu-Artifact-SHA256"),
              SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == sha,
              data.starts(with: Data("WEBVTT".utf8)) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        return EpisodeDialoguePreparation(draft: .init(sound_plan_id: sound.id,
            expected_sound_plan_sha256: sound.payload.sound_plan_sha256, expected_lineage_sha256: lineage), captionsSHA256: sha)
    }

    func stageEpisodeDialogue(sound: EpisodeSoundPlan, preparation: EpisodeDialoguePreparation) async throws -> EpisodeDialogueStageReceipt {
        try Task.checkCancellation()
        try sound.validateCueWindows()
        let draft = preparation.draft
        guard !sound.run_id.isEmpty, sound.payload.edit_approved,
              draft.sound_plan_id == sound.id, draft.expected_sound_plan_sha256 == sound.payload.sound_plan_sha256,
              EpisodeDialogueStageReceipt.validSHA(draft.expected_lineage_sha256),
              EpisodeDialogueStageReceipt.validSHA(preparation.captionsSHA256) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var request = URLRequest(url: baseURL.appending(path: "v1/production-runs/\(sound.run_id)/adopted-dialogue/stage"))
        request.httpMethod = "POST"
        request.timeoutInterval = 300
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(draft)
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        try Task.checkCancellation()
        let receipt = try decoder.decode(EpisodeDialogueStageReceipt.self, from: data)
        try receipt.validate(runID: sound.run_id, preparation: preparation)
        return receipt
    }

    func stageEpisodeSoundSource(sound: EpisodeSoundPlan, draft: EpisodeSoundSourceDraft) async throws -> EpisodeSoundSourceReceipt {
        try Task.checkCancellation()
        try sound.validateCueWindows()
        try draft.validate()
        guard !sound.run_id.isEmpty, sound.payload.edit_approved,
              draft.sound_plan_id == sound.id, draft.expected_sound_plan_sha256 == sound.payload.sound_plan_sha256 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var request = URLRequest(url: baseURL.appending(path: "v1/production-runs/\(sound.run_id)/sound-sources"))
        request.httpMethod = "POST"
        request.timeoutInterval = 60
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(draft)
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        try Task.checkCancellation()
        let receipt = try decoder.decode(EpisodeSoundSourceReceipt.self, from: data)
        try receipt.validate(runID: sound.run_id, draft: draft, duration: sound.payload.duration_seconds,
                             cueCount: sound.payload.cues.count)
        return receipt
    }

    func health() async throws -> RuntimeHealth {
        let (data, response) = try await authorizedData(
            from: baseURL.appending(path: "health")
        )
        try validate(response, data: data)
        return try decoder.decode(RuntimeHealth.self, from: data)
    }

    func prepareEpisodeMix(sound: EpisodeSoundPlan, dialogue: EpisodeDialogueStageReceipt,
                           sources: [EpisodeSoundSourceReceipt.Source]) async throws -> EpisodePreparedMix {
        try Task.checkCancellation()
        try sound.validateCueWindows()
        guard sound.payload.edit_approved, dialogue.run_id == sound.run_id,
              dialogue.payload.lineage.sound_plan_id == sound.id,
              dialogue.payload.lineage.sound_plan_sha256 == sound.payload.sound_plan_sha256,
              sources.count == 4, Set(sources.map(\.layer)) == Set(EpisodeSoundRole.allCases) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var request = URLRequest(url: baseURL.appending(path: "v1/production-runs/\(sound.run_id)/adopted-dialogue/prepare-mix"))
        request.httpMethod = "POST"; request.timeoutInterval = 300
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(EpisodeMixRequest(staging_id: dialogue.id,
            expected_staging_sha256: dialogue.payload.staging_sha256, sound_layers: sources))
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        try Task.checkCancellation()
        return try EpisodePreparedMix(body: data, sound: sound, dialogue: dialogue, sources: sources)
    }

    func renderEpisodeMix(_ mix: EpisodePreparedMix) async throws -> EpisodeRenderedMix {
        try Task.checkCancellation()
        var request = URLRequest(url: baseURL.appending(path: "v1/production-runs/\(mix.runID)/postproduction-materializations"))
        request.httpMethod = "POST"; request.timeoutInterval = 1800
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = mix.body
        let (data, response) = try await authorizedData(for: request)
        try validate(response, data: data)
        try Task.checkCancellation()
        let result = try decoder.decode(EpisodeRenderedMix.self, from: data)
        try result.validate(mix)
        let handoff = try EpisodeOutputHandoff(materialization: data)
        var sealRequest = URLRequest(url: baseURL.appending(path: "v1/production-runs/\(mix.runID)/rendered-output-seal"))
        sealRequest.httpMethod = "POST"
        sealRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        sealRequest.httpBody = handoff.body
        let (sealData, sealResponse) = try await authorizedData(for: sealRequest)
        try validate(sealResponse, data: sealData)
        guard let seal = try JSONSerialization.jsonObject(with: sealData) as? [String: Any],
              seal["run_id"] as? String == mix.runID,
              let sealSHA = seal["manifest_sha256"] as? String,
              EpisodeDialogueStageReceipt.validSHA(sealSHA) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        for gate in ["media-structure-qa", "decoded-media-qa"] {
            try Task.checkCancellation()
            var check = URLRequest(url: baseURL.appending(path: "v1/production-runs/\(mix.runID)/\(gate)"))
            check.httpMethod = "POST"; check.timeoutInterval = 1800
            let (reportData, reportResponse) = try await authorizedData(for: check)
            try validate(reportResponse, data: reportData)
            guard let report = try JSONSerialization.jsonObject(with: reportData) as? [String: Any],
                  report["run_id"] as? String == mix.runID,
                  report["output_seal_sha256"] as? String == sealSHA,
                  report["master_sha256"] as? String == handoff.masterSHA else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            if report["status"] as? String == "FAIL" {
                throw EpisodeOutputQualityFailure(codes: report["failures"] as? [String] ?? [])
            }
            guard report["status"] as? String == "PASS" else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
        }
        return result
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

    @discardableResult
    func retimeEpisodeSound(edit: EpisodeEditingEvent, review: EpisodeEditReview? = nil) async throws -> EpisodeSoundPlan {
        struct Draft: Encodable {
            let expected_plan_sha256: String; let edit_id: String; let expected_edit_sha256: String
            let expected_edit_review_id: String?
        }
        guard edit.event_type == "postproduction_edit_drafted", let sha = edit.payload.edit_sha256,
              sha.count == 64 else { throw LibrarySnapshotRefreshError.contextChanged }
        if let review {
            try validateEpisodeEditReview(review, edit: edit)
            guard review.payload.edit_approved else { throw LibrarySnapshotRefreshError.contextChanged }
        }
        let receipt: EpisodeSoundPlan = try await post("v1/production-runs/\(edit.run_id)/sound-plan-drafts",
            body: Draft(expected_plan_sha256: edit.payload.plan_sha256, edit_id: edit.id, expected_edit_sha256: sha,
                        expected_edit_review_id: review?.id))
        let sound = receipt.payload
        try receipt.validateCueWindows()
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
        return receipt
    }

    func latestEpisodeEdit(inputs: EpisodeEditingEvent) async throws -> EpisodeEditingEvent? {
        let events: [EpisodeEditEnvelope] = try await get("v1/production-runs/\(inputs.run_id)/events")
        let edits = events.compactMap(\.edit)
        guard edits.allSatisfy({ $0.run_id == inputs.run_id }) else { throw LibrarySnapshotRefreshError.contextChanged }
        guard let latest = edits.last(where: { $0.payload.plan_id == inputs.payload.plan_id }) else { return nil }
        try validateSavedEpisodeEdit(latest, inputs: inputs)
        return latest
    }

    func attachEpisodeAudio(sound: EpisodeSoundPlan, draft: EpisodeAudioTakeDraft) async throws -> EpisodeAudioTake {
        try sound.validateCueWindows()
        guard sound.event_type == "episode_sound_plan_drafted", sound.payload.edit_approved,
              let reviewID = sound.payload.edit_review_id, !reviewID.isEmpty,
              draft.sound_plan_id == sound.id, draft.expected_sound_plan_sha256 == sound.payload.sound_plan_sha256,
              sound.payload.cues.indices.contains(draft.shot_index), !draft.asset_id.isEmpty,
              draft.expected_asset_sha256.count == 64,
              draft.expected_asset_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              draft.source_in_seconds.isFinite, (0...1800).contains(draft.source_in_seconds) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let result: EpisodeAudioTake = try await post("v1/production-runs/\(sound.run_id)/audio-takes", body: draft)
        try validateEpisodeAudio(result, sound: sound, draft: draft, reviewID: reviewID)
        return result
    }

    func recoverEpisodeAudio(sound: EpisodeSoundPlan) async throws -> [EpisodeAudioTake] {
        try sound.validateCueWindows()
        guard sound.event_type == "episode_sound_plan_drafted", sound.payload.edit_approved,
              let reviewID = sound.payload.edit_review_id, !reviewID.isEmpty else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        var components = URLComponents(url: baseURL.appending(path: "v1/production-runs/\(sound.run_id)/audio-takes"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "sound_plan_id", value: sound.id),
                                URLQueryItem(name: "expected_sound_plan_sha256", value: sound.payload.sound_plan_sha256)]
        let (data, response) = try await authorizedData(from: components.url!)
        try validate(response, data: data)
        let results = try decoder.decode([EpisodeAudioTake].self, from: data)
        var indices = Set<Int>()
        for result in results {
            let take = result.payload
            guard sound.payload.cues.indices.contains(take.shot_index), indices.insert(take.shot_index).inserted,
                  !take.asset_id.isEmpty, take.expected_asset_sha256.count == 64,
                  take.expected_asset_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
                  take.source_in_seconds.isFinite, (0...1800).contains(take.source_in_seconds) else {
                throw LibrarySnapshotRefreshError.contextChanged
            }
            let draft = EpisodeAudioTakeDraft(sound_plan_id: sound.id, expected_sound_plan_sha256: sound.payload.sound_plan_sha256,
                shot_index: take.shot_index, asset_id: take.asset_id, expected_asset_sha256: take.expected_asset_sha256,
                source_in_seconds: take.source_in_seconds)
            try validateEpisodeAudio(result, sound: sound, draft: draft, reviewID: reviewID)
        }
        return results
    }

    func saveRecordingTranscript(take: EpisodeAudioTake, draft: EpisodeRecordingTranscript) async throws -> RecordingTranscriptRecord {
        guard draft.takeID == take.id, draft.sampleCount == take.payload.decoded_sample_count,
              !draft.captionsApproved, !draft.speechAlignmentVerified else { throw LibrarySnapshotRefreshError.contextChanged }
        let saved: RecordingTranscriptRecord = try await post(
            "v1/production-runs/\(take.run_id)/audio-takes/\(take.id)/transcripts",
            body: RecordingTranscriptSubmission(take: take, draft: draft))
        try saved.validate(take: take, reviewID: draft.reviewID)
        guard saved.payload.source_audio_sha256 == draft.sourceAudioSHA256,
              saved.payload.transcript == draft.transcript.trimmingCharacters(in: .whitespacesAndNewlines),
              saved.payload.segments == draft.segments,
              saved.payload.recognizer_version == draft.recognizerVersion else { throw LibrarySnapshotRefreshError.contextChanged }
        return saved
    }

    func recoverRecordingTranscript(take: EpisodeAudioTake, reviewID: String) async throws -> RecordingTranscriptRecord? {
        var components = URLComponents(url: baseURL.appending(path:
            "v1/production-runs/\(take.run_id)/audio-takes/\(take.id)/transcripts"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "expected_take_sha256", value: take.payload.take_sha256),
                                URLQueryItem(name: "expected_review_id", value: reviewID)]
        let (data, response) = try await authorizedData(from: components.url!)
        try validate(response, data: data)
        let saved = try decoder.decode(RecordingTranscriptRecord?.self, from: data)
        try saved?.validate(take: take, reviewID: reviewID)
        return saved
    }

    func saveCaptionReview(transcript: RecordingTranscriptRecord,
                           draft: RecordingCaptionSubmission) async throws -> RecordingCaptionReview {
        try draft.validate(sampleCount: transcript.payload.sample_count)
        guard draft.expected_transcript_sha256 == transcript.payload.transcript_sha256 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let saved: RecordingCaptionReview = try await post(
            "v1/production-runs/\(transcript.run_id)/audio-takes/\(transcript.payload.take_id)/transcripts/\(transcript.id)/reviews", body: draft)
        try RecordingCaptionRecovery(current_transcript_id: transcript.id, latest_review: saved,
            applies_to_current_transcript: true, captions_approved: true).validate(transcript: transcript)
        guard saved.payload.segments == draft.segments,
              saved.payload.expected_previous_review_id == draft.expected_previous_review_id,
              saved.payload.reviewed_by == draft.reviewed_by.trimmingCharacters(in: .whitespacesAndNewlines),
              saved.payload.confirmation == draft.confirmation.trimmingCharacters(in: .whitespacesAndNewlines) else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        return saved
    }

    func recoverCaptionReview(transcript: RecordingTranscriptRecord) async throws -> RecordingCaptionRecovery {
        var components = URLComponents(url: baseURL.appending(path:
            "v1/production-runs/\(transcript.run_id)/audio-takes/\(transcript.payload.take_id)/transcripts/\(transcript.id)/reviews"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "expected_transcript_sha256", value: transcript.payload.transcript_sha256)]
        let (data, response) = try await authorizedData(from: components.url!)
        try validate(response, data: data)
        let saved = try decoder.decode(RecordingCaptionRecovery.self, from: data)
        try saved.validate(transcript: transcript)
        return saved
    }

    func downloadAcceptedEpisodeAudio(sound: EpisodeSoundPlan, take: EpisodeAudioTake,
                                      expectedReviewID: String) async throws -> AcceptedEpisodeAudio {
        let state = try await recoverEpisodeAudioReview(sound: sound, take: take)
        guard state.take_approved, state.applies_to_current_take,
              state.latest_review?.id == expectedReviewID else { throw LibrarySnapshotRefreshError.contextChanged }
        var components = URLComponents(url: baseURL.appending(path:
            "v1/production-runs/\(sound.run_id)/audio-takes/\(take.id)/accepted-audio"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "expected_take_sha256", value: take.payload.take_sha256),
                                URLQueryItem(name: "expected_review_id", value: expectedReviewID)]
        var request = URLRequest(url: components.url!)
        request.timeoutInterval = 120
        request.cachePolicy = .reloadIgnoringLocalCacheData
        try await requireOwnedRuntime()
        let (temporary, response) = try await session.download(for: request)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let expectedBytes = 44 + take.payload.decoded_sample_count * 4
        let size = try FileManager.default.attributesOfItem(atPath: temporary.path)[.size] as? NSNumber
        guard !Task.isCancelled, (48...57_600_044).contains(expectedBytes),
              size?.intValue == expectedBytes else { throw LibrarySnapshotRefreshError.contextChanged }
        let bytes = try Data(contentsOf: temporary)
        return try AcceptedEpisodeAudioValidation.validate(bytes, response: response, takeID: take.id,
            reviewID: expectedReviewID, sampleCount: take.payload.decoded_sample_count)
    }

    func recoverEpisodeAudioReview(sound: EpisodeSoundPlan, take: EpisodeAudioTake) async throws -> EpisodeAudioReviewRecovery {
        try sound.validateCueWindows()
        let p = take.payload
        guard sound.event_type == "episode_sound_plan_drafted", sound.payload.cues.indices.contains(p.shot_index),
              p.source_in_seconds.isFinite, (0...1800).contains(p.source_in_seconds),
              !p.asset_id.isEmpty, p.expected_asset_sha256.count == 64,
              p.expected_asset_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              sound.payload.edit_approved, let reviewID = sound.payload.edit_review_id, !reviewID.isEmpty else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        try validateEpisodeAudio(take, sound: sound, draft: EpisodeAudioTakeDraft(
            sound_plan_id: sound.id, expected_sound_plan_sha256: sound.payload.sound_plan_sha256,
            shot_index: p.shot_index, asset_id: p.asset_id, expected_asset_sha256: p.expected_asset_sha256,
            source_in_seconds: p.source_in_seconds), reviewID: reviewID)
        var components = URLComponents(url: baseURL.appending(path:
            "v1/production-runs/\(sound.run_id)/audio-takes/\(take.id)/reviews"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "expected_take_sha256", value: p.take_sha256)]
        let (data, response) = try await authorizedData(from: components.url!)
        try validate(response, data: data)
        let recovered = try decoder.decode(EpisodeAudioReviewRecovery.self, from: data)
        guard !Task.isCancelled, recovered.current_take_id == take.id,
              recovered.current_take_sha256 == p.take_sha256 else { throw LibrarySnapshotRefreshError.contextChanged }
        if let review = recovered.latest_review {
            let r = review.payload
            let applies = r.take_id == take.id && r.take_sha256 == p.take_sha256
            guard !review.id.isEmpty, review.run_id == sound.run_id, review.event_type == "episode_audio_take_reviewed",
                  !r.take_id.isEmpty, r.take_sha256.count == 64,
                  r.take_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
                  r.sound_plan_id == sound.id, r.sound_plan_sha256 == sound.payload.sound_plan_sha256,
                  r.shot_index == p.shot_index, r.edit_review_id == reviewID, r.edit_sha256 == p.edit_sha256,
                  r.review_sha256.count == 64, r.review_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
                  r.take_approved == (r.decision == .accept),
                  recovered.applies_to_current_take == applies,
                  recovered.take_approved == (applies && r.take_approved),
                  r.listening_evidence == "USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY",
                  !r.speech_alignment_verified, !r.final_mix_approved, !r.captions_approved,
                  !r.master_accepted, !r.generation_performed else { throw LibrarySnapshotRefreshError.contextChanged }
            if applies {
                guard r.asset_id == p.asset_id, r.asset_sha256 == p.expected_asset_sha256,
                      r.source_in_seconds == p.source_in_seconds, r.duration_seconds == p.duration_seconds else {
                    throw LibrarySnapshotRefreshError.contextChanged
                }
            }
        } else if recovered.applies_to_current_take || recovered.take_approved {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        return recovered
    }

    func reviewEpisodeAudio(sound: EpisodeSoundPlan, take: EpisodeAudioTake,
                            draft: EpisodeAudioReviewDraft) async throws -> EpisodeAudioReview {
        try sound.validateCueWindows()
        let p = take.payload
        guard sound.event_type == "episode_sound_plan_drafted", sound.payload.edit_approved,
              let reviewID = sound.payload.edit_review_id, !reviewID.isEmpty,
              sound.payload.cues.indices.contains(p.shot_index),
              p.source_in_seconds.isFinite, (0...1800).contains(p.source_in_seconds),
              !p.asset_id.isEmpty, p.expected_asset_sha256.count == 64,
              p.expected_asset_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              draft.expected_take_sha256 == p.take_sha256,
              draft.expected_review_id.map({ !$0.isEmpty && $0.count <= 160 }) ?? true,
              !draft.reviewed_by.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              draft.reviewed_by.count <= 160,
              !draft.confirmation.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              draft.confirmation.count <= 2000 else { throw LibrarySnapshotRefreshError.contextChanged }
        try validateEpisodeAudio(take, sound: sound, draft: EpisodeAudioTakeDraft(
            sound_plan_id: sound.id, expected_sound_plan_sha256: sound.payload.sound_plan_sha256,
            shot_index: p.shot_index, asset_id: p.asset_id, expected_asset_sha256: p.expected_asset_sha256,
            source_in_seconds: p.source_in_seconds), reviewID: reviewID)
        let saved: EpisodeAudioReview = try await post(
            "v1/production-runs/\(sound.run_id)/audio-takes/\(take.id)/reviews", body: draft)
        let r = saved.payload
        guard !Task.isCancelled, !saved.id.isEmpty, saved.run_id == sound.run_id,
              saved.event_type == "episode_audio_take_reviewed",
              r.take_id == take.id, r.take_sha256 == p.take_sha256,
              r.sound_plan_id == sound.id, r.sound_plan_sha256 == sound.payload.sound_plan_sha256,
              r.edit_review_id == reviewID, r.edit_sha256 == p.edit_sha256,
              r.shot_index == p.shot_index, r.asset_id == p.asset_id, r.asset_sha256 == p.expected_asset_sha256,
              r.source_in_seconds == p.source_in_seconds, r.duration_seconds == p.duration_seconds,
              r.decision == draft.decision,
              r.reviewed_by == draft.reviewed_by.trimmingCharacters(in: .whitespacesAndNewlines),
              r.confirmation == draft.confirmation.trimmingCharacters(in: .whitespacesAndNewlines),
              r.review_sha256.count == 64, r.review_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              r.take_approved == (draft.decision == .accept),
              r.listening_evidence == "USER_ATTESTATION_NOT_PLAYBACK_TELEMETRY",
              !r.speech_alignment_verified, !r.final_mix_approved, !r.captions_approved,
              !r.master_accepted, !r.generation_performed else { throw LibrarySnapshotRefreshError.contextChanged }
        return saved
    }

    private func validateEpisodeAudio(_ result: EpisodeAudioTake, sound: EpisodeSoundPlan,
                                      draft: EpisodeAudioTakeDraft, reviewID: String) throws {
        let take = result.payload
        let cue = sound.payload.cues[draft.shot_index]
        let duration = cue.end_seconds - cue.start_seconds
        guard !Task.isCancelled, !result.id.isEmpty, result.run_id == sound.run_id,
              take.take_sha256.count == 64, take.take_sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              result.event_type == "episode_audio_take_attached", take.sound_plan_id == sound.id,
              take.expected_sound_plan_sha256 == sound.payload.sound_plan_sha256,
              take.shot_index == draft.shot_index, take.asset_id == draft.asset_id,
              take.expected_asset_sha256 == draft.expected_asset_sha256,
              take.source_in_seconds == draft.source_in_seconds, take.edit_review_id == reviewID,
              take.edit_sha256 == sound.payload.edit_sha256, take.start_seconds == cue.start_seconds,
              abs(take.duration_seconds - duration) < 0.000001,
              take.decoded_sample_count == Int((duration * 48000).rounded()),
              take.sample_rate_hz == 48000, take.channels == 2,
              !take.audio_approved, !take.speech_alignment_verified, !take.captions_approved,
              !take.master_accepted, !take.generation_performed else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
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
