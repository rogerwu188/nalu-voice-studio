// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NaluVoiceStudio",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "NaluVoiceStudio", targets: ["NaluVoiceStudio"]),
        .executable(name: "NaluVisualAnalyzer", targets: ["NaluVisualAnalyzer"]),
        .executable(name: "NaluSemanticRecognizer", targets: ["NaluSemanticRecognizer"]),
        .executable(name: "NaluUpdateHelper", targets: ["NaluUpdateHelper"]),
    ],
    targets: [
        .executableTarget(name: "NaluVoiceStudio"),
        .executableTarget(name: "NaluVisualAnalyzer"),
        .executableTarget(name: "NaluSemanticRecognizer"),
        .target(name: "NaluUpdateCore"),
        .executableTarget(name: "NaluUpdateHelper", dependencies: ["NaluUpdateCore"]),
        .testTarget(name: "NaluVoiceStudioTests", dependencies: ["NaluVoiceStudio"]),
        .testTarget(name: "NaluUpdateCoreTests", dependencies: ["NaluUpdateCore"]),
        .testTarget(name: "NaluUpdateHelperTests", dependencies: ["NaluUpdateHelper"]),
    ]
)
