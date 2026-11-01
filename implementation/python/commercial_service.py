"""F80 自有商业账户/积分/签到/邀请——独立商业服务面公开账（W5-U02 合成先行）。

06 行 V7-80 acceptance（owner=product；prereq E04/E07/E25 全 VERIFIED）：
保留源 v2 完整范围——账户/积分/签到/邀请真实幂等回执、撤销和余额；
只在独立商业服务面，案件工作台零运营位；不继承上游厂商账号营销，
不前移 v1。00-总协调 §6.1 裁决#13-19：W5 商业服务端统一合成先行，
真实托管设施（托管服务/支付/营销系统）v2 商业化时补——本面为产品侧
真实记账面（append-only 台账＋幂等回执＋确定性余额），零网络、零
URL、零遥测、零上游账号继承。

红线落法（结构性，非纸面）：

- 独立商业服务面＝独立冻结方法组 commercial.*（legal_entry）＋独立
  状态根（config.commercial_state_root）；案件工作台零运营位＝本模块
  不被任何案件/业务模块 import（导入图断言见 recon/test），方法字段
  闭集拒绝 case/matter 类字段——商业数据进不了案件面，案件上下文进
  不了商业面。
- 不继承上游厂商账号营销＝账户只认本产品 org/user 显式身份声明；
  无 referral_link/促销/追踪字段（字段闭集外一律具名拒）；产物零
  营销字段（recon 扫描）。
- 不前移 v1＝本面只提供账户/积分/签到/邀请/撤销/余额六类商业操作，
  不提供任何 v1 业务能力（案件/材料/引证等），冻结方法组与既有全部
  方法组零交集（不冒已有业务入口，06 binding UI_HOST_OR_NEW_PRODUCT）。

幂等纪律（F63 同构）：同 request_id 同输入 → 同回执逐键相等
（idempotent_replay=True，不双记）；同 request_id 异输入 → 具名
conflict；幂等键＝输入 digest，时间戳只溯源不入键；回执内
balance_after_cents 在入账时刻冻结——事后余额变动不改写历史回执，
重放永久同字节语义。

金额纪律：全部积分/余额一律整型分（int cents）；float/str/bool 具名
拒收。签到/邀请奖励＝冻结常量；台账严格 append-only（发放条目永不
改写，撤销＝追加撤销记录指向目标 receipt_id，生效状态由账目推导）：
余额＝未被撤销发放之和——撤销只减该笔发放且该笔此前必在余额内，
余额恒非负（结构不变量，测试断言）。

策略应用（F81 真实应用到运行面）：credit_grant/checkin 接受桥注入的
policy 投影（org_policy_admin 求值产物，键闭集见 POLICY_KEYS）；本模
块不 import org_policy_admin（两模块互不依赖，桥装配），投影缺键＝
无限制（默认开放，商业功能面语义非法证 fail-closed 面）；策略闸先于
入账——被拒操作不产生回执。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f80-commercial-service/1"

# 奖励政策冻结常量（整型分；本产品自有商业面合成政策）。
CHECKIN_REWARD_CENTS = 500
INVITE_REDEEM_REWARD_CENTS = 800
INVITE_REFERRAL_REWARD_CENTS = 300

# credit_grant 理由闭集（签到/邀请奖励走各自操作，不经 credit_grant）。
GRANT_REASONS = ("signup_bonus", "manual_adjust")

# F81 策略投影键闭集（org_policy_admin.POLICY_KEYS 同源；桥装配传入）。
POLICY_KEYS = ("commercial.checkin_enabled",
               "commercial.max_credit_grant_cents")

# 各方法字段闭集（闭集外字段具名拒——case/matter/url/促销等无处置位）。
FIELD_WHITELISTS = {
    "account_open": ("org_id", "user_ref"),
    "credit_grant": ("account_id", "request_id", "reason", "delta_cents"),
    "checkin": ("account_id", "request_id", "day"),
    "invite_issue": ("account_id", "request_id"),
    "invite_redeem": ("account_id", "request_id", "invite_code"),
    "revoke": ("account_id", "request_id", "receipt_id"),
    "balance_read": ("account_id",),
}


class CommercialServiceError(ValueError):
    """typed 错误：str(self) 只有错误码，金额/身份原文不入错误码。"""

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
        raise CommercialServiceError(code)
    return value


def _require_int_cents(value, code: str) -> int:
    """金额纪律：只收整型分；float/str/bool 一律具名拒收。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise CommercialServiceError(code + ":not_integer_cents")
    return value


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                              sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _check_fields(op: str, args: dict) -> None:
    unknown = sorted(set(args) - set(FIELD_WHITELISTS[op]))
    if unknown:
        raise CommercialServiceError("f80_field_forbidden:" + unknown[0])


