//
//  GångSkanningView.swift
//  PulsAr
//
//  Skannar gångar och samlar 3D-punktmoln med LiDAR
//

import SwiftUI
import ARKit
import Combine
import Accelerate

// ─────────────────────────────────────────────────────────────────
// HUVUDVY
// ─────────────────────────────────────────────────────────────────

struct GångSkanningView: View {
    @StateObject private var manager  = GångSkanningManager()
    @StateObject private var uploader = ServerUploader()
    @State private var visaUppladdning = false
    @State private var sekunder        = 0
    @State private var timer: Timer?   = nil
    @State private var valtGångnummer  = ""
    @State private var visaGångval     = true
    @State private var ankarpunkter: [[String: Any]] = []
    @State private var laddning        = true
    @Environment(\.dismiss) var dismiss

    var body: some View {
        ZStack {
            if !visaGångval {
                ARKameraVyGång(manager: manager)
                    .ignoresSafeArea()
            } else {
                Color.black.ignoresSafeArea()
            }

            if visaGångval {
                gångvalVy
            } else {
                skanningOverlay
            }

            if visaUppladdning {
                UppladddningsView(
                    uploader:      uploader,
                    skanningsmapp: manager.skanningsmapp,
                    arFrames:      manager.sparadePositioner,
                    punkter3D:     manager.punkter3D,
                    onDismiss:     { dismiss() }
                )
            }
        }
        .navigationBarHidden(true)
        .onDisappear { manager.stoppa() }
        .onAppear {
            Task {
                guard let url = URL(string: "\(PulsArConfig.serverURL)/ankarpunkter/") else { return }
                do {
                    let (data, _) = try await URLSession.shared.data(from: url)
                    let json      = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                    let punkter   = json?["ankarpunkter"] as? [[String: Any]] ?? []
                    await MainActor.run {
                        ankarpunkter = punkter
                        laddning     = false
                    }
                } catch {
                    await MainActor.run { laddning = false }
                }
            }
        }
    }

    // ─────────────────────────────────────────────
    // GÅNGVAL
    // ─────────────────────────────────────────────

