# -*- coding: utf-8 -*-
"""F89 数字三分类豁免产品面（工单 W2b-U04）。

06 行 F89 acceptance：事实金额/规则数/否定语义正确分类，不把 LLM 分类叫
确定性；金额由 JC，歧义待核，错误算式反例拒绝；保原三分类豁免结构，
歧义必须待核。

三分类（闭集，V7-89 原类名→工程名）：
  - fact_amount        当事人事实数→事实金额（货币/利率携带值）
  - rule_number        法律规则数（条文号/诉讼时效期数）
  - negative_semantics 否定数→否定/比较辖域内的有极性数
  - unknown            歧义待核（不伪填不猜；pending_review=True）

豁免结构（保原三分类豁免）：三类各自豁免朴素「数字须与来源事实一致」
交叉核对，但各绑定自己的核验纪律——
  - fact_amount        → jc_amount_evaluation（金额值必须经 JC 公开求值）
  - rule_number        → rule_borne（规则携带，不与事实核对）
  - negative_semantics → polarity_bounded（极性承载，不作正向断言）
  - unknown            → pending_review（无豁免，必须待核）

确定性纪律（LegalTech 红线 1）：分类＝正则＋状态机，零模型/零网络/零
随机；classify_document 是纯函数（只吃 text），同输入字节级同输出。
金额解析产品侧一律 Decimal（float 输入一律拒收），跨界以定点十进制
字符串传递；金额值经 JC 公开求值（P01 jc.evaluate → jc-harness-local/1
business task，JC 侧 Fraction 精确）。错误算式反例＝JC 求值余额与文书
主张余额不等 → MISMATCH 具名拒绝（连同两侧精确值与差值），绝不静默。

歧义待核（fail-closed）：无确定性线索/混形态解析不了/日历表达式/裸
百分数/裸期限 → unknown＋具名 reason；事实金额解析不出值 → 类可定但
value=None＋pending_review（JC 求值前必须人工钉值）。
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction

SCHEMA = "juscite-f89-number-classification/1"
AMOUNT_SCHEMA = "juscite-f89-amount-verification/1"

CLASS_FACT_AMOUNT = "fact_amount"
CLASS_RULE_NUMBER = "rule_number"
CLASS_NEGATIVE = "negative_semantics"
CLASS_UNKNOWN = "unknown"

# 三分类豁免结构（冻结：类→豁免纪律）
EXEMPTIONS = {
    CLASS_FACT_AMOUNT: {"fact_crosscheck": "exempt",
                        "discipline": "jc_amount_evaluation"},
    CLASS_RULE_NUMBER: {"fact_crosscheck": "exempt",
                        "discipline": "rule_borne"},
    CLASS_NEGATIVE: {"fact_crosscheck": "exempt",
                     "discipline": "polarity_bounded"},
    CLASS_UNKNOWN: {"fact_crosscheck": None,
                    "discipline": "pending_review"},
}

DETERMINISM = "regex-state-machine"


class NumberFaceError(ValueError):
    """Typed F89 face failure; str() is a code, never material content."""


def _fail(code: str) -> NumberFaceError:
    return NumberFaceError(code)


# --------------------------------------------------------------------- #
# 确定性数字解析（正则＋状态机；零模型参与）
# --------------------------------------------------------------------- #

# 中文数字字符（小写＋大写两套；两套不得混用）
_CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
             "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
             "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5, "陆": 6,
             "柒": 7, "捌": 8, "玖": 9}
_CN_UNIT = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000}
_CN_SMALL = frozenset("零〇一二三四五六七八九十百千万亿两")
_CN_CAPITAL = frozenset("零〇壹贰叁肆伍陆柒捌玖拾佰仟万亿")
_CN_CLASS = frozenset(_CN_DIGIT) | frozenset(_CN_UNIT) | {"万", "亿"}


def parse_cn_numeral(text: str) -> int | None:
    """中文数字→整数（节式状态机：万/亿分段；小写/大写不得混用）。

    不认识的形态返回 None（不猜）。裸「万/亿」不是数。
    """
    if not text or text in ("万", "亿"):
        return None
    chars = set(text)
    if not chars <= _CN_SMALL and not chars <= _CN_CAPITAL:
        return None  # 小写/大写混用＝不可解析
    total = 0
    section = 0
    current = 0
    for ch in text:
        if ch in _CN_DIGIT:
            current = current * 10 + _CN_DIGIT[ch]
        elif ch in _CN_UNIT:
            if current == 0:
                current = 1  # 「十」「拾」起首＝隐式一
            section += current * _CN_UNIT[ch]
            current = 0
        else:  # 万/亿 分段
            section += current
            current = 0
            if ch == "亿":
                total = (total + section) * 10 ** 8
            else:
                total += section * 10 ** 4
            section = 0
    return total + section + current


# 数字体（NUM）：阿拉伯（千位逗号）＋万亿乘号＋（混形态吞并的中文尾），
# 或中文数字串。混形态（阿拉伯＋中文数字混写）只在值解析处判 None。
_CN_CLASS_SRC = "".join(sorted(_CN_CLASS))
_ARITH_SRC = r"\d+(?:,\d+)*(?:\.\d+)?"
_NUM = ("(?:" + _ARITH_SRC + "[万亿]*[" + _CN_CLASS_SRC + "]*"
        "|[" + _CN_CLASS_SRC + "]+)")

# 货币后缀（长前先）与货币前缀
_CURRENCY_SUFFIX = ("美元|欧元|日元|港元|港币|英镑|卢布|法郎|元整|万元|元|圆")
_CURRENCY_PREFIX = "人民币|￥|¥"
_CURRENCY_CODE = {"美元": "USD", "欧元": "EUR", "日元": "JPY", "港元": "HKD",
                  "港币": "HKD", "英镑": "GBP", "卢布": "RUB", "法郎": "FRF",
                  "元整": "CNY", "万元": "CNY", "元": "CNY", "圆": "CNY"}
_CURRENCY_SUFFIX_LIST = ("美元", "欧元", "日元", "港元", "港币", "英镑",
                         "卢布", "法郎", "元整", "万元", "元", "圆")

# 期限后缀（个月先于月；日/天同义）
_DURATION_SUFFIX = "个月|月|日|天|年|周"
_DURATION_LIST = ("个月", "月", "日", "天", "年", "周")

# 否定/比较辖域线索（闭集；cue→极性）。辖域内的数＝否定语义类，极性随
# 记（不作正向断言）。间隔 ≤ _NEG_GAP 字符且同子句、中间无别的数字体。
_NEG_CUES = {
    "不超过": "upper_bound", "不得超": "upper_bound", "不能超": "upper_bound",
    "不应超": "upper_bound", "不可超": "upper_bound", "未超过": "upper_bound",
    "未超出": "upper_bound", "不高于": "upper_bound", "不大于": "upper_bound",
    "不多于": "upper_bound", "至多": "upper_bound", "最多": "upper_bound",
    "上限": "upper_bound",
    "不少于": "lower_bound", "不低于": "lower_bound", "不小于": "lower_bound",
    "至少": "lower_bound", "最少": "lower_bound", "下限": "lower_bound",
    "不足": "below", "不满": "below", "未满": "below", "未足": "below",
    "未达": "below", "低于": "below", "少于": "below",
    "超过": "above", "超出": "above", "高于": "above", "多于": "above",
    "大于": "above",
}
# 后缀界线线索（数/单位后紧跟）：X以上＝≥，X以下/X以内＝≤
_BOUND_SUFFIX = {"以上": "lower_bound", "以下": "upper_bound",
                 "以内": "upper_bound"}
_NEG_GAP = 6
_NOUN_GAP = 2
_CLAUSE_BREAK = "。；！？\n\r;"

# 金融名词（名词后数字＝事实金额；单位未声明则 unit=None 如实空缺）
_FIN_NOUNS = ("本金", "利息", "违约金", "罚息", "滞纳金", "欠款", "货款",
              "租金", "价款", "赔偿金", "诉讼费", "律师费", "代理费",
              "定金", "押金", "保证金", "工资", "报酬", "金额", "标的额")
_RATE_WORDS = ("利率", "费率")
_PRESCRIPTION_WORDS = ("时效",)

# 主扫描（alternation 顺序即同位优先级：条文＞百分之＞百分号＞期限＞
# 货币（含前缀）＞裸数（含前缀））
_MASTER_RE = re.compile(
    "第" + _NUM + "条(?:之" + _NUM + ")?"
    + "|第" + _NUM + "[款项]"
    + "|百分之" + _NUM
    + "|" + _NUM + r"\s*[%％]"
    + "|" + _NUM + "(?:" + _DURATION_SUFFIX + ")"
    + "|(?:" + _CURRENCY_PREFIX + ")?" + _NUM + "(?:" + _CURRENCY_SUFFIX + ")"
    + "|(?:" + _CURRENCY_PREFIX + ")?" + _NUM)

_DATE_RE = re.compile(r"\d{1,4}年(?:\d{1,2}月)?(?:\d{1,2}日)?")
_ARITH_RE = re.compile(_ARITH_SRC)
_NUMBER_TOKEN_RE = re.compile(_NUM)
_NUMERAL_CHAR = frozenset(_CN_DIGIT) | frozenset(_CN_UNIT) | {"万", "亿"}


def _plain(value: Decimal) -> str:
    """Decimal→定点十进制字符串（无指数；产品侧展示/回显唯一形态）。"""
    return format(value.normalize(), "f")


def _rational_wire(value: Decimal) -> str:
    """Decimal→JC 规范有理数串（``n`` 或 ``n/d``；codec.exact_rational 对
    恰此形态收货；十进制值永远精确可表）。"""
    return str(Fraction(value))


def _fraction_to_plain(value: Fraction) -> str:
    """Fraction→定点十进制串（分母 2^a·5^b 时精确；否则如实回规范有理数
    串——十进制入参下不会走到，走到也不丢精度不猜）。"""
    denominator = value.denominator
    residual = denominator
    for factor in (2, 5):
        while residual % factor == 0:
            residual //= factor
    if residual == 1:
        digits = len(str(abs(value.numerator))) + 64
        with localcontext() as context:
            context.prec = digits
            return _plain(Decimal(value.numerator) / Decimal(denominator))
    return str(value)


def _number_value(token: str) -> Decimal | None:
    """数字体→Decimal；混形态（阿拉伯＋中文数字混写）＝None 不猜。"""
    match = re.match("(" + _ARITH_SRC + ")([万亿]*)(.*)$", token)
    if match:
        arabic, mult, rest = match.groups()
        if rest:  # 阿拉伯体后跟中文数字＝混形态
            return None
        return _parse_arabic(arabic + mult)
    return _parse_chinese_value(token)


def _parse_arabic(text: str) -> Decimal | None:
    """阿拉伯体（可带千位逗号/万亿乘号）→Decimal；逗号不成组＝None。"""
    body = text
    multiplier = Decimal(1)
    while body and body[-1] in "万亿":
        multiplier *= Decimal(10 ** 8) if body[-1] == "亿" else Decimal(10 ** 4)
        body = body[:-1]
    if "," in body:
        head, *groups = body.split(",")
        if not groups or len(head) > 3 or any(len(g) != 3 for g in groups):
            return None  # 千位逗号不成组＝不可解析（不猜）
    try:
        return Decimal(body.replace(",", "")) * multiplier
    except InvalidOperation:
        return None


def _parse_chinese_value(text: str) -> Decimal | None:
    value = parse_cn_numeral(text)
    return None if value is None else Decimal(value)


def _clause_bounds(text: str, position: int) -> tuple[int, int]:
    start = max(text.rfind(ch, 0, position) for ch in _CLAUSE_BREAK) + 1
    ends = [text.find(ch, position) for ch in _CLAUSE_BREAK]
    ends = [e for e in ends if e != -1]
    return start, (min(ends) if ends else len(text))


def _find_neg_cue(text: str, start: int) -> tuple[str, str] | None:
    """数首 start 的否定/比较辖域线索（同子句、cue 尾与数首间隔 ≤
    _NEG_GAP、间隔内无其他数字体——线索归最近的数）。

    返回 (cue, polarity) 或 None。
    """
    clause_start, _ = _clause_bounds(text, start)
    for cue in sorted(_NEG_CUES, key=len, reverse=True):
        window_start = max(clause_start, start - _NEG_GAP - len(cue))
        pos = text.rfind(cue, window_start, start)
        if pos < 0:
            continue
        gap = text[pos + len(cue):start]
        if len(gap) > _NEG_GAP:
            continue
        if any(ch in _NUMERAL_CHAR or ch.isdigit() for ch in gap):
            return None  # 线索已被更近的数消费
        return cue, _NEG_CUES[cue]
    return None


def _bound_suffix(text: str, end: int) -> tuple[str, str] | None:
    """数尾紧随的界线后缀（以上/以下/以内）。返回 (suffix, polarity)。"""
    suffix = text[end:end + 2]
    if suffix in _BOUND_SUFFIX:
        return suffix, _BOUND_SUFFIX[suffix]
    return None


def _fin_noun_cue(text: str, start: int, clause_start: int) -> str | None:
    """金融名词紧邻数首（间隔 ≤ _NOUN_GAP）。返回命中的名词或 None。"""
    for noun in _FIN_NOUNS:
        window_start = max(clause_start, start - _NOUN_GAP - len(noun))
        if text.find(noun, window_start, start) >= 0:
            gap_end = text.rfind(noun, window_start, start) + len(noun)
            if start - gap_end <= _NOUN_GAP:
                return noun
    return None


def _extract_number(raw: str) -> tuple[str, Decimal | None]:
    """命中原文→（数字体, 值）。剥第/百分之/货币前缀后取首个数字体。"""
    body = raw
    for prefix in ("第", "百分之", "人民币", "￥", "¥"):
        if body.startswith(prefix):
            body = body[len(prefix):]
            break
    token_match = _NUMBER_TOKEN_RE.match(body)
    token = token_match.group(0) if token_match else body
    return token, _number_value(token)


def _extract_form(raw: str) -> str:
    """命中形态（由命中文本的确定性结构判定，非语义猜测）。"""
    if raw.startswith("第") and ("条" in raw or "款" in raw or "项" in raw):
        return "article" if "条" in raw else "article_subref"
    if raw.startswith("百分之") or raw.endswith(("%", "％")):
        return "percent"
    tail = raw.rstrip("%％")
    if tail.endswith(_DURATION_LIST):
        return "duration"
    if tail.endswith(_CURRENCY_SUFFIX_LIST) or \
            raw.startswith(("人民币", "￥", "¥")):
        return "money"
    return "raw"


def _unit_of(form: str, raw: str) -> str | None:
    tail = raw.rstrip("%％")
    for suffix in _CURRENCY_SUFFIX_LIST:
        if tail.endswith(suffix):
            return _CURRENCY_CODE[suffix]
    if raw.startswith("百分之") or raw.endswith(("%", "％")):
        return "percent"
    if raw.startswith(("人民币", "￥", "¥")):
        return "CNY"
    for suffix in _DURATION_LIST:
        if tail.endswith(suffix):
            return {"个月": "月", "月": "月", "日": "日", "天": "日",
                    "年": "年", "周": "周"}[suffix]
    return None


def _classify_mention(text: str, span: tuple[int, int], raw: str,
                      date_spans: list[tuple[int, int]]) -> dict:
    start, end = span
    number_text, value = _extract_number(raw)
    form = _extract_form(raw)
    clause_start, clause_end = _clause_bounds(text, start)
    clause = text[clause_start:clause_end]
    polarity = None
    reason = None

    if form in ("article", "article_subref"):
        klass, cue = CLASS_RULE_NUMBER, "article"
    else:
        neg = _find_neg_cue(text, start)
        bound = _bound_suffix(text, end)
        noun = None
        if form != "money":
            noun = _fin_noun_cue(text, start, clause_start)
        if neg is not None:
            klass, cue = CLASS_NEGATIVE, "negation:" + neg[0]
            polarity = neg[1]
        elif bound is not None:
            klass, cue = CLASS_NEGATIVE, "bound_suffix:" + bound[0]
            polarity = bound[1]
        elif form == "money" or noun is not None:
            klass, cue = CLASS_FACT_AMOUNT, ("currency" if form == "money"
                                             else "fin_noun:" + noun)
        elif form == "percent" and any(w in clause for w in _RATE_WORDS):
            klass, cue = CLASS_FACT_AMOUNT, "rate"
        elif form == "duration" and any(w in clause
                                        for w in _PRESCRIPTION_WORDS):
            klass, cue = CLASS_RULE_NUMBER, "prescription_period"
        elif any(ds[0] <= start < ds[1] for ds in date_spans):
            klass, cue, reason = CLASS_UNKNOWN, "calendar", "calendar_expression"
        elif form == "duration":
            klass, cue, reason = CLASS_UNKNOWN, None, "bare_duration"
        elif form == "percent":
            klass, cue, reason = CLASS_UNKNOWN, None, "bare_percent"
        elif value is None:
            klass, cue, reason = CLASS_UNKNOWN, None, "value_unparseable"
        else:
            klass, cue, reason = CLASS_UNKNOWN, None, "bare_number"

    pending = klass == CLASS_UNKNOWN
    if klass == CLASS_FACT_AMOUNT and value is None:
        pending = True  # 类可定但值不可解析：JC 求值前必须人工钉值
        reason = reason or "amount_value_unparseable"
    mention = {
        "span": [start, end],
        "text": raw,
        "number_text": number_text,
        "form": form,
        "class": klass,
        "cue": cue,
        "polarity": polarity,
        "value": None if value is None else _plain(value),
        "unit": _unit_of(form, raw),
        "exemption": EXEMPTIONS[klass],
        "pending_review": pending,
    }
    if reason:
        mention["reason"] = reason
    return mention


def classify_document(text: str) -> dict:
    """F89 三分类（纯函数：只吃 text；正则＋状态机；零模型零网络零随机）。

    每个 number mention 一条记录：类/线索/极性/值（Decimal 定点字符串）
    /单位/豁免结构；歧义→unknown＋具名 reason＋pending_review。
    """
    if not isinstance(text, str):
        raise _fail("classify_text_invalid")
    date_spans = [m.span() for m in _DATE_RE.finditer(text)]
    mentions = [_classify_mention(text, m.span(), m.group(0), date_spans)
                for m in _MASTER_RE.finditer(text)]
    counts = {CLASS_FACT_AMOUNT: 0, CLASS_RULE_NUMBER: 0,
              CLASS_NEGATIVE: 0, CLASS_UNKNOWN: 0}
    for mention in mentions:
        counts[mention["class"]] += 1
    return {
        "schema": SCHEMA,
        "determinism": DETERMINISM,
        "model_involved": False,
        "counts": dict(counts, total=len(mentions)),
        "pending_review": any(m["pending_review"] for m in mentions),
        "mentions": mentions,
    }


# --------------------------------------------------------------------- #
# 金额经 JC 公开求值（P01 jc.evaluate → jc-harness-local/1）
# --------------------------------------------------------------------- #

JC_CONTRACT = "jc-harness-local/1"
JC_ENTRY = "P01 jc.evaluate"
_RECOGNITION_ATOM = "payment_recognized"
_DATE_ANCHOR = "2000-01-01"   # 余额＝本金−已认定付款与日期无关（结构性）；
                              # 未传日期时的固定合成锚，响应内回显不隐藏。


def parse_amount_text(value, field: str) -> str:
    """金额入参→定点十进制字符串（产品侧 Decimal 全程；float 一律拒收）。"""
    if isinstance(value, bool) or value is None:
        raise _fail("amount_invalid:" + field)
    if isinstance(value, float):
        raise _fail("amount_float_rejected:" + field)
    if isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value.strip())
        except InvalidOperation:
            raise _fail("amount_unparseable:" + field) from None
    else:
        raise _fail("amount_invalid:" + field)
    if not decimal_value.is_finite() or decimal_value < 0:
        raise _fail("amount_invalid:" + field)
    return _plain(decimal_value)


def canonical_date(value, field: str) -> str:
    """YYYY-MM-DD（JC 契约日期串；畸形＝具名拒绝）。"""
    if value is None:
        return _DATE_ANCHOR
    if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", value):
        raise _fail("date_invalid:" + field)
    return value


def build_amount_task(*, principal: str, payments: list[dict],
                      as_of: str, due_day: str) -> dict:
    """合成 business task（确定性单世界：全部付款认定）。

    纯函数：只依赖入参；金额一律转 JC 规范有理数串（Decimal→Fraction
    精确，无浮点）；selection_ref/sources 由入参规范形 sha256 派生（同
    入参同 task 字节）。日期仅承载（余额与日期无关）。
    """
    rational_principal = _rational_wire(Decimal(principal))
    rational_payments = [
        {"payment_id": p["payment_id"],
         "amount": _rational_wire(Decimal(p["amount"])),
         "event_day": p.get("event_day") or due_day}
        for p in payments]
    canonical = json.dumps(
        {"principal": rational_principal,
         "payments": [{"payment_id": p["payment_id"], "amount": p["amount"]}
                      for p in rational_payments]},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    selection_ref = "sha256:" + hashlib.sha256(
        canonical.encode("utf-8")).hexdigest()
    body = "SYNTHETIC F89 amount verification: principal %s; payments %s." % (
        rational_principal,
        "; ".join("%s=%s" % (p["payment_id"], p["amount"])
                  for p in rational_payments))
    spec = {
        "relation_id": "f89-amount-verification",
        "creditor": "SYN-Creditor", "debtor": "SYN-Debtor",
        "debt_id": "DEBT-F89", "principal": rational_principal,
        "due_day": due_day, "asof_day": as_of,
        "sources": [{"source_id": "F89-SYNTHETIC", "version": "1",
                     "body": body, "start": 0, "end": len(body),
                     "quoted": body}],
        "payments": [{
            "payment_id": p["payment_id"], "amount": p["amount"],
            "event_day": p["event_day"],
            "payer": "SYN-Debtor", "recipient": "SYN-Creditor",
            "debt_id": "DEBT-F89", "recognition_atom": _RECOGNITION_ATOM,
            "source_id": "F89-SYNTHETIC"} for p in rational_payments],
        "facts": [{"atom": _RECOGNITION_ATOM, "observed": True}],
        "constraint": {"op": "true", "atom": "", "children": []},
        "approved_policy": "SYNTHETIC-CONDITIONAL-PRINCIPAL/1",
    }
    context = {
        "request": "SYNTHETIC-F89-AMOUNT-VERIFY", "jurisdiction": "TEST",
        "event_time": due_day, "decision_time": as_of,
        "procedure": "conditional_analysis", "stage": "analysis",
        "party": "claimant", "issue": "principal-balance",
        "scenario": "finite-conditional-completions", "profile": "grounded",
        "law_version": "source-snapshot-example",
        "interpretation": "explicit-reference", "rulepack_version": "test-1",
        "engine_version": "reference-2.1", "model_version": "synthetic-model-1",
        "evidence_version": "test-evidence-1",
        "target": "f89_amount_balance_verification",
        "semantic_scope": "height_bounded",
        "assumptions": ["synthetic F89 amount verification"],
        "max_depth": 2,
    }
    return {
        "task_id": "f89-amount-verify", "issue_id": "principal-balance",
        "requirement_id": "SYNTHETIC_EXACT_PRINCIPAL_ANALYTICS_TWO_FILES/1",
        "profile": "SYNTHETIC-CONDITIONAL-PRINCIPAL/1",
        "selection_ref": selection_ref,
        "input": {
            "context": context, "spec": spec,
            "model": {
                "weights": [{"world": {"atoms": [
                    {"atom": _RECOGNITION_ATOM, "value": True}]},
                    "probability": "1"}],
                "threshold": "0", "costs": ["0", "0", "0", "0"],
                "legal_options": [], "basis": "SYNTHETIC-SETTLEMENT-GRID/1",
            },
            "solve_budget": None,
        },
    }


def amount_verdict(result: dict, *, claimed: str, principal: str,
                   payments: list[dict], as_of: str, due_day: str,
                   date_anchor_used: bool) -> dict:
    """JC 求值结果×文书主张余额 → 裁决（错误算式反例＝MISMATCH 具名拒绝）。"""
    rows = result.get("business_results") or []
    if not rows:
        raise _fail("jc_business_row_missing")
    row = rows[0]
    if row.get("completion") != "exact_finite_scenarios":
        raise _fail("jc_completion:" + str(row.get("completion")
                                           or row.get("error_code")))
    analytics = row.get("analytics") or {}
    jc_balance = analytics.get("expected_balance")
    if not isinstance(jc_balance, str):
        raise _fail("jc_balance_missing")
    jc_value = Fraction(jc_balance)              # JC 规范有理数串（精确）
    claimed_value = Fraction(Decimal(claimed))   # 产品侧 Decimal（精确）
    delta = jc_value - claimed_value
    payments_total = sum((Fraction(Decimal(p["amount"]))
                          for p in payments), Fraction(0))
    return {
        "schema": AMOUNT_SCHEMA,
        "verdict": "CONSISTENT" if delta == 0 else "MISMATCH",
        "claimed_balance": claimed,
        "jc_balance": _fraction_to_plain(jc_value),
        "delta_jc_minus_claimed": _fraction_to_plain(delta),
        "amounts": {
            "principal": principal,
            "payments": [{"payment_id": p["payment_id"],
                          "amount": p["amount"]} for p in payments],
            "payments_total": _fraction_to_plain(payments_total),
        },
        "dates": {"as_of": as_of, "due_day": due_day,
                  "date_anchor": "fixed-synthetic" if date_anchor_used
                  else "caller-provided"},
        "arithmetic": {
            "engine": "jc.evaluate(jc-harness-local/1; fraction-exact)",
            "product_side": "decimal-exact",
            "float_used": False,
        },
        "jc": {
            "contract": JC_CONTRACT, "entry": JC_ENTRY,
            "completion": row.get("completion"),
            "execution_mode": result.get("execution_mode"),
            "signature_status": result.get("signature_status"),
            "run_identity_ref": result.get("run_identity_ref"),
            "input_ref": row.get("input_ref"),
            "outcomes": row.get("outcomes"),
        },
    }
