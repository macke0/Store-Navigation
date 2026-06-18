//
//  MeshExporter.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-05-03.
//


//
//  MeshExporter.swift
//  PulsAr / ICA_ai
//
//  Exporterar samtliga ARMeshAnchors i en ARSession som en enda .glb-fil
//  (binary glTF 2.0). Resultatet kan visas direkt i Three.js, SceneKit,
//  RealityKit eller på 3dviewer.net — och innehåller riktig LiDAR-mesh
//  (golv, möbler, väggar, allt som ARKit triangulerade), inte bara
//  RoomPlan-väggarnas parametriska modell.
//

import ARKit
import Foundation
import simd

enum MeshExporter {

    /// Exportera alla ARMeshAnchors i en ARSession som en glb.
    /// Sparas till `mappURL/mesh.glb` (skriver över ev. tidigare fil).
    /// Returnerar URL till den skrivna filen och total storlek i MB.
    @discardableResult
    static func exportSessionsMesh(
        session: ARSession?,
        till mappURL: URL
    ) throws -> (URL, Float) {
        let anchors = (session?.currentFrame?.anchors ?? [])
            .compactMap { $0 as? ARMeshAnchor }

        guard !anchors.isEmpty else {
            throw NSError(
                domain: "MeshExporter",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey:
                    "Inga ARMeshAnchors i sessionen — har LiDAR + sceneReconstruction = .mesh aktiverats?"]
            )
        }

        let utURL = mappURL.appendingPathComponent("mesh.glb")
        let glb = try byggGLB(från: anchors)
        try glb.write(to: utURL, options: .atomic)

