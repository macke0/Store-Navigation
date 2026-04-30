//
//  NavigationKartView.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-04-24.
//


//
//  NavigationKartView.swift
//  PulsAr
//
//  Visar kundens position på butikskartan som blå prick.
//  Använder VPS för initial position + ARKit-delta för kontinuerlig uppdatering.
//
//  Framtida features:
//  - Produktmarkör när kund sökt
//  - Rutt-linje från kund till produkt
//  - Auto-kamera när kund är nära produkten
//

import SwiftUI
import ARKit
import Combine

struct NavigationKartView: View {
    let butikId: String
    let produktNamn: String?      // Framtida: visa produkt-markör
    
    @StateObject private var manager = NavigationKartManager()
    @Environment(\.dismiss) var dismiss
    
    init(butikId: String, produktNamn: String? = nil) {
        self.butikId = butikId
        self.produktNamn = produktNamn
    }
    
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            
            if manager.kartBild == nil {
                laddningsVy
            } else {
                huvudVy
            }
        }
        .navigationBarHidden(true)
        .onAppear {
            manager.butikId = butikId
            manager.startaARSession()
            manager.laddaKartbild()
        }
        .onDisappear {
            manager.stoppaARSession()
        }
    }
    
    // ─────────────────────────────────────────────
    // LADDNING
    // ─────────────────────────────────────────────
    
    var laddningsVy: some View {
        VStack(spacing: 20) {
            ProgressView().scaleEffect(2).tint(.white)
            Text("Laddar karta...")
                .foregroundColor(.white)
            if let fel = manager.fel {
                Text(fel)
                    .foregroundColor(.red)
                    .font(.caption)
                    .multilineTextAlignment(.center)
                    .padding()
                Button("Stäng") { dismiss() }
                    .foregroundColor(.white)
                    .padding()
                    .background(Color.gray)
                    .cornerRadius(8)
            }
        }
    }
    
    // ─────────────────────────────────────────────
    // HUVUDVY
    // ─────────────────────────────────────────────
    
    var huvudVy: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Button { dismiss() } label: {
                    Image(systemName: "xmark")
                        .foregroundColor(.white)
                        .padding(10)
                        .background(Color.white.opacity(0.2))
                        .clipShape(Circle())
                }
                
                Spacer()
                
                VStack(spacing: 2) {
                    if let produkt = produktNamn {
                        Text("Navigerar till")
                            .font(.caption)
                            .foregroundColor(.gray)
                        Text(produkt)
                            .font(.headline)
                            .foregroundColor(.white)
                    } else {
                        Text("Din position")
                            .font(.headline)
                            .foregroundColor(.white)
                    }
                }
                
                Spacer()
                
                // Status-indikator
                HStack(spacing: 4) {
                    Circle()
                        .fill(manager.positionsStatus.färg)
                        .frame(width: 8, height: 8)
                    Text(manager.positionsStatus.text)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.white.opacity(0.1))
                .cornerRadius(12)
            }
            .padding()
            
            // Kartvisning
            GeometryReader { geo in
                ZStack {
                    if let img = manager.kartBild {
                        Image(uiImage: img)
                            .resizable()
                            .scaledToFit()
                            .overlay(
                                GeometryReader { imgGeo in
                                    // Kundens position (blå prick)
                                    if let pixel = manager.kundPixel {
                                        let visaPos = pixelTillVy(
                                            pixel: pixel,
                                            imgSize: img.size,
                                            vySize: imgGeo.size
                                        )
                                        
                                        // Riktnings-kon (bakom pricken)
                                        riktningsKon(
                                            mitt: visaPos,
                                            riktningRad: manager.kundRiktningRad
                                        )
                                        
                                        // Blå prick
                                        ZStack {
                                            Circle()
                                                .fill(Color.blue.opacity(0.3))
                                                .frame(width: 40, height: 40)
                                                .scaleEffect(manager.pulsAnimation ? 1.5 : 1.0)
                                                .animation(
                                                    .easeInOut(duration: 1.5).repeatForever(autoreverses: true),
                                                    value: manager.pulsAnimation
                                                )
                                            Circle()
                                                .fill(Color.blue)
                                                .frame(width: 16, height: 16)
                                            Circle()
                                                .stroke(Color.white, lineWidth: 3)
                                                .frame(width: 16, height: 16)
                                        }
                                        .position(visaPos)
                                    }
                                }
                            )
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .onAppear {
                manager.pulsAnimation = true
            }
            
            // Bottom-panel
            bottomPanel
        }
    }
    
    func riktningsKon(mitt: CGPoint, riktningRad: Float) -> some View {
        Path { path in
            let längd: CGFloat = 40
            let bredd: CGFloat = 30
            
            // Rita en triangel/kon som pekar i riktningen
            let spets = CGPoint(
                x: mitt.x + cos(CGFloat(riktningRad)) * längd,
                y: mitt.y + sin(CGFloat(riktningRad)) * längd
            )
            
            let vinkel1 = CGFloat(riktningRad) + .pi / 2
            let vinkel2 = CGFloat(riktningRad) - .pi / 2
            
            let bas1 = CGPoint(
                x: mitt.x + cos(vinkel1) * bredd / 2,
                y: mitt.y + sin(vinkel1) * bredd / 2
            )
            let bas2 = CGPoint(
                x: mitt.x + cos(vinkel2) * bredd / 2,
                y: mitt.y + sin(vinkel2) * bredd / 2
            )
            
            path.move(to: spets)
            path.addLine(to: bas1)
            path.addLine(to: bas2)
            path.closeSubpath()
        }
        .fill(Color.blue.opacity(0.4))
    }
    
    var bottomPanel: some View {
        VStack(spacing: 12) {
            // Position-info
            if manager.harPosition {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Position (VPS)")
                            .font(.caption2)
                            .foregroundColor(.gray)
                        Text(String(format: "%.1f, %.1f m",
                                    manager.kundKartX,
                                    manager.kundKartZ))
                            .font(.system(.caption, design: .monospaced))
                            .foregroundColor(.white)
                    }
                    Spacer()
                    if let pixel = manager.kundPixel {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("Pixel")
                                .font(.caption2)
                                .foregroundColor(.gray)
                            Text(String(format: "%.0f, %.0f",
                                        pixel.x, pixel.y))
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(.white)
                        }
                    }
                }
                .padding(.horizontal)
            }
            
            // Uppdatera-knapp
            Button {
                Task { await manager.görVpsFix() }
            } label: {
                HStack {
                    if manager.gör_vps_fix {
                        ProgressView().tint(.white).scaleEffect(0.8)
                        Text("Hittar position...")
                    } else {
                        Image(systemName: "location.circle.fill")
                        Text(manager.harPosition ? "Uppdatera position" : "Hitta min position")
                            .bold()
                    }
                }
                .foregroundColor(.white)
                .padding()
                .frame(maxWidth: .infinity)
                .background(Color.blue)
                .cornerRadius(12)
            }
            .disabled(manager.gör_vps_fix)
            .padding(.horizontal)
            
            if let info = manager.statusText {
                Text(info)
                    .font(.caption)
                    .foregroundColor(.yellow)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
        }
        .padding(.bottom, 20)
        .background(Color.black.opacity(0.3))
    }
    
    // ─── Koordinattransformation ───
    
    func pixelTillVy(pixel: CGPoint, imgSize: CGSize, vySize: CGSize) -> CGPoint {
        let skalaX = vySize.width / imgSize.width
        let skalaY = vySize.height / imgSize.height
        let skala = min(skalaX, skalaY)  // scaledToFit använder minsta skalan
        
        let renderadBredd = imgSize.width * skala
        let renderadHöjd = imgSize.height * skala
        let offsetX = (vySize.width - renderadBredd) / 2
        let offsetY = (vySize.height - renderadHöjd) / 2
        
        return CGPoint(
            x: pixel.x * skala + offsetX,
            y: pixel.y * skala + offsetY
        )
    }
}


