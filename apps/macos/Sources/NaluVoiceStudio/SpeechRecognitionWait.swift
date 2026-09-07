import Foundation

/// Resolves callback-based speech operations exactly once, including missing callbacks.
@MainActor final class SpeechRecognitionWait<Value: Sendable> {
    private var continuation: CheckedContinuation<Value, Error>?
    private var deadline: Task<Void, Never>?
    private var stop: (() -> Void)?
    private var started = false

    func run(timeoutNanoseconds: UInt64,
             start: (@escaping @Sendable (Result<Value, Error>) -> Void) -> (() -> Void)) async throws -> Value {
        guard !started else { throw LibrarySnapshotRefreshError.contextChanged }
        started = true
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                self.continuation = continuation
                guard !Task.isCancelled else { cancel(); return }
                deadline = Task { [weak self] in
                    do { try await Task.sleep(nanoseconds: timeoutNanoseconds) }
                    catch { return }
                    self?.finish(.failure(FinalMasterSpeechError.timedOut))
                }
                stop = start { [weak self] result in
                    Task { @MainActor in self?.finish(result) }
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in self?.cancel() }
        }
    }

    func cancel() { finish(.failure(CancellationError())) }

    private func finish(_ result: Result<Value, Error>) {
        guard let continuation else { return }
        self.continuation = nil
        deadline?.cancel(); deadline = nil
        let cleanup = stop; stop = nil
        cleanup?()
        continuation.resume(with: result)
    }
}
