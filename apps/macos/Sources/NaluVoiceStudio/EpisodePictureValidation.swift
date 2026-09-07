import CryptoKit
import Foundation

struct EpisodePicture: Sendable {
    let fileURL: URL
    let receiptID: String
    let sha256: String
    let editSHA: String
}

enum EpisodePictureValidation {
    @discardableResult static func validate(bytes: Data, response: URLResponse, editSHA: String) throws -> String {
        guard let http = response as? HTTPURLResponse, http.statusCode == 200, http.mimeType == "video/mp4",
              (12...128_000_000).contains(bytes.count), bytes.subdata(in: 4..<8) == Data("ftyp".utf8),
              http.value(forHTTPHeaderField: "X-Nalu-Edit-SHA256") == editSHA,
              http.value(forHTTPHeaderField: "X-Nalu-Preview-Audio") == "none",
              http.value(forHTTPHeaderField: "X-Nalu-Master-Accepted") == "false",
              let receiptID = http.value(forHTTPHeaderField: "X-Nalu-Preview-Receipt-ID"),
              !receiptID.isEmpty, receiptID.count <= 160,
              receiptID.range(of: "^[A-Za-z0-9_-]+$", options: .regularExpression) != nil,
              http.value(forHTTPHeaderField: "X-Nalu-Preview-SHA256") == SHA256.hash(data: bytes).map({ String(format: "%02x", $0) }).joined()
        else { throw RuntimeError.requestFailed("预览与当前剪辑不一致，已停止播放。剪辑和原视频仍保留。") }
        return receiptID
    }
}
