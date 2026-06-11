//
//  KundAssistentView.swift
//  PulsAr
//
//  Kund-flödets framsida: AI-assistent som hjälper kunden planera inköp.
//  Varje svar kan innehålla produkter med en "Hitta i butiken"-knapp som
//  startar AR-navigeringen direkt.
//
//  Backend: POST /chat/kund/assistent → { svar, session_id, produkter[] }
//

import SwiftUI

// MARK: - Modeller

/// En produkt som assistenten föreslår, med kartposition för navigering.
struct KundProdukt: Codable, Identifiable, Hashable {
    let produkt_id: String
    let visningsnamn: String?
    let x: Double?
    let y: Double?
    let z: Double?

    var id: String { produkt_id }

    /// Bygg en SökProdukt så att vi kan återanvända ARNavigationView.
    var somSökProdukt: SökProdukt {
        SökProdukt(
            id: produkt_id,
            visningsnamn: visningsnamn ?? produkt_id,
            varumarke: "",
            kategori: "",
            bild_url: nil,
            gång: nil,
            x: x,
            y: y,
            z: z,
            status: nil
        )
    }

    /// Har produkten en känd kartposition?
    var harPosition: Bool { x != nil && z != nil }
}

private struct KundAssistentRequest: Codable {
    let meddelande: String
    let session_id: String?
}

private struct KundAssistentResponse: Codable {
    let svar: String
    let session_id: String
    let produkter: [KundProdukt]
}

/// Ett meddelande i konversationen. Assistentsvar kan bära produkter.
struct KundMeddelande: Identifiable {
    let id = UUID()
    let roll: Roll
    let text: String
    let produkter: [KundProdukt]

    enum Roll { case kund, assistent }
}

// MARK: - Service

@MainActor
final class KundAssistentService: ObservableObject {
    @Published var meddelanden: [KundMeddelande] = []
    @Published var laddar = false

    private var sessionId: String?
    private let baseURL = PulsArConfig.serverURL

    func skicka(_ text: String) async {
        let rensad = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !rensad.isEmpty else { return }

        meddelanden.append(KundMeddelande(roll: .kund, text: rensad, produkter: []))
        laddar = true

        do {
            let svar = try await postAssistent(rensad)
            sessionId = svar.session_id
            meddelanden.append(
                KundMeddelande(roll: .assistent, text: svar.svar, produkter: svar.produkter)
            )
        } catch let fel as URLError where fel.code == .timedOut {
            felmeddelande("Servern tog för lång tid. Försök igen om en stund.")
        } catch let fel as URLError where fel.code == .cannotConnectToHost || fel.code == .notConnectedToInternet {
            felmeddelande("Kan inte nå servern. Kontrollera nätverket.")
        } catch {
            felmeddelande("Något gick fel: \(error.localizedDescription)")
        }

        laddar = false
    }

    func rensa() {
        meddelanden.removeAll()
        sessionId = nil
    }

    private func felmeddelande(_ text: String) {
        meddelanden.append(KundMeddelande(roll: .assistent, text: text, produkter: []))
    }

    private func postAssistent(_ meddelande: String) async throws -> KundAssistentResponse {
        guard let url = URL(string: "\(baseURL)/chat/kund/assistent") else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30
        request.httpBody = try JSONEncoder().encode(
            KundAssistentRequest(meddelande: meddelande, session_id: sessionId)
        )

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(KundAssistentResponse.self, from: data)
    }
}

// MARK: - Vy

struct KundAssistentView: View {
    @StateObject private var service = KundAssistentService()
    @State private var inmatning = ""
    @State private var valdProdukt: SökProdukt?
    @FocusState private var fältFokus: Bool

