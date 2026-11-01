"""F84 产品侧接线测试（W2b-U48）：review 内嵌聊天——只读投影提问。

全部合成材料。legal_entry 新增 REVIEW_CHAT_METHODS（唯一方法
review_chat.ask，产品面 review_chat），桥与产品面经 seam 注入单测（零仓
依赖；真全链实跑对账在 tools/PENDING_OWNER_f84_review_chat_recon.py）。

权威断言（06 F84：review聊天只读当前可见真实格和引用；改格必须走写权
限）在本测试的机械形态：
  - 上下文闭集：tabular.read×review_status 合并投影＋支持戳引用，逐格
    白名单键（值/引用/复核状态）；白名单外键具名拒（绝不携带原件/身份
    映射——合成 marker 扫描上下文全文）；
  - 零写通道：review_chat.py 源 AST 级不含任何 harness 写方法名（人工
    改格唯一通道=F25 review_batch_human_edit＋F92 行级权限面；复核/重
    跑=W2b-U31 面），方法组封闭（伪造写方法不注册）；
  - 模型不可用具名不伪输出：产品服务未配置＝review_chat_model_
    not_configured 具名拒；回答永远来自产品服务轮次回读（单测用假
    service_client 注入），绝不本地伪造成功回答；
  - fail-closed：DTO 闭集外字段/未知方法/未配置桥＝NOT_CONNECTED。
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import review_chat  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
    # 模型通道单测一律不配 opencode_registration——未配置路径全桥可测。
}
SCOPE = {"kind": "matter", "matterId": "m-f84chat"}
BATCH = "brt-f84chat"


def tabular_read_doc() -> dict:
    """合成 tabular.read 投影（同 W2b-U05 面形：列三元组＋支持状态）。"""
    return {
        "reviewBatchId": BATCH,
        "batchStatus": "active",
        "columnContractDefined": True,
        "columns": [
            {"id": "amount", "name": "合同金额"},
            {"id": "cited", "name": "法律依据"},
        ],
        "rows": [
            {"rowId": "row-1", "rowState": "done", "cells": [
                {"columnId": "amount", "columnName": "合同金额",
                 "gold": {"kind": "number", "expect": "123456.78"},
                 "value": "123,456.78 元", "cellGeneration": 0,
                 "cellSource": "machine",
                 "supportStatus": "SUPPORTED_CITATION_LEVEL",
                 "goldMatch": True, "goldMatchReason": None},
                {"columnId": "cited", "columnName": "法律依据",
                 "gold": {"kind": "text"}, "value": "《合成数据安全法》第七条",
                 "cellGeneration": 0, "cellSource": "machine",
                 "supportStatus": "NO_STAMP",
                 "goldMatch": None, "goldMatchReason": "type_only_gold"},
            ]},
        ],
        "supportCounts": {},
        "accounting": "per_cell_scoped",
        "note": "synthetic",
        "face": "synthetic",
    }


def review_status_doc() -> dict:
    return {
        "batchId": BATCH,
        "projections": [
            {"rowId": "row-1", "cellId": "amount",
             "reviewStatus": "REVIEWED_CONFIRMED", "entryCount": 1},
            {"rowId": "row-1", "cellId": "cited",
             "reviewStatus": "NOT_REVIEWED", "entryCount": 0},
        ],
        "counts": {"REVIEWED_CONFIRMED": 1, "NOT_REVIEWED": 1},
        "face": "synthetic",
    }


def support_read_doc() -> dict:
    """合成支持账回读（entries 键=rowId:cellId；戳内引用＋出处指针）。"""
    return {
        "batchId": BATCH,
        "entries": {
            "row-1:amount": [{
                "seq": 1, "entryKind": "stamp",
                "record": {
                    "gate": {"gateStatus": "CITATION_VERIFIED",
                             "asOf": "2026-10-17T00:00:00Z",
                             "runSeq": 1,
                             "extractionBatchId": "ext-f84",
                             "candidateId": "cand-1"},
                    "citations": [{
                        "citationText": "《合成数据安全法》第七条",
                        "status": "current_verified",
                        "verifiedScoped": True,
                        "quoteInArticle": "第七条（合成条文）",
                    }],
                    "provenance": {"source": "material_extraction",
                                   "doc": "doc-synth-1", "page": 3,
                                   "textSha256": "ab" * 32},
                },
            }],
        },
        "counts": {},
        "face": "synthetic",
    }


def patch_projections(testcase, read=None, status=None, support=None):
    """注入三投影 seam（patch review_chat._harness_call；调用账留证）。"""
    read = read if read is not None else tabular_read_doc()
    status = status if status is not None else review_status_doc()
    support = support if support is not None else support_read_doc()
    calls = []

    def _fake(method, args, config):
        calls.append(method)
        return {"tabular.read": read,
                "tabular.review_status": status,
                "harness.review_support_read": support}[method]

    patcher = unittest.mock.patch.object(review_chat, "_harness_call", _fake)
    patcher.start()
    testcase.addCleanup(patcher.stop)
    return calls


def fake_service_client(testcase, *, assistant_reply: str | None = (
        "合成回答：值为 123,456.78 元"), calls: list | None = None):
    """假产品服务客户端（唯一模型通道的 transport 替身；合成材料）。

    review_chat 在调用点 ``from e07_coordinator import service_client``——
    替身必须钉在 e07_coordinator 模块属性上（函数内 import 每次重绑）。
    assistant_reply=None ＝模型轮次永远不出文本（TURN_PENDING 径）。
    """
    import e07_coordinator
    messages: list = []

    class FakeClient:
        def request(self, method, path):
            if calls is not None:
                calls.append(method + " " + path)
            return {"data": list(messages), "cursor": None}

        def prompt(self, sid, request):
            if calls is not None:
                calls.append("PROMPT " + sid + " " + request["text"][:48])
            messages.append({"id": request["id"], "type": "user"})
            if assistant_reply is not None:
                messages.append({"id": "asst-1", "type": "assistant",
                                 "content": [{"type": "text",
                                              "text": assistant_reply}]})
                messages.append({"id": "idle-1", "type": "idle"})

    client = FakeClient()
    patcher = unittest.mock.patch.object(e07_coordinator, "service_client",
                                         lambda config: client)
    patcher.start()
    testcase.addCleanup(patcher.stop)
    # create_public_session 一并替身（会话创建属产品服务径；本测试钉：
    # ask 走 create_public_session 同一入口）。
    session_calls = []

    def _fake_session(payload, config):
        session_calls.append(payload)
        return {"data": {"id": payload["id"], "title": payload["title"]}}

    session_patcher = unittest.mock.patch.object(
        e07_coordinator, "create_public_session", _fake_session)
    session_patcher.start()
    testcase.addCleanup(session_patcher.stop)
    return client, session_calls


class MethodGroupTests(unittest.TestCase):
    def test_frozen_group_membership(self) -> None:
        self.assertEqual(frozenset({"review_chat.ask"}),
                         legal_entry.REVIEW_CHAT_METHODS)
        self.assertEqual(frozenset({"review_chat.ask"}),
                         review_chat.REVIEW_CHAT_METHODS)

    def test_forged_write_methods_never_registered(self) -> None:
        for forged in ("review_chat.edit", "review_chat.write",
                       "review_chat.human_edit", "review_chat.commit_cell"):
            self.assertNotIn(forged, legal_entry.REVIEW_CHAT_METHODS)

    def test_no_second_write_channel_in_source(self) -> None:
        """AST 级：聊天面源码零写通道（F84 红线即面即守）。"""
        source = (ROOT / "python" / "review_chat.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                called.add(node.value)
        for write_method in (
                "harness.review_batch_human_edit",
                "harness.review_receipt_record",
                "harness.review_cell_rerun",
                "harness.review_batch_claim",
                "harness.review_batch_submit",
                "tabular.review_receipt", "tabular.cell_rerun",
                "tabular.support_stamp", "tabular.invalidate"):
            self.assertNotIn(write_method, called)
        # 唯一 harness 读调用＝tabular.read×review_status＋support_read。
        for read_method in ("tabular.read", "tabular.review_status",
                            "harness.review_support_read"):
            self.assertIn(read_method, called)


class ContextProjectionTests(unittest.TestCase):
    def test_context_merged_whitelist_projection(self) -> None:
        calls = patch_projections(self)
        context = review_chat.review_chat_context(
            {"review_batch_id": BATCH, "scope": SCOPE}, CONFIG)
        # 三投影同源读取（read×status×support），无第四调用。
        self.assertEqual(calls, ["tabular.read", "tabular.review_status",
                                 "harness.review_support_read"])
        self.assertTrue(context["readOnly"])
        self.assertEqual(context["reviewBatchId"], BATCH)
        cells = context["rows"][0]["cells"]
        self.assertEqual(
            [set(cell) for cell in cells],
            [set(review_chat._CELL_CONTEXT_FIELDS)] * 2)
        amount = cells[0]
        self.assertEqual(amount["value"], "123,456.78 元")
        self.assertEqual(amount["reviewStatus"], "REVIEWED_CONFIRMED")
        self.assertEqual(amount["supportStatus"],
                         "SUPPORTED_CITATION_LEVEL")
        self.assertTrue(amount["goldMatch"])
        self.assertEqual(amount["citations"][0]["citationText"],
                         "《合成数据安全法》第七条")
        self.assertEqual(amount["citations"][0]["doc"], "doc-synth-1")
        self.assertEqual(amount["citations"][0]["page"], 3)
        cited = cells[1]
        self.assertEqual(cited["reviewStatus"], "NOT_REVIEWED")
        self.assertEqual(cited["citations"], [])

    def test_context_never_carries_originals_or_identity_mapping(self) -> None:
        """合成 marker 扫描：上下文全文不含原件路径/页文本/身份映射键。"""
        read = tabular_read_doc()
        # 投影源里故意埋入越界形态（模拟桥面可能漂移的输入）：支持账里
        # 塞 originalPath/页文本——上下文白名单必须把它们滤掉。
        support = support_read_doc()
        record = support["entries"]["row-1:amount"][0]["record"]
        record["provenance"]["originalPath"] = "X:/synth/original.pdf"
        record["provenance"]["pageText"] = "SYNTH_ORIGINAL_PAGE_MARKER"
        record["identityMapping"] = {"actor": "lawyer-1",
                                     "realName": "SYNTH_IDENTITY_MARKER"}
        patch_projections(self, read=read, support=support)
        context = review_chat.review_chat_context(
            {"review_batch_id": BATCH, "scope": SCOPE}, CONFIG)
        text = json.dumps(context, ensure_ascii=False)
        for marker in ("originalPath", "pageText", "identityMapping",
                       "SYNTH_ORIGINAL_PAGE_MARKER", "SYNTH_IDENTITY_MARKER"):
            self.assertNotIn(marker, text)
        self.assertEqual(
            set(context["rows"][0]["cells"][0]["citations"][0]),
            set(review_chat._CITATION_CONTEXT_FIELDS))

    def test_context_rejects_unknown_review_status(self) -> None:
        status = review_status_doc()
        status["projections"][0]["reviewStatus"] = "REVIEWED_AUTOSIGNED"
        patch_projections(self, status=status)
        with self.assertRaises(NotConnected) as caught:
            review_chat.review_chat_context(
                {"review_batch_id": BATCH, "scope": SCOPE}, CONFIG)
        self.assertIn("review_chat_status_invalid", str(caught.exception))

    def test_context_requires_full_status_coverage(self) -> None:
        status = review_status_doc()
        status["projections"] = status["projections"][:1]
        patch_projections(self, status=status)
        with self.assertRaises(NotConnected) as caught:
            review_chat.review_chat_context(
                {"review_batch_id": BATCH, "scope": SCOPE}, CONFIG)
        self.assertIn("review_chat_status_missing", str(caught.exception))

    def test_context_dto_closed_set(self) -> None:
        patch_projections(self)
        for bad in ({"review_batch_id": BATCH, "scope": SCOPE,
                     "row_filter": "row-1"},
                    {"scope": SCOPE},
                    {"review_batch_id": "", "scope": SCOPE}):
            with self.assertRaises(NotConnected):
                review_chat.review_chat_context(bad, CONFIG)
        with self.assertRaises(NotConnected):
            review_chat.review_chat_context(
                {"review_batch_id": BATCH,
                 "scope": {"kind": "matter", "matterId": ""}}, CONFIG)


class AskTurnTests(unittest.TestCase):
    def ask(self, testcase, **service_kwargs):
        patch_projections(testcase)
        return fake_service_client(testcase, **service_kwargs)

    def test_model_unconfigured_named_not_fabricated(self) -> None:
        """模型不可用＝具名拒（不伪输出）：桥配置无 opencode 通道即拒。"""
        patch_projections(self)
        with self.assertRaises(NotConnected) as caught:
            review_chat.review_chat_ask(
                {"review_batch_id": BATCH, "scope": SCOPE,
                 "question": "第一行的合同金额是多少？"}, CONFIG)
        self.assertIn("review_chat_model_not_configured",
                      str(caught.exception))

    def test_unconfigured_bridge_fail_closed(self) -> None:
        # 桥面全未配置（无 harness 键无 opencode 键）＝harness 读先具名拒
        # （fail-closed 链第一环），绝不空响应冒成功。
        with self.assertRaises(NotConnected):
            legal_entry.call("review_chat.ask",
                             {"review_batch_id": BATCH, "scope": SCOPE,
                              "question": "问题"}, {})

    def test_dispatch_through_frozen_group(self) -> None:
        """legal_entry 冻结组分发＋产品服务轮次（全链同进程径）。"""
        _, session_calls = self.ask(self)
        result = legal_entry.call(
            "review_chat.ask",
            {"review_batch_id": BATCH, "scope": SCOPE,
             "question": "row-1 的合同金额是多少？"}, CONFIG)
        self.assertEqual(len(session_calls), 1)
        self.assertEqual(result["reply"], "合成回答：值为 123,456.78 元")
        self.assertTrue(result["readOnly"])

    def test_unknown_method_fail_closed(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("review_chat.edit", {}, CONFIG)
        self.assertIn("method_not_connected:review_chat.edit",
                      str(caught.exception))

    def test_ask_rides_product_service_turn(self) -> None:
        """回答来自产品服务轮次回读；prompt 携带只读上下文＋问题。"""
        _, session_calls = self.ask(self)
        result = review_chat.review_chat_ask(
            {"review_batch_id": BATCH, "scope": SCOPE,
             "question": "row-1 的合同金额是多少？依据是什么？"}, CONFIG)
        self.assertEqual(len(session_calls), 1)
        self.assertTrue(session_calls[0]["id"].startswith("ses_f84chat_"))
        self.assertEqual(result["reply"],
                         "合成回答：值为 123,456.78 元")
        self.assertTrue(result["readOnly"])
        self.assertEqual(result["reviewBatchId"], BATCH)
        # 随轮回传的上下文＝装配的同一份白名单投影（回执可审计）。
        self.assertEqual(result["context"]["rows"][0]["cells"][0]["value"],
                         "123,456.78 元")

    def test_ask_dto_closed_set(self) -> None:
        self.ask(self)
        for bad in ({"review_batch_id": BATCH, "scope": SCOPE},
                    {"review_batch_id": BATCH, "scope": SCOPE,
                     "question": "问题", "row_id": "row-1"},
                    {"review_batch_id": BATCH, "scope": SCOPE,
                     "question": "   "}):
            with self.assertRaises(NotConnected):
                review_chat.review_chat_ask(bad, CONFIG)

    def test_turn_pending_reported_honestly(self) -> None:
        """轮次未完成＝TURN_PENDING 如实回传（reply=None 不伪造）。"""
        self.ask(self, assistant_reply=None)  # 模型轮次永不出文本
        with unittest.mock.patch.object(review_chat, "_TURN_WINDOW_SECONDS",
                                        0.0):
            result = review_chat.review_chat_ask(
                {"review_batch_id": BATCH, "scope": SCOPE,
                 "question": "慢问题"}, CONFIG)
        self.assertIsNone(result["reply"])
        self.assertEqual(result["state"], "TURN_PENDING")
        self.assertIn("不伪造", result["note"])


if __name__ == "__main__":
    unittest.main()
