import SwiftUI

struct PublicationMetricsSnapshot: Codable, Sendable {
    let schemaVersion: String
    let id: String
    let runID: String
    let projectID: String
    let episodeID: String
    let platform: String
    let remotePublicationID: String
    let publicationRecordSHA256: String
    let windowStart: String
    let windowEnd: String
    let views: Int
    let uniqueViewers: Int
    let watchTimeSeconds: Int
    let averageViewDurationSeconds: Double
    let completionRate: Double
    let likes: Int
    let comments: Int
    let shares: Int
    let followersGained: Int
    let verificationEvidenceSHA256: String
    let readOnlySyncPerformed: Bool
    let publicationPerformed: Bool
    let productionPerformed: Bool
    let externalWritePerformed: Bool
    let idempotencyKeySHA256: String
    let requestSHA256: String
    let createdAt: String
    let snapshotSHA256: String

    enum CodingKeys: String, CodingKey {
        case id, platform, views, likes, comments, shares
        case schemaVersion = "schema_version"
        case runID = "run_id"
        case projectID = "project_id"
        case episodeID = "episode_id"
        case remotePublicationID = "remote_publication_id"
        case publicationRecordSHA256 = "publication_record_sha256"
        case windowStart = "window_start"
        case windowEnd = "window_end"
        case uniqueViewers = "unique_viewers"
        case watchTimeSeconds = "watch_time_seconds"
        case averageViewDurationSeconds = "average_view_duration_seconds"
        case completionRate = "completion_rate"
        case followersGained = "followers_gained"
        case verificationEvidenceSHA256 = "verification_evidence_sha256"
        case readOnlySyncPerformed = "read_only_sync_performed"
        case publicationPerformed = "publication_performed"
        case productionPerformed = "production_performed"
        case externalWritePerformed = "external_write_performed"
        case idempotencyKeySHA256 = "idempotency_key_sha256"
        case requestSHA256 = "request_sha256"
        case createdAt = "created_at"
        case snapshotSHA256 = "snapshot_sha256"
    }
}

struct DirectorStrategyRevision: Codable, Identifiable, Sendable {
    let schemaVersion: String
    let id: String
    let projectID: String
    let targetEpisodeID: String
    let sourceMetricsID: String
    let sourceMetricsSHA256: String
    let revision: Int
    let observations: [String]
    let directives: [String]
    let immutableConstraints: [String]
    let requiresScriptRevisionAndApproval: Bool
    let productionStarted: Bool
    let publicationPerformed: Bool
    let createdAt: String
    let strategySHA256: String

    enum CodingKeys: String, CodingKey {
        case id, revision, observations, directives
        case schemaVersion = "schema_version"
        case projectID = "project_id"
        case targetEpisodeID = "target_episode_id"
        case sourceMetricsID = "source_metrics_id"
        case sourceMetricsSHA256 = "source_metrics_sha256"
        case immutableConstraints = "immutable_constraints"
        case requiresScriptRevisionAndApproval = "requires_script_revision_and_approval"
        case productionStarted = "production_started"
        case publicationPerformed = "publication_performed"
        case createdAt = "created_at"
        case strategySHA256 = "strategy_sha256"
    }
}

struct PublicationLearningRecord: Sendable {
    let strategy: DirectorStrategyRevision
    let metrics: PublicationMetricsSnapshot

    init(
        validating strategy: DirectorStrategyRevision,
        metrics: PublicationMetricsSnapshot,
        projectID: String
    ) throws {
        guard strategy.projectID == projectID,
              metrics.projectID == projectID,
              metrics.id == strategy.sourceMetricsID,
              metrics.snapshotSHA256 == strategy.sourceMetricsSHA256,
              metrics.readOnlySyncPerformed,
              !metrics.publicationPerformed,
              !metrics.productionPerformed,
              !metrics.externalWritePerformed,
              strategy.requiresScriptRevisionAndApproval,
              !strategy.productionStarted,
              !strategy.publicationPerformed else {
            throw PublicationLearningValidationError.unsafeOrMismatchedRecord
        }
        self.strategy = strategy
        self.metrics = metrics
    }
}

enum PublicationLearningValidationError: LocalizedError {
    case unsafeOrMismatchedRecord

    var errorDescription: String? {
        "播出反馈的只读安全记录不一致，Nalu 已停止展示"
    }
}

struct PublicationLearningPresentation: Identifiable, Equatable, Sendable {
    let id: String
    let revision: Int
    let platformLabel: String
    let targetEpisodeLabel: String
    let windowLabel: String
    let viewsLabel: String
    let completionLabel: String
    let observations: [String]
    let directives: [String]
    let safetyStatement: String
    let spokenSummary: String

