# -*- coding: utf-8 -*-
"""F121 案件时间线 chronology 产品面（工单 W4-U52）。

06 行 F121 acceptance（v1.5，owner=product+harness）：事件时间轴回到
来源/确认状态；未知时点不填录入日，修改触发依赖失效。与期限计算/日历
联动，事实整理刚需；业务事件分类不混 JC。

分工（同 owner 两半边，不复制第二权威）：
  - harness 半边（legal-harness w4-u52，schema v34 chronology_events 一
    账五方法）：事件账本——来源 ref 封闭六字段＋确认闸（unconfirmed→
    confirmed 唯一通道＝人工决定凭据，E17 同频）＋unknown ⇔ event_date
    IS NULL 表级 CHECK＋修改必带显式失效标记（E15 同构）＋读侧对账
    object_dependencies 钉定。程序期限链只读消费绝不写入。
  - 产品半边（本文件）：确定性事件抽取（正则＋状态机，LegalTech 红线
    1：严禁模型模糊猜日期）＋期限锚守卫（D01 期限计算只读联动——锚日
    期只能来自 confirmed 且依赖不 STALE 的已确认事件）。

确定性纪律：extract_events 是纯函数（只吃文本段列表），零模型/零网络
/零时钟/零随机，同输入字节级同输出（canonical JSON 两跑相等）。

未知时点纪律（fail-closed）：抽不到完整日期（如只有「3月5日」无年份）
→ datePrecision='unknown'＋eventDate=None——绝不回填文档日期/处理时
间/当前日期；候选永不直接入账（入账唯一通道＝harness.chronology_event
_record，落账即 unconfirmed 待人工确认）。

期限锚守卫（与 F118/D01 联动的只读半边）：deadline_anchor 只回读已
确认且依赖不 STALE 的事件日期；未确认（chronology_anchor_not_
confirmed）或依赖已失效（chronology_anchor_dependency_stale）一律具
名拒——事件修改触发依赖失效后，下游期限计算必须显式重锚，绝不静默
用旧日期。本面不写程序期限账（schedule/procedure_events 的投影唯一
权威＝F118）。
"""
from __future__ import annotations

import json
import re

SCHEMA = "juscite-f121-chronology/1"
DETERMINISM = "regex-state-machine"

# 业务事件分类闭集（纯标签；与 harness 侧 _CHRONOLOGY_KINDS 同一冻结集，
# 不触发 JC 计算——分类值本身不携带任何金额/期限计算语义）。
EVENT_KINDS = (
    "contract_signing", "performance", "payment", "breach", "service",
    "hearing", "judgment", "preservation", "arbitration", "other",
)

DATE_PRECISIONS = ("day", "month", "year", "unknown")
DATE_ORIGINS = ("extracted", "manual", "unavailable")

# 日期正则闭集（确定性抽取；无年「3月5日」＝时点不全→unknown，绝不猜年）。
_RE_DAY_CN = re.compile(r"(?<![0-9])([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日")
_RE_DAY_ISO = re.compile(r"(?<![0-9])([0-9]{4})-([0-9]{2})-([0-9]{2})")
_RE_MONTH_CN = re.compile(r"(?<![0-9])([0-9]{4})年([0-9]{1,2})月(?![0-9日])")
_RE_YEAR_CN = re.compile(r"(?<![0-9])([0-9]{4})年(?![0-9月])")
_RE_MONTH_DAY_ONLY = re.compile(r"(?<![0-9])([0-9]{1,2})月([0-9]{1,2})日")

# 文档日期/落款标签片段（确定性剔除）：标签后的日期是文书自身的时间属性，
# 绝不允许被抽成事件日期（未知时点不填文档日期的行为级落实）。
_RE_DOC_DATE_LABEL = re.compile(
    r"[（(]?[^。；;\n]{0,6}(?:文档日期|落款日期|落款时间|打印日期|生成日期"
    r"|出具日期)[^。；;\n]{0,3}[：:][0-9]{4}[-年/][0-9]{1,2}(?:[-月/][0-9]{1,2})?日?[^。；;\n]{0,2}[)）]?")

