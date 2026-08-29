import Foundation

struct ProjectDraft: Codable, Sendable {
    var title = ""
    var description = ""
    var audienceMode = "general"
    var plannedEpisodeCount = 6
    var targetEpisodeSeconds = 150

    enum CodingKeys: String, CodingKey {
        case title, description
        case audienceMode = "audience_mode"
        case plannedEpisodeCount = "planned_episode_count"
        case targetEpisodeSeconds = "target_episode_seconds"
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
}

struct InterviewMessage: Identifiable, Sendable {
    enum Speaker: Sendable, Equatable { case nalu, user }
    let id = UUID()
    let speaker: Speaker
    let text: String
}
