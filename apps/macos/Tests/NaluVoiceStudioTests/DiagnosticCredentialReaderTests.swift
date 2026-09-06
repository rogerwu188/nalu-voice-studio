import XCTest
@testable import NaluVoiceStudio

final class DiagnosticCredentialReaderTests: XCTestCase {
    func testSuccessfulReadAndMissingValue() async throws {
        let reader = DiagnosticCredentialReader()
        let value = try await reader.read { "synthetic-only" }
        XCTAssertEqual(value, "synthetic-only")
        let missing = try await reader.read { nil }
        XCTAssertNil(missing)
    }

    func testLookupFailureIsReturned() async {
        do {
            _ = try await DiagnosticCredentialReader().read {
                throw AIServiceModelList.CheckError.credentialAccessRequired
            }
            XCTFail("Expected credential error")
        } catch {
            guard case AIServiceModelList.CheckError.credentialAccessRequired = error else {
                return XCTFail("Unexpected error")
            }
        }
    }

    func testTimeoutDoesNotQueueMoreSystemReadsAndLateResultIsDiscarded() async throws {
        let reader = DiagnosticCredentialReader()
        let release = DispatchSemaphore(value: 0)
        let finished = expectation(description: "Late lookup returned")
        defer { release.signal() }
        do {
            _ = try await reader.read(timeout: 0.05) {
                release.wait()
                finished.fulfill()
                return "late-synthetic-only"
            }
            XCTFail("Expected timeout, not the late value")
        } catch {
            guard case AIServiceModelList.CheckError.credentialReadTimedOut = error else {
                return XCTFail("Unexpected error")
            }
        }
        do {
            _ = try await reader.read {
                XCTFail("Must not enqueue another system lookup")
                return nil
            }
            XCTFail("Expected pending error")
        } catch {
            guard case AIServiceModelList.CheckError.credentialReadPending = error else {
                return XCTFail("Unexpected error")
            }
        }
        release.signal()
        await fulfillment(of: [finished], timeout: 2)
        // A double continuation resume after timeout would trap the test process.
        try await Task.sleep(nanoseconds: 50_000_000)
        let fresh = try await reader.read { "fresh-synthetic-only" }
        XCTAssertEqual(fresh, "fresh-synthetic-only")
    }
}
