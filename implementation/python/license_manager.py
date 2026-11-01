# -*- coding: utf-8 -*-
"""F78 授权激活＋每日校验＋宽限期（工单 W5-U01）。

06 F78（V7-78；owner=distribution，desktop/selfhost 双实例；acceptance：
「授权校验/宽限/离线状态真实；不因服务中断删除数据或伪授权」；legacy
link F12）。裁决 #13-19（00-总协调 §6.1）：商业服务端统一合成先行——
真实设施 v2 商业化时补，具名回收点＝tools/license_issuer_synth.py 头注。

设计（最小必要面）：
  - 激活＝安装离线许可令牌：license.activate(token) 经 F79 验签（签名/
    指纹/时间窗/时钟水印全过）后持久化激活记录——离线激活真实成立（F79
    legacy link F78 的语义主链）；与签发服务的交换在调用方/部署层，产品
    面只消费令牌。
  - 每日校验＝license.check 联系 config.license_service_url：24h 窗内不
    出网（每日语义）；到点真 HTTP 校验——valid→记 valid 清宽限；revoked
    →记 revoked（真实状态，绝不伪授权）；服务不可达→进宽限：宽限锚＝
    最近一次 valid（无则激活时刻），宽限预算＝config.license_grace_days
    （缺省 14）天，**一次性钉定不展期**（后续不可达沿用既有预算）。
  - 状态机（真实派生，绝不伪授权）：not_activated < authorized < grace <
    grace_expired / revoked / license_expired / clock_rollback_detected。
    时钟回拨检出（F79 now_checked typed 拒或检视事实）时状态投影恒为
    clock_rollback_detected——回拨时钟下绝不投影 authorized（fail-closed）。
  - 红线「不因服务中断删除数据或伪授权」结构性钉死：本文件零删除路径
    （激活记录/校验历史/宽限预算只追加只更新，无 unlink），服务不可达
    只进宽限/具名状态，任何代码路径都不把「未验证」写成「已授权」。
  - F30 协调（W3-U05 先例 F74 同式）：每日校验是新增出网通道，出网前读
    F30 旗标（airplane_mode.flag）——armed 且服务端非回环＝具名拒
    license_daily_check_airplane_blocked（先于任何连接）；回环合成签发
    服务（裁决#13-19）在 armed 时保持可用（F30 回环例外同语义）。F30
    冻结通道闭集零改动。
  - legacy link F12：时钟水印 HMAC 密钥经既有保险库（license_verify 统
    一取钥），本面不自建凭据。

错误全部 typed（LicenseError 的 str 只有 license_* 码，与 F79 共类）；
状态/回执零密钥字节零令牌原文。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from bridge_errors import NotConnected
from license_verify import LicenseError, _iso, now_checked

STATE_SCHEMA = "lvyin-license-state/1"
SERVICE_TIMEOUT_SECONDS = 10
DAY_SECONDS = 86400
DEFAULT_GRACE_DAYS = 14

# legal_entry 冻结方法组（组外方法绝不落到本面）。
LICENSE_MANAGER_METHODS = frozenset({
    "license.activate",
    "license.check",
    "license.status",
})

_STATE_FILENAME = "license-state.json"

# 状态闭集（status/check 只出这些词；真实派生，无第四形态）。
STATE_NOT_ACTIVATED = "not_activated"
STATE_AUTHORIZED = "authorized"
STATE_GRACE = "grace"
STATE_GRACE_EXPIRED = "grace_expired"
STATE_REVOKED = "revoked"
STATE_LICENSE_EXPIRED = "license_expired"
STATE_CLOCK_ROLLBACK = "clock_rollback_detected"


# ---------------------------------------------------------------------- #
# 状态持久化（原子写；零删除路径）
# ---------------------------------------------------------------------- #

def _state_path(config: dict) -> Path:
    state_root = (config or {}).get("license_state_root")
    if not state_root:
        raise LicenseError("license_state_root_not_configured")
    return Path(str(state_root)) / _STATE_FILENAME


def _load_state(config: dict) -> dict | None:
    path = _state_path(config)
    if not path.is_file():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("schema") != STATE_SCHEMA:
        raise LicenseError("license_state_schema_unknown")
    return state


def _write_state(config: dict, state: dict) -> None:
    path = _state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_iso"] = _iso(time.time())
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)


def _grace_days(config: dict) -> int:
    raw = (config or {}).get("license_grace_days")
    if raw is None:
        return DEFAULT_GRACE_DAYS
    try:
        days = int(raw)
    except (TypeError, ValueError):
        raise LicenseError("license_grace_days_invalid") from None
    if days < 1:
        raise LicenseError("license_grace_days_invalid")
    return days


# ---------------------------------------------------------------------- #
# F30 协调（只读旗标；冻结通道闭集零改动）
# ---------------------------------------------------------------------- #

def _airplane_blocks(config: dict, endpoint: str) -> str | None:
    """armed 且服务端非回环＝拒；回环合成签发服务保持可用（F30 回环例外
    同语义）。返回具名拒码或 None。"""
    from airplane_mode import flag, endpoint_is_local

    if not flag(config or {}).get("enabled"):
        return None
    if endpoint_is_local(endpoint):
        return None
    return "license_daily_check_airplane_blocked"


# ---------------------------------------------------------------------- #
# 服务校验（真 HTTP；不可达＝typed，绝不伪造结果）
# ---------------------------------------------------------------------- #

def _service_check(url: str, body: dict) -> dict:
    """POST {status}；网络失败一律 typed license_service_unreachable
    （HTTPError/URLError/OSError 同落）；服务可达但应答不识＝typed
    license_service_response_unknown——可达但坏≠中断，绝不因此开宽限。"""
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/check",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request,
                                    timeout=SERVICE_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        # HTTPError⊂URLError⊂OSError：非 200 与连不通同落「不可达」。
        raise LicenseError("license_service_unreachable:" + str(
            getattr(exc, "reason", None) or type(exc).__name__)) from None
    except (ValueError, UnicodeDecodeError):
        raise LicenseError("license_service_response_unknown") from None
    status = payload.get("status") if isinstance(payload, dict) else None
    if status not in ("valid", "revoked"):
        raise LicenseError("license_service_response_unknown")
    return {"status": status}


# ---------------------------------------------------------------------- #
# 状态投影（真实派生；回拨时钟下绝不投影 authorized）
# ---------------------------------------------------------------------- #

def _project(config: dict, state: dict | None) -> dict:
    if state is None or not state.get("activation"):
        return {"schema": STATE_SCHEMA, "state": STATE_NOT_ACTIVATED}
    clock_facts = None
    try:
        from license_verify import clock_inspect
        clock_facts = clock_inspect(config)
    except LicenseError:
        clock_facts = None
    if clock_facts is not None and clock_facts.get("rollback_detected"):
        return {"schema": STATE_SCHEMA, "state": STATE_CLOCK_ROLLBACK,
                "clock": clock_facts,
                "note": "时钟回拨检出——fail-closed，绝不投影 authorized"}
    try:
        now = now_checked(config)
    except LicenseError as exc:
        if str(exc) == "license_clock_rollback_detected":
            return {"schema": STATE_SCHEMA, "state": STATE_CLOCK_ROLLBACK,
                    "note": "时钟回拨检出——fail-closed，绝不投影 authorized"}
        raise
    activation = state["activation"]
    if now > float(activation["not_after"]):
        out_state = STATE_LICENSE_EXPIRED
    elif state.get("last_check", {}).get("result") == "revoked":
        out_state = STATE_REVOKED
    else:
        grace_until = state.get("grace_until_epoch")
        if grace_until is not None:
            if now > float(grace_until):
                out_state = STATE_GRACE_EXPIRED
            else:
                out_state = STATE_GRACE
        else:
            out_state = STATE_AUTHORIZED
    return {
        "schema": STATE_SCHEMA,
        "state": out_state,
        "license_id": activation["license_id"],
        "subject": activation["subject"],
        "features": list(activation.get("features") or []),
        "device_fp_hash": activation["device_fp_hash"],
        "not_after": activation["not_after"],
        "not_after_iso": activation.get("not_after_iso"),
        "activated_at_iso": activation.get("activated_at_iso"),
        "last_check": dict(state.get("last_check") or {}) or None,
        "grace_until_epoch": state.get("grace_until_epoch"),
        "grace_until_iso": (state.get("grace_until_epoch") and _iso(
            float(state["grace_until_epoch"]))) or None,
        "grace_days": state.get("grace_days"),
    }


# ---------------------------------------------------------------------- #
# 三方法：activate / check / status
# ---------------------------------------------------------------------- #

def activate(token, config: dict) -> dict:
    """激活＝F79 验签过闸后持久化激活记录（离线真实成立；零伪授权）。"""
    from license_verify import verify_offline_token

    now = now_checked(config)
    verified = verify_offline_token(token, config, now)
    state = _load_state(config) or {"schema": STATE_SCHEMA}
    state["activation"] = {
        "license_id": verified["license_id"],
        "subject": verified["subject"],
        "features": verified["features"],
        "device_fp_hash": verified["device_fp_hash"],
        "not_before": verified["not_before"],
        "not_after": verified["not_after"],
        "not_after_iso": verified["not_after_iso"],
        "activated_at_epoch": now,
        "activated_at_iso": _iso(now),
        "algorithm": verified["algorithm"],
        "issuer_fingerprint": verified["issuer_fingerprint"],
    }
    # 重激活＝显式新令牌覆盖（校验历史归零语义：新许可新周期）。
    state["last_check"] = {"at_epoch": now, "at_iso": _iso(now),
                           "result": "activated"}
    state["last_valid_epoch"] = now
    state["grace_until_epoch"] = None
    state["grace_days"] = _grace_days(config)
    _write_state(config, state)
    return _project(config, state)


def check(config: dict) -> dict:
    """每日校验：任一 24h 窗内已校验（含不可达/撤销记录）不出网；到点真
    HTTP；不可达进宽限（锚=最近 valid，无则激活时刻；预算一次性钉定不展
    期）；revoked 真实入账；宽限过期＝grace_expired（零删数据零伪授权）。"""
    url = (config or {}).get("license_service_url")
    if not url:
        raise NotConnected("license_service_not_configured")
    state = _load_state(config)
    if state is None or not state.get("activation"):
        raise LicenseError("license_not_activated")
    now = now_checked(config)
    last = dict(state.get("last_check") or {})
    if last.get("at_epoch") \
            and now < float(last["at_epoch"]) + DAY_SECONDS:
        # 每日语义：窗内不出网（任何结果都算已校验过今天），状态照实投影。
        return {**_project(config, state), "checked_now": False,
                "next_check_due_epoch": float(last["at_epoch"]) + DAY_SECONDS}
    blocked = _airplane_blocks(config, str(url))
    if blocked:
        raise NotConnected(blocked)
    try:
        result = _service_check(str(url), {
            "license_id": state["activation"]["license_id"],
            "device_fp_hash": state["activation"]["device_fp_hash"],
        })
    except LicenseError as exc:
        if str(exc).split(":")[0] != "license_service_unreachable":
            raise  # 可达但应答不识＝typed 拒，状态零动（绝不因此开宽限）
        # 服务中断→宽限：锚=最近 valid（无则激活时刻）；预算一次性钉定。
        anchor = state.get("last_valid_epoch") \
            or float(state["activation"]["activated_at_epoch"])
        if not state.get("grace_until_epoch"):
            state["grace_until_epoch"] = anchor + \
                _grace_days(config) * DAY_SECONDS
        state["last_check"] = {"at_epoch": now, "at_iso": _iso(now),
                               "result": "service_unreachable"}
        _write_state(config, state)
        return _project(config, state)
    state["last_check"] = {"at_epoch": now, "at_iso": _iso(now),
                           "result": result["status"]}
    if result["status"] == "valid":
        state["last_valid_epoch"] = now
        state["grace_until_epoch"] = None
    else:  # revoked：真实入账（不回滚不删除；恢复只随服务端改判）
        state["grace_until_epoch"] = None
    _write_state(config, state)
    return _project(config, state)


def status(config: dict) -> dict:
    """只读投影：真实状态（含回拨 fail-closed 投影）；零副作用零伪授权。"""
    return _project(config, _load_state(config))


def license_manager_call(method: str, args: dict, config: dict) -> dict:
    if method == "license.activate":
        return activate((args or {}).get("token"), config)
    if method == "license.check":
        return check(config)
    if method == "license.status":
        return status(config)
    raise LicenseError("license_method_not_connected:" + method)
