# -*- coding: utf-8 -*-
"""F74 网页检索兜底＋web-verified 声明 验收对账（PENDING_OWNER 版，工单
W4-U44）。

06 行 F74（v1.5；owner=product+codices；B4；desktop/selfhost 双实例）
acceptance＝网页结果 URL 与原文真实核验，web 来源声明明确，禁编 URL；
preserved＝随 F64 降级链末端开（硬依赖 W4-U41：F64-v1.5 付费/web 段
2026-10-21 已 VERIFIED，本单接末端）。

分段（每 profile 全量 20 检，断言全走真产品入口 legal_entry 子进程径）：
  S1 链末端语义＋冻结面钉定：W2a-U13 v1 策略面零漂移（链
     本地→付费→web、web 段=declared_gap_pending_F64-v1.5(B4)——F74 恰
     接该末端）；F74 冻结方法组恰一方法；codices E22 冻结面 lccc_consumer
     与 P11 commercial_law_mcp sha256 钉定（authority/14 台账值）。
  S2 白名单域闸（T05 教训：CodeMode web fetch 无闸→本面请求面必须先闸
     后网）：白名单缺配置=fail-closed NOT_CONNECTED；方案白名单外/
     域名白名单外 typed 拒且服务端收包计数零增（闸先于任何网络 I/O）；
     AST：凡发起 urlopen 的函数体必先调 gate_url；零 urljoin。
  S3 检索→取回原文→sha256 绑定→引文逐字核验（127.0.0.1 回环合成端点，
     全程合成材料零真实外联）：候选 URL 逐字转录 byte-exact；取回原文字
     节 sha256 与服务端独立记账的所供字节 sha 逐字相等（hash 真绑定原文，
     禁只存 URL）；verified 记录携 W4-U41 web_verified 声明（schema
     juscite-f64-web-verified/1、basis=web_verified、signs_current=False）；
     引文不逐字→具名 gap 零内容零声明；请求面主机全落白名单。
  S4 web-verified=W4-U41 同一分账语义（跨单一致性断言）：F74 产物声明与
     桥上 statute.web_declaration 对同一取证三元组输出逐键相等；AST：
     声明面单一来源 declare_web_verified，web_fallback 内零声明键/schema/
     basis 常量复制（永不冒数据库核验）。
  S5 禁编 URL：AST 级零拼造（方案前缀字面量仅 WEB_URL_SCHEMES 两方案
     条目；零 f-string/format/%/加号拼 URL；零 urljoin）＋负测：无网
     （端点拒连）→具名缺口 candidates/verified 恒空零伪造；混合结果中
     方案外/白名单外 URL→具名 gap 且永不被取文（服务端只收到白名单内
     取文）。
  S6 失败不造假＋链末端闸＋冻结面全程字节稳定：前两段具名缺口证据缺失
     →typed 拒（链末端不跳开）；引文不逐字→零声明；检索端点 500→具名
     web_status_500 零伪造；codices/P11/产品声明面 sha 前后相等＋
     PROVIDERS 零引用（AST 零 commercial import）。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f74_web_fallback_recon.py --profile desktop
  python -X utf8 tools/PENDING_OWNER_f74_web_fallback_recon.py --profile desktop --profile selfhost
  [--codices-repo <含 lccc_consumer.py 目录>] [--formal-root <codices 正式目录>]
  [--commercial-tool <commercial_law_mcp.py>]
  [--evidence-roots "evidence/F74"]

--profile 可重复（action=append，同 f64_f69 工具同款）；重复即逐 profile
  依序全量跑各 20 检并各写证据；缺省=desktop。
exit 0＝全部断言过（RECON_OK）；证据 JSON 写 <root>/<profile>/ 各一份。
唯一网络面＝127.0.0.1 回环合成端点（绝不真实外联）；无网负测用本机拒连
端口。裁决#8-12 同频：无网/未授权=具名缺口不造结果；真实互联网法源页
实测挂授权后补（不假销账）。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
WEB_FALLBACK = REPO_ROOT / "implementation" / "python" / "web_fallback.py"
STATUTE_VALIDITY = REPO_ROOT / "implementation" / "python" / "statute_validity.py"

DEFAULT_CODICES_REPO = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u12-e22"
)
DEFAULT_FORMAL_ROOT = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices"
)
DEFAULT_COMMERCIAL_TOOL = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\tools\commercial_law_mcp.py"
)

# E22 冻结面 v1.0（W2a-U12 钉定；W2a-U13/W4-U41 同款 FATAL 钉）。
LCCC_SHA256 = "eb11ee5be548dbfed6e8b3f0052d11f28abb0cd010e1ef6236fb1e2fecf245d9"
# P11 主检 sha256（authority/14-Python入口证据.csv 行 P11；W4-U41 亲验）。
P11_SHA256 = "b7b7c1fe1faf57791b84969b1c47cdfcef62b1a3ed97482dbbe09d4204aef0a9"

# 合成材料（全合成网页与引文，与任何真实法源页零交集）。
SYNTH_QUOTE = "【W4U44合成引文】个人信息处理者不得以个人不同意为由拒绝提供产品或者服务（合成条文·仅供核验）。"
SYNTH_TITLE_A = "合成法源网页甲（含引文）"
SYNTH_TITLE_B = "合成法源网页乙（不含引文）"

WEB_FALLBACK_SCHEMA = "juscite-f74-web-fallback/1"
W4U41_DECLARATION_SCHEMA = "juscite-f64-web-verified/1"
WHITELIST = ["127.0.0.1"]
CLOSED_SET_METHOD = "web.not_in_frozen_list_probe"


def sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail}
        )
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用；返回 {exit, payload}。付费 token 一律剥除
    （断言子进程环境确定性，W4-U41 同款）。"""
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
        env = {k: v for k, v in os.environ.items()}
        for var in ("YUANDIAN_MCP_TOKEN", "PKULAW_MCP_TOKEN"):
            env.pop(var, None)
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, text=True, encoding="utf-8", env=env,
            timeout=300, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


