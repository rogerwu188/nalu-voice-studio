import SwiftUI

enum ComfortTextStyle: CaseIterable {
    case title, title2, title3, headline, body, callout, caption

    var baseSize: Double {
        switch self {
        case .title: 28
        case .title2: 22
        case .title3: 15
        case .headline, .body: 13
        case .callout: 12
        case .caption: 10
        }
    }

    func pointSize(level: Int) -> Double {
        // macOS does not resize these semantic fonts in response to Dynamic Type.
        // Explicit point sizes also let layout reflow rather than magnifying pixels.
        let factors = [0.9, 1.0, 1.2, 1.4]
        return baseSize * factors[min(3, max(0, level))]
    }
}

private struct ComfortTextLevelKey: EnvironmentKey {
    static let defaultValue = 1
}

extension EnvironmentValues {
    var naluComfortTextLevel: Int {
        get { self[ComfortTextLevelKey.self] }
        set { self[ComfortTextLevelKey.self] = newValue }
    }
}

private struct ComfortFontModifier: ViewModifier {
    @Environment(\.naluComfortTextLevel) private var level
    let style: ComfortTextStyle
    let weight: Font.Weight?
    let monospacedDigits: Bool

    func body(content: Content) -> some View {
        let font = Font.system(
            size: style.pointSize(level: level),
            weight: weight ?? (style == .headline ? .semibold : .regular)
        )
        content.font(monospacedDigits ? font.monospacedDigit() : font)
    }
}

extension View {
    func naluFont(
        _ style: ComfortTextStyle,
        weight: Font.Weight? = nil,
        monospacedDigits: Bool = false
    ) -> some View {
        modifier(ComfortFontModifier(style: style, weight: weight, monospacedDigits: monospacedDigits))
    }
}
