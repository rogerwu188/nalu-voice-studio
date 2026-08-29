import SwiftUI

struct RuntimeStatusBadge: View {
    let status: String

    private var state: (color: Color, text: String, symbol: String) {
        if status.contains("已就绪") {
            return (.green, "本地制片厂在线 → 可以创作", "checkmark.circle.fill")
        }
        if status.contains("尚未启动") {
            return (.red, "本地制片厂未连接 ×", "xmark.circle.fill")
        }
        return (.orange, "本地制片厂正在启动 → 请稍等", "arrow.triangle.2.circlepath")
    }

    var body: some View {
        Label(state.text, systemImage: state.symbol)
            .font(.headline)
            .foregroundStyle(state.color)
            .accessibilityLabel("系统状态：\(state.text)")
    }
}

struct VoiceActivityStatus: View {
    let isListening: Bool

    var body: some View {
        HStack(spacing: 14) {
            if isListening {
                TimelineView(.animation(minimumInterval: 0.12)) { timeline in
                    let tick = timeline.date.timeIntervalSinceReferenceDate
                    HStack(alignment: .center, spacing: 4) {
                        Circle()
                            .fill(.red)
                            .frame(width: 14, height: 14)
                            .scaleEffect(0.85 + 0.2 * wave(tick, offset: 0))
                            .opacity(0.65 + 0.35 * wave(tick, offset: 0))
                        ForEach(0..<5, id: \.self) { index in
                            Capsule()
                                .fill(.red)
                                .frame(
                                    width: 5,
                                    height: 12 + 18 * wave(tick, offset: Double(index) * 0.7)
                                )
                        }
                    }
                }
                .frame(width: 72, height: 38)
                VStack(alignment: .leading, spacing: 2) {
                    Text("正在录音 · 我在听")
                        .font(.title3.bold())
                        .foregroundStyle(.red)
                    Text("请继续说；说完后再按一下红色按钮")
                        .foregroundStyle(.secondary)
                }
            } else {
                Image(systemName: "arrow.down.circle.fill")
                    .font(.title)
                    .foregroundStyle(.blue)
                VStack(alignment: .leading, spacing: 2) {
                    Text("准备好了 → 按下面的蓝色按钮")
                        .font(.title3.bold())
                    Text("按钮变红并开始跳动，就代表 Nalu 正在听")
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
        }
        .padding(.horizontal, 24)
        .padding(.top, 12)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            isListening ? "正在录音，Nalu 正在听" : "尚未录音，请按蓝色按钮开始"
        )
    }

    private func wave(_ tick: TimeInterval, offset: Double) -> Double {
        (sin(tick * 6 + offset) + 1) / 2
    }
}
