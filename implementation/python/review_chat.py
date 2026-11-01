# -*- coding: utf-8 -*-
"""F84 review 内嵌聊天产品面（工单 W2b-U48）。

06 F84 assertion：review聊天只读当前可见真实格和引用；改格必须走写权限。
本模块是**只读上下文装配＋模型轮次编排**，零写通道、零第二账本、零第二
材料真源：

  - 聊天上下文（review_chat_context）：tabular.read（列三元组：列名/值/
    世代/来源/支持状态/goldMatch，W2b-U05）× tabular.review_status（复核
    状态投影，W2b-U31）机械合并，另附当前支持戳内引用（citationText/
    status/verifiedScoped/quoteInArticle＋doc/page/textSha256 出处指针，
    经既有 harness.review_support_read 同源读取）。上下文**只含**当前可见
    格值＋引用＋复核状态——逐字段白名单投影；绝不携带原件文本/原件路径/
    身份映射（投影零字节；U40 C07 先例同源）。
  - 模型轮次（review_chat_ask）：唯一模型通道＝产品服务（OpenCode 2.0.28
    HTTP 面，e07_coordinator.service_client 同径）——总账 §3.1 裁决③：
    模型 = DeepSeek BYOK（key 已配入产品隔离配置，不入 git）。服务未配置
    ＝具名拒 review_chat_model_not_configured；transport typed 码原样上浮
    ；轮次超窗＝TURN_PENDING 如实回传——**绝不伪造回答**（不伪输出）。
  - 改格必须走写权限：本模块无任何写函数——人工改格走既有
    harness.review_batch_human_edit（F25 组）＋F92 行级权限面（W2b-U40
    已交付）；复核/重跑走 W2b-U31 面。聊天面零写通道（F84 红线即面即守
    ——与 oc28 补丁 014 审查面同一纪律：UI/聊天都不开第二写通道）。

金额纪律：本面不解释值语义（值原样投影；Decimal 对照在 tabular.read）。
未配置/未知方法 fail-closed exit 3 具名（legal_entry 纪律）。

桥·增强三式·式一/式二（2026-10-30 施工；唯一依据=竞品情报/2026-10-29-
规格波/律台-桥增强三式规格.md，行为级机制等量吸收律台 lawdesk 0.4.2 MIT，
零复制零文案进入）：
  - 式一 会话续接：同对话（review_batch×matter）+同模型通道+directory 未
    变+上一轮已收口（非 TURN_PENDING）→ 复用会话注册表里的 sessionId 直
    发 prompt（服务端会话本就持久）；任一守卫破→落式二携历史重开。会话 id
    以创建回执为准，桥侧不生成后假定成立。
  - 式二 换模型携历史：模型通道变更＝必然新会话（模型 create 时绑定不可中
    途换，opencodeAdapter.mjs:46-48 实测钉定）；新会话首 prompt 前置本对话
    历史 transcript（逐条【用户】/【助手】、只收 text 部件、尾部保留上限
    24000 字符+头部省略标注）；换轨事件 {sourceSessionId→newSessionId,原因}
    落注册表可审计；新轨首轮未成功收口前通道标记不更新（账面与实际不漂移）。
  - 变异纪律不变（opencode_http.py:3-5）：prompt 不自动重试；续接时遇会话
    已被清理（404/410 类确定结局）＝具名回传+携历史重开恰一次，不确定结局
    （transport_failure/5xx）原样上浮并标记轮次未知。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from bridge_errors import NotConnected

REVIEW_CHAT_FACE_NOTE = (
    "review-chat(W2b-U48): tabular.read(W2b-U05)"
    "+tabular.review_status(W2b-U31)"
    "+harness.review_support_read(W2b-U05)；模型通道=产品服务"
    "(opencode_http 2.0.28，裁决③ DeepSeek BYOK)；零写通道")

# legal_entry 冻结方法组（唯一方法：只读提问）。组外方法绝不落到本面。
REVIEW_CHAT_METHODS = frozenset({
    "review_chat.ask",
})

_ASK_ARGS_FIELDS = frozenset({
    "review_batch_id", "question", "scope",
})
# 式二（换模型携历史）：ask 可选携带 model={id,providerID} 切换通道；闭集
# 外字段仍一概拒（DTO 纪律不放松）。
_ASK_ARGS_OPTIONAL = frozenset({"model"})
# 上下文逐格白名单（F84 红线的机械形态：上下文只能由这些键组成）。
_CELL_CONTEXT_FIELDS = frozenset({
    "cellId", "columnName", "value", "cellGeneration", "cellSource",
    "supportStatus", "reviewStatus", "goldMatch", "goldMatchReason",
    "citations",
})
_CITATION_CONTEXT_FIELDS = frozenset({
    "citationText", "status", "verifiedScoped", "quoteInArticle",
    "doc", "page", "textSha256",
})
# 复核状态闭集（与 tabular.review_status 投影同集，W2b-U31）。
_REVIEW_STATUS_CLOSED = frozenset({
    "REVIEWED_CONFIRMED", "REVIEWED_REJECTED", "NOT_REVIEWED",
})
_TURN_WINDOW_SECONDS = 180.0

# 模型钉定（总账 §3.1 裁决③：模型 = DeepSeek BYOK，key 已配入产品隔离
# 配置）。会话创建必须显式带 model——缺省时服务回退 OpenCode 内建免费
# 档（provider.auth 拒），那不是裁决③的模型通道。
CHAT_MODEL = {"id": "deepseek-chat", "providerID": "deepseek-byok"}

# ---------------------------------------------------------------------- #
# 桥·增强三式·式一/式二：会话注册表 + 换轨 transcript（2026-10-30）。
# 注册表=对话作用域持久化 {sessionId, modelChannel, directory} 三元组＋
# 历史 rows（text 部件投影）＋换轨事件；ask 时先查表再决定续接/携历史重开。
# ---------------------------------------------------------------------- #

_REGISTRY_SCHEMA = "review-chat-sessions/1"
# transcript 尾部保留上限（规格 §式二：对齐律台 24000 字符量级的施工常量）。
_TRANSCRIPT_CHAR_LIMIT = 24000
_TRANSCRIPT_OMISSION_HEAD = "〔更早的对话内容已省略〕"
_HISTORY_ROLES = frozenset({"user", "assistant"})
_SWITCH_REASONS = frozenset({
    "model_channel_changed", "directory_changed", "turn_pending",
    "session_invalid",
})
_SESSION_GONE_CODES = frozenset({"http_404", "http_410"})
# 探明不可写的注册表根（一次性降级：后续 ask 不再反复撞同一堵墙，行为回落
# 为无续接的逐问新会话——不中断聊天主链）。
_REGISTRY_UNWRITABLE: set = set()


def _registry_file(config: dict):
    """注册表落点：review_chat_state_root 优先，回落 harness_state_root
    （宿主既有状态根同源）；两者皆缺＝None（不持久化）。"""
    root = config.get("review_chat_state_root") \
        or config.get("harness_state_root")
    if not root:
        return None
    return Path(root) / "review-chat-sessions" / "sessions.json"


def _empty_registry() -> dict:
    return {"schema": _REGISTRY_SCHEMA, "conversations": {}}


def _load_registry(config: dict) -> dict:
    path = _registry_file(config)
    if path is None or not path.exists():
        return _empty_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        # 注册表坏了＝fail-closed 具名拒（不静默重建丢账、不带着坏账续接）。
        raise NotConnected("review_chat_registry_unreadable") from None
    if not isinstance(data, dict) or data.get("schema") != _REGISTRY_SCHEMA \
            or not isinstance(data.get("conversations"), dict):
        raise NotConnected("review_chat_registry_invalid")
    # 文件读取边界守卫：逐对话条目结构校验（坏账不带病续接）。
    allowed = {"sessionId", "modelChannel", "directory", "turnState",
               "history", "switchEvents"}
    for entry in data["conversations"].values():
        if not isinstance(entry, dict) or not set(entry) <= allowed \
                or not isinstance(entry.get("sessionId"), str) \
                or not isinstance(entry.get("modelChannel"), dict) \
                or not isinstance(entry.get("directory"), str) \
                or entry.get("turnState") not in ("IDLE", "PENDING") \
                or not isinstance(entry.get("history"), list) \
                or not isinstance(entry.get("switchEvents"), list) \
                or not all(isinstance(row, dict)
                           and row.get("role") in _HISTORY_ROLES
                           and isinstance(row.get("text"), str)
                           for row in entry["history"]):
            raise NotConnected("review_chat_registry_invalid")
    return data


def _save_registry(config: dict, registry: dict) -> bool:
    """原子写（tmp+os.replace，run_cursor_store 同法）。根不可写＝一次性
    降级返回 False（续接停用，聊天主链照常）。"""
    path = _registry_file(config)
    if path is None or str(path.parent) in _REGISTRY_UNWRITABLE:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(registry, ensure_ascii=False, sort_keys=True),
            encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        _REGISTRY_UNWRITABLE.add(str(path.parent))
        return False
    return True


def _conversation_key(args: dict, matter_id: str) -> str:
    """对话作用域键：审查批次 × 事项（同键才谈得上续接）。"""
    return str(args["review_batch_id"]) + "|" + matter_id


def _transcript_text(history: list) -> str:
    """历史 rows → transcript 文本：逐条【用户】/【助手】标记（rows 本就只
    收 text 部件——工具噪音不入；无附件字节，材料不出域红线）；超限保尾部
    ＋头部省略标注（规格 §式二）。"""
    lines = ["【{}】{}".format(
        "用户" if row.get("role") == "user" else "助手", row.get("text") or "")
        for row in history]
    text = "\n".join(lines)
    if len(text) <= _TRANSCRIPT_CHAR_LIMIT:
        return text
    kept: list = []
    total = 0
    for line in reversed(lines):
        if kept and total + len(line) + 1 > _TRANSCRIPT_CHAR_LIMIT:
            break
        kept.append(line)
        total += len(line) + 1
    return _TRANSCRIPT_OMISSION_HEAD + "\n" + "\n".join(reversed(kept))


def _harness_call(method: str, args: dict, config: dict) -> dict:
    """harness 公开面分派 seam（默认=legal_entry.call 同进程径；selfhost
    侧 PG 直连部署由调用方替换本 seam——同 U05/U31 先例）。"""
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
        raise NotConnected("review_chat_scope_invalid")
    return scope


# ---------------------------------------------------------------------- #
# 聊天上下文：tabular.read × review_status × 支持戳引用（只读白名单投影）
# ---------------------------------------------------------------------- #


def _citations_of(support_index: dict, row_id: str, cell_id: str) -> list:
    """当前支持戳（末条目）内的引用逐条白名单投影；无戳＝空表。出处仅
    指针（doc/page/textSha256），绝不携带页文本/原件字节。"""
    entries = support_index.get((row_id, cell_id)) or []
    if not entries:
        return []
    record = entries[-1].get("record") or {}
    if record.get("entryKind") == "invalidation":
        return []
    provenance = record.get("provenance") or {}
    out = []
    for citation in record.get("citations", []):
        out.append({
            "citationText": citation.get("citationText"),
            "status": citation.get("status"),
            "verifiedScoped": citation.get("verifiedScoped"),
            "quoteInArticle": citation.get("quoteInArticle"),
            "doc": provenance.get("doc"),
            "page": provenance.get("page"),
            "textSha256": provenance.get("textSha256"),
        })
    return out


def _review_status_index(status_doc: dict) -> dict:
    """复核状态投影 → {(rowId, cellId): reviewStatus}。闭集外值具名拒。"""
    index = {}
    for projection in status_doc.get("projections", []):
        status = projection.get("reviewStatus")
        if status not in _REVIEW_STATUS_CLOSED:
            raise NotConnected("review_chat_status_invalid:" + str(status))
        index[(projection.get("rowId"), projection.get("cellId"))] = status
    return index


def review_chat_context(args: dict, config: dict) -> dict:
    """当前可见真实格＋引用＋复核状态的只读合并投影（F84 上下文闭集）。"""
    _require(args, frozenset({"review_batch_id", "scope"}),
             "review_chat_context_args_invalid")
    scope = _scope_of(args)
    batch_id = args.get("review_batch_id")
    if not isinstance(batch_id, str) or not batch_id:
        raise NotConnected("review_chat_batch_id_required")
    read = _harness_call("tabular.read",
                         {"review_batch_id": batch_id, "scope": scope},
                         config)
    status = _harness_call("tabular.review_status",
                           {"review_batch_id": batch_id, "scope": scope},
                           config)
    support = _harness_call("harness.review_support_read",
                            {"scope": scope, "batch_id": batch_id}, config)
    support_index = {}
    for key, entries in (support.get("entries") or {}).items():
        row_id, _, cell_id = key.rpartition(":")
        support_index[(row_id, cell_id)] = entries
    status_index = _review_status_index(status)
    rows_out = []
    for row in read.get("rows", []):
        cells_out = []
        for cell in row.get("cells", []):
            key = (row.get("rowId"), cell.get("columnId"))
            if key not in status_index:
                raise NotConnected(
                    "review_chat_status_missing:%s:%s" % key)
            projection = {
                "cellId": cell.get("columnId"),
                "columnName": cell.get("columnName"),
                "value": cell.get("value"),
                "cellGeneration": cell.get("cellGeneration"),
                "cellSource": cell.get("cellSource"),
                "supportStatus": cell.get("supportStatus"),
                "reviewStatus": status_index[key],
                "goldMatch": cell.get("goldMatch"),
                "goldMatchReason": cell.get("goldMatchReason"),
                "citations": _citations_of(support_index,
                                           key[0], key[1]),
            }
            if set(projection) - _CELL_CONTEXT_FIELDS:
                raise NotConnected("review_chat_context_leak")
            for citation in projection["citations"]:
                if set(citation) - _CITATION_CONTEXT_FIELDS:
                    raise NotConnected("review_chat_citation_leak")
            cells_out.append(projection)
        rows_out.append({"rowId": row.get("rowId"),
                         "rowState": row.get("rowState"),
                         "cells": cells_out})
    return {
        "reviewBatchId": read.get("reviewBatchId"),
        "batchStatus": read.get("batchStatus"),
        "columns": [
            {"id": column.get("id"), "name": column.get("name")}
            for column in read.get("columns", [])
        ],
        "rows": rows_out,
        "readOnly": True,
        "note": "聊天上下文只含当前可见格值＋引用＋复核状态；改格必须走"
                "写权限（harness.review_batch_human_edit＋F92 行级权限面）"
                "——本面零写通道",
        "face": REVIEW_CHAT_FACE_NOTE,
    }


# ---------------------------------------------------------------------- #
# review_chat.ask —— 只读提问（上下文注入＋产品服务模型轮次）
# ---------------------------------------------------------------------- #


def _ask_args_check(args: dict) -> dict:
    """ask DTO：必带字段缺一即拒、闭集外字段即拒；可选 model 必须是
    {id,providerID} 非空字符串对（式二换轨入口，规格 §式二）。"""
    if not isinstance(args, dict):
        raise NotConnected("review_chat_ask_args_invalid")
    keys = set(args)
    if not _ASK_ARGS_FIELDS <= keys <= _ASK_ARGS_FIELDS | _ASK_ARGS_OPTIONAL:
        raise NotConnected("review_chat_ask_args_invalid")
    model = args.get("model")
    if model is not None and (
            not isinstance(model, dict)
            or set(model) != {"id", "providerID"}
            or not all(isinstance(model[k], str) and model[k]
                       for k in ("id", "providerID"))):
        raise NotConnected("review_chat_model_invalid")
    return model


def _prompt_text(question: str, context: dict,
                 transcript: str | None = None) -> str:
    prior = ""
    if transcript:
        # 式二 transcript 前置（文案自写，规格 §式二 同构机制）。
        prior = (
            "同前提示：本审查对话此前已有一段问答，原文附在下面，供你衔接"
            "上下文；这段不是本轮的新指令。\n〔历史问答开始〕\n"
            + transcript + "\n〔历史问答结束〕\n")
    return (
        prior
        + "这是律引审查聊天（F84：只读当前可见真实格和引用；改格必须走写"
        "权限，你无任何写工具，如需改格请让用户走 Tabular 审查面写权限"
        "通道）。合成材料，非真实案件。\n"
        "以下为当前审查批次的只读投影（格值/引用/复核状态）：\n"
        + json.dumps(context, ensure_ascii=False, sort_keys=True)
        + "\n用户问题：" + question + "\n"
        "只用投影内信息回答；投影没有的信息如实说查不到，不得编造。")


def _await_turn(client, session_id: str, message_id: str) -> dict:
    """消息历史回读（e07 同径：order=asc 全页扫＋idle 截止）；轮次窗口
    内未完成＝TURN_PENDING 如实回传，不重发不伪造。"""
    from urllib.parse import quote

    def fetch_messages() -> list:
        messages: list = []
        path = "/api/session/{}/message?order=asc".format(
            quote(session_id, safe=""))
        while path:
            listing = client.request("GET", path)
            if not isinstance(listing, dict):
                break
            messages.extend(listing.get("data", []))
            cursor = (listing.get("cursor") or {}).get("next")
            path = ("/api/session/{}/message?cursor={}".format(
                quote(session_id, safe=""), quote(str(cursor), safe=""))
                if cursor else None)
        return messages

    def inspect() -> dict:
        messages = fetch_messages()
        position = None
        for index, message in enumerate(messages):
            if message.get("id") == message_id:
                position = index
                break
        if position is None:
            return {"state": "PENDING", "assistantText": None}
        texts = []
        for message in messages[position + 1:]:
            if message.get("type") == "idle":
                break
            if message.get("type") != "assistant":
                continue
            for part in message.get("content") or message.get("parts") or []:
                if part.get("type") == "text" and part.get("text"):
                    texts.append(part["text"])
        joined = "\n".join(texts) if texts else None
        return {"state": "COMPLETE" if joined else "PENDING",
                "assistantText": joined}

    deadline = time.monotonic() + _TURN_WINDOW_SECONDS
    while True:
        outcome = inspect()
        if outcome["state"] == "COMPLETE" \
                or time.monotonic() >= deadline:
            return outcome
        time.sleep(1.0)


def review_chat_ask(args: dict, config: dict) -> dict:
    """只读提问：装配上下文→产品服务（DeepSeek BYOK，裁决③）一轮→回
    答原样回传。模型未配置＝具名拒；超窗＝TURN_PENDING——绝不伪造。

    式一/式二（2026-10-30）：先查会话注册表——同对话+同通道+directory 未
    变+上轮已收口→复用 sessionId 直发 prompt；任一破（通道变更/上轮未收
    口/会话已被清理）＝携历史 transcript 重开新会话并落换轨事件。"""
    model_arg = _ask_args_check(args)
    question = args.get("question")
    if not isinstance(question, str) or not question.strip():
        raise NotConnected("review_chat_question_required")
    channel = dict(model_arg) if model_arg else dict(CHAT_MODEL)
    # F30 airplane gate (W3-U05)：armed 且 chat provider 未声明本地＝在装配
    # 上下文/创建会话之前具名拒（airplane_remote_model_blocked）——不发任
    # 何连接；未 armed 时行为与现状逐字节相同（按实际通道 provider 判）。
    from airplane_mode import enforce_bridge_egress
    enforce_bridge_egress(config, "model_round_remote",
                          provider_id=str(channel.get("providerID") or ""))
    context = review_chat_context({
        "review_batch_id": args["review_batch_id"],
        "scope": args["scope"]}, config)
    # 模型通道＝产品服务（唯一；key 在产品隔离配置，不入桥配置不入 git）。
    from e07_coordinator import create_public_session, service_client
    from opencode_http import TransportError
    try:
        client = service_client(config)
    except NotConnected:
        raise NotConnected("review_chat_model_not_configured") from None
    matter_id = str(args["scope"]["matterId"])
    conv_key = _conversation_key(args, matter_id)
    registry = _load_registry(config)
    entry = registry["conversations"].get(conv_key)

    # 式一续接守卫（规格 §式一，律台三守卫同构+一条）：表内有 sessionId ∧
    # 模型通道未变 ∧ directory 未变 ∧ 该会话无运行中轮次。
    switch_reason = None
    if entry is not None:
        if entry.get("modelChannel") != channel:
            switch_reason = "model_channel_changed"
        elif entry.get("directory") != matter_id:
            switch_reason = "directory_changed"
        elif entry.get("turnState") == "PENDING":
            switch_reason = "turn_pending"
    history = list(entry.get("history") or []) if entry else []
    events = list(entry.get("switchEvents") or []) if entry else []
    resumed = False
    reopened_after = None
    transcript = None
    if entry is not None and switch_reason is None:
        # 续接：复用注册表 sessionId 直发 prompt（服务端会话本就持久，
        # opencode_http.py:86-92；id 权威＝当初创建回执，桥侧不臆造）。
        session_id = entry["sessionId"]
        message_id = "msg_f84chat_" + uuid.uuid4().hex[:12]
        try:
            client.prompt(session_id, {
                "id": message_id,
                "text": _prompt_text(question, context)})
            resumed = True
        except TransportError as exc:
            if exc.uncertain or exc.code not in _SESSION_GONE_CODES:
                # 变异纪律（opencode_http.py:3-5）：不确定结局不自动重试，
                # typed 码原样上浮；轮次标 PENDING（下轮不续接这条未知账）。
                entry["turnState"] = "PENDING"
                _save_registry(config, registry)
                raise
            # 会话已被服务端清理（确定结局 404/410）＝具名回传＋落式二携
            # 历史重开恰一次（不无限重试）。
            reopened_after = "session_invalid:" + exc.code
            switch_reason = "session_invalid"
    if not resumed:
        # 新会话（式二）：首问/守卫破/会话失效；有历史则 transcript 前置
        # （模型 create 时绑定，通道变＝必然新会话）。
        transcript = _transcript_text(history) if history else None
        session_id = ("ses_f84chat_" + str(int(time.time())) + "-"
                      + uuid.uuid4().hex[:8])
        created = create_public_session({
            "id": session_id,
            "title": "律引审查聊天（F84 合成）",
            "model": dict(channel),
        }, config)
        created_value = (created.get("data", created) if isinstance(created, dict)
                         else {}) or {}
        if created_value.get("id") != session_id:
            raise NotConnected("review_chat_session_invalid")
        message_id = "msg_f84chat_" + uuid.uuid4().hex[:12]
        try:
            client.prompt(session_id, {
                "id": message_id,
                "text": _prompt_text(question, context, transcript)})
        except TransportError:
            # 新会话首 prompt 失败：不自动重试；通道标记不更新（式二机制 4
            # ——换轨失败账面仍绑旧通道），旧会话轮次标 PENDING 防漂移。
            if entry is not None:
                entry["turnState"] = "PENDING"
                _save_registry(config, registry)
            raise
        if entry is not None and switch_reason is not None:
            # 换轨留痕（规格 §式二）：sourceSessionId→newSessionId+原因，
            # 落注册表可审计，不静默。
            events.append({
                "sourceSessionId": entry.get("sessionId"),
                "newSessionId": session_id,
                "reason": switch_reason,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })

    # prompt 已落地：先落账（用户行入 history、轮次 PENDING）——后续回读
    # 途中任何失败都不丢已落地变异的账面。
    history.append({"role": "user", "text": question})
    registry["conversations"][conv_key] = {
        "sessionId": session_id,
        "modelChannel": channel,
        "directory": matter_id,
        "turnState": "PENDING",
        "history": history,
        "switchEvents": events,
    }
    persisted = _save_registry(config, registry)
    outcome = _await_turn(client, session_id, message_id)
    if outcome["state"] == "COMPLETE":
        history.append({"role": "assistant",
                        "text": outcome.get("assistantText")})
        registry["conversations"][conv_key]["turnState"] = "IDLE"
        persisted = _save_registry(config, registry)
    answer = {
        "reviewBatchId": context["reviewBatchId"],
        "question": question,
        "context": context,
        "sessionRef": session_id,
        "messageId": message_id,
        "readOnly": True,
        "model": ("product-service(%s/%s，裁决③)" % (
            channel["providerID"], channel["id"]) if channel == CHAT_MODEL
            else "product-service(%s/%s)" % (
            channel["providerID"], channel["id"])),
        "continuity": {
            "resumed": resumed,
            "transcriptPrefix": bool(transcript),
            "switchReason": switch_reason,
            "reopenedAfter": reopened_after,
            "persisted": persisted,
        },
        "face": REVIEW_CHAT_FACE_NOTE,
    }
    if outcome["state"] == "COMPLETE":
        answer["reply"] = outcome.get("assistantText")
        return answer
    # 已入队未完成（窗口内无回答）＝如实具名；不等待伪造、不自动重发。
    answer["reply"] = None
    answer["state"] = "TURN_PENDING"
    answer["note"] = ("模型轮次已入队未完成（%ds 窗）——如实回传，不伪造"
                      "回答；重提问须新轮次（新 message id）"
                      % int(_TURN_WINDOW_SECONDS))
    return answer


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（review_chat.*）
# ---------------------------------------------------------------------- #


def review_chat_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发。未列方法绝不落到这里。"""
    if method == "review_chat.ask":
        return review_chat_ask(args, config)
    raise NotConnected("review_chat_method_not_connected:" + method)
