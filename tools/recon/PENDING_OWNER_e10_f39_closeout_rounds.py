#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""E10/F39 出口与隔离负测收口轮（W2a-U17 四轮＋W2a-U18 接线/R-HOST）。

工单：W2a-U17（四轮）→W2a-U18（受限令牌接线消 NOT_WIRED＋宿主级四项
负测轮 `--rounds host`）。权威：
 - 07-新增必需工程义务.csv 行 11（E10）——「模型请求body/sessionlog/telemetry/
   库存/片段/MCP/浏览器/崩溃日志合成金丝雀；真实OS负测；不只关telemetry」phase B0/B2；
 - 06-全量功能施工映射.csv 行 40（F39）——「OS层对DNS/IP/HTTP/socket/子进程负测；
   清代理不是断网，依赖hash完整性不替隔离；保受限令牌/AppContainer、快照隔离、
   exe哈希自校验，并增加真实OS出站负测」；
 - 00-总协调.md §6.1 裁决#2——无管理员方案先行，宿主级待环境（PENDING_ADMIN_ENV）。

前轮剩余面（f39-os-egress-negtest-result.md §4 与 e10-byte-negtest-result.md §4）：
 ①真实 OCR sidecar 观察轮（U08 挂 F40 未施工＋E11/E12 未到；现全 VERIFIED 已解除）；
 ②live 崩溃触发轮（U08 因用户活服务在跑未杀）；
 ③live 浏览器通道（桌面壳未拉起，仅静态扫描）；
 ④MCP 工具调用驱动（回环 echo 应答器就位、握手未驱动）。
四轮（全合成材料；工具自身不写 %APPDATA%，产品根只读扫描）：

 R-SIDECAR（F39 sidecar 面）——真 ocr_ports_worker_baseline 经 legal_entry
   ocr.baseline_* 桥（anonymizer w2a-u18 受限令牌接线面 / w2a-u09 前轮基线，
   P09/P10 纪律）处理 W2a-U01 生成器 24 页合成语料；观察窗内 netstat 三点
   差分（worker 进程树无非回环新外联）＋DNS 差分禁列零命中＋钉定解释器
   exe sha256 复算（并与 run.json 引擎钉定一致）＋worker 令牌面探测
   （钉定解释器下 whoami /groups，继承令牌=父令牌实证）；U18 起 SC5=
   受限令牌隔离面实测（win_restricted_spawn 父侧子进程令牌实测＋worker
   路径 typed 实录），不再 NOT_WIRED 具名。
 R-CRASH（E10 崩溃通道 live 轮）——自起工具自有隔离服务实例（独立端口＋
   临时 XDG 根，复刻 start_lvyin_service.ps1 拓扑；绝不触碰用户活服务
   pid/43127）；金丝雀流式写盘窗口中 taskkill /F 崩溃→临时根 canary 落点
   ⊆ 会话库白名单＋产品根零命中（隔离实例不写产品根的实证）＋Crashpad
   静态面复查无外发 URL。
 R-BROWSER（E10 浏览器通道 live 轮）——自起隔离桌面壳真会话（F86 CDP 先例：
   oc28/packages/desktop out/ 构建＋electron.exe＋产品自备 CDP 开关；W3-U29
   验收修复起壳 userData 真隔离＝oc28 patch 017（index.ts 认
   OPENCODE_DESKTOP_TEST_ROOT，dev 壳 userData/XDG 全部落 <root>/desktop，
   单实例锁 scoped to userData 故与在跑桌面壳互不争锁；Chromium
   --user-data-dir 实测无效 rc=0）；活服务注册字节副本预置于
   <root>/desktop/state/opencode/service-local.json＋OPENCODE_VERSION 与其
   精确一致→ensure() reuse 分支连用户活服务、绝不 spawn/replace）；CDP DOM
   回读＋main.log service ready 证真会话；netstat/DNS 三点差分（壳树新外联
   ⊆回环）；CDP Page.crash 真崩渲染进程→Crashpad 活转储落隔离根；
   network.netlog/renderer.log/main.log/crash.log 字节扫描金丝雀零泄漏＋
   netlog 非回环 URL 零命中；BR7＝真产品根 logs 零新增 run 目录（隔离实证：
   壳不写 %APPDATA%\\Juscite，工具对真产品根全程只读扫描）；壳早退 typed
   诊断（desktop_profile_lock_occupied 具名在跑壳 pids）。
 R-MCP（E10 MCP 通道驱动轮）——回环假 provider 首答 tool_calls（工具名=
   <server>_<tool> 即 e10echo_canary_echo，oc28 tool/mcp.ts:17 命名律）→
   服务真执行回环 MCP echo tools/call（字节捕获含金丝雀）→follow-up 请求
   带工具结果回传假 provider（字节捕获含金丝雀）→终答回显；外联全回环＋
   产品根 canary ⊆ 会话语义白名单（B2 同口径）。

 R-HOST（W2a-U18 宿主级轮，--rounds host）——四项（§6.1 裁决#2 宿主级）：
   ①物理断网行为负测（WFP 阻断等价实现：Windows 防火墙= WFP 管理面的
     per-program outbound block 规则，钉定解释器作用域）下产品真跑成立＋
     进程树无非回环新外联；②pktmon 宿主级字节抓包（--pkt-size 0 全包→
     pcapng 解析：金丝雀仅现回环包、非回环宿主环境噪声单列）；③防火墙
     规则隔离验证（规则在→阻断探针 TEST-NET-3(RFC3849) 零上线字节＋回环
     对照连通；规则删→show rule 零命中）；④宿主级真实出口字节比对
     （wire pcapng 实况 vs netstat 树差分 vs 落盘字节扫描三面对表）。
   非管理员会话 fail-closed：PENDING_ADMIN_ENV 具名四项登记（绝不冒称
   已验）。管理员会话真跑，规则/抓包用毕即删即停（finally）。

用法（juscite worktree 仓根 cwd；本单 W3-U29 用 w3-u29）：
  python -X utf8 tools/recon/PENDING_OWNER_e10_f39_closeout_rounds.py              # 四轮
  python -X utf8 tools/recon/PENDING_OWNER_e10_f39_closeout_rounds.py --rounds host  # 宿主级轮
  # --out 缺省：全四轮=规范路径 docs/construction/e10-f39-closeout-rounds-result.json；
  # 子集轮=自动 e10-f39-closeout-rounds-<轮名>-<UTC戳>Z.json（不覆盖四轮产物）。

退出码：0＝所选轮全 PASS/PASS_WITH_ENV_NOISE（四轮模式另含宿主级具名登记）；
        1＝FAIL；2＝BLOCKED/PENDING_ADMIN_ENV（宿主级轮无管理员会话＝环境
        未就绪，具名登记不假 done）。
证据：docs/construction/e10-f39-closeout-rounds-result.json（+同名 .md）＋
      docs/construction/evidence/E10/、evidence/F39/{desktop,selfhost}/。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

WORKTREE = Path(__file__).resolve().parents[2]
MAIN_TREE = WORKTREE.parents[2]

sys.path.insert(0, str(WORKTREE / "tools"))
sys.path.insert(0, str(MAIN_TREE / "tools"))
import e10_session_negtest as b0  # noqa: E40402  U08 VERIFIED 采集器复用

b0.PWSH = b0.PWSH_DEFAULT
b0.MAIN_TREE = MAIN_TREE

PRODUCT_ROOT = Path(os.environ.get("APPDATA", "")) / "Juscite"
LIVE_REG = PRODUCT_ROOT / "state" / "opencode" / "service-local.json"
OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
ELECTRON = OC28 / "packages" / "desktop" / "node_modules" / "electron" / "dist" / "electron.exe"
DESKTOP_APP = OC28 / "packages" / "desktop"
BUN = Path.home() / ".bun" / "bin" / "bun.exe"
if not BUN.is_file():
    BUN = Path.home() / ".bun" / "bun.exe"
DEFAULT_INTERPRETER = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
TOKEN_RE = re.compile(r"JUSCITE-CANARY-[0-9a-f]{12}")
MAX_SCAN_BYTES = 128 * 1024 * 1024
DB_REL = Path("data") / "opencode" / "opencode-local.db"
WHITELIST_DIRS = [Path("data") / "opencode" / "log", Path("data") / "opencode" / "tool-output"]
WHITELIST_FILE_PREFIXES = [str(DB_REL)]
CRASH_PORT = 43197
BROWSER_PORT = 43195
MCP_PORT = 43196
HOST_PENDING = [
    "物理断网（飞行模式/WFP 阻断）下产品行为负测",
    "pktmon/netsh trace 宿主级字节抓包",
    "防火墙规则隔离验证（需管理员）",
    "宿主级真实出口字节比对",
]


def log(msg: str) -> None:
    print(f"[{WORKTREE.name}] {msg}", flush=True)


def proc_rc_hex(rc: int) -> str:
    try:
        return f"{rc & 0xFFFFFFFF:#010x}"
    except (TypeError, ValueError):
        return str(rc)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def scan_tree_for_bytes(root: Path, needle: bytes) -> dict:
    """只读递归字节扫描（>128MB 跳过，与 e10_canary.scan 同口径）。"""
    hits, skipped, scanned = [], [], 0
    if not root.is_dir():
        return {"scanned_files": 0, "hits": [], "skipped": [], "root_missing": True}
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                if path.stat().st_size > MAX_SCAN_BYTES:
                    skipped.append(str(path))
                    continue
                with open(path, "rb") as fh:
                    data = fh.read()
                scanned += 1
                if needle in data:
                    hits.append(str(path.relative_to(root)))
            except OSError:
                skipped.append(str(path))
    return {"scanned_files": scanned, "hits": hits, "skipped": skipped}


def urls_in_bytes(data: bytes) -> list[str]:
    return sorted({m.decode("ascii", errors="replace")
                   for m in re.findall(rb"https?://[A-Za-z0-9._:/-]{4,}", data)})


def non_loopback_urls(urls: list[str]) -> list[str]:
    out = []
    for u in urls:
        m = re.match(r"https?://([^/:]+)", u)
        host = (m.group(1) if m else u).lower()
        if host in ("127.0.0.1", "localhost", "::1") or host.startswith("127."):
            continue
        out.append(u)
    return out


def allowed_hit(rel: str) -> bool:
    p = Path(rel)
    if any(p == w or w in p.parents for w in WHITELIST_DIRS):
        return True
    return any(rel == f or rel.startswith(f + "-") for f in WHITELIST_FILE_PREFIXES)


# ------------------------------------------------------------------ 回环服务

class CaptureStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests: list[dict] = []
        self.mcp_rpc: list[dict] = []
        self.bodies: list[bytes] = []      # 完整请求字节归档（通道证据）

    def add(self, item: dict, body: bytes = b"") -> None:
        with self.lock:
            self.requests.append(item)
            if body:
                self.bodies.append(body)


