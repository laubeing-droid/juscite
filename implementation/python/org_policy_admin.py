"""F81 企业组策略/深度管理台——策略账与真实应用面（W5-U02 合成先行）。

06 行 V7-81 acceptance（owner=product；prereq E04/E07/E25 全 VERIFIED）：
管理策略真实应用到用户和运行面；深管理不替代最小 v1 管理台。
00-总协调 §6.1 裁决#13-19：商业服务端统一合成先行。

红线落法：

- 真实应用到用户和运行面＝三段真实链：orgadmin.policy_declare（
  append-only 策略账，typed 值校验）→ orgadmin.policy_read/policy_apply
  （F9 语义求值：段序 org→user，同段声明序 findLast 末条胜出——user
  段压过 org 段，与 f9-permission-precedence.md「会话段压过 agent 段」
  同构）→ 桥把求值投影注入 commercial_service（F80 运行面），
  checkin_enabled=False 拒签到、max_credit_grant_cents 拒超限发放
  ——策略改动即时改变运行面行为（recon/test 端到端断言）。
- 深管理不替代最小 v1 管理台＝本面只管 v2 商业面策略（键闭集全部
  commercial.*）；案件/材料/harness 等 v1 管理面（F04 案件权限规则/
  veto 账、F05 协作面）不在本面处置位——键闭集外具名拒（含
  case.* 探测负测）；本模块零 v1 业务 import；冻结方法组与既有全部
  方法组零交集（不冒已有业务入口，06 binding UI_HOST_OR_NEW_PRODUCT）。
- append-only＋幂等：声明记录不删不改（改值＝追加新记录，末条生效）；
  同 request_id 同输入重放同回执，异输入具名 conflict。

本模块不 import commercial_service（两模块互不依赖，legal_entry 桥
装配）；零网络、零 URL。org_id＝企业组；user_ref＝组内用户；分层
only org/user 两段（v2 商业面当前真实消费面，不预造 role/组中层级）。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f81-org-policy-admin/1"

# 策略键闭集（全部 v2 商业面键；v1 业务键一律不在处置位）。
POLICY_KEYS = ("commercial.checkin_enabled",
               "commercial.max_credit_grant_cents")

# 段闭集（org=企业组段；user=用户段；求值段序 org→user，末段胜出）。
SEGMENTS = ("org", "user")

FIELD_WHITELISTS = {
    "policy_declare": ("org_id", "user_ref", "policy_key", "value",
                       "declared_by", "request_id"),
    "policy_read": ("org_id", "user_ref"),
    "policy_apply": ("org_id", "user_ref"),
}


class OrgPolicyError(ValueError):
    """typed 错误：str(self) 只有错误码。"""

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


def _require_str(value, code: str, *, max_len: int = 128) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise OrgPolicyError(code)
    return value


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                              sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _ledger_path(state_root: Path) -> Path:
    return Path(state_root) / "policy-ledger.json"


def load_ledger(state_root) -> dict:
    path = _ledger_path(Path(state_root))
    if not path.is_file():
        return {"schema": SCHEMA, "records": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_value(policy_key: str, value) -> None:
    """typed 策略值闭集：bool 键只收 bool；分上限键只收非负整型分。"""
    if policy_key == "commercial.checkin_enabled":
        if not isinstance(value, bool):
            raise OrgPolicyError("f81_policy_value_invalid:expect_bool")
        return
    if policy_key == "commercial.max_credit_grant_cents":
        if isinstance(value, bool) or not isinstance(value, int) \
                or value < 0:
            raise OrgPolicyError(
                "f81_policy_value_invalid:expect_non_negative_int_cents")
        return
    raise OrgPolicyError("f81_policy_key_unknown:" + str(policy_key))


def _check_fields(op: str, args: dict) -> None:
    unknown = sorted(set(args) - set(FIELD_WHITELISTS[op]))
    if unknown:
        raise OrgPolicyError("f81_field_forbidden:" + unknown[0])


# ---------------------------------------------------------------------------
# 声明（append-only 策略账；幂等回执；改值＝追加新记录末条生效）
# ---------------------------------------------------------------------------

def policy_declare(state_root, args: dict) -> dict:
    _check_fields("policy_declare", args)
    root = Path(state_root)
    org_id = _require_str(args.get("org_id"), "f81_org_id_required")
    user_ref = args.get("user_ref")
    if user_ref is not None:
        user_ref = _require_str(user_ref, "f81_user_ref_invalid")
    declared_by = _require_str(args.get("declared_by"),
                               "f81_declared_by_required")
    request_id = _require_str(args.get("request_id"),
                              "f81_request_id_required")
    policy_key = args.get("policy_key")
    if policy_key not in POLICY_KEYS:
        raise OrgPolicyError("f81_policy_key_unknown:" + str(policy_key))
    _validate_value(policy_key, args.get("value"))
    digest = _sha256_bytes(_canonical(
        {"op": "policy_declare", "args": args}).encode("utf-8"))
    ledger = load_ledger(root)
    for record in ledger["records"]:
        if record["request_id"] == request_id:
            if record["request_digest"] == digest:
                return {"record": dict(record), "idempotent_replay": True}
            raise OrgPolicyError("f81_declare_conflict")
    segment = "user" if user_ref is not None else "org"
    record = {
        "schema": SCHEMA,
        "policy_id": "f81p-" + digest[:16],
        "org_id": org_id,
        "user_ref": user_ref,
        "segment": segment,
        "policy_key": policy_key,
        "value": args.get("value"),
        "declared_by": declared_by,
        "request_id": request_id,
        "request_digest": digest,
        "recorded_at": _now(),
    }
    ledger["records"].append(record)
    _atomic_write_json(_ledger_path(root), ledger)
    return {"record": dict(record), "idempotent_replay": False}


# ---------------------------------------------------------------------------
# 求值（F9 语义：段序 org→user 拼接后 findLast 末条胜出——user 段压过
# org 段；trace 记录每键胜出记录，管理面可读）
# ---------------------------------------------------------------------------

def evaluate(ledger: dict, org_id: str, user_ref) -> dict:
    """对 (org, user) 求值有效策略投影＋完整匹配链（纯函数）。

    trace＝按段序 org→user 拼接后的全部匹配记录（声明序）——每键
    末条即胜出者（findLast 语义），org 候选与 user 覆盖全程可读。
    """
    org_records = [r for r in ledger["records"]
                   if r["org_id"] == org_id and r["segment"] == "org"]
    user_records = [r for r in ledger["records"]
                    if r["org_id"] == org_id and r["segment"] == "user"
                    and user_ref is not None
                    and r["user_ref"] == user_ref]
    ordered = org_records + user_records
    effective: dict = {}
    trace: list[dict] = []
    for record in ordered:
        key = record["policy_key"]
        trace.append({"policy_key": key,
                      "segment": record["segment"],
                      "policy_id": record["policy_id"],
                      "value": record["value"],
                      "user_ref": record["user_ref"]})
        effective[key] = record["value"]  # 顺序扫描不提前停——末条胜出
    return {"org_id": org_id,
            "user_ref": user_ref,
            "effective": effective,
            "trace": trace,
            "records_considered": len(ordered)}


def policy_read(state_root, args: dict) -> dict:
    _check_fields("policy_read", args)
    org_id = _require_str(args.get("org_id"), "f81_org_id_required")
    user_ref = args.get("user_ref")
    if user_ref is not None:
        user_ref = _require_str(user_ref, "f81_user_ref_invalid")
    return evaluate(load_ledger(Path(state_root)), org_id, user_ref)


# ---------------------------------------------------------------------------
# 应用（真实应用到运行面的回执步骤：对用户求值并产出商业面投影）
# ---------------------------------------------------------------------------

def policy_apply(state_root, args: dict) -> dict:
    """把有效策略应用到运行面（F80 商业服务面）并出应用回执。

    应用回执＝该用户在商业运行面的生效投影（legal_entry 桥把同一
    投影注入 commercial_service——行为生效由 recon/test 端到端断言：
    声明后 checkin/grant 实际行为改变）。user_ref 必填（应用到用户）。
    """
    _check_fields("policy_apply", args)
    org_id = _require_str(args.get("org_id"), "f81_org_id_required")
    user_ref = _require_str(args.get("user_ref"),
                            "f81_user_ref_required")
    projection = evaluate(load_ledger(Path(state_root)), org_id, user_ref)
    unknown = sorted(set(projection["effective"]) - set(POLICY_KEYS))
    if unknown:
        raise OrgPolicyError("f81_projection_key_unknown:" + unknown[0])
    return {"org_id": org_id,
            "user_ref": user_ref,
            "surface": "commercial_service",
            "applied_at": _now(),
            "applied": dict(projection["effective"]),
            "trace": projection["trace"],
            "records_considered": projection["records_considered"]}
