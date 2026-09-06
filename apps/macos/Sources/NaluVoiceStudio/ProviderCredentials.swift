import Foundation
import Security

enum ProviderCredential: String, CaseIterable, Identifiable {
    case seedance = "seedance-api-key"
    case minimax = "minimax-api-key"
    case openAIRealtime = "openai-realtime-api-key"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .seedance: "Seedance / SD2 Pro"
        case .minimax: "MiniMax H3"
        case .openAIRealtime: "OpenAI API（自然语音与联网查找）"
        }
    }
}

struct KeychainSecretStore {
    private let service = "studio.nalu.voice.provider-credentials"

    /// Presence is not proof of readability or provider validity. Do not decrypt
    /// a password (and potentially block on authorization) to draw a status badge.
    func contains(
        _ credential: ProviderCredential,
        lookup: (CFDictionary) -> OSStatus = { SecItemCopyMatching($0, nil) }
    ) throws -> Bool {
        var query = baseQuery(credential)
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        query[kSecReturnAttributes as String] = true
        query[kSecUseAuthenticationUI as String] = kSecUseAuthenticationUIFail
        let status = lookup(query as CFDictionary)
        if status == errSecItemNotFound { return false }
        guard status == errSecSuccess else {
            throw KeychainSecretError.operationFailed(status)
        }
        return true
    }

    func set(_ secret: String, for credential: ProviderCredential) throws {
        let cleaned = secret.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { throw KeychainSecretError.emptySecret }
        let encoded = Data(cleaned.utf8)
        let query = baseQuery(credential)
        let updateStatus = SecItemUpdate(
            query as CFDictionary,
            [kSecValueData as String: encoded] as CFDictionary
        )
        if updateStatus == errSecSuccess {
            try verifySaved(encoded, for: credential)
            return
        }
        guard updateStatus == errSecItemNotFound else {
            throw KeychainSecretError.operationFailed(updateStatus)
        }
        var create = query
        create[kSecValueData as String] = encoded
        create[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let addStatus = SecItemAdd(create as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw KeychainSecretError.operationFailed(addStatus)
        }
        try verifySaved(encoded, for: credential)
    }

    private func verifySaved(_ expected: Data, for credential: ProviderCredential) throws {
        guard try read(credential) == expected else {
            throw KeychainSecretError.verificationFailed
        }
    }

    func remove(_ credential: ProviderCredential) throws {
        let status = SecItemDelete(baseQuery(credential) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainSecretError.operationFailed(status)
        }
    }

    func secret(for credential: ProviderCredential, allowAuthenticationUI: Bool = true) throws -> String? {
        guard let data = try read(credential, allowAuthenticationUI: allowAuthenticationUI) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func readQuery(_ credential: ProviderCredential, allowAuthenticationUI: Bool) -> [String: Any] {
        var query = baseQuery(credential)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        if !allowAuthenticationUI {
            query[kSecUseAuthenticationUI as String] = kSecUseAuthenticationUIFail
        }
        return query
    }

    private func read(_ credential: ProviderCredential, allowAuthenticationUI: Bool = true) throws -> Data? {
        let query = readQuery(credential, allowAuthenticationUI: allowAuthenticationUI)
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = item as? Data else {
            throw KeychainSecretError.operationFailed(status)
        }
        return data
    }

    private func baseQuery(_ credential: ProviderCredential) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: credential.rawValue,
        ]
    }
}

enum KeychainSecretError: LocalizedError {
    case emptySecret
    case verificationFailed
    case operationFailed(OSStatus)

    var errorDescription: String? {
        switch self {
        case .emptySecret:
            "密钥不能为空。"
        case .verificationFailed:
            "钥匙串写入后未能核对成功，请重试。"
        case .operationFailed(let status):
            SecCopyErrorMessageString(status, nil) as String? ?? "macOS 钥匙串操作失败。"
        }
    }
}

enum RuntimeEnvironmentBuilder {
    private static let inheritedAllowlist = [
        "PATH", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SSL_CERT_FILE",
    ]

    static func build(
        inherited: [String: String],
        applicationSupport: URL,
        resources: URL
    ) -> [String: String] {
        var environment = inherited.filter { inheritedAllowlist.contains($0.key) }
        environment["NALU_DATA_ROOT"] = applicationSupport.appending(path: "data").path
        environment["NALU_DATABASE_PATH"] = applicationSupport
            .appending(path: "nalu.sqlite3").path
        environment["NALU_REPOSITORY_ROOT"] = resources
            .appending(path: "runtime-resources").path
        environment["NALU_VISUAL_ANALYZER_BINARY"] = resources
            .appending(path: "analyzers/nalu-visual-analyzer").path
        environment["NALU_SEMANTIC_RECOGNIZER_BINARY"] = resources
            .appending(path: "recognizers/nalu-semantic-recognizer").path
        return environment
    }
}
