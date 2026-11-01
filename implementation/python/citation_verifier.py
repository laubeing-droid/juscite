# -*- coding: utf-8 -*-
"""F70 引证核验器产品面（工单 W2a-U14）。

单条核验＋全文引用逐条范围记账。引用解析＝确定性正则＋状态机（工作区
约束 1：案号/法条/文档分块用正则、状态机等确定性解析，严禁模型猜测）；
版本/效力/时点一律经 W2a-U13 的 statute_validity（其法源消费经 E22
冻结面 lccc_consumer v1.0/v1.1）；标题→WJBS 定位经冻结面 v1.1 追加的
find_by_title（精确匹配，无模糊/别名猜测）；真实取文走冻结面
read_markdown_text，按真实 md 正文做条款定位与引文支持核验。

17 卡步骤落地：本地优先→时点/效力/版本（statute.citation_gate）→真实
取文定位（md 正文条款切分状态机）→支持核验（引文必须真出现在定位条款
正文）→引用回读（support.article_text 回读定位原文）。

记账纪律（06 行 F70 acceptance）：
  - 每引用独立状态：现行/已修订/已废止/替代/虚构/失效/误引（fail-closed
    时=未知）；一条一记，scope 字段写明本条到底核到了什么；
  - 虚构/失效/误引绝不标全核（verified_scoped 恒 False）；
  - 无文档级 PASS 笼统结论：verify_document 只出逐条记录＋状态计数，
    不产任何「全文通过」字段；
  - 本地面未命中≠全局不存在：虚构状态同时携带降级链缺口声明（付费/web
    未执行段），不据此断言外部一定没有。

Fail-closed：缺 as_of/多版本不可定/状态冲突/窗口不可定→未知，不签现行
（继承 F69 纪律：被废除检索到也不许引）。
"""

from __future__ import annotations

import os
import re
import sys

from bridge_errors import NotConnected
import statute_validity

# ---------------------------------------------------------------------- #
# 状态词汇（06 行 F70 acceptance 的七状态＋fail-closed 未知）
# ---------------------------------------------------------------------- #

STATUS_CURRENT = "现行"
STATUS_AMENDED = "已修订"
STATUS_ABOLISHED = "已废止"
STATUS_SUPERSEDED = "替代"
STATUS_FABRICATED = "虚构"
STATUS_EXPIRED = "失效"
STATUS_MISCITED = "误引"
STATUS_UNKNOWN = "未知"

# 绝不能标全核的三态（06 行：虚构/失效/误引不能标全核）
NEVER_FULLY_VERIFIED = (STATUS_FABRICATED, STATUS_EXPIRED, STATUS_MISCITED)

LOCAL_FACE_NAME = "lccc_consumer(E22 freeze v1.1/find_by_title)"

# ---------------------------------------------------------------------- #
# 确定性引用解析（正则＋状态机；无模型参与）
# ---------------------------------------------------------------------- #

# 中文法定数字（条款号用）：零一二三四五六七八九＋单位十百千
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def parse_cn_numeral(text: str) -> int | None:
    """中文法定数字→整数（确定性状态机；不认识返回 None 不猜）。"""
    if not text:
        return None
    total = 0          # 已结算的高段
    current = 0        # 当前段累积
    saw_digit = False
    for ch in text:
        if ch in _CN_DIGITS:
            current = current * 10 + _CN_DIGITS[ch]
            saw_digit = True
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            if not saw_digit or current == 0:
                current = 1  # 「十」「百」起首＝隐式一（十五条/百条）
            total += current * unit
            current = 0
            saw_digit = False
        else:
            return None
    return total + current if text else None


_NUMERAL = r"[零一二三四五六七八九十百千]+"
# 条文引用：第N条（可带 之一/之二…）；不匹配汉字数字以外的形态
_ARTICLE_RE = re.compile(
    r"第(?P<num>" + _NUMERAL + r")条(?:之(?P<sub>" + _NUMERAL + r"))?")
# 款/项跟随（可选，按原文保留不解读语义，仅记引用定位粒度）
_SUBREF_RE = re.compile(
    r"第(?:[一二三四五六七八九十百千零]+|[0-9]+)[款项]")
