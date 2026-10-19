// node.script helper for midigpt.js: things Max's own JavaScript cannot do.
//
//   open_tag <device folder> <file name>   ask the running Live to open the tag device; Live loads it onto the
//                                          selected track. (The Live API cannot insert a device, so midigpt.js
//                                          selects the track and sends this.) The file is looked for next to
//                                          the main device, then in the installed MIDI-GPT folder.
//   config_set <key> <value...>            save a setting in the per-user config file
//   http_body <id> <i> <|text>             one chunk of a request body
//   http_send <id> <method> <url> <timeout ms> <chunks> <|dump path or |>
//                                          make the request; replies http_chunk <id> <i> <|text> for each chunk of
//                                          the response, then http_done <id> <status> <chunks> (status 0: no
//                                          connection), or http_timeout <id>. A streamed reply (text/event-stream)
//                                          sends http_event <id> <|json> per notes or progress frame ({ n: new notes,
//                                          progress }), at most every 200 ms, and then the final frame's response
//                                          as the reply. With a dump path (dev mode) the body and the reply are
//                                          also written to <path>.req.json / .resp.json
//   http_abort <id>                        drop an in-flight request
//
// Sends "config <key> <value...>" for every saved setting when it starts and on "hello", then "config_ready".
// Replies "node_error <message>" on failure.
const maxApi = require("max-api");
const { execFile } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

