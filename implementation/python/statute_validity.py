# -*- coding: utf-8 -*-
"""F64(v1/v1.5)/F69 法条效力产品面（工单 W2a-U13；v1.5 段 W4-U41）。

本地优先来源策略＋法条效力状态产品化。全部法源消费经 W2a-U12 冻结的
lccc_consumer 公开统一面（E22 冻结 v1.0：只读、零网络、零写入），本模块
不绕面直读正式表、不重建效力算法、不编 URL、不自采付费源。

F64 v1.5（06 行 F64 acceptance v1.5 段，W4-U41）：付费通道裁决#8-12
负测先行（P11 请求面以合成 mock 端点实测真实 HTTP 往返，真授权后补，
产品面仍不发起付费/web 取数）；web 兜底段=web-verified 声明机制
（statute.web_declaration 分账声明，永不冒数据库核验签名）。

F64 v1 冻结（06 行 F64 acceptance v1 段）：
  - 确定性降级链 本地→付费→web 写进检索策略，顺序不可跳级；
  - v1 只执行本地段；付费/web 段为具名声明缺口，实测归 F64-v1.5 独立
    实例（B4，E27 复合对账已拆行）——本面绝不发起付费/web 取数；
  - 付费段状态=P11 付费 consumer（codices tools/commercial_law_mcp.py）
    token 在位性：未配置→具名缺口 PAID_TOKEN_NOT_CONFIGURED（不自采）。
    只查在位，不读 token 值（14-Python入口与施工接线.md P11 行）。

F69 产品化（06 行 F69 acceptance）：
  - 按适用时点（as_of，YYYYMMDD）定位版本/状态/替代；状态采信本地面
    SXX==DE_01018 一致时的值；施行窗口 SXRQ<=as_of<SHXRQ（施行日当天
    生效、失效日当天已失效）；
  - 缺日期/缺编码/冲突→unknown，不签现行（signs_current 恒 False）；
  - 引证闸：被废除（已废止/已修改/已失效）检索到也不许引——decision
    恒非 ALLOWED；替代链数据缺→replacement=unknown 不编造（E22 冻结面
    v1.0：legal_relations 现为空表，无替代链）。
"""

from __future__ import annotations

import os
import sys

from bridge_errors import NotConnected

# ---------------------------------------------------------------------- #
# F64 v1 冻结常量
# ---------------------------------------------------------------------- #

# 确定性降级链：顺序冻结，不可跳级（06 行 F64：本地→付费→web 兜底）。
SOURCE_CHAIN_V1 = ("local", "paid", "web")
CHAIN_VERSION = "v1"
DEGRADATION_POLICY = "local_first_no_silent_escalation"

# v1 各段状态：本地=已执行；付费/web=具名声明缺口（实测归 F64-v1.5/B4）。
SEGMENT_STATE_V1 = {
    "local": "executed",
    "paid": "declared_gap_pending_F64-v1.5(B4)",
    "web": "declared_gap_pending_F64-v1.5(B4)",
}

# P11 付费 consumer 的 token 环境变量（commercial_law_mcp.py PROVIDERS
# 冻结镜像；只取公开键名，不取 URL——本面零 URL 披露）。
PAID_TOKEN_ENV_VARS = ("YUANDIAN_MCP_TOKEN", "PKULAW_MCP_TOKEN")

LOCAL_FACE_NAME = "lccc_consumer(E22 freeze v1.0)"

# ---------------------------------------------------------------------- #
# F69 引证闸决策码
# ---------------------------------------------------------------------- #

DECISION_ALLOWED = "ALLOWED"
DECISION_BLOCKED = "BLOCKED"
DECISION_UNKNOWN = "UNKNOWN"

# 已被替代/不再现行的状态标签（E22 冻结面 SUPERSEDED_CODES 的中文镜像）
SUPERSEDED_LABELS = ("已修改", "已废止", "已失效")

REPLACEMENT_UNKNOWN_REASON = (
    "legal_relations 空表（E22 冻结面 v1.0：替代链数据缺，恒 unknown 不编造）"
)


