import SwiftUI
import Combine



typealias ProduktResultat = SökProdukt

final class SökCache {
    static let shared = SökCache()
    private var cache: [String: [SökProdukt]] = [:]
    func spara(query: String, produkter: [SökProdukt]) {
        cache[query.lowercased().trimmingCharacters(in: .whitespaces)] = produkter
    }
    func hämta(query: String) -> [SökProdukt]? {
        cache[query.lowercased().trimmingCharacters(in: .whitespaces)]
    }
}

struct SökProdukt: Codable, Identifiable, Hashable {
    let id: String
    let visningsnamn: String
    let varumarke: String
    let kategori: String
    let bild_url: String?
    let gång: Int?
    let x: Double?
    let y: Double?
    let z: Double?
    let status: String?
}

struct SökSvar: Codable {
    let query: String
    let antal: Int
    let produkter: [SökProdukt]
}


// ICA-färger
private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)
private let icaMörkRöd = Color(red: 0.72, green: 0.08, blue: 0.12)

// MARK: - Produktkort
struct ProduktKort: View {
    let produkt: SökProdukt
    let onNavigera: () -> Void

    var body: some View {
        Button(action: onNavigera) {
            HStack(spacing: 14) {
                // Produktbild
                if let bildUrl = produkt.bild_url, !bildUrl.isEmpty, let url = URL(string: bildUrl) {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .empty:
                            bildPlaceholder
                                .overlay(ProgressView().scaleEffect(0.6).tint(.white))
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                                .frame(width: 56, height: 56)
                                .cornerRadius(10)
                        case .failure:
                            bildPlaceholder
                        @unknown default:
                            bildPlaceholder
                        }
                    }
                } else {
                    bildPlaceholder
                }

                // Info
                VStack(alignment: .leading, spacing: 4) {
                    Text(produkt.visningsnamn)
                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                        .foregroundColor(.white)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)

                    HStack(spacing: 6) {
                        if !produkt.varumarke.isEmpty {
                            Text(produkt.varumarke)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.white.opacity(0.5))
                        }

                        if !produkt.varumarke.isEmpty && !produkt.kategori.isEmpty {
                            Circle()
                                .fill(.white.opacity(0.3))
                                .frame(width: 3, height: 3)
                        }

                        if !produkt.kategori.isEmpty {
                            Text(produkt.kategori)
                                .font(.system(size: 12))
                                .foregroundColor(.white.opacity(0.35))
                        }
                    }

                    if let gång = produkt.gång {
                        HStack(spacing: 4) {
                            Image(systemName: "mappin.circle.fill")
                                .font(.system(size: 11))
                                .foregroundColor(icaRöd)
                            Text("Gång \(gång)")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundColor(icaRöd)
                        }
                    }
                }

                Spacer()

                // Navigera
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(.white.opacity(0.25))
            }
            .padding(12)
            .background(Color.white.opacity(0.06))
            .cornerRadius(14)
            .overlay(
                RoundedRectangle(cornerRadius: 14)
                    .stroke(Color.white.opacity(0.06), lineWidth: 1)
            )
        }
        .buttonStyle(PlainButtonStyle())
    }

    private var bildPlaceholder: some View {
        RoundedRectangle(cornerRadius: 10)
            .fill(Color.white.opacity(0.08))
            .frame(width: 56, height: 56)
            .overlay(
                Image(systemName: "basket")
                    .font(.system(size: 20))
                    .foregroundColor(.white.opacity(0.2))
            )
    }
}


// MARK: - Snabbknapp
struct SnabbSökKnapp: View {
    let ikon: String
    let text: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                ZStack {
                    Circle()
                        .fill(icaRöd.opacity(0.15))
                        .frame(width: 48, height: 48)
                    Image(systemName: ikon)
                        .font(.system(size: 18))
                        .foregroundColor(icaRöd)
                }
                Text(text)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundColor(.white.opacity(0.7))
            }
            .frame(width: 72)
        }
    }
}

