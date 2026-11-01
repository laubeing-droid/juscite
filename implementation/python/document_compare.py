"""F55 独立文档对比（W4-U37）：产品侧 document_compare 公开面
（document-adapter 家族，F54 conversion.*/F49 redline.* 同族）。

义务 06:F55 断言：「两份实际文件本地对比与变更清单对应，PDF/DOCX 范围
有明确支持」；17 卡 target=新产品 document-adapter（entries P02,P04）。

纪律：
- 两实际文件确定性差量（F49 compareDocuments 差量纪律复用，不模型猜测）：
  对齐算法复用 document_redline._align（difflib.SequenceMatcher 确定性
  纯函数，行为不变）；DOCX 侧文本/表格/脚注分段抽取、PDF 侧逐页文本行
  （pdfium，复用 F54 pdf_facts）→ 段序列 difflib 对齐 → 窗格行＋变更
  清单。无模型、无网络、无时钟入载荷。
- 变更清单逐项对应＝硬门（不过不出清单）：①双射——每条非 equal 窗格行
  恰对应一条变更项、每条变更项回指唯一窗格行；②覆盖——按行序回放，
  消费左档的行文本序列==左档分段序列（右档同理）；③双侧文本来自实际
  登记字节。三条不变式任一不成立＝typed 拒，不落清单。
- PDF/DOCX 范围有明确支持：支持矩阵显式声明——(docx,docx) 与
  (pdf,pdf)；跨类（docx↔pdf）与其他格式＝f55_mode_unsupported 具名拒，
  绝不猜测转义。DOCX 分段模型＝可见文本段（正文段/表格行/脚注）；
  编号标记/修订标记（delText）/样式/页眉脚/域在模型外——range.model
  与 range.outside_model 显式声明；两档模型外事实有差异而可见段零差量
  ＝f55_difference_outside_segment_model 具名拒（fail-closed 不假
  「无变化」），有可见差量时如实标注 outside_model_differences。
- 双留存（F54 同款）：登记即复制 left.bin/right.bin，sha256 钉定永不
  覆盖（同 id 异字节=fail-closed）；对比目录 append-only（不删不改）。
- 确定性：payload_digest＝rows+changes 规范 JSON 的 sha256（无时间戳
  进载荷）——同输入两跑、跨 profile 同摘要。

fail-closed：未配置状态根/文件缺失/不可读/模式不支持/PDF 无文本层/
对账不变式不成立——一律 typed error（f55_* 错误码，str 只有码不携材料
内容）。宿主原生双栏/三窗格 UI 不在本面（本面交付窗格行投影数据：
rows[left,right] 即双栏；rows[left,right,change_id→changes] 即三窗格）。
"""
from __future__ import annotations

import base64
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

SCHEMA = "juscite-f55-document-compare/1"
STATE_SUBDIR = "document-compare"
# 支持矩阵（06:F55「PDF/DOCX范围有明确支持」——显式闭集声明）
SUPPORTED_MODES = (("docx", "docx"), ("pdf", "pdf"))
MODE_NAMES = {("docx", "docx"): "docx_docx", ("pdf", "pdf"): "pdf_pdf"}
# DOCX 分段模型外构件清单（range.outside_model 显式声明）
OUTSIDE_MODEL_DOCX = (
    "numbering_marks",       # 段编号标记（numId/numFmt 级差异）
    "revision_marks",        # 修订标记本体（w:delText 删除侧内容）
    "styles_formatting",     # 样式/字体/版面
    "header_footer_parts",   # 页眉页脚部件
    "fields_graphics",       # 域/图形/文本框
)
OUTSIDE_MODEL_PDF = (
    "scanned_pages",         # 无文本层页（如实计数，不 OCR 不猜）
    "layout_geometry",       # 版面几何/坐标
    "images_annotations",    # 图像/批注
)

_DOC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_CMP_DIR_RE = re.compile(r"^\d{4}-compare$")
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_NS = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"

