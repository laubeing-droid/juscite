"""F24 Host 侧投影/游标/批准恢复元数据存储（W3-U03）。

义务 06 F24 acceptance：「所选核心Session与Harness业务run/goal各唯一
owner；Host只有投影/游标/批准恢复元数据，同键重放异内容拒绝，不另造业
务终局」。本模块是宿主（产品端）唯一新增 F24 落地面：

- 只存三类元数据：core session 引用（transport）、run 游标
  （headSeq，事件流断线续读指针＝SSE cursor 的宿主侧消费位）、批准/
  恢复元数据（人工批准·恢复决定的账面锚引用＝harness run.approval
  事件键，不携带业务内容）；
- 业务事实的真源全部在 owner 侧：run/goal 账在 harness（public 公开
  面），core session 账在服务端——本存储结构性不含 goal 内容字段、不
  含 run 终局字段，也没有任何写入业务终局的 API（终局只能来自 owner
  链 terminal_results，宿主只能经 harness 公开面回读投影）；
- 同键重放语义在宿主侧的形态：游标更新按 runId 覆盖（游标不是账），
  批准元数据按 (runId, decision, decisionRef) 幂等去重——宿主不产生
  第二业务账，重复批准记录不叠加。

schema: f24-runhost/1。原子写（tmp+os.replace）。测试
test_f24_f26_wiring.py 钉死：零 goal 内容键、零终局字段、模块无终局
写入 API（AST）、重复批准幂等、游标覆盖。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SCHEMA = "f24-runhost/1"

# 结构性禁入键（=goal 内容字段：宿主存储永不是第二 goal 账；E07
# RecoveryStore 同款清单）。
GOAL_CONTENT_KEYS = frozenset({
    "confirmedScope", "hardConstraints", "preferences",
    "unitTiming", "sourceDecisionRef",
})
# 结构性禁入键（=业务终局字段：终局只能来自 owner 链，宿主不签终局）。
TERMINAL_FORBIDDEN_KEYS = frozenset({
    "terminal", "terminalResult", "terminalResultHash", "resultHash",
    "finalVerdict", "businessOutcome",
})

_RUN_HOST_FIELDS = frozenset({
    "schema", "sessionRefs", "runCursors", "approvals",
})
_APPROVAL_FIELDS = frozenset({
    "runId", "decision", "decisionRef", "decidedAt",
})
_APPROVAL_DECISIONS = frozenset({"approved", "resumed"})
_CURSOR_FIELDS = frozenset({"headSeq", "updatedAt"})
_METADATA_LIMIT = 1000


class RunCursorStoreError(ValueError):
    """宿主存储守卫 typed 错误；str(...) 即错误码。"""


def _guard_metadata(state: dict) -> None:
    """禁入键守卫：任何层级的 goal 内容/终局字段一律具名拒（fail-closed）。"""

    def _walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in GOAL_CONTENT_KEYS:
                    raise RunCursorStoreError(
                        f"run_host_goal_content_forbidden:{key}")
                if key in TERMINAL_FORBIDDEN_KEYS:
                    raise RunCursorStoreError(
                        f"run_host_terminal_field_forbidden:{key}")
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(state)


class RunCursorStore:
    """宿主投影/游标/批准恢复元数据（只此三类，别无业务事实）。"""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {"schema": SCHEMA, "sessionRefs": {},
                    "runCursors": {}, "approvals": []}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RunCursorStoreError("run_host_store_corrupt") from None
        if not isinstance(state, dict) or state.get("schema") != SCHEMA:
            raise RunCursorStoreError("run_host_store_schema_unknown")
        extra = set(state) - set(_RUN_HOST_FIELDS)
        if extra:
            raise RunCursorStoreError(
                f"run_host_store_fields_not_closed:{sorted(extra)}")
        state.setdefault("sessionRefs", {})
        state.setdefault("runCursors", {})
        state.setdefault("approvals", [])
        _guard_metadata(state)
        return state

    def save(self, state: dict) -> None:
        if not isinstance(state, dict) or state.get("schema") != SCHEMA:
            raise RunCursorStoreError("run_host_store_shape_invalid")
        extra = set(state) - set(_RUN_HOST_FIELDS)
        if extra:
            raise RunCursorStoreError(
                f"run_host_store_fields_not_closed:{sorted(extra)}")
        if set(state) != set(_RUN_HOST_FIELDS):
            raise RunCursorStoreError("run_host_store_shape_invalid")
        _guard_metadata(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, self.path)

    # -- core session 引用（transport 元数据；session 账主=core）-----------

    def record_session_ref(self, scope_key: str, session_id: str) -> dict:
        state = self.load()
        refs = state["sessionRefs"]
        if not isinstance(scope_key, str) or not scope_key \
                or not isinstance(session_id, str) or not session_id:
            raise RunCursorStoreError("run_host_session_ref_invalid")
        previous = refs.get(scope_key)
        refs[scope_key] = session_id
        self.save(state)
        return {"scopeKey": scope_key, "sessionId": session_id,
                "previous": previous, "replayed": previous == session_id}

    # -- run 游标（SSE cursor 消费位；游标不是账，按 runId 覆盖）----------

    def update_cursor(self, run_id: str, head_seq: int,
                      updated_at: str) -> dict:
        state = self.load()
        if not isinstance(run_id, str) or not run_id \
                or isinstance(head_seq, bool) or not isinstance(head_seq, int) \
                or head_seq < 0 or not isinstance(updated_at, str):
            raise RunCursorStoreError("run_host_cursor_invalid")
        cursors = state["runCursors"]
        previous = cursors.get(run_id)
        if previous is not None and int(previous.get("headSeq", -1)) > head_seq:
            # 游标回退＝投影源倒退，拒不采纳（游标单调）。
            raise RunCursorStoreError("run_host_cursor_regressed")
        cursors[run_id] = {"headSeq": head_seq, "updatedAt": updated_at}
        self.save(state)
        return {"runId": run_id, "headSeq": head_seq,
                "previous": (None if previous is None
                             else previous.get("headSeq"))}

    def read_cursor(self, run_id: str) -> int | None:
        state = self.load()
        cursor = state["runCursors"].get(run_id)
        return None if cursor is None else int(cursor["headSeq"])

    # -- 批准/恢复元数据（账面锚引用；幂等去重，宿主不产生第二账）--------

    def record_approval(self, run_id: str, decision: str,
                        decision_ref: str, decided_at: str) -> dict:
        state = self.load()
        if not isinstance(run_id, str) or not run_id \
                or decision not in _APPROVAL_DECISIONS \
                or not isinstance(decision_ref, str) or not decision_ref \
                or not isinstance(decided_at, str):
            raise RunCursorStoreError("run_host_approval_invalid")
        entry = {"runId": run_id, "decision": decision,
                 "decisionRef": decision_ref, "decidedAt": decided_at}
        approvals = state["approvals"]
        if len(approvals) >= _METADATA_LIMIT:
            raise RunCursorStoreError("run_host_approval_overflow")
        if entry in approvals:
            return {"approval": entry, "replayed": True,
                    "approvalCount": len(approvals)}
        approvals.append(entry)
        self.save(state)
        return {"approval": entry, "replayed": False,
                "approvalCount": len(approvals)}
