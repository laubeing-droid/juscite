"""F11 备份独立恢复对账 产品侧接线测试（W3-U11）。

全部合成材料。backup_restore 产品面（backup_sets+restore_jobs+口令加密+
每日 schedule+结构对账）与 legal_entry BACKUP_METHODS 桥 fail-closed：
- 密闭组用临时目录内的合成 stub harness owner 面（backup=zip/restore=
  解包/integrity=ok）驱动编排面全流程——编排面绝不自实现第二套存储快照，
  owner 面只被消费；真 harness MatterStore/E08 backup-restore 的行为由
  harness 仓 verify 门禁与本仓对账工具（sha256 钉定漂移响亮拒）双面保证。
- 真_owner 组（检出缺席则整组诚实 skip，绝不假绿）在真 harness
  MatterStore 上钉死：WAL 未检查点已提交内容进快照（一致备份）、恢复根
  公开读数逐键相等（对象/引用/字节验真的底座）。
- 红线：坏包/错口令=先全量验包后落位（零写入）；恢复目标绝不与声明现根
  重叠；金额面零浮点（本组不产金额，语义验真在对账工具）。
"""

from __future__ import annotations

import base64
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
from backup_restore import (  # noqa: E402
    PACKAGE_MAGIC, PACKAGE_SUFFIX, SET_LEDGER, JOB_LEDGER, _digest_tree,
    _fernet)

HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u53")

STUB_MATTER_STORE = '''
"""Synthetic harness owner face for hermetic coordinator tests (W3-U11)."""
import hashlib, zipfile
from pathlib import Path


class MatterStore:
    def __init__(self, state_root):
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.root = self.state_root / "data"

    def seed(self, name, payload):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def integrity_check(self):
        return {"ok": True}

    def backup(self, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w") as archive:
            for path in sorted(self.root.rglob("*")):
                if path.is_file():
                    archive.write(path, "data/" + str(
                        path.relative_to(self.root)).replace("\\\\", "/"))
        return {"path": str(destination),
                "sha256": hashlib.sha256(
                    destination.read_bytes()).hexdigest(),
                "integrity": {"ok": True}}

    @classmethod
    def restore(cls, backup, target_root):
        target_root = Path(target_root)
        if target_root.exists() and any(target_root.iterdir()):
            raise ValueError("restore_target_not_empty")
        target_root.mkdir(parents=True)
        with zipfile.ZipFile(backup) as archive:
            archive.extractall(target_root)
        return cls(target_root)
'''


def _code(exc: NotConnected) -> str:
    text = str(exc)
    prefix = "backup_failed:"
    return text[len(prefix):] if text.startswith(prefix) else text


def _write_config(tmp: Path, *, passphrase="pw-f11-synthetic", **overrides):
    config = {
        "backup_state_root": str(tmp / "backup-root"),
        "backup_passphrase": passphrase,
        "backup_targets": [
            {"id": "anonymizer", "kind": "dir",
             "root": str(tmp / "live" / "anonymizer")},
            {"id": "product", "kind": "dir",
             "root": str(tmp / "live" / "product")},
        ],
        "harness_import_path": str(tmp / "stub-harness"),
    }
    config.update(overrides)
    return config


def _seed_live(tmp: Path) -> dict:
    markers = {}
    anon = tmp / "live" / "anonymizer"
    (anon / "overlay" / "m-f11").mkdir(parents=True)
    (anon / "overlay" / "m-f11" / "revisions.json").write_text(
        json.dumps({"synthetic": "f11-overlay-ledger"}), encoding="utf-8")
    (anon / "originals").mkdir(parents=True, exist_ok=True)
    (anon / "originals" / "orig.txt").write_bytes("F11 合成原件字节。".encode())
    prod = tmp / "live" / "product"
    (prod / "config").mkdir(parents=True)
    (prod / "config" / "lvyin-f11.json").write_text(
        json.dumps({"surface": "f11-synthetic-product-state"}), encoding="utf-8")
    markers["anonymizer"] = _digest_tree(anon)
    markers["product"] = _digest_tree(prod)
    return markers


def _write_stub_harness(tmp: Path) -> Path:
    src = tmp / "stub-harness" / "src" / "legal_harness" / "state"
    src.mkdir(parents=True)
    (src / "matter_store.py").write_text(STUB_MATTER_STORE, encoding="utf-8")
    return tmp / "stub-harness"


