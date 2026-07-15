"""The /dev memory-graph 3D view (memory-rebuild spec §7-6 可视化).

Adapted from ``docs/superpowers/mockups/2026-07-02-memory-ontology-three.html``
— the 定稿模型 canvas is the ACCEPTANCE AUTHORITY. The visual language is the
spec §7-6 COMPLETE axis→channel classification (one channel per state axis,
Cartesian product covered, no overloads, no gaps):

- **points** — kind → azimuth SECTOR (person/org/project/artifact; events use
  the bottom height band, self at origin) · 时态 → HEIGHT BAND (live mid /
  historical sunk / event-terminal bottom ring) · consolidation → RADIUS
  (strong=near USER) + size · connectivity → TEXTURE (solid disc vs hollow
  dashed orphan ring) · lens → COLOR only (种类/validity/记忆度). Positions
  are a pure function of identity + now-state: the as-of scrubber changes
  visibility/color, never the layout.
- **edges** — observations → thickness (always) · historical → gray-thin
  (masks lens color) · status → opacity (shadow constantly dim; labels only
  for active or obs≥3) · 作用面/方向/极性 → the three edge lenses.
- **面** — color = per-face IDENTITY hue (provenance rides LINE STYLE:
  both=solid bright frame+fill / single=dashed weak, exactly the mockup);
  vertices = the anchor entities it emerged from, NEVER including USER.
  Complete n-case dispatch: n≥3 hull · n=2 translucent spindle · n=1 halo
  ring on the anchor · n=0 tower plate.
- **体** — per-body identity hue, always-solid frame; vertices = member
  anchors ∪ USER (§1.5-3 rollup). m≥2 hull · m=1 USER↔anchor spindle ·
  m=0 plate.
- **time scrubber + ▶** — client-side f(T) over the REAL bitemporal fields;
  edges carry evidence-time ``valid_from`` so the axis has real depth.

Served by ``GET /dev/memory`` behind the same dev gate as the ops dashboard,
with the same rebuild-free override (``<root>/dev_memory.html``). The dashboard
embeds it as the 记忆图 tab (lazy iframe).
"""

