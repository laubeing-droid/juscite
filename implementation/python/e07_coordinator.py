"""E07 product-side minimal coordinator over the harness goal ledger.

Contract: harness docs/e07-goal-contract.md §5 (five product integration
points) + 05-V8完整施工方案 §2.1 暂停紧箍咒. Boundaries, all mechanical:

- ONE public session turn per advance_turn() call — reuse the OpenCode core
  loop via opencode_http.Client (PIN 2.0.28); never an agent loop, never a
  copied runner (dispatch/tickets/leases stay in the harness opencode target).
- No second goal ledger: every goal fact is read from / written through the
  harness bridge (legal_entry → public_entry --goal-json, resolve_provider_method).
- Mutations are never blindly retried. An uncertain prompt outcome is an
  UNKNOWN: reconcile the caller-persisted message id against the session
  inbox (durable admission queue) and message history before anything else.
- STALE basis never auto-continues: preflight returns it to the human.
- resume_goal is the only wake-up channel and it is explicit (user action);
  nothing in this module calls it except user_resume_goal().
- Product persists transport/recovery metadata only (session_ref, message
  ids, seq, ledger request ids) — never goal content.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

from opencode_http import Client, TransportError

# Same closed vocabulary as goal_basis.PAUSE_REASONS (juscite seed) and
# harness GOAL_PAUSE_BOUNDARIES (units.py) — one set, three names aligned.
from goal_basis import PAUSE_REASONS
# Shared error objects (single module even when legal_entry runs as a script).
from bridge_errors import NotConnected, SessionRejected

MESSAGE_ID_PREFIX = "msg_"
DEV_VERSION_PREFIX = "2.0.0-local-"


class CoordinatorBlocked(RuntimeError):
    """Preflight refused to advance; code is a machine reason, not prose."""

    def __init__(self, code: str, detail: dict | None = None):
        self.code, self.detail = code, detail or {}
        super().__init__(code)


# ------------------------------------------------------------------ ③ UI 数据源

def pause_banner(open_pause: dict | None) -> dict:
    """Harness openPause → the always-on pause UI projection.

    紧箍咒②：原生 UI 常显「已暂停 · 原因 · 一键续跑」；续跑唯一后端动作
    = harness.resume_goal 显式调用。No pause → paused=False so the UI can
    render the running state from the same call.
    """
    if not open_pause:
        return {"paused": False}
    boundary = open_pause.get("boundary", "")
    trigger_value = open_pause.get("triggerValue", "")
    return {
        "paused": True,
        "boundary": boundary,
        "triggerValue": trigger_value,
        "pausedAt": open_pause.get("pausedAt"),
        "detail": open_pause.get("detail", ""),
        "display": "已暂停 · {}（触发值 {}） · 一键续跑".format(boundary, trigger_value),
        "resume": {
            "method": "harness.resume_goal",
            "explicit": True,
            "pauseIdx": open_pause.get("pauseIdx"),
        },
    }


# ------------------------------------------------- ⑤ F-9 session-creation guard

def _pattern_intersects(pattern: str, other: str) -> bool:
    """Conservative wildcard overlap: assume overlap unless provably disjoint.

    Two literal (wildcard-free) patterns intersect only when equal; any
    wildcard side can reach the other, so it counts as intersecting. Being
    over-broad rejects more sessions — the fail-closed direction F-9 wants.
    """
    if "*" in pattern or "*" in other:
        return True
    return pattern == other


def policy_conflicts(permissions: list, policies: list) -> list:
    """Session allow rules that intersect a product policy deny (T18 定论).

    A policy entry {action: "tool.use", resource: "shell:*"} governs requests
    named by the resource's first segment ("shell"); the tail is the resource
    pattern over the tool's operands. A session allow rule whose action can
    reach that name AND whose resource can reach that operand space would
    allow during the transient pre-activation window what the policy vetoes
    after convergence — the only hole configuration diffs cannot close.
    """
    conflicts = []
    for rule in permissions or []:
        if not isinstance(rule, dict) or rule.get("effect") != "allow":
            continue
        action = str(rule.get("action", ""))
        resource = str(rule.get("resource", ""))
        for policy in policies or []:
            if not isinstance(policy, dict) or policy.get("effect") != "deny":
                continue
            governed, _, tail = str(policy.get("resource", "")).partition(":")
            tail = tail or "*"
            if _pattern_intersects(action, governed) and _pattern_intersects(resource, tail):
                conflicts.append({"rule": rule, "policy": policy})
    return conflicts


DEFAULT_POLICIES_PATH = Path(
    os.environ.get("APPDATA", str(Path.home()))
) / "Juscite" / "config" / "opencode" / "opencode.json"


def load_product_policies(path: Path | str | None = None) -> list:
    """Read experimental.policies from the product opencode.json (read-only)."""
    target = Path(path) if path is not None else DEFAULT_POLICIES_PATH
    if not target.exists():
        return []
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    return data.get("experimental", {}).get("policies", [])


# --------------------------------------------------------- transport/recovery ④

class RecoveryStore:
    """Product-side transport & recovery metadata (contract §5.5).

    Holds session_ref / seq / message ids / ledger request ids ONLY — no goal
    content ever lands here (that would be a second goal ledger).
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {"schema": "e07-recovery/1", "session_ref": None, "seq": 0,
                    "commands": {}, "turns": []}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("recovery_store_corrupt") from None
        if not isinstance(state, dict) or state.get("schema") != "e07-recovery/1":
            raise ValueError("recovery_store_schema_unknown")
        state.setdefault("session_ref", None)
        state.setdefault("seq", 0)
        state.setdefault("commands", {})
        state.setdefault("turns", [])
        return state

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def next_id(self, prefix: str) -> str:
        """Bump seq and derive a deterministic id (write-ahead safe)."""
        state = self.load()
        state["seq"] = int(state["seq"]) + 1
        value = "{}_{}".format(prefix, state["seq"])
        self.save(state)
        return value

    def command_id(self, purpose: str) -> str:
        """Stable ledger requestId per purpose (idempotent replay after crash)."""
        state = self.load()
        commands = state["commands"]
        if purpose not in commands:
            state["seq"] = int(state["seq"]) + 1
            commands[purpose] = "e07-cmd_{}".format(state["seq"])
            self.save(state)
        return commands[purpose]

    def record_turn(self, turn: dict) -> None:
        state = self.load()
        turns = [t for t in state["turns"] if t.get("messageId") != turn["messageId"]]
        turns.append(turn)
        state["turns"] = turns
        state["session_ref"] = turn.get("sessionRef", state.get("session_ref"))
        self.save(state)

    def unresolved_turn(self) -> dict | None:
        for turn in reversed(self.load()["turns"]):
            if turn.get("state") in ("SUBMITTING", "SUBMITTED_UNKNOWN", "ENQUEUED",
                                     "PENDING", "CLAIMED_PENDING"):
                return turn
        return None


