"""F39 OS 层出站负测（无管理员先行方案）＋隔离保面核对。

义务来源：docs/construction/authority/06-全量功能施工映射.csv 行 40（F39）与
07-新增必需工程义务.csv 行 40——「OS 层对 DNS/IP/HTTP/socket/子进程负测；清代理不是断网，
依赖 hash 完整性不替隔离；保受限令牌/AppContainer、快照隔离、exe 哈希自校验，
并增加真实 OS 出站负测」；prereq=E10,E11,E12（E11/E12 未到，F39 全销账挂前置）。
裁决依据：docs/construction/00-总协调.md §6.1 裁决#2——无管理员方案先行
（netstat/DNS 缓存差分）；宿主级（netsh trace/pktmon/WFP/防火墙/物理断网）待环境。

本工具做四件事（全合成，不写 %APPDATA%，产品根只读）：
 1. S1 产品服务树面：活服务（127.0.0.1:43127）进程树快照 + 观察窗内 netstat/DNS 三点差分，
    断言窗内服务树无新非回环外联、禁列域名（e10-egress-inventory §1）零命中、
    无新增网络型子进程（子进程负测的无管理员面）；
 2. S2 「清代理≠断网」对照组：合成子进程在**清空代理环境变量**后仍完成
    socket 连接 + HTTP 请求 + DNS 解析（全回环/本机解析，无真实外联）——
    证明"清代理"不等于网络隔离，不能当隔离证据（07 F39 原文口径）；
 3. S3 隔离保面核对（keep-surface，如实 NOT_WIRED_YET 不冒称）：
    - 受限令牌/AppContainer：OS 能力探测（进程令牌组/完整性级别）＋产品侧接线状态=未接线
      （OCR sidecar 尚未施工，F40 NOT_RUN；grep 证据）；
    - 快照隔离：产品配置 snapshots=false（只读读取）＋anonymizer 铁律「inputs are read-only
      snapshots / No network」（其 AGENTS.md 硬规则 3/4）——owner 侧表面在册；
    - exe 哈希自校验：对实际运行的服务解释器 bun.exe 与本工具运行时 python.exe 计算
      SHA-256 并复算核对（自校验机制演示），同时按 07 F39 明文登记「依赖 hash 完整性不替隔离」；
 4. S4 Crashpad 无出站面旁证：Crashpad 目录字节扫描无 submitURL/https 外发地址。

宿主级负测（PENDING_ADMIN_ENV）：断网（飞行模式/WFP 阻断）下行为断言、pktmon/netsh trace
字节级抓包、防火墙规则隔离验证、真实 OCR sidecar 物理断网轮——待管理员/环境，不冒称。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
MAIN_TREE = WORKTREE.parents[2]

sys.path.insert(0, str(WORKTREE / "tools"))
sys.path.insert(0, str(MAIN_TREE / "tools"))
import e10_session_negtest as b0  # noqa: E402  既有采集器复用（VERIFIED）

b0.PWSH = b0.PWSH_DEFAULT
b0.MAIN_TREE = MAIN_TREE

PRODUCT_ROOT = Path(os.environ.get("APPDATA", "")) / "Juscite"
PRODUCT_CONFIG = PRODUCT_ROOT / "config" / "opencode" / "opencode.json"
SIDECHILD = r"""
import json, os, socket, sys, urllib.request
# 合成 sidecar 替身：清代理环境后仍展示网络栈各层可用（全回环，无真实外联）
proxy_keys = [k for k in os.environ if k.lower().endswith("_proxy") or k.lower() == "no_proxy"]
for k in proxy_keys:
    os.environ.pop(k, None)
report = {"proxy_env_after_clear": {k: os.environ.get(k) for k in proxy_keys}}
host, port, mode = sys.argv[1], int(sys.argv[2]), sys.argv[3]
# 层1 socket
s = socket.create_connection((host, port), timeout=5)
report["socket_connect"] = f"{host}:{port} ok"
s.close()
# 层2 HTTP（不走代理 env；opener 显式无代理，回环本来也不走）
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(f"http://{host}:{port}/probe", timeout=5) as resp:
    report["http_get"] = {"status": resp.status, "body": resp.read(64).decode("utf-8", "replace")}
