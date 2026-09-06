import XCTest
import Security
@testable import NaluVoiceStudio

final class CredentialPresenceTests: XCTestCase {
    func testReadOnlyDiagnosticFailsInsteadOfWaitingForAuthorization() {
        let query = KeychainSecretStore().readQuery(.openAIRealtime, allowAuthenticationUI: false)
        XCTAssertEqual(query[kSecUseAuthenticationUI as String] as? String, kSecUseAuthenticationUIFail as String)
        XCTAssertEqual(query[kSecReturnData as String] as? Bool, true)
        XCTAssertEqual(query[kSecAttrAccount as String] as? String, ProviderCredential.openAIRealtime.rawValue)
    }

    func testExplicitSecretOperationsRetainSystemAuthorization() {
        let query = KeychainSecretStore().readQuery(.openAIRealtime, allowAuthenticationUI: true)
        XCTAssertNil(query[kSecUseAuthenticationUI as String])
        XCTAssertEqual(query[kSecReturnData as String] as? Bool, true)
    }

    func testPresenceNeverRequestsPasswordOrInteractiveAuthorization() throws {
        for credential in ProviderCredential.allCases {
            let present = try KeychainSecretStore().contains(credential) { raw in
                let query = raw as NSDictionary
                XCTAssertNil(query[kSecReturnData])
                XCTAssertNil(query[kSecValueData])
                XCTAssertEqual(query[kSecReturnAttributes] as? Bool, true)
                XCTAssertEqual(query[kSecUseAuthenticationUI] as? String, kSecUseAuthenticationUIFail as String)
                XCTAssertEqual(query[kSecAttrAccount] as? String, credential.rawValue)
                XCTAssertEqual(query[kSecAttrService] as? String, "studio.nalu.voice.provider-credentials")
                return errSecSuccess
            }
            XCTAssertTrue(present)
        }
    }

    func testMissingIsNotConfigured() throws {
        XCTAssertFalse(try KeychainSecretStore().contains(.openAIRealtime) { _ in errSecItemNotFound })
    }

    func testDeniedOrUnavailableIsNotReportedAsMissingOrConfigured() {
        for status in [errSecInteractionNotAllowed, errSecAuthFailed, errSecNotAvailable] {
            XCTAssertThrowsError(try KeychainSecretStore().contains(.openAIRealtime) { _ in status })
        }
    }
}
