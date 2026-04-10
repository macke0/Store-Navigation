//
//  VPSTestView.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-04-01.
//


//
//  VPSTestView.swift
//  PulsAr
//
//  Testvy för att mäta VPS-accuracy på kända positioner
//

import SwiftUI
import ARKit
import Combine

// ─────────────────────────────────────────────────────────────────
// HUVUDVY
// ─────────────────────────────────────────────────────────────────

struct VPSTestView: View {
    @StateObject private var tester = VPSTester()
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        NavigationStack {
            ZStack {
                // AR-kamera
                VPSTestKameraVy(tester: tester)
                    .ignoresSafeArea()
                
                VStack {
                    // Status
                    statusBar
                    
                    Spacer()
                    
                    // Resultat
                    if !tester.testResultat.isEmpty {
                        resultatKort
                    }
                    
                    // Kontroller
                    kontrollPanel
                }
                .padding()
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Stäng") { dismiss() }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Exportera") { tester.exporteraResultat() }
                        .disabled(tester.testResultat.isEmpty)
                }
            }
        }
    }
    
    // ─────────────────────────────────────────────
    // STATUSBAR
    // ─────────────────────────────────────────────
    
    private var statusBar: some View {
        HStack {
            // VPS Status
            HStack(spacing: 6) {
                Circle()
                    .fill(tester.ärLokaliserad ? Color.green : Color.orange)
                    .frame(width: 10, height: 10)
                
                Text(tester.statusText)
                    .font(.caption)
                    .foregroundColor(.white)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(.ultraThinMaterial)
            .cornerRadius(20)
            
            Spacer()
            
            // Antal tester
            Text("\(tester.testResultat.count) test")
                .font(.caption)
                .foregroundColor(.white)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(.ultraThinMaterial)
                .cornerRadius(20)
        }
    }
    
    // ─────────────────────────────────────────────
    // RESULTATKORT
    // ─────────────────────────────────────────────
    
    private var resultatKort: some View {
        VStack(spacing: 12) {
            // Sammanfattning
            HStack(spacing: 20) {
                statistikPill(
                    titel: "Träffsäkerhet",
                    värde: String(format: "%.0f%%", tester.träffsäkerhet * 100),
                    färg: tester.träffsäkerhet > 0.7 ? .green : .orange
                )
                
                statistikPill(
                    titel: "Medelfel",
                    värde: String(format: "%.2fm", tester.medelfel),
                    färg: tester.medelfel < 0.5 ? .green : .orange
                )
                
                statistikPill(
                    titel: "Konfidens",
                    värde: tester.medelKonfidens,
                    färg: .blue
                )
            }
            
            // Senaste test
            if let senaste = tester.testResultat.last {
                Divider()
                
                VStack(spacing: 4) {
                    Text("Senaste test")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    
                    HStack {
                        VStack(alignment: .leading) {
                            Text("Verklig: (\(String(format: "%.2f", senaste.verkligX)), \(String(format: "%.2f", senaste.verkligZ)))")
                            Text("VPS: (\(String(format: "%.2f", senaste.vpsX)), \(String(format: "%.2f", senaste.vpsZ)))")
                        }
                        .font(.caption)
                        
                        Spacer()
                        
                        VStack(alignment: .trailing) {
                            Text("Fel: \(String(format: "%.2f", senaste.fel))m")
                                .foregroundColor(senaste.fel < 0.5 ? .green : .orange)
                            Text(senaste.konfidens)
                                .foregroundColor(.secondary)
                        }
                        .font(.caption)
                    }
                }
            }
        }
        .padding()
        .background(.ultraThinMaterial)
        .cornerRadius(16)
    }
    
    private func statistikPill(titel: String, värde: String, färg: Color) -> some View {
        VStack(spacing: 4) {
            Text(värde)
                .font(.headline)
                .foregroundColor(färg)
            Text(titel)
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
    }
    
    // ─────────────────────────────────────────────
    // KONTROLLPANEL
    // ─────────────────────────────────────────────
    
    private var kontrollPanel: some View {
        VStack(spacing: 16) {
            // Instruktion
            Text("Stå på en känd position och tryck 'Markera'")
                .font(.caption)
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
            
            HStack(spacing: 16) {
                // Markera position
                Button(action: { tester.markeraStartPosition() }) {
                    VStack(spacing: 4) {
                        Image(systemName: "mappin.and.ellipse")
                            .font(.title2)
                        Text("Markera")
                            .font(.caption)
                    }
                    .foregroundColor(.white)
                    .frame(width: 80, height: 70)
                    .background(Color.blue)
                    .cornerRadius(12)
                }
                
                // Testa VPS
                Button(action: { tester.testaVPS() }) {
                    VStack(spacing: 4) {
                        Image(systemName: tester.testar ? "hourglass" : "location.viewfinder")
                            .font(.title2)
                        Text(tester.testar ? "Testar..." : "Testa VPS")
                            .font(.caption)
                    }
                    .foregroundColor(.white)
                    .frame(width: 80, height: 70)
                    .background(tester.testar ? Color.gray : Color.green)
                    .cornerRadius(12)
                }
                .disabled(tester.testar || !tester.harMarkerat)
                
                // Rensa
                Button(action: { tester.rensaResultat() }) {
                    VStack(spacing: 4) {
                        Image(systemName: "trash")
                            .font(.title2)
                        Text("Rensa")
                            .font(.caption)
                    }
                    .foregroundColor(.white)
                    .frame(width: 80, height: 70)
                    .background(Color.red.opacity(0.8))
                    .cornerRadius(12)
                }
                .disabled(tester.testResultat.isEmpty)
            }
            
            // ARKit-position
            if tester.harMarkerat {
                Text("Markerad position: (\(String(format: "%.2f", tester.markeradPosition.x)), \(String(format: "%.2f", tester.markeradPosition.z)))")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.7))
            }
        }
        .padding()
        .background(.ultraThinMaterial)
        .cornerRadius(16)
    }
}

