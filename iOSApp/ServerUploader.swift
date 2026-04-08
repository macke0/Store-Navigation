//
//  ServerUploader.swift
//  PulsAr
//
//  Laddar upp skanningsdata inkl 3D-punktmoln till server
//  Använder batch-uppladdning för stora skanningar
//

import Foundation
import Combine

class ServerUploader: ObservableObject {
    @Published var progress:      Double = 0.0
    @Published var laddarUpp:     Bool   = false
    @Published var klart:         Bool   = false
    @Published var felmeddelande: String = ""

    let serverURL = "http://192.168.0.166:8000"
    
    // Batch-inställningar
    let framesPerBatch = 3
    let punkterPerBatch = 10000

    // ─────────────────────────────────────────────
    // LADDA UPP MED 3D-PUNKTER (BATCH)
    // ─────────────────────────────────────────────
    
    @MainActor
    func laddaUppSkanning3D(videoURL: URL?, arFrames: [[String: Any]], punkter3D: [Punkt3D]) async {
        guard !laddarUpp else {
            print("⚠️ Uppladdning pågår redan")
            return
        }
        guard let mapp = videoURL else { return }
        
        laddarUpp     = true
        progress      = 0.0
        felmeddelande = ""
        klart         = false

        do {
            // Samla bilder
            let filer = try FileManager.default.contentsOfDirectory(
                at: mapp, includingPropertiesForKeys: nil)
                .filter { $0.pathExtension == "jpg" }
                .sorted { $0.lastPathComponent < $1.lastPathComponent }
            
            let totalFrames = filer.count
            let totalPunkter = punkter3D.count
            
            print("📤 Förbereder uppladdning: \(totalFrames) bilder, \(totalPunkter) 3D-punkter")
            
            // Beräkna antal batches
            let frameBatches = stride(from: 0, to: totalFrames, by: framesPerBatch).map { i in
                Array(filer[i..<min(i + framesPerBatch, totalFrames)])
            }
            
            let totalBatches = frameBatches.count
            print("📦 Delar upp i \(totalBatches) batches")
            
            // Generera skanning-ID
            let skanningId = "skanning_\(Int(Date().timeIntervalSince1970))"
            
            // Skicka varje batch
            for (batchIndex, batchFiler) in frameBatches.enumerated() {
                let isFirst = batchIndex == 0
                let isLast = batchIndex == totalBatches - 1
                
                // Räkna ut vilka frames som ingår i denna batch
                let startFrame = batchIndex * framesPerBatch
                let endFrame = min(startFrame + framesPerBatch, totalFrames)
                
                // Filtrera positioner för denna batch
                let batchPositioner = Array(arFrames[startFrame..<min(endFrame, arFrames.count)])
                
                // Filtrera 3D-punkter för denna batch (baserat på frame-index)
                let batchPunkter = punkter3D.filter { p in
                    p.frame >= startFrame && p.frame < endFrame
                }
                
                print("📤 Batch \(batchIndex + 1)/\(totalBatches): \(batchFiler.count) frames, \(batchPunkter.count) punkter")
                
                try await skickaBatch(
                    skanningId: skanningId,
                    batchIndex: batchIndex,
                    totalBatches: totalBatches,
                    filer: batchFiler,
                    positioner: batchPositioner,
                    punkter: batchPunkter,
                    isFirst: isFirst,
                    isLast: isLast
                )
                
                // Uppdatera progress
                progress = Double(batchIndex + 1) / Double(totalBatches)
            }

            progress  = 1.0
            laddarUpp = false
            klart     = true
            
            // Rensa cache för att spara minne
            URLCache.shared.removeAllCachedResponses()
            
            // Radera lokala filer efter uppladdning
            try? FileManager.default.removeItem(at: mapp)
            
            print("✅ Uppladdning klar!")

        } catch {
            laddarUpp     = false
            felmeddelande = "Uppladdning misslyckades: \(error.localizedDescription)"
            print("❌ Fel: \(error)")
        }
    }
    
    // ─────────────────────────────────────────────
    // SKICKA EN BATCH
    // ─────────────────────────────────────────────
    
    private func skickaBatch(
        skanningId: String,
        batchIndex: Int,
        totalBatches: Int,
        filer: [URL],
        positioner: [[String: Any]],
        punkter: [Punkt3D],
        isFirst: Bool,
        isLast: Bool
    ) async throws {
        
        let boundary = UUID().uuidString
        var body = Data()
        
        // Metadata
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"skanning_id\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(skanningId)\r\n".data(using: .utf8)!)
        
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"batch_index\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(batchIndex)\r\n".data(using: .utf8)!)
        
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"total_batches\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(totalBatches)\r\n".data(using: .utf8)!)
        
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"is_last\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(isLast)\r\n".data(using: .utf8)!)

        // Lägg till bilder
        for fil in filer {
            let data = try Data(contentsOf: fil)
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"frames\"; filename=\"\(fil.lastPathComponent)\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
            body.append(data)
            body.append("\r\n".data(using: .utf8)!)
        }

        // Lägg till positioner
        let posJSON = try JSONSerialization.data(withJSONObject: positioner)
        let posString = String(data: posJSON, encoding: .utf8) ?? "[]"
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"positioner\"\r\n\r\n".data(using: .utf8)!)
        body.append(posString.data(using: .utf8)!)
        body.append("\r\n".data(using: .utf8)!)
        
        // Lägg till 3D-punkter
        let punkterData = punkter.map { p -> [String: Any] in
            return [
                "x": p.x, "y": p.y, "z": p.z,
                "u": p.u, "v": p.v,
                "frame": p.frame,
                "confidence": p.confidence
            ]
        }
        let punkterJSON = try JSONSerialization.data(withJSONObject: punkterData)
        let punkterString = String(data: punkterJSON, encoding: .utf8) ?? "[]"
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"punkter_3d\"\r\n\r\n".data(using: .utf8)!)
        body.append(punkterString.data(using: .utf8)!)
        body.append("\r\n".data(using: .utf8)!)
        
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        
        print("   📦 Body size: \(body.count / 1024) KB")

        // Skicka request
        var request = URLRequest(url: URL(string: "\(serverURL)/skanna-video-batch/")!)
        request.httpMethod = "POST"
        request.httpBody   = body
        request.setValue("multipart/form-data; boundary=\(boundary)",
                         forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 120  // 2 min per batch

        let (responseData, response) = try await URLSession.shared.data(for: request)
        
        if let http = response as? HTTPURLResponse {
            if let responseString = String(data: responseData, encoding: .utf8) {
                print("   📥 Svar: \(responseString)")
            }
            
            guard http.statusCode == 200 else {
                throw URLError(.badServerResponse)
            }
        }
    }
    
    // ─────────────────────────────────────────────
    // BAKÅTKOMPATIBEL (utan 3D)
    // ─────────────────────────────────────────────
    
    @MainActor
    func laddaUppSkanning(videoURL: URL?, arFrames: [[String: Any]]) async {
        await laddaUppSkanning3D(videoURL: videoURL, arFrames: arFrames, punkter3D: [])
    }
}
