"""W4-U02 (F71): the hybrid vector/similar-case retrieval audited at the bridge.

Positives run the REAL bridge subprocess (legal_entry --request-json) against
the real cases public face on this wave's pinned cases worktree (w4-u02, base
w2b-u57@858d0fa; JUSCITE_CASES_ROOT override) — the subprocess isolates the
lcr import from other wiring tests that pin the w2b-u57 checkout in-process.
The pre-extension negative pins the w2b-u57 worktree as the provider: it
genuinely lacks execution.hybrid, so the bridge must named-reject
(cases_public_facade_missing_hybrid_receipt) instead of silently downgrading
to a plain ordered search. Payload negatives exercise the real
legal_entry._audit_hybrid_receipt. All corpus material is synthetic.
"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "python"))

REPO_ROOT = HERE.parents[2]                       # juscite worktree root
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"

FIELDS = ['canonical_doc_id', 'doc_text', 'source_version', 'cause', 'judge_date', 'court_id',
          'court_name_norm', 'case_no_norm', 'case_class', 'trial_prog', 'court_level',
          'region_prov', 'region_city', 'case_result', 'year']

_SYN_ROWS = [
    {'canonical_doc_id': 'SYN-001', 'source_version': 'v1',
     'doc_text': '被告乙未能证明已经向原告甲还款，借贷事实不清，利息主张不予支持。',
     'cause': '民间借贷', 'judge_date': '2026-03-01', 'court_id': 'C1',
     'court_name_norm': '合成一审法院', 'case_no_norm': '(2026)合001', 'case_class': '民事',
     'trial_prog': '一审', 'court_level': '基层', 'region_prov': '测试省',
     'region_city': '测试市', 'case_result': '部分支持', 'year': '2026'},
    {'canonical_doc_id': 'SYN-002', 'source_version': 'v1',
     'doc_text': '原告主张的违约金过高，依法予以酌减，其余诉讼请求驳回。',
     'cause': '合同纠纷', 'judge_date': '2026-03-02', 'court_id': 'C2',
     'court_name_norm': '合成二审法院', 'case_no_norm': '(2026)合002', 'case_class': '民事',
     'trial_prog': '二审', 'court_level': '中级', 'region_prov': '测试省',
     'region_city': '测试市', 'case_result': '驳回', 'year': '2026'},
]


def cases_worktree():
    """This wave's cases branch (W4-U02); JUSCITE_CASES_ROOT overrides."""
    override = os.environ.get("JUSCITE_CASES_ROOT")
    if override:
        return Path(override)
    for parent in HERE.parents:
        if parent.name == "jusbench工作区":
            guess = (parent.parent / "legal-cn-cases工作区" / "legal-cn-cases"
                     / ".local" / "worktrees" / "w4-u02")
            if (guess / "lcr" / "hybrid_search.py").is_file():
                return guess
            break
    raise AssertionError("cases w4-u02 worktree not found; set JUSCITE_CASES_ROOT")


def prior_wave_worktree():
    for parent in HERE.parents:
        if parent.name == "jusbench工作区":
            guess = (parent.parent / "legal-cn-cases工作区" / "legal-cn-cases"
                     / ".local" / "worktrees" / "w2b-u57")
            if (guess / "lcr" / "public_facade.py").is_file():
                return guess
            break
    return None


def build_root(base: Path) -> dict:
    import gzip
    import csv as _csv
    sys.path.insert(0, str(cases_worktree()))
    from lcr.runtime_v4 import initialize
    from lcr.monthly import import_month
    src = base / 'source'
    src.mkdir(parents=True, exist_ok=True)
    with gzip.open(src / '2026-03.csv.gz', 'wt', encoding='utf-8-sig', newline='') as f:
        w = _csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(_SYN_ROWS)
    cfg = initialize(str(base / 'v4'), str(src), batch_rows=2)
    report = import_month(cfg, str(src / '2026-03.csv.gz'))
    assert report['status'] == 'PUBLISHED', report
    db = sqlite3.connect(cfg['state_db'])
    dataset_version = 'documents:%d' % db.execute(
        "SELECT version FROM publication WHERE name='documents'").fetchone()[0]
    db.close()
    return {'cases_root': cfg['root'],
            'cases_import_path': str(cases_worktree()),
            'cases_dataset_version': dataset_version}


_ENV = None


def config():
    global _ENV
    if _ENV is None:
        _ENV = build_root(Path(tempfile.mkdtemp(prefix='w4u02_f71_wiring_')))
    return _ENV


