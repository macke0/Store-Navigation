//
//  KartläggView.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-03-31.
//

import SwiftUI
import ARKit
import Combine

// ─────────────────────────────────────────────────────────────────
// HUVUDVY
// ─────────────────────────────────────────────────────────────────

struct KartläggView: View {
    @StateObject private var manager = KartläggManager()
    @State private var visaNamnDialog = false
    @State private var nyttNamn       = ""
    @Environment(\.dismiss) var dismiss

    var body: some View {
        ZStack {
            ARKameraVyKartlägg(manager: manager)
                .ignoresSafeArea()

            VStack {
                // Statusrad
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Kartlägg butik")
                            .font(.headline).foregroundColor(.white)
                        Text("\(manager.ankarpunkter.count) punkter markerade")
                            .font(.caption).foregroundColor(.secondary)
                    }
                    Spacer()
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .foregroundColor(.white)
                            .padding(8)
                            .background(.ultraThinMaterial)
                            .clipShape(Circle())
                    }
                }
                .padding()
                .background(.ultraThinMaterial)

                Spacer()

                // Markerade punkter
                if !manager.ankarpunkter.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(manager.ankarpunkter) { punkt in
                                HStack(spacing: 6) {
                                    Image(systemName: punkt.ikon)
                                        .font(.caption)
                                        .foregroundColor(punkt.färg)
                                    Text(punkt.namn)
                                        .font(.caption)
                                        .foregroundColor(.white)
                                    Button {
                                        manager.taBortPunkt(punkt)
                                    } label: {
                                        Image(systemName: "xmark")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(.ultraThinMaterial)
                                .cornerRadius(20)
                            }
                        }
                        .padding(.horizontal)
                    }
                    .padding(.bottom, 8)
                }

                // Snabbval
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(snabbval, id: \.0) { namn, ikon in
                            Button {
                                manager.läggTillPunkt(namn: namn, ikon: ikon)
                            } label: {
                                HStack(spacing: 4) {
                                    Image(systemName: ikon).font(.caption)
                                    Text(namn).font(.caption)
                                }
                                .foregroundColor(.white)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 8)
                                .background(Color.blue.opacity(0.3))
                                .cornerRadius(20)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 20)
                                        .stroke(Color.blue.opacity(0.5), lineWidth: 1)
                                )
                            }
                        }

                        Button {
                            visaNamnDialog = true
                        } label: {
                            HStack(spacing: 4) {
                                Image(systemName: "plus").font(.caption)
                                Text("Annat...").font(.caption)
                            }
                            .foregroundColor(.white)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(Color.green.opacity(0.3))
                            .cornerRadius(20)
                            .overlay(
                                RoundedRectangle(cornerRadius: 20)
                                    .stroke(Color.green.opacity(0.5), lineWidth: 1)
                            )
                        }
                    }
                    .padding(.horizontal)
                }
                .padding(.bottom, 8)

                // Spara-knapp
                Button {
                    Task { await manager.sparaTillServer() }
                } label: {
                    HStack {
                        if manager.sparar {
                            ProgressView().tint(.white).scaleEffect(0.8)
                        } else {
                            Image(systemName: manager.sparad ? "checkmark" : "icloud.and.arrow.up")
                        }
                        Text(manager.sparar ? "Sparar..." :
                             manager.sparad ? "Sparat!" :
                             "Spara (återvänd till start först)")
                            .fontWeight(.semibold)
                            .font(.subheadline)
                    }
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(manager.sparad ? Color.green : Color.blue)
                    .cornerRadius(14)
                    .padding(.horizontal)
                }
                .padding(.bottom, 40)
                .disabled(manager.ankarpunkter.isEmpty || manager.sparar)
            }
        }
        .navigationBarHidden(true)
        .sheet(isPresented: $visaNamnDialog) {
            anpassatNamnDialog
        }
    }

    // Snabbval för vanliga benämningar
    let snabbval: [(String, String)] = [
        ("Gång 1",  "arrow.right"),
        ("Gång 2",  "arrow.right"),
        ("Gång 3",  "arrow.right"),
        ("Gång 4",  "arrow.right"),
        ("Gång 5",  "arrow.right"),
        ("Gång 6",  "arrow.right"),
        ("Gång 7",  "arrow.right"),
        ("Gång 8",  "arrow.right"),
        ("Gång 9",  "arrow.right"),
        ("Gång 10", "arrow.right"),
        ("Gång 11", "arrow.right"),
        ("Gång 12", "arrow.right"),
        ("Gång 13", "arrow.right"),
        ("Gång 14", "arrow.right"),
        ("Gång 15", "arrow.right"),
        ("Kassan",       "dollarsign.circle"),
        ("Ingången",     "door.left.hand.open"),
        ("Mejeri",       "refrigerator"),
        ("Bröd",         "basket"),
        ("Pelare",       "building.columns"),
        ("Frukt & Grönt","leaf"),
        ("Frys",         "snowflake"),
        ("Kött & Fisk",  "fork.knife"),
    ]

    var anpassatNamnDialog: some View {
        NavigationView {
            VStack(spacing: 20) {
                Text("Namnge ankarpunkt")
                    .font(.headline)

                TextField("T.ex. 'Gång 16' eller 'Pelare vid mejeri'",
                          text: $nyttNamn)
                    .textFieldStyle(.roundedBorder)
                    .padding(.horizontal)

                Button("Lägg till") {
                    if !nyttNamn.isEmpty {
                        manager.läggTillPunkt(namn: nyttNamn, ikon: "mappin")
                        nyttNamn      = ""
                        visaNamnDialog = false
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(nyttNamn.isEmpty)
            }
            .padding()
            .navigationTitle("Ny ankarpunkt")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Avbryt") { visaNamnDialog = false }
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// MANAGER
// ─────────────────────────────────────────────────────────────────

class KartläggManager: NSObject, ObservableObject, ARSessionDelegate {
    private var session:      ARSession?
    private var senasteFrame: ARFrame?

    @Published var ankarpunkter: [Ankarpunkt] = []
    @Published var sparar = false
    @Published var sparad = false

    func startaSession(session: ARSession) {
        self.session      = session
        session.delegate  = self
        let config        = ARWorldTrackingConfiguration()
        config.planeDetection = []
        session.run(config, options: [.resetTracking, .removeExistingAnchors])
    }

    func stoppa() { session?.pause() }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        senasteFrame = frame
    }

    func läggTillPunkt(namn: String, ikon: String) {
        guard let frame = senasteFrame else { return }
        let t = frame.camera.transform
        let punkt = Ankarpunkt(
            namn: namn,
            ikon: ikon,
            x:    t.columns.3.x,
            y:    t.columns.3.y,
            z:    t.columns.3.z
        )
        DispatchQueue.main.async {
            self.ankarpunkter.append(punkt)
            self.sparad = false
        }
        print("📍 Markerade: \(namn) @ (\(String(format: "%.2f", t.columns.3.x)), \(String(format: "%.2f", t.columns.3.z)))")
    }

    func taBortPunkt(_ punkt: Ankarpunkt) {
        ankarpunkter.removeAll { $0.id == punkt.id }
    }

    func sparaTillServer() async {
        guard !ankarpunkter.isEmpty else { return }
        DispatchQueue.main.async { self.sparar = true }

        // Loop closure — korrigera drift om återvänt till start
        let korrigerade = korrigeraAnkarpunkter(ankarpunkter)

        let data = korrigerade.map { $0.tillDict() }
        guard let json = try? JSONSerialization.data(withJSONObject: data) else {
            DispatchQueue.main.async { self.sparar = false }
            return
        }

        var request        = URLRequest(url: URL(string: "http://192.168.0.166:8000/ankarpunkter/")!)
        request.httpMethod = "POST"
        request.httpBody   = json
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30

        do {
            let (_, _) = try await URLSession.shared.data(for: request)
            DispatchQueue.main.async {
                self.sparar = false
                self.sparad = true
            }
            print("✅ Ankarpunkter sparade")
        } catch {
            DispatchQueue.main.async { self.sparar = false }
            print("❌ Fel: \(error)")
        }
    }

    // ─────────────────────────────────────────────
    // LOOP CLOSURE FÖR ANKARPUNKTER
    // ─────────────────────────────────────────────

    private func korrigeraAnkarpunkter(_ punkter: [Ankarpunkt]) -> [Ankarpunkt] {
        guard punkter.count >= 2 else { return punkter }

        let start  = punkter.first!
        let slut   = punkter.last!
        let driftX = slut.x - start.x
        let driftZ = slut.z - start.z
        let totalDrift = sqrt(driftX*driftX + driftZ*driftZ)

        guard totalDrift < 2.0 else {
            print("⚠️  Inget loop closure — återvänd till startpunkten")
            return punkter
        }

        print("✅ Loop closure: \(String(format: "%.2f", totalDrift))m drift korrigerad")

        // Beräkna ackumulerad sträcka
        var längder: [Float] = [0]
        for i in 1..<punkter.count {
            let dx = punkter[i].x - punkter[i-1].x
            let dz = punkter[i].z - punkter[i-1].z
            längder.append(längder.last! + sqrt(dx*dx + dz*dz))
        }
        let totalLängd = längder.last!
        
        print("🔍 Loop closure check:")
        print("   Start: (\(start.x), \(start.z))")
        print("   Slut:  (\(slut.x), \(slut.z))")
        print("   Drift: \(String(format: "%.2f", totalDrift))m")
        print("   Tröskel: 2.0m")
        
        guard totalLängd > 0.1 else { return punkter }
        

        // Korrigera med smooth S-kurva
        return punkter.enumerated().map { i, punkt in
            let t       = längder[i] / totalLängd
            let tSmooth = t * t * (3 - 2 * t)
            return Ankarpunkt(
                namn: punkt.namn,
                ikon: punkt.ikon,
                x:    punkt.x - driftX * tSmooth,
                y:    punkt.y,
                z:    punkt.z - driftZ * tSmooth
            )
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// AR-KAMERAVY
// ─────────────────────────────────────────────────────────────────

struct ARKameraVyKartlägg: UIViewRepresentable {
    let manager: KartläggManager

    func makeUIView(context: Context) -> ARSCNView {
        let scnView = ARSCNView(frame: .zero)
        scnView.automaticallyUpdatesLighting = false
        scnView.scene = SCNScene()
        DispatchQueue.main.async {
            manager.startaSession(session: scnView.session)
        }
        return scnView
    }

    func updateUIView(_ uiView: ARSCNView, context: Context) {}
}
