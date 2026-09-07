import CryptoKit
import Foundation
import Testing
@testable import NaluVoiceStudio

@Test func acceptedRecordingAudioValidatesActualPCMAndExactIdentity() throws {
    var bytes = Array("RIFF".utf8)
    func append(_ value: Int, _ length: Int) {
        bytes += (0..<length).map { UInt8((value >> ($0 * 8)) & 255) }
    }
    append(44, 4) // total 52 bytes: two stereo samples
    bytes += Array("WAVEfmt ".utf8)
    append(16, 4); append(1, 2); append(2, 2)
    append(48000, 4); append(192000, 4); append(4, 2); append(16, 2)
    bytes += Array("data".utf8); append(8, 4)
    bytes += [1, 0, 2, 0, 3, 0, 4, 0]
    let data = Data(bytes)
    func response(_ data: Data, override: [String: String] = [:]) -> HTTPURLResponse {
        var headers = ["Content-Type": "audio/wav", "Cache-Control": "no-store",
            "X-Nalu-Take-ID": "take", "X-Nalu-Review-ID": "review",
            "X-Nalu-Audio-SHA256": SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()]
        headers.merge(override) { _, new in new }
        return HTTPURLResponse(url: URL(string: "http://127.0.0.1/audio")!, statusCode: 200,
                               httpVersion: nil, headerFields: headers)!
    }
    let accepted = try AcceptedEpisodeAudioValidation.validate(data, response: response(data),
        takeID: "take", reviewID: "review", sampleCount: 2)
    #expect(accepted.data == data && accepted.sampleCount == 2)
    for (key, value) in [("X-Nalu-Take-ID", "other"), ("X-Nalu-Review-ID", "old"),
                         ("X-Nalu-Audio-SHA256", "wrong"), ("Content-Type", "text/html"),
                         ("Cache-Control", "public")] {
        #expect(throws: (any Error).self) {
            try AcceptedEpisodeAudioValidation.validate(data, response: response(data, override: [key: value]),
                takeID: "take", reviewID: "review", sampleCount: 2)
        }
    }
    for index in [0, 4, 8, 12, 16, 20, 22, 24, 28, 32, 34, 36, 40] {
        var changed = data; changed[index] ^= 1
        #expect(throws: (any Error).self) {
            try AcceptedEpisodeAudioValidation.validate(changed, response: response(changed),
                takeID: "take", reviewID: "review", sampleCount: 2)
        }
    }
    for count in [0, 1, 3, Int.max] {
        #expect(throws: (any Error).self) {
            try AcceptedEpisodeAudioValidation.validate(data, response: response(data),
                takeID: "take", reviewID: "review", sampleCount: count)
        }
    }
}
