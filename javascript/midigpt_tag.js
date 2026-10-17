/**
 * Face of the MIDI-GPT Instrument tag device (patchers/MIDI-GPT Instrument.amxd,
 * built by tools/build_tag_device.py): the rendered background (media/panel/
 * midigpt_tag_bg.png), the readout on its screen, and the
 * keys' LED slits. Two live.menus with no background sit on the keys (FAMILY, PROGRAM); the stored
 * parameter is the hidden "Instrument" menu (GM 1-128, or 129 = Drums), which is
 * what midigpt.js reads and writes.
 *
 * In:   instrument <0-128>   the stored parameter's value (128 = drums)
 *       family <0-16>        the FAMILY menu was used
 *       program <0-7>        the PROGRAM menu was used
 * Out:  0 -> Instrument menu (int: set it)
 *       1 -> FAMILY menu ("set n")
 *       2 -> PROGRAM menu ("_parameter_range ...", "set n", "ignoreclick 0|1")
 *       3 -> "tag_changed" (to the main device: [s midigpt_tag_changed])
 */

autowatch = 0;
inlets = 1;
outlets = 4;

mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;

var FAMILIES = ["PIANO", "CHROM PERC", "ORGAN", "GUITAR", "BASS", "STRINGS", "ENSEMBLE", "BRASS", "REED", "PIPE", "SYNTH LEAD", "SYNTH PAD", "SYNTH FX", "ETHNIC", "PERCUSSIVE", "SFX", "DRUMS"];
var PROGRAMS = [
    ["GRAND", "BRIGHT", "ELEC GRAND", "HONKY-TONK", "E.PIANO 1", "E.PIANO 2", "HARPSICHORD", "CLAVI"],
    ["CELESTA", "GLOCKENSPIEL", "MUSIC BOX", "VIBRAPHONE", "MARIMBA", "XYLOPHONE", "TUBULAR BELLS", "DULCIMER"],
    ["DRAWBAR", "PERCUSSIVE", "ROCK", "CHURCH", "REED", "ACCORDION", "HARMONICA", "TANGO ACC"],
    ["NYLON", "STEEL", "JAZZ", "CLEAN", "MUTED", "OVERDRIVE", "DISTORTION", "HARMONICS"],
    ["ACOUSTIC", "FINGER", "PICK", "FRETLESS", "SLAP 1", "SLAP 2", "SYNTH 1", "SYNTH 2"],
    ["VIOLIN", "VIOLA", "CELLO", "CONTRABASS", "TREMOLO", "PIZZICATO", "HARP", "TIMPANI"],
    ["STRINGS 1", "STRINGS 2", "SYN STRINGS 1", "SYN STRINGS 2", "CHOIR AAHS", "VOICE OOHS", "SYNTH VOICE", "ORCH HIT"],
    ["TRUMPET", "TROMBONE", "TUBA", "MUTED TPT", "FRENCH HORN", "SECTION", "SYN BRASS 1", "SYN BRASS 2"],
    ["SOPRANO SAX", "ALTO SAX", "TENOR SAX", "BARI SAX", "OBOE", "ENGLISH HORN", "BASSOON", "CLARINET"],
    ["PICCOLO", "FLUTE", "RECORDER", "PAN FLUTE", "BOTTLE", "SHAKUHACHI", "WHISTLE", "OCARINA"],
    ["SQUARE", "SAW", "CALLIOPE", "CHIFF", "CHARANG", "VOICE", "FIFTHS", "BASS+LEAD"],
    ["NEW AGE", "WARM", "POLYSYNTH", "CHOIR", "BOWED", "METALLIC", "HALO", "SWEEP"],
    ["RAIN", "SOUNDTRACK", "CRYSTAL", "ATMOSPHERE", "BRIGHTNESS", "GOBLINS", "ECHOES", "SCI-FI"],
    ["SITAR", "BANJO", "SHAMISEN", "KOTO", "KALIMBA", "BAGPIPE", "FIDDLE", "SHANAI"],
    ["TINKLE BELL", "AGOGO", "STEEL DRUMS", "WOODBLOCK", "TAIKO", "MELODIC TOM", "SYNTH DRUM", "REVERSE CYM."],
    ["FRET NOISE", "BREATH", "SEASHORE", "BIRD TWEET", "TELEPHONE", "HELICOPTER", "APPLAUSE", "GUNSHOT"]
];
var DRUMS = 128;
var C = { g: [0.784, 0.784, 0.784, 1], c: [1, 1, 1, 1], a: [1, 0.588, 0.275, 1], dim: [1, 1, 1, 0.38], key: [0.478, 0.478, 0.478, 1],
          rule: [1, 1, 1, 0.12], ledOff: [0.165, 0.165, 0.165, 1], led: [0.95, 0.95, 0.95, 1] };
