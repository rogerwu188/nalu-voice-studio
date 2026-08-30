import SwiftUI

struct ContinuityEvidenceView: View {
    let evidence: [ContinuityExtractionEvidence]

    @ViewBuilder var body: some View {
        if !evidence.isEmpty {
            DisclosureGroup("查看 Nalu 依据的剧本原文（\(evidence.count) 条）") {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(evidence) { item in
                        evidenceCard(item)
                    }
                    Label(
                        "这些只是整理依据；必须由您听完并确认，才会交给下一集。",
                        systemImage: "person.crop.circle.badge.checkmark"
                    )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }
                .padding(.top, 8)
            }
            .accessibilityHint("展开查看每项结尾状态对应的定稿剧本原文")
        }
    }

    private func evidenceCard(_ item: ContinuityExtractionEvidence) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(item.excerpt)
                .font(.body)
                .textSelection(.enabled)
            Text(
                item.confidence == "high"
                    ? "原文有明确表述"
                    : "可能是未解悬念，请重点核对"
            )
            .font(.caption)
            .foregroundStyle(item.confidence == "high" ? .secondary : .orange)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            Color.secondary.opacity(0.06),
            in: RoundedRectangle(cornerRadius: 10)
        )
    }
}
