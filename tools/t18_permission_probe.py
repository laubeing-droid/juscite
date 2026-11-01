"""T18 / F-9 permission precedence probe.

Runs against the live lvyin service (oc28 v2) and measures the effect returned by
`session.permission.create` for a synthetic session whose session-level ruleset is
[shell deny (decoy), shell allow (trailing)].

Groups (each rep gets a FRESH directory => fresh location instance):
  A  create -> probe immediately
  B  create -> sleep 10s -> probe
  C  create -> probe immediately with explicit agent param
  W  warm control: 5 more probes against group A rep #5 directory (converged)

Output: JSON lines to stdout (effect, timings). Password is read from the
service registration file and never printed.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
import urllib.request

REG = os.path.expandvars(r"%APPDATA%\Juscite\state\opencode\service-local.json")
REPS = 5
DELAY_S = 10.0

PROBE_ACTION = "shell"
# Decoy deny first, trailing allow second: last-match-wins inside session rules
# must yield allow at the rules phase; the policies veto (if registered) flips to deny.
SESSION_RULES = [
    {"action": "shell", "resource": "*", "effect": "deny"},
    {"action": "shell", "resource": "*", "effect": "allow"},
]


def load_auth():
    reg = json.load(open(REG, encoding="utf-8"))
    token = base64.b64encode(f"opencode:{reg['password']}".encode()).decode()
    return reg["url"], {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def call(url, headers, path, payload=None, timeout=120):
    req = urllib.request.Request(
        url + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read())
    return body, (time.perf_counter() - t0) * 1000.0


def probe_session(url, headers, directory, agent=None, delay=0.0):
    payload = {
        "title": "t18-f9-probe",
        "permissions": SESSION_RULES,
        "location": {"directory": directory},
    }
    create_body, create_ms = call(url, headers, "/api/session", payload)
    session_id = create_body["data"]["id"]
    session_agent = create_body["data"].get("agent")
    if delay:
        time.sleep(delay)
    probe = {
        "action": PROBE_ACTION,
        "resources": [f"echo t18-synthetic-probe-{os.path.basename(directory)}"],
        "metadata": {"probe": "t18-f9", "synthetic": True},
    }
    if agent is not None:
        probe["agent"] = agent
    body, probe_ms = call(url, headers, f"/api/session/{session_id}/permission", probe)
    return {
        "directory": directory,
        "session_id": session_id,
        "session_agent": session_agent,
        "create_ms": round(create_ms, 1),
        "probe_ms": round(probe_ms, 1),
        "effect": body["data"]["effect"],
    }


def main():
    url, headers = load_auth()
    root = os.path.join(tempfile.gettempdir(), "t18-f9-probes")
    os.makedirs(root, exist_ok=True)
    results = {"A_immediate": [], "B_delay10s": [], "C_agent_explicit": [], "W_warm_control": []}

    def fresh_dir(tag):
        d = os.path.join(root, f"{tag}-{int(time.time()*1000)}")
        os.makedirs(d, exist_ok=True)
        return d

    for i in range(1, REPS + 1):
        results["A_immediate"].append(probe_session(url, headers, fresh_dir(f"a{i}")))
        print(json.dumps({"group": "A_immediate", "rep": i, **results["A_immediate"][-1]}, ensure_ascii=False))
        sys.stdout.flush()
    for i in range(1, REPS + 1):
        results["B_delay10s"].append(probe_session(url, headers, fresh_dir(f"b{i}"), delay=DELAY_S))
        print(json.dumps({"group": "B_delay10s", "rep": i, **results["B_delay10s"][-1]}, ensure_ascii=False))
        sys.stdout.flush()
    for i in range(1, REPS + 1):
        results["C_agent_explicit"].append(
            probe_session(url, headers, fresh_dir(f"c{i}"), agent="legal-review")
        )
        print(json.dumps({"group": "C_agent_explicit", "rep": i, **results["C_agent_explicit"][-1]}, ensure_ascii=False))
        sys.stdout.flush()
    warm_dir = results["A_immediate"][-1]["directory"]
    for i in range(1, REPS + 1):
        body, ms = call(url, headers, f"/api/session/{results['A_immediate'][-1]['session_id']}/permission", {
            "action": PROBE_ACTION,
            "resources": [f"echo t18-synthetic-warm-{i}"],
            "metadata": {"probe": "t18-f9-warm", "synthetic": True},
        })
        row = {"directory": warm_dir, "probe_ms": round(ms, 1), "effect": body["data"]["effect"]}
        results["W_warm_control"].append(row)
        print(json.dumps({"group": "W_warm_control", "rep": i, **row}, ensure_ascii=False))
        sys.stdout.flush()

    summary = {
        g: {
            "deny": sum(1 for r in rows if r["effect"] == "deny"),
            "allow": sum(1 for r in rows if r["effect"] == "allow"),
            "ask": sum(1 for r in rows if r["effect"] == "ask"),
            "n": len(rows),
        }
        for g, rows in results.items()
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
