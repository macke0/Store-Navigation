//
//  Modeller.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-03-31.
//

import SwiftUI

struct Ankarpunkt: Identifiable {
    let id    = UUID()
    let namn:  String
    let ikon:  String
    let x:     Float
    let y:     Float
    let z:     Float

    var färg: Color {
        if namn.lowercased().contains("gång")   { return .blue }
        if namn.lowercased().contains("kassa")  { return .green }
        if namn.lowercased().contains("pelare") { return .orange }
        return .white
    }

    func tillDict() -> [String: Any] {
        ["namn": namn, "ikon": ikon, "x": x, "y": y, "z": z]
    }
}
