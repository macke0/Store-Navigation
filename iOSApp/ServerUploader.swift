//
//  ServerUploader.swift
//  PulsAr
//
//  Bakgrunds-URLSession — upload fortsätter även när skärmen är släckt.
//  Hanterar scan-sessioner och batch-upload till butiksmodellen.
//

import Foundation
import Combine
import UIKit

// ─────────────────────────────────────────────────────────────────
// BACKGROUND UPLOAD MANAGER (singleton)
// ─────────────────────────────────────────────────────────────────
//
// En delad URLSession med `background(withIdentifier:)` som körs
// via iOS nsurlsessiond-daemonen. Uploads fortsätter även när
// appen är suspenderad eller skärmen låst.
//

final class BackgroundUploadManager: NSObject {
    static let shared = BackgroundUploadManager()

    // En identifier per app-installation. Samma identifier över app-omstarter
    // låter iOS koppla tillbaka uppgifter till appen.
    private let sessionIdentifier = "se.pulsar.upload.background"

    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.background(withIdentifier: sessionIdentifier)
        config.sessionSendsLaunchEvents = true
        config.isDiscretionary = false            // vi vill köra direkt, inte vänta på idealt läge
        config.allowsCellularAccess = true
        config.timeoutIntervalForRequest = 60
        config.timeoutIntervalForResource = 3600  // 1h för hela överföringen
        return URLSession(configuration: config, delegate: self, delegateQueue: nil)
    }()

    private let lock = NSLock()

    private struct Pending {
        let continuation: CheckedContinuation<Data, Error>
        var data: Data
        let tempFile: URL
    }
    private var pending: [Int: Pending] = [:]

    // Sätts av AppDelegate när iOS skickar bakgrunds-events.
    var backgroundEventsCompletionHandler: (() -> Void)?

    private override init() { super.init() }

    /// Laddar upp en fil i bakgrunden. Returnerar serverns svar när uppgiften
    /// är klar — även om det är efter att skärmen låsts och lysts upp igen.
    func upload(request: URLRequest, bodyFile: URL) async throws -> Data {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Data, Error>) in
            let task = session.uploadTask(with: request, fromFile: bodyFile)
            lock.lock()
            pending[task.taskIdentifier] = Pending(
                continuation: continuation,
                data: Data(),
                tempFile: bodyFile
            )
            lock.unlock()
            task.resume()
        }
    }
}

extension BackgroundUploadManager: URLSessionDataDelegate {
    func urlSession(_ session: URLSession,
                    dataTask: URLSessionDataTask,
                    didReceive data: Data) {
        lock.lock()
        if var p = pending[dataTask.taskIdentifier] {
            p.data.append(data)
            pending[dataTask.taskIdentifier] = p
        }
        lock.unlock()
    }

    func urlSession(_ session: URLSession,
                    task: URLSessionTask,
                    didCompleteWithError error: Error?) {
        lock.lock()
        let p = pending.removeValue(forKey: task.taskIdentifier)
        lock.unlock()
        guard let p = p else { return }

        // Städa upp temp-filen oavsett utfall
        try? FileManager.default.removeItem(at: p.tempFile)

        if let error = error {
            p.continuation.resume(throwing: error)
            return
        }
        if let http = task.response as? HTTPURLResponse, http.statusCode != 200 {
            p.continuation.resume(throwing: URLError(.badServerResponse))
            return
        }
        p.continuation.resume(returning: p.data)
    }

    func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
        DispatchQueue.main.async {
            self.backgroundEventsCompletionHandler?()
            self.backgroundEventsCompletionHandler = nil
        }
    }
}


// ─────────────────────────────────────────────────────────────────
// SERVER UPLOADER
// ─────────────────────────────────────────────────────────────────

class ServerUploader: ObservableObject {
    @Published var progress:      Double = 0.0
    @Published var laddarUpp:     Bool   = false
    @Published var klart:         Bool   = false
    @Published var felmeddelande: String = ""
    @Published var sessionId:     String = ""
    @Published var sessionStatus: String = ""
    var kartaId: String? = nil

    let serverURL = PulsArConfig.serverURL
    let framesPerBatch = 10

    // ─────────────────────────────────────────────
    // STARTA SESSION
    // ─────────────────────────────────────────────

