import CoreGraphics
import CoreImage
import Darwin
import Foundation
import ImageIO
import Vision

private struct AnalyzerRequest: Decodable {
    let schemaVersion: String
    let frames: [FrameInput]
    let subjects: [SubjectInput]

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case frames
        case subjects
    }
}

private struct FrameInput: Decodable {
    let shotID: String
    let frameSha256: String
    let imagePath: String

    private enum CodingKeys: String, CodingKey {
        case shotID = "shot_id"
        case frameSha256 = "frame_sha256"
        case imagePath = "image_path"
    }
}

private struct SubjectInput: Decodable {
    let entityID: String
    let kind: String
    let references: [ReferenceInput]

    private enum CodingKeys: String, CodingKey {
        case entityID = "entity_id"
        case kind
        case references
    }
}

private struct ReferenceInput: Decodable {
    let assetID: String
    let sha256: String
    let imagePath: String

    private enum CodingKeys: String, CodingKey {
        case assetID = "asset_id"
        case sha256
        case imagePath = "image_path"
    }
}

private struct AnalyzerResponse: Encodable {
    let schemaVersion = "nalu.apple-vision-measurements/v1"
    let framework = "Apple Vision"
    let localAnalysis = true
    let shots: [ShotMeasurement]

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case framework
        case localAnalysis = "local_analysis"
        case shots
    }
}

private struct ShotMeasurement: Encodable {
    let shotID: String
    let frameSha256: String
    let subjects: [SubjectMeasurement]

    private enum CodingKeys: String, CodingKey {
        case shotID = "shot_id"
        case frameSha256 = "frame_sha256"
        case subjects
    }
}

private struct SubjectMeasurement: Encodable {
    let entityID: String
    let identityDistance: Double?
    let dominantColor: String
    let colorConfidence: Double
    let spaceAxis: String
    let axisConfidence: Double
    let subjectCenterX: Double?
    let pose: String
    let poseConfidence: Double
    let bodyJointCount: Int
    let propDistances: [String: Double]

    private enum CodingKeys: String, CodingKey {
        case entityID = "entity_id"
        case identityDistance = "identity_distance"
        case dominantColor = "dominant_color"
        case colorConfidence = "color_confidence"
        case spaceAxis = "space_axis"
        case axisConfidence = "axis_confidence"
        case subjectCenterX = "subject_center_x"
        case pose
        case poseConfidence = "pose_confidence"
        case bodyJointCount = "body_joint_count"
        case propDistances = "prop_distances"
    }
}

private enum AnalyzerFailure: Error, CustomStringConvertible {
    case invalidSchema
    case unreadableImage(String)
    case missingFeaturePrint(String)

    var description: String {
        switch self {
        case .invalidSchema:
            "unsupported analyzer request schema"
        case .unreadableImage(let path):
            "could not decode image: \(path)"
        case .missingFeaturePrint(let path):
            "Apple Vision could not create a feature print: \(path)"
        }
    }
}

private struct BodyMeasurement {
    let axis: String
    let axisConfidence: Double
    let centerX: Double?
    let pose: String
    let poseConfidence: Double
    let jointCount: Int
}

private final class PerceptualAnalyzer {
    private let context = CIContext(options: [.cacheIntermediates: false])
    private var referencePrints: [String: VNFeaturePrintObservation] = [:]

    func analyze(_ request: AnalyzerRequest) throws -> AnalyzerResponse {
        guard request.schemaVersion == "nalu.apple-vision-request/v1" else {
            throw AnalyzerFailure.invalidSchema
        }
        let propSubjects = request.subjects.filter { $0.kind == "prop" }
        let characterSubjects = request.subjects.filter { $0.kind == "character" }
        let shots = try request.frames.map { frame in
            let image = try loadImage(frame.imagePath)
            let framePrint = try featurePrint(image, path: frame.imagePath)
            let (color, colorConfidence) = dominantColor(image)
            let body = bodyMeasurement(image)
            let propDistances = try distances(
                framePrint: framePrint,
                subjects: propSubjects
            )
            let subjects = try characterSubjects.map { subject in
                SubjectMeasurement(
                    entityID: subject.entityID,
                    identityDistance: try minimumDistance(
                        framePrint: framePrint,
                        references: subject.references
                    ),
                    dominantColor: color,
                    colorConfidence: colorConfidence,
                    spaceAxis: body.axis,
                    axisConfidence: body.axisConfidence,
                    subjectCenterX: body.centerX,
                    pose: body.pose,
                    poseConfidence: body.poseConfidence,
                    bodyJointCount: body.jointCount,
                    propDistances: propDistances
                )
            }
            return ShotMeasurement(
                shotID: frame.shotID,
                frameSha256: frame.frameSha256,
                subjects: subjects
            )
        }
        return AnalyzerResponse(shots: shots)
    }

