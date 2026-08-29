// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NaluVoiceStudio",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "NaluVoiceStudio", targets: ["NaluVoiceStudio"])
    ],
    targets: [
        .executableTarget(name: "NaluVoiceStudio")
    ]
)
