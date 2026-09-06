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
    var draft_writers: [String: ExternalWriterDeclaration?]? = nil

    func conversationMessages() -> [InterviewMessage] {
        var messages: [InterviewMessage] = []
        for turn in turns {
            messages.append(.init(speaker: .user, text: turn.text))
            if let answer = turn.answer {
                let drafts = answer.episode_drafts.map {
                    "第\($0.episode_number)集《\($0.title)》草稿\n\($0.outline)\n\n\($0.script)"
                }.joined(separator: "\n\n")
                messages.append(.init(speaker: .nalu,
                    text: answer.reply + (drafts.isEmpty ? "" : "\n\n" + drafts)))
            } else if turn.status == "pending" {
                messages.append(.init(speaker: .nalu,
                    text: "这句话已保存，但上次请求没有记录到完整结果。我没有自动重复调用；您可以继续补充。"))
            }
        }
        return messages
    }
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
    var external_writer: ExternalWriterDeclaration? = nil
    var writer_response_json: String? = nil
}
