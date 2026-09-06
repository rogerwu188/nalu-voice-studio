import XCTest
@testable import NaluVoiceStudio

final class CredentialDraftSaveTests: XCTestCase {
    func testOpenAIOnlyDoesNotRequireVideoProviderKeys() {
        var saved: [ProviderCredential] = []
        XCTAssertTrue(CredentialDraftSave.save([
            (.seedance, ""), (.minimax, "  "), (.openAIRealtime, " synthetic "),
        ]) { credential, secret in
            saved.append(credential)
            XCTAssertEqual(secret, "synthetic")
            return true
        })
        XCTAssertEqual(saved, [.openAIRealtime])
    }

    func testFailurePreventsClosingAndStopsFurtherWrites() {
        var attempts = 0
        XCTAssertFalse(CredentialDraftSave.save([
            (.openAIRealtime, "synthetic"), (.seedance, "synthetic"),
        ]) { _, _ in
            attempts += 1
            return false
        })
        XCTAssertEqual(attempts, 1)
    }

    func testAllBlankLeavesExistingCredentialsUntouched() {
        XCTAssertTrue(CredentialDraftSave.save([(.openAIRealtime, "\n ")]) { _, _ in
            XCTFail("An empty draft must never overwrite or delete an existing key")
            return false
        })
    }
}
