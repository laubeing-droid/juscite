"""F48 <edits> 流式协议＋卡片状态机＋DB/书签双持久化对账（W2b-U12）
——双 profile（desktop/selfhost）。

对账对象：产品侧 document-adapter 新模块 implementation/python/
edits_protocol.py（legal_entry 冻结方法组 edits.*）＋提案登记走 harness 面
（legal-harness工作区 w2b-u11 分支 public_entry --formalproposal-json 封闭
径——desktop profile 与产品桥（legal_entry → 子进程 public_entry）完全同一
条链（SQLite 状态根）；selfhost profile＝PgMatterStore 直连 lh-pg-e08
（resolve_provider_method 同一封闭注册））。

全部合成材料：合成复杂 DOCX 用 W2a-U01 生成器扩展现场生成
（tools/e12_corpus_gen.py --docx，seed 20261017 钉定全合成——两遍生成逐字
节相同亲验）；临时状态根；合成 matter/提案/宿主动作。harness 检出零字节
改动（只运行其代码，git 只读命令核对分支）。

实跑覆盖（PENDING_OWNER_F48_edits_protocol）：
  语料确定性（同 seed 两跑逐字节＋清单摘要一致）→ 登记纪律（同 id 同字节
  幂等/异字节具名拒）→ 流式协议（7 字符分块喂入＝整块喂入同卡集：分块
  语义不可见；未知标签前向兼容警告；截断 close＝f48_stream_truncated 具名
  拒且未闭合尾卡绝不产出、坏流卡片账零行）→ 唯一 quote 定位（零命中/
  多命中具名拒不碰文档）→ harness 提案登记（正式交付物 register rev1＋
  formal_propose 提案 pending：canonical 一字不动）→ 部分接受 apply（真
  修订 OOXML：replace＝w:del[delText 原文]＋w:ins[新文] 两个独立元素＝
  office-js#5188 规避形；insert 只 ins；delete 只 del；书签包裹；现行文本
  语义＝旧文只在 delText；他部件字节保真；拒绝卡零痕迹）→ 既有修订越位
  （新 id>901、前手 900/901 原样）→ 重读回流 harness 正式采用
  （read_document 实际文件字节＝host_result_bytes → canonical rev2
  source=user_accept）→ 宿主动过后重载对账（接受修订→host_accepted/
  移除→host_removed，以实际文档为准改写 DB＋事件留痕）→ DB 级扫描
  （状态闭集/事件链）→ 桥负向（未配置/未知方法/方法组冻结）。

用法：
  python -X utf8 tools/recon/PENDING_OWNER_f48_edits_protocol_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失。
证据：docs/construction/evidence/F48/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid as _uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
import edits_protocol as ep  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u11")
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"
SEED = 20261017

MATTER = "m-f48-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
MATERIAL = "mat-f48-complex"

F48_METHODS = frozenset({
    "edits.register", "edits.stream_open", "edits.stream_push",
    "edits.stream_close", "edits.locate", "edits.apply",
    "edits.read_document", "edits.reconcile", "edits.cards",
})
HARNESS_METHODS_USED = (
    "harness.register_material", "harness.read_material",
    "harness.formal_propose", "harness.formal_decide",
)

AUTHOR = "lvyin-edits"  # F53 作者声明闭集（W2b-U49；edits 通道绑定）
DATE = "2026-10-17T00:00:00Z"


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def ref(kind: str, ref_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": "1", "matterId": MATTER}


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks: list[dict] = []

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part,
                     error=(NotConnected, ValueError)):
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc))
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def branch_checks(self):
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref", "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w2b-u01")
        master = self.git(self.harness_root, "rev-parse", "master")
        self.step("c01_harness_branch", branch == "w2b-u11", branch=branch)
        self.step("c01_harness_base_on_w2b_u01", base.startswith("0d5c79bc"),
                  base=base)
        self.step("c01_harness_master_untouched", master.startswith("929d0802"),
                  master=master)
        dirty = self.git(self.harness_root, "status", "--porcelain")
        self.step("c01_harness_worktree_clean", dirty == "", dirty=dirty[:200])

    # ------------------------------------------------------------------
    # 共用流水（两 profile 同集断言）：call_edits=产品面（desktop=桥/
    # selfhost=模块面），call_harness+harness_ok=harness 面，query_harness=
    # harness 库直读。
    # ------------------------------------------------------------------
    def common_flow(self, profile: str, call_edits, call_harness,
                    harness_ok, query_harness):
        # ---- C02 合成复杂 DOCX 语料（W2a-U01 生成器扩展，seed 钉定）
        corpus_a = Path(tempfile.mkdtemp(prefix="juscite-f48-corpus-a-"))
        corpus_b = Path(tempfile.mkdtemp(prefix="juscite-f48-corpus-b-"))
        for out in (corpus_a, corpus_b):
            code = subprocess.call(
                [sys.executable, "-X", "utf8", str(REPO_ROOT / "tools"
                                                   / "e12_corpus_gen.py"),
                 "--docx", str(out), "--seed", str(SEED)])
            if code != 0:
                raise AssertionError("generator_failed:" + str(out))
        manifest = json.loads(
            (corpus_a / "docx_manifest.json").read_text(encoding="utf-8"))
        byte_identical = all(
            (corpus_a / item["name"]).read_bytes()
            == (corpus_b / item["name"]).read_bytes()
            for item in manifest["files"])
        sha_match = all(
            hashlib.sha256((corpus_a / item["name"]).read_bytes()).hexdigest()
            == item["sha256"] for item in manifest["files"])
        self.step("c02_corpus_deterministic_seed_pinned",
                  byte_identical and sha_match
                  and manifest["seed"] == SEED
                  and len(manifest["files"]) == 2,
                  seed=manifest["seed"], files=[f["name"]
                                                 for f in manifest["files"]])
        complex_doc = (corpus_a / "f48_doc_complex.docx").read_bytes()
        prior_doc = (corpus_a / "f48_doc_existing_revisions.docx").read_bytes()
        paragraphs = [p for p in manifest["texts"]["paragraphs"]
                      if not p["repeat"]]
        repeat_paragraph = manifest["texts"]["repeat_paragraph"]
        table_amount = "480,000.00"
        prior_paragraphs = [
            p["text"] for p in manifest["texts"]["prior_document"]["paragraphs"]]

        # ---- C03 登记纪律（原件钉定：同 id 同字节幂等/异字节具名拒）
        register = call_edits("edits.register",
                              {"document_id": "d-main",
                               "bytesB64": b64(complex_doc)})
        again = call_edits("edits.register",
                           {"document_id": "d-main",
                            "bytesB64": b64(complex_doc)})
        self.step("c03_registration_discipline",
                  register["registered"] is True
                  and again["registered"] is False
                  and register["original_sha256"]
                  == hashlib.sha256(complex_doc).hexdigest())
        self.expect_error("c03_bytes_mismatch_refused", lambda: call_edits(
            "edits.register", {"document_id": "d-main",
                               "bytesB64": b64(b"not-a-docx")}),
            "f48_document_bytes_mismatch")
        call_edits("edits.register", {"document_id": "d-prior",
                                      "bytesB64": b64(prior_doc)})

        # ---- C04 流式协议：分块不可见＋未知标签＋截断具名拒
        def build_stream(cards: str) -> str:
            return "<edits>" + cards + "</edits>"

        cards_xml = (
            '<edit id="c1" op="replace"><old>' + paragraphs[0]["text"]
            + "</old><new>替换后的全新合成句（含逾期利息主张）。</new>"
            "<reason>金额主张修正</reason></edit>"
            + '<edit id="c2" op="insert"><old>' + paragraphs[1]["text"]
            + "</old><new>（插入的补充说明句）</new>"
            "<reason>补充说明</reason></edit>"
            + '<edit id="c3" op="delete"><old>' + paragraphs[2]["text"]
            + "</old><reason>删除冗余条款</reason></edit>"
            + '<edit id="c4" op="replace"><old>' + repeat_paragraph
            + "</old><new>重复句不应被定位。</new></edit>"
            + '<edit id="c5" op="replace"><old>文档中不存在的句子甲乙丙。'
            "</old><new>无从替换。</new></edit>"
            + '<edit id="c6" op="delete"><old>' + table_amount
            + "</old><reason>表格内删除</reason></edit>"
            + '<edit id="c7" op="replace"><old>' + paragraphs[3]["text"]
            + "</old><new>带未知标签的修订句。</new><occurrence>1"
            "</occurrence></edit>")
        stream = build_stream(cards_xml)
        call_edits("edits.stream_open", {"document_id": "d-main",
                                         "stream_id": "s1"})
        for i in range(0, len(stream), 7):
            call_edits("edits.stream_push",
                       {"document_id": "d-main", "stream_id": "s1",
                        "chunk": stream[i:i + 7]})
        closed = call_edits("edits.stream_close",
                            {"document_id": "d-main", "stream_id": "s1"})
        call_edits("edits.stream_open", {"document_id": "d-main",
                                         "stream_id": "s2"})
        call_edits("edits.stream_push",
                   {"document_id": "d-main", "stream_id": "s2",
                    "chunk": stream})
        oneshot = call_edits("edits.stream_close",
                             {"document_id": "d-main", "stream_id": "s2"})
        chunk_cards = json.dumps(closed["cards"], ensure_ascii=False,
                                 sort_keys=True)
        oneshot_cards = json.dumps(oneshot["cards"], ensure_ascii=False,
                                   sort_keys=True)
        self.step("c04_stream_chunking_invisible",
                  closed["protocol_error"] is None
                  and [c["card_id"] for c in closed["cards"]]
                  == ["c1", "c2", "c3", "c4", "c5", "c6", "c7"]
                  and chunk_cards == oneshot_cards,
                  cards=len(closed["cards"]))
        self.step("c04_unknown_tag_forward_compatible",
                  any("occurrence" in w for w in closed["warnings"])
                  and len(closed["cards"]) == 7,
                  warnings=closed["warnings"])
        # 截断流：掐掉尾卡闭合（c7 未闭合）
        truncated = stream[:stream.rindex("</edit>")]
        call_edits("edits.stream_open", {"document_id": "d-main",
                                         "stream_id": "s3"})
        call_edits("edits.stream_push",
                   {"document_id": "d-main", "stream_id": "s3",
                    "chunk": truncated})
        cut = call_edits("edits.stream_close",
                         {"document_id": "d-main", "stream_id": "s3"})
        cut_cards = call_edits("edits.cards", {"document_id": "d-main"})
        cut_stream_cards = [card for card in cut_cards["cards"]
                            if card["stream_id"] == "s3"]
        self.step("c04_truncation_named_refusal",
                  cut["protocol_error"] is not None
                  and cut["protocol_error"]["code"] == "f48_stream_truncated"
                  and "c7" not in [c["card_id"] for c in cut["cards"]]
                  and cut_stream_cards == [],
                  emitted=[c["card_id"] for c in cut["cards"]])

        # ---- C05 唯一 quote 定位（零/多命中具名拒，不碰文档）
        before = self._working(profile, "d-main").read_bytes()
        locate = call_edits("edits.locate", {"document_id": "d-main",
                                             "stream_id": "s1"})
        by_id = {card["card_id"]: card for card in locate["cards"]}
        self.step("c05_unique_quote_localization",
                  by_id["c1"]["state"] == "located"
                  and by_id["c2"]["state"] == "located"
                  and by_id["c3"]["state"] == "located"
                  and by_id["c6"]["state"] == "located"
                  and by_id["c7"]["state"] == "located"
                  and by_id["c4"]["state"] == "locate_failed"
                  and by_id["c4"]["state_reason"] == "quote_not_unique"
                  and by_id["c4"]["occurrences"] >= 2
                  and by_id["c5"]["state"] == "locate_failed"
                  and by_id["c5"]["state_reason"] == "quote_not_found"
                  and self._working(profile, "d-main").read_bytes() == before,
                  states={k: v["state"] for k, v in by_id.items()})

        # ---- C06 harness 提案登记（canonical 一字不动）
        call_harness("harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("reg-1"),
            "material": {"id": MATERIAL, "kind": "office",
                         "title": "民事起诉状（F48 对账合成）",
                         "bytesB64": b64(complex_doc)}})
        quotes_payload = [
            {"text": paragraphs[0]["text"], "reason": "金额主张修正",
             "sourceRef": ref("material", MATERIAL)},
            {"text": paragraphs[2]["text"], "reason": "删除冗余条款",
             "sourceRef": ref("material", MATERIAL)},
        ]
        proposal = call_harness("harness.formal_propose", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("fp-1"),
            "proposal": {"proposalId": "fp-1", "materialId": MATERIAL,
                         "baseRevision": 1, "bytesB64": b64(stream.encode()),
                         "channel": "machine", "author": AUTHOR,
                         "quotes": quotes_payload, "note": "F48 全合成流"}})
        listing = call_harness("harness.formal_proposal_list",
                               {"scope": SCOPE, "material_id": MATERIAL})
        canonical_before = listing["canonical"]
        revisions_before = query_harness(
            "SELECT COUNT(*) AS n FROM material_candidates"
            " WHERE matter_id=? AND material_id=?",
            (MATTER, MATERIAL))[0]["n"] if harness_ok else 2
        self.step("c06_harness_proposal_pending",
                  harness_ok and canonical_before["revision"] == 1
                  and canonical_before["sha256"]
                  == hashlib.sha256(complex_doc).hexdigest()
                  and listing["proposals"][0]["state"] == "pending"
                  and listing["proposals"][0]["decisionRef"] is None
                  and revisions_before == 1,
                  canonical=canonical_before["revision"])

        # ---- C07 部分接受 apply：真修订 OOXML＋书签＋拒绝零痕迹
        apply_result = call_edits("edits.apply", {
            "document_id": "d-main", "stream_id": "s1",
            "card_ids": ["c1", "c2", "c6", "c7"],
            "reject_card_ids": ["c3"],
            "revision_author": AUTHOR, "revision_date": DATE})
        applied = {card["card_id"]: card for card in apply_result["cards"]}
        working = self._working(profile, "d-main")
        parts = ep.load_docx_parts(working)
        scan = ep.scan_document(parts)
        bookmark_names = set(scan["bookmarks"])
        revisions = scan["revisions"]
        # 现行文本语义
        root, _, _ = ep._parse_document_xml(parts["word/document.xml"])
        current_text, _ = ep.build_text_index(root)
        c1_del = [rev for rev in revisions if rev["kind"] == "del"
                  and rev["text"] == paragraphs[0]["text"]]
        c1_ins = [rev for rev in revisions if rev["kind"] == "ins"
                  and rev["text"] == "替换后的全新合成句（含逾期利息主张）。"]
        self.step("c07_real_revisions_landed",
                  applied["c1"]["applied"] and applied["c2"]["applied"]
                  and applied["c6"]["applied"] and applied["c7"]["applied"]
                  and len(c1_del) == 1 and len(c1_ins) == 1
                  and len(applied["c1"]["revision_ids"]) == 2,
                  dels=sum(1 for r in revisions if r["kind"] == "del"),
                  ins=sum(1 for r in revisions if r["kind"] == "ins"))
        # #5188 规避形：replace=两个独立修订元素（del 与 ins 为**紧邻兄弟**），
        # delText 逐字保留原文（office-js#5188 的丢失面结构性不存在）
        c1_container = None
        for bm in root.iter(ep.W + "bookmarkStart"):
            if bm.get(ep.W + "name") == "JF48_c1":
                for p in root.iter(ep.W + "p"):
                    if any(el is bm for el in p.iter()):
                        c1_container = p
                        break
                break
        children = list(c1_container)

        def text_of(element, tagname):
            return "".join(sub.text or ""
                           for sub in element.iter(ep.W + tagname))

        indexes = {}
        for idx, el in enumerate(children):
            if el.tag == ep.W + "bookmarkStart" \
                    and el.get(ep.W + "name") == "JF48_c1":
                indexes["bm"] = idx
            elif el.tag == ep.W + "del" \
                    and text_of(el, "delText") == paragraphs[0]["text"]:
                indexes["del"] = idx
            elif el.tag == ep.W + "ins" and text_of(el, "t") \
                    == "替换后的全新合成句（含逾期利息主张）。":
                indexes["ins"] = idx
            elif el.tag == ep.W + "bookmarkEnd":
                indexes.setdefault("bmend", idx)
        self.step("c07_5188_avoidance_split_ops",
                  indexes.get("del") is not None
                  and indexes.get("ins") == indexes.get("del", -9) + 1
                  and indexes.get("bm", -9) < indexes.get("del", -9)
                  < indexes.get("bmend", -9)
                  and c1_del[0]["text"] == paragraphs[0]["text"]
                  and "JF48_c1" in bookmark_names
                  and scan["bookmarks"]["JF48_c1"]["text"]
                  == "替换后的全新合成句（含逾期利息主张）。",
                  indexes=indexes,
                  del_id=c1_del[0]["id"], ins_id=c1_ins[0]["id"])
        self.step("c07_current_text_semantics",
                  "替换后的全新合成句" in current_text
                  and paragraphs[0]["text"] not in current_text
                  and "（插入的补充说明句）" in current_text
                  and table_amount not in current_text,
                  note="旧文只在 delText；表内删除生效")
        self.step("c07_bookmarks_and_reject_clean",
                  {"JF48_c1", "JF48_c2", "JF48_c6", "JF48_c7"}
                  <= bookmark_names
                  and "JF48_c3" not in bookmark_names
                  and "JF48_c4" not in bookmark_names
                  and paragraphs[2]["text"] in current_text,
                  bookmarks=sorted(bookmark_names),
                  note="拒绝卡 c3 原文仍在现行文本（人说不=文档不动）")
        # 他部件字节保真（页眉/页脚/脚注/styles/rels/[Content_Types]）
        original_parts = ep.load_docx_parts_from_bytes(complex_doc)
        untouched = all(parts[name] == payload
                        for name, payload in original_parts.items()
                        if name != "word/document.xml")
        self.step("c07_other_parts_byte_identical", untouched)

        # ---- C08 既有修订越位（d-prior 文档）
        prior_stream = build_stream(
            '<edit id="p1" op="replace"><old>' + prior_paragraphs[0]
            + "</old><new>前手在场时的后到修订句。</new></edit>")
        call_edits("edits.stream_open", {"document_id": "d-prior",
                                         "stream_id": "sp"})
        call_edits("edits.stream_push",
                   {"document_id": "d-prior", "stream_id": "sp",
                    "chunk": prior_stream})
        call_edits("edits.stream_close", {"document_id": "d-prior",
                                          "stream_id": "sp"})
        call_edits("edits.locate", {"document_id": "d-prior",
                                    "stream_id": "sp"})
        prior_apply = call_edits("edits.apply", {
            "document_id": "d-prior", "stream_id": "sp",
            "card_ids": ["p1"], "revision_author": AUTHOR,
            "revision_date": DATE})
        prior_ids = prior_apply["cards"][0]["revision_ids"]
        prior_scan = ep.scan_document(
            ep.load_docx_parts(self._working(profile, "d-prior")))
        prior_authors = [rev for rev in prior_scan["revisions"]
                         if rev["author"] == "prior-author"]
        self.step("c08_existing_revisions_beyond_allocation",
                  all(int(value) > 901 for value in prior_ids)
                  and {rev["id"] for rev in prior_authors} == {"900", "901"},
                  new_ids=prior_ids)

        # ---- C09 重读实际文件回流 harness 正式采用（部分接受 bake）
        reread = call_edits("edits.read_document", {"document_id": "d-main"})
        reread_bytes = base64.b64decode(reread["bytesB64"])
        decided = call_harness("harness.formal_decide", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dec-1"),
            "decision": {"proposalId": "fp-1", "action": "accept",
                         "reasonRef": ref("reason", "r-f48"),
                         "receiptRef": ref("receipt", "rc-f48"),
                         "resultBytesB64": reread["bytesB64"]}})
        baked = call_harness("harness.read_material", {
            "scope": SCOPE, "material_id": MATERIAL, "revision": 2})
        self.step("c09_host_result_bytes_baked",
                  harness_ok
                  and decided["canonical"]["revision"] == 2
                  and base64.b64decode(baked["bytesB64"]) == reread_bytes
                  and baked["source"] == "user_accept"
                  and baked["resultSource"] == "host_result_bytes"
                  and baked["sha256"]
                  == hashlib.sha256(reread_bytes).hexdigest(),
                  canonical=decided["canonical"]["revision"])

        # ---- C10 重载对账（宿主动过实际文档→以实际文档为准）
        # 宿主模拟①：接受 c1 修订（去 del、解 ins 留文本、书签保留）
        # 宿主模拟②：整体移除 c6（书签＋修订全删）
        tampered = dict(parts)
        troot, tdecls, tdns = ep._parse_document_xml(parts["word/document.xml"])

        def region_container(name):
            for bm in troot.iter(ep.W + "bookmarkStart"):
                if bm.get(ep.W + "name") == name:
                    for p in troot.iter(ep.W + "p"):
                        if any(el is bm for el in p.iter()):
                            return p

        container = region_container("JF48_c1")
        seen = False
        for el in list(container):
            if el.tag == ep.W + "bookmarkStart" \
                    and el.get(ep.W + "name") == "JF48_c1":
                seen = True
                continue
            if el.tag == ep.W + "bookmarkEnd":
                break
            if not seen:
                continue
            if el.tag == ep.W + "ins":
                index = list(container).index(el)
                for run in list(el):
                    container.insert(index, run)
                    index += 1
                container.remove(el)
            elif el.tag == ep.W + "del":
                container.remove(el)
        container = region_container("JF48_c6")
        seen = False
        for el in list(container):
            if el.tag == ep.W + "bookmarkStart" \
                    and el.get(ep.W + "name") == "JF48_c6":
                seen = True
                container.remove(el)
                continue
            if el.tag == ep.W + "bookmarkEnd" and seen:
                container.remove(el)
                break
            if not seen:
                continue
            if el.tag in (ep.W + "ins", ep.W + "del"):
                container.remove(el)
        tampered["word/document.xml"] = ep._serialize_document_xml(
            troot, tdecls, tdns)
        ep.write_docx_atomic(working, tampered)

        reconcile = call_edits("edits.reconcile", {"document_id": "d-main"})
        s1_cards = [card for card in reconcile["cards"]
                    if card["stream_id"] == "s1"]
        states = {card["card_id"]: card["db_state_after"]
                  for card in s1_cards}
        doc_view = {card["card_id"]: card["document"] for card in s1_cards}
        self.step("c10_reconcile_document_authoritative",
                  states["c1"] == "host_accepted"
                  and doc_view["c1"]["bookmark_present"] is True
                  and states["c2"] == "applied"
                  and states["c7"] == "applied"
                  and states["c3"] == "rejected"
                  and states["c6"] == "host_removed"
                  and doc_view["c6"]["bookmark_present"] is False
                  and reconcile["authoritative"] == "document",
                  states=states)
        cards_view = call_edits("edits.cards", {"document_id": "d-main"})
        db_states = {card["card_id"]: (card["state"], card["bookmark_present"])
                     for card in cards_view["cards"]
                     if card["stream_id"] == "s1"}
        self.step("c10_dual_persistence_db_updated",
                  db_states["c1"] == ("host_accepted", True)
                  and db_states["c2"] == ("applied", True)
                  and db_states["c7"] == ("applied", True)
                  and db_states["c3"] == ("rejected", False)
                  and db_states["c6"] == ("host_removed", False),
                  db_states=db_states)

        # ---- C11 DB 级扫描（卡片账状态闭集＋事件链）
        with contextlib.closing(self._cards_db(profile, "d-main")) as conn:
            rows = conn.execute(
                "SELECT state, COUNT(*) AS n FROM cards GROUP BY state"
            ).fetchall()
            state_counts = {row["state"]: row["n"] for row in rows}
            event_kinds = [row[0] for row in conn.execute(
                "SELECT DISTINCT kind FROM events").fetchall()]
        closed = set(ep.CARD_STATES)
        self.step("c11_card_db_closed_states_and_events",
                  set(state_counts) <= closed
                  and state_counts.get("host_accepted") == 1
                  and state_counts.get("host_removed") == 1
                  and state_counts.get("applied") == 2
                  and state_counts.get("rejected") == 1
                  and {"locate", "apply", "reject", "reconcile"}
                  <= set(event_kinds),
                  state_counts=state_counts, events=sorted(event_kinds))

    # ------------------------------------------------------------------
    def _state_root(self, profile: str) -> Path:
        return self._roots[profile]

    def _working(self, profile: str, document_id: str) -> Path:
        return (self._state_root(profile) / "edits-protocol"
                / document_id / "working.docx")

    def _cards_db(self, profile: str, document_id: str):
        import sqlite3
        path = (self._state_root(profile) / "edits-protocol"
                / document_id / "cards.db")
        connection = sqlite3.connect(str(path))
        connection.row_factory = sqlite3.Row
        return connection

    def bridge_negatives(self, config):
        # ---- C12 桥负向：未配置/未知方法/方法组冻结
        try:
            legal_entry.call("edits.cards", {"document_id": "d1"}, {})
            raise AssertionError("bridge_not_configured_expected")
        except NotConnected as exc:
            self.step("c12_bridge_not_configured",
                      "f48_state_root_missing" in str(exc))
        try:
            legal_entry.call("edits.bake", {"document_id": "d1"}, config)
            raise AssertionError("bridge_unknown_method_expected")
        except NotConnected as exc:
            self.step("c12_bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))
        self.step("c12_method_group_frozen",
                  legal_entry.EDITS_METHODS == F48_METHODS)

    # -- profile drivers ---------------------------------------------------
    _roots: dict[str, Path] = {}

    def run_desktop(self) -> int:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f48-desktop-")
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        self._roots["desktop"] = state_root / "edits-face"
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        config = {
            "harness_public_entry":
                str(self.harness_root / "tools/workflow-tools/harness"
                    "/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 120,
            "edits_state_root": str(state_root / "edits-face"),
        }
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(MATTER, "cas://profile-f48-recon")

        def call(method, args):
            return legal_entry.call(method, args, config)

        def query(sql, params):
            import sqlite3
            with contextlib.closing(store._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        print("[profile desktop] SQLite via product bridge subprocess",
              flush=True)
        self.common_flow("desktop",
                         call_edits=call, call_harness=call,
                         harness_ok=True, query_harness=query)
        self.bridge_negatives(config)
        return 0

    def run_selfhost(self, dsn: str) -> int:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root),
                     str(self.harness_root / "tests")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-f48-selfhost-")
        edits_root = Path(temporary.name) / "edits-face"
        self._roots["selfhost"] = edits_root
        store = PgMatterStore(
            Path(temporary.name) / "state", dsn=dsn,
            schema="f48_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        bound = {name: resolve_provider_method(name, units)
                 for name in HARNESS_METHODS_USED}
        bound["harness.formal_proposal_list"] = resolve_provider_method(
            "harness.formal_proposal_list", units)
        store.create_matter(MATTER, "cas://profile-f48-recon")

        edits_config = {"edits_state_root": str(edits_root)}

        def call_edits(method, args):
            return legal_entry.call(method, args, edits_config)

        def call_harness(method, args):
            return bound[method](**args)

        def query(sql, params):
            with contextlib.closing(store._connect()) as connection:
                rows = connection.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)",
              flush=True)
        self.common_flow("selfhost",
                         call_edits=call_edits, call_harness=call_harness,
                         harness_ok=True, query_harness=query)
        store.destroy()
        return 0


def write_evidence(profile: str, recon: Recon, harness_root: Path,
                   started: str, code: int) -> Path:
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" / "F48" \
        / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema": "juscite-f48-edits-protocol-recon/1",
        "unit": "W2b-U12",
        "feature": "F48",
        "profile": profile,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started,
        "finished_at": finished,
        "harness_worktree": str(harness_root),
        "harness_branch": "w2b-u11",
        "harness_base": "w2b-u01@0d5c79bc (formal proposal face)",
        "corpus": "tools/e12_corpus_gen.py --docx seed 20261017",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    (evidence_dir / "f48_edits_protocol_recon.json").write_text(
        payload + "\n", encoding="utf-8")
    lines = [f"# F48 edits 流式协议 recon（{profile}）",
             "",
             f"- unit: W2b-U12 · profile: {profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- harness: `{harness_root}` @ branch w2b-u11"
             "（基 w2b-u01@0d5c79bc；master 929d0802 零动）",
             f"- 语料：e12_corpus_gen --docx seed 20261017（两遍生成逐字节"
             "相同亲验）",
             f"- started: {started} · finished: {finished}",
             "",
             "| # | check | status |",
             "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']}"
                     f" | {check['status']} |")
    lines += ["", "全部合成材料；desktop＝产品桥（edits.*＋harness.* 子进程"
              " public_entry SQLite 全链），selfhost＝PgMatterStore 直连"
              " lh-pg-e08（同一封闭注册）＋edits.* 经 legal_entry。"]
    (evidence_dir / "f48_edits_protocol_recon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return evidence_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop"]
    if not (args.harness_root / "tools/workflow-tools/harness"
            "/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    failures = 0
    first = True
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon = Recon(args.harness_root)
        try:
            if first:
                # C01 分支/基/master/工作树干净亲验（只跑一次，两 profile
                # 共用同一 harness 检出）。
                recon.branch_checks()
            if profile == "desktop":
                code = recon.run_desktop()
            else:
                code = recon.run_selfhost(args.pg_dsn)
        except Exception as error:  # noqa: BLE001 - reported per profile
            print(f"RECON_FAIL[{profile}]: {error}", flush=True)
            recon.checks.append({"check": "recon_driver", "status": "FAIL",
                                 "error": str(error)[:400]})
            code = 2
        evidence_dir = write_evidence(profile, recon, args.harness_root,
                                      started, code)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={evidence_dir}", flush=True)
        if code != 0:
            failures += 1
        first = False
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
