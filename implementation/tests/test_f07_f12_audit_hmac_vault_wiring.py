# -*- coding: utf-8 -*-
"""W3-U09 / F07+F12 acceptance: audit HMAC integrity + BYOK credential vault.

F12（真实BYOK经DPAPI/keyring读写；配置和日志不露key；缺解密不明文降级）
与 F07（产品审计HMAC完整性：篡改/截断/重放检测，摘要不含原件/身份/秘密，
密钥归产品凭据设施，不恢复Harness已拆部署签章总闸）——全部断言走真产品
面（in-process 同 legal_entry.call 同径）＋少量真产品入口子进程径。测试
键全部合成（DeepSeek 形运行时生成），不入 git；金丝雀扫描沿 E10
（tools/e10_canary 同一模块 in-process 复用）。材料全合成。
"""
import ast
import base64
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))

import audit_hmac as ah
import credential_vault as cv
import legal_entry

sys.path.insert(0, str(HERE.parent / "tools"))
import e10_canary  # noqa: E402

REPO_ROOT = HERE.parent
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"


def _fresh_roots(tmp: Path):
    vault_root = tmp / "vault"
    audit_root = tmp / "audit"
    vault_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)
    return vault_root, audit_root


def _provision_audit_key(vault_root: Path, key: bytes | None = None) -> bytes:
    key = key or os.urandom(32)
    cv.vault_put(vault_root, cv.AUDIT_KEY_SERVICE, cv.AUDIT_KEY_ACCOUNT, key)
    return key


class FrozenGroupTests(unittest.TestCase):
    def test_frozen_method_groups(self):
        self.assertEqual(
            legal_entry.VAULT_METHODS,
            frozenset({"vault.status", "vault.put", "vault.get",
                       "vault.delete", "vault.list"}))
        self.assertEqual(
            legal_entry.AUDIT_HMAC_METHODS,
            frozenset({"audit.append", "audit.verify", "audit.read",
                       "audit.export"}))

    def test_audit_group_disjoint_from_all_business_groups(self):
        groups = [value for name, value in vars(legal_entry).items()
                  if name.endswith("_METHODS")
                  and isinstance(value, frozenset)]
        others = [g for g in groups if g is not legal_entry.AUDIT_HMAC_METHODS]
        self.assertTrue(others)
        for group in others:
            self.assertFalse(legal_entry.AUDIT_HMAC_METHODS & group, str(group))

    def test_no_signature_gate_markers_in_new_faces(self):
        # 不恢复已拆部署签章总闸（stage B 16d73893）：产品新面零总闸标记。
        markers = ("host_signature", "core_signature", "deployment_gate",
                   "sealed_signature", "activation_gate")
        for rel in ("audit_hmac.py", "credential_vault.py"):
            text = (HERE / "python" / rel).read_text(encoding="utf-8")
            for marker in markers:
                self.assertNotIn(marker, text, rel)

    def test_vault_ast_single_decrypt_path(self):
        # 缺解密不明文降级的结构面：vault_get 只有一条解密通道（DPAPI/keyring
        # 密文），不存在读配置明文的回退分支（无 open() 落在 get 路径）。
        tree = ast.parse((HERE / "python" / "credential_vault.py")
                         .read_text(encoding="utf-8"))
        get_fn = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef)
                      and node.name == "vault_get")
        for node in ast.walk(get_fn):
            self.assertNotIsInstance(node, ast.With)
        names = {node.func.attr if isinstance(node.func, ast.Attribute)
                 else node.func.id
                 for node in ast.walk(get_fn)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, (ast.Attribute, ast.Name))}
        self.assertNotIn("open", names)  # get 路径零明文文件读取


