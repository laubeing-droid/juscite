"""W4-U42 (F72): the court-case-library tiering face wired through the bridge.

Positives run the real in-process bridge (legal_entry.call) against the
pinned cases branch delivery bced7c9 (lcr/caselib.py carrier + public_facade
_execute_caselib; independently re-verified in this unit: full cases pytest
166 passed on that exact tree). caselib.search must go through case.search
(F68 ladder + receipt audited at the bridge, caller cannot unsubscribe);
the caseLibrary additive block is audited for the E19-conformant stamp class
and the product projection carries the scoreSemantics stamp
(retrievalScoreIsNotWinRate family). Three-tier readback (guiding/included/
ordinary-classified/unknown) binds to dataset/indexVersion pins; a web-page
declaration never signs an official tier. Unauthorized state = the honest
negative (skipped/not_authorized, block absent, nothing fabricated); the
config domain has zero endpoint keys (W4-U03 N2 same standard). The
frozen-base negative runs the REAL bridge subprocess against the P08-pinned
pre-F72 checkout — it must named-reject, never fall back silently. All
corpus material is synthetic.
"""
import ast
import hashlib
import json
import os
import csv
import gzip
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "python"))

REPO_ROOT = HERE.parents[2]                       # juscite worktree root
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
ENTRY_CSV = REPO_ROOT / "docs" / "construction" / "authority" / "14-Python入口证据.csv"

# W4-U45 precedent: consume the parallel unit's committed delivery through a
# unit-named pin branch/worktree (w4-u42 == bced7c9, zero new commits),
# independently re-verified before consumption.
CASES_WT = Path(
    r"D:\Codex\1.法律工作区\legal-cn-cases工作区\legal-cn-cases"
    r"\.local\worktrees\w4-u42")
CASES_MAIN = Path(
    r"D:\Codex\1.法律工作区\legal-cn-cases工作区\legal-cn-cases")
CASES_DELIVERY_COMMIT = "bced7c94b2319b0e41ead425ff3f3d8b10dfafc2"
CASES_E19_PIN_COMMIT = "916ddf5d26fa798f0931eb8b27c758a8e7eca8e1"
CASES_SHA256 = {
    "lcr/caselib.py":
        "c1e1356a7fa947bae70544ee8eefd9db09b3bcf885b8039b17458308432a90f9",
    "lcr/public_facade.py":
        "e0a3bcf41d72e5b2b8d2ffaf728d70604080dafe3e9bc0f386deca927174ce9a",
}
PRODUCT_FACE = REPO_ROOT / "implementation" / "python" / "court_case_library.py"

LADDER = ("local_corpus", "cncases_full", "paid_legal_api", "court_case_library")

FIELDS = ['canonical_doc_id', 'doc_text', 'source_version', 'cause', 'judge_date', 'court_id',
          'court_name_norm', 'case_no_norm', 'case_class', 'trial_prog', 'court_level',
          'region_prov', 'region_city', 'case_result', 'year']

# 合成语料（工程夹具，非真实裁判；覆盖三分层四形态）。
CASLIB_RECORDS = [
    {"docId": "CASLIB-SYN-G1",
     "docText": "【合成语料，非真实裁判】指导性案例要点：借款合同还款义务与利息认定。",
     "caseNo": "(2026)合指1号", "courtName": "合成高级法院", "judgeDate": "2026-01-10",
     "tierDeclaration": {"tier": "guiding_case",
                         "source": "caselib_official_declaration",
                         "evidenceRef": "synth-official-decl-g1"},
     "provenance": [{"kind": "caselib_official_declaration",
                     "ref": "synth-official-g1"}]},
    {"docId": "CASLIB-SYN-I1",
     "docText": "【合成语料，非真实裁判】入库案例要点：违约金调整的还款抵充顺序。",
     "caseNo": "(2026)合入2号", "courtName": "合成中级法院", "judgeDate": "2026-01-20",
     "tierDeclaration": {"tier": "included_case",
                         "source": "caselib_official_declaration",
                         "evidenceRef": "synth-official-decl-i1"}},

    {"docId": "CASLIB-SYN-O1",
     "docText": "【合成语料，非真实裁判】普通裁判文书：还款计划争议与逾期责任。",
     "caseNo": "(2026)合民3号", "courtName": "合成基层法院", "judgeDate": "2026-02-11",
     "originDeclaration": {"classification": "ordinary_judgment",
                           "source": "synth-local-catalog",
                           "evidenceRef": "synth-origin-o1"}},
    {"docId": "CASLIB-SYN-W1",
     "docText": "【合成语料，非真实裁判】仅有网页声明的文书：还款凭证认定。",
     "caseNo": "(2026)合民4号", "courtName": "合成基层法院", "judgeDate": "2026-02-12",
     "provenance": [{"kind": "web_page_declaration",
                     "ref": "synth-web-page-ref-w1"}]},
]

