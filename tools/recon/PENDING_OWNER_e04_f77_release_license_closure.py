# -*- coding: utf-8 -*-
"""E04+F77 发行闭包实拍验收（PENDING_OWNER 版，工单 W3-U22）。

义务：E04 余段=发行闭包实拍（e04-license-closure.md B0 静态段已定：2649 包/0 强传染/40 风险）；
F77 非功能行（17 卡）：BSL1.1 参数文本按已裁参数冻结／上游 MIT/Apache NOTICE 修改通知保留／
不称全部 BSL／个人免签不称公开签名包／具体生效日期文本发行时冻结。

七段检查：
  A UNKNOWN 488 复核：锁文件清单（e04-license-inventory.json）bucket 计数与 e04-license-closure.md §3.1/§7 纪律互核
  B @sentry/cli=FSL-1.1-MIT 仅构建期：清单事实＋desktop 发行实拍不在 shipped 闭包
  C BSL1.1 参数文本按已裁参数冻结：NOTICE-draft.md 冻结表逐参数在位；生效日期随 W4-U27
    v1.5 发行冻结（Change Date=2030-10-20＋生效日期=2026-10-20 逐字在位——原 W3-U22
    「发行未发生不填日期」随发行事件发生退役，改口理由见 FROZEN_BSL_ANCHORS 注）
  D 上游 MIT/Apache NOTICE 修改通知保留：上游版权行/sha256＋git 机械修改清单逐项在位＋上游 in-app 声明注册表随包标记实测
  E 不称全部 BSL：冻结面禁「整体/全部以 BSL」正声称；必有组合物诚实分权句
  F 个人免签不称公开签名包：desktop 安装物 Get-AuthenticodeSignature=NotSigned 实跑＋文档面明示未签
  G 发行闭包实拍（desktop）：win-unpacked app.asar 头解析 shipped 闭包逐包 license
    （0 UNKNOWN/0 强 Copyleft/MPL 枚举）＋Electron chromium 披露＋权重/字体扫描＋bundled CLI 实拍
    ＋安装物 sha256

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_e04_f77_release_license_closure.py --profile desktop
      [--oc28 <oc28 检出>] [--installer <dist exe>] [--evidence-dir docs/construction/evidence/F77/desktop]
  python -X utf8 tools/recon/PENDING_OWNER_e04_f77_release_license_closure.py --profile selfhost
      [--evidence-dir docs/construction/evidence/F77/selfhost]

exit 0＝本 profile 全部适用检查 PASS。
selfhost（首建 W3-U22；工件级补跑 W3-U33）：compose 实物已建（W3-U23 交付
implementation/deploy/f02-selfhost/{docker-compose.selfhost.yml,f02_selfhost_entry.py}，
随仓 commit）——B/F 按 compose 实物工件级实拍（B=字节扫描零 FSL/sentry/node_modules
命中＋镜像引用闭集＋entry import 全 stdlib/首方；F=两实物文件免签实拍——非 PE 文本
格式 Authenticode=UnknownError 即无签名载体【本机实测与普通 .txt 同；真有签名必回
Valid】，PE installer 面仍恰 NotSigned＋实物/文档面零「已签名/公开签名包」正声称）；
实物缺失 fail-closed 记 NOT_RUN_ARTIFACT_PENDING（不冒 PASS 不假 FAIL）。G 检
desktop 专属（compose 形态无 asar 安装物）。
只读消费：不写 oc28、不触 %APPDATA%、不触网络、不拉起 compose 栈
（栈真跑闭合属 E25/F02 面：evidence/E25/selfhost/recon-result.json RECON_OK 20/20）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

RUN_UTC = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
RUN_DATE = time.strftime("%Y%m%d")
RUN_UNIT = "W3-U33"  # 工件级补跑单；工具首建=W3-U22（desktop 面 7/7 未见改）

DEFAULT_OC28 = r"D:\Codex\1.法律工作区\jusbench工作区\oc28"

# F77-selfhost compose 实物（W3-U23 交付 4b5113b，随仓 commit；本单 W3-U33 消费）
COMPOSE_ARTIFACT_DIR = "implementation/deploy/f02-selfhost"
COMPOSE_ARTIFACT_FILES = (
    f"{COMPOSE_ARTIFACT_DIR}/docker-compose.selfhost.yml",
    f"{COMPOSE_ARTIFACT_DIR}/f02_selfhost_entry.py",
)
# B 工件级字节扫描标记：FSL 包（@sentry/cli 系）与 npm 闭包不得入 compose 实物
FSL_MARKERS = ("@sentry/cli", "sentry-cli", "sentry_cli", "node_modules")

# 已裁 BSL 参数冻结锚（W3-U22 冻结文本，见 NOTICE-draft.md §1）
# 已裁 BSL 参数冻结锚（W3-U22 冻结文本，见 NOTICE-draft.md §1）。
# 【W4-U27 改口 2026-10-20，实质不变量零放松】生效日期冻结态变更：
# 17 卡 F77「具体生效日期文本发行时冻结」的发行事件＝W4-U27 v1.5 发行文本（工单明文
# "BSL1.1 参数文本+生效日期随本发行冻结入 license 面"）——NOTICE 生效日期=2026-10-20、
# Change Date=2030-10-20（自 2026-10-20 起满四年，四年间隔=已裁参数不变；本机发行候选
# 未公开发布，锚定口径如需随未来真实首次公开发布调整属用户裁定）。故 check_c 由
# W3-U22 的「发行未发生→不得含日历日期」翻转为「发行已发生→必须含钉定冻结日期」；
# 冻结值必须逐字命中，防漂移。已裁四参数仍不重开。
FROZEN_BSL_ANCHORS = [
    ("Licensor 留空行", "| Licensor | 【留空，待发行冻结——权利主体未经用户裁定，不擅填】 |"),
    ("Licensed Work 行", "| Licensed Work | 律引（JusBench），基线 OpenCode v2.0.28"),
    ("Change License=MIT", "| Change License | MIT |"),
    # W4-U27：Change Date 行随 v1.5 发行冻结为具体日期（原 W3-U22 锚「自首次公开发布起满四年之日」随冻结态退役）
    ("Change Date=2030-10-20（v1.5 发行冻结）", "| Change Date | **2030-10-20**"),
    ("Change Date 锚定说明（自 2026-10-20 起满四年）", "自本发行文本冻结日 2026-10-20 起满四年之日"),
    ("Additional Use Grant=自用放行+禁竞品", "| Additional Use Grant | 律师／律所／个人自用放行；禁止竞争性使用"),
    ("私域三级", "| 私域分发三级 | 代码与 schema 可公开审计／法律方法手册（manuals）所内受控／人格（persona）内容个人"),
]
# W4-U27 冻结值（NOTICE §1 Change Date 行与 §6.4 生效日期行）
FROZEN_EFFECTIVE_DATE = "2026-10-20"
FROZEN_CHANGE_DATE = "2030-10-20"

# B0 静态段计数锚（e04-license-closure.md §3.1；键名=inventory JSON 实际 bucket 名）
B0_BUCKETS = {
    "first_party": 32,
    "permissive": 2089,
    "weak_copyleft": 7,
    "pd_dedication": 2,
    "custom_other": 4,
    "unknown": 488,
    "dual_or": 17,
    "multi_and": 7,
    "font": 3,
}
B0_TOTAL = 2649

UPSTREAM_COPYRIGHT = "Copyright (c) 2025 opencode"
UPSTREAM_LICENSE_SHA256 = "625F0F619133F89BBBB2ABE37369613DFA1885EBA1E50D02170DEB62BB42CB6B"

MODIFIED_PATHS = [
    "packages/app/src/shell/routes/routes.tsx",
    "packages/desktop/src/main/index.ts",
    "packages/desktop/src/main/service/background-service.ts",
    "packages/app/src/legal-workbench/",
]

WEIGHT_EXTS = (".onnx", ".gguf", ".safetensors", ".tflite", ".h5", ".ckpt", ".pt", ".pth", ".params")
FONT_EXTS = (".ttf", ".otf", ".woff", ".woff2", ".eot")

STRONG_COPYLEFT_RE = re.compile(r"\b((A)?GPL)-[0-9]|\bAGPL\b")

# 「不称全部 BSL」禁句式（正声称；纪律句「不称全部 BSL」属提及不算——否定窗判定见 mention_violation）
ALL_BSL_FORBIDDEN = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"整体[以按]\s*BSL",
        r"全部[以按]\s*BSL",
        r"整包\s*BSL",
        r"entire\s+(work|product|distribution)\s+(is\s+)?BSL",
        r"whole\s+(work|product|distribution)\s+(is\s+)?BSL",
    )
]
ALL_BSL_REQUIRED = ("BSL 1.1", "上游", "MIT")  # 组合物诚实分权句三要素

# 签名禁称（正声称；「不称公开签名包」等纪律提及不算）
UNSIGNED_FORBIDDEN = re.compile(r"已签名|公开签名包|digitally signed", re.IGNORECASE)

# 否定窗：命中样式的紧前方若含否定/纪律标记则按「提及」处理，不算正声称
NEGATION_MARKERS = ("不称", "不是", "无", "禁", "未", "非", "不冒", "排除")


def mention_violation(text: str, pattern) -> str | None:
    for m in pattern.finditer(text):
        ctx = text[max(0, m.start() - 8) : m.start()]
        if not any(neg in ctx for neg in NEGATION_MARKERS):
            return m.group(0)
    return None


class Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool | None, detail: str) -> None:
        self.items.append(
            {
                "check": check_id,
                "result": "PASS" if ok is True else ("FAIL" if ok is False else "NOT_RUN_ARTIFACT_PENDING"),
                "detail": detail,
            }
        )
        mark = "PASS" if ok is True else ("FAIL" if ok is False else "SKIP")
        print(f"[e04-f77] {mark} {check_id}: {detail}")

    @property
    def failures(self) -> list[dict]:
        return [i for i in self.items if i["result"] == "FAIL"]

    @property
    def skips(self) -> list[dict]:
        return [i for i in self.items if i["result"] == "NOT_RUN_ARTIFACT_PENDING"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def read_repo_file(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def git_oc28_status(oc28: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(oc28), "status", "--porcelain"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [ln for ln in out.splitlines() if ln.strip()]


def authenticode_status(path: Path) -> str:
    ps = (
        "(Get-AuthenticodeSignature -LiteralPath "
        f"'{str(path)}'"
        ").Status.ToString()"
    )
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
    )
    return out.stdout.decode("utf-8", "replace").strip()


def _not_pe(path: Path) -> bool:
    """非 PE 格式（无 MZ 头）＝无 Authenticode 内嵌签名载体。"""
    return not path.read_bytes().startswith(b"MZ")


def _unsigned_face_ok(status: str, path: Path) -> bool:
    """免签判定：PE 面（installer）必须恰 NotSigned；非 PE 文本工件面
    UnknownError 亦判无签名——本机实测（2026-10-20）：普通 .txt 与 compose
    两文件同回 UnknownError＋StatusMessage「指定的信任提供程序不认识或不支持
    使用者的指定格式」（该格式不支持 Authenticode），真有签名（含 cat 目录册
    命中，对照组 C:\\Windows\\System32\\where.exe）必回 Valid。"""
    if status == "NotSigned":
        return True
    return status == "UnknownError" and _not_pe(path)


# ---------------- asar 头解析（机械实拍，无第三方依赖） ----------------


def parse_asar(path: Path) -> tuple[dict, int]:
    raw = path.read_bytes()
    header_size = struct.unpack_from("<I", raw, 4)[0]
    json_len = struct.unpack_from("<I", raw, 12)[0]
    header = json.loads(raw[16 : 16 + json_len].rstrip(b"\x00"))
    return header, 8 + header_size


def asar_files(header: dict) -> dict[str, dict]:
    files: dict[str, dict] = {}

    def walk(node: dict, prefix: list[str]) -> None:
        for k, v in node.get("files", {}).items():
            if "files" in v:
                walk(v, prefix + [k])
            else:
                files["/".join(prefix + [k])] = v

    walk(header, [])
    return files


def shipped_packages(files: dict[str, dict], unpacked_root: Path) -> dict[str, dict]:
    """shipped 闭包 = asar 内 node_modules/<pkg>/package.json ∪ app.asar.unpacked/node_modules 磁盘包。"""
    pkgs: dict[str, dict] = {}
    for path in files:
        segs = path.split("/")
        for i, seg in enumerate(segs):
            if seg == "node_modules":
                if i + 1 >= len(segs):
                    break
                name = segs[i + 1]
                if name.startswith("@"):
                    if i + 2 >= len(segs):
                        break
                    name = f"{name}/{segs[i + 2]}"
                key = f"node_modules/{name}"
                if key not in pkgs:
                    pj_rel = f"{key}/package.json"
                    pkgs[key] = {"package_json": pj_rel, "unpacked": False}
                break
    if unpacked_root.is_dir():
        for nm in sorted(unpacked_root.rglob("package.json")):
            rel = nm.relative_to(unpacked_root.parent)
            key = str(rel.as_posix()[: -len("/package.json")])
            pkgs[key] = {"package_json": None, "unpacked": True, "disk": str(nm)}
    return pkgs


def read_pkg_meta(pkg: dict, asar_path: Path, payload_base: int, files: dict[str, dict]) -> dict:
    if pkg.get("unpacked"):
        d = json.loads(Path(pkg["disk"]).read_text(encoding="utf-8"))
    else:
        v = files[pkg["package_json"]]
        with open(asar_path, "rb") as f:
            f.seek(payload_base + int(v["offset"]))
            data = f.read(v["size"])
        d = json.loads(data)
    return {
        "version": d.get("version"),
        "license": d.get("license"),
        "licenses": d.get("licenses"),
    }


# ---------------- 检查段 ----------------


def check_a_unknown_488(repo: Path, ck: Checks) -> None:
    inv = json.loads(read_repo_file(repo, "docs/construction/e04-license-inventory.json"))
    meta = inv["meta"]
    pkgs = inv["packages"]
    closure = read_repo_file(repo, "docs/construction/e04-license-closure.md")
    ok_parts = []
    ok_parts.append(("unique_packages", meta["unique_packages"] == B0_TOTAL, str(meta["unique_packages"])))
    by_bucket = {}
    for p in pkgs:
        by_bucket[p["bucket"]] = by_bucket.get(p["bucket"], 0) + 1
    for name, want in B0_BUCKETS.items():
        got = by_bucket.get(name, 0)
        ok_parts.append((f"bucket:{name}", got == want, f"{got}=={want}"))
    unk_reason = {}
    for p in pkgs:
        if p["bucket"] == "unknown":
            r = p.get("unknown_reason", "")
            key = "本地未安装" if "本地未安装" in r else ("workspace 无字段" if "workspace" in r else "无字段")
            unk_reason[key] = unk_reason.get(key, 0) + 1
    detail = (
        f"锁文件去重 {meta['unique_packages']}=={B0_TOTAL}；"
        + "；".join(f"{k}={v}" for k, v, _ in [x for x in ok_parts if x[0].startswith('bucket')])
        + f"；UNKNOWN 分解={unk_reason}"
    )
    ok = all(x[1] for x in ok_parts)
    ok = ok and ("不能声称「当前依赖闭包无传染性许可」" in closure)
    detail += "；§7 不声称纪律在位" if ok else "；§7 纪律缺失或计数不符"
    ck.add("A.UNKNOWN488复核", ok, detail)


def check_b_sentry_fsl(
    repo: Path,
    ck: Checks,
    shipped: dict[str, dict] | None,
    pkg_meta: dict[str, dict] | None,
    compose_scan: dict | None = None,
) -> None:
    inv = json.loads(read_repo_file(repo, "docs/construction/e04-license-inventory.json"))
    fsl = [
        f"{p['name']}@{p['version']}"
        for p in inv["packages"]
        if "sentry/cli" in p["name"] and p.get("license") == "FSL-1.1-MIT"
    ]
    if shipped is None:
        detail = f"清单事实：FSL-1.1-MIT={fsl}；工件级实拍未跑"
        if compose_scan is not None:
            detail += f"（compose 实物缺失={compose_scan.get('present')}，fail-closed 如实挂账）"
        else:
            detail += "（compose 实物未建，挂 E25）"
        ck.add(
            "B.sentryCLI_FSL_仅构建期",
            None,
            detail,
        )
        return
    shipped_names = set(shipped.keys())
    leak = [n for n in ("node_modules/@sentry/cli", "node_modules/@sentry/cli-win32-x64") if n in shipped_names]
    sentry_shipped = sorted(k for k in shipped_names if k.startswith("node_modules/@sentry/"))
    sentry_licenses = {k: (pkg_meta.get(k, {}).get("license") or pkg_meta.get(k, {}).get("licenses")) for k in sentry_shipped}
    non_mit = {k: v for k, v in sentry_licenses.items() if v != "MIT"}
    ok = not leak and not non_mit
    detail = (
        f"FSL 清单={fsl}；泄漏={leak}；shipped @sentry/*={len(sentry_shipped)} 包全 MIT（{non_mit or '无非 MIT'}）"
    )
    if compose_scan is not None:
        comp_ok = bool(compose_scan.get("ok_b"))
        ok = ok and comp_ok
        detail += (
            f"；compose 工件级：FSL/sentry/node_modules 字节扫描零命中={compose_scan['fsl_hits']}（"
            f"{'零命中' if compose_scan['fsl_hits_zero'] else '命中即泄漏'}）；"
            f"镜像引用闭集={compose_scan['images']}（无本地 build 段={compose_scan['no_build_section']}"
            f"，==[python:3.12-alpine]={compose_scan['image_ok']}）；"
            f"entry import 顶层={compose_scan['entry_import_tops']}（全 stdlib＋legal_harness 首方={compose_scan['imports_ok']}）"
        )
    ck.add(
        "B.sentryCLI_FSL_仅构建期",
        ok,
        detail,
    )


def check_c_bsl_params(repo: Path, ck: Checks) -> None:
    notice = read_repo_file(repo, "docs/construction/NOTICE-draft.md")
    missing = [name for name, anchor in FROZEN_BSL_ANCHORS if anchor not in notice]
    cd_line = next((ln for ln in notice.splitlines() if ln.startswith("| Change Date")), "")
    # W4-U27 冻结态：发行事件（v1.5 发行文本）已发生 → Change Date 必须逐字含冻结日期
    # 2030-10-20，NOTICE 生效日期行必须逐字含 2026-10-20（原 W3-U22「不得含日历日期」
    # 随发行事件发生退役，改口理由见 FROZEN_BSL_ANCHORS 注）。
    cd_frozen = FROZEN_CHANGE_DATE in cd_line
    eff_frozen = f"生效日期：**{FROZEN_EFFECTIVE_DATE}" in notice
    ok = not missing and cd_frozen and eff_frozen and ("不称「全部 BSL」" in notice or "不称「全部BSL」" in notice)
    ck.add(
        "C.BSL参数文本冻结",
        ok,
        f"冻结锚缺失={missing or '无'}；Change Date 冻结值 {FROZEN_CHANGE_DATE} 在位={cd_frozen}"
        f"（W4-U27 随 v1.5 发行冻结）；生效日期 {FROZEN_EFFECTIVE_DATE} 在位={eff_frozen}；不称全部BSL句在位",
    )


def check_d_upstream_notice(repo: Path, oc28: Path, ck: Checks, asar_markers: dict[str, int] | None) -> None:
    notice = read_repo_file(repo, "docs/construction/NOTICE-draft.md")
    missing_paths = [p for p in MODIFIED_PATHS if p not in notice]
    ok = (
        (UPSTREAM_COPYRIGHT in notice)
        and (UPSTREAM_LICENSE_SHA256 in notice)
        and not missing_paths
    )
    detail = (
        f"上游版权行/sha256 在位={UPSTREAM_COPYRIGHT[:20] if UPSTREAM_COPYRIGHT in notice else False}/"
        f"{UPSTREAM_LICENSE_SHA256[:8] if UPSTREAM_LICENSE_SHA256 in notice else False}；"
        f"修改清单缺失={missing_paths or '无'}"
    )
    if asar_markers is not None:
        marks_ok = (
            asar_markers.get("Reserved Font Name", 0) >= 1
            and asar_markers.get("Apache License", 0) >= 1
            and asar_markers.get("betteroffice", 0) >= 1
        )
        ok = ok and marks_ok
        detail += f"；上游 in-app 声明注册表随包标记={asar_markers}"
    else:
        detail += "；in-app 注册表为源树声明（工件级标记未跑，compose 挂 E25）"
    ck.add("D.上游NOTICE修改声明保留", ok, detail)


def check_e_not_all_bsl(repo: Path, ck: Checks) -> None:
    targets = [
        "docs/construction/NOTICE-draft.md",
        "docs/construction/e01-stack-freeze.md",
        "docs/construction/e04-license-closure.md",
    ]
    hits: list[str] = []
    honest: list[str] = []
    for rel in targets:
        text = read_repo_file(repo, rel)
        for rx in ALL_BSL_FORBIDDEN:
            hit = mention_violation(text, rx)
            if hit:
                hits.append(f"{rel}:{hit}")
        if rel.endswith("NOTICE-draft.md") and all(s in text for s in ALL_BSL_REQUIRED):
            honest.append(rel)
    closure = read_repo_file(repo, "docs/construction/e04-license-closure.md")
    ok = (not hits) and bool(honest) and ("不能声称「当前依赖闭包无传染性许可」" in closure)
    ck.add("E.不称全部BSL", ok, f"禁句命中={hits or '无'}；组合物分权句={honest}；B0 §7 不声称纪律在位")


def check_f_unsigned(
    ck: Checks,
    installer: Path | None,
    docs_texts: list[tuple[str, str]],
    artifact_files: list[Path] | None = None,
    artifact_texts: list[tuple[str, str]] | None = None,
) -> None:
    bad = [f"{rel}:{mention_violation(text, UNSIGNED_FORBIDDEN)}" for rel, text in docs_texts if mention_violation(text, UNSIGNED_FORBIDDEN)]
    for rel, text in artifact_texts or []:
        v = mention_violation(text, UNSIGNED_FORBIDDEN)
        if v:
            bad.append(f"{rel}:{v}")
    if installer is None and not artifact_files:
        ck.add(
            "F.个人免签不称公开签名包",
            None,
            f"工件级实拍未跑（compose 实物缺失）；文档面禁称命中={bad or '无'}",
        )
        return
    faces: list[tuple[str, Path]] = []
    if installer is not None:
        faces.append(("installer", installer))
    faces.extend((p.name, p) for p in artifact_files or [])
    statuses = [(name, authenticode_status(p), p) for name, p in faces]
    ok = all(_unsigned_face_ok(s, p) for _, s, p in statuses) and not bad
    shown = [f"{name}={s}" + ("" if s == "NotSigned" else "（非 PE 文本格式无签名载体）") for name, s, _ in statuses]
    ck.add(
        "F.个人免签不称公开签名包",
        ok,
        f"Get-AuthenticodeSignature={shown}（全无签名）；文档面禁称命中={bad or '无'}",
    )


def check_g_release_snapshot(
    repo: Path,
    oc28: Path,
    dist_dir: Path,
    installer: Path,
    ck: Checks,
) -> tuple[dict, dict, dict[str, int]]:
    win_unpacked = dist_dir / "win-unpacked"
    asar = win_unpacked / "resources" / "app.asar"
    unpacked_nm = win_unpacked / "resources" / "app.asar.unpacked" / "node_modules"

    header, payload_base = parse_asar(asar)
    files = asar_files(header)
    shipped = shipped_packages(files, unpacked_nm)
    pkg_meta: dict[str, dict] = {}
    unread: list[str] = []
    for key, pkg in sorted(shipped.items()):
        try:
            pkg_meta[key] = read_pkg_meta(pkg, asar, payload_base, files)
        except Exception as exc:  # noqa: BLE001 —— 机械实拍：读不到如实记
            unread.append(f"{key}:{type(exc).__name__}")
            pkg_meta[key] = {"version": None, "license": None, "licenses": None, "error": str(exc)}

    unknown = sorted(k for k, v in pkg_meta.items() if not (v.get("license") or v.get("licenses")))
    strong = sorted(
        f"{k}={pkg_meta[k].get('license')}"
        for k, v in pkg_meta.items()
        if STRONG_COPYLEFT_RE.search(str(v.get("license") or "") + " " + str(v.get("licenses") or ""))
        and "LGPL" not in str(v.get("license") or "")
    )
    mpl = sorted(
        f"{k}@{pkg_meta[k].get('version')}={pkg_meta[k].get('license')}"
        for k, v in pkg_meta.items()
        if "MPL" in str(v.get("license") or "")
    )
    weight_files = sorted(p for p in files if p.lower().endswith(WEIGHT_EXTS))
    font_files = sorted(p for p in files if p.lower().endswith(FONT_EXTS))
    chromium = (win_unpacked / "LICENSES.chromium.html").is_file()
    electron_lic = (win_unpacked / "LICENSE.electron.txt").is_file()

    data = open(asar, "rb").read()
    markers = {
        "Reserved Font Name": data.count(b"Reserved Font Name"),
        "Apache License": data.count(b"Apache License"),
        "betteroffice": data.count(b"betteroffice"),
        "OpenOOXML": data.count(b"OpenOOXML"),
        "OFL-1.1": data.count(b"OFL-1.1"),
    }
    del data

    cli_exe = win_unpacked / "resources" / "opencode-cli.exe"
    cli_version = (win_unpacked / "resources" / "opencode-cli.version").read_text(encoding="utf-8").strip()
    cli_sha = sha256_file(cli_exe)
    exe_sha = sha256_file(installer)
    blockmap = installer.with_suffix(installer.suffix + ".blockmap")
    blockmap_sha = sha256_file(blockmap) if blockmap.is_file() else None

    ok = (not unknown) and (not strong) and (not unread) and chromium and electron_lic and (not weight_files)
    detail = (
        f"shipped 闭包={len(shipped)} 包（asar 条目 {len(files)}）；UNKNOWN={unknown or '0'}；"
        f"强 Copyleft={strong or '0'}；MPL={mpl}；unread={unread or '无'}；"
        f"chromium 披露={chromium}/electron LICENSE={electron_lic}；权重文件={len(weight_files)}；字体文件={len(font_files)}"
    )
    ck.add("G.发行闭包实拍", ok, detail)

    snapshot = {
        "installer": {
            "path": str(installer),
            "size_bytes": installer.stat().st_size,
            "sha256": exe_sha,
            "blockmap_sha256": blockmap_sha,
        },
        "shipped_packages": {
            "total": len(shipped),
            "unknown": unknown,
            "strong_copyleft": strong,
            "mpl_file_level": mpl,
            "unread": unread,
            "licenses": {k: v for k, v in sorted(pkg_meta.items())},
        },
        "asar": {"entries": len(files), "node_modules_packages": len(shipped)},
        "electron_disclosure": {
            "LICENSES.chromium.html": chromium,
            "LICENSE.electron.txt": electron_lic,
        },
        "weights_files": weight_files,
        "font_files_count": len(font_files),
        "bundled_cli": {
            "sha256": cli_sha,
            "version": cli_version,
            "provenance": "@opencode/cli-windows-x64-baseline@dev（npm dev nightly；scripts/prebuild.ts dev 分支 downloadCliToResources 下载，非本机源码编译）",
        },
    }
    return snapshot, pkg_meta, markers


def gather_docs(repo: Path) -> list[tuple[str, str]]:
    out = []
    for rel in (
        "docs/construction/NOTICE-draft.md",
        "docs/construction/e01-stack-freeze.md",
        "docs/construction/e04-license-closure.md",
    ):
        out.append((rel, read_repo_file(repo, rel)))
    return out


def compose_artifact_scan(repo: Path) -> dict:
    """F77-selfhost 工件级实拍（W3-U22 挂账 B/F，本单 W3-U33 补跑）。

    实物＝W3-U23 交付 compose 两文件（implementation/deploy/f02-selfhost/，随仓
    commit）：
    B＝@sentry/cli(FSL-1.1-MIT) 工件级不入闭包：两实物字节扫描 FSL_MARKERS 零命中
       ＋镜像引用闭集（唯一 python:3.12-alpine 官方镜像、无本地 build 段）
       ＋entry import 顶层全 stdlib/legal_harness 首方（sys.stdlib_module_names 判定）；
    F＝签名面共用同一实物（Authenticode 实跑在 check_f_unsigned）。
    只读、不触网络、不拉起 compose 栈（栈真跑闭合属 E25/F02 已 VERIFIED 面）。
    """
    out: dict = {"files": list(COMPOSE_ARTIFACT_FILES)}
    present: dict[str, bool] = {}
    shas: dict[str, str] = {}
    sizes: dict[str, int] = {}
    texts: dict[str, str] = {}
    for rel in COMPOSE_ARTIFACT_FILES:
        p = repo / rel
        present[rel] = p.is_file()
        if p.is_file():
            raw = p.read_bytes()
            shas[rel] = hashlib.sha256(raw).hexdigest()
            sizes[rel] = len(raw)
            texts[rel] = raw.decode("utf-8")
    out["present"] = present
    out["sha256"] = shas
    out["bytes"] = sizes
    out["present_ok"] = all(present.values())
    out["_texts"] = texts
    if not out["present_ok"]:
        return out
    fsl_hits = {rel: [m for m in FSL_MARKERS if m in texts[rel]] for rel in COMPOSE_ARTIFACT_FILES}
    yml = texts[COMPOSE_ARTIFACT_FILES[0]]
    entry = texts[COMPOSE_ARTIFACT_FILES[1]]
    images = []
    for line in yml.splitlines():
        m = re.match(r"\s*image:\s*(\S+)", line)
        if m:
            images.append(m.group(1))
    tops: set[str] = set()
    for a, b in re.findall(r"^\s*(?:from\s+([\w.]+)|import\s+([\w.]+))", entry, re.MULTILINE):
        tops.add((a or b).split(".")[0])
    import_tops = sorted(tops)
    imports_ok = all(t in sys.stdlib_module_names or t == "legal_harness" for t in tops)
    fsl_zero = all(not v for v in fsl_hits.values())
    image_ok = images == ["python:3.12-alpine"]
    no_build = "build:" not in yml
    out.update(
        {
            "fsl_hits": fsl_hits,
            "fsl_hits_zero": fsl_zero,
            "images": images,
            "image_ok": image_ok,
            "no_build_section": no_build,
            "entry_import_tops": import_tops,
            "imports_ok": imports_ok,
            "ok_b": fsl_zero and image_ok and no_build and imports_ok,
        }
    )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=("desktop", "selfhost"), required=True)
    ap.add_argument("--oc28", default=DEFAULT_OC28)
    ap.add_argument("--installer", default=None)
    # W4-U27 增设（只加参不改默认）：打包产物输出已可重定向仓外 scratch——
    # win-unpacked/app.asar 相对 dist_dir 取，--dist-dir 指向 scratch 输出根即可对
    # 非默认位置安装物做闭包实拍；缺省行为与 W3-U22 完全一致。
    ap.add_argument("--dist-dir", default=None)
    ap.add_argument("--evidence-dir", default=None)
    args = ap.parse_args()

    repo = Path.cwd()
    oc28 = Path(args.oc28)
    ck = Checks()

    check_a_unknown_488(repo, ck)
    check_c_bsl_params(repo, ck)
    check_e_not_all_bsl(repo, ck)
    docs = gather_docs(repo)

    if args.profile == "desktop":
        dist_dir = Path(args.dist_dir) if args.dist_dir else oc28 / "packages" / "desktop" / "dist"
        installer = Path(args.installer) if args.installer else dist_dir / "opencode-desktop-win-x64.exe"
        if not installer.is_file():
            print(f"[e04-f77] FATAL: 安装物不存在：{installer}")
            return 2
        snapshot, pkg_meta, markers = check_g_release_snapshot(repo, oc28, dist_dir, installer, ck)
        shipped = snapshot["shipped_packages"]
        check_b_sentry_fsl(repo, ck, {k: {} for k in shipped["licenses"]}, pkg_meta)
        check_d_upstream_notice(repo, oc28, ck, markers)
        check_f_unsigned(ck, installer, docs)
    else:
        # W3-U33 补跑：compose 实物已建（W3-U23 交付）——B/F 工件级实拍；实物缺失 fail-closed 保持挂账
        scan = compose_artifact_scan(repo)
        if scan["present_ok"]:
            check_b_sentry_fsl(repo, ck, {}, {}, compose_scan=scan)
            check_d_upstream_notice(repo, oc28, ck, None)
            check_f_unsigned(
                ck,
                None,
                docs,
                artifact_files=[repo / rel for rel in COMPOSE_ARTIFACT_FILES],
                artifact_texts=[(rel, scan["_texts"][rel]) for rel in COMPOSE_ARTIFACT_FILES],
            )
        else:
            check_b_sentry_fsl(repo, ck, None, None, compose_scan=scan)
            check_d_upstream_notice(repo, oc28, ck, None)
            check_f_unsigned(ck, None, docs)
        scan.pop("_texts", None)
        snapshot = {
            "note": "selfhost compose 实物在盘（W3-U23 交付随仓 commit）；本 profile 闭包=锁文件口径＋冻结文本面＋compose 工件级 B/F 实拍（W3-U33 补跑）",
            "compose_artifact": scan,
        }

    result = {
        "tool": "tools/recon/PENDING_OWNER_e04_f77_release_license_closure.py",
        "unit": RUN_UNIT,
        "unit_note": "工件级补跑单 W3-U33；工具与 desktop 面首建=W3-U22（evidence 同目录 20261018 件）",
        "profile": args.profile,
        "run_utc": RUN_UTC,
        "oc28_head": subprocess.run(
            ["git", "-C", str(oc28), "rev-parse", "HEAD"], capture_output=True, check=True
        ).stdout.decode().strip(),
        "checks": ck.items,
        "snapshot": snapshot,
        "failures": ck.failures,
        "skips": [s["check"] for s in ck.skips],
    }

    evidence_dir = Path(args.evidence_dir) if args.evidence_dir else repo / "docs/construction/evidence/F77" / args.profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_json = evidence_dir / f"release-closure-{RUN_DATE}.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [
        f"# E04+F77 发行闭包实拍（{args.profile}，{RUN_UNIT}，{RUN_UTC}）",
        "",
        f"- oc28 HEAD：`{result['oc28_head']}`（tag v2.0.28）",
    ]
    for item in ck.items:
        lines.append(f"- **{item['result']}** {item['check']}：{item['detail']}")
    if ck.failures:
        lines.append(f"- 失败 {len(ck.failures)} 项 → exit 1")
    if ck.skips:
        lines.append(f"- 工件级未跑（如实挂账）={ck.skips}")
    (evidence_dir / f"release-closure-{RUN_DATE}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[e04-f77] profile={args.profile} checks={len(ck.items)} fail={len(ck.failures)} skip={len(ck.skips)}")
    print(f"[e04-f77] evidence={out_json}")
    return 1 if ck.failures else 0


if __name__ == "__main__":
    sys.exit(main())
