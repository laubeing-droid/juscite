"""E10 OS 层出站负测（会话期差分，无管理员方案）。

裁决依据：docs/construction/00-总协调.md §6.1 裁决 #2——OS 层出站负测走
无管理员方案先行（netstat/Get-DnsClientCache 会话期差分）；宿主级抓包待环境。

方法：对活服务 127.0.0.1:43127（注册文件 %APPDATA%\\Juscite\\state\\opencode\\service-local.json，
basic opencode:<password，只读不印不落盘>）发一轮带合成金丝雀材料的 DeepSeek 模型轮
（provider=deepseek-byok model=deepseek-chat，材料只写系统临时目录，token 唯一），
在 跑前/会话中/跑后 三次采集 netstat -ano(TCP) 与 Get-DnsClientCache(pwsh)，
断言差分里仅出现预期端点（api.deepseek.com 及本机回环），无 models.dev/遥测/未知外联。

断言（产物 JSON 的 assertions 字段逐条对应）：
  A1 模型轮完成（assistant 文本非空；不完成=>BLOCKED，防空洞 PASS）
  A2 服务进程树（43127 监听 PID 及其子孙）新外联 ⊆ {api.deepseek.com 解析 IP} ∪ 回环
  A3 DNS 差分：禁列域名（models.dev/opencode.ai/sentry/posthog/npmjs 等，e10-egress-inventory §1）
     零命中；未知域名仅当与进程树外联 IP 挂钩才计违规，纯环境再解析登记为 environment
  A4 密钥零落盘（服务密码字节不在产物 JSON 中）
  旁证（不判 PASS/FAIL）：模型轮出站链——服务直连 api.deepseek.com，或经本机代理
     （127.0.0.1:10808，工作区环境事实）出回环、代理远端腿 IP 挂 api.deepseek.com 解析集
     （按进程归属代理腿属本机代理，时间/IP 关联仅作旁证登记，不冒称产品断言）

方法边界（如实）：netstat 是瞬时采样，短命连接可能漏采；DNS 缓存系统级不可按进程归因；
清缓存后其他进程再解析会进差分（按 IP 挂钩归因到进程树与否分环境/违规）；仅 TCP。
复用：implementation/python/opencode_http.py（主树，传输层）、tools/e10_canary.py（主树，金丝雀材料）。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

WORKTREE = Path(__file__).resolve().parents[1]
MAIN_TREE = WORKTREE.parents[2]  # .../juscite/.local/worktrees/<wt> -> .../juscite

PWSH_DEFAULT = (r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\.github-runner\tools"
                r"\PowerShell-7.6.4\pwsh.exe")
REG_PATH = Path(os.path.expandvars(r"%APPDATA%\Juscite\state\opencode\service-local.json"))
SERVICE_ORIGIN = "http://127.0.0.1:43127"
EXPECTED_HOST = "api.deepseek.com"

# e10-egress-inventory.md §1 的默认开/遥测/目录类端点（本负测的禁列）
FORBIDDEN_DNS = [
    "models.dev", "models.opencode.ai", "opencode.ai", "sentry.io", "ingest.sentry.io",
    "posthog.com", "registry.npmjs.org", "npmjs.org", "formulae.brew.sh",
    "tavily.com", "exa.ai", "firecrawl.dev", "search.parallel.ai", "agent.tinyfish.ai",
]
EGRESS_STATES = {"ESTABLISHED", "SYN_SENT", "TIME_WAIT", "CLOSE_WAIT", "FIN_WAIT_1", "FIN_WAIT_2"}
NETSTAT_ROW = re.compile(r"^\s*TCP\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d+)\s*$")


# ---------- 基础采集 ----------

def run(cmd: list[str], timeout: float = 60) -> str:
    out = subprocess.run(cmd, capture_output=True, timeout=timeout)
    return out.stdout.decode("utf-8", errors="replace")


def pwsh_json(ps_script: str, tmp_file: Path) -> list[dict] | dict:
    """pwsh 输出经临时文件收口（UTF-8 确定性），避开控制台代码页。"""
    script = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        + ps_script.replace("__OUT__", str(tmp_file).replace("'", "''"))
        + "; exit 0"
    )
    proc = subprocess.run([PWSH, "-NoProfile", "-Command", script],
                          capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError("pwsh failed: " + proc.stderr.decode("utf-8", errors="replace")[:400])
    text = tmp_file.read_text(encoding="utf-8-sig")
    if not text.strip():
        return []
    data = json.loads(text)
    return data if isinstance(data, list) else [data]


def netstat_rows() -> set[tuple[str, str, str, int]]:
    text = run(["netstat", "-ano", "-p", "tcp"])
    rows = set()
    for line in text.splitlines():
        m = NETSTAT_ROW.match(line)
        if m:
            rows.add((m.group(1), m.group(2), m.group(3), int(m.group(4))))
    return rows


def dns_snapshot(tmp_file: Path) -> set[tuple[str, str, int]]:
    entries = pwsh_json(
        "Get-DnsClientCache | Select-Object Entry,Data,Type | ConvertTo-Json -Compress "
        "| Set-Content -LiteralPath '__OUT__' -Encoding utf8",
        tmp_file)
    out = set()
    for e in entries:
        entry = str(e.get("Entry", "")).rstrip(".").lower()
        data = str(e.get("Data", "")).strip()
        if entry:
            out.add((entry, data, int(e.get("Type") or 0)))
    return out


def proc_snapshot(tmp_file: Path) -> dict[int, dict]:
    procs = pwsh_json(
        "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name "
        "| ConvertTo-Json -Compress | Set-Content -LiteralPath '__OUT__' -Encoding utf8",
        tmp_file)
    return {int(p["ProcessId"]): {"ppid": int(p["ParentProcessId"] or 0), "name": p.get("Name", "?")}
            for p in procs}


def descendants(procs: dict[int, dict], root_pid: int) -> set[int]:
    children: dict[int, list[int]] = {}
    for pid, info in procs.items():
        children.setdefault(info["ppid"], []).append(pid)
    seen, stack = {root_pid}, [root_pid]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def host_of(addr: str) -> str:
    return addr[1:addr.index("]")] if addr.startswith("[") else addr.rsplit(":", 1)[0] if ":" in addr else addr


def is_loopback(addr: str) -> bool:
    h = host_of(addr).lower()
    return h == "::1" or h.startswith("127.")


def resolve_ips(host: str) -> dict[str, list[str]]:
    ips: dict[str, list[str]] = {"v4": [], "v6": []}
    try:
        for info in socket.getaddrinfo(host, 443):
            ip = info[4][0]
            bucket = "v6" if ":" in ip else "v4"
            if ip not in ips[bucket]:
                ips[bucket].append(ip)
    except OSError as exc:
        ips["error"] = [str(exc)]
    return ips


# ---------- 服务探测与自起 ----------

def read_registration() -> dict:
    return json.loads(REG_PATH.read_text(encoding="utf-8"))


def build_client(password: str):
    sys.path.insert(0, str(MAIN_TREE / "implementation" / "python"))
    from opencode_http import Client  # 主树公开传输层
    headers = {"Authorization": "Basic " + base64.b64encode(
        ("opencode:" + password).encode()).decode("ascii")}
    return Client(SERVICE_ORIGIN, headers=headers, timeout=60)


def service_info(password: str) -> dict | None:
    try:
        client = build_client(password)
        payload = client.request("GET", "/api/info")
        return payload.get("data", payload) if isinstance(payload, dict) else None
    except Exception:
        return None


def autostart_service(log_file: Path):
    """服务死时用主树 tools/start_lvyin_service.ps1 拉起（产品拓扑复刻）。返回 launcher 进程。"""
    script = MAIN_TREE / "tools" / "start_lvyin_service.ps1"
    if not script.is_file():
        raise RuntimeError(f"start script missing: {script}")
    log = open(log_file, "wb")
    return subprocess.Popen(
        [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=str(MAIN_TREE), stdout=log, stderr=subprocess.STDOUT)


def wait_service(deadline_s: float) -> dict:
    """等自起服务就绪；注册文件会被重写，轮询时重读。"""
    end = time.time() + deadline_s
    while time.time() < end:
        try:
            reg = read_registration()
        except (OSError, json.JSONDecodeError):
            reg = {}
        info = service_info(reg.get("password", "")) if reg.get("password") else None
        if info:
            return reg
        time.sleep(3)
    raise RuntimeError("autostart timeout: service not ready")


# ---------- 模型轮 ----------

def canary_material(out_dir: Path) -> tuple[str, dict[str, str]]:
    sys.path.insert(0, str(MAIN_TREE / "tools"))
    from e10_canary import material_files, new_token  # T06 VERIFIED 的金丝雀生成器
    token = new_token()
    return token, material_files(token)


def assistant_text(client, session_id: str) -> str | None:
    try:
        listing = client.request("GET", f"/api/session/{quote(session_id, safe='')}/message")
    except Exception:
        return None
    parts = []
    for message in listing.get("data", []) if isinstance(listing, dict) else []:
        if message.get("type") != "assistant":
            continue
        for part in message.get("content", []) or message.get("parts", []):
            if part.get("type") == "text" and part.get("text"):
                parts.append(part["text"])
    return "\n".join(parts) if parts else None


# ---------- 差分与断言 ----------

def classify_dns(dns_diff: list[tuple[str, str, int]], allowed_ips: set[str],
                 service_remote_ips: set[str], deepseek_chain_ips: set[str]):
    """返回 (classified 列表, forbidden_hits, product_linked_unknown)。"""
    classified, forbidden, linked_unknown = [], [], []
    for entry, data, rtype in sorted(dns_diff):
        item = {"entry": entry, "data": data, "type": rtype}
        if any(entry == f or entry.endswith("." + f) for f in FORBIDDEN_DNS):
            item["class"] = "forbidden"
            forbidden.append(item)
        elif "deepseek" in entry or "deepseek" in data.lower() or (
                data and data in deepseek_chain_ips):
            item["class"] = "expected_deepseek"
        elif data in service_remote_ips or (data and data in allowed_ips):
            item["class"] = "product_linked_ip"
            linked_unknown.append(item)
        else:
            item["class"] = "environment"
        classified.append(item)
    return classified, forbidden, linked_unknown


def main() -> int:
    global PWSH
    parser = argparse.ArgumentParser(description="E10 OS 层出站负测（会话期差分，无管理员方案）")
    parser.add_argument("--out", default=str(WORKTREE / "docs" / "construction"
                                             / "e10-session-negtest-result.json"))
    parser.add_argument("--provider", default="deepseek-byok")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--prompt-timeout", type=float, default=240.0)
    parser.add_argument("--autostart-timeout", type=float, default=180.0)
    parser.add_argument("--pwsh", default=PWSH_DEFAULT)
    parser.add_argument("--main-tree", default=str(MAIN_TREE))
    parser.add_argument("--no-autostart", action="store_true", help="服务死时直接 BLOCKED，不拉起")
    parser.add_argument("--no-flush-dns", action="store_true",
                        help="不清 DNS 缓存（默认清，使差分基线干净；系统会自行回填）")
    args = parser.parse_args()
    PWSH = args.pwsh
    main_tree = Path(args.main_tree).resolve()
    if not (main_tree / "implementation" / "python" / "opencode_http.py").is_file():
        print("FAIL: 主树 implementation/python/opencode_http.py 不存在", file=sys.stderr)
        return 2

    ts = int(time.time())
    snap_dir = Path(os.environ.get("TEMP", ".")) / f"juscite-e10-negtest-{ts}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {
        "unit": "E10 OS 层出站负测（会话期差分，无管理员方案）",
        "meta": {
            "tool": "tools/e10_session_negtest.py",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "adjudication": "00-总协调.md §6.1 裁决#2：无管理员方案先行",
            "method": "netstat -ano -p tcp + Get-DnsClientCache 三点快照（前/中/后）差分",
            "snapshot_dir": str(snap_dir),
            "limitations": [
                "netstat 瞬时采样，短命连接可能漏采",
                "DNS 缓存系统级、不可按进程归因，靠进程树外联 IP 挂钩归因",
                "仅 TCP；QUIC/UDP 出站不可见（本断言面为服务 HTTPS 出站）",
                "若服务经本机代理出站，只见回环连接，代理之外远端本方法不可见",
            ],
        },
        "service": {}, "canary": {}, "model_round": {},
        "snapshots": {}, "diff": {}, "assertions": [], "verdict": None,
    }

    def assert_row(aid: str, expected: str, observed, ok: bool) -> None:
        result["assertions"].append(
            {"id": aid, "expected": expected, "observed": observed,
             "result": "PASS" if ok else "FAIL"})

    # ---- ① 活服务 ----
    launcher = None
    try:
        reg = read_registration()
    except (OSError, json.JSONDecodeError):
        reg = {}
    info = service_info(reg.get("password", "")) if reg.get("password") else None
    if info is None:
        if args.no_autostart:
            print(json.dumps({"verdict": "BLOCKED", "reason": "service dead, --no-autostart"},
                             ensure_ascii=False))
            return 2
        print("[negtest] 服务死，主树 start_lvyin_service.ps1 拉起 …", flush=True)
        launcher = autostart_service(snap_dir / "service-start.log")
        reg = wait_service(args.autostart_timeout)
        info = service_info(reg["password"])
    password = reg["password"]
    result["service"] = {
        "started_by_tool": launcher is not None,
        "pid_reg": reg.get("pid"),
        "version": info.get("version"),
        "url": "http://127.0.0.1:43127",  # 只记 origin，不带凭据
        "dev_version": info.get("version") != "2.0.28",
    }

    # 监听 PID 交叉验证（netstat 里 43127 的 LISTENER）
    pre_rows_probe = netstat_rows()
    listeners = {pid for (local, _r, state, pid) in pre_rows_probe
                 if state == "LISTENING" and local.endswith(":43127")}
    service_pid = listeners.pop() if len(listeners) == 1 else reg.get("pid")
    result["service"]["pid_listener"] = service_pid
    result["service"]["pid_match_reg"] = (service_pid == reg.get("pid"))

    client = build_client(password)

    # ---- ② 三次采集：前 ----
    procs_pre = proc_snapshot(snap_dir / "procs-pre.json")
    tree_pre = descendants(procs_pre, int(service_pid)) if service_pid else set()
    if not args.no_flush_dns:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=30)
        result["meta"]["dns_flushed"] = True
    pre = {"netstat": netstat_rows(), "dns": dns_snapshot(snap_dir / "dns-pre.json"),
           "at": time.strftime("%H:%M:%S")}
    result["snapshots"]["pre"] = {"netstat_rows": len(pre["netstat"]),
                                  "dns_entries": len(pre["dns"]), "at": pre["at"]}

    # ---- ③ 金丝雀材料 + DeepSeek 模型轮 ----
    token, materials = canary_material(snap_dir)
    ws = snap_dir / "ws"
    (ws / "materials").mkdir(parents=True, exist_ok=True)
    material_path = ws / "materials" / "material.md"
    material_path.write_text(materials["material.md"], encoding="utf-8")
    (ws / "materials" / "mcp_payload.json").write_text(
        materials["mcp_payload.json"], encoding="utf-8")
    result["canary"] = {"token": token, "material_dir": str(snap_dir),
                        "policy": "只写系统临时目录，不进真实工作区/产品目录"}

    session_id = f"ses_e10neg_{ts}"
    message_id = f"msg_e10neg_{ts}"
    prompt_text = (
        materials["session_input.txt"]
        + "\n随消息附上 material.md，请阅读后回答两行：第一行原样给出材料中的金丝雀标记；"
          "第二行给出假案号。不要展开分析。"
    )
    result["model_round"] = {"provider": args.provider, "model": args.model,
                             "session_id": session_id, "message_id": message_id}

    round_fail: str | None = None
    try:
        client.create({"id": session_id, "title": "律引 E10 出站负测（合成金丝雀）",
                       "location": {"directory": str(ws)},
                       "model": {"id": args.model, "providerID": args.provider}})
        client.prompt(session_id, {"id": message_id, "text": prompt_text,
                                   "model": {"id": args.model, "providerID": args.provider},
                                   "files": [{"uri": material_path.as_uri(),
                                              "name": material_path.name}]})
    except Exception as exc:  # TransportError 等：round 未成立
        round_fail = getattr(exc, "code", None) or type(exc).__name__

    # ---- ② 会话中采样 ----
    mid_netstat: set[tuple[str, str, str, int]] = set()
    mid_dns: set[tuple[str, str, int]] = set()
    answer = None
    if round_fail is None:
        deadline = time.time() + args.prompt_timeout
        t0 = time.time()
        dns_taken = set()
        while time.time() < deadline:
            mid_netstat |= netstat_rows()
            elapsed = time.time() - t0
            for mark in (2.0, 25.0):  # 两个会话中 DNS 采样点
                if elapsed >= mark and mark not in dns_taken:
                    mid_dns |= dns_snapshot(snap_dir / f"dns-mid-{int(mark)}.json")
                    dns_taken.add(mark)
            answer = assistant_text(client, session_id)
            if answer:
                break
            time.sleep(2.0)
    result["model_round"].update({
        "submitted": round_fail is None,
        "fail_code": round_fail,
        "assistant_text_excerpt": (answer or "")[:300],
        "token_echoed_in_answer": bool(answer and token in answer),
    })

    # ---- ② 跑后采集 ----
    post = {"netstat": netstat_rows(), "dns": dns_snapshot(snap_dir / "dns-post.json"),
            "at": time.strftime("%H:%M:%S")}
    procs_post = proc_snapshot(snap_dir / "procs-post.json")
    tree_post = descendants(procs_post, int(service_pid)) if service_pid else set()
    result["snapshots"]["mid"] = {"netstat_rows": len(mid_netstat),
                                  "dns_entries": len(mid_dns)}
    result["snapshots"]["post"] = {"netstat_rows": len(post["netstat"]),
                                   "dns_entries": len(post["dns"]), "at": post["at"]}
    service_tree = {int(p) for p in (tree_pre | tree_post)}
    result["diff"]["service_tree_pids"] = sorted(service_tree)
    result["diff"]["service_tree_names"] = sorted(
        {(procs_pre.get(p) or procs_post.get(p) or {}).get("name") or "?" for p in service_tree})

    # ---- ④ 差分与断言 ----
    allowed = resolve_ips(EXPECTED_HOST)
    allowed_ips = set(allowed.get("v4", [])) | set(allowed.get("v6", []))
    result["allowed"] = {"host": EXPECTED_HOST, **allowed}

    dns_diff = (mid_dns | post["dns"]) - pre["dns"]
    deepseek_chain_ips = {data for (entry, data, _t) in (mid_dns | post["dns"])
                          if "deepseek" in entry}

    during_rows = (mid_netstat | post["netstat"]) - pre["netstat"]
    new_rows, new_listeners = [], []
    proc_all = {**procs_pre, **procs_post}
    for (local, remote, state, pid) in sorted(during_rows):
        row = {"local": local, "remote": remote, "state": state, "pid": pid,
               "proc": proc_all.get(pid, {}).get("name") or ("pid0" if pid == 0 else "?")}
        if state == "LISTENING":
            new_listeners.append(row)
            continue
        if pid in service_tree:
            row["class"] = "service_tree"
            if is_loopback(remote):
                row["verdict"] = "allowed_loopback"
            elif host_of(remote) in allowed_ips:
                row["verdict"] = "allowed_deepseek"
            else:
                row["verdict"] = "violation_unknown_remote"
        elif is_loopback(remote):
            row["class"], row["verdict"] = "loopback_other", "allowed"
        elif pid == 0:
            row["class"], row["verdict"] = "unattributed_pid0", "recorded"
        else:
            row["class"], row["verdict"] = "environment", "environment_noise"
        new_rows.append(row)

    # ---- 代理腿关联（服务→本机代理→远端）：本机环境代理统一 127.0.0.1:10808（00-总协调 §1）----
    # 成对行配对：服务树回环行 (svc_local -> proxy_local) 与代理进程行 (proxy_local -> svc_local)。
    deepseek_ip_pool = allowed_ips | deepseek_chain_ips
    pair_index = {(r["local"], r["remote"]): r for r in new_rows}
    service_loopback_rows = [r for r in new_rows if r["class"] == "service_tree"
                             and r["verdict"] == "allowed_loopback"]
    proxy_pids: set[int] = set()
    for r in service_loopback_rows:
        peer = pair_index.get((r["remote"], r["local"]))
        if peer and peer["pid"] and peer["pid"] not in service_tree:
            r["proxy_peer_pid"] = peer["pid"]
            r["proxy_peer_proc"] = peer["proc"]
            proxy_pids.add(peer["pid"])
    far_leg_rows = []
    for r in new_rows:
        if r["class"] == "environment" and r["pid"] in proxy_pids and not is_loopback(r["remote"]):
            if host_of(r["remote"]) in deepseek_ip_pool:
                r["class"], r["verdict"] = "proxy_far_leg", "allowed_deepseek_via_proxy"
                far_leg_rows.append(r)
    result["diff"]["netstat_new"] = new_rows
    result["diff"]["netstat_new_listeners"] = new_listeners
    result["diff"]["model_round_egress_chain"] = {
        "service_to_loopback_proxy": [
            {k: r[k] for k in ("local", "remote", "state", "pid", "proc", "proxy_peer_proc")}
            for r in service_loopback_rows if "proxy_peer_pid" in r],
        "proxy_processes": sorted(proxy_pids),
        "proxy_far_leg_to_expected": [
            {k: r[k] for k in ("local", "remote", "state", "pid", "proc")} for r in far_leg_rows],
        "proxied_deepseek_egress_observed": bool(far_leg_rows),
        "note": "代理远端腿按进程归属属本机代理（xray 等），时间/IP 与服务轮次关联仅作旁证登记",
    }

    service_remotes = {host_of(r["remote"]) for r in new_rows if r["class"] == "service_tree"}
    reverse: dict[str, str] = {}
    for ip in sorted(service_remotes - {""}):
        try:
            reverse[ip] = socket.gethostbyaddr(ip)[0]
        except OSError:
            reverse[ip] = "<no-ptr>"
    result["diff"]["service_tree_remotes"] = sorted(service_remotes)
    result["diff"]["service_tree_reverse_lookup"] = reverse

    classified, forbidden_hits, linked_unknown = classify_dns(
        dns_diff, allowed_ips, service_remotes, deepseek_chain_ips)
    result["diff"]["dns_new"] = classified
    result["diff"]["dns_new_count"] = len(classified)

    # A1 模型轮完成
    assert_row("A1_model_round_completed", "assistant 文本非空（防空洞 PASS）",
               {"submitted": round_fail is None, "has_answer": bool(answer),
                "fail_code": round_fail}, ok=bool(answer))
    # A2 进程树外联白名单
    a2_bad = [r for r in new_rows if r.get("verdict") == "violation_unknown_remote"]
    assert_row("A2_service_tree_egress_subset_allowed",
               "服务进程树新外联 ⊆ {api.deepseek.com IP} ∪ 回环",
               {"violations": a2_bad, "service_tree_remotes": sorted(service_remotes)},
               ok=not a2_bad)
    # A3 DNS 差分
    assert_row("A3_dns_diff_no_forbidden_no_linked_unknown",
               "禁列域名零命中；未知域名不挂进程树外联 IP",
               {"forbidden": forbidden_hits, "product_linked_unknown": linked_unknown,
                "environment_count": sum(1 for c in classified if c["class"] == "environment")},
               ok=not forbidden_hits and not linked_unknown)
    # A4 密钥零落盘（写盘前检查）；直连旁证不判 PASS/FAIL
    deepseek_observed = bool(service_remotes & allowed_ips)
    result["diff"]["direct_deepseek_egress_observed"] = deepseek_observed

    if round_fail is not None or not answer:
        verdict = "BLOCKED"
    elif a2_bad or forbidden_hits or linked_unknown:
        verdict = "FAIL"
    elif any(c["class"] == "environment" for c in classified) or any(
            r["class"] in ("environment", "unattributed_pid0") for r in new_rows):
        verdict = "PASS_WITH_ENV_NOISE"
    else:
        verdict = "PASS"
    result["verdict"] = verdict
    result["meta"]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    assert_row("A4_no_secret_in_artifact", "服务密码字节不在产物 JSON 中",
               {"checked": True}, ok=password not in payload)
    # 重新序列化以纳入 A5 行自身
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if password in payload:
        print("FAIL: 密钥泄漏进产物，拒绝写盘", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    print(json.dumps({"verdict": verdict, "out": str(out_path),
                      "assertions": {a["id"]: a["result"] for a in result["assertions"]},
                      "direct_deepseek_egress_observed": deepseek_observed,
                      "dns_new": result["diff"]["dns_new_count"]},
                     ensure_ascii=False))

    # ---- 自起服务收尾（你拉起的你负责关；原本就在的不动）----
    if launcher is not None:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(launcher.pid)],
                       capture_output=True, timeout=30)
        time.sleep(2)
        closed = not any(local.endswith(":43127") and state == "LISTENING"
                         for (local, _r, state, _p) in netstat_rows())
        print(json.dumps({"autostart_teardown": "stopped" if closed else "STILL_LISTENING"},
                         ensure_ascii=False))

    return 0 if verdict in ("PASS", "PASS_WITH_ENV_NOISE") else (2 if verdict == "BLOCKED" else 1)


if __name__ == "__main__":
    PWSH = PWSH_DEFAULT
    sys.exit(main())
