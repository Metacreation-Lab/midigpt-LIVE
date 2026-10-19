/**
 * @license
 * Copyright 2021 Metacreation Lab All Rights Reserved.
 *
 * Licensed under ????
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    ????
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
*/

/*________________________________________________________________________

            Max generic stuff:
 ________________________________________________________________________*/

// The core of the MIDI-GPT device: Live API observers, generation state, the
// HTTP client, and writing results into clips. The panel side of it is in
// midigpt_panel_link.js (include()d below).
//
// Outlets: 0 -> the panel window (panel_state / panel_notes, see midigpt_panel_link.js)
//          1 -> the dev bridge's [udpsend 127.0.0.1 7475] (see bridge())
//          2 -> [node.script midigpt_node.js] (open_tag, config_set)
//
// autowatch is off: it makes Max poll the file and recompile on every save,
// which is a development convenience, not something to ship. While
// developing, reload with tools/bridge.py reload (or re-add the device).
autowatch = 0;
outlets = 3;
inlets = 1;
var OUT_PANEL = 0, OUT_BRIDGE = 1, OUT_NODE = 2;

// Repo root while developing (<root>/patchers/MIDI-GPT.amxd): where dev mode's
// flag file and log live. patcher.filepath is often still empty while the
// script is first being instantiated, so init() resolves this again once the
// device has loaded (see resolve_paths()).
function compute_root(patcher){
    var fp = "";
    try { fp = patcher.filepath || ""; } catch (e) {}
    if (!fp) return "";
    var dir = fp.substring(0, fp.lastIndexOf("/"));
    if (dir.slice(-9) === "/patchers") dir = dir.slice(0, -9);
    return dir;
}
var ROOT = compute_root(this.patcher);
// the folder the device file is in (the tag device ships next to it)
function compute_device_dir(patcher){
    var fp = "";
    try { fp = patcher.filepath || ""; } catch (e) {}
    return fp ? fp.substring(0, fp.lastIndexOf("/")) : "";
}
var DEVICE_DIR = compute_device_dir(this.patcher);

function root_path(name){ return ROOT ? ROOT + "/" + name : name; }

function file_exists(path){
    var f = new File(path, "read");
    var ok = f.isopen;
    if (ok) f.close();
    return ok;
}

// Dev mode = verbose logging to the Max console + midigpt.log, and the UDP dev
// bridge. Off unless the device's 2nd js argument is 1 or a ".midigpt_dev"
// file exists in the repo root (gitignored) -- so a shipped device stays
// quiet without having to edit the .amxd.
var DEV_MODE = file_exists(root_path(".midigpt_dev"));
var debug = DEV_MODE;

// File logging is buffered and flushed by a Task at most once a second:
// writing the log synchronously on every post() (on Live's UI thread) made
// the device sluggish.
var _logfile = root_path("midigpt.log");
var _orig_post = post;
var _log_buffer = [];
var _log_flush_pending = false;
var _log_flush_task = new Task(function(){
    _log_flush_pending = false;
    if (!_log_buffer.length) return;
    var lines = _log_buffer;
    _log_buffer = [];
    try {
        var f = new File(_logfile, "readwrite", "TEXT");
        // Max's File doesn't reliably seek to EOF on open; do it explicitly.
        f.position = f.eof;
        for (var i = 0; i < lines.length; i++) f.writeline(lines[i]);
        f.close();
    } catch (e) {}
}, this);

post = function() {
    var msg = Array.prototype.slice.call(arguments).join(" ");
    _orig_post(msg);
    if (!debug) return;
    _log_buffer.push(new Date().toISOString().slice(11,23) + " " + msg);
    if (!_log_flush_pending) { _log_flush_pending = true; _log_flush_task.schedule(1000); }
};
// Diagnostic logging -- a no-op unless debug is on. Use error() for
// anything the user should always see in the Max console.
function flog() { if (debug) post.apply(null, arguments); }
// Dev mode: where a request's full body and reply go (the Node helper writes them; see http_send's dump argument).
function dump_prefix(request_id){ return root_path("midigpt_requests/" + request_id); }

// Written every time this script is (re)compiled: grep the log for
// "SCRIPT LOADED" to check that an edit is live.
flog("==== midigpt.js SCRIPT LOADED at " + new Date().toISOString() + " ====");

if (jsarguments.length>1 && +jsarguments[1])
    debug = DEV_MODE = true;

/*________________________________________________________________________

            Variables:
 ________________________________________________________________________*/

// Mirrors of the JS state, so it survives a script reload (see schedule_dict_sync()).
var max_global_params = new Dict("global_params");
var max_scenes_params = new Dict("scenes_params");

var SERVER_URL = "http://127.0.0.1:3456";   // install.sh's server launcher

// The server URL is a per-user setting, saved by the node.script helper
// (javascript/midigpt_node.js) in ~/Library/Application Support/MIDI-GPT/live.json
// (%APPDATA%\MIDI-GPT on Windows): a frozen device's own folder may be
// read-only or temporary. The helper sends it back ("config server_url ...")
// when it starts.
function save_persisted_server_url(){
    outlet(OUT_NODE, "config_set", "server_url", SERVER_URL);
}

// "config <key> <value>" / "config_ready" from the node.script helper
function handle_config(a){
    if (a[0] == "config_ready") return;
    if (a[1] == "server_url" && a[2]) {
        if (String(a[2]) === SERVER_URL) return;
        SERVER_URL = String(a[2]);
        global_params.server_url = SERVER_URL;
        flog("config: server_url " + SERVER_URL);
        if (initialized) { schedule_panel(); http_info(); http_models(); }
    }
}


// Unset track -> melodic Acoustic Grand Piano (GM program 0), matching
// default_track_params' own prior instrument:0/track_type:10(=melodic)
// defaults -- same neutral fallback, just resolved from the new map
// instead of a dead per-scene tparams field.
function track_instrument_key(track_id){
    var track = new LiveAPI();
    track.id = track_id;
    var name = track.get("name");
    return "name:" + ((name && name.length) ? name.join(" ") : track_id);
}

// ---------------------------------------------------------------------------
// Track instruments live ON the track: a "MIDI-GPT Instrument" device (a
// pass-through MIDI effect, patchers/MIDI-GPT Instrument.amxd) holds the GM
// program (0-127) or Drums (128) as its stored "Instrument" parameter. It is
// saved with the set and moves with the track through renames, reordering,
// duplication and copy/paste -- the Live counterpart of the Reaper plugin
// renaming tracks to canonical instrument names. Setup writes the tags;
// generation reads them. A track without a tag is detected from what Live
// exposes, in this order and nothing else: its instrument device (a Drum Rack
// means drums, otherwise the device/preset name), then the track name, then
// the default (Acoustic Grand Piano).
// ---------------------------------------------------------------------------
// Track-name keywords and canonical GM names, ported from midigpt-REAPER's midi_extraction.py so both
// plugins resolve a name the same way (exact canonical name first, then the first keyword hit in GM order).
var GM_KEYWORDS = [[0, ["piano", "key"]], [1, ["bright"]], [3, ["honk"]], [4, ["ep1"]], [5, ["ep2"]], [6, ["harpsi"]], [7, ["clav"]], [8, ["celest"]], [9, ["glock"]], [10, ["box"]], [11, ["vibra"]], [12, ["marimba"]], [13, ["xyl"]], [14, ["bell", "tubu"]], [15, ["dulcimer"]], [16, ["organ", "dorg"]], [17, ["porg"]], [18, ["rorg"]], [19, ["corg"]], [20, ["reorg", "reed"]], [21, ["acc"]], [22, ["harmonica"]], [23, ["tango"]], [24, ["nyl"]], [25, ["steel g", "sgtr", "agtr"]], [26, ["jazz", "jgtr"]], [27, ["cgtr"]], [28, ["mute", "mgtr"]], [29, ["ogtr", "over"]], [30, ["gtr", "guit", "dist"]], [31, ["harmon"]], [32, ["aco"]], [33, ["finger"]], [34, ["bass"]], [35, ["fretless"]], [37, ["slap"]], [38, ["sbass1"]], [39, ["sbass2"]], [40, ["violin", "vn1", "vn2"]], [41, ["viola", "vn3"]], [42, ["cell", "vn4"]], [43, ["contra", "vn5"]], [44, ["trem"]], [45, ["pizz"]], [46, ["harp"]], [47, ["timp"]], [48, ["str"]], [52, ["choir", "aah"]], [53, ["ooh"]], [54, ["voice"]], [55, ["hit", "orch"]], [56, ["trumpet", "tp"]], [57, ["trom"]], [58, ["tuba"]], [59, ["muted"]], [60, ["french", "horn", "fh"]], [61, ["brass"]], [64, ["sax"]], [68, ["oboe"]], [69, ["english horn", "english"]], [70, ["bsn", "baso"]], [71, ["clarinet"]], [72, ["picc"]], [73, ["flute", "fl1", "fl2"]], [74, ["recorder"]], [75, ["pan"]], [76, ["bottle"]], [77, ["shak"]], [78, ["whistle"]], [79, ["ocarina"]], [80, ["square", "lead1", "ld1"]], [81, ["saw", "lead2", "ld2"]], [82, ["calli", "lead3", "ld3"]], [83, ["chiff", "lead4", "ld4"]], [84, ["chara", "lead5", "ld5"]], [85, ["lead 6", "ld6"]], [86, ["fifth", "lead7", "ld7"]], [87, ["lead8", "ld8"]], [88, ["pad1", "new", "age"]], [89, ["pad2", "warm"]], [90, ["pad3", "polys"]], [91, ["pad4", "cpad"]], [92, ["pad5", "bowed"]], [93, ["pad6", "metallic"]], [94, ["pad7", "halo"]], [95, ["pad8", "sweep"]], [96, ["fx1", "rain"]], [97, ["fx2", "soundtrack"]], [98, ["fx3", "crystal"]], [99, ["fx4", "atmos"]], [100, ["fx5"]], [101, ["fx6", "goblin"]], [102, ["fx7", "echoes"]], [103, ["fx8", "sci"]], [104, ["sitar"]], [105, ["banjo"]], [106, ["sham"]], [107, ["koto"]], [108, ["kali"]], [109, ["bag", "pipe"]], [110, ["fiddle"]], [111, ["shan"]], [112, ["tink"]], [113, ["agog"]], [114, ["steel"]], [115, ["wood"]], [116, ["taiko"]], [117, ["mtom", "melodic tom"]], [118, ["synth drum", "sdrum"]], [119, ["rev"]], [120, ["fret"]], [121, ["breath"]], [122, ["seashore"]], [123, ["bird", "tweet"]], [124, ["phone"]], [125, ["heli"]], [126, ["applause"]], [127, ["gunshot"]], [128, ["drum", "kick", "kik", "sn", "tom", "hat", "ride", "crash", "china", "tambo"]]];
var GM_CANONICAL = ["acoustic_grand_piano", "bright_acoustic_piano", "electric_grand_piano", "honky_tonk_piano", "electric_piano_1", "electric_piano_2", "harpsichord", "clavi", "celesta", "glockenspiel", "music_box", "vibraphone", "marimba", "xylophone", "tubular_bells", "dulcimer", "drawbar_organ", "percussive_organ", "rock_organ", "church_organ", "reed_organ", "accordion", "harmonica", "tango_accordion", "acoustic_guitar_nylon", "acoustic_guitar_steel", "electric_guitar_jazz", "electric_guitar_clean", "electric_guitar_muted", "overdriven_guitar", "distortion_guitar", "guitar_harmonics", "acoustic_bass", "electric_bass_finger", "electric_bass_pick", "fretless_bass", "slap_bass_1", "slap_bass_2", "synth_bass_1", "synth_bass_2", "violin", "viola", "cello", "contrabass", "tremolo_strings", "pizzicato_strings", "orchestral_harp", "timpani", "string_ensemble_1", "string_ensemble_2", "synth_strings_1", "synth_strings_2", "choir_aahs", "voice_oohs", "synth_voice", "orchestra_hit", "trumpet", "trombone", "tuba", "muted_trumpet", "french_horn", "brass_section", "synth_brass_1", "synth_brass_2", "soprano_sax", "alto_sax", "tenor_sax", "baritone_sax", "oboe", "english_horn", "bassoon", "clarinet", "piccolo", "flute", "recorder", "pan_flute", "blown_bottle", "shakuhachi", "whistle", "ocarina", "lead_1_square", "lead_2_sawtooth", "lead_3_calliope", "lead_4_chiff", "lead_5_charang", "lead_6_voice", "lead_7_fifths", "lead_8_bass__lead", "pad_1_new_age", "pad_2_warm", "pad_3_polysynth", "pad_4_choir", "pad_5_bowed", "pad_6_metallic", "pad_7_halo", "pad_8_sweep", "fx_1_rain", "fx_2_soundtrack", "fx_3_crystal", "fx_4_atmosphere", "fx_5_brightness", "fx_6_goblins", "fx_7_echoes", "fx_8_sci_fi", "sitar", "banjo", "shamisen", "koto", "kalimba", "bag_pipe", "fiddle", "shanai", "tinkle_bell", "agogo", "steel_drums", "woodblock", "taiko_drum", "melodic_tom", "synth_drum", "reverse_cymbal", "guitar_fret_noise", "breath_noise", "seashore", "bird_tweet", "telephone_ring", "helicopter", "applause", "gunshot"];

var TAG_DEVICE_NAME = "MIDI-GPT Instrument";
var TAG_DRUMS = 128;

function name_to_instrument(name){
    if (!name) return null;
    var lower = String(name).toLowerCase();
    var canon = lower.split(/\s+/).join("_").replace(/-/g, "_");
    if (canon === "drums") return TAG_DRUMS;
    var exact = GM_CANONICAL.indexOf(canon);
    if (exact >= 0) return exact;
    for (var i = 0; i < GM_KEYWORDS.length; i++) {
        var words = GM_KEYWORDS[i][1];
        for (var j = 0; j < words.length; j++) if (lower.indexOf(words[j]) !== -1) return GM_KEYWORDS[i][0];
    }
    return null;
}