# 引文（支持核验对象）：成对中文/直角/西文引号
_QUOTE_OPEN = {"\u201c": "\u201d", "「": "」", "\u300c": "\u300d", '"': '"'}
# 状态机句边界（引用与其引文须同句）
_SENTENCE_END = "。；\n\r"
_TITLE_RE = re.compile(r"《(?P<title>[^《》\n]{1,120})》")


def _strip_decorations(text: str) -> str:
    """确定性装饰剥离：全角空格/空白/markdown 强调与列表符。
    仅删承载层装饰字符，不改动任何标点与文字（不做模糊规范化）。"""
    cleaned = []
    for ch in text:
        if ch in ("*", "-", " ", "\u3000", "\t", ">", "#"):
            continue
        cleaned.append(ch)
    return "".join(cleaned)


def split_articles(markdown_text: str) -> dict:
    """真实 md 正文→{条文号: 条文文本} 状态机切分。

    承载层格式（真实 md 实测）：条文起点=行首 `- **第N条**` 或裸
    `第N条`；条文延续=后续缩进/子列表行，直到下一条文起点或章节标题。
    frontmatter（--- 块）先剥掉。切分失败返回空 dict（不猜）。
    """
    if not markdown_text:
        return {}
    lines = markdown_text.splitlines()
    # 剥 frontmatter
    start = 0
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                start = idx + 1
                break
    article_start = re.compile(r"^(?:-\s*)?\*{0,2}第(" + _NUMERAL +
                               r")条(?:之(" + _NUMERAL + r"))?\*{0,2}")
    heading = re.compile(r"^#{1,6}\s")
    articles: dict = {}
    order: list = []
    current_key = None
    current_lines: list = []
    for line in lines[start:]:
        stripped = line.strip()
        match = article_start.match(stripped) if stripped else None
        if match:
            num = parse_cn_numeral(match.group(1))
            if num is None:
                continue  # 不认识的数字形态：跳过该行，不猜
            if current_key is not None:
                articles[current_key] = "\n".join(current_lines)
            current_key = match.group(0)
            key_num = str(num) + ("之" + match.group(2) if match.group(2) else "")
            current_lines = [line]
            order.append((current_key, key_num, num,
                          match.group(2)))
        elif current_key is not None:
            if heading.match(stripped):
                articles[current_key] = "\n".join(current_lines)
                current_key = None
                current_lines = []
            else:
                current_lines.append(line)
    if current_key is not None:
        articles[current_key] = "\n".join(current_lines)
    # 以「条文号」为键重建（保留原文键与行文本）
    result: dict = {}
    for _marker, key_num, num, sub in order:
        text = articles.get(_marker, "")
        result[key_num] = {"number": num, "sub": sub or "",
                           "text": text}
    return result


def _scan_citation_segment(text: str, start: int):
    """从书名号结尾向后扫引用段（状态机，引号感知）。

    返回 (segment_end, quote)：segment_end＝本引用段结束位置——首个
    「不在引号内」的句号/分号/换行，或下一个书名号《（新引用开始），或
    文末；quote＝段内第一段成对引号文本（引号内的句号不算句界——引文
    含句号是法定文本常态）。段内引号未闭合＝引文不完整，quote 记 None
    不猜。
    """
    in_quote = None
    quote = None
    quote_start = -1
    i = start
    length = len(text)
    while i < length:
        ch = text[i]
        if in_quote is not None:
            if ch == in_quote:
                if quote is None:
                    quote = text[quote_start + 1:i]
                in_quote = None
        elif ch in _QUOTE_OPEN:
            in_quote = _QUOTE_OPEN[ch]
            if quote_start < 0:
                quote_start = i
        elif ch in _SENTENCE_END or ch == "《":
            return i, quote
        i += 1
    return length, quote


