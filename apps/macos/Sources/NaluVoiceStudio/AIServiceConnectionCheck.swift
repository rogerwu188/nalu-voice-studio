import Foundation

struct AIServiceModelList: Decodable {
    struct Model: Decodable { let id: String }
    let data: [Model]

    static func summary(_ bytes: Data, secret: String, savedModels: AIServiceModels? = nil) throws -> String {
        guard bytes.count <= 1_000_000,
              let list = try? JSONDecoder().decode(Self.self, from: bytes),
              list.data.count <= 10_000 else { throw CheckError.invalidResponse }
        // Model IDs are untrusted provider output, never instructions or markup.
        let names = list.data.map(\.id).filter {
            !$0.isEmpty && $0.count <= 128 && !$0.contains(secret)
                && !$0.hasPrefix("sk-")
                && $0.range(of: "^[A-Za-z0-9][A-Za-z0-9._:/-]*$", options: .regularExpression) != nil
        }
        let displayed = names.prefix(10).joined(separator: "、")
        var selectionSummary = ""
        if let savedModels {
            _ = try savedModels.validated()
            let available = Set(names)
            for (label, model) in [("查询", savedModels.research), ("实时语音", savedModels.realtime), ("转写", savedModels.transcription)] {
                // Do not echo user-entered values: they might accidentally contain
                // a credential. Membership is advisory, never a capability test.
                selectionSummary += "\n已保存的\(label)模型：" + (available.contains(model) ? "列表中可见（功能未验证）" : "列表中未找到，请向服务商核实")
            }
        }
        return "模型列表访问成功，返回 \(list.data.count) 个模型。"
            + (displayed.isEmpty ? "" : "\n模型：\(displayed)")
            + selectionSummary
            + "\n这仅验证地址和模型列表访问，不代表聊天、联网搜索或实时语音已通过测试。"
    }

    enum CheckError: LocalizedError {
        case invalidResponse
        case credentialAccessRequired
        case credentialReadTimedOut
        case credentialReadPending
        var errorDescription: String? {
            switch self {
            case .invalidResponse:
                "服务商返回的模型列表格式不受支持；尚未验证连接能力。"
            case .credentialAccessRequired:
                "本次检查无法读取钥匙串中的密钥，尚未连接服务商。请先解锁钥匙串并允许 Nalu 访问，或在本窗口输入密钥后再检查；无需发到聊天中。"
            case .credentialReadTimedOut:
                "读取钥匙串超时，尚未连接服务商。系统读取可能仍在等待；您可以在本窗口输入密钥后检查，无需发到聊天中。"
            case .credentialReadPending:
                "上一次系统钥匙串读取仍在等待，本次不会重复读取或连接服务商。您可以在本窗口输入密钥后检查。"
            }
        }
    }
}

actor AIServiceConnectionCheck {
    func check(endpoint: AIServiceEndpoint, draft: String) async throws -> String {
        let savedModels = try AIServiceModels.load(for: endpoint)
        let entered = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        let saved: String?
        do {
            if entered.isEmpty { saved = try await DiagnosticCredentialReader.shared.read() }
            else { saved = entered }
        } catch let error as AIServiceModelList.CheckError { throw error
        } catch { throw AIServiceModelList.CheckError.credentialAccessRequired }
        try Task.checkCancellation()
        guard let key = saved,
              !key.isEmpty else { throw RealtimeVoiceError.missingCredential }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 20
        configuration.timeoutIntervalForResource = 25
        let session = URLSession(configuration: configuration,
                                 delegate: AIServiceRedirectGuard(), delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        var request = URLRequest(url: endpoint.url("models"))
        request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let (stream, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw AIServiceModelList.CheckError.invalidResponse
        }
        if let failure = RealtimeVoiceError.forHTTPStatus(http.statusCode) { throw failure }
        var data = Data()
        for try await byte in stream {
            guard data.count < 1_000_000 else { throw AIServiceModelList.CheckError.invalidResponse }
            data.append(byte)
        }
        return try AIServiceModelList.summary(data, secret: key, savedModels: savedModels)
    }
}
