import Foundation

enum AssistantActionRequest: Equatable {
    case webResearch(query: String)
    case requiresConfirmation(description: String)
}

enum AssistantActionRouter {
    static let maximumQueryCharacters = 2_000

    static func requestsNovelImport(_ text: String) -> Bool {
        let cleaned = text.filter { !$0.isWhitespace }
        guard !["不要", "先别", "暂不", "只查", "只找", "登录", "购买", "付款", "发布",
                "下单", "上传", "发送", "删除", "注册"].contains(where: cleaned.contains)
        else { return false }
        return ["小说", "章节", "整本书"].contains(where: cleaned.contains)
            && (["抓取", "下载", "导入", "保存到本地"].contains(where: cleaned.contains)
                || requestsSourceWriting(cleaned))
    }

    static func requestsSourceWriting(_ text: String) -> Bool {
        let cleaned = text.filter { !$0.isWhitespace }
        guard !["不要", "先别", "暂不", "只查", "只找"].contains(where: cleaned.contains) else { return false }
        if ["作为剧本", "生成剧本", "改编成", "写成剧本", "做成短剧", "拿来写剧本", "用来写剧本"].contains(where: cleaned.contains) { return true }
        // Spoken requests include measure words and fillers, not exact UI labels.
        // This starts only unapproved writing, never production or publication.
        let patterns = [
            #"(?:作为|当作|用作)(?:这个|那个|整个|整部|我们的|我的)*剧本"#,
            #"(?:做成|拍成|写成|改成)(?:一部|一个|一套|多集|若干集)?(?:电视)?(?:连续剧|短剧|电影|纪录片|动画片)"#,
            #"(?:写|编|生成)(?:一下|出|成)?(?:第[一二三四五六七八九十0-9]+集|分集)(?:的)?剧本"#,
        ]
        return patterns.contains { cleaned.range(of: $0, options: .regularExpression) != nil }
    }

    static func route(_ spoken: String) -> AssistantActionRequest? {
        let cleaned = spoken.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return nil }

        let executionSignals = [
            "网上", "网络上", "上网", "网站", "网页", "搜索", "搜一下", "查一下", "查找", "帮我找",
        ]
        let sourceLookup = cleaned.range(
            of: #"(?:请|帮我)?找(?:到|一下)?(?:这|那|一)(?:篇文章|本书|本小说|份资料|个网址)"#,
            options: .regularExpression
        ) != nil && requestsSourceWriting(cleaned)
        guard executionSignals.contains(where: cleaned.contains)
                || sourceURL(in: cleaned) != nil || sourceLookup
                || requestsNovelImport(cleaned) else { return nil }

        if requiresConfirmation(cleaned) && !requestsNovelImport(cleaned) {
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

    static func sourceURL(in text: String) -> String? {
        guard let range = text.range(of: #"https://[^\s<>"，。！？]+"#, options: .regularExpression) else { return nil }
        return String(text[range]).trimmingCharacters(in: CharacterSet(charactersIn: "),;。"))
    }
}

struct WebResearchSource: Codable, Equatable, Sendable {
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
                let safeTitle = source.title
                    .replacingOccurrences(of: "[", with: "（")
                    .replacingOccurrences(of: "]", with: "）")
                    .replacingOccurrences(of: "(", with: "（")
                    .replacingOccurrences(of: ")", with: "）")
                return "• [\(safeTitle)](\(source.url.absoluteString))"
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
            self.session = URLSession(configuration: configuration, delegate: AIServiceRedirectGuard(), delegateQueue: nil)
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

    static func makeRequest(query: String, apiKey: String, configuredModels: AIServiceModels? = nil) throws -> URLRequest {
        let endpoint = try AIServiceEndpoint.current()
        let models = try configuredModels?.validated() ?? AIServiceModels.load(for: endpoint)
        var request = URLRequest(url: endpoint.url("responses"))
        request.httpMethod = "POST"
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "model": models.research,
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
