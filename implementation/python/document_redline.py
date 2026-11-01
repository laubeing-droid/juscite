"""F49 干净基版与提案 replay 对比产真修订红线（W2b-U14）：产品侧
document-adapter 公开面——compareDocuments 差量语义（非会话内打标）。

义务 06:F49 / 17 卡断言：「干净基版与提案replay对比产真修订；表格/脚注/
编号有内容回读」。管线（17 卡）：公开 proposal/base refs →（本面）提案
replay 与渲染解耦 → compareDocuments 差量 → 产物红线 DOCX；宿主原生
定位/部分接受/拒绝与回流（F46/F47）不在本面。产物红线 DOCX 供
W2b-U16 WPS 宿主验证与 E13 两宿主正式 DOCX 闭环收口消费。

纪律：
- 提案 replay 与渲染解耦（06:F49「提案 replay 与渲染解耦，更稳」）：
  提案＝封闭算子集 JSON（材料面，无渲染、无模型、无网络）；replay＝把
  算子确定性地重放到干净基版副本上得 replay.docx（独立在盘工件，可单
  独检视）。红线＝对盘上两个真实文件（baseline.docx↔replay.docx）做
  compareDocuments 差量（difflib 确定性对齐），绝不回看算子——红线是
  两份字节的函数，不是算子的转写。
- 真修订（不模拟 DOCX）：红线文档携带真 OOXML 修订标记——w:ins/w:del
  （内联增删，w:delText 口径）、段标记增删（w:pPr/w:rPr/w:ins|w:del）、
  行级增删（w:trPr/w:ins|w:del）、属性变更（w:pPrChange 携旧 pPr）。
- 对账双不变式（不过不出红线）：accept_all(红线)==replay 事实 且
  reject_all(红线)==baseline 事实（正文/表格/脚注/编号四类事实）。
- 内容回读：修订清单从**产物红线 DOCX 本身**回读（解析修订标记得
  category/location/inserted_text/deleted_text），不是从 diff 中间量抄。
- 干净基版闸：基版含既有修订标记（w:ins/w:del/w:pPrChange 等）→ 具名
  拒（干净基版语义）；含文本框/图形/域/批注/math/sdt 等本模型外构件 →
  具名拒（f49_baseline_unsupported_construct:*，fail-closed 不静默丢）。
  F54 LibreOffice 候选（文本框结构）如实被拒；纯文本重建候选（平铺
  OOXML）可入修订线。
- 确定性：无模型/无网络/无时钟入 XML（w:author/w:date＝提案声明的
  author/authored_utc 透传）；zip 定时间戳固定→同输入字节级同输出，
  跨 profile 同摘要。修订作者不伪装律师（F53 前置：默认 lvyin-redline）。

fail-closed：typed error（f49_* 错误码，绝不携材料内容）。状态根同
F54 纪律（TEMP/显式配置，绝不写 %APPDATA%）。
"""
from __future__ import annotations

import base64
import copy
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

