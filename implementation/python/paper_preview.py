"""F18 纸张 CSS 文书观感（W3-U21）：产品侧 paper_preview 公开面
（document-adapter 家族，F54 conversion.* 同族）。

义务 06:F18 断言：「纸张 CSS 文书观感（衬线+页边距+微阴影）；零依赖提升
法律文书感」＋验收行「纸张预览与真实DOCX/PDF分页分别核；缩放阅读不遮
正文」。08§3 文书行硬纪律：「CSS预览/文件存在/HTML.doc 不等正式DOCX」。

本面把两件事**分别**承载，互不代言：
- paper.document＝纸张预览的文本内容面：确定性抽取（zipfile＋ET，同输入
  两跑同回执；无时钟无随机），回执**零分页字段**（结构上没有
  page_count/pages——CSS 预览无从冒充分页），并携带显式声明块
  pagination（css 预览面不携带分页主张、正式分页参照指向
  paper.pagination_reference）。
- paper.pagination_reference＝真实分页唯一参照面：LibreOffice headless
  （--convert-to pdf，确定性 CLI 非模型；Windows 用 soffice.com 阻塞
  二进制——沿用 F54 实测钉定的两坑规避：非 PDF 输入不带
  writer_pdf_import 过滤器、.exe 分离拿不到真退出码）渲染 DOCX→PDF，
  页数与逐页文本自 **PDF 实测**（pdfium，复用 F54 pdf_facts），非 DOCX
  数学推导、非 CSS 近似。回执显式 disclaimer=
  official_render_reference_not_css_preview。
- 确定性口径如实：document 同输入两跑逐键相等；分页参照的页数/逐页
  文本跨状态根复现（内容级）；PDF 字节不主张逐字节确定（内嵌时间戳
  元数据，如实记录不装样子）。参照按 docx 内容摘要钉定目录、渲染一次
  复用（同内容幂等；异内容自然落新目录，不覆盖）。

fail-closed：未配置状态根/soffice、docx 缺失/不可读、转换失败/无产物
——typed error（f18_* 错误码，str 只有码不携材料内容），绝不静默回退
CSS 近似分页，绝不编页数。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
import zipfile
from pathlib import Path

SCHEMA = "juscite-f18-paper-preview/1"
STATE_SUBDIR = "paper-preview"

# 单写者纪律：soffice 共享 UserInstallation 配置目录，进程内串行（F54 同款）。
_LOCK = threading.Lock()


class PaperError(ValueError):
    """Typed F18 face failure; str() is a code, never material content."""

    error_code = "f18_invalid"


def _fail(code: str) -> PaperError:
    return PaperError(code)


_DOCX_PATH_KEY = "docx_path"


def _docx_path_from(args: dict) -> Path:
    raw = args.get(_DOCX_PATH_KEY)
    if not isinstance(raw, str) or not raw:
        raise _fail("f18_docx_path_required")
    path = Path(raw)
    if not path.is_file():
        raise _fail("f18_docx_not_found")
    return path


# --------------------------------------------------------------------------
# 预览内容面：确定性抽取（零分页字段）
# --------------------------------------------------------------------------

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_NS = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"


def _docx_blocks(docx_path: Path) -> list[dict]:
    """正文块抽取（阅读序）：paragraph＝w:p 聚合文本；table_row＝w:tr 逐格
    文本。mc:Fallback 是 mc:Choice 的复制载体，跳过＝按逻辑内容去重（F54
    实测口径）。零样式零分页推断——预览面只要内容与顺序。"""
    import xml.etree.ElementTree as ET

    try:
        zf = zipfile.ZipFile(docx_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise _fail("f18_docx_unreadable:" + type(exc).__name__) from None
    with zf:
        try:
            root = ET.fromstring(zf.read("word/document.xml"))
        except (KeyError, ET.ParseError) as exc:
            raise _fail("f18_docx_invalid:" + type(exc).__name__) from None
        body = root.find(_W_NS + "body")
        if body is None:
            raise _fail("f18_docx_invalid:no_body")

        parent = {c: p for p in root.iter() for c in p}

        def _in_fallback(node) -> bool:
            while node in parent:
                node = parent[node]
                if node.tag == _MC_NS + "Fallback":
                    return True
            return False

        blocks: list[dict] = []

        def _walk(node):
            for child in node:
                if child.tag == _MC_NS + "Fallback":
                    continue
                if child.tag == _W_NS + "p":
                    text = "".join(
                        t.text or "" for t in child.iter(_W_NS + "t")
                        if not _in_fallback(t)).strip()
                    if text:
                        blocks.append({"kind": "paragraph", "text": text})
                elif child.tag == _W_NS + "tbl":
                    for tr in child.findall(_W_NS + "tr"):
                        cells = [
                            "".join(t.text or "" for t in tc.iter(_W_NS + "t")
                                    if not _in_fallback(t)).strip()
                            for tc in tr.findall(_W_NS + "tc")]
                        blocks.append({"kind": "table_row", "cells": cells})
                else:
                    _walk(child)

        _walk(body)
        return blocks


def document(args: dict, config: dict) -> dict:
    """纸张预览内容面：确定性抽取＋零分页字段（CSS 预览结构性不携带分页
    主张——08§3「CSS 预览不等正式 DOCX」的内容面承载）。"""
    path = _docx_path_from(args)
    blocks = _docx_blocks(path)
    from pdf_conversion import docx_content_digest
    digest = docx_content_digest(path)
    paragraphs = sum(1 for b in blocks if b["kind"] == "paragraph")
    table_rows = len(blocks) - paragraphs
    chars = sum(
        len(b["text"]) if b["kind"] == "paragraph"
        else sum(len(c) for c in b["cells"]) for b in blocks)
    # 显式声明块：预览面不携带分页（不是"没有算分页"，是结构上不存在分页
    # 字段）；正式分页唯一参照＝paper.pagination_reference（LibreOffice
    # 渲染 PDF 实测）。
    return {
        "schema": SCHEMA,
        "docx": {
            "name": path.name,
            "content_digest": digest,
            "bytes": path.stat().st_size,
        },
        "blocks": blocks,
        "counts": {"blocks": len(blocks), "paragraphs": paragraphs,
                   "table_rows": table_rows, "chars": chars},
        "pagination": {
            "carried_by_preview": False,
            "preview_rendering": "css_continuous_sheet_no_page_claims",
            "official_reference_method": "paper.pagination_reference",
            "css_preview_is_not_official_pagination": True,
        },
    }


# --------------------------------------------------------------------------
# 分页参照面：LibreOffice 渲染 PDF，页数/逐页文本自 PDF 实测
# --------------------------------------------------------------------------

def _render_reference(binary: Path, state_root: Path, docx_path: Path,
                      ref_dir: Path, timeout_s: int) -> None:
    """确定性 CLI 子进程（唯一参照渲染器）。staging 副本定名 input.docx
    （产物名与源文件名解耦，非 ASCII 源名不入命令行——F54 同款）；
    UserInstallation 隔离于状态根（绝不写 %APPDATA%）。DOCX→PDF 走 Writer
    原生打开（不带 writer_pdf_import——那是 PDF 输入过滤器，F54 实测钉定）。"""
    staging = ref_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(docx_path, staging / "input.docx")
    profile = (Path(state_root) / "lo-profile").resolve()
    profile.mkdir(parents=True, exist_ok=True)
    argv = [str(binary), "--headless", "--norestore", "--nolockcheck",
            "-env:UserInstallation=" + profile.as_uri(),
            "--convert-to", "pdf",
            "--outdir", str(staging), str(staging / "input.docx")]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise _fail("f18_reference_timeout") from None
    except OSError as exc:
        raise _fail("f18_reference_failed:" + type(exc).__name__) from None
    produced = staging / "input.pdf"
    if proc.returncode != 0 or not produced.is_file():
        raise _fail("f18_reference_failed:exit%d" % proc.returncode)
    target = ref_dir / "reference.pdf"
    tmp = target.with_suffix(".tmp")
    shutil.move(str(produced), str(tmp))
    os.replace(tmp, target)
    shutil.rmtree(staging, ignore_errors=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pagination_reference(args: dict, config: dict) -> dict:
    """真实分页参照面：LibreOffice 渲染 DOCX→PDF，页数/逐页文本自 PDF
    实测（pdfium）。参照按 docx 内容摘要钉定目录，渲染一次复用；回执
    disclaimer 显式声明「官方渲染参照，非 CSS 预览」。"""
    from pdf_conversion import _resolve_soffice, engine_report, pdf_facts

    state_root = config.get("paper_state_root")
    if not isinstance(state_root, str) or not state_root:
        raise _fail("f18_state_root_not_configured")
    binary = _resolve_soffice(config)
    if binary is None:
        raise _fail("f18_soffice_not_configured")
    path = _docx_path_from(args)
    from pdf_conversion import docx_content_digest
    digest = docx_content_digest(path)

    root = Path(state_root)
    ref_dir = root / STATE_SUBDIR / digest[:16]
    reference = ref_dir / "reference.pdf"
    rendered = "reused"
    timeout_s = int(config.get("conversion_timeout_s", 300))
    with _LOCK:
        if not reference.is_file():
            if ref_dir.exists() and any(
                    ref_dir.iterdir()) and not (ref_dir / "staging").exists():
                # 有残留目录但无参照文件＝状态不完整（半成品），拒绝不覆盖
                raise _fail("f18_state_inconsistent")
            rendered = "fresh"
            _render_reference(binary, root, path, ref_dir, timeout_s)

    engine = engine_report(config)
    facts = pdf_facts(reference)
    pages = [{
        "page": page["index"],
        "line_count": len(page["lines"]),
        "first_line": (page["lines"][0]["text"] if page["lines"] else ""),
        "chars": sum(len(line["text"]) for line in page["lines"]),
        "width_pt": page["width_pt"],
        "height_pt": page["height_pt"],
    } for page in facts["pages"]]
    return {
        "schema": SCHEMA,
        "docx": {
            "name": path.name,
            "content_digest": digest,
            "bytes": path.stat().st_size,
        },
        "reference": {
            "file": "reference.pdf",
            "sha256": _sha256_file(reference),
            "bytes": reference.stat().st_size,
            "rendered": rendered,
        },
        "engine": {
            "name": "libreoffice",
            "version": engine.get("version"),
            "binary": Path(str(engine.get("binary") or binary)).name,
            "cli_flags": ["--headless", "--norestore", "--nolockcheck",
                          "-env:UserInstallation=<state>/lo-profile",
                          "--convert-to", "pdf"],
            "timeout_s": timeout_s,
        },
        "page_count": facts["page_count"],
        "pages": pages,
        "total_lines": sum(p["line_count"] for p in pages),
        "reference_kind": "LibreOffice_PDF_render_measured_by_pdfium",
        "disclaimer": "official_render_reference_not_css_preview",
    }


# --------------------------------------------------------------------------
# 桥分发（legal_entry paper.* 唯一入口；fail-closed 同基线）
# --------------------------------------------------------------------------

def paper_call(method: str, args: dict, config: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("f18_args_invalid")
    try:
        if method == "paper.document":
            return document(args, config)
        if method == "paper.pagination_reference":
            return pagination_reference(args, config)
        raise _fail("f18_method_unknown")
    except PaperError:
        raise
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise _fail("f18_failed:" + type(exc).__name__) from None
