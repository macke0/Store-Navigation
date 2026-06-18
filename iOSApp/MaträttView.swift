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

    /// Kopia med mängden skalad (id/pris/position oförändrade) — används när
    /// kunden ändrar antal portioner så vi slipper generera nya rätter.
    func skalad(faktor: Double) -> MatrattIngrediens {
        MatrattIngrediens(
            produkt_id: produkt_id, namn_ingrediens: namn_ingrediens,
            mangd: Portionsskala.skala(mangd, faktor: faktor),
            visningsnamn: visningsnamn, pris: pris, enhetspris: enhetspris,
            kampanjpris: kampanjpris, kampanjtext: kampanjtext, bild_url: bild_url,
            x: x, y: y, z: z, matchad: matchad
        )
    }
}

struct Matratt: Codable, Identifiable {
    let namn: String?
    let beskrivning: String?
    let portioner: Int?
    let protein_g_per_portion: Double?
    let kolhydrater_g_per_portion: Double?
    let fett_g_per_portion: Double?
    let kcal_per_portion: Double?
    let bild_url: String?
    let betyg: Double?
    let antal_betyg: Int?
    let total_pris: Double
    let ordinarie_pris: Double
    let besparing: Double
    let ingredienser: [MatrattIngrediens]

    var id: String { namn ?? UUID().uuidString }
}

private struct MaträttRequest: Codable {
    let meddelande: String
    let karta: String
    let portioner: Int
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

// Skalar mängdsträngar ("600 g", "2 dl", "1,5 st") med en faktor så att samma
// rätt kan visas för fler/färre portioner utan att generera om den. Hittar
// första talet, multiplicerar och avrundar snyggt; text utan tal lämnas orörd.
enum Portionsskala {
    static func skala(_ mangd: String?, faktor: Double) -> String? {
        guard let mangd = mangd, !mangd.isEmpty else { return mangd }
        guard abs(faktor - 1) > 0.001 else { return mangd }
        guard let r = mangd.range(of: #"\d+(?:[.,]\d+)?"#, options: .regularExpression)
        else { return mangd }
        let tal = Double(mangd[r].replacingOccurrences(of: ",", with: ".")) ?? 0
        let nytt = tal * faktor
        let txt: String
        if nytt >= 10 {
            txt = String(Int(nytt.rounded()))
        } else {
            let avrundat = (nytt * 10).rounded() / 10
            txt = avrundat == avrundat.rounded()
                ? String(Int(avrundat))
                : String(format: "%.1f", avrundat).replacingOccurrences(of: ".", with: ",")
        }
        return mangd.replacingCharacters(in: r, with: txt)
    }
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

    func sök(_ text: String, portioner: Int) async {
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
                MaträttRequest(meddelande: rensad, karta: "hela_butiken", portioner: portioner)
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
    @State private var portioner = 4
    @State private var vald: Matratt?
    @State private var visaLista = false
    @FocusState private var fokus: Bool

    private let förslag = [
        "Maträtter med mycket protein som använder era kampanjer",
        "Billig vardagsmiddag för familjen",
        "Vegetariskt med dagens erbjudanden",
    ]

    var body: some View {
        ZStack {
            Tema.bakgrund.ignoresSafeArea()
            VStack(spacing: 0) {
                sökRad
                portionsRad
                innehåll
            }
        }
        .navigationTitle("Matinspiration")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    Haptik.tryck()
                    visaLista = true
                } label: {
                    ZStack(alignment: .topTrailing) {
                        Image(systemName: "cart.fill").foregroundColor(Tema.röd)
                        if lista.antal > 0 {
                            Text("\(lista.antal)")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(.white)
                                .padding(4)
                                .background(Tema.röd)
                                .clipShape(Circle())
                                .offset(x: 10, y: -8)
                        }
                    }
                }
            }
        }
        .sheet(item: $vald) { rätt in
            MaträttDetaljVy(rätt: rätt, valdaPortioner: portioner)
        }
        .sheet(isPresented: $visaLista) {
            InköpslistaVy()
        }
    }

