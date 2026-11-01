"""F32 案件级记忆产品侧接线测试（W4-U34）：memory.* 方法组＋蒸馏确定性。

全部合成材料。legal_entry 新增 HARNESS_MEMORY_METHODS 六方法（--memory-json
信封）与 MEMORY_METHODS 七方法（memory.distill 本地确定性蒸馏，其余薄路由
harness 封闭信封）；subprocess seam 注入，单测零仓依赖；真 public_entry
全链＋PG 直连对账在 tools/PENDING_OWNER_f32_case_memory_recon.py。
fail-closed：未配置桥＝NOT_CONNECTED，绝不空响应冒成功。

合同要点（harness schema v31 case_memory_entries；v1.5·TTL 差异点）：
确认闸唯一生效转移（proposed 永不进生效投影）；每条记忆带来源 ref＋TTL；
TTL 过期与显式撤销回读不可见；目标账本不被延后（对 E18 goal/E15/E17 账
只读消费零写交叉）。蒸馏同输入同字节（canonical JSON）。
"""

from __future__ import annotations

import json
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E401,F401
from case_memory import (  # noqa: E402
    TTL_BY_KIND,
    DistillationError,
    canonical_bytes,
    distill,
)

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE = {"kind": "matter", "matterId": "m-f32"}
HARNESS_METHODS = (
    "harness.memory_propose", "harness.memory_confirm",
    "harness.memory_revoke", "harness.memory_read",
    "harness.memory_effective_list", "harness.memory_pending_list",
)
MEMORY_METHODS = (
    "memory.extract", "memory.propose", "memory.confirm", "memory.revoke",
    "memory.read", "memory.effective_list", "memory.pending_list",
)

TRANSCRIPT = [
    {"role": "user", "text": "事实：合同签订日为 2026-03-01（合成对账用）"},
    {"role": "assistant", "text": "已收到，违约金按日万分之五计算。"},
    {"role": "user", "text": "务必在答辩期内提交证据，不要联系对方当事人。"},
    {"role": "user", "text": "以后文书一律用简体中文。"},
    {"role": "assistant", "text": "今天天气如何？"},  # 无标记→零候选
]


def fake_entry_output(result, surface="memory"):
    return json.dumps({"surface": surface, "method": "synthetic",
                       "result": result})


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def capture_envelope(method_name):
    """Subprocess seam：捕获 --memory-json 信封并回固定成功结果。"""
    captured: list[dict] = []

    def _capture(argv, env, timeout):
        captured.append({
            "argv": list(argv),
            "envelope": json.loads(Path(
                argv[argv.index("--memory-json") + 1]
            ).read_text(encoding="utf-8"))})
        return SimpleNamespace(stdout=fake_entry_output({"ok": True}),
                               returncode=0)

    return captured, unittest.mock.patch.object(legal_entry, "_execute",
                                                _capture)


