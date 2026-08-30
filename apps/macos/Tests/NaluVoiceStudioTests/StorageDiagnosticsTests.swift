import XCTest
@testable import NaluVoiceStudio

final class StorageDiagnosticsTests: XCTestCase {
    func testAvailableSpaceUsesReadableFileSize() {
        let diagnostics = StorageDiagnostics(
            status: "warning",
            availableBytes: 10 * 1024 * 1024 * 1024,
            totalBytes: 100 * 1024 * 1024 * 1024,
            databaseBytes: 4096,
            minimumProductionReserveBytes: 5 * 1024 * 1024 * 1024,
            recommendedFreeBytes: 20 * 1024 * 1024 * 1024,
            canStartNewProduction: true,
            explanation: "本机空间偏少"
        )

        XCTAssertFalse(diagnostics.availableLabel.isEmpty)
        XCTAssertTrue(diagnostics.availableLabel.contains("GB"))
    }
}
