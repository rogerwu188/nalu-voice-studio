import XCTest
@testable import NaluVoiceStudio

final class VoiceInteractionModeTests: XCTestCase {
    func testDefaultUsesRequestedLocalDictationAndTTSBaseline() {
        XCTAssertEqual(VoiceInteractionMode.defaultMode, .localDictation)
        XCTAssertTrue(VoiceInteractionMode.defaultMode.allowsLocalSpeech(realtimeActive: false))
    }

    func testGPTNeverEnablesSystemSpeechIncludingDisconnectedState() {
        XCTAssertFalse(VoiceInteractionMode.gptRealtime.allowsLocalSpeech(realtimeActive: false))
        XCTAssertFalse(VoiceInteractionMode.gptRealtime.allowsLocalSpeech(realtimeActive: true))
    }

    func testLocalSpeechRequiresExplicitModeAndNoRealtimeSession() {
        XCTAssertTrue(VoiceInteractionMode.localDictation.allowsLocalSpeech(realtimeActive: false))
        XCTAssertFalse(VoiceInteractionMode.localDictation.allowsLocalSpeech(realtimeActive: true))
    }

    @MainActor
    func testSuppressedSystemSpeechDoesNotClaimCompletedReadback() {
        let playback = SpeechPlayback()
        var result: Bool?
        playback.speak("Synthetic readback") { result = $0 }
        XCTAssertEqual(result, false)
    }
}
