# -*- coding: utf-8 -*-
"""F73 用户自建知识库 RAG 验收对账（W4-U43）。

06:F73（owner=manuals+product，B4，desktop;selfhost 双实例）acceptance
「经验/所内知识按授权/快照/出处检索，向量质量与过期治理真实，不串案」
＋17 卡「Harness manuals/playbook 公开消费＋受控内容包＋原生技能UI；
固定内容 hash/权限→公开读取→实际任务消费→来源回执和验证；不公开私域
蒸馏」＋工作区根 AGENTS.md 真安全边界 3（安装包不带 manuals 与 persona
内容）＋06 prereq 未列 F71（非硬 DAG，向量底座 f71_hybrid/1 接口级复用
不互锁）。

分段（全局一次＋每 profile 两腿）：
  S0 钉定（manuals 仓 master@a93c14e 六文件 sha256＋src 树文件集恰 8
     模块＝零引擎代码铁律漂移即 FATAL；persona 缺席形态；F73 面在盘）
  S1 授权/快照/出处闭环（产品桥 legal_entry CLI 子进程真径：entry_put
     快照 sha256 客端重算相等；修订 supersede 历史可读；public/firm 授权
     矩阵；private 授权尝试具名拒＋读侧具名拒；命中 sourceRefs 回溯源
     文档（盘上文件 sha256 逐字对上）；回执重算＋usage log 落盘；篡改
     具名拒；manuals record 引用不经 kb 面具名拒＝单一权威）
  S2 向量质量真实（4 主题×3 合成条目金标 recall@1/MRR=1.0；向量分量
     金标>噪声；两跑逐字节同；按 effective 降序）
  S3 质量评分真实（同文对偶 quality 0.9/0.3 定序＋qualityFactor 具名）
  S4 过期治理真实（过期 stale 标记+降权 0.5+因子算术可复算；新鲜孪生
     压过过期孪生；未验证=freshness_unknown；回执 staleCount 可验）
  S5 分案隔离（跨案结构性不可见；本案+全局可见；绑案全局不可见）
  S6 私域分发三级红线（implementation/ 实物树 × manuals/persona 仓
     全文件 sha256 零重叠；kb 引擎 import 闭集零 legal_cn_manuals/lcr/
     网络；MANUAL_METHODS 四方法冻结无越界 manual.*；persona/observer
     具名拒不复活）
  S7 F71 接口级复用（未知后端具名拒不静默回落；回执如实自报
     local-deterministic-v1＋f71_hybrid/1，不冒神经向量模型）
  X  双 profile 归一化 digest 相等（治理面与宿主形态无关）

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f73_kb_rag_recon.py \
      --profile desktop --profile selfhost

exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F73/<profile>/ 与
docs/construction/evidence/F73/<profile>/。全合成材料（合成条目标注
工程验证样本，无法条引文）；不发网络；零 %APPDATA% 触碰；manuals 仓
只读消费（钉定 checkout），零字节改动。
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
KB_RAG = REPO_ROOT / "implementation" / "python" / "kb_rag.py"
KB_TEST = REPO_ROOT / "implementation" / "tests" / "test_f73_kb_rag_wiring.py"

MANUALS_SHA256 = {
    "src/legal_cn_manuals/consumer.py":
        "fead81957eacc6a04d23b46c40cb0e890a4b23963b030bb1ed2501aeeb1cec6f",
    "src/legal_cn_manuals/import_service.py":
        "2d4371e9340a2b9aa62427f30cb87fbc9ca3de11ba3863a49eca97d08e292b82",
    "src/legal_cn_manuals/store.py":
        "766a2033ec6c46a090fd7b70da44b9e297d90037d80c77eff5135ecd0c9fa872",
    "src/legal_cn_manuals/trust.py":
        "e33bb1a82b64fd3d14c32d45d0cc69fa55e1027b5bd7e55b52b90ea278ad9952",
    "src/legal_cn_manuals/contracts.py":
        "3b54d258dd7b8710476f070aef70776f777c28b567941ad2e5009dcee0796067",
    "src/legal_cn_manuals/errors.py":
        "2a67f440f3e97f10aa18ac7e54cf38cc604ad3e21e7de8ed62b50c32387f6c62",
}
MANUALS_HEAD_EXPECTED = "a93c14e80146ed08042502d1d418dbc81b51b535"
MANUALS_SRC_EXPECTED = sorted(
    "__init__.py consumer.py contracts.py data_side.py errors.py "
    "import_service.py store.py trust.py".split())

NETWORK_MODULES = {"socket", "ssl", "urllib", "urllib.request", "urllib.parse",
                   "http", "http.client", "requests", "httpx", "ftplib",
                   "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc",
                   "websocket"}
KB_ALLOWED_IMPORTS = {"__future__", "datetime", "hashlib", "json", "math",
                      "os", "re", "typing"}
MANUAL_QUARTET = frozenset({
    "manual.open", "manual.search", "manual.read", "manual.version"})

# ------------------------------------------------------------ 合成材料 --
# 四个互斥合成主题（工程验证样本；全部虚构、无法条引文、无真实案情）。
SYN_TOPICS = {
    "t1": ("押金结算退还", "押金 结算 租赁 物业交割 退还",
           "租赁押金结算应在物业交割后按清单核验扣除项，剩余押金限期退还，"
           "异议须留痕。"),
    "t2": ("仲裁时效管理", "仲裁 时效 劳动关系 申请期限",
           "劳动关系争议申请仲裁的时效台账要点：起算、中止、中断事由逐项"
           "留痕，逾期风险主动提示。"),
    "t3": ("知识产权许可审查", "知识产权 许可 侵权 合同条款",
           "知识产权许可合同条款审查要点：许可范围、分许可限制、侵权责任"
           "分担与终止后义务。"),
    "t4": ("工期签证台账", "工期 签证 施工 监理 计日",
           "建设工程工期签证与监理计日记录管理：事件发生后限期书面签证，"
           "顺延申请附证据链。"),
}
SYN_MARK = ("本条为工程合成验收材料（SYNTHETIC），无任何真实法条引文、"
            "无真实案情。")


def synth_body(tid: str, n: int) -> str:
    name, _q, point = SYN_TOPICS[tid]
    return ("# 合成经验条目·%s·%d（工程验证样本）\n%s\n%s\n"
            % (name, n, point, SYN_MARK))


def synth_query(tid: str) -> str:
    return SYN_TOPICS[tid][1]


def today_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self):
        return all(i["status"] == "PASS" for i in self.items)

    @property
    def passed_count(self):
        return sum(1 for i in self.items if i["status"] == "PASS")


# ------------------------------------------------------------ 检出解析 --

def resolve_workspace_sibling(*parts: str) -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "jusbench工作区":
            guess = parent.parent.joinpath(*parts)
            return guess if guess.is_dir() else None
    return None


def manuals_checkout(override: str | None) -> Path:
    if override:
        return Path(override)
    env = os.environ.get("JUSCITE_MANUALS_CHECKOUT")
    if env:
        return Path(env)
    got = resolve_workspace_sibling("legal-cn-manuals工作区",
                                    "legal-cn-manuals-repo")
    if got is None:
        raise SystemExit("PENDING_ENV manuals checkout not resolved "
                         "(--manuals-checkout / JUSCITE_MANUALS_CHECKOUT)")
    return got


def persona_checkout(override: str | None) -> Path | None:
    if override:
        return Path(override)
    env = os.environ.get("JUSCITE_PERSONA_CHECKOUT")
    if env:
        return Path(env)
    return resolve_workspace_sibling("legal-cn-persona工作区",
                                     "legal-cn-persona-repo")


# ------------------------------------------------------------ S0 钉定 --

def s0_pins(checks: Checks, manuals_root: Path, persona_root: Path | None):
    for rel, want in sorted(MANUALS_SHA256.items()):
        got = sha256_file(manuals_root / rel)
        checks.add("c01_manuals_pin[%s]" % Path(rel).stem, got == want,
                   "sha256 %s… %s" % (got[:12], "MATCH" if got == want
                                      else "DRIFT(want %s…)" % want[:12]))
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(manuals_root),
                          capture_output=True, text=True).stdout.strip()
    checks.add("c07_manuals_head_pin", head == MANUALS_HEAD_EXPECTED,
               "HEAD %s（漂移即 FATAL＝钉定只读消费）" % head[:12])
    src_files = sorted(p.name for p in
                       (manuals_root / "src" / "legal_cn_manuals").glob("*.py"))
    checks.add("c08_manuals_src_fileset_zero_engine_drift",
               src_files == MANUALS_SRC_EXPECTED,
               "src 树恰 %d 模块＝零引擎代码铁律（无新增引擎文件）" % len(src_files))
    if persona_root is None:
        ok, detail = True, "persona 仓缺失（可选件缺席形态）"
    else:
        names = sorted(str(p.relative_to(persona_root)) for p in
                       persona_root.rglob("*")
                       if p.is_file() and ".git" not in p.parts)
        ok = set(names) <= {".gitignore", "README.md"}
        detail = ("persona 仓 README-only（缺席形态）" if ok
                  else "persona 仓形态漂移：%s" % names[:5])
    checks.add("c09_persona_absence_form", ok, detail)
    present = all(p.is_file() for p in (LEGAL_ENTRY, KB_RAG, KB_TEST))
    checks.add("c10_f73_surfaces_present", present,
               "kb_rag.py＋legal_entry.py＋wiring 测试在本 worktree 在盘")


# ------------------------------------------------------------ 产品桥 CLI --

def call_cli(method: str, args: dict, config: dict, tmp: Path):
    """真产品入口子进程径（legal_entry CLI，同 E23/F64 纪律）。"""
    req = tmp / ("request-%s.json" % method.replace(".", "-"))
    cfg = tmp / "config.json"
    req.write_text(json.dumps({"method": method, "args": args},
                              ensure_ascii=False), encoding="utf-8")
    cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
         "--request-json", str(req), "--config", str(cfg)],
        capture_output=True, text=True, timeout=180)
    payload = None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            payload = json.loads(line)
    return proc.returncode, payload


def refuse_code(payload) -> str:
    """NOT_CONNECTED 载荷里的 typed 码（kb 组前缀 kb_failed: 后段）。"""
    code = (payload or {}).get("code") or ""
    return code.split("kb_failed:", 1)[1] if code.startswith("kb_failed:") \
        else code


# ------------------------------------------------------------ 合成语料 --

def synth_entry(kb_id: str, *, body: str, title: str, scope="public",
                quality=0.9, last_verified=None, window=None, matter=None,
                source_refs=None, topics=None) -> dict:
    return {"kbId": kb_id, "title": title, "body": body, "readScope": scope,
            "qualityScore": quality, "lastVerified": last_verified,
            "freshnessWindowDays": window, "matterId": matter,
            "sourceRefs": source_refs or [
                {"owner": "kb", "kind": "kb-source", "id": "syn-origin-"
                 + kb_id.replace(".", "-")}],
            "topics": topics or []}


def build_corpus(tmp: Path) -> tuple[list[dict], dict[str, str]]:
    """合成语料：4 主题×3 条＋1 噪声，全部 public；每条 sourceRef 指向
    盘上合成源文档（digest 绑定＝检索命中可回溯源文档）。"""
    sources: dict[str, str] = {}
    src_dir = tmp / "sources"
    src_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    seq = 0
    for tid in SYN_TOPICS:
        for n in (1, 2, 3):
            seq += 1
            doc_id = "syn-doc-%02d" % seq
            doc_path = src_dir / (doc_id + ".md")
            doc_path.write_text(
                "合成源文档 %s（工程验证样本，无法条引文）\n%s\n"
                % (doc_id, synth_body(tid, n)), encoding="utf-8")
            digest = sha256_file(doc_path)
            sources[doc_id] = digest
            entries.append(synth_entry(
                "kb-%s-%d" % (tid, n),
                title="合成经验条目·%s·%d（工程验证样本）" % (SYN_TOPICS[tid][0], n),
                body=synth_body(tid, n), quality=0.9,
                last_verified=today_iso(), window=365,
                source_refs=[{"owner": "kb", "kind": "kb-source-document",
                              "id": doc_id, "version": "1", "matterId": None,
                              "digest": digest}],
                topics=[SYN_TOPICS[tid][0]]))
    entries.append(synth_entry(
        "kb-noise-1", title="合成噪声条目（工程验证样本）",
        body="天气记录、食谱草稿与旅行笔记的混合合成文本，与各主题无词面"
             "重叠。%s" % SYN_MARK,
        quality=0.9, last_verified=today_iso(), window=365))
    return entries, sources


def client_digest(entry: dict) -> str:
    view = {k: entry[k] for k in ("title", "body", "readScope",
                                  "qualityScore", "lastVerified",
                                  "freshnessWindowDays", "matterId",
                                  "sourceRefs", "topics")}
    return hashlib.sha256(canonical_json(view)).hexdigest()


# ------------------------------------------------------------ per profile --

def run_profile(profile: str, checks: Checks, manuals_root: Path,
                persona_root: Path | None, tmp: Path) -> dict:
    """单 profile 全段；返回归一化观测面（跨 profile digest 用）。"""
    tag = "[%s]" % profile
    state_root = tmp / "kb-state"
    config = {"kb_state_root": str(state_root)}
    obs: dict = {}

    def put(entry, cfg=None):
        rc, payload = call_cli("kb.entry_put", entry, cfg or config, tmp)
        assert rc == 0 and payload["status"] == "OWNER_RESPONSE", (rc, payload)
        return payload["result"]

    def search(args):
        rc, payload = call_cli("kb.search", args, config, tmp)
        assert rc == 0 and payload["status"] == "OWNER_RESPONSE", (rc, payload)
        return payload["result"]

    def refuse(method, args, cfg=None):
        rc, payload = call_cli(method, args, cfg or config, tmp)
        return rc, refuse_code(payload), payload

    corpus, sources = build_corpus(tmp)
    for entry in corpus:
        put(entry)

    # ---- S1 授权/快照/出处闭环 ----
    replay = put(corpus[0])
    checks.add("p01_entry_put_digest%s" % tag,
               replay["revised"] is False
               and replay["entryDigest"] == client_digest(corpus[0]),
               "entry_put 幂等重放（同内容不追加修订）；快照 sha256 客端 "
               "canonical 全字段重算逐字相等")

    v1 = put(synth_entry("kb-sup-1", title="合成修订链条目（v1）",
                         body="合成修订链第一版正文（SYNTHETIC）。",
                         quality=0.8))
    v2 = put(synth_entry("kb-sup-1", title="合成修订链条目（v2）",
                         body="合成修订链第二版正文（SYNTHETIC）。",
                         quality=0.8))
    rc, payload = call_cli("kb.read", {"kbId": "kb-sup-1", "version": 1},
                           config, tmp)
    old = payload["result"]
    checks.add("p02_supersede_chain_history%s" % tag,
               rc == 0 and v2["revision"] == 2
               and v2["superseded"]["revision"] == 1
               and old["entryRef"]["digest"] == v1["entryDigest"]
               and "第一版" in old["body"],
               "同 kbId 修订推进 rev1→rev2；旧版按 version 钉 digest 回读"
               "（快照推进只增不改）")
    obs["supersede"] = {"v2Revision": v2["revision"],
                        "oldDigestHead": old["entryRef"]["digest"][:8]}

    put(synth_entry("kb-firm-1", scope="firm",
                    title="合成所内条目·内部结算复核清单（工程样本）",
                    body="所内受控合成条目：内部结算复核清单五步核验（工程"
                         "样本，无真实案情）。",
                    quality=0.8, last_verified=today_iso(), window=365))
    q_firm = {"query": "内部结算复核清单 五步核验"}
    pub = search(dict(q_firm))
    firm = search(dict(q_firm, authorizedReadScopes=["firm"]))
    pub_ids = [h["entryRef"]["id"] for h in pub["hits"]]
    firm_ids = [h["entryRef"]["id"] for h in firm["hits"]]
    checks.add("p03_public_default_auth%s" % tag,
               pub["authorizedReadScopes"] == ["public"],
               "缺省授权面=public（fail-closed），回显 authorizedReadScopes")
    checks.add("p04_firm_hidden_then_visible%s" % tag,
               "kb-firm-1" not in pub_ids and "kb-firm-1" in firm_ids,
               "firm 条目未授权不命中；显式授权后命中")
    obs["auth"] = {"public": sorted(pub_ids), "firm": sorted(firm_ids)}

    rc_p, code_p, _ = refuse("kb.search", {"query": "内部结算复核清单",
                                           "authorizedReadScopes": ["private"]})
    checks.add("p05_private_authorization_named_refusal%s" % tag,
               rc_p == 3
               and code_p == "kb_scope_mismatch:private_never_authorizable",
               "private 授权尝试 exit 3 具名拒（不公开私域蒸馏·授权面）")
    put(synth_entry("kb-priv-1", scope="private",
                    title="合成私域条目（工程样本）",
                    body="个人私域合成蒸馏条目：任何形式的检索都不应命中，"
                         "读取必须具名拒。", quality=0.8))
    wide = search({"query": "私域蒸馏 合成条目", "topK": 20})
    rc_r, code_r, _ = refuse("kb.read", {"kbId": "kb-priv-1"})
    checks.add("p06_private_never_hits_never_reads%s" % tag,
               "kb-priv-1" not in [h["entryRef"]["id"] for h in wide["hits"]]
               and rc_r == 3 and code_r ==
               "kb_scope_mismatch:private_never_leaves_read_whitelist",
               "private 检索零命中＋读侧具名拒（manuals「private 不出读侧"
               "白名单」同纪律）")

    trace_ok, traced = True, 0
    for tid in SYN_TOPICS:
        out = search({"query": synth_query(tid), "topK": 4})
        for hit in out["hits"]:
            for ref in hit["sourceRefs"]:
                if ref.get("kind") == "kb-source-document":
                    traced += 1
                    if sources.get(ref["id"]) != ref["digest"]:
                        trace_ok = False
    checks.add("p07_provenance_traceable%s" % tag, trace_ok and traced >= 12,
               "检索命中 sourceRefs 逐条回溯源文档：%d 条 digest 与盘上源"
               "文件逐字对上" % traced)

    usage_path = state_root / "usage-log.jsonl"
    receipts = [json.loads(l) for l in
                usage_path.read_text(encoding="utf-8").splitlines() if l]
    search_receipts = [r for r in receipts if r["kind"] == "kb-search-receipt"]
    last = search_receipts[-1]
    recompute = hashlib.sha256(canonical_json(
        {k: v for k, v in last.items() if k != "receiptId"})).hexdigest()[:16]
    checks.add("p08_receipt_verify_and_log%s" % tag,
               recompute == last["receiptId"] and len(search_receipts) >= 6,
               "usage log %d 条检索回执落盘；receiptId=sha256(canonical)"
               "[:16] 客端重算逐字相等（来源回执可验证）"
               % len(search_receipts))

    tam_root = tmp / "kb-state-tamper"
    tam_cfg = {"kb_state_root": str(tam_root)}
    rc, payload = call_cli("kb.entry_put", synth_entry(
        "kb-tam-1", title="合成篡改探针（工程样本）",
        body="合成正文用于篡改检测（SYNTHETIC）。", quality=0.5),
        tam_cfg, tmp)
    assert rc == 0
    entries_path = tam_root / "entries.jsonl"
    rows = [json.loads(l) for l in
            entries_path.read_text(encoding="utf-8").splitlines() if l]
    rows[0]["content"]["body"] = "被篡改的正文（SYNTHETIC tamper probe）"
    entries_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                  for r in rows) + "\n", encoding="utf-8")
    rc_t, code_t, _ = refuse("kb.read", {"kbId": "kb-tam-1"}, tam_cfg)
    checks.add("p09_tamper_named_refusal%s" % tag,
               rc_t == 3 and code_t == "kb_digest_mismatch",
               "快照漂移（内容篡改）kb.read 逐次重算具名拒 fail-closed")

    rc_m, code_m, _ = refuse("kb.read", {"kbId": "e73-syn-pack/e73-mtd-001"})
    checks.add("p10_manuals_record_not_served_by_kb%s" % tag,
               rc_m == 3 and code_m == "kb_ref_not_found",
               "manuals record 引用不经 kb 面取正文（单一权威；受控消费仍"
               "归 manual.* 四方法＝既有受控通道）")

    # ---- S2 向量质量真实 ----
    rankings = {}
    recall_ok, mrr_ok = True, True
    for tid in SYN_TOPICS:
        out = search({"query": synth_query(tid), "topK": 4})
        golden = {"kb-%s-1" % tid, "kb-%s-2" % tid, "kb-%s-3" % tid}
        ids = [h["entryRef"]["id"] for h in out["hits"]]
        if not ids or ids[0] not in golden:
            recall_ok = False
        rank = next((i for i, h in enumerate(out["hits"], 1)
                     if h["entryRef"]["id"] in golden), 99)
        if rank != 1:
            mrr_ok = False
        rankings[tid] = ids
    checks.add("p11_golden_recall_at_1%s" % tag, recall_ok,
               "4 主题金标 recall@1=1.0（top1 恒为主题条目）")
    checks.add("p12_golden_mrr%s" % tag, mrr_ok, "4 主题金标 MRR=1.0")
    obs["rankings"] = rankings

    wide = search({"query": synth_query("t1"), "topK": 20})
    by_id = {h["entryRef"]["id"]: h for h in wide["hits"]}
    golden_vec = by_id["kb-t1-1"]["score"]["vector"]
    noise_vec = by_id.get("kb-noise-1", {}).get("score", {}).get("vector", 0.0)
    checks.add("p13_vector_discriminates%s" % tag,
               golden_vec > noise_vec and golden_vec > 0.0,
               "t1 金标向量分量 %.4f > 噪声 %.4f（零相关噪声不入命中按 0 计）"
               % (golden_vec, noise_vec))

    run1 = search({"query": synth_query("t1"), "topK": 4})
    run2 = search({"query": synth_query("t1"), "topK": 4})
    strip_hits = lambda r: json.dumps(r["hits"], ensure_ascii=False,
                                      sort_keys=True)
    checks.add("p14_two_runs_byte_identical%s" % tag,
               strip_hits(run1) == strip_hits(run2),
               "同查询两跑命中（id/分/标记）逐字节相同＝确定性")
    effs = [h["score"]["effective"] for h in run1["hits"]]
    checks.add("p15_sorted_by_effective%s" % tag,
               all(a >= b for a, b in zip(effs, effs[1:])),
               "命中按 effective 降序")

    # ---- S3 质量评分真实 ----
    pair_common = dict(
        body="同文对偶合成条目：质量评分因子隔离样本（SYNTHETIC）。",
        title="合成质量对偶条目（工程样本）", scope="public",
        last_verified=today_iso(), window=365)
    put(synth_entry("kb-qual-low", quality=0.3, **pair_common))
    put(synth_entry("kb-qual-high", quality=0.9, **pair_common))
    out = search({"query": "质量评分因子隔离样本 同文对偶合成条目"})
    ids_q = [h["entryRef"]["id"] for h in out["hits"]]
    scores = {h["entryRef"]["id"]: h["score"] for h in out["hits"]}
    checks.add("p16_quality_breaks_tie%s" % tag,
               ids_q[:2] == ["kb-qual-high", "kb-qual-low"]
               and scores["kb-qual-high"]["qualityFactor"] == 0.95
               and scores["kb-qual-low"]["qualityFactor"] == 0.65,
               "同文对偶仅质量不同→0.9 压 0.3；qualityFactor=0.5+0.5×q "
               "具名回显")
    obs["quality_order"] = ids_q[:2]

    # ---- S4 过期治理真实 ----
    twin_common = dict(
        body="过期治理孪生合成条目：同文隔离新鲜度因子（SYNTHETIC）。",
        title="合成过期孪生条目（工程样本）", scope="public", quality=0.8)
    put(synth_entry("kb-stale-old", last_verified="2020-01-01", window=30,
                    **twin_common))
    put(synth_entry("kb-stale-new", last_verified=today_iso(), window=365,
                    **twin_common))
    out = search({"query": "过期治理孪生合成条目 同文隔离新鲜度因子"})
    hits = {h["entryRef"]["id"]: h for h in out["hits"]}
    old, new = hits["kb-stale-old"], hits["kb-stale-new"]
    math_ok = old["score"]["effective"] == round(
        old["score"]["relevance"] * old["score"]["qualityFactor"]
        * old["score"]["stalenessFactor"], 6)
    checks.add("p17_expired_marked%s" % tag,
               old["stale"] and old["staleReason"] == "freshness_expired"
               and old["score"]["stalenessFactor"] == 0.5,
               "过期条目 stale 标记＋staleReason=freshness_expired＋降权 "
               "0.5 具名（绝不静默混入）")
    checks.add("p18_staleness_math%s" % tag, math_ok,
               "effective=relevance×qualityFactor×stalenessFactor 客端复算"
               "相等")
    ids_s = [h["entryRef"]["id"] for h in out["hits"]]
    checks.add("p19_fresh_outranks_expired%s" % tag,
               ids_s.index("kb-stale-new") < ids_s.index("kb-stale-old"),
               "同文孪生：新鲜条目排名恒压过过期条目")
    unv_hits = search({"query": "修订链条目 合成"})["hits"]
    unv_hit = next((h for h in unv_hits
                    if h["entryRef"]["id"] == "kb-sup-1"), None)
    checks.add("p20_unverified_marked%s" % tag,
               unv_hit is not None and unv_hit["stale"]
               and unv_hit["staleReason"] == "freshness_unknown",
               "未验证（lastVerified 缺失）条目标记 freshness_unknown 同降权")
    resp_stale = sum(1 for h in out["hits"] if h["stale"])
    checks.add("p21_receipt_stale_count%s" % tag,
               out["staleCount"] == resp_stale,
               "回执 staleCount=%d 与响应命中逐条复核一致（可验口径）"
               % out["staleCount"])
    obs["stale"] = {"respStale": out["staleCount"]}

    # ---- S5 分案隔离 ----
    put(synth_entry("kb-ma-1", title="合成绑案条目 A（工程样本）",
                    body="仅属案件 m-atok-a 的合成条目（SYNTHETIC）。",
                    quality=0.8, last_verified=today_iso(), window=365,
                    matter="m-atok-a"))
    q_iso = {"query": "合成绑案条目 仅属案件"}
    in_a = [h["entryRef"]["id"] for h in
            search(dict(q_iso, matterId="m-atok-a"))["hits"]]
    in_b = [h["entryRef"]["id"] for h in
            search(dict(q_iso, matterId="m-atok-b"))["hits"]]
    in_g = [h["entryRef"]["id"] for h in search(dict(q_iso))["hits"]]
    checks.add("p22_cross_case_invisible%s" % tag, "kb-ma-1" not in in_b,
               "A 案绑案条目在 B 案检索结构性不可见（跨案检索隔离断言）")
    checks.add("p23_own_case_and_global_visible%s" % tag,
               "kb-ma-1" in in_a and "kb-noise-1" in in_b,
               "本案检索=本案∪全局（全局合成条目在 B 案仍可见）")
    checks.add("p24_case_bound_invisible_globally%s" % tag,
               "kb-ma-1" not in in_g, "绑案条目在全局（无 matterId）检索"
               "同样不可见")
    obs["case"] = {"a": len(in_a), "b": len(in_b), "global": len(in_g)}

    # ---- S6 私域分发三级红线 ----
    impl_hashes = {}
    for path in sorted((REPO_ROOT / "implementation").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            impl_hashes.setdefault(sha256_file(path),
                                   str(path.relative_to(REPO_ROOT)))
    manuals_hashes = {}
    for path in sorted(manuals_root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            manuals_hashes.setdefault(sha256_file(path),
                                      str(path.relative_to(manuals_root)))
    overlap_m = sorted(set(impl_hashes) & set(manuals_hashes))
    checks.add("p25_install_surface_zero_manuals_overlap%s" % tag,
               not overlap_m,
               "implementation/ 实物树 %d 文件 × manuals 仓 %d 文件 sha256 "
               "零重叠（安装包不带 manuals 内容）"
               % (len(impl_hashes), len(manuals_hashes)))
    if persona_root is not None:
        persona_hashes = {sha256_file(p) for p in persona_root.rglob("*")
                          if p.is_file() and ".git" not in p.parts}
        overlap_p = sorted(set(impl_hashes) & persona_hashes)
        persona_note = "README-only"
    else:
        overlap_p = []
        persona_note = "缺席"
    checks.add("p26_install_surface_zero_persona_overlap%s" % tag,
               not overlap_p,
               "implementation/ 实物树 × persona 仓（%s）sha256 零重叠"
               % persona_note)
    imports = set()
    for node in ast.walk(ast.parse(KB_RAG.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imports.add((node.module or "").split(".")[0])
    bad_imports = sorted((imports - KB_ALLOWED_IMPORTS)
                         | (imports & NETWORK_MODULES))
    checks.add("p27_engine_import_closure%s" % tag, not bad_imports,
               "kb_rag import 闭集=%s（零 legal_cn_manuals＝manuals 零引擎"
               "代码铁律侧·零 lcr＝F71 非互锁·零网络）" % sorted(imports))
    le_source = LEGAL_ENTRY.read_text(encoding="utf-8")
    tree = ast.parse(le_source)
    groups = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id.endswith("_METHODS"):
            names = []
            if isinstance(node.value, ast.Call):
                for elt in node.value.args:
                    if isinstance(elt, (ast.Set, ast.List, ast.Tuple)):
                        names = [e.value for e in elt.elts
                                 if isinstance(e, ast.Constant)]
            groups[node.targets[0].id] = names
    manual_tokens = sorted(m for names in groups.values() for m in names
                           if m.startswith("manual."))
    kb_group = set(groups.get("KB_METHODS") or ())
    checks.add("p28_manual_methods_frozen%s" % tag,
               frozenset(manual_tokens) == MANUAL_QUARTET
               and kb_group == {"kb.entry_put", "kb.search", "kb.read",
                                "kb.stats"},
               "MANUAL_METHODS 恰读侧四方法（受控通道面冻结）＋KB_METHODS "
               "恰四方法，无越界 manual.*/写面方法")
    rc_pp, code_pp, _ = refuse("persona.test", {})
    rc_ob, code_ob, _ = refuse("observer.test", {})
    checks.add("p29_persona_observer_named_refusals%s" % tag,
               rc_pp == 3 and code_pp == "persona_optional_component_not_wired"
               and rc_ob == 3
               and code_ob == "observer_not_enabled_pending_user_decision",
               "persona/observer 具名拒不复活（任何配置不可启用）")
    obs["refusals"] = {"persona": code_pp, "observer": code_ob}

    # ---- S7 F71 接口级复用 ----
    rc_b, code_b, _ = refuse("kb.search",
                             {"query": "x", "backend": "not-a-backend"},
                             {"kb_state_root": str(state_root),
                              "kb_backend": "not-a-backend"})
    checks.add("p30_unknown_backend_named_refusal%s" % tag,
               rc_b == 3 and code_b.startswith("kb_backend_unknown"),
               "未知检索后端具名拒不静默回落（接口级复用：后端可插拔可替换）")
    out = search({"query": synth_query("t3"), "topK": 3})
    checks.add("p31_receipt_honest_backend%s" % tag,
               out["backend"] == "local-deterministic-v1"
               and out["retrievalContract"] == "f71_hybrid/1"
               and out["kbContract"] == "kb-rag/1",
               "回执如实自报 backend=local-deterministic-v1＋f71_hybrid/1"
               "（接口名，不冒神经向量模型）")
    obs["backend"] = {"backend": out["backend"],
                      "contract": out["retrievalContract"]}

    return obs


# ------------------------------------------------------------ main --

def normalized_digest(obs: dict) -> str:
    return sha256_text(json.dumps(obs, ensure_ascii=False, sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append", default=[],
                    choices=["desktop", "selfhost"])
    ap.add_argument("--manuals-checkout", default=None)
    ap.add_argument("--persona-checkout", default=None)
    args = ap.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]

    checks = Checks()
    manuals_root = manuals_checkout(args.manuals_checkout)
    persona_root = persona_checkout(args.persona_checkout)
    s0_pins(checks, manuals_root, persona_root)
    if not checks.all_passed:
        print("RECON_FAILED pin drift — exit 2")
        return 2

    profile_results = {}
    with tempfile.TemporaryDirectory(prefix="f73-kb-recon-") as tmp:
        tmp_root = Path(tmp)
        for profile in profiles:
            profile_results[profile] = run_profile(
                profile, checks, manuals_root, persona_root,
                tmp_root / profile)
    if len(profiles) > 1:
        digests = {p: normalized_digest(obs)
                   for p, obs in profile_results.items()}
        distinct = sorted(set(digests.values()))
        checks.add("x01_cross_profile_normalized_digest_equal",
                   len(distinct) == 1,
                   "双 profile 归一化 digest %s（治理面与宿主形态无关）"
                   % [d[:12] for d in distinct])
    else:
        checks.add("x01_cross_profile_normalized_digest_equal", False,
                   "单 profile 跑（--profile %s）：无跨 profile 断言；"
                   "验收形态=双 profile 全跑" % profiles[0])

    verdict = "RECON_OK" if checks.all_passed else "RECON_FAILED"
    try:
        subject_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
            capture_output=True, text=True).stdout.strip()
    except OSError:
        subject_commit = None
    result = {
        "recon": "f73-kb-rag",
        "obligation": "F73",
        "unit": "W4-U43",
        "verdict": verdict,
        "acceptance": "经验/所内知识按授权/快照/出处检索，向量质量与过期"
                      "治理真实，不串案",
        "vector_base": {"contract": "f71_hybrid/1",
                        "reuse": "interface-level（06 prereq 未列 F71＝非硬"
                                 " DAG，不 import 不互锁）",
                        "default_backend": "local-deterministic-v1"},
        "red_lines": {
            "three_tier_distribution":
                "安装包不带 manuals/persona 内容（p25/p26 实物树 sha256 "
                "零重叠）；private 永不可授权永不出读侧白名单（p05/p06）",
            "controlled_channel":
                "受控内容包只经既有 manual.* 读侧四方法（p10/p28），"
                "kb 引擎零 manuals ingestion（p27）",
            "manuals_zero_engine":
                "manuals 仓 src 树恰 8 模块钉定（c08），六文件 sha256 钉定"
                "（c01-c06）",
        },
        "manuals_pin": {"head": MANUALS_HEAD_EXPECTED, "files": MANUALS_SHA256,
                        "checkout": str(manuals_root)},
        "persona_absence": {"checkout": str(persona_root)
                            if persona_root else None,
                            "form": "README-only（可选件缺省形态）"},
        "subject_commit": subject_commit,
        "profile_digests": {p: normalized_digest(obs)
                            for p, obs in profile_results.items()},
        "checks": checks.items,
        "passed": checks.passed_count, "total": len(checks.items),
    }
    for base in (REPO_ROOT / "evidence" / "F73",
                 REPO_ROOT / "docs" / "construction" / "evidence" / "F73"):
        for profile in profiles:
            out_dir = base / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = dict(result)
            payload["profile"] = profile
            payload["profile_result"] = profile_results[profile]
            (out_dir / "f73-kb-rag-recon.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1,
                           sort_keys=True), encoding="utf-8")
    print("%s %d/%d checks — exit %d" %
          (verdict, checks.passed_count, len(checks.items),
           0 if checks.all_passed else 1))
    return 0 if checks.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
