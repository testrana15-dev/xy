import os
import re
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from motor.motor_asyncio import AsyncIOMotorClient
import uvicorn

# ─── Config ───────────────────────────────────────────────────────────────────
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
PORT      = int(os.environ.get("PORT", 8000))

# ─── MongoDB ──────────────────────────────────────────────────────────────────
client = AsyncIOMotorClient(MONGO_URI)
db     = client["yt_uploader_bot"]
col    = db["videos"]

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# ─── Caption Parser ───────────────────────────────────────────────────────────
def parse_caption(caption: str) -> dict:
    """
    Caption format:
      [🎥]Vid Id : 62
      File Title :  Basic Maths L1 [720p].mkv
      Batch Name : IAT & NEST 2026 Complete Combo
      Topic Name: Daily Class Recordings & Notes
      Extracted By ➤ CourierWell
    """
    result = {"title": "", "batch": "Unknown Batch", "topic": "General"}
    for line in caption.splitlines():
        line = line.strip()
        if re.search(r'File\s*Title', line, re.I):
            val = re.split(r':\s*', line, 1)[-1].strip()
            val = re.sub(r'\.[a-zA-Z0-9]{2,4}$', '', val)          # remove extension
            val = re.sub(r'\[\d{3,4}p\]', '', val, flags=re.I)     # remove [720p]
            val = re.sub(r'\(.*?quality.*?\)', '', val, flags=re.I) # remove quality
            result["title"] = val.strip()
        elif re.search(r'Batch\s*Name', line, re.I):
            result["batch"] = re.split(r':\s*', line, 1)[-1].strip()
        elif re.search(r'Topic\s*Name', line, re.I):
            result["topic"] = re.split(r'[:\s]\s*', line, 1)[-1].strip()
    return result

# ─── API Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/data")
async def get_data():
    """
    Return full structured data:
    { batches: { batch_name: { topic_name: [ {title, yt_link, yt_id} ] } } }
    """
    docs = await col.find({}, {"caption": 1, "yt_link": 1, "yt_id": 1}).to_list(5000)

    batches: dict = {}
    for doc in docs:
        caption  = doc.get("caption", "")
        yt_link  = doc.get("yt_link", "")
        yt_id    = doc.get("yt_id", "")

        if not yt_link or not caption:
            continue

        parsed = parse_caption(caption)
        batch  = parsed["batch"]  or "Unknown Batch"
        topic  = parsed["topic"]  or "General"
        title  = parsed["title"]  or caption[:60]

        batches.setdefault(batch, {}).setdefault(topic, []).append({
            "title":   title,
            "yt_link": yt_link,
            "yt_id":   yt_id,
        })

    return JSONResponse({"batches": batches})


