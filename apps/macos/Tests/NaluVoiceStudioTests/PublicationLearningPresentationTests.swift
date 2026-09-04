import Foundation
import Testing
@testable import NaluVoiceStudio

private final class PublicationLearningURLProtocol: URLProtocol, @unchecked Sendable {
    static var responses: [String: Data] = [:]
    static var requestedPaths: [String] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let path = request.url?.path ?? ""
        Self.requestedPaths.append(path)
        let body = Self.responses[path] ?? Data(#"{"detail":"missing fixture"}"#.utf8)
        let status = Self.responses[path] == nil ? 404 : 200
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: "HTTP/1.1",
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

struct PublicationLearningPresentationTests {
    @Test func nativeClientSendsNoRequestWithoutRuntimeOwnership() async {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PublicationLearningURLProtocol.self]
        let client = RuntimeClient(
            baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: configuration),
            accessCheck: { false }
        )
        PublicationLearningURLProtocol.requestedPaths = []

        do {
            _ = try await client.listProjects()
            Issue.record("An unowned Runtime must not receive even a read request")
        } catch {
            guard case RuntimeError.unmanagedRuntimeAccessDenied = error else {
                return Issue.record("Unexpected denial error: \(error)")
            }
        }

        #expect(PublicationLearningURLProtocol.requestedPaths.isEmpty)
    }

    @Test func decodesVerifiedMetricsAndVersionedStrategy() throws {
        let metrics = try JSONDecoder().decode(
            PublicationMetricsSnapshot.self,
            from: Data(metricsJSON.utf8)
        )
        let strategy = try JSONDecoder().decode(
            DirectorStrategyRevision.self,
            from: Data(strategyJSON.utf8)
        )

        #expect(metrics.readOnlySyncPerformed)
        #expect(!metrics.publicationPerformed)
        #expect(!metrics.productionPerformed)
        #expect(!metrics.externalWritePerformed)
        #expect(strategy.revision == 2)
        #expect(strategy.requiresScriptRevisionAndApproval)
        #expect(!strategy.productionStarted)
    }

    @Test func explainsFeedbackInPlainChineseWithoutOfferingAWrite() throws {
        let presentation = try makePresentation()

        #expect(presentation.platformLabel == "哔哩哔哩")
        #expect(presentation.targetEpisodeLabel == "第 2 集《回家》")
        #expect(presentation.windowLabel.contains("2026 年 9 月 1 日"))
        #expect(presentation.completionLabel == "完播率 52%")
        #expect(presentation.spokenSummary.contains("第一条建议"))
        #expect(presentation.spokenSummary.contains("没有发布"))
        #expect(presentation.spokenSummary.contains("没有开始制作"))
        #expect(presentation.safetyStatement.contains("重新确认"))
        #expect(presentation.isVerifiedReadOnly)
    }

