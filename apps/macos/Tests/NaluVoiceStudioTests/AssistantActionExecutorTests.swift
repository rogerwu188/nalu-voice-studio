import XCTest
@testable import NaluVoiceStudio

final class AssistantActionExecutorTests: XCTestCase {
    func testSourceWritingHandoffRequiresExplicitIntent() {
        XCTAssertTrue(AssistantActionRouter.requestsSourceWriting("找这个网址，把它作为剧本"))
        XCTAssertTrue(AssistantActionRouter.requestsSourceWriting("把我的文章改编成三集短剧"))
        XCTAssertFalse(AssistantActionRouter.requestsSourceWriting("帮我找这个网站"))
        XCTAssertFalse(AssistantActionRouter.requestsSourceWriting("只查一下，先别生成剧本"))
        XCTAssertFalse(AssistantActionRouter.requestsSourceWriting("不要改编成短剧"))
    }

    func testSuppliedSourceURLRoutesToReadingWithoutSearchKeywords() {
        XCTAssertEqual(AssistantActionRouter.sourceURL(in: "用 https://example.com/book，这是资料"), "https://example.com/book")
        XCTAssertEqual(AssistantActionRouter.route("https://example.com/book"), .webResearch(query: "https://example.com/book"))
        XCTAssertNil(AssistantActionRouter.sourceURL(in: "我想讲海边的故事"))
    }

    func testRoutesExplicitOnlineResearchWithoutMutatingInterview() {
        XCTAssertEqual(
            AssistantActionRouter.route("请在网上搜索青山短剧生产线的项目主页"),
            .webResearch(query: "请在网上搜索青山短剧生产线的项目主页")
        )
        XCTAssertEqual(
            AssistantActionRouter.route("打开网站帮我找这本书的介绍"),
            .webResearch(query: "打开网站帮我找这本书的介绍")
        )
        XCTAssertNil(AssistantActionRouter.route("我小时候住在海边"))
    }

    func testExternalWritesAndDownloadsRequireVisibleConfirmation() {
        let requests = [
            "去网上找到这本书并下载下来",
            "搜索以后替我购买",
            "找到网站并登录发布",
            "上网查到以后发送给朋友",
        ]
        for request in requests {
            guard case .requiresConfirmation(let description) = AssistantActionRouter.route(request) else {
                return XCTFail("Expected confirmation boundary for \(request)")
            }
            XCTAssertEqual(description, request)
        }
    }

    func testResponseParserKeepsHTTPSourcesAndDeduplicatesURLs() throws {
        let data = try JSONSerialization.data(withJSONObject: [
            "output": [
                [
                    "type": "web_search_call",
                    "action": ["sources": [
                        ["title": "项目主页", "url": "https://example.com/project"],
                        ["title": "重复来源", "url": "https://example.com/project"],
                        ["title": "不安全来源", "url": "http://example.com/plain"],
                    ]],
                ],
                [
                    "type": "message",
                    "content": [[
                        "type": "output_text",
                        "text": "我找到了项目主页。",
                        "annotations": [[
                            "type": "url_citation",
                            "title": "发布说明",
                            "url": "https://example.com/release",
                        ]],
                    ]],
                ],
            ]
        ])

        let result = try OpenAIWebResearchClient.parseResponse(data)
        XCTAssertEqual(result.answer, "我找到了项目主页。")
        XCTAssertEqual(result.sources.map(\.url.absoluteString), [
            "https://example.com/project", "https://example.com/release",
        ])
        XCTAssertTrue(result.conversationText(resumePrompt: "请继续讲童年").contains("再接着刚才的创作"))
    }

    func testResponseParserFailsClosedWithoutText() throws {
        let data = try JSONSerialization.data(withJSONObject: [
            "output": [["type": "web_search_call", "action": ["sources": []]]]
        ])
        XCTAssertThrowsError(try OpenAIWebResearchClient.parseResponse(data))
    }

    func testRequestContractUsesHostedWebSearchWithoutStorage() async throws {
        let session = makeFixtureSession()
        AssistantActionURLProtocol.responseData = try JSONSerialization.data(withJSONObject: [
            "output": [[
                "type": "message",
                "content": [["type": "output_text", "text": "测试结果", "annotations": []]],
            ]]
        ])
        let client = OpenAIWebResearchClient(session: session, fixedAPIKey: "sk-test")
        _ = try await client.research("测试查询")

        let request = try OpenAIWebResearchClient.makeRequest(
            query: "测试查询", apiKey: "sk-test"
        )
        XCTAssertEqual(request.url, OpenAIWebResearchClient.endpoint)
        XCTAssertEqual(request.httpMethod, "POST")
        let body = try XCTUnwrap(request.httpBody)
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(root["store"] as? Bool, false)
        XCTAssertEqual(root["model"] as? String, OpenAIWebResearchClient.model)
        XCTAssertEqual((root["tools"] as? [[String: String]])?.first?["type"], "web_search")
        XCTAssertEqual(root["include"] as? [String], ["web_search_call.action.sources"])
    }

    private func makeFixtureSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AssistantActionURLProtocol.self]
        return URLSession(configuration: configuration)
    }
}

private final class AssistantActionURLProtocol: URLProtocol, @unchecked Sendable {
    static var responseData = Data()
    static var lastRequest: URLRequest?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lastRequest = request
        client?.urlProtocol(
            self,
            didReceive: HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil
            )!,
            cacheStoragePolicy: .notAllowed
        )
        client?.urlProtocol(self, didLoad: Self.responseData)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
