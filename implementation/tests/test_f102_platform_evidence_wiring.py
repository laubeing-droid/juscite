# -*- coding: utf-8 -*-
"""F102 商标/电商取证八平台（合成先行）产品面接线测试（工单 W5-U05）。

06 V7-102 行（v2；owner=product；UI_HOST_OR_NEW_PRODUCT；B5）
acceptance＝八平台范围冻结真实采集出处/时间/凭证；失败不假造证据。
裁决#13-19（00-总协调.md:254）：八平台统一合成先行，真实平台采集 v2
商业化时补（RECOVERY_POINT 具名）。本面不接入 legal_entry
（UI_HOST_OR_NEW_PRODUCT：不冒已有业务入口）。

合同硬点（本测试主战场）：
  - 八平台闭集冻结：恰 8 成员（CNIPA/百度/淘宝/天猫/京东/拼多多/抖音/
    小红书）＋默认采集序冻结；闭集外平台具名拒；
  - 确定性取证链：单页/两片拼接/多片拼接三路径；重叠裁切后整幅行数
    恰等于内容高；拼接保真（整幅可由目标逐行真值重组）；页号标记带
    ＋页眉带墨迹入金标 bbox（E12 纪律）；最小确定性 PDF（无 /ID 无时
    间戳）；
  - 出处/时间/凭证绑定：source=合成目标具名 provider（synthetic=True、
    usable_as_real_platform_evidence=false）；retrieved_at 出自回执；
    seal=sha256(canonical)可重算；同参数两跑 PDF 逐字节同＋同 seal；
  - E17 EvidenceAttempt 语义：值字段（trajectory/credential/pdf_sha256/
    page_manifest/pdf_bytes）只允许在 EVIDENCE_SEALED 非空；失败路径
    （闭集外/关键词缺/间隔预检/WAF 拦截/未登录/回执残缺/传输异常/适
    配器缺席）恒 None，绝不产部分/合成证据（失败不假造证据）；
  - 反爬攻略：客户端间隔预检（零请求发出）＋目标侧 WAF 闸（检索面）；
  - 面纪律：零网络零子进程零文件 I/O；零 URL 字面量（真实端点禁编
    URL）；legal_entry 零接线；RECOVERY_POINT 具名。

全程合成材料（进程内合成目标＋注入假时钟；零真实外联）。
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import platform_evidence as pe  # noqa: E402
from platform_evidence import (  # noqa: E402
    DEFAULT_CAPTURE_ORDER, EIGHT_PLATFORMS, ENTRY_STATUSES,
    PLATFORM_CONTENT_HEIGHT, RECOVERY_POINT, RASTER_W,
    SYNTHETIC_PROVIDER_ID, VALUE_BEARING_STATUSES,
    PlatformEvidenceSession, SyntheticCaptureTarget,
    content_height_scaled_of, slice_plan,
)

MODULE = ROOT / "python" / "platform_evidence.py"
LEGAL_ENTRY = ROOT / "python" / "legal_entry.py"

SYNTH_SESSION = "synthetic-session-token-not-real"


def _clock_state(start=1000.0):
    return {"now": start}


def _make_world(state=None, seed: int = 20261022):
    state = state or {"now": 1000.0}
    target = SyntheticCaptureTarget(lambda: state["now"], seed=seed)
    sess = PlatformEvidenceSession(target, lambda: state["now"])
    return state, target, sess


def _capture_all(sess, state, keyword="大华"):
    attempts = {}
    for pid in DEFAULT_CAPTURE_ORDER:
        token = SYNTH_SESSION if pe.platform_requires_login(pid) else None
        attempts[pid] = sess.capture(pid, keyword, session_token=token)
        state["now"] += 5
    return attempts


def _value_fields_none(attempt) -> bool:
    return all(attempt.get(key) is None for key in (
        "trajectory", "credential", "pdf_sha256", "page_manifest",
        "pdf_bytes", "retrieved_at"))


class EightPlatformClosedSet(unittest.TestCase):
    """八平台闭集冻结（裁决#13-19 合成常量闭集）。"""

    def test_01_closed_set_exactly_eight_members(self):
        self.assertEqual(len(EIGHT_PLATFORMS), 8)
        self.assertEqual([e[0] for e in EIGHT_PLATFORMS],
                         ["cnipa", "baidu", "taobao", "tmall", "jd",
                          "pdd", "douyin", "xhs"])
        names = {e[1] for e in EIGHT_PLATFORMS}
        for name in ("国家知识产权局（CNIPA）", "百度", "淘宝", "天猫",
                     "京东", "拼多多", "抖音", "小红书"):
            self.assertIn(name, names)

    def test_02_login_flags_frozen_from_source(self):
        flags = {e[0]: e[3] for e in EIGHT_PLATFORMS}
        # 源件参考表：CNIPA SSO＋京东/拼多多/抖音/小红书 需登录。
        self.assertEqual(flags, {"cnipa": True, "baidu": False,
                                 "taobao": False, "tmall": False,
                                 "jd": True, "pdd": True, "douyin": True,
                                 "xhs": True})

    def test_03_default_capture_order_frozen(self):
        self.assertEqual(DEFAULT_CAPTURE_ORDER,
                         ("taobao", "tmall", "jd", "pdd", "douyin",
                          "xhs", "baidu", "cnipa"))
        self.assertEqual(sorted(DEFAULT_CAPTURE_ORDER),
                         sorted(e[0] for e in EIGHT_PLATFORMS))

    def test_04_unknown_platform_rejected_no_evidence(self):
        _, _, sess = _make_world()
        attempt = sess.capture("wechat", "大华")
        self.assertEqual(attempt["status"], "F102_PLATFORM_UNKNOWN")
        self.assertTrue(_value_fields_none(attempt))

    def test_05_keyword_required(self):
        _, _, sess = _make_world()
        for bad in ("", None, 123, "x" * 65):
            attempt = sess.capture("taobao", bad)
            self.assertEqual(attempt["status"], "F102_KEYWORD_REQUIRED")
            self.assertTrue(_value_fields_none(attempt))