# ---------------------------------------------------------------------- #
# 合成回环 web 端点（S3/S5/S6 专用；绝不真实外联）
# ---------------------------------------------------------------------- #

class _SyntheticWeb(BaseHTTPRequestHandler):
    """合成检索端点＋合成法源页。mode：
    normal=甲页含引文＋乙页不含；mixed=另发方案外/白名单外结果 URL；
    noquote=只发不含引文的乙页；error=检索端点 500。
    服务端独立记账：received（请求面）＋served（所供字节 sha——recon 独立
    复算用，hash 绑定不回读产品自证）。"""
    mode = "normal"
    received: list = []
    served: dict = {}

    def _log(self, op: str):
        _SyntheticWeb.received.append({"op": op, "path": self.path,
                                       "host": self.headers.get("Host", "")})

    def _send(self, code: int, payload: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self._log("search")
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            request = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            request = {}
        if _SyntheticWeb.mode == "error":
            self._send(500, "synthetic search outage".encode("utf-8"),
                       "text/plain; charset=utf-8")
            return
        host = "127.0.0.1:%d" % self.server.server_address[1]
        page_a = _page_bytes(with_quote=True)
        page_b = _page_bytes(with_quote=False)
        _SyntheticWeb.served["/pages/a"] = page_a
        _SyntheticWeb.served["/pages/b"] = page_b
        if _SyntheticWeb.mode == "noquote":
            results = [
                {"title": SYNTH_TITLE_B,
                 "url": "http://%s/pages/b" % host}]
        else:
            results = [
                {"title": SYNTH_TITLE_A,
                 "url": "http://%s/pages/a" % host}]
            if _SyntheticWeb.mode in ("normal", "mixed"):
                results.append(
                    {"title": SYNTH_TITLE_B,
                     "url": "http://%s/pages/b" % host})
            if _SyntheticWeb.mode == "mixed":
                results.append({"title": "方案外合成候选",
                                "url": "ftp://%s/pages/c" % host})
                results.append({"title": "白名单外合成候选",
                                "url": "http://out-of-allowlist.example/x"})
        body = json.dumps({"results": results},
                          ensure_ascii=False).encode("utf-8")
        self._send(200, body, "application/json; charset=utf-8")

    def do_GET(self):
        self._log("fetch")
        if _SyntheticWeb.mode == "error":
            self._send(500, b"synthetic outage", "text/plain; charset=utf-8")
            return
        page = _SyntheticWeb.served.get(self.path)
        if page is None:
            self._send(404, b"synthetic missing", "text/plain; charset=utf-8")
            return
        self._send(200, page, "text/html; charset=utf-8")

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass


def _page_bytes(with_quote: bool) -> bytes:
    body = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<title>合成网页</title></head><body><main>")
    if with_quote:
        body += "<p>" + SYNTH_QUOTE + "</p>"
    body += "<p>合成网页其余段落（与引文无关）。</p></main></body></html>"
    return body.encode("utf-8")


def _start_server() -> tuple:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SyntheticWeb)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # 夹具预热：吸收回环 listener 首连瞬态（防火墙/首包冷启）；只暖夹具，
    # 不改产品语义；预热请求计入 received 后清零保持收包断言基线。
    import urllib.request
    for _ in range(20):
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    "http://127.0.0.1:%d/search" % port, data=b"{}",
                    headers={"Content-Type": "application/json"}),
                timeout=5).read()
            break
        except Exception:
            time.sleep(0.05)
    _SyntheticWeb.received = []
    return server, thread, port


