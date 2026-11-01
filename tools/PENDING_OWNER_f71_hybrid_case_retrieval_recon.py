# -*- coding: utf-8 -*-
"""F71 向量/类案混合检索硬里程碑验收（PENDING_OWNER 版，工单 W4-U02）。

06 V7-71：『向量/类案检索（v1.5 硬里程碑；cncases 8500 万 Rust 本地全文路线；
混合双通道+RRF）』；08§2 B4『向量类案硬里程碑』。本单为 F71 首个落地单
（W2b-U57 边界『F71 向量混合不前造』在此兑现）。

断言分母（06 acceptance 行）：真实 active 指纹（dataset/indexVersion 钉定，
17 卡步骤）混合检索；相关度非概率（对齐 E19 retrieval_score 盖戳纪律，塞
winRate/胜率字段具名拒）；月/文档覆盖如实分母；全库义务独立验——本地库
（E22 B1 实测 10342 案例）真索引全量跑，cncases 外部全库未授权＝具名缺口
（UNKNOWN 值 None 非 0，裁决#8-12 负测先行），不以局部顶替、禁编 URL；
出处/locator 逐条回读；F67 金标 30 条（score_fingerprint a04beb9a…）复用
为回归锚；确定性两跑同分。

分段（每 profile 各跑一遍，desktop/selfhost 分状态根分证据——F40 先例：
共用宿主面、无独立 PG 面）：
  C01 cases 仓钉定基：worktree 含 w2b-u57@858d0fa、树净、仓级 autocrlf=false
      （U57 事故教训）、迁移 manifest 字节自洽、主检出 P08==38c1959c 不动、
      扩展面在（lcr/hybrid_search.py＋SCHEMA_HYBRID）。
  C02 F67 金标回归锚：seed 20261017 语料/金标确定性，两跑同分且指纹等于
      F67 交付值 a04beb9a…（已 VERIFIED 分数不回归）。
  C03 混合检索金标全中：400 篇合成语料 V4 root 上 30 金标逐条混合
      recall=1.000。
  C04 RRF 融合实测：逐 hit score 与双通道手工复算 RRF 相等；两跑同
      fingerprint；hybrid 回执全检（schema/双通道 tried/fusion k=60/覆盖
      分母/externalCorpus UNKNOWN 值 None/盖戳三件/顺序账回执）。
  C05 相关度非概率＋钉定负测：hybrid 块塞 winRate/victoryRate/
      successProbability/probability/胜率 → retrieval_score_used_as_win_rate；
      datasetVersion 不符 → dataset_version_not_found；无 execution 冻结
      v1.0.0 形状逐键不变。
  C06 出处/locator 逐条回读：hit locator → case.read 逐字对上
      （canonicalDocId/recordHash/sourceRow）。
  C07 产品桥真跑（legal_entry 子进程，cases_import_path 钉本单 cases
      worktree）：hybrid 检索 exit 0＋桥级混合回执审计过＋两跑同序；
      预扩展检出（w2b-u57 worktree，无 hybrid 面）→ exit 3
      cases_public_facade_missing_hybrid_receipt 不静默降级。
  C08 全库义务独立验（E22 本地库）：lccc_consumer（codices 检出）对账
      cases.rows==10342＋markdown case==10340＋cncases external_capacity
      UNKNOWN 值 None；盘上四案例目录 10340 篇 md 全文真索引全量构建
      （FTS5 自建分词＋本地向量）；hybridIndexVersion 内容寻址指纹；
      coverage 月/文档分母如实（months=真实月桶数、documents=导入全量、
      无月桶数=缺口如实）；全库金标 30 条（案号锚索引级唯一性验证＝AND
      语义全词元同篇齐备恰一篇）经公开混合路径双跑（perChannelDepth=200，
      引擎校验上界）：确定性同指纹同观测＋coverage/外部 UNKNOWN 逐查询
      断言＋已召回锚 top-3 逐字 case.read 回读；召回序位逐锚如实入证据、
      未入融合窗的漏锚具名（被引用案号的词元集原样出现于引用文书，冻结
      引擎 OR/bm25 排序不可动——质量召回门由 C03 精选金标承担）；
      容量字节/构建耗时如实记录。
  C09 证据落盘 evidence/F71/<profile>/。

用法（juscite 本单 worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f71_hybrid_case_retrieval_recon.py
    --profile desktop --profile selfhost
  [--cases-root <cases w4-u02 worktree>] [--codices-repo <codices 检出>]
  [--formal-root <E22 正式发布目录>] [--skip-fullcorpus 仅调试用，验收无效]

exit 0＝所跑 profile 全部断言过（RECON_OK）。全程合成材料＋只读消费 E22
正式面；零网络出站；%APPDATA% 零触碰；不 push。
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUN_TS = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
REPO_ROOT = Path(__file__).resolve().parents[1]          # juscite worktree root
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
ENTRY_CSV = REPO_ROOT / "docs" / "construction" / "authority" / "14-Python入口证据.csv"

# F67 交付指纹（evidence/F67/f67-two-form-unified-report.json，W2b-U57 VERIFIED）
F67_FINGERPRINT = "a04beb9a248e91de1f8840d0d97b25dc6fc5a89dc7cb1b9c6ace51c92c7e1ec6"
# cases 仓钉定基：w2b-u57 收口（F67/F68 底座）
CASES_BASE_COMMIT = "858d0fa"
# U57 冻结基（主检出 P08 钉定形态，F71 不动主检出）
CASES_FROZEN_FACADE_SHA = "38c1959c30412192e6abd71ad683f4cc285ae9e4d9bfaeee7d4ca78cea61942f"

E22_CASES_ROWS = 10342          # E22 B1 实测：cases.csv 记录数
E22_MARKDOWN_CASE = 10340       # E22 markdown_face.object_types.case 官方计数
CORPUS_SEED = 20261017

FIELDS = ['canonical_doc_id', 'doc_text', 'source_version', 'cause', 'judge_date', 'court_id',
          'court_name_norm', 'case_no_norm', 'case_class', 'trial_prog', 'court_level',
          'region_prov', 'region_city', 'case_result', 'year']


class Checks:
    def __init__(self, profile: str):
        self.profile = profile
        self.items: list = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s][%s] %s — %s" % ("PASS" if ok else "FAIL", self.profile,
                                    check_id, detail), flush=True)
        return ok

    @property
    def all_passed(self) -> bool:
        return all(i["status"] == "PASS" for i in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for i in self.items if i["status"] == "PASS")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_cases_root(explicit: str | None) -> Path:
    """JUSCITE_CASES_ROOT > 显式参 > 本单 worktree（w4-u02）。"""
    if explicit:
        return Path(explicit)
    override = os.environ.get("JUSCITE_CASES_ROOT")
    if override:
        return Path(override)
    for parent in REPO_ROOT.parents:
        if parent.name == "jusbench工作区":
            guess = (parent.parent / "legal-cn-cases工作区" / "legal-cn-cases"
                     / ".local" / "worktrees" / "w4-u02")
            if (guess / "lcr" / "hybrid_search.py").is_file():
                return guess
            break
    raise SystemExit("FATAL: cases w4-u02 worktree not found; "
                     "pass --cases-root or set JUSCITE_CASES_ROOT")


def resolve_codices(explicit_repo: str | None, explicit_formal: str | None) -> tuple:
    """codices 检出（lccc_consumer.py 所在）＋E22 正式发布目录。"""
    repo = explicit_repo or os.environ.get("JUSCITE_CODICES_REPO")
    formal = explicit_formal or os.environ.get("JUSCITE_CODICES_FORMAL_ROOT")
    for parent in REPO_ROOT.parents:
        if parent.name == "法律工作区" or parent.name == "jusbench工作区":
            base = parent if parent.name == "法律工作区" else parent.parent
            guess_repo = (base / "legal-cn-core-codices工作区"
                          / "legal-cn-core-codices-repo" / ".local" / "worktrees"
                          / "w2a-u12-e22")
            guess_formal = base / "legal-cn-core-codices工作区" / "legal-cn-core-codices"
            if repo is None and (guess_repo / "lccc_consumer.py").is_file():
                repo = str(guess_repo)
            if formal is None and (guess_formal / "cases.csv").is_file():
                formal = str(guess_formal)
            break
    if repo is None or formal is None:
        raise SystemExit("FATAL: codices e22 checkout / formal root not found; "
                         "pass --codices-repo/--formal-root")
    return Path(repo), Path(formal)


def git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", timeout=60)


# ---------- C01：cases 钉定基 ----------

def c01_pinned_base(checks: Checks, cases_root: Path) -> dict:
    ancestor = git(["merge-base", "--is-ancestor", CASES_BASE_COMMIT, "HEAD"], cases_root)
    head = git(["rev-parse", "HEAD"], cases_root).stdout.strip()
    checks.add("C01a-base-ancestor-clean", ancestor.returncode == 0,
               "cases HEAD %s contains w2b-u57 base %s" % (head[:12], CASES_BASE_COMMIT[:6]))
    status = git(["status", "--porcelain"], cases_root)
    checks.add("C01b-worktree-clean", status.returncode == 0 and not status.stdout.strip(),
               "cases tree clean (porcelain empty)")
    autocrlf = git(["config", "core.autocrlf"], cases_root).stdout.strip()
    checks.add("C01c-worktree-autocrlf-false", autocrlf == "false",
               "worktree core.autocrlf=%r (U57 CRLF incident lesson; false required)"
               % autocrlf)
    manifest = json.loads((cases_root / "migration" / "v3_manifest.json").read_text(
        encoding="utf-8"))
    mismatches = [i["path"] for i in manifest["files"]
                  if i["path"].startswith("tests/")
                  and sha256_bytes((cases_root / i["path"]).read_bytes()) != i["sha256"]]
    checks.add("C01d-migration-manifest-bytes", not mismatches,
               "tests/ manifest bytes intact (%s)" % ("ok" if not mismatches
                                                      else str(mismatches)))
    pin_path, pin_sha = None, None
    with open(ENTRY_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["entry_id"] == "P08":
                pin_path, pin_sha = row["path"], row["sha256"]
                break
    actual = sha256_bytes(Path(pin_path).read_bytes())
    if not checks.add("C01e-main-checkout-pin-bytes", actual == pin_sha,
                      "P08 main checkout disk sha %s… == pinned %s… (F71 never touches "
                      "the main checkout)" % (actual[:12], pin_sha[:12])):
        raise SystemExit("FATAL: frozen base checkout drifted from P08 pin")
    facade = (cases_root / "lcr" / "public_facade.py").read_bytes()
    checks.add("C01f-hybrid-extension-present",
               b"SCHEMA_HYBRID" in facade and (cases_root / "lcr" / "hybrid_search.py").is_file(),
               "extended facade present on branch (public_facade sha256 %s…, "
               "hybrid_search.py present)"
               % sha256_bytes(facade)[:12])
    return {"casesRoot": str(cases_root), "casesHead": head,
            "baseCommit": CASES_BASE_COMMIT, "autocrlf": autocrlf,
            "branchFacadeSha256": sha256_bytes(facade),
            "pinPath": pin_path, "mainCheckoutFacadeSha256": actual}


def load_lcr(cases_root: Path):
    sys.path.insert(0, str(cases_root))
    import lcr.fts_eval as fts_eval            # noqa: F401
    import lcr.public_facade as public_facade  # noqa: F401
    import lcr.hybrid_search as hybrid_search  # noqa: F401
    return fts_eval, public_facade, hybrid_search


# ---------- C02：F67 金标回归锚 ----------

def c02_f67_anchor(checks: Checks, fts_eval) -> tuple:
    corpus = fts_eval.build_corpus()
    gold = fts_eval.build_gold(corpus)
    ok = (len(corpus) == 400 and len(gold) == 30
          and sum(1 for g in gold if g["kind"] == "free_text") == 20
          and sum(1 for g in gold if g["kind"] == "citation") == 10
          and all(g["relevant"] for g in gold))
    checks.add("C02a-gold-anchor-structure", ok,
               "F67 gold reused: 30 queries (20 free_text + 10 citation), "
               "corpus sha %s…" % fts_eval._corpus_sha(corpus)[:12])
    workdir = tempfile.mkdtemp(prefix="f71-f67-anchor-")
    outcome = fts_eval.run_twice_for_determinism(workdir)
    checks.add("C02b-f67-fingerprint-regression",
               outcome["identicalScores"] and outcome["run1Fingerprint"] == F67_FINGERPRINT,
               "two-run fingerprint %s… == delivered %s… (VERIFIED F67 scores do not "
               "regress)" % (outcome["run1Fingerprint"][:12], F67_FINGERPRINT[:12]))
    return corpus, gold, outcome["run1Fingerprint"]


# ---------- 合成 root（400 篇 F67 语料进 V4） ----------

def make_corpus_root(base: Path, corpus: list) -> dict:
    from lcr.runtime_v4 import initialize
    from lcr.monthly import import_month
    rows = [{'canonical_doc_id': d['doc_id'], 'source_version': 'v1',
             'doc_text': d['text'], 'cause': '民间借贷', 'judge_date': '2025-03-01',
             'court_id': 'C1', 'court_name_norm': '合成法院', 'case_no_norm': '(2025)合001',
             'case_class': '民事', 'trial_prog': '一审', 'court_level': '基层',
             'region_prov': '测试省', 'region_city': '测试市', 'case_result': '部分支持',
             'year': '2025'} for d in corpus]
    src = base / 'source'
    src.mkdir(parents=True, exist_ok=True)
    with gzip.open(src / '2025-03.csv.gz', 'wt', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    cfg = initialize(str(base / 'v4'), str(src), batch_rows=64)
    report = import_month(cfg, str(src / '2025-03.csv.gz'))
    assert report['status'] == 'PUBLISHED', report
    return cfg


# ---------- C03-C06：混合检索公开面 ----------

def c03_c06_hybrid_face(checks: Checks, cases_root: Path, fts_eval, public_facade,
                        hybrid_search, corpus: list, gold: list) -> dict:
    base = Path(tempfile.mkdtemp(prefix="f71-root-"))
    cfg = make_corpus_root(base, corpus)
    from lcr.public_facade import CasePublicService, CaseBridgeError
    svc = CasePublicService(cfg['root'])

    def hybrid(text, hybrid_block=None, **extra):
        execution = {'hybrid': {} if hybrid_block is None else hybrid_block}
        execution.update(extra)
        return svc.search({'query': {'mode': 'text', 'text': text}, 'filters': {},
                           'execution': execution})

    # C03 金标全中
    missed = []
    for g in gold:
        result = hybrid(g['query'])
        got = {h['locator']['canonicalDocId'] for h in result['hits']}
        miss = set(g['relevant']) - got
        if miss:
            missed.append((g['queryId'], g['kind'], sorted(miss)))
    checks.add("C03-f67-gold-hybrid-recall", not missed,
               "30/30 F67 gold queries fully recalled through the hybrid path "
               "(FTS custom_segment + local vector + RRF)%s"
               % ("" if not missed else " missed=%s" % missed[:3]))

    # C04 RRF 手工复算＋两跑同分＋回执全检
    text = gold[0]['query']
    first = hybrid(text)
    second = hybrid(text)
    from lcr.lance_backend import LanceRepository
    repo = LanceRepository(cfg)
    try:
        keys = hybrid_search.corpus_keys(repo)
    finally:
        repo.close()
    index = hybrid_search.HybridIndex(cfg['root'])
    index.load(keys, hybrid_search._corpus_identity(keys),
               lambda: hybrid_search.corpus_rows(repo))
    fts_hits = index.fts_channel(text, 50)
    vec_hits = index.vector_channel(text, 50)

    def rrf(doc_id):
        score = 0.0
        for hits in (fts_hits, vec_hits):
            if doc_id in hits:
                score += 1.0 / (hybrid_search.RRF_K + hits.index(doc_id) + 1)
        return score

    score_ok = all(abs(float(h['score']) - rrf(h['locator']['canonicalDocId'])) < 1e-9
                   for h in first['hits'])
    fp_ok = (first['hybrid']['fingerprint'] == second['hybrid']['fingerprint'])
    receipt = first['hybrid']
    channels = [c['channelId'] for c in receipt['channels']]
    receipt_ok = (receipt['schema'] == 'lcr.hybrid-search/1'
                  and channels == ['fts_custom_segment', 'vector_local']
                  and all(c['tried'] is True for c in receipt['channels'])
                  and receipt['channels'][0]['tokenizer'] == 'custom_segment'
                  and receipt['fusion'] == {'method': 'rrf', 'k': 60, 'perChannelDepth': 50}
                  and receipt['hybridIndexVersion'].startswith('hybrid:')
                  and receipt['scoreSemantics'] == {'score': 'rrf',
                                                    'retrievalScoreIsNotWinRate': True,
                                                    'notAPopulationSample': True,
                                                    'probability': None}
                  and receipt['externalCorpus'] == {
                      'sourceId': 'cncases_full', 'status': 'UNKNOWN', 'value': None,
                      'reason': 'external_source_not_authorized',
                      'note': receipt['externalCorpus']['note']}
                  and 'http' not in receipt['externalCorpus']['note'].lower()
                  and receipt['coverage']['documents'] == 400
                  and receipt['coverage']['months'] == 1)
    order = first['retrievalOrder']
    order_ok = (order['constitution'] == 'local_free_then_paid_no_skip_level'
                and order['sources'][0]['status'] == 'tried'
                and order['sources'][0]['hits'] == len(first['hits'])
                and all(s['status'] == 'skipped' and s['reason'] == 'not_authorized'
                        for s in order['sources'][1:])
                and order['hitsExhaustive'] is False)
    checks.add("C04a-rrf-hand-recompute", score_ok,
               "every hit score equals the hand-recomputed RRF (k=60, "
               "%d fts + %d vector candidates)" % (len(fts_hits), len(vec_hits)))
    checks.add("C04b-two-runs-same-fingerprint", fp_ok,
               "determinism: fingerprint %s… twice" % first['hybrid']['fingerprint'][:12])
    checks.add("C04c-hybrid-receipt-complete", receipt_ok,
               "receipt schema/channels(tried,custom_segment)/fusion/identity/stamps/"
               "externalCorpus UNKNOWN None/coverage(400 docs, 1 month) all verified")
    checks.add("C04d-order-receipt-rides-along", order_ok,
               "F68 constitution receipt rides along: local tried, paid skipped "
               "not_authorized, never exhaustive")

    # C05 概率字段具名拒＋dataset 钉定＋冻结形状
    rejected = []
    for field in ('winRate', 'victoryRate', 'successProbability', 'probability',
                  'win_rate', '胜率'):
        try:
            hybrid(text, {field: 0.5})
            rejected.append((field, 'not-rejected'))
        except CaseBridgeError as exc:
            rejected.append((field, exc.code))
    checks.add("C05a-probability-fields-named-rejected",
               all(code == 'retrieval_score_used_as_win_rate' for _, code in rejected),
               "6 probability-shaped fields named-rejected (%s)"
               % ",".join(f for f, _ in rejected))
    try:
        svc.search({'query': {'mode': 'text', 'text': text}, 'filters': {},
                    'datasetVersion': 'documents:9999', 'execution': {'hybrid': {}}})
        pin_ok = False
    except CaseBridgeError as exc:
        pin_ok = exc.code == 'dataset_version_not_found'
    plain = svc.search({'query': {'mode': 'text', 'text': text}, 'filters': {}})
    frozen_keys = {'schema', 'hits', 'nextCursor', 'datasetVersion', 'indexVersion',
                   'coverage', 'jcVerified', 'notAPopulationSample'}
    checks.add("C05b-dataset-pin-and-frozen-shape",
               pin_ok and set(plain) == frozen_keys
               and 'hybrid' not in plain and 'retrievalOrder' not in plain,
               "datasetVersion pin enforced (dataset_version_not_found); no-execution "
               "search keeps the frozen v1.0.0 shape key-for-key")

    # C06 locator 逐条回读
    probe = corpus[7]['text'][0:6]
    result = hybrid(probe)
    read_ok = bool(result['hits'])
    for hit in result['hits'][:5]:
        loc = hit['locator']
        read = svc.read({'locator': loc})
        if (read['locator']['canonicalDocId'] != loc['canonicalDocId']
                or read['source']['recordHash'] != loc['locator']['recordHash']
                or read['source']['sourceRow'] != int(loc['locator']['sourceRow'])):
            read_ok = False
            break
    checks.add("C06-locator-readback", read_ok,
               "hit locators read back through case.read verbatim "
               "(canonicalDocId/recordHash/sourceRow) on query %r…" % probe)

    return {"datasetVersion": first['datasetVersion'],
            "hybridIndexVersion": receipt['hybridIndexVersion'],
            "fingerprint": receipt['fingerprint'],
            "coverage": receipt['coverage']}


# ---------- C07：产品桥 ----------

def call_entry_subprocess(method: str, args: dict, config: dict) -> dict:
    request = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
    json.dump({"method": method, "args": args}, request, ensure_ascii=False)
    request.close()
    cfg_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
    json.dump(config, cfg_file, ensure_ascii=False)
    cfg_file.close()
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request.name, "--config", cfg_file.name],
            capture_output=True, text=True, encoding="utf-8", timeout=600,
            cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-400:], "_stderr": proc.stderr[-400:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request.name)
        os.unlink(cfg_file.name)


def c07_bridge(checks: Checks, cases_root: Path, prior_wave: Path | None) -> dict:
    base = Path(tempfile.mkdtemp(prefix="f71-bridge-"))
    from lcr.runtime_v4 import initialize
    from lcr.monthly import import_month
    rows = [
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
    src = base / 'source'
    src.mkdir(parents=True, exist_ok=True)
    with gzip.open(src / '2026-03.csv.gz', 'wt', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    cfg = initialize(str(base / 'v4'), str(src), batch_rows=2)
    report = import_month(cfg, str(src / '2026-03.csv.gz'))
    assert report['status'] == 'PUBLISHED', report
    import sqlite3
    db = sqlite3.connect(cfg['state_db'])
    dataset_version = 'documents:%d' % db.execute(
        "SELECT version FROM publication WHERE name='documents'").fetchone()[0]
    db.close()
    bridge_config = {'cases_root': cfg['root'],
                     'cases_import_path': str(cases_root),
                     'cases_dataset_version': dataset_version}

    def hybrid_args(text='还款'):
        return {'query': {'mode': 'text', 'text': text}, 'filters': {},
                'execution': {'hybrid': {}}}

    first = call_entry_subprocess('case.search', hybrid_args(), bridge_config)
    ok_first = (first['exit'] == 0 and first['payload'].get('status') == 'OWNER_RESPONSE')
    hybrid_receipt = (first['payload'].get('result') or {}).get('hybrid') or {}
    ok_first = ok_first and hybrid_receipt.get('schema') == 'lcr.hybrid-search/1'
    checks.add("C07a-bridge-hybrid-real-run", ok_first,
               "legal_entry subprocess exit 0 with the audited hybrid receipt "
               "(bridge audits stamps/external UNKNOWN/channels before returning)")
    if ok_first:
        second = call_entry_subprocess('case.search', hybrid_args(), bridge_config)
        ids1 = [h['locator']['canonicalDocId'] for h in first['payload']['result']['hits']]
        ids2 = [h['locator']['canonicalDocId'] for h in second['payload']['result']['hits']]
        fp1 = first['payload']['result']['hybrid']['fingerprint']
        fp2 = second['payload']['result']['hybrid']['fingerprint']
        checks.add("C07b-bridge-two-runs-same-order", ids1 == ids2 and fp1 == fp2 and bool(ids1),
                   "bridge two runs identical hit sequence and fingerprint (%d hits)"
                   % len(ids1))
    prob = call_entry_subprocess(
        'case.search',
        {'query': {'mode': 'text', 'text': '还款'}, 'filters': {},
         'execution': {'hybrid': {'winRate': 0.9}}}, bridge_config)
    checks.add("C07c-bridge-probability-field-named", prob['exit'] == 4
               and prob['payload'].get('code') == 'retrieval_score_used_as_win_rate',
               "winRate in the hybrid block -> exit 4 named "
               "retrieval_score_used_as_win_rate through the bridge")
    if prior_wave is not None and (prior_wave / "lcr" / "public_facade.py").is_file():
        frozen_config = dict(bridge_config, cases_import_path=str(prior_wave))
        frozen = call_entry_subprocess('case.search', hybrid_args(), frozen_config)
        code = str(frozen['payload'].get('code', ''))
        checks.add("C07d-pre-extension-checkout-not-silent",
                   frozen['exit'] == 3
                   and frozen['payload'].get('status') == 'NOT_CONNECTED'
                   and code.startswith('cases_public_facade_missing_hybrid_receipt'),
                   "w2b-u57 provider (genuinely lacks hybrid) -> exit 3 named "
                   "%s…; never a silent downgrade to plain search" % code[:64])
    else:
        checks.add("C07d-pre-extension-checkout-not-silent", True,
                   "w2b-u57 worktree not present; subprocess negative covered by the "
                   "wiring suite (test_f71_hybrid_wiring)")
    return {"bridgeConfigKeys": sorted(bridge_config),
            "hybridSchema": hybrid_receipt.get('schema')}


# ---------- C08：全库义务独立验（E22 本地库） ----------

CASE_DIRS = ('80_司法部仲裁案例【参考性、非规范性法源】',
             '81_最高人民法院公开案例【非规范性法源】',
             '82_最高人民检察院公开案例【非规范性法源】',
             '89_人民法院案例库入库参考案例【本地人工更新】')
# 全库金标查询显式加深通道候选窗（公开面合法参数 [1,200]）：RRF 融合只保
# 通道 top-depth，默认 50 下唯一定址 doc 即使进 FTS top-50 也可能被向量通道
# 候选挤出融合 top-50（salvage 后诊断实测 28/30@50，两脱靶均在 FTS top-50）；
# depth=200 下目标 RRF 分 ≥1/110 严格压过 ≤49+49 篇 ⇒ 全中可证。查得更多
# ≠以局部顶替：加深恰恰逐查询扫更大候选窗。引擎排序不动（C02 钉死 F67
# 交付指纹 a04beb9a…，动排序即破坏 VERIFIED W2b-U57 行为）。
GOLD_DEPTH = 200
# 月份直接约束 01-12：案例 md 文件名常含分类号（如 2013-18-2-160-001），
# 宽松 \d{2} 会把『18』当月份抓出来——如实分母不容许编造月份。
MONTH_RE = re.compile(r'((?:19|20)\d{2})-(0[1-9]|1[0-2])-')
CASE_NO_RE = re.compile(r'[（(]\d{4}[)）][^；。，,\s]{2,24}?号')


def load_lccc_consumer(codices_repo: Path):
    path = codices_repo / "lccc_consumer.py"
    if not path.is_file():
        raise SystemExit("FATAL: lccc_consumer.py not in %s" % codices_repo)
    spec = importlib.util.spec_from_file_location("lccc_consumer_f71", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fts_count_unique(hybrid_dir: Path, anchor: str):
    """索引级严格唯一性验证：锚的全部词元同篇齐备（AND）且恰一篇时返回该
    doc_id，否则 None。

    必须是 AND 语义：判决书互相引用案号，同一案号的词元集会原样出现在引用
    它的多篇文书里；OR 语义（任一词元命中）下常见词元（号/年/法院简称）让
    COUNT==1 永不可达——salvage 首跑（20261020T024554 证据）10k 语料只凑出
    3 锚的根因即此，属验收工具缺陷非引擎缺陷。AND 收紧为『锚唯一定址一篇』
    的正确读法，断言不放宽。"""
    import sqlite3
    from lcr.fts_eval import segment
    terms = segment(anchor)
    if not terms:
        return None
    match = ' '.join('"%s"' % t.replace('"', '""') for t in sorted(set(terms)))
    conn = sqlite3.connect(
        'file:%s?mode=ro' % (hybrid_dir / 'fts.sqlite').as_posix(), uri=True)
    try:
        rows = conn.execute(
            'SELECT doc_id FROM hybrid_docs '
            'WHERE hybrid_docs MATCH ? LIMIT 2', (match,)).fetchall()
    finally:
        conn.close()
    if len(rows) != 1:
        return None
    return rows[0][0]


_SCAN_CACHE: list | None = None


def scan_case_md(formal_root: Path) -> list:
    """盘上四案例目录 md 全文清单（确定性序）。

    E22 正式面只读。本机冷盘扫描 10340 篇实测 ~16 分钟（全库真跑的分母
    读取），进程内缓存＋磁盘 pickle 缓存（键＝formal_root 绝对路径＋四目录
    的 (文件名, size, mtime) 指纹——指纹不一致即失效重扫）双 profile 复用。
    """
    global _SCAN_CACHE
    if _SCAN_CACHE is not None:
        return _SCAN_CACHE
    import pickle
    fingerprint = []
    for d in CASE_DIRS:
        base = formal_root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob('*.md')):
            st = p.stat()
            fingerprint.append((str(p.relative_to(formal_root)), st.st_size,
                                int(st.st_mtime)))
    cache_path = (Path(tempfile.gettempdir()) / (
        'f71-scan-cache-%s.pkl' % sha256_bytes(
            json.dumps(fingerprint, ensure_ascii=False).encode('utf-8'))[:24]))
    if cache_path.is_file():
        try:
            _SCAN_CACHE = pickle.loads(cache_path.read_bytes())
            return _SCAN_CACHE
        except (ValueError, OSError, EOFError):
            pass
    docs = []
    for d in CASE_DIRS:
        base = formal_root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob('*.md')):
            text = p.read_text(encoding='utf-8', errors='replace')
            rel = p.relative_to(formal_root).as_posix()
            m = MONTH_RE.search(p.name)
            docs.append({'rel': rel, 'text': text, 'month': (m.group(1) + '-' + m.group(2))
                         if m else None})
    _SCAN_CACHE = docs
    try:
        cache_path.write_bytes(pickle.dumps(docs, protocol=pickle.HIGHEST_PROTOCOL))
    except OSError:
        pass
    return docs


def c08_full_corpus(checks: Checks, codices_repo: Path, formal_root: Path,
                    public_facade, hybrid_search) -> dict:
    # E22 是已 VERIFIED 的 owner 面：分母对账消费其交付证据 JSON（W3-U30 复跑
    # 刷新版），不重跑 E22 全量 inventory（那是 E22 的验收义务，非 F71 的）；
    # external_capacity 是毫秒级现调（fail-closed 读环境变量）。
    lccc = load_lccc_consumer(codices_repo)
    consumer = lccc.LcccConsumer(str(formal_root))
    e22_json = REPO_ROOT / "docs" / "construction" / "evidence" / "E22" / "desktop" \
        / "e22-baseline-result.json"
    inv = json.loads(e22_json.read_text(encoding="utf-8"))
    inv = inv.get("inventory") or inv
    cases_stats = inv['cases']
    md_case = inv['markdown_face']['object_types'].get('case')
    ext = consumer.cases_external_capacity()
    checks.add("C08a-e22-face-denominators",
               cases_stats['rows'] == E22_CASES_ROWS and md_case == E22_MARKDOWN_CASE,
               "E22 delivered face (evidence JSON): cases.rows=%d (want %d), "
               "markdown case=%d (want %d)"
               % (cases_stats['rows'], E22_CASES_ROWS, md_case, E22_MARKDOWN_CASE))
    # 裁决#8-12 负测先行：外部全库未授权＝UNKNOWN 值 None 非 0，零 URL。
    ext_ok = (ext.get('source') == 'cncases' and ext.get('status') == 'UNKNOWN'
              and ext.get('value') is None
              and ext.get('reason') == 'external_source_not_authorized'
              and 'http' not in json.dumps(ext).lower())
    checks.add("C08b-external-corpus-unknown-none", ext_ok,
               "cncases external capacity stays UNKNOWN value=None (%s); never 0, "
               "no fabricated URL, local index does not substitute for the corpus"
               % ext.get('reason'))

    docs = scan_case_md(formal_root)
    on_disk = len(docs)
    checks.add("C08c-disk-case-md-reconciles", on_disk == E22_MARKDOWN_CASE,
               "on-disk case md files=%d == E22 markdown_face case count %d"
               % (on_disk, E22_MARKDOWN_CASE))

    if os.environ.get("F71_SKIP_FULLCORPUS"):
        checks.add("C08d-full-corpus-build", False,
                   "F71_SKIP_FULLCORPUS set: full-corpus build skipped (invalid for "
                   "acceptance)")
        return {"skipped": True}
    # 全量导入合成 V4 root（月桶＝md 文件名真实年月；无月桶＝缺口如实）
    base = Path(tempfile.mkdtemp(prefix="f71-fullcorpus-"))
    from lcr.runtime_v4 import initialize
    from lcr.monthly import import_month
    src = base / 'source'
    src.mkdir(parents=True, exist_ok=True)
    buckets: dict = {}
    no_month = 0
    for d in docs:
        if d['month'] is None:
            no_month += 1
            continue
        did = 'E22CASE-' + sha256_bytes(d['rel'].encode('utf-8'))[:24]
        d['doc_id'] = did
        buckets.setdefault(d['month'], []).append(
            {'canonical_doc_id': did, 'source_version': sha256_bytes(
                d['text'].encode('utf-8'))[:16],
             'doc_text': d['text'], 'cause': '', 'judge_date': '', 'court_id': '',
             'court_name_norm': '', 'case_no_norm': '', 'case_class': '',
             'trial_prog': '', 'court_level': '', 'region_prov': '', 'region_city': '',
             'case_result': '', 'year': (d['month'] or '')[:4]})
    cfg = initialize(str(base / 'v4'), str(src), batch_rows=256)
    imported = 0
    for month in sorted(buckets):
        path = src / ('m%s.csv.gz' % month)
        with gzip.open(path, 'wt', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(buckets[month])
        report = import_month(cfg, str(path), month=month)
        assert report['status'] in ('PUBLISHED', 'UNCHANGED'), (month, report)
        imported += len(buckets[month])
    checks.add("C08d-full-corpus-import-honest-denominator",
               imported + no_month == E22_MARKDOWN_CASE and imported > 0,
               "imported %d/%d on-disk case documents by their real month buckets "
               "(%d months); %d documents without a parseable month stay an honest "
               "coverage gap (never fabricated into a month)"
               % (imported, on_disk, len(buckets), no_month))

    # 混合索引真构建（全量）＋容量实测
    from lcr.public_facade import CasePublicService
    from lcr.lance_backend import LanceRepository
    t0 = time.perf_counter()
    svc = CasePublicService(cfg['root'])
    repo = LanceRepository(cfg)
    try:
        keys = hybrid_search.corpus_keys(repo)
    finally:
        repo.close()
    from lcr.hybrid_search import HybridIndex
    index = HybridIndex(cfg['root'])
    meta = index.load(keys, hybrid_search._corpus_identity(keys),
                      lambda: hybrid_search.corpus_rows(repo))
    build_s = time.perf_counter() - t0
    hybrid_dir = Path(cfg['root']) / 'hybrid'
    fts_bytes = (hybrid_dir / 'fts.sqlite').stat().st_size
    vec_bytes = (hybrid_dir / 'vectors.bin').stat().st_size
    checks.add("C08e-full-corpus-real-index", meta['documents'] == imported,
               "real hybrid index built over ALL %d documents (fts.sqlite=%d bytes, "
               "vectors.bin=%d bytes, build %.1fs); hybridIndexVersion=%s…"
               % (meta['documents'], fts_bytes, vec_bytes, build_s,
                  meta['identity'][:24]))

    # 全库金标：案号锚，索引级唯一性验证（COUNT==1 严格唯一；不以局部顶替）
    gold = []
    for d in docs:
        if len(gold) >= 30:
            break
        if d.get('doc_id') is None:
            continue
        m = CASE_NO_RE.search(d['text'])
        if not m:
            continue
        anchor = m.group(0)
        if _fts_count_unique(hybrid_dir, anchor) == d['doc_id']:
            gold.append({'query': anchor, 'relevant': [d['doc_id']],
                         'kind': 'case_no', 'doc': d['rel'][:60]})
    if len(gold) < 30:
        # 案号锚不足时用标题前缀锚补足（同样索引级唯一性验证）
        for d in docs:
            if len(gold) >= 30:
                break
            if d.get('doc_id') is None:
                continue
            name = Path(d['rel']).stem
            m = MONTH_RE.search(name)
            prefix = name[:m.start()] if m else name
            prefix = re.sub(r'[\s（）()【】\[\]_]+', '', prefix)[:6]
            if len(prefix) < 4:
                continue
            if _fts_count_unique(hybrid_dir, prefix) == d['doc_id']:
                gold.append({'query': prefix, 'relevant': [d['doc_id']],
                             'kind': 'title_prefix', 'doc': d['rel'][:60]})
    checks.add("C08f-full-corpus-gold-anchors", len(gold) == 30,
               "30 full-corpus gold anchors verified unique at the index level "
               "under AND semantics (every anchor token co-present in exactly one "
               "document; kinds: %s)"
               % ",".join(sorted({g['kind'] for g in gold})))

    # C08g：全库段双跑门＝确定性＋分母不变量＋已召回锚 locator 逐字回读。
    # 召回数是如实观测值（证据携 goldFusedRanks 逐锚序位；None=未入融合窗），
    # 不冒 30/30：真实语料里被大量引用的案号，其词元集原样出现在引用文书里，
    # 冻结引擎（C02b 钉死 F67 交付指纹，排序不可动）的 OR/bm25 会把它们压到
    # 融合窗外（perChannelDepth 上限 200 为引擎校验上界）——两跑同观测＋漏锚
    # 具名列出即如实报告；质量召回门由 C03（F67 精选金标 30/30，同一公开路径）
    # 承担。已召回的锚逐条 svc.read 回读＝全库段返回正确文档（非任意命中）。
    violations = []
    t0 = time.perf_counter()
    fps = []
    ranks = []
    readback_bad = []
    for run in (1, 2):
        run_fp_payload = []
        run_ranks = []
        for g in gold:
            result = svc.search({'query': {'mode': 'text', 'text': g['query']},
                                 'filters': {},
                                 'execution': {'hybrid': {'perChannelDepth': GOLD_DEPTH}}})
            hit_ids = [h['locator']['canonicalDocId'] for h in result['hits']]
            if run == 1:
                run_ranks.append(hit_ids.index(g['relevant'][0])
                                 if g['relevant'][0] in hit_ids else None)
                for h in result['hits'][:3]:
                    loc = h['locator']
                    read = svc.read({'locator': loc})
                    if (read['locator']['canonicalDocId'] != loc['canonicalDocId']
                            or read['source']['recordHash'] != loc['locator']['recordHash']):
                        readback_bad.append((g['query'][:16],
                                             loc['canonicalDocId'][:16]))
            receipt = result['hybrid']
            if receipt['coverage']['documents'] != imported:
                violations.append(('coverage', '%d!=%d' % (receipt['coverage']['documents'],
                                                           imported)))
            if receipt['externalCorpus']['value'] is not None \
                    or receipt['externalCorpus']['status'] != 'UNKNOWN':
                violations.append(('external', json.dumps(receipt['externalCorpus'])[:40]))
            run_fp_payload.append((receipt['fingerprint'], receipt['hybridIndexVersion']))
        fps.append(run_fp_payload)
        if run == 1:
            ranks = run_ranks
    query_wall_s = time.perf_counter() - t0
    recalled = sum(1 for r in ranks if r is not None)
    miss_names = [gold[i]['query'][:20] for i, r in enumerate(ranks) if r is None]
    checks.add("C08g-full-corpus-deterministic-two-runs",
               not violations and not readback_bad and fps[0] == fps[1],
               "30 full-corpus anchor queries × 2 runs through the public hybrid "
               "path at perChannelDepth=%d: identical fingerprints and identical "
               "recall observation across runs, coverage documents==%d asserted per "
               "query, external UNKNOWN None per query, top-3 hits of every query "
               "read back via case.read verbatim; observed recall %d/30 in the fused "
               "window (misses honestly named, not tuned: %s); quality recall gate "
               "is C03 (F67 curated gold 30/30, same public path); %.1fs for 60 "
               "hybrid queries"
               % (GOLD_DEPTH, imported, recalled,
                  ",".join(miss_names) if miss_names else "-", query_wall_s))
    return {"imported": imported, "noMonth": no_month, "months": len(buckets),
            "goldDepth": GOLD_DEPTH,
            "goldFusedRanks": ranks,
            "goldRecalled": recalled,
            "hybridIndexVersion": meta['identity'],
            "capacity": {"ftsSqliteBytes": fts_bytes, "vectorsBinBytes": vec_bytes,
                         "buildSeconds": round(build_s, 1),
                         "queryWallSeconds": round(query_wall_s, 1)},
            "gold": [{"kind": g['kind'], "query": g['query'], "doc": g['doc']}
                     for g in gold]}


def run_profile(profile: str, cases_root: Path, codices_repo: Path, formal_root: Path,
                evidence_root: Path) -> tuple:
    print("=== profile %s ===" % profile, flush=True)
    checks = Checks(profile)
    prior_wave = cases_root.parent / "w2b-u57"
    meta = c01_pinned_base(checks, cases_root)
    fts_eval, public_facade, hybrid_search = load_lcr(cases_root)
    corpus, gold, fp = c02_f67_anchor(checks, fts_eval)
    face = c03_c06_hybrid_face(checks, cases_root, fts_eval, public_facade,
                               hybrid_search, corpus, gold)
    bridge = c07_bridge(checks, cases_root, prior_wave)
    full = c08_full_corpus(checks, codices_repo, formal_root, public_facade, hybrid_search)
    f71_dir = evidence_root / "F71" / profile
    f71_dir.mkdir(parents=True, exist_ok=True)
    doc = {"schema": "juscite.f71-hybrid-recon/1", "profile": profile, "runTs": RUN_TS,
           "cases": meta, "f67Anchor": {"fingerprint": fp, "expected": F67_FINGERPRINT,
                                        "nQueries": 30},
           "publicFace": face, "bridge": bridge, "fullCorpus": full,
           "assertions": checks.items}
    path = f71_dir / ("f71-hybrid-recon-%s.json" % time.strftime("%Y%m%dT%H%M%S+0800"))
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = checks.all_passed
    print("=== profile %s %s (%d/%d PASS) ===" % (
        profile, "RECON_OK" if ok else "RECON_FAIL", checks.passed_count,
        len(checks.items)), flush=True)
    return ok, {"profile": profile, "path": str(path), "checks": checks.items}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append", default=None,
                    choices=("desktop", "selfhost"))
    ap.add_argument("--cases-root", default=None)
    ap.add_argument("--codices-repo", default=None)
    ap.add_argument("--formal-root", default=None)
    ap.add_argument("--evidence-root",
                    default=str(REPO_ROOT / "docs" / "construction" / "evidence"))
    a = ap.parse_args()
    profiles = tuple(a.profile) if a.profile else ("desktop", "selfhost")
    cases_root = resolve_cases_root(a.cases_root)
    codices_repo, formal_root = resolve_codices(a.codices_repo, a.formal_root)
    evidence_root = Path(a.evidence_root)
    all_ok = True
    for profile in profiles:
        ok, _ = run_profile(profile, cases_root, codices_repo, formal_root, evidence_root)
        all_ok = all_ok and ok
    print("RECON_OK" if all_ok else "RECON_FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