class F11BackupRestoreWiringTests(unittest.TestCase):
    """密闭组：编排面全流程（stub owner 面）＋桥 fail-closed。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="f11-wiring-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.harness_root = _write_stub_harness(self.tmp)
        self.live = _seed_live(self.tmp)
        self.config = _write_config(self.tmp)

    def _create(self, now="2026-10-18T08:00:00Z", config=None):
        return legal_entry.call(
            "backup.create", {"now": now}, config or self.config)

    def _restore(self, backup_id, config=None, **kwargs):
        args = {"backup_id": backup_id,
                "restore_root": str(self.tmp / "restore-root"), **kwargs}
        return legal_entry.call("backup.restore", args, config or self.config)

    def test_create_package_set_row_and_no_plaintext(self):
        row = self._create()
        package = Path(self.config["backup_state_root"]) / "packages" / (
            row["backup_id"] + PACKAGE_SUFFIX)
        self.assertTrue(package.is_file())
        packaged = package.read_bytes()
        self.assertTrue(packaged.startswith(b"LVTBAK1\n"))
        # 口令与全部明文标记不出现在包字节（口令加密到位）。
        for secret in ("pw-f11-synthetic", "f11-overlay-ledger",
                       "F11 合成原件字节。", "f11-synthetic-product-state"):
            self.assertNotIn(secret.encode("utf-8"), packaged)
        # 暂存明文已删。
        staging = Path(self.config["backup_state_root"]) / "staging"
        self.assertEqual(list(staging.iterdir()) if staging.exists() else [],
                         [])
        # 账行落定且 backup.sets 可回读。
        sets = legal_entry.call("backup.sets", {}, self.config)
        self.assertEqual(len(sets["sets"]), 1)
        self.assertEqual(sets["sets"][0]["backup_id"], row["backup_id"])
        self.assertEqual(sets["sets"][0]["package"]["sha256"],
                         row["package"]["sha256"])
        self.assertEqual(sets["jobs"], [])
        # manifest 文件计数=两目录目标文件数之和。
        self.assertEqual(row["file_count"],
                         len(self.live["anonymizer"]) + len(self.live["product"]))

    def test_restore_reconcile_roundtrip_independent_root(self):
        row = self._create()
        job = self._restore(row["backup_id"])
        self.assertEqual(job["kind"], "restore")
        restore_root = self.tmp / "restore-root"
        for target_id in ("anonymizer", "product"):
            restored = restore_root / target_id
            self.assertTrue(restored.is_dir())
            self.assertEqual(_digest_tree(restored), self.live[target_id])
        recon = legal_entry.call(
            "backup.reconcile",
            {"backup_id": row["backup_id"],
             "restore_root": str(restore_root)}, self.config)
        self.assertEqual(recon["verdict"], "RECON_OK")
        checks = {f["check"]: f["status"] for f in recon["findings"]}
        self.assertEqual(set(checks.values()), {"PASS"})
        jobs = legal_entry.call("backup.sets", {}, self.config)["jobs"]
        self.assertEqual([j["kind"] for j in jobs], ["restore", "reconcile"])

    def test_bad_package_refuses_without_writing_anything(self):
        row = self._create()
        package = Path(self.config["backup_state_root"]) / "packages" / (
            row["backup_id"] + PACKAGE_SUFFIX)
        raw = bytearray(package.read_bytes())
        raw[-3] ^= 0xFF  # 翻转密文尾部＝MAC 必炸
        package.write_bytes(bytes(raw))
        before = {tid: _digest_tree(self.tmp / "live" / tid)
                  for tid in ("anonymizer", "product")}
        with self.assertRaises(NotConnected) as caught:
            self._restore(row["backup_id"])
        self.assertEqual(_code(caught.exception), "f11_package_unreadable")
        restore_root = self.tmp / "restore-root"
        self.assertFalse((restore_root / "anonymizer").exists())
        self.assertFalse((restore_root / "product").exists())
        after = {tid: _digest_tree(self.tmp / "live" / tid)
                 for tid in ("anonymizer", "product")}
        self.assertEqual(before, after)  # 现根零触碰

    def test_restore_rejects_member_path_escape(self):
        """解密后的清单仍不可信：`..` / 绝对路径不得写到恢复根之外。"""
        row = self._create()
        package = Path(self.config["backup_state_root"]) / "packages" / (
            row["backup_id"] + PACKAGE_SUFFIX)
        raw = package.read_bytes()
        newline = raw.index(b"\n", len(PACKAGE_MAGIC))
        header = json.loads(raw[len(PACKAGE_MAGIC):newline].decode("utf-8"))
        salt = base64.b64decode(header["kdf"]["salt_b64"])
        inner = _fernet(self.config["backup_passphrase"], salt).decrypt(
            raw[newline + 1:])
        with zipfile.ZipFile(io.BytesIO(inner)) as archive:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            payload = {name: archive.read(name) for name in archive.namelist()}
        for target in manifest["targets"]:
            if target["kind"] != "dir":
                continue
            target["files"]["../../escaped-f11.txt"] = {
                "sha256": "0" * 64, "size": 4}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in payload.items():
                if name == "manifest.json":
                    continue
                archive.writestr(name, data)
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        token = _fernet(self.config["backup_passphrase"], salt).encrypt(
            buf.getvalue())
        package.write_bytes(raw[:newline + 1] + token)
        marker = self.tmp / "escaped-f11.txt"
        with self.assertRaises(NotConnected) as caught:
            self._restore(row["backup_id"])
        self.assertEqual(_code(caught.exception), "f11_member_path_invalid")
        self.assertFalse(marker.exists())
        self.assertFalse(any(self.tmp.rglob("escaped-f11.txt")))

    def test_wrong_passphrase_same_named_refusal(self):
        row = self._create()
        other = _write_config(self.tmp, passphrase="pw-other-999")
        with self.assertRaises(NotConnected) as caught:
            self._restore(row["backup_id"], config=other)
        self.assertEqual(_code(caught.exception), "f11_package_unreadable")
        self.assertFalse((self.tmp / "restore-root" / "product").exists())

    def test_restore_never_overlaps_live_root_or_nonempty_target(self):
        row = self._create()
        # 恢复根=live 根父目录 → 目标目录恰为现根：好包也拒。
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "backup.restore",
                {"backup_id": row["backup_id"],
                 "restore_root": str(self.tmp / "live")}, self.config)
        self.assertEqual(_code(caught.exception),
                         "f11_restore_target_overlaps_live_root")
        # 同一恢复根二次恢复 → 目标已存在非空。
        self._restore(row["backup_id"])
        with self.assertRaises(NotConnected) as caught:
            self._restore(row["backup_id"])
        self.assertEqual(_code(caught.exception), "f11_restore_target_not_empty")

    def test_reconcile_requires_restore(self):
        row = self._create()
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call(
                "backup.reconcile",
                {"backup_id": row["backup_id"],
                 "restore_root": str(self.tmp / "restore-root")}, self.config)
        self.assertEqual(_code(caught.exception),
                         "f11_reconcile_requires_restore")

    def test_schedule_daily_due_semantics(self):
        schedule = lambda now, cfg=None: legal_entry.call(  # noqa: E731
            "backup.schedule", {"now": now}, cfg or self.config)
        first = schedule("2026-10-18T08:00:00Z")
        self.assertTrue(first["due"] and first["last_backup_date"] is None)
        self._create(now="2026-10-18T09:00:00Z")
        same_day = schedule("2026-10-18T15:00:00Z")
        self.assertFalse(same_day["due"])
        self.assertEqual(same_day["next_due_date"], "2026-10-19")
        next_day = schedule("2026-10-19T00:00:00Z")
        self.assertTrue(next_day["due"])
        every_second = _write_config(self.tmp)
        every_second["backup_schedule"] = {"interval_days": 2}
        spaced = schedule("2026-10-19T00:00:00Z", every_second)
        self.assertFalse(spaced["due"])
        self.assertEqual(spaced["next_due_date"], "2026-10-20")
        bad = _write_config(self.tmp)
        bad["backup_schedule"] = {"interval_days": 0}
        with self.assertRaises(NotConnected) as caught:
            schedule("2026-10-19T00:00:00Z", bad)
        self.assertEqual(_code(caught.exception),
                         "f11_schedule_interval_invalid")

    def test_bridge_fail_closed_negatives(self):
        cases = [
            ("backup.sets", {}, {}, "f11_backup_state_root_not_configured"),
            ("backup.create", {"now": "2026-10-18T00:00:00Z"},
             _write_config(self.tmp, passphrase=""), "f11_passphrase_required"),
            ("backup.create", {"now": "2026-10-18T00:00:00Z"},
             _write_config(self.tmp, **{
                 "backup_targets": [{"id": "x", "kind": "tape",
                                     "root": str(self.tmp)}]}),
             "f11_target_kind_unknown"),
            ("backup.create", {"now": "2026-10-18T00:00:00Z"},
             _write_config(self.tmp, **{
                 "backup_targets": [{"id": "x", "kind": "dir",
                                     "root": str(self.tmp / "nope")}]}),
             "f11_target_root_missing"),
            ("backup.restore", {"backup_id": "bk-none",
                                "restore_root": str(self.tmp / "r")},
             self.config, "f11_backup_set_unknown"),
        ]
        for method, args, config, want in cases:
            with self.subTest(code=want):
                with self.assertRaises(NotConnected) as caught:
                    legal_entry.call(method, args, config)
                self.assertEqual(_code(caught.exception), want)
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("backup.explode", {}, self.config)
        self.assertIn("method_not_connected", str(caught.exception))


@unittest.skipUnless(
    (HARNESS_ROOT / "src" / "legal_harness" / "state" / "matter_store.py")
    .is_file(), "pinned harness checkout absent on this machine")
class F11HarnessOwnerFaceTests(unittest.TestCase):
    """真 owner 面（E08 MatterStore）：一致备份与恢复根公开读数。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="f11-owner-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_wal_committed_content_survives_backup_restore(self):
        sys.path.insert(0, str(HARNESS_ROOT / "src"))
        from legal_harness.state.matter_store import MatterStore
        from legal_harness.business.units import HarnessUnits
        live_root = self.tmp / "harness-live"
        store = MatterStore(live_root)
        store.create_matter("m-f11-wal", "cas://profile-f11-synthetic")
        units = HarnessUnits(store)
        doc = "委托代理合同（F11 一致备份探针合成）。".encode("utf-8")
        import base64
        units.register_material(
            "lawyer-1", {"kind": "matter", "matterId": "m-f11-wal"},
            {"requestId": "rm-wal-1", "targetId": None,
             "expectedRevision": None, "inputRefs": []},
            {"id": "mat-f11-wal", "kind": "digital_text",
             "title": "F11 探针合成", "bytesB64":
                 base64.b64encode(doc).decode("ascii")})
        # 持 open 连接写入已提交但留在 WAL 的探针行（不 checkpoint）。
        probe_value = "wal-probe-" + uuid.uuid4().hex
        held = sqlite3.connect(str(store.database_path))
        try:
            held.execute("CREATE TABLE IF NOT EXISTS f11_wal_probe(v TEXT)")
            held.execute("INSERT INTO f11_wal_probe VALUES (?)", (probe_value,))
            held.commit()
            config = {
                "backup_state_root": str(self.tmp / "backup-root"),
                "backup_passphrase": "pw-f11-owner",
                "backup_targets": [
                    {"id": "harness", "kind": "harness_store",
                     "root": str(live_root)}],
                "harness_import_path": str(HARNESS_ROOT),
            }
            row = legal_entry.call("backup.create",
                                   {"now": "2026-10-18T10:00:00Z"}, config)
            job = legal_entry.call(
                "backup.restore",
                {"backup_id": row["backup_id"],
                 "restore_root": str(self.tmp / "restore-root")}, config)
            restored_root = Path(
                job["targets"][0]["restored_root"])
            # 快照独立可开：无 -wal 文件仍含 WAL 已提交内容（一致备份）。
            probe = sqlite3.connect(
                str(restored_root / "core" / "matter-store.sqlite3"))
            try:
                got = [r[0] for r in probe.execute(
                    "SELECT v FROM f11_wal_probe").fetchall()]
            finally:
                probe.close()
            self.assertEqual(got, [probe_value])
            # 恢复根经 owner 面 integrity + 公开读数（对象/引用/字节）。
            restored = MatterStore(restored_root)
            self.assertTrue(restored.integrity_check()["ok"])
            read = HarnessUnits(restored).read_material(
                {"kind": "matter", "matterId": "m-f11-wal"},
                material_id="mat-f11-wal", revision=1)
            self.assertEqual(base64.b64decode(read["bytesB64"]), doc)
            self.assertEqual(read["casRef"], f"cas://{read['sha256']}")
        finally:
            held.close()


if __name__ == "__main__":
    unittest.main()