def call_entry_subprocess(method, args, cfg):
    request = tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.json', delete=False)
    json.dump({'method': method, 'args': args}, request, ensure_ascii=False)
    request.close()
    cfg_file = tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.json', delete=False)
    json.dump(cfg, cfg_file, ensure_ascii=False)
    cfg_file.close()
    try:
        proc = subprocess.run(
            [sys.executable, '-X', 'utf8', str(LEGAL_ENTRY),
             '--request-json', request.name, '--config', cfg_file.name],
            capture_output=True, text=True, encoding='utf-8', timeout=300,
            cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {'_raw': proc.stdout[-400:], '_stderr': proc.stderr[-400:]}
        return {'exit': proc.returncode, 'payload': payload}
    finally:
        os.unlink(request.name)
        os.unlink(cfg_file.name)


def _hybrid_args(text='还款', hybrid=None):
    execution = {'hybrid': {} if hybrid is None else hybrid}
    return {'query': {'mode': 'text', 'text': text}, 'filters': {}, 'execution': execution}


class BridgeHybridSubprocessTests(unittest.TestCase):
    def test_hybrid_search_through_bridge_with_audited_receipt(self):
        out = call_entry_subprocess('case.search', _hybrid_args(), config())
        self.assertEqual(out['exit'], 0, out['payload'])
        result = out['payload']['result']
        self.assertEqual(result['schema'], 'lcr.search/4')
        hybrid = result['hybrid']
        self.assertEqual(hybrid['schema'], 'lcr.hybrid-search/1')
        self.assertTrue(hybrid['hybridIndexVersion'].startswith('hybrid:'))
        self.assertEqual([c['channelId'] for c in hybrid['channels']],
                         ['fts_custom_segment', 'vector_local'])
        self.assertTrue(all(c['tried'] for c in hybrid['channels']))
        self.assertEqual(hybrid['scoreSemantics']['retrievalScoreIsNotWinRate'], True)
        self.assertEqual(hybrid['scoreSemantics']['probability'], None)
        self.assertEqual(hybrid['externalCorpus']['status'], 'UNKNOWN')
        self.assertIsNone(hybrid['externalCorpus']['value'])
        self.assertEqual(result['retrievalOrder']['constitution'],
                         'local_free_then_paid_no_skip_level')
        self.assertTrue(result['hits'])

    def test_two_runs_identical_fingerprint_through_bridge(self):
        first = call_entry_subprocess('case.search', _hybrid_args(), config())
        second = call_entry_subprocess('case.search', _hybrid_args(), config())
        self.assertEqual(first['exit'], 0)
        self.assertEqual(second['exit'], 0)
        fp1 = first['payload']['result']['hybrid']['fingerprint']
        fp2 = second['payload']['result']['hybrid']['fingerprint']
        self.assertEqual(fp1, fp2)
        ids1 = [h['locator']['canonicalDocId'] for h in first['payload']['result']['hits']]
        ids2 = [h['locator']['canonicalDocId'] for h in second['payload']['result']['hits']]
        self.assertEqual(ids1, ids2)

    def test_probability_field_named_rejected_through_bridge(self):
        out = call_entry_subprocess('case.search', _hybrid_args(hybrid={'winRate': 0.9}),
                                    config())
        self.assertEqual(out['exit'], 4, out['payload'])
        self.assertEqual(out['payload'].get('status'), 'CASE_ERROR')
        self.assertEqual(out['payload'].get('code'), 'retrieval_score_used_as_win_rate')

    def test_pre_extension_checkout_named_rejected_not_silent_downgrade(self):
        """w2b-u57 provider genuinely lacks execution.hybrid; the real bridge
        subprocess must named-reject instead of silently returning a plain
        ordered search."""
        prior = prior_wave_worktree()
        if prior is None:
            self.skipTest('w2b-u57 worktree not present on this machine')
        cfg = dict(config(), cases_import_path=str(prior))
        out = call_entry_subprocess('case.search', _hybrid_args(), cfg)
        self.assertEqual(out['exit'], 3, out['payload'])
        self.assertEqual(out['payload'].get('status'), 'NOT_CONNECTED')
        self.assertTrue(str(out['payload'].get('code', '')).startswith(
            'cases_public_facade_missing_hybrid_receipt'), out['payload'].get('code'))


def _load_legal_entry_module():
    spec = importlib.util.spec_from_file_location('legal_entry_f71_test', LEGAL_ENTRY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class HybridAuditPayloadNegativeTests(unittest.TestCase):
    """Hermetic payload-level negatives for the bridge hybrid receipt auditor."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_legal_entry_module()
        cls.channels = ({'channelId': 'fts_custom_segment', 'kind': 'fulltext'},
                        {'channelId': 'vector_local', 'kind': 'vector'})

    def _audit(self, result):
        self.mod._audit_hybrid_receipt(result, 'lcr.hybrid-search/1', self.channels)

    @staticmethod
    def _good_hybrid(**over):
        receipt = {'schema': 'lcr.hybrid-search/1',
                   'hybridIndexVersion': 'hybrid:' + 'a' * 64,
                   'channels': [
                       {'channelId': 'fts_custom_segment', 'kind': 'fulltext',
                        'tried': True, 'candidates': 3},
                       {'channelId': 'vector_local', 'kind': 'vector',
                        'tried': True, 'candidates': 2}],
                   'scoreSemantics': {'score': 'rrf',
                                      'retrievalScoreIsNotWinRate': True,
                                      'notAPopulationSample': True,
                                      'probability': None},
                   'externalCorpus': {'sourceId': 'cncases_full', 'status': 'UNKNOWN',
                                      'value': None,
                                      'reason': 'external_source_not_authorized'},
                   'coverage': {'documents': 400, 'months': 6}}
        receipt.update(over)
        return receipt

    def test_missing_receipt_named(self):
        with self.assertRaises(self.mod.CaseProviderError) as ctx:
            self._audit({'schema': 'lcr.search/4', 'hits': []})
        self.assertEqual(ctx.exception.code, 'case_search_hybrid_receipt_missing')

    def test_wrong_schema_named(self):
        with self.assertRaises(self.mod.CaseProviderError) as ctx:
            self._audit({'hits': [], 'hybrid': self._good_hybrid(schema='tampered')})
        self.assertEqual(ctx.exception.code, 'case_search_hybrid_receipt_invalid')

    def test_bad_identity_named(self):
        with self.assertRaises(self.mod.CaseProviderError) as ctx:
            self._audit({'hits': [],
                         'hybrid': self._good_hybrid(hybridIndexVersion='v1.2.3')})
        self.assertEqual(ctx.exception.code, 'case_search_hybrid_receipt_invalid')

    def test_channel_missing_or_not_tried_named(self):
        for tamper in ({'channels': [{'channelId': 'fts_custom_segment'}]},
                       {'channels': [{'channelId': 'fts_custom_segment', 'tried': False},
                                     {'channelId': 'vector_local', 'tried': True}]}):
            with self.assertRaises(self.mod.CaseProviderError) as ctx:
                self._audit({'hits': [], 'hybrid': self._good_hybrid(**tamper)})
            self.assertEqual(ctx.exception.code, 'case_search_hybrid_receipt_invalid')

    def test_stamp_tamper_named(self):
        for over in ({'scoreSemantics': {'retrievalScoreIsNotWinRate': False,
                                         'notAPopulationSample': True,
                                         'probability': None}},
                     {'scoreSemantics': {'retrievalScoreIsNotWinRate': True,
                                         'notAPopulationSample': True,
                                         'probability': 0.5}}):
            with self.assertRaises(self.mod.CaseProviderError) as ctx:
                self._audit({'hits': [], 'hybrid': self._good_hybrid(**over)})
            self.assertEqual(ctx.exception.code, 'case_search_hybrid_receipt_invalid')

    def test_external_corpus_not_unknown_named(self):
        for value in (0, 85_000_000):
            with self.assertRaises(self.mod.CaseProviderError) as ctx:
                self._audit({'hits': [], 'hybrid': self._good_hybrid(
                    externalCorpus={'sourceId': 'cncases_full', 'status': 'UNKNOWN',
                                    'value': value,
                                    'reason': 'external_source_not_authorized'})})
            self.assertEqual(ctx.exception.code, 'case_search_hybrid_receipt_invalid',
                             'value=%r must be named-rejected (None is the only honest '
                             'unauthorized value)' % value)
        with self.assertRaises(self.mod.CaseProviderError) as ctx:
            self._audit({'hits': [], 'hybrid': self._good_hybrid(
                externalCorpus={'sourceId': 'cncases_full', 'status': 'MEASURED',
                                'value': 123, 'reason': 'x'})})
        self.assertEqual(ctx.exception.code, 'case_search_hybrid_receipt_invalid')

    def test_coverage_denominator_missing_named(self):
        with self.assertRaises(self.mod.CaseProviderError) as ctx:
            self._audit({'hits': [], 'hybrid': self._good_hybrid(
                coverage={'documents': 0, 'months': 6})})
        self.assertEqual(ctx.exception.code, 'case_search_hybrid_receipt_invalid')


if __name__ == '__main__':
    unittest.main()
