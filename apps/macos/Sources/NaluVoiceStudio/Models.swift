import Foundation

enum JSONValue: Codable, Hashable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer()
        if value.decodeNil() { self = .null }
        else if let decoded = try? value.decode(Bool.self) { self = .bool(decoded) }
        else if let decoded = try? value.decode(Double.self) { self = .number(decoded) }
        else if let decoded = try? value.decode(String.self) { self = .string(decoded) }
        else if let decoded = try? value.decode([String: JSONValue].self) {
            self = .object(decoded)
        } else if let decoded = try? value.decode([JSONValue].self) {
            self = .array(decoded)
        } else {
            throw DecodingError.dataCorruptedError(
                in: value, debugDescription: "Unsupported JSON value"
            )
        }
    }

    func encode(to encoder: Encoder) throws {
        var value = encoder.singleValueContainer()
        switch self {
        case .string(let item): try value.encode(item)
        case .number(let item): try value.encode(item)
        case .bool(let item): try value.encode(item)
        case .object(let item): try value.encode(item)
        case .array(let item): try value.encode(item)
        case .null: try value.encodeNil()
        }
    }

    var displayText: String {
        switch self {
        case .string(let item): item
        case .number(let item): item.formatted()
        case .bool(let item): item ? "是" : "否"
        case .object, .array, .null: ""
        }
    }

    var readableText: String {
        switch self {
        case .string(let item): return item
        case .number(let item): return item.formatted()
        case .bool(let item): return item ? "是" : "否"
        case .object(let item):
            return item.keys.sorted().compactMap { key in
                item[key].map { "\(key)：\($0.readableText)" }
            }.joined(separator: "；")
        case .array(let item): return item.map(\.readableText).joined(separator: "、")
        case .null: return "未填写"
        }
    }
}

struct ProjectDraft: Codable, Sendable {
    var title = ""
    var description = ""
    var audienceMode = "general"
    var plannedEpisodeCount = 6
    var targetEpisodeSeconds = 150
    var projectBible: [String: String] = [:]
    var creativeFormat = "short_drama_series"
    var productionPipeline = "qingshan-short-drama"

    enum CodingKeys: String, CodingKey {
        case title, description
        case audienceMode = "audience_mode"
        case plannedEpisodeCount = "planned_episode_count"
        case targetEpisodeSeconds = "target_episode_seconds"
        case projectBible = "project_bible"
        case creativeFormat = "creative_format"
        case productionPipeline = "production_pipeline"
    }
}

struct NaluProject: Codable, Identifiable, Sendable {
    let id: String
    let title: String
    let description: String
    let audienceMode: String
    let plannedEpisodeCount: Int
    let archivedAt: String?
    let creativeFormat: String
    let productionPipeline: String

    enum CodingKeys: String, CodingKey {
        case id, title, description
        case audienceMode = "audience_mode"
        case plannedEpisodeCount = "planned_episode_count"
        case archivedAt = "archived_at"
        case creativeFormat = "creative_format"
        case productionPipeline = "production_pipeline"
    }
}

struct ProjectRenameDraft: Codable, Sendable {
    let title: String
}

struct ProjectArchiveDraft: Codable, Sendable {
    let archived: Bool
}

struct RuntimeHealth: Codable, Sendable {
    let status: String
    let service: String
    let version: String
    let schemaVersion: String

    enum CodingKeys: String, CodingKey {
        case status, service, version
        case schemaVersion = "schema_version"
    }
}

struct SeasonDraft: Codable, Sendable {
    let title: String
    let seasonNumber: Int
    let plannedEpisodeCount: Int

    enum CodingKeys: String, CodingKey {
        case title
        case seasonNumber = "season_number"
        case plannedEpisodeCount = "planned_episode_count"
    }
}

struct NaluSeason: Codable, Identifiable, Sendable {
    let id: String
    let projectID: String
    let title: String
    let seasonNumber: Int
    let plannedEpisodeCount: Int
    let seasonArc: [String: JSONValue]
    let planRevision: Int
    let approvedPlanRevision: Int?

    enum CodingKeys: String, CodingKey {
        case id, title
        case projectID = "project_id"
        case seasonNumber = "season_number"
        case plannedEpisodeCount = "planned_episode_count"
        case seasonArc = "season_arc"
        case planRevision = "plan_revision"
        case approvedPlanRevision = "approved_plan_revision"
    }
}

struct SeasonPlanUpdateDraft: Codable, Sendable {
    let seasonArc: [String: JSONValue]
    let sourceTranscript: String

