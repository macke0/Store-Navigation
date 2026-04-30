//
//  LokalProdukt.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-04-11.
//


import Foundation
import Combine

// MARK: - Lokal produkt för sökning
struct LokalProdukt: Codable, Identifiable {
    let id: String
    let n: String   // visningsnamn
    let v: String   // varumärke
    let k: String   // kategori
    let b: String?  // bild-URL
}

struct ProduktListaSvar: Codable {
    let antal: Int
    let produkter: [LokalProdukt]
}

// MARK: - Lokal sökmotor
/// Söker bland produkter lokalt på telefonen — instant resultat, noll nätverksanrop.
/// Samma logik som _filtrera_kandidater i claude_sok.py
final class LokalSökmotor: ObservableObject {
    static let shared = LokalSökmotor()
    
    @Published var laddad = false
    @Published var antalProdukter = 0
    
    nonisolated(unsafe) private var produkter: [LokalProdukt] = []
    
    // Ord som måste matcha som HELA ord (inte substring)
    private let helaOrdMatch: Set<String> = ["ägg", "ost", "te", "ris", "öl", "vin", "rom", "sås"]
    
    // Nyckelord som kräver Claude
    private let claudeNyckelord = [
        "som fungerar som", "istället för", "alternativ", "ersätt",
        "liknande", "substitut", "billigare", "nyttigare", "hälsosammare",
        "glutenfri", "glutenfritt", "laktosfri", "laktosfritt",
        "vegansk", "veganskt", "vegetarisk", "sockerfri", "sockerfritt",
        "till", "recept", "ingrediens", "laga", "göra", "baka",
        "behöver", "vad kan", "finns det", "något som", "kan jag",
        "passar till", "fredagsmys", "frukost", "middag", "lunch"
    ]
    
    // MARK: - Ladda produkter från server
    
    func laddaProdukter(serverURL: String) async {
        // Kolla om vi redan har laddat
        guard !laddad else { return }
        
        // Försök ladda från lokal cache först
        if let cachade = laddaFrånDisk() {
            await MainActor.run {
                self.produkter = cachade
                self.antalProdukter = cachade.count
                self.laddad = true
            }
            print("📦 Laddade \(cachade.count) produkter från cache")
            return
        }
        
        // Ladda från server
        guard let url = URL(string: "\(serverURL)/produkter/lista") else { return }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let svar = try JSONDecoder().decode(ProduktListaSvar.self, from: data)
            
            // Spara till disk
            sparaTillDisk(data: data)
            
            await MainActor.run {
                self.produkter = svar.produkter
                self.antalProdukter = svar.produkter.count
                self.laddad = true
            }
            print("📦 Laddade \(svar.produkter.count) produkter från server")
        } catch {
            print("⚠️ Kunde inte ladda produktlista: \(error)")
        }
    }
    
    // MARK: - Lokal sökning
    
    nonisolated func sök(query: String, limit: Int = 20) -> [SökProdukt] {
        let q = query.lowercased().trimmingCharacters(in: .whitespaces)
        guard q.count >= 2 else { return [] }
        
        let sökord = q.split(separator: " ").map(String.init).filter { $0.count >= 2 }
        guard !sökord.isEmpty else { return [] }
        
        // Poängsätt alla produkter
        var resultat: [(score: Int, produkt: LokalProdukt)] = []
        
        for produkt in produkter {
            let namn = produkt.n.lowercased()
            let varumärke = produkt.v.lowercased()
            let kategori = produkt.k.lowercased()
            let sökText = "\(namn) \(varumärke) \(kategori)"
            let namnOrd = namn.split(separator: " ").map(String.init)
            let allaOrd = sökText.split(separator: " ").map(String.init)
            
            var score = 0
            
            for sökord in sökord {
                let kräverHelMatch = helaOrdMatch.contains(sökord) || sökord.count <= 3
                
                // Exakt ordmatchning i namn
                if namnOrd.contains(sökord) {
                    score += 20
                }
                // Exakt ordmatchning i varumärke/kategori
                else if allaOrd.contains(sökord) {
                    score += 12
                }
                // Prefix-matchning (mjö → mjölk, mjöl)
                else if !kräverHelMatch && allaOrd.contains(where: { $0.hasPrefix(sökord) }) {
                    score += 15
                }
                // Innehåller (inte för korta ord)
                else if !kräverHelMatch && sökText.contains(sökord) {
                    // Kolla att det inte är "fri"-suffix (laktosfri osv)
                    if !sökText.contains("\(sökord)fri") {
                        score += 5
                    }
                }
            }
            
            // Bonus om ALLA sökord matchade
            if sökord.count > 1 && score > 0 {
                let allaHittade = sökord.allSatisfy { ord in
                    let kräverHel = helaOrdMatch.contains(ord) || ord.count <= 3
                    if kräverHel {
                        return allaOrd.contains(ord)
                    } else {
                        return sökText.contains(ord)
                    }
                }
                if allaHittade {
                    score += 10
                }
            }
            
            if score > 0 {
                resultat.append((score, produkt))
            }
        }
        
        // Sortera och returnera
        resultat.sort { $0.score > $1.score }
        
        return resultat.prefix(limit).map { item in
            SökProdukt(
                id: item.produkt.id,
                visningsnamn: item.produkt.n,
                varumarke: item.produkt.v,
                kategori: item.produkt.k,
                bild_url: item.produkt.b,
                gång: nil,
                x: nil,
                y: nil,
                z: nil,
                status: nil
            )
        }
    }
    
    // MARK: - Behöver Claude?
    
    func behöverClaude(query: String) -> Bool {
        let q = query.lowercased()
        return claudeNyckelord.contains { q.contains($0) }
    }
    
    // MARK: - Disk-cache
    
    private var cacheURL: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("produkter.json")
    }
    
    private func sparaTillDisk(data: Data) {
        try? data.write(to: cacheURL)
    }
    
    private func laddaFrånDisk() -> [LokalProdukt]? {
        guard let data = try? Data(contentsOf: cacheURL) else { return nil }
        
        // Kolla ålder — uppdatera om äldre än 24h
        if let attr = try? FileManager.default.attributesOfItem(atPath: cacheURL.path),
           let modified = attr[.modificationDate] as? Date,
           Date().timeIntervalSince(modified) > 86400 {
            return nil  // För gammal
        }
        
        guard let svar = try? JSONDecoder().decode(ProduktListaSvar.self, from: data) else {
            return nil
        }
        return svar.produkter
    }
}
