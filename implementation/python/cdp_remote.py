"""F65 浏览器 CDP 遥控——配对码＋按 tab 授权＋人工边界＋外部动作账公开面。

06 行 V7-65（v2；owner=product；B5；desktop/selfhost 双实例；python_entry=
UI_HOST_OR_NEW_PRODUCT）：浏览器 CDP 遥控（内置浏览器/MV3 扩展＋配对码＋
按标签页授权）；acceptance＝浏览器按 tab 授权与配对；操作受人工边界，
证据和外部副作用可对账；source_rationale＝风险高，L6 人工确认制已覆盖
主场景——人工边界负测为本面核心断言。05 §11 B5：17 已列 v2 全范围、
高级评审/CDP/商业服务及逐项依赖验收。

纪律出处（在案先例，不复制第二权威）：
- UI_HOST_OR_NEW_PRODUCT＝不冒已有业务入口：本模块不接入 legal_entry
  （W5-U03 F33 同款先例：不创第二业务入口；recon 以 legal_entry.py sha
  前后相等钉死零接线）。原生 UI/MV3 扩展触发面属产品宿主后续工单不前造
  （台账 F63-desktop failure_reason 边界句同文）。
- 外部动作授权账＝E24 已 VERIFIED 形态（W3-U26）/W4-U40 F63 授权账同构：
  append-only＋幂等重放＋scope/动作闭集＋typed 拒。
- 负测先行（裁决#8-12 同频）：未配对/未授权 tab/缺人工确认一律具名拒且
  零副作用；回执只从真实 CDP 响应转录（失败不编轨迹）；禁编 URL——
  连接端点只来自显式会话登记（宿主自持的受控浏览器实例），逐连接前过
  回环闸（先闸后网，W4-U44 T05 教训同款）。

四层模型（每层拒绝码闭集见各节）：
1. 配对（pairing_issue/pairing_bind）：宿主为受控浏览器实例签发一次性
   配对码（短 TTL、绑定 controller_id）；码原文只在签发返回值出现一次，
   状态根只存 sha256 摘要（码不落盘）；绑定一次性（二次绑定具名拒）、
   过期具名拒、controller 不匹配具名拒。绑定产出 controller_token
   （同样只返回一次，账面只存摘要）。
2. 按 tab 授权（tab_authorize）：配对后的 controller 对单个 tab（CDP
   target）逐个授权；授权前先向受控实例真实核对 tab 在位（/json/list
   转录），tab 授权与 tab 元数据（url/title）作为授权时点证据落账；
   授权必须携带人工确认（L6 人工确认制——授权本身即是人工决定面）。
   同 (session, tab) 重复授权幂等重放不双记（E24 形态）。
3. 人工边界（human_confirm）：动作执行与 tab 授权各自需要显式人工确认
   记录（confirmed_by 具名）；确认一次性（消费即具名，重用具名拒）、
   绑定 (purpose, session, tab, action_key, params 摘要)，缺确认/绑错/
   过期全具名拒。确认账 append-only 事件流（issued/consumed 两类事件，
   不改写）。
4. 动作与对账（action_execute/ledger_read）：动作闭集 v1 只有
   navigate/evaluate；幂等键 action_key——同键同内容幂等重放（不重执行、
   回执逐字同、零新副作用），同键异内容具名冲突；回执只从真实 CDP 响应
   转录并 sha256 绑定（retrieved_at 出自本地时钟仅溯源、不入摘要）；
   动作账 append-only JSONL，成功才落账（失败不编轨迹——transport 异常
   /页面异常 typed 拒零落账）。ledger_read 只读投影供独立对账（recon
   以自建独立 CDP 连接回读浏览器实态与账面回执对账）。

确定性纪律：全部显式比较；零模型零金额；唯一网络面＝会话登记端点上的
回环 CDP（127.0.0.1/localhost，先闸后网）；transport 可注入（W4-U40
F63 同款——测试/负测注入假 transport，真实 CDP transport 为默认值）。
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f65-cdp-remote/1"

# 动作闭集（v1）。新增动作须扩此闭集入账，不得隐式放行。
ACTIONS = ("navigate", "evaluate")

# 人工确认用途闭集（L6 人工确认制：授权与动作两张确认面分开）。
CONFIRM_PURPOSES = ("tab_grant", "action")

# 回环主机闭集：会话端点与逐连接 URL 的唯一合法主机。
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

# 方案闭集（会话登记端点）。
ENDPOINT_SCHEMES = ("ws://", "wss://", "http://", "https://")

DEFAULT_PAIRING_TTL_S = 300
DEFAULT_CONFIRM_TTL_S = 120
DEFAULT_IO_TIMEOUT_S = 30

# 拒绝码闭集（typed；供 recon/测试钉死比对）。
REJECTION_CODES = (
    "cdp_endpoint_not_local",
    "cdp_session_not_found",
    "cdp_pairing_code_invalid",
    "cdp_pairing_code_expired",
    "cdp_pairing_code_reused",
    "cdp_controller_mismatch",
    "cdp_not_paired",
    "cdp_tab_not_found",
    "cdp_tab_not_authorized",
    "cdp_human_confirmation_required",
    "cdp_human_confirmation_invalid",
    "cdp_human_confirmation_used",
    "cdp_human_confirmation_expired",
    "cdp_action_unknown",
    "cdp_action_key_conflict",
    "cdp_action_failed",
    "cdp_evaluate_exception",
    "cdp_params_invalid",
)


class CdpRemoteError(ValueError):
    """typed 拒绝（code ∈ REJECTION_CODES 闭集；敏感值不进码面）。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# 基础（确定性摘要／原子写／时钟）