    private func loadImage(_ path: String) throws -> CGImage {
        let url = URL(fileURLWithPath: path)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        else {
            throw AnalyzerFailure.unreadableImage(path)
        }
        return image
    }

    private func featurePrint(_ image: CGImage, path: String) throws -> VNFeaturePrintObservation {
        let request = VNGenerateImageFeaturePrintRequest()
        try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
        guard let observation = request.results?.first else {
            throw AnalyzerFailure.missingFeaturePrint(path)
        }
        return observation
    }

    private func referencePrint(_ reference: ReferenceInput) throws -> VNFeaturePrintObservation {
        if let cached = referencePrints[reference.sha256] { return cached }
        let image = try loadImage(reference.imagePath)
        let observation = try featurePrint(image, path: reference.imagePath)
        referencePrints[reference.sha256] = observation
        return observation
    }

    private func minimumDistance(
        framePrint: VNFeaturePrintObservation,
        references: [ReferenceInput]
    ) throws -> Double? {
        var values: [Double] = []
        for reference in references {
            var distance: Float = 0
            try framePrint.computeDistance(&distance, to: referencePrint(reference))
            values.append(Double(distance))
        }
        return values.min()
    }

    private func distances(
        framePrint: VNFeaturePrintObservation,
        subjects: [SubjectInput]
    ) throws -> [String: Double] {
        var result: [String: Double] = [:]
        for subject in subjects {
            if let distance = try minimumDistance(
                framePrint: framePrint,
                references: subject.references
            ) {
                result[subject.entityID] = distance
            }
        }
        return result
    }

    private func dominantColor(_ image: CGImage) -> (String, Double) {
        let input = CIImage(cgImage: image)
        guard let filter = CIFilter(name: "CIAreaAverage") else { return ("unknown", 0) }
        filter.setValue(input, forKey: kCIInputImageKey)
        filter.setValue(CIVector(cgRect: input.extent), forKey: kCIInputExtentKey)
        guard let output = filter.outputImage else { return ("unknown", 0) }
        var rgba = [UInt8](repeating: 0, count: 4)
        context.render(
            output,
            toBitmap: &rgba,
            rowBytes: 4,
            bounds: CGRect(x: 0, y: 0, width: 1, height: 1),
            format: .RGBA8,
            colorSpace: CGColorSpaceCreateDeviceRGB()
        )
        let red = Double(rgba[0]) / 255
        let green = Double(rgba[1]) / 255
        let blue = Double(rgba[2]) / 255
        let maximum = max(red, green, blue)
        let minimum = min(red, green, blue)
        let delta = maximum - minimum
        let saturation = maximum == 0 ? 0 : delta / maximum
        if saturation < 0.12 {
            if maximum > 0.86 { return ("白色", min(1, (maximum - 0.75) * 4)) }
            if maximum < 0.18 { return ("黑色", min(1, (0.30 - maximum) * 4)) }
            return ("灰色", min(1, 1 - saturation))
        }
        let hue: Double
        if maximum == red {
            hue = 60 * (((green - blue) / delta).truncatingRemainder(dividingBy: 6))
        } else if maximum == green {
            hue = 60 * (((blue - red) / delta) + 2)
        } else {
            hue = 60 * (((red - green) / delta) + 4)
        }
        let normalizedHue = hue < 0 ? hue + 360 : hue
        let name: String
        switch normalizedHue {
        case 0..<15, 345...360: name = "红色"
        case 15..<45: name = "橙色"
        case 45..<70: name = "黄色"
        case 70..<165: name = "绿色"
        case 165..<195: name = "青色"
        case 195..<255: name = "蓝色"
        case 255..<300: name = "紫色"
        default: name = "粉色"
        }
        return (name, min(1, saturation * 1.4))
    }

