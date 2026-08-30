import SwiftUI

enum ProductionProgressAttention: Equatable {
    case working
    case needsConfirmation
    case stopped
    case finished
    case waiting
}

struct ProductionProgressPresentation: Equatable {
    let attention: ProductionProgressAttention
    let reassurance: String
    let nextStep: String

    init(progress: EpisodeProductionProgress) {
        if progress.stage == "charge_reconciliation" {
            attention = .needsConfirmation
            reassurance = "正在安全核对，没有重复扣费或重复提交"
            nextStep = "核对清楚前不能取消，也不会自动重试"
        } else if progress.stage == "safe_retry_review" || progress.runStatus == "waiting_for_approval" {
            attention = .needsConfirmation
            reassurance = "Nalu 正在等您确认，没有卡住"
            nextStep = "确认后才会继续可能产生费用的步骤"
        } else if progress.runStatus == "failed" || progress.runStatus == "cancelled" {
            attention = .stopped
            reassurance = progress.runStatus == "cancelled" ? "本集已安全暂停" : "本集已停下，没有偷偷重试"
            nextStep = progress.canResume ? "可以从已保存的位置恢复" : "请先查看失败说明"
        } else if progress.runStatus == "completed" || progress.episodeStatus == "ready_to_publish" || progress.episodeStatus == "published" {
            attention = .finished
            reassurance = "本集制作已经完成"
            nextStep = progress.episodeStatus == "published" ? "成片已经发布" : "请检查成片并决定是否发行"
        } else if let runStatus = progress.runStatus,
                  ["created", "preflight", "queued", "running", "qa_review"].contains(runStatus) {
            attention = .working
            reassurance = "Nalu 正在工作，没有停"
            nextStep = progress.canCancel ? "需要时可以安全暂停" : "正在完成不可中断的安全步骤"
        } else {
            attention = .waiting
            reassurance = "当前进度已经保存"
            nextStep = progress.progressPercent >= 20 ? "准备好后可以进入制作" : "继续完成剧本和素材确认"
        }
    }

    var moves: Bool { attention == .working }
}

struct ProductionProgressStatusView: View {
    let progress: EpisodeProductionProgress
    let lastRefreshedAt: Date?
    let refreshWarning: String?

    private var presentation: ProductionProgressPresentation {
        ProductionProgressPresentation(progress: progress)
    }

    private var accent: Color {
        switch presentation.attention {
        case .working: .blue
        case .needsConfirmation: .orange
        case .stopped: .red
        case .finished: .green
        case .waiting: .secondary
        }
    }

    private var statusIcon: String {
        switch presentation.attention {
        case .working: "arrow.right.circle.fill"
        case .needsConfirmation: "hand.raised.circle.fill"
        case .stopped: "pause.circle.fill"
        case .finished: "checkmark.circle.fill"
        case .waiting: "clock.circle.fill"
        }
    }

    var body: some View {
        TimelineView(.animation(minimumInterval: 0.55, paused: !presentation.moves)) { context in
            let movingRight = Int(context.date.timeIntervalSinceReferenceDate * 2) % 2 == 0
            HStack(alignment: .top, spacing: 16) {
                Image(systemName: statusIcon)
                    .font(.system(size: 34, weight: .bold))
                    .foregroundStyle(accent)
                    .offset(x: presentation.moves && movingRight ? 8 : 0)
                    .animation(.easeInOut(duration: 0.5), value: movingRight)
                    .frame(width: 48, height: 44)

                VStack(alignment: .leading, spacing: 7) {
                    HStack(alignment: .firstTextBaseline) {
                        Text("第 \(progress.episodeNumber) 集 · \(progress.currentAction)")
                            .font(.title3.bold())
                        Spacer()
                        Text("\(progress.progressPercent)%")
                            .font(.title2.bold().monospacedDigit())
                            .foregroundStyle(accent)
                    }
                    ProgressView(value: Double(progress.progressPercent), total: 100)
                        .tint(accent)
                    Text(presentation.reassurance)
                        .font(.headline)
                        .foregroundStyle(accent)
                    Text(progress.explanation)
                        .foregroundStyle(.primary)
                    Label(presentation.nextStep, systemImage: "arrow.turn.down.right")
                        .foregroundStyle(.secondary)
                    if let refreshWarning {
                        Label(refreshWarning, systemImage: "wifi.exclamationmark")
                            .foregroundStyle(.orange)
                    } else if let lastRefreshedAt {
                        Text("刚刚自动核对 · \(lastRefreshedAt.formatted(date: .omitted, time: .standard))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
            .background(accent.opacity(0.09), in: RoundedRectangle(cornerRadius: 16))
            .overlay {
                RoundedRectangle(cornerRadius: 16)
                    .stroke(accent.opacity(0.30), lineWidth: 1)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(
                "第 \(progress.episodeNumber) 集，\(progress.currentAction)，进度百分之 \(progress.progressPercent)。\(presentation.reassurance)。\(progress.explanation)。\(presentation.nextStep)"
            )
        }
    }
}
