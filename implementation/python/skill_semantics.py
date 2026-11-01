# -*- coding: utf-8 -*-
"""F93 SKILL.md 通道三执行语义产品面（W3-U16）。

义务 06:F93（17 卡；F93-desktop/F93-selfhost 双实例）：「SKILL.md 通道+
三种执行语义（聊天注入/实例化 review/调用计算器）」＋台账断言「SKILL聊天
注入/review实例/JC计算三语义真实，禁无必要DAG引擎」＋05 §8「同ID来源、
选中/注入/调用/产物分别证」。

三语义落点（本面＝SKILL 通道的唯一产品执行面；UI 仅调用/展示）：

- skill.read（来源）：确定性解析 SKILL.md——id 规则与上游原生通道一致
  （SKILL.md→父目录名；其余→文件名去 .md），frontmatter 仅取 name/
  description，全文 sha256 入回执（同 ID 产物可溯源）；列模板块与计算
  步骤块只报告存在性与块 sha，不在 read 里实例化。
- skill.review_instantiate（实例化 review）：正文恰一块
  ```lvyin-review-columns 封闭 JSON（列 name/prompt/format/version＋
  金标 kind 结构闭集）→ 经既有冻结方法组 harness.review_batch_create＋
  harness.review_columns_define 真实建批入账（F25/F82 底座，零第二列
  权威）；批标题携带 skill@sha 溯源、note 携带全文 sha256。模板缺失/
  不唯一/字段闭集外一律具名拒。
- skill.calculate（调用计算器，本行独有桥接语义）：正文恰一块
  ```lvyin-calc-step 封闭 JSON（method 冻结具名输入域＋rule/calendar
  版本声明）→ method 必须在真实五族计算器闭集内且与 skill 声明一致 →
  经既有冻结方法组 calc.*（P01 JCClient 同一钉定公开面）真实计算；
  JC typed 拒绝原样上浮（JC_FAILURE 携码 exit 4），绝不造数。
- 禁无必要 DAG 引擎：本面无图/引擎/编排结构（导入闭集 AST 钉定，见
  wiring 测试）——三语义各自一次派发，不做通用 DAG。

fail-closed：typed error（SkillSemanticsError 的 str 只有 f93_* 错误码，
绝不携材料内容）；未配置 harness/jc config＝NotConnected（桥既有码）。
无状态根（纯解析＋既有账面派发）。
"""
from __future__ import annotations

import hashlib
import json
import re

from bridge_errors import NotConnected

SCHEMA = "juscite-f93-skill-semantics/1"

# legal_entry 冻结方法组（唯一入口；组外方法绝不落到本面）。
SKILL_METHODS = frozenset({
    "skill.read",
    "skill.review_instantiate",
    "skill.calculate",
})

# 封闭块标记（fenced 围栏语言标记；正文恰一块——多块＝非确定性解析拒绝）。
TEMPLATE_BLOCK_LANG = "lvyin-review-columns"
CALC_STEP_BLOCK_LANG = "lvyin-calc-step"

# 列格式闭集（05 §8 Tabular 列 name/prompt/format/version；闭集在本面
# 声明，wiring 测试与既有列消费面钉定——格式账面只存字符串）。
COLUMN_FORMATS = frozenset({"text", "decimal-string", "date", "boolean"})

# 计算器方法闭集＝legal_entry calc 真实六族槽位（registry/recon/calendar
# 是治理面不是计算器，不入「调用计算器」组；wiring 测试与 legal_entry
# _CALC_FAMILY_SLOT_BY_METHOD 钉定相等——单一权威在 legal_entry 冻结组；
# W4-U48：calc.damages＝C07 赔偿金 v1.5 首批扩充加入计算器组）。
CALC_SLOT_METHODS = frozenset({
    "calc.interest", "calc.court_fee", "calc.preservation_fee",
    "calc.contingency_fee", "calc.arbitration_fee", "calc.damages",
})

_TEMPLATE_COLUMN_FIELDS = frozenset({
    "id", "name", "prompt", "format", "version", "gold",
})
_TEMPLATE_TOP_FIELDS = frozenset({"columns", "rows"})
_ROW_FIELDS = frozenset({"id"})

_CALC_STEP_FIELDS = frozenset({
    "method", "rule_version", "calendar_version", "input_domain",
})

_FENCE_RE = re.compile(r"^```([A-Za-z0-9-]+)[ \t]*\r?\n(.*?)\r?\n?^```[ \t]*$",
                       re.S | re.M)
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)\Z", re.S)
_FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):[ \t]*(.*)$")


class SkillSemanticsError(ValueError):
    """Typed F93 face failure; str() is a code, never material content."""