    private func bodyMeasurement(_ image: CGImage) -> BodyMeasurement {
        let poseRequest = VNDetectHumanBodyPoseRequest()
        let faceRequest = VNDetectFaceRectanglesRequest()
        let saliencyRequest = VNGenerateAttentionBasedSaliencyImageRequest()
        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        try? handler.perform([poseRequest, faceRequest, saliencyRequest])

        if let pose = poseRequest.results?.first,
           let points = try? pose.recognizedPoints(.all)
        {
            let trusted = points.values.filter { $0.confidence >= 0.2 }
            if trusted.count >= 4 {
                let center = trusted.map { Double($0.location.x) }.reduce(0, +)
                    / Double(trusted.count)
                let confidence = trusted.map { Double($0.confidence) }.reduce(0, +)
                    / Double(trusted.count)
                let classified = classifyPose(points)
                return BodyMeasurement(
                    axis: axis(center),
                    axisConfidence: confidence,
                    centerX: center,
                    pose: classified.0,
                    poseConfidence: classified.1,
                    jointCount: trusted.count
                )
            }
        }
        if let face = faceRequest.results?.max(by: {
            $0.boundingBox.width * $0.boundingBox.height
                < $1.boundingBox.width * $1.boundingBox.height
        }) {
            let center = Double(face.boundingBox.midX)
            return BodyMeasurement(
                axis: axis(center),
                axisConfidence: Double(face.confidence),
                centerX: center,
                pose: "unknown",
                poseConfidence: 0,
                jointCount: 0
            )
        }
        if let salient = saliencyRequest.results?.first?.salientObjects?.max(by: {
            $0.boundingBox.width * $0.boundingBox.height
                < $1.boundingBox.width * $1.boundingBox.height
        }) {
            let center = Double(salient.boundingBox.midX)
            return BodyMeasurement(
                axis: axis(center),
                axisConfidence: Double(salient.confidence),
                centerX: center,
                pose: "unknown",
                poseConfidence: 0,
                jointCount: 0
            )
        }
        return BodyMeasurement(
            axis: "unknown",
            axisConfidence: 0,
            centerX: nil,
            pose: "unknown",
            poseConfidence: 0,
            jointCount: 0
        )
    }

    private func axis(_ centerX: Double) -> String {
        if centerX < 0.40 { return "screen-left" }
        if centerX > 0.60 { return "screen-right" }
        return "center"
    }

    private func classifyPose(
        _ points: [VNHumanBodyPoseObservation.JointName: VNRecognizedPoint]
    ) -> (String, Double) {
        let names: [VNHumanBodyPoseObservation.JointName] = [
            .leftShoulder, .rightShoulder, .leftHip, .rightHip,
            .leftKnee, .rightKnee, .leftAnkle, .rightAnkle,
        ]
        let trusted = names.compactMap { name -> VNRecognizedPoint? in
            guard let point = points[name], point.confidence >= 0.2 else { return nil }
            return point
        }
        guard trusted.count >= 5 else { return ("unknown", 0) }
        let xs = trusted.map { Double($0.location.x) }
        let ys = trusted.map { Double($0.location.y) }
        let confidence = trusted.map { Double($0.confidence) }.reduce(0, +)
            / Double(trusted.count)
        let horizontalSpan = (xs.max() ?? 0) - (xs.min() ?? 0)
        let verticalSpan = (ys.max() ?? 0) - (ys.min() ?? 0)
        if horizontalSpan > verticalSpan * 1.25 { return ("lying", confidence) }

        let hips: [VNRecognizedPoint] = [
            VNHumanBodyPoseObservation.JointName.leftHip,
            VNHumanBodyPoseObservation.JointName.rightHip,
        ].compactMap { points[$0] }.filter { $0.confidence >= 0.2 }
        let knees: [VNRecognizedPoint] = [
            VNHumanBodyPoseObservation.JointName.leftKnee,
            VNHumanBodyPoseObservation.JointName.rightKnee,
        ].compactMap { points[$0] }.filter {
            $0.confidence >= 0.2
        }
        let ankles: [VNRecognizedPoint] = [
            VNHumanBodyPoseObservation.JointName.leftAnkle,
            VNHumanBodyPoseObservation.JointName.rightAnkle,
        ].compactMap { points[$0] }.filter {
            $0.confidence >= 0.2
        }
        guard !hips.isEmpty, !knees.isEmpty, !ankles.isEmpty else {
            return ("unknown", confidence * 0.7)
        }
        let mean: ([VNRecognizedPoint], KeyPath<CGPoint, CGFloat>) -> Double = { values, key in
            values.map { Double($0.location[keyPath: key]) }.reduce(0, +) / Double(values.count)
        }
        let hipY = mean(hips, \.y)
        let kneeY = mean(knees, \.y)
        let ankleY = mean(ankles, \.y)
        let ankleXSpan = ankles.count > 1
            ? abs(Double(ankles[0].location.x - ankles[1].location.x)) : 0
        if abs(hipY - kneeY) < 0.14, kneeY > ankleY + 0.08 {
            return ("sitting", confidence)
        }
        if abs(kneeY - ankleY) < 0.11 { return ("kneeling", confidence) }
        if ankleXSpan > 0.18 { return ("walking", confidence * 0.9) }
        return ("standing", confidence)
    }
}

@main
private enum NaluVisualAnalyzerMain {
    static func main() {
        do {
            let input = FileHandle.standardInput.readDataToEndOfFile()
            let decoder = JSONDecoder()
            let request = try decoder.decode(AnalyzerRequest.self, from: input)
            let response = try PerceptualAnalyzer().analyze(request)
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            FileHandle.standardOutput.write(try encoder.encode(response))
        } catch {
            FileHandle.standardError.write(Data("\(error)\n".utf8))
            exit(1)
        }
    }
}