def parse_citations(text: str) -> list:
    """全文确定性引用抽取（状态机：书名号→条文→引文须同段）。

    每条产出：{span, citation_text, title, article_ref, article_number,
    article_sub, subrefs, quote}。span 相对输入文本偏移；同段多条文
    （《A》第一条、第三条）各自成条，引文只归首个条文；无条文的书名号
    引用也成条（条文字段 None，核验停在标题/版本级）。引用段以「不在
    引号内的句界」或下一书名号为界——引文内的句号不断段。
    """
    if not isinstance(text, str) or not text:
        return []
    results: list = []
    for title_match in _TITLE_RE.finditer(text):
        title = title_match.group("title")
        seg_end, quote = _scan_citation_segment(text, title_match.end())
        tail = text[title_match.end():seg_end]
        article_matches = list(_ARTICLE_RE.finditer(tail))
        if not article_matches:
            results.append({
                "span": [title_match.start(), title_match.end()],
                "citation_text": title_match.group(0),
                "title": title,
                "article_ref": None, "article_number": None,
                "article_sub": None, "subrefs": [],
                "quote": quote,
            })
            continue
        cursor = 0
        for art in article_matches:
            ref_text = art.group(0)
            num = parse_cn_numeral(art.group("num"))
            if num is None:
                continue
            # 款/项跟随（紧邻条文之后）
            subref_text = ""
            probe = art.end()
            while True:
                sub = _SUBREF_RE.match(tail, probe)
                if not sub:
                    break
                subref_text += sub.group(0)
                probe = sub.end()
            art_abs_start = title_match.end() + art.start()
            art_abs_end = title_match.end() + probe
            results.append({
                "span": [title_match.start(), art_abs_end],
                "citation_text": title_match.group(0) + tail[art.start():probe],
                "title": title,
                "article_ref": ref_text,
                "article_number": num,
                "article_sub": art.group("sub"),
                "subrefs": subref_text,
                # 引文归属段内首个条文；多条文段后续条文不带引文
                "quote": quote if cursor == 0 else None,
            })
            cursor += 1
    results.sort(key=lambda item: item["span"][0])
    return results


# ---------------------------------------------------------------------- #
# 消费面装配（与 statute_validity 同纪律：经冻结面，不绕面）
# ---------------------------------------------------------------------- #

# 面模块按路径加载并缓存在本模块（唯一模块名隔离：同进程内其他消费方
# 可能已把 v1.0 面载入 sys.modules['lccc_consumer']——本面须用 v1.1 的
# find_by_title，按配置路径独立加载不共用、不受污染；进程内同路径只载一次）
_FACE_MODULE_CACHE: dict = {}
_FACE_MODULE_NAME = "lccc_consumer_f70_face_v1_1"


def _consumer(config: dict):
    """经 E22 冻结面 v1.1 取 LcccConsumer（按路径加载，具名 fail-closed）。

    面文件=配置 codices_import_path 下的 lccc_consumer.py；缺 find_by_title
    （v1.0 旧面）＝面过旧具名拒绝，不静默降级。
    """
    import importlib.util
    import_path = config.get("codices_import_path")
    formal_root = config.get("codices_formal_root")
    if not import_path:
        raise NotConnected("codices_import_path_not_configured")
    if not formal_root:
        raise NotConnected("codices_formal_root_not_configured")
    key = os.path.normpath(os.path.abspath(import_path))
    module = _FACE_MODULE_CACHE.get(key)
    if module is None:
        face_file = os.path.join(import_path, "lccc_consumer.py")
        if not os.path.isfile(face_file):
            raise NotConnected(
                "lccc_consumer_not_in_import_path:" + str(import_path))
        spec = importlib.util.spec_from_file_location(
            _FACE_MODULE_NAME, face_file)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise NotConnected(
                "lccc_consumer_not_importable:" + type(exc).__name__) from None
        if not hasattr(getattr(module, "LcccConsumer", None),
                       "find_by_title"):
            raise NotConnected(
                "lccc_consumer_face_too_old:find_by_title_missing_v1_1")
        _FACE_MODULE_CACHE[key] = module
    try:
        return module.LcccConsumer(formal_root)
    except FileNotFoundError as exc:
        raise NotConnected("lccc_formal_face_incomplete:" + str(exc)) from None


# ---------------------------------------------------------------------- #
# 单条核验
# ---------------------------------------------------------------------- #


