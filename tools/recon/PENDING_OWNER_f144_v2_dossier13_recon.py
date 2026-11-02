#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F144-v2 企业尽调技能包 13 件全量 recon（W5-U15 合成施工）。

台账 F144-v2 行（B5 composite 段，t26-registry-split 拆分规则）：断言逐字
出自 06 source_stage 拍板文「…13 件套全量 v2」（06 acceptance 无 v2 段）。
13 件清单唯一权威＝竞品情报 zhiexa-skill-market.md §1「启信宝 13 件套」
（03-功能分母 F144 引；06 source_stage 2026-10-13 用户拍板＝MCP 连接器
接入企查查/天眼查不自采数据）。本工具复验 13 件全量消费面（
implementation/python/dossier13.py＋legal_entry dossier13.*，W5-U15）沿
W4-U40 九条负测纪律全继承（台账 F144-desktop actual）：

  ① 提供商闭集类别名 qcc_mcp/tyc_mcp 零 URL（单一权威自
    enterprise_connector.PROVIDER_CATEGORIES 导入，本面零第二闭集）；
  ② 缺 token→PAID_TOKEN_NOT_CONFIGURED 不自采不编数据（data/credential
    恒 None 非 {}，06 acceptance 逐字）；
  ③ token 在位仍 SESSION_ABSENT＝产品桥无已配置 MCP 连接器可注入——
    真实调用路径结构性不可达（客户端未建不可能自采）；
  ④ 回执转录绑定 出处（provider 闭集）/时间 retrieved_at/额度
    quota_remaining（05:149 来源时点额度可见）＋载荷 sha256 水印＋确定
    性 seal——凭证逐字承连接器产物（单一权威零重算），企业数据原文不
    落账（档案原文扫描零企业名）；
  ⑤ 失败三路（QUERY_FAILED/RECEIPT_INVALID×2）data/credential 恒 None
    绝不编占位企业字段；
  ⑥ url/cookie 旁路字段件面顶层具名拒＋名称/统一社会信用代码恰一查询
    键；
  ⑦ AST 双验＝dossier13.py 导入闭集零网络模块＋字符串常量零 URL＋标识
    符零旁路关键字＋recon 自身同检（W4-U03 N4 先例）；
  ⑧ 状态根产物零 URL 字面量零 token 值；
  ⑨ 幂等回流（同 dossier_id 同输入重放逐键相等/异输入 conflict/回读投
    影相等）。
  全量面＝13/13 闭集（件名逐字照抄权威清单零改写，全量＝不是 12 也不
  是 14；13 件全跑各落一档）＋双跑确定性（剥 recorded_at 逐键相等）。

边界如实：真实 MCP 连接器授权调用的实测属 F144-desktop/selfhost 回收
点（授权后补联测，W5-U19 守账），不并入本单——本单为 13 件全量合成施
工（合成回执/合成会话显式 synth）；原生 UI 触发面属产品宿主后续工单不
前造；F94 技能目录分发链不在本单。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f144_v2_dossier13_recon.py
  [--state-root-prefix <dir>] [--keep-temp]

退出码：0＝RECON_OK；2＝RECON_FAIL；3＝环境缺失。
证据：evidence/F144/v2/（JSON＋MD＋README，台账 evidence_path 兑现）。
全程合成材料；不 push。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUN_DATE = time.strftime("%Y%m%d")

SYNTH_TOKEN = "JUSCITE-SYNTH-TOKEN-NOT-REAL"
TOKEN_ENVS = ("QCC_MCP_TOKEN", "TYC_MCP_TOKEN")

D13_MODULE = REPO / "implementation" / "python" / "dossier13.py"
ENT_MODULE = REPO / "implementation" / "python" / "enterprise_connector.py"

D13_EXPECTED_IMPORTS = {"__future__", "hashlib", "json", "os", "datetime",
                        "pathlib", "enterprise_connector"}
BANNED_IDENT_SUBSTRINGS = ("cookie", "webdriver", "selenium")
URL_SCHEME_PARTS = ("http", "https", "ftp", "ws", "wss")
URL_SCHEME_MARK = ":" + "/" + "/"

