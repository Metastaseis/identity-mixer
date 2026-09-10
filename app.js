// Identity Mixer — player and UI. Driven entirely by manifest.json.
// The player's only audio job: start every loop at one shared AudioContext time
// and loop each one over exactly its bar-grid length. Sync and harmony are
// solved in pipeline/, never here.

const LEVEL_DEFAULT = 0.6;
const MASTER_DEFAULT = 0.8;
const START_LEAD = 0.15;      // seconds between the tap and the shared start time
const SWAP_LEAD = 0.05;       // seconds between a picker tap and the swap
const RAMP = 0.03;            // setTargetAtTime time constant for click-free fader moves
const STORAGE_KEY = "mixer-state";
const DEBUG = new URLSearchParams(location.search).get("debug") === "1";

const status = document.getElementById("status");
const board = document.getElementById("board");
const playBtn = document.getElementById("play");

let MANIFEST = null, ASSETS = [], MANIFEST_VERSION = 0;
let state = [];
let master = MASTER_DEFAULT, playing = false;

// ---------- manifest ----------
async function loadManifest() {
  const res = await fetch("manifest.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`manifest ${res.status}`);
  const m = await res.json();
  if (!Array.isArray(m.assets) || m.assets.length !== 6) throw new Error("manifest needs exactly six assets");
  if (m.beats_per_bar !== 4) throw new Error("only 4 beats per bar are supported");
  if (!Number.isInteger(m.version)) throw new Error("manifest needs an integer version");
  m.assets.forEach(a => { if (!a.clips || !a.clips.length) throw new Error(`asset ${a.id} has no clips`); });
  return m;
}
// Loop lengths come from the manifest grid, never from decoded buffer lengths.
const barLength = () => MANIFEST.beats_per_bar * 60 / MANIFEST.tempo;
const loopLength = clip => (clip.bars ?? MANIFEST.bars) * barLength();

// ---------- state ----------
// Saved fader levels always survive. Saved clip choices survive only while the
// manifest version is unchanged: a bump means clip order or defaults moved.
function loadState() {
  state = ASSETS.map(() => ({ level: LEVEL_DEFAULT, clip: 0 }));
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null"); } catch (e) {}
  if (!saved) return;
  if (saved.levels) saved.levels.forEach((v, i) => { if (state[i]) state[i].level = v; });
  if (saved.version === MANIFEST_VERSION && saved.clips) {
    saved.clips.forEach((v, i) => { if (state[i] && ASSETS[i].clips[v]) state[i].clip = v; });
  } else {
    persist();   // record the new version with default clip choices
  }
}
function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      version: MANIFEST_VERSION, levels: state.map(s => s.level), clips: state.map(s => s.clip),
    }));
  } catch (e) {}
}
const levels = () => state.map(s => s.level);
const clipOf = i => ASSETS[i].clips[state[i].clip];

// ---------- audio ----------
let ctx = null, masterGain = null, chans = [], startTime = 0;
const buffers = new Map();
const toGain = level => level * level;   // perceptual: level 0..1 -> gain

async function ensureAudio() {           // only ever reached from the play tap
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    masterGain = ctx.createGain(); masterGain.gain.value = master; masterGain.connect(ctx.destination);
  }
  if (ctx.state === "suspended") await ctx.resume();
}
async function loadBuffer(file) {
  if (buffers.has(file)) return buffers.get(file);
  const res = await fetch(file);
  if (!res.ok) throw new Error(`${file} ${res.status}`);
  const buf = await ctx.decodeAudioData(await res.arrayBuffer());
  buffers.set(file, buf); return buf;
}
function makeChannel(buf, i) {
  const clip = clipOf(i), L = loopLength(clip);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.loop = true; src.loopStart = 0; src.loopEnd = L;   // the bar grid, not buf.duration
  const g = ctx.createGain(); g.gain.value = toGain(state[i].level);
  src.connect(g); g.connect(masterGain);
  return { src, g, clip, L };
}
async function startAll() {
  await ensureAudio();
  status.textContent = "טוען…";
  const bufs = await Promise.all(ASSETS.map((_, i) => loadBuffer(clipOf(i).file)));
  stopAll(true);
  const t0 = ctx.currentTime + START_LEAD;   // one shared start time for all six channels
  startTime = t0;
  chans = bufs.map((buf, i) => { const c = makeChannel(buf, i); c.src.start(t0); return c; });
  playing = true; status.textContent = "";
  if (DEBUG) debugStart();
}
function stopAll(silent) {
  chans.forEach(c => { try { c.src.stop(); } catch (e) {} });
  chans = [];
  if (!silent) { playing = false; if (DEBUG) debugStop(); }
}
async function swapClip(i) {   // replace one channel in place, aligned to the shared bar grid
  if (!playing) return;
  const buf = await loadBuffer(clipOf(i).file);
  const old = chans[i];
  const c = makeChannel(buf, i);
  const t = ctx.currentTime + SWAP_LEAD;
  const offset = (t - startTime) % c.L;          // where this clip's loop is on the grid at time t
  c.src.start(t, offset);
  try { old.src.stop(t); } catch (e) {}
  chans[i] = c;
  if (DEBUG) debugChannel(i, t);
}
function setLevel(i, v) {
  state[i].level = v;
  if (chans[i]) chans[i].g.gain.setTargetAtTime(toGain(v), ctx.currentTime, RAMP);
}