    private var sökRad: some View {
        HStack(spacing: 10) {
            Image(systemName: "fork.knife")
                .foregroundColor(Tema.textTunn)
            TextField("Vad är du sugen på?", text: $inmatning)
                .foregroundColor(Tema.text)
                .focused($fokus)
                .submitLabel(.search)
                .onSubmit(sök)
            if service.laddar {
                ProgressView().scaleEffect(0.7).tint(Tema.röd)
            }
        }
        .padding(14)
        .background(Tema.kort)
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Tema.kortKant, lineWidth: 1))
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    // +/- för antal portioner. Ändrar bara MÄNGDERNA i rätterna som redan visas
    // (skalas i detaljvyn) — vi genererar inte nya rätter. Nästa fritextsökning
    // använder valt antal som utgångspunkt.
    private var portionsRad: some View {
        HStack(spacing: 12) {
            Image(systemName: "person.2.fill").foregroundColor(Tema.textTunn)
            Text("Antal portioner").font(.system(size: 14)).foregroundColor(Tema.textSvag)
            Spacer()
            HStack(spacing: 16) {
                stegKnapp(ikon: "minus", aktiv: portioner > 1) {
                    if portioner > 1 { portioner -= 1; Haptik.tryck() }
                }
                Text("\(portioner)")
                    .font(.system(size: 17, weight: .bold, design: .rounded))
                    .foregroundColor(Tema.text)
                    .frame(minWidth: 24)
                stegKnapp(ikon: "plus", aktiv: portioner < 12) {
                    if portioner < 12 { portioner += 1; Haptik.tryck() }
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .kortYta(hörn: 14)
        .padding(.horizontal, 16)
        .padding(.bottom, 4)
    }

    private func stegKnapp(ikon: String, aktiv: Bool, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: ikon)
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(aktiv ? Tema.röd : Tema.textTunn)
                .frame(width: 32, height: 32)
                .background((aktiv ? Tema.röd : Tema.textTunn).opacity(0.12))
                .clipShape(Circle())
        }
        .buttonStyle(TryckStyle())
        .disabled(!aktiv)
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

    // Skeleton-kort i stället för en tom spinner → känns omedelbart och visar
    // vad som är på väg. Tre platshållare i samma form som de riktiga korten.
    private var laddarVy: some View {
        ScrollView {
            VStack(spacing: 14) {
                HStack(spacing: 8) {
                    ProgressView().scaleEffect(0.8).tint(Tema.röd)
                    Text("Komponerar maträtter med dagens kampanjer…")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundColor(Tema.textSvag)
                    Spacer()
                }
                .padding(.top, 4)

                ForEach(0..<3, id: \.self) { _ in SkelettKort() }
            }
            .padding(16)
        }
    }

    private var välkomst: some View {
        VStack(spacing: 16) {
            Spacer().frame(height: 30)
            Image(systemName: "sparkles")
                .font(.system(size: 42)).foregroundColor(Tema.röd)
            Text("Sök på maträtter eller ingredienser")
                .font(Tema.Typ.titel)
                .foregroundColor(Tema.text)
                .multilineTextAlignment(.center)
            VStack(spacing: 8) {
                ForEach(förslag, id: \.self) { f in
                    Button { inmatning = f; sök() } label: {
                        HStack {
                            Image(systemName: "wand.and.stars").foregroundColor(Tema.röd)
                            Text(f).foregroundColor(Tema.text)
                                .font(.system(size: 13))
                                .multilineTextAlignment(.leading)
                            Spacer()
                        }
                        .padding()
                        .kortYta(hörn: 12)
                    }
                    .buttonStyle(TryckStyle())
                }
            }
            .padding(.horizontal, 16)
            Spacer()
        }
    }

    private func meddelande(ikon: String, text: String) -> some View {
        VStack(spacing: 14) {
            Spacer()
            Image(systemName: ikon).font(.system(size: 40)).foregroundColor(Tema.textTunn)
            Text(text).foregroundColor(Tema.textSvag)
                .multilineTextAlignment(.center).padding(.horizontal, 40)
            Spacer()
        }
    }

    private func sök() {
        let text = inmatning.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        Haptik.tryck()
        fokus = false
        Task { await service.sök(inmatning, portioner: portioner) }
    }
}

// MARK: - Skeleton-kort

private struct SkelettKort: View {
    @State private var puls = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Rectangle()
                .fill(Color.black.opacity(0.06))
                .frame(height: 180)
            VStack(alignment: .leading, spacing: 10) {
                stapel(bredd: 0.7, höjd: 16)
                stapel(bredd: 0.9, höjd: 11)
                HStack(spacing: 8) {
                    stapel(bredd: 0.25, höjd: 20)
                    stapel(bredd: 0.25, höjd: 20)
                }
            }
            .padding(14)
        }
        .background(Tema.kort)
        .cornerRadius(18)
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Tema.kortKant, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .opacity(puls ? 0.55 : 1)
        .onAppear {
            withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) {
                puls = true
            }
        }
    }

    private func stapel(bredd: CGFloat, höjd: CGFloat) -> some View {
        GeometryReader { geo in
            RoundedRectangle(cornerRadius: 5)
                .fill(Color.black.opacity(0.08))
                .frame(width: geo.size.width * bredd, height: höjd)
        }
        .frame(height: höjd)
    }
}

