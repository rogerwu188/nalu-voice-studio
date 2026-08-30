import Foundation

actor RuntimeClient {
    private let baseURL: URL
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(baseURL: URL = URL(string: "http://127.0.0.1:8765")!) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 10
        self.session = URLSession(configuration: configuration)
    }

    func health() async throws -> RuntimeHealth {
        let (data, response) = try await session.data(from: baseURL.appending(path: "health"))
        try validate(response, data: data)
        return try decoder.decode(RuntimeHealth.self, from: data)
    }

    func listProjects(includeArchived: Bool = false) async throws -> [NaluProject] {
        var components = URLComponents(
            url: baseURL.appending(path: "v1/projects"), resolvingAgainstBaseURL: false
        )!
        if includeArchived {
            components.queryItems = [URLQueryItem(name: "include_archived", value: "true")]
        }
        let (data, response) = try await session.data(from: components.url!)
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
        let (data, response) = try await session.data(
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
        let (responseData, response) = try await session.data(for: request)
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
        let (responseData, response) = try await session.data(for: request)
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
        let (data, response) = try await session.data(
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
        let (data, response) = try await session.data(for: request)
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

    func createFeedback(_ draft: FeedbackDraft) async throws -> FeedbackItem {
        try await post("v1/feedback", body: draft)
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
        seasonID: String, confirmation: String, reviewChannel: String,
        guardianApproval: Bool
    ) async throws -> SeasonPlanApproval {
        try await post(
            "v1/seasons/\(seasonID)/plan-approvals",
            body: SeasonPlanApprovalDraft(
                approvedBy: "local-user",
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

    func createEpisode(seasonID: String, draft: EpisodeDraft) async throws -> NaluEpisode {
        try await post("v1/seasons/\(seasonID)/episodes", body: draft)
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
        narrativeMetadata: [String: JSONValue] = [:]
    ) async throws -> ScriptRevision {
        try await post(
            "v1/episodes/\(episodeID)/scripts",
            body: ScriptRevisionDraft(
                content: content,
                summaryForVoiceReview: summary,
                sourceTranscript: sourceTranscript,
                narrativeMetadata: narrativeMetadata
            )
        )
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

    private func get<Response: Decodable>(_ path: String) async throws -> Response {
        let (data, response) = try await session.data(from: baseURL.appending(path: path))
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
        let (data, response) = try await session.data(for: request)
        try validate(response, data: data)
        return try decoder.decode(Response.self, from: data)
    }

    private func validate(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Unknown runtime error"
            throw RuntimeError.requestFailed(message)
        }
    }
}

enum RuntimeError: LocalizedError {
    case requestFailed(String)

    var errorDescription: String? {
        switch self {
        case .requestFailed(let message): message
        }
    }
}