// ---------- sync self-test (?debug=1) ----------
// Web Audio exposes no playhead, so this reports what can be known: every source's
// scheduled start and loopEnd, each decoded buffer's length against the grid (the
// drift a buffer-length loop would accumulate, which explicit loopEnd removes),
// and the audio clock against the wall clock (a stall shows as growing skew).
const dbg = { timer: null, wall0: 0, lastLoop: -1, maxDrift: 0 };
function debugChannel(i, t) {
  const c = chans[i], b = c.src.buffer;
  const gridSamples = Math.round(c.L * b.sampleRate), delta = b.length - gridSamples;
  console.log(`[sync] ch${i} ${c.clip.id}: start ${t.toFixed(6)} s, loopEnd ${c.L.toFixed(6)} s, `
    + `buffer ${b.length} samples @${b.sampleRate} Hz (grid ${gridSamples}, Δ ${delta >= 0 ? "+" : ""}${delta})`);
}
function debugStart() {
  console.log(`[sync] start scheduled at ${startTime.toFixed(6)} s, context ${ctx.sampleRate} Hz, `
    + `bar ${barLength().toFixed(4)} s, library loop ${(MANIFEST.bars * barLength()).toFixed(4)} s`);
  chans.forEach((_, i) => debugChannel(i, startTime));
  dbg.wall0 = performance.now() / 1000 - ctx.currentTime;
  dbg.lastLoop = -1; dbg.maxDrift = 0;
  dbg.timer = setInterval(debugTick, 100);
}
function debugStop() { clearInterval(dbg.timer); dbg.timer = null; }
function debugTick() {
  if (!playing) return;
  const el = ctx.currentTime - startTime;
  if (el < 0) return;
  const loop = Math.floor(el / (MANIFEST.bars * barLength()));
  if (loop === dbg.lastLoop) return;
  dbg.lastLoop = loop;
  const skewMs = ((performance.now() / 1000 - dbg.wall0) - ctx.currentTime) * 1000;
  let worst = 0;
  const rows = chans.map((c, i) => {
    const b = c.src.buffer;
    const bufLoop = b.length / b.sampleRate;
    const pos = el % c.L;                                          // playback position on the grid
    const wouldDrift = (bufLoop - c.L) * Math.floor(el / c.L) * 1000; // ms, without explicit loopEnd
    worst = Math.max(worst, Math.abs(wouldDrift));
    return `ch${i} ${c.clip.id} pos ${pos.toFixed(3)} s, bufΔ ${((bufLoop - c.L) * 1000).toFixed(3)} ms/loop, would-be ${wouldDrift.toFixed(2)} ms`;
  });
  dbg.maxDrift = Math.max(dbg.maxDrift, worst);
  console.log(`[sync] loop ${loop} at ${el.toFixed(3)} s, clock skew ${skewMs.toFixed(1)} ms\n  ` + rows.join("\n  "));
  status.textContent = `בדיקת סנכרון · לולאה ${loop} · סטייה מקסימלית ${dbg.maxDrift.toFixed(2)} מ״ש · שעון ${skewMs >= 0 ? "+" : ""}${skewMs.toFixed(1)} מ״ש`;
}