    @Test func exposesStableCoherentVoiceOverContract() throws {
        let presentation = try makePresentation()

        #expect(presentation.metricsAccessibilityLabel.contains("平台，哔哩哔哩"))
        #expect(presentation.metricsAccessibilityLabel.contains("1,234 次观看"))
        #expect(presentation.metricsAccessibilityLabel.contains("完播率 52%"))
        #expect(presentation.observationsAccessibilityLabel.hasPrefix("Nalu 看到的情况"))
        #expect(presentation.directivesAccessibilityLabel.contains("第 2 集《回家》"))
        #expect(presentation.safetyAccessibilityLabel.contains("没有替您发布"))
        #expect(presentation.safetyAccessibilityLabel.contains("重新确认"))
        #expect(Set(PublicationLearningAccessibilityID.all).count == 7)
        #expect(PublicationLearningAccessibilityID.all.allSatisfy {
            $0.hasPrefix("nalu.publication-learning.")
        })
    }

    @Test func rejectsCrossProjectOrWriteCapableLearningRecords() throws {
        let metrics = try JSONDecoder().decode(
            PublicationMetricsSnapshot.self,
            from: Data(metricsJSON.utf8)
        )
        let strategy = try JSONDecoder().decode(
            DirectorStrategyRevision.self,
            from: Data(strategyJSON.utf8)
        )

        #expect(throws: PublicationLearningValidationError.self) {
            try PublicationLearningRecord(
                validating: strategy,
                metrics: metrics,
                projectID: "another_project"
            )
        }

        let unsafe = try JSONDecoder().decode(
            PublicationMetricsSnapshot.self,
            from: Data(metricsJSON.replacingOccurrences(
                of: #""external_write_performed":false"#,
                with: #""external_write_performed":true"#
            ).utf8)
        )
        #expect(throws: PublicationLearningValidationError.self) {
            try PublicationLearningRecord(
                validating: strategy,
                metrics: unsafe,
                projectID: "prj_1"
            )
        }
    }

    @Test func nativeClientLoadsBothReadOnlyEndpointsAndFailsClosed() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PublicationLearningURLProtocol.self]
        let client = RuntimeClient(
            baseURL: URL(string: "http://127.0.0.1:8765")!,
            session: URLSession(configuration: configuration),
            accessCheck: { true }
        )
        let strategyList = "[\(strategyJSON)]"
        PublicationLearningURLProtocol.responses = [
            "/v1/projects/prj_1/director-strategies": Data(strategyList.utf8),
            "/v1/publication-metrics/met_1": Data(metricsJSON.utf8),
        ]
        PublicationLearningURLProtocol.requestedPaths = []

        let records = try await client.publicationLearning(projectID: "prj_1")

        #expect(records.count == 1)
        #expect(records[0].strategy.revision == 2)
        #expect(PublicationLearningURLProtocol.requestedPaths == [
            "/v1/projects/prj_1/director-strategies",
            "/v1/publication-metrics/met_1",
        ])

        let unsafeMetrics = metricsJSON.replacingOccurrences(
            of: #""external_write_performed":false"#,
            with: #""external_write_performed":true"#
        )
        PublicationLearningURLProtocol.responses[
            "/v1/publication-metrics/met_1"
        ] = Data(unsafeMetrics.utf8)

        do {
            _ = try await client.publicationLearning(projectID: "prj_1")
            Issue.record("A write-capable metric response must fail closed")
        } catch {
            #expect(error is PublicationLearningValidationError)
        }

        let mismatchedStrategy = strategyJSON.replacingOccurrences(
            of: String(repeating: "e", count: 64),
            with: String(repeating: "0", count: 64)
        )
        PublicationLearningURLProtocol.responses = [
            "/v1/projects/prj_1/director-strategies": Data("[\(mismatchedStrategy)]".utf8),
            "/v1/publication-metrics/met_1": Data(metricsJSON.utf8),
        ]
        do {
            _ = try await client.publicationLearning(projectID: "prj_1")
            Issue.record("A digest-mismatched strategy must fail closed")
        } catch {
            #expect(error is PublicationLearningValidationError)
        }
    }

    private func makePresentation() throws -> PublicationLearningPresentation {
        let metrics = try JSONDecoder().decode(
            PublicationMetricsSnapshot.self,
            from: Data(metricsJSON.utf8)
        )
        let strategy = try JSONDecoder().decode(
            DirectorStrategyRevision.self,
            from: Data(strategyJSON.utf8)
        )
        return PublicationLearningPresentation(
            record: try PublicationLearningRecord(
                validating: strategy,
                metrics: metrics,
                projectID: "prj_1"
            ),
            targetEpisode: NaluEpisode(
                id: "ep_2",
                title: "回家",
                episodeNumber: 2,
                logline: "回到故乡",
                outline: [:],
                targetSeconds: 180,
                status: "planned"
            )
        )
    }

    private var metricsJSON: String {
        #"{"schema_version":"nalu.publication-metrics/v1","id":"met_1","run_id":"run_1","project_id":"prj_1","episode_id":"ep_1","platform":"bilibili","remote_publication_id":"BV1","publication_record_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","window_start":"2026-09-01T00:00:00+00:00","window_end":"2026-09-08T00:00:00+00:00","views":1234,"unique_viewers":1100,"watch_time_seconds":9000,"average_view_duration_seconds":70.5,"completion_rate":0.52,"likes":80,"comments":30,"shares":20,"followers_gained":12,"verification_evidence_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","read_only_sync_performed":true,"publication_performed":false,"production_performed":false,"external_write_performed":false,"idempotency_key_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","request_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","created_at":"2026-09-08T00:01:00Z","snapshot_sha256":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"}"#
    }

    private var strategyJSON: String {
        #"{"schema_version":"nalu.director-strategy/v1","id":"strategy_2","project_id":"prj_1","target_episode_id":"ep_2","source_metrics_id":"met_1","source_metrics_sha256":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","revision":2,"observations":["本次核验窗口完播率为 52.0%。"],"directives":["下一集前 15 秒更快交代人物目标与核心冲突。"],"immutable_constraints":["不得自动修改已批准剧本"],"requires_script_revision_and_approval":true,"production_started":false,"publication_performed":false,"created_at":"2026-09-08T00:01:00Z","strategy_sha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}"#
    }
}