var BOLD = "Ableton Sans Bold";

var inst = 0, fam = 0, prog = 0, lit = -1, ready = false;
var bg = null;
try { bg = new Image("midigpt_tag_bg.png"); if (!bg.size[0]) bg = null; } catch (e) { bg = null; }

function split(i) { fam = i === DRUMS ? 16 : Math.floor(i / 8); prog = i === DRUMS ? 0 : i % 8; }

// the stored value changed (Live loaded the set, MIDI-GPT Setup wrote it, or a menu below set it)
function instrument(v) {
    v = Math.max(0, Math.min(DRUMS, Math.round(v)));
    var changed = !ready || v !== inst;
    inst = v; split(v);
    syncMenus();
    mgraphics.redraw();
    if (changed) { ready = true; outlet(3, "tag_changed"); }
}
function family(f) {
    f = Math.round(f);
    if (f === fam && inst !== DRUMS) return;
    lit = 0;
    outlet(0, f === 16 ? DRUMS : f * 8);
}
function program(p) {
    p = Math.round(p);
    if (fam === 16 || p === prog) return;
    lit = 1;
    outlet(0, fam * 8 + p);
}
function syncMenus() {
    outlet(1, "set", fam);
    if (fam === 16) { outlet(2, "_parameter_range", "—"); outlet(2, "set", 0); outlet(2, "ignoreclick", 1); return; }
    var names = [];
    for (var i = 0; i < 8; i++) names.push((fam * 8 + i + 1) + " " + PROGRAMS[fam][i]);
    outlet(2, ["_parameter_range"].concat(names));
    outlet(2, "set", prog);
    outlet(2, "ignoreclick", 0);
}

// ------------------------------------------------------------------ drawing
function rgba(c) { mgraphics.set_source_rgba(c[0], c[1], c[2], c[3]); }
function textW(s, size, sp) {
    mgraphics.select_font_face(BOLD); mgraphics.set_font_size(size);
    var w = 0;
    for (var i = 0; i < s.length; i++) w += mgraphics.text_measure(s.charAt(i))[0] + sp;
    return w;
}
// letter-spaced text, vertically centred on y
function txt(x, y, s, size, col, align, sp) {
    var mg = mgraphics, w = textW(s, size, sp);
    if (align === "right") x -= w; else if (align === "center") x -= w / 2;
    var fe = mg.font_extents();
    y += (fe[0] - fe[1]) / 2;
    rgba(col);
    for (var i = 0; i < s.length; i++) {
        var ch = s.charAt(i);
        if (ch !== " ") { mg.move_to(x, y); mg.show_text(ch); }
        x += mg.text_measure(ch)[0] + sp;
    }
}
function paint() {
    var mg = mgraphics;
    if (bg) {
        mg.save(); mg.scale(0.5, 0.5); mg.set_source_rgba(1, 1, 1, 1); mg.image_surface_draw(bg); mg.restore();
    } else { mg.set_source_rgba(0.086, 0.086, 0.086, 1); mg.rectangle(0, 0, 112, 169); mg.fill(); }
    var drums = fam === 16, famName = FAMILIES[fam], progName = drums ? "GM PERCUSSION" : PROGRAMS[fam][prog];
    var col = drums ? C.a : C.c;
    // readout on the screen (8, 8, 96, 62)
    txt(14, 17, drums ? "GM KIT" : "GM " + (inst + 1), 5, C.dim, "left", 0.9);
    rgba(C.rule); mg.rectangle(13, 23, 86, 0.6); mg.fill();
    var big = textW(famName, 13, 1.2) <= 84 ? 13 : 10;
    txt(14, 36, famName, big, col, "left", 1.2);
    if (textW(progName, 6.4, 0.8) <= 84) txt(14, 56, progName, 6.4, C.g, "left", 0.8);
    else {
        var w = progName.split(" "), h = Math.ceil(w.length / 2);
        txt(14, 52, w.slice(0, h).join(" "), 6.4, C.g, "left", 0.8);
        txt(14, 61, w.slice(h).join(" "), 6.4, C.g, "left", 0.8);
    }
    // the two keys: the LED slit (the live.menus on top draw the legend and arrow)
    var keyY = [84, 108];
    for (var k = 0; k < 2; k++) {
        var y = keyY[k], on = lit === k && !(drums && k === 1);
        if (on) {
            for (var gl = 3; gl >= 1; gl--) { mg.set_source_rgba(0.95, 0.95, 0.95, 0.08 * (4 - gl)); mg.rectangle(12 - gl * 0.7, y + 7 - gl * 0.7, 1.6 + gl * 1.4, 4 + gl * 1.4); mg.fill(); }
        }
        rgba(on ? C.led : C.ledOff); mg.rectangle(12, y + 7, 1.6, 4); mg.fill();
    }
}
