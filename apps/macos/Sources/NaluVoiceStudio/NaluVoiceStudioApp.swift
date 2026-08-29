import SwiftUI

@main
struct NaluVoiceStudioApp: App {
    @State private var interview = VoiceInterviewViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(interview)
                .frame(minWidth: 980, minHeight: 680)
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 1180, height: 760)
    }
}
