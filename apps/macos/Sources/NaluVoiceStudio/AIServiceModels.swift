import Foundation

struct AIServiceModels: Codable, Equatable {
    var research = "gpt-5.4-mini"
    var realtime = "gpt-realtime-2.1"
    var transcription = "gpt-4o-mini-transcribe"

    func validated() throws -> AIServiceModels {
        for name in [research, realtime, transcription] {
            guard !name.isEmpty, name.count <= 128, !name.hasPrefix("sk-"),
                  name.range(of: "^[A-Za-z0-9][A-Za-z0-9._:/-]*$", options: .regularExpression) != nil
            else { throw ModelError.invalidIdentifier }
        }
        return self
    }

    private static func key(for endpoint: AIServiceEndpoint) -> String {
        "nalu.ai-models.v1." + endpoint.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    static func load(for endpoint: AIServiceEndpoint, defaults: UserDefaults = .standard) throws -> AIServiceModels {
        guard let data = defaults.data(forKey: key(for: endpoint)) else { return Self() }
        return try JSONDecoder().decode(Self.self, from: data).validated()
    }

    func save(for endpoint: AIServiceEndpoint, defaults: UserDefaults = .standard) throws {
        defaults.set(try JSONEncoder().encode(validated()), forKey: Self.key(for: endpoint))
    }

    enum ModelError: LocalizedError {
        case invalidIdentifier
        var errorDescription: String? { "请输入服务商提供的模型 ID，不要填写密钥、空格或说明文字。" }
    }
}
