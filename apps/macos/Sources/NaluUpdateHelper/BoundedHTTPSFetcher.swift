import Foundation
import NaluUpdateCore

enum HTTPSFetchError: Error, LocalizedError {
    case invalidURL
    case destinationExists
    case invalidResponse
    case redirectRejected
    case resourceTooLarge
    case timedOut

    var errorDescription: String? {
        switch self {
        case .invalidURL: "Only an exact HTTPS update URL is allowed."
        case .destinationExists: "The update download destination already exists."
        case .invalidResponse: "The update server returned an invalid response."
        case .redirectRejected: "Update downloads may not redirect to another URL."
        case .resourceTooLarge: "The update download exceeded its configured size limit."
        case .timedOut: "The update download timed out."
        }
    }
}

struct BoundedHTTPSFetcher: UpdateResourceFetching, @unchecked Sendable {
    private let configuration: URLSessionConfiguration

    init(configuration: URLSessionConfiguration = .ephemeral) {
        self.configuration = configuration
    }

    func fetch(_ source: URL, to destination: URL, maximumBytes: UInt64) throws {
        guard source.scheme == "https", source.host?.isEmpty == false,
              source.user == nil, source.password == nil
        else { throw HTTPSFetchError.invalidURL }
        guard destination.isFileURL,
              !FileManager.default.fileExists(atPath: destination.path)
        else { throw HTTPSFetchError.destinationExists }
        let attempt = HTTPSDownloadAttempt(
            source: source,
            destination: destination,
            maximumBytes: maximumBytes,
            configuration: configuration
        )
        do {
            try attempt.run()
        } catch {
            try? FileManager.default.removeItem(at: destination)
            throw error
        }
    }
}

private final class HTTPSDownloadAttempt: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let source: URL
    private let destination: URL
    private let maximumBytes: UInt64
    private let configuration: URLSessionConfiguration
    private let completion = DispatchSemaphore(value: 0)
    private var receivedBytes: UInt64 = 0
    private var output: FileHandle?
    private var terminalError: Error?
    private var session: URLSession?
    private var task: URLSessionDataTask?

    init(
        source: URL,
        destination: URL,
        maximumBytes: UInt64,
        configuration: URLSessionConfiguration
    ) {
        self.source = source
        self.destination = destination
        self.maximumBytes = maximumBytes
        self.configuration = configuration
    }

    func run() throws {
        configuration.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        configuration.urlCache = nil
        configuration.httpCookieStorage = nil
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 600
        let queue = OperationQueue()
        queue.maxConcurrentOperationCount = 1
        let session = URLSession(configuration: configuration, delegate: self, delegateQueue: queue)
        self.session = session
        var request = URLRequest(url: source)
        request.httpMethod = "GET"
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.setValue("application/json, application/zip", forHTTPHeaderField: "Accept")
        let task = session.dataTask(with: request)
        self.task = task
        task.resume()
        guard completion.wait(timeout: .now() + 610) == .success else {
            task.cancel()
            session.invalidateAndCancel()
            throw HTTPSFetchError.timedOut
        }
        session.finishTasksAndInvalidate()
        if let terminalError { throw terminalError }
        guard receivedBytes <= maximumBytes,
              FileManager.default.fileExists(atPath: destination.path)
        else { throw HTTPSFetchError.invalidResponse }
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse,
        newRequest request: URLRequest,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        terminalError = HTTPSFetchError.redirectRejected
        completionHandler(nil)
    }

    func urlSession(
        _ session: URLSession,
        dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
    ) {
        guard terminalError == nil,
              let response = response as? HTTPURLResponse,
              response.statusCode == 200,
              response.url == source,
              response.expectedContentLength < 0 ||
                UInt64(response.expectedContentLength) <= maximumBytes,
              FileManager.default.createFile(atPath: destination.path, contents: nil),
              let handle = try? FileHandle(forWritingTo: destination)
        else {
            if terminalError == nil {
                terminalError = response.expectedContentLength > 0 &&
                    UInt64(response.expectedContentLength) > maximumBytes
                    ? HTTPSFetchError.resourceTooLarge
                    : HTTPSFetchError.invalidResponse
            }
            completionHandler(.cancel)
            return
        }
        output = handle
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard terminalError == nil else { return }
        let next = receivedBytes + UInt64(data.count)
        guard next >= receivedBytes, next <= maximumBytes else {
            terminalError = HTTPSFetchError.resourceTooLarge
            dataTask.cancel()
            return
        }
        do {
            try output?.write(contentsOf: data)
            receivedBytes = next
        } catch {
            terminalError = error
            dataTask.cancel()
        }
    }

    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didCompleteWithError error: Error?
    ) {
        try? output?.close()
        output = nil
        if terminalError == nil { terminalError = error }
        completion.signal()
    }
}