MEMORY_VIEW_HTML = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Persome Memory — 记忆图（真库）</title>
<style>
  :root{--bg:#0c0e13;--panel:#171a21;--ink:#e8ebf0;--dim:#98a0ad;--line:#2a2f3a;--user:#c65cff;--fork:#e06666;--live:#3fb970;}
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI",sans-serif;overflow:hidden}
  .wrap{display:flex;height:100%}
  .canvas{position:relative;flex:1;overflow:hidden}
  #view{position:absolute;inset:0;background:radial-gradient(ellipse 90% 75% at 50% 32%,#191c24 0%,#101218 45%,#0a0b0f 100%)}
  .toolbar{position:absolute;top:12px;left:12px;z-index:6;display:flex;gap:6px;flex-wrap:wrap;align-items:center;max-width:70%}
  .toolbar span.lbl{color:var(--dim);font-size:11px}
  .toolbar button{background:rgba(23,26,33,.9);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:4px 8px;font-size:12px;cursor:pointer}
  .toolbar button.on{border-color:var(--user);color:#fff}
  .timebar{position:absolute;bottom:12px;left:50%;transform:translateX(-50%);z-index:6;display:flex;align-items:center;gap:10px;background:rgba(23,26,33,.95);border:1px solid var(--line);border-radius:10px;padding:8px 14px}
  .timebar input[type=range]{width:300px;accent-color:var(--user)}
  .timebar #tlabel{font-size:12px;min-width:96px}
  .timebar button{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:4px 9px;cursor:pointer}
  .legend{position:absolute;top:52px;right:12px;z-index:5;background:rgba(23,26,33,.92);border:1px solid var(--line);border-radius:10px;padding:9px 12px;font-size:12px;max-width:255px;max-height:70vh;overflow:auto}
  .legend .row{display:flex;align-items:center;gap:7px;margin:3px 0;color:var(--dim)}
  .legend .sec{margin-top:7px;color:var(--ink);font-weight:600;font-size:11px}
  .dot{width:11px;height:11px;border-radius:50%;flex:none}
  .bar{width:20px;height:0;border-top:3px solid;flex:none}
  .stats{position:absolute;top:12px;right:12px;z-index:5;background:rgba(23,26,33,.92);border:1px solid var(--line);border-radius:10px;padding:7px 12px;font-size:12px;color:var(--dim);max-width:255px}
  .stats b{color:var(--ink)}
  .detail{position:absolute;bottom:64px;left:12px;z-index:6;background:rgba(23,26,33,.95);border:1px solid var(--line);border-radius:10px;padding:10px 13px;font-size:12.5px;color:var(--dim);max-width:360px;max-height:52vh;overflow:auto;display:none}
  .detail h3{margin:0 0 5px;font-size:13px;color:var(--user)}
  .detail b{color:var(--ink)}
  .lbl3d{font-size:11px;font-weight:500;letter-spacing:.2px;color:rgba(236,239,245,.94);text-shadow:0 1px 3px rgba(0,0,0,.92);pointer-events:none;white-space:nowrap;background:rgba(10,12,17,.5);padding:1px 6px;border-radius:6px;transition:opacity .18s ease}
  .lbl3d.sm{font-size:9.5px;color:rgba(203,210,223,.86);background:rgba(10,12,17,.42)}
  .lbl3d.ghost{color:rgba(167,175,191,.68);font-style:italic;background:rgba(10,12,17,.3)}
  .lbl3d.hide{display:none}
  .lbl3d.hl{background:rgba(42,33,62,.92);box-shadow:0 0 0 1px var(--user);color:#fff;z-index:20}
  #err{position:absolute;inset:0;display:none;align-items:center;justify-content:center;color:var(--fork);padding:40px;text-align:center;white-space:pre-wrap;z-index:9}
</style>
<script type="importmap">
{"imports":{
  "three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
}}
</script>
</head>
<body>
<div class="wrap">
  <div class="canvas">
    <div class="toolbar">
      <span class="lbl">点:</span>
      <button data-lens="kind" class="on">种类</button><button data-lens="validity">validity</button><button data-lens="mem">记忆度</button>
      <span class="lbl">| 边:</span>
      <button data-elens="mod" class="on">作用面</button><button data-elens="dir">方向</button><button data-elens="val">极性</button>
      <span class="lbl">|</span><button id="schemaBtn" class="on">▦ 面</button><button id="bodyBtn" class="on">▦▦ 体</button><button id="spinBtn">⟳</button>
    </div>
    <div id="view"></div><div id="err"></div>
    <div class="stats" id="stats">加载中…</div>
    <div class="legend" id="legend"></div>
    <div class="detail" id="detail"></div>
    <div class="timebar"><button id="play">▶</button><span class="lbl" style="color:var(--dim);font-size:11px">as-of</span>
      <input type="range" id="time" min="0" max="24" step="1" value="24"><span id="tlabel">now</span></div>
  </div>
</div>

<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {CSS2DRenderer, CSS2DObject} from 'three/addons/renderers/CSS2DRenderer.js';
import {ConvexGeometry} from 'three/addons/geometries/ConvexGeometry.js';
const errBox=document.getElementById('err');
window.addEventListener('error',e=>{errBox.style.display='flex';errBox.textContent='加载/渲染出错（多半是没联网加载 Three CDN）。\n'+e.message;});

// ── 真数据（可重取——实时轮询长大，延时摄影用）──────────────────────
let nodes=[], edges=[], faces=[], searchState={}, byId={};
function ingest(data){
  nodes=data.nodes||[]; edges=data.edges||[]; faces=data.faces||[];
  searchState=data.search||{}; byId=Object.fromEntries(nodes.map(n=>[n.id,n]));
}
ingest(await (await fetch('/dev/memory-graph')).json());

// ── 轴 ↔ 通道（spec §7-6 完备分类）────────────────────────────────
const kcls=n=>n.kind==='self'?'user':(n.kind==='event'?'occ':'cont');
const KIND={user:0xc65cff,cont:0x3aa0a0,occ:0xd9a441};
const PFAM={engaged_with:'floor',participates_in:'dyn',part_of:'struct',reports_to:'struct',knows:'aff',about:'sem',depends_on:'struct'};
const FAM={struct:0x5b8dff,dyn:0xe0803c,sem:0x46c68a,aff:0xb57cff,floor:0x3a3f4a};
const VAL={'+':0x3fb970,'-':0xe06666,'0':0x6b7280};
const SYM=new Set(['knows']);
// 面/体身份色：id 的确定性色相（provenance 走线型，不占颜色通道——mockup 语义）
function hash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return (h>>>0)/4294967296;}
const idColor=id=>new THREE.Color().setHSL(hash(id),0.55,0.58);
let lens='kind',eLens='mod',showSchema=true,showBody=true,focus=null;

// ── 布局：位置 = 身份 + now 态的纯函数（as-of 只改可见性/颜色）──────
// θ 扇区=kind；y 带=时态；r=证据强度（近=强）；孤儿由贴图+外壳半径表达
const strength={}, nodeEdgesNow={};
const histNow=e=>e.valid_to!=null; // now 态的时效（布局用；as-of 态另算）
const SECTOR={person:[0,200],org:[200,253],project:[253,306],artifact:[306,360]};
const P={};
function computeLayout(){
  for(const k in strength)delete strength[k];for(const k in nodeEdgesNow)delete nodeEdgesNow[k];for(const k in P)delete P[k];
  edges.forEach(e=>{for(const id of [e.a,e.b]){strength[id]=Math.max(strength[id]||0,e.observations||1);}});
  edges.forEach(e=>{(nodeEdgesNow[e.a]=nodeEdgesNow[e.a]||[]).push(e);(nodeEdgesNow[e.b]=nodeEdgesNow[e.b]||[]).push(e);});
  const buckets={};
  nodes.forEach(n=>{if(n.kind!=='self'&&n.kind!=='event'){const k=n.kind in SECTOR?n.kind:'person';(buckets[k]=buckets[k]||[]).push(n.id);}});
  for(const k of Object.keys(buckets))buckets[k].sort();
  const angleOf={};
  for(const [k,[a0,a1]] of Object.entries(SECTOR)){
    const ids=buckets[k]||[];
    ids.forEach((id,i)=>{angleOf[id]=(a0+((i+0.5)/ids.length)*(a1-a0))*Math.PI/180;});
  }
  // 时态下沉的分位数等化：cont 点按最近观察时间排名 → [0,1]
  const ageRank={};
  {
    const ages=[];
    nodes.forEach(n=>{
      if(n.kind==='self'||n.kind==='event')return;
      const es=nodeEdgesNow[n.id]||[];
      let last=0;
      es.forEach(e=>{const ts=e.last_observed_at||e.valid_from;if(ts){const v=new Date(ts).getTime();if(v>last)last=v;}});
      ages.push([n.id,last?(Date.now()-last):Infinity]);
    });
    ages.sort((a,b)=>a[1]-b[1]);
    ages.forEach(([id],i)=>{ageRank[id]=ages.length>1?i/(ages.length-1):0;});
  }
  let ei=0;const GA=Math.PI*(3-Math.sqrt(5));
  for(const n of nodes){
    const h=hash(n.id);
    if(n.kind==='self'){P[n.id]=new THREE.Vector3(0,0,0);continue;}
    if(n.kind==='event'){ // 发生者：底层环（终态即历史），全周
      const th=(ei++)*GA+h;const r=3.4-Math.min(strength[n.id]||1,6)*0.1;
      P[n.id]=new THREE.Vector3(Math.cos(th)*r,-1.8+h*0.5,Math.sin(th)*r);continue;}
    const th=angleOf[n.id]??h*Math.PI*2;
    const es=nodeEdgesNow[n.id]||[];
    const historical=es.length&&es.every(histNow);
    // y=连续时态下沉轴（§7-6 修订二：分位数等化）。真库审计发现年龄分布本身很紧
    // （多数实体最新证据在 5–15 天内），线性/对数任何度量映射都保团——按「距上次
    // 观察天数」的**排名**均匀铺满带（序保留、可区分由构造保证；精确天数进详情卡）。
    const y=0.35-(ageRank[n.id]??1)*1.1-(historical?0.5:0)+(h-0.5)*0.1;
    const r=es.length?(3.1-Math.min(strength[n.id]||1,10)*0.14):4.3; // 强=近；无边=外壳
    P[n.id]=new THREE.Vector3(Math.cos(th)*r,y,Math.sin(th)*r);
  }
}
computeLayout();

// ── 时间轴：真 bitemporal f(T)（valid_from/valid_to/created_at；可重算）──
let t0=new Date(), t1=new Date();
function computeTimeline(){
  const dates=[];
  edges.forEach(e=>{if(e.valid_from)dates.push(e.valid_from);});
  faces.forEach(f=>{if(f.created_at)dates.push(f.created_at);});
  dates.sort();
  t0=dates.length?new Date(dates[0]):new Date();
  t1=new Date();
}
computeTimeline();
const STEPS=24;
const slider=document.getElementById('time'), tlabel=document.getElementById('tlabel');
function tAt(step){return new Date(t0.getTime()+(t1.getTime()-t0.getTime())*step/STEPS);}
let T=t1;
const before=(a,b)=>!a||new Date(a)<=b;      // absent field ⇒ fail-open visible
const closed=vt=>vt!=null&&new Date(vt)<=T;
const edgeVisible=e=>before(e.valid_from,T);
const faceVisible=f=>before(f.created_at,T);
const edgeHist=e=>closed(e.valid_to);

// ── Three 场景（mockup 同款内敛风）────────────────────────────────
const view=document.getElementById('view');
const scene=new THREE.Scene(); scene.fog=new THREE.FogExp2(0x0b0c10,0.03);
const camera=new THREE.PerspectiveCamera(50,view.clientWidth/view.clientHeight,0.1,100); camera.position.set(0,1.8,9);
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true}); renderer.setPixelRatio(devicePixelRatio); renderer.setSize(view.clientWidth,view.clientHeight);
renderer.toneMapping=THREE.ACESFilmicToneMapping; view.appendChild(renderer.domElement);
const labelRenderer=new CSS2DRenderer(); labelRenderer.setSize(view.clientWidth,view.clientHeight); labelRenderer.domElement.style.cssText='position:absolute;top:0;pointer-events:none'; view.appendChild(labelRenderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement); controls.enableDamping=true; controls.dampingFactor=.08;
const graph=new THREE.Group(); scene.add(graph);
const circleTex=(()=>{const c=document.createElement('canvas');c.width=c.height=128;const g=c.getContext('2d');g.beginPath();g.arc(64,64,60,0,Math.PI*2);g.fillStyle='#fff';g.fill();return new THREE.CanvasTexture(c);})();
const ringTex=(()=>{const c=document.createElement('canvas');c.width=c.height=128;const g=c.getContext('2d');g.beginPath();g.arc(64,64,54,0,Math.PI*2);g.lineWidth=10;g.setLineDash([16,12]);g.strokeStyle='#fff';g.stroke();return new THREE.CanvasTexture(c);})();
// 恒星光晕：柔和径向渐变（亮核 → 透明边），加法混合 → 星系辉光
const glowTex=(()=>{const c=document.createElement('canvas');c.width=c.height=128;const g=c.getContext('2d');
  const gr=g.createRadialGradient(64,64,0,64,64,64);
  gr.addColorStop(0,'rgba(255,255,255,1)');gr.addColorStop(0.18,'rgba(255,255,255,0.6)');
  gr.addColorStop(0.5,'rgba(255,255,255,0.16)');gr.addColorStop(1,'rgba(255,255,255,0)');
  g.fillStyle=gr;g.fillRect(0,0,128,128);return new THREE.CanvasTexture(c);})();
