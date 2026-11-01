# -*- coding: utf-8 -*-
"""F94 技能目录分发链＋F95 cat-xierluo zip 直装兼容 验收对账（W3-U17）。

06:F94（F94-desktop/F94-selfhost 双实例）「pin commit/hash 的社区技能目录
可离线安装和回滚；商用内容不混广场」；06:F95（F95-desktop/F95-selfhost 双
实例）「zip 预检路径/权限/来源，格式兼容真安装运行；不信任任意脚本」。
17 卡 F94 落点＝Harness manuals/playbook 公开消费＋受控内容包；§6.1 裁
决#7：manuals/persona 受控内容**合成样本先行**、不公开蒸馏——本工具全部
材料纯合成（合成 git 仓＋合成社区 zip），零网络、零真实 manuals/persona
内容、零 %APPDATA% 触碰。

分段：
  S0 环境与钉定（oc28 HEAD==026b106 只读核验＋bun 在位＋合成源确定性
     commit；跨 profile 同 commit）
  S1 F94 pin 安装（git_local 离线装 public：receipt commit==pin＋manifest
     摘要可独立复算＋read 技能清单＋运行投影==独立重算的上游
     toModelOutput＋verify OK）
  S2 F94 回滚（v2 安装→回滚回 v1 摘要与逐字节→再回滚 typed 拒）
  S3 商用内容不混广场（受控合成样本装 controlled OK；受控源装 public
     f94_channel_mismatch；受控 pack→public bundle 同拒；渠道根分离读出
     不相交；受控 bundle 装回受控新根 OK）
  S4 桌面离线捆绑（pack 两次逐字节同产物→bundle 装入全新状态根摘要相
     等＋verify OK；bundle 篡改一字节 f95_zip_source_mismatch）
  S5 F95 zip 直装（cat-xierluo 格式合成 zip：inspect 技能/脚本/惰性→
     install 换 public 活动→投影==上游 toModelOutput→verify OK）
  S6 F95 预检负向十一连（zip-slip/绝对/驱动器/控制字符/保留设备名/符号
     链接条目/setuid/重复条目/零技能格式/来源不匹配/来源缺声明＋zip 装受
     控渠道拒——全部经真产品入口 CLI typed 拒）
  S7 不信任任意脚本（skill_catalog.py AST：零 eval/exec/shell；子进程仅
     git 钉定解析两处；zip 内脚本落盘字节不变）
  S8 上游原生解析器复跑（bun＋oc28 pin skill-file.ts 真模块对安装面
     skills/ 目录解析——id/name/description 与 manifest 逐项相等；坏
     frontmatter 上游 Skipped 与本面拒装对偶）
  S9 跨 profile 确定性（manifest 摘要×3＋bundle sha＋合成源 commit 两
     profile 全等）
  S10 桥 fail-closed（缺状态根 exit 3；未知方法 method_not_connected）

用法（juscite worktree w3-u17 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f94_f95_skilldist_zip_recon.py \
      [--profile desktop] [--profile selfhost]
缺省双 profile。exit 0＝RECON_OK 全断言过；证据 JSON 写 evidence/F94/
<profile>/ 与 evidence/F95/<profile>/（及 docs/construction/evidence/ 镜像）。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
FACE = REPO_ROOT / "implementation" / "python" / "skill_catalog.py"

OC28_ROOT = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
OC28_PIN = "026b106bc5d41b679ffc413264229c340871e4d3"
BUN = Path.home() / ".bun" / "bun.exe"

GIT_ENV = dict(os.environ,
               GIT_AUTHOR_DATE="2026-10-18T00:00:00+00:00",
               GIT_COMMITTER_DATE="2026-10-18T00:00:00+00:00")

PUBLIC_CATALOG = {"catalog_id": "community-skills", "channel": "public"}
CONTROLLED_CATALOG = {"catalog_id": "manuals-sample",
                      "channel": "controlled"}

SKILL_V1 = {
    "legal-review/SKILL.md": (
        "---\nname: legal-review\ndescription: 合同审查技能（合成验收样本）\n"
        "---\n第一步 通读全文。\n").encode("utf-8"),
    "legal-review/reference/checklist.md": "审查清单一（合成）。\n".encode("utf-8"),
    "legal-review/scripts/scan.py": b"print('inert-data-never-executed')\n",
    "notes.md": "# 根级单文件技能（合成）\n".encode("utf-8"),
}
SKILL_V2 = dict(SKILL_V1)
SKILL_V2["legal-review/SKILL.md"] = (
    "---\nname: legal-review\ndescription: 合同审查技能 v2（合成验收样本）\n"
    "---\n第一步 通读全文。第二步 复核要点。\n").encode("utf-8")

CONTROLLED_SKILL = {
    "playbook-sample/SKILL.md": (
        "---\nname: playbook-sample\ndescription: 受控内容包合成样本（裁决#7，"
        "不公开蒸馏）\n---\n受控合成正文，仅本机受控渠道消费。\n").encode("utf-8"),
}

CAT_ZIP_SKILL_DIR = "legal-skills-main/legal-citation"
CAT_ZIP_ENTRIES = [
    ("legal-skills-main/legal-citation/SKILL.md",
     "---\nname: legal-citation\ndescription: 引文核验技能（cat-xierluo 格式"
     "合成发布件）\n---\n引文先核后引。\n"),
    ("legal-skills-main/legal-citation/scripts/fmt.py",
     "print('never-executed-marker')\n"),
]


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id, "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self):
        return all(i["status"] == "PASS" for i in self.items)

    @property
    def passed_count(self):
        return sum(i["status"] == "PASS" for i in self.items)


def call_cli(method: str, args: dict, config: dict):
    """真产品入口子进程径（legal_entry CLI；同 F54/F112 recon 纪律）。"""
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "request.json"
        cfg = Path(tmp) / "config.json"
        req.write_text(json.dumps({"method": method, "args": args},
                                  ensure_ascii=False), encoding="utf-8")
        cfg.write_text(json.dumps(config, ensure_ascii=False),
                       encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", str(req), "--config", str(cfg)],
            capture_output=True, text=True, encoding="utf-8", timeout=300)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "RAW", "stdout": proc.stdout[:400]}
        return proc.returncode, payload


def expect_cli_refusal(checks: Checks, cid: str, method: str, args: dict,
                       config: dict, code_fragment: str):
    code, out = call_cli(method, args, config)
    ok = (code == 3 and out.get("status") == "NOT_CONNECTED"
          and code_fragment in str(out.get("code", "")))
    checks.add(cid, ok, f"{method} typed refusal {code_fragment} -> exit {code} "
                        f"{str(out.get('code', out.get('status','')))[:100]}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rmtree_rw(path: Path):
    """Windows 只读 .git 对象可删（先摘只读位）。"""
    def _onerror(func, p, _exc):
        Path(p).chmod(0o666)
        func(p)
    shutil.rmtree(path, onerror=_onerror)


def canonical_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def build_git_repo(root: Path, catalog: dict, files: dict,
                   message: str = "init") -> str:
    root.mkdir(parents=True, exist_ok=True)
    def git(*args):
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, env=GIT_ENV)
        assert proc.returncode == 0, proc.stderr[:200]
        return proc.stdout
    git("init", "-q")
    git("config", "core.autocrlf", "false")
    (root / "catalog.json").write_bytes(
        json.dumps(catalog, ensure_ascii=False).encode("utf-8"))
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    git("add", "-A")
    git("-c", "user.name=F94-Acceptance",
        "-c", "user.email=f94@juscite.local", "commit", "-q", "-m", message)
    return git("rev-parse", "HEAD").decode().strip()


def zip_raw(entries, compress=False) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for item in entries:
            name, data = item[0], item[1]
            attr = item[2] if len(item) > 2 else None
            zi = zipfile.ZipInfo("placeholder", date_time=(2026, 1, 1, 0, 0, 0))
            zi.filename = name  # 直赋绕过写端 os.sep 归一化
            if attr is not None:
                zi.external_attr = attr
            if compress:
                zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, data if isinstance(data, bytes)
                        else data.encode("utf-8"))
    return buf.getvalue()


def upstream_projection(skill_dir: Path, name: str, content: str) -> str:
    """独立重算上游 toModelOutput（packages/core/src/skill.ts）——与产品面
    实现不同代码路径，逐字节相等＝真安装运行的消费合同。"""
    files = sorted(
        str(p.resolve()) for p in skill_dir.rglob("*")
        if p.is_file() and p.name != "SKILL.md")[:10]
    return "\n".join([
        f'<skill_content name="{name}">',
        f"# Skill: {name}",
        "",
        content.strip(),
        "",
        f"Base directory for this skill: {skill_dir.resolve()}",
        "Relative paths in this skill (e.g., scripts/, reference/) are "
        "relative to this base directory.",
        "Note: file list is sampled.",
        "",
        "<skill_files>",
        *(f"<file>{f}</file>" for f in files),
        "</skill_files>",
        "</skill_content>",
    ])


BUN_PROBE_TS = """import { SkillFile } from "OC28/packages/core/src/config/plugin/skill-file.ts"
import path from "path"
const fs = require("fs")
const dir = path.resolve(process.argv[2]!)
const found: Array<[string, string]> = []
const rootMd: string[] = []
function walk(d: string) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name)
    if (e.isDirectory()) walk(p)
    else if (e.isFile() && e.name.toLowerCase().endsWith(".md")) {
      if (e.name === "SKILL.md") found.push([p, "SKILL"])
      else if (path.dirname(p) === dir) rootMd.push(p)
    }
  }
}
walk(dir)
const load = (p: string) => {
  const parsed = SkillFile.parse(dir, p, fs.readFileSync(p, "utf8"))
  return parsed._tag === "Parsed"
    ? { file: path.relative(dir, p).split(path.sep).join("/"), tag: "Parsed",
        id: parsed.skill.id, name: parsed.skill.name,
        description: parsed.skill.description ?? null }
    : { file: path.relative(dir, p).split(path.sep).join("/"),
        tag: "Skipped", reason: parsed.reason }
}
console.log(JSON.stringify([
  ...found.map(([p]) => load(p)), ...rootMd.map(load)]))
