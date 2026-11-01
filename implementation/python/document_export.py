"""F58 红线/对比产物导出 PDF（W4-U37）：产品侧 document_export 公开面
（document-adapter 家族，F54 conversion.*/F18 paper_preview 同族）。

义务 06:F58 断言：「真实红线/对比PDF可阅读打印并保变更范围；失败不交
空PDF」；17 卡 target=新产品 document-adapter（entries P02,P04）；随
F55 立项（同单）。

纪律：
- 真渲染：LibreOffice headless --convert-to pdf（确定性 CLI，非模型）。
  W2b-U17/W3-U21 实测两坑沿用：Windows 必须 soffice.com（控制台阻塞
  二进制——.exe 分离拿不到输出与真退出码，经 pdf_conversion
  _resolve_soffice 确定性改用）；DOCX→PDF 走 Writer 原生打开（不带
  writer_pdf_import——那是 PDF 输入过滤器）。UserInstallation 隔离于
  状态根（lo-profile），绝不写 %APPDATA%。
- 消费权威面不复制第二真源：红线源经 U14 已 VERIFIED 的
  redline.redline b64 面（document_redline.redline_bytes）取件；对比源
  经 F55 doccompare.report 取件；预期变更侧文本自产物红线 DOCX 本身
  （修订 run 级：w:ins/w:t 与 w:del/w:delText 逐元素）与 F55 变更清单
  （整项 before/after 侧）读出。
- 保变更范围＝硬门：渲染后自 PDF 实测全文（pdfium，F54 pdf_facts 复用），
  逐变更项核对删除侧/插入侧文本均呈现在 PDF 文本层（去空白归一，容忍
  换行切分）；任一侧缺失＝f58_change_scope_lost 具名拒。无文本侧的编号
  类变更（w:pPrChange）如实记 not_text_verifiable，不入匹配分母不假绿。
- 可阅读打印＝硬门：PDF 页数≥1 且文本行总数≥1（零页/零文本＝typed 拒）。
- 失败不交空 PDF：渲染失败/超时/零字节/空页/不可读/变更范围丢失——一律
  typed 拒且**清除半成品导出目录**（盘上不留假产物）。
- 双留存 append-only：源字节 source.docx 复制落位 sha256 钉定；导出目录
  不删不改（失败目录整体清除）。对比报告 DOCX 自 F55 变更清单确定性
  生成（zip 定时间戳固定，无时钟）；PDF 字节不主张逐字节确定（内嵌时间
  戳元数据，如实记录不装样子）。

fail-closed：未配置状态根/soffice、源缺失/不可读、渲染失败——typed
error（f58_* 错误码，str 只有码不携材料内容）。宿主打印/预览 UI 不在
本面（本面交付可阅读打印的 PDF 产物与其保范围证据）。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f58-document-export/1"
STATE_SUBDIR = "document-export"
SOURCE_KINDS = ("redline", "compare_report", "docx")
_DEFAULT_TIMEOUT_S = 300

_EXP_DIR_RE = re.compile(r"^\d{4}-(redline|compare_report|docx)$")

_LOCK = threading.Lock()


class DocExportError(ValueError):
    """Typed F58 face failure; str() is a code, never material content."""

    error_code = "f58_invalid"


def _fail(code: str) -> DocExportError:
    return DocExportError(code)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _json_loads(text: str) -> dict:
    return json.loads(text)


def _norm(text: str) -> str:
    """PDF 文本层核对归一：去全部空白（容忍渲染换行/矩形切分）。"""
    return "".join(text.split())


# --------------------------------------------------------------------------
# 源装载（权威面取件，不复制第二真源）
# --------------------------------------------------------------------------

def _expected_from_redline(raw: bytes) -> list:
    """预期变更侧文本自产物红线 DOCX 本身——**修订 run 级**（w:ins 内
    w:t / w:del 内 w:delText 逐元素取文本）。

    粒度依据（W4-U37 渲染实测钉定）：compareDocuments 差量为字符级，
    LibreOffice 渲染时删除/插入 run 在 PDF 文本层按位置交错（pdfium 矩形
    序 del 先于同位 ins），before/after 整侧在文本层**不连续**——run 级
    文本（渲染保持连续）才是可核对粒度。段标记/行标记/pPrChange 等无
    run 文本的标记自然跳过（其内容由所在 run 承载，编号类无文本侧在
    核对时如实 not_text_verifiable）。"""
    import io
    import xml.etree.ElementTree as ET
    _W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            roots = [ET.fromstring(zf.read("word/document.xml"))]
            if "word/footnotes.xml" in zf.namelist():
                roots.append(ET.fromstring(zf.read("word/footnotes.xml")))
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise _fail("f58_redline_docx_invalid:" + type(exc).__name__) \
            from None
    expected: list = []
    seq = 0
    for root in roots:
        for holder in root.iter():
            tag = holder.tag
            if tag == _W + "ins":
                text = "".join(t.text or "" for t in holder.iter(_W + "t"))
                side = "after"
            elif tag == _W + "del":
                text = "".join(t.text or ""
                               for t in holder.iter(_W + "delText"))
                side = "before"
            else:
                continue
            if not text.strip():
                continue          # 段标记等无文本标记：无文本侧可核
            seq += 1
            expected.append({"id": "r%04d" % seq,
                             "kind": "revision_" + str(tag.rsplit("}", 1)[-1]),
                             "sides": {side: text}})
    return expected


def _source_redline(args: dict, config: dict) -> dict:
    from document_redline import redline_bytes, RedlineError
    redline_state_root = config.get("redline_state_root")
    if not redline_state_root:
        raise _fail("f58_redline_state_root_not_configured")
    redline_id = args.get("redline_id")
    if not isinstance(redline_id, str) or not redline_id:
        raise _fail("f58_redline_id_invalid")
    try:
        view = redline_bytes(Path(redline_state_root), redline_id)
    except RedlineError as exc:
        raise _fail("f58_redline_source:" + str(exc)) from None
    raw = base64.b64decode(view["docx_b64"], validate=True)
    return {"kind": "redline", "ref_id": redline_id, "bytes": raw,
            "sha256": view["sha256"],
            "expected": _expected_from_redline(raw),
            "meta": {"revision_count": view.get("revision_count"),
                     "consumers": view.get("consumers")}}


def _source_compare_report(args: dict, config: dict) -> dict:
    from document_compare import DocCompareError
    from document_compare import report as cmp_report
    cmp_state_root = config.get("doccompare_state_root")
    if not cmp_state_root:
        raise _fail("f58_doccompare_state_root_not_configured")
    comparison_id = args.get("comparison_id")
    if not isinstance(comparison_id, str) or not comparison_id:
        raise _fail("f58_comparison_id_invalid")
    try:
        comparison = cmp_report(Path(cmp_state_root), comparison_id)
    except DocCompareError as exc:
        raise _fail("f58_compare_source:" + str(exc)) from None
    items = comparison.get("change_items") or []
    expected = [{"id": item["id"], "kind": item["kind"],
                 "sides": {"before": item.get("before_text") or "",
                           "after": item.get("after_text") or ""}}
                for item in items]
    raw = _build_report_docx(comparison)
    return {"kind": "compare_report", "ref_id": comparison_id,
            "bytes": raw, "sha256": _sha256_bytes(raw),
            "expected": expected,
            "meta": {"mode": comparison.get("mode"),
                     "changes": comparison.get("changes")}}


def _source_docx(args: dict, config: dict) -> dict:
    b64 = args.get("docx_b64")
    if not isinstance(b64, str) or not b64:
        raise _fail("f58_docx_b64_required")
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise _fail("f58_docx_b64_invalid") from None
    return {"kind": "docx", "ref_id": args.get("ref_id") or "direct",
            "bytes": raw, "sha256": _sha256_bytes(raw),
            "expected": [], "meta": {}}


# --------------------------------------------------------------------------
# 对比报告 DOCX 确定性生成（自 F55 变更清单；zip 定时间戳固定）
# --------------------------------------------------------------------------

def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _p(text: str, bold: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return ("<w:p><w:r>" + rpr
            + f'<w:t xml:space="preserve">{_xml_escape(text)}</w:t>'
            + "</w:r></w:p>")


def _cell(text: str) -> str:
    return ('<w:tc><w:tcPr><w:tcW w:w="3200" w:type="dxa"/></w:tcPr>'
            + _p(text) + "</w:tc>")


def _build_report_docx(comparison: dict) -> bytes:
    """对比报告 DOCX（双栏变更表）：左档/右档两列＋变更类型，全部行自
    F55 变更清单（真实差量转写，无模型无时钟；zip 定时间戳固定）。"""
    changes = comparison.get("change_items") or []
    mode = comparison.get("mode", "?")
    kind_labels = {"replace": "替换", "insert": "插入", "delete": "删除"}
    rows = ['<w:tr>' + _cell("变更") + _cell("左档（原稿）")
            + _cell("右档（修改稿）") + "</w:tr>"]
    for item in changes:
        kind = kind_labels.get(item.get("kind"), item.get("kind") or "?")
        rows.append("<w:tr>" + _cell(f"{kind}（{item.get('id')}）")
                    + _cell(item.get("before_text") or "（无原文）")
                    + _cell(item.get("after_text") or "（无修改后）")
                    + "</w:tr>")
    if not changes:
        rows.append("<w:tr>" + _cell("—") + _cell("（无变更）")
                    + _cell("（无变更）") + "</w:tr>")
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>'
        + _p("律引对比报告（变更清单）", bold=True)
        + _p(f"对比模式：{mode}　变更数：{len(changes)}"
             "　本报告自 F55 变更清单确定性生成（内容为两实际登记文件差量）。")
        + '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
          '<w:tblGrid><w:gridCol w:w="1600"/><w:gridCol w:w="4800"/>'
          '<w:gridCol w:w="4800"/></w:tblGrid>'
        + "".join(rows)
        + "</w:tbl>"
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
          '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134"'
          ' w:left="1134"/></w:sectPr></w:body></w:document>')
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/><Default Extension='
        '"xml" ContentType="application/xml"/><Override PartName="/word/'
        'document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://'
        'schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/></Relationships>')
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"/>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in (("[Content_Types].xml", content_types),
                           ("_rels/.rels", rels),
                           ("word/document.xml", document),
                           ("word/_rels/document.xml.rels", doc_rels)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


# --------------------------------------------------------------------------
# 渲染（LibreOffice headless 真渲染；F18 _render_reference 同款实测坑规避）
# --------------------------------------------------------------------------

def _render_pdf(binary: Path, state_root: Path, docx_path: Path,
                out_dir: Path, timeout_s: int) -> None:
    staging = out_dir / "staging"
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
        shutil.rmtree(staging, ignore_errors=True)
        raise _fail("f58_render_timeout") from None
    except OSError as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise _fail("f58_render_failed:" + type(exc).__name__) from None
    produced = staging / "input.pdf"
    if proc.returncode != 0 or not produced.is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise _fail("f58_render_failed:exit%d" % proc.returncode)
    if produced.stat().st_size == 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise _fail("f58_empty_render_output")
    target = out_dir / "export.pdf"
    tmp = target.with_suffix(".tmp")
    shutil.move(str(produced), str(tmp))
    os.replace(tmp, target)
    shutil.rmtree(staging, ignore_errors=True)


# --------------------------------------------------------------------------
# 保变更范围核对（PDF 文本层实测）
# --------------------------------------------------------------------------

def _verify_scope(pdf_path: Path, expected: list, granularity: str) -> dict:
    from pdf_conversion import pdf_facts
    facts = pdf_facts(pdf_path)
    if facts["page_count"] < 1:
        raise _fail("f58_empty_pdf")
    full_text = _norm("".join(
        line["text"] for page in facts["pages"] for line in page["lines"]))
    if not full_text:
        raise _fail("f58_unreadable_pdf")
    items = []
    matched = 0
    not_text_verifiable = 0
    for exp in expected:
        sides = exp["sides"]
        if not any((side or "").strip() for side in sides.values()):
            not_text_verifiable += 1
            items.append({"id": exp["id"], "kind": exp.get("kind"),
                          "verified": "not_text_verifiable"})
            continue
        found = {}
        ok = True
        for side_name in ("before", "after"):
            text = _norm(sides.get(side_name) or "")
            if not text:
                continue
            hit = text in full_text
            found[side_name + "_found"] = hit
            ok = ok and hit
        if not ok:
            raise _fail("f58_change_scope_lost:%s:%s"
                        % (exp["id"],
                           ",".join(k for k, v in found.items()
                                    if not v)))
        matched += 1
        items.append({"id": exp["id"], "kind": exp.get("kind"),
                      "verified": "text_sides_found", **found})
    return {"checked": matched, "matched": matched,
            "not_text_verifiable": not_text_verifiable,
            "items": items,
            "granularity": granularity,
            "denominator_note": "checked==matched；not_text_verifiable "
                                "项无文本侧不入分母不假绿"}


# --------------------------------------------------------------------------
# 导出面（append-only 双留存）
# --------------------------------------------------------------------------

def _exports_root(state_root: Path) -> Path:
    return Path(state_root) / STATE_SUBDIR / "exports"


def _next_export_dir(state_root: Path, kind: str) -> Path:
    root = _exports_root(state_root)
    root.mkdir(parents=True, exist_ok=True)
    seq = 1
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and entry.name.split("-", 1)[0].isdigit():
            seq = max(seq, int(entry.name.split("-", 1)[0]) + 1)
    return root / f"{seq:04d}-{kind}"


def export_pdf(args: dict, config: dict) -> dict:
    state_root = config.get("docexport_state_root")
    if not state_root:
        raise _fail("f58_state_root_not_configured")
    source_kind = args.get("source")
    if source_kind not in SOURCE_KINDS:
        raise _fail("f58_source_unsupported:" + str(source_kind))
    from pdf_conversion import _resolve_soffice, engine_report
    binary = _resolve_soffice(config)
    if binary is None:
        raise _fail("f58_soffice_not_configured")
    loader = {"redline": _source_redline,
              "compare_report": _source_compare_report,
              "docx": _source_docx}[source_kind]
    source = loader(args, config)
    timeout_s = int(config.get("conversion_timeout_s", _DEFAULT_TIMEOUT_S))
    with _LOCK:
        exp_dir = _next_export_dir(Path(state_root), source_kind)
        exp_dir.mkdir(parents=True, exist_ok=False)
        try:
            source_path = exp_dir / "source.docx"
            source_path.write_bytes(source["bytes"])
            if _sha256_file(source_path) != source["sha256"]:
                raise _fail("f58_state_inconsistent")
            _render_pdf(binary, Path(state_root), source_path, exp_dir,
                        timeout_s)
            pdf_path = exp_dir / "export.pdf"
            scope_granularity = {
                "redline": "revision_run_normalized_containment",
                "compare_report": "change_item_side_normalized_containment",
                "docx": "none",
            }[source_kind]
            scope = _verify_scope(pdf_path, source["expected"],
                                  scope_granularity)
            engine = engine_report(config)
            from pdf_conversion import pdf_facts
            facts = pdf_facts(pdf_path)
            export = {
                "schema": SCHEMA,
                "export_id": exp_dir.name,
                "source": {"kind": source_kind, "ref_id": source["ref_id"],
                           "file": "source.docx",
                           "sha256": source["sha256"],
                           "bytes": len(source["bytes"]), **(
                               {"meta": source["meta"]}
                               if source["meta"] else {})},
                "pdf": {"file": "export.pdf",
                        "sha256": _sha256_file(pdf_path),
                        "bytes": pdf_path.stat().st_size,
                        "page_count": facts["page_count"],
                        "page_sizes_pt": [[p["width_pt"], p["height_pt"]]
                                          for p in facts["pages"]],
                        "total_lines": sum(len(p["lines"])
                                           for p in facts["pages"])},
                "engine": {"name": "libreoffice",
                           "version": engine.get("version"),
                           "binary": Path(str(engine.get("binary")
                                              or binary)).name,
                           "cli_flags": ["--headless", "--norestore",
                                         "--nolockcheck",
                                         "-env:UserInstallation="
                                         "<state>/lo-profile",
                                         "--convert-to", "pdf"],
                           "timeout_s": timeout_s},
                "change_scope": scope,
                "readable_printable": {"page_count_min_1": True,
                                       "text_lines_min_1": True},
                "pdf_byte_determinism":
                    "not_claimed_embedded_timestamps_recorded_honestly",
                "rendered_utc": _now_utc(),
            }
            _atomic_write_json(exp_dir / "export.json", export)
        except Exception:
            shutil.rmtree(exp_dir, ignore_errors=True)   # 失败不交空 PDF
            raise
    return dict(export)


def report_export(state_root: Path, export_id: str) -> dict:
    if not _EXP_DIR_RE.match(str(export_id)):
        raise _fail("f58_export_id_invalid")
    path = _exports_root(Path(state_root)) / str(export_id) / "export.json"
    if not path.is_file():
        raise _fail("f58_export_not_found")
    export = _json_loads(path.read_text(encoding="utf-8"))
    exp_dir = path.parent
    if _sha256_file(exp_dir / "source.docx") \
            != export["source"]["sha256"]:
        raise _fail("f58_source_bytes_mismatch")
    if _sha256_file(exp_dir / "export.pdf") != export["pdf"]["sha256"]:
        raise _fail("f58_pdf_bytes_mismatch")
    return export


def list_exports(state_root: Path) -> dict:
    root = _exports_root(Path(state_root))
    out = []
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            meta = entry / "export.json"
            if meta.is_file():
                view = _json_loads(meta.read_text(encoding="utf-8"))
                out.append({"export_id": view["export_id"],
                            "source_kind": view["source"]["kind"],
                            "ref_id": view["source"]["ref_id"],
                            "rendered_utc": view["rendered_utc"],
                            "page_count": view["pdf"]["page_count"],
                            "scope_checked":
                                view["change_scope"]["checked"],
                            "scope_matched":
                                view["change_scope"]["matched"]})
    return {"schema": SCHEMA, "exports": out}


# --------------------------------------------------------------------------
# 桥分发（legal_entry docexport.* 唯一入口；fail-closed 同基线）
# --------------------------------------------------------------------------

def docexport_call(method: str, args: dict, config: dict) -> dict:
    state_root = config.get("docexport_state_root")
    if not state_root:
        raise _fail("f58_state_root_not_configured")
    if not isinstance(args, dict):
        raise _fail("f58_args_invalid")
    try:
        if method == "docexport.pdf":
            return export_pdf(args, config)
        if method == "docexport.report":
            export_id = args.get("export_id")
            if not isinstance(export_id, str) or not export_id:
                raise _fail("f58_export_id_invalid")
            return report_export(Path(state_root), export_id)
        if method == "docexport.list":
            return list_exports(Path(state_root))
        raise _fail("f58_method_unknown")
    except DocExportError:
        raise
    except Exception as exc:
        # 同族基线：失败面只带类型名，绝不携材料内容。
        raise _fail("f58_failed:" + type(exc).__name__) from None
