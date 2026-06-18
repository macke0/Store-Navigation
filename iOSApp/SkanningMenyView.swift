//
//  SkanningMenyView.swift
//  PulsAr
//

import SwiftUI

private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)

struct SkanningMenyView: View {
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationView {
            ZStack {
                Color.black.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 20) {
                        // Header
                        VStack(spacing: 8) {
                            Image(systemName: "building.2.fill")
                                .font(.system(size: 40))
                                .foregroundColor(icaRöd)
                            Text("Personal")
                                .font(.system(size: 32, weight: .bold, design: .rounded))
                                .foregroundColor(.white)
                            Text("ICA Maxi Bromma")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(.white.opacity(0.4))
                                .tracking(2)
                                .textCase(.uppercase)
                        }
                        .padding(.top, 40)
                        .padding(.bottom, 10)

                        // Skanna butiken
                        StegKort(
                            titel:       "Skanna butiken",
                            beskrivning: "Filma hyllorna genom att gå genom butiken. Pausa och fortsätt när du vill.",
                            ikon:        "camera.viewfinder",
                            färg:        icaRöd
                        ) {
                            AnyView(PreflightView())
                        }

                        // Läge 2 — Skanna produkter mot befintlig karta
                        StegKort(
                            titel:       "Skanna produkter",
                            beskrivning: "Lokalisera dig mot kartan, sedan filma hyllorna. Produkter sparas med koordinater.",
                            ikon:        "tag.fill",
                            färg:        .purple
                        ) {
                            AnyView(ProduktSkanningView(kartaNamn: "hela_butiken"))
                        }
                        /*
                        // Kartlägg (behålls för ankarpunkter)
                        StegKort(
                            titel:       "Markera referenspunkter",
                            beskrivning: "Markera kassor, pelare och andra fasta punkter. Görs en gång.",
                            ikon:        "mappin.and.ellipse",
                            färg:        .orange
                        ) {
                            AnyView(KartläggView())
                        }
                        */
                        StegKort(
                            titel:       "Kalibrera butikskarta",
                            beskrivning: "Koppla ICAs butikskarta till VPS. Gå till 3 punkter i butiken.",
                            ikon:        "map.fill",
                            färg:        .blue
                        ) {
                            AnyView(KalibreringView(butikId: "bromma_maxi"))
                        }
                        
                        // Kundens navigationsvy - visa position på karta
                        StegKort(
                            titel:       "Öppna navigationskarta",
                            beskrivning: "Se din position på butikskartan. Kräver kalibrering.",
                            ikon:        "location.north.circle.fill",
                            färg:        .cyan
                        ) {
                            AnyView(NavigationKartView(butikId: "bromma_maxi"))
                        }

                        // VPS-test - lokalisera mot 3D-karta + visa live på admin-vy
                        StegKort(
                            titel:       "Testa VPS-lokalisering",
                            beskrivning: "Stå på en känd plats, scanna och se din position som blå dot på /viewer/3d.",
                            ikon:        "location.viewfinder",
                            färg:        .green
                        ) {
                            AnyView(VPSTestView())
                        }

                        // Tips
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Tips")
                                .font(.system(size: 15, weight: .bold, design: .rounded))
                                .foregroundColor(.white)

                            InfoRad(ikon: "lightbulb.fill",
                                    text: "Bra belysning ger bättre produktigenkänning")
                            InfoRad(ikon: "figure.walk",
                                    text: "Gå långsamt och stadigt längs hyllan")
                            InfoRad(ikon: "arrow.left.and.right",
                                    text: "Filma från olika vinklar för bättre precision")
                            InfoRad(ikon: "camera.fill",
                                    text: "Håll kameran mot hylltaggarna")
                            InfoRad(ikon: "pause.circle",
                                    text: "Pausa och fortsätt när som helst")
                        }
                        .padding()
                        .background(Color.white.opacity(0.04))
                        .cornerRadius(16)
                        .padding(.horizontal)

                        Button { dismiss() } label: {
                            Text("Stäng")
                                .foregroundColor(.white.opacity(0.3))
                                .padding(.bottom, 40)
                        }
                    }
                }
            }
            .navigationBarHidden(true)
        }
    }
}

// ─────────────────────────────────────────────────────────────────
// HJÄLPVYER
// ─────────────────────────────────────────────────────────────────

struct StegKort<Destination: View>: View {
    let titel:       String
    let beskrivning: String
    let ikon:        String
    let färg:        Color
    let destination: () -> Destination

    var body: some View {
        NavigationLink(destination: destination()) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 12)
                        .fill(färg.opacity(0.15))
                        .frame(width: 44, height: 44)
                    Image(systemName: ikon)
                        .font(.system(size: 18))
                        .foregroundColor(färg)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(titel)
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                        .foregroundColor(.white)
                    Text(beskrivning)
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.4))
                        .multilineTextAlignment(.leading)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(.white.opacity(0.2))
            }
            .padding(14)
            .background(Color.white.opacity(0.05))
            .cornerRadius(14)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(färg.opacity(0.2), lineWidth: 1)
            )
            .padding(.horizontal)
        }
    }
}

struct InfoRad: View {
    let ikon: String
    let text: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: ikon)
                .font(.system(size: 13))
                .foregroundColor(.yellow.opacity(0.8))
                .frame(width: 20)
            Text(text)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.45))
        }
    }
}