# 13 件权威清单（zhiexa-skill-market.md §1 逐字；recon 钉定件名零漂移）。
AUTHORITY_PIECE_NAMES = (
    "企业优先级排序", "全景尽调报告", "公司风险速查",
    "关联企业传导风险", "前置准入核验", "司法与经营风险体检",
    "合作前主体核验", "国内企业关联关系", "多次关系寻源",
    "客户准入快速筛查", "招投标情报雷达", "负面舆情扫描",
    "重点区域企业检索",
)

# 回收点（具名，写回台账 failure_reason；真实半边不并单）。
RECOVERY_F144 = (
    "F144 真实授权半边回收点（不并单，W5-U19 守账）：企查查/天眼查 MCP "
    "连接器授权（token 配置入产品凭据设施）后经连接器真实授权调用，实测"
    "回执 出处/时间/额度转录绑定（05:149 来源时点额度可见不自采）——挂 "
    "F144-desktop/selfhost 既有回收点；F144-v2 本单为 13 件套全量 v2 合"
    "成施工（件目录＋消费面＋九条负测纪律），不前造真实通道")


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.failed = 0

    def check(self, cid: str, ok: bool, detail: str) -> bool:
        self.rows.append({"id": cid, "ok": bool(ok), "detail": detail[:600]})
        if not ok:
            self.failed += 1
            eprint(f"  [FAIL] {cid}: {detail[:300]}")
        else:
            eprint(f"  [ ok ] {cid}: {detail[:180]}")
        return bool(ok)

    @property
    def passed(self) -> int:
        return len(self.rows) - self.failed


def load_bridge():
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    from legal_entry import call as bridge_call
    return bridge_call


# ---------------------------------------------------------------------------
# AST 静态审计（负测纪律⑦＝结构性事实）
# ---------------------------------------------------------------------------

def ast_string_constants(source: str) -> list[str]:
    tree = ast.parse(source)
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant) and \
                        isinstance(value.value, str):
                    values.append(value.value)
    return values


def ast_import_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
    return roots


def d13_module_ast_audit(path: Path) -> tuple[bool, str]:
    """导入闭集恰零网络模块＋字符串常量零 URL 模式＋标识符零旁路关键字。"""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = ast_import_roots(source)
    if imported != D13_EXPECTED_IMPORTS:
        return False, f"{path.name} 导入闭集漂移: {sorted(imported)}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            for part in URL_SCHEME_PARTS:
                if part + URL_SCHEME_MARK in low:
                    return False, (f"{path.name} 字符串常量含 "
                                   f"{part}{URL_SCHEME_MARK}")
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        for name in names:
            for kw in BANNED_IDENT_SUBSTRINGS:
                if kw in name.lower():
                    return False, (f"{path.name} 标识符 {name} 含旁路关键"
                                   f"字 {kw}")
    return True, (f"{path.name} 导入闭集 {sorted(imported)}＝零网络模块"
                  "（enterprise_connector＝闭集单一权威本地零网络产品模"
                  "块）；字符串常量零 URL 模式；标识符零旁路关键字")


def recon_self_ast_audit() -> tuple[bool, str]:
    """本 recon 自身同检（W4-U03 N4 先例：面与工具双双自检）。"""
    source = Path(__file__).read_text(encoding="utf-8")
    constants = ast_string_constants(source)
    url_hits = [c for c in constants
                if any(part + URL_SCHEME_MARK in c.lower()
                       for part in URL_SCHEME_PARTS)]
    imports = ast_import_roots(source)
    net_tokens = {"urllib", "requests", "socket", "http", "ftplib",
                  "smtplib", "telnetlib"}
    net_hits = sorted(imports & net_tokens)
    ok = not url_hits and not net_hits
    return ok, (f"recon 自身字符串常量 {len(constants)} 个零 URL 字面量；"
                f"网络 token {net_hits or '无'}")


def scan_tree_blob(root: Path) -> str:
    chunks = []
    for p in sorted(root.rglob("*.json")):
        chunks.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def url_hits_in(blob: str) -> list[str]:
    low = blob.lower()
    return [part + URL_SCHEME_MARK for part in URL_SCHEME_PARTS
            if part + URL_SCHEME_MARK in low]


def err_text(exc: BaseException) -> str:
    return str(exc)


def strip_volatile(dossier: dict) -> dict:
    # recorded_at 仅溯源不入确定性对照；其余逐键相等。
    return {k: v for k, v in dossier.items() if k != "recorded_at"}


