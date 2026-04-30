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
    <button class="mode-btn active" id="bMesh" onclick="toggleMesh()">Mesh</button>
    <button class="mode-btn active" id="bPoints" onclick="togglePoints()">Punkter</button>
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

<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const API = window.location.origin;
// Vilken gång ska visas? ?gång=mjölk_gång — fallback hela_butiken
const gång = new URLSearchParams(window.location.search).get('gång') || 'hela_butiken';
document.getElementById('gångLabel').textContent = '· ' + gång;

let scene, cam, renderer, raycaster = new THREE.Raycaster(), mouse = new THREE.Vector2();
let positioner=[], produkter=[], frames=[];
let pathDots=[], prodMeshes=[];
let mode='orbit', walkIdx=0, selectedFrameIdx=-1;
let mmBounds={};

// Live-position state (rapporterad av iOS-app eller web-test)
let livePosMesh=null, livePosArrow=null, livePosLastT=0;

// Mesh + punktmoln (för on/off)
let meshObj=null, pointsObj=null;

// Orbit state
let orb = {r:12, phi:Math.PI/3.5, theta:0};
let tgt = new THREE.Vector3();
let drag=false, rDrag=false, prev={x:0,y:0}, clickT=0, clickP={x:0,y:0};

// Highlighted
let highlightedDot = null;

// ── INIT ──
async function init(){
  // Scene
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x080808);
  scene.fog = new THREE.FogExp2(0x080808, 0.04);

  cam = new THREE.PerspectiveCamera(55, 1, 0.05, 150);
  renderer = new THREE.WebGLRenderer({antialias:true, alpha:false});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
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
  await buildPointCloud();
  await buildMesh();
  centerCam();
  drawMinimap();

  document.getElementById('loading').style.display='none';
  document.getElementById('statTxt').textContent=
    `${positioner.length} pos · ${produkter.length} prod · ${frames.length} frames`;

  setupEvents();
  animate();

  // Starta poll-loop för live-position (1 Hz)
  pollLivePos();
  setInterval(pollLivePos, 1000);
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

// ── POINT CLOUD ──
async function buildPointCloud(){
  try{
    const r=await fetch(`${API}/viewer/pointcloud?max_points=60000`);
    const d=await r.json();
    if(!d.punkter||!d.punkter.length)return;
    const pts=d.punkter;
    const geo=new THREE.BufferGeometry();
    const positions=new Float32Array(pts.length*3);
    const colors=new Float32Array(pts.length*3);
    let minY=Infinity,maxY=-Infinity;
    for(const p of pts){minY=Math.min(minY,p[1]);maxY=Math.max(maxY,p[1])}
    const rangeY=maxY-minY||1;
    for(let i=0;i<pts.length;i++){
      positions[i*3]=pts[i][0];
      positions[i*3+1]=pts[i][1];
      positions[i*3+2]=pts[i][2];
      const t=(pts[i][1]-minY)/rangeY;
      if(t<0.3){colors[i*3]=0.05+t*0.3;colors[i*3+1]=0.08+t*0.4;colors[i*3+2]=0.15+t*0.5}
      else if(t<0.7){const s=(t-0.3)/0.4;colors[i*3]=0.1+s*0.2;colors[i*3+1]=0.2+s*0.4;colors[i*3+2]=0.3+s*0.3}
      else{const s=(t-0.7)/0.3;colors[i*3]=0.3+s*0.5;colors[i*3+1]=0.6+s*0.3;colors[i*3+2]=0.6+s*0.2}
    }
    geo.setAttribute('position',new THREE.BufferAttribute(positions,3));
    geo.setAttribute('color',new THREE.BufferAttribute(colors,3));
    const mat=new THREE.PointsMaterial({size:0.02,vertexColors:true,transparent:true,opacity:0.6,sizeAttenuation:true,depthWrite:false});
    pointsObj = new THREE.Points(geo,mat);
    scene.add(pointsObj);
    console.log('Punktmoln:',pts.length,'punkter');
  }catch(e){console.error('Pointcloud:',e)}
}

