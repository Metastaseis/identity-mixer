// Identity Mixer — player and UI. Driven entirely by manifest.json.
// The player's only audio job: start every loop at one shared AudioContext time
// and loop each one over exactly its bar-grid length. Sync and harmony are
// solved in pipeline/, never here. Each channel plays one instrument: one source,
// the selected clip's file, behind the channel's fader.

const LEVEL_DEFAULT = 0;      // every fader starts at zero: the participant raises the instruments they want
const MASTER_DEFAULT = 0.8;
const START_LEAD = 0.15;      // seconds between the tap and the shared start time
const SWAP_LEAD = 0.05;       // seconds between a picker tap and the swap
const RAMP = 0.03;            // setTargetAtTime time constant for click-free fader moves
const DECODE_RATE = 44100;    // background decodes run in an OfflineAudioContext at the clip rate
const STORAGE_KEY = "mixer-state-instruments";   // new with the one-instrument model: old saved levels (0.6) are not read
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
  if (saved) {
    if (saved.levels) saved.levels.forEach((v, i) => { if (state[i]) state[i].level = v; });
    if (saved.version === MANIFEST_VERSION && saved.clips) {
      saved.clips.forEach((v, i) => { if (state[i] && ASSETS[i].clips[v]) state[i].clip = v; });
    } else {
      persist();   // record the new version with default clip choices
    }
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
const ready = [];                   // per channel: Promise that its selected clip was fetched and decoded
const toGain = level => level * level;   // perceptual: level 0..1 -> gain

async function ensureAudio() {           // only ever reached from the play tap
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    masterGain = ctx.createGain(); masterGain.gain.value = master; masterGain.connect(ctx.destination);
  }
  if (ctx.state !== "running") await ctx.resume();   // "suspended", or iOS "interrupted" after a call or backgrounding
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
function preloadChannel(i) {             // background: fetch + decode the selected clip, show a loading state
  const clip = clipOf(i);
  setLoading(i, true);
  const p = loadBuffer(clip.file).then(
    () => { if (clipOf(i) === clip) setLoading(i, false); },
    e => { console.error("[load]", e); if (clipOf(i) === clip) setLoading(i, true, true); });
  ready[i] = p;
  return p;
}
async function makeChannel(i) {          // one source, straight into the channel's fader: source -> g -> master
  const clip = clipOf(i), L = loopLength(clip);
  let buf;
  try { buf = await playableBuffer(clip.file); }
  catch (e) { if (clipOf(i) === clip) setLoading(i, true, true); throw e; }
  const g = ctx.createGain(); g.gain.value = toGain(state[i].level); g.connect(masterGain);   // the fader
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.loop = true; src.loopStart = 0; src.loopEnd = L;   // the bar grid, not buf.duration
  src.connect(g);
  return { clip, L, g, src };
}
async function startAll() {
  await ensureAudio();
  status.textContent = "טוען…";
  await Promise.all(ASSETS.map((_, i) => ready[i] || preloadChannel(i)));
  const built = [];
  for (let i = 0; i < ASSETS.length; i++) built.push(await makeChannel(i));   // every source exists before the start time is read
  stopAll(true);
  const t0 = ctx.currentTime + START_LEAD;   // one shared start time for every channel
  startTime = t0;
  built.forEach(c => c.src.start(t0));
  chans = built;
  playing = true; status.textContent = "";
  updateHint();
  if (DEBUG) debugStart();
}
function stopAll(silent) {
  chans.forEach(c => { try { c.src.stop(); } catch (e) {} });
  chans = [];
  if (!silent) { playing = false; updateHint(); if (DEBUG) debugStop(); }
}
async function swapClip(i) {   // replace one channel in place, aligned to the shared bar grid
  preloadChannel(i);
  if (!playing) return;
  await ready[i];
  const c = await makeChannel(i);
  if (c.clip !== clipOf(i) || !playing) return;   // superseded by a later pick, or stopped meanwhile
  const old = chans[i];
  const t = ctx.currentTime + SWAP_LEAD;
  const offset = (((t - startTime) % c.L) + c.L) % c.L;   // where this clip's loop is on the grid at time t (never negative, even before the shared start)
  c.src.start(t, offset);
  if (old) { try { old.src.stop(t); } catch (e) {} }
  chans[i] = c;
  if (DEBUG) debugChannel(i, t);
}
function setLevel(i, v) {
  state[i].level = v;
  if (chans[i]) chans[i].g.gain.setTargetAtTime(toGain(v), ctx.currentTime, RAMP);
  updateHint();
}
// While playing with every fader at zero nothing sounds: say how to hear something.
const HINT = "הרימו פיידר כדי לשמוע";
function updateHint() {
  if (DEBUG) return;                                  // the sync self-test owns the status line
  const silent = playing && state.every(s => Math.round(s.level * 100) === 0);   // every fader shows 0
  if (silent) status.textContent = HINT;
  else if (status.textContent === HINT) status.textContent = "";
}

// ---------- sync self-test (?debug=1) ----------
// Web Audio exposes no playhead, so this reports what can be known: each channel's one
// source with its scheduled start and loopEnd, its decoded buffer's length against the
// grid (the drift a buffer-length loop would accumulate, which explicit loopEnd removes),
// the number of running sources, and the audio clock against the wall clock (a stall
// shows as growing skew).
const dbg = { timer: null, wall0: 0, lastLoop: -1, maxDrift: 0 };
const sourceCount = () => chans.filter(Boolean).length;
function debugChannel(i, t) {
  const c = chans[i], b = c.src.buffer;
  const gridSamples = Math.round(c.L * b.sampleRate), delta = b.length - gridSamples;
  console.log(`[sync] ch${i} ${c.clip.id}: start ${t.toFixed(6)} s, loopEnd ${c.L.toFixed(6)} s, `
    + `buffer ${b.length} samples @${b.sampleRate} Hz (grid ${gridSamples}, Δ ${delta >= 0 ? "+" : ""}${delta})`);
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
    const b = c.src.buffer;
    const bufLoop = b.length / b.sampleRate;
    const pos = el % c.L;                                          // playback position on the grid
    const wouldDrift = (bufLoop - c.L) * Math.floor(el / c.L) * 1000; // ms, without explicit loopEnd
    worst = Math.max(worst, Math.abs(wouldDrift));
    return `ch${i} ${c.clip.id} pos ${pos.toFixed(3)} s, bufΔ ${((bufLoop - c.L) * 1000).toFixed(3)} ms/loop, would-be ${wouldDrift.toFixed(2)} ms`;
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
    ch.innerHTML = `<div class="fader" role="slider" tabindex="0" aria-label="${a.name} · ${a.instrument.name}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
        <div class="fill" style="height:${state[i].level * 100}%"></div><div class="val">${pct}</div></div>
      <button class="name" data-i="${i}">${a.name}</button>
      <div class="inst">${a.instrument.name}</div>
      <div class="pick"><span class="clip"></span><select class="song" name="song-${a.id}" data-i="${i}" aria-label="שיר · ${a.name}"></select></div>
      <div class="load" aria-live="polite"></div>`;
    board.appendChild(ch);
    renderSongs(i);
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
      const to = v => Math.round(Math.max(0, Math.min(1, v)) * 100) / 100;   // whole percent: steps add up to exactly 0 and 1
      if (e.key === "ArrowUp") { setLevel(i, to(state[i].level + step)); render(); persist(); e.preventDefault(); }
      if (e.key === "ArrowDown") { setLevel(i, to(state[i].level - step)); render(); persist(); e.preventDefault(); }
    });
  });
}
// The song dropdown under a column: one option per clip of the asset. The visible label
// wraps the selected title; the native select sits invisibly on top of it and opens the
// phone's own menu. An asset with a single clip shows its title with no menu.
function renderSongs(i) {
  const pick = board.children[i].querySelector(".pick");
  const sel = pick.querySelector(".song"), label = pick.querySelector(".clip");
  const clips = ASSETS[i].clips;
  sel.innerHTML = "";
  clips.forEach((c, k) => sel.appendChild(new Option(c.title, k)));
  sel.value = state[i].clip;
  sel.disabled = clips.length < 2;
  pick.classList.toggle("single", clips.length < 2);
  label.textContent = clipOf(i).title;
}
function setLoading(i, on, failed) {
  const ch = board.children[i]; if (!ch) return;
  ch.classList.toggle("loading", !!on);
  const el = ch.querySelector(".load"); if (el) el.textContent = failed ? "הטעינה נכשלה" : "טוען…";
}