def _closed_port() -> int:
    """本机拒连端口（无网负测用；bind 后即关）。"""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


# ---------------------------------------------------------------------- #
# AST 级断言（禁编 URL／闸先于网／声明单一来源）
# ---------------------------------------------------------------------- #

def url_fabrication_violations(path: str) -> list:
    """AST：禁编 URL。含方案前缀的字符串常量只许是 WEB_URL_SCHEMES 两个
    方案条目；零 f-string/format/%/加号拼 URL；零 urljoin 引用。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    scheme_consts = {"http://", "https://"}
    offenders: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if (node.value.startswith(("http://", "https://"))
                    and node.value not in scheme_consts):
                offenders.append("url_literal:" + node.value[:60])
        elif isinstance(node, ast.JoinedStr):
            if any(isinstance(part, ast.Constant)
                   and isinstance(part.value, str)
                   and "http" in part.value for part in node.values):
                offenders.append("fstring_building_url")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "format" \
                and isinstance(node.func.value, ast.Constant) \
                and isinstance(node.func.value.value, str) \
                and "http" in node.func.value.value:
            offenders.append("format_building_url")
        elif isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Mod) \
                    and isinstance(node.left, ast.Constant) \
                    and isinstance(node.left.value, str) \
                    and "http" in node.left.value:
                offenders.append("percent_building_url")
            if isinstance(node.op, ast.Add):
                for side in (node.left, node.right):
                    if isinstance(side, ast.Constant) \
                            and isinstance(side.value, str) \
                            and "http" in side.value:
                        offenders.append("concat_building_url")
        elif isinstance(node, ast.Attribute) and node.attr == "urljoin":
            offenders.append("urljoin_reference")
    return offenders


def gate_precedes_network_violations(path: str) -> list:
    """AST（T05 教训）：凡发起 urlopen 的函数体必先调 gate_url——闸先于
    任何网络 I/O；gate_url 自身零网络。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    offenders: list = []

    def _has_urlopen(node) -> bool:
        return any(
            isinstance(sub, ast.Call)
            and ((isinstance(sub.func, ast.Name) and sub.func.id == "urlopen")
                 or (isinstance(sub.func, ast.Attribute)
                     and sub.func.attr == "urlopen"))
            for sub in ast.walk(node))

    def _has_gate(node) -> bool:
        return any(
            isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            and sub.func.id == "gate_url"
            for sub in ast.walk(node))

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and _has_urlopen(node) \
                and not _has_gate(node):
            offenders.append(node.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "gate_url" \
                and _has_urlopen(node):
            offenders.append("gate_url_itself_opens_network")
    return offenders


def declaration_single_source_facts(path: str) -> dict:
    """AST：声明面单一来源——web_fallback 引用 declare_web_verified（W4-U41
    面）；零声明 schema/basis/签名键常量复制（永不冒数据库核验）。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    consts: set = set()
    declares_import = False
    declares_called = False
    commercial_refs: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            consts.add(node.value)
        if isinstance(node, ast.ImportFrom) and node.module == "statute_validity":
            if any(alias.name == "declare_web_verified" for alias in node.names):
                declares_import = True
        if isinstance(node, ast.Name) and node.id == "declare_web_verified":
            declares_called = True
        if isinstance(node, ast.Name) and "commercial" in node.id.lower():
            commercial_refs.append("name:" + node.id)
        if isinstance(node, ast.Attribute) and "commercial" in node.attr.lower():
            commercial_refs.append("attr:" + node.attr)
    duplicated = sorted(
        {W4U41_DECLARATION_SCHEMA, "web_verified", "local_db_verified",
         "paid_db_verified",
         "provider_url", "provider_record_id", "face_sha256", "lccc_face"}
        & consts)
    return {
        "declares_import": declares_import,
        "declares_called": declares_called,
        "duplicated_declaration_consts": duplicated,
        "commercial_refs": sorted(set(commercial_refs)),
    }


def frozen_group_methods(path: str, group: str) -> set:
    """AST：legal_entry 中指定 frozenset 方法组的确切成员。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == group
                for t in node.targets):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Set):
                    return {elt.value for elt in sub.elts
                            if isinstance(elt, ast.Constant)}
    return set()


# ---------------------------------------------------------------------- #
# 分段
# ---------------------------------------------------------------------- #