def _resolve_version(consumer, config: dict, title: str, as_of: str) -> dict:
    """标题→唯一版本行（确定性规则，fail-closed）。

    1) find_by_title 精确匹配；0 行=本面未命中（虚构·本地段）；
    2) 逐候选过 statute.citation_gate(as_of)：恰一 ALLOWED→即所引版本；
    3) 无 ALLOWED：取 SXRQ<=as_of 的最新一版（施行时点在 as_of 前的最
       近版本）；并列/全无→未知（版本不可定，不猜）。
    返回 {rows, chosen, gate, ambiguous}。
    """
    rows = consumer.find_by_title(title)
    if not rows:
        return {"rows": [], "chosen": None, "gate": None, "ambiguous": False}
    if len(rows) == 1:
        # 单版本标题无可言歧义：唯一行即所引版本（时点判定交引证闸）
        chosen_wjbs = rows[0]["wjbs"]
        return {"rows": rows, "chosen": chosen_wjbs,
                "gate": statute_validity.citation_gate(
                    config, {"wjbs": chosen_wjbs, "as_of": as_of}),
                "ambiguous": False}
    gates = {}
    for row in rows:
        gates[row["wjbs"]] = statute_validity.citation_gate(
            config, {"wjbs": row["wjbs"], "as_of": as_of})
    allowed = [w for w, g in gates.items() if g.get("decision") == "ALLOWED"]
    if len(allowed) == 1:
        chosen_wjbs = allowed[0]
    elif len(allowed) > 1:
        return {"rows": rows, "chosen": None, "gate": None, "ambiguous": True}
    else:
        eligible = [r for r in rows if r["sxrq"] and r["sxrq"] <= as_of]
        if not eligible:
            return {"rows": rows, "chosen": None, "gate": None,
                    "ambiguous": True}
        latest = max(eligible, key=lambda r: r["sxrq"])["sxrq"]
        tied = [r for r in eligible if r["sxrq"] == latest]
        if len(tied) != 1:
            return {"rows": rows, "chosen": None, "gate": None,
                    "ambiguous": True}
        chosen_wjbs = tied[0]["wjbs"]
    return {"rows": rows, "chosen": chosen_wjbs,
            "gate": gates[chosen_wjbs], "ambiguous": False,
            "gates": gates}


def _newer_same_title_exists(rows: list, chosen_wjbs: str) -> bool:
    """同名更新版本在库（确定性：同标题行中存在 SXRQ 更晚者）。"""
    chosen = next((r for r in rows if r["wjbs"] == chosen_wjbs), None)
    if chosen is None or not chosen.get("sxrq"):
        return False
    return any(r["wjbs"] != chosen_wjbs and r.get("sxrq")
               and r["sxrq"] > chosen["sxrq"] for r in rows)


def _status_from_gate(gate: dict, newer_exists: bool) -> str:
    if gate.get("decision") == "ALLOWED":
        return STATUS_CURRENT
    code = gate.get("code", "")
    label = gate.get("status_label")
    if code == "ABOLISHED_NOT_CITABLE":
        return STATUS_SUPERSEDED if newer_exists else STATUS_ABOLISHED
    if code == "SUPERSEDED_NOT_CITABLE":
        if newer_exists:
            return STATUS_SUPERSEDED
        if label == "已修改":
            return STATUS_AMENDED
        return STATUS_EXPIRED  # 已失效（SUPERSEDED_LABELS 其余）
    # NOT_YET_IN_FORCE / UNKNOWN 各分支：fail-closed 未知，不签任何现行
    return STATUS_UNKNOWN


