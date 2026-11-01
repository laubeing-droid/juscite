# -*- coding: utf-8 -*-
"""桥·增强三式·式一/式二 合成自测（2026-10-30）。

唯一依据=竞品情报/2026-10-29-规格波/律台-桥增强三式规格.md §式一/§式二
验收断言（全部合成材料，假 service_client/create_public_session 注入，
零仓依赖零真实模型轮次）：

  式一 ①同通道两连问→第二问复用同一 sessionId（零新建）；
       ②会话已被删（404 类确定结局）→具名回传且携历史重开恰一次；
       ③上轮未收口（TURN_PENDING）→不续接，携历史重开（reason=turn_pending）。
  式二 ①A 通道两轮后切 B 通道→新 sessionId 且首 prompt 含前两轮文本；
       ②超限截尾保尾部+头部省略标注；transcript 只收 text 部件（工具噪音
       不入）；无附件字节（本面结构无附件输入）；
       ③换轨事件 {sourceSessionId→newSessionId,原因} 落注册表；
       ④B 通道首轮失败→通道标记不变（账面与实际不漂移）。

守卫补验：directory 变更守卫（注册表文件边界白盒）；无可用状态根＝逐问新
会话（续接停用不害主链）；ask 可选 model DTO 校验。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import review_chat  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
from opencode_http import TransportError  # noqa: E402
import test_f84_review_chat_wiring as base  # noqa: E402

SCOPE = base.SCOPE
BATCH = base.BATCH
CHANNEL_B = {"id": "model-b", "providerID": "provider-b"}


class FakeService:
    """假产品服务（transport 替身）：按会话存消息；支持会话清理（404）与
    按模型通道注入 create/prompt 失败；assistant 消息可掺工具/推理噪音
    部件（断言 history 只收 text）。"""

    def __init__(self, *, reply="合成回答：值为 123,456.78 元",
                 noise_parts=False):
        self.reply = reply
        self.noise_parts = noise_parts
        self.sessions: dict = {}
        self.create_calls: list = []
        self.prompt_calls: list = []
        self.gone: set = set()
        self.fail_create_models: set = set()
        self.fail_prompt_sessions: set = set()

    def create(self, payload, config):
        model = payload.get("model") or {}
        if model.get("id") in self.fail_create_models:
            raise TransportError("transport_failure", uncertain=True)
        self.create_calls.append(payload)
        self.sessions[payload["id"]] = []
        return {"data": {"id": payload["id"], "title": payload["title"]}}

    def prompt(self, sid, request):
        if sid in self.gone:
            raise TransportError("http_404")
        if sid in self.fail_prompt_sessions:
            raise TransportError("transport_failure", uncertain=True)
        messages = self.sessions.setdefault(sid, [])
        self.prompt_calls.append((sid, request))
        messages.append({"id": request["id"], "type": "user"})
        if self.reply is None:  # 慢模型径：轮次永不出文本
            return
        parts = [{"type": "text", "text": self.reply}]
        if self.noise_parts:
            parts = [{"type": "tool", "tool": "SYNTH_TOOL_NOISE"},
                     {"type": "reasoning", "text": "SYNTH_REASONING_NOISE"},
                     *parts]
        messages.append({"id": "asst-" + request["id"], "type": "assistant",
                         "content": parts})
        messages.append({"id": "idle-" + request["id"], "type": "idle"})

    def request(self, method, path):
        sid = path.split("/")[3]
        if sid in self.gone:
            raise TransportError("http_404")
        return {"data": self.sessions.get(sid, []), "cursor": None}


class ContinuityTestCase(unittest.TestCase):
    """公共脚手架：临时状态根＋三投影 seam＋假产品服务注入。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = dict(base.CONFIG)
        self.config["harness_state_root"] = self.tmp.name
        base.patch_projections(self)
        self.service = FakeService()
        self._patch_service(self.service)

    def _patch_service(self, service):
        import e07_coordinator
        for name, value in (("service_client", lambda config: service),
                            ("create_public_session", service.create)):
            patcher = unittest.mock.patch.object(e07_coordinator, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def registry(self) -> dict:
        path = Path(self.tmp.name) / "review-chat-sessions" / "sessions.json"
        if not path.exists():
            return {"schema": "review-chat-sessions/1",
                    "conversations": {}}
        return json.loads(path.read_text(encoding="utf-8"))

    def entry(self) -> dict:
        key = BATCH + "|" + SCOPE["matterId"]
        return self.registry()["conversations"].get(key) or {}

    def ask(self, question="问题", **kwargs):
        args = {"review_batch_id": BATCH, "scope": SCOPE, "question": question}
        args.update(kwargs)
        return review_chat.review_chat_ask(args, self.config)


class SessionResumeTests(ContinuityTestCase):
    def test_same_channel_second_ask_reuses_session(self) -> None:
        """式一①：同通道两连问→第二问复用同一 sessionId，零新建。"""
        first = self.ask("第一问：row-1 的合同金额？")
        second = self.ask("第二问：依据是什么？")
        self.assertEqual(len(self.service.create_calls), 1)
        sid = first["sessionRef"]
        self.assertEqual(second["sessionRef"], sid)
        self.assertEqual([s for s, _ in self.service.prompt_calls],
                         [sid, sid])
        self.assertTrue(first["continuity"]["resumed"] is False)
        self.assertTrue(second["continuity"]["resumed"])
        self.assertIsNone(second["continuity"]["switchReason"])
        self.assertTrue(second["continuity"]["persisted"])
        entry = self.entry()
        self.assertEqual(entry["sessionId"], sid)
        self.assertEqual(entry["turnState"], "IDLE")
        self.assertEqual([row["role"] for row in entry["history"]],
                         ["user", "assistant", "user", "assistant"])

    def test_deleted_session_reopens_once_with_history(self) -> None:
        """式一②：会话已被清理（404）→具名回传＋携历史重开恰一次。"""
        first = self.ask("第一问")
        sid = first["sessionRef"]
        self.service.gone.add(sid)  # 服务端清理（prompt 与回读都 404）
        second = self.ask("第二问")
        self.assertEqual(second["continuity"]["reopenedAfter"],
                         "session_invalid:http_404")
        self.assertEqual(second["continuity"]["switchReason"],
                         "session_invalid")
        # 恰一次：整个第二问只新建了一个会话（重开一次，不无限重试）。
        self.assertEqual(len(self.service.create_calls), 2)
        self.assertNotEqual(second["sessionRef"], sid)
        prompt = self.service.prompt_calls[-1][1]["text"]
        self.assertIn("〔历史问答开始〕", prompt)
        self.assertIn("【用户】第一问", prompt)
        self.assertIn("【助手】", prompt)
        # 重开后对旧会话的 prompt 尝试恰一次。
        self.assertEqual([s for s, _ in self.service.prompt_calls].count(sid), 1)
        event = self.entry()["switchEvents"][-1]
        self.assertEqual(event["sourceSessionId"], sid)
        self.assertEqual(event["newSessionId"], second["sessionRef"])
        self.assertEqual(event["reason"], "session_invalid")

    def test_pending_turn_blocks_resume(self) -> None:
        """式一③：上轮未收口（TURN_PENDING）→不续接，携历史重开。"""
        self.service.reply = None  # 首问永远不出回答
        with unittest.mock.patch.object(review_chat, "_TURN_WINDOW_SECONDS",
                                        0.0):
            first = self.ask("慢问题")
        self.assertEqual(first["state"], "TURN_PENDING")
        self.service.reply = FakeService().reply
        second = self.ask("新问题")
        self.assertEqual(second["continuity"]["switchReason"], "turn_pending")
        self.assertEqual(len(self.service.create_calls), 2)
        prompt = self.service.prompt_calls[-1][1]["text"]
        self.assertIn("【用户】慢问题", prompt)  # 未答问照转写不断链
        entry = self.entry()
        self.assertEqual(entry["turnState"], "IDLE")
        self.assertEqual(entry["switchEvents"][-1]["reason"], "turn_pending")

    def test_directory_guard_forces_new_session(self) -> None:
        """守卫补验：注册表 directory 与当前事项不符→不续接（白盒改账模拟
        注册表漂移；正常路径下 convKey 已含 matterId，此守卫兜文件边界）。"""
        first = self.ask("第一问")
        key = BATCH + "|" + SCOPE["matterId"]
        path = Path(self.tmp.name) / "review-chat-sessions" / "sessions.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["conversations"][key]["directory"] = "m-other-synth"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        second = self.ask("第二问")
        self.assertEqual(second["continuity"]["switchReason"],
                         "directory_changed")
        self.assertNotEqual(second["sessionRef"], first["sessionRef"])
        self.assertEqual(len(self.service.create_calls), 2)

    def test_no_state_root_degrades_to_new_session_per_ask(self) -> None:
        """无可用状态根＝续接停用：逐问新会话（主链不受害），persisted=False。"""
        self.config["harness_state_root"] = "X:/synth/unwritable-root"
        first = self.ask("第一问")
        second = self.ask("第二问")
        self.assertEqual(len(self.service.create_calls), 2)
        self.assertFalse(first["continuity"]["persisted"])
        self.assertFalse(second["continuity"]["persisted"])
        self.assertFalse(second["continuity"]["resumed"])


class CarryHistoryTests(ContinuityTestCase):
    def test_channel_change_opens_new_session_with_transcript(self) -> None:
        """式二①③：A 通道两轮后切 B→新会话、首 prompt 含前两轮文本、
        create 显式绑 B 模型、换轨事件落账。"""
        self.ask("第一问", )
        self.ask("第二问")
        third = self.ask("第三问", model=dict(CHANNEL_B))
        self.assertEqual(len(self.service.create_calls), 2)  # q1 新建+q3 换轨新建
        self.assertEqual(self.service.create_calls[-1]["model"], CHANNEL_B)
        self.assertNotEqual(third["sessionRef"],
                            self.service.create_calls[0]["id"])
        self.assertEqual(third["continuity"]["switchReason"],
                         "model_channel_changed")
        prompt = self.service.prompt_calls[-1][1]["text"]
        self.assertIn("〔历史问答开始〕", prompt)
        self.assertIn("【用户】第一问", prompt)
        self.assertIn("【助手】", prompt)
        self.assertIn("〔历史问答结束〕", prompt)
        self.assertIn("用户问题：第三问", prompt)
        entry = self.entry()
        self.assertEqual(entry["modelChannel"], CHANNEL_B)
        self.assertEqual(entry["sessionId"], third["sessionRef"])
        event = entry["switchEvents"][-1]
        self.assertEqual(event["sourceSessionId"],
                         self.service.create_calls[0]["id"])
        self.assertEqual(event["newSessionId"], third["sessionRef"])
        self.assertEqual(event["reason"], "model_channel_changed")

    def test_transcript_tail_cap_with_omission_note(self) -> None:
        """式二②：超限截尾保尾部＋头部省略标注（24000 常量）。"""
        long_history = []
        for i in range(30):
            long_history.append({"role": "user", "text": "问%d-%s" % (
                i, "甲" * 1200)})
            long_history.append({"role": "assistant", "text": "答%d-%s" % (
                i, "乙" * 1200)})
        key = BATCH + "|" + SCOPE["matterId"]
        path = Path(self.tmp.name) / "review-chat-sessions"
        path.mkdir(parents=True, exist_ok=True)
        (path / "sessions.json").write_text(json.dumps({
            "schema": "review-chat-sessions/1",
            "conversations": {key: {
                "sessionId": "ses_seed_long", "modelChannel": dict(
                    review_chat.CHAT_MODEL),
                "directory": SCOPE["matterId"], "turnState": "IDLE",
                "history": long_history, "switchEvents": []}},
        }, ensure_ascii=False), encoding="utf-8")
        result = self.ask("新问题", model=dict(CHANNEL_B))
        self.assertEqual(result["continuity"]["switchReason"],
                         "model_channel_changed")
        prompt = self.service.prompt_calls[-1][1]["text"]
        self.assertIn(review_chat._TRANSCRIPT_OMISSION_HEAD, prompt)
        self.assertNotIn("【用户】问0-", prompt)      # 头部已截
        self.assertIn("【用户】问29-", prompt)        # 尾部保留
        self.assertIn("【助手】答29-", prompt)
        # 单元径同口径复核：截尾后正文 ≤ 上限+标注。
        body = prompt.split("〔历史问答开始〕\n", 1)[1].split(
            "\n〔历史问答结束〕", 1)[0]
        self.assertLessEqual(len(body),
                             len(review_chat._TRANSCRIPT_OMISSION_HEAD) + 1
                             + review_chat._TRANSCRIPT_CHAR_LIMIT)
        self.assertTrue(result["continuity"]["transcriptPrefix"])

    def test_history_text_only_no_tool_noise(self) -> None:
        """式二②：assistant 消息掺工具/推理噪音部件→history 只收 text。"""
        self.service.noise_parts = True
        self.ask("第一问")
        entry = self.entry()
        self.assertEqual(entry["history"][1]["role"], "assistant")
        self.assertNotIn("SYNTH_TOOL_NOISE", entry["history"][1]["text"])
        self.assertNotIn("SYNTH_REASONING_NOISE",
                         entry["history"][1]["text"])
        self.assertEqual(entry["history"][1]["text"], self.service.reply)

    def test_failed_switch_keeps_channel_marker(self) -> None:
        """式二④：B 通道 create 失败（不确定结局）→typed 上浮、通道标记
        不变；A 通道续接照常（账面与实际不漂移）。"""
        self.ask("第一问")
        sid_a = self.service.create_calls[0]["id"]
        self.service.fail_create_models.add(CHANNEL_B["id"])
        with self.assertRaises(TransportError) as caught:
            self.ask("换轨问", model=dict(CHANNEL_B))
        self.assertEqual(caught.exception.code, "transport_failure")
        entry = self.entry()
        self.assertEqual(entry["modelChannel"], review_chat.CHAT_MODEL)
        self.assertEqual(entry["sessionId"], sid_a)
        self.assertEqual(entry["turnState"], "IDLE")
        back = self.ask("回 A 通道问")
        self.assertTrue(back["continuity"]["resumed"])
        self.assertEqual(back["sessionRef"], sid_a)

    def test_failed_prompt_after_create_marks_pending_keeps_marker(self) -> None:
        """式二④补充：create 成功但 prompt 落地失败（不确定结局）→不重试、
        通道标记不动、轮次标 PENDING（下轮携历史重开）。"""
        self.ask("第一问")
        sid_a = self.service.create_calls[0]["id"]
        # 让假服务只对新会话 prompt 失败：
        original_prompt = self.service.prompt

        def fail_new_sessions(sid, request):
            if sid != sid_a:
                raise TransportError("transport_failure", uncertain=True)
            return original_prompt(sid, request)

        self.service.prompt = fail_new_sessions
        with self.assertRaises(TransportError):
            self.ask("换轨问", model=dict(CHANNEL_B))
        entry = self.entry()
        self.assertEqual(entry["modelChannel"], review_chat.CHAT_MODEL)
        self.assertEqual(entry["sessionId"], sid_a)
        self.assertEqual(entry["turnState"], "PENDING")
        self.service.prompt = original_prompt
        retry = self.ask("再问")
        self.assertEqual(retry["continuity"]["switchReason"], "turn_pending")
        self.assertEqual(len(self.service.create_calls), 3)


class DtoTests(ContinuityTestCase):
    def test_optional_model_dto_closed(self) -> None:
        for bad in (
                {"model": "deepseek-chat"},
                {"model": {"id": "x"}},
                {"model": {"id": "", "providerID": "p"}},
                {"model": {"id": "x", "providerID": "p", "extra": 1}}):
            args = {"review_batch_id": BATCH, "scope": SCOPE,
                    "question": "q", **bad}
            with self.assertRaises(NotConnected) as caught:
                review_chat.review_chat_ask(args, self.config)
            self.assertIn("review_chat_model_invalid", str(caught.exception))
        for bad in ({"review_batch_id": BATCH, "scope": SCOPE,
                     "question": "q", "row_id": "row-1"},
                    {"review_batch_id": BATCH, "scope": SCOPE}):
            with self.assertRaises(NotConnected) as caught:
                review_chat.review_chat_ask(bad, self.config)
            self.assertIn("review_chat_ask_args_invalid",
                          str(caught.exception))


if __name__ == "__main__":
    unittest.main()
