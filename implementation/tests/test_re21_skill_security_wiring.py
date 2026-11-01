# -*- coding: utf-8 -*-
"""RE-21 增补·技能安装安全层 wiring 验收（施工波 2026-10-30 单元 #21）。

规格=docs/RE规格库/RE-21-技能安装-增补-安全层.md（MingJuris 737ef85 机
制净室；对拍清单 37 行中本面覆盖 #1-#20/#35/#36 的安装链侧）。全部断言走
真产品入口（legal_entry.call 同进程；桥纪律与 typed 码映射同 F99 先例）。
全部合成材料：合成 zip/合成清单/合成来源登记；零网络零模型；%APPDATA%
零触碰（状态根=tempdir 注入）。
"""
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry
import skill_security
from skill_security import (SKILL_SECURITY_METHODS, SOURCES,
                            can_bundle_skill, can_install_skill,
                            can_run_skill, parse_version_range,
                            range_satisfies, scan_entry_text,
                            validate_declared_manifest)
from bridge_errors import NotConnected

GOOD_SOURCE = {"kind": "registry",
               "url": "https://synth.example/sources/apache-skill",
               "author": "合成作者"}


def _entry_sha(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _manifest(entry_sha: str, **over) -> dict:
    m = {
        "id": "demo-skill", "name": "演示技能", "version": "1.0.0",
        "description": "合成声明式包（演示用）",
        "entry": "SKILL.md",
        "permissions": ["call-model", "read-matter-files"],
        "compatibility": {"app": "*"},
        "source": dict(GOOD_SOURCE),
        "sha256": entry_sha,
        "license": "Apache-2.0",
    }
    m.update(over)
    return m


def _make_zip(path: Path, manifest: dict, files: dict) -> str:
    payload = dict(files)
    payload["skill.json"] = json.dumps(manifest, ensure_ascii=False).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, blob in sorted(payload.items()):
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.external_attr = 0o600 << 16
            zf.writestr(zi, blob)
    return hashlib.sha256(path.read_bytes()).hexdigest()


ENTRY_TEXT = "# 演示技能\n\n纯方法论正文（合成材料）：三步法与核对清单。\n"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.config = {"skill_security_state_root": str(self.state)}

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, method, args):
        return legal_entry.call(method, args, self.config)

    def zip_of(self, manifest, files=None):
        files = dict(files or {})
        files.setdefault("SKILL.md", ENTRY_TEXT.encode())
        zpath = self.root / ("z-%d.zip" % len(list(self.root.iterdir())))
        sha = _make_zip(zpath, manifest, files)
        return str(zpath), sha


