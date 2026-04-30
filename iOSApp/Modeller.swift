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

struct Punkt3D: Codable {
    let x: Float          // Världskoordinat X
    let y: Float          // Världskoordinat Y (höjd)
    let z: Float          // Världskoordinat Z
    let u: Float          // Pixel-koordinat i bilden
    let v: Float          // Pixel-koordinat i bilden
    let frame: Int        // Vilken frame punkten kommer från
    let confidence: Float // LiDAR-konfidens
}
