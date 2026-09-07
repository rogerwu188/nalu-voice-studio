import Foundation

struct LibrarySnapshotRefreshPreview: Decodable {
    var run_id: String
    var refresh_required: Bool
    var request: Request
    struct Request: Codable {
        var source_event_id: String
        var expected_plan_sha256: String
        var expected_package_sha256: String
        var expected_library_sha256: String
    }
}

enum LibrarySnapshotRefreshError: LocalizedError {
    case contextChanged
    var errorDescription: String? { "本集制作资料已变化，请重新核对；原剧本和人物确认仍然保留。" }
}
