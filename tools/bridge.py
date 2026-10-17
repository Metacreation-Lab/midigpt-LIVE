#!/usr/bin/env python3
"""
Talk to a running MIDI-GPT device (in Live or the Max editor) over the UDP dev
bridge. The bridge is inert unless dev mode is on:  touch .midigpt_dev
(in the repo root), then reload the device.

  python3 tools/bridge.py state            session / selection / server state
  python3 tools/bridge.py ui               every named widget's value + rect
  python3 tools/bridge.py msg <sel> [args] send a message exactly as the UI would,
                                               e.g. msg set_global_param temperature 0.8
                                                    msg set_bar_selected 2 1
                                                    msg bang            (generate)
  python3 tools/bridge.py eval '<js expr>'  evaluate in midigpt.js's scope (dev only)
  python3 tools/bridge.py ui_send <path> <msg..>  message a named widget, e.g.
                                               ui_send main_window/setup_url select
  python3 tools/bridge.py reload           recompile midigpt.js from disk and re-init
  python3 tools/bridge.py log [n]          last n lines of midigpt.log (default 40)

Device side: [udpreceive 7474] -> [route /bridge /reload] -> midigpt.js, and
midigpt.js outlet 1 -> [udpsend 127.0.0.1 7475]. Messages are plain OSC.
"""

import json
import os
import random
import socket
import struct
import sys

SEND_PORT = 7474
RECV_PORT = 7475
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pad(b):
    return b + b"\0" * (4 - len(b) % 4)


def osc_encode(address, args):
    tags, payload = ",", b""
    for a in args:
        if isinstance(a, bool) or isinstance(a, int):
            tags += "i"
            payload += struct.pack(">i", int(a))
        elif isinstance(a, float):
            tags += "f"
            payload += struct.pack(">f", a)
        else:
            tags += "s"
            payload += _pad(str(a).encode("utf-8"))
    return _pad(address.encode()) + _pad(tags.encode()) + payload


def osc_decode(data):
    def read_str(i):
        end = data.index(b"\0", i)
        s = data[i:end].decode("utf-8", "replace")
        return s, (end + 4) & ~3
    address, i = read_str(0)
    tags, i = read_str(i)
    args = []
    for t in tags[1:]:
        if t == "i":
            args.append(struct.unpack(">i", data[i:i + 4])[0]); i += 4
        elif t == "f":
            args.append(struct.unpack(">f", data[i:i + 4])[0]); i += 4
        elif t == "s":
            s, i = read_str(i); args.append(s)
    return address, args


def coerce(tok):
    for cast in (int, float):
        try:
            return cast(tok)
        except ValueError:
            pass
    return tok


def request(cmd, args=(), timeout=5.0):
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(("127.0.0.1", RECV_PORT))
    rx.settimeout(timeout)
    req_id = random.randint(1, 1 << 30)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.sendto(osc_encode("/bridge", [req_id, cmd] + list(args)), ("127.0.0.1", SEND_PORT))
    chunks, total = {}, None
    try:
        while total is None or len(chunks) < total:
            data, _ = rx.recvfrom(65535)
            address, a = osc_decode(data)
            if address != "/midigpt/reply" or a[0] != req_id:
                continue
            _, seq, total, chunk = a[:4]
            chunks[seq] = chunk if isinstance(chunk, str) else str(chunk)
    except socket.timeout:
        sys.exit("no reply -- is the device loaded, and does .midigpt_dev exist in the repo root? "
                 "(the device reads it on load; use 'reload' after creating it)")
    finally:
        rx.close()
    text = "".join(chunks[i] for i in range(total))
    try:
        return json.loads(text)
    except ValueError:
        return text


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "reload":
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(osc_encode("/reload", []), ("127.0.0.1", SEND_PORT))
        print("reload sent")
        return 0
    if cmd == "log":
        n = int(argv[1]) if len(argv) > 1 else 40
        path = os.path.join(ROOT, "midigpt.log")
        with open(path, errors="replace") as f:
            print("".join(f.readlines()[-n:]), end="")
        return 0
    if cmd in ("state", "ui"):
        result = request(cmd)
    elif cmd == "ui_send":
        result = request("ui_send", [argv[1]] + [coerce(t) for t in argv[2:]])
    elif cmd == "eval":
        result = request("eval", [" ".join(argv[1:])])
    elif cmd == "msg":
        result = request("msg", [coerce(t) for t in argv[1:]])
    else:
        print(__doc__)
        return 2
    print(json.dumps(result, indent=2) if not isinstance(result, str) else result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