SCHEMA = "juscite-f49-replay-redline/1"
PROPOSAL_SCHEMA = "juscite-f49-replay-proposal/1"
STATE_SUBDIR = "document-redline"
# 封闭算子集（06:F49 材料面；一行一算子，顺序重放）
OP_NAMES = (
    "body.replace_text",        # 正文段文本替换（保留非文本 run 如脚注引用）
    "body.insert_paragraph",    # 正文段前插入新段（文本须非空）
    "body.delete_paragraph",    # 删正文段
    "table.cell_text",          # 表格单元格文本替换
    "table.insert_row",         # 行前插入行（cells 须与网格列数一致）
    "table.delete_row",         # 删行
    "footnote.replace_text",    # 脚注文本替换
    "para.numbering_set",       # 段编号引用设置（numId 或 null=清除）
)
# 红线产物消费方（契约声明；验证属各自工单）
REDLINE_CONSUMERS = ("W2b-U16-wps-host", "E13-docx-closeout")
DEFAULT_AUTHOR = "lvyin-redline"
# 基版模型外构件（黑名单口径：破坏 diff/文本模型的承载结构；未列构件
# 原样携带不丢）。LibreOffice Writer PDF 导入的文本框结构在此如实被拒。
_UNSUPPORTED_CONSTRUCTS = frozenset({
    "AlternateContent", "Fallback", "Choice", "drawing", "pict", "object",
    "fldSimple", "fldChar", "instrText", "commentReference",
    "commentRangeStart", "commentRangeEnd", "math", "sdt", "sdtContent",
    "hyperlink", "smartTag", "txbxContent",
})
_EXISTING_REVISION_MARKS = frozenset({
    "ins", "del", "pPrChange", "rPrChange", "trPrChange", "tcPrChange",
    "tblPrChange", "sectPrChange", "moveFrom", "moveTo", "celMerge",
    "rowMerge", "delText",
})
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = "{%s}" % _W_NS
_MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
_DOC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PROP_DIR_RE = re.compile(r"^\d{4}-replay$")
_RED_DIR_RE = re.compile(r"^\d{4}-compare$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

_LOCK = threading.Lock()


class RedlineError(ValueError):
    """Typed F49 face failure; str() is a code, never material content."""

    error_code = "f49_invalid"


def _fail(code: str) -> RedlineError:
    return RedlineError(code)


# --------------------------------------------------------------------------
# OOXML 包读取/确定性序列化（包级复制＋选择性部件替换）
# --------------------------------------------------------------------------

def _read_package_bytes(raw: bytes) -> dict:
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise _fail("f49_docx_unreadable:" + type(exc).__name__) from None
    with zf:
        parts = {info.filename: zf.read(info.filename)
                 for info in zf.infolist()}
        order = [info.filename for info in zf.infolist()]
    if "word/document.xml" not in parts:
        raise _fail("f49_document_part_missing")
    trees: dict = {}
    for name in ("word/document.xml", "word/footnotes.xml",
                 "word/numbering.xml"):
        if name in parts:
            try:
                trees[name] = ET.fromstring(parts[name])
            except ET.ParseError as exc:
                raise _fail("f49_part_invalid:" + name) from None
    return {"raw": raw, "parts": parts, "order": order, "trees": trees}


def _read_package(source) -> dict:
    try:
        raw = Path(source).read_bytes()
    except OSError:
        raise _fail("f49_docx_not_found") from None
    return _read_package_bytes(raw)


def _part_ns_declarations(raw_part: bytes) -> list:
    out = []
    try:
        for _event, pair in ET.iterparse(io.BytesIO(raw_part),
                                         events=["start-ns"]):
            out.append(pair)
    except ET.ParseError:
        pass
    return out


def _serialize_tree(tree: ET.Element, original_part: bytes) -> bytes:
    """确定性序列化：保留原部件全部命名空间声明（未用到的以 xmlns:*
    属性补回根，防 mc:Ignorable 指向被 ET 丢弃的前缀）。"""
    decls = _part_ns_declarations(original_part)
    for prefix, uri in decls:
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass
    used = set()
    for elem in tree.iter():
        if isinstance(elem.tag, str) and elem.tag.startswith("{"):
            used.add(elem.tag[1:].split("}", 1)[0])
        for key in elem.attrib:
            if isinstance(key, str) and key.startswith("{"):
                used.add(key[1:].split("}", 1)[0])
    for prefix, uri in decls:
        if uri not in used:
            attr = "xmlns" if prefix == "" else "xmlns:" + prefix
            if attr not in tree.attrib:
                tree.set(attr, uri)
    body = ET.tostring(tree, encoding="utf-8", xml_declaration=False)
    return (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
            + body)


def _write_package(out_path: Path, base_parts: dict, base_order: list,
                   replacements: dict) -> None:
    """包级复制＋选择性部件替换；zip 时间戳固定→字节级确定。"""
    tmp = out_path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        seen = set()
        for name in base_order:
            seen.add(name)
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zf.writestr(info, replacements.get(name, base_parts[name]))
        for name, payload in replacements.items():   # 新部件追加（尾部）
            if name not in seen:
                info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                zf.writestr(info, payload)
    os.replace(tmp, out_path)


def docx_content_digest(docx_path) -> str:
    """部件级内容摘要（同 F54 口径：zip 容器时间戳不参与）。"""
    with zipfile.ZipFile(Path(docx_path)) as zf:
        parts = [f"{i.filename}:{hashlib.sha256(zf.read(i.filename)).hexdigest()}"
                 for i in zf.infolist()]
    return hashlib.sha256("\n".join(sorted(parts)).encode("utf-8")).hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# 文档模型（干净基版闸＋四类事实抽取）
# --------------------------------------------------------------------------

def _gate_tree_clean(tree, part_label: str) -> None:
    if tree is None:                      # 无该部件＝无非法构件
        return
    for elem in tree.iter():
        tag = elem.tag
        if not isinstance(tag, str):
            continue                      # 注释/PI：原样携带不参与模型
        local = tag.split("}", 1)[-1]
        if local in _EXISTING_REVISION_MARKS:
            raise _fail("f49_baseline_has_existing_revisions:"
                        + part_label + local)
        if tag.startswith("{%s}" % _MC_NS) or local in \
                _UNSUPPORTED_CONSTRUCTS:
            raise _fail("f49_baseline_unsupported_construct:"
                        + part_label + local)


def _body_children(tree: ET.Element) -> list:
    body = tree.find(_W + "body")
    if body is None:
        raise _fail("f49_body_missing")
    return list(body)


def _body_paragraphs(tree: ET.Element) -> list:
    return [c for c in _body_children(tree) if c.tag == _W + "p"]


def _tables(tree: ET.Element) -> list:
    return [c for c in _body_children(tree) if c.tag == _W + "tbl"]


def _rows(tbl: ET.Element) -> list:
    return [c for c in tbl if c.tag == _W + "tr"]


def _cells(tr: ET.Element) -> list:
    return [c for c in tr if c.tag == _W + "tc"]


def _paragraph_text(p: ET.Element) -> str:
    out = []
    for r in p.findall(_W + "r"):
        for t in r.findall(_W + "t"):
            out.append(t.text or "")
    return "".join(out)


def _cell_text(tc: ET.Element) -> str:
    return "\n".join(_paragraph_text(p) for p in tc.findall(_W + "p")).strip()


def _numbering_map(numbering_tree) -> dict:
    """numId→[(ilvl, numFmt, lvlText)] 解析表（事实只读，不改动部件）。"""
    if numbering_tree is None:
        return {}
    abstract = {}
    for an in numbering_tree.findall(_W + "abstractNum"):
        lvls = []
        for lvl in an.findall(_W + "lvl"):
            fmt = lvl.find(_W + "numFmt")
            text = lvl.find(_W + "lvlText")
            lvls.append((lvl.get(_W + "ilvl", "0"),
                         fmt.get(_W + "val") if fmt is not None else None,
                         text.get(_W + "val") if text is not None else None))
        abstract[an.get(_W + "abstractNumId")] = lvls
    out = {}
    for num in numbering_tree.findall(_W + "num"):
        nid = num.get(_W + "numId")
        ref = num.find(_W + "abstractNumId")
        if nid is not None and ref is not None:
            out[nid] = abstract.get(ref.get(_W + "val"))
    return out


def _para_numbering(p: ET.Element):
    ppr = p.find(_W + "pPr")
    if ppr is None:
        return None
    numpr = ppr.find(_W + "numPr")
    if numpr is None:
        return None
    nid = numpr.find(_W + "numId")
    if nid is None:
        return None
    ilvl = numpr.find(_W + "ilvl")
    return {"num_id": nid.get(_W + "val"),
            "ilvl": ilvl.get(_W + "val", "0") if ilvl is not None else "0"}


def _footnote_entries(footnotes_tree) -> dict:
    """真脚注（排除 separator/continuationSeparator）: id→w:footnote。"""
    if footnotes_tree is None:
        return {}
    out = {}
    for fn in footnotes_tree.findall(_W + "footnote"):
        if fn.get(_W + "type") in ("separator", "continuationSeparator"):
            continue
        out[fn.get(_W + "id")] = fn
    return out


def extract_facts(document_tree: ET.Element, footnotes_tree,
                  numbering_tree=None) -> dict:
    """四类事实：正文段序列/段编号/表格网格/脚注文本。对账口径唯一。"""
    numap = _numbering_map(numbering_tree)
    body = []
    numbering = []
    for p in _body_paragraphs(document_tree):
        body.append(_paragraph_text(p))
        num = _para_numbering(p)
        if num is None:
            numbering.append(None)
        else:
            lvls = numap.get(num["num_id"]) or []
            fmt = next((f for i, f, _t in lvls if i == num["ilvl"]), None)
            numbering.append({"num_id": num["num_id"],
                              "ilvl": num["ilvl"], "num_fmt": fmt})
    tables = [[[_cell_text(tc) for tc in _cells(tr)]
               for tr in _rows(tbl)]
              for tbl in _tables(document_tree)]
    footnotes = {}
    for fid, fn in _footnote_entries(footnotes_tree).items():
        footnotes[fid] = "\n".join(_paragraph_text(p)
                                   for p in fn.findall(_W + "p")).strip()
    return {"body": body, "numbering": numbering, "tables": tables,
            "footnotes": footnotes}


def facts_digest(facts: dict) -> str:
    return hashlib.sha256(json.dumps(
        facts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _facts_view(facts: dict) -> dict:
    return {"body_paragraphs": len(facts["body"]),
            "tables": len(facts["tables"]),
            "footnotes": len(facts["footnotes"]),
            "numbered_paragraphs": sum(1 for n in facts["numbering"]
                                       if n is not None),
            "facts_digest": facts_digest(facts)}


# --------------------------------------------------------------------------
# 提案（封闭算子集）与 replay（渲染解耦：算子→确定性重放）
# --------------------------------------------------------------------------

def _author_policy_gate(channel: str, author: str) -> None:
    """F53 收拢（W2b-U49）：机器通道修订作者过 author_policy 策略面——
    闭集外作者（含律师名）＝f53_author_impersonation 具名拒；错绑＝
    f53_author_channel_mismatch。f53 码落本面 typed 错误族透传。"""
    from author_policy import check_revision_author, AuthorPolicyError
    try:
        check_revision_author(channel, author)
    except AuthorPolicyError as exc:
        raise _fail(str(exc)) from None


def _validate_proposal(proposal) -> dict:
    if not isinstance(proposal, dict):
        raise _fail("f49_proposal_invalid")
    author = proposal.get("author") or DEFAULT_AUTHOR
    if not isinstance(author, str) or not (1 <= len(author) <= 64):
        raise _fail("f49_proposal_author_invalid")
    authored = proposal.get("authored_utc")
    if not isinstance(authored, str) or not _UTC_RE.match(authored):
        raise _fail("f49_proposal_authored_utc_invalid")
    ops = proposal.get("ops")
    if not isinstance(ops, list) or not ops:
        raise _fail("f49_proposal_ops_required")
    norm = []
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in OP_NAMES:
            raise _fail("f49_proposal_op_unknown")
        if op.get("op") == "body.insert_paragraph" \
                and not (isinstance(op.get("text"), str) and op["text"]):
            raise _fail("f49_proposal_op_invalid:body.insert_paragraph")
        norm.append(dict(op))
    # F53 收拢（W2b-U49）：提案作者过 author_policy 策略面——闭集外作者
    # （含律师名）＝f53_author_impersonation 具名拒。形参/算子校验在前，
    # 既有 f49 负向码不变。
    _author_policy_gate("redline", author)
    return {"schema": PROPOSAL_SCHEMA, "author": author,
            "authored_utc": authored, "ops": norm}


def _text_run(text: str, rpr_template) -> ET.Element:
    run = ET.Element(_W + "r")
    if rpr_template is not None:
        run.append(copy.deepcopy(rpr_template))
    t = ET.SubElement(run, _W + "t")
    t.set(_XML_SPACE, "preserve")
    t.text = text
    return run


def _first_rpr(p: ET.Element):
    for r in p.findall(_W + "r"):
        rpr = r.find(_W + "rPr")
        if rpr is not None:
            return rpr
    return None


def _replace_paragraph_text(p: ET.Element, text: str) -> None:
    """替换段文本：只删文本 run，保留非文本 run（脚注引用/分页符等）；
    新文本 run 落在首个文本 run 原位（无则追加）。"""
    children = list(p)
    text_idx = [i for i, c in enumerate(children)
                if c.tag == _W + "r" and c.find(_W + "t") is not None]
    rpr = _first_rpr(p)
    new_run = _text_run(text, rpr)
    if not text_idx:
        p.append(new_run)
        return
    insert_at = text_idx[0]
    for i in reversed(text_idx):
        p.remove(children[i])
    p.insert(insert_at, new_run)


def _clear_extra_paragraphs(ps: list) -> None:
    """多段容器（单元格/脚注）：首段之外的段清空文本 run（段保留）。"""
    for extra in ps[1:]:
        for run in list(extra.findall(_W + "r")):
            if run.find(_W + "t") is not None:
                extra.remove(run)


def _apply_op(doc: dict, op: dict) -> None:
    name = op["op"]
    doc_tree = doc["trees"]["word/document.xml"]
    fn_tree = doc["trees"].get("word/footnotes.xml")
    body = doc_tree.find(_W + "body")

    if name in ("body.replace_text", "body.insert_paragraph",
                "body.delete_paragraph", "para.numbering_set"):
        paras = _body_paragraphs(doc_tree)
        i = op.get("index")
        if not isinstance(i, int) or isinstance(i, bool):
            raise _fail("f49_op_target_missing:" + name)
        if name == "body.insert_paragraph":
            if not (0 <= i <= len(paras)):
                raise _fail("f49_op_target_missing:" + name)
            text = op.get("text")
            if not isinstance(text, str) or not text:
                raise _fail("f49_proposal_op_invalid:body.insert_paragraph")
            new_p = ET.Element(_W + "p")
            new_p.append(_text_run(text, None))
            anchor = paras[i] if i < len(paras) else None
            if anchor is None:
                sect = body.find(_W + "sectPr")
                if sect is not None:
                    body.insert(list(body).index(sect), new_p)
                else:
                    body.append(new_p)
            else:
                body.insert(list(body).index(anchor), new_p)
            return
        if not (0 <= i < len(paras)):
            raise _fail("f49_op_target_missing:" + name)
        if name == "body.replace_text":
            text = op.get("text")
            if not isinstance(text, str):
                raise _fail("f49_proposal_op_invalid:body.replace_text")
            _replace_paragraph_text(paras[i], text)
            return
        if name == "body.delete_paragraph":
            body.remove(paras[i])
            return
        # para.numbering_set
        num_id = op.get("num_id")
        if num_id is not None:
            numbering = doc["trees"].get("word/numbering.xml")
            if numbering is None or str(num_id) not in _numbering_map(
                    numbering):
                raise _fail("f49_op_numbering_unknown")
        p = paras[i]
        ppr = p.find(_W + "pPr")
        if num_id is None:
            if ppr is not None:
                numpr = ppr.find(_W + "numPr")
                if numpr is not None:
                    ppr.remove(numpr)
            return
        if ppr is None:
            ppr = ET.Element(_W + "pPr")
            p.insert(0, ppr)
        old = ppr.find(_W + "numPr")
        if old is not None:
            ppr.remove(old)
        numpr = ET.Element(_W + "numPr")
        ET.SubElement(numpr, _W + "ilvl").set(_W + "val", "0")
        ET.SubElement(numpr, _W + "numId").set(_W + "val", str(num_id))
        rpr = ppr.find(_W + "rPr")
        if rpr is not None:
            ppr.insert(list(ppr).index(rpr), numpr)
        else:
            ppr.append(numpr)
        return

    if name.startswith("table."):
        tables = _tables(doc_tree)
        t = op.get("table")
        if not isinstance(t, int) or isinstance(t, bool) \
                or not (0 <= t < len(tables)):
            raise _fail("f49_op_target_missing:table:" + name)
        rows = _rows(tables[t])
        if name == "table.cell_text":
            r, c, text = op.get("row"), op.get("col"), op.get("text")
            if not isinstance(r, int) or not (0 <= r < len(rows)) \
                    or not isinstance(text, str):
                raise _fail("f49_op_target_missing:table.cell_text")
            cells = _cells(rows[r])
            if not isinstance(c, int) or not (0 <= c < len(cells)):
                raise _fail("f49_op_target_missing:table.cell_text")
            ps = cells[c].findall(_W + "p")
            if ps:
                _replace_paragraph_text(ps[0], text)
                _clear_extra_paragraphs(ps)
            else:
                new_p = ET.Element(_W + "p")
                new_p.append(_text_run(text, None))
                cells[c].append(new_p)
            return
        if name == "table.insert_row":
            r, cells_spec = op.get("row"), op.get("cells")
            if not isinstance(r, int) or not (0 <= r <= len(rows)) \
                    or not isinstance(cells_spec, list) or not cells_spec \
                    or not all(isinstance(x, str) for x in cells_spec):
                raise _fail("f49_op_target_missing:table.insert_row")
            width = len(_cells(rows[0])) if rows else len(cells_spec)
            if len(cells_spec) != width:
                raise _fail("f49_op_cells_mismatch")
            new_tr = ET.Element(_W + "tr")
            template_tcpr = None
            if rows and _cells(rows[0]):
                template_tcpr = _cells(rows[0])[0].find(_W + "tcPr")
            for text in cells_spec:
                tc = ET.Element(_W + "tc")
                if template_tcpr is not None:
                    tc.append(copy.deepcopy(template_tcpr))
                cell_p = ET.Element(_W + "p")
                cell_p.append(_text_run(text, None))
                tc.append(cell_p)
                new_tr.append(tc)
            if r < len(rows):
                tables[t].insert(list(tables[t]).index(rows[r]), new_tr)
            else:
                tables[t].append(new_tr)
            return
        if name == "table.delete_row":
            r = op.get("row")
            if not isinstance(r, int) or not (0 <= r < len(rows)):
                raise _fail("f49_op_target_missing:table.delete_row")
            tables[t].remove(rows[r])
            return

    if name == "footnote.replace_text":
        fid, text = op.get("id"), op.get("text")
        if not isinstance(fid, int) or isinstance(fid, bool) \
                or not isinstance(text, str):
            raise _fail("f49_op_target_missing:footnote.replace_text")
        fn = _footnote_entries(fn_tree).get(str(fid))
        if fn is None:
            raise _fail("f49_op_target_missing:footnote:" + str(fid))
        ps = fn.findall(_W + "p")
        if ps:
            _replace_paragraph_text(ps[0], text)
            _clear_extra_paragraphs(ps)
        else:
            new_p = ET.Element(_W + "p")
            new_p.append(_text_run(text, None))
            fn.append(new_p)
        return

    raise _fail("f49_proposal_op_unknown")


def _replay_to_parts(baseline: dict, proposal_norm: dict) -> dict:
    """重放：基线包副本上按序应用算子→替换部件字节（独立在盘工件）。"""
    doc = {"parts": dict(baseline["parts"]),
           "order": list(baseline["order"]),
           "trees": {k: copy.deepcopy(v)
                     for k, v in baseline["trees"].items()}}
    for op in proposal_norm["ops"]:
        _apply_op(doc, op)
    replacements = {
        "word/document.xml": _serialize_tree(
            doc["trees"]["word/document.xml"],
            baseline["parts"]["word/document.xml"])}
    if "word/footnotes.xml" in doc["trees"]:
        replacements["word/footnotes.xml"] = _serialize_tree(
            doc["trees"]["word/footnotes.xml"],
            baseline["parts"]["word/footnotes.xml"])
    return replacements


# --------------------------------------------------------------------------
# compareDocuments 差量 → 真修订红线
# --------------------------------------------------------------------------

class _RevisionIds:
    def __init__(self):
        self.next = 1001

    def take(self) -> str:
        value = str(self.next)
        self.next += 1
        return value


def _diff_segments(old: str, new: str) -> list:
    """字符级差量段：[("keep"|"del"|"ins", text), ...]（确定性）。"""
    if old == new:
        return [("keep", old)] if old else []
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            out.append(("keep", old[i1:i2]))
        else:
            if i1 < i2:
                out.append(("del", old[i1:i2]))
            if j1 < j2:
                out.append(("ins", new[j1:j2]))
    return out


def _mk_rev(kind: str, author: str, date: str, ids: _RevisionIds
            ) -> ET.Element:
    el = ET.Element(_W + kind)
    el.set(_W + "id", ids.take())
    el.set(_W + "author", author)
    el.set(_W + "date", date)
    return el


def _run_of(text: str, tagname: str, rpr) -> ET.Element:
    run = ET.Element(_W + "r")
    if rpr is not None:
        run.append(copy.deepcopy(rpr))
    t = ET.SubElement(run, _W + tagname)
    t.set(_XML_SPACE, "preserve")
    t.text = text
    return run


def _mark_paragraph_replaced(p: ET.Element, old_text: str, new_text: str,
                              author: str, date: str,
                              ids: _RevisionIds) -> None:
    """在基线段落上打真修订：文本 run 区替换为 keep/del/ins 段；非文本
    run（脚注引用/br）原位保留。"""
    segments = _diff_segments(old_text, new_text)
    if not segments:
        return
    text_runs = [c for c in list(p) if c.tag == _W + "r"
                 and c.find(_W + "t") is not None]
    rpr = _first_rpr(p)
    insert_at = list(p).index(text_runs[0]) if text_runs else len(list(p))
    built = []
    for kind, seg_text in segments:
        if not seg_text:
            continue
        if kind == "keep":
            built.append(_run_of(seg_text, "t", rpr))
        elif kind == "del":
            holder = _mk_rev("del", author, date, ids)
            holder.append(_run_of(seg_text, "delText", rpr))
            built.append(holder)
        else:
            holder = _mk_rev("ins", author, date, ids)
            holder.append(_run_of(seg_text, "t", rpr))
            built.append(holder)
    for run in text_runs:
        p.remove(run)
    for offset, el in enumerate(built):
        p.insert(insert_at + offset, el)


def _paragraph_mark(p: ET.Element, kind: str, author: str, date: str,
                    ids: _RevisionIds) -> None:
    """段标记修订（插入段/删除段）：w:pPr/w:rPr/w:ins|w:del。"""
    ppr = p.find(_W + "pPr")
    if ppr is None:
        ppr = ET.Element(_W + "pPr")
        p.insert(0, ppr)
    rpr = ppr.find(_W + "rPr")
    if rpr is None:
        rpr = ET.Element(_W + "rPr")
        ppr.append(rpr)
    rpr.append(_mk_rev(kind, author, date, ids))


def _wrap_runs(p: ET.Element, kind: str, author: str, date: str,
               ids: _RevisionIds) -> None:
    """插入侧：文本 run 包进 w:ins；删除侧：w:t→w:delText 后包进 w:del。"""
    for run in list(p.findall(_W + "r")):
        if run.find(_W + "t") is None:
            continue
        if kind == "del":
            run.find(_W + "t").tag = _W + "delText"
        holder = _mk_rev(kind, author, date, ids)
        idx = list(p).index(run)
        p.remove(run)
        p.insert(idx, holder)
        holder.append(run)


def _trpr_rev(tr: ET.Element, kind: str, author: str, date: str,
              ids: _RevisionIds) -> None:
    trpr = tr.find(_W + "trPr")
    if trpr is None:
        trpr = ET.Element(_W + "trPr")
        tr.insert(0, trpr)
    trpr.append(_mk_rev(kind, author, date, ids))


def _ppr_equal(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return ET.tostring(a) == ET.tostring(b)


def _apply_ppr_change(p_base: ET.Element, p_replay: ET.Element,
                      author: str, date: str, ids: _RevisionIds) -> None:
    """属性变更（编号等）：当前 pPr←replay 版；w:pPrChange 携旧 pPr 内容。"""
    old_ppr = p_base.find(_W + "pPr")
    new_ppr = p_replay.find(_W + "pPr")
    if _ppr_equal(old_ppr, new_ppr):
        return
    change = ET.Element(_W + "pPrChange")
    change.set(_W + "id", ids.take())
    change.set(_W + "author", author)
    change.set(_W + "date", date)
    if old_ppr is not None:
        if new_ppr is None:
            # 属性整删（本封闭算子集不产生该形态）——如实拒，不猜
            raise _fail("f49_compare_ppr_removed_unsupported")
        for child in list(old_ppr):
            change.append(child)           # 旧 pPr 内容移入 pPrChange
    if new_ppr is not None:
        fresh = copy.deepcopy(new_ppr)
        if old_ppr is not None:
            p_base.remove(old_ppr)
        p_base.insert(0, fresh)
    ppr_now = p_base.find(_W + "pPr")
    ppr_now.append(change)                 # pPrChange 规范位置＝pPr 末位


def _align(a_items: list, b_items: list) -> list:
    """确定性对齐（compareDocuments 差量核心）：[(opcode, a_idx, b_idx)]；
    replace 逐位配对，余量成 insert/delete；每侧每个下标恰出现一次。"""
    pairs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, a_items, b_items, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                pairs.append(("equal", i1 + k, j1 + k))
        else:
            for k in range(max(i2 - i1, j2 - j1)):
                a_idx = i1 + k if k < i2 - i1 else None
                b_idx = j1 + k if k < j2 - j1 else None
                pairs.append(("pair", a_idx, b_idx))
    return pairs


def build_redline(baseline: dict, replay_pkg: dict, author: str, date: str
                  ) -> dict:
    """从两份盘上包差量产真修订红线（返回替换部件字节）。"""
    ids = _RevisionIds()
    b_doc = copy.deepcopy(baseline["trees"]["word/document.xml"])
    b_fn = copy.deepcopy(baseline["trees"]["word/footnotes.xml"]) \
        if "word/footnotes.xml" in baseline["trees"] else None
    r_doc = replay_pkg["trees"]["word/document.xml"]
    r_fn = replay_pkg["trees"].get("word/footnotes.xml")
    body_el = b_doc.find(_W + "body")

    # ---- 正文段对齐与标记（段槽锚定：非段元素原位穿越）----
    b_paras = _body_paragraphs(b_doc)
    r_paras = _body_paragraphs(r_doc)
    b_texts = [_paragraph_text(p) for p in b_paras]
    r_texts = [_paragraph_text(p) for p in r_paras]

    transformed: dict = {}          # 基线段序号→已标记元素
    pre_slot: dict = {}             # 基线段序号→[先于该段发射的插入段]
    pending_ins: list = []
    for opcode, a_idx, b_idx in _align(b_texts, r_texts):
        if a_idx is not None:
            pre_slot.setdefault(a_idx, []).extend(pending_ins)
            pending_ins = []
            p_base = b_paras[a_idx]
            if b_idx is not None:
                if opcode == "pair":
                    _mark_paragraph_replaced(p_base, b_texts[a_idx],
                                             r_texts[b_idx], author, date,
                                             ids)
                _apply_ppr_change(p_base, r_paras[b_idx], author, date, ids)
            else:
                _wrap_runs(p_base, "del", author, date, ids)
                _paragraph_mark(p_base, "del", author, date, ids)
            transformed[a_idx] = p_base
        else:
            p_new = copy.deepcopy(r_paras[b_idx])
            _wrap_runs(p_new, "ins", author, date, ids)
            _paragraph_mark(p_new, "ins", author, date, ids)
            pending_ins.append(p_new)

    new_children = []
    para_ordinal = 0
    for child in list(body_el):
        if child.tag == _W + "p":
            for el in pre_slot.get(para_ordinal, []):
                new_children.append(el)
            new_children.append(transformed.get(para_ordinal, child))
            para_ordinal += 1
        else:
            new_children.append(child)
    if pending_ins:                  # 尾部插入段：落在 sectPr 前（无则末尾）
        sect_idx = next((i for i, el in enumerate(new_children)
                         if el.tag == _W + "sectPr"), None)
        for offset, el in enumerate(pending_ins):
            if sect_idx is None:
                new_children.append(el)
            else:
                new_children.insert(sect_idx + offset, el)
    for child in list(body_el):
        body_el.remove(child)
    for child in new_children:
        body_el.append(child)

    # ---- 表格（行对齐；表数不变——整表增删不属本封闭集）----
    b_tables = _tables(b_doc)
    r_tables = _tables(r_doc)
    if len(b_tables) != len(r_tables):
        raise _fail("f49_compare_table_count_changed")
    for b_tbl, r_tbl in zip(b_tables, r_tables):
        b_rows = _rows(b_tbl)
        r_rows = _rows(r_tbl)
        b_sig = [tuple(_cell_text(tc) for tc in _cells(tr)) for tr in b_rows]
        r_sig = [tuple(_cell_text(tc) for tc in _cells(tr)) for tr in r_rows]
        new_trs = []
        for opcode, a_idx, b_idx in _align(b_sig, r_sig):
            if a_idx is not None:
                tr = b_rows[a_idx]
                if b_idx is not None:
                    for b_tc, r_tc in zip(_cells(tr), _cells(r_rows[b_idx])):
                        old_cell = _cell_text(b_tc)
                        new_cell = _cell_text(r_tc)
                        if old_cell == new_cell:
                            continue
                        ps = b_tc.findall(_W + "p")
                        if not ps:
                            continue
                        _mark_paragraph_replaced(
                            ps[0], _paragraph_text(ps[0]), new_cell,
                            author, date, ids)
                        for extra in ps[1:]:
                            _wrap_runs(extra, "del", author, date, ids)
                else:
                    _trpr_rev(tr, "del", author, date, ids)
                    for tc in _cells(tr):
                        for p in tc.findall(_W + "p"):
                            _wrap_runs(p, "del", author, date, ids)
                new_trs.append(tr)
            else:
                tr = copy.deepcopy(r_rows[b_idx])
                _trpr_rev(tr, "ins", author, date, ids)
                for tc in _cells(tr):
                    for p in tc.findall(_W + "p"):
                        _wrap_runs(p, "ins", author, date, ids)
                new_trs.append(tr)
        tr_iter = iter(new_trs)
        new_tbl_children = []
        for child in list(b_tbl):
            if child.tag == _W + "tr":
                new_tbl_children.append(next(tr_iter))
            else:
                new_tbl_children.append(child)
        for leftover in tr_iter:
            new_tbl_children.append(leftover)
        for child in list(b_tbl):
            b_tbl.remove(child)
        for child in new_tbl_children:
            b_tbl.append(child)

    # ---- 脚注（按 id 对齐；脚注集合增删不属本封闭集）----
    if b_fn is not None:
        b_entries = _footnote_entries(b_fn)
        r_entries = _footnote_entries(r_fn) if r_fn is not None else {}
        if set(b_entries) != set(r_entries):
            raise _fail("f49_compare_footnote_set_changed")
        for fid in sorted(b_entries, key=lambda x: int(x)):
            b_ps = b_entries[fid].findall(_W + "p")
            r_ps = r_entries[fid].findall(_W + "p")
            old_text = "\n".join(_paragraph_text(p) for p in b_ps).strip()
            new_text = "\n".join(_paragraph_text(p) for p in r_ps).strip()
            if old_text == new_text:
                continue
            if b_ps:
                _mark_paragraph_replaced(b_ps[0], _paragraph_text(b_ps[0]),
                                         new_text, author, date, ids)
                for extra in b_ps[1:]:
                    _wrap_runs(extra, "del", author, date, ids)

    replacements = {"word/document.xml": _serialize_tree(
        b_doc, baseline["parts"]["word/document.xml"])}
    if b_fn is not None:
        replacements["word/footnotes.xml"] = _serialize_tree(
            b_fn, baseline["parts"]["word/footnotes.xml"])
    return replacements


# --------------------------------------------------------------------------
# accept_all / reject_all（对账双不变式的确定性变换）
# --------------------------------------------------------------------------

def _parent_of(root: ET.Element, target: ET.Element):
    for par in root.iter():
        if target in list(par):
            return par
    return None


def _settle_paragraph_marks(root: ET.Element, accept: bool) -> None:
    """段标记处置：accept——标记删除的段整段删、标记插入的段去标保留；
    reject——标记插入的段整段删、标记删除的段去标保留。"""
    for p in list(root.iter(_W + "p")):
        ppr = p.find(_W + "pPr")
        if ppr is None:
            continue
        rpr = ppr.find(_W + "rPr")
        if rpr is None:
            continue
        gone_mark = rpr.find(_W + "del" if accept else _W + "ins")
        keep_mark = rpr.find(_W + "ins" if accept else _W + "del")
        if gone_mark is not None:
            parent = _parent_of(root, p)
            if parent is not None:
                parent.remove(p)
            continue
        if keep_mark is not None:
            rpr.remove(keep_mark)


def _settle_table_rows(root: ET.Element, accept: bool) -> None:
    for tr in list(root.iter(_W + "tr")):
        trpr = tr.find(_W + "trPr")
        if trpr is None:
            continue
        gone = trpr.find(_W + "del" if accept else _W + "ins")
        keep = trpr.find(_W + "ins" if accept else _W + "del")
        if gone is not None:
            parent = _parent_of(root, tr)
            if parent is not None:
                parent.remove(tr)
        elif keep is not None:
            trpr.remove(keep)


def _accept_all(root: ET.Element) -> None:
    _settle_paragraph_marks(root, accept=True)
    _settle_table_rows(root, accept=True)
    for ins in list(root.iter(_W + "ins")):     # 内联插入：解包保留内容
        parent = _parent_of(root, ins)
        if parent is None:
            continue
        idx = list(parent).index(ins)
        for child in list(ins):
            parent.insert(idx, child)
            idx += 1
        parent.remove(ins)
    for dele in list(root.iter(_W + "del")):    # 内联删除：内容随之删除
        parent = _parent_of(root, dele)
        if parent is not None:
            parent.remove(dele)
    for change in list(root.iter(_W + "pPrChange")):
        ppr = _parent_of(root, change)
        if ppr is not None:
            ppr.remove(change)


def _reject_all(root: ET.Element) -> None:
    _settle_paragraph_marks(root, accept=False)
    _settle_table_rows(root, accept=False)
    for ins in list(root.iter(_W + "ins")):     # 内联插入：整体撤销
        parent = _parent_of(root, ins)
        if parent is not None:
            parent.remove(ins)
    for dele in list(root.iter(_W + "del")):    # 内联删除：解包恢复内容
        parent = _parent_of(root, dele)
        if parent is None:
            continue
        idx = list(parent).index(dele)
        for child in list(dele):
            parent.insert(idx, child)
            idx += 1
        parent.remove(dele)
    for t in list(root.iter(_W + "delText")):
        t.tag = _W + "t"
    for change in list(root.iter(_W + "pPrChange")):
        ppr = _parent_of(root, change)
        if ppr is None:
            continue
        ppr.clear()                             # 旧 pPr 内容整体恢复
        for child in list(change):
            ppr.append(child)


# --------------------------------------------------------------------------
# 产物红线回读（修订清单从红线文档本身解析——内容回读本体）
# --------------------------------------------------------------------------

def read_revisions(redline_docx) -> dict:
    pkg = _read_package(redline_docx)
    doc_tree = pkg["trees"]["word/document.xml"]
    fn_tree = pkg["trees"].get("word/footnotes.xml")
    revisions: list = []

    def _row_marked(tr) -> str | None:
        trpr = tr.find(_W + "trPr")
        if trpr is None:
            return None
        if trpr.find(_W + "ins") is not None:
            return "ins"
        if trpr.find(_W + "del") is not None:
            return "del"
        return None

    def _locate(p: ET.Element) -> dict:
        for tbl_idx, tbl in enumerate(_tables(doc_tree)):
            for r_idx, tr in enumerate(_rows(tbl)):
                for c_idx, tc in enumerate(_cells(tr)):
                    if any(par is p for par in tc.findall(_W + "p")):
                        return {"table": tbl_idx, "row": r_idx, "col": c_idx}
        for i, par in enumerate(_body_paragraphs(doc_tree)):
            if par is p:
                return {"para": i}
        return {}

    def _cell_all_text(tc: ET.Element) -> str:
        """行级修订的格内容回读：w:t＋w:delText 全取（删除行内容在
        delText 里、插入行 run 在 w:ins 里——一律可读）。"""
        parts = []
        for par in tc.findall(_W + "p"):
            seg = []
            for node in par.iter():
                if node.tag in (_W + "t", _W + "delText"):
                    seg.append(node.text or "")
            parts.append("".join(seg))
        return "\n".join(parts).strip()

    def _sides(p: ET.Element) -> tuple:
        """红线标记双侧全文回读：before=keep＋delText，after=keep＋ins。"""
        before: list = []
        after: list = []
        for child in p:
            if child.tag == _W + "r":
                for t in child.findall(_W + "t"):
                    before.append(t.text or "")
                    after.append(t.text or "")
            elif child.tag == _W + "ins":
                for t in child.iter(_W + "t"):
                    after.append(t.text or "")
            elif child.tag == _W + "del":
                for t in child.iter(_W + "delText"):
                    before.append(t.text or "")
        return "".join(before), "".join(after)

    def _paragraph_revisions(p: ET.Element) -> None:
        loc = _locate(p)
        category = "body" if "para" in loc else "table"
        ppr = p.find(_W + "pPr")
        mark_ins = mark_del = change = None
        if ppr is not None:
            rpr = ppr.find(_W + "rPr")
            if rpr is not None:
                mark_ins = rpr.find(_W + "ins")
                mark_del = rpr.find(_W + "del")
            change = ppr.find(_W + "pPrChange")
        ins_text = "".join(t.text or "" for holder in p.findall(_W + "ins")
                           for t in holder.iter(_W + "t"))
        del_text = "".join(t.text or "" for holder in p.findall(_W + "del")
                           for t in holder.iter(_W + "delText"))
        before_text, after_text = _sides(p)
        if mark_ins is not None:
            revisions.append({"category": category, "kind": "paragraph_insert",
                              **loc, "inserted_text": ins_text,
                              "after_text": after_text,
                              "author": mark_ins.get(_W + "author"),
                              "revision_id": mark_ins.get(_W + "id")})
            return
        if mark_del is not None:
            revisions.append({"category": category, "kind": "paragraph_delete",
                              **loc, "deleted_text": del_text,
                              "before_text": before_text,
                              "author": mark_del.get(_W + "author"),
                              "revision_id": mark_del.get(_W + "id")})
            return
        if change is not None:
            old_num = None
            for numpr in change.iter(_W + "numPr"):
                nid = numpr.find(_W + "numId")
                old_num = nid.get(_W + "val") if nid is not None else None
                break
            new_num = None
            if ppr.find(_W + "numPr") is not None:
                nid = ppr.find(_W + "numPr").find(_W + "numId")
                new_num = nid.get(_W + "val") if nid is not None else None
            revisions.append({"category": "numbering",
                              "kind": "paragraph_property_change", **loc,
                              "old_num_id": old_num, "new_num_id": new_num,
                              "author": change.get(_W + "author"),
                              "revision_id": change.get(_W + "id")})
        if ins_text or del_text:
            revisions.append({"category": category, "kind": "text_replace",
                              **loc, "inserted_text": ins_text,
                              "deleted_text": del_text,
                              "before_text": before_text,
                              "after_text": after_text})

    for p in _body_paragraphs(doc_tree):
        _paragraph_revisions(p)
    for tbl in _tables(doc_tree):
        for r_idx, tr in enumerate(_rows(tbl)):
            tbl_idx = _tables(doc_tree).index(tbl)
            row_mark = _row_marked(tr)
            cells = [_cell_all_text(tc) for tc in _cells(tr)]
            if row_mark == "ins":
                el = tr.find(_W + "trPr").find(_W + "ins")
                revisions.append({"category": "table", "kind": "row_insert",
                                  "table": tbl_idx, "row": r_idx,
                                  "cells": cells,
                                  "author": el.get(_W + "author"),
                                  "revision_id": el.get(_W + "id")})
                continue                    # 行级增删已携内容，跳过格级
            if row_mark == "del":
                el = tr.find(_W + "trPr").find(_W + "del")
                revisions.append({"category": "table", "kind": "row_delete",
                                  "table": tbl_idx, "row": r_idx,
                                  "cells": cells,
                                  "author": el.get(_W + "author"),
                                  "revision_id": el.get(_W + "id")})
                continue
            for tc in _cells(tr):
                for par in tc.findall(_W + "p"):
                    _paragraph_revisions(par)

    if fn_tree is not None:
        for fid in sorted(_footnote_entries(fn_tree),
                          key=lambda x: int(x)):
            for p in _footnote_entries(fn_tree)[fid].findall(_W + "p"):
                ins_text = "".join(t.text or ""
                                   for holder in p.findall(_W + "ins")
                                   for t in holder.iter(_W + "t"))
                del_text = "".join(t.text or ""
                                   for holder in p.findall(_W + "del")
                                   for t in holder.iter(_W + "delText"))
                if ins_text or del_text:
                    before_text, after_text = _sides(p)
                    revisions.append({"category": "footnote",
                                      "kind": "text_replace",
                                      "footnote_id": fid,
                                      "inserted_text": ins_text,
                                      "deleted_text": del_text,
                                      "before_text": before_text,
                                      "after_text": after_text})

    by_category: dict = {}
    for rev in revisions:
        by_category[rev["category"]] = by_category.get(rev["category"],
                                                       0) + 1
    return {"count": len(revisions), "by_category": by_category,
            "items": revisions}


def _readback_content_complete(revisions: dict) -> bool:
    """内容回读闸：每条修订必须携内容（增删文本/行格/新旧编号）。"""
    for rev in revisions["items"]:
        kind = rev.get("kind")
        if kind in ("paragraph_insert", "row_insert"):
            if not (rev.get("inserted_text") or rev.get("cells")):
                return False
        elif kind in ("paragraph_delete", "row_delete"):
            if not (rev.get("deleted_text") or rev.get("cells")):
                return False
        elif kind == "paragraph_property_change":
            if rev.get("old_num_id") is None and rev.get("new_num_id") \
                    is None:
                return False
        else:
            if not (rev.get("inserted_text") or rev.get("deleted_text")):
                return False
    return True


# --------------------------------------------------------------------------
# 状态布局（append-only；状态根绝不写 %APPDATA%）
# --------------------------------------------------------------------------

def _document_dir(state_root: Path, document_id: str) -> Path:
    return Path(state_root) / STATE_SUBDIR / document_id


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _next_seq_dir(parent: Path, suffix: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    seq = 1
    for entry in sorted(parent.iterdir()):
        if entry.is_dir() and entry.name.split("-", 1)[0].isdigit():
            seq = max(seq, int(entry.name.split("-", 1)[0]) + 1)
    return parent / f"{seq:04d}-{suffix}"


def _load_docx_bytes(args: dict) -> bytes:
    b64 = args.get("docx_b64")
    if isinstance(b64, str) and b64:
        try:
            return base64.b64decode(b64, validate=True)
        except Exception:
            raise _fail("f49_docx_b64_invalid") from None
    path = args.get("docx_path")
    if isinstance(path, str) and path:
        try:
            return Path(path).read_bytes()
        except OSError:
            raise _fail("f49_docx_not_found") from None
    raise _fail("f49_docx_required")


def register(state_root: Path, document_id: str, args: dict) -> dict:
    payload = _load_docx_bytes(args)
    with _LOCK:
        doc_dir = _document_dir(Path(state_root), document_id)
        manifest_path = doc_dir / "document.json"
        sha = _sha256_bytes(payload)
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest["baseline"]["sha256"] != sha:
                raise _fail("f49_baseline_bytes_mismatch")
            return dict(manifest)
        pkg = _read_package_bytes(payload)
        _gate_tree_clean(pkg["trees"]["word/document.xml"], "")
        _gate_tree_clean(pkg["trees"].get("word/footnotes.xml"),
                         "footnotes.")
        facts = extract_facts(pkg["trees"]["word/document.xml"],
                              pkg["trees"].get("word/footnotes.xml"),
                              pkg["trees"].get("word/numbering.xml"))
        doc_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = doc_dir / "baseline.docx"
        if baseline_path.exists():
            raise _fail("f49_state_inconsistent")
        tmp = baseline_path.with_suffix(".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, baseline_path)
        manifest = {
            "schema": SCHEMA, "document_id": document_id,
            "matter_id": args.get("matter_id"),
            "baseline": {"file": "baseline.docx", "sha256": sha,
                         "bytes": len(payload),
                         "content_digest":
                             docx_content_digest(baseline_path)},
            "facts": _facts_view(facts),
            "model": "supported_constructs_gated",
            "registered_utc": _now_utc(),
        }
        _atomic_write_json(manifest_path, manifest)
        return dict(manifest)


def _require_document(state_root: Path, document_id: str) -> tuple:
    doc_dir = _document_dir(Path(state_root), document_id)
    manifest_path = doc_dir / "document.json"
    if not manifest_path.is_file():
        raise _fail("f49_document_not_registered")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline = doc_dir / "baseline.docx"
    if _sha256_file(baseline) != manifest["baseline"]["sha256"]:
        raise _fail("f49_baseline_bytes_mismatch")
    return doc_dir, manifest


def replay(state_root: Path, document_id: str, proposal_args) -> dict:
    proposal = _validate_proposal(proposal_args)
    with _LOCK:
        doc_dir, manifest = _require_document(Path(state_root), document_id)
        baseline_pkg = _read_package(doc_dir / "baseline.docx")
        replacements = _replay_to_parts(baseline_pkg, proposal)
        prop_dir = _next_seq_dir(doc_dir / "proposals", "replay")
        prop_dir.mkdir(parents=True, exist_ok=False)
        try:
            replay_path = prop_dir / "replay.docx"
            _write_package(replay_path, baseline_pkg["parts"],
                           baseline_pkg["order"], replacements)
            replay_pkg = _read_package(replay_path)
            replay_facts = extract_facts(
                replay_pkg["trees"]["word/document.xml"],
                replay_pkg["trees"].get("word/footnotes.xml"),
                replay_pkg["trees"].get("word/numbering.xml"))
            base_facts = extract_facts(
                baseline_pkg["trees"]["word/document.xml"],
                baseline_pkg["trees"].get("word/footnotes.xml"),
                baseline_pkg["trees"].get("word/numbering.xml"))
            if replay_facts == base_facts:
                raise _fail("f49_proposal_no_change")
            out = {
                "schema": SCHEMA,
                "proposal_id": f"{document_id}:{prop_dir.name}",
                "document_id": document_id,
                "ops_applied": len(proposal["ops"]),
                "author": proposal["author"],
                "authored_utc": proposal["authored_utc"],
                "replay": {"file": "proposals/" + prop_dir.name
                           + "/replay.docx",
                           "sha256": _sha256_file(replay_path),
                           "content_digest":
                               docx_content_digest(replay_path),
                           "bytes": replay_path.stat().st_size},
                "replay_facts": _facts_view(replay_facts),
                "baseline_facts": _facts_view(base_facts),
                "created_utc": _now_utc(),
            }
            _atomic_write_json(prop_dir / "replay.json", out)
        except Exception:
            shutil.rmtree(prop_dir, ignore_errors=True)
            raise
    return dict(out)


def _split_ref(ref: str, pattern) -> tuple:
    parts = str(ref).split(":")
    if len(parts) != 2 or not _DOC_ID_RE.match(parts[0]) \
            or not pattern.match(parts[1]):
        raise _fail("f49_ref_invalid")
    return parts[0], parts[1]


def compare(state_root: Path, document_id: str, proposal_id: str) -> dict:
    with _LOCK:
        doc_dir, manifest = _require_document(Path(state_root), document_id)
        p_doc, p_dirname = _split_ref(proposal_id, _PROP_DIR_RE)
        if p_doc != document_id:
            raise _fail("f49_ref_document_mismatch")
        replay_json = doc_dir / "proposals" / p_dirname / "replay.json"
        if not replay_json.is_file():
            raise _fail("f49_replay_not_found")
        replay_manifest = json.loads(replay_json.read_text(encoding="utf-8"))
        replay_path = doc_dir / "proposals" / p_dirname / "replay.docx"
        if _sha256_file(replay_path) != replay_manifest["replay"]["sha256"]:
            raise _fail("f49_replay_bytes_mismatch")
        baseline_pkg = _read_package(doc_dir / "baseline.docx")
        replay_pkg = _read_package(replay_path)
        author = replay_manifest["author"]
        date = replay_manifest["authored_utc"]
        replacements = build_redline(baseline_pkg, replay_pkg, author, date)
        red_dir = _next_seq_dir(doc_dir / "redlines", "compare")
        red_dir.mkdir(parents=True, exist_ok=False)
        try:
            redline_path = red_dir / "redline.docx"
            _write_package(redline_path, baseline_pkg["parts"],
                           baseline_pkg["order"], replacements)
            # 对账双不变式（不过不出红线）
            red_pkg = _read_package(redline_path)
            numbering_tree = red_pkg["trees"].get("word/numbering.xml")
            base_facts = extract_facts(
                baseline_pkg["trees"]["word/document.xml"],
                baseline_pkg["trees"].get("word/footnotes.xml"),
                baseline_pkg["trees"].get("word/numbering.xml"))
            replay_facts = extract_facts(
                replay_pkg["trees"]["word/document.xml"],
                replay_pkg["trees"].get("word/footnotes.xml"),
                replay_pkg["trees"].get("word/numbering.xml"))

            def _settled_facts(accept: bool) -> dict:
                tree = copy.deepcopy(red_pkg["trees"]["word/document.xml"])
                fn = red_pkg["trees"].get("word/footnotes.xml")
                fn_tree = copy.deepcopy(fn) if fn is not None else None
                if accept:
                    _accept_all(tree)
                    if fn_tree is not None:
                        _accept_all(fn_tree)
                else:
                    _reject_all(tree)
                    if fn_tree is not None:
                        _reject_all(fn_tree)
                return extract_facts(tree, fn_tree, numbering_tree)

            if _settled_facts(True) != replay_facts:
                raise _fail("f49_reconciliation_failed:accept_all")
            if _settled_facts(False) != base_facts:
                raise _fail("f49_reconciliation_failed:reject_all")
            revisions = read_revisions(redline_path)
            if not _readback_content_complete(revisions):
                raise _fail("f49_readback_content_incomplete")
            out = {
                "schema": SCHEMA,
                "redline_id": f"{document_id}:{red_dir.name}",
                "document_id": document_id, "proposal_id": proposal_id,
                "baseline": {"sha256": manifest["baseline"]["sha256"],
                             "content_digest":
                                 manifest["baseline"]["content_digest"]},
                "replay": dict(replay_manifest["replay"]),
                "redline": {"file": "redlines/" + red_dir.name
                            + "/redline.docx",
                            "sha256": _sha256_file(redline_path),
                            "content_digest":
                                docx_content_digest(redline_path),
                            "bytes": redline_path.stat().st_size,
                            "revision_author": author,
                            "revision_date": date},
                "revisions": revisions,
                "reconciliation": {
                    "accept_all_equals_replay": True,
                    "reject_all_equals_baseline": True,
                    "readback_content_complete": True,
                },
                "consumers": list(REDLINE_CONSUMERS),
                "created_utc": _now_utc(),
            }
            _atomic_write_json(red_dir / "redline.json", out)
        except Exception:
            shutil.rmtree(red_dir, ignore_errors=True)
            raise
    return dict(out)


def report(state_root: Path, redline_id: str) -> dict:
    document_id, dirname = _split_ref(redline_id, _RED_DIR_RE)
    doc_dir = _document_dir(Path(state_root), document_id)
    path = doc_dir / "redlines" / dirname / "redline.json"
    if not path.is_file():
        raise _fail("f49_redline_not_found")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    redline = doc_dir / "redlines" / dirname / "redline.docx"
    if _sha256_file(redline) != manifest["redline"]["sha256"]:
        raise _fail("f49_redline_bytes_mismatch")
    if _sha256_file(doc_dir / "baseline.docx") != \
            manifest["baseline"]["sha256"]:
        raise _fail("f49_baseline_bytes_mismatch")
    return dict(manifest)


def list_documents(state_root: Path, document_id: str) -> dict:
    doc_dir, _manifest = _require_document(Path(state_root), document_id)
    proposals = []
    for entry in sorted((doc_dir / "proposals").iterdir()):
        meta = entry / "replay.json"
        if meta.is_file():
            view = json.loads(meta.read_text(encoding="utf-8"))
            proposals.append({"proposal_id": view["proposal_id"],
                              "ops_applied": view["ops_applied"],
                              "created_utc": view["created_utc"],
                              "sha256": view["replay"]["sha256"]})
    redlines = []
    for entry in sorted((doc_dir / "redlines").iterdir()):
        meta = entry / "redline.json"
        if meta.is_file():
            view = json.loads(meta.read_text(encoding="utf-8"))
            redlines.append({"redline_id": view["redline_id"],
                             "proposal_id": view["proposal_id"],
                             "created_utc": view["created_utc"],
                             "sha256": view["redline"]["sha256"],
                             "revision_count": view["revisions"]["count"]})
    return {"schema": SCHEMA, "document_id": document_id,
            "proposals": proposals, "redlines": redlines}


def redline_bytes(state_root: Path, redline_id: str) -> dict:
    view = report(state_root, redline_id)
    document_id, dirname = _split_ref(redline_id, _RED_DIR_RE)
    path = _document_dir(Path(state_root), document_id) / "redlines" \
        / dirname / "redline.docx"
    return {"schema": SCHEMA, "redline_id": redline_id,
            "sha256": view["redline"]["sha256"],
            "revision_count": view["revisions"]["count"],
            "consumers": view["consumers"],
            "docx_b64": base64.b64encode(path.read_bytes()).decode("ascii")}


# --------------------------------------------------------------------------
# 桥分发（legal_entry redline.* 唯一入口；fail-closed 同基线）
# --------------------------------------------------------------------------

def redline_call(method: str, args: dict, config: dict) -> dict:
    state_root = config.get("redline_state_root")
    if not state_root:
        raise _fail("f49_state_root_not_configured")

    def _document_id() -> str:
        document_id = args.get("document_id")
        if not isinstance(document_id, str) \
                or not _DOC_ID_RE.match(document_id):
            raise _fail("f49_document_id_invalid")
        return document_id

    if method == "redline.register":
        return register(Path(state_root), _document_id(), args)
    if method == "redline.replay":
        return replay(Path(state_root), _document_id(), args.get("proposal"))
    if method == "redline.compare":
        proposal_id = args.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise _fail("f49_ref_invalid")
        return compare(Path(state_root), _document_id(), proposal_id)
    if method == "redline.report":
        redline_id = args.get("redline_id")
        if not isinstance(redline_id, str) or not redline_id:
            raise _fail("f49_ref_invalid")
        return report(Path(state_root), redline_id)
    if method == "redline.list":
        return list_documents(Path(state_root), _document_id())
    if method == "redline.redline":
        redline_id = args.get("redline_id")
        if not isinstance(redline_id, str) or not redline_id:
            raise _fail("f49_ref_invalid")
        return redline_bytes(Path(state_root), redline_id)
    raise _fail("f49_method_unknown")