# ---------------------------------------------------------------------------
# 合成会话（显式合成材料；真实通道授权后补联测，不编其形状）
# ---------------------------------------------------------------------------

class SynthEnterpriseSession:
    """合成 MCP 连接器会话（显式 synth；零网络）。"""

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def query(self, company_name=None, credit_code=None):
        return {
            "provider": self.provider,
            "retrieved_at": "2026-10-23T08:30:00Z",
            "quota_remaining": 87,
            "payload": {"name": "合成市合成科技有限公司",
                        "status": "存续（合成样本）"},
        }


def synth_session_factory(provider: str):
    return SynthEnterpriseSession(provider)


# ---------------------------------------------------------------------------
# 单轮 recon
# ---------------------------------------------------------------------------

def run_checks(state_root: Path, bridge) -> tuple[Checks, dict]:
    ck = Checks()
    d13_cfg = {"dossier13_state_root": str(state_root / "d13")}
    company = "合成市合成科技有限公司"
    matter = "m-f144-v2-recon"
    evidence: dict = {"state_root": str(state_root)}

    env_snapshot = {v: os.environ.get(v) for v in TOKEN_ENVS}
    for v in TOKEN_ENVS:
        os.environ.pop(v, None)
    probe = {v: ("present" if env_snapshot[v] else "absent")
             for v in TOKEN_ENVS}
    evidence["authorization_probe"] = {
        "token_envs": probe,
        "note": "recon 全程在受控进程内显式设定/还原 token 环境；缺省态"
                "＝未配置 token（本机常态，授权未落地）"}
    eprint("-- 授权探测：token envs=" + ",".join(
        f"{v}={probe[v]}" for v in TOKEN_ENVS))

    try:
        # ---- 纪律⑦：模块 AST（d13 消费面；连接器面 W4-U40 recon 已钉，
        #      此处并列复验闭合单一权威链）---------------------------
        ok, detail = d13_module_ast_audit(D13_MODULE)
        ck.check("c01_d13_module_ast_no_network_no_url", ok, detail)

        # ---- 桥 fail-closed 三路 -----------------------------------
        try:
            bridge("dossier13.run_dossier",
                   {"dossier_id": "d", "matter_id": "m",
                    "piece_id": "panorama-report",
                    "providers": ["qcc_mcp"],
                    "company_name": company}, {})
            ck.check("c02_d13_fail_closed_state_root", False, "未抛")
        except Exception as exc:  # noqa: BLE001
            ck.check("c02_d13_fail_closed_state_root",
                     "dossier13_state_root_not_configured"
                     in err_text(exc), f"状态根缺→{exc}")
        try:
            bridge("dossier13.explode", {}, d13_cfg)
            ck.check("c02_d13_fail_closed_unknown_method", False, "未抛")
        except Exception as exc:  # noqa: BLE001
            ck.check("c02_d13_fail_closed_unknown_method",
                     "method_not_connected:dossier13.explode"
                     in err_text(exc), f"未知方法→{exc}")
        try:
            bridge("dossier13.run_dossier", "not-a-dict", d13_cfg)
            ck.check("c02_d13_fail_closed_params", False, "未抛")
        except Exception as exc:  # noqa: BLE001
            ck.check("c02_d13_fail_closed_params",
                     "dossier13_params_invalid" in err_text(exc),
                     f"params 非字典→{exc}")

        # ---- 全量件目录：13/13 闭集，件名逐字（全量＝不是 12 也不是 14）
        pack = bridge("dossier13.pack_read", {}, d13_cfg)
        names = tuple(p["name"] for p in pack["pieces"])
        ids = [p["piece_id"] for p in pack["pieces"]]
        pack_blob = json.dumps(pack, ensure_ascii=False)
        ck.check("c03_pack_full_set_13_verbatim_names",
                 pack["piece_count"] == 13 and pack["full_set"] is True
                 and names == AUTHORITY_PIECE_NAMES
                 and len(ids) == len(set(ids)) == 13
                 and pack["form"] == "skill_pack_no_self_collection"
                 and pack["self_collection"] == "none"
                 and pack["url_disclosure"] == "none"
                 and pack["providers"] == ["qcc_mcp", "tyc_mcp"]
                 and URL_SCHEME_MARK not in pack_blob,
                 "pack_read＝13/13 全量闭集：件名逐字照抄 zhiexa-skill-"
                 "market §1 权威清单零改写、顺序保持、id 唯一；形态声明"
                 " no_self_collection＋零 URL 披露＋提供商闭集类别名（单"
                 "一权威）")

        # ---- 纪律②：缺 token→PAID_TOKEN_NOT_CONFIGURED 不自采不编数据
        r_tok = bridge("dossier13.run_dossier",
                       {"dossier_id": "d-tok", "matter_id": matter,
                        "piece_id": "panorama-report",
                        "providers": ["qcc_mcp", "tyc_mcp"],
                        "company_name": company}, d13_cfg)
        tok_segs = r_tok["segments"]
        ck.check("c04_token_gap_values_none",
                 all(s["status"] == "TOKEN_NOT_CONFIGURED"
                     and s["reason"] == "PAID_TOKEN_NOT_CONFIGURED"
                     and s["data"] is None and s["credential"] is None
                     for s in tok_segs)
                 and len(tok_segs) == 2
                 and r_tok["counts"]["token_not_configured"] == 2,
                 "缺 Token 查询→不自采或编数据：双提供商 data/credential "
                 "恒 None（非 {} 非占位企业字段；06 acceptance 逐字）")

        # ---- 纪律①：提供商/件闭集外具名拒---------------------------
        refusals_ok = True
        refusal_parts = []
        for kwargs, needle in (
                ({"dossier_id": "d-badprov", "matter_id": matter,
                  "piece_id": "company-risk-quick-scan",
                  "providers": ["unknowncorp_mcp"],
                  "company_name": company},
                 "d13_provider_unknown:unknowncorp_mcp"),
                ({"dossier_id": "d-badpiece", "matter_id": matter,
                  "piece_id": "no-such-piece",
                  "providers": ["qcc_mcp"], "company_name": company},
                 "d13_piece_unknown:no-such-piece")):
            try:
                bridge("dossier13.run_dossier", kwargs, d13_cfg)
                refusals_ok = False
                refusal_parts.append(needle + ":未拒")
            except Exception as exc:  # noqa: BLE001
                good = needle in err_text(exc)
                refusals_ok = refusals_ok and good
                refusal_parts.append(needle + ":" + str(good))
        ck.check("c05_closed_set_refusals", refusals_ok,
                 "提供商闭集外/件闭集外具名拒（" + ";".join(refusal_parts)
                 + "；闭集单一权威零第二闭集）")

        # ---- 纪律③：token 在位仍 SESSION_ABSENT（桥 session_factory 恒
        #      None＝结构性不可达）-------------------------------------
        os.environ["QCC_MCP_TOKEN"] = SYNTH_TOKEN
        os.environ["TYC_MCP_TOKEN"] = SYNTH_TOKEN
        r_sess = bridge("dossier13.run_dossier",
                        {"dossier_id": "d-sess", "matter_id": matter,
                         "piece_id": "counterparty-verification",
                         "providers": ["qcc_mcp", "tyc_mcp"],
                         "credit_code": "91340100SYNTH0001X"}, d13_cfg)
        sess_segs = r_sess["segments"]
        ck.check("c06_session_absent_structural_unreachable",
                 all(s["status"] == "SESSION_ABSENT"
                     and s["reason"]
                     == "CONNECTOR_SESSION_ABSENT_PENDING_AUTHORIZATION"
                     and s["data"] is None and s["credential"] is None
                     for s in sess_segs)
                 and r_sess["sessions_established"] == 0,
                 "token 在位仍 SESSION_ABSENT——产品桥无已配置 MCP 连接器"
                 "可注入（真实接入属授权后配置），真实调用路径结构性不可"
                 "达（客户端未建不可能自采）")

        # ---- 纪律④：合成回执转录（模块级注入合成会话＝显式合成材料）：
        #      出处/时间/额度绑定＋凭证逐字承连接器产物＋企业原文不落账
        import dossier13 as d13
        import enterprise_connector as ent
        r_seal = d13.run_dossier(
            state_root / "d13",
            {"dossier_id": "d-seal", "matter_id": matter,
             "piece_id": "panorama-report", "providers": ["qcc_mcp"],
             "company_name": company},
            session_factory=synth_session_factory)
        seg = r_seal["segments"][0]
        cred = seg["credential"]
        dossier_raw = (state_root / "d13" / "dossiers" / "d-seal.json") \
            .read_text(encoding="utf-8")
        recompute = ent.record_from_receipt(
            {"provider": "qcc_mcp", "company_name": company,
             "credit_code": None}, SynthEnterpriseSession("qcc_mcp").query())
        ck.check("c07_receipt_binds_credential_verbatim_no_raw",
                 seg["status"] == "DILIGENCE_RECORDED"
                 and cred["provider"] == "qcc_mcp"
                 and cred["retrieved_at"] == "2026-10-23T08:30:00Z"
                 and cred["quota_remaining"] == 87
                 and len(cred["source_watermark"]["payload_sha256"]) == 64
                 and seg["data"]["payload_sha256"]
                 == cred["source_watermark"]["payload_sha256"]
                 and recompute == cred
                 and company not in dossier_raw
                 and "存续（合成样本）" not in dossier_raw,
                 "MCP 回执转录：出处（provider 闭集）＋时间＋额度 87（05:"
                 "149 来源时点额度可见）绑定＋载荷 sha256 水印＋确定性 "
                 "seal；凭证与连接器面 record_from_receipt 重算逐键相等"
                 "（单一权威零重算零第二 seal）；企业数据原文不落账（档案"
                 "原文扫描零企业名）")

        # ---- 纪律⑤：失败三路 data/credential 恒 None----------------
        def _boom(_provider):
            raise RuntimeError("synth connector down")

        r_fail = d13.run_dossier(
            state_root / "d13",
            {"dossier_id": "d-fail", "matter_id": matter,
             "piece_id": "bidding-radar", "providers": ["qcc_mcp"],
             "company_name": company},
            session_factory=_boom)

        class _BadSession:
            def query(self, company_name=None, credit_code=None):
                return {"provider": "unknowncorp_mcp",
                        "retrieved_at": "2026-10-23T08:30:00Z",
                        "payload": {}}

        r_bad = d13.run_dossier(
            state_root / "d13",
            {"dossier_id": "d-bad", "matter_id": matter,
             "piece_id": "negative-publicity-scan", "providers": ["tyc_mcp"],
             "company_name": company},
            session_factory=lambda _p: _BadSession())

        class _NoQuotaSession:
            def query(self, company_name=None, credit_code=None):
                return {"provider": "tyc_mcp",
                        "retrieved_at": "2026-10-23T08:30:00Z",
                        "payload": {"k": "v"}}

        r_noquota = d13.run_dossier(
            state_root / "d13",
            {"dossier_id": "d-noquota", "matter_id": matter,
             "piece_id": "key-region-search", "providers": ["tyc_mcp"],
             "company_name": company},
            session_factory=lambda _p: _NoQuotaSession())
        f, b, q = (r_fail["segments"][0], r_bad["segments"][0],
                   r_noquota["segments"][0])
        ck.check("c08_failure_three_ways_no_data",
                 f["status"] == "QUERY_FAILED"
                 and f["reason"] == "connector_failed:RuntimeError"
                 and f["data"] is None and f["credential"] is None
                 and b["status"] == "RECEIPT_INVALID"
                 and b["reason"]
                 == "f144_receipt_invalid:provider_not_in_closed_set"
                 and b["data"] is None and b["credential"] is None
                 and q["status"] == "RECEIPT_INVALID"
                 and q["reason"]
                 == "f144_receipt_invalid:quota_remaining_missing"
                 and q["data"] is None and q["credential"] is None,
                 "失败不编数据：session 异常→QUERY_FAILED；provider 闭集外"
                 "/缺额度→RECEIPT_INVALID 具名理由；三路 data/credential "
                 "恒 None，绝不编占位企业字段")

        # ---- 纪律⑥：旁路字段具名拒＋恰一查询键----------------------
        neg_ok = True
        neg_parts = []
        for field in ("url", "cookie"):
            try:
                bridge("dossier13.run_dossier",
                       {"dossier_id": "d-neg-" + field, "matter_id": matter,
                        "piece_id": "pre-admission-check",
                        "providers": ["qcc_mcp"],
                        "company_name": company,
                        field: "synth-bypass-value"}, d13_cfg)
                neg_ok = False
                neg_parts.append(field + ":未拒")
            except Exception as exc:  # noqa: BLE001
                neg_ok = neg_ok and \
                    "d13_field_forbidden:" + field in err_text(exc)
                neg_parts.append(field + ":具名拒")
        for label, extra in (("both",
                              {"credit_code": "91340100SYNTH0001X"}),
                             ("none", {})):
            base = {"dossier_id": "d-key-" + label, "matter_id": matter,
                    "piece_id": "pre-admission-check",
                    "providers": ["qcc_mcp"]}
            base.update(extra)
            if label == "none":
                base.pop("company_name", None)
            else:
                base["company_name"] = company
            try:
                bridge("dossier13.run_dossier", base, d13_cfg)
                neg_ok = False
                neg_parts.append(label + "-keys:未拒")
            except Exception as exc:  # noqa: BLE001
                neg_ok = neg_ok and \
                    "d13_query_key_exactly_one_required" in err_text(exc)
                neg_parts.append(label + "-keys:具名拒")
        ck.check("c09_bypass_and_key_discipline", neg_ok,
                 "url/cookie 旁路字段件面具名拒＋名称/信用代码恰一查询键"
                 "（" + ";".join(neg_parts) + "；不自采＝无隐式通道）")

        # ---- 纪律⑧：状态根产物零 URL 零 token 值---------------------
        blob = scan_tree_blob(state_root / "d13")
        hits = url_hits_in(blob)
        leak = SYNTH_TOKEN in blob
        ck.check("c10_artifacts_zero_url_zero_token",
                 not hits and not leak,
                 f"d13 状态根全产物零 URL 字面量（{hits or '无'}）＋零 "
                 f"token 值泄漏={leak}")

        # ---- 纪律⑨：幂等重放逐键相等／conflict／回读投影相等---------
        replay = bridge("dossier13.run_dossier",
                        {"dossier_id": "d-seal", "matter_id": matter,
                         "piece_id": "panorama-report",
                         "providers": ["qcc_mcp"],
                         "company_name": company}, d13_cfg)
        idem_ok = replay == r_seal
        conflict_ok = True
        try:
            bridge("dossier13.run_dossier",
                   {"dossier_id": "d-seal", "matter_id": matter,
                    "piece_id": "panorama-report",
                    "providers": ["tyc_mcp"],
                    "company_name": company}, d13_cfg)
            conflict_ok = False
        except Exception as exc:  # noqa: BLE001
            conflict_ok = "d13_dossier_conflict" in err_text(exc)
        read = bridge("dossier13.dossier_read",
                      {"dossier_id": "d-seal"}, d13_cfg)
        ck.check("c11_idempotent_replay_conflict_read",
                 idem_ok and conflict_ok and read == r_seal,
                 "幂等回流：同 dossier_id 同输入重放逐键相等（不双记）；异"
                 "输入具名 conflict；回读投影==档案")

        # ---- 全量面：13 件全跑各落一档（13/13 不缺件不重件）----------
        coverage_ids = []
        coverage_names_ok = True
        for piece_id, piece_name in zip(d13.PIECE_IDS, d13.PIECE_NAMES):
            # 模块级合成会话（显式 synth）：桥面 session_factory 恒 None
            # （结构性 SESSION_ABSENT，见 c06）；全量覆盖要验的是回执转录
            # 通道下 13 件各自完整落档——与 c07/c08 同一合成通道。
            r_cov = d13.run_dossier(
                state_root / "d13",
                {"dossier_id": "cov-" + piece_id,
                 "matter_id": matter, "piece_id": piece_id,
                 "providers": ["qcc_mcp", "tyc_mcp"],
                 "company_name": company},
                session_factory=synth_session_factory)
            coverage_ids.append(r_cov["piece_id"])
            if r_cov["piece_name"] != piece_name:
                coverage_names_ok = False
            if r_cov["counts"]["diligence_recorded"] != 2:
                coverage_names_ok = False
        dossier_files = list((state_root / "d13" / "dossiers")
                             .glob("*.json"))
        ck.check("c12_full_pack_coverage_13_dossiers",
                 len(coverage_ids) == 13
                 and sorted(coverage_ids) == sorted(d13.PIECE_IDS)
                 and coverage_names_ok
                 and len(dossier_files) == 19,
                 "13 件套全量：件 id 与件名一一对应（权威清单逐字）且每件"
                 "双提供商回执各 2 转录；档案恰 19 份（c04/c06/c07 各 1＋"
                 "失败三路 3＋覆盖 13；c05/c09 六次闭集拒零落档；c11 重放"
                 "不双记零新档）")

        # ---- 双跑确定性：同输入独立状态根重跑剥 recorded_at 逐键相等--
        r_det = d13.run_dossier(
            state_root / "d13-det",
            {"dossier_id": "d-seal", "matter_id": matter,
             "piece_id": "panorama-report", "providers": ["qcc_mcp"],
             "company_name": company},
            session_factory=synth_session_factory)
        ck.check("c13_dossier_determinism_double_run",
                 strip_volatile(r_det) == strip_volatile(r_seal),
                 "双跑确定性：独立状态根同输入重跑剥 recorded_at 逐键相等"
                 "（合成回执的确定性面；recorded_at 仅溯源）")

        evidence["pack"] = pack
        evidence["token_gap"] = r_tok
        evidence["session_absent"] = r_sess
        evidence["recorded"] = r_seal
        evidence["credential"] = cred
        evidence["failure"] = r_fail
        evidence["receipt_invalid_closed_set"] = r_bad
        evidence["receipt_invalid_quota"] = r_noquota
        evidence["coverage_piece_ids"] = coverage_ids
        return ck, evidence
    finally:
        for v, saved in env_snapshot.items():
            if saved is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = saved


