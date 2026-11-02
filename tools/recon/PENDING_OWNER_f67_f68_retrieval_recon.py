# -*- coding: utf-8 -*-
"""F67+F68 检索候选评测与顺序宪法对账（PENDING_OWNER 版，工单 W2b-U57）。

F67：SQLite 三方案（FTS5 unicode61/自建分词/trigram）在 seed 钉定合成语料上
实测金标召回/延迟/容量，两跑同分；PG zhparser/pg_jieba 候选在 E08 compose PG
（lh-pg-e08，postgres:17-alpine）如实执行——扩展不可用＝结论具名 unavailable，
不造分不阻塞（候选评测非安装义务，不凭选核默裁默认预分词 tsvector）。
F68：检索顺序宪法（本地免费→付费不可跳级）后端可审计——cases 公开面真跑
回执＋产品桥真跑强制回执＋跳级/伪零命中/无回执/理由出闭集全具名拒。

分段（每 profile 各跑一遍，desktop/selfhost 双 profile）：
  C01 cases 仓钉定基：worktree 含 main@916ddf5、树净、迁移 manifest 字节自洽；
      主检出盘上 public_facade.py == 钉定 sha256 38c1959c…（漂移即 FATAL）。
  C02-C05 F67 SQLite：合成语料/金标确定性、三方案真跑、两跑同分指纹。
  C06 F67 PG 候选（selfhost 主测；desktop 记 N/A）：docker exec psql 逐扩展
      如实探测，可用即真评测（召回/服务端延迟/容量），不可用即具名 unavailable。
  C07-C08 cases 公开面真跑＋顺序回执正向（F68）。
  C09 产品桥真跑（legal_entry 子进程，cases_import_path 钉本波 worktree），
      两跑命中序列一致；回执经桥审计。
  C10 公开面负测×5：重排拒/穷尽不可达具名拒/伪零命中拒/已授权无适配器
      failed 具名/未知授权来源拒。
  C11 桥负测×3：预扩展检出（钉定基）→ cases_public_facade_missing_retrieval_order
      不静默放行；审计函数载荷负测×6；未配置 NOT_CONNECTED 语义保留。
  C12 证据落盘 evidence/F67|F68/<profile>/ ＋ 两形态统一报告。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f67_f68_retrieval_recon.py
  [--profile desktop|selfhost|both] [--cases-root <cases worktree>]
  [--evidence-root docs/construction/evidence]

exit 0＝所跑 profile 全部断言过（RECON_OK）；全程合成材料、零网络出站
（唯一外部交互=E08 本机 docker 容器 psql）、%APPDATA% 零触碰。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUN_TS = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
REPO_ROOT = Path(__file__).resolve().parents[2]          # juscite worktree root
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
ENTRY_CSV = REPO_ROOT / "docs" / "construction" / "authority" / "14-Python入口证据.csv"

CASES_PIN_COMMIT = "916ddf5d26fa798f0931eb8b27c758a8e7eca8e1"
CASES_PIN_FACADE_SHA = "38c1959c30412192e6abd71ad683f4cc285ae9e4d9bfaeee7d4ca78cea61942f"
PG_CONTAINER = "lh-pg-e08"
PG_EXTENSIONS = ("zhparser", "pg_jieba")
PG_EVAL_SCHEMA = "f67_eval"
RECEIPT_SCHEMA = "lcr.retrieval-order/1"
CONSTITUTION = "local_free_then_paid_no_skip_level"
LADDER = ("local_corpus", "cncases_full", "paid_legal_api", "court_case_library")

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
        print("[%s][%s] %s — %s" % ("PASS" if ok else "FAIL", self.profile, check_id, detail))
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
    """JUSCITE_CASES_ROOT > 本波 worktree >（合并后回退）含扩展的主检出。"""
    if explicit:
        return Path(explicit)
    override = os.environ.get("JUSCITE_CASES_ROOT")
    if override:
        return Path(override)
    for parent in REPO_ROOT.parents:
        if parent.name == "jusbench工作区":
            guess = (parent.parent / "legal-cn-cases工作区" / "legal-cn-cases"
                     / ".local" / "worktrees" / "w2b-u57")
            if (guess / "lcr" / "public_facade.py").is_file():
                return guess
            break
    for parent in REPO_ROOT.parents:
        if parent.name == "jusbench工作区":
            main_checkout = parent.parent / "legal-cn-cases工作区" / "legal-cn-cases"
            facade = main_checkout / "lcr" / "public_facade.py"
            if facade.is_file() and b"SCHEMA_RETRIEVAL_ORDER" in facade.read_bytes():
                return main_checkout
            break
    raise SystemExit("FATAL: cases w2b-u57 worktree not found; "
                     "pass --cases-root or set JUSCITE_CASES_ROOT")


def git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", timeout=60)


def c01_pinned_base(checks: Checks, cases_root: Path) -> dict:
    if not checks.add("C01a-pin-ancestor",
                      git(["merge-base", "--is-ancestor", CASES_PIN_COMMIT, "HEAD"],
                          cases_root).returncode == 0,
                      "cases HEAD contains pinned base %s" % CASES_PIN_COMMIT[:12]):
        raise SystemExit("FATAL: pinned base drifted (工单红线：漂移即 FATAL)")
    status = git(["status", "--porcelain"], cases_root)
    checks.add("C01b-worktree-clean", status.returncode == 0 and not status.stdout.strip(),
               "cases tree clean (porcelain empty)")
    head = git(["rev-parse", "HEAD"], cases_root).stdout.strip()
    # 迁移 manifest 字节自洽（worktree 内 tests/*.py == v3_manifest.json 钉定）
    manifest = json.loads((cases_root / "migration" / "v3_manifest.json").read_text(encoding="utf-8"))
    mismatches = [i["path"] for i in manifest["files"]
                  if i["path"].startswith("tests/")
                  and sha256_bytes((cases_root / i["path"]).read_bytes()) != i["sha256"]]
    checks.add("C01c-migration-manifest-bytes", not mismatches,
               "tests/ manifest bytes intact (%s)" % ("ok" if not mismatches else str(mismatches)))
    # 主检出（P08 钉定路径）盘上字节 == 38c1959c…（扩展前冻结基；漂移即 FATAL）
    pin_path, pin_sha = None, None
    import csv
    with open(ENTRY_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["entry_id"] == "P08":
                pin_path, pin_sha = row["path"], row["sha256"]
                break
    actual = sha256_bytes(Path(pin_path).read_bytes())
    if not checks.add("C01d-main-checkout-pin-bytes", actual == pin_sha,
                      "P08 main checkout disk sha %s… == pinned %s…" % (actual[:12], pin_sha[:12])):
        raise SystemExit("FATAL: frozen base checkout drifted from P08 pin")
    facade_sha = sha256_bytes((cases_root / "lcr" / "public_facade.py").read_bytes())
    checks.add("C01e-extension-present",
               b"SCHEMA_RETRIEVAL_ORDER" in (cases_root / "lcr" / "public_facade.py").read_bytes(),
               "extended facade present on branch (sha256 %s…, differs from base by design)"
               % facade_sha[:12])
    return {"casesRoot": str(cases_root), "casesHead": head,
            "pinnedBase": CASES_PIN_COMMIT, "pinnedFacadeSha256": pin_sha,
            "pinPath": pin_path,
            "mainCheckoutFacadeSha256": actual, "branchFacadeSha256": facade_sha}


def load_lcr(cases_root: Path):
    sys.path.insert(0, str(cases_root))
    import lcr.fts_eval as fts_eval            # noqa: F401
    import lcr.public_facade as public_facade  # noqa: F401
    return fts_eval, public_facade


def c02_c05_fts_eval(checks: Checks, fts_eval) -> dict:
    corpus_a, corpus_b = fts_eval.build_corpus(), fts_eval.build_corpus()
    sha_a, sha_b = fts_eval._corpus_sha(corpus_a), fts_eval._corpus_sha(corpus_b)
    checks.add("C02-corpus-deterministic", sha_a == sha_b and len(corpus_a) == 400,
               "corpus sha256 %s… x2 identical, 400 docs" % sha_a[:12])
    gold_a, gold_b = fts_eval.build_gold(corpus_a), fts_eval.build_gold(corpus_a)
    checks.add("C03-gold-deterministic", gold_a == gold_b and len(gold_a) == 30
               and all(g["relevant"] for g in gold_a),
               "gold x2 identical, 30 queries all anchored")
    workdir = tempfile.mkdtemp(prefix="f67-recon-")
    outcome = fts_eval.run_twice_for_determinism(workdir)
    checks.add("C05-two-runs-same-scores", outcome["identicalScores"],
               "score fingerprints %s… == %s… (wall-clock excluded by design)"
               % (outcome["run1Fingerprint"][:12], outcome["run2Fingerprint"][:12]))
    report = outcome["reports"][0]
    plans_ok = (set(report["plans"]) == {"unicode61", "custom_segment", "trigram"}
                and all(len(b["perQuery"]) == 30 and 0.0 <= b["recall"] <= 1.0
                        and b["capacity"]["sqliteBytes"] > 0 for b in report["plans"].values()))
    checks.add("C04-sqlite-three-plans-real", plans_ok,
               " ".join("%s recall=%.3f mrr=%.3f bytes=%d" % (p, b["recall"], b["mrr"],
                                                              b["capacity"]["sqliteBytes"])
                        for p, b in report["plans"].items()))
    return {"report": report, "run1Fingerprint": outcome["run1Fingerprint"],
            "run2Fingerprint": outcome["run2Fingerprint"], "corpusSha256": sha_a}


# ---------- C06：PG 候选评测（lh-pg-e08 如实执行/unavailable 具名） ----------

def docker_psql(sql: str, env_pairs: dict, user: str, dbname: str,
                timeout: int = 300, tuples_only: bool = False) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec", "-i"]
    for k, v in env_pairs.items():
        cmd += ["-e", "%s=%s" % (k, v)]
    cmd += [PG_CONTAINER, "psql", "-U", user, "-d", dbname,
            "-v", "ON_ERROR_STOP=1", "-X", "-q", "-f", "-"]
    if tuples_only:
        cmd += ["-tA"]
    return subprocess.run(cmd, input=sql.encode("utf-8"), capture_output=True, timeout=timeout)


def _psql_env(inspect_stdout: str) -> tuple:
    cfg = json.loads(inspect_stdout)[0]["Config"]["Env"]
    envv = dict(e.split("=", 1) for e in cfg if "=" in e)
    return (envv.get("POSTGRES_USER", "lh_app"), envv.get("POSTGRES_DB", "legal_harness"),
            {"PGPASSWORD": envv.get("POSTGRES_PASSWORD", "")})


def c06_pg_candidates(checks: Checks, gold: list, corpus: list) -> dict:
    section = {"container": PG_CONTAINER, "image": "postgres:17-alpine (E08 compose)",
               "extensions": {}, "conclusion": None}
    inspect = subprocess.run(["docker", "inspect", PG_CONTAINER], capture_output=True,
                             text=True, encoding="utf-8", timeout=60)
    if inspect.returncode != 0:
        section["conclusion"] = "unavailable"
        section["reason"] = "container %s not inspectable: %s" % (PG_CONTAINER, inspect.stderr.strip())
        checks.add("C06-pg-candidates-unavailable-named", True, section["reason"])
        return section
    user, dbname, psql_env = _psql_env(inspect.stdout)
    # 可用性探测（pg_available_extensions 是如实来源；不猜包是否存在）
    probe = docker_psql("SELECT name FROM pg_available_extensions "
                        "WHERE name IN ('zhparser','pg_jieba') ORDER BY 1;",
                        psql_env, user, dbname, tuples_only=True)
    if probe.returncode != 0:
        section["conclusion"] = "unavailable"
        section["reason"] = "psql probe failed: %s" % probe.stderr.decode("utf-8", "replace").strip()[:400]
        checks.add("C06-pg-candidates-unavailable-named", True, section["reason"])
        return section
    available = {ln.strip() for ln in probe.stdout.decode("utf-8", "replace").splitlines() if ln.strip()}
    # 逐扩展如实 CREATE EXTENSION（真实尝试；失败原样具名）
    creatable = {}
    for ext in PG_EXTENSIONS:
        if ext not in available:
            section["extensions"][ext] = {
                "status": "unavailable",
                "reason": "not in pg_available_extensions on %s (postgres:17-alpine carries "
                          "no third-party C extensions; candidate evaluation is not an "
                          "installation obligation)" % PG_CONTAINER}
            continue
        made = docker_psql("CREATE EXTENSION IF NOT EXISTS %s;" % ext,
                           psql_env, user, dbname)
        if made.returncode == 0:
            creatable[ext] = True
            section["extensions"][ext] = {"status": "created"}
        else:
            section["extensions"][ext] = {
                "status": "unavailable",
                "reason": "CREATE EXTENSION failed: %s"
                          % made.stderr.decode("utf-8", "replace").strip()[:500]}
    if not creatable:
        section["conclusion"] = "unavailable"
        named = "; ".join("%s=%s" % (e, v["status"]) for e, v in section["extensions"].items())
        checks.add("C06-pg-candidates-unavailable-named", True,
                   "zhparser/pg_jieba unavailable on lh-pg-e08 (named, no fabricated scores): " + named)
        return section
    # 可用 → 真评测（同金标、同语料；服务端时钟计时；容量 pg_total_relation_size）
    tsv_config = {"zhparser": "zhparser", "pg_jieba": "jiebacfg"}
    lines = ["CREATE SCHEMA IF NOT EXISTS %s;" % PG_EVAL_SCHEMA,
             "DROP TABLE IF EXISTS %s.queries CASCADE;" % PG_EVAL_SCHEMA,
             "DROP TABLE IF EXISTS %s.timings CASCADE;" % PG_EVAL_SCHEMA,
             "CREATE TABLE %s.queries(qid text PRIMARY KEY, txt text);" % PG_EVAL_SCHEMA]
    for g in gold:
        txt = g["query"].replace("$q$", "")
        lines.append("INSERT INTO %s.queries VALUES ('$q$%s$q$','$q$%s$q$');"
                     % (PG_EVAL_SCHEMA, g["queryId"], txt))
    for ext, cfgname in tsv_config.items():
        if ext not in creatable:
            continue
        table = "docs_%s" % ext
        lines += [
            "DROP TABLE IF EXISTS %s.%s;" % (PG_EVAL_SCHEMA, table),
            "CREATE TABLE %s.%s(doc_id text PRIMARY KEY, body text, tsv tsvector "
            "GENERATED ALWAYS AS (to_tsvector('%s', body)) STORED);" % (PG_EVAL_SCHEMA, table, cfgname),
            "CREATE INDEX %s_idx ON %s.%s USING GIN(tsv);" % (table, PG_EVAL_SCHEMA, table),
        ]
        for d in corpus:
            body = d["text"].replace("$q$", "")
            lines.append("INSERT INTO %s.%s VALUES ('$q$%s$q$', '$q$%s$q$');"
                         % (PG_EVAL_SCHEMA, table, d["doc_id"], body))
    lines += ["CREATE TABLE %s.timings(qid text, ext text, ms double precision, hits text[]);"
              % PG_EVAL_SCHEMA,
              "DO $eval$ DECLARE q record; t0 timestamptz; "
              + " ".join("h_%s text[];" % e for e in creatable) + " BEGIN"]
    for ext in creatable:
        lines.append(
            "FOR q IN SELECT qid, txt FROM %(s)s.queries LOOP "
            "t0 := clock_timestamp(); EXECUTE format("
            "'SELECT array_agg(doc_id) FROM (SELECT doc_id FROM %(s)s.docs_%(e)s "
            "WHERE tsv @@ plainto_tsquery('%(c)s', %%L) "
            "ORDER BY ts_rank(tsv, plainto_tsquery('%(c)s', %%L)) DESC, doc_id LIMIT 20)', q.txt, q.txt) "
            "INTO h_%(e)s; INSERT INTO %(s)s.timings VALUES (q.qid, '%(e)s', "
            "1000*(clock_timestamp()-t0), h_%(e)s); END LOOP;"
            % {"s": PG_EVAL_SCHEMA, "e": ext, "c": tsv_config[ext]})
    lines += ["END $eval$;"]
    run = docker_psql("\n".join(lines), psql_env, user, dbname)
    if run.returncode != 0:
        section["conclusion"] = "unavailable"
        section["reason"] = "eval script failed: %s" % run.stderr.decode("utf-8", "replace").strip()[:500]
        checks.add("C06-pg-candidates-unavailable-named", True, section["reason"])
        docker_psql("DROP SCHEMA IF EXISTS %s CASCADE;" % PG_EVAL_SCHEMA, psql_env, user, dbname)
        return section
    dump = docker_psql("COPY (SELECT ext, qid, ms, array_to_string(hits, ',') FROM %s.timings "
                       "ORDER BY ext, qid) TO STDOUT WITH CSV HEADER;" % PG_EVAL_SCHEMA,
                       psql_env, user, dbname, tuples_only=False)
    sizes = docker_psql("SELECT 'f67_eval:' || ext || '=' || "
                        "pg_size_pretty(pg_total_relation_size('%s.docs_' || ext)) "
                        "FROM (SELECT DISTINCT ext FROM %s.timings) t ORDER BY 1;"
                        % (PG_EVAL_SCHEMA, PG_EVAL_SCHEMA),
                        psql_env, user, dbname, tuples_only=True)
    size_lines = [ln.strip() for ln in sizes.stdout.decode("utf-8", "replace").splitlines()
                  if ln.strip()]
    plans = {}
    if dump.returncode == 0:
        import csv as _csv
        rows = {}
        reader = _csv.DictReader(dump.stdout.decode("utf-8", "replace").splitlines())
        for r in reader:
            rows.setdefault(r["ext"], {})[r["qid"]] = (
                float(r["ms"]), [h for h in (r.get("array_to_string") or "").split(",") if h])
        for ext in creatable:
            per = rows.get(ext, {})
            if not per:
                continue
            found = rr_total = relevant_total = 0
            lats = []
            for g in gold:
                ms, hits = per.get(g["queryId"], (0.0, []))
                rel = set(g["relevant"])
                relevant_total += len(rel)
                gold_hits = [h for h in hits if h in rel]
                found += len(gold_hits)
                rr_total += (1.0 / (hits.index(gold_hits[0]) + 1)) if gold_hits else 0.0
                lats.append(ms)
            plans[ext] = {"recall": found / relevant_total if relevant_total else 0.0,
                          "mrr": rr_total / len(gold),
                          "latencyServerMsMean": sum(lats) / len(lats) if lats else 0.0,
                          "capacity": [s for s in size_lines if ext in s]}
    section["plans"] = plans
    section["conclusion"] = "measured" if plans else "unavailable"
    if plans:
        checks.add("C06-pg-candidates-measured", True,
                   " ".join("%s recall=%.3f meanServerMs=%.1f" % (e, p["recall"], p["latencyServerMsMean"])
                            for e, p in plans.items()))
    else:
        section["reason"] = "eval ran but no timing rows parsed: %s" % \
            dump.stderr.decode("utf-8", "replace").strip()[:400]
        checks.add("C06-pg-candidates-unavailable-named", True, section["reason"])
    # 评测残留在专用 schema，用毕即清（合成容器，不留施工残渣）
    docker_psql("DROP SCHEMA IF EXISTS %s CASCADE;" % PG_EVAL_SCHEMA, psql_env, user, dbname)
    return section


# ---------- C07-C11：cases 公开面与产品桥 ----------

def make_synthetic_root(base: Path):
    """合成 dataset root（只读 FTS 面；无向量模型 → text-only pin）。

    lcr 经 run_profile.load_lcr 已钉到 cases worktree 的 sys.path[0]。
    """
    from lcr.runtime_v4 import initialize
    from lcr.monthly import import_month
    import gzip
    import csv as _csv
    rows = [
        {"canonical_doc_id": "SYN-001", "source_version": "v1",
         "doc_text": "【合成语料，非真实裁判】被告乙未能证明已经向原告甲还款，借贷事实不清，利息主张不予支持。",
         "cause": "民间借贷", "judge_date": "2026-03-01", "court_id": "C1",
         "court_name_norm": "合成一审法院", "case_no_norm": "(2026)合001", "case_class": "民事",
         "trial_prog": "一审", "court_level": "基层", "region_prov": "测试省",
         "region_city": "测试市", "case_result": "部分支持", "year": "2026"},
        {"canonical_doc_id": "SYN-002", "source_version": "v1",
         "doc_text": "【合成语料，非真实裁判】原告主张的违约金过高，依法予以酌减，其余诉讼请求驳回。",
         "cause": "合同纠纷", "judge_date": "2026-03-02", "court_id": "C2",
         "court_name_norm": "合成二审法院", "case_no_norm": "(2026)合002", "case_class": "民事",
         "trial_prog": "二审", "court_level": "中级", "region_prov": "测试省",
         "region_city": "测试市", "case_result": "驳回", "year": "2026"},
    ]
    src = base / "source"
    src.mkdir(parents=True, exist_ok=True)
    month = src / "2026-03.csv.gz"
    with gzip.open(month, "wt", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    cfg = initialize(str(base / "v4"), str(src), batch_rows=2)
    report = import_month(cfg, str(month))
    assert report["status"] == "PUBLISHED", report
    return cfg


def c07_c10_public_face(checks: Checks, cases_root: Path, public_facade) -> dict:
    base = Path(tempfile.mkdtemp(prefix="f67-root-"))
    cfg = make_synthetic_root(base)
    svc = public_facade.CasePublicService(cfg["root"])
    dataset_version = svc._versions.dataset_version
    plain = svc.search({"query": {"mode": "text", "text": "还款"}, "filters": {}})
    checks.add("C07a-public-face-real-run",
               plain["schema"] == "lcr.search/4" and bool(plain["hits"]),
               "real text search hit synthetic corpus (hits=%d)" % len(plain["hits"]))
    ordered = svc.search({"query": {"mode": "text", "text": "还款"}, "filters": {},
                          "execution": {}})
    receipt = ordered.get("retrievalOrder") or {}
    ids = [s["sourceId"] for s in receipt.get("sources", [])]
    local = receipt["sources"][0] if receipt.get("sources") else {}
    checks.add("C08a-order-receipt-positive",
               receipt.get("schema") == RECEIPT_SCHEMA
               and receipt.get("constitution") == CONSTITUTION and ids == list(LADDER)
               and local.get("status") == "tried" and local.get("reason") is None
               and all(s["status"] == "skipped" and s["reason"] == "not_authorized"
                       for s in receipt["sources"][1:])
               and receipt.get("hitsExhaustive") is False,
               "receipt schema/constitution/ladder ok; local tried, paid skipped not_authorized")
    # C10 公开面负测×5
    try:
        svc.search({"query": {"mode": "text", "text": "还款"}, "filters": {},
                    "execution": {"order": ["cncases_full", "local_corpus"]}})
        ok_reorder = False
    except public_facade.CaseBridgeError as exc:
        ok_reorder = exc.code == "search_order_violation"
    checks.add("C10a-reorder-rejected", ok_reorder,
               "caller reorder -> search_order_violation (ladder is backend-owned)")
    try:
        svc.search({"query": {"mode": "text", "text": "还款"}, "filters": {},
                    "execution": {"requireExhaustive": True}})
        ok_exh = False
    except public_facade.CaseBridgeError as exc:
        ok_exh = (exc.code == "exhaustive_unachievable_source_untried"
                  and all(n in str(exc) for n in ("cncases_full", "paid_legal_api", "court_case_library")))
    checks.add("C10b-exhaustive-named", ok_exh,
               "requireExhaustive with untried fee sources -> named list, must not return")
    zero = svc.search({"query": {"mode": "text", "text": "查无此案的词毫无处"}, "filters": {},
                       "execution": {}})
    zr = zero["retrievalOrder"]
    ok_zero = (zero["hits"] == [] and zr["zeroHitAuthoritative"] is False
               and zr["hitsExhaustive"] is False)
    try:
        svc.search({"query": {"mode": "text", "text": "查无此案的词毫无处"}, "filters": {},
                    "execution": {"zeroHitAuthoritative": True}})
        ok_claim = False
    except public_facade.CaseBridgeError as exc:
        ok_claim = exc.code == "zero_hit_not_authoritative_source_untried"
    checks.add("C10c-zero-hit-not-faked", ok_zero and ok_claim,
               "local zero stays qualified; corpus-wide zero claim named-rejected")
    runtime_json = Path(cfg["root"]) / "runtime.json"
    saved = runtime_json.read_text(encoding="utf-8")
    body = json.loads(saved)
    body["paid_sources_authorized"] = ["cncases_full"]
    runtime_json.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    try:
        svc2 = public_facade.CasePublicService(cfg["root"])
        auth = svc2.search({"query": {"mode": "text", "text": "还款"}, "filters": {},
                            "execution": {}})
        by_id = {s["sourceId"]: s for s in auth["retrievalOrder"]["sources"]}
        ok_auth = (by_id["cncases_full"]["status"] == "failed"
                   and by_id["cncases_full"]["reason"] == "adapter_not_implemented")
        checks.add("C10d-authorized-no-adapter-named", ok_auth,
                   "authorized but adapter-less -> failed/adapter_not_implemented (never silent)")
        body["paid_sources_authorized"] = ["not_a_real_source"]
        runtime_json.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        try:
            public_facade.CasePublicService(cfg["root"]).search(
                {"query": {"mode": "text", "text": "还款"}, "filters": {}, "execution": {}})
            ok_unknown = False
        except public_facade.CaseBridgeError as exc:
            ok_unknown = exc.code == "schema_invalid"
        checks.add("C10e-unknown-authorized-source", ok_unknown,
                   "authorized source outside the closed ladder -> schema_invalid")
    finally:
        runtime_json.write_text(saved, encoding="utf-8")
    return {"datasetVersion": dataset_version,
            "plainSearchKeys": sorted(plain), "receipt": receipt}


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
            capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-400:], "_stderr": proc.stderr[-400:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request.name)
        os.unlink(cfg_file.name)


def c09_c11_bridge(checks: Checks, cases_root: Path, pin_facade_path: str) -> dict:
    base = Path(tempfile.mkdtemp(prefix="f67-bridge-"))
    cfg = make_synthetic_root(base)
    db_path = cfg["state_db"]
    import sqlite3
    db = sqlite3.connect(db_path)
    dataset_version = "documents:%d" % db.execute(
        "SELECT version FROM publication WHERE name='documents'").fetchone()[0]
    db.close()
    bridge_config = {"cases_root": cfg["root"],
                     "cases_import_path": str(cases_root),
                     "cases_dataset_version": dataset_version}
    args = {"query": {"mode": "text", "text": "还款"}, "filters": {}}
    first = call_entry_subprocess("case.search", args, bridge_config)
    ok_first = (first["exit"] == 0 and first["payload"].get("status") == "OWNER_RESPONSE"
                and first["payload"].get("result", {}).get("retrievalOrder", {}).get("schema")
                == RECEIPT_SCHEMA)
    checks.add("C09a-bridge-real-run-receipt", ok_first,
               "legal_entry subprocess exit 0 with audited order receipt (profile-embedded "
               "cases engine; desktop/selfhost differ only in PG candidate scope, see C06)")
    if ok_first:
        second = call_entry_subprocess("case.search", args, bridge_config)
        ids1 = [h["locator"]["canonicalDocId"] for h in first["payload"]["result"]["hits"]]
        ids2 = [h["locator"]["canonicalDocId"] for h in second["payload"]["result"]["hits"]]
        checks.add("C09b-bridge-two-runs-same-hits", ids1 == ids2 and bool(ids1),
                   "bridge two runs identical hit sequence (%d hits)" % len(ids1))
    # C11a 预扩展检出（钉定基主检出）→ 桥不静默放行
    frozen_config = dict(bridge_config, cases_import_path=str(Path(pin_facade_path).parents[1]))
    frozen = call_entry_subprocess("case.search", args, frozen_config)
    code = str(frozen["payload"].get("code", ""))
    checks.add("C11a-pre-extension-checkout-not-silent",
               frozen["exit"] == 3 and frozen["payload"].get("status") == "NOT_CONNECTED"
               and code.startswith("cases_public_facade_missing_retrieval_order"),
               "frozen-base provider -> exit 3 named %s…" % code[:60])
    # C11b 审计函数载荷负测×6（真 legal_entry._audit_retrieval_order）
    sys.path.insert(0, str(LEGAL_ENTRY.parent))  # legal_entry 的模块级 opencode_http 依赖
    spec = importlib.util.spec_from_file_location("legal_entry_recon", LEGAL_ENTRY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ladder = [{"sourceId": s} for s in LADDER]
    reasons = {"not_authorized", "adapter_not_implemented", "failed_upstream"}

    def good_receipt(**over):
        paid = [{"sourceId": s, "tier": "paid", "feeRequired": True, "status": "skipped",
                 "reason": "not_authorized", "hits": 0, "elapsedMs": 0.0}
                for s in LADDER[1:]]
        receipt = {"schema": RECEIPT_SCHEMA, "constitution": CONSTITUTION,
                   "sources": [{"sourceId": "local_corpus", "tier": "local_free",
                                "feeRequired": False, "status": "tried", "reason": None,
                                "hits": 2, "elapsedMs": 1.0}] + paid,
                   "hitsExhaustive": False, "zeroHitAuthoritative": False}
        receipt.update(over)
        return receipt

    def audit(result, require_exhaustive=False):
        mod._audit_retrieval_order(result, RECEIPT_SCHEMA, CONSTITUTION, ladder, reasons,
                                   require_exhaustive)

    negatives = []
    try:
        audit({"hits": []}); negatives.append(False)
    except mod.CaseProviderError as exc:
        negatives.append(exc.code == "case_search_order_receipt_missing")
    for tamper, why in (({"schema": "x"}, "schema"), ({"constitution": "x"}, "constitution")):
        try:
            audit({"hits": [], "retrievalOrder": good_receipt(**tamper)}); negatives.append(False)
        except mod.CaseProviderError as exc:
            negatives.append(exc.code == "case_search_order_receipt_invalid")
    bad_order = good_receipt(); bad_order["sources"].reverse()
    try:
        audit({"hits": [], "retrievalOrder": bad_order}); negatives.append(False)
    except mod.CaseProviderError as exc:
        negatives.append(exc.code == "case_search_order_receipt_invalid")
    bad_reason = good_receipt(); bad_reason["sources"][1]["reason"] = "budget_frozen"
    try:
        audit({"hits": [], "retrievalOrder": bad_reason}); negatives.append(False)
    except mod.CaseProviderError as exc:
        negatives.append(exc.code == "case_search_order_receipt_invalid")
    fake_zero = good_receipt(); fake_zero["zeroHitAuthoritative"] = True
    try:
        audit({"hits": [], "retrievalOrder": fake_zero}); negatives.append(False)
    except mod.CaseProviderError as exc:
        negatives.append(exc.code == "case_search_order_receipt_invalid")
    checks.add("C11b-audit-payload-negatives", all(negatives) and len(negatives) == 6,
               "6/6 payload negatives named-rejected (missing/schema/constitution/reorder/"
               "closed-set-reason/fake-zero)")
    # C11c 未配置 NOT_CONNECTED 语义保留
    unbound = call_entry_subprocess("case.search", args, {})
    checks.add("C11c-unbound-still-not-connected",
               unbound["exit"] == 3 and unbound["payload"].get("status") == "NOT_CONNECTED",
               "unbound config -> NOT_CONNECTED exit 3 (existing semantics preserved)")
    return {"bridgeConfigKeys": sorted(bridge_config)}


def run_profile(profile: str, cases_root: Path, evidence_root: Path) -> tuple:
    print("=== profile %s ===" % profile)
    checks = Checks(profile)
    meta = c01_pinned_base(checks, cases_root)
    fts_eval, public_facade = load_lcr(cases_root)
    fts = c02_c05_fts_eval(checks, fts_eval)
    gold = fts_eval.build_gold(fts_eval.build_corpus())
    if profile == "selfhost":
        pg = c06_pg_candidates(checks, gold, fts_eval.build_corpus())
    else:
        pg = {"conclusion": "n/a-desktop-profile",
              "reason": "desktop form is evaluated by the SQLite three plans (C04); "
                        "PG candidates belong to the selfhost form"}
        checks.add("C06-pg-candidates-desktop-na", True, pg["reason"])
    face = c07_c10_public_face(checks, cases_root, public_facade)
    bridge = c09_c11_bridge(checks, cases_root, meta["pinPath"])
    # 证据落盘
    f67_dir = evidence_root / "F67" / profile
    f68_dir = evidence_root / "F68" / profile
    f67_dir.mkdir(parents=True, exist_ok=True)
    f68_dir.mkdir(parents=True, exist_ok=True)
    f67_doc = {"schema": "juscite.f67-retrieval-eval/1", "profile": profile, "runTs": RUN_TS,
               "cases": meta, "sqlite": fts, "pg": pg}
    f68_doc = {"schema": "juscite.f68-order-receipt/1", "profile": profile, "runTs": RUN_TS,
               "constitution": CONSTITUTION, "ladder": list(LADDER),
               "publicFace": face, "bridge": bridge,
               "assertions": [i for i in checks.items if i["id"].startswith(("C08", "C09", "C10", "C11"))]}
    f67_path = f67_dir / ("f67-retrieval-eval-%s.json" % time.strftime("%Y%m%dT%H%M%S+0800"))
    f68_path = f68_dir / ("f68-order-receipt-%s.json" % time.strftime("%Y%m%dT%H%M%S+0800"))
    f67_path.write_text(json.dumps(f67_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    f68_path.write_text(json.dumps(f68_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = checks.all_passed
    print("=== profile %s %s (%d/%d PASS) ===" % (
        profile, "RECON_OK" if ok else "RECON_FAIL", checks.passed_count, len(checks.items)))
    return ok, {"profile": profile, "f67": f67_doc, "f68": f68_doc,
                "f67Path": str(f67_path), "f68Path": str(f68_path),
                "checks": checks.items}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=("desktop", "selfhost", "both"), default="both")
    ap.add_argument("--cases-root", default=None)
    ap.add_argument("--evidence-root", default=str(REPO_ROOT / "docs" / "construction" / "evidence"))
    a = ap.parse_args()
    cases_root = resolve_cases_root(a.cases_root)
    profiles = ("desktop", "selfhost") if a.profile == "both" else (a.profile,)
    evidence_root = Path(a.evidence_root)
    results = []
    all_ok = True
    for profile in profiles:
        ok, doc = run_profile(profile, cases_root, evidence_root)
        results.append(doc)
        all_ok = all_ok and ok
    if len(results) == 2:
        unified = {"schema": "juscite.f67-two-form-unified/1", "runTs": RUN_TS,
                   "forms": {r["profile"]: {"sqlite": r["f67"]["sqlite"], "pg": r["f67"]["pg"]}
                             for r in results},
                   "gold": {"seed": results[0]["f67"]["sqlite"]["report"]["gold"]["seed"],
                            "nQueries": results[0]["f67"]["sqlite"]["report"]["gold"]["nQueries"]},
                   "conclusion": ("SQLite 三方案两形态同 seed 同分实测；PG 候选以 lh-pg-e08 实况"
                                  "具名（measured/unavailable），不凭选核默裁默认预分词 tsvector，"
                                  "不因选核改变已裁范围")}
        (evidence_root / "F67").mkdir(parents=True, exist_ok=True)
        (evidence_root / "F67" / "f67-two-form-unified-report.json").write_text(
            json.dumps(unified, ensure_ascii=False, indent=2), encoding="utf-8")
        print("unified report: %s" % (evidence_root / "F67" / "f67-two-form-unified-report.json"))
    print("RECON_OK" if all_ok else "RECON_FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