// MARK: - URLSession för sökning
private let sökSession: URLSession = {
    let config = URLSessionConfiguration.default
    config.httpMaximumConnectionsPerHost = 4
    config.timeoutIntervalForRequest = 10
    config.requestCachePolicy = .reloadIgnoringLocalCacheData
    return URLSession(configuration: config)
}()

// MARK: - SökView
struct SökView: View {
    @State private var sökText = ""
    @State private var produkter: [SökProdukt] = []
    @State private var isLoading = false
    @State private var harSökt = false
    @State private var valdProdukt: SökProdukt? = nil
    @State private var felmeddelande: String? = nil
    @State private var sökTask: Task<Void, Never>? = nil
    @State private var sökKälla: String = ""
    @FocusState private var sökFältFokus: Bool


    @StateObject private var sökmotor = LokalSökmotor.shared

    let serverURL: String = PulsArConfig.serverURL

    let snabbSökningar: [(ikon: String, text: String)] = [
        ("cup.and.saucer.fill", "Kaffe"),
        ("🥛".isEmpty ? "drop.fill" : "drop.fill", "Mjölk"),
        ("leaf.fill", "Frukt"),
        ("fork.knife", "Kött"),
        ("fish.fill", "Fisk"),
        ("birthday.cake", "Bröd"),
        ("takeoutbag.and.cup.and.straw", "Dryck"),
        ("carrot.fill", "Grönt"),
    ]

