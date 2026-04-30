//
//  ARNavigationView.swift
//  PulsAr
//
//  AR-navigering med VPS-position + ARKit rotation tracking
//
//  ARKITEKTUR:
//  - VPS ger position (x,z) OCH yaw i KARTANS koordinatsystem
//  - Vid första lyckade VPS: beräkna offset mellan karta och ARKit-frame
//  - Mellan VPS-fixar: ARKit rotation tracking håller koll på vart användaren tittar
//  - Varje ny VPS-fix korrigerar eventuell drift
//
//  FRAMTID:
//  - Lägg till butikskarta med hyllor (occupancy grid)
//  - A* pathfinding från kundPosition till produkt
//  - Waypoints längs rutten → AR-pilar vid varje sväng
//

import SwiftUI
import ARKit
import SceneKit
import Combine

// ─────────────────────────────────────────────────────────────────
// HUVUDVY
// ─────────────────────────────────────────────────────────────────

struct ARNavigationView: View {
    let produkt: SökProdukt
    @StateObject private var manager = ARNavManager()
    @Environment(\.dismiss) var dismiss

    var body: some View {
        ZStack {
            ARNavKameraVy(manager: manager)
                .ignoresSafeArea()

            VStack {
                // Topprad
                HStack {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .font(.title2)
                            .foregroundColor(.white)
                            .padding(12)
                            .background(.ultraThinMaterial)
                            .clipShape(Circle())
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(produkt.visningsnamn)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .foregroundColor(.white)
                            .lineLimit(2)
                            .multilineTextAlignment(.trailing)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(.ultraThinMaterial)
                    .cornerRadius(12)
                }
                .padding()

                Spacer()

                // Navigeringskort
                if manager.ärFramme {
                    frammeVy
                } else {
                    navigeringsKort
                }
            }
        }
        .navigationBarHidden(true)
        .onAppear {
            manager.starta(produkt: produkt)
        }
        .onDisappear {
            manager.stoppa()
        }
    }

    // ─── FRAMME ───

    var frammeVy: some View {
        VStack(spacing: 16) {
            ZStack {
                Circle().fill(Color.green.opacity(0.3)).frame(width: 100, height: 100)
                Circle().fill(Color.green.opacity(0.5)).frame(width: 70, height: 70)
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 50)).foregroundColor(.green)
            }
            Text("Du är framme!").font(.title).fontWeight(.bold).foregroundColor(.white)
            Text(produkt.visningsnamn).font(.headline).foregroundColor(.white)
                .padding().background(.ultraThinMaterial).cornerRadius(16)
            Button { dismiss() } label: {
                Text("Klar").fontWeight(.semibold).foregroundColor(.white)
                    .frame(maxWidth: .infinity).padding()
                    .background(Color.green).cornerRadius(14)
            }
            .padding(.horizontal, 40)
        }
        .padding().padding(.bottom, 40)
    }

    // ─── NAVIGERINGSKORT ───

    var navigeringsKort: some View {
        VStack(spacing: 0) {
            if !manager.harPosition {
                // Söker position
                HStack(spacing: 10) {
                    ProgressView().tint(.white).scaleEffect(0.8)
                    Text("Söker din position...")
                        .font(.subheadline).foregroundColor(.white)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 20)
                .background(.ultraThinMaterial)
                .cornerRadius(20)
                .padding(.horizontal, 20)
                .padding(.bottom, 40)
            } else {
                VStack(spacing: 12) {
                    // Stor riktningspil
                    riktningsPil

                    // Avstånd
                    Text(avståndText)
                        .font(.system(size: 36, weight: .bold, design: .rounded))
                        .foregroundColor(.white)

                    // Instruktion
                    Text(instruktionText)
                        .font(.headline)
                        .foregroundColor(.white.opacity(0.9))

                    // VPS-status
                    HStack(spacing: 8) {
                        Circle().fill(statusFärg).frame(width: 8, height: 8)
                        Text("VPS: \(manager.senasteInliers) inliers")
                            .font(.caption2).foregroundColor(.white.opacity(0.6))
                    }
                    .padding(.top, 4)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 24)
                .background(.ultraThinMaterial)
                .cornerRadius(24)
                .padding(.horizontal, 20)
                .padding(.bottom, 40)
            }
        }
    }

    // ─── RIKTNINGSPIL ───

    var riktningsPil: some View {
        Image(systemName: "location.north.fill")
            .font(.system(size: 80, weight: .bold))
            .foregroundColor(pilFärg)
            .rotationEffect(.radians(Double(manager.relativBäring)))
            .shadow(color: pilFärg.opacity(0.5), radius: 10)
            .animation(.easeInOut(duration: 0.3), value: manager.relativBäring)
    }

    var pilFärg: Color {
        let d = manager.avstånd
        if d < 2 { return .green }
        if d < 5 { return .yellow }
        return .orange
    }

    var statusFärg: Color {
        if manager.senasteInliers >= 30 { return .green }
        if manager.senasteInliers >= 15 { return .yellow }
        return .orange
    }

    var avståndText: String {
        let d = manager.avstånd
        if d < 1 { return "< 1 m" }
        if d < 10 { return String(format: "%.1f m", d) }
        return "\(Int(d)) m"
    }

    var instruktionText: String {
        let a = abs(manager.relativBäring)
        let b = manager.relativBäring
        if a < 0.4 { return "Gå rakt fram" }
        if a < 1.2 { return b > 0 ? "Sväng höger" : "Sväng vänster" }
        if a < 2.5 { return b > 0 ? "Vänd höger" : "Vänd vänster" }
        return "Vänd om"
    }
}

