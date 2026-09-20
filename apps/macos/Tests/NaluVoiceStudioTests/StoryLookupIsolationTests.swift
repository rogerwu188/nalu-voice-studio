import Foundation
import XCTest
@testable import NaluVoiceStudio

private final class HeldStoryLookupProtocol: URLProtocol, @unchecked Sendable {
    static let lock = NSLock()
    static var held: HeldStoryLookupProtocol?
    static var readStarted: XCTestExpectation?
    static var unexpectedRequest: XCTestExpectation?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lock.lock(); defer { Self.lock.unlock() }
        if request.httpMethod == "GET", request.url?.path == "/v1/projects/A/interactive-story", Self.held == nil {
            Self.held = self
            Self.readStarted?.fulfill()
        } else {
            Self.unexpectedRequest?.fulfill()
            client?.urlProtocol(self, didFailWithError: URLError(.cancelled))
        }
    }
    static func finish(success: Bool) {
        lock.lock(); let pending = held; lock.unlock()
        guard let pending else { return }
        if success {
            pending.client?.urlProtocol(pending, didReceive: HTTPURLResponse(url: pending.request.url!,
                statusCode: 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
            pending.client?.urlProtocol(pending, didLoad: Data(#"{"revision":0,"turns":[],"summary":"","episode_drafts":[]}"#.utf8))
            pending.client?.urlProtocolDidFinishLoading(pending)
        } else {
            pending.client?.urlProtocol(pending, didFailWithError: URLError(.cannotConnectToHost))
        }
    }
    override func stopLoading() {}
}

final class StoryLookupIsolationTests: XCTestCase {
    @MainActor func testLateLookupDoesNotWriteOrClearNewProjectActivity() async throws {
        try await checkLateRead(command: "上网搜索一本海边故事的小说")
    }

    @MainActor func testLateDraftAdoptionDoesNotWriteOrClearNewProjectActivity() async throws {
        try await checkLateRead(command: "采用第一集草稿")
    }

    @MainActor private func checkLateRead(command: String) async throws {
        for success in [true, false] {
            let started = expectation(description: "old project read")
            let unexpected = expectation(description: "no followup request after switching")
            unexpected.isInverted = true
            HeldStoryLookupProtocol.held = nil
            HeldStoryLookupProtocol.readStarted = started
            HeldStoryLookupProtocol.unexpectedRequest = unexpected
            let configuration = URLSessionConfiguration.ephemeral
            configuration.protocolClasses = [HeldStoryLookupProtocol.self]
            let session = URLSession(configuration: configuration)
            let model = VoiceInterviewViewModel(runtime: RuntimeClient(
                baseURL: URL(string: "http://127.0.0.1:8765")!, session: session, accessCheck: { true }))
            model.setLocalVoiceEnabled(false)
            model.selectedProjectID = "A"
            model.transcript = command
            XCTAssertTrue(model.submitTypedTranscript())
            await fulfillment(of: [started], timeout: 10)
            model.selectedProjectID = "B"
            model.assistantActionStatus = "B正在创作"
            let messages = model.messages.map(\.text)
            HeldStoryLookupProtocol.finish(success: success)
            await fulfillment(of: [unexpected], timeout: 1)
            XCTAssertEqual(model.assistantActionStatus, "B正在创作")
            XCTAssertEqual(model.messages.map(\.text), messages)
            session.invalidateAndCancel()
        }
    }
}