    var gångvalVy: some View {
        VStack(spacing: 24) {
            Text("Välj gång att skanna")
                .font(.largeTitle).fontWeight(.bold)
                .foregroundColor(.white)

            Text("Starta vid gångingången. Gå långsamt (~0.5 m/s).\nRikta kameran rakt mot hyllorna.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
            
            // LiDAR-varning
            if !ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
                HStack {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.yellow)
                    Text("Denna enhet saknar LiDAR. 3D-precision blir sämre.")
                        .font(.caption)
                        .foregroundColor(.yellow)
                }
                .padding()
                .background(Color.yellow.opacity(0.15))
                .cornerRadius(12)
                .padding(.horizontal)
            }

            if laddning {
                ProgressView().tint(.white).padding()
            } else if ankarpunkter.isEmpty {
                Text("Inga ankarpunkter hittade.\nKartlägg butiken först.")
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                    .padding()
            } else {
                ScrollView {
                    LazyVGrid(columns: [
                        GridItem(.flexible()),
                        GridItem(.flexible()),
                    ], spacing: 12) {
                        ForEach(ankarpunkter, id: \.description) { punkt in
                            Button {
                                let namn = punkt["namn"] as? String ?? "okänd"
                                let x    = (punkt["x"] as? NSNumber)?.floatValue ?? 0
                                let z    = (punkt["z"] as? NSNumber)?.floatValue ?? 0
                                valtGångnummer       = namn
                                manager.startaOffset = (x, z)
                                visaGångval          = false
                                manager.starta(gång: namn)
                            } label: {
                                VStack(spacing: 6) {
                                    Image(systemName: punkt["ikon"] as? String ?? "mappin")
                                        .font(.title2)
                                        .foregroundColor(.blue)
                                    Text(punkt["namn"] as? String ?? "")
                                        .font(.subheadline)
                                        .foregroundColor(.white)
                                        .multilineTextAlignment(.center)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 16)
                                .background(Color.blue.opacity(0.2))
                                .cornerRadius(12)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.blue.opacity(0.5), lineWidth: 1)
                                )
                            }
                        }
                    }
                    .padding(.horizontal)
                }
            }

            Button { dismiss() } label: {
                Text("Avbryt").foregroundColor(.secondary)
            }
        }
        .padding()
    }

    // ─────────────────────────────────────────────
    // SCANNING OVERLAY
    // ─────────────────────────────────────────────

    var skanningOverlay: some View {
        VStack {
            // Statusrad
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(valtGångnummer)
                        .font(.headline).foregroundColor(.white)
                    HStack {
                        Circle()
                            .fill(manager.spelarIn ? Color.red : Color.gray)
                            .frame(width: 8, height: 8)
                        Text(manager.spelarIn
                             ? "Spelar in \(formateraTid(sekunder))"
                             : "Redo")
                            .font(.caption).foregroundColor(.white)
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(manager.antalFrames) frames")
                        .font(.caption).foregroundColor(.white)
                    Text("\(manager.antal3DPunkter) 3D-punkter")
                        .font(.caption).foregroundColor(.cyan)
                }
            }
            .padding()
            .background(.ultraThinMaterial)

            Spacer()

            // 3D-status
            if manager.spelarIn {
                HStack(spacing: 20) {
                    VStack {
                        Text("\(manager.antal3DPunkter)")
                            .font(.title2).bold()
                            .foregroundColor(.cyan)
                        Text("3D punkter")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    
                    VStack {
                        Text(String(format: "%.1f", manager.medelDjup))
                            .font(.title2).bold()
                            .foregroundColor(.green)
                        Text("m djup")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    
                    VStack {
                        Text(String(format: "%.2f", manager.nuvarandeDrift))
                            .font(.title2).bold()
                            .foregroundColor(manager.nuvarandeDrift > 0.5 ? .yellow : .green)
                        Text("m drift")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                .padding()
                .background(.ultraThinMaterial)
                .cornerRadius(12)
                
                // Varning om max punkter nådd
                if manager.maxPunkterNådd {
                    HStack {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.green)
                        Text("Tillräckligt med data — du kan stoppa skanningen")
                            .font(.caption)
                            .foregroundColor(.green)
                    }
                    .padding(8)
                    .background(Color.green.opacity(0.2))
                    .cornerRadius(8)
                }
            }

            // Instruktion
            if !manager.spelarIn {
                VStack(spacing: 6) {
                    Text("📱 Håll telefonen stilla")
                        .font(.headline).foregroundColor(.yellow)
                    Text("Rikta kameran rakt mot hyllan.\nGå långsamt och stadigt.")
                        .font(.caption).foregroundColor(.white)
                        .multilineTextAlignment(.center)
                }
                .padding()
                .background(.ultraThinMaterial)
                .cornerRadius(12)
                .padding(.bottom, 8)
            }

            // Knappar
            HStack(spacing: 20) {
                // Avbryt
                Button { dismiss() } label: {
                    Image(systemName: "xmark")
                        .font(.title2)
                        .foregroundColor(.white)
                        .frame(width: 60, height: 60)
                        .background(Color.red.opacity(0.8))
                        .clipShape(Circle())
                }

                // Inspelningsknapp
                Button {
                    if manager.spelarIn {
                        manager.stoppaSpelaIn()
                        timer?.invalidate()
                        visaUppladdning = true
                    } else {
                        manager.börjaSpelaIn()
                        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
                            sekunder += 1
                        }
                    }
                } label: {
                    ZStack {
                        Circle()
                            .stroke(Color.white, lineWidth: 4)
                            .frame(width: 80, height: 80)
                        Circle()
                            .fill(manager.spelarIn ? Color.red : Color.white)
                            .frame(width: manager.spelarIn ? 36 : 64, height: manager.spelarIn ? 36 : 64)
                            .cornerRadius(manager.spelarIn ? 8 : 32)
                    }
                }
            }
            .padding(.bottom, 40)
        }
    }

    func formateraTid(_ sekunder: Int) -> String {
        let m = sekunder / 60
        let s = sekunder % 60
        return String(format: "%d:%02d", m, s)
    }
}

// ─────────────────────────────────────────────────────────────────
// 3D PUNKT STRUKTUR
// ─────────────────────────────────────────────────────────────────

