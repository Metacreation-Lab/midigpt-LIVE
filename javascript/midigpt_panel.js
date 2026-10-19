/**
 * The MIDI-GPT panel: the whole device window (960 x 640) in one jsui.
 * Ported from the browser prototype (tools/frontend_assets.py layouts, the
 * drawing code in the prototype's app.js). The rendered background and part
 * sprites are PNGs (midigpt_*.png, written by tools/export_panel_assets.py);
 * everything that changes (LEDs, legends, the HUD screens) is drawn here
 * through midigpt_canvas.js, a canvas-2D layer over mgraphics.
 *
 * In (from midigpt.js outlet 6):
 *   panel_state <json>   tracks, parameters, server, generation, fault
 *   panel_notes <json>   per track, per bar: [[start, length, pitch] ...] (0-1)
 *   either one can come in parts: "~part:<i>:<n>|<text>" (joinParts)
 *
 * Out: "panel <verb> <args...>" to midigpt.js, plus "url_edit <0|1>" for the
 * window patch (it shows the native address field over the Setup screen).
 *
 * The window is split into regions, one jsui each (jsarguments[1]: top, roll,
 * main, output, masks), over a native fpic showing the page background. A
 * region repaints only when the state it draws changes, so turning a knob
 * repaints one bay, not the window. "page <name>" goes to every region;
 * "bg <file>" (from the main region) to the fpic.
 */

autowatch = 0;
inlets = 1;
outlets = 1;

mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;

include("midigpt_canvas.js");
var CV = MidigptCanvas;
include("midigpt_panel_spec.js");
var SPM = MidigptPanelSpec;
var SP = SPM.SPEC, T = SPM.THEME;
var ACC = T.led, INK = T.ink, LAB = T.lab, HUD = T.hud;
var W = 960, H = 640;
var g = null;
var REGION = jsarguments.length > 1 ? String(jsarguments[1]) : "all";
var REGIONS = { top: [788, 2, 168, 34], roll: [4, 36, 952, 220], main: [4, 256, 684, 264], output: [688, 256, 268, 264],
                masks: [4, 520, 952, 118], all: [0, 0, 960, 640] };
var RX = REGIONS[REGION] || REGIONS.all;
function inRegion(name) { return REGION === "all" || REGION === name; }

function now() { return new Date().getTime(); }
function ext(a, b) { for (var k in b) a[k] = b[k]; return a; }
function rgba(rgb, a) { return rgb.replace("rgb(", "rgba(").replace(")", "," + a + ")"); }
function send() { outlet(0, ["panel"].concat(Array.prototype.slice.call(arguments))); }

// ------------------------------------------------------------------ assets (rendered at 2x)
var IMG = {};
function img(name) {
    var im = IMG[name];
    if (im === undefined) {
        try { im = new Image("midigpt_" + name); if (!im.size[0]) im = null; } catch (e) { im = null; }
        IMG[name] = im;
    }
    return im;
}
// Dimmed parts use pre-dimmed sprites (name_aNN.png, see export_panel_assets.py): mgraphics' group alpha
// draws them shifted.
// The levels each kind is drawn at (knobs 0.55, toggle thumbs 0.5, keys 0.28 / 0.4 / 0.62); only these are shipped.
// Keep in sync with DIMS in tools/video/finish_panel_assets.py and tools/export_panel_assets.py.
var DIMS = { knob: [55], thumb: [50], key: [28, 50, 62] };
function drawImg(name, x, y) {
    var a = g.globalAlpha;
    if (a < 0.999 && name.indexOf("bg_") !== 0) {
        var levels = DIMS[name.slice(0, name.indexOf("_"))] || [50], best = levels[0];
        for (var i = 0; i < levels.length; i++) if (Math.abs(levels[i] - a * 100) < Math.abs(best - a * 100)) best = levels[i];
        name = name.replace(".png", "_a" + best + ".png");
    }
    var im = img(name);
    if (!im) return;
    g.globalAlpha = 1;
    g.drawImage(im, x, y, im.size[0] / 2, im.size[1] / 2);
    g.globalAlpha = a;
}

// ------------------------------------------------------------------ tables
var NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
var DUR = ["1/32", "1/16", "1/8", "1/4", "1/2", "1"];   // the server's six note-duration levels
var FAMILIES = ["PIANO", "CHROM PERC", "ORGAN", "GUITAR", "BASS", "STRINGS", "ENSEMBLE", "BRASS", "REED", "PIPE", "SYNTH LEAD", "SYNTH PAD", "SYNTH FX", "ETHNIC", "PERCUSSIVE", "SFX", "DRUMS"];
var FAM_SHORT = ["PIANO", "C.PERC", "ORGAN", "GUITAR", "BASS", "STRINGS", "ENSMBL", "BRASS", "REED", "PIPE", "LEAD", "PAD", "SYN FX", "ETHNIC", "PERC", "SFX", "DRUMS"];
var PROGRAMS = {
    "PIANO": ["GRAND", "BRIGHT", "ELEC GRAND", "HONKY-TONK", "E.PIANO 1", "E.PIANO 2", "HARPSICHORD", "CLAVI"],
    "CHROM PERC": ["CELESTA", "GLOCKENSPIEL", "MUSIC BOX", "VIBRAPHONE", "MARIMBA", "XYLOPHONE", "TUBULAR BELLS", "DULCIMER"],
    "ORGAN": ["DRAWBAR", "PERCUSSIVE", "ROCK", "CHURCH", "REED", "ACCORDION", "HARMONICA", "TANGO ACC"],
    "GUITAR": ["NYLON", "STEEL", "JAZZ", "CLEAN", "MUTED", "OVERDRIVE", "DISTORTION", "HARMONICS"],
    "BASS": ["ACOUSTIC", "FINGER", "PICK", "FRETLESS", "SLAP 1", "SLAP 2", "SYNTH 1", "SYNTH 2"],
    "STRINGS": ["VIOLIN", "VIOLA", "CELLO", "CONTRABASS", "TREMOLO", "PIZZICATO", "HARP", "TIMPANI"],
    "ENSEMBLE": ["STRINGS 1", "STRINGS 2", "SYN STRINGS 1", "SYN STRINGS 2", "CHOIR AAHS", "VOICE OOHS", "SYNTH VOICE", "ORCH HIT"],
    "BRASS": ["TRUMPET", "TROMBONE", "TUBA", "MUTED TPT", "FRENCH HORN", "SECTION", "SYN BRASS 1", "SYN BRASS 2"],
    "REED": ["SOPRANO SAX", "ALTO SAX", "TENOR SAX", "BARI SAX", "OBOE", "ENGLISH HORN", "BASSOON", "CLARINET"],
    "PIPE": ["PICCOLO", "FLUTE", "RECORDER", "PAN FLUTE", "BOTTLE", "SHAKUHACHI", "WHISTLE", "OCARINA"],
    "SYNTH LEAD": ["SQUARE", "SAW", "CALLIOPE", "CHIFF", "CHARANG", "VOICE", "FIFTHS", "BASS+LEAD"],
    "SYNTH PAD": ["NEW AGE", "WARM", "POLYSYNTH", "CHOIR", "BOWED", "METALLIC", "HALO", "SWEEP"],
    "SYNTH FX": ["RAIN", "SOUNDTRACK", "CRYSTAL", "ATMOSPHERE", "BRIGHTNESS", "GOBLINS", "ECHOES", "SCI-FI"],
    "ETHNIC": ["SITAR", "BANJO", "SHAMISEN", "KOTO", "KALIMBA", "BAGPIPE", "FIDDLE", "SHANAI"],
    "PERCUSSIVE": ["TINKLE BELL", "AGOGO", "STEEL DRUMS", "WOODBLOCK", "TAIKO", "MELODIC TOM", "SYNTH DRUM", "REVERSE CYM."],
    "SFX": ["FRET NOISE", "BREATH", "SEASHORE", "BIRD TWEET", "TELEPHONE", "HELICOPTER", "APPLAUSE", "GUNSHOT"],
    "DRUMS": ["STANDARD KIT"]
};
function programs(f) { return PROGRAMS[FAMILIES[f]] || ["1", "2", "3", "4", "5", "6", "7", "8"]; }
function instName(i) { return i === 128 ? "DRUMS" : programs(Math.floor(i / 8))[i % 8]; }
// rhythm mask units as the server names them (fraction of a quarter note)
var UNIT_INFO = { whole: [4, "1/1"], half: [2, "1/2"], quarter: [1, "1/4"], quarter_triplet: [1 / 3, "1/4T"],
                  eighth: [0.5, "1/8"], eighth_triplet: [1 / 6, "1/8T"], sixteenth: [0.25, "1/16"], sixteenth_triplet: [1 / 12, "1/16T"] };
var UNIT_ORDER = ["whole", "half", "quarter", "quarter_triplet", "eighth", "eighth_triplet", "sixteenth", "sixteenth_triplet"];

// ------------------------------------------------------------------ state (from midigpt.js) + view state (here)
var S = {
    scene: -1, bars: 8, ts: "4/4", cur: -1, tracks: [],
    tp: { poly: [0, 0], len: [0, 0], density: 0, key: 0, range: 0, silence: 0, pcs: 0 },
    masks: { scale: 0, root: 0, mode: 0, register: [0, 127], rhythm: 0, unit: "sixteenth", strength: 0.8, exact: 0, pattern: [], remix: 0, amount: 0.3, pd: 0 },
    sample: { temp: 1, topp: 1, topk: 0, esc: 1, takes: 1, seed: 0 },
    checks: { novelty: 1, silence: 1, shuffle: 0 },
    engine: { model: "", models: [], dims: [4], context: 4, context_auto: 1, bps: 1, bps_auto: 1, tps: 1, tps_auto: 1, attempts: 3, polylim: 0, denslim: 0, maskp: 0, maskk: 0, velocity: 0, micro: 0 },
    server: { online: 0, latency: 0, url: "", caps: { mask: 0, remix: 0, rhythm: 0, scales: [], units: [], vel: 0, micro: 0, attrs: [] }, res: 12 },
    gen: { status: "idle", t0: 0, elapsed: 0, notes: 0, seed: 0, att: 0, tps: 0, ctx: 0, maxctx: 0, takes: [], cur: -1, orig: 0 },
    err: null,
    tagging: 0
};
var NOTESDATA = [];   // per track (S.tracks order), per bar
var ui = { page: "main", scroll: { row: 0, bar: 0 }, anim: {}, press: null, takePage: 0,
           setup: { sel: 0, picked: {}, scroll: 0, browseFam: null, wiz: null, resetArm: 0 }, editingUrl: false, flash: null, engList: "models", genreScroll: 0 };
var errSeen = null;   // the fault the person has not cleared yet (cleared locally; a new one replaces it)

var lastKey = null, notesVer = 0;
function panel_state(json) {
    json = joinParts("state", json);
    if (json === null) return;
    try { S = JSON.parse(json); } catch (e) { post("midigpt_panel: bad state\n"); return; }
    if (S.err && (!errSeen || errSeen.id !== S.err.id)) errSeen = ext({ t: now() }, S.err);
    if (!S.err) errSeen = null;
    if (ui.setup.sel >= S.tracks.length) ui.setup.sel = Math.max(0, S.tracks.length - 1);
    refresh();
}
// only the roll draws notes (the patch sends them nowhere else; this guards a stale patch). "pm": per mille values.
var NSCALE = 1;
function panel_notes(json) {
    if (!inRegion("roll")) return;
    json = joinParts("notes", json);
    if (json === null) return;
    try { var nd = JSON.parse(json); NOTESDATA = nd.tracks || []; NSCALE = nd.pm ? 0.001 : 1; } catch (e) {}
    notesVer++;
    redraw();
}
// a long panel_state / panel_notes arrives in parts, "~part:<i>:<n>|<text>" (see panel_send in midigpt_panel_link.js);
// returns the whole message once every part is in, else null
var PARTS = {};
function joinParts(kind, msg) {
    msg = String(msg);
    if (msg.substr(0, 6) !== "~part:") return msg;
    var bar = msg.indexOf("|"), hd = msg.substring(6, bar).split(":"), i = +hd[0], n = +hd[1];
    var p = PARTS[kind];
    if (!p || p.n !== n || i === 0) p = PARTS[kind] = { n: n, got: 0, s: [] };
    if (p.s[i] === undefined) p.got++;
    p.s[i] = msg.substr(bar + 1);
    if (p.got < n) return null;
    delete PARTS[kind];
    return p.s.join("");
}
function page(name) { if (ui.page === name) return; ui.page = String(name); if (ui.page !== "setup") ui.editingUrl = false; if (ui.page !== "main") ui.seedEditing = false; redraw(); }
// what this region draws, as a string: repaint when it changes
function regionKey() {
    var c = cur(), base = ui.page + "|";
    switch (REGION) {
        case "top": return base;
        case "roll": return base + JSON.stringify([S.tracks, S.bars, S.ts, S.cur, S.gen.status, S.gen.takes, S.gen.cur, S.gen.picked, S.gen.dropped, S.engine.model, S.server.online, S.server.latency, S.scene]);
        case "main":
            if (ui.page === "main") return base + JSON.stringify([S.tp, c ? [c.short, c.inst, isTarget(c)] : 0, S.sample, S.checks]);
            if (ui.page === "engine") return base + JSON.stringify([S.engine, S.checks, S.server.caps, S.server.online, S.server.res, ui.engList, ui.genreScroll]);
            return base + JSON.stringify([S.tracks, S.server.url, S.server.online, S.tagging]);
        case "output": return base + JSON.stringify([S.gen, S.sample.takes, S.err, S.server.online, S.engine.attempts]);
        case "masks": return base + JSON.stringify([S.masks, S.server.caps, S.ts, S.server.res, c ? [c.short, isTarget(c)] : 0]);
    }
    return Math.random();
}
function refresh() {
    var k = regionKey();
    if (k !== lastKey) { lastKey = k; redraw(); }
    if (streamingHere() || (errSeen && errSeen.retry && !errSeen.retried)) again(STREAM_MS);
}

