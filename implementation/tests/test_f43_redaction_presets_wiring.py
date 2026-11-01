"""W4-U36 / F43 脱敏策略预设桥面测试：冻结方法组、fail-closed 配置面、
策略裁决绑定与每案共享假名经桥同进程闭环（anonymizer 仓 w4-u36 分支
redaction_presets_service 公开面；落 W2a-U15 既有面扩展，不建第二权威）。

真 OCR 闸链与双 profile 验收由 tools/PENDING_OWNER_f43_redaction_presets_recon.py
承担；此处为引擎无关的桥面合同（全部合成材料）。
"""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))

_SRC = os.environ.get("JUSCITE_ANONYMIZER_SRC")
if not _SRC:
    # 同波 worktree 相对推断（与 recon 工具同式）：裸跑验收命令也能命中
    # w4-u36 分支源（W4 链头＋W2a-U15 附件闸面＋本单 F43 面），而非全局
    # .pth 指向的其他分支检出。向上搜索而非固定深度（W2a-U17 合并时公开
    # 改口：两布局命中同一目标路径）。
    _root = next((_p for _p in Path(__file__).resolve().parents
                  if (_p / "legal-cn-anonymizer工作区").is_dir()), None)
    _guess = (_root / "legal-cn-anonymizer工作区"
              / "legal-cn-anonymizer" / ".local" / "worktrees" / "w4-u36"
              / "src") if _root else None
    if _guess and (_guess / "legal_anonymizer" / "application"
                   / "redaction_presets_service.py").is_file():
        _SRC = str(_guess)
if _SRC:
    sys.path.insert(0, _SRC)

_rps = None
try:
    from legal_anonymizer.application import (
        redaction_presets_service as _rps,
    )
except ImportError:                                    # pragma: no cover
    _rps = None
if _rps is None and _SRC:
    # 全套跑时字母序更早的测试可能已把其他分支检出缓存进 sys.modules；
    # 逐出后按本文件的钉定路径重导入（保持本桥面测试对 w4-u36 面封闭）。
    import importlib
    for _mod in [m for m in sys.modules if m == "legal_anonymizer"
                 or m.startswith("legal_anonymizer.")]:
        del sys.modules[_mod]
    try:
        _rps = importlib.import_module(
            "legal_anonymizer.application.redaction_presets_service")
    except ImportError:                                # pragma: no cover
        _rps = None

from legal_entry import call, NotConnected, REDACTION_PRESET_METHODS

PHONE = "13700005555"
NAME = "张三丰"


def _cfg(state_root, **extra):
    config = {"anonymizer_contract": "p09/p10",
              "attachment_gate_state_root": str(state_root)}
    config.update(extra)
    return config


def _canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


@unittest.skipIf(_rps is None, "anonymizer w4-u36 src not importable")
def _pin_face():
    """运行时钉定本波面（与 test_f38_f44 同式）。全套单进程内多波桥测试
    共存（U15 attachment 面在 w2a-u15、U16 batch 面在 w2a-u16、本单 F43 面
    在 w4-u36——平行分支互含超集不同），各文件类级 setUpClass 重钉保证
    legal_entry 桥内延迟 import 恒命中本波面。"""
    if not _SRC:
        return None
    sys.path.insert(0, _SRC)  # 本波面提到 path 最前（他波后插入者会压前）
    import importlib
    for m in [m for m in sys.modules if m == "legal_anonymizer"
              or m.startswith("legal_anonymizer.")]:
        del sys.modules[m]
    return importlib.import_module(
        "legal_anonymizer.application.redaction_presets_service")


