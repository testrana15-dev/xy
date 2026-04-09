import os
import re
import hmac
import hashlib
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
import uvicorn

# ─── Config ───────────────────────────────────────────────────────────────────
MONGO_URI      = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
PORT           = int(os.environ.get("PORT", 8000))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY     = os.environ.get("SECRET_KEY", "changeme_secret")

# ─── MongoDB ──────────────────────────────────────────────────────────────────
mclient    = AsyncIOMotorClient(MONGO_URI)
mdb        = mclient["yt_uploader_bot"]
videos_col = mdb["videos"]
vis_col    = mdb["visibility"]   # {_id: key, hidden: bool}

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# ─── Auth ─────────────────────────────────────────────────────────────────────
def make_token(pw: str) -> str:
    return hmac.new(SECRET_KEY.encode(), pw.encode(), hashlib.sha256).hexdigest()

def valid_token(token: str) -> bool:
    return hmac.compare_digest(token, make_token(ADMIN_PASSWORD))

async def require_admin(request: Request):
    token = request.headers.get("X-Admin-Token", "")
    if not valid_token(token):
        raise HTTPException(status_code=401, detail="Unauthorized")

# ─── Caption Parser ───────────────────────────────────────────────────────────
def parse_caption(caption: str) -> dict:
    result = {"title": "", "batch": "Unknown Batch", "topic": "General"}
    for line in caption.splitlines():
        line = line.strip()
        if re.search(r'File\s*Title', line, re.I):
            val = re.split(r':\s*', line, 1)[-1].strip()
            val = re.sub(r'\.[a-zA-Z0-9]{2,4}$', '', val)
            val = re.sub(r'\[\d{3,4}p\]', '', val, flags=re.I)
            result["title"] = val.strip()
        elif re.search(r'Batch\s*Name', line, re.I):
            result["batch"] = re.split(r':\s*', line, 1)[-1].strip()
        elif re.search(r'Topic\s*Name', line, re.I):
            result["topic"] = re.split(r'[:\s]\s*', line, 1)[-1].strip()
    return result

# ─── Public API ───────────────────────────────────────────────────────────────
@app.get("/api/data")
async def get_public_data():
    hidden_docs = await vis_col.find({"hidden": True}).to_list(5000)
    hidden_keys = {d["_id"] for d in hidden_docs}
    docs = await videos_col.find({}, {"caption": 1, "yt_link": 1, "yt_id": 1}).to_list(5000)
    batches: dict = {}
    for doc in docs:
        caption = doc.get("caption", "")
        yt_link = doc.get("yt_link", "")
        yt_id   = doc.get("yt_id", "")
        if not yt_link or not caption:
            continue
        p     = parse_caption(caption)
        batch = p["batch"] or "Unknown Batch"
        topic = p["topic"] or "General"
        title = p["title"] or caption[:60]
        if batch in hidden_keys or f"{batch}||{topic}" in hidden_keys:
            continue
        batches.setdefault(batch, {}).setdefault(topic, []).append(
            {"title": title, "yt_link": yt_link, "yt_id": yt_id}
        )
    return JSONResponse({"batches": batches})

# ─── Admin APIs ───────────────────────────────────────────────────────────────
@app.post("/api/admin/login")
async def admin_login(request: Request):
    body = await request.json()
    if body.get("password", "") != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Wrong password")
    return JSONResponse({"token": make_token(ADMIN_PASSWORD)})

@app.get("/api/admin/data")
async def get_admin_data(request: Request):
    await require_admin(request)
    hidden_docs = await vis_col.find({"hidden": True}).to_list(5000)
    hidden_keys = {d["_id"] for d in hidden_docs}
    docs = await videos_col.find({}, {"caption": 1, "yt_link": 1, "yt_id": 1}).to_list(5000)
    batches: dict = {}
    for doc in docs:
        caption = doc.get("caption", "")
        yt_link = doc.get("yt_link", "")
        yt_id   = doc.get("yt_id", "")
        if not yt_link or not caption:
            continue
        p     = parse_caption(caption)
        batch = p["batch"] or "Unknown Batch"
        topic = p["topic"] or "General"
        title = p["title"] or caption[:60]
        batches.setdefault(batch, {"hidden": batch in hidden_keys, "topics": {}})
        tkey = f"{batch}||{topic}"
        batches[batch]["topics"].setdefault(topic, {"hidden": tkey in hidden_keys, "lectures": []})
        batches[batch]["topics"][topic]["lectures"].append({"title": title, "yt_id": yt_id})
    return JSONResponse({"batches": batches})