def _digest_args(op: str, args: dict) -> str:
    return _sha256_bytes(_canonical({"op": op, "args": args})
                         .encode("utf-8"))


def _account_path(state_root: Path, account_id: str) -> Path:
    return Path(state_root) / "accounts" / (account_id + ".json")


def _invites_path(state_root: Path) -> Path:
    return Path(state_root) / "invites.json"


def account_id_for(org_id: str, user_ref: str) -> str:
    """账户标识确定性：同 org/user 两跑同 id（幂等开户的键）。"""
    return "c80acc-" + _sha256_bytes(
        _canonical({"org_id": org_id, "user_ref": user_ref})
        .encode("utf-8"))[:16]


def load_account(state_root, account_id: str) -> dict:
    path = _account_path(Path(state_root), account_id)
    if not path.is_file():
        raise CommercialServiceError("f80_account_unknown")
    return json.loads(path.read_text(encoding="utf-8"))


def account_identity(state_root, account_id: str) -> tuple[str, str]:
    """桥装配用：账户的 (org_id, user_ref)——策略按此求值后注入。"""
    account = load_account(state_root, account_id)
    return account["org_id"], account["user_ref"]


def _save_account(state_root: Path, account: dict) -> None:
    _atomic_write_json(_account_path(state_root, account["account_id"]),
                       account)


def _balance_of(account: dict) -> int:
    revoked = _revoked_receipt_ids(account)
    return sum(e["delta_cents"] for e in account["entries"]
               if e["kind"] == "grant"
               and e["receipt_id"] not in revoked)


def _revoked_receipt_ids(account: dict) -> set:
    return {e["target_receipt_id"] for e in account["entries"]
            if e["kind"] == "revocation"}


def balance_read(state_root, args: dict) -> dict:
    """余额回读（只读投影；整型分＋ACTIVE/REVOKED 计数）。"""
    _check_fields("balance_read", args)
    root = Path(state_root)
    account = load_account(root,
                           _require_str(args.get("account_id"),
                                        "f80_account_id_required"))
    entries = account["entries"]
    revoked = _revoked_receipt_ids(account)
    active = [e for e in entries if e["kind"] == "grant"
              and e["receipt_id"] not in revoked]
    revoked_grants = [e for e in entries if e["kind"] == "grant"
                      and e["receipt_id"] in revoked]
    return {
        "schema": SCHEMA,
        "account_id": account["account_id"],
        "org_id": account["org_id"],
        "user_ref": account["user_ref"],
        "balance_cents": _balance_of(account),
        "grants_active": len(active),
        "grants_revoked": len(revoked_grants),
        "revocations": sum(1 for e in entries
                           if e["kind"] == "revocation"),
    }


# ---------------------------------------------------------------------------
# 账户（幂等开户：同 org/user 重放同账户，不建第二账户）
# ---------------------------------------------------------------------------

def account_open(state_root, args: dict) -> dict:
    _check_fields("account_open", args)
    root = Path(state_root)
    org_id = _require_str(args.get("org_id"), "f80_org_id_required")
    user_ref = _require_str(args.get("user_ref"), "f80_user_ref_required")
    account_id = account_id_for(org_id, user_ref)
    path = _account_path(root, account_id)
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        return {"account": {k: existing[k] for k in
                            ("schema", "account_id", "org_id", "user_ref",
                             "opened_at")},
                "idempotent_replay": True}
    account = {"schema": SCHEMA, "account_id": account_id,
               "org_id": org_id, "user_ref": user_ref,
               "opened_at": _now(), "entries": []}
    _save_account(root, account)
    return {"account": {k: account[k] for k in
                        ("schema", "account_id", "org_id", "user_ref",
                         "opened_at")},
            "idempotent_replay": False}