def render_readme(stamp: str) -> str:
    stem = "f144-v2-dossier13-recon-" + stamp
    return "\n".join([
        "# F144-v2／13 件套全量 v2 证据（W5-U15 合成施工）",
        "",
        "- `" + stem + ".json`／`.md`：企业尽调技能包 13 件全量 recon 证据"
        "（含授权探测、逐检清单、回收点具名）；",
        "- 台账断言（F144-v2，B5）：13 件套全量 v2（照抄 06 source_stage "
        "拍板文；06 acceptance 无 v2 段）；13 件清单唯一权威＝zhiexa-"
        "skill-market.md §1 启信宝 13 件套（03-功能分母 F144 引）；",
        "- W4-U40 九条负测纪律全继承（闭集零 URL／缺 token 不自采不编数"
        "据／SESSION_ABSENT 结构性不可达／回执转录绑定 出处-时间-额度-"
        "sha256-确定性 seal／失败三路值恒 None／旁路字段具名拒＋恰一键／"
        "AST 双验／产物零 URL 零 token／幂等重放）；",
        "- 真实授权半边挂 F144-desktop/selfhost 回收点（W5-U19 守账）不"
        "并单；全程合成材料；不 push。",
    ]) + "\n"


def render_md(checks: Checks, cross_rows: list, payload: dict) -> str:
    lines = [
        "# F144-v2 企业尽调技能包 13 件全量 recon 证据（W5-U15）", "",
        "台账 F144-v2（B5 composite 段）：断言逐字出自 06 source_stage 拍板"
        "文「…13 件套全量 v2」；13 件清单唯一权威＝zhiexa-skill-market.md "
        "§1 启信宝 13 件套。W4-U40 九条负测纪律全继承；真实授权半边挂 "
        "F144-desktop/selfhost 回收点（W5-U19 守账）不并单。",
        "",
        "## 回收点（具名）",
        f"- {RECOVERY_F144}",
        "## 负测纪律（结构性事实）",
        "- 提供商闭集类别名 qcc_mcp/tyc_mcp 零 URL（单一权威导入）；缺 "
        "token→PAID_TOKEN_NOT_CONFIGURED 不自采不编数据；",
        "- token 在位仍 SESSION_ABSENT＝真实调用路径结构性不可达（客户端"
        "未建不可能自采）；回执转录绑定 出处/时间/额度＋sha256 水印＋确定"
        "性 seal（凭证逐字承连接器产物）；失败三路 data/credential 恒 "
        "None；",
        "- url/cookie 旁路字段具名拒＋恰一查询键；13 件全量闭集（件名逐"
        "字）；AST 双验＋recon 自身同检；产物零 URL 零 token 值；幂等重放"
        "逐键相等。",
        "## 检查清单",
    ]
    lines += [f"- [{'x' if r['ok'] else ' '}] {r['id']}: {r['detail']}"
              for r in checks.rows]
    lines += [f"- [{'x' if r['ok'] else ' '}] {r['id']}: {r['detail']}"
              for r in cross_rows]
    passed = checks.passed + sum(1 for r in cross_rows if r["ok"])
    total = len(checks.rows) + len(cross_rows)
    lines += ["", f"**{passed}/{total} checks passed.**", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state-root-prefix", type=Path, default=None,
                    help="状态根前缀（默认临时目录）")
    ap.add_argument("--keep-temp", action="store_true",
                    help="保留默认临时状态根（调试用）")
    args = ap.parse_args(argv)

    started = time.time()
    tmp_ctx = None
    if args.state_root_prefix is None:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="juscite-f144v2-")
        args.state_root_prefix = Path(tmp_ctx.name)
        if args.keep_temp:
            args.state_root_prefix = (Path(tempfile.gettempdir())
                                      / "juscite-f144v2-keep")
            args.state_root_prefix.mkdir(parents=True, exist_ok=True)
            tmp_ctx = None
    args.state_root_prefix.mkdir(parents=True, exist_ok=True)

    try:
        bridge = load_bridge()
    except Exception as exc:  # noqa: BLE001
        eprint(f"[ENV] 桥不可用: {type(exc).__name__}: {exc}")
        return 3

    eprint(f"== W5-U15 F144-v2 dossier13 recon state_root="
           f"{args.state_root_prefix}")

    ok = True
    ck, evidence = run_checks(args.state_root_prefix, bridge)
    ok = ok and ck.failed == 0

    # -- 跨检：recon 自身 AST＋回收点具名--------------------------------
    cross_rows: list[dict] = []
    self_ok, self_detail = recon_self_ast_audit()
    cross_rows.append({
        "id": "c00_recon_self_ast_no_url_no_network",
        "ok": self_ok,
        "detail": self_detail + "（W4-U03 N4 先例：面与工具双双自检）",
    })
    ok = ok and self_ok
    cross_rows.append({
        "id": "c14_recovery_point_named_not_merged",
        "ok": bool(RECOVERY_F144),
        "detail": "真实授权半边回收点具名＝F144-desktop/selfhost（W5-U19 "
                  "守账，不并单）；本单＝13 件套全量 v2 合成施工，不前造"
                  "真实通道",
    })

    payload = {
        "schema": "juscite-f144-v2-dossier13-recon/1",
        "unit": "W5-U15",
        "obligations": ["F144-v2"],
        "ruling": ("06 source_stage 2026-10-13 用户拍板（MCP 连接器不自"
                   "采）＋t26 拆分 F144-v2/B5；13 件清单唯一权威＝"
                   "zhiexa-skill-market.md §1 启信宝 13 件套"),
        "recovery_points": {"F144": RECOVERY_F144},
        "started_at": now_iso(),
        "run_date": RUN_DATE,
        "command": ("python -X utf8 "
                    "tools/PENDING_OWNER_f144_v2_dossier13_recon.py"),
        "modules": {"dossier13": sha256_file(D13_MODULE),
                    "enterprise_connector": sha256_file(ENT_MODULE)},
        "authority_piece_names": list(AUTHORITY_PIECE_NAMES),
        "finished_at": None,
        "duration_s": None,
    }
    payload["checks"] = {"cross": cross_rows, "single": ck.rows}
    payload["evidence"] = evidence
    payload["finished_at"] = now_iso()
    payload["duration_s"] = round(time.time() - started, 1)
    payload["overall"] = "RECON_OK" if ok else "RECON_FAIL"
    payload["passed"] = ck.passed + sum(1 for r in cross_rows if r["ok"])
    payload["total"] = len(ck.rows) + len(cross_rows)

    # -- 证据落盘（台账 evidence_path＝evidence/F144/v2/）----------------
    ev_root = REPO / "evidence" / "F144" / "v2"
    ev_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = "f144-v2-dossier13-recon-" + stamp
    (ev_root / (stem + ".json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    (ev_root / (stem + ".md")).write_text(
        render_md(ck, cross_rows, payload), encoding="utf-8")
    (ev_root / "README.md").write_text(render_readme(stamp),
                                       encoding="utf-8")

    for r in cross_rows:
        if not r["ok"]:
            eprint(f"  [FAIL] {r['id']}: {r['detail'][:300]}")
    eprint(f"== {payload['passed']}/{payload['total']} checks passed "
           f"({payload['duration_s']}s)")
    if not ok:
        eprint("RECON_FAIL")
        return 2
    eprint("RECON_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