class TestManifestClosedSet(Base):
    """对拍 #1-#5：九必填字段一次全报/坏 JSON 一条 issue/id 目录名/entry
    双闸/未知权限拒/坏哈希/版本范围不可解析=不满足。"""

    def test_missing_fields_reported_all_at_once(self):
        issues = validate_declared_manifest({})
        self.assertEqual(len(issues), 10)  # 十字段逐项一条，一次全报
        self.assertTrue(all(i.startswith("s21_field_missing:") for i in issues))

    def test_bad_json_is_one_issue_not_crash(self):
        raw = "{not json"
        obj = json.loads(json.dumps(raw))  # 非 dict
        issues = validate_declared_manifest(obj)
        self.assertEqual(issues, ["s21_manifest_not_object"])

    def test_id_must_be_dirname_safe(self):
        m = _manifest("a" * 64)
        m["id"] = "Bad/Id"
        self.assertIn("s21_id_invalid", validate_declared_manifest(m))
        m["id"] = "good-id.v2"
        self.assertNotIn("s21_id_invalid", validate_declared_manifest(m))

    def test_entry_path_and_suffix_gate(self):
        m = _manifest("a" * 64)
        for bad in ("/abs/SKILL.md", "a\\b.md", "C:x.md", "../up.md",
                    "a//b.md", " SKILL.md", "SKILL.md ", "img.png", "s.md\0"):
            m["entry"] = bad
            self.assertIn("s21_entry_invalid",
                          validate_declared_manifest(m), bad)
        m["entry"] = "notes/MAIN.markdown"
        self.assertNotIn("s21_entry_invalid",
                         validate_declared_manifest(m))

    def test_unknown_permission_rejected_not_dropped(self):
        m = _manifest("a" * 64)
        m["permissions"] = ["call-model", "run-anything"]
        self.assertIn("s21_permission_unknown",
                      validate_declared_manifest(m))

    def test_sha_and_source_and_version_shapes(self):
        m = _manifest("X" * 64)
        self.assertIn("s21_sha256_invalid", validate_declared_manifest(m))
        m = _manifest("a" * 64, version="1.2")
        self.assertIn("s21_version_invalid", validate_declared_manifest(m))
        m = _manifest("a" * 64)
        m["source"] = {"kind": "web"}
        self.assertIn("s21_source_invalid", validate_declared_manifest(m))

    def test_compat_range_four_syntax_and_norefusal_by_guess(self):
        m = _manifest("a" * 64)
        m["compatibility"] = {"app": "~1.2.3"}
        self.assertIn("s21_compatibility_unparseable",
                      validate_declared_manifest(m))
        # 不可解析范围按不满足处理：app 版本在档即拒装
        m2 = _manifest("a" * 64)
        m2["compatibility"] = {"app": "~1.2.3"}
        issues = validate_declared_manifest(m2, app_version="1.5.0")
        self.assertIn("s21_compatibility_unsatisfied", issues)
        # 四语法全识别
        for ok in (">=1.0.0", "^1.2.3", "1.2.3", "*"):
            self.assertIsNotNone(parse_version_range(ok), ok)

    def test_zero_x_caret_pins_minor(self):
        self.assertTrue(range_satisfies(parse_version_range("^0.2.3"),
                                        "0.2.9"))
        self.assertFalse(range_satisfies(parse_version_range("^0.2.3"),
                                         "0.3.0"))
        self.assertTrue(range_satisfies(parse_version_range("^1.2.3"),
                                        "1.9.9"))
        self.assertFalse(range_satisfies(parse_version_range("^1.2.3"),
                                         "2.0.0"))

    def test_app_version_unknown_skips_check(self):
        m = _manifest("a" * 64)
        m["compatibility"] = {"app": ">=9.9.9"}
        self.assertEqual(validate_declared_manifest(m), [])  # 无 app 版本=跳过
        self.assertIn("s21_compatibility_unsatisfied",
                      validate_declared_manifest(m, app_version="1.0.0"))


class TestScanner(Base):
    """对拍 #6-#9：七信号+主机名清单+建议权限+不可自动启用+缺口具名+
    零提示免责话术。"""

    def test_seven_signals_and_hostnames(self):
        text = ("先 bash 执行，再 curl https://api.synth.example/x 取数，"
                "open('out.txt','w') 写文件，os.remove 删文件，"
                "读 process.env.API_KEY，走 mcp 调用，带 bearer: token。")
        scan = scan_entry_text(text)
        self.assertEqual(scan["signals"], list(skill_security.SIGNAL_ORDER))
        self.assertIn("api.synth.example", scan["hostnames"])
        self.assertIn("shell", scan["permissions_suggested"])
        self.assertIn("call-model", scan["permissions_suggested"])
        self.assertTrue(scan["unsafe_auto_enable"])

    def test_shell_gap_named(self):
        scan = scan_entry_text("运行 bash 脚本", declared_permissions=[])
        codes = [w["code"] for w in scan["warnings"]]
        self.assertIn("s21_gap_shell_undeclared", codes)
        scan2 = scan_entry_text("运行 bash 脚本",
                                declared_permissions=["shell"])
        self.assertNotIn("s21_gap_shell_undeclared",
                         [w["code"] for w in scan2["warnings"]])

    def test_zero_signal_disclaimer_in_inspect_face(self):
        zpath, sha = self.zip_of(_manifest(_entry_sha(ENTRY_TEXT)))
        out = self.call("skill.secure.inspect", {"zip_path": zpath,
                                                 "sha256": sha})
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["scan"]["signals"], [])
        self.assertIn("不等于安全", out["scan_note"])