// ─────────────────────────────────────────────────────────────────
// AR-KAMERAVY
// ─────────────────────────────────────────────────────────────────

struct ARNavKameraVy: UIViewRepresentable {
    let manager: ARNavManager

    func makeUIView(context: Context) -> ARSCNView {
        let scnView = ARSCNView(frame: .zero)
        scnView.automaticallyUpdatesLighting = true
        scnView.autoenablesDefaultLighting = true
        scnView.scene = SCNScene()
        manager.startaAR(scnView: scnView)
        return scnView
    }

    func updateUIView(_ uiView: ARSCNView, context: Context) {}
}

// ─────────────────────────────────────────────────────────────────
// MANAGER
// ─────────────────────────────────────────────────────────────────

class ARNavManager: NSObject, ObservableObject, ARSessionDelegate {
    @Published var avstånd: Float = 0
    @Published var relativBäring: Float = 0
    @Published var harPosition = false
    @Published var ärFramme = false
    @Published var senasteInliers: Int = 0

    private var produkt: SökProdukt?
    private var scnView: ARSCNView?
    private var arSession: ARSession?
    private var vpsTimer: Timer?
    private var isLokaliserar = false

    // Kundens position i KARTANS koordinatsystem
    private var kundKartX: Float = 0
    private var kundKartZ: Float = 0
    
    private var senasteArkitX: Float = 0
    private var senasteArkitZ: Float = 0
    private var harArkitReferens: Bool = false

    // Offset mellan kartans frame och ARKit-frame (yaw runt gravitationsaxeln).
    // Kalibreras vid varje lyckad VPS-fix. ARKit sköter rotation däremellan.
    private var mapToArkitYawOffset: Float = 0
    private var mapToArkitKalibrerad = false

    // Throttling för riktningsuppdatering
    private var lastRiktningUppdatering: CFTimeInterval = 0

    let serverURL = PulsArConfig.serverURL
    let frammeAvstånd: Float = 2.0

    // ─── LIFECYCLE ───

    func starta(produkt: SökProdukt) {
        self.produkt = produkt
        print("🟢 Navigation startad: \(produkt.visningsnamn) @ (\(produkt.x ?? 0), \(produkt.z ?? 0))")
    }

