// midigpt.js side of the panel (javascript/midigpt_panel.js). include()d by midigpt.js,
// so it shares midigpt.js's globals.
//
// Out (outlet 0):  panel_state <json>   everything the panel draws except notes
//                  panel_notes <json>   note previews per track and bar
// In:              panel <verb> <args...>   (panel_message)
//
// The panel shows every MIDI track of the selected scene. Any track can be a
// generation target: AR on, or bars painted. Tracks without a clip in the
// scene get one when they are generated.

var panel_ready = false;         // the panel said "ready": state pushes start
var panel_task = null;
var panel_last = { state: "", notes: null };   // notes: the scene cache whose notes were sent last
var panel_scene_cache = null;
var panel_fault_state = null;    // {id, code, cause, action, warn, notSent, retry}
var panel_fault_seq = 0;
var panel_fault_fresh = false;   // a structured fault was just set: report_error() should not overwrite it
var panel_gen = { t0: 0, elapsed: 0, notes: 0, seed: 0, att: 0, tps: 0, ctx: 0, maxctx: 0 };

function schedule_panel(){
    if (!panel_ready || panel_task) return;
    panel_task = new Task(function(){ panel_task = null; push_panel(); }, this);
    panel_task.schedule(15);
}

function panel_invalidate_scene(){ panel_scene_cache = null; panel_rows = {}; track_inst_cache = {}; schedule_panel(); }

// A tag device was added, changed or removed (it sends "tag_changed" through [s midigpt_tag_changed]). Live has not
// always finished adding / removing the device yet, so re-read the tracks a moment later.
var tag_change_task = null;
function panel_tag_changed(){
    if (tag_change_task) tag_change_task.cancel();
    tag_change_task = new Task(function(){ tag_change_task = null; panel_invalidate_scene(); }, this);
    tag_change_task.schedule(250);
}

// ------------------------------------------------------------------ the scene: tracks, clips, notes
function short_name(name){
    var s = String(name || "").toUpperCase().replace(/^\d+[-\s]+/, "").replace(/\s+/g, " ").trim();
    return s.length > 7 ? s.slice(0, 7) : (s || "TRK");
}

// One row per MIDI track of the selected scene, cached by track id: a click in Live refreshes one row, not the scene
// (panel_invalidate_tracks), and a scene or track-list change empties the lot (invalidate_scene_cache). The row keeps
// what build_request() needs to find the clip again (slot, clip id, meter), so GENERATE doesn't walk the set twice.
var panel_rows = {}, panel_rows_scene = -2;
var track_inst_cache = {};      // track id -> detect_track_instrument() result (tags change rarely; walking devices is slow)

function cached_instrument(track_id){
    var d = track_inst_cache[track_id];
    if (!d) d = track_inst_cache[track_id] = detect_track_instrument(track_id);
    return d;
}

function panel_row(i){
    var tid = track_ids[i], row = panel_rows[tid];
    if (row) { row.i = i; return row; }
    row = { i: i, tid: tid, name: "", short: "", hc: 0, nb: 0, inst: 0, src: "DEFAULT", slot: 0, clip: 0, num: 0, den: 0, notes: [] };
    try {
        var track = new LiveAPI();
        track.id = tid;
        row.name = (track.get("name") || [""]).join(" ");
        row.short = short_name(row.name);
        row.slot = +strip_ids(track.get("clip_slots"))[current_scene] || 0;
        if (row.slot) {
            var slot = new LiveAPI();
            slot.id = row.slot;
            if (+slot.get("has_clip")) {
                var clip = new LiveAPI();
                clip.id = row.clip = +slot.get("clip")[1];
                var num = row.num = +clip.get("signature_numerator")[0], den = row.den = +clip.get("signature_denominator")[0];
                var barLen = num / den * 4;
                var looping = !!(+clip.get("looping"));
                var start = looping ? +clip.get("loop_start")[0] : +clip.get("start_marker")[0];
                var end = looping ? +clip.get("loop_end")[0] : +clip.get("end_marker")[0];
                row.hc = 1;
                row.nb = Math.max(1, Math.ceil((end - start) / barLen - 1e-6));
                var live = JSON.parse(clip.call("get_notes_extended", 0, 128, start, end - start));
                var lo = 127, hi = 0, k;
                for (k = 0; k < live.notes.length; k++) { lo = Math.min(lo, live.notes[k].pitch); hi = Math.max(hi, live.notes[k].pitch); }
                lo -= 2; hi += 2;
                for (var b = 0; b < row.nb; b++) row.notes.push([]);
                for (k = 0; k < live.notes.length && k < 2000; k++) {
                    var n = live.notes[k], rel = n.start_time - start, bar = Math.floor(rel / barLen);
                    if (bar < 0 || bar >= row.nb || row.notes[bar].length >= 48) continue;
                    var x = (rel - bar * barLen) / barLen;
                    // per mille: a third shorter than 3-decimal fractions, and the roll draws at most ~200 px a bar
                    row.notes[bar].push([Math.round(x * 1000), Math.round(Math.min(n.duration / barLen, 1 - x) * 1000),
                                         Math.round((hi > lo ? (n.pitch - lo) / (hi - lo) : 0.5) * 1000)]);
                }
            }
        }
        var det = cached_instrument(tid);
        row.inst = det.instrument;
        row.src = det.source.toUpperCase();
    } catch (e) { flog("panel_row: track " + i + " failed: " + e); }
    panel_rows[tid] = row;
    return row;
}

