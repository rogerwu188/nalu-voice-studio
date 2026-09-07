import Foundation
import Testing
@testable import NaluVoiceStudio

@MainActor @Test func speechWaitResolvesDuplicateCallbacksOnce() async throws {
    let wait = SpeechRecognitionWait<Int>()
    var stopped = 0
    let result = try await wait.run(timeoutNanoseconds: 1_000_000_000) { complete in
        complete(.success(7)); complete(.success(9))
        return { stopped += 1 }
    }
    #expect([7, 9].contains(result) && stopped == 1)
    wait.cancel()
    #expect(stopped == 1)
}

@MainActor @Test func speechWaitTimesOutWithoutServiceCallback() async {
    let wait = SpeechRecognitionWait<Int>()
    var stopped = 0
    do {
        _ = try await wait.run(timeoutNanoseconds: 1_000_000) { _ in { stopped += 1 } }
        Issue.record("missing speech callback must time out")
    } catch FinalMasterSpeechError.timedOut {} catch { Issue.record("wrong timeout error") }
    #expect(stopped == 1)
}

@MainActor @Test func speechWaitCancellationStopsTheServiceAndIgnoresLateResult() async {
    let wait = SpeechRecognitionWait<Int>()
    var stopped = 0
    var complete: (@Sendable (Result<Int, Error>) -> Void)?
    let operation = Task { try await wait.run(timeoutNanoseconds: 1_000_000_000) { callback in
        complete = callback
        return { stopped += 1 }
    } }
    for _ in 0..<100 where complete == nil { await Task.yield() }
    guard complete != nil else { operation.cancel(); Issue.record("speech operation did not start"); return }
    operation.cancel()
    do { _ = try await operation.value; Issue.record("cancelled speech must not return words") }
    catch is CancellationError {} catch { Issue.record("wrong cancellation error") }
    complete?(.success(1))
    await Task.yield()
    #expect(stopped == 1)
}

@MainActor @Test func speechWaitCannotBeReusedAfterCompletion() async throws {
    let wait = SpeechRecognitionWait<Int>()
    _ = try await wait.run(timeoutNanoseconds: 1_000_000_000) { complete in
        complete(.success(1)); return {}
    }
    var restarted = false
    do {
        _ = try await wait.run(timeoutNanoseconds: 1_000_000_000) { _ in restarted = true; return {} }
        Issue.record("old callbacks must not target a reused waiter")
    } catch {}
    #expect(!restarted)
}
