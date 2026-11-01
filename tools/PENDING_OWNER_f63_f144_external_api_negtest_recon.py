#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F63＋F144 五项外部 API 之 EMS＋企查查/天眼查 recon（W4-U40 负测先行）。

00-总协调 §6.1 裁决#8-12（五项外部 API 统一负测先行：禁编 URL/失败不
造假，授权后补）为唯一执行态。06 行 acceptance 的真实半边（F63「EMS 轨
迹与取证时间/来源水印凭证真实生成」＝真实 EMS 官方 API 授权调用；F144
「企查查/天眼查 MCP 实际授权调用/出处/时间」＝真实 MCP 连接器授权调用）
属授权后补联测（回收点具名，见 verdict.recovery_points 与本单台账
failure_reason）。本工具只复验负测半边＋凭证/转录逻辑的合成封存：

  F63（ems_evidence.py＋legal_entry ems.*，owner=product）：
  - 未授权动作→ACTION_NOT_AUTHORIZED 值恒 None（授权闸先行，E24 形态）；
  - 缺 token→具名缺口 PAID_TOKEN_NOT_CONFIGURED（W2a-U13 先例同码）不自采；
  - 已授权＋token 在位也只得到 ADAPTER_ABSENT——本波产品桥无 EMS 适配器
    可注入（端点未定禁编 URL），未授权/未接线态真实调用路径结构性不可达
    （客户端未建不可能自采；构造级证明＝W2a-U13 P11「构造即拒」同构）；
  - 凭证只从真实回执转录并绑定取证时间（retrieved_at）＋来源水印
    （provider＋回执 sha256）＋确定性 seal；E17 EvidenceAttempt 语义＝
    有凭据（真实回执）才记取得，无回执条目轨迹/凭证/费用恒 None——
    失败不编轨迹（transport 异常/回执残缺具名拒，绝不生成部分轨迹）；
  - 费用只收整型分（E21 消费面纪律，float 具名拒）。
  F144（enterprise_connector.py＋legal_entry enterprise.*，owner=product；
  2026-10-13 用户拍板：走 MCP 连接器接入不自采数据；13 件套全量 v2=
  F144-v2 归 W5 不前造）：
  - 提供商闭集类别名 qcc_mcp/tyc_mcp（零 URL；连接器形态端点由用户 MCP
    配置提供，产品面不编 URL）；缺 Token→PAID_TOKEN_NOT_CONFIGURED 不
    自采或编数据（值恒 None 非 {}）；连接器会话未建→SESSION_ABSENT
    （客户端未建不可能自采）；回执转录绑定 出处（provider 闭集）/时间
    （retrieved_at）/额度（quota_remaining，05:149 来源时点额度可见）。
  双面 AST 级零拼 URL：两产品模块字符串常量零 URL 模式（连冻结常量都
  不存在——比 P11「字面量只在 PROVIDERS」更强）＋导入闭集恰零网络模块
  ＋标识符零采集旁路关键字；本 recon 自身同检（W4-U03 N4 先例）；状态
  根全部产物零 URL 字面量零 token 值。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f63_f144_external_api_negtest_recon.py \
      --profile desktop --profile selfhost
  [--state-root-prefix <dir>] [--keep-temp]

退出码：0＝RECON_OK（双 profile 全过）；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/F63/<profile>/ 与 evidence/F144/<profile>/
（JSON＋MD，同名族前缀）。全程合成材料；不 push。
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

# 合成标记 token（显式合成，不入账不外发；recon 结束即还原环境）。
SYNTH_TOKEN = "JUSCITE-SYNTH-TOKEN-NOT-REAL"
TOKEN_ENVS = ("EMS_API_TOKEN", "QCC_MCP_TOKEN", "TYC_MCP_TOKEN")

EMS_MODULE = REPO / "implementation" / "python" / "ems_evidence.py"
ENT_MODULE = REPO / "implementation" / "python" / "enterprise_connector.py"

EXPECTED_IMPORTS = {"__future__", "hashlib", "json", "os", "datetime",
                    "pathlib"}
BANNED_IDENT_SUBSTRINGS = ("cookie", "webdriver", "selenium")
# URL 判别式拆写（本文件自身也是被检对象，不得含完整 URL 字面量）。
URL_SCHEME_PARTS = ("http", "https", "ftp", "ws", "wss")
URL_SCHEME_MARK = ":" + "/" + "/"

# 授权后补联测回收点（具名，写回台账 failure_reason）。
RECOVERY_F63 = (
    "F63 授权后补联测回收点：EMS 官方 API 授权落地后，落产品 EMS 适配器"
    "（端点出自授权方文档冻结常量，禁编 URL）经 ems.evidence_query 真实"
    "调用，实测轨迹与取证时间/来源水印凭证真实生成（裁决#8-12 授权后补）")
RECOVERY_F144 = (
    "F144 授权后补联测回收点：企查查/天眼查 MCP 连接器授权（token 配置入"
    "产品凭据设施）后，经 MCP 连接器真实授权调用，实测回执 出处/时间/额度"
    "转录绑定（05:149 来源时点额度可见不自采；13 件套全量 v2=F144-v2 归"
    " W5 不前造）")


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
# AST 静态审计（负测先行＝结构性事实，不是运行时约定）
# ---------------------------------------------------------------------------

def ast_string_constants(source: str) -> list[str]:
    tree = ast.parse(source)
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
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


