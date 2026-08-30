import Foundation

enum ProductionVoiceCommand: Equatable {
    case requestPause
    case confirmPause
    case cancelPause
    case clarifyPause
    case requestResume
}

enum ProductionVoiceCommandParser {
    static func parse(
        _ spoken: String,
        awaitingPauseConfirmation: Bool
    ) -> ProductionVoiceCommand? {
        let normalized = spoken
            .replacingOccurrences(of: " ", with: "")
            .replacingOccurrences(of: "，", with: "")
            .replacingOccurrences(of: "。", with: "")

        if awaitingPauseConfirmation {
            if containsAny(normalized, ["不暂停", "别暂停", "继续做", "继续制作", "算了", "取消"]) {
                return .cancelPause
            }
            if containsAny(normalized, ["确认暂停", "确定暂停", "是的暂停", "我确认暂停"]) {
                return .confirmPause
            }
            return .clarifyPause
        }

        if containsAny(
            normalized,
            ["暂停制作", "停止制作", "暂停这一集", "暂停本集", "把这集停下"]
        ) {
            return .requestPause
        }
        if containsAny(
            normalized,
            ["恢复制作", "恢复本集制作", "继续制作", "接着制作", "恢复这一集", "继续这一集"]
        ) {
            return .requestResume
        }
        return nil
    }

    private static func containsAny(_ text: String, _ phrases: [String]) -> Bool {
        phrases.contains(where: text.contains)
    }
}
