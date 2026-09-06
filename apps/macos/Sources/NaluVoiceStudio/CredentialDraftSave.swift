import Foundation

enum CredentialDraftSave {
    static func save(
        _ drafts: [(ProviderCredential, String)],
        using persist: (ProviderCredential, String) -> Bool
    ) -> Bool {
        for (credential, draft) in drafts {
            let cleaned = draft.trimmingCharacters(in: .whitespacesAndNewlines)
            // Empty means unchanged, never removal or a required unrelated provider.
            guard !cleaned.isEmpty else { continue }
            guard persist(credential, cleaned) else { return false }
        }
        return true
    }
}