// ─────────────────────────────────────────────────────────────────
// MANAGER
// ─────────────────────────────────────────────────────────────────

@MainActor
class NavigationKartManager: NSObject, ObservableObject, ARSessionDelegate {
    var butikId: String = ""
    
    @Published var kartBild: UIImage?
    @Published var fel: String?
    @Published var harPosition: Bool = false
    @Published var kundKartX: Float = 0
    @Published var kundKartZ: Float = 0
    @Published var kundPixel: CGPoint?
    @Published var kundRiktningRad: Float = 0   // Radianer, 0 = åt höger (+x pixel)
    @Published var gör_vps_fix: Bool = false
    @Published var statusText: String?
    @Published var pulsAnimation: Bool = false
    @Published var positionsStatus: PositionsStatus = .ingen
    
    private var arSession: ARSession?
    private var senasteArkitX: Float = 0
    private var senasteArkitZ: Float = 0
    private var harArkitReferens: Bool = false
    
    // Offset mellan ARKit-frame och kartans yaw (kalibreras vid VPS-fix)
    private var mapToArkitYawOffset: Float = 0
    private var mapToArkitKalibrerad: Bool = false
    
    private var lastUpdateTime: TimeInterval = 0
    
    enum PositionsStatus {
        case ingen, osäker, ok, nyss_uppdaterad
        