let nodeSprites=[],faceMeshes=[],bodyMeshes=[],labels3d=[];
// prio = 标签预算/碰撞剔除的优先级（大=先画、不被剔）；baseOp = 语义透明度（雾/hover 在其上乘）；
// full = hover title 全文（面的长句截断后靠它读全）。所有标签收进 labels3d 供每帧 cullLabels 处理。
function mkLabel(text,cls,colorHex,prio,baseOp,full,target){const d=document.createElement('div');d.className='lbl3d'+(cls?' '+cls:'');d.textContent=text;if(colorHex)d.style.color=colorHex;if(full)d.title=full;const o=new CSS2DObject(d);o.userData={label:true,prio:prio||0,baseOp:baseOp==null?1:baseOp,nid:null,fid:target?target.id:null};o.element.style.opacity=o.userData.baseOp;
  if(target){d.style.pointerEvents='auto';d.style.cursor='pointer'; // 面/体标签可交互：hover→setHover 高亮，click→pickTarget 选中
    d.addEventListener('mouseenter',()=>setHover({type:target.kind,id:target.id}));
    d.addEventListener('mouseleave',()=>setHover(null));
    d.addEventListener('click',ev=>{ev.stopPropagation();pickTarget(target.kind,target.id);});}
  labels3d.push(o);return o;}
function hullMesh(vs,color,opacity){let geo=null;
  if(vs.length>=4){try{geo=new ConvexGeometry(vs);}catch(e){geo=null;}}
  if(!geo||!geo.attributes.position||geo.attributes.position.count<3){
    geo=new THREE.BufferGeometry();const pts=[];
    for(let i=1;i<vs.length-1;i++)pts.push(vs[0].x,vs[0].y,vs[0].z,vs[i].x,vs[i].y,vs[i].z,vs[i+1].x,vs[i+1].y,vs[i+1].z);
    geo.setAttribute('position',new THREE.Float32BufferAttribute(pts,3));geo.computeVertexNormals();}
  return new THREE.Mesh(geo,new THREE.MeshBasicMaterial({color,transparent:true,opacity,side:THREE.DoubleSide,depthWrite:false}));}
function edgeMesh(A,B,color,radius,opacity){const dir=new THREE.Vector3().subVectors(B,A);const len=dir.length();
  const m=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,len,8,1,true),new THREE.MeshBasicMaterial({color,transparent:true,opacity,depthWrite:false}));
  m.position.copy(A).addScaledVector(dir,.5); m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),dir.clone().normalize()); return m;}

// ── as-of 态 ───────────────────────────────────────────────────────
function computeState(){
  const vEdges=edges.filter(edgeVisible);
  const inComp=new Set(['self']);
  {const adj={};nodes.forEach(n=>adj[n.id]=[]);vEdges.forEach(e=>{if(adj[e.a])adj[e.a].push(e.b);if(adj[e.b])adj[e.b].push(e.a);});
   const q=['self'];while(q.length){const x=q.shift();(adj[x]||[]).forEach(y=>{if(!inComp.has(y)){inComp.add(y);q.push(y);}});}}
  const shadowIds=new Set(nodes.filter(n=>!inComp.has(n.id)).map(n=>n.id));
  const nodeEdges={};vEdges.forEach(e=>{(nodeEdges[e.a]=nodeEdges[e.a]||[]).push(e);(nodeEdges[e.b]=nodeEdges[e.b]||[]).push(e);});
  const validity={};nodes.forEach(n=>{const es=nodeEdges[n.id]||[];
    validity[n.id]=kcls(n)==='occ'?'terminal':(es.length&&es.every(edgeHist)?'historical':'live');});
  const mem={};nodes.forEach(n=>mem[n.id]=n.id==='self'?99:0);
  for(let i=0;i<6;i++)vEdges.forEach(e=>{const o=(e.observations||1)*(edgeHist(e)?.5:1);
    mem[e.a]=Math.max(mem[e.a]||0,Math.min(mem[e.b]||0,o));mem[e.b]=Math.max(mem[e.b]||0,Math.min(mem[e.a]||0,o));});
  return {vEdges,shadowIds,validity,mem};
}
function focusSets(vEdges){
  let HN=null,HE=null,HF=null;
  if(focus){const vis=faces.filter(faceVisible);
    if(focus.kind==='node'){
      HN=focus.treeIds?new Set(focus.treeIds):new Set([focus.id]);
      if(!focus.treeIds)vEdges.forEach(e=>{if(e.a===focus.id)HN.add(e.b);if(e.b===focus.id)HN.add(e.a);});
      HF=new Set(vis.filter(f=>(f.anchors||[]).includes(focus.id)).map(f=>f.id));
      HE=e=>HN.has(e.a)&&HN.has(e.b);}
    else{const f=vis.find(x=>x.id===focus.id);const mem=new Set(f?(f.anchors||[]):[]);mem.add('self');
      HN=mem;HF=new Set([focus.id]);HE=e=>mem.has(e.a)&&mem.has(e.b);}}
  return {HN,HE,HF};
}
function nodeColor(n,st){
  if(lens==='kind')return KIND[kcls(n)];
  if(lens==='validity'){const v=st.validity[n.id];return v==='terminal'?0x33507a:(v==='live'?0x3fb970:0x727a88);}
  if(lens==='mem'){const t=Math.min(1,(st.mem[n.id]||0)/5);return new THREE.Color(0x2a2f3a).lerp(new THREE.Color(0x62d6ff),t).getHex();}
  return 0x888888;
}
function edgeColor(e){if(edgeHist(e))return 0x5b636f; // 遮蔽序：historical > lens
  if(eLens==='mod')return FAM[PFAM[e.predicate]||'aff'];
  if(eLens==='val')return VAL[e.polarity||'0'];
  return 0x9aa3b2;}