function panel_scene(){
    if (panel_scene_cache && panel_scene_cache.scene === current_scene && panel_scene_cache.n === track_ids.length) return panel_scene_cache;
    if (panel_rows_scene !== current_scene) { panel_rows = {}; panel_rows_scene = current_scene; }
    var rows = [], notes = [], maxBars = 0, ts = null;
    for (var i = 0; i < track_ids.length && current_scene >= 0; i++) {
        var row = panel_row(i);
        if (row.hc) { maxBars = Math.max(maxBars, row.nb); if (!ts) ts = row.num + "/" + row.den; }
        rows.push(row);
        notes.push(row.notes);
    }
    if (!ts) {
        try { var song = new LiveAPI("live_set"); ts = song.get("signature_numerator")[0] + "/" + song.get("signature_denominator")[0]; } catch (e) { ts = "4/4"; }
    }
    panel_scene_cache = { scene: current_scene, n: track_ids.length, rows: rows, notes: notes, bars: maxBars || 8, ts: ts };
    panel_scene_cache.nj = JSON.stringify({ scene: current_scene, pm: 1, tracks: notes });   // panel_notes, built once per rebuild (pm: per mille)
    return panel_scene_cache;
}

// Some tracks changed (a clip click, a take, a finished generation, an instrument): re-read only those rows.
function panel_invalidate_tracks(nrs, inst){
    for (var i = 0; i < nrs.length; i++) {
        var tid = track_ids[+nrs[i]];
        if (tid === undefined) continue;
        delete panel_rows[tid];
        if (inst) delete track_inst_cache[tid];
    }
    panel_scene_cache = null;
    schedule_panel();
}

function scene_tparams(t){
    if (current_scene < 0 || !all_clips_params.scenes[current_scene] || !all_clips_params.scenes[current_scene].tracks[t]) return null;
    return apply_track_defaults(all_clips_params.scenes[current_scene].tracks[t]);
}

// The track the TRACK and MASKS bays edit: the MIDI track selected in Live; when none is (an audio or
// return track, or nothing), the last one that was, else the first target, else the first MIDI track.
var panel_last_track = -1;
function panel_edit_track(){
    if (current_track >= 0) { panel_last_track = current_track; return current_track; }
    if (panel_last_track >= 0 && panel_last_track < track_ids.length) return panel_last_track;
    for (var t = 0; t < track_ids.length; t++) { var tp = scene_tparams(t); if (tp && panel_is_target(tp)) return t; }
    return track_ids.length ? 0 : -1;
}