# ---------------------------------------------------------------------------
# 发放（真实幂等回执；整型分；F81 策略上限真实应用）
# ---------------------------------------------------------------------------

def _receipt_projection(account: dict, entry: dict) -> dict:
    proj = dict(entry)
    proj["account_id"] = account["account_id"]
    return proj


def _find_by_request(account: dict, request_id: str):
    for entry in account["entries"]:
        if entry.get("request_id") == request_id:
            return entry
    return None


def _replay_or_conflict(account: dict, op: str, request_id: str,
                        request_digest: str):
    """同 request_id：同输入→同回执（replay）；异输入→具名 conflict。"""
    prior = _find_by_request(account, request_id)
    if prior is None:
        return None
    if prior["request_digest"] == request_digest:
        return prior
    raise CommercialServiceError("f80_" + op + "_conflict")


def _commit_grant(root: Path, account: dict, entry: dict) -> dict:
    """入账并在回执内冻结入账时刻余额（历史回执永久稳定）。

    entry 的 status＝签发时状态（ACTIVE）；条目永不改写，当前生效
    状态由撤销记录推导（_revoked_receipt_ids）——append-only。
    """
    account["entries"].append(entry)
    entry["balance_after_cents"] = _balance_of(account)
    _save_account(root, account)
    return _receipt_projection(account, entry)


def credit_grant(state_root, args: dict, *, policy=None) -> dict:
    """积分发放（append-only 幂等回执）。

    F81 策略真实应用：policy["commercial.max_credit_grant_cents"] 非
    None 时，超出上限的发放具名拒（策略先于入账，回执不存在）。
    """
    _check_fields("credit_grant", args)
    root = Path(state_root)
    account = load_account(root,
                           _require_str(args.get("account_id"),
                                        "f80_account_id_required"))
    request_id = _require_str(args.get("request_id"),
                              "f80_request_id_required")
    reason = args.get("reason")
    if reason not in GRANT_REASONS:
        raise CommercialServiceError("f80_reason_unknown:" + str(reason))
    delta = _require_int_cents(args.get("delta_cents"),
                               "f80_delta_invalid")
    if delta <= 0:
        raise CommercialServiceError("f80_delta_invalid:must_be_positive")
    digest = _digest_args("credit_grant", args)
    prior = _replay_or_conflict(account, "credit_grant", request_id, digest)
    if prior is not None:
        return {"receipt": _receipt_projection(account, prior),
                "idempotent_replay": True}
    cap = (policy or {}).get("commercial.max_credit_grant_cents")
    if cap is not None and delta > cap:
        raise CommercialServiceError(
            "f80_grant_exceeds_policy_cap:" + str(int(cap)))
    entry = {"kind": "grant",
             "receipt_id": "c80r-" + digest[:16],
             "request_id": request_id,
             "request_digest": digest,
             "reason": reason,
             "delta_cents": delta,
             "status": "ACTIVE",
             "granted_at": _now()}
    return {"receipt": _commit_grant(root, account, entry),
            "idempotent_replay": False}


# ---------------------------------------------------------------------------
# 签到（确定性日历日：一日一签；同日异请求具名拒不静默双发）
# ---------------------------------------------------------------------------

def _checkin_day(day_raw) -> str:
    if not isinstance(day_raw, str):
        raise CommercialServiceError("f80_day_invalid:not_string")
    try:
        parsed = date.fromisoformat(day_raw)
    except ValueError:
        raise CommercialServiceError(
            "f80_day_invalid:not_iso_date") from None
    if parsed.isoformat() != day_raw:
        # fromisoformat 在 3.11+ 也收基本格式（20261022）——非展开式具名拒。
        raise CommercialServiceError("f80_day_invalid:not_extended_format")
    return day_raw


