import Foundation
import Vision
import ImageIO

// Local macOS OCR helper. Receives one image path and emits JSON word data.
guard CommandLine.arguments.count == 2 else { exit(2) }
let url = URL(fileURLWithPath: CommandLine.arguments[1])
do {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    let supported = try request.supportedRecognitionLanguages()
    request.recognitionLanguages = ["zh-Hant", "en-US"].filter { supported.contains($0) }
    try VNImageRequestHandler(url: url).perform([request])
    let observations = (request.results ?? []).sorted {
        if abs($0.boundingBox.midY - $1.boundingBox.midY) > 0.03 {
            return $0.boundingBox.midY > $1.boundingBox.midY
        }
        return $0.boundingBox.minX < $1.boundingBox.minX
    }
    let candidates = observations.compactMap { $0.topCandidates(1).first }
    let result: [String: Any] = ["text": candidates.map { $0.string }, "conf": candidates.map { Double($0.confidence) * 100 }, "engine": "apple_vision"]
    let data = try JSONSerialization.data(withJSONObject: result)
    FileHandle.standardOutput.write(data)
} catch {
    FileHandle.standardError.write(Data(String(describing: error).utf8))
    exit(1)
}