def _require(args: dict, fields: frozenset, code: str) -> None:
    """DTO 闭集校验：必带字段缺一即拒、闭集外字段即拒（无旁路）。"""
    if not isinstance(args, dict) or set(args) != set(fields):
        raise NotConnected(code)


def _text(value, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise SkillSemanticsError(code)
    return value


# ---------------------------------------------------------------------- #
# 来源：SKILL.md 确定性解析（id 规则与上游原生通道一致）
# ---------------------------------------------------------------------- #


def _skill_id_of(path: str) -> str:
    from pathlib import Path as _Path
    p = _Path(path)
    if p.name == "SKILL.md":
        return p.parent.name
    return p.stem


def read_skill(path: str) -> dict:
    """来源面：解析一次，全文 sha256＋frontmatter name/description＋两块
    存在性/块 sha。文件缺失/正文空＝具名拒；frontmatter 缺失＝具名拒
    （原生通道对 frontmatter 不合式的文件同样跳过——通道两侧一致）。"""
    from pathlib import Path as _Path
    raw_path = _Path(path)
    try:
        raw = raw_path.read_bytes()
    except OSError:
        raise SkillSemanticsError("f93_skill_file_missing") from None
    if not raw:
        raise SkillSemanticsError("f93_skill_file_empty")
    # 换行归一（CRLF/CR→LF）：fenced 块锚点解析与 read_text 通用换行一致；
    # contentSha256 恒对原始字节计算（归一只用于解析）。
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise SkillSemanticsError("f93_skill_frontmatter_missing")
    name = None
    description = None
    for line in match.group(1).splitlines():
        pair = _FRONTMATTER_LINE_RE.match(line.strip())
        if pair is None:
            continue
        if pair.group(1) == "name" and name is None:
            name = pair.group(2).strip() or None
        elif pair.group(1) == "description" and description is None:
            description = pair.group(2).strip() or None
    body = match.group(2)
    fences = {lang: [block for lang2, block in _FENCE_RE.findall(body)
                     if lang2 == lang]
              for lang in (TEMPLATE_BLOCK_LANG, CALC_STEP_BLOCK_LANG)}
    template_block = fences[TEMPLATE_BLOCK_LANG]
    step_block = fences[CALC_STEP_BLOCK_LANG]
    return {
        "schema": SCHEMA,
        "id": _skill_id_of(path),
        "name": name,
        "description": description,
        "path": str(raw_path),
        "contentSha256": hashlib.sha256(raw).hexdigest(),
        "template": (None if not template_block else {
            "sha256": hashlib.sha256(template_block[0].encode("utf-8")
                                     ).hexdigest(),
        }),
        "calcStep": (None if not step_block else {
            "sha256": hashlib.sha256(step_block[0].encode("utf-8")
                                     ).hexdigest(),
        }),
    }


def _selected_skill(args: dict) -> dict:
    """选中纪律：调用方携带 skill_id，本面按同一 id 规则重推——不一致即拒
    （不得实例化/计算未选中的 skill）。"""
    parsed = read_skill(_text(args.get("skill_path"),
                              "f93_skill_path_invalid"))
    selected = _text(args.get("skill_id"), "f93_skill_id_invalid")
    if parsed["id"] != selected:
        raise SkillSemanticsError(
            "f93_skill_id_mismatch:" + parsed["id"] + "!=" + selected)
    return parsed


# ---------------------------------------------------------------------- #
# 实例化 review：列模板（恰一块）→ 既有 harness 冻结方法组
# ---------------------------------------------------------------------- #


def _blocks_of(body: str, lang: str, missing: str, not_unique: str) -> str:
    blocks = [block for block_lang, block in _FENCE_RE.findall(body)
              if block_lang == lang]
    if not blocks:
        raise SkillSemanticsError(missing)
    if len(blocks) > 1:
        raise SkillSemanticsError(not_unique)
    return blocks[0]


def _template_of(parsed: dict) -> dict:
    raw = _blocks_of(_body_of(parsed), TEMPLATE_BLOCK_LANG,
                     "f93_template_block_missing",
                     "f93_template_block_not_unique")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise SkillSemanticsError("f93_template_json_invalid") from None
    if not isinstance(data, dict) or not set(data) <= _TEMPLATE_TOP_FIELDS \
            or "columns" not in data:
        raise SkillSemanticsError("f93_template_fields_invalid")
    raw_columns = data["columns"]
    if not isinstance(raw_columns, list) or not raw_columns:
        raise SkillSemanticsError("f93_template_columns_invalid")
    columns = []
    seen_ids = set()
    for column in raw_columns:
        if not isinstance(column, dict) \
                or set(column) != _TEMPLATE_COLUMN_FIELDS:
            raise SkillSemanticsError("f93_template_column_fields_invalid")
        column_id = _text(column["id"], "f93_template_column_id_invalid")
        if column_id in seen_ids:
            raise SkillSemanticsError("f93_template_column_duplicate")
        seen_ids.add(column_id)
        name = _text(column["name"], "f93_template_column_name_invalid")
        prompt = _text(column["prompt"], "f93_template_column_prompt_invalid")
        fmt = _text(column["format"], "f93_template_column_format_invalid")
        if fmt not in COLUMN_FORMATS:
            raise SkillSemanticsError("f93_template_format_unknown:" + fmt)
        version = _text(column["version"],
                        "f93_template_column_version_invalid")
        gold = column["gold"]
        if not isinstance(gold, dict) \
                or not isinstance(gold.get("kind"), str) or not gold["kind"]:
            raise SkillSemanticsError("f93_template_gold_invalid")
        columns.append({"id": column_id, "name": name, "prompt": prompt,
                        "format": fmt, "version": version, "gold": gold})
    raw_rows = data.get("rows", [])
    if not isinstance(raw_rows, list) or not raw_rows:
        raise SkillSemanticsError("f93_template_rows_invalid")
    rows = []
    seen_rows = set()
    for row in raw_rows:
        if not isinstance(row, dict) or set(row) != _ROW_FIELDS:
            raise SkillSemanticsError("f93_template_row_fields_invalid")
        row_id = _text(row["id"], "f93_template_row_id_invalid")
        if row_id in seen_rows:
            raise SkillSemanticsError("f93_template_row_duplicate")
        seen_rows.add(row_id)
        rows.append({"id": row_id,
                     "cells": {column["id"]: None for column in columns}})
    return {"columns": columns, "rows": rows, "sha256": hashlib.sha256(
        raw.encode("utf-8")).hexdigest()}


def _body_of(parsed: dict) -> str:
    from pathlib import Path as _Path
    return _Path(parsed["path"]).read_text(encoding="utf-8")


def skill_review_instantiate(args: dict, config: dict) -> dict:
    """语义②：模板 → harness.review_batch_create＋review_columns_define
    （既有冻结方法组；零第二列权威）。标题=「name（id@sha8）」确定性
    溯源；note 携全文 sha256。两笔账共用调用方 CommandKey 根，列账键
    派生「:columns」后缀（同键异内容＝conflict——派生保证两键异内容各
    得其位）。账面错误（批 id 重复/列冲突/键冲突等）沿桥既有
    HarnessCommandError 上浮，不在本面改写。"""
    matter_id = _text(args.get("matter_id"), "f93_matter_id_invalid")
    batch_id = _text(args.get("batch_id"), "f93_batch_id_invalid")
    key = args.get("key")
    if not isinstance(key, dict) or not isinstance(key.get("requestId"), str) \
            or not key["requestId"]:
        raise SkillSemanticsError("f93_command_key_invalid")
    scope = {"kind": "matter", "matterId": matter_id}
    parsed = _selected_skill(args)
    template = _template_of(parsed)
    # 列 prompt＝技能通道指导内容（05 §8「列 name/prompt/format/version」
    # 里的 prompt），harness 列账闭集 {id,name,format,version,gold} 不收
    # prompt——账面列传 {id,name} 与 {id,name,format,version,gold}，prompt
    # 随本面回执携带（UI 仅调用/展示），不塞账本未定义字段。
    batch_columns = [{"id": c["id"], "name": c["name"]}
                     for c in template["columns"]]
    ledger_columns = [{"id": c["id"], "name": c["name"],
                       "format": c["format"], "version": c["version"],
                       "gold": c["gold"]} for c in template["columns"]]
    title = "%s（%s@%s）" % (parsed["name"] or parsed["id"], parsed["id"],
                             parsed["contentSha256"][:8])
    note = "skill=%s sha256=%s templateSha256=%s" % (
        parsed["id"], parsed["contentSha256"], template["sha256"])
    created = _harness_call("harness.review_batch_create", {
        "actor_id": "lvyin-skill", "scope": scope, "key": key,
        "batch": {"id": batch_id, "title": title, "note": note,
                  "columns": batch_columns, "rows": template["rows"]},
    }, config)
    _harness_call("harness.review_columns_define", {
        "actor_id": "lvyin-skill", "scope": scope,
        "key": {**key, "requestId": key["requestId"] + ":columns"},
        "batch_id": batch_id, "columns": ledger_columns,
    }, config)
    return {
        "schema": SCHEMA,
        "semantic": "review_instantiate",
        "skill": {"id": parsed["id"],
                  "contentSha256": parsed["contentSha256"],
                  "templateSha256": template["sha256"]},
        "templateColumns": [{"id": c["id"], "prompt": c["prompt"]}
                            for c in template["columns"]],
        "batchId": batch_id,
        "created": created,
    }


# ---------------------------------------------------------------------- #
# 调用计算器：计算步骤块（恰一块）→ 既有 calc.* 冻结方法组（P01 JCClient）
# ---------------------------------------------------------------------- #


def _calc_step_of(parsed: dict) -> dict:
    raw = _blocks_of(_body_of(parsed), CALC_STEP_BLOCK_LANG,
                     "f93_calc_step_block_missing",
                     "f93_calc_step_block_not_unique")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise SkillSemanticsError("f93_calc_step_json_invalid") from None
    if not isinstance(data, dict) or set(data) != _CALC_STEP_FIELDS:
        raise SkillSemanticsError("f93_calc_step_fields_invalid")
    method = _text(data["method"], "f93_calc_method_invalid")
    if method not in CALC_SLOT_METHODS:
        raise SkillSemanticsError("f93_calc_method_not_in_closed_set:"
                                  + method)
    rule_version = _text(data["rule_version"],
                         "f93_calc_rule_version_invalid")
    calendar_version = _text(data["calendar_version"],
                             "f93_calc_calendar_version_invalid")
    domain = data["input_domain"]
    if not isinstance(domain, list) or not domain \
            or not all(isinstance(key, str) and key for key in domain):
        raise SkillSemanticsError("f93_calc_input_domain_invalid")
    if len(set(domain)) != len(domain):
        raise SkillSemanticsError("f93_calc_input_domain_duplicate")
    return {"method": method, "rule_version": rule_version,
            "calendar_version": calendar_version,
            "input_domain": sorted(domain), "sha256": hashlib.sha256(
                raw.encode("utf-8")).hexdigest()}


def skill_calculate(args: dict, config: dict) -> dict:
    """语义③（本行独有桥接）：skill 声明计算步骤（方法/具名输入域/
    rule·calendar 版本），调用方绑定实值，JC 经既有 calc.* 冻结组真实
    计算。输入键集必须等于声明域（冻结具名输入域——多键/缺键具名拒）；
    JC typed 拒绝（闭集外槽位/浮点/负金额等）原样上浮＝JC_FAILURE 携码
    exit 4，绝不造数。回执携带 JC calculationReceiptRef（owner=jc）与
    独立 checker 结论＝产物面。"""
    _text(args.get("matter_id"), "f93_matter_id_invalid")
    parsed = _selected_skill(args)
    step = _calc_step_of(parsed)
    payload = args.get("input")
    if not isinstance(payload, dict) or not payload:
        raise SkillSemanticsError("f93_calc_input_invalid")
    if set(payload) != set(step["input_domain"]):
        extra = sorted(set(payload) ^ set(step["input_domain"]))
        raise SkillSemanticsError(
            "f93_calc_input_domain_mismatch:" + ",".join(extra))
    import legal_entry
    result = legal_entry.call(step["method"],
                              {"matter_id": args["matter_id"],
                               "input": payload},
                              config)
    return {
        "schema": SCHEMA,
        "semantic": "calculate",
        "skill": {"id": parsed["id"],
                  "contentSha256": parsed["contentSha256"],
                  "calcStepSha256": step["sha256"]},
        "step": {"method": step["method"],
                 "ruleVersion": step["rule_version"],
                 "calendarVersion": step["calendar_version"],
                 "inputDomain": step["input_domain"]},
        "input": payload,
        "result": result,
    }


# ---------------------------------------------------------------------- #
# 入口与 seam
# ---------------------------------------------------------------------- #


def skill_call(method: str, args: dict, config: dict) -> dict:
    if method == "skill.read":
        _require(args, {"skill_path"}, "f93_read_params_invalid")
        return read_skill(_text(args.get("skill_path"),
                                "f93_skill_path_invalid"))
    if method == "skill.review_instantiate":
        _require(args,
                 {"skill_path", "skill_id", "matter_id", "batch_id", "key"},
                 "f93_instantiate_params_invalid")
        return skill_review_instantiate(args, config)
    if method == "skill.calculate":
        _require(args,
                 {"skill_path", "skill_id", "matter_id", "input"},
                 "f93_calculate_params_invalid")
        return skill_calculate(args, config)
    raise NotConnected("method_not_connected:" + method)


def _harness_call(method: str, args: dict, config: dict) -> dict:
    """harness 公开面分派 seam（默认＝legal_entry.call 同进程径；selfhost
    侧 PG 直连部署由调用方替换本 seam——同 U05/U31/U48 先例）。"""
    import legal_entry
    return legal_entry.call(method, args, config)