def _lccc(config: dict):
    """经冻结公开面取 LcccConsumer；未配置/面缺→具名 NotConnected。"""
    import_path = config.get("codices_import_path")
    formal_root = config.get("codices_formal_root")
    if not import_path:
        raise NotConnected("codices_import_path_not_configured")
    if not formal_root:
        raise NotConnected("codices_formal_root_not_configured")
    if import_path not in sys.path:
        sys.path.insert(0, import_path)
    try:
        import lccc_consumer
    except ImportError as exc:
        raise NotConnected("lccc_consumer_not_importable:" + str(exc)) from None
    try:
        return lccc_consumer.LcccConsumer(formal_root)
    except FileNotFoundError as exc:
        raise NotConnected("lccc_formal_face_incomplete:" + str(exc)) from None


def _paid_gap() -> dict:
    """付费段具名缺口。只查 token 在位性，不读值、不发请求。"""
    missing = [
        var for var in PAID_TOKEN_ENV_VARS
        if not os.environ.get(var, "").strip()
    ]
    if missing:
        return {
            "reason": "PAID_TOKEN_NOT_CONFIGURED",
            "detail": ";".join(missing),
            "self_collection": "none",
        }
    return {
        "reason": "PAID_TOKEN_PRESENT_NOT_EXERCISED_IN_V1",
        "self_collection": "none",
        "note": "v1 不发起付费取数；合法付费连接实测归 F64-v1.5(B4)",
    }


def _degradation(gap_reasons: list) -> dict:
    """F64 v1 降级链声明：本地已执行，付费/web 具名缺口，零跳级零自采。"""
    return {
        "chain": list(SOURCE_CHAIN_V1),
        "policy": DEGRADATION_POLICY,
        "version": CHAIN_VERSION,
        "segments": dict(SEGMENT_STATE_V1),
        "escalated": False,
        "gap_declared": bool(gap_reasons),
        "gap_reasons": list(gap_reasons),
        "url_disclosure": "none",
        "note": "v1 只执行本地段；缺口具名声明不静默跳级、不自采、不编 URL",
    }


def source_strategy(config: dict) -> dict:
    """F64 v1 检索策略冻结面：降级链＋各段状态＋付费具名缺口。"""
    segments = {
        "local": {
            "state": SEGMENT_STATE_V1["local"],
            "face": LOCAL_FACE_NAME,
            "config_keys": ["codices_import_path", "codices_formal_root"],
        },
        "paid": {
            "state": SEGMENT_STATE_V1["paid"],
            "gap": _paid_gap(),
        },
        "web": {
            "state": SEGMENT_STATE_V1["web"],
            "gap": {
                "reason": "WEB_FALLBACK_PENDING_F64_V1_5_B4",
                "url_policy": "fabrication_forbidden",
            },
        },
    }
    return {
        "chain": list(SOURCE_CHAIN_V1),
        "version": CHAIN_VERSION,
        "frozen": True,
        "policy": DEGRADATION_POLICY,
        "segments": segments,
        "web_verified_note": "web-verified 不冒数据库核验（06 行 F64 acceptance）",
    }


def _identifier(args: dict) -> tuple:
    wjbs = args.get("wjbs")
    code31 = args.get("code31")
    if bool(wjbs) == bool(code31):
        raise NotConnected("statute_identifier_exactly_one_required")
    if wjbs is not None and not isinstance(wjbs, str):
        raise NotConnected("statute_wjbs_must_be_string")
    if code31 is not None and not isinstance(code31, str):
        raise NotConnected("statute_code31_must_be_string")
    return wjbs, code31


def resolve(config: dict, args: dict) -> dict:
    """本地优先单段执行：经冻结面定位时点/状态/替代＋降级链缺口声明。

    本地面任何 unknown/未命中都只产生具名缺口，绝不触发付费/web 段，
    也绝不伪零命中（失败显式入 gap_reasons）。
    """
    wjbs, code31 = _identifier(args)
    as_of = args.get("as_of")
    if as_of is not None and not isinstance(as_of, str):
        raise NotConnected("statute_as_of_must_be_string")
    consumer = _lccc(config)
    face = consumer.resolve_effectivity(wjbs=wjbs, code31=code31, as_of=as_of)
    result = dict(face)
    result["source"] = "local:" + LOCAL_FACE_NAME
    result["timepoint_positioned"] = as_of is not None
    if result.get("replacement") == "unknown":
        result["replacement_reason"] = REPLACEMENT_UNKNOWN_REASON
    gap_reasons = list(face.get("reasons") or [])
    if not face.get("found"):
        gap_reasons.append("LOCAL_FACE_NOT_FOUND")
    elif face.get("status_label") == "unknown":
        gap_reasons.append("LOCAL_FACE_STATUS_UNKNOWN")
    result["degradation"] = _degradation(gap_reasons)
    return result


