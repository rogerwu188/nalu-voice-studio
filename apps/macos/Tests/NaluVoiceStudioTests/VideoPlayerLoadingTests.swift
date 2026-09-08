import AppKit
import AVKit
import SwiftUI
import Testing

@Suite(.serialized)
struct VideoPlayerLoadingTests {
    @MainActor @Test func nativeAndSwiftUIPlayersCanBeInstantiated() {
        _ = NSApplication.shared
        let player = AVPlayer()
        let native = AVPlayerView(frame: NSRect(x: 0, y: 0, width: 320, height: 180))
        native.player = player
        #expect(native.player === player)

        // Launch-only tests never instantiate the SwiftUI AVKit overlay.
        let host = NSHostingView(rootView: VideoPlayer(player: player))
        host.frame = NSRect(x: 0, y: 0, width: 320, height: 180)
        host.layoutSubtreeIfNeeded()
        #expect(!host.subviews.isEmpty)
        native.player = nil
        player.pause()
    }
}