        let storlek = Float(glb.count) / (1024 * 1024)
        print("✅ MeshExporter: \(anchors.count) anchors → \(utURL.lastPathComponent) (\(String(format: "%.2f", storlek)) MB)")
        return (utURL, storlek)
    }

    // MARK: - Private

    /// Bygger en valid binary glTF 2.0-blob från en uppsättning mesh-anchors.
    /// Alla anchors slås ihop till en enda mesh i världs-koordinater.
    private static func byggGLB(från anchors: [ARMeshAnchor]) throws -> Data {

        var positions: [SIMD3<Float>] = []
        var normaler:  [SIMD3<Float>] = []
        var index:     [UInt32]       = []

        var minPos = SIMD3<Float>(repeating:  Float.greatestFiniteMagnitude)
        var maxPos = SIMD3<Float>(repeating: -Float.greatestFiniteMagnitude)
        var indexOffset: UInt32 = 0

        for anchor in anchors {
            let geom = anchor.geometry
            let xform = anchor.transform

            // 3x3-rotation för normaler (ingen translation)
            let R = float3x3(
                SIMD3<Float>(xform.columns.0.x, xform.columns.0.y, xform.columns.0.z),
                SIMD3<Float>(xform.columns.1.x, xform.columns.1.y, xform.columns.1.z),
                SIMD3<Float>(xform.columns.2.x, xform.columns.2.y, xform.columns.2.z)
            )

            // ── Vertices (respektera stride!) ──
            let vSrc = geom.vertices
            let vBase = vSrc.buffer.contents().advanced(by: vSrc.offset)
            let antalV = vSrc.count

            // ── Normaler ──
            let nSrc = geom.normals
            let nBase = nSrc.buffer.contents().advanced(by: nSrc.offset)
            let antalN = nSrc.count

            // ARMeshGeometry: vertices.format == .float3, stride kan vara 12 eller 16
            for i in 0..<antalV {
                let p = vBase
                    .advanced(by: i * vSrc.stride)
                    .assumingMemoryBound(to: SIMD3<Float>.self)
                    .pointee
                let h = xform * SIMD4<Float>(p.x, p.y, p.z, 1)
                let world = SIMD3<Float>(h.x, h.y, h.z)
                positions.append(world)
                minPos = simd_min(minPos, world)
                maxPos = simd_max(maxPos, world)
            }

            for i in 0..<antalN {
                let n = nBase
                    .advanced(by: i * nSrc.stride)
                    .assumingMemoryBound(to: SIMD3<Float>.self)
                    .pointee
                var nw = R * n
                let len = simd_length(nw)
                if len > 1e-6 { nw /= len }
                normaler.append(nw)
            }

            // ── Faces (UInt32-trippel typiskt på ARKit) ──
            let fSrc = geom.faces
            let bytesPerIndex = fSrc.bytesPerIndex
            let primCount = fSrc.count          // antal trianglar
            let perPrim = fSrc.indexCountPerPrimitive
            let totalIndex = primCount * perPrim
            let fBase = fSrc.buffer.contents()

            for i in 0..<totalIndex {
                let raw: UInt32
                switch bytesPerIndex {
                case 4:
                    raw = fBase
                        .advanced(by: i * 4)
                        .assumingMemoryBound(to: UInt32.self)
                        .pointee
                case 2:
                    let v = fBase
                        .advanced(by: i * 2)
                        .assumingMemoryBound(to: UInt16.self)
                        .pointee
                    raw = UInt32(v)
                default:
                    throw NSError(domain: "MeshExporter", code: 2,
                                  userInfo: [NSLocalizedDescriptionKey:
                                    "Oväntad bytesPerIndex=\(bytesPerIndex)"])
                }
                index.append(raw + indexOffset)
            }

            indexOffset += UInt32(antalV)
        }

        // ── Bygg binär buffert: positions | normals | indices, 4-byte alignment ──
        var bin = Data()
        bin.reserveCapacity(positions.count * 12 + normaler.count * 12 + index.count * 4 + 32)

        // VIKTIGT: SIMD3<Float> i Swift har stride=16 (4 bytes padding för alignment).
        // glTF kräver packed VEC3 = exakt 12 bytes/element. Skriv x,y,z explicit.

        let posOffset = bin.count
        for p in positions {
            var x = p.x, y = p.y, z = p.z
            withUnsafeBytes(of: &x) { bin.append(contentsOf: $0) }
            withUnsafeBytes(of: &y) { bin.append(contentsOf: $0) }
            withUnsafeBytes(of: &z) { bin.append(contentsOf: $0) }
        }
        align(&bin, to: 4, fill: 0)

        let normOffset = bin.count
        for n in normaler {
            var x = n.x, y = n.y, z = n.z
            withUnsafeBytes(of: &x) { bin.append(contentsOf: $0) }
            withUnsafeBytes(of: &y) { bin.append(contentsOf: $0) }
            withUnsafeBytes(of: &z) { bin.append(contentsOf: $0) }
        }
        align(&bin, to: 4, fill: 0)

        let idxOffset = bin.count
        for i in index {
            var v = i.littleEndian
            withUnsafeBytes(of: &v) { bin.append(contentsOf: $0) }
        }
        align(&bin, to: 4, fill: 0)

        // ── Bygg glTF JSON-manifest ──
        let json: [String: Any] = [
            "asset": [
                "version": "2.0",
                "generator": "PulsAr MeshExporter (ARMeshAnchor → glTF 2.0)"
            ],
            "scene": 0,
            "scenes": [["nodes": [0]]],
            "nodes": [["mesh": 0, "name": "PulsArLiDAR"]],
            "meshes": [[
                "name": "ScannedMesh",
                "primitives": [[
                    "attributes": [
                        "POSITION": 0,
                        "NORMAL": 1
                    ],
                    "indices": 2,
                    "material": 0,
                    "mode": 4   // TRIANGLES
                ]]
            ]],
            "materials": [[
                "name": "DefaultMatte",
                "pbrMetallicRoughness": [
                    "baseColorFactor": [0.78, 0.80, 0.82, 1.0],
                    "metallicFactor": 0.05,
                    "roughnessFactor": 0.85
                ],
                "doubleSided": true
            ]],
            "buffers": [["byteLength": bin.count]],
            "bufferViews": [
                ["buffer": 0, "byteOffset": posOffset,  "byteLength": positions.count * 12, "target": 34962],
                ["buffer": 0, "byteOffset": normOffset, "byteLength": normaler.count  * 12, "target": 34962],
                ["buffer": 0, "byteOffset": idxOffset,  "byteLength": index.count     * 4,  "target": 34963]
            ],
            "accessors": [
                [
                    "bufferView": 0, "componentType": 5126, "count": positions.count, "type": "VEC3",
                    "min": [minPos.x, minPos.y, minPos.z],
                    "max": [maxPos.x, maxPos.y, maxPos.z]
                ],
                [
                    "bufferView": 1, "componentType": 5126, "count": normaler.count, "type": "VEC3"
                ],
                [
                    "bufferView": 2, "componentType": 5125, "count": index.count, "type": "SCALAR"
                ]
            ]
        ]

        let jsonData = try JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])
        var jsonChunk = jsonData
        // Padda JSON-chunk med space (0x20) till multipel av 4
        while jsonChunk.count % 4 != 0 { jsonChunk.append(0x20) }

        // Padda BIN-chunk med 0x00 (redan gjort ovan, men säkra)
        var binChunk = bin
        while binChunk.count % 4 != 0 { binChunk.append(0x00) }

        // ── Bygg glb-fil ──
        let totalLength = 12                          // header
                        + 8 + jsonChunk.count         // JSON chunk (header + body)
                        + 8 + binChunk.count          // BIN chunk

        var ut = Data()
        ut.reserveCapacity(totalLength)

        // 12-byte file header
        appendLE(&ut, UInt32(0x46546C67))             // 'glTF'
        appendLE(&ut, UInt32(2))                      // version
        appendLE(&ut, UInt32(totalLength))            // total length

        // JSON chunk
        appendLE(&ut, UInt32(jsonChunk.count))
        appendLE(&ut, UInt32(0x4E4F534A))             // 'JSON'
        ut.append(jsonChunk)

        // BIN chunk
        appendLE(&ut, UInt32(binChunk.count))
        appendLE(&ut, UInt32(0x004E4942))             // 'BIN\0'
        ut.append(binChunk)

        return ut
    }

    private static func align(_ data: inout Data, to multiple: Int, fill: UInt8) {
        while data.count % multiple != 0 {
            data.append(fill)
        }
    }

    private static func appendLE(_ data: inout Data, _ value: UInt32) {
        var v = value.littleEndian
        withUnsafeBytes(of: &v) { data.append(contentsOf: $0) }
    }
}
