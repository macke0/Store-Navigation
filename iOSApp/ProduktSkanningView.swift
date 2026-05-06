//
//  ProduktSkanningView.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-05-03.
//


//
//  ProduktSkanningView.swift
//  PulsAr
//
//  Läge 2: Skanna produkter mot en redan byggd karta.
//
//  Flöde:
//   1. Användaren startar vyn → ARKit-session startar
//   2. Användaren trycker "Lokalisera" → backend kör VPS och svarar med
//      T_arkit→karta (16 floats). Vi sparar den och håller den konstant.
//   3. Användaren trycker "Starta skanning" → vi skickar varje 0.5s
//      en frame + LiDAR-punkter + cameraTransform + intrinsics +
//      T_arkit→karta till /produkter/skanna_frame/
//   4. Backend kör A1, sparar i kartans identifierade_produkter.json
//

import SwiftUI
import ARKit
import Combine
import Accelerate

private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)

// ─────────────────────────────────────────────────────────────────
// HUVUDVY
// ─────────────────────────────────────────────────────────────────

struct ProduktSkanningView: View {
    let kartaNamn: String

    @StateObject private var manager = ProduktSkanningManager()
    @Environment(\.dismiss) var dismiss

    init(kartaNamn: String = "hela_butiken") {
        self.kartaNamn = kartaNamn
    }

    var body: some View {
        ZStack {
            // AR-kamera i bakgrunden
            ProduktSkanningKameraVy(manager: manager)
                .ignoresSafeArea()

            VStack {
                statusBar
                Spacer()

                if !manager.senastTräffar.isEmpty {
                    träffPanel
                }

                kontrollPanel
            }
            .padding()
        }
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button("Stäng") {
                    manager.stoppaAllt()
                    dismiss()
                }
                .foregroundColor(.white)
            }
        }
        .onAppear { manager.kartaNamn = kartaNamn }
        .onDisappear { manager.stoppaAllt() }
    }

    // ─────────────────────────────────────────────
    // STATUSBAR
    // ─────────────────────────────────────────────

    private var statusBar: some View {
        HStack {
            HStack(spacing: 6) {
                Circle()
                    .fill(statusFärg)
                    .frame(width: 10, height: 10)
                Text(manager.statusText)
                    .font(.caption)
                    .foregroundColor(.white)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.ultraThinMaterial)
            .cornerRadius(20)

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text("\(manager.antalFrames) frames")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.white)
                Text("\(manager.antalProdukter) produkter")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.cyan)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.ultraThinMaterial)
            .cornerRadius(20)
        }
    }

    private var statusFärg: Color {
        if manager.skannar { return .red }
        if manager.lokaliserad { return .green }
        return .orange
    }

    // ─────────────────────────────────────────────
    // TRÄFFPANEL — senaste hittade produkter
    // ─────────────────────────────────────────────

    private var träffPanel: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Senast hittade")
                .font(.caption)
                .foregroundColor(.secondary)
            ForEach(manager.senastTräffar.prefix(3)) { t in
                HStack {
                    Text(t.namn)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white)
                        .lineLimit(1)
                    Spacer()
                    Text("(\(String(format: "%.1f", t.x)), \(String(format: "%.1f", t.z)))")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(.white.opacity(0.6))
                    Text(t.metod)
                        .font(.system(size: 10))
                        .foregroundColor(metodFärg(t.metod))
                }
            }
        }
        .padding()
        .background(.ultraThinMaterial)
        .cornerRadius(12)
    }

    private func metodFärg(_ metod: String) -> Color {
        if metod.starts(with: "bbox") { return .green }
        return .orange
    }

    // ─────────────────────────────────────────────
    // KONTROLLPANEL
    // ─────────────────────────────────────────────

    private var kontrollPanel: some View {
        VStack(spacing: 12) {
            Text(instruktion)
                .font(.caption)
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            HStack(spacing: 16) {
                if !manager.lokaliserad {
                    // Lokalisera-knapp
                    Button(action: { manager.lokalisera() }) {
                        VStack(spacing: 4) {
                            Image(systemName: manager.lokaliserar ? "hourglass" : "location.viewfinder")
                                .font(.title2)
                            Text(manager.lokaliserar ? "Söker..." : "Lokalisera")
                                .font(.caption)
                        }
                        .foregroundColor(.white)
                        .frame(width: 100, height: 70)
                        .background(manager.lokaliserar ? Color.gray : Color.blue)
                        .cornerRadius(12)
                    }
                    .disabled(manager.lokaliserar)
                } else if !manager.skannar {
                    // Starta-skanning-knapp
                    Button(action: { manager.startaSkanning() }) {
                        VStack(spacing: 4) {
                            Image(systemName: "play.circle.fill")
                                .font(.title2)
                            Text("Starta")
                                .font(.caption)
                        }
                        .foregroundColor(.white)
                        .frame(width: 100, height: 70)
                        .background(icaRöd)
                        .cornerRadius(12)
                    }

                    // Lokalisera-om-knapp
                    Button(action: { manager.lokalisera() }) {
                        VStack(spacing: 4) {
                            Image(systemName: "arrow.clockwise")
                                .font(.title2)
                            Text("Lokalisera om")
                                .font(.caption)
                        }
                        .foregroundColor(.white)
                        .frame(width: 100, height: 70)
                        .background(Color.blue.opacity(0.7))
                        .cornerRadius(12)
                    }
                } else {
                    // Stoppa-knapp
                    Button(action: { manager.stoppaSkanning() }) {
                        VStack(spacing: 4) {
                            Image(systemName: "stop.circle.fill")
                                .font(.title2)
                            Text("Stoppa")
                                .font(.caption)
                        }
                        .foregroundColor(.white)
                        .frame(width: 100, height: 70)
                        .background(Color.gray)
                        .cornerRadius(12)
                    }
                }
            }
        }
        .padding()
        .background(.ultraThinMaterial)
        .cornerRadius(16)
    }

    private var instruktion: String {
        if manager.skannar {
            return "Filma hyllorna långsamt. En frame skickas var 0.5 sek."
        }
        if manager.lokaliserad {
            return "Lokaliserad i kartan ✓ — tryck Starta för att skanna produkter."
        }
        if manager.lokaliserar {
            return "Lokaliserar mot kartan…"
        }
        return "Stå mitt i en gång du skannat och tryck Lokalisera."
    }
}

