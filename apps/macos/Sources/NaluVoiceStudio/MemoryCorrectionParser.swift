import Foundation

struct MemoryCorrection: Equatable, Sendable {
    enum Field: Equatable, Sendable {
        case title, description, approximateDate, place, storyRelevance
    }

    let field: Field
    let value: String
}

enum MemoryCorrectionParser {
    static func parse(_ spoken: String) -> MemoryCorrection? {
        let rules: [(keywords: [String], field: MemoryCorrection.Field)] = [
            (["地点", "地方"], .place),
            (["时间", "年份", "日期"], .approximateDate),
            (["标题", "名字"], .title),
            (["故事意义", "故事作用"], .storyRelevance),
            (["说明", "描述"], .description),
        ]
        for rule in rules where rule.keywords.contains(where: spoken.contains) {
            guard let value = correctedValue(from: spoken) else { return nil }
            return MemoryCorrection(field: rule.field, value: value)
        }
        return nil
    }

    private static func correctedValue(from spoken: String) -> String? {
        let separators = ["改成", "改为", "应该是", "其实是", "是"]
        for separator in separators {
            guard let range = spoken.range(of: separator, options: .backwards) else { continue }
            let value = spoken[range.upperBound...]
                .trimmingCharacters(in: .whitespacesAndNewlines.union(.punctuationCharacters))
            if !value.isEmpty { return value }
        }
        return nil
    }
}

