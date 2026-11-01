"""E05 产品侧结果消费与五身份映射 broker 单测（W3-U24，全合成）。

Fake transport/runtime 完整走 consume_dispatch：五个角色各一笔（离线五身份
闭合）＋负向（未知角色/漂移不拒/重放不拒/绑定账闭字段/重复会话/回读不等）。
零 harness import——与生产面同一约束（e05_result_broker.py 模块头）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from e05_result_broker import (
    BINDING_FIELDS,
    FIVE_ROLE_IDS,
    GOAL_CONTENT_KEYS,
    ROLE_PROMPTS,
    SCHEMA_VERSION,
    E05BrokerError,
    ResultBindingStore,
    binding_entry_of,
    build_node_result,
    build_role_prompt,
    consume_dispatch,
    events_from_readback,
    role_session_id,
    validate_binding_entry,
    verify_consumption,
)

MARKER = "E05-BROKER-SYNTH-ACK"
ROLES = (
    "case-conductor",
    "intake-evidence-agent",
    "legal-research-agent",
    "drafting-agent",
    "adversarial-review-agent",
)

NODE_RESULT_FIELDS = frozenset({
    "schema_version", "node_id", "role_id", "role_contract_hash",
    "artifacts", "outputs", "claims", "payload", "open_gaps",
})


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha64(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_dispatch(role_id: str, seq: int = 0) -> dict:
    dispatch_id = "dispatch-" + sha64(f"d\0{role_id}\0{seq}".encode())[:24]
    ticket = {
        "run_id": "run-e05-test", "matter_id": "matter-e05-test",
        "node_id": f"node-{seq}", "role_id": role_id,
        "role_contract_hash": sha64(role_id.encode()),
    }
    lease = sha64(f"lease\0{dispatch_id}".encode())
    return {
        "status": "ACCEPTED", "dispatch_id": dispatch_id,
        "ticket_hash": sha64(canonical(ticket)),
        "capability_lease": lease,
        "ticket": ticket,
    }


def make_dispatch_view(dispatch: dict) -> dict:
    return {
        "dispatch_id": dispatch["dispatch_id"],
        "ticket_hash": dispatch["ticket_hash"],
        "role_id": dispatch["ticket"]["role_id"],
        "capability_lease_hash": sha64(dispatch["capability_lease"].encode("ascii")),
        "created_at": "2026-10-19T00:00:00+00:00",
        "expires_at": "2026-10-19T01:00:00+00:00",
    }


class FakeTransport:
    """合成 OpenCode 服务：会话/轮次/回读（真轮次由消息时间线模拟）。"""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.timelines: dict[str, list[dict]] = {}
        self.prompts: list[tuple[str, str, str]] = []

    def create_session(self, session_id, title, model=None):
        if session_id in self.sessions:
            raise E05BrokerError("session_exists")
        self.sessions[session_id] = {
            "id": session_id, "title": title,
            "time": {"created": 1_792_000_000_000},
        }
        self.timelines[session_id] = []
        return self.sessions[session_id]

    def session_readback(self, session_id):
        return self.sessions[session_id]

    def prompt(self, session_id, message_id, text, model=None):
        self.prompts.append((session_id, message_id, text))
        self.timelines[session_id].append(
            {"id": message_id, "type": "user",
             "time": {"created": 1_792_000_000_001}})
        answer = f"{MARKER}:{session_id}"
        self.timelines[session_id].append({
            "id": message_id + "-a", "type": "assistant",
            "model": model or {"id": "deepseek-chat"},
            "time": {"completed": 1_792_000_000_500},
            "parts": [{"type": "text", "text": answer}],
        })
        self.timelines[session_id].append(
            {"id": message_id + "-i", "type": "idle",
             "time": {"created": 1_792_000_000_900}})
        session = self.sessions[session_id]
        session["time"]["idle"] = 1_792_000_000_900
        return {"id": message_id}

    def messages(self, session_id):
        rows = self.timelines[session_id]
        return rows, canonical(rows)


class FakeRuntime:
    """合成 harness runtime facade：dispatch/node/CAS/三角闭合。"""

    def __init__(self, dispatches: dict[str, dict], nodes: list[dict]):
        self.dispatches = dispatches
        self.node_rows = nodes
        self.cas: dict[str, bytes] = {}
        self.open: set[str] = set()
        self.accepted: dict[str, dict] = {}

    def record_transcript(self, dispatch_id, lease, transcript: bytes):
        assert dispatch_id in self.open, "dispatch must be open"
        digest = sha64(transcript)
        self.cas[digest] = transcript
        return {"transcript_ref": f"cas://{digest}",
                "transcript_hash": digest, "length": len(transcript)}

    def seal_artifact(self, data: bytes) -> str:
        digest = sha64(data)
        self.cas[digest] = data
        return digest

    def nodes(self, run_id):
        return [dict(node) for node in self.node_rows]

    def run_view(self, run_id):
        return {"run_id": run_id, "matter_id": "matter-e05-test"}

    def dispatch_view(self, dispatch_id):
        return make_dispatch_view(self.dispatches[dispatch_id])

    def normalize_events(self, bundle, dispatch_view):
        # 翻译只做形状转录（词汇执法在 harness；合成面直接转录）
        return [dict(event) for event in bundle["events"]], [
            (sha64(canonical(event)), dict(event)) for event in bundle["events"]]

    def accept_canonical(self, dispatch_id, lease, canonical_events,
                         verified_events, result):
        if dispatch_id not in self.open:
            raise RuntimeError("dispatch no longer open")
        sessions = {str(event.get("child_session_id"))
                    for event in canonical_events}
        if len(sessions) != 1:
            raise RuntimeError("success_child_session_changed")
        result_hash = sha64(canonical(result))
        receipt = {
            "receipt_id": "evidence-" + sha64(dispatch_id.encode())[:16],
            "child_session_id": next(iter(sessions)),
            "result_hash": result_hash,
            "transcript_hash": str(canonical_events[-1].get("transcript_hash")),
            "ticket_hash": self.dispatches[dispatch_id]["ticket_hash"],
        }
        self.open.discard(dispatch_id)
        self.accepted[dispatch_id] = {"receipt": receipt, "result": result}
        for node in self.node_rows:
            if node["node_id"] == self.dispatches[dispatch_id]["ticket"]["node_id"]:
                node["state"] = "RESULT_ACCEPTED"
                node["accepted_result_hash"] = result_hash
        return {"status": "ACCEPTED", "accepted": True, "receipt": receipt}


def make_node(role_id: str, seq: int) -> dict:
    return {
        "node_id": f"node-{seq}", "role_id": role_id,
        "role_contract_hash": sha64(role_id.encode()),
        "required_outputs_json": json.dumps(["issue_frame"]),
        "state": "PENDING", "accepted_result_hash": None,
    }


def consume_one(role_id: str, seq: int, runtime: FakeRuntime,
                transport: FakeTransport, store: ResultBindingStore,
                **kwargs) -> dict:
    dispatch = make_dispatch(role_id, seq)
    runtime.open.add(dispatch["dispatch_id"])
    runtime.dispatches[dispatch["dispatch_id"]] = dispatch
    entry = consume_dispatch(
        transport=transport, runtime=runtime, dispatch=dispatch,
        goal_id="g-e05-test", goal_task_id="task-e05-test",
        marker=MARKER, **kwargs)
    return store.record(entry)


@pytest.fixture()
def store(tmp_path: Path) -> ResultBindingStore:
    return ResultBindingStore(tmp_path / "e05-bindings.json")


# ---------------------------------------------------------------- 五身份映射

def test_five_role_ids_closed_set() -> None:
    assert FIVE_ROLE_IDS == frozenset(ROLES)
    assert len(ROLES) == 5
    assert set(ROLE_PROMPTS) == FIVE_ROLE_IDS


def test_role_prompt_names_role_and_rejects_unknown() -> None:
    text = build_role_prompt("drafting-agent", run_id="run-1", node_id="n",
                             marker=MARKER)
    assert "drafting-agent" in text and MARKER in text
    with pytest.raises(E05BrokerError) as exc:
        build_role_prompt("generic-helper", run_id="r", node_id="n", marker="m")
    assert exc.value.code == "e05_role_not_in_five_identities"


def test_role_session_id_deterministic_and_ses_prefixed() -> None:
    one = role_session_id("dispatch-abc")
    assert one.startswith("ses_") and one == role_session_id("dispatch-abc")
    assert one != role_session_id("dispatch-other")


# ---------------------------------------------------------------- 结果消费

def test_consume_dispatch_all_five_roles_offline(store: ResultBindingStore) -> None:
    """五身份各一笔完整消费：专会/角色绑定/三角/绑定账行全过。"""
    transport = FakeTransport()
    nodes = [make_node(role, index) for index, role in enumerate(ROLES)]
    runtime = FakeRuntime({}, nodes)
    entries = [consume_one(role, index, runtime, transport, store)
               for index, role in enumerate(ROLES)]
    assert len(entries) == 5
    for entry, role in zip(entries, ROLES):
        assert entry["role_id"] == role
        assert entry["session_id"].startswith("ses_e05b_")
        assert entry["goal_id"] == "g-e05-test"
        assert entry["node_state"] == "RESULT_ACCEPTED"
        assert len({entry["session_id"] for entry in entries}) == 5
        # 绑定账行 ↔ 服务/账面回读逐项相等（合成视图）
        dispatch = runtime.dispatches[entry["dispatch_id"]]
        verify_consumption(
            entry,
            dispatch_view=runtime.dispatch_view(dispatch["dispatch_id"]),
            node=next(n for n in nodes if n["node_id"] == entry["node_id"]),
            goal_view={"goal": {"goalId": "g-e05-test"}},
            session_view=transport.session_readback(entry["session_id"]))
    # 逐角色 prompt 注入了角色身份
    prompted_roles = [text for _, _, text in transport.prompts]
    assert sum(role in text for text in prompted_roles
               for role in ROLES) == 5


def test_consume_dispatch_rejects_unknown_role(store: ResultBindingStore) -> None:
    dispatch = make_dispatch("case-conductor")
    dispatch["ticket"]["role_id"] = "generic-helper"
    with pytest.raises(E05BrokerError) as exc:
        consume_dispatch(transport=FakeTransport(), runtime=FakeRuntime({}, []),
                         dispatch=dispatch)
    assert exc.value.code == "e05_role_not_in_five_identities"


def test_consume_dispatch_rejects_unaccepted(store: ResultBindingStore) -> None:
    dispatch = make_dispatch("case-conductor")
    dispatch["status"] = "CLOSED_BLOCK"
    with pytest.raises(E05BrokerError) as exc:
        consume_dispatch(transport=FakeTransport(), runtime=FakeRuntime({}, []),
                         dispatch=dispatch)
    assert exc.value.code == "e05_dispatch_not_accepted"


def test_consume_dispatch_drift_must_be_rejected(store: ResultBindingStore) -> None:
    class NoRejectRuntime(FakeRuntime):
        def accept_canonical(self, dispatch_id, lease, canonical_events,
                             verified_events, result):
            return {"status": "ACCEPTED", "accepted": True,
                    "receipt": {"receipt_id": "r",
                                "child_session_id": canonical_events[0]["child_session_id"],
                                "result_hash": "a" * 64,
                                "transcript_hash": "b" * 64,
                                "ticket_hash": "c" * 64}}

    dispatch = make_dispatch("case-conductor")
    runtime = NoRejectRuntime({}, [make_node("case-conductor", 0)])
    runtime.open.add(dispatch["dispatch_id"])
    runtime.dispatches[dispatch["dispatch_id"]] = dispatch
    with pytest.raises(E05BrokerError) as exc:
        consume_dispatch(transport=FakeTransport(), runtime=runtime,
                         dispatch=dispatch, marker=MARKER)
    assert exc.value.code == "e05_drift_not_rejected"


def test_consume_dispatch_replay_probe_rejects_after_closure(
        store: ResultBindingStore) -> None:
    """闭合后重放不被拒 → 具名失败（harness 侧执法的 Product 侧验收）。"""

    class ReplayHappyRuntime(FakeRuntime):
        def accept_canonical(self, dispatch_id, lease, canonical_events,
                             verified_events, result):
            self.open.add(dispatch_id)  # 缺陷形态：闭合后仍可重放
            return super().accept_canonical(dispatch_id, lease,
                                            canonical_events, verified_events,
                                            result)

    dispatch = make_dispatch("case-conductor")
    runtime = ReplayHappyRuntime({}, [make_node("case-conductor", 0)])
    runtime.open.add(dispatch["dispatch_id"])
    runtime.dispatches[dispatch["dispatch_id"]] = dispatch
    with pytest.raises(E05BrokerError) as exc:
        consume_dispatch(transport=FakeTransport(), runtime=runtime,
                         dispatch=dispatch, marker=MARKER, replay_probe=True)
    assert exc.value.code == "e05_replay_not_rejected"


def test_consume_dispatch_receipt_triangle_enforced(store: ResultBindingStore) -> None:
    class BadTriangleRuntime(FakeRuntime):
        def accept_canonical(self, dispatch_id, lease, canonical_events,
                             verified_events, result):
            outcome = super().accept_canonical(dispatch_id, lease,
                                               canonical_events, verified_events,
                                               result)
            outcome["receipt"]["result_hash"] = "f" * 64
            return outcome

    dispatch = make_dispatch("case-conductor")
    runtime = BadTriangleRuntime({}, [make_node("case-conductor", 0)])
    runtime.open.add(dispatch["dispatch_id"])
    runtime.dispatches[dispatch["dispatch_id"]] = dispatch
    with pytest.raises(E05BrokerError) as exc:
        consume_dispatch(transport=FakeTransport(), runtime=runtime,
                         dispatch=dispatch, marker=MARKER)
    assert exc.value.code == "e05_receipt_triangle_mismatch"


def test_node_result_shape_and_required_outputs(store: ResultBindingStore) -> None:
    node = make_node("legal-research-agent", 2)
    node["required_outputs_json"] = json.dumps(["legal_research"])
    transport = FakeTransport()
    runtime = FakeRuntime({}, [node])
    dispatch = make_dispatch("legal-research-agent", 2)
    runtime.open.add(dispatch["dispatch_id"])
    runtime.dispatches[dispatch["dispatch_id"]] = dispatch
    consume_one("legal-research-agent", 2, runtime, transport, store)
    result = runtime.accepted[dispatch["dispatch_id"]]["result"]
    assert set(result) == NODE_RESULT_FIELDS
    assert set(node_result["output_kind"]
               for node_result in result["outputs"]) == {"legal_research"}
    assert result["role_id"] == "legal-research-agent"
    assert len(result["artifacts"][0]) == 64
    assert MARKER in json.dumps(result["payload"], ensure_ascii=False)


def test_events_carry_role_binding_and_hashes(store: ResultBindingStore) -> None:
    dispatch = make_dispatch("intake-evidence-agent", 1)
    bundle = events_from_readback(
        dispatch, "ses_x", created_ms=1792000000000, completed_ms=1792000000500,
        idle_ms=1792000000900, result_hash="a" * 64, transcript_hash="b" * 64)
    kinds = [event["event_type"] for event in bundle["events"]]
    assert kinds == ["session.created", "message.part.updated", "session.idle"]
    for event in bundle["events"]:
        assert event["role_id"] == event["agent_type"] == "intake-evidence-agent"
        assert event["ticket_hash"] == dispatch["ticket_hash"]
    assert bundle["events"][2]["result_hash"] == "a" * 64
    assert bundle["events"][2]["transcript_hash"] == "b" * 64
    assert bundle["events"][0]["result_hash"] is None


# ---------------------------------------------------------------- 绑定账

def test_binding_store_roundtrip_and_read_by_run(tmp_path: Path) -> None:
    store = ResultBindingStore(tmp_path / "b.json")
    dispatch = make_dispatch("case-conductor")
    entry = binding_entry_of(
        dispatch=dispatch, dispatch_view=make_dispatch_view(dispatch),
        receipt={"receipt_id": "evidence-x"}, result_hash="a" * 64,
        transcript_hash="b" * 64, session_id="ses_e05b_x",
        node_state="RESULT_ACCEPTED", matter_id="matter-e05-test",
        goal_id="g-1", goal_task_id="t-1")
    stored = store.record(entry)
    assert stored == entry
    reloaded = ResultBindingStore(tmp_path / "b.json")
    assert reloaded.read_by_session("ses_e05b_x")["receipt_id"] == "evidence-x"
    assert [row["dispatch_id"] for row in reloaded.read_by_run("run-e05-test")] \
        == [dispatch["dispatch_id"]]
    assert reloaded.read_by_session("ses_missing") is None


def test_binding_store_rejects_duplicate_session(tmp_path: Path) -> None:
    store = ResultBindingStore(tmp_path / "b.json")
    dispatch = make_dispatch("case-conductor")
    entry = binding_entry_of(
        dispatch=dispatch, dispatch_view=make_dispatch_view(dispatch),
        receipt={"receipt_id": "evidence-x"}, result_hash="a" * 64,
        transcript_hash="b" * 64, session_id="ses_e05b_x",
        node_state="RESULT_ACCEPTED", matter_id="matter-e05-test",
        goal_id=None, goal_task_id=None)
    store.record(entry)
    with pytest.raises(E05BrokerError) as exc:
        store.record(dict(entry))
    assert exc.value.code == "e05_binding_duplicate_session"


def test_binding_entry_fields_closed_and_metadata_only() -> None:
    dispatch = make_dispatch("case-conductor")
    entry = binding_entry_of(
        dispatch=dispatch, dispatch_view=make_dispatch_view(dispatch),
        receipt={"receipt_id": "evidence-x"}, result_hash="a" * 64,
        transcript_hash="b" * 64, session_id="ses_e05b_x",
        node_state="RESULT_ACCEPTED", matter_id="matter-e05-test",
        goal_id="g-1", goal_task_id="t-1")
    assert set(entry) == BINDING_FIELDS
    # lease 本体绝不入账（只存 sha256）；goal 内容键零出现
    assert dispatch["capability_lease"] not in json.dumps(entry)
    for key in GOAL_CONTENT_KEYS:
        assert key not in entry
    with pytest.raises(E05BrokerError) as exc:
        validate_binding_entry(dict(entry, confirmedScope="泄露 goal 内容"))
    assert exc.value.code == "e05_binding_fields_not_closed"


def test_binding_entry_rejects_bad_hashes_and_session() -> None:
    dispatch = make_dispatch("case-conductor")
    base = dict(
        dispatch=dispatch, dispatch_view=make_dispatch_view(dispatch),
        receipt={"receipt_id": "evidence-x"},
        transcript_hash="b" * 64,
        node_state="RESULT_ACCEPTED", matter_id="matter-e05-test",
        goal_id=None, goal_task_id=None)
    with pytest.raises(E05BrokerError) as exc:
        binding_entry_of(**base, result_hash="xyz", session_id="ses_e05b_x")
    assert "hash_invalid" in exc.value.code
    with pytest.raises(E05BrokerError) as exc:
        binding_entry_of(**base, result_hash="a" * 64,
                         session_id="session_no_prefix")
    assert exc.value.code == "e05_session_prefix_invalid"


def test_verify_consumption_mismatch_facets(tmp_path: Path) -> None:
    dispatch = make_dispatch("case-conductor")
    entry = binding_entry_of(
        dispatch=dispatch, dispatch_view=make_dispatch_view(dispatch),
        receipt={"receipt_id": "evidence-x"}, result_hash="a" * 64,
        transcript_hash="b" * 64, session_id="ses_e05b_x",
        node_state="RESULT_ACCEPTED", matter_id="matter-e05-test",
        goal_id="g-1", goal_task_id="t-1")
    good = dict(
        dispatch_view=make_dispatch_view(dispatch),
        node={"state": "RESULT_ACCEPTED", "accepted_result_hash": "a" * 64},
        goal_view={"goal": {"goalId": "g-1"}},
        session_view={"id": "ses_e05b_x"})
    verify_consumption(entry, **good)  # 全等不抛
    for facet, bad in (
        ("ticket", dict(good, dispatch_view=dict(
            make_dispatch_view(dispatch), ticket_hash="e" * 64))),
        ("state", dict(good, node=dict(
            {"state": "DISPATCHED", "accepted_result_hash": "a" * 64}))),
        ("result", dict(good, node=dict(
            {"state": "RESULT_ACCEPTED", "accepted_result_hash": "f" * 64}))),
        ("goal", dict(good, goal_view={"goal": {"goalId": "g-other"}})),
        ("session", dict(good, session_view={"id": "ses_other"})),
    ):
        with pytest.raises(E05BrokerError) as exc:
            verify_consumption(entry, **bad)
        assert exc.value.code.startswith("e05_readback_mismatch")


def test_binding_schema_version_pinned() -> None:
    assert SCHEMA_VERSION == "e05-binding/1"
