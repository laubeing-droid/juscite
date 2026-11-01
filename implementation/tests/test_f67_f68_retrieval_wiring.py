"""W2b-U57 (F67+F68): the retrieval-order constitution audited at the bridge.

Positives run the real in-process bridge (legal_entry.call) against the real
cases public face on this wave's pinned cases worktree (JUSCITE_CASES_ROOT
override; same discipline as conftest's anonymizer resolution). The
receipt-missing negative runs the REAL bridge subprocess against the frozen
pre-extension checkout pinned in 14-Python入口证据.csv (P08 sha256
38c1959c…, verified in-test) — an honest provider that genuinely lacks the
receipt; the bridge must named-reject it, never fabricate. All corpus
material is synthetic.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "python"))
sys.path.insert(0, str(HERE.parent))

REPO_ROOT = HERE.parents[2]                       # juscite worktree root
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
ENTRY_CSV = REPO_ROOT / "docs" / "construction" / "authority" / "14-Python入口证据.csv"

import hashlib
import os

from legal_entry import call, CaseProviderError, _audit_retrieval_order  # noqa: E402
from test_p05_p08_cases_wiring import env, _pinned_entries  # noqa: E402

RECEIPT_SCHEMA = "lcr.retrieval-order/1"
CONSTITUTION = "local_free_then_paid_no_skip_level"
LADDER = ("local_corpus", "cncases_full", "paid_legal_api", "court_case_library")
UNTRIED_REASONS = {"not_authorized", "adapter_not_implemented", "failed_upstream"}

_CONFIG = None


def config():
    global _CONFIG
    if _CONFIG is None:
        e = env()
        _CONFIG = {"cases_root": e["cfg"]["root"],
                   "cases_import_path": str(e["cases_root"]),
                   "cases_dataset_version": e["dataset_version"],
                   "cases_index_version": e["index_version"]}
    return _CONFIG


def _search_args(text="还款", execution=None):
    args = {"query": {"mode": "text", "text": text}, "filters": {}}
    if execution is not None:
        args["execution"] = execution
    return args


class BridgeOrderReceiptTests(unittest.TestCase):
    def test_bridge_forces_order_ledger_without_caller_optin(self):
        result = call("case.search", _search_args(), config())
        receipt = result["retrievalOrder"]
        self.assertEqual(receipt["schema"], RECEIPT_SCHEMA)
        self.assertEqual(receipt["constitution"], CONSTITUTION)
        self.assertEqual([s["sourceId"] for s in receipt["sources"]], list(LADDER))
        local = receipt["sources"][0]
        self.assertEqual(local["tier"], "local_free")
        self.assertEqual(local["status"], "tried")
        self.assertIsNone(local["reason"])
        for entry in receipt["sources"][1:]:
            self.assertEqual(entry["status"], "skipped")
            self.assertEqual(entry["reason"], "not_authorized")
        self.assertFalse(receipt["hitsExhaustive"])
        self.assertTrue(result["hits"], "real hits from the real synthetic corpus")

    def test_two_runs_identical_hit_sequence(self):
        first = call("case.search", _search_args(), config())
        second = call("case.search", _search_args(), config())
        ids_first = [h["locator"]["canonicalDocId"] for h in first["hits"]]
        ids_second = [h["locator"]["canonicalDocId"] for h in second["hits"]]
        self.assertEqual(ids_first, ids_second, "same query must score identically twice")
        self.assertTrue(ids_first)

    def test_require_exhaustive_named_reject_through_bridge(self):
        with self.assertRaises(CaseProviderError) as ctx:
            call("case.search", _search_args(execution={"requireExhaustive": True}), config())
        self.assertEqual(ctx.exception.code, "exhaustive_unachievable_source_untried")

    def test_caller_order_tamper_named_reject_through_bridge(self):
        with self.assertRaises(CaseProviderError) as ctx:
            call("case.search", _search_args(execution={"order": ["cncases_full"]}), config())
        self.assertEqual(ctx.exception.code, "search_order_violation")

    def test_zero_hit_claim_named_reject_through_bridge(self):
        with self.assertRaises(CaseProviderError) as ctx:
            call("case.search", _search_args(text="查无此案的词毫无处",
                                             execution={"zeroHitAuthoritative": True}), config())
        self.assertEqual(ctx.exception.code, "zero_hit_not_authoritative_source_untried")

    def test_authorized_without_adapter_named_failed_through_bridge(self):
        runtime_json = Path(config()["cases_root"]) / "runtime.json"
        saved = runtime_json.read_text(encoding="utf-8")
        body = json.loads(saved)
        body["paid_sources_authorized"] = ["cncases_full"]
        runtime_json.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        try:
            result = call("case.search", _search_args(), config())
            by_id = {s["sourceId"]: s for s in result["retrievalOrder"]["sources"]}
            self.assertEqual(by_id["cncases_full"]["status"], "failed")
            self.assertEqual(by_id["cncases_full"]["reason"], "adapter_not_implemented")
        finally:
            runtime_json.write_text(saved, encoding="utf-8")


class AuditFunctionNegativeTests(unittest.TestCase):
    """Hermetic payload-level negatives for the bridge receipt auditor."""

    def _audit(self, result, require_exhaustive=False):
        _audit_retrieval_order(result, RECEIPT_SCHEMA, CONSTITUTION,
                               [{"sourceId": s} for s in LADDER], UNTRIED_REASONS,
                               require_exhaustive)

    @staticmethod
    def _good_receipt(hits=None, untried=True):
        paid = ({"sourceId": "cncases_full", "tier": "paid", "feeRequired": True,
                 "status": "skipped", "reason": "not_authorized", "hits": 0, "elapsedMs": 0.0},
                {"sourceId": "paid_legal_api", "tier": "paid", "feeRequired": True,
                 "status": "skipped", "reason": "not_authorized", "hits": 0, "elapsedMs": 0.0},
                {"sourceId": "court_case_library", "tier": "paid", "feeRequired": True,
                 "status": "skipped", "reason": "not_authorized", "hits": 0, "elapsedMs": 0.0})
        return {"schema": RECEIPT_SCHEMA, "constitution": CONSTITUTION,
                "sources": [{"sourceId": "local_corpus", "tier": "local_free",
                             "feeRequired": False, "status": "tried", "reason": None,
                             "hits": 3, "elapsedMs": 1.0}] + list(paid),
                "hitsExhaustive": not untried, "zeroHitAuthoritative": False}

    def test_missing_receipt_named(self):
        with self.assertRaises(CaseProviderError) as ctx:
            self._audit({"schema": "lcr.search/4", "hits": []})
        self.assertEqual(ctx.exception.code, "case_search_order_receipt_missing")

    def test_wrong_schema_or_constitution_named(self):
        for key in ("schema", "constitution"):
            receipt = self._good_receipt()
            receipt[key] = "tampered"
            with self.assertRaises(CaseProviderError) as ctx:
                self._audit({"hits": [], "retrievalOrder": receipt})
            self.assertEqual(ctx.exception.code, "case_search_order_receipt_invalid", key)

    def test_reordered_ladder_named(self):
        receipt = self._good_receipt()
        receipt["sources"].reverse()
        with self.assertRaises(CaseProviderError) as ctx:
            self._audit({"hits": [], "retrievalOrder": receipt})
        self.assertEqual(ctx.exception.code, "case_search_order_receipt_invalid")

    def test_local_not_tried_named(self):
        receipt = self._good_receipt()
        receipt["sources"][0]["status"] = "failed"
        with self.assertRaises(CaseProviderError) as ctx:
            self._audit({"hits": [], "retrievalOrder": receipt})
        self.assertEqual(ctx.exception.code, "case_search_order_receipt_invalid")

    def test_reason_outside_closed_set_named(self):
        receipt = self._good_receipt()
        receipt["sources"][1]["reason"] = "frozen_out_by_budget"   # not in the closed set
        with self.assertRaises(CaseProviderError) as ctx:
            self._audit({"hits": [], "retrievalOrder": receipt})
        self.assertEqual(ctx.exception.code, "case_search_order_receipt_invalid")

    def test_require_exhaustive_echo_mismatch_named(self):
        with self.assertRaises(CaseProviderError) as ctx:
            self._audit({"hits": [], "retrievalOrder": self._good_receipt(untried=True)},
                        require_exhaustive=True)
        self.assertEqual(ctx.exception.code, "case_search_order_receipt_invalid")

    def test_zero_hit_authoritative_mismatch_named(self):
        receipt = self._good_receipt(untried=True)
        receipt["zeroHitAuthoritative"] = True   # claims corpus-wide zero while untried
        with self.assertRaises(CaseProviderError) as ctx:
            self._audit({"hits": [], "retrievalOrder": receipt})
        self.assertEqual(ctx.exception.code, "case_search_order_receipt_invalid")


class FrozenBaseReceiptMissingSubprocessTests(unittest.TestCase):
    def test_pre_extension_checkout_named_rejected_real_subprocess(self):
        """The frozen base checkout (P08 pin) genuinely lacks the receipt; the
        real bridge subprocess must named-reject it instead of fabricating."""
        pin_path, pin_sha = _pinned_entries()["P08"]
        self.assertEqual(hashlib.sha256(Path(pin_path).read_bytes()).hexdigest(), pin_sha,
                         "frozen-base checkout drifted from the P08 pin")
        frozen_root = str(Path(pin_path).parents[1])
        cfg = dict(config(), cases_import_path=frozen_root)
        request = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        json.dump({"method": "case.search", "args": _search_args()}, request, ensure_ascii=False)
        request.close()
        cfg_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        json.dump(cfg, cfg_file, ensure_ascii=False)
        cfg_file.close()
        try:
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
                 "--request-json", request.name, "--config", cfg_file.name],
                capture_output=True, text=True, encoding="utf-8",
                timeout=300, cwd=str(REPO_ROOT))
            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "NOT_CONNECTED")
            self.assertTrue(payload["code"].startswith("cases_public_facade_missing_retrieval_order"),
                            payload["code"])
        finally:
            os.unlink(request.name)
            os.unlink(cfg_file.name)


if __name__ == "__main__":
    unittest.main()