# ---------------------------------------------------------------------------


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest_of(obj) -> str:
    return _sha256_text(_canonical(obj))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(record) + "\n")


def _read_json(path: Path, default: dict) -> dict:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list:
    if not path.is_file():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _require_str(value, code: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise CdpRemoteError(code)
    return value


# ---------------------------------------------------------------------------
# 回环闸（先闸后网：唯一网络面前置；闸自身零网络零端点构造）
# ---------------------------------------------------------------------------


def require_loopback_endpoint(url: str) -> str:
    """回环闸：方案＋主机闭集；非法/非回环 typed 拒（先于任何 I/O）。"""
    if not isinstance(url, str):
        raise CdpRemoteError("cdp_endpoint_not_local")
    if not url.startswith(ENDPOINT_SCHEMES):
        raise CdpRemoteError("cdp_endpoint_not_local")
    rest = url.split("://", 1)[1]
    host_part = rest.split("/", 1)[0].split("?", 1)[0]
    host = host_part.rsplit("@", 1)[-1]
    if host.startswith("["):  # [::1]:port
        host = host[1:host.index("]")] if "]" in host else host
    else:
        host = host.rsplit(":", 1)[0]
    host = host.lower().rstrip(".")
    if host not in LOOPBACK_HOSTS:
        raise CdpRemoteError("cdp_endpoint_not_local")
    return host


def _to_http_base(endpoint: str) -> str:
    """会话登记端点（ws(s)/http(s) 同端口）→ DevTools HTTP 基址。"""
    require_loopback_endpoint(endpoint)
    for ws_scheme, http_scheme in (("wss://", "https://"), ("ws://", "http://")):
        if endpoint.startswith(ws_scheme):
            return http_scheme + endpoint[len(ws_scheme):]
    return endpoint


# ---------------------------------------------------------------------------
# 真实 CDP transport（默认值；测试注入假 transport）
# ---------------------------------------------------------------------------


class RealCdpTransport:
    """受控实例 CDP 通道：tab 发现（HTTP /json/list）＋命令（页面级 WS）。

    逐连接前过回环闸；URL 一律来自受控实例真实响应的逐字转录
    （webSocketDebuggerUrl 出自 /json/list，不自行拼造）。
    """

    def list_tabs(self, endpoint: str) -> list:
        base = _to_http_base(endpoint).rstrip("/")
        require_loopback_endpoint(base)
        with urllib.request.urlopen(base + "/json/list",
                                    timeout=DEFAULT_IO_TIMEOUT_S) as response:
            targets = json.loads(response.read().decode("utf-8"))
        return [t for t in targets if isinstance(t, dict)]

    def command(self, ws_url: str, method: str, params: dict) -> dict:
        require_loopback_endpoint(ws_url)
        import websocket  # websocket-client（受控依赖，f82 会话先例）
        conn = websocket.create_connection(ws_url, timeout=DEFAULT_IO_TIMEOUT_S)
        try:
            conn.send(json.dumps({"id": 1, "method": method,
                                  "params": params}))
            deadline = time.monotonic() + DEFAULT_IO_TIMEOUT_S
            while time.monotonic() < deadline:
                message = json.loads(conn.recv())
                if message.get("id") == 1:
                    return message
            raise CdpRemoteError("cdp_action_failed:timeout")
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 1. 配对（一次性绑定；码原文不落盘）
# ---------------------------------------------------------------------------


def _sessions_path(state_root: Path) -> Path:
    return Path(state_root) / "cdp_pairing_sessions.json"


def _load_sessions(state_root: Path) -> dict:
    return _read_json(_sessions_path(Path(state_root)),
                      {"schema": SCHEMA, "sessions": []})


def pairing_issue(state_root, args: dict) -> dict:
    """宿主为受控浏览器实例签发一次性配对码（码原文只在返回值出现一次）。"""
    root = Path(state_root)
    endpoint = _require_str(args.get("endpoint"), "cdp_params_invalid")
    require_loopback_endpoint(endpoint)
    controller_id = _require_str(args.get("controller_id"),
                                 "cdp_params_invalid")
    pairing_ttl = args.get("pairing_ttl_s", DEFAULT_PAIRING_TTL_S)
    if not isinstance(pairing_ttl, int) or isinstance(pairing_ttl, bool) \
            or pairing_ttl <= 0:
        raise CdpRemoteError("cdp_params_invalid")
    code = secrets.token_hex(16)
    session_id = "cdpsess-" + secrets.token_hex(8)
    issued_at = _now_iso()
    session = {
        "session_id": session_id,
        "endpoint": endpoint,
        "controller_id": controller_id,
        "code_hash": _sha256_text(code),
        "pairing_ttl_s": pairing_ttl,
        "issued_at": issued_at,
        "pairing_expires_epoch": time.time() + pairing_ttl,
        "binds": [],  # 一次性：至多一条绑定记录
    }
    ledger = _load_sessions(root)
    ledger["sessions"].append(session)
    _atomic_write_json(_sessions_path(root), ledger)
    return {"session_id": session_id, "pairing_code": code,
            "controller_id": controller_id, "endpoint": endpoint,
            "pairing_ttl_s": pairing_ttl, "issued_at": issued_at,
            "schema": SCHEMA}


def pairing_bind(state_root, args: dict) -> dict:
    """controller 持码一次性绑定；绑定产出 controller_token（只返回一次）。"""
    root = Path(state_root)
    session_id = _require_str(args.get("session_id"), "cdp_params_invalid")
    code = _require_str(args.get("pairing_code"), "cdp_pairing_code_invalid")
    controller_id = _require_str(args.get("controller_id"),
                                 "cdp_params_invalid")
    ledger = _load_sessions(root)
    session = next((s for s in ledger["sessions"]
                    if s["session_id"] == session_id), None)
    if session is None:
        raise CdpRemoteError("cdp_session_not_found")
    if session["binds"]:
        raise CdpRemoteError("cdp_pairing_code_reused")
    if time.time() > session["pairing_expires_epoch"]:
        raise CdpRemoteError("cdp_pairing_code_expired")
    if controller_id != session["controller_id"]:
        raise CdpRemoteError("cdp_controller_mismatch")
    if _sha256_text(code) != session["code_hash"]:
        raise CdpRemoteError("cdp_pairing_code_invalid")
    token = secrets.token_hex(32)
    bind = {
        "bound_at": _now_iso(),
        "controller_token_hash": _sha256_text(token),
    }
    session["binds"].append(bind)  # 会话行内一次性终局（同 F59 包决定面）
    _atomic_write_json(_sessions_path(root), ledger)
    return {"session_id": session_id, "controller_token": token,
            "controller_id": controller_id, "bound_at": bind["bound_at"]}


def _paired_session(state_root: Path, session_id, token) -> dict:
    """配对态核验：会话在位＋已绑定＋token 摘要匹配（未配对一律具名拒）。"""
    _require_str(session_id if isinstance(session_id, str) else None,
                 "cdp_not_paired")
    if not isinstance(token, str) or not token:
        raise CdpRemoteError("cdp_not_paired")
    ledger = _load_sessions(state_root)
    session = next((s for s in ledger["sessions"]
                    if s["session_id"] == session_id), None)
    if session is None or not session["binds"]:
        raise CdpRemoteError("cdp_not_paired")
    if _sha256_text(token) != session["binds"][-1]["controller_token_hash"]:
        raise CdpRemoteError("cdp_not_paired")
    return session


# ---------------------------------------------------------------------------
# 3. 人工确认（L6 人工确认制；append-only 事件流 issued/consumed）
# ---------------------------------------------------------------------------


def _confirmations_path(state_root: Path) -> Path:
    return Path(state_root) / "cdp_human_confirmations.jsonl"


def human_confirm(state_root, args: dict) -> dict:
    """人工侧记录一次显式确认（用途闭集；一次性；绑定用途对象摘要）。"""
    root = Path(state_root)
    purpose = args.get("purpose")
    if purpose not in CONFIRM_PURPOSES:
        raise CdpRemoteError("cdp_params_invalid")
    session_id = _require_str(args.get("session_id"), "cdp_params_invalid")
    tab_id = args.get("tab_id")
    if tab_id is not None:
        tab_id = _require_str(tab_id, "cdp_params_invalid")
    if purpose == "tab_grant" and not tab_id:
        raise CdpRemoteError("cdp_params_invalid")
    action_key = args.get("action_key")
    params_digest = None
    if purpose == "action":
        action_key = _require_str(action_key, "cdp_params_invalid")
        action = args.get("action")
        if not isinstance(action, str) or action not in ACTIONS:
            raise CdpRemoteError("cdp_action_unknown")
        # 摘要口径与 action_execute 消费侧一致：{action, params} 复合。
        params_digest = _digest_of({"action": action,
                                    "params": args.get("params")})
    confirmed_by = _require_str(args.get("confirmed_by"),
                                "cdp_params_invalid")
    ttl_s = args.get("ttl_s", DEFAULT_CONFIRM_TTL_S)
    if not isinstance(ttl_s, int) or isinstance(ttl_s, bool) or ttl_s <= 0:
        raise CdpRemoteError("cdp_params_invalid")
    token = secrets.token_hex(24)
    event = {
        "event": "issued",
        "confirm_id": "cdpcfm-" + secrets.token_hex(6),
        "purpose": purpose,
        "session_id": session_id,
        "tab_id": tab_id,
        "action_key": action_key,
        "params_digest": params_digest,
        "confirmed_by": confirmed_by,
        "token_hash": _sha256_text(token),
        "ttl_s": ttl_s,
        "issued_at": _now_iso(),
        "expires_epoch": time.time() + ttl_s,
        "synthetic": bool(args.get("synthetic", False)),
    }
    _append_jsonl(_confirmations_path(root), event)
    out = {k: v for k, v in event.items()
           if k not in ("token_hash", "expires_epoch")}
    out["confirmation"] = token
    return out


def _consume_confirmation(state_root: Path, token, expected: dict) -> dict:
    """核验并消费人工确认：issued 未消费＋绑定逐键相等＋未过期→追加
    consumed 事件（账面不改写）。任何不符按具体原因具名拒。"""
    if not isinstance(token, str) or not token:
        raise CdpRemoteError("cdp_human_confirmation_required")
    events = _jsonl(_confirmations_path(state_root))
    issued = next((e for e in events
                   if e.get("event") == "issued"
                   and e.get("token_hash") == _sha256_text(token)), None)
    if issued is None:
        raise CdpRemoteError("cdp_human_confirmation_invalid")
    if any(e.get("event") == "consumed"
           and e.get("confirm_id") == issued["confirm_id"] for e in events):
        raise CdpRemoteError("cdp_human_confirmation_used")
    if time.time() > issued["expires_epoch"]:
        raise CdpRemoteError("cdp_human_confirmation_expired")
    for field, want in expected.items():
        if issued.get(field) != want:
            raise CdpRemoteError("cdp_human_confirmation_invalid")
    _append_jsonl(_confirmations_path(state_root), {
        "event": "consumed",
        "confirm_id": issued["confirm_id"],
        "token_hash": issued["token_hash"],
        "consumed_at": _now_iso(),
    })
    return issued


# ---------------------------------------------------------------------------
# 2. 按 tab 授权（真实 tab 在位核对；授权时点元数据转录落账）
# ---------------------------------------------------------------------------


def _grants_path(state_root: Path) -> Path:
    return Path(state_root) / "cdp_tab_grants.json"


def _load_grants(state_root: Path) -> dict:
    return _read_json(_grants_path(Path(state_root)),
                      {"schema": SCHEMA, "grants": []})


def tab_authorize(state_root, args: dict, *, transport=None) -> dict:
    """对单个 tab 授权（人工确认面 tab_grant）：真实在位核对→append-only
    授权账；同 (session, tab) 幂等重放不双记（E24 形态）。"""
    root = Path(state_root)
    transport = transport or RealCdpTransport()
    session = _paired_session(root, args.get("session_id"),
                              args.get("controller_token"))
    tab_id = _require_str(args.get("tab_id"), "cdp_params_invalid")
    confirmation = args.get("human_confirmation")
    grants = _load_grants(root)
    prior = next((g for g in grants["grants"]
                  if g["session_id"] == session["session_id"]
                  and g["tab_id"] == tab_id), None)
    if prior is not None:
        return {"grant": dict(prior), "replayed": True, "schema": SCHEMA}
    tabs = transport.list_tabs(session["endpoint"])
    target = next((t for t in tabs if t.get("id") == tab_id), None)
    if target is None:
        raise CdpRemoteError("cdp_tab_not_found")
    # tab 真实在位核对通过后才消费人工确认（fail-fast：拒路径不消耗人工
    # 决定面资源；确认绑定该 tab，存在性核对先于消费）。
    issued = _consume_confirmation(root, confirmation, {
        "purpose": "tab_grant",
        "session_id": session["session_id"],
        "tab_id": tab_id,
    })
    grant = {
        "grant_id": "cdpgrant-" + _sha256_text(
            session["session_id"] + "|" + tab_id)[:16],
        "session_id": session["session_id"],
        "tab_id": tab_id,
        "tab_url": target.get("url"),
        "tab_title": target.get("title"),
        "granted_by": issued["confirmed_by"],
        "granted_at": _now_iso(),
    }
    grants["grants"].append(grant)
    _atomic_write_json(_grants_path(root), grants)
    return {"grant": grant, "replayed": False, "schema": SCHEMA}


# ---------------------------------------------------------------------------
# 4. 动作执行与动作账（append-only；成功才落账；幂等重放/冲突）
# ---------------------------------------------------------------------------


def _ledger_path(state_root: Path) -> Path:
    return Path(state_root) / "cdp_action_ledger.jsonl"


def action_execute(state_root, args: dict, *, transport=None) -> dict:
    """执行受权动作：配对→tab 授权→人工确认→幂等键→真实 CDP→回执落账。"""
    root = Path(state_root)
    transport = transport or RealCdpTransport()
    session = _paired_session(root, args.get("session_id"),
                              args.get("controller_token"))
    tab_id = _require_str(args.get("tab_id"), "cdp_params_invalid")
    action = args.get("action")
    params = args.get("params")
    action_key = _require_str(args.get("action_key"), "cdp_params_invalid")
    if action not in ACTIONS or not isinstance(params, dict):
        raise CdpRemoteError("cdp_action_unknown")
    grants = _load_grants(root)
    if not any(g["session_id"] == session["session_id"]
               and g["tab_id"] == tab_id for g in grants["grants"]):
        raise CdpRemoteError("cdp_tab_not_authorized")
    params_digest = _digest_of({"action": action, "params": params})
    entries = _jsonl(_ledger_path(root))
    prior = next((e for e in entries if e["action_key"] == action_key), None)
    if prior is not None:
        if prior["params_digest"] != params_digest:
            raise CdpRemoteError("cdp_action_key_conflict")
        return {"action_key": action_key, "replayed": True,
                "receipt": prior["receipt"],
                "receipt_sha256": prior["receipt_sha256"],
                "executed_at": prior["executed_at"], "schema": SCHEMA}
    _consume_confirmation(root, args.get("human_confirmation"), {
        "purpose": "action",
        "session_id": session["session_id"],
        "tab_id": tab_id,
        "action_key": action_key,
        "params_digest": params_digest,
    })
    receipt, ws_url = _dispatch_action(session, tab_id, action, params,
                                       transport)
    record = {
        "action_key": action_key,
        "session_id": session["session_id"],
        "tab_id": tab_id,
        "action": action,
        "params_digest": params_digest,
        "receipt": receipt,
        "receipt_sha256": _sha256_text(_canonical(receipt)),
        "executed_at": _now_iso(),
        "schema": SCHEMA,
    }
    _append_jsonl(_ledger_path(root), record)
    return {"action_key": action_key, "replayed": False,
            "receipt": receipt,
            "receipt_sha256": record["receipt_sha256"],
            "executed_at": record["executed_at"],
            "ws_url_used": ws_url, "schema": SCHEMA}


def _dispatch_action(session: dict, tab_id: str, action: str, params: dict,
                     transport) -> tuple:
    """动作分派：唯一真实执行面。URL 全部转录自受控实例响应（禁编 URL）。"""
    tabs = transport.list_tabs(session["endpoint"])
    target = next((t for t in tabs if t.get("id") == tab_id), None)
    if target is None:
        raise CdpRemoteError("cdp_tab_not_found")
    ws_url = target.get("webSocketDebuggerUrl")
    if not isinstance(ws_url, str) or not ws_url:
        raise CdpRemoteError("cdp_action_failed:ws_url_absent")
    if action == "navigate":
        url = params.get("url")
        if not isinstance(url, str) or not url:
            raise CdpRemoteError("cdp_params_invalid")
        response = transport.command(ws_url, "Page.navigate", {"url": url})
    else:  # evaluate（闭集已验）
        expression = params.get("expression")
        if not isinstance(expression, str) or not expression:
            raise CdpRemoteError("cdp_params_invalid")
        response = transport.command(ws_url, "Runtime.evaluate",
                                     {"expression": expression,
                                      "returnByValue": True})
    if "error" in response:
        raise CdpRemoteError("cdp_action_failed:" + str(
            response["error"].get("message", "unknown")))
    result = response.get("result", {})
    if result.get("exceptionDetails") is not None:
        raise CdpRemoteError("cdp_evaluate_exception")
    # 回执只转录受控实例真实响应的确定性面（id 类易变字段不入回执语义，
    # frameId/loaderId 属响应真实内容逐字转录）。
    receipt = {"action": action, "result": result.get("result"),
               "frame_id": result.get("frameId"),
               "loader_id": result.get("loaderId"),
               "target_url": target.get("url")}
    return receipt, ws_url


def ledger_read(state_root, args: dict) -> dict:
    """只读投影（对账面）：动作账＋授权账＋会话绑定计数（零敏感值）。"""
    root = Path(state_root)
    entries = _jsonl(_ledger_path(root))
    grants = _load_grants(root)["grants"]
    sessions = _load_sessions(root)["sessions"]
    if args.get("session_id") is not None:
        session_id = _require_str(args.get("session_id"),
                                  "cdp_params_invalid")
        entries = [e for e in entries if e["session_id"] == session_id]
        grants = [g for g in grants if g["session_id"] == session_id]
        sessions = [s for s in sessions if s["session_id"] == session_id]
    return {
        "schema": SCHEMA,
        "actions": entries,
        "grants": grants,
        "sessions": [{"session_id": s["session_id"],
                      "controller_id": s["controller_id"],
                      "endpoint": s["endpoint"],
                      "bound": bool(s["binds"])} for s in sessions],
    }