    enum CodingKeys: String, CodingKey {
        case seasonArc = "season_arc"
        case sourceTranscript = "source_transcript"
    }
}

struct SeasonPlanApprovalDraft: Codable, Sendable {
    let approvedBy: String
    let spokenConfirmation: String
    let reviewChannel: String
    let guardianApproval: Bool

    enum CodingKeys: String, CodingKey {
        case approvedBy = "approved_by"
        case spokenConfirmation = "spoken_confirmation"
        case reviewChannel = "review_channel"
        case guardianApproval = "guardian_approval"
    }
}

struct SeasonPlanApproval: Codable, Sendable {
    let id: String
    let seasonID: String
    let planRevision: Int

    enum CodingKeys: String, CodingKey {
        case id
        case seasonID = "season_id"
        case planRevision = "plan_revision"
    }
}

struct EpisodeDraft: Codable, Sendable {
    let title: String
    let episodeNumber: Int
    let logline: String
    let targetSeconds: Int

    enum CodingKeys: String, CodingKey {
        case title, logline
        case episodeNumber = "episode_number"
        case targetSeconds = "target_seconds"
    }
}

struct NaluEpisode: Codable, Identifiable, Sendable {
    let id: String
    let title: String
    let episodeNumber: Int
    let logline: String
    let outline: [String: JSONValue]
    let targetSeconds: Int
    let status: String

    enum CodingKeys: String, CodingKey {
        case id, title, logline, outline, status
        case episodeNumber = "episode_number"
        case targetSeconds = "target_seconds"
    }
}

struct EpisodeProductionProgress: Codable, Identifiable, Sendable {
    var id: String { episodeID }
    let episodeID: String
    let episodeNumber: Int
    let title: String
    let episodeStatus: String
    let runID: String?
    let runStatus: String?
    let stage: String
    let progressPercent: Int
    let currentAction: String
    let explanation: String
    let canCancel: Bool
    let canResume: Bool
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case title, stage, explanation
        case episodeID = "episode_id"
        case episodeNumber = "episode_number"
        case episodeStatus = "episode_status"
        case runID = "run_id"
        case runStatus = "run_status"
        case progressPercent = "progress_percent"
        case currentAction = "current_action"
        case canCancel = "can_cancel"
        case canResume = "can_resume"
        case updatedAt = "updated_at"
    }
}

struct EpisodePlanUpdateDraft: Codable, Sendable {
    let logline: String
    let outline: [String: JSONValue]
    let sourceTranscript: String

    enum CodingKeys: String, CodingKey {
        case logline, outline
        case sourceTranscript = "source_transcript"
    }
}

struct ScriptRevision: Codable, Identifiable, Sendable {
    var id: String { "\(episodeID)-\(revision)" }
    let episodeID: String
    let revision: Int
    let content: String
    let summaryForVoiceReview: String
    let sourceTranscript: String
    let narrativeMetadata: [String: JSONValue]
    let approvedAt: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case revision, content
        case episodeID = "episode_id"
        case summaryForVoiceReview = "summary_for_voice_review"
        case sourceTranscript = "source_transcript"
        case narrativeMetadata = "narrative_metadata"
        case approvedAt = "approved_at"
        case createdAt = "created_at"
    }
}

struct ScriptRevisionDraft: Codable, Sendable {
    let content: String
    let summaryForVoiceReview: String
    let sourceTranscript: String
    let narrativeMetadata: [String: JSONValue]

    enum CodingKeys: String, CodingKey {
        case content
        case summaryForVoiceReview = "summary_for_voice_review"
        case sourceTranscript = "source_transcript"
        case narrativeMetadata = "narrative_metadata"
    }
}

struct CharacterContinuityState: Codable, Equatable, Sendable {
    var location: String?
    var wardrobe: [String]?
    var injuries: [String]?
    var heldProps: [String]?
    var relationships: [String: String]?
    var revealedFacts: [String]?

    enum CodingKeys: String, CodingKey {
        case location, wardrobe, injuries, relationships
        case heldProps = "held_props"
        case revealedFacts = "revealed_facts"
    }

