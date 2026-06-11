//
//  MaträttView.swift
//  PulsAr
//
//  Kund-flöde: bläddra bland maträttsförslag med bilder. Sök fritt
//  ("maträtter med mycket protein som använder era kampanjer just nu").
//  Tryck på en rätt → ingredienser med riktiga priser/kampanjer, total
//  kostnad och besparing, samt knapp för att lägga i inköpslistan.
//
//  Backend: POST /chat/kund/matratter → { matratter: [...] }
//

import SwiftUI
import Combine

// MARK: - Modeller

struct MatrattIngrediens: Codable, Identifiable, Hashable {
    let produkt_id: String?
    let namn_ingrediens: String?
    let mangd: String?
    let visningsnamn: String?
    let pris: String?
    let enhetspris: String?
    let kampanjpris: String?
    let kampanjtext: String?
    let bild_url: String?
    let x: Double?
    let y: Double?
    let z: Double?
    let matchad: Bool

    var id: String { produkt_id ?? namn_ingrediens ?? UUID().uuidString }

    /// Pris som faktiskt gäller (kampanj om satt, annars ordinarie).
    var effektivtPris: Double? {
        MatrattFormat.tal(kampanjpris) ?? MatrattFormat.tal(pris)
    }

    var harKampanj: Bool { MatrattFormat.tal(kampanjpris) != nil }

    var harPosition: Bool { x != nil && z != nil }

    var somSökProdukt: SökProdukt {
        SökProdukt(
            id: produkt_id ?? (namn_ingrediens ?? ""),
            visningsnamn: visningsnamn ?? namn_ingrediens ?? "",
            varumarke: "", kategori: "", bild_url: bild_url,
            gång: nil, x: x, y: y, z: z, status: nil
        )
    }
}

struct Matratt: Codable, Identifiable {
    let namn: String?
    let beskrivning: String?
    let portioner: Int?
    let protein_g_per_portion: Double?
    let bild_url: String?
    let total_pris: Double
    let ordinarie_pris: Double
    let besparing: Double
    let ingredienser: [MatrattIngrediens]

    var id: String { namn ?? UUID().uuidString }
}

private struct MaträttRequest: Codable {
    let meddelande: String
    let karta: String
}

private struct MaträttResponse: Codable {
    let matratter: [Matratt]
}

// MARK: - Formatering

enum MatrattFormat {
    static func tal(_ s: String?) -> Double? {
        guard let s = s, !s.isEmpty else { return nil }
        return Double(s.replacingOccurrences(of: ",", with: "."))
    }

    /// "27.23" → "27,90 kr". Returnerar nil om saknas.
    static func kr(_ värde: Double?) -> String? {
        guard let v = värde else { return nil }
        return String(format: "%.2f", v).replacingOccurrences(of: ".", with: ",") + " kr"
    }

    static func kr(sträng: String?) -> String? { kr(tal(sträng)) }
}

// MARK: - Inköpslista (delad, sparas lokalt)

@MainActor
final class InköpslistaStore: ObservableObject {
    static let shared = InköpslistaStore()
    @Published private(set) var varor: [MatrattIngrediens] = []

    private let nyckel = "pulsar_inkopslista"

    private init() { ladda() }

    var antal: Int { varor.count }

    var totalPris: Double {
        varor.reduce(0) { $0 + ($1.effektivtPris ?? 0) }
    }

    var totalBesparing: Double {
        varor.reduce(0) { delsumma, vara in
            guard let ord = MatrattFormat.tal(vara.pris),
                  let eff = vara.effektivtPris, eff < ord else { return delsumma }
            return delsumma + (ord - eff)
        }
    }

    func innehåller(_ vara: MatrattIngrediens) -> Bool {
        varor.contains { $0.id == vara.id }
    }

    func växla(_ vara: MatrattIngrediens) {
        if let idx = varor.firstIndex(where: { $0.id == vara.id }) {
            varor.remove(at: idx)
        } else {
            varor.append(vara)
        }
        spara()
    }

    func läggTill(_ nya: [MatrattIngrediens]) {
        for v in nya where v.matchad && !innehåller(v) { varor.append(v) }
        spara()
    }

    func ta_bort(_ vara: MatrattIngrediens) {
        varor.removeAll { $0.id == vara.id }
        spara()
    }

    func rensa() { varor.removeAll(); spara() }

    private func spara() {
        if let data = try? JSONEncoder().encode(varor) {
            UserDefaults.standard.set(data, forKey: nyckel)
        }
    }

