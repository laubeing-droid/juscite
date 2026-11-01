# -*- coding: utf-8 -*-
"""W4-U45 / F90 acceptance: ruleset / playbook review bridge + candidate ledger.

06:F90 (F90-desktop/F90-selfhost; owner manuals+product+jc; entries P04/P01;
17 card target = JC compiler_core/client.py public owner extension + real
rule packs, UI only calls/displays): the fixed playbook review walks a
versioned checklist entry by entry and returns the mandated per-entry
RISK / BASIS / DEVIATION triple, every verdict bound to the frozen W2b-U19
rule-pack locator + retrieved date; candidate rules carry the narrow
projection only and never become facts (the E15 path_candidates narrow-field
isomorphism — the single channel onward is an explicit decide/adopt with a
decision reference); deviation detection is re-derived by the independent
checker along a different arithmetic path and the receipt seals only on
agreement; entries without a deterministic check kind stay NOT_CHECKED with
a named reason (unknown preserved, never papered to 0); input/result refs
ride the receipt (inputDigest + playbookReviewRef owner=jc).

The JC review face (compiler_core.playbook_review + playbook_checker +
client.playbook_review_registry/review_playbook) is consumed read-only
through the pinned P01 JCClient surface at the JC w4-u45 branch head
(= W4-U25's delivered F90 commit 066ad59, independently re-verified in this
unit: 65 unit tests + 22 static-gate tests + the formal_e2e/mcp_protocol
acceptance suite all green on this exact tree). The deviations leg lands in
the harness deviation account through the P04 provider dispatch
(harness.record_deviation over the --goal-json closed envelope). All
materials are synthetic engineering fixtures; statutory constants are
asserted at their gazette values from the frozen packs.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry  # noqa: E402
import playbook_review  # noqa: E402

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus"
    r"\.local\worktrees\w4-u45")
JC_SHA256 = {
    "compiler_core/playbook_review.py":
        "cdaf35ea72651399be95e5c03b83169d306bf3d7a5406d29eef7372d6ee00bff",
    "compiler_core/playbook_checker.py":
        "ecee5b59cc5df3cff3e75f37a218273611cd200685067ac9bc6e482b65e59b23",
    "compiler_core/client.py":
        "6fb3423def9676c90d7fe1c61d503d26bcb56475f89b2274b179687abed84c88",
}
HARNESS_REPO = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo")
HARNESS_SHA256 = {
    "tools/workflow-tools/harness/public_entry.py":
        "b6b28863223ea4cf502449b64b635ca2c3f00a31179eaa98769caead962b5719",
    "src/legal_harness/business/units.py":
        "4a6c9860f60a0aeaa42da96263634a50c9fb7185502ffee05c3373f4695db6e2",
}

# 官方锚点（W2b-U19 冻结包 gazette 值；测试断言具名）：
#   C03 财产案件 1000 万标的受理费 = 230000 分（2300 元，481号令第13条）；
#   C04 保全费上限 = 500000 分（5000 元，481号令第14条封顶）；
#   C05 风险代理首档费率 = 0.18；婚姻继承案件不属于禁止风险代理闭集；
#   C06 贸仲立案费 100 万标的（表一 out）= 1000000 分。
OFFICIAL_C03_10M_MINOR = 230_000
OFFICIAL_C04_CAP_MINOR = 500_000
OFFICIAL_C05_BRACKET0_RATE = "0.18"
OFFICIAL_C06_OUT_1M_MINOR = 1_000_000
OFFICIAL_PACK_TITLE = "诉讼费用交纳办法（国务院令第481号）"
OFFICIAL_PACK_LOCATOR = \
    "http://gongbao.court.gov.cn/Details/d0faf211b7a8b0c57e4fc3daa78c36.html"

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


def _require_pins():
    if not (JC_REPO / "compiler_core" / "playbook_review.py").is_file():
        raise AssertionError(
            f"pinned JC w4-u45 worktree missing at {JC_REPO}; "
            "the F90 playbook review bridge cannot be verified")
    if not (HARNESS_REPO / "tools/workflow-tools/harness/public_entry.py").is_file():
        raise AssertionError(
            f"pinned harness construction checkout missing at {HARNESS_REPO}; "
            "the F90 deviations leg cannot be verified")


def _config(tmp_path=None, with_harness=True):
    _require_pins()
    if tmp_path is None:
        holder = tempfile.TemporaryDirectory()
        _ACTIVE_TMPDIRS.append(holder)
        tmp_path = Path(holder.name)
    elif isinstance(tmp_path, tempfile.TemporaryDirectory):
        tmp_path = Path(tmp_path.name)
    else:
        tmp_path = Path(tmp_path)
    rules = tmp_path / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    config = {
        "jc_state_root": str(tmp_path / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
        "playbook_state_root": str(tmp_path / "pstate"),
    }
    if with_harness:
        registration = tmp_path / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-wiring"}),
            encoding="utf-8")
        config.update({
            "harness_public_entry":
                str(HARNESS_REPO / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(tmp_path / "hstate"),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
        })
    return config


def _run_cli(method, args, config):
    """真产品入口子进程径（legal_entry CLI；同族 recon 纪律）。"""
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(HERE / "python" / "legal_entry.py"),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


def _entries_conformed():
    """一条与冻结包完全一致的 active 行（值与依据俱真）。"""
    return [{
        "entryId": "chk-c03",
        "claim": "财产案件 1000 万标的受理费应收 2300 元（481号令第13条）",
        "status": "active",
        "check": {"kind": "computed_fee", "family": "C03",
                  "input": {"case_category": "property",
                            "amount_minor": 10_000_000},
                  "claimedAmountMinor": OFFICIAL_C03_10M_MINOR},
        "claimedSource": {"title": OFFICIAL_PACK_TITLE,
                          "locator": OFFICIAL_PACK_LOCATOR},
    }]


class F90PlaybookReviewWiringTests(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        while _ACTIVE_TMPDIRS:
            _ACTIVE_TMPDIRS.pop().cleanup()

    # -- 冻结面 ------------------------------------------------------------

    def test_frozen_method_groups(self):
        self.assertEqual(sorted(legal_entry.PLAYBOOK_REVIEW_METHODS), [
            "playbook.adopt", "playbook.candidates", "playbook.deviations_record",
            "playbook.registry", "playbook.review"])
        self.assertEqual(sorted(legal_entry.HARNESS_PLAYBOOK_METHODS), [
            "harness.read_playbook", "harness.record_deviation",
            "harness.select_playbook"])
        # 既有同族冻结组零动（F90 是 calc.* 家族的新成员，不改旧组）。
        self.assertIn("calc.rule_pack_delta", legal_entry.RULE_PACK_GOVERNANCE_METHODS)

    def test_pinned_worktree_sha_matches(self):
        _require_pins()
        for relative, expected in JC_SHA256.items():
            digest = hashlib_sha256(JC_REPO / relative)
            self.assertEqual(digest, expected, f"JC {relative} drifted from the pin")
        for relative, expected in HARNESS_SHA256.items():
            digest = hashlib_sha256(HARNESS_REPO / relative)
            self.assertEqual(digest, expected,
                             f"harness {relative} drifted from the pin")

    def test_registry_freeze_document(self):
        config = _config()
        code, out = _run_cli("playbook.registry", {}, config)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.get("status"), "OWNER_RESPONSE")
        doc = out["result"]
        self.assertEqual(doc["registry_version"], "playbook-review/1")
        self.assertEqual(doc["receipt_schema_version"], "jc-playbook-review/1")
        # 输入域闭集（17 卡：冻结具名输入域）
        self.assertEqual(doc["input_domain"]["request_fields"],
                         ["playbookId", "playbookVersion", "entries"])
        self.assertEqual(doc["input_domain"]["entry_statuses"],
                         ["active", "candidate"])
        # 风险映射闭集（逐条风险核）
        self.assertEqual(sorted(doc["risk_map"]), ["basis", "none", "unchecked", "value"])
        self.assertEqual(doc["risk_map"]["unchecked"]["level"], "REVIEW_REQUIRED")
        # 权威包逐槽带官方 locator+retrieved（E21 冻结面）
        packs = doc["authority_packs"]
        self.assertEqual(sorted(packs), ["C03", "C04", "C05", "C06"])
        for slot, pack in packs.items():
            source = pack["source"]
            self.assertTrue(pack["pack_version"], f"{slot} pack_version missing")
            self.assertTrue(source["locator"], f"{slot} locator missing")
            self.assertTrue(source["retrieved"], f"{slot} retrieved missing")
        # 候选纪律与封章规则在冻结文档具名
        self.assertIn("never facts", doc["candidate_rules"]["principle"])
        self.assertIn("checker agreement", doc["seal_rule"])

    # -- 逐条判定 ----------------------------------------------------------

    def test_review_sealed_conformed_entry_low(self):
        config = _config()
        code, out = _run_cli(
            "playbook.review",
            {"playbook_id": "pb-acceptance", "playbook_version": "v1",
             "entries": _entries_conformed()}, config)
        self.assertEqual(code, 0, out)
        receipt = out["result"]["receipt"]
        self.assertIs(receipt["sealed"], True)
        self.assertIsNotNone(receipt.get("inputDigest"))
        self.assertEqual(receipt["playbookReviewRef"]["owner"], "jc")
        row = receipt["reviews"][0]
        self.assertEqual(row["risk"]["level"], "LOW")
        self.assertEqual(row["risk"]["reasons"], ["consistent_with_official_pack"])
        self.assertEqual(row["basis"]["status"], "OFFICIAL_PACK")
        self.assertEqual(row["basis"]["pack"], "C03")
        # 判定结果绑定规则版本 locator（E21 冻结面）
        self.assertTrue(row["locator"])
        self.assertEqual(row["locator"], row["basis"]["locator"])
        self.assertTrue(row["basis"]["retrieved"])
        self.assertEqual(row["deviations"], [])
        self.assertEqual(row["authorityValue"], OFFICIAL_C03_10M_MINOR)
        self.assertEqual(receipt["counts"]["noDeviation"], 1)
        # 评审记录落状态根（deviations_record / 候选账可回读）
        self.assertTrue(out["result"]["reviewId"])
        self.assertEqual(out["result"]["reviewRef"]["owner"], "jc")

    def test_review_value_and_basis_deviations(self):
        config = _config()
        entries = [{
            "entryId": "chk-bad-value",
            "claim": "保全费上限 5000 分",
            "status": "active",
            "check": {"kind": "cap_minor", "pack": "C04",
                      "claimedCapMinor": 5000},
        }, {
            "entryId": "chk-bad-basis",
            "claim": "风险代理首档费率 18%",
            "status": "active",
            "check": {"kind": "ladder_rate", "pack": "C05", "bracketIndex": 0,
                      "claimedRate": OFFICIAL_C05_BRACKET0_RATE},
            "claimedSource": {"title": "诉讼费用交纳办法",
                              "locator": "example.invalid/wrong-locator"},
        }]
        code, out = _run_cli("playbook.review",
                             {"playbook_id": "pb", "playbook_version": "v1",
                              "entries": entries}, config)
        self.assertEqual(code, 0, out)
        rows = {r["entryId"]: r for r in out["result"]["receipt"]["reviews"]}
        # 值偏差 → HIGH + expected/actual 具名（权威值 500000 分＝5000 元）
        value_row = rows["chk-bad-value"]
        self.assertEqual(value_row["risk"]["level"], "HIGH")
        kinds = [d["kind"] for d in value_row["deviations"]]
        self.assertEqual(kinds, ["value"])
        self.assertEqual(value_row["deviations"][0]["expected"],
                         OFFICIAL_C04_CAP_MINOR)
        # 依据偏差 → 值全对但依据错（title＋locator 均异）→ MEDIUM
        basis_row = rows["chk-bad-basis"]
        self.assertEqual(basis_row["risk"]["level"], "MEDIUM")
        kinds = [d["kind"] for d in basis_row["deviations"]]
        self.assertEqual(kinds, ["basis", "basis"])
        self.assertTrue(any("locator" in d["detail"] for d in basis_row["deviations"]))

    def test_review_not_checked_preserved(self):
        config = _config()
        entries = [{
            "entryId": "chk-manual",
            "claim": "证据链完整性需人工判断",
            "status": "active",
        }]
        code, out = _run_cli("playbook.review",
                             {"playbook_id": "pb", "playbook_version": "v1",
                              "entries": entries}, config)
        self.assertEqual(code, 0, out)
        receipt = out["result"]["receipt"]
        row = receipt["reviews"][0]
        self.assertEqual(row["risk"]["level"], "REVIEW_REQUIRED")
        self.assertEqual(row["risk"]["reasons"],
                         ["no_deterministic_check_for_entry"])
        self.assertEqual(row["verdictSource"], "not_checked")
        self.assertIsNone(row["locator"])
        self.assertEqual(row["deviations"], [])
        self.assertEqual(receipt["counts"]["notChecked"], 1)
        # 缺值/未知规则＝UNKNOWN fail-closed 不补 0：无任何伪造判定字段
        self.assertNotIn("authorityValue", row)

    def test_review_candidate_narrow_projection(self):
        config = _config()
        entries = _entries_conformed() + [
            {"entryId": "cand-1", "claim": "建议增加执行时限核查项",
             "status": "candidate", "candidateReason": "无确定性检查类"}]
        code, out = _run_cli("playbook.review",
                             {"playbook_id": "pb", "playbook_version": "v1",
                              "entries": entries}, config)
        self.assertEqual(code, 0, out)
        receipt = out["result"]["receipt"]
        self.assertEqual(receipt["counts"]["candidates"], 1)
        self.assertEqual(receipt["candidates"], [{
            "entryId": "cand-1", "claim": "建议增加执行时限核查项",
            "status": "candidate", "note": "candidate_rule_not_a_fact",
            "candidateReason": "无确定性检查类"}])
        # 候选自动入候选账（窄投影＋回执溯源），同回执重放幂等
        ledger = out["result"]["candidateLedger"]
        self.assertTrue(ledger["recorded"][0]["recorded"])
        code, out2 = _run_cli("playbook.review",
                              {"playbook_id": "pb", "playbook_version": "v1",
                               "entries": entries}, config)
        self.assertEqual(code, 0, out2)
        self.assertFalse(out2["result"]["candidateLedger"]["recorded"][0]["recorded"])
        code, view = _run_cli("playbook.candidates", {}, config)
        self.assertEqual(code, 0, view)
        rows = view["result"]["candidates"]
        self.assertEqual(view["result"]["counts"],
                         {"total": 1, "pending": 1, "adopted": 0, "rejected": 0})
        row = rows[0]
        self.assertEqual(row["status"], "candidate")
        self.assertEqual(row["reviewRef"]["owner"], "jc")
        # 候选账零判定形状字段（结构性不是事实）
        for verdict_field in ("risk", "basis", "deviation", "deviations",
                              "certified", "verdict", "check", "claimed_source"):
            self.assertNotIn(verdict_field, row)

    def test_candidate_ledger_field_closure(self):
        """候选行携 verdict 形字段＝窄闭集具名拒（E15 同构；单元级 seam）。"""
        holder = tempfile.TemporaryDirectory()
        _ACTIVE_TMPDIRS.append(holder)
        root = Path(holder.name)
        from bridge_errors import NotConnected
        with self.assertRaises(NotConnected) as caught:
            playbook_review._record_candidate(
                root, {"entryId": "x", "claim": "c", "risk": {"level": "LOW"}},
                "pb", "v1", "deadbeef",
                {"owner": "jc", "kind": "playbook-review", "id": "x",
                 "digest": "sha256:x"})
        self.assertIn("playbook_candidate_field_not_closed", str(caught.exception))

    # -- 显式 decide 通道 ---------------------------------------------------

    def test_adopt_explicit_channel_and_idempotency(self):
        config = _config()
        entries = _entries_conformed() + [
            {"entryId": "cand-2", "claim": "建议增加管辖异议核查项",
             "status": "candidate", "candidateReason": "待律师定"}]
        code, out = _run_cli("playbook.review",
                             {"playbook_id": "pb", "playbook_version": "v1",
                              "entries": entries}, config)
        self.assertEqual(code, 0, out)
        code, view = _run_cli("playbook.candidates", {}, config)
        cid = view["result"]["candidates"][0]["candidateId"]
        decision_ref = {"owner": "lawyer", "kind": "decision", "id": "d-42"}
        # 无 decisionRef 不签决定
        code, out = _run_cli("playbook.adopt",
                             {"candidate_id": cid, "decision": "adopt"},
                             config)
        self.assertEqual(code, 3, out)
        self.assertIn("playbook_decision_ref_required", str(out.get("code")))
        # 非法决定值
        code, out = _run_cli("playbook.adopt",
                             {"candidate_id": cid, "decision": "maybe",
                              "decision_ref": decision_ref}, config)
        self.assertEqual(code, 3, out)
        self.assertIn("playbook_decision_invalid", str(out.get("code")))
        # 未知候选
        code, out = _run_cli("playbook.adopt",
                             {"candidate_id": "cand-nope", "decision": "adopt",
                              "decision_ref": decision_ref}, config)
        self.assertEqual(code, 3, out)
        self.assertIn("playbook_candidate_not_found", str(out.get("code")))
        # 显式采纳 → adopted＋采纳非判定申明
        code, out = _run_cli("playbook.adopt",
                             {"candidate_id": cid, "decision": "adopt",
                              "decision_ref": decision_ref}, config)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["result"]["decision"], "adopt")
        self.assertFalse(out["result"]["replay"])
        self.assertIn("adopted_rule_not_a_verdict", out["result"]["note"])
        code, view = _run_cli("playbook.candidates", {}, config)
        self.assertEqual(view["result"]["counts"],
                         {"total": 1, "pending": 0, "adopted": 1, "rejected": 0})
        # 同内容重放幂等；异决定 conflict 具名拒
        code, out = _run_cli("playbook.adopt",
                             {"candidate_id": cid, "decision": "adopt",
                              "decision_ref": decision_ref}, config)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["result"]["replay"])
        code, out = _run_cli("playbook.adopt",
                             {"candidate_id": cid, "decision": "reject",
                              "decision_ref": decision_ref}, config)
        self.assertEqual(code, 3, out)
        self.assertIn("playbook_decision_conflict", str(out.get("code")))

    # -- P04 偏差账 --------------------------------------------------------

    def _create_harness_matter(self, matter_id: str, config: dict) -> None:
        """案件准入是 harness 的既有公开面（E18 先例：测试夹具显式建案件，
        桥绝不隐式造案件）。"""
        sys.path.insert(0, str(HARNESS_REPO / "src"))
        for _name in [m for m in list(sys.modules)
                      if m == "legal_harness" or m.startswith("legal_harness.")]:
            del sys.modules[_name]
        from legal_harness.state.matter_store import MatterStore
        MatterStore(Path(config["harness_state_root"])).create_matter(
            matter_id, "cas://profile-f90-wiring")

    def test_deviations_record_p04_leg(self):
        config = _config()
        matter_id = "m-f90-wiring"
        self._create_harness_matter(matter_id, config)
        entries = [{
            "entryId": "chk-dev", "claim": "诉讼费算错 100 元",
            "status": "active",
            "check": {"kind": "computed_fee", "family": "C03",
                      "input": {"case_category": "property",
                                "amount_minor": 10_000_000},
                      "claimedAmountMinor": OFFICIAL_C03_10M_MINOR - 10_000},
        }, {
            "entryId": "chk-unknown", "claim": "证据链完整性需人工判断",
            "status": "active",
        }]
        code, out = _run_cli("playbook.review",
                             {"playbook_id": "pb", "playbook_version": "v1",
                              "matter_id": matter_id, "entries": entries},
                             config)
        self.assertEqual(code, 0, out)
        review_id = out["result"]["reviewId"]
        code, rec = _run_cli("playbook.deviations_record",
                             {"review_id": review_id}, config)
        self.assertEqual(code, 0, rec)
        self.assertEqual(rec.get("status"), "OWNER_RESPONSE")
        recorded = rec["result"]["recorded"]
        self.assertEqual([r["entryId"] for r in recorded], ["chk-dev", "chk-unknown"])
        self.assertEqual(recorded[0]["deviationKinds"], ["value"])
        self.assertEqual(recorded[0]["riskLevel"], "HIGH")
        # NOT_CHECKED 行以 REVIEW_REQUIRED 落账（unknown 不静默消失）
        self.assertEqual(recorded[1]["kind"], "not_checked")
        self.assertEqual(recorded[1]["deviationKinds"], ["REVIEW_REQUIRED"])
        for row in recorded:
            ref = row["deviationRef"]
            self.assertEqual(ref.get("owner"), "harness")
            self.assertEqual(ref.get("kind"), "deviation")
            self.assertTrue(ref.get("id"))
        # deterministic requestId 重放＝同 deviation id（CommandKey 幂等）
        code, rec2 = _run_cli("playbook.deviations_record",
                              {"review_id": review_id}, config)
        self.assertEqual(code, 0, rec2)
        self.assertEqual([r["deviationRef"]["id"] for r in rec2["result"]["recorded"]],
                         [r["deviationRef"]["id"] for r in recorded])

    def test_deviations_record_empty_review(self):
        config = _config()
        matter_id = "m-f90-wiring-empty"
        self._create_harness_matter(matter_id, config)
        code, out = _run_cli("playbook.review",
                             {"playbook_id": "pb", "playbook_version": "v1",
                              "matter_id": matter_id,
                              "entries": _entries_conformed()}, config)
        self.assertEqual(code, 0, out)
        review_id = out["result"]["reviewId"]
        code, rec = _run_cli("playbook.deviations_record",
                             {"review_id": review_id}, config)
        self.assertEqual(code, 0, rec)
        self.assertEqual(rec["result"]["recorded"], [])
        self.assertEqual(rec["result"]["counts"]["recorded"], 0)

    # -- fail-closed -------------------------------------------------------

    def test_bridge_fail_closed(self):
        config = _config()
        del config["playbook_state_root"]
        code, out = _run_cli("playbook.review",
                             {"playbook_id": "pb", "playbook_version": "v1",
                              "entries": _entries_conformed()}, config)
        self.assertEqual(code, 3, out)
        self.assertIn("playbook_state_root_not_configured", str(out.get("code")))
        # 未知 playbook 方法（冻结组外一律 fail-closed）
        code, out = _run_cli("playbook.nope", {}, _config())
        self.assertEqual(code, 3, out)
        self.assertIn("method_not_connected:playbook.nope", str(out.get("code")))
        # JC typed 拒：float 金额入参（F89 纪律）→ JC_FAILURE 携码 exit 4
        entries = [{"entryId": "bad", "claim": "c", "status": "active",
                    "check": {"kind": "cap_minor", "pack": "C04",
                              "claimedCapMinor": 5000.5}}]
        code, out = _run_cli("playbook.review",
                             {"playbook_id": "pb", "playbook_version": "v1",
                              "entries": entries}, _config())
        self.assertEqual(code, 4, out)
        self.assertEqual(out.get("status"), "JC_FAILURE")
        self.assertIn("playbook_float_input_refused", str(out.get("code")))
        # JC typed 拒：候选携判定字段（JC 侧先拒）
        entries = [{"entryId": "cand-x", "claim": "c", "status": "candidate",
                    "risk": {"level": "LOW"}}]
        code, out = _run_cli("playbook.review",
                             {"playbook_id": "pb", "playbook_version": "v1",
                              "entries": entries}, _config())
        self.assertEqual(code, 4, out)
        self.assertIn("playbook_candidate_verdict_field_refused",
                      str(out.get("code")))
        # deviations_record：未知 review id
        code, out = _run_cli("playbook.deviations_record",
                             {"review_id": "nope"}, _config())
        self.assertEqual(code, 3, out)
        self.assertIn("playbook_review_not_found", str(out.get("code")))


def hashlib_sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
