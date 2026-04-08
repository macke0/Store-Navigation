import SwiftUI
import Combine

// Alias för bakåtkompatibilitet
typealias ProduktResultat = SökProdukt

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
    
    let serverURL: String
    
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
        
        defer { isLoading = false }
        
        guard let encodedQuery = sökText.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(serverURL)/sok?q=\(encodedQuery)") else {
            return
        }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let svar = try JSONDecoder().decode(SökSvar.self, from: data)
            
            await MainActor.run {
                produkter = svar.produkter
            }
        } catch {
            print("Sökfel: \(error)")
            await MainActor.run {
                produkter = []
            }
        }
    }
}

// MARK: - Preview
struct SökView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationView {
            SökView(serverURL: "http://192.168.0.166:8000")
        }
    }
}