    init(record: PublicationLearningRecord, targetEpisode: NaluEpisode?) {
        let strategy = record.strategy
        let metrics = record.metrics
        id = strategy.id
        revision = strategy.revision
        platformLabel = Self.platformName(metrics.platform)
        if let targetEpisode {
            targetEpisodeLabel = "第 \(targetEpisode.episodeNumber) 集《\(targetEpisode.title)》"
        } else {
            targetEpisodeLabel = "下一集"
        }
        windowLabel = "\(Self.day(metrics.windowStart)) 至 \(Self.day(metrics.windowEnd))"
        viewsLabel = "\(metrics.views.formatted()) 次观看"
        completionLabel = "完播率 \(Int((metrics.completionRate * 100).rounded()))%"
        observations = strategy.observations
        directives = strategy.directives
        safetyStatement = "这些是只读建议。Nalu 没有替您发布、花费额度或开始制作；采纳建议前必须建立新剧本版本，并由您重新确认。"
        let advice = strategy.directives.first ?? "保持当前创作方向。"
        spokenSummary = [
            "这是第 \(strategy.revision) 版发行反馈。",
            "\(Self.platformName(metrics.platform)) 的发行身份已经核验。",
            "统计期间是 \(Self.day(metrics.windowStart)) 至 \(Self.day(metrics.windowEnd))，共有 \(metrics.views) 次观看，完播率是 \(Int((metrics.completionRate * 100).rounded()))%。",
            "给\(targetEpisodeLabel)的第一条建议是：\(advice)",
            "这次只读取了结果，没有发布，也没有开始制作。采纳建议前，仍要建立新的剧本版本并由您确认。",
        ].joined(separator: " ")
    }

    var isVerifiedReadOnly: Bool {
        safetyStatement.contains("只读")
    }

    private static func platformName(_ platform: String) -> String {
        switch platform {
        case "youtube": "YouTube"
        case "bilibili": "哔哩哔哩"
        default: platform
        }
    }

    private static func day(_ timestamp: String) -> String {
        let raw = String(timestamp.prefix(10))
        let parts = raw.split(separator: "-")
        guard parts.count == 3 else { return raw }
        return "\(parts[0]) 年 \(Int(parts[1]) ?? 0) 月 \(Int(parts[2]) ?? 0) 日"
    }
}

struct PublicationLearningView: View {
    let items: [PublicationLearningPresentation]
    let isLoading: Bool
    let warning: String?
    let onReadLatest: () -> Void
    let onRefresh: () -> Void

    private var latest: PublicationLearningPresentation? { items.last }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: latest == nil ? "chart.line.uptrend.xyaxis" : "checkmark.seal.fill")
                    .font(.title)
                    .foregroundStyle(latest == nil ? .secondary : .green)
                    .frame(width: 36)
                VStack(alignment: .leading, spacing: 4) {
                    Text("播出反馈与下一集建议")
                        .font(.title2.bold())
                    Text(latest == nil ? "还没有经过核验的播出反馈" : "发行身份已核验 · 只读")
                        .font(.headline)
                        .foregroundStyle(latest == nil ? .secondary : .green)
                }
                Spacer()
                if isLoading {
                    ProgressView().accessibilityLabel("正在读取播出反馈")
                } else {
                    Button("刷新", systemImage: "arrow.clockwise", action: onRefresh)
                        .controlSize(.large)
                }
            }

            if let latest {
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 150), spacing: 10)],
                    alignment: .leading,
                    spacing: 10
                ) {
                    metric(latest.platformLabel, icon: "play.rectangle.fill")
                    metric(latest.viewsLabel, icon: "eye.fill")
                    metric(latest.completionLabel, icon: "chart.bar.fill")
                    metric("建议第 \(latest.revision) 版", icon: "clock.arrow.circlepath")
                }
                .accessibilityElement(children: .combine)

                Text(latest.windowLabel)
                    .font(.callout)
                    .foregroundStyle(.secondary)

                if !latest.observations.isEmpty {
                    VStack(alignment: .leading, spacing: 7) {
                        Text("Nalu 看到了什么")
                            .font(.headline)
                        ForEach(latest.observations.prefix(2), id: \.self) { observation in
                            Label(observation, systemImage: "eye")
                                .font(.body)
                        }
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("给 \(latest.targetEpisodeLabel)")
                        .font(.headline)
                    ForEach(latest.directives.prefix(3), id: \.self) { directive in
                        Label(directive, systemImage: "arrow.turn.down.right")
                            .font(.body)
                    }
                }

                Button("朗读本次反馈", systemImage: "speaker.wave.2.fill", action: onReadLatest)
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .accessibilityHint("朗读播出数据、下一集建议和安全说明")

                Label(latest.safetyStatement, systemImage: "lock.shield.fill")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else if !isLoading {
                Text("成片经过受控发行并取得只读核验结果后，Nalu 会自动整理这里；您不需要填写专业表格。")
                    .font(.body)
                    .foregroundStyle(.secondary)
            }

            if let warning {
                Label(warning, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
            }
        }
        .padding(18)
        .background(Color.green.opacity(latest == nil ? 0.035 : 0.07), in: RoundedRectangle(cornerRadius: 14))
        .accessibilityElement(children: .contain)
    }

    private func metric(_ text: String, icon: String) -> some View {
        Label(text, systemImage: icon)
            .font(.headline)
            .padding(.horizontal, 11)
            .padding(.vertical, 8)
            .background(.background.opacity(0.8), in: Capsule())
    }
}