function curIdx() { for (var i = 0; i < S.tracks.length; i++) if (S.tracks[i].i === S.cur) return i; return -1; }
function cur() { var i = curIdx(); return i >= 0 ? S.tracks[i] : null; }
function curKind() { var t = cur(); return t && t.inst === 128 ? "drums" : "melodic"; }
function setupTrack() { return S.tracks[Math.min(ui.setup.sel, S.tracks.length - 1)] || null; }
// AR: every bar from its start (t.as) to the end of the clip; the bars before the start are its history
function painted(t, b) { return !t.ig && (t.ar ? (b < t.nb || !t.hc) && b >= (t.as || 0) : t.paint.charAt(b) === "1"); }
function isTarget(t) { if (t.ig) return false; if (t.ar) return true; return t.paint.indexOf("1") >= 0; }
function caps() { return S.server.caps || {}; }
function hasAttr(name) { var a = caps().attrs; return !!(a && a.indexOf(name) >= 0); }

// ------------------------------------------------------------------ text
function txt(x, y, s, size, col, align, spacing, weight) {
    g.save();
    g.font = (weight || 700) + " " + size + "px";
    g.letterSpacing = (spacing == null ? 1 : spacing) + "px";
    g.fillStyle = col; g.textBaseline = "middle"; g.textAlign = align || "left";
    g.fillText(s, x, y);
    g.restore();
}

// the largest size (down to 60 %) at which s fits in maxW
function fitSize(s, size, spacing, maxW) {
    g.save(); g.font = "700 " + size + "px"; g.letterSpacing = spacing + "px";
    var w = g.measureText(s).width; g.restore();
    return w <= maxW ? size : Math.max(size * 0.6, size * maxW / w);
}

// ------------------------------------------------------------------ hit registry (rebuilt every paint)
var hits = [];
function hit(kind, x, y, w, h, data) { hits.push({ kind: kind, x: x, y: y, w: w, h: h, d: data }); }
function find(x, y, kind) {
    for (var i = hits.length - 1; i >= 0; i--) {
        var h = hits[i];
        if ((!kind || h.kind === kind) && x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h) return h;
    }
    return null;
}

