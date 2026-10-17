// node.script helper for midigpt.js: things Max's own JavaScript cannot do.
//
//   open_tag <device folder> <file name>   ask the running Live to open the tag device; Live loads it onto the
//                                          selected track. (The Live API cannot insert a device, so midigpt.js
//                                          selects the track and sends this.) The file is looked for next to
//                                          the main device, then in the installed MIDI-GPT folder.
//   config_set <key> <value...>            save a setting in the per-user config file
//
// Sends "config <key> <value...>" for every saved setting when it starts, then "config_ready".
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

const cfg = readConfig();
for (const k of Object.keys(cfg)) if (k !== "install_dir") maxApi.outlet("config", k, String(cfg[k]));
maxApi.outlet("config_ready");
