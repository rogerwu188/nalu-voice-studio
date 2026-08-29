import Foundation

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

    enum CodingKeys: String, CodingKey {
        case id, title, description
        case audienceMode = "audience_mode"
        case plannedEpisodeCount = "planned_episode_count"
    }
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

    enum CodingKeys: String, CodingKey {
        case id, title
        case projectID = "project_id"
        case seasonNumber = "season_number"
        case plannedEpisodeCount = "planned_episode_count"
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
    let status: String

    enum CodingKeys: String, CodingKey {
        case id, title, status
        case episodeNumber = "episode_number"
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
