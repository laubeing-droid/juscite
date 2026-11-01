# -*- coding: utf-8 -*-
"""F64(v1)/F69 验收对账（PENDING_OWNER 版，工单 W2a-U13）。

时点定位／状态／替代链／unknown fail-closed／本地优先降级链 v1 面，
全部断言走真产品入口（implementation/python/legal_entry.py 子进程径），
法源消费经 W2a-U12 冻结公开面 lccc_consumer（E22 freeze v1.0）。

分段：
  S1 时点定位与状态（F69）：真实本地数据锚点逐条过引证闸，行内事实由
     正式表独立复核（不回读本地面自证）；被废除检索到也不许引＝横切不变量。
  S2 替代链（F69）：legal_relations 空表落地核对＋替代恒 unknown 不编造。
  S3 本地优先降级链 v1 面（F64）：链冻结 本地→付费→web；本地段唯一执行；
     付费/web 具名声明缺口（实测归 F64-v1.5/B4）；零 URL 披露；产品面
     statute_validity 静态零网络零写入；P11 token 环境变量名镜像零漂移。
  S4 P11 付费 consumer 负测：未配置 token→具名缺口（构造即拒，不可能
     自采）；URL 只出自冻结 PROVIDERS 常量（构造级＋AST 静态级双验）；
     v1 产品面不引用 P11。
  S5 桥 fail-closed：未配置/未知方法 exit 3 具名 NOT_CONNECTED。
  S6 付费通道 v1.5 段（W4-U41，裁决#8-12 负测先行）：P11 客户端真建
     （合成 token 在位→真 McpHttpClient 非桩）；合成 mock 端点（127.0.0.1
     回环）请求面真实可达——真实 HTTP 往返 tools/call、两 provider 各用
     真实工具名；错误封皮/isError 具名失败不造假；codices 冻结面盘上
     字节全程不动＋PROVIDERS 内存覆盖用毕即还原。绝不真打付费服务，
     真授权后补。
  S7 web 兜底 v1.5 段（W4-U41）：web-verified 声明机制分账断言——
     verification_basis=web_verified 与数据库核验（local/paid）异账；
     声明键集与数据库核验签名键零交；取证事实缺/畸形/URL scheme 白名单
     外→具名拒不编造；AST：declare_web_verified 函数体零本地冻结面/
     P11/网络引用（web 声明路径与数据库核验结构性隔离）。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f64_f69_validity_recon.py --profile desktop
  python -X utf8 tools/PENDING_OWNER_f64_f69_validity_recon.py --profile desktop --profile selfhost
  [--formal-root <codices 正式目录>] [--codices-repo <含 lccc_consumer.py 目录>]
  [--commercial-tool <commercial_law_mcp.py>]
  [--evidence-roots "evidence/F64,evidence/F69"]

--profile 可重复（action=append，同目录 e20/f107_f108/e19 工具同款）；
  重复即逐 profile 依序全量跑各 36 检（v1 段 28 检断言逻辑与 W2a-U13
  版逐条不变＋v1.5 段 8 检 W4-U41）并各写证据；缺省=desktop。
exit 0＝全部断言过；证据 JSON 写 <root>/<profile>/ 各一份。
只读消费，不写正式目录；唯一网络面＝S6 的 127.0.0.1 回环合成 mock
端点（不真打付费服务）。

（W3-U27 改口：原实现 --profile 单值后写覆盖，工单验收命令
「--profile desktop --profile selfhost」会静默只跑 selfhost；
本改动仅扩 CLI 为 append＋逐 profile 循环，28 检断言逻辑零改动。）
（W4-U41 扩 v1.5 段：S1-S5 断言逻辑零改动；新增 S6/S7 各 4 检。）
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

csv.field_size_limit(10 ** 9)

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"

DEFAULT_FORMAL_ROOT = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices"
)
DEFAULT_CODICES_REPO = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u12-e22"
)
DEFAULT_COMMERCIAL_TOOL = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\tools\commercial_law_mcp.py"
)

LCCC_SHA256 = "eb11ee5be548dbfed6e8b3f0052d11f28abb0cd010e1ef6236fb1e2fecf245d9"

# 真实数据锚点（E22 基线实测在盘；行内事实运行时独立复核，漂移即 FAIL）
ANCHORS = {
    "CUR": "1.2.156.3005.6-0100000000100120210820009100000",  # 个保法 2021 SXX=01
    "ABO_SH": "1.2.156.3005.6-1300000000635020200413000600000",  # 已废止且有失效日
    "ABO_NOSH": "1.2.156.3005.6-0100000000100020171104000100000",  # 已废止无失效日
    "AMD": "1.2.156.3005.6-0100000000100120081227000400000",  # 专利法 2008 已修改
    "NTY": "1.2.156.3005.6-0100000000100120260626002300030",  # 尚未施行 SXRQ 未来
    "LAG": "1.2.156.3005.6-0200000000300020260810000000030",  # SXX=02 施行日已过
    "NCODE": "1.2.156.3005.6-1700000000339220260722035300000",  # 无 GB 文件码
}

NETWORK_MODULES = {
    "urllib", "urllib.request", "urllib.parse", "requests", "socket",
    "http", "http.client", "httpx", "aiohttp",
}
WRITE_MODES = {"w", "a", "x", "w+", "a+", "x+", "r+", "+"}
SUPERSEDED_SXX = {"03", "04", "05"}


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


def sha256_file(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_document_rows(formal_root: str) -> dict:
    """正式表独立读取（锚点行内事实复核用；消费断言仍走冻结面）。"""
    rows: dict = {}
    path = os.path.join(formal_root, "legal_documents.csv")
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.setdefault(row["WJBS"], row)
    return rows


def call_entry(method: str, args: dict, config: dict,
               scrub_tokens: bool = True) -> dict:
    """真产品入口子进程调用；返回 {exit, stdout_json}。"""
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
        if scrub_tokens:
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


def expect_gate(checks: Checks, check_id: str, response: dict, decision: str,
                code_prefix: str, extra: dict | None = None) -> dict:
    payload = response["payload"]
    ok = (
        response["exit"] == 0
        and payload.get("status") == "OWNER_RESPONSE"
        and payload["result"]["decision"] == decision
        and payload["result"]["code"].startswith(code_prefix)
    )
    detail = "exit=%s status=%s decision=%s code=%s" % (
        response["exit"], payload.get("status"),
        payload.get("result", {}).get("decision"),
        payload.get("result", {}).get("code"))
    if ok and extra:
        for key, want in extra.items():
            got = payload["result"].get(key)
            ok = ok and got == want
            detail += " %s=%r(want %r)" % (key, got, want)
    checks.add(check_id, ok, detail)
    return payload.get("result", {})


def no_http(value) -> bool:
    if isinstance(value, str):
        return "http://" not in value and "https://" not in value
    if isinstance(value, dict):
        return all(no_http(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(no_http(v) for v in value)
    return True


def static_scan_module(path: str, forbid_commercial: bool) -> list:
    """AST 静态扫描：零网络 import、零写模式 open、（可选）零 P11 引用。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    violations: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            names = []
        for name in names:
            if name in NETWORK_MODULES or name.split(".")[0] in {
                    n.split(".")[0] for n in NETWORK_MODULES}:
                violations.append("network_import:" + name)
            if forbid_commercial and "commercial" in name:
                violations.append("commercial_import:" + name)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "open":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) \
                    and node.args[1].value in WRITE_MODES:
                violations.append("write_mode_open")
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant) \
                        and kw.value.value in WRITE_MODES:
                    violations.append("write_mode_open")
    return violations


