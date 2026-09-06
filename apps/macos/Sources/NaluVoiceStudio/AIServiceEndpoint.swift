import Foundation

struct AIServiceEndpoint {
    static let official = "https://api.openai.com/v1"
    static let preferenceKey = "nalu.ai-service-base-url"
    let baseURL: URL

    init(_ raw: String) throws {
        let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let parts = URLComponents(string: value),
              parts.scheme == "https", let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil,
              parts.query == nil, parts.fragment == nil,
              parts.port == nil || parts.port == 443,
              parts.path == "/v1" || parts.path == "/v1/",
              let url = parts.url else { throw EndpointError.invalidAddress }
        baseURL = url
    }

    static func current() throws -> AIServiceEndpoint {
        try AIServiceEndpoint(UserDefaults.standard.string(forKey: preferenceKey) ?? official)
    }

    func url(_ path: String) -> URL { baseURL.appendingPathComponent(path) }

    enum EndpointError: LocalizedError {
        case invalidAddress
        var errorDescription: String? {
            "API 地址须为 https://服务商域名/v1，不能包含密钥、查询参数或其他端口。"
        }
    }
}

/// Never forward credentials to a redirect destination chosen by a provider.
final class AIServiceRedirectGuard: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
