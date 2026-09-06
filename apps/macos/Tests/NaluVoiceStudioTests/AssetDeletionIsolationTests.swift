import Foundation
import XCTest
@testable import NaluVoiceStudio

private final class AssetIsolationProtocol: URLProtocol, @unchecked Sendable {
    static var hook: (@Sendable (URLRequest) async -> Void)?
    static var failDelete = false
    static var paths: [String] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Task {
            Self.paths.append(request.url!.path)
            await Self.hook?(request)
            let deleting = request.httpMethod == "DELETE"
            let status = deleting ? (Self.failDelete ? 500 : 204) : 200
            let bytes = Data((status == 500 ? "{}" : deleting ? "" : "[]").utf8)
            let response = HTTPURLResponse(url: request.url!, statusCode: status,
                httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: bytes)
            client?.urlProtocolDidFinishLoading(self)
        }
    }
    override func stopLoading() {}
}

@MainActor
final class AssetDeletionIsolationTests: XCTestCase {
    private func asset(_ id: String, project: String) -> NaluAsset {
        NaluAsset(id: id, projectID: project, seasonID: nil, episodeID: nil,
            kind: "source_document", name: id, localURI: "file:///synthetic",
            subjectName: "", metadata: [:], consentGranted: false,
            consentScope: "project_only", guardianApproved: false, createdAt: "test")
    }

    private func model() -> VoiceInterviewViewModel {
        AssetIsolationProtocol.hook = nil
        AssetIsolationProtocol.failDelete = false
        AssetIsolationProtocol.paths = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AssetIsolationProtocol.self]
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:18700")!,
            session: URLSession(configuration: configuration), accessCheck: { true })
        let model = VoiceInterviewViewModel(runtime: runtime)
        model.selectedProjectID = "A"
        model.assets = [asset("old", project: "A")]
        return model
    }

    func testSwitchAtEveryResponseBoundaryDoesNotOverwriteNewSelection() async {
        for path in ["/v1/assets/old", "/v1/projects/A/assets", "/v1/projects/A/memory-cards"] {
            let model = model()
            let sentinel = asset("new", project: "B")
            let count = model.messages.count
            AssetIsolationProtocol.hook = { request in
                guard request.url?.path == path else { return }
                await MainActor.run {
                    model.selectedProjectID = "B"
                    model.assets = [sentinel]
                }
            }
            await model.deleteAsset("old")
            XCTAssertEqual(model.selectedProjectID, "B", path)
            XCTAssertEqual(model.assets.map(\.id), ["new"], path)
            XCTAssertEqual(model.messages.count, count, path)
        }
    }

    func testSwitchAwayAndBackSuppressesOldError() async {
        let model = model()
        AssetIsolationProtocol.failDelete = true
        AssetIsolationProtocol.hook = { _ in
            await MainActor.run {
                model.selectedProjectID = "B"
                model.selectedProjectID = "A"
                model.errorMessage = "current selection message"
            }
        }
        await model.deleteAsset("old")
        XCTAssertEqual(model.errorMessage, "current selection message")
    }

    func testForeignAssetMakesNoRequest() async {
        let model = model()
        model.selectedProjectID = "B"
        await model.deleteAsset("old")
        XCTAssertTrue(AssetIsolationProtocol.paths.isEmpty)
    }

    func testUnchangedSelectionStillRefreshesAndReportsSuccess() async {
        let model = model()
        await model.deleteAsset("old")
        XCTAssertTrue(model.assets.isEmpty)
        XCTAssertEqual(model.messages.last?.text, "本地素材和素材记录已经删除。")
    }
}
