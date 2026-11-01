# -*- coding: utf-8 -*-
"""F72 人民法院案例库官方分层接入——产品桥面（工单 W4-U42，负测先行）。

权威分工（不复制第二权威）：
- 梯子/回执/适配器唯一权威 = cases 公开面（P08 扩展，cases 仓分支交付
  bced7c9：lcr/caselib.py 承载＋lcr/public_facade.py _execute_caselib）。
  检索一律走 legal_entry._call_case_public("case.search", execution.caseLibrary)
  ——F68 顺序宪法（本地免费先试）与回执审计在桥上强制，调用方不可退订。
- 本模块只做三件产品侧事：
  ① caselib.register：licensed 语料承载登记（语料许可门在 cases 侧强制，
     产品面只校验回读形状并回投影，绝不放宽）；
  ② caselib.search：经 case.search 公开面真跑后，对 caseLibrary additive 块
     做 E19 同频戳审计（retrievalScoreIsNotWinRate 类：相关度非概率/命题
     不代签/分是十进制文本；任何 probability 形字段具名拒），并在产品投影
     上盖 scoreSemantics 常量戳（纯纪律声明，零数据合成）；
  ③ caselib.tier：指导性/入库/普通裁判三分层逐条回读（官方 tier 闭集
     guiding_case/included_case；普通裁判=具名来源的分类维度，绝不写入官方
     tier 字段；web 页面声明只能作 provenance 备注——不因官方网页就签分层；
     无来源=unknown 具名，不默认 ordinary）。

裁决#8-12 负测先行（00-总协调 §6.1）：本构建未获案例库 API 授权——
- 配置域不存在任何端点/URL 键（结构性零预造端点，W4-U03 N2 同口径）；
- 未授权梯子语义 = skipped/not_authorized（F68 已 VERIFIED），caseLibrary
  块缺席就是缺席，产品面绝不补造；
- live transport 显式具名缺席（cases 侧 caselib_live_transport_not_
  implemented_pending_authorization），授权后补联测（回收点具名）；
- 本模块零 URL 字面量、零网络/子进程导入（AST 可验，wiring 测试钉定）。

config 键（cases 桥同域）：cases_root（v4 root，承载位置）、
cases_import_path（钉定 cases 检出）、caselib_dataset_version（search/tier
必配 pin；register 回读的 datasetVersion 与之冲突即具名拒）。缺配置 =
NOT_CONNECTED（exit 3），typed 错误（str 仅 caselib_* 错误码）同样经
NotConnected 通道具名上浮。
"""
from __future__ import annotations

import json

SCHEMA_REGISTER_PROJECTION = "lvyin-caselib-register/1"
SCHEMA_SEARCH_PROJECTION = "lvyin-caselib-search/1"

SOURCE_NAME = "court_case_library"          # F68 梯子类别名（别名零 URL）

# E19 同频戳（W2b-U27 JC prediction_separation 同族常量；桥级转录，纯纪律
# 声明零数据合成——检索分是相关度不是胜率，样本成员不由检索结果宣告）。
SCORE_SEMANTICS_STAMP = {
    "retrievalScoreIsNotWinRate": True,
    "notAPopulationSample": True,
    "probability": None,
}

# probability 形字段禁入（E19 编造三形态拒同口径；嵌套扫描请求与回执块）。
PROBABILITY_FIELD_BAN = ("winRate", "victoryRate", "successProbability",
                         "probability", "win_rate", "胜率")

# cases 侧 caselib 面的冻结常量（本面不重定义，从钉定检出导入后校验）。
_PROPOSITION_SUPPORT_EXPECTED = \
    "UNSIGNED_SOURCE_DECLARATION_IS_NOT_PROPOSITION_SUPPORT"

_ERROR_CODES_CLOSED = (
    "caselib_config_missing",
    "caselib_config_forbidden",
    "caselib_module_missing",
    "caselib_state_unavailable",
    "caselib_binding_conflict",
    "caselib_args_invalid",
    "caselib_probability_field_forbidden",
    "caselib_block_missing",
    "caselib_block_stamp_invalid",
    "caselib_locator_binding_invalid",
)
# cases 承载侧（lcr.caselib ERROR_CODES_CLOSED）的 caselib_* 码经本面转录
# 上浮：码域按前缀约定封闭（非 caselib_ 前缀一律构造期具名拒），桥面只透
# 码不透消息。

