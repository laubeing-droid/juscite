"""W3-U17 / F94+F95 wiring: 技能目录分发链与 cat-xierluo zip 直装
（skill.catalog.* / skill.zip.* 桥方法组 → skill_catalog 产品面）。

义务 06:F94（F94-desktop/F94-selfhost）「pin commit/hash 的社区技能目录可
离线安装和回滚；商用内容不混广场」；06:F95（F95-desktop/F95-selfhost）
「zip 预检路径/权限/来源，格式兼容真安装运行；不信任任意脚本」。受控内容
按 §6.1 裁决#7 合成样本先行——全部材料纯合成，零网络，零真实
manuals/persona 内容。

- 单测面：frontmatter 上游契约镜像、manifest 推导、zip 预检负向（zip-slip/
  绝对路径/驱动器/反斜杠[raw 名字节级构造]/控制字符/保留设备名/符号链接/
  setuid/重复条目/零技能/来源缺失与不匹配）、渠道不混广场三路拒、回滚链
  （A→B→回滚→再回滚拒）、pack 确定性＋bundle 跨状态根摘要相等、运行投影
  ＝上游 toModelOutput 同形、桥 fail-closed、面 AST 纪律（zip 路径零
  subprocess/exec/eval；git 子进程仅钉定解析）。
"""
import ast
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected, SKILL_CATALOG_METHODS, \
    SKILL_ZIP_METHODS  # noqa: E402
import skill_catalog as sc  # noqa: E402

BS = chr(92)  # heredoc 安全的反斜杠（测试源里不写字面 \）


# --------------------------------------------------------------------------
# 合成材料构造（全合成，零网络）
# --------------------------------------------------------------------------

