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
}

struct ProjectDraft: Codable, Sendable {
    var title = ""
    var description = ""
    var audienceMode = "general"
    var plannedEpisodeCount = 6
    var targetEpisodeSeconds = 150
    var projectBible: [String: String] = [:]

    enum CodingKeys: String, CodingKey {
        case title, description
        case audienceMode = "audience_mode"
        case plannedEpisodeCount = "planned_episode_count"
        case targetEpisodeSeconds = "target_episode_seconds"
        case projectBible = "project_bible"
    }
}

struct NaluProject: Codable, Identifiable, Sendable {
    let id: String
    let title: String
    let description: String
    let audienceMode: String
    let plannedEpisodeCount: Int
    let archivedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, description
        case audienceMode = "audience_mode"
        case plannedEpisodeCount = "planned_episode_count"
        case archivedAt = "archived_at"
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
    let approvedAt: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case revision, content
        case episodeID = "episode_id"
        case summaryForVoiceReview = "summary_for_voice_review"
        case sourceTranscript = "source_transcript"
        case approvedAt = "approved_at"
        case createdAt = "created_at"
    }
}

struct ScriptRevisionDraft: Codable, Sendable {
    let content: String
    let summaryForVoiceReview: String
    let sourceTranscript: String

    enum CodingKeys: String, CodingKey {
        case content
        case summaryForVoiceReview = "summary_for_voice_review"
        case sourceTranscript = "source_transcript"
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

struct ProjectPlanDraft: Codable, Sendable {
    let project: ProjectDraft
    let seasonTitle: String

    enum CodingKeys: String, CodingKey {
        case project
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