@unittest.skipIf(_rps is None, "anonymizer w4-u36 src not importable")
class TestF43PresetsRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_face()

    def test_frozen_group_and_one_to_one_scopes(self):
        self.assertEqual(
            sorted(REDACTION_PRESET_METHODS),
            ["redaction.deidentify_matter", "redaction.presets",
             "redaction.pseudonym_resolve", "redaction.rehydrate_matter"])
        reg = call("redaction.presets", {}, _cfg(self.tmp))
        self.assertEqual([p["preset"] for p in reg["presets"]],
                         ["external_send", "internal_analysis",
                          "public_release"])
        self.assertEqual(len({p["egress_scope"] for p in reg["presets"]}), 3)
        strict = [p["preset"] for p in reg["presets"] if p["strictest"]]
        self.assertEqual(strict, ["external_send"])   # 对外发送=最严（唯一）

    def test_registry_digest_deterministic_canonical(self):
        a = call("redaction.presets", {}, _cfg(self.tmp))
        b = call("redaction.presets", {}, _cfg(self.tmp))
        self.assertEqual(_canonical(a), _canonical(b))
        for entry in a["presets"]:
            import hashlib
            body = {k: v for k, v in entry.items()
                    if k not in ("config_sha256", "override_active")}
            self.assertEqual(entry["config_sha256"], hashlib.sha256(
                _canonical(body).encode("utf-8")).hexdigest())

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="f43-wiring-"))


@unittest.skipIf(_rps is None, "anonymizer w4-u36 src not importable")
class TestF43BridgeFailClosed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_face()

    def test_contract_and_state_root_required(self):
        with self.assertRaises(NotConnected) as cm:
            call("redaction.presets", {}, {"anonymizer_contract": "wrong"})
        self.assertIn("anonymizer_p09_p10_not_configured",
                      str(cm.exception))
        with self.assertRaises(NotConnected) as cm2:
            call("redaction.presets", {},
                 {"anonymizer_contract": "p09/p10"})
        self.assertIn("attachment_gate_state_root_not_configured",
                      str(cm2.exception))

    def test_invalid_preset_matter_items_typed(self):
        for method, args, code in [
            ("redaction.deidentify_matter",
             {"matter_id": "m", "preset": "bogus", "text": "x"},
             "redaction_preset_invalid"),
            ("redaction.deidentify_matter",
             {"preset": "external_send", "text": "x"},
             "redaction_preset_matter_id_required"),
            ("redaction.deidentify_matter",
             {"matter_id": "m", "preset": "external_send"},
             "redaction_preset_text_required"),
            ("redaction.pseudonym_resolve",
             {"matter_id": "m", "preset": "external_send", "items": []},
             "redaction_preset_items_invalid"),
            ("redaction.rehydrate_matter",
             {"matter_id": "m-none", "preset": "external_send", "text": "x"},
             "redaction_preset_failed:redaction_preset_no_map"),
        ]:
            with self.assertRaises(NotConnected) as cm:
                call(method, args, _cfg(self.tmp))
            self.assertIn(code, str(cm.exception), f"{method} {args}")

    def test_bad_override_surfaces_as_owner_code(self):
        (self.tmp / "redaction_presets").mkdir(parents=True)
        (self.tmp / "redaction_presets" / "external_send.json").write_text(
            "{broken", encoding="utf-8")
        with self.assertRaises(NotConnected) as cm:
            call("redaction.presets", {}, _cfg(self.tmp))
        self.assertIn("redaction_preset_failed:redaction_preset_config_invalid",
                      str(cm.exception))

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="f43-wiring-"))