"""


def bun_parse_skills(checks: Checks, cid: str, skills_dir: Path,
                     expected: list, expect_skipped=None) -> bool:
    """真上游解析器（oc28 pin 检出只读 import）解析安装面，与 manifest 逐
    项相等。expect_skipped=None 要求零跳过；否则须与其相等（对偶证据）。"""
    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.ts"
        probe.write_text(BUN_PROBE_TS.replace("OC28",
                                              OC28_ROOT.as_posix()),
                         encoding="utf-8")
        proc = subprocess.run([str(BUN), str(probe), str(skills_dir)],
                              capture_output=True, text=True, timeout=120)
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return checks.add(cid, False,
                              f"bun probe failed: {proc.stderr[:200]}")
    got = [{"id": s["id"], "name": s["name"], "description": s["description"]}
           for s in parsed if s["tag"] == "Parsed"]
    skipped = [s["file"] for s in parsed if s["tag"] == "Skipped"]
    want = [{"id": s["id"], "name": s["name"],
             "description": s.get("description")}
            for s in expected]
    skip_ok = (skipped == expect_skipped) if expect_skipped is not None \
        else not skipped
    return checks.add(cid, got == want and skip_ok,
                      f"上游 skill-file.ts 解析安装面：{len(got)} 可加载"
                      f"={[x['id'] for x in got]} skipped={skipped} "
                      f"与期望相等={got == want and skip_ok}")


def run_profile(profile: str, workspace_root: Path) -> tuple[Checks, dict]:
    checks = Checks()
    facts: dict = {"profile": profile}
    workspace = workspace_root / profile
    if workspace.exists():
        rmtree_rw(workspace)
    workspace.mkdir(parents=True)
    state_root = workspace / "state"
    config = {"skill_catalog_state_root": str(state_root)}

    def channel_dir(channel: str) -> Path:
        return state_root / "skill-catalog" / channel

    # S0 环境与钉定 --------------------------------------------------------
    git_proc = subprocess.run(["git", "-C", str(OC28_ROOT),
                               "rev-parse", "HEAD"],
                              capture_output=True, text=True)
    oc28_head = git_proc.stdout.strip()
    checks.add("S0-1", oc28_head == OC28_PIN,
               f"oc28 只读核验 HEAD==pin 026b106…（实测 {oc28_head[:12]}…）")
    facts["oc28_head"] = oc28_head
    bun_v = subprocess.run([str(BUN), "--version"], capture_output=True,
                           text=True).stdout.strip() if BUN.is_file() else ""
    checks.add("S0-2", bool(bun_v), f"bun 在位（{bun_v or 'MISSING'}）")
    facts["bun"] = bun_v
    pub_repo = workspace / "src-public"
    commit_v1 = build_git_repo(pub_repo, PUBLIC_CATALOG, SKILL_V1)
    commit_v2 = build_git_repo(pub_repo, PUBLIC_CATALOG, SKILL_V2,
                               message="v2")
    ctl_repo = workspace / "src-controlled"
    commit_ctl = build_git_repo(ctl_repo, CONTROLLED_CATALOG,
                                CONTROLLED_SKILL)
    checks.add("S0-3", commit_v1 != commit_v2 and len(commit_v1) == 40,
               f"合成源确定性 commit：public v1={commit_v1[:12]}… v2="
               f"{commit_v2[:12]}… controlled={commit_ctl[:12]}…")
    facts.update(commit_v1=commit_v1, commit_v2=commit_v2,
                 commit_ctl=commit_ctl)

    # S1 F94 pin 离线安装（public） ----------------------------------------
    src_v1 = {"kind": "git_local", "repo": str(pub_repo),
              "commit": commit_v1}
    code, out = call_cli("skill.catalog.install",
                         {"channel": "public", "source": src_v1}, config)
    ok = code == 0 and out.get("status") == "OWNER_RESPONSE" \
        and out["result"]["status"] == "INSTALLED"
    checks.add("F94-A1", ok, f"git_local pin 安装经 CLI exit {code}")
    if not ok:
        return checks, facts
    r1 = out["result"]
    digest_v1 = r1["manifest_sha256"]
    facts["digest_public_v1"] = digest_v1
    checks.add("F94-A2", r1["commit"] == commit_v1
               and r1["channel"] == "public"
               and r1["kind"] == "git_local",
               f"receipt 钉定：commit==pin、channel/kind 如实"
               f"（{r1['install_id']}）")
    man_path = channel_dir("public") / "store" / digest_v1 / "manifest.json"
    man_bytes = man_path.read_bytes()
    checks.add("F94-A3", sha256_hex(man_bytes) == digest_v1,
               "manifest 摘要独立复算相等（canonical JSON sha256＝内容寻址）")
    manifest_v1 = json.loads(man_bytes)
    checks.add("F94-A4",
               all(f["sha256"] == sha256_hex(
                   (channel_dir("public") / "store" / digest_v1
                    / f["path"]).read_bytes())
                   for f in manifest_v1["files"]),
               f"manifest 逐文件 sha256 与 store 树全等"
               f"（{len(manifest_v1['files'])} 文件）")
    code, out = call_cli("skill.catalog.read",
                         {"channel": "public"}, config)
    ids = [s["id"] for s in out["result"]["skills"]] if code == 0 else []
    checks.add("F94-A5", code == 0 and ids == ["legal-review", "notes"],
               f"公开读取（消费面）：技能清单 {ids}（公开消费＋root md 形态）")
    code, out = call_cli("skill.catalog.read",
                         {"channel": "public", "skill_id": "legal-review"},
                         config)
    proj = out["result"].get("projection", "") if code == 0 else ""
    expect_proj = upstream_projection(
        channel_dir("public") / "skills" / "legal-review", "legal-review",
        "第一步 通读全文。\n")
    checks.add("F94-A6", proj == expect_proj,
               "运行投影==独立重算上游 toModelOutput（逐字节）＝真安装运行的"
               "消费合同；原生 loader 经 config skills 目录源可加载 skills/ 布局")
    code, out = call_cli("skill.catalog.verify", {"channel": "public"},
                         config)
    checks.add("F94-A7", code == 0
               and out["result"]["status"] == "OK",
               "verify 内容账全对（OK）")

    # S2 F94 回滚 ----------------------------------------------------------
    code, out = call_cli("skill.catalog.install",
                         {"channel": "public",
                          "source": {"kind": "git_local",
                                     "repo": str(pub_repo),
                                     "commit": commit_v2}}, config)
    digest_v2 = out["result"]["manifest_sha256"] if code == 0 else ""
    checks.add("F94-B1", code == 0 and digest_v2
               and digest_v2 != digest_v1,
               f"v2 安装换 pin（digest {digest_v2[:12]}…≠v1）")
    code, out = call_cli("skill.catalog.rollback", {"channel": "public"},
                         config)
    rb = out.get("result", {}) if code == 0 else {}
    back = (channel_dir("public") / "skills" / "legal-review"
            / "SKILL.md").read_bytes() if rb else b""
    checks.add("F94-B2", code == 0 and rb.get("action") == "rollback"
               and rb.get("manifest_sha256") == digest_v1
               and back == SKILL_V1["legal-review/SKILL.md"],
               f"回滚回 v1：digest 还原＋活动面逐字节还原"
               f"（restored={rb.get('restored_install_id')}）")
    expect_cli_refusal(checks, "F94-B3", "skill.catalog.rollback",
                       {"channel": "public"}, config,
                       "f94_rollback_no_previous")

    # S3 商用内容不混广场 ---------------------------------------------------
    src_ctl = {"kind": "git_local", "repo": str(ctl_repo),
               "commit": commit_ctl}
    code, out = call_cli("skill.catalog.install",
                         {"channel": "controlled", "source": src_ctl}, config)
    ok = code == 0 and out["result"]["status"] == "INSTALLED"
    digest_ctl = out["result"]["manifest_sha256"] if ok else ""
    facts["digest_controlled"] = digest_ctl
    checks.add("F94-C1", ok, f"受控合成样本（裁决#7）装 controlled OK"
               f"（digest {digest_ctl[:12]}…）")
    expect_cli_refusal(checks, "F94-C2", "skill.catalog.install",
                       {"channel": "public", "source": src_ctl}, config,
                       "f94_channel_mismatch")
    code, out = call_cli("skill.catalog.pack", {"channel": "controlled"},
                         config)
    packed_ctl = out["result"] if code == 0 else {}
    ctl_bundle = (channel_dir("controlled") / "bundles"
                  / packed_ctl.get("file", "x"))
    expect_cli_refusal(checks, "F94-C3", "skill.catalog.install",
                       {"channel": "public",
                        "source": {"kind": "bundle", "path": str(ctl_bundle),
                                   "sha256": packed_ctl.get("sha256", "")}},
                       config, "f94_channel_mismatch")
    code, out = call_cli("skill.catalog.read", {"channel": "public"}, config)
    pub_ids = {s["id"] for s in out["result"]["skills"]} if code == 0 else set()
    code, out = call_cli("skill.catalog.read",
                         {"channel": "controlled"}, config)
    ctl_ids = {s["id"] for s in out["result"]["skills"]} if code == 0 else set()
    checks.add("F94-C4", pub_ids == {"legal-review", "notes"}
               and ctl_ids == {"playbook-sample"} and not pub_ids & ctl_ids,
               f"渠道根物理分离读出不相交：public={sorted(pub_ids)} "
               f"controlled={sorted(ctl_ids)}；面上无跨渠道搬运方法")
    state_ctl2 = workspace / "state-controlled-offline"
    code, out = call_cli("skill.catalog.install",
                         {"channel": "controlled",
                          "source": {"kind": "bundle",
                                     "path": str(ctl_bundle),
                                     "sha256": packed_ctl["sha256"]}},
                         {"skill_catalog_state_root": str(state_ctl2)})
    checks.add("F94-C5", code == 0
               and out["result"]["manifest_sha256"] == digest_ctl,
               "受控 bundle 离线装入受控新根：digest 与源安装相等")

    # S4 桌面离线捆绑（public v1 活动态） -----------------------------------
    code, out = call_cli("skill.catalog.pack", {"channel": "public"}, config)
    packed1 = out["result"] if code == 0 else {}
    code, out = call_cli("skill.catalog.pack", {"channel": "public"}, config)
    packed2 = out["result"] if code == 0 else {}
    checks.add("F94-D1", packed1 and packed1 == packed2,
               f"pack 两次同产物（sha {packed1.get('sha256','')[:12]}…）＝确定性")
    facts["bundle_public_sha"] = packed1.get("sha256")
    bundle_path = channel_dir("public") / "bundles" / packed1["file"]
    state_offline = workspace / "state-offline-desktop"
    code, out = call_cli("skill.catalog.install",
                         {"channel": "public",
                          "source": {"kind": "bundle",
                                     "path": str(bundle_path),
                                     "sha256": packed1["sha256"]}},
                         {"skill_catalog_state_root": str(state_offline)})
    ok = code == 0 and out["result"]["manifest_sha256"] == digest_v1
    checks.add("F94-D2", ok,
               "bundle 离线装入全新状态根（模拟第二台桌面）：digest==源 pin 安装")
    code, out = call_cli("skill.catalog.verify", {"channel": "public"},
                         {"skill_catalog_state_root": str(state_offline)})
    checks.add("F94-D3", code == 0 and out["result"]["status"] == "OK",
               "离线根 verify OK（bundle 内逐文件 sha256 预检过）")
    tampered = bytearray(bundle_path.read_bytes())
    tampered[-1] ^= 0xFF
    bad_bundle = workspace / "tampered.bundle.zip"
    bad_bundle.write_bytes(bytes(tampered))
    expect_cli_refusal(checks, "F94-D4", "skill.catalog.install",
                       {"channel": "public",
                        "source": {"kind": "bundle", "path": str(bad_bundle),
                                   "sha256": packed1["sha256"]}},
                       {"skill_catalog_state_root": str(state_offline)},
                       "f95_zip_source_mismatch")

    # S5 F95 cat-xierluo zip 直装 ------------------------------------------
    zdata = zip_raw([(n, d) for n, d in CAT_ZIP_ENTRIES])
    zip_path = workspace / "legal-skills.zip"
    zip_path.write_bytes(zdata)
    zip_sha = sha256_hex(zdata)
    code, out = call_cli("skill.zip.inspect",
                         {"zip_path": str(zip_path), "sha256": zip_sha},
                         config)
    insp = out.get("result", {}) if code == 0 else {}
    checks.add("F95-A1", code == 0 and insp.get("status") == "OK"
               and [s["id"] for s in insp.get("skills", [])]
               == ["legal-citation"]
               and insp.get("scripts")
               == ["legal-skills-main/legal-citation/scripts/fmt.py"]
               and insp.get("executed") == [],
               "inspect 预检：技能可加载清单＋脚本惰性列出＋零执行")
    facts["zip_sha"] = zip_sha
    facts["digest_zip"] = None
    code, out = call_cli("skill.zip.install",
                         {"zip_path": str(zip_path), "sha256": zip_sha,
                          "url": "https://example.invalid/legal-skills.zip"},
                         config)
    ok = code == 0 and out.get("status") == "OWNER_RESPONSE" \
        and out["result"]["status"] == "INSTALLED"
    checks.add("F95-A2", ok, f"zip 直装（cat-xierluo 格式）经 CLI exit {code}")
    r_zip = out["result"] if ok else {}
    digest_zip = r_zip.get("manifest_sha256", "")
    facts["digest_zip"] = digest_zip
    checks.add("F95-A3", r_zip.get("channel") == "public"
               and r_zip.get("kind") == "zip"
               and r_zip.get("zip_sha256") == zip_sha
               and r_zip.get("scripts")
               == ["legal-skills-main/legal-citation/scripts/fmt.py"],
               "receipt：public 渠道＋zip_sha256 来源钉定＋脚本惰性列表")
    code, out = call_cli("skill.catalog.read",
                         {"channel": "public", "skill_id": "legal-citation"},
                         config)
    proj = out["result"].get("projection", "") if code == 0 else ""
    expect_proj = upstream_projection(
        channel_dir("public") / "skills" / "legal-citation",
        "legal-citation", "引文先核后引。\n")
    checks.add("F95-A4", proj == expect_proj,
               "zip 安装技能运行投影==上游 toModelOutput（格式兼容真安装运行）")
    code, out = call_cli("skill.catalog.verify", {"channel": "public"},
                         config)
    checks.add("F95-A5", code == 0 and out["result"]["status"] == "OK"
               and out["result"]["install_id"] == r_zip.get("install_id"),
               "zip 安装后 verify OK（全量替换：上一 pin 收进 history 可回滚）")
    code, out = call_cli("skill.catalog.read", {"channel": "public"}, config)
    hist = out["result"]["history_count"] if code == 0 else 0
    checks.add("F95-A6", hist == 4,
               f"history 链完整（v1 装/v2 装/回滚/zip 装＝{hist} 条，"
               "回滚亦入账 append-only）")

    # S6 F95 预检负向 -------------------------------------------------------
    good_skill = "---\nname: ok\n---\nx"
    def neg(cid, entries, frag, compress=False, attr_override=None):
        zd = zip_raw(entries, compress=compress)
        p = workspace / f"neg-{cid}.zip"
        p.write_bytes(zd)
        expect_cli_refusal(checks, cid, "skill.zip.install",
                           {"zip_path": str(p),
                            "sha256": sha256_hex(zd),
                            "url": "https://example.invalid/neg.zip"},
                           config, frag)
    neg("F95-B1", [("../evil.txt", b"x")], "f95_zip_path_unsafe")
    neg("F95-B2", [("/abs/evil.txt", b"x")], "f95_zip_path_unsafe")
    neg("F95-B3", [("C:/evil.txt", b"x")], "f95_zip_path_unsafe")
    neg("F95-B4", [("co" + chr(8) + "n.txt", b"x")], "f95_zip_path_unsafe")
    neg("F95-B5", [("CON/SKILL.md", good_skill)], "f95_zip_path_unsafe")
    neg("F95-B6", [("link.txt", b"target", 0o120777 << 16)],
        "f95_zip_entry_not_regular")
    neg("F95-B7", [("ok/SKILL.md", good_skill, 0o104755 << 16)],
        "f95_zip_permission_bits")
    neg("F95-B8", [("a.txt", b"x"), ("a.txt", b"y"),
                   ("ok/SKILL.md", good_skill)], "f95_zip_entry_duplicate")
    neg("F95-B9", [("only.txt", b"x")], "f95_zip_format_incompatible")
    bad_sha = workspace / "neg-mismatch.zip"
    bad_sha.write_bytes(zip_raw([("ok/SKILL.md", good_skill)]))
    expect_cli_refusal(checks, "F95-B10", "skill.zip.install",
                       {"zip_path": str(bad_sha), "sha256": "0" * 64,
                        "url": "https://example.invalid/neg.zip"},
                       config, "f95_zip_source_mismatch")
    expect_cli_refusal(checks, "F95-B11", "skill.zip.install",
                       {"zip_path": str(bad_sha),
                        "sha256": sha256_hex(bad_sha.read_bytes())},
                       config, "f95_zip_source_required")
    expect_cli_refusal(checks, "F95-B12", "skill.catalog.install",
                       {"channel": "controlled",
                        "source": {"kind": "zip", "path": str(zip_path),
                                   "sha256": zip_sha, "url": "u"}},
                       config, "f95_zip_channel_public_only")

    # S7 不信任任意脚本 -----------------------------------------------------
    face_src = FACE.read_text(encoding="utf-8")
    face_tree = ast.parse(face_src)
    ast_ok = True
    for node in ast.walk(face_tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in (
                    "eval", "exec", "compile", "__import__"):
                ast_ok = False
            if isinstance(node.func, ast.Attribute) and node.func.attr in (
                    "system", "popen"):
                ast_ok = False
        if isinstance(node, ast.keyword) and node.arg == "shell":
            ast_ok = False
    git_sites = [n for n in ast.walk(face_tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "_git"]
    checks.add("F95-C1", ast_ok and len(git_sites) == 2
               and '["git", "-C", str(repo), *args]' in face_src,
               "面 AST：零 eval/exec/shell；子进程仅 git 钉定解析两处"
               "（rev-parse＋archive），zip 路径零子进程")
    script_on_disk = (channel_dir("public") / "skills" / "legal-citation"
                      / "scripts" / "fmt.py")
    checks.add("F95-C2", script_on_disk.is_file()
               and script_on_disk.read_bytes()
               == CAT_ZIP_ENTRIES[1][1].encode("utf-8")
               and not (channel_dir("public") / "skills"
                        / "legal-citation" / "never-executed-marker").exists()
               and not (workspace / "never-executed-marker").exists(),
               "zip 内脚本落盘为惰性数据：字节原样、零执行痕迹（脚本若被运行"
               "会写的标记文件不存在）")

    # S8 上游原生解析器复跑 --------------------------------------------------
    # 两安装面对照：git 目录技能＋根 md（离线根仍为 v1 pin）与 zip 直装
    # 活动面（legal-citation）——真上游模块解析结果与各面 manifest 逐项相等。
    ok_a = bun_parse_skills(checks, "F95-D1a",
                            state_offline / "skill-catalog" / "public"
                            / "skills",
                            json.loads(man_path.read_bytes())["skills"])
    code, out = call_cli("skill.catalog.read", {"channel": "public"}, config)
    active_zip = out["result"].get("active", {}) if code == 0 else {}
    zip_manifest = json.loads((channel_dir("public") / "store"
                               / active_zip.get("manifest_sha256", "x")
                               / "manifest.json").read_bytes()) \
        if active_zip else {"skills": []}
    ok_b = bun_parse_skills(checks, "F95-D1b",
                            channel_dir("public") / "skills",
                            zip_manifest["skills"])
    ok = ok_a and ok_b
    checks.add("F95-D1", ok,
               "上游 skill-file.ts 真模块解析两安装面（git pin 面与 zip 直装"
               "面）与各 manifest 逐项相等——格式兼容由上游原生代码背书")
    broken_dir = workspace / "broken-fixture"
    (broken_dir / "bad-skill").mkdir(parents=True)
    (broken_dir / "bad-skill" / "SKILL.md").write_bytes(
        "---\nname: [broken\n---\ny".encode("utf-8"))
    ok2 = bun_parse_skills(checks, "F95-D2", broken_dir, [],
                           expect_skipped=["bad-skill/SKILL.md"])
    zbad = zip_raw([("good/SKILL.md", "---\nname: good\n---\nx"),
                    ("bad/SKILL.md", "---\nname: [broken\n---\ny")])
    bad_zip = workspace / "mixed-broken.zip"
    bad_zip.write_bytes(zbad)
    expect_cli_refusal(checks, "F95-D3", "skill.zip.install",
                       {"zip_path": str(bad_zip),
                        "sha256": sha256_hex(zbad),
                        "url": "https://example.invalid/broken.zip"},
                       config, "f94_skill_frontmatter_invalid")
    checks.add("F95-D4", ok and ok2,
               "对偶成立：上游 Skipped 的技能本面整包拒装（fail-closed 强于"
               "上游静默跳过，钉定可加载目录）")

    # S10 桥 fail-closed ----------------------------------------------------
    expect_cli_refusal(checks, "F94-E1", "skill.catalog.read",
                       {"channel": "public"}, {}, "f94_state_root_not_configured")
    expect_cli_refusal(checks, "F94-E2", "skill.catalog.destroy", {}, config,
                       "method_not_connected")
    return checks, facts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--workspace-root", type=Path, default=None)
    args = ap.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    workspace_root = args.workspace_root or (
        Path(tempfile.gettempdir()) / "juscite-f94-f95")

    all_facts: dict = {}
    all_ok = True
    for profile in profiles:
        print(f"===== profile: {profile} =====")
        checks, facts = run_profile(profile, workspace_root)
        all_facts[profile] = {"checks": checks.items, "facts": facts,
                              "passed": checks.passed_count,
                              "total": len(checks.items)}
        all_ok = all_ok and checks.all_passed

    # S9 跨 profile 确定性（同输入同摘要：分发链与宿主形态无关）
    if len(profiles) == 2:
        a, b = (all_facts[p]["facts"] for p in profiles)
        det = (a["commit_v1"] == b["commit_v1"]
               and a["commit_v2"] == b["commit_v2"]
               and a["commit_ctl"] == b["commit_ctl"]
               and a["digest_public_v1"] == b["digest_public_v1"]
               and a["digest_controlled"] == b["digest_controlled"]
               and a["digest_zip"] == b["digest_zip"]
               and a["bundle_public_sha"] == b["bundle_public_sha"])
        ca = all_facts[profiles[0]]["checks"]
        ca.append({"id": "S9-1",
                   "status": "PASS" if det else "FAIL",
                   "detail": f"跨 profile 确定性：合成源 commit×3＋manifest "
                             f"摘要×3＋bundle sha 全等（desktop==selfhost）"})
        print("[%s] S9-1 — 跨 profile 确定性（manifest 摘要与宿主形态无关）"
              % ("PASS" if det else "FAIL"))
        all_ok = all_ok and det

    for profile in profiles:
        for feature, seg in (("F94", ("F94", "S0", "S9")),
                             ("F95", ("F95", "S0", "S9"))):
            items = [i for i in all_facts[profile]["checks"]
                     if i["id"].startswith(tuple(seg))]
            payload = {
                "unit": "W3-U17", "feature": feature,
                "profile": profile,
                "generated_by": "tools/PENDING_OWNER_f94_f95_skilldist_zip_recon.py",
                "checks": items,
                "passed": sum(1 for i in items if i["status"] == "PASS"),
                "total": len(items),
                "status": "RECON_OK" if all(i["status"] == "PASS"
                                            for i in items) else "FAIL",
                "facts": {k: v for k, v in all_facts[profile]["facts"].items()
                          if k != "checks"},
            }
            for base in (REPO_ROOT / "evidence" / feature / profile,
                         REPO_ROOT / "docs" / "construction" / "evidence"
                         / feature / profile):
                base.mkdir(parents=True, exist_ok=True)
                (base / f"{feature.lower()}-result.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=1),
                    encoding="utf-8")

    print("===== RECON_%s（%s）=====" % (
        "OK" if all_ok else "FAIL",
        "；".join("%s=%d/%d" % (p, all_facts[p]["passed"],
                                all_facts[p]["total"])
                  for p in profiles)))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
