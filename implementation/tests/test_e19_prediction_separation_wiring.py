# -*- coding: utf-8 -*-
"""W2b-U27+W4-U55 / E19 acceptance: separation bridge + B4 calibration.

07 E19 (B2 segment; deps E15/E22) + 04 sections 1/8, extended by the
W4-U55 B4 segment:
* court materials declared for normative use never join a prediction
  sample — sample membership is an explicit frame admission, and even an
  explicit admission of a normative-use material is refused typed;
* the target-court readiness audit names every missing migration /
  calibration / leakage scope and never carries a probability (no model
  means no fabricated probability — default 50%, neutral risk parameter
  one, and a court unified win rate are all refused);
* retrieval scores are stamped not-win-rate; planting one into a
  probability-shaped field is a typed refusal;
* B4: the time/jurisdiction migration calibration pipeline actually
  runs on synthetic rows (exact-rational per-bin diagnostics), a
  synthetic receipt is stamped usableAsRealCalibrationEvidence=false,
  and an authorized_real_court_data request without a non-empty
  authorization attestation is refused typed (real court data is an
  authorized-source family — fail-closed, never fabricated).

All materials below are synthetic engineering fixtures. The bridge
consumes the pinned JC w4-u55 worktree (a superset of the w2b-u27 E19
chain head) through the P01 JCClient surface — no second authority, and
the cases repo is never written.
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

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w4-u55")

# Runtime face pinning (W2a-U16 discipline): the whole pytest process must
# resolve compiler_core to THIS wave's JC worktree. w4-u55 is a superset
# of the w2b-u27 chain head (prediction_separation + calibration_transfer),
# so both faces stay importable; the reverse order (main face first) would
# lack both modules.
if (JC_REPO / "compiler_core" / "prediction_separation.py").is_file():
    sys.path.insert(0, str(JC_REPO))
    for _name in [m for m in list(sys.modules)
                  if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[_name]

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

RECORDS = [
    {   # 本地法院材料，规范理由用途（合成）。
        "materialId": "m-norm-local",
        "jurisdiction": "ZJ", "courtId": "H01", "courtLevel": "first",
        "decisionDate": "2024-05-01", "sourceTier": "local_court",
        "factualDifference": "合成事实差异：无书面合同",
        "declaredUse": "normative_reference", "datasetVersion": "ds-synth-1",
    },
    {   # 最高法指导材料，规范理由用途（合成）——提高权威层级不产生胜率。
        "materialId": "m-norm-supreme",
        "jurisdiction": "SC", "courtId": "SPC", "courtLevel": "retrial",
        "decisionDate": "2023-11-11", "sourceTier": "supreme_guidance",
        "factualDifference": "合成事实差异：程序阶段不同",
        "declaredUse": "normative_reference", "datasetVersion": "ds-synth-1",
    },
    {   # 邻省经验总体用途（合成）。
        "materialId": "m-emp-neighbor",
        "jurisdiction": "JS", "courtId": "H02", "courtLevel": "second",
        "decisionDate": "2023-01-15", "sourceTier": "neighboring_province",
        "factualDifference": "合成事实差异：辖区不同",
        "declaredUse": "empirical_population", "datasetVersion": "ds-synth-1",
    },
    {   # 样本用途材料（合成）——唯一可显式 admission 的行。
        "materialId": "m-samp",
        "jurisdiction": "ZJ", "courtId": "H01", "courtLevel": "first",
        "decisionDate": "2024-06-01", "sourceTier": "local_court",
        "factualDifference": "合成事实差异：损失认定同构",
        "declaredUse": "prediction_sample", "datasetVersion": "ds-synth-1",
    },
]

FRAME = {
    "sampleFrameId": "sf-synth-1", "targetCourt": "H01",
    "targetJurisdiction": "ZJ", "caseFamily": "买卖合同纠纷（合成）",
    "labelDefinition": "一审全部诉请获支持（合成标签）",
    "timeWindowStart": "2023-01-01", "timeWindowEnd": "2024-12-31",
    "datasetVersion": "ds-synth-1", "admittedRowIds": ["m-samp"],
}

TARGET = {"targetCourt": "H01", "targetJurisdiction": "ZJ",
          "evaluationTime": "2026-10-16"}

DIMENSIONS = ("sample_selection", "label_definition", "time_window",
              "case_family", "time_migration_calibration",
              "jurisdiction_migration_calibration", "calibration_report",
              "leakage_audit")


def _all_evidence():
    return {d: {"evidenceId": f"ev-{d}", "note": "合成证据引用"}
            for d in DIMENSIONS}


_ACTIVE_TMPDIRS = []


def _config(tmp_path=None):
    if not (JC_REPO / "compiler_core" / "prediction_separation.py").is_file():
        raise AssertionError(
            f"pinned JC w2b-u27 worktree missing at {JC_REPO}; the E19 "
            "separation bridge cannot be verified")
    if tmp_path is None:
        holder = tempfile.TemporaryDirectory()
        _ACTIVE_TMPDIRS.append(holder)
        tmp_path = Path(holder.name)
    else:
        tmp_path = Path(tmp_path)
    rules = tmp_path / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8")
    return {
        "jc_state_root": str(tmp_path / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
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


class TestMethodGroupFrozen(unittest.TestCase):
    def test_frozen_method_group(self):
        self.assertEqual(legal_entry.PREDICTION_SEPARATION_METHODS, frozenset({
            "prediction.declare", "prediction.readiness",
            "prediction.retrieval_guard", "prediction.calibration_transfer"}))

    def test_unknown_prediction_method_not_connected(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("prediction.win_rate", {}, _config())
        self.assertIn("method_not_connected", str(ctx.exception))


class TestDeclareFace(unittest.TestCase):
    def test_declare_counts_and_never_admits(self):
        code, out = _run_cli("prediction.declare",
                             {"matterId": "m-e19", "records": RECORDS},
                             _config())
        self.assertEqual(code, 0, out)
        self.assertEqual(out["status"], "OWNER_RESPONSE")
        result = out["result"]
        self.assertEqual(result["declaredCount"], 4)
        self.assertEqual(result["useCounts"], {
            "normative_reference": 2, "empirical_population": 1,
            "prediction_sample": 1})
        # 结构性：声明面永不产出样本成员资格。
        self.assertFalse(result["declaresSampleMembership"])
        # 回执 ref owner=jc（不由前端制造）。
        self.assertEqual(result["declarationRef"]["owner"], "jc")

    def test_declare_extra_fields_typed_refusal(self):
        stuffed = dict(RECORDS[0], winProbabilityHint="0.9")
        code, out = _run_cli("prediction.declare",
                             {"matterId": "m-e19", "records": [stuffed]},
                             _config())
        self.assertEqual(code, 4, out)
        self.assertEqual(out["status"], "JC_FAILURE")
        self.assertIn("reference_fields_not_closed", out["code"])

    def test_unconfigured_fails_closed(self):
        code, out = _run_cli("prediction.declare", {"records": RECORDS}, {})
        self.assertEqual(code, 3, out)
        self.assertEqual(out["status"], "NOT_CONNECTED")


class TestReadinessFace(unittest.TestCase):
    def test_separation_counts_and_named_gaps(self):
        code, out = _run_cli("prediction.readiness", {
            "matterId": "m-e19",
            "request": {"frame": FRAME, "records": RECORDS,
                        "target": TARGET, "evidence": {}},
        }, _config())
        self.assertEqual(code, 0, out)
        result = out["result"]
        separation = result["separation"]
        # 4 声明 1 入样：规范/经验用途材料不在样本。
        self.assertEqual(separation["declaredCount"], 4)
        self.assertEqual(separation["admittedSampleRowCount"], 1)
        self.assertEqual(separation["declaredNotInSample"], 3)
        self.assertTrue(separation["normativeUseNeverAutoAdmitted"])
        # 八维证据全缺＝具名缺口，预测 unknown，无概率。
        self.assertFalse(result["predictionKnown"])
        self.assertEqual(result["missingScopes"], list(DIMENSIONS))
        self.assertIsNone(result["probability"])

    def test_complete_evidence_still_no_probability(self):
        code, out = _run_cli("prediction.readiness", {
            "matterId": "m-e19",
            "request": {"frame": FRAME, "records": RECORDS,
                        "target": TARGET, "evidence": _all_evidence()},
        }, _config())
        self.assertEqual(code, 0, out)
        result = out["result"]
        self.assertTrue(result["predictionKnown"])
        self.assertEqual(result["missingScopes"], [])
        self.assertIsNone(result["probability"])
        self.assertTrue(result["noModelNoProbability"])
        self.assertEqual(result["readinessRef"]["owner"], "jc")

    def test_normative_admission_refused_typed(self):
        frame = dict(FRAME, admittedRowIds=["m-norm-local"])
        code, out = _run_cli("prediction.readiness", {
            "matterId": "m-e19",
            "request": {"frame": frame, "records": RECORDS,
                        "target": TARGET, "evidence": _all_evidence()},
        }, _config())
        self.assertEqual(code, 4, out)
        self.assertEqual(out["status"], "JC_FAILURE")
        self.assertIn("prediction_admission_use_conflict", out["code"])

    def test_frame_fact_missing_refused_per_field(self):
        frame = dict(FRAME)
        frame["labelDefinition"] = ""
        code, out = _run_cli("prediction.readiness", {
            "matterId": "m-e19",
            "request": {"frame": frame, "records": RECORDS,
                        "target": TARGET, "evidence": _all_evidence()},
        }, _config())
        self.assertEqual(code, 4, out)
        self.assertIn("prediction_frame_required:labelDefinition", out["code"])

    def test_default_half_refused_nested(self):
        code, out = _run_cli("prediction.readiness", {
            "matterId": "m-e19",
            "request": {"frame": FRAME, "records": RECORDS,
                        "target": dict(TARGET, priorProbability="0.5"),
                        "evidence": _all_evidence()},
        }, _config())
        self.assertEqual(code, 4, out)
        self.assertIn("probability_placeholder_refused", out["code"])

    def test_unified_court_rate_refused(self):
        code, out = _run_cli("prediction.readiness", {
            "matterId": "m-e19",
            "request": {"frame": FRAME, "records": RECORDS,
                        "target": dict(TARGET, unifiedCourtRate="0.62"),
                        "evidence": _all_evidence()},
        }, _config())
        self.assertEqual(code, 4, out)
        self.assertIn("probability_placeholder_refused", out["code"])

    def test_bridge_input_shapes(self):
        # request 非 dict＝NOT_CONNECTED（桥层校验，不进 JC）。
        code, out = _run_cli("prediction.readiness",
                             {"matterId": "m-e19", "request": "blob"},
                             _config())
        self.assertEqual(code, 3, out)
        self.assertEqual(out["status"], "NOT_CONNECTED")
        self.assertIn("prediction_readiness_input_required", out["code"])


class TestRetrievalGuardFace(unittest.TestCase):
    def test_hits_stamped_not_win_rate(self):
        code, out = _run_cli("prediction.retrieval_guard", {
            "matterId": "m-e19",
            "hits": [
                {"hitId": "h-1", "retrievalScore": "0.92",
                 "canonicalDocId": "doc-1"},
                {"hitId": "h-2", "retrievalScore": "12.5"},
            ],
            "datasetVersion": "ds-synth-1", "indexVersion": "ix-synth-1",
        }, _config())
        self.assertEqual(code, 0, out)
        result = out["result"]
        self.assertFalse(result["retrievalScoreUsableAsWinRate"])
        self.assertIsNone(result["probability"])
        first, second = result["hits"]
        self.assertEqual(first["retrievalScore"], "0.92")
        self.assertTrue(first["retrievalScoreIsNotWinRate"])
        self.assertTrue(first["notAPopulationSample"])
        self.assertIsNone(first["probability"])
        self.assertEqual(second["retrievalScore"], "12.5")
        self.assertEqual(result["guardRef"]["owner"], "jc")

    def test_score_planted_as_win_rate_refused(self):
        code, out = _run_cli("prediction.retrieval_guard", {
            "matterId": "m-e19",
            "hits": [{"hitId": "h-1", "retrievalScore": "0.92",
                      "winRate": "0.92"}],
        }, _config())
        self.assertEqual(code, 4, out)
        self.assertEqual(out["status"], "JC_FAILURE")
        self.assertIn("retrieval_score_used_as_win_rate", out["code"])

    def test_guard_request_shape_accepted(self):
        # request 形态同 hits 直塞（桥接受两种入参形态，同一 JC 面）。
        code, out = _run_cli("prediction.retrieval_guard", {
            "matterId": "m-e19",
            "request": {"hits": [{"hitId": "h-1",
                                  "retrievalScore": "0.5"}]},
        }, _config())
        self.assertEqual(code, 0, out)
        self.assertTrue(out["result"]["hits"][0]["retrievalScoreIsNotWinRate"])

    def test_guard_bad_input_shape_not_connected(self):
        code, out = _run_cli("prediction.retrieval_guard",
                             {"matterId": "m-e19", "hits": "blob"},
                             _config())
        self.assertEqual(code, 3, out)
        self.assertIn("prediction_guard_input_required", out["code"])


CAL_ROWS = [
    {"rowId": "r-1", "predictedScore": "0.8", "observedLabel": 1,
     "decisionDate": "2023-06-01", "jurisdiction": "ZJ"},
    {"rowId": "r-2", "predictedScore": "0.4", "observedLabel": 0,
     "decisionDate": "2023-06-02", "jurisdiction": "ZJ"},
    {"rowId": "r-3", "predictedScore": "0.6", "observedLabel": 1,
     "decisionDate": "2024-06-01", "jurisdiction": "JS"},
    {"rowId": "r-4", "predictedScore": "0.2", "observedLabel": 0,
     "decisionDate": "2024-06-02", "jurisdiction": "JS"},
]

CAL_REQUEST = {
    "sampleFrameId": "sf-synth-b4", "targetCourt": "H01",
    "targetJurisdiction": "ZJ", "caseFamily": "买卖合同纠纷（合成）",
    "datasetVersion": "ds-synth-b4", "rows": CAL_ROWS,
    "timeBins": [
        {"binId": "t-2023", "start": "2023-01-01", "end": "2023-12-31"},
        {"binId": "t-2024", "start": "2024-01-01", "end": "2024-12-31"},
    ],
    "jurisdictionBins": [
        {"binId": "j-target", "jurisdictions": ["ZJ"]},
        {"binId": "j-neighbour", "jurisdictions": ["JS"]},
    ],
    "dataProvenance": "synthetic_mechanism_demo",
}


class TestCalibrationTransferFace(unittest.TestCase):
    """W4-U55 B4 段：两轴迁移校准计算框架真跑＋出处闭集负测。"""

    def test_synthetic_pipeline_runs_exact_diagnostics(self):
        code, out = _run_cli("prediction.calibration_transfer", {
            "matterId": "m-e19", "request": CAL_REQUEST,
        }, _config())
        self.assertEqual(code, 0, out)
        result = out["result"]
        self.assertEqual(result["schema_version"], "jc-calibration-transfer/1")
        # t-2023 箱：0.8/1 胜＋0.4/0 负 → 均值 3/5、频率 1/2、差 -1/10。
        t2023 = result["timeMigration"]["bins"][0]
        self.assertEqual(t2023["rowCount"], 2)
        self.assertEqual(t2023["meanPredictedScore"],
                         {"numerator": 3, "denominator": 5,
                          "isInteger": False})
        self.assertEqual(t2023["observedFrequency"],
                         {"numerator": 1, "denominator": 2,
                          "isInteger": False})
        self.assertEqual(t2023["calibrationGap"],
                         {"numerator": -1, "denominator": 10,
                          "isInteger": False})
        self.assertEqual(result["jurisdictionMigration"]["bins"][0]["rowCount"], 2)
        self.assertEqual(result["calibrationTransferRef"]["owner"], "jc")

    def test_synthetic_receipt_never_usable_as_real_evidence(self):
        code, out = _run_cli("prediction.calibration_transfer", {
            "matterId": "m-e19", "request": CAL_REQUEST,
        }, _config())
        self.assertEqual(code, 0, out)
        result = out["result"]
        self.assertTrue(result["syntheticMechanismDemo"])
        self.assertFalse(result["realDataAuthorized"])
        self.assertFalse(result["usableAsRealCalibrationEvidence"])
        self.assertIsNone(result["probability"])
        self.assertTrue(result["noModelNoProbability"])

    def test_real_data_without_authorization_refused_typed(self):
        request = dict(CAL_REQUEST,
                       dataProvenance="authorized_real_court_data")
        code, out = _run_cli("prediction.calibration_transfer", {
            "matterId": "m-e19", "request": request,
        }, _config())
        self.assertEqual(code, 4, out)
        self.assertEqual(out["status"], "JC_FAILURE")
        self.assertIn("real_court_data_authorization_missing", out["code"])

    def test_unknown_provenance_refused_typed(self):
        code, out = _run_cli("prediction.calibration_transfer", {
            "matterId": "m-e19",
            "request": dict(CAL_REQUEST, dataProvenance="scraped_web_dump"),
        }, _config())
        self.assertEqual(code, 4, out)
        self.assertIn("calibration_provenance_invalid", out["code"])

    def test_planted_win_rate_field_refused(self):
        row = dict(CAL_ROWS[0], winRate="0.92")
        code, out = _run_cli("prediction.calibration_transfer", {
            "matterId": "m-e19",
            "request": dict(CAL_REQUEST, rows=[row]),
        }, _config())
        self.assertEqual(code, 4, out)
        self.assertIn("probability_placeholder_refused", out["code"])

    def test_float_score_refused_formal_face(self):
        row = dict(CAL_ROWS[0], predictedScore=0.75)
        code, out = _run_cli("prediction.calibration_transfer", {
            "matterId": "m-e19",
            "request": dict(CAL_REQUEST, rows=[row]),
        }, _config())
        self.assertEqual(code, 4, out)
        self.assertIn("calibration_row_score_invalid", out["code"])

    def test_calibration_does_not_clear_readiness_gaps(self):
        # 合成校准回执不是 readiness 证据：时间/辖区迁移校准两维仍具名缺口。
        evidence = {d: {"evidenceId": f"ev-{d}"} for d in DIMENSIONS
                    if d not in ("time_migration_calibration",
                                 "jurisdiction_migration_calibration")}
        code, out = _run_cli("prediction.readiness", {
            "matterId": "m-e19",
            "request": {"frame": FRAME, "records": RECORDS,
                        "target": TARGET, "evidence": evidence},
        }, _config())
        self.assertEqual(code, 0, out)
        result = out["result"]
        self.assertFalse(result["predictionKnown"])
        self.assertEqual(result["missingScopes"],
                         ["time_migration_calibration",
                          "jurisdiction_migration_calibration"])
        self.assertIsNone(result["probability"])

    def test_bridge_input_shape_not_connected(self):
        code, out = _run_cli("prediction.calibration_transfer",
                             {"matterId": "m-e19", "request": "blob"},
                             _config())
        self.assertEqual(code, 3, out)
        self.assertEqual(out["status"], "NOT_CONNECTED")
        self.assertIn("prediction_calibration_input_required", out["code"])


if __name__ == "__main__":
    unittest.main()
