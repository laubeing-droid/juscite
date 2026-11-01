# -*- coding: utf-8 -*-
"""F85 结果导出 Excel 产品面（工单 W3-U15）。

06 F85（17 卡，owner=product；依赖 F82/F87）：结果导出 Excel（引文标记
脱壳）；acceptance 断言「Excel 真实格值与可审引用列一致；内部标记脱壳
不丢来源」。本模块是**投影＋确定性 XLSX 生成**，不是第二真源：

  - 真值唯一来源＝tabular.read（F82 列三元组投影，W2b-U05）×
    harness.review_support_read（格支持账：核验戳/出处，W2b-U05）——
    同源读取，本面不重算金标、不重判核验、不碰材料字节；
  - 内部标记脱壳：格值内嵌的引文内部标记（冻结语法 ⟦引:<引文文本>⟧，
    确定性正则解析，非模型）从交付值中剥除——剥除只删标记跨度本身，
    其余字节逐字保留；每条被剥标记的引文文本落进该格的**可审引用列**
    （脱壳不丢来源）。已剥值残留任何标记壳（⟦/⟧）＝具名拒不静默出门；
  - 可审引用列与真实格值一致：引用列条目只来自两处——该格支持戳内
    已核引用（逐条带 F87 闸三态＋F70 状态＋doc/page/sha256 出处）与
    未入戳的被剥标记（F87 三态＝UNVERIFIED 具名，出处具名缺席）——
    绝不把 UNVERIFIED 伪成已核，也绝不给标记编造出处；
  - 缺值不伪填：值为 None 的格在 XLSX 中就是空格（不写单元格），状态
    列具名 value_absent——绝不写「N/A」之类编造占位；
  - XLSX 确定性生成：纯标准库 zipfile+xml 最小 OOXML（inlineStr，全部
    字符串格——金额十进制串原样入格，不落浮点），zip 项时间戳钉定
    (1980,1,1,0,0,0)、项序固定、XML 无时钟——同输入两跑同字节。

金额纪律：格值是字符串原样投影（十进制金额串不经浮点）；本面不解释
值语义（goldMatch 唯一在 tabular.read）。

状态面：零自有持久化——XLSX 字节 base64 回传，落盘由调用方负责；原生
UI 触发面不在本单（公开面先行，同 F54/F45 先例）。
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import zipfile
from xml.sax.saxutils import escape

from bridge_errors import NotConnected

EXCEL_EXPORT_FACE_NOTE = (
    "excel-export(W3-U15): tabular.read(W2b-U05)"
    "+harness.review_support_read(W2b-U05)同源投影；引文标记脱壳不丢"
    "来源；XLSX 确定性生成")

# 方法组闭集（legal_entry 冻结注册；组外方法绝不落到本面）。
EXCEL_EXPORT_METHODS = frozenset({
    "export.xlsx",
})

_XLSX_ARGS_FIELDS = frozenset({"scope", "review_batch_id"})

# 内部引文标记（冻结语法）：⟦引:<引文文本>⟧。确定性正则；引文文本不得
# 为空、不得含闭合壳 ⟧（含之＝形状不合法具名拒）。
MARKER_OPEN = "⟦引:"
MARKER_CLOSE = "⟧"
MARKER_RE = re.compile(re.escape(MARKER_OPEN) + r"([^" + MARKER_CLOSE
                       + r"]{1,500}?)" + re.escape(MARKER_CLOSE))
# 脱壳后残留检查：任何标记壳残留（不完整标记/裸壳）都拒绝出门。
RESIDUE_RE = re.compile(r"⟦|⟧")

# F87 引用闸三态闭集（与 extraction_gate.GATE_STATUSES 同集＋UNVERIFIED
# 缺省形态；wiring 测试钉定相等，防漂移）。
GATE_UNVERIFIED = "UNVERIFIED"
GATE_THREE_STATES = frozenset({
    GATE_UNVERIFIED, "CITATION_VERIFIED", "REJECTED",
})

# 支持状态闭集（harness review_support_read 投影闭集，W2b-U05；本面只
# 投影不判定）。
SUPPORT_STATUS_CLOSED = frozenset({
    "SUPPORTED_CITATION_LEVEL", "UNSUPPORTED_REJECTED",
    "STALE_CELL_ADVANCED", "INVALIDATED", "NO_STAMP",
})

_FILL_ABSENT = "value_absent"

_SHEET_NAME = "审查结果"
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def _harness_call(method: str, args: dict, config: dict) -> dict:
    """公开面分派 seam（默认=legal_entry.call 同进程径；selfhost 侧由
    调用方替换本 seam——同 tabular_review/review_chat 先例）。"""
    import legal_entry
    return legal_entry.call(method, args, config)


def _require(args: dict, fields: frozenset, code: str) -> None:
    if not isinstance(args, dict) or set(args) != set(fields):
        raise NotConnected(code)


def _scope_of(args: dict) -> dict:
    scope = args.get("scope")
    if not isinstance(scope, dict) or scope.get("kind") != "matter" \
            or not isinstance(scope.get("matterId"), str) \
            or not scope.get("matterId"):
        raise NotConnected("export_scope_invalid")
    return scope


# ---------------------------------------------------------------------- #
# 内部标记脱壳（确定性：正则＋闭集检查；非模型）
# ---------------------------------------------------------------------- #


def strip_markers(value: str) -> tuple:
    """剥除格值内引文标记：返回 (真实格值, [引文文本…])。

    剥除只删标记跨度；其余字节逐字保留（ reconstruction：两段拼接还原
    原值——recon 逐格验证）。标记壳残留＝具名拒（内部标记绝不带出门）。
    """
    markers = []
    for match in MARKER_RE.finditer(value):
        text = match.group(1)
        if not text.strip():
            raise NotConnected("export_marker_citation_text_required")
        markers.append(text)
    stripped_parts = []
    last = 0
    for match in MARKER_RE.finditer(value):
        stripped_parts.append(value[last:match.start()])
        last = match.end()
    stripped_parts.append(value[last:])
    stripped = "".join(stripped_parts)
    if RESIDUE_RE.search(stripped):
        raise NotConnected("export_marker_residue:" + stripped[:50])
    return stripped, markers


def _cell_text(value) -> str:
    """格值字符串化闭集：str 原样／None 空串（空格＝缺值，不写单元格）
    ／int 十进制串；float 具名拒（金额纪律——浮点永不入格）；bool/其他
    类型具名拒（值语义不解释）。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        raise NotConnected("export_value_type_unsupported:bool")
    if isinstance(value, float):
        raise NotConnected("export_float_value_refused")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    raise NotConnected("export_value_type_unsupported:"
                       + type(value).__name__)


