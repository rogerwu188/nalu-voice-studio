import Foundation
import Testing
@testable import NaluVoiceStudio

private final class DelayedInterviewProtocol: URLProtocol, @unchecked Sendable {
    static let lock = NSLock()
    static var pending: DelayedInterviewProtocol?
    static func isPending() -> Bool {
        lock.lock(); defer { lock.unlock() }
        return pending != nil
    }
    static func finishPending(success: Bool) {
        lock.lock()
        let held = pending
        pending = nil
        lock.unlock()
        guard let held else { return }
        if success {
            let body = """
            {"project":{"id":"A","title":"A","description":"",
            "audience_mode":"general","planned_episode_count":1,
            "creative_format":"short_drama_series","production_pipeline":"qingshan"},
            "season":{"id":"season-A","project_id":"A","title":"第一季",
            "season_number":1,"planned_episode_count":1,"season_arc":{},"plan_revision":1},
            "episodes":[]}
            """
            held.client?.urlProtocol(held, didReceive: HTTPURLResponse(url: held.request.url!,
                statusCode: 201, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
            held.client?.urlProtocol(held, didLoad: Data(body.utf8))
            held.client?.urlProtocolDidFinishLoading(held)
            return
        }
        held.client?.urlProtocol(held, didFailWithError: URLError(.cannotConnectToHost))
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lock.lock(); defer { Self.lock.unlock() }
        Self.pending = self
    }
    override func stopLoading() {}
}

@Suite(.serialized)
struct InterviewCompletionIsolationTests {
    @MainActor @Test(arguments: [false, true])
    func lateCompletionDoesNotChangeNewProject(success: Bool) async throws {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForResource = 5
        config.protocolClasses = [DelayedInterviewProtocol.self]
        let model = VoiceInterviewViewModel(runtime: RuntimeClient(
            baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true }))
        model.setLocalVoiceEnabled(false)
        model.selectedProjectID = "A"
        model.draftProjectID = "A"
        let saving = Task { await model.createInterviewedProject(ProjectDraft()) }
        for _ in 0..<100 where !DelayedInterviewProtocol.isPending() {
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(DelayedInterviewProtocol.isPending())
        model.selectedProjectID = "B"
        model.draftProjectID = "B"
        model.transcript = "B的故事"
        model.errorMessage = "B原有提示"
        let messages = model.messages.map(\.text)
        DelayedInterviewProtocol.finishPending(success: success)
        await saving.value
        #expect(model.selectedProjectID == "B")
        #expect(model.draftProjectID == "B")
        #expect(model.transcript == "B的故事")
        #expect(model.errorMessage == "B原有提示")
        #expect(model.messages.map(\.text) == messages)
        model.selectedProjectID = "A"
        #expect(model.draftProjectID == (success ? nil : "A"))
    }
}
