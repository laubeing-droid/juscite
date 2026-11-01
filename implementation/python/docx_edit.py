"""F45 通道① agent CLI 直改文档（清洁版＋批注修订版 DOCX）——产品侧
document-adapter 公开面（W2b-U15）。

义务 06:F45 断言：「实际完整清洁/批注修订DOCX可打开；正文/表格/编号保真，
旧稿不覆盖」。通道①＝agent CLI 直接编辑文档：纯 Python 确定性生成两个
真实完整 DOCX——清洁版（全部编辑生效、零修订标记）＋批注修订版（同一
编辑集落成 w:ins/w:del 修订标记＋w:comment 批注）。Word/WPS 宿主自动化
（通道②）不在本面（U16）；本面不模拟宿主。

单一条流（经 U11 合同登记 harness 正式材料版本，assistant_edit 来源
=F114 闭集）：

  原稿（harness material 指定 revision；字节经 read_material CAS 随读
  必验回读——base_revision 钉定，无本地第二真源）
    │ docxedit.apply（闭集编辑操作，全部按原稿段落/表格索引寻址）
    ├─→ 清洁版 clean.docx（=将来 bake 后的 canonical 字节形态）
    ├─→ 批注修订版 annotated.docx（人审/宿主定位面：修订标记＋批注）
    ├─→ harness.add_material_revision(source=assistant_edit, bytes=清洁版)
    │     ＝F114 闭集来源（"AI 修订提案字节"）正式材料版本，头行前进
    └─→ harness.formal_propose(base_revision=assistant_edit 头行,
          bytes=清洁版, channel=machine, author, quotes=编辑定位集)
          → pending（U11/F47 提案账）
    正式采用（formal_decide accept → bake source=user_accept＝F114 §2
    "assistant 改的与用户接受的同字节两行来源不同"）属人审决定面，本单
    不前造 UI，合同链已通。

纪律（全部与既有面同基线）：
- 确定性：零模型、零网络、零随机；zip 时间戳钉定（1980-01-01），修订/
  批注 w:date 取调用方 edited_at 参数（ISO 串校验）——同输入两跑同字节。
- 保真硬门（产出落盘前独立检查器，不过即 typed 拒、不留产物）：检查器
  走 python-docx（lxml 解析路径，与生成引擎 xml.etree 不同算路）真打开
  两个产物——①清洁版零修订标记（无 w:ins/w:del/w:delText/
  commentReference，无 comments 部件）②清洁版正文投影==原稿＋恰好声明的
  编辑集（检查器从自己的 lxml 抽取独立重推期望）③批注修订版接受全部
  修订后的文本==清洁版（两版本语义绑定）④未编辑表格/格结构性相等
  ⑤编号：未编辑段落 numPr 结构性相等＋numbering.xml 部件逐字节⑥未编辑
  package 部件逐字节相等（styles/footer 等原样复制；批注修订版只许
  comments 三处新增）⑦修订标记计数/唯一 id/作者与编辑集对账、delText
  只在 w:del 内⑧批注 comments.xml 与锚点双向对账。
- 旧稿不覆盖：原稿字节在 harness CAS（append-only，随读必验）；本面
  产物 outputs/<seq>/ append-only（不删不改不覆写）；同 request id 重放
  幂等返回（harness 侧 CommandKey 派生键使写入天然幂等重放）。
- fail-closed：未配置状态根/harness 桥、quote 不存在或歧义、编辑冲突、
  不受支持的段落结构、base 漂移（harness 具名码透传）——一律 typed
  error（f45_*），绝不产出假成功；错误码不携材料内容。

边界（如实，不伪称）：
- v1 编辑闭集五种（replace_text/insert_paragraph/delete_paragraph/
  replace_cell/comment），全部按原稿 body 级段落索引与表格 (行,列)
  寻址；表格结构编辑（插行/删行/合并格）、页眉页脚编辑、多段落单元格
  编辑不在闭集（typed 拒）。
- 段落编辑面支持 pPr＋runs 构成的段落（书签/域等其它子元素=typed 拒）；
  编辑段落重建 runs 沿用原段首 run 的 rPr。
- 独立检查器需 python-docx（lxml）在解释器环境（缺=f45_checker_
  unavailable fail-closed，不静默跳过检查）；真宿主可开性另经
  LibreOffice headless 转换在验收 recon 实证（本面不依赖）。
- 文档根元素经 xml.etree 重序列化：已用命名空间前缀经 register_
  namespace 保留；mc:Ignorable 引用的未用前缀声明可能不保留（v1 支持
  ET 可往返的文档；验收语料与常规 Writer/Word 产物均在此列）。
- F53 作者策略（AI 修订不冒律师）后续面；本面如实记录 author 元数据
  不校验身份（F47 §7 同款纪律）。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import threading
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f45-docx-edit/1"
STATE_SUBDIR = "docx-edit"
# 06:F45 通道①＝agent CLI；F47 通道闭集 machine/word/wps 中的 machine。
CHANNEL = "machine"
# F114 闭集来源（docs/f114-version-source-contract.md §1）：AI 修订提案
# 字节经 add_material_revision 显式声明 assistant_edit。
ASSISTANT_SOURCE = "assistant_edit"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_COMMENT_TYPE = ("application/vnd.openxmlformats-officedocument"
                 ".wordprocessingml.comments+xml")
_COMMENT_REL_TYPE = ("http://schemas.openxmlformats.org/officeDocument/2006"
                     "/relationships/comments")

EDIT_OPS = ("replace_text", "insert_paragraph", "delete_paragraph",
            "replace_cell", "comment")

_MATTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REQUEST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# zip 时间戳钉定：同输入两跑同字节（1980=zip 可表示最早值）。
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

_LOCK = threading.Lock()


class DocxEditError(ValueError):
    """Typed F45 face failure; str() is a code, never material content."""

    error_code = "f45_invalid"


def _fail(code: str) -> DocxEditError:
    return DocxEditError(code)


def _q(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def content_digest(docx_bytes: bytes) -> str:
    """部件级内容摘要（zip 容器时间戳不参与）——跨次生成可复现锚。"""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        parts = [f"{info.filename}:{_sha256(zf.read(info.filename))}"
                 for info in zf.infolist()]
    return _sha256("\n".join(sorted(parts)).encode("utf-8"))


def _copy_element(element) -> ET.Element:
    return ET.fromstring(ET.tostring(element))


def _struct_form(element) -> str:
    """前缀无关结构性规范形（自家确定性序列化）：本地名+排序属性+直属
    文本/尾文本+子结构。ET 与 lxml 元素同构可比（保真对照统一口径）。"""
    def local(tag) -> str:
        return tag.rsplit("}", 1)[-1] if isinstance(tag, str) and "}" in tag \
            else tag
    attrs = "|".join(f"{k}={v!r}" for k, v in sorted(element.attrib.items()))
    tails = [(child.tail or "").strip() for child in element]
    own = (element.text or "").strip()
    pieces = [local(element.tag), attrs]
    if own or any(tails):
        pieces.append("text=" + json.dumps(
            [own] + tails, ensure_ascii=False))
    pieces.extend(_struct_form(child) for child in element)
    return "(" + " ".join(pieces) + ")"


# ---------------------------------------------------------------------------
# 原稿模型（xml.etree 解析路径——生成引擎侧）
# ---------------------------------------------------------------------------

def _register_prefixes(raw_document_xml: bytes) -> None:
    """原稿根元素声明的 xmlns 前缀注册进 ET 序列化器（保住 w: 等前缀；
    未声明前缀不猜测）。根元素定位跳过 <?xml ...?> 声明与 <!-- 注释 -->
    （裸 find(b">") 会命中声明尾的 ?>，实测坑）。"""
    match = re.search(rb'<[A-Za-z0-9_:][^>]*>', raw_document_xml)
    if match is None:
        return
    root_tag = match.group(0)
    for prefix, uri in re.findall(
            rb'xmlns:([A-Za-z0-9_.-]+)="([^"]+)"', root_tag):
        try:
            ET.register_namespace(prefix.decode("ascii"),
                                  uri.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            continue  # 非常规前缀：ET 退回 ns0 形（规范形对照不受影响）


def _para_text(element) -> str:
    return "".join(node.text or "" for node in element.iter(_q("t")))


def _first_rpr(para) -> ET.Element | None:
    for run in para.findall(_q("r")):
        node = run.find(_q("rPr"))
        if node is not None:
            return node
        break
    return None


def parse_source(docx_bytes: bytes) -> dict:
    """原稿结构模型：body 级块序列（段落/表格/其它原样块）。段落索引=
    body 直接 w:p 子元素序；表格索引=body 直接 w:tbl 子元素序。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(docx_bytes))
    except (zipfile.BadZipFile, OSError) as exc:
        raise _fail("f45_source_unreadable:" + type(exc).__name__) from None
    with zf:
        if "word/document.xml" not in zf.namelist():
            raise _fail("f45_source_not_docx")
        raw = zf.read("word/document.xml")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise _fail("f45_source_xml_invalid:" + type(exc).__name__) from None
        body = root.find(_q("body"))
        if body is None:
            raise _fail("f45_source_body_missing")
        _register_prefixes(raw)
        blocks: list[dict] = []
        para_index = table_index = 0
        for child in body:
            if child.tag == _q("p"):
                blocks.append({
                    "kind": "para", "index": para_index, "element": child,
                    "text": _para_text(child),
                    "supported": all(grand.tag in (_q("pPr"), _q("r"))
                                     for grand in child),
                    "first_rpr": _first_rpr(child),
                })
                para_index += 1
            elif child.tag == _q("tbl"):
                rows: list[list[dict]] = []
                for tr in child.findall(_q("tr")):
                    cells = []
                    for tc in tr.findall(_q("tc")):
                        paras = tc.findall(_q("p"))
                        cells.append({
                            "paragraphs": paras,
                            "text": "".join(_para_text(p) for p in paras),
                            "first_rpr": (_first_rpr(paras[0])
                                          if paras else None),
                            "ppr": (paras[0].find(_q("pPr"))
                                    if paras else None),
                        })
                    rows.append(cells)
                blocks.append({"kind": "table", "index": table_index,
                               "element": child, "rows": rows})
                table_index += 1
            else:
                blocks.append({"kind": "other", "element": child})
        return {"root": root, "blocks": blocks, "para_count": para_index,
                "table_count": table_index}


