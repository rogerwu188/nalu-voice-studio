import XCTest
@testable import NaluVoiceStudio

final class FeedbackReviewPreparationTests: XCTestCase {
    func testNaluInfersProfessionalReviewFieldsFromOnePlainLanguageReport() {
        let preparation = FeedbackReviewPreparation.infer(
            category: "bug",
            message: " 点上传照片没有反应 ",
            screen: "interview"
        )

        XCTAssertEqual(preparation.actualBehavior, "点上传照片没有反应")
        XCTAssertTrue(preparation.expectedBehavior.contains("说明原因和下一步"))
        XCTAssertEqual(preparation.reproductionSteps.count, 3)
        XCTAssertTrue(preparation.reproductionSteps[0].contains("interview"))
        XCTAssertTrue(preparation.reproductionSteps[2].contains("点上传照片没有反应"))
    }

    func testPreferenceDoesNotClaimAutomaticProductMutation() {
        let preparation = FeedbackReviewPreparation.infer(
            category: "preference",
            message: "请一直说慢一点",
            screen: "interview"
        )

        XCTAssertTrue(preparation.expectedBehavior.contains("只在本机"))
        XCTAssertTrue(preparation.expectedBehavior.contains("恢复"))
    }
}
