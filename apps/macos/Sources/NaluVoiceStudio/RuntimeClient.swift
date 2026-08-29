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
        try await post("v1/projects", body: draft)
    }

    func createProjectPlan(_ draft: ProjectPlanDraft) async throws -> ProjectPlan {
        try await post("v1/project-plans", body: draft)
    }

    func listSeasons(projectID: String) async throws -> [NaluSeason] {
        try await get("v1/projects/\(projectID)/seasons")
    }

    func createSeason(projectID: String, draft: SeasonDraft) async throws -> NaluSeason {
        try await post("v1/projects/\(projectID)/seasons", body: draft)
    }

    func listEpisodes(seasonID: String) async throws -> [NaluEpisode] {
        try await get("v1/seasons/\(seasonID)/episodes")
    }

    func createEpisode(seasonID: String, draft: EpisodeDraft) async throws -> NaluEpisode {
        try await post("v1/seasons/\(seasonID)/episodes", body: draft)
    }

    private func get<Response: Decodable>(_ path: String) async throws -> Response {
        let (data, response) = try await session.data(from: baseURL.appending(path: path))
        try validate(response, data: data)
        return try decoder.decode(Response.self, from: data)
    }

    private func post<Body: Encodable, Response: Decodable>(
        _ path: String, body: Body
    ) async throws -> Response {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        let (data, response) = try await session.data(for: request)
        try validate(response, data: data)
        return try decoder.decode(Response.self, from: data)
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
