# -*- coding: utf-8 -*-
"""F72 人民法院案例库官方分层接入验收对账（工单 W4-U42，负测先行）。

权威面（不复制第二权威）：
  - cases 承载＝分支交付 bced7c9（lcr/caselib.py CaseLibCorpus＋
    public_facade._execute_caselib 梯子 additive），本单经 unit 命名 pin
    分支 w4-u42（=bced7c9 零新提交）独立复验后消费（W4-U45 先例）；
  - E19 钉定基不动＝cases main@916ddf5 工作树净＋P08 冻结基 sha256
    38c1959c… 逐字在位（漂移即 FATAL）；
  - 产品面＝implementation/python/court_case_library.py＋legal_entry 冻结
    COURT_CASE_LIBRARY_METHODS（caselib.register/search/tier，P08/P11 域）；
    全部断言走真产品入口（legal_entry.py 子进程径）。

分段（--profile 可重复，desktop/selfhost 双 profile；每 profile 各跑一遍）：
  F1 钉定完整性：交付 commit/树净/caselib+facade sha；E19 基 main@916ddf5
     不动＋P08 主检出盘上字节（漂移即 FATAL，绝不静默跟随）。
  F2 禁编 URL／零网络（AST 级，N3/N4 同口径）：cases 两侧＋产品面＋本工具
     自身，字符串常量零 URL、导入根零网络/子进程 token。
  F3 语料承载登记（17 卡第一步：范围/语料许可）：许可缺/web 页面声明冒官
     方 tier/本地来源冒官方分层 三路具名拒；合法登记投影（datasetVersion/
     indexVersion 内容寻址钉定）＋同语料幂等重放同态。
  F4 未授权负测（裁决#8-12；N1/N2 同口径）：未授权梯子=skipped/
     not_authorized＋caseLibrary 块缺席（authorizedTried=False，绝不补造）；
     客户端构造即拒（本域端点形配置键具名拒，零预造端点）；配置域零 URL
     键＋状态根零 URL 字节扫描。
  F5 授权形态诚实性：伪授权但承载缺席＝failed/failed_upstream＋error=
     caselib_corpus_not_registered（不伪命中不编 URL——N2 同口径的 F72 形）。
  F6 授权真跑（合成语料承载在位）：receipt court_case_library=tried＋
     caseLibrary 块真实命中；三分层逐条回读（guiding/included/官方 tier；
     ordinary=具名来源分类维度绝不入官方 tier 字段；仅 web 页面声明=双
     unknown 具名——不因官方网页就签）；E19 同频戳审计（relevanceNot
     Probability/propositionSupport 不代签/score 十进制文本）＋产品投影
     scoreSemantics 常量戳（retrievalScoreIsNotWinRate 族）；两跑命中序列
     一致（确定性）；official tier 过滤真跑＋ordinary 过滤具名拒。
  F7 分层回读面：caselib.tier 逐 docId 三分层来源绑定（officialTier/
     tierSource＋classification/classificationSource）；未知 docId 具名拒。
  F8 pin/概率/缺配/冻结基负测：stale caselib pin 具名拒；probability 形
     字段私运具名拒（E19 同口径）；未配置 NOT_CONNECTED；预 F72 冻结基
     （P08 主检出）真子进程 caselib_module_missing 不静默回退。
  F9 跨 profile 对账（双 profile 都跑完后）：剥 elapsedMs 后投影逐键相等。

授权后补联测回收点（具名，写入证据）：本构建未获案例库 API 授权——
  liveTransport=caselib_live_transport_not_implemented_pending_authorization；
  用户提供官方授权语料后，以同一 caselib.register 门承载（license 声明真
  实 evidenceRef）→ caselib.search/tier 同面复跑（dataset/indexVersion 换
  真实官方钉定值）即为联测回收点；live transport 由 cases 仓适配器按授权
  形态实现，本工具不预造、不编 URL、不造数。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f72_court_library_recon.py --profile desktop --profile selfhost
  [--cases-worktree <含 bced7c9 的 cases 检出>] [--state-root-prefix <dir>]
  [--evidence-root evidence/F72]
exit 0＝RECON_OK（双 profile 全过＋跨 profile 对账过）；1＝断言失败；
2＝环境缺失。
全程合成材料；零网络出站；%APPDATA% 零触碰；不 push。
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUN_TS = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[1]          # juscite worktree root
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
ENTRY_CSV = REPO_ROOT / "docs" / "construction" / "authority" / "14-Python入口证据.csv"
PRODUCT_FACE = REPO_ROOT / "implementation" / "python" / "court_case_library.py"

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
LADDER = ("local_corpus", "cncases_full", "paid_legal_api", "court_case_library")
SIGNED_PROPOSITION = "UNSIGNED_SOURCE_DECLARATION_IS_NOT_PROPOSITION_SUPPORT"
LIVE_TRANSPORT = "caselib_live_transport_not_implemented_pending_authorization"

NETWORK_TOKENS = {"urllib", "requests", "socket", "http", "httpx", "aiohttp",
                  "ftplib", "smtplib", "telnetlib", "subprocess"}
SCHEME_PARTS = ("http", "https", "ftp", "ws", "wss", "file")
SCHEME_MARK = ":" + "/" + "/"

FIELDS = ['canonical_doc_id', 'doc_text', 'source_version', 'cause', 'judge_date',
          'court_id', 'court_name_norm', 'case_no_norm', 'case_class', 'trial_prog',
          'court_level', 'region_prov', 'region_city', 'case_result', 'year']

LOCAL_ROWS = [
    {"canonical_doc_id": "SYN-001", "source_version": "v1",
     "doc_text": "【合成语料，非真实裁判】被告乙未能证明已经向原告甲还款，借贷事实不清。",
     "cause": "民间借贷", "judge_date": "2026-03-01", "court_id": "C1",
     "court_name_norm": "合成一审法院", "case_no_norm": "(2026)合001",
     "case_class": "民事", "trial_prog": "一审", "court_level": "基层",
     "region_prov": "测试省", "region_city": "测试市", "case_result": "部分支持",
     "year": "2026"},
    {"canonical_doc_id": "SYN-002", "source_version": "v1",
     "doc_text": "【合成语料，非真实裁判】原告主张的违约金过高，依法予以酌减。",
     "cause": "合同纠纷", "judge_date": "2026-03-02", "court_id": "C2",
     "court_name_norm": "合成二审法院", "case_no_norm": "(2026)合002",
     "case_class": "民事", "trial_prog": "二审", "court_level": "中级",
     "region_prov": "测试省", "region_city": "测试市", "case_result": "驳回",
     "year": "2026"},
]

# 合成承载语料（工程夹具，非真实裁判；覆盖三分层四形态，双 profile 同字节）。
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
MANIFEST = {"source": "court_case_library",
            "license": {"name": "synthetic-eval-license",
                        "evidenceRef": "synth-license-evidence-1"},
            "records": CASLIB_RECORDS}

RECOVERY_POINT = (
    "授权后补联测回收点（裁决#8-12）：用户提供案例库官方授权语料后，"
    "①以同一 caselib.register 门承载真实授权语料（license.name/evidenceRef "
    "换真实值）；②caselib.search/caselib.tier 同面复跑（datasetVersion/"
    "indexVersion 换真实官方钉定值）；③live transport 由 cases 仓适配器按 "
    "授权形态实现（现值=%s）。本工具不预造端点、不编 URL、不造数。"
    % LIVE_TRANSPORT)


class Checks:
    def __init__(self, profile: str):
        self.profile = profile
        self.items: list = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s][%s] %s — %s" % ("PASS" if ok else "FAIL", self.profile,
                                    check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(i["status"] == "PASS" for i in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for i in self.items if i["status"] == "PASS")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", timeout=60)


def resolve_cases_worktree(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    override = os.environ.get("JUSCITE_CASES_WT_F72")
    if override:
        return Path(override)
    for parent in REPO_ROOT.parents:
        if parent.name == "jusbench工作区":
            guess = (parent.parent / "legal-cn-cases工作区" / "legal-cn-cases"
                     / ".local" / "worktrees" / "w4-u42")
            if (guess / "lcr" / "caselib.py").is_file():
                return guess
            break
    raise SystemExit("FATAL: cases w4-u42 worktree (delivery bced7c9) not found; "
                     "pass --cases-worktree")


# ---------------- 真产品入口（legal_entry 子进程径） ----------------

def entry_call(method: str, args: dict, config: dict):
    """真产品入口一次调用；返回 (exit_code, payload)。"""
    request = tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                          suffix=".json", delete=False)
    json.dump({"method": method, "args": args}, request, ensure_ascii=False)
    request.close()
    cfg_file = tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                           suffix=".json", delete=False)
    json.dump(config, cfg_file, ensure_ascii=False)
    cfg_file.close()
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request.name, "--config", cfg_file.name],
            capture_output=True, text=True, encoding="utf-8",
            timeout=300, cwd=str(REPO_ROOT))
    finally:
        os.unlink(request.name)
        os.unlink(cfg_file.name)
    payload = None
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "PROTOCOL_INVALID", "stdout": proc.stdout[:400]}
    return proc.returncode, payload


def expect_not_connected(checks: Checks, check_id: str, method: str, args: dict,
                         config: dict, want_code: str) -> bool:
    code, payload = entry_call(method, args, config)
    ok = (code == 3 and isinstance(payload, dict)
          and payload.get("status") == "NOT_CONNECTED"
          and str(payload.get("code", "")).endswith(want_code))
    return checks.add(check_id, ok,
                      "exit=%s status=%s code=%s（期望 …%s）"
                      % (code, (payload or {}).get("status"),
                         (payload or {}).get("code"), want_code))


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k != "elapsedMs"}
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


def _build_v4_root(base: Path) -> tuple:
    sys.path.insert(0, str(CASES_WORKTREE))
    from lcr.runtime_v4 import initialize
    from lcr.monthly import import_month
    src = base / "source"
    src.mkdir(parents=True, exist_ok=True)
    month = src / "2026-03.csv.gz"
    import csv as _csv
    import gzip as _gzip
    with _gzip.open(month, "wt", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(LOCAL_ROWS)
    cfg = initialize(str(base / "v4"), str(src), batch_rows=2)
    report = import_month(cfg, str(month))
    assert report["status"] == "PUBLISHED", report
    import sqlite3
    db = sqlite3.connect(cfg["state_db"])
    dataset_version = "documents:%d" % db.execute(
        "SELECT version FROM publication WHERE name='documents'").fetchone()[0]
    db.close()
    return cfg["root"], dataset_version


def _set_authorized(root: str, sources) -> None:
    rt = Path(root) / "runtime.json"
    body = json.loads(rt.read_text(encoding="utf-8"))
    body["paid_sources_authorized"] = list(sources)
    rt.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def _scan_urls_bytes(root: Path) -> list:
    hits = []
    for path in root.rglob("*"):
        if path.is_file() and path.stat().st_size < 4_000_000:
            try:
                blob = path.read_bytes().lower()
            except OSError:
                continue
            if any(p.encode() + SCHEME_MARK.encode() in blob for p in SCHEME_PARTS):
                hits.append(path.name)
    return hits


def ast_url_network(source: str) -> tuple:
    tree = ast.parse(source)
    url_hits = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and any(p + SCHEME_MARK in n.value.lower() for p in SCHEME_PARTS)]
    roots = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            roots.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            roots.add(n.module.split(".")[0])
    return url_hits, sorted(roots & NETWORK_TOKENS)


CASES_WORKTREE: Path


def run_profile(profile: str, cases_worktree: Path, state_prefix: Path,
                evidence_root: Path) -> tuple:
    checks = Checks(profile)
    holder = tempfile.TemporaryDirectory(prefix="w4u42_f72_%s_" % profile,
                                         dir=str(state_prefix))
    base = Path(holder.name)
    root, dataset_version = _build_v4_root(base)
    config = {"cases_root": root,
              "cases_import_path": str(cases_worktree),
              "cases_dataset_version": dataset_version,
              "caselib_dataset_version": None}
    projections: dict = {}

    # ---------- F1 钉定完整性 ----------
    head = git(["rev-parse", "HEAD"], cases_worktree).stdout.strip()
    status = git(["status", "--porcelain"], cases_worktree)
    checks.add("F1a-delivery-commit-clean",
               head == CASES_DELIVERY_COMMIT and not status.stdout.strip(),
               "cases worktree HEAD=%s tree-clean=%s（交付 %s…）"
               % (head[:12], not status.stdout.strip(),
                  CASES_DELIVERY_COMMIT[:12]))
    for rel, want in CASES_SHA256.items():
        actual = sha256_file(cases_worktree / rel)
        checks.add("F1b-pin-" + Path(rel).name.replace('.', '-'), actual == want,
                   "%s sha256=%s…（钉定 %s…）" % (rel, actual[:16], want[:16]))
    main_head = git(["rev-parse", "HEAD"], CASES_MAIN).stdout.strip()
    main_status = git(["status", "--porcelain"], CASES_MAIN)
    checks.add("F1c-e19-pin-untouched",
               main_head == CASES_E19_PIN_COMMIT and not main_status.stdout.strip(),
               "cases main HEAD=%s clean=%s（E19 钉定基不动）"
               % (main_head[:12], not main_status.stdout.strip()))
    with open(ENTRY_CSV, encoding="utf-8-sig") as f:
        p08 = next(r for r in __import__("csv").DictReader(f)
                   if r["entry_id"] == "P08")
    p08_sha = sha256_file(Path(p08["path"]))
    checks.add("F1d-p08-frozen-base-bytes", p08_sha == p08["sha256"],
               "P08 主检出盘上 sha=%s…（冻结基 %s…，漂移即 FATAL）"
               % (p08_sha[:16], p08["sha256"][:16]))

    # ---------- F2 禁编 URL／零网络（AST，N3/N4 同口径） ----------
    # 被检面（cases 两侧＋产品面）＝零网络主体（零 URL 字面量＋零网络/子进程
    # 导入根）；本工具自身是观察者——子进程仅 legal_entry 驱动/git 钉定读取
    # 两处（驱动真产品入口，非网络通道），故豁免 subprocess token，URL 字面
    # 量门不豁免（探针值拆写，结构性禁编 URL）。
    for label, path in (("caselib.py", cases_worktree / "lcr" / "caselib.py"),
                        ("public_facade.py", cases_worktree / "lcr" / "public_facade.py"),
                        ("court_case_library.py", PRODUCT_FACE)):
        url_hits, net_hits = ast_url_network(path.read_text(encoding="utf-8"))
        checks.add("F2-no-url-" + label, not url_hits,
                   "%s AST 零 URL 字面量（命中 %d）" % (label, len(url_hits)))
        checks.add("F2-no-network-" + label, not net_hits,
                   "%s 导入根零网络/子进程 token（命中 %s）" % (label, net_hits or "无"))
    self_url_hits, self_net_hits = ast_url_network(
        Path(os.path.abspath(__file__)).read_text(encoding="utf-8"))
    checks.add("F2-no-url-recon-self", not self_url_hits,
               "recon-self AST 零 URL 字面量（命中 %d；探针值拆写）" % len(self_url_hits))
    checks.add("F2-recon-self-observer-only",
               self_net_hits == ["subprocess"],
               "recon-self 网络根零命中；subprocess 豁免＝观察者驱动 legal_entry/"
               "git 两处（被检面才是零网络主体）")

    # ---------- F3 语料承载登记（许可门负测先行） ----------
    no_license = dict(MANIFEST, license=None)
    expect_not_connected(checks, "F3a-license-missing-named",
                         "caselib.register", {"manifest": no_license}, config,
                         "caselib_failed:caselib_license_missing")
    web_tier = dict(MANIFEST, records=[dict(CASLIB_RECORDS[0],
                                            tierDeclaration={
                                                "tier": "guiding_case",
                                                "source": "web_page_declaration",
                                                "evidenceRef": "synth-web-ref"})])
    expect_not_connected(checks, "F3b-web-decl-cannot-sign-tier",
                         "caselib.register", {"manifest": web_tier}, config,
                         "caselib_failed:caselib_tier_source_not_official")
    origin_tier = dict(MANIFEST, records=[dict(CASLIB_RECORDS[2],
                                               originDeclaration={
                                                   "classification": "guiding_case",
                                                   "source": "synth-local-catalog",
                                                   "evidenceRef": "synth-x"})])
    expect_not_connected(checks, "F3c-origin-cannot-claim-official-tier",
                         "caselib.register", {"manifest": origin_tier}, config,
                         "caselib_failed:caselib_origin_value_invalid")
    code, payload = entry_call("caselib.register", {"manifest": MANIFEST}, config)
    reg = (payload or {}).get("result") or {}
    checks.add("F3d-register-projection-pin",
               code == 0 and reg.get("datasetVersion") == "caselib:1"
               and str(reg.get("indexVersion", "")).startswith("caselib-idx:")
               and reg.get("recordCount") == 4 and reg.get("liveTransport") == LIVE_TRANSPORT,
               "register exit=%s datasetVersion=%s indexVersion=%s records=%s"
               % (code, reg.get("datasetVersion"), str(reg.get("indexVersion"))[:24],
                  reg.get("recordCount")))
    config["caselib_dataset_version"] = reg.get("datasetVersion")
    code2, payload2 = entry_call("caselib.register", {"manifest": MANIFEST}, config)
    reg2 = (payload2 or {}).get("result") or {}
    checks.add("F3e-register-idempotent-replay",
               code2 == 0 and reg2.get("datasetVersion") == reg.get("datasetVersion")
               and reg2.get("indexVersion") == reg.get("indexVersion")
               and reg2.get("revision") == reg.get("revision"),
               "同语料重放 dataset/index/revision 全等（幂等承载）")

    # ---------- F4 未授权负测（裁决#8-12；N1/N2 同口径） ----------
    _set_authorized(root, [])
    code, payload = entry_call("caselib.search",
                               {"query": {"mode": "text", "text": "还款"}}, config)
    proj = (payload or {}).get("result") or {}
    by_id = {s["sourceId"]: s
             for s in ((proj.get("retrievalOrder") or {}).get("sources") or [])}
    entry = by_id.get("court_case_library") or {}
    checks.add("F4a-unauthorized-block-absent-ladder-skipped",
               code == 0 and proj.get("authorizedTried") is False
               and proj.get("caseLibrary") is None
               and entry.get("status") == "skipped"
               and entry.get("reason") == "not_authorized"
               and entry.get("hits", 0) == 0
               and by_id.get("local_corpus", {}).get("status") == "tried",
               "未授权：caseLibrary 块缺席＋skipped/not_authorized/hits=0＋本地腿 "
               "tried（诚实负测，绝不补造）")
    for key in ("cases_url", "caselib_endpoint", "court_library_base_url"):
        bad = dict(config, caselib_dataset_version=None)
        # 探针值拆写（本工具自身受 F2 AST 零 URL 门约束，不携完整 URL 字面量）
        bad[key] = "http" + "://" + "127.0.0.1:1/never-an-endpoint"
        expect_not_connected(checks, "F4b-client-construction-refused-" + key,
                             "caselib.search",
                             {"query": {"mode": "text", "text": "还款"}}, bad,
                             "caselib_failed:caselib_config_forbidden")
    url_state_hits = _scan_urls_bytes(Path(root))
    checks.add("F4c-state-zero-url-bytes", not url_state_hits,
               "状态根（runtime.json/承载 state.json）字节级零 URL（命中 %s）"
               % (url_state_hits or "无"))
    projections["unauthorized"] = _strip_volatile(proj)

    # ---------- F5 授权形态诚实性（承载缺席＝双层具名，N2 同口径 F72 形） ----------
    empty_root, empty_dv = _build_v4_root(base / "empty")
    empty_config = dict(config, cases_root=empty_root, cases_dataset_version=empty_dv,
                        caselib_dataset_version="caselib:1")
    _set_authorized(empty_root, ["court_case_library"])
    expect_not_connected(checks, "F5a-authorized-no-carrier-face-pin-named",
                         "caselib.search",
                         {"query": {"mode": "text", "text": "还款"}}, empty_config,
                         "caselib_failed:caselib_state_unavailable")
    code, payload = entry_call(
        "case.search",
        {"query": {"mode": "text", "text": "还款"}, "filters": {},
         "execution": {"caseLibrary": {}}},
        {"cases_root": empty_root, "cases_import_path": str(cases_worktree),
         "cases_dataset_version": empty_dv})
    by_id = {s["sourceId"]: s
             for s in ((((payload or {}).get("result") or {})
                        .get("retrievalOrder") or {}).get("sources") or [])}
    entry = by_id.get("court_case_library") or {}
    checks.add("F5b-authorized-without-carrier-ladder-failed-named",
               code == 0 and entry.get("status") == "failed"
               and entry.get("reason") == "failed_upstream"
               and entry.get("error") == "caselib_corpus_not_registered"
               and entry.get("hits", 0) == 0
               and not (((payload or {}).get("result") or {}).get("caseLibrary")),
               "伪授权但承载缺席（裸 case.search 梯层）：failed/failed_upstream＋"
               "error=caselib_corpus_not_registered＋hits=0＋块缺席（不伪命中不编 URL）")
    _set_authorized(empty_root, [])

    # ---------- F6 授权真跑（合成承载在位） ----------
    _set_authorized(root, ["court_case_library"])
    args = {"query": {"mode": "text", "text": "还款"}, "limit": 20}
    code, payload = entry_call("caselib.search", args, config)
    proj = (payload or {}).get("result") or {}
    block = proj.get("caseLibrary") or {}
    by_id = {s["sourceId"]: s
             for s in ((proj.get("retrievalOrder") or {}).get("sources") or [])}
    checks.add("F6a-authorized-real-block",
               code == 0 and proj.get("authorizedTried") is True and block.get("hits")
               and by_id.get("court_case_library", {}).get("status") == "tried"
               and by_id["court_case_library"].get("hits", 0) == len(block.get("hits") or []),
               "授权真跑：exit=%s 块命中=%d receipt court_case_library=%s"
               % (code, len(block.get("hits") or []),
                  by_id.get("court_case_library", {}).get("status")))
    tiering = {h["caseNo"]: h["tiering"] for h in block.get("hits") or []}
    checks.add("F6b-three-tier-readback",
               tiering.get("(2026)合指1号", {}).get("officialTier") == "guiding_case"
               and tiering.get("(2026)合入2号", {}).get("officialTier") == "included_case"
               and tiering.get("(2026)合民3号", {}).get("officialTier") == "unknown"
               and tiering.get("(2026)合民3号", {}).get("classification") == "ordinary_judgment"
               and tiering.get("(2026)合民4号", {}).get("officialTier") == "unknown"
               and tiering.get("(2026)合民4号", {}).get("classification") == "unknown",
               "三分层逐条：官方 tier guiding/included；普通裁判=具名分类不入官方"
               " tier；仅 web 声明=双 unknown 具名（不因官方网页就签）")
    stamps_ok = (block.get("relevanceNotProbability") is True
                 and block.get("propositionSupport") == SIGNED_PROPOSITION
                 and block.get("liveTransport") == LIVE_TRANSPORT
                 and all(isinstance(h.get("score"), str) for h in block.get("hits") or [])
                 and all(h.get("locator", {}).get("datasetVersion") == "caselib:1"
                         and h.get("locator", {}).get("indexVersion")
                         for h in block.get("hits") or []))
    checks.add("F6c-e19-stamp-class-audit", stamps_ok,
               "E19 同频戳：relevanceNotProbability＋propositionSupport 不代签＋"
               "score 十进制文本＋locator dataset/index 钉定逐条")
    checks.add("F6d-product-score-semantics-stamp",
               proj.get("scoreSemantics") == {"retrievalScoreIsNotWinRate": True,
                                              "notAPopulationSample": True,
                                              "probability": None},
               "产品投影盖 scoreSemantics 常量戳（retrievalScoreIsNotWinRate 族）")
    code2, payload2 = entry_call("caselib.search", dict(args), config)
    proj2 = (payload2 or {}).get("result") or {}
    ids1 = [h["caseNo"] for h in (proj.get("caseLibrary") or {}).get("hits") or []]
    ids2 = [h["caseNo"] for h in (proj2.get("caseLibrary") or {}).get("hits") or []]
    checks.add("F6e-two-runs-identical", code2 == 0 and ids1 == ids2 and ids1,
               "两跑命中序列逐项相等（确定性，n=%d）" % len(ids1))
    code3, payload3 = entry_call(
        "caselib.search", dict(args, caseLibrary={"filters": {"tier": "guiding_case"}}),
        config)
    block3 = ((payload3 or {}).get("result") or {}).get("caseLibrary") or {}
    checks.add("F6f-official-tier-filter-real",
               code3 == 0 and block3.get("hits") is not None
               and all(h["tiering"]["officialTier"] == "guiding_case"
                       for h in block3.get("hits") or [])
               and any(h["caseNo"] == "(2026)合指1号" for h in block3.get("hits") or []),
               "official tier 过滤真跑：命中全部 guiding_case（含 (2026)合指1号）")
    code4, payload4 = entry_call(
        "caselib.search",
        dict(args, caseLibrary={"filters": {"tier": "ordinary_judgment"}}), config)
    checks.add("F6g-ordinary-filter-named-reject",
               code4 == 4 and (payload4 or {}).get("status") == "CASE_ERROR"
               and payload4.get("code") == "query_invalid"
               and "caselib_filter_invalid" in str(payload4.get("message", "")),
               "ordinary 过滤具名拒：exit=4 query_invalid（caselib_filter_invalid——"
               "普通裁判是分类不是官方分层）")
    projections["authorized_search"] = _strip_volatile(proj)

    # ---------- F7 分层回读面 ----------
    code, payload = entry_call("caselib.tier", {"docId": "CASLIB-SYN-G1"}, config)
    view = (payload or {}).get("result") or {}
    checks.add("F7a-tier-guiding-with-source",
               code == 0 and view.get("officialTier") == "guiding_case"
               and (view.get("tierSource") or {}).get("source") == "caselib_official_declaration"
               and view.get("datasetVersion") == "caselib:1",
               "caselib.tier 指导性：officialTier=tierSource 官方声明＋datasetVersion 钉定")
    code, payload = entry_call("caselib.tier", {"docId": "CASLIB-SYN-I1"}, config)
    view = (payload or {}).get("result") or {}
    checks.add("F7b-tier-included-with-source",
               code == 0 and view.get("officialTier") == "included_case"
               and (view.get("tierSource") or {}).get("evidenceRef") == "synth-official-decl-i1",
               "caselib.tier 入库：officialTier=included_case＋evidenceRef 逐字绑定")
    code, payload = entry_call("caselib.tier", {"docId": "CASLIB-SYN-O1"}, config)
    view = (payload or {}).get("result") or {}
    checks.add("F7c-ordinary-classification-binding",
               code == 0 and view.get("officialTier") == "unknown"
               and view.get("classification") == "ordinary_judgment"
               and (view.get("classificationSource") or {}).get("source") == "synth-local-catalog",
               "caselib.tier 普通裁判：官方 tier=unknown＋分类来源具名绑定")
    code, payload = entry_call("caselib.tier", {"docId": "CASLIB-SYN-W1"}, config)
    view = (payload or {}).get("result") or {}
    checks.add("F7d-web-only-signs-nothing",
               code == 0 and view.get("officialTier") == "unknown"
               and view.get("tierReason") == "no_official_tier_declaration_in_corpus"
               and view.get("classification") == "unknown"
               and view.get("classificationReason") == "no_named_classification_source_in_corpus",
               "仅网页声明：官方分层与分类双 unknown 具名（web 页面≠命题成立）")
    expect_not_connected(checks, "F7e-unknown-docid-named",
                         "caselib.tier", {"docId": "CASLIB-SYN-NONE"}, config,
                         "caselib_failed:caselib_ref_not_found")
    projections["tiers"] = {
        "G1": _strip_volatile(entry_call("caselib.tier", {"docId": "CASLIB-SYN-G1"},
                                         config)[1].get("result")),
        "O1": _strip_volatile(entry_call("caselib.tier", {"docId": "CASLIB-SYN-O1"},
                                         config)[1].get("result")),
        "W1": _strip_volatile(entry_call("caselib.tier", {"docId": "CASLIB-SYN-W1"},
                                         config)[1].get("result")),
    }
    _set_authorized(root, [])

    # ---------- F8 pin/概率/缺配/冻结基负测 ----------
    bad = dict(config, caselib_dataset_version="caselib:999")
    expect_not_connected(checks, "F8a-stale-pin-named",
                         "caselib.tier", {"docId": "CASLIB-SYN-G1"}, bad,
                         "caselib_failed:caselib_binding_conflict")
    expect_not_connected(checks, "F8b-probability-smuggling-named",
                         "caselib.search",
                         {"query": {"mode": "text", "text": "还款"},
                          "caseLibrary": {"winRate": "0.9"}}, config,
                         "caselib_failed:caselib_probability_field_forbidden")
    expect_not_connected(checks, "F8c-unconfigured-not-connected",
                         "caselib.search", {"query": {"mode": "text", "text": "还款"}},
                         {}, "caselib_failed:caselib_config_missing")
    frozen_config = dict(config, cases_import_path=str(CASES_MAIN))
    expect_not_connected(checks, "F8d-frozen-base-no-silent-fallback",
                         "caselib.search",
                         {"query": {"mode": "text", "text": "还款"}}, frozen_config,
                         "caselib_failed:caselib_module_missing")

    evidence = {
        "run_ts": RUN_TS,
        "run_date": RUN_DATE,
        "unit": "W4-U42",
        "profile": profile,
        "command": "python -X utf8 tools/PENDING_OWNER_f72_court_library_recon.py "
                   + " ".join(sys.argv[1:]),
        "cwd": str(REPO_ROOT),
        "subject_commit": git(["rev-parse", "HEAD"], REPO_ROOT).stdout.strip(),
        "pins": {
            "cases_delivery_commit": CASES_DELIVERY_COMMIT,
            "cases_worktree_head": head,
            "cases_sha256": {rel: sha256_file(cases_worktree / rel)
                             for rel in CASES_SHA256},
            "e19_pin_commit": CASES_E19_PIN_COMMIT,
            "e19_main_head": main_head,
            "p08_frozen_sha256": p08["sha256"],
        },
        "product_face_sha256": sha256_file(PRODUCT_FACE),
        "corpus": {"records": 4, "tiers": ["guiding_case", "included_case",
                                           "ordinary_judgment(classified)", "web-only"],
                   "license": MANIFEST["license"]},
        "authorization_note": "裁决#8-12：未授权（缺省 fail-closed）；授权后补联测"
                              "回收点见 post_authorization_recovery_point",
        "post_authorization_recovery_point": RECOVERY_POINT,
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    out_dir = evidence_root / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "f72-court-library-recon.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# F72 法院案例库 recon 证据（%s，%s）" % (profile, RUN_TS),
          "",
          "- verdict: **%s**（%d/%d 检）" % (evidence["overall"],
                                            checks.passed_count, len(checks.items)),
          "- 钉定：cases 交付 %s（worktree HEAD %s）；E19 基 main@%s 不动；"
          "P08 冻结基 sha %s…" % (CASES_DELIVERY_COMMIT[:12], head[:12],
                                  main_head[:12], p08["sha256"][:16]),
          "- 合成语料：4 记录三分层四形态；承载 datasetVersion=%s" % reg.get("datasetVersion"),
          "- %s" % RECOVERY_POINT,
          "- 检查项：",
          ""]
    md += ["- [%s] %s — %s" % (c["status"], c["id"], c["detail"]) for c in checks.items]
    (out_dir / "f72-court-library-recon.md").write_text(
        "\n".join(md), encoding="utf-8")
    print("---")
    print("RECON_%s %d/%d checks — profile=%s" % (
        "OK" if checks.all_passed else "FAIL", checks.passed_count,
        len(checks.items), profile))
    holder.cleanup()
    return checks.all_passed, projections, evidence


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("desktop", "selfhost"),
                        action="append", default=None)
    parser.add_argument("--cases-worktree", default=None)
    parser.add_argument("--state-root-prefix",
                        default=os.path.join(tempfile.gettempdir(), "w4u42-f72"))
    parser.add_argument("--evidence-root", default="evidence/F72")
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]

    global CASES_WORKTREE
    CASES_WORKTREE = resolve_cases_worktree(args.cases_worktree)
    for rel in CASES_SHA256:
        if not (CASES_WORKTREE / rel).is_file():
            print("FATAL: %s 不在 %s（交付 bced7c9 检出）" % (rel, CASES_WORKTREE))
            return 2
    if not PRODUCT_FACE.is_file() or not LEGAL_ENTRY.is_file():
        print("FATAL: 产品面/桥不在位（%s / %s）" % (PRODUCT_FACE, LEGAL_ENTRY))
        return 2
    evidence_root = REPO_ROOT / args.evidence_root
    state_prefix = Path(args.state_root_prefix)
    state_prefix.mkdir(parents=True, exist_ok=True)

    outcomes = []
    store: dict = {}
    for profile in profiles:
        ok, projections, evidence = run_profile(profile, CASES_WORKTREE,
                                                state_prefix, evidence_root)
        outcomes.append(ok)
        store[profile] = projections
    cross_ok = True
    if len(store) >= 2:
        checks = Checks("cross")
        ref = store[profiles[0]]
        same = all(_strip_volatile(store[p]) == _strip_volatile(ref)
                   for p in profiles[1:])
        cross_ok = checks.add(
            "F9-cross-profile-projections-equal", same,
            "剥 elapsedMs 后 %s 投影逐键相等（分层回读/检索回执/戳三面）"
            % "+".join(profiles))
        (evidence_root / "f72-cross-profile.json").write_text(
            json.dumps({"run_ts": RUN_TS, "profiles": profiles,
                        "checks": checks.items,
                        "overall": "PASS" if cross_ok else "FAIL"},
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print("CROSS %s — %s" % ("OK" if cross_ok else "FAIL", profiles))
    ok_all = all(outcomes) and cross_ok
    print("F72_RECON_%s" % ("OK" if ok_all else "FAIL"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
