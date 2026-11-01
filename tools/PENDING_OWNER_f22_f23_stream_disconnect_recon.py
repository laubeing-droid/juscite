# -*- coding: utf-8 -*-
"""F22+F23 BYOK 真实流式与断线停止语义活服务对账（工单 W3-U02）。

权威（台账四行 assertion 为准，docs/construction/acceptance-ledger.csv）：
- F22-desktop/selfhost「BYOK与本地模型真实流式工具调用；模型不可用具名报错
  不伪输出」；
- F23-desktop/selfhost「关窗/网络断线不取消run；cursor重连，流缺口resync；
  stop独立终态，迟到finish不覆停止；外部副作用未知先对账」。
- 06 F22=V7-22「BYOK+本地模型通道（v1 只开此）」owner=product；06 F23=V7-23
  「server-owned run（生成与 HTTP 解耦/seq 断线续播/stop 独立端点）」
  source_rationale「掉线 detach 是中国网络环境刚需」；17 卡 owner 面=原生
  OpenCode UI/host（UI_HOST_OR_NEW_PRODUCT，不创第二 Agent loop）。

机制锚点（oc28 v2.0.28 检出实读；e07_live_recon.py 文件头 W1-U06 已核沿用）：
- server-owned run：core/session/session.ts:174 prompt 持久入队后
  `if (input.resume !== false) yield* execution.wake`——执行在服务端 fiber，
  HTTP 只负责入队；session.ts:192「The server owns completion recording even
  if the submitting client disconnects」；
- 真流式活面：GET /api/event（protocol/groups/event.ts:44）SSE 逐事件推送，
  活测本构建一轮真出 session.text.delta ×17＋session.step.started＋
  session.execution.succeeded（provider 流式 delta 每 100ms 批发，
  core/session/runner/publish-llm-event.ts deltaBatchInterval=100）；
- 断线续播 cursor（F23 落面）：持久消息账 GET /api/session/:id/message
  ?order=asc＋cursor.next 分页（protocol/groups/session.ts SessionsCursor）。
  本单活证：experimental 持久 log 端点（GET /api/experimental/session/:id/log
  ?after=&follow=）在本产品拓扑**结构性空回放**——cli/server-process.ts 启动
  不传 events.persist → core/src/bus.ts:203 `persist = options?.persist ??
  false` → EventTable 不落（bus.ts:649 仅 persist 才写事件体，seq 计数表
  EventSequenceTable 照写）→ 活测完整轮次后纯回放仅得 log.synced marker
  （seq 推进而事件体为零）。故 F23「cursor重连，流缺口resync」落在产品实际
  持久回读面＝消息账（e07_live_recon 已证跨完整重启存活：「消息历史含 idle
  标记，回读为准绳，不依赖 SSE（事件流挥发契约）」，e07 文件头 27-28 行），
  experimental log 如实记边界不冒验；
- /api/event 对照面=挥发契约（protocol/groups/event.ts:51「Volatile by
  contract: a slow consumer overflows and fails the stream, and events during
  disconnection are missed」）——断开窗内事件只由持久消息账补齐，活流重连
  只得窗后增量（本单 F23-B 双侧实测）；
- stop 独立终态：core/session/execution.ts:50-54 terminal 三值
  succeeded/interrupted/failed；:119-147 用户 interrupt 发布
  session.execution.interrupted 并释放执行 claim；core/session/
  message-updater.ts:63-77,144-148 idle 行 append，outcome 三值各为独立终态；
- 迟到 finish 不覆停止：execution.ts:118「One terminal observation per busy
  period」；publish-llm-event.ts:169-171「Provider-event publication remains
  uninterruptible through its writes」——中断前已发布事件照常落账，中断后
  不再有新 step（session.step.started 持久事件经消息账投影可数，stop 后为零；
  schema/session-event.ts:326-340 durable 定义）；
- 断电不丢 run：execution.ts:76-80 write-ahead claim「recovery is a property
  of the database」；execution/restart.ts:46-62 crash/SIGKILL/优雅重启同构
  恢复；server/src/fetch.ts:47、process.ts:241 服务启动即
  resumeSuspendedSessions；
- 外部副作用未知先对账：execution/restart.ts:52-53「Recovery is at-least-once:
  local coordination prevents concurrent drains, not repeated external side
  effects after a crash」——stop/断线后的外部副作用以盘上实态＋消息账对账，
  不信事件流推断；
- inbox 同 id 幂等与 resume:false（F23 机制锚点，W1-U06 e07_live_recon 已活
  证，本单 F23-anchor 轻量复锚）：core/session/inbox.ts:70-73 matches() 只比
  对 session+type；session.ts:174 resume:false=已入队未投递。

拓扑（同合同双形态；authority/14:21「桌面与selfhost分别部署同合同」）：
- desktop＝`serve --service`（产品桌面托管拓扑：state/opencode/
  service-local.json 注册文件；T07 start_lvyin_service.ps1／W1-U06
  e07_live_recon／W2a-U17 R-CRASH 同形）；
- selfhost＝`serve` 前台（自托管独立服务拓扑：无注册文件，URL 走 stdout
  「server listening on <url>」（cli/server-process.ts:195），密码经
  OPENCODE_SERVER_PASSWORD 注入（cli/env.ts:10-11；server/auth.ts:17,28
  用户名固定 opencode））。
  两形态 XDG 四根全在临时目录，绝不写 %APPDATA%\\Juscite（前后快照比对）。

红线：材料全合成；oc28 只读（serve 从源码跑，零补丁零改动）；产品
%APPDATA%\\Juscite 只读（BYOK opencode.json 只读复制进临时根；本单附加的两
个合成 provider 只写临时根副本）；密钥不打印不入 git；测试一律合成材料；
不 push。

「本地模型」通道边界如实：本机 Ollama 未装（总账 §1 环境事实＋本单探针具名
记录）；本地通道以 recon 进程内 127.0.0.1 OpenAI 兼容 SSE 端点（与 llama.cpp
server／Ollama OpenAI 兼容层同形线缆协议）真流式实测——分块传输/流式解析/
tool_calls 增量组装/权限闸/工具执行/盘上回读全真实，仅模型权重为合成脚本
（测试一律合成材料红线）；Ollama 缺席如实记录，不冒装。

T15 M 组干净会话纪律（tools/e02_tool_closure.py C 组）：每个模型轮次用独立
干净会话（不挂任何探针规则集），权限面=产品 legal-review profile 原样
（deny 打底/allow 居中/.env 尾置，T13 修正序）；§2.1 DeepSeek 附件径证据链
沿用=金额只出现在合成材料文件内，prompt 不含答案，模型必须经工具读取。

用法（juscite worktree w3-u02 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f22_f23_stream_disconnect_recon.py \
      [--profile desktop --profile selfhost] [--oc28 <path>] [--keep]

退出码：0=RECON_OK（全部所选 profile 全检过）；1=RECON_FAIL；3=RECON_BLOCKED
（bun/oc28/产品 BYOK 配置缺失、模型轮次机械边界不可用）。
证据：evidence/F22/<profile>/ 与 evidence/F23/<profile>/ 各落一份 recon
JSON+MD（一次跑批双义务目录，同份检查分账落盘）。
"""
from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

from opencode_http import Client  # noqa: E402

DEFAULT_OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
DEFAULT_BUN = Path.home() / ".bun" / "bun.exe"
DEV_VERSION = "2.0.0-local-w3u02"     # F-4：dev 版记实值（打包 pin=2.0.28）
PROVIDER_ID = "deepseek-byok"         # 总账 §3.1 ③ 用户裁决：DeepSeek BYOK
MODEL_ID = "deepseek-chat"
LOCAL_PROVIDER_ID = "synthetic-local"
LOCAL_MODEL_ID = "local-synth"
DEAD_PROVIDER_ID = "synthetic-dead"
DEAD_MODEL_ID = "unavailable-model"

