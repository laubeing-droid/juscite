"""W3-U13 / F61 微信 ID 批次采集桥面测试：冻结方法组、fail-closed 配置面、
未授权＝UNKNOWN 值 None 非 0、url/cookie 旁路字段具名拒、幂等回流与
出处 sha 绑定经桥同进程闭环（anonymizer 面只经既有 material.deidentify
P10 公开面；附件闸全链真跑由 tools/PENDING_OWNER_f61_batch_collection_recon.py
承担）。全部合成材料。

AST 面断言（负测先行纪律）：wechat_collection.py 导入闭集零网络模块、
字符串常量零 URL 模式、标识符零采集旁路关键字——禁编 URL/不走 Cookie
逆向是结构性事实，不是运行时约定。
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))

from legal_entry import call, NotConnected, WECHAT_COLLECTION_METHODS

PHONE = "13700005555"
ID_CARD = "110101199003078670"


def _cfg(**extra):
    config = {"anonymizer_contract": "p09/p10"}
    config.update(extra)
    return config


class F61WechatCollectionWiringTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.cfg = _cfg(collection_state_root=str(self.root / "state"))

    def tearDown(self):
        self._tmp.cleanup()

    # -- 冻结面 ------------------------------------------------------------
    def test_frozen_method_group(self):
        self.assertEqual(WECHAT_COLLECTION_METHODS, frozenset({
            "collection.authorize", "collection.batch",
            "collection.batch_read"}))

    def test_unknown_method_stays_not_connected(self):
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:collection.explode"):
            call("collection.explode", {}, self.cfg)

    def test_fail_closed_config(self):
        with self.assertRaisesRegex(NotConnected,
                                    "anonymizer_p09_p10_not_configured"):
            call("collection.authorize", {"external_ids": ["w1"],
                                          "authorized_by": "x"}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "collection_state_root_not_configured"):
            call("collection.authorize", {"external_ids": ["w1"],
                                          "authorized_by": "x"}, _cfg())
        with self.assertRaisesRegex(NotConnected,
                                    "wechat_collection_params_invalid"):
            call("collection.batch", "not-a-dict", self.cfg)

    # -- 授权账 ------------------------------------------------------------
    def test_authorize_ledger_idempotent_and_closed(self):
        r1 = call("collection.authorize",
                  {"external_ids": ["wxid_a", "wxid_b"],
                   "authorized_by": "synth-user"}, self.cfg)
        self.assertFalse(r1["idempotent_replay"])
        self.assertEqual(r1["authorized_ids_total"], 2)
        # 顺序无关幂等重放
        r2 = call("collection.authorize",
                  {"external_ids": ["wxid_b", "wxid_a"],
                   "authorized_by": "synth-user"}, self.cfg)
        self.assertTrue(r2["idempotent_replay"])
        self.assertEqual(r2["authorization"]["auth_id"],
                         r1["authorization"]["auth_id"])
        # scope 闭集外拒（不预造在线/爬取形态）
        with self.assertRaisesRegex(NotConnected, "f61_scope_unknown:web_crawl"):
            call("collection.authorize",
                 {"external_ids": ["wxid_c"], "authorized_by": "u",
                  "scope": "web_crawl"}, self.cfg)
        with self.assertRaisesRegex(NotConnected, "f61_authorized_by_required"):
            call("collection.authorize", {"external_ids": ["wxid_c"]},
                 self.cfg)
        with self.assertRaisesRegex(NotConnected, "f61_external_ids_required"):
            call("collection.authorize", {"authorized_by": "u"}, self.cfg)

    # -- 批次采集：text 件＋未授权 UNKNOWN-----------------------------------
    def _write_export(self, name: str, content: str) -> Path:
        path = self.root / "exports" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _authorize_ab(self):
        call("collection.authorize",
             {"external_ids": ["wxid_a", "wxid_b"],
              "authorized_by": "synth-user"}, self.cfg)

    def test_batch_unknown_not_authorized_values_none_not_zero(self):
        self._authorize_ab()
        export = self._write_export("chat.txt", f"张三 {PHONE} 到庭")
        receipt = call("collection.batch", {
            "batch_id": "b-unk", "matter_id": "m-unk",
            "items": [
                {"external_id": "wxid_a", "kind": "text",
                 "export_path": str(export)},
                {"external_id": "wxid_ghost", "kind": "text",
                 "export_path": str(export)},
            ]}, self.cfg)
        self.assertEqual(receipt["counts"]["total"], 2)
        self.assertEqual(receipt["counts"]["unknown_not_authorized"], 1)
        unknown = [i for i in receipt["items"]
                   if i["status"] == "UNKNOWN_NOT_AUTHORIZED"]
        self.assertEqual(len(unknown), 1)
        entry = unknown[0]
        # UNKNOWN 值 None 非 0：三值位结构性 None，绝不填 0/空对象。
        self.assertIsNone(entry["export"])
        self.assertIsNone(entry["collected"])
        self.assertIsNone(entry["gate"])
        self.assertEqual(entry["reason"], "external_id_not_authorized")
        collected = [i for i in receipt["items"] if i["status"] == "COLLECTED"]
        self.assertEqual(len(collected), 1)
        # 投影红线：条目不回传导出原文、脱敏文本与原件路径
        blob = json.dumps(receipt, ensure_ascii=False)
        self.assertNotIn("张三", blob)
        self.assertNotIn("export_path", blob)

    def test_batch_text_provenance_sha_binding_via_real_deidentify(self):
        self._authorize_ab()
        export = self._write_export(
            "chat2.txt", f"被申请人身份证 {ID_CARD}，电话 {PHONE}，已收函")
        receipt = call("collection.batch", {
            "batch_id": "b-text", "matter_id": "m-text",
            "items": [{"external_id": "wxid_a", "kind": "text",
                       "export_path": str(export)}]}, self.cfg)
        entry = receipt["items"][0]
        self.assertEqual(entry["status"], "COLLECTED")
        self.assertEqual(entry["collected"]["kind"], "sanitized_text")
        self.assertTrue(entry["export"]["sha256"])
        self.assertTrue(entry["collected"]["sha256"])
        # 出处一致：同输入独立 deidentify 的 sanitized sha 与批次绑定相等
        independent = call("material.deidentify",
                           {"text": export.read_text(encoding="utf-8")},
                           self.cfg)
        import hashlib
        self.assertEqual(entry["collected"]["sha256"],
                         hashlib.sha256(
                             independent["sanitized_text"].encode("utf-8"))
                         .hexdigest())
        self.assertNotEqual(entry["collected"]["sha256"],
                            entry["export"]["sha256"])
        self.assertTrue(entry["review_required"])  # 规则面语义如实携带

    def test_batch_declared_sha_mismatch_is_source_mismatch(self):
        self._authorize_ab()
        export = self._write_export("chat3.txt", "正常内容")
        receipt = call("collection.batch", {
            "batch_id": "b-sha", "matter_id": "m-sha",
            "items": [{"external_id": "wxid_a", "kind": "text",
                       "export_path": str(export),
                       "export_sha256": "0" * 64}]}, self.cfg)
        entry = receipt["items"][0]
        self.assertEqual(entry["status"], "SOURCE_MISMATCH")
        self.assertEqual(entry["reason"], "f61_export_sha_mismatch")
        self.assertIsNone(entry["collected"])
        self.assertEqual(receipt["counts"]["source_mismatch"], 1)

    # -- 负测先行：url/cookie 旁路字段具名拒---------------------------------
    def test_url_and_cookie_bypass_fields_refused(self):
        self._authorize_ab()
        export = self._write_export("chat4.txt", "x")
        for field, value in (
                ("url", "https://weixin.example.invalid/profile"),
                ("cookie", "SESSIONID=1"),
                ("session", "s"),
                ("token", "t")):
            with self.assertRaisesRegex(
                    NotConnected, "collection_failed:f61_field_forbidden:"
                    + field):
                call("collection.batch", {
                    "batch_id": "b-neg-" + field, "matter_id": "m",
                    "items": [{"external_id": "wxid_a", "kind": "text",
                               "export_path": str(export), field: value}]},
                    self.cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "f61_field_forbidden:weixin_url"):
            call("collection.batch", {
                "batch_id": "b-neg-top", "matter_id": "m",
                "weixin_url": "https://example.invalid",
                "items": [{"external_id": "wxid_a", "kind": "text",
                           "export_path": str(export)}]}, self.cfg)

    # -- 幂等回流（裁决#6）---------------------------------------------------
    def test_batch_idempotent_replay_and_conflict(self):
        self._authorize_ab()
        export = self._write_export("chat5.txt", "幂等回流内容")

        def _args():
            return {"batch_id": "b-idem", "matter_id": "m-idem",
                    "items": [{"external_id": "wxid_a", "kind": "text",
                               "export_path": str(export)}]}

        r1 = call("collection.batch", _args(), self.cfg)
        r2 = call("collection.batch", _args(), self.cfg)
        self.assertEqual(r1, r2)  # 同输入重放同回执（不双记）
        self.assertEqual(r1["recorded_at"], r2["recorded_at"])
        conflict = _args()
        conflict["items"][0]["external_id"] = "wxid_b"
        with self.assertRaisesRegex(NotConnected, "f61_batch_conflict"):
            call("collection.batch", conflict, self.cfg)
        # 回读投影与回执一致
        read = call("collection.batch_read", {"batch_id": "b-idem"}, self.cfg)
        self.assertEqual(read, r1)
        with self.assertRaisesRegex(NotConnected, "f61_batch_not_found"):
            call("collection.batch_read", {"batch_id": "nope"}, self.cfg)

    def test_batch_validation_closed(self):
        self._authorize_ab()
        for args, code in (
                ({"matter_id": "m", "items": [{"external_id": "w",
                                               "kind": "text",
                                               "export_path": "x"}]},
                 "f61_batch_id_required"),
                ({"batch_id": "b", "items": [{"external_id": "w",
                                              "kind": "text",
                                              "export_path": "x"}]},
                 "f61_matter_id_required"),
                ({"batch_id": "b", "matter_id": "m", "items": []},
                 "f61_items_required"),
                ({"batch_id": "b", "matter_id": "m",
                  "items": [{"external_id": "w", "kind": "web_crawl",
                             "export_path": "x"}]},
                 "f61_kind_unknown:web_crawl"),
                ({"batch_id": "b", "matter_id": "m",
                  "items": [{"kind": "text", "export_path": "x"}]},
                 "f61_external_id_invalid"),
                ({"batch_id": "b", "matter_id": "m",
                  "items": [{"external_id": "wxid_a", "kind": "text"}]},
                 "f61_export_path_required")):
            with self.assertRaisesRegex(NotConnected, code):
                call("collection.batch", args, self.cfg)
        with self.assertRaisesRegex(NotConnected, "f61_export_unreadable"):
            call("collection.batch", {
                "batch_id": "b-missing", "matter_id": "m",
                "items": [{"external_id": "wxid_a", "kind": "text",
                           "export_path": str(self.root / "nope.txt")}]},
                self.cfg)

    # -- AST 面：禁编 URL／不走 Cookie 逆向是结构性事实------------------------
    def test_ast_face_no_network_no_url_no_cookie_keywords(self):
        source_path = (Path(__file__).resolve().parents[1] / "python"
                       / "wechat_collection.py")
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or "").split(".")[0])
        self.assertEqual(
            imported, {"__future__", "hashlib", "json", "os", "datetime",
                       "pathlib"},
            f"导入闭集漂移: {sorted(imported)}")
        # 字符串常量零 URL 模式（URL 构造结构性不可能）
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                low = node.value.lower()
                self.assertNotIn("http://", low)
                self.assertNotIn("https://", low)
        # 标识符零采集旁路关键字（Cookie/逆向会话/自动登录族）
        banned = ("cookie", "session", "webdriver", "selenium", "token",
                  "credential")
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Name):
                names.append(node.id)
            elif isinstance(node, ast.Attribute):
                names.append(node.attr)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(node.name)
            elif isinstance(node, ast.arg):
                names.append(node.arg)
            for name in names:
                for kw in banned:
                    self.assertNotIn(kw, name.lower(),
                                     f"标识符 {name} 含旁路关键字 {kw}")
        # 批次/条目字段闭集常量本身不含旁路字段
        from wechat_collection import (BATCH_FIELD_WHITELIST,
                                       ITEM_FIELD_WHITELIST)
        for fields in (BATCH_FIELD_WHITELIST, ITEM_FIELD_WHITELIST):
            for field in fields:
                for kw in banned:
                    self.assertNotIn(kw, field)


if __name__ == "__main__":
    unittest.main()
