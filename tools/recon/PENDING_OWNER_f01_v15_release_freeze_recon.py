# -*- coding: utf-8 -*-
"""F01 B3 后段 v1.5 发行＋F77 生效日期发行冻结 对账（PENDING_OWNER 版，工单 W4-U27）。

义务（08§2 B3 后段「两发行安装升级恢复」的前半——发行物产出与冻结）：
  F01-desktop 残段（行 assertion 明文）：『完整 v1 发行与安装升级恢复依 08§2 B3 后段补齐』
    → 本单打 v1.5 安装物：复用 W3-U22 打包链（bun run build ＋ bun run package:win，
    electron-builder.config.ts win target=["nsis"]），**打包暂存用仓外 scratch 目录**
    （electron-builder 输出经 -c.directories.output 重定向，不落 oc28 dist——W3-U22
    『oc28 dist 暂存区被后续覆盖 3478a41c 如实披露』教训：暂存区与交付位分离）；
    产物入 evidence/artifact 双副本 sha256 逐位核同。
    跨版本升级路径实测归 W4-U28（本单不冒安装升级断言）。
  F77-selfhost/desktop 残段（行 assertion 明文）：『具体生效日期文本发行时冻结』
    → BSL1.1 参数文本＋生效日期随本发行冻结入 license 面（NOTICE-draft.md：
    生效日期=2026-10-20、Change Date=2030-10-20 自 2026-10-20 起满四年；
    已裁四参数不重开；Licensor 仍留空待裁）；上游 MIT/Apache NOTICE 保留核对；
    不称全部 BSL；个人免签不称公开签名包（E25 纪律）。

检查段：
  S0 预态锚定：oc28 HEAD=026b106…（v2.0.28 pin）；工作树足迹（git status --porcelain
     精确清单）预记录；oc28 dist 现存安装物 sha 预记录（覆盖态事实）。
  S1 构建：bun run build（cwd oc28/packages/desktop）exit 0。
  S2 打包：bun run package:win -- -c.directories.output=<仓外 scratch> exit 0。
  S3 产物与纪律：scratch 安装物在位；sha256 ≠ v1（13feaf18…，全新发行物）；
     oc28 dist 前 sha==后 sha（本运行零写 dist）；git status 预态==后态且 HEAD 不变
     （补丁链载体零改动——构建只写 gitignored out/，与 W3-U22 同链固有）。
  S4 双副本逐位核同：scratch → evidence（docs/construction/evidence/F77/desktop/v1.5/，
     入 git）与 artifact（.local/artifacts/F77/v1.5/，gitignored 冗余副本）——exe＋
     blockmap 三方 sha256 相等且字节级 filecmp 相同；SHA256SUMS.txt 冻结值落盘。
  S5 F77 冻结与闭包消费：复跑 tools/recon/PENDING_OWNER_e04_f77_release_license_closure.py
     --profile desktop（--installer/--dist-dir 指向 scratch v1.5 产物，--evidence-dir
     指向 v1.5 证据位）——A UNKNOWN 复核／B @sentry FSL 仅构建期／C BSL 参数+生效日期
     冻结（2030-10-20＋2026-10-20 逐字）／D 上游 NOTICE 修改声明保留＋in-app 注册表随包
     ／E 不称全部 BSL／F 免签 NotSigned 实跑＋禁称扫描／G shipped 闭包 0 UNKNOWN・
     0 强 Copyleft——全 PASS exit 0；另验 asar 内无 execprobe.tmp.ts（NOTICE §2 复拍
     披露的机械佐证）。
  S6 F01 发行记录：v1.5=战役第二发行（B3「两发行」之第二）；ProductVersion 保持
     2.0.28（E01 冻结不擅改，v1.5 为发行序号标签非版本字段变更）；与 v1/覆盖态
     3478a41c 关系如实入档；W4-U28 衔接注记。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f01_v15_release_freeze_recon.py
      [--oc28 DIR] [--scratch DIR] [--skip-build]

exit 0＝安装物产出＋双副本 sha256 逐位核同＋F77 冻结核对全 PASS。
红线：全程合成材料；%APPDATA%\\JusBench（v6 遗留）零触碰；不公开发布不打 tag；
oc28 源文件/补丁链零改动（构建只写 gitignored 位）；不 push 不 PR。
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RUN_UTC = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
RUN_DATE = time.strftime("%Y%m%d")

DEFAULT_OC28 = r"D:\Codex\1.法律工作区\jusbench工作区\oc28"
OC28_PIN_HEAD = "026b106bc5d41b679ffc413264229c340871e4d3"

# v1 冻结值（W3-U22，docs/construction/evidence/F77/desktop/SHA256SUMS.txt 在盘权威）
V1_EXE_SHA256 = "13feaf18ecafe70b9de4171b37d85463568dacd85e35d4e66ece43b292ef1efb"

# 本机负载实测（W4-U27 首跑）：build 约 7 分钟、electron-builder 打包逾 30 分钟
# （win-unpacked ~600MB 落盘＋NSIS 压缩 ~250MB，负载下更慢）——超时给足，宁可等不可半途。
BUILD_TIMEOUT = 30 * 60
PACKAGE_TIMEOUT = 120 * 60

EVIDENCE_DIR = Path("docs/construction/evidence/F77/desktop/v1.5")
ARTIFACT_DIR = Path(".local/artifacts/F77/v1.5")
F01_EVIDENCE_DIR = Path("evidence/F01/desktop")

EXEC_PROBE_NAME = "execprobe.tmp.ts"  # W3-U02 残留探针（NOTICE §2 复拍披露：不入安装物）


class Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str, **facts) -> None:
        self.items.append({"check": check_id, "result": "PASS" if ok else "FAIL",
                           "detail": detail, **facts})
        print(f"[v15-freeze] {'PASS' if ok else 'FAIL'} {check_id}: {detail}", flush=True)

    @property
    def failures(self) -> list[dict]:
        return [i for i in self.items if i["result"] == "FAIL"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_oc28(*args: str) -> str:
    return subprocess.run(["git", "-C", args[0], *args[1:]],
                          capture_output=True, check=True).stdout.decode("utf-8").strip()


def find_bun() -> Path:
    cand = Path(os.environ.get("BUN", "")) if os.environ.get("BUN") else Path.home() / ".bun" / "bun.exe"
    if cand.is_file():
        return cand
    found = subprocess.run(["where", "bun"], capture_output=True)
    if found.returncode == 0:
        first = found.stdout.decode("utf-8", "replace").splitlines()[0].strip()
        if first:
            return Path(first)
    raise RuntimeError("bun not found（W3-U22 链依赖 bun 1.4.2；设 BUN= 或装 ~/.bun/bun.exe）")


def run_step(argv: list, cwd: Path, timeout: int, log_path: Path) -> tuple[int, str]:
    """子进程输出按字节捕获落盘再解码（中文控制台不炸；全量输出入证据）。
    超时树杀（bun→electron-builder 孙进程持有输出管道，只杀直接子进程会留孤儿
    并把 run() 卡在管道收尾——W4-U27 首跑教训）。"""
    proc = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=timeout)
        blob = out + b"\n--- stderr ---\n" + err
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True)
        out, err = proc.communicate()
        mark = ("\n--- TIMEOUT: %ds tree-kill ---" % timeout).encode()
        blob = (out or b"") + b"\n--- stderr ---\n" + (err or b"") + mark
        rc = 124
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_bytes(blob)
    text = blob.decode("utf-8", errors="replace")
    return rc, text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--oc28", default=DEFAULT_OC28)
    ap.add_argument("--scratch", default=None, help="仓外打包暂存目录（缺省 %TEMP% 下新建）")
    ap.add_argument("--skip-build", action="store_true", help="仅调试用：跳过 bun run build（验收不带此参）")
    args = ap.parse_args()

    repo = Path.cwd()
    oc28 = Path(args.oc28)
    desktop_dir = oc28 / "packages" / "desktop"
    ck = Checks()
    # 仓 .gitignore 有 *.log——构建证据日志用 .txt 后缀以可入 git
    log_dir = Path("evidence/F01/desktop/v15-build-logs")

    # ---------------- S0 预态锚定 ----------------
    head = git_oc28(str(oc28), "rev-parse", "HEAD")
    pre_status = git_oc28(str(oc28), "status", "--porcelain")
    dist_exe = desktop_dir / "dist" / "opencode-desktop-win-x64.exe"
    pre_dist_sha = sha256_file(dist_exe) if dist_exe.is_file() else None
    v1_sums = (repo / "docs/construction/evidence/F77/desktop/SHA256SUMS.txt").read_text(encoding="utf-8")
    v1_in_repo = V1_EXE_SHA256 in v1_sums
    ck.add("S0.预态锚定", head == OC28_PIN_HEAD and v1_in_repo and len(pre_status) > 0,
           f"oc28 HEAD={head[:12]}（pin {'OK' if head == OC28_PIN_HEAD else 'DRIFT'}）；"
           f"工作树足迹 {len(pre_status.splitlines())} 行（补丁链载体）；v1 冻结值在盘={v1_in_repo}；"
           f"dist 现存安装物 sha（覆盖态事实）={(pre_dist_sha or 'none')[:16]}…",
           head=head, preStatusLines=pre_status.splitlines(), preDistSha256=pre_dist_sha)

    # ---------------- S1 构建（复用 W3-U22 链） ----------------
    bun = find_bun()
    if not args.skip_build:
        rc, text = run_step([str(bun), "run", "build"], desktop_dir, BUILD_TIMEOUT,
                            log_dir / "build.txt")
        tail = text[-400:].replace("\n", " | ")
        ck.add("S1.bun_run_build", rc == 0, f"bun run build（cwd oc28/packages/desktop）exit={rc}；尾迹：{tail}")
        if rc != 0:
            return 1
    else:
        ck.add("S1.bun_run_build", True, "SKIP（--skip-build 调试态，非验收形态）")

    # ---------------- S2 打包（输出重定向仓外 scratch） ----------------
    if args.scratch:
        scratch = Path(args.scratch)
    else:
        scratch = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / f"w4u27-v15-stage-{time.strftime('%Y%m%d-%H%M%S')}"
    scratch.mkdir(parents=True, exist_ok=True)
    inside_oc28 = str(scratch.resolve()).lower().startswith(str(oc28.resolve()).lower())
    inside_repo = str(scratch.resolve()).lower().startswith(str(repo.resolve()).lower())
    ck.add("S2.scratch_仓外", not inside_oc28 and not inside_repo,
           f"打包暂存 scratch={scratch}（oc28 内={inside_oc28}；juscite 内={inside_repo}——均应 False）")
    if inside_oc28 or inside_repo:
        return 1

    rc, text = run_step([str(bun), "run", "package:win", "--",
                         f"-c.directories.output={scratch}"],
                        desktop_dir, PACKAGE_TIMEOUT, log_dir / "package.txt")
    tail = text[-400:].replace("\n", " | ")
    ck.add("S2.bun_run_package_win", rc == 0,
           f"bun run package:win -- -c.directories.output=<scratch>（复用 W3-U22 链＋仅加输出重定向）exit={rc}；尾迹：{tail}")
    if rc != 0:
        return 1

    # ---------------- S3 产物与纪律 ----------------
    scratch_exe = scratch / "opencode-desktop-win-x64.exe"
    scratch_blockmap = scratch / "opencode-desktop-win-x64.exe.blockmap"
    scratch_unpacked = scratch / "win-unpacked"
    ok_files = scratch_exe.is_file() and scratch_blockmap.is_file() and (scratch_unpacked / "resources" / "app.asar").is_file()
    exe_sha = sha256_file(scratch_exe) if scratch_exe.is_file() else None
    exe_size = scratch_exe.stat().st_size if scratch_exe.is_file() else None
    ck.add("S3.scratch产物在位", ok_files,
           f"scratch 安装物在位={scratch_exe.is_file()}（{exe_size} B）＋blockmap＋win-unpacked/app.asar",
           scratch=str(scratch))
    if not ok_files or exe_sha is None:
        return 1

    post_status = git_oc28(str(oc28), "status", "--porcelain")
    post_head = git_oc28(str(oc28), "rev-parse", "HEAD")
    post_dist_sha = sha256_file(dist_exe) if dist_exe.is_file() else None
    discipline = (post_status == pre_status and post_head == head
                  and pre_dist_sha == post_dist_sha)
    ck.add("S3.oc28零改动dist零写", discipline,
           f"git status 预态==后态={post_status == pre_status}；HEAD 不变={post_head == head}；"
           f"dist sha 前==后（本运行零写 oc28 dist）={pre_dist_sha == post_dist_sha}"
           f"（{(pre_dist_sha or 'none')[:12]}…）；构建仅写 gitignored out/（W3-U22 链固有）")

    new_artifact = exe_sha != V1_EXE_SHA256
    ck.add("S3.全新发行物", new_artifact,
           f"v1.5 sha256={exe_sha}；≠ v1（{V1_EXE_SHA256[:12]}…）={new_artifact}"
           f"（v1.5 为 W4-U27 全新构建；与覆盖态 {(pre_dist_sha or 'none')[:12]}… 关系仅记录）",
           v15Sha256=exe_sha, v1Sha256=V1_EXE_SHA256, preDistSha256=pre_dist_sha)

    # ---------------- S4 双副本逐位核同 ----------------
    ev_dir = repo / EVIDENCE_DIR
    ar_dir = repo / ARTIFACT_DIR
    ev_dir.mkdir(parents=True, exist_ok=True)
    ar_dir.mkdir(parents=True, exist_ok=True)
    dual = {}
    for name, src in (("opencode-desktop-win-x64.exe", scratch_exe),
                      ("opencode-desktop-win-x64.exe.blockmap", scratch_blockmap)):
        ev = ev_dir / name
        ar = ar_dir / name
        ev.write_bytes(src.read_bytes())
        ar.write_bytes(src.read_bytes())
        shas = {p: sha256_file(p) for p in (src, ev, ar)}
        byte_equal = filecmp.cmp(str(src), str(ev), shallow=False) and filecmp.cmp(str(src), str(ar), shallow=False)
        dual[name] = {"sha256": shas[ev], "size": src.stat().st_size,
                      "threeWayShaEqual": len(set(shas.values())) == 1,
                      "byteIdentical": byte_equal}
        ck.add(f"S4.双副本核同:{name}",
               len(set(shas.values())) == 1 and byte_equal,
               f"scratch/evidence/artifact 三方 sha256={shas[ev][:16]}… 一致且 filecmp 字节级相同"
               f"（evidence={ev}｜artifact={ar}）")
    sums_lines = [f"{dual[n]['sha256']} *{n}" for n in sorted(dual)]
    (ev_dir / "SHA256SUMS.txt").write_text("\n".join(sums_lines) + "\n", encoding="utf-8")
    ar_sums = ar_dir / "SHA256SUMS.txt"
    ar_sums.write_text("\n".join(sums_lines) + "\n", encoding="utf-8")

    # ---------------- S5 F77 冻结与闭包消费（复跑 e04 工具对 v1.5 产物） ----------------
    e04 = repo / "tools" / "PENDING_OWNER_e04_f77_release_license_closure.py"
    rc, text = run_step([sys.executable, "-X", "utf8", str(e04),
                         "--profile", "desktop",
                         "--installer", str(scratch_exe),
                         "--dist-dir", str(scratch),
                         "--evidence-dir", str(repo / EVIDENCE_DIR)],
                        repo, 15 * 60, log_dir / "e04_v15.txt")
    e04_tail = [ln for ln in text.splitlines() if ln.startswith("[e04-f77]")][-12:]
    ck.add("S5.e04闭包消费全PASS", rc == 0,
           f"PENDING_OWNER_e04_f77_release_license_closure.py --profile desktop（installer/dist-dir→scratch v1.5）"
           f"exit={rc}；检查尾迹：{' | '.join(e04_tail[-6:])}")

    # asar 机械佐证：W3-U02 残留探针不入安装物（NOTICE §2 复拍披露）
    sys.path.insert(0, str(repo / "tools"))
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("e04tool", e04)
        e04mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(e04mod)
        header, payload_base = e04mod.parse_asar(scratch_unpacked / "resources" / "app.asar")
        files = e04mod.asar_files(header)
        probe_leak = [p for p in files if EXEC_PROBE_NAME in p]
        ck.add("S5.asar无execprobe残留", not probe_leak,
               f"asar 条目 {len(files)}；{EXEC_PROBE_NAME} 命中={probe_leak or '无'}"
               f"（W3-U02 临时探针不随 v1.5 分发，NOTICE §2 复拍披露机械佐证）")
    except Exception as exc:  # noqa: BLE001 —— 佐证失败即整体失败，不静默
        ck.add("S5.asar无execprobe残留", False, f"asar 扫描异常：{type(exc).__name__}: {exc}")
        probe_leak = ["scan_error"]

    # ---------------- S6 F01 发行记录 + 证据落盘 ----------------
    result = {
        "tool": "tools/recon/PENDING_OWNER_f01_v15_release_freeze_recon.py",
        "unit": "W4-U27",
        "run_utc": RUN_UTC,
        "oc28_head": head,
        "oc28_status_lines": post_status.splitlines(),
        "release": {
            "label": "v1.5（战役第二发行，08§2 B3 后段『两发行』之第二；跨版本升级路径实测归 W4-U28）",
            "installer": str(scratch_exe),
            "size_bytes": exe_size,
            "sha256": exe_sha,
            "blockmap_sha256": dual["opencode-desktop-win-x64.exe.blockmap"]["sha256"],
            "product_version_note": "ProductVersion 保持 2.0.28（E01 冻结不擅改）；v1.5 为发行序号标签非版本字段变更",
            "v1_relation": {"v1_sha256": V1_EXE_SHA256, "isNewArtifact": exe_sha != V1_EXE_SHA256,
                            "preDistOverwriteSha256": pre_dist_sha,
                            "preDistNote": "oc28 dist 现存物为 W3-U29 期再构建的覆盖态（W3-U23 披露 3478a41c…），非交付位"},
            "scratch_staging": str(scratch),
            "evidence_copy": str(ev_dir),
            "artifact_copy": str(ar_dir),
            "dual_copy": dual,
        },
        "f77_freeze": {
            "effective_date": "2026-10-20",
            "change_date": "2030-10-20",
            "note": "BSL1.1 参数文本+生效日期随本发行（v1.5）冻结入 license 面（NOTICE-draft.md）；已裁四参数不重开；Licensor 留空待裁；本机发行候选未公开发布",
        },
        "checks": ck.items,
        "failures": ck.failures,
    }
    (repo / F01_EVIDENCE_DIR).mkdir(parents=True, exist_ok=True)
    out_json = repo / F01_EVIDENCE_DIR / f"v15-release-freeze-recon-{RUN_DATE}.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    readme = [
        "# F77-desktop v1.5 发行证据（W4-U27，2026-10-20）",
        "",
        f"工单 W4-U27＝F01 B3 后段 v1.5 发行＋F77 生效日期随本发行冻结。安装物 {exe_size} B，",
        f"sha256 `{exe_sha}`（全新构建，≠ v1 `{V1_EXE_SHA256[:12]}…`）；blockmap sha256",
        f"`{dual['opencode-desktop-win-x64.exe.blockmap']['sha256']}`。",
        "",
        "## 文件",
        "",
        "| 文件 | 说明 |",
        "|---|---|",
        "| `opencode-desktop-win-x64.exe` | NSIS 安装物（v1.5，本机发行候选）。**个人免签（NotSigned），不称公开签名包；dev 通道无 publish 配置=结构性不可发布；本机不公开发布。** |",
        "| `opencode-desktop-win-x64.exe.blockmap` | electron-builder block map |",
        "| `SHA256SUMS.txt` | 上两项校验和 |",
        "| `release-closure-*.json/.md` | e04 工具对 v1.5 产物的 A-G 闭包实拍（0 UNKNOWN/0 强 Copyleft；F77 冻结日期核对） |",
        "",
        "## 与 v1 的关系",
        "",
        f"- v1=W3-U22（{V1_EXE_SHA256[:12]}…，001-016 载体期）；v1.5=本单（当前补丁链载体 3M+2??，含 017 期 userData 隔离等后改）。",
        f"- oc28 dist 现存 {(pre_dist_sha or 'none')[:12]}… 为 W3-U29 期覆盖态——教训落实：本单起打包暂存走仓外 scratch（-c.directories.output 重定向），dist 非交付位。",
        "- ProductVersion 保持 2.0.28（E01 冻结）；v1.5=战役发行序号。跨版本升级路径实测归 W4-U28。",
        "- F77 冻结：生效日期 2026-10-20／Change Date 2030-10-20（NOTICE-draft.md §1/§6.4）；双副本=本目录＋`<juscite>/.local/artifacts/F77/v1.5/`（gitignored，逐位核同）。",
    ]
    (ev_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")

    md = [
        f"# F01 B3 后段 v1.5 发行＋F77 生效日期冻结（W4-U27，{RUN_UTC}）",
        "",
    ] + [f"- **{i['result']}** {i['check']}：{i['detail']}" for i in ck.items]
    if ck.failures:
        md.append(f"- 失败 {len(ck.failures)} 项 → exit 1")
    (repo / F01_EVIDENCE_DIR / f"v15-release-freeze-recon-{RUN_DATE}.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"[v15-freeze] checks={len(ck.items)} fail={len(ck.failures)}")
    print(f"[v15-freeze] v1.5 sha256={exe_sha} size={exe_size}")
    print(f"[v15-freeze] evidence={ev_dir}")
    return 1 if ck.failures else 0


if __name__ == "__main__":
    sys.exit(main())