class F32DistillationTests(unittest.TestCase):
    """确定性蒸馏：同输入同字节；标记闭集固定序；形状出闭集具名拒。"""

    def test_distill_deterministic_bytes(self) -> None:
        first = distill(TRANSCRIPT, session_id="ses-f32", matter_id="m-f32")
        second = distill(TRANSCRIPT, session_id="ses-f32", matter_id="m-f32")
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        self.assertEqual(first["transcriptSha256"], second["transcriptSha256"])
        # 候选分类：constraint > preference > fact 固定序；无标记消息零候选。
        self.assertEqual(first["candidateCount"], 3)
        kinds = [c["kind"] for c in first["candidates"]]
        self.assertEqual(kinds, ["fact", "constraint", "preference"])
        # 候选强制带来源 ref（host 转写 digest 封闭六字段）＋TTL。
        for candidate in first["candidates"]:
            self.assertEqual(set(candidate["sourceRef"]),
                             {"owner", "kind", "id", "version", "matterId",
                              "digest"})
            self.assertEqual(candidate["sourceRef"]["kind"],
                             "session_transcript")
            self.assertEqual(candidate["sourceRef"]["digest"],
                             first["transcriptSha256"])
            self.assertIn(candidate["ttlSeconds"], set(TTL_BY_KIND.values()))
        # 确定性 id：同转写同序号同 id。
        self.assertEqual(
            [c["candidateId"] for c in first["candidates"]],
            [c["candidateId"] for c in second["candidates"]])

    def test_distill_input_change_changes_bytes(self) -> None:
        first = distill(TRANSCRIPT, session_id="ses-f32", matter_id="m-f32")
        altered = [dict(m) for m in TRANSCRIPT]
        altered[0] = dict(altered[0], text="事实：合同签订日为 2026-03-02")
        second = distill(altered, session_id="ses-f32", matter_id="m-f32")
        self.assertNotEqual(first["transcriptSha256"],
                            second["transcriptSha256"])
        self.assertNotEqual(canonical_bytes(first), canonical_bytes(second))

    def test_distill_rejects_closed_shape(self) -> None:
        for bad, code in (
            ([], "transcript_invalid"),
            ([{"role": "system", "text": "x"}], "transcript_role_unknown"),
            ([{"role": "user"}], "fields_not_closed"),
            ([{"role": "user", "text": "  "}], "transcript_text_invalid"),
            ("不是列表", "transcript_invalid"),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(DistillationError) as caught:
                    distill(bad, session_id="ses-f32", matter_id="m-f32")
                self.assertIn(code, str(caught.exception))


class F32BridgeTests(unittest.TestCase):
    """legal_entry 两组方法：白名单、memory 信封、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_MEMORY_METHODS,
                         frozenset(HARNESS_METHODS))
        self.assertEqual(legal_entry.MEMORY_METHODS,
                         frozenset(MEMORY_METHODS))
        # 伪方法（绕确认闸的状态直改/第二写通道/自动签发生效）不在冻结组。
        for forged in ("harness.memory_set_effective", "memory.write",
                       "memory.auto_confirm", "memory.set_ttl",
                       "harness.memory_update"):
            self.assertNotIn(forged, legal_entry.HARNESS_MEMORY_METHODS)
            self.assertNotIn(forged, legal_entry.MEMORY_METHODS)

    def test_memory_methods_ride_memory_envelope(self) -> None:
        source_ref = {"owner": "host", "kind": "session_transcript",
                      "id": "ses-f32", "version": "1", "matterId": "m-f32",
                      "digest": "a" * 64}
        decision_ref = {"owner": "host", "kind": "decision-receipt",
                        "id": "dec-1", "version": "1", "matterId": "m-f32",
                        "digest": None}
        # 候选＝memory.extract 产物形（candidateId/kind/text）——产品路由
        # 经 to_harness_memory 映射为 harness 载荷闭集后出信封。
        args_by_method = {
            "memory.propose": {
                "actor_id": "distiller", "scope": SCOPE,
                "key": command_key("mp-1"),
                "candidate": {"candidateId": "mem-1", "kind": "fact",
                              "text": "事实（合成）", "messageIndex": 0,
                              "sourceRef": source_ref,
                              "ttlSeconds": 7_776_000}},
            "memory.confirm": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("mc-1"), "memoryId": "mem-1",
                "decisionRef": decision_ref},
            "memory.revoke": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("mr-1"), "memoryId": "mem-1",
                "reasonRef": decision_ref},
            "memory.read": {"scope": SCOPE, "memoryId": "mem-1",
                            "revision": None},
            "memory.effective_list": {"scope": SCOPE},
            "memory.pending_list": {"scope": SCOPE},
        }
        expected_params = {
            "memory.propose": {
                "actor_id": "distiller", "scope": SCOPE,
                "key": command_key("mp-1"),
                "memory": {"memoryId": "mem-1",
                           "content": {"kind": "fact",
                                       "text": "事实（合成）"},
                           "sourceRef": source_ref,
                           "ttlSeconds": 7_776_000}},
            "memory.confirm": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("mc-1"),
                "confirmation": {"memoryId": "mem-1",
                                 "decisionRef": decision_ref}},
            "memory.revoke": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("mr-1"),
                "revocation": {"memoryId": "mem-1",
                               "reasonRef": decision_ref}},
            "memory.read": {"scope": SCOPE, "memory_id": "mem-1",
                            "revision": None},
            "memory.effective_list": {"scope": SCOPE},
            "memory.pending_list": {"scope": SCOPE},
        }
        for method in ("memory.propose", "memory.confirm", "memory.revoke",
                       "memory.read", "memory.effective_list",
                       "memory.pending_list"):
            with self.subTest(method=method):
                captured, patcher = capture_envelope(method)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, args_by_method[method],
                                          CONFIG)
                self.assertEqual(result, {"ok": True})
                argv = captured[0]["argv"]
                self.assertIn("--memory-json", argv)
                for other in ("--goal-json", "--tasks-json",
                              "--loosedocs-json", "--collab-json",
                              "--schedule-json", "--materials-json"):
                    self.assertNotIn(other, argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(
                    envelope["method"],
                    "harness.memory_" + method.split(".", 1)[1])
                # 路由形状逐键断言（propose→memory / confirm→confirmation /
                # revoke→revocation / read→memory_id+revision）。
                self.assertEqual(envelope["params"], expected_params[method])

    def test_confirm_envelope_shape(self) -> None:
        decision_ref = {"owner": "host", "kind": "decision-receipt",
                        "id": "dec-1", "version": "1", "matterId": "m-f32",
                        "digest": None}
        captured, patcher = capture_envelope("memory.confirm")
        patcher.start()
        self.addCleanup(patcher.stop)
        legal_entry.call("memory.confirm",
                         {"actor_id": "lawyer-1", "scope": SCOPE,
                          "key": command_key("mc-1"), "memoryId": "mem-1",
                          "decisionRef": decision_ref},
                         CONFIG)
        params = captured[0]["envelope"]["params"]
        self.assertEqual(captured[0]["envelope"]["method"],
                         "harness.memory_confirm")
        self.assertEqual(params["confirmation"],
                         {"memoryId": "mem-1", "decisionRef": decision_ref})

    def test_distill_local_no_subprocess(self) -> None:
        result = legal_entry.call("memory.extract",
                                  {"transcript": TRANSCRIPT,
                                   "sessionId": "ses-f32",
                                   "matterId": "m-f32"}, CONFIG)
        self.assertEqual(result["schema"], "juscite-f32-distillation/1")
        self.assertEqual(result["candidateCount"], 3)

    def test_bridge_not_configured_and_unknown(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("memory.effective_list", {"scope": SCOPE}, {})
        self.assertIn("harness_public_entry_not_configured",
                      str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("memory.auto_confirm", {"scope": SCOPE}, CONFIG)
        self.assertIn("method_not_connected", str(caught.exception))
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("harness.memory_update", {"scope": SCOPE}, CONFIG)
        self.assertIn("method_not_connected", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
