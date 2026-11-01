"""S0 acceptance smoke against the product-isolated OpenCode v2 service.

Reads the service registration written by the patched desktop
(state/opencode/service-local.json for the dev channel; the release channel
writes state/opencode/service.json — F-7/patch 008 dispatches the file by
channel, W3-U34), authenticates with basic auth, and exercises:
info / create / prompt / get / inbox / interrupt.
Credentials are read from the registration file or environment; they are never
printed or committed. Both registration files may exist on disk (stale copies
from the other channel are a measured fact), so the live one is picked by
answering /api/info — the live-pid authority discipline.

The delivered implementation/python/opencode_http.py pins runtime "2.0.28";
dev-mode boots report "2.0.0-local-<ts>" (or the T07 wrapper mark
"2.0.28-local-*"), and the packaged bundled CLI reports its own frozen version
("0.0.0-dev-21102", W3-U22/e01 §9.1 — recorded as the release-channel fact,
never faked as the pin; F-4 dual-track, PIN checks distinguish dev/packaged).
This driver reuses the same transport but records the actual version instead of
failing the check, and marks DEV_VERSION=true when it is not the packaged pin.

Usage: python -X utf8 tools/s0_smoke.py --workspace <dir> [--skip-prompt]
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "implementation" / "python"))
from opencode_http import Client, TransportError  # noqa: E402

PIN = "2.0.28"


def registration_credentials() -> tuple[str, dict, dict]:
    """Pick the live registration among both channel files by answering
    /api/info (stale copies from the other channel are a measured fact —
    W3-U34 release-form run: service.json Oct-19 stale while dev served)."""
    reg_dir = Path(os.path.expandvars(r"%APPDATA%\Juscite\state\opencode"))
    errors = []
    for reg_path in (reg_dir / "service.json",          # release channel (packaged)
                     reg_dir / "service-local.json"):   # dev channel (source run)
        if not reg_path.exists():
            errors.append("%s:missing" % reg_path.name)
            continue
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            headers = {"Authorization": "Basic " + base64.b64encode(
                f"opencode:{reg['password']}".encode()).decode("ascii")}
            url = reg["url"]
            info = Client(url, headers=headers, timeout=10).request("GET", "/api/info")
            value = info.get("data", info) if isinstance(info, dict) else {}
            facts = {"registration": str(reg_path),
                     "channel": "release" if reg_path.name == "service.json" else "dev",
                     "regPid": reg.get("pid"), "livePid": value.get("pid"),
                     "version": value.get("version")}
            return url, dict(headers), facts
        except (OSError, ValueError, KeyError, TransportError) as exc:
            errors.append("%s:%r" % (reg_path.name, exc))
    raise FileNotFoundError("no live service registration under %s (%s)"
                            % (reg_dir, "; ".join(errors)))


def wait_for(condition, timeout, interval=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(interval)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--skip-prompt", action="store_true")
    parser.add_argument("--prompt-timeout", type=float, default=180.0)
    parser.add_argument("--provider", default="zhipu-smoke")
    parser.add_argument("--model", default="glm-4-flash")
    args = parser.parse_args()

    url, headers, reg_facts = registration_credentials()
    client = Client(url, headers=headers, timeout=60)
    results = {"steps": []}

    def step(name, status, **facts):
        entry = {"step": name, "status": status, **facts}
        results["steps"].append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)

    # 0. registration channel (F-4 dual-track: record which channel file is live)
    step("registration", "OK", **reg_facts)

    # 1. info / version
    try:
        info = client.request("GET", "/api/info")
        value = info.get("data", info) if isinstance(info, dict) else {}
        version = value.get("version") if isinstance(value, dict) else None
        step("info", "OK", version=version, dev_version=(version != PIN))
    except TransportError as exc:
        step("info", "FAIL", code=exc.code)
        return 2

    session_id = "ses_s0_smoke_" + str(int(time.time()))
    # 2. create session bound to the smoke workspace directory, with the BYOK provider as session model
    try:
        created = client.create({
            "id": session_id,
            "title": "律引 S0 冒烟（合成）",
            "location": {"directory": str(Path(args.workspace).resolve())},
            "model": {"id": args.model, "providerID": args.provider},
        })
        step("create", "OK", session_id=session_id, keys=sorted(created.keys()) if isinstance(created, dict) else None)
    except TransportError as exc:
        step("create", "FAIL", code=exc.code)
        return 2

    if args.skip_prompt:
        print(json.dumps({"status": "SMOKE_PARTIAL", "results": results}, ensure_ascii=False))
        return 0

    # 3. prompt with the BYOK provider; caller-persisted message id; synthetic material attached
    material = Path(args.workspace).resolve() / "materials" / "合成材料-合同摘要.txt"
    message_id = "msg_s0_" + str(int(time.time()))
    prompt_text = (
        "这是律引 S0 冒烟测试（合成材料，非真实案件）。随消息附上材料文件，请阅读后用两行回答："
        "第一行：合同总价款与付款期限；第二行：按合同约定逾期付款的违约金计算标准。不要展开分析。"
    )
    try:
        response = client.prompt(session_id, {
            "id": message_id,
            "text": prompt_text,
            "model": {"id": args.model, "providerID": args.provider},
            "files": [{"uri": material.as_uri(), "name": material.name}],
        })
        step("prompt", "SUBMITTED", message_id=message_id, response_keys=sorted(response.keys()) if isinstance(response, dict) else None)
    except TransportError as exc:
        step("prompt", "FAIL", code=exc.code, uncertain=exc.uncertain)

    # 4. poll the message list for assistant output
    def assistant_text():
        try:
            listing = client.request("GET", f"/api/session/{quote(session_id, safe='')}/message")
        except TransportError:
            return None
        parts = []
        for message in listing.get("data", []) if isinstance(listing, dict) else []:
            if message.get("type") != "assistant":
                continue
            for part in message.get("content", []) or message.get("parts", []):
                if part.get("type") == "text" and part.get("text"):
                    parts.append(part["text"])
        return "\n".join(parts) if parts else None

    answer = wait_for(assistant_text, args.prompt_timeout)
    step("assistant_output", "OK" if answer else "TIMEOUT", text=(answer or "")[:300])

    # 5. inbox
    try:
        inbox = client.inbox(session_id)
        step("inbox", "OK", payload_keys=sorted(inbox.keys()) if isinstance(inbox, dict) else None)
    except TransportError as exc:
        step("inbox", "FAIL", code=exc.code)

    # 6. interrupt (safe on an idle session as a transport check)
    try:
        client.interrupt(session_id)
        step("interrupt", "OK")
    except TransportError as exc:
        step("interrupt", "FAIL", code=exc.code)

    # 7. final session readback for persistence evidence
    try:
        session = client.session(session_id)
        value = session.get("data", session) if isinstance(session, dict) else {}
        messages = value.get("messages", []) if isinstance(value, dict) else []
        step("session_readback", "OK",
             session_id=value.get("id") if isinstance(value, dict) else None,
             message_count=len(messages),
             title=value.get("title") if isinstance(value, dict) else None)
    except TransportError as exc:
        step("session_readback", "FAIL", code=exc.code)

    print(json.dumps({"status": "SMOKE_DONE", "results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
