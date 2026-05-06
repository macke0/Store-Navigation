//
//  ButikSkanningView.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-04-12.
//


//
//  ButikSkanningView.swift
//  PulsAr
//
//  Fri skanning av butiken — starta, pausa, fortsätt
//  Ersätter GångSkanningView med enklare flöde
//

import SwiftUI
import ARKit
import Combine
import Accelerate

// ICA-färger
private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)

// ─────────────────────────────────────────────────────────────────
// HUVUDVY
// ─────────────────────────────────────────────────────────────────

struct ButikSkanningView: View {
    let kartaId: String?  // NY: vilken karta ska skanningen kopplas till?
    
    @StateObject private var manager  = ButikSkanningManager()
    @StateObject private var uploader = ServerUploader()
    
    init(kartaId: String? = nil) {
        self.kartaId = kartaId
    }
    @State private var visaUppladdning = false
    @State private var sekunder        = 0
    @State private var timer: Timer?   = nil
    @State private var pausadeSessioner: [[String: Any]] = []
    @State private var laddning        = true
    @State private var visaSkanningVy  = false
    @Environment(\.dismiss) var dismiss

    var body: some View {
        ZStack {
            if visaSkanningVy {
                ARKameraVyButik(manager: manager)
                    .ignoresSafeArea()
                skanningOverlay
            } else {
                Color.black.ignoresSafeArea()
                startVy
            }

            if visaUppladdning {
                ButikUppladdningsVy(
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
                await manager.laddaTäckning(serverURL: PulsArConfig.serverURL)
                
                let sessioner = await uploader.hämtaSessioner()
                await MainActor.run {
                    pausadeSessioner = sessioner.filter { ($0["status"] as? String) == "pausad" }
                    laddning = false
                    uploader.kartaId = kartaId   // NY rad
                }
            }
        }
    }

    // ─────────────────────────────────────────────
    // STARTVY — Ny/Fortsätt skanning
    // ─────────────────────────────────────────────

    var startVy: some View {
        VStack(spacing: 24) {
            Spacer()

            // Ikon
            ZStack {
                Circle()
                    .fill(icaRöd.opacity(0.15))
                    .frame(width: 100, height: 100)
                Image(systemName: "camera.viewfinder")
                    .font(.system(size: 44))
                    .foregroundColor(icaRöd)
            }

            Text("Skanna butiken")
                .font(.system(size: 28, weight: .bold, design: .rounded))
                .foregroundColor(.white)

            Text("Gå genom butiken och filma hyllorna.\nDu kan pausa och fortsätta när som helst.")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.5))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)