@app.post("/api/admin/toggle")
async def toggle_visibility(request: Request):
    await require_admin(request)
    body = await request.json()
    key  = body.get("key")
    hidden = body.get("hidden")
    if not key:
        raise HTTPException(status_code=400, detail="key required")
    await vis_col.update_one({"_id": key}, {"$set": {"hidden": hidden}}, upsert=True)
    return JSONResponse({"ok": True})

# ─── Main Website ─────────────────────────────────────────────────────────────
MAIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>StudyVault</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Figtree:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
:root{--bg:#07090f;--surface:#0e1220;--card:#131829;--border:#1e2538;--accent:#5865f2;--glow:#5865f220;--cyan:#22d3ee;--text:#e2e8f0;--muted:#64748b;--r:12px}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Figtree',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:14px;padding:14px 24px;background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100}
.logo{font-family:'Syne',sans-serif;font-weight:800;font-size:1.4rem;background:linear-gradient(135deg,#5865f2,#22d3ee);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.layout{display:flex;flex:1}
.sidebar{width:280px;min-width:240px;background:var(--surface);border-right:1px solid var(--border);overflow-y:auto;position:sticky;top:57px;height:calc(100vh - 57px)}
.sb-title{font-family:'Syne',sans-serif;font-size:.65rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);padding:20px 16px 10px}
.batch-item{border-left:3px solid transparent;transition:all .2s}
.batch-item.active{border-left-color:var(--accent);background:var(--glow)}
.batch-hdr{display:flex;align-items:center;gap:10px;padding:10px 16px;font-size:.85rem;font-weight:600;cursor:pointer}
.batch-hdr:hover{color:var(--cyan)}
.b-icon{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,#5865f2,#22d3ee);display:flex;align-items:center;justify-content:center;font-size:.75rem;flex-shrink:0;font-family:'Syne',sans-serif;font-weight:700}
.b-name{flex:1;line-height:1.3}
.b-cnt{font-size:.7rem;background:var(--border);padding:2px 7px;border-radius:20px;color:var(--muted)}
.topic-list{display:none}
.batch-item.active .topic-list{display:block}
.topic-item{display:flex;align-items:center;gap:8px;padding:8px 16px 8px 26px;cursor:pointer;font-size:.8rem;color:var(--muted);transition:color .15s}
.topic-item:hover,.topic-item.active{color:var(--cyan)}
.topic-item.active::before{content:'';width:5px;height:5px;border-radius:50%;background:var(--cyan);flex-shrink:0}
.main{flex:1;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:24px}
/* Player */
.player-section{display:none;flex-direction:column;gap:12px}
.player-section.visible{display:flex}
.now-lbl{font-family:'Syne',sans-serif;font-size:.65rem;letter-spacing:2px;text-transform:uppercase;color:var(--accent)}
.now-ttl{font-family:'Syne',sans-serif;font-size:1.25rem;font-weight:700;margin-top:4px}
.pw{position:relative;width:100%;aspect-ratio:16/9;background:#000;border-radius:var(--r);overflow:hidden;box-shadow:0 0 60px #5865f220,0 20px 60px #00000080}
.pw iframe{position:absolute;top:-60px;left:0;width:100%;height:calc(100% + 120px);border:none;pointer-events:none}
.cov{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:flex-end;cursor:pointer;z-index:10;transition:background .3s}
.pw:hover .cov{background:linear-gradient(transparent 40%,#000000c0)}
.ctrls{display:flex;align-items:center;gap:8px;padding:10px 14px;opacity:0;transform:translateY(6px);transition:all .25s;flex-wrap:wrap}
.pw:hover .ctrls{opacity:1;transform:translateY(0)}
.cb{background:none;border:none;color:#fff;cursor:pointer;padding:4px;border-radius:6px;display:flex;align-items:center;transition:background .15s;flex-shrink:0}
.cb:hover{background:rgba(255,255,255,.15)}
.cb svg{width:18px;height:18px}
.prog{flex:1;min-width:80px;height:4px;background:rgba(255,255,255,.2);border-radius:4px;cursor:pointer}
.prog-f{height:100%;border-radius:4px;background:linear-gradient(90deg,#5865f2,#22d3ee);width:0%;transition:width .5s linear}
.tdisp{font-size:.72rem;color:rgba(255,255,255,.8);white-space:nowrap;font-variant-numeric:tabular-nums}
.csel{background:#1a1f35;border:1px solid #1e2538;color:#fff;font-size:.72rem;padding:3px 8px;border-radius:6px;cursor:pointer;outline:none}
.csel option{background:#1a1f35}
.vw{display:flex;align-items:center;gap:6px}
.vs{width:55px;height:4px;-webkit-appearance:none;appearance:none;background:rgba(255,255,255,.2);border-radius:4px;cursor:pointer}
.vs::-webkit-slider-thumb{-webkit-appearance:none;width:12px;height:12px;background:#fff;border-radius:50%}
.cplay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;opacity:0;transition:opacity .2s;pointer-events:none}
.pw.paused .cplay{opacity:1}
.cpb{width:64px;height:64px;background:rgba(88,101,242,.85);border-radius:50%;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(8px)}
/* Lectures */
.slbl{font-family:'Syne',sans-serif;font-size:.65rem;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:12px}
.lgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.lcard{background:var(--card);border:1px solid var(--border);border-radius:var(--r);padding:14px;cursor:pointer;display:flex;gap:12px;align-items:flex-start;transition:all .2s}
.lcard:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:0 8px 30px #5865f220}
.lcard.playing{border-color:var(--cyan);background:#0e1f2a}
.lnum{width:32px;height:32px;background:var(--border);border-radius:8px;display:flex;align-items:center;justify-content:center;font-family:'Syne',sans-serif;font-weight:700;font-size:.75rem;color:var(--muted);flex-shrink:0}
.lcard.playing .lnum{background:var(--cyan);color:#000}
.linf{flex:1;min-width:0}
.lttl{font-size:.85rem;font-weight:600;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.lbdg{display:inline-flex;align-items:center;gap:4px;font-size:.65rem;color:var(--cyan);margin-top:6px}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:300px;gap:12px;color:var(--muted);text-align:center}
.loading{display:flex;align-items:center;justify-content:center;height:60vh;gap:12px;color:var(--muted)}
.spin{width:24px;height:24px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
@media(max-width:700px){.layout{flex-direction:column}.sidebar{width:100%;height:auto;position:relative;top:0;border-right:none;border-bottom:1px solid var(--border)}.main{padding:12px}.lgrid{grid-template-columns:1fr}.vw,.csel{display:none}}
</style>
</head>
<body>
<header>
  <div class="logo">StudyVault</div>
  <span style="margin-left:auto;font-size:.75rem;color:var(--muted)">Premium Learning</span>
</header>
<div class="layout">
  <nav class="sidebar">
    <div class="sb-title">Batches</div>
    <div id="bList"><div class="loading"><div class="spin"></div></div></div>
  </nav>
  <main class="main" id="main">
    <section class="player-section" id="pSec">
      <div><div class="now-lbl">&#9654; Now Playing</div><div class="now-ttl" id="nTitle">—</div></div>
      <div class="pw paused" id="pw">
        <div id="ytP"></div>
        <div class="cov" onclick="tPlay()">
          <div class="cplay"><div class="cpb"><svg viewBox="0 0 24 24" fill="white" width="28" height="28"><path d="M8 5v14l11-7z"/></svg></div></div>
          <div class="ctrls" onclick="event.stopPropagation()">
            <button class="cb" onclick="tPlay()"><svg id="pIco" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></button>
            <span class="tdisp" id="tDisp">0:00 / 0:00</span>
            <div class="prog" id="prog" onclick="seekC(event)"><div class="prog-f" id="progF"></div></div>
            <div class="vw">
              <button class="cb" onclick="tMute()"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/></svg></button>
              <input type="range" class="vs" min="0" max="100" value="100" oninput="setVol(this.value)"/>
            </div>
            <select class="csel" onchange="setSp(this.value)" title="Speed">
              <option value="0.5">0.5x</option><option value="0.75">0.75x</option>
              <option value="1" selected>1x</option><option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option><option value="1.75">1.75x</option>
              <option value="2">2x</option>
            </select>
            <select class="csel" id="qSel" onchange="setQ(this.value)" title="Quality">
              <option value="auto">Auto</option>
            </select>
            <button class="cb" onclick="tFS()"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg></button>
          </div>
        </div>
      </div>
    </section>
    <section id="lecSec">
      <div class="empty" id="emp">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor" style="opacity:.3"><path d="M12 3L1 9l11 6 9-4.91V17h2V9L12 3zM5 13.18v4L12 21l7-3.82v-4L12 17l-7-3.82z"/></svg>
        <div>Sidebar se batch aur topic select karo</div>
      </div>
      <div id="lecList" style="display:none">
        <div class="slbl" id="tLbl">Lectures</div>
        <div class="lgrid" id="lGrid"></div>
      </div>
    </section>
  </main>
</div>
<script src="https://www.youtube.com/iframe_api"></script>
<script>
let D={},pl=null,pI=null,muted=false;
async function init(){
  try{const r=await fetch('/api/data');const j=await r.json();D=j.batches||{};rSB();}
  catch(e){document.getElementById('bList').innerHTML='<div class="empty" style="height:200px">❌ Data load failed</div>';}
}
function rSB(){
  const bs=Object.keys(D);
  if(!bs.length){document.getElementById('bList').innerHTML='<div class="empty" style="height:200px">Koi video nahi</div>';return;}
  document.getElementById('bList').innerHTML=bs.map((b,bi)=>{
    const ts=Object.keys(D[b]),tot=ts.reduce((s,t)=>s+D[b][t].length,0);
    const ic=b.substring(0,2).toUpperCase();
    return`<div class="batch-item" id="bi${bi}">
      <div class="batch-hdr" onclick="tBatch(${bi})">
        <div class="b-icon">${ic}</div><div class="b-name">${b}</div><div class="b-cnt">${tot}</div>
      </div>
      <div class="topic-list">${ts.map((t,ti)=>`<div class="topic-item" id="ti${bi}_${ti}" onclick="sTopic('${esc(b)}','${esc(t)}',${bi},${ti})">${t}</div>`).join('')}</div>
    </div>`;
  }).join('');
}
function tBatch(bi){document.querySelectorAll('.batch-item').forEach((e,i)=>e.classList.toggle('active',i===bi));}
function sTopic(b,t,bi,ti){
  tBatch(bi);
  document.querySelectorAll('.topic-item').forEach(e=>e.classList.remove('active'));
  const el=document.getElementById(`ti${bi}_${ti}`);if(el)el.classList.add('active');
  const ls=D[b]?.[t]||[];
  document.getElementById('emp').style.display='none';
  document.getElementById('lecList').style.display='block';
  document.getElementById('tLbl').textContent=t;
  document.getElementById('lGrid').innerHTML=ls.map((l,i)=>
    `<div class="lcard" id="lc${i}" onclick="play('${esc(l.yt_id)}','${esc(l.title)}',${i})">
      <div class="lnum">${String(i+1).padStart(2,'0')}</div>
      <div class="linf"><div class="lttl">${l.title}</div><div class="lbdg">&#9654; Watch Lecture</div></div>
    </div>`).join('');
  document.getElementById('main').scrollTo({top:0,behavior:'smooth'});
}
function onYouTubeIframeAPIReady(){}
function play(vid,title,idx){
  document.getElementById('nTitle').textContent=title;
  document.getElementById('pSec').classList.add('visible');
  document.querySelectorAll('.lcard').forEach((c,i)=>c.classList.toggle('playing',i===idx));
  if(pl&&pl.loadVideoById){pl.loadVideoById(vid);pState(true);}
  else{
    if(pl){try{pl.destroy();}catch(e){}}
    pl=new YT.Player('ytP',{
      videoId:vid,
      playerVars:{controls:0,modestbranding:1,rel:0,showinfo:0,iv_load_policy:3,disablekb:1,fs:0,playsinline:1,origin:location.origin,enablejsapi:1},
      events:{onReady:e=>{e.target.playVideo();pState(true);},onStateChange:sCh}
    });
  }
  document.getElementById('main').scrollTo({top:0,behavior:'smooth'});
}
function sCh(e){
  if(e.data===YT.PlayerState.PLAYING){pState(true);stP();lQual();}
  else if(e.data===YT.PlayerState.PAUSED||e.data===YT.PlayerState.ENDED){pState(false);spP();}
}
function pState(playing){
  document.getElementById('pw').classList.toggle('paused',!playing);
  document.getElementById('pIco').innerHTML=playing?'<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>':'<path d="M8 5v14l11-7z"/>';
}
function tPlay(){if(!pl)return;pl.getPlayerState()===YT.PlayerState.PLAYING?pl.pauseVideo():pl.playVideo();}
function stP(){spP();pI=setInterval(()=>{
  if(!pl||!pl.getDuration)return;
  const c=pl.getCurrentTime()||0,d=pl.getDuration()||0;
  if(d>0){document.getElementById('progF').style.width=(c/d*100)+'%';document.getElementById('tDisp').textContent=`${fmt(c)} / ${fmt(d)}`;}
},500);}
function spP(){if(pI)clearInterval(pI);}
function seekC(e){if(!pl||!pl.getDuration)return;const b=document.getElementById('prog');pl.seekTo((e.offsetX/b.offsetWidth)*pl.getDuration(),true);}
function setVol(v){if(pl)pl.setVolume(parseInt(v));}
function tMute(){if(!pl)return;muted=!muted;muted?pl.mute():pl.unMute();}
function setSp(v){if(pl)pl.setPlaybackRate(parseFloat(v));}
function setQ(v){if(pl)pl.setPlaybackQuality(v==='auto'?'default':v);}
function lQual(){
  if(!pl||!pl.getAvailableQualityLevels)return;
  const lvls=pl.getAvailableQualityLevels(),cur=pl.getPlaybackQuality();
  document.getElementById('qSel').innerHTML='<option value="auto">Auto</option>'+lvls.map(q=>`<option value="${q}"${q===cur?' selected':''}>${q}</option>`).join('');
}
function tFS(){const w=document.getElementById('pw');document.fullscreenElement?document.exitFullscreen():w.requestFullscreen();}
function fmt(s){const m=Math.floor(s/60),sc=Math.floor(s%60);return`${m}:${sc.toString().padStart(2,'0')}`;}
function esc(s){return(s||'').replace(/\\\\/g,'\\\\\\\\').replace(/'/g,"\\\\'")}
init();
</script>
</body>
</html>"""

# ─── Admin Panel ──────────────────────────────────────────────────────────────
ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Admin — StudyVault</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Figtree:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
:root{--bg:#07090f;--surface:#0e1220;--card:#131829;--border:#1e2538;--accent:#5865f2;--green:#22c55e;--red:#ef4444;--text:#e2e8f0;--muted:#64748b;--r:10px}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Figtree',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
#ls{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.lb{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:40px;width:100%;max-width:380px;text-align:center}
.ll{font-family:'Syne',sans-serif;font-size:1.8rem;font-weight:800;background:linear-gradient(135deg,#5865f2,#22d3ee);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}
.ls{color:var(--muted);font-size:.85rem;margin-bottom:28px}
.inp{width:100%;background:var(--card);border:1px solid var(--border);color:var(--text);padding:12px 16px;border-radius:var(--r);font-size:.9rem;outline:none;margin-bottom:14px;font-family:'Figtree',sans-serif}
.inp:focus{border-color:var(--accent)}
.btn{width:100%;background:var(--accent);color:#fff;border:none;padding:12px;border-radius:var(--r);font-size:.9rem;font-weight:600;cursor:pointer;font-family:'Figtree',sans-serif}
.btn:hover{opacity:.85}
.em{color:#ef4444;font-size:.8rem;margin-top:8px;display:none}
#app{display:none}
header{display:flex;align-items:center;gap:12px;padding:14px 24px;background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100}
.logo{font-family:'Syne',sans-serif;font-weight:800;font-size:1.2rem;background:linear-gradient(135deg,#5865f2,#22d3ee);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.bdg{background:#5865f220;color:#5865f2;font-size:.7rem;padding:3px 10px;border-radius:20px;font-weight:600}
.lout{margin-left:auto;background:none;border:1px solid var(--border);color:var(--muted);padding:6px 14px;border-radius:var(--r);cursor:pointer;font-size:.8rem;font-family:'Figtree',sans-serif}
.lout:hover{border-color:var(--red);color:var(--red)}
.wrap{max-width:900px;margin:0 auto;padding:24px}
.pt{font-family:'Syne',sans-serif;font-size:1.4rem;font-weight:700;margin-bottom:4px}
.ps{color:var(--muted);font-size:.85rem;margin-bottom:24px}
.bb{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);margin-bottom:14px;overflow:hidden}
.br{display:flex;align-items:center;gap:12px;padding:14px 16px;cursor:pointer}
.br:hover{background:rgba(255,255,255,.02)}
.bic{width:34px;height:34px;border-radius:8px;background:linear-gradient(135deg,#5865f2,#22d3ee);display:flex;align-items:center;justify-content:center;font-family:'Syne',sans-serif;font-weight:700;font-size:.75rem;flex-shrink:0}
.btn2{flex:1;font-weight:600;font-size:.9rem;text-align:left}
.lcc{font-size:.75rem;color:var(--muted)}
.tog{position:relative;width:44px;height:24px;flex-shrink:0}
.tog input{opacity:0;width:0;height:0}
.sl{position:absolute;inset:0;background:#333;border-radius:24px;cursor:pointer;transition:.3s}
.sl::before{content:'';position:absolute;height:18px;width:18px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.3s}
input:checked+.sl{background:var(--green)}
input:checked+.sl::before{transform:translateX(20px)}
.tp{display:none;border-top:1px solid var(--border);padding:0 16px 12px}
.bb.open .tp{display:block}
.chv{transition:transform .3s;color:var(--muted)}
.bb.open .chv{transform:rotate(180deg)}
.tr{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--border)}
.tr:last-child{border-bottom:none}
.tn{flex:1;font-size:.85rem}
.tc{font-size:.72rem;color:var(--muted)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--green);flex-shrink:0}
.dot.h{background:var(--red)}
.loading{display:flex;align-items:center;justify-content:center;height:200px;gap:12px;color:var(--muted)}
.spin{width:24px;height:24px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.toast{position:fixed;bottom:24px;right:24px;background:var(--green);color:#000;padding:10px 20px;border-radius:var(--r);font-size:.85rem;font-weight:600;opacity:0;transition:opacity .3s;pointer-events:none;z-index:999}
.toast.show{opacity:1}
</style>
</head>
<body>
<div id="ls">
  <div class="lb">
    <div class="ll">StudyVault</div>
    <div class="ls">Admin Panel &mdash; Restricted Access</div>
    <input type="password" class="inp" id="pw" placeholder="Password..." onkeydown="if(event.key==='Enter')login()"/>
    <button class="btn" onclick="login()">Login</button>
    <div class="em" id="em">&#10060; Wrong password</div>
  </div>
</div>
<div id="app">
  <header>
    <div class="logo">StudyVault</div>
    <span class="bdg">Admin</span>
    <button class="lout" onclick="logout()">Logout</button>
  </header>
  <div class="wrap">
    <div class="pt">Visibility Control</div>
    <div class="ps">Batches aur topics show/hide karo &mdash; instantly website pe reflect hoga.</div>
    <div id="cnt"><div class="loading"><div class="spin"></div><span>Loading...</span></div></div>
  </div>
</div>
<div class="toast" id="toast">&#10003; Saved!</div>
<script>
let TOK=localStorage.getItem('sv_tok')||'';
let BD={};
async function login(){
  const pw=document.getElementById('pw').value;
  try{
    const r=await fetch('/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
    if(!r.ok){document.getElementById('em').style.display='block';return;}
    const j=await r.json();TOK=j.token;localStorage.setItem('sv_tok',TOK);showApp();
  }catch(e){document.getElementById('em').style.display='block';}
}
function logout(){localStorage.removeItem('sv_tok');location.reload();}
function showApp(){document.getElementById('ls').style.display='none';document.getElementById('app').style.display='block';load();}
if(TOK)showApp();
async function load(){
  try{
    const r=await fetch('/api/admin/data',{headers:{'X-Admin-Token':TOK}});
    if(r.status===401){logout();return;}
    const j=await r.json();BD=j.batches||{};render();
  }catch(e){document.getElementById('cnt').innerHTML='<div class="loading">&#10060; Load failed</div>';}
}
function render(){
  const bs=Object.keys(BD);
  if(!bs.length){document.getElementById('cnt').innerHTML='<div class="loading">Koi data nahi &mdash; pehle bot se video upload karo</div>';return;}
  document.getElementById('cnt').innerHTML=bs.map((b,bi)=>{
    const bd=BD[b],ts=Object.keys(bd.topics||{});
    const tot=ts.reduce((s,t)=>s+bd.topics[t].lectures.length,0);
    const ic=b.substring(0,2).toUpperCase();
    const tRows=ts.map(t=>{
      const td=bd.topics[t],tk=encodeURIComponent(b+'||'+t);
      return`<div class="tr">
        <div class="dot${td.hidden?' h':''}"></div>
        <div class="tn">${t}</div>
        <div class="tc">${td.lectures.length} lec</div>
        <label class="tog"><input type="checkbox"${!td.hidden?' checked':''} onchange="tog(decodeURIComponent('${tk}'),!this.checked)"/><span class="sl"></span></label>
      </div>`;
    }).join('');
    return`<div class="bb" id="bb${bi}">
      <div class="br" onclick="tBlock(${bi})">
        <div class="bic">${ic}</div>
        <div class="btn2">${b}</div>
        <div class="lcc">${tot} lectures &middot; ${ts.length} topics</div>
        <label class="tog" onclick="event.stopPropagation()">
          <input type="checkbox"${!bd.hidden?' checked':''} onchange="tog('${encodeURIComponent(b)}',!this.checked,true)"/><span class="sl"></span>
        </label>
        <svg class="chv" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M7 10l5 5 5-5z"/></svg>
      </div>
      <div class="tp">${tRows}</div>
    </div>`;
  }).join('');
}
function tBlock(bi){document.getElementById(`bb${bi}`).classList.toggle('open');}
async function tog(key,hidden){
  try{
    await fetch('/api/admin/toggle',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':TOK},body:JSON.stringify({key,hidden})});
    showToast();
  }catch(e){alert('Save failed!');}
}
function showToast(){const t=document.getElementById('toast');t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2000);}
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(MAIN_HTML)

@app.get("/ranaji", response_class=HTMLResponse)
async def admin_panel():
    return HTMLResponse(ADMIN_HTML)

if __name__ == "__main__":
    uvicorn.run("web:app", host="0.0.0.0", port=PORT, reload=False)

