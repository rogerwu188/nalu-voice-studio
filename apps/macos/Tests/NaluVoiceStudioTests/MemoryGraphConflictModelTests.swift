import Foundation
import Testing
@testable import NaluVoiceStudio

struct MemoryGraphConflictModelTests {
    @Test func decodesEvidenceLinkedSpokenConflictReport() throws {
        let data = Data(
            #"""
            {
              "project_id":"prj_1",
              "candidate_memory_id":"mem_new",
              "checked_against_confirmed_cards":2,
              "blocking":true,
              "conflicts":[{
                "kind":"relationship",
                "subject":"李小梅",
                "candidate_value":"母亲",
                "existing_value":"妻子",
                "candidate_memory_id":"mem_new",
                "candidate_revision":2,
                "candidate_asset_id":"ast_new",
                "existing_memory_id":"mem_old",
                "existing_revision":1,
                "existing_asset_id":"ast_old",
                "explanation":"李小梅的关系对不上。"
              }],
              "spoken_summary":"我发现一处资料对不上，暂时不能归档。"
            }
            """#.utf8
        )

        let report = try JSONDecoder().decode(MemoryGraphConflictReport.self, from: data)

        #expect(report.blocking)
        #expect(report.checkedAgainstConfirmedCards == 2)
        #expect(report.conflicts.first?.candidateRevision == 2)
        #expect(report.conflicts.first?.existingAssetID == "ast_old")
        #expect(report.spokenSummary.contains("暂时不能归档"))
    }
}