    var jsonValue: JSONValue {
        var object: [String: JSONValue] = [:]
        if let location { object["location"] = .string(location) }
        if let wardrobe { object["wardrobe"] = .array(wardrobe.map(JSONValue.string)) }
        if let injuries { object["injuries"] = .array(injuries.map(JSONValue.string)) }
        if let heldProps { object["held_props"] = .array(heldProps.map(JSONValue.string)) }
        if let relationships {
            object["relationships"] = .object(relationships.mapValues(JSONValue.string))
        }
        if let revealedFacts {
            object["revealed_facts"] = .array(revealedFacts.map(JSONValue.string))
        }
        return .object(object)
    }
}

struct PropContinuityState: Codable, Equatable, Sendable {
    var owner: String?
    var location: String?
    var condition: String?

    var jsonValue: JSONValue {
        var object: [String: JSONValue] = [:]
        if let owner { object["owner"] = .string(owner) }
        if let location { object["location"] = .string(location) }
        if let condition { object["condition"] = .string(condition) }
        return .object(object)
    }
}

struct ContinuityState: Codable, Equatable, Sendable {
    var characters: [String: CharacterContinuityState] = [:]
    var props: [String: PropContinuityState] = [:]
    var sceneLocation: String?
    var storyTime: String?
    var weather: String?

    enum CodingKeys: String, CodingKey {
        case characters, props, weather
        case sceneLocation = "scene_location"
        case storyTime = "story_time"
    }

    var jsonValue: JSONValue {
        var object: [String: JSONValue] = [
            "characters": .object(characters.mapValues(\.jsonValue)),
            "props": .object(props.mapValues(\.jsonValue)),
        ]
        if let sceneLocation { object["scene_location"] = .string(sceneLocation) }
        if let storyTime { object["story_time"] = .string(storyTime) }
        if let weather { object["weather"] = .string(weather) }
        return .object(object)
    }
}

struct ContinuitySnapshotDraft: Codable, Sendable {
    let sourceEpisodeID: String?
    let state: ContinuityState
    let unresolvedHooks: [String]

    enum CodingKeys: String, CodingKey {
        case state
        case sourceEpisodeID = "source_episode_id"
        case unresolvedHooks = "unresolved_hooks"
    }
}

struct ContinuitySnapshot: Codable, Identifiable, Sendable {
    let id: String
    let episodeID: String
    let sourceEpisodeID: String?
    let state: ContinuityState
    let unresolvedHooks: [String]
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, state
        case episodeID = "episode_id"
        case sourceEpisodeID = "source_episode_id"
        case unresolvedHooks = "unresolved_hooks"
        case createdAt = "created_at"
    }
}

struct ContinuityExtractionProposal: Codable, Sendable {
    let schemaVersion: String
    let episodeID: String
    let scriptRevision: Int
    let proposalSHA256: String
    let source: String
    let state: ContinuityState
    let unresolvedHooks: [String]
    let extractedPaths: [String]
    let spokenSummary: String

    enum CodingKeys: String, CodingKey {
        case source, state
        case schemaVersion = "schema_version"
        case episodeID = "episode_id"
        case scriptRevision = "script_revision"
        case proposalSHA256 = "proposal_sha256"
        case unresolvedHooks = "unresolved_hooks"
        case extractedPaths = "extracted_paths"
        case spokenSummary = "spoken_summary"
    }
}

struct ContinuityExtractionConfirmationDraft: Codable, Sendable {
    let reviewedScriptRevision: Int
    let proposalSHA256: String
    let reviewedState: ContinuityState
    let unresolvedHooks: [String]
    let confirmedBy: String
    let spokenConfirmation: String
    let reviewChannel: String
    let guardianApproval: Bool
    let changeSummary: String

    enum CodingKeys: String, CodingKey {
        case unresolvedHooks = "unresolved_hooks"
        case reviewedScriptRevision = "reviewed_script_revision"
        case proposalSHA256 = "proposal_sha256"
        case reviewedState = "reviewed_state"
        case confirmedBy = "confirmed_by"
        case spokenConfirmation = "spoken_confirmation"
        case reviewChannel = "review_channel"
        case guardianApproval = "guardian_approval"
        case changeSummary = "change_summary"
    }
}

struct ContinuityExtractionApproval: Codable, Identifiable, Sendable {
    let id: String
    let actionType: String
    let projectID: String
    let episodeID: String
    let scriptRevision: Int
    let approvedBy: String
    let spokenConfirmation: String
    let guardianApproval: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case actionType = "action_type"
        case projectID = "project_id"
        case episodeID = "episode_id"
        case scriptRevision = "script_revision"
        case approvedBy = "approved_by"
        case spokenConfirmation = "spoken_confirmation"
        case guardianApproval = "guardian_approval"
        case createdAt = "created_at"
    }
}