def module_ast_audit(path: Path) -> tuple[bool, str]:
    """导入闭集恰零网络模块＋字符串常量零 URL 模式＋标识符零旁路关键字。"""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = ast_import_roots(source)
    if imported != EXPECTED_IMPORTS:
        return False, f"{path.name} 导入闭集漂移: {sorted(imported)}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            for part in URL_SCHEME_PARTS:
                if part + URL_SCHEME_MARK in low:
                    return False, f"{path.name} 字符串常量含 {part}://{URL_SCHEME_MARK}"
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
                    return False, f"{path.name} 标识符 {name} 含旁路关键字 {kw}"
    return True, (f"{path.name} 导入闭集 {sorted(imported)}＝零网络模块；"
                  "字符串常量零 URL 模式；标识符零旁路关键字")


def self_ast_audit() -> tuple[bool, str]:
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


# ---------------------------------------------------------------------------
# 合成回执/合成连接器（显式合成材料；真实通道授权后补联测，不编其形状）
# ---------------------------------------------------------------------------

def synth_ems_receipt(waybill_no: str) -> dict:
    return {
        "provider": "ems_synth",
        "retrieved_at": "2026-10-21T08:00:00Z",
        "trace": [
            {"time": "2026-10-20T09:00:00Z", "desc": "【合成】收寄封发"},
            {"time": "2026-10-21T07:30:00Z", "desc": "【合成】投递并签收"},
        ],
        "cost_cents": 300,
    }


class SynthEnterpriseSession:
    """合成 MCP 连接器会话（显式 synth provider 回执；零网络）。"""

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def query(self, company_name=None, credit_code=None):
        return {
            "provider": self.provider,
            "retrieved_at": "2026-10-21T08:30:00Z",
            "quota_remaining": 87,
            "payload": {"name": "合成市合成科技有限公司",
                        "status": "存续（合成样本）"},
        }


def synth_session_factory(provider: str):
    return SynthEnterpriseSession(provider)


# ---------------------------------------------------------------------------
# 单 profile
# ---------------------------------------------------------------------------

