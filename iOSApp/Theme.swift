//
//  Theme.swift
//  PulsAr
//
//  Delad ljus ICA-design: varumärkesfärger, ytor och haptik. Samlas här så att
//  alla kundvyer ser likadana ut i stället för att duplicera färgvärden i varje fil.
//

import SwiftUI
import UIKit

enum Tema {
    // ICA-rött (varumärket). Mörkröd används till gradienter/tryck-states.
    static let röd       = Color(red: 0.89, green: 0.12, blue: 0.17)
    static let mörkRöd   = Color(red: 0.72, green: 0.08, blue: 0.12)

    // Ljusa ytor — vänligt och rent, inte den generiska "AI-app-svarta".
    static let bakgrund  = Color(red: 0.96, green: 0.96, blue: 0.97)
    static let kort      = Color.white
    static let kortKant  = Color.black.opacity(0.06)

    // Text mot ljus bakgrund.
    static let text      = Color(red: 0.11, green: 0.11, blue: 0.13)
    static let textSvag  = Color(red: 0.11, green: 0.11, blue: 0.13).opacity(0.55)
    static let textTunn  = Color(red: 0.11, green: 0.11, blue: 0.13).opacity(0.35)

    // Dämpad grön för protein/positiva värden (neon-.green skär mot ljus bakgrund).
    static let grön      = Color(red: 0.18, green: 0.58, blue: 0.30)

    // Mjuk kortskugga som ger djup utan att kännas tung.
    static let skuggFärg = Color.black.opacity(0.08)
}

extension Tema {
    /// Gemensam typografi-skala (SF Rounded för rubriker, system för text) så att
    /// alla vyer använder samma storlekar i stället för spridda magiska tal.
    enum Typ {
        static let display = Font.system(size: 32, weight: .bold,     design: .rounded) // sidhjälte
        static let rubrik  = Font.system(size: 22, weight: .bold,     design: .rounded) // sektion
        static let titel   = Font.system(size: 17, weight: .bold,     design: .rounded) // korttitel
        static let kropp   = Font.system(size: 15, weight: .regular)                    // brödtext
        static let under   = Font.system(size: 13, weight: .regular)                    // undertext
        static let etikett = Font.system(size: 12, weight: .semibold)                   // pill/märke
        static let liten   = Font.system(size: 11, weight: .medium)                     // metadata
    }
}

enum Haptik {
    /// Lätt knapp-tryck — ger känslan av att appen svarar direkt.
    static func tryck() {
        let g = UIImpactFeedbackGenerator(style: .light)
        g.impactOccurred()
    }

    /// Tydligare träff — t.ex. när något lagts i listan.
    static func träff() {
        let g = UIImpactFeedbackGenerator(style: .medium)
        g.impactOccurred()
    }
}

extension View {
    /// Ett vitt kort med mjuk skugga — appens grundyta.
    func kortYta(hörn: CGFloat = 16) -> some View {
        self
            .background(Tema.kort)
            .cornerRadius(hörn)
            .overlay(
                RoundedRectangle(cornerRadius: hörn)
                    .stroke(Tema.kortKant, lineWidth: 1)
            )
            .shadow(color: Tema.skuggFärg, radius: 10, y: 4)
    }

    /// Mörk gradient nedtill på en bild så vit text (magasin-stil) blir läsbar.
    func bildScrim(hörn: CGFloat = 0) -> some View {
        overlay(
            LinearGradient(
                colors: [.clear, .black.opacity(0.15), .black.opacity(0.7)],
                startPoint: .top, endPoint: .bottom
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: hörn))
    }
}