struct ContinuityExtractionConfirmationResult: Codable, Sendable {
    let snapshot: ContinuitySnapshot
    let approval: ContinuityExtractionApproval
}

struct InheritedContinuityResult: Codable, Sendable {
    let snapshot: ContinuitySnapshot?
}

struct ContinuityOverrideDraft: Codable, Sendable {
    let schemaVersion = "nalu.continuity-override/v1"
    let conflictPaths: [String]
    let reason: String
    let reviewedBy: String
    let spokenConfirmation: String

    enum CodingKeys: String, CodingKey {
        case reason
        case schemaVersion = "schema_version"
        case conflictPaths = "conflict_paths"
        case reviewedBy = "reviewed_by"
        case spokenConfirmation = "spoken_confirmation"
    }
}

struct ContinuityHookResolutionDraft: Codable, Identifiable, Equatable, Sendable {
    var id: String { hook }
    let hook: String
    var disposition: String
    var explanation: String
}

struct ContinuityHookReviewDraft: Codable, Equatable, Sendable {
    let schemaVersion = "nalu.continuity-hook-review/v1"
    let inheritedSnapshotID: String
    let resolutions: [ContinuityHookResolutionDraft]
    let reviewedBy: String
    let spokenConfirmation: String
    let guardianApproval: Bool

    enum CodingKeys: String, CodingKey {
        case resolutions
        case schemaVersion = "schema_version"
        case inheritedSnapshotID = "inherited_snapshot_id"
        case reviewedBy = "reviewed_by"
        case spokenConfirmation = "spoken_confirmation"
        case guardianApproval = "guardian_approval"
    }
}

struct ContinuityPreflightDraft: Codable, Sendable {
    let openingState: ContinuityState
    let transitionExplanations: [String: String]
    let override: ContinuityOverrideDraft?
    let hookReview: ContinuityHookReviewDraft?

    enum CodingKeys: String, CodingKey {
        case override
        case openingState = "opening_state"
        case transitionExplanations = "transition_explanations"
        case hookReview = "hook_review"
    }
}

struct ContinuityConflict: Codable, Identifiable, Sendable {
    var id: String { path }
    let path: String
    let inheritedValue: JSONValue
    let proposedValue: JSONValue
    let explanation: String
    let overridden: Bool

    enum CodingKeys: String, CodingKey {
        case path, explanation, overridden
        case inheritedValue = "inherited_value"
        case proposedValue = "proposed_value"
    }
}

struct ContinuityPreflightResult: Codable, Sendable {
    let inheritedSnapshotID: String?
    let canProceed: Bool
    let conflicts: [ContinuityConflict]
    let hookReviewStatus: String
    let hookResolutions: [ContinuityHookResolutionDraft]
    let explanation: String

    enum CodingKeys: String, CodingKey {
        case conflicts, explanation
        case inheritedSnapshotID = "inherited_snapshot_id"
        case canProceed = "can_proceed"
        case hookReviewStatus = "hook_review_status"
        case hookResolutions = "hook_resolutions"
    }
}

struct ContinuityCharacterEntry: Identifiable, Equatable, Sendable {
    var id = UUID()
    var name = ""
    var location = ""
    var wardrobe = ""
    var injuries = ""
    var heldProps = ""
    var relationships = ""
    var revealedFacts = ""
}

struct ContinuityPropEntry: Identifiable, Equatable, Sendable {
    var id = UUID()
    var name = ""
    var owner = ""
    var location = ""
    var condition = ""
}

struct ContinuityFormDraft: Equatable, Sendable {
    var characters: [ContinuityCharacterEntry] = []
    var props: [ContinuityPropEntry] = []
    var sceneLocation = ""
    var storyTime = ""
    var weather = ""
    var unresolvedHooks = ""

    init() {}

    init(snapshot: ContinuitySnapshot) {
        self.init(state: snapshot.state, unresolvedHooks: snapshot.unresolvedHooks)
    }

    init(state: ContinuityState, unresolvedHooks: [String] = []) {
        characters = state.characters.keys.sorted().compactMap { name in
            guard let item = state.characters[name] else { return nil }
            return ContinuityCharacterEntry(
                name: name,
                location: item.location ?? "",
                wardrobe: Self.join(item.wardrobe),
                injuries: Self.join(item.injuries),
                heldProps: Self.join(item.heldProps),
                relationships: Self.joinRelationships(item.relationships),
                revealedFacts: Self.join(item.revealedFacts)
            )
        }
        props = state.props.keys.sorted().compactMap { name in
            guard let item = state.props[name] else { return nil }
            return ContinuityPropEntry(
                name: name,
                owner: item.owner ?? "",
                location: item.location ?? "",
                condition: item.condition ?? ""
            )
        }
        sceneLocation = state.sceneLocation ?? ""
        storyTime = state.storyTime ?? ""
        weather = state.weather ?? ""
        self.unresolvedHooks = Self.join(unresolvedHooks)
    }