# 「客户端构造即拒」（W4-U03 N2 同口径：授权形态零预造端点）：本面配置域
# 不存在任何端点键；凡本域键（caselib/case/court/library）携端点形「段」
# （url/uri/endpoint/host/port/addr/server，按非字母数字分段整段相等——
# import 的 port 子串不算），一律构造期具名拒——授权落点是 cases 侧
# licensed 语料承载，绝不是 URL。
import re as _re
_ENDPOINT_SEGMENTS = frozenset({"url", "uri", "endpoint", "host", "port",
                                "addr", "address", "server"})
_DOMAIN_KEY_TOKENS = ("caselib", "case", "court", "library")


def _refuse_endpoint_config(config) -> None:
    for key in config:
        k = str(key).lower()
        segments = {s for s in _re.split(r"[^a-z0-9]+", k) if s}
        if any(t in k for t in _DOMAIN_KEY_TOKENS) \
                and (segments & _ENDPOINT_SEGMENTS):
            raise CaseLibraryError(
                "caselib_config_forbidden",
                "config key %r is an endpoint-shaped key; the court case "
                "library face has no endpoint (client construction refused; "
                "W4-U03 N2 same standard)" % key)


class CaseLibraryError(Exception):
    """Named error of the F72 product face; codes are the caselib_* domain."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        if code not in _ERROR_CODES_CLOSED and not code.startswith("caselib_"):
            raise ValueError("caselib face error code outside the caselib_* "
                             "domain: " + code)
        self.code = code


def _require_config(config, keys):
    missing = [k for k in keys if not config.get(k)]
    if missing:
        raise CaseLibraryError("caselib_config_missing",
                               "missing config keys: " + ",".join(missing))


def _probability_scan(obj, where: str) -> None:
    """嵌套扫描 probability 形字段（E19 同口径：塞了就是具名拒）。"""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key) in PROBABILITY_FIELD_BAN:
                raise CaseLibraryError(
                    "caselib_probability_field_forbidden",
                    "%s field %r is probability-shaped; retrieval relevance "
                    "stays a relevance score (retrievalScoreIsNotWinRate)" % (where, key))
            _probability_scan(value, where)
    elif isinstance(obj, list):
        for item in obj:
            _probability_scan(item, where)


def _pin_lcr(config) -> None:
    """钉定检出优先（W2a-U14 教训的 cases 形）：若同进程已缓存其他检出
    （如前波 w2b-u57）的 lcr 包——其 __path__ 不在 cases_import_path——先
    逐出缓存再导入，保证承载面（lcr.caselib）与梯子面（lcr.public_facade）
    与钉定检出同源。生产子进程为净进程，本函数为 no-op。"""
    import os
    import sys
    import_path = os.path.abspath(str(config["cases_import_path"]))
    cached = sys.modules.get("lcr")
    if cached is not None:
        try:
            cached_checkout = os.path.dirname(os.path.abspath(list(cached.__path__)[0]))
        except (AttributeError, IndexError):
            cached_checkout = None
        if cached_checkout is not None and cached_checkout != import_path:
            for name in [m for m in list(sys.modules)
                         if m == "lcr" or m.startswith("lcr.")]:
                del sys.modules[name]


def _caselib_module(config):
    """从钉定 cases 检出导入 lcr.caselib（索引 owner 公开扩模块）。"""
    import os
    import sys
    _refuse_endpoint_config(config)
    _require_config(config, ("cases_import_path", "cases_root"))
    import_path = str(config["cases_import_path"])
    if not os.path.isdir(import_path):
        raise CaseLibraryError("caselib_module_missing",
                               "cases_import_path_missing:" + import_path)
    if import_path in sys.path:
        sys.path.remove(import_path)
    sys.path.insert(0, import_path)   # 钉定检出恒置首（异源 path 项可能在首）
    _pin_lcr(config)
    try:
        from lcr import caselib
    except ImportError as exc:
        raise CaseLibraryError("caselib_module_missing",
                               "lcr.caselib not importable from %s: %s"
                               % (import_path, exc)) from None
    # 冻结常量漂移即具名拒（命题不代签语义必须与 cases 侧逐字同源）。
    if getattr(caselib, "PROPOSITION_SUPPORT_UNSIGNED", None) \
            != _PROPOSITION_SUPPORT_EXPECTED:
        raise CaseLibraryError(
            "caselib_module_missing",
            "lcr.caselib.PROPOSITION_SUPPORT_UNSIGNED drifted from the pinned "
            "constant; refusing to consume an unverified face")
    return caselib


def _read_state(config):
    caselib = _caselib_module(config)
    state = caselib.CaseLibCorpus(str(config["cases_root"])).read()
    if state is None:
        raise CaseLibraryError("caselib_state_unavailable",
                               "no caselib corpus registered under cases_root")
    return caselib, state


def _check_dataset_pin(config, state):
    pin = config.get("caselib_dataset_version")
    if not pin:
        raise CaseLibraryError(
            "caselib_config_missing",
            "caselib_dataset_version pin is required for search/tier "
            "(dataset/indexVersion binding is the F72 acceptance spine)")
    if str(pin) != state["datasetVersion"]:
        raise CaseLibraryError(
            "caselib_binding_conflict",
            "caselib_dataset_version pin %r != registered corpus %r"
            % (pin, state["datasetVersion"]))


# ---------------------------------------------------------------- register

def register_corpus(args: dict, config) -> dict:
    """caselib.register：licensed 语料承载登记（许可门在 cases 侧，产品面
    不放宽；回读投影携带 datasetVersion/indexVersion 钉定值供配置绑定）。"""
    if not isinstance(args, dict) or not isinstance(args.get("manifest"), dict):
        raise CaseLibraryError("caselib_args_invalid",
                               "caselib.register requires args.manifest object")
    caselib = _caselib_module(config)
    try:
        state = caselib.CaseLibCorpus(str(config["cases_root"])).register(
            args["manifest"])
    except caselib.CaseLibError as exc:
        raise CaseLibraryError(str(exc.code), str(exc)) from None
    unknown = sorted(set(state) - {"schema", "source", "license", "revision",
                                   "datasetVersion", "indexVersion", "records"})
    if unknown or state.get("source") != SOURCE_NAME:
        raise CaseLibraryError("caselib_state_unavailable",
                               "registered state shape invalid: %s" % unknown)
    return {"schema": SCHEMA_REGISTER_PROJECTION,
            "source": state["source"],
            "license": dict(state["license"]),
            "revision": state["revision"],
            "datasetVersion": state["datasetVersion"],
            "indexVersion": state["indexVersion"],
            "recordCount": len(state["records"]),
            "liveTransport": caselib.LIVE_TRANSPORT_STATUS}


# ------------------------------------------------------------------ search

def audit_case_library_block(block, caselib) -> dict:
    """E19 同频戳审计（块在位才审；缺席=未授权诚实态，绝不补造）。"""
    if not isinstance(block, dict):
        raise CaseLibraryError("caselib_block_missing",
                               "caseLibrary block present but not an object")
    if block.get("relevanceNotProbability") is not True \
            or block.get("propositionSupport") != caselib.PROPOSITION_SUPPORT_UNSIGNED \
            or block.get("liveTransport") != caselib.LIVE_TRANSPORT_STATUS:
        raise CaseLibraryError(
            "caselib_block_stamp_invalid",
            "caseLibrary block missing the E19-conformant stamp trio "
            "(relevanceNotProbability/propositionSupport/liveTransport)")
    _probability_scan(block, "caseLibrary block")
    for hit in block.get("hits") or []:
        locator = hit.get("locator") or {}
        if not (isinstance(locator, dict) and locator.get("datasetVersion")
                and locator.get("indexVersion") and "canonicalDocId" in locator):
            raise CaseLibraryError(
                "caselib_locator_binding_invalid",
                "hit locator must bind datasetVersion/indexVersion/canonicalDocId")
        if not isinstance(hit.get("score"), str):
            raise CaseLibraryError(
                "caselib_block_stamp_invalid",
                "hit.score must stay decimal text (float is forbidden: "
                "retrievalScoreIsNotWinRate family)")
        if not isinstance(hit.get("tiering"), dict) \
                or "officialTier" not in hit["tiering"]:
            raise CaseLibraryError(
                "caselib_block_stamp_invalid",
                "hit.tiering readback missing officialTier")
    return block


def search_through_bridge(args: dict, config, call_case_public) -> dict:
    """caselib.search：走 case.search 公开面（梯子强制），审计 caseLibrary
    块后转录；产品投影盖 E19 同频 scoreSemantics 常量戳。

    双重 pin（F72 验收主轴「dataset/indexVersion 钉定」）：
    - cases_dataset_version＝本地语料（local_corpus 梯腿）数据集 pin，
      case.search 合同自带；
    - caselib_dataset_version＝caselib 承载数据集 pin，经
      execution.caseLibrary.datasetVersion 注入 cases 侧适配器；调用方自带
      该键时与钉定态冲突即具名拒。
    """
    if not isinstance(args, dict):
        raise CaseLibraryError("caselib_args_invalid",
                               "caselib.search args must be an object")
    _refuse_endpoint_config(config)
    _require_config(config, ("cases_root", "cases_import_path",
                             "cases_dataset_version",
                             "caselib_dataset_version"))
    _probability_scan(args, "caselib.search args")
    caselib, state = _read_state(config)
    _check_dataset_pin(config, state)
    selector = args.get("query") or {}
    if not isinstance(selector, dict) or selector.get("mode") != "text":
        raise CaseLibraryError("caselib_args_invalid",
                               "caselib.search requires query.mode=text")
    caselib_exec = args.get("caseLibrary")
    if caselib_exec is None:
        caselib_exec = {}
    if not isinstance(caselib_exec, dict):
        raise CaseLibraryError("caselib_args_invalid",
                               "args.caseLibrary must be an object when present")
    unknown = sorted(set(caselib_exec) - {"filters", "datasetVersion"})
    if unknown:
        raise CaseLibraryError(
            "caselib_args_invalid",
            "args.caseLibrary keys outside the closed set: " + ",".join(unknown))
    caller_pin = caselib_exec.get("datasetVersion")
    if caller_pin is not None and str(caller_pin) != state["datasetVersion"]:
        raise CaseLibraryError(
            "caselib_binding_conflict",
            "caller caseLibrary.datasetVersion %r != registered corpus %r"
            % (caller_pin, state["datasetVersion"]))
    caselib_exec = dict(caselib_exec)
    caselib_exec["datasetVersion"] = state["datasetVersion"]
    body = {"query": {"mode": "text", "text": selector.get("text") or ""},
            "filters": args.get("filters") or {},
            "limit": args.get("limit", 20),
            "execution": {"caseLibrary": caselib_exec}}
    _pin_lcr(config)   # 梯子面同源：_call_case_public 的 lcr.public_facade
                       # 必须来自钉定检出（否则 F72 适配器缺席＝块静默丢失）
    result = call_case_public("case.search", body, config)
    block = result.get("caseLibrary")
    projection = {"schema": SCHEMA_SEARCH_PROJECTION,
                  "source": SOURCE_NAME,
                  "datasetVersion": state["datasetVersion"],
                  "indexVersion": state["indexVersion"],
                  "authorizedTried": block is not None,
                  "caseLibrary": None,
                  "retrievalOrder": result.get("retrievalOrder"),
                  "localHits": len(result.get("hits") or [])}
    if block is not None:
        audit_case_library_block(block, caselib)
        projection["caseLibrary"] = block
        projection["scoreSemantics"] = dict(SCORE_SEMANTICS_STAMP)
    return projection


# -------------------------------------------------------------------- tier

def tier_readback(args: dict, config) -> dict:
    """caselib.tier：三分层逐条回读（官方 tier／普通裁判分类／无声面 unknown
    具名）；datasetVersion 钉定绑定校验前置。"""
    if not isinstance(args, dict) or not args.get("docId"):
        raise CaseLibraryError("caselib_args_invalid",
                               "caselib.tier requires args.docId")
    caselib, state = _read_state(config)
    _check_dataset_pin(config, state)
    try:
        view = caselib.CaseLibCorpus(str(config["cases_root"])).tier_readback(
            str(args["docId"]),
            dataset_version=state["datasetVersion"])
    except caselib.CaseLibError as exc:
        raise CaseLibraryError(str(exc.code), str(exc)) from None
    if view.get("datasetVersion") != state["datasetVersion"] \
            or view.get("indexVersion") != state["indexVersion"]:
        raise CaseLibraryError("caselib_locator_binding_invalid",
                               "tier readback drifted from the pinned state")
    return view


def call(method: str, args, config):
    """Entry used by the legal_entry bridge; config may be a plain dict."""
    if config is None:
        config = {}
    if not isinstance(args, dict):
        raise CaseLibraryError("caselib_args_invalid", "args must be an object")
    if method == "caselib.register":
        return register_corpus(args, config)
    if method == "caselib.search":
        from legal_entry import _call_case_public
        return search_through_bridge(args, config, _call_case_public)
    if method == "caselib.tier":
        return tier_readback(args, config)
    raise CaseLibraryError("caselib_args_invalid",
                           "unknown caselib face method: " + str(method))