function track_device_ids(track_id){
    var t = new LiveAPI();
    t.id = track_id;
    return strip_ids(t.get("devices"));
}

// {device, param} ids of the track's tag, or null
function find_tag(track_id){
    var devs = track_device_ids(track_id);
    for (var i = 0; i < devs.length; i++) {
        var d = new LiveAPI();
        d.id = devs[i];
        if ((d.get("name") || [""])[0] !== TAG_DEVICE_NAME) continue;
        var params = strip_ids(d.get("parameters"));
        for (var k = 0; k < params.length; k++) {
            var p = new LiveAPI();
            p.id = params[k];
            if ((p.get("name") || [""])[0] === "Instrument") return { device: devs[i], param: params[k] };
        }
    }
    return null;
}

function read_tag(track_id){
    var tag = find_tag(track_id);
    if (!tag) return null;
    var p = new LiveAPI();
    p.id = tag.param;
    return Math.round(+p.get("value")[0]);
}

function write_tag(track_id, instrument){
    var tag = find_tag(track_id);
    if (!tag) return false;
    var p = new LiveAPI();
    p.id = tag.param;
    p.set("value", instrument);
    return true;
}

// {instrument: 0-127 | 128, source: "tag" | "drum rack" | "device" | "name" | "default"}
function detect_track_instrument(track_id){
    var tagged = read_tag(track_id);
    if (tagged !== null) return { instrument: tagged, source: "tag" };
    var devs = track_device_ids(track_id);
    for (var i = 0; i < devs.length; i++) {
        var d = new LiveAPI();
        d.id = devs[i];
        var cls = (d.get("class_name") || [""])[0];
        if (cls === "DrumGroupDevice") return { instrument: TAG_DRUMS, source: "drum rack" };
        if (+(d.get("type") || [0])[0] === 1) {   // instrument (or instrument rack): its name is the preset / plugin name
            var hit = name_to_instrument((d.get("name") || [""])[0]);
            if (hit !== null) return { instrument: hit, source: "device" };
        }
    }
    var t = new LiveAPI();
    t.id = track_id;
    var byName = name_to_instrument((t.get("name") || [""]).join(" "));
    if (byName !== null) return { instrument: byName, source: "name" };
    return { instrument: 0, source: "default" };
}

function get_track_instrument(track_id){
    var d = detect_track_instrument(track_id);
    return d.instrument === TAG_DRUMS ? { track_type: "drum", instrument: 0 } : { track_type: "melodic", instrument: d.instrument };
}

// Writes the track's tag, adding the tag device first if the track has none.
function set_track_instrument(track_id, track_type, instrument){
    var inst = track_type === "drum" ? TAG_DRUMS : (+instrument || 0);
    if (write_tag(track_id, inst)) { flog("set_track_instrument: tag " + track_id + " -> " + inst); schedule_panel(); return; }
    ensure_tag(track_id, inst);
}

// The Live API cannot insert devices, so a tag is added the way a user would:
// select the track, then ask Live to open the tag's .amxd (Live loads a device
// file onto the selected track). node.script (javascript/midigpt_node.js) does the
// opening; this side waits for the device to appear and then sets it.
var tag_queue = [];
var tag_task = null;
function ensure_tag(track_id, instrument){
    // already waiting for this track's tag: just change what it will be set to (opening it again would add a second tag)
    for (var q = 0; q < tag_queue.length; q++) if (tag_queue[q].track == track_id) { tag_queue[q].instrument = instrument; return; }
    tag_queue.push({ track: track_id, instrument: instrument, tries: 0, opened: false });
    if (!tag_task) next_tag();
}
function next_tag(){
    if (!tag_queue.length) { tag_task = null; schedule_panel(); return; }
    var job = tag_queue[0];
    if (write_tag(job.track, job.instrument)) { flog("tag set on " + job.track + " -> " + job.instrument); tag_queue.shift(); next_tag(); return; }
    if (!job.opened) {
        var view = new LiveAPI("live_set view");
        view.set("selected_track", "id " + job.track);
        outlet(OUT_NODE, "open_tag", DEVICE_DIR, TAG_DEVICE_NAME + ".amxd");
        job.opened = true;
    }
    if (++job.tries > 40) { report_error("Could not add the MIDI-GPT Instrument tag to a track (Live did not load it)."); tag_queue.shift(); }
    tag_task = new Task(next_tag, this);
    tag_task.schedule(250);
}

// Standard General MIDI 1 program names, GM program numbers 0-127 (index
// == program number), for turning a stored instrument value back into a name.
var GM_INSTRUMENT_NAMES = [
    "Acoustic Grand Piano","Bright Acoustic Piano","Electric Grand Piano","Honky-tonk Piano",
    "Electric Piano 1","Electric Piano 2","Harpsichord","Clavinet",
    "Celesta","Glockenspiel","Music Box","Vibraphone","Marimba","Xylophone","Tubular Bells","Dulcimer",
    "Drawbar Organ","Percussive Organ","Rock Organ","Church Organ","Reed Organ","Accordion","Harmonica","Tango Accordion",
    "Acoustic Guitar (nylon)","Acoustic Guitar (steel)","Electric Guitar (jazz)","Electric Guitar (clean)",
    "Electric Guitar (muted)","Overdriven Guitar","Distortion Guitar","Guitar Harmonics",
    "Acoustic Bass","Electric Bass (finger)","Electric Bass (pick)","Fretless Bass",
    "Slap Bass 1","Slap Bass 2","Synth Bass 1","Synth Bass 2",
    "Violin","Viola","Cello","Contrabass","Tremolo Strings","Pizzicato Strings","Orchestral Harp","Timpani",
    "String Ensemble 1","String Ensemble 2","Synth Strings 1","Synth Strings 2",
    "Choir Aahs","Voice Oohs","Synth Voice","Orchestra Hit",
    "Trumpet","Trombone","Tuba","Muted Trumpet","French Horn","Brass Section","Synth Brass 1","Synth Brass 2",
    "Soprano Sax","Alto Sax","Tenor Sax","Baritone Sax","Oboe","English Horn","Bassoon","Clarinet",
    "Piccolo","Flute","Recorder","Pan Flute","Blown Bottle","Shakuhachi","Whistle","Ocarina",
    "Lead 1 (square)","Lead 2 (sawtooth)","Lead 3 (calliope)","Lead 4 (chiff)",
    "Lead 5 (charang)","Lead 6 (voice)","Lead 7 (fifths)","Lead 8 (bass + lead)",
    "Pad 1 (new age)","Pad 2 (warm)","Pad 3 (polysynth)","Pad 4 (choir)",
    "Pad 5 (bowed)","Pad 6 (metallic)","Pad 7 (halo)","Pad 8 (sweep)",
    "FX 1 (rain)","FX 2 (soundtrack)","FX 3 (crystal)","FX 4 (atmosphere)",
    "FX 5 (brightness)","FX 6 (goblins)","FX 7 (echoes)","FX 8 (sci-fi)",
    "Sitar","Banjo","Shamisen","Koto","Kalimba","Bag pipe","Fiddle","Shanai",
    "Tinkle Bell","Agogo","Steel Drums","Woodblock","Taiko Drum","Melodic Tom","Synth Drum","Reverse Cymbal",
    "Guitar Fret Noise","Breath Noise","Seashore","Bird Tweet","Telephone Ring","Helicopter","Applause","Gunshot"
];

// model_dim (context bars) the loaded checkpoint accepts, from /info
function model_dim_options(){
    var opts = server_capabilities && server_capabilities.model_dim_options;
    return opts && opts.length ? opts : [4, 8];
}

// Server info/capabilities cache -- populated by http_info(), consulted
// when building requests (mask_mode, num_candidates clamp) and by the UI
// to gate advanced controls the loaded checkpoint doesn't support.
//
// server_resolution (/info's "resolution") is the tokenizer's internal
// token grid -- used ONLY for converting our own tick units into
// rhythm_mask.positions.pos / rhythm_mask.grid values (not implemented
// yet). It has NOTHING to do with note onset_ticks/duration_ticks -- that
// is governed entirely by each individual score object's own `resolution`
// field (see SCORE_RESOLUTION below), request and response alike. Mixing
// the two up produced notes with wildly wrong timing/duration; keep them
// separate.
var server_info = null;
var server_capabilities = {};
var server_resolution = 480;
var server_scale_presets = [];
var server_grid_units = [];
var server_online = false;

// Ticks-per-quarter-note we use to encode our OWN outgoing score (context
// notes read from Live). Standard MIDI PPQ, matches the API's own default
// -- confirmed with the server side: score.resolution (not /info's
// resolution) governs note ticks in every score body, request and
// response, and defaults to 480. Always read a *response*'s own
// score.resolution when parsing it back (see write_score_to_clips()) --
// this constant is only for what we send.
var SCORE_RESOLUTION = 480;

var midigptScore = {};
var midigptRequest = {};

// Those are the variables where we store general info about the Live session’s state:
var scene_ids = [];
var track_ids = [];
var current_scene = -1;
var current_track = -1;
var current_track_slots = [];

// Populated fresh by build_request() on every generation: parallel
// arrays of (track index, clip id) for exactly the tracks that were
// generation targets in that request -- resolved directly via LiveAPI in
// the same per-track loop that already touches every track's clip, not
// derived from Live's Session View multi-selection. This is what
// capture_write_ctx()/write_score_to_clips() actually write results back
// into.
var write_track_nrs = [];
var write_clip_ids = [];
var write_max_loop_start = 0;
var write_original = [];    // the targets as they were at GENERATE (build_request): what the take picker's revert restores

var scene_tempo, session_ts_n, session_ts_d;

/*______________________________________________________________________
 
            Clips generation parameters:
________________________________________________________________________*/

// The panel (javascript/midigpt_panel.js): its state push and message handler share this file's globals.
// Included before any top-level code can call into it.
include("midigpt_panel_link.js");

var default_track_params = {
    autoregressive: false,
    ignore: false,
    track_type: 10, //aka STANDARD_TRACK (11 for STANDARD_DRUM_TRACK)
    instrument: 0,
    instrument_name: "any",
    temperature: 1.,
    ts_numerator: 4,
    ts_denominator: 4,
    n_bars: 0,
    // Common stuff:
    selected_bars: [],
    // for instruments only:
    min_polyphony_q: 0, //max: 6 - 0 is any
    max_polyphony_q: 0, //max: 6
    min_note_duration_q: 0, //max: 6 - 0 is any
    max_note_duration_q: 0, //max: 6
    polyphony_hard_limit: 12, //ints - is 0 any ?
    // for drums only:
    density: 0,
    start_time: 0,
    length: 0,
    n_bars_to_create: 1,

    // Pitch mask: 0=Off, 1=Scale, 2=Pitch Classes
    pitch_mask_mode: 0,
    pitch_mask_scale: "major",
    pitch_mask_root: 0,
    pitch_mask_classes: 0,   // 12-bit bitmask, bit N = pitch class N allowed
    // Pitch mask soft reweight: 0=Off, 1=Uniform, 2=Normal
    pitch_shape_mode: 0,
    pitch_shape_min: 48,
    pitch_shape_max: 72,
    pitch_shape_mean: 60,
    pitch_shape_std: 8,
    // Rhythm mask (soft grid only). "" = Off, else a grid unit name.
    rhythm_grid_unit: "",
    rhythm_grid_strength: 0.8,
    // The panel's rhythm editor: on/off, unit, GRID (soft) or EXACT (onsets per bar, polyphony each)
    rhythm_on: 0,
    rhythm_unit: "sixteenth",
    rhythm_exact: 0,
    rhythm_pattern: [],
    // Remix (variation of existing content); mutually exclusive with
    // rhythm_mask on the same track, enforced in compute_track_controls().
    remix_enabled: 0,
    remix_amount: 0.3,
    remix_mode: 0,   // 0=Pitch Only, 1=Pitch + Duration
}


/*______________________________________________________________________
 
            Global generation parameters:
________________________________________________________________________*/

var global_params = {
    percentage : 100,
    shuffle : false,
    tracks_per_step : 1,
    bars_per_step : 1,
    model_dim: 4,
    batch_size: 1,
    use_per_track_temperature: true,
    temperature: 1.0,
    ckpt: "",
    verbose: false,
    // InferenceConfig fields not previously sent -- see build_config():
    seed: -1,                    // -1 = omit key, server picks + returns one
    max_attempts: 3,
    novelty_check: true,
    silence_check: true,
    temperature_escalation: 1.0,
    polyphony_hard_limit: 0,
    density_hard_limit: 0,
    top_p: 1.0,
    top_k: 0,
    mask_p: 0,
    mask_k: 0,
    num_candidates: 1,
    // Selected checkpoint id (from GET /models, e.g. "yellow_medium") --
    // sent as config.model on every /generate call (per-request selection,
    // no separate server-side switch endpoint exists). "" = not chosen
    // yet / use whatever the server defaults to (build_config() omits the
    // key entirely in that case).
    model: "",
    // *_auto: true = Auto (the server or effective_model_dim() decides). seed_auto omits the
    // seed so the server picks one (and returns it).
    model_dim_auto: true,
    bars_per_step_auto: true,
    tracks_per_step_auto: true,
    poly_hard_limit_auto: true,
    density_hard_limit_auto: true,
    top_k_auto: true,
    top_p_auto: true,
    temp_esc_auto: true,
    seed_auto: true,
    // Top-level request.controls -- see build_request():
    velocity_enabled: false,
    microtiming_enabled: false,
    genre: "",
    server_url: SERVER_URL
}

// Snapshot of the real defaults above, for reset_all_settings() -- taken
// once at load, before global_params gets mutated by anything else.
var DEFAULT_GLOBAL_PARAMS = JSON.parse(JSON.stringify(global_params));

if ( JSON.stringify(max_global_params) == "{}") {
    debug && post("max global params empty at init — setting default params ", "\n");
    max_global_params.parse(JSON.stringify(global_params));
} else {
    // Dict already has saved content from a previous session -- load it
    // back instead of overwriting with defaults. Merge key-by-key so a
    // schema change (new fields added since the last save) still gets
    // sane defaults for whatever the saved dict doesn't have.
    var saved_global_params = JSON.parse(max_global_params.stringify());
    for (var gk in saved_global_params) {
        if (gk in global_params) global_params[gk] = saved_global_params[gk];
    }
    if (global_params.server_url) SERVER_URL = global_params.server_url;
    flog("loaded persisted global_params, server_url=" + SERVER_URL);
}