    var state: ContinuityState {
        var characterState: [String: CharacterContinuityState] = [:]
        for item in characters {
            let name = Self.clean(item.name)
            guard !name.isEmpty else { continue }
            characterState[name] = CharacterContinuityState(
                location: Self.optional(item.location),
                wardrobe: Self.list(item.wardrobe),
                injuries: Self.list(item.injuries),
                heldProps: Self.list(item.heldProps),
                relationships: Self.relationshipMap(item.relationships),
                revealedFacts: Self.list(item.revealedFacts)
            )
        }
        var propState: [String: PropContinuityState] = [:]
        for item in props {
            let name = Self.clean(item.name)
            guard !name.isEmpty else { continue }
            propState[name] = PropContinuityState(
                owner: Self.optional(item.owner),
                location: Self.optional(item.location),
                condition: Self.optional(item.condition)
            )
        }
        return ContinuityState(
            characters: characterState,
            props: propState,
            sceneLocation: Self.optional(sceneLocation),
            storyTime: Self.optional(storyTime),
            weather: Self.optional(weather)
        )
    }

    var hooks: [String] { Self.list(unresolvedHooks) ?? [] }

    var hasContent: Bool {
        let value = state
        return !value.characters.isEmpty || !value.props.isEmpty
            || value.sceneLocation != nil || value.storyTime != nil || value.weather != nil
            || !hooks.isEmpty
    }

    private static func clean(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func optional(_ value: String) -> String? {
        let cleaned = clean(value)
        return cleaned.isEmpty ? nil : cleaned
    }

    private static func list(_ value: String) -> [String]? {
        let values = value
            .components(separatedBy: CharacterSet(charactersIn: "、，,；;\n"))
            .map(clean)
            .filter { !$0.isEmpty }
        return values.isEmpty ? nil : values
    }

    private static func relationshipMap(_ value: String) -> [String: String]? {
        var result: [String: String] = [:]
        for line in value.components(separatedBy: CharacterSet(charactersIn: "；;\n")) {
            let pieces = line.split(
                maxSplits: 1,
                omittingEmptySubsequences: false,
                whereSeparator: { $0 == "：" || $0 == ":" }
            )
            guard pieces.count == 2 else { continue }
            let person = clean(String(pieces[0]))
            let relationship = clean(String(pieces[1]))
            if !person.isEmpty, !relationship.isEmpty { result[person] = relationship }
        }
        return result.isEmpty ? nil : result
    }

    private static func join(_ values: [String]?) -> String {
        values?.joined(separator: "、") ?? ""
    }

    private static func joinRelationships(_ values: [String: String]?) -> String {
        values?.keys.sorted().compactMap { key in
            values?[key].map { "\(key)：\($0)" }
        }.joined(separator: "；") ?? ""
    }
}

struct ScriptApprovalDraft: Codable, Sendable {
    let approvedBy: String
    let spokenConfirmation: String
    let guardianApproval: Bool

    enum CodingKeys: String, CodingKey {
        case approvedBy = "approved_by"
        case spokenConfirmation = "spoken_confirmation"
        case guardianApproval = "guardian_approval"
    }
}

struct ScriptRevocationDraft: Codable, Sendable {
    let requestedBy: String
    let reason: String

    enum CodingKeys: String, CodingKey {
        case requestedBy = "requested_by"
        case reason
    }
}

struct NaluAsset: Codable, Identifiable, Sendable {
    let id: String
    let projectID: String
    let seasonID: String?
    let episodeID: String?
    let kind: String
    let name: String
    let localURI: String
    let subjectName: String
    let metadata: [String: JSONValue]
    let consentGranted: Bool
    let consentScope: String
    let guardianApproved: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, kind, name, metadata
        case projectID = "project_id"
        case seasonID = "season_id"
        case episodeID = "episode_id"
        case localURI = "local_uri"
        case subjectName = "subject_name"
        case consentGranted = "consent_granted"
        case consentScope = "consent_scope"
        case guardianApproved = "guardian_approved"
        case createdAt = "created_at"
    }
}