        var text: String {
            switch self {
            case .ingen: return "Ingen position"
            case .osäker: return "Osäker"
            case .ok: return "OK"
            case .nyss_uppdaterad: return "Uppdaterad"
            }
        }
        
        var färg: Color {
            switch self {
            case .ingen: return .gray
            case .osäker: return .orange
            case .ok: return .green
            case .nyss_uppdaterad: return .cyan
            }
        }
    }
    
    // ─── AR-SESSION ───
    
    func startaARSession() {
        let session = ARSession()
        session.delegate = self
        
        let config = ARWorldTrackingConfiguration()
        config.planeDetection = [.horizontal, .vertical]
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            config.frameSemantics = [.sceneDepth]
        }
        
        session.run(config, options: [.resetTracking, .removeExistingAnchors])
        arSession = session
        
        // Auto-gör VPS-fix efter 2 sekunder (ge ARKit tid att stabilisera)
        Task {
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            await görVpsFix()
        }
    }
    
    func stoppaARSession() {
        arSession?.pause()
    }
    
    // ─── ARSessionDelegate: kontinuerlig position-uppdatering ───
    
    nonisolated func session(_ session: ARSession, didUpdate frame: ARFrame) {
        Task { @MainActor in
            let now = CACurrentMediaTime()
            if now - lastUpdateTime < 0.1 { return }
            lastUpdateTime = now
            
            guard harPosition && harArkitReferens && mapToArkitKalibrerad else { return }
            
            // ARKit-delta för kontinuerlig positionsuppdatering
            let arkitX = frame.camera.transform.columns.3.x
            let arkitZ = frame.camera.transform.columns.3.z
            
            let deltaArkitX = arkitX - senasteArkitX
            let deltaArkitZ = arkitZ - senasteArkitZ
            
            let cosOffset = cos(mapToArkitYawOffset)
            let sinOffset = sin(mapToArkitYawOffset)
            let deltaKartX = deltaArkitX * cosOffset + deltaArkitZ * sinOffset
            let deltaKartZ = -deltaArkitX * sinOffset + deltaArkitZ * cosOffset
            
            kundKartX += deltaKartX
            kundKartZ += deltaKartZ
            senasteArkitX = arkitX
            senasteArkitZ = arkitZ
            
            // Beräkna kompassriktning (vilket håll kunden tittar)
            let arkitYaw = atan2(-frame.camera.transform.columns.2.x,
                                  -frame.camera.transform.columns.2.z)
            let kartYaw = arkitYaw - mapToArkitYawOffset
            // kartYaw är i kartans "världskoordinater". Vi måste omvandla till bildkoordinater.
            // Kartans X ökar åt höger, Z ökar framåt (samma som VPS).
            // Om kartYaw = 0 betyder det kunden tittar i +Z-riktningen.
            // På bilden: +Z kan motsvara uppåt eller nedåt, beror på kalibrering.
            // För nu: använd kartYaw som grov approximation av pil-riktning.
            kundRiktningRad = -kartYaw  // Vänder tecknet eftersom bild-Y är inverterad
            
            // Uppdatera pixelposition
            await uppdateraPixelPosition()
            
            // Sätt status till osäker efter ett tag utan VPS-fix
            if now - senasteFixTid > 30 {
                positionsStatus = .osäker
            }
        }
    }
    
    private var senasteFixTid: TimeInterval = 0
    
    // ─── LADDA KARTBILD ───
    
    func laddaKartbild() {
        guard let url = URL(string: "\(PulsArConfig.serverURL)/butik/\(butikId)/kartbild") else {
            fel = "Ogiltig server-URL"
            return
        }
        
        Task {
            do {
                let (data, response) = try await URLSession.shared.data(from: url)
                guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                    fel = "Kartbild ej tillgänglig. Är butiken kalibrerad?"
                    return
                }
                guard let img = UIImage(data: data) else {
                    fel = "Ogiltig bildfil"
                    return
                }
                kartBild = img
            } catch {
                fel = "Fel: \(error.localizedDescription)"
            }
        }
    }
    
    // ─── VPS-FIX ───
    
    func görVpsFix() async {
        guard !gör_vps_fix else { return }
        guard let session = arSession,
              let frame = session.currentFrame else {
            statusText = "AR-session ej redo"
            return
        }
        
        gör_vps_fix = true
        statusText = "Hittar din position..."
        
        // Ta bild
        let pixelBuffer = frame.capturedImage
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent),
              let bildData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.85) else {
            statusText = "Kunde inte ta bild"
            gör_vps_fix = false
            return
        }
        
        // ARKit yaw vid bildtillfället
        let arkitYawVidBild = atan2(-frame.camera.transform.columns.2.x,
                                     -frame.camera.transform.columns.2.z)
        
        // Skicka till VPS
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
            
            var request = URLRequest(url: URL(string: "\(PulsArConfig.serverURL)/lokalisera/")!)
            request.httpMethod = "POST"
            request.httpBody = body
            request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 15
            
            let (data, _) = try await URLSession.shared.data(for: request)
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  json["hittad"] as? Bool == true else {
                statusText = "Kunde inte hitta position. Rikta kameran mot hyllor."
                gör_vps_fix = false
                return
            }
            
            let vpsX = (json["x"] as? NSNumber)?.floatValue ?? 0
            let vpsZ = (json["z"] as? NSNumber)?.floatValue ?? 0
            let vpsYaw = (json["yaw"] as? NSNumber)?.floatValue ?? 0  // grader
            let inliers = (json["inliers"] as? NSNumber)?.intValue ?? 0
            
            guard inliers >= 20 else {
                statusText = "För svag match (\(inliers) inliers). Prova igen."
                gör_vps_fix = false
                return
            }
            
            // Uppdatera position
            kundKartX = vpsX
            kundKartZ = vpsZ
            harPosition = true
            senasteFixTid = CACurrentMediaTime()
            
            // Kalibrera yaw-offset för ARKit-delta
            let vpsYawRad = vpsYaw * .pi / 180.0
            mapToArkitYawOffset = arkitYawVidBild - vpsYawRad
            mapToArkitKalibrerad = true
            
            // Spara ARKit-referens
            senasteArkitX = frame.camera.transform.columns.3.x
            senasteArkitZ = frame.camera.transform.columns.3.z
            harArkitReferens = true
            
            positionsStatus = .nyss_uppdaterad
            statusText = "Position hittad! (\(inliers) inliers)"
            
            // Hämta pixelposition från servern
            await uppdateraPixelPosition()
            
            // Rensa status efter 3 sekunder
            Task {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                if positionsStatus == .nyss_uppdaterad {
                    positionsStatus = .ok
                    statusText = nil
                }
            }
        } catch {
            statusText = "Nätverksfel: \(error.localizedDescription)"
        }
        
        gör_vps_fix = false
    }
    
    // ─── PIXEL-TRANSLATION ───
    
    func uppdateraPixelPosition() async {
        guard harPosition else { return }
        
        do {
            guard let url = URL(string: "\(PulsArConfig.serverURL)/butik/\(butikId)/vps-till-pixel") else {
                return
            }
            
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let body: [String: Any] = ["x": kundKartX, "z": kundKartZ]
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.timeoutInterval = 5
            
            let (data, _) = try await URLSession.shared.data(for: request)
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                return
            }
            
            if json["fel"] != nil {
                statusText = "Butiken ej kalibrerad"
                return
            }
            
            let px = (json["pixel_x"] as? NSNumber)?.doubleValue ?? 0
            let py = (json["pixel_y"] as? NSNumber)?.doubleValue ?? 0
            
            kundPixel = CGPoint(x: px, y: py)
        } catch {
            // Tyst — kan hända ofta om nätverk sackar
        }
    }
}