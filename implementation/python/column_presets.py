# -*- coding: utf-8 -*-
"""F83 合同列预设产品面（工单 W3-U15）。

06 F83（17 卡，owner=product；UI_HOST_OR_NEW_PRODUCT）：列预设（合同审查
10+ 列模板）；acceptance 断言「合同列预设字段与 format 严格分离；每列金
标、缺值/多值/未知不伪填」。本模块是**冻结预设＋申报编排**，不是第二列
权威、不是第二核验器：

  - 列权威＝F82 列合同（harness.review_columns_*，W2b-U05 VERIFIED）：
    建批冻结列集合＋金标一次性入账都在 harness；本面只把冻结预设按合同
    申报进既有批（review_columns_define），列集合不冻结/异内容冲突等
    具名拒不复制不代判；
  - 字段与 format 严格分离（结构性，不是约定）：预设的**字段层**闭集
    {id,name,gold}——字段层携带 format 键即具名拒（字段定义里没有
    format 的位置）；**format 层**闭集 {id,format} 独立成表；两层 id 集合
    必须恰等，只在申报边界 join 成 harness 列合同形状
    {id,name,format,version,gold}。冻结预设经 _validate_preset 在每次
    read/apply/values 前复验（防漂移，响亮失败）；
  - 每列金标：12 列每列必有 gold（kind 闭集与 tabular_review/harness
    同集）；本面不解释值语义，金标对照（goldMatch）唯一在 tabular.read；
  - 缺值/多值/未知不伪填：column_preset.values 是填充投影——每个候选
    列恰好 0 个提及＝缺值、≥2 个互异提及＝多值、number 金标列的单提及
    不可 Decimal 解析＝未知；三种形态值恒 None＋具名 fill 理由，绝不编
    造占位值（金额 Decimal/整分纪律：不可解析的金额串不落格）。

金额纪律：number 金标列的可填性判定用 Decimal（十进制串，不落浮点，
同 tabular_review number 金标对照语义）。

状态面：零自有持久化——预设是冻结代码事实，填充投影是纯函数，申报
落在 harness 列合同账（W2b-U05）。原生 UI 触发面不在本单（公开面先行，
同 F54/F45 先例）。
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from bridge_errors import NotConnected

COLUMN_PRESET_FACE_NOTE = (
    "column-preset(W3-U15): harness.review_columns_*(W2b-U05)申报；"
    "字段/format 严格分离；每列金标；缺值/多值/未知不伪填")

# 方法组闭集（legal_entry 冻结注册；组外方法绝不落到本面）。
COLUMN_PRESET_METHODS = frozenset({
    "column_preset.read", "column_preset.apply", "column_preset.values",
})

# 金标 kind 闭集（与 harness REVIEW_GOLD_KINDS／产品 tabular_review 同集
# ——wiring 测试钉定相等，防三处漂移）。
GOLD_KINDS = frozenset({
    "text", "enum", "number", "date", "boolean", "none",
})

# ---------------------------------------------------------------------- #
# 冻结预设：字段层（{id,name,gold}）与 format 层（{id,format}）严格分离
# ---------------------------------------------------------------------- #

FIELDS = (
    {"id": "parties", "name": "合同主体",
     "gold": {"kind": "text"}},
    {"id": "contract_amount", "name": "合同金额（元）",
     "gold": {"kind": "number"}},
    {"id": "payment_term", "name": "付款期限",
     "gold": {"kind": "text"}},
    {"id": "performance_date", "name": "履行期限",
     "gold": {"kind": "date"}},
    {"id": "contract_term", "name": "合同期限",
     "gold": {"kind": "text"}},
    {"id": "liability_breach", "name": "违约责任",
     "gold": {"kind": "text"}},
    {"id": "penalty_standard", "name": "违约金标准",
     "gold": {"kind": "number"}},
    {"id": "dispute_resolution", "name": "争议解决方式",
     "gold": {"kind": "enum", "expect": ["诉讼", "仲裁"]}},
    {"id": "governing_law", "name": "适用法律",
     "gold": {"kind": "text"}},
    {"id": "effectiveness", "name": "生效条件",
     "gold": {"kind": "text"}},
    {"id": "legal_basis", "name": "法律依据（引文）",
     "gold": {"kind": "text"}},
    {"id": "risk_level", "name": "审查风险等级",
     "gold": {"kind": "enum", "expect": ["高", "中", "低"]}},
)

FORMATS = (
    {"id": "parties", "format": "text"},
    {"id": "contract_amount", "format": "decimal-string"},
    {"id": "payment_term", "format": "text"},
    {"id": "performance_date", "format": "iso-date"},
    {"id": "contract_term", "format": "text"},
    {"id": "liability_breach", "format": "text"},
    {"id": "penalty_standard", "format": "decimal-string"},
    {"id": "dispute_resolution", "format": "text"},
    {"id": "governing_law", "format": "text"},
    {"id": "effectiveness", "format": "text"},
    {"id": "legal_basis", "format": "text"},
    {"id": "risk_level", "format": "text"},
)

PRESET_ID = "contract-review"
PRESET_VERSION = "1"

# 填充投影 fill 闭集（缺值/多值/未知不伪填的具名形态）。
FILL_FILLED = "filled"
FILL_MISSING = "value_missing"
FILL_AMBIGUOUS = "value_ambiguous"
FILL_UNKNOWN = "value_unknown"
FILL_CLOSED = frozenset({
    FILL_FILLED, FILL_MISSING, FILL_AMBIGUOUS, FILL_UNKNOWN,
})

_READ_ARGS_FIELDS = frozenset(set())
_APPLY_ARGS_FIELDS = frozenset({
    "scope", "review_batch_id", "actor_id", "key",
})
_VALUES_ARGS_FIELDS = frozenset({"values"})

# number 金标列可填性判定的确定性数字抽取（与 tabular_review number 金标
# 对照同语义：中文合同文本中的金额串——千位逗号＋小数；Decimal 比对，
# 不落浮点；不可解析＝未知，不落格）。
_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _harness_call(method: str, args: dict, config: dict) -> dict:
    """harness 公开面分派 seam（默认=legal_entry.call 子进程径；selfhost
    侧 PG 直连部署由调用方替换本 seam——同 tabular_review 先例）。"""
    import legal_entry
    return legal_entry.call(method, args, config)


def _require(args: dict, fields: frozenset, code: str) -> None:
    """DTO 闭集校验：必带字段缺一即拒、闭集外字段即拒（无旁路）。"""
    if not isinstance(args, dict) or set(args) != set(fields):
        raise NotConnected(code)


def _scope_of(args: dict) -> dict:
    scope = args.get("scope")
    if not isinstance(scope, dict) or scope.get("kind") != "matter" \
            or not isinstance(scope.get("matterId"), str) \
            or not scope.get("matterId"):
        raise NotConnected("column_preset_scope_invalid")
    return scope


def _command_key(args: dict) -> dict:
    key = args.get("key")
    if not isinstance(key, dict) or not isinstance(key.get("requestId"), str) \
            or not key.get("requestId"):
        raise NotConnected("column_preset_command_key_invalid")
    return key


def _validate_field(field, offset: int) -> dict:
    """字段层闭集：{id,name,gold}——字段定义携带 format 键＝严格分离被
    破坏，具名拒（preset_field_carries_format:<id>）。gold 必在（每列
    金标），kind 闭集。"""
    if not isinstance(field, dict):
        raise NotConnected("column_preset_field_invalid:%d" % offset)
    if set(field) != {"id", "name", "gold"}:
        if "format" in field:
            raise NotConnected(
                "preset_field_carries_format:%s"
                % field.get("id", "?"))
        raise NotConnected("column_preset_field_shape_invalid:%d" % offset)
    if not isinstance(field["id"], str) or not field["id"]:
        raise NotConnected("column_preset_field_id_invalid:%d" % offset)
    if not isinstance(field["name"], str) or not field["name"]:
        raise NotConnected("column_preset_field_name_invalid:%d" % offset)
    gold = field["gold"]
    if not isinstance(gold, dict) or gold.get("kind") not in GOLD_KINDS:
        raise NotConnected("column_preset_gold_required:%s" % field["id"])
    return field


def _validate_format(item, offset: int) -> dict:
    """format 层闭集：{id,format}——format 表携带 gold/name＝越层，具名拒。"""
    if not isinstance(item, dict) or set(item) != {"id", "format"}:
        raise NotConnected("column_preset_format_shape_invalid:%d" % offset)
    if not isinstance(item["format"], str) or not item["format"]:
        raise NotConnected("column_preset_format_invalid:%d" % offset)
    return item


def _validate_preset() -> tuple:
    """冻结预设结构复验（read/apply/values 前置，防漂移响亮失败）：
    字段层/format 层各自闭集＋两层 id 集合恰等＋无重复 id。"""
    ids = []
    for offset, field in enumerate(FIELDS):
        _validate_field(field, offset)
        ids.append(field["id"])
    if len(set(ids)) != len(ids):
        raise NotConnected("column_preset_field_duplicate")
    format_ids = []
    for offset, item in enumerate(FORMATS):
        _validate_format(item, offset)
        format_ids.append(item["id"])
    if len(set(format_ids)) != len(format_ids):
        raise NotConnected("column_preset_format_duplicate")
    if set(ids) != set(format_ids):
        raise NotConnected(
            "preset_format_id_mismatch:fields=%s:formats=%s"
            % (",".join(sorted(set(ids) - set(format_ids))),
               ",".join(sorted(set(format_ids) - set(ids)))))
    return tuple(FIELDS), tuple(FORMATS)


def _joined_columns() -> list:
    """申报边界 join：字段层×format 层→harness 列合同形状。join 之后
    才同时具备 format 与 gold；字段层本体永不携带 format。"""
    fields, formats = _validate_preset()
    format_by_id = {item["id"]: item["format"] for item in formats}
    return [{
        "id": field["id"], "name": field["name"],
        "format": format_by_id[field["id"]],
        "version": PRESET_VERSION, "gold": dict(field["gold"]),
    } for field in fields]


# ---------------------------------------------------------------------- #
# column_preset.read —— 冻结预设只读回读（两层分离形态原样呈现）
# ---------------------------------------------------------------------- #


def preset_read(args: dict, config: dict) -> dict:
    _require(args, _READ_ARGS_FIELDS, "column_preset_read_args_invalid")
    fields, formats = _validate_preset()
    return {
        "presetId": PRESET_ID,
        "version": PRESET_VERSION,
        "fieldCount": len(fields),
        "fields": [dict(field) for field in fields],
        "formats": [dict(item) for item in formats],
        "separated": True,
        "goldKinds": sorted(GOLD_KINDS),
        "note": "字段层 {id,name,gold} 与 format 层 {id,format} 严格分离"
                "——字段定义无 format 键、format 表无 gold；每列必有金标；"
                "申报时在边界 join 成 harness 列合同形状",
        "face": COLUMN_PRESET_FACE_NOTE,
    }


# ---------------------------------------------------------------------- #
# column_preset.apply —— 冻结预设申报进既有批（列权威在 harness）
# ---------------------------------------------------------------------- #


def preset_apply(args: dict, config: dict) -> dict:
    _require(args, _APPLY_ARGS_FIELDS, "column_preset_apply_args_invalid")
    scope = _scope_of(args)
    _command_key(args)
    actor_id = args.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        raise NotConnected("column_preset_actor_invalid")
    batch_id = args.get("review_batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise NotConnected("column_preset_batch_id_required")
    columns = _joined_columns()
    receipt = _harness_call("harness.review_columns_define", {
        "actor_id": actor_id, "scope": scope, "key": args["key"],
        "batch_id": batch_id, "columns": columns}, config)
    return {
        "presetId": PRESET_ID,
        "presetVersion": PRESET_VERSION,
        "reviewBatchId": batch_id,
        "columnCount": len(columns),
        "harness": receipt,
        "note": "列集合冻结与金标冲突判定唯一在 harness（columns_not_frozen"
                "/review_columns_conflict 具名拒原样上浮）；本面不建第二列"
                "权威",
        "face": COLUMN_PRESET_FACE_NOTE,
    }


# ---------------------------------------------------------------------- #
# column_preset.values —— 填充投影（缺值/多值/未知不伪填）
# ---------------------------------------------------------------------- #


def _value_fillable(gold: dict, mention: str) -> bool:
    """number 金标列：单提及必须可 Decimal 解析（金额纪律——不可解析的
    金额串是未知，不落格）；其余 kind 本面不解释值语义（对照唯一在
    tabular.read goldMatch）。"""
    if gold.get("kind") != "number":
        return True
    found = _NUMBER_RE.search(mention.replace("，", ","))
    if not found:
        return False
    try:
        Decimal(found.group(0).replace(",", ""))
    except InvalidOperation:
        return False
    return True


def preset_values(args: dict, config: dict) -> dict:
    _require(args, _VALUES_ARGS_FIELDS, "column_preset_values_args_invalid")
    fields, _ = _validate_preset()
    gold_by_id = {field["id"]: field["gold"] for field in fields}
    values = args.get("values")
    if not isinstance(values, dict) or not values:
        raise NotConnected("column_preset_values_invalid")
    out = []
    for column_id, mentions in values.items():
        gold = gold_by_id.get(column_id)
        if gold is None:
            raise NotConnected("preset_column_unknown:" + str(column_id))
        if not isinstance(mentions, list) or \
                not all(isinstance(item, str) for item in mentions):
            raise NotConnected("column_preset_mentions_invalid:"
                               + str(column_id))
        distinct = sorted(set(mentions))  # 确定性去重（同文多提非多值）
        if not distinct:
            fill, value, reason = FILL_MISSING, None, "no_mention"
        elif len(distinct) > 1:
            fill, value, reason = FILL_AMBIGUOUS, None, (
                "distinct=%d" % len(distinct))
        elif not _value_fillable(gold, distinct[0]):
            fill, value, reason = FILL_UNKNOWN, None, "number_unparseable"
        else:
            fill, value, reason = FILL_FILLED, distinct[0], None
        if fill not in FILL_CLOSED:
            raise NotConnected("column_preset_fill_closed")
        out.append({
            "columnId": column_id,
            "value": value,
            "fill": fill,
            "reason": reason,
            "mentionCount": len(mentions),
            "distinctCount": len(distinct),
        })
    filled = sum(1 for item in out if item["fill"] == FILL_FILLED)
    return {
        "presetId": PRESET_ID,
        "cells": out,
        "filledCount": filled,
        "unfilledCount": len(out) - filled,
        "note": "缺值/多值/未知恒 value=None＋具名 fill——绝不编造占位值"
                "；同文多提及去重不升格为多值",
        "face": COLUMN_PRESET_FACE_NOTE,
    }


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（column_preset.*）
# ---------------------------------------------------------------------- #


def column_preset_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发（column_preset.*）。未列方法绝不落到
    这里。"""
    if method == "column_preset.read":
        return preset_read(args, config)
    if method == "column_preset.apply":
        return preset_apply(args, config)
    return preset_values(args, config)  # column_preset.values