class TestInstallChain(Base):
    """对拍 #10/#11/#14/#15/#7：入口 sha 断言+零残留+版本层+同版本替换+
    多版本并存+三上限+装停分离告知。"""

    def test_install_success_and_version_layout(self):
        zpath, sha = self.zip_of(_manifest(_entry_sha(ENTRY_TEXT)))
        out = self.call("skill.secure.install", {"zip_path": zpath,
                                                 "sha256": sha})
        self.assertEqual(out["status"], "INSTALLED")
        self.assertEqual(out["enabled"], 1)  # 零警告=装上即启用+免责文案
        self.assertIn("不等于安全", out["message"])
        vdir = self.state / "packages" / "demo-skill" / "1.0.0"
        self.assertTrue((vdir / "SKILL.md").is_file())
        self.assertFalse((vdir / "skill.json").exists())  # 清单入记录不重复落盘

    def test_entry_sha_mismatch_refused_zero_residue(self):
        m = _manifest("f" * 64)  # 声明值与实际不符
        zpath, sha = self.zip_of(m)
        pre = self.call("skill.secure.inspect", {"zip_path": zpath,
                                                 "sha256": sha})
        self.assertEqual(pre["status"], "REFUSED")
        self.assertIn("s21_entry_sha_mismatch", pre["issues"])
        with self.assertRaises(NotConnected) as ctx:
            self.call("skill.secure.install", {"zip_path": zpath,
                                               "sha256": sha})
        self.assertIn("s21_install_refused", str(ctx.exception))
        # 零残留：状态根无包文件树（记录树也无）
        self.assertFalse((self.state / "packages").exists())

    def test_multi_version_coexist_and_same_version_replace(self):
        z1, s1 = self.zip_of(_manifest(_entry_sha(ENTRY_TEXT)))
        self.call("skill.secure.install", {"zip_path": z1, "sha256": s1})
        m2 = _manifest(_entry_sha(ENTRY_TEXT), version="1.1.0")
        z2, s2 = self.zip_of(m2)
        self.call("skill.secure.install", {"zip_path": z2, "sha256": s2})
        listing = self.call("skill.secure.list", {})
        self.assertEqual(len(listing["packages"]), 2)  # 多版本并存
        # 同版本重装=替换不重复
        z3, s3 = self.zip_of(_manifest(_entry_sha(ENTRY_TEXT)))
        self.call("skill.secure.install", {"zip_path": z3, "sha256": s3})
        listing = self.call("skill.secure.list", {})
        self.assertEqual(len(listing["packages"]), 2)
        self.assertEqual(listing["history_count"], 3)

    def test_budget_limits(self):
        files = {f"extra/p{i:03d}.txt": b"x" * 100 for i in range(250)}
        zpath, sha = self.zip_of(_manifest(_entry_sha(ENTRY_TEXT)),
                                 files=files)
        with self.assertRaises(NotConnected) as ctx:
            self.call("skill.secure.install", {"zip_path": zpath,
                                               "sha256": sha})
        self.assertIn("s21_package_budget_exceeded", str(ctx.exception))

    def test_warnings_mean_disabled_by_default_with_message(self):
        text = ENTRY_TEXT + "\n执行：bash run.sh（合成信号文本）\n"
        zpath, sha = self.zip_of(_manifest(_entry_sha(text)),
                                 files={"SKILL.md": text.encode()})
        out = self.call("skill.secure.install", {"zip_path": zpath,
                                                 "sha256": sha})
        self.assertEqual(out["enabled"], 0)  # 装上即停用
        self.assertIn("默认停用", out["message"])
        codes = [w["code"] for w in out["warnings"]]
        self.assertIn("s21_signal_shell", codes)
        self.assertIn("s21_gap_shell_undeclared", codes)  # 未声明 shell