def run_profile(profile: str, args, bridge) -> tuple[Checks, dict]:
    ck = Checks()
    state_root = Path(args.state_root_prefix) / f"profile-{profile}"
    ems_cfg = {"ems_evidence_state_root": str(state_root / "ems")}
    ent_cfg = {"enterprise_connector_state_root": str(state_root / "ent")}
    waybill = "1130000000012"
    matter_f63 = "m-f63-recon"
    matter_f144 = "m-f144-recon"
    evidence: dict = {"profile": profile, "state_root": str(state_root)}

    # ---- 授权态/token 态探测（裁决#8-12：负测先行，授权后补）--------------
    env_snapshot = {v: os.environ.get(v) for v in TOKEN_ENVS}
    for v in TOKEN_ENVS:
        os.environ.pop(v, None)
    probe = {
        "token_envs": {v: ("present" if env_snapshot[v] else "absent")
                       for v in TOKEN_ENVS},
        "note": "recon 全程在受控进程内显式设定/还原 token 环境；缺省态"
                "＝未配置 token（本机常态，授权未落地）",
    }
    evidence["authorization_probe"] = probe
    eprint("-- 授权探测：token envs="
           + ",".join(f"{v}={probe['token_envs'][v]}" for v in TOKEN_ENVS))

    try:
        # ================================================================
        # F63 leg
        # ================================================================
        ok, detail = module_ast_audit(EMS_MODULE)
        ck.check("c01_ems_module_ast_no_network_no_url", ok, detail)

        # fail-closed 三路（桥基线）
        try:
            bridge("ems.evidence_query",
                   {"query_id": "q", "matter_id": "m",
                    "items": [{"waybill_no": waybill}]}, {})
            ck.check("c02_ems_fail_closed_state_root", False, "未抛")
        except Exception as exc:  # noqa: BLE001
            ck.check("c02_ems_fail_closed_state_root",
                     "ems_evidence_state_root_not_configured"
                     in err_text(exc), f"状态根缺→{exc}")
        try:
            bridge("ems.explode", {}, ems_cfg)
            ck.check("c02_ems_fail_closed_unknown_method", False, "未抛")
        except Exception as exc:  # noqa: BLE001
            ck.check("c02_ems_fail_closed_unknown_method",
                     "method_not_connected:ems.explode" in err_text(exc),
                     f"未知方法→{exc}")
        try:
            bridge("ems.evidence_query", "not-a-dict", ems_cfg)
            ck.check("c02_ems_fail_closed_params", False, "未抛")
        except Exception as exc:  # noqa: BLE001
            ck.check("c02_ems_fail_closed_params",
                     "ems_evidence_params_invalid" in err_text(exc),
                     f"params 非字典→{exc}")

        # 授权账（E24 形态：append-only＋幂等重放＋scope 闭集）
        auth1 = bridge("ems.action_authorize",
                       {"authorized_by": f"synth-lawyer-{profile}"}, ems_cfg)
        auth2 = bridge("ems.action_authorize",
                       {"authorized_by": f"synth-lawyer-{profile}"}, ems_cfg)
        a1 = auth1["authorization"]
        ck.check("c03_ems_authorize_ledger_e24_form",
                 auth2["idempotent_replay"] is True
                 and auth2["authorization"]["auth_id"] == a1["auth_id"]
                 and a1["scope"] == "ems_official_api_query"
                 and a1["authorized_by"] == f"synth-lawyer-{profile}"
                 and isinstance(a1["recorded_at"], str),
                 f"E24 形态授权账 auth_id={a1['auth_id']} scope 闭集＋幂等")
        try:
            bridge("ems.action_authorize",
                   {"authorized_by": "x", "scope": "web_scrape"}, ems_cfg)
            ck.check("c03_ems_scope_closed", False, "闭集外 scope 未拒")
        except Exception as exc:  # noqa: BLE001
            ck.check("c03_ems_scope_closed",
                     "f63_scope_unknown:web_scrape" in err_text(exc),
                     f"scope 闭集外→{exc}")

        # 未授权态查询（独立状态根＝真实未授权态复现；授权闸先行值恒 None）
        unauth_cfg = {"ems_evidence_state_root":
                      str(state_root / "ems-unauth-probe")}
        r_unauth = bridge("ems.evidence_query",
                          {"query_id": "q-unauth", "matter_id": matter_f63,
                           "items": [{"waybill_no": waybill}]}, unauth_cfg)
        u_item = r_unauth["items"][0]
        ck.check("c04_ems_unauthorized_unreachable_values_none",
                 u_item["status"] == "ACTION_NOT_AUTHORIZED"
                 and u_item["reason"] == "f63_action_not_authorized"
                 and u_item["trajectory"] is None
                 and u_item["credential"] is None,
                 "未授权动作→ACTION_NOT_AUTHORIZED 轨迹/凭证恒 None"
                 "（授权闸先行；UNKNOWN 不是 0 不造空轨迹）")

        # 缺 token（已授权）→ 具名缺口 PAID_TOKEN_NOT_CONFIGURED 不自采
        r_notok = bridge("ems.evidence_query",
                         {"query_id": "q-notoken", "matter_id": matter_f63,
                          "items": [{"waybill_no": waybill}]}, ems_cfg)
        n_item = r_notok["items"][0]
        ck.check("c05_ems_token_named_gap_paid_token_not_configured",
                 n_item["status"] == "TOKEN_NOT_CONFIGURED"
                 and n_item["reason"] == "PAID_TOKEN_NOT_CONFIGURED"
                 and n_item["trajectory"] is None
                 and n_item["credential"] is None,
                 "已授权缺 token→PAID_TOKEN_NOT_CONFIGURED（W2a-U13 先例"
                 "同码）不自采；授权闸先行→token 闸次序实证（c04→c05）")

        # 已授权＋token 在位：适配器缺席＝客户端未建不可能自采（构造级）
        os.environ["EMS_API_TOKEN"] = SYNTH_TOKEN
        r_adapter = bridge("ems.evidence_query",
                           {"query_id": "q-adapter", "matter_id": matter_f63,
                            "items": [{"waybill_no": waybill}]}, ems_cfg)
        a_item = r_adapter["items"][0]
        ck.check("c06_ems_adapter_absent_structural_unreachable",
                 a_item["status"] == "ADAPTER_ABSENT"
                 and a_item["reason"]
                 == "EMS_ADAPTER_ABSENT_PENDING_AUTHORIZATION"
                 and a_item["trajectory"] is None
                 and a_item["credential"] is None
                 and r_adapter["adapter"] == "absent",
                 "已授权＋token 在位仍 ADAPTER_ABSENT——产品桥无适配器可注"
                 "入（端点未定禁编 URL），真实调用路径结构性不可达（客户端"
                 "未建不可能自采＝P11 构造即拒同构）")

        # 合成回执封存（模块级注入合成 transport＝显式合成材料）：凭证绑定
        # 取证时间/来源水印＋确定性 seal＋轨迹转录
        import ems_evidence as ems
        qr_sealed = ems.run_query(
            state_root / "ems",
            {"query_id": "q-seal", "matter_id": matter_f63,
             "items": [{"waybill_no": waybill}]},
            transport=synth_ems_receipt)
        s_item = qr_sealed["items"][0]
        cred = s_item["credential"]
        receipt = synth_ems_receipt(waybill)
        ck.check("c07_ems_seal_binds_time_source_watermark",
                 s_item["status"] == "EVIDENCE_SEALED"
                 and cred["evidence_time_utc"] == receipt["retrieved_at"]
                 and cred["source_watermark"]["provider"]
                 == receipt["provider"]
                 and len(cred["source_watermark"]["receipt_sha256"]) == 64
                 and cred["trace_count"] == len(receipt["trace"])
                 and len(s_item["trajectory"]) == len(receipt["trace"]),
                 f"EVIDENCE_SEALED：凭证绑定取证时间 {cred['evidence_time_utc']}"
                 f"＋来源水印 provider={cred['source_watermark']['provider']}"
                 "＋回执 sha256；轨迹自回执转录（描述只留哈希）")
        resealed = ems.seal_from_receipt(waybill, receipt)
        ck.check("c07_ems_seal_deterministic",
                 resealed["seal"] == cred["seal"]
                 and ems.seal_from_receipt(waybill, receipt)["seal"]
                 == cred["seal"],
                 f"seal 确定性：两次重算同值 {cred['seal'][:16]}…（时钟不入"
                 " seal 语义）")

        # 失败不编轨迹（transport 异常/回执残缺两路＋值恒 None）
        def _boom(_w):
            raise RuntimeError("synth network down")

        qr_fail = ems.run_query(
            state_root / "ems",
            {"query_id": "q-fail", "matter_id": matter_f63,
             "items": [{"waybill_no": waybill}]}, transport=_boom)
        f_item = qr_fail["items"][0]

        def _bad_receipt(_w):
            return {"provider": "ems_synth", "retrieved_at": None,
                    "trace": "not-a-list"}

        qr_bad = ems.run_query(
            state_root / "ems",
            {"query_id": "q-bad", "matter_id": matter_f63,
             "items": [{"waybill_no": waybill}]}, transport=_bad_receipt)
        b_item = qr_bad["items"][0]
        ck.check("c08_ems_failure_no_trajectory",
                 f_item["status"] == "QUERY_FAILED"
                 and f_item["reason"] == "transport_failed:RuntimeError"
                 and f_item["trajectory"] is None
                 and f_item["credential"] is None
                 and b_item["status"] == "RECEIPT_INVALID"
                 and b_item["reason"]
                 == "f63_receipt_invalid:retrieved_at_missing"
                 and b_item["trajectory"] is None
                 and b_item["credential"] is None,
                 "失败不编轨迹：transport 异常→QUERY_FAILED；回执残缺→"
                 "RECEIPT_INVALID 具名理由；两路轨迹/凭证恒 None，绝不生成"
                 "部分/合成轨迹条目")

        # 费用纪律（E21 消费面）：float 具名拒；整型分入凭证
        def _float_cost(_w):
            r = synth_ems_receipt(_w)
            r["cost_cents"] = 3.5
            return r

        try:
            ems.seal_from_receipt(waybill, _float_cost(waybill))
            ck.check("c09_ems_cost_integer_cents_only", False,
                     "float 费用未拒收")
        except Exception as exc:  # noqa: BLE001
            ck.check("c09_ems_cost_integer_cents_only",
                     "f63_receipt_invalid:cost_not_integer_cents"
                     in err_text(exc),
                     f"float 费用具名拒→{exc}；整型分（300）入凭证"
                     f" cost_cents={cred.get('cost_cents')}（E21 消费面纪律"
                     "；真实费用计算走 JC 计算面授权后）")

        # 幂等回流＋冲突＋回读（F61 同构）
        replay = ems.run_query(
            state_root / "ems",
            {"query_id": "q-seal", "matter_id": matter_f63,
             "items": [{"waybill_no": waybill}]},
            transport=synth_ems_receipt)
        ck.check("c10_ems_idempotent_replay",
                 replay == qr_sealed, "同 query 同输入重放逐键相等（不双记）")
        try:
            ems.run_query(
                state_root / "ems",
                {"query_id": "q-seal", "matter_id": matter_f63,
                 "items": [{"waybill_no": "1130000000999"}]},
                transport=synth_ems_receipt)
            ck.check("c10_ems_conflict_refused", False, "异输入未拒")
        except Exception as exc:  # noqa: BLE001
            ck.check("c10_ems_conflict_refused",
                     "f63_query_conflict" in err_text(exc),
                     f"异输入→{exc}")
        read = bridge("ems.evidence_read", {"query_id": "q-seal"}, ems_cfg)
        ck.check("c10_ems_read_projection",
                 read == qr_sealed, "回读投影==回执")

        # 旁路字段具名拒（url/cookie 无隐式采集通道）
        bypass_ok = True
        detail_parts = []
        for field, value in (("url", "synth-bypass-value"),
                             ("cookie", "synth-bypass-value")):
            try:
                bridge("ems.evidence_query",
                       {"query_id": "q-neg-" + field,
                        "matter_id": matter_f63,
                        "items": [{"waybill_no": waybill, field: value}]},
                       ems_cfg)
                bypass_ok = False
                detail_parts.append(field + ":未拒")
            except Exception as exc:  # noqa: BLE001
                detail_parts.append(field + ":"
                                    + str("f63_field_forbidden" in err_text(exc)))
                bypass_ok = bypass_ok and \
                    "f63_field_forbidden:" + field in err_text(exc)
        try:
            bridge("ems.evidence_query",
                   {"query_id": "q-neg-top", "matter_id": matter_f63,
                    "ems_endpoint": "synth-bypass-value",
                    "items": [{"waybill_no": waybill}]}, ems_cfg)
            bypass_ok = False
            detail_parts.append("top:未拒")
        except Exception as exc:  # noqa: BLE001
            bypass_ok = bypass_ok and \
                "f63_field_forbidden:ems_endpoint" in err_text(exc)
            detail_parts.append("top:ems_endpoint 具名拒")
        ck.check("c11_ems_bypass_fields_refused", bypass_ok,
                 "url/cookie item 级＋顶层旁路字段全具名拒（"
                 + ";".join(detail_parts) + "；无隐式采集通道）")

        # E17 投影不变量：有凭据（真实回执）才记取得——扫状态根全查询账
        invariant_ok = True
        e17_detail = []
        for qpath in sorted((state_root / "ems" / "queries").glob("*.json")):
            qdata = json.loads(qpath.read_text(encoding="utf-8"))["receipt"]
            for entry in qdata["items"]:
                if entry["status"] == "EVIDENCE_SEALED":
                    c = entry["credential"]
                    good = bool(c) and bool(c.get("evidence_time_utc")) \
                        and bool(c.get("source_watermark")) \
                        and bool(c.get("seal")) \
                        and entry["trajectory"] is not None
                else:
                    good = entry["trajectory"] is None \
                        and entry["credential"] is None
                if not good:
                    invariant_ok = False
                    e17_detail.append(qpath.stem)
        ck.check("c12_ems_e17_projection_invariant", invariant_ok,
                 "E17 语义全账扫描：有凭据（真实回执）才记取得——"
                 "EVIDENCE_SEALED 必绑 时间/水印/seal；其余状态轨迹/凭证恒"
                 f" None（违例={e17_detail or '无'}）")

        # 产物面零 URL＋零 token 值
        blob = scan_tree_blob(state_root)
        hits = url_hits_in(blob)
        leak = SYNTH_TOKEN in blob
        ck.check("c13_ems_artifacts_zero_url_zero_token",
                 not hits and not leak,
                 f"F63 状态根全产物零 URL 字面量（{hits or '无'}）＋零 "
                 f"token 值泄漏={leak}")

        # ================================================================
        # F144 leg
        # ================================================================
        ok, detail = module_ast_audit(ENT_MODULE)
        ck.check("c14_ent_module_ast_no_network_no_url", ok, detail)

        try:
            bridge("enterprise.connector_status", {}, {})
            ck.check("c15_ent_fail_closed_state_root", False, "未抛")
        except Exception as exc:  # noqa: BLE001
            ck.check("c15_ent_fail_closed_state_root",
                     "enterprise_connector_state_root_not_configured"
                     in err_text(exc), f"状态根缺→{exc}")
        try:
            bridge("enterprise.explode", {}, ent_cfg)
            ck.check("c15_ent_fail_closed_unknown_method", False, "未抛")
        except Exception as exc:  # noqa: BLE001
            ck.check("c15_ent_fail_closed_unknown_method",
                     "method_not_connected:enterprise.explode"
                     in err_text(exc), f"未知方法→{exc}")

        # 连接器状态面：缺 Token 具名缺口＋形态声明＋不自采
        status = bridge("enterprise.connector_status", {}, ent_cfg)
        missing_envs = ["QCC_MCP_TOKEN", "TYC_MCP_TOKEN"]
        ck.check("c16_ent_status_named_gap",
                 status["form"] == "mcp_connector_no_self_collection"
                 and status["sessions_established"] == 0
                 and status["self_collection"] == "none"
                 and status["url_disclosure"] == "none"
                 and len(status["gaps"]) == 1
                 and status["gaps"][0]["reason"]
                 == "PAID_TOKEN_NOT_CONFIGURED"
                 and status["gaps"][0]["detail"]
                 == ";".join(missing_envs),
                 "connector_status：缺 token→PAID_TOKEN_NOT_CONFIGURED"
                 "（detail=QCC_MCP_TOKEN;TYC_MCP_TOKEN）不自采；连接器形态"
                 "声明＋零会话＋零 URL 披露")

        # 缺 Token 查询 → 不自采或编数据（值恒 None 非 {}）
        r_ent_notok = bridge("enterprise.diligence_query",
                             {"query_id": "q-ent-notok",
                              "matter_id": matter_f144,
                              "items": [{"provider": "qcc_mcp",
                                         "company_name":
                                         "合成市合成科技有限公司"}]}, ent_cfg)
        en_item = r_ent_notok["items"][0]
        ck.check("c17_ent_query_token_gap_values_none",
                 en_item["status"] == "TOKEN_NOT_CONFIGURED"
                 and en_item["reason"] == "PAID_TOKEN_NOT_CONFIGURED"
                 and en_item["data"] is None
                 and en_item["credential"] is None,
                 "缺 Token 查询→不自采或编数据：data/credential 恒 None"
                 "（非 {} 非占位企业字段；06 acceptance 逐字）")

        # 提供商闭集外具名拒（不预造未知连接器形态）
        try:
            bridge("enterprise.diligence_query",
                   {"query_id": "q-ent-badprov", "matter_id": matter_f144,
                    "items": [{"provider": "unknowncorp_mcp",
                               "company_name": "合成公司"}]}, ent_cfg)
            ck.check("c18_ent_provider_closed_set", False, "未拒")
        except Exception as exc:  # noqa: BLE001
            ck.check("c18_ent_provider_closed_set",
                     "f144_provider_unknown:unknowncorp_mcp"
                     in err_text(exc), f"闭集外 provider→{exc}")

        # token 在位：连接器会话未建＝客户端未建不可能自采（构造级）
        os.environ["QCC_MCP_TOKEN"] = SYNTH_TOKEN
        os.environ["TYC_MCP_TOKEN"] = SYNTH_TOKEN
        status2 = bridge("enterprise.connector_status", {}, ent_cfg)
        r_ent_sess = bridge("enterprise.diligence_query",
                            {"query_id": "q-ent-sess",
                             "matter_id": matter_f144,
                             "items": [{"provider": "tyc_mcp",
                                        "credit_code":
                                        "91340100SYNTH0001X"}]}, ent_cfg)
        es_item = r_ent_sess["items"][0]
        ck.check("c19_ent_session_absent_structural_unreachable",
                 status2["gaps"] == []
                 and es_item["status"] == "SESSION_ABSENT"
                 and es_item["reason"]
                 == "CONNECTOR_SESSION_ABSENT_PENDING_AUTHORIZATION"
                 and es_item["data"] is None
                 and es_item["credential"] is None
                 and r_ent_sess["sessions_established"] == 0,
                 "token 在位仍 SESSION_ABSENT——产品桥无已配置 MCP 连接器可"
                 "注入（真实接入属授权后配置），真实调用路径结构性不可达"
                 "（客户端未建不可能自采）")

        # 合成 MCP 回执转录（模块级注入合成会话＝显式合成材料）：
        # 出处/时间/额度绑定＋载荷只留 sha＋确定性 seal
        import enterprise_connector as ent
        qr_ent = ent.diligence_query(
            state_root / "ent",
            {"query_id": "q-ent-seal", "matter_id": matter_f144,
             "items": [{"provider": "qcc_mcp",
                        "company_name": "合成市合成科技有限公司"}]},
            session_factory=synth_session_factory)
        ed_item = qr_ent["items"][0]
        ecred = ed_item["credential"]
        sealed_ledger_text = (state_root / "ent" / "queries"
                              / "q-ent-seal.json").read_text(encoding="utf-8")
        ck.check("c20_ent_receipt_binds_source_time_quota",
                 ed_item["status"] == "DILIGENCE_RECORDED"
                 and ecred["provider"] == "qcc_mcp"
                 and ecred["retrieved_at"] == "2026-10-21T08:30:00Z"
                 and ecred["quota_remaining"] == 87
                 and len(ecred["source_watermark"]["payload_sha256"]) == 64
                 and ed_item["data"]["payload_sha256"]
                 == ecred["source_watermark"]["payload_sha256"]
                 and "合成市合成科技有限公司" not in sealed_ledger_text,
                 "MCP 回执转录：出处（provider 闭集）＋时间＋额度 87"
                 "（05:149 来源时点额度可见）绑定；企业数据原文不落账"
                 "（载荷只留 sha256＋字段计数；查询账原文零企业名实测）")
        recred = ent.record_from_receipt(
            {"provider": "qcc_mcp",
             "company_name": "合成市合成科技有限公司", "credit_code": None},
            SynthEnterpriseSession("qcc_mcp").query())
        ck.check("c20_ent_seal_deterministic",
                 recred["seal"] == ecred["seal"],
                 f"seal 确定性：重算同值 {ecred['seal'][:16]}…")

        # 失败不编数据（session 异常/回执残缺两路）
        def _boom_factory(_provider):
            raise RuntimeError("synth connector down")

        qr_ent_fail = ent.diligence_query(
            state_root / "ent",
            {"query_id": "q-ent-fail", "matter_id": matter_f144,
             "items": [{"provider": "qcc_mcp", "company_name": "合成公司"}]},
            session_factory=_boom_factory)
        ef_item = qr_ent_fail["items"][0]

        class _BadSession:
            def query(self, company_name=None, credit_code=None):
                return {"provider": "unknowncorp_mcp",
                        "retrieved_at": "2026-10-21T08:30:00Z",
                        "payload": {}}

        qr_ent_bad = ent.diligence_query(
            state_root / "ent",
            {"query_id": "q-ent-bad", "matter_id": matter_f144,
             "items": [{"provider": "tyc_mcp", "company_name": "合成公司"}]},
            session_factory=lambda _p: _BadSession())
        eb_item = qr_ent_bad["items"][0]

        class _NoQuotaSession:
            def query(self, company_name=None, credit_code=None):
                return {"provider": "tyc_mcp",
                        "retrieved_at": "2026-10-21T08:30:00Z",
                        "payload": {"k": "v"}}

        qr_ent_noquota = ent.diligence_query(
            state_root / "ent",
            {"query_id": "q-ent-noquota", "matter_id": matter_f144,
             "items": [{"provider": "tyc_mcp", "company_name": "合成公司"}]},
            session_factory=lambda _p: _NoQuotaSession())
        eq_item = qr_ent_noquota["items"][0]
        ck.check("c21_ent_failure_no_data",
                 ef_item["status"] == "QUERY_FAILED"
                 and ef_item["reason"] == "connector_failed:RuntimeError"
                 and ef_item["data"] is None
                 and eb_item["status"] == "RECEIPT_INVALID"
                 and eb_item["reason"]
                 == "f144_receipt_invalid:provider_not_in_closed_set"
                 and eb_item["data"] is None
                 and eq_item["status"] == "RECEIPT_INVALID"
                 and eq_item["reason"]
                 == "f144_receipt_invalid:quota_remaining_missing"
                 and eq_item["data"] is None,
                 "失败不编数据：session 异常→QUERY_FAILED；provider 闭集外/"
                 "缺额度→RECEIPT_INVALID 具名理由；三路 data/credential 恒"
                 " None，绝不编占位企业字段")

        # 旁路字段＋恰一查询键
        neg_ok = True
        neg_parts = []
        for field in ("url", "cookie"):
            try:
                bridge("enterprise.diligence_query",
                       {"query_id": "q-ent-neg-" + field,
                        "matter_id": matter_f144,
                        "items": [{"provider": "qcc_mcp",
                                   "company_name": "合成公司",
                                   field: "synth-bypass-value"}]}, ent_cfg)
                neg_ok = False
                neg_parts.append(field + ":未拒")
            except Exception as exc:  # noqa: BLE001
                neg_ok = neg_ok and \
                    "f144_field_forbidden:" + field in err_text(exc)
                neg_parts.append(field + ":具名拒")
        try:
            bridge("enterprise.diligence_query",
                   {"query_id": "q-ent-neg-both", "matter_id": matter_f144,
                    "items": [{"provider": "qcc_mcp",
                               "company_name": "合成公司",
                               "credit_code": "91340100SYNTH0001X"}]},
                   ent_cfg)
            neg_ok = False
            neg_parts.append("both-keys:未拒")
        except Exception as exc:  # noqa: BLE001
            neg_ok = neg_ok and \
                "f144_query_key_exactly_one_required" in err_text(exc)
            neg_parts.append("both-keys:具名拒")
        ck.check("c22_ent_bypass_and_key_discipline", neg_ok,
                 "url/cookie 旁路字段具名拒＋名称/信用代码恰一查询键（"
                 + ";".join(neg_parts) + "；不自采＝无隐式通道）")

        # 幂等回流＋冲突＋回读
        replay_ent = ent.diligence_query(
            state_root / "ent",
            {"query_id": "q-ent-seal", "matter_id": matter_f144,
             "items": [{"provider": "qcc_mcp",
                        "company_name": "合成市合成科技有限公司"}]},
            session_factory=synth_session_factory)
        ck.check("c23_ent_idempotent_replay", replay_ent == qr_ent,
                 "同 query 同输入重放逐键相等（不双记）")
        try:
            ent.diligence_query(
                state_root / "ent",
                {"query_id": "q-ent-seal", "matter_id": matter_f144,
                 "items": [{"provider": "tyc_mcp", "company_name": "别家"}]},
                session_factory=synth_session_factory)
            ck.check("c23_ent_conflict_refused", False, "异输入未拒")
        except Exception as exc:  # noqa: BLE001
            ck.check("c23_ent_conflict_refused",
                     "f144_query_conflict" in err_text(exc),
                     f"异输入→{exc}")
        read_ent = bridge("enterprise.diligence_read",
                          {"query_id": "q-ent-seal"}, ent_cfg)
        ck.check("c23_ent_read_projection", read_ent == qr_ent,
                 "回读投影==回执")

        # F144 产物面零 URL＋零 token 值
        ent_blob = scan_tree_blob(state_root / "ent")
        ent_hits = url_hits_in(ent_blob)
        ent_leak = SYNTH_TOKEN in ent_blob
        ck.check("c24_ent_artifacts_zero_url_zero_token",
                 not ent_hits and not ent_leak,
                 f"F144 状态根全产物零 URL 字面量（{ent_hits or '无'}）＋零 "
                 f"token 值泄漏={ent_leak}")

        evidence["f63"] = {
            "unauthorized": r_unauth, "token_gap": r_notok,
            "adapter_absent": r_adapter, "sealed": qr_sealed,
            "failure": qr_fail, "receipt_invalid": qr_bad,
            "credential": cred,
        }
        evidence["f144"] = {
            "status_unconfigured": status, "token_gap": r_ent_notok,
            "session_absent": r_ent_sess, "recorded": qr_ent,
            "failure": qr_ent_fail, "receipt_invalid_closed_set": qr_ent_bad,
            "receipt_invalid_quota": qr_ent_noquota,
            "credential": ecred,
        }
        return ck, evidence
    finally:
        for v, saved in env_snapshot.items():
            if saved is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = saved