// 面/体标签防重叠：多个面的质心挤在同一片锚点上时，贪心竖向错开
let placedLabels=[];
function placeLabel(pos){const p=pos.clone();
  for(let guard=0;guard<12;guard++){
    if(placedLabels.every(q=>q.distanceTo(p)>0.36))break;
    p.y+=0.19;}
  placedLabels.push(p.clone());return p;}
// ② 面的长签名 → 短关键词标签（引号里的词优先，否则剥「用户…」前缀取前 11 字）；全句进 hover title。
function faceKey(sig){sig=(sig||'').trim();
  const m=sig.match(/[「『“"']([^」』”"']{2,16})[」』”"']/);
  if(m)return m[1];
  return sig.replace(/^用户(倾向于|擅长|正在|会|对|以|建立了|是|发现|采用)?/,'').slice(0,11);}
function faceFull(f,pfx){return pfx+(f.signature||'')+`  [${f.provenance}${f.status==='active'?'·转正✓':'·shadow'}]`;}
// 面/体的 n-case 分派（spec §7-6 完备表）：n≥3 凸包 · n=2 梭 · n=1 光环 · n=0 塔板
function renderFace(f,anchorPts,col,both,o,tagPrefix){
  const hex='#'+col.getHexString();
  const tag=tagPrefix+faceKey(f.signature)+(f.status==='active'?' ✓':'');
  const full=faceFull(f,tagPrefix), fprio=40+Math.min(f.observations||1,10);
  const isBody=f.level===2;
  const frameOp=(both||isBody?0.85:0.45)*o, fillOp=(isBody?0.03:(both?0.15:0.05))*o;
  if(anchorPts.length>=3){
    const fill=hullMesh(anchorPts,col,fillOp);
    fill.userData={kind:'face',id:f.id};graph.add(fill);(isBody?bodyMeshes:faceMeshes).push(fill);
    const mat=(both||isBody)?new THREE.LineBasicMaterial({color:col,transparent:true,opacity:frameOp})
      :new THREE.LineDashedMaterial({color:col,transparent:true,opacity:frameOp,dashSize:.12,gapSize:.1});
    const eg=new THREE.LineSegments(new THREE.EdgesGeometry(fill.geometry),mat);
    if(!(both||isBody))eg.computeLineDistances();
    graph.add(eg);
    const c=anchorPts.reduce((s,v)=>s.add(v.clone()),new THREE.Vector3()).multiplyScalar(1/anchorPts.length);
    const lab=mkLabel(tag,both?'sm':'sm ghost',hex,fprio,o,full,{kind:'face',id:f.id});lab.position.copy(placeLabel(c.add(new THREE.Vector3(0,0.12,0))));graph.add(lab);
    return true;
  }
  if(anchorPts.length===2){ // 2 点撑不起 2 维 → 半透梭
    const sp=edgeMesh(anchorPts[0],anchorPts[1],col,0.05,(both||isBody?0.32:0.16)*o);
    sp.userData={kind:'face',id:f.id};graph.add(sp);(isBody?bodyMeshes:faceMeshes).push(sp);
    const c=anchorPts[0].clone().add(anchorPts[1]).multiplyScalar(.5);
    const lab=mkLabel(tag,both?'sm':'sm ghost',hex,fprio,o,full,{kind:'face',id:f.id});lab.position.copy(placeLabel(c.add(new THREE.Vector3(0,0.1,0))));graph.add(lab);
    return true;
  }
  if(anchorPts.length===1){ // 关于这一个事物的规律 → 锚点光环
    const halo=new THREE.Sprite(new THREE.SpriteMaterial({map:ringTex,color:col,transparent:true,opacity:(both?0.9:0.5)*o,depthTest:false,depthWrite:false}));
    halo.scale.setScalar(0.52);halo.position.copy(anchorPts[0]);halo.renderOrder=2;halo.userData={kind:'face',id:f.id};graph.add(halo);(isBody?bodyMeshes:faceMeshes).push(halo);
    const lab=mkLabel(tag,both?'sm':'sm ghost',hex,fprio,o,full,{kind:'face',id:f.id});lab.position.copy(placeLabel(anchorPts[0].clone().add(new THREE.Vector3(0,0.4,0))));graph.add(lab);
    return true;
  }
  return false; // n=0：塔板 fallback（调用方收集）
}

