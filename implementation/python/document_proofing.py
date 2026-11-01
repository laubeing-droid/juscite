"""F143 法律写作校对插件（一致性/术语，定位原文可接受拒绝）（W5-U14）：
产品侧 document-adapter 公开面——术语表/一致性规则的确定性校对候选面。

义务 06:V7-143 断言（验收向量逐字）：「一致性/术语校对定位原文且可接受
拒绝；不同语义不自动合并」。17 卡 steps（逐字）：「公开proposal/base
refs→宿主原生定位/修订/比对→部分接受/拒绝→重读实际文件→CAS/version→
Harness正式采用；不模拟DOCX」。

纪律：
- 定位沿 F50/F51 引用原文重锚定纪律（W2b-U13，00-总协调 W2b-U13 行）：
  发现项的定位＝原文逐字引文（quote＝所在段全文）在当前文档文本中的
  精确子串重搜（零折叠零规范化、重叠命中计数、大小写不折叠）。quote
  唯一命中才 LOCATED（携溯源 span，position_source=verbatim_quote_match、
  offset_conversion_used 恒 False）；零/多命中＝AMBIGUOUS——候选不携带
  任何位置字段（不以偏移强改），落 needs_review 留人。禁就近匹配：
  本模块不存在任何模糊/编辑距离/前缀逼近代码（结构性缺席，非阈值 0）。
- 不同语义不自动合并（红线）：合并仅限逐条确定性同语义判定——
  (rule_id, match, suggestion) 全同且逐条 quote 逐字唯一命中才并入同一
  proposed 候选；两条不同规则命中同一重叠 span 且建议不同＝语义冲突
  候选（status=conflict），各自独立呈现、绝不互相合并；人同时接受两条
  冲突候选时 propose 具名拒（f143_conflict_candidates_accepted）——语义
  冲突必须留人逐条裁决，机器不代选。
- 候选→人审接受/拒绝→canonical（F47 提案/采用合同，W2b-U11）：本面
  产候选与决定账，propose 把已接受候选确定性转成 F49 封闭算子集 JSON
  （body.replace_text/table.cell_text）并重放出真实更正 DOCX；Harness
  正式采用（formal_propose/formal_decide·CAS/version·resultBytesB64＝
  重读盘上实际文件回流）由桥/调用方编排，本面不复制第二账本。
- 不模拟 DOCX：输入输出都是真实 DOCX 包字节。算子重放复用 W2b-U14
  document_redline 既有 VERIFIED 机制（包读取/确定性序列化/固定 zip
  时间戳），非文本部件逐字节保真；修订线（w:ins/w:del）属 F48/F49 面，
  本面不重做（更正文档＝确定性重放产物，同 F49 replay.docx 形态）。
- 术语表/一致性规则＝合成冻结清单（模块级 RULESET 常量＋RULESET_SHA256
  钉定；ruleset_read 回读）。确定性：无模型、无网络、无随机、无时钟入
  XML（同输入同输出；created/decided/built 时间戳除外）。
- v1 边界如实：扫描面＝正文段与表格单元格首段（build_text_index 现行
  文本语义，w:delText 不算现行文本）；脚注文本不扫描（负控在 recon）；
  单元格非首段命中＝定位得到但应用面不覆盖，候选落 needs_review 留人
  （fail-closed 不静默丢）。段落定位偏移 match_offset_in_quote 是 quote
  内容自身的常量属性（quote 逐字节定位后段内结构不变），不是跨文档
  偏移换算——跨文档位置一律由 quote 重搜现场推导。

fail-closed：未配置状态根、参数非法、文档未登记、字节漂移、候选未知、
冲突同受、重锚失败、闭集外方法——一律 typed error（f143_* 错误码），
错误码不携材料内容。状态根纪律同 document-adapter 基线（TEMP/显式配
置，绝不写 %APPDATA%）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "juscite-f143-proofing/1"
STATE_SUBDIR = "document-proofing"
DEFAULT_AUTHOR = "lvyin-proofing"   # F53 作者声明闭集 proofing 通道绑定

# 合成冻结清单（术语表＋一致性规则；全合成、与任何真实业务无关）。
# 确定性校对面只认 exact 子串命中；suggestion＝整段文本内该命中的替换文。
RULESET = (
    {"rule_id": "T-01", "kind": "terminology", "match": "订金",
     "suggestion": "定金",
     "note": "合成冻结术语表：定金（担保）／订金（预付）用字统一"},
    {"rule_id": "T-02", "kind": "terminology", "match": "身份证号",
     "suggestion": "公民身份号码",
     "note": "合成冻结术语表：证件名称用词统一"},
    {"rule_id": "T-05", "kind": "terminology", "match": "收取订金",
     "suggestion": "收取预付款",
     "note": "合成冻结术语表：整词短语条目（与 T-01 同段重叠命中＝语义"
             "冲突候选留人，不自动合并）"},
    {"rule_id": "C-03", "kind": "consistency", "match": "叁拾陆万元",
     "suggestion": "叁拾陆万元整",
     "note": "合成冻结一致性规则：大写金额统一带『整』收尾"},
    {"rule_id": "C-04", "kind": "consistency", "match": "360000",
     "suggestion": "360,000.00",
     "note": "合成冻结一致性规则：小写金额统一千分位＋两位小数"},
)
RULESET_SHA256 = hashlib.sha256(
    json.dumps(list(RULESET), ensure_ascii=False, sort_keys=True)
    .encode("utf-8")).hexdigest()

RULE_KINDS = ("terminology", "consistency")
CANDIDATE_STATES = ("proposed", "conflict", "needs_review")
DECISION_ACTIONS = ("accept", "reject")

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = "{%s}" % _W_NS
_DOC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# 单写者纪律（状态根内串行；跨进程由调用方状态根隔离保证）。
# RLock：decide/propose 持锁期间复用 candidates()/scan()（同线程重入）。
_LOCK = threading.RLock()


class ProofingError(ValueError):
    """Typed F143 face failure; str() is a code, never material content."""

    error_code = "f143_invalid"


def _fail(code: str) -> ProofingError:
    return ProofingError(code)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def _digest(obj) -> str:
    return _sha256_bytes(_canonical_json(obj).encode("utf-8"))


def _find_all(text: str, needle: str) -> list[int]:
    """逐字精确命中（零折叠零规范化；重叠命中也计数——F50 同口径）。"""
    hits: list[int] = []
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            return hits
        hits.append(idx)
        start = idx + 1


# --------------------------------------------------------------------------
# 状态布局
# --------------------------------------------------------------------------

def _document_dir(state_root: Path, document_id: str) -> Path:
    return Path(state_root) / STATE_SUBDIR / document_id


def _atomic_write_json(path: Path, payload) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(_canonical_json(payload), encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _atomic_write_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(_canonical_json(r) + "\n" for r in rows),
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _load_manifest(state_root: Path, document_id: str) -> dict:
    path = _document_dir(state_root, document_id) / "document.json"
    if not path.is_file():
        raise _fail("f143_document_not_registered")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    original = _document_dir(state_root, document_id) / "original.docx"
    if not original.is_file() \
            or _sha256_bytes(original.read_bytes()) != manifest["sha256"]:
        raise _fail("f143_document_bytes_mismatch")
    return manifest


def _load_text(state_root: Path, document_id: str) -> tuple[str, list]:
    """现行文本索引（edits_protocol 既有 VERIFIED 装载机制——不建第二
    文本模型）：全文＋段记录（el／start／end／locator／body 序）。"""
    from edits_protocol import build_text_index
    manifest = _load_manifest(state_root, document_id)
    from document_redline import _read_package
    pkg = _read_package(_document_dir(state_root, document_id)
                        / "original.docx")
    text, segments = build_text_index(pkg["trees"]["word/document.xml"])
    if _sha256_bytes(text.encode("utf-8")) != manifest["text_sha256"]:
        raise _fail("f143_document_bytes_mismatch")
    locators = _para_locator_map(pkg["trees"]["word/document.xml"])
    paras: list[dict] = []
    order: dict[int, dict] = {}
    for seg in segments:
        rec = order.get(id(seg.para_el))
        if rec is None:
            rec = {"el": seg.para_el, "start": seg.start, "end": seg.end,
                   "locator": locators.get(id(seg.para_el)),
                   "seq": len(order)}
            order[id(seg.para_el)] = rec
            paras.append(rec)
        else:
            rec["end"] = seg.end
    return text, paras


def _para_locator_map(tree) -> dict:
    """段元素→落位（body 段序号／表格 t,r,c,p）。确定性走查，事实只读。"""
    body = tree.find(_W + "body")
    if body is None:
        raise _fail("f143_document_part_missing")
    out: dict = {}
    body_index = 0
    table_index = 0
    for child in body:
        if child.tag == _W + "p":
            out[id(child)] = {"kind": "body", "index": body_index}
            body_index += 1
        elif child.tag == _W + "tbl":
            for r, tr in enumerate(c for c in child if c.tag == _W + "tr"):
                for c, tc in enumerate(ch for ch in tr
                                       if ch.tag == _W + "tc"):
                    for pi, p in enumerate(ch for ch in tc
                                           if ch.tag == _W + "p"):
                        out[id(p)] = {"kind": "cell", "table": table_index,
                                      "row": r, "col": c, "para": pi}
            table_index += 1
    return out


# --------------------------------------------------------------------------
# 扫描（F50 纪律：quote 逐字重搜；多命中零位置字段）
# --------------------------------------------------------------------------

def scan(state_root: Path, document_id: str) -> dict:
    """对登记文档跑合成冻结规则集。发现项定位＝所在段全文（quote）逐字
    重搜；唯一命中才带溯源 span（offset_conversion_used 恒 False），
    多命中＝AMBIGUOUS 零位置字段（不以偏移强改）。确定性：同文档同
    规则集同输出。"""
    text, paras = _load_text(state_root, document_id)
    findings: list[dict] = []
    for rule in RULESET:
        variant = rule["match"]
        for m in _find_all(text, variant):
            para = next((p for p in paras if p["start"] <= m < p["end"]),
                        None)
            if para is None:                  # 防御性（文本只来自段）
                raise _fail("f143_failed:index_model_violation")
            quote = text[para["start"]:para["end"]]
            qhits = _find_all(text, quote)
            located = len(qhits) == 1
            finding = {
                "finding_id": "f-" + hashlib.sha256(
                    ("juscite-f143-finding\0" + document_id + "\0"
                     + rule["rule_id"] + "\0" + variant + "\0"
                     + str(m - para["start"]) + "\0" + quote)
                    .encode("utf-8")).hexdigest()[:16],
                "rule_id": rule["rule_id"],
                "kind": rule["kind"],
                "match": variant,
                "suggestion": rule["suggestion"],
                "note": rule["note"],
                "quote": quote,
                "match_offset_in_quote": m - para["start"],
                "location_status": ("LOCATED" if located
                                    else "AMBIGUOUS"),
                "quote_hits": len(qhits),
                "position_source": "verbatim_quote_match",
                "offset_conversion_used": False,
            }
            if located:
                # F50 纪律：唯一命中才携带位置面字段（locator/溯源 span）。
                # 多命中＝AMBIGUOUS 零位置字段（不以偏移强改）。
                finding["locator"] = para["locator"]
                finding["trace_span"] = [m, m + len(variant)]
            findings.append(finding)
    result = {
        "schema": SCHEMA,
        "document_id": document_id,
        "ruleset_sha256": RULESET_SHA256,
        "text_sha256": _sha256_bytes(text.encode("utf-8")),
        "findings": findings,
        "counts": {
            "total": len(findings),
            "located": sum(1 for f in findings
                           if f["location_status"] == "LOCATED"),
            "ambiguous": sum(1 for f in findings
                             if f["location_status"] == "AMBIGUOUS"),
        },
        "boundaries": {"scan_scope": "body_paragraphs_and_first_cell_"
                                     "paragraphs",
                       "footnotes_scanned": False},
    }
    with _LOCK:
        doc_dir = _document_dir(state_root, document_id)
        doc_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(doc_dir / "scan.json", result)
    return result


# --------------------------------------------------------------------------
# 候选合并（红线：合并仅限逐条确定性同语义判定；语义冲突留人）
# --------------------------------------------------------------------------

def _overlap(a: list[int], b: list[int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def candidates(state_root: Path, document_id: str) -> dict:
    """发现项确定性归并：
    - 同 (rule_id, match, suggestion) 且逐条 LOCATED 且不涉冲突 → 一条
      proposed 候选（occurrences 逐条保留，＝唯一允许的自动合并）；
    - 任意非 LOCATED 发现 → 按 (rule, match, suggestion, quote) 并入
      needs_review 候选（零位置字段，留人；绝不给建议位置）；
    - 不同规则重叠 span 且建议不同 → 各自独立 conflict 候选（定位照给
      ——冲突在语义不在位置；绝不互相合并、绝不自动择一）。
    """
    scanned = scan(state_root, document_id)
    findings = scanned["findings"]
    conflict_ids: set[str] = set()
    for i, a in enumerate(findings):
        if a["location_status"] != "LOCATED" or "trace_span" not in a:
            continue
        for b in findings[i + 1:]:
            if b is a or b["location_status"] != "LOCATED":
                continue
            if "trace_span" not in b:
                continue
            if a["rule_id"] == b["rule_id"]:
                continue
            if a["suggestion"] == b["suggestion"]:
                continue
            if _overlap(a["trace_span"], b["trace_span"]):
                conflict_ids.add(a["finding_id"])
                conflict_ids.add(b["finding_id"])
    out: list[dict] = []
    groups: dict[tuple, list[dict]] = {}
    for f in findings:
        key = (f["rule_id"], f["match"], f["suggestion"])
        groups.setdefault(key, []).append(f)

    def _occurrence(f: dict) -> dict:
        occ = {"quote": f["quote"],
               "match_offset_in_quote": f["match_offset_in_quote"],
               "locator": f["locator"], "finding_id": f["finding_id"]}
        if "trace_span" in f:
            occ["trace_span"] = f["trace_span"]
        return occ

    for (rule_id, match, suggestion), members in groups.items():
        # 应用面 v1 覆盖：body 段与单元格首段；单元格非首段命中＝定位
        # 得到但本面算子不覆盖 → needs_review 留人（fail-closed 不静默丢）。
        def _in_scope(f: dict) -> bool:
            locator = f.get("locator") or {}
            if locator.get("kind") == "body":
                return True
            if locator.get("kind") == "cell":
                return locator.get("para", 0) == 0
            return False

        clean = [f for f in members
                 if f["location_status"] == "LOCATED"
                 and f["finding_id"] not in conflict_ids
                 and _in_scope(f)]
        ambiguous_all = [f for f in members
                         if f["location_status"] == "AMBIGUOUS"]
        # 同 (rule, match, suggestion, quote) 的歧义发现并同一条 needs_review
        # 候选（同一处人审项；occurrences 逐条携 quote，仍然零位置字段）。
        amb_groups: dict = {}
        for f in ambiguous_all:
            amb_groups.setdefault(f["quote"], []).append(f)
        for quote, fs in sorted(amb_groups.items()):
            out.append({
                "candidate_id": "c-" + hashlib.sha256(
                    ("juscite-f143-cand\0" + document_id + "\0"
                     + rule_id + "\0" + match + "\0" + suggestion + "\0"
                     + "needs_review\0" + quote)
                    .encode("utf-8")).hexdigest()[:16],
                "rule_id": rule_id, "kind": fs[0]["kind"],
                "match": match, "suggestion": suggestion,
                "note": fs[0]["note"],
                "status": "needs_review",
                "reason": "quote_not_unique_no_position_left_to_human",
                # F50 红线：零/多命中不给任何位置字段——仅携 quote（原文）
                # 供人审；段内偏移/locator/trace 一律不带（不以偏移强改）。
                "occurrences": [{"quote": quote,
                                 "finding_id": f["finding_id"]}
                                for f in fs],
                "decision": None,
            })
        conflicted = [f for f in members
                      if f["finding_id"] in conflict_ids]
        extra_scope = [f for f in members
                       if f["location_status"] == "LOCATED"
                       and f["finding_id"] not in conflict_ids
                       and not _in_scope(f)]
        for f in conflicted:
            out.append({
                "candidate_id": "c-" + hashlib.sha256(
                    ("juscite-f143-cand\0" + document_id + "\0"
                     + f["finding_id"]).encode("utf-8")).hexdigest()[:16],
                "rule_id": rule_id, "kind": f["kind"],
                "match": match, "suggestion": suggestion,
                "note": f["note"],
                "status": "conflict",
                "reason": "semantic_conflict_overlap_left_to_human",
                "conflict_with": sorted(
                    g["finding_id"] for g in findings
                    if g["finding_id"] in conflict_ids
                    and g is not f
                    and g["rule_id"] != f["rule_id"]
                    and "trace_span" in g and "trace_span" in f
                    and _overlap(g["trace_span"], f["trace_span"])),
                "occurrences": [_occurrence(f)],
                "decision": None,
            })
        for f in extra_scope:
            out.append({
                "candidate_id": "c-" + hashlib.sha256(
                    ("juscite-f143-cand\0" + document_id + "\0"
                     + f["finding_id"]).encode("utf-8")).hexdigest()[:16],
                "rule_id": rule_id, "kind": f["kind"],
                "match": match, "suggestion": suggestion,
                "note": f["note"],
                "status": "needs_review",
                "reason": "cell_extra_paragraph_v1_boundary_left_to_human",
                "occurrences": [_occurrence(f)],
                "decision": None,
            })
        if clean:
            out.append({
                "candidate_id": "c-" + hashlib.sha256(
                    ("juscite-f143-cand\0" + document_id + "\0"
                     + rule_id + "\0" + match + "\0" + suggestion + "\0"
                     + "proposed\0"
                     + "\0".join(f["finding_id"] for f in clean))
                    .encode("utf-8")).hexdigest()[:16],
                "rule_id": rule_id, "kind": clean[0]["kind"],
                "match": match, "suggestion": suggestion,
                "note": clean[0]["note"],
                "status": "proposed",
                "reason": ("merged_same_semantics_deterministic"
                           if len(clean) > 1
                           else "single_located_occurrence"),
                "merge_key": [rule_id, match, suggestion],
                "occurrences": [_occurrence(f) for f in clean],
                "decision": None,
            })
    out.sort(key=lambda c: (c["status"], c["rule_id"], c["match"],
                            c["candidate_id"]))
    result = {
        "schema": SCHEMA,
        "document_id": document_id,
        "ruleset_sha256": RULESET_SHA256,
        "text_sha256": scanned["text_sha256"],
        "candidates": out,
        "state_counts": {s: sum(1 for c in out if c["status"] == s)
                         for s in CANDIDATE_STATES},
    }
    result["candidates_sha256"] = _digest(
        {k: v for k, v in result.items() if k != "candidates_sha256"})
    with _LOCK:
        doc_dir = _document_dir(state_root, document_id)
        doc_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(doc_dir / "candidates.json", result)
    return result


# --------------------------------------------------------------------------
# 决定账（append-only；人审接受/拒绝）
# --------------------------------------------------------------------------

def _load_decisions(state_root: Path, document_id: str) -> list[dict]:
    path = _document_dir(state_root, document_id) / "decisions.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _latest_decisions(rows: list[dict]) -> dict:
    latest: dict[str, dict] = {}
    for row in rows:
        latest[row["candidate_id"]] = row
    return latest


def decide(state_root: Path, document_id: str, candidate_id: str,
           action, actor_id) -> dict:
    """候选级人审（可接受拒绝）。append-only 账：同候选同动作同人连发
    幂等不双登；改判＝追加（最新有效）；propose 只认每候选最新决定。"""
    if action not in DECISION_ACTIONS:
        raise _fail("f143_action_invalid")
    if not isinstance(candidate_id, str) or not candidate_id \
            or not isinstance(actor_id, str) or not actor_id:
        raise _fail("f143_candidate_unknown")
    with _LOCK:
        listing = candidates(state_root, document_id)
        by_id = {c["candidate_id"]: c for c in listing["candidates"]}
        record_in = by_id.get(candidate_id)
        if record_in is None:
            raise _fail("f143_candidate_unknown")
        rows = _load_decisions(state_root, document_id)
        prior = _latest_decisions(rows).get(candidate_id)
        entry = {
            "seq": len(rows) + 1,
            "candidate_id": candidate_id,
            "candidate_digest": _digest(record_in),
            "action": action,
            "actor_id": actor_id,
            "decided_utc": _now_utc(),
        }
        if prior is not None and prior["action"] == action \
                and prior["actor_id"] == actor_id:
            return {"schema": SCHEMA, "document_id": document_id,
                    "recorded": False, "idempotent": True,
                    "latest": prior}
        rows.append(entry)
        _atomic_write_jsonl(
            _document_dir(state_root, document_id) / "decisions.jsonl",
            rows)
    return {"schema": SCHEMA, "document_id": document_id,
            "recorded": True, "idempotent": False, "latest": entry}


# --------------------------------------------------------------------------
# 提案构建（F49 封闭算子集＋确定性重放＝真实更正 DOCX）
# --------------------------------------------------------------------------

def _reanchor(text: str, candidate: dict) -> list[dict]:
    """F50 重锚定：逐条 quote 在当前文本重搜；唯一命中才取段内偏移定位
    match（quote 内容常量属性），并逐字复核命中内容。零/多命中＝具名拒。"""
    anchored = []
    for occ in candidate["occurrences"]:
        if "trace_span" not in occ:
            raise _fail("f143_candidate_not_located:" + candidate["candidate_id"])
        hits = _find_all(text, occ["quote"])
        if len(hits) != 1:
            raise _fail("f143_reanchor_failed:" + candidate["candidate_id"])
        start = hits[0] + occ["match_offset_in_quote"]
        end = start + len(candidate["match"])
        if text[start:end] != candidate["match"]:
            raise _fail("f143_reanchor_mismatch:" + candidate["candidate_id"])
        anchored.append({"start": start, "end": end, "occ": occ})
    return anchored


def propose(state_root: Path, document_id: str) -> dict:
    """已接受候选→F49 封闭算子集（body.replace_text/table.cell_text）→
    确定性重放出真实更正 DOCX（独立在盘工件，非模拟 DOCX）。语义冲突
    同受＝f143_conflict_candidates_accepted 具名拒（语义冲突必须留人）；
    定位漂移/歧义＝f143_reanchor_failed 具名拒（不猜改）。确定性：同接
    受集同文档→同 ops 同 corrected 字节。"""
    from document_redline import (_read_package, _replay_to_parts,
                                  _write_package)
    accepted_ids = _accepted_ids(state_root, document_id)
    if not accepted_ids:
        raise _fail("f143_no_accepted_candidates")
    text, paras = _load_text(state_root, document_id)
    listing = candidates(state_root, document_id)
    by_id = {c["candidate_id"]: c for c in listing["candidates"]}
    accepted = [by_id[i] for i in accepted_ids]
    anchored: list[dict] = []
    for cand in accepted:
        for item in _reanchor(text, cand):
            anchored.append({"candidate": cand, "start": item["start"],
                             "end": item["end"]})
    anchored.sort(key=lambda a: (a["start"], a["end"],
                                 a["candidate"]["candidate_id"]))
    for prev, cur in zip(anchored, anchored[1:]):
        if _overlap([prev["start"], prev["end"]],
                    [cur["start"], cur["end"]]):
            raise _fail("f143_conflict_candidates_accepted")
    by_para: dict[int, dict] = {}
    for item in anchored:
        para = next((p for p in paras
                     if p["start"] <= item["start"] < p["end"]), None)
        if para is None:
            raise _fail("f143_reanchor_failed:" +
                        item["candidate"]["candidate_id"])
        locator = para["locator"] or {}
        if locator.get("kind") == "cell" and locator.get("para", 0) != 0:
            raise _fail("f143_scope_unsupported:cell_extra_paragraph")
        bucket = by_para.setdefault(para["seq"], {"para": para, "edits": []})
        bucket["edits"].append((item["start"] - para["start"],
                                item["end"] - para["start"],
                                item["candidate"]["suggestion"]))
    ops = []
    quotes = []
    for seq in sorted(by_para):
        bucket = by_para[seq]
        para = bucket["para"]
        quote = text[para["start"]:para["end"]]
        new_text = quote
        for start, end, repl in sorted(bucket["edits"], reverse=True):
            new_text = new_text[:start] + repl + new_text[end:]
        locator = para["locator"] or {}
        if locator.get("kind") == "body":
            ops.append({"op": "body.replace_text",
                        "index": locator["index"], "text": new_text})
        else:
            ops.append({"op": "table.cell_text",
                        "table": locator["table"], "row": locator["row"],
                        "col": locator["col"], "text": new_text})
        quotes.append({"text": quote, "para_seq": seq,
                       "new_text": new_text})
    ops_digest = _digest(ops)
    accepted_digest = _digest(accepted_ids)
    proposal_id = "f143p-" + hashlib.sha256(
        ("juscite-f143-proposal\0" + document_id + "\0"
         + accepted_digest + "\0" + ops_digest)
        .encode("utf-8")).hexdigest()[:16]
    doc_dir = _document_dir(state_root, document_id)
    payload = {
        "schema": SCHEMA,
        "proposal_id": proposal_id,
        "document_id": document_id,
        "base_text_sha256": listing["text_sha256"],
        "accepted_candidates": accepted_ids,
        "accepted_digest": accepted_digest,
        "ops": ops,
        "ops_digest": ops_digest,
        "quotes": quotes,
        "built_utc": _now_utc(),
    }
    with _LOCK:
        pkg = _read_package(doc_dir / "original.docx")
        replacements = _replay_to_parts(
            pkg, {"ops": [{"op": op["op"], **{k: v for k, v in op.items()
                                              if k != "op"}}
                          for op in ops]})
        # 不模拟 DOCX＋未触部件逐字节保真：v1 算子集只改 document.xml；
        # _replay_to_parts 会无条件重排 footnotes.xml（F49 面内语义），
        # 本面无脚注算子——未触部件从替换集中剔除，字节保持登记原样。
        replacements = {"word/document.xml":
                        replacements["word/document.xml"]}
        _write_package(doc_dir / "corrected.docx", pkg["parts"],
                       pkg["order"], replacements)
        corrected_sha = _sha256_bytes(
            (doc_dir / "corrected.docx").read_bytes())
    payload["corrected"] = {"file": "corrected.docx",
                            "sha256": corrected_sha}
    prior_path = doc_dir / "proposal.json"
    idempotent = False
    if prior_path.is_file():
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        idempotent = (prior.get("proposal_id") == proposal_id
                      and prior.get("accepted_digest") == accepted_digest
                      and prior.get("corrected", {}).get("sha256")
                      == corrected_sha)
    with _LOCK:
        _atomic_write_json(prior_path, payload)
    return {"schema": SCHEMA, "document_id": document_id,
            "proposal": payload, "idempotent": idempotent}


def _accepted_ids(state_root: Path, document_id: str) -> list[str]:
    """每候选最新决定＝accept 的候选 id 列表（升序；未知候选具名拒）。"""
    listing = candidates(state_root, document_id)
    by_id = {c["candidate_id"]: c for c in listing["candidates"]}
    latest = _latest_decisions(_load_decisions(state_root, document_id))
    accepted_ids = []
    for candidate_id, row in latest.items():
        if row["action"] != "accept":
            continue
        if candidate_id not in by_id:
            raise _fail("f143_candidate_unknown")
        accepted_ids.append(candidate_id)
    accepted_ids.sort()
    return accepted_ids


def proposal_read(state_root: Path, document_id: str) -> dict:
    path = _document_dir(state_root, document_id) / "proposal.json"
    if not path.is_file():
        raise _fail("f143_proposal_absent")
    payload = json.loads(path.read_text(encoding="utf-8"))
    corrected = _document_dir(state_root, document_id) / "corrected.docx"
    if corrected.is_file():
        payload = dict(payload)
        payload["corrected_on_disk_sha256"] = _sha256_bytes(
            corrected.read_bytes())
    return payload


def read_document(state_root: Path, document_id: str) -> dict:
    """重读盘上实际文件（F47 resultBytesB64 回流源；不缓存不转写）。"""
    _load_manifest(state_root, document_id)
    doc_dir = _document_dir(state_root, document_id)
    corrected = doc_dir / "corrected.docx"
    import base64
    if corrected.is_file():
        return {"schema": SCHEMA, "document_id": document_id,
                "which": "corrected", "file": "corrected.docx",
                "bytesB64": base64.b64encode(corrected.read_bytes())
                .decode("ascii")}
    original = doc_dir / "original.docx"
    return {"schema": SCHEMA, "document_id": document_id,
            "which": "original", "file": "original.docx",
            "bytesB64": base64.b64encode(original.read_bytes())
            .decode("ascii")}


def ruleset_read() -> dict:
    return {"schema": SCHEMA, "ruleset_sha256": RULESET_SHA256,
            "kinds": list(RULE_KINDS),
            "rules": [dict(rule) for rule in RULESET],
            "frozen": True,
            "author": DEFAULT_AUTHOR}


def register(state_root: Path, document_id, matter_id, bytes_b64) -> dict:
    """登记校对文档（真实 DOCX 字节；同 id 同字节幂等，异字节具名拒；
    登记后钉定——扫描/候选/决定/提案全部面向该基面）。"""
    if not isinstance(document_id, str) or not _DOC_ID_RE.match(document_id):
        raise _fail("f143_document_id_invalid")
    if not isinstance(bytes_b64, str):
        raise _fail("f143_bytes_required")
    import base64
    try:
        payload = base64.b64decode(bytes_b64, validate=True)
    except Exception:
        raise _fail("f143_document_bytes_invalid") from None
    sha = _sha256_bytes(payload)
    with _LOCK:
        doc_dir = _document_dir(state_root, document_id)
        manifest_path = doc_dir / "document.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest["sha256"] != sha:
                raise _fail("f143_document_bytes_mismatch")
            out = dict(manifest)
            out["idempotent"] = True
            return out
        from edits_protocol import build_text_index
        from document_redline import _read_package_bytes
        try:
            pkg = _read_package_bytes(payload)
        except ProofingError:
            raise
        except Exception as exc:
            raise _fail("f143_docx_unreadable:" + type(exc).__name__) from None
        text, _segs = build_text_index(pkg["trees"]["word/document.xml"])
        manifest = {
            "schema": SCHEMA,
            "document_id": document_id,
            "matter_id": matter_id,
            "sha256": sha,
            "bytes": len(payload),
            "text_sha256": _sha256_bytes(text.encode("utf-8")),
            "registered_utc": _now_utc(),
        }
        doc_dir.mkdir(parents=True, exist_ok=True)
        original = doc_dir / "original.docx"
        tmp = original.with_suffix(".tmp")
        tmp.write_bytes(payload)
        os.replace(tmp, original)
        _atomic_write_json(manifest_path, manifest)
    out = dict(manifest)
    out["idempotent"] = False
    return out


def list_documents(state_root: Path) -> dict:
    root = Path(state_root) / STATE_SUBDIR
    if not root.is_dir():
        return {"schema": SCHEMA, "documents": []}
    docs = []
    for manifest_path in sorted(root.glob("*/document.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        docs.append({"document_id": manifest["document_id"],
                     "matter_id": manifest.get("matter_id"),
                     "sha256": manifest["sha256"],
                     "registered_utc": manifest["registered_utc"]})
    return {"schema": SCHEMA, "documents": docs}


# --------------------------------------------------------------------------
# 桥分发（legal_entry proofing.* 唯一入口；fail-closed 同基线）
# --------------------------------------------------------------------------

def proofing_call(method: str, args: dict, config: dict) -> dict:
    # 规则集回读＝纯策略读（author.policy 同例），先于状态根闸。
    if method == "proofing.ruleset_read":
        try:
            return ruleset_read()
        except ProofingError:
            raise
        except Exception as exc:
            raise _fail("f143_failed:" + type(exc).__name__) from None
    state_root = config.get("proofing_state_root")
    if not state_root:
        raise _fail("f143_state_root_not_configured")

    def _document_id() -> str:
        document_id = args.get("document_id")
        if not isinstance(document_id, str) \
                or not _DOC_ID_RE.match(document_id):
            raise _fail("f143_document_id_invalid")
        return document_id

    try:
        if method == "proofing.register":
            return register(Path(state_root), args.get("document_id"),
                            args.get("matter_id"), args.get("bytesB64"))
        if method == "proofing.scan":
            return scan(Path(state_root), _document_id())
        if method == "proofing.candidates":
            return candidates(Path(state_root), _document_id())
        if method == "proofing.decide":
            return decide(Path(state_root), _document_id(),
                          args.get("candidate_id"), args.get("action"),
                          args.get("actor_id"))
        if method == "proofing.propose":
            return propose(Path(state_root), _document_id())
        if method == "proofing.proposal_read":
            return proposal_read(Path(state_root), _document_id())
        if method == "proofing.read_document":
            return read_document(Path(state_root), _document_id())
        if method == "proofing.list":
            return list_documents(Path(state_root))
        raise _fail("f143_method_unknown")
    except ProofingError:
        raise
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise _fail("f143_failed:" + type(exc).__name__) from None