def zip_raw(entries):
    """entries: [(name, data, external_attr|None)]——直接赋 zi.filename 绕开
    zipfile 写入期的 os.sep 归一化，构造带原始分隔符/属性的负向 zip。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data, *attrs in entries:
            zi = zipfile.ZipInfo("placeholder", date_time=(2026, 1, 1, 0, 0, 0))
            zi.filename = name
            if attrs and attrs[0] is not None:
                zi.external_attr = attrs[0]
            zf.writestr(zi, data)
    return buf.getvalue()


def patch_entry_name(data: bytes, old: str, new: str) -> bytes:
    """等长字节补丁（zipfile 拒写反斜杠名；对已建 zip 的 local header＋中
    央目录做同长替换，构造真反斜杠条目名）。"""
    assert len(old) == len(new)
    return data.replace(old.encode(), new.encode())


def build_git_repo(root: Path, catalog: dict, skill_files: dict,
                   message: str = "init") -> str:
    """确定性合成 git 仓（固定 author/date → commit sha 跨进程/跨 profile
    可复现）；返回 HEAD commit 全 sha。"""
    root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ,
               GIT_AUTHOR_DATE="2026-10-18T00:00:00+00:00",
               GIT_COMMITTER_DATE="2026-10-18T00:00:00+00:00")
    def git(*args):
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, env=env)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout
    git("init", "-q")
    git("config", "core.autocrlf", "false")   # archive/add 全程 LF（D2 教训）
    (root / "catalog.json").write_bytes(
        json.dumps(catalog, ensure_ascii=False).encode("utf-8"))
    for rel, data in skill_files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    git("-c", "core.autocrlf=false", "add", "-A")
    git("-c", "user.name=F94-Acceptance",
        "-c", "user.email=f94@juscite.local", "commit", "-q", "-m", message)
    return git("rev-parse", "HEAD").decode().strip()


PUBLIC_CATALOG = {"catalog_id": "community-skills", "channel": "public"}
CONTROLLED_CATALOG = {"catalog_id": "manuals-sample", "channel": "controlled"}

SKILL_V1 = {
    "legal-review/SKILL.md": (
        "---\nname: legal-review\ndescription: 合同审查技能（合成）\n---\n"
        "第一步 读全文。\n").encode("utf-8"),
    "legal-review/reference/checklist.md": "清单一。\n".encode("utf-8"),
    "legal-review/scripts/scan.py": b"print('inert-data')\n",
    "notes.md": "# 根级单文件技能（合成）\n".encode("utf-8"),
}
SKILL_V2 = dict(SKILL_V1)
SKILL_V2["legal-review/SKILL.md"] = (
    "---\nname: legal-review\ndescription: 合同审查技能 v2（合成）\n---\n"
    "第一步 读全文。第二步 复核。\n").encode("utf-8")

CAT_XIERLUO_ZIP = [
    ("legal-skills-main/legal-citation/SKILL.md",
     "---\nname: legal-citation\ndescription: 引文核验技能（cat-xierluo "
     "格式合成发布件）\n---\n引文先核后引。\n", None),
    ("legal-skills-main/legal-citation/scripts/fmt.py",
     b"print('never-executed')\n", None),
]


class F94F95Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def cfg(self, name="state"):
        return {"skill_catalog_state_root": str(self.tmp / name)}


class FrontmatterTests(F94F95Fixture):
    def test_valid_absent_plain(self):
        got = sc.parse_skill_markdown("---\nname: a\ndescription: b\n---\nX")
        self.assertEqual((got["name"], got["description"]), ("a", "b"))
        got = sc.parse_skill_markdown("plain body")
        self.assertIsNone(got["name"])
        self.assertEqual(got["content"], "plain body")

    def test_upstream_skip_cases(self):
        # YAML 不可解 / name 非标量 / name 空值 → 上游 Skipped → 本面 None
        self.assertIsNone(sc.parse_skill_markdown(
            "---\nname: [broken\n---\nx"))
        self.assertIsNone(sc.parse_skill_markdown(
            "---\nname:\n  - a\n  - b\n---\nx"))
        self.assertIsNone(sc.parse_skill_markdown("---\nname:\n---\nx"))
        self.assertIsNone(sc.parse_skill_markdown(
            "---\n- list item\n---\nx"))

    def test_quoted_and_colon_values(self):
        got = sc.parse_skill_markdown(
            "---\nname: 'quoted: name'\ndescription: \"dq\"\n---\nC")
        self.assertEqual(got["name"], "quoted: name")
        self.assertEqual(got["description"], "dq")

    def test_no_closing_delimiter(self):
        # gray-matter：无闭合定界符→无 frontmatter 提取→可加载
        got = sc.parse_skill_markdown("---\nname: a\nno close")
        self.assertIsNone(got["name"])


class DeriveTests(F94F95Fixture):
    def test_manifest_and_mount(self):
        out = sc.derive_manifest_from_files(
            dict(SKILL_V1), catalog_id="community-skills", channel="public",
            kind="git_local", commit="a" * 40)
        man = out["manifest"]
        self.assertEqual([s["id"] for s in man["skills"]],
                         ["legal-review", "notes"])
        mounts = {f["path"] for f in man["files"]}
        self.assertEqual(mounts, {
            "legal-review/SKILL.md", "legal-review/reference/checklist.md",
            "legal-review/scripts/scan.py", "notes.md"})
        self.assertEqual(out["mount"]["notes.md"], "notes.md")
        self.assertEqual(out["mount"]["legal-review/SKILL.md"],
                         "legal-review/SKILL.md")
        self.assertEqual(man["skills"][0]["name"], "legal-review")
        self.assertEqual(man["skills"][0]["file_count"], 3)
        self.assertEqual(man["skills"][1]["file_count"], 1)

    def test_ambiguous_and_invalid_and_empty(self):
        files = {"a/x/SKILL.md": b"---\nname: x\n---\n1",
                 "b/x/SKILL.md": b"---\nname: x\n---\n2"}
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.derive_manifest_from_files(files, catalog_id="c",
                                          channel="public", kind="zip")
        self.assertEqual(str(cm.exception), "f94_skill_id_ambiguous")
        bad = {"s/SKILL.md": b"---\nname: [broken\n---\nx"}
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.derive_manifest_from_files(bad, catalog_id="c",
                                          channel="public", kind="zip")
        self.assertEqual(str(cm.exception), "f94_skill_frontmatter_invalid")
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.derive_manifest_from_files({"only.txt": b"x"}, catalog_id="c",
                                          channel="public", kind="zip")
        self.assertEqual(str(cm.exception), "f94_catalog_empty")


class ZipPrecheckTests(F94F95Fixture):
    def install_refusal(self, zdata, frag, *, sha=None, channel=None,
                        method="skill.zip.install", extra=None):
        path = self.tmp / (frag + ".zip")
        path.write_bytes(zdata)
        args = {"zip_path": str(path),
                "sha256": sha or hashlib.sha256(zdata).hexdigest(),
                "url": "https://example.invalid/synth.zip"}
        if channel:
            args = {"channel": channel,
                    "source": {"kind": "zip", "path": str(path),
                               "sha256": args["sha256"], "url": args["url"]}}
            method = "skill.catalog.install"
        if extra:
            args.update(extra)
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.catalog_call(method, args, self.cfg())
        self.assertEqual(str(cm.exception), frag)

    def test_path_negatives(self):
        good = "---\nname: ok\n---\nx".encode("utf-8")
        cases = [
            ("../evil.txt", b"x"),
            ("..\\evil.txt", b"x"),   # 读取端归一化后仍带 .. 段
            ("/abs/evil.txt", b"x"),
            ("C:/evil.txt", b"x"),
            ("C:absolute.txt", b"x"),
            ("co" + chr(8) + "n.txt", b"x"),
            ("CON/SKILL.md", good),
            ("NUL.txt", b"x"),
            ("a/" * 20 + "deep.txt", b"x"),
        ]
        for name, data in cases:
            zdata = zip_raw([(name, data)])
            self.install_refusal(zdata, "f95_zip_path_unsafe")

    def test_entry_type_and_perm_negatives(self):
        self.install_refusal(
            zip_raw([("link.txt", b"target", 0o120777 << 16)]),
            "f95_zip_entry_not_regular")
        self.install_refusal(
            zip_raw([("ok/SKILL.md", "---\nname: ok\n---\nx",
                      0o104755 << 16)]),
            "f95_zip_permission_bits")
        self.install_refusal(
            zip_raw([("d/", b"", 0o120777 << 16)]),
            "f95_zip_entry_not_regular")
        # 目录条目带常规权限位＝Unix 工具常态，必须放行
        znorm = zip_raw([("d/", b"", 0o040755 << 16),
                         ("d/SKILL.md", "---\nname: d\n---\nx", None)])
        path = self.tmp / "norm.zip"
        path.write_bytes(znorm)
        out = sc.catalog_call(
            "skill.zip.install",
            {"zip_path": str(path),
             "sha256": hashlib.sha256(znorm).hexdigest(),
             "url": "https://example.invalid/n.zip"}, self.cfg())
        self.assertEqual([s["id"] for s in out["skills"]], ["d"])

    def test_boundary_function_backslash_and_controlchars(self):
        # 注：zipfile 读取端会把条目名中的 \ 归一化为 /，故经 zip 全链无法
        # 观察反斜杠；边界函数直测（危险语义 ..／绝对／驱动器在归一化后
        # 仍全数被路径检查捕获，另有全链负向覆盖）。
        self.assertIsNone(sc._safe_rel_path("a" + BS + "b.txt"))
        self.assertIsNone(sc._safe_rel_path(".." + BS + "x"))
        self.assertIsNone(sc._safe_rel_path("co" + chr(8) + "n.txt"))
        self.assertIsNone(sc._safe_rel_path("C:x"))
        self.assertIsNone(sc._safe_rel_path("http://evil/x"))
        self.assertEqual(sc._safe_rel_path("a/b/c.md"), "a/b/c.md")

    def test_duplicate_and_budget(self):
        zdup = zip_raw([("a.txt", b"x"), ("a.txt", b"y"),
                        ("ok/SKILL.md", "---\nname: ok\n---\nx")])
        self.install_refusal(zdup, "f95_zip_entry_duplicate")
        self.install_refusal(
            zip_raw([("a", b"x"), ("a/b.txt", b"y"),
                     ("ok/SKILL.md", "---\nname: ok\n---\nx")]),
            "f95_zip_entry_duplicate")
        # zip 炸弹（高压缩比大文件；ZipInfo 需显式 DEFLATED——默认 STORED）
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zi = zipfile.ZipInfo("bomb.bin")
            zi.filename = "bomb.bin"
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, b"\0" * (2 * 1024 * 1024))
            zi = zipfile.ZipInfo("s")
            zi.filename = "ok/SKILL.md"
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, "---\nname: ok\n---\nx")
        self.install_refusal(buf.getvalue(), "f95_zip_budget_exceeded")

    def test_source_and_format_negatives(self):
        zok = zip_raw([("ok/SKILL.md", "---\nname: ok\n---\nx")])
        self.install_refusal(zok, "f95_zip_source_mismatch", sha="0" * 64)
        path = self.tmp / "ok.zip"
        path.write_bytes(zok)
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.catalog_call("skill.zip.install",
                            {"zip_path": str(path),
                             "sha256": hashlib.sha256(zok).hexdigest()},
                            self.cfg())
        self.assertEqual(str(cm.exception), "f95_zip_source_required")
        self.install_refusal(zip_raw([("only.txt", b"x")]),
                             "f95_zip_format_incompatible")
        # 渠道：zip 源只准 public
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.catalog_call(
                "skill.catalog.install",
                {"channel": "controlled",
                 "source": {"kind": "zip", "path": str(path),
                            "sha256": hashlib.sha256(zok).hexdigest(),
                            "url": "u"}},
                self.cfg())
        self.assertEqual(str(cm.exception), "f95_zip_channel_public_only")

    def test_inspect_lists_scripts_inert(self):
        zdata = zip_raw(CAT_XIERLUO_ZIP)
        path = self.tmp / "legal-skills.zip"
        path.write_bytes(zdata)
        out = sc.catalog_call(
            "skill.zip.inspect",
            {"zip_path": str(path),
             "sha256": hashlib.sha256(zdata).hexdigest()}, self.cfg())
        self.assertEqual(out["status"], "OK")
        self.assertEqual([s["id"] for s in out["skills"]], ["legal-citation"])
        self.assertEqual(out["scripts"],
                         ["legal-skills-main/legal-citation/scripts/fmt.py"])
        self.assertEqual(out["executed"], [])
        self.assertEqual(out["violations"], [])


class InstallRollbackTests(F94F95Fixture):
    def make_repo(self, name, catalog, files):
        repo = self.tmp / name
        commit = build_git_repo(repo, catalog, files)
        return repo, commit

    def test_pinned_install_read_verify_rollback(self):
        repo, commit = self.make_repo("pub-repo", PUBLIC_CATALOG, SKILL_V1)
        cfg = self.cfg()
        src = {"kind": "git_local", "repo": str(repo), "commit": commit}
        out = sc.catalog_call("skill.catalog.install",
                              {"channel": "public", "source": src}, cfg)
        self.assertEqual(out["status"], "INSTALLED")
        self.assertEqual(out["commit"], commit)
        self.assertEqual(out["file_count"], 4)
        digest1 = out["manifest_sha256"]
        # manifest 摘要可独立复算（canonical JSON sha256）
        man_bytes = (self.tmp / "state" / "skill-catalog" / "public" / "store"
                     / digest1 / "manifest.json").read_bytes()
        self.assertEqual(hashlib.sha256(man_bytes).hexdigest(), digest1)
        # expected_manifest_sha256 钉定：不符即拒
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.catalog_call("skill.catalog.install",
                            {"channel": "public", "source": src,
                             "expected_manifest_sha256": "0" * 64}, cfg)
        self.assertEqual(str(cm.exception), "f94_manifest_mismatch")
        # read：技能清单＋运行投影＝上游 toModelOutput 同形
        got = sc.catalog_call("skill.catalog.read",
                              {"channel": "public",
                               "skill_id": "legal-review"}, cfg)
        self.assertEqual(got["skill"]["name"], "legal-review")
        base = str((self.tmp / "state" / "skill-catalog" / "public"
                    / "skills" / "legal-review").resolve())
        files_abs = sorted(
            str((self.tmp / "state" / "skill-catalog" / "public" / "skills"
                 / "legal-review" / rel).resolve())
            for rel in ("reference/checklist.md", "scripts/scan.py"))
        expected = "\n".join([
            '<skill_content name="legal-review">',
            "# Skill: legal-review",
            "",
            "第一步 读全文。",
            "",
            f"Base directory for this skill: {base}",
            "Relative paths in this skill (e.g., scripts/, reference/) are relative to this base directory.",
            "Note: file list is sampled.",
            "",
            "<skill_files>",
            *(f"<file>{p}</file>" for p in files_abs),
            "</skill_files>",
            "</skill_content>",
        ])
        self.assertEqual(got["projection"], expected)
        # verify OK → 安装面篡改 → TAMPERED
        self.assertEqual(sc.catalog_call("skill.catalog.verify",
                                         {"channel": "public"}, cfg)["status"],
                         "OK")
        victim = (self.tmp / "state" / "skill-catalog" / "public" / "skills"
                  / "notes.md")
        victim.write_bytes(b"# tampered\n")
        verdict = sc.catalog_call("skill.catalog.verify",
                                  {"channel": "public"}, cfg)
        self.assertEqual(verdict["status"], "TAMPERED")
        self.assertEqual(verdict["changed"], ["notes.md"])
        # v2 安装 → 回滚回 v1（逐字节）→ 再回滚拒
        commit2 = build_git_repo(repo, PUBLIC_CATALOG, SKILL_V2,
                                 message="v2")
        self.assertNotEqual(commit2, commit)
        out2 = sc.catalog_call(
            "skill.catalog.install",
            {"channel": "public",
             "source": {"kind": "git_local", "repo": str(repo),
                        "commit": commit2}}, cfg)
        self.assertNotEqual(out2["manifest_sha256"], digest1)
        rb = sc.catalog_call("skill.catalog.rollback",
                             {"channel": "public"}, cfg)
        self.assertEqual(rb["restored_install_id"], out["install_id"])
        self.assertEqual(rb["manifest_sha256"], digest1)
        back = (self.tmp / "state" / "skill-catalog" / "public" / "skills"
                / "legal-review" / "SKILL.md").read_bytes()
        self.assertEqual(back, SKILL_V1["legal-review/SKILL.md"])
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.catalog_call("skill.catalog.rollback",
                            {"channel": "public"}, cfg)
        self.assertEqual(str(cm.exception), "f94_rollback_no_previous")
        # 空渠道回滚/读
        for frag, method, args in [
            ("f94_active_missing", "skill.catalog.rollback",
             {"channel": "controlled"}),
            ("f94_active_missing", "skill.catalog.verify",
             {"channel": "controlled"}),
        ]:
            with self.assertRaises(sc.SkillCatalogError) as cm:
                sc.catalog_call(method, args, cfg)
            self.assertEqual(str(cm.exception), frag)

    def test_channel_separation(self):
        cfg = self.cfg()
        crepo, ccommit = self.make_repo("ctl-repo", CONTROLLED_CATALOG,
                                        {"playbook-sample/SKILL.md":
                                         "---\nname: playbook-sample\n"
                                         "description: 受控合成样本（裁决#7）\n"
                                         "---\n受控正文\n".encode("utf-8")})
        src = {"kind": "git_local", "repo": str(crepo), "commit": ccommit}
        ok = sc.catalog_call("skill.catalog.install",
                             {"channel": "controlled", "source": src}, cfg)
        self.assertEqual(ok["status"], "INSTALLED")
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.catalog_call("skill.catalog.install",
                            {"channel": "public", "source": src}, cfg)
        self.assertEqual(str(cm.exception), "f94_channel_mismatch")
        # 受控 pack → public bundle 槽仍拒
        packed = sc.catalog_call("skill.catalog.pack",
                                 {"channel": "controlled"}, cfg)
        bundle = (self.tmp / "state" / "skill-catalog" / "controlled"
                  / "bundles" / packed["file"])
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.catalog_call("skill.catalog.install",
                            {"channel": "public",
                             "source": {"kind": "bundle",
                                        "path": str(bundle),
                                        "sha256": packed["sha256"]}}, cfg)
        self.assertEqual(str(cm.exception), "f94_channel_mismatch")
        # 渠道根物理分离，面上无跨渠道方法
        pub = sc.catalog_call("skill.catalog.read",
                              {"channel": "public"}, cfg)
        con = sc.catalog_call("skill.catalog.read",
                              {"channel": "controlled"}, cfg)
        self.assertEqual(pub["active"], None)
        self.assertEqual(
            {s["id"] for s in con["skills"]}, {"playbook-sample"})

    def test_zip_install_and_bundle_offline_loop(self):
        cfg_a, cfg_b = self.cfg("state-a"), self.cfg("state-b")
        zdata = zip_raw(CAT_XIERLUO_ZIP)
        zpath = self.tmp / "legal-skills.zip"
        zpath.write_bytes(zdata)
        sha = hashlib.sha256(zdata).hexdigest()
        out = sc.catalog_call(
            "skill.zip.install",
            {"zip_path": str(zpath), "sha256": sha,
             "url": "https://example.invalid/legal-skills.zip"}, cfg_a)
        self.assertEqual([s["id"] for s in out["skills"]], ["legal-citation"])
        self.assertEqual(
            out["scripts"],
            ["legal-skills-main/legal-citation/scripts/fmt.py"])
        self.assertNotIn("executed", out)  # receipt 无执行面
        # pack 两次逐字节同产物（确定性）
        p1 = sc.catalog_call("skill.catalog.pack", {"channel": "public"},
                             cfg_a)
        p2 = sc.catalog_call("skill.catalog.pack", {"channel": "public"},
                             cfg_a)
        self.assertEqual(p1["sha256"], p2["sha256"])
        # bundle 离线装入另一状态根：摘要与 zip 直装相等
        bundle = (self.tmp / "state-a" / "skill-catalog" / "public"
                  / "bundles" / p1["file"])
        out_b = sc.catalog_call(
            "skill.catalog.install",
            {"channel": "public",
             "source": {"kind": "bundle", "path": str(bundle),
                        "sha256": p1["sha256"]}}, cfg_b)
        self.assertEqual(out_b["manifest_sha256"], out["manifest_sha256"])
        v_b = sc.catalog_call("skill.catalog.verify",
                              {"channel": "public"}, cfg_b)
        self.assertEqual(v_b["status"], "OK")
        # bundle 篡改一字节 → 来源拒
        tampered = bytearray(bundle.read_bytes())
        tampered[-1] ^= 0xFF
        bad = self.tmp / "bad.bundle.zip"
        bad.write_bytes(bytes(tampered))
        with self.assertRaises(sc.SkillCatalogError) as cm:
            sc.catalog_call("skill.catalog.install",
                            {"channel": "public",
                             "source": {"kind": "bundle", "path": str(bad),
                                        "sha256": p1["sha256"]}}, cfg_b)
        self.assertEqual(str(cm.exception), "f95_zip_source_mismatch")
        # store 内容寻址：同 pin 重装同一 store 目录（零重复树）
        stores = list((self.tmp / "state-a" / "skill-catalog" / "public"
                       / "store").iterdir())
        self.assertEqual(len(stores), 1)


class BridgeTests(F94F95Fixture):
    def test_frozen_groups(self):
        self.assertIsInstance(SKILL_CATALOG_METHODS, frozenset)
        self.assertIsInstance(SKILL_ZIP_METHODS, frozenset)
        self.assertEqual(
            SKILL_CATALOG_METHODS,
            {"skill.catalog.install", "skill.catalog.rollback",
             "skill.catalog.verify", "skill.catalog.read",
             "skill.catalog.pack"})
        self.assertEqual(SKILL_ZIP_METHODS,
                         {"skill.zip.install", "skill.zip.inspect"})

    def test_bridge_fail_closed(self):
        for method, args in [
            ("skill.catalog.read", {"channel": "public"}),
            ("skill.zip.install", {"zip_path": "x", "sha256": "0" * 64}),
        ]:
            with self.assertRaises(NotConnected) as cm:
                call(method, args, {})
            self.assertIn("f94_state_root_not_configured", str(cm.exception))
        zdata = zip_raw([("ok/SKILL.md", "---\nname: ok\n---\nx")])
        path = self.tmp / "ok.zip"
        path.write_bytes(zdata)
        with self.assertRaises(NotConnected) as cm:
            call("skill.zip.install",
                 {"zip_path": str(path), "sha256": "0" * 64,
                  "url": "u"}, self.cfg())
        self.assertIn("f95_zip_source_mismatch", str(cm.exception))
        with self.assertRaises(NotConnected) as cm:
            call("skill.catalog.destroy", {}, self.cfg())
        self.assertIn("method_not_connected", str(cm.exception))

    def test_face_ast_discipline(self):
        # zip 直装路径零执行面：模块无 eval/exec；subprocess 仅 git 钉定解析
        src = Path(sc.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and \
                        node.func.id in ("eval", "exec", "compile",
                                         "__import__"):
                    self.fail("forbidden dynamic execution call")
                if isinstance(node.func, ast.Attribute) and \
                        node.func.attr in ("system", "popen", "exec",
                                           "eval"):
                    self.fail("forbidden dynamic execution attribute")
            if isinstance(node, ast.keyword) and node.arg == "shell":
                self.fail("shell=True forbidden")
        git_calls = [n for n in ast.walk(tree)
                     if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name)
                     and n.func.id == "_git"]
        self.assertEqual(len(git_calls), 2)  # rev-parse＋archive，仅钉定解析
        self.assertIn('["git", "-C", str(repo), *args]', src)


if __name__ == "__main__":
    unittest.main()
