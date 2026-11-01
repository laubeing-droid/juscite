# -*- coding: utf-8 -*-
"""F123 导出签名清单产品桥接线测试（工单 W4-U54）。

06 F123（v1.5；owner=harness+product；acceptance：实际导出清单/文件 hash
验签可核；篡改单文件被检出，私钥不出包）。产品面＝legal_entry 三冻结方
法组：EXPORT_MANIFEST_METHODS（signed_export 签发器）＋EXPORT_CHECKER_
METHODS（export_manifest_checker 独立验证器）＋HARNESS_EXPORT_LEDGER_
METHODS（--exportledger-json 信封；harness docs/f123-signed-export-
contract.md）。

合同硬点（本测试主战场，全链真子进程 public_entry）：
  - 签发＝逐文件 sha256＋清单 HMAC-SHA256 签名＋过账才回执（harness 账
    本独立重算 manifest_sha256/file_set_digest 过账）；
  - 验签＝独立验证路径（export_manifest_checker 零 import 签发器——AST
    钉死；遍历实际目录独立重算；三形态篡改＋清单两形全部检出且定位到
    具体文件）；
  - 密钥只存本机 state（signing.secret；清单/账本/回执只携指纹；全产物
    扫描零暴露＋正控样本证明非空转）；
  - 桥 fail-closed：未配置 NotConnected 具名／封闭注册外方法具名拒／账
    面 f123_* 具名码透传。

全程合成材料（合成案卷＋合成导出文件）。
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402

# harness 战役分支（A2 链）本单 worktree 钉定
HARNESS_WORKTREE = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w4-u54")

MATTER_X = "m-f123-wx"

# 合成导出文件（三件：正文/证据/说明——内容全合成）
SYNTH_FILES = [
    ("docs/起诉状-合成案.docx",
     b"PK\x03\x04 synthetic pleading body \xe5\xbe\x8b\xe5\xbc\x95"),
    ("evidence/证据-合成卷.pdf",
     b"%PDF-1.7 synthetic evidence bytes for f123 wiring"),
    ("README-合成导出.txt",
     "合成导出说明\n".encode("utf-8")),
]


def _key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def _file_args(files: list) -> list:
    return [{"path": p, "dataB64": base64.b64encode(b).decode("ascii")}
            for p, b in files]


def _config(state_root: Path, **harness_state) -> dict:
    return {
        "signed_export_state_root": str(state_root / "export-state"),
        "harness_public_entry":
            str(HARNESS_WORKTREE / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(harness_state.get(
            "harness_root", state_root / "harness-state")),
        "harness_timeout": 120,
    }


def _package_args(export_id: str, files: list) -> dict:
    return {"exportId": export_id, "matterId": MATTER_X,
            "purpose": "代理审判材料导出（合成接线测试）",
            "files": _file_args(files), "sourceRefs": []}


def canonical(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


class F123SignedExportWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (HARNESS_WORKTREE /
                "tools/workflow-tools/harness/public_entry.py").is_file():
            raise AssertionError(
                f"pinned harness w4-u54 worktree missing at "
                f"{HARNESS_WORKTREE}; the F123 export bridge cannot be "
                "verified")
        cls.holder = tempfile.TemporaryDirectory(prefix="juscite-f123-wiring-")
        state_root = Path(cls.holder.name)
        (state_root / "harness-state").mkdir(parents=True)
        cls.config = _config(state_root)
        cls.state_root = state_root
        sys.path.insert(0, str(HARNESS_WORKTREE / "src"))
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root / "harness-state")
        store.create_matter(MATTER_X, "cas://f123-wiring")

    @classmethod
    def tearDownClass(cls):
        cls.holder.cleanup()

    def test_01_sign_export_full_chain_binds_ledger(self):
        result = legal_entry.call("export.package",
                                  _package_args("f123-w1", SYNTH_FILES),
                                  self.config)
        export_dir = Path(result["dir"])
        # 产物三件在盘＋逐文件 hash 与清单一致。
        for path, blob in SYNTH_FILES:
            on_disk = export_dir / "files" / Path(*path.split("/"))
            self.assertTrue(on_disk.is_file(), path)
            self.assertEqual(hashlib.sha256(on_disk.read_bytes()).hexdigest(),
                             hashlib.sha256(blob).hexdigest())
        # 清单＋签名在盘；清单 canonical 摘要与回执/账本三方一致。
        document = json.loads(
            (export_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "lvyin-signed-export/1")
        self.assertEqual(document["algorithm"], "HMAC-SHA256")
        self.assertEqual(len(document["files"]), 3)
        manifest = {k: v for k, v in document.items() if k != "signature"}
        digest = hashlib.sha256(canonical(manifest)).hexdigest()
        self.assertEqual(result["manifestSha256"], digest)
        self.assertEqual(result["recordRef"]["owner"], "harness")
        record = legal_entry.call("harness.export_record_read",
                                  {"scope": {"kind": "matter",
                                             "matterId": MATTER_X},
                                   "export_id": "f123-w1"}, self.config)
        self.assertEqual(record["manifestSha256"], digest)
        self.assertEqual(record["fileCount"], 3)
        # 密钥只存 state：signing.secret 在（32B）；密钥本体（原始字节/
        # hex）不在清单文件与账面回执（只许指纹在场）。
        secret = (Path(self.config["signed_export_state_root"])
                  / "f123-export" / "signing.secret")
        self.assertTrue(secret.is_file())
        key = secret.read_bytes()
        self.assertEqual(len(key), 32)
        manifest_text = (export_dir / "manifest.json").read_text(
            encoding="utf-8")
        record_text = json.dumps(record, ensure_ascii=False)
        for needle in (key, key.hex().encode("ascii")):
            self.assertNotIn(needle, manifest_text.encode("utf-8"))
            self.assertNotIn(needle.decode("latin-1"), record_text)

    def test_02_idempotent_replay_same_manifest_no_dup(self):
        first = legal_entry.call("export.package",
                                 _package_args("f123-w2", SYNTH_FILES),
                                 self.config)
        second = legal_entry.call("export.package",
                                  _package_args("f123-w2", SYNTH_FILES),
                                  self.config)
        self.assertEqual(first["manifestSha256"], second["manifestSha256"])
        self.assertEqual(first["recordRef"]["id"],
                         second["recordRef"]["id"])
        listed = legal_entry.call("export.package_list",
                                  {"matterId": MATTER_X}, self.config)
        rows = [i for i in listed["items"] if i["exportId"] == "f123-w2"]
        self.assertEqual(len(rows), 1)

    def test_03_same_export_id_different_content_refused(self):
        legal_entry.call("export.package",
                         _package_args("f123-w3", SYNTH_FILES), self.config)
        swapped = [("docs/起诉状-合成案.docx", b"tampered different bytes")]
        # 同 export_id 异文件集＝签发面本地先拒不落盘（typed 码经
        # NotConnected 信封透传；若本地漏拦，账本 f123_export_id_conflict
        # 具名拒是第二道防线）。
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("export.package",
                             _package_args("f123-w3", swapped), self.config)
        self.assertIn("f123_export_id_conflict", str(caught.exception))

    def test_04_independent_verify_pass_on_clean_export(self):
        legal_entry.call("export.package",
                         _package_args("f123-w4", SYNTH_FILES), self.config)
        verdict = legal_entry.call("export.verify",
                                   {"exportId": "f123-w4"}, self.config)
        self.assertEqual(verdict["verdict"], "PASS")
        self.assertEqual(verdict["findings"], [])
        self.assertTrue(verdict["signatureValid"])
        self.assertEqual(verdict["checkedFileCount"], 3)
        record = legal_entry.call("harness.export_record_read",
                                  {"scope": {"kind": "matter",
                                             "matterId": MATTER_X},
                                   "export_id": "f123-w4"}, self.config)
        self.assertEqual(verdict["manifestSha256"],
                         record["manifestSha256"])

    def test_05_three_tamper_forms_detected_and_localized(self):
        base = legal_entry.call("export.package",
                                _package_args("f123-w5", SYNTH_FILES),
                                self.config)
        exports_root = (Path(self.config["signed_export_state_root"])
                        / "f123-export" / "exports")

        def make_copy(suffix: str) -> Path:
            import shutil
            target = exports_root / f"f123-w5-{suffix}"
            shutil.copytree(exports_root / "f123-w5", target)
            return target

        # ① 改单文件字节 → file_hash_mismatch 定位到该文件。
        copy1 = make_copy("t1")
        victim = copy1 / "files" / "evidence" / "证据-合成卷.pdf"
        victim.write_bytes(victim.read_bytes() + b"x")
        v1 = legal_entry.call("export.verify",
                              {"exportId": "f123-w5-t1"}, self.config)
        self.assertEqual(v1["verdict"], "TAMPERED")
        forms1 = [(f["form"], f["path"]) for f in v1["findings"]]
        self.assertIn(("file_hash_mismatch", "evidence/证据-合成卷.pdf"),
                      forms1)

        # ② 增/换外来文件 → file_not_in_manifest 定位到该文件。
        copy2 = make_copy("t2")
        (copy2 / "files" / "docs" / "外来件-合成.txt").write_bytes(
            b"foreign file")
        v2 = legal_entry.call("export.verify",
                              {"exportId": "f123-w5-t2"}, self.config)
        forms2 = [(f["form"], f["path"]) for f in v2["findings"]]
        self.assertIn(("file_not_in_manifest", "docs/外来件-合成.txt"),
                      forms2)

        # ③ 删文件 → file_missing 定位到该文件。
        copy3 = make_copy("t3")
        (copy3 / "files" / "README-合成导出.txt").unlink()
        v3 = legal_entry.call("export.verify",
                              {"exportId": "f123-w5-t3"}, self.config)
        forms3 = [(f["form"], f["path"]) for f in v3["findings"]]
        self.assertIn(("file_missing", "README-合成导出.txt"), forms3)

        # ④ 清单本身被改 → manifest_signature_invalid（签名不验）。
        copy4 = make_copy("t4")
        document = json.loads(
            (copy4 / "manifest.json").read_text(encoding="utf-8"))
        document["files"][0]["sha256"] = "0" * 64
        (copy4 / "manifest.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=1,
                       sort_keys=True), encoding="utf-8")
        v4 = legal_entry.call("export.verify",
                              {"exportId": "f123-w5-t4"}, self.config)
        forms4 = [f["form"] for f in v4["findings"]]
        self.assertIn("manifest_signature_invalid", forms4)
        self.assertFalse(v4["signatureValid"])
        # 干净导出不受影响（base 复验仍 PASS——篡改只伤被篡副本）。
        v0 = legal_entry.call("export.verify",
                              {"exportId": "f123-w5"}, self.config)
        self.assertEqual(v0["verdict"], "PASS")

    def test_06_verification_receipts_recorded_pass_and_tampered(self):
        legal_entry.call("export.package",
                         _package_args("f123-w6", SYNTH_FILES), self.config)
        clean = legal_entry.call("export.verify",
                                 {"exportId": "f123-w6"}, self.config)
        record = legal_entry.call("harness.export_record_read",
                                  {"scope": {"kind": "matter",
                                             "matterId": MATTER_X},
                                   "export_id": "f123-w6"}, self.config)
        ok = legal_entry.call("harness.export_verification_record", {
            "actor_id": "lvyin-product",
            "scope": {"kind": "matter", "matterId": MATTER_X},
            "key": _key("v-w6-1"), "export_id": "f123-w6",
            "verdict": clean["verdict"], "findings": clean["findings"],
            "verifier": "export_manifest_checker/1",
            "checked_file_count": clean["checkedFileCount"],
            "manifest_sha256": clean["manifestSha256"]}, self.config)
        self.assertTrue(ok["created"])
        # 篡改形态落 TAMPERED 回执（findings 定位到具体文件）。
        exports_root = (Path(self.config["signed_export_state_root"])
                        / "f123-export" / "exports")
        import shutil
        shutil.copytree(exports_root / "f123-w6",
                        exports_root / "f123-w6-tam")
        victim = (exports_root / "f123-w6-tam" / "files" / "docs"
                  / "起诉状-合成案.docx")
        victim.write_bytes(b"tampered")
        bad = legal_entry.call("export.verify",
                               {"exportId": "f123-w6-tam"}, self.config)
        self.assertEqual(bad["verdict"], "TAMPERED")
        tam = legal_entry.call("harness.export_verification_record", {
            "actor_id": "lvyin-product",
            "scope": {"kind": "matter", "matterId": MATTER_X},
            "key": _key("v-w6-2"), "export_id": "f123-w6",
            "verdict": bad["verdict"], "findings": bad["findings"],
            "verifier": "export_manifest_checker/1",
            "checked_file_count": bad["checkedFileCount"],
            "manifest_sha256": bad["manifestSha256"]}, self.config)
        self.assertEqual(tam["verificationSeq"], 2)
        history = legal_entry.call("harness.export_verification_list", {
            "scope": {"kind": "matter", "matterId": MATTER_X},
            "export_id": "f123-w6"}, self.config)
        self.assertEqual([i["verdict"] for i in history["items"]],
                         ["PASS", "TAMPERED"])
        # 结论与事实互斥绑定：PASS 带 findings＝账面具名拒。
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call("harness.export_verification_record", {
                "actor_id": "lvyin-product",
                "scope": {"kind": "matter", "matterId": MATTER_X},
                "key": _key("v-w6-3"), "export_id": "f123-w6",
                "verdict": "PASS",
                "findings": [{"form": "file_missing", "path": "x"}],
                "verifier": "export_manifest_checker/1",
                "checked_file_count": 3,
                "manifest_sha256": clean["manifestSha256"]}, self.config)
        self.assertIn("f123_verdict_findings_mismatch",
                      str(caught.exception))

    def test_07_secret_exposure_scan_zero_hits_with_positive_control(self):
        legal_entry.call("export.package",
                         _package_args("f123-w7", SYNTH_FILES), self.config)
        scan = legal_entry.call("export.secret_exposure_scan", {},
                                self.config)
        self.assertFalse(scan["exposed"])
        self.assertGreaterEqual(scan["scannedFiles"], 4)
        # 正控：另立临时状态根，把密钥 hex 写进一个产物文件——同法扫描
        # 必命中（证明扫描非空转；F41 同法）。
        with tempfile.TemporaryDirectory(
                prefix="juscite-f123-posctl-") as control_tmp:
            control_config = _config(Path(control_tmp))
            control_state = Path(control_config["signed_export_state_root"])
            from signed_export import _load_or_create_key
            key = _load_or_create_key(control_state / "f123-export")
            leak_dir = control_state / "f123-export" / "exports" / "leak"
            leak_dir.mkdir(parents=True)
            (leak_dir / "leak.bin").write_bytes(key.hex().encode("ascii"))
            control = legal_entry.call("export.secret_exposure_scan", {},
                                       control_config)
            self.assertTrue(control["exposed"])
            self.assertEqual(control["exposedFile"], "leak.bin")

    def test_08_checker_independent_path_ast(self):
        python_dir = ROOT / "python"
        checker_tree = ast.parse(
            (python_dir / "export_manifest_checker.py").read_text(
                encoding="utf-8"))
        signer_tree = ast.parse(
            (python_dir / "signed_export.py").read_text(encoding="utf-8"))
        # 验证器零 import 签发器（独立代码路径——calc_checker 先例）。
        for tree, name in ((checker_tree, "export_manifest_checker"),
                           (signer_tree, "signed_export")):
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertNotIn("signed_export", imported, name)
            self.assertNotIn("export_manifest_checker", imported, name)
        # 双面零网络（出站通道结构性不存在）。
        forbidden = {"socket", "ssl", "urllib", "http", "requests",
                     "subprocess"}
        for tree, name in ((checker_tree, "export_manifest_checker"),
                           (signer_tree, "signed_export")):
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported |= {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertEqual(imported & forbidden, set(), name)

    def test_09_bridge_fail_closed(self):
        # 未配置 harness 桥＝NOT_CONNECTED 具名（export 依赖账本）。
        with tempfile.TemporaryDirectory(
                prefix="juscite-f123-noharness-") as bare_tmp:
            bare = _config(Path(bare_tmp))
            bare["harness_public_entry"] = ""
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call("export.package",
                                 _package_args("f123-w9", SYNTH_FILES),
                                 bare)
            self.assertIn("harness_public_entry_not_configured",
                          str(caught.exception))
        # 未配置状态根＝签发面具名拒。
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("export.package",
                             _package_args("f123-w9b", SYNTH_FILES),
                             {"harness_public_entry": "x"})
        self.assertIn("f123_state_root_not_configured",
                      str(caught.exception))
        # 封闭注册外方法具名拒（三组外）。
        for method in ("export.sign", "export.verify_remote",
                       "harness.export_sign"):
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call(method, {}, self.config)
            self.assertIn("method_not_connected", str(caught.exception))
        # 验证器：未知导出具名拒。
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("export.verify",
                             {"exportId": "f123-none"}, self.config)
        self.assertIn("f123chk_export_not_found", str(caught.exception))

    def test_10_content_determinism_across_state_roots(self):
        with tempfile.TemporaryDirectory(
                prefix="juscite-f123-det-") as det_tmp:
            det_config = _config(Path(det_tmp))
            from legal_harness.state.matter_store import MatterStore
            MatterStore(Path(det_config["harness_state_root"])).create_matter(
                MATTER_X, "cas://f123-det")
            result = legal_entry.call("export.package",
                                      _package_args("f123-w10",
                                                    SYNTH_FILES),
                                      det_config)
        base = legal_entry.call("export.package",
                                _package_args("f123-w10b", SYNTH_FILES),
                                self.config)
        # 内容级确定性：逐文件 hash/文件集摘要/算法/指纹算法面跨状态根相
        # 等（manifest 含真实时钟 createdAt——清单字节不主张跨跑相同，
        # U08/E15 剥时间戳先例）。
        self.assertEqual(result["fileSetDigest"], base["fileSetDigest"])
        self.assertEqual(result["fileCount"], base["fileCount"])
        self.assertEqual(result["algorithm"], base["algorithm"])
        verdict_a = legal_entry.call("export.verify",
                                     {"exportId": "f123-w10b"},
                                     self.config)
        self.assertEqual(verdict_a["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
