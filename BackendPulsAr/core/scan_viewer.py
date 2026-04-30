"""
scan_viewer.py — Butiksvy med produktredigering
Visar frames, minimap, och låter personal redigera produkter.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import json

router = APIRouter(tags=["Scan Viewer"])

BUTIK_DIR = Path("/home/hartman/ICA_ai/BackendPulsAr/data/butik_modell")
KARTOR_DIR = Path("/home/hartman/ICA_ai/BackendPulsAr/data/kartor")


@router.get("/viewer", response_class=HTMLResponse)
async def viewer_huvudsida():
    return VIEWER_HTML


@router.get("/viewer/skanningar")
async def lista_skanningar():
    resultat = []
    sessioner_dir = BUTIK_DIR / "sessioner"
    if sessioner_dir.exists():
        for d in sorted(sessioner_dir.iterdir()):
            if d.is_dir():
                frames_dir = d / "frames"
                n_frames = len(list(frames_dir.glob("*.jpg"))) if frames_dir.exists() else 0
                resultat.append({"namn": d.name, "typ": "session", "frames": n_frames, "källa": "butik_modell"})
    if KARTOR_DIR.exists():
        for d in KARTOR_DIR.iterdir():
            if d.is_dir() and (d / "metadata.json").exists():
                with open(d / "metadata.json") as f:
                    meta = json.load(f)
                resultat.append({"namn": meta.get("gång", d.name), "typ": "karta", "frames": len(meta.get("frames", [])), "källa": "kartor_3d"})
    for sd in sorted(Path("/tmp").glob("skanning_*")):
        if sd.is_dir():
            n = len(list(sd.glob("frame_*.jpg")))
            if n > 0:
                resultat.append({"namn": sd.name, "typ": "rå", "frames": n, "källa": "tmp"})
    return {"skanningar": resultat}


@router.get("/viewer/data/{namn}")
async def viewer_data(namn: str):
    frames, positioner = [], []
    session_dir = BUTIK_DIR / "sessioner" / namn
    if session_dir.exists():
        fd = session_dir / "frames"
        if fd.exists():
            for ff in sorted(fd.glob("*.jpg")):
                fid = int(ff.stem.replace("frame_", ""))
                frames.append({"id": fid, "har_bild": True})
        pp = session_dir / "positioner.json"
        if pp.exists():
            with open(pp) as f: positioner = json.load(f)
    kd = KARTOR_DIR / namn.replace(" ", "_")
    if kd.exists() and (kd / "metadata.json").exists():
        with open(kd / "metadata.json") as f: meta = json.load(f)
        positioner = meta.get("positioner", [])
        for fid in meta.get("frames", []):
            frames.append({"id": fid, "har_bild": True})
        # Om inga positioner i metadata, ladda från sessioner
        if not positioner:
            sessioner_dir = BUTIK_DIR / "sessioner"
            if sessioner_dir.exists():
                for sd in sorted(sessioner_dir.iterdir()):
                    pp2 = sd / "positioner.json"
                    if pp2.exists():
                        with open(pp2) as f2: spos = json.load(f2)
                        for p in spos: p["session"] = sd.name
                        positioner.extend(spos)
    rd = Path("/tmp") / namn
    if rd.exists():
        for ff in sorted(rd.glob("frame_*.jpg")):
            fid = int(ff.stem.replace("frame_", ""))
            frames.append({"id": fid, "har_bild": True})
        pp = rd / "positioner.json"
        if pp.exists():
            with open(pp) as f: positioner = json.load(f)
    # Ladda produkter
    produkter = []
    prod_path = BUTIK_DIR / "identifierade_produkter.json"
    if prod_path.exists():
        with open(prod_path) as f: produkter = json.load(f)
    return {"namn": namn, "antal_frames": len(frames), "frames": frames, "positioner": positioner, "produkter": produkter}


@router.get("/viewer/frame/{namn}/{frame_id}")
async def viewer_frame_bild(namn: str, frame_id: int):
    for p in [
        BUTIK_DIR / "sessioner" / namn / "frames" / f"frame_{frame_id}.jpg",
        KARTOR_DIR / namn.replace(" ", "_") / f"frame_{frame_id}.jpg",
        Path("/tmp") / namn / f"frame_{frame_id}.jpg",
    ]:
        if p.exists(): return FileResponse(str(p))
    for sd in Path("/tmp").glob(f"skanning_*{namn.replace(' ', '_')}*"):
        fp = sd / f"frame_{frame_id}.jpg"
        if fp.exists(): return FileResponse(str(fp))
    return {"error": "Frame ej hittad"}


# ─── MESH (ARKit/RoomPlan) ──────────────────────────────────────────
# Returnerar triangulerad mesh som JSON: vertices + faces + classifications.
# Lazy-genererar från anchor-binärer i sessioner/{x}/mesh/. För 'hela_butiken'
# slås alla sessioners meshar ihop.
@router.get("/viewer/mesh/{namn}")
async def viewer_mesh(namn: str):
    try:
        import numpy as np
        from core.mesh_parser import parse_session_mesh
    except Exception as e:
        return {"error": f"mesh_parser ej tillgänglig: {e}", "vertices": [], "faces": []}

    sessioner_dirs = []
    if namn == "hela_butiken":
        sd_root = BUTIK_DIR / "sessioner"
        if sd_root.exists():
            sessioner_dirs = [d for d in sorted(sd_root.iterdir()) if d.is_dir()]
    else:
        sd = BUTIK_DIR / "sessioner" / namn
        if sd.exists():
            sessioner_dirs = [sd]

    if not sessioner_dirs:
        return {"error": "ingen session", "vertices": [], "faces": [], "classifications": []}

    alla_verts, alla_norms, alla_faces, alla_class = [], [], [], []
    vert_offset = 0
    for session_dir in sessioner_dirs:
        try:
            anchors = parse_session_mesh(session_dir)
        except Exception as e:
            print(f"⚠️ mesh-parse-fel i {session_dir}: {e}")
            continue
        for a in anchors:
            try:
                wv = a.world_vertices()
            except Exception:
                continue
            alla_verts.append(wv)
            alla_faces.append(a.faces + vert_offset)
            # Rotera normaler med transformens 3x3-del (utan translation)
            try:
                R = a.transform[:3, :3]
                world_norms = (R @ a.normals.T).T
                # Normalisera (ifall transform har skala)
                lens = np.linalg.norm(world_norms, axis=1, keepdims=True)
                lens[lens < 1e-8] = 1.0
                world_norms = world_norms / lens
                alla_norms.append(world_norms.astype(np.float32))
            except Exception:
                alla_norms.append(np.zeros_like(wv, dtype=np.float32))
            if a.classifications is not None and len(a.classifications) == len(a.faces):
                alla_class.append(a.classifications)
            else:
                alla_class.append(np.zeros(len(a.faces), dtype=np.uint8))
            vert_offset += len(wv)

    if not alla_verts:
        return {"error": "ingen mesh-data", "vertices": [], "faces": [], "classifications": []}

    verts = np.vstack(alla_verts).astype(np.float32)
    norms = np.vstack(alla_norms).astype(np.float32)
    faces = np.vstack(alla_faces).astype(np.uint32)
    cls = np.concatenate(alla_class).astype(np.uint8) if alla_class else np.zeros(len(faces), dtype=np.uint8)

    # Decimera om för stort (browser-prestanda) — enkel face-sampling
    MAX_FACES = 300_000
    if len(faces) > MAX_FACES:
        step = len(faces) // MAX_FACES + 1
        faces = faces[::step]
        cls = cls[::step]

    return {
        "vertices": verts.tolist(),
        "normals": norms.tolist(),
        "faces": faces.tolist(),
        "classifications": cls.tolist(),
        "antal_v": int(len(verts)),
        "antal_f": int(len(faces)),
    }


VIEWER_HTML = """<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Puls-AR — Butiksvy</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'SF Pro',system-ui,sans-serif;background:#0a0a0a;color:#e0e0e0;overflow:hidden;height:100vh}
.ica-red{color:#e31e24}
#startPage{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;gap:24px}
#startPage h1{font-size:32px;font-weight:700}
.subtitle{color:#666;font-size:14px;margin-top:-16px}
.scan-list{display:flex;flex-direction:column;gap:8px;width:100%;max-width:440px;padding:0 20px}
.scan-card{background:#161616;border:1px solid #222;border-radius:12px;padding:14px 18px;cursor:pointer;transition:all .2s;display:flex;align-items:center;gap:14px}
.scan-card:hover{background:#1a1a1a;border-color:#e31e24}
.scan-icon{width:40px;height:40px;background:rgba(227,30,36,.12);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px}
.scan-info{flex:1}.scan-info h3{font-size:14px}.scan-info .meta{font-size:11px;color:#555;margin-top:2px}
.no-scans{color:#444;text-align:center;padding:40px}.no-scans p{margin-top:8px;font-size:13px}
#viewerPage{display:none;height:100vh;flex-direction:column}
.topbar{display:flex;align-items:center;padding:10px 16px;background:#111;border-bottom:1px solid #1a1a1a;gap:12px;flex-shrink:0}
.back-btn{background:none;border:none;color:#e31e24;font-size:20px;cursor:pointer;padding:4px 8px}
.topbar-title{font-size:14px;font-weight:600;flex:1}
.frame-counter{font-size:12px;color:#555;font-variant-numeric:tabular-nums}
.viewer-content{display:flex;flex:1;overflow:hidden}
.frame-view{flex:1;position:relative;background:#000;display:flex;align-items:center;justify-content:center}
.frame-view img{max-width:100%;max-height:100%;object-fit:contain}
.frame-placeholder{color:#333;text-align:center}.frame-placeholder .icon{font-size:48px;margin-bottom:12px}
.nav-arrow{position:absolute;top:50%;transform:translateY(-50%);background:rgba(0,0,0,.6);border:1px solid #333;color:#fff;font-size:24px;padding:12px 16px;cursor:pointer;border-radius:8px;transition:all .15s;z-index:10}
.nav-arrow:hover{background:rgba(227,30,36,.4);border-color:#e31e24}
.nav-arrow.left{left:12px}.nav-arrow.right{right:12px}
.sidebar{width:280px;background:#111;border-left:1px solid #1a1a1a;display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto}
.sidebar h3{font-size:11px;color:#444;text-transform:uppercase;letter-spacing:1px;padding:12px 14px 6px}
.minimap-container{padding:10px}
.minimap{width:100%;aspect-ratio:1;background:#0a0a0a;border:1px solid #1a1a1a;border-radius:8px;position:relative;overflow:hidden}
.minimap-dot{position:absolute;width:3px;height:3px;border-radius:50%;background:#333;transform:translate(-50%,-50%)}
.minimap-dot.active{background:#e31e24;width:8px;height:8px;box-shadow:0 0 8px rgba(227,30,36,.6)}
.minimap-dot.product{background:#4CAF50;width:7px;height:7px;cursor:pointer;z-index:5}
.minimap-dot.product:hover{width:10px;height:10px;box-shadow:0 0 6px rgba(76,175,80,.6)}
.minimap-dot.product.low{background:#FF9800}
.minimap-dot.product.manual{background:#2196F3}
.info-row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #141414;font-size:11px}
.info-row .label{color:#444}.info-row .value{color:#777;font-variant-numeric:tabular-nums}
.timeline{padding:0 14px 10px;flex-shrink:0}
.timeline input[type=range]{width:100%;accent-color:#e31e24}
.kbd-hints{display:flex;gap:8px;justify-content:center;padding:6px;font-size:10px;color:#333}
kbd{background:#1a1a1a;border:1px solid #222;border-radius:4px;padding:1px 5px;font-family:inherit}
.loading{display:flex;align-items:center;justify-content:center;height:100%;color:#444}
@keyframes spin{to{transform:rotate(360deg)}}
.spinner{width:20px;height:20px;border:2px solid #222;border-top-color:#e31e24;border-radius:50%;animation:spin .8s linear infinite;margin-right:8px}

/* Produktlista */
.produkt-lista{padding:0 10px;max-height:300px;overflow-y:auto}
.produkt-item{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:6px;cursor:pointer;transition:all .15s;font-size:12px}
.produkt-item:hover{background:#1a1a1a}
.produkt-item.selected{background:rgba(227,30,36,.15);border:1px solid rgba(227,30,36,.3)}
.produkt-konfidens{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.konf-hög{background:#4CAF50}
.konf-medium{background:#FF9800}
.konf-låg{background:#f44336}
.produkt-namn{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#ccc}
.produkt-meta{font-size:10px;color:#555}
.produkt-edit{color:#555;font-size:10px;cursor:pointer;padding:2px 6px;border-radius:4px}
.produkt-edit:hover{background:#222;color:#e31e24}

/* Edit modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);display:flex;align-items:center;justify-content:center;z-index:100}
.modal{background:#1a1a1a;border:1px solid #333;border-radius:14px;padding:24px;width:360px;max-width:90vw}
.modal h2{font-size:16px;margin-bottom:16px;color:#e0e0e0}
.modal label{font-size:12px;color:#666;display:block;margin-top:10px;margin-bottom:4px}
.modal input{width:100%;background:#111;border:1px solid #333;border-radius:8px;padding:8px 12px;color:#e0e0e0;font-size:14px;outline:none}
.modal input:focus{border-color:#e31e24}
.modal-buttons{display:flex;gap:8px;margin-top:20px;justify-content:flex-end}
.modal-btn{padding:8px 16px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s}
.btn-save{background:#e31e24;color:#fff}.btn-save:hover{background:#c4181d}
.btn-cancel{background:#222;color:#888}.btn-cancel:hover{background:#333}
.btn-delete{background:transparent;color:#f44336;margin-right:auto}.btn-delete:hover{background:rgba(244,67,54,.1)}
.btn-add{background:#222;border:1px dashed #444;color:#888;width:100%;padding:8px;border-radius:8px;cursor:pointer;font-size:12px;margin:8px 10px}
.btn-add:hover{border-color:#e31e24;color:#e31e24}
</style>
</head>
<body>

<div id="startPage">
  <h1>🛒 <span class="ica-red">Puls-AR</span> Viewer</h1>
  <p class="subtitle">Utforska och redigera butiksskanningar</p>
  <div class="scan-list" id="scanList"><div class="loading"><div class="spinner"></div> Laddar...</div></div>
</div>

<div id="viewerPage">
  <div class="topbar">
    <button class="back-btn" onclick="visaStart()">←</button>
    <span class="topbar-title" id="viewerTitle">—</span>
    <span class="frame-counter" id="frameCounter">0/0</span>
  </div>
  <div class="viewer-content">
    <div class="frame-view" id="frameView">
      <button class="nav-arrow left" onclick="föregående()">‹</button>
      <img id="frameImg" src="" style="display:none">
      <div class="frame-placeholder" id="framePlaceholder"><div class="icon">📷</div><p>Laddar...</p></div>
      <button class="nav-arrow right" onclick="nästa()">›</button>
    </div>
    <div class="sidebar">
      <h3>Karta</h3>
      <div class="minimap-container"><div class="minimap" id="minimap"></div></div>
      
      <h3>Produkter <span id="produktCount" style="color:#555"></span></h3>
      <div class="produkt-lista" id="produktLista"></div>
      <button class="btn-add" onclick="visaLäggTillModal()">+ Lägg till produkt</button>
      
      <h3>Frame-info</h3>
      <div style="padding:0 14px;font-size:11px;color:#555" id="frameInfo"><p>Ingen data</p></div>
      
      <h3>Tidslinje</h3>
      <div class="timeline">
        <input type="range" id="timeline" min="0" max="0" value="0" oninput="gåTill(parseInt(this.value))">
      </div>
      <div class="kbd-hints"><span><kbd>←</kbd><kbd>→</kbd> Nav</span><span><kbd>Space</kbd> Spela</span></div>
    </div>
  </div>
</div>

<!-- Edit Modal -->
<div class="modal-overlay" id="editModal" style="display:none" onclick="if(event.target===this)stängModal()">
  <div class="modal">
    <h2 id="modalTitle">Redigera produkt</h2>
    <label>Produktnamn</label>
    <input id="editNamn" placeholder="T.ex. Arla Mjölk 3%">
    <label>X-position (meter)</label>
    <input id="editX" type="number" step="0.01">
    <label>Z-position (meter)</label>
    <input id="editZ" type="number" step="0.01">
    <label>Y-höjd (meter)</label>
    <input id="editY" type="number" step="0.01" value="1.5">
    <div class="modal-buttons">
      <button class="modal-btn btn-delete" id="deleteBtn" onclick="taBortProdukt()">Ta bort</button>
      <button class="modal-btn btn-cancel" onclick="stängModal()">Avbryt</button>
      <button class="modal-btn btn-save" onclick="sparaRedigering()">Spara</button>
    </div>
  </div>
</div>

<script>
const API = window.location.origin;
let currentScan = null, frames = [], positioner = [], produkter = [];
let currentIndex = 0, playing = false, playInterval = null;
let editingProduct = null;
let minimapBounds = {};

async function laddaSkanningar() {
  try {
    const r = await fetch(`${API}/viewer/skanningar`);
    const d = await r.json();
    const list = document.getElementById('scanList');
    if (!d.skanningar.length) {
      list.innerHTML = '<div class="no-scans"><div style="font-size:48px;margin-bottom:12px">📡</div><h3>Inga skanningar ännu</h3><p>Skanna butiken med appen.</p></div>';
      return;
    }
    list.innerHTML = d.skanningar.map(s => `
      <div class="scan-card" onclick="öppnaSkanning('${s.namn}')">
        <div class="scan-icon">${{session:'📹',karta:'🗺️',rå:'📁'}[s.typ]||'📁'}</div>
        <div class="scan-info"><h3>${s.namn}</h3><div class="meta">${s.frames} frames</div></div>
      </div>`).join('');
  } catch(e) {
    document.getElementById('scanList').innerHTML = `<div class="no-scans"><h3>Fel</h3><p>${e.message}</p></div>`;
  }
}

async function öppnaSkanning(namn) {
  document.getElementById('startPage').style.display = 'none';
  document.getElementById('viewerPage').style.display = 'flex';
  document.getElementById('viewerTitle').textContent = namn;
  currentScan = namn;
  const r = await fetch(`${API}/viewer/data/${encodeURIComponent(namn)}`);
  const d = await r.json();
  frames = d.frames; positioner = d.positioner || []; produkter = d.produkter || [];
  document.getElementById('timeline').max = Math.max(0, frames.length-1);
  byggMinimap();
  ritaProdukter();
  if (frames.length) gåTill(0);
}

function visaStart() {
  document.getElementById('startPage').style.display = 'flex';
  document.getElementById('viewerPage').style.display = 'none';
  stoppSpela(); laddaSkanningar();
}

function gåTill(i) {
  if (i<0||i>=frames.length) return;
  currentIndex = i;
  const f = frames[i], img = document.getElementById('frameImg'), ph = document.getElementById('framePlaceholder');
  if (f.har_bild) {
    img.src = `${API}/viewer/frame/${encodeURIComponent(currentScan)}/${f.id}`;
    img.style.display='block'; ph.style.display='none';
    img.onerror = () => {img.style.display='none';ph.style.display='block';};
  } else {img.style.display='none';ph.style.display='block';}
  document.getElementById('frameCounter').textContent = `${i+1}/${frames.length}`;
  document.getElementById('timeline').value = i;
  uppdateraMinimap(i); visaFrameInfo(f, i);
}

function nästa(){gåTill(currentIndex+1)} function föregående(){gåTill(currentIndex-1)}
function toggleSpela(){if(playing){stoppSpela();return;}playing=true;playInterval=setInterval(()=>{if(currentIndex>=frames.length-1){stoppSpela();return;}nästa();},150);}
function stoppSpela(){playing=false;if(playInterval)clearInterval(playInterval);}

function byggMinimap() {
  const mm = document.getElementById('minimap'); mm.innerHTML = '';
  if (!positioner.length) {mm.innerHTML='<p style="color:#333;text-align:center;padding:40px;font-size:11px">Ingen positionsdata</p>';return;}
  let minX=Infinity,maxX=-Infinity,minZ=Infinity,maxZ=-Infinity;
  for (const p of positioner) {minX=Math.min(minX,p.x||0);maxX=Math.max(maxX,p.x||0);minZ=Math.min(minZ,p.z||0);maxZ=Math.max(maxZ,p.z||0);}
  // Inkludera produkter i bounds
  for (const p of produkter) {minX=Math.min(minX,p.x||0);maxX=Math.max(maxX,p.x||0);minZ=Math.min(minZ,p.z||0);maxZ=Math.max(maxZ,p.z||0);}
  const pad=0.5;minX-=pad;maxX+=pad;minZ-=pad;maxZ+=pad;
  minimapBounds = {minX,maxX,minZ,maxZ,rX:maxX-minX||1,rZ:maxZ-minZ||1};
  
  for (let i=0;i<positioner.length;i++) {
    const p=positioner[i],dot=document.createElement('div');
    dot.className='minimap-dot';dot.id=`dot-${i}`;
    dot.style.left=`${((p.x||0)-minX)/minimapBounds.rX*90+5}%`;
    dot.style.top=`${((p.z||0)-minZ)/minimapBounds.rZ*90+5}%`;
    mm.appendChild(dot);
  }
}

function ritaProdukter() {
  const mm = document.getElementById('minimap');
  // Ta bort gamla produktprickar
  mm.querySelectorAll('.product').forEach(d => d.remove());
  
  // Rita produkter på minimap
  if (minimapBounds.rX) {
    for (const p of produkter) {
      const dot = document.createElement('div');
      const konf = p.konfidens || 0;
      dot.className = `minimap-dot product ${konf<0.4?'low':''} ${p.manuellt_korrigerad?'manual':''}`;
      dot.style.left = `${((p.x||0)-minimapBounds.minX)/minimapBounds.rX*90+5}%`;
      dot.style.top = `${((p.z||0)-minimapBounds.minZ)/minimapBounds.rZ*90+5}%`;
      dot.title = p.visningsnamn || 'Okänd';
      dot.onclick = (e) => { e.stopPropagation(); visaRedigeraModal(p); };
      mm.appendChild(dot);
    }
  }
  
  // Produktlista i sidebar
  const lista = document.getElementById('produktLista');
  document.getElementById('produktCount').textContent = `(${produkter.length})`;
  
  if (!produkter.length) {
    lista.innerHTML = '<p style="color:#333;font-size:11px;padding:8px">Inga produkter identifierade</p>';
    return;
  }
  
  lista.innerHTML = produkter.map((p,i) => {
    const konf = p.konfidens || 0;
    const konfKlass = konf > 0.7 ? 'konf-hög' : konf > 0.4 ? 'konf-medium' : 'konf-låg';
    const manual = p.manuellt_korrigerad ? ' 📝' : '';
    return `
      <div class="produkt-item" onclick="visaRedigeraModal(produkter[${i}])">
        <div class="produkt-konfidens ${konfKlass}"></div>
        <span class="produkt-namn">${p.visningsnamn||'Okänd'}${manual}</span>
        <span class="produkt-meta">${(konf*100).toFixed(0)}%</span>
        <span class="produkt-edit">✏️</span>
      </div>`;
  }).join('');
}

function uppdateraMinimap(i) {
  document.querySelectorAll('.minimap-dot.active').forEach(d=>d.classList.remove('active'));
  const dot=document.getElementById(`dot-${i}`);if(dot)dot.classList.add('active');
}

function visaFrameInfo(f,i) {
  const info=document.getElementById('frameInfo');
  if(i<positioner.length){const p=positioner[i];
    info.innerHTML=`
      <div class="info-row"><span class="label">Frame</span><span class="value">${f.id}</span></div>
      <div class="info-row"><span class="label">X</span><span class="value">${(p.x||0).toFixed(3)}</span></div>
      <div class="info-row"><span class="label">Z</span><span class="value">${(p.z||0).toFixed(3)}</span></div>
      <div class="info-row"><span class="label">Rot</span><span class="value">${(p.rot_y||0).toFixed(2)}°</span></div>
      <div class="info-row"><span class="label">LiDAR</span><span class="value">${p.har_lidar?'✅':'❌'}</span></div>
      <div class="info-row"><span class="label">3D</span><span class="value">${p.antal_3d_punkter||0}</span></div>`;
  } else {info.innerHTML=`<div class="info-row"><span class="label">Frame</span><span class="value">${f.id}</span></div>`;}
}

// ── REDIGERING ──

function visaRedigeraModal(produkt) {
  editingProduct = produkt;
  document.getElementById('modalTitle').textContent = 'Redigera produkt';
  document.getElementById('editNamn').value = produkt.visningsnamn || '';
  document.getElementById('editX').value = (produkt.x || 0).toFixed(3);
  document.getElementById('editZ').value = (produkt.z || 0).toFixed(3);
  document.getElementById('editY').value = (produkt.y || 1.5).toFixed(3);
  document.getElementById('deleteBtn').style.display = 'block';
  document.getElementById('editModal').style.display = 'flex';
  document.getElementById('editNamn').focus();
}

function visaLäggTillModal() {
  editingProduct = null;
  document.getElementById('modalTitle').textContent = 'Lägg till produkt';
  document.getElementById('editNamn').value = '';
  document.getElementById('editX').value = '0';
  document.getElementById('editZ').value = '0';
  document.getElementById('editY').value = '1.5';
  document.getElementById('deleteBtn').style.display = 'none';
  document.getElementById('editModal').style.display = 'flex';
  document.getElementById('editNamn').focus();
}

function stängModal() {
  document.getElementById('editModal').style.display = 'none';
  editingProduct = null;
}

async function sparaRedigering() {
  const namn = document.getElementById('editNamn').value.trim();
  const x = parseFloat(document.getElementById('editX').value);
  const z = parseFloat(document.getElementById('editZ').value);
  const y = parseFloat(document.getElementById('editY').value);
  
  if (!namn) { alert('Ange produktnamn'); return; }
  
  try {
    if (editingProduct && editingProduct.position_id) {
      // Korrigera befintlig
      await fetch(`${API}/produkter/korrigera`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({position_id: editingProduct.position_id, namn, x, y, z})
      });
    } else {
      // Lägg till ny
      await fetch(`${API}/produkter/lägg-till`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({namn, x, y, z})
      });
    }
    
    // Ladda om data
    stängModal();
    await öppnaSkanning(currentScan);
  } catch(e) {
    alert('Kunde inte spara: ' + e.message);
  }
}

async function taBortProdukt() {
  if (!editingProduct || !editingProduct.position_id) return;
  if (!confirm(`Ta bort ${editingProduct.visningsnamn}?`)) return;
  
  try {
    await fetch(`${API}/produkter/korrigera/${editingProduct.position_id}`, {method:'DELETE'});
    stängModal();
    await öppnaSkanning(currentScan);
  } catch(e) { alert('Fel: ' + e.message); }
}

document.addEventListener('keydown', e => {
  if (document.getElementById('editModal').style.display !== 'none') {
    if (e.key === 'Escape') stängModal();
    if (e.key === 'Enter') sparaRedigering();
    return;
  }
  if (document.getElementById('viewerPage').style.display === 'none') return;
  switch(e.key) {
    case 'ArrowRight':e.preventDefault();nästa();break;
    case 'ArrowLeft':e.preventDefault();föregående();break;
    case ' ':e.preventDefault();toggleSpela();break;
    case 'Escape':visaStart();break;
  }
});

laddaSkanningar();
</script>
</body>
</html>
"""

@router.get("/viewer/pointcloud")
async def viewer_pointcloud(max_points: int = 50000):
    """Returnera 3D-punktmoln från alla sessioner."""
    import random
    punkter = []
    sessioner_dir = BUTIK_DIR / "sessioner"
    if sessioner_dir.exists():
        for sd in sorted(sessioner_dir.iterdir()):
            pp = sd / "punkter_3d.json"
            if pp.exists():
                with open(pp) as f:
                    pts = json.load(f)
                for p in pts:
                    punkter.append([
                        round(p.get("x", 0), 3),
                        round(p.get("y", 0), 3),
                        round(p.get("z", 0), 3)
                    ])
    # Sampla om för många
    if len(punkter) > max_points:
        punkter = random.sample(punkter, max_points)
    return {"antal": len(punkter), "punkter": punkter}


@router.get("/viewer/pointcloud")
async def viewer_pointcloud(max_points: int = 50000):
    import random
    punkter = []
    sessioner_dir = BUTIK_DIR / "sessioner"
    if sessioner_dir.exists():
        for sd in sorted(sessioner_dir.iterdir()):
            pp = sd / "punkter_3d.json"
            if pp.exists():
                with open(pp) as f:
                    pts = json.load(f)
                for p in pts:
                    punkter.append([round(p.get("x",0),3),round(p.get("y",0),3),round(p.get("z",0),3)])
    if len(punkter) > max_points:
        punkter = random.sample(punkter, max_points)
    return {"antal": len(punkter), "punkter": punkter}
