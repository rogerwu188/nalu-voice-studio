import Foundation

enum PrivacySafety {
    static func canImportAsset(
        kind: String,
        name: String,
        subjectName: String,
        consentGranted: Bool,
        consentStatement: String,
        guardianRequired: Bool,
        guardianApproved: Bool,
        scopeToEpisode: Bool,
        selectedEpisodeID: String?
    ) -> Bool {
        guard !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return false
        }
        guard !scopeToEpisode || selectedEpisodeID != nil else { return false }
        guard ["character_image", "voice_reference"].contains(kind) else { return true }
        guard consentGranted,
              !subjectName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !consentStatement.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return false
        }
        return !guardianRequired || guardianApproved
    }

    static func canDeleteProject(
        preview: ProjectDeletionPreview?,
        confirmationTitle: String,
        deleteProductionSnapshots: Bool
    ) -> Bool {
        guard let preview, confirmationTitle == preview.projectTitle else { return false }
        return !preview.requiresSnapshotDeletionConfirmation || deleteProductionSnapshots
    }
}