struct AssetConsentRevocationDraft: Codable, Sendable {
    let requestedBy: String
    let reason: String

    enum CodingKeys: String, CodingKey {
        case requestedBy = "requested_by"
        case reason
    }
}

struct AssetConsentRecord: Codable, Sendable {
    let id: String
    let assetID: String
    let actionType: String

    enum CodingKeys: String, CodingKey {
        case id
        case assetID = "asset_id"
        case actionType = "action_type"
    }
}

struct AssetDependencyReport: Codable, Sendable {
    let assetID: String
    let canDelete: Bool
    let productionRunIDs: [String]
    let explanation: String

    enum CodingKeys: String, CodingKey {
        case explanation
        case assetID = "asset_id"
        case canDelete = "can_delete"
        case productionRunIDs = "production_run_ids"
    }
}

struct ProjectDeletionPreview: Codable, Sendable {
    let projectID: String
    let projectTitle: String
    let assetCount: Int
    let productionRunCount: Int
    let requiresSnapshotDeletionConfirmation: Bool
    let explanation: String

    enum CodingKeys: String, CodingKey {
        case explanation
        case projectID = "project_id"
        case projectTitle = "project_title"
        case assetCount = "asset_count"
        case productionRunCount = "production_run_count"
        case requiresSnapshotDeletionConfirmation = "requires_snapshot_deletion_confirmation"
    }
}

struct ProjectDeletionDraft: Codable, Sendable {
    let confirmationTitle: String
    let requestedBy: String
    let deleteProductionSnapshots: Bool

    enum CodingKeys: String, CodingKey {
        case confirmationTitle = "confirmation_title"
        case requestedBy = "requested_by"
        case deleteProductionSnapshots = "delete_production_snapshots"
    }
}

struct ProjectDeletionResult: Codable, Sendable {
    let projectID: String
    let deleted: Bool
    let removedAssetCount: Int
    let removedProductionRunCount: Int
    let verifiedAbsent: Bool

    enum CodingKeys: String, CodingKey {
        case deleted
        case projectID = "project_id"
        case removedAssetCount = "removed_asset_count"
        case removedProductionRunCount = "removed_production_run_count"
        case verifiedAbsent = "verified_absent"
    }
}

struct FeedbackDraft: Codable, Sendable {
    let projectID: String?
    let category: String
    let message: String
    let source: String
    let screen: String
    let shareAuthorized: Bool
    let guardianApproval: Bool

    enum CodingKeys: String, CodingKey {
        case category, message, source, screen
        case projectID = "project_id"
        case shareAuthorized = "share_authorized"
        case guardianApproval = "guardian_approval"
    }
}

struct FeedbackItem: Codable, Identifiable, Sendable {
    let id: String
    let projectID: String?
    let category: String
    let message: String
    let source: String
    let status: String
    let redactionApplied: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id, category, message, source, status
        case projectID = "project_id"
        case redactionApplied = "redaction_applied"
        case createdAt = "created_at"
    }
}

struct MemoryPersonDraft: Codable, Sendable {
    let name: String
    let relationship: String
    let note: String
}

struct MemoryCardDraft: Codable, Sendable {
    let assetID: String
    let title: String
    let description: String
    let ocrText: String
    let spokenContext: String
    let approximateDate: String
    let place: String
    let people: [MemoryPersonDraft]
    let storyRelevance: String
    let allowedUse: String

    enum CodingKeys: String, CodingKey {
        case title, description, place, people
        case assetID = "asset_id"
        case ocrText = "ocr_text"
        case spokenContext = "spoken_context"
        case approximateDate = "approximate_date"
        case storyRelevance = "story_relevance"
        case allowedUse = "allowed_use"
    }
}

struct MemoryCard: Codable, Identifiable, Sendable {
    let id: String
    let projectID: String
    let assetID: String
    let title: String
    let description: String
    let ocrText: String
    let spokenContext: String
    let approximateDate: String
    let place: String
    let people: [MemoryPersonDraft]
    let storyRelevance: String
    let allowedUse: String
    let currentRevision: Int
    let confirmationStatus: String

    enum CodingKeys: String, CodingKey {
        case id, title, description, place, people
        case projectID = "project_id"
        case assetID = "asset_id"
        case ocrText = "ocr_text"
        case spokenContext = "spoken_context"
        case approximateDate = "approximate_date"
        case storyRelevance = "story_relevance"
        case allowedUse = "allowed_use"
        case currentRevision = "current_revision"
        case confirmationStatus = "confirmation_status"
    }
}