// ---------- UI ----------
function buildBoard() {
  board.innerHTML = "";
  ASSETS.forEach((a, i) => {
    const ch = document.createElement("div"); ch.className = "ch"; ch.style.setProperty("--c", a.color);
    const pct = Math.round(state[i].level * 100);
    ch.innerHTML = `<div class="fader" role="slider" tabindex="0" aria-label="${a.name}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
        <div class="fill" style="height:${state[i].level * 100}%"></div><div class="val">${pct}</div></div>
      <div class="name">${a.name}</div>
      <button class="clip" data-i="${i}"><u>${clipOf(i).title}</u></button>`;
    board.appendChild(ch);
    const fader = ch.querySelector(".fader"), fill = ch.querySelector(".fill"), val = ch.querySelector(".val");
    const render = () => { const p = Math.round(state[i].level * 100); fill.style.height = (state[i].level * 100) + "%"; val.textContent = p; fader.setAttribute("aria-valuenow", p); };
    const fromPointer = e => { const r = fader.getBoundingClientRect(); const v = 1 - (e.clientY - r.top) / r.height; setLevel(i, Math.max(0, Math.min(1, v))); render(); };
    let dragging = false;
    fader.addEventListener("pointerdown", e => { dragging = true; fader.setPointerCapture(e.pointerId); fromPointer(e); });
    fader.addEventListener("pointermove", e => { if (dragging) fromPointer(e); });
    fader.addEventListener("pointerup", () => { dragging = false; persist(); });
    fader.addEventListener("pointercancel", () => { dragging = false; persist(); });
    fader.addEventListener("keydown", e => {
      const step = e.shiftKey ? 0.1 : 0.05;
      if (e.key === "ArrowUp") { setLevel(i, Math.min(1, state[i].level + step)); render(); persist(); e.preventDefault(); }
      if (e.key === "ArrowDown") { setLevel(i, Math.max(0, state[i].level - step)); render(); persist(); e.preventDefault(); }
    });
  });
}

// clip picker
const picker = document.getElementById("picker");
board.addEventListener("click", e => {
  const b = e.target.closest(".clip"); if (!b) return;
  const i = +b.dataset.i; const a = ASSETS[i];
  document.getElementById("pickerTitle").textContent = a.name;
  document.getElementById("pickerDesc").textContent = a.description + (a.clips.length === 1 ? " (בגרסה הזו יש קטע אחד לכל נכס.)" : " בחרו את הקטע שמתאר אתכם.");
  const list = document.getElementById("choices"); list.innerHTML = "";
  a.clips.forEach((c, k) => {
    const btn = document.createElement("button"); btn.className = "choice"; btn.setAttribute("aria-pressed", k === state[i].clip);
    btn.innerHTML = `${c.title}${c.note ? `<small>${c.note}</small>` : ""}`;
    btn.onclick = async () => { state[i].clip = k; persist(); b.innerHTML = `<u>${c.title}</u>`; list.querySelectorAll(".choice").forEach(x => x.setAttribute("aria-pressed", x === btn)); await swapClip(i); };
    list.appendChild(btn);
  });
  picker.showModal();
});
document.getElementById("pickerClose").onclick = () => picker.close();

// play / master
playBtn.onclick = async () => {
  if (!playing) {
    playBtn.disabled = true;
    try { await startAll(); playBtn.textContent = "עצור"; playBtn.setAttribute("aria-pressed", "true"); }
    catch (e) { status.textContent = "לא הצלחתי להפעיל שמע. נסו שוב."; console.error(e); }
    playBtn.disabled = false;
  } else {
    stopAll(); playBtn.textContent = "נגן"; playBtn.setAttribute("aria-pressed", "false");
  }
};
document.getElementById("master").oninput = e => { master = e.target.value / 100; if (masterGain) masterGain.gain.setTargetAtTime(master, ctx.currentTime, RAMP); };

// profile (the six levels as a shape)
const profileDlg = document.getElementById("profileDlg");
document.getElementById("profileBtn").onclick = () => {
  document.getElementById("chart").innerHTML = IdentityProfile.radar(ASSETS, levels());
  document.getElementById("profileText").textContent = IdentityProfile.text(ASSETS, levels());
  profileDlg.showModal();
};
document.getElementById("profileClose").onclick = () => profileDlg.close();
document.getElementById("copyBtn").onclick = async () => {
  const t = IdentityProfile.text(ASSETS, levels());
  try { await navigator.clipboard.writeText("שישה נכסים — " + t); status.textContent = "הועתק."; } catch (e) { status.textContent = t; }
};

// ---------- boot ----------
(async () => {
  playBtn.disabled = true;
  try {
    MANIFEST = await loadManifest();
    ASSETS = MANIFEST.assets;
    MANIFEST_VERSION = MANIFEST.version;
    loadState();
    buildBoard();
    playBtn.disabled = false;
    if (DEBUG) status.textContent = "מצב בדיקת סנכרון";
  } catch (e) {
    status.textContent = "לא הצלחתי לטעון את ספריית הקטעים.";
    console.error(e);
  }
})();
