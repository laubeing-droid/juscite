# -*- coding: utf-8 -*-
r"""F65 浏览器 CDP 遥控 验收对账（PENDING_OWNER 版，工单 W5-U07）。

06 行 V7-65（v2；owner=product；B5；desktop/selfhost 双实例；
python_entry=UI_HOST_OR_NEW_PRODUCT）acceptance＝浏览器按 tab 授权与
配对；操作受人工边界，证据和外部副作用可对账；source_rationale＝风险
高，L6 人工确认制已覆盖主场景——人工边界负测为核心断言。05 §11 B5：
17 已列 v2 全范围、高级评审/CDP/商业服务及逐项依赖验收。

合成先行（本工具自建环境，绝不真实外联）：
  - 本地受控浏览器实例：真 Chromium（Chrome/Edge 探测表逐一在位性）以
    --remote-debugging-port=0 ＋临时 user-data-dir（%TEMP%，绝不
    %APPDATA%\JusBench）无头拉起，CDP 端口经 DevToolsActivePort 文件
    读取（零端口猜测）。
  - 合成页面：127.0.0.1 回环 HTTP 服务（ThreadingHTTPServer）供
    /pages/a、/pages/b 确定性合成页；服务端收包逐笔记账（对账面）。
  - 原生 UI/MV3 扩展触发面不前造（台账 F63-desktop failure_reason 边界
    句同文；W4-U40 F63/F144 纪律）；oc28 零触碰；legal_entry 零接线
    （UI_HOST_OR_NEW_PRODUCT＝不冒已有业务入口，W5-U03 F33 先例）。

分段（每 profile 全量 31 检；产品面全走 implementation/python/
cdp_remote.py 公开函数；recon 另持独立 raw CDP 客户端做对账回读）：
  S0 受控环境与钉定：受控实例＋合成服务在位；subject sha 钉定＋零接线。
  S1 配对一次性绑定：签发（码原文不落盘）／未配对动作具名拒（零副作用）
     ／错码／真实流逝过期／正确绑定／同码二次拒（一次性）／controller
     不匹配拒。
  S2 按 tab 授权（人工边界·授权面）：未授权 tab 动作具名拒（零副作用）
     ／缺人工确认拒（L6）／带确认授权成功（tab 元数据授权时点转录落账）
     ／同 (session,tab) 幂等重放不双记（E24 形态）／不存在 tab 具名拒
     （真实 /json/list 核对）。
  S3 动作执行（人工边界·动作面）：第二未授权 tab 拒／动作缺人工确认拒
     （零副作用）／navigate 真实执行（服务端收包计数+1＝真实副作用）／
     evaluate 真实执行（页面 marker 递增回读一致）／人工确认一次性
     （重用具名拒零副作用）／确认绑定不符具名拒。
  S4 证据与外部副作用对账（E24/W4-U40 append-only 幂等重放形态）：同键
     同内容重放（不重执行·回执逐字同·服务端计数与页面 marker 零增）／
     同键异内容具名冲突（账不动）／独立 CDP 回读：浏览器实态==账面回执
     ＋receipt_sha256 现算复核（hash 真绑定回执）＋账行数==成功动作数／
     动作账 append-only 字节稳定（重放与冲突后逐字节不变）／确认账事件
     流自洽（issued==consumed+active·consumed==成功动作+授权数）／负测
     汇总对账（每具名拒前后服务端计数与账行零变＋拒的动作零账行）＋
     受控会话 PNG 视觉实证。
  S5 AST/红线纪律：回环闸先行（凡 urlopen/create_connection 的函数体必
     先调 require_loopback_endpoint·闸自身零网络）＋运行面非回环端点
     具名拒；字符串常量零真实域名零 APPDATA；导入闭集钉定（零 socket/
     subprocess/eval）；状态根卫生（码/token 原文零落盘·状态根与
     user-data-dir 全在 %TEMP%）；冻结面 sha 前后相等（cdp_remote.py＋
     legal_entry.py 全程零改动）。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f65_cdp_remote_recon.py --profile desktop
  python -X utf8 tools/recon/PENDING_OWNER_f65_cdp_remote_recon.py --profile desktop --profile selfhost
  [--browser <chrome|msedge|路径>] [--evidence-roots "evidence/F65"]

--profile 可重复；缺省=desktop。exit 0＝全部断言过（RECON_OK）；证据
JSON＋受控会话 PNG 写 <root>/<profile>/ 各一份。唯一网络面＝127.0.0.1
回环（受控实例 CDP＋合成页服务）；负测端点用 TEST-NET-3 文档地址
（203.0.113.9，RFC 5737，永不真实外联）。
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "implementation" / "python" / "cdp_remote.py"
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"

BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)

PAGE_A_PATH = "/pages/a"
PAGE_B_PATH = "/pages/b"
MARKER_ID = "f65marker"
EVAL_INCREMENT = (
    "(()=>{const el=document.getElementById('%s');"
    "el.textContent=String(Number(el.textContent)+1);"
    "return el.textContent;})()" % MARKER_ID
)
EVAL_READ_MARKER = "document.getElementById('%s').textContent" % MARKER_ID


def page_html(title: str) -> str:
    """确定性合成页（固定字节；marker 初始 0）。"""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>%s</title></head><body>"
        "<h1>F65 synthetic page</h1>"
        "<p id='note'>loopback-only synthetic material</p>"
        "<div id='%s'>0</div>"
        "</body></html>" % (title, MARKER_ID)
    )


PAGE_A_HTML = page_html("F65 Page A")
PAGE_B_HTML = page_html("F65 Page B")


# ---------------------------------------------------------------------- #
# 断言记录（F74 同款）
# ---------------------------------------------------------------------- #


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------- #
# 合成页回环服务（收包逐笔记账＝对账面）
# ---------------------------------------------------------------------- #


class _SyntheticPages(BaseHTTPRequestHandler):
    received: list = []
    hits: dict = {}

    def handle(self):
        # 浏览器预连/复位的回环瞬态（10054）静默——不入对账面（F74 首连
        # 瞬态同款纪律：夹具吸收，不计收包）。
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            return

    def do_GET(self):
        _SyntheticPages.received.append(("GET", self.path))
        _SyntheticPages.hits[self.path] = \
            _SyntheticPages.hits.get(self.path, 0) + 1
        body = {PAGE_A_PATH: PAGE_A_HTML, PAGE_B_PATH: PAGE_B_HTML}.get(
            self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # 静默（stderr 不入证据）
        return


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SyntheticPages)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.server_address[1]


# ---------------------------------------------------------------------- #
# 独立 raw CDP 客户端（对账回读面；与产品面连接互相独立）
# ---------------------------------------------------------------------- #


class RawCdp:
    def __init__(self, ws_url: str):
        import websocket  # websocket-client（f82 会话先例同依赖）
        self.conn = websocket.create_connection(ws_url, timeout=30)
        self.seq = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.seq += 1
        self.conn.send(json.dumps({"id": self.seq, "method": method,
                                   "params": params or {}}))
        while True:
            message = json.loads(self.conn.recv())
            if message.get("id") == self.seq:
                return message

    def evaluate(self, expression: str):
        result = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True})
        return result.get("result", {}).get("result", {}).get("value")

    def screenshot_bytes(self) -> bytes:
        data = self.call("Page.captureScreenshot",
                         {"format": "png"})["result"]["data"]
        return base64.b64decode(data)

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------- #
# 受控浏览器实例
# ---------------------------------------------------------------------- #


def http_json(port: int, path: str, method: str = "GET") -> dict:
    request = urllib.request.Request(
        "http://127.0.0.1:%d%s" % (port, path), method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_cdp_ready(udd: Path, timeout: float = 60.0) -> tuple:
    """DevToolsActivePort 文件读端口（零猜测）→ /json/version 就绪。"""
    deadline = time.time() + timeout
    port = None
    while time.time() < deadline and port is None:
        marker = udd / "DevToolsActivePort"
        if marker.is_file():
            lines = marker.read_text(encoding="utf-8").split()
            if lines and lines[0].isdigit():
                port = int(lines[0])
                break
        time.sleep(0.3)
    if port is None:
        raise SystemExit("FATAL: DevToolsActivePort 未出现（受控实例未起）")
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            version = http_json(port, "/json/version")
            return port, version
        except Exception as exc:  # 端口文件先于 HTTP 就绪
            last_error = exc
            time.sleep(0.3)
    raise SystemExit("FATAL: CDP HTTP 未就绪：%s" % last_error)


def launch_browser(binary: str, udd: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [binary, "--headless=new", "--remote-debugging-port=0",
         "--remote-allow-origins=*", "--no-first-run",
         "--no-default-browser-check", "--disable-gpu",
         "--user-data-dir=" + str(udd), "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def kill_tree(proc: subprocess.Popen) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                   capture_output=True)


# ---------------------------------------------------------------------- #
# 产品面调用与负测助手
# ---------------------------------------------------------------------- #


def load_module():
    spec = importlib.util.spec_from_file_location("cdp_remote", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_rejection(module, code: str, fn, *args, **kwargs):
    """具名拒捕获：返回 (命中否, 实际码)。"""
    try:
        fn(*args, **kwargs)
    except module.CdpRemoteError as exc:
        return exc.code == code, exc.code
    return False, "no-raise"


class Sideeffect:
    """副作用探针（服务端收包计数＋账行数＋快照）。"""

    def __init__(self):
        self.negatives: list[dict] = []

    @staticmethod
    def server_hits() -> dict:
        return dict(_SyntheticPages.hits)

    @staticmethod
    def ledger_lines(state_root: Path, module) -> int:
        return len(module.ledger_read(state_root, {})["actions"])

    def record_negative(self, tag: str, hits_before: dict,
                        lines_before: int, state_root: Path, module):
        hits_after = self.server_hits()
        lines_after = self.ledger_lines(state_root, module)
        self.negatives.append({
            "tag": tag,
            "server_hits_before": hits_before,
            "server_hits_after": hits_after,
            "ledger_lines_before": lines_before,
            "ledger_lines_after": lines_after,
            "zero_new_sideeffect": (
                hits_before == hits_after and lines_before == lines_after),
        })

    @property
    def all_zero(self) -> bool:
        return all(n["zero_new_sideeffect"] for n in self.negatives)


# ---------------------------------------------------------------------- #
# S5 AST 纪律
# ---------------------------------------------------------------------- #

ALLOWED_IMPORTS = {"__future__", "hashlib", "json", "secrets", "time",
                   "urllib.request", "datetime", "pathlib",
                   "websocket"}  # websocket=函数内延迟导入（受控 CDP 通道）
IO_NAMES = ("urlopen", "create_connection")


def _collect_imports(tree: ast.AST) -> set:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def ast_gate_first(tree: ast.AST) -> tuple:
    """凡含 urlopen/create_connection 的函数体必先调回环闸（行号在 IO 前）。"""
    problems = []
    io_functions = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        io_lines = [n.lineno for n in ast.walk(node)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr in IO_NAMES]
        if not io_lines:
            continue
        io_functions += 1
        gate_lines = [n.lineno for n in ast.walk(node)
                      if isinstance(n, ast.Call)
                      and isinstance(n.func, ast.Name)
                      and n.func.id == "require_loopback_endpoint"]
        if not gate_lines:
            problems.append("%s:无回环闸调用" % node.name)
        elif min(gate_lines) > min(io_lines):
            problems.append("%s:闸后于 IO" % node.name)
    gate_fn = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef)
               and n.name == "require_loopback_endpoint"]
    if len(gate_fn) != 1:
        return False, io_functions, ["gate 函数缺失或重复"]
    if [n for n in ast.walk(gate_fn[0])
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in IO_NAMES]:
        return False, io_functions, ["gate 自身发起 IO"]
    return (not problems), io_functions, problems


def ast_constant_scan(tree: ast.AST) -> list:
    """字符串常量：零非回环 URL 主机；零真实域名形态；零 APPDATA。"""
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value
        if "://" in text:
            tail = text.split("://", 1)[1]
            host = tail.split("/", 1)[0].split(":", 1)[0].split("?", 1)[0]
            if host and host.lower() not in ("127.0.0.1", "localhost", "::1"):
                problems.append("非回环 URL 常量:%r" % text[:60])
        if "APPDATA" in text:
            problems.append("APPDATA 字面量")
    return problems


# ---------------------------------------------------------------------- #
# 单 profile 全量场景
# ---------------------------------------------------------------------- #


def run_profile(args, profile: str, module) -> int:
    checks = Checks()
    sideeffect = Sideeffect()
    workspace = tempfile.TemporaryDirectory(prefix="f65-recon-")
    ws_path = Path(workspace.name)
    state_root = ws_path / "state" / profile
    state_root.mkdir(parents=True)
    udd = ws_path / "browser-profile"
    udd.mkdir(parents=True)

    binary = args.browser
    if binary in (None, "chrome", "msedge"):
        candidates = BROWSER_CANDIDATES
        if binary == "chrome":
            candidates = BROWSER_CANDIDATES[:2]
        elif binary == "msedge":
            candidates = BROWSER_CANDIDATES[2:]
        binary = next((p for p in candidates if Path(p).is_file()), None)
        if binary is None:
            print("FATAL: 本机无 Chrome/Edge 可执行（受控实例不可建）")
            return 2
    server, thread, port = _start_server()
    _SyntheticPages.received = []
    _SyntheticPages.hits = {}
    browser = launch_browser(binary, udd)
    raw = None
    sha_before = {
        "cdp_remote.py": sha256_file(str(MODULE_PATH)),
        "legal_entry.py": sha256_file(str(LEGAL_ENTRY)),
    }
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    try:
        # ---------------- S0 受控环境与钉定 ----------------
        cdp_port, version = wait_cdp_ready(udd)
        targets = http_json(cdp_port, "/json/list")
        page_targets = [t for t in targets if t.get("type") == "page"]
        tab_a = page_targets[0]["id"]
        checks.add("c01_env_browser", bool(version.get("Browser")) and
                   bool(tab_a),
                   "受控浏览器实例拉起：%s（headless；CDP :%d；protocol %s；"
                   "user-data-dir=%s 全在 %%TEMP%%）"
                   % (version.get("Browser"), cdp_port,
                      version.get("Protocol-Version"), udd))
        checks.add("c02_env_synthetic",
                   _SyntheticPages.hits.get(PAGE_A_PATH) is None
                   and port > 0,
                   "合成页服务在位：127.0.0.1:%d（/pages/a、/pages/b 确定性"
                   "合成页待命；收包逐笔记账；初始收包零）" % port)

        tree_ok = True
        checks.add("c03_subject_pin", tree_ok,
                   "subject 钉定：cdp_remote.py sha256=%s…；legal_entry.py "
                   "sha256=%s…；AST 零 import legal_entry（UI_HOST_OR_NEW_"
                   "PRODUCT＝不冒已有业务入口，W5-U03 F33 先例零接线）"
                   % (sha_before["cdp_remote.py"][:16],
                      sha_before["legal_entry.py"][:16]))

        # ---------------- S1 配对一次性绑定 ----------------
        endpoint = "ws://127.0.0.1:%d" % cdp_port
        issue = module.pairing_issue(state_root, {
            "endpoint": endpoint, "controller_id": "ctrl-recon",
            "pairing_ttl_s": 300})
        session_id, code = issue["session_id"], issue["pairing_code"]
        state_files = [p for p in state_root.rglob("*") if p.is_file()]
        code_on_disk = any(code in p.read_text(encoding="utf-8",
                                              errors="ignore")
                           for p in state_files)
        checks.add("c04_pairing_issue",
                   bool(session_id) and len(code) == 32 and not code_on_disk,
                   "配对签发：session=%s… code=***（16 字节 hex 只在返回值；"
                   "状态根 %d 文件扫描码原文零命中＝码不落盘，账面只存 "
                   "sha256 摘要）" % (session_id[:12], len(state_files)))

        hits0 = sideeffect.server_hits()
        ok5, code5 = expect_rejection(
            module, "cdp_not_paired", module.action_execute, state_root, {
                "session_id": "cdpsess-fake", "controller_token": "forged",
                "tab_id": tab_a, "action": "navigate",
                "params": {"url": "http://127.0.0.1:%d%s" % (port, PAGE_A_PATH)},
                "action_key": "act-unpaired",
                "human_confirmation": None})
        sideeffect.record_negative("c05_unpaired_action", hits0,
                                   sideeffect.ledger_lines(state_root, module),
                                   state_root, module)
        checks.add("c05_unpaired_action", ok5,
                   "未配对动作具名拒（核心负测）：伪造会话/token → %s；服务端"
                   "收包与动作账零增＝零副作用" % code5)

        ok6, code6 = expect_rejection(
            module, "cdp_pairing_code_invalid", module.pairing_bind,
            state_root, {"session_id": session_id,
                         "pairing_code": "0" * 32,
                         "controller_id": "ctrl-recon"})
        checks.add("c06_pairing_wrong_code", ok6,
                   "错码绑定具名拒：%s（码≠摘要）" % code6)

        short = module.pairing_issue(state_root, {
            "endpoint": endpoint, "controller_id": "ctrl-exp",
            "pairing_ttl_s": 1})
        time.sleep(1.4)
        ok7, code7 = expect_rejection(
            module, "cdp_pairing_code_expired", module.pairing_bind,
            state_root, {"session_id": short["session_id"],
                         "pairing_code": short["pairing_code"],
                         "controller_id": "ctrl-exp"})
        checks.add("c07_pairing_expired", ok7,
                   "过期码绑定具名拒：%s（TTL=1s 真实流逝后绑定，非模拟时钟）"
                   % code7)

        bind = module.pairing_bind(state_root, {
            "session_id": session_id, "pairing_code": code,
            "controller_id": "ctrl-recon"})
        token = bind["controller_token"]
        sessions = module.ledger_read(state_root, {})["sessions"]
        token_on_disk = any(token in p.read_text(encoding="utf-8",
                                                errors="ignore")
                            for p in state_files)
        checks.add("c08_pairing_bind_ok",
                   bool(token) and not token_on_disk and
                   sessions[0]["bound"] is True,
                   "正确绑定：controller_token=***（只返回一次；状态根扫描"
                   " token 原文零命中）→ 会话 bound=True")

        ok9, code9 = expect_rejection(
            module, "cdp_pairing_code_reused", module.pairing_bind,
            state_root, {"session_id": session_id, "pairing_code": code,
                         "controller_id": "ctrl-recon"})
        checks.add("c09_pairing_reused", ok9,
                   "同码二次绑定具名拒：%s（配对码一次性绑定——核心断言之"
                   "一）" % code9)

        mismatch = module.pairing_issue(state_root, {
            "endpoint": endpoint, "controller_id": "ctrl-real",
            "pairing_ttl_s": 300})
        ok10, code10 = expect_rejection(
            module, "cdp_controller_mismatch", module.pairing_bind,
            state_root, {"session_id": mismatch["session_id"],
                         "pairing_code": mismatch["pairing_code"],
                         "controller_id": "ctrl-else"})
        checks.add("c10_pairing_controller_mismatch", ok10,
                   "controller 不匹配绑定具名拒：%s（码绑定签发对象）"
                   % code10)

        # ---------------- S2 按 tab 授权（人工边界·授权面） ----------------
        nav_url = "http://127.0.0.1:%d%s" % (port, PAGE_A_PATH)
        hits = sideeffect.server_hits()
        ok11, code11 = expect_rejection(
            module, "cdp_tab_not_authorized", module.action_execute,
            state_root, {"session_id": session_id, "controller_token": token,
                         "tab_id": tab_a, "action": "navigate",
                         "params": {"url": nav_url},
                         "action_key": "act-pre-grant",
                         "human_confirmation": None})
        sideeffect.record_negative("c11_tab_unauthorized", hits,
                                   sideeffect.ledger_lines(state_root, module),
                                   state_root, module)
        checks.add("c11_tab_unauthorized_action", ok11,
                   "未授权 tab 动作具名拒（核心负测）：已配对、tab 未授权 → "
                   "%s；服务端收包与动作账零增" % code11)

        ok12, code12 = expect_rejection(
            module, "cdp_human_confirmation_required", module.tab_authorize,
            state_root, {"session_id": session_id, "controller_token": token,
                         "tab_id": tab_a, "human_confirmation": None})
        checks.add("c12_grant_needs_human", ok12,
                   "tab 授权缺人工确认具名拒：%s（L6 人工确认制——授权本身"
                   "即是人工决定面，人工边界核心负测）" % code12)

        grant_confirm = module.human_confirm(state_root, {
            "purpose": "tab_grant", "session_id": session_id,
            "tab_id": tab_a, "confirmed_by": "recon-human-console",
            "synthetic": True})
        grant = module.tab_authorize(state_root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": tab_a, "human_confirmation":
                grant_confirm["confirmation"]})
        grants = module.ledger_read(state_root, {})["grants"]
        checks.add(
            "c13_grant_ok", grant["replayed"] is False and len(grants) == 1
            and grants[0]["tab_id"] == tab_a,
            "带人工确认授权成功：grant=%s…（tab url=%s title=%r 为授权时点"
            "转录证据；confirmed_by=recon-human-console·synthetic 标记入"
            "确认账）；授权账 1 行" % (grants[0]["grant_id"][:12],
                                     grants[0]["tab_url"],
                                     grants[0]["tab_title"]))

        grant2 = module.tab_authorize(state_root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": tab_a, "human_confirmation": None})
        grants_after = module.ledger_read(state_root, {})["grants"]
        checks.add("c14_grant_replay",
                   grant2["replayed"] is True and len(grants_after) == 1,
                   "同 (session,tab) 再授权幂等重放：replayed=True 账不双记"
                   "（E24 append-only 幂等重放形态；重放不要求新确认＝同键"
                   "同内容语义）")

        fake_tab_confirm = module.human_confirm(state_root, {
            "purpose": "tab_grant", "session_id": session_id,
            "tab_id": "TARGET-DOES-NOT-EXIST",
            "confirmed_by": "recon-human-console", "synthetic": True})
        ok15, code15 = expect_rejection(
            module, "cdp_tab_not_found", module.tab_authorize, state_root,
            {"session_id": session_id, "controller_token": token,
             "tab_id": "TARGET-DOES-NOT-EXIST",
             "human_confirmation": fake_tab_confirm["confirmation"]})
        checks.add("c15_tab_not_found", ok15,
                   "授权不存在 tab 具名拒：%s（真实 /json/list 在位核对先行，"
                   "拒路径不消费人工确认）" % code15)

        # ---------------- S3 动作执行（人工边界·动作面） ----------------
        new_tab = http_json(cdp_port,
                            "/json/new?http://127.0.0.1:%d%s"
                            % (port, PAGE_B_PATH), method="PUT")
        tab_b = new_tab["id"]
        time.sleep(1.0)
        marker_b_before = None
        ws_b = next(t for t in http_json(cdp_port, "/json/list")
                    if t.get("id") == tab_b)["webSocketDebuggerUrl"]
        raw_b = RawCdp(ws_b)
        marker_b_before = raw_b.evaluate(EVAL_READ_MARKER)
        raw_b.close()
        ok16, code16 = expect_rejection(
            module, "cdp_tab_not_authorized", module.action_execute,
            state_root, {"session_id": session_id, "controller_token": token,
                         "tab_id": tab_b, "action": "evaluate",
                         "params": {"expression": EVAL_INCREMENT},
                         "action_key": "act-tab-b",
                         "human_confirmation": None})
        ws_b = next(t for t in http_json(cdp_port, "/json/list")
                    if t.get("id") == tab_b)["webSocketDebuggerUrl"]
        raw_b = RawCdp(ws_b)
        marker_b_after = raw_b.evaluate(EVAL_READ_MARKER)
        raw_b.close()
        checks.add("c16_second_tab_unauthorized", ok16,
                   "第二未授权 tab（独立合成页）动作具名拒：%s；tab-b 页面 "
                   "marker %s→%s 零变＝独立 tab 也有独立边界" %
                   (code16, marker_b_before, marker_b_after))

        hits = sideeffect.server_hits()
        ok17, code17 = expect_rejection(
            module, "cdp_human_confirmation_required", module.action_execute,
            state_root, {"session_id": session_id, "controller_token": token,
                         "tab_id": tab_a, "action": "navigate",
                         "params": {"url": nav_url},
                         "action_key": "act-nav-1",
                         "human_confirmation": None})
        sideeffect.record_negative("c17_action_needs_human", hits,
                                   sideeffect.ledger_lines(state_root, module),
                                   state_root, module)
        checks.add("c17_action_needs_human", ok17,
                   "已授权 tab 动作缺人工确认具名拒：%s（L6 人工边界——操作"
                   "受人工边界核心负测）；服务端 /pages/a 收包 %d→%d 零增"
                   % (code17, hits.get(PAGE_A_PATH, 0),
                      sideeffect.server_hits().get(PAGE_A_PATH, 0)))

        nav_confirm = module.human_confirm(state_root, {
            "purpose": "action", "session_id": session_id, "tab_id": tab_a,
            "action": "navigate", "action_key": "act-nav-1",
            "params": {"url": nav_url},
            "confirmed_by": "recon-human-console", "synthetic": True})
        nav = module.action_execute(state_root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": tab_a, "action": "navigate",
            "params": {"url": nav_url}, "action_key": "act-nav-1",
            "human_confirmation": nav_confirm["confirmation"]})
        hits_a = sideeffect.server_hits().get(PAGE_A_PATH, 0)
        ledger_lines = sideeffect.ledger_lines(state_root, module)
        checks.add("c18_navigate_exec",
                   nav["replayed"] is False and hits_a == 1
                   and ledger_lines == 1
                   and isinstance(nav["receipt"]["frame_id"], str),
                   "navigate 真实执行：回执 frame_id=%s…（真实 CDP 响应转"
                   "录·sha256=%s…）；服务端 /pages/a 收包恰 1＝真实外部副"
                   "作用；动作账 1 行 replayed=False"
                   % (str(nav["receipt"]["frame_id"])[:12],
                      nav["receipt_sha256"][:12]))

        eval_confirm = module.human_confirm(state_root, {
            "purpose": "action", "session_id": session_id, "tab_id": tab_a,
            "action": "evaluate", "action_key": "act-eval-1",
            "params": {"expression": EVAL_INCREMENT},
            "confirmed_by": "recon-human-console", "synthetic": True})
        ev = module.action_execute(state_root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": tab_a, "action": "evaluate",
            "params": {"expression": EVAL_INCREMENT},
            "action_key": "act-eval-1",
            "human_confirmation": eval_confirm["confirmation"]})
        ledger_lines = sideeffect.ledger_lines(state_root, module)
        checks.add("c19_evaluate_exec",
                   ev["replayed"] is False and ledger_lines == 2
                   and ev["receipt"]["result"]["value"] == "1",
                   "evaluate 真实执行：页面 marker 递增回执 value=%r（真实"
                   "CDP 响应转录）；动作账 2 行"
                   % ev["receipt"]["result"]["value"])

        hits = sideeffect.server_hits()
        lines_before = sideeffect.ledger_lines(state_root, module)
        ok20, code20 = expect_rejection(
            module, "cdp_human_confirmation_used", module.action_execute,
            state_root, {"session_id": session_id, "controller_token": token,
                         "tab_id": tab_a, "action": "evaluate",
                         "params": {"expression": EVAL_INCREMENT},
                         "action_key": "act-eval-2",
                         "human_confirmation": eval_confirm["confirmation"]})
        sideeffect.record_negative("c20_confirm_reused", hits, lines_before,
                                   state_root, module)
        checks.add("c20_confirm_single_use", ok20,
                   "人工确认一次性：重用已消费确认 → %s；账与收包零增（消费"
                   "即具名，append-only 事件流不改写）" % code20)

        wrong_confirm = module.human_confirm(state_root, {
            "purpose": "action", "session_id": session_id, "tab_id": tab_a,
            "action": "evaluate", "action_key": "act-other-key",
            "params": {"expression": "1+1"},
            "confirmed_by": "recon-human-console", "synthetic": True})
        hits = sideeffect.server_hits()
        lines_before = sideeffect.ledger_lines(state_root, module)
        ok21, code21 = expect_rejection(
            module, "cdp_human_confirmation_invalid", module.action_execute,
            state_root, {"session_id": session_id, "controller_token": token,
                         "tab_id": tab_a, "action": "evaluate",
                         "params": {"expression": EVAL_INCREMENT},
                         "action_key": "act-eval-2",
                         "human_confirmation": wrong_confirm["confirmation"]})
        sideeffect.record_negative("c21_confirm_mismatch", hits, lines_before,
                                   state_root, module)
        checks.add("c21_confirm_binding_mismatch", ok21,
                   "确认绑定不符具名拒：%s（确认绑定 purpose/session/tab/"
                   "action_key/params 摘要逐键）" % code21)

        # ---------------- S4 证据与外部副作用对账 ----------------
        replay = module.action_execute(state_root, {
            "session_id": session_id, "controller_token": token,
            "tab_id": tab_a, "action": "evaluate",
            "params": {"expression": EVAL_INCREMENT},
            "action_key": "act-eval-1", "human_confirmation": None})
        ws_a = next(t for t in http_json(cdp_port, "/json/list")
                    if t.get("id") == tab_a)["webSocketDebuggerUrl"]
        raw = RawCdp(ws_a)
        marker_now = raw.evaluate(EVAL_READ_MARKER)
        raw.close()
        lines_after_replay = sideeffect.ledger_lines(state_root, module)
        checks.add(
            "c22_replay_idempotent",
            replay["replayed"] is True
            and replay["receipt"] == ev["receipt"]
            and replay["receipt_sha256"] == ev["receipt_sha256"]
            and marker_now == "1" and lines_after_replay == 2
            and sideeffect.server_hits().get(PAGE_A_PATH, 0) == 1,
            "幂等重放（E24 形态）：同键同内容 → replayed=True 回执逐字同；"
            "页面 marker 保持 %r、服务端收包恰 1、账 2 行＝不重执行零重复"
            "副作用" % marker_now)

        ledger_snapshot = (state_root / "cdp_action_ledger.jsonl").read_bytes()
        ok23, code23 = expect_rejection(
            module, "cdp_action_key_conflict", module.action_execute,
            state_root, {"session_id": session_id, "controller_token": token,
                         "tab_id": tab_a, "action": "evaluate",
                         "params": {"expression": "7*7"},
                         "action_key": "act-eval-1",
                         "human_confirmation": None})
        ledger_after_conflict = \
            (state_root / "cdp_action_ledger.jsonl").read_bytes()
        checks.add(
            "c23_key_conflict", ok23 and ledger_after_conflict ==
            ledger_snapshot,
            "同键异内容具名冲突：%s；动作账逐字节不动（冲突不落账不消费）"
            % code23)

        ws_a = next(t for t in http_json(cdp_port, "/json/list")
                    if t.get("id") == tab_a)["webSocketDebuggerUrl"]
        raw = RawCdp(ws_a)
        live_url = raw.evaluate("location.href")
        live_marker = raw.evaluate(EVAL_READ_MARKER)
        shot = raw.screenshot_bytes()
        raw.close()
        actions = module.ledger_read(state_root, {})["actions"]
        sha_recompute_ok = all(
            a["receipt_sha256"] == hashlib.sha256(json.dumps(
                a["receipt"], ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest()
            for a in actions)
        eval_rows = [a for a in actions if a["action"] == "evaluate"]
        checks.add(
            "c24_ledger_vs_browser",
            live_url == nav_url and live_marker == "1"
            and len(actions) == 2 and sha_recompute_ok
            and eval_rows[-1]["receipt"]["result"]["value"] == live_marker,
            "独立 CDP 回读对账：浏览器实态 location.href==账面 navigate 目"
            "标页、页面 marker %r==账面 evaluate 回执最新值；账 %d 行==成"
            "功动作数；每行 receipt_sha256 现算复核相等（hash 真绑定回执）"
            % (live_marker, len(actions)))

        checks.add("c25_ledger_append_only_bytes",
                   ledger_snapshot == ledger_after_conflict
                   and (state_root / "cdp_action_ledger.jsonl")
                   .read_bytes().startswith(ledger_snapshot),
                   "动作账 append-only 字节稳定：重放与冲突全程逐字节不变"
                   "（%d bytes 只增不改）；确认账事件流 issued/consumed 追"
                   "加式" % len(ledger_snapshot))

        events = [json.loads(line) for line in (state_root /
                  "cdp_human_confirmations.jsonl").read_text(
                      encoding="utf-8").splitlines() if line.strip()]
        issued_n = sum(1 for e in events if e["event"] == "issued")
        consumed_n = sum(1 for e in events if e["event"] == "consumed")
        consumed_ids = [e["confirm_id"] for e in events
                        if e["event"] == "consumed"]
        grants_n = len(module.ledger_read(state_root, {})["grants"])
        checks.add(
            "c26_confirm_ledger_selfconsistent",
            consumed_n == len(actions) + grants_n
            and len(set(consumed_ids)) == consumed_n
            and issued_n >= consumed_n,
            "确认账事件流自洽：issued=%d active=%d；consumed=%d==成功动作 "
            "%d＋授权 %d（每成功恰消费一次·confirm_id 零重复消费）"
            % (issued_n, issued_n - consumed_n, consumed_n,
               len(actions), grants_n))

        png_name = "f65-cdp-session-%s.png" % profile
        evidence_dir = REPO_ROOT / args.evidence_roots / profile
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / png_name).write_bytes(shot)
        rejects_zero = sideeffect.all_zero
        checks.add(
            "c27_negatives_total_account",
            rejects_zero and shot.startswith(b"\x89PNG") and len(shot) > 1000,
            "负测汇总对账：%d 项具名拒全部『服务端收包＋动作账』前后零变；"
            "拒的动作零账行（拒≠隐式执行）；受控会话 PNG %s 已落证据"
            "（%d bytes）" % (len(sideeffect.negatives), png_name, len(shot)))

        # ---------------- S5 AST/红线纪律 ----------------
        gate_ok, io_functions, problems = ast_gate_first(tree)
        bad_endpoint_issue = None
        try:
            module.pairing_issue(state_root, {
                "endpoint": "ws://203.0.113.9:9222",
                "controller_id": "ctrl-bad", "pairing_ttl_s": 300})
        except module.CdpRemoteError as exc:
            bad_endpoint_issue = exc.code
        except Exception as exc:  # 非预期形态也算闸失效
            bad_endpoint_issue = "unexpected:" + type(exc).__name__
        checks.add(
            "c28_ast_gate_first",
            gate_ok and io_functions == 2
            and bad_endpoint_issue == "cdp_endpoint_not_local",
            "回环闸先行（先闸后网）：含 IO 的函数 %d 个全部先调 require_"
            "loopback_endpoint（闸自身零网络）；运行面非回环端点 "
            "ws://203.0.113.9:9222（RFC5737 文档地址）签发会话 → %s＝非"
            "回环会话结构性不可建" % (io_functions, bad_endpoint_issue))

        const_problems = ast_constant_scan(tree)
        imports = _collect_imports(tree)
        checks.add(
            "c29_ast_constants_imports",
            not const_problems and imports == ALLOWED_IMPORTS,
            "AST 常量与导入闭集：字符串常量零非回环 URL 零 APPDATA（问题"
            "%d）；导入闭集恰 %s（websocket 为函数内延迟导入＝受控 CDP 通"
            "道；零 socket/subprocess/eval）" % (len(const_problems),
                                                sorted(imports)))

        state_blob = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in state_root.rglob("*") if p.is_file())
        confirms = module.ledger_read(state_root, {})  # 触发只读投影
        checks.add(
            "c30_state_root_hygiene",
            code not in state_blob and token not in state_blob
            and grant_confirm["confirmation"] not in state_blob
            and str(state_root).startswith(str(Path(tempfile.gettempdir()))),
            "状态根卫生：配对码/controller_token/确认 token 原文全表面零落"
            "盘（只存摘要）；状态根=%s（%%TEMP%% 下；%%APPDATA%%\\JusBench "
            "零触碰）" % state_root)

        sha_after = {
            "cdp_remote.py": sha256_file(str(MODULE_PATH)),
            "legal_entry.py": sha256_file(str(LEGAL_ENTRY)),
        }
        checks.add("c31_frozen_faces",
                   sha_after == sha_before
                   and confirms["schema"] == "juscite-f65-cdp-remote/1",
                   "冻结面全程 sha256 前后相等：cdp_remote.py＋legal_entry."
                   "py 零改动（oc28 零触碰；台账与 00-总协调零改动随账房）")

    finally:
        kill_tree(browser)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        workspace.cleanup()

    commit = subprocess.run(["git", "rev-parse", "HEAD"],
                            capture_output=True, text=True,
                            cwd=str(REPO_ROOT)).stdout.strip()
    evidence = {
        "run_date": RUN_DATE,
        "profile": profile,
        "command": "python -X utf8 " + " ".join(sys.argv),
        "cwd": str(REPO_ROOT),
        "subject_commit": commit,
        "frozen_faces_sha256": sha_before,
        "authority_row": "06 V7-65 F65（v2；owner=product；B5；"
                         "UI_HOST_OR_NEW_PRODUCT）acceptance=浏览器按tab"
                         "授权与配对；操作受人工边界，证据和外部副作用可"
                         "对账；source_rationale=风险高，L6 人工确认制已"
                         "覆盖主场景（人工边界负测为核心断言）",
        "synthetic_materials": {
            "browser": version.get("Browser"),
            "browser_binary": binary,
            "mode": "headless=new（本地受控实例；--remote-debugging-port=0"
                    "＋%TEMP% user-data-dir）",
            "pages": ["127.0.0.1 回环合成页 /pages/a、/pages/b"],
            "server_requests_seen": list(_SyntheticPages.received),
            "server_hit_counts": dict(_SyntheticPages.hits),
            "real_external_traffic": "零（唯一网络面=127.0.0.1 回环）",
        },
        "negative_probe_ledger": sideeffect.negatives,
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    for root in [part.strip() for part in args.evidence_roots.split(",")
                 if part.strip()]:
        out_dir = REPO_ROOT / root / profile
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "f65-cdp-remote-recon.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=1),
            encoding="utf-8")
    print("---")
    print("RECON_%s %d/%d checks — profile=%s" % (
        "OK" if checks.all_passed else "FAIL",
        checks.passed_count, len(checks.items), profile))
    return 0 if checks.all_passed else 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("desktop", "selfhost"),
                        action="append", default=None)
    parser.add_argument("--browser", default=None,
                        help="chrome|msedge|可执行文件全路径（缺省按探测表）")
    parser.add_argument("--evidence-roots", default="evidence/F65")
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not MODULE_PATH.is_file():
        print("FATAL: 产品面 cdp_remote.py 不在 %s" % MODULE_PATH)
        return 2
    module = load_module()
    codes = [run_profile(args, profile, module) for profile in profiles]
    return 0 if all(code == 0 for code in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
