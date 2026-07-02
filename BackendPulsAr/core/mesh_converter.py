"""
mesh_converter.py
─────────────────
Konverterar uppladdade ARMeshAnchor .bin-filer till en kombinerad
binary glTF 2.0-fil (mesh.glb) som /viewer/3d kan rendera direkt.

.bin-formatet (skrivet av ButikSkanningView.serializeMeshAnchor):
    [4 B]    UInt32  vertexCount
    [4 B]    UInt32  faceCount
    [64 B]   float32 transform (4×4 column-major)
    [V·s]    float32 vertices  (stride s = 12 eller 16)
    [V·s]    float32 normals   (samma stride)
    [F·12]   UInt32  faces     (3 index per triangel)
    [F·1]    UInt8   classifications  (valfri, kan saknas)

Skriptet auto-detekterar både stride och om classifications finns
genom att jämföra mot den faktiska filstorleken.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Tuple

import numpy as np


HEADER_SIZE = 8 + 64  # 4+4 (counts) + 16 floats (transform)


def _detekt_layout(file_size: int, vc: int, fc: int) -> Tuple[int, int]:
    """Returnerar (vertex_stride, classification_size) — ger upp om ingen passar."""
    rest = file_size - HEADER_SIZE
    for vstride in (16, 12):
        for cls in (0, 1):
            if rest == vc * vstride * 2 + fc * 12 + fc * cls:
                return vstride, cls
    raise ValueError(
        f"Kan inte gissa layout: V={vc} F={fc} rest={rest} bytes"
    )


def _läs_bin(file_path: Path):
    """Läs en .bin och returnera (positions_world, normals_world, indices)."""
    data = file_path.read_bytes()
    if len(data) < HEADER_SIZE:
        raise ValueError(f"{file_path.name}: för kort fil ({len(data)} B)")

    vc, fc = struct.unpack_from("<II", data, 0)

    # Transform: 16 floats lagrade column-major från Swift.
    # NumPy reshape är row-major, så raw[i,j] = swift[j,i] (transponerad).
    raw = np.frombuffer(data, dtype=np.float32, count=16, offset=8).reshape(4, 4)

    vstride, cls_size = _detekt_layout(len(data), vc, fc)

    off = HEADER_SIZE

    # Vertices (möjligen padded float4)
    if vstride == 12:
        vert = np.frombuffer(data, dtype=np.float32, count=vc * 3, offset=off).reshape(vc, 3)
    else:
        padded = np.frombuffer(data, dtype=np.float32, count=vc * 4, offset=off).reshape(vc, 4)
        vert = padded[:, :3].copy()
    off += vc * vstride

    # Normals
    if vstride == 12:
        norm = np.frombuffer(data, dtype=np.float32, count=vc * 3, offset=off).reshape(vc, 3)
    else:
        padded = np.frombuffer(data, dtype=np.float32, count=vc * 4, offset=off).reshape(vc, 4)
        norm = padded[:, :3].copy()
    off += vc * vstride

    # Faces (UInt32 trippel)
    idx = np.frombuffer(data, dtype=np.uint32, count=fc * 3, offset=off).reshape(fc, 3)

    # ── Applicera transform i världs-koordinater ──
    # Swift: world_col = M_swift @ local_col, med bytes lagrade column-major.
    # Vår `raw` är M_swift.T (numpy reshape från sekventiella column-bytes).
    # Med radvektor-konvention: world_row = local_row @ M_swift.T = local_row @ raw
    ones = np.ones((vc, 1), dtype=np.float32)
    homog = np.concatenate([vert, ones], axis=1)            # (V, 4)
    world_pos = (homog @ raw)[:, :3]                        # (V, 3)

    # Normals: bara rotation (3×3-blocket från raw, vilket är M_swift[:3,:3].T).
    # world_norm_row = local_norm_row @ M_swift[:3,:3].T = local_norm_row @ raw[:3,:3]
    world_norm = norm @ raw[:3, :3]
    längd = np.linalg.norm(world_norm, axis=1, keepdims=True)
    world_norm = world_norm / np.maximum(längd, 1e-6)

    return (
        world_pos.astype(np.float32),
        world_norm.astype(np.float32),
        idx.astype(np.uint32),
    )


def _bygg_glb(
    positions: np.ndarray,
    normals: np.ndarray,
    indices: np.ndarray,
    out_path: Path,
) -> int:
    """Skriv en valid binary glTF 2.0-fil. Returnerar storlek i bytes."""
    pos_bytes = np.ascontiguousarray(positions, dtype=np.float32).tobytes()
    norm_bytes = np.ascontiguousarray(normals, dtype=np.float32).tobytes()
    idx_bytes = np.ascontiguousarray(indices, dtype=np.uint32).flatten().tobytes()

    def _pad4(b: bytes, fill: bytes = b"\x00") -> bytes:
        while len(b) % 4 != 0:
            b += fill
        return b

    bin_data = b""
    pos_offset = len(bin_data); bin_data = _pad4(bin_data + pos_bytes)
    norm_offset = len(bin_data); bin_data = _pad4(bin_data + norm_bytes)
    idx_offset = len(bin_data); bin_data = _pad4(bin_data + idx_bytes)

    n_pos = int(len(positions))
    n_norm = int(len(normals))
    n_idx = int(indices.size)

    mn = positions.min(axis=0).tolist() if n_pos > 0 else [0.0, 0.0, 0.0]
    mx = positions.max(axis=0).tolist() if n_pos > 0 else [0.0, 0.0, 0.0]

    manifest = {
        "asset": {
            "version": "2.0",
            "generator": "PulsAr backend mesh_converter (.bin → glTF 2.0)",
        },
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "PulsArLiDAR"}],
        "meshes": [{
            "name": "ScannedMesh",
            "primitives": [{
                "attributes": {"POSITION": 0, "NORMAL": 1},
                "indices": 2,
                "material": 0,
                "mode": 4,
            }],
        }],
        "materials": [{
            "name": "DefaultMatte",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.78, 0.80, 0.82, 1.0],
                "metallicFactor": 0.05,
                "roughnessFactor": 0.85,
            },
            "doubleSided": True,
        }],
        "buffers": [{"byteLength": len(bin_data)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": pos_offset,  "byteLength": n_pos * 12, "target": 34962},
            {"buffer": 0, "byteOffset": norm_offset, "byteLength": n_norm * 12, "target": 34962},
            {"buffer": 0, "byteOffset": idx_offset,  "byteLength": n_idx * 4,  "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": n_pos, "type": "VEC3", "min": mn, "max": mx},
            {"bufferView": 1, "componentType": 5126, "count": n_norm, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5125, "count": n_idx, "type": "SCALAR"},
        ],
    }

    json_chunk = json.dumps(manifest, sort_keys=True).encode("utf-8")
    while len(json_chunk) % 4 != 0:
        json_chunk += b" "

    bin_chunk = bin_data
    while len(bin_chunk) % 4 != 0:
        bin_chunk += b"\x00"

    total_length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)

    with open(out_path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total_length))   # 'glTF', v2, length
        fh.write(struct.pack("<II", len(json_chunk), 0x4E4F534A))    # JSON chunk header
        fh.write(json_chunk)
        fh.write(struct.pack("<II", len(bin_chunk), 0x004E4942))     # BIN chunk header
        fh.write(bin_chunk)

    return total_length


def konvertera_session(session_dir: Path) -> dict:
    """
    Slå ihop alla .bin-filer i sessionsmappen → mesh.glb.
    Returnerar metadata om resultatet.
    """
    session_dir = Path(session_dir)
    mesh_dir = session_dir / "mesh"
    if not mesh_dir.exists():
        raise FileNotFoundError(f"Ingen mesh-mapp i {session_dir}")

    bin_files = sorted(mesh_dir.glob("*.bin"))
    if not bin_files:
        raise ValueError(f"Inga .bin-filer i {mesh_dir}")

    all_pos = []
    all_norm = []
    all_idx = []
    idx_offset = 0
    skippade = []

    for bf in bin_files:
        try:
            pos, norm, idx = _läs_bin(bf)
        except Exception as e:
            skippade.append(f"{bf.name}: {e}")
            continue
        all_pos.append(pos)
        all_norm.append(norm)
        all_idx.append(idx + idx_offset)
        idx_offset += len(pos)

    if not all_pos:
        raise RuntimeError(f"Alla .bin-filer kunde inte parsas. Fel: {skippade}")

    positions = np.concatenate(all_pos, axis=0)
    normals = np.concatenate(all_norm, axis=0)
    indices = np.concatenate(all_idx, axis=0)

    out = session_dir / "mesh.glb"
    storlek = _bygg_glb(positions, normals, indices, out)

    return {
        "fil": str(out),
        "storlek_mb": round(storlek / (1024 * 1024), 2),
        "antal_anchors": len(bin_files),
        "antal_anchors_ok": len(all_pos),
        "antal_skippade": len(skippade),
        "skippade": skippade,
        "antal_vertices": int(len(positions)),
        "antal_trianglar": int(len(indices)),
        "bbox_min": positions.min(axis=0).tolist(),
        "bbox_max": positions.max(axis=0).tolist(),
    }


def _läs_glb(file_path: Path):
    """Läs en binary glTF 2.0 (vårt _bygg_glb-format) → (positions, normals, indices).

    Läser via accessors/bufferViews så det tål vår egen output oavsett offset-padding.
    Returnerar (positions VEC3 f32, normals VEC3 f32|None, indices uint32).
    """
    data = file_path.read_bytes()
    magic, ver, _length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError(f"{file_path.name}: ej glTF (magic {hex(magic)})")

    off = 12
    jlen, _jtype = struct.unpack_from("<II", data, off); off += 8
    manifest = json.loads(data[off:off + jlen].decode("utf-8")); off += jlen
    _blen, _btype = struct.unpack_from("<II", data, off); off += 8
    bin_start = off  # BIN-chunkens data börjar här

    accessors = manifest["accessors"]
    views = manifest["bufferViews"]

    _KOMP = {5126: (np.float32, 4), 5125: (np.uint32, 4), 5123: (np.uint16, 2)}
    _ANTAL = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def _läs_accessor(idx: int):
        acc = accessors[idx]
        bv = views[acc["bufferView"]]
        dtype, _sz = _KOMP[acc["componentType"]]
        n = acc["count"] * _ANTAL[acc["type"]]
        start = bin_start + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        arr = np.frombuffer(data, dtype=dtype, count=n, offset=start)
        comps = _ANTAL[acc["type"]]
        return arr.reshape(acc["count"], comps) if comps > 1 else arr

    prim = manifest["meshes"][0]["primitives"][0]
    attr = prim["attributes"]
    positions = _läs_accessor(attr["POSITION"]).astype(np.float32)
    normals = (_läs_accessor(attr["NORMAL"]).astype(np.float32)
               if "NORMAL" in attr else None)
    indices = _läs_accessor(prim["indices"]).astype(np.uint32)
    return positions, normals, indices


def konvertera_alla_sessioner(butik_dir: Path, out_path: Path | None = None) -> dict:
    """
    Slå ihop mesh.glb från ALLA sessioner → en gemensam mesh_merged.glb.

    Alla sessioner ligger redan i samma kart-frame (positioner == transform ==
    kartkoordinater), så meshar kan konkateneras direkt utan per-session-transform.
    Detta fyller hål vid omskanning: nya sessioner adderar geometri i samma frame.

    Cache: om out_path finns och är nyare än alla sessioners mesh.glb → återanvänd.
    """
    butik_dir = Path(butik_dir)
    sessioner_dir = butik_dir / "sessioner"
    if not sessioner_dir.exists():
        raise FileNotFoundError(f"Ingen sessioner-mapp i {butik_dir}")

    if out_path is None:
        out_path = butik_dir / "mesh_merged.glb"
    out_path = Path(out_path)

    glb_files: list[Path] = []
    for sd in sorted(sessioner_dir.iterdir()):
        if sd.is_dir() and (sd / "mesh.glb").exists():
            glb_files.append(sd / "mesh.glb")
    if not glb_files:
        raise ValueError(f"Inga mesh.glb i någon session under {sessioner_dir}")

    # Cache-check: hoppa ombygge om merged är färskare än alla sessioners mesh.glb.
    # (Undvik att räkna in vår egen merged-fil om den råkar ligga i sessioner.)
    if out_path.exists():
        senaste = max(gf.stat().st_mtime for gf in glb_files)
        if out_path.stat().st_mtime >= senaste:
            return {"fil": str(out_path), "cache": True, "antal_sessioner": len(glb_files)}

    all_pos = []
    all_norm = []
    all_idx = []
    idx_offset = 0
    skippade = []

    for gf in glb_files:
        try:
            pos, norm, idx = _läs_glb(gf)
        except Exception as e:
            skippade.append(f"{gf.parent.name}: {e}")
            continue
        if norm is None:
            norm = np.zeros_like(pos)
        all_pos.append(pos)
        all_norm.append(norm)
        all_idx.append(idx.reshape(-1, 3) + idx_offset if idx.ndim == 1 else idx + idx_offset)
        idx_offset += len(pos)

    if not all_pos:
        raise RuntimeError(f"Alla mesh.glb kunde inte parsas. Fel: {skippade}")

    positions = np.concatenate(all_pos, axis=0)
    normals = np.concatenate(all_norm, axis=0)
    indices = np.concatenate(all_idx, axis=0)

    storlek = _bygg_glb(positions, normals, indices, out_path)

    return {
        "fil": str(out_path),
        "cache": False,
        "storlek_mb": round(storlek / (1024 * 1024), 2),
        "antal_sessioner": len(glb_files),
        "antal_sessioner_ok": len(all_pos),
        "antal_skippade": len(skippade),
        "skippade": skippade,
        "antal_vertices": int(len(positions)),
        "antal_trianglar": int(len(indices)),
        "bbox_min": positions.min(axis=0).tolist(),
        "bbox_max": positions.max(axis=0).tolist(),
    }


# CLI: kör direkt på en sessionsmapp
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Användning: python -m core.mesh_converter <sessionsmapp>")
        sys.exit(1)
    res = konvertera_session(Path(sys.argv[1]))
    print(json.dumps(res, indent=2, ensure_ascii=False))
