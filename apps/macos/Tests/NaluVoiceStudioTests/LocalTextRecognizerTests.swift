import AppKit
import XCTest
@testable import NaluVoiceStudio

final class LocalTextRecognizerTests: XCTestCase {
    func testMalformedImageReturnsEmptyDraft() async {
        let result = await LocalTextRecognizer.recognize(in: Data("not an image".utf8))
        XCTAssertEqual(result, "")
    }

    @MainActor
    func testPrintedFixtureIsRecognizedOnDevice() async throws {
        let image = NSImage(size: NSSize(width: 1400, height: 260))
        image.lockFocus()
        NSColor.white.setFill()
        NSRect(x: 0, y: 0, width: 1400, height: 260).fill()
        ("NALU LOCAL OCR 1982" as NSString).draw(
            at: NSPoint(x: 60, y: 100),
            withAttributes: [.font: NSFont.systemFont(ofSize: 72), .foregroundColor: NSColor.black]
        )
        image.unlockFocus()
        let tiff = try XCTUnwrap(image.tiffRepresentation)
        let bitmap = try XCTUnwrap(NSBitmapImageRep(data: tiff))
        let png = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
        let result = await LocalTextRecognizer.recognize(in: png).uppercased()
        XCTAssertTrue(result.contains("NALU"), result)
        XCTAssertTrue(result.contains("1982"), result)
    }
}