struct Punkt3D: Codable {
    let x: Float          // Världskoordinat X
    let y: Float          // Världskoordinat Y (höjd)
    let z: Float          // Världskoordinat Z
    let u: Float          // Pixel-koordinat i bilden
    let v: Float          // Pixel-koordinat i bilden
    let frame: Int        // Vilken frame punkten kommer från
    let confidence: Float // LiDAR-konfidens
    // OBS: descriptor beräknas server-side med SuperPoint, skickas ej från iOS
}

// ─────────────────────────────────────────────────────────────────
// MANAGER MED 3D-PUNKTINSAMLING
// ─────────────────────────────────────────────────────────────────

class GångSkanningManager: NSObject, ObservableObject, ARSessionDelegate {
    private var session: ARSession?
    
    @Published var spelarIn           = false
    @Published var antalFrames        = 0
    @Published var antal3DPunkter     = 0
    @Published var nuvarandeDrift:    Float = 0
    @Published var medelDjup:         Float = 0
    @Published var harLuckor          = false
    @Published var maxPunkterNådd     = false
    
    var skanningsmapp:    URL?
    var sparadePositioner: [[String: Any]] = []
    var punkter3D:         [Punkt3D] = []
    var startPosition:     (Float, Float)?
    var startaOffset:      (Float, Float) = (0, 0)
    var gångNamn           = ""
    
    private var frameRäknare = 0
    private let sparaKö      = DispatchQueue(label: "spara", qos: .userInitiated)
    
    // Kamera-intrinsics för PnP
    private var fx: Float = 0
    private var fy: Float = 0
    private var cx: Float = 0
    private var cy: Float = 0
    
    // ─────────────────────────────────────────────
    // PUNKTBEGRÄNSNINGAR
    // ─────────────────────────────────────────────
    private let maxPunkterPerFrame = 300      // 300 räcker gott för lokalisering
    private let maxTotalaPunkter = 500000     // 500k ger ~5+ minuter
    private let samplingStep = 12             // Glesare sampling, snabbare     

    func starta(gång: String) {
        gångNamn = gång
    }

    func startaARSession(session: ARSession) {
        self.session = session
        session.delegate = self

        let config = ARWorldTrackingConfiguration()
        config.planeDetection = [.horizontal, .vertical]
        
        // Aktivera LiDAR om tillgängligt
        if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
            config.frameSemantics = [.sceneDepth, .smoothedSceneDepth]
            print("✅ LiDAR aktiverad")
        } else {
            print("⚠️  Ingen LiDAR — använder ARKit depth estimation")
        }
        
