// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NaluVoiceStudio",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "NaluVoiceStudio", targets: ["NaluVoiceStudio"]),
        .executable(name: "NaluVisualAnalyzer", targets: ["NaluVisualAnalyzer"]),
    ],
    targets: [
        .executableTarget(name: "NaluVoiceStudio"),
        .executableTarget(name: "NaluVisualAnalyzer"),
        .testTarget(name: "NaluVoiceStudioTests", dependencies: ["NaluVoiceStudio"])
    ]
)