def _support_check(consumer, config: dict, parsed: dict,
                   wjbs: str | None, gate: dict | None) -> dict:
    """真实取文定位＋支持核验＋引用回读。

    定位失败/无 md 载体→article_located=False（不猜正文）；不可引版本
    不做引文支持判定（status 不依赖它），但定位事实仍如实回读。
    """
    support = {
        "article_located": False,
        "article_text": None,
        "quote_in_article": None,
        "quote_in_document": None,
        "text_carrier": None,
    }
    if wjbs is None:
        return support
    markdown_text = None
    entry = consumer.document_markdown(wjbs)
    if entry is not None:
        markdown_text = consumer.read_markdown_text(wjbs)
        support["text_carrier"] = entry.get("path")
    if markdown_text is None:
        return support
    articles = split_articles(markdown_text)
    normalized_doc = _strip_decorations(markdown_text)
    if parsed.get("article_number") is None:
        # 无条文引用：文档级载体在位即回读，定位停在标题级
        support["article_located"] = False
        support["document_text_present"] = True
        return support
    key = str(parsed["article_number"]) + (
        "之" + parsed["article_sub"] if parsed.get("article_sub") else "")
    article = articles.get(key)
    if article is None:
        support["quote_in_document"] = None
        return support
    support["article_located"] = True
    support["article_text"] = article["text"].strip()
    if not parsed.get("quote"):
        return support
    normalized_article = _strip_decorations(article["text"])
    normalized_quote = _strip_decorations(parsed["quote"])
    support["quote_in_article"] = normalized_quote in normalized_article
    support["quote_in_document"] = normalized_quote in normalized_doc
    return support


def verify_citation(parsed: dict, config: dict, consumer=None) -> dict:
    """单条引用核验（17 卡全步骤）。返回逐条范围记账记录。"""
    as_of = parsed.get("as_of")
    if as_of is None:
        raise NotConnected("citation_as_of_required_fail_closed")
    if not isinstance(as_of, str) or not re.match(r"^\d{8}$", as_of):
        raise NotConnected("citation_as_of_must_be_yyyymmdd")
    if consumer is None:
        consumer = _consumer(config)
    title = parsed.get("title")
    if not isinstance(title, str) or not title:
        raise NotConnected("citation_title_required")

    record = {
        "citation_text": parsed.get("citation_text"),
        "title": title,
        "article_ref": parsed.get("article_ref"),
        "article_number": parsed.get("article_number"),
        "quote": parsed.get("quote"),
        "identifier": None,
        "status": STATUS_UNKNOWN,
        "decision": None,
        "code": None,
        "reasons": [],
        "scope": [],
        "verified_scoped": False,
        "support": None,
        "replacement": None,
        "replacement_reason": "",
        "degradation": None,
    }

    resolution = _resolve_version(consumer, config, title, as_of)
    rows = resolution["rows"]
    if not rows:
        # 本地面未命中：虚构（本地段）；付费/web 缺口具名声明，不判全局
        strategy = statute_validity.source_strategy(config)
        record["status"] = STATUS_FABRICATED
        record["code"] = "LOCAL_FACE_TITLE_MISS"
        record["reasons"] = [
            "本地面标题精确匹配未命中（%s）" % LOCAL_FACE_NAME,
            "本地未命中≠全局不存在；付费/web 段为声明缺口（F64-v1.5/B4），"
            "不据此自采、不编造",
        ]
        record["degradation"] = strategy["segments"]["paid"]["gap"]
        record["scope"] = ["title_lookup:local_exact_miss"]
        record["verified_scoped"] = False
        return record

    if resolution["ambiguous"]:
        record["code"] = "VERSION_UNRESOLVED_FAIL_CLOSED"
        record["reasons"] = ["多版本且无可引版本/施行时点不可定——不猜版本"]
        record["scope"] = ["title_lookup:hit", "version_resolution:ambiguous"]
        record["verified_scoped"] = False
        return record

    wjbs = resolution["chosen"]
    gate = resolution["gate"]
    record["identifier"] = wjbs
    record["decision"] = gate.get("decision")
    record["code"] = gate.get("code")
    record["reasons"] = list(gate.get("reasons") or [])
    record["replacement"] = gate.get("replacement")
    record["replacement_reason"] = gate.get("replacement_reason", "")

    newer = _newer_same_title_exists(rows, wjbs)
    status = _status_from_gate(gate, newer)
    support = _support_check(consumer, config, parsed, wjbs, gate)

    # 支持核验只在可引（现行）版本上判定误引；其余状态如实记定位事实
    if status == STATUS_CURRENT:
        scope = ["title_lookup:hit", "version:resolved",
                 "effect:%s" % gate.get("code")]
        if parsed.get("article_number") is not None:
            if not support["article_located"]:
                status = STATUS_MISCITED
                record["code"] = "ARTICLE_NOT_IN_REAL_TEXT"
                record["reasons"].append(
                    "真实取文定位失败：正文无此条文号（或无 md 载体）——"
                    "引用条文不存在于真实文本，判误引")
            elif parsed.get("quote"):
                if support["quote_in_article"]:
                    scope.append("quote:supported_in_located_article")
                else:
                    status = STATUS_MISCITED
                    record["code"] = ("QUOTE_MISATTRIBUTED"
                                      if support["quote_in_document"]
                                      else "QUOTE_NOT_IN_REAL_TEXT")
                    record["reasons"].append(
                        "引文不在所引条文真实正文中"
                        + ("（存在于文中他处=张冠李戴）"
                           if support["quote_in_document"]
                           else "（全文亦无=伪引文）"))
        record["scope"] = scope
    else:
        record["scope"] = ["title_lookup:hit", "version:resolved",
                           "effect:%s" % gate.get("code"),
                           "support_check:not_applicable_non_citable"]

    record["status"] = status
    record["support"] = support
    record["verified_scoped"] = (
        status == STATUS_CURRENT
        and (parsed.get("article_number") is None
             or support["article_located"])
        and (not parsed.get("quote")
             or support["quote_in_article"] is True)
    )
    return record


