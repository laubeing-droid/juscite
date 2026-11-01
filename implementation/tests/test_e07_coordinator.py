"""E07 product coordinator + goal-ledger bridge tests (W1-U01). All synthetic.

Covers the five integration points of harness docs/e07-goal-contract.md §5:
preflight (get/list/read_basis, STALE→human), mechanical pause (closed
boundary set + mandatory trigger value), explicit-only resume, plan
re-decision, and transport/recovery metadata (never goal content); plus the
mutation discipline (no blind retry; uncertain → reconcile inbox/history),
the F-9 fail-closed session-creation guard (T18), and the legal_entry
harness.* dispatch through public_entry --goal-json (subprocess seam faked —
no harness checkout is needed or touched here).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import e07_coordinator as ec
import legal_entry as le
from e07_coordinator import (
    BridgeGoalLedger, Coordinator, CoordinatorBlocked, RecoveryStore,
    load_product_policies, pause_banner, policy_conflicts,
)
from legal_entry import HarnessCommandError, NotConnected, SessionRejected
from opencode_http import TransportError

SCOPE = {"kind": "matter", "matterId": "m-e07-synth"}


def open_pause(idx=1, boundary="BUDGET_LIMIT", trigger="500.00"):
    return {"goalRef": "goal/m-e07-synth/g1/1/abc", "pauseIdx": idx,
            "boundary": boundary, "triggerValue": trigger, "detail": "",
            "state": "paused", "pausedBy": "product-coordinator",
            "pausedAt": "2026-10-15T00:00:00Z", "resumedBy": None, "resumedAt": None}


class FakeLedger:
    """Scripted harness responses + a call journal (goal content never local)."""

    def __init__(self, **state):
        self.state = state
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, json.loads(json.dumps(params))))
        if method == "harness.list_goals":
            items = self.state.get("items", [{"goalId": "g1", "headRevision": 1,
                                              "status": "active"}])
            return {"items": items}
        if method == "harness.get_goal":
            return {"goalRef": "goal/m-e07-synth/g1/1/abc", "goal": {"goalId": "g1"},
                    "status": self.state.get("status", "active"), "headRevision": 1,
                    "openPause": self.state.get("openPause"),
                    "planDecisions": [], "taskAdoptions": [], "pauseEntries": []}
        if method == "harness.read_goal_basis":
            return {"status": self.state.get("basis", "CURRENT"),
                    "savedBasis": {}, "currentBasis": {}}
        if method == "harness.list_goal_pauses":
            return {"items": self.state.get("pauseEntries", []),
                    "openPause": self.state.get("openPause")}
        return self.state.get("returns", {}).get(method, {"ok": True})


class FakeClient:
    def __init__(self, *, prompt_error=None, messages=None, inbox=None,
                 session_error=None, complete_turn=True, pages=None):
        self.prompt_error = prompt_error
        self.history = list(messages or [])
        self.pages = [list(p) for p in pages] if pages else None
        self.inbox_payload = inbox if inbox is not None else {"data": []}
        self.session_error = session_error
        self.complete_turn = complete_turn
        self.prompts = []
        self.paths = []

    def request(self, method, path):
        self.paths.append(path)
        base, _, query = path.partition("?")
        if base.endswith("/message"):
            # Live API contract: order=asc pinned; cursor pages are opaque and
            # never combined with order. Cursor value = next page index.
            pages = self.pages if self.pages else [self.history]
            index = 0
            if "cursor=" in query:
                index = int(query.rsplit("cursor=", 1)[1])
            listing = {"data": list(pages[index])}
            if index + 1 < len(pages):
                listing["cursor"] = {"next": str(index + 1)}
            return listing
        if path == "/api/info":
            return {"version": "2.0.28"}
        raise AssertionError("unexpected path " + path)

    def create(self, payload):
        self.created = payload
        return {"data": {"id": "ses_synth_1"}}

    def session(self, sid):
        if self.session_error:
            raise self.session_error
        return {"data": {"id": sid}}

    def prompt(self, sid, request):
        self.prompts.append((sid, dict(request)))
        if self.prompt_error:
            raise self.prompt_error
        self.history = self.history + [
            {"id": request["id"], "type": "user", "text": request["text"]}]
        if self.complete_turn:
            self.history = self.history + [
                {"id": "msg_a_1", "type": "assistant",
                 "content": [{"type": "text", "text": "合成回答"}]},
                {"id": "msg_i_1", "type": "idle"}]
        return {"data": {"id": request["id"]}}

    def inbox(self, sid):
        return self.inbox_payload


def make_coordinator(ledger_state=None, **client_kwargs):
    ledger = FakeLedger(**(ledger_state or {}))
    client = FakeClient(**client_kwargs)
    store = RecoveryStore(Path(tempfile.mkdtemp()) / "recovery.json")
    return Coordinator(ledger, client, store, turn_timeout=0.3, poll_interval=0.01), ledger, client


class PauseBannerTests(unittest.TestCase):
    def test_renders_paused_reason_and_explicit_resume(self):
        banner = pause_banner(open_pause())
        self.assertTrue(banner["paused"])
        self.assertEqual(banner["boundary"], "BUDGET_LIMIT")
        self.assertEqual(banner["triggerValue"], "500.00")
        self.assertIn("已暂停", banner["display"])
        self.assertIn("一键续跑", banner["display"])
        self.assertEqual(banner["resume"]["method"], "harness.resume_goal")
        self.assertTrue(banner["resume"]["explicit"])

    def test_no_open_pause_renders_running(self):
        self.assertEqual(pause_banner(None), {"paused": False})


class PreflightTests(unittest.TestCase):
    def test_no_goal_and_ambiguous_refuse_to_pick(self):
        co, ledger, _ = make_coordinator({"items": []})
        self.assertEqual(co.preflight(SCOPE)["decision"], "NO_GOAL")
        co2, ledger2, _ = make_coordinator({"items": [
            {"goalId": "g1", "headRevision": 1, "status": "active"},
            {"goalId": "g2", "headRevision": 1, "status": "active"}]})
        self.assertEqual(co2.preflight(SCOPE)["decision"], "AMBIGUOUS")

    def test_open_pause_blocks_advance_and_feeds_banner(self):
        co, _, client = make_coordinator({"openPause": open_pause()})
        with self.assertRaises(CoordinatorBlocked) as ctx:
            co.advance_turn(SCOPE, "ses_synth_1", "合成推进")
        self.assertEqual(ctx.exception.code, "preflight_paused")
        self.assertTrue(ctx.exception.detail["banner"]["paused"])
        self.assertEqual(client.prompts, [])

    def test_revoked_goal_blocks_advance(self):
        co, _, client = make_coordinator({"status": "revoked"})
        with self.assertRaises(CoordinatorBlocked) as ctx:
            co.advance_turn(SCOPE, "ses_synth_1", "x")
        self.assertEqual(ctx.exception.code, "preflight_revoked")
        self.assertEqual(client.prompts, [])

    def test_stale_basis_returns_to_human(self):
        co, _, client = make_coordinator({"basis": "STALE_REQUIRES_REVIEW"})
        with self.assertRaises(CoordinatorBlocked) as ctx:
            co.advance_turn(SCOPE, "ses_synth_1", "x", task_id="t1")
        self.assertEqual(ctx.exception.code, "preflight_stale_return_to_human")
        self.assertEqual(ctx.exception.detail["basis"]["status"], "STALE_REQUIRES_REVIEW")
        self.assertEqual(client.prompts, [])

    def test_ready_advances_exactly_one_turn_and_persists_metadata(self):
        co, _, client = make_coordinator()
        result = co.advance_turn(SCOPE, "ses_synth_1", "合成推进", task_id="t1")
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual(len(client.prompts), 1)
        sid, request = client.prompts[0]
        self.assertEqual(sid, "ses_synth_1")
        self.assertTrue(request["id"].startswith("msg_"))
        state = co.store.load()
        self.assertEqual(state["session_ref"], "ses_synth_1")
        self.assertEqual(state["turns"][-1]["state"], "COMPLETE")
        self.assertTrue(state["turns"][-1]["messageId"].startswith("msg_e07_"))
        # transport/recovery metadata only — refs and ids, never goal content
        dumped = json.dumps(state)
        for field in ("confirmedScope", "hardConstraints", "preferences", "unitTiming"):
            self.assertNotIn(field, dumped)

    def test_explicit_message_id_must_be_msg_prefixed(self):
        co, _, _ = make_coordinator()
        with self.assertRaises(ValueError):
            co.advance_turn(SCOPE, "ses_synth_1", "x", message_id="bad-1")


class MutationDisciplineTests(unittest.TestCase):
    def test_uncertain_prompt_never_retried_and_reconciles(self):
        error = TransportError("transport_failure", uncertain=True)
        co, _, client = make_coordinator(prompt_error=error)
        result = co.advance_turn(SCOPE, "ses_synth_1", "合成推进")
        self.assertEqual(len(client.prompts), 1)  # exactly one attempt
        self.assertEqual(result["state"], "UNKNOWN_RECONCILED")
        claim = result["claim"]
        # the write-ahead id is in neither inbox nor history → never admitted
        self.assertEqual(claim["claimState"], "NOT_ADMITTED")
        self.assertTrue(claim["resubmitRequiresNewMessageId"])
        self.assertEqual(co.store.load()["turns"][-1]["state"], "NOT_ADMITTED")

    def test_new_turn_after_not_admitted_uses_new_message_id(self):
        error = TransportError("transport_failure", uncertain=True)
        co, _, client = make_coordinator(prompt_error=error)
        co.advance_turn(SCOPE, "ses_synth_1", "合成推进")
        first_id = client.prompts[0][1]["id"]
        # reconciliation proved non-admission: a NEW explicit turn (new id) is
        # lawful — a same-id resubmit would be the forbidden blind retry.
        co.client.prompt_error = None
        result = co.advance_turn(SCOPE, "ses_synth_1", "重发合成推进")
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual(len(client.prompts), 2)
        self.assertNotEqual(client.prompts[1][1]["id"], first_id)

    def test_busy_previous_turn_refuses_new_prompt(self):
        co, _, client = make_coordinator(complete_turn=False)
        first = co.advance_turn(SCOPE, "ses_synth_1", "合成推进")
        self.assertEqual(first["state"], "PENDING")
        with self.assertRaises(CoordinatorBlocked) as ctx:
            co.advance_turn(SCOPE, "ses_synth_1", "第二轮")
        self.assertEqual(ctx.exception.code, "unresolved_previous_turn")
        self.assertEqual(len(client.prompts), 1)

    def test_pending_turn_times_out_honestly(self):
        co, _, client = make_coordinator(complete_turn=False)
        result = co.advance_turn(SCOPE, "ses_synth_1", "合成推进")
        self.assertEqual(result["state"], "PENDING")
        self.assertEqual(co.store.load()["turns"][-1]["state"], "PENDING")

    def test_deterministic_transport_failure_reraises(self):
        co, _, client = make_coordinator(
            prompt_error=TransportError("http_400", uncertain=False))
        with self.assertRaises(TransportError):
            co.advance_turn(SCOPE, "ses_synth_1", "x")
        self.assertEqual(co.store.load()["turns"][-1]["state"], "FAILED_TRANSPORT")

    def test_reconcile_id_in_inbox_is_durable_admission(self):
        co, _, _ = make_coordinator(inbox={"data": [
            {"id": "msg_e07_9", "type": "user", "delivery": "queue"}]})
        claim = co.reconcile("ses_synth_1", "msg_e07_9")
        self.assertEqual(claim["claimState"], "ENQUEUED")
        self.assertEqual(claim["messageId"], "msg_e07_9")

    def test_reconcile_delivered_without_assistant_is_pending(self):
        co, _, _ = make_coordinator(
            messages=[{"id": "msg_e07_1", "type": "user", "text": "q"}])
        claim = co.reconcile("ses_synth_1", "msg_e07_1")
        self.assertEqual(claim["claimState"], "CLAIMED_PENDING")
        self.assertFalse(claim["resubmitRequiresNewMessageId"])

    def test_reconcile_absent_id_is_not_admitted(self):
        co, _, _ = make_coordinator(
            messages=[{"id": "msg_other", "type": "user", "text": "q"}])
        claim = co.reconcile("ses_synth_1", "msg_e07_1")
        self.assertEqual(claim["claimState"], "NOT_ADMITTED")
        self.assertTrue(claim["resubmitRequiresNewMessageId"])

    def test_message_fetch_pins_asc_order(self):
        # Live-API default is newest-first (v2 message.ts SessionMessagesQuery);
        # an anchor-relative scan must pin order=asc (live-recon catch, W1-U06).
        co, _, _ = make_coordinator(
            messages=[{"id": "msg_e07_1", "type": "user", "text": "q"}])
        co.reconcile("ses_synth_1", "msg_e07_1")
        message_paths = [p for p in co.client.paths if "/message" in p]
        self.assertTrue(message_paths)
        self.assertTrue(all("order=asc" in p and "cursor=" not in p
                            for p in message_paths), message_paths)

    def test_message_scan_follows_cursor_pages(self):
        # 助答与 idle 标记落在第二页：不分页读取会把已完成轮次误判 PENDING。
        co, _, _ = make_coordinator(pages=[
            [{"id": "msg_e07_1", "type": "user", "text": "q"}],
            [{"id": "msg_a_1", "type": "assistant",
              "content": [{"type": "text", "text": "合成回答"}]},
             {"id": "msg_i_1", "type": "idle"}]])
        claim = co.reconcile("ses_synth_1", "msg_e07_1")
        self.assertEqual(claim["claimState"], "CLAIMED_COMPLETE")
        self.assertTrue(claim["assistantText"])


class RecoveryTests(unittest.TestCase):
    def test_recovery_reads_back_after_restart_no_reprompt(self):
        co, _, client = make_coordinator()
        history = [{"id": "msg_e07_1", "type": "user", "text": "q"},
                   {"id": "msg_a_1", "type": "assistant",
                    "content": [{"type": "text", "text": "合成回答"}]},
                   {"id": "msg_i_1", "type": "idle"}]
        client.history = history
        co.store.record_turn({"messageId": "msg_e07_1", "sessionRef": "ses_synth_1",
                              "state": "SUBMITTED_UNKNOWN"})
        report = co.recover()
        self.assertEqual(report["state"], "CLAIMED_COMPLETE")
        self.assertEqual(client.prompts, [])  # readback only — S0 persistence base

    def test_recovery_unreachable_is_not_data_loss(self):
        co, _, _ = make_coordinator(session_error=TransportError(
            "transport_failure", uncertain=False))
        co.store.record_turn({"messageId": "msg_e07_1", "sessionRef": "ses_synth_1",
                              "state": "PENDING"})
        report = co.recover()
        self.assertEqual(report["state"], "UNREACHABLE")
        self.assertEqual(report["code"], "transport_failure")

    def test_recovery_clean_without_metadata(self):
        co, _, _ = make_coordinator()
        self.assertEqual(co.recover()["state"], "CLEAN")


class PauseResumeTests(unittest.TestCase):
    def test_boundary_closed_set_and_trigger_required_before_ledger(self):
        co, ledger, _ = make_coordinator()
        with self.assertRaises(ValueError):
            co.pause_goal(SCOPE, "g1", "SHELL_ESCAPE", "1")
        with self.assertRaises(ValueError):
            co.pause_goal(SCOPE, "g1", "BUDGET_LIMIT", "")
        self.assertEqual(ledger.calls, [])
        receipt = co.pause_goal(SCOPE, "g1", "BUDGET_LIMIT", "500.00", detail="合成")
        method, params = ledger.calls[-1]
        self.assertEqual(method, "harness.pause_goal")
        self.assertEqual(params["pause"]["boundary"], "BUDGET_LIMIT")
        self.assertEqual(params["pause"]["triggerValue"], "500.00")
        self.assertEqual(params["pause"]["detail"], "合成")
        self.assertTrue(params["key"]["requestId"])

    def test_pause_request_id_stable_per_episode(self):
        co, ledger, _ = make_coordinator()
        co.pause_goal(SCOPE, "g1", "TIME_LIMIT", "3600")
        first = ledger.calls[-1][1]["key"]["requestId"]
        co.pause_goal(SCOPE, "g1", "TIME_LIMIT", "3600")  # same episode: replay-safe
        self.assertEqual(ledger.calls[-1][1]["key"]["requestId"], first)
        # a new episode (pause entry landed) gets a fresh CommandKey
        co.ledger.state["pauseEntries"] = [{"pauseIdx": 1}]
        co.pause_goal(SCOPE, "g1", "TIME_LIMIT", "3600")
        self.assertNotEqual(ledger.calls[-1][1]["key"]["requestId"], first)

    def test_resume_without_index_resolves_open_pause(self):
        co, ledger, _ = make_coordinator({"openPause": open_pause(idx=2)})
        co.user_resume_goal(SCOPE, "g1")
        method, params = ledger.calls[-1]
        self.assertEqual(method, "harness.resume_goal")
        self.assertEqual(params["resume"], {"goalId": "g1", "pauseIdx": 2})
        # nothing paused and no index → clean refusal, no ledger write
        co2, ledger2, _ = make_coordinator()
        with self.assertRaises(CoordinatorBlocked):
            co2.user_resume_goal(SCOPE, "g1")
        self.assertFalse(any(m == "harness.resume_goal" for m, _ in ledger2.calls))

    def test_resume_is_explicit_and_only_channel(self):
        co, ledger, _ = make_coordinator({"openPause": open_pause()})
        co.preflight(SCOPE)          # paused: reads only
        co.recover()                 # recovery: reads only
        self.assertFalse(any(m == "harness.resume_goal" for m, _ in ledger.calls))
        receipt = co.user_resume_goal(SCOPE, "g1", pause_idx=1)
        method, params = ledger.calls[-1]
        self.assertEqual(method, "harness.resume_goal")
        self.assertEqual(params["resume"], {"goalId": "g1", "pauseIdx": 1})
        # after resume the ledger shows no open pause → next preflight is READY
        co.ledger.state["openPause"] = None
        self.assertEqual(co.preflight(SCOPE)["decision"], "READY")

    def test_decide_goal_plan_carries_scope_change(self):
        co, ledger, _ = make_coordinator()
        co.decide_goal_plan(SCOPE, {"goalId": "g1", "planId": "plan-2",
                                    "planRevision": "2", "decision": "approved"})
        method, params = ledger.calls[-1]
        self.assertEqual(method, "harness.decide_goal_plan")
        self.assertEqual(params["decision"]["planRevision"], "2")


class F9SessionCreationTests(unittest.TestCase):
    POLICIES = [{"action": "tool.use", "resource": "shell:*", "effect": "deny"},
                {"action": "tool.use", "resource": "webfetch:*", "effect": "deny"}]

    def test_allow_rule_conflicting_policy_deny_rejected(self):
        co, _, client = make_coordinator()
        payload = {"title": "合成会话", "permissions": [
            {"action": "shell", "resource": "*", "effect": "allow"}]}
        with self.assertRaises(SessionRejected):
            co.create_session(payload, policies=self.POLICIES)
        self.assertFalse(hasattr(client, "created"))

    def test_wildcard_allow_rejected_and_disjoint_rule_allowed(self):
        payload_bad = {"permissions": [{"action": "*", "resource": "*", "effect": "allow"}]}
        self.assertEqual(len(policy_conflicts(payload_bad["permissions"], self.POLICIES)), 2)
        payload_ok = {"permissions": [{"action": "read", "resource": "*", "effect": "allow"}]}
        self.assertEqual(policy_conflicts(payload_ok["permissions"], self.POLICIES), [])

    def test_deny_rules_and_missing_permissions_pass_guard(self):
        rules = [{"action": "shell", "resource": "*", "effect": "deny"}]
        self.assertEqual(policy_conflicts(rules, self.POLICIES), [])
        self.assertEqual(policy_conflicts([], self.POLICIES), [])
        self.assertEqual(policy_conflicts(None, self.POLICIES), [])

    def test_create_session_passes_after_guard(self):
        co, _, client = make_coordinator()
        payload = {"title": "合成会话", "permissions": [
            {"action": "read", "resource": "*", "effect": "allow"}]}
        result = co.create_session(payload, policies=self.POLICIES)
        self.assertEqual(client.created, payload)

    def test_load_product_policies_from_synthetic_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opencode.json"
            path.write_text(json.dumps(
                {"experimental": {"policies": self.POLICIES}}), encoding="utf-8")
            self.assertEqual(load_product_policies(path), self.POLICIES)
            self.assertEqual(load_product_policies(Path(tmp) / "missing.json"), [])


class LegalEntryGoalDispatchTests(unittest.TestCase):
    CONFIG = {"harness_public_entry": "X:/harness/public_entry.py",
              "harness_target": "opencode",
              "harness_state_root": "S:/synthetic-state",
              "harness_timeout": 5}

    def fake_execute(self, output=None, returncode=0, error=None, capture=None):
        def _run(argv, env, timeout):
            if capture is not None:
                capture.append({"argv": list(argv), "env": dict(env),
                                "timeout": timeout,
                                "payload": json.loads(Path(argv[argv.index("--goal-json") + 1]).read_text(encoding="utf-8"))})
            if error:
                raise error
            return SimpleNamespace(returncode=returncode, stdout=output)
        return _run

    def test_goal_json_shape_target_flag_and_env(self):
        captured = []
        output = json.dumps({"surface": "goal", "method": "harness.get_goal",
                             "result": {"status": "active"}})
        original = le._execute
        le._execute = self.fake_execute(output, capture=captured)
        try:
            result = le.call("harness.get_goal",
                             {"scope": SCOPE, "goal_id": "g1"}, dict(self.CONFIG))
        finally:
            le._execute = original
        self.assertEqual(result, {"status": "active"})
        self.assertEqual(len(captured), 1)
        run = captured[0]
        self.assertEqual(run["payload"],
                         {"method": "harness.get_goal",
                          "params": {"scope": SCOPE, "goal_id": "g1"}})
        self.assertIn("--target", run["argv"])
        self.assertEqual(run["argv"][run["argv"].index("--target") + 1], "opencode")
        self.assertEqual(run["env"]["LH_LEGAL_STATE_ROOT"], "S:/synthetic-state")
        goal_file = Path(run["argv"][run["argv"].index("--goal-json") + 1])
        self.assertFalse(goal_file.exists())  # temp file cleaned up

    def test_typed_business_failure_raises_harness_command_error(self):
        output = json.dumps({"status": "FAIL", "error": "goal_already_paused:1"})
        original = le._execute
        le._execute = self.fake_execute(output, returncode=1)
        try:
            with self.assertRaises(HarnessCommandError) as ctx:
                le.call("harness.pause_goal", {"scope": SCOPE}, dict(self.CONFIG))
        finally:
            le._execute = original
        self.assertEqual(str(ctx.exception), "goal_already_paused:1")

    def test_stderr_and_invalid_stdout_never_surfaced(self):
        original = le._execute
        le._execute = self.fake_execute("not json at all", returncode=0)
        try:
            with self.assertRaises(HarnessCommandError) as ctx:
                le.call("harness.list_goals", {"scope": SCOPE}, dict(self.CONFIG))
        finally:
            le._execute = original
        self.assertEqual(str(ctx.exception), "harness_entry_protocol_invalid")

    def test_timeout_is_typed_unknown(self):
        original = le._execute
        le._execute = self.fake_execute(error=subprocess.TimeoutExpired(cmd="x", timeout=5))
        try:
            with self.assertRaises(HarnessCommandError) as ctx:
                le.call("harness.save_goal", {"scope": SCOPE}, dict(self.CONFIG))
        finally:
            le._execute = original
        self.assertEqual(str(ctx.exception), "harness_entry_timeout")

    def test_whitelist_closed_and_config_fail_closed(self):
        with self.assertRaises(NotConnected):
            le.call("harness.save_fact", {}, dict(self.CONFIG))  # not E07 surface
        with self.assertRaises(NotConnected):
            le.call("harness.get_goal", {"scope": SCOPE}, {})    # no entry configured
        with self.assertRaises(NotConnected):
            le.call("harness.get_goal", {"scope": SCOPE},
                    {"harness_public_entry": "X:/harness/public_entry.py"})


class SessionCreateEntryTests(unittest.TestCase):
    def test_entry_applies_f9_guard_before_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / "service-local.json"
            # dead port: nothing listens on 127.0.0.1:1 — no live service touched
            reg.write_text(json.dumps(
                {"url": "http://127.0.0.1:1", "password": "synthetic"}), encoding="utf-8")
            policies_path = Path(tmp) / "opencode.json"
            policies_path.write_text(json.dumps(
                {"experimental": {"policies": [
                    {"action": "tool.use", "resource": "shell:*", "effect": "deny"}]}}),
                encoding="utf-8")
            config = {"opencode_registration": str(reg),
                      "opencode_policies": str(policies_path)}
            bad = {"permissions": [{"action": "shell", "resource": "*",
                                    "effect": "allow"}]}
            with self.assertRaises(SessionRejected):
                le.call("session.create", bad, config)
            # no live service needed for the rejection path: fail-closed first
            good = {"permissions": [{"action": "read", "resource": "*",
                                     "effect": "allow"}]}
            with self.assertRaises(TransportError):
                le.call("session.create", good, config)  # guard passed, transport fails

    def test_service_client_fails_closed_without_config(self):
        with self.assertRaises(NotConnected):
            ec.service_client({})
        with tempfile.TemporaryDirectory() as tmp:
            reg = Path(tmp) / "service-local.json"
            reg.write_text(json.dumps(
                {"url": "http://127.0.0.1:43127", "password": "synthetic"}), encoding="utf-8")
            client = ec.service_client({"opencode_registration": str(reg)})
            self.assertEqual(client.url, "http://127.0.0.1:43127")


class BridgeLedgerTests(unittest.TestCase):
    def test_bridge_ledger_delegates_to_legal_entry(self):
        captured = []
        output = json.dumps({"surface": "goal", "method": "harness.list_goals",
                             "result": {"items": []}})
        original = le._execute
        le._execute = self.fake_execute_shared(output, captured)
        try:
            ledger = BridgeGoalLedger({
                "harness_public_entry": "X:/harness/public_entry.py",
                "harness_target": "opencode"})
            result = ledger.call("harness.list_goals", {"scope": SCOPE})
        finally:
            le._execute = original
        self.assertEqual(result, {"items": []})
        self.assertEqual(captured[0]["payload"]["method"], "harness.list_goals")

    @staticmethod
    def fake_execute_shared(output, captured):
        def _run(argv, env, timeout):
            captured.append({"payload": json.loads(
                Path(argv[argv.index("--goal-json") + 1]).read_text(encoding="utf-8"))})
            return SimpleNamespace(returncode=0, stdout=output)
        return _run


if __name__ == "__main__":
    unittest.main()
