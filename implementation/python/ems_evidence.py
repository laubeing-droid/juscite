"""F63 快递查询/EMS 取证——授权账与取证封存账公开面（W4-U40 负测先行）。

06 行 F63 acceptance：EMS 轨迹与取证时间/来源水印凭证真实生成；失败不编
轨迹。owner=product；prerequisites E10,E11,E12,E17,E21,E24。00-总协调
§6.1 裁决#8-12（五项外部 API 统一负测先行：禁编 URL/失败不造假，授权后
补）为本波唯一执行态：EMS 官方 API 授权未落地——真实轨迹/凭证的实测属
授权后补联测（回收点具名见 recon 证据与本单台账 failure_reason）。

负测先行结构（W2a-U13 P11 先例＋W3-U13 F61 先例同构）：

- 授权账（authorize_action）：显式登记的律师授权外部动作（E24 形态：
  authorized_by＋scope 闭集＋append-only＋幂等重放）。scope 闭集 v1 只有
  ems_official_api_query（类别名）；任何在线端点形态不具名即不存在——
  本面零 URL 字面量（AST 级断言见 recon/test），端点属授权后适配器工单，
  禁编 URL。
- token 在位性（token_state）：未配置→具名缺口 PAID_TOKEN_NOT_CONFIGURED
  （W2a-U13 先例同码），只查在位不读值、不发请求、不自采。
- 查询（run_query）：唯一网络通道＝本桥注入的 transport 可调用参数；
  本波产品桥无 EMS 适配器可注入（端点未定，禁编 URL）→ 已授权＋token
  在位也只会得到具名缺口 EMS_ADAPTER_ABSENT——未授权态/未接线态真实
  调用路径结构性不可达（客户端未建不可能自采）。
- 回执封存（seal_from_receipt）：轨迹与凭证只从真实回执转录——凭证绑定
  取证时间（retrieved_at，出自回执）＋来源水印（provider＋回执 sha256），
  seal=确定性 sha256（同回执两跑同字节同 seal，时钟不入 seal 语义）。
  E17 EvidenceAttempt 语义：有凭据（真实回执）才记取得——无回执条目
  trajectory/credential/cost 恒 None（UNKNOWN 不是 0，不造空轨迹）。
- 失败不编轨迹：transport 异常→QUERY_FAILED；回执残缺（缺 provider/
  retrieved_at/trace 非列表/类型不符）→RECEIPT_INVALID 具名理由，值恒
  None，绝不生成部分/合成轨迹条目。
- 费用纪律（E21 消费面）：回执费用只收整型分；float/str/bool 具名拒收
  （金额 Decimal/整分纪律）；真实费用计算走 JC 计算面（E21），本面只
  转录回执申报值。
- 幂等回流：同 query_id 同输入重放同回执（不双记）；异输入具名 conflict。
- 敏感红线：条目投影只带状态/哈希/计数/具名理由——token 值、URL、回执
  原文（地址/签收人等面）绝不回传不落账（轨迹条目只留时间＋描述哈希）。

确定性纪律：waybill/receipt 全部显式比较；recorded_at 仅溯源展示不入
幂等键（幂等键=输入 digest）；本模块零网络依赖（导入闭集见 recon C01
AST 断言）。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f63-ems-evidence/1"

# 授权范围闭集（v1）：EMS 官方 API 查询（类别名，零 URL——端点属授权后
# 适配器工单，禁编 URL）。新增 scope 须扩此闭集入账，不得隐式放行。
ACTION_SCOPES = ("ems_official_api_query",)

# token 环境变量（产品约定；只查在位性，不读值——W2a-U13 PAID_TOKEN_
# NOT_CONFIGURED 先例同纪律）。
TOKEN_ENV_VAR = "EMS_API_TOKEN"

# 条目状态闭集。
ENTRY_STATUSES = (
    "EVIDENCE_SEALED",         # 真实回执转录完成（凭证绑定时间/来源水印）
    "RECEIPT_INVALID",         # 回执残缺/类型不符（失败不编轨迹）
    "QUERY_FAILED",            # transport 异常（失败不编轨迹）
    "ADAPTER_ABSENT",          # 适配器未接线（客户端未建不可能自采）
    "TOKEN_NOT_CONFIGURED",    # 缺 token（PAID_TOKEN_NOT_CONFIGURED 不自采）
    "ACTION_NOT_AUTHORIZED",   # 未授权动作（E24 授权闸先行）
)

# 值字段（轨迹/凭证/费用）只允许在 EVIDENCE_SEALED 非空；其余状态恒 None。
VALUE_BEARING_STATUSES = ("EVIDENCE_SEALED",)

QUERY_FIELD_WHITELIST = ("query_id", "matter_id", "items")
ITEM_FIELD_WHITELIST = ("waybill_no",)


class EmsEvidenceError(ValueError):
    """typed 错误：str(self) 只有错误码，回执原文/token 值永不进错误码。"""

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
        raise EmsEvidenceError(code)
    return value


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                              sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 授权账（E24 形态：显式授权的外部动作）
# ---------------------------------------------------------------------------

def _authorization_path(state_root: Path) -> Path:
    return Path(state_root) / "authorization.json"


def load_authorization(state_root) -> dict:
    path = _authorization_path(Path(state_root))
    if not path.is_file():
        return {"schema": SCHEMA, "authorizations": []}
    return json.loads(path.read_text(encoding="utf-8"))


def authorization_digest(state_root) -> str | None:
    path = _authorization_path(Path(state_root))
    return _sha256_bytes(path.read_bytes()) if path.is_file() else None


def authorized_scopes(state_root) -> set[str]:
    ledger = load_authorization(state_root)
    scopes: set[str] = set()
    for entry in ledger["authorizations"]:
        scopes.add(entry["scope"])
    return scopes


def authorize_action(state_root, args: dict) -> dict:
    """登记律师授权的 EMS 查询外部动作（append-only＋幂等重放）。"""
    root = Path(state_root)
    scope = args.get("scope") or ACTION_SCOPES[0]
    if scope not in ACTION_SCOPES:
        raise EmsEvidenceError("f63_scope_unknown:" + str(scope))
    authorized_by = _require_str(args.get("authorized_by"),
                                 "f63_authorized_by_required")
    key = scope + "|" + authorized_by
    ledger = load_authorization(root)
    for entry in ledger["authorizations"]:
        if entry["scope"] == scope and entry["authorized_by"] == authorized_by:
            return {"authorization": dict(entry),
                    "idempotent_replay": True}
    record = {
        "auth_id": "f63auth-" + _sha256_bytes(key.encode("utf-8"))[:16],
        "scope": scope,
        "authorized_by": authorized_by,
        "recorded_at": _now(),
    }
    ledger["authorizations"].append(record)
    _atomic_write_json(_authorization_path(root), ledger)
    return {"authorization": record, "idempotent_replay": False}


# ---------------------------------------------------------------------------
# token 在位性（只查在位，不读值）
# ---------------------------------------------------------------------------

def token_state() -> dict:
    if not os.environ.get(TOKEN_ENV_VAR, "").strip():
        return {"present": False,
                "reason": "PAID_TOKEN_NOT_CONFIGURED",
                "detail": TOKEN_ENV_VAR,
                "self_collection": "none"}
    return {"present": True, "reason": None,
            "self_collection": "none",
            "note": "token 在位不等于已接线；适配器缺席仍不发起查询"}


# ---------------------------------------------------------------------------
# 回执封存（轨迹/凭证只从真实回执转录；E17 语义：有凭据才记取得）
# ---------------------------------------------------------------------------

def _validate_receipt(receipt) -> list[str]:
    """回执合同闭集校验；返回具名缺口列表（空＝合格）。"""
    problems: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt_not_object"]
    provider = receipt.get("provider")
    if provider is None:
        problems.append("provider_missing")
    elif not isinstance(provider, str) or not provider:
        problems.append("provider_invalid")
    retrieved_at = receipt.get("retrieved_at")
    if retrieved_at is None:
        problems.append("retrieved_at_missing")
    elif not isinstance(retrieved_at, str) or not retrieved_at:
        problems.append("retrieved_at_invalid")
    trace = receipt.get("trace")
    if trace is None:
        problems.append("trace_missing")
    elif not isinstance(trace, list):
        problems.append("trace_not_list")
    else:
        for step in trace:
            if not isinstance(step, dict) or \
                    not isinstance(step.get("time"), str) or \
                    not isinstance(step.get("desc"), str):
                problems.append("trace_step_invalid")
                break
    cost = receipt.get("cost_cents")
    if cost is not None:
        # 金额纪律：只收整型分；float/str/bool 一律拒收。
        if isinstance(cost, bool) or not isinstance(cost, int):
            problems.append("cost_not_integer_cents")
    return problems


def seal_from_receipt(waybill_no: str, receipt: dict) -> dict:
    """从真实回执确定性封存：轨迹转录＋取证时间/来源水印凭证。

    纯函数（同输入两跑同字节同 seal）；时钟不入 seal——evidence_time
    出自回执 retrieved_at，来源水印=provider＋回执 sha256。轨迹条目只留
    时间＋描述哈希（描述原文不落账——地址/签收人等面不回传）。
    """
    problems = _validate_receipt(receipt)
    if problems:
        raise EmsEvidenceError("f63_receipt_invalid:" + problems[0])
    receipt_digest = _sha256_bytes(_canonical(receipt).encode("utf-8"))
    trace = receipt.get("trace") or []
    trace_projection = [
        {"time": step["time"], "desc_sha256": _sha256_bytes(
            step["desc"].encode("utf-8"))}
        for step in trace
    ]
    waybill_digest = _sha256_bytes(waybill_no.encode("utf-8"))
    core = {
        "waybill_sha256": waybill_digest,
        "receipt_sha256": receipt_digest,
        "evidence_time_utc": receipt["retrieved_at"],
        "trace_digest": _sha256_bytes(
            _canonical(trace_projection).encode("utf-8")),
    }
    return {
        "kind": "ems_evidence_credential/1",
        "waybill_sha256": waybill_digest,
        "source_watermark": {
            "provider": receipt["provider"],
            "receipt_sha256": receipt_digest,
            "origin": "receipt_transcription",
        },
        "evidence_time_utc": receipt["retrieved_at"],
        "trace_count": len(trace_projection),
        "trace_digest": core["trace_digest"],
        "cost_cents": receipt.get("cost_cents"),
        "seal": _sha256_bytes(_canonical(core).encode("utf-8")),
    }


def _entry(waybill_no: str, status: str, reason, trajectory, credential):
    return {"waybill_sha256": _sha256_bytes(waybill_no.encode("utf-8")),
            "status": status, "reason": reason, "trajectory": trajectory,
            "credential": credential}


def _trajectory_projection(receipt: dict) -> list[dict]:
    trace = receipt.get("trace") or []
    return [{"time": step["time"], "desc_sha256": _sha256_bytes(
        step["desc"].encode("utf-8"))} for step in trace]


def run_query(state_root, args: dict, *, transport) -> dict:
    """按授权条目批次查询 EMS 轨迹并封存取证凭证。

    transport＝本桥注入的唯一网络通道（可调用 waybill_no→receipt dict）；
    本模块绝不自行构造客户端（零网络依赖＝结构性）。transport=None
    （本波产品桥常态：适配器未接线）→ 已授权＋token 在位也只会得到
    ADAPTER_ABSENT 具名缺口——真实调用路径结构性不可达。
    """
    root = Path(state_root)
    unknown_fields = sorted(set(args) - set(QUERY_FIELD_WHITELIST))
    if unknown_fields:
        # 采集旁路字段（url/cookie/token…）在顶层也无处置位。
        raise EmsEvidenceError("f63_field_forbidden:" + unknown_fields[0])
    query_id = _require_str(args.get("query_id"), "f63_query_id_required",
                            max_len=128)
    _require_str(args.get("matter_id"), "f63_matter_id_required",
                 max_len=128)
    items_raw = args.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise EmsEvidenceError("f63_items_required")

    digest = _sha256_bytes(_canonical(args).encode("utf-8"))
    path = _query_path(root, query_id)
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("input_digest") == digest:
            return dict(existing["receipt"])
        raise EmsEvidenceError("f63_query_conflict")

    authorized = ACTION_SCOPES[0] in authorized_scopes(root)
    token = token_state()
    projections: list[dict] = []
    for raw in items_raw:
        if not isinstance(raw, dict):
            raise EmsEvidenceError("f63_item_invalid")
        unknown_item_fields = sorted(set(raw) - set(ITEM_FIELD_WHITELIST))
        if unknown_item_fields:
            # 负测先行：url/cookie 等旁路字段具名拒——不存在隐式采集通道。
            raise EmsEvidenceError(
                "f63_field_forbidden:" + unknown_item_fields[0])
        waybill = _require_str(raw.get("waybill_no"),
                               "f63_waybill_no_required", max_len=64)

        # 授权闸先行（F61 顺序语义）：未授权动作→值恒 None。
        if not authorized:
            projections.append(
                _entry(waybill, "ACTION_NOT_AUTHORIZED",
                       "f63_action_not_authorized", None, None))
            continue
        # token 在位性：缺 token→具名缺口不自采（W2a-U13 先例同码）。
        if not token["present"]:
            projections.append(
                _entry(waybill, "TOKEN_NOT_CONFIGURED",
                       "PAID_TOKEN_NOT_CONFIGURED", None, None))
            continue
        # 适配器闸：transport 未接线（客户端未建）→不可能自采。
        if transport is None:
            projections.append(
                _entry(waybill, "ADAPTER_ABSENT",
                       "EMS_ADAPTER_ABSENT_PENDING_AUTHORIZATION",
                       None, None))
            continue
        try:
            receipt = transport(waybill)
        except Exception as exc:  # noqa: BLE001
            # 失败不编轨迹：异常面只带类型名，回执原文/token 值不进账。
            projections.append(
                _entry(waybill, "QUERY_FAILED",
                       "transport_failed:" + type(exc).__name__, None, None))
            continue
        problems = _validate_receipt(receipt)
        if problems:
            projections.append(
                _entry(waybill, "RECEIPT_INVALID",
                       "f63_receipt_invalid:" + problems[0], None, None))
            continue
        credential = seal_from_receipt(waybill, receipt)
        projections.append({
            "waybill_sha256": credential["waybill_sha256"],
            "status": "EVIDENCE_SEALED",
            "reason": None,
            "trajectory": _trajectory_projection(receipt),
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
        "authorization_digest": authorization_digest(root),
        "token_env": TOKEN_ENV_VAR,
        "adapter": "present" if transport is not None else "absent",
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
    query_id = _require_str(args.get("query_id"), "f63_query_id_required",
                            max_len=128)
    path = _query_path(Path(state_root), query_id)
    if not path.is_file():
        raise EmsEvidenceError("f63_query_not_found")
    return dict(json.loads(path.read_text(encoding="utf-8"))["receipt"])