def _strip_volatile(receipt: dict) -> dict:
    # 时变键（时间戳/授权账 digest——含各 profile 授权时刻）不参与跨
    # profile 确定性对照；其余（items 投影/counts/adapter/幂等键）逐键相等。
    return {k: v for k, v in receipt.items()
            if k not in ("recorded_at", "authorization_digest", "matter_id",
                         "query_id")}


def render_readme(family: str, profile: str, stamp: str) -> str:
    stem = (family.lower() + "-ems-negtest-recon-" + stamp
            if family == "F63"
            else family.lower() + "-enterprise-negtest-recon-" + stamp)
    return "\n".join([
        "# " + family + "／" + profile + " 证据（W4-U40 负测先行，裁决#8-12）",
        "",
        "- `" + stem + ".json`／`.md`：F63＋F144 外部 API 负测先行 recon 证据"
        "（双族同名同内容，族前缀区分；含授权探测、逐检清单、回收点具名）；",
        "- acceptance 向量（06 行）：F63＝EMS 轨迹与取证时间/来源水印凭证真实"
        "生成；失败不编轨迹——F144＝企查查/天眼查 MCP 实际授权调用/出处/时间；"
        "缺 Token 不自采或编数据；",
        "- 本目录现载＝负测先行段证据（未授权/未接线态调用路径结构性不可达＋"
        "合成回执封存/转录逻辑）；真实授权调用实测属授权后补联测（回收点具名"
        "见 recovery_points，写回台账 failure_reason）；",
        "- 全程合成材料；不 push。",
    ]) + "\n"


