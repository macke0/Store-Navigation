//
//  KundAssistentView.swift
//  PulsAr
//
//  Kund-flödets varusökning: skriv vad du letar efter → träffar direkt →
//  tryck för att navigera till varan i butiken (AR). De mest sökta varorna
//  ligger som snabbknappar överst så vanliga köp går på ett tryck.
//
//  Sökning: lokalt på telefonen (LokalSökmotor, instant) + en smartare
//  serversökning (/sok?q=) som uppgraderar träffarna strax efter.
//

import SwiftUI
import Combine

struct KundAssistentView: View {
    @StateObject private var sökmotor = LokalSökmotor.shared
    @State private var sökText = ""
    @State private var produkter: [SökProdukt] = []
    @State private var laddar = false
    @State private var harSökt = false
    @State private var valdProdukt: SökProdukt?
    @State private var sökTask: Task<Void, Never>?
    @FocusState private var fältFokus: Bool

    private let serverURL = PulsArConfig.serverURL

    // De mest sökta varorna — ett tryck fyller sökfältet och söker direkt.
    private let populära: [(ikon: String, namn: String)] = [
        ("drop.fill", "Mjölk"),
        ("cup.and.saucer.fill", "Kaffe"),
        ("birthday.cake.fill", "Bröd"),
        ("fork.knife", "Kyckling"),
        ("fish.fill", "Lax"),
        ("carrot.fill", "Tomater"),
        ("leaf.fill", "Bananer"),
        ("takeoutbag.and.cup.and.straw.fill", "Läsk"),
    ]

    var body: some View {
        ZStack {
            Tema.bakgrund.ignoresSafeArea()

            VStack(spacing: 0) {
                sökFält
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 8)

                resultat
            }
        }
        .navigationTitle("Hitta en vara")
        .navigationBarTitleDisplayMode(.inline)
        .fullScreenCover(item: $valdProdukt) { produkt in
            ARNavigationView(produkt: produkt)
        }
        .task { await sökmotor.laddaProdukter(serverURL: serverURL) }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { fältFokus = true }
        }
    }

    // MARK: Sökfält

    private var sökFält: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(Tema.textSvag)

            TextField("Vad letar du efter?", text: $sökText)
                .foregroundColor(Tema.text)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .focused($fältFokus)
                .onChange(of: sökText) { _, ny in hanteraSökning(ny) }

            if laddar {
                ProgressView().tint(Tema.röd).scaleEffect(0.7)
            } else if !sökText.isEmpty {
                Button(action: rensa) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundColor(Tema.textTunn)
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .kortYta(hörn: 14)
    }

    // MARK: Resultat / populärt

    @ViewBuilder
    private var resultat: some View {
        if sökText.isEmpty && !harSökt {
            populäraVy
        } else if produkter.isEmpty && harSökt && !laddar {
            tomVy
        } else {
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(produkter) { produkt in
                        ProduktRad(produkt: produkt) {
                            Haptik.tryck()
                            valdProdukt = produkt
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
            }
        }
    }

    private var populäraVy: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("MEST SÖKTA")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(Tema.textSvag)
                    .tracking(1.5)
                    .padding(.horizontal, 4)

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 100), spacing: 10)], spacing: 10) {
                    ForEach(populära, id: \.namn) { vara in
                        Button {
                            Haptik.tryck()
                            sökText = vara.namn
                        } label: {
                            VStack(spacing: 10) {
                                ZStack {
                                    Circle()
                                        .fill(Tema.röd.opacity(0.10))
                                        .frame(width: 44, height: 44)
                                    Image(systemName: vara.ikon)
                                        .font(.system(size: 18, weight: .semibold))
                                        .foregroundColor(Tema.röd)
                                }
                                Text(vara.namn)
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                                    .foregroundColor(Tema.text)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 16)
                            .kortYta(hörn: 14)
                        }
                        .buttonStyle(TryckStyle())
                    }
                }
            }
            .padding(16)
        }
    }

    private var tomVy: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "magnifyingglass")
                .font(.system(size: 40))
                .foregroundColor(Tema.textTunn)
            Text("Inga varor hittades")
                .font(.system(size: 15, weight: .medium, design: .rounded))
                .foregroundColor(Tema.textSvag)
            Spacer()
        }
    }

    // MARK: Söklogik

    private func hanteraSökning(_ text: String) {
        sökTask?.cancel()
        let q = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard q.count >= 2 else {
            withAnimation(.easeInOut(duration: 0.15)) {
                produkter = []; harSökt = false
            }
            return
        }

        sökTask = Task { @MainActor in
            harSökt = true

            // Liten debounce, sen instant lokal träff.
            try? await Task.sleep(nanoseconds: 100_000_000)
            guard !Task.isCancelled else { return }
            let lokala = await Task.detached(priority: .userInitiated) {
                sökmotor.sök(query: q)
            }.value
            guard !Task.isCancelled else { return }
            withAnimation(.easeInOut(duration: 0.15)) { produkter = lokala }

            // Uppgradera med serverns smartare sökning strax efter.
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            await serverSök(q)
        }
    }

    private func serverSök(_ query: String) async {
        guard let enc = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(serverURL)/sok?q=\(enc)") else { return }
        laddar = true
        defer { laddar = false }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            guard !Task.isCancelled else { return }
            let svar = try JSONDecoder().decode(SökSvar.self, from: data)
            if !svar.produkter.isEmpty {
                withAnimation(.easeInOut(duration: 0.2)) { produkter = svar.produkter }
            }
        } catch {
            // Lokala träffar står kvar — ingen anledning att störa kunden.
        }
    }

    private func rensa() {
        sökText = ""
        sökTask?.cancel()
        withAnimation(.easeInOut(duration: 0.15)) {
            produkter = []; harSökt = false
        }
        fältFokus = true
    }
}