class BridgeGoalLedger:
    """The only goal authority: legal_entry → public_entry --goal-json."""

    def __init__(self, config: dict):
        self.config = config

    def call(self, method: str, params: dict):
        import legal_entry
        return legal_entry.call(method, params, self.config)


# ------------------------------------------------------------------ coordinator

class Coordinator:
    """Reads the goal account, advances one public session turn per call."""

    def __init__(self, ledger, client, store, *, actor_id="product-coordinator",
                 turn_timeout=120.0, poll_interval=1.0, version_pin="2.0.28",
                 budget_gate=None):
        self.ledger = ledger
        self.client = client
        self.store = store
        self.actor_id = actor_id
        self.turn_timeout = turn_timeout
        self.poll_interval = poll_interval
        self.version_pin = version_pin
        # F28 (W3-U04): optional mechanical-budget gate (turn_budget.BudgetGate
        # duck type). E07 §7 left budget triggering to "后续预算工单" — this is
        # that work order. When set, every advance_turn records its transport
        # facts (tokens / cost minor / elapsed / failure code) into the gate;
        # an exceeded verdict is written to the REAL harness goal ledger via
        # pause_goal (紧箍咒: boundary + triggerValue + time in the account),
        # so the NEXT preflight blocks — the tool face converges and stays
        # paused until the explicit user resume.
        self.budget_gate = budget_gate

    # -- service version (F-4 dual-track: record actual, flag dev) ----------

    def service_version(self):
        info = self.client.request("GET", "/api/info")
        value = info.get("data", info) if isinstance(info, dict) else {}
        version = value.get("version") if isinstance(value, dict) else None
        if version != self.version_pin and not (
            isinstance(version, str) and version.startswith(DEV_VERSION_PREFIX)
        ):
            raise TransportError("runtime_version_mismatch")
        return version, version != self.version_pin

    # -- ⑤ F-9 session-creation entry ----------------------------------------

    def create_session(self, payload: dict, *, policies: list | None = None):
        """Create a public session behind the fail-closed permission guard."""
        guards = policies if policies is not None else load_product_policies()
        conflicts = policy_conflicts((payload or {}).get("permissions"), guards)
        if conflicts:
            raise SessionRejected(
                "session_allow_conflicts_policy_deny:" + json.dumps(
                    conflicts[0]["rule"], ensure_ascii=False, sort_keys=True)
            )
        return self.client.create(payload)

    # -- 开工前（§5.1）：get_goal/list_goals/read_goal_basis ------------------

    def preflight(self, scope: dict, goal_id: str | None = None,
                  task_id: str | None = None, current: dict | None = None) -> dict:
        goals = self.ledger.call("harness.list_goals", {"scope": scope})
        items = goals.get("items", [])
        if goal_id is None:
            if not items:
                return {"decision": "NO_GOAL", "banner": pause_banner(None), "basis": None}
            if len(items) > 1:
                return {"decision": "AMBIGUOUS", "items": items,
                        "banner": pause_banner(None), "basis": None}
            goal_id = items[0]["goalId"]
        account = self.ledger.call(
            "harness.get_goal", {"scope": scope, "goal_id": goal_id})
        banner = pause_banner(account.get("openPause"))
        if account.get("openPause") is not None:
            return {"decision": "PAUSED", "goalId": goal_id, "banner": banner,
                    "basis": None, "account": account}
        if account.get("status") == "revoked":
            return {"decision": "REVOKED", "goalId": goal_id, "banner": banner,
                    "basis": None, "account": account}
        basis = None
        if task_id is not None:
            query = {"goalId": goal_id, "taskId": task_id}
            if current:
                query["current"] = current
            basis = self.ledger.call(
                "harness.read_goal_basis", {"scope": scope, "query": query})
            if basis.get("status") != "CURRENT":
                # STALE 不自动续跑，交回人（e07-goal-contract §5.1）
                return {"decision": "STALE_RETURN_TO_HUMAN", "goalId": goal_id,
                        "banner": banner, "basis": basis, "account": account}
        return {"decision": "READY", "goalId": goal_id, "banner": banner,
                "basis": basis, "account": account}

    # -- 机械边界暂停（§5.2）：boundary 闭集 + triggerValue 必填 --------------

    def pause_goal(self, scope: dict, goal_id: str, boundary: str,
                   trigger_value: str, detail: str = "") -> dict:
        if boundary not in PAUSE_REASONS:
            raise ValueError("goal_pause_boundary_invalid")
        if not isinstance(trigger_value, str) or not trigger_value:
            raise ValueError("goal_pause_trigger_invalid")
        # Episode-scoped requestId: count the ledger's pause entries so a
        # retry after a timeout replays the SAME episode, while a new episode
        # (after an explicit resume) gets a fresh CommandKey — an identical
        # envelope under a replayed id would silently skip the second write.
        pauses = self.ledger.call("harness.list_goal_pauses",
                                  {"scope": scope, "goal_id": goal_id})
        episode = len(pauses.get("items", [])) + 1
        params = {
            "actor_id": self.actor_id, "scope": scope,
            "key": self._key("pause:{}:{}:{}".format(goal_id, boundary, episode)),
            "pause": {"goalId": goal_id, "boundary": boundary,
                      "triggerValue": trigger_value, "detail": detail},
        }
        return self.ledger.call("harness.pause_goal", params)

    # -- 用户一键续跑（§5.3）：唯一显式恢复通道 --------------------------------

    def user_resume_goal(self, scope: dict, goal_id: str,
                         pause_idx: int | None = None) -> dict:
        if pause_idx is None:
            # 一键续跑 without an explicit index resolves the open pause from
            # the ledger (the account is the only goal truth) and refuses
            # cleanly when nothing is paused.
            account = self.ledger.call(
                "harness.get_goal", {"scope": scope, "goal_id": goal_id})
            open_pause = account.get("openPause")
            if open_pause is None:
                raise CoordinatorBlocked("goal_not_paused", {"goalId": goal_id})
            pause_idx = open_pause.get("pauseIdx")
        resume = {"goalId": goal_id, "pauseIdx": pause_idx}
        params = {
            "actor_id": self.actor_id, "scope": scope,
            "key": self._key("resume:{}:{}".format(goal_id, pause_idx)),
            "resume": resume,
        }
        result = self.ledger.call("harness.resume_goal", params)
        if self.budget_gate is not None:
            # F28: an explicit user resume starts a fresh meter episode
            # (the durable pause fact stays in the goal ledger).
            reset = getattr(self.budget_gate, "reset", None)
            if callable(reset):
                reset()
        return result

    # -- 范围变更（§5.4）：decide_goal_plan ------------------------------------

    def decide_goal_plan(self, scope: dict, decision: dict) -> dict:
        goal_id = decision.get("goalId", "")
        return self.ledger.call("harness.decide_goal_plan", {
            "actor_id": self.actor_id, "scope": scope,
            # decision in the key: the same decision replays after a timeout,
            # while re-deciding the same plan version (改判允许，contract §2)
            # gets a fresh CommandKey instead of a conflict.
            "key": self._key("plan:{}:{}:{}:{}".format(
                goal_id, decision.get("planId", ""),
                decision.get("planRevision", ""), decision.get("decision", ""))),
            "decision": decision,
        })

    def _key(self, purpose: str) -> dict:
        # CommandKey shape per harness tests/test_e07_goal_ledger.py
        # (command_key): targetId=None — the goal-ledger methods carry their
        # own state guards, and a non-null targetId would arm command_tx's
        # object-revision check (command_tx.py:69-76) which pause/resume do
        # not want.
        return {"requestId": self.store.command_id(purpose), "targetId": None,
                "expectedRevision": None, "inputRefs": []}

    # -- F28 预算检查点：度量入闸；超限写真实 goal 账（机械暂停）-------------

    def _budget_checkpoint(self, scope: dict, plan: dict, *, tokens: int = 0,
                           cost_minor: int = 0, elapsed_s: float = 0.0,
                           failure_code: str | None = None) -> dict | None:
        if self.budget_gate is None or not plan.get("goalId"):
            return None
        verdict = self.budget_gate.record_turn(
            tokens=tokens, cost_minor=cost_minor, elapsed_s=elapsed_s,
            failure_code=failure_code)
        if not verdict.get("exceeded"):
            return {"verdict": verdict}
        detail = json.dumps(verdict.get("detail") or {},
                            ensure_ascii=False, sort_keys=True)
        pause = self.pause_goal(scope, plan["goalId"], verdict["boundary"],
                                verdict["triggerValue"], detail=detail)
        return {"verdict": verdict, "pause": pause}

    # -- 推进公开 session turn（§5 + 05:35）------------------------------------

    def advance_turn(self, scope: dict, session_id: str, text: str, *,
                     message_id: str | None = None, goal_id: str | None = None,
                     task_id: str | None = None, current: dict | None = None,
                     usage: dict | None = None) -> dict:
        started = time.monotonic()
        plan = self.preflight(scope, goal_id=goal_id, task_id=task_id, current=current)
        if plan["decision"] != "READY":
            raise CoordinatorBlocked("preflight_" + plan["decision"].lower(), plan)
        unresolved = self.store.unresolved_turn()
        if unresolved is not None and unresolved.get("sessionRef") == session_id:
            # 上一轮仍未知/未完成：先对账，绝不盲补发（mutation 不盲重试）
            raise CoordinatorBlocked("unresolved_previous_turn", unresolved)
        if message_id is None:
            message_id = self.store.next_id("msg_e07")
        if not message_id.startswith(MESSAGE_ID_PREFIX):
            raise ValueError("message_id_requires_msg_prefix")
        turn = {"messageId": message_id, "sessionRef": session_id,
                "goalRef": (plan.get("account") or {}).get("goalRef"),
                "state": "SUBMITTING"}
        self.store.record_turn(turn)  # write-ahead: id survives a crash mid-POST
        turn_tokens = int((usage or {}).get("tokens", 0) or 0)
        turn_cost = (usage or {}).get("cost_minor", 0) or 0
        try:
            self.client.prompt(session_id, {"id": message_id, "text": text})
            turn["state"] = "SUBMITTED"
            self.store.record_turn(dict(turn))
        except TransportError as exc:
            if not exc.uncertain:
                turn["state"] = "FAILED_TRANSPORT"
                self.store.record_turn(dict(turn))
                self._budget_checkpoint(
                    scope, plan, elapsed_s=time.monotonic() - started,
                    failure_code=exc.code)
                raise
            # 超时=未知：先对账 inbox/history，再决定下一步（不自动重发）
            self._budget_checkpoint(
                scope, plan, elapsed_s=time.monotonic() - started,
                failure_code=exc.code)
            claim = self.reconcile(session_id, message_id)
            turn["state"] = claim["claimState"]
            turn["reconcile"] = claim
            self.store.record_turn(dict(turn))
            return {"state": "UNKNOWN_RECONCILED", "turn": turn, "claim": claim}
        outcome = self._await_turn(session_id, message_id)
        turn["state"] = outcome["state"]
        turn["assistantChars"] = len(outcome.get("assistantText") or "")
        self.store.record_turn(dict(turn))
        budget = self._budget_checkpoint(
            scope, plan, tokens=turn_tokens, cost_minor=turn_cost,
            elapsed_s=time.monotonic() - started)
        result = {"state": outcome["state"], "turn": turn, **outcome}
        if budget is not None:
            result["budget"] = budget["verdict"]
            if budget.get("pause") is not None:
                # 横幅显示唯一真源＝goal 账 openPause（下一次 preflight/
                # pause_banner 回读）；这里只回放触发事实供调用方记录。
                result["budgetPause"] = {
                    "goalId": plan["goalId"],
                    "boundary": budget["verdict"]["boundary"],
                    "triggerValue": budget["verdict"]["triggerValue"],
                    "detail": budget["verdict"].get("detail") or {},
                }
        return result

    def _await_turn(self, session_id: str, message_id: str) -> dict:
        deadline = time.monotonic() + self.turn_timeout
        while True:
            outcome = self._inspect_history(session_id, message_id)
            if outcome["state"] in ("COMPLETE",) or time.monotonic() >= deadline:
                return outcome
            time.sleep(self.poll_interval)

    @staticmethod
    def _scan_messages(messages: list, message_id: str) -> dict:
        position = None
        for index, message in enumerate(messages):
            if message.get("id") == message_id:
                position = index
                break
        if position is None:
            return {"found": False, "assistantText": None}
        texts = []
        for message in messages[position + 1:]:
            if message.get("type") == "idle":
                break
            if message.get("type") != "assistant":
                continue
            for part in message.get("content") or message.get("parts") or []:
                if part.get("type") == "text" and part.get("text"):
                    texts.append(part["text"])
        return {"found": True, "assistantText": "\n".join(texts) if texts else None}

    def _fetch_messages(self, session_id: str) -> list:
        """Full message timeline, oldest first, across cursor pages.

        Live-API contract (v2 protocol message.ts SessionMessagesQuery):
        default order is newest-first and responses are paged — an
        anchor-relative scan must pin ?order=asc and follow cursor.next, or a
        finished turn reads PENDING forever (live-recon catch, W1-U06).
        """
        messages: list = []
        path = "/api/session/{}/message?order=asc".format(_quote(session_id))
        while path:
            listing = self.client.request("GET", path)
            if not isinstance(listing, dict):
                return messages
            messages.extend(listing.get("data", []))
            cursor = (listing.get("cursor") or {}).get("next")
            # cursor is opaque and must not be combined with order (contract).
            path = "/api/session/{}/message?cursor={}".format(
                _quote(session_id), _quote(str(cursor))) if cursor else None
        return messages

    def _inspect_history(self, session_id: str, message_id: str) -> dict:
        scan = self._scan_messages(self._fetch_messages(session_id), message_id)
        if not scan["found"]:
            return {"state": "PENDING", "assistantText": None}
        if scan["assistantText"]:
            return {"state": "COMPLETE", "assistantText": scan["assistantText"]}
        return {"state": "PENDING", "assistantText": None}

    # -- ④ inbox/claim 对账（S0 已验服务持久化为底）----------------------------

    def reconcile(self, session_id: str, message_id: str) -> dict:
        """Claim a message id against the durable admission queue + history.

        S0-verified persistence base (00-总协调 §2.1): sessions and their
        messages survive full service restarts, so a readback — never a
        resubmit — is the authoritative recovery move.
        """
        report = {"messageId": message_id, "sessionRef": session_id,
                  "claimState": "NOT_ADMITTED", "resubmitRequiresNewMessageId": True}
        inbox = self.client.inbox(session_id)
        enqueued = {
            item.get("id")
            for item in (inbox.get("data", []) if isinstance(inbox, dict) else [])
            if isinstance(item, dict)
        }
        if message_id in enqueued:
            report["claimState"] = "ENQUEUED"  # durably admitted, not delivered
            return report
        scan = self._scan_messages(self._fetch_messages(session_id), message_id)
        if not scan["found"]:
            return report  # provably never admitted — a NEW id may resubmit
        if scan["assistantText"]:
            report["claimState"] = "CLAIMED_COMPLETE"
            report["assistantText"] = scan["assistantText"]
        else:
            report["claimState"] = "CLAIMED_PENDING"  # delivered, turn running
        report["resubmitRequiresNewMessageId"] = False
        return report

    def recover(self) -> dict:
        """Product-restart reconciliation: read state, never re-prompt."""
        state = self.store.load()
        session_id = state.get("session_ref")
        if not session_id:
            return {"state": "CLEAN"}
        try:
            self.client.session(session_id)
        except TransportError as exc:
            # Reads are non-mutating; unreachable service is "not up yet",
            # never "data lost" — S0 persistence is the base.
            return {"state": "UNREACHABLE", "code": exc.code, "sessionRef": session_id}
        turn = self.store.unresolved_turn()
        if turn is None:
            return {"state": "IDLE", "sessionRef": session_id}
        claim = self.reconcile(session_id, turn["messageId"])
        merged = dict(turn)
        merged["state"] = claim["claimState"]
        self.store.record_turn(merged)
        return {"state": claim["claimState"], "sessionRef": session_id,
                "turn": merged, "claim": claim}


