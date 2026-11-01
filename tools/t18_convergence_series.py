"""T18 / F-9 convergence timing: how long until the policies veto appears on a
fresh directory instance?

For each of 2 fresh directories: create probe session (trailing allow shell),
then probe the SAME session at t = 0, 5, 10, 20, 30, 45, 60, 90, 120 s and
record the first deny. Also: create a NEW session in the first (now warm)
directory and probe immediately.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from t18_permission_probe import load_auth, call, SESSION_RULES, PROBE_ACTION

SCHEDULE = [0, 5, 10, 20, 30, 45, 60, 90, 120]


def make_session(url, headers, directory):
    body, ms = call(url, headers, "/api/session", {
        "title": "t18-f9-convergence",
        "permissions": SESSION_RULES,
        "location": {"directory": directory},
    })
    return body["data"]["id"], ms


def probe(url, headers, session_id, tag):
    body, ms = call(url, headers, f"/api/session/{session_id}/permission", {
        "action": PROBE_ACTION,
        "resources": [f"echo t18-convergence-{tag}"],
        "metadata": {"probe": "t18-f9-convergence", "synthetic": True},
    })
    return body["data"]["effect"], ms


def main():
    url, headers = load_auth()
    root = os.path.join(tempfile.gettempdir(), "t18-f9-probes")
    os.makedirs(root, exist_ok=True)

    warm_directory = None
    for run in (1, 2):
        d = os.path.join(root, f"conv{run}-{int(time.time()*1000)}")
        os.makedirs(d, exist_ok=True)
        sid, create_ms = make_session(url, headers, d)
        print(json.dumps({"run": run, "event": "created", "directory": d, "session": sid,
                          "create_ms": round(create_ms, 1)}), flush=True)
        t0 = time.perf_counter()
        for offset in SCHEDULE:
            wait = offset - (time.perf_counter() - t0)
            if wait > 0:
                time.sleep(wait)
            effect, ms = probe(url, headers, sid, f"r{run}-{offset}")
            print(json.dumps({"run": run, "t_s": round(time.perf_counter() - t0, 1),
                              "effect": effect, "probe_ms": round(ms, 1)}), flush=True)
        if run == 1:
            warm_directory = d

    # New session inside the now-warm directory from run 1: is the veto instance-level?
    sid2, create_ms = make_session(url, headers, warm_directory)
    effect, ms = probe(url, headers, sid2, "warm-new-session")
    print(json.dumps({"event": "warm_dir_new_session", "directory": warm_directory,
                      "session": sid2, "create_ms": round(create_ms, 1),
                      "effect": effect, "probe_ms": round(ms, 1)}), flush=True)


if __name__ == "__main__":
    main()