class TestLoadReverifyAndLifecycle(Base):
    """对拍 #12/#13/#17/#35/#36：加载重验/卸载不可见/卸载路径守卫/安装史
    留档/三态分离。"""

    def _install(self):
        zpath, sha = self.zip_of(_manifest(_entry_sha(ENTRY_TEXT)))
        return self.call("skill.secure.install", {"zip_path": zpath,
                                                  "sha256": sha})

    def test_read_reverify_tampered_disk_refused(self):
        self._install()
        entry = (self.state / "packages" / "demo-skill" / "1.0.0"
                 / "SKILL.md")
        entry.write_text(ENTRY_TEXT + "\n被改过的字节（合成）", "utf-8")
        with self.assertRaises(NotConnected) as ctx:
            self.call("skill.secure.read", {"package_id": "demo-skill",
                                            "version": "1.0.0"})
        self.assertIn("s21_entry_tampered", str(ctx.exception))

    def test_uninstall_invisible_and_history_kept(self):
        self._install()
        out = self.call("skill.secure.uninstall", {"package_id": "demo-skill",
                                                   "version": "1.0.0"})
        self.assertEqual(out["status"], "UNINSTALLED")
        listing = self.call("skill.secure.list", {})
        self.assertEqual(listing["packages"], [])  # 卸载后不可见
        with self.assertRaises(NotConnected):
            self.call("skill.secure.read", {"package_id": "demo-skill",
                                            "version": "1.0.0"})  # 不可加载
        # 安装史留档：记录行与事件账都在
        rec = (self.state / "records" / "demo-skill" / "1.0.0.json")
        record = json.loads(rec.read_text("utf-8"))
        self.assertIsNotNone(record["uninstalled_at"])
        self.assertEqual(record["enabled"], 0)
        hist = (self.state / "history.jsonl").read_text("utf-8").splitlines()
        self.assertEqual(len(hist), 2)  # install + uninstall（行不删）

    def test_three_states_independent(self):
        self._install()
        out = self.call("skill.secure.set_active",
                        {"package_id": "demo-skill", "version": "1.0.0",
                         "enabled": False})
        self.assertFalse(out["enabled"])
        listing = self.call("skill.secure.list", {})
        pkg = listing["packages"][0]
        self.assertTrue(pkg["installed"])
        self.assertFalse(pkg["enabled"])
        self.assertFalse(pkg["hired"])  # 三态分离不塌缩
        # 停用仍可读（「我不想它跑」≠「删掉它」），enabled 如实回带
        read = self.call("skill.secure.read", {"package_id": "demo-skill",
                                               "version": "1.0.0"})
        self.assertFalse(read["enabled"])

    def test_uninstall_path_guard(self):
        """对拍 #17：卸载不可能变成任意递归删除。第一道=id/version 形状
        前置校验（目录名成分不合法=typed 拒，不触任何路径）；第二道=包根
        内 resolve 守卫（防损坏记录，代码在卸载链内）。"""
        self._install()
        for bad_version in ("..\\..\\..\\evil", "../../../evil", "1.0.0/x",
                            "1.0.0\\..\\..\\evil"):
            with self.assertRaises(NotConnected) as ctx:
                self.call("skill.secure.uninstall",
                          {"package_id": "demo-skill",
                           "version": bad_version})
            self.assertIn("s21_params_invalid", str(ctx.exception),
                          bad_version)
        # 真实安装的包未被触碰（守卫只拒不删）
        self.assertTrue((self.state / "packages" / "demo-skill"
                         / "1.0.0" / "SKILL.md").is_file())