# ---------------------------------------------------------------------- #
# 投影：tabular.read × 支持账 → 行投影（值列＋可审引用列＋状态列）
# ---------------------------------------------------------------------- #


def _support_index(support_doc: dict) -> dict:
    """支持账 entries → {(rowId, cellId): entries}（键形 row:cell，同
    review_chat 先例）。"""
    index = {}
    for key, entries in (support_doc.get("entries") or {}).items():
        row_id, _, cell_id = key.rpartition(":")
        index[(row_id, cell_id)] = entries
    return index


def _latest_support_record(entries: list):
    """末条**支持**记录（失效条目不覆盖引用面——失效本身在支持状态投影
    里具名 INVALIDATED）；无支持记录＝None。"""
    for entry in reversed(entries or []):
        record = entry.get("record") or {}
        if record.get("entryKind") == "support":
            return record
    return None


def _citation_rows(stamped: dict, markers: list) -> list:
    """格的可审引用条目：支持戳引用逐条（F87 闸三态＋F70 状态＋出处）
    ＋未入戳被剥标记（UNVERIFIED 具名，出处具名缺席不编造）。"""
    provenance = (stamped or {}).get("provenance") or {}
    gate = (stamped or {}).get("gate") or {}
    stamped_status = gate.get("gateStatus")
    if stamped_status is not None and stamped_status not in GATE_THREE_STATES:
        raise NotConnected("export_gate_status_invalid:" + str(stamped_status))
    rows = []
    seen = set()
    for citation in (stamped or {}).get("citations", []):
        text = citation.get("citationText")
        seen.add(text)
        rows.append({
            "citationText": text,
            "gateStatus": stamped_status,
            "status": citation.get("status"),
            "doc": provenance.get("doc"),
            "page": provenance.get("page"),
            "textSha256": provenance.get("textSha256"),
            "origin": "support_stamp",
        })
    for text in markers:
        if text in seen:
            continue  # 已入戳引用：戳是唯一出处形态，不双列
        seen.add(text)
        rows.append({
            "citationText": text,
            "gateStatus": GATE_UNVERIFIED,
            "status": None,
            "doc": None,
            "page": None,
            "textSha256": None,
            "origin": "marker_without_support_stamp",
        })
    return rows


