"""W2b-U13 / F50+F51 wiring: 引用原文重锚定＋引用前逐字核验
（anchor.* 桥方法组 → document_anchor 产品面 document-adapter）。

义务 06:F50 断言：「定位一律引用原文重锚定、禁偏移换算；插入后按原文
重锚仍定位正确；零/多命中不以偏移强改」。
义务 06:F51 断言：「引用前逐字核验（NOT FOUND 禁呈现，不就近匹配）；
引用逐字定位成功才改；NOT_FOUND 拒自动修改并给人工入口」。

反例集（工单钦定）：同形文本多命中／近形文本零命中逐字对账。语料全
合成（00-总协调 §6.1 裁决#1）。
"""
import ast
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected  # noqa: E402

MODULE_PATH = Path(__file__).resolve().parents[1] / 'python' \
    / 'document_anchor.py'

T0 = (
    "合成测试合同（F50-F51-TEST，全部内容虚构）\n"
    "3.1 合同总价款为人民币360,000.00元。\n"
    "3.2 甲方应在验收合格后三十日内支付当期价款。\n"
    "4.1 乙方应于2026年12月31日前完成交付。\n"
)
QUOTE = "甲方应在验收合格后三十日内支付当期价款。"
INSERT = "3.0 本合同价款含税费。\n"
REPL = "甲方应在验收合格后四十五日内支付当期价款。"

MEMO = (
    "合成备忘录（F50-F51-TEST）\n"
    "决议一：Party A shall pay within 30 days.\n"
    "决议二：合同金额小写 360,000.00 元。\n"
)
QUOTE_EN = "Party A shall pay within 30 days."
QUOTE_AMT = "合同金额小写 360,000.00 元。"


def _cfg(state_root):
    return {"anchor_state_root": str(state_root)}


def _register(cfg, document_id="doc-t", quote=QUOTE, text=T0,
              matter_id="M-SYN"):
    return call("anchor.register",
                {"document_id": document_id, "matter_id": matter_id,
                 "quote": quote, "text": text}, cfg)


def _locate(cfg, anchor_id, text, document_id="doc-t"):
    return call("anchor.locate",
                {"document_id": document_id, "anchor_id": anchor_id,
                 "text": text}, cfg)


def _gate(cfg, anchor_id, text, replacement=None, document_id="doc-t"):
    args = {"document_id": document_id, "anchor_id": anchor_id,
            "text": text}
    if replacement is not None:
        args["replacement"] = replacement
    return call("anchor.gate_edit", args, cfg)


def _strip_utc(obj):
    if isinstance(obj, dict):
        return {k: _strip_utc(v) for k, v in obj.items()
                if not k.endswith("_utc")}
    if isinstance(obj, list):
        return [_strip_utc(v) for v in obj]
    return obj