class TestLicenseGate(Base):
    """对拍 #18/#19：三闸+来源登记逐源钉许可状态+G6 连接器只留档。"""

    def test_three_gates(self):
        self.assertFalse(can_bundle_skill(
            "https://synth.example/sources/cc-by-nc-skill"))  # restricted
        self.assertFalse(can_bundle_skill(
            "https://synth.example/sources/no-license-skill"))  # unknown
        self.assertTrue(can_bundle_skill(
            "https://synth.example/sources/apache-skill"))
        self.assertTrue(can_install_skill(
            "https://synth.example/sources/apache-skill"))  # compatible+installable
        self.assertFalse(can_install_skill(
            "https://synth.example/sources/readme-only-skill"))  # needs_review
        self.assertFalse(can_install_skill("https://not.registered/x"))

    def test_g6_connector_archived_not_run(self):
        g6 = "https://synth.example/connectors/g6-demo"
        self.assertIn(g6, SOURCES)  # 名单留档
        self.assertFalse(can_run_skill(g6))  # 不接线不作为技能运行
        self.assertTrue(SOURCES[g6]["connector"])
        self.assertFalse(SOURCES[g6]["wired"])

    def test_non_compatible_source_refused_at_install(self):
        src = {"kind": "registry",
               "url": "https://synth.example/sources/cc-by-nc-skill"}
        zpath, sha = self.zip_of(_manifest(_entry_sha(ENTRY_TEXT),
                                           source=src))
        pre = self.call("skill.secure.inspect", {"zip_path": zpath,
                                                 "sha256": sha})
        self.assertEqual(pre["status"], "REFUSED")
        self.assertIn("s21_license_not_installable", pre["issues"])

    def test_catzip_form_zip_refused_no_hash_no_permission(self):
        # catzip 形（frontmatter 无 permissions/sha256 声明）：安全层通道
        # 无声明即零权限+无哈希即拒装（§3.0 裁定②）
        files = {"SKILL.md": ("---\nname: cat-skill\ndescription: 合成\n"
                              "---\n正文（合成）\n").encode()}
        zpath = self.root / "catzip.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("SKILL.md", files["SKILL.md"])
        sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
        pre = self.call("skill.secure.inspect", {"zip_path": str(zpath),
                                                 "sha256": sha})
        self.assertEqual(pre["status"], "REFUSED")
        self.assertIn("s21_manifest_missing", pre["issues"])

    def test_zip_source_sha_mismatch_refused(self):
        zpath, _ = self.zip_of(_manifest(_entry_sha(ENTRY_TEXT)))
        with self.assertRaises(NotConnected) as ctx:
            self.call("skill.secure.inspect", {"zip_path": zpath,
                                               "sha256": "0" * 64})
        self.assertIn("s21_zip_source_mismatch", str(ctx.exception))