# 层3 DNS 解析（本机解析器；localhost 为本地条目，不产生真实外联查询）
report["dns_resolve"] = socket.getaddrinfo("localhost", None)[0][4][0]
print(json.dumps(report, ensure_ascii=False))
"""


# ---------- 回环探针服务 ----------

def make_probe_handler(store: dict):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            store["hits"] += 1
            body = b"F39-PROBE-OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


# ---------- 保面核对 ----------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def token_groups() -> dict:
    """进程令牌面：完整性级别与 AppContainer 组归属（只读探测，不尝试提权）。"""
    try:
        out = subprocess.run(["whoami", "/groups", "/fo", "csv"], capture_output=True,
                             timeout=30).stdout.decode("gbk", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return {"error": "whoami_failed"}
    labels = [line.split(",")[0].strip('"') for line in out.splitlines() if line.strip()]
    return {"integrity_level": next((l for l in labels if " Mandatory Level" in l), None),
            "in_appcontainer": any("ALL RESTRICTED APPLICATION PACKAGES" in l for l in labels),
            "group_count": len(labels)}


def surface_wiring_search() -> dict:
    """产品侧四个隔离机制的接线状态（grep 只读证据；OCR sidecar 未施工即如实 NOT_WIRED_YET）。"""
    roots = [MAIN_TREE / "implementation", MAIN_TREE / "tools", MAIN_TREE / "docs"]
    needles = {
        "restricted_token_or_appcontainer": re.compile(r"AppContainer|CreateRestrictedToken|受限令牌", re.I),
        "physical_network_block": re.compile(r"物理断网|WFP|netsh\s+trace|pktmon|FIREWALL|防火墙规则", re.I),
        "exe_hash_selfcheck": re.compile(r"哈希自校验|hash.*self.?check|sha256.*verify", re.I),
    }
    found = {k: [] for k in needles}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for key, pattern in needles.items():
                if pattern.search(text):
                    found[key].append(str(path.relative_to(MAIN_TREE)))
    return found


# ---------- 主流程 ----------

def main() -> int:
    parser = argparse.ArgumentParser(description="F39 OS 层出站负测（无管理员先行）＋隔离保面核对")
    parser.add_argument("--out", default=str(WORKTREE / "docs" / "construction"
                                             / "f39-os-egress-negtest-result.json"))
    parser.add_argument("--window", type=float, default=8.0, help="服务树观察窗秒数")
    args = parser.parse_args()

    snap_dir = Path(tempfile.gettempdir()) / f"juscite-f39-{int(time.time())}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {
        "unit": "F39 OS 层出站负测（无管理员先行）＋隔离保面核对",
        "meta": {
            "tool": "tools/f39_os_egress_negtest.py",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "adjudication": "00-总协调.md §6.1 裁决#2：无管理员方案先行；宿主级待环境",
            "prerequisites": {"E10": "IMPLEMENTING（B0 会话级 PASS；B2 字节级见 e10-byte-negtest-result.json）",
                              "E11": "NOT_RUN", "E12": "NOT_RUN"},
            "pending_admin_env": [
                "断网（飞行模式/WFP 阻断）下产品行为负测",
                "pktmon/netsh trace 宿主级字节抓包",
                "防火墙规则隔离验证",
                "真实 OCR sidecar 物理断网轮（sidecar 未施工，挂 F40 及后续）",
            ],
            "snapshot_dir": str(snap_dir),
        },
        "service": {}, "control": {}, "surface": {}, "diff": {},
        "assertions": [], "verdict": None,
    }

    def assert_row(aid: str, expected: str, observed, ok: bool) -> None:
        result["assertions"].append({"id": aid, "expected": expected, "observed": observed,
                                     "result": "PASS" if ok else "FAIL"})

    # ---- S1 产品服务树面 ----
    try:
        reg = b0.read_registration()
    except (OSError, json.JSONDecodeError):
        reg = {}
    probe_rows = b0.netstat_rows()
    listeners = {pid for (local, _r, state, pid) in probe_rows
                 if state == "LISTENING" and local.endswith(":43127")}
    if not listeners:
        print(json.dumps({"verdict": "BLOCKED", "reason": "service not listening (43127)"},
                         ensure_ascii=False))
        return 2
    service_pid = listeners.pop()
    procs_pre = b0.proc_snapshot(snap_dir / "procs-pre.json")
    tree_pre = b0.descendants(procs_pre, int(service_pid))
    result["service"] = {"pid": service_pid, "started_by_tool": False,
                         "tree_pids": sorted(tree_pre),
                         "tree_names": sorted({(procs_pre.get(p) or {}).get("name") or "?"
                                               for p in tree_pre})}
    subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=30)
    pre = {"netstat": b0.netstat_rows(), "dns": b0.dns_snapshot(snap_dir / "dns-pre.json")}

    # ---- S2 清代理≠断网对照（观察窗内并行跑合成 sidecar 替身） ----
    store = {"hits": 0}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_probe_handler(store))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = "127.0.0.1", srv.server_address[1]
    child_src = snap_dir / "f39_sidechild.py"
    child_src.write_text(SIDECHILD, encoding="utf-8")
    env_clean = {k: v for k, v in os.environ.items()
                 if not k.lower().endswith("_proxy") and k.lower() != "no_proxy"}
    child = subprocess.run([sys.executable, "-X", "utf8", str(child_src), host, str(port), "probe"],
                           capture_output=True, timeout=60, cwd=str(snap_dir), env=env_clean)
    control = {"proxy_env_cleared": True, "exit": child.returncode,
               "probe_hits": store["hits"]}
    try:
        control["child_report"] = json.loads(child.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        control["child_report"] = None
        control["stderr"] = child.stderr.decode("utf-8", errors="replace")[:300]
    result["control"] = control

    # 观察窗（子进程已结束；窗内采样服务面）
    deadline = time.time() + args.window
    mid_netstat: set = set()
    while time.time() < deadline:
        mid_netstat |= b0.netstat_rows()
        time.sleep(2.0)
    post = {"netstat": b0.netstat_rows(), "dns": b0.dns_snapshot(snap_dir / "dns-post.json")}
    procs_post = b0.proc_snapshot(snap_dir / "procs-post.json")
    tree_post = b0.descendants(procs_post, int(service_pid))
    proc_all = {**procs_pre, **procs_post}
    service_tree = {int(p) for p in (tree_pre | tree_post)}

    during = (mid_netstat | post["netstat"]) - pre["netstat"]
    new_rows, new_tree_procs = [], sorted(tree_post - tree_pre)
    for (local, remote, state, pid) in sorted(during):
        row = {"local": local, "remote": remote, "state": state, "pid": pid,
               "proc": proc_all.get(pid, {}).get("name") or ("pid0" if pid == 0 else "?")}
        if state == "LISTENING":
            continue
        if pid in service_tree:
            row["class"] = "service_tree"
            row["verdict"] = "allowed_loopback" if b0.is_loopback(remote) else "violation_non_loopback"
        elif b0.is_loopback(remote):
            row["class"], row["verdict"] = "loopback_other", "allowed"
        elif pid == 0:
            row["class"], row["verdict"] = "unattributed_pid0", "recorded"
        else:
            row["class"], row["verdict"] = "environment", "environment_noise"
        new_rows.append(row)
    dns_diff = post["dns"] - pre["dns"]
    service_remotes = {b0.host_of(r["remote"]) for r in new_rows if r["class"] == "service_tree"}
    classified_dns, forbidden_hits, linked_unknown = b0.classify_dns(
        dns_diff, set(), service_remotes, set())
    result["diff"] = {"netstat_new": new_rows, "dns_new": classified_dns,
                      "tree_new_processes": new_tree_procs}
    srv.shutdown()

    # ---- S3 隔离保面核对 ----
    surface: dict = result["surface"]
    surface["process_token"] = token_groups()
    wiring = surface_wiring_search()
    surface["wiring_search"] = wiring
    snapshots_disabled = None
    try:
        cfg_text = PRODUCT_CONFIG.read_text(encoding="utf-8")
        snapshots_disabled = json.loads(cfg_text).get("snapshots") is False
    except (OSError, json.JSONDecodeError):
        pass
    surface["product_snapshots_false"] = snapshots_disabled
    exe_hashes = {}
    # 服务解释器路径：直接问 Win32_Process ExecutablePath（服务 pid 亲测），where 兜底
    bun_path = None
    try:
        rows = b0.pwsh_json(
            "Get-CimInstance Win32_Process -Filter \"ProcessId=" + str(service_pid) + "\" "
            "| Select-Object ExecutablePath | ConvertTo-Json -Compress "
            "| Set-Content -LiteralPath '__OUT__' -Encoding utf8",
            snap_dir / "svc-exe.json")
        bun_path = (rows[0] or {}).get("ExecutablePath") if rows else None
    except Exception:
        bun_path = None
    if not bun_path:
        try:
            out = subprocess.run(["where", "bun"], capture_output=True, timeout=15
                                 ).stdout.decode("gbk", errors="replace").splitlines()
            bun_path = out[0].strip() if out else None
        except (OSError, subprocess.TimeoutExpired):
            pass
    for label, path in (("bun_service_exe", bun_path), ("python_tool_exe", sys.executable)):
        if path and Path(path).is_file():
            exe_hashes[label] = {"path": path, "sha256": sha256_file(Path(path))}
    # 自校验机制演示：复算一遍必须逐字节一致
    surface["exe_hash_selfcheck"] = {
        "hashes": exe_hashes,
        "recheck_match": all(h["sha256"] == sha256_file(Path(h["path"])) for h in exe_hashes.values()),
        "policy_note": "依赖 hash 完整性不替隔离（07 F39 原文）；哈希面仅为完整性自证",
    }
    surface["mechanism_status"] = {
        "restricted_token_appcontainer": "OS 能力可探测（见 process_token）；产品侧未接线"
                                         "（OCR sidecar 未施工，F40 NOT_RUN）——NOT_WIRED_YET 如实",
        "snapshot_isolation": f"产品配置 snapshots={'false（读自产品配置，只读）' if snapshots_disabled else snapshots_disabled}"
                              "；anonymizer 铁律 inputs are read-only snapshots + No network"
                              "（legal-cn-anonymizer AGENTS.md 硬规则 3/4）；sidecar 级快照隔离 NOT_WIRED_YET",
        "exe_hash_selfcheck": "机制演示落地（本工具）；产品链未接线——NOT_WIRED_YET 如实",
        "physical_network_isolation": "无管理员不可验（WFP/防火墙需管理员）——PENDING_ADMIN_ENV",
    }

    # ---- S4 Crashpad 无出站面旁证 ----
    crash_dir = PRODUCT_ROOT / "Crashpad"
    crash_urls: list[str] = []
    crash_scanned = 0
    if crash_dir.is_dir():
        for path in crash_dir.rglob("*"):
            if path.is_file():
                try:
                    data = path.read_bytes()
                except OSError:
                    continue
                crash_scanned += 1
                crash_urls += [m.decode("ascii", errors="replace")
                               for m in re.findall(rb"https?://[A-Za-z0-9._:/-]{4,}", data)]
    surface["crashpad"] = {"scanned_files": crash_scanned, "urls_found": sorted(set(crash_urls))}

    # ---- 断言 ----
    tree_bad = [r for r in new_rows if r["class"] == "service_tree"
                and r["verdict"] == "violation_non_loopback"]
    assert_row("F1_service_tree_no_non_loopback_egress",
               "观察窗内服务进程树无新非回环外联",
               {"violations": tree_bad}, ok=not tree_bad)
    assert_row("F2_dns_no_forbidden_no_linked_unknown",
               "DNS 差分禁列域名零命中且无挂钩未知域名",
               {"forbidden": forbidden_hits, "product_linked_unknown": linked_unknown},
               ok=not forbidden_hits and not linked_unknown)
    assert_row("F3_no_new_network_subprocess",
               "观察窗内服务树无新增子进程（子进程负测无管理员面）",
               {"tree_new_processes": new_tree_procs}, ok=not new_tree_procs)
    control_ok = (control["exit"] == 0 and control["probe_hits"] >= 1
                  and control["child_report"] is not None
                  and control["child_report"].get("socket_connect", "").endswith("ok")
                  and control["child_report"].get("http_get", {}).get("status") == 200)
    assert_row("F4_proxy_clear_not_network_off",
               "清代理后网络栈仍可用（socket+HTTP+DNS 全通）→ 清代理≠断网",
               {"child_exit": control["exit"], "probe_hits": control["probe_hits"],
                "child_report": control["child_report"]}, ok=control_ok)
    surface_ok = (surface["exe_hash_selfcheck"]["recheck_match"] and exe_hashes
                  and surface["crashpad"]["urls_found"] == [])
    assert_row("F5_surface_recheck_and_crashpad_clean",
               "exe 哈希自校验复算一致；Crashpad 无外发 URL 字节",
               {"exe_hashes": {k: v["sha256"][:16] + "…" for k, v in exe_hashes.items()},
                "crashpad_urls": surface["crashpad"]["urls_found"]}, ok=surface_ok)
    assert_row("F6_mechanism_status_recorded",
               "四个隔离机制状态如实登记（未接线=NOT_WIRED_YET，宿主级=PENDING_ADMIN_ENV，不冒称）",
               surface["mechanism_status"], ok=True)

    failed = [a for a in result["assertions"] if a["result"] == "FAIL"]
    result["verdict"] = "FAIL" if failed else (
        "PASS_WITH_ENV_NOISE" if any(r["class"] in ("environment", "unattributed_pid0")
                                     for r in new_rows) or
        any(c["class"] == "environment" for c in classified_dns) else "PASS")
    result["meta"]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": result["verdict"], "out": str(out_path),
                      "assertions": {a["id"]: a["result"] for a in result["assertions"]}},
                     ensure_ascii=False))
    return 0 if result["verdict"] in ("PASS", "PASS_WITH_ENV_NOISE") else 1


if __name__ == "__main__":
    sys.exit(main())
