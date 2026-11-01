# -*- coding: utf-8 -*-
"""W3-U19 / E23 B1 段验收：受控内容读侧桥＋观察闭环缺省面。

07 E23 assertion「现有受控内容消费，不公开蒸馏；Observer建议待用户，不
自动改路由prompt/规则发布启用」＋裁决#7（合成样本先行；Observer 不启用）：
* manual.* 四方法 = manuals 仓 legal_cn_manuals.consumer 读侧白名单
  （manual.open/search/read/version）一一对应——桥只转发，不造第二消费者；
  private 记录永不出走读侧白名单（scope_mismatch 具名拒）；
* persona.*/observer.* 具名 not_connected（可选件缺席形态；Observer 待用户
  裁决，任何配置不可启用）；
* 方法组冻结＝纯读侧：无 publish/enable/distill/observe/prompt 方法，
  消费动作不自动改路由 prompt、不自动启用规则发布。

全部材料为工程合成样本（合成包正文为标注合成的方法条目，无法条引文）。
manuals 检出以 sha256 钉定只读消费（tools/PENDING_OWNER_e23_controlled_
content_recon.py S0 为验收级钉定；本测试沿用同一钉定常量），缺检出时
整类诚实跳过，绝不假通过。
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry  # noqa: E402

_TOOLS = HERE.parent / "tools"
_RECON_PATH = _TOOLS / "PENDING_OWNER_e23_controlled_content_recon.py"

_spec = importlib.util.spec_from_file_location("e23_recon", _RECON_PATH)
e23_recon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e23_recon)


def _manuals_root():
    try:
        return e23_recon.manuals_checkout(None)
    except SystemExit:
        return None


class _PackEnv:
    """临时 packs 根＋真实信任管线落合成包（与 recon 同一构建器）。"""

    def __init__(self):
        self.manuals_root = _manuals_root()
        self.holder = tempfile.TemporaryDirectory()
        tmp = Path(self.holder.name)
        self.tmp = tmp
        self.packs_root = tmp / "packs"
        self.packs_root.mkdir(parents=True, exist_ok=True)
        staging = tmp / "staging-src"
        staging.mkdir(parents=True, exist_ok=True)
        self.pointer, self.import_result, self.entries = \
            e23_recon.import_pack_via_trust_pipeline(
                self.manuals_root, self.packs_root, staging)
        self.config = e23_recon.bridge_config(self.manuals_root,
                                              self.packs_root)

    def pack_ref(self):
        return {"owner": "manuals", "kind": "manual-pack",
                "id": e23_recon.SYN_PACK_ID,
                "version": str(self.pointer["snapshotVersion"]),
                "matterId": None, "digest": self.pointer["payloadDigest"]}

    def record_ref(self, record_id):
        return {"owner": "manuals", "kind": "manual-record",
                "id": "%s/%s" % (e23_recon.SYN_PACK_ID, record_id),
                "version": str(self.pointer["snapshotVersion"]),
                "matterId": None,
                "digest": self.entries[record_id]["recordDigest"]}

    def close(self):
        self.holder.cleanup()


_SKIP = None


def _skip_reason():
    global _SKIP
    if _SKIP is None:
        _SKIP = "manuals checkout not resolved" if _manuals_root() is None \
            else ""
    return _SKIP


class TestMethodGroupFrozen(unittest.TestCase):
    def test_frozen_method_group_is_read_side_quartet(self):
        self.assertEqual(legal_entry.MANUAL_METHODS, frozenset({
            "manual.open", "manual.search", "manual.read",
            "manual.version"}))

    def test_bridge_surface_equals_consumer_public_methods(self):
        root = _manuals_root()
        if root is None:
            self.skipTest(_skip_reason())
        sys.path.insert(0, str(root / "src"))
        for name in [m for m in list(sys.modules)
                     if m == "legal_cn_manuals"
                     or m.startswith("legal_cn_manuals.")]:
            del sys.modules[name]
        from legal_cn_manuals.consumer import ManualsConsumer
        consumer_methods = sorted(
            n for n, member in vars(ManualsConsumer).items()
            if callable(member) and not n.startswith("_"))
        self.assertEqual(consumer_methods,
                         ["open", "read", "search", "version"])

    def test_no_banned_tokens_in_any_frozen_method_group(self):
        import ast
        source = (HERE / "python" / "legal_entry.py").read_text(
            encoding="utf-8")
        groups = e23_recon._method_names_from_frozenset(ast.parse(source))
        banned = sorted(
            m for names in groups.values() for m in names
            if any(tok in m.lower() for tok in e23_recon.BANNED_METHOD_TOKENS))
        self.assertEqual(banned, [])

    def test_manual_call_has_no_filesystem_write_face(self):
        import ast
        fn = e23_recon._func_source_lines(
            (HERE / "python" / "legal_entry.py").read_text(encoding="utf-8"),
            "_manual_call")
        hits = []
        for node in ast.walk(ast.parse(fn)):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) \
                        and node.func.attr in e23_recon.WRITE_ATTRS:
                    hits.append(node.func.attr)
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    hits.append("open()")
        self.assertEqual(hits, [])


class TestFailClosed(unittest.TestCase):
    def test_unconfigured_fails_closed(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("manual.version",
                             {"scope": {"kind": "system"},
                              "pack_id": "x", "version": None}, {})
        self.assertIn("manuals_lh_distill_ingest_1_not_configured",
                      str(ctx.exception))

    def test_missing_import_path_fails_closed(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("manual.version",
                             {"scope": {"kind": "system"},
                              "pack_id": "x", "version": None},
                             {"manuals_contract": "lh-distill-ingest/1",
                              "manuals_import_path": "Z:/definitely/missing",
                              "manuals_packs_root": "Z:/also/missing"})
        self.assertIn("manuals_import_path_missing", str(ctx.exception))

    def test_missing_packs_root_fails_closed(self):
        root = _manuals_root()
        if root is None:
            self.skipTest(_skip_reason())
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("manual.version",
                             {"scope": {"kind": "system"},
                              "pack_id": "x", "version": None},
                             {"manuals_contract": "lh-distill-ingest/1",
                              "manuals_import_path": str(root / "src")})
        self.assertIn("manuals_packs_root_not_configured", str(ctx.exception))

    def test_unknown_manual_method_not_connected(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("manual.publish", {}, {})
        self.assertIn("method_not_connected:manual.publish",
                      str(ctx.exception))

    def test_persona_namespace_named_refusal(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("persona.consume", {}, {})
        self.assertIn("persona_optional_component_not_wired",
                      str(ctx.exception))

    def test_observer_namespace_named_refusal_adjudication7(self):
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("observer.enable", {}, {})
        self.assertIn("observer_not_enabled_pending_user_decision",
                      str(ctx.exception))

    def test_observer_persona_not_configurable(self):
        # 任何配置都不能启用：带满配置同样具名拒。
        root = _manuals_root()
        config = {"manuals_contract": "lh-distill-ingest/1"}
        if root is not None:
            config["manuals_import_path"] = str(root / "src")
            config["manuals_packs_root"] = str(HERE / ".." / "any")
        for method in ("observer.enable", "observer.record",
                       "persona.attach", "persona.inject_prompt"):
            with self.assertRaises(legal_entry.NotConnected) as ctx:
                legal_entry.call(method, {}, config)
            self.assertTrue(str(ctx.exception).startswith(
                ("observer_not_enabled_pending_user_decision",
                 "persona_optional_component_not_wired")), method)


@unittest.skipIf(_manuals_root() is None, _skip_reason() or
                 "manuals checkout not resolved")
class TestSyntheticConsumptionLoop(unittest.TestCase):
    def setUp(self):
        self.env = _PackEnv()
        self.addCleanup(self.env.close)

    def test_version_open_search_read_full_chain(self):
        scope = {"kind": "system"}
        version = legal_entry.call("manual.version",
                                   {"scope": scope,
                                    "pack_id": e23_recon.SYN_PACK_ID,
                                    "version": None}, self.env.config)
        manifest_digest = e23_recon.sha256_file(
            self.env.packs_root / e23_recon.SYN_PACK_ID
            / e23_recon.SYN_PUBLICATION / "manifest.json")
        self.assertEqual(version["manifestRef"]["digest"], manifest_digest)

        opened = legal_entry.call("manual.open",
                                  {"scope": scope,
                                   "pack_id": e23_recon.SYN_PACK_ID,
                                   "version": e23_recon.SYN_PUBLICATION},
                                  self.env.config)
        self.assertEqual(opened["packRef"]["digest"],
                         self.env.pointer["payloadDigest"])

        search = legal_entry.call("manual.search",
                                  {"scope": scope,
                                   "packRef": self.env.pack_ref(),
                                   "query": "", "routeKeys":
                                   ["civil_commercial"],
                                   "includeHeld": False, "cursor": None,
                                   "filters": None}, self.env.config)
        hit_ids = [i["id"].split("/", 1)[1] for i in search["items"]]
        self.assertEqual(hit_ids, ["e23-mtd-001"])

        read = legal_entry.call("manual.read",
                                {"scope": scope,
                                 "record_ref": self.env.record_ref(
                                     "e23-mtd-001")}, self.env.config)
        self.assertEqual(read["body"], e23_recon.SYN_RECORDS[0]["body"])
        self.assertEqual(read["trust"]["status"], "verified")
        self.assertEqual(read["receipt"]["inputRefs"],
                         [self.env.record_ref("e23-mtd-001")])
        self.assertEqual(read["usage"]["packId"], e23_recon.SYN_PACK_ID)

    def test_private_record_never_leaves_read_side(self):
        scope = {"kind": "system"}
        search = legal_entry.call("manual.search",
                                  {"scope": scope,
                                   "packRef": self.env.pack_ref(),
                                   "query": "合成私有", "routeKeys": [],
                                   "includeHeld": True, "cursor": None,
                                   "filters": None}, self.env.config)
        hit_ids = [i["id"].split("/", 1)[1] for i in search["items"]]
        self.assertNotIn("e23-mtd-004", hit_ids)
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            legal_entry.call("manual.read",
                             {"scope": scope,
                              "record_ref": self.env.record_ref(
                                  "e23-mtd-004")}, self.env.config)
        self.assertIn("manuals_provider_scope_mismatch", str(ctx.exception))

    def test_consumption_is_deterministic_across_calls(self):
        scope = {"kind": "system"}
        one = legal_entry.call("manual.read",
                               {"scope": scope,
                                "record_ref": self.env.record_ref(
                                    "e23-mtd-002")}, self.env.config)
        two = legal_entry.call("manual.read",
                               {"scope": scope,
                                "record_ref": self.env.record_ref(
                                    "e23-mtd-002")}, self.env.config)
        self.assertEqual(e23_recon.strip_volatile(one),
                         e23_recon.strip_volatile(two))
        self.assertEqual(one["body"], two["body"])

    def test_persona_absence_loop_completes(self):
        # persona 仓 README-only 缺席形态下，manuals 消费闭环完整走通
        # ＝可选件性质行为级（E23 owner=manuals+persona+harness 的 persona
        # 缺省面）。
        scope = {"kind": "system"}
        read = legal_entry.call("manual.read",
                                {"scope": scope,
                                 "record_ref": self.env.record_ref(
                                     "e23-mtd-001")}, self.env.config)
        self.assertTrue(read["body"].startswith("# 合成方法条目一"))
        self.assertNotIn("persona", json.dumps(self.env.config))


if __name__ == "__main__":
    unittest.main()
