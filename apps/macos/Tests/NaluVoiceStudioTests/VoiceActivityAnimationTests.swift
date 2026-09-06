import XCTest
@testable import NaluVoiceStudio

final class VoiceActivityAnimationTests: XCTestCase {
    func testLevelsStayWithinRenderableRange() {
        for tick in stride(from: 0.0, through: 10.0, by: 0.05) {
            for bar in 0..<5 {
                let level = VoiceActivityAnimation.level(
                    at: tick,
                    offset: Double(bar) * 0.7
                )
                XCTAssertGreaterThanOrEqual(level, 0)
                XCTAssertLessThanOrEqual(level, 1)
            }
        }
    }

    func testSuccessiveAnimationFramesChangeTheVisibleWaveform() {
        let firstFrame = (0..<5).map {
            VoiceActivityAnimation.level(at: 0, offset: Double($0) * 0.7)
        }
        let secondFrame = (0..<5).map {
            VoiceActivityAnimation.level(at: 0.12, offset: Double($0) * 0.7)
        }

        XCTAssertNotEqual(firstFrame, secondFrame)
        XCTAssertGreaterThan(
            zip(firstFrame, secondFrame).map { abs($0 - $1) }.max() ?? 0,
            0.1
        )
    }
}
