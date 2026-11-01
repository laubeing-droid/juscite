# -*- coding: utf-8 -*-
"""W3-U15 / F83+F85 acceptance: contract column presets + Excel export.

06:F83 assertion「合同列预设字段与format严格分离；每列金标、缺值/多值/
未知不伪填」＋06:F85 assertion「Excel真实格值与可审引用列一致；内部标记
脱壳不丢来源」＋XLSX 确定性生成两跑同字节。

* column_preset.read — frozen 12-field preset (≥10), field layer
  {id,name,gold} strictly separated from format layer {id,format};
  a field carrying a format key is a named refusal;
* column_preset.apply — preset declared into an existing F82 batch through
  harness.review_columns_define (the single column authority); frozen-set
  and conflict verdicts pass through untouched;
* column_preset.values — fill projection: missing/multi/unknown keep
  value=None with a named fill (never a fabricated placeholder); number
  gold columns require Decimal-parseable mentions (amount discipline);
* export.xlsx — same-source projection of tabular.read ×
  harness.review_support_read; real cell values (internal citation
  markers ⟦引:…⟧ stripped span-exact) stay consistent with the auditable
  citation columns (stamp citations with F87 three-state + provenance;
  stripped markers without a stamp are UNVERIFIED with named provenance
  absence); absent values export as truly empty cells; the XLSX is
  deterministic (fixed zip timestamps, clock-free XML — two runs, same
  bytes) and is read back through an independent zip+xml parse.

All materials are synthetic engineering fixtures. The bridge harness seam
is injected via unittest.mock (zero repo dependency); the full-chain
reconciliation lives in tools/PENDING_OWNER_f83_f85_columns_export_recon.py.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import unittest
import unittest.mock
import zipfile
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import column_presets  # noqa: E402
import excel_export  # noqa: E402
import tabular_review  # noqa: E402
import extraction_gate  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

SCOPE = {"kind": "matter", "matterId": "m-f83f85"}
KEY = {"requestId": "k-1", "targetId": None, "expectedRevision": None,
       "inputRefs": []}


def not_connected_call(method: str, args: dict, config: dict | None = None):
    return legal_entry.call(method, args, config or {})


class F83PresetStructureTests(unittest.TestCase):
    """冻结预设结构：字段/format 严格分离＋每列金标（F83 断言前两半）。"""

    def test_read_shape_separated_and_gilded(self) -> None:
        view = column_presets.preset_read({}, {})
        self.assertGreaterEqual(view["fieldCount"], 10)
        self.assertEqual(view["fieldCount"], len(view["fields"]))
        self.assertTrue(view["separated"])
        for field in view["fields"]:
            # 字段层闭集：绝无 format 键；每列必有金标（kind 闭集）。
            self.assertEqual(set(field), {"id", "name", "gold"})
            self.assertNotIn("format", field)
            self.assertIn(field["gold"]["kind"], column_presets.GOLD_KINDS)
        for item in view["formats"]:
            # format 层闭集：绝无 gold/name 越层。
            self.assertEqual(set(item), {"id", "format"})
        self.assertEqual({f["id"] for f in view["fields"]},
                         {x["id"] for x in view["formats"]})

    def test_gold_kinds_closure_matches_tabular_face(self) -> None:
        # 金标 kind 闭集三处一致（harness REVIEW_GOLD_KINDS 的产品侧同集）。
        self.assertEqual(column_presets.GOLD_KINDS,
                         tabular_review._GOLD_KINDS)

    def test_field_carries_format_refused(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            column_presets._validate_field(
                {"id": "x", "name": "越层列", "format": "text",
                 "gold": {"kind": "text"}}, 0)
        self.assertIn("preset_field_carries_format:x", str(caught.exception))

    def test_format_layer_shape_refused(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            column_presets._validate_format(
                {"id": "x", "format": "text", "gold": {"kind": "text"}}, 0)
        self.assertIn("column_preset_format_shape_invalid",
                      str(caught.exception))

    def test_join_id_mismatch_refused(self) -> None:
        tampered = tuple(dict(item) for item in column_presets.FORMATS[:-1])
        with unittest.mock.patch.object(column_presets, "FORMATS", tampered):
            with self.assertRaises(NotConnected) as caught:
                column_presets._joined_columns()
        self.assertIn("preset_format_id_mismatch", str(caught.exception))

    def test_join_boundary_produces_harness_shape(self) -> None:
        columns = column_presets._joined_columns()
        self.assertEqual(len(columns), column_presets.preset_read({}, {})
                         ["fieldCount"])
        for column in columns:
            # join 只发生在申报边界：harness 列合同形状五键齐。
            self.assertEqual(set(column),
                             {"id", "name", "format", "version", "gold"})


class F83ValuesProjectionTests(unittest.TestCase):
    """填充投影：缺值/多值/未知不伪填（F83 断言后半）。"""

    def _project(self, values: dict) -> dict:
        return column_presets.preset_values({"values": values}, {})

    def test_missing_multi_unknown_never_filled(self) -> None:
        out = self._project({
            "contract_amount": [],                        # 缺值
            "risk_level": ["高", "低"],                    # 多值（互异）
            "penalty_standard": ["以实物为准"],             # 未知（不可 Decimal）
            "parties": ["甲方"],                           # 填充
        })
        by_id = {cell["columnId"]: cell for cell in out["cells"]}
        self.assertEqual(by_id["contract_amount"]["fill"],
                         "value_missing")
        self.assertEqual(by_id["contract_amount"]["value"], None)
        self.assertEqual(by_id["risk_level"]["fill"], "value_ambiguous")
        self.assertEqual(by_id["risk_level"]["value"], None)
        self.assertEqual(by_id["penalty_standard"]["fill"], "value_unknown")
        self.assertEqual(by_id["penalty_standard"]["value"], None)
        self.assertEqual(by_id["parties"]["fill"], "filled")
        self.assertEqual(by_id["parties"]["value"], "甲方")
        self.assertEqual(out["unfilledCount"], 3)

    def test_identical_mentions_dedupe_not_ambiguous(self) -> None:
        out = self._project({"parties": ["甲方", "甲方"]})
        cell = out["cells"][0]
        self.assertEqual(cell["fill"], "filled")
        self.assertEqual(cell["distinctCount"], 1)
        self.assertEqual(cell["mentionCount"], 2)

    def test_number_gold_requires_decimal_parseable(self) -> None:
        out = self._project({"contract_amount": ["总价为人民币123,456.78元"]})
        self.assertEqual(out["cells"][0]["fill"], "filled")
        out = self._project({"contract_amount": ["按实结算"]})
        self.assertEqual(out["cells"][0]["fill"], "value_unknown")

    def test_unknown_column_refused(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            self._project({"ghost": ["x"]})
        self.assertIn("preset_column_unknown:ghost", str(caught.exception))

    def test_non_string_mention_refused(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            self._project({"parties": [123]})
        self.assertIn("column_preset_mentions_invalid", str(caught.exception))


class F83ApplyBridgeTests(unittest.TestCase):
    """申报桥：列权威唯一在 harness（seam 注入）。"""

    def test_apply_declares_through_harness(self) -> None:
        captured = {}

        def fake_seam(method, args, config):
            captured["method"] = method
            captured["args"] = args
            return {"replayed": False, "columns": len(args["columns"]),
                    "batchId": args["batch_id"]}

        with unittest.mock.patch.object(column_presets, "_harness_call",
                                        fake_seam):
            got = legal_entry.call(
                "column_preset.apply",
                {"scope": SCOPE, "review_batch_id": "brt-f83",
                 "actor_id": "lawyer-1", "key": KEY}, {})
        self.assertEqual(captured["method"], "harness.review_columns_define")
        self.assertEqual(captured["args"]["batch_id"], "brt-f83")
        self.assertEqual(len(captured["args"]["columns"]), 12)
        self.assertEqual(got["columnCount"], 12)

    def test_apply_args_closed(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "column_preset.apply",
                {"scope": SCOPE, "review_batch_id": "brt-f83",
                 "actor_id": "lawyer-1", "key": KEY, "columns": [{}]}, {})
        self.assertIn("column_preset_apply_args_invalid",
                      str(caught.exception))

    def test_group_membership_frozen(self) -> None:
        self.assertEqual(legal_entry.COLUMN_PRESET_METHODS,
                         frozenset(column_presets.COLUMN_PRESET_METHODS))
        for forged in ("column_preset.write", "column_preset.patch_gold",
                       "preset.define"):
            self.assertNotIn(forged, legal_entry.COLUMN_PRESET_METHODS)
        self.assertEqual(legal_entry.EXCEL_EXPORT_METHODS,
                         frozenset(excel_export.EXCEL_EXPORT_METHODS))
        self.assertNotIn("export.verify", legal_entry.EXCEL_EXPORT_METHODS)


_SHA = "c" * 64
_COLUMNS = [{"id": "contract_amount", "name": "合同金额（元）"},
            {"id": "legal_basis", "name": "法律依据（引文）"}]
_READ_DOC = {
    "reviewBatchId": "brt-f85", "batchStatus": "completed",
    "columns": [
        {"id": "contract_amount", "name": "合同金额（元）",
         "gold": {"kind": "number"}},
        {"id": "legal_basis", "name": "法律依据（引文）",
         "gold": {"kind": "text"}},
    ],
    "rows": [{
        "rowId": "row-1", "rowState": "done", "cells": [
            {"columnId": "contract_amount", "columnName": "合同金额（元）",
             "gold": {"kind": "number"},
             "value": "总价123,456.78元⟦引:《合》第一条⟧",
             "cellGeneration": 1, "cellSource": "machine",
             "supportStatus": "SUPPORTED_CITATION_LEVEL"},
            {"columnId": "legal_basis", "columnName": "法律依据（引文）",
             "gold": {"kind": "text"}, "value": None,
             "cellGeneration": 0, "cellSource": "initial",
             "supportStatus": "NO_STAMP"},
        ]}],
}
_SUPPORT_DOC = {
    "entries": {"row-1:contract_amount": [{
        "seq": 1, "entryKind": "support",
        "record": {"entryKind": "support", "seq": 1,
                   "gate": {"gateStatus": "CITATION_VERIFIED"},
                   "citations": [{"citationText": "《合》第一条",
                                  "status": "现行"}],
                   "provenance": {"source": "material_extraction",
                                  "doc": "synth_doc", "page": 3,
                                  "textSha256": _SHA}}},
    ]},
}


def fake_seam(method, args, config):
    if method == "tabular.read":
        return json.loads(json.dumps(_READ_DOC))
    if method == "harness.review_support_read":
        return json.loads(json.dumps(_SUPPORT_DOC))
    raise AssertionError("unexpected seam method: " + method)


class F85ProjectionTests(unittest.TestCase):
    """投影：真实格值与可审引用列一致＋标记脱壳不丢来源。"""

    def _export(self):
        with unittest.mock.patch.object(excel_export, "_harness_call",
                                        fake_seam):
            return legal_entry.call(
                "export.xlsx",
                {"scope": SCOPE, "review_batch_id": "brt-f85"}, {})

    def test_projection_value_citation_consistency(self) -> None:
        got = self._export()
        cell = got["projection"]["rows"][0]["cells"][0]
        # 真实格值＝剥除标记跨度，其余字节逐字保留。
        self.assertEqual(cell["realValue"], "总价123,456.78元")
        raw = cell["rawValue"]
        self.assertEqual(
            raw.replace(excel_export.MARKER_OPEN + cell["markers"][0]
                        + excel_export.MARKER_CLOSE, ""),
            cell["realValue"])
        # 脱壳不丢来源：被剥标记的引文文本在可审引用列（戳内已核形态）。
        self.assertEqual([c["citationText"] for c in cell["citations"]],
                         ["《合》第一条"])
        self.assertEqual(cell["citations"][0]["gateStatus"],
                         "CITATION_VERIFIED")
        self.assertEqual(cell["citations"][0]["origin"], "support_stamp")
        self.assertEqual(cell["citations"][0]["textSha256"], _SHA)
        # 缺值＝空串＋具名 value_absent（不伪填）。
        cell2 = got["projection"]["rows"][0]["cells"][1]
        self.assertEqual(cell2["realValue"], "")
        self.assertEqual(cell2["fillState"], "value_absent")
        self.assertEqual(cell2["stateCell"], "NO_STAMP|value_absent")
        self.assertEqual(cell2["citations"], [])

    def test_marker_without_stamp_is_named_unverified(self) -> None:
        doc = json.loads(json.dumps(_READ_DOC))
        doc["rows"][0]["cells"][1]["value"] = "适用《月球法》⟦引:《月球法》第一条⟧"
        doc["rows"][0]["cells"][1]["supportStatus"] = "NO_STAMP"

        def seam(method, args, config):
            if method == "tabular.read":
                return doc
            return json.loads(json.dumps(_SUPPORT_DOC))

        with unittest.mock.patch.object(excel_export, "_harness_call", seam):
            got = legal_entry.call(
                "export.xlsx",
                {"scope": SCOPE, "review_batch_id": "brt-f85"}, {})
        cell = got["projection"]["rows"][0]["cells"][1]
        self.assertEqual(cell["realValue"], "适用《月球法》")
        citation = cell["citations"][0]
        self.assertEqual(citation["gateStatus"], "UNVERIFIED")
        self.assertEqual(citation["origin"],
                         "marker_without_support_stamp")
        self.assertIsNone(citation["textSha256"])  # 出处具名缺席不编造
        self.assertIn("UNVERIFIED｜无支持戳", cell["citationCell"])

    def test_residue_and_bad_markers_refused(self) -> None:
        for bad in ("值⟦残⟧壳", "值⟦引:⟧尾", "完整⟦引:甲⟧后残留⟦"):
            with self.assertRaises(NotConnected):
                excel_export.strip_markers(bad)
    def test_strip_is_span_exact(self) -> None:
        stripped, markers = excel_export.strip_markers(
            "前⟦引:甲⟧中⟦引:乙⟧后")
        self.assertEqual((stripped, markers), ("前中后", ["甲", "乙"]))

    def test_float_value_refused(self) -> None:
        doc = json.loads(json.dumps(_READ_DOC))
        doc["rows"][0]["cells"][0]["value"] = 123456.78

        def seam(method, args, config):
            if method == "tabular.read":
                return doc
            return json.loads(json.dumps(_SUPPORT_DOC))

        with unittest.mock.patch.object(excel_export, "_harness_call", seam):
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call(
                    "export.xlsx",
                    {"scope": SCOPE, "review_batch_id": "brt-f85"}, {})
        self.assertIn("export_float_value_refused", str(caught.exception))

    def test_gate_three_states_closure(self) -> None:
        # F87 三态闭集：闸两态＋UNVERIFIED 缺省形态，与 extraction_gate 同源。
        self.assertEqual(excel_export.GATE_THREE_STATES,
                         set(extraction_gate.GATE_STATUSES)
                         | {excel_export.GATE_UNVERIFIED})
        stamped = excel_export._citation_rows(
            {"gate": {"gateStatus": "REJECTED"},
             "provenance": {}, "citations": []}, [])
        self.assertEqual(stamped, [])


class F85XlsxDeterminismTests(unittest.TestCase):
    """XLSX 确定性生成＋独立回读对账（zipfile+xml 不同解析路径）。"""

    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

    def _projection(self):
        with unittest.mock.patch.object(excel_export, "_harness_call",
                                        fake_seam):
            return excel_export.export_projection(
                {"scope": SCOPE, "review_batch_id": "brt-f85"}, {})

    def test_two_runs_same_bytes(self) -> None:
        projection = self._projection()
        first = excel_export.build_xlsx(projection)
        second = excel_export.build_xlsx(projection)
        self.assertEqual(first, second)
        # 生成器内不含时钟：zip 项时间戳钉定。
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))

    def _sheet_grid(self, payload: bytes) -> list:
        """独立回读（zipfile＋ElementTree，与生成不同解析路径）：
        行×列内联字符串网格。"""
        grid = []
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        for row in root.iter(self.NS + "row"):
            cells = {}
            for cell in row.iter(self.NS + "c"):
                ref = cell.attrib["r"]
                letters = "".join(ch for ch in ref if ch.isalpha())
                text = "".join(t.text or "" for t in cell.iter(self.NS + "t"))
                cells[letters] = text
            grid.append(cells)
        return grid

    def test_readback_matches_projection(self) -> None:
        projection = self._projection()
        payload = excel_export.build_xlsx(projection)
        grid = self._sheet_grid(payload)
        header, data = grid[0], grid[1]
        # 表头：行ID＋每列三联（值/引用/状态）。
        self.assertEqual(header["A"], "行ID")
        self.assertEqual(header["B"], "合同金额（元）")
        self.assertEqual(header["C"], "合同金额（元）·引用")
        self.assertEqual(header["D"], "合同金额（元）·状态")
        # 真实格值（标记剥除后）与引用列同源一致。
        cell = projection["rows"][0]["cells"][0]
        self.assertEqual(data["B"], cell["realValue"])
        self.assertEqual(data["C"], cell["citationCell"])
        self.assertEqual(data["D"], cell["supportStatus"])
        # 缺值格＝真空（不写单元格），状态列仍在结构位（G）具名 value_absent。
        self.assertNotIn("E", data)
        self.assertNotIn("F", data)
        self.assertEqual(data["G"], "NO_STAMP|value_absent")

    def test_full_export_receipt(self) -> None:
        with unittest.mock.patch.object(excel_export, "_harness_call",
                                        fake_seam):
            got = legal_entry.call(
                "export.xlsx",
                {"scope": SCOPE, "review_batch_id": "brt-f85"}, {})
        payload = base64.b64decode(got["xlsx_b64"])
        self.assertEqual(got["sha256"],
                         __import__("hashlib").sha256(payload).hexdigest())
        self.assertEqual(got["cellCount"], 2)
        self.assertEqual(got["markerSyntax"], "⟦引:<引文文本>⟧")
        self.assertEqual(payload[:2], b"PK")


class F85BridgeDispatchTests(unittest.TestCase):
    """legal_entry 分派：闭集外方法具名拒；未配置 seam fail-closed。"""

    def test_unknown_export_method_refused(self) -> None:
        # W4-U54 演进：export.verify 由「未接线占位名」落为 F123 独立验
        # 证器真面（export_manifest_checker，EXPORT_CHECKER_METHODS 冻结
        # 组）——本负测换仍属闭集外的名字，语义不变：未知导出方法具名拒。
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("export.verify_remote", {"scope": SCOPE}, {})
        self.assertIn("method_not_connected:export.verify_remote",
                      str(caught.exception))

    def test_unconfigured_seam_fails_closed(self) -> None:
        # 无 harness 配置：tabular.read 经桥面 NOT_CONNECTED 具名（exit 3）。
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "export.xlsx",
                {"scope": SCOPE, "review_batch_id": "brt-f85"}, {})
        self.assertIn("harness_public_entry_not_configured",
                      str(caught.exception))

    def test_args_shape_closed(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "export.xlsx",
                {"scope": SCOPE, "review_batch_id": "brt-f85",
                 "rows": []}, {})
        self.assertIn("export_args_invalid", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