            // LiDAR-status
            if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                    Text("LiDAR tillgänglig")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.green)
                }
            } else {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.yellow)
                    Text("Ingen LiDAR — precision blir lägre")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.yellow)
                }
            }

            Spacer()

            // Knappar
            VStack(spacing: 12) {
                // Ny skanning
                Button {
                    manager.starta()
                    visaSkanningVy = true
                } label: {
                    HStack {
                        Image(systemName: "plus.circle.fill")
                            .font(.system(size: 18))
                        Text("Ny skanning")
                            .font(.system(size: 16, weight: .bold, design: .rounded))
                    }
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(icaRöd)
                    .cornerRadius(14)
                }

                // Fortsätt pausade sessioner
                if !pausadeSessioner.isEmpty {
                    ForEach(pausadeSessioner, id: \.description) { session in
                        Button {
                            let sid = session["session_id"] as? String ?? ""
                            uploader.sessionId = sid
                            manager.starta()
                            visaSkanningVy = true
                            Task {
                                await uploader.fortsättSession(sid)
                            }
                        } label: {
                            HStack {
                                Image(systemName: "play.circle.fill")
                                    .font(.system(size: 18))
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Fortsätt skanning")
                                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                                    let frames = session["antal_frames"] as? Int ?? 0
                                    Text("\(frames) frames sparade")
                                        .font(.system(size: 12))
                                        .foregroundColor(.white.opacity(0.5))
                                }
                                Spacer()
                            }
                            .foregroundColor(.white)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 14)
                            .background(.ultraThinMaterial)
                            .cornerRadius(14)
                            .overlay(
                                RoundedRectangle(cornerRadius: 14)
                                    .stroke(.white.opacity(0.1), lineWidth: 1)
                            )
                        }
                    }
                }
            }
            .padding(.horizontal, 36)

            // Tips
            VStack(alignment: .leading, spacing: 8) {
                tipsRad(ikon: "figure.walk", text: "Gå långsamt och stadigt (~0.5 m/s)")
                tipsRad(ikon: "camera.fill", text: "Rikta kameran mot hyllorna")
                tipsRad(ikon: "arrow.uturn.backward", text: "Du kan gå fram och tillbaka")
                tipsRad(ikon: "pause.circle", text: "Pausa när som helst och fortsätt sen")
            }
            .padding(16)
            .background(Color.white.opacity(0.04))
            .cornerRadius(14)
            .padding(.horizontal, 36)

            Spacer()

            Button { dismiss() } label: {
                Text("Stäng")
                    .foregroundColor(.white.opacity(0.3))
            }
            .padding(.bottom, 20)
        }
    }

    private func tipsRad(ikon: String, text: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: ikon)
                .font(.system(size: 14))
                .foregroundColor(icaRöd.opacity(0.8))
                .frame(width: 20)
            Text(text)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.5))
        }
    }

    // ─────────────────────────────────────────────
    // SKANNING OVERLAY
    // ─────────────────────────────────────────────

    var skanningOverlay: some View {
        VStack {
            // Statusrad
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Skannar butiken")
                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                        .foregroundColor(.white)
                    HStack(spacing: 6) {
                        Circle()
                            .fill(manager.spelarIn ? Color.red : Color.gray)
                            .frame(width: 8, height: 8)
                        Text(manager.spelarIn
                             ? formateraTid(sekunder)
                             : "Redo")
                            .font(.system(size: 13, design: .monospaced))
                            .foregroundColor(.white.opacity(0.7))
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    Text("\(manager.antalFrames) frames")
                        .font(.system(size: 13, design: .monospaced))
                        .foregroundColor(.white.opacity(0.7))
                    Text("\(manager.antal3DPunkter) 3D")
                        .font(.system(size: 13, design: .monospaced))
                        .foregroundColor(.cyan.opacity(0.8))
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(.ultraThinMaterial)

            Spacer()

            // Stats
            if manager.spelarIn {
                VStack(spacing: 8) {
                    HStack(spacing: 20) {
                        statPill(värde: "\(manager.antal3DPunkter)", label: "3D", färg: .cyan)
                        statPill(värde: String(format: "%.1f", manager.medelDjup), label: "m djup", färg: .green)
                        statPill(värde: String(format: "%.2f", manager.nuvarandeDrift), label: "m drift",
                                 färg: manager.nuvarandeDrift > 0.5 ? .yellow : .green)
                    }
                    HStack(spacing: 20) {
                        statPill(värde: "\(manager.antalMeshAnchors)", label: "mesh", färg: .purple)
                        statPill(värde: "\(manager.antalMeshTrianglar / 1000)k", label: "△ tri", färg: .pink)
                        statPill(värde: String(format: "%.1f", manager.meshLagrad), label: "MB", färg: .orange)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(.ultraThinMaterial)
                .cornerRadius(12)
            }
            
            if !manager.harÖverlapp && manager.spelarIn {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.yellow)
                    Text("Inget överlapp med tidigare skanning — gå mot skannat område")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.yellow)
                }
                .padding(10)
                .background(Color.yellow.opacity(0.15))
                .cornerRadius(10)
                .padding(.horizontal, 16)
            }
            
            if manager.visaLoopPåminnelse && manager.spelarIn {
                HStack(spacing: 8) {
                    Image(systemName: "arrow.uturn.backward.circle.fill")
                        .foregroundColor(.cyan)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Gå tillbaka mot startpunkten")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.cyan)
                        Text("\(String(format: "%.0f", manager.avståndFrånStart))m bort — loop closure förbättrar precision")
                            .font(.system(size: 11))
                            .foregroundColor(.cyan.opacity(0.7))
                    }
                }
                .padding(10)
                .background(Color.cyan.opacity(0.1))
                .cornerRadius(10)
                .padding(.horizontal, 16)
            }

            // Knappar
            HStack(spacing: 20) {
                // Avbryt
                Button { dismiss() } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundColor(.white)
                        .frame(width: 56, height: 56)
                        .background(Color.white.opacity(0.15))
                        .clipShape(Circle())
                }

                // Inspelning
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
                            .frame(width: 76, height: 76)
                        Circle()
                            .fill(manager.spelarIn ? icaRöd : Color.white)
                            .frame(width: manager.spelarIn ? 32 : 60,
                                   height: manager.spelarIn ? 32 : 60)
                            .cornerRadius(manager.spelarIn ? 6 : 30)
                    }
                }

                // Pausa & ladda upp det som finns
                Button {
                    manager.stoppaSpelaIn()
                    timer?.invalidate()
                    Task {
                        await uploader.pausaSession()
                    }
                    dismiss()
                } label: {
                    Image(systemName: "pause.fill")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundColor(.white)
                        .frame(width: 56, height: 56)
                        .background(Color.orange.opacity(0.7))
                        .clipShape(Circle())
                }
            }
            .padding(.bottom, 40)
        }
    }

    private func statPill(värde: String, label: String, färg: Color) -> some View {
        VStack(spacing: 2) {
            Text(värde)
                .font(.system(size: 18, weight: .bold, design: .monospaced))
                .foregroundColor(färg)
            Text(label)
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.4))
        }
    }

    func formateraTid(_ sekunder: Int) -> String {
        let m = sekunder / 60
        let s = sekunder % 60
        return String(format: "%d:%02d", m, s)
    }
}

