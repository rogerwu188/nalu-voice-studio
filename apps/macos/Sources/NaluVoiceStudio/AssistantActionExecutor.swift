import Foundation

enum AssistantActionRequest: Equatable {
    case webResearch(query: String)
    case requiresConfirmation(description: String)
}

enum AssistantActionRouter {
    static let maximumQueryCharacters = 2_000

    static func route(_ spoken: String) -> AssistantActionRequest? {
        let cleaned = spoken.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return nil }

        let executionSignals = [
            "网上", "网络上", "上网", "网站", "搜索", "搜一下", "查一下", "查找", "帮我找",
        ]
        guard executionSignals.contains(where: cleaned.contains) else { return nil }

        if requiresConfirmation(cleaned) {
            return .requiresConfirmation(description: String(cleaned.prefix(maximumQueryCharacters)))
        }
        return .webResearch(query: String(cleaned.prefix(maximumQueryCharacters)))
    }

    static func requiresConfirmation(_ text: String) -> Bool {
        let protectedSignals = [
            "下载", "购买", "付款", "下单", "发布", "上传", "发送", "删除", "注册", "登录",
        ]
        return protectedSignals.contains(where: text.contains)
    }
}

struct WebResearchSource: Equatable, Sendable {
    let title: String
    let url: URL
}

struct WebResearchResult: Equatable, Sendable {
    let answer: String
    let sources: [WebResearchSource]

    func conversationText(resumePrompt: String) -> String {
        var sections = [answer]
        if !sources.isEmpty {
            let links = sources.prefix(5).map { source in
                "• [\(source.title)](\(source.url.absoluteString))"
            }
            sections.append("参考来源：\n" + links.joined(separator: "\n"))
        }
        sections.append("我们再接着刚才的创作：\(resumePrompt)")
        return sections.joined(separator: "\n\n")
    }
}

enum WebResearchError: LocalizedError {
    case missingCredential
    case requestFailed
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .missingCredential:
            "请先在“模型密钥”中保存 OpenAI API 密钥，我才能替您上网查找。"
        case .requestFailed:
            "这次联网查找没有成功。我没有自动重试，也没有改变您的创作进度。"
        case .invalidResponse:
            "联网结果格式不正确。我没有采用这份结果，也没有改变您的创作进度。"
        }
    }

    static func publicDescription(for error: Error) -> String {
        (error as? WebResearchError)?.localizedDescription
            ?? WebResearchError.requestFailed.localizedDescription
    }
}

actor OpenAIWebResearchClient {
    static let endpoint = URL(string: "https://api.openai.com/v1/responses")!
    static let model = "gpt-5.4-mini"
    static let maximumResponseBytes = 2_000_000

    private let session: URLSession
    private let fixedAPIKey: String?

    init(session: URLSession? = nil, fixedAPIKey: String? = nil) {
        if let session {
            self.session = session
        } else {
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 45
            configuration.waitsForConnectivity = false
            self.session = URLSession(configuration: configuration)
        }
        self.fixedAPIKey = fixedAPIKey
    }

    func research(_ query: String) async throws -> WebResearchResult {
        let apiKey = try fixedAPIKey ?? KeychainSecretStore().secret(for: .openAIRealtime)
        guard let apiKey, !apiKey.isEmpty else { throw WebResearchError.missingCredential }

        let request = try Self.makeRequest(query: query, apiKey: apiKey)
        let (data, response) = try await session.data(for: request)
        guard data.count <= Self.maximumResponseBytes,
              let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode) else {
            throw WebResearchError.requestFailed
        }
        return try Self.parseResponse(data)
    }

    static func makeRequest(query: String, apiKey: String) throws -> URLRequest {
        var request = URLRequest(url: Self.endpoint)
        request.httpMethod = "POST"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "model": Self.model,
            "instructions": """
                你是 Nalu 的只读联网研究员。只回答用户本次查询，不执行下载、登录、购买、
                发布、上传、发送、删除或其他外部写入。用简短清楚的中文回答，保留事实限定。
                """,
            "input": String(query.prefix(AssistantActionRouter.maximumQueryCharacters)),
            "tools": [["type": "web_search"]],
            "tool_choice": "auto",
            "include": ["web_search_call.action.sources"],
            "max_tool_calls": 3,
            "max_output_tokens": 800,
            "store": false,
        ])
        return request
    }

    static func parseResponse(_ data: Data) throws -> WebResearchResult {
        guard data.count <= maximumResponseBytes,
              let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let output = root["output"] as? [[String: Any]] else {
            throw WebResearchError.invalidResponse
        }

        var textParts: [String] = []
        var sources: [WebResearchSource] = []
        var seenURLs: Set<String> = []

        func admit(title: String?, urlString: String?) {
            guard sources.count < 12,
                  let urlString,
                  !seenURLs.contains(urlString),
                  let url = URL(string: urlString),
                  url.scheme?.lowercased() == "https",
                  url.host != nil else { return }
            seenURLs.insert(urlString)
            let cleanedTitle = title?.trimmingCharacters(in: .whitespacesAndNewlines)
            sources.append(.init(
                title: String((cleanedTitle?.isEmpty == false ? cleanedTitle! : url.host!).prefix(160)),
                url: url
            ))
        }

        for item in output {
            if item["type"] as? String == "message",
               let content = item["content"] as? [[String: Any]] {
                for part in content where part["type"] as? String == "output_text" {
                    if let text = part["text"] as? String,
                       !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        textParts.append(text)
                    }
                    for annotation in part["annotations"] as? [[String: Any]] ?? [] {
                        admit(
                            title: annotation["title"] as? String,
                            urlString: annotation["url"] as? String
                        )
                    }
                }
            }
            if item["type"] as? String == "web_search_call",
               let action = item["action"] as? [String: Any] {
                for source in action["sources"] as? [[String: Any]] ?? [] {
                    admit(title: source["title"] as? String, urlString: source["url"] as? String)
                }
            }
        }

        let answer = textParts.joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !answer.isEmpty else { throw WebResearchError.invalidResponse }
        return WebResearchResult(answer: String(answer.prefix(8_000)), sources: sources)
    }
}
