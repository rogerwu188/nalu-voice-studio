import WebKit
import XCTest
@testable import NaluVoiceStudio

@MainActor
private final class RealtimeHarnessDelegate: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
    let loaded: XCTestExpectation
    init(_ loaded: XCTestExpectation) { self.loaded = loaded }
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { loaded.fulfill() }
    func userContentController(_ userContentController: WKUserContentController,
                               didReceive message: WKScriptMessage) {}
}

final class RealtimeWebKitCancellationTests: XCTestCase {
    @MainActor
    func testStopAndReplacementAtEveryBoundaryInWebKit() async throws {
        for stage in ["microphone", "offer", "local", "fetch", "body"] {
            for replacement in [false, true] {
                let loaded = expectation(description: "Local WebKit page \(stage) \(replacement)")
                let delegate = RealtimeHarnessDelegate(loaded)
                let configuration = WKWebViewConfiguration()
                configuration.websiteDataStore = .nonPersistent()
                configuration.userContentController.add(delegate, name: "naluRealtime")
                configuration.userContentController.addUserScript(WKUserScript(
                    source: Self.mockMediaAndTransport, injectionTime: .atDocumentStart,
                    forMainFrameOnly: true))
                let webView = WKWebView(frame: .zero, configuration: configuration)
                webView.navigationDelegate = delegate
                defer {
                    webView.stopLoading()
                    configuration.userContentController.removeScriptMessageHandler(forName: "naluRealtime")
                }
                // The production page executes unchanged. No broker, real key or native media is used.
                webView.loadHTMLString(RealtimeVoiceCoordinator.webRTCPage, baseURL: nil)
                await fulfillment(of: [loaded], timeout: 10)
                let value = try await webView.callAsyncJavaScript(Self.exercise,
                    arguments: ["stage": stage, "replacement": replacement],
                    in: nil, contentWorld: .page)
                let result = try XCTUnwrap(value as? [String: Any])
                let sentBeforeStop = ["fetch", "body"].contains(stage) ? 1 : 0
                XCTAssertEqual(result["requests"] as? Int, sentBeforeStop + (replacement ? 1 : 0))
                XCTAssertEqual(result["oldClosed"] as? Bool, true)
                XCTAssertEqual(result["oldAnswers"] as? Int, 0)
                XCTAssertEqual(result["oldTrackStops"] as? Int, 1)
                XCTAssertEqual(result["replacementHealthy"] as? Bool, true)
                XCTAssertEqual(result["aborted"] as? Bool, true)
            }
        }
    }

    private static let mockMediaAndTransport = #"""
    window.qa = {peers: [], tracks: [], requests: [], stage: null, paused: false};
    qa.waiting = new Promise(resolve => qa.entered = resolve);
    qa.gate = new Promise(resolve => qa.release = resolve);
    qa.pause = async where => {
      if (where !== qa.stage || qa.paused) return;
      qa.paused = true; qa.entered(); await qa.gate;
    };
    window.RTCPeerConnection = class {
      constructor() { this.closed = false; this.answers = 0; qa.peers.push(this); }
      addTrack() {}
      createDataChannel() { return {addEventListener() {}, close() {}, send() {}}; }
      async createOffer() { await qa.pause('offer'); return {sdp: 'synthetic'}; }
      async setLocalDescription() { await qa.pause('local'); }
      async setRemoteDescription() { this.answers++; }
      close() { this.closed = true; }
    };
    Object.defineProperty(navigator, 'mediaDevices', {value: {getUserMedia: async () => {
      const track = {stops: 0, stop() { this.stops++; }};
      qa.tracks.push(track); await qa.pause('microphone');
      return {getTracks: () => [track]};
    }}});
    window.fetch = async (url, options) => {
      qa.requests.push(options); await qa.pause('fetch');
      return {ok: true, text: async () => { await qa.pause('body'); return 'synthetic'; }};
    };
    """#

    private static let exercise = #"""
    qa.stage = stage;
    const old = naluRealtime.start('synthetic', 'https://synthetic.invalid/v1/realtime/calls');
    let deadline;
    try {
      await Promise.race([qa.waiting, new Promise((_, reject) => {
        deadline = setTimeout(() => reject(new Error('Synthetic stage was not reached')), 3000);
      })]);
    } finally { clearTimeout(deadline); }
    if (replacement) await naluRealtime.start('replacement', 'https://synthetic.invalid/v1/realtime/calls');
    else naluRealtime.stop();
    qa.release(); await old;
    const result = {
      requests: qa.requests.length, oldClosed: qa.peers[0].closed,
      oldAnswers: qa.peers[0].answers, oldTrackStops: qa.tracks[0].stops,
      replacementHealthy: !replacement || (!qa.peers[1].closed && qa.peers[1].answers === 1 && qa.tracks[1].stops === 0),
      aborted: !['fetch', 'body'].includes(stage) || qa.requests[0].signal.aborted
    };
    naluRealtime.stop(); return result;
    """#
}
