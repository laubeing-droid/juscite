# -*- coding: utf-8 -*-
"""F64(v1)/F69 产品侧接线测试（工单 W2a-U13）：本地优先来源策略＋法条效力。

全部合成材料（正式面目录为临时合成 CSV 树；唯一真实文件＝两份钉定公开面：
lccc_consumer.py（E22 冻结 v1.0，codices 分支 jusbench/w2a-u12-e22-baseline）
与 commercial_law_mcp.py（P11 付费 consumer，仅静态镜像核对 token 环境变量
名，不发任何请求）。钉定文件缺失/漂移即响亮失败，不静默跳过。

合同要点：
  F64 v1 降级链 本地→付费→web 冻结进检索策略：本地段唯一执行，付费/web
  恒具名声明缺口（F64-v1.5/B4），不静默跳级、不自采、零 URL 披露；
  F69 按适用时点定位状态/替代：缺 as_of/缺编码/冲突/窗口不可定→UNKNOWN
  不签现行；被废除（已废止/已修改/已失效）检索到也不许引（decision 恒非
  ALLOWED）；替代链数据缺→replacement=unknown 不编造。
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import statute_validity  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

# 钉定公开面（本机实测路径；codices 分支合并后 lccc 落仓根，路径随之订正）
LCCC_PATH = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u12-e22\lccc_consumer.py"
)
LCCC_SHA256 = "eb11ee5be548dbfed6e8b3f0052d11f28abb0cd010e1ef6236fb1e2fecf245d9"
COMMERCIAL_PATH = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\tools\commercial_law_mcp.py"
)
COMMERCIAL_SHA256 = (
    "b7b7c1fe1faf57791b84969b1c47cdfcef62b1a3ed97482dbbe09d4204aef0a9"
)

FACE_CSV_HEADERS = {
    "legal_contents.csv": ["DE_01001", "content_block"],
    "legal_relations.csv": ["WJBS", "related_wjbs"],
    "legal_sources.csv": ["WJBS", "source"],
    "cases.csv": ["official_case_id", "has_fulltext"],
    "case_legal_references.csv": ["case_id", "wjbs"],
    "case_holdings.csv": ["case_id", "holding"],
    "practice_references.csv": ["wjbs", "practice"],
}


def _body(date8: str, seq: str = "0001") -> str:
    # category[0:4]+agency[4:14]+date[14:22]+seq[22:26]+int[26:29]+type[29:31]
    return "0100" + "0000001001" + date8 + seq + "000" + "00"


# 合成行（全部为造出来的编码/日期，不含任何真实材料）
DOC_ROWS = [
    # WJBS 体, DE_01001, GBRQ, SXX, DE_01018, SXRQ, SHXRQ, 渠道
    (_body("20210820", "0091"), "in", "20210820", "01", "01", "20211101", "", "国家法律法规数据库"),
    (_body("20150101"), "in", "20150101", "04", "04", "20150601", "20200101", "国家法律法规数据库"),
    (_body("20170101"), "in", "20170101", "04", "04", "20170601", "", "国家法律法规数据库"),
    (_body("20081227"), "in", "20081227", "03", "03", "20090101", "", "国家法律法规数据库"),
    (_body("20260626"), "in", "20260626", "02", "02", "20270101", "", "国家法律法规数据库"),
    (_body("20260810"), "in", "20260810", "02", "02", "20260901", "", "国家法律法规数据库"),
    (_body("20200101"), "", "20200101", "01", "01", "20200601", "", "国家法律法规数据库"),
    (_body("20100101"), "in", "20100101", "01", "03", "20100601", "", "国家法律法规数据库"),
    (_body("20110101"), "in", "20110101", "01", "01", "201106", "", "国家法律法规数据库"),
]
WJBS = {name: "1.2.156.3005.6-" + row[0]
        for name, row in zip(
            ("CUR", "ABO_SH", "ABO_NOSH", "AMD", "NTY", "LAG",
             "NCODE", "CONF", "MAL"), DOC_ROWS)}
NOT_FOUND_WJBS = "1.2.156.3005.6-" + _body("20300101", "9999")


def build_synthetic_formal_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="f64f69-synth-"))
    with (root / "legal_documents.csv").open("w", encoding="utf-8-sig",
                                             newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["WJBS", "DE_01001", "GBRQ", "SXX", "DE_01018",
                         "SXRQ", "SHXRQ", "DE_01021"])
        for body, use_code, gbrq, sxx, de01018, sxrq, shxrq, channel in DOC_ROWS:
            writer.writerow(["1.2.156.3005.6-" + body,
                             body if use_code else "", gbrq, sxx, de01018,
                             sxrq, shxrq, channel])
    for name, header in FACE_CSV_HEADERS.items():
        with (root / name).open("w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle).writerow(header)
    (root / "README.md").write_text("synthetic F64/F69 test face\n",
                                    encoding="utf-8")
    (root / "SHA256SUMS").write_text("synthetic\n", encoding="utf-8")
    return root


def load_lccc_module():
    if not LCCC_PATH.is_file():
        raise FileNotFoundError(
            f"pinned frozen face missing at {LCCC_PATH} (E22 freeze v1.0, "
            "codices branch jusbench/w2a-u12-e22-baseline; after merge use "
            "the repo root) — F64/F69 must consume the frozen face, "
            "no substitute allowed")
    digest = hashlib.sha256(LCCC_PATH.read_bytes()).hexdigest()
    if digest != LCCC_SHA256:
        raise AssertionError(
            f"pinned lccc_consumer.py drifted: sha256 {digest} != "
            f"{LCCC_SHA256} (E22 freeze contract changed — update the pin "
            "through a codices branch, never bypass)")
    spec = importlib.util.spec_from_file_location("lccc_consumer_pin", LCCC_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _no_http_anywhere(value) -> bool:
    if isinstance(value, str):
        return "http://" not in value and "https://" not in value
    if isinstance(value, dict):
        return all(_no_http_anywhere(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_no_http_anywhere(v) for v in value)
    return True


class FrozenFacePinTest(unittest.TestCase):
    def test_pinned_lccc_face_present_and_unchanged(self):
        module = load_lccc_module()  # 缺失/漂移即失败
        self.assertTrue(hasattr(module, "LcccConsumer"))

    def test_paid_env_mirror_matches_p11_consumer(self):
        if not COMMERCIAL_PATH.is_file():
            raise FileNotFoundError(
                f"pinned P11 consumer missing at {COMMERCIAL_PATH} "
                "(14-Python入口与施工接线.md P11)")
        digest = hashlib.sha256(COMMERCIAL_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, COMMERCIAL_SHA256, "P11 consumer drifted")
        spec = importlib.util.spec_from_file_location(
            "commercial_law_mcp_pin", COMMERCIAL_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mirrored = {v["token_env"] for v in module.PROVIDERS.values()}
        self.assertEqual(mirrored, set(statute_validity.PAID_TOKEN_ENV_VARS))


class F69ValidityGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lccc = load_lccc_module()
        cls.root = build_synthetic_formal_root()
        cls.config = {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(cls.root),
        }

    def _gate(self, wjbs, as_of=None):
        args = {"wjbs": wjbs}
        if as_of is not None:
            args["as_of"] = as_of
        return legal_entry.call("statute.citation_gate", args, self.config)

    def _resolve(self, wjbs, as_of=None):
        args = {"wjbs": wjbs}
        if as_of is not None:
            args["as_of"] = as_of
        return legal_entry.call("statute.resolve", args, self.config)

    def test_current_in_force_citable_with_timepoint(self):
        result = self._gate(WJBS["CUR"], "20261015")
        self.assertEqual(result["decision"], "ALLOWED")
        self.assertEqual(result["code"], "CURRENT_IN_FORCE_CITABLE")
        self.assertTrue(result["signs_current"])
        self.assertEqual(result["status_label"], "有效")
        self.assertEqual(result["in_force_window"], "yes")

    def test_timepoint_moves_verdict_before_effective_date(self):
        result = self._gate(WJBS["CUR"], "20211031")
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertEqual(result["code"], "NOT_YET_IN_FORCE_AT_AS_OF")
        self.assertFalse(result["signs_current"])

    def test_missing_as_of_fails_closed_never_signs_current(self):
        result = self._gate(WJBS["CUR"])
        self.assertEqual(result["decision"], "UNKNOWN")
        self.assertEqual(result["code"], "AS_OF_REQUIRED_FAIL_CLOSED")
        self.assertFalse(result["signs_current"])

    def test_malformed_as_of_fails_closed(self):
        result = self._gate(WJBS["CUR"], "2021-10-31")
        self.assertEqual(result["decision"], "UNKNOWN")
        self.assertEqual(result["code"], "AS_OF_MALFORMED_FAIL_CLOSED")

    def test_abolished_with_expiry_window_blocked(self):
        result = self._gate(WJBS["ABO_SH"], "20261015")
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertEqual(result["code"], "ABOLISHED_NOT_CITABLE")
        self.assertEqual(result["in_force_window"], "no")

    def test_abolished_without_expiry_date_still_not_citable(self):
        # 被废除检索到也不许引：窗口不可定也绝不放行
        result = self._gate(WJBS["ABO_NOSH"], "20261015")
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertEqual(result["code"], "ABOLISHED_NOT_CITABLE")
        self.assertEqual(result["in_force_window"], "unknown")

    def test_amended_superseded_not_citable_replacement_unknown(self):
        result = self._gate(WJBS["AMD"], "20261015")
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertEqual(result["code"], "SUPERSEDED_NOT_CITABLE")
        self.assertEqual(result["replacement"], "unknown")
        self.assertIn("legal_relations", result["replacement_reason"])

    def test_not_yet_in_force_blocked_at_as_of(self):
        result = self._gate(WJBS["NTY"], "20261015")
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertEqual(result["code"], "NOT_YET_IN_FORCE_AT_AS_OF")

    def test_status_window_conflict_lag_fails_closed(self):
        result = self._gate(WJBS["LAG"], "20261015")
        self.assertEqual(result["decision"], "UNKNOWN")
        self.assertEqual(result["code"], "STATUS_WINDOW_CONFLICT_FAIL_CLOSED")

    def test_missing_gb_code_unknown_never_signs_current(self):
        result = self._gate(WJBS["NCODE"], "20261015")
        self.assertEqual(result["decision"], "UNKNOWN")
        self.assertTrue(result["code"].startswith(
            "FACE_STRUCTURAL_GAP_FAIL_CLOSED:NO_GB_FILE_CODE_SCOPE_GAP"))
        self.assertFalse(result["signs_current"])
        resolve = self._resolve(WJBS["NCODE"], "20261015")
        # 冻结面合同（lccc_consumer.py:356）：结构缺口行 status_label 仍返回，
        # 但窗口/现行一律 unknown／False——缺编码不签现行
        self.assertFalse(resolve["signs_current"])
        self.assertEqual(resolve["in_force_window"], "unknown")

    def test_status_field_conflict_unknown(self):
        result = self._gate(WJBS["CONF"], "20261015")
        self.assertEqual(result["decision"], "UNKNOWN")
        self.assertTrue(result["code"].startswith(
            "FACE_STRUCTURAL_GAP_FAIL_CLOSED:SXX_VS_DE01018_CONFLICT"))

    def test_malformed_date_field_unknown(self):
        result = self._gate(WJBS["MAL"], "20261015")
        self.assertEqual(result["decision"], "UNKNOWN")
        self.assertTrue(result["code"].startswith(
            "FACE_STRUCTURAL_GAP_FAIL_CLOSED:DATE_FIELD_MALFORMED"))

    def test_malformed_wjbs_and_not_found_unknown(self):
        bad = self._gate("1.2.156.3005.6-000", "20261015")
        self.assertEqual(bad["decision"], "UNKNOWN")
        self.assertIn("INVALID_WJBS_FORMAT", bad["code"])
        missing = self._gate(NOT_FOUND_WJBS, "20261015")
        self.assertEqual(missing["decision"], "UNKNOWN")
        self.assertIn("NOT_FOUND_IN_LEGAL_DOCUMENTS", missing["code"])

    def test_code31_path_locates_version(self):
        result = legal_entry.call(
            "statute.resolve",
            {"code31": _body("20210820", "0091"), "as_of": "20261015"},
            self.config)
        self.assertTrue(result["found"])
        self.assertEqual(result["status_label"], "有效")
        self.assertTrue(result["timepoint_positioned"])


class F64LocalFirstStrategyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(build_synthetic_formal_root()),
        }

    def test_chain_frozen_local_executed_paid_web_declared(self):
        result = legal_entry.call("statute.source_strategy", {}, self.config)
        self.assertEqual(result["chain"], ["local", "paid", "web"])
        self.assertTrue(result["frozen"])
        self.assertEqual(result["version"], "v1")
        self.assertEqual(result["policy"], "local_first_no_silent_escalation")
        self.assertEqual(result["segments"]["local"]["state"], "executed")
        self.assertIn("declared_gap_pending_F64-v1.5(B4)",
                      result["segments"]["paid"]["state"])
        self.assertIn("declared_gap_pending_F64-v1.5(B4)",
                      result["segments"]["web"]["state"])

    def test_paid_gap_named_when_token_missing_no_self_collection(self):
        with unittest.mock.patch.dict(
                os.environ,
                {var: "" for var in statute_validity.PAID_TOKEN_ENV_VARS}):
            result = legal_entry.call("statute.source_strategy", {},
                                      self.config)
        gap = result["segments"]["paid"]["gap"]
        self.assertEqual(gap["reason"], "PAID_TOKEN_NOT_CONFIGURED")
        self.assertEqual(set(gap["detail"].split(";")),
                         set(statute_validity.PAID_TOKEN_ENV_VARS))
        self.assertEqual(gap["self_collection"], "none")

    def test_paid_token_present_still_not_exercised_and_value_never_leaks(self):
        secret = "synthetic-token-value-f64f69"
        env = {var: secret for var in statute_validity.PAID_TOKEN_ENV_VARS}
        with unittest.mock.patch.dict(os.environ, env):
            result = legal_entry.call("statute.source_strategy", {},
                                      self.config)
        gap = result["segments"]["paid"]["gap"]
        self.assertEqual(gap["reason"], "PAID_TOKEN_PRESENT_NOT_EXERCISED_IN_V1")
        self.assertEqual(gap["self_collection"], "none")
        self.assertNotIn(secret, json.dumps(result, ensure_ascii=False))

    def test_local_gap_never_escalates_and_declares_named_gap(self):
        result = legal_entry.call(
            "statute.resolve",
            {"wjbs": "1.2.156.3005.6-000", "as_of": "20261015"},
            self.config)
        block = result["degradation"]
        self.assertFalse(block["escalated"])
        self.assertTrue(block["gap_declared"])
        self.assertIn("INVALID_WJBS_FORMAT", ";".join(block["gap_reasons"]))
        self.assertEqual(block["segments"]["local"], "executed")
        self.assertIn("declared_gap_pending_F64-v1.5(B4)",
                      block["segments"]["paid"])
        self.assertIn("declared_gap_pending_F64-v1.5(B4)",
                      block["segments"]["web"])

    def test_zero_url_disclosure_on_all_three_methods(self):
        for method, args in (
                ("statute.source_strategy", {}),
                ("statute.resolve", {"wjbs": "1.2.156.3005.6-000"}),
                ("statute.citation_gate",
                 {"wjbs": "1.2.156.3005.6-000", "as_of": "20261015"})):
            result = legal_entry.call(method, args, self.config)
            self.assertTrue(_no_http_anywhere(result), method)

    def test_strategy_runs_without_codices_config(self):
        # 策略声明面不依赖本地正式面在位
        result = statute_validity.source_strategy({})
        self.assertEqual(result["chain"], ["local", "paid", "web"])


class FailClosedWiringTest(unittest.TestCase):
    def test_resolve_without_config_fails_named(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("statute.resolve",
                             {"wjbs": "1.2.156.3005.6-" + _body("20210820")},
                             {})
        self.assertEqual(str(ctx.exception),
                         "codices_import_path_not_configured")

    def test_resolve_without_formal_root_fails_named(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("statute.resolve",
                             {"wjbs": "1.2.156.3005.6-" + _body("20210820")},
                             {"codices_import_path": str(LCCC_PATH.parent)})
        self.assertEqual(str(ctx.exception),
                         "codices_formal_root_not_configured")

    def test_unknown_statute_method_not_connected(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("statute.verify", {}, self.config_ok())
        self.assertIn("method_not_connected", str(ctx.exception))

    def test_identifier_requires_exactly_one(self):
        for args in ({}, {"wjbs": "a", "code31": "b"}):
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("statute.resolve", args, self.config_ok())
            self.assertEqual(str(ctx.exception),
                             "statute_identifier_exactly_one_required")

    def test_non_dict_args_rejected(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("statute.resolve", ["not", "a", "dict"],
                             self.config_ok())
        self.assertEqual(str(ctx.exception), "statute_params_invalid")

    @staticmethod
    def config_ok():
        return {
            "codices_import_path": str(LCCC_PATH.parent),
            "codices_formal_root": str(build_synthetic_formal_root()),
        }


if __name__ == "__main__":
    unittest.main()