def section_s1(checks: Checks, base_config: dict, commercial_tool: str,
               codices_repo: str) -> None:
    strategy = call_entry("statute.source_strategy", {}, base_config)
    result = strategy["payload"].get("result", {}) \
        if strategy["exit"] == 0 else {}
    web_seg = (result.get("segments") or {}).get("web") or {}
    checks.add(
        "S1A_chain_tail_reserved_in_v1_strategy",
        strategy["exit"] == 0
        and result.get("chain") == ["local", "paid", "web"]
        and result.get("policy") == "local_first_no_silent_escalation"
        and web_seg.get("state") == "declared_gap_pending_F64-v1.5(B4)"
        and web_seg.get("gap", {}).get("reason")
        == "WEB_FALLBACK_PENDING_F64_V1_5_B4"
        and bool(result.get("web_verified_note")),
        "W2a-U13 v1 策略面零漂移：chain=%s policy=%s web 段=%s（gap=%s）——"
        "降级链仍保留 web 为末端，F74 恰接该末端（W4-U41 后末端已开）"
        % (result.get("chain"), result.get("policy"),
           web_seg.get("state"), web_seg.get("gap", {}).get("reason")))
    group = frozen_group_methods(str(LEGAL_ENTRY), "WEB_FALLBACK_METHODS")
    unknown = call_entry(CLOSED_SET_METHOD, {}, base_config)
    payload = unknown["payload"]
    checks.add(
        "S1B_f74_group_frozen_closed_set",
        group == {"web.fallback_retrieve"}
        and unknown["exit"] == 3
        and payload.get("status") == "NOT_CONNECTED"
        and "method_not_connected" in str(payload.get("code")),
        "F74 冻结方法组恰一方法 web.fallback_retrieve（AST：%s）；封闭集外"
        "%s → exit=%s %s/%s（桥 fail-closed）"
        % (sorted(group), CLOSED_SET_METHOD, unknown["exit"],
           payload.get("status"), payload.get("code")))
    lccc = sha256_file(os.path.join(codices_repo, "lccc_consumer.py"))
    p11 = sha256_file(commercial_tool)
    checks.add(
        "S1C_codices_e22_p11_frozen_faces_pinned",
        lccc == LCCC_SHA256 and p11 == P11_SHA256,
        "codices E22 冻结面 lccc_consumer.py sha256 %s…（W2a-U12 钉定）＋"
        "P11 commercial_law_mcp.py sha256 %s…（authority/14 台账值）双双"
        "亲验在位" % (lccc[:8], p11[:8]))


def section_s2(checks: Checks, port: int) -> None:
    baseline = len(_SyntheticWeb.received)
    no_whitelist = call_entry(
        "web.fallback_retrieve",
        {"query": "合成查询", "quote": SYNTH_QUOTE,
         "chain": {"local_gap": "LOCAL_FACE_NOT_FOUND",
                   "paid_gap": "PAID_TOKEN_NOT_CONFIGURED"}},
        {"web_search_endpoint": "http://127.0.0.1:%d/search" % port})
    payload = no_whitelist["payload"]
    checks.add(
        "S2A_whitelist_missing_fail_closed",
        no_whitelist["exit"] == 3
        and payload.get("status") == "NOT_CONNECTED"
        and payload.get("code") == "web_whitelist_not_configured",
        "白名单缺配置 → exit=%s %s/%s（fail-closed：零隐式放行域，T05 无闸"
        "教训反面钉死）" % (no_whitelist["exit"], payload.get("status"),
                            payload.get("code")))
    scheme = call_entry(
        "web.fallback_retrieve",
        {"query": "合成查询", "quote": SYNTH_QUOTE,
         "chain": {"local_gap": "LOCAL_FACE_NOT_FOUND",
                   "paid_gap": "PAID_TOKEN_NOT_CONFIGURED"}},
        {"web_allowed_domains": WHITELIST,
         "web_search_endpoint": "ftp://127.0.0.1:%d/search" % port})
    payload = scheme["payload"]
    checks.add(
        "S2B_scheme_outside_typed_reject_before_network",
        scheme["exit"] == 3
        and payload.get("status") == "NOT_CONNECTED"
        and payload.get("code") == "web_url_scheme_not_allowed"
        and len(_SyntheticWeb.received) == baseline,
        "方案白名单外端点（ftp://）→ exit=%s %s/%s；服务端收包计数 %d→%d "
        "零增＝闸先于任何网络 I/O"
        % (scheme["exit"], payload.get("status"), payload.get("code"),
           baseline, len(_SyntheticWeb.received)))
    baseline = len(_SyntheticWeb.received)
    domain = call_entry(
        "web.fallback_retrieve",
        {"query": "合成查询", "quote": SYNTH_QUOTE,
         "chain": {"local_gap": "LOCAL_FACE_NOT_FOUND",
                   "paid_gap": "PAID_TOKEN_NOT_CONFIGURED"}},
        {"web_allowed_domains": WHITELIST,
         "web_search_endpoint": "http://not-allowed.example/search"})
    payload = domain["payload"]
    checks.add(
        "S2C_domain_outside_typed_reject_before_network",
        domain["exit"] == 3
        and payload.get("status") == "NOT_CONNECTED"
        and payload.get("code") == "web_domain_not_whitelisted:not-allowed.example"
        and len(_SyntheticWeb.received) == baseline,
        "域名白名单外端点 → exit=%s %s/%s；服务端收包计数 %d→%d 零增＝白名单"
        "外主机永达不了网络"
        % (domain["exit"], payload.get("status"), payload.get("code"),
           baseline, len(_SyntheticWeb.received)))
    offenders = gate_precedes_network_violations(str(WEB_FALLBACK))
    checks.add(
        "S2D_ast_gate_precedes_network_zero_urljoin",
        not offenders,
        "AST：凡发起 urlopen 的函数体必先调 gate_url（闸先于网，T05 "
        "CodeMode 无闸教训钉死）；gate_url 自身零网络；零 urljoin；违规=%s"
        % (";".join(offenders) or "无"))


