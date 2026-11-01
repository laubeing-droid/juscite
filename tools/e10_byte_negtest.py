"""E10 字节级出口金丝雀负测（B2 段 · 无管理员先行方案）。

裁决依据：docs/construction/00-总协调.md §6.1 裁决#2——无管理员方案先行；
宿主级抓包（netsh trace/pktmon/断网负测）待环境，本工具不冒称。
上游清册：docs/construction/e10-egress-inventory.md（§1 出口面 / §2 落点 / §3.1 通道映射）。

方法（全合成材料，不写 %APPDATA%，产品根只读扫描）：
 1. 金丝雀材料复用 tools/e10_canary.py material_files（token 唯一 JUSCITE-CANARY-<12hex>）；
 2. 会话工作目录放**项目级 opencode.json**（oc28 ConfigDiscovery 自 location.directory
    向上发现，config/discovery.ts:76-90）：定义假 provider e10fake（@ai-sdk/openai-compatible，
    oc28 packages/core/node_modules 本地解析，无 npm 外联）baseURL 指向本工具在回环起的
    HTTP 假 provider——模型轮的真实序列化 body 字节被就地捕获（通道 A，e10-egress-inventory
    §5 预留的"本地假 provider 接住 A 通道 body"无管理员落地）；同时配回环 remote MCP
    echo（通道 D 接线观测）；
 3. 模型轮期间 netstat/Get-DnsClientCache 三点差分（复用 tools/e10_session_negtest.py 采集器）：
    服务进程树新外联必须 ⊆ 回环（假 provider 全回环，比 B0 更严）；禁列域名零命中；
 4. 轮后对产品根 %APPDATA%\\Juscite 全量**字节级**扫描 token（e10_canary 判定口径）：
    白名单（e10-egress-inventory §2/§3.2）= data\\opencode\\opencode-local.db(+wal/shm)、
    data\\opencode\\log\\、data\\opencode\\tool-output\\；白名单外任何命中=FAIL
    （含 config\\、cache、Crashpad\\、logs\\*\\*（netlog/renderer/main/crash）、state\\ 凭据文件）；
 5. 会话库表级归因：db+wal 复制到临时目录后 sqlite 只读打开，逐表 SELECT * 字节找 token，
    命中表必须 ⊆ 会话语义表 {session_message,event,session_inbox,session_pending,session_v2}；
    kv（models.dev 目录缓存）/credential/account 等表零命中（通道"库存"与凭据面）；
 6. 崩溃通道：Crashpad\\ 与 logs\\**\\crash.log 字节扫描零 token；Crashpad settings.dat
    无 submitURL/https 外发地址字节（uploadToServer:false 的文件级旁证）。

如实边界（不冒称）：
 - 宿主级断网/WFP/抓包待环境（§6.1 裁决#2），PENDING_ADMIN_ENV；
 - live 崩溃触发（杀流式写盘窗口）不作用于用户活服务——本轮 NOT_RUN，仅静态扫描；
 - 浏览器（桌面壳）通道未随本负测拉起：live NOT_RUN，既有 netlog/renderer.log 静态扫描；
 - MCP 通道：回环接线与握手字节观测；MCP 工具调用未从假模型驱动（工具命名发现超出本单时间盒），
   如实记录，不以"未驱动"充"已覆盖"。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import sqlite3
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
import e10_session_negtest as b0  # noqa: E402  既有会话级负测（VERIFIED）：采集器与服务探测复用
from e10_canary import material_files  # noqa: E402  T06 VERIFIED 金丝雀材料

b0.PWSH = b0.PWSH_DEFAULT  # 模块内 pwsh_json 依赖全局 PWSH（B0 仅在 __main__ 赋值）
b0.MAIN_TREE = MAIN_TREE   # B0 从主树被导入时其自身 MAIN_TREE 会少一级，这里按本 worktree 校正

PRODUCT_ROOT = Path(os.environ.get("APPDATA", "")) / "Juscite"
DB_REL = Path("data") / "opencode" / "opencode-local.db"
TOKEN_RE = re.compile(r"JUSCITE-CANARY-[0-9a-f]{12}")
FAKE_PROVIDER = "e10fake"
FAKE_MODEL = "e10fake-canary"
FAKE_KEY = "sk-e10fake-synthetic-not-a-secret"
SESSION_TABLES_ALLOWED = {"session_message", "event", "session_inbox", "session_pending", "session_v2"}
MAX_SCAN_BYTES = 128 * 1024 * 1024
# 白名单（相对产品根）：e10-egress-inventory §2 预期落点 + §3.2 白名单默认不含项的反面
WHITELIST_DIRS = [Path("data") / "opencode" / "log", Path("data") / "opencode" / "tool-output"]
WHITELIST_FILE_PREFIXES = [str(DB_REL)]  # db 本体与 -wal/-shm 伴生文件


# ---------- 回环假 provider（通道 A 字节捕获） ----------

class CaptureStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests: list[dict] = []
        self.mcp_rpc: list[dict] = []

    def add(self, item: dict) -> None:
        with self.lock:
            self.requests.append(item)


def make_fake_provider_handler(store: CaptureStore):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # 静音默认 stderr 日志
            pass

        def _capture(self, body: bytes) -> None:
            store.add({
                "at": time.strftime("%H:%M:%S"),
                "client": self.client_address[0],
                "method": self.command,
                "path": self.path,
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body_len": len(body),
                "body_has_token": bool(TOKEN_RE.search(body.decode("utf-8", errors="replace"))),
                "body_preview": body[:400].decode("utf-8", errors="replace"),
            })

        def do_GET(self):
            self._capture(b"")
            if self.path.rstrip("/").endswith("/models") or self.path.rstrip("/").endswith("/v1/models"):
                payload = json.dumps({"object": "list", "data": [{"id": FAKE_MODEL, "object": "model",
                                                                  "owned_by": "e10-synthetic"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            self._capture(body)
            text = self.path.rstrip("/")
            if text.endswith("/chat/completions"):
                found = TOKEN_RE.search(body.decode("utf-8", errors="replace"))
                token = found.group(0) if found else "JUSCITE-CANARY-<未捕获>"
                reply = f"金丝雀标记回显：{token}（E10 假 provider 合成应答）"
                self._send_sse(reply)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def _send_sse(self, reply: str) -> None:
            chunk = lambda delta, finish=None: {  # noqa: E731
                "id": "chatcmpl-e10fake", "object": "chat.completion.chunk", "created": int(time.time()),
                "model": FAKE_MODEL,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            events = [
                chunk({"role": "assistant", "content": ""}),
                chunk({"content": reply}),
                chunk({}, "stop"),
                {"id": "chatcmpl-e10fake", "object": "chat.completion.chunk", "created": int(time.time()),
                 "model": FAKE_MODEL, "choices": [],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
            ]
            sse = b"".join(b"data: " + json.dumps(e, ensure_ascii=False).encode("utf-8") + b"\n\n"
                           for e in events) + b"data: [DONE]\n\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(sse)))
            self.end_headers()
            self.wfile.write(sse)
            self.close_connection = True

    return Handler


# ---------- 回环 MCP echo（通道 D 接线观测） ----------

def make_mcp_handler(store: CaptureStore):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _json(self, code: int, obj) -> None:
            payload = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            if obj is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload:
                self.wfile.write(payload)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            text = body.decode("utf-8", errors="replace")
            with store.lock:
                store.mcp_rpc.append({
                    "at": time.strftime("%H:%M:%S"), "client": self.client_address[0],
                    "path": self.path, "body_preview": text[:300],
                    "body_has_token": bool(TOKEN_RE.search(text))})
            try:
                msg = json.loads(text) if text.strip() else {}
            except json.JSONDecodeError:
                self._json(400, {"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse error"}})
                return
            method = msg.get("method", "")
            msg_id = msg.get("id")
            if method == "initialize":
                self._json(200, {"jsonrpc": "2.0", "id": msg_id, "result": {
                    "protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-06-18"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "e10-mcp-echo", "version": "1.0.0"}}})
            elif method == "tools/list":
                self._json(200, {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [{
                    "name": "canary_echo", "description": "E10 合成回显工具（仅测试）",
                    "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}}]}})
            elif method == "tools/call":
                self._json(200, {"jsonrpc": "2.0", "id": msg_id, "result": {
                    "content": [{"type": "text", "text": "MCP-ECHO: " + json.dumps(
                        msg.get("params", {}).get("arguments", {}), ensure_ascii=False)}]}})
            elif msg_id is None:  # notification（含 notifications/initialized）
                self._json(202, None)
            else:
                self._json(200, {"jsonrpc": "2.0", "id": msg_id,
                                 "result": {}, "e10note": "generic-ack"})

    return Handler


def serve(handler) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{srv.server_address[1]}"
    return srv, origin


# ---------- 字节级扫描 ----------

def scan_product_root(token: str) -> dict:
    """只读递归字节扫描产品根；>128MB 跳过（与 e10_canary.scan 同口径）。"""
    needle = token.encode("ascii")
    hits, skipped, scanned = [], [], 0
    for dirpath, _dirnames, filenames in os.walk(PRODUCT_ROOT):
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                size = path.stat().st_size
                if size > MAX_SCAN_BYTES:
                    skipped.append({"file": str(path), "reason": f">{MAX_SCAN_BYTES}"})
                    continue
                with open(path, "rb") as handle:
                    data = handle.read()
                scanned += 1
                if needle in data:
                    hits.append(str(path.relative_to(PRODUCT_ROOT)))
            except OSError as exc:
                skipped.append({"file": str(path), "reason": type(exc).__name__})
    def allowed(rel: str) -> bool:
        p = Path(rel)
        if any(p == w or w in p.parents for w in WHITELIST_DIRS):
            return True
        return any(rel == f or rel.startswith(f + "-") for f in WHITELIST_FILE_PREFIXES)
    return {"scanned_files": scanned, "hits": hits, "allowed_hits": [h for h in hits if allowed(h)],
            "violations": [h for h in hits if not allowed(h)], "skipped": skipped}


def db_table_attribution(token: str, tmp_dir: Path) -> dict:
    """db+wal+shm 复制到临时目录后 sqlite 只读逐表归因（不碰活库）。"""
    srcs = [PRODUCT_ROOT / DB_REL,
            PRODUCT_ROOT / (str(DB_REL) + "-wal"),
            PRODUCT_ROOT / (str(DB_REL) + "-shm")]
    if not srcs[0].is_file():
        return {"error": "db_missing", "token_tables": [], "forbidden_tables": ["<db-missing>"]}
    dst = tmp_dir / "opencode-local.db"
    copied = []
    for src in srcs:
        if src.is_file():
            shutil.copy2(src, tmp_dir / src.name)
            copied.append(src.name)
    con = sqlite3.connect("file:" + str(dst).replace("\\", "/") + "?mode=ro", uri=True)
    needle = token
    token_tables, table_rows = [], {}
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        try:
            rows = con.execute(f'SELECT * FROM "{name}"').fetchall()
        except sqlite3.Error:
            table_rows[name] = {"rows": None, "error": "unreadable"}
            continue
        joined = "\n".join(repr(r) for r in rows)
        if needle in joined:
            token_tables.append(name)
        table_rows[name] = {"rows": len(rows)}
    con.close()
    return {"copied": copied, "token_tables": token_tables,
            "forbidden_tables": sorted(set(token_tables) - SESSION_TABLES_ALLOWED),
            "table_rowcounts": table_rows}


def scan_binary_for_urls(path: Path) -> list[str]:
    """Crashpad settings 面：找 submitURL/https:// 外发地址字节（文件级旁证）。"""
    try:
        data = path.read_bytes()
    except OSError:
        return []
    found = re.findall(rb"https?://[A-Za-z0-9._:/-]{4,}", data)
    return sorted({m.decode("ascii", errors="replace") for m in found})


