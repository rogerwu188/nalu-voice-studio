import XCTest
@testable import NaluVoiceStudio

final class DocumentaryReadinessTests: XCTestCase {
    func testSpokenSummaryExplainsEvidencePlanningAndReenactmentGate() {
        let report = DocumentaryReadinessReport(
            projectID: "prj_1",
            documentaryMode: "archival_with_reenactment",
            evidence: [
                DocumentaryEvidenceItem(
                    assetID: "ast_1",
                    memoryID: "mem_1",
                    name: "老火车站照片",
                    kind: "source_document",
                    scope: "project",
                    confirmationStatus: "confirmed",
                    currentRevision: 1,
                    allowedUse: "story_development",
                    narrativeAuthority: true,
                    visualGenerationAuthorized: false
                )
            ],
            confirmedNarrativeSourceCount: 1,
            draftOrUnlinkedSourceCount: 0,
            canPlanChapters: true,
            canEnterProduction: false,
            generatedReenactmentLabelRequired: true,
            blockers: ["adapter pending"],
            nextQuestions: ["您想按时间顺序讲，还是按人生主题分章？"]
        )

        XCTAssertTrue(report.spokenSummary.contains("可以开始规划章节"))
        XCTAssertTrue(report.spokenSummary.contains("还不能进入成片生产"))
        XCTAssertTrue(report.spokenSummary.contains("必须清楚标明为重现"))
        XCTAssertTrue(report.spokenSummary.contains("按时间顺序"))
    }
}
