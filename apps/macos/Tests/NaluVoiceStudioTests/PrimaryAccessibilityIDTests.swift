import XCTest
@testable import NaluVoiceStudio

final class PrimaryAccessibilityIDTests: XCTestCase {
    func testPrimaryConversationControlsHaveStableUniqueIdentifiers() {
        let identifiers = [
            NaluPrimaryAccessibilityID.projectList,
            NaluPrimaryAccessibilityID.createProject,
            NaluPrimaryAccessibilityID.runtimeStatus,
            NaluPrimaryAccessibilityID.realtimeVoice,
            NaluPrimaryAccessibilityID.assetImportToolbar,
            NaluPrimaryAccessibilityID.assetImportCard,
            NaluPrimaryAccessibilityID.voiceActivity,
            NaluPrimaryAccessibilityID.microphoneToggle,
        ]

        XCTAssertEqual(Set(identifiers).count, identifiers.count)
        XCTAssertTrue(identifiers.allSatisfy { $0.hasPrefix("nalu.") })
        XCTAssertTrue(identifiers.allSatisfy { !$0.contains(" ") })
    }
}