// ── MESH (ARKit/RoomPlan triangulerad yta) ──
async function buildMesh(){
  try{
    const r=await fetch(`${API}/viewer/mesh/${encodeURIComponent(gång)}`);
    if(!r.ok){console.warn('Ingen mesh:',r.status);return;}
    const d=await r.json();
    if(!d.vertices||!d.vertices.length||!d.faces||!d.faces.length){
      console.warn('Tom mesh:',d.error||'');
      return;
    }

    const geo=new THREE.BufferGeometry();

    // Vertices → Float32Array
    const positions=new Float32Array(d.vertices.length*3);
    for(let i=0;i<d.vertices.length;i++){
      positions[i*3]=d.vertices[i][0];
      positions[i*3+1]=d.vertices[i][1];
      positions[i*3+2]=d.vertices[i][2];
    }
    geo.setAttribute('position',new THREE.BufferAttribute(positions,3));

    // Faces → index
    const indices=new Uint32Array(d.faces.length*3);
    for(let i=0;i<d.faces.length;i++){
      indices[i*3]=d.faces[i][0];
      indices[i*3+1]=d.faces[i][1];
      indices[i*3+2]=d.faces[i][2];
    }
    geo.setIndex(new THREE.BufferAttribute(indices,1));

    // Färgkodning per vertex baserat på face-klassifikation
    // ARKit: 0=none, 1=wall, 2=floor, 3=ceiling, 4=table, 5=seat, 6=window, 7=door
    const classColors={
      0:[0.50,0.50,0.52],
      1:[0.78,0.76,0.72],
      2:[0.45,0.32,0.22],
      3:[0.30,0.30,0.32],
      4:[0.60,0.42,0.25],
      5:[0.45,0.30,0.55],
      6:[0.55,0.75,0.95],
      7:[0.65,0.35,0.20],
    };
    const vertColors=new Float32Array(d.vertices.length*3);
    for(let i=0;i<d.vertices.length;i++){
      vertColors[i*3]=0.50; vertColors[i*3+1]=0.50; vertColors[i*3+2]=0.52;
    }
    if(d.classifications&&d.classifications.length===d.faces.length){
      for(let i=0;i<d.faces.length;i++){
        const cls=d.classifications[i]||0;
        const col=classColors[cls]||classColors[0];
        const f=d.faces[i];
        for(let j=0;j<3;j++){
          const vi=f[j];
          vertColors[vi*3]=col[0];
          vertColors[vi*3+1]=col[1];
          vertColors[vi*3+2]=col[2];
        }
      }
    }
    geo.setAttribute('color',new THREE.BufferAttribute(vertColors,3));
    geo.computeVertexNormals();

    const mat=new THREE.MeshStandardMaterial({
      vertexColors:true,
      roughness:0.85,
      metalness:0.05,
      transparent:true,
      opacity:0.9,
      side:THREE.DoubleSide,
      flatShading:false,
    });

    meshObj=new THREE.Mesh(geo,mat);
    scene.add(meshObj);
    console.log('Mesh:',d.antal_v,'verts,',d.antal_f,'faces');
  }catch(e){console.error('mesh:',e)}
}

function toggleMesh(){
  const btn=document.getElementById('bMesh');
  if(!meshObj){
    buildMesh().then(()=>{
      if(meshObj){meshObj.visible=true;btn.classList.add('active');}
    });
    return;
  }
  meshObj.visible=!meshObj.visible;
  btn.classList.toggle('active',meshObj.visible);
}

function togglePoints(){
  const btn=document.getElementById('bPoints');
  if(!pointsObj)return;
  pointsObj.visible=!pointsObj.visible;
  btn.classList.toggle('active',pointsObj.visible);
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

// ── WALK MODE ──
function setMode(m){
  mode=m;
  document.getElementById('mOrbit').classList.toggle('active',m==='orbit');
  document.getElementById('mWalk').classList.toggle('active',m==='walk');
  document.getElementById('walkHud').style.display=m==='walk'?'block':'none';
  if(m==='walk'){
    // Start at nearest pos to current target
    let best=0,bd=Infinity;
    for(let i=0;i<positioner.length;i++){const p=positioner[i];
      const d=Math.sqrt((tgt.x-(p.x||0))**2+(tgt.z-(p.z||0))**2);
      if(d<bd){bd=d;best=i}}
    goWalk(best);
  }else{
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

init();
</script>
</body>
</html>
"""