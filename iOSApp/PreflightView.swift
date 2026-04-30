//
//  PreflightView.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-04-25.
//


//
//  PreflightView.swift
//  PulsAr
//
//  Identifierar vilken karta användaren är vid innan skanning startar.
//  Tre möjliga utfall:
//    - match: automatiskt fortsätt till skanning med karta_id
//    - första_skanning: bekräftelseskärm
//    - okänd_plats: instruktion att gå till skannat område
//

import SwiftUI
import ARKit
import Combine

private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)


struct PreflightView: View {
    @StateObject private var manager = PreflightManager()
    @State private var navigeraTillSkanning = false
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            
            // Kameravy som bakgrund
            ARKameraVyPreflight(manager: manager)
                .ignoresSafeArea()
                .opacity(0.5)
            
            // Overlay
            VStack {
                // Header
                HStack {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .foregroundColor(.white)
                            .padding(10)
                            .background(Color.white.opacity(0.3))
                            .clipShape(Circle())
                    }
                    Spacer()
                    Text("Identifiera plats")
                        .font(.headline)
                        .foregroundColor(.white)
                    Spacer()
                    // Spacer för symmetri
                    Image(systemName: "xmark")
                        .foregroundColor(.clear)
                        .padding(10)
                }
                .padding()
                
                Spacer()
                
                // Status-kort
                statusKort
                    .padding(.horizontal)
                
                Spacer()
                
                // Action-knappar
                kontrollKnappar
                    .padding()
            }
        }
        .navigationBarHidden(true)
        .onAppear {
            manager.starta()
        }
        .onDisappear {
            manager.stoppa()
        }
        .background(
            // Navigerings-länk till skanning
            NavigationLink(
                destination: ButikSkanningView(kartaId: manager.matchadKartaId),
                isActive: $navigeraTillSkanning
            ) { EmptyView() }
        )
    }
    
    // ─────────────────────────────────────────────
    // STATUS-KORT
    // ─────────────────────────────────────────────
    
    var statusKort: some View {
        VStack(spacing: 16) {
            // Stor ikon baserat på status
            switch manager.status {
            case .söker:
                ZStack {
                    Circle()
                        .stroke(Color.white.opacity(0.3), lineWidth: 4)
                        .frame(width: 80, height: 80)
                    Circle()
                        .trim(from: 0, to: 0.3)
                        .stroke(Color.white, lineWidth: 4)
                        .frame(width: 80, height: 80)
                        .rotationEffect(.degrees(manager.spinnerVinkel))
                        .animation(.linear(duration: 1).repeatForever(autoreverses: false), value: manager.spinnerVinkel)
                }
                .onAppear { manager.spinnerVinkel = 360 }
                
            case .match:
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 70))
                    .foregroundColor(.green)
                
            case .förstaSkanning:
                Image(systemName: "plus.circle.fill")
                    .font(.system(size: 70))
                    .foregroundColor(.blue)
                
            case .okändPlats:
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 70))
                    .foregroundColor(.orange)
                
            case .fel:
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 70))
                    .foregroundColor(.red)
            }
            
            // Statustext
            Text(manager.statusTitel)
                .font(.title2.bold())
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
            
            Text(manager.statusBeskrivning)
                .font(.body)
                .foregroundColor(.white.opacity(0.8))
                .multilineTextAlignment(.center)
                .padding(.horizontal)
            
            // Diagnostik (under utveckling)
            if manager.status == .söker {
                Text("Försök \(manager.antalFörsök)")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.5))
            } else if manager.senasteInliers > 0 {
                Text("\(manager.senasteInliers) inliers")
                    .font(.caption.monospaced())
                    .foregroundColor(.white.opacity(0.5))
            }
        }
        .padding(24)
        .background(.ultraThinMaterial)
        .cornerRadius(20)
    }
    
    // ─────────────────────────────────────────────
    // KONTROLLKNAPPAR
    // ─────────────────────────────────────────────
    
    var kontrollKnappar: some View {
        VStack(spacing: 12) {
            switch manager.status {
            case .söker:
                Button {
                    manager.stoppa()
                    dismiss()
                } label: {
                    Text("Avbryt")
                        .foregroundColor(.white)
                        .padding()
                        .frame(maxWidth: .infinity)
                        .background(Color.gray.opacity(0.6))
                        .cornerRadius(12)
                }
                
            case .match:
                Button {
                    navigeraTillSkanning = true
                } label: {
                    HStack {
                        Image(systemName: "camera.viewfinder")
                        Text("Starta skanning")
                            .bold()
                    }
                    .foregroundColor(.white)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(icaRöd)
                    .cornerRadius(12)
                }
                
                Button { dismiss() } label: {
                    Text("Avbryt")
                        .foregroundColor(.white.opacity(0.6))
                        .padding()
                }
                
            case .förstaSkanning:
                VStack(spacing: 8) {
                    Text("Detta blir den första skanningen för butiken.")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                        .multilineTextAlignment(.center)
                    Text("Servern kommer skapa en ny karta som heter 'bromma_maxi'.")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                        .multilineTextAlignment(.center)
                }
                .padding(.bottom, 8)
                
                Button {
                    navigeraTillSkanning = true
                } label: {
                    HStack {
                        Image(systemName: "plus.circle.fill")
                        Text("Skapa ny karta")
                            .bold()
                    }
                    .foregroundColor(.white)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(Color.blue)
                    .cornerRadius(12)
                }
                
                Button { dismiss() } label: {
                    Text("Avbryt")
                        .foregroundColor(.white.opacity(0.6))
                        .padding()
                }
                
            case .okändPlats:
                Button {
                    manager.återupptaSökning()
                } label: {
                    HStack {
                        Image(systemName: "arrow.clockwise")
                        Text("Försök igen")
                            .bold()
                    }
                    .foregroundColor(.white)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(Color.orange)
                    .cornerRadius(12)
                }
                
                Button { dismiss() } label: {
                    Text("Avbryt")
                        .foregroundColor(.white.opacity(0.6))
                        .padding()
                }
                
            case .fel:
                Button {
                    manager.återupptaSökning()
                } label: {
                    Text("Försök igen")
                        .foregroundColor(.white)
                        .padding()
                        .frame(maxWidth: .infinity)
                        .background(Color.gray)
                        .cornerRadius(12)
                }
                
                Button { dismiss() } label: {
                    Text("Stäng")
                        .foregroundColor(.white.opacity(0.6))
                        .padding()
                }
            }
        }
    }
}