    private func ladda() {
        guard let data = UserDefaults.standard.data(forKey: nyckel),
              let lista = try? JSONDecoder().decode([MatrattIngrediens].self, from: data)
        else { return }
        varor = lista
    }
}

// MARK: - Service

@MainActor
final class MaträttService: ObservableObject {
    @Published var matratter: [Matratt] = []
    @Published var laddar = false
    @Published var fel: String?

    private let baseURL = PulsArConfig.serverURL

    func sök(_ text: String) async {
        let rensad = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !rensad.isEmpty else { return }
        laddar = true
        fel = nil
        matratter = []

        do {
            guard let url = URL(string: "\(baseURL)/chat/kund/matratter") else {
                throw URLError(.badURL)
            }
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.timeoutInterval = 120
            req.httpBody = try JSONEncoder().encode(
                MaträttRequest(meddelande: rensad, karta: "hela_butiken")
            )
            let (data, svar) = try await URLSession.shared.data(for: req)
            guard let http = svar as? HTTPURLResponse, http.statusCode == 200 else {
                throw URLError(.badServerResponse)
            }
            matratter = try JSONDecoder().decode(MaträttResponse.self, from: data).matratter
            if matratter.isEmpty { fel = "Hittade inga maträtter. Försök formulera om." }
        } catch let e as URLError where e.code == .timedOut {
            fel = "Det tog för lång tid. Försök igen."
        } catch {
            fel = "Något gick fel: \(error.localizedDescription)"
        }
        laddar = false
    }
}

// MARK: - Vy

struct MaträttView: View {
    @StateObject private var service = MaträttService()
    @StateObject private var lista = InköpslistaStore.shared
    @State private var inmatning = ""
    @State private var vald: Matratt?
    @State private var visaLista = false
    @FocusState private var fokus: Bool

    private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)

    private let förslag = [
        "Maträtter med mycket protein som använder era kampanjer",
        "Billig vardagsmiddag för familjen",
        "Vegetariskt med dagens erbjudanden",
    ]

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 0) {
                sökRad
                innehåll
            }
        }
        .navigationTitle("Matinspiration")
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button { visaLista = true } label: {
                    ZStack(alignment: .topTrailing) {
                        Image(systemName: "cart.fill").foregroundColor(.white)
                        if lista.antal > 0 {
                            Text("\(lista.antal)")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(.white)
                                .padding(4)
                                .background(icaRöd)
                                .clipShape(Circle())
                                .offset(x: 10, y: -8)
                        }
                    }
                }
            }
        }
        .sheet(item: $vald) { rätt in
            MaträttDetaljVy(rätt: rätt)
        }
        .sheet(isPresented: $visaLista) {
            InköpslistaVy()
        }
    }

    private var sökRad: some View {
        HStack(spacing: 10) {
            Image(systemName: "fork.knife")
                .foregroundColor(.white.opacity(0.4))
            TextField("Vad är du sugen på?", text: $inmatning)
                .foregroundColor(.white)
                .focused($fokus)
                .submitLabel(.search)
                .onSubmit(sök)
            if service.laddar {
                ProgressView().scaleEffect(0.7).tint(icaRöd)
            }
        }
        .padding(14)
        .background(Color.white.opacity(0.08))
        .cornerRadius(14)
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    @ViewBuilder
    private var innehåll: some View {
        if service.laddar && service.matratter.isEmpty {
            laddarVy
        } else if let fel = service.fel, service.matratter.isEmpty {
            meddelande(ikon: "exclamationmark.bubble", text: fel)
        } else if service.matratter.isEmpty {
            välkomst
        } else {
            ScrollView {
                LazyVStack(spacing: 14) {
                    ForEach(service.matratter) { rätt in
                        MaträttKort(rätt: rätt) { vald = rätt }
                    }
                }
                .padding(16)
            }
        }
    }

    private var laddarVy: some View {
        VStack(spacing: 16) {
            Spacer()
            ProgressView().scaleEffect(1.3).tint(icaRöd)
            Text("Komponerar maträtter med dagens kampanjer…")
                .font(.system(size: 15, weight: .semibold, design: .rounded))
                .foregroundColor(.white.opacity(0.7))
                .multilineTextAlignment(.center)
            Text("Det kan ta upp till en minut.")
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.35))
            Spacer()
        }
        .padding(.horizontal, 40)
    }

    private var välkomst: some View {
        VStack(spacing: 16) {
            Spacer().frame(height: 30)
            Image(systemName: "sparkles")
                .font(.system(size: 42)).foregroundColor(icaRöd)
            Text("Sök på maträtter eller ingredienser")
                .font(.system(size: 16, weight: .semibold, design: .rounded))
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
            VStack(spacing: 8) {
                ForEach(förslag, id: \.self) { f in
                    Button { inmatning = f; sök() } label: {
                        HStack {
                            Image(systemName: "wand.and.stars").foregroundColor(icaRöd)
                            Text(f).foregroundColor(.white)
                                .font(.system(size: 13))
                                .multilineTextAlignment(.leading)
                            Spacer()
                        }
                        .padding()
                        .background(Color.white.opacity(0.06))
                        .cornerRadius(12)
                    }
                }
            }
            .padding(.horizontal, 16)
            Spacer()
        }
    }

    private func meddelande(ikon: String, text: String) -> some View {
        VStack(spacing: 14) {
            Spacer()
            Image(systemName: ikon).font(.system(size: 40)).foregroundColor(.white.opacity(0.2))
            Text(text).foregroundColor(.white.opacity(0.5))
                .multilineTextAlignment(.center).padding(.horizontal, 40)
            Spacer()
        }
    }

    private func sök() {
        fokus = false
        Task { await service.sök(inmatning) }
    }
}