// MARK: - Produktrad (ljust kort)

private struct ProduktRad: View {
    let produkt: SökProdukt
    let onTryck: () -> Void

    var body: some View {
        Button(action: onTryck) {
            HStack(spacing: 14) {
                bild

                VStack(alignment: .leading, spacing: 3) {
                    Text(produkt.visningsnamn)
                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                        .foregroundColor(Tema.text)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)

                    HStack(spacing: 6) {
                        if !produkt.varumarke.isEmpty {
                            Text(produkt.varumarke)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Tema.textSvag)
                        }
                        if !produkt.varumarke.isEmpty && !produkt.kategori.isEmpty {
                            Circle().fill(Tema.textTunn).frame(width: 3, height: 3)
                        }
                        if !produkt.kategori.isEmpty {
                            Text(produkt.kategori)
                                .font(.system(size: 12))
                                .foregroundColor(Tema.textTunn)
                        }
                    }
                }

                Spacer()

                Image(systemName: "location.fill")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(Tema.röd)
            }
            .padding(12)
            .kortYta(hörn: 14)
        }
        .buttonStyle(TryckStyle())
    }

    private var bild: some View {
        Group {
            if let url = produkt.bild_url, !url.isEmpty, let u = URL(string: url) {
                AsyncImage(url: u) { fas in
                    switch fas {
                    case .success(let bild):
                        bild.resizable().aspectRatio(contentMode: .fit)
                    case .empty:
                        platshållare.overlay(ProgressView().scaleEffect(0.6).tint(Tema.röd))
                    default:
                        platshållare
                    }
                }
                .frame(width: 52, height: 52)
                .background(Color.white)
                .cornerRadius(10)
            } else {
                platshållare
            }
        }
    }

    private var platshållare: some View {
        RoundedRectangle(cornerRadius: 10)
            .fill(Tema.röd.opacity(0.08))
            .frame(width: 52, height: 52)
            .overlay(
                Image(systemName: "basket.fill")
                    .font(.system(size: 18))
                    .foregroundColor(Tema.röd.opacity(0.5))
            )
    }
}

#Preview {
    NavigationView { KundAssistentView() }
}