TURN_TIMEOUT = 300.0

SYNTH_MATERIAL = (
    "【合成对账材料·非真实案件】\n"
    "卖方：合成卖方甲（测试数据）。买方：合成买方乙（测试数据）。\n"
    "合同总价款：人民币 137,550.25 元。\n"
    "付款期限：验收合格后 20 日内一次性支付。\n"
)
AMOUNT = "137,550.25"

# F22-A：金额只在材料文件内（§2.1 附件径证据链），模型必须经工具读取。
DEEPSEEK_TOOL_PROMPT = (
    "这是律引 F22 真实流式工具调用测试（全合成材料，非真实案件）。\n"
    "请严格按顺序：先用 glob 工具列出 materials 目录下的文件，"
    "再用 read 工具读取找到的那份材料，然后只用一行回答材料中的合同总价款"
    "数字（原样引用，不要计算，不要编造数字）。"
)
# F23-A/B：长输出轮次（制造流式窗口与断开窗口）。
LONG_OUTPUT_PROMPT = (
    "这是律引 F23 断线续播测试（全合成材料，非真实案件）。"
    "请围绕「为什么服务端拥有的运行不能因为客户端断开而取消」写一段约五百字的"
    "纯文字说明，不要分点，不要调用任何工具，连续写完。"
)
# F23-C：写副作用哨兵＋长输出（stop 落在工具完成后、文本流中）。
STOP_TURN_PROMPT = (
    "这是律引 F23 停止语义测试（全合成材料，非真实案件）。\n"
    "请严格按顺序：先用 write 工具创建文件 work/f23-sentinel.txt，"
    "内容恰好为一行：F23-SENTINEL-{token}\n"
    "写完文件后，再围绕「外部副作用未知时为什么要先对账再行动」写一段约五百字"
    "的纯文字说明，不要分点，不要调用任何工具，连续写完。\n"
)

LOCAL_SENTINEL_REL = "work/local-channel.txt"
LOCAL_SENTINEL_CONTENT = "F22 本地通道合成写入行一\nF22 本地通道合成写入行二\n"
LOCAL_TURN_PROMPT = (
    "这是律引 F22 本地模型通道测试（全合成）。请先用 write 工具创建文件 {}，"
    "内容为以下两行（原样写入）：\n{}然后只用一行报告已写入的文件路径。"
).format(LOCAL_SENTINEL_REL, LOCAL_SENTINEL_CONTENT)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def port_open(port: int, host="127.0.0.1") -> bool:
    with socket.socket() as probe:
        probe.settimeout(1.0)
        return probe.connect_ex((host, port)) == 0


def closed_port() -> int:
    """拿一个当前无人监听、且实测拒绝连接的端口（不可用具名报错的靶子）。"""
    for _ in range(20):
        port = free_port()
        if not port_open(port):
            return port
    raise RuntimeError("no closed port found")


class SseReader:
    """全局 /api/event SSE 消费者（独立线程，可粗暴杀流=断线模拟）。

    逐行读 `data: <json>` 帧；`: heartbeat` 注释行忽略（15s 一跳，
    server/handlers/event.ts）；杀流=直接关 socket，读线程以 killed 标志
    收场——这就是 F23 的「杀流/断网」。
    """

    def __init__(self, name: str, port: int, password: str):
        self.name = name
        self.port = port
        self.password = password
        self.events: list[dict] = []
        self.killed = False
        self.ended = False
        self.error: str | None = None
        self._conn: http.client.HTTPConnection | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _run(self):
        try:
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
            self._conn = conn
            token = base64.b64encode(
                ("opencode:" + self.password).encode()).decode("ascii")
            conn.request("GET", "/api/event", headers={
                "Accept": "text/event-stream",
                "Authorization": "Basic " + token,
                "Cache-Control": "no-cache",
            })
            resp = conn.getresponse()
            if resp.status != 200:
                self.error = "sse_http_{}".format(resp.status)
                self.ended = True
                return
            pending: list[str] = []
            while True:
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if text.startswith(":"):
                    continue
                if text.startswith("data:"):
                    pending.append(text[5:].strip())
                    continue
                if text == "" and pending:
                    try:
                        self.events.append(json.loads("\n".join(pending)))
                    except json.JSONDecodeError:
                        self.error = "sse_frame_invalid"
                    pending = []
                    continue
            self.ended = True
        except OSError:
            self.error = None if self.killed else "sse_connection_lost"
            self.ended = True
        except Exception as exc:  # noqa: BLE001 —— 读线程兜底，错误上交主线程断言
            self.error = "sse_reader_" + type(exc).__name__
            self.ended = True

    def kill(self):
        """粗暴断开（TCP 层杀流）：线程内 readline 抛 OSError 收场。"""
        self.killed = True
        try:
            if self._conn is not None:
                self._conn.close()
        except OSError:
            pass

    def wait_event(self, pred, deadline_s: float):
        end = time.monotonic() + deadline_s
        seen = 0
        while time.monotonic() < end:
            while seen < len(self.events):
                event = self.events[seen]
                seen += 1
                if pred(event):
                    return event
            time.sleep(0.05)
        return None

    def of_session(self, session_id: str, etype: str | None = None,
                   since_s: float | None = None,
                   until_s: float | None = None) -> list[dict]:
        out = []
        for event in self.events:
            if etype is not None and event.get("type") != etype:
                continue
            data = event.get("data") or {}
            if data.get("sessionID") not in (None, session_id):
                continue
            created_s = (event.get("created") or 0) / 1000.0
            if since_s is not None and created_s < since_s:
                continue
            if until_s is not None and created_s >= until_s:
                continue
            out.append(event)
        return out


def wait_terminal(client: Client, session_id: str, after_message_id: str,
                  timeout_s: float) -> list[dict]:
    """轮询消息历史（order=asc＋cursor 分页，生产同契约），直到该轮之后出现
    idle 行（succeeded/failed/interrupted 任一）或超时。"""
    end = time.monotonic() + timeout_s
    history: list[dict] = []
    while time.monotonic() < end:
        history = fetch_history(client, session_id)
        if idle_rows_after(history, after_message_id):
            return history
        time.sleep(0.5)
    return history


def fetch_history(client: Client, session_id: str) -> list[dict]:
    """全量消息时间线（order=asc＋cursor.next 分页链，e07 生产同契约）。"""
    return history_with_pages(client, session_id)[0]


def history_with_pages(client: Client, session_id: str):
    """同 fetch_history，另回分页链长度（cursor 重连证据用）。"""
    messages: list[dict] = []
    pages = 0
    path = "/api/session/{}/message?order=asc".format(quote(session_id, safe=""))
    while path:
        listing = client.request("GET", path)
        if not isinstance(listing, dict):
            break
        messages.extend(listing.get("data", []))
        pages += 1
        cursor = (listing.get("cursor") or {}).get("next")
        path = ("/api/session/{}/message?cursor={}".format(
            quote(session_id, safe=""), quote(str(cursor), safe=""))
            if cursor else None)
    return messages, pages


def rows_after(history: list[dict], message_id: str, kind: str) -> list[dict]:
    started = False
    out = []
    for row in history:
        if row.get("id") == message_id:
            started = True
            continue
        if started and row.get("type") == kind:
            out.append(row)
    return out


def idle_rows_after(history: list[dict], message_id: str) -> list[dict]:
    return rows_after(history, message_id, "idle")


def assistant_rows_after(history: list[dict], message_id: str) -> list[dict]:
    return rows_after(history, message_id, "assistant")


def tool_parts(history: list[dict]) -> list[dict]:
    parts = []
    for row in history:
        if row.get("type") == "assistant":
            for part in row.get("content", []) or []:
                if isinstance(part, dict) and part.get("type") == "tool":
                    parts.append(part)
    return parts


