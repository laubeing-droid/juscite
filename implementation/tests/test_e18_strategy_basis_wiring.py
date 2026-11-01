# -*- coding: utf-8 -*-
"""W2b-U52 / E18 acceptance: customer-goal & strategy basis bridge.

07 E18 (harness+jc; deps E05/E15/E21) + 08§3 five-scenario row
「goal-only策略变更」:
* strategy rows pin goal version refs (T16 goal account = the single
  customer-goal authority; forged owner≠harness / digest drift refused);
* three gates (fact/law/strategy) judged separately — a request carrying
  a combined verdict or total-score field is refused by name;
* hard-constraint violations force overall=fail and are never offset by
  passing gates;
* goal-only change (G1/G2 revised, fact/law same version) → the strategy
  gate reads STALE while the fact/law gates stay FRESH (three-way split,
  never merged);
* the evaluation receipt is JC's (strategyBasisRef owner=jc via
  jc.strategy_evaluate) and the harness transcribes it as jcEvaluationRef.

All materials below are synthetic engineering fixtures. The bridge
consumes the pinned harness w2b-u52 worktree (superset of the w2b-u51
chain head, schema v22) through the closed public_entry provider dispatch
(--strategybasis-json envelope) and the pinned JC w2b-u52 worktree (a
superset of the w2b-u27 E19 chain head) through the P01 JCClient surface
— no second authority anywhere.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry

HARNESS_REPO = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u52")
JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w2b-u52")

# Runtime face pinning (W2a-U16 discipline): the whole pytest process must
# resolve compiler_core to THIS wave's JC worktree — w2b-u52 is a superset
# of the w2b-u27 (E19) and w2b-u19 (E21) chain heads, so this module pins
# first (alphabetical collection) and the later purges by those modules
# re-pin to subsets whose faces this superset fully covers.
if (JC_REPO / "compiler_core" / "strategy_basis.py").is_file():
    sys.path.insert(0, str(JC_REPO))
    for _name in [m for m in list(sys.modules)
                  if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[_name]

_MATTER = "m-e18-wiring"


# create_local_client 需要至少一个规则根（JC 不自带规则库、绝不发明法
# 律能力）——策略评估面语义上不消费规则，但客户端构造要求非空，给最小
# 合成包（无法律效力，仅工程验证）。
RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [{
        "source_id": "acceptance-statute", "jurisdiction": "TEST",
        "authority_tier": "official_first_party",
        "issuer": "Acceptance Test Authority", "title": "acceptance-statute",
        "publication_time": "2020-01-01T00:00:00Z",
        "effective_from": "2020-01-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                    "page": None, "span_start": None, "span_end": None},
        "content": ("SYNTHETIC acceptance rule text for engineering "
                    "verification only; no legal effect."),
        "structure_sections": ["ART-1"],
    }],
    "rules": [
        {"rule_id": "acc-base", "jurisdiction": "TEST",
         "governing_law": "acceptance-statute", "source_id": "acceptance-statute",
         "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.contract", "required": True}],
         "conclusion": {"value": "applies"},
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}


_ACTIVE_TMPDIRS = []


def _jc_config(tmp_path=None):
    if not (JC_REPO / "compiler_core" / "strategy_basis.py").is_file():
        raise AssertionError(
            f"pinned JC w2b-u52 worktree missing at {JC_REPO}; the E18 "
            "strategy bridge cannot be verified")
    holder = tempfile.TemporaryDirectory()
    _ACTIVE_TMPDIRS.append(holder)  # keep alive for the whole test process
    tmp_path = Path(holder.name)
    rules = tmp_path / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(tmp_path / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }


def _harness_config(state_root: Path):
    if not (HARNESS_REPO / "tools/workflow-tools/harness/public_entry.py"
            ).is_file():
        raise AssertionError(
            f"pinned harness w2b-u52 worktree missing at {HARNESS_REPO}; "
            "the E18 strategy bridge cannot be verified")
    registration = state_root.parent / "service-local.json"
    registration.write_text(json.dumps(
        {"url": "http://127.0.0.1:1", "password": "synthetic-wiring"}),
        encoding="utf-8")
    return {
        "harness_public_entry":
            str(HARNESS_REPO / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(state_root),
        "harness_service_registration": str(registration),
        "harness_timeout": 120,
    }


def _run_cli(method, args, config):
    with tempfile.TemporaryDirectory() as tmp:
        request = Path(tmp) / "request.json"
        conf = Path(tmp) / "config.json"
        request.write_text(json.dumps({"method": method, "args": args},
                                      ensure_ascii=False), encoding="utf-8")
        conf.write_text(json.dumps(config, ensure_ascii=False),
                        encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(HERE / "python" / "legal_entry.py"),
             "--request-json", str(request), "--config", str(conf)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


def _key(request_id: str, target_id: str | None = None,
         expected_revision: int | None = None) -> dict:
    return {"requestId": request_id, "targetId": target_id,
            "expectedRevision": expected_revision, "inputRefs": []}


def _goal_payload(matter: str, goal_id: str, revision: int = 1,
                  supersedes: int | None = None) -> dict:
    return {
        "schemaVersion": "1.0.0-draft", "matterId": matter, "goalId": goal_id,
        "revision": revision,
        "confirmedScope": "E18 桥合成：货款 85000 元追收",
        "hardConstraints": [
            {"id": "hc-2", "kind": "no_installment", "value": "true",
             "description": "不接受分期"},
        ],
        "preferences": [{"id": "pf-1", "kind": "relationship",
                         "description": "保留供货关系"}],
        "unitTiming": {"unit": "CNY", "asOf": "2026-10-17"},
        "sourceDecisionRef": None,
        "supersedesRevision": supersedes,
    }


def _gates(strategy_verdict="pass"):
    return {
        "fact": {"verdict": "pass", "basisRefs": ["fact-pins:f-1@v1（合成）"]},
        "law": {"verdict": "pass",
                "basisRefs": ["law-check-snapshot:lcs-1（合成）"]},
        "strategy": {"verdict": strategy_verdict,
                     "basisRefs": ["goal:g-1@1", "goal:g-2@1"]},
    }


class TestMethodGroupsFrozen(unittest.TestCase):
    """现组零动＋新组封闭枚举。"""

    def test_goal_group_untouched(self):
        self.assertEqual(legal_entry.HARNESS_GOAL_METHODS, frozenset({
            "harness.save_goal", "harness.revoke_goal", "harness.get_goal",
            "harness.list_goals", "harness.decide_goal_plan",
            "harness.adopt_goal_task", "harness.pause_goal",
            "harness.resume_goal", "harness.list_goal_pauses",
            "harness.read_goal_basis",
        }))

    def test_strategy_group_frozen(self):
        self.assertEqual(legal_entry.HARNESS_STRATEGY_METHODS, frozenset({
            "harness.strategy_basis_register", "harness.strategy_basis_evaluate",
            "harness.strategy_basis_read", "harness.strategy_basis_list",
            "harness.strategy_evaluation_read",
            "harness.strategy_evaluation_list",
        }))
        self.assertEqual(legal_entry.STRATEGY_BASIS_JC_METHODS,
                         frozenset({"jc.strategy_evaluate"}))

    def test_unknown_strategy_method_not_connected(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("harness.strategy_basis_decide", {}, {})
        self.assertIn("method_not_connected", str(ctx.exception))


class TestJcStrategyEvaluateFace(unittest.TestCase):
    """jc.strategy_evaluate 消费口（CLI 全链：exit 0/3/4 分义）。"""

    def test_evaluate_seals_three_gates_and_jc_ref(self):
        code, out = _run_cli(
            "jc.strategy_evaluate",
            {"matterId": "m-e18", "request": {
                "strategyId": "st-1", "strategyRevision": 1,
                "gates": _gates(), "declaredConstraints": ["hc-2"],
                "constraintResults": [{"constraintId": "hc-2",
                                       "satisfied": True}]}},
            _jc_config())
        self.assertEqual(code, 0, out)
        self.assertEqual(out["status"], "OWNER_RESPONSE")
        result = out["result"]
        self.assertEqual(result["overall"], "pass")
        self.assertEqual(result["strategyBasisRef"]["owner"], "jc")
        self.assertTrue(result["strategyBasisRef"]["digest"].startswith("sha256:"))

    def test_combined_field_refused_exit4(self):
        code, out = _run_cli(
            "jc.strategy_evaluate",
            {"matterId": "m-e18", "request": {
                "strategyId": "st-1", "strategyRevision": 1,
                "gates": _gates(), "declaredConstraints": ["hc-2"],
                "constraintResults": [{"constraintId": "hc-2",
                                       "satisfied": True}],
                "score": 0.9}},
            _jc_config())
        self.assertEqual(code, 4, out)
        self.assertEqual(out["status"], "JC_FAILURE")
        self.assertIn("strategy_combined_verdict_refused", out["code"])

    def test_missing_gate_refused_exit4(self):
        gates = _gates()
        gates.pop("strategy")
        code, out = _run_cli(
            "jc.strategy_evaluate",
            {"matterId": "m-e18", "request": {
                "strategyId": "st-1", "strategyRevision": 1,
                "gates": gates, "declaredConstraints": [],
                "constraintResults": []}},
            _jc_config())
        self.assertEqual(code, 4, out)
        self.assertIn("strategy_gate_missing", out["code"])

    def test_unconfigured_fails_closed_exit3(self):
        code, out = _run_cli("jc.strategy_evaluate", {"request": {}}, {})
        self.assertEqual(code, 3, out)
        self.assertEqual(out["status"], "NOT_CONNECTED")


class TestHarnessStrategyBridge(unittest.TestCase):
    """产品桥全链：goal 账钉定→策略行→JC 回执转录→goal-only 三分判。"""

    @classmethod
    def setUpClass(cls):
        cls.holder = tempfile.TemporaryDirectory(prefix="juscite-e18-wiring-")
        state_root = Path(cls.holder.name) / "state"
        state_root.mkdir(parents=True)
        cls.config = _harness_config(state_root)
        sys.path.insert(0, str(HARNESS_REPO / "src"))
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(_MATTER, "cas://profile-e18-wiring")
        cls.scope = {"kind": "matter", "matterId": _MATTER}
        cls.g1 = legal_entry.call(
            "harness.save_goal",
            {"actor_id": "lawyer-1", "scope": cls.scope, "key": _key("wg-1"),
             "goal": _goal_payload(_MATTER, "g-1")}, cls.config)
        cls.g2 = legal_entry.call(
            "harness.save_goal",
            {"actor_id": "lawyer-1", "scope": cls.scope, "key": _key("wg-2"),
             "goal": _goal_payload(_MATTER, "g-2")}, cls.config)

    @classmethod
    def tearDownClass(cls):
        cls.holder.cleanup()

    def test_01_register_pins_goal_refs_and_reads_fresh(self):
        registered = legal_entry.call(
            "harness.strategy_basis_register",
            {"actor_id": "lawyer-1", "scope": self.scope, "key": _key("ws-1"),
             "strategy": {
                 "strategyId": "st-1", "revision": 1,
                 "title": "E18 桥合成策略：诉讼追收保全关系",
                 "goalRefs": [self.g1["goalRef"], self.g2["goalRef"]],
                 "factRevision": "v1", "lawRevision": "v1",
                 "hardConstraints": [{"constraintId": "hc-2",
                                      "statement": "不接受分期（合成硬约束）"}]}},
            self.config)
        self.assertEqual(registered["strategy"]["revision"], 1)
        self.assertTrue(all(ref["owner"] == "harness"
                            for ref in registered["strategy"]["goalRefs"]))
        projection = legal_entry.call(
            "harness.strategy_basis_read",
            {"scope": self.scope, "strategy_id": "st-1"}, self.config)
        gates = projection["gates"]
        self.assertEqual([gates["factGate"]["status"],
                          gates["lawGate"]["status"],
                          gates["strategyGate"]["status"]],
                         ["FRESH", "FRESH", "FRESH"])

    def test_02_goal_ref_forgery_refused(self):
        forged = dict(self.g1["goalRef"], owner="jc")
        with self.assertRaises(legal_entry.HarnessCommandError) as ctx:
            legal_entry.call(
                "harness.strategy_basis_register",
                {"actor_id": "lawyer-1", "scope": self.scope,
                 "key": _key("ws-forge"),
                 "strategy": {
                     "strategyId": "st-forge", "revision": 1, "title": "伪造",
                     "goalRefs": [forged], "factRevision": "v1",
                     "lawRevision": "v1", "hardConstraints": []}},
                self.config)
        self.assertIn("strategy_goal_ref_owner_invalid", str(ctx.exception))

    def test_03_jc_receipt_transcribed_and_hard_constraint_not_offset(self):
        # 真实 JC 公开出口取回执（owner=jc）——三门全 pass 且约束满足。
        code, out = _run_cli(
            "jc.strategy_evaluate",
            {"matterId": _MATTER, "request": {
                "strategyId": "st-1", "strategyRevision": 1,
                "gates": _gates(), "declaredConstraints": ["hc-2"],
                "constraintResults": [{"constraintId": "hc-2",
                                       "satisfied": True}]}},
            _jc_config())
        self.assertEqual(code, 0, out)
        jc_ref = out["result"]["strategyBasisRef"]
        recorded = legal_entry.call(
            "harness.strategy_basis_evaluate",
            {"actor_id": "jc-evaluator", "scope": self.scope,
             "key": _key("we-1"),
             "evaluation": {
                 "evaluationId": "ev-1", "strategyId": "st-1",
                 "strategyRevision": 1, "gates": _gates(),
                 "constraintResults": [{"constraintId": "hc-2",
                                        "satisfied": True}],
                 "jcEvaluationRef": jc_ref}},
            self.config)
        self.assertEqual(recorded["evaluation"]["overall"], "pass")
        # 违反路径：JC 判违反（satisfied=false → JC overall=fail），harness
        # 转录后账本推导同样 fail——三门全 pass 不抵硬约束违反。
        code, out = _run_cli(
            "jc.strategy_evaluate",
            {"matterId": _MATTER, "request": {
                "strategyId": "st-1", "strategyRevision": 1,
                "gates": _gates(), "declaredConstraints": ["hc-2"],
                "constraintResults": [{"constraintId": "hc-2",
                                       "satisfied": False}]}},
            _jc_config())
        self.assertEqual(out["result"]["overall"], "fail")
        violated = legal_entry.call(
            "harness.strategy_basis_evaluate",
            {"actor_id": "jc-evaluator", "scope": self.scope,
             "key": _key("we-2"),
             "evaluation": {
                 "evaluationId": "ev-2", "strategyId": "st-1",
                 "strategyRevision": 1, "gates": _gates(),
                 "constraintResults": [{"constraintId": "hc-2",
                                        "satisfied": False}],
                 "jcEvaluationRef": out["result"]["strategyBasisRef"]}},
            self.config)
        self.assertEqual(violated["evaluation"]["overall"], "fail")
        self.assertEqual(violated["evaluation"]["hardConstraintViolations"],
                         ["hc-2"])

    def test_04_combined_verdict_refused_at_bridge(self):
        with self.assertRaises(legal_entry.HarnessCommandError) as ctx:
            legal_entry.call(
                "harness.strategy_basis_evaluate",
                {"actor_id": "jc-evaluator", "scope": self.scope,
                 "key": _key("we-stuff"),
                 "evaluation": {
                     "evaluationId": "ev-stuff", "strategyId": "st-1",
                     "strategyRevision": 1, "gates": _gates(),
                     "constraintResults": [{"constraintId": "hc-2",
                                            "satisfied": True}],
                     "jcEvaluationRef": self.g1["goalRef"],
                     "total": 0.87}},
                self.config)
        self.assertIn("strategy_combined_verdict_refused", str(ctx.exception))

    def test_05_goal_only_change_stales_strategy_gate_only(self):
        # 只改 G1（G2 不动，fact/law 同版）＝goal-only 策略变更。
        legal_entry.call(
            "harness.save_goal",
            {"actor_id": "lawyer-1", "scope": self.scope,
             "key": _key("wg-3", "g-1", 1),
             "goal": _goal_payload(_MATTER, "g-1", revision=2, supersedes=1)},
            self.config)
        projection = legal_entry.call(
            "harness.strategy_basis_read",
            {"scope": self.scope, "strategy_id": "st-1"}, self.config)
        gates = projection["gates"]
        self.assertEqual(gates["factGate"]["status"], "FRESH",
                         "fact 同版不动＝事实门保持 FRESH")
        self.assertEqual(gates["lawGate"]["status"], "FRESH")
        self.assertEqual(gates["strategyGate"]["status"], "STALE")
        self.assertIn("goal_head_moved:g-1:pinned1->head2",
                      gates["strategyGate"]["reasons"])
        # 三门分判的独立门：current 显式给新版 fact → 事实门独立 STALE。
        projection = legal_entry.call(
            "harness.strategy_basis_read",
            {"scope": self.scope, "strategy_id": "st-1",
             "current": {"factRevision": "v2"}}, self.config)
        self.assertEqual(projection["gates"]["factGate"]["status"], "STALE")
        self.assertEqual(projection["gates"]["lawGate"]["status"], "FRESH")
        listed = legal_entry.call(
            "harness.strategy_basis_list", {"scope": self.scope}, self.config)
        self.assertEqual([s["strategyId"] for s in listed["strategies"]],
                         ["st-1"], "伪造拒绝路径零入账")


if __name__ == "__main__":
    unittest.main()
