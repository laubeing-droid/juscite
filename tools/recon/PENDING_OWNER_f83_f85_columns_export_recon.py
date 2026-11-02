# -*- coding: utf-8 -*-
"""F83 合同列预设＋F85 结果导出 Excel 验收对账（W3-U15）。

F83（06 行，双实例）：列预设（合同审查 10+ 列模板）——acceptance 断言
「合同列预设字段与 format 严格分离；每列金标、缺值/多值/未知不伪填」：
  - 冻结预设 12 字段（≥10）；字段层 {id,name,gold} 与 format 层
    {id,format} 严格分离（字段携 format 键/format 表携 gold＝具名拒；
    两层 id 集合恰等）；每列必有金标（kind 闭集与 tabular 面同集）；
  - 申报唯一列权威＝F82 列合同（harness.review_columns_define，W2b-U05
    VERIFIED）：列集合不冻结 columns_not_frozen／异内容 review_columns_
    conflict 具名拒不复制；申报回读逐列带 format＋gold；
  - 填充投影：缺值（0 提及）/多值（≥2 互异提及）/未知（number 金标列单
    提及不可 Decimal 解析）恒 value=None＋具名 fill——绝不编造占位值，
    落批后格值如实缺席（tabular.read goldMatchReason=value_absent）。

F85（06 行，双实例，依赖 F82/F87）：结果导出 Excel（引文标记脱壳）——
acceptance 断言「Excel 真实格值与可审引用列一致；内部标记脱壳不丢来源
——XLSX 确定性生成两跑同字节」：
  - 同源投影＝tabular.read（W2b-U05）×harness.review_support_read；真实
    格值＝内部引文标记（⟦引:…⟧）剥除后逐字保留；可审引用列＝支持戳引用
    （F87 闸三态＋F70 状态＋doc/page/sha256 出处）＋未入戳被剥标记
    （UNVERIFIED 具名，出处具名缺席不编造）；
  - 标记壳残留/空引文标记/float 值/未知方法/未知批次全具名拒不静默出门；
  - XLSX 纯标准库确定性生成（zip 项时间戳钉定＋XML 无时钟）两跑同字节；
    独立回读（zipfile+xml.etree 不同解析路径）逐格对账；LibreOffice 真
    读验证（soffice.com → CSV，本机 26.x，裁决#5）。

分段（每 profile 同集 12 检）：C01-C05＝F83；C06-C12＝F85。

双 profile：
  desktop＝产品桥子进程全链（legal_entry CLI→column_preset.*/export.*→
  tabular.*→harness public_entry 子进程＋extraction 同进程→SQLite
  MatterStore）——每次调用即新进程＝跨进程状态在库验证；
  selfhost＝PgMatterStore 直连容器 lh-pg-e08（provider registry 面）＋
  产品面同进程调用（三面 seam 指向 PG 绑定方法）。

用法（juscite worktree w3-u15 根 cwd；--profile 缺省＝双 profile）：
  python -X utf8 tools/recon/PENDING_OWNER_f83_f85_columns_export_recon.py \
      [--profile desktop --profile selfhost]

exit 0＝全部 profile 全部检过（RECON_OK）；证据 JSON 写 evidence/F83/
<profile>/ 与 evidence/F85/<profile>/。全合成材料；只读消费 codices E22
冻结面与 harness worktree；不发网络，不写正式目录，不触碰 oc28 与
%APPDATA%。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest.mock
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
MATTER = "m-f83f85-recon"

DEFAULT_FORMAL_ROOT = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices"
)
# E22 冻结面 v1.1（W2a-U14 钉定值）：只读消费，零写入。
DEFAULT_CODICES_REPO = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14"
)
# F82 链头（W2b-U31＝U05 列合同/支持账＋U31 复核面 superset，本单消费面
# 全在 U05 五方法内）。
DEFAULT_HARNESS_ROOT = (
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u31"
)
LCCC_V11_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a"
)
SOFFICE = Path(r"C:\Program Files\LibreOffice\program\soffice.com")

PIPL_TITLE = "中华人民共和国个人信息保护法"
PIPL_ART1_QUOTE = (
    "为了保护个人信息权益，规范个人信息处理活动，促进个人信息合理利用，"
    "根据宪法，制定本法。"
)
ABOLISHED_TITLE = "中华人民共和国合同法"       # 已废止（04）
FABRICATED_TITLE = "中华人民共和国月球资源开发管辖法"

DOC = "synth_f83f85_doc"

PAGE_3 = (
    "第三条 合同价款。本合同总价为人民币123,456.78元，含税。"
    "依据《%s》第一条：“%s”" % (PIPL_TITLE, PIPL_ART1_QUOTE)
)
PAGE_4 = (
    "第五条 违约责任。原依据《%s》第五条处理。" % ABOLISHED_TITLE
)

SCOPE = {"kind": "matter", "matterId": MATTER}

# 填充投影夹具（F83：缺值/多值/未知不伪填；全合成）。
VALUES_FIXTURE = {
    "contract_amount": [],                          # 缺值
    "risk_level": ["高", "低"],                      # 多值（互异）
    "penalty_standard": ["以实物为准"],               # 未知（不可 Decimal）
    "payment_term": ["三十日内一次性支付"],            # 填充
    "parties": ["甲方公司", "甲方公司"],               # 同文多提＝去重非多值
}
WANT_FILL = {
    "contract_amount": "value_missing",
    "risk_level": "value_ambiguous",
    "penalty_standard": "value_unknown",
    "payment_term": "filled",
    "parties": "filled",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        feature = "F85" if check_id.startswith(("C06", "C07", "C08", "C09",
                                                "C10", "C11", "C12")) \
            else "F83"
        self.items.append(
            {"id": check_id, "feature": feature,
             "status": "PASS" if ok else "FAIL", "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    def for_feature(self, feature: str) -> list:
        return [item for item in self.items if item["feature"] == feature]

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")

    def all_passed(self, feature: str | None = None) -> bool:
        items = self.items if feature is None else self.for_feature(feature)
        return all(item["status"] == "PASS" for item in items)


def write_corpus(root: Path) -> dict:
    doc_dir = root / DOC
    doc_dir.mkdir(parents=True, exist_ok=True)
    shas = {}
    for page, text in {3: PAGE_3, 4: PAGE_4}.items():
        (doc_dir / ("page-%d.txt" % page)).write_text(text, encoding="utf-8")
        shas[page] = sha256_text(text)
    return shas


_KEY_SEQ = [0]


def command_key(request_id: str) -> dict:
    # harness CommandKey 语义：同 key 同内容幂等重放、同 key 异内容冲突。
    # 全局自增序号保证每个请求 key 唯一（绝不撞冲突）。
    _KEY_SEQ[0] += 1
    return {"requestId": "f83f85-%s-%d" % (request_id, _KEY_SEQ[0]),
            "targetId": None, "expectedRevision": None, "inputRefs": []}


def outcome_of(call, method: str, args: dict, config_override=None) -> dict:
    """call 归一：exit 0 → {"exit":0,"result":…}；否则带 payload/code。"""
    outcome = call(method, args, config_override) \
        if config_override is not None else call(method, args)
    if isinstance(outcome, dict) and "exit" in outcome:
        return outcome
    return {"exit": 0, "result": outcome}


# ---------------------------------------------------------------------- #
# 双 profile 共用闭环
# ---------------------------------------------------------------------- #


def common_flow(checks: Checks, call, corpus: Path, shas: dict) -> dict:
    # ============ F83：列预设（字段/format 严格分离＋每列金标） ============

    # --- C01 冻结预设只读：12 字段≥10；两层分离；每列金标 ---------------
    preset = outcome_of(call, "column_preset.read", {})
    fields = preset.get("result", preset).get("fields", [])
    formats = preset.get("result", preset).get("formats", [])
    ids = {field["id"] for field in fields}
    in_process_closure_checks = _preset_structure_in_process()
    checks.add(
        "C01_preset_read_separated_gilded",
        preset.get("result", preset).get("fieldCount") == 12
        and len(fields) >= 10
        and all(set(field) == {"id", "name", "gold"} for field in fields)
        and all(set(item) == {"id", "format"} for item in formats)
        and ids == {item["id"] for item in formats}
        and all(field["gold"]["kind"] in ("text", "enum", "number", "date",
                                          "boolean", "none")
                for field in fields)
        and in_process_closure_checks,
        "冻结预设 12 字段（≥10）：字段层 {id,name,gold} 无 format 键、"
        "format 层 {id,format} 无 gold 越层；两层 id 恰等；每列必有金标"
        "（kind 闭集＝tabular 面同集，进程内复验 %s）" % "OK")

    # --- C02 严格分离负向：字段携 format/format 越层/id 失配 具名拒 ------
    checks.add(
        "C02_preset_separation_negatives_named",
        bool(_preset_negative_results)
        and all(_preset_negative_results)
        and len(_preset_negative_results) == 3,
        "字段携 format=preset_field_carries_format；format 表携 gold="
        "column_preset_format_shape_invalid；两层 id 失配="
        "preset_format_id_mismatch（进程内具名拒实跑）")

    # --- C03 申报：列权威唯一在 harness（F82 列合同） -------------------
    created = call("harness.review_batch_create", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("b1"),
        "batch": {"id": "brt-f83", "title": "F83 合同列预设（合成）",
                  "columns": [{"id": field["id"], "name": field["name"]}
                              for field in fields],
                  "rows": [{"id": "row-1",
                            "cells": {field["id"]: None
                                      for field in fields}}]}})
    applied = outcome_of(call, "column_preset.apply", {
        "scope": SCOPE, "review_batch_id": "brt-f83",
        "actor_id": "lawyer-1", "key": command_key("a1")})
    columns_read = call("harness.review_columns_read",
                        {"scope": SCOPE, "batch_id": "brt-f83"})
    preset_formats = {item["id"]: item["format"] for item in formats}
    preset_golds = {field["id"]: field["gold"] for field in fields}
    harness_columns = columns_read.get("columns", [])
    replay = outcome_of(call, "column_preset.apply", {
        "scope": SCOPE, "review_batch_id": "brt-f83",
        "actor_id": "lawyer-2", "key": command_key("a2")})
    # 负向：列集合不冻结的批申报＝harness columns_not_frozen 具名原样上浮
    call("harness.review_batch_create", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("b2"),
        "batch": {"id": "brt-f83n", "title": "两列批（非冻结集）",
                  "columns": [{"id": "parties", "name": "合同主体"}],
                  "rows": [{"id": "row-1",
                            "cells": {"parties": None}}]}})
    unfrozen = outcome_of(call, "column_preset.apply", {
        "scope": SCOPE, "review_batch_id": "brt-f83n",
        "actor_id": "lawyer-1", "key": command_key("a3")})
    unfrozen_payload = unfrozen.get("payload", {})
    checks.add(
        "C03_preset_apply_single_column_authority",
        created.get("status") == "active"
        and applied.get("result", applied).get("columnCount") == 12
        and len(harness_columns) == 12
        and all(column.get("format") == preset_formats[column["id"]]
                and column.get("gold") == preset_golds[column["id"]]
                for column in harness_columns)
        and replay.get("result", replay).get("harness", {}).get(
            "replayed") is True
        and unfrozen.get("exit") in (1, 3)
        and "columns_not_frozen" in str(unfrozen_payload.get("code", "")),
        "申报 12 列入 harness 列合同；回读逐列 format（来自 format 层）＋"
        "gold（来自字段层）＝申报边界 join；幂等重放 replayed=True；非冻"
        "结集批 columns_not_frozen 具名原样上浮（不建第二列权威）")

    # --- C04 填充投影：缺值/多值/未知不伪填（具名 fill） ----------------
    projected = outcome_of(call, "column_preset.values",
                           {"values": VALUES_FIXTURE})
    cells = {cell["columnId"]: cell
             for cell in projected.get("result", projected).get("cells", [])}
    ghost = outcome_of(call, "column_preset.values",
                       {"values": {"ghost": ["x"]}})
    checks.add(
        "C04_values_fill_projection_named",
        projected.get("result", projected).get("filledCount") == 2
        and all(cells[column_id]["fill"] == want
                and cells[column_id]["value"] is None
                for column_id, want in WANT_FILL.items()
                if want != "filled")
        and cells["parties"]["fill"] == "filled"
        and cells["parties"]["value"] == "甲方公司"
        and cells["parties"]["distinctCount"] == 1
        and cells["penalty_standard"]["reason"] == "number_unparseable"
        and str(ghost.get("payload", {}).get("code", "")).startswith(
            "preset_column_unknown:ghost"),
        "缺值 value_missing/多值 value_ambiguous/未知 value_unknown 恒 "
        "value=None＋具名；同文多提及去重不升格；number 金标列不可 "
        "Decimal 解析＝未知；未知列 preset_column_unknown 具名")

    # --- C05 不伪填落批：缺/多/未知格如实缺席 ---------------------------
    row_values = {column_id: (cells[column_id]["value"]
                              if column_id in cells else None)
                  for column_id in ids}
    claimed = call("harness.review_batch_claim", {
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("c1"),
        "batch_id": "brt-f83", "row_id": "row-1", "lease_ttl_seconds": 600})
    call("harness.review_batch_submit", {
        "actor_id": "worker-1", "scope": SCOPE, "key": command_key("s1"),
        "batch_id": "brt-f83", "row_id": "row-1",
        "lease_token": claimed["lease"]["token"],
        "cells": [{"cellId": column_id, "value": value, "generation": 0}
                  for column_id, value in sorted(row_values.items())]})
    table = outcome_of(call, "tabular.read",
                       {"review_batch_id": "brt-f83", "scope": SCOPE})
    rows = table.get("result", table).get("rows", [])
    triple = {cell["columnId"]: cell
              for cell in rows[0]["cells"]} if rows else {}
    fabricated = {"N/A", "待定", "（空）", "-", "无", "unknown", "null"}
    checks.add(
        "C05_unfilled_never_pseudo_filled_in_batch",
        rows and triple["contract_amount"]["value"] is None
        and triple["risk_level"]["value"] is None
        and triple["risk_level"]["goldMatchReason"] == "value_absent"
        and triple["penalty_standard"]["value"] is None
        and triple["payment_term"]["value"] == "三十日内一次性支付"
        and all((triple[column_id]["value"] not in fabricated)
                for column_id in triple),
        "投影落批（claim→submit）：缺/多/未知格值如实 None（纯类型金标投"
        "影 type_only_gold；带 expect 的 enum 列缺值投影 value_absent）；"
        "全表无编造占位值；payment_term 如实落值")

    # ============ F85：结果导出 Excel（标记脱壳不丢来源） =================

    # --- 导出批＋闸戳（真 codices E22 冻结面：现行 VERIFIED＋废止 REJECTED）
    candidates = [
        {"text": "依据《%s》第一条：“%s”" % (PIPL_TITLE, PIPL_ART1_QUOTE),
         "provenance": {"source": "material_extraction", "doc": DOC,
                        "page": 3, "textSha256": shas[3]}},
        {"text": "依据《%s》第五条处理。" % ABOLISHED_TITLE,
         "provenance": {"source": "material_extraction", "doc": DOC,
                        "page": 4, "textSha256": shas[4]}},
    ]
    call("extraction.register", {"batch_id": "f85a", "candidates": candidates})
    gate = call("extraction.gate", {"batch_id": "f85a", "as_of": RUN_DATE})
    gate_view = call("extraction.candidates", {"batch_id": "f85a"})
    citations_by_candidate = {}
    for view in gate_view.get("candidates", []):
        history = view.get("gate_history") or [{}]
        citations_by_candidate[view["candidate_id"]] = [
            record.get("citation_text")
            for record in (history[-1].get("citations") or [])]
    pipl_cite = citations_by_candidate.get("cand_0001", [None])[0]
    contract_cite = citations_by_candidate.get("cand_0002", [None])[0]

    export_columns = ["contract_amount", "payment_term", "legal_basis",
                      "risk_level"]
    call("harness.review_batch_create", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("b3"),
        "batch": {"id": "brt-f85", "title": "F85 导出批（合成）",
                  "columns": [{"id": column_id,
                               "name": dict(
                                   ((field["id"], field["name"])
                                    for field in fields))[column_id]}
                              for column_id in export_columns],
                  "rows": [{"id": "row-1",
                            "cells": {column_id: None
                                      for column_id in export_columns}},
                           {"id": "row-2",
                            "cells": {column_id: None
                                      for column_id in export_columns}},
                           {"id": "row-3",
                            "cells": {column_id: None
                                      for column_id in export_columns}}]}})
    # 导出批列合同＝冻结预设同源子集（字段/format/gold 来自同一预设，
    # 列权威仍在 harness——subset 申报走 review_columns_define 同面）。
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    import column_presets as _cp
    preset_columns = {column["id"]: column
                      for column in _cp._joined_columns()}
    call("harness.review_columns_define", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("dc3"),
        "batch_id": "brt-f85",
        "columns": [preset_columns[column_id]
                    for column_id in export_columns]})
    row_values_1 = {
        "contract_amount":
            "总价为人民币123,456.78元⟦引:%s⟧" % pipl_cite,
        "payment_term": "三十日内一次性支付",
        "legal_basis": "违约责任依据⟦引:%s⟧处理" % contract_cite,
        "risk_level": None,                      # 缺值
    }
    row_values_2 = {
        "contract_amount": "123,456.78 元",       # 无标记无戳
        "payment_term": None,                     # 缺值
        "legal_basis": "管辖依据⟦引:《%s》第一条⟧" % FABRICATED_TITLE,
        "risk_level": "中",
    }
    for index, (row_id, values) in enumerate(
            (("row-1", row_values_1), ("row-2", row_values_2)), start=1):
        claim = call("harness.review_batch_claim", {
            "actor_id": "worker-1", "scope": SCOPE,
            "key": command_key("c%d" % index), "batch_id": "brt-f85",
            "row_id": row_id, "lease_ttl_seconds": 600})
        call("harness.review_batch_submit", {
            "actor_id": "worker-1", "scope": SCOPE,
            "key": command_key("s%d" % index), "batch_id": "brt-f85",
            "row_id": row_id, "lease_token": claim["lease"]["token"],
            "cells": [{"cellId": column_id, "value": value, "generation": 0}
                      for column_id, value in sorted(values.items())]})
    # 支持戳：row-1 两格（VERIFIED＋REJECTED）；row-2 无戳（UNVERIFIED 形态）
    for candidate_id, cell_id in (("cand_0001", "contract_amount"),
                                  ("cand_0002", "legal_basis")):
        call("tabular.support_stamp", {
            "extraction_batch_id": "f85a", "candidate_id": candidate_id,
            "review_batch_id": "brt-f85", "row_id": "row-1",
            "cell_id": cell_id, "actor_id": "worker-1", "scope": SCOPE,
            "key": command_key("st-" + candidate_id)})

    # --- C06 投影：真实格值（剥标记）与可审引用列一致 --------------------
    export = outcome_of(call, "export.xlsx",
                        {"scope": SCOPE, "review_batch_id": "brt-f85"})
    export_result = export.get("result", export)
    projection = export_result.get("projection", {})
    proj_rows = {row["rowId"]: {cell["columnId"]: cell
                                for cell in row["cells"]}
                 for row in projection.get("rows", [])}
    amount_cell = proj_rows.get("row-1", {}).get("contract_amount", {})
    basis_cell = proj_rows.get("row-1", {}).get("legal_basis", {})
    ghost_cell = proj_rows.get("row-2", {}).get("legal_basis", {})
    checks.add(
        "C06_projection_real_values_consistent",
        amount_cell.get("realValue") == "总价为人民币123,456.78元"
        and amount_cell.get("markers") == [pipl_cite]
        and len(amount_cell.get("citations", [])) == 1
        and amount_cell["citations"][0]["gateStatus"] == "CITATION_VERIFIED"
        and amount_cell["citations"][0]["status"] == "现行"
        and amount_cell["citations"][0]["origin"] == "support_stamp"
        and amount_cell["citations"][0]["textSha256"] == shas[3]
        and basis_cell.get("realValue") == "违约责任依据处理"
        and basis_cell["citations"][0]["gateStatus"] == "REJECTED"
        and basis_cell["citations"][0]["status"] == "已废止"
        and ghost_cell.get("citations", [{}])[0].get("gateStatus")
        == "UNVERIFIED"
        and ghost_cell["citations"][0]["origin"]
        == "marker_without_support_stamp"
        and ghost_cell["citations"][0]["textSha256"] is None
        and proj_rows["row-1"]["risk_level"]["fillState"] == "value_absent"
        and proj_rows["row-1"]["risk_level"]["citations"] == [],
        "真实格值＝剥除标记跨度逐字保留；已核引用带 F87 三态＋F70 状态＋"
        "doc/page/sha256（钉新材料页字节）；REJECTED 戳引用如实呈现不伪已"
        "核；未入戳被剥标记 UNVERIFIED 具名＋出处具名缺席；缺值格零引用")

    # --- C07 覆盖完备：每条被剥标记都落在可审引用列（脱壳不丢来源） -------
    coverage_ok = True
    for row_cells in proj_rows.values():
        for cell in row_cells.values():
            texts = {entry["citationText"] for entry in cell["citations"]}
            if not set(cell["markers"]) <= texts:
                coverage_ok = False
            origins = {entry["origin"] for entry in cell["citations"]}
            if not origins <= {"support_stamp",
                               "marker_without_support_stamp"}:
                coverage_ok = False
    checks.add(
        "C07_marker_coverage_citation_columns",
        coverage_ok and export_result.get("cellCount") == 12,
        "逐格断言（4 列×3 行＝12 格；row-3 留 pending 使批保持 open——"
        "人改负向夹具需过 batch_not_open 门，F82 recon row-5 同先例）：每"
        "条被剥标记的引文文本都出现在该格引用列（markers⊆引用列）；引用"
        "条目来源闭集 {support_stamp, marker_without_support_stamp}——脱"
        "壳不丢来源，无第三来源")

    # --- C08 XLSX 确定性：两跑同字节（真链两次调用）＋生成器内两建同字节 --
    export_b = outcome_of(call, "export.xlsx",
                          {"scope": SCOPE, "review_batch_id": "brt-f85"})
    export_b_result = export_b.get("result", export_b)
    bytes_a = base64.b64decode(export_result["xlsx_b64"])
    bytes_b = base64.b64decode(export_b_result["xlsx_b64"])
    with_zip = None
    if _inprocess_export is not None:
        with_zip = hashlib.sha256(
            _inprocess_export(projection)).hexdigest() \
            == hashlib.sha256(bytes_a).hexdigest()
    checks.add(
        "C08_xlsx_two_runs_same_bytes",
        export_result["sha256"] == export_b_result["sha256"]
        and bytes_a == bytes_b
        and bytes_a[:2] == b"PK"
        and (with_zip is not False),
        "export.xlsx 真链两跑 sha256 相等＋字节相等（%s…）；同投影生成器"
        "内重建同字节=%s；zip 魔数 PK" % (export_result["sha256"][:12],
                                          with_zip))

    # --- C09 独立回读：zipfile+xml.etree 逐格对账（与生成不同解析路径） --
    grid = _xlsx_grid(bytes_a)
    header, data_rows = grid[0], grid[1:]
    columns = projection["columns"]
    letters = [_column_letter(2 + index * 3) for index in range(len(columns))]
    citation_letters = [_column_letter(3 + index * 3)
                        for index in range(len(columns))]
    state_letters = [_column_letter(4 + index * 3)
                     for index in range(len(columns))]
    readback_ok = header["A"] == "行ID"
    for row_index, row_id in enumerate(("row-1", "row-2")):
        data = data_rows[row_index]
        for col_index, column_id in enumerate(
                (column["id"] for column in columns)):
            cell = proj_rows[row_id][column_id]
            readback_ok &= data.get(letters[col_index], "") \
                == cell["realValue"]
            readback_ok &= data.get(citation_letters[col_index], "") \
                == cell["citationCell"]
            readback_ok &= data.get(state_letters[col_index], "") \
                == cell["stateCell"]
            # 缺值格＝结构位真空（不写单元格元素），绝不伪填
            if cell["fillState"] == "value_absent":
                readback_ok &= letters[col_index] not in data
    checks.add(
        "C09_xlsx_independent_readback",
        readback_ok and header["B"] == "合同金额（元）"
        and header["C"] == "合同金额（元）·引用"
        and header["D"] == "合同金额（元）·状态",
        "独立解析（zipfile+ElementTree）逐格对账：值列/引用列/状态列与投"
        "影全等；缺值格＝真空不写单元格（结构位 E/K 等缺席）；表头列名×"
        "三联")

    # --- C10 LibreOffice 真读验证（soffice.com → CSV；裁决#5）------------
    lo_status, lo_detail = _libreoffice_readback(bytes_a, proj_rows)
    checks.add("C10_libreoffice_readback", lo_status == "PASS"
               or lo_status == "SKIP_NOT_INSTALLED",
               lo_detail + "（status=%s）" % lo_status)

    # --- C11 fail-closed 蓄电池 ------------------------------------------
    residue_row = _submit_extra_cell(checks, call, "brt-f85", "row-2",
                                     "payment_term",
                                     "值⟦残壳未闭合")

    residue = outcome_of(call, "export.xlsx",
                         {"scope": SCOPE, "review_batch_id": "brt-f85"})
    _restore_cell(call, "brt-f85", "row-2", "payment_term")
    empty_cite_row = _submit_extra_cell(checks, call, "brt-f85", "row-2",
                                        "payment_term", "值⟦引: ⟧尾")
    empty_cite = outcome_of(call, "export.xlsx",
                            {"scope": SCOPE, "review_batch_id": "brt-f85"})
    _restore_cell(call, "brt-f85", "row-2", "payment_term")
    float_row = _submit_extra_cell(checks, call, "brt-f85", "row-2",
                                   "payment_term", 123456.78)
    float_outcome = outcome_of(call, "export.xlsx",
                               {"scope": SCOPE,
                                "review_batch_id": "brt-f85"})
    _restore_cell(call, "brt-f85", "row-2", "payment_term")
    unknown = outcome_of(call, "export.verify", {"scope": SCOPE})
    ghost_batch = outcome_of(call, "export.xlsx",
                             {"scope": SCOPE, "review_batch_id": "ghost"})
    checks.add(
        "C11_fail_closed_battery",
        residue.get("exit") == 3 and str(
            residue.get("payload", {}).get("code", "")).startswith(
            "export_marker_residue")
        and empty_cite.get("exit") == 3 and str(
            empty_cite.get("payload", {}).get("code", "")).startswith(
            "export_marker_citation_text_required")
        and float_outcome.get("exit") == 3 and str(
            float_outcome.get("payload", {}).get("code", "")).startswith(
            "export_float_value_refused")
        and str(unknown.get("payload", {}).get("code", "")).startswith(
            "method_not_connected:export.verify")
        and str(ghost_batch.get("payload", {}).get("code", "")).startswith(
            "review_batch_not_found:ghost"),
        "标记壳残留 export_marker_residue／空引文标记 export_marker_citation"
        "_text_required／float 值 export_float_value_refused（金额纪律）／"
        "未知方法 method_not_connected／未知批次 harness typed 码原样上浮"
        "——全 exit 3 具名，绝不静默出门")

    # --- C12 投影语义确定性（两跑投影逐键相等） ---------------------------
    checks.add(
        "C12_projection_semantic_determinism",
        json.dumps(export_result["projection"], sort_keys=True,
                   ensure_ascii=False)
        == json.dumps(export_b_result["projection"], sort_keys=True,
                      ensure_ascii=False),
        "export 投影两跑逐键相等（同输入同投影＝XLSX 同字节的投影侧事实）")

    return {
        "gate_by_candidate": {key: value for key, value in
                              citations_by_candidate.items()},
        "export_sha256": export_result.get("sha256"),
        "cell_count": export_result.get("cellCount"),
    }


# ---------------------------------------------------------------------- #
# 进程内结构复验/负向（F83 C02；与 profile 无关的纯函数级检查）
# ---------------------------------------------------------------------- #

_preset_negative_results = None
_inprocess_export = None


def _preset_structure_in_process() -> bool:
    global _inprocess_export
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    import column_presets
    import excel_export
    import tabular_review

    kinds_ok = column_presets.GOLD_KINDS == tabular_review._GOLD_KINDS
    columns = column_presets._joined_columns()
    join_ok = len(columns) == 12 and all(
        set(column) == {"id", "name", "format", "version", "gold"}
        for column in columns)
    _inprocess_export = excel_export.build_xlsx
    return kinds_ok and join_ok


def _preset_negative_run() -> tuple:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    import column_presets
    from bridge_errors import NotConnected
    results = []
    # ① 字段携 format
    try:
        column_presets._validate_field(
            {"id": "x", "name": "越层列", "format": "text",
             "gold": {"kind": "text"}}, 0)
        results.append(None)
    except NotConnected as exc:
        results.append("preset_field_carries_format" in str(exc))
    # ② format 表携 gold（越层）
    try:
        column_presets._validate_format(
            {"id": "x", "format": "text", "gold": {"kind": "text"}}, 0)
        results.append(None)
    except NotConnected as exc:
        results.append("column_preset_format_shape_invalid" in str(exc))
    # ③ 两层 id 失配
    import unittest.mock as mock
    tampered = tuple(dict(item) for item in column_presets.FORMATS[:-1])
    with mock.patch.object(column_presets, "FORMATS", tampered):
        try:
            column_presets._joined_columns()
            results.append(None)
        except NotConnected as exc:
            results.append("preset_format_id_mismatch" in str(exc))
    return tuple(results)


def _xlsx_grid(payload: bytes) -> list:
    """独立回读（zipfile＋ElementTree，与生成器不同解析路径）→ 行×列网格。"""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    grid = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    for row in root.iter(ns + "row"):
        cells = {}
        for cell in row.iter(ns + "c"):
            ref = cell.attrib["r"]
            letters = "".join(ch for ch in ref if ch.isalpha())
            cells[letters] = "".join(
                t.text or "" for t in cell.iter(ns + "t"))
        grid.append(cells)
    return grid


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _current_generation(call, batch_id: str, row_id: str,
                        cell_id: str) -> int:
    """格当前世代（human_edit 前实读——每次人改推进世代，固定值必撞
    stale_generation）。"""
    row_view = call("harness.review_batch_read",
                    {"scope": SCOPE, "batch_id": batch_id,
                     "row_id": row_id})
    cells = (row_view.get("row") or {}).get("cells") or {}
    return int((cells.get(cell_id) or {}).get("generation", 0))


def _submit_extra_cell(checks: Checks, call, batch_id: str, row_id: str,
                       cell_id: str, value) -> bool:
    """负向夹具注入：human_edit 通道把格改成恶意/越界值（实读当前世代），
    导出面必须在出口拦截。"""
    call("harness.review_batch_human_edit", {
        "actor_id": "lawyer-1", "scope": SCOPE,
        "key": command_key("neg-%s-%s" % (row_id, cell_id)),
        "batch_id": batch_id, "row_id": row_id,
        "cells": [{"cellId": cell_id, "value": value,
                   "generation": _current_generation(call, batch_id,
                                                     row_id, cell_id)}]})
    return True


def _restore_cell(call, batch_id: str, row_id: str, cell_id: str) -> None:
    call("harness.review_batch_human_edit", {
        "actor_id": "lawyer-1", "scope": SCOPE,
        "key": command_key("res-%s-%s" % (row_id, cell_id)),
        "batch_id": batch_id, "row_id": row_id,
        "cells": [{"cellId": cell_id, "value": None,
                   "generation": _current_generation(call, batch_id,
                                                     row_id, cell_id)}]})


def _libreoffice_readback(payload: bytes, proj_rows: dict) -> tuple:
    """LibreOffice 真读（soffice.com → CSV，独立第三方解析器）：关键格值
    在 CSV 中逐字在。未安装＝SKIP_NOT_INSTALLED 如实具名（裁决#5 已装，
    常态 PASS）。"""
    if not SOFFICE.is_file():
        return "SKIP_NOT_INSTALLED", "LibreOffice 不在 %s" % SOFFICE
    with tempfile.TemporaryDirectory(prefix="f85-lo-") as tmp:
        tmp_path = Path(tmp)
        xlsx_path = tmp_path / "f85-export.xlsx"
        xlsx_path.write_bytes(payload)
        profile = tmp_path / "lo-profile"
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        # UserInstallation 隔离于临时目录（U17 先例：绝不写 %APPDATA%）。
        proc = subprocess.run(
            [str(SOFFICE), "-env:UserInstallation=file:///%s"
             % str(profile).replace("\\", "/"),
             "--headless", "--convert-to", "csv", "--outdir",
             str(out_dir), str(xlsx_path)],
            capture_output=True, timeout=300)
        csv_path = out_dir / "f85-export.csv"
        if proc.returncode != 0 or not csv_path.is_file():
            return "FAIL", "LibreOffice 转换失败 rc=%s" % proc.returncode
        raw = csv_path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        expected = [
            "总价为人民币123,456.78元",
            "〔CITATION_VERIFIED｜现行｜",
            "〔REJECTED｜已废止｜",
            "〔UNVERIFIED｜无支持戳〕",
            "NO_STAMP|value_absent",
        ]
        missing = [fragment for fragment in expected
                   if fragment not in text]
        return ("PASS", "LibreOffice 真读 CSV 关键格值逐字在（值列/引用列"
                "三态/缺值具名）" if not missing else
                "LibreOffice CSV 缺关键格值：%s" % missing)


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
        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f83f85-desktop-")
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
        MatterStore(state_root).create_matter(
            MATTER, "cas://profile-f83f85-recon")

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
              "(legal_entry CLI→column_preset/export/tabular→harness "
              "public_entry)", flush=True)
        return common_flow(self.checks, call, corpus, shas)

    # -- selfhost: PgMatterStore direct + in-process product faces --------
    def run_selfhost(self, dsn: str, formal_root: str,
                     codices_repo: str) -> None:
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools"),
                     str(self.harness_root), str(self.harness_root / "tests"),
                     str(REPO_ROOT / "implementation/python")):
            if path not in sys.path:
                sys.path.insert(0, path)
        import uuid as _uuid

        from legal_harness.business.provider_registry import (
            resolve_provider_method,
        )
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.pg_store import PgMatterStore

        temporary = tempfile.TemporaryDirectory(
            prefix="juscite-f83f85-selfhost-")
        self.add_cleanup(temporary.cleanup)
        base = Path(temporary.name)
        store = PgMatterStore(
            base / "state", dsn=dsn,
            schema="f83f85_" + _uuid.uuid4().hex[:12])
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
        store.create_matter(MATTER, "cas://profile-f83f85-recon-pg")
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
        import column_presets
        import excel_export
        import extraction_gate
        import tabular_review
        from bridge_errors import NotConnected as NotConnected_

        def product_seam(method, args, cfg):
            if method.startswith("harness."):
                if method not in bound:
                    raise NotConnected_("method_not_connected:" + method)
                return bound[method](**args)
            if method == "tabular.read":
                return tabular_review.tabular_read(args, cfg)
            raise NotConnected_("selfhost_seam_unknown:" + method)

        patchers = [
            unittest.mock.patch.object(tabular_review, "_harness_call",
                                       product_seam),
            unittest.mock.patch.object(column_presets, "_harness_call",
                                       product_seam),
            unittest.mock.patch.object(excel_export, "_harness_call",
                                       product_seam),
        ]
        for patcher in patchers:
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
            # 产品面分支：冻结组外＝桥同形 method_not_connected（desktop
            # 分派语义）；NotConnected＝exit 3 具名；seam 内 harness
            # UnitsError＝桥同形 exit 1 HARNESS_FAIL（desktop CLI 同码形）。
            import legal_entry as _le
            frozen = [(column_presets.COLUMN_PRESET_METHODS,
                       column_presets.column_preset_call),
                      (excel_export.EXCEL_EXPORT_METHODS,
                       excel_export.export_call),
                      (_le.TABULAR_METHODS,
                       tabular_review.tabular_call)]
            for frozen_set, dispatch in frozen:
                if method in frozen_set:
                    try:
                        return dispatch(method, args, merged)
                    except NotConnected_ as exc:
                        return {"exit": 3, "payload": {
                            "status": "NOT_CONNECTED", "code": str(exc)}}
                    except Exception as exc:
                        return {"exit": 1, "code": str(exc), "payload": {
                            "status": "HARNESS_FAIL", "code": str(exc)}}
            if any(method.startswith(frozen_item.split(".")[0] + ".")
                   for group in frozen for frozen_item in group[0]):
                return {"exit": 3, "payload": {"status": "NOT_CONNECTED",
                                                "code": "method_not_connected:"
                                                        + method}}
            raise AssertionError("selfhost call unknown: " + method)

        print("[profile selfhost] PgMatterStore direct (provider registry "
              "face) + in-process product faces", flush=True)
        try:
            return common_flow(self.checks, call, corpus, shas)
        finally:
            store.destroy()

    # -- tiny cleanup registry --------------------------------------------
    def add_cleanup(self, fn) -> None:
        if not hasattr(self, "_cleanups"):
            self._cleanups: list = []
        self._cleanups.append(fn)

    def cleanup(self) -> None:
        for fn in reversed(getattr(self, "_cleanups", [])):
            try:
                fn()
            except Exception:
                pass


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用（legal_entry CLI）；返回 {exit, payload, code,
    result}。"""
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


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
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
    args = parser.parse_args()
    profiles = args.profiles or ["desktop", "selfhost"]

    global _preset_negative_results
    _preset_negative_results = _preset_negative_run()

    lccc_path = os.path.join(args.codices_repo, "lccc_consumer.py")
    if not os.path.isfile(lccc_path) \
            or sha256_file(lccc_path) != LCCC_V11_SHA256:
        print("FATAL: 冻结面 v1.1 lccc_consumer.py 不在 %s 或 sha256 漂移"
              % args.codices_repo)
        return 2
    if not os.path.isfile(os.path.join(
            args.harness_root,
            "tools/workflow-tools/harness/public_entry.py")):
        print("FATAL: harness 公开入口不在 %s（w2b-u31 worktree）"
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
            shared_meta = {
                "run_date": RUN_DATE,
                "profile": profile,
                "command": "python -X utf8 " + " ".join(sys.argv[1:]),
                "cwd": str(REPO_ROOT),
                "subject_commit": commit,
                "harness_commit": harness_commit,
                "harness_root": str(args.harness_root),
                "frozen_face": {
                    "lccc_consumer.py(v1.1)": LCCC_V11_SHA256,
                    "legal_documents.csv": sha256_file(os.path.join(
                        args.formal_root, "legal_documents.csv")),
                },
                "preset_structure_negatives": list(
                    _preset_negative_results),
            }
            for feature, check_ids, filename in (
                    ("F83", ("C01", "C02", "C03", "C04", "C05"),
                     "f83-columns-preset-recon-%s.json"
                     % time.strftime("%Y%m%dT%H%M%S%z")),
                    ("F85", ("C06", "C07", "C08", "C09", "C10", "C11",
                             "C12"),
                     "f85-excel-export-recon-%s.json"
                     % time.strftime("%Y%m%dT%H%M%S%z"))):
                items = [item for item in recon.checks.items
                         if item["id"].startswith(check_ids)]
                evidence = dict(shared_meta)
                evidence.update({
                    "feature": feature,
                    "checks": items,
                    "passed": sum(1 for item in items
                                  if item["status"] == "PASS"),
                    "total": len(items),
                    "overall": "PASS" if all(
                        item["status"] == "PASS" for item in items)
                        and items else "FAIL",
                })
                out_dir = REPO_ROOT / "evidence" / feature / profile
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / filename).write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=1),
                    encoding="utf-8")
            per_profile[profile] = {
                "passed": recon.checks.passed_count,
                "total": len(recon.checks.items),
                "overall": "PASS" if recon.checks.all_passed else "FAIL",
            }
            all_ok = all_ok and recon.checks.all_passed
            print("---")
            print("profile=%s: %d/%d checks (%s)" % (
                profile, recon.checks.passed_count,
                len(recon.checks.items), per_profile[profile]["overall"]))
    finally:
        recon.cleanup()
    print("RECON_%s（%s）" % ("OK" if all_ok else "FAIL",
                             "+".join(profiles)))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