// MARK: - Maträttskort

struct MaträttKort: View {
    let rätt: Matratt
    let onTryck: () -> Void

    var body: some View {
        Button(action: onTryck) {
            VStack(alignment: .leading, spacing: 0) {
                // Magasin-stil: titeln ligger OVANPÅ den riktiga bilden via en mörk
                // scrim, betyget som pill uppe till höger.
                ZStack(alignment: .bottomLeading) {
                    bild
                    Text(rätt.namn ?? "Maträtt")
                        .font(.system(size: 19, weight: .heavy, design: .rounded))
                        .foregroundColor(.white)
                        .lineLimit(2).multilineTextAlignment(.leading)
                        .shadow(color: .black.opacity(0.35), radius: 4, y: 1)
                        .padding(14)
                }
                .frame(height: 180)
                .frame(maxWidth: .infinity)
                .clipped()
                .bildScrim()
                .overlay(alignment: .topTrailing) { betygsPill }

                VStack(alignment: .leading, spacing: 8) {
                    if let b = rätt.beskrivning {
                        Text(b).font(Tema.Typ.under)
                            .foregroundColor(Tema.textSvag)
                            .lineLimit(2).multilineTextAlignment(.leading)
                    }

                    HStack(spacing: 8) {
                        if let k = rätt.kcal_per_portion, k > 0 {
                            märke(ikon: "flame.fill", text: "\(Int(k)) kcal", färg: Tema.grön)
                        } else if let p = rätt.protein_g_per_portion, p > 0 {
                            märke(ikon: "bolt.fill", text: "\(Int(p))g protein", färg: Tema.grön)
                        }
                        if let pris = MatrattFormat.kr(rätt.total_pris) {
                            märke(ikon: "tag.fill", text: pris, färg: Tema.textSvag)
                        }
                        if rätt.besparing >= 0.5 {
                            märke(ikon: "arrow.down.circle.fill",
                                  text: "spara \(MatrattFormat.kr(rätt.besparing) ?? "")",
                                  färg: Tema.röd)
                        }
                    }
                }
                .padding(14)
            }
            .background(Tema.kort)
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).stroke(Tema.kortKant, lineWidth: 1))
            .shadow(color: Tema.skuggFärg, radius: 12, y: 5)
        }
        .buttonStyle(TryckStyle())
    }

    @ViewBuilder
    private var bild: some View {
        if let s = rätt.bild_url, !s.isEmpty, let url = URL(string: s) {
            // Mjuk intoning när bilden laddats (transaction-animation) + lugn
            // platshållare under laddning i stället för en orange gradient-blink.
            AsyncImage(url: url, transaction: Transaction(animation: .easeIn(duration: 0.35))) { phase in
                switch phase {
                case .success(let img):
                    img.resizable().aspectRatio(contentMode: .fill)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                case .empty:
                    laddarBild
                default:
                    bildPlaceholder
                }
            }
        } else {
            bildPlaceholder
        }
    }

    // Lugn, neutral platshållare medan bilden hämtas — känns mindre "blinkig".
    private var laddarBild: some View {
        Color.black.opacity(0.06)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .overlay(ProgressView().tint(Tema.textTunn))
    }

    // Betyg som pill ovanpå bilden (uppe till höger) — visas bara om receptet
    // har ett betyg. Stjärnan i guld, resten vit på halvtransparent platta.
    @ViewBuilder
    private var betygsPill: some View {
        if let b = rätt.betyg, b > 0 {
            HStack(spacing: 3) {
                Image(systemName: "star.fill")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(Color(red: 1.0, green: 0.8, blue: 0.2))
                Text(String(format: "%.1f", b).replacingOccurrences(of: ".", with: ","))
                    .font(.system(size: 11, weight: .bold))
                if let n = rätt.antal_betyg, n > 0 {
                    Text("(\(n))").font(.system(size: 10, weight: .medium)).opacity(0.85)
                }
            }
            .foregroundColor(.white)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(.black.opacity(0.55))
            .clipShape(Capsule())
            .padding(10)
        }
    }

    private var bildPlaceholder: some View {
        ZStack {
            LinearGradient(
                colors: [Color(red: 0.97, green: 0.5, blue: 0.35), Tema.röd],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
            Image(systemName: "fork.knife")
                .font(.system(size: 36)).foregroundColor(.white.opacity(0.7))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
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
    let valdaPortioner: Int
    @StateObject private var lista = InköpslistaStore.shared
    @State private var valdProdukt: SökProdukt?
    @Environment(\.dismiss) private var stäng

    // Skalfaktor från rättens egna basportioner till kundens valda antal.
    private var faktor: Double {
        Double(valdaPortioner) / Double(max(rätt.portioner ?? valdaPortioner, 1))
    }

    // Ingredienserna med mängder skalade till valt portionsantal.
    private var skaladeIngredienser: [MatrattIngrediens] {
        rätt.ingredienser.map { $0.skalad(faktor: faktor) }
    }

    var body: some View {
        NavigationView {
            ZStack {
                Tema.bakgrund.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if let b = rätt.beskrivning {
                            Text(b).font(.system(size: 15))
                                .foregroundColor(Tema.textSvag)
                        }

                        HStack(spacing: 10) {
                            statistik("\(valdaPortioner)", "portioner", Tema.textSvag)
                            if let b = rätt.betyg, b > 0 {
                                statistik(String(format: "%.1f", b).replacingOccurrences(of: ".", with: ","),
                                          "betyg", Color(red: 0.95, green: 0.62, blue: 0.18))
                            }
                            if let k = rätt.kcal_per_portion, k > 0 {
                                statistik("\(Int(k))", "kcal/portion", Tema.text)
                            }
                            if rätt.besparing >= 0.5 {
                                statistik(MatrattFormat.kr(rätt.besparing) ?? "", "du sparar", Tema.röd)
                            }
                        }

                        näringsavsnitt

                        Text("Ingredienser")
                            .font(Tema.Typ.titel)
                            .foregroundColor(Tema.text)

                        ForEach(skaladeIngredienser) { ing in
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
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Stäng") { stäng() }.tint(Tema.röd)
                }
            }
            .fullScreenCover(item: $valdProdukt) { p in ARNavigationView(produkt: p) }
        }
    }

    private func statistik(_ stort: String, _ litet: String, _ färg: Color) -> some View {
        VStack(spacing: 2) {
            Text(stort).font(.system(size: 18, weight: .bold, design: .rounded)).foregroundColor(färg)
            Text(litet).font(.system(size: 11)).foregroundColor(Tema.textSvag)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .kortYta(hörn: 12)
    }

    // Balanserad näringsöversikt per portion: protein / kolhydrater / fett.
    @ViewBuilder
    private var näringsavsnitt: some View {
        let p = rätt.protein_g_per_portion ?? 0
        let k = rätt.kolhydrater_g_per_portion ?? 0
        let f = rätt.fett_g_per_portion ?? 0
        if p > 0 || k > 0 || f > 0 {
            VStack(alignment: .leading, spacing: 10) {
                Text("Näringsvärde per portion")
                    .font(Tema.Typ.titel)
                    .foregroundColor(Tema.text)
                HStack(spacing: 10) {
                    makro("Protein", p, Tema.grön)
                    makro("Kolhydrater", k, Tema.röd)
                    makro("Fett", f, Color(red: 0.95, green: 0.62, blue: 0.18))
                }
            }
        }
    }

    private func makro(_ namn: String, _ gram: Double, _ färg: Color) -> some View {
        VStack(spacing: 3) {
            Text("\(Int(gram))g")
                .font(.system(size: 18, weight: .bold, design: .rounded)).foregroundColor(färg)
            Text(namn).font(.system(size: 11)).foregroundColor(Tema.textSvag)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(färg.opacity(0.10))
        .cornerRadius(12)
    }

    private func ingrediensRad(_ ing: MatrattIngrediens) -> some View {
        HStack(spacing: 12) {
            ingrediensBild(ing)

            VStack(alignment: .leading, spacing: 3) {
                Text(ing.visningsnamn ?? ing.namn_ingrediens ?? "")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Tema.text).lineLimit(2)
                if let m = ing.mangd, !m.isEmpty {
                    Text(m).font(.system(size: 12)).foregroundColor(Tema.textSvag)
                }
                prisRad(ing)
            }

            Spacer()

            if ing.harPosition {
                Button {
                    Haptik.tryck()
                    valdProdukt = ing.somSökProdukt
                } label: {
                    Image(systemName: "location.fill")
                        .font(.system(size: 13)).foregroundColor(Tema.röd)
                        .padding(8).background(Tema.röd.opacity(0.12)).clipShape(Circle())
                }
            }

            if ing.matchad {
                Button {
                    Haptik.tryck()
                    lista.växla(ing)
                } label: {
                    Image(systemName: lista.innehåller(ing) ? "checkmark.circle.fill" : "plus.circle")
                        .font(.system(size: 22))
                        .foregroundColor(lista.innehåller(ing) ? Tema.grön : Tema.textTunn)
                }
            }
        }
        .padding(10)
        .kortYta(hörn: 12)
    }

    @ViewBuilder
    private func ingrediensBild(_ ing: MatrattIngrediens) -> some View {
        if let s = ing.bild_url, !s.isEmpty, let url = URL(string: s) {
            AsyncImage(url: url) { phase in
                if case .success(let img) = phase {
                    img.resizable().aspectRatio(contentMode: .fit)
                } else {
                    Color.black.opacity(0.05)
                }
            }
            .frame(width: 44, height: 44)
            .background(Color.white)
            .cornerRadius(8)
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Tema.kortKant, lineWidth: 1))
        } else {
            RoundedRectangle(cornerRadius: 8).fill(Color.black.opacity(0.05))
                .frame(width: 44, height: 44)
                .overlay(Image(systemName: ing.matchad ? "basket" : "questionmark")
                    .font(.system(size: 16)).foregroundColor(Tema.textTunn))
        }
    }

    @ViewBuilder
    private func prisRad(_ ing: MatrattIngrediens) -> some View {
        if !ing.matchad {
            Text("Finns ej i sortimentet")
                .font(.system(size: 11)).foregroundColor(.orange)
        } else if ing.harKampanj {
            HStack(spacing: 6) {
                if let ord = MatrattFormat.kr(sträng: ing.pris) {
                    Text(ord).font(.system(size: 12)).strikethrough()
                        .foregroundColor(Tema.textTunn)
                }
                if let kp = MatrattFormat.kr(sträng: ing.kampanjpris) {
                    Text(kp).font(.system(size: 13, weight: .bold)).foregroundColor(Tema.röd)
                }
                if let t = ing.kampanjtext, !t.isEmpty {
                    Text(t).font(.system(size: 10)).foregroundColor(Tema.röd.opacity(0.8))
                }
            }
        } else if let pris = MatrattFormat.kr(sträng: ing.pris) {
            Text(pris).font(.system(size: 13, weight: .semibold)).foregroundColor(Tema.textSvag)
        }
    }

    private var prisSummering: some View {
        VStack(spacing: 8) {
            rad("Totalt", MatrattFormat.kr(rätt.total_pris) ?? "–", Tema.text)
            if rätt.besparing >= 0.5 {
                rad("Du sparar med kampanjer", MatrattFormat.kr(rätt.besparing) ?? "", Tema.röd)
            }
        }
        .padding(14)
        .kortYta(hörn: 12)
    }

    private func rad(_ vänster: String, _ höger: String, _ färg: Color) -> some View {
        HStack {
            Text(vänster).font(.system(size: 14)).foregroundColor(Tema.textSvag)
            Spacer()
            Text(höger).font(.system(size: 15, weight: .bold)).foregroundColor(färg)
        }
    }

    private var läggTillKnapp: some View {
        Button {
            Haptik.träff()
            lista.läggTill(skaladeIngredienser)
        } label: {
            HStack {
                Image(systemName: "cart.badge.plus")
                Text("Lägg alla i inköpslista").font(.system(size: 15, weight: .bold, design: .rounded))
            }
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Tema.röd)
            .cornerRadius(14)
            .shadow(color: Tema.röd.opacity(0.3), radius: 8, y: 3)
        }
        .buttonStyle(TryckStyle())
    }
}