struct MemoryCardConfirmationDraft: Codable, Sendable {
    let confirmedBy: String
    let reviewedRevision: Int
    let reviewChannel: String
    let spokenConfirmation: String

    enum CodingKeys: String, CodingKey {
        case confirmedBy = "confirmed_by"
        case reviewedRevision = "reviewed_revision"
        case reviewChannel = "review_channel"
        case spokenConfirmation = "spoken_confirmation"
    }
}

struct MemoryCardUpdateDraft: Codable, Sendable {
    let title: String
    let description: String
    let approximateDate: String
    let place: String
    let storyRelevance: String
    let allowedUse: String
    let sourceChannel: String
    let changeSummary: String

    enum CodingKeys: String, CodingKey {
        case title, description, place
        case approximateDate = "approximate_date"
        case storyRelevance = "story_relevance"
        case allowedUse = "allowed_use"
        case sourceChannel = "source_channel"
        case changeSummary = "change_summary"
    }
}

struct MemoryGraphConflict: Codable, Sendable {
    let kind: String
    let subject: String
    let candidateValue: String
    let existingValue: String
    let candidateMemoryID: String
    let candidateRevision: Int
    let candidateAssetID: String
    let existingMemoryID: String
    let existingRevision: Int
    let existingAssetID: String
    let explanation: String

    enum CodingKeys: String, CodingKey {
        case kind, subject, explanation
        case candidateValue = "candidate_value"
        case existingValue = "existing_value"
        case candidateMemoryID = "candidate_memory_id"
        case candidateRevision = "candidate_revision"
        case candidateAssetID = "candidate_asset_id"
        case existingMemoryID = "existing_memory_id"
        case existingRevision = "existing_revision"
        case existingAssetID = "existing_asset_id"
    }
}

struct MemoryGraphConflictReport: Codable, Sendable {
    let projectID: String
    let candidateMemoryID: String
    let checkedAgainstConfirmedCards: Int
    let blocking: Bool
    let conflicts: [MemoryGraphConflict]
    let spokenSummary: String

    enum CodingKeys: String, CodingKey {
        case blocking, conflicts
        case projectID = "project_id"
        case candidateMemoryID = "candidate_memory_id"
        case checkedAgainstConfirmedCards = "checked_against_confirmed_cards"
        case spokenSummary = "spoken_summary"
    }
}

struct DocumentaryEvidenceItem: Codable, Identifiable, Sendable {
    var id: String { assetID }
    let assetID: String
    let memoryID: String?
    let name: String
    let kind: String
    let scope: String
    let confirmationStatus: String
    let currentRevision: Int?
    let allowedUse: String?
    let narrativeAuthority: Bool
    let visualGenerationAuthorized: Bool

    enum CodingKeys: String, CodingKey {
        case name, kind, scope
        case assetID = "asset_id"
        case memoryID = "memory_id"
        case confirmationStatus = "confirmation_status"
        case currentRevision = "current_revision"
        case allowedUse = "allowed_use"
        case narrativeAuthority = "narrative_authority"
        case visualGenerationAuthorized = "visual_generation_authorized"
    }
}

struct DocumentaryReadinessReport: Codable, Sendable {
    let projectID: String
    let documentaryMode: String
    let evidence: [DocumentaryEvidenceItem]
    let confirmedNarrativeSourceCount: Int
    let draftOrUnlinkedSourceCount: Int
    let canPlanChapters: Bool
    let canEnterProduction: Bool
    let generatedReenactmentLabelRequired: Bool
    let blockers: [String]
    let nextQuestions: [String]

    enum CodingKeys: String, CodingKey {
        case evidence, blockers
        case projectID = "project_id"
        case documentaryMode = "documentary_mode"
        case confirmedNarrativeSourceCount = "confirmed_narrative_source_count"
        case draftOrUnlinkedSourceCount = "draft_or_unlinked_source_count"
        case canPlanChapters = "can_plan_chapters"
        case canEnterProduction = "can_enter_production"
        case generatedReenactmentLabelRequired = "generated_reenactment_label_required"
        case nextQuestions = "next_questions"
    }