// ─────────────────────────────────────────────────────────────────
// MANAGER
// ─────────────────────────────────────────────────────────────────

@MainActor
class PreflightManager: NSObject, ObservableObject, ARSessionDelegate {
    @Published var status: PreflightStatus = .söker
    @Published var statusTitel: String = "Hittar din position..."
    @Published var statusBeskrivning: String = "Rikta kameran mot hyllorna i butiken"
    @Published var matchadKartaId: String? = nil
    @Published var senasteInliers: Int = 0
    @Published var antalFörsök: Int = 0
    @Published var spinnerVinkel: Double = 0
    
    var arSession: ARSession?
    private var söker = false
    private var senasteFörsök: TimeInterval = 0
    private let försökIntervall: TimeInterval = 1.5  // Försök var 1.5 sek
    
    enum PreflightStatus {
        case söker
        case match
        case förstaSkanning
        case okändPlats
        case fel
    }
    
    func starta() {
        söker = true
        status = .söker
        statusTitel = "Hittar din position..."
        statusBeskrivning = "Rikta kameran mot hyllorna i butiken"
        antalFörsök = 0
    }
    
    func stoppa() {
        söker = false
        arSession?.pause()
    }
    
    func återupptaSökning() {
        antalFörsök = 0
        starta()
    }
    
    // ─── ARSessionDelegate ───
    
    nonisolated func session(_ session: ARSession, didUpdate frame: ARFrame) {
        Task { @MainActor in
            guard söker else { return }
            
            let now = CACurrentMediaTime()
            if now - senasteFörsök < försökIntervall { return }
            senasteFörsök = now
            
            // Försök hitta position
            await försökPreflightFix(frame: frame)
        }
    }
    
    private func försökPreflightFix(frame: ARFrame) async {
        guard söker else { return }
        antalFörsök += 1
        
        // Ta bild
        let pixelBuffer = frame.capturedImage
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent),
              let bildData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.85) else {
            return
        }
        
        // Skicka till /preflight
        do {
            let boundary = UUID().uuidString
            var body = Data()
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"bild\"; filename=\"frame.jpg\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
            body.append(bildData)
            body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
            
            var request = URLRequest(url: URL(string: "\(PulsArConfig.serverURL)/preflight")!)
            request.httpMethod = "POST"
            request.httpBody = body
            request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 10
            
            let (data, _) = try await URLSession.shared.data(for: request)
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let statusStr = json["status"] as? String else {
                return
            }
            
            // Tolka resultat
            switch statusStr {
            case "match":
                let kartaId = json["karta_id"] as? String ?? ""
                let inliers = (json["inliers"] as? NSNumber)?.intValue ?? 0
                
                söker = false
                matchadKartaId = kartaId
                senasteInliers = inliers
                status = .match
                statusTitel = "Plats hittad!"
                statusBeskrivning = "Du är vid \(kartaId.replacingOccurrences(of: "_", with: " "))"
                
            case "första_skanning":
                söker = false
                matchadKartaId = nil
                status = .förstaSkanning
                statusTitel = "Första skanningen"
                statusBeskrivning = "Inga befintliga kartor finns. Du kommer skapa den första."
                
            case "okänd_plats":
                // Fortsätt försöka i några försök till
                if antalFörsök >= 5 {
                    söker = false
                    status = .okändPlats
                    statusTitel = "Kunde inte känna igen platsen"
                    statusBeskrivning = "Stå där du tidigare skannat och rikta kameran mot hyllorna."
                }
                // Annars: fortsätt söka tyst
                
            default:
                break
            }
            
        } catch {
            // Tyst — kan vara nätverkshicka, fortsätt försöka
            if antalFörsök >= 8 {
                söker = false
                status = .fel
                statusTitel = "Anslutningsfel"
                statusBeskrivning = "Kunde inte nå servern. Kontrollera din anslutning."
            }
        }
    }
}


// ─────────────────────────────────────────────────────────────────
// AR-KAMERAVY
// ─────────────────────────────────────────────────────────────────

struct ARKameraVyPreflight: UIViewRepresentable {
    let manager: PreflightManager
    
    func makeUIView(context: Context) -> ARSCNView {
        let scnView = ARSCNView(frame: .zero)
        scnView.automaticallyUpdatesLighting = false
        scnView.scene = SCNScene()
        
        let config = ARWorldTrackingConfiguration()
        config.planeDetection = [.horizontal, .vertical]
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            config.frameSemantics = [.sceneDepth]
        }
        
        scnView.session.delegate = manager
        scnView.session.run(config, options: [.resetTracking, .removeExistingAnchors])
        
        DispatchQueue.main.async {
            manager.arSession = scnView.session
        }
        
        return scnView
    }
    
    func updateUIView(_ uiView: ARSCNView, context: Context) {}
}