// MARK: - Maträttskort

struct MaträttKort: View {
    let rätt: Matratt
    let onTryck: () -> Void
    private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)

    var body: some View {
        Button(action: onTryck) {
            VStack(alignment: .leading, spacing: 0) {
                bild
                VStack(alignment: .leading, spacing: 8) {
                    Text(rätt.namn ?? "Maträtt")
                        .font(.system(size: 17, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                        .lineLimit(2).multilineTextAlignment(.leading)

                    if let b = rätt.beskrivning {
                        Text(b).font(.system(size: 13))
                            .foregroundColor(.white.opacity(0.55))
                            .lineLimit(2).multilineTextAlignment(.leading)
                    }

                    HStack(spacing: 8) {
                        if let p = rätt.protein_g_per_portion, p > 0 {
                            märke(ikon: "bolt.fill", text: "\(Int(p))g protein", färg: .green)
                        }
                        if let pris = MatrattFormat.kr(rätt.total_pris) {
                            märke(ikon: "tag.fill", text: pris, färg: .white.opacity(0.7))
                        }
                        if rätt.besparing >= 0.5 {
                            märke(ikon: "arrow.down.circle.fill",
                                  text: "spara \(MatrattFormat.kr(rätt.besparing) ?? "")",
                                  färg: icaRöd)
                        }
                    }
                }
                .padding(14)
            }
            .background(Color.white.opacity(0.06))
            .cornerRadius(16)
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(.white.opacity(0.06), lineWidth: 1))
        }
        .buttonStyle(PlainButtonStyle())
    }

    @ViewBuilder
    private var bild: some View {
        if let s = rätt.bild_url, !s.isEmpty, let url = URL(string: s) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let img):
                    img.resizable().aspectRatio(contentMode: .fill)
                default:
                    bildPlaceholder
                }
            }
            .frame(height: 150).frame(maxWidth: .infinity)
            .clipped()
        } else {
            bildPlaceholder.frame(height: 150).frame(maxWidth: .infinity)
        }
    }

    private var bildPlaceholder: some View {
        ZStack {
            LinearGradient(colors: [icaRöd.opacity(0.3), .black],
                           startPoint: .top, endPoint: .bottom)
            Image(systemName: "fork.knife")
                .font(.system(size: 36)).foregroundColor(.white.opacity(0.3))
        }
    }

    private func märke(ikon: String, text: String, färg: Color) -> some View {
        HStack(spacing: 4) {
            Image(systemName: ikon).font(.system(size: 10, weight: .bold))
            Text(text).font(.system(size: 11, weight: .semibold))
        }
        .foregroundColor(färg)
        .padding(.horizontal, 8).padding(.vertical, 5)
        .background(färg.opacity(0.12))
        .cornerRadius(8)
    }
}

// MARK: - Detaljvy

