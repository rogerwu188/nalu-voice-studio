import AppKit
import Foundation
import UniformTypeIdentifiers

enum NativeFileExport {
    static func suggestedFilename(title: String, suffix: String) -> String {
        let forbidden = CharacterSet(charactersIn: "/:").union(.controlCharacters)
        let replaced = title.unicodeScalars.map { scalar -> Character in
            forbidden.contains(scalar) ? "-" : Character(String(scalar))
        }
        let compact = String(replaced)
            .split(whereSeparator: { $0.isWhitespace })
            .joined(separator: " ")
            .trimmingCharacters(in: CharacterSet(charactersIn: ".- "))
        let base = compact.isEmpty ? "Nalu项目" : String(compact.prefix(80))
        return "\(base)-\(suffix)"
    }

    @MainActor
    static func save(
        data: Data,
        suggestedFilename: String,
        contentType: UTType,
        title: String,
        message: String,
        prompt: String
    ) async throws -> URL? {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [contentType]
        panel.canCreateDirectories = true
        panel.isExtensionHidden = false
        panel.nameFieldStringValue = suggestedFilename
        panel.title = title
        panel.message = message
        panel.prompt = prompt

        let response: NSApplication.ModalResponse
        if let window = NSApp.keyWindow ?? NSApp.mainWindow {
            response = await withCheckedContinuation { continuation in
                panel.beginSheetModal(for: window) { result in
                    continuation.resume(returning: result)
                }
            }
        } else {
            response = panel.runModal()
        }

        guard response == .OK, let url = panel.url else { return nil }
        try data.write(to: url, options: .atomic)
        return url
    }
}