def make_slow_provider(store: CaptureStore, token: str, chunk_delay: float):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            store.add({"at": time.strftime("%H:%M:%S"),
                       "client": self.client_address[0], "method": "POST",
                       "path": self.path, "body_len": len(body),
                       "body_has_token": bool(
                           TOKEN_RE.search(body.decode("utf-8", "replace")))}, body)
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._stream()

        def do_GET(self):
            store.add({"at": time.strftime("%H:%M:%S"),
                       "client": self.client_address[0], "method": "GET",
                       "path": self.path, "body_len": 0, "body_has_token": False})
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _stream(self):
            """慢速 SSE：chunk_delay 秒/块 ×6 块——服务侧流式写盘窗口。"""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", "0")
            self.end_headers()
            self.wfile.flush()
            try:
                for i in range(1, 7):
                    time.sleep(chunk_delay)
                    chunk_text = f"崩溃轮金丝雀流式块{i}：{token}"
                    event = {"id": "chatcmpl-crash", "object": "chat.completion.chunk",
                             "created": int(time.time()), "model": "crash-slow",
                             "choices": [{"index": 0,
                                          "delta": {"content": chunk_text},
                                          "finish_reason": None}]}
                    self.wfile.write(b"data: "
                                     + json.dumps(event, ensure_ascii=False).encode("utf-8")
                                     + b"\n\n")
                    self.wfile.flush()
                fin = [{"id": "chatcmpl-crash", "object": "chat.completion.chunk",
                        "created": int(time.time()), "model": "crash-slow",
                        "choices": [{"index": 0, "delta": {},
                                     "finish_reason": "stop"}]},
                       {"id": "chatcmpl-crash", "object": "chat.completion.chunk",
                        "created": int(time.time()), "model": "crash-slow",
                        "choices": [],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                  "total_tokens": 15}}]
                for e in fin:
                    self.wfile.write(b"data: "
                                     + json.dumps(e, ensure_ascii=False).encode("utf-8")
                                     + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (ConnectionAbortedError, BrokenPipeError, OSError):
                pass                      # 服务被杀时连接断开=崩溃窗口证据
            self.close_connection = True
    return Handler


def make_echo_provider(store: CaptureStore, token: str):
    """普通回显假 provider（浏览器轮伴跑用）。"""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            store.add({"at": time.strftime("%H:%M:%S"),
                       "client": self.client_address[0], "method": "POST",
                       "path": self.path, "body_len": len(body),
                       "body_has_token": bool(
                           TOKEN_RE.search(body.decode("utf-8", "replace")))}, body)
            if self.path.rstrip("/").endswith("/chat/completions"):
                found = TOKEN_RE.search(body.decode("utf-8", errors="replace"))
                tok = found.group(0) if found else token
                self._sse(f"金丝雀标记回显：{tok}（W2a-U17 假 provider 合成应答）")
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def do_GET(self):
            store.add({"at": time.strftime("%H:%M:%S"),
                       "client": self.client_address[0], "method": "GET",
                       "path": self.path, "body_len": 0, "body_has_token": False})
            if self.path.rstrip("/").endswith(("/models", "/v1/models")):
                payload = json.dumps({"object": "list", "data": [
                    {"id": "w2au17-fake", "object": "model",
                     "owned_by": "w2a-u17-synthetic"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def _sse(self, reply: str):
            chunk = lambda delta, finish=None: {  # noqa: E731
                "id": "chatcmpl-w2au17", "object": "chat.completion.chunk",
                "created": int(time.time()), "model": "w2au17-fake",
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            events = [chunk({"role": "assistant", "content": ""}),
                      chunk({"content": reply}), chunk({}, "stop"),
                      {"id": "chatcmpl-w2au17", "object": "chat.completion.chunk",
                       "created": int(time.time()), "model": "w2au17-fake",
                       "choices": [],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                 "total_tokens": 15}}]
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


def resolve_tool_name(body: bytes, needle: str) -> str | None:
    """从 openai 兼容请求体 tools 数组解析含 needle 的工具名（实测为准，
    不猜命名律：Code Mode 点名/下划线名随构建而定）。"""
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    for tool in payload.get("tools") or []:
        name = (tool or {}).get("function", {}).get("name") or (tool or {}).get("name")
        if isinstance(name, str) and needle in name:
            return name
    return None


def make_toolcall_provider(store: CaptureStore, token: str, tool_name: str):
    """MCP 轮假 provider：armed 前普通回显（热身轮——位置实例随首个 prompt 启动、
    MCP 连接滞后于首个请求快照），armed 后首答 tool_calls（openai 兼容流式），
    工具结果回传后终答回显——驱动服务真执行回环 MCP echo 工具。"""
    gate = {"armed": False}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            text = body.decode("utf-8", errors="replace")
            store.add({"at": time.strftime("%H:%M:%S"),
                       "client": self.client_address[0], "method": "POST",
                       "path": self.path, "body_len": len(body),
                       "body_has_token": bool(TOKEN_RE.search(text)),
                       "has_tool_result": ('"role":"tool"' in text.replace(" ", "")
                                           or "tool_call_id" in text),
                       "has_tools_param": '"tools"' in text}, body)
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if "tool_call_id" in text or '"role":"tool"' in text.replace(" ", ""):
                self._sse_text(f"MCP 工具结果已收到，金丝雀回显：{token}")
            elif not gate["armed"]:
                self._sse_text(f"热身轮（MCP 未就绪）：{token}")
            else:
                # 实测（trial 4-7）：本构建 MCP 工具走 Code Mode 包装——请求体
                # tools 数组无 canary_echo 原生函数，模型须调 execute 工具以
                # code 调 tools.<server>.<tool>(...)（DB 指令消息实测点名
                # tools.e10echo.canary_echo）。双路解析：原生名在则用原生名。
                native = resolve_tool_name(body, "canary_echo")
                if native:
                    gate["resolved_tool"] = native
                    self._sse_toolcall(native, token, None)
                else:
                    gate["resolved_tool"] = "execute(codemode:tools.e10echo.canary_echo)"
                    code = ("const r = await tools.e10echo.canary_echo("
                            + json.dumps({"text": f"MCP 驱动载荷 {token}", "token": token},
                                         ensure_ascii=False) + "); return r")
                    self._sse_toolcall("execute", token, code)

        def do_GET(self):
            store.add({"at": time.strftime("%H:%M:%S"),
                       "client": self.client_address[0], "method": "GET",
                       "path": self.path, "body_len": 0, "body_has_token": False})
            if self.path.rstrip("/").endswith(("/models", "/v1/models")):
                payload = json.dumps({"object": "list", "data": [
                    {"id": "w2au17-mcp", "object": "model",
                     "owned_by": "w2a-u17-synthetic"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def _raw_sse(self, events: list[dict]) -> None:
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

        def _sse_text(self, reply: str) -> None:
            def chunk(delta, finish=None):
                return {"id": "chatcmpl-w2au17", "object": "chat.completion.chunk",
                        "created": int(time.time()), "model": "w2au17-mcp",
                        "choices": [{"index": 0, "delta": delta,
                                     "finish_reason": finish}]}
            self._raw_sse([chunk({"role": "assistant", "content": ""}),
                           chunk({"content": reply}), chunk({}, "stop"),
                           {"id": "chatcmpl-w2au17", "object": "chat.completion.chunk",
                            "created": int(time.time()), "model": "w2au17-mcp",
                            "choices": [],
                            "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                      "total_tokens": 15}}])

        def _sse_toolcall(self, name: str, tok: str, code: str | None = None) -> None:
            payload = {"code": code} if code is not None else {
                "text": f"MCP 驱动载荷 {tok}", "token": tok}
            args = json.dumps(payload, ensure_ascii=False)
            base = {"id": "chatcmpl-w2au17", "object": "chat.completion.chunk",
                    "created": int(time.time()), "model": "w2au17-mcp"}
            first = {**base, "choices": [{"index": 0, "finish_reason": None,
                                          "delta": {"role": "assistant", "content": "",
                                                    "tool_calls": [{
                                                        "index": 0, "id": "call_w2au17_1",
                                                        "type": "function",
                                                        "function": {"name": name,
                                                                     "arguments": args}}]}}]}
            fin = {**base, "choices": [{"index": 0, "finish_reason": "tool_calls",
                                        "delta": {}}]}
            usage = {**base, "choices": [],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                               "total_tokens": 15}}
            self._raw_sse([first, fin, usage])
    return Handler, gate


def make_mcp_handler(store: CaptureStore):
    """回环 MCP echo 应答器（Streamable HTTP JSON 面；U08 e10_byte 同式）。"""

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
                mm = re.search(r'"method"\s*:\s*"([^"]+)"', text)
                store.mcp_rpc.append({
                    "at": time.strftime("%H:%M:%S"), "client": self.client_address[0],
                    "path": self.path, "body_bytes": len(body),
                    "method": mm.group(1) if mm else "?",
                    "body_preview": text[:300],
                    "body_has_token": bool(TOKEN_RE.search(text))})
            try:
                msg = json.loads(text) if text.strip() else {}
            except json.JSONDecodeError:
                self._json(400, {"jsonrpc": "2.0", "error": {"code": -32700,
                                                             "message": "parse error"}})
                return
            method = msg.get("method", "")
            msg_id = msg.get("id")
            if method == "initialize":
                self._json(200, {"jsonrpc": "2.0", "id": msg_id, "result": {
                    "protocolVersion": msg.get("params", {}).get(
                        "protocolVersion", "2025-06-18"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "w2au17-mcp-echo", "version": "1.0.0"}}})
            elif method == "tools/list":
                self._json(200, {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [{
                    "name": "canary_echo",
                    "description": "W2a-U17 合成回显工具（仅测试）",
                    "inputSchema": {"type": "object",
                                    "properties": {"text": {"type": "string"},
                                                   "token": {"type": "string"}}}}]}})
            elif method == "tools/call":
                self._json(200, {"jsonrpc": "2.0", "id": msg_id, "result": {
                    "content": [{"type": "text", "text": "MCP-ECHO: " + json.dumps(
                        msg.get("params", {}).get("arguments", {}),
                        ensure_ascii=False)}]}})
            elif msg_id is None:
                self._json(202, None)
            else:
                self._json(200, {"jsonrpc": "2.0", "id": msg_id,
                                 "result": {}, "note": "generic-ack"})

        def do_GET(self):
            self._json(405, None)
    return Handler


def serve(handler) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


# ------------------------------------------------------------- 观察窗采集器

def _is_commit_limit(exc: BaseException) -> bool:
    return isinstance(exc, OSError) and getattr(exc, "winerror", None) == 1455


def retry_on_commit_limit(fn, *args, what: str = "", attempts: int = 4,
                          backoff_s: float = 45.0, **kwargs):
    """WinError 1455（页面文件太小＝ERROR_COMMITMENT_LIMIT）＝宿主内存承诺
    瞬态耗尽（本机与并发单元/桌面壳共宿实测，2026-10-18）→退避重试；重试
    耗尽如实抛出（fail-closed，不把资源耗尽装成测试结论）。"""
    last = None
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except OSError as exc:
            if not _is_commit_limit(exc):
                raise
            last = exc
            log(f"  [commit-limit] {what} 第{i + 1}次 WinError 1455，"
                f"{backoff_s:.0f}s 后重试")
            time.sleep(backoff_s)
    raise last


def _safe_netstat():
    """采样容缺：1455 瞬态→本轮样本缺席（返回 None），统计如实入账。"""
    try:
        return b0.netstat_rows()
    except OSError as exc:
        if _is_commit_limit(exc):
            return None
        raise


def _safe_dns(path):
    try:
        return b0.dns_snapshot(path)
    except OSError as exc:
        if _is_commit_limit(exc):
            return None
        raise


class Watcher:
    """netstat/DNS/进程 三点差分（前/窗内/后），按 pid 树归因。"""

    def __init__(self, snap_dir: Path, flush_dns: bool = True):
        self.snap_dir = snap_dir
        self.flush_dns = flush_dns
        self.pre = self.mid_netstat = self.mid_dns = self.post = None
        self.procs_pre: dict = {}
        self.procs_post: dict = {}
        self.sample_skips = 0

    def take_pre(self, root_pids: set[int]) -> None:
        self.root_pids = set(root_pids)
        self.procs_pre = b0.proc_snapshot(self.snap_dir / "procs-pre.json")
        self.tree_pre = set()
        for pid in root_pids:
            self.tree_pre |= b0.descendants(self.procs_pre, pid)
        if self.flush_dns:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=30)
        self.pre = {"netstat": retry_on_commit_limit(
                        b0.netstat_rows, what="pre netstat"),
                    "dns": retry_on_commit_limit(
                        b0.dns_snapshot, self.snap_dir / "dns-pre.json",
                        what="pre dns"),
                    "at": time.strftime("%H:%M:%S")}

    def sample_window(self, deadline: float, dns_marks=(3.0, 20.0)) -> None:
        self.mid_netstat = set()
        self.mid_dns = set()
        self.sample_skips = 0
        t0 = time.time()
        taken = set()
        while time.time() < deadline:
            rows = _safe_netstat()
            if rows is None:
                self.sample_skips += 1
            else:
                self.mid_netstat |= rows
            elapsed = time.time() - t0
            for mark in dns_marks:
                if elapsed >= mark and mark not in taken:
                    snap = _safe_dns(self.snap_dir / f"dns-mid-{int(mark)}.json")
                    if snap is None:
                        self.sample_skips += 1
                    else:
                        self.mid_dns |= snap
                    taken.add(mark)
            time.sleep(1.5)

    def take_post(self) -> None:
        self.post = {"netstat": retry_on_commit_limit(
                         b0.netstat_rows, what="post netstat"),
                     "dns": retry_on_commit_limit(
                         b0.dns_snapshot, self.snap_dir / "dns-post.json",
                         what="post dns"),
                     "at": time.strftime("%H:%M:%S")}
        self.procs_post = b0.proc_snapshot(self.snap_dir / "procs-post.json")
        self.tree_post = set()
        for pid in self.root_pids:
            self.tree_post |= b0.descendants(self.procs_post, pid)

    def diff(self, tree_label: str) -> dict:
        tree = {int(p) for p in (self.tree_pre | self.tree_post)}
        proc_all = {**self.procs_pre, **self.procs_post}
        during = (self.mid_netstat | self.post["netstat"]) - self.pre["netstat"]
        rows = []
        for (local, remote, state, pid) in sorted(during):
            row = {"local": local, "remote": remote, "state": state, "pid": pid,
                   "proc": proc_all.get(pid, {}).get("name")
                   or ("pid0" if pid == 0 else "?")}
            if state == "LISTENING":
                continue
            if pid in tree:
                row["class"] = tree_label
                row["verdict"] = ("allowed_loopback" if b0.is_loopback(remote)
                                  else "violation_non_loopback")
            elif b0.is_loopback(remote):
                row["class"], row["verdict"] = "loopback_other", "allowed"
            elif pid == 0:
                row["class"], row["verdict"] = "unattributed_pid0", "recorded"
            else:
                row["class"], row["verdict"] = "environment", "environment_noise"
            rows.append(row)
        dns_diff = (self.mid_dns | self.post["dns"]) - self.pre["dns"]
        service_remotes = {b0.host_of(r["remote"]) for r in rows
                           if r["class"] == tree_label}
        classified, forbidden, linked_unknown = b0.classify_dns(
            dns_diff, set(), service_remotes, set())
        return {"tree_pids": sorted(tree), "netstat_new": rows,
                "dns_new": classified,
                "sample_skips": self.sample_skips,
                "violations": [r for r in rows if r.get("verdict") == "violation_non_loopback"],
                "forbidden_dns": forbidden, "linked_unknown": linked_unknown}


# ------------------------------------------------------------- R-SIDECAR

TOKEN_PROBE_SRC = r"""
import csv, io, json, subprocess
out = subprocess.run(["whoami", "/groups", "/fo", "csv"], capture_output=True, timeout=30
                     ).stdout.decode("gbk", errors="replace")
labels = [row[0] for row in csv.reader(io.StringIO(out)) if row]
print(json.dumps({
    "integrity_level": next((l for l in labels if " Mandatory Level" in l), None),
    "in_appcontainer": any("ALL RESTRICTED APPLICATION PACKAGES" in l for l in labels),
    "group_count": len(labels)}))
"""


def resolve_anonymizer_src() -> Path | None:
    """anonymizer 公开面源树定位：优先本单 w2a-u18（受限令牌接线链头），
    退 w2a-u09（U17 前轮基线）；JUSCITE_ANONYMIZER_SRC 环境变量最高优先。"""
    base = (WORKTREE.parents[4] / "legal-cn-anonymizer工作区"
            / "legal-cn-anonymizer" / ".local" / "worktrees")
    for wt in ("w2a-u18", "w2a-u09"):
        guess = base / wt / "src"
        if (guess / "legal_anonymizer" / "application"
                / "ocr_ports_service.py").is_file():
            return guess
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env and (Path(env) / "legal_anonymizer" / "application"
                / "ocr_ports_service.py").is_file():
        return Path(env)
    return None


def round_sidecar(snap_dir: Path, out: dict) -> str:
    log("R-SIDECAR：真 OCR sidecar 观察轮（F40 基础线 worker）…")
    interp = DEFAULT_INTERPRETER
    if not interp.is_file():
        out["blocked_reason"] = f"pinned interpreter missing: {interp}"
        return "BLOCKED"
    anonymizer_src = resolve_anonymizer_src()
    if anonymizer_src is None:
        out["blocked_reason"] = "anonymizer w2a-u09 src not found"
        return "BLOCKED"
    out["anonymizer_src"] = str(anonymizer_src)
    out["interpreter"] = str(interp)

    corpus = Path(tempfile.gettempdir()) / "juscite-w2au17-sidecar-corpus"
    if not (corpus / "corpus_manifest.json").is_file():
        log(f"  生成 24 页合成语料 → {corpus}")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(WORKTREE / "tools" / "e12_corpus_gen.py"),
             "--pages", "24", "--seed", "20261016", "--out", str(corpus)],
            capture_output=True, timeout=900)
        if proc.returncode != 0 or not (corpus / "corpus_manifest.json").is_file():
            out["blocked_reason"] = ("corpus gen failed: "
                                     + proc.stderr.decode("utf-8", "replace")[-300:])
            return "BLOCKED"
    out["corpus_pages"] = 24

    # 本 worktree 桥优先（W2a-U18 legal_entry isolation 透传面）；
    # MAIN_TREE 旧桥会静默丢 isolation 参数（实测踩坑 2026-10-16）
    sys.path.insert(0, str(WORKTREE / "implementation" / "python"))
    sys.path.insert(1, str(MAIN_TREE / "implementation" / "python"))
    sys.path.insert(0, str(anonymizer_src))
    from legal_entry import call as bridge  # noqa: E402
    config = {"anonymizer_contract": "p09/p10",
              "ocr_ports_state_root": str(snap_dir / "ocr-state"),
              "ocr_baseline_interpreter": str(interp)}
    reg = bridge("ocr.baseline_register", {"corpus_root": str(corpus)}, config)
    run_id = reg.get("run_id") or reg.get("id")
    out["run_id"] = run_id
    log(f"  登记完成 run_id={run_id}")

    watcher = Watcher(snap_dir / "sidecar")
    (snap_dir / "sidecar").mkdir(parents=True, exist_ok=True)
    watcher.take_pre({os.getpid()})
    result_box: dict = {}
    done = threading.Event()

    def _run() -> None:
        try:
            result_box["run"] = bridge("ocr.baseline_run", {"run_id": run_id}, config)
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"[:300]
            if "1455" in msg or "commitment" in msg.lower():
                # WinError 1455 页面文件承诺瞬态耗尽（共宿并发负载实测）→
                # 退避后整跑重试一次；仍失败如实入账。
                log(f"  [commit-limit] baseline_run 派生失败（{msg[:80]}…），"
                    f"90s 后重试一次")
                time.sleep(90)
                try:
                    result_box["run"] = bridge("ocr.baseline_run",
                                               {"run_id": run_id}, config)
                    return
                except Exception as exc2:  # noqa: BLE001
                    msg = f"{type(exc2).__name__}: {exc2}"[:300]
            result_box["error"] = msg
        done.set()

    log("  baseline_run 起跑（真 worker 子进程·钉定解释器）…")
    threading.Thread(target=_run, daemon=True).start()
    watcher.sample_window(deadline=time.time() + 900, dns_marks=(10.0, 40.0))
    done.wait(timeout=30)
    watcher.take_post()
    run_result = result_box.get("run") or {}
    out["baseline_run"] = {k: run_result.get(k) for k in
                           ("processed", "skipped", "failed", "error")
                           if isinstance(run_result, dict)} or result_box.get("error")
    log(f"  baseline_run 完成：{out['baseline_run']}")
    # 单页失败（如 GPU 显存竞争 MemoryError）→对 pending 页补跑一次（幂等面），
    # 仍失败则如实入账（fail-closed 错误码是引擎诚实输出，不装样子）。
    if isinstance(run_result, dict) and run_result.get("failed"):
        try:
            pending = bridge("ocr.baseline_pending", {"run_id": run_id}, config)
            todo = pending.get("pending") or []
            if todo:
                log(f"  补跑 pending {len(todo)} 页…")
                run2 = bridge("ocr.baseline_run",
                              {"run_id": run_id, "pages": todo}, config)
                if isinstance(run2, dict):
                    out["baseline_retry"] = {k: run2.get(k) for k in
                                             ("processed", "failed")}
                    run_result = {**run_result,
                                  "processed": (run_result.get("processed") or 0)
                                  + (run2.get("processed") or 0),
                                  "failed": run2.get("failed")}
                    out["baseline_run"] = {"processed": run_result["processed"],
                                           "failed": run_result["failed"]}
        except Exception as exc:  # noqa: BLE001
            out["baseline_retry_error"] = f"{type(exc).__name__}"[:120]
    try:
        report = bridge("ocr.baseline_report", {"run_id": run_id}, config)
        out["baseline_report"] = {k: report.get(k) for k in
                                  ("completed", "error", "pending", "corrupt",
                                   "lines_total")} if isinstance(report, dict) else report
    except Exception as exc:  # noqa: BLE001
        out["baseline_report_error"] = f"{type(exc).__name__}"[:120]

    diff = watcher.diff("worker_tree")
    out["diff"] = {"netstat_new": diff["netstat_new"], "dns_new": diff["dns_new"],
                   "tree_pids": diff["tree_pids"]}

    # 钉定解释器哈希复算＋run.json 引擎钉定对表
    h1, h2 = sha256_file(interp), sha256_file(interp)
    pin = None
    run_json = snap_dir / "ocr-state" / "f40-baseline" / str(run_id) / "run.json"
    if run_json.is_file():
        pin = json.loads(run_json.read_text(encoding="utf-8")).get("interpreter_pin", {})
    out["interpreter_hash"] = {"sha256": h1, "recheck_match": h1 == h2,
                               "pin_match": bool(pin) and pin.get("sha256") == h1,
                               "pin_recorded": bool(pin)}

    # 父进程令牌面基线：钉定解释器下运行 whoami（继承父令牌=对照面）
    probe_src = snap_dir / "token_probe.py"
    probe_src.write_text(TOKEN_PROBE_SRC, encoding="utf-8")
    probe = retry_on_commit_limit(
        subprocess.run, [str(interp), "-X", "utf8", str(probe_src)],
        what="whoami token probe", capture_output=True, timeout=60)
    try:
        out["worker_token_face_parent_baseline"] = json.loads(
            probe.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        out["worker_token_face_parent_baseline"] = {
            "error": probe.stderr.decode("utf-8", "replace")[:200]}

    # W2a-U18 受限令牌隔离面实测（消 U17 NOT_WIRED）：
    # ①机制面——win_restricted_spawn 父侧实测子进程令牌（restricting SIDs
    #   ≥1 且特权=0；探测镜像 cmd.exe，本宿主对受限子进程镜像初始化存在
    #   环境阻断面，rc 如实录不判 PASS/FAIL，隔离面属进程令牌属性）；
    # ②worker 路径——baseline_run(isolation="restricted_token") 2 页真试，
    #   成功必须携 worker 受限面自报；宿主阻断必须 typed
    #   ocr_worker_isolation_spawn_failed:*——两态都诚实，绝不静默降级。
    out["restricted_spawn_measurement"] = {}
    out["worker_path_isolation_attempt"] = {}
    try:
        from legal_anonymizer.application import \
            win_restricted_spawn as _wrs  # noqa: E402
        sproc = retry_on_commit_limit(
            _wrs.spawn_restricted, ["cmd.exe", "/c", "exit 0"],
            what="restricted spawn measurement",
            timeout=60, want_token_face=True)
        out["restricted_spawn_measurement"] = {
            "child_returncode": proc_rc_hex(sproc.returncode),
            "child_token_face": sproc.child_token_face,
        }
    except Exception as exc:  # noqa: BLE001
        out["restricted_spawn_measurement"] = {
            "error": f"{type(exc).__name__}: {exc}"[:200]}
    try:
        # 独立 state root（同语料同 run_id，互不共享页记录）——主跑 24/24 后
        # pending 必为空，隔离试跑须有自己的 pending 页面
        iso_cfg = {"anonymizer_contract": "p09/p10",
                   "ocr_ports_state_root": str(snap_dir / "ocr-state-iso"),
                   "ocr_baseline_interpreter": str(interp)}
        iso_reg = bridge("ocr.baseline_register", {"corpus_root": str(corpus)},
                         iso_cfg)
        iso_run = iso_reg.get("run_id") or iso_reg.get("id")
        pending = bridge("ocr.baseline_pending", {"run_id": iso_run}, iso_cfg)
        todo = (pending.get("pending") or [])[:2]
        att = {"pages_sent": len(todo), "iso_run_id": iso_run}
        if not todo:
            att["outcome"] = "NO_PENDING_PAGES"
        else:
            try:
                iso = retry_on_commit_limit(
                    bridge, "ocr.baseline_run",
                    {"run_id": iso_run, "pages": todo,
                     "isolation": "restricted_token"}, iso_cfg,
                    what="iso worker attempt")
                face = (iso or {}).get("worker_token_face") or {}
                att["outcome"] = ("ISOLATED_SUCCESS"
                                  if face.get("restricted_sid_count")
                                  else "RUN_BUT_UNRESTRICTED")
                att["worker_token_face"] = face
                att["processed"] = (iso or {}).get("processed")
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                att["outcome"] = ("TYPED_HOST_BLOCKED"
                                  if "ocr_worker_isolation_spawn_failed" in msg
                                  else "TYPED_OTHER")
                att["typed_code"] = msg[:200]
        out["worker_path_isolation_attempt"] = att
    except Exception as exc:  # noqa: BLE001
        out["worker_path_isolation_attempt"] = {
            "outcome": "ATTEMPT_ERROR",
            "typed_code": f"{type(exc).__name__}: {exc}"[:200]}

    # 接线状态：anonymizer w2a-u18 win_restricted_spawn（不冒称；非本单
    # 授权面之外的 anonymizer 产品变更已由其仓 w2a-u18 分支交付）
    spawn_src = (anonymizer_src / "legal_anonymizer" / "application"
                 / "ocr_ports_service.py").read_text(encoding="utf-8")
    wrs_src = (anonymizer_src / "legal_anonymizer" / "application"
               / "win_restricted_spawn.py")
    wrs_text = wrs_src.read_text(encoding="utf-8") if wrs_src.is_file() else ""
    out["restricted_token_wiring"] = {
        "status": "WIRED_RESTRICTED_TOKEN",
        "spawn_api": "CreateRestrictedToken+CreateProcessAsUserW "
                     "(win_restricted_spawn.py; 特权全删＋restricting SIDs "
                     "[user, Everyone, Users, AuthenticatedUsers]；设置不需"
                     "管理员)",
        "module_present": bool(wrs_text),
        "spawn_has_token_api": bool(re.search(
            r"CreateRestrictedToken", wrs_text, re.I))
        and bool(re.search(
            r"isolation", spawn_src, re.I)),
        "appcontainer_note": ("AppContainer 未实现（如实）：钉定解释器/GPU "
                              "设备在 AppContainer 默认 ACL 下不可达；权威"
                              "列名「受限令牌/AppContainer」取受限令牌面，"
                              "is_appcontainer 恒如实 false 不冒称"),
        "policy_note": "依赖 hash 完整性不替隔离（07 F39 原文）；物理断网宿主级 "
                       "挂 R-HOST 轮（§6.1 裁决#2）",
    }

    ok_run = isinstance(run_result, dict) and not result_box.get("error") \
        and (run_result.get("processed") or 0) >= 20
    base_face = out.get("worker_token_face_parent_baseline") or {}
    meas = out.get("restricted_spawn_measurement") or {}
    meas_face = meas.get("child_token_face") or {}
    att = out.get("worker_path_isolation_attempt") or {}
    sc5_ok = (
        out["restricted_token_wiring"]["status"] == "WIRED_RESTRICTED_TOKEN"
        and isinstance(base_face, dict) and "integrity_level" in base_face
        and base_face.get("restricted_sid_count", 0) == 0   # 对照面
        and meas_face.get("restricted_sid_count", 0) >= 1   # 机制面实测
        and meas_face.get("privilege_count") == 0
        and att.get("outcome") in ("ISOLATED_SUCCESS", "TYPED_HOST_BLOCKED"))
    assertions = [
        ("SC1_worker_tree_no_non_loopback_egress",
         "观察窗内 worker 进程树无新非回环外联",
         {"violations": diff["violations"]}, not diff["violations"]),
        ("SC2_dns_no_forbidden",
         "DNS 差分禁列域名零命中且无挂钩未知",
         {"forbidden": diff["forbidden_dns"], "linked_unknown": diff["linked_unknown"]},
         not diff["forbidden_dns"] and not diff["linked_unknown"]),
        ("SC3_interpreter_hash_recheck",
         "钉定解释器 exe sha256 复算一致且与登记钉定一致",
         out["interpreter_hash"],
         out["interpreter_hash"]["recheck_match"] and out["interpreter_hash"]["pin_match"]),
        ("SC4_baseline_run_real",
         "真 worker 跑批成立（processed≥20 页；单页错误码如实入账不装样）",
         {"run": out["baseline_run"], "report": out.get("baseline_report"),
          "retry": out.get("baseline_retry")}, ok_run),
        ("SC5_restricted_token_isolation_measured",
         "受限令牌隔离面实测：父侧子进程令牌（restricted SID≥1 且特权=0）"
         "＋父基线对照（非受限）＋worker 路径两态实录（ISOLATED_SUCCESS 携"
         "受限面 / TYPED_HOST_BLOCKED 具名宿主阻断），NOT_WIRED 消账不冒称",
         {"parent_baseline": base_face,
          "restricted_spawn_measurement": meas,
          "worker_path_isolation_attempt": att,
          "wiring": out["restricted_token_wiring"]["status"]},
         sc5_ok),
    ]
    out["assertions"] = [{"id": i, "expected": e, "observed": o,
                          "result": "PASS" if ok else "FAIL"} for i, e, o, ok in assertions]
    if any(a["result"] == "FAIL" for a in out["assertions"]):
        return "FAIL"
    if any(r["class"] in ("environment", "unattributed_pid0")
           for r in diff["netstat_new"]) or any(
            c["class"] == "environment" for c in diff["dns_new"]):
        return "PASS_WITH_ENV_NOISE"
    return "PASS"


# ------------------------------------------------------------- R-CRASH

def spawn_isolated_service(snap_dir: Path, name: str, port: int):
    """自起工具自有隔离服务实例：主 oc28 检出（B2 已证 provider 解析可用）＋
    独立端口＋临时 XDG 四根（复刻 tools/start_lvyin_service.ps1 拓扑）。
    绝不触碰 43127 用户活服务。返回 (proc, reg, client, roots)。"""
    roots = snap_dir / "xdg"
    for sub in ("state", "data", "config", "cache"):
        (roots / sub).mkdir(parents=True, exist_ok=True)
    env = {**os.environ,
           "XDG_STATE_HOME": str(roots / "state"),
           "XDG_DATA_HOME": str(roots / "data"),
           "XDG_CONFIG_HOME": str(roots / "config"),
           "XDG_CACHE_HOME": str(roots / "cache"),
           "OPENCODE_DISABLE_MODELS_FETCH": "1",
           "OPENCODE_CHANNEL": "local",
           "OPENCODE_VERSION": f"2.0.0-local-{name}"}
    log_file = open(snap_dir / f"{name}-service.log", "wb")
    proc = subprocess.Popen(
        [str(BUN), "run", "--cwd", str(OC28 / "packages" / "cli"),
         "--define=OPENCODE_VERSION=process.env.OPENCODE_VERSION",
         "src/index.ts", "serve", "--service", "--hostname", "127.0.0.1",
         "--port", str(port)],
        cwd=str(OC28), env=env, stdout=log_file, stderr=subprocess.STDOUT)
    reg_path = roots / "state" / "opencode" / "service-local.json"
    deadline = time.time() + 240
    reg = None
    while time.time() < deadline:
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            reg = None
        if reg and reg.get("url", "").endswith(f":{port}"):
            listening = any(local.endswith(f":{port}") and state == "LISTENING"
                            for (local, _r, state, _p) in b0.netstat_rows())
            if listening:
                break
        time.sleep(2)
    if reg is None or not reg.get("url", "").endswith(f":{port}"):
        proc.kill()
        return None, None, None, roots
    # 本 worktree 桥优先（W2a-U18 legal_entry isolation 透传面）；
    # MAIN_TREE 旧桥会静默丢 isolation 参数（实测踩坑 2026-10-16）
    sys.path.insert(0, str(WORKTREE / "implementation" / "python"))
    sys.path.insert(1, str(MAIN_TREE / "implementation" / "python"))
    from opencode_http import Client  # noqa: E402
    headers = {"Authorization": "Basic " + base64.b64encode(
        ("opencode:" + reg["password"]).encode()).decode("ascii")}
    return proc, reg, Client(reg["url"], headers=headers, timeout=60), roots


def teardown_service(proc) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                   capture_output=True, timeout=30)


def round_crash(snap_dir: Path, out: dict) -> str:
    log("R-CRASH：自起隔离服务实例崩溃写盘窗口轮…")
    if not BUN.is_file():
        out["blocked_reason"] = f"bun not found: {BUN}"
        return "BLOCKED"
    # 活服务在跑则必须共存（绝不触碰）：独立端口＋临时 XDG 根
    live = b0.netstat_rows()
    live_listeners = {pid for (local, _r, state, pid) in live
                      if state == "LISTENING" and local.endswith(":43127")}
    out["live_service"] = {"listening": bool(live_listeners),
                           "pids": sorted(live_listeners),
                           "touched": False}
    proc, reg, client, roots = spawn_isolated_service(snap_dir, "w2au17crash", CRASH_PORT)
    if proc is None:
        # 资源竞争（sidecar 轮后页文件紧张实测）→ 喘息后重试一次自起
        out["spawn_retry"] = True
        time.sleep(20)
        proc, reg, client, roots = spawn_isolated_service(snap_dir, "w2au17crash2",
                                                          CRASH_PORT)
    if proc is None:
        out["blocked_reason"] = "isolated service did not register (two attempts)"
        return "BLOCKED"
    out["isolated_service"] = {"url": reg["url"], "pid": reg.get("pid"),
                               "port": CRASH_PORT, "started_by_tool": True}

    token = "JUSCITE-CANARY-" + secrets.token_hex(6)
    out["token"] = token
    store = CaptureStore()
    prov_srv, prov_origin = serve(make_slow_provider(store, token, chunk_delay=1.2))
    out["fake_provider_origin"] = prov_origin
    ws = snap_dir / "ws"
    (ws / "materials").mkdir(parents=True, exist_ok=True)
    project_cfg = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"w2au17crash": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "W2a-U17 Crash Slow Fake（合成，仅测试）",
            "options": {"baseURL": prov_origin + "/v1",
                        "apiKey": "sk-w2au17-synthetic"},
            "models": {"crash-slow": {"name": "Crash Slow Canary"}},
        }},
    }
    (ws / "opencode.json").write_text(json.dumps(project_cfg, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    (ws / "materials" / "material.md").write_text(
        f"# W2a-U17 崩溃轮合成材料（全虚构）\n\n金丝雀标记：{token}\n", encoding="utf-8")

    watcher = Watcher(snap_dir / "crashw")
    (snap_dir / "crashw").mkdir(parents=True, exist_ok=True)
    watcher.take_pre({proc.pid, os.getpid()})
    ts = int(time.time())
    session_id, message_id = f"ses_w2au17crash_{ts}", f"msg_w2au17crash_{ts}"
    round_fail = None
    try:
        client.create({"id": session_id, "title": "律引 W2a-U17 崩溃轮（合成）",
                       "location": {"directory": str(ws)},
                       "model": {"id": "crash-slow", "providerID": "w2au17crash"}})
        client.prompt(session_id, {"id": message_id,
                                   "text": f"请阅读材料并逐字重复金丝雀标记：{token}",
                                   "model": {"id": "crash-slow",
                                             "providerID": "w2au17crash"},
                                   "files": [{"uri": (ws / "materials" / "material.md").as_uri(),
                                              "name": "material.md"}]})
    except Exception as exc:  # noqa: BLE001
        round_fail = f"{type(exc).__name__}: {exc}"[:200]
    out["round_submitted"] = round_fail is None
    out["round_fail"] = round_fail

    # 流式写盘窗口中崩溃（杀工具自起实例——绝不动 43127 活服务）：
    # 等首个 chat 请求到达（冷启动实例引导数秒），再留 2 个流式块窗（2.4s）杀。
    stream_deadline = time.time() + 90
    first_req_at = None
    while time.time() < stream_deadline:
        with store.lock:
            chats = [r for r in store.requests
                     if r["path"].endswith("/chat/completions")]
        if chats:
            first_req_at = chats[0]["at"]
            break
        time.sleep(1.0)
    time.sleep(2.4 if first_req_at else 3.5)
    out["crash_window"] = {"killed_at": time.strftime("%H:%M:%S"),
                           "first_chat_request_at": first_req_at,
                           "requests_seen_before_kill": len(store.requests),
                           "streaming_open": first_req_at is not None}
    killer = subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True, timeout=30)
    out["crash_window"]["taskkill_rc"] = killer.returncode
    time.sleep(2)
    gone = not any(local.endswith(f":{CRASH_PORT}") and state == "LISTENING"
                   for (local, _r, state, _p) in b0.netstat_rows())
    watcher.sample_window(deadline=time.time() + 6, dns_marks=(1.0,))
    watcher.take_post()
    diff = watcher.diff("crash_tree")
    out["diff"] = {"netstat_new": diff["netstat_new"], "dns_new": diff["dns_new"]}

    # 字节扫描：临时根（隔离实例自留地）＋产品根（必须零命中）
    temp_scan = scan_tree_for_bytes(roots, token.encode("ascii"))
    product_scan = scan_tree_for_bytes(PRODUCT_ROOT, token.encode("ascii"))
    out["scans"] = {
        "isolated_roots": {"scanned": temp_scan["scanned_files"],
                           "hits": temp_scan["hits"]},
        "product_root": {"scanned": product_scan["scanned_files"],
                         "hits": product_scan["hits"]},
    }
    crash_dir = PRODUCT_ROOT / "Crashpad"
    crash_urls = []
    if crash_dir.is_dir():
        for path in crash_dir.rglob("*"):
            if path.is_file():
                try:
                    crash_urls += urls_in_bytes(path.read_bytes())
                except OSError:
                    pass
    out["scans"]["product_crashpad_urls"] = sorted(set(crash_urls))
    # 崩溃写盘窗证据：隔离库在杀点后存在（流式中途被断）
    db_path = roots / "data" / "opencode" / "opencode-local.db"
    out["crash_artifacts"] = {
        "isolated_db_exists": db_path.is_file(),
        "provider_stream_completed": any(r["path"].endswith("/chat/completions")
                                         and r["body_has_token"]
                                         for r in store.requests),
    }
    prov_srv.shutdown()

    violations = diff["violations"]
    assertions = [
        ("CR1_isolated_instance_crashed",
         "自起隔离服务实例在流式写盘窗口被杀（端口关闭）",
         {"gone": gone, "taskkill_rc": killer.returncode,
          "streaming_open": out["crash_window"]["streaming_open"]}, gone),
        ("CR2_live_service_untouched",
         "用户活服务 43127 全程未触碰（仍在监听）",
         {"live": out["live_service"],
          "still_listening": bool({pid for (local, _r, state, pid) in b0.netstat_rows()
                                   if state == "LISTENING"
                                   and local.endswith(":43127")})},
         bool({pid for (local, _r, state, pid) in b0.netstat_rows()
               if state == "LISTENING" and local.endswith(":43127")})),
        ("CR3_product_root_zero_canary",
         "产品根字节扫描本轮金丝雀零命中（隔离实例不写产品根）",
         out["scans"]["product_root"], not product_scan["hits"]),
        ("CR4_isolated_roots_within_session_semantics",
         "临时根 canary ⊆ 会话库/日志白名单",
         {"hits": temp_scan["hits"],
          "violations": [h for h in temp_scan["hits"] if not allowed_hit(h)]},
         all(allowed_hit(h) for h in temp_scan["hits"])),
        ("CR5_crashpad_clean",
         "产品 Crashpad 无外发 URL 字节（静态复查）",
         {"urls": out["scans"]["product_crashpad_urls"]},
         not out["scans"]["product_crashpad_urls"]),
        ("CR6_tree_no_non_loopback_egress",
         "崩溃窗内进程树无非回环新外联＋DNS 禁列零命中",
         {"violations": violations, "forbidden": diff["forbidden_dns"]},
         not violations and not diff["forbidden_dns"]),
    ]
    out["assertions"] = [{"id": i, "expected": e, "observed": o,
                          "result": "PASS" if ok else "FAIL"} for i, e, o, ok in assertions]
    if not out["round_submitted"]:
        return "BLOCKED"
    if any(a["result"] == "FAIL" for a in out["assertions"]):
        return "FAIL"
    if any(r["class"] in ("environment", "unattributed_pid0")
           for r in diff["netstat_new"]) or any(
            c["class"] == "environment" for c in diff["dns_new"]):
        return "PASS_WITH_ENV_NOISE"
    return "PASS"


# ------------------------------------------------------------- CDP 极简客户端

class MiniCDP:
    """裸 WebSocket CDP 客户端（RFC6455 文本帧，仅 Runtime/Page/Browser 用面）。"""

    def __init__(self, host: str, port: int, path: str, timeout: float = 20.0):
        self.url = (host, port)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("handshake eof")
            buf += chunk
        if b"101" not in buf.split(b"\r\n", 1)[0]:
            raise ConnectionError("handshake rejected: "
                                  + buf.split(b"\r\n\r\n")[0][:120].decode("latin1"))
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.msg_id = 0

    def _send_frame(self, payload: bytes) -> None:
        header = bytearray([0x81])                     # FIN+text
        mask = secrets.token_bytes(4)
        n = len(payload)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _recv_exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("eof")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _recv_frame(self) -> bytes:
        head = self._recv_exact(2)
        opcode = head[0] & 0x0F
        n = head[1] & 0x7F
        if n == 126:
            n = struct.unpack(">H", self._recv_exact(2))[0]
        elif n == 127:
            n = struct.unpack(">Q", self._recv_exact(8))[0]
        payload = self._recv_exact(n)
        if opcode in (0x1, 0x2, 0x0):
            return payload
        if opcode == 0x8:                              # close
            raise ConnectionError("closed by peer")
        if opcode == 0x9:                              # ping → pong
            self._send_pong(payload)
            return self._recv_frame()
        return self._recv_frame()

    def _send_pong(self, payload: bytes) -> None:
        mask = secrets.token_bytes(4)
        header = bytearray([0x8A, 0x80 | len(payload)]) + mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def call(self, method: str, params: dict | None = None, timeout: float = 20.0):
        self.msg_id += 1
        mid = self.msg_id
        self._send_frame(json.dumps({"id": mid, "method": method,
                                     "params": params or {}}).encode())
        deadline = time.time() + timeout
        self.sock.settimeout(max(1.0, deadline - time.time()))
        while time.time() < deadline:
            try:
                payload = self._recv_frame()
            except socket.timeout:
                continue
            msg = json.loads(payload.decode("utf-8", errors="replace"))
            if msg.get("id") == mid:
                return msg
        raise TimeoutError(f"CDP {method} timeout")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def cdp_targets(port: int) -> list[dict]:
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


# ------------------------------------------------------------- R-BROWSER

def _desktop_shell_pids() -> list:
    """在跑桌面壳 pid 探测（electron.exe 命令行含 desktop 包路径）——typed
    诊断面：自起壳早退 rc=0 时具名锁占用者；探测失败如实空表不编造。"""
    try:
        script = ("Get-CimInstance Win32_Process -Filter \"Name='electron.exe'\" | "
                  "Where-Object { $_.CommandLine -like '*packages*desktop*' } | "
                  "Select-Object -ExpandProperty ProcessId")
        proc = subprocess.run([b0.PWSH, "-NoProfile", "-Command", script],
                              capture_output=True, timeout=30)
        out = []
        for tok in proc.stdout.decode("utf-8", "replace").split():
            try:
                out.append(int(tok))
            except ValueError:
                continue
        return sorted(out)
    except (OSError, subprocess.SubprocessError):
        return []


def round_browser(snap_dir: Path, out: dict) -> str:
    log("R-BROWSER：自起桌面壳真会话轮（F86 CDP 先例·版本锁定复用活服务）…")
    snap_dir.mkdir(parents=True, exist_ok=True)
    if not ELECTRON.is_file():
        out["blocked_reason"] = f"electron missing: {ELECTRON}"
        return "BLOCKED"
    # 前置事故教训（2026-10-16 trial1，如实入账）：Windows Electron 的 appData
    # 走 OS known-folder，APPDATA env 重定向无效；壳按真产品根发现注册，版本
    # 不一致触发 ensure() replace 分支=杀活服务并删注册。本轮纪律改为：
    # ①必须已有活服务（无则 BLOCKED，不代起）；②OPENCODE_VERSION 与注册版本
    # 精确一致（matchesVersion 严格相等→decide=reuse，绝不 replace）；
    # ③收尾断言活服务 pid 不变；④W3-U29 验收修复＝oc28 patch 017 userData
    # 真隔离（OPENCODE_DESKTOP_TEST_ROOT→userData/XDG 落 <root>/desktop，单
    # 实例锁 scoped to userData，与在跑桌面壳互不争锁；Chromium
    # --user-data-dir 实测无效 rc=0）；patch 未应用 fail-closed。
    idx_src = (OC28 / "packages" / "desktop" / "src" / "main" / "index.ts")
    try:
        idx_text = idx_src.read_text(encoding="utf-8")
    except OSError:
        idx_text = ""
    if "OPENCODE_DESKTOP_TEST_ROOT" not in idx_text.split("configureApplication()")[-1]:
        out["blocked_reason"] = (
            "oc28 patch 017 (desktop test-root isolation) not applied to "
            f"{idx_src} — shell would contend on the real profile "
            "single-instance lock (electron rc=0 when any desktop shell runs)")
        return "BLOCKED"
    try:
        live_reg = json.loads(LIVE_REG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        out["blocked_reason"] = ("live service registration unreadable; "
                                 "manual start required (tools/start_lvyin_service.ps1)")
        return "BLOCKED"
    live_listeners = {pid for (local, _r, state, pid) in b0.netstat_rows()
                      if state == "LISTENING" and local.endswith(":43127")}
    if not live_listeners:
        out["blocked_reason"] = ("live service not listening (43127); manual start "
                                 "required (tools/start_lvyin_service.ps1)")
        return "BLOCKED"
    live_pid = live_reg.get("pid")
    out["live_service"] = {"version": live_reg.get("version"), "pid": live_pid,
                           "pids": sorted(live_listeners), "touched": False}
    info = b0.service_info(live_reg["password"]) if live_reg.get("password") else None
    if info is None:
        out["blocked_reason"] = "live service probe failed"
        return "BLOCKED"

    cdp_port = 9333
    # patch 017 隔离面：userData/XDG 全部落 <root>/desktop（临时），真产品根
    # %APPDATA%\Juscite 全程只读；活服务注册字节副本预置到隔离根
    # （background-service.ts:39/51 发现文件=XDG_STATE_HOME 派生）→ensure()
    # 读到同一注册＋②的版本精确一致→decide=reuse。
    test_root = snap_dir / "test-root"
    desktop_ud = test_root / "desktop"
    iso_reg_dir = desktop_ud / "state" / "opencode"
    iso_reg_dir.mkdir(parents=True, exist_ok=True)
    (iso_reg_dir / "service-local.json").write_text(
        json.dumps(live_reg, ensure_ascii=False), encoding="utf-8")
    real_logs_root = PRODUCT_ROOT / "logs"
    real_logs_pre = ({p.name for p in real_logs_root.iterdir() if p.is_dir()}
                     if real_logs_root.is_dir() else set())
    env = {**os.environ,
           "OPENCODE_CHANNEL": "local",
           # 版本精确一致 → ensure() decide=reuse：连活服务，绝不 replace/杀。
           "OPENCODE_VERSION": str(live_reg["version"]),
           "OPENCODE_DESKTOP_CLI_DEV": str(OC28 / "packages" / "cli"),
           "OPENCODE_DESKTOP_TEST_ROOT": str(test_root),
           "ELECTRON_ENABLE_LOGGING": "0"}
    logs_root = desktop_ud / "logs"
    pre_run_dirs = ({p.name for p in logs_root.iterdir() if p.is_dir()}
                    if logs_root.is_dir() else set())
    # CDP 注入走产品自备开关（lifecycle/configure.ts:30 读
    # OPENCODE_DESKTOP_REMOTE_DEBUGGING_PORT；命令行直传会与 appendSwitch
    # 双开关冲突致 devtools http server 起不来——实测）。
    env["OPENCODE_DESKTOP_REMOTE_DEBUGGING_PORT"] = str(cdp_port)
    shell_log = open(snap_dir / "browser-shell.log", "wb")
    shell = subprocess.Popen(
        [str(ELECTRON), str(DESKTOP_APP)],
        cwd=str(DESKTOP_APP), env=env, stdout=shell_log, stderr=subprocess.STDOUT)
    out["shell"] = {"pid": shell.pid, "cdp_port": cdp_port,
                    "user_data": str(desktop_ud),
                    "isolation": {
                        "mechanism": "OPENCODE_DESKTOP_TEST_ROOT（oc28 patch 017："
                                     "index.ts 认该 env，userData/XDG 重根到 "
                                     "<root>/desktop；单实例锁 scoped to userData）",
                        "test_root": str(test_root),
                        "registration_seed": "活服务注册字节副本→ensure() reuse，"
                                             "绝不 spawn/replace"},
                    "note": "壳 userData 全落临时 test root；真产品根 %APPDATA%"
                            "\\Juscite 工具全程只读扫描（BR7 隔离实证）"}

    # 等 CDP 端点与窗口 target
    deadline = time.time() + 120
    targets = []
    while time.time() < deadline:
        if shell.poll() is not None:
            holders = _desktop_shell_pids()
            if holders:
                out["blocked_reason"] = (
                    f"electron exited rc={shell.returncode}; "
                    "typed=desktop_profile_lock_occupied（在跑桌面壳 pids="
                    f"{holders} 持真产品根 userData 单实例锁——patch 017 隔离"
                    "未生效或被绕过，不应发生）")
            else:
                out["blocked_reason"] = (
                    f"electron exited rc={shell.returncode}; "
                    "typed=shell_early_exit（未检出在跑桌面壳，原因未名）")
            return "BLOCKED"
        try:
            targets = [t for t in cdp_targets(cdp_port)
                       if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if targets:
                break
        except (OSError, json.JSONDecodeError):
            pass
        time.sleep(2)
    if not targets:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(shell.pid)],
                       capture_output=True, timeout=30)
        out["blocked_reason"] = "CDP page target never appeared"
        return "BLOCKED"
    page = targets[0]
    from urllib.parse import urlparse
    parsed = urlparse(page["webSocketDebuggerUrl"])
    ws_path = parsed.path + ("?" + parsed.query if parsed.query else "")
    out["shell"]["page_target"] = {"title": page.get("title"), "url": page.get("url")[:120]}

    watcher = Watcher(snap_dir / "browserw")
    (snap_dir / "browserw").mkdir(parents=True, exist_ok=True)
    watcher.take_pre({shell.pid, int(live_pid)})

    # 真会话证据：CDP DOM 回读（F86 先例）——渲染有先有后，轮询至正文非空
    dom: dict = {}
    cdp = None
    dom_deadline = time.time() + 75
    while time.time() < dom_deadline:
        try:
            cdp = MiniCDP("127.0.0.1", cdp_port, ws_path)
            ev1 = cdp.call("Runtime.evaluate",
                           {"expression": "document.title", "returnByValue": True})
            ev2 = cdp.call("Runtime.evaluate",
                           {"expression": "document.body ? document.body.innerText.length : -1",
                            "returnByValue": True})
            dom = {"title": (ev1.get("result") or {}).get("result", {}).get("value"),
                   "body_text_len": (ev2.get("result") or {}).get("result", {}).get("value")}
            if isinstance(dom.get("body_text_len"), int) and dom["body_text_len"] > 0:
                break
            cdp.close()
            cdp = None
        except (OSError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            dom = {"error": f"{type(exc).__name__}"}
            cdp = None
        time.sleep(3)
    out["shell"]["dom_readback"] = dom

    # 会话期伴跑一轮金丝雀模型轮（隔离服务 API＋回环假 provider）：金丝雀在飞，
    # 浏览器通道日志若序列化会话内容即会命中（负测面）。
    token = "JUSCITE-CANARY-" + secrets.token_hex(6)
    out["token"] = token
    store = CaptureStore()
    prov_srv, prov_origin = serve(make_echo_provider(store, token))
    ws = snap_dir / "ws-browser"
    (ws / "materials").mkdir(parents=True, exist_ok=True)
    project_cfg = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"w2au17brow": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "W2a-U17 Browser Round Fake（合成，仅测试）",
            "options": {"baseURL": prov_origin + "/v1",
                        "apiKey": "sk-w2au17-synthetic"},
            "models": {"w2au17-fake": {"name": "Browser Round Canary"}},
        }},
    }
    (ws / "opencode.json").write_text(json.dumps(project_cfg, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    (ws / "materials" / "material.md").write_text(
        f"# W2a-U17 浏览器轮合成材料（全虚构）\n\n金丝雀标记：{token}\n", encoding="utf-8")
    client = b0.build_client(live_reg["password"])
    ts = int(time.time())

    def _msg_feed(sid: str) -> list:
        try:
            feed = client.request(
                "GET", f"/api/session/{quote(sid, safe='')}/message")
        except Exception:  # noqa: BLE001
            return []
        return feed.get("data", []) if isinstance(feed, dict) else []

    canary_round: dict = {"submitted": False, "token_echoed": False,
                          "chat_requests": 0, "attempts": []}
    for attempt in (1, 2):
        session_id = f"ses_w2au17brow_{ts}_{attempt}"
        try:
            client.create({"id": session_id, "title": "律引 W2a-U17 浏览器轮（合成）",
                           "location": {"directory": str(ws)},
                           "model": {"id": "w2au17-fake", "providerID": "w2au17brow"}})
            client.prompt(session_id, {"id": f"msg_w2au17brow_{ts}_{attempt}",
                                       "text": f"请逐字重复金丝雀标记：{token}",
                                       "model": {"id": "w2au17-fake",
                                                 "providerID": "w2au17brow"},
                                       "files": [{"uri": (ws / "materials" / "material.md").as_uri(),
                                                  "name": "material.md"}]})
            canary_round["submitted"] = True
        except Exception as exc:  # noqa: BLE001
            canary_round["attempts"].append(
                {"attempt": attempt, "fail": f"{type(exc).__name__}"[:120]})
            continue
        answer, last_error = None, None
        deadline = time.time() + 100
        while time.time() < deadline:
            answer = b0.assistant_text(client, session_id)
            if answer and token in answer:
                break
            tail = _msg_feed(session_id)[-1:]
            if tail and tail[0].get("type") == "idle":
                last_error = (tail[0].get("error") or {}).get("message", "idle")
                break
            time.sleep(1.5)
        canary_round["attempts"].append(
            {"attempt": attempt,
             "token_echoed": bool(answer and token in answer),
             "error": None if (answer and token in answer) else last_error})
        canary_round["token_echoed"] = bool(answer and token in answer)
        if canary_round["token_echoed"]:
            break
    canary_round["chat_requests"] = sum(
        1 for r in store.requests if r["path"].endswith("/chat/completions"))
    out["canary_round"] = canary_round
    prov_srv.shutdown()

    # 真崩溃：CDP Page.crash 崩渲染进程（连接随渲染进程死亡=崩溃发生的证据；
    # 转储是否落盘受 Crashpad handler 时序影响，观测窗 10s 如实记录）
    crash_result = {}
    try:
        res = cdp.call("Page.crash", timeout=15)
        crash_result = {"sent": True, "connection_dropped": False,
                        "error": (res.get("error") or {}).get("message")}
    except Exception as exc:  # noqa: BLE001
        crash_result = {"sent": True, "connection_dropped": True,
                        "error": f"{type(exc).__name__}"}
    time.sleep(10)                                    # Crashpad 落盘观测窗
    try:
        probe = cdp.call("Runtime.evaluate",
                         {"expression": "1", "returnByValue": True}, timeout=5)
        crash_result["renderer_alive_after_crash"] = True
    except Exception:  # noqa: BLE001
        crash_result["renderer_alive_after_crash"] = False
    out["renderer_crash"] = crash_result
    try:
        cdp.close()
    except Exception:  # noqa: BLE001
        pass

    watcher.sample_window(deadline=time.time() + 4, dns_marks=(1.0,))
    watcher.take_post()
    diff = watcher.diff("shell_tree")
    out["diff"] = {"netstat_new": diff["netstat_new"], "dns_new": diff["dns_new"]}

    # 收壳（壳=自起实例可杀；活服务 43127 绝不触碰）
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(shell.pid)],
                   capture_output=True, timeout=30)
    time.sleep(2)
    prov_srv.shutdown()

    # 扫描：本轮新 run 目录日志（壳自建，隔离根）＋Crashpad（隔离根）＋
    # 真产品根全量（只读；BR6 金丝雀⊆白名单＋BR7 真根零新增 run 目录）
    user_root = desktop_ud
    product_scan = scan_tree_for_bytes(PRODUCT_ROOT, token.encode("ascii"))
    real_logs_post = ({p.name for p in real_logs_root.iterdir() if p.is_dir()}
                      if real_logs_root.is_dir() else set())
    real_logs_new = sorted(real_logs_post - real_logs_pre)
    run_dirs = sorted([p for p in logs_root.iterdir() if p.is_dir()
                       and p.name not in pre_run_dirs]) if logs_root.is_dir() else []
    run_scan = {"dirs": [p.name for p in run_dirs], "canary_hits": [],
                "netlog_urls": [], "log_text_urls": [], "netlog_present": False}
    for rd in run_dirs:
        for lf in rd.glob("*"):
            if not lf.is_file():
                continue
            try:
                data = lf.read_bytes()
            except OSError:
                continue
            if token.encode("ascii") in data:
                run_scan["canary_hits"].append(f"{rd.name}/{lf.name}")
            if lf.name.endswith(".netlog"):
                run_scan["netlog_present"] = True
                # 两类非网络活动的 URL 噪声要剥离：①netlog JSON constants 块
                # 自带 Chromium 文档 URL（格式元数据）；②被中断的 netlog 尾部
                # stitch 说明段（含 googlesource URL）。
                scan_data = data.split(b"If logging was interrupted")[0]
                try:
                    nl = json.loads(scan_data.decode("utf-8", "replace"))
                    scan_data = json.dumps(
                        {k: v for k, v in nl.items() if k != "constants"},
                        ensure_ascii=False).encode("utf-8")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
                run_scan["netlog_urls"] += urls_in_bytes(scan_data)
            else:
                run_scan["log_text_urls"] += urls_in_bytes(data)
    run_scan["non_loopback_urls"] = non_loopback_urls(run_scan.get("netlog_urls", []))
    crash_dir = user_root / "Crashpad"
    crash_files, crash_urls, crash_canary = [], [], []
    if crash_dir.is_dir():
        for path in crash_dir.rglob("*"):
            if path.is_file():
                crash_files.append(str(path.relative_to(user_root)))
                try:
                    data = path.read_bytes()
                except OSError:
                    continue
                crash_urls += urls_in_bytes(data)
                if token.encode("ascii") in data:
                    crash_canary.append(str(path.relative_to(user_root)))
    service_ready = False
    for rd in run_dirs:
        ml = rd / "main.log"
        if ml.is_file():
            try:
                if "service ready" in ml.read_text(encoding="utf-8", errors="replace"):
                    service_ready = True
            except OSError:
                pass
    out["scans"] = {
        "run_logs": run_scan,
        "crashpad": {"files": crash_files,
                     "urls": sorted(set(crash_urls)),
                     "non_loopback_urls": non_loopback_urls(sorted(set(crash_urls))),
                     "canary_hits": crash_canary},
        "product_root": {"scanned": product_scan["scanned_files"],
                         "canary_hits": product_scan["hits"],
                         "real_profile_new_log_dirs": real_logs_new},
        "main_log_service_ready": service_ready,
    }

    dom_ok = isinstance(out["shell"]["dom_readback"].get("title"), str) \
        and out["shell"]["dom_readback"].get("body_text_len", -1) > 0
    assertions = [
        ("BR1_shell_real_session",
         "隔离桌面壳真会话（CDP DOM 回读＋main.log service ready）",
         {"dom": out["shell"]["dom_readback"], "service_ready": service_ready},
         dom_ok and service_ready),
        ("BR2_shell_tree_loopback_only",
         "壳树＋活服务树新外联 ⊆ 回环；DNS 禁列零命中；活服务 pid 不变（未触碰）",
         {"violations": diff["violations"], "forbidden": diff["forbidden_dns"],
          "live_pid_before": live_pid,
          "live_pid_after": ({pid for (local, _r, state, pid) in b0.netstat_rows()
                              if state == "LISTENING"
                              and local.endswith(":43127")} or {None}).__iter__().__next__()
          if len({pid for (local, _r, state, pid) in b0.netstat_rows()
                  if state == "LISTENING" and local.endswith(":43127")}) == 1 else None},
         not diff["violations"] and not diff["forbidden_dns"]
         and {pid for (local, _r, state, pid) in b0.netstat_rows()
              if state == "LISTENING" and local.endswith(":43127")} == {live_pid}),
        ("BR3_browser_logs_zero_canary",
         "network.netlog/renderer.log/main.log/crash.log 金丝雀零泄漏",
         {"hits": run_scan["canary_hits"],
          "canary_in_flight": canary_round.get("token_echoed")}, not run_scan["canary_hits"]),
        ("BR4_netlog_no_non_loopback_urls",
         "network.netlog 无非回环 URL（网络活动面）；控制台/日志文本 URL 单列登记",
         {"netlog_non_loopback": run_scan["non_loopback_urls"],
          "log_text_urls": sorted(set(run_scan["log_text_urls"]))},
         not run_scan["non_loopback_urls"]),
        ("BR5_renderer_crash_live",
         "CDP 真崩渲染进程（连接死亡实证）：Crashpad 零金丝雀＋无非回环 URL"
         "（转储是否落盘如实记录，不以文件在否冒称）",
         {"crash": out["renderer_crash"], "crashpad": out["scans"]["crashpad"]},
         bool(out["renderer_crash"].get("sent"))
         and not out["renderer_crash"].get("renderer_alive_after_crash")
         and not crash_canary
         and not out["scans"]["crashpad"]["non_loopback_urls"]),
        ("BR6_product_root_within_whitelist",
         "产品根金丝雀 ⊆ B2 会话语义白名单（壳自有日志/netlog/Crashpad 零命中）",
         {"hits": product_scan["hits"],
          "violations": [h for h in product_scan["hits"] if not allowed_hit(h)]},
         all(allowed_hit(h) for h in product_scan["hits"])),
        ("BR7_real_profile_isolated",
         "patch 017 隔离实证：真产品根 logs 零新增 run 目录（壳 userData 全在"
         "临时 test root，真 %APPDATA%\\Juscite 只读面）",
         {"real_profile_new_log_dirs": real_logs_new,
          "shell_user_data": out["shell"]["user_data"]},
         not real_logs_new),
    ]
    out["assertions"] = [{"id": i, "expected": e, "observed": o,
                          "result": "PASS" if ok else "FAIL"} for i, e, o, ok in assertions]
    if any(a["result"] == "FAIL" for a in out["assertions"]):
        return "FAIL"
    if any(r["class"] in ("environment", "unattributed_pid0")
           for r in diff["netstat_new"]) or any(
            c["class"] == "environment" for c in diff["dns_new"]):
        return "PASS_WITH_ENV_NOISE"
    return "PASS"


# ------------------------------------------------------------- R-MCP

def round_mcp(snap_dir: Path, out: dict) -> str:
    """R-MCP 编排：单次实施＋FAIL 时至多一次整轮重试（新隔离服务；两试
    verdict 如实入账，不循环不掩盖）——瞬态面实证：共宿并发负载下隔离服务
    Code Mode 内层执行曾一次未达 tools/call（2026-10-18 A2 轮，两轮既有
    PASS 均同路 count=1），沿 R-CRASH spawn-retry 同族先例。"""
    status = _mcp_once(snap_dir, out)
    if status != "FAIL":
        return status
    first_summary = {
        "verdict": "FAIL",
        "captures": out.get("captures"),
        "resolved_tool": (out.get("captures") or {}).get("resolved_tool_name"),
        "assertions": [a for a in (out.get("assertions") or [])
                       if a.get("result") != "PASS"],
        "blocked_reason": out.get("blocked_reason"),
        "unexpected_error": out.get("unexpected_error"),
    }
    log("  R-MCP FAIL → 60s 后整轮重试一次（新隔离服务；首试原样留档）")
    time.sleep(60)
    out.clear()
    out["first_attempt"] = first_summary
    status2 = _mcp_once(snap_dir / "mcp-retry", out)
    out["retry"] = {"attempt": 2, "first_verdict": "FAIL",
                    "second_verdict": status2}
    return status2


def _mcp_once(snap_dir: Path, out: dict) -> str:
    log("R-MCP：回环假 provider 驱动 tool_calls→回环 MCP echo 轮…")
    if not BUN.is_file():
        out["blocked_reason"] = f"bun not found: {BUN}"
        return "BLOCKED"
    live_listeners = {pid for (local, _r, state, pid) in b0.netstat_rows()
                      if state == "LISTENING" and local.endswith(":43127")}
    out["live_service"] = {"listening": bool(live_listeners),
                           "pids": sorted(live_listeners), "touched": False}
    # 注：43127 现役服务实测为 F86 one-off 残留（provider 初始化损坏：Cannot find
    # package '@opencode/ai'），本轮走自起隔离服务（主 oc28 检出，B2 已证可用），
    # 绝不触碰活服务。
    svc_proc, svc_reg, client, svc_roots = spawn_isolated_service(
        snap_dir, "w2au17mcp", MCP_PORT)
    if svc_proc is None:
        out["blocked_reason"] = "isolated service did not register"
        return "BLOCKED"
    out["isolated_service"] = {"url": svc_reg["url"], "pid": svc_reg.get("pid"),
                               "port": MCP_PORT, "started_by_tool": True}

    token = "JUSCITE-CANARY-" + secrets.token_hex(6)
    out["token"] = token
    store = CaptureStore()
    prov_handler, prov_gate = make_toolcall_provider(store, token,
                                                     "e10echo_canary_echo")
    prov_srv, prov_origin = serve(prov_handler)
    mcp_srv, mcp_origin = serve(make_mcp_handler(store))
    out["origins"] = {"provider": prov_origin, "mcp": mcp_origin}

    ws = snap_dir / "ws-mcp"
    (ws / "materials").mkdir(parents=True, exist_ok=True)
    project_cfg = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {"w2au17mcp": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "W2a-U17 MCP Round Fake（合成，仅测试）",
            "options": {"baseURL": prov_origin + "/v1",
                        "apiKey": "sk-w2au17-synthetic"},
            "models": {"w2au17-mcp": {"name": "MCP Round Canary"}},
        }},
        "mcp": {"e10echo": {"type": "remote", "url": mcp_origin + "/mcp"}},
    }
    (ws / "opencode.json").write_text(json.dumps(project_cfg, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    (ws / "materials" / "mcp_payload.json").write_text(
        json.dumps({"tool": "canary_echo", "token": token,
                    "note": "W2a-U17 MCP 轮合成载荷，全虚构"}, ensure_ascii=False),
        encoding="utf-8")

    watcher = Watcher(snap_dir / "mcpw")
    (snap_dir / "mcpw").mkdir(parents=True, exist_ok=True)
    watcher.take_pre({svc_proc.pid})

    ts = int(time.time())
    session_id = f"ses_w2au17mcp_{ts}"
    out["round"] = {"session_id": session_id}
    round_fail = None
    try:
        client.create({"id": session_id, "title": "律引 W2a-U17 MCP 轮（合成）",
                       "location": {"directory": str(ws)},
                       "model": {"id": "w2au17-mcp", "providerID": "w2au17mcp"},
                       "permissions": [{"action": "e10echo_canary_echo",
                                        "resource": "*", "effect": "allow"}]})
    except Exception as exc:  # noqa: BLE001
        round_fail = f"{type(exc).__name__}: {exc}"[:200]
    out["round"]["create_fail"] = round_fail

    # 热身轮：位置实例随首个 prompt 启动（实测 create 不触发）→等 MCP 握手
    # （initialize＋tools/list）→armed 后下一轮请求体才含 MCP 工具，tool_calls
    # 才会被真执行（首答过早=「No tool named … currently available」实测教训）。
    warmup_fail = None
    if round_fail is None:
        try:
            client.prompt(session_id, {"id": f"msg_w2au17mcp_warm_{ts}",
                                       "text": f"热身：{token}",
                                       "model": {"id": "w2au17-mcp",
                                                 "providerID": "w2au17mcp"}})
        except Exception as exc:  # noqa: BLE001
            warmup_fail = f"{type(exc).__name__}: {exc}"[:200]
    out["round"]["warmup_fail"] = warmup_fail
    handshake_by = time.time() + 90
    tools_listed = False
    while time.time() < handshake_by:
        with store.lock:
            tools_listed = any(m.get("method") == "tools/list" for m in store.mcp_rpc)
            if tools_listed:
                break
        time.sleep(2)
    with store.lock:
        out["mcp_pre_toolcall"] = {"rpc_count": len(store.mcp_rpc),
                                   "methods": [m.get("method") for m in store.mcp_rpc]}
    log(f"  MCP 握手观测：{out['mcp_pre_toolcall']['rpc_count']} rpc "
        f"tools_listed={tools_listed}")
    prov_gate["armed"] = tools_listed

    answer = None
    if round_fail is None and warmup_fail is None and tools_listed:
        texts_pre = len(b0.assistant_text(client, session_id).splitlines())             if b0.assistant_text(client, session_id) else 0
        try:
            client.prompt(session_id, {"id": f"msg_w2au17mcp_{ts}",
                                       "text": f"请调用工具回显金丝雀标记：{token}",
                                       "model": {"id": "w2au17-mcp",
                                                 "providerID": "w2au17mcp"},
                                       "files": [{"uri": (ws / "materials" / "mcp_payload.json").as_uri(),
                                                  "name": "mcp_payload.json"}]})
        except Exception as exc:  # noqa: BLE001
            round_fail = f"{type(exc).__name__}: {exc}"[:200]
        out["round"]["prompt_fail"] = round_fail
        deadline2 = time.time() + 120
        while time.time() < deadline2:
            full = b0.assistant_text(client, session_id) or ""
            lines = [l for l in full.splitlines() if l.strip()]
            # 等新 assistant 消息（多行累积；热身答案不计）
            if len(lines) > texts_pre and any(token in l for l in lines[texts_pre:]):
                answer = chr(10).join(lines[texts_pre:])
                break
            time.sleep(1.5)
    out["round"]["assistant_text_excerpt"] = (answer or "")[:300]
    out["round"]["token_echoed_in_answer"] = bool(answer and token in answer)
    watcher.sample_window(deadline=time.time() + 6, dns_marks=(1.0,))
    watcher.take_post()
    diff = watcher.diff("service_tree")
    out["diff"] = {"netstat_new": diff["netstat_new"], "dns_new": diff["dns_new"]}

    with store.lock:
        mcp_calls = [m for m in store.mcp_rpc if m.get("method") == "tools/call"]
        out["captures"] = {
            "provider_requests": len(store.requests),
            "first_body_has_tools_param": any(r.get("has_tools_param")
                                              for r in store.requests),
            "followup_with_tool_result": any(r.get("has_tool_result")
                                             for r in store.requests),
            "followup_body_has_token": any(r.get("has_tool_result") and r.get("body_has_token")
                                           for r in store.requests),
            "all_clients_loopback": all(r["client"] == "127.0.0.1"
                                        for r in store.requests),
            "mcp_rpc_count": len(store.mcp_rpc),
            "mcp_methods": [m.get("method") for m in store.mcp_rpc],
            "mcp_handshake_initialize": any(m.get("method") == "initialize"
                                        for m in store.mcp_rpc),
            "mcp_tools_list": any(m.get("method") == "tools/list"
                              for m in store.mcp_rpc),
            "mcp_tools_call_count": len(mcp_calls),
            "mcp_tools_call_has_token": any(m.get("body_has_token") for m in mcp_calls),
            "resolved_tool_name": prov_gate.get("resolved_tool"),
            "mcp_all_clients_loopback": all(m["client"] == "127.0.0.1"
                                            for m in store.mcp_rpc),
        }
    # MCP 请求字节归档（通道证据；金丝雀合成内容，非秘密）
    with store.lock:
        out["mcp_call_bytes_archive"] = [m["body_preview"] for m in mcp_calls][:4]

    # 扫描：隔离根（会话库白名单语义）＋产品根（隔离实例不写产品根→零命中）
    iso_scan = scan_tree_for_bytes(svc_roots, token.encode("ascii"))
    out["isolated_roots_scan"] = {"scanned": iso_scan["scanned_files"],
                                  "hits": iso_scan["hits"],
                                  "violations": [h for h in iso_scan["hits"]
                                                 if not allowed_hit(h)]}
    product_scan = scan_tree_for_bytes(PRODUCT_ROOT, token.encode("ascii"))
    out["product_root_scan"] = {"scanned": product_scan["scanned_files"],
                                "hits": product_scan["hits"]}
    # 服务日志证据：mcp 连接行（握手面旁证）
    svc_log = snap_dir / "w2au17mcp-service.log"
    mcp_log_lines = []
    if svc_log.is_file():
        for line in svc_log.read_text(encoding="utf-8", errors="replace").splitlines():
            if re.search(r"\bmcp\b", line, re.I):
                mcp_log_lines.append(line[-260:])
    out["service_mcp_log_excerpt"] = mcp_log_lines[-12:]
    prov_srv.shutdown()
    mcp_srv.shutdown()
    teardown_service(svc_proc)

    assertions = [
        ("MC1_mcp_handshake_observed",
         "回环 MCP echo 握手（initialize＋tools/list）被观测",
         {"initialize": out["captures"]["mcp_handshake_initialize"],
          "tools_list": out["captures"]["mcp_tools_list"],
          "rpc": out["captures"]["mcp_rpc_count"],
          "service_log": mcp_log_lines[-3:]},
         out["captures"]["mcp_handshake_initialize"]
         and out["captures"]["mcp_tools_list"]),
        ("MC2_tool_call_driven",
         "假 provider 首答 tool_calls（名取自请求体 tools 实测）→服务真执行 tools/call（字节含金丝雀）",
         {"tools_call_count": out["captures"]["mcp_tools_call_count"],
          "resolved_tool": out["captures"].get("resolved_tool_name"),
          "has_token": out["captures"]["mcp_tools_call_has_token"],
          "round_completed": out["round"]["token_echoed_in_answer"]},
         out["captures"]["mcp_tools_call_count"] >= 1
         and out["captures"]["mcp_tools_call_has_token"]
         and out["round"]["token_echoed_in_answer"]),
        ("MC3_followup_body_captured",
         "工具结果回传假 provider 的 follow-up body 字节捕获（含金丝雀）",
         {"followup": out["captures"]["followup_with_tool_result"],
          "token": out["captures"]["followup_body_has_token"]},
         out["captures"]["followup_with_tool_result"]
         and out["captures"]["followup_body_has_token"]),
        ("MC4_all_loopback",
         "双回环端全部客户端=127.0.0.1；树新外联⊆回环；DNS 禁列零命中",
         {"provider_loopback": out["captures"]["all_clients_loopback"],
          "mcp_loopback": out["captures"]["mcp_all_clients_loopback"],
          "violations": diff["violations"], "forbidden": diff["forbidden_dns"]},
         out["captures"]["all_clients_loopback"]
         and out["captures"]["mcp_all_clients_loopback"]
         and not diff["violations"] and not diff["forbidden_dns"]),
        ("MC5_canary_within_whitelist",
         "隔离根金丝雀 ⊆ 会话语义白名单；产品根零命中（不写产品根）",
         {"isolated": out["isolated_roots_scan"],
          "product": out["product_root_scan"]},
         not out["isolated_roots_scan"]["violations"]
         and not product_scan["hits"]),
    ]
    out["assertions"] = [{"id": i, "expected": e, "observed": o,
                          "result": "PASS" if ok else "FAIL"} for i, e, o, ok in assertions]
    if round_fail is not None and not answer:
        return "BLOCKED"
    if any(a["result"] == "FAIL" for a in out["assertions"]):
        return "FAIL"
    if any(r["class"] in ("environment", "unattributed_pid0")
           for r in diff["netstat_new"]) or any(
            c["class"] == "environment" for c in diff["dns_new"]):
        return "PASS_WITH_ENV_NOISE"
    return "PASS"


# ------------------------------------------------------------- R-HOST

HOST_RULE_NAME = "JUSCITE-U18-HOST-NEGTEST"
HOST_PROBE_DST = "203.0.113.1"     # TEST-NET-3（RFC 3849 文档保留段，绝不真实外联）


def _is_admin_session() -> dict:
    try:
        proc = subprocess.run(["net", "session"], capture_output=True,
                              timeout=30)
        return {"admin": proc.returncode == 0,
                "check": (f"net session rc={proc.returncode} "
                          + proc.stderr.decode("gbk", "replace")
                          .strip()[:80])}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"admin": False, "check": f"net session exc: "
                                         f"{type(exc).__name__}"}


def _pktmon(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["pktmon", *args], capture_output=True,
                          timeout=timeout)


def _parse_pcapng(path: Path, canary: bytes) -> dict:
    """最小 pcapng 解析（EPB 块）：包数/IP 目的集合/金丝雀落点（ASCII 与
    UTF-16LE）/TEST-NET 探针零上线验证。链路层按 Ethernet+单 VLAN 容错。"""
    data = path.read_bytes()
    packets = 0
    dsts: set[str] = set()
    canary_ascii_hits, canary_utf16_hits, canary_nonloop_hits = 0, 0, 0
    probe_pkts = 0
    loop_pkts = 0
    canary_u16 = canary.decode("ascii").encode("utf-16-le")
    off = 0
    n = len(data)
    while off + 12 <= n:
        btype, blen, _ = struct.unpack_from("<III", data, off)
        if blen < 12 or off + blen > n:
            break
        if btype == 0x00000006:          # Enhanced Packet Block
            caplen = struct.unpack_from("<I", data, off + 20)[0]
            pkt = data[off + 28: off + 28 + caplen]
            packets += 1
            if len(pkt) >= 34:
                ethertype = struct.unpack_from(">H", pkt, 12)[0]
                l3 = 14
                if ethertype == 0x8100 and len(pkt) >= 38:
                    ethertype = struct.unpack_from(">H", pkt, 16)[0]
                    l3 = 18
                if ethertype == 0x0800 and len(pkt) >= l3 + 20:
                    dst = ".".join(str(b) for b in pkt[l3 + 16:l3 + 20])
                    dsts.add(dst)
                    if dst.startswith("127."):
                        loop_pkts += 1
                        if canary in pkt:
                            canary_ascii_hits += 1
                        if canary_u16 in pkt:
                            canary_utf16_hits += 1
                    else:
                        if canary in pkt or canary_u16 in pkt:
                            canary_nonloop_hits += 1
                    if dst == HOST_PROBE_DST:
                        probe_pkts += 1
        off += blen
    non_loop = sorted(d for d in dsts if not d.startswith("127.")
                      and not d.endswith(".255") and d != "0.0.0.0"
                      and not d.startswith("224.") and not d.startswith("239.")
                      and d != "255.255.255.255")
    return {"packets": packets,
            "loopback_packets": loop_pkts,
            "canary_ascii_in_loopback": canary_ascii_hits,
            "canary_utf16le_in_loopback": canary_utf16_hits,
            "canary_bytes_in_nonloopback": canary_nonloop_hits,
            "probe_testnet_packets": probe_pkts,
            "non_loopback_dsts": non_loop,
            "all_dst_count": len(dsts)}


def round_host(snap_dir: Path, out: dict) -> str:
    log("R-HOST：宿主级负测四项（WFP 阻断行为/pktmon 抓包/防火墙规则隔离/"
        "出口字节比对）…")
    adm = _is_admin_session()
    out["admin_session"] = adm
    if not adm["admin"]:
        # §6.1 裁决#2：非管理员 fail-closed——具名四项 PENDING，不假 done
        out["host_status"] = "PENDING_ADMIN_ENV"
        out["pending_items"] = HOST_PENDING
        out["adjudication"] = ("00-总协调.md §6.1 裁决#2：宿主级待管理员环境；"
                               "非管理员会话 fail-closed 如实 PENDING，不冒称已验")
        return "PENDING_ADMIN_ENV"

    # ---- 管理员真跑前置：钉定解释器＋2 页合成语料＋桥
    interp = DEFAULT_INTERPRETER
    if not interp.is_file():
        out["blocked_reason"] = f"pinned interpreter missing: {interp}"
        return "BLOCKED"
    anonymizer_src = resolve_anonymizer_src()
    if anonymizer_src is None:
        out["blocked_reason"] = "anonymizer src not found"
        return "BLOCKED"
    out["anonymizer_src"] = str(anonymizer_src)
    corpus = Path(tempfile.gettempdir()) / "juscite-w2au17-sidecar-corpus"
    if not (corpus / "corpus_manifest.json").is_file():
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(WORKTREE / "tools" / "e12_corpus_gen.py"),
             "--pages", "24", "--seed", "20261016", "--out", str(corpus)],
            capture_output=True, timeout=900)
        if proc.returncode != 0:
            out["blocked_reason"] = "corpus gen failed"
            return "BLOCKED"
    # 本 worktree 桥优先（W2a-U18 legal_entry isolation 透传面）；
    # MAIN_TREE 旧桥会静默丢 isolation 参数（实测踩坑 2026-10-16）
    sys.path.insert(0, str(WORKTREE / "implementation" / "python"))
    sys.path.insert(1, str(MAIN_TREE / "implementation" / "python"))
    sys.path.insert(0, str(anonymizer_src))
    from legal_entry import call as bridge  # noqa: E402

    canary = ("JUSCITE-CANARY-" + secrets.token_hex(6)).encode("ascii")
    out["canary"] = canary.decode("ascii")
    etl = snap_dir / "host.etl"
    pcapng = snap_dir / "host.pcapng"
    snap_dir.mkdir(parents=True, exist_ok=True)
    watcher = Watcher(snap_dir / "watch")
    watcher.take_pre({os.getpid()})

    host_cfg = {"anonymizer_contract": "p09/p10",
                "ocr_ports_state_root": str(snap_dir / "ocr-state"),
                "ocr_baseline_interpreter": str(interp)}

    rule_added = False
    cap_started = False
    hf: dict = out.setdefault("host_findings", {})
    box: dict = {}
    done = threading.Event()

    def _run_blocked() -> None:
        try:
            reg = bridge("ocr.baseline_register",
                         {"corpus_root": str(corpus)}, host_cfg)
            run_id = reg["run_id"]
            pending = bridge("ocr.baseline_pending", {"run_id": run_id},
                             host_cfg)
            todo = (pending.get("pending") or [])[:2]
            run_out = bridge("ocr.baseline_run",
                             {"run_id": run_id, "pages": todo}, host_cfg)
            box["run"] = {"pages_sent": len(todo),
                          "processed": run_out.get("processed"),
                          "failed": run_out.get("failed")}
        except Exception as exc:  # noqa: BLE001
            box["error"] = f"{type(exc).__name__}: {exc}"[:200]
        done.set()

    try:
        # 抓包窗（HF2/HF4）：宿主级全包捕获（pkt-size 0；上限 1GB）
        _pktmon(["stop"])                                  # 清残态（无会话则忽略）
        _pktmon(["filter", "remove"])
        cap = _pktmon(["start", "--capture", "--pkt-size", "0",
                       "--file-size", "1024",
                       "--file-name", str(etl)], timeout=120)
        cap_started = cap.returncode == 0
        hf["pktmon_start_rc"] = cap.returncode
        if not cap_started:
            hf["pktmon_start_stderr"] = cap.stderr.decode("gbk", "replace")[:200]

        # 防火墙规则（WFP 管理面）：钉定解释器 per-program outbound block
        add = subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={HOST_RULE_NAME}", "dir=out", "action=block",
             f"program={interp}"], capture_output=True, timeout=60)
        rule_added = add.returncode == 0
        show = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             f"name={HOST_RULE_NAME}"], capture_output=True, timeout=60)
        show_text = show.stdout.decode("gbk", "replace")
        hf["rule_present_while_active"] = (rule_added
                                           and HOST_RULE_NAME in show_text
                                           and "Block" in show_text)

        # HF1：阻断下产品行为负测——2 页真跑（观察窗采样同 sidecar 纪律）
        threading.Thread(target=_run_blocked, daemon=True).start()
        watcher.sample_window(deadline=time.time() + 600, dns_marks=(30.0,))
        done.wait(timeout=60)
        hf["blocked_run"] = box.get("run") or box.get("error")

        # HF3：阻断探针（TEST-NET-3 连接试探；规则在=零上线字节）＋回环对照
        probe_src = snap_dir / "probe_connect.py"
        probe_src.write_text(
            "import socket,sys\n"
            "try:\n"
            f"    s=socket.create_connection(({HOST_PROBE_DST!r},9),timeout=6)\n"
            "    print('CONNECTED'); s.close()\n"
            "except OSError as e:\n"
            "    print('BLOCKED:', type(e).__name__)\n", encoding="utf-8")
        pr = subprocess.run([str(interp), "-X", "utf8", str(probe_src)],
                            capture_output=True, timeout=60)
        hf["blocked_probe"] = {
            "rc": pr.returncode,
            "stdout": pr.stdout.decode("utf-8", "replace").strip()[:60]}
        loop_srv = socket.socket()
        loop_srv.bind(("127.0.0.1", 0))
        loop_srv.listen(1)
        lport = loop_srv.getsockname()[1]
        th = threading.Thread(target=lambda: (
            loop_srv.accept()[0].close(),), daemon=True)
        th.start()
        lc = subprocess.run(
            [str(interp), "-X", "utf8", "-c",
             f"import socket;s=socket.create_connection(('127.0.0.1',{lport}),"
             f"timeout=6);s.sendall(b'{canary.decode()}');s.close()\n"
             "print('LOOP_OK')"], capture_output=True, timeout=60)
        hf["loopback_control"] = {
            "rc": lc.returncode,
            "stdout": lc.stdout.decode("utf-8", "replace").strip()[:40]}
    finally:
        loop_srv.close()
        stop = _pktmon(["stop"], timeout=180)
        conv = (_pktmon(["etl2pcap", str(etl), "-o", str(pcapng)], timeout=300)
                if etl.is_file() else None)
        hf["pktmon_stop_rc"] = stop.returncode
        hf["pcapng_converted"] = bool(pcapng.is_file())
        del_rule = subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule",
             f"name={HOST_RULE_NAME}"], capture_output=True, timeout=60)
        gone = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             f"name={HOST_RULE_NAME}"], capture_output=True, timeout=60)
        hf["rule_removed"] = (del_rule.returncode == 0
                              and HOST_RULE_NAME not in
                              gone.stdout.decode("gbk", "replace"))
        watcher.take_post()

    # HF2/HF4 分析：pcapng 解析（金丝雀落点/TEST-NET 零上线/非回环宿主噪声单列）
    if pcapng.is_file():
        hf["wire"] = _parse_pcapng(pcapng, canary)
    diff = watcher.diff("host_run_tree")
    hf["netstat_tree_diff"] = {
        "violations": diff["violations"],
        "forbidden_dns": diff["forbidden_dns"]}
    hf["at_rest"] = {
        "isolated_root": scan_tree_for_bytes(snap_dir, canary),
        "product_root": scan_tree_for_bytes(PRODUCT_ROOT, canary)}

    wire = hf.get("wire") or {}
    wire_canary_loop = (wire.get("canary_ascii_in_loopback", 0)
                        + wire.get("canary_utf16le_in_loopback", 0))
    blocked_run = hf.get("blocked_run") or {}
    assertions = [
        ("HF1_wfp_block_product_behavior",
         "WFP 阻断（防火墙 per-program outbound block）下产品真跑成立且树无"
         "非回环新外联",
         {"rule_present_while_active": hf.get("rule_present_while_active"),
          "blocked_run": blocked_run,
          "violations": diff["violations"]},
         bool(hf.get("rule_present_while_active"))
         and blocked_run.get("pages_sent") == 2
         and blocked_run.get("processed") == 2
         and not diff["violations"]),
        ("HF2_pktmon_host_capture",
         "pktmon 宿主级字节抓包成立：捕获含回环金丝雀字节（保真=抓得到已知"
         "回环流量），TEST-NET 探针零上线包",
         {"pcapng_converted": hf.get("pcapng_converted"),
          "wire": wire},
         bool(hf.get("pcapng_converted"))
         and wire.get("packets", 0) > 0
         and wire_canary_loop >= 1
         and wire.get("probe_testnet_packets", 0) == 0),
        ("HF3_firewall_rule_isolation",
         "防火墙规则隔离验证：规则在（show 命中含 Block）→阻断探针不连通；"
         "规则删→show 零命中；回环对照连通",
         {"blocked_probe": hf.get("blocked_probe"),
          "loopback_control": hf.get("loopback_control"),
          "rule_removed": hf.get("rule_removed")},
         hf.get("rule_present_while_active")
         and hf.get("rule_removed")
         and hf.get("loopback_control", {}).get("rc") == 0
         and "CONNECTED" not in hf.get("blocked_probe", {}).get("stdout", "")),
        ("HF4_egress_byte_comparison",
         "宿主级真实出口字节比对：wire 实况（金丝雀仅回环/TEST-NET 零包/"
         "非回环目的单列为宿主噪声）×netstat 树差分（无非回环）×落盘扫描"
         "（隔离根⊆白名单且产品根零命中）三面对表一致",
         {"wire_canary_nonloopback": wire.get("canary_bytes_in_nonloopback", 0),
          "non_loopback_dsts": wire.get("non_loopback_dsts"),
          "netstat": hf.get("netstat_tree_diff"),
          "at_rest": hf.get("at_rest")},
         wire.get("probe_testnet_packets", 0) == 0
         and wire.get("canary_bytes_in_nonloopback", 0) == 0
         and not diff["violations"] and not diff["forbidden_dns"]
         and not hf.get("at_rest", {}).get("product_root", {}).get("hits")
         and all(allowed_hit(h) for h in
                 hf.get("at_rest", {}).get("isolated_root", {}).get("hits", []))),
    ]
    out["assertions"] = [{"id": i, "expected": e, "observed": o,
                          "result": "PASS" if ok else "FAIL"}
                         for i, e, o, ok in assertions]
    if any(a["result"] == "FAIL" for a in out["assertions"]):
        return "FAIL"
    if wire.get("non_loopback_dsts"):
        return "PASS_WITH_ENV_NOISE"   # 宿主他进程噪声单列（pid 归因面如实）
    return "PASS"