        session.run(config, options: [.resetTracking, .removeExistingAnchors])
    }

    func stoppa() {
        session?.pause()
    }

    func börjaSpelaIn() {
        let timestamp = Int(Date().timeIntervalSince1970)
        let säkertNamn = gångNamn.replacingOccurrences(of: " ", with: "_")
        skanningsmapp = FileManager.default.temporaryDirectory
            .appendingPathComponent("skanning_\(säkertNamn)_\(timestamp)")
        
        try? FileManager.default.createDirectory(
            at: skanningsmapp!, withIntermediateDirectories: true)
        
        sparadePositioner = []
        punkter3D = []
        frameRäknare = 0
        antalFrames = 0
        antal3DPunkter = 0
        maxPunkterNådd = false
        spelarIn = true
        
        print("🎬 Börjar 3D-skanning av \(gångNamn)")
    }

    func stoppaSpelaIn() {
        spelarIn = false
        print("⏹️  Stoppar \(gångNamn)")
        print("   Frames: \(antalFrames)")
        print("   3D-punkter: \(punkter3D.count)")
        print("   Drift: \(nuvarandeDrift)m")
    }

    // ─────────────────────────────────────────────
    // FRAME PROCESSING
    // ─────────────────────────────────────────────

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        guard spelarIn else { return }
        frameRäknare += 1
        
        // Ta frame var 5:e uppdatering (~6 fps)
        guard frameRäknare % 5 == 0 else { return }
        
        guard let mapp = skanningsmapp else { return }
        let bildIndex = frameRäknare / 5
        
        // Kameraposition
        let t = frame.camera.transform
        let camX = t.columns.3.x + startaOffset.0
        let camY = t.columns.3.y
        let camZ = t.columns.3.z + startaOffset.1
        
        // Spara intrinsics
        let intrinsics = frame.camera.intrinsics
        fx = intrinsics[0][0]
        fy = intrinsics[1][1]
        cx = intrinsics[2][0]
        cy = intrinsics[2][1]
        
        // Drift-beräkning
        if startPosition == nil { startPosition = (camX, camZ) }
        if let (sx, sz) = startPosition {
            let drift = sqrt(pow(camX - sx, 2) + pow(camZ - sz, 2))
            DispatchQueue.main.async { self.nuvarandeDrift = drift }
        }
        
        // Extrahera 3D-punkter från LiDAR (om vi inte nått max)
        var nya3DPunkter: [Punkt3D] = []
        if punkter3D.count < maxTotalaPunkter {
            nya3DPunkter = extrahera3DPunkter(
                frame: frame,
                frameIndex: bildIndex,
                cameraTransform: t
            )
            
            if !nya3DPunkter.isEmpty {
                punkter3D.append(contentsOf: nya3DPunkter)
                DispatchQueue.main.async {
                    self.antal3DPunkter = self.punkter3D.count
                    if self.punkter3D.count >= self.maxTotalaPunkter {
                        self.maxPunkterNådd = true
                    }
                }
            }
        }
        
        // Spara frame
        let pixelBuffer = frame.capturedImage
        sparaKö.async { [weak self] in
            self?.sparaFrame(pixelBuffer, index: bildIndex, till: mapp)
        }
        
        // Spara metadata
        let position: [String: Any] = [
            "frame": bildIndex,
            "x": camX,
            "y": camY,
            "z": camZ,
            "rot_y": frame.camera.eulerAngles.y,
            "fx": fx,
            "fy": fy,
            "cx": cx,
            "cy": cy,
            "gång": gångNamn,
            "har_lidar": frame.sceneDepth != nil,
            "antal_3d_punkter": nya3DPunkter.count
        ]
        
        DispatchQueue.main.async {
            self.sparadePositioner.append(position)
            self.antalFrames = bildIndex
        }
    }

    // ─────────────────────────────────────────────
    // 3D PUNKT EXTRAKTION FRÅN LIDAR
    // ─────────────────────────────────────────────

    private func extrahera3DPunkter(
        frame: ARFrame,
        frameIndex: Int,
        cameraTransform: simd_float4x4
    ) -> [Punkt3D] {
        
        guard let depthMap = frame.sceneDepth?.depthMap ?? frame.smoothedSceneDepth?.depthMap else {
            return []
        }
        
        guard let confidenceMap = frame.sceneDepth?.confidenceMap ?? frame.smoothedSceneDepth?.confidenceMap else {
            return []
        }
        
        var punkter: [Punkt3D] = []
        
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
        
        // Bildstorlek (för pixel-koordinater) - LANDSCAPE
        let imageWidth = CVPixelBufferGetWidth(frame.capturedImage)
        let imageHeight = CVPixelBufferGetHeight(frame.capturedImage)
        
        var totalDjup: Float = 0
        var djupCount = 0
        
        // Sampla punkter glesare för att hålla nere storleken
        outerLoop: for row in stride(from: 0, to: depthHeight, by: samplingStep) {
            for col in stride(from: 0, to: depthWidth, by: samplingStep) {
                // Stoppa om vi nått max för denna frame
                if punkter.count >= maxPunkterPerFrame {
                    break outerLoop
                }
                
                let idx = row * depthWidth + col
                let depth = depthData[idx]
                let confidence = confData[idx]
                
                // Filtrera: giltig djup och hög konfidens
                guard depth > 0.1 && depth < 5.0 && confidence >= 1 else { continue }
                
                totalDjup += depth
                djupCount += 1
                
                // Landscape koordinater (för 3D-beräkning med intrinsics)
                let u_landscape = Float(col) / Float(depthWidth) * Float(imageWidth)
                let v_landscape = Float(row) / Float(depthHeight) * Float(imageHeight)
                
                // Konvertera till 3D med LANDSCAPE koordinater och intrinsics
                let x_cam = (u_landscape - cx) * depth / fx
                let y_cam = (v_landscape - cy) * depth / fy
                let z_cam = depth
                
                // Transformera till världskoordinater
                let camPoint = SIMD4<Float>(x_cam, y_cam, z_cam, 1.0)
                let worldPoint = cameraTransform * camPoint
                
                // Portrait koordinater (för 2D-matchning med SuperPoint)
                // Bilden sparas roterad .right: new_x = imageHeight - v, new_y = u
                let u_portrait = Float(imageHeight) - v_landscape
                let v_portrait = u_landscape
                
                // Skapa punkt
                let punkt = Punkt3D(
                    x: worldPoint.x + startaOffset.0,
                    y: worldPoint.y,
                    z: worldPoint.z + startaOffset.1,
                    u: u_portrait,   // Portrait för SuperPoint-matchning
                    v: v_portrait,
                    frame: frameIndex,
                    confidence: Float(confidence) / 2.0
                )
                punkter.append(punkt)
            }
        }
        
        if djupCount > 0 {
            DispatchQueue.main.async {
                self.medelDjup = totalDjup / Float(djupCount)
            }
        }
        
        return punkter
    }

    // ─────────────────────────────────────────────
    // SPARA FRAME
    // ─────────────────────────────────────────────

    private func sparaFrame(_ pixelBuffer: CVPixelBuffer, index: Int, till mapp: URL) {
        let ciImage = CIImage(cvPixelBuffer: pixelBuffer).oriented(.right)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else { return }
        let uiImage = UIImage(cgImage: cgImage)
        let frameURL = mapp.appendingPathComponent("frame_\(index).jpg")
        if let data = uiImage.jpegData(compressionQuality: 0.92) {
            try? data.write(to: frameURL)
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// AR-KAMERAVY
// ─────────────────────────────────────────────────────────────────

struct ARKameraVyGång: UIViewRepresentable {
    let manager: GångSkanningManager

    func makeUIView(context: Context) -> ARSCNView {
        let scnView = ARSCNView(frame: .zero)
        scnView.automaticallyUpdatesLighting = false
        scnView.scene = SCNScene()
        DispatchQueue.main.async {
            manager.startaARSession(session: scnView.session)
        }
        return scnView
    }

    func updateUIView(_ uiView: ARSCNView, context: Context) {}
}

// ─────────────────────────────────────────────────────────────────
// UPPLADDNINGSVY (uppdaterad för 3D-data)
// ─────────────────────────────────────────────────────────────────

struct UppladddningsView: View {
    @ObservedObject var uploader: ServerUploader
    let skanningsmapp: URL?
    let arFrames:      [[String: Any]]
    let punkter3D:     [Punkt3D]
    let onDismiss:     () -> Void
    
    var body: some View {
        ZStack {
            Color.black.opacity(0.8).ignoresSafeArea()
            VStack(spacing: 20) {
                if uploader.klart {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 60)).foregroundColor(.green)
                    Text("Uppladdning klar!")
                        .font(.title2).fontWeight(.bold).foregroundColor(.white)
                    Text("Servern bygger 3D-kartan.\nDet tar 2-5 minuter.")
                        .foregroundColor(.secondary).multilineTextAlignment(.center)
                    Button("Klar", action: onDismiss)
                        .padding().background(Color.green)
                        .foregroundColor(.white).cornerRadius(12)

                } else if !uploader.felmeddelande.isEmpty {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 60)).foregroundColor(.red)
                    Text("Något gick fel")
                        .font(.title2).foregroundColor(.white)
                    Text(uploader.felmeddelande)
                        .foregroundColor(.secondary).multilineTextAlignment(.center)
                    Button("Försök igen") { Task { await laddaUpp() } }
                        .padding().background(Color.blue)
                        .foregroundColor(.white).cornerRadius(12)

                } else {
                    ProgressView().scaleEffect(2).tint(.white)
                    Text("Laddar upp \(arFrames.count) frames + \(punkter3D.count) 3D-punkter...")
                        .foregroundColor(.white).padding(.top)
                    ProgressView(value: uploader.progress)
                        .tint(.cyan).padding(.horizontal, 40)
                }
            }
            .padding(30)
        }
        .task {
            await laddaUpp()
        }
    }

    func laddaUpp() async {
        guard !uploader.laddarUpp && !uploader.klart else { return }
        
        await uploader.laddaUppSkanning3D(
            videoURL: skanningsmapp,
            arFrames: arFrames,
            punkter3D: punkter3D
        )
    }
}
