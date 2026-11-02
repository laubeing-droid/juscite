"""E15 路径与新证据公开合同对账（W2b-U23）——双 profile（desktop/selfhost）。

对账对象：harness 分支 w2b-u23（基于线2链头 w2b-u11@88bf1757＝
w2a-u05→w2a-u06(F114)→w2b-u01(F25)→w2b-u11(F47) 同链接力）的
public_entry --pathevidence-json 封闭径——desktop profile 与产品桥
（legal_entry → 子进程 public_entry）完全同一条链（SQLite 状态根）；
selfhost profile＝PgMatterStore 直连 lh-pg-e08（resolve_provider_method
同一封闭注册）。全部合成材料：临时状态根、合成事实/材料/候选/重评/投影；
harness 与 JC 检出零字节改动（只运行其代码，git 只读命令核对分支）。

实跑覆盖（PENDING_OWNER_E15_path_evidence_contract）：
  路径候选 pending（case_issues 零新增＝未采用卡片不改正式请求）→
  候选卡塞额外字段拒（闭集）→ 法源 locator 缺失拒 → 要件 unknown 终值
  照记 → r1/r2 备位＋同损失重叠声明回读 → adopt r2＝窄字段六字段闭集
  登记 case_issues（issue_saved 事件可见）＋adoptedIssueRef 可回读 →
  reject r1（issue 面一字不动）→ 决定态再决定拒（状态机）→ adopt 载荷
  塞额外字段拒 → 新证据重评（weakened 带 JC basis＋undetermined 无 basis
  ＝未知不伪支持）→ 无依据签增强拒 → 判定闭集外拒 → **真实 JC 公开出口**
  （jc.evaluate 真跑＋read_argument_graph 读取，branchRefs 实测为空）
  → 分支投影登记（hasBranches=false＋noBranchReason 具名＝该 run 无分支
  显式标记）→ harness 造 branch ref 拒（不由前端制造）→ DB 级扫描
  （三账行数/窄字段载荷逐键）→ 桥负向（未配置 NOT_CONNECTED／未知方法
  method_not_connected／方法组冻结）。

用法：
  python -X utf8 tools/PENDING_OWNER_e15_path_evidence_contract_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/E15/<profile>/ JSON＋MD。
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
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo\.local\worktrees\w2b-u23")

MATTER = "m-e15-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}

# lh-pg-e08 容器（E08 拓扑）：仅回环端口、合成专用凭据（LH_PG_PASSWORD
# 同源，密钥只在本机容器；可用 LH_E08_PG_DSN 覆写）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

# JC 检出（14-Python入口证据.csv P01 钉定路径；只读）。client.py sha256
# 钉定＝P01 同值，漂移即 FATAL（不猜改不静默换源）。
JC_REPO = Path(r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus")
JC_CLIENT_SHA256 = "15c2f88f415d1758a628d7f98c1ecb87c623f017ffe1f1040c488d9ad775c7be"

E15_METHODS = frozenset({
    "harness.path_candidate_register", "harness.path_candidate_decide",
    "harness.path_candidate_read", "harness.path_candidate_list",
    "harness.assessment_delta_record", "harness.assessment_delta_read",
    "harness.assessment_delta_list",
    "harness.branch_projection_record", "harness.branch_projection_read",
    "harness.branch_projection_list",
})


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def href(kind: str, ref_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": "1", "matterId": MATTER}


def synth_candidate(candidate_id: str, title: str,
                    relation_targets: list[str]) -> dict:
    return {
        "candidateId": candidate_id,
        "pathType": "claim",
        "title": title,
        "basisRefs": [href("fact", "f-contract"), href("issue", "issue-base")],
        "triggerLocator": {
            "materialRef": href("material", "mat-e15"),
            "documentId": "doc-1", "pageIndex": 3, "blockId": "blk-7",
            "span": {"startCodePoint": 10, "endCodePoint": 40}},
        "elements": [
            {"elementId": "el-1", "statement": "合同有效成立",
             "status": "established",
             "factRefs": [href("fact", "f-contract")],
             "counterEvidenceRefs": []},
            {"elementId": "el-2", "statement": "违约行为",
             "status": "disputed",
             "factRefs": [href("fact", "f-breach")],
             "counterEvidenceRefs": [href("fact", "f-performance")]},
            {"elementId": "el-3", "statement": "损失数额确定",
             "status": "unknown", "factRefs": [], "counterEvidenceRefs": []},
        ],
        "lawVersionRefs": [
            {"ref": {"owner": "codices", "kind": "statute",
                     "id": "WJBS-583", "version": "1", "matterId": None},
             "locator": "GB583 第577条",
             "supportStatus": "verified_locator_only"},
        ],
        "deadlineNote": "三年诉讼时效（合成）",
        "relation": {"kind": "alternative",
                     "targetCandidateIds": relation_targets},
        "lossOverlap": {"declared": True, "sameLossWith": relation_targets,
                        "note": "同一损失重叠不得重复受偿（合成声明）"},
        "normativeScopeRefs": [href("law-check-snapshot", "lcs-1")],
        "experientialScopeRefs": [href("case_sample", "cs-9")],
        "proposedTaskRef": href("task", "t-research-1"),
        "note": "全合成候选卡",
    }


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
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref", "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w2b-u11")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w2b-u23", branch=branch)
        self.step("c01_harness_base_on_w2b_u11", base.startswith("88bf1757"),
                  base=base)
        self.step("c01_harness_master_untouched", master.startswith("929d0802"),
                  master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])
        jc_sha = hashlib.sha256(
            (JC_REPO / "compiler_core" / "client.py").read_bytes()).hexdigest()
        self.step("c01_jc_client_pin", jc_sha == JC_CLIENT_SHA256,
                  sha256=jc_sha[:16])

    # ------------------------------------------------------------------
    # C02–C12：call(method, args) 走被测链；query(sql, params) 直读库。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call, query):
        # ---- C02 候选 pending：未采用卡片不改正式请求（issue 面零新增）。
        r1 = call("harness.path_candidate_register", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("reg-r1"),
            "candidate": synth_candidate(
                "r1", "违约损害赔偿备位主张（E15 对账合成 r1）", ["r2"])})
        issues_pending = query(
            "SELECT COUNT(*) AS n FROM case_issues WHERE matter_id=?",
            (MATTER,))[0]["n"]
        self.step("c02_pending_never_touches_formal_issues",
                  r1["candidate"]["state"] == "pending"
                  and r1["candidate"]["adoptedIssueRef"] is None
                  and issues_pending == 0,
                  state=r1["candidate"]["state"], issues=issues_pending)
        # 要件 unknown 终值照记（关键前提未知不当满足）。
        elements = r1["candidate"]["candidate"]["elements"]
        self.step("c02_element_unknown_recorded_verbatim",
                  [e["status"] for e in elements]
                  == ["established", "disputed", "unknown"],
                  statuses=[e["status"] for e in elements])

        # ---- C03 候选卡塞额外字段拒（请求/要件塞进候选 DTO 外字段即拒）。
        stuffed = synth_candidate("r-stuff", "塞额外字段（合成反例）", [])
        stuffed["requests"] = ["支付货款85,000元"]
        self.expect_error("c03_candidate_extra_fields_refused", lambda: call(
            "harness.path_candidate_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("reg-stuff"), "candidate": stuffed}),
            "fields_not_closed")
        # 法源 locator 缺失拒（法源 locator 缺失不用于正式论证）。
        no_locator = synth_candidate("r-noloc", "缺 locator（合成反例）", [])
        no_locator["lawVersionRefs"] = [
            {"ref": {"owner": "codices", "kind": "statute",
                     "id": "WJBS-583", "version": "1", "matterId": None},
             "locator": "", "supportStatus": "unverified"}]
        self.expect_error("c03_law_locator_missing_refused", lambda: call(
            "harness.path_candidate_register", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("reg-noloc"), "candidate": no_locator}),
            "path_candidate_law_locator_required")
        ledger_clean = query(
            "SELECT COUNT(*) AS n FROM path_candidates WHERE matter_id=?",
            (MATTER,))[0]["n"]
        self.step("c03_refusals_left_zero_rows", ledger_clean == 1,
                  candidates=ledger_clean)

        # ---- C04 r2 登记＋备位/重叠回读（备位路径可回读 r1/r2）。
        call("harness.path_candidate_register", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("reg-r2"),
            "candidate": synth_candidate(
                "r2", "不当得利返还备位主张（E15 对账合成 r2）", ["r1"])})
        readback_r1 = call("harness.path_candidate_read",
                           {"scope": SCOPE, "candidate_id": "r1"})["candidate"]
        relation = readback_r1["candidate"]["relation"]
        overlap = readback_r1["candidate"]["lossOverlap"]
        # 同损失重叠只有声明——候选账无金额字段（重叠损失不机械相加）。
        flat = json.dumps(readback_r1["candidate"], ensure_ascii=False)
        self.step("c04_alternative_and_overlap_readable",
                  relation["kind"] == "alternative"
                  and relation["targetCandidateIds"] == ["r2"]
                  and overlap["declared"] is True
                  and overlap["sameLossWith"] == ["r2"]
                  and "amount" not in flat and "sum" not in flat
                  and "percentage" not in flat,
                  relation=relation["kind"])

        # ---- C05 adopt r2＝窄字段闭集登记 case_issues＋采用记录可回读。
        adopted = call("harness.path_candidate_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-r2"),
            "decision": {"candidateId": "r2", "action": "adopt",
                         "reasonRef": href("reason", "r-adopt-r2"),
                         "receiptRef": href("receipt", "rc-adopt-r2"),
                         "issue": {"id": "issue-restitution", "revision": 1,
                                   "title": "不当得利返还（r2 采用后正式争点）",
                                   "claimRefs": [href("claim", "c-1")],
                                   "factRefs": [href("fact", "f-contract")],
                                   "partyIds": ["p-1"]}}})
        issue_row = query(
            "SELECT issue_json FROM case_issues WHERE matter_id=?"
            " AND issue_id='issue-restitution'",
            (MATTER,))[0]
        issue_payload = json.loads(issue_row["issue_json"])
        issue_saved = query(
            "SELECT COUNT(*) AS n FROM change_events WHERE matter_id=?"
            " AND kind='issue_saved'", (MATTER,))[0]["n"]
        self.step("c05_adopt_registers_issue_narrow_fields_only",
                  adopted["issuesTouched"] == 1
                  and set(issue_payload) == {
                      "id", "revision", "title", "claimRefs", "factRefs",
                      "partyIds", "ref"}
                  and issue_payload["title"]
                  == "不当得利返还（r2 采用后正式争点）"
                  and issue_saved == 1
                  and adopted["candidate"]["adoptedIssueRef"]["id"]
                  == "issue-restitution"
                  and adopted["candidate"]["decision"]["action"] == "adopt",
                  payload_keys=sorted(issue_payload))

        # ---- C06 adopt 载荷塞额外字段拒（窄字段不得塞额外——负向）。
        self.expect_error("c06_stuffed_issue_payload_refused", lambda: call(
            "harness.path_candidate_decide", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("dec-stuff"),
                "decision": {"candidateId": "r1", "action": "adopt",
                             "reasonRef": href("reason", "r-x"),
                             "receiptRef": href("receipt", "rc-x"),
                             "issue": {"id": "issue-x", "revision": 1,
                                       "title": "x", "claimRefs": [],
                                       "factRefs": [], "partyIds": [],
                                       "elements": [{"e": "塞要件"}]}}}),
            "fields_not_closed")
        issues_after_stuff = query(
            "SELECT COUNT(*) AS n FROM case_issues WHERE matter_id=?",
            (MATTER,))[0]["n"]
        self.step("c06_stuffed_payload_zero_issues", issues_after_stuff == 1,
                  issues=issues_after_stuff)

        # ---- C07 reject r1＝人说不：issue 面一字不动＋决定记录可回读。
        rejected = call("harness.path_candidate_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-r1"),
            "decision": {"candidateId": "r1", "action": "reject",
                         "reasonRef": href("reason", "r-reject-r1"),
                         "receiptRef": href("receipt", "rc-reject-r1")}})
        issues_after_reject = query(
            "SELECT COUNT(*) AS n FROM case_issues WHERE matter_id=?",
            (MATTER,))[0]["n"]
        r1_after = call("harness.path_candidate_read",
                        {"scope": SCOPE, "candidate_id": "r1"})["candidate"]
        self.step("c07_reject_leaves_issues_untouched",
                  rejected["issuesTouched"] == 0
                  and issues_after_reject == 1
                  and r1_after["state"] == "rejected"
                  and r1_after["adoptedIssueRef"] is None
                  and r1_after["decision"]["action"] == "reject",
                  issues=issues_after_reject, state=r1_after["state"])
        listing = call("harness.path_candidate_list", {"scope": SCOPE})
        self.step("c07_listing_state_counts",
                  listing["stateCounts"] == {"adopted": 1, "pending": 0,
                                             "rejected": 1},
                  counts=listing["stateCounts"])

        # ---- C08 决定态再决定拒（状态机闭集）。
        self.expect_error("c08_redecide_refused", lambda: call(
            "harness.path_candidate_decide", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("dec-again"),
                "decision": {"candidateId": "r1", "action": "adopt",
                             "reasonRef": href("reason", "r-y"),
                             "receiptRef": href("receipt", "rc-y"),
                             "issue": {"id": "issue-y", "revision": 1,
                                       "title": "y", "claimRefs": [],
                                       "factRefs": [], "partyIds": []}}}),
            "path_candidate_state_invalid:rejected")

        # ---- C09 新证据重评：weakened 带 JC basis＋undetermined 无 basis
        # （未知不伪支持）；无依据签增强拒；百分比类判定闭集外拒。
        delta = call("harness.assessment_delta_record", {
            "actor_id": "recon-assistant", "scope": SCOPE,
            "key": key("ad-1"),
            "delta": {"deltaId": "ad-1", "changeReason": "material",
                      "oldInputRefs": [href("material", "mat-e15")],
                      "newInputRefs": [href("material", "mat-e15v2")],
                      "items": [
                          {"kind": "fact", "ref": href("fact", "f-loss"),
                           "outcome": "weakened",
                           "reason": "新合成证据削弱损失数额认定",
                           "basisRefs": [{"owner": "jc", "kind": "issue-result",
                                          "id": "ir-1", "version": "1",
                                          "matterId": MATTER}]},
                          {"kind": "issue",
                           "ref": href("issue", "issue-restitution"),
                           "outcome": "undetermined",
                           "reason": "重评依赖未取得，未知不伪支持",
                           "basisRefs": []}],
                      "counterEvidenceRefs": [href("fact", "f-counter")],
                      "rescopeRefs": [href("artifact", "a-brief")],
                      "note": "全合成重评"}})
        outcomes = [item["outcome"] for item in delta["delta"]["delta"]["items"]]
        self.step("c09_delta_outcomes_recorded",
                  outcomes == ["weakened", "undetermined"], outcomes=outcomes)
        self.expect_error("c09_no_basis_strengthened_refused", lambda: call(
            "harness.assessment_delta_record", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("ad-nb"),
                "delta": {"deltaId": "ad-nb", "changeReason": "material",
                          "oldInputRefs": [href("material", "m1")],
                          "newInputRefs": [href("material", "m2")],
                          "items": [
                              {"kind": "fact", "ref": href("fact", "f-x"),
                               "outcome": "strengthened",
                               "reason": "无依据（合成反例）",
                               "basisRefs": []}]}}),
            "assessment_delta_basis_required:strengthened")
        self.expect_error("c09_percentage_outcome_refused", lambda: call(
            "harness.assessment_delta_record", {
                "actor_id": "recon-assistant", "scope": SCOPE,
                "key": key("ad-pc"),
                "delta": {"deltaId": "ad-pc", "changeReason": "material",
                          "oldInputRefs": [href("material", "m1")],
                          "newInputRefs": [href("material", "m2")],
                          "items": [
                              {"kind": "fact", "ref": href("fact", "f-x"),
                               "outcome": "improved_by_30pct",
                               "reason": "百分比代替法律判断（合成反例）",
                               "basisRefs": [href("reason", "r-z")]}]}}),
            "assessment_delta_outcome_invalid")

        # ---- C10 真实 JC 公开出口：evaluate 真跑＋read_argument_graph 读
        # 取（branchRefs 实测）→ 投影登记照实转录。
        jc_graph = self._jc_real_read(profile)
        projection = call("harness.branch_projection_record", {
            "actor_id": "recon-system", "scope": SCOPE, "key": key("bp-1"),
            "projection": {
                "projectionId": "bp-1",
                "jcRunRef": jc_graph["runRef"],
                "jcGraphRef": jc_graph["graphRef"],
                "profile": jc_graph["profile"],
                "inputRefs": [href("material", "mat-e15")],
                "branches": [{
                    "ref": branch_ref, "hypothesis": "合成分支假设",
                    "conclusion": "合成分支结论", "scope": jc_graph["profile"],
                } for branch_ref in jc_graph["branchRefs"]]}})
        view = projection["projection"]
        self.step("c10_jc_public_exit_transcribed_verbatim",
                  jc_graph["branchRefs"] == []
                  and view["hasBranches"] is False
                  and view["branchCount"] == 0
                  and view["branchRefs"] == []
                  and view["noBranchReason"]
                  == "jc_public_exit_branch_refs_empty"
                  and view["jcRunRef"]["owner"] == "jc"
                  and view["jcGraphRef"]["owner"] == "jc"
                  and view["profile"] == jc_graph["profile"],
                  noBranchReason=view["noBranchReason"],
                  profile=view["profile"])
        # 不由前端制造：harness 造的 branch ref 拒收。
        self.expect_error("c10_frontend_branch_ref_refused", lambda: call(
            "harness.branch_projection_record", {
                "actor_id": "recon-system", "scope": SCOPE,
                "key": key("bp-fake"),
                "projection": {"projectionId": "bp-fake",
                               "jcRunRef": jc_graph["runRef"],
                               "jcGraphRef": jc_graph["graphRef"],
                               "profile": jc_graph["profile"],
                               "branches": [{
                                   "ref": href("argument-node", "node-fake"),
                                   "hypothesis": "前端自造分支",
                                   "conclusion": "不得入账",
                                   "scope": "任意"}]}}),
            "branch_ref_owner_invalid")

        # ---- C11 DB 级扫描：三账行数＋issue 载荷窄字段＋事件行。
        candidates_db = query(
            "SELECT candidate_id, state FROM path_candidates"
            " WHERE matter_id=? ORDER BY candidate_id", (MATTER,))
        deltas_db = query(
            "SELECT COUNT(*) AS n FROM assessment_deltas WHERE matter_id=?",
            (MATTER,))[0]["n"]
        projections_db = query(
            "SELECT COUNT(*) AS n FROM branch_projections WHERE matter_id=?",
            (MATTER,))[0]["n"]
        failed_rows = query(
            "SELECT COUNT(*) AS n FROM path_candidates WHERE matter_id=?"
            " AND candidate_id IN ('r-stuff','r-noloc')", (MATTER,))[0]["n"]
        self.step("c11_db_level_scan",
                  [(row["candidate_id"], row["state"]) for row in candidates_db]
                  == [("r1", "rejected"), ("r2", "adopted")]
                  and deltas_db == 1 and projections_db == 1
                  and failed_rows == 0,
                  candidates=[(row["candidate_id"], row["state"])
                              for row in candidates_db],
                  deltas=deltas_db, projections=projections_db)

        # ---- C12 重评/投影回读面（matter 键控）。
        delta_read = call("harness.assessment_delta_read",
                          {"scope": SCOPE, "delta_id": "ad-1"})["delta"]
        projection_read = call("harness.branch_projection_read",
                               {"scope": SCOPE, "projection_id": "bp-1"}
                               )["projection"]
        self.step("c12_readback_faces",
                  delta_read["deltaId"] == "ad-1"
                  and projection_read["projectionId"] == "bp-1"
                  and call("harness.assessment_delta_list",
                           {"scope": SCOPE})["deltaCount"] == 1
                  and call("harness.branch_projection_list",
                           {"scope": SCOPE})["projectionCount"] == 1)

    def _jc_real_read(self, profile: str) -> dict:
        """真实 JC 公开出口读取：evaluate 真跑一次合成 run，然后
        read_argument_graph 取 branchRefs（04 证据 J client.py:1445 当前
        恒空——本对账实测钉定该事实，不宣称多解释已落地）。"""
        import test_p01_jc_wiring as p01
        with tempfile.TemporaryDirectory(prefix="juscite-e15-jc-") as tmp:
            config = p01._config(Path(tmp))
            queries = p01._issue_queries(config)
            result = legal_entry.call("jc.evaluate", {
                "bundle": {
                    "case_id": "e15-recon-case",
                    "decision_time": "2026-09-01T00:00:00Z",
                    "facts": [{"fact_key": "acc.contract"},
                              {"fact_key": "acc.exception"}],
                    "queries": queries,
                },
                "issue_queries": queries,
            }, config)
            if result["run_status"] != "success":
                raise AssertionError(
                    f"jc evaluate run_status={result['run_status']}")
            client = legal_entry._jc_client(config)
            graph = client.read_argument_graph(
                result["run_identity_ref"], case_id="e15-recon-case")
            # JC run_identity_ref 是 {kind, digest} 裸身份（非 wire ref 形）；
            # 入账按本合同 ref 词形转录（owner=jc·id=run digest hex）——
            # 原样标识同一 run，不改写不发明。
            run_digest = result["run_identity_ref"]["digest"]
            run_ref = {"owner": "jc", "kind": "run-identity",
                       "id": run_digest.removeprefix("sha256:"),
                       "version": "1", "matterId": MATTER}
            return {
                "runRef": run_ref,
                "graphRef": graph["graphRef"],
                "branchRefs": graph.get("branchRefs") or [],
                "profile": "SYNTHETIC-CONDITIONAL-PRINCIPAL/1",
            }

    def bridge_negatives(self, config):
        # ---- C13 桥负向：未配置/未知方法/方法组冻结。
        try:
            legal_entry.call("harness.path_candidate_register",
                             {"scope": SCOPE}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c13_bridge_not_configured",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.path_candidate_adopt",
                             {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c13_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c13_method_group_frozen",
                  legal_entry.HARNESS_PATH_EVIDENCE_METHODS == E15_METHODS)

    # -- profile drivers ---------------------------------------------------

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-e15-desktop-")
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
        store.create_matter(MATTER, "cas://profile-e15-recon")

        def call(method, args):
            return legal_entry.call(method, args, config)

        def query(sql, params):
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop", call, query)
        self.bridge_negatives(config)
        return 0

    def run_selfhost(self, dsn: str) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)
        import contextlib

        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-e15-selfhost-")
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="e15_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        bound = {name: resolve_provider_method(name, units)
                 for name in E15_METHODS}
        store.create_matter(MATTER, "cas://profile-e15-recon")

        def call(method, args):
            return bound[method](**args)

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        self.common_flow("selfhost", call, query)
        store.destroy()
        return 0


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> Path:
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" / "E15" \
        / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-e15-path-evidence-contract-recon/1",
        "unit": "W2b-U23",
        "feature": "E15",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w2b-u23",
        "harness_base": "w2b-u11@88bf1757 (w2a-u05→w2a-u06/F114→w2b-u01/F25→w2b-u11/F47)",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    (evidence_dir / "e15_path_evidence_contract_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    lines = [f"# E15 路径与新证据公开合同 recon（{profile}）",
             "",
             f"- unit: W2b-U23 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ branch w2b-u23"
             "（基 w2b-u11@88bf1757；master 929d0802 零动）",
             f"- started: {started} · finished: {finished}",
             "",
             "| # | check | status |",
             "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']}"
                     f" | {check['status']} |")
    lines += ["", "全部合成材料；desktop＝产品桥子进程全链（SQLite 状态根），"
              "selfhost＝PgMatterStore 直连 lh-pg-e08（同一封闭注册）；"
              "C10 的 branchRefs 经真实 JC 公开出口（jc.evaluate 真跑＋"
              "read_argument_graph 读取）实测为空，照实入账为该 run 无分支。"]
    (evidence_dir / "e15_path_evidence_contract_recon.md").write_text(
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
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    if not (JC_REPO / "compiler_core" / "client.py").is_file():
        print("RECON_BLOCKED: pinned JC checkout missing:", JC_REPO)
        return 3
    failures = 0
    first = True
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root)
        try:
            if first:
                # C01 分支/基/master/工作树干净/JC 钉亲验（只跑一次，两
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
