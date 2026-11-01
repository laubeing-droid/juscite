# -*- coding: utf-8 -*-
"""F98 技能自动路由引擎（触发评分/预算装填/activeLimit）产品面（W4-U47）。

义务 06:F98（17 卡；F98-desktop/F98-selfhost 双实例；owner=product；B4）
「技能自动路由引擎（触发评分/预算装填/activeLimit）」＋台账断言「显式调用
优先，自动路由预算/activeLimit 可核，材料注入不借机启 skill」＋preserved
「v1 显式调用为主，自动路由随后」＋17 卡「上游原生 app/client 或产品模块；
优先保原生能力→仅选型必要差异→新增产品合同」。

原生契约（oc28 pin 026b106 只读对照；本面零改动上游、不创第二 Agent loop）：
- packages/core/src/config/plugin/skill-file.ts:49-51：autoinvoke＝
  metadata["opencode/autoinvoke"] ?? (disable-model-invocation ? false :
  undefined)（布尔词表 true/yes/on/1、false/no/off/0，其余＝未声明）。
- packages/core/src/skill/instructions.ts:76：原生自动列举过滤器＝
  description 存在 ∧ autoinvoke !== false——原生面不列入的技能不得自动
  调用。本面候选池＝该过滤器逐字镜像（优先保原生能力：原生排除＝本面排
  除；原生未排除＝本面才可评分）。
- 显式调用原生无条件（用户直调以 <skill_content> 注入，不受 autoinvoke/
  预算/activeLimit 约束）——本面 explicit 径同样无条件，且在结构上先于
  评分返回（自动路由只在无显式调用时介入＝AST 断言 explicit 分支零评分
  调用；显式未知技能 typed 拒，绝不静默回落自动路由）。

落点（本面＝自动路由唯一产品决策面；UI/agent 仅调用/展示；候选与投影唯
一来源＝既有 F94 目录公开面 skill.catalog.read（活动面 receipt＋
runtime_projection 上游 toModelOutput 逐字节同形），零第二目录权威）：

- skill.route.decide：{channel, query, explicit?, materials?, policy?}
  · explicit 存在 → mode=explicit：按 skill_id 经目录面校验并装填该技能
    投影（无条件，不吃预算/activeLimit＝原生显式语义）；零评分、零候选
    评估、零自动装填；query 只入留痕 sha。materials 照常扫描留痕。
  · 无 explicit → mode=auto：候选＝目录活动面技能经原生过滤器；触发评分
    （确定性整数分，两轨词元化：Latin 词元＋中文连字二元组）：
        id 命中（Latin 词边界/子串）   +50  ref id_hit
        name 全名命中（query 含全名）  +40  ref name_hit
        名称词元交（每命中）           +20 封顶 +40  ref name_kw:<词元>
        描述词元交（每命中）           +10 封顶 +30  ref kw_hit:<词元>
    达阈（trigger_threshold 默认 40）按 (-score, id) 确定性排序：
      activeLimit（默认 3）＝合格数上限——超限 typed 拒
      f98_active_limit_exceeded（绝不静默裁剪；拒绝照常留痕带评分依据）；
      预算装填 load_budget_bytes（默认 16384）＝按序装填，装不下→
      deferred 具名 budget_exhausted 留痕可核（零静默丢弃），一件都装不
      下→ typed 拒 f98_budget_no_fit。
  · materials（不可信材料块）绝不入评分器（评分器输入只有 query 通道）：
    逐块经既有 F27 injection.scan 扫描（同频同规则表），家族命中记
    quarantine——只记 id/sha256/家族/条数，零内容回显。注入内容含 skill
    触发词/指令不引发自动路由（注入隔离；负测与正对照同run可核）。
- skill.route.log：决策留痕读取（decisions.jsonl 逐条 digest 复核；篡改
  ＝typed 拒 f98_log_digest_mismatch；审计可重放：同输入两跑 digest 相
  等——seq/digest 不入 digest 体）。
- 工具白名单并集下发（RE-12 对拍 T9＝B15/B16 等量）：decide 响应携
  allowed_tools＝本轮 loaded 技能声明工具并集——声明面＝SKILL.md
  「## 工具面」节内行内代码点号 token（确定性提取，零第二声明权威；
  无该节＝纯方法论零声明）；每条 loaded 另携该技能 tools 清单。
  deferred（未注入）不授权（竞品语义：仅注入技能授工具）。宿主把
  allowed_tools 回设 config["skill_tool_policy"]（legal_entry.call 漏斗
  对工具族方法逐调用把关，未授权具名拒 f98_tool_not_allowed:*——竞品
  /active tool policy/ 等量；零触发/非技能轮不设键＝不设防，B49 空态
  回合照常执行）。

决策留痕（唯一写入口 decide；留痕零内容）：每路由一次恰追加一记录
（seq 单调；schema/face/seq/digest/mode/decision/channel/query_sha256/
explicit/candidates{eligible,excluded+reason}/scores+评分依据 ref/
loaded+bytes+sha256/deferred+reason/materials+clean+families/
finding_count+payload_sha256/policy 快照/decision/reason）；记录零
query/material 原文（内容性字段只有 sha256 与工程标识——留痕本身不得成
为第二注入通道，同 F27 扫描报告纪律）。

fail-closed：typed error（SkillRoutingError 的 str 只有 f98_* 错误码，
绝不携 query/material 内容）；未配置 skill_routing_state_root／
skill_catalog_state_root＝typed 拒（桥包 NotConnected exit 3）；F27 面
异常归一 f98_material_invalid；F94 面 typed 码归一 f98_catalog_failed。
确定性：无模型、无网络、无随机、无时钟（记录无 wall time；seq 之外全确
定性→同输入跨 run/跨 profile 可复跑对账）。金额不涉及；无 DAG 无编排
（一次决策一次装填）。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from bridge_errors import NotConnected

SCHEMA = "juscite-f98-skill-routing/1"

# legal_entry 冻结方法组（唯一入口；组外方法绝不落到本面）。
SKILL_ROUTING_METHODS = frozenset({
    "skill.route.decide",
    "skill.route.log",
})

CHANNELS = ("public", "controlled")

# 路由策略闭集（字段外一律拒；缺省＝默认策略）。active_limit=0 合法：
# 自动路由对任何合格候选即拒（上限真实生效）；load_budget_bytes≥1。
_POLICY_FIELDS = ("trigger_threshold", "active_limit", "load_budget_bytes")
_DEFAULT_POLICY = {"trigger_threshold": 40, "active_limit": 3,
                   "load_budget_bytes": 16384}

# 触发评分权重（确定性整数；名称信号强于描述信号；描述单独永不及阈）。
SCORE_ID_HIT = 50
SCORE_NAME_HIT = 40
SCORE_NAME_KW_HIT = 20
SCORE_NAME_KW_CAP = 40
SCORE_KW_HIT = 10
SCORE_KW_CAP = 30

# 决策闭值。
DECISION_EXPLICIT = "explicit"
DECISION_AUTO = "auto"
DECISION_NONE = "none"
DECISION_REFUSED_ACTIVE_LIMIT = "refused_active_limit"
DECISION_REFUSED_BUDGET_NO_FIT = "refused_budget_no_fit"

LOG_FILENAME = "decisions.jsonl"

# 原生 autoinvoke 镜像（skill-file.ts:49-51）。
_AUTOINVOKE_METADATA_KEY = "opencode/autoinvoke"
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?",
                             re.S)
_FM_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)$")
_FM_NESTED_RE = re.compile(r"^[ \t]+([^\s:]+):[ \t]*(.*)$")
_TRUE_WORDS = frozenset(("true", "yes", "on", "1"))
_FALSE_WORDS = frozenset(("false", "no", "off", "0"))

# 两轨词元化：Latin 词元（小写 [a-z0-9]+）＋中文连字二元组（含单字 run）。
_LATIN_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_LATIN_TERM_RE = re.compile(r"[a-z0-9]\Z")


class SkillRoutingError(ValueError):
    """Typed F98 face failure; str() is a code, never query/material content."""


def _fail(code: str) -> SkillRoutingError:
    return SkillRoutingError(code)


def _require(args: dict, fields: frozenset, code: str) -> None:
    """DTO 闭集校验：必带字段缺一即拒、闭集外字段即拒（无旁路）。"""
    if not isinstance(args, dict) or set(args) != set(fields):
        raise NotConnected(code)


# ---------------------------------------------------------------------- #
# 两轨词元化与命中（确定性；零模型）
# ---------------------------------------------------------------------- #


def _latin_terms(text: str) -> list:
    return sorted(set(_LATIN_RE.findall(text.lower())))


def _cjk_terms(text: str) -> list:
    terms = []
    for run in _CJK_RE.findall(text):
        if len(run) == 1:
            terms.append(run)
        else:
            terms.extend(run[i:i + 2] for i in range(len(run) - 1))
    return sorted(set(terms))


def _contains_term(haystack_lower: str, term: str) -> bool:
    """Latin 词元按词边界（recalculate 不冒 calc）；其余（id 连字/中文）
    按子串。"""
    if _LATIN_TERM_RE.fullmatch(term):
        return re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(term),
                         haystack_lower) is not None
    return term in haystack_lower


def _keywords_of(text: str) -> list:
    return sorted(set(_latin_terms(text)) | set(_cjk_terms(text)))


def _keyword_hit(keyword: str, query_lower: str, query_latin: set) -> bool:
    if _LATIN_TERM_RE.fullmatch(keyword):
        return keyword in query_latin
    return keyword in query_lower


# ---------------------------------------------------------------------- #
# 原生 autoinvoke 镜像（skill-file.ts:46-51 逐语义）
# ---------------------------------------------------------------------- #


def _bool_word(raw: str):
    word = raw.strip().lower()
    if word in _TRUE_WORDS:
        return True
    if word in _FALSE_WORDS:
        return False
    return None


def _autoinvoke_of(entry_text: str) -> "tuple[bool | None, bool | None]":
    """→ (autoinvoke, disable_model_invocation)。镜像 skill-file.ts：
    autoinvoke＝metadata["opencode/autoinvoke"] ?? (disable？
    false : undefined)。frontmatter 缺失＝(None, None)（上游无 frontmatter
    的文件同样可加载，name/description 缺省由 id/无 派生）。"""
    match = _FRONTMATTER_RE.match(entry_text)
    if match is None:
        return None, None
    disable = None
    opencode_flag = None
    in_metadata = False
    for line in match.group(1).splitlines():
        plain = _FM_LINE_RE.match(line)
        if plain is not None:
            key, raw = plain.group(1), plain.group(2)
            if key == "metadata":
                # 嵌套映射形态＝键后空值（随行缩进块）；行内集合形态本面
                # 不解析（上游 Unknown 容忍，autoinvoke 视为未声明）。
                in_metadata = not raw.strip()
                continue
            in_metadata = False
            if key == "disable-model-invocation":
                disable = _bool_word(raw)
            continue
        nested = _FM_NESTED_RE.match(line)
        if nested is not None and in_metadata \
                and nested.group(1) == _AUTOINVOKE_METADATA_KEY:
            opencode_flag = _bool_word(nested.group(2))
    autoinvoke = opencode_flag if opencode_flag is not None else (
        False if disable is True else None)
    return autoinvoke, disable


# ---------------------------------------------------------------------- #
# 工具面声明提取（RE-12 对拍 T9＝B15/B16：allowedTools 白名单并集下发）
# ---------------------------------------------------------------------- #

# 声明面＝SKILL.md「## 工具面」节内行内代码点号 token（如 `kb.search`）；
# 无该节＝纯方法论零声明。确定性提取，零第二声明权威。
_TOOLS_HEADING = "## 工具面"
_NEXT_HEADING_RE = re.compile(r"^## ", re.M)
_INLINE_TOOL_RE = re.compile(r"`([a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+)`")


def _declared_tools_of(projection: str) -> list:
    start = projection.find(_TOOLS_HEADING)
    if start < 0:
        return []
    body = projection[start + len(_TOOLS_HEADING):]
    match = _NEXT_HEADING_RE.search(body)
    if match is not None:
        body = body[:match.start()]
    return sorted(set(_INLINE_TOOL_RE.findall(body)))


# ---------------------------------------------------------------------- #
# 触发评分（评分器输入只有 query 通道——materials 结构上进不来）
# ---------------------------------------------------------------------- #


def _score_skill(query_lower: str, query_latin: set, skill: dict) -> dict:
    """确定性整数评分＋具名评分依据 ref。skill＝活动面 receipt 条目
    {id, name, description?}（F94 公开面，零第二目录权威）。"""
    skill_id = skill["id"]
    name = skill.get("name") or skill_id
    score = 0
    basis = []
    if _contains_term(query_lower, skill_id.lower()):
        score += SCORE_ID_HIT
        basis.append("id_hit")
    if _contains_term(query_lower, name.lower()):
        score += SCORE_NAME_HIT
        basis.append("name_hit")
    name_hits = [kw for kw in _keywords_of(name)
                 if _keyword_hit(kw, query_lower, query_latin)]
    if name_hits:
        score += min(SCORE_NAME_KW_HIT * len(name_hits), SCORE_NAME_KW_CAP)
        basis.extend("name_kw:" + kw for kw in name_hits)
    desc_hits = [kw for kw in _keywords_of(skill.get("description") or "")
                 if _keyword_hit(kw, query_lower, query_latin)]
    if desc_hits:
        score += min(SCORE_KW_HIT * len(desc_hits), SCORE_KW_CAP)
        basis.extend("kw_hit:" + kw for kw in desc_hits)
    return {"skill": skill_id, "score": score, "basis": basis}


def _eligible_reason(skill: dict, entry_text: str):
    """原生过滤器镜像（instructions.ts:76）：None＝自动候选；否则具名排除
    原因。原生排除＝本面排除（优先保原生能力）。"""
    if not skill.get("description"):
        return "no_description"
    autoinvoke, _disable = _autoinvoke_of(entry_text)
    if autoinvoke is False:
        return "autoinvoke_false"
    return None


# ---------------------------------------------------------------------- #
# 目录面 seam 与入口文件定位（唯一候选源＝F94 公开面）
# ---------------------------------------------------------------------- #


def _catalog_call(method: str, args: dict, config: dict) -> dict:
    import skill_catalog
    try:
        return skill_catalog.catalog_call(method, args, config)
    except skill_catalog.SkillCatalogError as exc:
        raise _fail("f98_catalog_failed:" + str(exc)) from None


def _entry_text_of(directory: str, skill_id: str) -> str:
    """安装面入口文件字节（目录技能 SKILL.md／根级单文件 <id>.md）——只读
    解析 autoinvoke 声明；两形皆缺＝typed 拒（活动面损坏，响亮不静默）。"""
    base = Path(directory)
    for candidate in (base / "SKILL.md", base / (skill_id + ".md")):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise _fail("f98_catalog_entry_missing:" + skill_id)


# ---------------------------------------------------------------------- #
# 决策留痕（内容自由化：零 query/material 原文；digest 可复核可重放）
# ---------------------------------------------------------------------- #


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _digest_of(body: dict) -> str:
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _log_path(config: dict):
    root = config.get("skill_routing_state_root")
    if not isinstance(root, str) or not root:
        raise _fail("f98_state_root_not_configured")
    return Path(root) / LOG_FILENAME


def _append_record(config: dict, body: dict) -> dict:
    path = _log_path(config)
    history = _read_lines(path)
    seq = len(history) + 1
    digest = _digest_of(body)
    record = dict(body)
    record["seq"] = seq
    record["digest"] = digest
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_canonical(record) + "\n")
    return {"seq": seq, "digest": digest}


def _read_lines(path) -> "list[str]":
    if not path.is_file():
        return []
    return [line for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _verify_record(record: dict) -> None:
    if not isinstance(record, dict) or record.get("schema") != SCHEMA \
            or not isinstance(record.get("seq"), int) \
            or not isinstance(record.get("digest"), str):
        raise _fail("f98_log_record_invalid")
    body = {k: v for k, v in record.items()
            if k not in ("seq", "digest")}
    if _digest_of(body) != record["digest"]:
        raise _fail("f98_log_digest_mismatch:seq=%s" % record["seq"])


# ---------------------------------------------------------------------- #
# materials：F27 同频扫描（家族/条数/sha 入留痕；内容绝不入）
# ---------------------------------------------------------------------- #


def _scan_materials(materials) -> "list[dict]":
    if materials is None:
        return []
    if not isinstance(materials, list):
        raise _fail("f98_material_invalid")
    import injection_defense
    records = []
    for index, block in enumerate(materials):
        if not isinstance(block, dict) \
                or set(block) != {"id", "text"} \
                or not isinstance(block.get("id"), str) or not block["id"]:
            raise _fail("f98_material_fields_invalid")
        try:
            report = injection_defense.scan_text(block.get("text"),
                                                 kind="material")
        except injection_defense.InjectionFaceError:
            raise _fail("f98_material_invalid") from None
        records.append({"id": block["id"],
                        "payload_sha256": report["content_sha256"],
                        "clean": bool(report["clean"]),
                        "families": report["families"],
                        "finding_count": len(report["findings"])})
    return records


# ---------------------------------------------------------------------- #
# 路由策略（闭集校验）
# ---------------------------------------------------------------------- #


class RoutingPolicy:
    __slots__ = _POLICY_FIELDS

    def __init__(self, *, trigger_threshold=None, active_limit=None,
                 load_budget_bytes=None):
        merged = dict(_DEFAULT_POLICY)
        for field, value in (("trigger_threshold", trigger_threshold),
                             ("active_limit", active_limit),
                             ("load_budget_bytes", load_budget_bytes)):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise _fail("f98_policy_invalid_value:" + field)
            merged[field] = value
        if merged["trigger_threshold"] < 0:
            raise _fail("f98_policy_invalid_value:trigger_threshold")
        if merged["active_limit"] < 0:
            raise _fail("f98_policy_invalid_value:active_limit")
        if merged["load_budget_bytes"] < 1:
            raise _fail("f98_policy_invalid_value:load_budget_bytes")
        self.trigger_threshold = merged["trigger_threshold"]
        self.active_limit = merged["active_limit"]
        self.load_budget_bytes = merged["load_budget_bytes"]

    @classmethod
    def from_mapping(cls, mapping) -> "RoutingPolicy":
        if mapping is None:
            return cls()
        if not isinstance(mapping, dict):
            raise _fail("f98_policy_invalid")
        unknown = sorted(set(mapping) - set(_POLICY_FIELDS))
        if unknown:
            raise _fail("f98_policy_unknown_field:" + ",".join(unknown))
        return cls(**mapping)

    def as_dict(self) -> dict:
        return {field: getattr(self, field) for field in _POLICY_FIELDS}


# ---------------------------------------------------------------------- #
# decide：显式优先（结构上先于评分返回）＋ 自动路由（评分→activeLimit→预算装填）
# ---------------------------------------------------------------------- #


def route_decide(args: dict, config: dict) -> dict:
    _log_path(config)  # 留痕根未配置＝入口即 typed 拒（不留半程）
    policy = RoutingPolicy.from_mapping(args.get("policy"))
    channel = args.get("channel")
    if channel not in CHANNELS:
        raise _fail("f98_channel_invalid")
    if not isinstance(config.get("skill_catalog_state_root"), str) \
            or not config.get("skill_catalog_state_root"):
        raise _fail("f98_catalog_state_root_not_configured")
    materials = _scan_materials(args.get("materials"))
    explicit = args.get("explicit")
    query = args.get("query")
    if explicit is not None:
        # ---- 显式径：先于一切候选评估/评分返回（AST 断言锚点）。 --------
        if not isinstance(explicit, dict) \
                or set(explicit) != {"skill_id"} \
                or not isinstance(explicit.get("skill_id"), str) \
                or not explicit["skill_id"]:
            raise _fail("f98_explicit_invalid")
        active = _active_receipt(channel, config)
        wanted = explicit["skill_id"]
        match = next((s for s in active["skills"]
                      if s["id"] == wanted), None)
        if match is None:
            raise _fail("f98_explicit_unknown:" + wanted)
        projection = _projection_of(channel, wanted, config)
        explicit_tools = _declared_tools_of(projection["projection"])
        query_text = query if isinstance(query, str) else ""
        body = _body_of(mode="explicit", decision=DECISION_EXPLICIT,
                        channel=channel, query=query_text, policy=policy,
                        candidates={"eligible": [], "excluded": []},
                        scores=[], explicit_skill_id=wanted,
                        loaded=[_loaded_entry(wanted, projection)],
                        deferred=[], materials=materials, reason=None)
        ref = _append_record(config, body)
        return {"schema": SCHEMA, "face": "route.decide",
                "mode": "explicit", "decision": DECISION_EXPLICIT,
                "channel": channel,
                "query_sha256": body["query_sha256"],
                "skill": {"id": match["id"],
                          "name": match.get("name") or match["id"],
                          "description": match.get("description")},
                "projection": projection["projection"],
                "bytes": projection["bytes"],
                "projection_sha256": projection["sha256"],
                "allowed_tools": explicit_tools,
                "scores": [], "loaded": [], "deferred": [],
                "materials": materials,
                "decision_ref": ref}
    # ---- 自动径（无显式调用才介入）。 --------------------------------
    if not isinstance(query, str) or not query:
        raise _fail("f98_query_required")
    active = _active_receipt(channel, config)
    query_lower = query.lower()
    query_latin = set(_latin_terms(query))
    scores = []
    eligible = []
    excluded = []
    projections = {}
    for skill in sorted(active["skills"], key=lambda s: s["id"]):
        projection = _projection_of(channel, skill["id"], config)
        entry_text = _entry_text_of(projection["directory"], skill["id"])
        reason = _eligible_reason(skill, entry_text)
        if reason is not None:
            excluded.append({"id": skill["id"], "reason": reason})
            continue
        eligible.append(skill["id"])
        scores.append(_score_skill(query_lower, query_latin, skill))
        projections[skill["id"]] = projection
    ranked = sorted((s for s in scores
                     if s["score"] >= policy.trigger_threshold),
                    key=lambda s: (-s["score"], s["skill"]))
    candidates = {"eligible": eligible, "excluded": excluded}
    if len(ranked) > policy.active_limit:
        body = _body_of(mode="auto", decision=DECISION_REFUSED_ACTIVE_LIMIT,
                        channel=channel, query=query, policy=policy,
                        candidates=candidates, scores=scores,
                        explicit_skill_id=None, loaded=[], deferred=[],
                        materials=materials,
                        reason="f98_active_limit_exceeded:%d>%d" % (
                            len(ranked), policy.active_limit))
        _append_record(config, body)  # 拒绝照常留痕（带评分依据）
        raise _fail(body["reason"])
    loaded = []
    deferred = []
    used = 0
    loaded_tools = {}
    for entry in ranked:
        projection = projections[entry["skill"]]
        if used + projection["bytes"] <= policy.load_budget_bytes:
            used += projection["bytes"]
            loaded_tools[entry["skill"]] = _declared_tools_of(
                projection["projection"])
            loaded.append(_loaded_entry(entry["skill"], projection))
        else:
            deferred.append({"skill": entry["skill"],
                             "bytes": projection["bytes"],
                             "reason": "budget_exhausted"})
    if ranked and not loaded:
        body = _body_of(mode="auto", decision=DECISION_REFUSED_BUDGET_NO_FIT,
                        channel=channel, query=query, policy=policy,
                        candidates=candidates, scores=scores,
                        explicit_skill_id=None, loaded=[], deferred=deferred,
                        materials=materials,
                        reason="f98_budget_no_fit:skills=%d budget=%d"
                               % (len(ranked), policy.load_budget_bytes))
        _append_record(config, body)
        raise _fail(body["reason"])
    decision = DECISION_AUTO if loaded else DECISION_NONE
    body = _body_of(mode="auto", decision=decision, channel=channel,
                    query=query, policy=policy, candidates=candidates,
                    scores=scores, explicit_skill_id=None,
                    loaded=loaded, deferred=deferred, materials=materials,
                    reason=None)
    ref = _append_record(config, body)
    return {"schema": SCHEMA, "face": "route.decide", "mode": "auto",
            "decision": decision, "channel": channel,
            "query_sha256": body["query_sha256"],
            "candidates": candidates, "scores": scores,
            "policy": policy.as_dict(),
            "budget": {"load_budget_bytes": policy.load_budget_bytes,
                       "used_bytes": used},
            "loaded": [{"skill": item["skill"], "bytes": item["bytes"],
                        "sha256": item["sha256"],
                        "tools": loaded_tools.get(item["skill"], []),
                        "projection": projections[item["skill"]]
                        ["projection"]} for item in loaded],
            "allowed_tools": sorted({tool for tools in
                                     loaded_tools.values()
                                     for tool in tools}),
            "deferred": deferred, "materials": materials,
            "decision_ref": ref}


def _active_receipt(channel: str, config: dict) -> dict:
    result = _catalog_call("skill.catalog.read",
                           {"channel": channel}, config)
    if not result.get("active"):
        raise _fail("f98_catalog_active_missing")
    return result


def _projection_of(channel: str, skill_id: str, config: dict) -> dict:
    result = _catalog_call("skill.catalog.read",
                           {"channel": channel, "skill_id": skill_id},
                           config)
    projection = result.get("projection")
    if not isinstance(projection, str) or not projection:
        raise _fail("f98_catalog_projection_missing:" + skill_id)
    return {"projection": projection,
            "bytes": len(projection.encode("utf-8")),
            "sha256": hashlib.sha256(
                projection.encode("utf-8")).hexdigest(),
            "directory": result.get("directory") or ""}


def _loaded_entry(skill_id: str, projection: dict) -> dict:
    return {"skill": skill_id, "bytes": projection["bytes"],
            "sha256": projection["sha256"]}


def _body_of(*, mode: str, decision: str, channel: str, query, policy:
             RoutingPolicy, candidates: dict, scores: list,
             explicit_skill_id, loaded: list, deferred: list,
             materials: list, reason) -> dict:
    """留痕体（零内容）：query 只入 sha；materials 只入 id/sha/家族/条数；
    loaded/deferred 只入 id/bytes/sha256/reason。"""
    return {
        "schema": SCHEMA, "face": "route.decide", "mode": mode,
        "decision": decision, "channel": channel,
        "query_sha256": hashlib.sha256(
            (query if isinstance(query, str) else "")
            .encode("utf-8")).hexdigest(),
        "explicit": explicit_skill_id,
        "policy": policy.as_dict(),
        "candidates": candidates, "scores": scores,
        "loaded": loaded, "deferred": deferred,
        "materials": materials, "reason": reason,
    }


# ---------------------------------------------------------------------- #
# log：决策留痕读取（逐条 digest 复核＝篡改响亮拒）
# ---------------------------------------------------------------------- #


def route_log(args: dict, config: dict) -> dict:
    limit = args.get("limit")
    after_seq = args.get("after_seq")
    if limit is not None and (isinstance(limit, bool) or not isinstance(
            limit, int) or limit < 1):
        raise _fail("f98_log_limit_invalid")
    if after_seq is not None and (isinstance(after_seq, bool)
                                  or not isinstance(after_seq, int)
                                  or after_seq < 0):
        raise _fail("f98_log_after_seq_invalid")
    path = _log_path(config)
    records = []
    truncated = False
    for line in _read_lines(path):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            raise _fail("f98_log_record_invalid") from None
        _verify_record(record)
        if after_seq is not None and record["seq"] <= after_seq:
            continue
        if limit is not None and len(records) >= limit:
            truncated = True
            break
        records.append(record)
    return {"schema": SCHEMA, "face": "route.log", "count": len(records),
            "truncated": truncated, "records": records}


def routing_call(method: str, args: dict, config: dict) -> dict:
    if not isinstance(args, dict):
        raise NotConnected("f98_params_invalid")
    if method == "skill.route.decide":
        _require(args,
                 {"channel", "query", "explicit", "materials", "policy"},
                 "f98_decide_params_invalid")
        return route_decide(args, config)
    if method == "skill.route.log":
        _require(args, {"limit", "after_seq"}, "f98_log_params_invalid")
        return route_log(args, config)
    raise NotConnected("method_not_connected:" + method)