def text_of(history: list[dict]) -> str:
    chunks = []
    for row in history:
        if row.get("type") == "assistant":
            for part in row.get("content", []) or []:
                if isinstance(part, dict) and part.get("type") == "text":
                    chunks.append(part.get("text", ""))
    return "".join(chunks)


def part_status(part: dict) -> str:
    state = part.get("state") or {}
    return state.get("status") or part.get("status") or "unknown"


class LocalModelServer:
    """127.0.0.1 OpenAI 兼容 SSE 端点（本地模型通道线缆真流式；权重=合成脚本）。

    两相脚本：请求消息无 tool 行→流式 tool_calls（write 哨兵文件，参数分
    ≥6 片增量）；有 tool 行→流式文本（≥10 片）。分块传输编码真实写线。
    """

    def __init__(self, sentinel_abs: Path):
        self.sentinel_abs = sentinel_abs
        self.port = free_port()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # 静默（默认 stderr 噪声）
                pass

            def do_GET(self):
                body = json.dumps({"object": "list", "data": [
                    {"id": LOCAL_MODEL_ID, "object": "model"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                used_tool = any(m.get("role") == "tool"
                                for m in payload.get("messages", []))
                # close-delimited SSE（HTTP/1.1 无 Content-Length/无
                # Transfer-Encoding，Connection: close 收尾即正文结束）：
                # 帧=`data: <json>\n\n`（与 oc28 EventFeed.frame 同形），
                # 终结=`data: [DONE]\n\n`。零手工 chunked 帧，免帧形差错。
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                def chunk(delta, finish=None):
                    return json.dumps({
                        "id": "chatcmpl-local-synth",
                        "object": "chat.completion.chunk", "created": 0,
                        "model": LOCAL_MODEL_ID,
                        "choices": [{"index": 0, "delta": delta,
                                     "finish_reason": finish}]},
                        ensure_ascii=False).encode("utf-8")

                def write(frame: bytes):
                    self.wfile.write(b"data: " + frame + b"\n\n")
                    self.wfile.flush()

                write(chunk({"role": "assistant", "content": None}))
                if not used_tool:
                    args = json.dumps({
                        "path": str(outer.sentinel_abs),
                        "content": LOCAL_SENTINEL_CONTENT}, ensure_ascii=False)
                    write(chunk({"tool_calls": [{
                        "index": 0, "id": "call_local_synth",
                        "type": "function", "function": {
                            "name": "write", "arguments": ""}}]}))
                    step = max(8, len(args) // 6)
                    for i in range(0, len(args), step):
                        write(chunk({"tool_calls": [{
                            "index": 0, "function": {
                                "arguments": args[i:i + step]}}]}))
                        time.sleep(0.03)
                    write(chunk({}, finish="tool_calls"))
                else:
                    text = "已写入本地通道哨兵文件（合成端点流式回执）。" * 4
                    for i in range(0, len(text), 12):
                        write(chunk({"content": text[i:i + 12]}))
                        time.sleep(0.03)
                    write(chunk({}, finish="stop"))
                write(json.dumps({
                    "id": "chatcmpl-local-synth",
                    "object": "chat.completion.chunk", "created": 0,
                    "model": LOCAL_MODEL_ID, "choices": [],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                              "total_tokens": 2}}).encode("utf-8"))
                write(b"[DONE]")
                self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.server.daemon_threads = True
        self._thread = threading.Thread(target=self.server.serve_forever,
                                        daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class Recon:
    def __init__(self, oc28: Path, profile: str, keep: bool):
        self.oc28 = oc28
        self.profile = profile
        self.keep = keep
        self.checks: list[dict] = []
        self.temp: dict | None = None
        self.service: subprocess.Popen | None = None
        self.port: int | None = None
        self.requested_port: int | None = None
        self.password: str | None = None
        self.local_server: LocalModelServer | None = None
        self.ts = time.strftime("%Y%m%dT%H%M%S")

    # -- check plumbing ------------------------------------------------------

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def blocked(self, reason, **facts):
        print(json.dumps({"check": reason, "status": "BLOCKED", **facts},
                         ensure_ascii=False), flush=True)
        print(json.dumps({"status": "RECON_BLOCKED", "profile": self.profile,
                          "reason": reason}, ensure_ascii=False))
        raise SystemExit(3)

    # -- %APPDATA% 只读证明 ---------------------------------------------------

    @staticmethod
    def snapshot_appdata() -> dict:
        appdata = Path(os.environ["APPDATA"]) / "Juscite"
        snap = {}
        target = appdata / "config" / "opencode" / "opencode.json"
        if target.exists():
            stat = target.stat()
            snap["config/opencode/opencode.json"] = (stat.st_size,
                                                     stat.st_mtime_ns)
        state_dir = appdata / "state" / "opencode"
        if state_dir.is_dir():
            for item in sorted(state_dir.glob("*.json")):
                stat = item.stat()
                snap["state/opencode/" + item.name] = (stat.st_size,
                                                       stat.st_mtime_ns)
        return snap

    # -- service lifecycle ----------------------------------------------------

    def launch(self) -> dict:
        roots = self.temp
        env = {k: v for k, v in os.environ.items()}
        env["XDG_STATE_HOME"] = str(roots["state_root"])
        env["XDG_DATA_HOME"] = str(roots["data_root"])
        env["XDG_CONFIG_HOME"] = str(roots["config_root"])
        env["XDG_CACHE_HOME"] = str(roots["cache_root"])
        env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"   # models.dev 禁轮询（T07/T08）
        env["OPENCODE_CHANNEL"] = "local"
        env["OPENCODE_VERSION"] = DEV_VERSION
        self.password = secrets.token_urlsafe(32)
        base_argv = [str(self.bun), "run", "--cwd", "packages/cli",
                     "--define=OPENCODE_VERSION=process.env.OPENCODE_VERSION",
                     "src/index.ts", "serve",
                     "--hostname", "127.0.0.1", "--port",
                     str(self.requested_port)]
        if self.profile == "desktop":
            # 产品桌面托管拓扑：serve --service → 注册文件（e07/W2a-U17 同形）。
            argv = base_argv + ["--service"]
        else:
            # 自托管前台拓扑：serve 前台＋环境注入密码（cli/env.ts:10-11），
            # URL 从 stdout「server listening on <url>」读取。
            env["OPENCODE_SERVER_PASSWORD"] = self.password
            argv = base_argv
        log = open(roots["service_log"], "ab")
        self.service = subprocess.Popen(argv, cwd=str(self.oc28), env=env,
                                        stdout=log, stderr=subprocess.STDOUT)
        return self.wait_ready()

    def wait_ready(self) -> dict:
        deadline = time.monotonic() + 240.0
        reg = None
        if self.profile == "desktop":
            reg_path = (self.temp["state_root"] / "opencode" /
                        "service-local.json")
            while time.monotonic() < deadline:
                if self.service is not None and self.service.poll() is not None:
                    self.blocked("service_process_exited",
                                 exit_code=self.service.returncode,
                                 log=str(self.temp["service_log"]))
                if reg_path.exists():
                    try:
                        reg = json.loads(reg_path.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        reg = None
                if reg is not None and reg.get("password"):
                    break
                time.sleep(1.0)
            if reg is None:
                self.blocked("service_registration_timeout",
                             log=str(self.temp["service_log"]))
            self.port = int(str(reg["url"]).rsplit(":", 1)[1])
            self.password = reg["password"]   # 服务实际租约密码（注册文件为准）
        else:
            log_path = Path(self.temp["service_log"])
            url = None
            while time.monotonic() < deadline:
                if self.service is not None and self.service.poll() is not None:
                    self.blocked("service_process_exited",
                                 exit_code=self.service.returncode,
                                 log=str(log_path))
                try:
                    text = log_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                for line in text.splitlines():
                    if "server listening on" in line:
                        url = line.rsplit(" ", 1)[-1].strip()
                if url:
                    break
                time.sleep(1.0)
            if not url:
                self.blocked("selfhost_url_timeout", log=str(log_path))
            self.port = int(str(url).rsplit(":", 1)[1])
            reg = {"url": url, "topology": "selfhost-foreground"}
        client = self.build_client()
        value = client.request("GET", "/api/info")
        info = value.get("data", value) if isinstance(value, dict) else {}
        version = info.get("version") if isinstance(info, dict) else None
        ok = (version == DEV_VERSION and bool(self.password)
              and port_open(self.port)
              and str(reg["url"]).endswith(":{}".format(self.requested_port)))
        self.step("topology_service_ready", ok,
                  profile=self.profile, requested_port=self.requested_port,
                  served_port=self.port, version=version,
                  dev_version=(version != "2.0.28"),
                  registration=("state/opencode/service-local.json"
                                if self.profile == "desktop"
                                else "none(stdout-url)"))
        return reg

    def build_client(self, timeout: float = 60.0) -> Client:
        token = base64.b64encode(
            ("opencode:" + self.password).encode()).decode("ascii")
        return Client("http://127.0.0.1:{}".format(self.port),
                      headers={"Authorization": "Basic " + token},
                      timeout=timeout)

    def kill_service(self):
        if self.service is None or self.service.poll() is not None:
            self.service = None
            return
        pid = self.service.pid
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True, timeout=60)
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if not port_open(self.port) and not _pid_alive(pid):
                break
            time.sleep(1.0)
        self.service = None

    # -- run ------------------------------------------------------------------

    def run(self, bun: Path) -> int:
        self.bun = bun
        base = Path(tempfile.mkdtemp(prefix="f22f23-{}-".format(self.profile)))
        roots = {"base": base}
        for key in ("state_root", "data_root", "config_root", "cache_root"):
            roots[key] = base / "oc" / key.split("_")[0]
            roots[key].mkdir(parents=True)
        roots["workspace"] = base / "workspace"
        (roots["workspace"] / "materials").mkdir(parents=True)
        (roots["workspace"] / "work").mkdir(parents=True)
        roots["service_log"] = base / "service.log"
        self.temp = roots
        try:
            return self._phases(roots)
        finally:
            self._teardown()

    def _teardown(self):
        if self.local_server is not None:
            try:
                self.local_server.stop()
            except Exception:
                pass
        try:
            self.kill_service()
        except Exception:
            if self.service is not None:
                subprocess.run(["taskkill", "/F", "/T",
                                "/PID", str(self.service.pid)],
                               capture_output=True, timeout=60)
        if self.temp is not None and not self.keep:
            shutil.rmtree(self.temp["base"], ignore_errors=True)
        elif self.temp is not None:
            print(json.dumps({"kept_temp_root": str(self.temp["base"])},
                             ensure_ascii=False), flush=True)

    def _phases(self, roots) -> int:
        # ---- 阶段 0：前置与只读快照 --------------------------------------
        before = self.snapshot_appdata()
        product_config = (Path(os.environ["APPDATA"]) / "Juscite" / "config" /
                          "opencode" / "opencode.json")
        if not product_config.exists():
            self.blocked("product_config_missing", path=str(product_config))
        try:
            product_cfg = json.loads(product_config.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.blocked("product_config_unreadable")
        byok = (product_cfg.get("provider", {}) or {}).get(PROVIDER_ID)
        if not isinstance(byok, dict) or not (
                (byok.get("options") or {}).get("apiKey")):
            self.blocked("byok_provider_missing", provider=PROVIDER_ID,
                         note="总账 §3.1 ③ DeepSeek BYOK key 未配置")
        self.step("local_model_channel_form_recorded", True,
                  ollama_installed=_ollama_installed(),
                  note="F22 本地模型段形态具名记录：本机 Ollama 未装（总账 §1"
                       "环境事实，不冒装）；本地通道以 recon 进程内 127.0.0.1 "
                       "OpenAI 兼容 SSE 端点（llama.cpp/Ollama OpenAI 兼容层"
                       "同形线缆协议）真流式实测——线缆/解析/工具执行全真实，"
                       "仅模型权重=合成脚本（测试一律合成材料红线）")

        # 临时配置副本 = 产品原样＋本单两个合成 provider（只写临时根）。
        dead_port = closed_port()
        self.local_server = LocalModelServer(
            roots["workspace"] / LOCAL_SENTINEL_REL).start()
        cfg = json.loads(json.dumps(product_cfg))     # 深拷贝，产品文件零触碰
        providers = cfg.setdefault("provider", {})
        providers[LOCAL_PROVIDER_ID] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Synthetic Local (recon)",
            "options": {"baseURL": "http://127.0.0.1:{}/v1".format(
                self.local_server.port), "apiKey": "synthetic-local-key"},
            "models": {LOCAL_MODEL_ID: {"name": "Local Synthetic Streaming"}},
        }
        providers[DEAD_PROVIDER_ID] = {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Synthetic Dead (recon)",
            "options": {"baseURL": "http://127.0.0.1:{}/v1".format(dead_port),
                        "apiKey": "synthetic-dead-key"},
            "models": {DEAD_MODEL_ID: {"name": "Unavailable Model"}},
        }
        opencode_config_dir = roots["config_root"] / "opencode"
        opencode_config_dir.mkdir(parents=True, exist_ok=True)
        (opencode_config_dir / "opencode.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
        (roots["workspace"] / "materials" /
         "合成材料-F22流式.txt").write_text(SYNTH_MATERIAL, encoding="utf-8")
        self.requested_port = free_port()
        self.step("topology_temp_roots", all(
            str(roots[key]).startswith(str(roots["base"]))
            for key in ("state_root", "data_root", "config_root",
                        "cache_root")),
            base=str(roots["base"]), profile=self.profile,
            synthetic_providers=[LOCAL_PROVIDER_ID, DEAD_PROVIDER_ID],
            dead_port=dead_port, local_endpoint_port=self.local_server.port)

        # ---- 阶段 1：服务拉起（双形态拓扑）＋experimental log 边界考据 ------
        self.launch()
        client = self.build_client()
        self._phase_experimental_log_boundary(client)

        # ---- F22-A：DeepSeek BYOK 真实流式工具调用（M 组干净会话纪律）----
        self._phase_byok_stream(client)

        # ---- F22-B：本地模型通道（127.0.0.1 OpenAI 兼容 SSE 真流式）------
        self._phase_local_stream(client)

        # ---- F22-C：模型不可用具名报错不伪输出 ----------------------------
        self._phase_unavailable_named(client)

        # ---- F23-A：关窗/断线不取消 run（全程零消费者跑完）----------------
        self._phase_detached_run(client)

        # ---- F23-B：cursor 重连＋流缺口 resync（两次杀流链）---------------
        self._phase_cursor_resync(client)

        # ---- F23-C/D/E：stop 独立终态＋迟到 finish 不覆＋副作用对账 -------
        self._phase_stop_semantics(client)

        # ---- F23-F：resume:false 持久入队锚点（e07 已深证，此处复锚）------
        self._phase_resume_false_anchor(client)

        # ---- 卫生断言 ------------------------------------------------------
        after = self.snapshot_appdata()
        self.step("appdata_juscite_read_only", after == before,
                  watched=sorted(before))
        self.kill_service()
        self.step("teardown_service_killed", not port_open(self.port),
                  port=self.port)
        return 0

    # -- experimental log 边界（本单活证，不冒验）-----------------------------

    def _phase_experimental_log_boundary(self, client: Client):
        session_id = "ses_f23_logbound_{}".format(self.ts)
        client.create({"id": session_id, "title": "律引 log 边界（合成）",
                       "location": {"directory": str(self.temp["workspace"])},
                       "model": {"id": MODEL_ID, "providerID": PROVIDER_ID}})
        prompt_id = "msg_f23_logbound_{}".format(self.ts)
        client.prompt(session_id, {"id": prompt_id,
                                   "text": "（合成）只回答两个字：收到。"
                                           "不要调用工具。"})
        history = wait_terminal(client, session_id, prompt_id, 120.0)
        idles = idle_rows_after(history, prompt_id)
        if not idles or idles[-1].get("outcome") != "succeeded":
            self.blocked("model_round_not_complete", phase="log-boundary")
        # 纯回放（无 follow）：完整轮次落账后读 experimental log。
        replayed = self._replay_experimental_log(session_id)
        self.step("f23_experimental_log_persist_off_boundary",
                  replayed["events"] == 0 and replayed["marker"] is True,
                  replay_events=replayed["events"],
                  synced_marker=replayed["marker"],
                  marker_seq=replayed["seq"],
                  history_rows=len(history),
                  note="边界如实：experimental 持久 log 端点在本产品拓扑"
                       "events.persist=false（cli/server-process.ts 不传 "
                       "events；bus.ts:203 默认 false→EventTable 不落盘），"
                       "完整轮次后回放恒空、仅 seq watermark marker——"
                       "F23 resync 不冒验此端点，落在持久消息账 cursor（F23-B）")

    def _replay_experimental_log(self, session_id: str) -> dict:
        path = "/api/experimental/session/{}/log".format(
            quote(session_id, safe=""))
        token = base64.b64encode(
            ("opencode:" + self.password).encode()).decode("ascii")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request("GET", path, headers={
                "Accept": "text/event-stream",
                "Authorization": "Basic " + token})
            resp = conn.getresponse()
            events = 0
            marker = False
            seq = None
            pending: list[str] = []
            while True:
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if text.startswith(":"):
                    continue
                if text.startswith("data:"):
                    pending.append(text[5:].strip())
                    continue
                if text == "" and pending:
                    try:
                        item = json.loads("\n".join(pending))
                    except json.JSONDecodeError:
                        item = {}
                    if item.get("type") == "log.synced":
                        marker = True
                        seq = item.get("seq")
                    else:
                        events += 1
                    pending = []
            return {"events": events, "marker": marker, "seq": seq}
        finally:
            conn.close()

    # -- F22-A ---------------------------------------------------------------

    def _phase_byok_stream(self, client: Client):
        session_id = "ses_f22_byok_{}".format(self.ts)
        client.create({"id": session_id, "title": "律引 F22 BYOK 流式（合成）",
                       "location": {"directory": str(self.temp["workspace"])},
                       "model": {"id": MODEL_ID, "providerID": PROVIDER_ID}})
        reader = SseReader("byok", self.port, self.password).start()
        prompt_id = "msg_f22_byok_{}".format(self.ts)
        client.prompt(session_id, {"id": prompt_id,
                                   "text": DEEPSEEK_TOOL_PROMPT})
        history = wait_terminal(client, session_id, prompt_id, TURN_TIMEOUT)
        reader.kill()
        idles = idle_rows_after(history, prompt_id)
        if not idles or idles[-1].get("outcome") != "succeeded":
            self.blocked("model_round_not_complete", phase="f22-byok",
                         outcomes=[i.get("outcome") for i in idles])
        assistants = assistant_rows_after(history, prompt_id)
        text = text_of(history)
        parts = tool_parts(history)
        text_deltas = reader.of_session(session_id, "session.text.delta")
        tool_started = reader.of_session(session_id, "session.tool.input.started")
        tool_called = reader.of_session(session_id, "session.tool.called")
        steps = reader.of_session(session_id, "session.step.started")
        usage = reader.of_session(session_id, "session.usage.updated")
        succeeded = reader.of_session(session_id, "session.execution.succeeded")
        self.step("f22_byok_real_streaming_tool_calls",
                  len(text_deltas) >= 1 and len(tool_started) >= 2
                  and len(tool_called) >= 2 and len(steps) >= 2
                  and len(succeeded) == 1,
                  assistant_messages=len(assistants),
                  text_delta_events=len(text_deltas),
                  tool_input_started_events=len(tool_started),
                  tool_called_events=len(tool_called),
                  step_started_events=len(steps),
                  execution_succeeded_events=len(succeeded),
                  note="全局事件流活证真实流式工具调用：text.delta ≥1（文本流式"
                       "增量，批发 100ms=publish-llm-event.ts "
                       "deltaBatchInterval）＋tool.input.started ≥2（glob+read"
                       " 工具调用流式装配）＋tool.called ≥2＋step.started ≥2"
                       "（多步工具链）＋execution.succeeded 恰 1。边界如实："
                       "provider 原子 tool-call 下 tool.input.started 会在 "
                       "tool-call 时刻补发（publish-llm-event.ts:325 fallback），"
                       "分片组装的流式证明由 F22-B 本地通道承载（参数 ≥6 片、"
                       "拼装失败即整轮失败）；tool.input.delta 事件本构建 "
                       "runner 不发布（fragments 无 delta 回调，"
                       "publish-llm-event.ts:250-258），不作断言")
        self.step("f22_byok_tool_parts_completed",
                  len(parts) >= 2
                  and all(part_status(p) == "completed" for p in parts),
                  parts=[{"tool": p.get("name"), "status": part_status(p)}
                         for p in parts],
                  note="glob→read 工具链真实执行（工具定义真实下发= T13 修正后"
                       "权限序；工具部件状态 completed）")
        self.step("f22_byok_attachment_chain_grounding",
                  AMOUNT in text and AMOUNT not in DEEPSEEK_TOOL_PROMPT,
                  amount=AMOUNT,
                  note="金额只在合成材料文件内（prompt 无答案）——模型经工具"
                       "读取后原样引用（§2.1 附件径证据链纪律）")
        self.step("f22_byok_usage_recorded", len(usage) >= 1,
                  usage_events=len(usage))

    # -- F22-B ---------------------------------------------------------------

    def _phase_local_stream(self, client: Client):
        session_id = "ses_f22_local_{}".format(self.ts)
        client.create({"id": session_id, "title": "律引 F22 本地通道（合成）",
                       "location": {"directory": str(self.temp["workspace"])},
                       "model": {"id": LOCAL_MODEL_ID,
                                 "providerID": LOCAL_PROVIDER_ID}})
        reader = SseReader("local", self.port, self.password).start()
        prompt_id = "msg_f22_local_{}".format(self.ts)
        client.prompt(session_id, {"id": prompt_id,
                                   "text": LOCAL_TURN_PROMPT})
        history = wait_terminal(client, session_id, prompt_id, TURN_TIMEOUT)
        reader.kill()
        idles = idle_rows_after(history, prompt_id)
        if not idles or idles[-1].get("outcome") != "succeeded":
            self.blocked("model_round_not_complete", phase="f22-local",
                         outcomes=[i.get("outcome") for i in idles])
        parts = tool_parts(history)
        text_deltas = reader.of_session(session_id, "session.text.delta")
        tool_started = reader.of_session(session_id, "session.tool.input.started")
        target = self.temp["workspace"] / LOCAL_SENTINEL_REL
        disk = target.read_text(encoding="utf-8") if target.exists() else None
        self.step("f22_local_streaming_tool_round",
                  len(parts) >= 1 and part_status(parts[0]) == "completed"
                  and len(text_deltas) >= 1 and len(tool_started) >= 1,
                  tool_parts=[{"tool": p.get("name"),
                               "status": part_status(p)} for p in parts],
                  text_delta_events=len(text_deltas),
                  tool_input_started_events=len(tool_started),
                  note="本地通道（127.0.0.1 OpenAI 兼容 SSE 端点）真流式："
                       "分块传输/tool_calls 增量组装（参数 ≥6 片分片写线，拼装"
                       "失败即整轮失败＝流式装配硬证明）/权限闸/工具执行全真实；"
                       "模型权重=合成脚本（测试一律合成材料）")
        self.step("f22_local_side_effect_on_disk",
                  disk == LOCAL_SENTINEL_CONTENT,
                  file=str(target), exists=target.exists(),
                  bytes_equal=disk == LOCAL_SENTINEL_CONTENT,
                  note="工具写副作用盘上逐字节回读")

    # -- F22-C ---------------------------------------------------------------

    def _phase_unavailable_named(self, client: Client):
        session_id = "ses_f22_dead_{}".format(self.ts)
        client.create({"id": session_id, "title": "律引 F22 不可用（合成）",
                       "location": {"directory": str(self.temp["workspace"])},
                       "model": {"id": DEAD_MODEL_ID,
                                 "providerID": DEAD_PROVIDER_ID}})
        prompt_id = "msg_f22_dead_{}".format(self.ts)
        client.prompt(session_id, {"id": prompt_id,
                                   "text": DEEPSEEK_TOOL_PROMPT})
        history = wait_terminal(client, session_id, prompt_id, TURN_TIMEOUT)
        idles = idle_rows_after(history, prompt_id)
        error = idles[-1].get("error") if idles else None
        fabricated = [t for t in [text_of(history)] if t.strip()]
        self.step("f22_unavailable_named_error_no_fake_output",
                  len(idles) >= 1 and idles[-1].get("outcome") == "failed"
                  and bool(error) and not fabricated,
                  outcome=idles[-1].get("outcome") if idles else None,
                  error_name=(error or {}).get("name")
                  if isinstance(error, dict) else None,
                  error_excerpt=(json.dumps(error, ensure_ascii=False)[:220]
                                if error else None),
                  assistant_text_parts=len(fabricated),
                  note="模型不可用→idle 终态 outcome=failed＋具名 error（连接"
                       "拒绝经透明重试耗尽后 failed，runner/retry.ts 上限 10 "
                       "次≈84-101s）；该轮零 assistant 文本部件＝不伪输出")

    # -- F23-A ---------------------------------------------------------------

    def _phase_detached_run(self, client: Client):
        session_id = "ses_f23_detach_{}".format(self.ts)
        client.create({"id": session_id, "title": "律引 F23 断线续跑（合成）",
                       "location": {"directory": str(self.temp["workspace"])},
                       "model": {"id": MODEL_ID, "providerID": PROVIDER_ID}})
        # 先订后发：全局事件流见首条流式增量→杀流（=关窗/断网），随后零 HTTP。
        reader = SseReader("detach", self.port, self.password).start()
        prompt_id = "msg_f23_detach_{}".format(self.ts)
        client.prompt(session_id, {"id": prompt_id,
                                   "text": LONG_OUTPUT_PROMPT})
        first = reader.wait_event(
            lambda e: e.get("type") == "session.text.delta"
            and (e.get("data") or {}).get("sessionID") == session_id, 120.0)
        if first is None:
            reader.kill()
            self.blocked("detach_no_streaming_observed", phase="f23-detach")
        t_kill = time.time()
        pre = fetch_history(client, session_id)
        pre_kill_ids = {m.get("id") for m in pre}
        pre_kill_text_len = len(text_of(pre))
        reader.kill()                       # 杀流＋随后零 HTTP 往返（关窗态）
        detach_window_s = 12.0
        time.sleep(detach_window_s)
        t_reconnect = time.time()
        # 重连：新活流消费者（只得窗后增量）＋持久消息账回读（补齐缺口）。
        reader2 = SseReader("detach-reconnect", self.port,
                            self.password).start()
        history = wait_terminal(client, session_id, prompt_id, TURN_TIMEOUT)
        reader2.kill()
        idles = idle_rows_after(history, prompt_id)
        recovered = [m.get("id") for m in history
                     if m.get("id") not in pre_kill_ids]
        final_text = text_of(history)
        self.step("f23_disconnect_run_not_cancelled",
                  bool(idles) and idles[-1].get("outcome") == "succeeded"
                  and len(recovered) >= 1
                  and len(final_text) > pre_kill_text_len,
                  killed_at=t_kill, reconnected_at=t_reconnect,
                  detach_window_s=detach_window_s,
                  pre_kill_message_rows=len(pre_kill_ids),
                  pre_kill_text_chars=pre_kill_text_len,
                  gap_rows_recovered=len(recovered),
                  recovered_kinds=sorted(
                      {m.get("type") for m in history
                       if m.get("id") not in pre_kill_ids}),
                  final_text_chars=len(final_text),
                  grew_during_detach=(len(final_text) > pre_kill_text_len),
                  note="唯一消费者杀流后全程零客户端流量，run 照常完成"
                       "（server-owned run：session.ts:174 入队后服务端 fiber"
                       "执行；session.ts:192 服务端拥有完成记录）；断开窗内"
                       "文本净增长（%d→%d 字符）＋缺口行（%s）由持久消息账"
                       "补齐".format(pre_kill_text_len, len(final_text),
                                    ",".join(sorted(
                                        {m.get("type") for m in history
                                         if m.get("id") not in pre_kill_ids})
                                    ) or "none"))

    # -- F23-B ---------------------------------------------------------------

    def _phase_cursor_resync(self, client: Client):
        session_id = "ses_f23_resync_{}".format(self.ts)
        client.create({"id": session_id, "title": "律引 F23 缺口重同步（合成）",
                       "location": {"directory": str(self.temp["workspace"])},
                       "model": {"id": MODEL_ID, "providerID": PROVIDER_ID}})
        reader = SseReader("resync", self.port, self.password).start()
        prompt_id = "msg_f23_resync_{}".format(self.ts)
        client.prompt(session_id, {"id": prompt_id,
                                   "text": LONG_OUTPUT_PROMPT})
        got = reader.wait_event(
            lambda e: e.get("type") == "session.text.delta"
            and (e.get("data") or {}).get("sessionID") == session_id, 120.0)
        if got is None:
            reader.kill()
            self.blocked("resync_no_streaming_observed", phase="f23-resync")
        # 断点 1：锚定当前消息账 id 集→杀流（缺口窗 1）。
        snap1 = {m.get("id") for m in fetch_history(client, session_id)}
        reader.kill()
        time.sleep(8.0)                      # 缺口窗 1：无任何消费者
        # 重连 1：cursor 分页链整读时间线（回放缺口 1）。
        hist1, pages1 = history_with_pages(client, session_id)
        term1 = idle_rows_after(hist1, prompt_id)
        # 断点 2：再挂消费者→（若仍在流式则攒一段 live）→再杀（缺口窗 2）。
        reader2 = SseReader("resync-2", self.port, self.password).start()
        got2 = reader2.wait_event(
            lambda e: e.get("type") == "session.text.delta"
            and (e.get("data") or {}).get("sessionID") == session_id, 20.0)
        if got2 is not None:
            time.sleep(2.0)                  # 攒一段 live（流式仍在的分支）
        snap2 = {m.get("id") for m in fetch_history(client, session_id)}
        reader2.kill()
        time.sleep(6.0)                      # 缺口窗 2
        # 重连 2：cursor 分页链整读（回放缺口 2）→至终态。
        hist2, pages2 = history_with_pages(client, session_id)
        idles = idle_rows_after(hist2, prompt_id)
        ids1 = [m.get("id") for m in hist1]
        ids2 = [m.get("id") for m in hist2]
        gap1 = sorted({m.get("type") for m in hist1
                       if m.get("id") not in snap1})
        gap2 = sorted({m.get("type") for m in hist2
                       if m.get("id") not in snap2})
        text = text_of(hist2)
        branch = ("completed_during_gap1" if term1
                  else "streaming_at_reconnect1")
        self.step("f23_cursor_reconnect_gap_resync",
                  bool(idles) and idles[-1].get("outcome") == "succeeded"
                  and len(hist1) - len(snap1) >= 1
                  and len(ids1) == len(set(ids1))
                  and len(ids2) == len(set(ids2))
                  and set(ids1) <= set(ids2)
                  and len(text) >= 100,
                  branch=branch,
                  cursor_chain_pages=[pages1, pages2],
                  read1_rows=len(ids1), read2_rows=len(ids2),
                  read1_unique=len(set(ids1)), read2_unique=len(set(ids2)),
                  timeline_monotone=set(ids1) <= set(ids2),
                  gap1_rows_recovered=len(hist1) - len(snap1),
                  gap1_kinds=gap1,
                  gap2_rows_recovered=len(hist2) - len(snap2),
                  gap2_kinds=gap2,
                  live_deltas_after_reconnect=(1 if got2 is not None else 0),
                  final_text_chars=len(text),
                  note="两次杀流两级 cursor 重连：每次重连经 order=asc＋"
                       "cursor.next 分页链整读持久时间线（生产同契约，e07 "
                       "_fetch_messages 同形）；每次读内零重复、时间线单调"
                       "收敛（第二次读 ⊇ 第一次读）、缺口行由消息账补齐、"
                       "终态 idle(succeeded)、最终文本完整；分支=" + branch
                       + "（完成时序无关：终态前/后断开均覆盖）")
        # 收敛对账：补齐后的时间线终态 == 持久账终态（回读为准绳）。
        self.step("f23_resync_converges_with_history",
                  bool(idles) and idles[-1].get("outcome") == "succeeded"
                  and len(text) >= 100,
                  history_terminal=idles[-1].get("outcome") if idles else None,
                  note="流缺口 resync 后与持久消息账对账一致（e07 文件头："
                       "消息历史含 idle 标记，回读为准绳，不依赖 SSE）")

    # -- F23-C/D/E -----------------------------------------------------------

    def _phase_stop_semantics(self, client: Client):
        token = secrets.token_hex(8)
        session_id = "ses_f23_stop_{}".format(self.ts)
        client.create({"id": session_id, "title": "律引 F23 停止语义（合成）",
                       "location": {"directory": str(self.temp["workspace"])},
                       "model": {"id": MODEL_ID, "providerID": PROVIDER_ID}})
        reader = SseReader("stop", self.port, self.password).start()
        prompt_id = "msg_f23_stop_{}".format(self.ts)
        client.prompt(session_id, {"id": prompt_id,
                                   "text": STOP_TURN_PROMPT.format(token=token)})
        # 等 write 工具部件在消息账落为 completed（副作用已定）→ stop 落在
        # 其后文本流中。避开「事件未及落账先被杀」的 at-least-once 竞态。
        deadline = time.monotonic() + 120.0
        write_done = False
        while time.monotonic() < deadline:
            parts = [p for p in tool_parts(fetch_history(client, session_id))
                     if p.get("name") == "write"]
            if parts and all(part_status(p) == "completed" for p in parts):
                write_done = True
                break
            time.sleep(0.5)
        if not write_done:
            reader.kill()
            self.blocked("stop_write_tool_not_completed", phase="f23-stop")
        interrupted = client.interrupt(session_id)
        interrupted_value = interrupted.get("data", interrupted) if isinstance(
            interrupted, dict) else {}
        t_stop = time.time()
        # 迟到 finish 观察窗：远超「迟到的正常完成」落地所需时间量级。
        reader.wait_event(lambda e: False, 10.0)
        reader.kill()
        time.sleep(3.0)                      # 事件投影沉淀
        history = fetch_history(client, session_id)
        idles = idle_rows_after(history, prompt_id)
        outcomes = [i.get("outcome") for i in idles]
        succeeded_after = [i for i in idles if i.get("outcome") == "succeeded"]
        # stop 后无新 step：session.step.started 经全局事件流可数（持久事件，
        # schema/session-event.ts:326-340），created ≥ t_stop 必为零。
        # t_stop=interrupt 被服务端接受（interrupted=true 返回）时刻。机制
        # （run-coordinator.ts:147-168）：interrupt=fire-and-forget Fiber.
        # interrupt，owner fiber 在不可中断写里把在途 step.started 冲完
        # （publish-llm-event.ts:169-171）——那是清理尾不是新步；断言=清理尾
        # 窗（3s）后观察窗内零新 step。
        cleanup_tail_s = 3.0
        steps_cleanup_tail = reader.of_session(
            session_id, "session.step.started",
            since_s=t_stop - 0.05, until_s=t_stop + cleanup_tail_s)
        steps_after_stop = reader.of_session(
            session_id, "session.step.started", since_s=t_stop + cleanup_tail_s)
        exec_succeeded_after = reader.of_session(
            session_id, "session.execution.succeeded", since_s=t_stop - 0.05)
        sentinel = self.temp["workspace"] / "work" / "f23-sentinel.txt"
        disk = (sentinel.read_text(encoding="utf-8")
                if sentinel.exists() else None)
        expected = "F23-SENTINEL-{}".format(token)
        write_parts = [p for p in tool_parts(history)
                       if p.get("name") == "write"]
        write_completed = bool(write_parts) and all(
            part_status(p) == "completed" for p in write_parts)
        # 外部副作用对账：盘上实态 ↔ 消息账工具态，两源一致才算数（分支如实记）。
        reconcile = ((write_completed and disk is not None
                      and disk.strip() == expected)
                     or (not write_completed and disk is None))
        branch = ("tool_completed_file_present" if write_completed
                  else "tool_not_completed_file_absent")
        self.step("f23_stop_independent_terminal",
                  bool(interrupted_value.get("interrupted")) and len(idles) >= 1
                  and outcomes[-1] == "interrupted"
                  and not steps_after_stop,
                  interrupted_flag=interrupted_value.get("interrupted"),
                  idle_rows=len(idles), outcomes=outcomes,
                  cleanup_tail_steps=len(steps_cleanup_tail),
                  new_steps_after_cleanup=len(steps_after_stop),
                  cleanup_tail_s=cleanup_tail_s, observe_window_s=10.0,
                  note="stop=独立终态：idle 行 outcome=interrupted（"
                       "execution.ts:50-54 三值终态；message-updater.ts:148 "
                       "append 不覆写）；interrupt=fire-and-forget（"
                       "run-coordinator.ts:161），清理尾窗内在途 step.started "
                       "照常落账（{} 条，如实记），其后观察窗零新 step".format(
                           len(steps_cleanup_tail)))
        self.step("f23_late_finish_does_not_override_stop",
                  len(succeeded_after) == 0 and len(exec_succeeded_after) == 0,
                  observe_window_s=10.0,
                  succeeded_idle_after_stop=len(succeeded_after),
                  succeeded_events_after_stop=len(exec_succeeded_after),
                  note="stop 后 10s 观察窗（≥500 字正常完成所需时间量级）："
                       "事件流与消息账双侧零 succeeded——终态每忙碌期只发一次"
                       "（execution.ts:118），迟到 finish 不覆停止")
        self.step("f23_side_effect_reconciled", reconcile,
                  write_tool_status=("completed" if write_completed
                                     else ("present_not_completed"
                                           if write_parts else "absent")),
                  sentinel_on_disk=disk is not None,
                  disk_matches=(disk is not None
                                and disk.strip() == expected),
                  branch=branch,
                  note="外部副作用未知先对账：盘上实态↔消息账工具态两源对表"
                       "（restart.ts:52-53 at-least-once 纪律），不凭事件流"
                       "推断；实际分支={}".format(branch))
        # stop 后会话健康：下一短轮正常完成（claim 已释放、run 栈无残尸）。
        redo_id = "msg_f23_after_stop_{}".format(self.ts)
        client.prompt(session_id, {"id": redo_id,
                                   "text": "（合成）只回答两个字：收到。"
                                           "不要调用工具。"})
        redo_history = wait_terminal(client, session_id, redo_id, TURN_TIMEOUT)
        redo_idles = idle_rows_after(redo_history, redo_id)
        self.step("f23_session_healthy_after_stop",
                  bool(redo_idles)
                  and redo_idles[-1].get("outcome") == "succeeded",
                  next_turn_terminal=(redo_idles[-1].get("outcome")
                                      if redo_idles else None),
                  note="stop 只终当轮：后续轮次照常完成（用户 interrupt 释放"
                       "执行 claim，execution.ts:129-135）")

    # -- F23-F ---------------------------------------------------------------

    def _phase_resume_false_anchor(self, client: Client):
        session_id = "ses_f23_park_{}".format(self.ts)
        client.create({"id": session_id, "title": "律引 F23 入队锚点（合成）",
                       "location": {"directory": str(self.temp["workspace"])},
                       "model": {"id": MODEL_ID, "providerID": PROVIDER_ID}})
        parked_id = "msg_f23_parked_{}".format(self.ts)
        admitted = client.prompt(session_id, {
            "id": parked_id, "text": "（合成）占位入队：不应被执行",
            "resume": False})
        admitted_value = admitted.get("data", admitted) if isinstance(
            admitted, dict) else {}
        inbox = client.inbox(session_id)
        items = inbox.get("data", []) if isinstance(inbox, dict) else []
        in_inbox = parked_id in {i.get("id") for i in items
                                 if isinstance(i, dict)}
        time.sleep(3.0)
        history = fetch_history(client, session_id)
        delivered = parked_id in {m.get("id") for m in history}
        client.request("DELETE", "/api/session/{}/inbox/{}".format(
            quote(session_id, safe=""), quote(parked_id, safe="")))
        inbox2 = client.inbox(session_id)
        items2 = inbox2.get("data", []) if isinstance(inbox2, dict) else []
        self.step("f23_resume_false_inbox_anchor",
                  admitted_value.get("id") == parked_id and in_inbox
                  and not delivered
                  and parked_id not in {i.get("id") for i in items2
                                        if isinstance(i, dict)},
                  inbox_rows=1, delivered=delivered, cancelled=True,
                  note="F23 机制锚点活复锚（W1-U06 e07_live_recon 深证）："
                       "resume:false=持久入队不投递（session.ts:174）；显式"
                       "取消是唯一撤销通道")


def _pid_alive(pid: int) -> bool:
    proc = subprocess.run(["tasklist", "/FI", "PID eq {}".format(pid)],
                          capture_output=True, text=True, timeout=30)
    return str(pid) in proc.stdout


def _ollama_installed() -> bool:
    return shutil.which("ollama") is not None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"], default=None)
    parser.add_argument("--oc28", type=Path, default=DEFAULT_OC28)
    parser.add_argument("--bun", type=Path, default=DEFAULT_BUN)
    parser.add_argument("--keep", action="store_true",
                        help="保留临时根供取证")
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    if not args.oc28.is_dir():
        print(json.dumps({"status": "RECON_BLOCKED",
                          "reason": "oc28_missing:" + str(args.oc28)},
                         ensure_ascii=False))
        return 3
    bun = args.bun if args.bun.exists() else Path(shutil.which("bun") or "")
    if not bun.exists():
        print(json.dumps({"status": "RECON_BLOCKED", "reason": "bun_not_found"},
                         ensure_ascii=False))
        return 3

    failed_profiles = []
    for profile in profiles:
        print("=== profile {} ===".format(profile), flush=True)
        recon = Recon(args.oc28, profile, args.keep)
        try:
            code = recon.run(bun)
            status = "RECON_OK" if code == 0 else "RECON_FAIL"
        except AssertionError as exc:
            failed_profiles.append(profile)
            status = "RECON_FAIL:{}".format(exc)
        except SystemExit as exc:
            if exc.code == 3:
                # BLOCKED=机械边界（缺 bun/配置/模型边界）：如实退出码 3。
                return 3
            raise
        write_evidence(recon)
        print(json.dumps({"profile": profile, "status": status,
                          "checks": len(recon.checks)}, ensure_ascii=False),
              flush=True)
        if failed_profiles:
            print(json.dumps({"status": "RECON_FAIL",
                              "failed": failed_profiles}, ensure_ascii=False))
            return 1
    print(json.dumps({"status": "RECON_OK", "profiles": profiles},
                     ensure_ascii=False))
    return 0


def write_evidence(recon: Recon) -> None:
    stamp = recon.ts
    for unit in ("F22", "F23"):
        out_dir = REPO_ROOT / "evidence" / unit / recon.profile
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "f22f23-stream-disconnect-recon/1",
            "unit": unit, "profile": recon.profile, "run_stamp": stamp,
            "oc28": str(recon.oc28),
            "oc28_head": _git_head(recon.oc28),
            "dev_version": DEV_VERSION, "pin": "2.0.28",
            "topology": ("desktop: serve --service（注册文件）"
                         if recon.profile == "desktop"
                         else "selfhost: serve 前台（stdout URL＋env 密码）"),
            "checks": recon.checks,
            "mechanism_anchors": MECHANISM_ANCHORS,
        }
        (out_dir / ("f22f23-stream-disconnect-recon-{}.json".format(stamp))
         ).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                      encoding="utf-8")
        lines = ["# F22/F23 流式与断线停止语义 recon —— {} @ {}".format(
            recon.profile, stamp), ""]
        for check in recon.checks:
            facts = ", ".join("{}={!r}".format(k, v) for k, v in
                              check.items() if k not in ("check", "status"))
            lines.append("- **{} [{}]** {}".format(
                check["check"], check["status"],
                facts if len(facts) <= 700 else facts[:700] + "…"))
        (out_dir / ("f22f23-stream-disconnect-recon-{}.md".format(stamp))
         ).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": ["evidence/F22/{}".format(recon.profile),
                                   "evidence/F23/{}".format(recon.profile)]},
                     ensure_ascii=False), flush=True)