def section_s3(checks: Checks, port: int, base_config: dict) -> dict:
    _SyntheticWeb.mode = "normal"
    response = call_entry(
        "web.fallback_retrieve",
        {"query": "合成查询词", "quote": SYNTH_QUOTE,
         "chain": {"local_gap": "LOCAL_FACE_NOT_FOUND",
                   "paid_gap": "PAID_TOKEN_NOT_CONFIGURED"}},
        dict(base_config,
             web_allowed_domains=WHITELIST,
             web_search_endpoint="http://127.0.0.1:%d/search" % port))
    payload = response["payload"]
    result = payload.get("result", {}) if response["exit"] == 0 else {}
    verified = result.get("verified") or []
    served_a = _SyntheticWeb.served.get("/pages/a", b"")
    served_b = _SyntheticWeb.served.get("/pages/b", b"")
    sha_a = hashlib.sha256(served_a).hexdigest()
    url_a = "http://127.0.0.1:%d/pages/a" % port
    url_b = "http://127.0.0.1:%d/pages/b" % port
    ok_a = (
        response["exit"] == 0 and len(verified) == 1
        and verified[0].get("source_url") == url_a
        and verified[0].get("content_sha256") == sha_a
        and verified[0].get("quote_verified") is True)
    checks.add(
        "S3A_verified_hash_binds_retrieved_original",
        ok_a,
        "取回原文 hash 绑定（禁只存 URL）：verified 恰 1（甲页）；URL 与"
        "检索响应逐字转录（byte-exact）；content_sha256=%s… 与服务端独立"
        "记账所供字节 sha 逐字相等（hash 真绑定取回原文，非产品自证）；"
        "引文逐字核对 quote_verified=True" % sha_a[:8])
    declaration = (verified[0].get("declaration") or {}) if verified else {}
    checks.add(
        "S3B_verified_carries_w4u41_web_verified_declaration",
        bool(declaration)
        and declaration.get("schema") == W4U41_DECLARATION_SCHEMA
        and declaration.get("verification_basis") == "web_verified"
        and declaration.get("signs_current") is False
        and declaration.get("source_url") == url_a
        and declaration.get("content_sha256") == sha_a,
        "verified 记录携 W4-U41 web_verified 声明：schema=%s basis=%s "
        "signs_current=False（web 来源不签现行）；取证 URL/sha 原样转录"
        % (declaration.get("schema"), declaration.get("verification_basis")))
    candidates = result.get("candidates") or []
    gaps = result.get("gaps") or []
    gap_b = [g for g in gaps if g.get("source_url") == url_b]
    ok_c = (
        [c.get("source_url") for c in candidates] == [url_a, url_b]
        and len(gap_b) == 1
        and gap_b[0].get("reason") == "web_quote_not_verified"
        and all("content_sha256" not in g and "declaration" not in g
                for g in gaps))
    checks.add(
        "S3C_candidates_transcribed_verbatim_quote_gap_named",
        ok_c,
        "候选 URL 逐字转录＝%s（与服务端所发逐字节一致，零拼造）；乙页引文"
        "不逐字→具名 gap web_quote_not_verified 且 gap 行零 content_sha256"
        "零 declaration（失败不造假）"
        % [c.get("source_url") for c in candidates])
    fetches = [c for c in (result.get("network_calls") or [])
               if c.get("op") == "fetch"]
    server_fetch_paths = [r["path"] for r in _SyntheticWeb.received
                          if r["op"] == "fetch"]
    hosts_seen = {c.get("host") for c in (result.get("network_calls") or [])}
    ok_d = (
        response["exit"] == 0
        and len(fetches) == 2
        and sorted(server_fetch_paths) == ["/pages/a", "/pages/b"]
        and hosts_seen == {"127.0.0.1"})
    checks.add(
        "S3D_request_surface_whitelist_only",
        ok_d,
        "请求面全落白名单域：产品请求面 fetch×2 恰对甲/乙两页；服务端实测"
        "只收到 /pages/a、/pages/b 两次取文；全部请求主机=%s ⊆ 白名单 %s"
        % (sorted(hosts_seen), WHITELIST))
    return result


