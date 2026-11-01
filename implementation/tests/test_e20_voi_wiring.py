# -*- coding: utf-8 -*-
"""W2b-U53+W4-U56 / E20 acceptance: VOI, multi-interpretation, line bridge.

07 E20 (B2 segment + B4 segment) + 08 section 3 five-scenario row:
* the bridge exposes exactly the frozen VOI method pair (jc.voi_analyze,
  jc.checkpoint_line) through the pinned P01 JCClient surface — unknown
  methods never reach the cores and missing jc config fails
  NOT_CONNECTED;
* probabilities are never request input: the probabilitySource carries
  exactly two owner=jc receipt refs (E19 readiness + checkpoint
  probability receipt); a readiness gap returns the named unavailable
  receipt with a null value (never 0.5 / risk 1 / unified rate); a
  complete evidence set plus a registered checkpoint receipt yields the
  exact rational VOI;
* multi-interpretation branches are transcribed owner=jc from the
  argument graph public exit (E15 branch_projection contract) — the
  front end never fabricates them;
* B4 (W4-U56): the checkpoint production line registers a real trained
  checkpoint (train_and_save on synthetic rows) and binds calibration
  evidence into readiness-consumable rows; a synthetic-data checkpoint
  is stamped usableForRealCasePrediction=false; without a checkpoint
  document the named model_not_available receipt is the answer; the
  line never emits a whole-case proof.

All materials below are synthetic engineering fixtures. The bridge
consumes the pinned JC w4-u56 worktree (a superset of the w2b-u53 E20
chain head) — no second authority.
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
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w4-u56")

# Runtime face pinning (W2a-U16 discipline): the whole pytest process must
# resolve compiler_core to THIS wave's JC worktree. w4-u56 is a superset
# of the w2b-u53 chain head (calc_families + prediction_separation +
# voi_analysis + checkpoint_line).
if (JC_REPO / "compiler_core" / "checkpoint_line.py").is_file():
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

DIMENSIONS = ("sample_selection", "label_definition", "time_window",
              "case_family", "time_migration_calibration",
              "jurisdiction_migration_calibration", "calibration_report",
              "leakage_audit")

RECORDS = [
    {"materialId": "m-samp", "jurisdiction": "ZJ", "courtId": "H01",
     "courtLevel": "first", "decisionDate": "2024-06-01",
     "sourceTier": "local_court", "factualDifference": "合成：损失认定同构",
     "declaredUse": "prediction_sample", "datasetVersion": "ds-synth-1"},
]
FRAME = {
    "sampleFrameId": "sf-synth-1", "targetCourt": "H01",
    "targetJurisdiction": "ZJ", "caseFamily": "买卖合同纠纷（合成）",
    "labelDefinition": "一审全部诉请获支持（合成标签）",
    "timeWindowStart": "2023-01-01", "timeWindowEnd": "2024-12-31",
    "datasetVersion": "ds-synth-1", "admittedRowIds": ["m-samp"],
}
TARGET = {"targetCourt": "H01", "targetJurisdiction": "ZJ",
          "evaluationTime": "2026-10-17"}

VOI_REQUEST = {
    "decisionId": "dec-e20-wiring",
    "worldStates": ["win", "lose"],
    "informationSets": [
        {"informationSetId": "I-win", "stateIds": ["win"]},
        {"informationSetId": "I-lose", "stateIds": ["lose"]},
    ],
    "actions": ["settle", "litigate"],
    "payoffs": [
        {"actionId": "settle", "stateId": "win", "netMinor": 3_000_000},
        {"actionId": "settle", "stateId": "lose", "netMinor": 3_000_000},
        {"actionId": "litigate", "stateId": "win", "netMinor": 10_000_000},
        {"actionId": "litigate", "stateId": "lose", "netMinor": -2_000_000},
    ],
    "costOfInformationMinor": 500_000,
}


def _all_evidence():
    return {d: {"evidenceId": f"ev-{d}", "note": "合成证据引用"}
            for d in DIMENSIONS}


_ACTIVE_TMPDIRS = []


def _config(tmp_path=None):
    if not (JC_REPO / "compiler_core" / "checkpoint_line.py").is_file():
        raise AssertionError(
            f"pinned JC w4-u56 worktree missing at {JC_REPO}; the E20 VOI "
            "bridge cannot be verified")
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


def _expect_owner(test, method, args, config):
    code, out = _run_cli(method, args, config)
    test.assertEqual(code, 0, f"{method} exit {code}: {out}")
    test.assertEqual(out.get("status"), "OWNER_RESPONSE")
    return out.get("result", {})


def _expect_typed(test, method, args, config, fragment):
    code, out = _run_cli(method, args, config)
    test.assertEqual(code, 4, f"{method} expected JC_FAILURE, exit {code}")
    test.assertEqual(out.get("status"), "JC_FAILURE")
    test.assertIn(fragment, str(out.get("code", "")))
    return out


class TestMethodGroupFrozen(unittest.TestCase):
    def test_frozen_method_group(self):
        self.assertEqual(legal_entry.VOI_ANALYSIS_METHODS,
                         frozenset({"jc.voi_analyze",
                                    "jc.checkpoint_line"}))

    def test_unknown_voi_method_not_connected(self):
        code, out = _run_cli("jc.voi_evaluate", {}, _config())
        self.assertEqual(code, 3)
        self.assertEqual(out.get("status"), "NOT_CONNECTED")

    def test_harness_voi_group_frozen(self):
        self.assertEqual(legal_entry.HARNESS_VOI_METHODS, frozenset({
            "harness.voi_request_register", "harness.voi_receipt_record",
            "harness.voi_read", "harness.voi_list"}))

    def test_unconfigured_fails_closed(self):
        code, out = _run_cli(
            "jc.voi_analyze",
            {"request": VOI_REQUEST, "readiness": {}}, {})
        self.assertEqual(code, 3)
        self.assertEqual(out.get("status"), "NOT_CONNECTED")

    def test_missing_readiness_payload_not_connected(self):
        code, out = _run_cli("jc.voi_analyze", {"request": VOI_REQUEST},
                             _config())
        self.assertEqual(code, 3)
        self.assertIn("voi_readiness_payload_required",
                      str(out.get("code", "")))

    def test_complete_evidence_without_checkpoint_refused(self):
        # 证据齐全但没有 checkpoint 概率回执＝无法算 VOI——桥面具名拒，
        # 不静默 unavailable 也不造数。
        code, out = _run_cli(
            "jc.voi_analyze",
            {"matterId": "m-e20", "request": VOI_REQUEST,
             "readiness": {"frame": FRAME, "records": RECORDS,
                            "target": TARGET, "evidence": _all_evidence()}},
            _config())
        self.assertEqual(code, 4)
        self.assertEqual(out.get("status"), "JC_FAILURE")
        self.assertIn("voi_checkpoint_receipt_required",
                      str(out.get("code", "")))


class TestVoiBridgeRealChain(unittest.TestCase):
    """真产品入口子进程径：合成证据 → JC 面真算（U27 recon 纪律）。"""

    @classmethod
    def setUpClass(cls):
        cls.config = _config()

    def _register(self, kind, payload):
        return _register_via_client(self.config, kind, payload)

    def test_readiness_gap_named_unavailable(self):
        gaps = _expect_owner(
            self, "prediction.readiness",
            {"matterId": "m-e20",
             "request": {"frame": FRAME, "records": RECORDS,
                         "target": TARGET, "evidence": {}}},
            self.config)
        self.assertFalse(gaps["predictionKnown"])
        checkpoint = {
            "kind": "probability-prediction",
            "checkpointId": "ckpt-synth-e20",
            "eventDefinition": "target-court-win（合成）",
            "perStateProbabilities": {"win": "0.6", "lose": "0.4"},
        }
        result = _expect_owner(
            self, "jc.voi_analyze",
            {"matterId": "m-e20",
             "request": VOI_REQUEST,
             "readiness": {"frame": FRAME, "records": RECORDS,
                            "target": TARGET, "evidence": {}},
             "checkpointProbability": checkpoint},
            self.config)
        self.assertFalse(result["voiKnown"])
        self.assertEqual(result["unavailableReason"],
                         "prediction_readiness_incomplete")
        self.assertEqual(result["missingScopes"], list(DIMENSIONS))
        self.assertIsNone(result["voi"])
        self.assertIsNone(result["probability"])
        self.assertTrue(result["noProbabilityNoVoi"])
        self.assertEqual(result["voiReceiptRef"]["owner"], "jc")

    def test_known_path_exact_rational_voi(self):
        ready = _expect_owner(
            self, "prediction.readiness",
            {"matterId": "m-e20",
             "request": {"frame": FRAME, "records": RECORDS,
                         "target": TARGET, "evidence": _all_evidence()}},
            self.config)
        self.assertTrue(ready["predictionKnown"])
        self.assertIsNone(ready["probability"])
        checkpoint = {
            "kind": "probability-prediction",
            "checkpointId": "ckpt-synth-e20",
            "eventDefinition": "target-court-win（合成）",
            "perStateProbabilities": {"win": "0.6", "lose": "0.4"},
        }
        result = _expect_owner(
            self, "jc.voi_analyze",
            {"matterId": "m-e20",
             "request": VOI_REQUEST,
             "readiness": {"frame": FRAME, "records": RECORDS,
                            "target": TARGET,
                            "evidence": _all_evidence()},
             "checkpointProbability": checkpoint},
            self.config)
        self.assertTrue(result["voiKnown"])
        self.assertEqual(result["valueUnit"], "minor")
        self.assertEqual(result["baseline"]["action"], "litigate")
        self.assertEqual(result["voi"],
                         {"numerator": 1_500_000, "denominator": 1,
                          "isInteger": True})
        self.assertIsNone(result["probability"])
        self.assertEqual(result["voiReceiptRef"]["owner"], "jc")

    _CHECKPOINT = {
        "kind": "probability-prediction",
        "checkpointId": "ckpt-synth-e20",
        "eventDefinition": "target-court-win（合成）",
        "perStateProbabilities": {"win": "0.6", "lose": "0.4"},
    }

    def _voi_args(self, **request_overrides):
        return {"matterId": "m-e20",
                "request": dict(VOI_REQUEST, **request_overrides),
                "readiness": {"frame": FRAME, "records": RECORDS,
                               "target": TARGET,
                               "evidence": _all_evidence()},
                "checkpointProbability": dict(self._CHECKPOINT)}

    def _voi_args_checkpoint(self, checkpoint):
        return {"matterId": "m-e20",
                "request": dict(VOI_REQUEST),
                "readiness": {"frame": FRAME, "records": RECORDS,
                               "target": TARGET,
                               "evidence": _all_evidence()},
                "checkpointProbability": checkpoint}

    def test_fabricated_probability_shape_refused_typed(self):
        # 与 E19 同源编造扫描：统一胜率/风险参数 1 在闭集外即具名拒。
        _expect_typed(
            self, "jc.voi_analyze", self._voi_args(unifiedCourtRate="0.62"),
            self.config, "probability_placeholder_refused")
        _expect_typed(
            self, "jc.voi_analyze", self._voi_args(riskParameter="1"),
            self.config, "probability_placeholder_refused")

    def test_checkpoint_probability_discipline(self):
        # 概率回执载荷缺 checkpointId——checkpoint 面转录不完整具名拒。
        bad = dict(self._CHECKPOINT)
        del bad["checkpointId"]
        _expect_typed(
            self, "jc.voi_analyze", self._voi_args_checkpoint(bad),
            self.config, "voi_probability_checkpoint_required")
        # 概率和不恰为 1——十进制精确归一具名拒。
        bad = dict(self._CHECKPOINT,
                   perStateProbabilities={"win": "0.6", "lose": "0.3"})
        _expect_typed(
            self, "jc.voi_analyze", self._voi_args_checkpoint(bad),
            self.config, "voi_probability_not_normalized")
        # 分数串概率不是 checkpoint 面的交换形状。
        bad = dict(self._CHECKPOINT,
                   perStateProbabilities={"win": "3/5", "lose": "2/5"})
        _expect_typed(
            self, "jc.voi_analyze", self._voi_args_checkpoint(bad),
            self.config, "voi_probability_shape_invalid")

    def test_non_minor_payoff_refused_typed(self):
        payoffs = list(VOI_REQUEST["payoffs"])
        payoffs[0] = dict(payoffs[0], netMinor=3000000.5)
        _expect_typed(
            self, "jc.voi_analyze", self._voi_args(payoffs=payoffs),
            self.config, "voi_payoff_not_minor_units")

    def test_partition_overlap_refused_typed(self):
        _expect_typed(
            self, "jc.voi_analyze",
            self._voi_args(informationSets=[
                {"informationSetId": "I-1", "stateIds": ["win", "lose"]},
                {"informationSetId": "I-2", "stateIds": ["win"]}]),
            self.config, "voi_partition_overlap")


def _train_synthetic_checkpoint():
    """真实训练真跑（子进程隔离于钉定 JC worktree；固定合成行零随机）：
    产线输入＝train_and_save 产物 checkpoint+evaluation 两文档。"""
    script = """
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from compiler_core.prediction import train_and_save