class VaultRoundtripTests(unittest.TestCase):
    def test_dpapi_real_write_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, _ = _fresh_roots(Path(tmp))
            key = cv.new_byok_test_key()
            self.assertRegex(key, r"^sk-[0-9a-f]{32}$")  # DeepSeek 形合成键
            put = cv.vault_put(vault_root, "deepseek-byok", "model-key",
                               key.encode("utf-8"))
            self.assertEqual(put["backend"], "dpapi")
            self.assertEqual(put["sha256"],
                             hashlib.sha256(key.encode()).hexdigest())
            got = cv.vault_get(vault_root, "deepseek-byok", "model-key",
                               reveal=True)
            self.assertEqual(
                base64.b64decode(got["secret_b64"]).decode("utf-8"), key)
            # 登记文件零明文键（DPAPI 密文 blob）。
            entry_path = (vault_root / "credentials" / "deepseek-byok"
                          / "model-key.json")
            self.assertNotIn(key.encode("utf-8"),
                             entry_path.read_bytes())

    def test_get_default_zero_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, _ = _fresh_roots(Path(tmp))
            key = cv.new_byok_test_key()
            cv.vault_put(vault_root, "s", "a", key.encode("utf-8"))
            got = cv.vault_get(vault_root, "s", "a")
            self.assertFalse(got["revealed"])
            self.assertNotIn("secret_b64", got)
            self.assertIn("…", got["masked"])
            self.assertNotEqual(got["masked"], key)

    def test_corrupt_blob_named_refusal_no_plaintext_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, _ = _fresh_roots(Path(tmp))
            key = cv.new_byok_test_key()
            cv.vault_put(vault_root, "s", "a", key.encode("utf-8"))
            entry_path = vault_root / "credentials" / "s" / "a.json"
            entry = json.loads(entry_path.read_text(encoding="utf-8"))
            entry["blob_b64"] = "AAAA" + entry["blob_b64"][4:]
            entry_path.write_text(json.dumps(entry), encoding="utf-8")
            with self.assertRaises(cv.VaultError) as ctx:
                cv.vault_get(vault_root, "s", "a", reveal=True)
            self.assertIn("vault_decrypt_failed", str(ctx.exception))
            # 失败后无明文回退产物（vault 全树 json 内零钥字节）。
            for path in vault_root.rglob("*.json"):
                self.assertNotIn(key.encode("utf-8"), path.read_bytes())

    def test_missing_entry_named_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, _ = _fresh_roots(Path(tmp))
            with self.assertRaises(cv.VaultError) as ctx:
                cv.vault_get(vault_root, "s", "absent")
            self.assertIn("vault_entry_missing", str(ctx.exception))

    def test_oversized_secret_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, _ = _fresh_roots(Path(tmp))
            with self.assertRaises(cv.VaultError) as ctx:
                cv.vault_put(vault_root, "s", "a", b"x" * 4097)
            self.assertIn("vault_secret_oversized", str(ctx.exception))

    def test_ref_rejects_traversal_and_ads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for service, account in (
                ("../x", "a"),
                ("a", ".."),
                ("a/b", "c"),
                ("a", "b:stream"),
                ("a..b", "c"),
                ("", "a"),
            ):
                with self.assertRaises(cv.VaultError) as ctx:
                    cv._entry_path(root, service, account)
                self.assertEqual(str(ctx.exception), "vault_ref_invalid")
            kept = cv._entry_path(root, "lvyin.audit", "hmac-sha256-v1")
            self.assertEqual(kept.name, "hmac-sha256-v1.json")

    def test_put_rejects_ads_before_crypto(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(cv.VaultError) as ctx:
                cv.vault_put(Path(tmp), "s", "a:stream", b"secret")
            self.assertEqual(str(ctx.exception), "vault_ref_invalid")

    def test_corrupt_registry_json_is_typed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = cv._entry_path(root, "s", "a")
            path.parent.mkdir(parents=True)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(cv.VaultError) as ctx:
                cv.vault_get(root, "s", "a")
            self.assertEqual(str(ctx.exception), "vault_schema_unknown")

    def test_keyring_backend_branch_honest(self):
        # keyring 未装＝具名缺（本机实态）；装了＝真往返。两分支都如实。
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, _ = _fresh_roots(Path(tmp))
            try:
                cv.vault_put(vault_root, "s", "a", b"hi", backend="keyring")
                got = cv.vault_get(vault_root, "s", "a", reveal=True,
                                   backend="keyring")
                self.assertEqual(
                    base64.b64decode(got["secret_b64"]).decode(), "hi")
            except cv.VaultError as exc:
                self.assertIn("vault_keyring_backend_unavailable",
                              str(exc))
                self.assertFalse(cv._keyring_ok())


class AuditHmacChainTests(unittest.TestCase):
    def _append3(self, vault_root, audit_root):
        heads = []
        for i in range(3):
            heads.append(ah.audit_append(
                vault_root, audit_root, "m-1",
                {"kind": "step", "note": str(i), "docSha": "a" * 8}))
        return heads

    def test_append_verify_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            _provision_audit_key(vault_root)
            heads = self._append3(vault_root, audit_root)
            self.assertEqual([h["seq"] for h in heads], [1, 2, 3])
            first_digest = heads[0]["digest"]
            self.assertEqual(heads[1]["previousHash"], first_digest)
            verified = ah.audit_verify(vault_root, audit_root, "m-1")
            self.assertTrue(verified["ok"])
            self.assertEqual(verified["entries"], 3)
            self.assertEqual(verified["head"], heads[-1]["digest"])
            read = ah.audit_read(vault_root, audit_root, "m-1")
            self.assertEqual(len(read["entries"]), 3)
            self.assertEqual(read["entries"][0]["event"]["note"], "0")

    def test_tamper_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            _provision_audit_key(vault_root)
            self._append3(vault_root, audit_root)
            path = audit_root / "audit-hmac" / "m-1.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            row = json.loads(lines[0])
            row["event"]["note"] = "TAMPERED"
            lines[0] = json.dumps(row, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(ah.AuditHmacError) as ctx:
                ah.audit_verify(vault_root, audit_root, "m-1")
            self.assertIn("audit_hmac_chain_broken:1", str(ctx.exception))

    def test_truncate_named_with_pinned_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            _provision_audit_key(vault_root)
            self._append3(vault_root, audit_root)
            head = ah.audit_verify(vault_root, audit_root, "m-1")["head"]
            path = audit_root / "audit-hmac" / "m-1.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines[:1]) + "\n", encoding="utf-8")
            with self.assertRaises(ah.AuditHmacError) as ctx:
                ah.audit_verify(vault_root, audit_root, "m-1",
                                expected_head=head)
            self.assertIn("audit_head_mismatch", str(ctx.exception))
            # 无锚前缀自查通过（与 harness W25 链同边界，如实主张）。
            self.assertTrue(ah.audit_verify(vault_root, audit_root,
                                            "m-1")["ok"])

    def test_replay_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            _provision_audit_key(vault_root)
            self._append3(vault_root, audit_root)
            path = audit_root / "audit-hmac" / "m-1.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines + [lines[1]]) + "\n",
                            encoding="utf-8")
            with self.assertRaises(ah.AuditHmacError) as ctx:
                ah.audit_verify(vault_root, audit_root, "m-1")
            self.assertIn("audit_hmac_replay_refused:2", str(ctx.exception))

    def test_append_never_extends_broken_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            _provision_audit_key(vault_root)
            self._append3(vault_root, audit_root)
            path = audit_root / "audit-hmac" / "m-1.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            row = json.loads(lines[2])
            row["event"]["note"] = "EVIL"
            lines[2] = json.dumps(row, ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":"))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(ah.AuditHmacError) as ctx:
                ah.audit_append(vault_root, audit_root, "m-1",
                                {"kind": "next"})
            self.assertIn("audit_hmac_chain_broken", str(ctx.exception))

    def test_event_closure_refuses_original_shaped_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            _provision_audit_key(vault_root)
            bad_events = [
                {"blob": "x" * 513},      # 超长值（原文形态）
                {"nested": {"deep": 1}},  # 嵌套结构
                {"money": 1.5},           # 浮点
                {"raw": b"bytes"},        # 二进制
            ]
            for bad in bad_events:
                with self.assertRaises(ah.AuditHmacError) as ctx:
                    ah.audit_append(vault_root, audit_root, "m-2", bad)
                self.assertIn("audit_event_payload_refused",
                              str(ctx.exception))
            # 对照：合法扁平元数据可入链。
            ok = ah.audit_append(vault_root, audit_root, "m-2",
                                 {"payload_b64": "AAAA", "len": 4})
            self.assertEqual(ok["seq"], 1)

    def test_missing_key_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            with self.assertRaises(ah.AuditHmacError) as ctx:
                ah.audit_append(vault_root, audit_root, "m", {"k": "v"})
            self.assertIn("audit_hmac_key_not_provisioned", str(ctx.exception))
            with self.assertRaises(ah.AuditHmacError):
                ah.audit_append(None, audit_root, "m", {"k": "v"})

    def test_export_mirror_idempotent_and_tamper_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            _provision_audit_key(vault_root)
            self._append3(vault_root, audit_root)
            first = ah.audit_export(vault_root, audit_root, "m-1")
            self.assertEqual(first["entryCount"], 3)
            again = ah.audit_export(vault_root, audit_root, "m-1")
            self.assertEqual(again["entryCount"], 3)
            export_path = Path(first["exportPath"])
            data = export_path.read_bytes()
            export_path.write_bytes(data.replace(b"step", b"evil"))
            with self.assertRaises(ah.AuditHmacError) as ctx:
                ah.audit_export(vault_root, audit_root, "m-1")
            self.assertIn("audit_export_tampered", str(ctx.exception))
            export_path.write_bytes(data)
            self.assertEqual(ah.audit_export(vault_root, audit_root,
                                             "m-1")["entryCount"], 3)

    def test_digest_contains_no_original_identity_secret(self):
        # 金丝雀法沿 E10：三枚令牌注入合成材料；事件只以 sha256 在场；
        # 审计全产物扫描零命中（in-process 复用 e10_canary.cmd_scan）。
        token = e10_canary.new_token()
        material = ("《合成合同》原件金丝雀：%s 当事人律某引 "
                    "证件号 110105TEST999999（合成）" % token)
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            _provision_audit_key(vault_root)
            ah.audit_append(vault_root, audit_root, "m-1", {
                "kind": "material_registered",
                "sha256": hashlib.sha256(material.encode()).hexdigest(),
                "doc": "att_0001"})
            ah.audit_export(vault_root, audit_root, "m-1")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = e10_canary.cmd_scan(str(audit_root), token, [], True)
            self.assertEqual(rc, 0)  # 零命中
            # 扫描器非空转对照：泄漏文件必被检出。
            (audit_root / "leak.tmp").write_text(token, encoding="utf-8")
            with contextlib.redirect_stdout(buffer):
                rc = e10_canary.cmd_scan(str(audit_root), token, [], True)
            self.assertEqual(rc, 1)
            (audit_root / "leak.tmp").unlink()

    def test_audit_root_has_no_key_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_root, audit_root = _fresh_roots(Path(tmp))
            key = _provision_audit_key(vault_root)
            self._append3(vault_root, audit_root)
            for path in audit_root.rglob("*.jsonl"):
                self.assertNotIn(key, path.read_bytes())
            # 钥料在 vault 密文内（密文≠钥字节）。
            entry = (vault_root / "credentials" / cv.AUDIT_KEY_SERVICE
                     / (cv.AUDIT_KEY_ACCOUNT + ".json")).read_bytes()
            self.assertNotIn(key, entry)