class AnchorReanchorTests(unittest.TestCase):
    """F50 重锚定：插入/删除后按原文重搜仍定位正确；登记幂等＋溯源不变。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="f50-reanchor-"))
        self.cfg = _cfg(self.tmp)

    def test_register_span_and_idempotent(self):
        reg = _register(self.cfg)
        expected = T0.find(QUOTE)
        self.assertEqual(reg["registered_span"],
                         [expected, expected + len(QUOTE)])
        self.assertEqual(reg["registered_matches"], 1)
        anchors_json = self.tmp / "document-anchor" / "doc-t" / "anchors.json"
        before = anchors_json.read_bytes()
        again = _register(self.cfg)
        self.assertEqual(again["anchor_id"], reg["anchor_id"])
        self.assertTrue(again["idempotent"])
        self.assertEqual(anchors_json.read_bytes(), before)  # 不双登

    def test_insertion_before_after_and_deletion(self):
        anchor_id = _register(self.cfg)["anchor_id"]
        t_before = T0.replace("3.1 ", INSERT + "3.1 ", 1)
        v = _locate(self.cfg, anchor_id, t_before)["verbatim"]
        self.assertEqual(v["status"], "LOCATED")
        self.assertEqual(v["matches"], 1)
        self.assertEqual(v["span"], [t_before.find(QUOTE),
                                     t_before.find(QUOTE) + len(QUOTE)])
        self.assertEqual(v["shift"], len(INSERT))       # 位移由重搜吸收
        self.assertEqual(v["position_source"], "verbatim_quote_match")
        self.assertFalse(v["offset_conversion_used"])
        # 锚后插入 → shift 0（在原始 T0 上追加）
        v_after = _locate(self.cfg, anchor_id,
                          T0 + "附则：一式两份。\n")["verbatim"]
        self.assertEqual(v_after["shift"], 0)
        # 锚前删除 → shift 为负
        chunk = "3.1 合同总价款为人民币360,000.00元。\n"
        v_del = _locate(self.cfg, anchor_id,
                        T0.replace(chunk, "", 1))["verbatim"]
        self.assertEqual(v_del["shift"], -len(chunk))

    def test_provenance_immutable_and_reregistration_conflict(self):
        reg = _register(self.cfg)
        t1 = T0.replace("3.1 ", INSERT + "3.1 ", 1)
        _locate(self.cfg, reg["anchor_id"], t1)          # 重锚不写账
        with self.assertRaises(NotConnected) as ctx:
            _register(self.cfg, text=t1)                 # 同键异文本
        self.assertIn("f50_anchor_reregistration_conflict",
                      str(ctx.exception))
        read_back = call("anchor.read",
                         {"document_id": "doc-t",
                          "anchor_id": reg["anchor_id"]}, self.cfg)
        self.assertEqual(read_back["registered_span"],
                         reg["registered_span"])          # 溯源不变
        self.assertEqual(read_back["text_sha256"], reg["text_sha256"])


class CounterexampleTests(unittest.TestCase):
    """反例集：同形多命中／近形零命中逐字对账（禁偏移强改＝零位置字段）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="f50-counter-"))
        self.cfg = _cfg(self.tmp)
        self.anchor_id = _register(self.cfg)["anchor_id"]
        self.reg_span = T0.find(QUOTE)

    def test_same_shape_multi_hit_refuses_without_span(self):
        t1 = T0.replace("3.1 ", INSERT + "3.1 ", 1)
        t2 = t1 + "\n备注（复述）：" + QUOTE + "\n"
        hits = []
        start = 0
        while (idx := t2.find(QUOTE, start)) >= 0:
            hits.append(idx)
            start = idx + 1
        self.assertEqual(len(hits), 2)
        offset_guess = self.reg_span + len(INSERT)   # 偏移换算值本可得
        self.assertIn(offset_guess, hits)            # 且恰为真命中之一
        v = _locate(self.cfg, self.anchor_id, t2)["verbatim"]
        self.assertEqual(v["status"], "AMBIGUOUS")
        self.assertEqual(v["matches"], 2)
        for key in ("span", "shift", "position_source"):
            self.assertNotIn(key, v)                 # 零位置字段

    def test_near_shape_zero_hit_variants(self):
        t1 = T0.replace("3.1 ", INSERT + "3.1 ", 1)
        variants = {
            "一字之差": t1.replace("三十日", "45日", 1),
            "引文内换行": t1.replace(QUOTE, QUOTE.replace("支付", "支付\n"), 1),
            "全角句号": t1.replace(QUOTE, QUOTE[:-1] + "．", 1),
        }
        for name, text in variants.items():
            with self.subTest(variant=name):
                v = _locate(self.cfg, self.anchor_id, text)["verbatim"]
                self.assertEqual(v["status"], "NOT_FOUND")
                self.assertEqual(v["matches"], 0)
                self.assertNotIn("span", v)
        # 文本比登记 span 更长——偏移换算本可返回陈旧位置，本面不给
        for name, text in variants.items():
            self.assertGreater(len(text), self.reg_span + len(QUOTE))

    def test_fullwidth_halfwidth_not_folded(self):
        memo_anchor = _register(self.cfg, document_id="doc-m",
                                quote=QUOTE_AMT, text=MEMO)["anchor_id"]
        fw = MEMO.replace("360,000.00", "360，000.00", 1)
        v = _locate(self.cfg, memo_anchor, fw, document_id="doc-m")[
            "verbatim"]
        self.assertEqual(v["status"], "NOT_FOUND")

    def test_ascii_case_not_folded(self):
        anchor = _register(self.cfg, document_id="doc-e",
                           quote=QUOTE_EN, text=MEMO)["anchor_id"]
        lowered = MEMO.replace(QUOTE_EN, QUOTE_EN.lower(), 1)
        v = _locate(self.cfg, anchor, lowered, document_id="doc-e")[
            "verbatim"]
        self.assertEqual(v["status"], "NOT_FOUND")

    def test_overlap_hits_counted_strictly(self):
        # "aa" 在 "aaa" 重叠命中 2 次 → 登记即拒（同形从严）
        with self.assertRaises(NotConnected) as ctx:
            _register(self.cfg, document_id="doc-ov", quote="aa",
                      text="aaa")
        self.assertIn("f50_anchor_ambiguous", str(ctx.exception))

    def test_register_refuses_missing_quote(self):
        with self.assertRaises(NotConnected) as ctx:
            _register(self.cfg, document_id="doc-miss",
                      quote="本引文不存在（合成反例）", text=T0)
        self.assertIn("f50_anchor_not_found", str(ctx.exception))