// ─────────────────────────────────────────────────────────────────
// SKANNING MANAGER
// ─────────────────────────────────────────────────────────────────

class ButikSkanningManager: NSObject, ObservableObject, ARSessionDelegate {
    private var session: ARSession?
    
    @Published var spelarIn           = false
    @Published var antalFrames        = 0
    @Published var antal3DPunkter     = 0
    @Published var nuvarandeDrift:    Float = 0
    @Published var medelDjup:         Float = 0
    @Published var maxPunkterNådd     = false
    @Published var tidligarePositioner: [(x: Float, z: Float)] = []
    @Published var harÖverlapp: Bool = true
    @Published var avståndFrånStart: Float = 0
    @Published var visaLoopPåminnelse: Bool = false
    // Mesh-tracking (Scene Reconstruction)
    @Published var antalMeshAnchors: Int = 0
    @Published var antalMeshTrianglar: Int = 0
    @Published var meshLagrad: Float = 0  // MB sparad mesh-data
    
    var skanningsmapp:    URL?
    var sparadePositioner: [[String: Any]] = []
    var punkter3D:         [Punkt3D] = []
    var startPosition:     (Float, Float)?
    
    private var skanningsTid: Date?
    private var frameRäknare = 0
    private let sparaKö      = DispatchQueue(label: "spara", qos: .userInitiated)
    
    private var fx: Float = 0
    private var fy: Float = 0
    private var cx: Float = 0
    private var cy: Float = 0
    
    private let maxPunkterPerFrame = 300
    private let maxTotalaPunkter = 500000
    private let samplingStep = 12

    func starta() {
        // Ingen gång-namn behövs längre
    }

    func startaARSession(session: ARSession) {
            self.session = session
            session.delegate = self

            let config = ARWorldTrackingConfiguration()
            config.planeDetection = [.horizontal, .vertical]
            
            if ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) {
                config.frameSemantics = [.sceneDepth, .smoothedSceneDepth]
            }
            