def render_md(profile: str, checks: Checks, cross_rows: list,
              payload: dict) -> str:
    lines = [
        f"# F63＋F144 外部 API 负测先行 recon 证据（{profile}，W4-U40）", "",
        "裁决#8-12（五项外部 API 统一负测先行：禁编 URL/失败不造假，授权后"
        "补）为唯一执行态；真实授权调用属授权后补联测（回收点具名如下）。",
        "",
        "## 回收点（具名，写回台账 failure_reason）",
        f"- {RECOVERY_F63}",
        f"- {RECOVERY_F144}",
        "## 负测先行纪律（结构性事实）",
        "- 未授权动作→ACTION_NOT_AUTHORIZED 值恒 None；缺 token→"
        "PAID_TOKEN_NOT_CONFIGURED（W2a-U13 先例同码）不自采；",
        "- 已授权＋token 在位仍 ADAPTER_ABSENT / SESSION_ABSENT——客户端未"
        "建不可能自采（P11 构造即拒同构；端点禁编 URL）；",
        "- 凭证只从真实回执转录并绑定 取证时间/来源水印（E17 语义＝有凭据"
        "才记取得）；失败不编轨迹/不编数据；",
        "- 两产品模块＋本 recon AST 级：导入闭集零网络模块、字符串常量零 "
        "URL 模式、标识符零旁路关键字；状态根产物零 URL 零 token 值。",
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
    ap.add_argument("--profile", action="append", default=None,
                    help="验收 profile（可多次；默认 desktop+selfhost）")
    ap.add_argument("--state-root-prefix", type=Path, default=None,
                    help="状态根前缀（默认临时目录）")
    ap.add_argument("--keep-temp", action="store_true",
                    help="保留默认临时状态根（调试用）")
    args = ap.parse_args(argv)
    if not args.profile:
        args.profile = ["desktop", "selfhost"]

    started = time.time()
    tmp_ctx = None
    if args.state_root_prefix is None:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="juscite-f63f144-")
        args.state_root_prefix = Path(tmp_ctx.name)
        if args.keep_temp:
            # 保留：改为固定前缀目录（不再走 TemporaryDirectory 清理）。
            args.state_root_prefix = (Path(tempfile.gettempdir())
                                      / "juscite-f63f144-keep")
            args.state_root_prefix.mkdir(parents=True, exist_ok=True)
            tmp_ctx = None
    args.state_root_prefix.mkdir(parents=True, exist_ok=True)

    try:
        bridge = load_bridge()
    except Exception as exc:  # noqa: BLE001
        eprint(f"[ENV] 桥不可用: {type(exc).__name__}: {exc}")
        return 3

    eprint(f"== W4-U40 F63+F144 recon profiles={args.profile} "
           f"state_root_prefix={args.state_root_prefix}")

    all_checks: list[Checks] = []
    per_profile_evidence: dict = {}
    ok = True
    for profile in args.profile:
        eprint(f"==== profile {profile} ====")
        ck, evidence = run_profile(profile, args, bridge)
        all_checks.append(ck)
        per_profile_evidence[profile] = evidence
        ok = ok and ck.failed == 0

    # -- 跨 profile 投影一致性（剥时变键逐键相等；F61 c19 先例）------------
    cross_rows: list[dict] = []
    self_ok, self_detail = self_ast_audit()
    cross_rows.append({
        "id": "c00_recon_self_ast_no_url_no_network",
        "ok": self_ok,
        "detail": self_detail + "（W4-U03 N4 先例：面与工具双双自检）",
    })
    ok = ok and self_ok
    cross_ok = len(args.profile) >= 2
    if cross_ok:
        base_ems = _strip_volatile(
            per_profile_evidence[args.profile[0]]["f63"]["sealed"])
        base_ent = _strip_volatile(
            per_profile_evidence[args.profile[0]]["f144"]["recorded"])
        for other in args.profile[1:]:
            if _strip_volatile(
                    per_profile_evidence[other]["f63"]["sealed"]) != base_ems:
                cross_ok = False
                break
            if _strip_volatile(
                    per_profile_evidence[other]["f144"]["recorded"]) != \
                    base_ent:
                cross_ok = False
                break
    cross_rows.append({
        "id": "c25_cross_profile_projection_equal",
        "ok": cross_ok,
        "detail": "跨 profile F63 封存/F144 转录投影剥时变键逐键相等"
                  "（合成回执的确定性面）" if cross_ok else
                  "跨 profile 投影漂移（确定性破约）",
    })
    ok = ok and cross_ok
    cross_rows.append({
        "id": "c26_recovery_points_named",
        "ok": bool(RECOVERY_F63) and bool(RECOVERY_F144),
        "detail": "授权后补联测回收点具名（F63 EMS 适配器＋F144 MCP 连接器"
                  "授权）；真实轨迹/调用实测归回收点，本波不假销账",
    })

    payload = {
        "schema": "juscite-f63-f144-external-api-negtest-recon/1",
        "unit": "W4-U40",
        "obligations": ["F63-desktop", "F63-selfhost",
                        "F144-desktop", "F144-selfhost"],
        "ruling": "00-总协调 §6.1 裁决#8-12 统一负测先行（禁编 URL/失败不"
                  "造假，授权后补）；F144-v2（13 件套全量 v2）归 W5 不前造",
        "recovery_points": {"F63": RECOVERY_F63, "F144": RECOVERY_F144},
        "started_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "run_date": RUN_DATE,
        "command": ("python -X utf8 "
                    "tools/PENDING_OWNER_f63_f144_external_api_negtest_recon"
                    ".py --profile desktop --profile selfhost"),
        "modules": {"ems_evidence": sha256_file(EMS_MODULE),
                    "enterprise_connector": sha256_file(ENT_MODULE)},
        "finished_at": None,
        "duration_s": None,
    }
    payload["checks"] = {"cross": cross_rows}
    for idx, profile in enumerate(args.profile):
        payload["checks"][profile] = all_checks[idx].rows
        payload[profile] = per_profile_evidence[profile]
    payload["finished_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    payload["duration_s"] = round(time.time() - started, 1)
    payload["overall"] = "RECON_OK" if ok else "RECON_FAIL"
    payload["passed"] = sum(c.passed for c in all_checks) + \
        sum(1 for r in cross_rows if r["ok"])
    payload["total"] = sum(len(c.rows) for c in all_checks) + len(cross_rows)

    # -- 证据落盘（台账 evidence_path＝顶层面 evidence/F63|F144/<profile>/；
    #     两族各落族前缀同名证据＋README）----------------------------------
    ev_root = REPO / "evidence"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for family in ("F63", "F144"):
        stem = (family.lower() + "-ems-negtest-recon-" + stamp
                if family == "F63"
                else family.lower() + "-enterprise-negtest-recon-" + stamp)
        for profile in args.profile:
            out_dir = ev_root / family / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / (stem + ".json")).write_text(
                json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
            (out_dir / (stem + ".md")).write_text(
                render_md(profile,
                          all_checks[args.profile.index(profile)],
                          cross_rows, payload),
                encoding="utf-8")
            (out_dir / "README.md").write_text(
                render_readme(family, profile, stamp), encoding="utf-8")

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