# ---------------------------------------------------------------------------
# 编辑计划（闭集操作；全部按原稿索引寻址，单帧参照无歧义）
# ---------------------------------------------------------------------------

_OP_FIELDS = {
    "replace_text": {"op", "paragraph", "find", "replace", "reason"},
    "insert_paragraph": {"op", "after", "text", "reason", "numbering",
                         "style"},
    "delete_paragraph": {"op", "paragraph", "reason"},
    "replace_cell": {"op", "table", "row", "col", "text", "reason"},
    "comment": {"op", "paragraph", "text"},
}


def _require_str(value, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise _fail(code)
    return value


def _require_index(value, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _fail(code)
    return value


def _para_block(model: dict, index: int, *, require_supported: bool) -> dict:
    if index >= model["para_count"]:
        raise _fail("f45_edit_paragraph_out_of_range")
    block = next(b for b in model["blocks"]
                 if b["kind"] == "para" and b["index"] == index)
    if require_supported and not block["supported"]:
        raise _fail("f45_paragraph_unsupported")
    return block


def plan_edits(model: dict, edits) -> dict:
    """编辑集→计划。冲突=同段两处内容编辑（replace/delete 互斥）、
    同格两处 replace_cell。insert 按 after 锚点聚组、保持编辑集次序。"""
    if not isinstance(edits, list) or not edits:
        raise _fail("f45_edits_required")
    # replace/delete: 段索引→规格；cells: (表,行,列)→规格；comments: 仅显式
    # 批注 op（锚点面）；quotes: 全部内容编辑的宿主定位集（提案 quotes）。
    plan = {"replace": {}, "delete": {}, "inserts": [], "cells": {},
            "comments": [], "quotes": []}
    for edit in edits:
        if not isinstance(edit, dict):
            raise _fail("f45_edit_fields_invalid")
        op = edit.get("op")
        if op not in _OP_FIELDS:
            raise _fail("f45_edit_op_unknown")
        if set(edit) != _OP_FIELDS[op]:
            raise _fail("f45_edit_fields_not_closed:" + op)
        if op == "replace_text":
            index = _require_index(edit["paragraph"],
                                   "f45_edit_paragraph_invalid")
            find = _require_str(edit["find"], "f45_edit_find_required")
            if not isinstance(edit["replace"], str):
                raise _fail("f45_edit_replace_invalid")
            reason = _require_str(edit["reason"], "f45_edit_reason_required")
            block = _para_block(model, index, require_supported=True)
            hits = block["text"].count(find)
            if hits == 0:
                raise _fail("f45_quote_not_found:" + str(index))
            if hits > 1:
                raise _fail("f45_quote_ambiguous:" + str(index))
            if index in plan["replace"] or index in plan["delete"]:
                raise _fail("f45_edit_conflict:" + str(index))
            start = block["text"].index(find)
            plan["replace"][index] = {
                "prefix": block["text"][:start], "find": find,
                "replace": edit["replace"],
                "suffix": block["text"][start + len(find):],
                "reason": reason,
            }
            plan["quotes"].append({"text": find, "reason": reason})
        elif op == "insert_paragraph":
            after = _require_index(edit["after"], "f45_edit_after_invalid")
            text = _require_str(edit["text"], "f45_edit_text_required")
            reason = _require_str(edit["reason"], "f45_edit_reason_required")
            if after >= model["para_count"]:
                raise _fail("f45_edit_paragraph_out_of_range")
            numbering = edit["numbering"]
            if numbering is not None and (
                    not isinstance(numbering, dict)
                    or set(numbering) != {"numId", "ilvl"}
                    or isinstance(numbering.get("numId"), bool)
                    or not isinstance(numbering.get("numId"), int)
                    or isinstance(numbering.get("ilvl"), bool)
                    or not isinstance(numbering.get("ilvl"), int)):
                raise _fail("f45_edit_numbering_invalid")
            style = edit["style"]
            if style is not None and not isinstance(style, str):
                raise _fail("f45_edit_style_invalid")
            plan["inserts"].append({"after": after, "text": text,
                                    "reason": reason, "numbering": numbering,
                                    "style": style})
            plan["quotes"].append({"text": text, "reason": reason})
        elif op == "delete_paragraph":
            index = _require_index(edit["paragraph"],
                                   "f45_edit_paragraph_invalid")
            reason = _require_str(edit["reason"], "f45_edit_reason_required")
            block = _para_block(model, index, require_supported=True)
            if index in plan["replace"] or index in plan["delete"]:
                raise _fail("f45_edit_conflict:" + str(index))
            plan["delete"][index] = {"reason": reason}
            # 空段落定位约定：quote 非空校验下以 ¶索引 作宿主定位文本。
            plan["quotes"].append({
                "text": block["text"] or f"¶{index}", "reason": reason})
        elif op == "replace_cell":
            table = _require_index(edit["table"], "f45_edit_table_invalid")
            row = _require_index(edit["row"], "f45_edit_row_invalid")
            col = _require_index(edit["col"], "f45_edit_col_invalid")
            text = _require_str(edit["text"], "f45_edit_text_required")
            reason = _require_str(edit["reason"], "f45_edit_reason_required")
            target = next(
                (b for b in model["blocks"]
                 if b["kind"] == "table" and b["index"] == table), None)
            if target is None:
                raise _fail("f45_edit_table_out_of_range")
            if row >= len(target["rows"]) or col >= len(target["rows"][row]):
                raise _fail("f45_edit_cell_out_of_range")
            cell = target["rows"][row][col]
            if len(cell["paragraphs"]) != 1:
                raise _fail("f45_cell_unsupported")
            if (table, row, col) in plan["cells"]:
                raise _fail("f45_edit_conflict:cell")
            plan["cells"][(table, row, col)] = {
                "text": text, "reason": reason, "old": cell["text"]}
            plan["quotes"].append({"text": cell["text"], "reason": reason})
        else:  # comment
            index = _require_index(edit["paragraph"],
                                   "f45_edit_paragraph_invalid")
            text = _require_str(edit["text"], "f45_edit_text_required")
            _para_block(model, index, require_supported=False)
            plan["comments"].append({"text": text, "paragraph": index})
    return plan


# ---------------------------------------------------------------------------
# 修订标记构造（批注修订版）
# ---------------------------------------------------------------------------

class _RevisionIds:
    def __init__(self):
        self.next_id = 1000

    def take(self) -> int:
        value = self.next_id
        self.next_id += 1
        return value


def _make_run(text: str, rpr=None, deleted: bool = False) -> ET.Element:
    run = ET.Element(_q("r"))
    if rpr is not None:
        run.append(_copy_element(rpr))
    node = ET.SubElement(run, _q("delText") if deleted else _q("t"))
    node.set(XML_SPACE, "preserve")
    node.text = text
    return run


def _rev_wrap(tag: str, ids: _RevisionIds, author: str, edited_at: str,
              children: list[ET.Element]) -> ET.Element:
    node = ET.Element(_q(tag))
    node.set(_q("id"), str(ids.take()))
    node.set(_q("author"), author)
    node.set(_q("date"), edited_at)
    for child in children:
        node.append(child)
    return node


def _mark_paragraph_mark(para: ET.Element, tag: str, ids: _RevisionIds,
                         author: str, edited_at: str) -> None:
    """段落标记修订（插入/删除整段）：pPr/rPr/<w:ins|w:del>。"""
    ppr = para.find(_q("pPr"))
    if ppr is None:
        ppr = ET.Element(_q("pPr"))
        para.insert(0, ppr)
    rpr = ppr.find(_q("rPr"))
    if rpr is None:
        rpr = ET.SubElement(ppr, _q("rPr"))
    mark = ET.SubElement(rpr, _q(tag))
    mark.set(_q("id"), str(ids.take()))
    mark.set(_q("author"), author)
    mark.set(_q("date"), edited_at)


def _comment_anchor(comment_id: int) -> tuple[ET.Element, ET.Element,
                                              ET.Element]:
    start = ET.Element(_q("commentRangeStart"))
    start.set(_q("id"), str(comment_id))
    end = ET.Element(_q("commentRangeEnd"))
    end.set(_q("id"), str(comment_id))
    ref_run = ET.Element(_q("r"))
    rpr = ET.SubElement(ref_run, _q("rPr"))
    style = ET.SubElement(rpr, _q("rStyle"))
    style.set(_q("val"), "CommentReference")
    ref = ET.SubElement(ref_run, _q("commentReference"))
    ref.set(_q("id"), str(comment_id))
    return start, end, ref_run


def _para_ppr_copy(source_para_element) -> ET.Element | None:
    ppr = source_para_element.find(_q("pPr"))
    return _copy_element(ppr) if ppr is not None else None


# ---------------------------------------------------------------------------
# 双版本生成
# ---------------------------------------------------------------------------

def generate_versions(model: dict, plan: dict, author: str,
                      edited_at: str) -> dict:
    """清洁版＋批注修订版生成（同一编辑计划两条投影）。

  段落分支：删除段（清洁版消失；批注修订版段落标记 del＋runs 包
  del＋批注）；替换段（清洁版重建 prefix+replace+suffix；批注修订版
  prefix 平文＋find 包 del＋replace 包 ins＋批注）；未编辑段（原样；
  有批注则批注修订版附锚点）；插入段（清洁版新段；批注修订版标记
  ins＋runs 包 ins＋批注）。表格分支：未编辑表原样；编辑表目标格
  重建（清洁版=新文本；批注修订版=旧包 del＋新包 ins＋批注锚）。"""
    ids = _RevisionIds()
    comments: list[dict] = []

    def add_comment(text: str) -> int:
        comments.append({"id": len(comments) + 1, "text": text})
        return comments[-1]["id"]

    comment_extras: dict[int, list[str]] = {}
    for spec in plan["comments"]:
        comment_extras.setdefault(spec["paragraph"], []).append(spec["text"])
    inserts_by_anchor: dict[int, list[dict]] = {}
    for spec in plan["inserts"]:
        inserts_by_anchor.setdefault(spec["after"], []).append(spec)

    def _anchors(texts: list[str]) -> tuple[list[ET.Element],
                                            list[ET.Element]]:
        """每条批注一组锚点：commentRangeStart（置于内容前）＋
        commentRangeEnd/commentReference（置于内容后）。"""
        starts: list[ET.Element] = []
        ends: list[ET.Element] = []
        for text in texts:
            start, end, ref = _comment_anchor(add_comment(text))
            starts.append(start)
            ends.append(end)
            ends.append(ref)
        return starts, ends

    clean_blocks: list[ET.Element] = []
    annotated_blocks: list[ET.Element] = []
    counts = {"replace": 0, "insert": 0, "delete": 0, "cell": 0}

    for block in model["blocks"]:
        if block["kind"] == "para":
            index = block["index"]
            replaced = plan["replace"].get(index)
            deleted = index in plan["delete"]
            extra = comment_extras.get(index, [])
            if deleted:
                counts["delete"] += 1
                para = ET.Element(_q("p"))
                ppr = _para_ppr_copy(block["element"])
                if ppr is not None:
                    para.append(ppr)
                _mark_paragraph_mark(para, "del", ids, author, edited_at)
                starts, ends = _anchors(
                    [plan["delete"][index]["reason"]] + extra)
                for node in starts:
                    para.append(node)
                if block["text"]:
                    para.append(_rev_wrap("del", ids, author, edited_at, [
                        _make_run(block["text"], block["first_rpr"],
                                  deleted=True)]))
                for node in ends:
                    para.append(node)
                annotated_blocks.append(para)
            elif replaced is not None:
                counts["replace"] += 1
                clean = ET.Element(_q("p"))
                ppr = _para_ppr_copy(block["element"])
                if ppr is not None:
                    clean.append(ppr)
                for text in (replaced["prefix"], replaced["replace"],
                             replaced["suffix"]):
                    if text:
                        clean.append(
                            _make_run(text, block["first_rpr"]))
                clean_blocks.append(clean)

                para = ET.Element(_q("p"))
                ppr = _para_ppr_copy(block["element"])
                if ppr is not None:
                    para.append(ppr)
                starts, ends = _anchors([replaced["reason"]] + extra)
                for node in starts:
                    para.append(node)
                if replaced["prefix"]:
                    para.append(_make_run(replaced["prefix"],
                                          block["first_rpr"]))
                para.append(_rev_wrap("del", ids, author, edited_at, [
                    _make_run(replaced["find"], block["first_rpr"],
                              deleted=True)]))
                para.append(_rev_wrap("ins", ids, author, edited_at, [
                    _make_run(replaced["replace"], block["first_rpr"])]))
                if replaced["suffix"]:
                    para.append(_make_run(replaced["suffix"],
                                          block["first_rpr"]))
                for node in ends:
                    para.append(node)
                annotated_blocks.append(para)
            else:
                clean_blocks.append(block["element"])
                if extra:
                    para = _copy_element(block["element"])
                    starts, ends = _anchors(extra)
                    insert_at = 1 if para.find(_q("pPr")) is not None else 0
                    for offset, node in enumerate(starts):
                        para.insert(insert_at + offset, node)
                    for node in ends:
                        para.append(node)
                    annotated_blocks.append(para)
                else:
                    annotated_blocks.append(_copy_element(block["element"]))
            for spec in inserts_by_anchor.get(index, []):
                counts["insert"] += 1

                def _new_para(style, numbering) -> ET.Element:
                    para = ET.Element(_q("p"))
                    if style is not None or numbering is not None:
                        ppr = ET.Element(_q("pPr"))
                        if style is not None:
                            node = ET.SubElement(ppr, _q("pStyle"))
                            node.set(_q("val"), style)
                        if numbering is not None:
                            numpr = ET.SubElement(ppr, _q("numPr"))
                            node = ET.SubElement(numpr, _q("ilvl"))
                            node.set(_q("val"), str(numbering["ilvl"]))
                            node = ET.SubElement(numpr, _q("numId"))
                            node.set(_q("val"), str(numbering["numId"]))
                        para.append(ppr)
                    return para

                clean = _new_para(spec["style"], spec["numbering"])
                clean.append(_make_run(spec["text"]))
                clean_blocks.append(clean)
                para = _new_para(spec["style"], spec["numbering"])
                _mark_paragraph_mark(para, "ins", ids, author, edited_at)
                starts, ends = _anchors([spec["reason"]])
                for node in starts:
                    para.append(node)
                para.append(_rev_wrap("ins", ids, author, edited_at, [
                    _make_run(spec["text"])]))
                for node in ends:
                    para.append(node)
                annotated_blocks.append(para)
        elif block["kind"] == "table":
            table_index = block["index"]
            cell_specs = {key: spec for key, spec in plan["cells"].items()
                          if key[0] == table_index}
            if not cell_specs:
                clean_blocks.append(block["element"])
                annotated_blocks.append(_copy_element(block["element"]))
            else:
                counts["cell"] += len(cell_specs)
                clean_table = _copy_element(block["element"])
                annotated_table = _copy_element(block["element"])
                clean_rows = clean_table.findall(_q("tr"))
                annotated_rows = annotated_table.findall(_q("tr"))
                for (table_i, row_i, col_i), spec in cell_specs.items():
                    tc_clean = clean_rows[row_i].findall(_q("tc"))[col_i]
                    para = tc_clean.findall(_q("p"))[0]
                    new_para = ET.Element(_q("p"))
                    ppr = para.find(_q("pPr"))
                    if ppr is not None:
                        new_para.append(_copy_element(ppr))
                    if spec["text"]:
                        new_para.append(_make_run(spec["text"]))
                    tc_clean.remove(para)
                    tc_clean.insert(0, new_para)

                    tc_annotated = annotated_rows[row_i].findall(
                        _q("tc"))[col_i]
                    para = tc_annotated.findall(_q("p"))[0]
                    new_para = ET.Element(_q("p"))
                    ppr = para.find(_q("pPr"))
                    if ppr is not None:
                        new_para.append(_copy_element(ppr))
                    starts, ends = _anchors([spec["reason"]])
                    for node in starts:
                        new_para.append(node)
                    if spec["old"]:
                        new_para.append(_rev_wrap(
                            "del", ids, author, edited_at,
                            [_make_run(spec["old"],
                                       block["rows"][row_i][col_i]
                                       ["first_rpr"], deleted=True)]))
                    new_para.append(_rev_wrap(
                        "ins", ids, author, edited_at,
                        [_make_run(spec["text"],
                                   block["rows"][row_i][col_i]
                                   ["first_rpr"])]))
                    for node in ends:
                        new_para.append(node)
                    tc_annotated.remove(para)
                    tc_annotated.insert(0, new_para)
                clean_blocks.append(clean_table)
                annotated_blocks.append(annotated_table)
        else:
            clean_blocks.append(block["element"])
            annotated_blocks.append(_copy_element(block["element"]))
    return {"clean_blocks": clean_blocks,
            "annotated_blocks": annotated_blocks,
            "comments": comments, "counts": counts}


def _serialize_document(model: dict, blocks: list[ET.Element]) -> bytes:
    root = ET.Element(model["root"].tag, dict(model["root"].attrib))
    body = ET.SubElement(root, _q("body"))
    for block in blocks:
        body.append(block)
    return (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            + ET.tostring(root, encoding="utf-8", xml_declaration=False))


def _extend_content_types(payload: bytes) -> bytes:
    """字节级插入 comments Override（OPC 解析器要求默认命名空间形——
    ET 重序列化会换 ns0 前缀，LibreOffice 实测拒载）。"""
    if b"/word/comments.xml" in payload:
        return payload
    override = (b'<Override PartName="/word/comments.xml" ContentType="'
                + _COMMENT_TYPE.encode("ascii") + b'"/>')
    close = payload.rfind(b"</Types>")
    if close < 0:
        raise _fail("f45_content_types_unparsable")
    return payload[:close] + override + payload[close:]


def _extend_document_rels(payload: bytes) -> bytes:
    """字节级插入 comments Relationship（同 _extend_content_types 纪律）。
    rId 取既有最大序号＋1（不再解析整树）。"""
    numbers = [int(m.group(1)) for m in re.finditer(
        rb'Id="rId(\d+)"', payload)]
    next_num = max(numbers, default=0) + 1
    rel = (b'<Relationship Id="rId' + str(next_num).encode("ascii")
           + b'" Type="' + _COMMENT_REL_TYPE.encode("ascii")
           + b'" Target="comments.xml"/>')
    close = payload.rfind(b"</Relationships>")
    if close < 0:
        raise _fail("f45_rels_unparsable")
    return payload[:close] + rel + payload[close:]


def _comments_xml(comments: list[dict], author: str,
                   edited_at: str) -> bytes:
    root = ET.Element(_q("comments"))
    for comment in comments:
        node = ET.SubElement(root, _q("comment"))
        node.set(_q("id"), str(comment["id"]))
        node.set(_q("author"), author)
        node.set(_q("date"), edited_at)
        node.set(_q("initials"), author[:2])
        para = ET.SubElement(node, _q("p"))
        run = ET.SubElement(para, _q("r"))
        text = ET.SubElement(run, _q("t"))
        text.set(XML_SPACE, "preserve")
        text.text = comment["text"]
    return (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            + ET.tostring(root, encoding="utf-8", xml_declaration=False))


def build_versions(source_bytes: bytes, model: dict, plan: dict, author: str,
                   edited_at: str) -> dict:
    """一步生成两版 DOCX 字节（确定性：同输入两跑同字节）。"""
    generated = generate_versions(model, plan, author, edited_at)
    clean_doc = _serialize_document(model, generated["clean_blocks"])
    annotated_doc = _serialize_document(model,
                                        generated["annotated_blocks"])

    def _package(document_xml: bytes,
                 comments: list[dict] | None) -> bytes:
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as src, \
                zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
            for name in src.namelist():
                if name == "word/document.xml":
                    continue
                payload = src.read(name)
                if comments is not None:
                    if name == "[Content_Types].xml":
                        payload = _extend_content_types(payload)
                    elif name == "word/_rels/document.xml.rels":
                        payload = _extend_document_rels(payload)
                info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(info, payload)
            if comments:
                info = zipfile.ZipInfo("word/comments.xml",
                                       date_time=_ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(info, _comments_xml(comments, author,
                                                 edited_at))
            info = zipfile.ZipInfo("word/document.xml", date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, document_xml)
        return out.getvalue()

    return {"clean": _package(clean_doc, None),
            "annotated": _package(annotated_doc, generated["comments"]),
            "counts": generated["counts"],
            "comments": generated["comments"]}


# ---------------------------------------------------------------------------
# 独立保真检查器（python-docx/lxml 解析路径——与生成引擎不同算路）
# ---------------------------------------------------------------------------

def fidelity_check(source_bytes: bytes, clean_bytes: bytes,
                   annotated_bytes: bytes, plan: dict, author: str) -> dict:
    """产出落盘前硬门。任何一维不过＝f45_fidelity_* typed 拒（先检查全部
  维度再统一判——报告携带各维事实）。

  期望值全部由检查器从自己的 lxml 抽取＋编辑计划独立重推，不复用生成
  引擎的 xml.etree 中间产物。"""
    try:
        from docx import Document as _Docx
    except ImportError:
        raise _fail("f45_checker_unavailable") from None
    from lxml import etree as _etree

    def _open(payload: bytes):
        try:
            return _Docx(io.BytesIO(payload))
        except Exception as exc:
            raise _fail("f45_docx_unopenable:" + type(exc).__name__) from None

    def _zip_names(payload: bytes) -> set[str]:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            return set(zf.namelist())

    def _zip_read(payload: bytes, name: str) -> bytes:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            return zf.read(name)

    source_doc = _open(source_bytes)
    clean_doc = _open(clean_bytes)
    annotated_doc = _open(annotated_bytes)
    source_body = source_doc.element.body
    clean_body = clean_doc.element.body
    annotated_body = annotated_doc.element.body

    def _paras(body):
        return [child for child in body if child.tag == _q("p")]

    def _tables(body):
        return [child for child in body if child.tag == _q("tbl")]

    def _text(element) -> str:
        return "".join(node.text or "" for node in element.iter(_q("t")))

    def _para_texts(body) -> list[str]:
        return [_text(para) for para in _paras(body)]

    dimensions: dict[str, dict] = {}

    # ---- 维度1：清洁版零修订标记（结构性干净，无 comments 部件）。
    markup_tags = {_q("ins"), _q("del"), _q("delText"),
                   _q("commentReference"), _q("commentRangeStart"),
                   _q("commentRangeEnd")}
    clean_marks = sum(1 for node in clean_body.iter()
                      if node.tag in markup_tags)
    dimensions["clean_is_clean"] = {
        "revision_marks": clean_marks,
        "comments_part_present": "word/comments.xml" in _zip_names(clean_bytes),
    }
    if clean_marks or "word/comments.xml" in _zip_names(clean_bytes):
        raise _fail("f45_fidelity_clean_is_clean")

    # ---- 维度2：正文投影（检查器自推期望：原稿 lxml 文本＋编辑计划）。
    source_texts = _para_texts(source_body)
    expected_texts: list[str] = []
    insert_after: dict[int, list[str]] = {}
    for spec in plan["inserts"]:
        insert_after.setdefault(spec["after"], []).append(spec["text"])
    for index, text in enumerate(source_texts):
        if index in plan["delete"]:
            pass
        elif index in plan["replace"]:
            spec = plan["replace"][index]
            hits = text.count(spec["find"])
            if hits != 1:
                raise _fail("f45_fidelity_expectation_unstable")
            start = text.index(spec["find"])
            expected_texts.append(text[:start] + spec["replace"]
                                  + text[start + len(spec["find"]):])
        else:
            expected_texts.append(text)
        for extra in insert_after.get(index, []):
            expected_texts.append(extra)
    clean_texts = _para_texts(clean_body)
    dimensions["body_text"] = {
        "expected_paragraphs": len(expected_texts),
        "clean_paragraphs": len(clean_texts),
        "equal": expected_texts == clean_texts,
    }
    if expected_texts != clean_texts:
        raise _fail("f45_fidelity_body_text")

    # ---- 维度3：批注修订版接受全部修订==清洁版（两版本语义绑定）。
    def _blocks_projection(body, *, skip_deleted_marks: bool) -> list[str]:
        out: list[str] = []
        for child in body:
            if child.tag == _q("p"):
                if skip_deleted_marks and child.findall(
                        f"{_q('pPr')}/{_q('rPr')}/{_q('del')}"):
                    continue
                out.append(_text(child))
            elif child.tag == _q("tbl"):
                cells = [_text(tc) for tr in child.findall(_q("tr"))
                         for tc in tr.findall(_q("tc"))]
                out.append("TBL:" + "|".join(cells))
        return out

    projected = _blocks_projection(annotated_body, skip_deleted_marks=True)
    clean_projection = _blocks_projection(clean_body, skip_deleted_marks=False)
    dimensions["accept_projection_equals_clean"] = {
        "projected_blocks": len(projected),
        "clean_blocks": len(clean_projection),
        "equal": projected == clean_projection,
    }
    if projected != clean_projection:
        raise _fail("f45_fidelity_accept_projection")

    # ---- 维度4：表格（数量相等；编辑表内未编辑格结构性相等、编辑格文本
    #      ==声明）。
    source_tables = _tables(source_body)
    clean_tables = _tables(clean_body)
    mismatches = 0
    if len(source_tables) == len(clean_tables):
        for table_index, (source_tbl, clean_tbl) in enumerate(
                zip(source_tables, clean_tables)):
            edited = {key[1:]: spec for key, spec in plan["cells"].items()
                      if key[0] == table_index}
            s_rows = source_tbl.findall(_q("tr"))
            c_rows = clean_tbl.findall(_q("tr"))
            if len(s_rows) != len(c_rows):
                mismatches += 1
                continue
            for row_index, (s_tr, c_tr) in enumerate(zip(s_rows, c_rows)):
                s_cells = s_tr.findall(_q("tc"))
                c_cells = c_tr.findall(_q("tc"))
                if len(s_cells) != len(c_cells):
                    mismatches += 1
                    continue
                for col_index, (s_tc, c_tc) in enumerate(zip(s_cells,
                                                             c_cells)):
                    if (row_index, col_index) in edited:
                        if _text(c_tc) != edited[(row_index, col_index)]["text"]:
                            mismatches += 1
                    elif _struct_form(s_tc) != _struct_form(c_tc):
                        mismatches += 1
    dimensions["tables"] = {
        "source_tables": len(source_tables),
        "clean_tables": len(clean_tables),
        "edited_cells": len(plan["cells"]),
        "mismatches": mismatches,
    }
    if len(source_tables) != len(clean_tables) or mismatches:
        raise _fail("f45_fidelity_tables")

    # ---- 维度5：编号（未编辑段落 numPr 结构性相等；插入段携带声明编号；
    #      numbering.xml 部件逐字节或两侧同缺）。
    def _numpr_forms(body) -> list:
        out = []
        for para in _paras(body):
            node = para.find(f"{_q('pPr')}/{_q('numPr')}")
            out.append(None if node is None else _struct_form(node))
        return out

    def _expected_numpr(numbering) -> str | None:
        if numbering is None:
            return None
        numpr = ET.Element(_q("numPr"))
        node = ET.SubElement(numpr, _q("ilvl"))
        node.set(_q("val"), str(numbering["ilvl"]))
        node = ET.SubElement(numpr, _q("numId"))
        node.set(_q("val"), str(numbering["numId"]))
        return _struct_form(numpr)

    source_numprs = iter(_numpr_forms(source_body))
    expected_numprs: list = []
    for index in range(len(source_texts)):
        if index not in plan["delete"]:
            expected_numprs.append(next(source_numprs))
        else:
            next(source_numprs)
        for spec in plan["inserts"]:
            if spec["after"] == index:
                expected_numprs.append(_expected_numpr(spec["numbering"]))
    clean_numprs = _numpr_forms(clean_body)
    numbering_part = ("word/numbering.xml" in _zip_names(source_bytes)
                      and "word/numbering.xml" in _zip_names(clean_bytes)
                      and _zip_read(source_bytes, "word/numbering.xml")
                      == _zip_read(clean_bytes, "word/numbering.xml"))
    dimensions["numbering"] = {
        "numprs_equal": expected_numprs == clean_numprs,
        "paragraphs": len(clean_numprs),
        "numbering_part_identical": numbering_part
        if "word/numbering.xml" in _zip_names(source_bytes) else None,
    }
    if expected_numprs != clean_numprs:
        raise _fail("f45_fidelity_numbering")
    if "word/numbering.xml" in _zip_names(source_bytes) and \
            "word/numbering.xml" not in _zip_names(clean_bytes):
        raise _fail("f45_fidelity_numbering_part_missing")

    # ---- 维度6：package 部件（未编辑部件逐字节；批注修订版只许 comments
    #      三处新增）。
    source_names = _zip_names(source_bytes)
    clean_names = _zip_names(clean_bytes)
    annotated_names = _zip_names(annotated_bytes)
    regen = {"word/document.xml", "[Content_Types].xml",
             "word/_rels/document.xml.rels"}
    allowed_extra = {"word/comments.xml"}
    missing = sorted(source_names - clean_names)
    extra_clean = sorted(clean_names - source_names)
    unexpected_ann = sorted(annotated_names - source_names - allowed_extra)
    byte_mismatch = []
    for name in sorted(source_names):
        if name in regen:
            continue
        if _zip_read(source_bytes, name) != _zip_read(clean_bytes, name):
            byte_mismatch.append("clean:" + name)
        if _zip_read(source_bytes, name) != _zip_read(annotated_bytes, name):
            byte_mismatch.append("annotated:" + name)
    dimensions["package_parts"] = {
        "source_parts": len(source_names),
        "missing_in_clean": missing,
        "extra_in_clean": extra_clean,
        "unexpected_in_annotated": unexpected_ann,
        "annotated_extra": sorted(annotated_names - source_names),
        "byte_mismatch": byte_mismatch[:8],
    }
    if missing or extra_clean or unexpected_ann or byte_mismatch:
        raise _fail("f45_fidelity_package_parts")

    # ---- 维度7：修订标记对账（计数·唯一 id·作者·delText 归位）。
    ins_nodes = list(annotated_body.iter(_q("ins")))
    del_nodes = list(annotated_body.iter(_q("del")))
    del_text_nodes = list(annotated_body.iter(_q("delText")))
    expected_ins = len(plan["replace"]) + 2 * len(plan["inserts"]) \
        + len(plan["cells"])
    expected_del = len(plan["replace"]) + len(plan["cells"]) \
        + sum(2 if source_texts[index] else 1
              for index in plan["delete"])
    ids_seen = [node.get(_q("id")) for node in ins_nodes + del_nodes]
    authors = {node.get(_q("author")) for node in ins_nodes + del_nodes}
    misplaced = [node for node in del_text_nodes
                 if node.getparent().tag != _q("r")
                 or node.getparent().getparent() is None
                 or node.getparent().getparent().tag != _q("del")]
    t_in_del = [node for node in annotated_body.iter(_q("t"))
                if any(anc.tag == _q("del")
                       for anc in node.iterancestors())]
    dimensions["revision_markup"] = {
        "ins": len(ins_nodes), "expected_ins": expected_ins,
        "del": len(del_nodes), "expected_del": expected_del,
        "ids_unique": len(ids_seen) == len(set(ids_seen)),
        "authors": sorted(authors),
        "del_text_misplaced": len(misplaced) + len(t_in_del),
    }
    if (len(ins_nodes) != expected_ins or len(del_nodes) != expected_del
            or len(ids_seen) != len(set(ids_seen))
            or ((ins_nodes or del_nodes) and authors != {author})
            or misplaced or t_in_del):
        raise _fail("f45_fidelity_revision_markup")

    # ---- 维度8：批注（comments.xml 与锚点双向对账＋计数==编辑集）。
    with zipfile.ZipFile(io.BytesIO(annotated_bytes)) as zf:
        comments_root = _etree.fromstring(zf.read("word/comments.xml"))
    comment_ids = {node.get(_q("id")) for node in comments_root}
    ref_ids = {node.get(_q("id")) for node in
               annotated_body.iter(_q("commentReference"))}
    expected_comments = (len(plan["replace"]) + len(plan["inserts"])
                         + len(plan["delete"]) + len(plan["cells"])
                         + len(plan["comments"]))
    dimensions["comments"] = {
        "comment_ids": len(comment_ids), "reference_ids": len(ref_ids),
        "expected": expected_comments,
        "bidirectional": comment_ids == ref_ids,
    }
    if comment_ids != ref_ids or len(comment_ids) != expected_comments:
        raise _fail("f45_fidelity_comments")

    return {
        "comparison": "independent_lxml_projection",
        "checker": "python-docx/lxml",
        "dimensions": dimensions,
        "all_passed": True,
        "counts": {"ins": expected_ins, "del": expected_del,
                   "comments": expected_comments},
    }


# ---------------------------------------------------------------------------
# 状态布局＋harness 登记（单一条流编排）
# ---------------------------------------------------------------------------

def _material_root(state_root: Path, matter_id: str, material_id: str) -> Path:
    return Path(state_root) / STATE_SUBDIR / matter_id / material_id


def _atomic_write(path: Path, payload: bytes) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def _next_output_dir(material_root: Path) -> Path:
    outputs = material_root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    seq = 1
    for entry in sorted(outputs.iterdir()):
        if entry.is_dir() and entry.name.isdigit():
            seq = max(seq, int(entry.name) + 1)
    return outputs / f"{seq:04d}"


def _find_replay(material_root: Path, request_id: str) -> dict | None:
    outputs = material_root / "outputs"
    if not outputs.is_dir():
        return None
    for entry in sorted(outputs.iterdir(), reverse=True):
        manifest_path = entry / "output.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if manifest.get("request_id") == request_id:
            return manifest
    return None


def _quotes_for_proposal(plan: dict, matter_id: str, material_id: str,
                         base_revision: int) -> list[dict]:
    """编辑定位集→F47 提案 quotes（精确 quote＋理由＋出处 ref）。"""
    source_ref = {"owner": "harness", "kind": "material",
                  "id": material_id, "version": str(base_revision),
                  "matterId": matter_id}
    return [{"text": quote["text"], "reason": quote["reason"],
             "sourceRef": dict(source_ref)} for quote in plan["quotes"]]


def _bridge_harness_call(config: dict):
    """缺省 harness 径＝产品桥（legal_entry 封闭信封子进程）。recon 的
    selfhost profile 注入 PgMatterStore 直连 seam（同合同对照，先例=
    W2b-U11 recon 直连公开面）。"""
    import legal_entry

    def call(method: str, args: dict):
        return legal_entry.call(method, args, config)
    return call


def _read_base_bytes(harness_call, matter_id: str, material_id: str,
                     base_revision: int) -> bytes:
    payload = harness_call("harness.read_material", {
        "scope": {"kind": "matter", "matterId": matter_id},
        "material_id": material_id, "revision": base_revision})
    try:
        raw = base64.b64decode(payload["bytesB64"])
        if payload.get("sha256") != _sha256(raw):
            raise _fail("f45_base_bytes_mismatch")
        return raw
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, DocxEditError):
            raise
        raise _fail("f45_base_readback_invalid") from None


def apply_edit(state_root: Path, config: dict, args: dict,
               harness_call=None) -> dict:
    """通道① 主入口：原稿回读→双版本生成→独立保真硬门→harness 正式
    材料版本（assistant_edit∈F114）＋U11 提案（channel=machine）→
    append-only 产物落盘。同 request id 重放幂等返回。"""
    if not isinstance(args, dict):
        raise _fail("f45_params_invalid")
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.match(matter_id):
        raise _fail("f45_matter_invalid")
    material_id = args.get("material_id")
    if not isinstance(material_id, str) or not _MATTER_RE.match(material_id):
        raise _fail("f45_material_invalid")
    base_revision = args.get("base_revision")
    if isinstance(base_revision, bool) or not isinstance(base_revision, int) \
            or base_revision < 1:
        raise _fail("f45_base_revision_invalid")
    request_id = args.get("request_id")
    if not isinstance(request_id, str) or not _REQUEST_RE.match(request_id):
        raise _fail("f45_request_id_invalid")
    proposal_id = args.get("proposal_id")
    if not isinstance(proposal_id, str) or not _REQUEST_RE.match(proposal_id):
        raise _fail("f45_proposal_id_invalid")
    actor_id = args.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        raise _fail("f45_actor_invalid")
    author = args.get("author")
    if not isinstance(author, str) or not author:
        raise _fail("f45_author_required")
    # F53 收拢（W2b-U49）：docxedit 通道修订/提案作者过 author_policy 策略
    # 面（闭集外作者含律师名＝f53_author_impersonation 具名拒；机器生成
    # 不冒律师）。f45 形参校验在前，既有负向码不变。
    from author_policy import check_revision_author, AuthorPolicyError
    try:
        check_revision_author("docxedit", author)
    except AuthorPolicyError as exc:
        raise _fail(str(exc)) from None
    edited_at = args.get("edited_at")
    if not isinstance(edited_at, str) or not _ISO_RE.match(edited_at):
        raise _fail("f45_edited_at_invalid")
    note = args.get("note")
    if note is not None and not isinstance(note, str):
        raise _fail("f45_note_invalid")
    scope = {"kind": "matter", "matterId": matter_id}
    if harness_call is None:
        harness_call = _bridge_harness_call(config)

    with _LOCK:
        material_root = _material_root(state_root, matter_id, material_id)
        source_bytes = _read_base_bytes(harness_call, matter_id, material_id,
                                        base_revision)
        model = parse_source(source_bytes)
        plan = plan_edits(model, args.get("edits"))
        versions = build_versions(source_bytes, model, plan, author,
                                  edited_at)
        clean_bytes = versions["clean"]
        annotated_bytes = versions["annotated"]
        clean_sha = _sha256(clean_bytes)

        replay = _find_replay(material_root, request_id)
        if replay is not None:
            if replay["clean"]["sha256"] != clean_sha:
                raise _fail("f45_request_conflict")
            view = _public_view(replay)
            view["replayed"] = True
            return view

        fidelity = fidelity_check(source_bytes, clean_bytes, annotated_bytes,
                                  plan, author)

        clean_b64 = base64.b64encode(clean_bytes).decode("ascii")
        revision_receipt = harness_call("harness.add_material_revision", {
            "actor_id": actor_id, "scope": scope,
            "key": {"requestId": f"{request_id}:assistant-edit",
                    "targetId": None, "expectedRevision": None,
                    "inputRefs": []},
            "revision": {"materialId": material_id, "bytesB64": clean_b64,
                         "baseRevision": base_revision,
                         "source": ASSISTANT_SOURCE}})
        assistant_revision = revision_receipt["revision"]
        proposal_receipt = harness_call("harness.formal_propose", {
            "actor_id": actor_id, "scope": scope,
            "key": {"requestId": f"{request_id}:formal-propose",
                    "targetId": None, "expectedRevision": None,
                    "inputRefs": []},
            "proposal": {
                "proposalId": proposal_id, "materialId": material_id,
                "baseRevision": assistant_revision, "bytesB64": clean_b64,
                "channel": CHANNEL, "author": author,
                "quotes": _quotes_for_proposal(plan, matter_id, material_id,
                                               base_revision),
                "note": note}})
        proposal_row = proposal_receipt["proposal"]

        out_dir = _next_output_dir(material_root)
        staging = out_dir.with_name(out_dir.name + ".staging")
        staging.mkdir(parents=True, exist_ok=False)
        try:
            staging.joinpath("clean.docx").write_bytes(clean_bytes)
            staging.joinpath("annotated.docx").write_bytes(annotated_bytes)
            manifest = {
                "schema": SCHEMA,
                "output_id": f"{material_id}:{out_dir.name}",
                "request_id": request_id,
                "matter_id": matter_id,
                "material_id": material_id,
                "base_revision": base_revision,
                "base_sha256": _sha256(source_bytes),
                "author": author,
                "edited_at": edited_at,
                "channel": CHANNEL,
                "edits": args["edits"],
                "edit_counts": versions["counts"],
                "clean": {"file": "clean.docx", "sha256": clean_sha,
                          "content_digest": content_digest(clean_bytes),
                          "bytes": len(clean_bytes)},
                "annotated": {
                    "file": "annotated.docx",
                    "sha256": _sha256(annotated_bytes),
                    "content_digest": content_digest(annotated_bytes),
                    "bytes": len(annotated_bytes)},
                "fidelity": fidelity,
                "harness": {
                    "assistant_edit": {
                        "revision": assistant_revision,
                        "source": revision_receipt.get("source"),
                        "sha256": revision_receipt.get("sha256"),
                        "cas_ref": revision_receipt.get("casRef"),
                        "base_revision": revision_receipt.get("baseRevision"),
                    },
                    "proposal": {
                        "proposal_id": proposal_id,
                        "state": proposal_row.get("state"),
                        "base_revision": proposal_row.get("baseRevision"),
                        "sha256": proposal_row.get("proposalSha256"),
                        "channel": proposal_row.get("channel"),
                        "quotes": len(plan["quotes"]),
                    },
                },
                "created_utc": _now_utc(),
            }
            _atomic_write(staging / "output.json", json.dumps(
                manifest, ensure_ascii=False, indent=1).encode("utf-8")
                + b"\n")
            os.replace(staging, out_dir)
        except Exception:
            import shutil
            shutil.rmtree(staging, ignore_errors=True)
            raise
        view = _public_view(manifest)
        view["replayed"] = False
        return view


def _manifest_at(state_root: Path, matter_id: str, material_id: str,
                 seq: str) -> tuple[Path, dict]:
    if not _MATTER_RE.match(matter_id) or not _MATTER_RE.match(material_id) \
            or not seq.isdigit():
        raise _fail("f45_output_id_invalid")
    path = _material_root(state_root, matter_id, material_id) / "outputs" \
        / seq / "output.json"
    if not path.is_file():
        raise _fail("f45_output_not_found")
    return path.parent, json.loads(path.read_text(encoding="utf-8"))


def _public_view(manifest: dict) -> dict:
    """桥回读面：完整清单去掉落盘时间等本地噪音字段。"""
    view = dict(manifest)
    view.pop("created_utc", None)
    return view


def list_outputs(state_root: Path, args: dict) -> dict:
    matter_id = args.get("matter_id")
    material_id = args.get("material_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.match(matter_id) \
            or not isinstance(material_id, str) \
            or not _MATTER_RE.match(material_id):
        raise _fail("f45_output_id_invalid")
    outputs = _material_root(state_root, matter_id, material_id) / "outputs"
    items = []
    if outputs.is_dir():
        for entry in sorted(outputs.iterdir()):
            manifest_path = entry / "output.json"
            if manifest_path.is_file():
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8"))
                items.append({
                    "output_id": manifest["output_id"],
                    "request_id": manifest["request_id"],
                    "base_revision": manifest["base_revision"],
                    "clean_sha256": manifest["clean"]["sha256"],
                    "annotated_sha256": manifest["annotated"]["sha256"],
                    "edit_counts": manifest["edit_counts"],
                    "proposal_id": manifest["harness"]["proposal"]
                    ["proposal_id"],
                    "proposal_state": manifest["harness"]["proposal"]
                    ["state"],
                })
    return {"schema": SCHEMA, "matter_id": matter_id,
            "material_id": material_id, "outputs": items}


def read_output(state_root: Path, args: dict) -> dict:
    seq = args.get("seq")
    want = args.get("file")
    if want not in ("clean", "annotated", None):
        raise _fail("f45_file_invalid")
    out_dir, manifest = _manifest_at(state_root, args.get("matter_id"),
                                     args.get("material_id"), seq)
    view = _public_view(manifest)
    if want is not None:
        name = manifest[want]["file"]
        payload = out_dir.joinpath(name).read_bytes()
        if _sha256(payload) != manifest[want]["sha256"]:
            raise _fail("f45_output_bytes_mismatch")
        view["docx_b64"] = base64.b64encode(payload).decode("ascii")
        view["file"] = want
    return view


def verify_output(state_root: Path, args: dict, config: dict,
                  harness_call=None) -> dict:
    """复验面：产物字节对清单＋原稿经 harness CAS 回读后独立检查器整跑。"""
    out_dir, manifest = _manifest_at(state_root, args.get("matter_id"),
                                     args.get("material_id"), args.get("seq"))
    clean = out_dir.joinpath(manifest["clean"]["file"]).read_bytes()
    annotated = out_dir.joinpath(manifest["annotated"]["file"]).read_bytes()
    if _sha256(clean) != manifest["clean"]["sha256"]:
        raise _fail("f45_output_bytes_mismatch:clean")
    if _sha256(annotated) != manifest["annotated"]["sha256"]:
        raise _fail("f45_output_bytes_mismatch:annotated")
    if harness_call is None:
        harness_call = _bridge_harness_call(config)
    source_bytes = _read_base_bytes(
        harness_call, manifest["matter_id"], manifest["material_id"],
        manifest["base_revision"])
    if _sha256(source_bytes) != manifest["base_sha256"]:
        raise _fail("f45_base_bytes_mismatch")
    model = parse_source(source_bytes)
    plan = _plan_from_manifest(manifest, model)
    fidelity = fidelity_check(source_bytes, clean, annotated, plan,
                              manifest["author"])
    return {"schema": SCHEMA, "output_id": manifest["output_id"],
            "verified": True, "fidelity": fidelity}


def _plan_from_manifest(manifest: dict, source_model: dict) -> dict:
    """清单内联编辑集→计划（与 apply 同一 plan_edits 单一路径推导）。"""
    return plan_edits(source_model, manifest["edits"])


def docx_edit_call(method: str, args: dict, config: dict,
                   harness_call=None) -> dict:
    """legal_entry docxedit.* 唯一分发（fail-closed 同基线）。

    配置级缺状态根＝NOT_CONNECTED（同全桥纪律）；业务级 typed 拒＝
    DocxEditError（f45_* 码，同 ConversionError 先例）。"""
    state_root = config.get("docx_edit_state_root")
    if not state_root:
        from bridge_errors import NotConnected
        raise NotConnected("f45_state_root_not_configured")
    if method == "docxedit.apply":
        return apply_edit(Path(state_root), config, args,
                          harness_call=harness_call)
    if method == "docxedit.outputs":
        return list_outputs(Path(state_root), args)
    if method == "docxedit.output":
        return read_output(Path(state_root), args)
    if method == "docxedit.verify":
        return verify_output(Path(state_root), args, config,
                             harness_call=harness_call)
    raise _fail("f45_method_unknown")
