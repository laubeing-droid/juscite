"""F48 ``<edits>`` 流式协议＋卡片状态机＋DB/书签双持久化（W2b-U12）：
产品侧 document-adapter 公开面——流式修订提案进入真 OOXML 修订线的执行通道。

义务 06:F48／17 卡（P02,P04）：「公开proposal/base refs→宿主原生定位/修订/
比对→部分接受/拒绝→重读实际文件→CAS/version→Harness正式采用；不模拟DOCX」。
05§8：候选通道共享 proposal/base_revision/精确quote/理由出处作者；重复命中/
base 漂移不猜改；部分接受回流 CAS 新 version，拒绝不改。

四个面（全部确定性，零模型零网络零第三方依赖）：

1. ``<edits>`` 流式协议——助手输出按任意分块流入（stream_open/push/close，
   块边界任意切分语义不可见：每次 push 对累积字节整体解析，切块方式不参与
   结果）。协议载体是单一 ``<edits>`` 根元素：
   ``<edit id=.. op=replace|insert|delete><old>精确quote</old><new>..</new>
   <reason>..</reason></edit>``。实体引用/CDATA 由标准 XML 增量解析器
   （xml.etree XMLPullParser——stdlib 确定性解析，无模型猜测）。未知标签记
   protocol warning 不阻断（前向兼容：旧解析器收到新标签不得永久卡死卡片，
   mike PR#347 部署顺序陷阱的规避）。流截断（mid-``</edit>`` 断流）＝
   f48_stream_truncated 具名拒：截断前的完整卡照常产出，未闭合尾卡绝不
   产出——流式失败不落半张卡。

2. #5188 规避（office-js#5188：Mac Word 把 tracked Replace 分解为「未跟踪
   删除＋跟踪插入」，.docx 只剩 w:ins 没有真 w:del，删除侧文本证据丢失）。
   本面结构性规避：replace 永远落成**两个独立修订元素**——w:del（w:delText
   逐字保留原文）＋紧随其后的 w:ins（w:t＝新文），绝不落单一合并 op；
   删除侧文本证据永远从实际文档的 w:delText 回读，不信宿主 API 的
   TrackedChange.text。insert 卡只落 w:ins；delete 卡只落 w:del。

3. 卡片状态机（闭集）：streamed → located | locate_failed（quote_not_found
   / quote_not_unique / quote_crosses_paragraph / revision_container_mismatch）
   → applied | rejected →（重载对账）host_accepted | host_removed。状态转移
   有守卫：未 located 不得 apply、已 applied 不得重 locate/重 apply。
   「唯一 quote 定位」：quote 必须在**当前文档正文**（全部 w:t 连接文本，
   含表内段落；w:delText 不算现行文本）里恰命中一次；零命中/多命中一律
   具名拒，绝不按偏移强改（不以猜测续写定位）。

4. DB/书签双持久化——每次 apply 同时落两处：实际文档里的 Word 书签
   （w:bookmarkStart/End，名=JF48_<card>，包住该卡的修订区）＋状态根
   SQLite 卡片账（revision ids、base/applied digest、quote sha）。重载
   对账（reconcile）：从盘上重读实际文档扫描书签与修订标记，与 DB 逐卡
   对照，**以实际文档为准**——宿主接受修订（标记消失正文留存）→
   host_accepted；宿主移除编辑（书签/修订皆不在）→ host_removed；DB
   状态被实际文档改写，漂移事件 append-only 留痕。文件写入原子
   （临时文件＋os.replace）；内容摘要部件级（zip 容器时间戳不参与）。

fail-closed：未配置状态根、文档未登记、字节不符、协议坏形、状态机违规
——一律 typed error（f48_* 错误码），错误码不携材料语义。不模拟 DOCX——
一切编辑作用于盘上真实 DOCX 字节，apply 后重读实际文件回流
（edits.read_document 供 harness CAS/version 消费）。

v1 边界（如实）：quote 不得跨段落（跨段删除涉及段落标记删除，属 F49
两宿主面）；受影响 run 的容器必须一致（混合 hyperLink/正文父级具名拒）；
编辑域=word/document.xml 正文（页眉脚/脚注部件保字节不动，脚注编辑属
F49）；run 子结构限 [rPr?]+单 w:t（tab/br 混排 span 具名拒不猜改）；
Word/WPS 真宿主联测属 F49，本面即宿主编辑通道的确定性实现。
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

SCHEMA = "juscite-f48-edits-protocol/1"
STATE_SUBDIR = "edits-protocol"
DOC_PART = "word/document.xml"
BOOKMARK_PREFIX = "JF48_"
FIXED_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = f"{{{W_NS}}}"
XML_SPACE = f"{{{XML_NS}}}space"

OPS = frozenset({"replace", "insert", "delete"})
# 卡片状态机闭集（reconcile 派生态以实际文档为准落 DB）
CARD_STATES = frozenset({
    "streamed", "located", "locate_failed", "applied",
    "rejected", "host_accepted", "host_removed",
})
# locate_failed 理由闭集（卡级，具名不猜改）
LOCATE_REASONS = frozenset({
    "quote_not_found", "quote_not_unique",
    "quote_crosses_paragraph", "revision_container_mismatch",
})

_DOC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CARD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_STREAM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REVISION_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cards (
  card_key TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  stream_id TEXT NOT NULL,
  card_id TEXT NOT NULL,
  op TEXT NOT NULL,
  quote TEXT,
  new_text TEXT,
  reason TEXT,
  state TEXT NOT NULL,
  state_reason TEXT,
  quote_sha256 TEXT,
  locate_doc_digest TEXT,
  bookmark TEXT,
  revision_ids TEXT,
  base_doc_digest TEXT,
  applied_doc_digest TEXT,
  applied_sha256 TEXT,
  updated_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS cards_doc_stream_card
  ON cards(document_id, stream_id, card_id);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  kind TEXT NOT NULL,
  card_key TEXT,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS streams (
  stream_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  closed INTEGER NOT NULL DEFAULT 0,
  protocol_error TEXT,
  card_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class EditsError(ValueError):
    """Typed F48 face failure; str() is a code, never material semantics."""

    error_code = "f48_invalid"


def _fail(code: str) -> EditsError:
    return EditsError(code)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _b64decode(payload) -> bytes:
    if not isinstance(payload, str) or not payload:
        raise _fail("f48_params_invalid:bytes_required")
    try:
        return base64.b64decode(payload, validate=True)
    except Exception:
        raise _fail("f48_params_invalid:bytes_not_base64") from None


# --------------------------------------------------------------------------
# DOCX 装载／序列化（纯 stdlib；部件级摘要；原子写；固定 zip 时间戳）
# --------------------------------------------------------------------------

def load_docx_parts(path: Path) -> dict[str, bytes]:
    """读盘上 DOCX 全部件字节；容器坏形/缺正文部件=fail-closed。"""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            parts = {name: zf.read(name) for name in names}
    except zipfile.BadZipFile:
        raise _fail("f48_document_zip_invalid") from None
    if DOC_PART not in parts:
        raise _fail("f48_document_part_missing")
    return parts


def load_docx_parts_from_bytes(payload: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = zf.namelist()
            parts = {name: zf.read(name) for name in names}
    except zipfile.BadZipFile:
        raise _fail("f48_document_zip_invalid") from None
    if DOC_PART not in parts:
        raise _fail("f48_document_part_missing")
    _parse_document_xml(parts[DOC_PART])   # 坏形正文=fail-closed
    return parts


def content_digest(parts: dict[str, bytes]) -> str:
    """部件级内容摘要（zip 容器 mtime 不参与；同内容同摘要）。"""
    digest = hashlib.sha256()
    for name in sorted(parts):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(parts[name]).digest())
    return digest.hexdigest()


def _parse_document_xml(raw: bytes):
    """登记原文命名空间前缀后解析正文部件。
    返回 (root, 前缀声明列表, 默认命名空间列表)。"""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _fail("f48_document_xml_invalid:encoding") from None
    declarations = re.findall(r'xmlns:([A-Za-z0-9_.-]+)\s*=\s*"([^"]+)"', text)
    default_ns = re.findall(r'xmlns\s*=\s*"([^"]+)"', text)
    for prefix, uri in declarations:
        ET.register_namespace(prefix, uri)
    for uri in default_ns:
        ET.register_namespace("", uri)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise _fail("f48_document_xml_invalid:malformed") from None
    return root, declarations, default_ns


def _serialize_document_xml(root, declarations, default_ns) -> bytes:
    """序列化正文部件；把 ET 可能丢掉的未用命名空间声明补回根标签
    （mc:Ignorable 类引用的前缀不能悬空——真实 Word 文档兼容）。"""
    out = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    prefix = b""
    body = out
    if out.startswith(b"<?xml"):
        decl_end = out.find(b"?>")
        if decl_end != -1:
            prefix, body = out[:decl_end + 2], out[decl_end + 2:]
    head_end = body.find(b">")
    start_tag = body[:head_end + 1]
    additions = []
    for prefix_uri in declarations:
        token = f'xmlns:{prefix_uri[0]}="{prefix_uri[1]}"'.encode("utf-8")
        if token not in start_tag:
            additions.append(b" " + token)
    for uri in default_ns:
        token = f'xmlns="{uri}"'.encode("utf-8")
        if token not in start_tag:
            additions.append(b" " + token)
    if additions:
        body = start_tag + b"".join(additions) + body[head_end + 1:]
    return prefix + body


def write_docx_atomic(path: Path, parts: dict[str, bytes]) -> None:
    """全部件重写（固定 zip 时间戳＝确定性容器）＋原子替换。"""
    handle = tempfile.NamedTemporaryFile(
        "wb", dir=str(path.parent), prefix=".f48-write-", delete=False)
    try:
        with zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, payload in parts.items():
                info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, payload)
        handle.close()
        os.replace(handle.name, path)
    finally:
        if not handle.closed:
            handle.close()
        if os.path.exists(handle.name):
            os.unlink(handle.name)


# --------------------------------------------------------------------------
# 正文文本索引（现行文本＝全部 w.t，含表内段落；w:delText 不算现行文本）
# --------------------------------------------------------------------------

class Segment:
    """一段 w:t 在全文里的落位（含其 run 与容器，供切分/包裹）。"""

    __slots__ = ("t_el", "run_el", "container", "para_el", "start", "end")

    def __init__(self, t_el, run_el, container, para_el, start, end):
        self.t_el = t_el
        self.run_el = run_el
        self.container = container
        self.para_el = para_el
        self.start = start
        self.end = end


def _iter_run_texts(element):
    """按文档序产出 (容器, run, w:t)：递归进 hyperlink/ins 等容器保持顺序。"""
    for child in element:
        if child.tag == W + "r":
            for sub in child:
                if sub.tag == W + "t":
                    yield element, child, sub
        else:
            yield from _iter_run_texts(child)


def build_text_index(root) -> tuple[str, list[Segment]]:
    body = root.find(W + "body")
    if body is None:
        raise _fail("f48_document_body_missing")
    segments: list[Segment] = []
    chunks: list[str] = []
    cursor = 0
    for paragraph in body.iter(W + "p"):
        for container, run, t_el in _iter_run_texts(paragraph):
            text = t_el.text or ""
            if not text:
                continue
            segments.append(Segment(t_el, run, container, paragraph,
                                    cursor, cursor + len(text)))
            chunks.append(text)
            cursor += len(text)
        chunks.append("\n")
        cursor += 1
    return "".join(chunks), segments


def find_occurrences(text: str, quote: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while True:
        index = text.find(quote, start)
        if index < 0:
            return positions
        positions.append(index)
        start = index + 1


def _set_preserve(t_el) -> None:
    t_el.set(XML_SPACE, "preserve")


def _split_run_at(segment: Segment, offsets: list[int]) -> list[Segment]:
    """在 t 文本的字符偏移处切分 run（deepcopy 保 rPr），返回按序的
    新 Segment 列表（连接文本==原文本）。切分只允许 run 子结构＝
    [rPr?]＋单 w:t，否则具名拒（fail-closed，不猜改复杂 run）。"""
    run = segment.run_el
    children = list(run)
    text_children = [child for child in children if child.tag == W + "t"]
    other = [child for child in children if child.tag not in (W + "rPr", W + "t")]
    if len(text_children) != 1 or other:
        raise _fail("f48_run_structure_unsupported")
    text = segment.t_el.text or ""
    cuts = sorted({offset for offset in offsets if 0 < offset < len(text)})
    if not cuts:
        return [segment]
    pieces: list[str] = []
    previous = 0
    for cut in cuts + [len(text)]:
        pieces.append(text[previous:cut])
        previous = cut
    t_el = segment.t_el
    t_el.text = pieces[0]
    _set_preserve(t_el)
    container = segment.container
    result = [Segment(t_el, run, container, segment.para_el,
                      segment.start, segment.start + len(pieces[0]))]
    current_run = run
    cursor = segment.start + len(pieces[0])
    for piece in pieces[1:]:
        new_run = copy.deepcopy(run)
        new_t = new_run.find(W + "t")
        new_t.text = piece
        _set_preserve(new_t)
        container.insert(list(container).index(current_run) + 1, new_run)
        result.append(Segment(new_t, new_run, container, segment.para_el,
                              cursor, cursor + len(piece)))
        cursor += len(piece)
        current_run = new_run
    return result


def _max_ids(root) -> tuple[int, int]:
    """(最大书签数字 id, 最大修订数字 id)——新 id 从其上分配，
    既有修订（他作者）永不被改写。"""
    bookmark = revision = 0
    for element in root.iter():
        raw_id = None
        if element.tag == W + "bookmarkStart":
            raw_id = element.get(W + "id")
        elif element.tag in (W + "ins", W + "del",
                             W + "moveFrom", W + "moveTo"):
            raw_id = element.get(W + "id")
        if raw_id is None:
            continue
        try:
            value = int(raw_id)
        except ValueError:
            continue
        if element.tag == W + "bookmarkStart":
            bookmark = max(bookmark, value)
        else:
            revision = max(revision, value)
    return bookmark, revision


def bookmark_name_for(card_id: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", card_id)[:32]
    return BOOKMARK_PREFIX + sanitized


def apply_card_to_tree(root, card: dict, author: str, date: str,
                       next_bookmark_id: int, next_revision_id: int) -> dict:
    """在内存树上一张卡：唯一 quote 重定位→切分→真修订（w:ins/w:del，
    #5188 规避＝replace 落两个独立修订元素）→书签包裹。

    返回 {bookmark, revision_ids}；定位失败 raise EditsError（code ∈
    LOCATE_REASONS）——调用方落卡级 locate_failed，不中断整批。
    """
    full_text, segments = build_text_index(root)
    quote = card["quote"]
    positions = find_occurrences(full_text, quote)
    if not positions:
        raise _fail("quote_not_found")
    if len(positions) > 1:
        raise _fail("quote_not_unique")
    quote_start, quote_end = positions[0], positions[0] + len(quote)
    affected = [segment for segment in segments
                if segment.start < quote_end and segment.end > quote_start]
    if not affected:
        raise _fail("quote_not_found")
    if id(affected[0].para_el) != id(affected[-1].para_el):
        raise _fail("quote_crosses_paragraph")
    if len({id(segment.container) for segment in affected}) != 1:
        raise _fail("revision_container_mismatch")
    container = affected[0].container

    op = card["op"]
    revision_ids: list[str] = []
    del_el = None
    ins_el = None
    allocated = 0

    if op in ("replace", "delete"):
        # 切出恰好覆盖 quote 的中段 run（每段只切自己的两侧边界）
        middle_runs = []
        for segment in affected:
            local_start = max(quote_start, segment.start) - segment.start
            local_end = min(quote_end, segment.end) - segment.start
            pieces = _split_run_at(segment, [local_start, local_end])
            middle_runs.append(pieces[1] if local_start > 0 else pieces[0])
        del_el = ET.Element(W + "del")
        del_el.set(W + "id", str(next_revision_id + allocated))
        del_el.set(W + "author", author)
        del_el.set(W + "date", date)
        revision_ids.append(str(next_revision_id + allocated))
        allocated += 1
        container.insert(
            list(container).index(middle_runs[0].run_el), del_el)
        del_text_parts = []
        for segment in middle_runs:
            t_el = segment.t_el
            del_text_parts.append(t_el.text or "")
            container.remove(segment.run_el)
            del_el.append(segment.run_el)
            t_el.tag = W + "delText"     # 真修订：删除侧文本证据落 delText
            _set_preserve(t_el)
        if "".join(del_text_parts) != quote:
            # 结构自检：中段拼接必须逐字等于 quote（确定性切分保证）
            raise _fail("f48_internal_split_mismatch")

    if op in ("replace", "insert"):
        ins_el = ET.Element(W + "ins")
        ins_el.set(W + "id", str(next_revision_id + allocated))
        ins_el.set(W + "author", author)
        ins_el.set(W + "date", date)
        revision_ids.append(str(next_revision_id + allocated))
        allocated += 1
        new_run = ET.SubElement(ins_el, W + "r")
        new_t = ET.SubElement(new_run, W + "t")
        new_t.text = card["new_text"]
        _set_preserve(new_t)
        if op == "replace":
            # #5188 规避：ins 紧随 del 之后（两个独立修订元素，非合并 op）
            container.insert(list(container).index(del_el) + 1, ins_el)
        else:
            # insert：锚点 quote 尾字符所在 run 的紧后位置
            tail = affected[-1]
            local_end = min(quote_end, tail.end) - tail.start
            pieces = _split_run_at(tail, [local_end])
            anchor_run = pieces[0].run_el
            container.insert(list(container).index(anchor_run) + 1, ins_el)

    name = bookmark_name_for(card["card_id"])
    for element in root.iter(W + "bookmarkStart"):
        if element.get(W + "name") == name:
            raise _fail("f48_bookmark_name_collision")
    first_el = del_el if del_el is not None else ins_el
    last_el = ins_el if ins_el is not None else del_el
    start_el = ET.Element(W + "bookmarkStart")
    start_el.set(W + "id", str(next_bookmark_id))
    start_el.set(W + "name", name)
    end_el = ET.Element(W + "bookmarkEnd")
    end_el.set(W + "id", str(next_bookmark_id))
    container.insert(list(container).index(first_el), start_el)
    container.insert(list(container).index(last_el) + 1, end_el)

    return {"bookmark": name, "revision_ids": revision_ids}


# --------------------------------------------------------------------------
# 实际文档扫描（重载对账的文档侧事实——以实际文档为准）
# --------------------------------------------------------------------------

def scan_document(parts: dict[str, bytes]) -> dict:
    """从部件字节扫描：JF48_ 书签（含区间现行文本）与修订标记。
    删除侧文本从 w:delText 回读（office-js#5188 的丢失面在这里结构性
    不存在：证据读实际文档，不读宿主 API）。"""
    root, _, _ = _parse_document_xml(parts[DOC_PART])
    body = root.find(W + "body")
    bookmarks: dict[str, dict] = {}
    revisions: list[dict] = []
    open_bookmarks: dict[str, list[str]] = {}
    name_by_numeric: dict[str, str] = {}

    def element_text(element, tagname) -> str:
        return "".join(sub.text or "" for sub in element.iter(tagname))

    for element in body.iter():
        tag = element.tag
        if tag in (W + "ins", W + "del"):
            kind = "ins" if tag == W + "ins" else "del"
            revisions.append({
                "id": element.get(W + "id"),
                "kind": kind,
                "author": element.get(W + "author"),
                "date": element.get(W + "date"),
                "text": element_text(
                    element, W + "t" if kind == "ins" else W + "delText"),
            })
        elif tag == W + "bookmarkStart":
            name = element.get(W + "name") or ""
            numeric = element.get(W + "id") or ""
            if name.startswith(BOOKMARK_PREFIX):
                bookmarks[name] = {"id": numeric, "text": ""}
                open_bookmarks[numeric] = []
                name_by_numeric[numeric] = name
        elif tag == W + "bookmarkEnd":
            numeric = element.get(W + "id") or ""
            if numeric in open_bookmarks:
                bookmarks[name_by_numeric[numeric]]["text"] = \
                    "".join(open_bookmarks.pop(numeric))
                name_by_numeric.pop(numeric, None)
        elif tag == W + "t":
            for collected in open_bookmarks.values():
                collected.append(element.text or "")
    for numeric, collected in open_bookmarks.items():
        bookmarks[name_by_numeric[numeric]]["text"] = "".join(collected)
    return {"bookmarks": bookmarks, "revisions": revisions}


# --------------------------------------------------------------------------
# <edits> 流式协议（XMLPullParser 增量；分块语义不可见；截断具名拒）
# --------------------------------------------------------------------------

_KNOWN_TAGS = ("edits", "edit", "old", "new", "reason")


def parse_stream(chunks: list[str], final: bool = False) -> dict:
    """解析累积块序列 → {cards, warnings, protocol_error, closed}。

    分块语义不可见：对拼接后字节整体解析（切块方式不参与结果）。
    final=False（push 中）：EOF 处未完＝正常开流状态（protocol_error=
    None），已完整卡照常产出；final=True（close）：根未闭合＝
    f48_stream_truncated 具名拒，未闭合尾卡绝不产出。坏形（非法记号/
    嵌套文本/根非法）两态皆具名拒。"""
    joined = "".join(chunks)
    if not joined.strip():
        return {"cards": [], "warnings": [],
                "protocol_error": {"code": "f48_protocol_empty"},
                "closed": False}
    parser = ET.XMLPullParser(events=("start", "end"))
    cards: list[dict] = []
    warnings: list[str] = []
    closed = False
    root_open = False
    current: dict | None = None
    current_depth = 0
    depth = 0

    def finish(code: str | None) -> dict:
        return {"cards": cards, "warnings": warnings,
                "protocol_error": {"code": code} if code else None,
                "closed": closed}

    def feed_all() -> str | None:
        nonlocal depth, current, current_depth, root_open, closed
        parser.feed(joined.encode("utf-8"))
        for event, element in parser.read_events():
            tag = element.tag
            if event == "start":
                depth += 1
                if depth == 1:
                    if tag != "edits":
                        return "f48_protocol_root_invalid"
                    root_open = True
                    continue
                if tag == "edit" and current is None and depth == 2:
                    current = dict(element.attrib)
                    current_depth = depth
                continue
            # end 事件
            depth -= 1
            if tag == "edits":
                closed = True
                continue
            if current is not None and tag == "edit" \
                    and depth == current_depth - 1:
                card, error = _validate_card(element, current)
                if error:
                    return error
                cards.append(card)
                current = None
                continue
            if tag not in _KNOWN_TAGS and depth >= 1:
                # 未知标签：前向兼容不阻断（mike PR#347 部署顺序陷阱规避）
                warnings.append("unknown_tag:" + str(tag))
        return None

    def eof_code(message: str) -> str | None:
        # EOF 处仍缺标记：close 时＝截断具名拒；push 中＝正常未完（None）
        if "no element found" in message or "unclosed" in message:
            return "f48_stream_truncated" if final else None
        return "f48_protocol_malformed"

    try:
        error = feed_all()
    except ET.ParseError as exc:
        return finish(eof_code(str(exc)))
    if error:
        return finish(error)
    try:
        parser.close()
    except ET.ParseError as exc:
        return finish(eof_code(str(exc)))
    if not root_open:
        return finish("f48_protocol_root_invalid")
    if not closed:
        return finish("f48_stream_truncated" if final else None)
    seen = set()
    for card in cards:
        if card["card_id"] in seen:
            return finish("f48_protocol_duplicate_card_id")
        seen.add(card["card_id"])
    return {"cards": cards, "warnings": warnings,
            "protocol_error": None, "closed": True}


def _validate_card(element, opened: dict) -> tuple[dict | None, str | None]:
    card_id = opened.get("id") or ""
    op = opened.get("op") or ""
    old_el = element.find("old")
    new_el = element.find("new")
    old = old_el.text if old_el is not None else None
    new = new_el.text if new_el is not None else None
    reason = element.findtext("reason")
    for leaf in (old_el, new_el):
        if leaf is not None and len(leaf):
            return None, "f48_protocol_nested_invalid"
    if not _CARD_ID_RE.match(card_id):
        return None, "f48_protocol_card_id_invalid"
    if op not in OPS:
        return None, "f48_protocol_edit_invalid:op"
    if not isinstance(old, str) or not old:
        return None, "f48_protocol_edit_invalid:old_required"
    if op == "delete" and new:
        return None, "f48_protocol_edit_invalid:delete_with_new"
    if op in ("replace", "insert") and not new:
        return None, "f48_protocol_edit_invalid:new_required"
    card = {"card_id": card_id, "op": op, "quote": old,
            "new_text": new or "", "reason": reason or ""}
    return card, None


# --------------------------------------------------------------------------
# 状态根（文档目录：original/working/CARDS db/streams）
# --------------------------------------------------------------------------

def _doc_dir(state_root: Path, document_id: str) -> Path:
    return Path(state_root) / STATE_SUBDIR / document_id


def _require_doc_dir(state_root: Path, document_id: str) -> Path:
    if not _DOC_ID_RE.match(document_id or ""):
        raise _fail("f48_document_id_invalid")
    directory = _doc_dir(state_root, document_id)
    if not (directory / "meta.json").is_file():
        raise _fail("f48_document_not_registered")
    return directory


def _connect(directory: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(directory / "cards.db"))
    connection.row_factory = sqlite3.Row
    connection.executescript(_SCHEMA_SQL)
    return connection


def _record_event(connection, kind: str, card_key: str | None, detail: str):
    connection.execute(
        "INSERT INTO events(at, kind, card_key, detail) VALUES (?,?,?,?)",
        (_now(), kind, card_key, detail))


def _card_row(connection, document_id: str, stream_id: str, card_id: str):
    return connection.execute(
        "SELECT * FROM cards WHERE document_id=? AND stream_id=? AND card_id=?",
        (document_id, stream_id, card_id)).fetchone()


def _upsert_stream_cards(connection, document_id: str, stream_id: str,
                         cards: list[dict]):
    for card in cards:
        if _card_row(connection, document_id, stream_id, card["card_id"]) \
                is None:
            connection.execute(
                "INSERT INTO cards(card_key, document_id, stream_id, card_id,"
                " op, quote, new_text, reason, state, state_reason,"
                " quote_sha256, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"{stream_id}:{card['card_id']}", document_id, stream_id,
                 card["card_id"], card["op"], card["quote"], card["new_text"],
                 card["reason"], "streamed", None,
                 _sha256_text(card["quote"]), _now()))


def _stream_chunks(directory: Path, stream_id: str) -> list[str]:
    path = directory / "streams" / stream_id / "chunks.jsonl"
    if not path.is_file():
        raise _fail("f48_stream_not_found")
    chunks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            chunks.append(json.loads(line)["chunk"])
    return chunks


def _write_stream_state(directory: Path, stream_id: str, state: dict) -> None:
    path = directory / "streams" / stream_id / "stream.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


def _read_stream_state(directory: Path, stream_id: str) -> dict:
    path = directory / "streams" / stream_id / "stream.json"
    if not path.is_file():
        raise _fail("f48_stream_not_found")
    return json.loads(path.read_text(encoding="utf-8"))


def _require_valid_stream(connection, document_id: str,
                          stream_id: str) -> dict:
    row = connection.execute(
        "SELECT * FROM streams WHERE stream_id=? AND document_id=?",
        (stream_id, document_id)).fetchone()
    if row is None:
        raise _fail("f48_stream_not_found")
    if not row["closed"]:
        raise _fail("f48_stream_not_closed")
    if row["protocol_error"]:
        raise _fail("f48_stream_invalid:" + row["protocol_error"])
    return dict(row)


# --------------------------------------------------------------------------
# 公开面方法
# --------------------------------------------------------------------------

def edits_register(state_root: Path, document_id: str, payload: bytes) -> dict:
    if not _DOC_ID_RE.match(document_id or ""):
        raise _fail("f48_document_id_invalid")
    directory = _doc_dir(state_root, document_id)
    sha = hashlib.sha256(payload).hexdigest()
    if (directory / "meta.json").is_file():
        meta = json.loads((directory / "meta.json").read_text("utf-8"))
        if meta["original_sha256"] != sha:
            raise _fail("f48_document_bytes_mismatch")
        return {"schema": SCHEMA, "document_id": document_id,
                "registered": False, "original_sha256": sha,
                "note": "idempotent_reread"}
    parts = load_docx_parts_from_bytes(payload)
    digest = content_digest(parts)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "original.docx").write_bytes(payload)
    (directory / "working.docx").write_bytes(payload)
    (directory / "meta.json").write_text(json.dumps({
        "schema": SCHEMA, "document_id": document_id,
        "original_sha256": sha, "content_digest": digest,
        "registered_at": _now()}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    (directory / "streams").mkdir(exist_ok=True)
    with closing(_connect(directory)):
        pass
    return {"schema": SCHEMA, "document_id": document_id, "registered": True,
            "original_sha256": sha, "content_digest": digest}


def edits_stream_open(state_root: Path, document_id: str, stream_id: str) -> dict:
    _require_doc_dir(state_root, document_id)
    if not _STREAM_ID_RE.match(stream_id or ""):
        raise _fail("f48_stream_id_invalid")
    directory = _doc_dir(state_root, document_id)
    stream_dir = directory / "streams" / stream_id
    if stream_dir.exists():
        raise _fail("f48_stream_exists")
    stream_dir.mkdir(parents=True)
    (stream_dir / "chunks.jsonl").write_text("", encoding="utf-8")
    _write_stream_state(directory, stream_id, {
        "schema": SCHEMA, "stream_id": stream_id,
        "document_id": document_id, "closed": False,
        "protocol_error": None})
    with closing(_connect(directory)) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO streams(stream_id, document_id, closed,"
            " protocol_error, card_count) VALUES (?,?,0,NULL,0)",
            (stream_id, document_id))
        connection.commit()
    return {"schema": SCHEMA, "stream_id": stream_id,
            "document_id": document_id, "state": "open"}


def _persist_parse(state_root: Path, document_id: str, stream_id: str,
                   parsed: dict, closing_stream: bool) -> dict:
    directory = _doc_dir(state_root, document_id)
    if _read_stream_state(directory, stream_id).get("closed"):
        raise _fail("f48_stream_closed")
    with closing(_connect(directory)) as connection:
        # 卡片账只在**有效 close**时落卡：push 期不落（流仍可能变坏），
        # 坏流 close 清掉该流全部行（失败面绝不污染卡片账）
        if closing_stream and parsed["protocol_error"] is None:
            _upsert_stream_cards(connection, document_id, stream_id,
                                 parsed["cards"])
        elif closing_stream:
            connection.execute(
                "DELETE FROM cards WHERE document_id=? AND stream_id=?",
                (document_id, stream_id))
        connection.execute(
            "UPDATE streams SET card_count=?, protocol_error=?, closed=?"
            " WHERE stream_id=?",
            (len(parsed["cards"]),
             parsed["protocol_error"]["code"] if parsed["protocol_error"]
             else None,
             1 if closing_stream else 0, stream_id))
        connection.commit()
    if closing_stream:
        state = _read_stream_state(directory, stream_id)
        state["closed"] = True
        state["protocol_error"] = parsed["protocol_error"]
        _write_stream_state(directory, stream_id, state)
    return {"schema": SCHEMA, "stream_id": stream_id,
            "document_id": document_id,
            "cards": parsed["cards"],
            "card_count": len(parsed["cards"]),
            "warnings": parsed["warnings"],
            "protocol_error": parsed["protocol_error"],
            "closed": bool(closing_stream)}


def edits_stream_push(state_root: Path, document_id: str, stream_id: str,
                      chunk) -> dict:
    _require_doc_dir(state_root, document_id)
    if not isinstance(chunk, str):
        raise _fail("f48_stream_chunk_invalid")
    directory = _doc_dir(state_root, document_id)
    chunks_path = directory / "streams" / stream_id / "chunks.jsonl"
    if not chunks_path.is_file():
        raise _fail("f48_stream_not_found")
    with open(chunks_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"chunk": chunk}, ensure_ascii=False) + "\n")
    parsed = parse_stream(_stream_chunks(directory, stream_id), final=False)
    return _persist_parse(state_root, document_id, stream_id, parsed, False)


def edits_stream_close(state_root: Path, document_id: str, stream_id: str) -> dict:
    _require_doc_dir(state_root, document_id)
    directory = _doc_dir(state_root, document_id)
    _read_stream_state(directory, stream_id)
    parsed = parse_stream(_stream_chunks(directory, stream_id), final=True)
    return _persist_parse(state_root, document_id, stream_id, parsed, True)


def edits_locate(state_root: Path, document_id: str, stream_id: str) -> dict:
    directory = _require_doc_dir(state_root, document_id)
    parts = load_docx_parts(directory / "working.docx")
    root, _, _ = _parse_document_xml(parts[DOC_PART])
    full_text, _segments = build_text_index(root)
    digest = content_digest(parts)
    results = []
    with closing(_connect(directory)) as connection:
        _require_valid_stream(connection, document_id, stream_id)
        rows = connection.execute(
            "SELECT * FROM cards WHERE document_id=? AND stream_id=?"
            " ORDER BY rowid", (document_id, stream_id)).fetchall()
        for row in rows:
            if row["state"] != "streamed":
                raise _fail("f48_card_state_invalid:" + row["state"])
            positions = find_occurrences(full_text, row["quote"])
            if len(positions) == 1:
                state, reason = "located", None
            elif not positions:
                state, reason = "locate_failed", "quote_not_found"
            else:
                state, reason = "locate_failed", "quote_not_unique"
            connection.execute(
                "UPDATE cards SET state=?, state_reason=?, locate_doc_digest=?,"
                " updated_at=? WHERE card_key=?",
                (state, reason, digest, _now(), row["card_key"]))
            _record_event(connection, "locate", row["card_key"],
                          json.dumps({"state": state, "reason": reason,
                                      "occurrences": len(positions),
                                      "doc_digest": digest}))
            connection.commit()
            results.append({
                "card_id": row["card_id"], "op": row["op"],
                "state": state, "state_reason": reason,
                "occurrences": len(positions),
                "quote_sha256": row["quote_sha256"],
                "doc_digest": digest})
    return {"schema": SCHEMA, "document_id": document_id,
            "stream_id": stream_id, "cards": results,
            "doc_digest": digest}


def edits_apply(state_root: Path, document_id: str, stream_id: str,
                card_ids, reject_card_ids, revision_author, revision_date) -> dict:
    directory = _require_doc_dir(state_root, document_id)
    if not isinstance(card_ids, list) or not all(
            isinstance(item, str) for item in card_ids):
        raise _fail("f48_apply_ids_required")
    reject_card_ids = reject_card_ids or []
    if not isinstance(revision_author, str) or not revision_author \
            or len(revision_author) > 64:
        raise _fail("f48_revision_params_invalid:author")
    if not isinstance(revision_date, str) \
            or not _REVISION_DATE_RE.match(revision_date):
        raise _fail("f48_revision_params_invalid:date")
    # F53 收拢（W2b-U49）：edits 通道修订作者过 author_policy 策略面
    # （闭集外作者含律师名＝f53_author_impersonation 具名拒；f48 形参校验
    # 在前，既有负向码不变）。
    from author_policy import check_revision_author, AuthorPolicyError
    try:
        check_revision_author("edits", revision_author)
    except AuthorPolicyError as exc:
        raise _fail(str(exc)) from None

    parts = load_docx_parts(directory / "working.docx")
    root, declarations, default_ns = _parse_document_xml(parts[DOC_PART])
    base_digest = content_digest(parts)
    # 新 id 从既有最大值之上分配（+1）：既有修订/书签永不被改写不冲突
    bookmark_id, revision_id = _max_ids(root)
    bookmark_id += 1
    revision_id += 1

    with closing(_connect(directory)) as connection:
        _require_valid_stream(connection, document_id, stream_id)
        # ---- 拒绝面先行（人说不：不碰文档一字）
        for card_id in reject_card_ids:
            row = _card_row(connection, document_id, stream_id, card_id)
            if row is None:
                raise _fail("f48_card_not_found:" + card_id)
            if row["state"] not in ("streamed", "located"):
                raise _fail("f48_card_state_invalid:" + row["state"])
            connection.execute(
                "UPDATE cards SET state='rejected',"
                " state_reason='human_rejected', updated_at=?"
                " WHERE card_key=?", (_now(), row["card_key"]))
            _record_event(connection, "reject", row["card_key"],
                          "human_rejected")
        connection.commit()

        outcomes = []
        for card_id in card_ids:
            row = _card_row(connection, document_id, stream_id, card_id)
            if row is None:
                raise _fail("f48_card_not_found:" + card_id)
            if row["state"] != "located":
                raise _fail("f48_card_state_invalid:" + row["state"])
            card = {"card_id": card_id, "op": row["op"], "quote": row["quote"],
                    "new_text": row["new_text"]}
            try:
                applied = apply_card_to_tree(
                    root, card, revision_author, revision_date,
                    bookmark_id, revision_id)
            except EditsError as exc:
                code = str(exc)
                if code in LOCATE_REASONS:
                    connection.execute(
                        "UPDATE cards SET state='locate_failed',"
                        " state_reason=?, updated_at=? WHERE card_key=?",
                        (code, _now(), row["card_key"]))
                    _record_event(connection, "apply_locate_failed",
                                  row["card_key"], code)
                    outcomes.append({"card_id": card_id, "applied": False,
                                     "state": "locate_failed",
                                     "state_reason": code})
                    continue
                raise
            bookmark_id += 1
            revision_id += len(applied["revision_ids"])
            outcomes.append({"card_id": card_id, "applied": True,
                             "state": "applied", **applied})

        applied_any = any(outcome["applied"] for outcome in outcomes)
        if applied_any:
            new_xml = _serialize_document_xml(root, declarations, default_ns)
            new_parts = dict(parts)
            new_parts[DOC_PART] = new_xml
            applied_digest = content_digest(new_parts)
            write_docx_atomic(directory / "working.docx", new_parts)
            applied_bytes = (directory / "working.docx").read_bytes()
            applied_sha = hashlib.sha256(applied_bytes).hexdigest()
        else:
            # 零卡接受（纯拒绝面）：文档一字不动，不重写文件
            applied_digest = base_digest
            applied_sha = hashlib.sha256(
                (directory / "working.docx").read_bytes()).hexdigest()
        for outcome in outcomes:
            if not outcome["applied"]:
                continue
            row_key = f"{stream_id}:{outcome['card_id']}"
            connection.execute(
                "UPDATE cards SET state='applied', state_reason=NULL,"
                " bookmark=?, revision_ids=?, base_doc_digest=?,"
                " applied_doc_digest=?, applied_sha256=?, updated_at=?"
                " WHERE card_key=?",
                (outcome["bookmark"], json.dumps(outcome["revision_ids"]),
                 base_digest, applied_digest, applied_sha, _now(), row_key))
            _record_event(connection, "apply", row_key,
                          json.dumps({"bookmark": outcome["bookmark"],
                                      "revision_ids": outcome["revision_ids"],
                                      "base": base_digest,
                                      "applied": applied_digest}))
        connection.commit()
    return {"schema": SCHEMA, "document_id": document_id,
            "stream_id": stream_id, "base_doc_digest": base_digest,
            "applied_doc_digest": applied_digest,
            "applied_sha256": applied_sha, "cards": outcomes}


def edits_read_document(state_root: Path, document_id: str) -> dict:
    """重读盘上实际文件（apply 后回流＝宿主结果字节；CAS/version 消费）。"""
    directory = _require_doc_dir(state_root, document_id)
    payload = (directory / "working.docx").read_bytes()
    parts = load_docx_parts(directory / "working.docx")
    return {"schema": SCHEMA, "document_id": document_id,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "content_digest": content_digest(parts),
            "bytesB64": base64.b64encode(payload).decode("ascii")}


def edits_reconcile(state_root: Path, document_id: str) -> dict:
    """重载对账：重读实际文档扫描书签/修订，与 DB 逐卡对照，
    **以实际文档为准**改写 DB 派生态并留痕（append-only 事件账）。"""
    directory = _require_doc_dir(state_root, document_id)
    parts = load_docx_parts(directory / "working.docx")
    scan = scan_document(parts)
    digest = content_digest(parts)
    doc_revision_ids = {revision["id"] for revision in scan["revisions"]}
    report_cards = []
    with closing(_connect(directory)) as connection:
        rows = connection.execute(
            "SELECT * FROM cards WHERE document_id=? ORDER BY rowid",
            (document_id,)).fetchall()
        for row in rows:
            if row["state"] != "applied":
                report_cards.append({
                    "card_id": row["card_id"], "stream_id": row["stream_id"],
                    "db_state": row["state"],
                    "document": {"bookmark_present": None,
                                 "revisions_found": [],
                                 "region_text_sha256": None},
                    "resolution": "not_tracked_in_doc",
                    "db_state_after": row["state"]})
                continue
            recorded_ids = json.loads(row["revision_ids"]) \
                if row["revision_ids"] else []
            bookmark = scan["bookmarks"].get(row["bookmark"])
            region_sha = _sha256_text(bookmark["text"]) if bookmark else None
            revisions_found = [rid for rid in recorded_ids
                               if rid in doc_revision_ids]
            doc_view = {
                "card_id": row["card_id"],
                "bookmark_present": bookmark is not None,
                "revisions_found": revisions_found,
                "region_text_sha256": region_sha,
            }
            state_after = row["state"]
            resolution = "intact"
            if bookmark is None:
                state_after = "host_removed"
                resolution = "document_authoritative_host_removed"
            elif not revisions_found:
                # 修订标记消失＝宿主动过：以实际文档判定——书签区间现行
                # 文本含新文 → 修订被接受（host_accepted）；否则该编辑已
                # 不在文档 → host_removed。DB 被实际文档改写。
                expected_new = row["new_text"] if row["op"] != "delete" else ""
                if expected_new and expected_new in bookmark["text"]:
                    state_after = "host_accepted"
                    resolution = "document_authoritative_revision_accepted"
                else:
                    state_after = "host_removed"
                    resolution = "document_authoritative_marks_gone"
            if state_after != row["state"]:
                connection.execute(
                    "UPDATE cards SET state=?, state_reason=?, updated_at=?"
                    " WHERE card_key=?",
                    (state_after, resolution, _now(), row["card_key"]))
                _record_event(connection, "reconcile", row["card_key"],
                              json.dumps({
                                  "from": row["state"], "to": state_after,
                                  "resolution": resolution,
                                  "bookmark_present": bookmark is not None,
                                  "doc_digest": digest},
                                  ensure_ascii=False))
            report_cards.append({
                "card_id": row["card_id"], "stream_id": row["stream_id"],
                "db_state": row["state"],
                "document": doc_view, "resolution": resolution,
                "db_state_after": state_after})
        known_bookmarks = {row["bookmark"] for row in rows if row["bookmark"]}
        for name in sorted(scan["bookmarks"]):
            if name not in known_bookmarks:
                _record_event(connection, "reconcile", None,
                              json.dumps({"unknown_bookmark": name}))
        connection.commit()
    return {"schema": SCHEMA, "document_id": document_id,
            "doc_digest": digest,
            "doc_bookmarks": sorted(scan["bookmarks"]),
            "doc_revision_count": len(scan["revisions"]),
            "cards": report_cards,
            "authoritative": "document"}


def edits_cards(state_root: Path, document_id: str) -> dict:
    directory = _require_doc_dir(state_root, document_id)
    parts = load_docx_parts(directory / "working.docx")
    scan = scan_document(parts)
    with closing(_connect(directory)) as connection:
        rows = connection.execute(
            "SELECT * FROM cards WHERE document_id=? ORDER BY rowid",
            (document_id,)).fetchall()
        cards = [{
            "card_id": row["card_id"], "stream_id": row["stream_id"],
            "op": row["op"], "quote": row["quote"],
            "new_text": row["new_text"], "reason": row["reason"],
            "state": row["state"], "state_reason": row["state_reason"],
            "quote_sha256": row["quote_sha256"],
            "bookmark": row["bookmark"],
            "revision_ids": json.loads(row["revision_ids"])
            if row["revision_ids"] else [],
            "bookmark_present": bool(row["bookmark"])
            and row["bookmark"] in scan["bookmarks"],
        } for row in rows]
    return {"schema": SCHEMA, "document_id": document_id,
            "doc_digest": content_digest(parts), "cards": cards}


# --------------------------------------------------------------------------
# 面入口（legal_entry 冻结方法组 edits.*）
# --------------------------------------------------------------------------

EDITS_METHODS = frozenset({
    "edits.register", "edits.stream_open", "edits.stream_push",
    "edits.stream_close", "edits.locate", "edits.apply",
    "edits.read_document", "edits.reconcile", "edits.cards",
})


def edits_call(method: str, args: dict, config: dict) -> dict:
    if method not in EDITS_METHODS:
        raise _fail("f48_method_not_connected:" + method)
    if not isinstance(args, dict):
        raise _fail("f48_params_invalid:args")
    root = config.get("edits_state_root")
    if not root:
        raise _fail("f48_state_root_missing")
    state_root = Path(root)
    document_id = args.get("document_id")
    if method == "edits.register":
        return edits_register(state_root, document_id,
                              _b64decode(args.get("bytesB64")))
    if not isinstance(document_id, str) or not document_id:
        raise _fail("f48_document_id_invalid")
    if method in ("edits.read_document", "edits.reconcile", "edits.cards"):
        return {
            "edits.read_document": edits_read_document,
            "edits.reconcile": edits_reconcile,
            "edits.cards": edits_cards,
        }[method](state_root, document_id)
    stream_id = args.get("stream_id")
    if method == "edits.stream_open":
        if not isinstance(stream_id, str):
            raise _fail("f48_stream_id_invalid")
        return edits_stream_open(state_root, document_id, stream_id)
    if not isinstance(stream_id, str) or not stream_id:
        raise _fail("f48_stream_id_invalid")
    if method == "edits.stream_push":
        return edits_stream_push(state_root, document_id, stream_id,
                                 args.get("chunk"))
    if method == "edits.stream_close":
        return edits_stream_close(state_root, document_id, stream_id)
    if method == "edits.locate":
        return edits_locate(state_root, document_id, stream_id)
    return edits_apply(state_root, document_id, stream_id,   # edits.apply
                       args.get("card_ids"), args.get("reject_card_ids"),
                       args.get("revision_author"),
                       args.get("revision_date"))
