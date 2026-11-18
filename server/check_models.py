"""Check models.yaml before the server starts, and say what is wrong in plain words (the server would print a
traceback). Run by the launchers with the server's Python: check_models.py <models.yaml>. Exit 1 when it can't be used.
"""
import sys

import yaml

path = sys.argv[1]
hint = "See https://metacreation-lab.github.io/midigpt-LIVE/models/"
try:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
except yaml.YAMLError as e:
    mark = getattr(e, "problem_mark", None)
    near = f" near line {mark.line + 1}" if mark else ""
    sys.exit(f"models.yaml has a mistake{near}: each model line starts with two spaces and a dash, like the others.\n"
             f"  {path}\n  {hint}")
if not isinstance(cfg, dict) or not cfg.get("models"):
    sys.exit(f"models.yaml lists no models: remove the \"# \" before at least one model line.\n  {path}\n  {hint}")
ids = [m.get("id") for m in cfg["models"] if isinstance(m, dict)]
default = cfg.get("default_model")
if default and default not in ids:
    sys.exit(f"models.yaml: default_model is {default}, which isn't switched on. Use one of: {', '.join(map(str, ids))}.\n"
             f"  {path}\n  {hint}")