// MARK: - Inköpslista

struct InköpslistaVy: View {
    @StateObject private var lista = InköpslistaStore.shared
    @State private var valdProdukt: SökProdukt?
    @Environment(\.dismiss) private var stäng

    var body: some View {
        NavigationView {
            ZStack {
                Tema.bakgrund.ignoresSafeArea()
                if lista.varor.isEmpty {
                    VStack(spacing: 14) {
                        Image(systemName: "cart").font(.system(size: 44))
                            .foregroundColor(Tema.textTunn)
                        Text("Inköpslistan är tom")
                            .font(.system(size: 15, design: .rounded))
                            .foregroundColor(Tema.textSvag)
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
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Stäng") { stäng() }.tint(Tema.textSvag)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    if !lista.varor.isEmpty {
                        Button {
                            Haptik.tryck()
                            lista.rensa()
                        } label: { Image(systemName: "trash") }
                            .tint(Tema.röd)
                    }
                }
            }
            .fullScreenCover(item: $valdProdukt) { p in ARNavigationView(produkt: p) }
        }
    }

    private func listaRad(_ vara: MatrattIngrediens) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(vara.visningsnamn ?? vara.namn_ingrediens ?? "")
                    .font(.system(size: 14, weight: .semibold)).foregroundColor(Tema.text)
                    .lineLimit(2)
                if let m = vara.mangd, !m.isEmpty {
                    Text(m).font(.system(size: 11)).foregroundColor(Tema.textSvag)
                }
            }
            Spacer()
            if let pris = MatrattFormat.kr(vara.effektivtPris) {
                Text(pris).font(.system(size: 13, weight: .bold))
                    .foregroundColor(vara.harKampanj ? Tema.röd : Tema.textSvag)
            }
            if vara.harPosition {
                Button {
                    Haptik.tryck()
                    valdProdukt = vara.somSökProdukt
                } label: {
                    Image(systemName: "location.fill")
                        .font(.system(size: 12)).foregroundColor(Tema.röd)
                }
            }
            Button {
                Haptik.tryck()
                lista.ta_bort(vara)
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 18)).foregroundColor(Tema.textTunn)
            }
        }
        .padding(12)
        .kortYta(hörn: 12)
    }

    private var summering: some View {
        VStack(spacing: 10) {
            HStack {
                Text("Totalt (\(lista.antal) varor)")
                    .font(.system(size: 14)).foregroundColor(Tema.textSvag)
                Spacer()
                Text(MatrattFormat.kr(lista.totalPris) ?? "–")
                    .font(.system(size: 18, weight: .bold)).foregroundColor(Tema.text)
            }
            if lista.totalBesparing >= 0.5 {
                HStack {
                    Text("Du sparar med kampanjer")
                        .font(.system(size: 12)).foregroundColor(Tema.röd)
                    Spacer()
                    Text(MatrattFormat.kr(lista.totalBesparing) ?? "")
                        .font(.system(size: 14, weight: .bold)).foregroundColor(Tema.röd)
                }
            }
        }
        .padding(16)
        .background(Tema.kort)
        .shadow(color: Tema.skuggFärg, radius: 10, y: -2)
    }
}

#Preview {
    NavigationView { MaträttView() }
}
