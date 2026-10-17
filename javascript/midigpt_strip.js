/**
 * The MIDI-GPT device's strip in Live's device chain (96 x 169): one big key
 * (media/panel/midigpt_strip_bg.png) with the MIDI-GPT mark on it. Clicking the key
 * opens the window; the mark lights for a moment.
 *
 * In:  flash
 * Out: bang (a click on the key)
 */

autowatch = 0;
inlets = 1;
outlets = 1;

mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;

var KEY = [10, 10, 76, 118];   // tools/tag_device_assets.py STRIP
// the Metacreation mark (render_ui.py LOGO_POLYS, viewBox 105.63 x 137.32)
var MARK = [[[26.41, 10.56], [84.51, 68.66], [26.41, 126.76], [36.97, 137.32], [105.63, 68.66], [36.97, 0], [26.41, 10.56]],
            [[31.69, 36.97], [0, 68.66], [31.69, 100.35], [42.25, 89.79], [21.13, 68.66], [42.25, 47.53], [31.69, 36.97]]];
var down = 0;
var bg = null;
try { bg = new Image("midigpt_strip_bg.png"); if (!bg.size[0]) bg = null; } catch (e) { bg = null; }

var off = new Task(function () { down = 0; mgraphics.redraw(); }, this);
function flash() { down = 1; mgraphics.redraw(); off.schedule(300); }
function onclick(x, y) {
    if (x >= KEY[0] && x <= KEY[0] + KEY[2] && y >= KEY[1] && y <= KEY[1] + KEY[3]) outlet(0, "bang");
}
onclick.local = 1;

function markPath(cx, cy, h) {
    var mg = mgraphics, k = h / 137.32, ox = cx - 105.63 * k / 2, oy = cy - h / 2;
    mg.new_path();
    for (var p = 0; p < MARK.length; p++) {
        for (var i = 0; i < MARK[p].length; i++) {
            var x = ox + MARK[p][i][0] * k, y = oy + MARK[p][i][1] * k;
            if (i === 0) mg.move_to(x, y); else mg.line_to(x, y);
        }
        mg.close_path();
    }
}

function paint() {
    var mg = mgraphics, dy = down ? 0.8 : 0;
    if (bg) { mg.save(); mg.scale(0.5, 0.5); mg.set_source_rgba(1, 1, 1, 1); mg.image_surface_draw(bg); mg.restore(); }
    else { mg.set_source_rgba(0.086, 0.086, 0.086, 1); mg.rectangle(0, 0, 96, 169); mg.fill(); }
    var cx = KEY[0] + KEY[2] / 2, cy = KEY[1] + KEY[3] / 2 + dy, h = 46;
    if (down) {   // lit: the mark glows in the LED colour (a few wider, fainter passes; mgraphics has no blur)
        mg.set_line_join("round");
        var passes = [[7, 0.05], [4.5, 0.09], [2.5, 0.16]];
        for (var i = 0; i < passes.length; i++) {
            markPath(cx, cy, h); mg.set_source_rgba(0.95, 0.95, 0.95, passes[i][1]); mg.set_line_width(passes[i][0]); mg.stroke();
        }
        markPath(cx, cy, h); mg.set_source_rgba(0.95, 0.95, 0.95, 1); mg.fill();
    } else {
        markPath(cx, cy, h); mg.set_source_rgba(0.478, 0.478, 0.478, 1); mg.fill();
    }
}
