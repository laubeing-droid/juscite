"""W1-U04: P05-P08 case retrieval entries wired through the product bridge.

E09 early wiring for the case domain (authority 14-Python入口与施工接线.md §1):
the bridge prefers the frozen CasePublicService public face (P08) and binds
dataset/indexVersion; the legacy lcr/1 HTTP seed keeps its failure semantics;
unbound configs answer NOT_CONNECTED, never a success stub.

All corpus material below is synthetic (软件合成语料, no real case data). The
vector index is real: encode_delta embeds the synthetic corpus with the locally
cached BAAI/bge-small-zh-v1.5 backbone, so cases_index_version is a genuine
content-addressed model key read back from state, never a fixture constant.
"""
import csv
import gzip
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "python"))

REPO_ROOT = HERE.parents[2]                       # juscite worktree root
ENTRY_CSV = REPO_ROOT / "docs" / "construction" / "authority" / "14-Python入口证据.csv"

from legal_entry import call, NotConnected, CaseProviderError  # noqa: E402

FIELDS = ['canonical_doc_id', 'doc_text', 'source_version', 'cause', 'judge_date', 'court_id',
          'court_name_norm', 'case_no_norm', 'case_class', 'trial_prog', 'court_level',
          'region_prov', 'region_city', 'case_result', 'year']

SYN_ROWS = [
    # Fully synthetic month rows; the make_fixtures demo source (DEMO-A) is added
    # by _build_env so the CARD-A fixture binds to a real source row of this corpus.
    {'canonical_doc_id': 'SYN-001', 'source_version': 'v1',
     'doc_text': '【合成语料，非真实裁判】被告乙未能证明已经向原告甲还款，借贷事实不清。',
     'cause': '民间借贷', 'judge_date': '2026-03-01', 'court_id': 'C1', 'court_name_norm': '合成一审法院',
     'case_no_norm': '(2026)合001', 'case_class': '民事', 'trial_prog': '一审', 'court_level': '基层',
     'region_prov': '测试省', 'region_city': '测试市', 'case_result': '部分支持', 'year': '2026'},
    {'canonical_doc_id': 'SYN-002', 'source_version': 'v1',
     'doc_text': '【合成语料，非真实裁判】原告主张的利息超过约定标准，不予支持。',
     'cause': '合同纠纷', 'judge_date': '2026-03-02', 'court_id': 'C2', 'court_name_norm': '合成二审法院',
     'case_no_norm': '(2026)合002', 'case_class': '民事', 'trial_prog': '二审', 'court_level': '中级',
     'region_prov': '测试省', 'region_city': '测试市', 'case_result': '驳回', 'year': '2026'},
]