    func startaAR(scnView: ARSCNView) {
        self.scnView = scnView
        self.arSession = scnView.session
        scnView.session.delegate = self

        let config = ARWorldTrackingConfiguration()
        config.worldAlignment = .gravity
        scnView.session.run(config, options: [.resetTracking, .removeExistingAnchors])

        vpsTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            self?.lokaliseraMedVPS()
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            self?.lokaliseraMedVPS()
        }
    }

    func stoppa() {
        arSession?.pause()
        vpsTimer?.invalidate()
    }

    // ─── ARKIT-DELEGATE (kontinuerlig riktningsuppdatering) ───

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let now = CACurrentMediaTime()
        if now - lastRiktningUppdatering < 0.1 { return }
        lastRiktningUppdatering = now
        
        // Uppdatera position via ARKit-delta mellan VPS-fixar
        if harPosition && harArkitReferens && mapToArkitKalibrerad {
            let arkitX = frame.camera.transform.columns.3.x
            let arkitZ = frame.camera.transform.columns.3.z
            
            let deltaArkitX = arkitX - senasteArkitX
            let deltaArkitZ = arkitZ - senasteArkitZ
            
            // Rotera delta från ARKit-frame till kartans frame
            let cosOffset = cos(mapToArkitYawOffset)
            let sinOffset = sin(mapToArkitYawOffset)
            let deltaKartX = deltaArkitX * cosOffset + deltaArkitZ * sinOffset
            let deltaKartZ = -deltaArkitX * sinOffset + deltaArkitZ * cosOffset
            
            DispatchQueue.main.async {
                self.kundKartX += deltaKartX
                self.kundKartZ += deltaKartZ
                self.senasteArkitX = arkitX
                self.senasteArkitZ = arkitZ
                self.uppdateraAvstånd()
                self.uppdateraRiktning()
            }
        } else {
            DispatchQueue.main.async { self.uppdateraRiktning() }
        }
    }

    // ─── VPS ───

    func lokaliseraMedVPS() {
        guard let session = arSession,
              let frame = session.currentFrame else { return }
        guard !isLokaliserar else { return }
        isLokaliserar = true

        let pixelBuffer = frame.capturedImage
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent),
              let bildData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.8) else {
            isLokaliserar = false
            return
        }

        // ARKit yaw vid bildtillfället (i ARKit-frame, runt gravitationsaxeln)
        let arkitYaw = atan2(-frame.camera.transform.columns.2.x, -frame.camera.transform.columns.2.z)

        Task {
            await skickaVPS(bildData: bildData, arkitYawVidBild: arkitYaw)
            await MainActor.run { self.isLokaliserar = false }
        }
    }

    private func skickaVPS(bildData: Data, arkitYawVidBild: Float) async {
        do {
            let boundary = UUID().uuidString
            var body = Data()
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"bild\"; filename=\"frame.jpg\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
            body.append(bildData)
            body.append("\r\n--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"gång_namn\"\r\n\r\n".data(using: .utf8)!)
            body.append("hela_butiken".data(using: .utf8)!)
            body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

            var request = URLRequest(url: URL(string: "\(serverURL)/lokalisera/")!)
            request.httpMethod = "POST"
            request.httpBody = body
            request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 15

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { return }
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  json["hittad"] as? Bool == true else {
                print("⚠️ VPS: ingen match")
                return
            }

            let vpsX = (json["x"] as? NSNumber)?.floatValue ?? 0
            let vpsZ = (json["z"] as? NSNumber)?.floatValue ?? 0
            let vpsYaw = (json["yaw"] as? NSNumber)?.floatValue ?? 0  // grader
            let inliers = (json["inliers"] as? NSNumber)?.intValue ?? 0

            guard inliers >= 25 else {
                print("⚠️ VPS ignorerat (\(inliers) inliers)")
                return
            }

            await MainActor.run {
                self.senasteInliers = inliers

                // Uppdatera position direkt — bra VPS = korrekt
                self.kundKartX = vpsX
                self.kundKartZ = vpsZ
                if !self.harPosition { self.harPosition = true }
                
                if let currentFrame = self.arSession?.currentFrame {
                    self.senasteArkitX = currentFrame.camera.transform.columns.3.x
                    self.senasteArkitZ = currentFrame.camera.transform.columns.3.z
                    self.harArkitReferens = true
                }

                // Kalibrera/omkalibrera offset mellan karta och ARKit-frame
                // VPS-yaw = kamerans riktning i kartans frame
                // ARKit-yaw = kamerans riktning i ARKit-frame
                // offset = ARKit - Karta  →  kamera_i_karta = ARKit_yaw - offset
                let vpsYawRad = vpsYaw * .pi / 180.0
                self.mapToArkitYawOffset = arkitYawVidBild - vpsYawRad
                self.mapToArkitKalibrerad = true

                self.uppdateraAvstånd()
                self.uppdateraRiktning()

                print("📍 VPS: (\(String(format: "%.2f", vpsX)), \(String(format: "%.2f", vpsZ))) yaw=\(String(format: "%.1f", vpsYaw))° offset=\(String(format: "%.1f", self.mapToArkitYawOffset * 180 / .pi))° inliers=\(inliers)")
            }

        } catch {
            print("❌ VPS-fel: \(error.localizedDescription)")
        }
    }

    // ─── AVSTÅND ───

    private func uppdateraAvstånd() {
        guard let p = produkt else { return }
        let dx = Float(p.x ?? 0) - kundKartX
        let dz = Float(p.z ?? 0) - kundKartZ
        avstånd = sqrt(dx * dx + dz * dz)
        ärFramme = avstånd < frammeAvstånd
    }

    // ─── RIKTNING ───
    //
    // Bäring till produkt i kartans frame: atan2(dx, -dz)
    // Kamerans yaw i kartans frame: ARKit_yaw - mapToArkitYawOffset
    // Relativ bäring = bäring - kamerayaw (båda i kartans frame)

    private func uppdateraRiktning() {
        guard harPosition,
              mapToArkitKalibrerad,
              let p = produkt,
              let frame = arSession?.currentFrame else { return }

        let dx = Float(p.x ?? 0) - kundKartX
        let dz = Float(p.z ?? 0) - kundKartZ

        // Bäring till produkt i kartans system
        let kartBäring = atan2(dx, -dz)

        // Kamerans nuvarande yaw i ARKit-frame
        let arkitYawNow = atan2(-frame.camera.transform.columns.2.x,
                                -frame.camera.transform.columns.2.z)

        // Konvertera till kartans frame
        let kameraYawIKarta = arkitYawNow - mapToArkitYawOffset

        // Relativ bäring
        var bäring = kartBäring - kameraYawIKarta
        while bäring > .pi { bäring -= 2 * .pi }
        while bäring < -.pi { bäring += 2 * .pi }

        relativBäring = bäring
    }

    // ─── FRAMTID: PATHFINDING ───
    //
    // struct Waypoint { let x: Float; let z: Float; let instruktion: String }
    // var rutt: [Waypoint] = []
    // var aktuellWaypoint = 0
    //
    // func beräknaRutt(butikskarta: [[Bool]]) {
    //     // A* från (kundKartX, kundKartZ) till (produktX, produktZ)
    //     // Resultat: lista av waypoints
    //     // uppdateraRiktning() pekar mot rutt[aktuellWaypoint]
    // }
}