def _citation_cell_text(citation_rows: list) -> str:
    """引用列单元格文本（人类可读＋机器可对账：一条一行）。"""
    lines = []
    for row in citation_rows:
        if row["origin"] == "support_stamp":
            lines.append("%s〔%s｜%s｜%s#%s｜%s〕" % (
                row["citationText"], row["gateStatus"], row["status"],
                row["doc"], row["page"], row["textSha256"]))
        else:
            lines.append("%s〔%s｜无支持戳〕" % (
                row["citationText"], row["gateStatus"]))
    return "\n".join(lines)


def export_projection(args: dict, config: dict) -> dict:
    """同源投影：逐行逐格 {真实格值, 引用条目, 支持状态, 缺值形态}。"""
    _require(args, _XLSX_ARGS_FIELDS, "export_args_invalid")
    scope = _scope_of(args)
    batch_id = args.get("review_batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise NotConnected("export_batch_id_required")
    read = _harness_call("tabular.read",
                         {"review_batch_id": batch_id, "scope": scope},
                         config)
    support = _harness_call("harness.review_support_read",
                            {"scope": scope, "batch_id": batch_id}, config)
    support_index = _support_index(support)
    rows_out = []
    cell_count = 0
    for row in read.get("rows", []):
        cells_out = []
        for cell in row.get("cells", []):
            raw_value = cell.get("value")
            raw_text = _cell_text(raw_value)
            stripped, markers = strip_markers(raw_text) \
                if raw_text else ("", [])
            entries = support_index.get((row.get("rowId"),
                                         cell.get("columnId"))) or []
            stamped = _latest_support_record(entries)
            citations = _citation_rows(stamped, markers)
            support_status = cell.get("supportStatus", "NO_STAMP")
            if support_status not in SUPPORT_STATUS_CLOSED:
                raise NotConnected("export_support_status_invalid:"
                                   + str(support_status))
            value_absent = raw_value is None
            cells_out.append({
                "rowId": row.get("rowId"),
                "columnId": cell.get("columnId"),
                "columnName": cell.get("columnName"),
                "rawValue": raw_text,
                "realValue": stripped,
                "markers": markers,
                "citations": citations,
                "citationCell": _citation_cell_text(citations),
                "supportStatus": support_status,
                "fillState": _FILL_ABSENT if value_absent else "filled",
                "stateCell": (support_status + "|" + _FILL_ABSENT)
                             if value_absent else support_status,
            })
            cell_count += 1
        rows_out.append({"rowId": row.get("rowId"),
                         "rowState": row.get("rowState"),
                         "cells": cells_out})
    columns = [{"id": column.get("id"), "name": column.get("name")}
               for column in read.get("columns", [])]
    return {
        "reviewBatchId": batch_id,
        "batchStatus": read.get("batchStatus"),
        "columns": columns,
        "rows": rows_out,
        "cellCount": cell_count,
        "face": EXCEL_EXPORT_FACE_NOTE,
    }


# ---------------------------------------------------------------------- #
# 确定性 XLSX 生成（最小 OOXML；inlineStr；zip 时间戳钉定）
# ---------------------------------------------------------------------- #


def _column_letter(index: int) -> str:
    """1 基列号 → A/…/AA…（确定性）。"""
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _sheet_xml(projection: dict) -> str:
    """工作表 XML：表头（列名×3：值/引用/状态）＋数据行。缺值格不写
    单元格元素（空＝缺值，不伪填）。"""
    columns = projection["columns"]
    header_cells = [("行ID", None)]
    for column in columns:
        header_cells.append((column["name"], "value"))
        header_cells.append((column["name"] + "·引用", "citation"))
        header_cells.append((column["name"] + "·状态", "state"))
    data_rows = []
    for row_ord, row in enumerate(projection["rows"], start=2):
        by_column = {cell["columnId"]: cell for cell in row["cells"]}
        cells_xml = [_cell_xml(1, row_ord, row["rowId"])]
        col_ord = 1
        for column in columns:
            col_ord += 1
            cell = by_column.get(column["id"])
            if cell is None:
                continue
            if cell["realValue"]:
                cells_xml.append(_cell_xml(col_ord, row_ord,
                                           cell["realValue"]))
            col_ord += 1
            if cell["citationCell"]:
                cells_xml.append(_cell_xml(col_ord, row_ord,
                                           cell["citationCell"]))
            col_ord += 1
            cells_xml.append(_cell_xml(col_ord, row_ord, cell["stateCell"]))
        data_rows.append(
            '<row r="%d">%s</row>' % (row_ord, "".join(cells_xml)))
    header_xml = "".join(
        _cell_xml(offset + 1, 1, text)
        for offset, (text, _) in enumerate(header_cells))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"><sheetData>'
        '<row r="1">%s</row>%s</sheetData></worksheet>'
        % (header_xml, "".join(data_rows)))