@unittest.skipIf(_rps is None, "anonymizer w4-u36 src not importable")
class TestF43PseudonymsViaBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_face()

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="f43-wiring-"))

    def test_deidentify_redacts_contact_and_shares_tokens(self):
        # 桥面缺省＝规则层（NER 资格事实独立，REVIEW_REQUIRED 语义沿 E11）：
        # 联系方式/证件恒脱；人名属 NER 层不在此断言（不假称已脱）。
        text = f"委托人已确认（电话 {PHONE}）同意代理。"
        a = call("redaction.deidentify_matter",
                 {"matter_id": "m", "preset": "internal_analysis",
                  "text": text}, _cfg(self.tmp))
        b = call("redaction.deidentify_matter",
                 {"matter_id": "m", "preset": "external_send", "text": text},
                 _cfg(self.tmp))
        self.assertNotIn(PHONE, a["sanitized_text"])   # 联系方式恒脱
        self.assertEqual(a["policy"], "balanced")
        self.assertEqual(b["policy"], "max")
        import re
        toks_a = sorted(set(re.findall(
            r"PHONE_\d+|R_\d+", a["sanitized_text"])))
        toks_b = sorted(set(re.findall(
            r"PHONE_\d+|R_\d+", b["sanitized_text"])))
        self.assertTrue(toks_a)
        self.assertEqual(toks_a, toks_b)               # 共享库：跨策略同 token
        self.assertEqual(a["map_sha256"], b["map_sha256"])
        # 映射零回显：响应剥离出域形态文本后，零 surface/零映射表内容
        body = _canonical({k: v for k, v in a.items()
                           if k != "sanitized_text"})
        self.assertNotIn(PHONE, body)

    def test_resolve_token_only_and_cross_strategy_consistency(self):
        r1 = call("redaction.pseudonym_resolve",
                  {"matter_id": "m", "preset": "internal_analysis",
                   "items": [{"surface": NAME, "category": "person"},
                             {"surface": PHONE, "category": "contact",
                              "kind": "cn-mobile"}]}, _cfg(self.tmp))
        self.assertEqual(len(r1["tokens"]), 2)
        self.assertNotIn(NAME, _canonical(r1))         # token-only，零 surface
        r2 = call("redaction.pseudonym_resolve",
                  {"matter_id": "m", "preset": "public_release",
                   "items": [{"surface": NAME, "category": "person"}]},
                  _cfg(self.tmp))
        self.assertEqual(r2["tokens"], [r1["tokens"][0]])  # 跨策略一致

    def test_rehydrate_matter_only_and_cross_matter_unreachable(self):
        text = f"委托人{NAME}（电话 {PHONE}）同意代理。"
        m1 = call("redaction.deidentify_matter",
                  {"matter_id": "m-1", "preset": "internal_analysis",
                   "text": text}, _cfg(self.tmp))
        call("redaction.deidentify_matter",
             {"matter_id": "m-2", "preset": "internal_analysis",
              "text": "无敏感项文本。"}, _cfg(self.tmp))
        import re
        phone_tok = re.findall(r"PHONE_\d+", m1["sanitized_text"])
        self.assertTrue(phone_tok)
        # 他案库还原本案独有 token → 原文不动（跨案结构性不可达）
        cross = call("redaction.rehydrate_matter",
                     {"matter_id": "m-2", "preset": "internal_analysis",
                      "text": phone_tok[0]}, _cfg(self.tmp))
        self.assertEqual(cross["text"], phone_tok[0])
        self.assertEqual(cross["resolved_count"], 0)
        # 本案还原正常
        own = call("redaction.rehydrate_matter",
                   {"matter_id": "m-1", "preset": "internal_analysis",
                    "text": m1["sanitized_text"]}, _cfg(self.tmp))
        self.assertIn(PHONE, own["text"])
        self.assertGreaterEqual(own["resolved_count"], 1)


