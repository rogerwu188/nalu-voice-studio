import Foundation

struct FeedbackReviewPreparation: Equatable, Sendable {
    let expectedBehavior: String
    let actualBehavior: String
    let reproductionSteps: [String]

    static func infer(category: String, message: String, screen: String) -> Self {
        let cleaned = message.trimmingCharacters(in: .whitespacesAndNewlines)
        let expected: String
        switch category {
        case "bug":
            expected = "这个操作应当完成；如果不能完成，Nalu 应用简单的话说明原因和下一步。"
        case "feature_request":
            expected = "Nalu 应当在不增加老人和儿童操作负担的前提下支持这项需求。"
        case "correction":
            expected = "Nalu 应当采用用户明确给出的改正，并保留可撤销的修改记录。"
        case "preference":
            expected = "Nalu 应当只在本机应用这项明确偏好，并允许用户随时恢复。"
        default:
            expected = "这个页面应当让普通用户、老人和儿童能够看懂、听懂并顺利完成操作。"
        }
        return Self(
            expectedBehavior: expected,
            actualBehavior: cleaned,
            reproductionSteps: [
                "打开 Nalu 的“\(screen)”页面。",
                "按用户描述的方式操作或说话。",
                "观察到这条意见中描述的情况：\(cleaned)",
            ]
        )
    }
}
