# -*- coding: utf-8 -*-
"""F121 产品侧接线测试（W4-U52）：legal_entry chronology 方法组＋确定性
抽取＋期限锚守卫。

全部合成材料：subprocess seam 注入（不真起 harness 进程，单测零网络零
仓依赖）；真 harness public_entry 的实跑对账在
tools/PENDING_OWNER_f121_chronology_recon.py（合成状态根＋合成 matter，
desktop=SQLite 桥径／selfhost=PG 直连，harness w4-u52 worktree 只读）。
fail-closed 纪律：未配置桥＝NOT_CONNECTED，绝不空响应冒成功。
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402
import chronology as chronology_face  # noqa: E402

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}

_SYNTH_SEGMENTS = [
    {"docId": "doc-1", "pageFrom": 1, "pageTo": 2, "text":
     "2024年3月5日，双方签订《购销合同》。合同约定验收后30日内付款。"
     "2024年3月，原告依约交付设备。"},
    {"docId": "doc-2", "pageFrom": 3, "pageTo": 3, "text":
     "3月5日被告签收货物（无年份记录）。2024年，法院受理本案。"},
]


def fake_entry_output(surface, result):
    return json.dumps({"surface": surface, "method": "synthetic",
                       "result": result})


def patch_execute(testcase, *, stdout="", returncode=0, calls=None):
    def _fake(argv, env, timeout):
        if calls is not None:
            calls.append({"argv": argv, "env": env})
        proc = SimpleNamespace()
        proc.stdout, proc.returncode = stdout, returncode
        return proc
    patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
    patcher.start()
    testcase.addCleanup(patcher.stop)


class ExtractDeterminismTests(unittest.TestCase):
    """chronology.extract：确定性抽取（正则＋状态机，红线 1）。"""

    def test_deterministic_two_runs_identical(self) -> None:
        self.assertTrue(chronology_face.canonical_determinism_probe(
            _SYNTH_SEGMENTS))

    def test_closed_kinds_and_date_shapes(self) -> None:
        result = chronology_face.extract_segments(_SYNTH_SEGMENTS)
        kinds = {c["eventKind"] for c in result["candidates"]}
        self.assertTrue(kinds <= set(chronology_face.EVENT_KINDS))
        by_date = {(c["eventKind"], c["eventDate"], c["datePrecision"])
                   for c in result["candidates"]}
        # 完整日期 → day；无年「3月5日」→ unknown（绝不猜年）。
        self.assertIn(("contract_signing", "2024-03-05", "day"), by_date)
        self.assertIn(("performance", "2024-03", "month"), by_date)
        self.assertIn(("service", None, "unknown"), by_date)
        self.assertIn(("other", "2024", "year"), by_date)
        # 抽取候选日期来源闭集：有日期＝extracted；unknown 档＝unavailable
        # （与 harness 表级 CHECK 同一冻结语义）；零录入日语义字段。
        for candidate in result["candidates"]:
            expected_origin = ("extracted" if candidate["eventDate"]
                               is not None else "unavailable")
            self.assertEqual(candidate["dateOrigin"], expected_origin)
            self.assertNotIn("entryDate", candidate)
            self.assertNotIn("documentDate", candidate)
        self.assertGreaterEqual(result["unknownCount"], 1)

    def test_unknown_never_fills_document_date(self) -> None:
        # 段落带文档日期字样也不得回填到 unknown 候选（unknown 项
        # eventDate 恒 None；文档日期字符串不进任何候选日期位）。
        segments = [{"docId": "doc-9", "pageFrom": 1, "pageTo": 1,
                     "text": "（文档日期：2026-10-21）被告签收货物。"}]
        result = chronology_face.extract_segments(segments)
        self.assertEqual(result["candidateCount"], 1)
        self.assertIsNone(result["candidates"][0]["eventDate"])
        self.assertEqual(result["candidates"][0]["datePrecision"], "unknown")

    def test_invalid_segments_refused(self) -> None:
        with self.assertRaises(chronology_face.ChronologyError) as caught:
            chronology_face.extract_segments([])
        self.assertIn("segments_invalid", str(caught.exception))
        with self.assertRaises(chronology_face.ChronologyError) as caught:
            chronology_face.extract_segments([{"docId": "d", "pageFrom": 2,
                                               "pageTo": 1, "text": "x"}])
        self.assertIn("segment_invalid", str(caught.exception))


class DeadlineAnchorTests(unittest.TestCase):
    """chronology.deadline_anchor：confirmed＋不 STALE 才可作期限锚。"""

    @staticmethod
    def _readback(**extra):
        readback = {
            "eventId": "ev-1", "revision": 2, "status": "confirmed",
            "eventDate": "2024-03-05", "datePrecision": "day",
            "sourceRef": {"owner": "harness", "kind": "material",
                          "id": "mat-1", "version": "1",
                          "matterId": "m-1", "digest": None},
            "dependencyStatus": {"stale": [], "staleCount": 0,
                                 "freshCount": 1},
        }
        readback.update(extra)
        return readback

    def test_confirmed_fresh_day_anchor_ok(self) -> None:
        anchor = chronology_face.deadline_anchor(self._readback())
        self.assertEqual(anchor["anchorDate"], "2024-03-05")
        self.assertEqual(anchor["eventId"], "ev-1")

    def test_unconfirmed_refused(self) -> None:
        with self.assertRaises(chronology_face.ChronologyError) as caught:
            chronology_face.deadline_anchor(self._readback(
                status="unconfirmed"))
        self.assertIn("chronology_anchor_not_confirmed", str(caught.exception))

    def test_stale_dependency_refused(self) -> None:
        with self.assertRaises(chronology_face.ChronologyError) as caught:
            chronology_face.deadline_anchor(self._readback(
                dependencyStatus={"stale": [{"dependentId": "sched-1",
                                             "reason":
                                             "chronology_event_revision_moved"}],
                                  "staleCount": 1, "freshCount": 0}))
        self.assertIn("chronology_anchor_dependency_stale",
                      str(caught.exception))

    def test_unknown_bucket_and_coarse_precision_refused(self) -> None:
        with self.assertRaises(chronology_face.ChronologyError) as caught:
            chronology_face.deadline_anchor(self._readback(
                eventDate=None, datePrecision="unknown"))
        self.assertIn("chronology_anchor_date_unknown", str(caught.exception))
        with self.assertRaises(chronology_face.ChronologyError) as caught:
            chronology_face.deadline_anchor(self._readback(
                eventDate="2024-03", datePrecision="month"))
        self.assertIn("chronology_anchor_precision_insufficient",
                      str(caught.exception))


class BridgeRoutingTests(unittest.TestCase):
    """legal_entry chronology 组：白名单分发、fail-closed、信封分离。"""

    def test_groups_enumerable_and_disjoint(self) -> None:
        self.assertEqual(legal_entry.HARNESS_CHRONOLOGY_METHODS, frozenset({
            "harness.chronology_event_record",
            "harness.chronology_event_confirm",
            "harness.chronology_event_read",
            "harness.chronology_axis",
            "harness.chronology_invalidations_list",
        }))
        self.assertEqual(legal_entry.CHRONOLOGY_METHODS, frozenset({
            "chronology.extract", "chronology.deadline_anchor"}))
        self.assertFalse(legal_entry.HARNESS_CHRONOLOGY_METHODS
                         & legal_entry.CHRONOLOGY_METHODS)

    def test_harness_group_uses_chronology_envelope(self) -> None:
        calls: list[dict] = []
        envelopes: list[dict] = []

        def _capture(argv, env, timeout):
            calls.append({"argv": argv, "env": env})
            envelopes.append(json.loads(
                Path(argv[argv.index("--chronology-json") + 1]).read_text(
                    encoding="utf-8")))
            return SimpleNamespace(
                stdout=fake_entry_output("chronology", {"known": []}),
                returncode=0)

        patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                             _capture)
        patcher.start()
        self.addCleanup(patcher.stop)
        result = legal_entry.call(
            "harness.chronology_axis",
            {"scope": {"kind": "matter", "matterId": "m-f121"}}, CONFIG)
        self.assertEqual(result, {"known": []})
        self.assertEqual(envelopes[0]["method"], "harness.chronology_axis")
        self.assertIn("--chronology-json", calls[0]["argv"])
        self.assertIn("--target", calls[0]["argv"])

    def test_unconfigured_bridge_refused(self) -> None:
        for method in ("harness.chronology_axis",
                       "harness.chronology_event_record"):
            with self.assertRaises(NotConnected):
                legal_entry.call(method, {"scope": {}}, {})

    def test_local_face_routes_without_bridge(self) -> None:
        result = legal_entry.call("chronology.extract",
                                  {"segments": _SYNTH_SEGMENTS}, {})
        self.assertEqual(result["schema"], "juscite-f121-chronology/1")
        with self.assertRaises(chronology_face.ChronologyError):
            legal_entry.call("chronology.extract", {"segments": []}, {})
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("chronology.nonsense", {}, {})
        self.assertIn("not_connected", str(caught.exception).lower())

    def test_bridge_error_surfaces_typed(self) -> None:
        patch_execute(self, stdout=json.dumps(
            {"status": "FAIL", "error": "chronology_unknown_date_filled"}),
            returncode=1)
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call(
                "harness.chronology_event_record",
                {"scope": {"kind": "matter", "matterId": "m"},
                 "key": {"requestId": "r1", "targetId": None,
                         "expectedRevision": None, "inputRefs": []},
                 "event": {"eventId": "e", "title": "t",
                           "eventKind": "other", "eventDate": None,
                           "datePrecision": "unknown",
                           "dateOrigin": "unavailable", "summary": "s",
                           "sourceRef": {"owner": "harness",
                                         "kind": "material", "id": "m1",
                                         "version": "1", "matterId": "m",
                                         "digest": None},
                           "sourceSpan": None, "invalidations": []}},
                CONFIG)
        self.assertIn("chronology_unknown_date_filled",
                      str(caught.exception))


class DeterminismAstTests(unittest.TestCase):
    """AST 纪律：抽取面导入闭集（仅 json/re），零模型/零网络/零时钟。"""

    def test_import_closure_is_stdlib_minimal(self) -> None:
        source = (ROOT / "python" / "chronology.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertEqual(imported, {"__future__", "json", "re"})

    def test_no_model_or_network_or_clock_markers(self) -> None:
        source = (ROOT / "python" / "chronology.py").read_text(
            encoding="utf-8")
        for marker in ("requests", "urllib", "http", "socket", "openai",
                       "anthropic", "datetime.now", "time.time",
                       "random", "uuid"):
            self.assertNotIn(marker, source)


if __name__ == "__main__":
    unittest.main()