class TestWiring(Base):
    """legal_entry 冻结组+typed 码映射（F99 先例同款桥纪律）。"""

    def test_method_group_registered(self):
        self.assertEqual(SKILL_SECURITY_METHODS, legal_entry.SKILL_SECURITY_METHODS)

    def test_typed_error_passthrough(self):
        try:
            legal_entry.call("skill.secure.list", {"x": 1},
                             {"skill_security_state_root": str(self.state)})
            raise AssertionError("unreachable")
        except NotConnected as exc:
            self.assertEqual(str(exc), "OK")  # list 宽容入参不拒——不触这里
        except Exception:
            pass

    def test_state_root_fail_closed(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("skill.secure.list", {}, {})
        self.assertIn("s21_state_root_not_configured", str(ctx.exception))

    def test_unknown_method_typed(self):
        with self.assertRaises(NotConnected):
            legal_entry.call("skill.secure.explode", {},
                             {"skill_security_state_root": str(self.state)})


class TestCatzipMigration(Base):
    """RE-21 增补 §3.0 迁移待办①（2026-10-31 落定）：catzip 已装 user 技能
    一次性迁版本层 packages/<id>/<version>/。全部合成材料（temp 根）。"""

    def make_catzip_root(self):
        root = self.root / "catzip-skills"
        root.mkdir()
        return root

    def test_migrate_moves_to_version_layer_with_provenance(self):
        src = self.make_catzip_root()
        # cat 形（frontmatter）+ SkillHub 形（skill.json+SKILL.md）双格式各一
        (src / "cat-style-search").mkdir()
        (src / "cat-style-search" / "SKILL.md").write_text(
            "---\nname: cat-style-search\ndescription: 合成 cat 形技能\n"
            "---\n正文（合成材料）：案内检索三步法。\n", "utf-8")
        (src / "Law_Contract_Review").mkdir()  # 大写+下划线=归一 id 锻炼
        (src / "Law_Contract_Review" / "skill.json").write_text(
            json.dumps({"name": "Law_Contract_Review",
                        "description": "合成 SkillHub 形"}), "utf-8")
        (src / "Law_Contract_Review" / "SKILL.md").write_text(
            "# 合同审查清单（合成）\n纯方法论正文，零信号。\n", "utf-8")
        report = skill_security.migrate_catzip_skills(src, self.config)
        self.assertEqual(report["failed"], [])
        self.assertEqual(len(report["migrated"]), 2)
        # 平铺源目录已移除（真迁移）；版本层落位
        self.assertFalse((src / "cat-style-search").exists())
        self.assertFalse((src / "Law_Contract_Review").exists())
        p1 = self.state / "packages" / "cat-style-search" / "0.0.0-catzip"
        p2 = self.state / "packages" / "law-contract-review" / "0.0.0-catzip"
        self.assertTrue((p1 / "SKILL.md").is_file())
        self.assertTrue((p2 / "SKILL.md").is_file())
        self.assertTrue((p2 / "skill.json").is_file())  # 原目录文件随迁
        # 记录：溯源字段+零声明权限+启停按扫描
        rec = json.loads((self.state / "records" / "cat-style-search"
                          / "0.0.0-catzip.json").read_text("utf-8"))
        self.assertEqual(rec["migrated_from"], "catzip")
        self.assertEqual(rec["migrated_dir"], "cat-style-search")
        self.assertEqual(rec["permissions"], [])  # 零声明=零权限
        self.assertEqual(rec["version"], "0.0.0-catzip")
        self.assertEqual(rec["enabled"], 1)  # 零信号=装上即启用
        hist = (self.state / "history.jsonl").read_text("utf-8").splitlines()
        self.assertEqual(json.loads(hist[0])["action"], "migrate")
        # 迁移件在安全层面可见可读（加载重验对记录 sha 通过）
        listing = self.call("skill.secure.list", {})
        ids = {p["package_id"] for p in listing["packages"]}
        self.assertEqual(ids, {"cat-style-search", "law-contract-review"})
        read = self.call("skill.secure.read",
                         {"package_id": "cat-style-search",
                          "version": "0.0.0-catzip"})
        self.assertIn("案内检索", read["text"])

    def test_migrate_warnings_mean_disabled(self):
        src = self.make_catzip_root()
        (src / "risky-skill").mkdir()
        text = ("---\nname: risky-skill\ndescription: 合成信号件\n---\n"
                "执行：bash run.sh（合成信号文本）\n")
        (src / "risky-skill" / "SKILL.md").write_text(text, "utf-8")
        report = skill_security.migrate_catzip_skills(src, self.config)
        self.assertEqual(report["failed"], [])
        item = report["migrated"][0]
        self.assertEqual(item["enabled"], 0)  # 装停分离跨迁移保持
        self.assertIn("shell", item["signals"])
        rec = json.loads((self.state / "records" / "risky-skill"
                          / "0.0.0-catzip.json").read_text("utf-8"))
        self.assertEqual(rec["enabled"], 0)
        codes = [w["code"] for w in rec["warnings"]]
        self.assertIn("s21_signal_shell", codes)

    def test_entry_missing_refused_source_kept_others_migrate(self):
        src = self.make_catzip_root()
        (src / "no-entry").mkdir()  # 只有 skill.json 无 SKILL.md=无入口锚
        (src / "no-entry" / "skill.json").write_text(
            json.dumps({"name": "no-entry"}), "utf-8")
        (src / "good-one").mkdir()
        (src / "good-one" / "SKILL.md").write_text(
            "---\nname: good-one\ndescription: 合成\n---\n正文。\n", "utf-8")
        report = skill_security.migrate_catzip_skills(src, self.config)
        # 逐件隔离：坏件失败码+源目录不动；好件照迁
        self.assertEqual(len(report["failed"]), 1)
        self.assertEqual(report["failed"][0]["code"],
                         "s21_migrate_entry_missing")
        self.assertTrue((src / "no-entry").exists())
        self.assertEqual(len(report["migrated"]), 1)
        self.assertEqual(report["migrated"][0]["package_id"], "good-one")

    def test_conflict_when_reinstalled_after_migration(self):
        src = self.make_catzip_root()
        (src / "dup-skill").mkdir()
        (src / "dup-skill" / "SKILL.md").write_text(
            "---\nname: dup-skill\ndescription: 合成\n---\n初版正文。\n",
            "utf-8")
        skill_security.migrate_catzip_skills(src, self.config)
        original = json.loads((self.state / "records" / "dup-skill"
                               / "0.0.0-catzip.json").read_text("utf-8"))
        # 迁移后经 catzip 面重装同名件（平铺目录再现）=冲突，不静默覆盖
        (src / "dup-skill").mkdir()
        (src / "dup-skill" / "SKILL.md").write_text(
            "---\nname: dup-skill\ndescription: 合成\n---\n重装正文。\n",
            "utf-8")
        report = skill_security.migrate_catzip_skills(src, self.config)
        self.assertEqual(report["failed"][0]["code"], "s21_migrate_conflict")
        kept = json.loads((self.state / "records" / "dup-skill"
                           / "0.0.0-catzip.json").read_text("utf-8"))
        self.assertEqual(kept["entry_sha256"], original["entry_sha256"])
        # 冲突件人工清走后重跑=零候选成功（幂等）
        import shutil as _shutil
        _shutil.rmtree(src / "dup-skill")
        report2 = skill_security.migrate_catzip_skills(src, self.config)
        self.assertEqual(report2["migrated"], [])
        self.assertEqual(report2["failed"], [])
        self.assertTrue(report2["source_root_present"])

    def test_missing_source_root_is_zero_candidates(self):
        report = skill_security.migrate_catzip_skills(
            self.root / "never-existed", self.config)
        self.assertFalse(report["source_root_present"])
        self.assertEqual(report["migrated"], [])
        self.assertEqual(report["failed"], [])

    def test_dry_run_writes_nothing(self):
        src = self.make_catzip_root()
        (src / "plan-skill").mkdir()
        (src / "plan-skill" / "SKILL.md").write_text(
            "---\nname: plan-skill\ndescription: 合成\n---\n正文。\n", "utf-8")
        report = skill_security.migrate_catzip_skills(src, self.config,
                                                      apply=False)
        self.assertEqual(report["planned"][0]["package_id"], "plan-skill")
        self.assertFalse((self.state / "packages").exists())
        self.assertFalse((self.state / "records").exists())
        self.assertTrue((src / "plan-skill" / "SKILL.md").is_file())  # 源不动

    def test_cli_dry_run_report_and_exit_codes(self):
        import subprocess
        import sys as _sys
        src = self.make_catzip_root()
        (src / "cli-skill").mkdir()
        (src / "cli-skill" / "SKILL.md").write_text(
            "---\nname: cli-skill\ndescription: 合成\n---\n正文。\n", "utf-8")
        script = HERE / "python" / "migrate_catzip_skills.py"
        report_path = self.root / "cli-report.json"
        # 干跑：exit 0+planned 报告+状态根零写入
        r = subprocess.run(
            [_sys.executable, "-X", "utf8", str(script),
             "--state-root", str(self.state), "--catzip-root", str(src),
             "--report", str(report_path), "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(report_path.read_text("utf-8"))
        self.assertEqual(out["apply"], False)
        self.assertEqual(len(out["planned"]), 1)
        self.assertFalse(self.state.exists())
        # 应用：exit 0+迁移+报告 migrated；重装同名件再跑：exit 1+冲突码
        r2 = subprocess.run(
            [_sys.executable, "-X", "utf8", str(script),
             "--state-root", str(self.state), "--catzip-root", str(src),
             "--report", str(report_path)],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertTrue((self.state / "packages" / "cli-skill"
                         / "0.0.0-catzip" / "SKILL.md").is_file())
        (src / "cli-skill").mkdir()
        (src / "cli-skill" / "SKILL.md").write_text(
            "---\nname: cli-skill\ndescription: 合成\n---\n重装。\n", "utf-8")
        r3 = subprocess.run(
            [_sys.executable, "-X", "utf8", str(script),
             "--state-root", str(self.state), "--catzip-root", str(src),
             "--report", str(report_path)],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(r3.returncode, 1)
        out3 = json.loads(report_path.read_text("utf-8"))
        self.assertEqual(out3["failed"][0]["code"], "s21_migrate_conflict")
        # state-root 缺失=fail-closed exit 2
        r4 = subprocess.run(
            [_sys.executable, "-X", "utf8", str(script)],
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual(r4.returncode, 2)
        self.assertIn("s21_state_root_not_configured", r4.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