function build(){
  while(graph.children.length){const o=graph.children.pop();o.traverse(x=>{if(x.isCSS2DObject&&x.element)x.element.remove();});}
  nodeSprites=[];faceMeshes=[];bodyMeshes=[];placedLabels=[];labels3d=[];
  const st=computeState();
  const {vEdges,shadowIds,validity}=st;
  const {HN,HE,HF}=focusSets(vEdges);
  const nOp=id=>HN?(HN.has(id)?1:.12):1, eOp=e=>HE?(HE(e)?1:.06):.85, fOp=id=>HF?(HF.has(id)?1:.12):1;
  const touched=new Set(['self']);vEdges.forEach(e=>{touched.add(e.a);touched.add(e.b);});
  let nP=0,nA=0,nEact=0,nEsh=0,nHist=0;
  // ── 边 ──
  for(const e of vEdges){
    const A=P[e.a],B=P[e.b];if(!A||!B)continue;
    const hist=edgeHist(e);
    const active=e.status==='active';
    const col=edgeColor(e);
    const radius=hist?0.006:(0.006+Math.min(e.observations||1,6)*0.007);
    const o=eOp(e)*(hist?0.3:(active?1:0.2)); // shadow 恒暗（§3.3 状态闸）
    graph.add(edgeMesh(A,B,col,radius,Math.min(.92,o)));
    if(active&&!hist)nEact++;else if(!hist)nEsh++;else nHist++;
    if(eLens==='dir'&&!hist){const dir=new THREE.Vector3().subVectors(B,A).normalize();
      const tip=B.clone().addScaledVector(dir,-.16);
      const ar=new THREE.Mesh(new THREE.ConeGeometry(.045,.13,10),new THREE.MeshBasicMaterial({color:col,transparent:true,opacity:o}));
      ar.position.copy(tip);ar.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),dir);graph.add(ar);
      if(SYM.has(e.predicate)){const t2=A.clone().addScaledVector(dir,.16);
        const a2=new THREE.Mesh(new THREE.ConeGeometry(.045,.13,10),new THREE.MeshBasicMaterial({color:col,transparent:true,opacity:o}));
        a2.position.copy(t2);a2.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),dir.clone().negate());graph.add(a2);}}
    if(!hist&&o>.35&&(active||(e.observations||1)>=3)){ // 标签控噪：active 或强证据
      const lc=A.clone().add(B).multiplyScalar(.5);
      const txt=(e.label||e.predicate)+((e.observations||1)>1?` ×${e.observations}`:'');
      const lab=mkLabel(txt,'sm','#'+col.toString(16).padStart(6,'0'),8+Math.min(e.observations||1,10),o);lab.position.copy(lc);graph.add(lab);}
  }
  // ── 点 ──
  for(const n of nodes){
    const cls=kcls(n);
    const isShadow=shadowIds.has(n.id);
    if(cls!=='user'&&!touched.has(n.id)&&!isShadow)continue;
    const strT=Math.min(strength[n.id]||1,12)/12;
    let col=isShadow?0x8a93a3:nodeColor(n,st);
    if(!isShadow&&cls==='cont'){ // 亮度 ∝ 证据强度：强=明度更高（保色相），弱=暗
      const c=new THREE.Color(col),hsl={};c.getHSL(hsl);c.setHSL(hsl.h,hsl.s,Math.min(0.92,hsl.l*(0.62+0.85*strT)));col=c.getHex();}
    const o=nOp(n.id)*(validity[n.id]==='historical'?.5:1)*(isShadow?.6:1);
    const coreSz=cls==='user'?0.32:(cls==='occ'?0.075:0.095), spOp=cls==='occ'?Math.min(o,.9):o; // 核=固定小亮点
    let glow=null;
    if(!isShadow){ // 恒星光晕：size ∝ 强度（亮度越大光晕越大），加法混合 → 星系辉光
      const haloSz=cls==='user'?1.25:(cls==='occ'?0.24:0.28+strT*0.7);
      const gOp=(cls==='occ'?0.3:(cls==='user'?0.75:0.38+strT*0.4))*o;
      glow=new THREE.Sprite(new THREE.SpriteMaterial({map:glowTex,color:col,transparent:true,opacity:gOp,depthTest:false,depthWrite:false,blending:THREE.AdditiveBlending}));
      glow.scale.setScalar(haloSz);glow.position.copy(P[n.id]);glow.renderOrder=2;glow.userData={glow:true,baseScale:haloSz,baseOp:gOp};graph.add(glow);}
    const core=new THREE.Sprite(new THREE.SpriteMaterial({map:isShadow?ringTex:circleTex,color:col,transparent:true,opacity:spOp,depthTest:false,depthWrite:false}));
    core.scale.setScalar(coreSz);core.position.copy(P[n.id]);core.renderOrder=3;core.userData={kind:'node',id:n.id,target:P[n.id].clone(),baseScale:coreSz,baseOp:spOp,glow};graph.add(core);nodeSprites.push(core);
    if(cls==='cont'){nP++;}else if(cls==='occ'){nA++;}
    if(cls!=='occ'||isShadow){
      const prio=cls==='user'?1000:(isShadow?20:60+Math.min(strength[n.id]||1,30));
      const lab=mkLabel(n.label+(isShadow?'（孤儿·shadow）':''),cls==='user'?null:(isShadow?'ghost':'sm'),prio,o);
      lab.userData.nid=n.id;
      lab.position.copy(P[n.id]).add(new THREE.Vector3(0,coreSz+0.14,0));graph.add(lab);}
  }
  // ── 面/体（角=锚点；面不含 USER，体锚 USER 一角）──
  const plates=[];
  const visFaces=faces.filter(faceVisible);
  visFaces.forEach(f=>{
    const isBody=f.level===2;
    if(isBody?!showBody:!showSchema)return;
    const both=f.provenance==='both';
    const col=idColor(f.id);
    const o=fOp(f.id);
    // 角=可见非孤儿锚点（孤儿在外壳，不参与涌现簇的形状）
    const anchorPts=(f.anchors||[]).filter(a=>P[a]&&touched.has(a)&&!shadowIds.has(a)).map(a=>P[a].clone());
    if(isBody&&anchorPts.length>=1)anchorPts.push(P['self'].clone()); // §1.5-3 体锚根
    if(!renderFace(f,anchorPts,col,both,o,isBody?'体◆':'面▸'))plates.push(f);
  });
  const byLevel={1:[],2:[]};
  plates.forEach(f=>{(byLevel[f.level]||byLevel[1]).push(f);});
  for(const lvl of [1,2]){
    const row=byLevel[lvl];const y=1.9+(lvl-1)*0.85;
    row.forEach((f,i)=>{
      const x=(i-(row.length-1)/2)*1.15;
      const both=f.provenance==='both';
      const col=idColor(f.id);
      const o=fOp(f.id);
      const plate=new THREE.Mesh(new THREE.CircleGeometry(0.34+Math.min(f.observations||1,6)*0.03,32),
        new THREE.MeshBasicMaterial({color:col,transparent:true,opacity:(both?0.5:0.16)*o,side:THREE.DoubleSide,depthWrite:false}));
      plate.rotation.x=-Math.PI/2;plate.position.set(x,y,0);plate.userData={kind:'face',id:f.id};graph.add(plate);faceMeshes.push(plate);
      const ring=new THREE.Mesh(new THREE.RingGeometry(0.36,0.4,32),
        new THREE.MeshBasicMaterial({color:col,transparent:true,opacity:(both?0.9:0.35)*o,side:THREE.DoubleSide,depthWrite:false}));
      ring.rotation.x=-Math.PI/2;ring.position.set(x,y,0);graph.add(ring);
      const pfx=(lvl===2?'体◆':'面▸');
      const lab=mkLabel(pfx+faceKey(f.signature)+(f.status==='active'?' ✓':''),both?'sm':'sm ghost','#'+col.getHexString(),40+Math.min(f.observations||1,10),o,faceFull(f,pfx),{kind:'face',id:f.id});
      lab.position.set(x,y+0.14,0);graph.add(lab);
    });
  }
  drawLegend(st.shadowIds.size);
  document.getElementById('stats').innerHTML=
    `人/实体 <b>${nP}</b> · Activity <b>${nA}</b> · 边 <b>${nEact} active / ${nEsh} shadow / ${nHist} 已结束</b> · 面/体 <b>${visFaces.length}</b>（${plates.length} 无锚塔板）<br>`+
    `<span style="font-size:11px">as-of ${T.toISOString().slice(0,10)} · 扇区=种类 · 高度=时态 · 近=证据强</span><br>`+
    `<span style="font-size:11px">检索权重: 文本1.0 · 槽${searchState.slot_pool_weight??'?'} · 关系${searchState.relation_pool_weight??'?'} · shadow喂食${searchState.relation_include_shadow?'开(×0.5)':'关'} · 池内混排${searchState.contains_pool_rerank?'开(recency⊕sim)':'关'}</span>`;
}
function drawLegend(nShadow){const L=document.getElementById('legend');const hx=c=>'#'+c.toString(16).padStart(6,'0');
  const nS={kind:[[KIND.user,'USER'],[KIND.cont,'持续者'],[KIND.occ,'发生者(终态事件)']],
            validity:[[0x3fb970,'live'],[0x727a88,'historical(边全收口)'],[0x33507a,'发生者(终态即历史)']],
            mem:[[0x62d6ff,'记忆度高(近USER·证据强)'],[0x2a2f3a,'低(易被遗忘)']]}[lens]||[];
  let h='<div class="sec">点（扇区=种类 · 高=新近/沉=久未观察 · 近=强）</div>'+nS.map(([c,t])=>`<div class="row"><span class="dot" style="background:${hx(c)}"></span>${t}</div>`).join('');
  h+='<div class="row"><span class="dot" style="background:transparent;border:2px dashed #8a93a3"></span>孤儿=shadow(TTL内)</div>';
  const eS={mod:[[FAM.struct,'结构(part_of/reports_to/depends_on)'],[FAM.dyn,'动态(participates_in)'],[FAM.sem,'指涉(about)'],[FAM.aff,'亲和(knows)']],
            dir:[[0x9aa3b2,'→ 规范方向 / ↔ knows 双头']],
            val:[[VAL['+'],'+'],[VAL['-'],'−'],[VAL['0'],'0(中性)']]}[eLens]||[];
  h+='<div class="sec">边（粗细=observations 证据数）</div>'+eS.map(([c,t])=>`<div class="row"><span class="bar" style="border-color:${hx(c)}"></span>${t}</div>`).join('');
  h+='<div class="row"><span class="bar" style="border-color:#5b636f;border-top-style:dashed"></span>historical(仍连通)</div>';
  h+='<div class="row"><span class="bar" style="border-color:#4a5160"></span>shadow status(恒暗·检索盲)</div>';
  h+='<div class="sec">面/体（颜色=身份色 · 角=锚点）</div>';
  h+='<div class="row"><span class="dot" style="background:#7a9;opacity:.6;border-radius:3px"></span>both=实线亮框(转正)</div>';
  h+='<div class="row"><span class="dot" style="background:transparent;border:2px dashed #7a9;border-radius:3px"></span>单路=虚线弱框(shadow)</div>';
  h+='<div class="row" style="font-size:11px">n≥3 凸包 · n=2 梭 · n=1 光环 · n=0 塔板；体多锚 USER 一角</div>';
  h+=`<div class="sec">收敛</div><div class="row" style="color:var(--live)">✓ 连通=①engaged地板 ⊕ ②语义边</div><div class="row" style="color:var(--dim)">孤儿:${nShadow} 个（无边或弱地板·TTL 即遗忘）</div>`;
  L.innerHTML=h;}
