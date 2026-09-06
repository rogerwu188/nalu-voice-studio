import XCTest
@testable import NaluVoiceStudio

final class AssetDeletionPresentationTests: XCTestCase {
    func testUnreferencedAssetExplainsCancelAndLocalCopy() {
        let report = AssetDependencyReport(assetID: "asset", canDelete: true, productionRunIDs: [], explanation: "internal English")
        XCTAssertTrue(report.allowsDeletionPresentation)
        XCTAssertTrue(report.deletionMessage.contains("原始文件不受影响"))
        XCTAssertTrue(report.deletionMessage.contains("还没有删除"))
        XCTAssertFalse(report.deletionMessage.contains("internal English"))
    }

    func testSnapshotAlwaysBlocksEvenWithInconsistentPermission() {
        let report = AssetDependencyReport(assetID: "asset", canDelete: true, productionRunIDs: ["internal-id"], explanation: "delete now")
        XCTAssertFalse(report.allowsDeletionPresentation)
        XCTAssertTrue(report.deletionMessage.contains("1 个制作快照"))
        XCTAssertFalse(report.deletionMessage.contains("internal-id"))
        XCTAssertFalse(report.deletionMessage.contains("delete now"))
    }

    func testUnknownRestrictionDoesNotClaimNoDependencies() {
        let report = AssetDependencyReport(assetID: "asset", canDelete: false, productionRunIDs: [], explanation: "unknown")
        XCTAssertFalse(report.allowsDeletionPresentation)
        XCTAssertTrue(report.deletionMessage.contains("不能安全删除"))
    }
}