// ─────────────────────────────────────────────────────────────────
// MANAGER
// ─────────────────────────────────────────────────────────────────

class ProduktSkanningManager: NSObject, ObservableObject, ARSessionDelegate {
    private var session: ARSession?

    @Published var statusText = "Startar AR…"
    @Published var lokaliserar = false
    @Published var lokaliserad = false
    @Published var skannar = false
    @Published var antalFrames = 0
    @Published var antalProdukter = 0
    @Published var senastTräffar: [Träff] = []

    var kartaNamn: String = "hela_butiken"

    /// T_arkit → karta (4x4), column-major flat (samma format backend förväntar)
    private var transformArkitTillKarta: [Float]?

    /// Timer för 0.5s-intervall
    private var skanningsTimer: Timer?

    /// Sista ramen att skicka
    private var senasteFrame: ARFrame?

    private let serverURL = PulsArConfig.serverURL
    private let frameKö = DispatchQueue(label: "produkt-skanning-frame", qos: .userInitiated)
    private var skickarFrame = false

    // ─────────────────────────────────────────────
    // AR SESSION
    // ─────────────────────────────────────────────

    func startaARSession(_ session: ARSession) {
        self.session = session
        session.delegate = self

        let config = ARWorldTrackingConfiguration()
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            config.frameSemantics = [.sceneDepth, .smoothedSceneDepth]
        }
        session.run(config, options: [.resetTracking, .removeExistingAnchors])