// ── 详情 + 拾取 ────────────────────────────────────────────────────
const detail=document.getElementById('detail');
// 详情面板里点「上级规律」链接 → 选中那个 Schema/体（点/面/体统一跳转）
detail.addEventListener('click',ev=>{const el=ev.target.closest('.lnk');if(el&&el.dataset.fid)pickTarget('face',el.dataset.fid);});
function showDetail(kind,id){
  if(kind==='node'){const n=byId[id];const cls=kcls(n);
    const st=cls==='occ'?'发生者(Activity·终态才入图)':cls==='user'?'根':`持续者(${n.kind})`;
    const es=edges.filter(e=>e.a===id||e.b===id);
    const preds={};es.forEach(e=>preds[e.predicate]=(preds[e.predicate]||0)+1);
    const predLine=Object.entries(preds).map(([k,v])=>`${k}×${v}`).join(' · ')||'无边';
    // 上级：这个点归纳成了哪些 Schema（面）/ 体（面的面）——面/体 anchors 含此点即其上级规律
    const mine=faces.filter(f=>(f.anchors||[]).includes(id)).sort((a,b)=>b.level-a.level||(b.observations||0)-(a.observations||0));
    const lin=mine.length?`<div style="color:var(--ink);font-weight:600;font-size:11px;margin:8px 0 2px">上级 · 归纳出的规律（Schema▸ / 体◆）</div>`+
      mine.map(f=>`<div class="lnk" data-fid="${f.id}" title="${(f.signature||'').replace(/"/g,'&quot;')}" style="cursor:pointer;margin:2px 0;padding-left:2px;color:${f.status==='active'?'var(--live)':'var(--dim)'}">${f.level===2?'体◆':'面▸'} ${faceKey(f.signature)}${f.status==='active'?' ✓转正':' ·shadow'}</div>`).join(''):'';
    detail.innerHTML=`<h3>${n.label}</h3><b>${st}</b> · kind=${n.kind} · 边 ${predLine}${lin}<br><span class="raw" style="color:var(--dim)">原始记忆加载中…</span>`;
    // §2.1 每个点指回符号收据：懒取该点蒸馏自的原始条目
    fetch('/dev/memory-node?id='+encodeURIComponent(id)).then(r=>r.json()).then(d=>{
      if(!focus||focus.id!==id)return;
      // 以该点为根的关系树（§3.4 路径即叙事，根=这个事物）
      function treeHtml(node,depth){
        if(!node||!node.edges||!node.edges.length)return '';
        return node.edges.map(e=>{
          const arrow=e.dir==='out'?'→':'←';
          const dim=e.status==='active'?'':'opacity:.55;';
          const hist=e.historical?'（已结束）':'';
          const lbl=byId[e.child.id]?byId[e.child.id].label:e.child.id;
          return `<div style="margin-left:${depth*13}px;${dim}font-size:12px">`+
            `${arrow} <span style="color:var(--dim)">${e.label||e.predicate}${e.observations>1?' ×'+e.observations:''}${hist}</span> `+
            `<b>${lbl}</b></div>`+treeHtml(e.child,depth+1);
        }).join('');
      }
      const tree=treeHtml(d.tree,0);
      const lines=(d.raw||[]).map(r=>`<div style="margin:4px 0;border-left:2px solid var(--line);padding-left:7px">`+
        `<span style="font-size:10.5px;color:var(--dim)">${(r.ts||'').slice(0,16)}</span><br>${r.text}</div>`).join('');
      const el=detail.querySelector('.raw');
      if(el)el.outerHTML=
        (tree?`<div class="raw"><div style="color:var(--ink);font-weight:600;font-size:11px;margin:5px 0 2px">关系树（以此为根）</div>${tree}`:`<div class="raw">`)+
        (lines?`<div style="color:var(--ink);font-weight:600;font-size:11px;margin:7px 0 2px">原始记忆</div>${lines}`:`<div style="color:var(--dim)">（${d.source||'无来源'}：暂无原始条目）</div>`)+
        `</div>`;
      // 树上的点在图中聚焦高亮
      const ids=new Set([id]);
      (function walk(n){(n.edges||[]).forEach(e=>{ids.add(e.child.id);walk(e.child);});})(d.tree||{});
      if(focus&&focus.id===id){focus={kind:'node',id,treeIds:ids};build();}
    }).catch(()=>{});}
  else{const f=faces.find(x=>x.id===id);if(!f)return;
    const both=f.provenance==='both';
    detail.innerHTML=`<h3>${f.level===2?'体◆':'面▸'}${f.signature||''}</h3>统一 schema（level${f.level}）· provenance=<b>${f.provenance}</b>${both?'（双信号转正 ✓）':'（单路 shadow）'} · obs=${f.observations}<br>锚：${(f.anchors||[]).join('、')||'（无锚·塔板）'}`;}
  detail.style.display='block';}