def section_s4(checks: Checks, port: int, retrieve_result: dict,
               base_config: dict) -> None:
    verified = retrieve_result.get("verified") or []
    declaration = (verified[0].get("declaration") or {}) if verified else {}
    cross = call_entry(
        "statute.web_declaration",
        {"source_url": declaration.get("source_url"),
         "content_sha256": declaration.get("content_sha256"),
         "retrieved_utc": declaration.get("retrieved_utc")},
        base_config)
    cross_result = cross["payload"].get("result", {}) if cross["exit"] == 0 else {}
    checks.add(
        "S4A_cross_unit_declaration_identical_to_w4u41_face",
        cross["exit"] == 0 and bool(declaration)
        and cross_result == declaration,
        "跨单一致性（W4-U41 同一分账语义）：F74 产物声明与桥上 "
        "statute.web_declaration 对同一取证三元组的输出逐键相等（%d 键）；"
        "声明面单一来源，非第二权威" % len(declaration))
    facts = declaration_single_source_facts(str(WEB_FALLBACK))
    ok = (
        facts["declares_import"] and facts["declares_called"]
        and not facts["duplicated_declaration_consts"]
        and not facts["commercial_refs"])
    checks.add(
        "S4B_declaration_single_sourced_ast",
        ok,
        "AST：web_fallback 引 import＋实调 declare_web_verified（W4-U41 "
        "statute_validity 面）；零声明 schema/basis/数据库签名键常量复制"
        "（web-verified 永不冒数据库核验）；零 P11/commercial 引用；重复"
        "常量=%s commercial 引用=%s"
        % (facts["duplicated_declaration_consts"] or "无",
           facts["commercial_refs"] or "无"))


def section_s5(checks: Checks, port: int, base_config: dict) -> None:
    offenders = url_fabrication_violations(str(WEB_FALLBACK))
    checks.add(
        "S5A_ast_zero_url_fabrication",
        not offenders,
        "AST 级禁编 URL：含方案前缀的字符串常量仅 WEB_URL_SCHEMES 两方案"
        "条目；零 f-string/format/%%/加号拼 URL；零 urljoin；违规=%s"
        % (";".join(offenders) or "无"))
    dead = _closed_port()
    offline = call_entry(
        "web.fallback_retrieve",
        {"query": "合成查询词", "quote": SYNTH_QUOTE,
         "chain": {"local_gap": "LOCAL_FACE_NOT_FOUND",
                   "paid_gap": "PAID_TOKEN_NOT_CONFIGURED"}},
        {"web_allowed_domains": WHITELIST,
         "web_search_endpoint": "http://127.0.0.1:%d/search" % dead})
    payload = offline["payload"]
    result = payload.get("result", {}) if offline["exit"] == 0 else {}
    gaps = result.get("gaps") or []
    ok = (
        offline["exit"] == 0
        and result.get("candidates") == []
        and result.get("verified") == []
        and len(gaps) == 1
        and gaps[0].get("reason", "").startswith("web_fetch_failed:"))
    checks.add(
        "S5B_no_network_named_gap_zero_fabrication",
        ok,
        "无网负测（端点 127.0.0.1:%d 拒连）→ exit=%s 具名缺口 %s；"
        "candidates/verified 恒空（零造结果零编 URL，裁决#8-12 同频）"
        % (dead, offline["exit"],
           gaps[0].get("reason") if gaps else "无"))
    _SyntheticWeb.mode = "mixed"
    baseline_fetches = len([r for r in _SyntheticWeb.received
                            if r["op"] == "fetch"])
    mixed = call_entry(
        "web.fallback_retrieve",
        {"query": "合成查询词", "quote": SYNTH_QUOTE,
         "chain": {"local_gap": "LOCAL_FACE_NOT_FOUND",
                   "paid_gap": "PAID_TOKEN_NOT_CONFIGURED"}},
        dict(base_config,
             web_allowed_domains=WHITELIST,
             web_search_endpoint="http://127.0.0.1:%d/search" % port))
    mixed_result = mixed["payload"].get("result", {}) \
        if mixed["exit"] == 0 else {}
    gaps = mixed_result.get("gaps") or []
    url_b = "http://127.0.0.1:%d/pages/b" % port
    scheme_gap = [g for g in gaps
                  if g.get("reason") == "web_url_scheme_not_allowed"]
    domain_gap = [g for g in gaps
                  if str(g.get("reason", "")).startswith(
                      "web_domain_not_whitelisted:out-of-allowlist.example")]
    server_fetch_paths = [r["path"] for r in _SyntheticWeb.received
                          if r["op"] == "fetch"][baseline_fetches:]
    verified = mixed_result.get("verified") or []
    ok = (
        mixed["exit"] == 0
        and len(scheme_gap) == 1 and len(domain_gap) == 1
        and server_fetch_paths == ["/pages/a", "/pages/b"]
        and len(verified) == 1)
    checks.add(
        "S5C_mixed_results_gated_named_never_fetched",
        ok,
        "混合结果负测：方案外（ftp://）与白名单外（out-of-allowlist.example）"
        "候选各落具名 gap（%s/%s）且永不被取文——服务端本段只收到白名单内"
        "/pages/a、/pages/b 两次取文；白名单内核验照常 verified×1"
        % (scheme_gap[0].get("reason") if scheme_gap else "缺",
           domain_gap[0].get("reason") if domain_gap else "缺"))
    _SyntheticWeb.mode = "normal"


