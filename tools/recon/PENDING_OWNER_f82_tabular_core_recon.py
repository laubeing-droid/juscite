# -*- coding: utf-8 -*-
"""F82 Tabular 窄版闭环核心验收对账（PENDING_OWNER 版，工单 W2b-U05）。

闭环合同（06 F82 acceptance 列/批量/出处/支持状态/失效回读＋07 E14 主体面
＋08§1「F82 列/溯源/复核/重跑/人改分别」中的列/溯源段）：
  列三元组（列名/金标/值）＋批量执行（W2b-U01 F25 租约/generation 底座）
  ＋出处（引用逐条回原文）＋支持状态（核验戳经 U02 citation 面＝
  W2b-U02 extraction.gate→W2a-U14 citation.*）＋失效回读（源版本推进→
  审计漂移→失效登记→重抽取重闸重盖章）。顺序纪律＝先引用核验服务
  （F70/W2a-U14 已 VERIFIED）再接抽取（U02 已 VERIFIED），本单只接不重判。

分段（每 profile 同集 12 检）：
  C01 列合同：金标入账回读＋幂等重放＋异内容拒＋列集合不冻结拒（F82-列）
  C02 批量执行：4 行 claim→submit→done、批自动 completed（F25 底座）
  C03 列三元组：tabular.read 逐格（列名/金标/值）＋goldMatch（Decimal/
       文本/枚举/未对上）投影（F82-列）
  C04 闸结论经 U02 面：现行真引文×2 VERIFIED＋已废止＋虚构 REJECTED 理由
       具名（fail-closed 不放行）
  C05 支持戳：VERIFIED 戳入账投影 SUPPORTED_CITATION_LEVEL（引用级；命题
       恒不代签）；UNVERIFIED 候选拒盖章（先核验再接抽取的接线点纪律）
  C06 出处审计：材料侧页文本 sha 对账＋引用逐条在页内；法规侧同面复验
       状态一致（F82-溯源＝出处可审计）
  C07 失效回读①：材料页字节推进→审计 AUDIT_FAIL（sha 漂移）→失效登记
       source_version_stale→投影 INVALIDATED、历史条目保全
  C08 失效回读②：人改后投影 STALE_CELL_ADVANCED（戳描述旧世代、值保全）
  C09 重抽取重闸重盖章：新版页 sha→新候选批次→闸跑→重盖章→审计复 OK
  C10 拒绝戳不伪支持：已废止/虚构 REJECTED 戳投影 UNSUPPORTED_REJECTED
       理由具名、零引用、无伪造支持
  C11 fail-closed 蓄电池：audit 缺语料根/失效理由闭集外/候选缺页 sha/
       未知方法/伪造闸字段（U02 面）/未知批次 全 exit 3 具名
  C12 回读确定性：tabular.read 两跑投影语义相等

双 profile：
  desktop＝产品桥子进程全链（legal_entry CLI→[tabular.*→harness
  public_entry 子进程＋extraction 同进程]→SQLite MatterStore）——每次
  调用即新进程＝跨进程状态在库验证；
  selfhost＝PgMatterStore 直连容器 lh-pg-e08（provider registry 面）＋
  产品面同进程调用（tabular seam 指向 PG 绑定方法）。

用法（juscite worktree w2b-u05 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f82_tabular_core_recon.py \
      --profile desktop --profile selfhost

exit 0＝全部 profile 全部检过（RECON_OK）；证据 JSON 写 evidence/F82/
<profile>/。只读消费（语料/正式表/冻结面），不发任何网络请求，不写正式
目录，不触碰 oc28 与 %APPDATA%。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
MATTER = "m-f82-recon"

DEFAULT_FORMAL_ROOT = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices"
)
# E22 冻结面 v1.1（codices 分支 jusbench/w2a-u14-f70-citation @ dc0caf68e）
DEFAULT_CODICES_REPO = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14"
)
DEFAULT_HARNESS_ROOT = (
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u05"
)
LCCC_V11_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a"
)

PIPL_TITLE = "中华人民共和国个人信息保护法"   # 现行（01）
PIPL_ART1_QUOTE = (
    "为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，"
    "根据宪法，制定本法。"
)
PIPL_ART7_QUOTE = "处理个人信息应当遵循公开、透明原则"  # 第七条（真引文）
ABOLISHED_TITLE = "中华人民共和国合同法"       # 已废止（04）
FABRICATED_TITLE = "中华人民共和国月球资源开发管辖法"

DOC = "synth_matter_doc_0001"

PAGE_3_V1 = (
    "第三条 合同价款。本合同总价为人民币123,456.78元"
    "（大写：壹拾贰万叁仟肆佰伍拾陆元柒角捌分），含税。"
    "依据《%s》第一条：“%s”" % (PIPL_TITLE, PIPL_ART1_QUOTE)
)
PAGE_3_V2 = (
    "第三条 合同价款（2026-10-16 修订版）。双方确认本合同总价为人民币"
    "123,456.78元（含税，不再另行调整）。"
    "依据《%s》第一条：“%s”" % (PIPL_TITLE, PIPL_ART1_QUOTE)
)
PAGE_4 = (
    "第五条 付款期限。验收合格后三十日内一次性支付。"
    "依据《%s》第七条：“%s”" % (PIPL_TITLE, PIPL_ART7_QUOTE)
)
PAGE_5 = (
    "第八条 争议解决。因本合同引起的争议，依据《%s》第五条处理。"
    % ABOLISHED_TITLE
)
PAGE_6 = (
    "第十条 管辖。因本合同引起的诉讼由月球法院专属管辖，"
    "依据《%s》第一条。" % FABRICATED_TITLE
)


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------- #
# 合成语料（页文本；材料真源替身——本单审计面只读，生产接线换 E12 导出）
# ---------------------------------------------------------------------- #


def write_corpus(root: Path, page3_text: str = PAGE_3_V1) -> dict:
    doc_dir = root / DOC
    doc_dir.mkdir(parents=True, exist_ok=True)
    pages = {3: page3_text, 4: PAGE_4, 5: PAGE_5, 6: PAGE_6}
    shas = {}
    for page, text in pages.items():
        (doc_dir / ("page-%d.txt" % page)).write_text(text, encoding="utf-8")
        shas[page] = sha256_text(text)
    return shas


# ---------------------------------------------------------------------- #
# 确定性抽取（recon 版 worker：正则；值语义解释到此为止）
# ---------------------------------------------------------------------- #

import re  # noqa: E402

_AMOUNT_RE = re.compile(r"总价为人民币([\d,，.]+)元")
_TERM_RE = re.compile(r"验收合格后(.+?)。")


def extract_amount(page_text: str):
    found = _AMOUNT_RE.search(page_text)
    return (found.group(1).replace("，", ",") + " 元") if found else None


def extract_term(page_text: str):
    found = _TERM_RE.search(page_text)
    return found.group(1) if found else None


def assertion_texts(shas: dict) -> list:
    """4 条抽取候选（断言文本＋出处钉字节）。"""
    return [
        {"text": "依据《%s》第一条：“%s”" % (PIPL_TITLE, PIPL_ART1_QUOTE),
         "provenance": {"source": "material_extraction", "doc": DOC,
                        "page": 3, "textSha256": shas[3]}},
        {"text": "依据《%s》第七条：“%s”" % (PIPL_TITLE, PIPL_ART7_QUOTE),
         "provenance": {"source": "material_extraction", "doc": DOC,
                        "page": 4, "textSha256": shas[4]}},
        {"text": "依据《%s》第五条处理" % ABOLISHED_TITLE,
         "provenance": {"source": "material_extraction", "doc": DOC,
                        "page": 5, "textSha256": shas[5]}},
        {"text": "依据《%s》第一条" % FABRICATED_TITLE,
         "provenance": {"source": "material_extraction", "doc": DOC,
                        "page": 6, "textSha256": shas[6]}},
    ]


WANT_GATE = {
    "cand_0001": ("CITATION_VERIFIED", []),
    "cand_0002": ("CITATION_VERIFIED", []),
    "cand_0003": ("REJECTED", ["OLD_VERSION_ABOLISHED"]),
    "cand_0004": ("REJECTED", ["FABRICATED_TITLE_LOCAL_MISS"]),
}


def gate_projection(gate_response: dict) -> dict:
    return {
        r["candidate_id"]: (r["gate_status"],
                            [x["reason"] for x in r["rejection_reasons"]])
        for r in gate_response["results"]}


COLUMNS = [
    {"id": "amount", "name": "合同金额", "format": "decimal-string",
     "version": "1", "gold": {"kind": "number", "expect": "123456.78"}},
    {"id": "payment_term", "name": "付款期限", "format": "text",
     "version": "1", "gold": {"kind": "text",
                              "expect": "三十日内一次性支付"}},
    {"id": "cited", "name": "法律依据", "format": "text", "version": "1",
     "gold": {"kind": "text"}},
]

SCOPE = {"kind": "matter", "matterId": MATTER}


def command_key(request_id: str) -> dict:
    return {"requestId": "f82-" + request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


# ---------------------------------------------------------------------- #
# 双 profile 共用闭环
# ---------------------------------------------------------------------- #


def expect_not_connected(checks: Checks, check_id: str, outcome: dict,
                         code_part: str) -> None:
    payload = outcome.get("payload", {})
    checks.add(check_id,
               outcome.get("exit") == 3
               and payload.get("status") == "NOT_CONNECTED"
               and str(payload.get("code", "")).startswith(code_part),
               "exit=%s %s/%s" % (outcome.get("exit"),
                                  payload.get("status"),
                                  payload.get("code")))


def common_flow(checks: Checks, call, corpus: Path, shas: dict) -> dict:
    page3_path = corpus / DOC / "page-3.txt"

    # --- 建批（F25 底座；列集合建批冻结；5 行制——row-5 收尾前保持批
    #     active 供人改段用，末段补完证 completed）--------------------------
    created = call("harness.review_batch_create", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rb1"),
        "batch": {"id": "brt-f82", "title": "Tabular 窄版闭环（F82 合成）",
                  "columns": [{"id": column["id"], "name": column["name"]}
                              for column in COLUMNS],
                  "rows": [{"id": "row-%d" % index,
                            "cells": {column["id"]: None
                                      for column in COLUMNS}}
                           for index in range(1, 6)]}})
    if created.get("status") != "active":
        raise SystemExit("FATAL: 建批失败：%s" % created)

    # --- C01 列合同（F82-列）-------------------------------------------
    defined = call("harness.review_columns_define", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rc1"),
        "batch_id": "brt-f82", "columns": COLUMNS})
    read_cols = call("harness.review_columns_read",
                     {"scope": SCOPE, "batch_id": "brt-f82"})
    replay = call("harness.review_columns_define", {
        "actor_id": "lawyer-2", "scope": SCOPE, "key": command_key("rc2"),
        "batch_id": "brt-f82", "columns": COLUMNS})
    conflict = call("harness.review_columns_define", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rc3"),
        "batch_id": "brt-f82", "columns": [
            dict(column, gold={"kind": "number", "expect": "999.00"})
            if column["id"] == "amount" else column for column in COLUMNS]})
    unfrozen = call("harness.review_columns_define", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rc4"),
        "batch_id": "brt-f82", "columns": COLUMNS + [
            {"id": "ghost", "name": "多列", "format": "text", "version": "1",
             "gold": {"kind": "none"}}]})
    gold_by_id = {column["id"]: column.get("gold")
                  for column in read_cols.get("columns", [])}
    checks.add(
        "C01_column_contract_gold_readback",
        defined.get("replayed") is False
        and replay.get("replayed") is True
        and gold_by_id.get("amount") == {"kind": "number",
                                         "expect": "123456.78"}
        and gold_by_id.get("payment_term") == {
            "kind": "text", "expect": "三十日内一次性支付"}
        and gold_by_id.get("cited") == {"kind": "text"}
        and str(conflict.get("code", "")).startswith(
            "review_columns_conflict")
        and str(unfrozen.get("code", "")).startswith("columns_not_frozen"),
        "金标入账回读（amount=number:123456.78/payment_term=text/cited="
        "纯类型）；幂等重放 replayed=True；异内容 review_columns_conflict；"
        "列集合不冻结 columns_not_frozen")

    # --- C02 批量执行（F25 底座租约循环）-------------------------------
    page3_text = page3_path.read_text(encoding="utf-8")
    row_values = {
        "row-1": {"amount": extract_amount(page3_text),
                  "cited": "《%s》第一条" % PIPL_TITLE},
        "row-2": {"payment_term": extract_term(PAGE_4),
                  "cited": "《%s》第七条" % PIPL_TITLE},
        "row-3": {"cited": "《%s》第五条" % ABOLISHED_TITLE},
        "row-4": {"amount": "777.00 元",  # 故意对不上金标
                  "cited": "《%s》第一条" % FABRICATED_TITLE},
    }
    for index, row_id in enumerate(sorted(row_values), start=1):
        claimed = call("harness.review_batch_claim", {
            "actor_id": "worker-1", "scope": SCOPE,
            "key": command_key("cl%d" % index), "batch_id": "brt-f82",
            "row_id": row_id, "lease_ttl_seconds": 600})
        call("harness.review_batch_submit", {
            "actor_id": "worker-1", "scope": SCOPE,
            "key": command_key("sb%d" % index), "batch_id": "brt-f82",
            "row_id": row_id, "lease_token": claimed["lease"]["token"],
            "cells": [{"cellId": cell_id, "value": value,
                       "generation": 0}
                      for cell_id, value in row_values[row_id].items()]})
    batch_read = call("harness.review_batch_read",
                      {"scope": SCOPE, "batch_id": "brt-f82"})
    checks.add(
        "C02_batch_execution_via_leases",
        batch_read.get("status") == "active"
        and batch_read.get("counts") == {"pending": 1, "leased": 0,
                                         "done": 4, "total": 5},
        "4 行 claim→submit→done（租约+generation 守卫底座）；row-5 留批内"
        "（末段补完证 completed）；counts=%s" % batch_read.get("counts"))

    # --- C04 闸结论经 U02 面（先核验再接抽取）--------------------------
    registered = call("extraction.register", {
        "batch_id": "f82a", "candidates": assertion_texts(shas)})
    gate = call("extraction.gate", {"batch_id": "f82a", "as_of": RUN_DATE})
    got = gate_projection(gate.get("result", gate))
    checks.add(
        "C04_gate_verdicts_via_u02_face",
        registered.get("result", registered).get("registered") == 4
        and got == WANT_GATE
        and gate.get("result", gate).get("face_sha256")
        == LCCC_V11_SHA256,
        "闸结论=%s（face_sha256 钉定回读）" % json.dumps(
            got, ensure_ascii=False))

    # --- C05 支持戳经 U02 面＋未核拒盖章 --------------------------------
    stamped = call("tabular.support_stamp", {
        "extraction_batch_id": "f82a", "candidate_id": "cand_0001",
        "review_batch_id": "brt-f82", "row_id": "row-1", "cell_id": "cited",
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("st1")})
    support1 = call("harness.review_support_read",
                    {"scope": SCOPE, "batch_id": "brt-f82", "row_id": "row-1",
                     "cell_id": "cited"})
    projection1 = (support1.get("projections") or [{}])[0]
    entry1 = support1["entries"]["row-1:cited"][0]["record"]
    call("extraction.register", {
        "batch_id": "f82u",
        "candidates": [assertion_texts(shas)[0]]})
    ungated = call("tabular.support_stamp", {
        "extraction_batch_id": "f82u", "candidate_id": "cand_0001",
        "review_batch_id": "brt-f82", "row_id": "row-1", "cell_id": "cited",
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("st0")})
    checks.add(
        "C05_support_stamp_via_u02_face",
        stamped.get("seq") == 1 and stamped.get("cellGeneration") == 1
        and projection1.get("supportStatus") == "SUPPORTED_CITATION_LEVEL"
        and entry1["gate"]["via"] == "extraction.gate(W2b-U02)"
        and entry1["gate"]["faceSha256"] == LCCC_V11_SHA256
        and entry1["gate"]["asOf"] == RUN_DATE
        and entry1["provenance"]["textSha256"] == shas[3]
        and ungated.get("exit") == 3
        and str(ungated.get("payload", {}).get("code", "")).startswith(
            "tabular_stamp_requires_gated_candidate"),
        "VERIFIED 戳入账（via=extraction.gate(W2b-U02)/faceSha256 钉定/"
        "asOf/出处 sha）；投影 SUPPORTED_CITATION_LEVEL（引用级）；未过闸"
        "候选拒盖章 exit 3")

    # --- C03 列三元组回读（F82-列）--------------------------------------
    table = call("tabular.read", {"review_batch_id": "brt-f82",
                                  "scope": SCOPE})
    triples = {}
    for row in table.get("rows", []):
        for cell in row.get("cells", []):
            triples[(row["rowId"], cell["columnId"])] = cell
    checks.add(
        "C03_column_triples_readback",
        table.get("columnContractDefined") is True
        and triples[("row-1", "amount")]["columnName"] == "合同金额"
        and triples[("row-1", "amount")]["gold"] == {
            "kind": "number", "expect": "123456.78"}
        and triples[("row-1", "amount")]["value"] == "123,456.78 元"
        and triples[("row-1", "amount")]["goldMatch"] is True
        and triples[("row-2", "payment_term")]["value"] == "三十日内一次性支付"
        and triples[("row-2", "payment_term")]["goldMatch"] is True
        and triples[("row-4", "amount")]["goldMatch"] is False
        and triples[("row-1", "payment_term")]["goldMatchReason"]
        == "value_absent"
        and triples[("row-1", "cited")]["supportStatus"]
        == "SUPPORTED_CITATION_LEVEL"
        and triples[("row-3", "cited")]["supportStatus"] == "NO_STAMP",
        "列三元组逐格回读：金标对上（含千位逗号/单位 Decimal 对照）、文本"
        "对上、777.00 对不上（goldMatch=False）、缺值 value_absent、支持"
        "状态随格")

    # --- C06 出处审计（F82-溯源）----------------------------------------
    audit1 = call("tabular.audit", {"review_batch_id": "brt-f82",
                                    "scope": SCOPE})
    checks.add(
        "C06_provenance_audit_item_by_item",
        audit1.get("auditStatus") == "AUDIT_OK"
        and audit1.get("sourceTraced") == "1/1"
        and audit1.get("statuteConsistent") == "1/1"
        and audit1["findings"][0]["citations"][0]["inSourceText"] is True
        and audit1["findings"][0]["statuteReplay"]["consistent"] is True,
        "出处逐条回原文：材料侧页 sha 对账＋引用文本在页内；法规侧同面"
        "复验状态一致（sourceTraced=%s statuteConsistent=%s）" % (
            audit1.get("sourceTraced"), audit1.get("statuteConsistent")))

    # --- C07 失效回读①（源版本推进→审计漂移→失效登记）-------------------
    page3_path.write_text(PAGE_3_V2, encoding="utf-8")
    shas_v2 = dict(shas)
    shas_v2[3] = sha256_text(PAGE_3_V2)
    audit2 = call("tabular.audit", {"review_batch_id": "brt-f82",
                                    "scope": SCOPE})
    invalidated = call("tabular.invalidate", {
        "review_batch_id": "brt-f82", "row_id": "row-1", "cell_id": "cited",
        "reason": "source_version_stale", "detail": "材料页字节推进：sha 漂移",
        "source_ref": {"doc": DOC, "page": 3},
        "actor_id": "auditor-1", "scope": SCOPE, "key": command_key("inv1")})
    support2 = call("harness.review_support_read",
                    {"scope": SCOPE, "batch_id": "brt-f82", "row_id": "row-1",
                     "cell_id": "cited"})
    projection2 = (support2.get("projections") or [{}])[0]
    kinds = [entry["entryKind"]
             for entry in support2["entries"]["row-1:cited"]]
    checks.add(
        "C07_source_drift_invalidation_readback",
        audit2.get("auditStatus") == "AUDIT_FAIL"
        and audit2["findings"][0]["sourceShaOk"] is False
        and invalidated.get("reason") == "source_version_stale"
        and projection2.get("supportStatus") == "INVALIDATED"
        and kinds == ["support", "invalidation"],
        "页字节推进→审计 AUDIT_FAIL（sha 漂移）→失效登记→投影 INVALIDATED；"
        "历史条目 %s 保全可回读" % kinds)

    # --- C09 重抽取重闸重盖章（失效后的恢复闭环）------------------------
    re_extracted = call("extraction.register", {
        "batch_id": "f82b", "candidates": assertion_texts(shas_v2)[:1]})
    gate_b = call("extraction.gate", {"batch_id": "f82b",
                                      "as_of": RUN_DATE})
    restamped = call("tabular.support_stamp", {
        "extraction_batch_id": "f82b", "candidate_id": "cand_0001",
        "review_batch_id": "brt-f82", "row_id": "row-1", "cell_id": "cited",
        "actor_id": "worker-2", "scope": SCOPE, "key": command_key("st2")})
    support3 = call("harness.review_support_read",
                    {"scope": SCOPE, "batch_id": "brt-f82", "row_id": "row-1",
                     "cell_id": "cited"})
    projection3 = (support3.get("projections") or [{}])[0]
    audit3 = call("tabular.audit", {"review_batch_id": "brt-f82",
                                    "scope": SCOPE})
    checks.add(
        "C09_re_extract_re_gate_re_stamp",
        re_extracted.get("result", re_extracted).get("registered") == 1
        and gate_projection(gate_b.get("result", gate_b))[
            "cand_0001"][0] == "CITATION_VERIFIED"
        and restamped.get("seq") == 3
        and projection3.get("supportStatus") == "SUPPORTED_CITATION_LEVEL"
        and projection3.get("entryCount") == 3
        and audit3.get("auditStatus") == "AUDIT_OK"
        and support3["entries"]["row-1:cited"][-1]["record"][
            "provenance"]["textSha256"] == shas_v2[3],
        "新版页 sha→新候选→重闸 VERIFIED→重盖章（seq=3）→投影恢复支持；"
        "末戳出处钉新版字节；审计复 AUDIT_OK")

    # --- C08 失效回读②（人改后 STALE 投影）------------------------------
    stamped2 = call("tabular.support_stamp", {
        "extraction_batch_id": "f82a", "candidate_id": "cand_0002",
        "review_batch_id": "brt-f82", "row_id": "row-2", "cell_id": "cited",
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("st3")})
    human = call("harness.review_batch_human_edit", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("he1"),
        "batch_id": "brt-f82", "row_id": "row-2",
        "cells": [{"cellId": "cited", "value": "《%s》第七条（人改核正）"
                    % PIPL_TITLE, "generation": 1}]})
    support4 = call("harness.review_support_read",
                    {"scope": SCOPE, "batch_id": "brt-f82", "row_id": "row-2",
                     "cell_id": "cited"})
    projection4 = (support4.get("projections") or [{}])[0]
    checks.add(
        "C08_human_edit_stale_projection",
        stamped2.get("seq") == 1
        and human["cells"]["cited"]["source"] == "human"
        and projection4.get("supportStatus") == "STALE_CELL_ADVANCED"
        and projection4["detail"]["stampedGeneration"] == 1
        and projection4["detail"]["currentGeneration"] == 2
        and projection4["detail"]["currentSource"] == "human",
        "人改后投影 STALE_CELL_ADVANCED（戳描述 gen1/当前 gen2/来源 human）；"
        "人改值保全不覆")

    # --- C10 拒绝戳不伪支持 ----------------------------------------------
    stamp3 = call("tabular.support_stamp", {
        "extraction_batch_id": "f82a", "candidate_id": "cand_0003",
        "review_batch_id": "brt-f82", "row_id": "row-3", "cell_id": "cited",
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("st4")})
    stamp4 = call("tabular.support_stamp", {
        "extraction_batch_id": "f82a", "candidate_id": "cand_0004",
        "review_batch_id": "brt-f82", "row_id": "row-4", "cell_id": "cited",
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("st5")})
    support5 = call("harness.review_support_read",
                    {"scope": SCOPE, "batch_id": "brt-f82"})
    by_cell = {(p.get("rowId"), p.get("cellId")): p
               for p in support5.get("projections", [])}
    checks.add(
        "C10_rejected_stamps_never_fabricate_support",
        stamp3.get("seq") == 1 and stamp4.get("seq") == 1
        and by_cell[("row-3", "cited")]["supportStatus"]
        == "UNSUPPORTED_REJECTED"
        and by_cell[("row-3", "cited")]["detail"]["gate"][
            "rejectionReasons"][0]["reason"] == "OLD_VERSION_ABOLISHED"
        and by_cell[("row-4", "cited")]["supportStatus"]
        == "UNSUPPORTED_REJECTED"
        and by_cell[("row-4", "cited")]["detail"]["gate"][
            "rejectionReasons"][0]["reason"]
        == "FABRICATED_TITLE_LOCAL_MISS",
        "已废止/虚构 REJECTED 戳投影 UNSUPPORTED_REJECTED 理由具名——拒绝"
        "候选不产支持、不伪已核")

    # --- 批收尾：row-5 补完（末行自动 completed 的批量执行终态）---------
    claim5 = call("harness.review_batch_claim", {
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("cl5"),
        "batch_id": "brt-f82", "row_id": "row-5",
        "lease_ttl_seconds": 600})
    final_submit = call("harness.review_batch_submit", {
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("sb5"),
        "batch_id": "brt-f82", "row_id": "row-5",
        "lease_token": claim5["lease"]["token"],
        "cells": [{"cellId": "cited", "value": "《%s》第一条（待复核）"
                    % PIPL_TITLE, "generation": 0}]})
    final_read = call("harness.review_batch_read",
                      {"scope": SCOPE, "batch_id": "brt-f82"})
    checks.add(
        "C10B_batch_completes_on_last_row",
        final_submit.get("state") == "done"
        and final_read.get("status") == "completed"
        and final_read.get("counts") == {"pending": 0, "leased": 0,
                                         "done": 5, "total": 5},
        "末行提交批自动 completed；终态 counts=%s"
        % final_read.get("counts"))

    # --- C11 fail-closed 蓄电池 ------------------------------------------
    expect_not_connected(
        checks, "C11A_audit_corpus_root_required",
        call("tabular.audit", {"review_batch_id": "brt-f82", "scope": SCOPE},
             config_override={"tabular_corpus_root": None}),
        "tabular_corpus_root_not_configured")
    expect_not_connected(
        checks, "C11B_invalidate_reason_closed",
        call("tabular.invalidate", {
            "review_batch_id": "brt-f82", "row_id": "row-1",
            "cell_id": "cited", "reason": "lawyer_changed_mind",
            "actor_id": "a", "scope": SCOPE, "key": command_key("invx")}),
        "tabular_invalidate_reason_invalid")
    call("extraction.register", {
        "batch_id": "f82n",
        "candidates": [{"text": "依据《%s》第一条" % PIPL_TITLE,
                        "provenance": {"source": "material_extraction",
                                       "doc": DOC, "page": 3}}]})
    call("extraction.gate", {"batch_id": "f82n", "as_of": RUN_DATE})
    expect_not_connected(
        checks, "C11C_stamp_requires_page_sha",
        call("tabular.support_stamp", {
            "extraction_batch_id": "f82n", "candidate_id": "cand_0001",
            "review_batch_id": "brt-f82", "row_id": "row-1",
            "cell_id": "cited", "actor_id": "worker-1", "scope": SCOPE,
            "key": command_key("stn")}),
        "tabular_stamp_requires_page_sha256")
    expect_not_connected(
        checks, "C11D_unknown_harness_method",
        call("harness.review_support_verify", {"scope": SCOPE}),
        "method_not_connected:")
    expect_not_connected(
        checks, "C11E_forged_gate_fields_refused",
        call("extraction.register", {
            "batch_id": "f82forge",
            "candidates": [{"text": "依据《%s》第一条" % PIPL_TITLE,
                            "gate_status": "CITATION_VERIFIED"}]}),
        "extraction_register_gate_fields_refused:")
    ghost = call("harness.review_support_read",
                 {"scope": SCOPE, "batch_id": "ghost"})
    checks.add(
        "C11F_unknown_batch",
        str(ghost.get("code", "")).startswith("review_batch_not_found:ghost"),
        "未知批次 typed 码=%s" % ghost.get("code"))

    # --- C12 回读确定性 ---------------------------------------------------
    table_a = call("tabular.read", {"review_batch_id": "brt-f82",
                                    "scope": SCOPE})
    table_b = call("tabular.read", {"review_batch_id": "brt-f82",
                                    "scope": SCOPE})
    checks.add(
        "C12_readback_determinism",
        json.dumps(table_a, sort_keys=True, ensure_ascii=False)
        == json.dumps(table_b, sort_keys=True, ensure_ascii=False)
        and table_a.get("rows"),
        "tabular.read 两跑投影语义相等（确定性）")

    return {
        "gate_projection": {k: list(v) for k, v in got.items()},
        "support_counts": support5.get("counts"),
        "audit_final": audit3.get("auditStatus"),
        "triples_count": len(triples),
    }


# ---------------------------------------------------------------------- #
# profile drivers
# ---------------------------------------------------------------------- #


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks = Checks()

    def base_config(self, state_root: Path, corpus: Path,
                    extraction_root: Path) -> dict:
        registration = state_root.parent / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        return {
            "harness_public_entry": str(
                self.harness_root
                / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 180,
            "harness_python": sys.executable,
            "extraction_gate_state_root": str(extraction_root),
            "codices_import_path": None,   # filled by caller
            "codices_formal_root": None,
            "codices_face_sha256": LCCC_V11_SHA256,
            "tabular_corpus_root": str(corpus),
        }

    # -- desktop: full product-bridge subprocess chain --------------------
    def run_desktop(self, formal_root: str, codices_repo: str) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="juscite-f82-desktop-")
        self.add_cleanup(temporary.cleanup)
        base = Path(temporary.name)
        state_root = base / "state"
        state_root.mkdir(parents=True)
        extraction_root = base / "extraction"
        corpus = base / "corpus"
        shas = write_corpus(corpus)
        config = self.base_config(state_root, corpus, extraction_root)
        config["codices_import_path"] = codices_repo
        config["codices_formal_root"] = formal_root
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        MatterStore(state_root).create_matter(MATTER,
                                              "cas://profile-f82-recon")

        def call(method, args, config_override=None):
            merged = dict(config)
            if config_override:
                for key, value in config_override.items():
                    if value is None:
                        merged.pop(key, None)
                    else:
                        merged[key] = value
            outcome = call_entry(method, args, merged)
            if outcome["exit"] == 0:
                return outcome["result"] if outcome["result"] \
                    is not None else {}
            payload = outcome["payload"]
            return {"exit": outcome["exit"], "payload": payload,
                    "code": payload.get("code")
                    if isinstance(payload, dict) else None}

        print("[profile desktop] SQLite via product bridge subprocess "
              "(legal_entry CLI→harness public_entry)", flush=True)
        common_flow(self.checks, call, corpus, shas)

    # -- selfhost: PgMatterStore direct + in-process product faces --------
    def run_selfhost(self, dsn: str, formal_root: str,
                     codices_repo: str) -> None:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root), str(self.harness_root / "tests"),
                     str(REPO_ROOT / "implementation/python")):
            if path not in sys.path:
                sys.path.insert(0, path)
        import contextlib
        import uuid as _uuid

        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(prefix="juscite-f82-selfhost-")
        self.add_cleanup(temporary.cleanup)
        base = Path(temporary.name)
        store = PgMatterStore(
            base / "state", dsn=dsn,
            schema="f82_" + _uuid.uuid4().hex[:12])
        units = HarnessUnits(store)
        bound = {name: resolve_provider_method(name, units)
                 for name in (
                     "harness.review_batch_create",
                     "harness.review_batch_claim",
                     "harness.review_batch_submit",
                     "harness.review_batch_human_edit",
                     "harness.review_batch_read",
                     "harness.review_columns_define",
                     "harness.review_columns_read",
                     "harness.review_support_record",
                     "harness.review_support_invalidate",
                     "harness.review_support_read")}
        store.create_matter(MATTER, "cas://profile-f82-recon-pg")
        corpus = base / "corpus"
        shas = write_corpus(corpus)
        extraction_root = base / "extraction"
        config = {
            "extraction_gate_state_root": str(extraction_root),
            "codices_import_path": codices_repo,
            "codices_formal_root": formal_root,
            "codices_face_sha256": LCCC_V11_SHA256,
            "tabular_corpus_root": str(corpus),
        }
        import extraction_gate
        import tabular_review
        from bridge_errors import NotConnected as NotConnected_

        patcher = unittest_mock_patch(
            tabular_review, "_harness_call",
            lambda method, args, cfg: bound[method](**args))
        patcher.start()
        self.add_cleanup(patcher.stop)

        def call(method, args, config_override=None):
            merged = dict(config)
            if config_override:
                for key, value in config_override.items():
                    if value is None:
                        merged.pop(key, None)
                    else:
                        merged[key] = value
            if method.startswith("harness."):
                if method not in bound:
                    # 桥形态对齐：冻结方法组外＝NOT_CONNECTED 具名。
                    return {"exit": 3, "payload": {
                        "status": "NOT_CONNECTED",
                        "code": "method_not_connected:" + method}}
                try:
                    return bound[method](**args)
                except Exception as exc:  # harness 面码原样上浮（不吞不改）
                    return {"exit": 1, "code": str(exc), "payload": {
                        "status": "HARNESS_FAIL", "code": str(exc)}}
            if method.startswith("extraction."):
                try:
                    return extraction_gate.extraction_call(method, args,
                                                           merged)
                except NotConnected_ as exc:
                    return {"exit": 3, "payload": {"status": "NOT_CONNECTED",
                                                    "code": str(exc)}}
            # tabular.*
            try:
                return tabular_review.tabular_call(method, args, merged)
            except NotConnected_ as exc:
                return {"exit": 3, "payload": {"status": "NOT_CONNECTED",
                                               "code": str(exc)}}

        print("[profile selfhost] PgMatterStore direct (provider registry "
              "face) + in-process product faces", flush=True)
        try:
            common_flow(self.checks, call, corpus, shas)
        finally:
            store.destroy()

    # -- tiny cleanup registry --------------------------------------------
    def add_cleanup(self, fn) -> None:
        self._cleanups.append(fn)

    _cleanups: list = []

    def cleanup(self) -> None:
        for fn in reversed(self._cleanups):
            try:
                fn()
            except Exception:
                pass


def unittest_mock_patch(target, attribute, replacement):
    import unittest.mock
    return unittest.mock.patch.object(target, attribute, replacement)


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用（legal_entry CLI）；返回 {exit, payload, code}。"""
    request_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    config_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "args": args}, request_handle,
                  ensure_ascii=False)
        request_handle.close()
        json.dump(config, config_handle, ensure_ascii=False)
        config_handle.close()
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, text=True, encoding="utf-8",
            timeout=900, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload,
                "code": payload.get("code") if isinstance(payload, dict)
                else None,
                "result": payload.get("result") if isinstance(payload, dict)
                else None}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def _unwrap(outcome: dict) -> dict:
    """call() 返回归一：desktop 子进程径已有 result 键；同进程径返回本体。"""
    return outcome


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.path.insert(0, str(REPO_ROOT / "implementation/python"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=("desktop", "selfhost"), dest="profiles",
                        help="发行形态（可重复；不给则双形态全跑）")
    parser.add_argument("--formal-root", default=DEFAULT_FORMAL_ROOT)
    parser.add_argument("--codices-repo", default=DEFAULT_CODICES_REPO)
    parser.add_argument("--harness-root", default=DEFAULT_HARNESS_ROOT)
    parser.add_argument(
        "--pg-dsn",
        default="postgresql://lh_app:e08-synth-only@127.0.0.1:55432/"
                "legal_harness",
        help="selfhost PgMatterStore 直连 DSN（默认＝本机合成容器 "
             "lh-pg-e08，deploy/docker-compose.pg.yml 同拓扑；合成专用"
             "凭据）")
    parser.add_argument("--evidence-root", default="evidence/F82")
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]

    lccc_path = os.path.join(args.codices_repo, "lccc_consumer.py")
    if not os.path.isfile(lccc_path) \
            or sha256_file(lccc_path) != LCCC_V11_SHA256:
        print("FATAL: 冻结面 v1.1 lccc_consumer.py 不在 %s 或 sha256 漂移"
              % args.codices_repo)
        return 2
    if not os.path.isfile(os.path.join(
            args.harness_root,
            "tools/workflow-tools/harness/public_entry.py")):
        print("FATAL: harness 公开入口不在 %s（w2b-u05 worktree）"
              % args.harness_root)
        return 2

    recon = Recon(Path(args.harness_root))
    per_profile: dict = {}
    all_ok = True
    try:
        for profile in profiles:
            recon.checks = Checks()
            if profile == "desktop":
                recon.run_desktop(args.formal_root, args.codices_repo)
            else:
                recon.run_selfhost(args.pg_dsn, args.formal_root,
                                   args.codices_repo)
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd=str(REPO_ROOT)).stdout.strip()
            harness_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd=str(args.harness_root)).stdout.strip()
            evidence = {
                "run_date": RUN_DATE,
                "profile": profile,
                "command": "python -X utf8 " + " ".join(sys.argv[1:]),
                "cwd": str(REPO_ROOT),
                "subject_commit": commit,
                "harness_commit": harness_commit,
                "frozen_face": {
                    "lccc_consumer.py(v1.1)": LCCC_V11_SHA256,
                    "legal_documents.csv": sha256_file(os.path.join(
                        args.formal_root, "legal_documents.csv")),
                },
                "checks": recon.checks.items,
                "passed": recon.checks.passed_count,
                "total": len(recon.checks.items),
                "overall": "PASS" if recon.checks.all_passed else "FAIL",
            }
            out_dir = REPO_ROOT / args.evidence_root / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / ("f82-tabular-core-recon-%s.json"
                        % time.strftime("%Y%m%dT%H%M%S%z"))).write_text(
                json.dumps(evidence, ensure_ascii=False, indent=1),
                encoding="utf-8")
            per_profile[profile] = evidence
            all_ok = all_ok and recon.checks.all_passed
            print("---")
            print("profile=%s: %d/%d checks" % (
                profile, recon.checks.passed_count,
                len(recon.checks.items)))
    finally:
        recon.cleanup()
    print("RECON_%s（%s）" % ("OK" if all_ok else "FAIL",
                             "+".join(profiles)))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
