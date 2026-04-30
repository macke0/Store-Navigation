import struct
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class MeshAnchor:
    anchor_id: str
    transform: np.ndarray  # 4x4 matrix (world-from-anchor)
    vertices: np.ndarray   # (N, 3) i anchor-lokala koordinater
    normals: np.ndarray    # (N, 3)
    faces: np.ndarray      # (M, 3) trianglar med vertex-index
    classifications: Optional[np.ndarray] = None  # (M,) byte per triangel
    
    @property
    def vertex_count(self) -> int:
        return len(self.vertices)
    
    @property
    def face_count(self) -> int:
        return len(self.faces)
    
    def world_vertices(self) -> np.ndarray:
        """Returnerar vertices i världs-koordinater (efter transform)."""
        # Lägg till homogen koordinat
        homog = np.hstack([self.vertices, np.ones((len(self.vertices), 1))])
        # Applicera transform (transform är column-major från Swift)
        # Swift simd_float4x4 kolumn-major == numpy radvis multiplikation
        world = (self.transform @ homog.T).T
        return world[:, :3]


def parse_mesh_anchor(filepath: Path) -> MeshAnchor:
    """Parsa en .bin-fil till MeshAnchor."""
    with open(filepath, 'rb') as f:
        data = f.read()
    
    offset = 0
    
    # Header
    vertex_count = struct.unpack_from('<I', data, offset)[0]
    offset += 4
    face_count = struct.unpack_from('<I', data, offset)[0]
    offset += 4
    
    # Transform (16 floats, column-major)
    transform_flat = struct.unpack_from('<16f', data, offset)
    offset += 64
    # Konvertera column-major → row-major numpy
    transform = np.array(transform_flat, dtype=np.float32).reshape(4, 4, order='F')
    
    # Vertices: ARKit använder typiskt stride=12 för Float3
    # Vi antar packed Float3 (12 bytes per vertex)
    vertex_bytes = vertex_count * 12
    vertices = np.frombuffer(data[offset:offset + vertex_bytes], 
                              dtype=np.float32).reshape(vertex_count, 3).copy()
    offset += vertex_bytes
    
    # Normals: samma format
    normal_bytes = vertex_count * 12
    normals = np.frombuffer(data[offset:offset + normal_bytes],
                             dtype=np.float32).reshape(vertex_count, 3).copy()
    offset += normal_bytes
    
    # Faces: 3 UInt32 per triangel
    face_bytes = face_count * 12
    faces = np.frombuffer(data[offset:offset + face_bytes],
                           dtype=np.uint32).reshape(face_count, 3).copy()
    offset += face_bytes
    
    # Classifications (om finns kvar)
    classifications = None
    if offset < len(data):
        remaining = len(data) - offset
        if remaining >= face_count:
            classifications = np.frombuffer(
                data[offset:offset + face_count], dtype=np.uint8
            ).copy()
    
    return MeshAnchor(
        anchor_id=filepath.stem,
        transform=transform,
        vertices=vertices,
        normals=normals,
        faces=faces,
        classifications=classifications,
    )


def parse_session_mesh(session_dir: Path) -> list:
    """Läs alla mesh-anchors från en session."""
    mesh_dir = session_dir / "mesh"
    if not mesh_dir.exists():
        print(f"⚠️ Ingen mesh-mapp i {session_dir}")
        return []
    
    anchors = []
    for bin_fil in sorted(mesh_dir.glob("*.bin")):
        try:
            anchor = parse_mesh_anchor(bin_fil)
            anchors.append(anchor)
        except Exception as e:
            print(f"❌ Kunde inte parsa {bin_fil.name}: {e}")
    
    return anchors


def mesh_statistik(anchors: list) -> dict:
    """Sammanställ statistik från alla mesh-anchors."""
    if not anchors:
        return {"antal_anchors": 0}
    
    total_verts = sum(a.vertex_count for a in anchors)
    total_faces = sum(a.face_count for a in anchors)
    
    # Samla alla world-vertices för att hitta bounding box
    alla_world = np.vstack([a.world_vertices() for a in anchors])
    min_xyz = alla_world.min(axis=0)
    max_xyz = alla_world.max(axis=0)
    
    return {
        "antal_anchors": len(anchors),
        "total_vertices": total_verts,
        "total_faces": total_faces,
        "bounds_min": min_xyz.tolist(),
        "bounds_max": max_xyz.tolist(),
        "storlek": (max_xyz - min_xyz).tolist(),
    }

def exportera_ply(anchors: list, output_path: Path):
    """Exportera alla mesh-anchors som en samlad PLY-fil."""
    # Samla alla vertices i världs-koordinater och alla faces
    alla_verts = []
    alla_faces = []
    vert_offset = 0
    
    for anchor in anchors:
        world_verts = anchor.world_vertices()
        alla_verts.append(world_verts)
        
        # Faces måste få ny offset eftersom vi staplar vertices
        faces_offset = anchor.faces + vert_offset
        alla_faces.append(faces_offset)
        vert_offset += len(world_verts)
    
    alla_verts = np.vstack(alla_verts)
    alla_faces = np.vstack(alla_faces)
    
    # Skriv PLY-fil (ASCII)
    with open(output_path, 'w') as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(alla_verts)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write(f"element face {len(alla_faces)}\n")
        f.write("property list uchar uint vertex_indices\n")
        f.write("end_header\n")
        
        for v in alla_verts:
            f.write(f"{v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
        for face in alla_faces:
            f.write(f"3 {face[0]} {face[1]} {face[2]}\n")
    
    print(f"✅ Exporterat: {output_path}")
    print(f"   {len(alla_verts):,} vertices, {len(alla_faces):,} faces")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        session_dir = Path(sys.argv[1])
    else:
        # Hitta senaste sessionen
        sessioner = Path("data/butik_modell/sessioner")
        senaste = max(sessioner.glob("session_*"), key=lambda p: p.stat().st_mtime)
        session_dir = senaste
    
    print(f"📂 Läser mesh från: {session_dir}")
    
    anchors = parse_session_mesh(session_dir)
    stats = mesh_statistik(anchors)
    
    print(f"\n📊 Mesh-statistik:")
    print(f"   Antal anchors: {stats['antal_anchors']}")
    if stats['antal_anchors'] > 0:
        print(f"   Total vertices: {stats['total_vertices']:,}")
        print(f"   Total faces: {stats['total_faces']:,}")
        print(f"   Bounding box (min): {stats['bounds_min']}")
        print(f"   Bounding box (max): {stats['bounds_max']}")
        print(f"   Storlek (m): {stats['storlek']}")
        
        # Klassifikations-stats
        med_class = [a for a in anchors if a.classifications is not None]
        print(f"\n   Anchors med klassifikation: {len(med_class)}/{len(anchors)}")
        if med_class:
            from collections import Counter
            alla_class = np.concatenate([a.classifications for a in med_class])
            counter = Counter(alla_class.tolist())
            
            # ARKit-klasser:
            klass_namn = {
                0: "none",
                1: "wall",
                2: "floor", 
                3: "ceiling",
                4: "table",
                5: "seat",
                6: "window",
                7: "door",
            }
            
            print(f"\n   Klassifikations-fördelning:")
            for klass_id, count in sorted(counter.items()):
                namn = klass_namn.get(klass_id, f"okänd_{klass_id}")
                print(f"      {namn}: {count:,}")
        
        # Exportera PLY (alltid, oavsett klassifikation)
        ply_path = session_dir / "mesh.ply"
        exportera_ply(anchors, ply_path)