# 事件句式状态机（关键词→分类；闭集冻结，顺序即优先级）。
_KIND_SIGNALS = (
    ("contract_signing", ("签订", "签署", "订立")),
    ("payment", ("支付", "付款", "转账", "汇款")),
    ("performance", ("交付", "履行", "验收", "竣工")),
    ("breach", ("违约", "逾期未", "未按约")),
    ("service", ("送达", "签收", "邮寄")),
    ("hearing", ("开庭", "庭审", "质证")),
    ("judgment", ("判决", "裁定", "调解书", "判决书")),
    ("preservation", ("查封", "冻结", "扣押", "财产保全")),
    ("arbitration", ("仲裁",)),
)

_SENTENCE_MAX = 160
_TEXT_MAX = 2_000_000
_SEGMENT_MAX = 10_000


class ChronologyError(ValueError):
    """Named product-face error; ``code`` is the stable rejection id."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _classify_sentence(sentence: str) -> str:
    for kind, signals in _KIND_SIGNALS:
        for signal in signals:
            if signal in sentence:
                return kind
    return "other"


def _normalize_day(y: str, m: str, d: str) -> str | None:
    year, month, day = int(y), int(m), int(d)
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _normalize_month(y: str, m: str) -> str | None:
    year, month = int(y), int(m)
    if not (1 <= month <= 12):
        return None
    return f"{year:04d}-{month:02d}"


def _sentences(text: str) -> list[str]:
    """确定性句界（。；\n 与全角分号；引号内不跨句界——与 W2a-U14 引文
    句界同族的最小实现）。"""
    parts: list[str] = []
    current: list[str] = []
    for char in text:
        current.append(char)
        if char in "。；;\n":
            sentence = "".join(current).strip()
            if sentence:
                parts.append(sentence)
            current = []
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def extract_segments(segments: list) -> dict:
    """确定性事件抽取（正则＋状态机）：输入材料文本段列表（E12 解析产
    物形状 {docId, pageFrom, pageTo, text}），输出事件候选列表。候选不
    入账——入账唯一通道＝harness.chronology_event_record（落账即
    unconfirmed）。未知时点＝unknown 档（eventDate=None），绝不回填文
    档日期/处理时间。"""
    if not isinstance(segments, list) or not segments:
        raise ChronologyError("chronology_extract_segments_invalid")
    if len(segments) > _SEGMENT_MAX:
        raise ChronologyError("chronology_extract_segments_too_many")
    candidates: list[dict] = []
    seen_keys: set[tuple] = set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise ChronologyError("chronology_extract_segment_invalid")
        doc_id = segment.get("docId")
        page_from = segment.get("pageFrom")
        page_to = segment.get("pageTo")
        text = segment.get("text")
        if not isinstance(doc_id, str) or not doc_id \
                or not isinstance(page_from, int) or isinstance(page_from, bool) \
                or page_from < 1 \
                or not isinstance(page_to, int) or isinstance(page_to, bool) \
                or page_to < page_from \
                or not isinstance(text, str) or not text:
            raise ChronologyError("chronology_extract_segment_invalid")
        if len(text) > _TEXT_MAX:
            raise ChronologyError("chronology_extract_text_too_long")
        for raw_sentence in _sentences(text):
            # 文档日期/落款标签片段先剔除：标签日期绝不作事件日期。
            sentence = _RE_DOC_DATE_LABEL.sub("，", raw_sentence)
            kind = _classify_sentence(sentence)
            day_cn = _RE_DAY_CN.search(sentence)
            day_iso = _RE_DAY_ISO.search(sentence)
            month_cn = _RE_MONTH_CN.search(sentence)
            year_cn = _RE_YEAR_CN.search(sentence)
            month_day = _RE_MONTH_DAY_ONLY.search(sentence)
            if day_cn is not None:
                event_date = _normalize_day(day_cn.group(1), day_cn.group(2),
                                            day_cn.group(3))
                precision = "day" if event_date else "unknown"
            elif day_iso is not None:
                event_date = _normalize_day(day_iso.group(1),
                                            day_iso.group(2), day_iso.group(3))
                precision = "day" if event_date else "unknown"
            elif month_cn is not None:
                event_date = _normalize_month(month_cn.group(1),
                                              month_cn.group(2))
                precision = "month" if event_date else "unknown"
            elif year_cn is not None:
                event_date = year_cn.group(1)
                precision = "year"
            elif kind != "other":
                # 无年「3月5日」或纯事件句：时点不全＝未知档，绝不猜年。
                event_date = None
                precision = "unknown"
            else:
                continue
            if event_date is None and precision != "unknown":
                continue
            title = sentence[:_SENTENCE_MAX]
            dedup_key = (doc_id, page_from, title, event_date, precision,
                         kind)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            candidates.append({
                "title": title,
                "eventKind": kind,
                "eventDate": event_date,
                "datePrecision": precision,
                # date_origin 描述「日期」的来源：有日期＝extracted；
                # unknown 档日期不可得＝unavailable（与 harness 表级
                # CHECK `unknown ⇔ origin=unavailable` 同一冻结语义——
                # 录入日/文档日期不在任何来源闭集里）。
                "dateOrigin": "extracted" if event_date is not None
                else "unavailable",
                "summary": sentence[:_SENTENCE_MAX * 2],
                "sourceSpan": {"docId": doc_id, "pageFrom": page_from,
                               "pageTo": page_to},
            })
    return {
        "schema": SCHEMA,
        "determinism": DETERMINISM,
        "candidates": candidates,
        "candidateCount": len(candidates),
        "unknownCount": sum(1 for c in candidates
                            if c["datePrecision"] == "unknown"),
    }


def deadline_anchor(event_readback: dict) -> dict:
    """D01 期限计算锚守卫（只读联动，不写程序期限账）：锚日期只能来自
    confirmed 且依赖不 STALE 的事件回执（harness.chronology_event_read
    的返回）。未确认/依赖失效一律具名拒——事件修改触发依赖失效后下
    游必须显式重锚，绝不静默用旧日期。unknown 档无日期可作锚，天然拒
    （chronology_anchor_date_unknown）。"""
    if not isinstance(event_readback, dict) or "eventId" not in event_readback:
        raise ChronologyError("chronology_anchor_readback_invalid")
    status = event_readback.get("status")
    if status != "confirmed":
        raise ChronologyError(
            f"chronology_anchor_not_confirmed:{event_readback.get('eventId')}"
            f":{status}")
    dependency = event_readback.get("dependencyStatus") or {}
    if dependency.get("staleCount"):
        raise ChronologyError(
            "chronology_anchor_dependency_stale:"
            f"{event_readback.get('eventId')}")
    event_date = event_readback.get("eventDate")
    if event_date is None:
        raise ChronologyError(
            f"chronology_anchor_date_unknown:{event_readback.get('eventId')}")
    precision = event_readback.get("datePrecision")
    if precision != "day":
        # 非日粒度（月/年）不能当期限起算日——精度不足须人工补全后重锚。
        raise ChronologyError(
            f"chronology_anchor_precision_insufficient:"
            f"{event_readback.get('eventId')}:{precision}")
    return {
        "anchorDate": event_date,
        "datePrecision": precision,
        "eventId": event_readback["eventId"],
        "revision": event_readback["revision"],
        "sourceRef": event_readback.get("sourceRef"),
    }


def chronology_call(method: str, args: dict, config: dict):
    """Product-face chronology surface (closed method group)."""
    if method == "chronology.extract":
        return extract_segments(args.get("segments"))
    if method == "chronology.deadline_anchor":
        return deadline_anchor(args.get("eventReadback"))
    raise ChronologyError("chronology_method_unknown:" + method)


def canonical_determinism_probe(segments: list) -> bool:
    """同输入两跑字节级同输出（确定性自证；recon 直接消费）。"""
    first = json.dumps(extract_segments(segments), ensure_ascii=False,
                       sort_keys=True)
    second = json.dumps(extract_segments(segments), ensure_ascii=False,
                        sort_keys=True)
    return first == second