// ------------------------------------------------------------------ LEDs, rings
var GLOW_PASSES = [[3.4, 0.07], [2.4, 0.12], [1.6, 0.2]];
function ledStroke(draw, width, fill, rgb) {
    g.save();
    g.lineCap = "round"; g.lineJoin = "round";
    for (var i = 0; i < GLOW_PASSES.length; i++) {
        var p = GLOW_PASSES[i];
        g.strokeStyle = "rgba(" + (rgb || T.ledRgb) + "," + p[1] + ")"; g.fillStyle = g.strokeStyle; g.lineWidth = width * p[0];
        draw(true); g.stroke();
    }
    g.strokeStyle = rgb ? "rgb(" + rgb + ")" : ACC; g.fillStyle = g.strokeStyle; g.lineWidth = width;
    draw(false);
    if (fill) g.fill(); else g.stroke();
    g.restore();
}
function knobRing(cx, cy, r, lo, hi, dim, auto) {
    var rr = r * 1.24, bw = Math.max(2, r * 0.12), n = Math.max(9, Math.round(r * 0.6) | 1), step = 270 / n, k, a0, a1;
    g.lineCap = "round";
    if (auto) {
        g.strokeStyle = dim ? T.dashOff : "rgba(" + T.ledRgb + ",0.38)"; g.lineWidth = bw; g.beginPath();
        for (k = 0; k < n; k++) {
            a0 = (135 + k * step + step * 0.36) * Math.PI / 180; a1 = (135 + (k + 1) * step - step * 0.36) * Math.PI / 180;
            g.moveTo(cx + rr * Math.cos(a0), cy + rr * Math.sin(a0)); g.arc(cx, cy, rr, a0, a1);
        }
        g.stroke();
        g.lineCap = "butt";
        return;
    }
    var lit = [], unlit = 0;
    g.beginPath();          // the unlit segments share one style: one path, one stroke
    for (k = 0; k < n; k++) {
        a0 = (135 + k * step + step * 0.36) * Math.PI / 180; a1 = (135 + (k + 1) * step - step * 0.36) * Math.PI / 180;
        var mid = (k + 0.5) / n, on = !dim && mid >= lo - 0.5 / n && mid <= hi + 0.5 / n && hi > 0.004;
        if (on) lit.push([a0, a1]);
        else { g.moveTo(cx + rr * Math.cos(a0), cy + rr * Math.sin(a0)); g.arc(cx, cy, rr, a0, a1); unlit++; }
    }
    if (unlit) { g.strokeStyle = T.dashOff; g.lineWidth = bw; g.stroke(); }
    if (lit.length) ledStroke(function () {
        g.beginPath();
        for (var j = 0; j < lit.length; j++) { g.moveTo(cx + rr * Math.cos(lit[j][0]), cy + rr * Math.sin(lit[j][0])); g.arc(cx, cy, rr, lit[j][0], lit[j][1]); }
    }, bw);
    g.lineCap = "butt";
}
function pointer(cx, cy, r, v, w) {
    var a = (-135 + 270 * v) * Math.PI / 180, s = Math.sin(a), c = -Math.cos(a);
    ledStroke(function () { g.beginPath(); g.moveTo(cx + r * 0.42 * s, cy + r * 0.42 * c); g.lineTo(cx + r * 0.72 * s, cy + r * 0.72 * c); }, w || Math.max(1.6, r * 0.085));
}
function round(x, y, w, h, r) {
    g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

// ------------------------------------------------------------------ knob definitions
// v() -> 0..1 (or [lo, hi] for range knobs), set(v) updates the local copy, emit() tells midigpt.js
function clamp01(x) { return Math.max(0, Math.min(1, x)); }
function lin(objFn, key, a, b, step, emit) {
    return {
        v: function () { return (objFn()[key] - a) / (b - a); },
        set: function (x) { var val = a + clamp01(x) * (b - a); if (step) val = Math.round(val / step) * step; objFn()[key] = +val.toFixed(4); },
        raw: function (val) { objFn()[key] = val; },
        emit: function () { emit(objFn()[key]); }
    };
}
function rangeDef(objFn, key, a, b, emit) {
    return {
        range: true,
        v: function () { var p = objFn()[key]; return [(p[0] - a) / (b - a), (p[1] - a) / (b - a)]; },
        set: function (x, end) {
            var p = objFn()[key], val = Math.round(a + clamp01(x) * (b - a));
            p[end] = val;
            if (p[0] > p[1]) { if (end === 0) p[1] = p[0]; else p[0] = p[1]; }
        },
        emit: function () { var p = objFn()[key]; emit(p[0], p[1]); }
    };
}
var tp = function () { return S.tp; };
var smp = function () { return S.sample; };
var eng = function () { return S.engine; };
var msk = function () { return S.masks; };
function scales() { return caps().scales && caps().scales.length ? caps().scales : ["major"]; }
function units() { var u = caps().units && caps().units.length ? caps().units : UNIT_ORDER; return UNIT_ORDER.filter(function (n) { return u.indexOf(n) >= 0; }); }
function nn(m) { return NOTES[m % 12] + (Math.floor(m / 12) - 1); }
function noScaleMask() { return !caps().mask || !S.masks.scale; }

var KNOBS = {
    // TRACK (the selected track). 0 = AUTO for each of these, as midigpt.js stores them.
    "POLY": ext(rangeDef(tp, "poly", 1, 10, function (lo, hi) { send("track", "poly", lo, hi); }),
                { show: function () { return curKind() !== "drums"; }, fmt: function () { var p = S.tp.poly; return p[0] + "–" + p[1]; },
                  isAuto: function () { return !S.tp.poly[0]; }, setAuto: function (v) { S.tp.poly = v ? [0, 0] : [1, 3]; send("track", "poly", S.tp.poly[0], S.tp.poly[1]); } }),
    "LENGTH": ext(rangeDef(tp, "len", 1, 6, function (lo, hi) { send("track", "len", lo, hi); }),
                  { show: function () { return curKind() !== "drums"; }, fmt: function () { var p = S.tp.len; return DUR[p[0] - 1] + "–" + DUR[p[1] - 1]; },
                    isAuto: function () { return !S.tp.len[0]; }, setAuto: function (v) { S.tp.len = v ? [0, 0] : [2, 4]; send("track", "len", S.tp.len[0], S.tp.len[1]); } }),
    // prism / expressive: shown only when the model has the control (0 = any)
    "KEY": ext(lin(tp, "key", 1, 24, 1, function (v) { send("track", "key", v); }),
               { show: function () { return hasAttr("key_signature") && curKind() !== "drums"; },
                 fmt: function () { var k = S.tp.key - 1; return NOTES[k % 12] + (k >= 12 ? "m" : ""); },
                 isAuto: function () { return !S.tp.key; }, setAuto: function (v) { S.tp.key = v ? 0 : 1; send("track", "key", S.tp.key); } }),
    "RANGE": ext(lin(tp, "range", 1, 48, 1, function (v) { send("track", "range", v); }),
                 { show: function () { return hasAttr("pitch_range") && curKind() !== "drums"; }, fmt: function () { return S.tp.range + " ST"; },
                   isAuto: function () { return !S.tp.range; }, setAuto: function (v) { S.tp.range = v ? 0 : 12; send("track", "range", S.tp.range); } }),
    "SILENCE": ext(lin(tp, "silence", 1, 10, 1, function (v) { send("track", "silence", v); }),
                   { show: function () { return hasAttr("silence_proportion"); }, fmt: function () { return (S.tp.silence - 1) * 10 + "%"; },
                     isAuto: function () { return !S.tp.silence; }, setAuto: function (v) { S.tp.silence = v ? 0 : 3; send("track", "silence", S.tp.silence); } }),
    // NOMML (expressive): the median rhythmic grid the notes sit on, 0 = on the beat ... 12 = freely timed
    "EXPRESSIVENESS": ext(lin(tp, "nomml", 1, 13, 1, function (v) { send("track", "nomml", v); }),
                          { show: function () { return hasAttr("nomml"); }, labelW: 70,
                            fmt: function () { return S.tp.nomml >= 13 ? "FREE" : S.tp.nomml <= 1 ? "GRID" : String(S.tp.nomml - 1); },
                            isAuto: function () { return !S.tp.nomml; }, setAuto: function (v) { S.tp.nomml = v ? 0 : 13; send("track", "nomml", S.tp.nomml); } }),
    "PCS": ext(lin(tp, "pcs", 1, 12, 1, function (v) { send("track", "pcs", v); }),
               { show: function () { return hasAttr("pitch_class_set") && curKind() !== "drums"; }, fmt: function () { return S.tp.pcs + " PC"; },
                 isAuto: function () { return !S.tp.pcs; }, setAuto: function (v) { S.tp.pcs = v ? 0 : 7; send("track", "pcs", S.tp.pcs); } }),
    "DENSITY": ext(lin(tp, "density", 1, 10, 1, function (v) { send("track", "density", v); }),
                   { show: function () { return curKind() === "drums"; }, fmt: function () { return String(S.tp.density); },
                     isAuto: function () { return !S.tp.density; }, setAuto: function (v) { S.tp.density = v ? 0 : 5; send("track", "density", S.tp.density); } }),
    // SAMPLE
    "TEMP": ext(lin(smp, "temp", 0.1, 3, 0.05, function (v) { send("sample", "temp", v); }), { fmt: function () { return S.sample.temp.toFixed(2); }, def: 1 }),
    "TOP-P": ext(lin(smp, "topp", 0.05, 1, 0.01, function (v) { send("sample", "topp", v); }), { fmt: function () { return S.sample.topp >= 1 ? "OFF" : S.sample.topp.toFixed(2); }, def: 1 }),
    "TOP-K": ext(lin(smp, "topk", 0, 500, 5, function (v) { send("sample", "topk", v); }), { fmt: function () { return S.sample.topk ? String(S.sample.topk) : "OFF"; }, def: 0 }),
    "ESC": ext(lin(smp, "esc", 1, 3, 0.05, function (v) { send("sample", "esc", v); }), { fmt: function () { return S.sample.esc.toFixed(2); }, def: 1 }),
    "TAKES": ext(lin(smp, "takes", 1, 16, 1, function (v) { send("sample", "takes", v); }), { fmt: function () { return String(S.sample.takes); }, def: 1 }),
    "PROB": ext(lin(smp, "prob", 0.05, 1, 0.05, function (v) { send("sample", "prob", v); }),
                { fmt: function () { return S.sample.prob >= 1 ? "ALL" : Math.round(S.sample.prob * 100) + "%"; }, def: 1 }),
    // ENGINE
    "CONTEXT": {
        v: function () { var d = S.engine.dims; return d.length > 1 ? Math.max(0, d.indexOf(S.engine.context)) / (d.length - 1) : 0.5; },
        set: function (x) { var d = S.engine.dims; S.engine.context = d[Math.round(clamp01(x) * (d.length - 1))]; },
        emit: function () { send("engine", "model_dim", S.engine.context); },
        fmt: function () { return S.engine.context + " BARS"; },
        isAuto: function () { return !!S.engine.context_auto; }, setAuto: function (v) { S.engine.context_auto = v ? 1 : 0; send("engine", "model_dim", v ? 0 : S.engine.context); }
    },
    "BARS/STEP": {
        v: function () { return (S.engine.bps - 1) / Math.max(1, S.engine.context - 1); },
        set: function (x) { S.engine.bps = 1 + Math.round(clamp01(x) * (S.engine.context - 1)); },
        emit: function () { send("engine", "bars_per_step", S.engine.bps); },
        fmt: function () { return String(S.engine.bps); },
        isAuto: function () { return !!S.engine.bps_auto; }, setAuto: function (v) { S.engine.bps_auto = v ? 1 : 0; send("engine", "bars_per_step", v ? 0 : S.engine.bps); }
    },
    "TRK/STEP": ext(lin(eng, "tps", 1, 16, 1, function (v) { send("engine", "tracks_per_step", v); }),
                    { fmt: function () { return String(S.engine.tps); }, isAuto: function () { return !!S.engine.tps_auto; },
                      setAuto: function (v) { S.engine.tps_auto = v ? 1 : 0; send("engine", "tracks_per_step", v ? 0 : S.engine.tps); } }),
    "ATTEMPTS": ext(lin(eng, "attempts", 1, 10, 1, function (v) { send("engine", "max_attempts", v); }), { fmt: function () { return String(S.engine.attempts); }, def: 3 }),
    "POLY LIM": ext(lin(eng, "polylim", 0, 32, 1, function (v) { send("engine", "poly_limit", v); }), { fmt: function () { return S.engine.polylim ? String(S.engine.polylim) : "OFF"; }, def: 0 }),
    "DENS LIM": ext(lin(eng, "denslim", 0, 64, 1, function (v) { send("engine", "density_limit", v); }), { fmt: function () { return S.engine.denslim ? String(S.engine.denslim) : "OFF"; }, def: 0 }),
    "MASK P": ext(lin(eng, "maskp", 0, 0.95, 0.05, function (v) { send("engine", "mask_p", v); }), { fmt: function () { return S.engine.maskp ? S.engine.maskp.toFixed(2) : "OFF"; }, def: 0 }),
    "MASK K": ext(lin(eng, "maskk", 0, 100, 1, function (v) { send("engine", "mask_k", v); }), { fmt: function () { return S.engine.maskk ? String(S.engine.maskk) : "OFF"; }, def: 0 }),
    // MASKS (the selected track)
    "ROOT": ext(lin(msk, "root", 0, 11, 1, function (v) { send("mask", "root", v); }), { fmt: function () { return NOTES[S.masks.root]; }, dim: noScaleMask }),
    "MODE": {
        v: function () { var l = scales(); return l.length > 1 ? Math.max(0, S.masks.mode) / (l.length - 1) : 0; },
        set: function (x) { S.masks.mode = Math.round(clamp01(x) * (scales().length - 1)); },
        emit: function () { send("mask", "scale", scales()[S.masks.mode]); },
        fmt: function () { return (scales()[S.masks.mode] || "").toUpperCase().replace(/_/g, " ").replace("PENTATONIC", "PENT").replace("HARMONIC", "HARM").replace("MELODIC", "MEL").replace("MIXOLYDIAN", "MIXO"); },
        dim: noScaleMask
    },
    "REGISTER": ext(rangeDef(msk, "register", 0, 127, function (lo, hi) { send("mask", "register", lo, hi); }),
                    { fmt: function () { var p = S.masks.register; return p[0] <= 0 && p[1] >= 127 ? "FULL" : nn(p[0]) + "–" + nn(p[1]); }, dim: noScaleMask }),
    "UNIT": {
        v: function () { var l = units(); return l.length > 1 ? Math.max(0, l.indexOf(S.masks.unit)) / (l.length - 1) : 0; },
        set: function (x) { var l = units(); S.masks.unit = l[Math.round(clamp01(x) * (l.length - 1))]; },
        emit: function () { send("mask", "unit", S.masks.unit); },
        fmt: function () { return (UNIT_INFO[S.masks.unit] || [0, "?"])[1]; },
        dim: function () { return !S.masks.rhythm; }
    },
    "STRENGTH": ext(lin(msk, "strength", 0, 1, 0.05, function (v) { send("mask", "strength", v); }),
                    { fmt: function () { return Math.round(S.masks.strength * 100) + "%"; }, dim: function () { return !S.masks.rhythm || S.masks.exact; } }),
    "AMOUNT": ext(lin(msk, "amount", 0, 1, 0.05, function (v) { send("mask", "amount", v); }),
                  { fmt: function () { return Math.round(S.masks.amount * 100) + "%"; }, dim: function () { return !caps().remix || !S.masks.remix; } })
};

var TOGGLES = {
    "NOVELTY": { get: function () { return S.checks.novelty; }, set: function (v) { S.checks.novelty = v; send("engine", "novelty", v); } },
    "SILENCE CHK": { label: "SILENCE", get: function () { return S.checks.silence; }, set: function (v) { S.checks.silence = v; send("engine", "silence", v); } },
    "SHUFFLE": { get: function () { return S.checks.shuffle; }, set: function (v) { S.checks.shuffle = v; send("engine", "shuffle", v); } },
    "SCALE": { get: function () { return S.masks.scale; }, set: function (v) { S.masks.scale = v; send("mask", "scale_on", v); }, dim: function () { return !caps().mask; } },
    "RHYTHM": { get: function () { return S.masks.rhythm; }, set: function (v) { S.masks.rhythm = v; send("mask", "rhythm", v); }, dim: function () { return !caps().rhythm; } },
    "REMIX": { get: function () { return S.masks.remix; }, set: function (v) { S.masks.remix = v; send("mask", "remix", v); }, dim: function () { return !caps().remix; } },
    "P+D": { get: function () { return S.masks.pd; }, set: function (v) { S.masks.pd = v; send("mask", "pd", v); }, dim: function () { return !caps().remix || !S.masks.remix; } },
    "VELOCITY": { get: function () { return S.engine.velocity; }, set: function (v) { S.engine.velocity = v; send("engine", "velocity", v); }, dim: function () { return !caps().vel; } },
    "MICRO": { get: function () { return S.engine.micro; }, set: function (v) { S.engine.micro = v; send("engine", "microtiming", v); }, dim: function () { return !caps().micro; } }
};

// ------------------------------------------------------------------ parts
function drawKnob(def, name, cx, cy, r) {
    if (!def || (def.show && !def.show())) return;
    var dim = def.dim ? def.dim() : false, o = SP.sprites.knob[r];
    if (dim) g.globalAlpha = 0.55;
    if (o) drawImg("knob_" + r + ".png", cx - o.ox, cy - o.oy);
    var v = def.v(), auto = def.isAuto && def.isAuto();
    if (auto) knobRing(cx, cy, r, 0, 1, dim, true);
    else if (def.range) {
        knobRing(cx, cy, r, v[0], v[1], dim);
        if (!dim) { pointer(cx, cy, r, v[0], Math.max(1.2, r * 0.06)); pointer(cx, cy, r, v[1]); }
    } else {
        knobRing(cx, cy, r, 0, v, dim);
        if (!dim) pointer(cx, cy, r, v);
    }
    g.globalAlpha = 1;
    var ly = cy + r * 1.24 + r * 0.06 + 10;
    var lab = def.label || name, ls = r < 20 ? 6.8 : 7.4;
    if (def.labelW) ls = fitSize(lab, ls, 1, def.labelW);    // a long name shrinks to its column
    txt(cx, ly, lab, ls, dim ? T.dim : LAB, "center", 1);
    txt(cx, ly + 10, auto ? "AUTO" : def.fmt(), 6.6, dim ? T.dim : auto ? ACC : INK, "center", auto ? 1 : 0.6);
    hit("knob", cx - r * 1.35, cy - r * 1.35, r * 2.7, r * 2.7, { def: def, name: name, cx: cx, cy: cy, r: r, dim: dim });
}
function drawToggle(def, name, x, y, w, h) {
    var on = def.get() ? 1 : 0, dim = def.dim ? def.dim() : false, key = name + x + y;
    var t = ui.anim[key] == null ? on : ui.anim[key];
    t += (on - t) * 0.55; if (Math.abs(on - t) < 0.02) t = on; else again(0); ui.anim[key] = t;
    if (dim) g.globalAlpha = 0.5;
    var sh = h * 0.8;
    if (t > 0.02) { g.save(); g.globalAlpha *= t; g.fillStyle = T.slotOn; round(x + 0.6, y + h / 2 - sh / 2 + 0.6, w - 1.2, sh - 1.2, sh / 2); g.fill(); g.restore(); }
    var o = SP.sprites.thumb[w + "x" + h], tx = x - 2 + t * (w - o.tw + 4), ty = y + h / 2 - o.th / 2;
    drawImg("thumb_" + w + "x" + h + ".png", tx - o.ox, ty - o.oy);
    var lx = tx + o.tw / 2, lyy = y + h / 2;
    if (on && !dim) ledStroke(function () { g.beginPath(); g.arc(lx, lyy, 2, 0, Math.PI * 2); }, 1.6, true);
    else { g.beginPath(); g.arc(lx, lyy, 2, 0, Math.PI * 2); g.fillStyle = T.togLedOff; g.fill(); }
    g.globalAlpha = 1;
    txt(x + w / 2, y - 9, def.label || name, 6.6, dim ? T.dim : LAB, "center", 0.9);
    if (!dim) hit("toggle", x - 8, y - 6, w + 16, h + 12, { def: def });
}
function drawKey(x, y, w, h, label, lit, onClick, opts) {
    opts = opts || {};
    var o = SP.sprites.key[w + "x" + h], down = ui.press && ui.press.x === x && ui.press.y === y;
    if (opts.dim) g.globalAlpha = opts.off ? 0.28 : 0.62;
    if (o) drawImg("key_" + w + "x" + h + ".png", x - o.ox, y - o.oy + (down ? 0.8 : 0));
    var mx = x + w / 2, sw = Math.min(18, w * 0.4);
    var bar = h < 12 ? [mx - sw / 2, y + h / 2 - 1, sw, 2] : h > 20 ? [mx - sw / 2, y + 4, sw, 2] : [mx - 3, y + 4, 6, 2];
    if (opts.led) lit = true;
    if (lit) ledStroke(function () { round(bar[0], bar[1] + (down ? 0.8 : 0), bar[2], bar[3], 1); }, 1.4, true, opts.led);
    else { g.fillStyle = T.keyLedOff; round(bar[0], bar[1], bar[2], bar[3], 1); g.fill(); }
    if (label === "<ret>") {
        var ay = y + h / 2 + 2 + (down ? 0.8 : 0);
        g.save(); g.strokeStyle = lit ? T.keyLit : T.keyText; g.lineWidth = 1.5; g.lineCap = "round"; g.lineJoin = "round";
        g.beginPath(); g.moveTo(mx + 5, ay - 5); g.lineTo(mx + 5, ay + 2); g.lineTo(mx - 5, ay + 2); g.moveTo(mx - 2, ay - 1); g.lineTo(mx - 5, ay + 2); g.lineTo(mx - 2, ay + 5); g.stroke(); g.restore();
    } else if (label) {
        txt(mx, y + h / 2 + 2 + (down ? 0.8 : 0), label, opts.size || (h > 50 ? 11 : 7.6), lit ? T.keyLit : T.keyText, "center", opts.spacing == null ? 1 : opts.spacing);
    }
    g.globalAlpha = 1;
    if (!opts.dim && onClick) hit("key", x, y, w, h, { fn: onClick, x: x, y: y });
}
// ------------------------------------------------------------------ seed
// A seed names a result, not a quantity: a readout and two keys instead of a knob.
//   DICE  rolls a new fixed seed
//   LOCK  lit: back to a random seed each run. Off: keep the seed you just heard (the selected take's in a batch,
//         else the last generation's)
//   the readout: click to type a seed (a native textedit, seed_text, opened by "seed_edit 1"); empty = random
function seedNow() { return S.sample.seed > 0 ? S.sample.seed : 0; }
function seedHeard() {            // [seed, where it came from] of the result on screen, or null
    var G = S.gen;
    if (!G.seed) return null;
    if (G.takes.length > 1 && G.cur >= 0) return [G.seed + G.cur, "TAKE " + (G.cur + 1)];
    return [G.seed, "LAST RUN"];
}
function seedRoll() { return 1 + Math.floor(Math.random() * 2147483646); }
function seedKey(x, y, w, h, label, lit, onClick, enabled) {
    var down = ui.press && ui.press.x === x && ui.press.y === y;
    g.save();
    if (enabled === false) g.globalAlpha = 0.4;
    g.fillStyle = "#1A1A1A"; round(x, y + (down ? 0.6 : 0), w, h, 2.5); g.fill();
    g.strokeStyle = "rgba(255,255,255,0.07)"; g.lineWidth = 0.8; round(x + 0.4, y + 0.4 + (down ? 0.6 : 0), w - 0.8, h - 0.8, 2.2); g.stroke();
    if (lit) ledStroke(function () { round(x + w / 2 - 5, y + 2.6 + (down ? 0.6 : 0), 10, 1.6, 0.8); }, 1.2, true);
    else { g.fillStyle = T.keyLedOff; round(x + w / 2 - 5, y + 2.6, 10, 1.6, 0.8); g.fill(); }
    txt(x + w / 2, y + h / 2 + 2 + (down ? 0.6 : 0), label, 5.8, lit ? T.keyLit : T.keyText, "center", 0.9);
    g.restore();
    if (enabled !== false && onClick) hit("key", x, y, w, h, { fn: onClick, x: x, y: y });
}
var SEED_W = 76, SEED_H = 20;
function seedRect(cx, cy) { return [cx - SEED_W / 2, cy - 17, SEED_W, SEED_H]; }
function drawSeed(cx, cy) {
    var r = seedRect(cx, cy), x = r[0], sy = r[1], w = r[2], seed = seedNow(), heard = seedHeard();
    // a screen sits in a little dip, like the stats screen: a darker rim, shadow at the top, light at the bottom
    g.fillStyle = "#1B1B1B"; round(x - 2.6, sy - 2.6, w + 5.2, SEED_H + 5.2, 5); g.fill();
    g.strokeStyle = "rgba(0,0,0,0.6)"; g.lineWidth = 1; round(x - 2.2, sy - 2.4, w + 4.4, SEED_H + 4.2, 4.6); g.stroke();
    g.strokeStyle = "rgba(255,255,255,0.05)"; g.lineWidth = 0.8; round(x - 2.6, sy - 2.0, w + 5.2, SEED_H + 5.0, 5); g.stroke();
    g.fillStyle = T.screenBg; round(x, sy, w, SEED_H, 3); g.fill();
    if (ui.seedEditing) {                             // the native field draws the text; outline the readout
        g.strokeStyle = ACC; g.lineWidth = 1; round(x + 0.5, sy + 0.5, w - 1, SEED_H - 1, 2.6); g.stroke();
        txt(x + 4, sy + 5.5, "1 – 2147483647", 4.6, rgba(HUD.g, 0.6), "left", 0.6);
    } else {
        g.strokeStyle = "rgba(255,255,255,0.06)"; g.lineWidth = 0.8; round(x + 0.4, sy + 0.4, w - 0.8, SEED_H - 0.8, 2.6); g.stroke();
        var main = seed ? String(seed) : "RANDOM";
        txt(x + 4, sy + 5.5, seed ? (ui.seedOrigin || "FIXED") : "CLICK TO TYPE", 4.6, rgba(HUD.g, 0.55), "left", 0.6);
        txt(x + w / 2, sy + SEED_H / 2 + 2.2, main, fitSize(main, 7.2, 0.4, w - 8), seed ? HUD.c : rgba(HUD.g, 0.75), "center", 0.4);
    }
    hit("key", x, sy, w, SEED_H, { fn: function () { ui.seedEditing = true; ui.seedBuf = ""; outlet(0, "seed_edit", 1); redraw(); }, x: x, y: sy });
    seedKey(x, sy + 24, 36, 13, "DICE", false, function () { ui.seedOrigin = "DICE"; send("sample", "seed", seedRoll()); });
    seedKey(x + 40, sy + 24, 36, 13, "LOCK", !!seed, function () {
        if (seed) { ui.seedOrigin = null; send("sample", "seed", 0); }
        else if (heard) { ui.seedOrigin = heard[1]; send("sample", "seed", heard[0]); }
    }, !!seed || !!heard);
    txt(cx, cy + 29.5, "SEED", 6.8, LAB, "center", 1);
}
function seed_done(typed) { ui.seedEditing = false; ui.seedBuf = ""; if (typed) ui.seedOrigin = "TYPED"; redraw(); }
// every key typed in the seed field (its ASCII code): keep digits only, never above the largest seed, and write the
// clean entry back into the field (the patch defers it, so it lands after the field has inserted the key)
var SEED_MAX = 2147483647;
function seed_key(k) {
    if (!ui.seedEditing) return;
    var b = ui.seedBuf || "";
    if (k >= 48 && k <= 57) { var nb = (b === "0" ? "" : b) + String.fromCharCode(k); if (+nb <= SEED_MAX) b = nb; }
    else if (k === 8 || k === 127) b = b.slice(0, -1);
    else if (k === 13 || k === 3) return;            // Enter: the field sends its text
    ui.seedBuf = b;
    outlet(0, "seed_set", b);
}

function bayTitle(x, y, w, title, sub, subCol) {
    txt(x + 14, y + 14, title, 7.5, T.title, "left", 1.6);
    if (sub) txt(x + w - 14, y + 14, sub, 6.6, subCol || INK, "right", 1.2);
}

// ------------------------------------------------------------------ HUD: piano roll
var VIEW = { rows: 6, bars: 8 };
function clampScroll() {
    ui.scroll.row = Math.max(0, Math.min(ui.scroll.row, S.tracks.length - VIEW.rows));
    ui.scroll.bar = Math.max(0, Math.min(ui.scroll.bar, S.bars - VIEW.bars));
}
var lastCur = null;
function followSelection() {   // keep Live's selected track on screen
    if (S.cur === lastCur) return;
    lastCur = S.cur;
    var i = curIdx();
    if (i < 0) return;
    if (i < ui.scroll.row) ui.scroll.row = i;
    if (i >= ui.scroll.row + VIEW.rows) ui.scroll.row = i - VIEW.rows + 1;
}
function hudRoll(x, y, w, h) {
    followSelection(); clampScroll();
    var gx = x + 106, gw = w - 106 - 16, gap = 3, n = Math.min(VIEW.rows, S.tracks.length), bars = Math.min(VIEW.bars, S.bars);
    var r0 = ui.scroll.row, b0 = ui.scroll.bar;
    var top = y + 20, bottom = y + h - 18, rh = (bottom - top - (VIEW.rows - 1) * 3) / VIEW.rows, bw = (gw - gap * (bars - 1)) / bars;
    hit("roll-area", x, y, w, h, {});
    if (S.tracks.length > VIEW.rows) {   // scrollbars: drag them, or scroll (onwheel)
        var sy0 = top, sh = bottom - top, th = sh * VIEW.rows / S.tracks.length, ty = sy0 + (sh - th) * r0 / (S.tracks.length - VIEW.rows);
        g.fillStyle = rgba(HUD.g, 0.15); g.fillRect(x + w - 8, sy0, 2, sh);
        g.fillStyle = rgba(HUD.g, 0.8); g.fillRect(x + w - 8, ty, 2, th);
        txt(x + w - 7, y + 10, r0 + 1 + "–" + (r0 + n) + "/" + S.tracks.length, 5.6, rgba(HUD.g, 0.6), "right", 0.5);
        hit("vscroll", x + w - 14, sy0, 14, sh, { y0: sy0, h: sh, th: th });
    }
    if (S.bars > VIEW.bars) {
        var tw = gw * VIEW.bars / S.bars, tx = gx + (gw - tw) * b0 / (S.bars - VIEW.bars);
        g.fillStyle = rgba(HUD.g, 0.15); g.fillRect(gx, y + 13, gw, 2);
        g.fillStyle = rgba(HUD.g, 0.8); g.fillRect(tx, y + 13, tw, 2);
        hit("hscroll", gx, y + 2, gw, 14, { x0: gx, w: gw, tw: tw });
    }
    g.lineWidth = 0.8;
    var b;
    for (b = 0; b < bars; b++) {
        var bx = gx + b * (bw + gap), bn = b0 + b + 1;
        txt(bx + 2, y + 10, (bn < 10 ? "0" : "") + bn, 6.5, rgba(HUD.g, 0.9), "left", 0.5);
        g.strokeStyle = rgba(HUD.g, 0.8); g.beginPath(); g.moveTo(bx, y + 14); g.lineTo(bx, y + 17); g.stroke();
    }
    g.strokeStyle = rgba(HUD.g, 0.35); g.beginPath(); g.moveTo(gx, y + 14); g.lineTo(gx + gw, y + 14); g.stroke();
    var streaming = S.gen.status === "streaming", hasTake = S.gen.takes.length && S.gen.cur >= 0;
    if (!S.tracks.length) txt(x + w / 2, y + h / 2, S.scene < 0 ? "SELECT A SCENE IN LIVE" : "NO MIDI TRACKS", 7.5, rgba(HUD.w, 0.5), "center", 1);
    for (var j = 0; j < n; j++) {
        var i = r0 + j, t = S.tracks[i], yy = top + j * (rh + 3), tgt = isTarget(t), a = t.ig ? 0.3 : 1, sel = t.i === S.cur, ar = t.ar && !t.ig;
        var tc = ar ? HUD.a : HUD.c;
        if (sel) {   // the track the TRACK and MASKS knobs edit
            g.fillStyle = rgba(HUD.c, 0.16); g.fillRect(x + 6, yy - 1, gx - x - 10, rh + 2);
            g.fillStyle = HUD.c; g.fillRect(x + 6, yy - 1, 2, rh + 2);
            g.strokeStyle = rgba(HUD.c, 0.55); g.lineWidth = 1; g.strokeRect(x + 6.5, yy - 0.5, gx + gw - x - 6, rh + 1);
        }
        if (tgt) { g.fillStyle = tc; g.beginPath(); g.moveTo(x + 12, yy + rh / 2 - 3); g.lineTo(x + 17, yy + rh / 2); g.lineTo(x + 12, yy + rh / 2 + 3); g.closePath(); g.fill(); }
        else { g.strokeStyle = rgba(HUD.w, 0.4 * a); g.lineWidth = 0.8; g.beginPath(); g.arc(x + 14.5, yy + rh / 2, 2.2, 0, Math.PI * 2); g.stroke(); }
        // context the server left out of the last generation so every step fit: amber, struck through
        var dropped = !streaming && S.gen.dropped && S.gen.dropped.indexOf(t.i) >= 0, ns = fitSize(t.short, rh < 22 ? 7.5 : 8.5, 1, 40);
        txt(x + 22, yy + rh / 2, t.short, ns, tgt ? tc : dropped ? rgba(HUD.a, 0.8) : rgba(HUD.w, 0.75 * a), "left", 1);
        if (dropped) { g.strokeStyle = rgba(HUD.a, 0.8); g.lineWidth = 1; g.beginPath(); g.moveTo(x + 21, yy + rh / 2); g.lineTo(x + 22 + Math.min(40, t.short.length * ns * 0.8), yy + rh / 2); g.stroke(); }
        hit("roll-name", x + 18, yy, 44, rh, { t: t });
        var sw = [["AR", x + 64, t.ar, HUD.a, "roll-ar"], ["IG", x + 84, t.ig, HUD.w, "roll-ig"]];
        for (var s = 0; s < 2; s++) {
            var c = sw[s], cx = c[1], cy = yy + rh / 2 - 5.5, on = !!c[2];
            if (on) { g.fillStyle = c[3]; g.fillRect(cx, cy, 17, 11); }
            else { g.strokeStyle = rgba(HUD.w, 0.28); g.lineWidth = 0.8; g.strokeRect(cx + 0.5, cy + 0.5, 16, 10); }
            txt(cx + 8.5, cy + 5.7, c[0], 5.8, on ? T.screenBg : rgba(HUD.w, 0.5), "center", 0.4);
            hit(c[4], cx - 1, cy - 2, 19, 15, { t: t });
        }
        for (var bb = 0; bb < bars; bb++) {
            var b2 = b0 + bb, bx2 = gx + bb * (bw + gap), k = t.cells.charAt(b2) || "N", pt = painted(t, b2);
            // painted, but PROB left it out of the last generation: dim brackets, its notes drawn as context
            var skip = pt && !streaming && S.gen.picked && (S.gen.picked[t.i] || []).indexOf(b2) < 0;
            if (ar && t.as > 0 && b2 === t.as) {   // where AR starts: a bar on the cell's left edge and a notch on top
                g.fillStyle = HUD.a; g.fillRect(bx2 - 2, yy - 1, 1.5, rh + 2);
                g.beginPath(); g.moveTo(bx2 - 2, yy - 1); g.lineTo(bx2 + 3, yy - 1); g.lineTo(bx2 - 2, yy + 4); g.closePath(); g.fill();
            }
            var editable = !t.hc || b2 < t.nb;
            if (editable) hit("roll-bar", bx2, yy, bw, rh, { t: t, b: b2 });
            var notes = NOTESDATA[i] && NOTESDATA[i][b2];
            var pc = ar ? HUD.a : HUD.m, col = pt && hasTake ? pc : HUD.g;
            if (pt) {
                var L = Math.min(6, bw / 4), cs = [[bx2, yy, 1, 1], [bx2 + bw, yy, -1, 1], [bx2, yy + rh, 1, -1], [bx2 + bw, yy + rh, -1, -1]];
                g.strokeStyle = skip ? rgba(pc, 0.35) : pc; g.lineWidth = 1.1;
                for (var q = 0; q < 4; q++) { g.beginPath(); g.moveTo(cs[q][0] + cs[q][2] * L, cs[q][1]); g.lineTo(cs[q][0], cs[q][1]); g.lineTo(cs[q][0], cs[q][1] + cs[q][3] * L); g.stroke(); }
                g.fillStyle = rgba(pc, 0.05); g.fillRect(bx2, yy, bw, rh);
                // steps of 0.02: each distinct colour string is parsed and cached once, not a new one every frame
                if (streaming) { g.fillStyle = rgba(pc, Math.round((0.08 + 0.06 * Math.sin(now() / 120 + b2)) * 50) / 50); g.fillRect(bx2, yy, bw, rh); }
            } else if (!editable) {
                // past the end of this track's clip: not part of it
            } else if (!(notes && notes.length)) {
                g.strokeStyle = rgba(HUD.g, 0.25 * a); g.lineWidth = 0.8; g.setLineDash([3, 3]); g.strokeRect(bx2 + 0.5, yy + 0.5, bw - 1, rh - 1); g.setLineDash([]);
            } else {
                g.strokeStyle = rgba(HUD.g, 0.28 * a); g.lineWidth = 0.8; g.strokeRect(bx2 + 0.5, yy + 0.5, bw - 1, rh - 1);
            }
            if (notes && notes.length && (!pt || skip || hasTake || k === "C")) {
                if (skip) col = HUD.g;
                g.fillStyle = rgba(col, (pt && hasTake && !skip ? 1 : 0.6) * a);
                g.beginPath();      // one path, one fill for the whole cell (a fill per note was thousands per paint)
                for (var m = 0; m < notes.length; m++) {
                    var nt = notes[m], X0 = bx2 + 3 + nt[0] * NSCALE * (bw - 6), X1 = X0 + Math.max(2, nt[1] * NSCALE * (bw - 6)), Y0 = yy + rh - 4 - nt[2] * NSCALE * (rh - 8);
                    g.rect(X0, Y0 - 0.9, Math.min(X1, bx2 + bw - 3) - X0, 1.8);
                }
                g.fill();
                g.beginPath();
            }
        }
    }
    var tg = [];
    for (var z = 0; z < S.tracks.length; z++) if (isTarget(S.tracks[z])) tg.push(S.tracks[z].short + (S.tracks[z].ar ? " (AR)" : ""));
    txt(x + 12, y + h - 9, "TGT " + (tg.length ? tg.join(" ") : "— PAINT BARS"), 6.5, HUD.c, "left", 1);
    var link = S.server.online ? "LINK " + S.server.latency + "MS" : "NO LINK";
    txt(x + w - 12, y + h - 9, link, 6.5, S.server.online ? HUD.g : HUD.a, "right", 1);
    txt(x + w / 2, y + h - 9, (S.engine.model || "").toUpperCase().replace(/_/g, " "), 6.5, rgba(HUD.w, 0.55), "center", 1);
}

// ------------------------------------------------------------------ HUD: generation stats + faults
var LABEL_W = {};   // the stats labels' widths (fixed strings, measured once)
function hudStats(x, y, w, h) {
    var G = S.gen;
    if (errSeen) return hudFault(x, y, w, h);
    var used = G.maxctx ? G.ctx / G.maxctx : 0;
    txt(x + 8, y + 10, "CTX", 6.5, HUD.g, "left", 0.8);
    var n = 24, bx0 = x + 30, bw = (w - 30 - 66) / n;
    for (var i = 0; i < n; i++) {
        var lit = i / n < used;
        g.fillStyle = lit ? (i / n > 0.8 ? HUD.a : HUD.g) : rgba(HUD.g, 0.15);
        g.fillRect(bx0 + i * bw, y + 7, bw - 1.2, 6);
    }
    txt(x + w - 8, y + 10, G.maxctx ? Math.round(G.ctx) + "/" + G.maxctx : "—", 6.5, HUD.g, "right", 0.5);
    g.strokeStyle = rgba(HUD.g, 0.2); g.lineWidth = 0.8; g.beginPath(); g.moveTo(x + 6, y + 17); g.lineTo(x + w - 6, y + 17); g.stroke();
    var elapsed = G.status === "streaming" && G.t0 ? (now() - G.t0) / 1000 : G.elapsed;
    var status = { idle: "READY", streaming: "RUNNING", done: "DONE", error: "ERROR", cancelled: "CANCEL", cancelling: "STOPPING" }[G.status] || "READY";
    var stCol = G.status === "error" ? HUD.a : G.status === "streaming" ? HUD.c : HUD.g;
    var rows = [["TOK/S", G.tps ? G.tps.toFixed(1) : "—", HUD.c], ["TIME", elapsed ? elapsed.toFixed(2) + "S" : "—", HUD.c], ["NOTES", G.notes ? String(Math.round(G.notes)) : "—", HUD.m],
                ["SEED", G.seed ? String(G.seed) : "—", HUD.g], ["ATT", G.att ? G.att + "/" + S.engine.attempts : "—", HUD.g], ["STATUS", status, stCol]];
    var cw = (w - 16) / 3;
    for (var r = 0; r < rows.length; r++) {
        var cx = x + 8 + (r % 3) * cw, cy = y + 17 + (h - 17) * (Math.floor(r / 3) + 1) / 3;
        txt(cx, cy, rows[r][0], 5.8, rgba(rows[r][2], 0.6), "left", 0.6);
        var lw = LABEL_W[rows[r][0]];
        if (lw === undefined) { g.save(); g.font = "700 5.8px"; g.letterSpacing = "0.6px"; lw = LABEL_W[rows[r][0]] = g.measureText(rows[r][0]).width; g.restore(); }
        txt(cx + cw - 6, cy, rows[r][1], fitSize(rows[r][1], 7.5, 0.4, cw - 6 - lw - 5), rows[r][2], "right", 0.4);   // never over its label
    }
}
// Avionics-style fault: a reverse-video tag (FAULT red / CAUTION amber / NOT SENT) and a short code, then the cause and
// what to do. Pressing the screen clears it.
function hudFault(x, y, w, h) {
    var E = errSeen, col = E.warn ? HUD.a : HUD.m, age = now() - E.t, blink = age < 2400 && Math.floor(age / 300) % 2;
    if (age < 2400) again(300 - age % 300);                              // the blink: each half-period, not every frame
    else if (E.retry && !E.retried) again(1000 - (age % 1000));          // the retry countdown: each second
    var tag = E.warn ? "CAUTION" : E.notSent ? "NOT SENT" : "FAULT";
    g.font = "700 6.4px"; g.letterSpacing = "1px";
    var tw = g.measureText(tag).width + 12;
    g.letterSpacing = "0px";
    if (!blink) { g.fillStyle = col; g.fillRect(x + 8, y + 5, tw, 11); }
    else { g.strokeStyle = col; g.lineWidth = 1; g.strokeRect(x + 8.5, y + 5.5, tw - 1, 10); }
    txt(x + 8 + tw / 2, y + 10.8, tag, 6.4, blink ? col : "#000000", "center", 1);
    txt(x + 8 + tw + 8, y + 10.8, E.code, 7.6, col, "left", 1.2);
    var left = E.retry ? Math.max(0, Math.ceil((E.t + E.retry * 1000 - now()) / 1000)) : 0;
    txt(x + w - 8, y + 10.8, E.retry ? "RETRY " + left + "S" : "PRESS TO CLEAR", 5.4, rgba(HUD.w, 0.4), "right", 0.8);
    g.strokeStyle = rgba(col, 0.35); g.lineWidth = 0.8; g.beginPath(); g.moveTo(x + 6, y + 21); g.lineTo(x + w - 6, y + 21); g.stroke();
    txt(x + 10, y + 21 + (h - 21) / 3, E.cause, 7, HUD.w, "left", 0.8);
    txt(x + 10, y + 21 + 2 * (h - 21) / 3, "▸ " + E.action, 6.4, HUD.c, "left", 0.7);
    hit("err", x, y, w, h, {});
}
function hudModels(x, y, w, h) {
    var l = S.server.online ? S.engine.models : [], genres = (caps().genres || []), gtab = ui.engList === "genre" && genres.length;
    if (genres.length) {   // two tabs: the model list, and the genre list of a model that has one (prism, expressive)
        var tabs = [["MODELS", "models", x + 10], ["GENRE", "genre", x + 56]];
        for (var tb = 0; tb < 2; tb++) {
            var on = (tabs[tb][1] === "genre") === !!gtab;
            txt(tabs[tb][2], y + 11, tabs[tb][0], 5.8, on ? HUD.c : rgba(HUD.g, 0.6), "left", 0.8);
            if (on) { g.fillStyle = HUD.c; g.fillRect(tabs[tb][2], y + 15, tabs[tb][0].length * 4.6, 1); }
            hit("eng-tab", tabs[tb][2] - 4, y + 2, 44, 16, { tab: tabs[tb][1] });
        }
    } else txt(x + 10, y + 11, "MODELS", 5.8, rgba(HUD.g, 0.6), "left", 0.8);
    var rh = 17, y0 = y + 22;
    if (gtab) { hudGenres(x, y, w, h, genres, rh, y0); return; }
    txt(x + w - 10, y + 11, S.server.online ? l.length + " ON SERVER" : "NO LINK", 5.8, S.server.online ? rgba(HUD.g, 0.6) : HUD.a, "right", 0.8);
    for (var i = 0; i < Math.min(5, l.length); i++) {
        var id = l[i], yy = y0 + i * rh, sel = id === S.engine.model;
        if (sel) { g.fillStyle = rgba(HUD.c, 0.10); g.fillRect(x + 4, yy - 1, w - 8, rh - 2); }
        g.fillStyle = sel ? HUD.c : rgba(HUD.w, 0.25); g.beginPath(); g.arc(x + 12, yy + rh / 2 - 1, sel ? 2.6 : 2, 0, Math.PI * 2); g.fill();
        txt(x + 22, yy + rh / 2 - 1, id.toUpperCase().replace(/_/g, " "), 7.2, sel ? HUD.c : rgba(HUD.w, 0.8), "left", 0.8);
        hit("model-row", x, yy - 1, w, rh, { id: id });
    }
    var c = caps(), iy = y + h - 26;
    g.strokeStyle = rgba(HUD.g, 0.2); g.lineWidth = 0.8; g.beginPath(); g.moveTo(x + 6, iy - 8); g.lineTo(x + w - 6, iy - 8); g.stroke();
    txt(x + 10, iy, "CTX " + S.engine.dims.join("/") + " BARS  ·  RES " + (S.server.res || 12) + "/Q", 5.8, rgba(HUD.g, 0.7), "left", 0.6);
    var feats = [c.mask ? "SCALE" : null, c.rhythm ? "RHYTHM" : null, c.remix ? "REMIX" : null, c.vel ? "VELOCITY" : null, c.micro ? "MICROTIMING" : null].filter(function (s) { return s; });
    txt(x + 10, iy + 12, feats.join(" · "), 5.8, rgba(HUD.m, 0.85), "left", 0.6);
}
// The genre list: NONE plus the model's genres, as many rows as fit above the footer; the wheel scrolls it.
function genreRows(h) { return Math.max(1, Math.floor((h - 22 - 8) / 17)); }
function hudGenres(x, y, w, h, genres, rh, y0) {
    var items = [""].concat(genres), n = genreRows(h), cur = S.engine.genre || "";
    ui.genreScroll = Math.max(0, Math.min(ui.genreScroll || 0, items.length - n));
    var s0 = ui.genreScroll;
    txt(x + w - 10, y + 11, (cur ? cur.toUpperCase() : "NONE") + "  ·  " + (s0 + 1) + "–" + Math.min(items.length, s0 + n) + "/" + items.length,
        5.8, rgba(HUD.g, 0.6), "right", 0.8);
    for (var i = 0; i < n && s0 + i < items.length; i++) {
        var id = items[s0 + i], yy = y0 + i * rh, sel = id === cur;
        if (sel) { g.fillStyle = rgba(HUD.c, 0.10); g.fillRect(x + 4, yy - 1, w - 8, rh - 2); }
        g.fillStyle = sel ? HUD.c : rgba(HUD.w, 0.25); g.beginPath(); g.arc(x + 12, yy + rh / 2 - 1, sel ? 2.6 : 2, 0, Math.PI * 2); g.fill();
        txt(x + 22, yy + rh / 2 - 1, id ? id.toUpperCase().replace(/_/g, " ") : "NONE", 7.2, sel ? HUD.c : rgba(HUD.w, id ? 0.8 : 0.5), "left", 0.8);
        hit("genre-row", x, yy - 1, w - 12, rh, { id: id });
    }
    if (items.length > n) {   // where the view is in the list
        var th = Math.max(10, (h - 30) * n / items.length), ty = y0 + (h - 30 - th) * s0 / (items.length - n);
        g.fillStyle = rgba(HUD.g, 0.15); g.fillRect(x + w - 7, y0, 2, h - 30);
        g.fillStyle = rgba(HUD.c, 0.6); g.fillRect(x + w - 7, ty, 2, th);
    }
}
// rhythm editor: GRID = soft pull toward the unit (strength); EXACT = the onsets per bar (first one fixed at the downbeat)
function rhythmGrid() {
    var ts = S.ts.split("/"), res = S.server.res || 12, u = UNIT_INFO[S.masks.unit] || UNIT_INFO.sixteenth;
    var barTicks = Math.round(+ts[0] * (4 / +ts[1]) * res), step = Math.max(1, Math.round(res * u[0]));
    var n = Math.max(1, Math.floor(barTicks / step)), beatTicks = Math.round((4 / +ts[1]) * res);
    var pat = S.masks.pattern || [];
    if (pat.length !== n) {
        pat = []; for (var i = 0; i < n; i++) pat.push((i * step) % beatTicks === 0 ? 1 : 0);
        pat[0] = Math.max(1, pat[0]);
    }
    return { n: n, step: step, beat: beatTicks, unit: u, pat: pat };
}
function hudRhythm(x, y, w, h) {
    var on = !!S.masks.rhythm, R = rhythmGrid(), a = on ? 1 : 0.35, exact = !!S.masks.exact;
    var tabs = [["GRID", 0], ["EXACT", 1]];
    for (var t = 0; t < 2; t++) {
        var tx = x + 8 + t * 40, sel = exact === !!tabs[t][1];
        txt(tx, y + 9, tabs[t][0], 5.8, sel ? rgba(HUD.c, a) : rgba(HUD.w, 0.35 * a), "left", 0.8);
        if (sel) { g.fillStyle = rgba(HUD.c, a); g.fillRect(tx, y + 14, tabs[t][0].length * 4.8, 1); }
        if (on) hit("rhythm-tab", tx - 2, y + 2, 36, 15, { exact: tabs[t][1] });
    }
    txt(x + w - 8, y + 9, S.ts + "  ·  " + R.unit[1] + "  ·  " + R.n + (R.n === 1 ? " STEP" : " STEPS"), 5.8, rgba(HUD.g, 0.7 * a), "right", 0.6);
    var cx0 = x + 8, cw = (w - 16) / R.n, cy = y + 22, ch = h - 34;
    for (var i = 0; i < R.n; i++) {
        var bx = cx0 + i * cw, v = R.pat[i], beat = (i * R.step) % R.beat === 0;
        var lit = exact ? v > 0 : true, strength = exact ? 1 : S.masks.strength, col = exact ? HUD.m : HUD.c, gw = Math.max(1, cw - 2);
        if (lit) {
            g.fillStyle = rgba(col, (exact ? 0.9 : 0.25 + 0.6 * strength) * a);
            var vh = exact ? ch * Math.min(1, 0.45 + 0.18 * v) : ch * 0.5;
            g.fillRect(bx + 1, cy + ch - vh, gw, vh);
            if (exact && v > 1) txt(bx + cw / 2, cy + ch - vh - 4, String(v), 5.2, rgba(HUD.w, a), "center", 0);
        } else { g.strokeStyle = rgba(HUD.g, 0.25 * a); g.lineWidth = 0.8; g.strokeRect(bx + 1.5, cy + ch - 4.5, gw - 1, 4); }
        if (exact && i === 0) txt(bx + cw / 2, y + h - 2.5, "▲", 4.5, rgba(HUD.w, 0.6 * a), "center", 0);
        g.fillStyle = rgba(HUD.g, (beat ? 0.7 : 0.25) * a); g.fillRect(bx + cw / 2 - 0.4, y + h - 9, 0.8, beat ? 4 : 2);
        if (on && exact) hit("rhythm-cell", bx, cy - 4, cw, ch + 6, { i: i });
    }
}

// ------------------------------------------------------------------ SETUP screens
function hudServer(x, y, w, h) {
    g.fillStyle = S.server.online ? HUD.g : HUD.a; g.beginPath(); g.arc(x + 12, y + h / 2, 3, 0, Math.PI * 2); g.fill();
    if (!ui.editingUrl) {
        txt(x + 22, y + h / 2, S.server.url, 7.5, HUD.g, "left", 0.8);
        txt(x + w - 10, y + h / 2, "EDIT", 5.8, rgba(HUD.c, 0.8), "right", 0.8);
    } else txt(x + w - 10, y + h / 2, "ENTER ↵", 5.8, rgba(HUD.c, 0.8), "right", 0.8);
    hit("url", x, y, w, h, {});
}
function hudTracks(x, y, w, h) {
    var rows = 7, rh = (h - 8) / rows, r0 = Math.max(0, Math.min(ui.setup.scroll || 0, S.tracks.length - rows));
    ui.setup.scroll = r0;
    var Z = ui.setup.wiz;
    for (var j = 0; j < Math.min(rows, S.tracks.length - r0); j++) {
        var i = r0 + j, t = S.tracks[i], yy = y + 4 + j * rh, sel = i === ui.setup.sel, picked = !!ui.setup.picked[i];
        var ask = !!(Z && Z.step === "confirm" && Z.queue[Z.pos] === i);
        if (sel || picked) { g.fillStyle = rgba(ask ? HUD.a : HUD.c, sel ? 0.14 : 0.06); g.fillRect(x + 4, yy, w - 8, rh - 2); }
        if (picked) { g.fillStyle = HUD.c; g.fillRect(x + 4, yy, 2, rh - 2); }
        txt(x + 12, yy + rh / 2 - 1, t.short, 7.5, ask ? HUD.a : sel ? HUD.c : HUD.w, "left", 1);
        var srcCol = t.src === "TAG" ? HUD.g : t.src === "DEFAULT" ? HUD.a : HUD.c;
        txt(x + 64, yy + rh / 2 - 1, t.src === "TAG" ? "◆ TAG" : t.src, 5.6, rgba(srcCol, 0.85), "left", 0.6);
        var shown = ask && Z.pick != null ? Z.pick : t.inst;
        txt(x + w - 26, yy + rh / 2 - 1, instName(shown), 6.2, ask && Z.pick != null ? HUD.c : t.src === "DEFAULT" ? rgba(HUD.a, 0.9) : HUD.g, "right", 0.6);
        hit("setup-row", x, yy, w - 22, rh, { i: i });
    }
    if (S.tracks.length > rows) {
        var th = (h - 8) * rows / S.tracks.length, ty = y + 4 + (h - 8 - th) * r0 / (S.tracks.length - rows);
        g.fillStyle = rgba(HUD.g, 0.15); g.fillRect(x + w - 4, y + 4, 2, h - 8); g.fillStyle = rgba(HUD.g, 0.8); g.fillRect(x + w - 4, ty, 2, th);
        hit("setup-scroll", x + w - 10, y + 4, 10, h - 8, { y0: y + 4, h: h - 8, th: th, rows: rows });
    }
    if (S.tagging) txt(x + w - 8, y + h + 9, "ADDING TAGS · " + S.tagging + " LEFT", 5.6, HUD.a, "right", 0.8);
}
function hudChoice(x, y, label, opts, val, key) {
    txt(x, y, label, 5.6, rgba(HUD.g, 0.7), "left", 0.7);
    var cx = x + 92;
    for (var i = 0; i < opts.length; i++) {
        var o = opts[i], on = val === i, wdt = o.length * 4.7 + 12;
        if (on) { g.fillStyle = rgba(HUD.c, 0.18); g.fillRect(cx - 4, y - 6, wdt, 12); }
        txt(cx + 2, y, o, 5.8, on ? HUD.c : rgba(HUD.w, 0.55), "left", 0.6);
        hit("wiz-opt", cx - 4, y - 7, wdt, 14, { key: key, v: i });
        cx += wdt + 6;
    }
}
function hudButton(x, y, label, kind, col) {
    var wdt = label.length * 5 + 14;
    g.strokeStyle = rgba(col || HUD.c, 0.8); g.lineWidth = 0.8; g.strokeRect(x + 0.5, y - 6.5, wdt, 13);
    txt(x + wdt / 2 + 0.5, y, label, 5.8, col || HUD.c, "center", 0.8);
    hit(kind, x, y - 7, wdt + 1, 14, {});
    return wdt;
}
function hudBrowser(x, y, w, h) {
    var Z = ui.setup.wiz, bx;
    if (Z && Z.step === "options") {
        txt(x + 10, y + 11, "SET UP " + Z.indices.length + (Z.scope === "sel" ? " SELECTED" : "") + " TRACK" + (Z.indices.length === 1 ? "" : "S"), 6, HUD.a, "left", 0.8);
        hudChoice(x + 10, y + 38, "DETECTION", ["AUTO", "CONFIRM EACH"], Z.confirm, "confirm");
        txt(x + 10, y + 112, Z.confirm ? "tag each track; confirm every instrument" : "tag each track; confirm only the ones with no guess", 5.6, rgba(HUD.w, 0.45), "left", 0.5);
        bx = x + w - 10; bx -= 50; hudButton(bx, y + h - 14, "CANCEL", "wiz-cancel", HUD.w); bx -= 40; hudButton(bx, y + h - 14, "RUN", "wiz-run", HUD.a);
        return;
    }
    var t = setupTrack();
    if (!t) { txt(x + w / 2, y + h / 2, "NO MIDI TRACKS", 7, rgba(HUD.w, 0.5), "center", 1); return; }
    var ask = !!(Z && Z.step === "confirm");
    var pick = ask && Z.pick != null ? Z.pick : null;
    var guess = pick != null ? pick : t.inst, gFam = guess === 128 ? 16 : Math.floor(guess / 8), gProg = guess === 128 ? 0 : guess % 8;
    var fam = ui.setup.browseFam != null ? ui.setup.browseFam : gFam;
    txt(x + 10, y + 11, ask ? "CONFIRM " + (Z.pos + 1) + "/" + Z.queue.length + "  \u00b7  " + t.short + "  \u00b7  " +
                              (pick != null ? "PICKED " + instName(pick) : "GUESS " + instName(t.inst) + " (" + t.src + ")")
                            : "INSTRUMENT  ·  " + t.short + "  ·  " + (t.src === "TAG" ? "TAGGED" : "NOT TAGGED, " + t.src), 5.8, ask ? HUD.a : rgba(HUD.g, 0.7), "left", 0.6);
    var gx = x + 8, gy = y + 22, cw = 44, ch = 15.5, i;
    for (i = 0; i < FAM_SHORT.length; i++) {
        var cx = gx + (i % 3) * cw, cy = gy + Math.floor(i / 3) * ch, on = i === fam;
        if (on) { g.fillStyle = rgba(HUD.c, 0.16); g.fillRect(cx, cy, cw - 3, ch - 3); }
        txt(cx + (cw - 3) / 2, cy + (ch - 3) / 2 + 0.5, FAM_SHORT[i], 5.6, on ? HUD.c : i === gFam ? HUD.g : rgba(HUD.w, 0.6), "center", 0.4);
        hit("browse-fam", cx, cy, cw - 3, ch - 3, { f: i });
    }
    var px = x + 8 + 3 * cw + 6, pw = x + w - 8 - px, progs = programs(fam), rh = Math.min(14.5, (h - 44) / progs.length);
    g.fillStyle = rgba(HUD.g, 0.2); g.fillRect(px - 4, gy, 1, h - 44);
    for (i = 0; i < progs.length; i++) {
        var yy = gy + i * rh, curP = fam === gFam && i === gProg;
        if (curP) { g.fillStyle = rgba(HUD.c, 0.16); g.fillRect(px, yy, pw, rh - 2); }
        txt(px + 6, yy + (rh - 2) / 2 + 0.5, (fam === 16 ? "" : (fam * 8 + i + 1) + "  ") + progs[i], 6, curP ? HUD.c : rgba(HUD.w, 0.8), "left", 0.5);
        hit("browse-prog", px, yy, pw, rh - 2, { f: fam, p: i });
    }
    if (ask) { bx = x + w - 10; bx -= 40; hudButton(bx, y + h - 13, "SKIP", "wiz-skip", HUD.w); bx -= 66; hudButton(bx, y + h - 13, "CONFIRM", "wiz-guess", HUD.a); }
}
function startSetup(scope, indices) {
    if (!indices.length) return;
    ui.setup.wiz = { scope: scope, indices: indices, confirm: 0, step: "options", choice: {}, done: {}, pick: null };
}
function runWizard() {
    var Z = ui.setup.wiz;
    Z.queue = Z.indices.filter(function (i) { return Z.confirm || S.tracks[i].src === "DEFAULT"; });
    if (!Z.queue.length) return applySetup();
    Z.step = "confirm"; Z.pos = 0; ui.setup.sel = Z.queue[0]; ui.setup.browseFam = null; ui.setup.scroll = Math.max(0, ui.setup.sel - 3);
}
function wizNext(choice) {
    var Z = ui.setup.wiz, ti = Z.queue[Z.pos], t = S.tracks[ti];
    Z.choice[ti] = choice; Z.pick = null;
    if (choice !== null && t) { t.inst = choice; t.src = "TAG"; send("setup_apply", t.i, choice); Z.done[ti] = 1; }
    if (++Z.pos >= Z.queue.length) return applySetup();
    ui.setup.sel = Z.queue[Z.pos]; ui.setup.browseFam = null; ui.setup.scroll = Math.max(0, ui.setup.sel - 3);
}
function applySetup() {
    var Z = ui.setup.wiz, args = ["setup_apply"];
    for (var k = 0; k < Z.indices.length; k++) {
        var i = Z.indices[k], t = S.tracks[i], c = (i in Z.choice) ? Z.choice[i] : t.inst;
        if (c === null || Z.done[i]) continue;
        args.push(t.i, c);
    }
    if (args.length > 1) send.apply(null, args);
    ui.setup.wiz = null; ui.setup.picked = {};
}

// ------------------------------------------------------------------ TRACK bay layout (only the knobs this track uses)
function trackLayout() {
    var drums = curKind() === "drums";
    var row1 = drums ? ["DENSITY"] : ["POLY", "LENGTH"];
    var bay = SP.pages.main.bays[0], bx = bay[0], bw = bay[2], top = bay[1] + 24, bottom = bay[1] + bay[3] - 6;
    var big = [34, 58], hgt = big[0] + big[1];
    var c1 = Math.round(top + (bottom - top - hgt) / 2) + big[0], out = [];
    // the model's extra controls (prism / expressive) in a second row, at the spec's places
    var row2 = [], spec = {};
    for (var n = 0; n < SP.pages.main.knobs.length; n++) spec[SP.pages.main.knobs[n][0]] = SP.pages.main.knobs[n];
    var extra = ["KEY", "RANGE", "SILENCE", "PCS", "EXPRESSIVENESS"];
    for (n = 0; n < extra.length; n++) if (KNOBS[extra[n]].show()) row2.push(extra[n]);
    if (row2.length) c1 = spec.POLY[2];
    for (var i = 0; i < row1.length; i++) out.push([row1[i], Math.round(bx + bw * (i + 0.5) / row1.length), c1, 26]);
    for (i = 0; i < row2.length; i++) out.push([row2[i], Math.round(bx + bw * (i + 0.5) / row2.length), spec.KEY[2], spec.KEY[3]]);
    return out;
}
var TRACK_KNOBS = { "POLY": 1, "LENGTH": 1, "TRACK TEMP": 1, "DENSITY": 1, "KEY": 1, "RANGE": 1, "SILENCE": 1, "PCS": 1, "EXPRESSIVENESS": 1 };
function specPage() { return ui.page === "engine" && (caps().vel || caps().micro) ? "engine_vm" : ui.page; }

// ------------------------------------------------------------------ paint
var paintMs = [];
var readySent = false, shownBg = null;
function paint() {
    if (!g) g = CV.wrap(mgraphics);
    var t0 = now();
    // The first paint means the window is open: only then does midigpt.js start building and pushing the panel's
    // state (it used to from device load, for a window that may never open). One region says it.
    if (!readySent && REGION === "top") { readySent = true; send("ready"); }
    // the page's background picture (one fpic in the patch, switched by name; ENGINE has two layouts)
    if (REGION === "main") { var bgp = specPage(); if (bgp !== shownBg) { shownBg = bgp; outlet(0, "bg", bgp); } }
    hits = [];
    g.save();
    g.translate(-RX[0], -RX[1]);
    var sp = specPage();
    if (REGION === "all") drawImg("bg_" + sp + ".png", 0, 0);
    if (inRegion("top")) paintTop();
    if (inRegion("roll")) { var s = SP.screen; hudRoll(s[0], s[1], s[2], s[3]); }
    if (inRegion("main")) paintMain(sp);
    if (inRegion("output")) paintOutput();
    if (inRegion("masks")) paintMasks();
    g.restore();
    paintMs.push(now() - t0);
    if (paintMs.length >= 20) { send("perf", REGION, Math.round(paintMs.reduce(function (a, b) { return a + b; }, 0) / paintMs.length), Math.max.apply(null, paintMs)); paintMs = []; }
}
function paintTop() {
    for (var i = 0; i < SP.top_keys.length; i++) {
        (function (k) {
            var p = k[0].toLowerCase();
            drawKey(k[1], k[2], k[3], k[4], k[0], ui.page === p, function () { outlet(0, "page", ui.page === p ? "main" : p); urlEdit(false); }, { size: 7.4 });
        })(SP.top_keys[i]);
    }
}
function paintMain(sp) {
    var i, page = SP.pages[sp], c = cur();
    for (i = 0; i < page.bays.length; i++) {
        var b = page.bays[i], sub = null, subCol = null;
        // the knobs edit the track selected in Live, which need not be one being generated: say which, loudly
        if (b[4] === "TRACK") {
            sub = c ? "EDITING " + c.short + " · " + (curKind() === "drums" ? "DRUMS" : "MELODIC") : "NO TRACK";
            if (c && !isTarget(c)) { sub = "EDITING " + c.short + " · NOT GENERATED"; subCol = ACC; }
        }
        if (b[4] === "SAMPLE") sub = "ALL TARGETS";
        bayTitle(b[0], b[1], b[2], b[4], sub, subCol);
    }
    var tk = ui.page === "main" ? trackLayout() : null;
    for (i = 0; i < page.knobs.length; i++) { var k = page.knobs[i]; if (k[0] === "SEED") { drawSeed(k[1], k[2]); continue; } if (!(tk && TRACK_KNOBS[k[0]])) drawKnob(KNOBS[k[0]], k[0], k[1], k[2], k[3]); }
    if (tk && c) for (i = 0; i < tk.length; i++) drawKnob(KNOBS[tk[i][0]], tk[i][0], tk[i][1], tk[i][2], tk[i][3]);
    for (i = 0; i < page.toggles.length; i++) { var tg = page.toggles[i]; if (TOGGLES[tg[0]]) drawToggle(TOGGLES[tg[0]], tg[0], tg[1], tg[2], tg[3], tg[4]); }
    for (i = 0; i < page.keys.length; i++) setupKey(page.keys[i]);
    var HS = { models: hudModels, server: hudServer, tracks: hudTracks, browser: hudBrowser };
    for (i = 0; i < page.screens.length; i++) { var sc = page.screens[i]; HS[sc[0]](sc[1], sc[2], sc[3], sc[4]); }
}
function paintOutput() {
    var i, O = SP.output, G = S.gen, nTk = G.takes.length;
    bayTitle(O.bay[0], O.bay[1], O.bay[2], "OUTPUT", nTk ? (G.cur < 0 ? "ORIGINAL" : "TAKE " + (G.cur + 1) + "/" + nTk) : null);
    var nT = nTk || S.sample.takes, nP = Math.max(1, Math.ceil(nT / 4)), pg = Math.min(ui.takePage, nP - 1);
    for (i = 0; i < O.pages.length; i++) {
        (function (k, pi) {
            if (pi >= nP) { drawKey(k[0], k[1], k[2], k[3], "", false, null, { dim: true, off: true }); return; }
            drawKey(k[0], k[1], k[2], k[3], "", pi === pg, function () { ui.takePage = pi; });
        })(O.pages[i], i);
    }
    for (i = 0; i < O.takes.length; i++) {
        (function (k, i) {
            if (i === 0) {
                drawKey(k[0], k[1], k[2], k[3], "<ret>", !!(nTk && G.cur < 0), function () { send("take", -1); }, { dim: !(nTk && G.orig), size: 12, spacing: 0 });
                return;
            }
            var ti = pg * 4 + i - 1;
            if (ti >= nT) { drawKey(k[0], k[1], k[2], k[3], String(ti + 1), false, null, { dim: true, off: true, size: 12, spacing: 0 }); return; }
            var have = ti < nTk && G.takes[ti], lit = have && G.cur === ti;
            drawKey(k[0], k[1], k[2], k[3], String(ti + 1), !!lit, function () { send("take", ti); }, { dim: !have, size: 12, spacing: 0 });
        })(O.takes[i], i);
    }
    hudStats(O.stats[0], O.stats[1], O.stats[2], O.stats[3]);
    drawKey(O.keep[0], O.keep[1], O.keep[2], O.keep[3], "KEEP", false, function () { send("keep"); }, { dim: !(nTk && G.cur >= 0), size: 8 });
    var busy = G.status === "streaming" || G.status === "cancelling";
    var faultLed = errSeen ? (errSeen.warn ? HUD.a : HUD.m).replace(/rgb\(|\)/g, "") : null;
    drawKey(O.generate[0], O.generate[1], O.generate[2], O.generate[3], busy ? "CANCEL" : "GENERATE", busy, busy ? function () { send("cancel"); } : generate,
            { size: 11, spacing: 2.4, led: busy ? null : faultLed });
}
function paintMasks() {
    var i, E = SP.extras, c = cur();
    bayTitle(E.bay[0], E.bay[1], E.bay[2], "MASKS", "PITCH · RHYTHM · REMIX · " + (c ? c.short + (isTarget(c) ? "" : " · NOT GENERATED") : "—"),
             c && !isTarget(c) ? ACC : null);
    for (i = 0; i < E.toggles.length; i++) { var et = E.toggles[i]; drawToggle(TOGGLES[et[0]], et[0], et[1], et[2], et[3], et[4]); }
    for (i = 0; i < E.knobs.length; i++) { var ek = E.knobs[i]; drawKnob(KNOBS[ek[0]], ek[0], ek[1], ek[2], ek[3]); }
    hudRhythm(E.rhythm[0], E.rhythm[1], E.rhythm[2], E.rhythm[3]);
}
function setupKey(k) {
    var lab = k[0], lit = false, fn = null;
    if (lab === "CONNECT") fn = function () { flash("CONNECT"); send("connect"); };
    else if (lab === "SETUP ALL") { lit = !!(ui.setup.wiz && ui.setup.wiz.scope === "all"); fn = function () { startSetup("all", S.tracks.map(function (_, i) { return i; })); }; }
    else if (lab === "SETUP SEL") {
        var selIdx = Object.keys(ui.setup.picked).map(Number);
        if (!selIdx.length) selIdx = [ui.setup.sel];
        lit = !!(ui.setup.wiz && ui.setup.wiz.scope === "sel");
        fn = function () { startSetup("sel", selIdx); };
    } else if (lab === "RESET") {
        lit = !!ui.setup.resetArm;
        fn = function () {
            if (ui.setup.resetArm) { send("reset"); ui.setup.resetArm = 0; }
            else { ui.setup.resetArm = 1; later(2500, function () { ui.setup.resetArm = 0; }); }
        };
        if (lit) lab = "SURE?";
    }
    if (ui.flash === k[0]) lit = true;
    drawKey(k[1], k[2], k[3], k[4], lab, lit, fn, { size: 7.2 });
}
function flash(name) { ui.flash = name; later(300, function () { ui.flash = null; }); }
// one Task per purpose, reused (a new Task per call was never freed)
var LATER = {};
function later(ms, fn, key) {
    key = key || String(fn);
    var t = LATER[key];
    if (!t) t = LATER[key] = new Task(function () { t.fn(); redraw(); }, this);
    t.fn = fn;
    t.cancel();
    t.schedule(ms);
}

// ------------------------------------------------------------------ generate (checked here first, so the server never 422s)
function preflight() {
    var out = [], E = S.engine, X = S.masks;
    var ctx = E.context_auto ? E.dims[0] : E.context;
    if (!E.bps_auto && E.bps > ctx) out.push(["BARS/STEP " + E.bps + " > CONTEXT " + ctx, "LOWER BARS/STEP"]);
    var c = cur();
    if (c && isTarget(c)) {
        if (X.remix && X.rhythm) out.push([c.short + ": REMIX + RHYTHM", "TURN ONE OFF"]);
        if ((X.remix || (X.rhythm && X.exact)) && !E.tps_auto && E.tps > 1) out.push([c.short + ": " + (X.remix ? "REMIX" : "EXACT RHYTHM") + " NEEDS TRK/STEP 1", "SET TRK/STEP TO 1"]);
    }
    if (S.sample.topk && E.maskk && E.maskk >= S.sample.topk) out.push(["MASK K ≥ TOP-K", "LOWER MASK K"]);
    if (E.maskp && E.maskp >= S.sample.topp) out.push(["MASK P ≥ TOP-P", "LOWER MASK P"]);
    return out;
}
function localFault(code, cause, action) { errSeen = { id: "local" + now(), code: code, cause: cause, action: action, warn: 0, notSent: 1, t: now() }; }
function generate() {
    errSeen = null;
    if (!S.server.online) { errSeen = { id: "local" + now(), code: "NO LINK", cause: "SERVER UNREACHABLE", action: "CHECK ADDRESS IN SETUP", t: now() }; return; }
    var any = false;
    for (var i = 0; i < S.tracks.length; i++) if (isTarget(S.tracks[i])) any = true;
    if (!any) return localFault("NO TARGET", "NO BARS CHOSEN", "PAINT BARS OR USE AR");
    var pf = preflight();
    if (pf.length) return localFault(pf.length > 1 ? "SETTINGS ×" + pf.length : "SETTING", pf[0][0], pf[0][1]);
    send("generate");
}

// ------------------------------------------------------------------ input
var drag = null, paintMode = null, lastClick = { t: 0, x: 0, y: 0 };
function onclick(x, y, button, cmd, shift, caps_, opt) {
    x += RX[0]; y += RX[1];
    var tm = now();
    var dbl = tm - lastClick.t < 320 && Math.abs(x - lastClick.x) < 4 && Math.abs(y - lastClick.y) < 4;
    lastClick = { t: tm, x: x, y: y };
    var h = find(x, y);
    drag = null;
    if (!h || h.kind !== "url") urlEdit(false, true);   // a click anywhere else closes the address field
    if (!h) return;
    var t, d;
    if (h.kind === "knob") {
        d = h.d;
        if (dbl && !d.dim) {   // double-click: AUTO on/off, or back to the default
            if (d.def.setAuto) d.def.setAuto(!d.def.isAuto());
            else if (d.def.def != null && d.def.raw) { d.def.raw(d.def.def); d.def.emit(); }
            redraw(); return;
        }
        if (d.dim) return;
        var v = d.def.v(), end = 0;
        if (d.def.range) {
            var ang = Math.atan2(x - d.cx, -(y - d.cy)) * 180 / Math.PI, vAt = (ang + 135) / 270;
            end = Math.abs(vAt - v[0]) < Math.abs(vAt - v[1]) ? 0 : 1;
            if (v[0] === v[1]) end = vAt > v[0] ? 1 : 0;
        }
        drag = { knob: d, y: y, v: v, end: end, all: !!opt, moved: false };
    }
    else if (h.kind === "toggle") { h.d.def.set(h.d.def.get() ? 0 : 1); }
    else if (h.kind === "key") { ui.press = { x: h.d.x, y: h.d.y }; drag = { key: h }; }
    else if (h.kind === "roll-name") { send("select_track", h.d.t.i); }
    else if (h.kind === "roll-ig") { t = h.d.t; t.ig = t.ig ? 0 : 1; if (t.ig) t.ar = 0; send("ignore", t.i, t.ig); }
    else if (h.kind === "roll-ar") { t = h.d.t; t.ar = t.ar ? 0 : 1; if (t.ar) t.ig = 0; send("ar", t.i, t.ar); }
    else if (h.kind === "roll-bar") {
        t = h.d.t;
        if (t.ig) { t.ig = 0; send("ignore", t.i, 0); }
        // AR: a click sets where generation starts (clicking the start again goes back to bar 1)
        if (t.ar) { t.as = t.as === h.d.b ? 0 : h.d.b; send("ar_start", t.i, t.as); redraw(); lastKey = regionKey(); return; }
        paintMode = t.paint.charAt(h.d.b) === "1" ? 0 : 1;
        setPaint(t, h.d.b, paintMode);
        drag = { paint: true };
    }
    else if (h.kind === "vscroll") { drag = { vs: h.d }; scrollTo(h.d, y); }
    else if (h.kind === "hscroll") { drag = { hs: h.d }; scrollTo(h.d, x); }
    else if (h.kind === "setup-scroll") { drag = { ss: h.d }; scrollTo(h.d, y); }
    else if (h.kind === "err") { errSeen = null; send("clear_fault"); }
    else if (h.kind === "model-row") { S.engine.model = h.d.id; send("engine", "model", h.d.id); }
    else if (h.kind === "eng-tab") { ui.engList = h.d.tab; }
    else if (h.kind === "genre-row") { S.engine.genre = h.d.id; send("engine", "genre", h.d.id || "none"); }
    else if (h.kind === "rhythm-tab") { S.masks.exact = h.d.exact; send("mask", "exact", h.d.exact); }
    else if (h.kind === "rhythm-cell") {
        var R = rhythmGrid(), pv = R.pat[h.d.i];
        if (shift) R.pat[h.d.i] = pv >= 4 ? 1 : pv + 1;
        else if (h.d.i > 0) R.pat[h.d.i] = pv ? 0 : 1;
        S.masks.pattern = R.pat;
        send.apply(null, ["mask", "pattern"].concat(R.pat));
    }
    else if (h.kind === "browse-fam") { ui.setup.browseFam = h.d.f; }
    else if (h.kind === "browse-prog") {
        var pick = h.d.f === 16 ? 128 : h.d.f * 8 + h.d.p;
        if (ui.setup.wiz && ui.setup.wiz.step === "confirm") { ui.setup.wiz.pick = pick; ui.setup.browseFam = null; }
        else { var tb = setupTrack(); if (tb) { tb.inst = pick; tb.src = "TAG"; send("set_instrument", tb.i, pick); } ui.setup.browseFam = null; }
    }
    else if (h.kind === "wiz-opt") { ui.setup.wiz[h.d.key] = h.d.v; }
    else if (h.kind === "wiz-run") { runWizard(); }
    else if (h.kind === "wiz-cancel") { ui.setup.wiz = null; }
    else if (h.kind === "wiz-guess") { var Zg = ui.setup.wiz; wizNext(Zg.pick != null ? Zg.pick : setupTrack().inst); }
    else if (h.kind === "wiz-skip") { wizNext(null); }
    else if (h.kind === "setup-row" && shift) { if (ui.setup.picked[h.d.i]) delete ui.setup.picked[h.d.i]; else ui.setup.picked[h.d.i] = 1; }
    else if (h.kind === "setup-row") { ui.setup.sel = h.d.i; ui.setup.browseFam = null; ui.setup.picked = {}; }
    else if (h.kind === "url") { urlEdit(true); }
    redraw();
    lastKey = regionKey();    // drawn as it is now: the core's echo of this change is not a second repaint
}
onclick.local = 1;
function setPaint(t, b, v) {
    var p = t.paint.split("");
    while (p.length <= b) p.push("0");
    if (p[b] === String(v)) return false;
    p[b] = String(v); t.paint = p.join("");
    send("bar", t.i, b, v);
    return true;
}
function scrollTo(d, pos) {
    var before = ui.scroll.row + "," + ui.scroll.bar + "," + ui.setup.scroll;
    scrollTo_(d, pos);
    return before !== ui.scroll.row + "," + ui.scroll.bar + "," + ui.setup.scroll;
}
function scrollTo_(d, pos) {
    if (d.y0 !== undefined && d.rows === undefined) {
        var f = (pos - d.y0 - d.th / 2) / Math.max(1, d.h - d.th);
        ui.scroll.row = Math.round(clamp01(f) * Math.max(0, S.tracks.length - VIEW.rows));
    } else if (d.x0 !== undefined) {
        var fx = (pos - d.x0 - d.tw / 2) / Math.max(1, d.w - d.tw);
        ui.scroll.bar = Math.round(clamp01(fx) * Math.max(0, S.bars - VIEW.bars));
    } else {
        var fs = (pos - d.y0 - d.th / 2) / Math.max(1, d.h - d.th);
        ui.setup.scroll = Math.round(clamp01(fs) * Math.max(0, S.tracks.length - d.rows));
    }
}
function ondrag(x, y, button, cmd, shift, caps_, opt) {
    if (!drag) return;
    x += RX[0]; y += RX[1];
    if (button === 0) {   // released
        if (drag.key) { var h = find(x, y, "key"); if (h && h.d.x === drag.key.d.x && h.d.y === drag.key.d.y) drag.key.d.fn(); }
        if (drag.knob && drag.moved) drag.knob.def.emit();
        drag = null; ui.press = null; paintMode = null; redraw(); return;
    }
    if (drag.knob) {
        var dv = (drag.y - y) / (shift ? 700 : 170), def = drag.knob.def;
        if (def.isAuto && def.isAuto()) { if (Math.abs(drag.y - y) < 3) return; def.setAuto(0); drag.v = def.v(); drag.y = y; }
        if (def.range) {
            if (drag.all) { var span = drag.v[1] - drag.v[0], lo = Math.max(0, Math.min(1 - span, drag.v[0] + dv)); def.set(lo, 0); def.set(lo + span, 1); }
            else def.set(drag.v[drag.end] + dv, drag.end);
        } else def.set(drag.v + dv);
        drag.moved = true;
        emitThrottled(def);
    } else if (drag.paint) {
        var hb = find(x, y, "roll-bar");
        if (!hb || !setPaint(hb.d.t, hb.d.b, paintMode)) return;      // nothing changed: no repaint
    } else if (drag.vs) { if (!scrollTo(drag.vs, y)) return; }
    else if (drag.hs) { if (!scrollTo(drag.hs, x)) return; }
    else if (drag.ss) { if (!scrollTo(drag.ss, y)) return; }
    redraw();
    lastKey = regionKey();
}
ondrag.local = 1;
// a knob drag sends at most every 60 ms, and once more on release
var lastEmit = 0;
function emitThrottled(def) { var t = now(); if (t - lastEmit > 60) { lastEmit = t; def.emit(); } }
function onidle(x, y) {}
onidle.local = 1;
// Scroll wheel and trackpad: vertical moves the roll's tracks (or the SETUP list), horizontal or Shift+wheel
// its bars. A trackpad sends many small steps, a wheel one per notch: they add up to whole rows / bars.
var wheelAcc = { x: 0, y: 0 };
function onwheel(x, y, wx, wy, button, cmd, shift) {
    x += RX[0]; y += RX[1];
    if (shift && !wx) { wx = wy; wy = 0; }
    var before = ui.scroll.row + "," + ui.scroll.bar + "," + ui.setup.scroll + "," + ui.genreScroll;
    wheelAcc.x += wx; wheelAcc.y += wy;
    var whole = function (v) { return v < 0 ? Math.ceil(v) : Math.floor(v); };
    var dx = whole(wheelAcc.x), dy = whole(wheelAcc.y);
    wheelAcc.x -= dx; wheelAcc.y -= dy;
    if (find(x, y, "roll-area")) {
        ui.scroll.row -= dy; ui.scroll.bar -= dx; clampScroll();
    } else if (find(x, y, "setup-row") || find(x, y, "setup-scroll")) {
        ui.setup.scroll = Math.max(0, Math.min((ui.setup.scroll || 0) - dy, S.tracks.length - 7));   // 7 rows: hudSetup
    } else if (find(x, y, "genre-row")) {
        ui.genreScroll = Math.max(0, (ui.genreScroll || 0) - dy);   // hudGenres clamps the end
    } else { wheelAcc.x = wheelAcc.y = 0; return; }
    if (before === ui.scroll.row + "," + ui.scroll.bar + "," + ui.setup.scroll + "," + ui.genreScroll) return;
    redraw();
    lastKey = regionKey();
}
onwheel.local = 1;

// ------------------------------------------------------------------ server address (a native textedit over the screen)
function urlEdit(on, always) {
    if (ui.editingUrl === !!on && !always) return;
    ui.editingUrl = !!on;
    if (on) outlet(0, "url_text", S.server.url);
    outlet(0, "url_edit", on ? 1 : 0);
}
function url_done() { ui.editingUrl = false; redraw(); }

// ------------------------------------------------------------------ redraw pump (animations, running generation, fault blink)
// redraw() paints now. again(ms) asks for one more paint after ms (an animation frame, a blink, a countdown); the pump
// runs only while something is pending and stops when idle. While a generation streams, the roll (its painted-bar
// shimmer) and the output (TIME) repaint at 8 fps; every new state repaints as well.
var STREAM_MS = 125;
var nextPaint = 0, pumping = false;
function redraw() { mgraphics.redraw(); }
function again(ms) {
    var at = now() + Math.max(0, ms || 0);
    if (!nextPaint || at < nextPaint) nextPaint = at;
    if (!pumping) { pumping = true; pump.repeat(); }
}
function streamingHere() { return S.gen.status === "streaming" && (REGION === "roll" || REGION === "output" || REGION === "all"); }
var pump = new Task(function () {
    var t = now();
    retryCheck();
    if (streamingHere() && !nextPaint) nextPaint = t + STREAM_MS;
    if (nextPaint && t >= nextPaint) { nextPaint = 0; mgraphics.redraw(); if (streamingHere()) nextPaint = t + STREAM_MS; }
    if (!nextPaint && !streamingHere() && !(errSeen && errSeen.retry && !errSeen.retried)) { pumping = false; pump.cancel(); }
}, this);
pump.interval = 40;
// a 503's automatic retry (the fault screen counts it down): sent from the pump, not from inside paint()
function retryCheck() {
    var E = errSeen;
    if (E && E.retry && !E.retried && now() >= E.t + E.retry * 1000) { E.retried = true; errSeen = null; send("generate"); redraw(); }
}
function onresize() { mgraphics.redraw(); }
onresize.local = 1;
function notifydeleted() { pump.cancel(); }
function bang() { redraw(); }