// ─────────────────────────────────────────────────────────────────
// VPS TESTER
// ─────────────────────────────────────────────────────────────────

class VPSTester: NSObject, ObservableObject, ARSessionDelegate {
    private var session: ARSession?
    private var arView: ARSCNView?
    
    @Published var testResultat: [VPSTestResultat] = []
    @Published var ärLokaliserad = false
    @Published var testar = false
    @Published var harMarkerat = false
    @Published var statusText = "Startar..."
    @Published var markeradPosition: SIMD3<Float> = .zero
    
    let serverURL = PulsArConfig.serverURL
    
    // ─────────────────────────────────────────────
    // BERÄKNADE EGENSKAPER
    // ─────────────────────────────────────────────
    
    var träffsäkerhet: Double {
        guard !testResultat.isEmpty else { return 0 }
        let lyckade = testResultat.filter { $0.lyckad }.count
        return Double(lyckade) / Double(testResultat.count)
    }
    
    var medelfel: Double {
        guard !testResultat.isEmpty else { return 0 }
        let lyckade = testResultat.filter { $0.lyckad }
        guard !lyckade.isEmpty else { return 0 }
        let totalFel = lyckade.reduce(0.0) { $0 + $1.fel }
        return totalFel / Double(lyckade.count)
    }
    
    var medelKonfidens: String {
        let konfidenserCount = testResultat.reduce(into: [:]) { counts, r in
            counts[r.konfidens, default: 0] += 1
        }
        return konfidenserCount.max(by: { $0.value < $1.value })?.key ?? "-"
    }
    
    // ─────────────────────────────────────────────
    // AR SESSION
    // ─────────────────────────────────────────────
    
    func startaSession(arView: ARSCNView) {
        self.arView = arView
        self.session = arView.session
        arView.session.delegate = self
        
        let config = ARWorldTrackingConfiguration()
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            config.frameSemantics = .sceneDepth
        }
        arView.session.run(config)
        