    private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 0) {
                meddelandeLista
                inmatningsRad
            }
        }
        .navigationTitle("Assistent")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button { service.rensa() } label: {
                    Image(systemName: "trash")
                }
                .tint(.white.opacity(0.6))
            }
        }
        .fullScreenCover(item: $valdProdukt) { produkt in
            ARNavigationView(produkt: produkt)
        }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { fältFokus = true }
        }
    }

    // MARK: Meddelanden

    private var meddelandeLista: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 14) {
                    if service.meddelanden.isEmpty {
                        välkomst
                    }
                    ForEach(service.meddelanden) { m in
                        meddelandeBubbla(m).id(m.id)
                    }
                    if service.laddar {
                        HStack(spacing: 8) {
                            ProgressView().tint(.white).scaleEffect(0.8)
                            Text("Tänker...").foregroundColor(.white.opacity(0.5))
                            Spacer()
                        }
                        .padding(.horizontal)
                    }
                }
                .padding()
            }
            .onChange(of: service.meddelanden.count) { _, _ in
                if let sista = service.meddelanden.last {
                    withAnimation { proxy.scrollTo(sista.id, anchor: .bottom) }
                }
            }
        }
    }

    private var välkomst: some View {
        VStack(spacing: 16) {
            Image(systemName: "sparkles")
                .font(.system(size: 44))
                .foregroundColor(icaRöd)
            Text("Hej! Vad ska du handla idag?")
                .font(.system(size: 18, weight: .semibold, design: .rounded))
                .foregroundColor(.white)
            VStack(spacing: 8) {
                förslagKnapp("Jag vill laga vegansk middag")
                förslagKnapp("Vad behöver jag till tacos?")
                förslagKnapp("Visa nyttiga mellanmål")
            }
        }
        .padding(.vertical, 40)
    }

    private func förslagKnapp(_ text: String) -> some View {
        Button {
            Task { await service.skicka(text) }
        } label: {
            HStack {
                Image(systemName: "text.bubble").foregroundColor(icaRöd)
                Text(text).foregroundColor(.white).font(.system(size: 14))
                Spacer()
                Image(systemName: "arrow.up.circle.fill").foregroundColor(icaRöd)
            }
            .padding()
            .background(Color.white.opacity(0.06))
            .cornerRadius(12)
        }
    }

    @ViewBuilder
    private func meddelandeBubbla(_ m: KundMeddelande) -> some View {
        HStack {
            if m.roll == .kund { Spacer(minLength: 50) }

            VStack(alignment: m.roll == .kund ? .trailing : .leading, spacing: 8) {
                Text(m.text)
                    .padding(12)
                    .background(m.roll == .kund ? icaRöd : Color.white.opacity(0.1))
                    .foregroundColor(.white)
                    .cornerRadius(16)

                ForEach(m.produkter) { produkt in
                    hittaKnapp(produkt)
                }
            }

            if m.roll == .assistent { Spacer(minLength: 50) }
        }
    }

    private func hittaKnapp(_ produkt: KundProdukt) -> some View {
        Button {
            valdProdukt = produkt.somSökProdukt
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "location.fill")
                    .font(.system(size: 12, weight: .bold))
                Text(produkt.visningsnamn ?? produkt.produkt_id)
                    .font(.system(size: 13, weight: .semibold))
                    .lineLimit(1)
                Spacer(minLength: 4)
                Text("Hitta i butiken")
                    .font(.system(size: 11, weight: .bold))
                    .opacity(0.85)
                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .bold))
            }
            .foregroundColor(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(produkt.harPosition ? icaRöd.opacity(0.9) : Color.gray.opacity(0.4))
            .cornerRadius(12)
        }
        .disabled(!produkt.harPosition)
    }

    // MARK: Inmatning

    private var inmatningsRad: some View {
        HStack(spacing: 12) {
            TextField("Skriv ett meddelande...", text: $inmatning)
                .foregroundColor(.white)
                .padding(12)
                .background(Color.white.opacity(0.08))
                .cornerRadius(20)
                .focused($fältFokus)
                .onSubmit(skicka)

            Button(action: skicka) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 32))
                    .foregroundColor(inmatning.isEmpty ? .gray : icaRöd)
            }
            .disabled(inmatning.isEmpty || service.laddar)
        }
        .padding()
        .background(Color.white.opacity(0.03))
    }

    private func skicka() {
        let text = inmatning
        inmatning = ""
        Task { await service.skicka(text) }
    }
}

#Preview {
    NavigationView { KundAssistentView() }
        .preferredColorScheme(.dark)
}