def checkin(state_root, args: dict, *, policy=None) -> dict:
    """每日签到发奖（整型分冻结常量；一日一签幂等）。

    F81 策略真实应用：policy["commercial.checkin_enabled"] 为 False 时
    具名拒（策略先于入账）。day 显式入参（确定性日历，不入隐藏时钟；
    幂等键含 day）。
    """
    _check_fields("checkin", args)
    root = Path(state_root)
    account = load_account(root,
                           _require_str(args.get("account_id"),
                                        "f80_account_id_required"))
    request_id = _require_str(args.get("request_id"),
                              "f80_request_id_required")
    day = _checkin_day(args.get("day"))
    digest = _digest_args("checkin", args)
    prior = _replay_or_conflict(account, "checkin", request_id, digest)
    if prior is not None:
        return {"receipt": _receipt_projection(account, prior),
                "idempotent_replay": True}
    if (policy or {}).get("commercial.checkin_enabled") is False:
        raise CommercialServiceError("f80_checkin_disabled_by_policy")
    for entry in account["entries"]:
        if entry["kind"] == "grant" and entry.get("day") == day:
            raise CommercialServiceError("f80_checkin_already_done:"
                                         + day)
    entry = {"kind": "grant",
             "receipt_id": "c80r-" + digest[:16],
             "request_id": request_id,
             "request_digest": digest,
             "reason": "checkin_reward",
             "delta_cents": CHECKIN_REWARD_CENTS,
             "status": "ACTIVE",
             "granted_at": _now(),
             "day": day}
    return {"receipt": _commit_grant(root, account, entry),
            "idempotent_replay": False}


# ---------------------------------------------------------------------------
# 邀请（邀请码签发/兑换：双腿回执同 redeem id；一码一兑；自兑具名拒）
# ---------------------------------------------------------------------------

