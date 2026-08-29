import Foundation

actor RuntimeClient {
    private let baseURL: URL
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(baseURL: URL = URL(string: "http://127.0.0.1:8765")!) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 10
        self.session = URLSession(configuration: configuration)
    }

    func health() async throws -> RuntimeHealth {
        let (data, response) = try await session.data(from: baseURL.appending(path: "health"))
        try validate(response, data: data)
        return try decoder.decode(RuntimeHealth.self, from: data)
    }

    func listProjects() async throws -> [NaluProject] {
        let (data, response) = try await session.data(from: baseURL.appending(path: "v1/projects"))
        try validate(response, data: data)
        return try decoder.decode([NaluProject].self, from: data)
    }

    func createProject(_ draft: ProjectDraft) async throws -> NaluProject {
        var request = URLRequest(url: baseURL.appending(path: "v1/projects"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(draft)
        let (data, response) = try await session.data(for: request)
        try validate(response, data: data)
        return try decoder.decode(NaluProject.self, from: data)
    }

    private func validate(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Unknown runtime error"
            throw RuntimeError.requestFailed(message)
        }
    }
}

enum RuntimeError: LocalizedError {
    case requestFailed(String)

    var errorDescription: String? {
        switch self {
        case .requestFailed(let message): message
        }
    }
}