LOCAL_ROWS = [
    {"canonical_doc_id": "SYN-001", "source_version": "v1",
     "doc_text": "【合成语料，非真实裁判】被告乙未能证明已经向原告甲还款，借贷事实不清。",
     "cause": "民间借贷", "judge_date": "2026-03-01", "court_id": "C1",
     "court_name_norm": "合成一审法院", "case_no_norm": "(2026)合001",
     "case_class": "民事", "trial_prog": "一审", "court_level": "基层",
     "region_prov": "测试省", "region_city": "测试市", "case_result": "部分支持",
     "year": "2026"},
]

_MANIFEST = {"source": "court_case_library",
             "license": {"name": "synthetic-eval-license",
                         "evidenceRef": "synth-license-evidence-1"},
             "records": CASLIB_RECORDS}

_ENV = None
_ACTIVE_TMPDIRS = []


def _require_pins():
    for rel, sha in CASES_SHA256.items():
        p = CASES_WT / rel
        if not p.is_file():
            raise AssertionError(
                f"pinned cases w4-u42 worktree missing at {CASES_WT}; the F72 "
                "court-library bridge cannot be verified")
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if actual != sha:
            raise AssertionError(f"{rel} drifted from the pinned delivery sha")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(CASES_WT),
                          capture_output=True, text=True, timeout=60).stdout.strip()
    if head != CASES_DELIVERY_COMMIT:
        raise AssertionError(f"cases w4-u42 worktree HEAD {head} != pinned delivery")
    # E19 钉定基不动：主检出 clean 且 P08 冻结基 sha 逐字在位。
    status = subprocess.run(["git", "status", "--porcelain"], cwd=str(CASES_MAIN),
                            capture_output=True, text=True, timeout=60).stdout.strip()
    if status:
        raise AssertionError(f"cases main checkout dirty: {status!r}")
    head_main = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(CASES_MAIN),
                               capture_output=True, text=True, timeout=60).stdout.strip()
    if head_main != CASES_E19_PIN_COMMIT:
        raise AssertionError(f"cases main HEAD {head_main} != E19 pin "
                             f"{CASES_E19_PIN_COMMIT}")