    var body: some View {
        ZStack {
            // Bakgrund
            Color.black.ignoresSafeArea()

            VStack(spacing: 0) {
                // Sökfält
                sökFält
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                    .padding(.bottom, 12)

                // Snabbval eller sökkälla
                if sökText.isEmpty && !harSökt {
                    snabbValRutnät
                        .padding(.bottom, 8)
                } else if !sökKälla.isEmpty && harSökt {
                    sökKällaIndikator
                }

                Divider()
                    .background(Color.white.opacity(0.1))

                // Resultat
                resultatVy
            }
        }
        .navigationTitle("Sök")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .fullScreenCover(item: $valdProdukt) { produkt in
            ARNavigationView(produkt: produkt)
        }
        .task {
            await sökmotor.laddaProdukter(serverURL: serverURL)
        }.onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                sökFältFokus = true
            }
        }
    }

    // MARK: - Sökfält
    private var sökFält: some View {
        HStack(spacing: 10) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(.white.opacity(0.4))

            TextField("Vad letar du efter?", text: $sökText)
                .focused($sökFältFokus)
                .font(.system(size: 16, design: .rounded))
                .foregroundColor(.white)
                .autocapitalization(.none)
                .disableAutocorrection(true)
                .onChange(of: sökText) { _,nyText in
                    hanteraSökning(nyText)
                }

            if isLoading {
                ProgressView()
                    .scaleEffect(0.7)
                    .tint(icaRöd)
            }

            if !sökText.isEmpty {
                Button(action: rensaSökning) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 16))
                        .foregroundColor(.white.opacity(0.3))
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color.white.opacity(0.08))
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }

    // MARK: - Snabbval rutnät
    private var snabbValRutnät: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Populärt")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundColor(.white.opacity(0.4))
                .textCase(.uppercase)
                .tracking(1)
                .padding(.horizontal, 20)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(snabbSökningar, id: \.text) { item in
                        SnabbSökKnapp(ikon: item.ikon, text: item.text) {
                            sökText = item.text
                        }
                    }
                }
                .padding(.horizontal, 16)
            }
        }
    }

    // MARK: - Sökkälla indikator
    private var sökKällaIndikator: some View {
        HStack(spacing: 6) {
            Image(systemName: sökKälla == "claude" ? "sparkles" : "bolt.fill")
                .font(.system(size: 10))
                .foregroundColor(sökKälla == "claude" ? .purple : .green)
            Text(sökKälla == "claude" ? "Smart sökning" : "Snabbsökning")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.white.opacity(0.35))

            if !produkter.isEmpty {
                Text("·")
                    .foregroundColor(.white.opacity(0.2))
                Text("\(produkter.count) resultat")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.25))
            }
            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 6)
        .animation(.easeInOut(duration: 0.2), value: sökKälla)
    }

    // MARK: - Resultatvy
    @ViewBuilder
    private var resultatVy: some View {
        if let fel = felmeddelande {
            Spacer()
            VStack(spacing: 14) {
                Image(systemName: "wifi.exclamationmark")
                    .font(.system(size: 40))
                    .foregroundColor(icaRöd.opacity(0.7))
                Text(fel)
                    .font(.system(size: 14, design: .rounded))
                    .foregroundColor(.white.opacity(0.5))
                    .multilineTextAlignment(.center)
            }
            .padding()
            Spacer()
        } else if produkter.isEmpty && harSökt && !isLoading {
            Spacer()
            VStack(spacing: 14) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 40))
                    .foregroundColor(.white.opacity(0.15))
                Text("Inga produkter hittades")
                    .font(.system(size: 15, weight: .medium, design: .rounded))
                    .foregroundColor(.white.opacity(0.35))
            }
            Spacer()
        } else if produkter.isEmpty && !harSökt {
            Spacer()
            VStack(spacing: 14) {
                Image(systemName: "basket")
                    .font(.system(size: 44))
                    .foregroundColor(.white.opacity(0.1))
                Text("Sök efter en produkt")
                    .font(.system(size: 15, weight: .medium, design: .rounded))
                    .foregroundColor(.white.opacity(0.25))
            }
            Spacer()
        } else {
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(produkter) { produkt in
                        ProduktKort(produkt: produkt) {
                            valdProdukt = produkt
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 20)
            }
            .animation(.easeInOut(duration: 0.15), value: produkter)
        }
    }

    // MARK: - Söklogik
    func hanteraSökning(_ text: String) {
        sökTask?.cancel()
        felmeddelande = nil

        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)

        guard trimmed.count >= 2 else {
            withAnimation(.easeInOut(duration: 0.15)) {
                produkter = []; harSökt = false; sökKälla = ""
            }
            return
        }

        sökTask = Task { @MainActor in
            harSökt = true

            // 100ms debounce
            try? await Task.sleep(nanoseconds: 100_000_000)
            guard !Task.isCancelled else { return }

            // Lokal sökning
            let q = trimmed
            let lokala = await Task.detached(priority: .userInitiated) {
                self.sökmotor.sök(query: q)
            }.value

            guard !Task.isCancelled else { return }

            withAnimation(.easeInOut(duration: 0.15)) {
                produkter = lokala; sökKälla = "lokal"
            }

            // Claude efter 300ms
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            await claudeSök(query: q)
        }
    }

    func rensaSökning() {
        sökText = ""
        sökTask?.cancel()
        withAnimation(.easeInOut(duration: 0.15)) {
            produkter = []; harSökt = false; sökKälla = ""; felmeddelande = nil
        }
    }

    func claudeSök(query: String) async {
        guard !query.isEmpty else { return }
        await MainActor.run { isLoading = true }
        guard let enc = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(serverURL)/sok?q=\(enc)") else { return }
        do {
            let (data, _) = try await sökSession.data(from: url)
            guard !Task.isCancelled else { return }
            let svar = try JSONDecoder().decode(SökSvar.self, from: data)
            await MainActor.run {
                if !svar.produkter.isEmpty {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        produkter = svar.produkter
                        sökKälla = "claude"
                    }
                }
                isLoading = false
            }
        } catch {
            let nsError = error as NSError
            if nsError.code == -999 || Task.isCancelled { return }
            await MainActor.run { isLoading = false }
        }
    }
}

struct SökView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationView { SökView() }
            .preferredColorScheme(.dark)
    }
}