def row(index, signal, noise, label):
    return {"features": {"f_signal": signal, "f_noise": noise},
            "label": label}


split = {
    "train": [row(1, 2.0, 0.1, 1), row(2, -1.5, 0.3, 0),
              row(3, 1.2, -0.2, 1), row(4, -0.8, 0.0, 0),
              row(5, 0.9, 0.4, 1), row(6, -1.1, -0.3, 0),
              row(7, 1.6, 0.2, 1), row(8, -1.8, 0.1, 0)],
    "dev": [row(9, 1.4, 0.0, 1), row(10, -1.2, 0.2, 0),
            row(11, 0.7, -0.1, 1), row(12, -0.6, 0.3, 0)],
    "test": [row(13, 1.9, 0.2, 1), row(14, -1.4, -0.2, 0),
             row(15, 0.4, 0.1, 1), row(16, -0.9, 0.0, 0)],
}
rows = split["train"] + split["dev"] + split["test"]
with tempfile.TemporaryDirectory(prefix="jc-line-train-") as tmp:
    result = train_and_save(
        Path(tmp), event_definition="target-court-win（合成）",
        rows=rows, feature_order=["f_signal", "f_noise"],
        split_rows=split,
        model_config={"epochs": 120, "learningRate": 0.3, "l2": 1e-3},
        data_version="ds-synth-e20b4", rule_version=None)
