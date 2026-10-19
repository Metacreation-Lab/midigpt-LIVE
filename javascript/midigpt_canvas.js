// A small part of the HTML canvas 2D API on top of jsui mgraphics, so the
// panel's drawing code (ported from the browser prototype) runs unchanged.
// include("midigpt_canvas.js") then MidigptCanvas.wrap(mgraphics) -> ctx. (include, not
// require: Max keeps require()d modules cached, so an edited module would not load.)
//
// Covered: save/restore, globalAlpha, fillStyle/strokeStyle (#hex, rgb(),
// rgba()), lineWidth/Cap/Join, setLineDash (strokeRect only), font
// ("700 7.4px ..."), letterSpacing, textAlign, textBaseline (middle /
// alphabetic), fillText, measureText, beginPath, moveTo, lineTo, arc, arcTo,
// rect, closePath, fill, stroke, fillRect, strokeRect, clearRect, drawImage
// (Image objects), translate, scale.
//
// Differences from a browser canvas: fillRect/strokeRect clear the current
// path (cairo has one path); only strokeRect honours line dashes.

var MidigptCanvas = (function () {
var exports = {};
var FACES = { 700: "Ableton Sans Bold", 400: "Ableton Sans Medium" };
exports.FACES = FACES;

var colorCache = {};
function parseColor(s) {
    var c = colorCache[s];
    if (c) return c;
    var m;
    if (s.charAt(0) === "#") {
        var h = s.slice(1);
        if (h.length === 3) h = h.charAt(0) + h.charAt(0) + h.charAt(1) + h.charAt(1) + h.charAt(2) + h.charAt(2);
        c = [parseInt(h.slice(0, 2), 16) / 255, parseInt(h.slice(2, 4), 16) / 255, parseInt(h.slice(4, 6), 16) / 255, 1];
    } else if ((m = /rgba?\(([^)]*)\)/.exec(s))) {
        var p = m[1].split(",");
        c = [+p[0] / 255, +p[1] / 255, +p[2] / 255, p.length > 3 ? +p[3] : 1];
    } else c = [1, 0, 1, 1];
    colorCache[s] = c;
    return c;
}
exports.parseColor = parseColor;

exports.wrap = function (mg) {
    var stack = [];
    var groupsOk = true;   // push_group / paint_with_alpha (dimmed sprites); plain drawing if missing
    var widthCache = {};
    var ctx = {
        globalAlpha: 1, fillStyle: "#000", strokeStyle: "#000", lineWidth: 1, lineCap: "butt", lineJoin: "miter",
        font: "400 10px sans", letterSpacing: "0px", textAlign: "left", textBaseline: "alphabetic", _dash: null,
        _px: 0, _py: 0, _sx: 0, _sy: 0
    };
    var KEYS = ["globalAlpha", "fillStyle", "strokeStyle", "lineWidth", "lineCap", "lineJoin", "font", "letterSpacing", "textAlign", "textBaseline", "_dash"];

    function src(style) { var c = parseColor(style); mg.set_source_rgba(c[0], c[1], c[2], c[3] * ctx.globalAlpha); }
    function lineProps() {
        mg.set_line_width(ctx.lineWidth);
        mg.set_line_cap(ctx.lineCap === "round" ? "round" : ctx.lineCap === "square" ? "square" : "butt");
        mg.set_line_join(ctx.lineJoin === "round" ? "round" : ctx.lineJoin === "bevel" ? "bevel" : "miter");
    }
    var fontCache = {}, extentCache = {};
    function fontProps() {
        var f = fontCache[ctx.font];
        if (!f) {
            var m = /(\d+)?\s*([\d.]+)px/.exec(ctx.font) || [0, 400, 10];
            var w = +(m[1] || 400), size = +m[2];
            f = fontCache[ctx.font] = { face: FACES[w >= 600 ? 700 : 400], size: size };
        }
        mg.select_font_face(f.face);
        mg.set_font_size(f.size);
        return f;
    }
    // Letter spacing is drawn one character at a time; half a pixel or less is not worth it (one show_text).
    function spacing() { var sp = parseFloat(ctx.letterSpacing) || 0; return sp > 0.5 ? sp : 0; }
    function charW(f, ch) {
        var k = f.face + f.size + ch, w = widthCache[k];
        if (w === undefined) { w = mg.text_measure(ch)[0]; widthCache[k] = w; }
        return w;
    }
    function textWidth(f, s) {
        var sp = spacing();
        if (!sp) {
            var k = f.face + f.size + "|" + s, w = widthCache[k];
            if (w === undefined) { w = mg.text_measure(s)[0]; widthCache[k] = w; }
            return w;
        }
        var t = 0;
        for (var i = 0; i < s.length; i++) t += charW(f, s.charAt(i)) + sp;
        return t;
    }

    ctx.save = function () {
        var o = {};
        for (var i = 0; i < KEYS.length; i++) o[KEYS[i]] = ctx[KEYS[i]];
        stack.push(o);
        mg.save();
    };
    ctx.restore = function () {
        var o = stack.pop();
        if (o) for (var k in o) ctx[k] = o[k];
        mg.restore();
    };
    ctx.translate = function (x, y) { mg.translate(x, y); };
    ctx.scale = function (x, y) { mg.scale(x, y); };
    ctx.setLineDash = function (d) { ctx._dash = d && d.length ? d : null; };

    ctx.beginPath = function () { mg.new_path(); };
    ctx.moveTo = function (x, y) { mg.move_to(x, y); ctx._px = ctx._sx = x; ctx._py = ctx._sy = y; };
    ctx.lineTo = function (x, y) { mg.line_to(x, y); ctx._px = x; ctx._py = y; };
    ctx.closePath = function () { mg.close_path(); ctx._px = ctx._sx; ctx._py = ctx._sy; };
    ctx.rect = function (x, y, w, h) { mg.rectangle(x, y, w, h); };   // adds to the path: many rects, one fill
    ctx.arc = function (cx, cy, r, a0, a1, ccw) {
        if (ccw) mg.arc_negative(cx, cy, r, a0, a1); else mg.arc(cx, cy, r, a0, a1);
        ctx._px = cx + r * Math.cos(a1); ctx._py = cy + r * Math.sin(a1);
    };
    // canvas arcTo: a line toward (x1,y1), then an arc of radius r tangent to both segments
    ctx.arcTo = function (x1, y1, x2, y2, r) {
        var x0 = ctx._px, y0 = ctx._py;
        var ax = x0 - x1, ay = y0 - y1, bx = x2 - x1, by = y2 - y1;
        var la = Math.sqrt(ax * ax + ay * ay), lb = Math.sqrt(bx * bx + by * by);
        if (la < 1e-6 || lb < 1e-6 || r < 1e-6) { ctx.lineTo(x1, y1); return; }
        ax /= la; ay /= la; bx /= lb; by /= lb;
        var cos = ax * bx + ay * by, ang = Math.acos(Math.max(-1, Math.min(1, cos)));
        if (ang < 1e-4 || Math.abs(ang - Math.PI) < 1e-4) { ctx.lineTo(x1, y1); return; }
        var d = r / Math.tan(ang / 2);
        var t0x = x1 + ax * d, t0y = y1 + ay * d, t1x = x1 + bx * d, t1y = y1 + by * d;
        var bisx = ax + bx, bisy = ay + by, bl = Math.sqrt(bisx * bisx + bisy * bisy);
        var cd = r / Math.sin(ang / 2), cx = x1 + bisx / bl * cd, cy = y1 + bisy / bl * cd;
        var s0 = Math.atan2(t0y - cy, t0x - cx), s1 = Math.atan2(t1y - cy, t1x - cx);
        var cross = ax * by - ay * bx;
        mg.line_to(t0x, t0y);
        if (cross < 0) mg.arc(cx, cy, r, s0, s1); else mg.arc_negative(cx, cy, r, s0, s1);
        ctx._px = t1x; ctx._py = t1y;
    };
    ctx.fill = function () { src(ctx.fillStyle); mg.fill_preserve(); };
    ctx.stroke = function () { src(ctx.strokeStyle); lineProps(); mg.stroke_preserve(); };

    ctx.fillRect = function (x, y, w, h) { mg.new_path(); mg.rectangle(x, y, w, h); src(ctx.fillStyle); mg.fill(); };
    ctx.clearRect = function () {};
    ctx.strokeRect = function (x, y, w, h) {
        mg.new_path();
        src(ctx.strokeStyle); lineProps();
        var d = ctx._dash;
        if (!d) { mg.rectangle(x, y, w, h); mg.stroke(); return; }
        var on = d[0], off = d[1] || d[0];
        var edges = [[x, y, x + w, y], [x + w, y, x + w, y + h], [x + w, y + h, x, y + h], [x, y + h, x, y]];
        for (var e = 0; e < 4; e++) {
            var E = edges[e], dx = E[2] - E[0], dy = E[3] - E[1], len = Math.sqrt(dx * dx + dy * dy);
            for (var p = 0; p < len; p += on + off) {
                var q = Math.min(len, p + on);
                mg.move_to(E[0] + dx * p / len, E[1] + dy * p / len);
                mg.line_to(E[0] + dx * q / len, E[1] + dy * q / len);
            }
        }
        mg.stroke();
    };

    ctx.measureText = function (s) { var f = fontProps(); return { width: textWidth(f, String(s)) }; };
    ctx.fillText = function (s, x, y) {
        s = String(s);
        var f = fontProps(), w = textWidth(f, s), sp = spacing();
        if (ctx.textAlign === "center") x -= w / 2;
        else if (ctx.textAlign === "right" || ctx.textAlign === "end") x -= w;
        if (ctx.textBaseline === "middle") {
            var ek = f.face + f.size, fe = extentCache[ek];
            if (!fe) fe = extentCache[ek] = mg.font_extents();   // [ascent, descent, height]
            y += (fe[0] - fe[1]) / 2;
        }
        src(ctx.fillStyle);
        if (!sp) { mg.move_to(x, y); mg.show_text(s); return; }
        for (var i = 0; i < s.length; i++) {
            var ch = s.charAt(i);
            if (ch !== " ") { mg.move_to(x, y); mg.show_text(ch); }
            x += charW(f, ch) + sp;
        }
    };

    // drawImage(img, x, y, w, h): img is a Max Image (its size is in pixels: the PNGs are rendered at 2x)
    ctx.drawImage = function (img, x, y, w, h) {
        var iw = img.size[0], ih = img.size[1];
        if (!iw || !ih) return;
        mg.new_path();   // image_surface_draw paints through the current path: a leftover ring path would swallow the image
        mg.set_source_rgba(1, 1, 1, 1);   // and with the current colour's alpha: a faint ring colour would fade the image
        mg.save();
        mg.translate(x, y);
        mg.scale(w / iw, h / ih);
        if (ctx.globalAlpha < 0.999 && groupsOk) {
            try {
                mg.push_group();
                mg.image_surface_draw(img);
                mg.pop_group_to_source();
                mg.paint_with_alpha(ctx.globalAlpha);
            } catch (e) { groupsOk = false; mg.image_surface_draw(img); }
        } else {
            mg.image_surface_draw(img);
        }
        mg.restore();
    };
    return ctx;
};
return exports;
})();