// ------------------------------------------------------------------ state
function push_panel(){
    if (!panel_ready) return;
    var sc = panel_scene(), tracks = [];
    for (var i = 0; i < sc.rows.length; i++) {
        var r = sc.rows[i], tp = scene_tparams(i) || {}, sel = as_array(tp.selected_bars), paint = "", cells = "";
        var nb = r.hc ? r.nb : sc.bars;
        for (var b = 0; b < nb; b++) paint += sel[b] ? "1" : "0";
        for (b = 0; b < sc.bars; b++) cells += !r.hc ? "N" : b >= r.nb ? "N" : (sc.notes[i][b] && sc.notes[i][b].length ? "C" : "E");
        tracks.push({ i: r.i, name: r.name, short: r.short, hc: r.hc, nb: r.nb, cells: cells, paint: paint,
                      ig: tp.ignore ? 1 : 0, ar: tp.autoregressive ? 1 : 0, inst: r.inst, src: r.src });
    }
    var et = panel_edit_track();
    var cp = scene_tparams(et) || apply_track_defaults({});
    var scales = server_scale_presets && server_scale_presets.length ? server_scale_presets : ["major"];
    var caps = server_capabilities || {};
    var gp = global_params;
    var st = {
        scene: current_scene, bars: sc.bars, ts: sc.ts, cur: et, live_sel: current_track >= 0 ? 1 : 0, tracks: tracks,
        tp: { poly: [+cp.min_polyphony_q || 0, +cp.max_polyphony_q || +cp.min_polyphony_q || 0],
              len: [+cp.min_note_duration_q || 0, +cp.max_note_duration_q || +cp.min_note_duration_q || 0], density: +cp.density || 0,
              key: +cp.key_q || 0, range: +cp.range_q || 0, silence: +cp.silence_q || 0, pcs: +cp.pcs_q || 0 },
        masks: { scale: +cp.pitch_mask_mode === 1 ? 1 : 0, root: +cp.pitch_mask_root || 0, mode: Math.max(0, scales.indexOf(cp.pitch_mask_scale)),
                 register: +cp.pitch_shape_mode === 1 ? [+cp.pitch_shape_min, +cp.pitch_shape_max] : [0, 127],
                 rhythm: +cp.rhythm_on ? 1 : 0, unit: cp.rhythm_unit || "sixteenth", strength: +cp.rhythm_grid_strength,
                 exact: +cp.rhythm_exact ? 1 : 0, pattern: as_array(cp.rhythm_pattern),
                 remix: cp.remix_enabled ? 1 : 0, amount: +cp.remix_amount, pd: +cp.remix_mode === 1 ? 1 : 0 },
        sample: { temp: +gp.temperature, topp: +gp.top_p, topk: +gp.top_k, esc: +gp.temperature_escalation,
                  takes: Math.max(1, +gp.num_candidates || 1), seed: gp.seed_auto ? 0 : Math.max(0, +gp.seed) },
        checks: { novelty: gp.novelty_check ? 1 : 0, silence: gp.silence_check ? 1 : 0, shuffle: gp.shuffle ? 1 : 0 },
        engine: { model: gp.model || server_default_model || "", models: server_models.map(function (m) { return m.id; }),
                  dims: model_dim_options(), context: +gp.model_dim, context_auto: gp.model_dim_auto ? 1 : 0,
                  bps: +gp.bars_per_step, bps_auto: gp.bars_per_step_auto ? 1 : 0, tps: +gp.tracks_per_step, tps_auto: gp.tracks_per_step_auto ? 1 : 0,
                  attempts: +gp.max_attempts, polylim: +gp.polyphony_hard_limit, denslim: +gp.density_hard_limit,
                  maskp: +gp.mask_p || 0, maskk: +gp.mask_k || 0, velocity: gp.velocity_enabled ? 1 : 0, micro: gp.microtiming_enabled ? 1 : 0 },
        server: { online: server_online ? 1 : 0, latency: latency_shown(server_latency_ms), url: SERVER_URL, res: server_resolution,
                  caps: { mask: caps.supports_pitch_mask ? 1 : 0, rhythm: caps.supports_rhythm_mask ? 1 : 0, remix: caps.supports_remix ? 1 : 0,
                          scales: scales, units: server_grid_units || [], vel: caps.switchable_velocity ? 1 : 0, micro: caps.switchable_microtiming ? 1 : 0,
                          attrs: server_info && server_info.attributes ? Object.keys(server_info.attributes) : [] } },
        gen: panel_gen_state(),
        err: panel_fault_state,
        tagging: tag_queue.length
    };
    var json = JSON.stringify(st);
    if (json !== panel_last.state) { panel_last.state = json; panel_send("panel_state", json); }
    if (sc !== panel_last.notes) {    // a rebuilt cache has new notes; the same cache has nothing new to send
        var prev = panel_last.notes;
        panel_last.notes = sc;
        if (!prev || prev.nj !== sc.nj) panel_send("panel_notes", sc.nj);
    }
}