const ray=new THREE.Raycaster(),mouse=new THREE.Vector2();let downXY=null;
renderer.domElement.addEventListener('pointerdown',e=>downXY={x:e.clientX,y:e.clientY});
renderer.domElement.addEventListener('pointerup',e=>{if(!downXY)return;const moved=Math.abs(e.clientX-downXY.x)+Math.abs(e.clientY-downXY.y)>4;downXY=null;if(moved)return;
  const r=renderer.domElement.getBoundingClientRect();mouse.x=((e.clientX-r.left)/r.width)*2-1;mouse.y=-((e.clientY-r.top)/r.height)*2+1;ray.setFromCamera(mouse,camera);
  let hit=null;for(const grp of [nodeSprites,faceMeshes,bodyMeshes]){const ins=ray.intersectObjects(grp,false);if(ins.length){hit=ins[0].object.userData;break;}}
  if(hit){focus=(focus&&focus.kind===hit.kind&&focus.id===hit.id)?null:{kind:hit.kind,id:hit.id};if(focus)showDetail(hit.kind,hit.id);else detail.style.display='none';}
  else{focus=null;detail.style.display='none';}
  build();});
// ── UI ─────────────────────────────────────────────────────────────
document.querySelectorAll('.toolbar [data-lens]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.toolbar [data-lens]').forEach(x=>x.classList.remove('on'));b.classList.add('on');lens=b.dataset.lens;build();}));
document.querySelectorAll('.toolbar [data-elens]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.toolbar [data-elens]').forEach(x=>x.classList.remove('on'));b.classList.add('on');eLens=b.dataset.elens;build();}));
document.getElementById('schemaBtn').addEventListener('click',function(){showSchema=!showSchema;this.classList.toggle('on',showSchema);build();});
document.getElementById('bodyBtn').addEventListener('click',function(){showBody=!showBody;this.classList.toggle('on',showBody);build();});
document.getElementById('spinBtn').addEventListener('click',function(){controls.autoRotate=!controls.autoRotate;controls.autoRotateSpeed=1.2;this.classList.toggle('on',controls.autoRotate);});
function setT(step){const s=Math.max(0,Math.min(STEPS,step));slider.value=s;T=s>=STEPS?t1:tAt(s);tlabel.textContent=s>=STEPS?'now':T.toISOString().slice(0,10);build();}
slider.addEventListener('input',()=>setT(+slider.value));
let play=null;document.getElementById('play').addEventListener('click',function(){
  if(play){clearInterval(play);play=null;this.textContent='▶';return;}
  this.textContent='⏸';if(+slider.value>=STEPS)setT(0);
  play=setInterval(()=>{const s=+slider.value;if(s>=STEPS){clearInterval(play);play=null;document.getElementById('play').textContent='▶';return;}setT(s+1);},700);});
build();  // 首次构建（explode() 挪到脚本末尾触发，避开 spawnStart 的 TDZ）

// ── 实时轮询：重取 → 重算布局/时间轴 → 重建（位置确定性=已有点留原位、新点平滑出现，
//    延时摄影用）。停在 now 时跟随新边；相机/镜头/焦点全程保留。────────────────
async function refresh(){
  try{
    const atNow=(+slider.value>=STEPS);
    ingest(await (await fetch('/dev/memory-graph')).json());
    computeLayout(); computeTimeline();
    if(atNow){T=t1;tlabel.textContent='now';}
    build();
  }catch(e){/* 网络抖动/写锁竞争 → 本轮跳过，下轮再来 */}
}
setInterval(refresh, 4000);

