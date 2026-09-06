import Foundation

enum VoiceInteractionMode: String, CaseIterable, Identifiable {
    case gptRealtime
    case localDictation

    var id: String { rawValue }
    var label: String {
        switch self {
        case .gptRealtime: "GPT 实时语音"
        case .localDictation: "本机听写与朗读"
        }
    }

    func allowsLocalSpeech(realtimeActive: Bool) -> Bool {
        self == .localDictation && !realtimeActive
    }
}