struct MaträttDetaljVy: View {
    let rätt: Matratt
    @StateObject private var lista = InköpslistaStore.shared
    @State private var valdProdukt: SökProdukt?
    @Environment(\.dismiss) private var stäng
    private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)

    var body: some View {
        NavigationView {
            ZStack {
                Color.black.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if let b = rätt.beskrivning {
                            Text(b).font(.system(size: 15))
                                .foregroundColor(.white.opacity(0.7))
                        }

                        HStack(spacing: 10) {
                            if let p = rätt.protein_g_per_portion, p > 0 {
                                statistik("\(Int(p))g", "protein/portion", .green)
                            }
                            if let port = rätt.portioner {
                                statistik("\(port)", "portioner", .white.opacity(0.7))
                            }
                            if rätt.besparing >= 0.5 {
                                statistik(MatrattFormat.kr(rätt.besparing) ?? "", "du sparar", icaRöd)
                            }
                        }

                        Text("Ingredienser")
                            .font(.system(size: 16, weight: .bold, design: .rounded))
                            .foregroundColor(.white)

                        ForEach(rätt.ingredienser) { ing in
                            ingrediensRad(ing)
                        }

                        prisSummering
                        läggTillKnapp
                    }
                    .padding(16)
                }
            }
            .navigationTitle(rätt.namn ?? "Maträtt")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Stäng") { stäng() }.tint(icaRöd)
                }
            }
            .fullScreenCover(item: $valdProdukt) { p in ARNavigationView(produkt: p) }
        }
        .preferredColorScheme(.dark)
    }

    private func statistik(_ stort: String, _ litet: String, _ färg: Color) -> some View {
        VStack(spacing: 2) {
            Text(stort).font(.system(size: 18, weight: .bold, design: .rounded)).foregroundColor(färg)
            Text(litet).font(.system(size: 11)).foregroundColor(.white.opacity(0.5))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(Color.white.opacity(0.05))
        .cornerRadius(12)
    }

    private func ingrediensRad(_ ing: MatrattIngrediens) -> some View {
        HStack(spacing: 12) {
            ingrediensBild(ing)

            VStack(alignment: .leading, spacing: 3) {
                Text(ing.visningsnamn ?? ing.namn_ingrediens ?? "")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white).lineLimit(2)
                if let m = ing.mangd, !m.isEmpty {
                    Text(m).font(.system(size: 12)).foregroundColor(.white.opacity(0.45))
                }
                prisRad(ing)
            }

            Spacer()

            if ing.harPosition {
                Button { valdProdukt = ing.somSökProdukt } label: {
                    Image(systemName: "location.fill")
                        .font(.system(size: 13)).foregroundColor(icaRöd)
                        .padding(8).background(icaRöd.opacity(0.12)).clipShape(Circle())
                }
            }

            if ing.matchad {
                Button { lista.växla(ing) } label: {
                    Image(systemName: lista.innehåller(ing) ? "checkmark.circle.fill" : "plus.circle")
                        .font(.system(size: 22))
                        .foregroundColor(lista.innehåller(ing) ? .green : .white.opacity(0.5))
                }
            }
        }
        .padding(10)
        .background(Color.white.opacity(0.05))
        .cornerRadius(12)
    }

    @ViewBuilder
    private func ingrediensBild(_ ing: MatrattIngrediens) -> some View {
        if let s = ing.bild_url, !s.isEmpty, let url = URL(string: s) {
            AsyncImage(url: url) { phase in
                if case .success(let img) = phase {
                    img.resizable().aspectRatio(contentMode: .fit)
                } else {
                    Color.white.opacity(0.08)
                }
            }
            .frame(width: 44, height: 44).cornerRadius(8)
        } else {
            RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.08))
                .frame(width: 44, height: 44)
                .overlay(Image(systemName: ing.matchad ? "basket" : "questionmark")
                    .font(.system(size: 16)).foregroundColor(.white.opacity(0.25)))
        }
    }

    @ViewBuilder
    private func prisRad(_ ing: MatrattIngrediens) -> some View {
        if !ing.matchad {
            Text("Finns ej i sortimentet")
                .font(.system(size: 11)).foregroundColor(.orange.opacity(0.7))
        } else if ing.harKampanj {
            HStack(spacing: 6) {
                if let ord = MatrattFormat.kr(sträng: ing.pris) {
                    Text(ord).font(.system(size: 12)).strikethrough()
                        .foregroundColor(.white.opacity(0.4))
                }
                if let kp = MatrattFormat.kr(sträng: ing.kampanjpris) {
                    Text(kp).font(.system(size: 13, weight: .bold)).foregroundColor(icaRöd)
                }
                if let t = ing.kampanjtext, !t.isEmpty {
                    Text(t).font(.system(size: 10)).foregroundColor(icaRöd.opacity(0.8))
                }
            }
        } else if let pris = MatrattFormat.kr(sträng: ing.pris) {
            Text(pris).font(.system(size: 13, weight: .semibold)).foregroundColor(.white.opacity(0.7))
        }
    }

    private var prisSummering: some View {
        VStack(spacing: 8) {
            rad("Totalt", MatrattFormat.kr(rätt.total_pris) ?? "–", .white)
            if rätt.besparing >= 0.5 {
                rad("Du sparar med kampanjer", MatrattFormat.kr(rätt.besparing) ?? "", icaRöd)
            }
        }
        .padding(14)
        .background(Color.white.opacity(0.05))
        .cornerRadius(12)
    }

    private func rad(_ vänster: String, _ höger: String, _ färg: Color) -> some View {
        HStack {
            Text(vänster).font(.system(size: 14)).foregroundColor(.white.opacity(0.7))
            Spacer()
            Text(höger).font(.system(size: 15, weight: .bold)).foregroundColor(färg)
        }
    }

    private var läggTillKnapp: some View {
        Button {
            lista.läggTill(rätt.ingredienser)
        } label: {
            HStack {
                Image(systemName: "cart.badge.plus")
                Text("Lägg alla i inköpslista").font(.system(size: 15, weight: .bold, design: .rounded))
            }
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(icaRöd)
            .cornerRadius(14)
        }
    }
}