// Per-user settings, outside the device: a frozen device's folder may be read-only or temporary.
function configDir() {
  if (process.platform === "darwin") return path.join(os.homedir(), "Library", "Application Support", "MIDI-GPT");
  if (process.platform === "win32") return path.join(process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming"), "MIDI-GPT");
  return path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config"), "MIDI-GPT");
}
const CONFIG = path.join(configDir(), "live.json");

function readConfig() {
  try { return JSON.parse(fs.readFileSync(CONFIG, "utf8")) || {}; } catch (e) { return {}; }
}

// The Live that is running right now (not just the system default for .amxd, which could be another version).
function runningLiveApp(cb) {
  if (process.platform !== "darwin") return cb(null);
  execFile("ps", ["-axo", "comm="], (err, out) => {
    if (err) return cb(null);
    const line = out.split("\n").find((l) => /Ableton Live[^/]*\.app\/Contents\/MacOS\//.test(l));
    cb(line ? line.slice(0, line.indexOf(".app/") + 4) : null);
  });
}

// Max paths can start with the volume name ("Macintosh HD:/Users/..."): make them POSIX
function posixPath(p) { return p.replace(/^[^/:]+:(?=\/)/, ""); }

// Where the tag device can be: next to the main device (a release folder, or patchers/ in the repo),
// the folder install.sh saved in the settings, and the default User Library's MIDI-GPT folder.
function tagCandidates(dir, file) {
  const out = [];
  if (dir) out.push(path.join(posixPath(dir), file));
  const cfg = readConfig();
  if (cfg.install_dir) out.push(path.join(cfg.install_dir, file));
  out.push(path.join(os.homedir(), process.platform === "win32" ? "Documents" : "Music", "Ableton", "User Library", "MIDI-GPT", file));
  return out;
}

function openFile(file, done) {
  if (process.platform === "darwin") runningLiveApp((app) => execFile("open", app ? ["-a", app, file] : [file], done));
  else execFile("cmd", ["/c", "start", "", file], done);
}

maxApi.addHandler("open_tag", (dir, ...name) => {
  const file = name.join(" ");
  const found = tagCandidates(String(dir || ""), file).find((p) => fs.existsSync(p));
  if (!found) return maxApi.outlet("node_error", "tag device not found: " + file);
  openFile(found, (err) => { if (err) maxApi.outlet("node_error", String(err.message || err)); });
});

maxApi.addHandler("config_set", (key, ...value) => {
  const cfg = readConfig();
  cfg[key] = value.join(" ");
  try {
    fs.mkdirSync(path.dirname(CONFIG), { recursive: true });
    fs.writeFileSync(CONFIG, JSON.stringify(cfg, null, 2) + "\n");
  } catch (e) { maxApi.outlet("node_error", "could not save settings: " + e.message); }
});

// HTTP for midigpt.js (Max's XMLHttpRequest crashes Live when a reply arrives after the device is deleted).
// Bodies and replies travel in chunks prefixed with "|", so Max never reads a chunk as a number.
const http = require("http");
const https = require("https");
const CHUNK = 16000;   // under Max's ~32k-character message argument, with room for the "|" prefix
const bodies = {};     // id -> body chunks
const requests = {};   // id -> in-flight request

maxApi.addHandler("http_body", (id, i, text) => {
  (bodies[id] = bodies[id] || [])[i] = String(text).slice(1);
});

// Streamed progress goes to Max at most this often (the panel cannot show more), the note counts added up.
const EVENT_MS = 200;

maxApi.addHandler("http_send", (id, method, url, timeout, n, dumpArg) => {
  const body = (bodies[id] || []).slice(0, n).join("");
  delete bodies[id];
  // dev mode: the full body and reply as files (a Max message cuts a log line at ~32k characters)
  const dump = dumpArg && String(dumpArg).length > 1 ? posixPath(String(dumpArg).slice(1)) : "";
  const save = (ext, text) => {
    if (!dump) return;
    fs.mkdir(path.dirname(dump), { recursive: true }, () => fs.writeFile(dump + ext, text, () => {}));
  };
  save(".req.json", body);
  let done = false;
  let evN = 0, evProgress = null, evTimer = null;
  const flushEvent = () => {
    if (evTimer) { clearTimeout(evTimer); evTimer = null; }
    if (done || (!evN && !evProgress)) return;
    maxApi.outlet("http_event", id, "|" + JSON.stringify({ n: evN, progress: evProgress }));
    evN = 0; evProgress = null;
  };
  const finish = (...msg) => { if (done) return; done = true; if (evTimer) clearTimeout(evTimer); delete requests[id]; maxApi.outlet(...msg); };
  let req;
  try {
    const u = new URL(String(url));
    const headers = body ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) } : {};
    req = (u.protocol === "https:" ? https : http).request(u, { method: String(method), headers }, (res) => {
      const parts = [];
      const sse = /text\/event-stream/.test(res.headers["content-type"] || "");
      let buf = "", status = res.statusCode, final = null;
      res.setEncoding("utf8");
      res.on("data", (d) => {
        if (!sse) return parts.push(d);
        buf += d;
        let k;
        while ((k = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, k); buf = buf.slice(k + 2);
          const line = frame.split("\n").find((l) => l.startsWith("data:"));
          let ev; try { ev = JSON.parse(line.slice(5)); } catch (e) { continue; }
          if (ev.type === "notes" || ev.type === "progress") {
            evN += (ev.notes || []).length;
            if (ev.progress) evProgress = ev.progress;
            if (!evTimer) evTimer = setTimeout(flushEvent, EVENT_MS);
          }
          else if (ev.type === "error") { status = 500; final = JSON.stringify({ detail: ev.error }); }
          else if (ev.response) final = JSON.stringify(ev.response);
        }
      });
      res.on("end", () => {
        if (done) return;
        const text = sse ? (final || "") : parts.join("");
        if (sse && !final) status = 0;      // the stream ended without its last frame
        flushEvent();                       // the last progress before the reply
        save(".resp.json", text);
        const n = Math.ceil(text.length / CHUNK);
        for (let k = 0; k < n; k++) maxApi.outlet("http_chunk", id, k, "|" + text.substr(k * CHUNK, CHUNK));
        finish("http_done", id, status, n);
      });
      res.on("error", () => finish("http_done", id, 0, 0));
    });
  } catch (e) { return finish("http_done", id, 0, 0); }
  requests[id] = req;
  // a plain timer: req.setTimeout only counts idle time on a connected socket, so an unreachable host took ~75 s
  if (+timeout > 0) {
    const timer = setTimeout(() => { finish("http_timeout", id); req.destroy(); }, +timeout);
    req.on("close", () => clearTimeout(timer));
  }
  req.on("error", () => finish("http_done", id, 0, 0));
  req.end(body || undefined);
});

maxApi.addHandler("http_abort", (id) => {
  const req = requests[id];
  delete requests[id];
  if (req) req.destroy();
});

function sendConfig() {
  const cfg = readConfig();
  for (const k of Object.keys(cfg)) if (k !== "install_dir") maxApi.outlet("config", k, String(cfg[k]));
  maxApi.outlet("config_ready");
}

// midigpt.js says hello from init(): this helper may have started before the script could hear it.
maxApi.addHandler("hello", sendConfig);
sendConfig();