def _quote(session_id: str) -> str:
    from urllib.parse import quote
    return quote(session_id, safe="")


# ------------------------------------------- legal_entry session.create wiring

def service_client(config: dict) -> Client:
    """Build the OpenCode client from registration file or env credentials."""
    registration = config.get("opencode_registration")
    if registration:
        data = json.loads(Path(registration).read_text(encoding="utf-8-sig"))
        token = base64.b64encode(
            ("opencode:" + data["password"]).encode()).decode("ascii")
        return Client(data["url"], headers={"Authorization": "Basic " + token},
                      timeout=float(config.get("opencode_timeout", 30)))
    if config.get("opencode_url"):
        username = os.environ.get("JUSBENCH_AGENT_USERNAME")
        password = os.environ.get("JUSBENCH_AGENT_PASSWORD")
        if not (username and password):
            raise NotConnected("service_authentication_required")
        token = base64.b64encode(
            (username + ":" + password).encode()).decode("ascii")
        return Client(config["opencode_url"],
                      headers={"Authorization": "Basic " + token},
                      timeout=float(config.get("opencode_timeout", 30)))
    raise NotConnected("opencode_service_not_configured")


def create_public_session(payload: dict, config: dict, *,
                          policies: list | None = None) -> dict:
    """legal_entry session.create handler: F-9 guard first, then transport."""
    guards = policies if policies is not None else load_product_policies(
        config.get("opencode_policies"))
    conflicts = policy_conflicts((payload or {}).get("permissions"), guards)
    if conflicts:
        raise SessionRejected(
            "session_allow_conflicts_policy_deny:" + json.dumps(
                conflicts[0]["rule"], ensure_ascii=False, sort_keys=True)
        )
    client = service_client(config)
    info = client.request("GET", "/api/info")
    value = info.get("data", info) if isinstance(info, dict) else {}
    version = value.get("version") if isinstance(value, dict) else None
    if version != "2.0.28" and not (
            isinstance(version, str) and version.startswith(DEV_VERSION_PREFIX)):
        raise TransportError("runtime_version_mismatch")
    return client.create(payload)
