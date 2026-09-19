import Testing
@testable import NaluVoiceStudio

struct FinalReviewIntegrityTests {
    @Test func rejectsWrongRunDuplicateMasterAndInvalidDigests() throws {
        let sha = String(repeating: "a", count: 64)
        func report(run: String = "run", master: String? = nil, count: Int = 1,
                    seal: String? = nil, failures: [String] = [], ok: Bool = true) -> RenderedOutputIntegrityResult {
            .init(seal: .init(runID: run, schemaVersion: "nalu.rendered-output-seal/v1",
                manifestSHA256: seal ?? sha,
                artifacts: (0..<count).map { _ in .init(kind: "master_video", sha256: master ?? sha) }),
                integrityOK: ok, failures: failures)
        }
        try report().validate(runID: "run")
        for invalid in [report(run: "other"), report(count: 0), report(count: 2),
                        report(master: String(repeating: "z", count: 64)), report(seal: "short"),
                        report(failures: ["tampered"]), report(ok: false)] {
            #expect(throws: (any Error).self) { try invalid.validate(runID: "run") }
        }
    }
}
