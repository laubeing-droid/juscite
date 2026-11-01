# -*- coding: utf-8 -*-
"""F82 Tabular 窄版闭环核心产品面（工单 W2b-U05）。

窄版闭环＝列三元组（列名/金标/值）＋批量执行＋出处（引用逐条回原文）
＋支持状态（核验戳经 U02 citation 面）＋失效回读。本模块是**编排与投影**
，不是第二核验器、不是第二材料真源：

  - 批量执行走 W2b-U01 已 VERIFIED 的 harness.review_batch_*（行租约＋
    generation 写守卫；迟到结果不覆人改）；
  - 支持状态走 U02 已 VERIFIED 的 extraction.*（强制闸，其核验唯一权威
    ＝W2a-U14 citation.*）；tabular.support_stamp 把闸跑结论转录进
    harness 格支持账（schema v17，W2b-U05 新增 review_support_* 面）——
    顺序纪律（07 E14：先引用核验服务再接抽取，非相互循环施工依赖）在
    结构上成立：未过闸候选（UNVERIFIED）不可盖章；
  - 出处审计（F82-溯源）：逐条引用回原文两端对账——材料侧重读语料页
    文本（sha256 与戳内钉定值比对＝源版本未漂移＋引用文本在页内）＋
    法规侧同面复验（citation.verify 重跑，状态与戳一致）。材料文本经
    config.tabular_corpus_root 只读（本面不写任何材料；生产接线换 E12
    导出面时同键同形，不建第二真源）；
  - quote 存在不等于命题支持：支持最好结局也只是引用级
    （SUPPORTED_CITATION_LEVEL），命题恒不代签（06 F82/F87 acceptance）。

金额纪律：金标 number 对照用 Decimal（十进制字符串跨界，不落浮点）；
本面不解释值语义，goldMatch 是确定性投影（正则＋Decimal 比较）。

状态面：抽取/闸状态在 extraction_gate 状态根（既有）；支持账在
harness MatterStore（SQLite/PG 同合同）。本模块无自有持久化。
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bridge_errors import NotConnected

TABULAR_FACE_NOTE = (
    "tabular(W2b-U05): harness.review_batch_*(W2b-U01)+extraction.*"
    "(W2b-U02)+harness.review_support_*(W2b-U05)")

# 金标 number 对照的确定性数字抽取（中文合同文本中的金额串：千位逗号
# ＋小数；不含单位——值语义解释到此为止，不做货币换算）。
_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_GOLD_KINDS = frozenset({
    "text", "enum", "number", "date", "boolean", "none",
})
# 失效理由闭集（与 harness review_support_invalidate 同集；产品侧只做
# 透传前校验，权威在 harness）。
INVALIDATION_REASONS = frozenset({
    "source_version_stale", "gate_face_drift",
})

_STAMP_ARGS_FIELDS = frozenset({
    "extraction_batch_id", "candidate_id", "review_batch_id", "row_id",
    "cell_id", "actor_id", "scope", "key",
})
_READ_ARGS_FIELDS = frozenset({"review_batch_id", "scope"})
_INVALIDATE_ARGS_FIELDS = frozenset({
    "review_batch_id", "row_id", "cell_id", "reason", "detail",
    "source_ref", "actor_id", "scope", "key",
})
_AUDIT_ARGS_FIELDS = frozenset({"review_batch_id", "scope"})


def _harness_call(method: str, args: dict, config: dict) -> dict:
    """harness 公开面分派 seam（默认=legal_entry.call 子进程径；selfhost
    侧 PG 直连部署由调用方替换本 seam——同 F25 recon 先例）。"""
    import legal_entry
    return legal_entry.call(method, args, config)


def _require(args: dict, fields: frozenset, code: str,
             optional: frozenset = frozenset({})) -> None:
    """DTO 闭集校验：必带字段缺一即拒、闭集外字段即拒（无旁路）。"""
    if not isinstance(args, dict) or set(args) - set(fields) \
            or (set(fields) - set(optional)) - set(args):
        raise NotConnected(code)


def _scope_of(args: dict) -> dict:
    scope = args.get("scope")
    if not isinstance(scope, dict) or scope.get("kind") != "matter" \
            or not isinstance(scope.get("matterId"), str) \
            or not scope.get("matterId"):
        raise NotConnected("tabular_scope_invalid")
    return scope


def _command_key(args: dict) -> dict:
    key = args.get("key")
    if not isinstance(key, dict) or not isinstance(key.get("requestId"), str) \
            or not key.get("requestId"):
        raise NotConnected("tabular_command_key_invalid")
    return key


# ---------------------------------------------------------------------- #
# tabular.read —— 列三元组投影（列名/金标/值＋支持状态）
# ---------------------------------------------------------------------- #


def _gold_match(gold: dict, value) -> dict:
    """金标对照（确定性投影；None＝不可对照，False＋reason＝可对照不符
    或值不可解析——不伪填不猜）。"""
    if not isinstance(gold, dict) or gold.get("kind") not in _GOLD_KINDS:
        return {"goldMatch": None, "goldMatchReason": "gold_absent"}
    kind = gold["kind"]
    expect = gold.get("expect")
    if kind == "none" or expect is None:
        return {"goldMatch": None, "goldMatchReason": "type_only_gold"}
    if value is None:
        return {"goldMatch": False, "goldMatchReason": "value_absent"}
    if kind == "enum":
        match = isinstance(value, str) and value in expect
        return {"goldMatch": match,
                "goldMatchReason": None if match else "enum_miss"}
    if kind == "boolean":
        match = value is expect
        return {"goldMatch": match,
                "goldMatchReason": None if match else "boolean_miss"}
    if kind in ("text", "date"):
        if not isinstance(value, str):
            return {"goldMatch": False,
                    "goldMatchReason": "value_not_text"}
        match = value.strip() == expect
        return {"goldMatch": match,
                "goldMatchReason": None if match else "text_miss"}
    # number：十进制字符串对照（金额纪律——Decimal，不落浮点）。
    if not isinstance(value, str):
        return {"goldMatch": False, "goldMatchReason": "value_not_text"}
    found = _NUMBER_RE.search(value.replace("，", ","))
    if not found:
        return {"goldMatch": False, "goldMatchReason": "number_unparseable"}
    try:
        match = Decimal(found.group(0).replace(",", "")) == Decimal(expect)
    except InvalidOperation:
        return {"goldMatch": False, "goldMatchReason": "number_unparseable"}
    return {"goldMatch": match,
            "goldMatchReason": None if match else "number_miss"}


def tabular_read(args: dict, config: dict) -> dict:
    _require(args, _READ_ARGS_FIELDS, "tabular_read_args_invalid")
    scope = _scope_of(args)
    batch_id = args.get("review_batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise NotConnected("tabular_batch_id_required")
    contract = _harness_call("harness.review_columns_read",
                             {"scope": scope, "batch_id": batch_id}, config)
    batch = _harness_call("harness.review_batch_read",
                          {"scope": scope, "batch_id": batch_id}, config)
    support = _harness_call("harness.review_support_read",
                            {"scope": scope, "batch_id": batch_id}, config)
    columns = {column["id"]: column for column in contract.get("columns", [])}
    support_index = {
        (projection.get("rowId"), projection.get("cellId")): projection
        for projection in support.get("projections", [])}
    rows_out = []
    for row in batch.get("rows", []):
        # F25 批级 read 只回行头；格面（值/generation/来源）逐行取。
        row_view = _harness_call("harness.review_batch_read",
                                 {"scope": scope, "batch_id": batch_id,
                                  "row_id": row["id"]}, config)
        cells_map = (row_view.get("row") or {}).get("cells") or {}
        cells_out = []
        for cell_id, cell in cells_map.items():
            column = columns.get(cell_id, {})
            projection = support_index.get((row["id"], cell_id), {})
            triple = {
                "columnId": cell_id,
                "columnName": column.get("name"),
                "gold": column.get("gold"),
                "value": cell.get("value"),
                "cellGeneration": cell.get("generation"),
                "cellSource": cell.get("source"),
                "supportStatus": projection.get("supportStatus",
                                                "NO_STAMP"),
            }
            triple.update(_gold_match(column.get("gold"), cell.get("value")))
            cells_out.append(triple)
        rows_out.append({"rowId": row["id"], "rowState": row.get("state"),
                         "cells": cells_out})
    counts = support.get("counts", {})
    return {
        "reviewBatchId": batch_id,
        "batchStatus": batch.get("status"),
        "columnContractDefined": contract.get("defined", False),
        "columns": contract.get("columns", []),
        "rows": rows_out,
        "supportCounts": counts,
        "accounting": "per_cell_scoped",
        "note": "列三元组（列名/金标/值）逐格投影；goldMatch=None＝不可"
                "对照（纯类型金标）；支持状态投影闭集见 harness 面；命题"
                "恒不代签",
        "face": TABULAR_FACE_NOTE,
    }


# ---------------------------------------------------------------------- #
# tabular.support_stamp —— 核验戳经 U02 citation 面转录入账（E14 接线点）
# ---------------------------------------------------------------------- #


def support_stamp(args: dict, config: dict) -> dict:
    _require(args, _STAMP_ARGS_FIELDS, "tabular_stamp_args_invalid")
    scope = _scope_of(args)
    _command_key(args)
    actor_id = args.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        raise NotConnected("tabular_actor_invalid")
    for field in ("extraction_batch_id", "candidate_id", "review_batch_id",
                  "row_id", "cell_id"):
        if not isinstance(args.get(field), str) or not args.get(field):
            raise NotConnected("tabular_stamp_%s_required" % field)
    # 核验面钉定：戳内 faceSha256 记录闸跑所要求的 config 钉（U02 闸未
    # 钉定即拒绝开闸——已过闸候选蕴含钉定在案；审计时同钉复验）。
    pinned = config.get("codices_face_sha256")
    if not isinstance(pinned, str) or not _SHA_RE.fullmatch(pinned):
        raise NotConnected("tabular_stamp_face_pin_required")
    # 闸结论唯一来源＝U02 面回读（本模块不重跑核验、不重判）。
    from extraction_gate import candidate_read
    view = candidate_read({"batch_id": args["extraction_batch_id"],
                           "candidate_id": args["candidate_id"]}, config)
    if view.get("gate_status") == "UNVERIFIED":
        raise NotConnected("tabular_stamp_requires_gated_candidate:"
                           + str(args["candidate_id"]))
    history = view.get("gate_history") or []
    if not history:
        raise NotConnected("tabular_stamp_no_gate_history")
    latest = history[-1]
    provenance = view.get("provenance") or {}
    if not isinstance(provenance.get("textSha256"), str) \
            or not _SHA_RE.fullmatch(provenance["textSha256"]):
        raise NotConnected("tabular_stamp_requires_page_sha256:"
                           "provenance.textSha256（出处必须钉字节——抽取"
                           "候选登记面须携带页文本 sha256）")
    if provenance.get("source") != "material_extraction" \
            or not isinstance(provenance.get("doc"), str) \
            or not provenance.get("doc") \
            or not isinstance(provenance.get("page"), int) \
            or isinstance(provenance.get("page"), bool):
        raise NotConnected("tabular_stamp_provenance_invalid:"
                           "source/doc/page 必填（material_extraction）")
    stamp_provenance = {"source": "material_extraction",
                        "doc": provenance["doc"],
                        "page": provenance["page"],
                        "textSha256": provenance["textSha256"]}
    for extra in ("block", "bbox"):
        if provenance.get(extra) is not None:
            stamp_provenance[extra] = provenance[extra]
    citations = []
    for citation in latest.get("citations", []):
        citations.append({
            "citationText": citation.get("citation_text"),
            "status": citation.get("status"),
            "code": citation.get("code"),
            "verifiedScoped": citation.get("verified_scoped"),
            "quoteInArticle": citation.get("quote_in_article"),
            **({"identifier": citation["identifier"]}
               if citation.get("identifier") is not None else {}),
        })
    entry = {
        "gate": {
            "via": "extraction.gate(W2b-U02)",
            "face": latest.get("verification_face")
                    or "citation.verify(W2a-U14 VERIFIED)→"
                       "statute.citation_gate(W2a-U13)→"
                       "lccc_consumer(E22 freeze v1.1)",
            "faceSha256": pinned,
            "asOf": latest.get("as_of"),
            "runSeq": latest.get("run_seq"),
            "extractionBatchId": args["extraction_batch_id"],
            "candidateId": args["candidate_id"],
            "gateStatus": view.get("gate_status"),
            "rejectionReasons": view.get("rejection_reasons", []),
        },
        "citations": citations,
        "provenance": stamp_provenance,
    }
    return _harness_call("harness.review_support_record", {
        "actor_id": actor_id, "scope": scope, "key": args["key"],
        "batch_id": args["review_batch_id"], "row_id": args["row_id"],
        "cell_id": args["cell_id"], "entry": entry}, config)


# ---------------------------------------------------------------------- #
# tabular.invalidate —— 失效登记（薄透传；理由闭集权威在 harness）
# ---------------------------------------------------------------------- #


def tabular_invalidate(args: dict, config: dict) -> dict:
    _require(args, _INVALIDATE_ARGS_FIELDS, "tabular_invalidate_args_invalid",
             optional=frozenset({"detail", "source_ref"}))
    scope = _scope_of(args)
    _command_key(args)
    if args.get("reason") not in INVALIDATION_REASONS:
        raise NotConnected("tabular_invalidate_reason_invalid:"
                           + str(args.get("reason")))
    payload = {"actor_id": args.get("actor_id"), "scope": scope,
               "key": args["key"], "batch_id": args["review_batch_id"],
               "row_id": args["row_id"], "cell_id": args["cell_id"],
               "reason": args["reason"]}
    if args.get("detail") is not None:
        payload["detail"] = args["detail"]
    if args.get("source_ref") is not None:
        payload["source_ref"] = args["source_ref"]
    return _harness_call("harness.review_support_invalidate", payload,
                         config)


# ---------------------------------------------------------------------- #
# tabular.audit —— 出处审计（F82-溯源：引用逐条回原文）
# ---------------------------------------------------------------------- #


def _corpus_page_text(corpus_root: str, doc: str, page: int) -> str:
    path = Path(corpus_root) / doc / ("page-%d.txt" % page)
    if not path.is_file():
        raise NotConnected("tabular_audit_source_page_missing:%s/%d"
                           % (doc, page))
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise NotConnected("tabular_audit_source_unreadable:"
                           + type(exc).__name__) from None


def tabular_audit(args: dict, config: dict) -> dict:
    """出处审计：材料侧（页文本 sha＋引用在页内）＋法规侧（同面复验一致）。

    审计对象＝每格**当前声明**（末条目为 support 的戳；投影同源语义）。
    已失效（末条目 invalidation）或被新戳取代的旧条目不重申——它们的
    失效/取代本身就在账上可回读（historical 计数）。REJECTED 戳无法规侧
    复验面（拒因重放属闸面职责），标注 not_applicable_rejected。
    """
    _require(args, _AUDIT_ARGS_FIELDS, "tabular_audit_args_invalid")
    scope = _scope_of(args)
    batch_id = args.get("review_batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise NotConnected("tabular_batch_id_required")
    corpus_root = config.get("tabular_corpus_root")
    if not isinstance(corpus_root, str) or not corpus_root:
        raise NotConnected("tabular_corpus_root_not_configured")
    pinned = config.get("codices_face_sha256")
    if not isinstance(pinned, str) or not _SHA_RE.fullmatch(pinned):
        raise NotConnected("tabular_audit_face_pin_required")
    support = _harness_call("harness.review_support_read",
                            {"scope": scope, "batch_id": batch_id}, config)
    findings = []
    statute_ok = statute_checked = source_ok = source_checked = 0
    historical = 0
    invalidated_cells = 0
    for key, entries in (support.get("entries") or {}).items():
        if not entries:
            continue
        historical += len(entries) - 1
        entry = entries[-1]
        record = entry.get("record") or {}
        if record.get("entryKind") == "invalidation":
            invalidated_cells += 1
            findings.append({
                "cell": key, "status": "invalidated",
                "reason": record.get("reason"),
                "historicalStamps": len(entries) - 1,
            })
            continue
        gate = record.get("gate") or {}
        provenance = record.get("provenance") or {}
        doc, page = provenance.get("doc"), provenance.get("page")
        # 材料侧：页文本重读＋sha 对账＋引用文本在页内（逐条回原文）。
        page_text = _corpus_page_text(corpus_root, doc, page)
        page_sha = hashlib.sha256(
            page_text.encode("utf-8")).hexdigest()
        sha_ok = page_sha == provenance.get("textSha256")
        source_checked += 1
        citation_hits = []
        for citation in record.get("citations", []):
            text = citation.get("citationText")
            citation_hits.append({
                "citationText": text,
                "inSourceText": isinstance(text, str) and text in page_text,
                "storedStatus": citation.get("status"),
                "storedQuoteInArticle": citation.get("quoteInArticle"),
            })
        source_ok += 1 if (sha_ok and all(
            hit["inSourceText"] for hit in citation_hits)) else 0
        finding = {
            "cell": key, "seq": entry.get("seq"),
            "gateStatus": gate.get("gateStatus"),
            "sourceShaOk": sha_ok,
            "citations": citation_hits,
        }
        # 法规侧：同面复验（重跑 citation.verify，与戳内结论对账）。
        if gate.get("gateStatus") != "CITATION_VERIFIED":
            finding["statuteReplay"] = "not_applicable_rejected"
            statute_checked += 0
            findings.append(finding)
            continue
        from citation_verifier import parse_citations, verify_citation
        from extraction_gate import candidate_read
        try:
            view = candidate_read({
                "batch_id": gate.get("extractionBatchId"),
                "candidate_id": gate.get("candidateId")}, config)
        except NotConnected:
            view = None
        if view is None:
            finding["statuteReplay"] = "candidate_unreadable"
            findings.append(finding)
            continue
        as_of = gate.get("asOf")
        replays = []
        for parsed in parse_citations(view.get("text") or ""):
            parsed = dict(parsed)
            parsed["as_of"] = as_of
            replay = verify_citation(parsed, config)
            replays.append({
                "citationText": replay.get("citation_text"),
                "status": replay.get("status"),
                "verifiedScoped": replay.get("verified_scoped"),
                "quoteInArticle": (
                    replay.get("support") or {}
                ).get("quote_in_article"),
            })
        stored = {citation.get("citationText"): citation
                  for citation in record.get("citations", [])}
        consistent = len(replays) == len(stored) and all(
            stored.get(replay["citationText"], {}).get(
                "status") == replay["status"]
            and stored.get(replay["citationText"], {}).get(
                "quoteInArticle") == replay["quoteInArticle"]
            for replay in replays)
        finding["statuteReplay"] = {
            "consistent": consistent,
            "replays": replays,
        }
        statute_checked += 1
        statute_ok += 1 if consistent else 0
        findings.append(finding)
    audited = source_checked
    ok = audited > 0 and source_ok == source_checked \
        and statute_ok == statute_checked
    return {
        "reviewBatchId": batch_id,
        "auditedStamps": audited,
        "sourceTraced": "%d/%d" % (source_ok, source_checked),
        "statuteConsistent": "%d/%d" % (statute_ok, statute_checked),
        "invalidatedCells": invalidated_cells,
        "historicalEntries": historical,
        "findings": findings,
        "auditStatus": "AUDIT_OK" if ok else "AUDIT_FAIL",
        "corpusRoot": corpus_root,
        "face": TABULAR_FACE_NOTE,
    }


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（tabular.*）
# ---------------------------------------------------------------------- #


def tabular_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发（tabular.*）。未列方法绝不落到这里。"""
    if method == "tabular.read":
        return tabular_read(args, config)
    if method == "tabular.support_stamp":
        return support_stamp(args, config)
    if method == "tabular.invalidate":
        return tabular_invalidate(args, config)
    return tabular_audit(args, config)  # tabular.audit