def _build_v4_root(base: Path) -> tuple:
    """合成 dataset root（text-only pin；lcr 钉到 w4-u42 检出）。"""
    sys.path.insert(0, str(CASES_WT))
    from lcr.runtime_v4 import initialize
    from lcr.monthly import import_month
    src = base / "source"
    src.mkdir(parents=True, exist_ok=True)
    month = src / "2026-03.csv.gz"
    with gzip.open(month, "wt", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(LOCAL_ROWS)
    cfg = initialize(str(base / "v4"), str(src), batch_rows=2)
    report = import_month(cfg, str(month))
    assert report["status"] == "PUBLISHED", report
    return cfg["root"], cfg["state_db"]


def _dataset_pin(root: str, state_db: str) -> str:
    import sqlite3
    db = sqlite3.connect(state_db)
    dataset_version = "documents:%d" % db.execute(
        "SELECT version FROM publication WHERE name='documents'").fetchone()[0]
    db.close()
    return dataset_version


def env():
    global _ENV
    if _ENV is None:
        import legal_entry
        _require_pins()
        holder = tempfile.TemporaryDirectory(prefix="w4u42_f72_")
        _ACTIVE_TMPDIRS.append(holder)
        base = Path(holder.name)
        root, state_db = _build_v4_root(base)
        config = {"cases_root": root,
                  "cases_import_path": str(CASES_WT),
                  "cases_dataset_version": _dataset_pin(root, state_db),
                  "caselib_dataset_version": None}   # filled after register
        reg = legal_entry.call("caselib.register", {"manifest": _MANIFEST}, config)
        config["caselib_dataset_version"] = reg["datasetVersion"]
        _ENV = {"holder": holder, "root": root, "config": config, "register": reg}
    return _ENV


def _scratch_config(tag: str) -> dict:
    """独立 v4 root（register 负测不污染共享 env 的承载状态）。"""
    import legal_entry
    holder = tempfile.TemporaryDirectory(prefix="w4u42_f72_neg_" + tag + "_")
    _ACTIVE_TMPDIRS.append(holder)
    root, state_db = _build_v4_root(Path(holder.name))
    return {"cases_root": root, "cases_import_path": str(CASES_WT),
            "cases_dataset_version": _dataset_pin(root, state_db),
            "caselib_dataset_version": None}


def _set_authorized(root: str, sources) -> None:
    rt = Path(root) / "runtime.json"
    body = json.loads(rt.read_text(encoding="utf-8"))
    body["paid_sources_authorized"] = list(sources)
    rt.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


class EntryPinTests(unittest.TestCase):
    def test_pinned_delivery_and_e19_base_intact(self):
        _require_pins()   # asserts inside; sha + HEAD + clean tree + main pin

    def test_p08_frozen_base_entry_pin_on_disk(self):
        with open(ENTRY_CSV, encoding="utf-8-sig") as f:
            rows = {r["entry_id"]: r for r in csv.DictReader(f)}
        pin = rows["P08"]
        self.assertEqual(Path(pin["path"]).read_bytes() and
                         hashlib.sha256(Path(pin["path"]).read_bytes()).hexdigest(),
                         pin["sha256"], "P08 frozen-base pin drifted on disk")


class RegisterTests(unittest.TestCase):
    def test_register_projection_and_idempotent_replay(self):
        import legal_entry
        e = env()
        reg = legal_entry.call("caselib.register", {"manifest": _MANIFEST}, e["config"])
        self.assertEqual(reg["schema"], "lvyin-caselib-register/1")
        self.assertEqual(reg["source"], "court_case_library")
        self.assertEqual(reg["datasetVersion"], "caselib:1")
        self.assertTrue(reg["indexVersion"].startswith("caselib-idx:"))
        self.assertEqual(reg["recordCount"], 4)
        self.assertIn("pending_authorization", reg["liveTransport"])
        again = legal_entry.call("caselib.register", {"manifest": _MANIFEST}, e["config"])
        self.assertEqual(again["datasetVersion"], reg["datasetVersion"])
        self.assertEqual(again["indexVersion"], reg["indexVersion"])

    def test_register_without_license_named_refused(self):
        import legal_entry
        from legal_entry import NotConnected
        cfg = _scratch_config("nolic")
        bad = dict(_MANIFEST, license=None)
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("caselib.register", {"manifest": bad}, cfg)
        self.assertTrue(str(ctx.exception).endswith(
            "caselib_failed:caselib_license_missing"), str(ctx.exception))

    def test_web_page_declaration_cannot_sign_official_tier(self):
        import legal_entry
        from legal_entry import NotConnected
        cfg = _scratch_config("webtier")
        bad = dict(_MANIFEST, records=[dict(CASLIB_RECORDS[0],
                                            tierDeclaration={
                                                "tier": "guiding_case",
                                                "source": "web_page_declaration",
                                                "evidenceRef": "synth-web-ref"})])
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("caselib.register", {"manifest": bad}, cfg)
        self.assertTrue(str(ctx.exception).endswith(
            "caselib_failed:caselib_tier_source_not_official"), str(ctx.exception))

    def test_local_origin_cannot_claim_official_tier(self):
        import legal_entry
        from legal_entry import NotConnected
        cfg = _scratch_config("origintier")
        bad = dict(_MANIFEST, records=[dict(CASLIB_RECORDS[2],
                                            originDeclaration={
                                                "classification": "guiding_case",
                                                "source": "synth-local-catalog",
                                                "evidenceRef": "synth-x"})])
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("caselib.register", {"manifest": bad}, cfg)
        self.assertTrue(str(ctx.exception).endswith(
            "caselib_failed:caselib_origin_value_invalid"), str(ctx.exception))


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = env()
        _set_authorized(e["root"], ["court_case_library"])
        cls.config = e["config"]

    @classmethod
    def tearDownClass(cls):
        _set_authorized(env()["root"], [])

    def test_authorized_search_real_block_with_stamp_class(self):
        import legal_entry
        result = legal_entry.call(
            "caselib.search", {"query": {"mode": "text", "text": "还款"}}, self.config)
        self.assertTrue(result["authorizedTried"])
        block = result["caseLibrary"]
        self.assertTrue(block["hits"])
        self.assertIs(block["relevanceNotProbability"], True)
        self.assertEqual(block["propositionSupport"],
                         "UNSIGNED_SOURCE_DECLARATION_IS_NOT_PROPOSITION_SUPPORT")
        self.assertEqual(result["scoreSemantics"],
                         {"retrievalScoreIsNotWinRate": True,
                          "notAPopulationSample": True, "probability": None})
        receipt = result["retrievalOrder"]["sources"]
        self.assertEqual([s["sourceId"] for s in receipt], list(LADDER))
        by_id = {s["sourceId"]: s for s in receipt}
        self.assertEqual(by_id["local_corpus"]["status"], "tried")
        self.assertEqual(by_id["court_case_library"]["status"], "tried")
        self.assertGreater(by_id["court_case_library"]["hits"], 0)
        for hit in block["hits"]:
            self.assertIsInstance(hit["score"], str)
            self.assertEqual(hit["locator"]["datasetVersion"],
                             self.config["caselib_dataset_version"])
            self.assertTrue(hit["locator"]["indexVersion"])
            self.assertIn(hit["tiering"]["officialTier"],
                          ("guiding_case", "included_case", "unknown"))

    def test_three_tier_readback_in_hits(self):
        import legal_entry
        result = legal_entry.call(
            "caselib.search", {"query": {"mode": "text", "text": "还款"},
                               "limit": 20}, self.config)
        tiering = {h["caseNo"]: h["tiering"] for h in result["caseLibrary"]["hits"]}
        self.assertEqual(tiering["(2026)合指1号"]["officialTier"], "guiding_case")
        self.assertEqual(tiering["(2026)合入2号"]["officialTier"], "included_case")
        ordinary = tiering["(2026)合民3号"]
        self.assertEqual(ordinary["officialTier"], "unknown")
        self.assertEqual(ordinary["classification"], "ordinary_judgment")
        self.assertEqual(ordinary["classificationSource"]["source"],
                         "synth-local-catalog")
        web = tiering["(2026)合民4号"]
        self.assertEqual(web["officialTier"], "unknown")
        self.assertEqual(web["classification"], "unknown")
        self.assertEqual(web["tierReason"], "no_official_tier_declaration_in_corpus")

    def test_two_runs_identical_hit_sequence(self):
        import legal_entry
        first = legal_entry.call("caselib.search",
                                 {"query": {"mode": "text", "text": "还款"}}, self.config)
        second = legal_entry.call("caselib.search",
                                  {"query": {"mode": "text", "text": "还款"}}, self.config)
        self.assertEqual([h["caseNo"] for h in first["caseLibrary"]["hits"]],
                         [h["caseNo"] for h in second["caseLibrary"]["hits"]])
        self.assertEqual(first["caseLibrary"]["datasetVersion"],
                         second["caseLibrary"]["datasetVersion"])

    def test_tier_filter_ordinary_is_classification_not_official_tier(self):
        import legal_entry
        from legal_entry import CaseProviderError
        with self.assertRaises(CaseProviderError) as ctx:
            legal_entry.call("caselib.search",
                             {"query": {"mode": "text", "text": "还款"},
                              "caseLibrary": {"filters": {"tier": "ordinary_judgment"}}},
                             self.config)
        self.assertEqual(ctx.exception.code, "query_invalid")
        self.assertIn("caselib_filter_invalid", str(ctx.exception))


class UnauthorizedTests(unittest.TestCase):
    def test_unauthorized_block_absent_ladder_skipped_nothing_fabricated(self):
        import legal_entry
        e = env()
        _set_authorized(e["root"], [])            # 缺省全未授权 fail-closed
        result = legal_entry.call("caselib.search",
                                  {"query": {"mode": "text", "text": "还款"}},
                                  e["config"])
        self.assertFalse(result["authorizedTried"])
        self.assertIsNone(result["caseLibrary"])
        self.assertNotIn("scoreSemantics", result)
        by_id = {s["sourceId"]: s for s in result["retrievalOrder"]["sources"]}
        entry = by_id["court_case_library"]
        self.assertEqual((entry["status"], entry["reason"], entry["hits"]),
                         ("skipped", "not_authorized", 0))
        self.assertGreater(by_id["local_corpus"]["hits"], 0,
                           "local ladder leg stays honest and real")


class TierReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = env()["config"]

    def test_official_tier_readback_with_source(self):
        import legal_entry
        view = legal_entry.call("caselib.tier", {"docId": "CASLIB-SYN-G1"},
                                self.config)
        self.assertEqual(view["officialTier"], "guiding_case")
        self.assertEqual(view["tierSource"]["source"],
                         "caselib_official_declaration")
        self.assertEqual(view["datasetVersion"],
                         self.config["caselib_dataset_version"])
        self.assertIsNone(view["tierReason"])

    def test_web_provenance_only_signs_nothing(self):
        import legal_entry
        view = legal_entry.call("caselib.tier", {"docId": "CASLIB-SYN-W1"},
                                self.config)
        self.assertEqual(view["officialTier"], "unknown")
        self.assertEqual(view["classification"], "unknown")
        self.assertEqual(view["tierReason"], "no_official_tier_declaration_in_corpus")
        self.assertEqual(view["classificationReason"],
                         "no_named_classification_source_in_corpus")

    def test_unknown_docid_named_refused(self):
        import legal_entry
        from legal_entry import NotConnected
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("caselib.tier", {"docId": "CASLIB-SYN-NONE"},
                             self.config)
        self.assertTrue(str(ctx.exception).endswith(
            "caselib_failed:caselib_ref_not_found"), str(ctx.exception))


class PinAndSmugglingTests(unittest.TestCase):
    def test_missing_caselib_pin_named(self):
        import legal_entry
        from legal_entry import NotConnected
        e = env()
        bad = dict(e["config"], caselib_dataset_version=None)
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("caselib.search",
                             {"query": {"mode": "text", "text": "还款"}}, bad)
        self.assertTrue(str(ctx.exception).endswith(
            "caselib_failed:caselib_config_missing"), str(ctx.exception))

    def test_stale_caselib_pin_named(self):
        import legal_entry
        from legal_entry import NotConnected
        e = env()
        bad = dict(e["config"], caselib_dataset_version="caselib:999")
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("caselib.tier", {"docId": "CASLIB-SYN-G1"}, bad)
        self.assertTrue(str(ctx.exception).endswith(
            "caselib_failed:caselib_binding_conflict"), str(ctx.exception))

    def test_caller_caseLibrary_pin_conflict_named(self):
        import legal_entry
        from legal_entry import NotConnected
        e = env()
        _set_authorized(e["root"], ["court_case_library"])
        try:
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("caselib.search",
                                 {"query": {"mode": "text", "text": "还款"},
                                  "caseLibrary": {"datasetVersion": "caselib:999"}},
                                 e["config"])
            self.assertTrue(str(ctx.exception).endswith(
                "caselib_failed:caselib_binding_conflict"), str(ctx.exception))
        finally:
            _set_authorized(e["root"], [])

    def test_probability_field_smuggling_named_reject(self):
        import legal_entry
        from legal_entry import NotConnected
        e = env()
        for smuggled in ({"winRate": 0.9}, {"caseLibrary": {"胜率": "0.9"}}):
            args = {"query": {"mode": "text", "text": "还款"}}
            args.update(smuggled)
            with self.subTest(smuggled=smuggled):
                with self.assertRaises(NotConnected) as ctx:
                    legal_entry.call("caselib.search", args, e["config"])
                self.assertTrue(str(ctx.exception).endswith(
                    "caselib_failed:caselib_probability_field_forbidden"),
                    str(ctx.exception))

    def test_unconfigured_bridge_not_connected(self):
        import legal_entry
        from legal_entry import NotConnected
        for method in ("caselib.register", "caselib.search", "caselib.tier"):
            with self.subTest(method=method):
                with self.assertRaises(NotConnected):
                    legal_entry.call(method, {}, {})

    def test_endpoint_shaped_config_client_construction_refused(self):
        """客户端构造即拒（W4-U03 N2 同口径）：本域端点形配置键一律具名拒。"""
        import legal_entry
        from legal_entry import NotConnected
        e = env()
        for key in ("cases_url", "caselib_endpoint", "court_library_base_url"):
            with self.subTest(key=key):
                bad = dict(e["config"], caselib_dataset_version=None)
                bad[key] = "http://127.0.0.1:1/never-a-real-endpoint"
                with self.assertRaises(NotConnected) as ctx:
                    legal_entry.call("caselib.search",
                                     {"query": {"mode": "text", "text": "还款"}}, bad)
                self.assertTrue(str(ctx.exception).endswith(
                    "caselib_failed:caselib_config_forbidden"), str(ctx.exception))


class AstDisciplineTests(unittest.TestCase):
    NETWORK_TOKENS = {"urllib", "requests", "socket", "http", "httpx",
                      "aiohttp", "ftplib", "smtplib", "telnetlib", "subprocess"}
    SCHEME_PARTS = ("http", "https", "ftp", "ws", "wss", "file")
    SCHEME_MARK = ":" + "/" + "/"

    def test_product_face_zero_url_zero_network(self):
        source = PRODUCT_FACE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        url_hits = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and any(p + self.SCHEME_MARK in n.value.lower()
                            for p in self.SCHEME_PARTS)]
        self.assertEqual(url_hits, [], "URL literals are structurally forbidden")
        roots = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                roots.update(a.name.split(".")[0] for a in n.names)
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                roots.add(n.module.split(".")[0])
        self.assertEqual(sorted(roots & self.NETWORK_TOKENS), [])

    def test_pinned_cases_faces_zero_url_zero_network(self):
        for rel in CASES_SHA256:
            source = (CASES_WT / rel).read_text(encoding="utf-8")
            tree = ast.parse(source)
            url_hits = [n.value for n in ast.walk(tree)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)
                        and any(p + self.SCHEME_MARK in n.value.lower()
                                for p in self.SCHEME_PARTS)]
            self.assertEqual(url_hits, [], rel)
            roots = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    roots.update(a.name.split(".")[0] for a in n.names)
                elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                    roots.add(n.module.split(".")[0])
            self.assertEqual(sorted(roots & self.NETWORK_TOKENS), [], rel)


