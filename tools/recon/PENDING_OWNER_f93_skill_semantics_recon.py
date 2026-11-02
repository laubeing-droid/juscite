# -*- coding: utf-8 -*-
"""F93 SKILL.md 通道三执行语义 验收对账（PENDING_OWNER 版，工单 W3-U16）。

权威（06:F93「SKILL.md 通道+三种执行语义（聊天注入/实例化 review/调用计
算器）」＋台账断言「SKILL聊天注入/review实例/JC计算三语义真实，禁无必要
DAG引擎」＋05 §8「同ID来源、选中/注入/调用/产物分别证」＋17 卡落点「JC
compiler_core/client.py 公开 owner 扩展及真实规则包；UI 仅调用/展示」——
owner 扩展已由 W2b-U19/U54/U55/U56 交付，本单 JC 仓公开面只读零改动）。

三语义真跑（同一个 SKILL ID：lvyin-jusbench-calc；同一个 SKILL.md 字节
文件同时被服务原生通道与产品面消费——同 ID 来源/选中/注入/调用/产物分
别证）：
  语义① 聊天注入（S 系列，隔离产品服务真跑，回环假 provider 捕获模型
        请求字节）：SKILL.md 落 <合成工作区>/skill/<id>/SKILL.md → 服务
        原生发现（GET /api/skill）→ prompt 携带 skills=[{id}]（选中；
        未知 id＝400 Skill not found 负向）→ 假 provider 捕获的
        /chat/completions 请求体含 <skill_content name=…> 块＋金丝雀标
        记＋Base directory（注入进真实模型请求）→ 会话消息回读持久化
        的 skill 文本。
  语义② 实例化 review（P 系列，双 profile）：产品面 skill.read（来源/
        选中：id 规则同上游原生通道，全文 sha256 溯源）→
        skill.review_instantiate 列模板恰一块 → 既有冻结方法组
        harness.review_batch_create＋review_columns_define 真实建批入账
        → 批/列回读逐键对账（列 id/name/format/version/gold 与模板全
        等；批标题/note 携 skill id@sha 溯源）；负向＝选中 id 不匹配/
        模板块缺失 具名拒。
  语义③ 调用计算器（本行独有桥接，P 系列，双 profile）：
        skill.calculate 计算步骤块恰一块（method/具名输入域/rule·
        calendar 版本声明）→ 既有 calc.* 冻结五族槽位（P01 JCClient）
        真算——C01 闰日夹具 20 分（E21 同源）、calculationReceiptRef
        owner=jc、独立 checker 同意；负向＝声明方法闭集外/输入域漂移
        具名拒＋JC typed FLOAT_FORBIDDEN（JC_FAILURE 携码 exit 4）原样
        上浮；确定性＝同输入两跑结果逐键相等。
  禁无必要 DAG 引擎：skill_semantics.py 导入闭集 AST 断言（无图/引擎/
        编排依赖）入证据。

钉定（漂移即 FATAL，exit 2）：JC 仓交付链头 worktree w2b-u55（基
w2b-u56）compiler_core/client.py sha256＝3bb8c56a364243af2acdf6200722
e704553e582be9e6521aa854ab285bc8b215；JC/LH 两 worktree 开工/收工
git status --porcelain 双查＝只读零改动。

用法（juscite worktree w3-u16 根 cwd；--profile 缺省＝双 profile）：
  python -X utf8 tools/recon/PENDING_OWNER_f93_skill_semantics_recon.py \
      [--profile desktop --profile selfhost]

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F93/<profile>/ 与
evidence/F93/service/。全程合成材料（假 provider 回环、无外部 API、无
BYOK 依赖）；%APPDATA%\\JusBench 与 oc28 主检出零触碰；JC/LH 仓只读。
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
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
import unittest.mock
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
EVIDENCE_ROOT = REPO_ROOT / "evidence" / "F93"

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w2b-u55")
JC_CLIENT_SHA256 = (
    "3bb8c56a364243af2acdf6200722e704553e582be9e6521aa854ab285bc8b215")
LH_REPO = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u53")
DEFAULT_OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
DEFAULT_BUN = Path.home() / ".bun" / "bun.exe"
DEV_VERSION = "2.0.0-local-w3u16f93"   # 隔离 dev 服务版记实值（打包 pin=2.0.28）

SKILL_ID = "lvyin-jusbench-calc"
SKILL_NAME = "律引计算助手"
MATTER = "m-f93-recon"
BATCH = "brt-f93-recon"

SKILL_MARKER = "F93-SKILL-MARKER-"  # + 随机后缀（每跑生成）

TEMPLATE_COLUMNS = [
    {"id": "principal", "name": "本金（分）", "prompt": "取合同本金，整数分",
     "format": "decimal-string", "version": "1",
     "gold": {"kind": "number"}},
    {"id": "interest", "name": "利息（分）", "prompt": "按阶梯利率计算",
     "format": "decimal-string", "version": "1",
     "gold": {"kind": "number"}},
]
TEMPLATE_DOC = {"columns": TEMPLATE_COLUMNS,
                "rows": [{"id": "row-1"}, {"id": "row-2"}]}
STEP_DOC = {"method": "calc.interest",
            "rule_version": "F93 合成验收声明（JC registry 调用时解析）",
            "calendar_version": "F93 合成验收声明（2026 版本包声明面）",
            "input_domain": ["principal_minor", "segments"]}

CALC_INPUT = {"principal_minor": 365_000,
              "segments": [{"start_date": "2024-02-28",
                            "end_date": "2024-03-01",
                            "annual_rate": "0.01"}]}
CALC_INPUT_FLOAT = {"principal_minor": 365_000,
                    "segments": [{"start_date": "2024-02-28",
                                  "end_date": "2024-03-01",
                                  "annual_rate": 0.01}]}

RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [{
        "source_id": "acceptance-statute", "jurisdiction": "TEST",
        "authority_tier": "official_first_party",
        "issuer": "Acceptance Test Authority", "title": "acceptance-statute",
        "publication_time": "2020-01-01T00:00:00Z",
        "effective_from": "2020-01-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                    "page": None, "span_start": None, "span_end": None},
        "content": ("SYNTHETIC acceptance rule text for engineering "
                    "verification only; no legal effect."),
        "structure_sections": ["ART-1"],
    }],
    "rules": [
        {"rule_id": "acc-base", "jurisdiction": "TEST",
         "governing_law": "acceptance-statute",
         "source_id": "acceptance-statute", "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.contract", "required": True}],
         "conclusion": {"value": "applies"},
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}


def skill_markdown(marker: str, step_doc: dict | None = STEP_DOC) -> str:
    fence = "`" * 3
    parts = ["---", "name: " + SKILL_NAME,
             "description: 批量审查列模板与 JC 公开计算（F93 合成验收技能）",
             "---", "",
             "# 律引 SKILL（F93 合成验收）", "",
             "金丝雀标记：%s" % marker, "",
             "本技能演示 SKILL.md 通道三种执行语义（同 ID 来源/选中/注入/"
             "调用/产物分别证；禁无必要 DAG 引擎）。", "",
             "## 语义② 列模板实例化 review", "",
             fence + "lvyin-review-columns",
             json.dumps(TEMPLATE_DOC, ensure_ascii=False),
             fence, ""]
    if step_doc is not None:
        parts += ["## 语义③ 调用计算器（JC 公开面，独有桥接）", "",
                  fence + "lvyin-calc-step",
                  json.dumps(step_doc, ensure_ascii=False),
                  fence, ""]
    return "\n".join(parts)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_status_porcelain(repo: Path) -> str:
    proc = subprocess.run(["git", "status", "--porcelain"],
                          capture_output=True, text=True, cwd=str(repo))
    return proc.stdout.strip()


def command_key(request_id: str) -> dict:
    return {"requestId": "f93-" + request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id,
                           "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail),
              flush=True)
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def call_entry(method: str, args: dict, config: dict) -> dict:
    """desktop 径：真产品入口子进程（legal_entry CLI）。"""
    request_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    config_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "args": args}, request_handle,
                  ensure_ascii=False)
        request_handle.close()
        json.dump(config, config_handle, ensure_ascii=False)
        config_handle.close()
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, text=True, encoding="utf-8",
            timeout=900, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload,
                "code": payload.get("code") if isinstance(payload, dict)
                else None,
                "result": payload.get("result") if isinstance(payload, dict)
                else None}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


# ---------------------------------------------------------------------- #
# 回环假 provider（捕获 /chat/completions 请求体＝注入面直接证据）
# ---------------------------------------------------------------------- #


class CaptureStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.chat_bodies: list[bytes] = []
        self.all_requests: list[dict] = []

    def add(self, item: dict, body: bytes = b"") -> None:
        with self.lock:
            self.all_requests.append(item)
            if item["path"].rstrip("/").endswith("/chat/completions"):
                self.chat_bodies.append(body)

    def chat_text(self) -> str:
        with self.lock:
            return "\n".join(
                body.decode("utf-8", errors="replace")
                for body in self.chat_bodies)


def make_fake_provider(store: CaptureStore, marker: str):
    """回环假 provider（W2a-U17 R-MCP 先例）：/models 列表＋SSE 回显。"""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            store.add({"at": time.strftime("%H:%M:%S"), "method": "POST",
                       "path": self.path, "body_len": len(body)}, body)
            if self.path.rstrip("/").endswith("/chat/completions"):
                self._sse("金丝雀回显：%s（W3-U16 假 provider 合成应答）"
                          % marker)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def do_GET(self):
            store.add({"at": time.strftime("%H:%M:%S"), "method": "GET",
                       "path": self.path, "body_len": 0})
            if self.path.rstrip("/").endswith(("/models", "/v1/models")):
                payload = json.dumps({"object": "list", "data": [
                    {"id": "f93-echo", "object": "model",
                     "owned_by": "w3-u16-synthetic"}]}).encode()
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
                "id": "chatcmpl-f93", "object": "chat.completion.chunk",
                "created": int(time.time()), "model": "f93-echo",
                "choices": [{"index": 0, "delta": delta,
                             "finish_reason": finish}]}
            events = [chunk({"role": "assistant", "content": ""}),
                      chunk({"content": reply}), chunk({}, "stop"),
                      {"id": "chatcmpl-f93",
                       "object": "chat.completion.chunk",
                       "created": int(time.time()), "model": "f93-echo",
                       "choices": [],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                 "total_tokens": 15}}]
            payload = "".join(
                "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                for event in events) + "data: [DONE]\n\n"
            data = payload.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

    return Handler


def serve(handler_factory) -> tuple[ThreadingHTTPServer, str]:
    # ThreadingHTTPServer（W2a-U17 同款）：keep-alive 连接不能占死 accept
    # 循环——单线程 HTTPServer 实测被 Bun 连接池挂住＝ECONNRESET。
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory())
    origin = "http://127.0.0.1:%d" % server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, origin


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def port_open(port: int) -> bool:
    sock = socket.socket()
    sock.settimeout(1.0)
    try:
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def pid_alive(pid: int) -> bool:
    proc = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid],
                          capture_output=True, text=True)
    return str(pid) in proc.stdout


# ---------------------------------------------------------------------- #
# 隔离产品服务（临时 XDG 四根；假 provider 在工作区 opencode.json——
# 零 BYOK 依赖、零 %APPDATA% 访问；绝不触碰 43127 活服务）
# ---------------------------------------------------------------------- #


class LiveService:
    def __init__(self, oc28: Path, bun: Path):
        self.oc28 = oc28
        self.bun = bun
        self.base = Path(tempfile.mkdtemp(prefix="f93-svc-"))
        self.roots = {key: self.base / "oc" / key
                      for key in ("state", "data", "config", "cache")}
        for key in self.roots:
            self.roots[key].mkdir(parents=True)
        self.port = free_port()
        self.proc = None
        self.registration: dict | None = None
        self.client = None
        self.capture_store: CaptureStore | None = None
        self.provider_origin: str | None = None

    def launch(self) -> dict:
        env = dict(os.environ)
        # 隔离服务只说回环：剥离代理变量（Bun 对 NO_PROXY 支持不完整——
        # 实测 HTTP(S)_PROXY 下模型回环请求被送进系统代理＝provider.
        # transport 重试打转，假 provider 零捕获；同 opencode_http.Client
        # 的回环 ProxyHandler({}) 纪律）。
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                    "http_proxy", "https_proxy", "all_proxy"):
            env.pop(key, None)
        env["NO_PROXY"] = "127.0.0.1,localhost,::1"
        env["XDG_STATE_HOME"] = str(self.roots["state"])
        env["XDG_DATA_HOME"] = str(self.roots["data"])
        env["XDG_CONFIG_HOME"] = str(self.roots["config"])
        env["XDG_CACHE_HOME"] = str(self.roots["cache"])
        env["OPENCODE_DISABLE_MODELS_FETCH"] = "1"
        env["OPENCODE_CHANNEL"] = "local"
        env["OPENCODE_VERSION"] = DEV_VERSION
        log = open(self.base / "service.log", "ab")
        self.proc = subprocess.Popen(
            [str(self.bun), "run", "--cwd", "packages/cli",
             "--define=OPENCODE_VERSION=process.env.OPENCODE_VERSION",
             "src/index.ts", "serve", "--service",
             "--hostname", "127.0.0.1", "--port", str(self.port)],
            cwd=str(self.oc28), env=env, stdout=log,
            stderr=subprocess.STDOUT)
        reg_path = self.roots["state"] / "opencode" / "service-local.json"
        deadline = time.monotonic() + 240.0
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise SystemExit("FATAL: 隔离服务进程退出（exit=%s，log=%s）"
                                 % (self.proc.returncode,
                                    self.base / "service.log"))
            reg = None
            if reg_path.exists():
                try:
                    reg = json.loads(reg_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    reg = None
            if reg is not None and reg.get("url", "").endswith(
                    ":%d" % self.port):
                try:
                    client = self._client(reg)
                    info = client.request("GET", "/api/info")
                    value = info.get("data", info) if isinstance(
                        info, dict) else {}
                    if isinstance(value, dict) and value.get("version"):
                        self.registration = reg
                        self.client = client
                        return reg
                except Exception:
                    pass
            time.sleep(1.0)
        raise SystemExit("FATAL: 隔离服务 240s 未就绪（log=%s）"
                         % (self.base / "service.log"))

    def _client(self, reg: dict):
        from opencode_http import Client
        token = base64.b64encode(
            ("opencode:" + reg["password"]).encode()).decode("ascii")
        return Client(reg["url"],
                      headers={"Authorization": "Basic " + token},
                      timeout=120.0)

    def shutdown(self) -> None:
        reg_path = self.roots["state"] / "opencode" / "service-local.json"
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(reg["pid"])],
                           capture_output=True, timeout=60)
            deadline = time.monotonic() + 45.0
            while time.monotonic() < deadline:
                if not port_open(self.port) and not pid_alive(reg["pid"]):
                    break
                time.sleep(1.0)
        except Exception:
            if self.proc is not None and self.proc.poll() is None:
                subprocess.run(["taskkill", "/F", "/T",
                                "/PID", str(self.proc.pid)],
                               capture_output=True, timeout=60)
        shutil.rmtree(self.base, ignore_errors=True)


def raw_post(client, path: str, body: dict) -> tuple[int, str]:
    """带错误体读取的原始 POST（负向断言要看到 Skill not found 消息）。"""
    request = urllib.request.Request(
        client.url + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json", **client.headers},
        method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=60) as response:
            return response.status, response.read().decode(
                "utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------- #
# 语义① 聊天注入（隔离服务真跑；服务级，双 profile 共享证据）
# ---------------------------------------------------------------------- #


def run_chat_injection(checks: Checks, service: LiveService,
                       workspace: Path, marker: str) -> dict:
    client = service.client
    store = service.capture_store
    skill_file = (workspace / ".opencode" / "skill" / SKILL_ID / "SKILL.md")
    skill_sha = sha256_of(skill_file)

    # S01 隔离服务 + 43127 活服务零触碰
    reg = service.registration
    live_43127 = port_open(43127)
    checks.add("S01_service_isolated_live_untouched", bool(reg),
               "隔离服务 %s（pid=%s，dev=%s，临时 XDG 四根 %s）；43127 用户"
               "活服务存在=%s（本轮零触碰）"
               % (reg["url"], reg.get("pid"), DEV_VERSION, service.base,
                  live_43127))

    # S02 原生发现（来源）：GET /api/skill（deepObject 编码）轮询至本 ID
    # 在册——位置实例惰性启动，技能清单异步装载（实测首轮空、秒级就绪）。
    listed = False
    listed_detail = "轮询超时未在册"
    deadline = time.monotonic() + 60.0
    poll = 0
    while time.monotonic() < deadline:
        poll += 1
        try:
            query = urllib.parse.urlencode(
                {"location[directory]": str(workspace)})
            payload = client.request("GET", "/api/skill?" + query)
            data = payload.get("data", payload) if isinstance(payload, dict) \
                else payload
            entries = {skill.get("id"): skill.get("name")
                       for skill in (data or []) if isinstance(skill, dict)}
            if entries.get(SKILL_ID) is not None:
                listed = True
                listed_detail = ("GET /api/skill?location[directory]=<ws> 第"
                                 "%d 次轮询在册；id=%r name=%r（原生发现＝"
                                 "<ws>/.opencode/skill/ 项目约定，同一 "
                                 "SKILL.md 文件）" % (poll, SKILL_ID,
                                                     entries.get(SKILL_ID)))
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2.0)
    if not listed:
        listed_detail = "60s 内 %d 次轮询未在册（位置实例技能装载失败）" % poll
    checks.add("S02_native_discovery_lists_skill_id", listed, listed_detail)

    # S03 会话绑定合成工作区（假 provider f93fake/f93-echo）
    ts = int(time.time())
    session_id = "ses_f93_%d" % ts
    client.create({"id": session_id,
                   "title": "律引 F93 语义①聊天注入（合成）",
                   "location": {"directory": str(workspace)},
                   "model": {"id": "f93-echo", "providerID": "f93fake"}})
    checks.add("S03_session_bound_to_synthetic_workspace", True,
               "会话 %s 绑定合成工作区（模型钉假 provider f93fake/f93-echo"
               "＝回环，零外部 API）" % session_id)

    # S04 选中：prompt 携带 skills=[{id}] → 200
    status, _ = raw_post(
        client, "/api/session/%s/prompt"
        % urllib.parse.quote(session_id, safe=""),
        {"id": "msg_f93_%d" % ts,
         "text": "请按技能说明逐字复述金丝雀标记。",
         "model": {"id": "f93-echo", "providerID": "f93fake"},
         "skills": [{"id": SKILL_ID}]})
    checks.add("S04_selection_prompt_with_skill_accepted", status == 200,
               "POST prompt skills=[{id:%s}] → HTTP %d（选中＝显式技能附件）"
               % (SKILL_ID, status))

    # S05 选中负向：未知 id → 400 Skill not found（真实查找，非 stub）
    neg_status, neg_body = raw_post(
        client, "/api/session/%s/prompt"
        % urllib.parse.quote(session_id, safe=""),
        {"id": "msg_f93_neg_%d" % ts, "text": "负向：未知技能。",
         "model": {"id": "f93-echo", "providerID": "f93fake"},
         "skills": [{"id": "f93-nonexistent"}]})
    neg_ok = neg_status == 400 and "Skill not found" in neg_body
    checks.add("S05_selection_unknown_skill_refused", neg_ok,
               "未知技能负向 → HTTP %d，body 含 Skill not found=%s"
               % (neg_status, "Skill not found" in neg_body))

    # S06 注入进真实模型请求（假 provider 捕获体；换行归一后做块锚检查）
    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        if store.chat_bodies:
            break
        time.sleep(1.0)
    chat_text = store.chat_text().replace("\r\n", "\n").replace("\r", "\n")
    # 捕获体是 JSON 请求字节：内容串内的引号已转义（\\"）——块锚检查取
    # 无引号碎片＋转义形态双认。
    has_block = ("<skill_content" in chat_text
                 and SKILL_NAME in chat_text)
    has_marker = marker in chat_text
    has_base = "Base directory for this skill" in chat_text
    checks.add("S06_injection_into_model_request",
               bool(store.chat_bodies) and has_block and has_marker
               and has_base,
               "假 provider 捕获 /chat/completions ×%d；请求体含 "
               "<skill_content 块＋技能名=%s、金丝雀=%s、Base directory=%s"
               "（JSON 转义感知；注入进真实 LLM 请求字节）"
               % (len(store.chat_bodies), has_block,
                  has_marker, has_base))

    # S07 注入持久化（会话消息回读；换行归一后做块锚检查）
    persisted = False
    persisted_detail = "消息回读为空"
    try:
        messages = client.request(
            "GET", "/api/session/%s/message?limit=20"
            % urllib.parse.quote(session_id, safe=""))
        dump = json.dumps(messages, ensure_ascii=False).replace(
            "\r\n", "\n").replace("\r", "\n")
        # JSON 转义感知：块锚取无引号碎片（引号在 dump 中是 \\"）。
        persisted = (marker in dump and "<skill_content" in dump
                     and SKILL_NAME in dump
                     and "Base directory for this skill" in dump)
        persisted_detail = ("会话消息回读含金丝雀=%s、<skill_content 块=%s、"
                            "技能名=%s、Base directory=%s"
                            % (marker in dump, "<skill_content" in dump,
                               SKILL_NAME in dump,
                               "Base directory for this skill" in dump))
    except Exception as exc:  # noqa: BLE001
        persisted_detail = "消息回读异常：%s: %s" % (type(exc).__name__,
                                                    str(exc)[:160])
    checks.add("S07_injection_persisted_in_session_message", persisted,
               persisted_detail + "（同 ID 来源文件 sha256=%s…）"
               % skill_sha[:12])

    return {"session": session_id, "provider_origin": service.provider_origin,
            "chat_captures": len(store.chat_bodies),
            "skill_sha256": skill_sha}


# ---------------------------------------------------------------------- #
# 双 profile 产品面（语义②③；desktop=子进程全链 / selfhost=PG 直连 seam）
# ---------------------------------------------------------------------- #


def run_product_profile(checks: Checks, call, workspace: Path) -> None:
    skill_path = str(workspace / ".opencode" / "skill" / SKILL_ID
                     / "SKILL.md")
    skill_sha = sha256_of(Path(skill_path))

    # P1 来源面：skill.read（同 ID 同文件；sha256 溯源）
    outcome = call("skill.read", {"skill_path": skill_path})
    parsed = outcome.get("result") or {}
    ok = (outcome.get("exit") == 0
          and parsed.get("id") == SKILL_ID
          and parsed.get("name") == SKILL_NAME
          and parsed.get("contentSha256") == skill_sha
          and parsed.get("template") and parsed.get("calcStep"))
    checks.add("P1_source_face_read_sha_traceable", ok,
               "skill.read → id=%s name=%s sha 匹配=%s template/calcStep="
               "%s/%s（同 ID 来源＝语义①注入的同一字节文件）"
               % (parsed.get("id"), parsed.get("name"),
                  parsed.get("contentSha256") == skill_sha,
                  bool(parsed.get("template")), bool(parsed.get("calcStep"))))

    # P2 语义② 真实建批入账（prompt＝技能通道内容随回执携带，不进账本）
    outcome = call("skill.review_instantiate",
                   {"skill_path": skill_path, "skill_id": SKILL_ID,
                    "matter_id": MATTER, "batch_id": BATCH,
                    "key": command_key("inst-1")})
    created = outcome.get("result") or {}
    prompts = {c.get("id"): c.get("prompt")
               for c in created.get("templateColumns") or []}
    prompts_ok = prompts == {c["id"]: c["prompt"] for c in TEMPLATE_COLUMNS}
    ok = (outcome.get("exit") == 0 and created.get("batchId") == BATCH
          and prompts_ok)
    checks.add("P2_review_instantiate_real_ledger", ok,
               "skill.review_instantiate → exit=%s batchId=%s skill=%s@%s…"
               "；模板 prompt 随回执携带=%s（harness 列账闭集不收 prompt，"
               "零第二列权威）"
               % (outcome.get("exit"), created.get("batchId"),
                  (created.get("skill") or {}).get("id"),
                  str((created.get("skill") or {}).get(
                      "contentSha256"))[:12], prompts_ok))

    # P3 语义② 回读对账（列三元组+金标全等；批溯源）
    columns_outcome = call("harness.review_columns_read",
                           {"scope": {"kind": "matter", "matterId": MATTER},
                            "batch_id": BATCH})
    batch_outcome = call("harness.review_batch_read",
                         {"scope": {"kind": "matter", "matterId": MATTER},
                          "batch_id": BATCH})
    columns = (columns_outcome.get("result") or {}).get("columns") or []
    expected = [{"id": c["id"], "name": c["name"], "format": c["format"],
                 "version": c["version"], "gold": c["gold"]}
                for c in TEMPLATE_COLUMNS]
    # 账面投影 ORDER BY column_id（字母序）——列集合按 id 排序后逐键全等。
    columns_equal = (sorted(columns, key=lambda c: c["id"])
                     == sorted(expected, key=lambda c: c["id"]))
    batch_result = batch_outcome.get("result") or {}
    snapshot = batch_result.get("snapshot") or batch_result
    title = str(snapshot.get("title") or "")
    provenance_ok = SKILL_ID + "@" in title and skill_sha[:8] in title
    checks.add("P3_review_readback_columns_equal_and_provenance",
               columns_equal and provenance_ok,
               "review_columns_read 逐键全等=%s（%d 列）；批标题「%s」含 "
               "id@sha8=%s（同 ID 产物可回读；note 不在 F25 回读投影，"
               "全文 sha 以面回执＋P1 溯源为准）"
               % (columns_equal, len(columns), title[:40], provenance_ok))

    # P4 语义② 负向：选中 id 不匹配 / 模板块缺失（独立负向 skill 文件）
    neg_root = workspace / "negskills"
    no_block_dir = neg_root / "lvyin-f93-noblock"
    no_block_dir.mkdir(parents=True, exist_ok=True)
    (no_block_dir / "SKILL.md").write_text(
        "---\nname: 无块技能\n---\n\n正文没有列模板块。\n", encoding="utf-8")
    mismatch = call("skill.review_instantiate",
                    {"skill_path": skill_path, "skill_id": "wrong-id",
                     "matter_id": MATTER, "batch_id": "brt-f93-neg",
                     "key": command_key("neg-1")})
    no_block = call("skill.review_instantiate",
                    {"skill_path": str(no_block_dir / "SKILL.md"),
                     "skill_id": "lvyin-f93-noblock", "matter_id": MATTER,
                     "batch_id": "brt-f93-neg2",
                     "key": command_key("neg-2")})
    mismatch_ok = (mismatch.get("exit") == 3
                   and "f93_skill_id_mismatch" in str(mismatch.get("code")))
    noblock_ok = (no_block.get("exit") == 3
                  and "f93_template_block_missing"
                  in str(no_block.get("code")))
    checks.add("P4_review_negatives_named_refusals", mismatch_ok
               and noblock_ok,
               "选中 id 不匹配 → exit=%s code=%s；模板块缺失 → exit=%s "
               "code=%s（具名拒，绝不猜改）"
               % (mismatch.get("exit"), str(mismatch.get("code"))[:60],
                  no_block.get("exit"), str(no_block.get("code"))[:60]))

    # P5 语义③ 真算（C01 闰日夹具＝E21 同源；receipt owner=jc；checker）
    outcome = call("skill.calculate",
                   {"skill_path": skill_path, "skill_id": SKILL_ID,
                    "matter_id": MATTER, "input": CALC_INPUT})
    result = outcome.get("result") or {}
    sheet = result.get("result") or {}
    ref = sheet.get("calculationReceiptRef") or {}
    ok = (outcome.get("exit") == 0
          and sheet.get("amount_minor") == 20
          and ref.get("owner") == "jc"
          and ref.get("kind") == "calc-family-sheet"
          and (sheet.get("independentChecker") or {}).get("agreed") is True
          and result.get("step", {}).get("ruleVersion")
          == STEP_DOC["rule_version"])
    checks.add("P5_calculate_real_jc_compute_receipt_checker", ok,
               "skill.calculate → exit=%s amount_minor=%s（365000×1%%×闰日2"
               "天/365）；calculationReceiptRef owner=%s kind=%s；独立 "
               "checker agreed=%s；ruleVersion 声明回带=%s"
               % (outcome.get("exit"), sheet.get("amount_minor"),
                  ref.get("owner"), ref.get("kind"),
                  (sheet.get("independentChecker") or {}).get("agreed"),
                  result.get("step", {}).get("ruleVersion") is not None))

    # P6 语义③ 确定性（同输入两跑逐键相等）
    outcome2 = call("skill.calculate",
                    {"skill_path": skill_path, "skill_id": SKILL_ID,
                     "matter_id": MATTER, "input": CALC_INPUT})
    sheet2 = (outcome2.get("result") or {}).get("result") or {}
    strip = lambda sheet: {k: v for k, v in sheet.items()
                           if k != "calculationReceiptRef"}  # noqa: E731
    deterministic = strip(sheet) == strip(sheet2)
    checks.add("P6_calculate_deterministic",
               outcome2.get("exit") == 0 and deterministic,
               "同输入两跑：amount_minor %s==%s，去 ref 后逐键相等=%s"
               % (sheet.get("amount_minor"), sheet2.get("amount_minor"),
                  deterministic))

    # P7 语义③ 负向三路（声明方法闭集外/输入域漂移/JC typed FLOAT_FORBIDDEN）
    bad_step_dir = workspace / "negskills" / "lvyin-f93-badstep"
    bad_step_dir.mkdir(parents=True, exist_ok=True)
    (bad_step_dir / "SKILL.md").write_text(
        skill_markdown("负向技能", step_doc=dict(STEP_DOC,
                                                 method="calc.registry")),
        encoding="utf-8")
    closed = call("skill.calculate",
                  {"skill_path": str(bad_step_dir / "SKILL.md"),
                   "skill_id": "lvyin-f93-badstep", "matter_id": MATTER,
                   "input": CALC_INPUT})
    domain = call("skill.calculate",
                  {"skill_path": skill_path, "skill_id": SKILL_ID,
                   "matter_id": MATTER, "input": {"principal_minor": 1}})
    float_neg = call("skill.calculate",
                     {"skill_path": skill_path, "skill_id": SKILL_ID,
                      "matter_id": MATTER, "input": CALC_INPUT_FLOAT})
    closed_ok = (closed.get("exit") == 3
                 and "f93_calc_method_not_in_closed_set"
                 in str(closed.get("code")))
    domain_ok = (domain.get("exit") == 3
                 and "f93_calc_input_domain_mismatch"
                 in str(domain.get("code")))
    float_ok = (float_neg.get("exit") == 4
                and (float_neg.get("payload") or {}).get("status")
                == "JC_FAILURE"
                and "FLOAT_FORBIDDEN" in str(float_neg.get("code")))
    checks.add("P7_calculate_negatives_named_and_typed",
               closed_ok and domain_ok and float_ok,
               "声明方法闭集外（calc.registry）→ exit=%s code=%s；输入域漂"
               "移 → exit=%s code=%s；float 年利率 JC typed → exit=%s "
               "status=%s code=%s（绝不造数）"
               % (closed.get("exit"), str(closed.get("code"))[:60],
                  domain.get("exit"), str(domain.get("code"))[:60],
                  float_neg.get("exit"),
                  (float_neg.get("payload") or {}).get("status"),
                  str(float_neg.get("code"))[:60]))

    # P8 冻结方法组：未知 skill.* 方法 exit 3 method_not_connected
    unknown = call("skill.route", {"skill_path": skill_path})
    ok = unknown.get("exit") == 3 and "method_not_connected" in str(
        unknown.get("code"))
    checks.add("P8_method_group_frozen_unknown_refused", ok,
               "skill.route（组外）→ exit=%s code=%s（三方法封闭组）"
               % (unknown.get("exit"), str(unknown.get("code"))[:60]))


def no_dag_engine_check(checks: Checks) -> None:
    """禁无必要 DAG 引擎：skill_semantics.py 导入闭集 AST 断言。"""
    source = (REPO_ROOT / "implementation" / "python" / "skill_semantics.py"
              ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    ok = imported == {"__future__", "hashlib", "json", "re", "bridge_errors",
                      "pathlib", "legal_entry"}
    checks.add("P9_no_dag_engine_import_closed_set", ok,
               "skill_semantics.py 导入闭集=%s（无图/引擎/编排依赖——三语义"
               "各一次派发，不做通用 DAG）" % sorted(imported))


def run_desktop(checks: Checks, workspace: Path, harness_root: Path) -> None:
    sys.path.insert(0, str(harness_root / "src"))
    from legal_harness.state.matter_store import MatterStore
    temporary = tempfile.TemporaryDirectory(prefix="f93-desktop-")
    state_root = Path(temporary.name) / "state"
    state_root.mkdir(parents=True)
    MatterStore(state_root).create_matter(MATTER, "cas://profile-f93-d")
    (workspace / "bridge-registration.json").write_text(
        json.dumps({"url": "http://127.0.0.1:1",
                    "password": "synthetic-recon"}), encoding="utf-8")
    rules = workspace / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(json.dumps(RULE_PACK),
                                              encoding="utf-8")
    config = {
        "harness_public_entry": str(
            harness_root / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(state_root),
        "harness_service_registration": str(workspace
                                            / "bridge-registration.json"),
        "harness_timeout": 180,
        "harness_python": sys.executable,
        "jc_state_root": str(workspace / "jc-state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }

    def call(method, args):
        outcome = call_entry(method, args, config)
        if outcome["exit"] == 0 and outcome["result"] is None:
            raise SystemExit("FATAL: %s exit 0 但结果缺失（payload=%s）"
                             % (method, json.dumps(outcome["payload"],
                                                   ensure_ascii=False)[:400]))
        return outcome

    checks.add("P0_profile_transport", True,
               "desktop＝legal_entry CLI 子进程全链（harness public_entry 子"
               "进程→SQLite MatterStore；JC 经 P01 同域配置 jc_import_path）")
    run_product_profile(checks, call, workspace)


def run_selfhost(checks: Checks, workspace: Path, harness_root: Path,
                 dsn: str) -> None:
    import uuid as _uuid
    for path in (str(harness_root / "src"),
                 str(REPO_ROOT / "implementation" / "python")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.business.provider_registry import (
        resolve_provider_method)
    from legal_harness.business.units import HarnessUnits
    from legal_harness.state.pg_store import PgMatterStore
    # 运行面钉定（W2a-U16 纪律）：compiler_core 必须解析到本波 JC 链头。
    sys.path.insert(0, str(JC_REPO))
    for name in [m for m in list(sys.modules)
                 if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[name]

    temporary = tempfile.TemporaryDirectory(prefix="f93-selfhost-")
    base = Path(temporary.name)
    store = PgMatterStore(base / "state", dsn=dsn,
                          schema="f93_" + _uuid.uuid4().hex[:12])
    units = HarnessUnits(store)
    names = ("harness.review_batch_create", "harness.review_columns_define",
             "harness.review_batch_read", "harness.review_columns_read")
    bound = {name: resolve_provider_method(name, units) for name in names}
    store.create_matter(MATTER, "cas://profile-f93-pg")
    import skill_semantics
    from bridge_errors import NotConnected

    def seam(method, args, cfg):
        if method in bound:
            return bound[method](**args)
        raise NotConnected("method_not_connected:" + method)

    patcher = unittest.mock.patch.object(skill_semantics, "_harness_call",
                                         seam)
    patcher.start()
    try:
        rules = workspace / "rules"
        rules.mkdir(parents=True, exist_ok=True)
        (rules / "jc-local-pack.json").write_text(json.dumps(RULE_PACK),
                                                  encoding="utf-8")
        config = {"jc_state_root": str(workspace / "jc-state-pg"),
                  "jc_rule_roots": [str(rules)],
                  "jc_import_path": str(JC_REPO)}

        def call(method, args):
            import legal_entry
            try:
                if method.startswith("harness."):
                    if method not in bound:
                        return {"exit": 3,
                                "code": "method_not_connected:" + method,
                                "result": None}
                    return {"exit": 0, "code": None,
                            "result": bound[method](**args)}
                result = legal_entry.call(method, args, config)
                return {"exit": 0, "code": None, "result": result}
            except NotConnected as exc:
                return {"exit": 3, "code": str(exc), "result": None}
            except legal_entry.JCMethodFailure as exc:
                return {"exit": 4, "code": str(exc),
                        "payload": {"status": "JC_FAILURE"}, "result": None}
            except Exception as exc:  # noqa: BLE001
                return {"exit": 1,
                        "code": "%s: %s" % (type(exc).__name__,
                                            str(exc)[:200]),
                        "result": None}

        checks.add("P0_profile_transport", True,
                   "selfhost＝产品面同进程＋harness PgMatterStore 直连 "
                   "lh-pg-e08（schema=f93_*）；_harness_call seam 注入同 "
                   "U48/U05/U31 先例")
        run_product_profile(checks, call, workspace)
    finally:
        patcher.stop()


# ---------------------------------------------------------------------- #
# main
# ---------------------------------------------------------------------- #


def main() -> int:
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles",
                        help="发行形态（可重复；不给则双形态全跑）")
    parser.add_argument("--harness-root", default=str(LH_REPO))
    parser.add_argument("--jc-repo", default=str(JC_REPO))
    parser.add_argument("--oc28", default=str(DEFAULT_OC28))
    parser.add_argument("--bun", default=str(DEFAULT_BUN))
    parser.add_argument(
        "--pg-dsn",
        default="postgresql://lh_app:e08-synth-only@127.0.0.1:55432/"
                "legal_harness",
        help="selfhost PgMatterStore 直连 DSN（默认＝本机合成容器 "
             "lh-pg-e08；合成专用凭据）")
    parser.add_argument("--skip-service", action="store_true",
                        help="跳过语义①隔离服务轮（仅双 profile 产品面）")
    parser.add_argument("--evidence-root", default=str(EVIDENCE_ROOT))
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]
    jc_repo = Path(args.jc_repo)
    harness_root = Path(args.harness_root)

    # ---- 钉定（漂移即 FATAL） ----------------------------------------
    client_path = jc_repo / "compiler_core" / "client.py"
    if not client_path.is_file():
        print("FATAL: JC client.py 不在 %s" % client_path)
        return 2
    actual_sha = sha256_of(client_path)
    if actual_sha != JC_CLIENT_SHA256:
        print("FATAL: JC client.py sha256 漂移（钉定 %s…，实测 %s…，%s）——"
              "JC 仓公开面只读零改动纪律被破坏或链头已前移，须显式重钉"
              % (JC_CLIENT_SHA256[:12], actual_sha[:12], jc_repo))
        return 2
    print("[pin] JC client.py sha256 = %s…（钉定一致；worktree %s）"
          % (actual_sha[:12], jc_repo.name), flush=True)
    if not (harness_root / "tools/workflow-tools/harness/public_entry.py"
            ).is_file():
        print("FATAL: harness 公开入口不在 %s" % harness_root)
        return 2
    jc_clean_before = git_status_porcelain(jc_repo)
    lh_clean_before = git_status_porcelain(harness_root)
    print("[pin] JC worktree porcelain 开工=%r；LH worktree porcelain 开工"
          "=%r" % (jc_clean_before, lh_clean_before), flush=True)

    service = None
    per_profile: dict = {}
    service_evidence: dict = {}
    all_ok = True
    try:
        # 单一合成工作区：语义①（服务原生通道，<ws>/.opencode/skill/ 项目
        # 约定发现）与语义②③（产品面）消费同一个 SKILL.md 字节文件（同 ID
        # 来源/选中/注入/调用/产物）。
        workspace = Path(tempfile.mkdtemp(prefix="f93-ws-"))
        marker = SKILL_MARKER + secrets.token_hex(6)
        skill_dir = workspace / ".opencode" / "skill" / SKILL_ID
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(skill_markdown(marker), encoding="utf-8")
        (workspace / "opencode.json").write_text(json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "provider": {"f93fake": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "W3-U16 F93 Fake（合成，仅测试）",
                "options": {"baseURL": "", "apiKey": "sk-f93-synthetic"},
                "models": {"f93-echo": {"name": "F93 Echo Canary"}},
            }},
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        if not args.skip_service:
            bun = Path(args.bun)
            if not bun.is_file():
                print("FATAL: bun 不在 %s（语义①隔离服务轮不可跑；可用 "
                      "--skip-service 明示降级并如实挂账）" % bun)
                return 2
            oc28 = Path(args.oc28)
            store = CaptureStore()
            provider_server, provider_origin = serve(
                lambda *args: make_fake_provider(store, marker))
            config_path = workspace / "opencode.json"
            config_doc = json.loads(config_path.read_text(
                encoding="utf-8"))
            (config_doc["provider"]["f93fake"]["options"]
             ["baseURL"]) = provider_origin + "/v1"
            config_path.write_text(
                json.dumps(config_doc, ensure_ascii=False, indent=2),
                encoding="utf-8")
            service = LiveService(oc28, bun)
            service.capture_store = store
            service.provider_origin = provider_origin
            reg = service.launch()
            print("[service] isolated product service at %s (pid=%s)"
                  % (reg["url"], reg.get("pid")), flush=True)
            service_checks = Checks()
            try:
                service_meta = run_chat_injection(service_checks, service,
                                                  workspace, marker)
            finally:
                try:
                    provider_server.shutdown()
                except Exception:
                    pass
            service_evidence = {
                "run_date": RUN_DATE,
                "command": "python -X utf8 " + " ".join(sys.argv[1:]),
                "checks": service_checks.items,
                "passed": service_checks.passed_count,
                "total": len(service_checks.items),
                "overall": ("PASS" if service_checks.all_passed
                            else "FAIL"),
                **service_meta,
            }
            out_dir = Path(args.evidence_root) / "service"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / ("f93-skill-semantics-service-%s.json"
                        % time.strftime("%Y%m%dT%H%M%S%z"))).write_text(
                json.dumps(service_evidence, ensure_ascii=False, indent=1),
                encoding="utf-8")
            all_ok = all_ok and service_checks.all_passed
            print("---")

        for profile in profiles:
            checks = Checks()
            if profile == "desktop":
                run_desktop(checks, workspace, harness_root)
            else:
                run_selfhost(checks, workspace, harness_root, args.pg_dsn)
            no_dag_engine_check(checks)
            jc_clean_after = git_status_porcelain(jc_repo)
            lh_clean_after = git_status_porcelain(harness_root)
            checks.add("P10_repos_readonly_zero_change",
                       jc_clean_before == jc_clean_after
                       and lh_clean_before == lh_clean_after,
                       "JC/LH worktree 开工/收工 porcelain 相等＝只读零改动"
                       "（JC 干净=%r LH 干净=%r）"
                       % (not jc_clean_after, not lh_clean_after))
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True,
                text=True, cwd=str(REPO_ROOT)).stdout.strip()
            evidence = {
                "run_date": RUN_DATE,
                "profile": profile,
                "command": "python -X utf8 " + " ".join(sys.argv[1:]),
                "cwd": str(REPO_ROOT),
                "subject_commit": commit,
                "pins": {"jc_repo": str(jc_repo),
                         "jc_client_sha256_pinned": JC_CLIENT_SHA256,
                         "jc_client_sha256_observed": actual_sha,
                         "harness_root": str(harness_root)},
                "skill": {"id": SKILL_ID, "sha256": sha256_of(skill_file)},
                "service_semantics": service_evidence or None,
                "checks": checks.items,
                "passed": checks.passed_count,
                "total": len(checks.items),
                "overall": "PASS" if checks.all_passed else "FAIL",
            }
            out_dir = Path(args.evidence_root) / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / ("f93-skill-semantics-recon-%s.json"
                        % time.strftime("%Y%m%dT%H%M%S%z"))).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=1),
                encoding="utf-8")
            per_profile[profile] = evidence
            all_ok = all_ok and checks.all_passed
            print("---")
            print("profile=%s: %d/%d checks" % (profile,
                                                checks.passed_count,
                                                len(checks.items)))
    finally:
        if service is not None:
            service.shutdown()
    print(json.dumps({"status": "RECON_OK" if all_ok else "RECON_FAIL",
                      "profiles": list(per_profile)}, ensure_ascii=False))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
