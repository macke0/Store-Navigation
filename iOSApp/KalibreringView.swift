//
//  KalibreringView.swift
//  PulsAr
//
//  Uppdaterad: zoom + pan på kartan för precis kalibrering.
//

import SwiftUI
import ARKit
import Combine

struct KalibreringView: View {
    let butikId: String
    
    @StateObject private var manager = KalibreringManager()
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            
            if manager.kartBild == nil {
                laddningsVy
            } else if manager.sparatResultat != nil {
                resultatVy
            } else {
                kalibreringsVy
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
    
    var laddningsVy: some View {
        VStack(spacing: 20) {
            ProgressView().scaleEffect(2).tint(.white)
            Text("Laddar butikskarta...")
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
    
    var kalibreringsVy: some View {
        VStack(spacing: 0) {
            HStack {
                Button { dismiss() } label: {
                    Image(systemName: "xmark")
                        .foregroundColor(.white)
                        .padding(10)
                        .background(Color.white.opacity(0.2))
                        .clipShape(Circle())
                }
                Spacer()
                Text("Kalibrera \(butikId)")
                    .font(.headline)
                    .foregroundColor(.white)
                Spacer()
                Button {
                    manager.ångraSenaste()
                } label: {
                    Image(systemName: "arrow.uturn.backward")
                        .foregroundColor(manager.punkter.isEmpty ? .gray : .white)
                        .padding(10)
                        .background(Color.white.opacity(0.2))
                        .clipShape(Circle())
                }
                .disabled(manager.punkter.isEmpty)
            }
            .padding()
            
            statusBar
            
            ZoombarKarta(
                bild: manager.kartBild!,
                punkter: manager.punkter,
                väntarPåPixel: manager.väntarPåPixel,
                onTap: { pixel in
                    if manager.väntarPåPixel {
                        manager.registreraPixel(pixelX: Float(pixel.x), pixelY: Float(pixel.y))
                    }
                }
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            
            kontrollKnappar
                .padding()
        }
    }
    
    var statusBar: some View {
        HStack(spacing: 16) {
            VStack(spacing: 2) {
                Text("\(manager.punkter.count)/3")
                    .font(.title2.bold())
                    .foregroundColor(manager.punkter.count >= 3 ? .green : .white)
                Text("punkter")
                    .font(.caption2)
                    .foregroundColor(.gray)
            }
            Divider().frame(height: 30).background(Color.gray)
            VStack(spacing: 2) {
                Text(manager.nuvarandeVpsKoord)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(manager.harVpsFix ? .cyan : .gray)
                Text("VPS")
                    .font(.caption2)
                    .foregroundColor(.gray)
            }
            Divider().frame(height: 30).background(Color.gray)
            Text(manager.instruktion)
                .font(.caption)
                .foregroundColor(.yellow)
                .multilineTextAlignment(.leading)
                .lineLimit(3)
            Spacer()
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color.white.opacity(0.1))
    }
    
    var kontrollKnappar: some View {
        VStack(spacing: 12) {
            if manager.väntarPåPixel {
                Text("👆 Zooma in och tryck exakt där du står på kartan")
                    .foregroundColor(.yellow)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(Color.yellow.opacity(0.2))
                    .cornerRadius(12)
                
                Button {
                    manager.avbrytRegistrering()
                } label: {
                    Text("Avbryt")
                        .foregroundColor(.white)
                        .padding()
                        .frame(maxWidth: .infinity)
                        .background(Color.gray)
                        .cornerRadius(12)
                }
            } else {
                Button {
                    manager.startaNyPunkt()
                } label: {
                    HStack {
                        Image(systemName: "camera.viewfinder")
                        Text("Kalibrera punkt \(manager.punkter.count + 1)")
                            .bold()
                    }
                    .foregroundColor(.white)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(Color.blue)
                    .cornerRadius(12)
                }
                .disabled(manager.punkter.count >= 10)
                
                if manager.punkter.count >= 3 {
                    Button {
                        Task { await manager.sparaKalibrering() }
                    } label: {
                        HStack {
                            if manager.sparar {
                                ProgressView().tint(.white)
                            } else {
                                Image(systemName: "checkmark.circle.fill")
                            }
                            Text(manager.sparar ? "Sparar..." : "Spara kalibrering")
                                .bold()
                        }
                        .foregroundColor(.white)
                        .padding()
                        .frame(maxWidth: .infinity)
                        .background(Color.green)
                        .cornerRadius(12)
                    }
                    .disabled(manager.sparar)
                }
            }
        }
    }
    
    var resultatVy: some View {
        VStack(spacing: 20) {
            if let r = manager.sparatResultat {
                Image(systemName: r.ok ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .font(.system(size: 80))
                    .foregroundColor(r.ok ? .green : .red)
                
                Text(r.ok ? "Kalibrering sparad!" : "Kalibrering misslyckades")
                    .font(.title.bold())
                    .foregroundColor(.white)
                
                if r.ok {
                    VStack(alignment: .leading, spacing: 8) {
                        infoRad("Antal punkter:", "\(r.antalPunkter)")
                        infoRad("Typ:", r.transformType)
                        infoRad("Medelfel:", "\(r.medelfelPixlar) px")
                        infoRad("Max fel:", "\(r.maxfelPixlar) px")
                    }
                    .padding()
                    .background(Color.white.opacity(0.1))
                    .cornerRadius(12)
                    
                    let bedömning = bedömKvalitet(medelfel: r.medelfelPixlar)
                    Text(bedömning)
                        .foregroundColor(.yellow)
                        .multilineTextAlignment(.center)
                        .padding()
                }
                
                Button {
                    dismiss()
                } label: {
                    Text("Stäng")
                        .bold()
                        .foregroundColor(.white)
                        .padding()
                        .frame(maxWidth: .infinity)
                        .background(Color.blue)
                        .cornerRadius(12)
                }
                .padding(.horizontal)
            }
        }
        .padding()
    }
    
    func infoRad(_ titel: String, _ värde: String) -> some View {
        HStack {
            Text(titel).foregroundColor(.gray)
            Spacer()
            Text(värde).foregroundColor(.white).font(.system(.body, design: .monospaced))
        }
        .frame(maxWidth: 280)
    }
    
    func bedömKvalitet(medelfel: Float) -> String {
        if medelfel < 10 { return "✨ Utmärkt kvalitet" }
        if medelfel < 30 { return "✅ Bra kvalitet" }
        if medelfel < 60 { return "⚠️ OK kvalitet — överväg att kalibrera om" }
        return "❌ Dålig kvalitet — kalibrera om med noggrannare punkter"
    }
}


// ─────────────────────────────────────────────────────────────────
// ZOOMBAR KARTA
// ─────────────────────────────────────────────────────────────────

struct ZoombarKarta: View {
    let bild: UIImage
    let punkter: [KalibreringsPunkt]
    let väntarPåPixel: Bool
    let onTap: (CGPoint) -> Void
    
    @State private var skala: CGFloat = 1.0
    @State private var senasteSkala: CGFloat = 1.0
    @State private var offset: CGSize = .zero
    @State private var senasteOffset: CGSize = .zero
    
    private let minSkala: CGFloat = 1.0
    private let maxSkala: CGFloat = 10.0
    
    var body: some View {
        GeometryReader { geo in
            let basStorlek = beräknaBasStorlek(bildStorlek: bild.size, vyStorlek: geo.size)
            let aktuellBredd = basStorlek.width * skala
            let aktuellHöjd = basStorlek.height * skala
            
            ZStack {
                Color.black
                
                ZStack {
                    Image(uiImage: bild)
                        .resizable()
                        .frame(width: aktuellBredd, height: aktuellHöjd)
                    
                    ForEach(Array(punkter.enumerated()), id: \.offset) { idx, p in
                        let positionPåSkalad = CGPoint(
                            x: CGFloat(p.pixelX) / bild.size.width * aktuellBredd,
                            y: CGFloat(p.pixelY) / bild.size.height * aktuellHöjd
                        )
                        
                        ZStack {
                            Circle()
                                .fill(Color.green.opacity(0.3))
                                .frame(width: 30, height: 30)
                            Circle()
                                .stroke(Color.green, lineWidth: 2)
                                .frame(width: 30, height: 30)
                            Text("\(idx + 1)")
                                .foregroundColor(.white)
                                .font(.caption.bold())
                        }
                        .position(positionPåSkalad)
                    }
                }
                .frame(width: aktuellBredd, height: aktuellHöjd)
                .offset(offset)
                .gesture(
                    SimultaneousGesture(
                        MagnificationGesture()
                            .onChanged { värde in
                                let nyEtt = senasteSkala * värde
                                skala = min(max(nyEtt, minSkala), maxSkala)
                            }
                            .onEnded { _ in
                                senasteSkala = skala
                                begränsaOffset(vyStorlek: geo.size, basStorlek: basStorlek)
                            },
                        
                        DragGesture()
                            .onChanged { värde in
                                offset = CGSize(
                                    width: senasteOffset.width + värde.translation.width,
                                    height: senasteOffset.height + värde.translation.height
                                )
                            }
                            .onEnded { _ in
                                begränsaOffset(vyStorlek: geo.size, basStorlek: basStorlek)
                                senasteOffset = offset
                            }
                    )
                )
                .onTapGesture { tappPunkt in
                    guard väntarPåPixel else { return }
                    let pixelX = (tappPunkt.x / aktuellBredd) * bild.size.width
                    let pixelY = (tappPunkt.y / aktuellHöjd) * bild.size.height
                    onTap(CGPoint(x: pixelX, y: pixelY))
                }
                
                VStack {
                    HStack {
                        Spacer()
                        Text(String(format: "%.1fx", skala))
                            .font(.caption.bold())
                            .foregroundColor(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.black.opacity(0.6))
                            .cornerRadius(6)
                            .padding()
                    }
                    Spacer()
                    
                    if skala > 1.05 || offset != .zero {
                        Button {
                            withAnimation(.spring()) {
                                skala = 1.0
                                senasteSkala = 1.0
                                offset = .zero
                                senasteOffset = .zero
                            }
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "arrow.up.left.and.down.right.magnifyingglass")
                                Text("Återställ").font(.caption)
                            }
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(Color.white.opacity(0.2))
                            .foregroundColor(.white)
                            .cornerRadius(8)
                        }
                        .padding(.bottom, 12)
                    }
                }
            }
            .clipped()
        }
    }
    
    func beräknaBasStorlek(bildStorlek: CGSize, vyStorlek: CGSize) -> CGSize {
        let bildRatio = bildStorlek.width / bildStorlek.height
        let vyRatio = vyStorlek.width / vyStorlek.height
        
        if bildRatio > vyRatio {
            return CGSize(width: vyStorlek.width, height: vyStorlek.width / bildRatio)
        } else {
            return CGSize(width: vyStorlek.height * bildRatio, height: vyStorlek.height)
        }
    }
    
    func begränsaOffset(vyStorlek: CGSize, basStorlek: CGSize) {
        let aktuellBredd = basStorlek.width * skala
        let aktuellHöjd = basStorlek.height * skala
        
        let maxX = max(0, (aktuellBredd - vyStorlek.width) / 2)
        let maxY = max(0, (aktuellHöjd - vyStorlek.height) / 2)
        
        offset.width = min(max(offset.width, -maxX), maxX)
        offset.height = min(max(offset.height, -maxY), maxY)
        senasteOffset = offset
    }
}


// ─────────────────────────────────────────────────────────────────
// MANAGER
// ─────────────────────────────────────────────────────────────────

@MainActor
class KalibreringManager: NSObject, ObservableObject, ARSessionDelegate {
    var butikId: String = ""
    
    @Published var kartBild: UIImage?
    @Published var fel: String?
    @Published var punkter: [KalibreringsPunkt] = []
    @Published var vpsKoordiat: (x: Float, z: Float)?
    @Published var väntarPåPixel: Bool = false
    @Published var sparar: Bool = false
    @Published var sparatResultat: KalibreringsResultat?
    @Published var nuvarandeVpsKoord: String = "—"
    @Published var harVpsFix: Bool = false
    @Published var instruktion: String = "Tryck på 'Kalibrera punkt 1' för att börja"
    
    private var arSession: ARSession?
    
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
    }
    
    func stoppaARSession() {
        arSession?.pause()
    }
    
    func laddaKartbild() {
        guard let url = URL(string: "\(PulsArConfig.serverURL)/butik/\(butikId)/kartbild") else {
            fel = "Ogiltig server-URL"
            return
        }
        Task {
            do {
                let (data, response) = try await URLSession.shared.data(from: url)
                guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                    fel = "Kunde inte hämta kartbild (ingen uppladdad?)"
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
    
    func startaNyPunkt() {
        instruktion = "Riktar kameran mot hyllan... gör VPS-fix"
        Task { await görVpsFix() }
    }
    
    func görVpsFix() async {
        guard let session = arSession,
              let frame = session.currentFrame else {
            instruktion = "AR-session ej redo — vänta några sekunder och prova igen"
            return
        }
        
        let pixelBuffer = frame.capturedImage
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent),
              let bildData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.85) else {
            instruktion = "Kunde inte ta bild"
            return
        }
        
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
                instruktion = "VPS: ingen match. Rikta kameran mot hyllor och prova igen."
                return
            }
            
            let x = (json["x"] as? NSNumber)?.floatValue ?? 0
            let z = (json["z"] as? NSNumber)?.floatValue ?? 0
            let inliers = (json["inliers"] as? NSNumber)?.intValue ?? 0
            
            guard inliers >= 20 else {
                instruktion = "VPS-fix för svag (\(inliers) inliers). Prova igen med bättre vinkel."
                return
            }
            
            vpsKoordiat = (x, z)
            harVpsFix = true
            nuvarandeVpsKoord = String(format: "(%.1f, %.1f)", x, z)
            väntarPåPixel = true
            instruktion = "VPS-fix ok (\(inliers) inliers). Zooma in och tryck på exakt plats."
        } catch {
            instruktion = "Nätverksfel: \(error.localizedDescription)"
        }
    }
    
    func registreraPixel(pixelX: Float, pixelY: Float) {
        guard let (x, z) = vpsKoordiat else { return }
        
        let punkt = KalibreringsPunkt(
            vpsX: x, vpsZ: z,
            pixelX: pixelX, pixelY: pixelY
        )
        punkter.append(punkt)
        
        väntarPåPixel = false
        vpsKoordiat = nil
        harVpsFix = false
        nuvarandeVpsKoord = "—"
        
        if punkter.count >= 3 {
            instruktion = "Du kan spara nu, eller lägg till fler punkter för bättre precision"
        } else {
            instruktion = "Punkt \(punkter.count) sparad. Gå till nästa plats och kalibrera."
        }
    }
    
    func avbrytRegistrering() {
        väntarPåPixel = false
        vpsKoordiat = nil
        harVpsFix = false
        nuvarandeVpsKoord = "—"
        instruktion = "Avbruten. Tryck 'Kalibrera punkt' för att börja om."
    }
    
    func ångraSenaste() {
        if !punkter.isEmpty {
            punkter.removeLast()
            instruktion = "Senaste punkten borttagen"
        }
    }
    
    func sparaKalibrering() async {
        guard punkter.count >= 3 else { return }
        sparar = true
        
        let refpunkter = punkter.map { p -> [String: Any] in
            return [
                "vps": [p.vpsX, p.vpsZ],
                "pixel": [p.pixelX, p.pixelY]
            ]
        }
        
        let body: [String: Any] = ["referenspunkter": refpunkter]
        
        do {
            guard let url = URL(string: "\(PulsArConfig.serverURL)/butik/\(butikId)/kalibrera") else {
                sparar = false
                return
            }
            
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            
            let (data, _) = try await URLSession.shared.data(for: request)
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                sparatResultat = KalibreringsResultat(ok: false, antalPunkter: 0, transformType: "", medelfelPixlar: 0, maxfelPixlar: 0)
                sparar = false
                return
            }
            
            let ok = json["ok"] as? Bool ?? false
            sparatResultat = KalibreringsResultat(
                ok: ok,
                antalPunkter: (json["antal_punkter"] as? NSNumber)?.intValue ?? punkter.count,
                transformType: json["transform_type"] as? String ?? "",
                medelfelPixlar: (json["medelfel_pixlar"] as? NSNumber)?.floatValue ?? 0,
                maxfelPixlar: (json["maxfel_pixlar"] as? NSNumber)?.floatValue ?? 0
            )
        } catch {
            sparatResultat = KalibreringsResultat(ok: false, antalPunkter: 0, transformType: "", medelfelPixlar: 0, maxfelPixlar: 0)
        }
        
        sparar = false
    }
}

struct KalibreringsPunkt {
    let vpsX: Float
    let vpsZ: Float
    let pixelX: Float
    let pixelY: Float
}

struct KalibreringsResultat {
    let ok: Bool
    let antalPunkter: Int
    let transformType: String
    let medelfelPixlar: Float
    let maxfelPixlar: Float
}
