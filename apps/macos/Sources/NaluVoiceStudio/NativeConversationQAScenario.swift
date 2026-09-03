import Foundation

enum NativeConversationQAScenarioError: LocalizedError {
    case unsupportedScenario(String)
    case requiresIsolatedLocalQA

    var errorDescription: String? {
        switch self {
        case .unsupportedScenario(let value):
            "不支持的本地界面 QA 场景：\(value)"
        case .requiresIsolatedLocalQA:
            "对话滚动 QA 只能在临时目录隔离的本地 QA 模式中运行。"
        }
    }
}

struct NativeConversationQAFixture {
    let messages: [InterviewMessage]
    let firstTranscript: String
    let finalTranscript: String
    let confidence: Float
}

enum NativeConversationQAScenario {
    static let environmentKey = "NALU_LOCAL_QA_SCENARIO"
    static let conversationScroll = "conversation-scroll"
    static let finalTranscriptPrefix = "【QA 当前实时转写】"

    static func isRequested(
        inherited: [String: String],
        temporaryDirectory: URL = FileManager.default.temporaryDirectory,
        fileManager: FileManager = .default
    ) throws -> Bool {
        guard let requested = inherited[environmentKey], !requested.isEmpty else {
            return false
        }
        guard requested == conversationScroll else {
            throw NativeConversationQAScenarioError.unsupportedScenario(requested)
        }
        guard inherited[RuntimeApplicationSupportResolver.localQAFlag] == "1" else {
            throw NativeConversationQAScenarioError.requiresIsolatedLocalQA
        }

        _ = try RuntimeApplicationSupportResolver.resolve(
            inherited: inherited,
            defaultURL: URL(fileURLWithPath: "/non-qa-user-data-must-not-be-used"),
            temporaryDirectory: temporaryDirectory,
            fileManager: fileManager
        )
        return true
    }

    static func fixture() -> NativeConversationQAFixture {
        let turns: [(InterviewMessage.Speaker, String)] = [
            (.nalu, "您好，我们只用本机假资料检查长对话是否一直跟着当前一句。"),
            (.user, "我想讲小时候住在海边的故事。"),
            (.nalu, "好，我们慢慢来。那座海边小城叫什么名字？"),
            (.user, "叫青湾，我和外婆住在一栋白色的小房子里。"),
            (.nalu, "您记得房子附近最熟悉的声音吗？"),
            (.user, "早晨能听见船笛，晚上能听见海浪。"),
            (.nalu, "故事里最重要的人是谁？"),
            (.user, "是外婆，她每天带我去市场买鱼。"),
            (.nalu, "有没有一张照片能让您马上想起那一天？"),
            (.user, "有一张我拿着红色小桶站在码头边的旧照片。"),
            (.nalu, "这张照片大约是哪一年拍的？"),
            (.user, "大约是一九八二年的夏天。"),
            (.nalu, "那一天发生了什么特别的事情？"),
            (.user, "我第一次跟着外婆坐小船，还遇到一场突然来的大雨。"),
            (.nalu, "这段回忆对您为什么重要？"),
            (.user, "因为外婆把自己的雨衣给了我，她自己全身都淋湿了。"),
            (.nalu, "我听懂了：这是一个关于照顾、勇气和想念的故事。"),
            (.user, "对，我还想补充最后一句，请继续听我说。"),
        ]
        return NativeConversationQAFixture(
            messages: turns.map { InterviewMessage(speaker: $0.0, text: $0.1) },
            firstTranscript: "我正在补充码头上的那场雨，请把这句话记在最下面。",
            finalTranscript: "\(finalTranscriptPrefix)外婆把雨衣披在我身上以后，还笑着说不用害怕。",
            confidence: 0.94
        )
    }

    @MainActor
    static func installIfRequested(
        on model: VoiceInterviewViewModel,
        inherited: [String: String] = ProcessInfo.processInfo.environment
    ) throws {
        guard try isRequested(inherited: inherited) else { return }
        let fixture = fixture()
        model.messages = fixture.messages
        model.transcriptConfidence = fixture.confidence
        model.transcript = fixture.firstTranscript

        Task { @MainActor [weak model] in
            try? await Task.sleep(for: .milliseconds(800))
            guard let model else { return }
            model.transcript = fixture.finalTranscript
        }
    }
}