/*________________________________________________________________________
/*________________________________________________________________________

            Init routine:
/*________________________________________________________________________
 ________________________________________________________________________*/


// First we get the saved params from Max (in the "scenes_params" dict)
var all_clips_params = JSON.parse(max_scenes_params.stringify());
//post(JSON.stringify(all_clips_params), "\n");

// LiveAPI objects, forward-declared here so functions elsewhere in the file
// can reference/reassign them; actually constructed in init_live_api()
// below, not immediately at script load.
var live_set, scenes, tracks, ts_num, ts_den, clip_len, track_mute,
    detail_clip, selected_scene, selected_track, set_view;

// Reading scene/track lists (and registering the selection observers)
// immediately at script-load time is a well-known Max for Live gotcha --
// the device isn't always fully attached to Live's API yet at that exact
// moment, so live_set.get("scenes")/("tracks") and observer registration
// can silently fail (symptom: LiveAPI's own "get: no valid object set"
// console error and garbage return values like 5e-324, and observer
// callbacks that never fire since they were registered too early).
// live.thisdevice -> deferlow -> "init" (in the main patcher) covers
// the device's *first* load, but a [js] object re-instantiated later in
// the same session (e.g. deleting/retyping it, or any other trigger of a
// fresh script load after the device has been running a while) can hit
// this same race on its own, independent of live.thisdevice, which only
// bangs once. So this still retries with a short delay (via Max's Task
// primitive) instead of assuming the first attempt worked -- belt and
// suspenders with the patch-level fix, not a replacement for it.
function init_live_api(attempt){
    attempt = attempt || 1;

    live_set = new LiveAPI("live_set");
    if (!live_set) post("no api object for set\n");
    scene_ids = strip_ids(live_set.get("scenes"));
    track_ids = strip_midi(strip_ids(live_set.get("tracks")));
    debug && flog("init_live_api: attempt=" + attempt + " scene_ids=" + JSON.stringify(scene_ids) + " track_ids=" + JSON.stringify(track_ids));

    if (scene_ids.length === 0 && track_ids.length === 0 && attempt < 15) {
        var retryTask = new Task(function(){ init_live_api(attempt + 1); }, this);
        retryTask.schedule(300);
        return;
    }
    if (scene_ids.length === 0 && track_ids.length === 0) {
        flog("init_live_api: giving up after " + attempt + " attempts -- Live API never returned a scene/track list");
    }

    // If Max’s dict for scenes_params is empty we init it with default values:
    if ( JSON.stringify(max_global_params) == "{}" || all_clips_params.scenes.length == 0) {
        debug && post("scenes params empty at init — building default params ", "\n");
        all_clips_params.scenes = [];
        init_clips_params();
    }

    // We set up callbacks to be informed when tracks or scenes are added, moved, removed:
    // This creates callbacks and triggers them:
    scenes = new LiveAPI(scenes_changed, "live_set");
        if (!scenes) post("no api object for scenes\n");
        scenes.property = "scenes";

    tracks = new LiveAPI(tracks_changed, "live_set");
        if (!tracks) post("no api object for tracks\n");
        tracks.property = "tracks";

    // Callbacks for the clip signature/length info

    ts_num = new LiveAPI(numerator_changed);
        ts_num.property = "signature_numerator";

    ts_den = new LiveAPI(denominator_changed);
        ts_den.property = "signature_denominator";

    clip_len = new LiveAPI(length_changed);
        clip_len.property = "end_time";

    // Callbacks for the clip signature/length info

    track_mute = new LiveAPI(track_muted);
        track_mute.property = "mute";

    // Then we set up callbacks to be notified anytime the selection changes:

    detail_clip = new LiveAPI(clip_edited, "live_set view");
        if (!detail_clip)  post("no api object for detail_clip\n");
        detail_clip.property = "detail_clip";

    selected_scene = new LiveAPI(scene_selected, "live_set view");
        if (!selected_scene)  post("no api object for selected_scene\n");
        selected_scene.property = "selected_scene";

    selected_track = new LiveAPI(track_selected, "live_set view");
        if (!selected_track) post("no api object for selected_track\n");
        selected_track.property = "selected_track";

    set_view = new LiveAPI("live_set view");
        if (!set_view)  post("no api object for set view\n");

    flog("init_live_api: observers registered (attempt " + attempt + ")");
    schedule_panel();

    // The selected_scene/selected_track observers only fire on a future
    // CHANGE -- binding .property above does not itself invoke the
    // callback with whatever's already selected. Without this, current_
    // scene/current_track stay at their -1 default until the user
    // reselects a track/scene.
    // Seed them here by feeding the current selection through the same
    // scene_selected()/track_selected() handlers the observers use.
    // Deferred one tick (Task w/ 0ms) rather than done inline: this whole
    // function can still be mid-retry when track_ids/scene_ids just barely
    // came back non-empty, and the wider Live API (set_view, clip_slots,
    // etc.) is not necessarily equally ready yet -- an exception here must
    // not be allowed to propagate up through this top-level script call,
    // since that would silently abort everything scheduled after
    // init_live_api() at file-load time (status display, /info, /models,
    // health polling).
    var seedTask = new Task(function(){
        try {
            var init_sel_scene = set_view.get("selected_scene");
            debug && flog("init_live_api: seedTask init_sel_scene=" + JSON.stringify(init_sel_scene));
            if (init_sel_scene && init_sel_scene[1] !== undefined)
                scene_selected(["selected_scene", "id", init_sel_scene[1]]);
            var init_sel_track = set_view.get("selected_track");
            debug && flog("init_live_api: seedTask init_sel_track=" + JSON.stringify(init_sel_track));
            if (init_sel_track && init_sel_track[1] !== undefined)
                track_selected(["selected_track", "id", init_sel_track[1]]);
            // The clip observers fired before the scene/track above were
            // known, so their length was dropped (n_bars stayed 0 until
            // another clip was clicked). Ask them again now.
            if (+clip_len.id) {
                ts_num.property = "signature_numerator";
                ts_den.property = "signature_denominator";
                clip_len.property = "end_time";
            }
            schedule_panel();
        } catch(e) {
            flog("init_live_api: initial selection seed failed: " + e);
        }
    }, this);
    seedTask.schedule(50);
}

// Fetch capabilities/resolution once at load -- build_request()/bang()
// refuse to generate until this has succeeded at least once.

// Periodic health polling, so the panel's server light follows the real
// server state. Self-reschedules after each
// check completes (success or failure) rather than using a fixed
// interval, so a slow/timed-out check can't stack up overlapping polls.
var HEALTH_POLL_MS = 15000;
var health_task = null;
var health_misses = 0;      // polls in a row the server didn't answer: back off 15 -> 30 -> 60 s

function schedule_health_poll(){
    if (device_deleted) return;
    if (!health_task) health_task = new Task(function(){
        http_health(function(ok){ health_misses = ok ? 0 : health_misses + 1; schedule_health_poll(); });
    }, this);
    health_task.schedule(HEALTH_POLL_MS * Math.min(4, Math.pow(2, health_misses)));
}

// HTTP goes through the Node helper, not Max's XMLHttpRequest: a reply that
// arrives after the device is deleted (closing or switching sets, removing the
// device) is delivered by Max's XMLHttpRequest to the freed js object and
// crashes Live, even after abort(). A reply from node.script to a deleted
// device is simply dropped.
//
// NodeRequest has the part of the XMLHttpRequest interface used here. Bodies
// and replies travel in chunks, each prefixed with "|" so Max never turns a
// chunk that looks like a number into one.
var HTTP_CHUNK = 16000;   // under Max's ~32k-character message argument (the helper uses the same)
var http_seq = 0;
var http_pending = {};      // id -> NodeRequest
var node_ready = false;     // set by the helper's config_ready
var node_queue = [];        // messages for the helper sent before it was running
var device_deleted = false;

function to_node(msg){
    if (node_ready) outlet(OUT_NODE, msg);
    else node_queue.push(msg);
}

function node_started(){
    var first = !node_ready;
    if (first) flog("node helper ready, " + node_queue.length + " queued message(s)");
    node_ready = true;
    var q = node_queue;
    node_queue = [];
    for (var i = 0; i < q.length; i++) outlet(OUT_NODE, q[i]);
    if (first && !device_deleted) { http_info(); http_models(); schedule_health_poll(); }
}

function NodeRequest(){
    this.readyState = 0;
    this.status = 0;
    this.responseText = "";
    this.timeout = 0;
    this.onreadystatechange = null;
    this.ontimeout = null;
    this._method = "GET";
    this._url = "";
    this._id = null;
    this._chunks = [];
}
NodeRequest.prototype.open = function(method, url){ this._method = method; this._url = url; this.readyState = 1; };
NodeRequest.prototype.setRequestHeader = function(){};   // the helper sends bodies as application/json
NodeRequest.prototype.send = function(body){
    var id = "h" + (++http_seq);
    this._id = id;
    http_pending[id] = this;
    body = body ? String(body) : "";
    var n = Math.ceil(body.length / HTTP_CHUNK);
    for (var i = 0; i < n; i++) to_node(["http_body", id, i, "|" + body.substr(i * HTTP_CHUNK, HTTP_CHUNK)]);
    to_node(["http_send", id, this._method, this._url, this.timeout || 0, n, this.dump ? "|" + this.dump : "|"]);
};
NodeRequest.prototype.abort = function(){
    if (!this._id || !http_pending[this._id]) return;
    delete http_pending[this._id];
    to_node(["http_abort", this._id]);
};

function new_request(){ return new NodeRequest(); }

// http_chunk <id> <i> <|text>, then http_done <id> <status> <chunks>, or http_timeout <id>;
// a streamed reply also sends http_event <id> <|json> per progress frame
function handle_http(a){
    var req = http_pending[a[1]];
    if (!req) return;
    if (a[0] == "http_chunk") { req._chunks[+a[2]] = String(a[3]).substr(1); return; }
    if (a[0] == "http_event") {
        if (req.onevent) { try { req.onevent(JSON.parse(String(a[2]).substr(1))); } catch (e) { flog("http_event: " + e); } }
        return;
    }
    delete http_pending[a[1]];
    req.readyState = 4;
    if (a[0] == "http_timeout") {
        if (req.ontimeout) req.ontimeout();
        else if (req.onreadystatechange) req.onreadystatechange();
        return;
    }
    req.status = +a[2];
    req.responseText = req._chunks.slice(0, +a[3]).join("");
    req._chunks = [];
    if (req.onreadystatechange) req.onreadystatechange();
}

// Called by Max when the js object is deleted: stop the timers that would
// otherwise call back into it.
function notifydeleted(){
    device_deleted = true;
    var tasks = [health_task, _log_flush_task, tag_task, dict_sync_task, status_revert_task, panel_task, tag_change_task];
    for (var i = 0; i < tasks.length; i++) if (tasks[i]) tasks[i].cancel();
    // A generation in flight would keep the server busy (up to its 5-minute timeout) and its socket open in the
    // helper: cancel it on the server and drop every request. Replies to a deleted device are dropped by node.script.
    try {
        if (active_generation && !active_generation.cancel_sent) http_cancel();
        for (var id in http_pending) if (node_ready) outlet(OUT_NODE, "http_abort", id);
    } catch (e) {}
    http_pending = {};
}

// Entry point, sent once by live.thisdevice -> deferlow -> "init" when the
// device is fully attached to Live. This used to be a "compile" message,
// which re-ran the whole script on every load (so everything was set up
// twice -- once at instantiation, once on recompile). Top-level code now
// only declares state; anything that touches the Live API or the network
// starts here. Guarded so a duplicate "init" is harmless.
var initialized = false;

// Re-derive everything that depends on where the device lives.
function resolve_paths(patcher){
    DEVICE_DIR = compute_device_dir(patcher) || DEVICE_DIR;
    var root = compute_root(patcher);
    if (!root || root === ROOT) return;
    ROOT = root;
    if (file_exists(root_path(".midigpt_dev"))) debug = DEV_MODE = true;
    _logfile = root_path("midigpt.log");
}

function init(){
    if (initialized) return;
    initialized = true;
    resolve_paths(this.patcher);
    flog("init: ROOT=" + ROOT + " dev=" + DEV_MODE);
    schedule_panel();
    outlet(OUT_NODE, "hello");   // the helper answers with config_ready (it may have started before this script)
    init_live_api();
    // /info, /models and the health poll start in node_started(): the saved server address arrives from the
    // helper first (config server_url ...), so they never go to the default address and then again.
}

/*________________________________________________________________________

            Server info / capabilities:
 ________________________________________________________________________*/

var server_latency_ms = -1;

// The panel is told only when what it shows changes: the light, or the latency step it displays.
function health_result(ok, latency){
    var changed = ok !== server_online || latency_shown(latency) !== latency_shown(server_latency_ms);
    server_online = ok;
    server_latency_ms = latency;
    if (changed) schedule_panel();
}

function http_health(on_done){
    debug && flog("http_health: GET " + SERVER_URL + "/health");
    var req = new_request();
    var t0 = Date.now();
    req.open("GET", SERVER_URL + "/health", true);
    req.timeout = 10000;
    req.ontimeout = function(){ flog("http_health: TIMEOUT"); health_result(false, -1); on_done && on_done(false); };
    req.onreadystatechange = function(){
        if (req.readyState === 4) {
            var ok = req.status === 200;
            debug && flog("http_health: " + (ok ? "ok" : ("failed " + req.status)));
            health_result(ok, ok ? Date.now() - t0 : -1);
            on_done && on_done(ok);
        }
    };
    req.send();
}