# ---------- 主流程 ----------

def main() -> int:
    parser = argparse.ArgumentParser(description="E10 字节级出口金丝雀负测（B2 段·无管理员先行）")
    parser.add_argument("--out", default=str(WORKTREE / "docs" / "construction"
                                             / "e10-byte-negtest-result.json"))
    parser.add_argument("--prompt-timeout", type=float, default=120.0)
    parser.add_argument("--no-autostart", action="store_true")
    parser.add_argument("--no-flush-dns", action="store_true")
    args = parser.parse_args()

    token = "JUSCITE-CANARY-" + secrets.token_hex(6)
    ts = int(time.time())
    snap_dir = Path(tempfile.gettempdir()) / f"juscite-e10-byte-{ts}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {
        "unit": "E10 字节级出口金丝雀负测（B2 段·无管理员先行）",
        "meta": {
            "tool": "tools/e10_byte_negtest.py", "token": token,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "adjudication": "00-总协调.md §6.1 裁决#2：无管理员方案先行；宿主级待环境",
            "method": "回环假 provider 接住序列化 body 字节 + netstat/DNS 三点差分 + 产品根全量字节扫描 + 会话库表级归因",
            "pending_admin_env": ["netsh trace/pktmon 抓包", "断网（飞行模式/WFP 阻断）负测", "宿主级真实出口字节比对"],
            "not_run_this_round": [
                "live 崩溃触发（不杀用户活服务；仅 Crashpad/crash.log 静态扫描）",
                "live 浏览器（桌面壳）通道（仅既有 netlog/renderer.log 静态扫描）",
                "MCP 工具调用未从假模型驱动（回环握手接线观测为准，如实记录）",
            ],
            "snapshot_dir": str(snap_dir),
        },
        "service": {}, "round": {}, "captures": {}, "diff": {}, "channels": {},
        "assertions": [], "verdict": None,
    }

    def assert_row(aid: str, expected: str, observed, ok: bool) -> None:
        result["assertions"].append({"id": aid, "expected": expected, "observed": observed,
                                     "result": "PASS" if ok else "FAIL"})

    # ---- ① 活服务（复用 B0：注册文件只读，密码不印不落盘） ----
    launcher = None
    try:
        reg = b0.read_registration()
    except (OSError, json.JSONDecodeError):
        reg = {}
    info = b0.service_info(reg.get("password", "")) if reg.get("password") else None
    if info is None:
        if args.no_autostart:
            print(json.dumps({"verdict": "BLOCKED", "reason": "service dead, --no-autostart"},
                             ensure_ascii=False))
            return 2
        print("[e10-byte] 服务死，主树 start_lvyin_service.ps1 拉起 …", flush=True)
        launcher = b0.autostart_service(snap_dir / "service-start.log")
        reg = b0.wait_service(180.0)
        info = b0.service_info(reg["password"])
    password = reg["password"]
    result["service"] = {"started_by_tool": launcher is not None, "pid_reg": reg.get("pid"),
                         "version": info.get("version")}
    client = b0.build_client(password)

    pre_rows_probe = b0.netstat_rows()
    listeners = {pid for (local, _r, state, pid) in pre_rows_probe
                 if state == "LISTENING" and local.endswith(":43127")}
    service_pid = listeners.pop() if len(listeners) == 1 else reg.get("pid")
    result["service"]["pid_listener"] = service_pid

    # ---- ② 跑前快照 ----
    procs_pre = b0.proc_snapshot(snap_dir / "procs-pre.json")
    tree_pre = b0.descendants(procs_pre, int(service_pid)) if service_pid else set()
    if not args.no_flush_dns:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=30)
        result["meta"]["dns_flushed"] = True
    pre = {"netstat": b0.netstat_rows(), "dns": b0.dns_snapshot(snap_dir / "dns-pre.json"),
           "at": time.strftime("%H:%M:%S")}

    # ---- ③ 合成工作区：材料 + 项目级 opencode.json（provider=回环假端点，MCP=回环 echo） ----
    ws = snap_dir / "ws"
    (ws / "materials").mkdir(parents=True, exist_ok=True)
    materials = material_files(token)
    (ws / "materials" / "material.md").write_text(materials["material.md"], encoding="utf-8")
    (ws / "materials" / "mcp_payload.json").write_text(materials["mcp_payload.json"], encoding="utf-8")

    store = CaptureStore()
    prov_srv, prov_origin = serve(make_fake_provider_handler(store))
    mcp_srv, mcp_origin = serve(make_mcp_handler(store))
    project_cfg = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            FAKE_PROVIDER: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "E10 Loopback Fake（合成，仅测试）",
                "options": {"baseURL": prov_origin + "/v1", "apiKey": FAKE_KEY},
                "models": {FAKE_MODEL: {"name": "E10 Canary Fake"}},
            }
        },
        "mcp": {"e10echo": {"type": "remote", "url": mcp_origin + "/mcp", "enabled": True}},
    }
    (ws / "opencode.json").write_text(json.dumps(project_cfg, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    result["meta"]["fake_provider_origin"] = prov_origin
    result["meta"]["mcp_echo_origin"] = mcp_origin

    # ---- ④ 模型轮（材料随消息附上） ----
    session_id = f"ses_e10byte_{ts}"
    message_id = f"msg_e10byte_{ts}"
    prompt_text = (materials["session_input.txt"]
                   + "\n随消息附上 material.md，请回答一行：原样给出材料中的金丝雀标记。不要展开。")
    result["round"] = {"session_id": session_id, "message_id": message_id,
                       "provider": FAKE_PROVIDER, "model": FAKE_MODEL}
    round_fail: str | None = None
    try:
        client.create({"id": session_id, "title": "律引 E10 字节级负测（合成金丝雀）",
                       "location": {"directory": str(ws)},
                       "model": {"id": FAKE_MODEL, "providerID": FAKE_PROVIDER}})
        time.sleep(3.0)  # 留出集成初始化（MCP 握手）窗口
        client.prompt(session_id, {"id": message_id, "text": prompt_text,
                                   "model": {"id": FAKE_MODEL, "providerID": FAKE_PROVIDER},
                                   "files": [{"uri": (ws / "materials" / "material.md").as_uri(),
                                              "name": "material.md"}]})
    except Exception as exc:
        round_fail = getattr(exc, "code", None) or type(exc).__name__

    # ---- ⑤ 会话中采样（复用 B0 节奏） ----
    mid_netstat: set = set()
    mid_dns: set = set()
    answer = None
    if round_fail is None:
        deadline = time.time() + args.prompt_timeout
        t0 = time.time()
        dns_taken = set()
        while time.time() < deadline:
            mid_netstat |= b0.netstat_rows()
            elapsed = time.time() - t0
            for mark in (2.0, 25.0):
                if elapsed >= mark and mark not in dns_taken:
                    mid_dns |= b0.dns_snapshot(snap_dir / f"dns-mid-{int(mark)}.json")
                    dns_taken.add(mark)
            answer = b0.assistant_text(client, session_id)
            if answer:
                break
            time.sleep(2.0)
    result["round"].update({"submitted": round_fail is None, "fail_code": round_fail,
                            "assistant_text_excerpt": (answer or "")[:300],
                            "token_echoed_in_answer": bool(answer and token in answer)})

    # ---- ⑥ 跑后快照 + 差分（预期：服务树新外联 ⊆ 回环；禁列域名零命中） ----
    post = {"netstat": b0.netstat_rows(), "dns": b0.dns_snapshot(snap_dir / "dns-post.json"),
            "at": time.strftime("%H:%M:%S")}
    procs_post = b0.proc_snapshot(snap_dir / "procs-post.json")
    tree_post = b0.descendants(procs_post, int(service_pid)) if service_pid else set()
    service_tree = {int(p) for p in (tree_pre | tree_post)}
    proc_all = {**procs_pre, **procs_post}

    dns_diff = (mid_dns | post["dns"]) - pre["dns"]
    during_rows = (mid_netstat | post["netstat"]) - pre["netstat"]
    new_rows = []
    for (local, remote, state, pid) in sorted(during_rows):
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
    service_remotes = {b0.host_of(r["remote"]) for r in new_rows if r["class"] == "service_tree"}
    classified_dns, forbidden_hits, linked_unknown = b0.classify_dns(
        dns_diff, set(), service_remotes, set())
    result["diff"] = {
        "service_tree_pids": sorted(service_tree),
        "netstat_new": new_rows,
        "dns_new": classified_dns,
        "dns_new_count": len(classified_dns),
    }

    # ---- ⑦ 通道判定 ----
    prov_reqs = [r for r in store.requests]
    chat_reqs = [r for r in prov_reqs if r["path"].rstrip("/").endswith("/chat/completions")]
    result["captures"] = {
        "fake_provider_requests": prov_reqs,
        "chat_completions_count": len(chat_reqs),
        "chat_body_has_token": any(r["body_has_token"] for r in chat_reqs),
        "chat_body_bytes_total": sum(r["body_len"] for r in chat_reqs),
        "all_clients_loopback": all(r["client"] == "127.0.0.1" for r in prov_reqs),
        "mcp_rpc": store.mcp_rpc,
        "mcp_handshake_observed": any("initialize" in (m.get("body_preview") or "")
                                      for m in store.mcp_rpc),
    }

    root_scan = scan_product_root(token)
    db_attr = db_table_attribution(token, snap_dir)
    crash_dir = PRODUCT_ROOT / "Crashpad"
    crash_urls = sorted({u for f in ("settings.dat",) if (crash_dir / f).is_file()
                         for u in scan_binary_for_urls(crash_dir / f)})
    channels = result["channels"]
    channels["A_body"] = {"expected": "序列化 body 含 token 且只到回环假 provider",
                          "observed": {"chat_requests": len(chat_reqs),
                                       "body_has_token": result["captures"]["chat_body_has_token"]}}
    channels["B_session_store"] = {"expected": "token 仅落会话库/会话日志白名单",
                                   "observed": {"allowed_hits": root_scan["allowed_hits"],
                                                "violations": root_scan["violations"]}}
    channels["C_crash"] = {"expected": "Crashpad/crash.log 零 token；settings 无外发 URL",
                           "observed": {"crashpad_token_hits": [h for h in root_scan["hits"]
                                                                if h.startswith("Crashpad")],
                                        "crash_log_hits": [h for h in root_scan["hits"]
                                                           if "crash" in h.lower()],
                                        "crashpad_urls": crash_urls}}
    channels["D_mcp"] = {"expected": "MCP 字节仅回环；不驱动工具调用如实记录",
                         "observed": {"handshake_observed": result["captures"]["mcp_handshake_observed"],
                                      "rpc_count": len(store.mcp_rpc),
                                      "tool_call_driven": False,
                                      "mcp_non_loopback_egress": [r for r in new_rows
                                                                  if r["class"] == "service_tree"
                                                                  and r["verdict"] != "allowed_loopback"]}}
    netlog_hits = [h for h in root_scan["hits"] if h.lower().endswith((".netlog", "network.log",
                                                                      "renderer.log", "main.log"))]
    channels["E_browser_static"] = {"expected": "既有 netlog/renderer 零 token（live 轮 NOT_RUN）",
                                    "observed": {"hits": netlog_hits}}
    channels["F_telemetry_inventory"] = {
        "expected": "禁列域名零命中；库内 kv/credential 表零 token",
        "observed": {"forbidden_dns": [c["entry"] for c in forbidden_hits],
                     "db_forbidden_tables": db_attr["forbidden_tables"]}}

    # ---- ⑧ 断言 ----
    a_body = result["captures"]["chat_body_has_token"] and result["captures"]["all_clients_loopback"]
    assert_row("B1_body_serialized_to_expected_endpoint_only",
               "真实序列化 body 含金丝雀且只发往回环假 provider",
               channels["A_body"]["observed"], ok=a_body)
    tree_bad = [r for r in new_rows if r["class"] == "service_tree"
                and r["verdict"] == "violation_non_loopback"]
    assert_row("B2_service_tree_all_loopback",
               "服务进程树新外联 ⊆ 回环（假 provider 全回环）",
               {"violations": tree_bad}, ok=not tree_bad)
    assert_row("B3_dns_no_forbidden_no_linked_unknown",
               "DNS 差分禁列零命中且无挂钩未知域名",
               {"forbidden": forbidden_hits, "product_linked_unknown": linked_unknown},
               ok=not forbidden_hits and not linked_unknown)
    assert_row("B4_file_hits_within_whitelist",
               "产品根字节扫描：白名单外零命中",
               {"violations": root_scan["violations"], "scanned": root_scan["scanned_files"]},
               ok=not root_scan["violations"])
    assert_row("B5_db_tables_session_semantic_only",
               "会话库命中表 ⊆ 会话语义表；kv/credential/account 零命中",
               {"token_tables": db_attr["token_tables"], "forbidden": db_attr["forbidden_tables"]},
               ok=not db_attr["forbidden_tables"])
    assert_row("B6_crashpad_clean",
               "Crashpad 零 token 且无 submitURL/外发 URL 字节",
               channels["C_crash"]["observed"],
               ok=not channels["C_crash"]["observed"]["crashpad_token_hits"]
               and not channels["C_crash"]["observed"]["crash_log_hits"]
               and not crash_urls)
    assert_row("B7_round_completed",
               "模型轮完成（assistant 回显 token）",
               {"submitted": round_fail is None, "token_echoed": result["round"]["token_echoed_in_answer"]},
               ok=bool(answer and result["round"]["token_echoed_in_answer"]))
    assert_row("B8_no_secret_in_artifact", "服务密码字节不在产物 JSON 中", {"checked": True}, ok=True)

    if round_fail is not None or not answer:
        verdict = "BLOCKED"
    elif any(a["result"] == "FAIL" for a in result["assertions"]):
        verdict = "FAIL"
    elif any(c["class"] in ("environment", "unattributed_pid0") for c in classified_dns) or any(
            r["class"] in ("environment", "unattributed_pid0") for r in new_rows):
        verdict = "PASS_WITH_ENV_NOISE"
    else:
        verdict = "PASS"
    result["verdict"] = verdict
    result["meta"]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if password in payload:
        print("FAIL: 密钥泄漏进产物，拒绝写盘", file=sys.stderr)
        return 1
    result["assertions"][-1]["result"] = "PASS"  # B8 上面的占位经字节校验后落定
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if password in payload:
        print("FAIL: 密钥泄漏进产物，拒绝写盘", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    print(json.dumps({"verdict": verdict, "out": str(out_path),
                      "assertions": {a["id"]: a["result"] for a in result["assertions"]},
                      "channels": {k: v["observed"] for k, v in channels.items()}},
                     ensure_ascii=False))

    prov_srv.shutdown()
    mcp_srv.shutdown()
    if launcher is not None:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(launcher.pid)],
                       capture_output=True, timeout=30)
    return 0 if verdict in ("PASS", "PASS_WITH_ENV_NOISE") else (2 if verdict == "BLOCKED" else 1)


if __name__ == "__main__":
    sys.exit(main())