            // NYTT: Aktivera Scene Reconstruction (kräver LiDAR)
            if ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh) {
                config.sceneReconstruction = .mesh
                print("✅ Scene Reconstruction aktiverat")
            } else {
                print("⚠️ Scene Reconstruction stöds inte på denna enhet")
            }
            
            session.run(config, options: [.resetTracking, .removeExistingAnchors])
        }
    func stoppa() {
        session?.pause()
    }

    func börjaSpelaIn() {
        let timestamp = Int(Date().timeIntervalSince1970)
        skanningsmapp = FileManager.default.temporaryDirectory
            .appendingPathComponent("skanning_butik_\(timestamp)")
        
        try? FileManager.default.createDirectory(
            at: skanningsmapp!, withIntermediateDirectories: true)
        
        sparadePositioner = []
        punkter3D = []
        frameRäknare = 0
        antalFrames = 0
        antal3DPunkter = 0
        maxPunkterNådd = false
        spelarIn = true
        
        print("🎬 Börjar butiksksanning")
    }

    func stoppaSpelaIn() {
        spelarIn = false
        print("⏹️ Stoppar skanning")
        print("   Frames: \(antalFrames)")
        print("   3D-punkter: \(punkter3D.count)")

        // ── Exportera fullständig LiDAR-mesh som mesh.glb ──
        // Detta innehåller golv, möbler och allt LiDAR triangulerade,
        // till skillnad från RoomPlan som bara ger väggar/fönster/dörrar.
        if let mapp = skanningsmapp {
            // Räkna ARMeshAnchors innan vi försöker exportera (för diagnostik)
            let allaAnchors = session?.currentFrame?.anchors ?? []
            let meshAnchorsNu = allaAnchors.compactMap { $0 as? ARMeshAnchor }.count
            var status = ""
            do {
                let (filURL, mb) = try MeshExporter.exportSessionsMesh(
                    session: session,
                    till: mapp
                )
                status = "OK: \(meshAnchorsNu) anchors, \(String(format: "%.2f", mb)) MB"
                print("📦 mesh.glb skriven: \(filURL.path) (\(status))")
            } catch {
                status = "FAIL: \(error.localizedDescription) [anchors_just_nu=\(meshAnchorsNu), totalt_under_skanning=\(antalMeshAnchors)]"
                print("⚠️ Kunde inte exportera mesh.glb: \(status)")
            }
            // Skriv status till disk så ServerUploader kan skicka det till servern
            // (ett sätt att se resultatet utan Xcode-konsol)
            let statusURL = mapp.appendingPathComponent("mesh_status.txt")
            try? status.data(using: .utf8)?.write(to: statusURL)
        }
    }
    //Kolla att det överlappar
    func laddaTäckning(serverURL: String) async {
        guard let url = URL(string: "\(serverURL)/scan/täckning") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            let positioner = json?["positioner"] as? [[String: Any]] ?? []
            
            let pos = positioner.compactMap { p -> (x: Float, z: Float)? in
                guard let x = (p["x"] as? NSNumber)?.floatValue,
                      let z = (p["z"] as? NSNumber)?.floatValue else { return nil }
                return (x, z)
            }
            
            await MainActor.run {
                self.tidligarePositioner = pos
            }
        } catch {
            print("⚠️ Kunde inte ladda täckning: \(error)")
        }
    }

    // Kolla överlapp under skanning (i session didUpdate)
    func kollaÖverlapp(currentX: Float, currentZ: Float) {
        if tidligarePositioner.isEmpty {
            harÖverlapp = true // Första skanningen, alltid OK
            return
        }
        
        // Kolla om vi är inom 3m från en tidigare position
        let nära = tidligarePositioner.contains { pos in
            let dx = pos.x - currentX
            let dz = pos.z - currentZ
            return sqrt(dx*dx + dz*dz) < 3.0
        }
        
        DispatchQueue.main.async {
            self.harÖverlapp = nära
        }
    }

    // ─────────────────────────────────────────────
    // FRAME PROCESSING (samma logik som GångSkanningManager)
    // ─────────────────────────────────────────────

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        guard spelarIn else { return }
        frameRäknare += 1
        guard frameRäknare % 5 == 0 else { return }
        guard let mapp = skanningsmapp else { return }
        
        let bildIndex = frameRäknare / 5
        
        // ─── Kameratransform (ingen offset — skannar från ARKit origin) ───
        let t = frame.camera.transform
        let camX = t.columns.3.x
        let camY = t.columns.3.y
        let camZ = t.columns.3.z

        // Flatta 4x4 kolumn-major för JSON (ARKit world_from_camera)
        let transformArr: [Float] = [
            t.columns.0.x, t.columns.0.y, t.columns.0.z, t.columns.0.w,
            t.columns.1.x, t.columns.1.y, t.columns.1.z, t.columns.1.w,
            t.columns.2.x, t.columns.2.y, t.columns.2.z, t.columns.2.w,
            t.columns.3.x, t.columns.3.y, t.columns.3.z, t.columns.3.w
        ]
        
        // ─── Intrinsics: ARKit ger landscape, bilden sparas portrait ───
        let intrinsics = frame.camera.intrinsics
        let fx_landscape = intrinsics[0][0]
        let fy_landscape = intrinsics[1][1]
        let cx_landscape = intrinsics[2][0]
        let cy_landscape = intrinsics[2][1]
        
        // Behåll landscape för 3D-extraktion
        fx = fx_landscape
        fy = fy_landscape
        cx = cx_landscape
        cy = cy_landscape
        
        // Konvertera till portrait (90° CW rotation):
        //   fx_P = fy_L, fy_P = fx_L
        //   cx_P = H_L - cy_L, cy_P = cx_L
        let imageW_L = Float(CVPixelBufferGetWidth(frame.capturedImage))
        let imageH_L = Float(CVPixelBufferGetHeight(frame.capturedImage))
        let fx_portrait = fy_landscape
        let fy_portrait = fx_landscape
        let cx_portrait = imageH_L - cy_landscape
        let cy_portrait = cx_landscape
        
        // Drift
        if startPosition == nil { startPosition = (camX, camZ) }
        if let (sx, sz) = startPosition {
            let drift = sqrt(pow(camX - sx, 2) + pow(camZ - sz, 2))
            DispatchQueue.main.async { self.nuvarandeDrift = drift }
        }
        
        // Loop closure-påminnelse
        if skanningsTid == nil { skanningsTid = Date() }
        let minuter = Date().timeIntervalSince(skanningsTid!) / 60
        if let (sx, sz) = startPosition {
            let avstånd = sqrt(pow(camX - sx, 2) + pow(camZ - sz, 2))
            DispatchQueue.main.async {
                self.avståndFrånStart = avstånd
                self.visaLoopPåminnelse = minuter > 5 && avstånd > 3.0
            }
        }
        
        // Kolla överlapp
        kollaÖverlapp(currentX: camX, currentZ: camZ)
        
        // 3D-punkter
        var nya3DPunkter: [Punkt3D] = []
        if punkter3D.count < maxTotalaPunkter {
            nya3DPunkter = extrahera3DPunkter(
                frame: frame, frameIndex: bildIndex, cameraTransform: t)
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
        sparaKö.async { [weak self] in
            self?.sparaFrame(frame.capturedImage, index: bildIndex, till: mapp)
        }
        
        // Spara metadata (PORTRAIT intrinsics + full transform)
        let position: [String: Any] = [
            "frame": bildIndex,
            "x": camX, "y": camY, "z": camZ,
            "rot_y": frame.camera.eulerAngles.y,
            "transform": transformArr,
            "fx": fx_portrait,
            "fy": fy_portrait,
            "cx": cx_portrait,
            "cy": cy_portrait,
            "image_width": imageH_L,
            "image_height": imageW_L,
            "har_lidar": frame.sceneDepth != nil,
            "antal_3d_punkter": nya3DPunkter.count
        ]
        
        DispatchQueue.main.async {
            self.sparadePositioner.append(position)
            self.antalFrames = bildIndex
        }
    }
    
    // ─────────────────────────────────────────────
    // MESH ANCHOR HANDLING (Scene Reconstruction)
    // ─────────────────────────────────────────────
    
    func session(_ session: ARSession, didAdd anchors: [ARAnchor]) {
        var nyaMeshAnchors = 0
        var nyaTrianglar = 0
        
        for anchor in anchors {
            if let meshAnchor = anchor as? ARMeshAnchor {
                nyaMeshAnchors += 1
                nyaTrianglar += meshAnchor.geometry.faces.count
                
                // Spara om vi spelar in
                if spelarIn {
                    sparaMeshAnchor(meshAnchor)
                }
            }
        }
        
        if nyaMeshAnchors > 0 {
            DispatchQueue.main.async {
                self.antalMeshAnchors += nyaMeshAnchors
                self.antalMeshTrianglar += nyaTrianglar
            }
        }
    }
    
    func session(_ session: ARSession, didUpdate anchors: [ARAnchor]) {
        // ARKit uppdaterar mesh-anchors löpande när skanning förfinas.
        // Vi sparar uppdaterade versioner så vi har den senaste datan.
        guard spelarIn else { return }
        
        for anchor in anchors {
            if let meshAnchor = anchor as? ARMeshAnchor {
                sparaMeshAnchor(meshAnchor)
            }
        }
    }
        
    // ─────────────────────────────────────────────
    // MESH SERIALISERING
    // ─────────────────────────────────────────────
    
    private func sparaMeshAnchor(_ meshAnchor: ARMeshAnchor) {
        guard let mapp = skanningsmapp else { return }
        
        let meshMapp = mapp.appendingPathComponent("mesh")
        try? FileManager.default.createDirectory(at: meshMapp, withIntermediateDirectories: true)
        
        let anchorId = meshAnchor.identifier.uuidString
        let filURL = meshMapp.appendingPathComponent("\(anchorId).bin")
        
        // Serialisera till kompakt binärformat
        sparaKö.async { [weak self] in
            guard let self = self else { return }
            
            do {
                let data = try self.serializeMeshAnchor(meshAnchor)
                try data.write(to: filURL)
                
                DispatchQueue.main.async {
                    let totalMB = self.beräknaMeshStorlek()
                    self.meshLagrad = totalMB
                }
            } catch {
                print("❌ Kunde inte spara mesh-anchor: \(error)")
            }
        }
    }
    
    private func serializeMeshAnchor(_ meshAnchor: ARMeshAnchor) throws -> Data {
        let geometry = meshAnchor.geometry
        let transform = meshAnchor.transform
        
        // Hämta vertices, faces, normals, classifications
        let vertices = geometry.vertices
        let faces = geometry.faces
        let normals = geometry.normals
        let classification = geometry.classification
        
        // Räkna data
        let vertexCount = vertices.count
        let faceCount = faces.count
        
        // Bygg datablob:
        // [header: vertexCount(4), faceCount(4), transform(16*4=64)]
        // [vertices: vertexCount * 3 * 4 bytes (Float3)]
        // [normals: vertexCount * 3 * 4 bytes (Float3)]
        // [faces: faceCount * 3 * 4 bytes (UInt32 trippel)]
        // [classifications: faceCount * 1 byte] (om finns)
        
        var data = Data()
        
        // Header
        var vc = UInt32(vertexCount)
        var fc = UInt32(faceCount)
        data.append(Data(bytes: &vc, count: 4))
        data.append(Data(bytes: &fc, count: 4))
        
        // Transform (4x4 column-major float)
        var t = transform
        withUnsafeBytes(of: &t) { bytes in
            data.append(contentsOf: bytes)
        }
        
        // Vertices
        let verticesBuffer = vertices.buffer
        let verticesPointer = verticesBuffer.contents().advanced(by: vertices.offset)
        let verticesData = Data(bytes: verticesPointer, count: vertexCount * vertices.stride)
        data.append(verticesData)
        
        // Normals
        let normalsBuffer = normals.buffer
        let normalsPointer = normalsBuffer.contents().advanced(by: normals.offset)
        let normalsData = Data(bytes: normalsPointer, count: vertexCount * normals.stride)
        data.append(normalsData)
        
        // Faces
        let facesBuffer = faces.buffer
        let facesPointer = facesBuffer.contents()
        let facesData = Data(bytes: facesPointer, count: faceCount * faces.bytesPerIndex * faces.indexCountPerPrimitive)
        data.append(facesData)
        
        // Classification (om finns)
        if let classification = classification {
            let classBuffer = classification.buffer
            let classPointer = classBuffer.contents().advanced(by: classification.offset)
            let classData = Data(bytes: classPointer, count: faceCount * classification.stride)
            data.append(classData)
        }
        
        return data
    }
    
    private func beräknaMeshStorlek() -> Float {
        guard let mapp = skanningsmapp else { return 0 }
        let meshMapp = mapp.appendingPathComponent("mesh")
        guard FileManager.default.fileExists(atPath: meshMapp.path) else { return 0 }
        
        var total: Int64 = 0
        if let enumerator = FileManager.default.enumerator(at: meshMapp, includingPropertiesForKeys: [.fileSizeKey]) {
            for case let url as URL in enumerator {
                if let storlek = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize {
                    total += Int64(storlek)
                }
            }
        }
        
        return Float(total) / (1024 * 1024)  // MB
    }
    
    // ─────────────────────────────────────────────
    // 3D PUNKT EXTRAKTION (samma som GångSkanningManager)
    // ─────────────────────────────────────────────

    private func extrahera3DPunkter(
        frame: ARFrame, frameIndex: Int, cameraTransform: simd_float4x4
    ) -> [Punkt3D] {
        guard let depthMap = frame.sceneDepth?.depthMap ?? frame.smoothedSceneDepth?.depthMap,
              let confidenceMap = frame.sceneDepth?.confidenceMap ?? frame.smoothedSceneDepth?.confidenceMap
        else { return [] }
        
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
        let imageWidth = CVPixelBufferGetWidth(frame.capturedImage)
        let imageHeight = CVPixelBufferGetHeight(frame.capturedImage)
        
        var totalDjup: Float = 0
        var djupCount = 0
        
        outerLoop: for row in stride(from: 0, to: depthHeight, by: samplingStep) {
            for col in stride(from: 0, to: depthWidth, by: samplingStep) {
                if punkter.count >= maxPunkterPerFrame { break outerLoop }
                
                let idx = row * depthWidth + col
                let depth = depthData[idx]
                let confidence = confData[idx]
                
                guard depth > 0.1 && depth < 5.0 && confidence >= 1 else { continue }
                
                totalDjup += depth
                djupCount += 1
                
                let u_landscape = Float(col) / Float(depthWidth) * Float(imageWidth)
                let v_landscape = Float(row) / Float(depthHeight) * Float(imageHeight)

                // ARKit camera-frame: +X right, +Y up, +Z BAKÅT.
                // Bild-pixlar har +V nedåt, depth pekar framåt → flip Y och Z
                // innan multiplikation med cameraTransform (som är ARKit world_from_camera).
                let x_cam =  (u_landscape - cx) * depth / fx
                let y_cam = -(v_landscape - cy) * depth / fy
                let z_cam = -depth

                let camPoint = SIMD4<Float>(x_cam, y_cam, z_cam, 1.0)
                let worldPoint = cameraTransform * camPoint
                
                let u_portrait = Float(imageHeight) - v_landscape
                let v_portrait = u_landscape
                
                punkter.append(Punkt3D(
                    x: worldPoint.x, y: worldPoint.y, z: worldPoint.z,
                    u: u_portrait, v: v_portrait,
                    frame: frameIndex,
                    confidence: Float(confidence) / 2.0
                ))
            }
        }
        
        if djupCount > 0 {
            DispatchQueue.main.async {
                self.medelDjup = totalDjup / Float(djupCount)
            }
        }
        
        return punkter
    }

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