function http_info(on_done){
    flog("http_info: GET " + SERVER_URL + "/info");
    var req = new_request();
    req.open("GET", SERVER_URL + "/info", true);
    req.timeout = 10000;
    req.ontimeout = function(){ flog("http_info: TIMEOUT"); server_online = false; schedule_panel(); on_done && on_done(false); };
    req.onreadystatechange = function(){
        if (req.readyState === 4) {
            if (req.status === 200) {
                try {
                    server_info = JSON.parse(req.responseText);
                } catch(e) {
                    flog("http_info: parse error " + e);
                    server_online = false;
                    schedule_panel();
                    on_done && on_done(false);
                    return;
                }
                server_online = true;
                server_capabilities = server_info.capabilities || {};
                server_resolution = server_info.resolution || server_resolution;
                server_scale_presets = server_capabilities.pitch_mask_scale_presets || server_scale_presets;
                server_grid_units = server_capabilities.rhythm_mask_grid_units || server_grid_units;
                flog("http_info: OK checkpoint=" + server_info.checkpoint + " resolution=" + server_resolution);
                schedule_panel();
                on_done && on_done(true);
            } else {
                flog("http_info: ERROR " + req.status);
                server_online = false;
                schedule_panel();
                on_done && on_done(false);
            }
        }
    };
    req.send();
}

// Available checkpoints (GET /models), for the ENGINE page's model picker.
var server_models = [];
var server_default_model = "";

function http_models(on_done){
    flog("http_models: GET " + SERVER_URL + "/models");
    var req = new_request();
    req.open("GET", SERVER_URL + "/models", true);
    req.timeout = 10000;
    req.ontimeout = function(){ flog("http_models: TIMEOUT"); on_done && on_done(false); };
    req.onreadystatechange = function(){
        if (req.readyState === 4) {
            if (req.status === 200) {
                try {
                    var data = JSON.parse(req.responseText);
                    server_models = data.models || [];
                    server_default_model = data.default_model || "";
                } catch(e) {
                    flog("http_models: parse error " + e);
                    on_done && on_done(false);
                    return;
                }
                // Only apply the server's default the first time (no
                // selection made yet) -- don't clobber a user's explicit
                // choice on a later refresh.
                if (!global_params.model && server_default_model) {
                    global_params.model = server_default_model;
                    max_global_params.parse(JSON.stringify(global_params));
                }
                flog("http_models: OK " + server_models.length + " models, default=" + server_default_model);
                schedule_panel();
                on_done && on_done(true);
            } else {
                flog("http_models: ERROR " + req.status);
                on_done && on_done(false);
            }
        }
    };
    req.send();
}

// Effective model_dim right now, respecting Auto mode (highest option for
// the current checkpoint) -- used to build the request (see build_config()).
function array_max(arr){
    var m = arr[0];
    for (var i = 1; i < arr.length; i++) if (arr[i] > m) m = arr[i];
    return m;
}

// maxAvailableBars (optional): the actual bar count Auto mode should fit
// within -- model_dim is a fixed generation WINDOW, not a required exact
// score length (confirmed against the live server: a 6-bar score with
// model_dim=4 completes fine, the model just slides its 4-bar window
// across it). The only real constraint is score bars >= model_dim, so
// Auto should pick the largest option that still fits, not just the
// largest option that exists overall -- e.g. a 6-bar clip should get
// model_dim=4, not 8, even though 8 is a valid option for this checkpoint
// in general. Only applied in Auto mode; an explicit manual choice is
// left as the user's own responsibility (build_request() separately
// refuses to generate if it doesn't fit, rather than silently overriding
// a deliberate choice).
function effective_model_dim(maxAvailableBars){
    var opts = model_dim_options();
    if (global_params.model_dim_auto) {
        if (typeof maxAvailableBars === "number" && isFinite(maxAvailableBars)) {
            var fitting = [];
            for (var i = 0; i < opts.length; i++) if (opts[i] <= maxAvailableBars) fitting.push(opts[i]);
            if (fitting.length) return array_max(fitting);
        }
        return array_max(opts);
    }
    if (opts.indexOf(global_params.model_dim) === -1) return opts[0];
    return global_params.model_dim;
}



/*________________________________________________________________________

            Max messages management:
 ________________________________________________________________________*/

function bang(){
    flog("bang: scene=" + current_scene + " track=" + current_track);
    if (active_generation) {
        flog("bang: generation already in flight, ignoring");
        report_status("busy");
        return;
    }
    if (!server_online) {
        flog("bang: server not reachable, refusing to generate");
        report_error("server offline -- run Refresh once it's reachable");
        return;
    }
    if (build_request()){
        capture_write_ctx();
        schedule_dict_sync();
        http_generate();
    }
}

/*________________________________________________________________________

            Beat -> tick conversion for our OWN outgoing score
            (SCORE_RESOLUTION, NOT server_resolution -- see the comment
            on SCORE_RESOLUTION above):
 ________________________________________________________________________*/

function beats_to_ticks(beats){
    return Math.round(beats * SCORE_RESOLUTION);
}

/*________________________________________________________________________

            Generation request/response lifecycle:
 ________________________________________________________________________*/

// No crypto/uuid in Max's js engine -- this only needs to be unique enough
// for cancel-correlation and log-grepping, not cryptographically unique.
function make_request_id(){
    return Date.now().toString(16) + "-" + Math.floor(Math.random()*0xffffff).toString(16)
         + "-" + Math.floor(Math.random()*0xffffff).toString(16);
}

// {request_id, started_at, cancel_sent} while a generation is in flight, else null.
var active_generation = null;

// Snapshot of what a response should be written into, captured at request
// time rather than read live -- an async response (or a later candidate
// swap) must never write into whatever happens to be selected *now*.
var last_write_ctx = null;

function capture_write_ctx(){
    last_write_ctx = {
        write_track_nrs: write_track_nrs.slice(),
        write_clip_ids: write_clip_ids.slice(),
        max_loop_start: write_max_loop_start,
        original: write_original.slice(),
        current_scene: current_scene,
        // per target track: the bars it asked the server to generate (the only bars written back)
        gen_bars: (function () {
            var m = {};
            for (var i = 0; i < midigptRequest.tracks.length; i++) m[midigptRequest.tracks[i].id] = midigptRequest.tracks[i].bars.slice();
            return m;
        })()
    };
}

function http_generate(){
    var request_id = make_request_id();
    var req = new_request();
    active_generation = { request_id: request_id, started_at: Date.now(), cancel_sent: false, xhr: req };

    report_status("generating");
    req.open("POST", SERVER_URL + "/generate", true);
    req.timeout = 300000;
    req.setRequestHeader("Content-Type", "application/json");
    req.ontimeout = function(){
        flog("[" + request_id + "] TIMEOUT after " + (Date.now() - active_generation.started_at) + "ms");
        active_generation = null;
        panel_fault("NO REPLY", "SERVER DID NOT ANSWER", "RETRY \u00b7 CHECK SERVER");
        report_error("Request timed out.");
    };
    req.onevent = panel_generation_progress;   // streamed: new notes and token progress while it runs
    req.onreadystatechange = function(){
        if (req.readyState === 4) {
            if (req.status === 200) {
                var result = JSON.parse(req.responseText);
                // the full response is in <request_id>.resp.json next to the request (dev mode; see dump_prefix())
                debug && flog("[" + request_id + "] RESPONSE 200 (" + (Date.now() - active_generation.started_at) + "ms, " + req.responseText.length + " chars)");
                debug && log_reproduce_hint(request_id, result);
                handle_generate_response(result);
            } else {
                flog("[" + request_id + "] RESPONSE ERROR " + req.status + " (" + (Date.now() - active_generation.started_at) + "ms): " + req.responseText);
                error("MIDI-GPT error " + req.status + ": " + req.responseText + "\n");
                active_generation = null;
                panel_fault_http(req.status, req.responseText);
                report_error("MIDI-GPT error " + req.status + ": " + req.responseText);
            }
        }
    };
    // model is a top-level field on the POST body (sibling to score/
    // request/request_id/stream), confirmed via the live server's own
    // /openapi.json schema (_GenerateBody.model) -- NOT inside
    // request.config. Omitted entirely when unset so the server just
    // uses its own default_model.
    // A single generation streams (progress for the stats screen); the server streams only one candidate.
    var body = {
        score: midigptScore,
        request: midigptRequest,
        request_id: request_id,
        stream: (midigptRequest.config.num_candidates || 1) <= 1
    };
    if (global_params.model) body.model = global_params.model;
    // In dev mode the full body (and the reply) are written by the Node helper to <request_id>.req.json /
    // .resp.json: enough to replay a request byte-for-byte (curl -d @file). Max messages cut a log line at ~32k.
    var text = JSON.stringify(body);
    if (debug) {
        req.dump = dump_prefix(request_id);
        flog("[" + request_id + "] REQUEST POST " + SERVER_URL + "/generate (" + text.length + " chars) -> " + req.dump + ".req.json");
    }
    req.send(text);
}

// Server-picked seeds (config.seed omitted / seed_auto on) only exist in the
// response, never the request -- without pulling them back out and pairing
// them with the request that was actually sent, a "random" result can never
// be reproduced. Logs a body that's the original request with .config.seed
// pinned to whatever the server chose, ready to paste straight back at
// POST /generate for an identical rerun.
function log_reproduce_hint(request_id, result){
    var seeds = [];
    if (result && result.candidates) {
        for (var i = 0; i < result.candidates.length; i++) {
            if (result.candidates[i] && typeof result.candidates[i].seed !== "undefined") seeds.push(result.candidates[i].seed);
        }
    } else if (result && typeof result.seed !== "undefined") {
        seeds.push(result.seed);
    } else if (result && typeof result.base_seed !== "undefined") {
        seeds.push(result.base_seed);
    }
    if (!seeds.length) return;
    // the request body is in <request_id>.req.json: set request.config.seed to this to rerun it exactly
    flog("[" + request_id + "] REPRODUCE seed(s)=" + JSON.stringify(seeds) + ": " + dump_prefix(request_id) + ".req.json with request.config.seed=" + seeds[0]);
}

// Cooperative cancellation: POST /generate/{id}/cancel on its own async
// request (a slow/unreachable server can't freeze this either). Cancellation
// takes effect at the server's next token-step boundary, so the ORIGINAL
// /generate XHR is left running and resolves normally with
// status:"cancelled" (partial score) -- handled by handle_generate_response.
// We do NOT locally abort() the original request: doing so would throw away
// whatever partial result the server was about to send back.
function http_cancel(){
    if (!active_generation || active_generation.cancel_sent) return;
    active_generation.cancel_sent = true;
    var request_id = active_generation.request_id;

    flog("http_cancel: POST " + SERVER_URL + "/generate/" + request_id + "/cancel");
    report_status("cancelling");

    var req = new_request();
    req.open("POST", SERVER_URL + "/generate/" + request_id + "/cancel", true);
    req.timeout = 10000;
    req.setRequestHeader("Content-Type", "application/json");
    req.onreadystatechange = function(){
        if (req.readyState === 4) {
            // 404 just means it already finished -- benign either way.
            flog("http_cancel: response " + req.status);
        }
    };
    req.ontimeout = function(){ flog("http_cancel: TIMEOUT"); };
    req.send("{}");
}

function handle_generate_response(result){
    var status = result.status || "completed";
    panel_generation_done(result);
    flog("handle_generate_response: status=" + status);

    if (status === "cancelled" && !result.score && !result.candidates) {
        flog("handle_generate_response: cancelled with nothing generated");
        active_generation = null;
        report_status("cancelled");
        return;
    }

    if (result.candidates) {
        handle_batch_response(result);
    } else {
        if (!result.score) {
            flog("handle_generate_response: no score in response");
            active_generation = null;
            report_error("Server response had no score.");
            return;
        }
        flog("handle_generate_response: seed=" + result.seed
            + " timing=" + JSON.stringify(result.timing)
            + " tokens=" + JSON.stringify(result.tokens));
        write_score_to_clips(result.score, last_write_ctx);
    }

    active_generation = null;
    report_status(status === "cancelled" ? "cancelled" : "done");
}

// Set after a num_candidates>1 generation completes -- lets select_candidate()
// re-write a different candidate's score with zero network calls, since all
// candidates already arrived in the one /generate response. Cleared (old
// candidates simply forgotten) the moment a new generation starts or the
// user's selection changes -- see clear_generation_state().
var last_generation = null;

function handle_batch_response(result){
    var candidates = result.candidates || [];
    var selected = -1;
    for (var i = 0; i < candidates.length; i++) {
        if (candidates[i].score) { selected = i; break; }
    }
    flog("handle_batch_response: " + candidates.length + " candidates, selected=" + selected);

    last_generation = {
        candidates: candidates,
        base_seed: result.base_seed,
        summary: result.summary,
        selected: selected,
        ctx: last_write_ctx
    };

    // what the clips held when GENERATE was pressed (the selected take, if a batch was showing), read with the
    // request; not read again here, so a take switched to while generating isn't mistaken for the original
    last_generation.original = last_write_ctx && last_write_ctx.original ? last_write_ctx.original : snapshot_targets(last_write_ctx);
    if (selected >= 0) write_score_to_clips(candidates[selected].score, last_write_ctx);
    schedule_panel();
}

// The panel's take picker. No-ops on an invalid index or a failed candidate (score == null); a stale swap must never silently
// write into the wrong clip.
function select_candidate(idx){
    idx = +idx;
    if (!last_generation) { flog("select_candidate: no active batch"); return; }
    var candidates = last_generation.candidates;
    if (idx < 0 || idx >= candidates.length) { flog("select_candidate: index out of range " + idx); return; }
    if (!candidates[idx].score) { flog("select_candidate: candidate " + idx + " has no score (failed)"); return; }

    write_score_to_clips(candidates[idx].score, last_generation.ctx);
    last_generation.selected = idx;
    flog("select_candidate: switched to " + idx + " (seed " + candidates[idx].seed + ")");
    schedule_panel();
}

// Invalidates the active batch on scene/track selection change or clip
// edit -- a swap after the user has moved on must never write into the
// wrong clip. Losing the picker on selection change is the deliberate,
// safe tradeoff.
function clear_generation_state(){
    if (last_generation) {
        flog("clear_generation_state: selection changed, forgetting batch");
        last_generation = null;
        schedule_panel();
    }
}