def url_literals_confined_to_providers(path: str) -> tuple:
    """commercial_law_mcp.py 禁编 URL：全部 http(s) 字面量只许出现在
    PROVIDERS 字典字面量内；且无 f-string/format/% 动态拼 URL。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    provider_urls: set = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PROVIDERS"
                for t in node.targets):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                        and sub.value.startswith(("http://", "https://")):
                    provider_urls.add(sub.value)
    offenders: list = []

    def _joined_literal(node: ast.JoinedStr) -> str:
        return "".join(part.value for part in node.values
                       if isinstance(part, ast.Constant))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and node.value.startswith(("http://", "https://")) \
                and node.value not in provider_urls:
            offenders.append("url_literal_outside_PROVIDERS:" + node.value)
        if isinstance(node, ast.JoinedStr) and "http" in _joined_literal(node):
            offenders.append("fstring_building_url")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "format" \
                and isinstance(node.func.value, ast.Constant) \
                and isinstance(node.func.value.value, str) \
                and "http" in node.func.value.value:
            offenders.append("format_building_url")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) \
                and isinstance(node.left, ast.Constant) \
                and isinstance(node.left.value, str) \
                and "http" in node.left.value:
            offenders.append("percent_building_url")
    return sorted(provider_urls), offenders


def section_s1(checks: Checks, rows: dict, config: dict, results: list) -> None:
    cur_row = rows.get(ANCHORS["CUR"], {})
    sxrq = cur_row.get("SXRQ", "")
    checks.add("S1_anchor_row_facts",
               cur_row.get("SXX") == "01" and bool(sxrq)
               and rows.get(ANCHORS["ABO_SH"], {}).get("SXX") == "04"
               and bool(rows.get(ANCHORS["ABO_SH"], {}).get("SHXRQ"))
               and rows.get(ANCHORS["ABO_NOSH"], {}).get("SXX") == "04"
               and not rows.get(ANCHORS["ABO_NOSH"], {}).get("SHXRQ")
               and rows.get(ANCHORS["AMD"], {}).get("SXX") == "03"
               and rows.get(ANCHORS["NTY"], {}).get("SXX") == "02"
               and rows.get(ANCHORS["NTY"], {}).get("SXRQ", "") > RUN_DATE
               and rows.get(ANCHORS["LAG"], {}).get("SXX") == "02"
               and rows.get(ANCHORS["LAG"], {}).get("SXRQ", "99991231") <= RUN_DATE
               and rows.get(ANCHORS["NCODE"], {}).get("DE_01001", "") == "",
               "锚点行内事实复核：CUR SXX=01 SXRQ=%s；ABO_SH 04+SHXRQ；"
               "ABO_NOSH 04 无 SHXRQ；AMD 03；NTY 02 SXRQ=%s>RUN；LAG 02 已到；"
               "NCODE 无码" % (sxrq, rows.get(ANCHORS["NTY"], {}).get("SXRQ")))

    gate = lambda wjbs, as_of: call_entry(
        "statute.citation_gate", {"wjbs": wjbs, "as_of": as_of}, config)
    resolve = lambda wjbs, as_of: call_entry(
        "statute.resolve", {"wjbs": wjbs, "as_of": as_of}, config)

    # R1 现行法在适用时点可引（时点定位正向）
    r1 = expect_gate(checks, "S1_R1_current_citable_at_as_of",
                     gate(ANCHORS["CUR"], RUN_DATE), "ALLOWED",
                     "CURRENT_IN_FORCE_CITABLE",
                     {"status_label": "有效", "in_force_window": "yes",
                      "signs_current": True, "replacement": "unknown"})
    results.append(r1)
    # R2 施行日前一天→BLOCKED（时点真的移动判定）
    before = "%08d" % (int(sxrq) - 1)
    expect_gate(checks, "S1_R2_before_effective_blocked",
                gate(ANCHORS["CUR"], before), "BLOCKED",
                "NOT_YET_IN_FORCE_AT_AS_OF",
                {"in_force_window": "no", "signs_current": False})
    # R3 施行日当天→ALLOWED（施行日当天生效）
    expect_gate(checks, "S1_R3_effective_day_citable",
                gate(ANCHORS["CUR"], sxrq), "ALLOWED",
                "CURRENT_IN_FORCE_CITABLE", {"in_force_window": "yes"})
    # R4 已废止（有失效日，窗口=no）→不许引
    r4 = expect_gate(checks, "S1_R4_abolished_with_expiry_not_citable",
                     gate(ANCHORS["ABO_SH"], RUN_DATE), "BLOCKED",
                     "ABOLISHED_NOT_CITABLE",
                     {"in_force_window": "no", "signs_current": False})
    results.append(r4)
    # R5 已废止（无失效日，窗口不可定）→仍不许引且不签现行
    r5 = expect_gate(checks, "S1_R5_abolished_without_expiry_not_citable",
                     gate(ANCHORS["ABO_NOSH"], RUN_DATE), "BLOCKED",
                     "ABOLISHED_NOT_CITABLE",
                     {"in_force_window": "unknown", "signs_current": False})
    results.append(r5)
    # R6 已修改→不许引＋替代 unknown
    r6 = expect_gate(checks, "S1_R6_amended_not_citable_replacement_unknown",
                     gate(ANCHORS["AMD"], RUN_DATE), "BLOCKED",
                     "SUPERSEDED_NOT_CITABLE",
                     {"replacement": "unknown"})
    results.append(r6)
    # R7 尚未施行（施行日未到）→BLOCKED
    expect_gate(checks, "S1_R7_not_yet_in_force_blocked",
                gate(ANCHORS["NTY"], RUN_DATE), "BLOCKED",
                "NOT_YET_IN_FORCE_AT_AS_OF", {"in_force_window": "no"})
    # R8 SXX=02 施行日已过（数据滞后冲突）→UNKNOWN fail-closed
    r8 = expect_gate(checks, "S1_R8_status_window_conflict_unknown",
                     gate(ANCHORS["LAG"], RUN_DATE), "UNKNOWN",
                     "STATUS_WINDOW_CONFLICT_FAIL_CLOSED",
                     {"signs_current": False})
    results.append(r8)
    # R9 缺 GB 编码→UNKNOWN 不签现行
    r9 = expect_gate(checks, "S1_R9_missing_code_unknown_fail_closed",
                     gate(ANCHORS["NCODE"], RUN_DATE), "UNKNOWN",
                     "FACE_STRUCTURAL_GAP_FAIL_CLOSED:NO_GB_FILE_CODE_SCOPE_GAP",
                     {"signs_current": False})
    results.append(r9)
    # R10 缺适用时点（as_of）→UNKNOWN 不签现行
    r10 = expect_gate(checks, "S1_R10_missing_as_of_unknown_fail_closed",
                      call_entry("statute.citation_gate",
                                 {"wjbs": ANCHORS["CUR"]}, config),
                      "UNKNOWN", "AS_OF_REQUIRED_FAIL_CLOSED",
                      {"signs_current": False})
    results.append(r10)
    # R11 畸形 WJBS / R12 未命中 →UNKNOWN 具名
    expect_gate(checks, "S1_R11_malformed_wjbs_unknown",
                gate("1.2.156.3005.6-000", RUN_DATE), "UNKNOWN",
                "NOT_FOUND_UNKNOWN:INVALID_WJBS_FORMAT")
    expect_gate(checks, "S1_R12_not_found_unknown",
                gate("1.2.156.3005.6-0100999999999920260101000000000",
                     RUN_DATE),
                "UNKNOWN", "NOT_FOUND_UNKNOWN:NOT_FOUND_IN_LEGAL_DOCUMENTS")
    # R13 横切不变量：被废除（03/04/05）检索到也不许引
    superseded_ok = all(
        item["decision"] in ("BLOCKED", "UNKNOWN")
        for item in results if item.get("status_label") in ("已修改", "已废止", "已失效")
    ) and any(item["code"] == "ABOLISHED_NOT_CITABLE" for item in results)
    checks.add("S1_R13_superseded_never_citable_invariant", superseded_ok,
               "已修改/已废止锚点 decision 全部非 ALLOWED 且已废止命中 "
               "ABOLISHED_NOT_CITABLE（被废除检索到也不许引）")
    # R14 resolve 面同步：现行法 resolve 带 as_of 时 timepoint_positioned
    resolve_resp = resolve(ANCHORS["CUR"], RUN_DATE)
    payload = resolve_resp["payload"]
    checks.add(
        "S1_R14_resolve_timepoint_flag",
        resolve_resp["exit"] == 0
        and payload["result"]["timepoint_positioned"] is True
        and payload["result"]["signs_current"] is True,
        "resolve as_of=%s → timepoint_positioned=True signs_current=True"
        % RUN_DATE)


def section_s2(checks: Checks, formal_root: str, gate_results: list) -> None:
    path = os.path.join(formal_root, "legal_relations.csv")
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        relations = [row for row in csv.DictReader(handle)]
    checks.add("S2A_legal_relations_empty_grounded", len(relations) == 0,
               "legal_relations.csv 数据行=%d（空表→替代链数据缺，E22 冻结面"
               "replacement 恒 unknown 的落地事实）" % len(relations))
    superseded = [item for item in gate_results
                  if item.get("status_label") in ("已修改", "已废止", "已失效")]
    checks.add(
        "S2B_replacement_always_unknown_never_fabricated",
        bool(superseded)
        and all(item.get("replacement") == "unknown" for item in superseded)
        and all("legal_relations" in (item.get("replacement_reason") or "")
                for item in superseded),
        "被替代锚点 %d 个 replacement 全部=unknown 且理由指向 legal_relations "
        "空表，无编造替代版本" % len(superseded))


def section_s3(checks: Checks, config: dict) -> dict:
    response = call_entry("statute.source_strategy", {}, config)
    payload = response["payload"]
    result = payload.get("result", {}) if response["exit"] == 0 else {}
    segments = result.get("segments", {})
    checks.add(
        "S3A_chain_frozen_local_executed_paid_web_declared",
        response["exit"] == 0 and result.get("chain") == ["local", "paid", "web"]
        and result.get("frozen") is True and result.get("version") == "v1"
        and segments.get("local", {}).get("state") == "executed"
        and "declared_gap_pending_F64-v1.5(B4)" in
        segments.get("paid", {}).get("state", "")
        and "declared_gap_pending_F64-v1.5(B4)" in
        segments.get("web", {}).get("state", ""),
        "chain=%s frozen=%s local=%s paid=%s web=%s（实测归 F64-v1.5/B4）"
        % (result.get("chain"), result.get("frozen"),
           segments.get("local", {}).get("state"),
           segments.get("paid", {}).get("state"),
           segments.get("web", {}).get("state")))
    paid_gap = segments.get("paid", {}).get("gap", {})
    checks.add(
        "S3B_paid_gap_named_no_self_collection",
        paid_gap.get("reason") == "PAID_TOKEN_NOT_CONFIGURED"
        and paid_gap.get("self_collection") == "none"
        and set(paid_gap.get("detail", "").split(";")) ==
        {"YUANDIAN_MCP_TOKEN", "PKULAW_MCP_TOKEN"},
        "未配置 token→具名缺口 %s（%s），不自采" % (
            paid_gap.get("reason"), paid_gap.get("detail")))
    miss = call_entry("statute.resolve",
                      {"wjbs": "1.2.156.3005.6-000", "as_of": RUN_DATE},
                      config)
    miss_result = miss["payload"].get("result", {})
    block = miss_result.get("degradation", {})
    checks.add(
        "S3C_local_miss_declares_gap_no_escalation",
        miss["exit"] == 0 and block.get("escalated") is False
        and block.get("gap_declared") is True
        and any("INVALID_WJBS_FORMAT" in reason
                for reason in block.get("gap_reasons", []))
        and "declared_gap_pending_F64-v1.5(B4)" in
        block.get("segments", {}).get("paid", "")
        and "declared_gap_pending_F64-v1.5(B4)" in
        block.get("segments", {}).get("web", ""),
        "本地未命中→具名缺口 %s；escalated=False，付费/web 仍声明缺口未跳级"
        % block.get("gap_reasons"))
    checks.add(
        "S3D_zero_url_disclosure",
        no_http(result) and no_http(miss_result)
        and no_http(call_entry("statute.resolve",
                               {"wjbs": ANCHORS["CUR"], "as_of": RUN_DATE},
                               config)["payload"].get("result", {})),
        "strategy/resolve(命中)/resolve(未命中) 三响应零 http(s) 披露")
    violations = static_scan_module(
        str(REPO_ROOT / "implementation" / "python" / "statute_validity.py"),
        forbid_commercial=True)
    checks.add("S3E_product_module_zero_network_zero_write",
               not violations, "AST 扫描 statute_validity.py：%s"
               % (";".join(violations) or "零网络 import、零写模式 open、零 P11 引用"))
    return result


def section_s4(checks: Checks, commercial_tool: str) -> None:
    spec = importlib.util.spec_from_file_location(
        "commercial_law_mcp_recon", commercial_tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    providers = {
        name: cfg["token_env"] for name, cfg in module.PROVIDERS.items()}
    saved = {var: os.environ.pop(var, None) for var in providers.values()}
    try:
        errors = {}
        for name in module.PROVIDERS:
            try:
                module.McpHttpClient(name)
                errors[name] = "NO_ERROR_RAISED"
            except RuntimeError as exc:
                errors[name] = str(exc)
        named_ok = all(
            errors[name] == "missing environment variable: %s" % env
            for name, env in providers.items())
        checks.add(
            "S4A_unconfigured_token_named_gap_no_client",
            named_ok,
            "未配置 token 构造即拒：%s（客户端未建→不可能自采）" % errors)
    finally:
        for var, value in saved.items():
            if value is not None:
                os.environ[var] = value
    fake = "synthetic-f64-recon-token"
    urls = {}
    saved = {}
    try:
        for name, env in providers.items():
            saved[env] = os.environ.get(env)
            os.environ[env] = fake
        for name in module.PROVIDERS:
            client = module.McpHttpClient(name)  # 构造即止，绝不 call
            urls[name] = client.url
        frozen_urls = {name: module.PROVIDERS[name]["url"]
                       for name in module.PROVIDERS}
        checks.add(
            "S4B_client_url_provenance_frozen_providers_only",
            urls == frozen_urls,
            "构造级：client.url 全部出自冻结 PROVIDERS 常量 %s（不发任何请求）"
            % urls)
    finally:
        for env, value in saved.items():
            if value is None:
                os.environ.pop(env, None)
            else:
                os.environ[env] = value
    provider_urls, offenders = url_literals_confined_to_providers(
        commercial_tool)
    checks.add(
        "S4C_no_fabricated_url_static",
        bool(provider_urls) and not offenders,
        "AST：http(s) 字面量 %d 个全部位于 PROVIDERS 字典内；违规=%s"
        % (len(provider_urls), ";".join(offenders) or "无"))
    # 产品面镜像零漂移（token 环境变量名与真实 PROVIDERS 一致）
    python_dir = str(REPO_ROOT / "implementation" / "python")
    if python_dir not in sys.path:
        sys.path.insert(0, python_dir)
    import statute_validity as product_module  # noqa: E402
    checks.add(
        "S4D_paid_env_mirror_zero_drift",
        set(product_module.PAID_TOKEN_ENV_VARS) == set(providers.values()),
        "产品面镜像 %s == P11 真实 PROVIDERS token_env %s"
        % (sorted(product_module.PAID_TOKEN_ENV_VARS),
           sorted(providers.values())))


class _SyntheticMcpMock(BaseHTTPRequestHandler):
    """合成 mock MCP 端点（S6 专用）：只绑 127.0.0.1 回环，记录请求面
    事实，按 mode 回应（ok/iserror/error）。绝不外联、不真打付费服务。"""
    received: list = []
    mode = "ok"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            request = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            request = {}
        params = request.get("params") or {}
        _SyntheticMcpMock.received.append({
            "path": self.path,
            "authorization": self.headers.get("Authorization", ""),
            "jsonrpc": request.get("jsonrpc"),
            "method": request.get("method"),
            "tool": params.get("name"),
            "arguments": params.get("arguments"),
        })
        if _SyntheticMcpMock.mode == "ok":
            body = {"jsonrpc": "2.0", "id": request.get("id"), "result": {
                "content": [{"type": "text", "text": json.dumps(
                    {"synthetic": True, "echo_tool": params.get("name")},
                    ensure_ascii=False)}],
                "isError": False}}
        elif _SyntheticMcpMock.mode == "iserror":
            body = {"jsonrpc": "2.0", "id": request.get("id"), "result": {
                "content": [], "isError": True,
                "message": "synthetic_mock_tool_error"}}
        else:
            body = {"jsonrpc": "2.0", "id": request.get("id"),
                    "error": {"code": -32000,
                              "message": "synthetic_mock_auth_denied"}}
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass


def _with_synthetic_tokens(module, token: str):
    """上下文工厂：配置/还原合成测试 token（只进本进程 env，绝不外发）。"""
    class _Guard:
        def __enter__(self):
            self.saved = {}
            for cfg in module.PROVIDERS.values():
                env = cfg["token_env"]
                self.saved[env] = os.environ.get(env)
                os.environ[env] = token
            return self.saved

        def __exit__(self, *exc):
            for env, value in self.saved.items():
                if value is None:
                    os.environ.pop(env, None)
                else:
                    os.environ[env] = value
            return False
    return _Guard()


def section_s6(checks: Checks, commercial_tool: str) -> None:
    """F64 v1.5 付费通道段（裁决#8-12 负测先行，真授权后补）。"""
    sha_before = sha256_file(commercial_tool)
    spec = importlib.util.spec_from_file_location(
        "commercial_law_mcp_recon_v15", commercial_tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    synthetic_token = "synthetic-f64-v15-token"

    with _with_synthetic_tokens(module, synthetic_token):
        clients = {}
        shapes = {}
        ok = True
        for name in module.PROVIDERS:
            client = module.McpHttpClient(name)
            clients[name] = client
            shape = (
                type(client) is module.McpHttpClient
                and client.url == module.PROVIDERS[name]["url"]
                and client.headers.get("Authorization")
                == "Bearer " + synthetic_token
                and client.timeout > 0
                and client.opener is not None)
            shapes[name] = shape
            ok = ok and shape
        checks.add(
            "S6A_paid_client_really_constructed", ok,
            "P11 客户端真建×%d（type=McpHttpClient 非桩；url 出自冻结 "
            "PROVIDERS 常量；合成 token 进 Authorization 头＝请求面凭证；"
            "timeout>0）：%s" % (len(clients), shapes))

    server = ThreadingHTTPServer(("127.0.0.1", 0), _SyntheticMcpMock)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_urls = {name: module.PROVIDERS[name]["url"]
                     for name in module.PROVIDERS}
    _SyntheticMcpMock.received = []
    _SyntheticMcpMock.mode = "ok"
    try:
        # 内存内把 PROVIDERS url 覆盖到合成 mock 端点（盘上冻结面零触碰，
        # S6D 复验）；构造级复证：client.url 全出自（覆盖后的）PROVIDERS。
        for name in module.PROVIDERS:
            module.PROVIDERS[name]["url"] = "http://127.0.0.1:%d/mcp" % port
        with _with_synthetic_tokens(module, synthetic_token):
            tools = {"YUANDIAN": "yuandian_rh_fg_search",
                     "PKULAW": "search_article"}
            providers_by_tool = {tool: name for name, tool in tools.items()}
            parsed_ok = True
            for name, tool in tools.items():
                result = module.McpHttpClient(name).call(
                    tool, {"synthetic_probe": name})
                parsed = json.loads(result["content"][0]["text"])
                parsed_ok = parsed_ok and (
                    parsed.get("synthetic") is True
                    and parsed.get("echo_tool") == tool)
            requests_seen = list(_SyntheticMcpMock.received)
            surface_ok = (
                parsed_ok and len(requests_seen) == len(tools)
                and {req["tool"] for req in requests_seen}
                == set(tools.values())
                and all(req["path"] == "/mcp" for req in requests_seen)
                and all(req["authorization"] == "Bearer " + synthetic_token
                        for req in requests_seen)
                and all(req["jsonrpc"] == "2.0"
                        and req["method"] == "tools/call"
                        for req in requests_seen)
                and all(req["arguments"]
                        == {"synthetic_probe": providers_by_tool[req["tool"]]}
                        for req in requests_seen))
            checks.add(
                "S6B_paid_request_surface_reachable_synthetic_mock",
                surface_ok,
                "合成 mock 端点 127.0.0.1:%d 请求面真实可达：%d 次真实 HTTP "
                "POST 往返，两 provider 各用 P11 真实工具名 %s，Bearer 合成 "
                "token、JSON-RPC 2.0 tools/call 封皮与 arguments 逐项对上，"
                "响应 result 解析回读（绝不真打付费服务）"
                % (port, len(requests_seen), sorted(tools.values())))
            # 负测：错误封皮/isError 一律具名 RuntimeError，绝不假成功。
            failures = {}
            for mode, marker in (("error", "synthetic_mock_auth_denied"),
                                 ("iserror", "synthetic_mock_tool_error")):
                _SyntheticMcpMock.mode = mode
                try:
                    module.McpHttpClient("YUANDIAN").call(
                        "yuandian_rh_fg_search", {})
                    failures[mode] = "NO_ERROR_RAISED"
                except RuntimeError as exc:
                    failures[mode] = str(exc)
                    if marker not in str(exc):
                        failures[mode] = "wrong_message:" + str(exc)
            _SyntheticMcpMock.mode = "ok"
            checks.add(
                "S6C_paid_failure_named_never_fabricated",
                all(marker in failures[mode]
                    for mode, marker in (("error", "synthetic_mock_auth_denied"),
                                         ("iserror", "synthetic_mock_tool_error"))),
                "错误封皮/isError 均具名 RuntimeError 不造假：%s" % failures)
    finally:
        for name in module.PROVIDERS:
            module.PROVIDERS[name]["url"] = original_urls[name]
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    restored = all(module.PROVIDERS[name]["url"] == original_urls[name]
                   for name in module.PROVIDERS)
    sha_after = sha256_file(commercial_tool)
    checks.add(
        "S6D_codices_frozen_face_bytes_untouched",
        restored and sha_before == sha_after,
        "codices 冻结面盘上字节全程不动（sha256 %s… 前后相等）＋PROVIDERS "
        "内存覆盖用毕即还原（client.url 复指冻结常量 %s）"
        % (sha_before[:8], sorted(original_urls.values())))


def web_declaration_ast_isolation(path: str) -> list:
    """AST：declare_web_verified 函数体零本地冻结面/P11/网络引用——
    web 声明路径与数据库核验、付费通道结构性隔离（永不冒数据库核验）。"""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    forbidden = {"_lccc", "lccc_consumer", "LOCAL_FACE_NAME", "resolve",
                 "citation_gate", "McpHttpClient", "PROVIDERS", "urlopen",
                 "urllib", "requests", "httpx", "aiohttp", "socket", "http"}
    offenders: list = []
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) \
                and node.name == "declare_web_verified":
            found = True
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id in forbidden:
                    offenders.append("name:" + sub.id)
                if isinstance(sub, ast.Attribute) and sub.attr in forbidden:
                    offenders.append("attr:" + sub.attr)
            break
    if not found:
        offenders.append("declare_web_verified_not_found")
    return offenders


