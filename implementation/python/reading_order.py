"""F86 前后端阅读序同源规范面（W2a-U07）：从 W2a-U02 解析产物
（anonymizer material_parse_service，经桥 material.parse_* 同一来源）组装
唯一规范阅读序文档（canonical reading-order document），前端阅读面与后端
解析序都消费本文档——不复制第二推导，不同端各自重排（同源纪律）。

义务 06:F86 断言：「前后端阅读序同源固定样例全一致；高亮页段/表格/扫描
OCR 命中」（引用命中属 E14 接线/W2b，不在本面）。V7 来源语义＝引文高亮
静默失败的预防针：命中解析不出来必须**响亮失败**（typed error），绝不静默
空高亮。

阅读序规则（确定性，与 E12 跨页表阅读序同构）：
- 卷按 doc_id 升序；页按页号升序（页序列=阅读序主干）；
- 页内：页段（本页整段）→ 表格行（page_row_index 升序，携组装组号）→
  扫描 OCR 命中（页脚页号识别，当前版本=最新 human 版本，无则最新
  engine 版本；无版本=诚实缺项，该页无 ocr_hit 项）。

三类命中（highlight kinds，闭集）：
- page_segment：页段命中 → seg:<doc>:<page>
- table：表格命中（组或组内行）→ row:<doc>:<page>:<group>:<row>
- ocr：扫描 OCR 命中（页号）→ ocr:<doc>:<page>

数据面：只读解析产物——批次清单 batch.json（anonymizer 服务 docstring
 documented 布局，身份白名单字段）＋公开面 pending_pages / read_page /
table_rows（解析记录一律经 read_page，不重复解析逻辑）。

fail-closed：批次未处理完（存在 pending 页）拒绝出文档（f86_batch_
incomplete，不静默渲染半本）；未知 kind/解析不到的选择子=typed error
（f86_kind_invalid / f86_selector_not_found）——静默失败预防针本体。
错误码只带类别与计数，绝不携材料内容（与 material.parse_* 同红线）。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "juscite-f86-reading-order/1"
SOURCE_FACE = "material.parse_*"
KINDS = ("page_segment", "table", "ocr")
# 高亮三类闭集（表格命中落在 table_row 阅读项上）
HIT_KINDS = frozenset(KINDS)


class ReadingOrderError(ValueError):
    """Typed F86 face failure; str() is a code, never material content."""

    error_code = "reading_order_invalid"


def _fail(code: str) -> "ReadingOrderError":
    return ReadingOrderError(code)


def order_hash(item_ids: list[str]) -> str:
    """规范序哈希：双端一致性锚（前端投影与后端规范文档对同一 id 序列
    各自计算，相等＝阅读序同源）。"""
    digest = hashlib.sha256()
    for item_id in item_ids:
        digest.update(item_id.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _batch_manifest(state_root: Path, batch_id: str) -> dict:
    """读批次清单（documented 布局 <root>/material-parse/<batch>/batch.json；
    只取身份字段 doc_id/page_count/pages[].page——与登记白名单同界）。"""
    path = Path(state_root) / "material-parse" / batch_id / "batch.json"
    if not path.is_file():
        raise _fail("f86_batch_not_registered")
    try:
        batch = json.loads(path.read_text(encoding="utf-8"))
        docs = [{"doc_id": d["doc_id"],
                 "pages": [int(t["page"]) for t in d["pages"]]}
                for d in batch["documents"]]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise _fail("f86_batch_manifest_invalid") from None
    return {"batch_id": batch_id, "documents": docs}


def _current_page_no(record: dict) -> dict | None:
    """页号当前版本（人改不覆语义：最新 human 版本，无则最新 engine）。"""
    versions = (record.get("page_no") or {}).get("versions") or []
    if not versions:
        return None
    current = (record.get("page_no") or {}).get("current_version")
    if current is not None:
        for v in versions:
            if v.get("version") == current:
                return v
    human = [v for v in versions if v.get("source") == "human"]
    pool = human or versions
    return max(pool, key=lambda v: v.get("version", 0))


def document(state_root: Path, batch_id: str,
             doc_ids: list[str] | None = None) -> dict:
    """组装规范阅读序文档（唯一同源；前端阅读面消费本产物，不自行推导）。

    只读 material_parse_service 已落盘解析产物（页记录＋跨页表组装）；批次
    有未处理页=fail-closed。确定性：无时钟/无随机/字典序稳定。
    """
    from legal_anonymizer.application import material_parse_service as mps

    state_root = Path(state_root)
    pending = mps.pending_pages(state_root, batch_id)
    if pending:
        raise _fail("f86_batch_incomplete:%d" % len(pending))
    manifest = _batch_manifest(state_root, batch_id)
    wanted = set(doc_ids) if doc_ids is not None else None

    items: list[dict] = []
    docs = sorted(manifest["documents"], key=lambda d: d["doc_id"])
    for doc in docs:
        doc_id = doc["doc_id"]
        if wanted is not None and doc_id not in wanted:
            continue
        assembled = mps.table_rows(state_root, batch_id, doc_id)
        rows_by_page: dict[int, list[dict]] = {}
        for gi, group in enumerate(assembled["groups"]):
            for row in group["rows"]:
                rows_by_page.setdefault(int(row["page"]), []).append(
                    {"group": gi, "row": row})
        for page in sorted(doc["pages"]):
            record = mps.read_page(state_root, batch_id, doc_id, page)
            items.append({
                "id": f"seg:{doc_id}:{page}",
                "kind": "page_segment",
                "doc_id": doc_id,
                "page": page,
                "signal": record.get("signal"),
                "geom": record.get("geom"),
                "duplicate_of": record.get("duplicate_of"),
            })
            for entry in sorted(rows_by_page.get(page, []),
                                key=lambda e: int(e["row"]["page_row_index"])):
                row = entry["row"]
                items.append({
                    "id": f"row:{doc_id}:{page}:{entry['group']}:"
                          f"{row['page_row_index']}",
                    "kind": "table_row",
                    "doc_id": doc_id,
                    "page": page,
                    "group": entry["group"],
                    "row": row["page_row_index"],
                    "cells": [
                        None if cell is None else {
                            "slot": slot, "text": cell.get("text"),
                            "bbox": cell.get("bbox"),
                            "confidence": cell.get("confidence"),
                        }
                        for slot, cell in enumerate(row.get("cells") or [])
                    ],
                })
            version = _current_page_no(record)
            if version is not None:
                items.append({
                    "id": f"ocr:{doc_id}:{page}",
                    "kind": "ocr_hit",
                    "doc_id": doc_id,
                    "page": page,
                    "hit": "page_no",
                    "text": version.get("text"),
                    "bbox": version.get("bbox"),
                    "confidence": version.get("confidence"),
                    "source": version.get("source"),
                    "version": version.get("version"),
                })
    for index, item in enumerate(items):
        item["order_index"] = index
    included = [d["doc_id"] for d in docs
                if wanted is None or d["doc_id"] in wanted]
    return {
        "schema": SCHEMA,
        "source_face": SOURCE_FACE,
        "batch_id": batch_id,
        "docs": included,
        "counts": {
            "items": len(items),
            "page_segments": sum(1 for i in items
                                 if i["kind"] == "page_segment"),
            "table_rows": sum(1 for i in items if i["kind"] == "table_row"),
            "ocr_hits": sum(1 for i in items if i["kind"] == "ocr_hit"),
        },
        "order_hash": order_hash([i["id"] for i in items]),
        "items": items,
    }


def hits(state_root: Path, batch_id: str, kind: str,
         selector: dict) -> dict:
    """三类命中解析（静默失败预防针：解析不到=typed error，不返回空）。

    - kind=page_segment，selector={doc_id,page} → 页段项（页几何/信号）
    - kind=table，selector={doc_id,group[,row]} → 组（或组内行）含单元格 bbox
    - kind=ocr，selector={doc_id,page} → 页号 OCR 命中（当前版本文本/bbox）
    """
    if kind not in HIT_KINDS:
        raise _fail("f86_kind_invalid")
    if not isinstance(selector, dict):
        raise _fail("f86_selector_invalid")
    doc_id = selector.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id:
        raise _fail("f86_selector_invalid:doc_id")
    doc = document(state_root, batch_id, doc_ids=[doc_id])

    if kind == "page_segment":
        page = selector.get("page")
        if isinstance(page, bool) or not isinstance(page, int):
            raise _fail("f86_selector_invalid:page")
        for item in doc["items"]:
            if item["kind"] == "page_segment" and item["page"] == page:
                return {"kind": kind, "hits": [item]}
        raise _fail("f86_selector_not_found:page_segment")
    if kind == "table":
        group = selector.get("group")
        if isinstance(group, bool) or not isinstance(group, int):
            raise _fail("f86_selector_invalid:group")
        rows = [i for i in doc["items"]
                if i["kind"] == "table_row" and i["group"] == group]
        if not rows:
            raise _fail("f86_selector_not_found:table")
        row_index = selector.get("row")
        if row_index is not None:
            if isinstance(row_index, bool) or not isinstance(row_index, int):
                raise _fail("f86_selector_invalid:row")
            rows = [i for i in rows if i["row"] == row_index]
            if not rows:
                raise _fail("f86_selector_not_found:table_row")
        return {"kind": kind,
                "hits": sorted(rows, key=lambda i: i["order_index"])}
    # kind == "ocr"
    page = selector.get("page")
    if isinstance(page, bool) or not isinstance(page, int):
        raise _fail("f86_selector_invalid:page")
    page_exists = False
    for item in doc["items"]:
        if item["kind"] == "page_segment" and item["page"] == page:
            page_exists = True
        if item["kind"] == "ocr_hit" and item["page"] == page:
            return {"kind": kind, "hits": [item]}
    # 页存在但页号 OCR 无命中（覆印/空识别缺报）＝响亮失败，不静默空高亮
    raise _fail("f86_selector_not_found:ocr_hit"
                if page_exists else "f86_selector_not_found:page")


def call(method: str, args: dict, config: dict) -> dict:
    """桥分发（legal_entry reading.* 方法组唯一入口；fail-closed 同基线）。"""
    state_root = config.get("material_parse_state_root")
    if not state_root:
        raise _fail("f86_state_root_not_configured")
    batch_id = args.get("batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise _fail("f86_batch_id_required")
    try:
        if method == "reading.document":
            doc_ids = args.get("doc_ids")
            if doc_ids is not None and not isinstance(doc_ids, list):
                raise _fail("f86_doc_ids_invalid")
            return document(Path(state_root), batch_id, doc_ids)
        if method == "reading.hits":
            return hits(Path(state_root), batch_id, args.get("kind"),
                        args.get("selector") or {})
        raise _fail("f86_method_unknown")
    except ReadingOrderError:
        raise
    except ValueError as exc:
        # material_parse_service.MaterialParseError 也是 ValueError 子类，
        # 其 str()＝错误码（如 parse_batch_not_registered）——透传码不携内容。
        if type(exc).__name__ == "MaterialParseError":
            raise _fail("f86_parse_face:" + str(exc)) from None
        raise _fail("f86_parse_face:" + type(exc).__name__) from None
