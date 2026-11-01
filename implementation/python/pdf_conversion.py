"""F54 PDF→docx 转换候选与保真检查（W2b-U17）：产品侧 document-adapter
公开面——扫描件/PDF 材料进修订线（红线管线）的入口。

义务 06:F54 断言：「保存原PDF和转换候选；纯文本重建明确损失，实际版面/
表/页眉脚对照，不称自动保真；LibreOffice优先转换；结构保真实际对照，
未保真标损失」。§6.1 裁决#5：LibreOffice 已装（C:\\Program Files\\LibreOffice，
B2b 就绪）。

纪律（全部实测钉定，LibreOffice 26.8.1.1 亲测）：
- LibreOffice 优先＝唯一自动转换器：soffice --headless
  --infilter=writer_pdf_import --convert-to docx:MS Word 2007 XML
  （确定性 CLI，非模型）。PDF 默认经 Draw 导入（无 docx 出口，实测
  exit 1 no export filter），必须显式走 Writer 导入过滤器。Windows 上
  必须用 soffice.com（控制台阻塞二进制；soffice.exe 分离返回拿不到
  输出与真退出码）。绝不静默换第二引擎。
- 双留存：state/pdf-conversion/<document_id>/original.pdf（注册时复制，
  sha256 钉定，永不覆盖——同 id 再注册字节不符=fail-closed）＋
  candidates/<seq>-<kind>/candidate.docx（append-only 顺序号，不删不改）。
- 不称自动保真：保真报告只做**实测结构对照**（五维：正文文本/页面几何/
  分页流/表格/页眉页脚），每维给 preserved/loss 实测状态与计数，
  auto_fidelity_claimed 恒 false；未保真标损失（losses 列表）。
  实测结论（本机 26.8.1.1）：Writer PDF 导入保留文本内容、页面尺寸与
  显式分页，但表格结构与页眉页脚部件**不重建**（内容以正文文本存活），
  图像页无文本层——如实记 loss，不装样子。
- 纯文本重建：conversion.rebuild 从留存原件抽文本逐行重建 docx（显式
  分页＋页面尺寸），损失闭集显式标注（表格结构/页眉页脚/图形图像/
  字体版面/精确排版），与转换候选拿同一对照器实测。
- 转换候选入 U14 红线管线：候选清单 schema=juscite-f54-pdf-conversion/1
  （candidate.json，含原件/候选双 sha、引擎身份、五维保真、losses、
  redline 块[editable_text/route]）即 W2b-U14 修订线消费契约；本面不
  前造修订线本身。

fail-closed：未配置状态根/soffice、PDF 不可读、转换失败或无产物、
原件字节变化、document_id 非法——一律 typed error（f54_* 错误码），
绝不产出假候选、绝不称保真。错误码不携材料内容（同 material.parse_*
红线）。确定性：无模型、无网络、无随机；docx 内容摘要（部件级 sha）
跨次转换复现（zip 容器时间戳不参与摘要）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f54-pdf-conversion/1"
STATE_SUBDIR = "pdf-conversion"
KINDS = ("libreoffice", "text_rebuild")
# 纯文本重建的显式损失闭集（06:F54「纯文本重建明确损失」）
REBUILD_LOSSES = (
    "table_structure",          # 表格结构（行列网格）不重建
    "header_footer_structure",  # 页眉页脚部件不重建（文本混入正文）
    "graphics_images",          # 图形/图像/照片不携带
    "fonts_styling",            # 字体/字号/粗斜体等样式不保留
    "precise_positioning",      # 精确坐标排版（缩进/行距/对齐）不保留
)
# 页眉页脚边带（页高百分比；PDF 侧几何分带口径，报告显式携带）
EDGE_BAND_PCT = 10
# 页面几何容差（pt，整数比较）
GEOMETRY_TOLERANCE_PT = 2

_DOC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SOFFICE_TIMEOUT_DEFAULT = 300

# 引擎身份缓存（每进程一次 --version 探测）
_ENGINE_CACHE: dict[str, str] = {}
# 单写者纪律：soffice 共享 UserInstallation 配置目录，进程内串行
_LOCK = threading.Lock()


class ConversionError(ValueError):
    """Typed F54 face failure; str() is a code, never material content."""

    error_code = "f54_invalid"


def _fail(code: str) -> ConversionError:
    return ConversionError(code)


# --------------------------------------------------------------------------
# 引擎（LibreOffice 优先＝唯一自动转换器）
# --------------------------------------------------------------------------

def _resolve_soffice(config: dict) -> Path | None:
    """解析 soffice 可执行：config libreoffice_soffice；Windows 下路径指
    soffice.exe 时若同目录存在 soffice.com 则确定性改用 .com（控制台阻塞
    二进制——.exe 分离返回，拿不到输出与真退出码；实测）。"""
    raw = config.get("libreoffice_soffice")
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    if os.name == "nt" and path.name.lower() == "soffice.exe":
        com = path.with_name("soffice.com")
        if com.is_file():
            return com
    return path if path.is_file() else None


def engine_report(config: dict) -> dict:
    """引擎探针（F40 ports 同式如实口径）：未配置/不可执行=NOT_INSTALLED，
    不装样子；可执行则实测 --version。"""
    binary = _resolve_soffice(config)
    report: dict = {
        "schema": SCHEMA, "engine": "libreoffice", "priority": 1,
        "configured": bool(config.get("libreoffice_soffice")),
    }
    if binary is None:
        report.update({"installed": False, "status": "NOT_INSTALLED"})
        if report["configured"]:
            report["note"] = "configured_binary_missing"
        return report
    key = str(binary)
    version = _ENGINE_CACHE.get(key)
    if version is None:
        try:
            proc = subprocess.run(
                [str(binary), "--version"], capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=60)
            first = (proc.stdout or "").strip().splitlines()
            version = (first[0].split()[1]
                       if proc.returncode == 0 and first
                       and first[0].lower().startswith("libreoffice") else "")
        except (subprocess.TimeoutExpired, OSError):
            version = ""
        if version:
            _ENGINE_CACHE[key] = version
    report.update({
        "installed": True,
        "status": "READY" if version else "VERSION_PROBE_FAILED",
        "binary": str(binary),
        "version": version or None,
        "infilter": "writer_pdf_import",
        "export_filter": "MS Word 2007 XML",
    })
    return report


def _soffice_version(binary: Path) -> str:
    return _ENGINE_CACHE.get(str(binary)) or ""


# --------------------------------------------------------------------------
# PDF 事实抽取（pypdfium2，确定性）
# --------------------------------------------------------------------------

def pdf_facts(pdf_path: Path) -> dict:
    """原 PDF 实测结构事实：页数/每页尺寸(pt)/每页文本行（pdfium rect 粒度
    ）/边带行（页眉页脚几何分带口径 EDGE_BAND_PCT）。只读，不写。"""
    import pypdfium2 as pdfium

    pages: list[dict] = []
    try:
        doc = pdfium.PdfDocument(str(pdf_path))
        try:
            for page in doc:
                w, h = page.get_size()
                band = h * EDGE_BAND_PCT / 100.0
                tp = page.get_textpage()
                lines: list[dict] = []
                try:
                    for i in range(tp.count_rects()):
                        l, b, r, t = tp.get_rect(i)
                        text = tp.get_text_bounded(l, b, r, t).strip()
                        if not text:
                            continue
                        zone = ("header" if t >= h - band
                                else "footer" if b <= band else "body")
                        lines.append({"text": text, "zone": zone})
                finally:
                    tp.close()
                pages.append({
                    "index": len(pages) + 1,
                    "width_pt": round(float(w), 1),
                    "height_pt": round(float(h), 1),
                    "lines": lines,
                })
                page.close()
        finally:
            doc.close()
    except Exception as exc:
        raise _fail("f54_pdf_unreadable:" + type(exc).__name__) from None
    return {"pages": pages, "page_count": len(pages)}


def _page_line_multisets(facts: dict) -> list[Counter]:
    return [Counter(line["text"] for line in page["lines"])
            for page in facts["pages"]]


def _edge_lines(facts: dict) -> list[str]:
    """边带行（页眉页脚几何分带口径 EDGE_BAND_PCT）：凡落入页顶/页底
    边带的文本行（含逐页变化的页码页脚）。边带是文档化几何启发（带页
    正文首行可能与带缘相交——实测口径），报告携带 band 百分比供判读。"""
    out: set[str] = set()
    for page in facts["pages"]:
        for line in page["lines"]:
            if line["zone"] in ("header", "footer"):
                out.add(line["text"])
    return sorted(out)


# --------------------------------------------------------------------------
# docx 事实抽取（zipfile＋ElementTree，确定性；无第三方依赖）
# --------------------------------------------------------------------------

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_NS = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"


def _docx_parse(docx_path: Path) -> dict:
    """候选 docx 实测结构事实。mc:Fallback 分支是 mc:Choice 的复制载体
    （Writer PDF 导入实测结构），文本抽取跳过 Fallback＝按逻辑内容去重；
    分页按 w:br[@w:type='page'] 切页（break 后文本归下页）。"""
    import xml.etree.ElementTree as ET

    try:
        zf = zipfile.ZipFile(docx_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise _fail("f54_docx_unreadable:" + type(exc).__name__) from None
    with zf:
        try:
            root = ET.fromstring(zf.read("word/document.xml"))
        except (KeyError, ET.ParseError) as exc:
            raise _fail("f54_docx_invalid:" + type(exc).__name__) from None
        body = root.find(_W_NS + "body")

        # 页面尺寸（twips→pt）
        sizes: list[tuple[int, int]] = []
        for sect in root.iter(_W_NS + "sectPr"):
            pgsz = sect.find(_W_NS + "pgSz")
            if pgsz is not None:
                sizes.append((round(int(pgsz.get(_W_NS + "w", "0")) / 20),
                              round(int(pgsz.get(_W_NS + "h", "0")) / 20)))

        parent = {c: p for p in root.iter() for c in p}

        def _in_fallback(node) -> bool:
            while node in parent:
                node = parent[node]
                if node.tag == _MC_NS + "Fallback":
                    return True
            return False

        page_texts: list[list[str]] = [[]]
        page_breaks = 0

        def _walk(node):
            nonlocal page_breaks
            for child in node:
                if child.tag == _MC_NS + "Fallback":
                    continue          # Choice/Fallback 同内容，只取 Choice
                if child.tag == _W_NS + "br" \
                        and child.get(_W_NS + "type") == "page":
                    page_breaks += 1
                    page_texts.append([])
                elif child.tag == _W_NS + "t":
                    text = (child.text or "").strip()
                    if text:
                        page_texts[-1].append(text)
                _walk(child)

        if body is not None:
            _walk(body)

        # 表格（w:tbl：行×列×单元格文本）
        tables: list[dict] = []
        if body is not None:
            for tbl in body.iter(_W_NS + "tbl"):
                rows_out = []
                for tr in tbl.findall(_W_NS + "tr"):
                    cells = []
                    for tc in tr.findall(_W_NS + "tc"):
                        cells.append("".join(
                            t.text or "" for t in tc.iter(_W_NS + "t")
                            if not _in_fallback(t)).strip())
                    rows_out.append(cells)
                tables.append({"rows": len(rows_out),
                               "cols": max((len(r) for r in rows_out),
                                           default=0),
                               "cells": rows_out})

        # 页眉页脚部件
        hf_parts: list[dict] = []
        for name in sorted(zf.namelist()):
            base = name.rsplit("/", 1)[-1]
            if not (base.startswith("header") or base.startswith("footer")) \
                    or not base.endswith(".xml"):
                continue
            try:
                part = ET.fromstring(zf.read(name))
            except ET.ParseError:
                continue
            texts = [t.text.strip() for t in part.iter(_W_NS + "t")
                     if (t.text or "").strip()]
            hf_parts.append({"part": base,
                             "kind": "header" if base.startswith("header")
                             else "footer",
                             "texts": texts})

        return {
            "page_sizes_pt": sizes,
            "page_breaks": page_breaks,
            "pages_text": page_texts,
            "tables": tables,
            "header_footer_parts": hf_parts,
        }


def _docx_page_multisets(parsed: dict) -> list[Counter]:
    return [Counter(texts) for texts in parsed["pages_text"]]


def docx_content_digest(docx_path: Path) -> str:
    """部件级内容摘要：zip 容器时间戳不参与（LibreOffice 两跑实测：部件
    全同、仅 zip mtime 异）——跨次转换可复现的确定性锚。"""
    with zipfile.ZipFile(docx_path) as zf:
        parts = []
        for info in zf.infolist():
            digest = hashlib.sha256(zf.read(info.filename)).hexdigest()
            parts.append(f"{info.filename}:{digest}")
    return hashlib.sha256("\n".join(sorted(parts)).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 纯文本重建 docx 写出（最小 OOXML，确定性）
# --------------------------------------------------------------------------

def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def write_text_rebuild_docx(out_path: Path, facts: dict) -> dict:
    """从 PDF 事实逐行纯文本重建：每行一段落、每页显式分页、页面尺寸取
    原 PDF（非排版还原声明）。损失闭集 REBUILD_LOSSES 由调用方记入清单。"""
    first = facts["pages"][0]
    w_tw = int(round(first["width_pt"] * 20))
    h_tw = int(round(first["height_pt"] * 20))
    paragraphs: list[str] = []
    for pi, page in enumerate(facts["pages"]):
        if pi:
            paragraphs.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        for line in page["lines"]:
            paragraphs.append(
                "<w:p><w:r><w:t xml:space=\"preserve\">"
                + _xml_escape(line["text"]) + "</w:t></w:r></w:p>")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        + "".join(paragraphs)
        + f'<w:sectPr><w:pgSz w:w="{w_tw}" w:h="{h_tw}"/>'
          '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134"'
          ' w:left="1134"/></w:sectPr></w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/><Default Extension='
        '"xml" ContentType="application/xml"/><Override PartName="/word/'
        'document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://'
        'schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/></Relationships>')
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"/>')
    tmp = out_path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
    os.replace(tmp, out_path)
    return {"pages": len(facts["pages"]),
            "lines": sum(len(p["lines"]) for p in facts["pages"])}


# --------------------------------------------------------------------------
# 保真对照（实测五维；不称自动保真）
# --------------------------------------------------------------------------

def fidelity_report(pdf: dict, docx_parsed: dict,
                    gold_tables: list[dict] | None = None) -> dict:
    """原 PDF ↔ 候选 docx 实测结构对照。每维给实测计数与状态；未保真标
    损失；auto_fidelity_claimed 恒 false（06:F54「不称自动保真」）。"""
    losses: list[str] = []
    dimensions: dict[str, dict] = {}

    # 1) 正文文本（逐页多重集对照；边带行计入文本面）
    pdf_pages = _page_line_multisets(pdf)
    docx_pages = _docx_page_multisets(docx_parsed)
    total = missing = extra = 0
    per_page = []
    for pi, pdf_counter in enumerate(pdf_pages):
        docx_counter = docx_pages[pi] if pi < len(docx_pages) else Counter()
        gone = pdf_counter - docx_counter
        added = docx_counter - pdf_counter
        total += sum(pdf_counter.values())
        missing += sum(gone.values())
        extra += sum(added.values())
        per_page.append({"page": pi + 1,
                         "pdf_lines": sum(pdf_counter.values()),
                         "docx_lines": sum(docx_counter.values()),
                         "missing": sum(gone.values()),
                         "extra": sum(added.values())})
    if total == 0:
        text_status = "no_text_layer"       # 原 PDF 无文本层（扫描件口径）
    elif missing == 0:
        text_status = "preserved"
    elif missing < total:
        text_status = "partial_loss"
    else:
        text_status = "loss"
    dimensions["text_content"] = {
        "status": text_status, "pdf_lines": total, "docx_lines":
        sum(sum(c.values()) for c in docx_pages),
        "missing_lines": missing, "extra_lines": extra, "per_page": per_page,
    }
    if text_status in ("partial_loss", "loss"):
        losses.append("text_content")

    # 2) 页面几何（PDF 每页尺寸 vs docx sectPr；±2pt 容差整数比较）
    pdf_sizes = [(round(p["width_pt"]), round(p["height_pt"]))
                 for p in pdf["pages"]]
    docx_sizes = docx_parsed["page_sizes_pt"]
    geo_ok = bool(docx_sizes) and all(
        any(abs(pw - dw) <= GEOMETRY_TOLERANCE_PT
            and abs(ph - dh) <= GEOMETRY_TOLERANCE_PT
            for dw, dh in docx_sizes)
        for pw, ph in pdf_sizes)
    dimensions["page_geometry"] = {
        "status": "preserved" if geo_ok else "loss",
        "pdf_sizes_pt": pdf_sizes, "docx_sizes_pt": docx_sizes,
        "tolerance_pt": GEOMETRY_TOLERANCE_PT,
    }
    if not geo_ok:
        losses.append("page_geometry")

    # 3) 分页流（PDF 页数 vs docx 显式分页 break 数＋1）
    docx_struct_pages = docx_parsed["page_breaks"] + 1
    pdf_pages_total = len(pdf["pages"])
    flow_ok = docx_struct_pages == pdf_pages_total
    dimensions["page_flow"] = {
        "status": "preserved" if flow_ok else "loss",
        "pdf_pages": pdf_pages_total,
        "docx_explicit_pages": docx_struct_pages,
        "docx_page_breaks": docx_parsed["page_breaks"],
    }
    if not flow_ok:
        losses.append("page_flow")

    # 4) 表格（金标在＝网格硬对照[rows/cols/单元格文本]；无金标＝docx
    #    表格内容存活实测＋重建数，结构面如实标 not_provided）
    docx_tables = docx_parsed["tables"]
    if gold_tables:
        matched = len(docx_tables) == len(gold_tables) and all(
            dt["rows"] == gt["rows"] and dt["cols"] == gt["cols"]
            and dt["cells"] == gt["cells"]
            for dt, gt in zip(docx_tables, gold_tables))
        tables_status = "preserved" if matched else "loss"
        detail = {
            "gold_tables": [{"rows": g["rows"], "cols": g["cols"]}
                            for g in gold_tables],
            "docx_tables": [{"rows": t["rows"], "cols": t["cols"]}
                            for t in docx_tables],
        }
    else:
        pdf_texts = Counter()
        for page in pdf["pages"]:
            pdf_texts.update(line["text"] for line in page["lines"])
        uncovered = 0
        cells_total = 0
        for tbl in docx_tables:
            for row in tbl["cells"]:
                for cell in row:
                    if not cell:
                        continue
                    cells_total += 1
                    if pdf_texts.get(cell, 0) <= 0:
                        uncovered += 1
        tables_status = ("no_tables" if not docx_tables
                         else "content_preserved" if uncovered == 0
                         else "loss")
        detail = {"docx_tables": len(docx_tables),
                  "docx_cells": cells_total, "cells_not_in_pdf": uncovered,
                  "structural_gold": "not_provided"}
    dimensions["tables"] = {"status": tables_status, **detail}
    if tables_status == "loss":
        losses.append("table_structure")

    # 5) 页眉页脚（PDF 跨页重现边带行 vs docx header/footer 部件）
    edges = _edge_lines(pdf)
    hf = docx_parsed["header_footer_parts"]
    hf_texts = {t for part in hf for t in part["texts"]}
    docx_pages_text = _docx_page_multisets(docx_parsed)
    if not edges and not hf:
        hf_status = "none_present"
    elif edges and not hf:
        hf_status = "loss"    # 实测：内容以正文存活但部件不重建（如实记损失）
    else:
        hf_status = ("preserved" if all(e in hf_texts for e in edges)
                     else "loss")
    content_as_body = bool(edges) and not hf and all(
        any(e in counter for counter in docx_pages_text) for e in edges)
    dimensions["headers_footers"] = {
        "status": hf_status, "pdf_edge_lines": edges,
        "edge_band_pct": EDGE_BAND_PCT,
        "docx_header_footer_parts": [p["part"] for p in hf],
        "content_survives_as_body_text": content_as_body,
    }
    if hf_status == "loss":
        losses.append("header_footer_structure")

    return {
        "comparison": "measured_structural",
        "auto_fidelity_claimed": False,
        "dimensions": dimensions,
        "losses": losses,
        "dimensions_all_preserved":
        all(d["status"] in ("preserved", "no_tables", "none_present",
                            "content_preserved", "no_text_layer")
            for d in dimensions.values()),
    }


# --------------------------------------------------------------------------
# 状态布局（双留存 append-only；W2b-U14 红线管线消费契约）
# --------------------------------------------------------------------------

def _document_dir(state_root: Path, document_id: str) -> Path:
    return Path(state_root) / STATE_SUBDIR / document_id


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _register_document(state_root: Path, document_id: str, matter_id,
                       pdf_path: Path) -> tuple[Path, dict]:
    """注册即双留存：original.pdf 复制落位＋document.json 身份钉定。
    同 id 重复注册：字节同＝幂等复用；字节异＝fail-closed（原件永不被
    覆盖，06:F54「保存原PDF」）。"""
    doc_dir = _document_dir(state_root, document_id)
    original = doc_dir / "original.pdf"
    facts = pdf_facts(pdf_path)
    payload = pdf_path.read_bytes()
    sha = hashlib.sha256(payload).hexdigest()
    manifest_path = doc_dir / "document.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["original"]["sha256"] != sha:
            raise _fail("f54_original_bytes_mismatch")
        return doc_dir, manifest
    doc_dir.mkdir(parents=True, exist_ok=True)
    if original.exists():               # 无清单但有残留＝状态不完整，拒绝
        raise _fail("f54_state_inconsistent")
    tmp = original.with_suffix(".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, original)
    manifest = {
        "schema": SCHEMA, "document_id": document_id,
        "matter_id": matter_id,
        "original": {"file": "original.pdf", "sha256": sha,
                     "bytes": len(payload), "pages": facts["page_count"],
                     "page_sizes_pt": [[p["width_pt"], p["height_pt"]]
                                       for p in facts["pages"]]},
        "registered_utc": _now_utc(),
    }
    _atomic_write_json(manifest_path, manifest)
    return doc_dir, manifest


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _next_candidate_dir(doc_dir: Path, kind: str) -> Path:
    candidates = doc_dir / "candidates"
    candidates.mkdir(parents=True, exist_ok=True)
    seq = 1
    for entry in sorted(candidates.iterdir()):
        if entry.is_dir() and entry.name.split("-", 1)[0].isdigit():
            seq = max(seq, int(entry.name.split("-", 1)[0]) + 1)
    return candidates / f"{seq:04d}-{kind}"


def _run_soffice(binary: Path, state_root: Path, pdf_path: Path,
                 out_dir: Path, timeout_s: int) -> None:
    """确定性 CLI 子进程（唯一转换器）。staging 副本定名 input.pdf——产物
    名与源文件名解耦（非 ASCII 源名不入命令行）。UserInstallation 隔离于
    状态根（绝不写 %APPDATA%）。"""
    staging = out_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf_path, staging / "input.pdf")
    profile = (Path(state_root) / "lo-profile").resolve()
    profile.mkdir(parents=True, exist_ok=True)
    argv = [str(binary), "--headless", "--norestore", "--nolockcheck",
            "-env:UserInstallation=" + profile.as_uri(),
            "--infilter=writer_pdf_import",
            "--convert-to", "docx:MS Word 2007 XML",
            "--outdir", str(staging), str(staging / "input.pdf")]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise _fail("f54_conversion_timeout") from None
    except OSError as exc:
        raise _fail("f54_conversion_failed:" + type(exc).__name__) from None
    produced = staging / "input.docx"
    if proc.returncode != 0 or not produced.is_file():
        raise _fail("f54_conversion_failed:exit%d" % proc.returncode)
    target = out_dir / "candidate.docx"
    tmp = target.with_suffix(".tmp")
    shutil.move(str(produced), str(tmp))
    os.replace(tmp, target)
    shutil.rmtree(staging, ignore_errors=True)


def _gold_tables_from(args: dict) -> list[dict] | None:
    """金标表网格（可选）：[{rows,cols,cells:[[...]]}]，来自调用方/语料
    清单（合成金标），用于表格结构硬对照。"""
    gold = args.get("gold_tables")
    if gold is None:
        return None
    if not isinstance(gold, list):
        raise _fail("f54_gold_tables_invalid")
    out = []
    for tbl in gold:
        if not isinstance(tbl, dict) or not isinstance(tbl.get("cells"), list):
            raise _fail("f54_gold_tables_invalid")
        rows = tbl["cells"]
        out.append({"rows": len(rows),
                    "cols": max((len(r) for r in rows), default=0),
                    "cells": [[str(c) for c in row] for row in rows]})
    return out


def convert(state_root: Path, document_id: str, pdf_path, matter_id,
            config: dict, gold_tables_args: dict | None = None) -> dict:
    """LibreOffice 转换候选（优先且唯一自动转换器）＋实测保真对照。"""
    binary = _resolve_soffice(config)
    if binary is None:
        raise _fail("f54_soffice_not_configured")
    src = Path(pdf_path)
    if not src.is_file():
        raise _fail("f54_pdf_not_found")
    timeout_s = int(config.get("conversion_timeout_s",
                               _SOFFICE_TIMEOUT_DEFAULT))
    gold = (_gold_tables_from(gold_tables_args)
            if gold_tables_args is not None else None)
    with _LOCK:
        doc_dir, manifest = _register_document(
            state_root, document_id, matter_id, src)
        cand_dir = _next_candidate_dir(doc_dir, "libreoffice")
        cand_dir.mkdir(parents=True, exist_ok=False)
        try:
            _run_soffice(binary, state_root, doc_dir / "original.pdf",
                         cand_dir, timeout_s)
            docx_path = cand_dir / "candidate.docx"
            facts = pdf_facts(doc_dir / "original.pdf")
            parsed = _docx_parse(docx_path)
            report = fidelity_report(facts, parsed, gold)
            candidate = _candidate_manifest(
                doc_dir, cand_dir, "libreoffice", document_id, manifest,
                binary, parsed, report, config, timeout_s)
        except Exception:
            shutil.rmtree(cand_dir, ignore_errors=True)  # 失败不留半成品
            raise
    _atomic_write_json(cand_dir / "candidate.json", candidate)
    return _public_view(candidate)


def rebuild(state_root: Path, document_id: str, pdf_path, matter_id,
            config: dict, gold_tables_args: dict | None = None) -> dict:
    """纯文本重建候选：从留存原件抽文本逐行重建（显式损失闭集标注）。"""
    gold = (_gold_tables_from(gold_tables_args)
            if gold_tables_args is not None else None)
    with _LOCK:
        if pdf_path is not None:
            doc_dir, manifest = _register_document(
                state_root, document_id, matter_id, Path(pdf_path))
        else:
            doc_dir = _document_dir(state_root, document_id)
            manifest_path = doc_dir / "document.json"
            if not manifest_path.is_file():
                raise _fail("f54_document_not_registered")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cand_dir = _next_candidate_dir(doc_dir, "text_rebuild")
        cand_dir.mkdir(parents=True, exist_ok=False)
        try:
            facts = pdf_facts(doc_dir / "original.pdf")
            docx_path = cand_dir / "candidate.docx"
            written = write_text_rebuild_docx(docx_path, facts)
            parsed = _docx_parse(docx_path)
            report = fidelity_report(facts, parsed, gold)
            # 纯文本重建：闭集损失显式标注（06:F54「纯文本重建明确损失」）
            rebuild_losses = [loss for loss in REBUILD_LOSSES
                              if loss not in report["losses"]]
            report = dict(
                report,
                losses=sorted(set(report["losses"] + rebuild_losses)),
                rebuild_annotation="pure_text_rebuild_explicit_losses:"
                                   + ",".join(REBUILD_LOSSES))
            candidate = _candidate_manifest(
                doc_dir, cand_dir, "text_rebuild", document_id, manifest,
                None, parsed, report, config, 0, written=written)
        except Exception:
            shutil.rmtree(cand_dir, ignore_errors=True)
            raise
    _atomic_write_json(cand_dir / "candidate.json", candidate)
    return _public_view(candidate)


def _candidate_manifest(doc_dir, cand_dir, kind, document_id, doc_manifest,
                        binary, parsed, report, config, timeout_s,
                        written: dict | None = None) -> dict:
    docx_path = cand_dir / "candidate.docx"
    candidate_id = f"{document_id}:{cand_dir.name}"
    engine = {
        "name": "libreoffice",
        "priority": 1,
        "binary": str(binary) if binary else None,
        "version": _soffice_version(binary) if binary else None,
        "infilter": "writer_pdf_import" if binary else None,
        "export_filter": "MS Word 2007 XML" if binary else None,
        "cli_flags": ["--headless", "--norestore", "--nolockcheck",
                      "-env:UserInstallation=<state>/lo-profile",
                      "--infilter=writer_pdf_import",
                      "--convert-to", "docx:MS Word 2007 XML"]
        if binary else ["deterministic-text-rebuild"],
        "timeout_s": timeout_s,
    } if binary else {
        "name": "pure-text-rebuild", "priority": None, "binary": None,
        "version": None, "infilter": None, "export_filter": None,
        "cli_flags": ["deterministic-text-rebuild"], "timeout_s": 0,
    }
    text_status = report["dimensions"]["text_content"]["status"]
    editable = text_status in ("preserved", "partial_loss")
    candidate = {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "document_id": document_id,
        "matter_id": doc_manifest.get("matter_id"),
        "kind": kind,
        "created_utc": _now_utc(),
        "engine": engine,
        "original": {"file": "original.pdf",
                     "sha256": doc_manifest["original"]["sha256"],
                     "bytes": doc_manifest["original"]["bytes"],
                     "pages": doc_manifest["original"]["pages"]},
        "candidate_docx": {
            "file": "candidates/" + cand_dir.name + "/candidate.docx",
            "sha256": _sha256_file(docx_path),
            "content_digest": docx_content_digest(docx_path),
            "bytes": docx_path.stat().st_size,
        },
        "docx_facts": {
            "page_sizes_pt": parsed["page_sizes_pt"],
            "page_breaks": parsed["page_breaks"],
            "tables": [{"rows": t["rows"], "cols": t["cols"]}
                       for t in parsed["tables"]],
            "header_footer_parts": [p["part"]
                                    for p in parsed["header_footer_parts"]],
        },
        "fidelity": report,
        # W2b-U14 红线管线消费契约：转换候选入口（不前造修订线本身）
        "redline": {
            "pipeline": "w2b-u14",
            "consumable_schema": SCHEMA,
            "editable_text": editable,
            "route": "revision_line" if editable else "needs_ocr",
            "candidate_manifest": "candidate.json",
        },
    }
    if written is not None:
        candidate["rebuild"] = written
    return candidate


def _public_view(candidate: dict) -> dict:
    """桥回读面：完整清单去掉本机绝对路径（binary 只回文件名——版本与
    确定性 CLI 面保留）；无材料内容新增面。"""
    view = dict(candidate)
    engine = view.get("engine")
    if isinstance(engine, dict) and engine.get("binary"):
        view["engine"] = dict(engine,
                              binary=Path(engine["binary"]).name)
    return view


_CAND_DIR_RE = re.compile(r"^\d{4}-(libreoffice|text_rebuild)$")


def _split_candidate_id(candidate_id: str) -> tuple[str, str]:
    parts = candidate_id.split(":")
    if len(parts) != 2 or not _DOC_ID_RE.match(parts[0]) \
            or not _CAND_DIR_RE.match(parts[1]):
        raise _fail("f54_candidate_id_invalid")
    return parts[0], parts[1]


def report(state_root: Path, candidate_id: str) -> dict:
    """候选清单回读（含五维保真与损失；U14 管线消费面）。"""
    document_id, dirname = _split_candidate_id(candidate_id)
    path = _document_dir(state_root, document_id) / "candidates" / dirname \
        / "candidate.json"
    if not path.is_file():
        raise _fail("f54_candidate_not_found")
    candidate = json.loads(path.read_text(encoding="utf-8"))
    # 双留存完整性：清单哈希与盘上字节复核（不照亮失败）
    doc_dir = _document_dir(state_root, document_id)
    if _sha256_file(doc_dir / "original.pdf") != \
            candidate["original"]["sha256"]:
        raise _fail("f54_original_bytes_mismatch")
    docx = doc_dir / "candidates" / dirname / "candidate.docx"
    if _sha256_file(docx) != candidate["candidate_docx"]["sha256"]:
        raise _fail("f54_candidate_bytes_mismatch")
    return _public_view(candidate)


def list_candidates(state_root: Path, document_id: str) -> dict:
    if not _DOC_ID_RE.match(document_id):
        raise _fail("f54_document_id_invalid")
    doc_dir = _document_dir(state_root, document_id)
    manifest_path = doc_dir / "document.json"
    if not manifest_path.is_file():
        raise _fail("f54_document_not_registered")
    out = []
    for cand in sorted((doc_dir / "candidates").iterdir()):
        meta = cand / "candidate.json"
        if meta.is_file():
            view = _public_view(
                json.loads(meta.read_text(encoding="utf-8")))
            out.append({"candidate_id": view["candidate_id"],
                        "kind": view["kind"],
                        "created_utc": view["created_utc"],
                        "sha256": view["candidate_docx"]["sha256"],
                        "content_digest":
                            view["candidate_docx"]["content_digest"],
                        "losses": view["fidelity"]["losses"],
                        "editable_text": view["redline"]["editable_text"]})
    return {"schema": SCHEMA, "document_id": document_id,
            "candidates": out}


def candidate_bytes(state_root: Path, candidate_id: str) -> dict:
    """候选 docx 字节（base64，跨 JSON 边界；红线管线取件面）。"""
    import base64
    view = report(state_root, candidate_id)
    document_id, dirname = _split_candidate_id(candidate_id)
    docx = _document_dir(state_root, document_id) / "candidates" / dirname \
        / "candidate.docx"
    return {"schema": SCHEMA, "candidate_id": candidate_id,
            "kind": view["kind"],
            "sha256": view["candidate_docx"]["sha256"],
            "docx_b64": base64.b64encode(docx.read_bytes()).decode("ascii")}


# --------------------------------------------------------------------------
# 桥分发（legal_entry conversion.* 唯一入口；fail-closed 同基线）
# --------------------------------------------------------------------------

def conversion_call(method: str, args: dict, config: dict) -> dict:
    if method == "conversion.engine":
        return engine_report(config)      # 探针面：无需状态根
    state_root = config.get("conversion_state_root")
    if not state_root:
        raise _fail("f54_state_root_not_configured")

    def _document_id() -> str:
        document_id = args.get("document_id")
        if not isinstance(document_id, str) \
                or not _DOC_ID_RE.match(document_id):
            raise _fail("f54_document_id_invalid")
        return document_id

    def _candidate_id() -> str:
        candidate_id = args.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise _fail("f54_candidate_id_invalid")
        return candidate_id

    try:
        if method == "conversion.convert":
            pdf_path = args.get("pdf_path")
            if not isinstance(pdf_path, str) or not pdf_path:
                raise _fail("f54_pdf_path_required")
            return convert(Path(state_root), _document_id(), pdf_path,
                           args.get("matter_id"), config,
                           gold_tables_args=args)
        if method == "conversion.rebuild":
            pdf_path = args.get("pdf_path")
            if pdf_path is not None and not isinstance(pdf_path, str):
                raise _fail("f54_pdf_path_invalid")
            return rebuild(Path(state_root), _document_id(), pdf_path,
                           args.get("matter_id"), config,
                           gold_tables_args=args)
        if method == "conversion.report":
            return report(Path(state_root), _candidate_id())
        if method == "conversion.list":
            return list_candidates(Path(state_root), _document_id())
        if method == "conversion.candidate":
            return candidate_bytes(Path(state_root), _candidate_id())
        raise _fail("f54_method_unknown")
    except ConversionError:
        raise
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise _fail("f54_failed:" + type(exc).__name__) from None
