import Foundation

/// A Keychain call can stall below the noninteractive Security API. Bound the
/// caller's wait without pretending that the underlying system call was cancelled.
final class DiagnosticCredentialReader: @unchecked Sendable {
    static let shared = DiagnosticCredentialReader()
    private let lock = NSLock()
    private var pending = false
    private let queue = DispatchQueue(label: "studio.nalu.diagnostic-credential")

    private final class Attempt: @unchecked Sendable {
        let lock = NSLock()
        var continuation: CheckedContinuation<String?, Error>?
        init(_ continuation: CheckedContinuation<String?, Error>) {
            self.continuation = continuation
        }
        func finish(_ result: Result<String?, Error>) {
            lock.lock()
            let callback = continuation
            continuation = nil
            lock.unlock()
            callback?.resume(with: result)
        }
    }

    func read(timeout: TimeInterval = 5,
              lookup: @escaping @Sendable () throws -> String? = {
                  try KeychainSecretStore().secret(for: .openAIRealtime, allowAuthenticationUI: false)
              }) async throws -> String? {
        try Task.checkCancellation()
        return try await withCheckedThrowingContinuation { continuation in
            lock.lock()
            guard !pending else {
                lock.unlock()
                continuation.resume(throwing: AIServiceModelList.CheckError.credentialReadPending)
                return
            }
            pending = true
            lock.unlock()
            let attempt = Attempt(continuation)
            DispatchQueue.global().asyncAfter(deadline: .now() + timeout) {
                attempt.finish(.failure(AIServiceModelList.CheckError.credentialReadTimedOut))
            }
            queue.async {
                let result = Result { try lookup() }
                // A late result only releases this worker. It cannot resume the
                // timed-out request or start any provider request on its behalf.
                self.lock.lock()
                self.pending = false
                self.lock.unlock()
                attempt.finish(result)
            }
        }
    }
}
