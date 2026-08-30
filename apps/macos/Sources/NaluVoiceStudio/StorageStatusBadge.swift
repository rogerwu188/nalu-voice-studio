import SwiftUI

struct StorageStatusBadge: View {
    let diagnostics: StorageDiagnostics

    private var color: Color {
        switch diagnostics.status {
        case "critical": .red
        case "warning": .orange
        default: .green
        }
    }

    private var icon: String {
        switch diagnostics.status {
        case "critical": "externaldrive.badge.exclamationmark"
        case "warning": "externaldrive.badge.questionmark"
        default: "externaldrive.fill.badge.checkmark"
        }
    }

    private var title: String {
        switch diagnostics.status {
        case "critical": "本机空间不足"
        case "warning": "本机空间偏少"
        default: "本机空间充足"
        }
    }

    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: icon)
            Text("\(title) · 还可用 \(diagnostics.availableLabel)")
        }
        .font(.callout.bold())
        .foregroundStyle(color)
        .help(diagnostics.explanation)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title)，还可用 \(diagnostics.availableLabel)。\(diagnostics.explanation)")
    }
}
