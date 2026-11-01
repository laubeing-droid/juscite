"""F50 引用原文重锚定＋F51 引用前逐字核验（W2b-U13）：产品侧
document-adapter 公开面——文档定位与改动闸的锚定纪律。

义务 06:F50 断言：「定位一律引用原文重锚定、禁偏移换算；插入后按原文
重锚仍定位正确；零/多命中不以偏移强改」（03-功能分母 F50 源引 doc-haus
redline.ts spike 实测偏移差 4——防插入后错位）。
义务 06:F51 断言：「引用前逐字核验（NOT FOUND 禁呈现，不就近匹配）；
引用逐字定位成功才改；NOT_FOUND 拒自动修改并给人工入口」（03-功能分母
F51 源引 doc-haus verify-quote.ts；大小写不折叠）。

纪律（结构性，非声明式）：
- 锚＝原文逐字引文（quote）。定位唯一来源＝quote 在当前文本中的精确
  子串搜索（Python str.find 语义：大小写敏感、空白与全半角原样、零
  折叠零规范化）。重叠命中也计数（"aa" 在 "aaa" 命中 2 次→多命中）。
- 禁偏移换算：锚记录里的 registered_span 只是登记时溯源事实，locate
  永不读取它推算新位置；编辑（插入/删除）后定位一律重搜原文。零命中
  （f50 NOT_FOUND）或多命中（AMBIGUOUS）时响应**不携带任何位置字段**
  ——即便登记偏移＋已知插入量能"算出"一个看似合法的位置也不给（不以
  偏移强改）。溯源事实登记后不可改写（重登记同键异文本=具名拒）。
- F51 逐字闸：改动（replacement）必须先经同一逐字定位。唯一命中→
  PROCEED＋span＋proposed_text（宿主原生应用的建议产物；本面不落
  CAS/版本——修订线属 W2b-U14，不前造）。零命中/多命中→拒自动修改，
  落人工入口（manual queue：quote＋拟改文＋具名理由，append-only、
  同内容幂等），绝不就近匹配（本模块不存在任何模糊/编辑距离/前缀
  逼近代码——不就近匹配是结构性缺席，不是阈值设 0）。
- 无 replacement 的调用＝纯逐字核验（引用呈现闸）：NOT_FOUND 禁呈现
  ——状态字段使"当作找到呈现"在消费侧不可表达；不落人工入口（无可改
  对象）。

fail-closed：未配置状态根、参数非法、锚未登记、登记时零/多命中——
一律 typed error（f50_* 错误码），错误码不携材料内容（同 material.*
红线；quote/文本只出现在正常结果与人工入口账里）。确定性：无模型、
无网络、无随机；同输入同输出（时间戳除外）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f50-f51-document-anchor/1"
STATE_SUBDIR = "document-anchor"

# F51 拒自动修改的具名理由闭集（人工入口 reason 字段唯一取值）
MANUAL_REASONS = ("not_found", "ambiguous")

_DOC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# 单写者纪律（状态根内串行；跨进程由调用方状态根隔离保证）
_LOCK = threading.Lock()


class AnchorError(ValueError):
    """Typed F50/F51 face failure; str() is a code, never material content."""

    error_code = "f50_invalid"


def _fail(code: str) -> AnchorError:
    return AnchorError(code)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _anchor_id(document_id: str, quote: str) -> str:
    digest = hashlib.sha256(
        ("juscite-f50-anchor\0" + document_id + "\0" + quote)
        .encode("utf-8")).hexdigest()[:16]
    return "a-" + digest


def _manual_entry_id(anchor_id: str, reason: str, replacement: str,
                     text_sha256: str) -> str:
    digest = hashlib.sha256(
        ("juscite-f51-manual\0" + anchor_id + "\0" + reason + "\0"
         + replacement + "\0" + text_sha256).encode("utf-8")).hexdigest()[:16]
    return "me-" + digest


def _find_all(text: str, quote: str) -> list[int]:
    """逐字精确命中（零折叠零规范化；重叠命中也计数——同形判定从严）。"""
    hits: list[int] = []
    start = 0
    while True:
        idx = text.find(quote, start)
        if idx < 0:
            return hits
        hits.append(idx)
        start = idx + 1


# --------------------------------------------------------------------------
# 状态布局（锚账登记后不可改写；人工入口 append-only）
# --------------------------------------------------------------------------

def _document_dir(state_root: Path, document_id: str) -> Path:
    return Path(state_root) / STATE_SUBDIR / document_id


def _atomic_write_json(path: Path, payload) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _load_anchors(state_root: Path, document_id: str) -> dict:
    path = _document_dir(state_root, document_id) / "anchors.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_manual_queue(state_root: Path, document_id: str) -> list[dict]:
    path = _document_dir(state_root, document_id) / "manual-queue.json"
    if not path.is_file():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    return entries.get("entries", []) if isinstance(entries, dict) else []


def _verbatim_block(quote: str, text: str, *, with_span: bool,
                    registered_span: list[int] | None = None) -> dict:
    """逐字定位核心（F50 唯一定位来源）。非唯一命中时不产任何位置字段。"""
    hits = _find_all(text, quote)
    block: dict = {
        "status": ("LOCATED" if len(hits) == 1
                   else "NOT_FOUND" if not hits else "AMBIGUOUS"),
        "matches": len(hits),
        "match": "verbatim_exact_no_folding",   # 大小写敏感、空白原样
    }
    if len(hits) == 1 and with_span:
        span = [hits[0], hits[0] + len(quote)]
        block["span"] = span
        block["position_source"] = "verbatim_quote_match"
        block["offset_conversion_used"] = False   # 禁偏移换算（恒假标记）
        if registered_span is not None:
            block["registered_span"] = registered_span
            block["shift"] = span[0] - registered_span[0]
    return block


# --------------------------------------------------------------------------
# 公开面（legal_entry anchor.* 唯一入口）
# --------------------------------------------------------------------------

def register(state_root: Path, document_id: str, matter_id, quote: str,
             text: str) -> dict:
    """登记锚：quote 必须在 text 中唯一逐字命中（登记即验证）。溯源事实
    （登记时文本 sha 与 span）登记后不可改写：同键同事实=幂等复用；同键
    异事实=具名拒（重锚定走 locate，不走重登记——结构性杜绝偏移账本）。"""
    if not isinstance(quote, str) or not quote:
        raise _fail("f50_quote_required")
    if not isinstance(text, str):
        raise _fail("f50_text_required")
    hits = _find_all(text, quote)
    if not hits:
        raise _fail("f50_anchor_not_found")
    if len(hits) > 1:
        raise _fail("f50_anchor_ambiguous")
    span = [hits[0], hits[0] + len(quote)]
    anchor_id = _anchor_id(document_id, quote)
    text_sha = _sha256_text(text)
    record = {
        "schema": SCHEMA,
        "anchor_id": anchor_id,
        "document_id": document_id,
        "matter_id": matter_id,
        "quote": quote,
        "quote_sha256": _sha256_text(quote),
        "text_sha256": text_sha,
        "registered_span": span,
        "registered_matches": 1,
        "created_utc": _now_utc(),
    }
    with _LOCK:
        anchors = _load_anchors(state_root, document_id)
        existing = anchors.get(anchor_id)
        if existing is not None:
            same = (existing.get("text_sha256") == text_sha
                    and existing.get("matter_id") == matter_id)
            if not same:
                raise _fail("f50_anchor_reregistration_conflict")
            out = dict(existing)
            out["idempotent"] = True
            return out
        anchors[anchor_id] = record
        doc_dir = _document_dir(state_root, document_id)
        doc_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(doc_dir / "anchors.json", anchors)
    out = dict(record)
    out["idempotent"] = False
    return out


def _require_anchor(state_root: Path, document_id: str,
                    anchor_id: str) -> dict:
    anchors = _load_anchors(state_root, document_id)
    record = anchors.get(anchor_id)
    if record is None or record.get("document_id") != document_id:
        raise _fail("f50_anchor_not_registered")
    return record


def locate(state_root: Path, document_id: str, anchor_id: str,
           text: str) -> dict:
    """F50 重锚定：按原文 quote 在当前文本重搜定位。唯一命中→LOCATED＋
    新 span＋shift（插入/删除位移由重搜吸收，非偏移算术）；零/多命中→
    NOT_FOUND/AMBIGUOUS，响应零位置字段（不以偏移强改）。"""
    if not isinstance(text, str):
        raise _fail("f50_text_required")
    record = _require_anchor(state_root, document_id, anchor_id)
    block = _verbatim_block(record["quote"], text, with_span=True,
                            registered_span=record["registered_span"])
    return {
        "schema": SCHEMA,
        "anchor_id": anchor_id,
        "document_id": document_id,
        "text_sha256": _sha256_text(text),
        "reanchor": "quote_search",          # 唯一重锚机制：原文重搜
        "verbatim": block,
    }


def gate_edit(state_root: Path, document_id: str, anchor_id: str, text: str,
              replacement) -> dict:
    """F51 引用前逐字核验＋改动闸。无 replacement＝纯核验（引用呈现闸，
    NOT_FOUND 禁呈现——状态字段使误呈现不可表达；不落人工入口）；有
    replacement＝改动闸：唯一命中才 PROCEED（span＋proposed_text）；零/
    多命中拒自动修改并落人工入口（quote＋拟改文＋具名理由，append-only
    同内容幂等）。不就近匹配：模糊匹配代码在本面结构性缺席。"""
    if not isinstance(text, str):
        raise _fail("f50_text_required")
    if replacement is not None and not isinstance(replacement, str):
        raise _fail("f50_replacement_invalid")
    record = _require_anchor(state_root, document_id, anchor_id)
    block = _verbatim_block(record["quote"], text, with_span=True,
                            registered_span=record["registered_span"])
    out: dict = {
        "schema": SCHEMA,
        "anchor_id": anchor_id,
        "document_id": document_id,
        "text_sha256": _sha256_text(text),
        "verbatim": block,
    }
    if replacement is None:
        out["gate"] = {"mode": "verify_only", "auto_edit": None}
        return out
    if block["status"] == "LOCATED":
        start, end = block["span"]
        out["gate"] = {
            "mode": "edit",
            "status": "PROCEED",
            "auto_edit": "permitted_verbatim_located",
            "proposed_text": text[:start] + replacement + text[end:],
            "replacement_span": block["span"],
        }
        return out
    reason = ("not_found" if block["status"] == "NOT_FOUND" else "ambiguous")
    if reason not in MANUAL_REASONS:          # 理由闭集守门（防御性）
        raise _fail("f51_reason_invalid")
    entry_id = _manual_entry_id(anchor_id, reason, replacement,
                                out["text_sha256"])
    entry = {
        "schema": SCHEMA,
        "manual_entry_id": entry_id,
        "anchor_id": anchor_id,
        "document_id": document_id,
        "matter_id": record.get("matter_id"),
        "reason": reason,
        "quote": record["quote"],
        "replacement": replacement,
        "text_sha256": out["text_sha256"],
        "status": "pending",                  # 人工处置在宿主/人侧，本面不代决
        "created_utc": _now_utc(),
    }
    with _LOCK:
        queue = _load_manual_queue(state_root, document_id)
        existing = next((e for e in queue
                         if e.get("manual_entry_id") == entry_id), None)
        if existing is None:
            queue.append(entry)
            doc_dir = _document_dir(state_root, document_id)
            doc_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(doc_dir / "manual-queue.json",
                               {"schema": SCHEMA,
                                "document_id": document_id,
                                "entries": queue})
        else:
            entry = existing
    out["gate"] = {
        "mode": "edit",
        "status": "NOT_FOUND_REFUSED" if reason == "not_found"
        else "AMBIGUOUS_REFUSED",
        "auto_edit": "refused",
        "manual_entry_id": entry["manual_entry_id"],
        "manual_reason": reason,
    }
    return out


def manual_queue(state_root: Path, document_id: str) -> dict:
    """人工入口回读（append-only 账；本面绝不删改条目、绝不代人工处置）。"""
    return {"schema": SCHEMA, "document_id": document_id,
            "entries": _load_manual_queue(state_root, document_id)}


def read_anchor(state_root: Path, document_id: str, anchor_id: str) -> dict:
    """锚记录回读（溯源事实：登记时文本 sha 与 span；登记后不可改写）。"""
    return _require_anchor(state_root, document_id, anchor_id)


# --------------------------------------------------------------------------
# 桥分发（legal_entry anchor.* 唯一入口；fail-closed 同基线）
# --------------------------------------------------------------------------

def anchor_call(method: str, args: dict, config: dict) -> dict:
    state_root = config.get("anchor_state_root")
    if not state_root:
        raise _fail("f50_state_root_not_configured")

    def _document_id() -> str:
        document_id = args.get("document_id")
        if not isinstance(document_id, str) \
                or not _DOC_ID_RE.match(document_id):
            raise _fail("f50_document_id_invalid")
        return document_id

    def _anchor_id() -> str:
        anchor_id = args.get("anchor_id")
        if not isinstance(anchor_id, str) or not anchor_id:
            raise _fail("f50_anchor_id_required")
        return anchor_id

    try:
        if method == "anchor.register":
            return register(Path(state_root), _document_id(),
                            args.get("matter_id"),
                            args.get("quote"), args.get("text"))
        if method == "anchor.locate":
            return locate(Path(state_root), _document_id(), _anchor_id(),
                          args.get("text"))
        if method == "anchor.gate_edit":
            return gate_edit(Path(state_root), _document_id(), _anchor_id(),
                             args.get("text"), args.get("replacement"))
        if method == "anchor.manual_queue":
            return manual_queue(Path(state_root), _document_id())
        if method == "anchor.read":
            return read_anchor(Path(state_root), _document_id(),
                               _anchor_id())
        raise _fail("f50_method_unknown")
    except AnchorError:
        raise
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise _fail("f50_failed:" + type(exc).__name__) from None
