import Foundation
import Testing
@testable import NaluVoiceStudio

struct PublicationLearningPresentationTests {
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