function write_score_to_clips(score, ctx){
    ctx = ctx || last_write_ctx;
    if (!ctx) { flog("write_score_to_clips: no write context captured, aborting"); return; }
    // Confirmed with the server side: score.resolution (not /info's
    // server_resolution, a different and unrelated value -- the
    // tokenizer's token grid) governs note ticks in every score body.
    // Always read it fresh per response; SCORE_RESOLUTION is only a
    // fallback for the unlikely case a response omits the field entirely.
    var res = score.resolution || SCORE_RESOLUTION;
    flog("write_score_to_clips: response resolution=" + res + " tracks=" + JSON.stringify(Object.keys(score.tracks)) + " write_track_nrs=" + JSON.stringify(ctx.write_track_nrs));
    for (var t in score.tracks) {
        var track_nr = ctx.write_track_nrs.indexOf(t);
        flog("  track t=" + t + " (type=" + typeof t + ") track_nr=" + track_nr + " clip_id=" + ctx.write_clip_ids[track_nr]);
        if (track_nr < 0) { flog("  -> skipping (not a generation target)"); continue; }
        var scoreBars = score.tracks[t].bars;
        var clip = new LiveAPI();
        clip.id = ctx.write_clip_ids[track_nr];
        if (!+clip.id) { flog("  -> skipping (no clip id)"); continue; }
        // the meter is in the reply (every bar carries it); the clip is asked only if it isn't
        var b0 = scoreBars[0] || {};
        var bar_len = b0.ts_numerator && b0.ts_denominator ? b0.ts_numerator / b0.ts_denominator * 4
                    : clip.get("signature_numerator")[0] / clip.get("signature_denominator")[0] * 4;
        var total_beats = bar_len * scoreBars.length;
        // Only the bars this track asked to generate are written, so context stays exactly as it was whatever
        // the server returns for it (servers before MIDI-GPT PR #11 could move a context bar's downbeat).
        // Adjacent bars are cleared in one call.
        var genBars = ctx.gen_bars && ctx.gen_bars[+t] ? ctx.gen_bars[+t].slice().sort(function (x, y) { return x - y; }) : null;
        if (genBars) {
            for (var gb = 0; gb < genBars.length; ) {
                var run = 1;
                while (gb + run < genBars.length && genBars[gb + run] === genBars[gb] + run) run++;
                clip.call("remove_notes_extended", 0, 128, genBars[gb] * bar_len, run * bar_len);
                gb += run;
            }
        } else {
            clip.call("remove_notes_extended", 0, 128, 0, 10000);
        }
        var notes = { notes: [] };
        for (var b in scoreBars) {
            if (genBars && genBars.indexOf(+b) < 0) continue;
            var barNotes = scoreBars[b].notes || [];
            for (var n in barNotes) {
                var sn = barNotes[n];
                debug && flog("  raw note bar=" + b + " " + JSON.stringify(sn));
                // Ticks are divided by this response's own `res` (its
                // score.resolution, read above) -- confirmed with the server
                // side that note ticks are governed per-score-body, never by
                // /info's unrelated server_resolution. Getting this wrong
                // once produced wildly incorrect onset/duration (e.g.
                // onset_ticks=1920 read as ~160 beats instead of 4, since it
                // was divided by 12 -- /info's value -- instead of 480).
                var start = (sn.onset_ticks / res) + bar_len * b;
                var rawDurBeats = sn.duration_ticks / res;
                if (!isFinite(rawDurBeats)) {
                    flog("  WARNING: non-finite duration_ticks=" + sn.duration_ticks + " (raw note above) -- falling back to a quarter note");
                    rawDurBeats = 1;
                }
                var dur = Math.max(bar_len / res, rawDurBeats);
                // clamp note end to clip boundary
                dur = Math.min(dur, total_beats - start);
                debug && flog("  -> start=" + start + " dur=" + dur);
                if (dur <= 0) continue;
                notes.notes.push({
                    pitch: sn.pitch,
                    start_time: start,
                    duration: dur,
                    velocity: sn.velocity
                });
            }
        }
        flog("  writing " + notes.notes.length + " notes to clip " + clip.id + " total_beats=" + total_beats);
        clip.call("add_new_notes", notes);
        // the clip's end once per batch: switching takes writes the same length (and each set is an undo step)
        ctx.ends = ctx.ends || {};
        if (ctx.ends[clip.id] !== total_beats) {
            clip.set("loop_end", total_beats);
            clip.set("end_marker", total_beats);
            ctx.ends[clip.id] = total_beats;
        }
    }
}
// The dicts mirror JS state so it survives a script reload; nothing reads
// them on the hot path. Serializing every scene x track x bar on every
// single click was a major source of lag, so writes are coalesced: any
// number of changes within DICT_SYNC_MS produce one serialization (a knob
// drag is one write, not ten a second).
var DICT_SYNC_MS = 1000;
var dict_sync_pending = false;
var dict_sync_task = new Task(function(){
    dict_sync_pending = false;
    max_scenes_params.parse(JSON.stringify(all_clips_params));
    max_global_params.parse(JSON.stringify(global_params));
}, this);

function schedule_dict_sync(){
    if (dict_sync_pending) return;
    dict_sync_pending = true;
    dict_sync_task.schedule(DICT_SYNC_MS);
}


// Resets Global Options and every track's per-track params to defaults.
// Deliberately leaves server_url untouched -- that's connection config,
// not a generation setting, and wiping it would silently disconnect the
// user from their server (same philosophy as the REAPER dashboard's
// reset, which also left server/instrument setup out of scope).
function reset_all_settings(){
    var keep_url = global_params.server_url;
    global_params = JSON.parse(JSON.stringify(DEFAULT_GLOBAL_PARAMS));
    global_params.server_url = keep_url;
    // model isn't in DEFAULT_GLOBAL_PARAMS meaningfully (it was still ""
    // at script-load time, before http_models() could ever have set it)
    // -- reset to the server's own default instead of blanking it.
    global_params.model = server_default_model || "";
    max_global_params.parse(JSON.stringify(global_params));

    all_clips_params.scenes = [];
    init_clips_params();

    // init_clips_params() just reset every track's n_bars: re-read the current
    // track's clip so its bars come back without a full rescan.
    if (current_track >= 0 && current_scene >= 0 && track_ids[current_track] &&
        all_clips_params.scenes[current_scene] && all_clips_params.scenes[current_scene].tracks[current_track]) {
        var resetTrack = new LiveAPI();
        resetTrack.id = track_ids[current_track];
        var resetSlotId = strip_ids(resetTrack.get("clip_slots"))[current_scene];
        var resetTparams = all_clips_params.scenes[current_scene].tracks[current_track];
        if (resetSlotId) {
            var resetSlot = new LiveAPI();
            resetSlot.id = resetSlotId;
            if (+resetSlot.get("has_clip")) {
                var resetClip = new LiveAPI();
                resetClip.id = +resetSlot.get("clip")[1];
                resetTparams.ts_numerator = resetClip.get("signature_numerator");
                resetTparams.ts_denominator = resetClip.get("signature_denominator");
                // check_clip_length() recomputes n_bars from tparams.length
                resetTparams.length = resetClip.get("end_time");
                check_clip_length(current_scene, current_track);
            }
        }
    }

    schedule_panel();
    flog("reset_all_settings: Global Options and Track Controls reset to defaults (server_url kept)");
    schedule_dict_sync();
}

/*________________________________________________________________________

            Status:
 ________________________________________________________________________*/

// The panel shows the status (and the fault, see panel_fault()).
// Terminal statuses (a one-shot outcome, not an ongoing state) revert to
// idle after a delay; a pending revert is cancelled by the next status.
var last_status = "idle";
var last_error = null;
var STATUS_AUTO_REVERT_MS = 4000;
var TERMINAL_STATUSES = { error: true, done: true, cancelled: true };
var status_revert_task = null;

function report_status(s){
    last_status = s;
    if (s !== "error") last_error = null;
    schedule_panel();

    if (status_revert_task) { status_revert_task.cancel(); status_revert_task = null; }
    if (TERMINAL_STATUSES[s]) {
        status_revert_task = new Task(function(){
            if (last_status === s) report_status("idle");
        }, this);
        status_revert_task.schedule(STATUS_AUTO_REVERT_MS);
    }
}

function report_error(msg){
    flog("report_error: " + msg);
    last_error = msg;
    if (panel_fault_fresh) panel_fault_fresh = false;
    else panel_fault_from_message(msg);
    report_status("error");
}

// The panel's view of the scene (midigpt_panel_link.js) is cached until a
// selection, clip, track or scene change invalidates it.
function invalidate_scene_cache(){ panel_invalidate_scene(); }

// A clip was clicked (or added): its track's row is re-read, not the scene. The clip's path names its track
// ("live_set tracks 3 clip_slots 0 clip"); anything else (an arrangement clip, nothing) refreshes the scene.
var path_api = null;
function invalidate_clip_track(clip_id){
    try {
        if (!path_api) path_api = new LiveAPI();
        path_api.id = clip_id;
        var m = /tracks (\d+) clip_slots/.exec(String(path_api.path));
        if (m) {
            path_api.path = "live_set tracks " + m[1];
            var nr = track_ids.indexOf(+path_api.id);
            if (nr < 0) nr = track_ids.indexOf(String(path_api.id));
            if (nr >= 0) { panel_invalidate_tracks([nr]); return; }
        }
    } catch (e) { flog("invalidate_clip_track: " + e); }
    panel_invalidate_scene();
}

/*________________________________________________________________________

            Parameters:
 ________________________________________________________________________*/

// Type-coerces to match the existing default's type, so booleans/numbers
// arriving as Max 0/1 atoms land correctly.
function set_global_param(key, value){
    if (!(key in global_params)) { flog("set_global_param: unknown key " + key); return; }
    var existing = global_params[key];
    if (typeof existing === "boolean") value = !!value;
    else if (typeof existing === "number") value = +value;
    global_params[key] = value;
    flog("set_global_param: " + key + " = " + value);
    schedule_dict_sync();
}

// A per-track param of track t in the current scene.
function set_track_param(t, key, value){
    t = +t;
    if (current_scene < 0 || !all_clips_params.scenes[current_scene] || !all_clips_params.scenes[current_scene].tracks[t]) {
        flog("set_track_param: no track " + t + " in current scene " + current_scene);
        return;
    }
    var tparams = apply_track_defaults(all_clips_params.scenes[current_scene].tracks[t]);
    if (!(key in tparams)) { flog("set_track_param: unknown key " + key); return; }
    var existing = tparams[key];
    if (typeof existing === "boolean") value = !!value;
    else if (typeof existing === "number") value = +value;
    tparams[key] = value;
    flog("set_track_param: track " + t + " " + key + " = " + value);
    schedule_dict_sync();
    schedule_panel();
}

// The ENGINE page's controls (panel "engine <key> <value>"). *_auto true = Auto; hard limits 0 = off.
function engine_set(key, value){
    var v = +value;
    switch (key) {
        case "model": global_params.model = String(value); schedule_dict_sync(); return;
        case "model_dim": if (v > 0) { set_global_param("model_dim_auto", false); set_global_param("model_dim", v); } else set_global_param("model_dim_auto", true); return;
        case "bars_per_step": if (v > 0) { set_global_param("bars_per_step_auto", false); set_global_param("bars_per_step", v); } else set_global_param("bars_per_step_auto", true); return;
        case "tracks_per_step": if (v > 0) { set_global_param("tracks_per_step_auto", false); set_global_param("tracks_per_step", v); } else set_global_param("tracks_per_step_auto", true); return;
        case "poly_limit": set_global_param("poly_hard_limit_auto", v <= 0); set_global_param("polyphony_hard_limit", Math.max(0, v)); return;
        case "density_limit": set_global_param("density_hard_limit_auto", v <= 0); set_global_param("density_hard_limit", Math.max(0, v)); return;
        case "max_attempts": set_global_param("max_attempts", Math.max(1, v)); return;
        case "novelty": set_global_param("novelty_check", !!v); return;
        case "silence": set_global_param("silence_check", !!v); return;
        case "shuffle": set_global_param("shuffle", !!v); return;
        case "velocity": set_global_param("velocity_enabled", !!v); return;
        case "microtiming": set_global_param("microtiming_enabled", !!v); return;
    }
    flog("engine_set: unknown key " + key);
}

/*________________________________________________________________________

            Takes:
 ________________________________________________________________________*/

// Revert support: the target clips as they were before the first take was
// written (notes with all Live 11 note fields, plus loop/end markers, which
// writing a take changes).
// Uses the Live 11 note API only: the old one (replace_selected_notes etc.)
// makes Live stop and ask the user whether the device may proceed.
function snapshot_targets(ctx){
    var snap = [];
    if (!ctx) return snap;
    for (var i = 0; i < ctx.write_track_nrs.length; i++) {
        var entry = { track: +ctx.write_track_nrs[i], notes: [] };
        try {
            var clipId = +ctx.write_clip_ids[i];
            if (clipId > 0) {
                var clip = new LiveAPI();
                clip.id = clipId;
                entry.clip = clipId;
                entry.loop_end = +clip.get("loop_end")[0];
                entry.end_marker = +clip.get("end_marker")[0];
                var got = JSON.parse(clip.call("get_notes_extended", 0, 128, 0, 100000));
                entry.notes = (got.notes || []).map(function (n) {
                    var c = {};
                    for (var k in n) if (k !== "note_id") c[k] = n[k];
                    return c;
                });
            }
        } catch (e) { flog("snapshot_targets: " + e); }
        snap.push(entry);
    }
    return snap;
}

