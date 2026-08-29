import Foundation

/// Keeps a structured interview from mistaking a conversational interruption for
/// an answer. Interruptions are answered first and never mutate the project draft.
enum InterviewInterruptionRouter {
    static func response(for spoken: String, resumePrompt: String) -> String? {
        let normalized = spoken
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: " ", with: "")

        guard isConversationInterruption(normalized) else { return nil }

        let answer: String
        if containsAny(normalized, ["听见", "听到", "在听", "听得见"]) {
            answer = "我听见了，也会先回答您现在问的事情。"
        } else if containsAny(normalized, ["你是谁", "叫什么"]) {
            answer = "我是 Nalu，一位陪您聊天、整理回忆并把故事交给专业生产线的语音创作助手。"
        } else if containsAny(normalized, ["实时语音", "自然语音", "一直对话"]) {
            answer = "您说的是自然语音对话：不用每次按一下，可以随时插话，我回答后再接着创作。当前这次是按键说话模式，自然语音模式需要单独开启云端语音并得到您的同意。"
        } else if containsAny(normalized, ["为什么不回答", "为什么不和我", "没有回答", "不对题"]) {
            answer = "刚才我只顾着按流程提问，没有先回答您，这是不对的。以后您随时插话，我会先答您的问题，再回到没有完成的步骤。"
        } else if containsAny(normalized, ["能不能聊天", "能聊天", "交流", "交互", "跟我说话", "回答问题", "我在问你"]) {
            answer = "可以。您不必顺着固定流程说；可以先提问、补充或纠正我。我会先回应，再带您回到刚才的位置。"
        } else if containsAny(normalized, ["你在干什么", "现在干什么", "怎么用", "下一步"]) {
            answer = "我正在听您说话，并把创作过程一次只推进一小步。您也可以随时停下来问我任何关于当前操作的问题。"
        } else {
            answer = "我听到您是在问我问题，不是在回答表格。我会保留现在的进度，先和您说清楚。"
        }

        return "\(answer)\n\n说清楚以后，我们再接着来：\(resumePrompt)"
    }

    private static func isConversationInterruption(_ spoken: String) -> Bool {
        containsAny(
            spoken,
            [
                "你在干什么", "现在干什么", "为什么不回答", "为什么不和我",
                "没有回答", "不对题", "我在问你", "回答问题", "能不能聊天",
                "能聊天", "跟我说话", "跟我交流", "交互沟通", "听得见",
                "你听见", "你听到", "你是谁", "叫什么", "怎么用",
                "实时语音", "自然语音", "一直对话",
            ]
        )
    }

    private static func containsAny(_ text: String, _ phrases: [String]) -> Bool {
        phrases.contains(where: text.contains)
    }
}