# ─── Frontend HTML ─────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>StudyVault</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=Figtree:wght@300;400;500;600&display=swap" rel="stylesheet"/>
<style>
:root {
  --bg:      #07090f;
  --surface: #0e1220;
  --card:    #131829;
  --border:  #1e2538;
  --accent:  #5865f2;
  --glow:    #5865f230;
  --cyan:    #22d3ee;
  --text:    #e2e8f0;
  --muted:   #64748b;
  --radius:  12px;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: 'Figtree', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
/* ── Header ── */
header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 24px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 100;
}
.logo {
  font-family: 'Syne', sans-serif;
  font-weight: 800;
  font-size: 1.4rem;
  background: linear-gradient(135deg, var(--accent), var(--cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -0.5px;
}
.logo-dot { color: var(--cyan); }
header .tagline {
  font-size: 0.75rem;
  color: var(--muted);
  margin-left: auto;
}
/* ── Layout ── */
.layout {
  display: flex;
  flex: 1;
  min-height: 0;
}
/* ── Sidebar ── */
.sidebar {
  width: 280px;
  min-width: 240px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 57px;
  height: calc(100vh - 57px);
}
.sidebar-title {
  font-family: 'Syne', sans-serif;
  font-size: 0.65rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--muted);
  padding: 20px 16px 10px;
}
.batch-item {
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: all 0.2s;
}
.batch-item.active {
  border-left-color: var(--accent);
  background: var(--glow);
}
.batch-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
}
.batch-header:hover { color: var(--cyan); }
.batch-icon {
  width: 30px; height: 30px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), var(--cyan));
  display: flex; align-items: center; justify-content: center;
  font-size: 0.75rem;
  flex-shrink: 0;
  font-family: 'Syne', sans-serif;
  font-weight: 700;
}
.batch-name { flex: 1; line-height: 1.3; }
.batch-count {
  font-size: 0.7rem;
  background: var(--border);
  padding: 2px 7px;
  border-radius: 20px;
  color: var(--muted);
}
.topic-list { display: none; }
.batch-item.active .topic-list { display: block; }
.topic-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px 8px 26px;
  cursor: pointer;
  font-size: 0.8rem;
  color: var(--muted);
  transition: color 0.15s;
}
.topic-item:hover, .topic-item.active { color: var(--cyan); }
.topic-item.active::before {
  content: '';
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--cyan);
  flex-shrink: 0;
}
/* ── Main ── */
.main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
/* ── Player ── */
.player-section {
  display: none;
  flex-direction: column;
  gap: 12px;
}
.player-section.visible { display: flex; }
.player-meta .now-label {
  font-size: 0.65rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--accent);
  font-family: 'Syne', sans-serif;
}
.player-meta .now-title {
  font-family: 'Syne', sans-serif;
  font-size: 1.4rem;
  font-weight: 700;
  margin-top: 4px;
  line-height: 1.3;
}
/* Custom Player Wrapper */
.player-wrapper {
  position: relative;
  width: 100%;
  aspect-ratio: 16/9;
  background: #000;
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: 0 0 60px #5865f220, 0 20px 60px #00000080;
}
.player-wrapper iframe {
  position: absolute;
  top: -60px; left: 0;
  width: 100%;
  height: calc(100% + 120px);  /* Hide top & bottom bars */
  border: none;
  pointer-events: none;         /* Our controls handle events */
}
/* Custom Controls */
.ctrl-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  background: transparent;
  transition: background 0.3s;
  z-index: 10;
  cursor: pointer;
}
.player-wrapper:hover .ctrl-overlay { background: linear-gradient(transparent 50%, #00000090); }
.controls {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  opacity: 0;
  transform: translateY(8px);
  transition: all 0.25s;
}
.player-wrapper:hover .controls { opacity: 1; transform: translateY(0); }
.ctrl-btn {
  background: none;
  border: none;
  color: white;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  transition: background 0.15s;
  flex-shrink: 0;
}
.ctrl-btn:hover { background: rgba(255,255,255,0.15); }
.ctrl-btn svg { width: 20px; height: 20px; }
.progress-bar {
  flex: 1;
  height: 4px;
  background: rgba(255,255,255,0.2);
  border-radius: 4px;
  cursor: pointer;
  position: relative;
}
.progress-fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--accent), var(--cyan));
  width: 0%;
  transition: width 0.5s linear;
}
.ctrl-time {
  font-size: 0.75rem;
  color: rgba(255,255,255,0.8);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.vol-wrap { display: flex; align-items: center; gap: 6px; }
.vol-slider {
  width: 60px; height: 4px;
  background: rgba(255,255,255,0.2);
  border-radius: 4px;
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
}
.vol-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 12px; height: 12px;
  background: white;
  border-radius: 50%;
}
/* Center play button */
.center-play {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
}
.player-wrapper.paused .center-play { opacity: 1; }
.center-play-btn {
  width: 64px; height: 64px;
  background: rgba(88,101,242,0.85);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(8px);
}
/* ── Lecture Grid ── */
.section-label {
  font-family: 'Syne', sans-serif;
  font-size: 0.65rem;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 12px;
}
.lecture-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.lecture-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  cursor: pointer;
  display: flex;
  gap: 12px;
  align-items: flex-start;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;
}
.lecture-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--glow), transparent);
  opacity: 0;
  transition: opacity 0.2s;
}
.lecture-card:hover { border-color: var(--accent); transform: translateY(-2px); box-shadow: 0 8px 30px #5865f220; }
.lecture-card:hover::before { opacity: 1; }
.lecture-card.playing { border-color: var(--cyan); background: #0e1f2a; }
.lec-num {
  width: 32px; height: 32px;
  background: var(--border);
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Syne', sans-serif;
  font-weight: 700;
  font-size: 0.75rem;
  color: var(--muted);
  flex-shrink: 0;
}
.lecture-card.playing .lec-num { background: var(--cyan); color: #000; }
.lec-info { flex: 1; min-width: 0; }
.lec-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.lec-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.65rem;
  color: var(--cyan);
  margin-top: 6px;
}
/* ── Empty / Loading states ── */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  gap: 12px;
  color: var(--muted);
  text-align: center;
}
.empty svg { opacity: 0.3; }
.loading {
  display: flex; align-items: center; justify-content: center;
  height: 60vh; gap: 12px; color: var(--muted);
}
.spinner {
  width: 24px; height: 24px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
/* ── Mobile ── */
@media (max-width: 700px) {
  .layout { flex-direction: column; }
  .sidebar { width: 100%; height: auto; position: relative; top: 0; border-right: none; border-bottom: 1px solid var(--border); }
  .main { padding: 12px; }
  .lecture-grid { grid-template-columns: 1fr; }
  .vol-wrap { display: none; }
}
</style>
</head>
<body>

<header>
  <div class="logo">Study<span class="logo-dot">Vault</span></div>
  <span class="tagline">Premium Learning Platform</span>
</header>

<div class="layout">
  <!-- Sidebar -->
  <nav class="sidebar" id="sidebar">
    <div class="sidebar-title">Batches</div>
    <div id="batchList"><div class="loading"><div class="spinner"></div></div></div>
  </nav>

  <!-- Main Content -->
  <main class="main" id="main">
    <!-- Player -->
    <section class="player-section" id="playerSection">
      <div class="player-meta">
        <div class="now-label">▶ Now Playing</div>
        <div class="now-title" id="nowTitle">—</div>
      </div>
      <div class="player-wrapper paused" id="playerWrapper">
        <div id="ytPlayer"></div>
        <div class="ctrl-overlay" onclick="togglePlay()">
          <div class="center-play">
            <div class="center-play-btn">
              <svg viewBox="0 0 24 24" fill="white" width="28" height="28"><path d="M8 5v14l11-7z"/></svg>
            </div>
          </div>
          <div class="controls" onclick="event.stopPropagation()">
            <button class="ctrl-btn" id="playBtn" onclick="togglePlay()">
              <svg id="playIcon" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            </button>
            <span class="ctrl-time" id="timeDisplay">0:00 / 0:00</span>
            <div class="progress-bar" id="progressBar" onclick="seekClick(event)">
              <div class="progress-fill" id="progressFill"></div>
            </div>
            <div class="vol-wrap">
              <button class="ctrl-btn" onclick="toggleMute()">
                <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/></svg>
              </button>
              <input type="range" class="vol-slider" min="0" max="100" value="100" id="volSlider" oninput="setVolume(this.value)"/>
            </div>
            <button class="ctrl-btn" onclick="toggleFullscreen()">
              <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- Lecture List -->
    <section id="lectureSection">
      <div class="empty" id="emptyState">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3L1 9l11 6 9-4.91V17h2V9L12 3zM5 13.18v4L12 21l7-3.82v-4L12 17l-7-3.82z"/></svg>
        <div>Sidebar se ek batch aur topic select karo</div>
      </div>
      <div id="lectureList" style="display:none">
        <div class="section-label" id="topicLabel">Lectures</div>
        <div class="lecture-grid" id="lectureGrid"></div>
      </div>
    </section>
  </main>
</div>

<!-- YouTube IFrame API -->
<script src="https://www.youtube.com/iframe_api"></script>
<script>
let DATA = {};
let player = null;
let ytReady = false;
let progressInterval = null;
let currentVideoId = null;
let isMuted = false;

// ── Load Data ──────────────────────────────────────────────────────────────
async function loadData() {
  try {
    const res = await fetch('/api/data');
    const json = await res.json();
    DATA = json.batches || {};
    renderSidebar();
  } catch (e) {
    document.getElementById('batchList').innerHTML =
      '<div class="empty" style="height:200px">❌ Data load nahi hua</div>';
  }
}

// ── Sidebar ─────────────────────────────────────────────────────────────────
function renderSidebar() {
  const batches = Object.keys(DATA);
  if (!batches.length) {
    document.getElementById('batchList').innerHTML =
      '<div class="empty" style="height:200px">Koi video nahi mili</div>';
    return;
  }
  const html = batches.map((batch, bi) => {
    const topics = Object.keys(DATA[batch]);
    const totalLecs = topics.reduce((s, t) => s + DATA[batch][t].length, 0);
    const icon = batch.substring(0,2).toUpperCase();
    const topicsHtml = topics.map((topic, ti) =>
      `<div class="topic-item" id="topic-${bi}-${ti}"
            onclick="selectTopic('${esc(batch)}','${esc(topic)}',${bi},${ti})">
         ${topic}
       </div>`
    ).join('');
    return `<div class="batch-item" id="batch-${bi}">
      <div class="batch-header" onclick="toggleBatch(${bi})">
        <div class="batch-icon">${icon}</div>
        <div class="batch-name">${batch}</div>
        <div class="batch-count">${totalLecs}</div>
      </div>
      <div class="topic-list">${topicsHtml}</div>
    </div>`;
  }).join('');
  document.getElementById('batchList').innerHTML = html;
}

function toggleBatch(bi) {
  document.querySelectorAll('.batch-item').forEach((el, i) => {
    el.classList.toggle('active', i === bi);
  });
}

function selectTopic(batch, topic, bi, ti) {
  toggleBatch(bi);
  document.querySelectorAll('.topic-item').forEach(el => el.classList.remove('active'));
  const el = document.getElementById(`topic-${bi}-${ti}`);
  if (el) el.classList.add('active');
  renderLectures(batch, topic);
}

// ── Lectures ────────────────────────────────────────────────────────────────
function renderLectures(batch, topic) {
  const lectures = DATA[batch]?.[topic] || [];
  document.getElementById('emptyState').style.display = 'none';
  document.getElementById('lectureList').style.display = 'block';
  document.getElementById('topicLabel').textContent = topic;
  const grid = document.getElementById('lectureGrid');
  grid.innerHTML = lectures.map((lec, i) =>
    `<div class="lecture-card" id="lec-${i}" onclick="playVideo('${esc(lec.yt_id)}','${esc(lec.title)}',${i})">
       <div class="lec-num">${String(i+1).padStart(2,'0')}</div>
       <div class="lec-info">
         <div class="lec-title">${lec.title}</div>
         <div class="lec-badge">
           <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
           Watch Lecture
         </div>
       </div>
     </div>`
  ).join('');
  // scroll to top
  document.getElementById('main').scrollTo({top: 0, behavior: 'smooth'});
}

// ── YouTube Player ───────────────────────────────────────────────────────────
function onYouTubeIframeAPIReady() {
  ytReady = true;
}

function playVideo(videoId, title, idx) {
  currentVideoId = videoId;
  document.getElementById('nowTitle').textContent = title;
  document.getElementById('playerSection').classList.add('visible');
  document.querySelectorAll('.lecture-card').forEach((c,i) =>
    c.classList.toggle('playing', i === idx));

  if (player && player.loadVideoById) {
    player.loadVideoById(videoId);
    onPlayerPlay();
  } else {
    if (player) { try { player.destroy(); } catch(e){} }
    player = new YT.Player('ytPlayer', {
      videoId: videoId,
      playerVars: {
        controls: 0,
        modestbranding: 1,
        rel: 0,
        showinfo: 0,
        iv_load_policy: 3,
        disablekb: 1,
        fs: 0,
        playsinline: 1,
        origin: location.origin,
        enablejsapi: 1,
      },
      events: {
        onReady: (e) => { e.target.playVideo(); onPlayerPlay(); },
        onStateChange: onStateChange,
      }
    });
  }
  document.getElementById('main').scrollTo({top: 0, behavior: 'smooth'});
}

function onStateChange(e) {
  const s = e.data;
  const wrapper = document.getElementById('playerWrapper');
  if (s === YT.PlayerState.PLAYING) {
    wrapper.classList.remove('paused');
    setPlayIcon(true);
    startProgress();
  } else if (s === YT.PlayerState.PAUSED || s === YT.PlayerState.ENDED) {
    wrapper.classList.add('paused');
    setPlayIcon(false);
    stopProgress();
  }
}

function onPlayerPlay() {
  document.getElementById('playerWrapper').classList.remove('paused');
  setPlayIcon(true);
  startProgress();
}

function togglePlay() {
  if (!player) return;
  const state = player.getPlayerState();
  if (state === YT.PlayerState.PLAYING) { player.pauseVideo(); }
  else { player.playVideo(); }
}

function setPlayIcon(playing) {
  document.getElementById('playIcon').innerHTML = playing
    ? '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>'
    : '<path d="M8 5v14l11-7z"/>';
}

function startProgress() {
  stopProgress();
  progressInterval = setInterval(updateProgress, 500);
}

function stopProgress() {
  if (progressInterval) clearInterval(progressInterval);
}

function updateProgress() {
  if (!player || !player.getDuration) return;
  const cur = player.getCurrentTime() || 0;
  const dur = player.getDuration() || 0;
  if (dur > 0) {
    document.getElementById('progressFill').style.width = (cur/dur*100) + '%';
    document.getElementById('timeDisplay').textContent = `${fmt(cur)} / ${fmt(dur)}`;
  }
}

function seekClick(e) {
  if (!player || !player.getDuration) return;
  const bar = document.getElementById('progressBar');
  const pct = (e.offsetX / bar.offsetWidth);
  player.seekTo(pct * player.getDuration(), true);
}

function setVolume(v) { if (player) player.setVolume(parseInt(v)); }

function toggleMute() {
  if (!player) return;
  isMuted = !isMuted;
  isMuted ? player.mute() : player.unMute();
}

function toggleFullscreen() {
  const wrapper = document.getElementById('playerWrapper');
  if (!document.fullscreenElement) wrapper.requestFullscreen();
  else document.exitFullscreen();
}

function fmt(s) {
  const m = Math.floor(s/60), sec = Math.floor(s%60);
  return `${m}:${sec.toString().padStart(2,'0')}`;
}

function esc(s) {
  return (s||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'");
}

loadData();
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(HTML)


if __name__ == "__main__":
    uvicorn.run("web:app", host="0.0.0.0", port=PORT, reload=False)

