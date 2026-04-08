//
//  SkanningMenyView.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-03-31.
//


import SwiftUI

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
                                .foregroundColor(.blue)
                            Text("Skanna butik")
                                .font(.largeTitle).fontWeight(.bold)
                                .foregroundColor(.white)
                            Text("ICA Maxi Bromma")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                        .padding(.top, 40)
                        .padding(.bottom, 10)

                        // Steg 0 — Kartlägg
                        StegKort(
                            nummer:      "0",
                            titel:       "Kartlägg butiken",
                            beskrivning: "Gå längs butiken och markera gångingångar, kassor och pelare. Görs en gång.",
                            ikon:        "mappin.and.ellipse",
                            färg:        .orange
                        ) {
                            AnyView(KartläggView())
                        }

                        // Steg 1 — Skanna gång
                        StegKort(
                            nummer:      "1",
                            titel:       "Skanna gång",
                            beskrivning: "Välj gång, starta vid ingången och filma längs hyllan. Återvänd till start.",
                            ikon:        "video.fill",
                            färg:        .green
                        ) {
                            AnyView(GångSkanningView())
                        }

                        // Info-kort
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Tips")
                                .font(.headline)
                                .foregroundColor(.white)

                            InfoRad(ikon: "lightbulb.fill",
                                    text: "Bra belysning ger bättre produktigenkänning")
                            InfoRad(ikon: "figure.walk",
                                    text: "Gå långsamt och stadigt längs hyllan")
                            InfoRad(ikon: "arrow.uturn.backward",
                                    text: "Återvänd alltid till startpunkten för loop closure")
                            InfoRad(ikon: "camera.fill",
                                    text: "Håll kameran mot hylltaggarna")
                        }
                        .padding()
                        .background(Color.white.opacity(0.05))
                        .cornerRadius(16)
                        .padding(.horizontal)

                        Button { dismiss() } label: {
                            Text("Stäng")
                                .foregroundColor(.secondary)
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
    let nummer:      String
    let titel:       String
    let beskrivning: String
    let ikon:        String
    let färg:        Color
    let destination: () -> Destination

    var body: some View {
        NavigationLink(destination: destination()) {
            HStack(spacing: 16) {
                // Stegnummer
                ZStack {
                    Circle()
                        .fill(färg.opacity(0.2))
                        .frame(width: 44, height: 44)
                    Text(nummer)
                        .font(.headline)
                        .foregroundColor(färg)
                }

                // Ikon
                Image(systemName: ikon)
                    .font(.title2)
                    .foregroundColor(färg)
                    .frame(width: 32)

                // Text
                VStack(alignment: .leading, spacing: 4) {
                    Text(titel)
                        .font(.headline)
                        .foregroundColor(.white)
                    Text(beskrivning)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.leading)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .foregroundColor(.secondary)
                    .font(.caption)
            }
            .padding()
            .background(Color.white.opacity(0.05))
            .cornerRadius(16)
            .overlay(
                RoundedRectangle(cornerRadius: 16)
                    .stroke(färg.opacity(0.3), lineWidth: 1)
            )
            .padding(.horizontal)
        }
    }
}

struct InfoRad: View {
    let ikon: String
    let text: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: ikon)
                .foregroundColor(.yellow)
                .frame(width: 20)
            Text(text)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}