class GateTests(unittest.TestCase):
    """F51 引用前逐字核验＋改动闸：定位成功才改；拒改给人工入口。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="f51-gate-"))
        self.cfg = _cfg(self.tmp)
        self.anchor_id = _register(self.cfg)["anchor_id"]

    def test_verify_only_mode(self):
        out = _gate(self.cfg, self.anchor_id, T0)      # 无 replacement
        self.assertEqual(out["verbatim"]["status"], "LOCATED")
        self.assertEqual(out["gate"]["mode"], "verify_only")
        self.assertIsNone(out["gate"]["auto_edit"])
        # 纯核验不落人工入口
        queue = call("anchor.manual_queue",
                     {"document_id": "doc-t"}, self.cfg)
        self.assertEqual(queue["entries"], [])

    def test_proceed_builds_proposed_text(self):
        out = _gate(self.cfg, self.anchor_id, T0, replacement=REPL)
        self.assertEqual(out["gate"]["status"], "PROCEED")
        self.assertEqual(out["gate"]["auto_edit"],
                         "permitted_verbatim_located")
        self.assertEqual(out["gate"]["proposed_text"],
                         T0.replace(QUOTE, REPL, 1))   # 独立复算
        self.assertEqual(out["gate"]["replacement_span"],
                         out["verbatim"]["span"])

    def test_not_found_refused_with_manual_entry(self):
        near = T0.replace("三十日", "45日", 1)
        out = _gate(self.cfg, self.anchor_id, near, replacement=REPL)
        self.assertEqual(out["gate"]["status"], "NOT_FOUND_REFUSED")
        self.assertEqual(out["gate"]["auto_edit"], "refused")
        self.assertNotIn("proposed_text", out["gate"])   # 拒自动修改
        self.assertNotIn("span", out["verbatim"])        # 零位置字段
        entry_id = out["gate"]["manual_entry_id"]
        # 同内容幂等；异拟改文追加
        again = _gate(self.cfg, self.anchor_id, near, replacement=REPL)
        self.assertEqual(again["gate"]["manual_entry_id"], entry_id)
        _gate(self.cfg, self.anchor_id, near, replacement="二号方案")
        queue = call("anchor.manual_queue",
                     {"document_id": "doc-t"}, self.cfg)
        self.assertEqual(len(queue["entries"]), 2)
        first = queue["entries"][0]
        self.assertEqual(first["reason"], "not_found")
        self.assertEqual(first["quote"], QUOTE)
        self.assertEqual(first["replacement"], REPL)
        self.assertEqual(first["status"], "pending")

    def test_ambiguous_refused_with_manual_entry(self):
        dup = T0 + "\n复述：" + QUOTE + "\n"
        out = _gate(self.cfg, self.anchor_id, dup, replacement=REPL)
        self.assertEqual(out["verbatim"]["status"], "AMBIGUOUS")
        self.assertEqual(out["gate"]["status"], "AMBIGUOUS_REFUSED")
        self.assertNotIn("proposed_text", out["gate"])
        queue = call("anchor.manual_queue",
                     {"document_id": "doc-t"}, self.cfg)
        self.assertEqual(queue["entries"][0]["reason"], "ambiguous")

    def test_manual_entry_closed_fields(self):
        near = T0.replace("三十日", "45日", 1)
        _gate(self.cfg, self.anchor_id, near, replacement=REPL)
        queue = call("anchor.manual_queue",
                     {"document_id": "doc-t"}, self.cfg)
        closed = {"schema", "manual_entry_id", "anchor_id", "document_id",
                  "matter_id", "reason", "quote", "replacement",
                  "text_sha256", "status", "created_utc"}
        for entry in queue["entries"]:
            self.assertLessEqual(set(entry.keys()), closed)
            self.assertIn(entry["reason"], ("not_found", "ambiguous"))
            self.assertEqual(entry["status"], "pending")


class BridgeFailClosedTests(unittest.TestCase):
    """桥面 fail-closed：缺配置/未知方法/坏 id/未登记锚；错误码纯码。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="f50-bridge-"))
        self.cfg = _cfg(self.tmp)

    def test_state_root_required(self):
        with self.assertRaises(NotConnected) as ctx:
            call("anchor.register",
                 {"document_id": "d", "quote": "x", "text": "x"}, {})
        self.assertIn("f50_state_root_not_configured", str(ctx.exception))

    def test_unknown_method_frozen_group(self):
        with self.assertRaises(NotConnected) as ctx:
            call("anchor.explode", {}, self.cfg)
        self.assertIn("method_not_connected:anchor.explode",
                      str(ctx.exception))

    def test_bad_document_id(self):
        with self.assertRaises(NotConnected) as ctx:
            call("anchor.register",
                 {"document_id": "../escape", "quote": "x", "text": "x"},
                 self.cfg)
        self.assertIn("f50_document_id_invalid", str(ctx.exception))

    def test_unregistered_anchor(self):
        with self.assertRaises(NotConnected) as ctx:
            call("anchor.locate",
                 {"document_id": "doc-t", "anchor_id": "a-0000000000000000",
                  "text": T0}, self.cfg)
        self.assertIn("f50_anchor_not_registered", str(ctx.exception))

    def test_error_codes_carry_no_material(self):
        import re
        probes = []
        try:
            call("anchor.register", {"document_id": "d", "quote": "机密引文",
                                     "text": "无此文本"}, self.cfg)
        except NotConnected as exc:
            probes.append(str(exc))
        try:
            call("anchor.gate_edit",
                 {"document_id": "doc-t", "anchor_id": "a-x", "text": T0,
                  "replacement": "R"}, self.cfg)
        except NotConnected as exc:
            probes.append(str(exc))
        shape = re.compile(r"^[\w:.;-]+$")
        for code in probes:
            self.assertTrue(shape.match(code), code)   # 纯码不带材料
            self.assertNotIn("机密引文", code)


