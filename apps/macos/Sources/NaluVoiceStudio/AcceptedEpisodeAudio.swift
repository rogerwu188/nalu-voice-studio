import CryptoKit
import Foundation

struct AcceptedEpisodeAudio: Sendable {
    let data: Data
    let sha256: String
    let takeID: String
    let reviewID: String
    let sampleCount: Int
}

enum AcceptedEpisodeAudioValidation {
    // Runtime's export contract is canonical PCM WAV, not arbitrary imported WAV.
    static func validate(_ data: Data, response: URLResponse, takeID: String,
                         reviewID: String, sampleCount: Int) throws -> AcceptedEpisodeAudio {
        guard !Task.isCancelled, !takeID.isEmpty, !reviewID.isEmpty,
              (1...14_400_000).contains(sampleCount), data.count == 44 + sampleCount * 4,
              let http = response as? HTTPURLResponse, http.statusCode == 200,
              http.mimeType == "audio/wav",
              http.value(forHTTPHeaderField: "X-Nalu-Take-ID") == takeID,
              http.value(forHTTPHeaderField: "X-Nalu-Review-ID") == reviewID,
              http.value(forHTTPHeaderField: "Cache-Control") == "no-store" else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let bytes = Array(data.prefix(44))
        func text(_ start: Int, _ count: Int) -> String { String(decoding: bytes[start..<(start + count)], as: UTF8.self) }
        func number(_ start: Int, _ count: Int) -> Int {
            (0..<count).reduce(0) { $0 | (Int(bytes[start + $1]) << ($1 * 8)) }
        }
        guard text(0, 4) == "RIFF", number(4, 4) == data.count - 8,
              text(8, 4) == "WAVE", text(12, 4) == "fmt ", number(16, 4) == 16,
              number(20, 2) == 1, number(22, 2) == 2, number(24, 4) == 48000,
              number(28, 4) == 192000, number(32, 2) == 4, number(34, 2) == 16,
              text(36, 4) == "data", number(40, 4) == sampleCount * 4 else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        let sha = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        guard http.value(forHTTPHeaderField: "X-Nalu-Audio-SHA256") == sha else {
            throw LibrarySnapshotRefreshError.contextChanged
        }
        return AcceptedEpisodeAudio(data: data, sha256: sha, takeID: takeID, reviewID: reviewID, sampleCount: sampleCount)
    }
}
