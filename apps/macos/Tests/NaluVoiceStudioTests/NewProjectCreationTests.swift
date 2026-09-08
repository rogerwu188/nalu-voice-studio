import Foundation
import Testing
@testable import NaluVoiceStudio

private final class NewProjectProtocol: URLProtocol, @unchecked Sendable {
    static var creations = 0
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        var body = "[]"
        if request.httpMethod == "POST" {
            Self.creations += 1
            body = """
            {"id":"project-\(Self.creations)","title":"未命名故事","description":"",
            "audience_mode":"general","planned_episode_count":6,
            "creative_format":"short_drama_series","production_pipeline":"qingshan"}
            """
        }
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!,
            statusCode: 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized)
struct NewProjectCreationTests {
    @MainActor @Test func explicitNewProjectDoesNotReuseExistingDraft() async {
        NewProjectProtocol.creations = 0
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [NewProjectProtocol.self]
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true })
        let model = VoiceInterviewViewModel(runtime: runtime)
        model.setLocalVoiceEnabled(false)
        await model.beginProject()
        model.transcript = "第一部故事未发送"
        await model.beginProject()
        #expect(NewProjectProtocol.creations == 2)
        #expect(Set(model.projects.map(\.id)).count == 2)
        #expect(model.selectedProjectID == "project-2")
        #expect(model.transcript.isEmpty)
        await model.selectProject("project-1")
        #expect(model.transcript == "第一部故事未发送")
        #expect(!model.projectCreationInProgress)
    }

    @MainActor @Test func overlappingClicksCreateOnlyOneProject() async {
        NewProjectProtocol.creations = 0
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [NewProjectProtocol.self]
        let model = VoiceInterviewViewModel(runtime: RuntimeClient(
            baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true }))
        model.setLocalVoiceEnabled(false)
        async let first: Void = model.beginProject()
        async let second: Void = model.beginProject()
        _ = await (first, second)
        #expect(NewProjectProtocol.creations == 1)
        #expect(model.projects.count == 1)
    }
}
