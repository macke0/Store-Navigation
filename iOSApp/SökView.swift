import Foundation

// Delade produktmodeller. Sök-UI:t flyttades in i KundAssistentView; här
// återstår bara de modeller som delas av ARNavigationView, KundAssistentView,
// MaträttView och LokalProdukt.

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