// asset description
const picker = document.getElementById("picker");
board.addEventListener("click", e => {
  const b = e.target.closest(".name"); if (!b) return;
  const a = ASSETS[+b.dataset.i];
  document.getElementById("pickerTitle").textContent = a.name;
  document.getElementById("pickerDesc").textContent = a.description;
  picker.showModal();
});
// song dropdown: pick a song, the channel swaps in place on the shared bar grid
board.addEventListener("change", async e => {
  const sel = e.target.closest(".song"); if (!sel) return;
  const i = +sel.dataset.i, k = +sel.value;
  if (!ASSETS[i].clips[k] || k === state[i].clip) return;
  state[i].clip = k; persist();
  sel.parentElement.querySelector(".clip").textContent = clipOf(i).title;
  try { await swapClip(i); }
  catch (err) { status.textContent = "לא הצלחתי להחליף שיר. נסו שוב."; console.error(err); }
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
    playBtn.disabled = false;                       // play is allowed at once; it waits for the buffers if needed
    ASSETS.forEach((_, i) => preloadChannel(i));   // fetch + decode in the background, no AudioContext involved
    if (DEBUG) status.textContent = "מצב בדיקת סנכרון";
  } catch (e) {
    status.textContent = "לא הצלחתי לטעון את ספריית הקטעים.";
    console.error(e);
  }
})();