    var spokenSummary: String {
        var parts = [
            "这个纪录片项目有 \(evidence.count) 份本地资料。",
            "其中 \(confirmedNarrativeSourceCount) 份已经确认，可以作为故事依据。",
        ]
        if draftOrUnlinkedSourceCount > 0 {
            parts.append("还有 \(draftOrUnlinkedSourceCount) 份需要说明或确认。")
        }
        parts.append(
            canPlanChapters
                ? "现在可以开始规划章节，但还不能进入成片生产。"
                : "请先确认至少一份允许用于故事发展的资料。"
        )
        if generatedReenactmentLabelRequired {
            parts.append("以后生成的剧情重现画面必须清楚标明为重现。")
        }
        if let question = nextQuestions.first { parts.append(question) }
        return parts.joined(separator: " ")
    }
}

struct LibraryEntityRevisionDraft: Codable, Sendable {
    let name: String
    let description: String
    let attributes: [String: JSONValue]
    let sourceAssetIDs: [String]
    let sourceMemoryIDs: [String]
    let sourceChannel: String
    let changeSummary: String

    enum CodingKeys: String, CodingKey {
        case name, description, attributes
        case sourceAssetIDs = "source_asset_ids"
        case sourceMemoryIDs = "source_memory_ids"
        case sourceChannel = "source_channel"
        case changeSummary = "change_summary"
    }
}

struct LibraryEntityCreateDraft: Codable, Sendable {
    let kind: String
    let name: String
    let description: String
    let attributes: [String: JSONValue]
    let sourceAssetIDs: [String]
    let sourceMemoryIDs: [String]
    let sourceChannel: String
    let changeSummary: String

    enum CodingKeys: String, CodingKey {
        case kind, name, description, attributes
        case sourceAssetIDs = "source_asset_ids"
        case sourceMemoryIDs = "source_memory_ids"
        case sourceChannel = "source_channel"
        case changeSummary = "change_summary"
    }
}

struct LibraryEntityRevision: Codable, Sendable {
    let entityID: String
    let revision: Int
    let name: String
    let description: String
    let attributes: [String: JSONValue]
    let sourceAssetIDs: [String]
    let sourceMemoryIDs: [String]
    let sourceChannel: String
    let changeSummary: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case revision, name, description, attributes
        case entityID = "entity_id"
        case sourceAssetIDs = "source_asset_ids"
        case sourceMemoryIDs = "source_memory_ids"
        case sourceChannel = "source_channel"
        case changeSummary = "change_summary"
        case createdAt = "created_at"
    }
}

struct LibraryEntity: Codable, Identifiable, Sendable {
    let id: String
    let projectID: String
    let kind: String
    let stableName: String
    let currentRevision: Int
    let confirmedRevision: Int?
    let current: LibraryEntityRevision
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id, kind, current
        case projectID = "project_id"
        case stableName = "stable_name"
        case currentRevision = "current_revision"
        case confirmedRevision = "confirmed_revision"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct LibraryEntityConfirmationDraft: Codable, Sendable {
    let confirmedBy: String
    let reviewedRevision: Int
    let reviewChannel: String
    let spokenConfirmation: String

    enum CodingKeys: String, CodingKey {
        case confirmedBy = "confirmed_by"
        case reviewedRevision = "reviewed_revision"
        case reviewChannel = "review_channel"
        case spokenConfirmation = "spoken_confirmation"
    }
}

struct LibraryEntityConfirmationRecord: Codable, Sendable {
    let id: String
    let entityID: String
    let confirmedBy: String
    let reviewedRevision: Int
    let reviewChannel: String
    let spokenConfirmation: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case entityID = "entity_id"
        case confirmedBy = "confirmed_by"
        case reviewedRevision = "reviewed_revision"
        case reviewChannel = "review_channel"
        case spokenConfirmation = "spoken_confirmation"
        case createdAt = "created_at"
    }
}

struct ProjectPlanDraft: Codable, Sendable {
    let projectID: String?
    let project: ProjectDraft
    let seasonTitle: String

    init(project: ProjectDraft, seasonTitle: String, projectID: String? = nil) {
        self.projectID = projectID
        self.project = project
        self.seasonTitle = seasonTitle
    }

    enum CodingKeys: String, CodingKey {
        case project
        case projectID = "project_id"
        case seasonTitle = "season_title"
    }
}

struct ProjectPlan: Codable, Sendable {
    let project: NaluProject
    let season: NaluSeason
    let episodes: [NaluEpisode]
}

struct InterviewMessage: Identifiable, Sendable {
    enum Speaker: Sendable, Equatable { case nalu, user }
    let id = UUID()
    let speaker: Speaker
    let text: String
}
