//
//  ARNavigationView.swift
//  PulsAr
//
//  AR-navigering till produkt med VPS-lokalisering
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

                    // Produktinfo
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(produkt.visningsnamn)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .foregroundColor(.white)
                            .lineLimit(2)
                            .multilineTextAlignment(.trailing)
                        if let gång = produkt.gång {
                            Text("Gång \(gång)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(.ultraThinMaterial)
                    .cornerRadius(12)
                }
                .padding()

                Spacer()

                // "Framme"-banner när nära
                if manager.ärFramme {
                    frammeVy
                } else {
                    // Lokaliseringsstatus
                    lokaliseringsStatus
                    
                    // Navigationsinformation
                    if manager.lokaliseringsStatus == .lokaliserad {
                        navigeringsInfo
                    }
                }
            }
        }
        .navigationBarHidden(true)
        .onAppear {
            manager.starta(målProdukt: produkt)
        }
        .onDisappear {
            manager.stoppa()
        }
    }

    // ─────────────────────────────────────────────
    // FRAMME-VY
    // ─────────────────────────────────────────────
    
    var frammeVy: some View {
        VStack(spacing: 16) {
            // Glödande ikon
            ZStack {
                Circle()
                    .fill(Color.green.opacity(0.3))
                    .frame(width: 100, height: 100)
                Circle()
                    .fill(Color.green.opacity(0.5))
                    .frame(width: 70, height: 70)
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 50))
                    .foregroundColor(.green)
            }
            
            Text("Du är framme!")
                .font(.title)
                .fontWeight(.bold)
                .foregroundColor(.white)
            
            Text("Produkten är markerad i grönt")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            // Produktinfo
            VStack(spacing: 8) {
                Text(produkt.visningsnamn)
                    .font(.headline)
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)
                
                if let gång = produkt.gång {
                    Text("Gång \(gång)")
                        .font(.caption)
                        .foregroundColor(.green)
                }
            }
            .padding()
            .background(.ultraThinMaterial)
            .cornerRadius(16)
            
            Button {
                dismiss()
            } label: {
                Text("Klar")
                    .fontWeight(.semibold)
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.green)
                    .cornerRadius(14)
            }
            .padding(.horizontal, 40)
        }
        .padding()
        .padding(.bottom, 40)
    }

    // ─────────────────────────────────────────────
    // LOKALISERINGSSTATUS
    // ─────────────────────────────────────────────

    var lokaliseringsStatus: some View {
        Group {
            switch manager.lokaliseringsStatus {
            case .söker:
                HStack(spacing: 10) {
                    ProgressView().tint(.white).scaleEffect(0.8)
                    Text("Letar efter din position...")
                        .font(.subheadline)
                        .foregroundColor(.white)
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(.ultraThinMaterial)
                .cornerRadius(30)
                .padding(.bottom, 8)

            case .lokaliserar:
                HStack(spacing: 10) {
                    ProgressView().tint(.yellow).scaleEffect(0.8)
                    Text("Lokaliserar...")
                        .font(.subheadline)
                        .foregroundColor(.yellow)
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(.ultraThinMaterial)
                .cornerRadius(30)
                .padding(.bottom, 8)

            case .lokaliserad:
                HStack(spacing: 8) {
                    Circle()
                        .fill(Color.green)
                        .frame(width: 8, height: 8)
                    Text("Position hittad")
                        .font(.caption)
                        .foregroundColor(.green)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(.ultraThinMaterial)
                .cornerRadius(20)
                .padding(.bottom, 4)

            case .fel:
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.yellow)
                    Text("Rikta kameran mot en hylla")
                        .font(.caption)
                        .foregroundColor(.yellow)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(.ultraThinMaterial)
                .cornerRadius(20)
                .padding(.bottom, 4)
            }
        }
    }

    // ─────────────────────────────────────────────
    // NAVIGERINGSINFO
    // ─────────────────────────────────────────────

    var navigeringsInfo: some View {
        VStack(spacing: 8) {
            // Avstånd
            if manager.avstånd > 0 {
                HStack(spacing: 6) {
                    Image(systemName: "location.fill")
                        .foregroundColor(.blue)
                    Text("\(String(format: "%.0f", manager.avstånd)) meter kvar")
                        .font(.headline)
                        .foregroundColor(.white)
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                .background(.ultraThinMaterial)
                .cornerRadius(20)
            }

            // Gånginformation
            HStack(spacing: 6) {
                Image(systemName: "arrow.right.circle.fill")
                    .foregroundColor(.green)
                if let gång = produkt.gång {
                    Text("Gå till gång \(gång)")
                        .font(.subheadline)
                        .foregroundColor(.white)
                } else {
                    Text("Följ pilen")
                        .font(.subheadline)
                        .foregroundColor(.white)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(.ultraThinMaterial)
            .cornerRadius(20)
        }
        .padding(.bottom, 40)
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
        scnView.autoenablesDefaultLighting   = true
        scnView.scene = SCNScene()
        manager.startaARSession(scnView: scnView)
        return scnView
    }

    func updateUIView(_ uiView: ARSCNView, context: Context) {}
}

// ─────────────────────────────────────────────────────────────────
// LOKALISERINGSSTATUS
// ─────────────────────────────────────────────────────────────────

enum LokaliseringsStatus {
    case söker
    case lokaliserar
    case lokaliserad
    case fel
}

// ─────────────────────────────────────────────────────────────────
// MANAGER
// ─────────────────────────────────────────────────────────────────

class ARNavManager: NSObject, ObservableObject, ARSessionDelegate {
    private var scnView:      ARSCNView?
    private var session:      ARSession?
    private var pilNod:       SCNNode?
    private var produktNod:   SCNNode?  // Highlight-nod
    private var målProdukt:   SökProdukt?
    private var lokaliseringsTimer: Timer?
    private var frameRäknare = 0
    
    // Sparad position från VPS
    private var kundPosition: SIMD2<Float>?

    @Published var lokaliseringsStatus: LokaliseringsStatus = .söker
    @Published var avstånd: Float = 0.0
    @Published var ärFramme: Bool = false

    let serverURL = PulsArConfig.serverURL
    let frammeAvstånd: Float = 2.0  // Meter för att räknas som "framme"

    func starta(målProdukt: SökProdukt) {
        self.målProdukt = målProdukt
    }

    func startaARSession(scnView: ARSCNView) {
        self.scnView  = scnView
        self.session  = scnView.session
        scnView.session.delegate = self

        let config = ARWorldTrackingConfiguration()
        config.planeDetection = [.horizontal]
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            config.frameSemantics = .sceneDepth
        }
        scnView.session.run(config, options: [.resetTracking, .removeExistingAnchors])

        // Börja lokalisera var 2:a sekund
        lokaliseringsTimer = Timer.scheduledTimer(
            withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.lokaliseraMedVPS()
        }
    }

    func stoppa() {
        session?.pause()
        lokaliseringsTimer?.invalidate()
        pilNod?.removeFromParentNode()
        produktNod?.removeFromParentNode()
    }

    // ─────────────────────────────────────────────
    // VPS LOKALISERING
    // ─────────────────────────────────────────────

    func lokaliseraMedVPS() {
        guard let frame = session?.currentFrame else { return }
        guard lokaliseringsStatus != .lokaliserar else { return }

        DispatchQueue.main.async {
            self.lokaliseringsStatus = .lokaliserar
        }

        // Konvertera aktuell frame till JPEG
        let pixelBuffer = frame.capturedImage
        let ciImage     = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context     = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent),
              let bildData = UIImage(cgImage: cgImage).jpegData(compressionQuality: 0.8) else {
            DispatchQueue.main.async { self.lokaliseringsStatus = .fel }
            return
        }

        Task {
            await skickaVPSFörfrågan(bildData: bildData, frame: frame)
        }
    }

    private func skickaVPSFörfrågan(bildData: Data, frame: ARFrame) async {
        do {
            let boundary = UUID().uuidString
            var body     = Data()

            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"bild\"; filename=\"frame.jpg\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
            body.append(bildData)
            body.append("\r\n".data(using: .utf8)!)

            // Skicka med gångnummer om vi vet det
            if let gång = målProdukt?.gång {
                body.append("--\(boundary)\r\n".data(using: .utf8)!)
                body.append("Content-Disposition: form-data; name=\"gång_namn\"\r\n\r\n".data(using: .utf8)!)
                body.append("Gång \(gång)".data(using: .utf8)!)
                body.append("\r\n".data(using: .utf8)!)
            }

            body.append("--\(boundary)--\r\n".data(using: .utf8)!)

            var request        = URLRequest(url: URL(string: "\(serverURL)/lokalisera/")!)
            request.httpMethod = "POST"
            request.httpBody   = body
            request.setValue("multipart/form-data; boundary=\(boundary)",
                             forHTTPHeaderField: "Content-Type")
            request.timeoutInterval = 5

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  http.statusCode == 200 else {
                await MainActor.run { self.lokaliseringsStatus = .fel }
                return
            }

            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let hittad = json?["hittad"] as? Bool ?? false

            if hittad {
                let kundX = (json?["x"] as? NSNumber)?.floatValue ?? 0
                let kundZ = (json?["z"] as? NSNumber)?.floatValue ?? 0

                await MainActor.run {
                    self.lokaliseringsStatus = .lokaliserad
                    self.kundPosition = SIMD2<Float>(kundX, kundZ)
                    self.uppdateraNavigation(frame: frame)
                }
            } else {
                await MainActor.run {
                    self.lokaliseringsStatus = .fel
                }
            }

        } catch {
            await MainActor.run {
                self.lokaliseringsStatus = .fel
            }
        }
    }

    // ─────────────────────────────────────────────
    // NAVIGATION & AR-OBJEKT
    // ─────────────────────────────────────────────

    func uppdateraNavigation(frame: ARFrame) {
        guard let produkt = målProdukt,
              let kundPos = kundPosition,
              let scnView = scnView else { return }

        // Hämta produktkoordinater
        let produktX = Float(produkt.x ?? 0)
        let produktZ = Float(produkt.z ?? 0)

        // Beräkna avstånd
        let dx = produktX - kundPos.x
        let dz = produktZ - kundPos.y
        let dist = sqrt(dx*dx + dz*dz)

        avstånd = dist
        ärFramme = dist < frammeAvstånd

        // Ta bort gamla noder
        pilNod?.removeFromParentNode()
        produktNod?.removeFromParentNode()

        let kameraTransform = frame.camera.transform
        let kameraPos = SIMD3<Float>(
            kameraTransform.columns.3.x,
            kameraTransform.columns.3.y,
            kameraTransform.columns.3.z
        )

        if ärFramme {
            // Visa produkt-highlight
            visaProduktHighlight(
                produktX: produktX,
                produktZ: produktZ,
                kameraPos: kameraPos,
                frame: frame
            )
        } else {
            // Visa navigationspil
            visaNavigationsPil(
                dx: dx, dz: dz,
                avstånd: dist,
                kameraPos: kameraPos,
                frame: frame
            )
        }
    }

    // ─────────────────────────────────────────────
    // PRODUKT-HIGHLIGHT (GRÖNT SKEN)
    // ─────────────────────────────────────────────

    private func visaProduktHighlight(produktX: Float, produktZ: Float, kameraPos: SIMD3<Float>, frame: ARFrame) {
        guard let scnView = scnView else { return }

        let highlightNod = SCNNode()

        // Glödande sfär
        let sfär = SCNSphere(radius: 0.15)
        sfär.firstMaterial?.diffuse.contents = UIColor.green.withAlphaComponent(0.6)
        sfär.firstMaterial?.emission.contents = UIColor.green
        sfär.firstMaterial?.transparency = 0.7
        let sfärNod = SCNNode(geometry: sfär)
        highlightNod.addChildNode(sfärNod)

        // Yttre ring (pulserande)
        let ring = SCNTorus(ringRadius: 0.25, pipeRadius: 0.02)
        ring.firstMaterial?.diffuse.contents = UIColor.green
        ring.firstMaterial?.emission.contents = UIColor.green
        let ringNod = SCNNode(geometry: ring)
        ringNod.eulerAngles.x = .pi / 2  // Lägg ringen horisontellt
        highlightNod.addChildNode(ringNod)

        // Pulsanimation
        let pulsera = CABasicAnimation(keyPath: "scale")
        pulsera.fromValue = SCNVector3(1, 1, 1)
        pulsera.toValue = SCNVector3(1.3, 1.3, 1.3)
        pulsera.duration = 0.8
        pulsera.autoreverses = true
        pulsera.repeatCount = .infinity
        highlightNod.addAnimation(pulsera, forKey: "pulsera")

        // Placera highlight framför kameran i riktning mot produkten
        let riktningX = produktX - kameraPos.x
        let riktningZ = produktZ - kameraPos.z
        let vinkel = atan2(riktningX, riktningZ)
        
        // Placera 1.5m framför i rätt riktning
        let avståndFramför: Float = 1.5
        highlightNod.simdPosition = SIMD3<Float>(
            kameraPos.x + sin(vinkel) * avståndFramför,
            kameraPos.y,
            kameraPos.z + cos(vinkel) * avståndFramför
        )

        scnView.scene.rootNode.addChildNode(highlightNod)
        produktNod = highlightNod
    }

    // ─────────────────────────────────────────────
    // NAVIGATIONS-PIL
    // ─────────────────────────────────────────────

    private func visaNavigationsPil(dx: Float, dz: Float, avstånd: Float, kameraPos: SIMD3<Float>, frame: ARFrame) {
        guard let scnView = scnView else { return }

        let pil = skapaPilNod(avstånd: avstånd)

        // Riktning mot produkten
        let vinkel = atan2(dx, dz)

        // Placera pilen 1.5 meter framför kameran
        pil.simdPosition = SIMD3<Float>(
            kameraPos.x + sin(vinkel) * 1.5,
            kameraPos.y - 0.3,
            kameraPos.z + cos(vinkel) * 1.5
        )
        pil.simdEulerAngles.y = -vinkel

        scnView.scene.rootNode.addChildNode(pil)
        pilNod = pil
    }

    private func skapaPilNod(avstånd: Float) -> SCNNode {
        let pilNod = SCNNode()

        // Färg baserat på avstånd
        let färg: UIColor = avstånd < 3 ? .green :
                            avstånd < 8 ? .yellow : .red

        // Pilstjälk (liggande cylinder)
        let stjälk = SCNCylinder(radius: 0.025, height: 0.35)
        stjälk.firstMaterial?.diffuse.contents = färg
        stjälk.firstMaterial?.emission.contents = färg.withAlphaComponent(0.5)
        let stjälkNod = SCNNode(geometry: stjälk)
        stjälkNod.eulerAngles.x = .pi / 2  // Lägg liggande
        stjälkNod.position = SCNVector3(0, 0, -0.1)
        pilNod.addChildNode(stjälkNod)

        // Pilhuvud (kon)
        let huvud = SCNCone(topRadius: 0, bottomRadius: 0.07, height: 0.15)
        huvud.firstMaterial?.diffuse.contents = färg
        huvud.firstMaterial?.emission.contents = färg.withAlphaComponent(0.5)
        let huvudNod = SCNNode(geometry: huvud)
        huvudNod.eulerAngles.x = -.pi / 2  // Peka framåt
        huvudNod.position = SCNVector3(0, 0, -0.35)
        pilNod.addChildNode(huvudNod)

        // Avståndslabel
        let textGeometri = SCNText(string: "\(Int(avstånd))m", extrusionDepth: 0.01)
        textGeometri.font = UIFont.systemFont(ofSize: 0.08, weight: .bold)
        textGeometri.firstMaterial?.diffuse.contents = UIColor.white
        let textNod = SCNNode(geometry: textGeometri)
        textNod.position = SCNVector3(-0.05, 0.1, 0)
        textNod.scale = SCNVector3(0.5, 0.5, 0.5)
        pilNod.addChildNode(textNod)

        // Pulsanimation
        let pulsa = CABasicAnimation(keyPath: "position.z")
        pulsa.fromValue = pilNod.position.z
        pulsa.toValue = pilNod.position.z - 0.05
        pulsa.duration = 0.5
        pulsa.autoreverses = true
        pulsa.repeatCount = .infinity
        pilNod.addAnimation(pulsa, forKey: "pulsa")

        return pilNod
    }

    // ─────────────────────────────────────────────
    // ARKIT DELEGATE
    // ─────────────────────────────────────────────

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        frameRäknare += 1
        guard frameRäknare % 10 == 0 else { return }
        guard lokaliseringsStatus == .lokaliserad else { return }
        
        // Uppdatera navigation med ny frame
        uppdateraNavigation(frame: frame)
    }
}
