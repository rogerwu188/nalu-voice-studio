import XCTest
@testable import NaluVoiceStudio

final class PrivacySafetyTests: XCTestCase {
    func testBiometricImportFailsClosedWithoutCompleteConsent() {
        XCTAssertFalse(canImport(consentGranted: false, guardianApproved: true))
        XCTAssertFalse(canImport(consentGranted: true, guardianApproved: false))
        XCTAssertTrue(canImport(consentGranted: true, guardianApproved: true))
    }

    func testEpisodeScopeRequiresSelectedEpisode() {
        XCTAssertFalse(
            PrivacySafety.canImportAsset(
                kind: "source_document",
                name: "采访记录",
                subjectName: "",
                consentGranted: false,
                consentStatement: "",
                guardianRequired: false,
                guardianApproved: false,
                scope: "episode",
                selectedSeasonID: "sea_1",
                selectedEpisodeID: nil
            )
        )
    }

    func testSeasonScopeRequiresSelectedSeason() {
        XCTAssertFalse(
            PrivacySafety.canImportAsset(
                kind: "scene_reference",
                name: "本季场景",
                subjectName: "",
                consentGranted: false,
                consentStatement: "",
                guardianRequired: false,
                guardianApproved: false,
                scope: "season",
                selectedSeasonID: nil,
                selectedEpisodeID: "ep_1"
            )
        )
    }

    func testProjectDeletionRequiresExactTitleAndSnapshotConfirmation() {
        let preview = ProjectDeletionPreview(
            projectID: "prj_1",
            projectTitle: "我的故事",
            assetCount: 2,
            productionRunCount: 1,
            requiresSnapshotDeletionConfirmation: true,
            explanation: "requires confirmation"
        )
        XCTAssertFalse(
            PrivacySafety.canDeleteProject(
                preview: preview,
                confirmationTitle: "我的故亊",
                deleteProductionSnapshots: true
            )
        )
        XCTAssertFalse(
            PrivacySafety.canDeleteProject(
                preview: preview,
                confirmationTitle: "我的故事",
                deleteProductionSnapshots: false
            )
        )
        XCTAssertTrue(
            PrivacySafety.canDeleteProject(
                preview: preview,
                confirmationTitle: "我的故事",
                deleteProductionSnapshots: true
            )
        )
    }

    private func canImport(consentGranted: Bool, guardianApproved: Bool) -> Bool {
        PrivacySafety.canImportAsset(
            kind: "character_image",
            name: "主角照片",
            subjectName: "小岚",
            consentGranted: consentGranted,
            consentStatement: "同意用于本项目",
            guardianRequired: true,
            guardianApproved: guardianApproved,
            scope: "project",
            selectedSeasonID: nil,
            selectedEpisodeID: nil
        )
    }
}