# ---------------------------------------------------------------------- #
# 全文逐条范围记账
# ---------------------------------------------------------------------- #


def verify_document(text: str, as_of: str, config: dict) -> dict:
    """全文所有引用逐条范围记账。无文档级 PASS 笼统结论。

    返回 {citations: [逐条记录…], summary: {total, by_status, …}}；
    summary 只做计数与缺口声明，不产「全文通过/全文核验」语义字段。
    """
    if not isinstance(text, str) or not text:
        raise NotConnected("citation_document_text_required")
    if not isinstance(as_of, str) or not re.match(r"^\d{8}$", as_of):
        raise NotConnected("citation_as_of_must_be_yyyymmdd")
    consumer = _consumer(config)
    parsed_items = parse_citations(text)
    records = []
    for index, parsed in enumerate(parsed_items):
        parsed = dict(parsed)
        parsed["as_of"] = as_of
        record = verify_citation(parsed, config, consumer=consumer)
        record["index"] = index
        record["span"] = parsed["span"]
        records.append(record)
    by_status: dict = {}
    for record in records:
        by_status[record["status"]] = by_status.get(record["status"], 0) + 1
    summary = {
        "total": len(records),
        "by_status": by_status,
        "not_fully_verifiable_statuses": list(NEVER_FULLY_VERIFIED),
        "accounting": "per_citation_scoped",
        "note": "逐条范围记账——无文档级 PASS 笼统结论；虚构/失效/误引"
                "任一在册即该条不标全核，文档级核验结论不存在",
        "local_face": LOCAL_FACE_NAME,
        "source_strategy": statute_validity.source_strategy(config)["chain"],
    }
    return {"citations": records, "summary": summary}


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（citation.*）
# ---------------------------------------------------------------------- #


def citation_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发（citation.*）。未列方法绝不落到这里。"""
    if method == "citation.parse":
        text = args.get("text")
        return {"citations": parse_citations(text)}
    if method == "citation.verify":
        citation = args.get("citation")
        if not isinstance(citation, str) or not citation.strip():
            raise NotConnected("citation_text_required")
        parsed_items = parse_citations(citation)
        if len(parsed_items) != 1:
            raise NotConnected(
                "citation_exactly_one_expected_got:%d" % len(parsed_items))
        parsed = dict(parsed_items[0])
        parsed["as_of"] = args.get("as_of")
        return verify_citation(parsed, config)
    if method == "citation.verify_document":
        return verify_document(args.get("text"), args.get("as_of"), config)
    raise NotConnected("citation_method_not_in_frozen_list:" + method)
