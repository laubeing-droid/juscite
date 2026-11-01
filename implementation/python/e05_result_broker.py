"""E05 产品侧结果消费与五身份映射 broker（W3-U24）。

义务来源：acceptance-ledger E05 行 failure_reason 余段「产品侧结果消费与五身份映射
留后续批次」；authority/07 E05 行 acceptance「……真实ticket/lease/角色/会话三事件/
transcriptCAS/结果消费……」。harness 侧活链已 VERIFIED（T12：ticket/lease/三事件/
CAS/三角/receipt，e05-live-integration.md）；本模块补齐产品侧另一半——把 T12 测试内
联的"临时 broker"落成产品面（opencode_v1/adapter.py:18-19 "the real producer is
wired by the juscite-side broker unit"），并对每笔消费落绑定账、支持回读核对。

职责（产品侧，零 harness import——harness 能力经注入的 runtime facade 消费，
对齐总账 §6.1a A2「产品桥经 targets/opencode 消费分支能力」）：
1. 五身份映射：五身份封闭集（harness role_contracts ROLE_CONTRACT_HASHES 同集）＋
   每角色专建 child session（dispatch 粒度确定性 ses_ id）＋逐角色 prompt；
   role 不在封闭集具名拒收（不造第六身份）。
2. 结果消费：消费一笔 dispatch（建会话→真模型轮次→回读取证三事件→transcript 入
   CAS→装配 node result→runtime_accept_canonical 三角闭合→RESULT_ACCEPTED），
   绑定账记录 OpenCode session ↔ goal/task/run/ticket/result 引用（只存引用不存
   goal 内容——e07 RecoveryStore 同款纪律）。
3. 绑定回读：read_by_session/read_by_run ＋ verify_consumption 对 harness 视图
   （dispatch/node）、目标账视图（goal）、服务视图（session 回读）逐项核对。

事件词汇/绑定硬约束全部 harness 侧执法（opencode_v1 adapter verify_raw_events：
闭字段集/sequence/ticket_hash/role_id==agent_type/时间窗/单调/同一 ses_ 会话）；
本模块只按该词汇装配，不复制第二执法。

红线：合成材料；凭据不打印不入绑定账（lease 只存 sha256）；不重试变异调用。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = "e05-binding/1"

# 五身份封闭集＝harness src/legal_harness/contracts/role_contracts.py
# ROLE_CONTRACT_HASHES 的键集（recon 工具对 harness 在盘值逐项核对，漂移即 FAIL）。
FIVE_ROLE_IDS = frozenset({
    "case-conductor",
    "intake-evidence-agent",
    "legal-research-agent",
    "drafting-agent",
    "adversarial-review-agent",
})

# 逐角色 prompt：产品侧为该角色专建 child session 注入的驱动文本（合成对账语义，
# 不承载法律规则——规则在 harness 角色合同 rules/role-contracts/*.json，由
# ticket.role_contract_hash 钉定）。
ROLE_PROMPTS = {
    "case-conductor":
        "你是律引五身份中的案经理（case-conductor）。本会话是为本票据专建的子会话，"
        "只处理票据列明的问题与输入引用；未知事实保持 unknown，不推测。",
    "intake-evidence-agent":
        "你是律引五身份中的受理取证代理（intake-evidence-agent）。本会话是为本票据"
        "专建的子会话，只做受理范围内的事实与材料清点；未知事实保持 unknown，不推测。",
    "legal-research-agent":
        "你是律引五身份中的法律研究代理（legal-research-agent）。本会话是为本票据"
        "专建的子会话，只做票据列明问题的法条研究；未知效力保持 unknown，不推测。",
    "drafting-agent":
        "你是律引五身份中的文书代理（drafting-agent）。本会话是为本票据专建的子会话，"
        "只按票据要求起草指定文书；不写票据外内容。",
    "adversarial-review-agent":
        "你是律引五身份中的对抗审查代理（adversarial-review-agent）。本会话是为本"
        "票据专建的子会话，只对票据指向的产物做对抗性审查；不代写改正文。",
}

# 绑定账闭字段集（引用面；goal 内容键一律不入账）。
BINDING_FIELDS = frozenset({
    "schema_version", "session_id", "dispatch_id", "ticket_hash",
    "capability_lease_sha256", "run_id", "matter_id", "node_id", "role_id",
    "goal_id", "goal_task_id", "result_hash", "transcript_hash", "receipt_id",
    "node_state", "recorded_at",
})

# goal 内容键（e07 RecoveryStore 同款扫描单）：绑定账只存引用，出现即拒。
GOAL_CONTENT_KEYS = ("confirmedScope", "hardConstraints", "preferences",
                     "unitTiming", "sourceDecisionRef")

SESSION_PREFIX = "ses_"
BROKER_SESSION_TAG = "ses_e05b_"

HEX64 = set("0123456789abcdef")


class E05BrokerError(Exception):
    """产品侧 broker 具名拒收（code 前缀 e05_，fail-closed 不静默）。"""

    def __init__(self, code: str, **facts):
        super().__init__(code)
        self.code = code
        self.facts = facts


def _require_hex64(value: Any, code: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or not set(value) <= HEX64):
        raise E05BrokerError(code, value=str(value)[:12])
    return value


def role_session_id(dispatch_id: str) -> str:
    """dispatch 粒度确定性 child session id（同 dispatch 同 id，重放安全）。"""
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        raise E05BrokerError("e05_dispatch_id_invalid")
    digest = hashlib.sha256(dispatch_id.encode("utf-8")).hexdigest()[:20]
    return BROKER_SESSION_TAG + digest


def build_role_prompt(role_id: str, *, run_id: str, node_id: str,
                      marker: str) -> str:
    """逐角色 prompt：角色身份句＋票据上下文＋合成回显指令。"""
    if role_id not in FIVE_ROLE_IDS:
        raise E05BrokerError("e05_role_not_in_five_identities", role_id=str(role_id))
    base = ROLE_PROMPTS[role_id]
    return (
        f"{base}\n"
        f"本次票据：run={run_id} node={node_id} role={role_id}（全合成对账材料，"
        f"非真实案件）。\n"
        f"请只原样回复一行：{marker}"
    )


def _rfc3339_utc(millis: Any) -> str:
    """服务毫秒时间戳（回读形状）→ RFC3339 UTC（T12 同款换算）。"""
    value = int(millis)
    moment = datetime.fromtimestamp(value // 1000, UTC).replace(
        microsecond=(value % 1000) * 1000)
    return moment.isoformat()


def _assistant_text(message: dict[str, Any]) -> str:
    parts = message.get("content") or message.get("parts") or []
    return "\n".join(
        str(part.get("text")) for part in parts
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
    )


def build_node_result(node: dict[str, Any], *, artifact_sha256: str,
                      session_id: str, marker: str) -> dict[str, Any]:
    """按 NODE_RESULT_FIELDS 闭集装配 node result（真实 assistant 产物入 CAS）。

    required outputs 逐项给同一 artifact 引用（output_kind 必须覆盖节点要求，
    与 T12 活链同形）；artifacts 为纯 hex digest（无 cas:// 前缀——T12 首跑
    cas_sha256_invalid 缺陷的教训钉在这里）。
    """
    _require_hex64(artifact_sha256, "e05_artifact_sha_invalid")
    required = json.loads(str(node["required_outputs_json"]))
    result = {
        "schema_version": "1.0",
        "node_id": str(node["node_id"]),
        "role_id": str(node["role_id"]),
        "role_contract_hash": str(node["role_contract_hash"]),
        "artifacts": [artifact_sha256],
        "outputs": [
            {"output_kind": kind, "artifact_sha256": artifact_sha256}
            for kind in required
        ],
        "claims": [],
        "payload": {"issues": [], "defects": [], "proposed_tasks": [],
                    "notes": [f"live session {session_id}",
                              f"marker {marker}"]},
        "open_gaps": [],
    }
    return result


def events_from_readback(dispatch: dict[str, Any], session_id: str, *,
                         created_ms: Any, completed_ms: Any, idle_ms: Any,
                         result_hash: str, transcript_hash: str) -> dict[str, Any]:
    """回读取证 → 三事件 raw 词汇 bundle（opencode_v1 adapter 闭字段集）。

    session.created→NODE_STARTED / message.part.updated→NODE_FINISHED /
    session.idle→DISPATCH_CONFIRMED；role_id==agent_type==ticket.role_id；
    observed_at＝服务真实毫秒时间戳换算 RFC3339 UTC（时间单调由服务时序保证，
    adapter 再执法）。
    """
    _require_hex64(result_hash, "e05_result_hash_invalid")
    _require_hex64(transcript_hash, "e05_transcript_hash_invalid")
    ticket = dispatch["ticket"]
    role_id = str(ticket["role_id"])
    if role_id not in FIVE_ROLE_IDS:
        raise E05BrokerError("e05_role_not_in_five_identities", role_id=role_id)
    dispatch_id = str(dispatch["dispatch_id"])
    ticket_hash = str(dispatch["ticket_hash"])

    def event(sequence: int, event_type: str, observed_ms: Any, **extra: Any) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "event_id": f"oc-e05b-{session_id}-{sequence}",
            "dispatch_id": dispatch_id, "sequence": sequence,
            "event_type": event_type, "outcome": "PASS",
            "role_id": role_id, "agent_type": role_id,
            "child_session_id": session_id, "ticket_hash": ticket_hash,
            "result_hash": extra.get("result_hash"),
            "transcript_hash": extra.get("transcript_hash"),
            "observed_at": _rfc3339_utc(observed_ms),
        }

    events = [
        event(0, "session.created", created_ms),
        event(1, "message.part.updated", completed_ms),
        event(2, "session.idle", idle_ms,
              result_hash=result_hash, transcript_hash=transcript_hash),
    ]
    return {
        "schema_version": "1.0", "dispatch_id": dispatch_id,
        "capability_lease": str(dispatch["capability_lease"]),
        "events": events,
    }


def binding_entry_of(*, dispatch: dict[str, Any], dispatch_view: dict[str, Any],
                     receipt: dict[str, Any], result_hash: str,
                     transcript_hash: str, session_id: str, node_state: str,
                     matter_id: str, goal_id: str | None,
                     goal_task_id: str | None,
                     recorded_at: str | None = None) -> dict[str, Any]:
    """消费事实 → 绑定账行（闭字段集；lease 只存 sha256；goal 只存引用）。"""
    ticket = dispatch["ticket"]
    entry = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "dispatch_id": str(dispatch["dispatch_id"]),
        "ticket_hash": str(dispatch["ticket_hash"]),
        "capability_lease_sha256": str(dispatch_view["capability_lease_hash"]),
        "run_id": str(ticket["run_id"]),
        "matter_id": str(matter_id),
        "node_id": str(ticket["node_id"]),
        "role_id": str(ticket["role_id"]),
        "goal_id": goal_id,
        "goal_task_id": goal_task_id,
        "result_hash": result_hash,
        "transcript_hash": transcript_hash,
        "receipt_id": str(receipt["receipt_id"]),
        "node_state": node_state,
        "recorded_at": recorded_at or datetime.now(UTC).isoformat(),
    }
    validate_binding_entry(entry)
    if entry["role_id"] not in FIVE_ROLE_IDS:
        raise E05BrokerError("e05_role_not_in_five_identities",
                             role_id=entry["role_id"])
    return entry


def validate_binding_entry(entry: Any) -> None:
    """闭字段集＋形状执法（session 前缀/hash 十六进制/无 goal 内容键）。"""
    if not isinstance(entry, dict) or set(entry) != BINDING_FIELDS:
        raise E05BrokerError(
            "e05_binding_fields_not_closed",
            got=sorted(entry) if isinstance(entry, dict) else type(entry).__name__)
    if entry["schema_version"] != SCHEMA_VERSION:
        raise E05BrokerError("e05_binding_schema_invalid",
                             schema=str(entry["schema_version"]))
    if not isinstance(entry["session_id"], str) \
            or not entry["session_id"].startswith(SESSION_PREFIX):
        raise E05BrokerError("e05_session_prefix_invalid",
                             session_id=str(entry["session_id"])[:16])
    for key in ("ticket_hash", "result_hash", "transcript_hash",
                "capability_lease_sha256"):
        _require_hex64(entry[key], "e05_binding_hash_invalid:" + key)
    leaked = _goal_keys_in(entry)
    if leaked:
        raise E05BrokerError("e05_binding_goal_content_leak", keys=sorted(leaked))


def _goal_keys_in(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in GOAL_CONTENT_KEYS:
                found.append(key)
            found.extend(_goal_keys_in(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_goal_keys_in(item))
    return found


def verify_consumption(entry: dict[str, Any], *, dispatch_view: dict[str, Any],
                       node: dict[str, Any], goal_view: Any,
                       session_view: dict[str, Any]) -> None:
    """绑定回读核对：绑定账行 ↔ harness 视图 ↔ 目标账 ↔ 服务现势，逐项相等。

    任一不等具名拒（e05_readback_mismatch:<facet>）——回读是消费的验收面，
    不等即账实不符，绝不静默放行。
    """
    validate_binding_entry(entry)
    facets = (
        ("dispatch_ticket_hash", str(dispatch_view.get("ticket_hash")),
         entry["ticket_hash"]),
        ("dispatch_role", str(dispatch_view.get("role_id")), entry["role_id"]),
        ("node_state", str(node.get("state")), entry["node_state"]),
        ("node_result_hash", str(node.get("accepted_result_hash")),
         entry["result_hash"]),
        ("session_id", str(session_view.get("id")), entry["session_id"]),
    )
    for name, observed, expected in facets:
        if observed != expected:
            raise E05BrokerError("e05_readback_mismatch:" + name,
                                 observed=observed, expected=expected)
    if goal_view is not None:
        observed_goal = None
        if isinstance(goal_view, dict):
            goal = goal_view.get("goal")
            if isinstance(goal, dict):
                observed_goal = goal.get("goalId")
            elif goal_view.get("goalId") is not None:
                observed_goal = goal_view.get("goalId")
        if entry["goal_id"] is not None and observed_goal != entry["goal_id"]:
            raise E05BrokerError("e05_readback_mismatch:goal_id",
                                 observed=observed_goal,
                                 expected=entry["goal_id"])


def consume_dispatch(*, transport: Any, runtime: Any, dispatch: dict[str, Any],
                     goal_id: str | None = None, goal_task_id: str | None = None,
                     marker: str = "E05-BROKER-SYNTHETIC-ACK",
                     title: str = "律引 E05 结果消费（合成）",
                     model: dict[str, str] | None = None,
                     turn_timeout: float = 420.0,
                     poll_interval: float = 1.0,
                     sleep: Callable[[float], None] = time.sleep,
                     drift_probe: bool = True,
                     replay_probe: bool = False) -> dict[str, Any]:
    """消费一笔 dispatch：建专会→真轮次→回读取证→CAS→三角→绑定账行。

    变异调用不重试（prompt 一次）；证据一律回读（SSE 挥发契约，e05-harness-recon
    §6.3）。drift_probe：三事件第二事件 child_session 漂移必须被 harness 拒
    （success_child_session_changed），不拒即具名失败；replay_probe：闭合后
    原样重放必须被拒（dispatch no longer open）。
    """
    if dispatch.get("status") != "ACCEPTED":
        raise E05BrokerError("e05_dispatch_not_accepted",
                             status=str(dispatch.get("status")))
    ticket = dispatch["ticket"]
    role_id = str(ticket["role_id"])
    if role_id not in FIVE_ROLE_IDS:
        raise E05BrokerError("e05_role_not_in_five_identities", role_id=role_id)
    run_id = str(ticket["run_id"])
    node_id = str(ticket["node_id"])
    dispatch_id = str(dispatch["dispatch_id"])
    lease = str(dispatch["capability_lease"])
    session_id = role_session_id(dispatch_id)
    if not session_id.startswith(SESSION_PREFIX):
        raise E05BrokerError("e05_session_prefix_invalid", session_id=session_id)

    # 1. dispatch 专建 child session（回读校验 id）
    readback = transport.create_session(
        session_id, f"{title} · {role_id}",
        model=model or {"id": "deepseek-chat", "providerID": "deepseek-byok"})
    if str(readback.get("id")) != session_id:
        raise E05BrokerError("e05_session_readback_mismatch",
                             observed=str(readback.get("id")))
    created_ms = (readback.get("time") or {}).get("created")
    if not isinstance(created_ms, int):
        raise E05BrokerError("e05_session_time_missing")

    # 2. 逐角色 prompt 一次（caller-persisted message id；不重试）
    message_id = "msg_e05b_" + hashlib.sha256(
        f"{dispatch_id}\0{session_id}".encode("utf-8")).hexdigest()[:24]
    transport.prompt(session_id, message_id,
                     build_role_prompt(role_id, run_id=run_id, node_id=node_id,
                                       marker=marker),
                     model=model)

    # 3. 回读为准绳：assistant 完成 → session idle
    assistant, completed_ms = _poll_completed_assistant(
        transport, session_id, turn_timeout, poll_interval, sleep)
    idle_ms = _poll_session_idle(transport, session_id, completed_ms,
                                 turn_timeout, poll_interval, sleep)

    # 4. transcript＝消息回读原始字节 → CAS
    listing, transcript_bytes = transport.messages(session_id)
    if not transcript_bytes:
        raise E05BrokerError("e05_transcript_empty")
    recorded = runtime.record_transcript(dispatch_id, lease, transcript_bytes)
    if recorded["transcript_hash"] != hashlib.sha256(transcript_bytes).hexdigest():
        raise E05BrokerError("e05_transcript_hash_mismatch")

    # 5. node result（真实 assistant 产物入 CAS）
    nodes = runtime.nodes(run_id)
    node = next((n for n in nodes if str(n["node_id"]) == node_id), None)
    if node is None:
        raise E05BrokerError("e05_node_not_found", node_id=node_id)
    artifact_sha = runtime.seal_artifact(_assistant_text(assistant).encode("utf-8"))
    result = build_node_result(node, artifact_sha256=artifact_sha,
                               session_id=session_id, marker=marker)
    result_hash = hashlib.sha256(json.dumps(
        result, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()

    # 6. 三事件 bundle（回读时间戳）
    bundle = events_from_readback(
        dispatch, session_id, created_ms=created_ms, completed_ms=completed_ms,
        idle_ms=idle_ms, result_hash=result_hash,
        transcript_hash=recorded["transcript_hash"])
    dispatch_view = runtime.dispatch_view(dispatch_id)

    # 7. 漂移负向：child_session 变更必须被拒（dispatch 保持 open）
    if drift_probe:
        drifted = [dict(event) for event in bundle["events"]]
        drifted[1]["child_session_id"] = session_id + "-drift"
        _expect_binding_rejection(
            runtime, dict(bundle, events=drifted), dispatch_view,
            dispatch_id, lease, result,
            expected="success_child_session_changed",
            code="e05_drift_not_rejected")

    # 8. 诚实链：翻译 → 三角闭合
    canonical_events, verified = runtime.normalize_events(bundle, dispatch_view)
    outcome = runtime.accept_canonical(dispatch_id, lease, canonical_events,
                                       verified, result)
    receipt = outcome.get("receipt") or {}
    if not outcome.get("accepted") or outcome.get("status") != "ACCEPTED":
        raise E05BrokerError("e05_node_result_rejected",
                             status=str(outcome.get("status")))
    if str(receipt.get("child_session_id")) != session_id \
            or str(receipt.get("result_hash")) != result_hash \
            or str(receipt.get("transcript_hash")) != recorded["transcript_hash"] \
            or str(receipt.get("ticket_hash")) != str(dispatch["ticket_hash"]):
        raise E05BrokerError("e05_receipt_triangle_mismatch")

    # 9. 闭合后重放必须拒（可选，首笔启用）
    if replay_probe:
        _expect_binding_rejection(
            runtime, bundle, dispatch_view, dispatch_id, lease, result,
            expected=None, code="e05_replay_not_rejected")

    node_state = str(next(n for n in runtime.nodes(run_id)
                          if str(n["node_id"]) == node_id)["state"])
    if node_state != "RESULT_ACCEPTED":
        raise E05BrokerError("e05_node_state_not_accepted", state=node_state)
    matter_id = str(runtime.run_view(run_id)["matter_id"])
    return binding_entry_of(
        dispatch=dispatch, dispatch_view=dispatch_view, receipt=receipt,
        result_hash=result_hash, transcript_hash=recorded["transcript_hash"],
        session_id=session_id, node_state=node_state, matter_id=matter_id,
        goal_id=goal_id, goal_task_id=goal_task_id)


def _expect_binding_rejection(runtime: Any, bundle: dict[str, Any],
                              dispatch_view: dict[str, Any], dispatch_id: str,
                              lease: str, result: dict[str, Any], *,
                              expected: str | None, code: str) -> None:
    """负向探针：normalize+accept 必须抛绑定拒收；不抛或码不对即具名失败。

    harness 侧拒收异常类型不进产品面（零 import）——按异常文本内的 harness
    具名码判定（success_child_session_changed / dispatch closed 形态）。
    """
    try:
        canonical_events, verified = runtime.normalize_events(bundle, dispatch_view)
        runtime.accept_canonical(dispatch_id, lease, canonical_events,
                                 verified, result)
    except Exception as error:  # noqa: BLE001 - 期望路径：必须是 harness 绑定拒收
        text = str(error)
        if expected is not None and expected not in text:
            raise E05BrokerError(code, observed=text[:80]) from error
        return
    raise E05BrokerError(code)


def _poll_completed_assistant(transport: Any, session_id: str, timeout: float,
                              poll_interval: float,
                              sleep: Callable[[float], None]):
    deadline = time.monotonic() + timeout
    while True:
        listing, _ = transport.messages(session_id)
        for message in listing:
            if message.get("type") != "assistant":
                continue
            time_shape = message.get("time") or {}
            observed = time_shape.get("completed") or time_shape.get("streamed")
            if observed and _assistant_text(message):
                return message, int(observed)
        if time.monotonic() >= deadline:
            raise E05BrokerError("e05_turn_not_completed", session_id=session_id)
        sleep(poll_interval)


def _poll_session_idle(transport: Any, session_id: str, completed_ms: int,
                       timeout: float, poll_interval: float,
                       sleep: Callable[[float], None]) -> int:
    deadline = time.monotonic() + timeout
    while True:
        readback = transport.session_readback(session_id)
        idle = (readback.get("time") or {}).get("idle")
        if isinstance(idle, int) and idle >= completed_ms:
            return idle
        if time.monotonic() >= deadline:
            raise E05BrokerError("e05_idle_not_observed", session_id=session_id)
        sleep(poll_interval)


class ResultBindingStore:
    """绑定账（JSON 原子写、append-only、闭字段集；引用面无 goal 内容）。"""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._rows: list[dict[str, Any]] = []
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("schema") != "e05-bindings/1":
                raise E05BrokerError("e05_binding_store_schema_invalid",
                                     schema=str(raw.get("schema")))
            self._rows = list(raw.get("bindings", []))

    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        validate_binding_entry(entry)
        if self.read_by_session(entry["session_id"]) is not None:
            raise E05BrokerError("e05_binding_duplicate_session",
                                 session_id=entry["session_id"])
        self._rows.append(dict(entry))
        self._flush()
        return dict(entry)

    def read_by_session(self, session_id: str) -> dict[str, Any] | None:
        for row in self._rows:
            if row["session_id"] == session_id:
                return dict(row)
        return None

    def read_by_run(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows if row["run_id"] == run_id]

    def all(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": "e05-bindings/1", "bindings": self._rows}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, self.path)
