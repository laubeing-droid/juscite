"""F144 企业查询/对手背景调查——MCP 连接器接入与尽调查询账公开面
（W4-U40 负测先行）。

06 行 F144 acceptance：企查查/天眼查 MCP 实际授权调用/出处/时间；缺
Token 不自采或编数据。2026-10-13 用户拍板（06 source_stage）：走 MCP
连接器接入企查查/天眼查，不自采数据；WorkBuddy 连接器市场实证该形态；
13 件套全量 v2=F144-v2 归 W5 不前造。05:149：合法 MCP/API，来源时点
额度可见，不自采。00-总协调 §6.1 裁决#8-12（统一负测先行：禁编 URL/
失败不造假，授权后补）为本波唯一执行态——真实 MCP 授权调用的实测属
授权后补联测（回收点具名见 recon 证据与本单台账 failure_reason）。

负测先行结构（W2a-U13 P11 先例＋W2b-U57 检索梯子先例＋W3-U13 F61 先例
同构）：

- 提供商目录：闭集类别名 qcc_mcp/tyc_mcp（名字只取 W4 类别名，零 URL
  ——连接器形态下端点由用户 MCP 配置提供，产品面不编 URL，AST 级断言
  见 recon/test）。
- token 在位性（connector_status）：未配置→具名缺口
  PAID_TOKEN_NOT_CONFIGURED（W2a-U13 先例同码，detail 具名缺哪个 env），
  只查在位不读值、不建会话、不自采、不编企业数据（值恒 None 非 {}）。
- 尽调查询（diligence_query）：唯一数据通道＝本桥注入的 session 工厂
  （MCP 连接器会话）；本波产品桥无已配置连接器可注入（真实接入属授权
  后配置）→ token 在位也只会得到具名缺口 CONNECTOR_SESSION_ABSENT——
  未授权/未接线态真实调用路径结构性不可达（客户端未建不可能自采）。
- 回执转录（record_from_receipt）：企业数据只从真实 MCP 回执转录——
  出处（provider 闭集内）＋时间（retrieved_at）＋额度（quota_remaining，
  05:149 来源时点额度可见）＋载荷 sha256 水印绑定；seal=确定性 sha256
  （同回执两跑同字节同 seal）。E17 EvidenceAttempt 语义：有凭据（真实
  回执）才记取得——无回执条目 data/credential 恒 None，绝不编占位企业
  字段。
- 失败不编数据：session 工厂异常→QUERY_FAILED；回执残缺（provider 闭
  集外/缺 retrieved_at/缺 quota/payload 非对象）→RECEIPT_INVALID 具名
  理由，值恒 None。
- 字段闭集：url/cookie 等采集旁路字段 item 级＋顶层 typed 具名拒（无
  隐式采集通道——不自采数据是结构性事实）。
- 幂等回流：同 query_id 同输入重放同回执（不双记）；异输入具名 conflict。
- 敏感红线：条目投影只带状态/哈希/额度/具名理由——token 值、URL、
  企业数据原文不回传不落账（载荷只留 sha256 与声明字段计数）。

确定性纪律：查询输入全部显式比较；recorded_at 仅溯源展示不入幂等键
（幂等键=输入 digest）；本模块零网络依赖（导入闭集见 recon C01 AST
断言）。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f144-enterprise-connector/1"

# 提供商类别闭集（类别名，零 URL——连接器形态端点由用户 MCP 配置提供，
# 产品面禁编 URL）。新增提供商须扩此闭集入账，不得隐式放行。
PROVIDER_CATEGORIES = ("qcc_mcp", "tyc_mcp")

# token 环境变量（产品约定；只查在位性，不读值——W2a-U13 先例同纪律）。
TOKEN_ENV_VARS = {"qcc_mcp": "QCC_MCP_TOKEN", "tyc_mcp": "TYC_MCP_TOKEN"}

# 条目状态闭集。
ENTRY_STATUSES = (
    "DILIGENCE_RECORDED",      # 真实 MCP 回执转录完成（出处/时间/额度绑定）
    "RECEIPT_INVALID",         # 回执残缺/provider 闭集外（失败不编数据）
    "QUERY_FAILED",            # session 工厂异常（失败不编数据）
    "SESSION_ABSENT",          # 连接器会话未建（客户端未建不可能自采）
    "TOKEN_NOT_CONFIGURED",    # 缺 token（PAID_TOKEN_NOT_CONFIGURED 不自采）
)

# 值字段（企业数据/凭证）只允许在 DILIGENCE_RECORDED 非空；其余恒 None。
VALUE_BEARING_STATUSES = ("DILIGENCE_RECORDED",)

QUERY_FIELD_WHITELIST = ("query_id", "matter_id", "items")
ITEM_FIELD_WHITELIST = ("provider", "company_name", "credit_code")


class EnterpriseConnectorError(ValueError):
    """typed 错误：str(self) 只有错误码，企业数据原文/token 值不进错误码。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _require_str(value, code: str, *, max_len: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise EnterpriseConnectorError(code)
    return value


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                              sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# token 在位性与连接器状态（只查在位，不读值，不建会话）
# ---------------------------------------------------------------------------

def _token_state(provider: str) -> dict:
    env = TOKEN_ENV_VARS[provider]
    if not os.environ.get(env, "").strip():
        return {"provider": provider, "token_env": env, "present": False,
                "reason": "PAID_TOKEN_NOT_CONFIGURED",
                "self_collection": "none"}
    return {"provider": provider, "token_env": env, "present": True,
            "reason": None, "self_collection": "none",
            "note": "token 在位不等于已接线；连接器会话未建仍不发起查询"}


def connector_status() -> dict:
    """连接器形态状态面：逐提供商 token 在位性＋形态声明＋缺口具名。

    本面永不建立连接器会话、永不自采（05:149 不自采＝结构性；真实 MCP
    授权调用属授权后补联测回收点）。
    """
    states = [_token_state(p) for p in PROVIDER_CATEGORIES]
    missing = [s["token_env"] for s in states if not s["present"]]
    return {
        "schema": SCHEMA,
        "form": "mcp_connector_no_self_collection",
        "providers": states,
        "gaps": [{
            "reason": "PAID_TOKEN_NOT_CONFIGURED",
            "detail": ";".join(missing),
            "self_collection": "none",
        }] if missing else [],
        "sessions_established": 0,
        "self_collection": "none",
        "url_disclosure": "none",
    }


# ---------------------------------------------------------------------------
# 回执转录（企业数据只从真实 MCP 回执转录；E17 语义：有凭据才记取得）
# ---------------------------------------------------------------------------

def _validate_receipt(receipt) -> list[str]:
    """MCP 回执合同闭集校验；返回具名缺口列表（空＝合格）。"""
    problems: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt_not_object"]
    provider = receipt.get("provider")
    if provider is None:
        problems.append("provider_missing")
    elif provider not in PROVIDER_CATEGORIES:
        problems.append("provider_not_in_closed_set")
    retrieved_at = receipt.get("retrieved_at")
    if retrieved_at is None:
        problems.append("retrieved_at_missing")
    elif not isinstance(retrieved_at, str) or not retrieved_at:
        problems.append("retrieved_at_invalid")
    if receipt.get("quota_remaining") is None:
        # 来源时点额度可见（05:149）——回执缺额度即残缺。
        problems.append("quota_remaining_missing")
    elif isinstance(receipt.get("quota_remaining"), bool) or \
            not isinstance(receipt.get("quota_remaining"), int):
        problems.append("quota_remaining_not_integer")
    if not isinstance(receipt.get("payload"), dict):
        problems.append("payload_not_object")
    return problems


def record_from_receipt(args: dict, receipt: dict) -> dict:
    """从真实 MCP 回执确定性转录：出处/时间/额度/载荷水印绑定。

    纯函数（同输入两跑同字节同 seal）；企业数据原文不落账——载荷只留
    sha256 与声明字段计数。
    """
    problems = _validate_receipt(receipt)
    if problems:
        raise EnterpriseConnectorError(
            "f144_receipt_invalid:" + problems[0])
    payload = receipt["payload"]
    payload_digest = _sha256_bytes(_canonical(payload).encode("utf-8"))
    query_digest = _sha256_bytes(_canonical(args).encode("utf-8"))
    core = {
        "query_digest": query_digest,
        "provider": receipt["provider"],
        "receipt_sha256": payload_digest,
        "retrieved_at": receipt["retrieved_at"],
        "quota_remaining": receipt["quota_remaining"],
    }
    return {
        "kind": "f144_diligence_credential/1",
        "provider": receipt["provider"],
        "retrieved_at": receipt["retrieved_at"],
        "quota_remaining": receipt["quota_remaining"],
        "source_watermark": {
            "payload_sha256": payload_digest,
            "origin": "mcp_receipt_transcription",
        },
        "payload_field_count": len(payload),
        "seal": _sha256_bytes(_canonical(core).encode("utf-8")),
    }


def _entry(provider, status: str, reason, data, credential):
    return {"provider": provider, "status": status, "reason": reason,
            "data": data, "credential": credential}


def diligence_query(state_root, args: dict, *, session_factory) -> dict:
    """按闭集提供商批次执行尽调查询并转录回执账。

    session_factory＝本桥注入的唯一数据通道（可调用
    provider→MCP session（query(company_name, credit_code)→receipt））；
    本模块绝不自行建立会话（零网络依赖＝结构性）。session_factory=None
    （本波产品桥常态：连接器未配置）→ token 在位也只会得到
    SESSION_ABSENT 具名缺口——真实调用路径结构性不可达。
    """
    root = Path(state_root)
    unknown_fields = sorted(set(args) - set(QUERY_FIELD_WHITELIST))
    if unknown_fields:
        raise EnterpriseConnectorError(
            "f144_field_forbidden:" + unknown_fields[0])
    query_id = _require_str(args.get("query_id"),
                            "f144_query_id_required", max_len=128)
    _require_str(args.get("matter_id"), "f144_matter_id_required",
                 max_len=128)
    items_raw = args.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise EnterpriseConnectorError("f144_items_required")

    digest = _sha256_bytes(_canonical(args).encode("utf-8"))
    path = _query_path(root, query_id)
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("input_digest") == digest:
            return dict(existing["receipt"])
        raise EnterpriseConnectorError("f144_query_conflict")

    projections: list[dict] = []
    sessions_established = 0
    for raw in items_raw:
        if not isinstance(raw, dict):
            raise EnterpriseConnectorError("f144_item_invalid")
        unknown_item_fields = sorted(set(raw) - set(ITEM_FIELD_WHITELIST))
        if unknown_item_fields:
            # 负测先行：url/cookie 等旁路字段具名拒——不自采＝无隐式通道。
            raise EnterpriseConnectorError(
                "f144_field_forbidden:" + unknown_item_fields[0])
        provider = raw.get("provider")
        if provider not in PROVIDER_CATEGORIES:
            raise EnterpriseConnectorError(
                "f144_provider_unknown:" + str(provider))
        company_name = raw.get("company_name")
        credit_code = raw.get("credit_code")
        if (company_name is None) == (credit_code is None):
            # 恰一查询键（名称或统一社会信用代码）。
            raise EnterpriseConnectorError(
                "f144_query_key_exactly_one_required")
        if company_name is not None:
            _require_str(company_name, "f144_company_name_invalid")
        if credit_code is not None:
            _require_str(credit_code, "f144_credit_code_invalid")

        token = _token_state(provider)
        if not token["present"]:
            # 缺 Token 不自采或编数据（06 acceptance 逐字）。
            projections.append(
                _entry(provider, "TOKEN_NOT_CONFIGURED",
                       "PAID_TOKEN_NOT_CONFIGURED", None, None))
            continue
        if session_factory is None:
            projections.append(
                _entry(provider, "SESSION_ABSENT",
                       "CONNECTOR_SESSION_ABSENT_PENDING_AUTHORIZATION",
                       None, None))
            continue
        try:
            session = session_factory(provider)
            sessions_established += 1
            receipt = session.query(company_name=company_name,
                                    credit_code=credit_code)
        except Exception as exc:  # noqa: BLE001
            # 失败不编数据：异常面只带类型名，企业数据原文不进账。
            projections.append(
                _entry(provider, "QUERY_FAILED",
                       "connector_failed:" + type(exc).__name__,
                       None, None))
            continue
        problems = _validate_receipt(receipt)
        if problems:
            projections.append(
                _entry(provider, "RECEIPT_INVALID",
                       "f144_receipt_invalid:" + problems[0], None, None))
            continue
        credential = record_from_receipt(
            {"provider": provider, "company_name": company_name,
             "credit_code": credit_code}, receipt)
        projections.append({
            "provider": provider,
            "status": "DILIGENCE_RECORDED",
            "reason": None,
            "data": {
                "payload_sha256": credential["source_watermark"]
                ["payload_sha256"],
                "payload_field_count": credential["payload_field_count"],
            },
            "credential": credential,
        })

    counts = {status: 0 for status in ENTRY_STATUSES}
    for entry in projections:
        counts[entry["status"]] += 1
    receipt_out = {
        "schema": SCHEMA,
        "query_id": query_id,
        "matter_id": args.get("matter_id"),
        "items": projections,
        "counts": {status.lower(): counts[status]
                   for status in ENTRY_STATUSES},
        "form": "mcp_connector_no_self_collection",
        "sessions_established": sessions_established,
        "input_digest": digest,
        "recorded_at": _now(),
    }
    _atomic_write_json(path, {"schema": SCHEMA, "query_id": query_id,
                              "input_digest": digest,
                              "receipt": receipt_out})
    return receipt_out


def _query_path(state_root: Path, query_id: str) -> Path:
    return Path(state_root) / "queries" / (query_id + ".json")


def read_query(state_root, args: dict) -> dict:
    """查询账回读（只读；存在性以外不做任何推导）。"""
    query_id = _require_str(args.get("query_id"),
                            "f144_query_id_required", max_len=128)
    path = _query_path(Path(state_root), query_id)
    if not path.is_file():
        raise EnterpriseConnectorError("f144_query_not_found")
    return dict(json.loads(path.read_text(encoding="utf-8"))["receipt"])
