import SwiftUI
import Combine

// Alias för bakåtkompatibilitet
typealias ProduktResultat = SökProdukt

// MARK: - Sökcache (in-memory, lever under app-sessionen)
/// Sparar sökresultat så att man kan navigera till produkter
/// även om nätverket tappas efter första sökningen.
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

// MARK: - Produktmodell med bild
struct SökProdukt: Codable, Identifiable {
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

// MARK: - Produktrad med bild
struct ProduktRad: View {
    let produkt: SökProdukt
    let onNavigera: () -> Void
    
    var body: some View {
        HStack(spacing: 12) {
            // Produktbild
            if let bildUrl = produkt.bild_url, let url = URL(string: bildUrl) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .empty:
                        ProgressView()
                            .frame(width: 60, height: 60)
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(width: 60, height: 60)
                            .cornerRadius(8)
                    case .failure:
                        Image(systemName: "photo")
                            .frame(width: 60, height: 60)
                            .foregroundColor(.gray)
                    @unknown default:
                        EmptyView()
                    }
                }
            } else {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.gray.opacity(0.2))
                    .frame(width: 60, height: 60)
                    .overlay(
                        Image(systemName: "photo")
                            .foregroundColor(.gray)
                    )
            }
            
            // Produktinfo
            VStack(alignment: .leading, spacing: 4) {
                Text(produkt.visningsnamn)
                    .font(.headline)
                    .lineLimit(2)
                
                Text(produkt.varumarke)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                if let gång = produkt.gång {
                    HStack(spacing: 4) {
                        Image(systemName: "mappin.circle.fill")
                            .foregroundColor(.blue)
                        Text("Gång \(gång)")
                            .font(.caption)
                            .foregroundColor(.blue)
                    }
                }
            }
            
            Spacer()
            
            // Navigera-knapp
            Button(action: onNavigera) {
                VStack(spacing: 4) {
                    Image(systemName: "arrow.triangle.turn.up.right.circle.fill")
                        .font(.title2)
                        .foregroundColor(.blue)
                    Text("Hitta")
                        .font(.caption2)
                        .foregroundColor(.blue)
                }
            }
        }
        .padding(.vertical, 8)
    }
}

// MARK: - SökView
struct SökView: View {
    @State private var sökText = ""
    @State private var produkter: [SökProdukt] = []
    @State private var isLoading = false
    @State private var harSökt = false
    @State private var valdProdukt: SökProdukt? = nil
    @State private var visaARNavigation = false
    @State private var felmeddelande: String? = nil
    
    let serverURL: String = PulsArConfig.serverURL
    
    let snabbSökningar = ["Mjölk", "Bröd", "Ägg", "Ost", "Kaffe", "Frukt"]
    
    var body: some View {
        VStack(spacing: 0) {
            // Sökfält
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.gray)
                
                TextField("Sök produkt...", text: $sökText)
                    .textFieldStyle(PlainTextFieldStyle())
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
                    .onSubmit {
                        Task { await sök() }
                    }
                
                if !sökText.isEmpty {
                    Button(action: {
                        sökText = ""
                        produkter = []
                        harSökt = false
                    }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.gray)
                    }
                }
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(12)
            .padding()
            
            // Snabbknappar
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(snabbSökningar, id: \.self) { term in
                        Button(action: {
                            sökText = term
                            Task { await sök() }
                        }) {
                            Text(term)
                                .font(.subheadline)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(Color.blue.opacity(0.1))
                                .foregroundColor(.blue)
                                .cornerRadius(20)
                        }
                    }
                }
                .padding(.horizontal)
            }
            .padding(.bottom, 8)
            
            Divider()
            
            // Resultat
            if isLoading {
                Spacer()
                VStack(spacing: 12) {
                    ProgressView()
                        .scaleEffect(1.2)
                    Text("Söker produkter...")
                        .foregroundColor(.gray)
                }
                Spacer()
            } else if let fel = felmeddelande {
                Spacer()
                VStack(spacing: 12) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.system(size: 50))
                        .foregroundColor(.red)
                    Text(fel)
                        .foregroundColor(.red)
                        .multilineTextAlignment(.center)
                    Button("Försök igen") {
                        felmeddelande = nil
                        Task { await sök() }
                    }
                    .buttonStyle(.bordered)
                }
                .padding()
                Spacer()
            } else if produkter.isEmpty && harSökt {
                Spacer()
                VStack(spacing: 12) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 50))
                        .foregroundColor(.gray)
                    Text("Inga produkter hittades")
                        .foregroundColor(.gray)
                }
                Spacer()
            } else if produkter.isEmpty {
                Spacer()
                VStack(spacing: 12) {
                    Image(systemName: "cart")
                        .font(.system(size: 50))
                        .foregroundColor(.gray)
                    Text("Sök efter en produkt")
                        .foregroundColor(.gray)
                }
                Spacer()
            } else {
                // Produktlista
                List(produkter) { produkt in
                    ProduktRad(produkt: produkt) {
                        valdProdukt = produkt
                        visaARNavigation = true
                    }
                }
                .listStyle(PlainListStyle())
            }
        }
        .navigationTitle("Sök")
        .navigationBarTitleDisplayMode(.inline)
        .fullScreenCover(isPresented: $visaARNavigation) {
            if let produkt = valdProdukt {
                ARNavigationView(produkt: produkt)
            }
        }
    }
    
    // MARK: - Sökfunktion
    func sök() async {
        guard !sökText.isEmpty else { return }
        
        isLoading = true
        harSökt = true
        felmeddelande = nil

        defer { isLoading = false }

        guard let encodedQuery = sökText.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(serverURL)/sok?q=\(encodedQuery)") else {
            return
        }

        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let svar = try JSONDecoder().decode(SökSvar.self, from: data)

            // Spara i cache för offline-åtkomst
            SökCache.shared.spara(query: sökText, produkter: svar.produkter)

            await MainActor.run {
                produkter = svar.produkter
            }
        } catch let error as URLError where error.code == .timedOut {
            await MainActor.run {
                // Försök hämta från cache
                if let cachade = SökCache.shared.hämta(query: sökText) {
                    produkter = cachade
                    felmeddelande = "Visar cachade resultat — servern svarar inte"
                } else {
                    felmeddelande = "Servern svarar inte — kontrollera att backend körs"
                    produkter = []
                }
            }
        } catch let error as URLError where error.code == .cannotConnectToHost || error.code == .notConnectedToInternet {
            await MainActor.run {
                if let cachade = SökCache.shared.hämta(query: sökText) {
                    produkter = cachade
                    felmeddelande = "Offline — visar cachade resultat"
                } else {
                    felmeddelande = "Ingen nätverksanslutning — kontrollera WiFi"
                    produkter = []
                }
            }
        } catch {
            await MainActor.run {
                if let cachade = SökCache.shared.hämta(query: sökText) {
                    produkter = cachade
                    felmeddelande = "Visar cachade resultat"
                } else {
                    felmeddelande = "Sökningen misslyckades: \(error.localizedDescription)"
                    produkter = []
                }
            }
        }
    }
}

// MARK: - Preview
struct SökView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationView {
            SökView()
        }
    }
}