        DispatchQueue.main.async {
            self.statusText = "Redo — tryck Lokalisera"
        }
    }

    func stoppaAllt() {
        skanningsTimer?.invalidate()
        skanningsTimer = nil
        session?.pause()
        session = nil
    }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        senasteFrame = frame
    }

    // ─────────────────────────────────────────────
    // LOKALISERING
    // ─────────────────────────────────────────────

    func lokalisera() {
        guard let frame = senasteFrame ?? session?.currentFrame else {
            statusText = "Ingen AR-frame ännu"
            return
        }
        lokaliserar = true
        statusText = "Lokaliserar…"

        // Snapshot av cameraTransform vid bildtagning
        let t = frame.camera.transform
        let transformArr: [Float] = [
            t.columns.0.x, t.columns.0.y, t.columns.0.z, t.columns.0.w,
            t.columns.1.x, t.columns.1.y, t.columns.1.z, t.columns.1.w,
            t.columns.2.x, t.columns.2.y, t.columns.2.z, t.columns.2.w,
            t.columns.3.x, t.columns.3.y, t.columns.3.z, t.columns.3.w
        ]

        // Konvertera frame till JPEG (samma orientering som butikskanning sparar)
        let pixelBuffer = frame.capturedImage
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent),
              let bildData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.85) else {
            DispatchQueue.main.async {
                self.lokaliserar = false
                self.statusText = "Kunde inte ta bild"
            }
            return
        }

        Task { await skickaLokaliseringsförfrågan(bildData: bildData,
                                                  arkitTransform: transformArr) }
    }

    private func skickaLokaliseringsförfrågan(bildData: Data,
                                              arkitTransform: [Float]) async {
        guard let url = URL(string: "\(serverURL)/produkter/lokalisera_för_skanning/") else {
            return
        }

        let boundary = UUID().uuidString
        var body = Data()

        func appendField(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }

        // Bild
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"bild\"; filename=\"frame.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(bildData)
        body.append("\r\n".data(using: .utf8)!)

        // Form-fält
        appendField("karta", kartaNamn)
        if let arkitJSON = try? JSONSerialization.data(withJSONObject: arkitTransform),
           let str = String(data: arkitJSON, encoding: .utf8) {
            appendField("arkit_transform", str)
        }

        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.httpBody = body
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 15

        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let hittad = json?["hittad"] as? Bool ?? false

            if hittad, let flat = json?["T_arkit_till_karta"] as? [Any] {
                let floats = flat.compactMap { ($0 as? NSNumber)?.floatValue }
                if floats.count == 16 {
                    let konfidens = json?["konfidens"] as? String ?? "okänd"
                    await MainActor.run {
                        self.transformArkitTillKarta = floats
                        self.lokaliserad = true
                        self.lokaliserar = false
                        self.statusText = "Lokaliserad (konf: \(konfidens))"
                    }
                    return
                }
            }

            await MainActor.run {
                self.lokaliserar = false
                self.lokaliserad = false
                let anledning = json?["anledning"] as? String ?? "ingen träff"
                self.statusText = "Lokalisering misslyckades: \(anledning)"
            }
        } catch {
            await MainActor.run {
                self.lokaliserar = false
                self.statusText = "Nätverksfel: \(error.localizedDescription)"
            }
        }
    }

    // ─────────────────────────────────────────────
    // SKANNING (0.5s timer)
    // ─────────────────────────────────────────────

    func startaSkanning() {
        guard lokaliserad, transformArkitTillKarta != nil else {
            statusText = "Lokalisera först"
            return
        }
        skannar = true
        statusText = "Skannar produkter…"
        antalFrames = 0
        senastTräffar = []

        skanningsTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            self?.skickaNästaFrame()
        }
    }

    func stoppaSkanning() {
        skanningsTimer?.invalidate()
        skanningsTimer = nil
        skannar = false
        statusText = "Pausad — \(antalProdukter) produkter sparade"
    }

    private func skickaNästaFrame() {
        guard !skickarFrame else { return }   // hoppa över om förra inte hunnit
        guard let frame = senasteFrame ?? session?.currentFrame else { return }
        guard let t_ak = transformArkitTillKarta else { return }

        skickarFrame = true

        // Kameratransform
        let t = frame.camera.transform
        let transformArr: [Float] = [
            t.columns.0.x, t.columns.0.y, t.columns.0.z, t.columns.0.w,
            t.columns.1.x, t.columns.1.y, t.columns.1.z, t.columns.1.w,
            t.columns.2.x, t.columns.2.y, t.columns.2.z, t.columns.2.w,
            t.columns.3.x, t.columns.3.y, t.columns.3.z, t.columns.3.w
        ]

        // Intrinsics → portrait (samma konvertering som ButikSkanning)
        let intrinsics = frame.camera.intrinsics
        let fx_L = intrinsics[0][0], fy_L = intrinsics[1][1]
        let cx_L = intrinsics[2][0], cy_L = intrinsics[2][1]
        let imageW_L = Float(CVPixelBufferGetWidth(frame.capturedImage))
        let imageH_L = Float(CVPixelBufferGetHeight(frame.capturedImage))
        let fx_P = fy_L
        let fy_P = fx_L
        let cx_P = imageH_L - cy_L
        let cy_P = cx_L

        let intrJSON: [String: Float] = ["fx": fx_P, "fy": fy_P, "cx": cx_P, "cy": cy_P]
        let dimsJSON: [String: Float] = ["image_width": imageH_L, "image_height": imageW_L]

        // LiDAR-punkter (ARKit-world) — samma sampling som ButikSkanning men förenklad
        let punkter = extrahera3DPunkter(frame: frame, fx: fx_L, fy: fy_L, cx: cx_L, cy: cy_L)

        // Bild
        let pixelBuffer = frame.capturedImage
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent),
              let bildData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.8) else {
            skickarFrame = false
            return
        }

        let frameId = antalFrames + 1

        Task {
            await skickaSkanningsFrame(
                bildData: bildData,
                transform: transformArr,
                intrinsics: intrJSON,
                imageDims: dimsJSON,
                punkter: punkter,
                t_ak: t_ak,
                frameId: frameId
            )
        }
    }

    private func skickaSkanningsFrame(bildData: Data,
                                      transform: [Float],
                                      intrinsics: [String: Float],
                                      imageDims: [String: Float],
                                      punkter: [[String: Float]],
                                      t_ak: [Float],
                                      frameId: Int) async {
        defer {
            DispatchQueue.main.async { self.skickarFrame = false }
        }

        guard let url = URL(string: "\(serverURL)/produkter/skanna_frame/") else { return }

        let boundary = UUID().uuidString
        var body = Data()

        func appendField(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }

        // Bild
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"bild\"; filename=\"frame_\(frameId).jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(bildData)
        body.append("\r\n".data(using: .utf8)!)

        // Form-fält som JSON-strängar
        appendField("karta", kartaNamn)
        appendField("frame_id", "\(frameId)")
        if let s = jsonString(transform) { appendField("transform", s) }
        if let s = jsonString(intrinsics) { appendField("intrinsics", s) }
        if let s = jsonString(imageDims) { appendField("image_dims", s) }
        if let s = jsonString(punkter) { appendField("frame_punkter", s) }
        if let s = jsonString(t_ak) { appendField("T_arkit_till_karta", s) }

        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.httpBody = body
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 30

        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let antalNya = json?["antal_nya"] as? Int ?? 0
            let totalt = json?["totalt"] as? Int ?? 0
            let produkter = json?["produkter"] as? [[String: Any]] ?? []

            await MainActor.run {
                self.antalFrames += 1
                self.antalProdukter = totalt

                // Lägg till nya träffar i UI-listan
                let nyaTräffar: [Träff] = produkter.compactMap { p in
                    guard let namn = p["visningsnamn"] as? String,
                          let x = (p["x"] as? NSNumber)?.doubleValue,
                          let z = (p["z"] as? NSNumber)?.doubleValue
                    else { return nil }
                    let metod = p["position_metod"] as? String ?? "?"
                    return Träff(namn: namn, x: x, z: z, metod: metod)
                }
                self.senastTräffar = nyaTräffar + self.senastTräffar
                if self.senastTräffar.count > 10 {
                    self.senastTräffar = Array(self.senastTräffar.prefix(10))
                }

                if self.skannar {
                    self.statusText = "Skannar… (\(self.antalFrames) frames, +\(antalNya) nya)"
                }
            }
        } catch {
            await MainActor.run {
                self.statusText = "Frame-fel: \(error.localizedDescription)"
            }
        }
    }

    // ─────────────────────────────────────────────
    // 3D-PUNKT EXTRAKTION (samma logik som ButikSkanning, glesare sampling)
    // ─────────────────────────────────────────────

    private func extrahera3DPunkter(frame: ARFrame,
                                    fx: Float, fy: Float, cx: Float, cy: Float) -> [[String: Float]] {
        guard let depthMap = frame.sceneDepth?.depthMap ?? frame.smoothedSceneDepth?.depthMap,
              let confidenceMap = frame.sceneDepth?.confidenceMap ?? frame.smoothedSceneDepth?.confidenceMap
        else { return [] }

        var punkter: [[String: Float]] = []

        CVPixelBufferLockBaseAddress(depthMap, .readOnly)
        CVPixelBufferLockBaseAddress(confidenceMap, .readOnly)
        defer {
            CVPixelBufferUnlockBaseAddress(depthMap, .readOnly)
            CVPixelBufferUnlockBaseAddress(confidenceMap, .readOnly)
        }

        let depthWidth = CVPixelBufferGetWidth(depthMap)
        let depthHeight = CVPixelBufferGetHeight(depthMap)
        let depthData = CVPixelBufferGetBaseAddress(depthMap)!.assumingMemoryBound(to: Float32.self)
        let confData = CVPixelBufferGetBaseAddress(confidenceMap)!.assumingMemoryBound(to: UInt8.self)
        let imageWidth = CVPixelBufferGetWidth(frame.capturedImage)
        let imageHeight = CVPixelBufferGetHeight(frame.capturedImage)

        let cameraTransform = frame.camera.transform

        let samplingStep = 16          // glesare än Läge 1 → mindre payload
        let maxPunkter = 600

        outer: for row in stride(from: 0, to: depthHeight, by: samplingStep) {
            for col in stride(from: 0, to: depthWidth, by: samplingStep) {
                if punkter.count >= maxPunkter { break outer }

                let idx = row * depthWidth + col
                let depth = depthData[idx]
                let confidence = confData[idx]
                guard depth > 0.1 && depth < 5.0 && confidence >= 1 else { continue }

                let u_landscape = Float(col) / Float(depthWidth) * Float(imageWidth)
                let v_landscape = Float(row) / Float(depthHeight) * Float(imageHeight)

                // ARKit camera-frame: +X right, +Y up, +Z BAKÅT.
                // Bild-pixlar har +V nedåt, depth pekar framåt.
                // Konvertera CV-pinhole → ARKit camera-frame (flip Y och Z).
                let x_cam =  (u_landscape - cx) * depth / fx
                let y_cam = -(v_landscape - cy) * depth / fy
                let z_cam = -depth

                let camPoint = SIMD4<Float>(x_cam, y_cam, z_cam, 1.0)
                let worldPoint = cameraTransform * camPoint

                punkter.append([
                    "x": worldPoint.x,
                    "y": worldPoint.y,
                    "z": worldPoint.z,
                ])
            }
        }
        return punkter
    }

    // ─────────────────────────────────────────────
    // HJÄLP
    // ─────────────────────────────────────────────

    private func jsonString(_ obj: Any) -> String? {
        guard let data = try? JSONSerialization.data(withJSONObject: obj) else { return nil }
        return String(data: data, encoding: .utf8)
    }
}

// ─────────────────────────────────────────────────────────────────
// MODELLER
// ─────────────────────────────────────────────────────────────────

struct Träff: Identifiable {
    let id = UUID()
    let namn: String
    let x: Double
    let z: Double
    let metod: String
}

// ─────────────────────────────────────────────────────────────────
// AR-KAMERAVY
// ─────────────────────────────────────────────────────────────────

struct ProduktSkanningKameraVy: UIViewRepresentable {
    let manager: ProduktSkanningManager

    func makeUIView(context: Context) -> ARSCNView {
        let arView = ARSCNView(frame: .zero)
        arView.automaticallyUpdatesLighting = true
        arView.scene = SCNScene()
        DispatchQueue.main.async {
            manager.startaARSession(arView.session)
        }
        return arView
    }

    func updateUIView(_ uiView: ARSCNView, context: Context) {}

    static func dismantleUIView(_ uiView: ARSCNView, coordinator: ()) {
        uiView.session.pause()
    }
}

#Preview {
    ProduktSkanningView()
}
