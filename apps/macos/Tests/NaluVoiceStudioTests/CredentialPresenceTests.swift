import XCTest
import Security
@testable import NaluVoiceStudio

final class CredentialPresenceTests: XCTestCase {
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