        DispatchQueue.main.async {
            self.statusText = "Redo"
        }
    }
    
    func stoppaSession() {
        session?.pause()
    }
    
    // ─────────────────────────────────────────────
    // MARKERA POSITION
    // ─────────────────────────────────────────────
    
    func markeraStartPosition() {
        guard let frame = session?.currentFrame else { return }
        
        let t = frame.camera.transform
        markeradPosition = SIMD3<Float>(
            t.columns.3.x,
            t.columns.3.y,
            t.columns.3.z
        )
        
        harMarkerat = true
        statusText = "Position markerad"
        
        // Visuell feedback
        if let arView = arView {
            let sphere = SCNSphere(radius: 0.05)
            sphere.firstMaterial?.diffuse.contents = UIColor.blue
            let node = SCNNode(geometry: sphere)
            node.simdPosition = markeradPosition
            arView.scene.rootNode.addChildNode(node)
        }
    }
    
    // ─────────────────────────────────────────────
    // TESTA VPS
    // ─────────────────────────────────────────────
    
    func testaVPS() {
        guard let frame = session?.currentFrame else { return }
        guard harMarkerat else { return }
        
        testar = true
        statusText = "Lokaliserar..."
        
        // Konvertera frame till JPEG
        let pixelBuffer = frame.capturedImage
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent),
              let bildData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.8) else {
            DispatchQueue.main.async {
                self.testar = false
                self.statusText = "Fel: Kunde inte ta bild"
            }
            return
        }
        
        Task {
            await skickaTestFörfrågan(bildData: bildData)
        }
    }
    
    private func skickaTestFörfrågan(bildData: Data) async {
        do {
            let boundary = UUID().uuidString
            var body = Data()
            
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"bild\"; filename=\"test.jpg\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
            body.append(bildData)
            body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
            
            var request = URLRequest(url: URL(string: "\(serverURL)/debug/lokalisera")!)
            request.httpMethod = "POST"
            request.httpBody = body
            request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 10
            
            let (data, response) = try await URLSession.shared.data(for: request)
            
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                await MainActor.run {
                    self.registreraResultat(lyckad: false, vpsX: 0, vpsZ: 0, konfidens: "fel")
                }
                return
            }
            
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let hittad = json?["hittad"] as? Bool ?? false
            
            if hittad {
                let vpsX = (json?["x"] as? NSNumber)?.floatValue ?? 0
                let vpsZ = (json?["z"] as? NSNumber)?.floatValue ?? 0
                let konfidens = json?["konfidens"] as? String ?? "okänd"
                
                await MainActor.run {
                    self.registreraResultat(lyckad: true, vpsX: vpsX, vpsZ: vpsZ, konfidens: konfidens)
                }
            } else {
                await MainActor.run {
                    self.registreraResultat(lyckad: false, vpsX: 0, vpsZ: 0, konfidens: "ej hittad")
                }
            }
            
        } catch {
            await MainActor.run {
                self.registreraResultat(lyckad: false, vpsX: 0, vpsZ: 0, konfidens: "nätverksfel")
            }
        }
    }
    
    private func registreraResultat(lyckad: Bool, vpsX: Float, vpsZ: Float, konfidens: String) {
        let resultat = VPSTestResultat(
            verkligX: Double(markeradPosition.x),
            verkligZ: Double(markeradPosition.z),
            vpsX: Double(vpsX),
            vpsZ: Double(vpsZ),
            konfidens: konfidens,
            lyckad: lyckad,
            tidpunkt: Date()
        )
        
        testResultat.append(resultat)
        testar = false
        ärLokaliserad = lyckad
        
        if lyckad {
            statusText = String(format: "✓ Fel: %.2fm", resultat.fel)
        } else {
            statusText = "✗ Kunde inte lokalisera"
        }
    }
    
    // ─────────────────────────────────────────────
    // RENSA
    // ─────────────────────────────────────────────
    
    func rensaResultat() {
        testResultat = []
        statusText = "Resultat rensat"
    }
    
    // ─────────────────────────────────────────────
    // EXPORTERA
    // ─────────────────────────────────────────────
    
    func exporteraResultat() {
        var csv = "tidpunkt,verklig_x,verklig_z,vps_x,vps_z,fel,konfidens,lyckad\n"
        
        let formatter = ISO8601DateFormatter()
        
        for r in testResultat {
            csv += "\(formatter.string(from: r.tidpunkt)),"
            csv += "\(r.verkligX),\(r.verkligZ),"
            csv += "\(r.vpsX),\(r.vpsZ),"
            csv += "\(r.fel),\(r.konfidens),\(r.lyckad)\n"
        }
        
        // Spara till fil
        let filename = "vps_test_\(Int(Date().timeIntervalSince1970)).csv"
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(filename)
        
        do {
            try csv.write(to: url, atomically: true, encoding: .utf8)
            print("📊 Exporterat till: \(url)")
            // I en riktig app: Visa UIActivityViewController för delning
        } catch {
            print("❌ Export misslyckades: \(error)")
        }
    }
    
    // ARSession delegate
    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        // Kan användas för continuous tracking
    }
}

// ─────────────────────────────────────────────────────────────────
// TESTRESULTAT
// ─────────────────────────────────────────────────────────────────

struct VPSTestResultat: Identifiable {
    let id = UUID()
    let verkligX: Double
    let verkligZ: Double
    let vpsX: Double
    let vpsZ: Double
    let konfidens: String
    let lyckad: Bool
    let tidpunkt: Date
    
    var fel: Double {
        guard lyckad else { return .infinity }
        let dx = vpsX - verkligX
        let dz = vpsZ - verkligZ
        return sqrt(dx*dx + dz*dz)
    }
}

// ─────────────────────────────────────────────────────────────────
// KAMERAVY
// ─────────────────────────────────────────────────────────────────

struct VPSTestKameraVy: UIViewRepresentable {
    let tester: VPSTester
    
    func makeUIView(context: Context) -> ARSCNView {
        let arView = ARSCNView(frame: .zero)
        arView.automaticallyUpdatesLighting = true
        arView.scene = SCNScene()
        tester.startaSession(arView: arView)
        return arView
    }
    
    func updateUIView(_ uiView: ARSCNView, context: Context) {}
    
    static func dismantleUIView(_ uiView: ARSCNView, coordinator: ()) {
        uiView.session.pause()
    }
}

#Preview {
    VPSTestView()
}
