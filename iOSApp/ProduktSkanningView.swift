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
                HStack(spacing: 4) {
                    Circle()
                        .fill(manager.trackingOK ? Color.green : Color.orange)
                        .frame(width: 6, height: 6)
                    Text("AR: \(manager.trackingStatus)")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(manager.trackingOK ? .white : .orange)
                }
                Text("\(manager.antalFrames) frames")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.white)
                Text("\(manager.antalProdukter) produkter")
                    .font(.system(size: 11, design: .monospaced))
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
    @Published var trackingStatus: String = "okänd"   // "OK", "begränsad", "förlorad"
    @Published var trackingOK: Bool = false

    var kartaNamn: String = "hela_butiken"

    /// Aktuell T_arkit → karta (4x4), column-major flat. Detta är vad
    /// produkt-frames använder. Uppdateras mjukt mot målTAk via blending.
    private var aktuellTAk: [Float]?

    /// Mål-T_ak från senaste VPS-rekalibrering. Aktuell blandas mot mål
    /// över ~0.5 sek så positionen aldrig hoppar.
    private var målTAk: [Float]?

    /// T_ak vid blending-start (snapshot för korrekt lerp)
    private var blendStartTAk: [Float]?

    /// Start-tidpunkt för pågående blending (nil = ingen blending pågår)
    private var blendStartTid: TimeInterval?

    /// Längd på blending (sekunder). 0.5 = mjuk men snabb korrigering.
    private let blendVaraktighet: TimeInterval = 0.5

    /// Timer för 0.5s-intervall (produkt-frames)
    private var skanningsTimer: Timer?

    /// Bakgrunds-timer som auto-rekalibrerar mot VPS var ~3 sek
    private var rekalibreringsTimer: Timer?

    /// Snabb timer (~3 Hz) som skickar lättviktig live-position till servern
    /// (bara transform + T_ak, ingen bild/LiDAR/Qwen) så 3D-viewerns Live-prick
    /// följer kameran mjukt i stället för att hoppa när en tung produkt-frame
    /// råkar bli klar.
    private var livePosTimer: Timer?
    private var skickarLivePos = false

    /// Sista ramen att skicka
    private var senasteFrame: ARFrame?

    /// Sista ARKit-tracking-state (uppdateras varje frame)
    private var senasteTrackingState: ARCamera.TrackingState = .notAvailable

    /// Antal bortskippade frames pga dålig tracking (för debug)
    private var skippadeFrames: Int = 0

    /// Antal genomförda auto-rekalibreringar (för debug)
    private var antalRekalibreringar: Int = 0

    /// Antal förkastade VPS-svar (för låga inliers eller för stor avvikelse)
    private var antalFörkastadeRekal: Int = 0

    /// Pågående rekalibrering (för att inte skicka flera samtidigt)
    private var rekalibrerar: Bool = false

    /// Föregående tracking-state (för att detektera relokalisering)
    private var förraTrackingState: ARCamera.TrackingState = .notAvailable

    /// Sätts true när ARKit återfått normal tracking efter en förlust. Då kan
    /// ARKits world-origin ha hoppat → den sparade T_ak är stale och pekar fel.
    /// En "hård" rekalibrering snappar T_ak direkt och åsidosätter sanity-checks
    /// (annars skulle de förkasta den korrekta korrigeringen som "för stort hopp").
    private var behöverHårdRekal: Bool = false

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
        rekalibreringsTimer?.invalidate()
        rekalibreringsTimer = nil
        livePosTimer?.invalidate()
        livePosTimer = nil
        session?.pause()
        session = nil
    }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        senasteFrame = frame
        senasteTrackingState = frame.camera.trackingState

        let (status, ok) = beskrivTracking(senasteTrackingState)
        DispatchQueue.main.async {
            if self.trackingStatus != status {
                self.trackingStatus = status
            }
            if self.trackingOK != ok {
                self.trackingOK = ok
            }
        }

        // Detektera relokalisering: ARKit har gått från icke-normal → normal
        // tracking. När det händer kan ARKits world-origin ha hoppat, så den
        // sparade T_ak pekar nu fel. Begär en hård rekalibrering som snappar
        // till VPS-sanningen igen (åsidosätter sanity-checks).
        if skannar {
            let förraOK: Bool = { if case .normal = förraTrackingState { return true } else { return false } }()
            let nuOK: Bool = { if case .normal = senasteTrackingState { return true } else { return false } }()
            if nuOK && !förraOK {
                behöverHårdRekal = true
            }
        }
        förraTrackingState = senasteTrackingState

        // Stega blending mot ny T_ak om det finns en pågående
        uppdateraBlending()
    }

    /// Beräknar yaw-vinkelskillnad (rad) mellan två T_ak-matriser genom att
    /// jämföra X-axelns horisontella projektion (column 0, XZ-plan).
    /// Returnerar 0 till π. Värden över π/3 (60°) indikerar troligen
    /// PnP-flipp eller annat allvarligt rotation-fel.
    private func yawDifference(mellan a: [Float], och b: [Float]) -> Float {
        // Column 0 (rotation-X-axel i karta-frame) = a[0], a[1], a[2]
        let ax = a[0], az = a[2]
        let bx = b[0], bz = b[2]
        let aMag = (ax*ax + az*az).squareRoot()
        let bMag = (bx*bx + bz*bz).squareRoot()
        guard aMag > 0.01 && bMag > 0.01 else { return 0 }
        let cos = (ax*bx + az*bz) / (aMag * bMag)
        let cosClamp = max(-1.0, min(1.0, cos))
        return acos(cosClamp)
    }

    /// Stega aktuellTAk mjukt mot målTAk baserat på tid sedan blendStartTid.
    /// När t >= 1.0 är blendingen klar och aktuell == mål.
    /// VIKTIGT: lerpar från en SNAPSHOT av aktuell vid blend-start, inte från
    /// nuvarande aktuell — annars kompounderar varje frame och vi når mål för fort.
    private func uppdateraBlending() {
        guard let mål = målTAk, let start = blendStartTid,
              let från = blendStartTAk
        else { return }

        let elapsed = Date().timeIntervalSince1970 - start
        let t = Float(min(elapsed / blendVaraktighet, 1.0))

        if t >= 1.0 {
            // Klart — lås aktuell = mål, rensa blending-state
            aktuellTAk = mål
            målTAk = nil
            blendStartTAk = nil
            blendStartTid = nil
        } else {
            // Linjär blend av alla 16 komponenter från snapshot mot mål.
            // För små förflyttningar (typiskt <30 cm/frame) är detta
            // tillräckligt nära korrekt slerp+lerp.
            aktuellTAk = zip(från, mål).map { (a, b) in a + (b - a) * t }
        }
    }

    private func beskrivTracking(_ state: ARCamera.TrackingState) -> (String, Bool) {
        switch state {
        case .normal:
            return ("OK", true)
        case .notAvailable:
            return ("init", false)
        case .limited(let anledning):
            switch anledning {
            case .initializing: return ("init", false)
            case .relocalizing: return ("åter-lokaliserar", false)
            case .excessiveMotion: return ("rör för fort", false)
            case .insufficientFeatures: return ("få features", false)
            @unknown default: return ("begränsad", false)
            }
        }
    }

    // ─────────────────────────────────────────────
    // LOKALISERING
    // ─────────────────────────────────────────────

    func lokalisera() {
        guard let frame = senasteFrame ?? session?.currentFrame else {
            statusText = "Ingen AR-frame ännu"
            return
        }
        // Vägra lokalisera om ARKit-tracking inte är pålitlig — PnP behöver
        // en frame där kamerapose är säker, annars blir T_arkit_till_karta fel.
        if case .normal = frame.camera.trackingState {
            // bra
        } else {
            statusText = "Vänta — tracking är \(trackingStatus). Backa lite."
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
                        // Engångs-lokalisering: sätt direkt utan blending
                        // (det finns ingen tidigare pose att blanda från)
                        self.aktuellTAk = floats
                        self.målTAk = nil
                        self.blendStartTAk = nil
                        self.blendStartTid = nil
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
        guard lokaliserad, aktuellTAk != nil else {
            statusText = "Lokalisera först"
            return
        }
        skannar = true
        statusText = "Skannar produkter…"
        antalFrames = 0
        skippadeFrames = 0
        antalRekalibreringar = 0
        antalFörkastadeRekal = 0
        behöverHårdRekal = false
        senastTräffar = []

        skanningsTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            self?.skickaNästaFrame()
        }

        // Auto-rekalibrering var 2 sek: blandar mjukt mot VPS-pose så
        // positionen aldrig hoppar men ARKit-drift fångas upp ofta nog att
        // den absoluta felmarginalen hålls liten under rörelse.
        rekalibreringsTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.autoRekalibrera()
        }

        // Snabb live-position (~3 Hz): följer kameran mjukt i 3D-viewern.
        livePosTimer = Timer.scheduledTimer(withTimeInterval: 0.3, repeats: true) { [weak self] _ in
            self?.skickaLivePos()
        }
    }

    func stoppaSkanning() {
        skanningsTimer?.invalidate()
        skanningsTimer = nil
        rekalibreringsTimer?.invalidate()
        rekalibreringsTimer = nil
        livePosTimer?.invalidate()
        livePosTimer = nil
        skannar = false
        statusText = "Pausad — \(antalProdukter) prod, \(antalRekalibreringar) rekal, \(antalFörkastadeRekal) avvisade, \(skippadeFrames) skippade"
    }

    // ─────────────────────────────────────────────
    // AUTO-REKALIBRERING (Väg 1)
    // ─────────────────────────────────────────────

    /// Skickar en tyst VPS-lokaliseringsförfrågan i bakgrunden under skanning.
    /// Om svaret är pålitligt (många inliers) uppdateras T_arkit_till_karta
    /// så ARKit-drift korrigeras. Inga UI-flaggor påverkas — användaren
    /// märker inget förrän nästa produktframe placeras med ny T_ak.
    private func autoRekalibrera() {
        guard !rekalibrerar else { return }
        guard let frame = senasteFrame ?? session?.currentFrame else { return }
        // Bara försök rekalibrera om tracking är pålitlig
        if case .normal = frame.camera.trackingState {} else { return }

        // Snapshot transform + bild på samma sätt som vanlig lokalisera()
        let t = frame.camera.transform
        let transformArr: [Float] = [
            t.columns.0.x, t.columns.0.y, t.columns.0.z, t.columns.0.w,
            t.columns.1.x, t.columns.1.y, t.columns.1.z, t.columns.1.w,
            t.columns.2.x, t.columns.2.y, t.columns.2.z, t.columns.2.w,
            t.columns.3.x, t.columns.3.y, t.columns.3.z, t.columns.3.w
        ]

        let pixelBuffer = frame.capturedImage
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent),
              let bildData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.7)
        else { return }

        // Snapshotta om detta är en hård rekalibrering (efter relokalisering).
        // Flaggan nollställs här så vi inte upprepar den i onödan.
        let hård = behöverHårdRekal
        behöverHårdRekal = false

        rekalibrerar = true
        Task { await skickaAutoRekalibrering(bildData: bildData, arkitTransform: transformArr, hård: hård) }
    }

    private func skickaAutoRekalibrering(bildData: Data, arkitTransform: [Float], hård: Bool) async {
        defer { DispatchQueue.main.async { self.rekalibrerar = false } }

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

        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"bild\"; filename=\"rekal.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(bildData)
        body.append("\r\n".data(using: .utf8)!)

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
        req.timeoutInterval = 10  // kortare än manuell — vi har gammal T_ak att falla tillbaka på

        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let hittad = json?["hittad"] as? Bool ?? false
            let inliers = json?["inliers"] as? Int ?? 0

            // Inlier-tröskel: hård rekalibrering kräver mycket hög säkerhet
            // (vi snappar utan sanity-checks), normal kräver lite lägre så
            // korrigeringar händer ofta nog att driften hålls liten.
            let minInliers = hård ? 80 : 60
            guard hittad, inliers >= minInliers,
                  let flat = json?["T_arkit_till_karta"] as? [Any]
            else {
                await MainActor.run { self.antalFörkastadeRekal += 1 }
                return
            }

            let floats = flat.compactMap { ($0 as? NSNumber)?.floatValue }
            guard floats.count == 16 else { return }

            // Hård rekalibrering: ARKit har relokaliserat och dess origin kan
            // ha hoppat → den sparade T_ak är ogiltig. Snappa direkt till VPS
            // och hoppa över sanity-checks (de skulle annars förkasta den
            // korrekta korrigeringen just för att den skiljer sig mycket).
            if hård {
                await MainActor.run {
                    self.aktuellTAk = floats
                    self.målTAk = nil
                    self.blendStartTAk = nil
                    self.blendStartTid = nil
                    self.antalRekalibreringar += 1
                }
                return
            }

            // Sanity-check 1: translation-skillnad mellan ny pose och
            // nuvarande pose. Om > 1.5 m är det troligen felaktigt PnP-svar.
            if let aktuell = aktuellTAk {
                let dtx = floats[12] - aktuell[12]
                let dty = floats[13] - aktuell[13]
                let dtz = floats[14] - aktuell[14]
                let avstånd = (dtx*dtx + dty*dty + dtz*dtz).squareRoot()
                if avstånd > 1.5 {
                    await MainActor.run { self.antalFörkastadeRekal += 1 }
                    return
                }

                // Sanity-check 2: yaw-flipp-detektion.
                // PnP kan i symmetriska scener konvergera på en 180°-roterad
                // lösning. Vi jämför X-axelns riktning (column 0 av rotation)
                // mellan ny och aktuell pose. Stora vinkelskillnader (>60°)
                // är troligen ett flipp eller annat allvarligt fel.
                let yawDiff = yawDifference(mellan: aktuell, och: floats)
                if yawDiff > .pi / 3 {  // 60°
                    await MainActor.run { self.antalFörkastadeRekal += 1 }
                    return
                }
            }

            // Starta blending: snapshotta nuvarande aktuell som startpunkt,
            // sätt mål och starttid. uppdateraBlending() lerpar varje frame.
            await MainActor.run {
                self.blendStartTAk = self.aktuellTAk
                self.målTAk = floats
                self.blendStartTid = Date().timeIntervalSince1970
                self.antalRekalibreringar += 1
            }
        } catch {
            // Tyst fel — vi har fortfarande gammal T_ak
        }
    }

    /// Skickar en lättviktig live-position till servern (bara kameratransform +
    /// T_ak). Servern räknar ut kartpositionen och 3D-viewern pollar den.
    /// Helt frikopplad från den tunga produkt-framen så pricken kan följa
    /// kameran i ~3 Hz i stället för att hoppa varje gång en frame blir klar.
    private func skickaLivePos() {
        guard !skickarLivePos else { return }
        guard let frame = senasteFrame ?? session?.currentFrame else { return }
        guard let t_ak = aktuellTAk else { return }

        let t = frame.camera.transform
        let transformArr: [Float] = [
            t.columns.0.x, t.columns.0.y, t.columns.0.z, t.columns.0.w,
            t.columns.1.x, t.columns.1.y, t.columns.1.z, t.columns.1.w,
            t.columns.2.x, t.columns.2.y, t.columns.2.z, t.columns.2.w,
            t.columns.3.x, t.columns.3.y, t.columns.3.z, t.columns.3.w
        ]

        skickarLivePos = true
        Task { await skickaLivePosRequest(transform: transformArr, t_ak: t_ak) }
    }

    private func skickaLivePosRequest(transform: [Float], t_ak: [Float]) async {
        defer { DispatchQueue.main.async { self.skickarLivePos = false } }
        guard let url = URL(string: "\(serverURL)/produkter/live_pos/") else { return }

        let boundary = UUID().uuidString
        var body = Data()
        func appendField(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }
        appendField("karta", kartaNamn)
        if let s = jsonString(transform) { appendField("transform", s) }
        if let s = jsonString(t_ak) { appendField("T_arkit_till_karta", s) }
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.httpBody = body
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 4

        _ = try? await URLSession.shared.data(for: req)
    }

    private func skickaNästaFrame() {
        guard !skickarFrame else { return }   // hoppa över om förra inte hunnit
        guard let frame = senasteFrame ?? session?.currentFrame else { return }
        guard let t_ak = aktuellTAk else { return }

        // Skippa frames med dålig ARKit-tracking — de ger felaktig kamerapose
        // och därmed felplacerade produkter. Räkna dem för debug.
        if case .normal = frame.camera.trackingState {
            // bra, fortsätt
        } else {
            skippadeFrames += 1
            DispatchQueue.main.async {
                self.statusText = "Tracking \(self.trackingStatus) — skippade frame (\(self.skippadeFrames) totalt)"
            }
            return
        }

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