def section_s7(checks: Checks, config: dict, commercial_tool: str) -> None:
    """F64 v1.5 web 兜底段：web-verified ≠ verified 分账。"""
    if str(REPO_ROOT / "implementation" / "python") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    import statute_validity as product_module  # noqa: E402
    evidence = {
        "source_url": "https://mock-web.invalid/synthetic/statute-page",
        "content_sha256": hashlib.sha256(
            b"synthetic web evidence w4-u41").hexdigest(),
        "retrieved_utc": "2026-10-21T00:00:00+00:00",
    }
    resp = call_entry("statute.web_declaration", dict(evidence), config)
    result = resp["payload"].get("result", {}) if resp["exit"] == 0 else {}
    spec = importlib.util.spec_from_file_location(
        "commercial_law_mcp_recon_s7", commercial_tool)
    p11 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(p11)
    p11_source_types = {"%s_VERIFIED" % name for name in p11.PROVIDERS}
    db_bases = {product_module.VERIFICATION_BASIS_LOCAL_DB,
                product_module.VERIFICATION_BASIS_PAID_DB}
    ok = (
        resp["exit"] == 0
        and result.get("verification_basis")
        == product_module.VERIFICATION_BASIS_WEB
        and result.get("signs_current") is False
        and result.get("verification_basis") not in db_bases
        and result.get("verification_basis") not in p11_source_types
        and result.get("source_url") == evidence["source_url"]
        and result.get("content_sha256") == evidence["content_sha256"])
    checks.add(
        "S7A_web_declaration_separate_ledger", ok,
        "web 兜底声明分账：verification_basis=%s ∉ 数据库核验账 %s ∉ P11 "
        "注册表 source_type %s；signs_current=False（web 来源不签现行）；"
        "取证 URL/sha256 原样转录"
        % (result.get("verification_basis"), sorted(db_bases),
           sorted(p11_source_types)))
    db_keys = set(product_module.DB_SIGNATURE_KEYS)
    overlap = sorted(db_keys & set(result))
    checks.add(
        "S7B_web_declaration_zero_db_signature_keys",
        bool(db_keys) and resp["exit"] == 0 and result and not overlap,
        "声明键集 %s 与数据库核验签名键 %s 零交（P11 注册表行 "
        "source_type/provider_record_id/provider_url/provider＋本地冻结面取文签 "
        "face_sha256/lccc_face）；越界=%s" % (
            sorted(result), sorted(db_keys), overlap or "无"))
    negatives = [
        ("missing_source_url",
         {k: v for k, v in evidence.items() if k != "source_url"},
         "web_declaration_evidence_missing:source_url"),
        ("missing_content_sha256",
         {k: v for k, v in evidence.items() if k != "content_sha256"},
         "web_declaration_evidence_missing:content_sha256"),
        ("missing_retrieved_utc",
         {k: v for k, v in evidence.items() if k != "retrieved_utc"},
         "web_declaration_evidence_missing:retrieved_utc"),
        ("url_scheme_not_allowed",
         dict(evidence, source_url="ftp://mock-web.invalid/x"),
         "web_declaration_url_scheme_not_allowed"),
        ("content_sha256_malformed",
         dict(evidence, content_sha256="nothex"),
         "web_declaration_content_sha256_malformed"),
    ]
    codes = {}
    all_ok = True
    for label, args, expected in negatives:
        negative = call_entry("statute.web_declaration", args, config)
        got = str(negative["payload"].get("code", ""))
        codes[label] = got
        all_ok = all_ok and (
            negative["exit"] == 3
            and negative["payload"].get("status") == "NOT_CONNECTED"
            and got == expected)
    checks.add(
        "S7C_web_declaration_missing_evidence_named_reject", all_ok,
        "取证事实缺任一/scheme 白名单外/sha 畸形→exit 3 NOT_CONNECTED 具名"
        "拒（不编造声明不编 URL）：%s" % codes)
    offenders = web_declaration_ast_isolation(
        str(REPO_ROOT / "implementation" / "python" / "statute_validity.py"))
    checks.add(
        "S7D_web_declaration_ast_isolated_from_db_face", not offenders,
        "AST：declare_web_verified 函数体零本地冻结面/P11/网络引用——"
        "web 声明路径与数据库核验结构性隔离；违规=%s"
        % (";".join(offenders) or "无"))


