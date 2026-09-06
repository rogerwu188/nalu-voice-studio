import Foundation

struct InteractiveEpisodeDraft: Codable, Equatable, Sendable {
    let episode_number: Int
    let title: String
    let outline: String
    let script: String
}

struct InteractiveStoryAnswer: Codable, Equatable, Sendable {
    let reply: String
    let summary: String
    let episode_drafts: [InteractiveEpisodeDraft]
    let outcome: String
}

struct InteractiveStoryTurn: Codable, Sendable {
    let turn_id: String
    let text: String
    let source_mode: String
    let status: String
    let answer: InteractiveStoryAnswer?
}

struct InteractiveStoryState: Codable, Sendable {
    let revision: Int
    let turns: [InteractiveStoryTurn]
    let summary: String
    let episode_drafts: [InteractiveEpisodeDraft]
}

struct InteractiveStoryInput: Encodable {
    let turn_id: String
    let expected_revision: Int
    let text: String
    let source_mode: String
}

struct InteractiveStoryAnswerRequest: Encodable {
    let expected_revision: Int
    let reply: String
    let summary: String
    let episode_drafts: [InteractiveEpisodeDraft]
    let outcome: String
}
