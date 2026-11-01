"""E18 客户目标与策略 basis 对账（W2b-U52）——双 profile（desktop/selfhost）。

对账对象：harness 分支 w2b-u52（基施工链头 w2b-u51@425e1cf5＝线2→线3
同链接力，schema v22 策略依赖账）的 public_entry --strategybasis-json
封闭径——desktop profile 与产品桥（legal_entry → 子进程 public_entry）
完全同一条链（SQLite 状态根）；selfhost profile＝PgMatterStore 直连
lh-pg-e08（resolve_provider_method 同一封闭注册）。全部合成材料：临时
状态根、合成 goal/策略/评估/JC 回执；harness 与 JC 检出零字节改动（只
运行其代码，git 只读命令核对分支）。

实跑覆盖（07 E18＋08§3 五场景行「goal-only策略变更」逐条）：
  G1/G2 保存→策略行钉 goal 版本引用（owner=harness 摘要必验）→同
  (id,revision) 幂等重放→goal ref 伪造（owner≠harness）具名拒零入账→
  摘要漂移具名拒→三门缺一具名拒（strategy_gate_missing＝三门合并判定
  非法）→总分字段具名拒（strategy_combined_verdict_refused＝总分互相
  抵形态结构性不存在）→**真实 JC 公开出口**（jc.strategy_evaluate 真跑
  取 strategyBasisRef owner=jc）→harness 转录评估（三门全 pass＋约束满
  足＝overall pass）→硬约束违反（JC satisfied=false 判 fail）→harness
  账本推导 overall=fail＋violations 具名（三门全 pass 不抵硬约束）→单
  门 fail 不互相抵→**goal-only 变更**（只改 G1，G2 不动，fact/law 同
  版）→读取投影三分判：事实/法律门 FRESH、策略门 STALE（逐 goal 具名
  reason goal_head_moved）→current 显式 fact 新版＝事实门独立 STALE 法
  律门不动→current 携带 goalRevision＝fields_not_closed（goal 时效只认
  账本）→撤销 G2→策略门 STALE（goal_revoked）→DB 级行数/重放不双登
  →桥负向（未配置 NOT_CONNECTED／未知方法 method_not_connected／方法组
  冻结＋goal 组零动）。

用法：
  python -X utf8 tools/PENDING_OWNER_e18_goal_strategy_basis_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/E18/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "implementation" / "tests"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u52")
DEFAULT_JC_ROOT = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w2b-u52")

MATTER = "m-e18-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（LH_PG_PASSWORD
# 同源，密钥只在本机容器；可用 LH_E08_PG_DSN 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

# JC 检出＝本单 w2b-u52 worktree（w2b-u19(E21)→w2b-u27(E19)→w2b-u51(E16)
# 同链接头超集）。client.py／strategy_basis.py sha256 钉定＝本单收口字
# 节，漂移即 FATAL（不猜改不静默换源）。
JC_CLIENT_SHA256 = "9a7ed9c2cae35905a48765a3505f6ba63c1858e22ded6a5746fc11e0f5b04b0b"
JC_STRATEGY_BASIS_SHA256 = "0ef7f0410f72b764708ffbb9e78db0575e080de42954df1db3b9602102552dad"

E18_METHODS = frozenset({
    "harness.strategy_basis_register", "harness.strategy_basis_evaluate",
    "harness.strategy_basis_read", "harness.strategy_basis_list",
    "harness.strategy_evaluation_read", "harness.strategy_evaluation_list",
})

GOAL_GROUP = frozenset({
    "harness.save_goal", "harness.revoke_goal", "harness.get_goal",
    "harness.list_goals", "harness.decide_goal_plan", "harness.adopt_goal_task",
    "harness.pause_goal", "harness.resume_goal", "harness.list_goal_pauses",
    "harness.read_goal_basis",
})

# create_local_client 需要至少一个规则根（JC 不自带规则库）；策略评估
# 面语义上不消费规则，给最小合成包（无法律效力，仅工程验证）。
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
         "governing_law": "acceptance-statute",
         "source_id": "acceptance-statute", "modality": "OBLIGATION",
         "premises": [{"fact_key": "acc.contract", "required": True}],
         "conclusion": {"value": "applies"},
         "effective_from": "2020-01-01T00:00:00Z"},
    ],
}

_ACTIVE_TMPDIRS = []


def key(request_id: str, target_id: str | None = None,
        expected_revision: int | None = None) -> dict:
    return {"requestId": request_id, "targetId": target_id,
            "expectedRevision": expected_revision, "inputRefs": []}


def goal_payload(goal_id: str, revision: int = 1,
                 supersedes: int | None = None) -> dict:
    return {
        "schemaVersion": "1.0.0-draft", "matterId": MATTER, "goalId": goal_id,
        "revision": revision,
        "confirmedScope": "E18 对账合成：货款 85000 元追收",
        "hardConstraints": [
            {"id": "hc-1", "kind": "min_recovery", "value": "85000",
             "description": "最低实收"},
            {"id": "hc-2", "kind": "no_installment", "value": "true",
             "description": "不接受分期"},
        ],
        "preferences": [{"id": "pf-1", "kind": "relationship",
                         "description": "保留供货关系"}],
        "unitTiming": {"unit": "CNY", "asOf": "2026-10-17"},
        "sourceDecisionRef": None,
        "supersedesRevision": supersedes,
    }


def gates_payload(strategy_verdict: str = "pass") -> dict:
    return {
        "fact": {"verdict": "pass",
                 "basisRefs": ["fact-pins:f-contract@v1（合成）"]},
        "law": {"verdict": "pass",
                "basisRefs": ["law-check-snapshot:lcs-1（合成）"]},
        "strategy": {"verdict": strategy_verdict,
                     "basisRefs": ["goal:g-1@1", "goal:g-2@1"]},
    }


def jc_config() -> dict:
    """JC 面配置（w2b-u52 worktree 钉定；state/rules 全合成临时根）。"""
    if not (DEFAULT_JC_ROOT / "compiler_core" / "strategy_basis.py").is_file():
        raise AssertionError(f"pinned JC worktree missing: {DEFAULT_JC_ROOT}")
    holder = tempfile.TemporaryDirectory(prefix="juscite-e18-jc-")
    _ACTIVE_TMPDIRS.append(holder)  # keep alive for the whole recon
    tmp = Path(holder.name)
    rules = tmp / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {"jc_state_root": str(tmp / "state"),
            "jc_rule_roots": [str(rules)],
            "jc_import_path": str(DEFAULT_JC_ROOT)}


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks: list[dict] = []

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part,
                     error=(HarnessCommandError, ValueError)):
        # desktop 桥链合同码冒 HarnessCommandError；selfhost 直连公开面冒
        # UnitsError（ValueError 子类）——两者都只认 code_part 在码里。
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc))
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref",
                          "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w2b-u51")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w2b-u52", branch=branch)
        self.step("c01_harness_base_on_w2b_u51_chain_head",
                  base.startswith("425e1cf5"), base=base)
        self.step("c01_harness_master_untouched", master.startswith("929d0802"),
                  master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])
        jc_client = hashlib.sha256(
            (DEFAULT_JC_ROOT / "compiler_core" / "client.py")
            .read_bytes()).hexdigest()
        jc_module = hashlib.sha256(
            (DEFAULT_JC_ROOT / "compiler_core" / "strategy_basis.py")
            .read_bytes()).hexdigest()
        self.step("c01_jc_client_pin", jc_client == JC_CLIENT_SHA256,
                  sha256=jc_client[:16])
        self.step("c01_jc_strategy_basis_pin",
                  jc_module == JC_STRATEGY_BASIS_SHA256,
                  sha256=jc_module[:16])

    # ------------------------------------------------------------------
    # C02–C13：call(method, args) 走被测链；query(sql, params) 直读库；
    # jc_evaluate(request) 走真实 JC 公开出口（legal_entry CLI 子进程全
    # 链——与产品桥同一进程形）。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query, jc_evaluate):
        # ---- C02 G1/G2 保存＋策略行钉 goal 版本引用。
        g1 = call("harness.save_goal", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("rg-1"),
            "goal": goal_payload("g-1")})
        g2 = call("harness.save_goal", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("rg-2"),
            "goal": goal_payload("g-2")})
        strategy = {
            "strategyId": "st-1", "revision": 1,
            "title": "E18 对账合成策略：诉讼追收保全关系",
            "goalRefs": [g1["goalRef"], g2["goalRef"]],
            "factRevision": "v1", "lawRevision": "v1",
            "hardConstraints": [{"constraintId": "hc-2",
                                 "statement": "不接受分期（合成硬约束）"}],
        }
        registered = call("harness.strategy_basis_register", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("rs-1"),
            "strategy": strategy})
        self.step("c02_strategy_pins_goal_version_refs",
                  registered["strategy"]["revision"] == 1
                  and [ref["id"] for ref in registered["strategy"]["goalRefs"]]
                  == ["g-1", "g-2"]
                  and all(ref["owner"] == "harness" and ref["digest"]
                          for ref in registered["strategy"]["goalRefs"]),
                  goalRefs=[ref["id"] + "@" + ref["version"]
                            for ref in registered["strategy"]["goalRefs"]])
        replay = call("harness.strategy_basis_register", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("rs-replay"),
            "strategy": strategy})
        self.step("c02_same_revision_replay_idempotent",
                  replay["replayed"] is True
                  and query("SELECT COUNT(*) AS n FROM strategy_basis_rows"
                            " WHERE matter_id=?", (MATTER,))[0]["n"] == 1,
                  replayed=replay["replayed"])

        # ---- C03 goal ref 伪造（owner≠harness）具名拒零入账。
        forged = dict(g1["goalRef"], owner="jc")
        self.expect_error("c03_goal_ref_forgery_refused", lambda: call(
            "harness.strategy_basis_register", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("rs-forge"),
                "strategy": dict(strategy, strategyId="st-forge",
                                 goalRefs=[forged])}),
            "strategy_goal_ref_owner_invalid:g-1@1")
        unknown = dict(g1["goalRef"], id="g-404")
        self.expect_error("c03_goal_ref_unknown_refused", lambda: call(
            "harness.strategy_basis_register", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("rs-unknown"),
                "strategy": dict(strategy, strategyId="st-unknown",
                                 goalRefs=[unknown])}),
            "strategy_goal_ref_unknown:g-404@1")
        drifted = dict(g1["goalRef"], digest="sha256:" + "f" * 64)
        self.expect_error("c03_goal_ref_digest_drift_refused", lambda: call(
            "harness.strategy_basis_register", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": key("rs-drift"),
                "strategy": dict(strategy, strategyId="st-drift",
                                 goalRefs=[drifted])}),
            "strategy_goal_digest_mismatch:g-1@1")
        rows = query("SELECT COUNT(*) AS n FROM strategy_basis_rows"
                     " WHERE matter_id=?", (MATTER,))[0]["n"]
        self.step("c03_refusals_left_zero_rows", rows == 1, strategies=rows)

        # ---- C04 三门缺一具名拒（三门合并判定非法）。
        for missing in ("fact", "law", "strategy"):
            gates = gates_payload()
            gates.pop(missing)
            self.expect_error(f"c04_gate_missing_{missing}_refused",
                              lambda gates=gates, missing=missing: call(
                                  "harness.strategy_basis_evaluate", {
                                      "actor_id": "jc-evaluator",
                                      "scope": SCOPE,
                                      "key": key(f"re-miss-{missing}"),
                                      "evaluation": {
                                          "evaluationId": f"ev-miss-{missing}",
                                          "strategyId": "st-1",
                                          "strategyRevision": 1,
                                          "gates": gates,
                                          "constraintResults": [
                                              {"constraintId": "hc-2",
                                               "satisfied": True}],
                                          "jcEvaluationRef": dict(
                                              g1["goalRef"], owner="jc",
                                              kind="strategy-basis-sheet",
                                              id="jc-calc-x",
                                              digest="sha256:" + "0" * 64)}}),
                              f"strategy_gate_missing:{missing}")

        # ---- C05 总分字段具名拒（总分互相抵形态结构性不存在）。
        stuffed = {"evaluationId": "ev-stuff", "strategyId": "st-1",
                   "strategyRevision": 1, "gates": gates_payload(),
                   "constraintResults": [{"constraintId": "hc-2",
                                          "satisfied": True}],
                   "jcEvaluationRef": dict(g1["goalRef"], owner="jc",
                                           kind="strategy-basis-sheet",
                                           id="jc-calc-x",
                                           digest="sha256:" + "0" * 64),
                   "score": 0.87}
        self.expect_error("c05_combined_score_refused", lambda: call(
            "harness.strategy_basis_evaluate", {
                "actor_id": "jc-evaluator", "scope": SCOPE,
                "key": key("re-stuff"), "evaluation": stuffed}),
            "strategy_combined_verdict_refused:evaluation:score")
        gates_stuffed = gates_payload()
        gates_stuffed["overall"] = {"verdict": "pass", "basisRefs": ["x"]}
        gates_stuffed_payload = {
            "evaluationId": "ev-stuff-gates", "strategyId": "st-1",
            "strategyRevision": 1, "gates": gates_stuffed,
            "constraintResults": [{"constraintId": "hc-2",
                                   "satisfied": True}],
            "jcEvaluationRef": dict(g1["goalRef"], owner="jc",
                                    kind="strategy-basis-sheet",
                                    id="jc-calc-x",
                                    digest="sha256:" + "0" * 64)}
        self.expect_error("c05_gates_combined_refused", lambda: call(
            "harness.strategy_basis_evaluate", {
                "actor_id": "jc-evaluator", "scope": SCOPE,
                "key": key("re-stuff-gates"),
                "evaluation": gates_stuffed_payload}),
            "strategy_combined_verdict_refused:gates:overall")
        rows = query("SELECT COUNT(*) AS n FROM strategy_gate_evaluations"
                     " WHERE matter_id=?", (MATTER,))[0]["n"]
        self.step("c05_refusals_left_zero_evaluations", rows == 0,
                  evaluations=rows)

        # ---- C06 真实 JC 公开出口：三门全 pass＋约束满足→harness 转录
        # overall=pass（jcEvaluationRef owner=jc 只转录不制造）。
        jc_pass = jc_evaluate({
            "strategyId": "st-1", "strategyRevision": 1,
            "gates": gates_payload(), "declaredConstraints": ["hc-2"],
            "constraintResults": [{"constraintId": "hc-2",
                                   "satisfied": True}]})
        self.step("c06_jc_real_exit_seals_pass",
                  jc_pass["overall"] == "pass"
                  and jc_pass["strategyBasisRef"]["owner"] == "jc"
                  and jc_pass["strategyBasisRef"]["digest"].startswith("sha256:"),
                  ref=jc_pass["strategyBasisRef"]["id"][:16])
        evaluated = call("harness.strategy_basis_evaluate", {
            "actor_id": "jc-evaluator", "scope": SCOPE, "key": key("re-1"),
            "evaluation": {
                "evaluationId": "ev-1", "strategyId": "st-1",
                "strategyRevision": 1, "gates": gates_payload(),
                "constraintResults": [{"constraintId": "hc-2",
                                       "satisfied": True}],
                "jcEvaluationRef": jc_pass["strategyBasisRef"]}})
        self.step("c06_harness_transcribes_overall_pass",
                  evaluated["evaluation"]["overall"] == "pass"
                  and evaluated["evaluation"]["jcEvaluationRef"]["owner"]
                  == "jc",
                  overall=evaluated["evaluation"]["overall"])

        # ---- C07 硬约束违反：JC 判 fail→harness 账本推导同样 fail
        # （三门全 pass 不抵硬约束违反，violations 逐条具名）。
        jc_violated = jc_evaluate({
            "strategyId": "st-1", "strategyRevision": 1,
            "gates": gates_payload(), "declaredConstraints": ["hc-2"],
            "constraintResults": [{"constraintId": "hc-2",
                                   "satisfied": False}]})
        self.step("c07_jc_judges_violation_fail",
                  jc_violated["overall"] == "fail"
                  and jc_violated["hard_constraint_violations"] == ["hc-2"],
                  overall=jc_violated["overall"])
        violated = call("harness.strategy_basis_evaluate", {
            "actor_id": "jc-evaluator", "scope": SCOPE, "key": key("re-2"),
            "evaluation": {
                "evaluationId": "ev-2", "strategyId": "st-1",
                "strategyRevision": 1, "gates": gates_payload(),
                "constraintResults": [{"constraintId": "hc-2",
                                       "satisfied": False}],
                "jcEvaluationRef": jc_violated["strategyBasisRef"]}})
        self.step("c07_hard_constraint_never_offset",
                  violated["evaluation"]["overall"] == "fail"
                  and violated["evaluation"]["hardConstraintViolations"]
                  == ["hc-2"],
                  overall=violated["evaluation"]["overall"])

        # ---- C08 单门 fail 不互相抵（三门分别判定）。
        jc_onefail = jc_evaluate({
            "strategyId": "st-1", "strategyRevision": 1,
            "gates": gates_payload(strategy_verdict="fail"),
            "declaredConstraints": ["hc-2"],
            "constraintResults": [{"constraintId": "hc-2",
                                   "satisfied": True}]})
        onefail = call("harness.strategy_basis_evaluate", {
            "actor_id": "jc-evaluator", "scope": SCOPE, "key": key("re-3"),
            "evaluation": {
                "evaluationId": "ev-3", "strategyId": "st-1",
                "strategyRevision": 1,
                "gates": gates_payload(strategy_verdict="fail"),
                "constraintResults": [{"constraintId": "hc-2",
                                       "satisfied": True}],
                "jcEvaluationRef": jc_onefail["strategyBasisRef"]}})
        self.step("c08_single_gate_fail_not_offset",
                  onefail["evaluation"]["overall"] == "fail"
                  and onefail["evaluation"]["hardConstraintViolations"] == [],
                  overall=onefail["evaluation"]["overall"])

        # ---- C09 goal-only 变更：只改 G1（G2 不动，fact/law 同版）→
        # 三分判：事实/法律门 FRESH、策略门 STALE（逐 goal 具名 reason）。
        call("harness.save_goal", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("rg-3", "g-1", 1),
            "goal": goal_payload("g-1", revision=2, supersedes=1)})
        moved = call("harness.strategy_basis_read",
                     {"scope": SCOPE, "strategy_id": "st-1"})
        gates = moved["gates"]
        self.step("c09_goal_only_change_three_way_split",
                  gates["factGate"]["status"] == "FRESH"
                  and gates["lawGate"]["status"] == "FRESH"
                  and gates["strategyGate"]["status"] == "STALE"
                  and gates["strategyGate"]["movedGoalCount"] == 1
                  and "goal_head_moved:g-1:pinned1->head2"
                  in gates["strategyGate"]["reasons"],
                  factGate=gates["factGate"]["status"],
                  lawGate=gates["lawGate"]["status"],
                  strategyGate=gates["strategyGate"]["status"],
                  reasons=gates["strategyGate"]["reasons"])
        pins = {pin["goalId"]: pin for pin in moved["goalPins"]}
        self.step("c09_goal_pins_projected",
                  pins["g-1"]["headRevision"] == 2
                  and pins["g-1"]["moved"] is True
                  and pins["g-2"]["moved"] is False,
                  g1=(pins["g-1"]["pinnedRevision"], pins["g-1"]["headRevision"]),
                  g2=(pins["g-2"]["pinnedRevision"], pins["g-2"]["headRevision"]))

        # ---- C10 三门独立：current 显式 fact 新版→事实门独立 STALE；
        # current 携带 goalRevision 拒（goal 时效只认账本）。
        fact_moved = call("harness.strategy_basis_read", {
            "scope": SCOPE, "strategy_id": "st-1",
            "current": {"factRevision": "v2"}})
        self.step("c10_fact_gate_stale_independently",
                  fact_moved["gates"]["factGate"]["status"] == "STALE"
                  and fact_moved["gates"]["factGate"]["reason"]
                  == "fact_revision_moved"
                  and fact_moved["gates"]["lawGate"]["status"] == "FRESH",
                  fact=fact_moved["gates"]["factGate"]["status"],
                  law=fact_moved["gates"]["lawGate"]["status"])
        self.expect_error("c10_current_goal_revision_refused", lambda: call(
            "harness.strategy_basis_read",
            {"scope": SCOPE, "strategy_id": "st-1",
             "current": {"goalRevision": "9"}}),
            "fields_not_closed")

        # ---- C11 撤销 G2→策略门 STALE（goal_revoked）。
        call("harness.revoke_goal", {
            "actor_id": "lawyer-1", "scope": SCOPE, "key": key("rv-2"),
            "goal_id": "g-2"})
        revoked = call("harness.strategy_basis_read",
                       {"scope": SCOPE, "strategy_id": "st-1"})
        self.step("c11_revoked_goal_stales_strategy_gate",
                  revoked["gates"]["strategyGate"]["status"] == "STALE"
                  and "goal_revoked:g-2"
                  in revoked["gates"]["strategyGate"]["reasons"],
                  reasons=revoked["gates"]["strategyGate"]["reasons"])

        # ---- C12 DB 级对账：评估账三行（重放不双登、拒绝零行）＋清单
        # ＋latest 投影。
        counts = query(
            "SELECT (SELECT COUNT(*) FROM strategy_basis_rows WHERE"
            " matter_id=?) AS strategies, (SELECT COUNT(*) FROM"
            " strategy_gate_evaluations WHERE matter_id=?) AS evaluations",
            (MATTER, MATTER))[0]
        listed = call("harness.strategy_evaluation_list",
                      {"scope": SCOPE, "strategy_id": "st-1"})
        projection = call("harness.strategy_basis_read",
                          {"scope": SCOPE, "strategy_id": "st-1"})
        self.step("c12_ledger_rows_and_projection",
                  counts["strategies"] == 1 and counts["evaluations"] == 3
                  and listed["evaluationCount"] == 3
                  and projection["latestEvaluation"]["evaluationId"] == "ev-3"
                  and "score" not in json.dumps(projection)
                  and "total" not in json.dumps(projection),
                  strategies=counts["strategies"],
                  evaluations=counts["evaluations"],
                  latest=projection["latestEvaluation"]["evaluationId"])

    def bridge_negatives(self, config):
        # ---- C13 桥负向：未配置/未知方法/方法组冻结＋goal 组零动。
        try:
            legal_entry.call("harness.strategy_basis_register",
                             {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c13_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.strategy_basis_decide",
                             {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c13_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c13_method_group_frozen",
                  legal_entry.HARNESS_STRATEGY_METHODS == E18_METHODS)
        self.step("c13_goal_group_untouched",
                  legal_entry.HARNESS_GOAL_METHODS == GOAL_GROUP)

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-e18-desktop-")
        _ACTIVE_TMPDIRS.append(temporary)
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config = {
            "harness_public_entry":
                str(self.harness_root / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
        }
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(MATTER, "cas://profile-e18-recon")

        def call(method, args):
            return legal_entry.call(method, args, config)

        def query(sql, params):
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def jc_evaluate(request):
            result = legal_entry.call("jc.strategy_evaluate",
                                      {"matterId": MATTER, "request": request},
                                      jc_config())
            if result.get("overall") is None:
                raise AssertionError(f"jc strategy evaluate failed: {result}")
            return result

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop", call, query, jc_evaluate)
        self.bridge_negatives(config)
        return 0

    def run_selfhost(self, dsn: str) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-e18-selfhost-")
        _ACTIVE_TMPDIRS.append(temporary)
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="e18_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        bound = {name: resolve_provider_method(name, units)
                 for name in E18_METHODS | GOAL_GROUP}
        store.create_matter(MATTER, "cas://profile-e18-recon")

        def call(method, args):
            return bound[method](**args)

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        def jc_evaluate(request):
            result = legal_entry.call("jc.strategy_evaluate",
                                      {"matterId": MATTER, "request": request},
                                      jc_config())
            if result.get("overall") is None:
                raise AssertionError(f"jc strategy evaluate failed: {result}")
            return result

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        self.common_flow("selfhost", call, query, jc_evaluate)
        store.destroy()
        return 0


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> Path:
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" / "E18" \
        / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-e18-goal-strategy-basis-recon/1",
        "unit": "W2b-U52",
        "feature": "E18",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w2b-u52",
        "harness_base": "w2b-u51@425e1cf5 (施工链头：w2a-u05→w2a-u06/F114→"
                        "w2b-u01/F25→w2b-u11/F47→w2b-u23/E15→w2b-u05/F82→"
                        "w2b-u25/E17→w2b-u31/F82复核→w2b-u40/F92→w2b-u51/E16)",
        "jc_worktree": str(DEFAULT_JC_ROOT),
        "jc_pin": {"client_sha256": JC_CLIENT_SHA256,
                   "strategy_basis_sha256": JC_STRATEGY_BASIS_SHA256},
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    (evidence_dir / "e18_goal_strategy_basis_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    lines = [f"# E18 客户目标与策略 basis recon（{profile}）",
             "",
             f"- unit: W2b-U52 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ branch w2b-u52"
             "（基 w2b-u51@425e1cf5 施工链头；master 929d0802 零动）",
             f"- JC: `{DEFAULT_JC_ROOT}` @ branch w2b-u52"
             "（client.py/strategy_basis.py sha256 钉定）",
             f"- started: {started} · finished: {finished}",
             "",
             "| # | check | status |",
             "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']}"
                     f" | {check['status']} |")
    lines += ["", "全部合成材料；desktop＝产品桥子进程全链（SQLite 状态根），"
              "selfhost＝PgMatterStore 直连 lh-pg-e08（同一封闭注册）；"
              "评估回执经真实 JC 公开出口（jc.strategy_evaluate 真跑）取得，"
              "strategyBasisRef owner=jc，harness 只转录不制造；goal-only "
              "变更（只改 G1，fact/law 同版）后三门分判：事实/法律门 FRESH、"
              "策略门 STALE。"]
    (evidence_dir / "e18_goal_strategy_basis_recon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return evidence_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py"
            ).exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    if not (DEFAULT_JC_ROOT / "compiler_core" / "strategy_basis.py").is_file():
        print("RECON_BLOCKED: pinned JC worktree missing:", DEFAULT_JC_ROOT)
        return 3
    failures = 0
    first = True
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root)
        try:
            if first:
                # C01 分支/基/master/工作树干净/JC 双钉亲验（只跑一次，两
                # profile 共用同一 harness 检出）。
                recon.branch_checks()
            if profile == "desktop":
                code = recon.run_desktop()
            else:
                code = recon.run_selfhost(args.pg_dsn)
        except Exception as error:  # noqa: BLE001 - reported per profile
            print(f"RECON_FAIL[{profile}]: {error}", flush=True)
            recon.checks.append({"check": "recon_driver", "status": "FAIL",
                                 "error": str(error)[:400]})
            code = 2
        evidence_dir = write_evidence(profile, recon, args.harness_root,
                                      started, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={evidence_dir}", flush=True)
        if code != 0:
            failures += 1
        first = False
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