@unittest.skipIf(_rps is None, "anonymizer w4-u36 src not importable")
class TestF43AuthorizeBindingViaBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_face()

    """授权面策略裁决经桥（crafted 闸门状态；真闸链归 recon 全链）。"""

    def setUp(self):
        import hashlib
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="f43-wiring-"))
        att = self.tmp / "attachments" / "m" / "a"
        att.mkdir(parents=True)
        burned = b"burned-bytes"
        (att / "burned.pdf").write_bytes(burned)
        binding = call("redaction.presets", {}, _cfg(self.tmp))["presets"][0]
        self.binding = binding
        verdict = {"matter_id": "m", "attachment_id": "a",
                   "verdict": "AUTHORIZED", "reasons": [],
                   "generated_at": "2026-10-20T00:00:00Z",
                   "egress_authorized": True,
                   "bound_sha256": hashlib.sha256(burned).hexdigest(),
                   "policy_binding": {
                       "preset": binding["preset"],
                       "egress_scope": binding["egress_scope"],
                       "config_sha256": binding["config_sha256"],
                       "vault_policy": binding["vault_policy"],
                       "strictest": binding["strictest"],
                       "allow_rehydrate": binding["allow_rehydrate"]}}
        (att / "verdict.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=1),
            encoding="utf-8")

    def test_scope_match_authorized_mismatch_refused(self):
        ok = call("attachment.authorize",
                  {"matter_id": "m", "attachment_id": "a",
                   "egress_scope": "external_send"}, _cfg(self.tmp))
        self.assertEqual(ok["decision"], "AUTHORIZED")
        self.assertEqual(ok["policy_binding"]["egress_scope"], "external_send")
        mis = call("attachment.authorize",
                   {"matter_id": "m", "attachment_id": "a",
                    "egress_scope": "public_release"}, _cfg(self.tmp))
        self.assertEqual(mis["decision"], "REFUSED")
        self.assertEqual(mis["reason"], "policy_scope_mismatch")

    def test_v1_path_unchanged_without_scope(self):
        v1 = call("attachment.authorize",
                  {"matter_id": "m", "attachment_id": "a"}, _cfg(self.tmp))
        self.assertEqual(v1["decision"], "AUTHORIZED")
        self.assertNotIn("policy_binding", v1)

    def test_policy_change_voids_until_regate(self):
        # 策略覆写 → 指纹变更 → 旧授权失效须重审
        odir = self.tmp / "redaction_presets"
        odir.mkdir()
        floor_min = ["id_card", "person", "personal_address", "phone"]
        (odir / "external_send.json").write_text(_canonical({
            "preset": "external_send",
            "redact_floor_kinds": floor_min + ["wechat"]}), encoding="utf-8")
        stale = call("attachment.authorize",
                     {"matter_id": "m", "attachment_id": "a",
                      "egress_scope": "external_send"}, _cfg(self.tmp))
        self.assertEqual(stale["decision"], "REFUSED")
        self.assertEqual(stale["reason"], "policy_changed_since_verdict")
        self.assertNotEqual(stale["bound_config_sha256"],
                            stale["current_config_sha256"])
        # 重审闭环：按当前策略重走闸门后的新裁决（回写新指纹）→ 授权恢复
        att = self.tmp / "attachments" / "m" / "a"
        verdict = json.loads((att / "verdict.json").read_text(encoding="utf-8"))
        verdict["policy_binding"]["config_sha256"] = \
            stale["current_config_sha256"]
        (att / "verdict.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=1),
            encoding="utf-8")
        ok = call("attachment.authorize",
                  {"matter_id": "m", "attachment_id": "a",
                   "egress_scope": "external_send"}, _cfg(self.tmp))
        self.assertEqual(ok["decision"], "AUTHORIZED")

    def test_invalid_scope_arg_typed(self):
        with self.assertRaises(NotConnected) as cm:
            call("attachment.authorize",
                 {"matter_id": "m", "attachment_id": "a",
                  "egress_scope": "bogus"}, _cfg(self.tmp))
        self.assertIn("attachment_gate_egress_scope_invalid", str(cm.exception))
        with self.assertRaises(NotConnected) as cm2:
            call("attachment.gate",
                 {"matter_id": "m", "attachment_id": "a",
                  "source_pdf": "x.pdf", "policy": "bogus"}, _cfg(self.tmp))
        self.assertIn("attachment_gate_policy_invalid", str(cm2.exception))


if __name__ == "__main__":
    unittest.main()
