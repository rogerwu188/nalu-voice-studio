import Foundation

enum ComfortPreferencesStore {
    static let key = "nalu.comfort-preferences.v1"

    private static func qaURL(inherited: [String: String]) throws -> URL {
        try RuntimeApplicationSupportResolver.resolve(
            inherited: inherited, defaultURL: URL(fileURLWithPath: "/unused")
        ).appending(path: "comfort-preferences.json")
    }

    static func load(
        inherited: [String: String] = ProcessInfo.processInfo.environment,
        defaults: UserDefaults = .standard
    ) -> ComfortPreferences {
        let data: Data?
        if inherited[RuntimeApplicationSupportResolver.localQAFlag] == "1" {
            // Invalid QA configuration must never fall back to real user preferences.
            data = try? Data(contentsOf: qaURL(inherited: inherited))
        } else {
            data = defaults.data(forKey: key)
        }
        guard let data,
              let preferences = try? JSONDecoder().decode(ComfortPreferences.self, from: data)
        else { return ComfortPreferences() }
        return preferences
    }

    static func save(
        _ preferences: ComfortPreferences,
        inherited: [String: String] = ProcessInfo.processInfo.environment,
        defaults: UserDefaults = .standard
    ) throws {
        let data = try JSONEncoder().encode(preferences)
        if inherited[RuntimeApplicationSupportResolver.localQAFlag] == "1" {
            try data.write(to: qaURL(inherited: inherited), options: .atomic)
        } else {
            defaults.set(data, forKey: key)
        }
    }
}

struct ComfortPreferences: Codable, Equatable, Sendable {
    var textLevel = 1
    var speechRate: Float = 0.42

    mutating func consume(_ spoken: String) -> String? {
        if spoken.contains("字大一点") || spoken.contains("字体大一点")
            || spoken.contains("看不清字") {
            textLevel = min(textLevel + 1, 3)
            return textLevel == 3 ? "好的，文字已经调到最大。" : "好的，文字已经放大。"
        }
        if spoken.contains("字小一点") || spoken.contains("字体小一点") {
            textLevel = max(textLevel - 1, 0)
            return textLevel == 0 ? "好的，文字已经调到最小。" : "好的，文字已经缩小一点。"
        }
        if spoken.contains("说慢一点") || spoken.contains("读慢一点") {
            speechRate = max(speechRate - 0.04, 0.30)
            return "好的，以后我会读慢一点。"
        }
        if spoken.contains("说快一点") || spoken.contains("读快一点") {
            speechRate = min(speechRate + 0.04, 0.54)
            return "好的，以后我会读快一点。"
        }
        if spoken.contains("恢复舒适设置") || spoken.contains("恢复字号和语速") {
            self = ComfortPreferences()
            return "好的，文字大小和朗读速度已经恢复默认。"
        }
        return nil
    }
}