class DeterministicEvidenceChain(unittest.TestCase):
    """确定性取证链（截图拼接 PDF＋页号 bbox E12 纪律）。"""

    def test_10_all_eight_sealed_with_bindings(self):
        state, target, sess = _make_world()
        attempts = _capture_all(sess, state)
        for pid, attempt in attempts.items():
            self.assertEqual(attempt["status"], "EVIDENCE_SEALED",
                             (pid, attempt["detail"]))
            self.assertTrue(attempt["synthetic"])
            self.assertFalse(attempt["usable_as_real_platform_evidence"])
            self.assertEqual(attempt["source"]["provider"],
                             SYNTHETIC_PROVIDER_ID)
            self.assertTrue(attempt["trajectory"])
            self.assertEqual(attempt["credential"]["provider"],
                             SYNTHETIC_PROVIDER_ID)
            self.assertEqual(len(attempt["credential"]["seal"]), 64)
            self.assertEqual(attempt["pdf_sha256"],
                             hashlib.sha256(attempt["pdf_bytes"])
                             .hexdigest())
            self.assertTrue(attempt["page_manifest"])
            # 页清单金标版本（E12 bbox 纪律沿袭）逐页在账。
            for page in attempt["page_manifest"]:
                self.assertEqual(page["gold_version"],
                                 pe.PAGE_BBOX_GOLD_VERSION)

    def test_11_three_stitch_paths_covered(self):
        state, _, sess = _make_world()
        attempts = _capture_all(sess, state)
        self.assertEqual(len(attempts["baidu"]["trajectory"]), 1)   # 单片
        self.assertEqual(len(attempts["jd"]["trajectory"]), 2)      # 两片
        self.assertEqual(len(attempts["cnipa"]["trajectory"]), 3)   # 多片

    def test_12_slice_plan_arithmetic(self):
        vp = pe.VIEWPORT_H_CEILING // pe.RASTER_SCALE
        self.assertEqual(slice_plan(100), [(1, 0)])
        self.assertEqual(slice_plan(vp + 100),
                         [(1, 0), (2, vp + 100 - vp)])
        big = vp * 2 + 500
        self.assertEqual(slice_plan(big),
                         [(1, 0), (2, vp), (3, big - vp)])

    def test_13_stitch_fidelity_rows_rebuild_from_target(self):
        """整幅栅格可由目标逐行真值重组（重叠裁切正确性）。"""
        state, target, sess = _make_world()
        attempts = _capture_all(sess, state)
        for pid in ("baidu", "jd", "cnipa"):
            scaled = content_height_scaled_of(pid)
            rebuild = b"".join(target.row_at(pid, "大华", y)
                               for y in range(scaled))
            manifest, rasters = pe._split_pages(rebuild)
            self.assertEqual(
                [p["page_raster_sha256"] for p in manifest],
                [p["page_raster_sha256"] for p in attempts[pid]
                 ["page_manifest"]], pid)

    def test_14_header_and_number_band_gold_bbox(self):
        state, target, sess = _make_world()
        attempts = _capture_all(sess, state)
        attempt = attempts["cnipa"]
        scaled = content_height_scaled_of("cnipa")
        rebuild = b"".join(target.row_at("cnipa", "大华", y)
                           for y in range(scaled))
        # 页眉标记带（黑）＋下缘白行。
        self.assertEqual(rebuild[:pe.HEADER_ROWS * RASTER_W],
                         b"\x00" * (pe.HEADER_ROWS * RASTER_W))
        self.assertEqual(
            rebuild[pe.HEADER_ROWS * RASTER_W:
                    (pe.HEADER_ROWS + 1) * RASTER_W],
            b"\xff" * RASTER_W)
        # 页号标记带墨迹：金标 bbox 行全黑＋上缘行全白；页号 1..N 连续。
        # 页栅格取自 _split_pages 产物（其 sha256 即金标绑定面）。
        _, page_rasters = pe._split_pages(rebuild)
        for page, (raw, width, height) in zip(attempt["page_manifest"],
                                              page_rasters):
            bx0, by0, bx1, by1 = page["number_band_bbox"]
            band = raw[by0 * RASTER_W:by1 * RASTER_W]
            margin = raw[(by0 - 1) * RASTER_W:by0 * RASTER_W]
            self.assertEqual(band, b"\x00" * len(band))
            self.assertEqual(margin, b"\xff" * RASTER_W)
            self.assertEqual(bx1 - bx0, RASTER_W)
            self.assertEqual(by1 - by0, pe.NUMBER_BAND_H)
        self.assertEqual([p["page_no"] for p in attempt["page_manifest"]],
                         list(range(1, len(attempt["page_manifest"]) + 1)))

    def test_15_pdf_structure_deterministic_no_id_no_timestamp(self):
        state, _, sess = _make_world()
        attempts = _capture_all(sess, state)
        pdf = attempts["cnipa"]["pdf_bytes"]
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        # 无 /ID 无时间戳——断言对象结构面（非压缩流字节，避免碰撞误报）。
        trailer_at = pdf.find(b"trailer\n<<")
        self.assertGreater(trailer_at, 0)
        trailer = pdf[trailer_at:pdf.find(b"startxref", trailer_at)]
        self.assertIn(b"/Root 1 0 R", trailer)
        for banned in (b"/ID", b"/CreationDate", b"/ModDate", b"/Info"):
            self.assertNotIn(banned, trailer)
        self.assertNotIn(b"/CreationDate", pdf[:trailer_at])
        n_pages = len(attempts["cnipa"]["page_manifest"])
        self.assertEqual(pdf.count(b"/Type /Page "), n_pages)
        self.assertIn(b"/Filter /FlateDecode", pdf)
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))

    def test_16_same_inputs_same_bytes_same_seal(self):
        state_a, _, sess_a = _make_world({"now": 1000.0})
        state_b, _, sess_b = _make_world({"now": 1000.0})
        a = sess_a.capture("cnipa", "大华", session_token=SYNTH_SESSION)
        b = sess_b.capture("cnipa", "大华", session_token=SYNTH_SESSION)
        self.assertEqual(a["pdf_bytes"], b["pdf_bytes"])
        self.assertEqual(a["credential"]["seal"], b["credential"]["seal"])
        self.assertEqual(a["trajectory"], b["trajectory"])

    def test_17_seal_recomputable_from_attempt(self):
        state, _, sess = _make_world()
        attempt = sess.capture("baidu", "大华")
        seal = hashlib.sha256(json.dumps(
            {"provider": attempt["source"]["provider"],
             "retrieved_at": attempt["retrieved_at"],
             "pdf_sha256": attempt["pdf_sha256"],
             "pages": attempt["credential"]["pages_digest"]},
            ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        self.assertEqual(seal, attempt["credential"]["seal"])


class AntiCrawlPolicies(unittest.TestCase):
    """反爬攻略合成保真：间隔预检（零请求）＋目标侧 WAF＋登录闸。"""

    def test_20_pacing_precheck_zero_fetch(self):
        state, target, sess = _make_world()
        first = sess.capture("taobao", "大华")
        self.assertEqual(first["status"], "EVIDENCE_SEALED")
        before = (target.measure_count, target.fetch_count)
        second = sess.capture("tmall", "大华")     # 同刻连发
        self.assertEqual(second["status"], "F102_PACING_VIOLATED")
        self.assertTrue(_value_fields_none(second))
        after = (target.measure_count, target.fetch_count)
        self.assertEqual(before, after)            # 零请求发出

    def test_21_pacing_released_after_interval(self):
        state, _, sess = _make_world()
        sess.capture("taobao", "大华")
        state["now"] += pe.MIN_INTERVAL_S
        attempt = sess.capture("tmall", "大华")
        self.assertEqual(attempt["status"], "EVIDENCE_SEALED")

    def test_22_target_waf_intercepts_frequent_search(self):
        state, target, _ = _make_world()
        r1 = target.measure("tmall", "大华", None)
        self.assertFalse(r1.get("blocked"))
        state["now"] += 1                          # < MIN_INTERVAL_S
        r2 = target.measure("tmall", "大华", None)
        self.assertTrue(r2.get("blocked"))
        self.assertEqual(r2.get("reason"), "waf_rate_limit")

    def test_23_waf_blocked_receipt_yields_no_evidence(self):
        state, _, _ = _make_world()

        class WafTransport:
            def __init__(self, inner):
                self.inner = inner

            def measure(self, *args, **kwargs):
                return {"provider": SYNTHETIC_PROVIDER_ID,
                        "kind": "measure", "synthetic": True,
                        "blocked": True, "reason": "waf_rate_limit"}

            def fetch_slice(self, *args, **kwargs):
                return self.inner.fetch_slice(*args, **kwargs)

        sess = PlatformEvidenceSession(
            WafTransport(SyntheticCaptureTarget(lambda: state["now"])),
            lambda: state["now"])
        attempt = sess.capture("taobao", "大华")
        self.assertEqual(attempt["status"], "F102_WAF_INTERCEPT")
        self.assertTrue(_value_fields_none(attempt))

    def test_24_login_required_platform_without_session(self):
        state, target, sess = _make_world()
        before = (target.measure_count, target.fetch_count)
        attempt = sess.capture("jd", "大华")
        self.assertEqual(attempt["status"], "F102_LOGIN_REQUIRED")
        self.assertTrue(_value_fields_none(attempt))
        self.assertEqual(before, (target.measure_count,
                                  target.fetch_count))
        # 目标侧同闸为防线：直连无 session 请求被拦（防线可达）。
        direct = target.measure("jd", "大华", None)
        self.assertTrue(direct.get("blocked"))
        self.assertEqual(direct.get("reason"), "login_required")

    def test_25_login_platform_with_session_passes(self):
        state, _, sess = _make_world()
        attempt = sess.capture("jd", "大华", session_token=SYNTH_SESSION)
        self.assertEqual(attempt["status"], "EVIDENCE_SEALED")


class FailureFakesNothing(unittest.TestCase):
    """失败不假造证据（E17 EvidenceAttempt 语义）。"""

    def test_30_adapter_absent_structurally_unreachable(self):
        _, _, sess = _make_world()
        sess.transport = None
        attempt = sess.capture("taobao", "大华")
        self.assertEqual(attempt["status"], "F102_ADAPTER_ABSENT")
        self.assertTrue(_value_fields_none(attempt))

    def test_31_receipt_invalid_no_partial_evidence(self):
        class BadTransport:
            def measure(self, *args, **kwargs):
                return {"kind": "measure", "synthetic": True,
                        "retrieved_at": "2026-10-22T00:00:00Z",
                        "content_height": 3580}    # 缺 provider

            def fetch_slice(self, *args, **kwargs):
                raise AssertionError("unreachable")

        _, _, sess = _make_world()
        sess.transport = BadTransport()
        attempt = sess.capture("baidu", "大华")
        self.assertEqual(attempt["status"], "F102_RECEIPT_INVALID")
        self.assertTrue(_value_fields_none(attempt))

    def test_32_mid_pipeline_failure_no_partial_pdf(self):
        class HalfTransport:
            def __init__(self, inner):
                self.inner = inner
                self.calls = 0

            def measure(self, *args, **kwargs):
                return self.inner.measure(*args, **kwargs)

            def fetch_slice(self, *args, **kwargs):
                self.calls += 1
                if self.calls >= 2:
                    raise OSError("boom")
                return self.inner.fetch_slice(*args, **kwargs)

        state, target, _ = _make_world()
        sess = PlatformEvidenceSession(
            HalfTransport(SyntheticCaptureTarget(lambda: state["now"])),
            lambda: state["now"])
        attempt = sess.capture("jd", "大华", session_token=SYNTH_SESSION)
        self.assertEqual(attempt["status"], "F102_CAPTURE_FAILED")
        self.assertTrue(_value_fields_none(attempt))

    def test_33_values_only_on_sealed_global_invariant(self):
        state, _, sess = _make_world()
        attempts = [
            sess.capture("wechat", "大华"),
            sess.capture("taobao", ""),
            sess.capture("taobao", "大华"),
            sess.capture("taobao", "大华"),        # 间隔预检
        ]
        state["now"] += pe.MIN_INTERVAL_S
        attempts.append(sess.capture("jd", "大华"))  # 未登录
        attempts.append(sess.capture("baidu", "大华"))  # 正道
        for attempt in attempts:
            if attempt["status"] in VALUE_BEARING_STATUSES:
                self.assertTrue(attempt["status"] == "EVIDENCE_SEALED"
                                and attempt["trajectory"] is not None
                                and attempt["credential"] is not None
                                and attempt["pdf_sha256"] is not None
                                and attempt["page_manifest"] is not None)
            else:
                self.assertTrue(_value_fields_none(attempt),
                                attempt["status"])

    def test_34_status_closed_set_shape(self):
        self.assertIn("EVIDENCE_SEALED", ENTRY_STATUSES)
        self.assertEqual(VALUE_BEARING_STATUSES, ("EVIDENCE_SEALED",))
        for status in ENTRY_STATUSES:
            if status not in VALUE_BEARING_STATUSES:
                self.assertTrue(status.startswith("F102_"))


class FaceDiscipline(unittest.TestCase):
    """面纪律：AST 闭集/零 URL/零接线/回收点具名。"""

    def test_40_ast_import_closed_set_zero_io(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        allowed = {"__future__", "hashlib", "json", "time", "zlib"}
        imports = set()
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0]
                               for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func,
                                                           ast.Name):
                calls.append(node.func.id)
        self.assertTrue(imports <= allowed,
                        "越界导入：%s" % (imports - allowed))
        for banned in ("print", "open"):
            self.assertNotIn(banned, calls)
        for banned in ("urllib", "socket", "http", "ssl", "ftplib",
                       "requests", "httpx", "subprocess", "logging",
                       "os", "pathlib"):
            self.assertNotIn(banned, imports)

    def test_41_zero_url_literals_in_module(self):
        source = MODULE.read_text(encoding="utf-8")
        for marker in ("http://", "https://", "www.", ".com/", ".cn/"):
            self.assertNotIn(marker, source, marker)

    def test_42_legal_entry_zero_wiring(self):
        text = LEGAL_ENTRY.read_text(encoding="utf-8")
        self.assertNotIn("platform_evidence", text)
        self.assertNotIn("f102", text.lower())

    def test_43_recovery_point_named(self):
        self.assertIn("v2 商业化时补", RECOVERY_POINT)
        self.assertIn("禁编 URL", RECOVERY_POINT)
        self.assertIn("E24", RECOVERY_POINT)

    def test_44_synthetic_named_everywhere(self):
        self.assertEqual(SYNTHETIC_PROVIDER_ID, "synthetic-local-target")
        self.assertIn("synthetic", SYNTHETIC_PROVIDER_ID)
        # 合成页内容高是合成世界常量（非真实测量）——闭集一致。
        self.assertEqual(sorted(PLATFORM_CONTENT_HEIGHT),
                         sorted(e[0] for e in EIGHT_PLATFORMS))


if __name__ == "__main__":
    unittest.main()