def section_s6(checks: Checks, port: int, base_config: dict,
               commercial_tool: str, codices_repo: str,
               sha_before: dict) -> None:
    tail = call_entry(
        "web.fallback_retrieve",
        {"query": "合成查询词", "quote": SYNTH_QUOTE,
         "chain": {"local_gap": "LOCAL_FACE_NOT_FOUND"}},
        dict(base_config,
             web_allowed_domains=WHITELIST,
             web_search_endpoint="http://127.0.0.1:%d/search" % port))
    payload = tail["payload"]
    checks.add(
        "S6A_chain_tail_requires_prior_gap_proofs",
        tail["exit"] == 3
        and payload.get("status") == "NOT_CONNECTED"
        and payload.get("code") == "web_chain_prior_segments_not_declared",
        "链末端闸：付费段具名缺口证据缺失（chain.paid_gap 空）→ exit=%s "
        "%s/%s——本地→付费→web 零跳级，末端不携前两段缺口凭证不开"
        % (tail["exit"], payload.get("status"), payload.get("code")))
    _SyntheticWeb.mode = "noquote"
    noquote = call_entry(
        "web.fallback_retrieve",
        {"query": "合成查询词", "quote": SYNTH_QUOTE,
         "chain": {"local_gap": "LOCAL_FACE_NOT_FOUND",
                   "paid_gap": "PAID_TOKEN_NOT_CONFIGURED"}},
        dict(base_config,
             web_allowed_domains=WHITELIST,
             web_search_endpoint="http://127.0.0.1:%d/search" % port))
    noquote_result = noquote["payload"].get("result", {}) \
        if noquote["exit"] == 0 else {}
    text = json.dumps(noquote_result, ensure_ascii=False)
    checks.add(
        "S6B_quote_not_verified_never_signs_declaration",
        noquote["exit"] == 0
        and noquote_result.get("verified") == []
        and any(g.get("reason") == "web_quote_not_verified"
                for g in (noquote_result.get("gaps") or []))
        and "web_verified" not in text
        and W4U41_DECLARATION_SCHEMA not in text,
        "引文不逐字负测（只发不含引文的乙页）→ verified 恒空＋具名 gap；"
        "全载荷零 web_verified 字样零声明 schema（永不冒数据库核验签名）")
    _SyntheticWeb.mode = "error"
    outage = call_entry(
        "web.fallback_retrieve",
        {"query": "合成查询词", "quote": SYNTH_QUOTE,
         "chain": {"local_gap": "LOCAL_FACE_NOT_FOUND",
                   "paid_gap": "PAID_TOKEN_NOT_CONFIGURED"}},
        dict(base_config,
             web_allowed_domains=WHITELIST,
             web_search_endpoint="http://127.0.0.1:%d/search" % port))
    outage_result = outage["payload"].get("result", {}) \
        if outage["exit"] == 0 else {}
    gaps = outage_result.get("gaps") or []
    checks.add(
        "S6C_http_error_named_not_fabricated",
        outage["exit"] == 0
        and outage_result.get("candidates") == []
        and outage_result.get("verified") == []
        and len(gaps) == 1 and gaps[0].get("reason") == "web_status_500",
        "检索端点 500 → 具名缺口 web_status_500（非 2xx 具名不入账）；"
        "candidates/verified 恒空零伪造")
    _SyntheticWeb.mode = "normal"
    sha_after = {
        "commercial_law_mcp.py": sha256_file(commercial_tool),
        "lccc_consumer.py": sha256_file(
            os.path.join(codices_repo, "lccc_consumer.py")),
        "statute_validity.py": sha256_file(str(STATUTE_VALIDITY)),
        "legal_entry.py": sha256_file(str(LEGAL_ENTRY)),
    }
    stable = all(sha_after[key] == value
                 for key, value in sha_before.items())
    checks.add(
        "S6D_frozen_faces_byte_stable_through_run",
        stable,
        "冻结面全程字节稳定（sha256 前后相等）：%s；P11 PROVIDERS 零引用"
        "（web_fallback AST 零 commercial 引用，S4B 亲证）"
        % ";".join("%s=%s…" % (key, value[:8])
                   for key, value in sorted(sha_after.items())))