function restore_original(){
    if (!last_generation || !last_generation.original) return;
    var snap = last_generation.original, ctx = last_generation.ctx;
    for (var i = 0; i < snap.length; i++) {
        try {
            var clipId = snap[i].clip;
            if (!clipId) {      // a new clip: empty it, keep the clip so takes can still be written
                var tr = new LiveAPI();
                tr.id = track_ids[snap[i].track];
                var slot = new LiveAPI();
                slot.id = strip_ids(tr.get("clip_slots"))[ctx.current_scene];
                if (!+slot.get("has_clip")) continue;
                clipId = +slot.get("clip")[1];
            }
            var clip = new LiveAPI();
            clip.id = clipId;
            clip.call("remove_notes_extended", 0, 128, 0, 100000);
            if (snap[i].notes.length) clip.call("add_new_notes", { notes: snap[i].notes });
            if (snap[i].loop_end) clip.set("loop_end", snap[i].loop_end);
            if (snap[i].end_marker) clip.set("end_marker", snap[i].end_marker);
        } catch (e) { flog("restore_original: " + e); }
    }
    last_generation.selected = -1;
    if (ctx) ctx.ends = {};     // the original's ends are back: the next take sets its own again
    flog("restore_original: restored " + snap.length + " clip(s)");
}

// Every message into the script. Split out of anything() so the dev bridge
// can inject the exact same messages.
function anything(){
    handle_message(arrayfromargs(messagename, arguments));
}