// A Max message argument holds at most ~32k characters: a dense scene's notes are longer, and the
// panel got a cut-off string it could not parse (an empty or stale roll). A long message goes in
// parts under its own name, each "~part:<i>:<n>|<text>" (the patch routes only these two names).
var PANEL_PART = 16000;
// The latency the panel shows, in steps: the /health poll measures a slightly different number every time, and an
// unrounded one changed the state (and repainted the roll) on every poll.
function latency_shown(ms){
    if (ms < 0) return 0;
    return ms < 20 ? Math.max(1, Math.ceil(ms / 5) * 5) : ms < 200 ? Math.round(ms / 10) * 10 : Math.round(ms / 50) * 50;
}

function panel_send(kind, json){
    if (json.length <= PANEL_PART) { outlet(OUT_PANEL, kind, json); return; }
    var n = Math.ceil(json.length / PANEL_PART);
    for (var i = 0; i < n; i++) outlet(OUT_PANEL, kind, "~part:" + i + ":" + n + "|" + json.substr(i * PANEL_PART, PANEL_PART));
}

function panel_gen_state(){
    var status = active_generation ? (active_generation.cancel_sent ? "cancelling" : "streaming")
               : last_status === "error" ? "error" : last_status === "done" ? "done" : last_status === "cancelled" ? "cancelled" : "idle";
    var takes = last_generation ? last_generation.candidates.map(function (c) { return c.score ? 1 : 0; }) : [];
    return { status: status, t0: active_generation ? active_generation.started_at : 0, elapsed: panel_gen.elapsed, notes: panel_gen.notes,
             seed: panel_gen.seed, att: panel_gen.att, tps: panel_gen.tps, ctx: panel_gen.ctx, maxctx: panel_gen.maxctx,
             takes: takes, cur: last_generation ? last_generation.selected : -1, orig: last_generation && last_generation.original ? 1 : 0 };
}

// ------------------------------------------------------------------ faults (shown on the OUTPUT screen)
function panel_fault(code, cause, action, opts){
    opts = opts || {};
    panel_fault_state = { id: ++panel_fault_seq, code: code, cause: String(cause).toUpperCase(), action: String(action).toUpperCase(),
                          warn: opts.warn ? 1 : 0, notSent: opts.notSent ? 1 : 0, retry: opts.retry || 0 };
    if (!opts.noReport) panel_fault_fresh = true;
    flog("panel_fault: " + JSON.stringify(panel_fault_state));
    schedule_panel();
}
function trim_cause(s, n){ s = String(s || ""); return s.length > (n || 44) ? s.slice(0, (n || 44) - 1) + "…" : s; }
function track_names_in(msg){
    return String(msg).replace(/track_id=(\d+)/g, function (_, n) {
        var sc = panel_scene_cache, r = sc && sc.rows[+n];
        return r ? r.short : "TRACK " + n;
    });
}
// report_error() strings from the existing code paths -> a fault
function panel_fault_from_message(msg){
    var m;
    msg = String(msg || "");
    if (/server offline/i.test(msg)) return panel_fault("NO LINK", "SERVER UNREACHABLE", "CHECK ADDRESS IN SETUP", { noReport: true });
    if (/Time signature mismatch/i.test(msg)) return panel_fault("TIME SIG", "CLIPS USE DIFFERENT METERS", "MATCH THE TIME SIGNATURES", { notSent: 1, noReport: true });
    if ((m = /(\d+(?:\.\d+)?) available, need at least model_dim=(\d+)/.exec(msg)))
        return panel_fault("TOO FEW BARS", Math.floor(+m[1]) + " BARS, CONTEXT NEEDS " + m[2], "LONGER CLIPS OR LOWER CONTEXT", { notSent: 1, noReport: true });
    if (/Select at least one bar/i.test(msg)) return panel_fault("NO TARGET", "NO BARS CHOSEN", "PAINT BARS OR USE AR", { notSent: 1, noReport: true });
    if (/tag/i.test(msg) && /Instrument|tag device/i.test(msg)) return panel_fault("TAG FAILED", "LIVE DID NOT LOAD THE TAG DEVICE", "ADD IT BY HAND (PATCHERS FOLDER)", { noReport: true });
    if (/timed out/i.test(msg)) return panel_fault("NO REPLY", "SERVER DID NOT ANSWER", "RETRY · CHECK SERVER", { noReport: true });
    if (/no score/i.test(msg)) return panel_fault("SRV FAULT", "REPLY HAD NO SCORE", "RETRY · SEE LOG", { noReport: true });
    return panel_fault("ERROR", trim_cause(msg), "SEE LOG", { noReport: true });
}
// non-200 from POST /generate
function panel_fault_http(status, text){
    var detail = text;
    try { var j = JSON.parse(text); detail = j.detail !== undefined ? (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)) : text; } catch (e) {}
    detail = track_names_in(detail);
    if (status === 503) return panel_fault("SRV BUSY", "SERVER QUEUE FULL", "AUTO RETRY", { warn: 1, retry: 5 });
    if (status === 400 && /unknown model/i.test(detail)) { http_models(); return panel_fault("MODEL GONE", "MODEL NOT ON SERVER", "PICK A MODEL IN ENGINE"); }
    if (status === 400) return panel_fault("BAD REQUEST", "DEVICE SENT A BROKEN REQUEST", "REPORT IT · REQUEST IN LOG");
    if (status === 422) {
        var drum = /(\w+): attribute 'note_density' is drum-only/.exec(detail);
        if (drum) return panel_fault("REJECTED", drum[1] + ": DENSITY IS DRUMS ONLY", "SET DENSITY TO AUTO");
        return panel_fault("REJECTED", trim_cause(detail), "CHECK THE SETTINGS");
    }
    if (status === 500 && /max attempts/i.test(detail)) return panel_fault("CHECKS FAIL", "ALL " + global_params.max_attempts + " ATTEMPTS FAILED", "RAISE ATTEMPTS OR ESC");
    if (status === 500 && /model_dim/i.test(detail)) return panel_fault("CTX OVERFLOW", "CONTEXT TOO LONG FOR MODEL", "IGNORE TRACKS OR LOWER CONTEXT");
    if (status === 500) return panel_fault("SRV FAULT", trim_cause(detail) || "INFERENCE CRASHED ON SERVER", "RETRY · RESTART SERVER IF IT REPEATS");
    if (status === 0) return panel_fault("LINK LOST", "NO RESPONSE FROM SERVER", "NOTHING WRITTEN · RETRY");
    return panel_fault("ERROR " + status, trim_cause(detail), "SEE LOG");
}