// MARK: - Inköpslista

struct InköpslistaVy: View {
    @StateObject private var lista = InköpslistaStore.shared
    @State private var valdProdukt: SökProdukt?
    @Environment(\.dismiss) private var stäng
    private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)

    var body: some View {
        NavigationView {
            ZStack {
                Color.black.ignoresSafeArea()
                if lista.varor.isEmpty {
                    VStack(spacing: 14) {
                        Image(systemName: "cart").font(.system(size: 44))
                            .foregroundColor(.white.opacity(0.15))
                        Text("Inköpslistan är tom")
                            .font(.system(size: 15, design: .rounded))
                            .foregroundColor(.white.opacity(0.4))
                    }
                } else {
                    VStack(spacing: 0) {
                        ScrollView {
                            LazyVStack(spacing: 8) {
                                ForEach(lista.varor) { vara in
                                    listaRad(vara)
                                }
                            }
                            .padding(16)
                        }
                        summering
                    }
                }
            }
            .navigationTitle("Inköpslista")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Stäng") { stäng() }.tint(.white.opacity(0.6))
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    if !lista.varor.isEmpty {
                        Button { lista.rensa() } label: { Image(systemName: "trash") }
                            .tint(icaRöd)
                    }
                }
            }
            .fullScreenCover(item: $valdProdukt) { p in ARNavigationView(produkt: p) }
        }
        .preferredColorScheme(.dark)
    }

    private func listaRad(_ vara: MatrattIngrediens) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(vara.visningsnamn ?? vara.namn_ingrediens ?? "")
                    .font(.system(size: 14, weight: .semibold)).foregroundColor(.white)
                    .lineLimit(2)
                if let m = vara.mangd, !m.isEmpty {
                    Text(m).font(.system(size: 11)).foregroundColor(.white.opacity(0.4))
                }
            }
            Spacer()
            if let pris = MatrattFormat.kr(vara.effektivtPris) {
                Text(pris).font(.system(size: 13, weight: .bold))
                    .foregroundColor(vara.harKampanj ? icaRöd : .white.opacity(0.7))
            }
            if vara.harPosition {
                Button { valdProdukt = vara.somSökProdukt } label: {
                    Image(systemName: "location.fill")
                        .font(.system(size: 12)).foregroundColor(icaRöd)
                }
            }
            Button { lista.ta_bort(vara) } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 18)).foregroundColor(.white.opacity(0.25))
            }
        }
        .padding(12)
        .background(Color.white.opacity(0.05))
        .cornerRadius(12)
    }

    private var summering: some View {
        VStack(spacing: 10) {
            HStack {
                Text("Totalt (\(lista.antal) varor)")
                    .font(.system(size: 14)).foregroundColor(.white.opacity(0.7))
                Spacer()
                Text(MatrattFormat.kr(lista.totalPris) ?? "–")
                    .font(.system(size: 18, weight: .bold)).foregroundColor(.white)
            }
            if lista.totalBesparing >= 0.5 {
                HStack {
                    Text("Du sparar med kampanjer")
                        .font(.system(size: 12)).foregroundColor(icaRöd)
                    Spacer()
                    Text(MatrattFormat.kr(lista.totalBesparing) ?? "")
                        .font(.system(size: 14, weight: .bold)).foregroundColor(icaRöd)
                }
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.08))
    }
}

#Preview {
    NavigationView { MaträttView() }.preferredColorScheme(.dark)
}
