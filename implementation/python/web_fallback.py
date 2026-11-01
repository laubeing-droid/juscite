# -*- coding: utf-8 -*-
"""F74 网页检索兜底＋web-verified 声明（工单 W4-U44）。

F64 确定性降级链（SOURCE_CHAIN_V1=本地→付费→web，W2a-U13 冻结）的末端段：
本地段（E22 lccc_consumer 冻结面）与付费段（P11，W4-U41）具名未命中后，
web 兜底才可开——调用方必须携前两段的具名缺口证据（chain.local_gap /
chain.paid_gap），缺任一＝typed 拒（链末端不跳开）。

四条验收硬点（06 行 F74 acceptance；工单 W4-U44）：
  1. 检索结果 URL 与原文逐字核验：候选 URL 逐字转录自检索响应（零拼造），
     取回原文字节 sha256 绑定入账，引文段对取回原文逐字核对；只存 URL 不
     取原文的记录结构性不存在（verified 记录必带 content_sha256＋声明）。
  2. web 来源声明＝web-verified 档永不冒数据库核验：声明面唯一来源＝
     W4-U41 statute_validity.declare_web_verified（statute.web_declaration
     同一分账语义，跨单一致）；本模块零声明键复制、零 second authority。
  3. 禁编 URL：AST 级零拼造——本模块字符串常量含「网络方案前缀」者仅
     WEB_URL_SCHEMES 两个方案条目；零 f-string/format/%/加号拼 URL、零
     urljoin；检索端点出自 config（运营方配置），结果 URL 逐字转录。
  4. 请求面走权限模型白名单域（T05 教训：CodeMode web fetch 无闸）：所有
     网络请求先过 gate_url（方案白名单＋域名白名单），白名单外 typed 拒，
     闸先于任何网络 I/O（recon 以服务端收包计数亲证）；白名单缺配置＝
     fail-closed NOT_CONNECTED，零隐式放行域。

无网/未授权＝具名缺口不造结果（裁决#8-12 同频）：检索失败/取文失败/状态
非 200/引文不逐字——一律具名入 gaps，绝不伪造 verified 记录。全程确定性
（字符串包含核对＋JSON 转录），零模型。金额不入本面。
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from bridge_errors import NotConnected
from statute_validity import declare_web_verified

# ---------------------------------------------------------------------- #
# 冻结常量
# ---------------------------------------------------------------------- #

WEB_FALLBACK_SCHEMA = "juscite-f74-web-fallback/1"

# 方案白名单（镜像 statute_validity.WEB_URL_SCHEMES；本模块唯一含方案
# 前缀的字符串常量）。
WEB_URL_SCHEMES = ("http://", "https://")

# 单次兜底最多取文核验的候选数（确定性封顶，防无界请求面）。
WEB_RESULT_CAP = 5

FETCH_TIMEOUT = 15

USER_AGENT = "juscite-f74-web-fallback/1"

# 前两段（本地/付费）具名缺口证据键——链末端开启凭证。
CHAIN_PROOF_KEYS = ("local_gap", "paid_gap")


class _FetchError(Exception):
    """取文/检索失败具名包装（网络/超时/DNS/非 2xx——失败不造假）。"""


def gate_url(url: str, whitelist: list) -> str:
    """权限模型白名单域闸（T05 教训）：先闸后网，白名单外 typed 拒。

    返回小写主机名；方案白名单外/域名白名单外/形态非法一律具名拒。
    """
    if not isinstance(url, str) or not url.startswith(WEB_URL_SCHEMES):
        raise NotConnected("web_url_scheme_not_allowed")
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        raise NotConnected("web_url_scheme_not_allowed")
    host = host.lower().rstrip(".")
    allowed = {str(w).strip().lower().rstrip(".") for w in whitelist
               if str(w).strip()}
    if host not in allowed:
        raise NotConnected("web_domain_not_whitelisted:" + host)
    return host


def _http_post_json(url: str, payload: dict, whitelist: list) -> tuple:
    """白名单闸→真实 POST JSON 往返；返回 (原始字节, 主机名)。"""
    host = gate_url(url, whitelist)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
            return response.read(), host
    except NotConnected:
        raise
    except urllib.error.HTTPError as exc:
        raise _FetchError("web_status_" + str(exc.code)) from None
    except Exception as exc:
        raise _FetchError("web_fetch_failed:" + type(exc).__name__) from None


def _http_get(url: str, whitelist: list) -> tuple:
    """白名单闸→真实 GET 取原文；返回 (原始字节, 主机名)。"""
    host = gate_url(url, whitelist)
    request = urllib.request.Request(
        url, method="GET", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
            return response.read(), host
    except NotConnected:
        raise
    except urllib.error.HTTPError as exc:
        raise _FetchError("web_status_" + str(exc.code)) from None
    except Exception as exc:
        raise _FetchError("web_fetch_failed:" + type(exc).__name__) from None


def _require_text(args: dict, key: str, code: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NotConnected(code)
    return value.strip()


def _named_gap_receipt(query: str, quote: str, chain: dict,
                       endpoint_host: str, network_calls: list,
                       reason: str) -> dict:
    """检索层失败：具名缺口收据，candidates/verified 恒空（零伪造）。"""
    return {
        "schema": WEB_FALLBACK_SCHEMA,
        "chain_position": "tail_of_F64_local_paid_web",
        "chain": {key: str(chain[key]).strip() for key in CHAIN_PROOF_KEYS},
        "query": query,
        "quote": quote,
        "search_endpoint_host": endpoint_host,
        "candidates": [],
        "verified": [],
        "gaps": [{"source_url": None, "title": None, "reason": reason}],
        "network_calls": network_calls,
        "note": "无网/未授权/响应非法＝具名缺口不造结果",
    }


def fallback_retrieve(config: dict, args: dict) -> dict:
    """F74 链末端段：检索→白名单闸→取回原文→sha256 绑定→引文逐字核验
    →W4-U41 web_verified 声明。失败路径全部具名入 gaps，零伪造。"""
    whitelist = config.get("web_allowed_domains")
    if (not isinstance(whitelist, list) or not whitelist
            or not all(isinstance(w, str) and w.strip() for w in whitelist)):
        raise NotConnected("web_whitelist_not_configured")
    query = _require_text(args, "query", "web_query_required")
    quote = _require_text(args, "quote", "web_quote_required")
    chain = args.get("chain")
    if (not isinstance(chain, dict)
            or any(not str(chain.get(key) or "").strip()
                   for key in CHAIN_PROOF_KEYS)):
        raise NotConnected("web_chain_prior_segments_not_declared")
    endpoint = str(config.get("web_search_endpoint") or "").strip()
    if not endpoint:
        raise NotConnected("web_search_endpoint_not_configured")
    # 检索端点同样过白名单闸（闸先于任何网络 I/O）。
    endpoint_host = gate_url(endpoint, whitelist)

    network_calls = [{"op": "search", "host": endpoint_host}]
    candidates = []
    verified = []
    gaps = []
    try:
        raw, _ = _http_post_json(endpoint, {"query": query}, whitelist)
    except NotConnected:
        raise
    except _FetchError as exc:
        return _named_gap_receipt(query, quote, chain, endpoint_host,
                                  network_calls, str(exc))
    try:
        search = json.loads(raw.decode("utf-8", "replace"))
        items = search["results"]
        if not isinstance(items, list):
            raise TypeError("results_not_list")
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError,
            KeyError, IndexError):
        return _named_gap_receipt(query, quote, chain, endpoint_host,
                                  network_calls, "web_search_response_invalid")

    # 结果 URL 逐字转录（零拼造）；白名单闸逐候选把关，闸外不取文。
    for item in items[:WEB_RESULT_CAP]:
        if not isinstance(item, dict):
            gaps.append({"source_url": None, "title": None,
                         "reason": "web_search_response_invalid"})
            continue
        title = item.get("title")
        url = str(item.get("url") or "").strip()
        if not url:
            gaps.append({"source_url": None, "title": title,
                         "reason": "web_result_url_missing"})
            continue
        candidates.append({"source_url": url, "title": title})
        try:
            host = gate_url(url, whitelist)
        except NotConnected as exc:
            gaps.append({"source_url": url, "title": title,
                         "reason": str(exc)})
            continue
        try:
            body, _ = _http_get(url, whitelist)
        except _FetchError as exc:
            gaps.append({"source_url": url, "title": title,
                         "reason": str(exc)})
            continue
        network_calls.append({"op": "fetch", "host": host})
        content_sha256 = hashlib.sha256(body).hexdigest()
        text = body.decode("utf-8", "replace")
        if quote not in text:
            gaps.append({"source_url": url, "title": title,
                         "reason": "web_quote_not_verified"})
            continue
        # 逐字核验过→W4-U41 同一分账声明（web-verified 永不冒数据库核验）。
        declaration = declare_web_verified({
            "source_url": url,
            "content_sha256": content_sha256,
            "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        })
        verified.append({
            "source_url": url,
            "title": title,
            "content_sha256": content_sha256,
            "content_bytes": len(body),
            "quote_verified": True,
            "declaration": declaration,
        })

    return {
        "schema": WEB_FALLBACK_SCHEMA,
        "chain_position": "tail_of_F64_local_paid_web",
        "chain": {key: str(chain[key]).strip() for key in CHAIN_PROOF_KEYS},
        "query": query,
        "quote": quote,
        "search_endpoint_host": endpoint_host,
        "candidates": candidates,
        "verified": verified,
        "gaps": gaps,
        "network_calls": network_calls,
        "note": "检索结果 URL 逐字转录＋取回原文 sha256 绑定＋引文逐字"
                "核验；只存 URL 不取原文的账面记录结构性不存在；失败具名"
                "不造结果（裁决#8-12 同频）",
    }


def web_fallback_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发（web.*）。未列方法绝不落到这里。"""
    if method == "web.fallback_retrieve":
        return fallback_retrieve(config, args)
    raise NotConnected("web_fallback_method_not_in_frozen_list:" + method)