class BridgeSubprocessTests(unittest.TestCase):
    """真产品入口子进程径（legal_entry CLI）。"""

    def _call(self, method, args, config):
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / "request.json"
            cfg = Path(tmp) / "config.json"
            req.write_text(json.dumps({"method": method, "args": args}),
                           encoding="utf-8")
            cfg.write_text(json.dumps(config), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
                 "--request-json", str(req), "--config", str(cfg)],
                capture_output=True, text=True, encoding="utf-8", timeout=120)
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {"status": "RAW"}
            return proc.returncode, payload

    def test_bridge_vault_roundtrip_exit0(self):
        key = cv.new_byok_test_key()
        with tempfile.TemporaryDirectory() as tmp:
            config = {"vault_state_root": str(Path(tmp) / "vault")}
            code, out = self._call("vault.put", {
                "service": "deepseek-byok", "account": "model-key",
                "secret_b64": base64.b64encode(key.encode()).decode()},
                config)
            self.assertEqual(code, 0, out)
            self.assertEqual(out["status"], "OWNER_RESPONSE")
            code, out = self._call("vault.get", {
                "service": "deepseek-byok", "account": "model-key",
                "reveal": True}, config)
            self.assertEqual(code, 0, out)
            self.assertEqual(
                base64.b64decode(out["result"]["secret_b64"]).decode(), key)

    def test_bridge_corrupt_named_exit3(self):
        key = cv.new_byok_test_key()
        with tempfile.TemporaryDirectory() as tmp:
            vault_root = Path(tmp) / "vault"
            config = {"vault_state_root": str(vault_root)}
            self.assertEqual(self._call("vault.put", {
                "service": "s", "account": "a",
                "secret_b64": base64.b64encode(key.encode()).decode()},
                config)[0], 0)
            entry_path = vault_root / "credentials" / "s" / "a.json"
            entry = json.loads(entry_path.read_text(encoding="utf-8"))
            entry["blob_b64"] = "AAAA" + entry["blob_b64"][4:]
            entry_path.write_text(json.dumps(entry), encoding="utf-8")
            code, out = self._call("vault.get", {
                "service": "s", "account": "a", "reveal": True}, config)
            self.assertEqual(code, 3)
            self.assertEqual(out["status"], "NOT_CONNECTED")
            self.assertIn("vault_decrypt_failed", out["code"])

    def test_bridge_unconfig_and_unknown_exit3(self):
        code, out = self._call("vault.put", {"service": "s", "account": "a",
                                             "secret_b64": "aGk="}, {})
        self.assertEqual(code, 3)
        self.assertIn("vault_state_root_not_configured", out["code"])
        code, out = self._call("vault.transmogrify", {}, {})
        self.assertEqual(code, 3)
        self.assertIn("not_connected", out["code"].lower())


if __name__ == "__main__":
    unittest.main()