class DeterminismTests(unittest.TestCase):
    """确定性：两状态根同序列同输出；AST 导入闭集＋无模糊匹配面。"""

    def test_two_state_roots_same_outputs(self):
        outs = []
        for i in range(2):
            tmp = Path(tempfile.mkdtemp(prefix=f"f50-det{i}-"))
            cfg = _cfg(tmp)
            reg = _register(cfg)
            v = _locate(cfg, reg["anchor_id"],
                        T0.replace("3.1 ", INSERT + "3.1 ", 1))["verbatim"]
            gate = _gate(cfg, reg["anchor_id"],
                         T0.replace("三十日", "45日", 1),
                         replacement=REPL)["gate"]
            outs.append(_strip_utc([reg, v, gate]))
        self.assertEqual(outs[0], outs[1])
        # anchor_id 确定性派生（文档＋quote）
        self.assertTrue(outs[0][0]["anchor_id"].startswith("a-"))

    def test_ast_import_whitelist_and_no_fuzzy_surface(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        allowed = {"__future__", "hashlib", "json", "os", "re", "threading",
                   "datetime", "pathlib"}
        self.assertLessEqual(imports, allowed)
        self.assertFalse(imports & {"random", "urllib", "socket", "http",
                                    "requests", "difflib"})
        banned = {"get_close_matches", "SequenceMatcher", "fuzz"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                self.assertNotIn(name, banned)   # 不就近匹配＝结构性缺席


if __name__ == "__main__":
    unittest.main()