class StaleCacheRegressionTests(unittest.TestCase):
    """W2a-U14 教训的 cases 形（同波 f67/p05 先行缓存旧检出 lcr）：
    产品面必须钉定检出优先（逐出异源缓存），保证承载面与梯子面同源。"""

    def test_stale_lcr_cache_purged_pin_wins(self):
        import legal_entry
        from court_case_library import CaseLibraryError  # noqa: F401
        e = env()
        saved = dict(sys.modules)
        sys.path.insert(0, str(CASES_WT))
        # 模拟先行波次：从旧检出（w2b-u57）导入 lcr，无 caselib 扩展。
        poison_root = str(CASES_MAIN)          # P08 冻结基（预扩展）
        sys.path.insert(0, poison_root)
        for name in [m for m in list(sys.modules)
                     if m == "lcr" or m.startswith("lcr.")]:
            del sys.modules[name]
        try:
            import lcr  # noqa: F401  （来自 poison_root：无 lcr.caselib）
            import lcr.public_facade  # noqa: F401
            poisoned = sys.modules["lcr"]
            self.assertIn(poison_root,
                          [str(Path(p).parent) for p in poisoned.__path__])
            # 产品面在异源缓存在位时仍必须工作（钉定检出优先）
            reg = legal_entry.call("caselib.register",
                                   {"manifest": _MANIFEST}, e["config"])
            self.assertEqual(reg["datasetVersion"],
                             e["register"]["datasetVersion"])
            _set_authorized(e["root"], ["court_case_library"])
            try:
                result = legal_entry.call(
                    "caselib.search", {"query": {"mode": "text", "text": "还款"}},
                    e["config"])
                self.assertTrue(result["authorizedTried"],
                                "stale lcr must be purged; the F72 adapter "
                                "lives only on the pinned checkout")
                self.assertTrue(result["caseLibrary"]["hits"])
            finally:
                _set_authorized(e["root"], [])
            pinned = sys.modules["lcr"]
            self.assertIn(str(CASES_WT),
                          [str(Path(p).parent) for p in pinned.__path__])
        finally:
            sys.path.remove(poison_root)
            sys.modules.clear()
            sys.modules.update(saved)


class FrozenBaseSubprocessTests(unittest.TestCase):
    def test_pre_f72_checkout_named_rejected_real_subprocess(self):
        """The P08-pinned base genuinely lacks lcr.caselib; the real bridge
        subprocess must named-reject instead of silently falling back."""
        cfg = dict(env()["config"], cases_import_path=str(CASES_MAIN))
        request = tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                              suffix=".json", delete=False)
        json.dump({"method": "caselib.search",
                   "args": {"query": {"mode": "text", "text": "还款"}}},
                  request, ensure_ascii=False)
        request.close()
        cfg_file = tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                               suffix=".json", delete=False)
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
            self.assertTrue(payload["code"].startswith("caselib_failed:caselib_module_missing"),
                            payload["code"])
        finally:
            os.unlink(request.name)
            os.unlink(cfg_file.name)


if __name__ == "__main__":
    unittest.main()
