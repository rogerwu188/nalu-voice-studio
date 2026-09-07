import Foundation

struct ProductionAuthorizationDraft: Codable, Equatable {
    var source_event_id: String
    var expected_plan_sha256: String
    var expected_package_sha256: String
    var confirmed_run_budget_credits: Int
    var approved_by = "nalu-native-user"
    var confirmation: String
    var guardian_approval: Bool
}

/// Budget collection is not approval. A separate readback and explicit reply are
/// required. Unrelated questions fall through to the normal assistant.
struct ProductionBudgetConversation {
    let runID: String
    let episodeID: String
    let preview: LibrarySnapshotRefreshPreview.Request
    let guardianRequired: Bool
    var credits: Int?
    var submittedDraft: ProductionAuthorizationDraft?

    enum Answer {
        case reply(String)
        case submit(ProductionAuthorizationDraft)
        case cancel
        case unrelated
    }

    var opening: String {
        "本集剧本和分镜已经保留。您愿意给这一集安排多少积分的预计制作预算？可以说“本集预算一千积分”。这只是说法示例，不是报价。"
    }
    var confirmationPhrase: String { guardianRequired ? "我是监护人，确认本集预算" : "确认本集预算" }
    var readback: String {
        guard let credits else { return opening }
        return "本集预计预算是 \(credits) 积分。积分是模型服务的计费单位，不是人民币；这是本地预算，不是服务商保证的扣费上限。每个镜头的费用还会单独核对，现在不会生成或扣费。"
            + "同意请说“\(confirmationPhrase)”，也可以重新说预算，或说“取消制作确认”。"
    }

    mutating func answer(_ text: String) -> Answer {
        let clean = Self.normalize(text)
        if ["取消制作确认", "先不制作", "先不做了", "取消预算确认"].contains(clean) { return .cancel }
        if let submittedDraft {
            return clean == "重试制作确认" ? .submit(submittedDraft) : .unrelated
        }
        if let value = Self.budget(text) {
            credits = value
            return .reply(readback)
        }
        if clean == Self.normalize(confirmationPhrase), let credits {
            let draft = ProductionAuthorizationDraft(source_event_id: preview.source_event_id,
                expected_plan_sha256: preview.expected_plan_sha256,
                expected_package_sha256: preview.expected_package_sha256,
                confirmed_run_budget_credits: credits, confirmation: text,
                guardian_approval: guardianRequired)
            submittedDraft = draft
            return .submit(draft)
        }
        if clean.contains("积分") || clean.contains("预算") {
            return .reply(readback)
        }
        return .unrelated
    }

    static func normalize(_ text: String) -> String {
        text.folding(options: .widthInsensitive, locale: Locale(identifier: "zh_CN"))
            .filter { !$0.isWhitespace && !"，。！？,.!?".contains($0) }
    }

    static func budget(_ text: String) -> Int? {
        // Keep decimal punctuation: “1.5积分” must never become “15积分”.
        let clean = text.folding(options: .widthInsensitive, locale: Locale(identifier: "zh_CN"))
            .trimmingCharacters(in: .whitespacesAndNewlines.union(CharacterSet(charactersIn: "。！？!?")))
            .filter { !$0.isWhitespace }
        let pattern = "^(?:本集)?(?:预算(?:改为|是|为)?)?([0-9]+|[零一二两三四五六七八九十百千万]+)积分$"
        guard clean.count <= 80, let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: clean, range: NSRange(clean.startIndex..., in: clean)),
              let range = Range(match.range(at: 1), in: clean) else { return nil }
        let number = String(clean[range])
        if let integer = Int(number) { return (1...1_000_000).contains(integer) ? integer : nil }
        let digits: [Character: Int] = ["一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                                      "五": 5, "六": 6, "七": 7, "八": 8, "九": 9]
        let units: [Character: Int] = ["十": 10, "百": 100, "千": 1000, "万": 10000]
        var total = 0, lastUnit = 100001
        var digit: Int?
        var zero = false
        for character in number {
            if character == "零" {
                guard total > 0, digit == nil, !zero else { return nil }
                zero = true
            } else if let value = digits[character] {
                guard digit == nil else { return nil }
                digit = value
            } else if let unit = units[character] {
                guard unit < lastUnit, digit != nil || (unit == 10 && total == 0 && !zero) else { return nil }
                total += (digit ?? 1) * unit
                digit = nil
                lastUnit = unit
                zero = false
            } else { return nil }
        }
        if let digit {
            // Do not guess whether “一千五” means 1005 or 1500.
            guard total == 0 || lastUnit == 10 || zero else { return nil }
            total += digit
        } else if zero { return nil }
        return (1...1_000_000).contains(total) ? total : nil
    }
}