def _pinned_entries():
    with open(ENTRY_CSV, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    return {r['entry_id']: (r['path'], r['sha256']) for r in rows if r['entry_id'] in {'P05', 'P06', 'P07', 'P08'}}


def _write_month(path, rows):
    with gzip.open(path, 'wt', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def _cases_worktree():
    """W2b-U57 same-wave pinning: the bridge now audits the F68 retrieval-order
    receipt, so the ``lcr`` import must resolve to this wave's cases branch
    (pre-extension checkouts answer case_search_order_receipt_missing).
    ``JUSCITE_CASES_ROOT`` overrides; with neither, fall back to the pinned P08
    main checkout (post-merge state). Same discipline as conftest's anonymizer
    worktree resolution (W2a-U14 lesson)."""
    override = os.environ.get("JUSCITE_CASES_ROOT")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "jusbench工作区":
            guess = (parent.parent / "legal-cn-cases工作区" / "legal-cn-cases"
                     / ".local" / "worktrees" / "w2b-u57")
            if (guess / "lcr" / "public_facade.py").is_file():
                return guess
            break
    return None


def _build_env(base):
    """Synthetic month -> published dataset (FTS) -> card -> units -> real vector index."""
    cases_root = _cases_worktree() or Path(_pinned_entries()['P08'][0]).parents[1]
    sys.path.insert(0, str(cases_root))
    from examples.make_fixtures import fixture
    from lcr.runtime_v4 import initialize, open_state
    from lcr.monthly import import_month
    from lcr.indexers_lance import encode_delta, sync_units
    from lcr.store import Store
    from lcr.binding import bind_quotes

    demo_source, demo_card = fixture('A')
    src = base / 'source'
    src.mkdir(parents=True, exist_ok=True)
    month = src / '2026-03.csv.gz'
    _write_month(month, [dict(demo_source)] + SYN_ROWS)
    cfg = initialize(str(base / 'v4'), str(src), batch_rows=2,
                     model='BAAI/bge-small-zh-v1.5', text_dimension=512,
                     device='cpu', max_length=128, encode_batch_size=2)
    report = import_month(cfg, str(month))
    assert report['status'] == 'PUBLISHED', report
    s = Store(cfg['state_db'])
    s.put_card(bind_quotes(demo_card, s.source(demo_source['canonical_doc_id'])))
    s.close()
    sync_units(cfg)
    encode_delta(cfg)
    db = open_state(cfg['state_db'])
    dataset_version = 'documents:%d' % db.execute(
        "SELECT version FROM publication WHERE name='documents'").fetchone()[0]
    index_version = json.loads(db.execute(
        "SELECT body FROM vector_models WHERE name='active'").fetchone()[0])['key']
    db.close()
    return {'cases_root': cases_root, 'cfg': cfg,
            'dataset_version': dataset_version, 'index_version': index_version}


_ENV = None


def env():
    global _ENV
    if _ENV is None:
        import tempfile
        _ENV = _build_env(Path(tempfile.mkdtemp(prefix='w1u04_cases_wiring_')))
    return _ENV


class EntryPinTests(unittest.TestCase):
    def test_p05_p08_files_match_pinned_sha256(self):
        for pid, (path, sha) in sorted(_pinned_entries().items()):
            with self.subTest(entry=pid):
                actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
                self.assertEqual(actual, sha, f'{pid} {path} drifted from the pinned entry sha')


class NotConnectedTests(unittest.TestCase):
    def test_unbound_config_is_not_connected(self):
        for method in ('case.search', 'case.read', 'case.stats', 'case.comparison'):
            with self.subTest(method=method):
                with self.assertRaises(NotConnected):
                    call(method, {'query': {'mode': 'text', 'text': '还款'}}, {})

    def test_partial_binding_is_not_connected(self):
        # cases_root without the dataset pin (and vice versa) must not connect.
        for partial in ({'cases_root': 'x'}, {'cases_dataset_version': 'documents:1'},
                        {'cases_root': 'x', 'cases_index_version': 'k'}):
            with self.subTest(config=partial):
                with self.assertRaises(NotConnected):
                    call('case.search', {'query': {'mode': 'text', 'text': '还款'}}, partial)

    def test_legacy_http_gate_failure_semantics_preserved(self):
        with self.assertRaisesRegex(NotConnected, 'cases_lcr1_http_not_configured'):
            call('case.search', {'query': '还款'}, {'cases_contract': 'lcr/1'})


class PublicFaceWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = env()
        cls.config = {'cases_root': e['cfg']['root'],
                      'cases_import_path': e['cases_root'],
                      'cases_dataset_version': e['dataset_version'],
                      'cases_index_version': e['index_version']}

    def test_search_real_trigger_and_version_echo(self):
        result = call('case.search', {'query': {'mode': 'text', 'text': '还款'}, 'filters': {}}, self.config)
        self.assertEqual(result['schema'], 'lcr.search/4')
        self.assertTrue(result['hits'], 'text search must really hit the synthetic corpus')
        self.assertEqual(result['datasetVersion'], self.config['cases_dataset_version'])
        self.assertEqual(result['indexVersion'], self.config['cases_index_version'])
        ids = {h['locator']['canonicalDocId'] for h in result['hits']}
        self.assertIn('SYN-001', ids)
        for hit in result['hits']:
            self.assertEqual(hit['authorityStatus'], 'CASE_SOURCE_CANDIDATE')
            self.assertEqual(hit['locator']['datasetVersion'], self.config['cases_dataset_version'])

    def test_stats_readback_echoes_dataset_binding(self):
        stats = call('case.stats', {'groupBy': ['case_result'], 'filters': {'cause': '民间借贷'}}, self.config)
        self.assertEqual(stats['datasetVersion'], self.config['cases_dataset_version'])
        self.assertEqual(stats['population'], 1)
        self.assertEqual([(g['key'], g['n']) for g in stats['groups']], [('部分支持', 1)])

    def test_read_readback_echoes_dataset_binding(self):
        # locator carries no datasetVersion on purpose: the binding supplies it.
        read = call('case.read', {'locator': {'canonicalDocId': 'SYN-001', 'month': '2026-03',
                                              'locator': {'sourceRow': 1, 'recordHash': '', 'itemId': None}}},
                    self.config)
        self.assertEqual(read['locator']['datasetVersion'], self.config['cases_dataset_version'])
        self.assertIn('还款', read['docText'])
        self.assertEqual(read['source']['sourceRow'], 2)  # DEMO-A is month row 1, SYN-001 row 2

    def test_comparison_real_trigger(self):
        report = call('case.comparison', {'leftId': 'CARD-A', 'rightId': 'CARD-A', 'mode': 'card'}, self.config)
        self.assertEqual(report['schema'], 'lcr.compare/1')
        self.assertTrue(report['sameTemplate'])

    def test_stale_dataset_pin_fails_closed(self):
        bad = dict(self.config, cases_dataset_version='documents:999999')
        with self.assertRaises(CaseProviderError) as ctx:
            call('case.search', {'query': {'mode': 'text', 'text': '还款'}}, bad)
        self.assertEqual(ctx.exception.code, 'dataset_version_not_found')

    def test_stale_index_pin_fails_closed(self):
        bad = dict(self.config, cases_index_version='not-a-real-index-key')
        with self.assertRaises(CaseProviderError) as ctx:
            call('case.search', {'query': {'mode': 'text', 'text': '还款'}}, bad)
        self.assertEqual(ctx.exception.code, 'index_not_built')

    def test_caller_conflicting_pin_rejected_not_silently_overridden(self):
        args = {'query': {'mode': 'text', 'text': '还款'},
                'datasetVersion': self.config['cases_dataset_version'] + 'x'}
        with self.assertRaisesRegex(ValueError, 'cases_binding_conflict'):
            call('case.search', args, self.config)

    def test_unknown_case_method_still_not_connected(self):
        with self.assertRaises(NotConnected):
            call('case.wiki_build', {'issue': 'x'}, self.config)


class CliChannelComparisonTests(unittest.TestCase):
    def test_p07_cli_search_on_same_synthetic_corpus(self):
        e = env()
        proc = subprocess.run(
            [sys.executable, '-X', 'utf8', '-m', 'lcr', '--db', e['cfg']['state_db'],
             'search', '还款', '--limit', '5'],
            cwd=str(e['cases_root']), capture_output=True, text=True,
            encoding='utf-8', timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out['schema'], 'lcr.search/1')
        self.assertTrue(any(h['card_id'] == 'CARD-A' for h in out['hits']),
                        'CLI channel must reach the same synthetic corpus/engine')


if __name__ == '__main__':
    unittest.main()