struct ARKameraVyButik: UIViewRepresentable {
    let manager: ButikSkanningManager

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
// UPPLADDNINGSVY
// ─────────────────────────────────────────────────────────────────

struct ButikUppladdningsVy: View {
    @ObservedObject var uploader: ServerUploader
    let skanningsmapp: URL?
    let arFrames:      [[String: Any]]
    let punkter3D:     [Punkt3D]
    let onDismiss:     () -> Void
    
    @State private var byggSteg: String = ""
    @State private var byggProcent: Int = 0
    @State private var kartaKlar: Bool = false
    
    var body: some View {
        ZStack {
            Color.black.opacity(0.85).ignoresSafeArea()
            
            VStack(spacing: 20) {
                if kartaKlar {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 56))
                        .foregroundColor(.green)
                    Text("Kartan är klar!")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                    Text("Produkter har identifierats.\nDu kan nu söka och navigera.")
                        .font(.system(size: 14))
                        .foregroundColor(.white.opacity(0.5))
                        .multilineTextAlignment(.center)
                    Button("Klar", action: onDismiss)
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                        .padding(.horizontal, 40)
                        .padding(.vertical, 14)
                        .background(Color.green)
                        .cornerRadius(12)

                } else if uploader.klart {
                    Image(systemName: "gearshape.2.fill")
                        .font(.system(size: 44))
                        .foregroundColor(.cyan)
                        .symbolEffect(.rotate)
                    Text("Bygger karta...")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                    if !byggSteg.isEmpty {
                        Text(byggSteg)
                            .font(.system(size: 14))
                            .foregroundColor(.white.opacity(0.5))
                    }
                    ProgressView(value: Double(byggProcent), total: 100)
                        .tint(.cyan)
                        .padding(.horizontal, 50)
                    Text("\(byggProcent)%")
                        .font(.system(size: 13, design: .monospaced))
                        .foregroundColor(.white.opacity(0.4))
                    
                    Text("Du kan stänga appen — bygget fortsätter på servern.")
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.3))
                        .multilineTextAlignment(.center)
                        .padding(.top, 8)
                    