// ── ⑤ hover 聚焦 + 标签选中：悬停/点击 点 或 面/体标签 → 高亮/选中，其余调暗（每帧，不重建）──
let hover=null, hoverSet=new Set(), hoverFaceId=null;
function setHover(h){
  const key=h?h.type+':'+h.id:null, cur=hover?hover.type+':'+hover.id:null;
  if(key===cur)return;
  hover=h; hoverSet=new Set(); hoverFaceId=null;
  if(h&&h.type==='node'){hoverSet.add(h.id);edges.forEach(e=>{if(e.a===h.id)hoverSet.add(e.b);if(e.b===h.id)hoverSet.add(e.a);});}
  else if(h&&h.type==='face'){const f=faces.find(x=>x.id===h.id);if(f){(f.anchors||[]).forEach(a=>hoverSet.add(a));hoverSet.add('self');}hoverFaceId=h.id;}
  renderer.domElement.style.cursor=h?'pointer':'default';
}
function pickTarget(kind,id){ // 点击选中（点/面通用，与画布拾取同一套 focus 逻辑）
  focus=(focus&&focus.kind===kind&&focus.id===id)?null:{kind,id};
  if(focus)showDetail(kind,id);else detail.style.display='none';
  build();
}
renderer.domElement.addEventListener('pointermove',ev=>{
  const r=renderer.domElement.getBoundingClientRect();
  mouse.x=((ev.clientX-r.left)/r.width)*2-1;mouse.y=-((ev.clientY-r.top)/r.height)*2+1;ray.setFromCamera(mouse,camera);
  const ins=ray.intersectObjects(nodeSprites,false);
  setHover(ins.length?{type:'node',id:ins[0].object.userData.id}:null);
});
renderer.domElement.addEventListener('pointerleave',()=>setHover(null));
function applyHover(){
  const on=!!hover;
  for(const sp of nodeSprites){const base=sp.userData.baseOp==null?1:sp.userData.baseOp;
    const f=on?(hoverSet.has(sp.userData.id)?1:0.14):1;
    sp.material.opacity=base*f;
    const g=sp.userData.glow;if(g)g.material.opacity=g.userData.baseOp*f;}
}
// ── ①④ 标签预算 + 碰撞剔除 + 景深雾化（每帧）：按优先级贪心占位，重叠/超预算即隐藏，远则淡 ──
const tmpV=new THREE.Vector3();
function cullLabels(){
  const W=view.clientWidth,H=view.clientHeight, items=[];
  for(const o of labels3d){const el=o.element;if(!el)continue;
    o.getWorldPosition(tmpV);const dist=camera.position.distanceTo(tmpV);
    tmpV.project(camera);
    if(tmpV.z>1||tmpV.z<-1){el.classList.add('hide');continue;}
    const sx=(tmpV.x*0.5+0.5)*W, sy=(-tmpV.y*0.5+0.5)*H;
    const fade=Math.max(0.12,Math.min(1,1.75-(dist-5.5)/10)); // 景深：远=淡
    const w=(el.textContent||'').length*7.2+12, h=16;
    let prio=o.userData.prio||0, hl=false;
    if(hover){if(hoverSet.has(o.userData.nid)||(hoverFaceId&&o.userData.fid===hoverFaceId)){prio+=1e5;hl=true;}else prio-=1e3;}
    items.push({el,sx,sy,w,h,fade,prio,hl,base:o.userData.baseOp==null?1:o.userData.baseOp});}
  items.sort((a,b)=>b.prio-a.prio);
  const occ=[]; let shown=0; const MAX=44;
  for(const it of items){const{el,sx,sy,w,h}=it;
    const x0=sx-w/2,x1=sx+w/2,y0=sy-h/2,y1=sy+h/2;
    let ov=false;for(const r of occ){if(x0<r.x1&&x1>r.x0&&y0<r.y1&&y1>r.y0){ov=true;break;}}
    if(!it.hl&&(ov||shown>=MAX)){el.classList.add('hide');}
    else{el.classList.remove('hide');el.classList.toggle('hl',it.hl);
      let op=it.base*it.fade; if(hover&&!it.hl)op*=0.28;
      el.style.opacity=op; if(!it.hl){occ.push({x0,x1,y0,y1});shown++;}}}
}
// ── 爆炸成图动效：核心闪光 → 冲击波扩散 → 点涟漪式炸出(过冲 pop) → 镜头从近拉开揭全貌 ──
let spawnStart=0, spawning=false, camStart=null, camEnd=null, flashObj=null, shockObj=null;
const easeOut=t=>1-Math.pow(1-t,3);
const easeBack=t=>{const c1=2.4,c3=c1+1;return 1+c3*Math.pow(t-1,3)+c1*Math.pow(t-1,2);}; // 过冲后落定
function explode(){
  spawnStart=performance.now();spawning=true;controls.enabled=false; // 动效期间接管相机
  camEnd=camera.position.clone();camStart=camEnd.clone().multiplyScalar(0.38); // 从近处拉开
  flashObj=new THREE.Sprite(new THREE.SpriteMaterial({map:circleTex,color:0xffffff,transparent:true,opacity:0,depthTest:false,depthWrite:false,blending:THREE.AdditiveBlending}));
  flashObj.renderOrder=9;scene.add(flashObj);
  shockObj=new THREE.Mesh(new THREE.RingGeometry(0.5,0.68,72),new THREE.MeshBasicMaterial({color:0x9fc6ff,transparent:true,opacity:0,side:THREE.DoubleSide,depthWrite:false,blending:THREE.AdditiveBlending}));
  shockObj.rotation.x=-Math.PI/2;scene.add(shockObj);
}
function endSpawn(){spawning=false;controls.enabled=true;if(camEnd)camera.position.copy(camEnd);
  for(const sp of nodeSprites){sp.position.copy(sp.userData.target);sp.scale.setScalar(sp.userData.baseScale||sp.scale.x);sp.material.opacity=sp.userData.baseOp==null?1:sp.userData.baseOp;
    const g=sp.userData.glow;if(g){g.position.copy(sp.userData.target);g.scale.setScalar(g.userData.baseScale);g.material.opacity=g.userData.baseOp;}}
  graph.traverse(o=>{o.visible=true;});labelRenderer.domElement.style.opacity=1;
  if(flashObj){scene.remove(flashObj);flashObj=null;}if(shockObj){scene.remove(shockObj);shockObj=null;}}
function stepSpawn(){
  const el=performance.now()-spawnStart, TOTAL=1800;
  if(camStart&&camEnd){camera.position.lerpVectors(camStart,camEnd,easeOut(Math.min(1,el/1450)));camera.lookAt(controls.target);}
  if(flashObj){flashObj.material.opacity=Math.max(0,(el<90?el/90:1-(el-90)/340))*0.95;flashObj.scale.setScalar(0.4+Math.min(1,el/430)*3);}
  if(shockObj){const s=Math.min(1,el/740);shockObj.scale.setScalar(0.3+s*7.5);shockObj.material.opacity=Math.max(0,1-s)*0.7;}
  for(const sp of nodeSprites){const tgt=sp.userData.target;if(!tgt)continue;
    const delay=Math.min(tgt.length()*80,560), lp=Math.max(0,Math.min(1,(el-delay)/770)), eb=Math.max(0.05,easeBack(lp)), op=Math.min(1,lp*1.7);
    sp.position.copy(tgt).multiplyScalar(easeOut(lp));                    // 位置缓出飞到位
    sp.scale.setScalar((sp.userData.baseScale||sp.scale.x)*eb);           // 大小过冲 pop
    sp.material.opacity=(sp.userData.baseOp==null?1:sp.userData.baseOp)*op;
    const g=sp.userData.glow;if(g){g.position.copy(sp.position);g.scale.setScalar(g.userData.baseScale*eb);g.material.opacity=g.userData.baseOp*op;}}
  const decoOn=el>560;
  graph.traverse(o=>{if(o!==graph&&!o.userData.label&&o.userData.kind!=='node'&&!o.userData.glow&&!o.isCSS2DObject)o.visible=decoOn;});
  labelRenderer.domElement.style.opacity=Math.max(0,Math.min(1,(el-920)/560));
  if(el>TOTAL)endSpawn();
}
function tick(){controls.update();
  if(spawning)stepSpawn(); else applyHover();
  cullLabels();
  renderer.render(scene,camera);labelRenderer.render(scene,camera);requestAnimationFrame(tick);}
tick();
explode();  // 打开/刷新即播放「一点炸开成记忆图」入场动效（此处 spawnStart/spawning 已初始化）
window.addEventListener('resize',()=>{camera.aspect=view.clientWidth/view.clientHeight;camera.updateProjectionMatrix();renderer.setSize(view.clientWidth,view.clientHeight);labelRenderer.setSize(view.clientWidth,view.clientHeight);});
</script>
</body></html>
"""