print(json.dumps({"checkpoint": result["checkpoint"],
                  "evaluation": result["evaluation"]},
                 ensure_ascii=False))
"""
    raw = subprocess.check_output(
        [sys.executable, "-X", "utf8", "-B", "-c", script, str(JC_REPO)],
        encoding="utf-8")
    return json.loads(raw.strip().splitlines()[-1])


class TestCheckpointLineBridge(unittest.TestCase):
    """B4 段（W4-U56）：产线桥真产品入口子进程径。"""

    @classmethod
    def setUpClass(cls):
        cls.config = _config()
        cls.trained = _train_synthetic_checkpoint()

    def _line_args(self, **overrides):
        request = {
            "checkpoint": self.trained["checkpoint"],
            "evaluation": self.trained["evaluation"],
            "worldStates": ["win", "lose"],
            "perStateProbabilities": {"win": "0.6", "lose": "0.4"},
            "boundEvidence": {
                "time_migration_calibration": {"evidenceId": "cal-t-2023"},
                "jurisdiction_migration_calibration": {
                    "evidenceId": "cal-j-zj"},
            },
            "dataProvenance": "synthetic_mechanism_demo",
        }
        request.update(overrides)
        return {"matterId": "m-e20", "request": request}

    def test_line_registers_trained_checkpoint_owner_jc(self):
        receipt = _expect_owner(self, "jc.checkpoint_line",
                                self._line_args(), self.config)
        self.assertTrue(receipt["checkpointRegistered"])
        self.assertEqual(receipt["checkpointLineRef"]["owner"], "jc")
        self.assertEqual(receipt["checkpointLineRef"]["kind"],
                         "checkpoint-line")
        self.assertEqual(receipt["probabilityReceiptRef"]["owner"], "jc")
        probability = receipt["probabilityReceipt"]
        self.assertEqual(probability["kind"], "probability-prediction")
        self.assertEqual(probability["checkpointId"],
                         self.trained["checkpoint"]["checkpoint_id"])
        self.assertEqual(probability["perStateProbabilities"],
                         {"win": "0.6", "lose": "0.4"})
        self.assertTrue(probability["boundToTrainedCheckpoint"])
        self.assertFalse(receipt["usableForRealCasePrediction"])
        self.assertFalse(receipt["wholeCaseProof"]["provenByLine"])
        # 产线概率回执直接喂 VOI 桥＝数值路径全链（真实训练产物驱动）。
        result = _expect_owner(
            self, "jc.voi_analyze",
            {"matterId": "m-e20",
             "request": VOI_REQUEST,
             "readiness": {"frame": FRAME, "records": RECORDS,
                            "target": TARGET,
                            "evidence": _all_evidence()},
             "checkpointProbability": probability},
            self.config)
        self.assertTrue(result["voiKnown"])
        self.assertEqual(result["voi"],
                         {"numerator": 1_500_000, "denominator": 1,
                          "isInteger": True})

    def test_line_without_checkpoint_named_unavailable(self):
        receipt = _expect_owner(
            self, "jc.checkpoint_line",
            {"matterId": "m-e20",
             "request": {"worldStates": ["win", "lose"],
                         "perStateProbabilities": {"win": "0.6",
                                                   "lose": "0.4"},
                         "dataProvenance": "synthetic_mechanism_demo"}},
            self.config)
        self.assertFalse(receipt["checkpointRegistered"])
        self.assertEqual(receipt["unavailableReason"], "model_not_available")
        self.assertIsNone(receipt["probabilityReceipt"])
        self.assertEqual(receipt["evidenceBindings"], {})
        self.assertIsNone(receipt["probability"])

    def test_line_fabrications_refused_typed(self):
        # 概率不归一。
        _expect_typed(
            self, "jc.checkpoint_line",
            self._line_args(
                perStateProbabilities={"win": "0.6", "lose": "0.3"}),
            self.config, "checkpoint_line_probability_not_normalized")
        # 统一胜率塞值。
        _expect_typed(
            self, "jc.checkpoint_line",
            self._line_args(winRate="0.62"),
            self.config, "probability_placeholder_refused")
        # 风险参数 1。
        _expect_typed(
            self, "jc.checkpoint_line",
            self._line_args(riskParameter="1"),
            self.config, "probability_placeholder_refused")
        # 数据侧维绝不产线生产。
        _expect_typed(
            self, "jc.checkpoint_line",
            self._line_args(boundEvidence={
                "sample_selection": {"evidenceId": "fake"}}),
            self.config, "checkpoint_line_dimension_not_producible")
        # 授权缺一即拒（真实法院数据＝授权族 fail-closed）。
        _expect_typed(
            self, "jc.checkpoint_line",
            self._line_args(
                dataProvenance="authorized_real_court_data"),
            self.config, "real_court_data_authorization_missing")


if __name__ == "__main__":
    unittest.main()
