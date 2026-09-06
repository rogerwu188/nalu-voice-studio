import Foundation
import Testing
@testable import NaluVoiceStudio

private final class ReviewRecoveryProtocol: URLProtocol, @unchecked Sendable {
    static var reads = 0
    static var writes = 0
    static var recoveredSeason = "season"
    static var existingInitially = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        if request.httpMethod == "POST" {
            Self.writes += 1
            client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost))
            return
        }
        Self.reads += 1
        let episode = """
        [{"id":"saved","season_id":"\(Self.recoveredSeason)","title":"Original title",
        "episode_number":1,"logline":"Original plan","outline":{},"target_seconds":60,"status":"planned"}]
        """
        let body = Self.existingInitially || Self.reads > 1 ? episode : "[]"
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200,
            httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized)
struct ReviewEpisodeRecoveryTests {
    private func client(existing: Bool = false, season: String = "season") -> RuntimeClient {
        ReviewRecoveryProtocol.reads = 0
        ReviewRecoveryProtocol.writes = 0
        ReviewRecoveryProtocol.existingInitially = existing
        ReviewRecoveryProtocol.recoveredSeason = season
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ReviewRecoveryProtocol.self]
        return RuntimeClient(baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: config), accessCheck: { true })
    }

    private let draft = EpisodeDraft(title: "New title", episodeNumber: 1,
                                    logline: "New plan", targetSeconds: 60)

    @Test func lostCreateResponseIsReconciledWithoutSecondWrite() async throws {
        let episode = try await client().resolveReviewEpisode(seasonID: "season", draft: draft)
        #expect(episode.id == "saved")
        #expect(episode.title == "Original title")
        #expect(ReviewRecoveryProtocol.writes == 1)
        #expect(ReviewRecoveryProtocol.reads == 2)
    }

    @Test func existingEpisodeDoesNotOverwritePlan() async throws {
        let episode = try await client(existing: true).resolveReviewEpisode(seasonID: "season", draft: draft)
        #expect(episode.logline == "Original plan")
        #expect(ReviewRecoveryProtocol.writes == 0)
    }

    @Test func anotherSeasonCannotSatisfyRecovery() async {
        do {
            _ = try await client(season: "other").resolveReviewEpisode(seasonID: "season", draft: draft)
            Issue.record("Cross-season recovery must fail")
        } catch {
            #expect(ReviewRecoveryProtocol.writes == 1)
        }
    }
}