    func startaSession() async -> String? {
        guard let url = URL(string: "\(serverURL)/scan/start") else { return nil }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 10

        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let sid = json?["session_id"] as? String ?? ""
            await MainActor.run {
                self.sessionId = sid
                self.sessionStatus = "aktiv"
            }
            print("🎬 Session startad: \(sid)")
            return sid
        } catch {
            print("❌ Kunde inte starta session: \(error)")
            return nil
        }
    }

    func fortsättSession(_ sid: String) async -> Bool {
        guard let url = URL(string: "\(serverURL)/scan/resume/\(sid)") else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let status = json?["status"] as? String ?? ""
            if status == "ok" {
                await MainActor.run {
                    self.sessionId = sid
                    self.sessionStatus = "aktiv"
                }
                print("▶️ Session återupptagen: \(sid)")
                return true
            }
        } catch {
            print("❌ Kunde inte fortsätta session: \(error)")
        }
        return false
    }

    func pausaSession() async {
        guard !sessionId.isEmpty else { return }
        guard let url = URL(string: "\(serverURL)/scan/pause/\(sessionId)") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        do {
            _ = try await URLSession.shared.data(for: request)
            await MainActor.run { self.sessionStatus = "pausad" }
            print("⏸️ Session pausad: \(sessionId)")
        } catch {
            print("❌ Kunde inte pausa: \(error)")
        }
    }

    func avslutaSession() async {
        guard !sessionId.isEmpty else { return }
        guard let url = URL(string: "\(serverURL)/scan/stop/\(sessionId)?auto_bygg=true") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let byggerKarta = json?["bygger_karta"] as? Bool ?? false
            await MainActor.run {
                self.sessionStatus = "klar"
                self.klart = true
            }
            if byggerKarta {
                print("✅ Session klar — kartan byggs i bakgrunden")
            } else {
                print("✅ Session klar")
            }
        } catch {
            print("❌ Kunde inte avsluta session: \(error)")
        }
    }

    // ─────────────────────────────────────────────
    // HUVUDFUNKTION — LADDA UPP HELA SKANNINGEN
    // ─────────────────────────────────────────────

    @MainActor
    func laddaUppSkanning3D(videoURL: URL?, arFrames: [[String: Any]], punkter3D punkterIn: [Punkt3D]) async {
        guard !laddarUpp else {
            print("⚠️ Uppladdning pågår redan")
            return
        }
        guard let mapp = videoURL else { return }

        // ── Downsample 3D-punkter innan upload ──────────────────────────────
        // 555k punkter → ~140k. JSON-storleken minskar ~4×, vilket är
        // den enskilt största posten i varje batch. Vi tar var 4:e punkt
        // (deterministisk stride — håller frame-fördelningen jämn).
        let punkterFaktor = 4
        let punkter3D: [Punkt3D]
        if punkterIn.count > 50_000 && punkterFaktor > 1 {
            punkter3D = stride(from: 0, to: punkterIn.count, by: punkterFaktor).map { punkterIn[$0] }
            print("📉 Downsamplade 3D-punkter: \(punkterIn.count) → \(punkter3D.count) (var \(punkterFaktor):e)")
        } else {
            punkter3D = punkterIn
        }

        laddarUpp     = true
        progress      = 0.0
        felmeddelande = ""
        klart         = false

        // Hindra skärmen från att släckas under upload — vi använder
        // bakgrundssession, så det är inte strikt nödvändigt, men det
        // håller användargränssnittet levande för statusuppdateringar.
        UIApplication.shared.isIdleTimerDisabled = true
        defer {
            UIApplication.shared.isIdleTimerDisabled = false
        }

        do {
            // Starta session om vi inte har en
            if sessionId.isEmpty {
                guard let sid = await startaSession() else {
                    felmeddelande = "Kunde inte starta session på servern"
                    laddarUpp = false
                    return
                }
                sessionId = sid
            }

            // Samla bilder
            let filer = try FileManager.default.contentsOfDirectory(
                at: mapp, includingPropertiesForKeys: nil)
                .filter { $0.pathExtension == "jpg" }
                .sorted { $0.lastPathComponent < $1.lastPathComponent }

            let totalFrames = filer.count
            print("📤 Förbereder uppladdning: \(totalFrames) bilder, \(punkter3D.count) 3D-punkter")

            let frameBatches = stride(from: 0, to: totalFrames, by: framesPerBatch).map { i in
                Array(filer[i..<min(i + framesPerBatch, totalFrames)])
            }
            let totalBatches = frameBatches.count
            print("📦 Delar upp i \(totalBatches) batches (session: \(sessionId))")

            for (batchIndex, batchFiler) in frameBatches.enumerated() {
                let startFrame = batchIndex * framesPerBatch
                let endFrame   = min(startFrame + framesPerBatch, totalFrames)
                let batchPositioner = Array(arFrames[startFrame..<min(endFrame, arFrames.count)])
                let batchPunkter = punkter3D.filter { p in
                    p.frame >= startFrame && p.frame < endFrame
                }

                try await skickaBatch(
                    batchIndex:   batchIndex,
                    totalBatches: totalBatches,
                    filer:        batchFiler,
                    positioner:   batchPositioner,
                    punkter:      batchPunkter,
                    isLast:       batchIndex == totalBatches - 1
                )

                // Ta bort uppladdade frames
                for fil in batchFiler {
                    try? FileManager.default.removeItem(at: fil)
                }
                progress = Double(batchIndex + 1) / Double(totalBatches)
            }

            await avslutaSession()

            progress  = 1.0
            laddarUpp = false
            klart     = true

            URLCache.shared.removeAllCachedResponses()
            try? FileManager.default.removeItem(at: mapp)

            print("✅ Uppladdning klar!")

        } catch let error as URLError where error.code == .timedOut {
            laddarUpp     = false
            felmeddelande = "Uppladdningen tog för lång tid."
        } catch let error as URLError where error.code == .cannotConnectToHost || error.code == .notConnectedToInternet {
            laddarUpp     = false
            felmeddelande = "Kan inte nå servern."
        } catch {
            laddarUpp     = false
            felmeddelande = "Uppladdning misslyckades: \(error.localizedDescription)"
        }
    }

    // ─────────────────────────────────────────────
    // SKICKA EN BATCH (via bakgrundssession)
    // ─────────────────────────────────────────────

    private func skickaBatch(
        batchIndex:   Int,
        totalBatches: Int,
        filer:        [URL],
        positioner:   [[String: Any]],
        punkter:      [Punkt3D],
        isLast:       Bool
    ) async throws {

        let boundary = UUID().uuidString

        // ─── Bygg multipart-kropp i en temp-fil (bakgrundssessioner
        //     kräver att kroppen finns på disk — kan inte använda httpBody)

        let tempFile = FileManager.default.temporaryDirectory
            .appendingPathComponent("batch_\(sessionId)_\(batchIndex)_\(UUID().uuidString).tmp")
        FileManager.default.createFile(atPath: tempFile.path, contents: nil)
        let handle = try FileHandle(forWritingTo: tempFile)
        defer { try? handle.close() }

        func writeString(_ s: String) throws {
            try handle.write(contentsOf: Data(s.utf8))
        }

        // session_id
        try writeString("--\(boundary)\r\n")
        try writeString("Content-Disposition: form-data; name=\"session_id\"\r\n\r\n")
        try writeString("\(sessionId)\r\n")

        // batch_index
        try writeString("--\(boundary)\r\n")
        try writeString("Content-Disposition: form-data; name=\"batch_index\"\r\n\r\n")
        try writeString("\(batchIndex)\r\n")

        // total_batches
        try writeString("--\(boundary)\r\n")
        try writeString("Content-Disposition: form-data; name=\"total_batches\"\r\n\r\n")
        try writeString("\(totalBatches)\r\n")

        // is_last
        try writeString("--\(boundary)\r\n")
        try writeString("Content-Disposition: form-data; name=\"is_last\"\r\n\r\n")
        try writeString("\(isLast)\r\n")
        
        // karta_id (om satt)
        if let kartaId = kartaId, !kartaId.isEmpty {
            try writeString("--\(boundary)\r\n")
            try writeString("Content-Disposition: form-data; name=\"karta_id\"\r\n\r\n")
            try writeString("\(kartaId)\r\n")
        }

        // Frames (strömmade från disk — aldrig helt i minne)
        for fil in filer {
            try writeString("--\(boundary)\r\n")
            try writeString("Content-Disposition: form-data; name=\"frames\"; filename=\"\(fil.lastPathComponent)\"\r\n")
            try writeString("Content-Type: image/jpeg\r\n\r\n")
            let frameHandle = try FileHandle(forReadingFrom: fil)
            while true {
                let chunk = try frameHandle.read(upToCount: 65_536) ?? Data()
                if chunk.isEmpty { break }
                try handle.write(contentsOf: chunk)
            }
            try frameHandle.close()
            try writeString("\r\n")
        }
        
        // Mesh-filer (skickas bara i sista batchen för enkelhet)
        if isLast {
            // Hitta mesh-mappen
            if let firstFrame = filer.first {
                let skanningsmapp = firstFrame.deletingLastPathComponent()

                // .bin-filer är redundanta nu när mesh.glb skickas direkt — droppade för
                // att korta upload. Sätt true för att aktivera igen.
                let skickaBinFiler = false
                if skickaBinFiler {
                    let meshMapp = skanningsmapp.appendingPathComponent("mesh")
                    if FileManager.default.fileExists(atPath: meshMapp.path) {
                        let meshFiler = (try? FileManager.default.contentsOfDirectory(at: meshMapp, includingPropertiesForKeys: nil)) ?? []
                        let binFiler = meshFiler.filter { $0.pathExtension == "bin" }

                        print("📦 Skickar \(binFiler.count) mesh-anchors")

                        for meshFil in binFiler {
                            try writeString("--\(boundary)\r\n")
                            try writeString("Content-Disposition: form-data; name=\"mesh\"; filename=\"\(meshFil.lastPathComponent)\"\r\n")
                            try writeString("Content-Type: application/octet-stream\r\n\r\n")
                            let meshHandle = try FileHandle(forReadingFrom: meshFil)
                            while true {
                                let chunk = try meshHandle.read(upToCount: 65_536) ?? Data()
                                if chunk.isEmpty { break }
                                try handle.write(contentsOf: chunk)
                            }
                            try meshHandle.close()
                            try writeString("\r\n")
                        }
                    }
                }

                // mesh_status.txt — diagnostik från MeshExporter (skickas till servern
                // så vi kan se i serverloggen om mesh.glb skapades eller misslyckades)
                let statusFil = skanningsmapp.appendingPathComponent("mesh_status.txt")
                if let statusStr = try? String(contentsOf: statusFil, encoding: .utf8) {
                    try writeString("--\(boundary)\r\n")
                    try writeString("Content-Disposition: form-data; name=\"mesh_status\"\r\n\r\n")
                    try writeString("\(statusStr)\r\n")
                } else {
                    try writeString("--\(boundary)\r\n")
                    try writeString("Content-Disposition: form-data; name=\"mesh_status\"\r\n\r\n")
                    try writeString("(saknas — stoppaSpelaIn kördes inte?)\r\n")
                }

                // mesh.glb — färdig LiDAR-mesh från MeshExporter, kan visas direkt i /viewer/3d
                let glbFil = skanningsmapp.appendingPathComponent("mesh.glb")
                if FileManager.default.fileExists(atPath: glbFil.path) {
                    let storlek = (try? FileManager.default.attributesOfItem(atPath: glbFil.path)[.size] as? Int) ?? 0
                    print("📦 Skickar mesh.glb (\(storlek / 1024) KB)")

                    try writeString("--\(boundary)\r\n")
                    try writeString("Content-Disposition: form-data; name=\"mesh_glb\"; filename=\"mesh.glb\"\r\n")
                    try writeString("Content-Type: model/gltf-binary\r\n\r\n")
                    let glbHandle = try FileHandle(forReadingFrom: glbFil)
                    while true {
                        let chunk = try glbHandle.read(upToCount: 65_536) ?? Data()
                        if chunk.isEmpty { break }
                        try handle.write(contentsOf: chunk)
                    }
                    try glbHandle.close()
                    try writeString("\r\n")
                }
            }
        }

        // Positioner
        let posJSON = try JSONSerialization.data(withJSONObject: positioner)
        try writeString("--\(boundary)\r\n")
        try writeString("Content-Disposition: form-data; name=\"positioner\"\r\n\r\n")
        try handle.write(contentsOf: posJSON)
        try writeString("\r\n")

        // 3D-punkter
        let punkterData: [[String: Any]] = punkter.map { p in
            ["x": p.x, "y": p.y, "z": p.z,
             "u": p.u, "v": p.v,
             "frame": p.frame,
             "confidence": p.confidence]
        }
        let punkterJSON = try JSONSerialization.data(withJSONObject: punkterData)
        try writeString("--\(boundary)\r\n")
        try writeString("Content-Disposition: form-data; name=\"punkter_3d\"\r\n\r\n")
        try handle.write(contentsOf: punkterJSON)
        try writeString("\r\n")

        // Slut-boundary
        try writeString("--\(boundary)--\r\n")
        try handle.close()

        // ─── Skicka via bakgrundssession

        var request = URLRequest(url: URL(string: "\(serverURL)/scan/upload")!)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        print("📤 Batch \(batchIndex + 1)/\(totalBatches): skickar...")
        let responseData = try await BackgroundUploadManager.shared.upload(
            request: request,
            bodyFile: tempFile
        )

        if let str = String(data: responseData, encoding: .utf8) {
            print("   📥 Svar: \(str.prefix(120))")
        }
    }

    // ─────────────────────────────────────────────
    // HÄMTA SESSIONER
    // ─────────────────────────────────────────────

    func hämtaSessioner() async -> [[String: Any]] {
        guard let url = URL(string: "\(serverURL)/scan/sessioner") else { return [] }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            return json?["sessioner"] as? [[String: Any]] ?? []
        } catch {
            return []
        }
    }

    // ─────────────────────────────────────────────
    // BAKÅTKOMPATIBEL
    // ─────────────────────────────────────────────

    @MainActor
    func laddaUppSkanning(videoURL: URL?, arFrames: [[String: Any]]) async {
        await laddaUppSkanning3D(videoURL: videoURL, arFrames: arFrames, punkter3D: [])
    }
}
