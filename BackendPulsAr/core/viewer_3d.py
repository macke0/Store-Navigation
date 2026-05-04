"""
viewer_3d.py — 3D Butiksvy + Street View
Kombinerad 3D-scen med frame-panel och produktöverlägg.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["3D Viewer"])

@router.get("/viewer/3d", response_class=HTMLResponse)
async def viewer_3d():
    return HTML

HTML = r"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Puls-AR — 3D</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#e0e0e0;overflow:hidden;height:100vh;
  font-family:-apple-system,BlinkMacSystemFont,'SF Pro',system-ui,sans-serif}

/* Layout */
#app{display:flex;height:100vh;flex-direction:column}
.topbar{display:flex;align-items:center;padding:8px 14px;background:#111;
  border-bottom:1px solid #1a1a1a;gap:10px;flex-shrink:0;z-index:50}
.topbar a{color:#e31e24;text-decoration:none;font-size:14px;font-weight:600;
  padding:5px 12px;background:rgba(227,30,36,0.1);border-radius:6px}
.topbar a:hover{background:rgba(227,30,36,0.25)}
.topbar-title{font-size:14px;font-weight:600;flex:1}
.mode-btn{padding:4px 12px;border:1px solid #333;border-radius:6px;
  background:transparent;color:#777;font-size:11px;cursor:pointer;font-family:inherit}
.mode-btn.active{background:#e31e24;border-color:#e31e24;color:#fff}
.mode-btn:hover{border-color:#e31e24}
.stat{font-size:11px;color:#444}

/* Höjd-filter */
.h-filter{display:flex;align-items:center;gap:6px;font-size:11px;color:#777;
  padding:3px 10px;border:1px solid #222;border-radius:6px;background:#0d0d0d}
.h-filter label{font-weight:600;color:#888}
.h-filter input[type=range]{width:90px;accent-color:#e31e24;cursor:pointer}
.h-filter .h-val{min-width:36px;text-align:right;font-variant-numeric:tabular-nums;color:#aaa}

.main{display:flex;flex:1;overflow:hidden}

/* 3D canvas */
#canvasWrap{flex:1;position:relative;background:#0a0a0a}
#canvasWrap canvas{width:100%!important;height:100%!important;display:block}

/* Frame panel */
#framePanel{width:0;overflow:hidden;transition:width 0.3s ease;background:#0d0d0d;
  border-left:1px solid #1a1a1a;display:flex;flex-direction:column;flex-shrink:0}
#framePanel.open{width:420px}
#framePanel .fp-head{display:flex;align-items:center;padding:8px 12px;
  background:#111;border-bottom:1px solid #1a1a1a;gap:8px;flex-shrink:0}
#framePanel .fp-head span{font-size:12px;color:#666;flex:1;font-variant-numeric:tabular-nums}
#framePanel .fp-close{background:none;border:none;color:#555;font-size:18px;cursor:pointer}
#framePanel .fp-close:hover{color:#e31e24}
#framePanel .fp-img-wrap{position:relative;flex:1;overflow:hidden;background:#000;
  display:flex;align-items:center;justify-content:center}
#framePanel .fp-img-wrap img{max-width:100%;max-height:100%;object-fit:contain}
.fp-prod-tag{position:absolute;transform:translate(-50%,-100%);pointer-events:auto;cursor:pointer}
.fp-prod-tag-inner{background:rgba(227,30,36,0.85);color:#fff;padding:3px 8px;
  border-radius:6px;font-size:10px;font-weight:600;white-space:nowrap;
  box-shadow:0 2px 8px rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.1)}
.fp-prod-tag-inner.high{background:rgba(76,175,80,0.85)}
.fp-prod-tag-inner.med{background:rgba(255,152,0,0.85)}

/* Nav in frame panel */
.fp-nav{display:flex;gap:6px;padding:8px 12px;background:#111;border-top:1px solid #1a1a1a;flex-shrink:0}
.fp-nav button{flex:1;padding:6px;border:1px solid #333;border-radius:6px;
  background:transparent;color:#888;cursor:pointer;font-family:inherit;font-size:12px}
.fp-nav button:hover{border-color:#e31e24;color:#e31e24}

/* Minimap */
#minimap{position:absolute;bottom:12px;left:12px;width:160px;height:160px;
  background:rgba(10,10,10,0.88);border:1px solid #282828;border-radius:10px;
  overflow:hidden;z-index:10;cursor:pointer}
#minimapCanvas{width:100%;height:100%;display:block}

/* Product info tooltip */
#tooltip{position:fixed;z-index:60;background:rgba(20,20,20,0.95);
  border:1px solid #333;border-radius:10px;padding:12px;display:none;
  backdrop-filter:blur(8px);min-width:200px;pointer-events:none}
#tooltip h4{font-size:13px;margin-bottom:3px}
#tooltip .meta{font-size:11px;color:#777}
#tooltip .konf-bar{height:3px;background:#222;border-radius:2px;margin-top:6px}
#tooltip .konf-fill{height:100%;border-radius:2px}

/* Walk mode HUD */
#walkHud{position:absolute;bottom:12px;left:50%;transform:translateX(-50%);
  z-index:10;display:none;background:rgba(10,10,10,0.8);border:1px solid #282828;
  border-radius:10px;padding:8px 16px;font-size:11px;color:#666;text-align:center}

/* Loading */
#loading{position:fixed;inset:0;background:#0a0a0a;z-index:200;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px}
@keyframes spin{to{transform:rotate(360deg)}}
.spinner{width:28px;height:28px;border:3px solid #222;border-top-color:#e31e24;
  border-radius:50%;animation:spin .8s linear infinite}
</style>
</head>
<body>
<div id="loading"><div class="spinner"></div><span style="color:#555;font-size:12px">Laddar 3D-vy...</span></div>
<div id="app">
  <div class="topbar">
    <a href="/viewer">← Tillbaka</a>
    <span class="topbar-title">Puls-AR 3D <span id="gångLabel" style="color:#888;font-weight:400"></span></span>
    <button class="mode-btn active" id="mOrbit" onclick="setMode('orbit')">Orbit</button>
    <button class="mode-btn" id="mWalk" onclick="setMode('walk')">Walk</button>
    <button class="mode-btn" id="mTop" onclick="setMode('top')">Topp</button>
    <div class="h-filter" title="Klipp bort tak / golv. Värdena är meter över golv-percentilen.">
      <label>Höjd</label>
      <input type="range" id="hMaxSlider" min="0.3" max="4.0" step="0.1" value="2.2">
      <span class="h-val" id="hMaxVal">2.2m</span>
    </div>
    <button class="mode-btn" id="mTakBort" onclick="toggleTak()" title="Visa/dölj tak">Tak av</button>
    <button class="mode-btn active" id="mMesh" onclick="setRender('mesh')" title="Visa LiDAR-mesh">Mesh</button>
    <button class="mode-btn" id="mPunkter" onclick="setRender('punkter')" title="Visa punktmoln">Punkter</button>
    <button class="mode-btn" id="mLive" onclick="toggleLivePos()" title="Visa live-position från iPhone (pollar var sekund)">Live</button>
    <span class="stat" id="statTxt"></span>
    <span class="stat" id="livePosTxt" style="color:#00aaff"></span>
  </div>
  <div class="main">
    <div id="canvasWrap">
      <div id="minimap"><canvas id="minimapCanvas" width="320" height="320"></canvas></div>
      <div id="walkHud">↑↓ Gå · ←→ Sväng · <b>Esc</b> Orbit</div>
    </div>
    <div id="framePanel">
      <div class="fp-head">
        <span id="fpTitle">Frame</span>
        <button class="fp-close" onclick="closeFrame()">×</button>
      </div>
      <div class="fp-img-wrap" id="fpImgWrap">
        <img id="fpImg" src="">
      </div>
      <div class="fp-nav">
        <button onclick="frameStep(-5)">← Bakåt</button>
        <button onclick="frameStep(5)">Framåt →</button>
      </div>
    </div>
  </div>
</div>
<div id="tooltip"><h4 id="ttN"></h4><div class="meta" id="ttM"></div><div class="konf-bar"><div class="konf-fill" id="ttK"></div></div></div>

<script>
// Three.js core + GLTFLoader. Försök lokal vendor först, fallback till CDN.
(function loadThree(){
  function load(src, ok, fail){
    const s=document.createElement('script');
    s.src=src; s.onload=ok; s.onerror=fail;
    document.head.appendChild(s);
  }
  function afterCore(){
    // GLTFLoader (för mesh.glb). Bara CDN — vi behöver inte vendor:a.
    const gltfUrls = [
      '/static/GLTFLoader.js',
      'https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js',
      'https://unpkg.com/three@0.128.0/examples/js/loaders/GLTFLoader.js'
    ];
    let i=0;
    function tryNext(){
      if (i>=gltfUrls.length){
        console.error('Kunde inte ladda GLTFLoader — mesh-vy kommer inte funka');
        window._threeReady && window._threeReady();
        return;
      }
      load(gltfUrls[i++], () => window._threeReady && window._threeReady(), tryNext);
    }
    tryNext();
  }
  load('/static/three.min.js', afterCore,
    () => load('https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js',
              afterCore,
              () => console.error('Kunde inte ladda Three.js')));
})();
window._threeReady = function(){
  if (window._threeStarted) return;
  if (typeof THREE === 'undefined') { console.error('THREE saknas vid _threeReady'); return; }
  window._threeStarted = true;
  init();
};
</script>
<script>
const API = window.location.origin;
// Vilken gång ska visas? ?gång=mjölk_gång — fallback hela_butiken
const gång = new URLSearchParams(window.location.search).get('gång') || 'hela_butiken';
document.getElementById('gångLabel').textContent = '· ' + gång;

let scene, cam, renderer, raycaster, mouse;
let positioner=[], produkter=[], frames=[];
let pathDots=[], prodMeshes=[];
let mode='orbit', walkIdx=0, selectedFrameIdx=-1;
let mmBounds={};

// Punktmoln-state — så vi kan ta bort/lägga till vid filterändring
let pointCloudMesh = null;
let pointCloudMeta = {y_floor:null, y_ceil:null, h_min:null, h_max:null};
let takBortkopplat = true;       // True = klipp tak
let userHMax = 2.2;              // användarens slider-värde (meter över golvet)
let pointCloudFetchToken = 0;    // för att avbryta gammal fetch

// Mesh-state (LiDAR mesh.glb)
let meshRoot = null;             // THREE.Group containing loaded mesh
let meshMaterials = [];          // alla material som ska ha clipping
let meshClippingPlane = null;    // höjd-clipping
let renderMode = 'mesh';         // 'mesh' | 'punkter' | 'båda'

// Live-position state (rapporterad av iOS-app eller web-test)
let livePosMesh=null, livePosArrow=null, livePosLastT=0;

// Orbit state
let orb = {r:12, phi:Math.PI/3.5, theta:0};
let tgt = null; // skapas i init() när THREE finns
let drag=false, rDrag=false, prev={x:0,y:0}, clickT=0, clickP={x:0,y:0};

// Highlighted
let highlightedDot = null;

// ── INIT ──
async function init(){
  // Skapa Three-objekt nu när THREE finns
  raycaster = new THREE.Raycaster();
  mouse = new THREE.Vector2();
  tgt = new THREE.Vector3();
  // Scene
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x080808);
  scene.fog = new THREE.FogExp2(0x080808, 0.04);

  cam = new THREE.PerspectiveCamera(55, 1, 0.05, 150);
  renderer = new THREE.WebGLRenderer({antialias:true, alpha:false});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.localClippingEnabled = true;
  renderer.shadowMap.enabled = false;
  document.getElementById('canvasWrap').prepend(renderer.domElement);
  onResize();

  // Lights
  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const dl = new THREE.DirectionalLight(0xffffff, 0.3);
  dl.position.set(8,15,8); scene.add(dl);
  const hl = new THREE.HemisphereLight(0x222244, 0x111111, 0.3);
  scene.add(hl);

  // Floor
  const floorGeo = new THREE.PlaneGeometry(80,80);
  const floorMat = new THREE.MeshStandardMaterial({color:0x0c0c0c, roughness:0.9, metalness:0.1});
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI/2; floor.position.y = -0.01;
  scene.add(floor);

  // Grid
  const grid = new THREE.GridHelper(80, 80, 0x161616, 0x101010);
  scene.add(grid);

  // Data: positioner + frames + batch-produkter från viewer/data
  try{
    const r = await fetch(`${API}/viewer/data/${encodeURIComponent(gång)}`);
    const d = await r.json();
    positioner=d.positioner||[]; produkter=d.produkter||[]; frames=d.frames||[];
  }catch(e){console.error('viewer/data:',e)}

  // Live-extraherade produkter — slå ihop med batch
  // Schema: {visningsnamn, x, y, z, säkerhet, ...} (från produkt_extraktion.py)
  // Mappar säkerhet → konfidens så färgkodningen funkar
  try{
    const r2 = await fetch(`${API}/vps/karta/${encodeURIComponent(gång)}/produkter`);
    if(r2.ok){
      const d2 = await r2.json();
      const liveProd = (d2.produkter||[]).map(p => {
        const sak = (p.säkerhet||'').toLowerCase();
        const konf = sak==='hög' ? 0.9 : sak==='medium' ? 0.6 : sak==='låg' ? 0.3 : (p.konfidens||0.5);
        return Object.assign({konfidens: konf, källa: 'live'}, p);
      });
      produkter = produkter.concat(liveProd);
    }
  }catch(e){console.error('live produkter:',e)}

  buildPath();
  buildProducts();
  // Default: visa LiDAR-mesh (snyggast). Punktmoln laddas lazily om man togglar.
  if (renderMode === 'mesh' || renderMode === 'båda'){
    await buildMesh();
  }
  if (renderMode === 'punkter' || renderMode === 'båda'){
    await buildPointCloud();
  }
  centerCam();
  drawMinimap();

  document.getElementById('loading').style.display='none';
  document.getElementById('statTxt').textContent=
    `${positioner.length} pos · ${produkter.length} prod · ${frames.length} frames`;

  setupEvents();
  animate();

  // Live-position pollas BARA när användaren slår på det via knappen
  // i topbar — undviker spam-loggar när ingen iPhone rapporterar in.
}

let livePosTimer = null;
function toggleLivePos(){
  const btn = document.getElementById('mLive');
  if (livePosTimer){
    clearInterval(livePosTimer); livePosTimer = null;
    if(livePosMesh){scene.remove(livePosMesh); livePosMesh=null}
    if(livePosArrow){scene.remove(livePosArrow); livePosArrow=null}
    document.getElementById('livePosTxt').textContent='';
    btn.classList.remove('active');
  } else {
    pollLivePos();
    livePosTimer = setInterval(pollLivePos, 1000);
    btn.classList.add('active');
  }
}

// ── LIVE POSITION ──
async function pollLivePos(){
  try{
    const r = await fetch(`${API}/vps/karta/${encodeURIComponent(gång)}/lokalisering-senaste`);
    if(!r.ok){
      // Ingen färsk position — ta bort dot om den finns
      if(livePosMesh){scene.remove(livePosMesh); livePosMesh=null}
      if(livePosArrow){scene.remove(livePosArrow); livePosArrow=null}
      document.getElementById('livePosTxt').textContent='';
      return;
    }
    const d = await r.json();
    if(typeof d.x !== 'number') return;

    const x=d.x, y=(typeof d.y==='number'?d.y:1.5), z=d.z, yaw=(d.yaw||0);

    if(!livePosMesh){
      // Skapa blå sfär + glow + beam ner till golvet
      const geo=new THREE.SphereGeometry(0.18,18,14);
      const mat=new THREE.MeshPhongMaterial({color:0x00aaff,emissive:0x00aaff,
        emissiveIntensity:0.7,transparent:true,opacity:0.95});
      livePosMesh=new THREE.Mesh(geo,mat);

      const glowGeo=new THREE.SphereGeometry(0.32,14,10);
      const glowMat=new THREE.MeshBasicMaterial({color:0x00aaff,transparent:true,opacity:0.18});
      livePosMesh.add(new THREE.Mesh(glowGeo,glowMat));

      // Riktningspil
      const arrowDir=new THREE.Vector3(Math.sin(yaw),0,Math.cos(yaw));
      livePosArrow=new THREE.ArrowHelper(arrowDir, new THREE.Vector3(x,y,z), 0.6, 0x00aaff, 0.18, 0.12);
      scene.add(livePosArrow);

      scene.add(livePosMesh);
    }
    livePosMesh.position.set(x,y,z);
    if(livePosArrow){
      livePosArrow.position.set(x,y,z);
      livePosArrow.setDirection(new THREE.Vector3(Math.sin(yaw),0,Math.cos(yaw)));
    }
    livePosLastT=d.t||(Date.now()/1000);
    const ageS=(Date.now()/1000 - livePosLastT).toFixed(1);
    document.getElementById('livePosTxt').textContent=
      `📍 (${x.toFixed(2)}, ${z.toFixed(2)}) · ${ageS}s`;
  }catch(e){/* tyst */}
}

// ── PATH ──
function buildPath(){
  const sess={};const cols=[0x2196F3,0xFF9800,0x9C27B0,0x4CAF50,0x00BCD4,0xE91E63];
  let ci=0;
  for(const p of positioner){const s=p.session||'d';if(!sess[s])sess[s]={c:cols[ci++%6],pts:[]};sess[s].pts.push(p)}

  // Lines per session
  for(const[,d]of Object.entries(sess)){
    if(d.pts.length<2)continue;
    const pts=d.pts.map(p=>new THREE.Vector3(p.x||0,0.02,p.z||0));
    const geo=new THREE.BufferGeometry().setFromPoints(pts);
    const mat=new THREE.LineBasicMaterial({color:d.c,transparent:true,opacity:0.5});
    scene.add(new THREE.Line(geo,mat));

    // Glowing tube on floor
    const tubePts=d.pts.filter((_,i)=>i%3===0).map(p=>new THREE.Vector3(p.x||0,0.01,p.z||0));
    if(tubePts.length>1){
      try{
        const curve=new THREE.CatmullRomCurve3(tubePts);
        const tubeGeo=new THREE.TubeGeometry(curve, tubePts.length*2, 0.03, 4, false);
        const tubeMat=new THREE.MeshBasicMaterial({color:d.c,transparent:true,opacity:0.25});
        scene.add(new THREE.Mesh(tubeGeo,tubeMat));
      }catch(e){}
    }
  }

  // Clickable dots every 5th position
  const dotGeo=new THREE.SphereGeometry(0.04,8,8);
  for(let i=0;i<positioner.length;i+=5){
    const p=positioner[i];
    const mat=new THREE.MeshBasicMaterial({color:0x444444});
    const dot=new THREE.Mesh(dotGeo,mat);
    dot.position.set(p.x||0,0.04,p.z||0);
    dot.userData={type:'dot',index:i};
    scene.add(dot);
    pathDots.push(dot);
  }
}

// ── PRODUCTS ──
function buildProducts(){
  for(const prod of produkter){
    const k=prod.konfidens||0;
    const manual=prod.manuellt_korrigerad;
    const col=manual?0x2196F3:k>0.7?0x4CAF50:k>0.4?0xFF9800:0xf44336;

    // Sphere
    const geo=new THREE.SphereGeometry(0.1,16,12);
    const mat=new THREE.MeshPhongMaterial({color:col,emissive:col,emissiveIntensity:0.35,
      transparent:true,opacity:0.9});
    const mesh=new THREE.Mesh(geo,mat);
    mesh.position.set(prod.x||0,prod.y||1.2,prod.z||0);
    mesh.userData={type:'product',product:prod};
    scene.add(mesh); prodMeshes.push(mesh);

    // Outer glow sphere
    const glowGeo=new THREE.SphereGeometry(0.16,12,8);
    const glowMat=new THREE.MeshBasicMaterial({color:col,transparent:true,opacity:0.08});
    const glow=new THREE.Mesh(glowGeo,glowMat);
    glow.position.copy(mesh.position);
    scene.add(glow);

    // Beam from floor
    const beamGeo=new THREE.CylinderGeometry(0.005,0.005,(prod.y||1.2),4);
    const beamMat=new THREE.MeshBasicMaterial({color:col,transparent:true,opacity:0.15});
    const beam=new THREE.Mesh(beamGeo,beamMat);
    beam.position.set(prod.x||0,(prod.y||1.2)/2,prod.z||0);
    scene.add(beam);

    // Floor ring
    const ringGeo=new THREE.RingGeometry(0.12,0.18,20);
    const ringMat=new THREE.MeshBasicMaterial({color:col,side:THREE.DoubleSide,transparent:true,opacity:0.2});
    const ring=new THREE.Mesh(ringGeo,ringMat);
    ring.position.set(prod.x||0,0.01,prod.z||0);
    ring.rotation.x=-Math.PI/2;
    scene.add(ring);

    // Label sprite
    const label=makeLabel(prod.visningsnamn||'?',col);
    label.position.set(prod.x||0,(prod.y||1.2)+0.2,prod.z||0);
    scene.add(label);
  }
}

function makeLabel(text,color){
  const c=document.createElement('canvas');const ctx=c.getContext('2d');
  c.width=512;c.height=56;
  ctx.fillStyle='rgba(8,8,8,0.82)';
  ctx.beginPath();ctx.roundRect(0,0,512,56,10);ctx.fill();
  ctx.strokeStyle='#'+color.toString(16).padStart(6,'0');
  ctx.lineWidth=2;ctx.beginPath();ctx.roundRect(1,1,510,54,10);ctx.stroke();
  ctx.fillStyle='#ddd';ctx.font='bold 24px -apple-system,sans-serif';
  ctx.textAlign='center';ctx.textBaseline='middle';
  let t=text;if(ctx.measureText(t).width>490){while(ctx.measureText(t+'…').width>490&&t.length>3)t=t.slice(0,-1);t+='…'}
  ctx.fillText(t,256,28);
  const tex=new THREE.CanvasTexture(c);
  const mat=new THREE.SpriteMaterial({map:tex,transparent:true,depthTest:false});
  const s=new THREE.Sprite(mat);s.scale.set(1.8,0.2,1);
  return s;
}

// ── MESH (LiDAR mesh.glb) ──
async function buildMesh(){
  if (typeof THREE.GLTFLoader === 'undefined'){
    console.warn('GLTFLoader saknas — kan inte ladda mesh');
    return;
  }
  removeMesh();
  return new Promise((resolve) => {
    const loader = new THREE.GLTFLoader();
    loader.load(`${API}/viewer/mesh?karta=${encodeURIComponent(gång)}`,
      (gltf) => {
        meshRoot = gltf.scene || gltf.scenes[0];
        meshMaterials = [];

        // Beräkna bounding box för att få y_floor/y_ceil
        const box = new THREE.Box3().setFromObject(meshRoot);
        if (box.isEmpty()){
          console.warn('Mesh bounding box är tom');
          resolve(); return;
        }
        // Spara meta — överskrivs INTE om pointcloud redan satte dem
        if (pointCloudMeta.y_floor == null) pointCloudMeta.y_floor = box.min.y;
        if (pointCloudMeta.y_ceil == null) pointCloudMeta.y_ceil = box.max.y;

        // Clipping plane (kapas vid h_max). Plan-normalen pekar nedåt så
        // allt över ytan klipps bort. constant = h_max.
        meshClippingPlane = new THREE.Plane(new THREE.Vector3(0,-1,0), 0);
        updateClippingPlane();

        // Sätt upp material med clipping + bra defaults
        meshRoot.traverse((obj) => {
          if (obj.isMesh){
            // Original-materialen kan vara MeshStandardMaterial från RoomPlan.
            // Kopiera och slå på clipping.
            const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
            const newMats = mats.map(m => {
              const nm = m.clone();
              nm.clippingPlanes = [meshClippingPlane];
              nm.side = THREE.DoubleSide;
              // Om materialet saknar färg/textur, ge den en ljus default
              if (!nm.map && (!nm.color || nm.color.getHex() === 0xffffff)){
                nm.color = new THREE.Color(0xa8b8c0);
              }
              if (nm.metalness !== undefined) nm.metalness = 0.05;
              if (nm.roughness !== undefined) nm.roughness = 0.85;
              meshMaterials.push(nm);
              return nm;
            });
            obj.material = Array.isArray(obj.material) ? newMats : newMats[0];
            obj.castShadow = false;
            obj.receiveShadow = false;
          }
        });

        scene.add(meshRoot);
        applyRenderMode();
        console.log('Mesh laddad:', meshMaterials.length, 'materials, bbox y=',
                    box.min.y.toFixed(2),'→',box.max.y.toFixed(2));
        resolve();
      },
      undefined,
      (err) => { console.error('GLTFLoader fel:', err); resolve(); }
    );
  });
}

function removeMesh(){
  if(!meshRoot) return;
  scene.remove(meshRoot);
  meshRoot.traverse((obj) => {
    if (obj.isMesh){
      if (obj.geometry) obj.geometry.dispose();
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      mats.forEach(m => m && m.dispose && m.dispose());
    }
  });
  meshRoot = null;
  meshMaterials = [];
  meshClippingPlane = null;
}

function updateClippingPlane(){
  if (!meshClippingPlane) return;
  if (takBortkopplat && pointCloudMeta.y_floor != null){
    const h = pointCloudMeta.y_floor + userHMax;
    // Plane.constant betyder: planet är y = constant när normalen är (0,-1,0)
    // Punkter där dot(n, p) + constant > 0 hålls. n=(0,-1,0) → -p.y + c > 0 → p.y < c
    // Så vi sätter constant = h.
    meshClippingPlane.constant = h;
  } else {
    // Inaktivera clipping genom att sätta constant väldigt högt
    meshClippingPlane.constant = 1e6;
  }
}

function setRender(m){
  renderMode = m;
  document.getElementById('mMesh').classList.toggle('active', m==='mesh' || m==='båda');
  document.getElementById('mPunkter').classList.toggle('active', m==='punkter' || m==='båda');
  applyRenderMode();
}

function applyRenderMode(){
  const showMesh = (renderMode === 'mesh' || renderMode === 'båda');
  const showPts = (renderMode === 'punkter' || renderMode === 'båda');
  if (meshRoot) meshRoot.visible = showMesh;
  if (pointCloudMesh) pointCloudMesh.visible = showPts;
  // Lazy-load om inte laddat ännu
  if (showPts && !pointCloudMesh) buildPointCloud();
  if (showMesh && !meshRoot) buildMesh();
}

// ── POINT CLOUD ──
function pointCloudURL(){
  // Bygg query: alltid auto_floor=true. Ceiling kan klippas av med h_max om tak ska bort.
  const params = new URLSearchParams({
    karta: gång,
    max_points: '60000',
    auto_floor: 'true',
  });
  if (takBortkopplat){
    // h_max i absoluta y: floor + userHMax
    if (pointCloudMeta.y_floor != null){
      params.set('höjd_max', String(pointCloudMeta.y_floor + userHMax));
    }
    // Backenden klipper tak default — vi behöver inte sätta ceiling_offset
  } else {
    // Visa allt: stäng av auto för h_max genom att skicka stort tal
    params.set('ceiling_offset', '-2.0');
  }
  return `${API}/viewer/pointcloud?` + params.toString();
}

async function buildPointCloud(){
  const myToken = ++pointCloudFetchToken;
  try{
    const r = await fetch(pointCloudURL());
    const d = await r.json();
    if (myToken !== pointCloudFetchToken) return; // newer fetch i flygande
    if(!d.punkter||!d.punkter.length){
      removePointCloud();
      pointCloudMeta = {y_floor:d.y_floor, y_ceil:d.y_ceil, h_min:d.h_min, h_max:d.h_max};
      return;
    }
    pointCloudMeta = {y_floor:d.y_floor, y_ceil:d.y_ceil, h_min:d.h_min, h_max:d.h_max};
    const pts=d.punkter;
    const geo=new THREE.BufferGeometry();
    const positions=new Float32Array(pts.length*3);
    const colors=new Float32Array(pts.length*3);
    // Använd faktiska floor/ceil från servern för stabil färggradient
    const minY = (d.y_floor!=null)?d.y_floor : Math.min(...pts.map(p=>p[1]));
    const maxY = (d.h_max!=null)?d.h_max : (d.y_ceil!=null?d.y_ceil:Math.max(...pts.map(p=>p[1])));
    const rangeY=Math.max(0.5, maxY-minY);
    for(let i=0;i<pts.length;i++){
      positions[i*3]=pts[i][0];
      positions[i*3+1]=pts[i][1];
      positions[i*3+2]=pts[i][2];
      // Färggradient: ljust grågrönt på golv-nivå → gult/orange högre upp
      // Vi lättar mörkret jämfört med tidigare för att efterlikna 3dviewer.net
      let t=(pts[i][1]-minY)/rangeY;
      if (t<0) t=0; if (t>1) t=1;
      if(t<0.35){
        // golvet: dimmig blå-grön
        const s=t/0.35;
        colors[i*3]=0.30+s*0.10;
        colors[i*3+1]=0.45+s*0.20;
        colors[i*3+2]=0.55+s*0.10;
      } else if(t<0.75){
        // mellanhöjd: ljusgrön/teal
        const s=(t-0.35)/0.40;
        colors[i*3]=0.40+s*0.30;
        colors[i*3+1]=0.65+s*0.20;
        colors[i*3+2]=0.65-s*0.20;
      } else {
        // toppen: varm orange
        const s=(t-0.75)/0.25;
        colors[i*3]=0.70+s*0.25;
        colors[i*3+1]=0.85-s*0.20;
        colors[i*3+2]=0.45-s*0.30;
      }
    }
    geo.setAttribute('position',new THREE.BufferAttribute(positions,3));
    geo.setAttribute('color',new THREE.BufferAttribute(colors,3));
    // PointsMaterial: större punkter, hög opacitet, ingen size-attenuation = jämn dot-storlek
    const mat=new THREE.PointsMaterial({
      size: (mode==='top') ? 2.4 : 2.0,
      vertexColors: true,
      transparent: true,
      opacity: 0.92,
      sizeAttenuation: false,   // konstant storlek i px → ser fyllig ut
      depthWrite: true,
    });
    removePointCloud();
    pointCloudMesh = new THREE.Points(geo, mat);
    scene.add(pointCloudMesh);
    console.log('Punktmoln:', pts.length, 'punkter, y_floor=',d.y_floor,'h_max=',d.h_max);
  }catch(e){console.error('Pointcloud:',e)}
}

function removePointCloud(){
  if(!pointCloudMesh) return;
  scene.remove(pointCloudMesh);
  if (pointCloudMesh.geometry) pointCloudMesh.geometry.dispose();
  if (pointCloudMesh.material) pointCloudMesh.material.dispose();
  pointCloudMesh = null;
}

// Debounced refetch när slider ändras
let _hMaxDebounceTimer = null;
function onHMaxChange(val){
  userHMax = parseFloat(val);
  document.getElementById('hMaxVal').textContent = userHMax.toFixed(1)+'m';
  // Mesh: clipping plane uppdateras direkt (no fetch)
  updateClippingPlane();
  // Punktmoln: debounced refetch
  if(_hMaxDebounceTimer) clearTimeout(_hMaxDebounceTimer);
  _hMaxDebounceTimer = setTimeout(()=>{
    if (renderMode === 'punkter' || renderMode === 'båda') buildPointCloud();
  }, 250);
}

function toggleTak(){
  takBortkopplat = !takBortkopplat;
  const btn = document.getElementById('mTakBort');
  btn.textContent = takBortkopplat ? 'Tak av' : 'Tak på';
  btn.classList.toggle('active', !takBortkopplat);
  updateClippingPlane();
  if (renderMode === 'punkter' || renderMode === 'båda') buildPointCloud();
}

// ── CAMERA ──
function centerCam(){
  if(!positioner.length)return;
  let sx=0,sz=0;
  for(const p of positioner){sx+=(p.x||0);sz+=(p.z||0)}
  tgt.set(sx/positioner.length,0,sz/positioner.length);
  updateOrbit();
}
function updateOrbit(){
  cam.position.set(
    tgt.x+orb.r*Math.sin(orb.phi)*Math.cos(orb.theta),
    tgt.y+orb.r*Math.cos(orb.phi),
    tgt.z+orb.r*Math.sin(orb.phi)*Math.sin(orb.theta));
  cam.lookAt(tgt);
}
function flyTo(pos,look,dur=0.4){
  const sp=cam.position.clone(),st=tgt.clone();
  const ep=pos.clone(),et=look.clone();
  let t=0;
  function step(){t+=0.016/dur;if(t>=1){cam.position.copy(ep);tgt.copy(et);cam.lookAt(tgt);return}
    const e=t*t*(3-2*t);cam.position.lerpVectors(sp,ep,e);tgt.lerpVectors(st,et,e);
    cam.lookAt(tgt);requestAnimationFrame(step)}
  step();
}

// ── EVENTS ──
function setupEvents(){
  const cv=renderer.domElement;
  cv.addEventListener('mousedown',e=>{drag=true;rDrag=e.button===2||e.shiftKey;
    prev={x:e.clientX,y:e.clientY};clickT=Date.now();clickP={x:e.clientX,y:e.clientY}});
  cv.addEventListener('mousemove',e=>{
    // Tooltip on hover
    updateTooltip(e);
    if(!drag)return;
    const dx=e.clientX-prev.x,dy=e.clientY-prev.y;
    if(mode==='orbit'){
      if(rDrag){const s=orb.r*0.002;
        const r=new THREE.Vector3();const u=new THREE.Vector3(0,1,0);
        r.crossVectors(cam.getWorldDirection(new THREE.Vector3()),u).normalize();
        tgt.add(r.multiplyScalar(-dx*s));tgt.y+=dy*s;
      }else{orb.theta-=dx*0.005;
        orb.phi=Math.max(0.1,Math.min(Math.PI*0.49,orb.phi-dy*0.005))}
      updateOrbit();
    }else if(mode==='walk'){
      // Look around
      const p=positioner[walkIdx];if(!p)return;
      const a=Math.atan2(tgt.x-cam.position.x,tgt.z-cam.position.z)-dx*0.003;
      tgt.set(cam.position.x+Math.sin(a)*3,cam.position.y,cam.position.z+Math.cos(a)*3);
      cam.lookAt(tgt);
    }
    prev={x:e.clientX,y:e.clientY}});
  cv.addEventListener('mouseup',e=>{drag=false;
    if(Date.now()-clickT<250&&Math.abs(e.clientX-clickP.x)+Math.abs(e.clientY-clickP.y)<8)
      handleClick(e)});
  cv.addEventListener('wheel',e=>{e.preventDefault();if(mode==='orbit'){
    orb.r*=e.deltaY>0?1.07:0.93;orb.r=Math.max(1,Math.min(60,orb.r));
    updateOrbit()}},{passive:false});
  cv.addEventListener('contextmenu',e=>e.preventDefault());

  document.addEventListener('keydown',e=>{
    if(mode==='walk'){
      switch(e.key){
        case'ArrowUp':case'w':walkStep(5);e.preventDefault();break;
        case'ArrowDown':case's':walkStep(-5);e.preventDefault();break;
        case'ArrowRight':case'd':walkStep(2);e.preventDefault();break;
        case'ArrowLeft':case'a':walkStep(-2);e.preventDefault();break;
        case'Escape':setMode('orbit');break}
    }else{
      if(e.key==='w')setMode('walk');
      if(e.key==='f')centerCam();
    }
  });

  // Höjd-slider
  const hMaxEl = document.getElementById('hMaxSlider');
  if (hMaxEl){
    hMaxEl.addEventListener('input', e => onHMaxChange(e.target.value));
    document.getElementById('hMaxVal').textContent = parseFloat(hMaxEl.value).toFixed(1)+'m';
    userHMax = parseFloat(hMaxEl.value);
  }

  // Minimap click
  document.getElementById('minimapCanvas').addEventListener('click',function(e){
    const rect=this.getBoundingClientRect();
    const sx=(e.clientX-rect.left)/rect.width*320;
    const sy=(e.clientY-rect.top)/rect.height*320;
    let best=0,bd=Infinity;
    for(let i=0;i<positioner.length;i++){const p=positioner[i];
      const px=((p.x||0)-mmBounds.minX)/mmBounds.rX*300+10;
      const py=((p.z||0)-mmBounds.minZ)/mmBounds.rZ*300+10;
      const d=(sx-px)**2+(sy-py)**2;if(d<bd){bd=d;best=i}}
    if(mode==='walk')goWalk(best);
    else{const p=positioner[best];tgt.set(p.x||0,0,p.z||0);updateOrbit();showFrame(best)}
  });

  window.addEventListener('resize',onResize);
}

function handleClick(e){
  const rect=renderer.domElement.getBoundingClientRect();
  mouse.x=((e.clientX-rect.left)/rect.width)*2-1;
  mouse.y=-((e.clientY-rect.top)/rect.height)*2+1;
  raycaster.setFromCamera(mouse,cam);

  // Products
  const ph=raycaster.intersectObjects(prodMeshes);
  if(ph.length>0){const prod=ph[0].object.userData.product;
    showTooltipFixed(prod,e.clientX,e.clientY);
    // Fly near
    if(mode==='orbit'){orb.r=4;tgt.set(prod.x||0,0,prod.z||0);updateOrbit()}
    return}

  // Path dots
  const dh=raycaster.intersectObjects(pathDots);
  if(dh.length>0){const idx=dh[0].object.userData.index;
    showFrame(idx);
    if(mode==='walk')goWalk(idx);
    else{const p=positioner[idx];
      flyTo(new THREE.Vector3((p.x||0)+2,2,(p.z||0)+2),new THREE.Vector3(p.x||0,0,p.z||0))}
    return}

  // Empty click — close panels
  closeFrame();
  document.getElementById('tooltip').style.display='none';
}

// ── TOOLTIP ──
function updateTooltip(e){
  const rect=renderer.domElement.getBoundingClientRect();
  mouse.x=((e.clientX-rect.left)/rect.width)*2-1;
  mouse.y=-((e.clientY-rect.top)/rect.height)*2+1;
  raycaster.setFromCamera(mouse,cam);
  const ph=raycaster.intersectObjects(prodMeshes);
  if(ph.length>0){
    const prod=ph[0].object.userData.product;
    showTooltipFixed(prod,e.clientX,e.clientY);
    renderer.domElement.style.cursor='pointer';
  }else{
    const dh=raycaster.intersectObjects(pathDots);
    renderer.domElement.style.cursor=dh.length>0?'pointer':'grab';
    if(!dh.length)document.getElementById('tooltip').style.display='none';
  }
}
function showTooltipFixed(prod,x,y){
  const tt=document.getElementById('tooltip');
  document.getElementById('ttN').textContent=prod.visningsnamn||'?';
  let m=[];if(prod.varumarke)m.push(prod.varumarke);if(prod.kategori)m.push(prod.kategori);
  m.push(`${((prod.konfidens||0)*100).toFixed(0)}%`);
  document.getElementById('ttM').textContent=m.join(' · ');
  const k=(prod.konfidens||0)*100;const kf=document.getElementById('ttK');
  kf.style.width=k+'%';kf.style.background=k>70?'#4CAF50':k>40?'#FF9800':'#f44336';
  tt.style.display='block';tt.style.left=(x+16)+'px';tt.style.top=(y-10)+'px';
}

// ── FRAME PANEL ──
function showFrame(posIdx){
  if(posIdx<0||posIdx>=positioner.length)return;
  selectedFrameIdx=posIdx;
  const p=positioner[posIdx];
  const fid=p.frame;if(fid===undefined)return;

  const panel=document.getElementById('framePanel');
  panel.classList.add('open');
  document.getElementById('fpTitle').textContent=`Frame ${fid} — (${(p.x||0).toFixed(2)}, ${(p.z||0).toFixed(2)})m`;
  document.getElementById('fpImg').src=`${API}/viewer/frame/${encodeURIComponent(gång)}/${fid}`;

  // Project products onto frame
  setTimeout(()=>projectOnFrame(posIdx),100);
  onResize();

  // Highlight dot in 3D
  if(highlightedDot)highlightedDot.material.color.setHex(0x444444);
  const dotIdx=Math.floor(posIdx/5);
  if(pathDots[dotIdx]){highlightedDot=pathDots[dotIdx];highlightedDot.material.color.setHex(0xe31e24)}

  drawMinimap();
}
function closeFrame(){
  document.getElementById('framePanel').classList.remove('open');
  selectedFrameIdx=-1;
  if(highlightedDot){highlightedDot.material.color.setHex(0x444444);highlightedDot=null}
  setTimeout(onResize,350);
}
function frameStep(step){
  if(selectedFrameIdx<0)return;
  showFrame(Math.max(0,Math.min(positioner.length-1,selectedFrameIdx+step)));
}

function projectOnFrame(posIdx){
  const wrap=document.getElementById('fpImgWrap');
  wrap.querySelectorAll('.fp-prod-tag').forEach(t=>t.remove());
  const c=positioner[posIdx];if(!c)return;
  const fx=c.fx||1000,fy=c.fy||1000,cx=c.cx||960,cy=c.cy||540;
  const cX=c.x||0,cY=c.y||0,cZ=c.z||0,rY=c.rot_y||0;

  for(const prod of produkter){
    const dx=(prod.x||0)-cX,dy=(prod.y||1.2)-cY,dz=(prod.z||0)-cZ;
    const dist=Math.sqrt(dx*dx+dz*dz);if(dist>6)continue;
    const cosR=Math.cos(-rY),sinR=Math.sin(-rY);
    const lx=dx*cosR-dz*sinR,lz=dx*sinR+dz*cosR;
    if(lz<=0.2)continue;
    const px=fx*lx/lz+cx,py=fy*(-dy)/lz+cy;
    const sX=px/(cx*2)*100,sY=py/(cy*2)*100;
    if(sX<2||sX>98||sY<2||sY>98)continue;
    const k=prod.konfidens||0;
    const klass=k>0.7?'high':k>0.4?'med':'';
    const tag=document.createElement('div');tag.className='fp-prod-tag';
    tag.style.left=sX+'%';tag.style.top=sY+'%';
    tag.innerHTML=`<div class="fp-prod-tag-inner ${klass}">${prod.visningsnamn||'?'}</div>`;
    wrap.appendChild(tag);
  }
}

// ── WALK / TOP / ORBIT MODE ──
function setMode(m){
  mode=m;
  document.getElementById('mOrbit').classList.toggle('active',m==='orbit');
  document.getElementById('mWalk').classList.toggle('active',m==='walk');
  const mTop=document.getElementById('mTop'); if(mTop) mTop.classList.toggle('active',m==='top');
  document.getElementById('walkHud').style.display=m==='walk'?'block':'none';
  if(m==='walk'){
    // Start at nearest pos to current target
    let best=0,bd=Infinity;
    for(let i=0;i<positioner.length;i++){const p=positioner[i];
      const d=Math.sqrt((tgt.x-(p.x||0))**2+(tgt.z-(p.z||0))**2);
      if(d<bd){bd=d;best=i}}
    goWalk(best);
  } else if (m==='top'){
    // Topp-vy: kameran rakt ovanifrån, ser ner i butiken
    // Beräkna bounds
    let minX=Infinity,maxX=-Infinity,minZ=Infinity,maxZ=-Infinity;
    for(const p of positioner){
      minX=Math.min(minX,p.x||0); maxX=Math.max(maxX,p.x||0);
      minZ=Math.min(minZ,p.z||0); maxZ=Math.max(maxZ,p.z||0);
    }
    if(!isFinite(minX)){minX=-5;maxX=5;minZ=-5;maxZ=5;}
    const cx=(minX+maxX)/2, cz=(minZ+maxZ)/2;
    const radius=Math.max(maxX-minX, maxZ-minZ)*0.7 + 4;
    tgt.set(cx,0,cz);
    cam.position.set(cx, radius, cz+0.001); // litet z-offset så lookAt funkar
    cam.lookAt(tgt);
    // Justera orbit-state så vidare drag fungerar
    orb.r = radius; orb.phi = 0.001; orb.theta = Math.PI/2;
    // Större punkter i topp-vyn
    if(pointCloudMesh && pointCloudMesh.material){
      pointCloudMesh.material.size = 2.6;
      pointCloudMesh.material.needsUpdate = true;
    }
  } else {
    // Orbit
    if(pointCloudMesh && pointCloudMesh.material){
      pointCloudMesh.material.size = 2.0;
      pointCloudMesh.material.needsUpdate = true;
    }
    centerCam();
  }
}
function goWalk(idx){
  idx=Math.max(0,Math.min(positioner.length-1,idx));
  walkIdx=idx;
  const p=positioner[idx];
  const x=p.x||0,y=(p.y||0)+1.6,z=p.z||0;
  // Look direction
  let lx=x,lz=z+1;
  if(idx<positioner.length-1){const n=positioner[idx+1];lx=n.x||0;lz=n.z||0}
  cam.position.set(x,y,z);
  tgt.set(lx,y-0.3,lz);cam.lookAt(tgt);
  showFrame(idx);
  drawMinimap();
}
function walkStep(s){goWalk(walkIdx+s)}

// ── MINIMAP ──
function drawMinimap(){
  const c=document.getElementById('minimapCanvas');const ctx=c.getContext('2d');
  const W=320,H=320;ctx.fillStyle='#0a0a0a';ctx.fillRect(0,0,W,H);
  if(!positioner.length)return;
  let minX=Infinity,maxX=-Infinity,minZ=Infinity,maxZ=-Infinity;
  for(const p of positioner){minX=Math.min(minX,p.x||0);maxX=Math.max(maxX,p.x||0);
    minZ=Math.min(minZ,p.z||0);maxZ=Math.max(maxZ,p.z||0)}
  for(const p of produkter){minX=Math.min(minX,p.x||0);maxX=Math.max(maxX,p.x||0);
    minZ=Math.min(minZ,p.z||0);maxZ=Math.max(maxZ,p.z||0)}
  const pad=1;minX-=pad;maxX+=pad;minZ-=pad;maxZ+=pad;
  mmBounds={minX,maxX,minZ,maxZ,rX:maxX-minX||1,rZ:maxZ-minZ||1};

  // Path
  const sess={};const cols=['#2196F3','#FF9800','#9C27B0','#4CAF50','#00BCD4'];let ci=0;
  for(const p of positioner){const s=p.session||'d';if(!sess[s])sess[s]={c:cols[ci++%5],p:[]};sess[s].p.push(p)}
  for(const[,d]of Object.entries(sess)){
    ctx.strokeStyle=d.c;ctx.lineWidth=1.5;ctx.globalAlpha=0.5;ctx.beginPath();
    for(let i=0;i<d.p.length;i++){const p=d.p[i];
      const sx=((p.x||0)-minX)/mmBounds.rX*300+10,sy=((p.z||0)-minZ)/mmBounds.rZ*300+10;
      i===0?ctx.moveTo(sx,sy):ctx.lineTo(sx,sy)}ctx.stroke()}
  ctx.globalAlpha=1;

  // Products
  for(const p of produkter){
    const sx=((p.x||0)-minX)/mmBounds.rX*300+10,sy=((p.z||0)-minZ)/mmBounds.rZ*300+10;
    const k=p.konfidens||0;ctx.fillStyle=k>0.7?'#4CAF50':k>0.4?'#FF9800':'#f44336';
    ctx.beginPath();ctx.arc(sx,sy,3,0,Math.PI*2);ctx.fill()}

  // Current position
  let curP=null;
  if(mode==='walk'&&walkIdx<positioner.length)curP=positioner[walkIdx];
  else if(selectedFrameIdx>=0&&selectedFrameIdx<positioner.length)curP=positioner[selectedFrameIdx];
  if(curP){
    const sx=((curP.x||0)-minX)/mmBounds.rX*300+10,sy=((curP.z||0)-minZ)/mmBounds.rZ*300+10;
    const g=ctx.createRadialGradient(sx,sy,0,sx,sy,12);
    g.addColorStop(0,'rgba(227,30,36,0.5)');g.addColorStop(1,'rgba(227,30,36,0)');
    ctx.fillStyle=g;ctx.beginPath();ctx.arc(sx,sy,12,0,Math.PI*2);ctx.fill();
    ctx.fillStyle='#e31e24';ctx.beginPath();ctx.arc(sx,sy,4,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle='#fff';ctx.lineWidth=1.5;ctx.stroke();
    // Direction
    const r=curP.rot_y||0;
    ctx.strokeStyle='#e31e24';ctx.lineWidth=2;ctx.beginPath();
    ctx.moveTo(sx,sy);ctx.lineTo(sx+Math.sin(r)*12,sy+Math.cos(r)*12);ctx.stroke();
    // FOV
    ctx.fillStyle='rgba(227,30,36,0.06)';ctx.beginPath();ctx.moveTo(sx,sy);
    ctx.lineTo(sx+Math.sin(r-0.5)*25,sy+Math.cos(r-0.5)*25);
    ctx.lineTo(sx+Math.sin(r+0.5)*25,sy+Math.cos(r+0.5)*25);ctx.closePath();ctx.fill();
  }
}

// ── ANIMATE ──
function animate(){
  requestAnimationFrame(animate);
  // Pulse products
  const t=Date.now()*0.002;
  for(let i=0;i<prodMeshes.length;i++){
    const s=1+Math.sin(t+i*0.7)*0.06;
    prodMeshes[i].scale.setScalar(s)}
  renderer.render(scene,cam);
}

function onResize(){
  const wrap=document.getElementById('canvasWrap');
  const w=wrap.clientWidth,h=wrap.clientHeight;
  cam.aspect=w/h;cam.updateProjectionMatrix();
  renderer.setSize(w,h);
}

// init() startas av _threeReady() i loader-scriptet ovan när Three.js har laddats.
// Om THREE råkar finnas redan (cachad), starta nu.
if (typeof THREE !== 'undefined' && !window._threeStarted){
  window._threeStarted = true;
  init();
}
</script>
</body>
</html>
"""