def _cell_xml(col_ord: int, row_ord: int, text: str) -> str:
    ref = "%s%d" % (_column_letter(col_ord), row_ord)
    return ('<c r="%s" t="inlineStr"><is>'
            '<t xml:space="preserve">%s</t></is></c>'
            % (ref, escape(text)))


def _workbook_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats'
        '.org/officeDocument/2006/relationships"><sheets><sheet name='
        '"%s" sheetId="1" r:id="rId1"/></sheets></workbook>'
        % escape(_SHEET_NAME, {'"': "&quot;"}))


_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types"><Default Extension="rels" ContentType='
    '"application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType='
    '"application/vnd.openxmlformats-officedocument.spreadsheetml.'
    'sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.'
    'spreadsheetml.worksheet+xml"/></Types>')

_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
    '2006/relationships"><Relationship Id="rId1" Type="http://'
    'schemas.openxmlformats.org/officeDocument/2006/relationships/'
    'officeDocument" Target="xl/workbook.xml"/></Relationships>')

_WORKBOOK_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
    '2006/relationships"><Relationship Id="rId1" Type="http://'
    'schemas.openxmlformats.org/officeDocument/2006/relationships/'
    'worksheet" Target="worksheets/sheet1.xml"/></Relationships>')


def build_xlsx(projection: dict) -> bytes:
    """确定性 XLSX 字节：项序固定＋zip 项时间戳钉定＋XML 无时钟——
    同输入两跑同字节。"""
    parts = (
        ("[Content_Types].xml", _CONTENT_TYPES_XML),
        ("_rels/.rels", _RELS_XML),
        ("xl/workbook.xml", _workbook_xml()),
        ("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS_XML),
        ("xl/worksheets/sheet1.xml", _sheet_xml(projection)),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts:
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            info.create_system = 0
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


# ---------------------------------------------------------------------- #
# export.xlsx —— 投影＋确定性 XLSX（base64 回传，零自有持久化）
# ---------------------------------------------------------------------- #


def export_xlsx(args: dict, config: dict) -> dict:
    projection = export_projection(args, config)
    payload = build_xlsx(projection)
    return {
        "reviewBatchId": projection["reviewBatchId"],
        "batchStatus": projection["batchStatus"],
        "sha256": hashlib.sha256(payload).hexdigest(),
        "xlsx_b64": base64.b64encode(payload).decode("ascii"),
        "rowCount": len(projection["rows"]),
        "cellCount": projection["cellCount"],
        "projection": projection,
        "markerSyntax": MARKER_OPEN + "<引文文本>" + MARKER_CLOSE,
        "note": "真实格值（标记剥除后）与可审引用列同源一致；缺值＝空格"
                "不伪填；XLSX 确定性生成（同输入两跑同字节）；全部字符"
                "串格——金额十进制串原样入格不落浮点",
        "face": EXCEL_EXPORT_FACE_NOTE,
    }


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（export.*）
# ---------------------------------------------------------------------- #


def export_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发（export.*）。未列方法绝不落到这里。"""
    if method == "export.xlsx":
        return export_xlsx(args, config)
    raise NotConnected("export_method_not_in_frozen_list:" + method)