def run_profile(args, profile: str, base_config: dict,
                commercial_tool: str, codices_repo: str) -> int:
    """单 profile 全量 20 检＋证据落盘。"""
    checks = Checks()
    sha_before = {
        "commercial_law_mcp.py": sha256_file(commercial_tool),
        "lccc_consumer.py": sha256_file(
            os.path.join(codices_repo, "lccc_consumer.py")),
        "statute_validity.py": sha256_file(str(STATUTE_VALIDITY)),
        "legal_entry.py": sha256_file(str(LEGAL_ENTRY)),
    }
    _SyntheticWeb.received = []
    _SyntheticWeb.served = {}
    _SyntheticWeb.mode = "normal"
    server, thread, port = _start_server()
    try:
        section_s1(checks, base_config, commercial_tool, codices_repo)
        section_s2(checks, port)
        retrieve_result = section_s3(checks, port, base_config)
        section_s4(checks, port, retrieve_result, base_config)
        section_s5(checks, port, base_config)
        section_s6(checks, port, base_config, commercial_tool,
                   codices_repo, sha_before)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO_ROOT)).stdout.strip()
    request_surface = [r for r in _SyntheticWeb.received]
    evidence = {
        "run_date": RUN_DATE,
        "profile": profile,
        "command": "python -X utf8 " + " ".join(sys.argv),
        "cwd": str(REPO_ROOT),
        "subject_commit": commit,
        "frozen_faces": sha_before,
        "authority_row": "06 V7-74 F74（v1.5；owner=product+codices；B4）"
                         "acceptance=网页结果URL与原文真实核验，web来源声明"
                         "明确，禁编URL；preserved=随 F64 降级链末端开"
                         "（W4-U41 F64-v1.5 2026-10-21 VERIFIED 后接末端）",
        "synthetic_materials": {
            "quote": SYNTH_QUOTE,
            "endpoint": "127.0.0.1 回环合成检索端点＋合成法源页（零真实外联）",
            "server_requests_seen": request_surface,
        },
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    for root in [part.strip() for part in args.evidence_roots.split(",")
                 if part.strip()]:
        out_dir = REPO_ROOT / root / profile
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "f74-web-fallback-recon.json").write_text(
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
    parser.add_argument("--codices-repo", default=DEFAULT_CODICES_REPO)
    parser.add_argument("--formal-root", default=DEFAULT_FORMAL_ROOT)
    parser.add_argument("--commercial-tool", default=DEFAULT_COMMERCIAL_TOOL)
    parser.add_argument("--evidence-roots", default="evidence/F74")
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]

    lccc_path = os.path.join(args.codices_repo, "lccc_consumer.py")
    if not os.path.isfile(lccc_path):
        print("FATAL: lccc_consumer.py 不在 %s（E22 冻结面）" % args.codices_repo)
        return 2
    if sha256_file(lccc_path) != LCCC_SHA256:
        print("FATAL: 冻结面 lccc_consumer.py sha256 漂移")
        return 2
    if not os.path.isfile(args.commercial_tool):
        print("FATAL: commercial_law_mcp.py 不在 %s（P11）"
              % args.commercial_tool)
        return 2
    if sha256_file(args.commercial_tool) != P11_SHA256:
        print("FATAL: P11 commercial_law_mcp.py sha256 漂移")
        return 2

    base_config = {
        "codices_import_path": args.codices_repo,
        "codices_formal_root": args.formal_root,
    }
    codes = [run_profile(args, profile, base_config, args.commercial_tool,
                         args.codices_repo)
             for profile in profiles]
    return 0 if all(code == 0 for code in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
