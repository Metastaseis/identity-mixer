// Identity Mixer — player and UI. Driven entirely by manifest.json.
// The player's only audio job: start every loop at one shared AudioContext time
// and loop each one over exactly its bar-grid length. Sync and harmony are
// solved in pipeline/, never here. A clip with stems plays its stems as parallel
// sources started at that same shared time; a stem toggle only moves that stem's
// gain, it never stops or restarts a source.

const LEVEL_DEFAULT = 0.6;
const MASTER_DEFAULT = 0.8;
const START_LEAD = 0.15;      // seconds between the tap and the shared start time
const SWAP_LEAD = 0.05;       // seconds between a picker tap and the swap
const RAMP = 0.03;            // setTargetAtTime time constant for click-free fader moves
const STEM_RAMP = 0.02;       // setTargetAtTime time constant for a stem on/off (20 ms)
const DECODE_RATE = 44100;    // background decodes run in an OfflineAudioContext at the clip rate
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
const hasStems = clip => Array.isArray(clip.stems) && clip.stems.length > 0;
// Every file a clip needs decoded: the full clip always, plus its stems when it has them.
const clipFiles = clip => hasStems(clip) ? [clip.file, ...clip.stems.map(s => s.file)] : [clip.file];

// ---------- state ----------
// Saved fader levels always survive. Saved clip choices survive only while the
// manifest version is unchanged: a bump means clip order or defaults moved.
// Stem toggles live in memory only: every clip starts with all its stems on.
function loadState() {
  state = ASSETS.map(() => ({ level: LEVEL_DEFAULT, clip: 0, off: new Set() }));
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
let decoder = null;                 // OfflineAudioContext: decodes in the background, never plays
const buffers = new Map();          // file -> AudioBuffer
const inflight = new Map();         // file -> Promise<AudioBuffer>
const ready = [];                   // per channel: Promise that its selected clip's files were fetched and decoded
const toGain = level => level * level;   // perceptual: level 0..1 -> gain

async function ensureAudio() {           // only ever reached from the play tap
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    masterGain = ctx.createGain(); masterGain.gain.value = master; masterGain.connect(ctx.destination);
  }
  if (ctx.state === "suspended") await ctx.resume();
}
function decodeWith(c, bytes) {          // promise or callback form, whichever this browser has
  return new Promise((resolve, reject) => {
    try { const p = c.decodeAudioData(bytes, resolve, reject); if (p && p.catch) p.catch(reject); }
    catch (e) { reject(e); }
  });
}
function backgroundDecoder() {
  if (!decoder) decoder = new (window.OfflineAudioContext || window.webkitOfflineAudioContext)(1, 1, DECODE_RATE);
  return decoder;
}
function loadBuffer(file) {              // fetch + decode once; safe before the play tap (no AudioContext needed)
  if (buffers.has(file)) return Promise.resolve(buffers.get(file));
  if (inflight.has(file)) return inflight.get(file);
  const p = (async () => {
    const res = await fetch(file);
    if (!res.ok) throw new Error(`${file} ${res.status}`);
    const bytes = await res.arrayBuffer();
    const buf = await decodeWith(ctx || backgroundDecoder(), bytes);
    buffers.set(file, buf);
    return buf;
  })().finally(() => inflight.delete(file));
  inflight.set(file, p);
  return p;
}
async function playableBuffer(file) {    // a buffer this context refuses (decoded elsewhere) is decoded again here
  let buf = await loadBuffer(file);
  try { ctx.createBufferSource().buffer = buf; }
  catch (e) { buffers.delete(file); buf = await loadBuffer(file); }
  return buf;
}
function preloadChannel(i) {             // background: fetch + decode the selected clip's files, show a loading state
  const clip = clipOf(i);
  setLoading(i, true);
  const p = Promise.allSettled(clipFiles(clip).map(loadBuffer)).then(results => {
    const failed = results.filter(r => r.status === "rejected");
    failed.forEach(r => console.error("[load]", r.reason));
    if (clipOf(i) === clip) setLoading(i, failed.length > 0, failed.length > 0);
    return results;
  });
  ready[i] = p;
  return p;
}
async function makeSource(i, part, L, g) {
  const buf = await playableBuffer(part.file);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.loop = true; src.loopStart = 0; src.loopEnd = L;   // the bar grid, not buf.duration
  const sg = ctx.createGain();                           // per-source gain: a stem's on/off lives here
  sg.gain.value = (part.id === null || !state[i].off.has(part.id)) ? part.base : 0;
  src.connect(sg); sg.connect(g);
  return { id: part.id, file: part.file, base: part.base, src, sg };
}
async function makeChannel(i) {
  const clip = clipOf(i), L = loopLength(clip);
  const g = ctx.createGain(); g.gain.value = toGain(state[i].level); g.connect(masterGain);   // the fader
  let sources = null;
  if (hasStems(clip)) {
    const base = clip.stems_gain ?? 1;   // one trim from the pipeline so the stems sum to the library loudness
    try { sources = await Promise.all(clip.stems.map(s => makeSource(i, { id: s.id, file: s.file, base }, L, g))); }
    catch (e) { console.error(`[stems] ${clip.id}: ${e.message}; playing the full clip instead`); }
  }
  if (!sources) sources = [await makeSource(i, { id: null, file: clip.file, base: 1 }, L, g)];
  return { clip, L, g, sources };
}
async function startAll() {
  await ensureAudio();
  status.textContent = "טוען…";
  await Promise.all(ASSETS.map((_, i) => ready[i] || preloadChannel(i)));
  const built = [];
  for (let i = 0; i < ASSETS.length; i++) built.push(await makeChannel(i));   // every source exists before the start time is read
  stopAll(true);
  const t0 = ctx.currentTime + START_LEAD;   // one shared start time for every source of every channel
  startTime = t0;
  built.forEach(c => c.sources.forEach(s => s.src.start(t0)));
  chans = built;
  playing = true; status.textContent = "";
  if (DEBUG) debugStart();
}
function stopAll(silent) {
  chans.forEach(c => c.sources.forEach(s => { try { s.src.stop(); } catch (e) {} }));
  chans = [];
  if (!silent) { playing = false; if (DEBUG) debugStop(); }
}
async function swapClip(i) {   // replace one channel in place, aligned to the shared bar grid
  state[i].off = new Set(); renderStems(i);   // a newly chosen clip starts with all its stems on
  preloadChannel(i);
  if (!playing) return;
  await ready[i];
  const c = await makeChannel(i);
  if (c.clip !== clipOf(i) || !playing) return;   // superseded by a later pick, or stopped meanwhile
  const old = chans[i];
  const t = ctx.currentTime + SWAP_LEAD;
  const offset = (t - startTime) % c.L;          // where this clip's loop is on the grid at time t
  c.sources.forEach(s => s.src.start(t, offset));
  if (old) old.sources.forEach(s => { try { s.src.stop(t); } catch (e) {} });
  chans[i] = c;
  if (DEBUG) debugChannel(i, t);
}
function setLevel(i, v) {
  state[i].level = v;
  if (chans[i]) chans[i].g.gain.setTargetAtTime(toGain(v), ctx.currentTime, RAMP);
}
function setStem(i, id, on) {   // gain only: the source keeps running on the grid
  if (on) state[i].off.delete(id); else state[i].off.add(id);
  const c = chans[i]; if (!c || !playing) return;
  const s = c.sources.find(x => x.id === id);
  if (s) s.sg.gain.setTargetAtTime(on ? s.base : 0, ctx.currentTime, STEM_RAMP);
}

