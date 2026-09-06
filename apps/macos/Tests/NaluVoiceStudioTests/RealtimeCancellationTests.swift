import Foundation
import WebKit
import XCTest
@testable import NaluVoiceStudio

private actor DelayedRealtimeCredential {
    private var released = false
    private var waiter: CheckedContinuation<String?, Never>?
    func read() async -> String? {
        if released { return "synthetic-test-key" }
        return await withCheckedContinuation { waiter = $0 }
    }
    func release() {
        released = true
        waiter?.resume(returning: "synthetic-test-key")
        waiter = nil
    }
}

private final class RealtimeNoNetworkProtocol: URLProtocol, @unchecked Sendable {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        XCTFail("Cancelled attempt must not reach the HTTP transport")
        client?.urlProtocol(self, didFailWithError: URLError(.cancelled))
    }
    override func stopLoading() {}
}

final class RealtimeCancellationTests: XCTestCase {
    private func broker(_ gate: DelayedRealtimeCredential,
                        started: XCTestExpectation) -> RealtimeSessionBroker {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RealtimeNoNetworkProtocol.self]
        return RealtimeSessionBroker(session: URLSession(configuration: configuration)) {
            started.fulfill()
            return await gate.read() // Deliberately ignores cancellation, like a system call.
        }
    }

    func testCancelledBrokerDoesNotPostAfterLateCredentialReturns() async throws {
        let gate = DelayedRealtimeCredential()
        let started = expectation(description: "Credential read started")
        let broker = broker(gate, started: started)
        let endpoint = try AIServiceEndpoint("https://synthetic.invalid/v1")
        let task = Task {
            try await broker.createClientSecret(instructions: "synthetic", endpoint: endpoint)
        }
        await fulfillment(of: [started], timeout: 2)
        task.cancel()
        await gate.release()
        do {
            _ = try await task.value
            XCTFail("Expected cancellation")
        } catch is CancellationError {} catch { XCTFail("Unexpected cancellation result") }
    }

    @MainActor
    func testStopOwnsCancellationAndLateCredentialCannotReactivateVoice() async {
        let gate = DelayedRealtimeCredential()
        let started = expectation(description: "Coordinator credential read started")
        let coordinator = RealtimeVoiceCoordinator(broker: broker(gate, started: started))
        let webView = WKWebView(frame: .zero)
        coordinator.attach(webView)
        let task = Task { await coordinator.start(instructions: "synthetic") }
        await fulfillment(of: [started], timeout: 3)
        coordinator.stop()
        await gate.release()
        await task.value
        XCTAssertEqual(coordinator.state, .off)
        XCTAssertFalse(coordinator.retryAllowed)
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "naluRealtime")
    }
}
