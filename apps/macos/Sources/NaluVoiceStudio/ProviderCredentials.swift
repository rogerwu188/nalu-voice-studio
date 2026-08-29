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
        case .openAIRealtime: "OpenAI Realtime 自然语音"
        }
    }
}

struct KeychainSecretStore {
    private let service = "studio.nalu.voice.provider-credentials"

    func contains(_ credential: ProviderCredential) throws -> Bool {
        try read(credential) != nil
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
        if updateStatus == errSecSuccess { return }
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
    }

    func remove(_ credential: ProviderCredential) throws {
        let status = SecItemDelete(baseQuery(credential) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainSecretError.operationFailed(status)
        }
    }

    func secret(for credential: ProviderCredential) throws -> String? {
        guard let data = try read(credential) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func read(_ credential: ProviderCredential) throws -> Data? {
        var query = baseQuery(credential)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
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
    case operationFailed(OSStatus)

    var errorDescription: String? {
        switch self {
        case .emptySecret:
            "密钥不能为空。"
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
        return environment
    }
}