// a streamed generation's progress frame ({ n: new notes, progress: { generated_tokens, model_forward_s,
// context_tokens, max_context_tokens, attempt } }): live notes, tokens/s, context and the retry attempt
function panel_generation_progress(ev){
    var p = ev.progress || {};
    if (p.attempt && p.attempt !== panel_gen.att) { panel_gen.att = +p.attempt; panel_gen.notes = 0; }   // a retry starts over
    panel_gen.notes += +ev.n || 0;
    if (p.generated_tokens && p.model_forward_s) panel_gen.tps = p.generated_tokens / p.model_forward_s;
    // the model's window: the step's prompt plus what this step generated (generated_tokens counts every step)
    if (p.context_tokens) panel_gen.ctx = +p.context_tokens + (+p.step_generated_tokens || 0);
    if (p.max_context_tokens) panel_gen.maxctx = +p.max_context_tokens;
    schedule_panel();
}

// a finished generation: stats, and a caution when takes were dropped or cut short
function panel_generation_done(result){
    panel_gen.elapsed = active_generation ? (Date.now() - active_generation.started_at) / 1000 : 0;
    var cands = result.candidates || null, ok = 0, failed = 0, trunc = false, written = 0;
    if (cands) {
        for (var i = 0; i < cands.length; i++) { if (cands[i].score) ok++; else failed++; if (cands[i].truncated) trunc = true; }
        var first = null;
        for (i = 0; i < cands.length; i++) if (cands[i].score) { first = cands[i]; break; }
        if (first) written = count_target_notes(first.score);
        panel_gen.seed = result.base_seed || (first && first.seed) || 0;
    } else if (result.score) {
        written = count_target_notes(result.score);
        panel_gen.seed = result.seed || 0;
        if (result.truncated) trunc = true;
    }
    panel_gen.notes = written;
    var tok = result.tokens || {}, tim = result.timing || {};
    var gen = +(tok.generated_tokens || tim.gen_count || 0), secs = +(tim.model_forward_s || 0);
    panel_gen.tps = +tok.tokens_per_second || (gen && secs ? gen / secs : 0);
    panel_gen.ctx = +(tok.peak_context_tokens || 0);   // the fullest the model's window got in any step
    panel_gen.maxctx = +(tok.max_context_tokens || 0);
    if (result.attempts) panel_gen.att = +result.attempts;
    if (failed && ok) panel_fault("TAKES LOST", failed + " OF " + (ok + failed) + " TAKES FAILED CHECKS", ok + " TAKES READY", { warn: 1, noReport: true });
    else if (trunc) panel_fault("CTX LIMIT", "TAKES MAY BE CUT SHORT", "LOWER CONTEXT OR BARS", { warn: 1, noReport: true });
    // only the targets' clips changed (and a target that had no clip now has one)
    if (last_write_ctx) panel_invalidate_tracks(last_write_ctx.write_track_nrs); else panel_invalidate_scene();
}
function count_target_notes(score){
    var n = 0, ctx = last_write_ctx;
    if (!score || !score.tracks || !ctx) return 0;
    for (var t in score.tracks) {
        if (ctx.write_track_nrs.indexOf(t) < 0 && ctx.write_track_nrs.indexOf(+t) < 0) continue;
        var bars = score.tracks[t].bars || [];
        for (var b = 0; b < bars.length; b++) n += (bars[b].notes || []).length;
    }
    return n;
}

