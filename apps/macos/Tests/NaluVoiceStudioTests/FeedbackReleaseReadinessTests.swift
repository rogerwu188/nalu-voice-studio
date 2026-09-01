import Foundation
import XCTest
@testable import NaluVoiceStudio

final class FeedbackReleaseReadinessTests: XCTestCase {
    func testDecodesMissingRolloutGatesWithoutClaimingRelease() throws {
        let data = Data(
            #"{"feedback_id":"fb_1","feedback_status":"ready_for_review","checks":[{"id":"review_bundle","status":"satisfied","explanation":"审核包已冻结"},{"id":"staged_rollout_receipt","status":"missing","explanation":"尚无真实发布回执"}],"ready_for_authorized_rollout":true,"released":false,"release_claimed":false,"network_call_performed":false,"external_write_performed":false,"schema_version":"nalu.feedback-governed-release-readiness/v1"}"#.utf8
        )

        let report = try JSONDecoder().decode(
            FeedbackGovernedReleaseReadiness.self,
            from: data
        )

        XCTAssertTrue(report.readyForAuthorizedRollout)
        XCTAssertFalse(report.released)
        XCTAssertFalse(report.releaseClaimed)
        XCTAssertEqual(report.checks.first?.status, "satisfied")
        XCTAssertEqual(report.checks.last?.id, "staged_rollout_receipt")
        XCTAssertEqual(report.checks.last?.status, "missing")
    }
}