_LOCK = threading.Lock()


class DocCompareError(ValueError):
    """Typed F55 face failure; str() is a code, never material content."""

    error_code = "f55_invalid"


def _fail(code: str) -> DocCompareError:
    return DocCompareError(code)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# 输入装载与类型判定（登记即双留存，F54 同款）
# --------------------------------------------------------------------------

def _load_bytes(args: dict, side: str) -> bytes:
    b64 = args.get(f"{side}_b64")
    if isinstance(b64, str) and b64:
        try:
            return base64.b64decode(b64, validate=True)
        except Exception:
            raise _fail(f"f55_{side}_b64_invalid") from None
    path = args.get(f"{side}_path")
    if isinstance(path, str) and path:
        try:
            return Path(path).read_bytes()
        except OSError:
            raise _fail(f"f55_{side}_not_found") from None
    raise _fail(f"f55_{side}_required")


def detect_kind(raw: bytes) -> str:
    if raw[:4] == b"%PDF":
        return "pdf"
    if raw[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                if "word/document.xml" in zf.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            pass
        return "zip_unknown"
    return "unknown"


def _mode_for(left_kind: str, right_kind: str) -> str:
    pair = (left_kind, right_kind)
    mode = MODE_NAMES.get(pair)
    if mode is None:
        raise _fail("f55_mode_unsupported:%s_%s" % pair)
    return mode


# --------------------------------------------------------------------------
# 分段模型：DOCX 可见文本段 / PDF 逐页文本行
# --------------------------------------------------------------------------

def _in_fallback_parent_map(root) -> dict:
    return {c: p for p in root.iter() for c in p}


def _descendant_texts(node, tag_local: str, parent) -> list:
    """节点下全部指定局部名文本（含 w:ins 等容器内——可见/删除侧全取）。"""
    out = []
    target = _W_NS + tag_local
    for elem in node.iter(target):
        p = elem
        in_fb = False
        while p in parent:
            p = parent[p]
            if p.tag == _MC_NS + "Fallback":
                in_fb = True
                break
        if not in_fb:
            out.append(elem.text or "")
    return out


def _paragraph_seg_text(p, parent) -> str:
    return "".join(_descendant_texts(p, "t", parent))


def _del_texts(root, parent) -> list:
    return [t for t in _descendant_texts(root, "delText", parent) if t]


def docx_segments(docx_path: Path) -> dict:
    """DOCX 分段：正文段/表格行/脚注（可见文本口径，段内修订容器文本
    全取）。返回段列表＋模型外事实摘要（编号事实＋删除侧文本）。"""
    try:
        zf = zipfile.ZipFile(docx_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise _fail("f55_docx_unreadable:" + type(exc).__name__) from None
    with zf:
        try:
            root = ET.fromstring(zf.read("word/document.xml"))
            fn_root = (ET.fromstring(zf.read("word/footnotes.xml"))
                       if "word/footnotes.xml" in zf.namelist() else None)
            num_root = (ET.fromstring(zf.read("word/numbering.xml"))
                        if "word/numbering.xml" in zf.namelist() else None)
        except (KeyError, ET.ParseError) as exc:
            raise _fail("f55_docx_invalid:" + type(exc).__name__) from None
    parent = _in_fallback_parent_map(root)
    segments: list[dict] = []
    body = root.find(_W_NS + "body")
    if body is not None:
        for child in body:
            if child.tag == _MC_NS + "Fallback":
                continue
            if child.tag == _W_NS + "p":
                text = _paragraph_seg_text(child, parent)
                segments.append({"category": "paragraph",
                                 "location": {"block": len(segments)},
                                 "text": text})
            elif child.tag == _W_NS + "tbl":
                for r_idx, tr in enumerate(child.findall(_W_NS + "tr")):
                    cells = ["".join(_descendant_texts(tc, "t", parent)).strip()
                             for tc in tr.findall(_W_NS + "tc")]
                    segments.append({
                        "category": "table_row",
                        "location": {"block": len(segments),
                                     "table": _table_index(root, child),
                                     "row": r_idx},
                        "text": " | ".join(cells),
                        "cells": cells})
    if fn_root is not None:
        fn_parent = _in_fallback_parent_map(fn_root)
        entries = []
        for fn in fn_root.findall(_W_NS + "footnote"):
            if fn.get(_W_NS + "type") in ("separator",
                                          "continuationSeparator"):
                continue
            fid = fn.get(_W_NS + "id")
            text = "\n".join(_paragraph_seg_text(p, fn_parent)
                             for p in fn.findall(_W_NS + "p")).strip()
            entries.append((fid, text))
        for fid, text in sorted(entries, key=lambda e: int(e[0] or 0)):
            segments.append({"category": "footnote",
                             "location": {"block": len(segments),
                                          "footnote_id": fid},
                             "text": text})
    # 模型外事实摘要（编号＋删除侧文本；供零差量守卫与如实标注）
    # numbering 只取真编号段（None=未编号段不参与——段数差异属可见差量）
    from document_redline import extract_facts
    facts = extract_facts(root, fn_root, num_root)
    outside = {
        "numbering": [n for n in facts["numbering"] if n is not None],
        "deleted_texts": _del_texts(root, parent),
    }
    return {"segments": segments, "outside": outside}


def _table_index(root, tbl) -> int:
    for i, node in enumerate(root.iter(_W_NS + "tbl")):
        if node is tbl:
            return i
    return -1


def pdf_segments(pdf_path: Path) -> dict:
    """PDF 分段：逐页文本行（pdfium，F54 pdf_facts 复用）。无文本层页
    如实计数；全档无文本＝typed 拒（扫描件走 F40 OCR 线，不假对比）。"""
    from pdf_conversion import pdf_facts
    facts = pdf_facts(pdf_path)
    segments: list[dict] = []
    pages_without_text = 0
    for page in facts["pages"]:
        if not page["lines"]:
            pages_without_text += 1
        for l_idx, line in enumerate(page["lines"]):
            segments.append({
                "category": "pdf_line",
                "location": {"block": len(segments),
                             "page": page["index"], "line": l_idx},
                "text": line["text"]})
    return {"segments": segments,
            "page_count": facts["page_count"],
            "pages_without_text": pages_without_text}


def _seg_texts(segments: list[dict]) -> list[str]:
    return [s["text"] for s in segments]


# --------------------------------------------------------------------------
# 对齐与窗格/变更清单（F49 _align 复用；对应三不变式硬门）
# --------------------------------------------------------------------------

def _payload_digest(rows: list, changes: list) -> str:
    return hashlib.sha256(json.dumps(
        {"rows": rows, "changes": changes},
        ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def build_comparison(mode: str, left_model: dict, right_model: dict) -> dict:
    """窗格行＋变更清单（确定性）＋对应三不变式（不过不出清单）。"""
    from document_redline import _align
    left_segs = left_model["segments"]
    right_segs = right_model["segments"]
    rows: list[dict] = []
    changes: list[dict] = []
    change_seq = 0
    for opcode, a_idx, b_idx in _align(_seg_texts(left_segs),
                                       _seg_texts(right_segs)):
        left_seg = left_segs[a_idx] if a_idx is not None else None
        right_seg = right_segs[b_idx] if b_idx is not None else None
        if opcode == "equal":
            kind = "equal"
        elif left_seg is None:
            kind = "insert"
        elif right_seg is None:
            kind = "delete"
        else:
            kind = "replace"
        row = {"id": "r%04d" % (len(rows) + 1), "kind": kind,
               "category": (left_seg or right_seg)["category"],
               "left": left_seg["text"] if left_seg else None,
               "right": right_seg["text"] if right_seg else None,
               "left_location": dict(left_seg["location"]) if left_seg else None,
               "right_location": dict(right_seg["location"])
               if right_seg else None,
               "change_id": None}
        if kind != "equal":
            change_seq += 1
            cid = "c%03d" % change_seq
            row["change_id"] = cid
            changes.append({
                "id": cid, "row_id": row["id"], "kind": kind,
                "category": row["category"],
                "left_location": row["left_location"],
                "right_location": row["right_location"],
                "before_text": left_seg["text"] if left_seg else "",
                "after_text": right_seg["text"] if right_seg else ""})
        rows.append(row)

    # 不变式①双射：非 equal 行↔变更项一一对应
    changed_rows = [r for r in rows if r["kind"] != "equal"]
    if len(changed_rows) != len(changes) or any(
            r["change_id"] != c["id"]
            for r, c in zip(changed_rows, changes)) \
            or {r["change_id"] for r in changed_rows} \
            != {c["id"] for c in changes}:
        raise _fail("f55_correspondence_bijection_failed")
    # 不变式②覆盖：行序回放两侧消费序列==分段序列
    consumed_left = [r["left"] for r in rows if r["left"] is not None]
    consumed_right = [r["right"] for r in rows if r["right"] is not None]
    if consumed_left != _seg_texts(left_segs) \
            or consumed_right != _seg_texts(right_segs):
        raise _fail("f55_correspondence_coverage_failed")
    # 不变式③双侧文本来自实际分段（与变更清单逐项相等）
    for c in changes:
        src_row = rows[int(c["row_id"][1:]) - 1]
        if c["before_text"] != (src_row["left"] or "") \
                or c["after_text"] != (src_row["right"] or ""):
            raise _fail("f55_correspondence_sides_failed")

    view = {
        "mode_options": ["two_pane", "three_pane"],
        "two_pane": {"columns": ["left", "right"],
                     "projection": "rows[left,right]"},
        "three_pane": {"columns": ["left", "right", "changes"],
                       "projection": "rows[left,right,change_id->changes]"},
    }
    by_kind: dict = {}
    by_category: dict = {}
    for c in changes:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
        by_category[c["category"]] = by_category.get(c["category"], 0) + 1
    return {"rows": rows, "changes": changes, "view": view,
            "payload_digest": _payload_digest(rows, changes),
            "counts": {"count": len(changes), "rows": len(rows),
                       "by_kind": by_kind, "by_category": by_category}}


def _outside_facts(model: dict) -> dict:
    return model.get("outside") or {}


def _outside_differences(left_model: dict, right_model: dict,
                         mode: str) -> list:
    """模型外差量具名清单（逐项实测，不笼统判异）。"""
    left_out = _outside_facts(left_model)
    right_out = _outside_facts(right_model)
    if not left_out and not right_out:
        return []
    out = []
    if json.dumps(left_out.get("numbering"), ensure_ascii=False,
                  sort_keys=True, default=str) != json.dumps(
            right_out.get("numbering"), ensure_ascii=False,
            sort_keys=True, default=str):
        out.append("numbering_marks")
    if json.dumps(left_out.get("deleted_texts"), ensure_ascii=False,
                  sort_keys=True) != json.dumps(
            right_out.get("deleted_texts"), ensure_ascii=False,
            sort_keys=True):
        out.append("revision_marks")
    return out


# --------------------------------------------------------------------------
# 状态布局（双留存＋append-only；状态根绝不写 %APPDATA%）
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


def _register(state_root: Path, document_id: str, args: dict) -> tuple:
    left_raw = _load_bytes(args, "left")
    right_raw = _load_bytes(args, "right")
    left_kind = detect_kind(left_raw)
    right_kind = detect_kind(right_raw)
    mode = _mode_for(left_kind, right_kind)
    doc_dir = _document_dir(state_root, document_id)
    manifest_path = doc_dir / "document.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["left"]["sha256"] != _sha256_bytes(left_raw):
            raise _fail("f55_left_bytes_mismatch")
        if manifest["right"]["sha256"] != _sha256_bytes(right_raw):
            raise _fail("f55_right_bytes_mismatch")
        return doc_dir, manifest, mode
    doc_dir.mkdir(parents=True, exist_ok=True)
    for side, raw in (("left", left_raw), ("right", right_raw)):
        target = doc_dir / f"{side}.bin"
        if target.exists():
            raise _fail("f55_state_inconsistent")
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, target)
    manifest = {
        "schema": SCHEMA, "document_id": document_id,
        "matter_id": args.get("matter_id"),
        "left": {"file": "left.bin", "sha256": _sha256_bytes(left_raw),
                 "bytes": len(left_raw), "kind": left_kind},
        "right": {"file": "right.bin", "sha256": _sha256_bytes(right_raw),
                  "bytes": len(right_raw), "kind": right_kind},
        "registered_utc": _now_utc(),
    }
    _atomic_write_json(manifest_path, manifest)
    return doc_dir, manifest, mode


def _require_document(state_root: Path, document_id: str) -> tuple:
    doc_dir = _document_dir(Path(state_root), document_id)
    manifest_path = doc_dir / "document.json"
    if not manifest_path.is_file():
        raise _fail("f55_document_not_registered")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for side in ("left", "right"):
        if _sha256_file(doc_dir / f"{side}.bin") != manifest[side]["sha256"]:
            raise _fail(f"f55_{side}_bytes_mismatch")
    return doc_dir, manifest


def _side_model(mode: str, side: str, path: Path) -> dict:
    if mode == "docx_docx":
        return docx_segments(path)
    return pdf_segments(path)


def compare(state_root: Path, document_id: str, args: dict) -> dict:
    with _LOCK:
        doc_dir, manifest, mode = _register(Path(state_root), document_id,
                                            args)
        cmp_dir = _next_seq_dir(doc_dir / "comparisons", "compare")
        cmp_dir.mkdir(parents=True, exist_ok=False)
        try:
            left_model = _side_model(mode, "left", doc_dir / "left.bin")
            right_model = _side_model(mode, "right", doc_dir / "right.bin")
            if mode == "pdf_pdf":
                for side, model in (("left", left_model),
                                    ("right", right_model)):
                    if model["page_count"] > 0 \
                            and len(model["segments"]) == 0:
                        raise _fail("f55_pdf_no_text_layer:" + side)
            payload = build_comparison(mode, left_model, right_model)
            # 模型外差量守卫：可见段零差量而模型外有差＝具名拒（不假无变化）
            outside_diffs = _outside_differences(left_model, right_model,
                                                 mode)
            if outside_diffs and payload["counts"]["count"] == 0:
                raise _fail("f55_difference_outside_segment_model:"
                            + ",".join(outside_diffs))
            range_block = {
                "supported_modes": [MODE_NAMES[p] for p in SUPPORTED_MODES],
                "mode": mode,
                "declared": True,
                "model": ("visible_text_segments_v1:body_paragraphs,"
                          "table_rows,footnotes" if mode == "docx_docx"
                          else "pdf_text_lines_v1:per_page_rect_lines"),
                "outside_model": list(OUTSIDE_MODEL_DOCX if mode
                                      == "docx_docx" else OUTSIDE_MODEL_PDF),
            }
            comparison = {
                "schema": SCHEMA,
                "comparison_id": f"{document_id}:{cmp_dir.name}",
                "document_id": document_id,
                "matter_id": manifest.get("matter_id"),
                "mode": mode,
                "range": range_block,
                "left": dict(manifest["left"], segments=len(
                    left_model["segments"])),
                "right": dict(manifest["right"], segments=len(
                    right_model["segments"])),
                "outside_model_differences": outside_diffs,
                "correspondence": {
                    "bijection": True, "coverage": True, "sides": True},
                "view": payload["view"],
                "changes": payload["counts"],
                "change_items": payload["changes"],
                "payload_digest": payload["payload_digest"],
                "created_utc": _now_utc(),
            }
            if mode == "pdf_pdf":
                comparison["pdf_pages_without_text"] = {
                    "left": left_model["pages_without_text"],
                    "right": right_model["pages_without_text"]}
                comparison["pdf_page_counts"] = {
                    "left": left_model["page_count"],
                    "right": right_model["page_count"]}
            _atomic_write_json(cmp_dir / "comparison.json", comparison)
        except Exception:
            shutil.rmtree(cmp_dir, ignore_errors=True)   # 失败不留半成品
            raise
    public = dict(comparison)
    public.pop("change_items", None)      # 清单大载荷只经 report 取（桥回执瘦身）
    return public


def _split_cmp_id(comparison_id: str) -> tuple:
    parts = str(comparison_id).split(":")
    if len(parts) != 2 or not _DOC_ID_RE.match(parts[0]) \
            or not _CMP_DIR_RE.match(parts[1]):
        raise _fail("f55_comparison_id_invalid")
    return parts[0], parts[1]


def report(state_root: Path, comparison_id: str) -> dict:
    document_id, dirname = _split_cmp_id(comparison_id)
    doc_dir = _document_dir(Path(state_root), document_id)
    path = doc_dir / "comparisons" / dirname / "comparison.json"
    if not path.is_file():
        raise _fail("f55_comparison_not_found")
    comparison = json.loads(path.read_text(encoding="utf-8"))
    for side in ("left", "right"):
        if _sha256_file(doc_dir / f"{side}.bin") \
                != comparison[side]["sha256"]:
            raise _fail(f"f55_{side}_bytes_mismatch")
    return comparison


def list_comparisons(state_root: Path, document_id: str) -> dict:
    if not _DOC_ID_RE.match(document_id):
        raise _fail("f55_document_id_invalid")
    doc_dir, manifest = _require_document(Path(state_root), document_id)
    out = []
    comp_root = doc_dir / "comparisons"
    if comp_root.is_dir():
        for entry in sorted(comp_root.iterdir()):
            meta = entry / "comparison.json"
            if meta.is_file():
                view = json.loads(meta.read_text(encoding="utf-8"))
                out.append({"comparison_id": view["comparison_id"],
                            "mode": view["mode"],
                            "created_utc": view["created_utc"],
                            "changes": view["changes"]["count"],
                            "payload_digest": view["payload_digest"]})
    return {"schema": SCHEMA, "document_id": document_id,
            "left": manifest["left"], "right": manifest["right"],
            "comparisons": out}


# --------------------------------------------------------------------------
# 桥分发（legal_entry doccompare.* 唯一入口；fail-closed 同基线）
# --------------------------------------------------------------------------

def doccompare_call(method: str, args: dict, config: dict) -> dict:
    state_root = config.get("doccompare_state_root")
    if not state_root:
        raise _fail("f55_state_root_not_configured")

    def _document_id() -> str:
        document_id = args.get("document_id")
        if not isinstance(document_id, str) \
                or not _DOC_ID_RE.match(document_id):
            raise _fail("f55_document_id_invalid")
        return document_id

    try:
        if method == "doccompare.compare":
            return compare(Path(state_root), _document_id(), args)
        if method == "doccompare.report":
            comparison_id = args.get("comparison_id")
            if not isinstance(comparison_id, str) or not comparison_id:
                raise _fail("f55_comparison_id_invalid")
            return report(Path(state_root), comparison_id)
        if method == "doccompare.list":
            return list_comparisons(Path(state_root), _document_id())
        raise _fail("f55_method_unknown")
    except DocCompareError:
        raise
    except Exception as exc:
        # 同族基线：失败面只带类型名，绝不携材料内容。
        raise _fail("f55_failed:" + type(exc).__name__) from None