def section_s5(checks: Checks, codices_repo: str) -> None:
    bad = call_entry("statute.resolve",
                     {"wjbs": ANCHORS["CUR"], "as_of": RUN_DATE}, {})
    payload = bad["payload"]
    checks.add(
        "S5A_unconfigured_bridge_fails_named_exit3",
        bad["exit"] == 3 and payload.get("status") == "NOT_CONNECTED"
        and payload.get("code") == "codices_import_path_not_configured",
        "空配置 → exit=%s %s/%s" % (bad["exit"], payload.get("status"),
                                     payload.get("code")))
    unknown = call_entry("statute.verify", {"wjbs": ANCHORS["CUR"]},
                         {"codices_import_path": codices_repo,
                          "codices_formal_root": DEFAULT_FORMAL_ROOT})
    payload = unknown["payload"]
    checks.add(
        "S5B_unknown_method_fails_named_exit3",
        unknown["exit"] == 3 and payload.get("status") == "NOT_CONNECTED"
        and "method_not_connected" in str(payload.get("code")),
        "statute.verify → exit=%s %s/%s" % (unknown["exit"],
                                            payload.get("status"),
                                            payload.get("code")))


def run_profile(args, profile: str, config: dict, lccc_path: str) -> int:
    """单 profile 全量 36 检＋证据落盘；S1-S5 断言逻辑与 W2a-U13 验收版
    逐字一致（v1 段 28 检）；S6/S7 为 W4-U41 v1.5 段（各 4 检）。"""
    checks = Checks()
    gate_results: list = []
    rows = load_document_rows(args.formal_root)
    section_s1(checks, rows, config, gate_results)
    section_s2(checks, args.formal_root, gate_results)
    strategy = section_s3(checks, config)
    section_s4(checks, args.commercial_tool)
    section_s5(checks, args.codices_repo)
    section_s6(checks, args.commercial_tool)
    section_s7(checks, config, args.commercial_tool)

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO_ROOT)).stdout.strip()
    host_tokens = sorted(
        var for var in ("YUANDIAN_MCP_TOKEN", "PKULAW_MCP_TOKEN")
        if os.environ.get(var, "").strip())
    evidence = {
        "run_date": RUN_DATE,
        "profile": profile,
        "command": "python -X utf8 " + " ".join(sys.argv),
        "cwd": str(REPO_ROOT),
        "host_paid_tokens_present": host_tokens or [],
        "host_token_note": "宿主机 token 在位情况（只记在位性不记值）；"
                           "断言子进程环境已剥除两 token，负测确定性成立",
        "subject_commit": commit,
        "formal_root": args.formal_root,
        "frozen_face": {
            "lccc_consumer.py": sha256_file(lccc_path),
            "commercial_law_mcp.py": sha256_file(args.commercial_tool),
            "legal_documents.csv": sha256_file(
                os.path.join(args.formal_root, "legal_documents.csv")),
            "legal_relations.csv": sha256_file(
                os.path.join(args.formal_root, "legal_relations.csv")),
        },
        "anchors": ANCHORS,
        "strategy": strategy,
        "v15_segment": {
            "ruling": "裁决#8-12 负测先行：付费通道以 127.0.0.1 回环合成 mock "
                      "端点实测请求面，不真打付费服务，真授权后补",
            "web_declaration_schema": "juscite-f64-web-verified/1",
        },
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    for root in [part.strip() for part in args.evidence_roots.split(",") if part.strip()]:
        out_dir = REPO_ROOT / root / profile
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "f64-f69-validity-recon.json").write_text(
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
    parser.add_argument("--formal-root", default=DEFAULT_FORMAL_ROOT)
    parser.add_argument("--codices-repo", default=DEFAULT_CODICES_REPO)
    parser.add_argument("--commercial-tool", default=DEFAULT_COMMERCIAL_TOOL)
    parser.add_argument("--evidence-roots", default="evidence/F64,evidence/F69")
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]

    lccc_path = os.path.join(args.codices_repo, "lccc_consumer.py")
    if not os.path.isfile(lccc_path):
        print("FATAL: lccc_consumer.py 不在 %s（E22 冻结面）" % args.codices_repo)
        return 2
    if sha256_file(lccc_path) != LCCC_SHA256:
        print("FATAL: 冻结面 lccc_consumer.py sha256 漂移")
        return 2

    config = {
        "codices_import_path": args.codices_repo,
        "codices_formal_root": args.formal_root,
    }
    codes = [run_profile(args, profile, config, lccc_path)
             for profile in profiles]
    return 0 if all(code == 0 for code in codes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