// ------------------------------------------------------------------ messages from the panel
function panel_track_param(t, key, value){
    var tp = scene_tparams(t);
    if (!tp) return;
    tp[key] = value;
    schedule_dict_sync();
}

function panel_message(a){
    var verb = a[1], t, tp, i;
    switch (verb) {
        case "ready":
            panel_ready = true;
            panel_last = { state: "", notes: null };
            panel_scene_cache = null;
            push_panel();
            return;
        case "generate":
            panel_fault_state = null;
            panel_gen = { t0: Date.now(), elapsed: 0, notes: 0, seed: 0, att: 0, tps: 0, ctx: 0, maxctx: 0 };
            bang();
            break;
        case "cancel": http_cancel(); break;
        case "take":
            if (+a[2] < 0) restore_original(); else select_candidate(+a[2]);
            panel_invalidate_tracks(last_generation && last_generation.ctx ? last_generation.ctx.write_track_nrs : track_ids.map(function (_, j) { return j; }));
            break;
        case "keep": last_generation = null; break;
        case "clear_fault": panel_fault_state = null; break;
        case "connect": http_health(); http_info(); http_models(); break;
        case "reset": reset_all_settings(); break;
        case "select_track":
            t = +a[2];
            if (track_ids[t] !== undefined) { var view = new LiveAPI("live_set view"); view.set("selected_track", "id " + track_ids[t]); }
            return;
        case "bar":
            t = +a[2]; tp = scene_tparams(t);
            if (!tp) return;
            var sel = as_array(tp.selected_bars).slice(), bi = +a[3];
            while (sel.length <= bi) sel.push(false);
            sel[bi] = !!(+a[4]);
            tp.selected_bars = sel;
            schedule_dict_sync();
            break;
        case "ignore":
            t = +a[2]; tp = scene_tparams(t);
            if (!tp) return;
            tp.ignore = !!(+a[3]);
            if (tp.ignore) tp.autoregressive = false;
            schedule_dict_sync();
            break;
        case "ar":
            t = +a[2]; tp = scene_tparams(t);
            if (!tp) return;
            tp.autoregressive = !!(+a[3]);
            if (tp.autoregressive) tp.ignore = false;
            schedule_dict_sync();
            break;
        case "track":   // the selected track's attributes; 0 = AUTO
            var et = panel_edit_track();
            if (et < 0) return;
            if (a[2] === "poly") { panel_track_param(et, "min_polyphony_q", +a[3]); panel_track_param(et, "max_polyphony_q", +a[4]); }
            else if (a[2] === "len") { panel_track_param(et, "min_note_duration_q", +a[3]); panel_track_param(et, "max_note_duration_q", +a[4]); }
            else if (a[2] === "density") panel_track_param(et, "density", +a[3]);
            else if (a[2] === "key" || a[2] === "range" || a[2] === "silence" || a[2] === "pcs") panel_track_param(et, a[2] + "_q", +a[3]);
            break;
        case "mask":    // the selected track's masks
            var et = panel_edit_track();
            if (et < 0) return;
            var k = a[2], v = a[3];
            if (k === "scale_on") panel_track_param(et, "pitch_mask_mode", +v ? 1 : 0);
            else if (k === "root") panel_track_param(et, "pitch_mask_root", +v);
            else if (k === "scale") panel_track_param(et, "pitch_mask_scale", String(v));
            else if (k === "register") {
                var lo = +a[3], hi = +a[4], full = lo <= 0 && hi >= 127;
                panel_track_param(et, "pitch_shape_mode", full ? 0 : 1);
                panel_track_param(et, "pitch_shape_min", lo);
                panel_track_param(et, "pitch_shape_max", hi);
            }
            else if (k === "rhythm") panel_track_param(et, "rhythm_on", +v ? 1 : 0);
            else if (k === "unit") panel_track_param(et, "rhythm_unit", String(v));
            else if (k === "strength") panel_track_param(et, "rhythm_grid_strength", +v);
            else if (k === "exact") panel_track_param(et, "rhythm_exact", +v ? 1 : 0);
            else if (k === "pattern") panel_track_param(et, "rhythm_pattern", a.slice(3).map(Number));
            else if (k === "remix") panel_track_param(et, "remix_enabled", +v ? 1 : 0);
            else if (k === "amount") panel_track_param(et, "remix_amount", +v);
            else if (k === "pd") panel_track_param(et, "remix_mode", +v ? 1 : 0);
            break;
        case "sample":
            var sk = a[2], sv = +a[3];
            if (sk === "temp") set_global_param("temperature", sv);
            else if (sk === "topp") { sv = Math.max(0.05, Math.min(1, sv)); set_global_param("top_p", sv); set_global_param("top_p_auto", sv >= 1); }   // server: (0, 1]
            else if (sk === "topk") { set_global_param("top_k", Math.round(sv)); set_global_param("top_k_auto", sv <= 0); }
            else if (sk === "esc") { set_global_param("temperature_escalation", sv); set_global_param("temp_esc_auto", sv <= 1); }
            else if (sk === "takes") set_global_param("num_candidates", Math.round(sv));
            else if (sk === "seed") { set_global_param("seed_auto", sv <= 0); set_global_param("seed", sv > 0 ? Math.round(sv) : -1); }
            break;
        case "seed_text":   // typed in the seed field: empty or 0 = random, a whole number 1..2147483647 = that seed, else ignored
            var stx = a.slice(2).join(" ").replace(/\s+/g, "");
            if (stx === "" || stx === "bang" || stx === "0") { set_global_param("seed_auto", true); set_global_param("seed", -1); }
            else if (/^\d+$/.test(stx) && +stx >= 1 && +stx <= 2147483647) { set_global_param("seed_auto", false); set_global_param("seed", +stx); }
            else flog("panel_message: seed_text ignored: " + stx);
            break;
        case "engine":
            if (a[2] === "mask_p") set_global_param("mask_p", +a[3]);
            else if (a[2] === "mask_k") set_global_param("mask_k", Math.round(+a[3]));
            else engine_set(a[2], a[3]);
            break;
        case "set_instrument":
            t = +a[2];
            if (track_ids[t] !== undefined) set_track_instrument(track_ids[t], +a[3] === TAG_DRUMS ? "drum" : "melodic", +a[3] === TAG_DRUMS ? 0 : +a[3]);
            panel_invalidate_tracks([t], true);
            break;
        case "setup_apply":   // setup_apply <track> <inst> <track> <inst> ...
            for (i = 2; i + 1 < a.length; i += 2) {
                t = +a[i];
                var inst = +a[i + 1];
                if (track_ids[t] === undefined) continue;
                set_track_instrument(track_ids[t], inst === TAG_DRUMS ? "drum" : "melodic", inst === TAG_DRUMS ? 0 : inst);
            }
            panel_invalidate_tracks(a.slice(2).filter(function (_, j) { return j % 2 === 0; }), true);
            break;
        case "perf": flog("panel perf " + a[2] + ": avg " + a[3] + " ms, max " + a[4] + " ms"); return;
        default:
            flog("panel_message: unknown " + a.join(" "));
            return;
    }
    schedule_panel();
}