def _git_head(root: Path) -> str:
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30)
        return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


MECHANISM_ANCHORS = {
    "server_owned_run": "oc28 core/session/session.ts:174（resume 门）+:192（服务端拥有完成记录）",
    "live_streaming_face": "oc28 GET /api/event（protocol/groups/event.ts:44）活流：session.text.delta 真增量（publish-llm-event.ts deltaBatchInterval=100）",
    "durable_resync_face": "oc28 持久消息账 GET /api/session/:id/message?order=asc＋cursor.next 分页（SessionsCursor）；e07_live_recon 已证跨完整重启存活",
    "experimental_log_boundary": "oc28 cli/server-process.ts 不传 events.persist→core/bus.ts:203 persist=false→EventTable 不落盘（bus.ts:649）→experimental log 回放恒空（本单活证）；如实记边界不冒验",
    "volatile_event_stream_contrast": "oc28 protocol/groups/event.ts:51（/api/event 挥发契约，断连即漏——缺口只由持久消息账补齐）",
    "stop_independent_terminal": "oc28 core/session/execution.ts:50-54,119-147 + core/session/message-updater.ts:63-77,144-148（idle 三值终态 append）",
    "late_finish_no_override": "oc28 core/session/execution.ts:118（每忙碌期一次终态观察）+ publish-llm-event.ts:169-171（中断前已发布事件照常落账）",
    "no_new_step_after_stop": "oc28 schema/session-event.ts:326-340（session.step.started 持久事件，stop 后计零）",
    "crash_resume": "oc28 core/session/execution.ts:76-80 + execution/restart.ts:46-62 + server/src/fetch.ts:47,process.ts:241",
    "side_effect_reconcile": "oc28 execution/restart.ts:52-53（recovery is at-least-once…external side effects）",
    "inbox_id_idempotent": "oc28 core/session/inbox.ts:70-73（W1-U06 e07_live_recon 已活证，本单复锚）",
}


if __name__ == "__main__":
    raise SystemExit(main())