def citation_gate(config: dict, args: dict) -> dict:
    """F69 引证闸：按适用时点定可引性，被废除检索到也不许引。

    decision ∈ {ALLOWED, BLOCKED, UNKNOWN}：
      ALLOWED  仅当定位成功＋结构核对全过＋状态=有效＋as_of 窗口内；
      BLOCKED  已废止/已修改/已失效（恒不 许引）或窗口明确未到；
      UNKNOWN  缺 as_of/缺编码/冲突/窗口不可定——fail-closed 不签现行。
    """
    wjbs, code31 = _identifier(args)
    as_of = args.get("as_of")
    if as_of is None:
        # 缺适用时点：不签现行（fail-closed）。仍回读基线定位供上下文。
        basis = resolve(config, {"wjbs": wjbs, "code31": code31})
        return _gate_result(
            basis, DECISION_UNKNOWN, "AS_OF_REQUIRED_FAIL_CLOSED",
            ["缺适用时点（as_of）：时点定位不可做，不签现行"],
        )
    if not isinstance(as_of, str):
        raise NotConnected("statute_as_of_must_be_string")
    basis = resolve(config, {"wjbs": wjbs, "code31": code31, "as_of": as_of})
    reasons = list(basis.get("reasons") or [])
    status = basis.get("status_label")
    window = basis.get("in_force_window")
    checks = basis.get("checks") or []
    structural_ok = all(c.get("result") == "pass" for c in checks)

    if not basis.get("found"):
        return _gate_result(
            basis, DECISION_UNKNOWN,
            "NOT_FOUND_UNKNOWN:" + (_first(reasons) or "LOCAL_FACE_NOT_FOUND"),
            reasons,
        )
    if not structural_ok:
        # 缺编码/码体冲突/日期字段畸形等结构缺口 → unknown 不签现行
        return _gate_result(
            basis, DECISION_UNKNOWN,
            "FACE_STRUCTURAL_GAP_FAIL_CLOSED:" + (_first(reasons) or "STRUCTURAL"),
            reasons,
        )
    if "AS_OF_MALFORMED" in reasons:
        return _gate_result(
            basis, DECISION_UNKNOWN, "AS_OF_MALFORMED_FAIL_CLOSED", reasons,
        )
    if status == "已废止":
        return _gate_result(
            basis, DECISION_BLOCKED, "ABOLISHED_NOT_CITABLE",
            reasons + ["被废除检索到也不许引（06 行 F69 preserved）"],
        )
    if status in ("已修改", "已失效"):
        return _gate_result(
            basis, DECISION_BLOCKED, "SUPERSEDED_NOT_CITABLE",
            reasons + ["已被替代版本提示=unknown；被替代检索到也不许引"],
        )
    if status == "unknown":
        return _gate_result(
            basis, DECISION_UNKNOWN, "STATUS_UNKNOWN_FAIL_CLOSED", reasons,
        )
    if status == "尚未施行":
        if window == "unknown":
            return _gate_result(
                basis, DECISION_UNKNOWN,
                "STATUS_WINDOW_CONFLICT_FAIL_CLOSED", reasons,
            )
        return _gate_result(
            basis, DECISION_BLOCKED, "NOT_YET_IN_FORCE_AT_AS_OF", reasons,
        )
    # status == "有效"（SXX=01 且 SXX==DE_01018 一致）
    if window == "unknown":
        return _gate_result(
            basis, DECISION_UNKNOWN, "WINDOW_UNKNOWN_FAIL_CLOSED", reasons,
        )
    if window == "no":
        return _gate_result(
            basis, DECISION_BLOCKED, "NOT_YET_IN_FORCE_AT_AS_OF",
            reasons + (["BEFORE_EFFECTIVE_DATE_AT_AS_OF"]
                       if "BEFORE_EFFECTIVE_DATE_AT_AS_OF" not in reasons else []),
        )
    # window == yes 且状态有效 → 时点现行可引
    return _gate_result(
        basis, DECISION_ALLOWED, "CURRENT_IN_FORCE_CITABLE", reasons,
    )


