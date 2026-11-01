# -*- coding: utf-8 -*-
"""F119 证据目录/清单生成（W4-U51）——产品侧公开面。

义务 06:F119（v1.5；owner=product+harness；17 卡 P02/P04）：「证据编号/
页段/待证事项真实生成横向目录；媒体加工单独可回读」。证据→质证→报告
主链的取证段：目录**真实生成**＝从 harness 证据目录账（W4-U51 账本半
边，schema v33 evidence_catalog_entries）头行投影，不凭空编行——空目
录具名拒不产空文书；页段逐段绑定 E12 解析产物（material.parse_* 页号
版本链当前版本，解析不到＝fail-closed 拒，不猜页码）；横向 docx 纯
Python 生成（F45 docx_edit 同构：可打开、独立保真检查器八维硬门、同
输入两跑同字节）；媒体加工（视频抽帧/PDF 转图）确定性执行后单独留痕
入 harness 媒体账（evidence_media_ops，输入/逐输出 sha256），产物落
本面状态根 append-only 可逐字节回读。

单一条流：

  harness.evidence_list（目录头行，真实在账证据）
    ├─ 页段绑定：material.parse_*（E12 解析产物页号当前版本）逐段解析
    ├─ 媒体加工列：harness.evidence_media_op_list 留痕投影
    ├─ 关联质证列：harness.cross_exam_list 主张绑定投影（证据→质证链）
    ├─ 生成横向 A4 docx（纯 Python xml.etree；zip 时间戳钉定）
    ├─ 八维硬门（python-docx/lxml 独立解析路径；不过＝typed 拒不留产物）
    └─ outputs/<seq>/ append-only（output.json＋catalog.docx）

媒体加工（evidencecat.media_process）：
  harness.evidence_read（必须钉在账证据）→ harness.read_material
  （源材料 CAS 随读必验）→ 确定性加工（pdf_to_image＝pypdfium2 固定
  scale 渲染＋自带 PNG 编码器；video_frame_extract＝ffmpeg 钉定参数
  逐 seek 抽帧）→ 逐输出 sha256 → harness.evidence_media_op_record
  （留痕入账）→ 状态根逐字节回读。引擎缺席＝探测具名缺口
  （F40 未安装如实先例），绝不假留痕。

纪律（全部与既有面同基线）：
- 确定性：零模型、零网络、零随机、零时钟入产物；同输入两跑同字节。
- fail-closed：未配置状态根/桥、目录为空、页段解析不到、材料锚不存在、
  闸/账本具名拒透传——一律 typed error（f119_*），错误码不携材料内容。
- 边界（如实）：目录排版仅横向 A4 一形；意见/报告文书属 F120/后续面；
  视频抽帧引擎＝本机 PATH 的 ffmpeg（缺席具名 NOT_INSTALLED，F40 纪
  律）；媒体加工不修改原件（源字节 CAS 只读）。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import struct
import subprocess
import threading
import zipfile
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = "juscite-f119-evidence-catalog/1"
STATE_SUBDIR = "evidence-catalog"

# 横向 A4（twips）：w:pgSz w=16838 h=11906 orient=landscape。
PAGE_W_TWIPS = 16838
PAGE_H_TWIPS = 11906

# 目录列（冻结闭集；八维硬门 D4 钉定）。
COLUMNS = ("证据编号", "证据名称", "证据形式", "举证方", "页段",
           "待证事项", "媒体加工", "关联质证")

KIND_LABELS = {
    "documentary": "书证", "physical": "物证", "audio_video": "视听资料",
    "electronic": "电子数据", "witness": "证人证言", "expert": "鉴定意见",
    "inspection": "勘验笔录", "statement": "当事人陈述",
}
PARTY_LABELS = {
    "plaintiff": "原告", "defendant": "被告",
    "third_party": "第三人", "court": "法院",
}

_MATTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_REQUEST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_LOCK = threading.Lock()

# 确定性 AST 面：ffmpeg 子进程实参闭集（引擎钉定调用形，非自由命令面）。
_FFMPEG_ARGV = ("ffmpeg", "-nostdin", "-loglevel", "error", "-threads", "1",
                "-y")


class EvidenceCatalogError(ValueError):
    """Typed F119 face failure; str() is a code, never material content."""

    error_code = "f119_invalid"


def _fail(code: str) -> EvidenceCatalogError:
    return EvidenceCatalogError(code)


def _q(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def content_digest(docx_bytes: bytes) -> str:
    """部件级内容摘要（zip 容器时间戳不参与）——跨次生成可复现锚。"""
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        parts = [f"{info.filename}:{_sha256(zf.read(info.filename))}"
                 for info in zf.infolist()]
    return _sha256("\n".join(sorted(parts)).encode("utf-8"))


def _bridge_call(method: str, args: dict, config: dict) -> dict:
    """harness 公开面 seam（默认＝legal_entry.call 冻结方法组）。"""
    import legal_entry
    return legal_entry.call(method, args, config)


def _state_root(config: dict) -> Path:
    root = config.get("evidence_catalog_state_root")
    if not root:
        raise _fail("f119_state_root_not_configured")
    return Path(root)


def _matter_root(state_root: Path, matter_id: str) -> Path:
    return state_root / STATE_SUBDIR / matter_id


def _atomic_write(path: Path, payload: bytes) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def _next_output_dir(root: Path) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    seq = 1
    for entry in sorted(outputs.iterdir()):
        if entry.is_dir() and entry.name.isdigit():
            seq = max(seq, int(entry.name) + 1)
    out_dir = outputs / f"{seq:04d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _find_output(root: Path, request_id: str) -> Path | None:
    outputs = root / "outputs"
    if not outputs.is_dir():
        return None
    for entry in sorted(outputs.iterdir(), reverse=True):
        manifest = entry / "output.json"
        if not manifest.is_file():
            continue
        try:
            record = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if record.get("request_id") == request_id:
            return entry
    return None


# ---------------------------------------------------------------------------
# E12 页段绑定（解析产物页号版本链当前版本）
# ---------------------------------------------------------------------------


def _parse_batch_manifest(config: dict, batch_id: str) -> dict:
    """批次清单（documented 布局 <material_parse_state_root>/material-parse/
    <batch>/batch.json；只取身份字段 doc_id/page_count）。"""
    root = config.get("material_parse_state_root")
    if not root:
        raise _fail("f119_parse_state_root_not_configured")
    path = Path(root) / "material-parse" / batch_id / "batch.json"
    if not path.is_file():
        raise _fail("f119_parse_batch_not_registered:" + batch_id)
    try:
        batch = json.loads(path.read_text(encoding="utf-8"))
        docs = {}
        for doc in batch["documents"]:
            pages = doc.get("pages") or []
            docs[str(doc["doc_id"])] = {
                "page_count": int(doc.get("page_count") or len(pages)),
                "pages": sorted(int(p["page"]) for p in pages),
            }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise _fail("f119_parse_batch_manifest_invalid") from None
    return docs


def _bind_segments(config: dict, batch_id: str,
                   segments: list) -> list[dict]:
    """页段→E12 解析产物绑定（解析不到＝typed 拒，绝不猜页码）。

    绑定语义：docId 必须在批次内；页码区间必须落在该 doc 已解析页集内
    （页号版本链当前版本集合；人改页号以当前版本为准——与 F86 阅读序
    同一语义面）。返回逐段绑定凭据（含解析页数）供目录行与八维门共
    用同一来源（不复制第二推导）。
    """
    docs = _parse_batch_manifest(config, batch_id)
    bound = []
    for segment in segments:
        doc_id = str(segment.get("docId"))
        doc = docs.get(doc_id)
        if doc is None:
            raise _fail("f119_segment_doc_not_in_batch:" + doc_id)
        page_from = segment.get("pageFrom")
        page_to = segment.get("pageTo")
        pages = set(doc["pages"])
        if not isinstance(page_from, int) or not isinstance(page_to, int) \
                or page_from < 1 or page_to < page_from \
                or not (page_from in pages and page_to in pages):
            raise _fail("f119_segment_pages_unresolved:" + doc_id)
        bound.append({"docId": doc_id, "pageFrom": page_from,
                      "pageTo": page_to,
                      "parsedPages": doc["page_count"] or len(doc["pages"])})
    return bound


# ---------------------------------------------------------------------------
# 确定性 DOCX 生成（横向目录；纯 xml.etree，zip 时间戳钉定）
# ---------------------------------------------------------------------------


def _el(parent, tag: str, text: str | None = None, **attrs) -> ET.Element:
    node = ET.SubElement(parent, _q(tag)) if parent is not None \
        else ET.Element(_q(tag))
    for key, value in attrs.items():
        node.set(_q(key), value)
    if text is not None:
        node.text = text
    return node


def _cell(width: int, text: str, bold: bool = False) -> ET.Element:
    tc = _el(None, "tc")
    tc_pr = _el(tc, "tcPr")
    _el(tc_pr, "tcW", w=str(width), hRule="atLeast")
    p = _el(tc, "p")
    p_pr = _el(p, "pPr")
    _el(p_pr, "spacing", before="20", after="20")
    run = _el(p, "r")
    if bold:
        r_pr = _el(run, "rPr")
        _el(r_pr, "b")
    _el(run, "t", text)
    return tc


def catalog_document_xml(title: str, rows: list[list[str]]) -> bytes:
    """横向目录 document.xml（确定性：无时钟无随机）。"""
    document = ET.Element(_q("document"))
    body = _el(document, "body")
    title_p = _el(body, "p")
    title_pr = _el(title_p, "pPr")
    _el(title_pr, "jc", val="center")
    title_run = _el(title_p, "r")
    title_rpr = _el(title_run, "rPr")
    _el(title_rpr, "b")
    _el(title_rpr, "sz", val="32")
    _el(title_run, "t", title)
    table = _el(body, "tbl")
    table_pr = _el(table, "tblPr")
    _el(table_pr, "tblW", w=str(PAGE_W_TWIPS - 2000), hRule="dxa")
    widths = (1100, 2600, 1000, 900, 2000, 3600, 1500, 1500)
    grid = _el(table, "tblGrid")
    for width in widths:
        _el(grid, "gridCol", w=str(width))
    header = _el(table, "tr")
    header_pr = _el(header, "trPr")
    _el(header_pr, "tblHeader")
    for width, label in zip(widths, COLUMNS):
        header.append(_cell(width, label, bold=True))
    for row in rows:
        tr = _el(table, "tr")
        for width, text in zip(widths, row):
            tr.append(_cell(width, text))
    sect = _el(body, "sectPr")
    _el(sect, "pgSz", w=str(PAGE_W_TWIPS), h=str(PAGE_H_TWIPS),
        orient="landscape")
    _el(sect, "pgMar", top="1000", right="1100", bottom="1000", left="1100",
        header="0", footer="0", gutter="0")
    ET.register_namespace("w", W_NS)
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' \
        + ET.tostring(document, encoding="utf-8", xml_declaration=False)


_FIXED_PARTS = {
    "[Content_Types].xml":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/'
        '/vnd.openxmlformats-package.relationships+xml"/><Default '
        'Extension="xml" ContentType="application/xml"/><Override '
        'PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>",
    "_rels/.rels":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/></Relationships>',
}


def package_docx(document_xml: bytes) -> bytes:
    """最小 DOCX 包（zip 时间戳钉定＝同输入两跑同字节）。"""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in sorted(_FIXED_PARTS):
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, _FIXED_PARTS[name].encode("utf-8"))
        info = zipfile.ZipInfo("word/document.xml", date_time=_ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        dst.writestr(info, document_xml)
    return out.getvalue()


# ---------------------------------------------------------------------------
# 独立保真检查器（python-docx/lxml 解析路径——与生成引擎不同算路）
# ---------------------------------------------------------------------------

_MARK_TAGS = {"ins", "del", "delText", "commentReference"}


def _lxml_local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) and "}" in tag \
        else tag


def fidelity_check(docx_bytes: bytes, expect: dict) -> dict:
    """八维硬门（不过即 typed 拒，产物不落盘）。

    D1 可打开：python-docx（lxml）真开；正文恰一标题段＋一表。
    D2 横向：section orient=LANDSCAPE 且页宽>页高（A4 横向 16838×11906）。
    D3 干净：零修订标记/零批注引用；无 comments 部件。
    D4 表头：表头行逐格＝冻结列集。
    D5 行数/身份格：数据行数＝在账证据数；编号/名称/形式/举证方逐格
       ＝harness 头行投影。
    D6 页段格：逐格＝E12 绑定投影（docId＋页码区间）。
    D7 待证事项格：逐格＝proveFacts 投影（"；"连接）。
    D8 链路格＋确定性：媒体加工/关联质证逐格＝投影；同输入两跑
       content_digest 相等（由调用方以两跑字节复核后写入本门）。
    """
    try:
        import docx as pydocx
    except ImportError:
        raise _fail("f119_checker_unavailable") from None
    failures = []
    try:
        doc = pydocx.Document(io.BytesIO(docx_bytes))
    except Exception:
        raise _fail("f119_docx_unreadable") from None
    # D1
    if len(doc.tables) != 1 or not doc.paragraphs:
        failures.append("D1_openable")
    # D2
    section = doc.sections[0]
    orientation = str(getattr(section, "orientation", ""))
    width = int(section.page_width.twips) if section.page_width else 0
    height = int(section.page_height.twips) if section.page_height else 0
    if "LANDSCAPE" not in orientation.upper() or width <= height \
            or width != PAGE_W_TWIPS or height != PAGE_H_TWIPS:
        failures.append("D2_landscape")
    # D3（lxml 独立解析）
    import lxml.etree as lxml_etree
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        names = set(zf.namelist())
        root = lxml_etree.fromstring(zf.read("word/document.xml"))
    marks = [el for el in root.iter()
             if _lxml_local(el.tag) in _MARK_TAGS]
    if marks or any(n.startswith("word/comments") for n in names):
        failures.append("D3_clean")
    table = doc.tables[0]
    # D4
    header = [cell.text for cell in table.rows[0].cells]
    if header != list(COLUMNS):
        failures.append("D4_header")
    # D5-D8
    data_rows = table.rows[1:]
    if len(data_rows) != len(expect["rows"]):
        failures.append("D5_row_count")
    else:
        for row, want in zip(data_rows, expect["rows"]):
            cells = [cell.text for cell in row.cells]
            if cells[:4] != want[:4]:
                failures.append("D5_identity:" + want[0])
                break
        for row, want in zip(data_rows, expect["rows"]):
            cells = [cell.text for cell in row.cells]
            if cells[4] != want[4]:
                failures.append("D6_segments:" + want[0])
                break
        for row, want in zip(data_rows, expect["rows"]):
            cells = [cell.text for cell in row.cells]
            if cells[5] != want[5]:
                failures.append("D7_facts:" + want[0])
                break
        for row, want in zip(data_rows, expect["rows"]):
            cells = [cell.text for cell in row.cells]
            if cells[6:] != want[6:]:
                failures.append("D8_chain:" + want[0])
                break
    if failures:
        raise _fail("f119_fidelity_gate_failed:" + ",".join(failures))
    return {"dims": 8, "checker": "python-docx+lxml", "failures": []}


# ---------------------------------------------------------------------------
# 行投影（harness 头行 → 目录行；生成与检查器共用同一投影）
# ---------------------------------------------------------------------------


def _segment_text(bound: list[dict]) -> str:
    parts = []
    for segment in bound:
        parts.append(f"{segment['docId']} 第{segment['pageFrom']}"
                     f"-{segment['pageTo']}页")
    return "；".join(parts)


def _project_rows(evidence_rows: list[dict], bindings: dict,
                  media_by_evidence: dict,
                  claims_by_evidence: dict) -> list[list[str]]:
    rows = []
    for item in evidence_rows:
        bound = bindings[item["evidenceId"]]
        ops = media_by_evidence.get(item["evidenceId"]) or []
        claim_ids = claims_by_evidence.get(item["evidenceId"]) or []
        rows.append([
            item["evidenceNo"], item["name"],
            KIND_LABELS.get(item["kind"], item["kind"]),
            PARTY_LABELS.get(item["sourceParty"], item["sourceParty"]),
            _segment_text(bound),
            "；".join(item["proveFacts"]),
            "；".join(ops) if ops else "—",
            "；".join(claim_ids) if claim_ids else "—",
        ])
    return rows


# ---------------------------------------------------------------------------
# 公开面方法
# ---------------------------------------------------------------------------


def generate(config: dict, args: dict) -> dict:
    """真实生成横向证据目录 docx（F119 acceptance 主断言）。"""
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.fullmatch(matter_id):
        raise _fail("f119_matter_id_invalid")
    parse_batch_id = args.get("parse_batch_id")
    if not isinstance(parse_batch_id, str) or not parse_batch_id:
        raise _fail("f119_parse_batch_id_required")
    request_id = args.get("request_id")
    if not isinstance(request_id, str) or not _REQUEST_RE.fullmatch(request_id):
        raise _fail("f119_request_id_invalid")
    scope = {"kind": "matter", "matterId": matter_id}

    with _LOCK:
        matter_root = _matter_root(_state_root(config), matter_id)
        replay = _find_output(matter_root, request_id)
        if replay is not None:
            record = json.loads(
                (replay / "output.json").read_text(encoding="utf-8"))
            return {key: record[key] for key in
                    ("op", "request_id", "docx_sha256", "content_digest",
                     "rows", "outputs_dir")}

        # 1) 目录头行（真实在账证据；空目录具名拒不产空文书）。
        listing = _bridge_call("harness.evidence_list", {"scope": scope},
                               config)
        evidence_rows = listing.get("items") or []
        if not evidence_rows:
            raise _fail("f119_empty_catalog_no_fabrication")

        # 2) 页段绑定 E12（逐段解析产物；解析不到＝fail-closed）。
        bindings = {}
        for item in evidence_rows:
            bindings[item["evidenceId"]] = _bind_segments(
                config, parse_batch_id, item.get("pageSegments") or [])

        # 3) 媒体加工留痕＋质证绑定投影（证据→质证链）。
        ops = (_bridge_call("harness.evidence_media_op_list", {"scope": scope},
                            config).get("items")) or []
        media_by_evidence: dict[str, list] = {}
        for op in ops:
            media_by_evidence.setdefault(op["evidenceId"], []).append(
                op["mediaOpId"])
        drafts = (_bridge_call("harness.cross_exam_list", {"scope": scope},
                               config).get("items")) or []
        claims_by_evidence: dict[str, list] = {}
        for draft in drafts:
            for claim in draft.get("claims") or []:
                claims_by_evidence.setdefault(
                    claim["evidenceRef"]["id"], []).append(
                    f"{draft['opinionId']}#{claim['claimId']}")

        # 4) 生成（两跑同字节先于落盘）。
        rows = _project_rows(evidence_rows, bindings, media_by_evidence,
                             claims_by_evidence)
        title = f"证据目录（{matter_id}）"
        first = package_docx(catalog_document_xml(title, rows))
        second = package_docx(catalog_document_xml(title, rows))
        if content_digest(first) != content_digest(second):
            raise _fail("f119_determinism_violation")

        # 5) 八维硬门（独立检查器；不过不留产物）。
        expect = {"rows": rows}
        gate = fidelity_check(first, expect)

        # 6) append-only 落盘。
        out_dir = _next_output_dir(matter_root)
        _atomic_write(out_dir / "catalog.docx", first)
        record = {
            "schema": SCHEMA, "op": "evidencecat.generate",
            "request_id": request_id, "matter_id": matter_id,
            "parse_batch_id": parse_batch_id,
            "docx_sha256": _sha256(first),
            "content_digest": content_digest(first),
            "rows": len(rows), "outputs_dir": str(out_dir),
            "fidelity_gate": gate,
            "evidence_ids": [item["evidenceId"] for item in evidence_rows],
        }
        _atomic_write(out_dir / "output.json",
                      json.dumps(record, ensure_ascii=False,
                                 indent=1).encode("utf-8"))
        return {key: record[key] for key in
                ("op", "request_id", "docx_sha256", "content_digest",
                 "rows", "outputs_dir")}


def list_outputs(config: dict, args: dict) -> dict:
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.fullmatch(matter_id):
        raise _fail("f119_matter_id_invalid")
    root = _matter_root(_state_root(config), matter_id) / "outputs"
    items = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            manifest = entry / "output.json"
            if not manifest.is_file():
                continue
            record = json.loads(manifest.read_text(encoding="utf-8"))
            items.append({key: record[key] for key in
                          ("request_id", "docx_sha256", "content_digest",
                           "rows")})
    return {"matter_id": matter_id, "items": items, "count": len(items)}


def read_output(config: dict, args: dict) -> dict:
    import base64
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.fullmatch(matter_id):
        raise _fail("f119_matter_id_invalid")
    request_id = args.get("request_id")
    if not isinstance(request_id, str) or not _REQUEST_RE.fullmatch(request_id):
        raise _fail("f119_request_id_invalid")
    out_dir = _find_output(_matter_root(_state_root(config), matter_id),
                           request_id)
    if out_dir is None:
        raise _fail("f119_output_not_found")
    payload = (out_dir / "catalog.docx").read_bytes()
    record = json.loads((out_dir / "output.json").read_text(encoding="utf-8"))
    if _sha256(payload) != record.get("docx_sha256"):
        raise _fail("f119_output_bytes_changed")
    return {
        "matter_id": matter_id, "request_id": request_id,
        "docx_sha256": record["docx_sha256"],
        "content_digest": record["content_digest"],
        "bytes": len(payload), "docx_b64": base64.b64encode(payload)
        .decode("ascii"),
    }


# ---------------------------------------------------------------------------
# 媒体加工（视频抽帧 / PDF 转图）：确定性执行＋单独留痕可回读
# ---------------------------------------------------------------------------


def media_probe(config: dict, args: dict) -> dict:
    """引擎探测（缺席具名 NOT_INSTALLED——F40 未安装如实先例）。"""
    engines = {}
    try:
        import pypdfium2 as _pdfium  # noqa: F401
        engines["pdf_to_image"] = {"available": True,
                                   "engine": "pypdfium2"}
    except ImportError:
        engines["pdf_to_image"] = {"available": False,
                                   "engine": "pypdfium2",
                                   "status": "NOT_INSTALLED"}
    try:
        proc = subprocess.run(("ffmpeg", "-version"),
                              capture_output=True, timeout=30)
        first = proc.stdout.decode("utf-8", "replace").splitlines()[0] \
            if proc.returncode == 0 and proc.stdout else ""
        engines["video_frame_extract"] = {
            "available": proc.returncode == 0,
            "engine": "ffmpeg",
            "version": first[:120],
            **({} if proc.returncode == 0
               else {"status": "NOT_INSTALLED"})}
    except (OSError, subprocess.SubprocessError):
        engines["video_frame_extract"] = {"available": False,
                                          "engine": "ffmpeg",
                                          "status": "NOT_INSTALLED"}
    return {"schema": SCHEMA, "engines": engines}


def _png_encode(width: int, height: int, rgba: bytes,
                stride: int | None = None) -> bytes:
    """最小确定性 PNG 编码（zlib/struct；color type 6 RGBA）。

    stride＝pdfium 位图行距（可能大于 width*4 的行对齐）；逐行按
    stride 切，行内截前 width*4 字节。"""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    stride = stride if stride is not None else width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:y * stride + width * 4]
                   for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _media_root(state_root: Path, matter_id: str) -> Path:
    return state_root / "media" / matter_id


def media_process(config: dict, args: dict) -> dict:
    """执行一次确定性媒体加工并留痕入账（harness.evidence_media_op_record）。"""
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.fullmatch(matter_id):
        raise _fail("f119_matter_id_invalid")
    media_op_id = args.get("media_op_id")
    if not isinstance(media_op_id, str) or not _REQUEST_RE.fullmatch(
            media_op_id):
        raise _fail("f119_media_op_id_invalid")
    actor_id = args.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        raise _fail("f119_actor_required")
    evidence_id = args.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise _fail("f119_evidence_id_required")
    op_kind = args.get("op_kind")
    if op_kind not in ("video_frame_extract", "pdf_to_image"):
        raise _fail("f119_media_op_kind_invalid")
    source = args.get("source") or {}
    material_id = source.get("material_id")
    revision = source.get("revision")
    if not isinstance(material_id, str) or not material_id \
            or not isinstance(revision, int) or isinstance(revision, bool) \
            or revision < 1:
        raise _fail("f119_media_source_invalid")
    scope = {"kind": "matter", "matterId": matter_id}

    # 必须钉在账证据（头行存在性；账本具名码透传为 f119_evidence_unresolved）。
    try:
        _bridge_call("harness.evidence_read",
                     {"scope": scope, "evidence_id": evidence_id}, config)
    except EvidenceCatalogError:
        raise
    except Exception as exc:
        raise _fail("f119_evidence_unresolved:"
                    + str(exc).split(":", 1)[0][:40]) from None

    # 源材料 CAS 随读必验（原件只读；加工不改原件）。
    readback = _bridge_call("harness.read_material",
                            {"scope": scope, "material_id": material_id,
                             "revision": revision}, config)
    import base64
    source_bytes = base64.b64decode(readback["bytesB64"])
    if _sha256(source_bytes) != readback.get("sha256"):
        raise _fail("f119_media_source_bytes_changed")

    if op_kind == "pdf_to_image":
        dpi = args.get("dpi")
        if not isinstance(dpi, int) or isinstance(dpi, bool) \
                or not (72 <= dpi <= 1200):
            raise _fail("f119_media_params_invalid")
        pages = args.get("pages")
        if not isinstance(pages, list) or not pages \
                or not all(isinstance(p, int) and not isinstance(p, bool)
                           and p >= 1 for p in pages):
            raise _fail("f119_media_params_invalid")
        rendered = _render_pdf_pages(source_bytes, dpi, pages)
        engine = "pypdfium2"
        params = {"dpi": dpi, "pages": pages}
    else:
        seeks = args.get("seek_times_sec")
        max_frames = args.get("max_frames", len(seeks or []))
        if not isinstance(seeks, list) or not seeks \
                or not all(isinstance(s, int) and not isinstance(s, bool)
                           and s >= 0 for s in seeks):
            raise _fail("f119_media_params_invalid")
        if not isinstance(max_frames, int) or isinstance(max_frames, bool) \
                or not (1 <= max_frames <= 1000):
            raise _fail("f119_media_params_invalid")
        probe = media_probe(config, {})
        engine_info = probe["engines"]["video_frame_extract"]
        if not engine_info.get("available"):
            # 引擎缺席＝具名缺口（绝不假留痕）。
            raise _fail("f119_media_engine_not_installed:ffmpeg")
        rendered = _extract_video_frames(source_bytes, seeks, max_frames,
                                         media_op_id)
        engine = "ffmpeg"
        params = {"seekTimesSec": seeks, "maxFrames": max_frames}

    # 产物先落盘（append-only；sha 以落盘字节为准），再留痕入账。
    outputs = []
    with _LOCK:
        op_dir = _media_root(_state_root(config), matter_id) / media_op_id
        if op_dir.exists():
            raise _fail("f119_media_op_dir_conflict")
        op_dir.mkdir(parents=True, exist_ok=True)
        try:
            for item in rendered:
                _atomic_write(op_dir / item["label"], item["payload"])
                outputs.append({"index": item["index"],
                                "label": item["label"],
                                "sha256": _sha256(item["payload"]),
                                "bytes": len(item["payload"])})
        except Exception:
            for item in rendered:
                (op_dir / item["label"]).unlink(missing_ok=True)
            op_dir.rmdir()
            raise

    # 留痕入账（输入 sha 钉定＋逐输出 sha/字节）。
    op_record = _bridge_call("harness.evidence_media_op_record", {
        "actor_id": actor_id, "scope": scope,
        "key": {"requestId": f"{media_op_id}", "targetId": None,
                "expectedRevision": None, "inputRefs": []},
        "media_op": {
            "mediaOpId": media_op_id, "evidenceId": evidence_id,
            "opKind": op_kind, "engine": engine, "params": params,
            "inputRef": {"materialId": material_id, "revision": revision,
                         "sha256": _sha256(source_bytes)},
            "outputs": outputs,
        }}, config)
    return {"op": "evidencecat.media_process", "matter_id": matter_id,
            "media_op_id": media_op_id, "evidence_id": evidence_id,
            "op_kind": op_kind, "engine": engine, "outputs": outputs,
            "receipt": op_record.get("receipt")}


def _render_pdf_pages(source_bytes: bytes, dpi: int,
                      pages: list[int]) -> list[dict]:
    """PDF→图（pypdfium2 固定 scale 确定性渲染＋自带 PNG 编码）。"""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise _fail("f119_media_engine_not_installed:pypdfium2") from None
    rendered = []
    try:
        doc = pdfium.PdfDocument(source_bytes)
    except Exception:
        raise _fail("f119_media_source_unreadable") from None
    try:
        scale = dpi / 72.0
        for page_index in pages:
            if page_index > len(doc):
                raise _fail("f119_media_page_out_of_range")
            page = doc[page_index - 1]
            bitmap = page.render(scale=scale, rev_byteorder=True)
            rendered.append({"index": page_index,
                             "label": f"page-{page_index:04d}.png",
                             "payload": _png_encode(bitmap.width,
                                                    bitmap.height,
                                                    bytes(bitmap.buffer),
                                                    bitmap.stride)})
    finally:
        doc.close()
    return rendered


def _extract_video_frames(source_bytes: bytes, seeks: list[int],
                          max_frames: int, media_op_id: str) -> list[dict]:
    """视频抽帧（ffmpeg 钉定参数逐 seek 抽帧；确定性解码）。"""
    import tempfile
    rendered = []
    with tempfile.TemporaryDirectory(
            prefix=f"f119-frames-{media_op_id[:24]}-") as workdir:
        src = Path(workdir) / "source.bin"
        src.write_bytes(source_bytes)
        for order, seek in enumerate(seeks[:max_frames]):
            target = Path(workdir) / f"frame-{order:04d}.png"
            argv = (*_FFMPEG_ARGV, "-ss", str(seek), "-i", str(src),
                    "-frames:v", "1", str(target))
            proc = subprocess.run(argv, capture_output=True, timeout=120)
            if proc.returncode != 0 or not target.is_file():
                raise _fail("f119_media_extract_failed")
            rendered.append({"index": order,
                             "label": f"seek-{seek:06d}.png",
                             "payload": target.read_bytes()})
    return rendered


def media_read(config: dict, args: dict) -> dict:
    """留痕回读：账面行＋产物逐字节复验（sha 不符＝具名拒）。"""
    import base64
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.fullmatch(matter_id):
        raise _fail("f119_matter_id_invalid")
    media_op_id = args.get("media_op_id")
    if not isinstance(media_op_id, str) or not _REQUEST_RE.fullmatch(
            media_op_id):
        raise _fail("f119_media_op_id_invalid")
    trail = _bridge_call("harness.evidence_media_op_read",
                         {"scope": {"kind": "matter", "matterId": matter_id},
                          "media_op_id": media_op_id}, config)
    op_dir = _media_root(_state_root(config), matter_id) / media_op_id
    outputs = []
    for output in trail.get("outputs") or []:
        path = op_dir / output["label"]
        if not path.is_file():
            raise _fail("f119_media_output_missing:" + output["label"])
        payload = path.read_bytes()
        if _sha256(payload) != output["sha256"]:
            raise _fail("f119_media_output_bytes_changed:" + output["label"])
        outputs.append({
            "index": output["index"], "label": output["label"],
            "sha256": output["sha256"], "bytes": len(payload),
            "png_b64": base64.b64encode(payload).decode("ascii"),
        })
    return {"op": "evidencecat.media_read", "matter_id": matter_id,
            "media_op_id": media_op_id, "evidence_id": trail["evidenceId"],
            "op_kind": trail["opKind"], "engine": trail["engine"],
            "params": trail.get("params"),
            "input_ref": trail.get("inputRef"), "outputs": outputs}


def evidence_catalog_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发（evidencecat.*）。未列方法绝不落到这里。"""
    if method == "evidencecat.generate":
        return generate(config, args)
    if method == "evidencecat.list":
        return list_outputs(config, args)
    if method == "evidencecat.read":
        return read_output(config, args)
    if method == "evidencecat.media_probe":
        return media_probe(config, args)
    if method == "evidencecat.media_process":
        return media_process(config, args)
    if method == "evidencecat.media_read":
        return media_read(config, args)
    raise EvidenceCatalogError("f119_method_unknown:" + method)