                    Button("Stäng", action: onDismiss)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(.white.opacity(0.4))
                        .padding(.top, 4)

                } else if !uploader.felmeddelande.isEmpty {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 56))
                        .foregroundColor(.red)
                    Text("Något gick fel")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                    Text(uploader.felmeddelande)
                        .font(.system(size: 14))
                        .foregroundColor(.white.opacity(0.5))
                        .multilineTextAlignment(.center)
                    Button("Försök igen") { Task { await laddaUpp() } }
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                        .padding(.horizontal, 40)
                        .padding(.vertical, 14)
                        .background(icaRöd)
                        .cornerRadius(12)

                } else {
                    ProgressView()
                        .scaleEffect(1.5)
                        .tint(.white)
                    Text("Laddar upp \(arFrames.count) frames...")
                        .font(.system(size: 15, design: .rounded))
                        .foregroundColor(.white.opacity(0.7))
                        .padding(.top, 8)
                    ProgressView(value: uploader.progress)
                        .tint(icaRöd)
                        .padding(.horizontal, 50)
                    Text("\(Int(uploader.progress * 100))%")
                        .font(.system(size: 13, design: .monospaced))
                        .foregroundColor(.white.opacity(0.4))
                }
            }
            .padding(30)
        }
        .task { await laddaUpp() }
        .task(id: uploader.klart) {
            guard uploader.klart else { return }
            await pollaByggStatus()
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
    
    func pollaByggStatus() async {
        while !kartaKlar {
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard let url = URL(string: "\(PulsArConfig.serverURL)/scan/bygg-status") else { break }
            
            do {
                let (data, _) = try await URLSession.shared.data(from: url)
                let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                let steg = json?["steg"] as? String ?? ""
                let procent = json?["procent"] as? Int ?? 0
                
                await MainActor.run {
                    byggSteg = steg
                    byggProcent = procent
                    if procent >= 100 { kartaKlar = true }
                }
            } catch {
                break
            }
        }
    }
}