def _load_invites(state_root: Path) -> dict:
    path = _invites_path(state_root)
    if not path.is_file():
        return {"schema": SCHEMA, "codes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def invite_issue(state_root, args: dict) -> dict:
    """签发邀请码（绑定邀请人账户；确定性码；签发幂等键=request_id）。"""
    _check_fields("invite_issue", args)
    root = Path(state_root)
    account = load_account(root,
                           _require_str(args.get("account_id"),
                                        "f80_account_id_required"))
    request_id = _require_str(args.get("request_id"),
                              "f80_request_id_required")
    digest = _digest_args("invite_issue", args)
    invites = _load_invites(root)
    code = "c80inv-" + digest[:12]
    existing = invites["codes"].get(code)
    if existing is not None:
        if existing["inviter_account_id"] == account["account_id"] and \
                existing["issue_request_id"] == request_id:
            return {"invite_code": code, "invite": dict(existing),
                    "idempotent_replay": True}
        raise CommercialServiceError("f80_invite_issue_conflict")
    record = {"invite_code": code,
              "inviter_account_id": account["account_id"],
              "issue_request_id": request_id,
              "issue_request_digest": digest,
              "issued_at": _now(),
              "redeemed_by": None, "redeem_id": None,
              "redeemed_at": None, "redemption_receipt": None}
    invites["codes"][code] = record
    _atomic_write_json(_invites_path(root), invites)
    return {"invite_code": code, "invite": dict(record),
            "idempotent_replay": False}


def _append_invite_grant(root: Path, account_id: str, *, reason: str,
                         cents: int, redeem_id: str) -> dict:
    account = load_account(root, account_id)
    digest = _sha256_bytes(_canonical(
        {"redeem_id": redeem_id, "account_id": account_id,
         "reason": reason}).encode("utf-8"))
    entry = {"kind": "grant",
             "receipt_id": "c80r-" + digest[:16],
             "request_id": redeem_id + ":" + reason,
             "request_digest": digest,
             "reason": reason, "delta_cents": cents,
             "status": "ACTIVE", "granted_at": _now(),
             "invite_redeem_id": redeem_id}
    return _commit_grant(root, account, entry)


def invite_redeem(state_root, args: dict) -> dict:
    """兑换邀请码：受邀人/邀请人双腿真实幂等回执（同一 redeem id）。

    一码一兑（已兑具名拒）；自兑具名拒；未知码具名拒。重放（同
    request_id 同输入）→ 同双腿回执不双发（双腿奖励在入账时刻冻结，
    重放返回存档回执）。
    """
    _check_fields("invite_redeem", args)
    root = Path(state_root)
    redeemer = load_account(root,
                            _require_str(args.get("account_id"),
                                         "f80_account_id_required"))
    request_id = _require_str(args.get("request_id"),
                              "f80_request_id_required")
    code = _require_str(args.get("invite_code"),
                        "f80_invite_code_required")
    digest = _digest_args("invite_redeem", args)
    invites = _load_invites(root)
    record = invites["codes"].get(code)
    if record is None:
        raise CommercialServiceError("f80_invite_code_unknown")
    if record["inviter_account_id"] == redeemer["account_id"]:
        raise CommercialServiceError("f80_invite_self_redeem")
    redeem_id = "c80rd-" + digest[:16]
    if record["redeem_id"] is not None:
        if record["redeem_id"] == redeem_id:
            return {"redemption": dict(record["redemption_receipt"]),
                    "idempotent_replay": True}
        raise CommercialServiceError("f80_invite_code_already_used")
    redeemer_receipt = _append_invite_grant(
        root, redeemer["account_id"],
        reason="invite_redeem_reward",
        cents=INVITE_REDEEM_REWARD_CENTS,
        redeem_id=redeem_id)
    inviter_receipt = _append_invite_grant(
        root, record["inviter_account_id"],
        reason="invite_referral_reward",
        cents=INVITE_REFERRAL_REWARD_CENTS,
        redeem_id=redeem_id)
    record["redeemed_by"] = redeemer["account_id"]
    record["redeem_id"] = redeem_id
    record["redeemed_at"] = _now()
    record["redemption_receipt"] = {
        "schema": SCHEMA, "redeem_id": redeem_id,
        "invite_code": code,
        "redeemer_account_id": redeemer["account_id"],
        "inviter_account_id": record["inviter_account_id"],
        "redeemer_receipt": redeemer_receipt,
        "inviter_receipt": inviter_receipt,
        "redeemed_at": record["redeemed_at"],
    }
    _atomic_write_json(_invites_path(root), invites)
    return {"redemption": dict(record["redemption_receipt"]),
            "idempotent_replay": False}


# ---------------------------------------------------------------------------
# 撤销（真实撤销：原发放标 REVOKED＋撤销记录入账；幂等；余额随之回落）
# ---------------------------------------------------------------------------

def revoke(state_root, args: dict) -> dict:
    """撤销一笔发放（运营纠错面）。

    台账 append-only：撤销＝append 撤销记录（target_receipt_id 指向
    目标发放，原发放条目零改写；生效状态由撤销记录推导）。含撤销
    request_id/digest 幂等：同撤销请求重放同回执；异请求撤销已撤
    发放具名拒；未知 receipt 具名拒。余额＝未被撤销发放之和，随之
    回落且恒非负（被撤发放此前必在余额内——结构不变量）。
    """
    _check_fields("revoke", args)
    root = Path(state_root)
    account = load_account(root,
                           _require_str(args.get("account_id"),
                                        "f80_account_id_required"))
    request_id = _require_str(args.get("request_id"),
                              "f80_request_id_required")
    receipt_id = _require_str(args.get("receipt_id"),
                              "f80_receipt_id_required")
    digest = _digest_args("revoke", args)
    prior = _replay_or_conflict(account, "revoke", request_id, digest)
    if prior is not None:
        return {"revocation": _receipt_projection(account, prior),
                "idempotent_replay": True}
    target = None
    for entry in account["entries"]:
        if entry["kind"] == "grant" and entry["receipt_id"] == receipt_id:
            target = entry
            break
    if target is None:
        raise CommercialServiceError("f80_receipt_unknown")
    if receipt_id in _revoked_receipt_ids(account):
        raise CommercialServiceError("f80_receipt_already_revoked")
    revocation = {"kind": "revocation",
                  "revocation_id": "c80v-" + digest[:16],
                  "request_id": request_id,
                  "request_digest": digest,
                  "target_receipt_id": receipt_id,
                  "target_reason": target["reason"],
                  "delta_cents": target["delta_cents"],
                  "revoked_at": _now()}
    account["entries"].append(revocation)
    revocation["balance_after_cents"] = _balance_of(account)
    _save_account(root, account)
    return {"revocation": _receipt_projection(account, revocation),
            "idempotent_replay": False}