// ---------- sync self-test (?debug=1) ----------
// Web Audio exposes no playhead, so this reports what can be known: every source's
// scheduled start and loopEnd, each decoded buffer's length against the grid (the
// drift a buffer-length loop would accumulate, which explicit loopEnd removes),
// the number of running sources, and the audio clock against the wall clock (a
// stall shows as growing skew).
const dbg = { timer: null, wall0: 0, lastLoop: -1, maxDrift: 0 };
const sourceCount = () => chans.reduce((n, c) => n + c.sources.length, 0);
function debugChannel(i, t) {
  const c = chans[i];
  c.sources.forEach(s => {
    const b = s.src.buffer;
    const gridSamples = Math.round(c.L * b.sampleRate), delta = b.length - gridSamples;
    console.log(`[sync] ch${i} ${c.clip.id}${s.id ? "/" + s.id : ""}: start ${t.toFixed(6)} s, loopEnd ${c.L.toFixed(6)} s, `
      + `buffer ${b.length} samples @${b.sampleRate} Hz (grid ${gridSamples}, Δ ${delta >= 0 ? "+" : ""}${delta})`);
  });
}
function debugStart() {
  console.log(`[sync] start scheduled at ${startTime.toFixed(6)} s, context ${ctx.sampleRate} Hz, `
    + `bar ${barLength().toFixed(4)} s, library loop ${(MANIFEST.bars * barLength()).toFixed(4)} s, ${sourceCount()} sources`);
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
    const b = c.sources[0].src.buffer;
    const bufLoop = b.length / b.sampleRate;
    const pos = el % c.L;                                          // playback position on the grid
    const wouldDrift = (bufLoop - c.L) * Math.floor(el / c.L) * 1000; // ms, without explicit loopEnd
    worst = Math.max(worst, Math.abs(wouldDrift));
    return `ch${i} ${c.clip.id} (${c.sources.length} src) pos ${pos.toFixed(3)} s, bufΔ ${((bufLoop - c.L) * 1000).toFixed(3)} ms/loop, would-be ${wouldDrift.toFixed(2)} ms`;
  });
  dbg.maxDrift = Math.max(dbg.maxDrift, worst);
  console.log(`[sync] loop ${loop} at ${el.toFixed(3)} s, ${sourceCount()} sources, clock skew ${skewMs.toFixed(1)} ms\n  ` + rows.join("\n  "));
  status.textContent = `בדיקת סנכרון · לולאה ${loop} · מקורות ${sourceCount()} · סטייה מקסימלית ${dbg.maxDrift.toFixed(2)} מ״ש · שעון ${skewMs >= 0 ? "+" : ""}${skewMs.toFixed(1)} מ״ש`;
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
      <button class="clip" data-i="${i}"><u>${clipOf(i).title}</u></button>
      <div class="load" aria-live="polite"></div>
      <div class="stems" data-i="${i}" role="group" aria-label="כלים · ${a.name}"></div>`;
    board.appendChild(ch);
    renderStems(i);
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
// One toggle chip per stem of the channel's selected clip; nothing for a clip without stems.
function renderStems(i) {
  const row = board.querySelector(`.stems[data-i="${i}"]`); if (!row) return;
  const clip = clipOf(i);
  row.innerHTML = "";
  if (!hasStems(clip)) return;
  clip.stems.forEach(s => {
    const b = document.createElement("button");
    b.className = "stem"; b.dataset.i = i; b.dataset.stem = s.id;
    b.textContent = s.name;
    b.setAttribute("aria-pressed", String(!state[i].off.has(s.id)));
    row.appendChild(b);
  });
}
function setLoading(i, on, failed) {
  const ch = board.children[i]; if (!ch) return;
  ch.classList.toggle("loading", !!on);
  const el = ch.querySelector(".load"); if (el) el.textContent = failed ? "הטעינה נכשלה" : "טוען…";
}

// stem chips and clip picker
const picker = document.getElementById("picker");
board.addEventListener("click", e => {
  const chip = e.target.closest(".stem");
  if (chip) {
    const on = chip.getAttribute("aria-pressed") !== "true";
    chip.setAttribute("aria-pressed", String(on));
    setStem(+chip.dataset.i, chip.dataset.stem, on);
    return;
  }
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

// profile (the six levels as a shape; stems are not part of it)
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
    playBtn.disabled = false;                       // play is allowed at once; it waits for the buffers if needed
    ASSETS.forEach((_, i) => preloadChannel(i));   // fetch + decode in the background, no AudioContext involved
    if (DEBUG) status.textContent = "מצב בדיקת סנכרון";
  } catch (e) {
    status.textContent = "לא הצלחתי לטעון את ספריית הקטעים.";
    console.error(e);
  }
})();
