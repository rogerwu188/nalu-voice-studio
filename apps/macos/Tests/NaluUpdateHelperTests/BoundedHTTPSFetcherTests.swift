import Foundation
import Testing
@testable import NaluUpdateHelper

private final class FixtureURLProtocol: URLProtocol, @unchecked Sendable {
    static var body = Data()
    static var headers: [String: String] = [:]

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: Self.headers
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

struct BoundedHTTPSFetcherTests {
    @Test func exactHTTPSWritesOnceAndRejectsUnsafeOrOversizedInputs() throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [FixtureURLProtocol.self]
        let fetcher = BoundedHTTPSFetcher(configuration: configuration)
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("nalu-https-fetcher-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        FixtureURLProtocol.body = Data("fixture".utf8)
        FixtureURLProtocol.headers = ["Content-Length": "7"]
        let destination = root.appendingPathComponent("fixture.bin")
        try fetcher.fetch(
            URL(string: "https://updates.nalu.invalid/v1/manifest.json")!,
            to: destination,
            maximumBytes: 7
        )
        #expect(try Data(contentsOf: destination) == FixtureURLProtocol.body)

        #expect(throws: HTTPSFetchError.invalidURL) {
            try fetcher.fetch(
                URL(string: "http://updates.nalu.invalid/v1/manifest.json")!,
                to: root.appendingPathComponent("http.bin"),
                maximumBytes: 10
            )
        }
        #expect(throws: HTTPSFetchError.destinationExists) {
            try fetcher.fetch(
                URL(string: "https://updates.nalu.invalid/v1/manifest.json")!,
                to: destination,
                maximumBytes: 10
            )
        }

        FixtureURLProtocol.body = Data(repeating: 0x41, count: 20)
        FixtureURLProtocol.headers = ["Content-Length": "20"]
        let oversized = root.appendingPathComponent("oversized.bin")
        #expect(throws: HTTPSFetchError.resourceTooLarge) {
            try fetcher.fetch(
                URL(string: "https://updates.nalu.invalid/v1/package.zip")!,
                to: oversized,
                maximumBytes: 10
            )
        }
        #expect(!FileManager.default.fileExists(atPath: oversized.path))
    }
}
