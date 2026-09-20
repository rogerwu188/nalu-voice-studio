import Foundation
import CryptoKit
import Testing
@testable import NaluVoiceStudio

private final class SavedNovelReadProtocol: URLProtocol, @unchecked Sendable {
    static var body = "null"
    static var status = 200
    static var requests: [URLRequest] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests.append(request)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: Self.status,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(Self.body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct SavedNovelReadTests {
    @MainActor @Test func savedSourceReadDistinguishesAbsenceFromFailureWithoutImporting() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SavedNovelReadProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
                                    session: session, accessCheck: { true })
        SavedNovelReadProtocol.requests = []
        SavedNovelReadProtocol.status = 200
        SavedNovelReadProtocol.body = "null"
        let missing = try await runtime.savedNovelImport(projectID: "project")
        #expect(missing == nil)
        SavedNovelReadProtocol.body = #"{"status":"complete","source_url":"https://example.com/book","completed_chapters":1,"chapters":[{"url":"https://example.com/1","title":"第一章","status":"complete"}]}"#
        let saved = try await runtime.savedNovelImport(projectID: "project")
        #expect(saved?.completed_chapters == 1)
        #expect(saved?.chapters.first?.title == "第一章")
        for (status, body) in [(503, #"{"detail":"unavailable"}"#), (200, "{broken")] {
            SavedNovelReadProtocol.status = status
            SavedNovelReadProtocol.body = body
            var rejected = false
            do { _ = try await runtime.savedNovelImport(projectID: "project") }
            catch { rejected = true }
            #expect(rejected)
        }
        #expect(SavedNovelReadProtocol.requests.count == 4)
        #expect(SavedNovelReadProtocol.requests.allSatisfy {
            $0.httpMethod == "GET" && $0.url?.path == "/v1/projects/project/novel-import"
        })
    }

    @MainActor @Test func importedChapterReaderFetchesExactChapterAndVerifiesItsIdentity() async throws {
        let text = "第一回正文"
        let digest = SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        let payload: [String: Any] = [
            "chapter_number": 1, "url": "https://example.com/chapter-1", "title": "第一回",
            "status": "complete", "text": text, "sha256": digest,
        ]
        SavedNovelReadProtocol.body = String(decoding: try JSONSerialization.data(withJSONObject: payload), as: UTF8.self)
        SavedNovelReadProtocol.status = 200
        SavedNovelReadProtocol.requests = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SavedNovelReadProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let runtime = RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
                                    session: session, accessCheck: { true })

        let chapter = try await runtime.importedNovelChapter(projectID: "project", chapterNumber: 1)
        try chapter.validate(expectedNumber: 1, expectedURL: "https://example.com/chapter-1",
                             expectedSHA256: digest)
        #expect(chapter.text == text)
        var wrongSourceRejected = false
        do {
            try chapter.validate(expectedNumber: 1, expectedURL: "https://example.com/other",
                                 expectedSHA256: digest)
        }
        catch { wrongSourceRejected = true }
        #expect(wrongSourceRejected)
        var corruptedContentRejected = false
        let corrupted = NovelImportedChapter(chapter_number: 1, url: chapter.url,
            title: chapter.title, status: "complete", text: "被改写的正文", sha256: digest)
        do {
            try corrupted.validate(expectedNumber: 1, expectedURL: chapter.url,
                                   expectedSHA256: digest)
        } catch { corruptedContentRejected = true }
        #expect(corruptedContentRejected)
        #expect(SavedNovelReadProtocol.requests.count == 1)
        #expect(SavedNovelReadProtocol.requests[0].httpMethod == "GET")
        #expect(SavedNovelReadProtocol.requests[0].url?.path == "/v1/projects/project/novel-import/chapters/1")
    }
}