function handle_message(a){
    if (a[0] == "panel") panel_message(a);
    else if (a[0] == "server_url") {   // the address field (Enter)
        if (!/^https?:\/\//.test(String(a[1]))) a[1] = "http://" + a[1];
        SERVER_URL = a[1];
        global_params.server_url = a[1];
        schedule_dict_sync();
        save_persisted_server_url();
        flog("server URL set to " + SERVER_URL);
        http_info();
        http_models();
    }
    else if (a[0] == "tag_changed") panel_tag_changed();
    else if (a[0] == "http_chunk" || a[0] == "http_event" || a[0] == "http_done" || a[0] == "http_timeout") handle_http(a);
    else if (a[0] == "config" || a[0] == "config_ready") { if (a[0] == "config_ready") node_started(); handle_config(a); }
    else if (a[0] == "node_error") report_error("MIDI-GPT helper: " + a.slice(1).join(" "));
    else if (a[0] == "refresh") refresh_params_structure();
    else if (a[0] == "cancel") http_cancel();
    else if (a[0] == "set_global_param") set_global_param(a[1], a[2]);
    else if (a[0] == "set_track_param") set_track_param(a[1], a[2], a[3]);
    else if (a[0] == "debug_mode") debug = !!(+a[1]);
    else post("unknown message " + a + "\n");
}

/*________________________________________________________________________

            Dev bridge (tools/bridge.py):
 ________________________________________________________________________*/

// [udpreceive 7474] -> [route /bridge] -> [deferlow] -> "bridge <id> <cmd> ..."
// Replies go out outlet 1 -> [udpsend 127.0.0.1 7475] as
// "/midigpt/reply <id> <seq> <total> <chunk>" -- chunked because macOS caps a
// UDP datagram at ~9 KB. Ignored entirely unless DEV_MODE is on, so a
// shipped device doesn't accept commands from the network.
//   state             -> session/selection/server state + current track params
//   ui                -> value + presentation rect of every named UI widget
//   msg <selector> .. -> same as the UI sending that message to midigpt.js
//   eval <js>         -> evaluate an expression in this script's scope
//   ui_send <path> <msg..> -> send a message to a named widget (path as in
//                        "ui", e.g. main_window/setup_url) -- like clicking it
var BRIDGE_CHUNK = 3000;

function bridge(){
    var a = arrayfromargs(arguments);
    var id = a.shift();
    var cmd = a.shift();
    var result;
    if (!DEV_MODE) {
        // Replies only ever go to 127.0.0.1, so saying why is harmless and
        // makes "no reply" debuggable.
        bridge_reply(id, JSON.stringify({ error: "dev mode off", root: ROOT,
            dev_flag: root_path(".midigpt_dev") }));
        return;
    }
    try {
        if (cmd === "state") result = bridge_state();
        else if (cmd === "ui") result = bridge_ui(this.patcher);
        else if (cmd === "ui_send") result = bridge_ui_send(this.patcher, a);
        else if (cmd === "msg") { handle_message(a); result = "sent"; }
        else if (cmd === "eval") result = eval(a.join(" "));
        else result = { error: "unknown bridge command " + cmd };
    } catch (e) {
        result = { error: "" + e };
    }
    bridge_reply(id, JSON.stringify(result));
}

function bridge_reply(id, text){
    var total = Math.max(1, Math.ceil(text.length / BRIDGE_CHUNK));
    for (var i = 0; i < total; i++)
        outlet(OUT_BRIDGE, "/midigpt/reply", id, i, total, text.substr(i * BRIDGE_CHUNK, BRIDGE_CHUNK));
}

function bridge_state(){
    var tparams = null;
    if (current_scene >= 0 && current_track >= 0 && all_clips_params.scenes[current_scene] &&
        all_clips_params.scenes[current_scene].tracks[current_track])
        tparams = all_clips_params.scenes[current_scene].tracks[current_track];
    return {
        root: ROOT, dev: DEV_MODE, initialized: initialized,
        server_url: SERVER_URL, server_online: server_online,
        last_status: last_status, last_error: last_error,
        generating: !!active_generation,
        current_scene: current_scene, current_track: current_track,
        scene_ids: scene_ids, track_ids: track_ids,
        edit_track: panel_edit_track(),
        global_params: global_params,
        current_track_params: tparams
    };
}

// Calls fn(path, obj) for every named object, descending into
// subpatchers and bpatchers ("p main_window" has no varname, so unnamed
// containers contribute their class name to the path).
function walk_named(patcher, fn){
    function visit(p, prefix){
        p.apply(function(obj){
            var cls = obj.maxclass;
            if (obj.varname) fn(prefix + obj.varname, obj);
            if (cls === "bpatcher" || cls === "patcher") {
                var sub = obj.subpatcher();
                if (sub) visit(sub, prefix + (obj.varname || (cls === "patcher" ? "main_window" : cls)) + "/");
            }
            return true;
        });
    }
    visit(patcher, "");
}

function bridge_ui_send(patcher, a){
    var path = a.shift();
    var target = null;
    walk_named(patcher, function(p, obj){ if (p === path) target = obj; });
    if (!target) return { error: "no widget " + path };
    target.message.apply(target, a);
    return "sent";
}

function bridge_ui(patcher){
    var out = {};
    walk_named(patcher, function(path, obj){
        out[path] = describe_widget(obj);
    });
    return out;
}

function describe_widget(obj){
    var entry = { cls: obj.maxclass };
    try { entry.value = obj.getvalueof(); } catch (e) {}
    try { entry.rect = obj.getattr("presentation_rect"); } catch (e) {}
    try { entry.hidden = obj.hidden; } catch (e) {}
    return entry;
}



/*______________________________________________________________________
 
            Init dict of parameters in Max :
________________________________________________________________________*/

// Backfills any key default_track_params has that tparams is missing --
// needed because a Live set saved before a schema change (new pitch/
// rhythm/remix fields) still has old, shorter per-track Dicts on load.
// Without this, e.g. tparams.pitch_mask_mode is undefined and
// compute_track_controls() either silently no-ops or sends malformed JSON.
function apply_track_defaults(tparams){
    for (var k in default_track_params) {
        if (!(k in tparams)) tparams[k] = default_track_params[k];
    }
    return tparams;
}

// Fast clone of default_track_params -- JSON.parse(JSON.stringify(...))
// was measurably slow when called O(scenes*tracks) times (e.g.
// reset_all_settings() -> init_clips_params() on a real project with many
// scenes/tracks), visibly blocking the UI thread on every Reset press.
// default_track_params is flat except for selected_bars (an array), so a
// manual shallow copy + explicit array copy is correct and far faster
// than a full JSON round-trip.
function clone_track_params(){
    var out = {};
    for (var k in default_track_params) {
        var v = default_track_params[k];
        out[k] = Array.isArray(v) ? v.slice() : v;
    }
    return out;
}

function init_clips_params(){
    for (s in scene_ids){
        all_clips_params.scenes[s] = { tracks: []}
        for (t in track_ids){
            all_clips_params.scenes[s].tracks[t] = clone_track_params();
        }
    }
}

/*________________________________________________________________________

            Scenes management:
 ________________________________________________________________________*/

function scenes_changed(args){
    if (args[0]=="scenes"){
        invalidate_scene_cache();
        var new_ids = [];
        var new_clips_params = { scenes: []};
        var pos, from, i, j;
        var ids = strip_ids(args);
        debug && post("scenes changed - scene ids: ", ids, "\n");
        for (pos in ids) {
            var id = ids[pos];

            search: // for scene id and move, insert or copy it in new list:
            if (scene_ids[pos]!=id){
                for(from in scene_ids)
                    if(scene_ids[from]==id) {
                        move_scene(from, pos); 
                        break search;
                    } // if scene was not found at the end of the loop:
                insert_scene(pos,id)
            } else copy_scene(pos,id);
        } // now check if some scenes have been removed in the process:
        if(new_ids.length<scene_ids.length){ // if so:

            find_missing: //scenes and remove them
            for(i in scene_ids){
                for(j in new_ids)
                    if(new_ids[j]==scene_ids[i])
                        continue find_missing;
                remove_scene(i);
            }
        } // replace old list with new one:
        scene_ids=new_ids;
        all_clips_params = new_clips_params;
        refresh_params_structure();
    }

    function copy_scene(p, i){
        new_ids[p] = i;
        debug && post("copying scene id#", i, "at position #", p, "\n");
        new_clips_params.scenes[p] = all_clips_params.scenes[p];
    }

    function insert_scene(p, i){
        new_ids[p] = i;
        debug && post("inserting scene id#", i, "at position #", p, "\n");
        new_clips_params.scenes[p] = { tracks: []}
    }

    function move_scene(p_from, p_to){
        debug && post("scene moved from #", p_from, "to #", p_to, "\n");
        new_clips_params.scenes[p_to] = all_clips_params.scenes[p_from];
        new_ids[p_to]=scene_ids[p_from];
    }

    function remove_scene(p){
        debug && post("scene #", p, "has been removed", "\n");
        //all_clips_params.scenes[pos] && all_clips_params.scenes.splice(pos, 1);
    }

}

/*________________________________________________________________________

             Track management:
 ________________________________________________________________________*/


function tracks_changed(args){
    // basically the same thing than above with scenes
    // but excluding non-MIDI tracks
    if (args[0]=="tracks"){
        invalidate_scene_cache();
        var new_ids = [];
        var new_clips_params = { scenes: []};
        for(s in scene_ids)
            new_clips_params.scenes[s] = {tracks: []}
        var pos = 0, i, j, from;
        var ids = strip_midi(strip_ids(args));
        debug && post("tracks changed - track ids: ", ids, "\n");
        for (pos in ids) {
            var id = ids[pos];

            search: 
            if (track_ids[pos]!=id){
                for(from in track_ids)
                    if (track_ids[from]==id) {
                        move_track(from, pos); 
                        break search;
                    }
                insert_track(pos, id);   
            } else copy_track(pos, id);
        } 
        
        if(new_ids.length<track_ids.length){

            find_missing:
            for(i in track_ids){
                for(j in new_ids)
                    if (new_ids[j]==track_ids[i]) 
                        continue find_missing;
                remove_track(i);
            }
        }
        track_ids=new_ids;
        all_clips_params = new_clips_params;
        refresh_params_structure();
        schedule_panel();   // track_ids just changed shape
    }

    function copy_track(p, i){
        new_ids[p] = i;
        debug && post("copying track ", p, " with id# ", i, "\n");
        for(s in scene_ids){
            debug && post("copying track #", p, "on scene #", s, "\n");
            new_clips_params.scenes[s].tracks[p] = all_clips_params.scenes[s].tracks[p]
          }
    }

    function insert_track(p, i){
        new_ids[p] = i;
        debug && post("inserting track id#", i, "at position #", p, "\n");
        debug && post(scene_ids.length, "scene ids: ", scene_ids, "\n");
        for(s in scene_ids){
            debug && post("inserting track #", p, "on scene #", s, "\n");
            new_clips_params.scenes[s].tracks[p] =  clone_track_params();
          }
    }

    function move_track(p_from, p_to){
        debug && post("track moved from #", p_from, "to #", p_to, "\n");
        new_ids[p_to]=track_ids[p_from];
        for(s in scene_ids){
            debug && post("moving track #", p_from, "to #", p_to , "on scene #", s, "\n");
            new_clips_params.scenes[s].tracks[p_to] = all_clips_params.scenes[s].tracks[p_from]
          }
    }

    function remove_track(p){
        debug && post("track #", p, "has been removed", "\n");
    }
}

/*______________________________________________________________________
 
            Clips generation parameters:
________________________________________________________________________*/


function refresh_params_structure(){
    var s, t;
    debug && post("refresh_params_structure() - scene_ids: ", scene_ids, "\n");
    debug && post("refresh_params_structure() - track_ids: ", track_ids, "\n");
    for (s in scene_ids){
        (all_clips_params.scenes[s]) || (all_clips_params.scenes[s] = { tracks: []});

        check_tracks: 
        for (t in track_ids){
            if(all_clips_params.scenes[s].tracks[t]==null) {  
                debug && post("track", t, "from scene", s ,"is empty", "\n");
                for(var i in all_clips_params.scenes){
                    if (all_clips_params.scenes[i].tracks[t]) {
                        if (all_clips_params.scenes[i].tracks[t].track_type==11){ 
                            debug && post("track", t, "from scene", i ,"is drums", "\n");
                            debug && post("so set track", t, "from scene", s ,"to drums", "\n");
                            all_clips_params.scenes[s].tracks[t] = clone_track_params();
                            all_clips_params.scenes[s].tracks[t].track_type = 11;
                            continue check_tracks;
                        }
                    }
                }
                debug && post("set track", t, "from scene", s ,"to instrument", "\n");
                all_clips_params.scenes[s].tracks[t] = clone_track_params();
            } else {
                apply_track_defaults(all_clips_params.scenes[s].tracks[t]);
            }
        }
    }
    // We update the dict in Max in case scenes and/or tracks have changed:
    schedule_dict_sync();
}

/*________________________________________________________________________
 
        Scene / track selection management:
 ________________________________________________________________________*/


function scene_selected(args){
    debug && flog("scene_selected: called, args=" + JSON.stringify(args));
    if(args[0] == "selected_scene") {
        var id = args[2];
        current_scene = scene_ids.indexOf(id);
        debug && post("current scene is # ", +current_scene, " with id: ", +id, "\n");
        invalidate_scene_cache();
        clear_generation_state();
        schedule_panel();
    }
}

function track_selected(args){
    debug && flog("track_selected: called, args=" + JSON.stringify(args));
    if(args[0]=="selected_track") {
        var id = args[2];
        var track = new LiveAPI();
        track.id = id;
        if(+track.get("has_midi_input")){
            current_track = +track_ids.indexOf(id);
            current_track_slots = strip_ids(track.get("clip_slots"));
            debug && post("current_track is #", current_track,
                " with id: ", id, "and slots :", current_track_slots, "\n");
            // Retarget the existing mute observer -- creating a new
            // LiveAPI observer on every selection leaked one per click.
            track_mute.id = id;
        } else {
            current_track = -1; current_track_slots = [];
            debug && post("current_track is not a MIDI track", "\n");
        }
        // Selecting a track changes no clip: refresh only that track's instrument (its devices may have changed
        // while it was selected), not the whole scene.
        if (current_track >= 0) panel_invalidate_tracks([current_track], true);
        clear_generation_state();
        schedule_panel();
    }
}

function clip_edited(args){
    if(args[0]=="detail_clip") {
        var id = args[2];
        invalidate_clip_track(id);
        if (id){
            debug && post("clip  #", id, "is detailed ", "\n");
            clear_generation_state();

            // Retarget the three clip observers created once in
            // init_live_api() (re-creating them here leaked 3 observers
            // per clip click, slowing Live down over a session).
            // Re-setting .property after .id fires each callback once with
            // the new clip's value; without it n_bars stays 0 ("empty clip").
            ts_num.id = id;
            ts_num.property = "signature_numerator";
            ts_den.id = id;
            ts_den.property = "signature_denominator";
            clip_len.id = id;
            clip_len.property = "end_time";

            // there's no per-slot has_clip observer: a clip selection is when another track's clip
            // most often just appeared or went, so refresh the panel here too
            schedule_panel();
        } else {
            debug && post("no clip is detailed ", "\n");
            if (current_scene >= 0 && current_track >= 0 &&
                all_clips_params.scenes[current_scene] &&
                all_clips_params.scenes[current_scene].tracks[current_track]) {
                all_clips_params.scenes[current_scene].tracks[current_track].n_bars = 0;
                all_clips_params.scenes[current_scene].tracks[current_track].selected_bars = [];
                schedule_panel();
            }
        }
    }
}

function numerator_changed(args){
    if(args[0]=="signature_numerator") {
        debug && post("numerator changed to ", args[1], "\n");
        if (current_scene < 0 || current_track < 0 || !all_clips_params.scenes[current_scene] || !all_clips_params.scenes[current_scene].tracks[current_track]) return;
        all_clips_params.scenes[current_scene].tracks[current_track].ts_numerator = args[1];
        clip_len.property = "end_time";
        //check_clip_length(current_scene, current_track);
        //schedule_panel();
    } 
}

function denominator_changed(args){
    debug && post("args ", args, "\n");
    if(args[0]=="signature_denominator") {
        debug && post("denominator", args[1], "\n");
        if (current_scene < 0 || current_track < 0 || !all_clips_params.scenes[current_scene] || !all_clips_params.scenes[current_scene].tracks[current_track]) return;
        all_clips_params.scenes[current_scene].tracks[current_track].ts_denominator = args[1]; 
        clip_len.property = "end_time";
        //check_clip_length(current_scene, current_track);
        //schedule_panel();
    } 
}

function length_changed(args){
    if(args[0]=="end_time") {
        if (current_scene < 0 || current_track < 0 || !all_clips_params.scenes[current_scene] || !all_clips_params.scenes[current_scene].tracks[current_track]) return;
        all_clips_params.scenes[current_scene].tracks[current_track].length = args[1]; 
        check_clip_length(current_scene, current_track);
        schedule_panel();
    } 
}

function track_muted(args){
    if(args[0]=="mute") {
        debug && post("mute", args[1],  "\n");  
        /* 
        Maybe we don’t want to correlate mute and ignore, after all ?

        all_clips_params.scenes[current_scene].tracks[current_track].ignore = args[1];
        schedule_panel();
        */
    } 
}

function check_clip_length(s, t){
    if (current_scene < 0 || current_track < 0 || !all_clips_params.scenes[current_scene] || !all_clips_params.scenes[current_scene].tracks[current_track]) return;
    if (!all_clips_params.scenes[s] || !all_clips_params.scenes[s].tracks[t]) return;
    all_clips_params.scenes[current_scene].tracks[current_track].n_bars = Math.ceil(
                all_clips_params.scenes[current_scene].tracks[current_track].length / (
                all_clips_params.scenes[current_scene].tracks[current_track].ts_numerator /
                all_clips_params.scenes[current_scene].tracks[current_track].ts_denominator * 4));
        debug && post("length", all_clips_params.scenes[current_scene].tracks[current_track].length, 
            "-> ", all_clips_params.scenes[current_scene].tracks[current_track].n_bars, " bars", "\n"); 
    var nBars = all_clips_params.scenes[s].tracks[t].n_bars;
    var prevnBars = all_clips_params.scenes[s].tracks[t].selected_bars.length;
    if (prevnBars > nBars) {
        debug && post("nBars", nBars, "with previously", prevnBars, ", removing ", prevnBars - nBars, " bars","\n"); 
        for (var n = prevnBars-1 ; n >= nBars; n--) {
            all_clips_params.scenes[s].tracks[t].selected_bars.pop();    
        }
    } else if (prevnBars < nBars) {
        debug && post("nBars", nBars, "with previously", prevnBars, ", adding ", nBars - prevnBars, " bars","\n"); 
        // the old UI started with every bar selected; the panel starts with none (painting bars is how you pick targets)
        for (var n = prevnBars ; n < nBars; n++) all_clips_params.scenes[s].tracks[t].selected_bars[n] = false;
    }
}


/*______________________________________________________________________
 
            Clip selection management:
________________________________________________________________________*/




/*______________________________________________________________________
 
            Utilities:
________________________________________________________________________*/

function strip_ids(args){
    // args of LiveAPI requests come in the form "request_name id m id n… etc."
    // so we parse out the first element ("request_name") 
    // and subsequent "id" keywords so we only get the id numbers
    // NB: + at the beginning converts the (string) arg to a number
    // so we use that to only retain numbers:
    var res = [];
    for (var e in args) 
        if (+args[e]) res.push(+args[e]);
    return res;
}

var strip_api = null;   // one object, retargeted per track
function strip_midi(all_ids) {
    var res_ids = [];
    if (!strip_api) strip_api = new LiveAPI();
    for (var i = 0; i < all_ids.length; i++) {
        strip_api.id = all_ids[i];
        if (+strip_api.get("has_midi_input")) res_ids.push(all_ids[i]);
    }
    return res_ids;
}

function as_array(v){
    if (v === undefined || v === null) return [];
    return Array.isArray(v) ? v : [v];
}

// Builds TrackPrompt.controls (pitch_mask / rhythm_mask / remix) from a
// track's params. Port of REAPER_midigpt_infill.py's
// _compute_track_controls -- same key names/encodings, so this stays a
// direct mirror of that logic.
function compute_track_controls(tparams){
    var controls = {};

    var pmMode = +tparams.pitch_mask_mode || 0;
    if (pmMode === 1 || pmMode === 2) {
        var pitchMask = {};
        if (pmMode === 1) {
            pitchMask.scale = tparams.pitch_mask_scale || "major";
            pitchMask.root = +tparams.pitch_mask_root || 0;
        } else {
            var bitmask = +tparams.pitch_mask_classes || 0;
            var classes = [];
            for (var pc = 0; pc < 12; pc++) if (bitmask & (1 << pc)) classes.push(pc);
            if (classes.length) pitchMask.pitch_classes = classes;
        }

        var shapeMode = +tparams.pitch_shape_mode || 0;
        if (shapeMode === 1) {
            pitchMask.shape = { type: "uniform", min: +tparams.pitch_shape_min || 0, max: +tparams.pitch_shape_max || 127 };
        } else if (shapeMode === 2) {
            pitchMask.shape = { type: "normal", mean: +tparams.pitch_shape_mean || 60, std: +tparams.pitch_shape_std || 8 };
        }

        if (pitchMask.scale !== undefined || pitchMask.pitch_classes !== undefined) {
            controls.pitch_mask = pitchMask;
        }
    }

    if (!!tparams.remix_enabled) {
        // remix derives its own onset schedule from the reference and is
        // mutually exclusive with rhythm_mask on the same track.
        controls.remix = {
            amount: +tparams.remix_amount || 0,
            mode: (+tparams.remix_mode === 1) ? "full" : "pitch"
        };
    } else if (+tparams.rhythm_on) {
        controls.rhythm_mask = rhythm_mask_for(tparams);
    }

    return controls;
}

// Rhythm units as fractions of a quarter note (the server's GRID_UNIT_FRACTIONS).
var RHYTHM_UNIT_Q = { whole: 4, half: 2, quarter: 1, quarter_triplet: 1 / 3, eighth: 0.5, eighth_triplet: 1 / 6, sixteenth: 0.25, sixteenth_triplet: 1 / 12 };

// EXACT: one onset per lit step, at ticks of the server's resolution (/info), the downbeat always included.
// EXACT on drum tracks needs a server with MIDI-GPT PR #12 (before it, the exact-rhythm forcer never counted
// drum notes and piled them all onto tick 0 of one bar). nino runs it since 2026-10-16.
function rhythm_mask_for(tparams){
    var unit = tparams.rhythm_unit || "sixteenth";
    if (!+tparams.rhythm_exact) return { grid: { unit: unit, strength: +tparams.rhythm_grid_strength || 0 } };
    var res = server_resolution || 12, step = Math.max(1, Math.round(res * (RHYTHM_UNIT_Q[unit] || 0.25)));
    var pat = as_array(tparams.rhythm_pattern), pos = [{ pos: 0, polyphony: Math.max(1, +pat[0] || 1) }];
    for (var i = 1; i < pat.length; i++) if (+pat[i] > 0) pos.push({ pos: i * step, polyphony: +pat[i] });
    return { positions: pos };
}

function build_config(nBarsForFit){
    var effectiveModelDim = effective_model_dim(nBarsForFit);

    // "Auto" mode: bars/step auto = the full current context size;
    // tracks/step auto = every MIDI track currently in the project, so
    // nothing gets excluded regardless of how many tracks exist.
    var effectiveBarsPerStep = global_params.bars_per_step_auto
        ? effectiveModelDim
        : Math.min(global_params.bars_per_step, effectiveModelDim);
    var effectiveTracksPerStep = global_params.tracks_per_step_auto
        ? Math.max(1, track_ids.length)
        : global_params.tracks_per_step;

    var cfg = {
        temperature: global_params.temperature,
        model_dim: effectiveModelDim,
        bars_per_step: effectiveBarsPerStep,
        tracks_per_step: effectiveTracksPerStep,
        shuffle: !!global_params.shuffle,
        mask_mode: server_capabilities.supports_token_mask ? "token" : "attention",
        max_attempts: global_params.max_attempts,
        novelty_check: !!global_params.novelty_check,
        silence_check: !!global_params.silence_check,
        temperature_escalation: global_params.temperature_escalation,
        polyphony_hard_limit: global_params.polyphony_hard_limit,
        density_hard_limit: global_params.density_hard_limit,
        top_p: Math.max(0.05, Math.min(1, +global_params.top_p || 1)),   // the server rejects 0
        top_k: global_params.top_k,
        num_candidates: Math.max(1, Math.min(16, Math.round(global_params.num_candidates || 1)))
    };
    if (!global_params.seed_auto && global_params.seed >= 0) cfg.seed = Math.round(global_params.seed);
    if (+global_params.mask_p > 0) cfg.mask_p = +global_params.mask_p;
    if (+global_params.mask_k > 0) cfg.mask_k = Math.round(+global_params.mask_k);
    return cfg;
}

function panel_is_target(tp){
    if (tp.ignore) return false;
    if (tp.autoregressive) return true;
    var sel = as_array(tp.selected_bars);
    for (var i = 0; i < sel.length; i++) if (sel[i]) return true;
    return false;
}

function build_request(){
    // fix booleans in params dict
    global_params.use_per_track_temperature = !!global_params.use_per_track_temperature;
    global_params.shuffle = !!global_params.shuffle;
    global_params.verbose = !!global_params.verbose;

    var session = new LiveAPI("live_set");
    var bpm = session.get("tempo")[0];

    midigptScore = { resolution: SCORE_RESOLUTION, tempo: Math.round(60000000 / bpm), tracks: [] };
    midigptRequest = {
        tracks: []
        // config is assigned further down, once nBars is known -- see the
        // model_dim-fit guard right after nBars is computed. build_config()
        // needs nBars to pick a fitting model_dim in Auto mode.
    };
    // Top-level request.controls -- omit keys that are off entirely rather
    // than sending false/null, so checkpoints without the relevant tokens
    // (switchable_velocity/microtiming, genre_groups) never see them.
    var reqControls = {};
    if (global_params.velocity_enabled) reqControls.velocity = true;
    if (global_params.microtiming_enabled) reqControls.microtiming = true;
    if (global_params.genre) reqControls.genre = global_params.genre;
    if (reqControls.velocity !== undefined || reqControls.microtiming !== undefined || reqControls.genre !== undefined) {
        midigptRequest.controls = reqControls;
    }

    // Every target track: AR on, or bars painted. A target without a clip in
    // this scene gets one as long as the scene's longest clip.
    var anyTarget = false, sceneBars = panel_scene().bars;
    for (var pt in track_ids) {
        var ptp = scene_tparams(pt);
        if (!ptp || !panel_is_target(ptp)) continue;
        anyTarget = true;
        ptp.n_bars_to_create = sceneBars;   // used when the track has no clip in this scene
    }
    if (!anyTarget) { report_error("Select at least one bar to infill (or enable Autoregressive) before generating."); return false; }

    // One pass over the tracks. The panel's rows already know each track's clip slot and instrument (cached:
    // walking every track's slots and devices again here froze the UI for seconds); what can change between a
    // click and GENERATE is read fresh: whether there is a clip, its meter, loop and notes.
    var sc = panel_scene();
    var max_loop_start = 0, max_unloop_start = 0, max_length = 0, ts_n, ts_d;
    var infos = [], sigs = [], api = new LiveAPI(), t, info;
    for (t = 0; t < track_ids.length; t++) {
        var row = sc.rows[t] || panel_row(t);
        var tp0 = all_clips_params.scenes[current_scene].tracks[t];
        var info = { clip: 0, slot: +row.slot || 0, target: panel_is_target(apply_track_defaults(tp0)) };
        if (!info.slot) {      // not cached (a new scene slot): look it up
            api.id = track_ids[t];
            info.slot = +strip_ids(api.get("clip_slots"))[current_scene] || 0;
        }
        if (info.slot) {
            api.id = info.slot;
            if (+api.get("has_clip")) info.clip = +api.get("clip")[1];
        }
        if (info.clip) {
            api.id = info.clip;
            info.num = +api.get("signature_numerator")[0];
            info.den = +api.get("signature_denominator")[0];
            info.looping = !!(+api.get("looping")[0]);
            info.start = info.looping ? +api.get("loop_start")[0] : +api.get("start_marker")[0];
            info.length = +api.get("end_time")[0];
            if (info.looping) max_loop_start = Math.max(max_loop_start, info.start);
            else max_unloop_start = Math.max(max_unloop_start, info.start);
            if (info.target) {
                // the whole clip once: the notes in the window go to the server, all of them (every Live 11 note
                // field) are the take picker's "original"
                info.loop_end = +api.get("loop_end")[0];
                info.end_marker = +api.get("end_marker")[0];
                var all = (JSON.parse(api.call("get_notes_extended", 0, 128, 0, 100000)).notes || []);
                info.original = all.map(function (n) { var c = {}; for (var k in n) if (k !== "note_id") c[k] = n[k]; return c; });
                info.notes = all.filter(function (n) { return n.start_time >= info.start && n.start_time < info.start + info.length; });
            } else {
                info.notes = JSON.parse(api.call("get_notes_extended", 0, 128, info.start, info.length)).notes || [];
            }
            ts_n = info.num; ts_d = info.den;
        } else {
            ts_n = tp0.ts_numerator; ts_d = tp0.ts_denominator;
            info.length = tp0.n_bars_to_create * (ts_n / ts_d * 4);
        }
        max_length = Math.max(max_length, info.length);
        sigs.push({ name: row.name, num: ts_n, den: ts_d });
        infos.push(info);
    }
    // test for different time signatures:
    for (t = 1; t < sigs.length; t++){
        if (sigs[t-1].num != sigs[t].num || sigs[t-1].den != sigs[t].den) {
            var sig_err = "";
            for (var s2 = 0; s2 < sigs.length; s2++) sig_err += sigs[s2].name + " " + sigs[s2].num + " " + sigs[s2].den + " ";
            report_error("Time signature mismatch across selected clips: " + sig_err);
            return false;
        }
    }

    debug && post("max loop start: ", max_loop_start, "/ max unloop start: ", max_unloop_start, " / max length:", max_length, "\n");
    var nBars = max_length / (ts_n / ts_d * 4) ;
    debug && post("-> ", nBars, " bars  -> (", Math.ceil(nBars), "full bars) in ", ts_n, "/", ts_d, "\n");

    midigptRequest.config = build_config(nBars);
    // model_dim is a fixed generation window (minimum score length), not a
    // context cap -- confirmed against the live server, and against real
    // 422s this session ("score has N bars but model_dim=M"). Whether Auto
    // picked something too big (shouldn't happen after the fit-filtering
    // above, but the server's checkpoint could still have changed) or the
    // user manually chose a model_dim bigger than what's available, refuse
    // here with a clear message instead of sending a request guaranteed to
    // fail.
    if (nBars < midigptRequest.config.model_dim) {
        var dimErr = "Not enough bars to generate: " + nBars + " available, need at least model_dim=" + midigptRequest.config.model_dim + ".";
        report_error(dimErr);
        return false;
    }

    debug && post("GENERATING PIECE!!",  "\n");
    write_track_nrs = [];
    write_clip_ids = [];
    write_original = [];
    write_max_loop_start = max_loop_start;
    for (t = 0; t < track_ids.length; t++){
        info = infos[t];
        var tparams = apply_track_defaults(all_clips_params.scenes[current_scene].tracks[t]);

        // The instrument is a track property (the MIDI-GPT Instrument tag), cached with the panel's rows.
        var det = cached_instrument(track_ids[t]);
        var isDrum = det.instrument === TAG_DRUMS;
        var midiProgram = isDrum ? 0 : det.instrument;

        midigptScore.tracks[t] = { track_type: isDrum ? "drum" : "melodic", instrument: midiProgram, bars: [] };

        var autoregressive = !!tparams.autoregressive;
        var ignore_track = !!tparams.ignore;

        // The server rejects AR + ignore on one track: ignore wins.
        if (autoregressive && ignore_track) {
            flog("build_request: track " + t + " had autoregressive+ignore both set, forcing autoregressive off\n");
            autoregressive = false;
        }

        // as_array() fixes Max's handling of single-element arrays stored as scalars:
        var sel_bars = as_array(tparams.selected_bars);

        // A track is a generation target when AR is on or any of its bars is painted;
        // every other track in the scene is context (unless ignored).
        var isTarget = info.target;
        var selectedBars = [];
        for (var b = 0; b < nBars; b++){
            selectedBars[b] = isTarget && (autoregressive || !!sel_bars[b]);
            midigptScore.tracks[t].bars[b] = { ts_numerator: ts_n, ts_denominator: ts_d, future: false, notes: [] };
        }

        if (info.clip) {
            if (isTarget) {
                write_track_nrs.push(t); write_clip_ids.push(info.clip);
                write_original.push({ track: t, clip: info.clip, loop_end: info.loop_end, end_marker: info.end_marker, notes: info.original });
            }
            var tS = info.looping ? max_loop_start : max_unloop_start;
            var bL = (ts_n / ts_d * 4);
            tparams.start_time = info.start;
            tparams.length = info.length;
            if (info.notes.length > 0){
                // A looping clip shorter than the generation window repeats: bars past the loop
                // read from the wrapped-back position (modulo the loop's own bar count).
                var loopBars = Math.max(1, Math.round(info.length / bL));
                for (var k = 0; k < info.notes.length; k++){
                    var note = info.notes[k];
                    var tb = Math.floor((note.start_time - tS) / bL);
                    if (tb < 0 || (info.looping && tb >= loopBars)) continue;   // past the loop: never heard
                    // a looping clip's bar repeats every loopBars bars across the window; else it is played once
                    for (b = tb; b < nBars; b += info.looping ? loopBars : nBars) {
                        midigptScore.tracks[t].bars[b].notes.push({
                            pitch: note.pitch,
                            velocity: note.velocity,
                            onset_ticks: beats_to_ticks(note.start_time - tb * bL - tS),
                            duration_ticks: Math.max(1, beats_to_ticks(note.duration)),
                            delta: 0
                        });
                    }
                }
            } else if (!isTarget) {
                ignore_track = true;   // an empty clip is no context
            }
        } else if (!isTarget) {
            ignore_track = true;       // an empty slot is no context
        } else {
            // a target without a clip: create one as long as the scene
            var newLen = tparams.n_bars_to_create * (ts_n / ts_d * 4);
            api.id = info.slot;
            api.call("create_clip", newLen + max_loop_start);
            var newId = +api.get("clip")[1];
            api.id = newId;
            api.set("loop_start", max_loop_start);
            write_track_nrs.push(t); write_clip_ids.push(newId);
            write_original.push({ track: t, clip: newId, loop_end: +api.get("loop_end")[0], end_marker: +api.get("end_marker")[0], notes: [] });
        }

        // Each bar's notes in time order (Live lists them by pitch): servers before MIDI-GPT PR #11 encode a
        // bar's onsets in listed order and drop the downbeat of an unsorted bar.
        for (var sb = 0; sb < midigptScore.tracks[t].bars.length; sb++) {
            midigptScore.tracks[t].bars[sb].notes.sort(function (a, b) { return a.onset_ticks - b.onset_ticks || a.pitch - b.pitch; });
        }

        // build TrackPrompt for this track:
        var barsToGenerate = [];
        for (var b = 0; b < selectedBars.length; b++) {
            if (selectedBars[b]) barsToGenerate.push(b);
        }
        var attrs = {};
        var densityIdx  = tparams.density;
        var minPolyIdx  = tparams.min_polyphony_q;
        var maxPolyIdx  = tparams.max_polyphony_q;
        var minDurIdx   = tparams.min_note_duration_q;
        var maxDurIdx   = tparams.max_note_duration_q;
        if (densityIdx > 0) attrs["note_density"]      = densityIdx - 1;
        if (minPolyIdx > 0) attrs["min_polyphony"]     = minPolyIdx - 1;
        if (maxPolyIdx > 0) attrs["max_polyphony"]     = maxPolyIdx - 1;
        if (minDurIdx  > 0) attrs["min_note_duration"] = minDurIdx  - 1;
        if (maxDurIdx  > 0) attrs["max_note_duration"] = maxDurIdx  - 1;
        midigptRequest.tracks.push({
            id:            +t,
            bars:          barsToGenerate,
            autoregressive: autoregressive,
            ignore:        ignore_track,
            mask_bars:     [],
            attributes:    attrs,
            // the panel stores masks per track: only tracks being generated send them
            controls:      isTarget ? compute_track_controls(tparams) : {}
        });
    }

    // remix and hard rhythm_mask.positions both require tracks_per_step==1
    // server-side. We only ever emit the soft rhythm_mask.grid (not
    // positions), which has no such requirement, so only remix needs this.
    var anyRemix = false;
    for (var ti = 0; ti < midigptRequest.tracks.length; ti++) {
        var tc = midigptRequest.tracks[ti].controls;
        if (tc && (tc.remix || (tc.rhythm_mask && tc.rhythm_mask.positions))) { anyRemix = true; break; }
    }
    if (anyRemix && midigptRequest.config.tracks_per_step !== 1) {
        flog("build_request: remix active on at least one track -- forcing tracks_per_step=1");
        midigptRequest.config.tracks_per_step = 1;
    }

    return true;
}

var densities = ["DENSITY_ANY", "DENSITY_ONE", "DENSITY_TWO", "DENSITY_THREE", "DENSITY_FOUR", "DENSITY_FIVE", "DENSITY_SIX", "DENSITY_SEVEN", "DENSITY_EIGHT", "DENSITY_NINE", "DENSITY_TEN"];
var durations = ["DURATION_ANY", "DURATION_THIRTY_SECOND", "DURATION_SIXTEENTH", "DURATION_EIGHTH", "DURATION_QUARTER", "DURATION_HALF", "DURATION_WHOLE"];
var polyphony = ["POLYPHONY_ANY", "POLYPHONY_ONE", "POLYPHONY_TWO", "POLYPHONY_THREE", "POLYPHONY_FOUR", "POLYPHONY_FIVE", "POLYPHONY_SIX"];
var instruments = ["no_drums","piano", "chromatic_perc", "organ", "guitar", "bass", "strings", "ensemble", "brass", "reed", "pipe", "synth_lead", "synth_pad", "synth_effects", "ethnic", "percussive", "sound_fx", 
                   "acoustic_grand_piano", "bright_acoustic_piano", "electric_grand_piano", "honky_tonk_piano", "electric_piano_1", "electric_piano_2", "harpsichord", "clavi", "celesta", "glockenspiel", "music_box", "vibraphone", "marimba", "xylophone", "tubular_bells", "dulcimer", "drawbar_organ", "percussive_organ", "rock_organ", "church_organ", "reed_organ", "accordion", "harmonica", "tango_accordion", "acoustic_guitar_nylon", "acoustic_guitar_steel", "electric_guitar_jazz", "electric_guitar_clean", "electric_guitar_muted", "overdriven_guitar", "distortion_guitar", "guitar_harmonics", "acoustic_bass", "electric_bass_finger", "electric_bass_pick", "fretless_bass", "slap_bass_1", "slap_bass_2", "synth_bass_1", "synth_bass_2", "violin", "viola", "cello", "contrabass", "tremolo_strings", "pizzicato_strings", "orchestral_harp", "timpani", "string_ensemble_1", "string_ensemble_2", "synth_strings_1", "synth_strings_2", "choir_aahs", "voice_oohs", "synth_voice", "orchestra_hit", "trumpet", "trombone", "tuba", "muted_trumpet", "french_horn", "brass_section", "synth_brass_1", "synth_brass_2", "soprano_sax", "alto_sax", "tenor_sax", "baritone_sax", "oboe", "english_horn", "bassoon", "clarinet", "piccolo", "flute", "recorder", "pan_flute", "blown_bottle", "shakuhachi", "whistle", "ocarina", "lead_1_square", "lead_2_sawtooth", "lead_3_calliope", "lead_4_chiff", "lead_5_charang", "lead_6_voice", "lead_7_fifths", "lead_8_bass__lead", "pad_1_new_age", "pad_2_warm", "pad_3_polysynth", "pad_4_choir", "pad_5_bowed", "pad_6_metallic", "pad_7_halo", "pad_8_sweep", "fx_1_rain", "fx_2_soundtrack", "fx_3_crystal", "fx_4_atmosphere", "fx_5_brightness", "fx_6_goblins", "fx_7_echoes", "fx_8_sci_fi", "sitar", "banjo", "shamisen", "koto", "kalimba", "bag_pipe", "fiddle", "shanai", "tinkle_bell", "agogo", "steel_drums", "woodblock", "taiko_drum", "melodic_tom", "synth_drum", "reverse_cymbal", "guitar_fret_noise", "breath_noise", "seashore", "bird_tweet", "telephone_ring", "helicopter", "applause", "gunshot", 
                   "drum_0"];