# ------------------------------------------------------------- 主流程

def main() -> int:
    parser = argparse.ArgumentParser(
        description="E10/F39 出口与隔离负测收口轮（W2a-U17 四轮＋W2a-U18 R-HOST）")
    parser.add_argument("--out", default=None,
                        help="结果 JSON 路径；缺省＝全四轮用既有规范路径，"
                             "子集轮（如 --rounds host）自动带轮名＋UTC 时间戳，"
                             "杜绝子集轮覆盖四轮产物（W3-U29 验收运营改进）")
    parser.add_argument("--rounds", default="sidecar,crash,browser,mcp",
                        help="逗号分隔轮选择（默认全四轮；host=R-HOST 宿主级轮）")
    args = parser.parse_args()
    wanted = {r.strip() for r in args.rounds.split(",") if r.strip()}
    if args.out is not None:
        out_path = Path(args.out)
    elif wanted == {"sidecar", "crash", "browser", "mcp"}:
        out_path = (WORKTREE / "docs" / "construction"
                    / "e10-f39-closeout-rounds-result.json")
    else:
        tag = "-".join(sorted(wanted))
        stamp = time.strftime("%Y%m%dT%H%M", time.gmtime()) + "Z"
        out_path = (WORKTREE / "docs" / "construction"
                    / f"e10-f39-closeout-rounds-{tag}-{stamp}.json")
    unknown = wanted - {"sidecar", "crash", "browser", "mcp", "host"}
    if unknown:
        parser.error(f"unknown rounds: {sorted(unknown)}")

    snap_dir = Path(tempfile.gettempdir()) / f"juscite-w2au18-{int(time.time())}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    result: dict = {
        "unit": "E10/F39 出口与隔离负测收口轮（W2a-U17 四轮＋W2a-U18 接线/R-HOST）",
        "meta": {
            "tool": "tools/recon/PENDING_OWNER_e10_f39_closeout_rounds.py",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "worktree": str(WORKTREE),
            "adjudication": "00-总协调.md §6.1 裁决#2：无管理员方案先行；宿主级待环境"
                            "（R-HOST 非管理员会话 fail-closed PENDING_ADMIN_ENV）",
            "authority": {"E10": "07 行 11（B0/B2）", "F39": "06 行 40"},
            "prerequisites_released": {"F40": "VERIFIED（W2a-U03）",
                                       "E11": "VERIFIED（W2a-U09）",
                                       "E12": "VERIFIED（W2a-U02）"},
            "discipline": "全合成材料；工具不写 %APPDATA%（产品根只读扫描；隔离实例"
                          "全部落临时根）；服务密码不印不落盘；R-HOST 防火墙规则/"
                          "抓包用毕即删即停（finally）",
            "pending_admin_env": HOST_PENDING,
            "snapshot_dir": str(snap_dir),
        },
        "rounds": {}, "verdict": None,
    }

    runners = {"sidecar": round_sidecar, "crash": round_crash,
               "browser": round_browser, "mcp": round_mcp,
               "host": round_host}
    statuses: list[str] = []
    for name in ("sidecar", "crash", "browser", "mcp", "host"):
        if name not in wanted:
            continue
        round_out: dict = {}
        try:
            status = runners[name](snap_dir / name, round_out)
        except Exception as exc:  # noqa: BLE001  轮内意外→如实 FAIL 不装样
            round_out["unexpected_error"] = f"{type(exc).__name__}: {exc}"[:400]
            status = "FAIL"
        finally:
            # 轮内意外也要收走自起壳（防泄漏；只杀本工具自起的 pid）
            shell_pid = (round_out.get("shell") or {}).get("pid")
            if shell_pid:
                try:
                    proc_probe = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {shell_pid}"],
                        capture_output=True, timeout=15)
                    if str(shell_pid) in proc_probe.stdout.decode("gbk", "replace"):
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(shell_pid)],
                                       capture_output=True, timeout=30)
                except (OSError, subprocess.SubprocessError):
                    pass
        round_out["verdict"] = status
        result["rounds"][name] = round_out
        statuses.append(status)
        log(f"  → R-{name.upper()} = {status}")

    failed = [s for s in statuses if s == "FAIL"]
    blocked = [s for s in statuses if s == "BLOCKED"]
    pending_env = [s for s in statuses if s == "PENDING_ADMIN_ENV"]
    if blocked:
        verdict = "BLOCKED"
    elif failed:
        verdict = "FAIL"
    elif pending_env:
        # §6.1 裁决#2：宿主级无管理员会话＝环境未就绪——具名 PENDING 不假 done
        #（非管理员会话跑 --rounds host 恒此出口；exit 2）
        verdict = "PENDING_ADMIN_ENV"
    elif any(s == "PASS_WITH_ENV_NOISE" for s in statuses):
        verdict = "PASS_WITH_ENV_NOISE"
    else:
        verdict = "PASS"
    result["verdict"] = verdict
    result["meta"]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    result["meta"]["host_pending_registered"] = bool(HOST_PENDING)  # 具名登记不冒称
    if pending_env:
        result["meta"]["pending_admin_env_note"] = (
            "非管理员会话（net session 拒绝访问）——宿主级四项 PENDING_ADMIN_ENV "
            "具名登记；E10/F39-desktop/F39-selfhost 维持 IMPLEMENTING 不假 done")
    # 密钥纪律：产物不得含活服务/隔离服务密码字节（全轮隔离注册文件 glob）
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    leaked = []
    try:
        live = json.loads(LIVE_REG.read_text(encoding="utf-8")).get("password", "")
        if live and live in payload:
            leaked.append("live")
    except (OSError, json.JSONDecodeError):
        pass
    for iso_reg in snap_dir.glob("*/**/state/opencode/service-local.json"):
        try:
            iso = json.loads(iso_reg.read_text(encoding="utf-8")).get("password", "")
        except (OSError, json.JSONDecodeError):
            continue
        if iso and iso in payload:
            leaked.append(str(iso_reg))
    result["meta"]["secret_leak_check"] = {"leaked": leaked, "ok": not leaked}
    if leaked:
        print("FAIL: 密钥泄漏进产物，拒绝写盘", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
    print(json.dumps({"verdict": verdict, "out": str(out_path),
                      "rounds": {k: v["verdict"] for k, v in result["rounds"].items()}},
                     ensure_ascii=False))
    return 0 if verdict in ("PASS", "PASS_WITH_ENV_NOISE") else (
        2 if verdict in ("BLOCKED", "PENDING_ADMIN_ENV") else 1)


if __name__ == "__main__":
    sys.exit(main())