# ---------------------------------------------------------------------- #
# F64 v1.5：web-verified 声明机制（工单 W4-U41；06 行 F64 acceptance
# v1.5 段＝合法付费连接/web 兜底各实测，web-verified 不冒数据库核验）
# ---------------------------------------------------------------------- #
# 降级链 web 兜底段的来源声明面：调用方携 web 取证事实进来，本面产
# web_verified 分账声明——核验 basis 闭集三账分立（本地冻结面／P11 商业库
# ／web 兜底），web 声明键集结构性不含数据库核验签名键。本面只声明不取
# 数：零网络（v1 同款 AST 白名单纪律）、URL 只转录取证事实（禁编 URL）、
# URL scheme 白名单外具名拒。

WEB_DECLARATION_SCHEMA = "juscite-f64-web-verified/1"

# 核验 basis 闭集：web_verified ≠ verified（数据库核验）分账。
VERIFICATION_BASIS_LOCAL_DB = "local_db_verified"  # E22 lccc 冻结面（v1 已实测）
VERIFICATION_BASIS_PAID_DB = "paid_db_verified"    # P11 商业库（真授权后补）
VERIFICATION_BASIS_WEB = "web_verified"            # web 兜底（本段）
VERIFICATION_BASIS_UNKNOWN = "unknown"             # fail-closed

# 数据库核验签名键（P11 注册表行 fieldnames＋本地冻结面取文签）：
# web 声明键集与之零交＝永不冒数据库核验签名。
DB_SIGNATURE_KEYS = frozenset({
    "source_type", "provider_record_id", "provider_url", "provider",
    "face_sha256", "lccc_face",
})

WEB_DECLARATION_REQUIRED_EVIDENCE = ("source_url", "content_sha256",
                                     "retrieved_utc")
WEB_URL_SCHEMES = ("http://", "https://")


def declare_web_verified(args: dict) -> dict:
    """web 兜底来源声明面：取证事实→web_verified 分账声明。

    缺任一取证要素/形态非法→具名拒（不编造声明、不编 URL）；输出
    verification_basis 恒 web_verified、signs_current 恒 False（web 来源
    不签现行——现行签名只出本地冻结面）。零网络：取证事实由调用方提供。
    """
    missing = [key for key in WEB_DECLARATION_REQUIRED_EVIDENCE
               if not str(args.get(key) or "").strip()]
    if missing:
        raise NotConnected(
            "web_declaration_evidence_missing:" + ";".join(missing))
    source_url = str(args["source_url"]).strip()
    if not source_url.startswith(WEB_URL_SCHEMES):
        raise NotConnected("web_declaration_url_scheme_not_allowed")
    content_sha256 = str(args["content_sha256"]).strip().lower()
    if (len(content_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in content_sha256)):
        raise NotConnected("web_declaration_content_sha256_malformed")
    return {
        "schema": WEB_DECLARATION_SCHEMA,
        "verification_basis": VERIFICATION_BASIS_WEB,
        "signs_current": False,
        "source_url": source_url,
        "content_sha256": content_sha256,
        "retrieved_utc": str(args["retrieved_utc"]).strip(),
        "note": "web-verified 分账声明：网页来源取证事实，永不冒数据库核验签名",
    }


def _first(reasons: list):
    return reasons[0] if reasons else ""


def _gate_result(basis: dict, decision: str, code: str, reasons: list) -> dict:
    result = {
        "identifier": basis.get("identifier"),
        "decision": decision,
        "code": code,
        "status_label": basis.get("status_label"),
        "in_force_window": basis.get("in_force_window"),
        "signs_current": basis.get("signs_current") is True and decision == DECISION_ALLOWED,
        "replacement": basis.get("replacement"),
        "replacement_reason": basis.get("replacement_reason", ""),
        "reasons": list(reasons),
        "degradation": basis.get("degradation"),
    }
    return result


def statute_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发（statute.*）。未列方法绝不落到这里。"""
    if method == "statute.source_strategy":
        return source_strategy(config)
    if method == "statute.resolve":
        return resolve(config, args)
    if method == "statute.citation_gate":
        return citation_gate(config, args)
    if method == "statute.web_declaration":
        return declare_web_verified(args)
    raise NotConnected("statute_method_not_in_frozen_list:" + method)
