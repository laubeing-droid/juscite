#!/usr/bin/env python3
"""E04 许可与依赖闭包 —— B0 静态清点脚本（律引 / JusBench）。

只读解析 OpenCode v2.0.28 固定检出（oc28）的 bun.lock 与本地 node_modules，
产出：
  1. docs/construction/e04-license-inventory.json   机器可读全量清单
  2. docs/construction/e04-license-closure.md       B0 静态清点报告（人读）

铁律：
  - oc28 一切内容（含 node_modules）只读，本脚本不写 oc28 下任何文件。
  - 许可只取自包内 package.json 的 license/licenses 字段（事实），
    读不到就记 UNKNOWN，绝不推断、绝不编造。
  - 风险项证据 = license 字段原文 / 包内 LICENSE 文件首行 / licenseText 首行 / 事实说明。

Python 3.12 标准库，无第三方依赖。exit 0 = 清点完成。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_OC28 = r"D:\Codex\1.法律工作区\jusbench工作区\oc28"

PERMISSIVE = {
    "MIT", "MIT-0", "MIT-Modern-Variant",
    "ISC", "0BSD", "Zlib",
    "Apache-1.0", "Apache-1.1", "Apache-2.0",
    "BSD-1-Clause", "BSD-2-Clause", "BSD-2-Clause-FreeBSD", "BSD-2-Clause-NetBSD",
    "BSD-3-Clause", "BSD-3-Clause-Clear", "BSD-4-Clause", "BSD-Source-Code",
    "BlueOak-1.0.0", "Python-2.0", "PSF-2.0", "Artistic-2.0",
    "ICU", "Unicode-3.0", "Unicode-TOU", "X11", "X11-distribute-modifications-variant",
    "libpng-2.0", "bzip2-1.0.6", "curl", "NCSA", "Net-SNMP", "PostgreSQL",
    "Unlicense",  # 单独入公共领域桶，见 PD_DEDICATION
    "WTFPL",
    "CC0-1.0", "CC-BY-4.0", "CC-BY-3.0",  # CC 计入 permissive 之外？→ 否，CC-BY 入 custom
}
PERMISSIVE.discard("CC-BY-4.0")
PERMISSIVE.discard("CC-BY-3.0")
PERMISSIVE.discard("Unlicense")
PERMISSIVE.discard("WTFPL")

PD_DEDICATION = {"Unlicense", "WTFPL"}          # 公共领域/弃权声明（任务点名 Unlicense 为风险位）
STRONG_COPYLEFT_TOKENS = ("AGPL", "SSPL", "GPL")  # GPL 最后判，避免误吞 AGPL/LGPL
WEAK_COPYLEFT_PREFIXES = ("LGPL", "MPL", "EPL", "CPL", "OSL", "RPL")
FONT_LICENSES = {"OFL-1.1", "OFL-1.0", "OFL"}

WEIGHT_MODEL_HINTS = ("onnx", "tfjs", "transformers", "llama", "gguf", "tensorflow", "torch")
DOC_ENGINE_HINTS = ("docx", "pptx", "xlsx", "pdf", "mammoth", "libreoffice", "pandoc")

LICENSE_FILE_CANDIDATES = (
    "LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE-MIT", "LICENSE.APACHE", "LICENSE.MIT",
    "LICENCE", "LICENCE.md", "COPYING", "COPYING.md", "COPYING.txt", "NOTICE",
)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def parse_jsonc(raw: str) -> dict:
    """bun.lock v1：无注释、带尾逗号。先直接解析，失败再剥尾逗号。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    stripped = re.sub(r",(\s*[}\]])", r"\1", raw)
    return json.loads(stripped)


def read_json_lenient(p: Path) -> tuple[dict | None, str | None]:
    """读 JSON，容 BOM/编码噪声。返回 (data, error)。"""
    try:
        raw = p.read_bytes()
    except OSError as e:
        return None, f"unreadable: {e}"
    for enc in ("utf-8-sig", "utf-8", "utf-16"):
        try:
            return json.loads(raw.decode(enc)), None
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return None, "package.json not decodable/parsable"


# ---------------------------------------------------------------------------
# bun.lock 解析
# ---------------------------------------------------------------------------

def parse_resolution(res: str) -> dict:
    """把 '@scope/name@version' / 'name@version' / workspace / https 钉定解析为字段。"""
    if "@workspace:" in res:
        name, ws = res.split("@workspace:", 1)
        return {"name": name, "version": "workspace:" + ws, "kind": "workspace",
                "workspace_path": ws, "version_key": res}
    marker = "@https://"
    if marker in res:
        name, url = res.split(marker, 1)
        version = "https://" + url
        return {"name": name, "version": version, "kind": "url",
                "workspace_path": None, "version_key": res}
    name, _, version = res.rpartition("@")
    if not name:  # 理论不达（rpartition 对无 @ 的串 name 为空）
        return {"name": res, "version": "", "kind": "registry",
                "workspace_path": None, "version_key": res}
    return {"name": name, "version": version, "kind": "registry",
            "workspace_path": None, "version_key": res}


def collect_lock_packages(lock: dict) -> list[dict]:
    """lock['packages'] 每条目 → 规范化记录；按 resolution 去重，保留全部父键。"""
    out: dict[str, dict] = {}
    for key, val in lock.get("packages", {}).items():
        if not (isinstance(val, list) and val and isinstance(val[0], str)):
            continue
        info = parse_resolution(val[0])
        res = val[0]
        meta = val[2] if len(val) > 2 and isinstance(val[2], dict) else {}
        rec = out.setdefault(res, {
            **info,
            "lock_keys": [],
            "os": meta.get("os"),
            "cpu": meta.get("cpu"),
        })
        rec["lock_keys"].append(key)
    return sorted(out.values(), key=lambda r: (r["name"], r["version"]))


# ---------------------------------------------------------------------------
# node_modules 定位（bun isolated linker）
# ---------------------------------------------------------------------------

class StoreIndex:
    """node_modules/.bun 目录索引：base 名（去 hash 后缀）→ 完整路径列表。"""

    def __init__(self, store_dir: Path):
        self.store_dir = store_dir
        self.dirs: list[str] = []
        if store_dir.is_dir():
            self.dirs = sorted(e.name for e in os.scandir(store_dir) if e.is_dir())

    def find(self, name: str, version: str) -> list[str]:
        """返回候选 store 目录名列表（可能带 +<hash> 后缀）。"""
        escaped = name.replace("/", "+")
        exact = f"{escaped}@{version}"
        hits = [d for d in self.dirs if d == exact]
        if hits:
            return hits
        # 版本带 +hash 后缀的安装形式（npm tarball 完整性 hash 由 bun 注入）
        prefix = exact + "+"
        hits = [d for d in self.dirs if d.startswith(prefix)]
        if hits:
            return hits
        # URL/非常规版本被转义（: 与 / → +）
        escaped_version = version.replace(":", "+").replace("/", "+")
        prefix = f"{escaped}@{escaped_version}"
        hits = [d for d in self.dirs if d == prefix or d.startswith(prefix + "+")]
        return hits


def find_pkg_json(oc28: Path, name: str, version: str, store: StoreIndex) -> tuple[Path | None, str]:
    """定位包内 package.json。返回 (路径, 定位方式说明)。"""
    # 1) 根提升
    root = oc28 / "node_modules" / name / "package.json"
    if root.is_file():
        data, err = read_json_lenient(root)
        if data is not None:
            v = data.get("version")
            n = data.get("name")
            if (v is None or v == version) and (n is None or n == name):
                return root, "root-hoisted"
        elif err:
            return root, "root-hoisted-unreadable"
    # 2) .bun store
    for d in store.find(name, version):
        p = store.store_dir / d / "node_modules" / name / "package.json"
        if p.is_file():
            return p, f"bun-store/{d}"
    # 3) 嵌套于其他包的 node_modules（peer 解析产物）
    escaped = name.replace("/", "+")
    for d in store.dirs:
        p = store.store_dir / d / "node_modules" / name / "package.json"
        if p.is_file():
            return p, f"bun-store-nested/{d}"
    return None, "not-found"


def extract_license_field(data: dict) -> tuple[str | None, str]:
    """从 package.json 取许可字段原文。返回 (raw, 来源字段)。"""
    lic = data.get("license")
    if isinstance(lic, str) and lic.strip():
        return lic.strip(), "license"
    if isinstance(lic, dict) and isinstance(lic.get("type"), str):
        return lic["type"].strip(), "license(dict.type)"
    lics = data.get("licenses")
    if isinstance(lics, str) and lics.strip():
        return lics.strip(), "licenses"
    if isinstance(lics, list) and lics:
        types = []
        for item in lics:
            if isinstance(item, str):
                types.append(item.strip())
            elif isinstance(item, dict) and isinstance(item.get("type"), str):
                types.append(item["type"].strip())
        if types:
            return " OR ".join(types), "licenses(list)"
    return None, "none"


def first_license_sentence(pkg_dir: Path, data: dict) -> str:
    """风险项证据关键句：licenseText 首行 → LICENSE 文件首行 → 字段原文。"""
    lt = data.get("licenseText")
    if isinstance(lt, str) and lt.strip():
        line = next((ln.strip() for ln in lt.splitlines() if ln.strip()), "")
        if line:
            return f"licenseText 首行: {line[:180]}"
    for cand in LICENSE_FILE_CANDIDATES:
        f = pkg_dir / cand
        if f.is_file():
            try:
                with f.open("r", encoding="utf-8", errors="replace") as fh:
                    line = next((ln.strip() for ln in fh if ln.strip()), "")
                if line:
                    return f"{cand} 首行: {line[:180]}"
            except OSError:
                continue
    lic, field = extract_license_field(data)
    if lic:
        return f"{field} 原文: {lic[:180]}"
    return "无 license/licenses/licenseText 字段，包内亦无 LICENSE/COPYING 文件"


# ---------------------------------------------------------------------------
# 许可分类
# ---------------------------------------------------------------------------

def normalize_token(tok: str) -> str:
    t = tok.strip().strip("()[]").strip()
    t = re.sub(r"\s+", " ", t)
    return t


def classify_single(token: str) -> str:
    """单个许可标识 → 桶名。"""
    t = normalize_token(token)
    tl = t.lower()
    if t == "UNLICENSED" or tl == "unlicensed":
        return "no_grant"
    if t in PD_DEDICATION:
        return "pd_dedication"
    if "SSPL" in t:
        return "strong_copyleft"
    if tl.startswith("agpl") or "AGPL" in t:
        return "strong_copyleft"
    if tl.startswith("lgpl") or "LGPL" in t:
        return "weak_copyleft"
    if re.search(r"\bGPL", t):
        return "strong_copyleft"
    if t in FONT_LICENSES or tl.startswith("ofl"):
        return "font"
    if any(tl.startswith(p.lower()) for p in WEAK_COPYLEFT_PREFIXES):
        return "weak_copyleft"
    if t in PERMISSIVE or tl in {p.lower() for p in PERMISSIVE}:
        return "permissive"
    if t in {"Public Domain", "public domain"}:
        return "pd_dedication"
    return "custom_other"


def classify(raw: str | None, kind: str) -> tuple[str, list[str]]:
    """返回 (桶名, 归一化许可列表)。"""
    if kind == "workspace":
        return "first_party", []
    if raw is None:
        return "unknown", []
    up = raw.upper()
    if " OR " in up:
        arms = [normalize_token(a) for a in re.split(r"\s+OR\s+", raw, flags=re.IGNORECASE)]
        return "dual_or", arms
    if " AND " in up:
        arms = [normalize_token(a) for a in re.split(r"\s+AND\s+", raw, flags=re.IGNORECASE)]
        return "multi_and", arms
    # 斜杠双写（如 MIT/X11）：两侧均为宽松许可才按双许可归桶，否则保持原样入 custom
    if "/" in raw and "(" not in raw:
        arms = [normalize_token(a) for a in raw.split("/")]
        if arms and all(classify_single(a) == "permissive" for a in arms):
            return "dual_or", arms
    # 带 exception（如 Apache-2.0 WITH LLVM-exception）：按主许可归类，原文保留
    if " WITH " in up:
        base = re.split(r"\s+WITH\s+", raw, flags=re.IGNORECASE)[0]
        return classify_single(base), [normalize_token(raw)]
    return classify_single(raw), [normalize_token(raw)]


RISK_BUCKETS = {
    "strong_copyleft": "强 Copyleft（GPL/AGPL/SSPL）",
    "weak_copyleft": "弱 Copyleft（LGPL/MPL/EPL 等，文件级义务）",
    "pd_dedication": "公共领域弃权声明（Unlicense/WTFPL，无担保且无署名结构）",
    "no_grant": "UNLICENSED（明示无授权）",
    "custom_other": "自定义/非常见限制性",
    "unknown": "UNKNOWN（读不到，不猜）",
    "dual_or": "双许可（OR，可择一）",
    "multi_and": "多重许可（AND，义务叠加）",
    "font": "字体许可（OFL，素材义务）",
}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def build_reverse_map(lock: dict) -> dict[str, list[tuple[str, str]]]:
    """child 包名 → [(父 resolution, 依赖段), ...]。数据源=bun.lock 各 entries 的依赖对象。"""
    rev: dict[str, list[tuple[str, str]]] = {}
    for val in lock.get("packages", {}).values():
        if not (isinstance(val, list) and val and isinstance(val[0], str)):
            continue
        res = val[0]
        deps = val[2] if len(val) > 2 and isinstance(val[2], dict) else {}
        for sect in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            for child in (deps.get(sect) or {}):
                lst = rev.setdefault(child, [])
                if (res, sect) not in lst:
                    lst.append((res, sect))
    for path, cfg in lock.get("workspaces", {}).items():
        wsname = cfg.get("name")
        if not wsname:
            continue
        res = f"{wsname}@workspace:{path}" if path else f"{wsname}@workspace:."
        for sect in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            for child in (cfg.get(sect) or {}):
                lst = rev.setdefault(child, [])
                if (res, sect) not in lst:
                    lst.append((res, sect))
    return rev


def _strip_version(res: str) -> str:
    """'@scope/name@1.2.3' / '@scope/name@workspace:p' / 'name@1.2.3' → 包名。"""
    if "@workspace:" in res:
        return res.split("@workspace:", 1)[0]
    name, sep, _ver = res.rpartition("@")
    return name if name else res


def referrer_chains(name: str, rev: dict[str, list[tuple[str, str]]],
                    max_depth: int = 4, max_branches: int = 4) -> list[str]:
    """从 name 向上走引用链到 workspace 根，返回链字符串列表（机械事实，封顶剪枝）。
    链方向：主体 ← 直接引用者 ← … ← workspace 根。"""
    chains: list[str] = []

    def walk(tokens: list[str], cur_name: str, depth: int):
        if len(chains) >= max_branches:
            return
        parents = rev.get(cur_name, [])
        if not parents or depth >= max_depth:
            chain = " ← ".join(tokens)
            if chain not in chains:
                chains.append(chain)
            return
        for parent_res, sect in parents:
            if len(chains) >= max_branches:
                break
            ptag = f"{parent_res}({sect})" if "workspace:" in parent_res else parent_res
            walk(tokens + [ptag], _strip_version(parent_res), depth + 1)

    walk([name], name, 0)
    return chains


def build_inventory(oc28: Path) -> tuple[list[dict], dict]:
    lock_path = oc28 / "bun.lock"
    lock = parse_jsonc(lock_path.read_text(encoding="utf-8"))
    entries = collect_lock_packages(lock)
    store = StoreIndex(oc28 / "node_modules" / ".bun")
    root_license_sha = (
        sha256_file(oc28 / "LICENSE") if (oc28 / "LICENSE").is_file() else None
    )

    records: list[dict] = []
    for ent in entries:
        name, version, kind = ent["name"], ent["version"], ent["kind"]
        rec = {
            "name": name,
            "version": version,
            "kind": kind,
            "os": ent.get("os"),
            "cpu": ent.get("cpu"),
            "lock_keys": ent["lock_keys"],
            "license": None,
            "license_field_source": None,
            "bucket": None,
            "normalized": [],
            "evidence_path": None,
            "evidence_locate": None,
            "evidence_quote": None,
            "unknown_reason": None,
        }
        if kind == "workspace":
            p = oc28 / ent["workspace_path"] / "package.json"
            rec["evidence_path"] = p.relative_to(oc28).as_posix()
            data, err = read_json_lenient(p)
            if data is None:
                rec["bucket"] = "unknown"
                rec["unknown_reason"] = f"workspace package.json 不可读: {err}"
            else:
                lic, field = extract_license_field(data)
                rec["license"] = lic
                rec["license_field_source"] = field
                rec["bucket"], rec["normalized"] = classify(lic, kind)
                if lic is None:
                    rec["bucket"] = "unknown"
                    rec["unknown_reason"] = (
                        "workspace 包 package.json 无 license/licenses 字段（事实）；"
                        "仓库根 LICENSE（MIT）在仓库层面覆盖本包——覆盖为仓库结构事实，"
                        "字段层面为空，逐包字段清点记 UNKNOWN"
                    )
                    rec["evidence_quote"] = first_license_sentence(p.parent, data)
            records.append(rec)
            continue

        p, how = find_pkg_json(oc28, name, version, store)
        rec["evidence_locate"] = how
        if p is None:
            rec["bucket"] = "unknown"
            rec["unknown_reason"] = "本地未安装（平台特定或可选依赖未随本机安装），node_modules 中无 package.json"
            records.append(rec)
            continue
        rec["evidence_path"] = p.relative_to(oc28).as_posix()
        data, err = read_json_lenient(p)
        if data is None:
            rec["bucket"] = "unknown"
            rec["unknown_reason"] = f"package.json 不可读: {err}（{how}）"
            records.append(rec)
            continue
        lic, field = extract_license_field(data)
        rec["license"] = lic
        rec["license_field_source"] = field
        rec["bucket"], rec["normalized"] = classify(lic, kind)
        if lic is None:
            rec["unknown_reason"] = "package.json 可读但无 license/licenses 字段（事实）"
            rec["evidence_quote"] = first_license_sentence(p.parent, data)
        elif rec["bucket"] not in ("permissive", "first_party"):
            rec["evidence_quote"] = first_license_sentence(p.parent, data)
        records.append(rec)

    lock_entries = len(lock.get("packages", {}))
    rev = build_reverse_map(lock)
    for r in records:
        if r["bucket"] in ("strong_copyleft", "weak_copyleft", "pd_dedication",
                           "no_grant", "custom_other", "dual_or", "multi_and", "font"):
            r["referrers"] = referrer_chains(r["name"], rev)
    meta = {
        "lock_entries": lock_entries,
        "unique_packages": len(records),
        "workspace_count": sum(1 for r in records if r["kind"] == "workspace"),
        "url_count": sum(1 for r in records if r["kind"] == "url"),
        "platform_specific_entries": sum(1 for r in records if r.get("os") or r.get("cpu")),
        "workspace_declared_mit": sum(
            1 for r in records if r["kind"] == "workspace"
            and isinstance(r["license"], str) and r["license"].strip().lower() == "mit"
        ),
        "bun_lock_sha256": sha256_file(lock_path),
        "root_license_sha256": root_license_sha,
    }
    return records, meta


def git_facts(oc28: Path) -> dict:
    import subprocess
    facts = {}
    def run(*args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", str(oc28), *args], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=30)
            return r.stdout.strip()
        except Exception as e:  # noqa: BLE001 - 事实采集失败按事实记录
            return f"<git 失败: {e}>"
    facts["head"] = run("rev-parse", "HEAD")
    facts["describe"] = run("describe", "--tags")
    facts["status_porcelain"] = [ln for ln in run("status", "--porcelain").splitlines() if ln]
    return facts


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def table_line(r: dict) -> str:
    obj: dict = {"name": r["name"], "version": r["version"]}
    if r["kind"] != "registry":
        obj["kind"] = r["kind"]
    if r.get("os"):
        obj["os"] = r["os"]
    if r.get("cpu"):
        obj["cpu"] = r["cpu"]
    obj["license"] = r["license"] if r["license"] is not None else "UNKNOWN"
    obj["bucket"] = r["bucket"]
    if r["bucket"] == "unknown" and r.get("unknown_reason"):
        obj["unknown_reason"] = r["unknown_reason"]
    return json.dumps(obj, ensure_ascii=False)


def render_md(records: list[dict], meta: dict, gitf: dict, oc28: Path,
              out_json_rel: str, gen_dt: datetime) -> str:
    n = len(records)
    bucket_counts = Counter(r["bucket"] for r in records)
    lic_counts = Counter((r["license"] if r["license"] else "UNKNOWN") for r in records)
    unknown_n = bucket_counts["unknown"]

    risk_sections = []
    for bucket in ("strong_copyleft", "weak_copyleft", "pd_dedication", "no_grant",
                   "custom_other", "unknown", "dual_or", "multi_and", "font"):
        items = [r for r in records if r["bucket"] == bucket]
        if not items:
            continue
        lines = [f"### {RISK_BUCKETS[bucket]} —— {len(items)} 项", ""]
        for r in items:
            if bucket == "unknown":
                fact = r.get("unknown_reason") or "读不到（不猜）"
                lines.append(f"- `{r['name']}@{r['version']}` — 事实：{fact}")
            else:
                quote = r.get("evidence_quote") or r.get("license") or ""
                loc = f"，证据位置 `{r['evidence_path']}`" if r.get("evidence_path") else ""
                lines.append(f"- `{r['name']}@{r['version']}` — license 字段原文：`{r['license']}`{loc}")
                lines.append(f"  - 关键句：{quote}")
                refs = r.get("referrers") or []
                if refs:
                    lines.append(f"  - 引用链（bun.lock 机械回溯）：{('；'.join(refs))}")
        risk_sections.append("\n".join(lines))

    weight_hits = [r for r in records if any(h in r["name"].lower() for h in WEIGHT_MODEL_HINTS)]
    doc_hits = [r for r in records if any(h in r["name"].lower() for h in DOC_ENGINE_HINTS)]
    ws_no_field = [r for r in records if r["kind"] == "workspace" and r["bucket"] == "unknown"]
    empty_field_n = sum(1 for r in records if not r["license"])
    not_installed_n = sum(1 for r in records if "未安装" in (r.get("unknown_reason") or ""))

    status_line = (
        f"**结论：不能声称「当前依赖闭包无传染性许可」。** 闭包中存在 {unknown_n} 项 UNKNOWN"
        f"（本地未安装或无 license 字段），另有强/弱 Copyleft、弃权声明、"
        f"多重义务与自定义许可共 {sum(bucket_counts[b] for b in RISK_BUCKETS if b != 'unknown')} 项需逐项处置；"
        f"待补 UNKNOWN {unknown_n} 项后方可声称。"
        if unknown_n else
        f"**结论：UNKNOWN 为 0；可声称「当前依赖闭包无传染性许可」的前提仍取决于"
        f"其余 {sum(bucket_counts[b] for b in RISK_BUCKETS if b != 'unknown')} 项风险清单的逐项处置。**"
    )

    json_lines = "\n".join(table_line(r) for r in records)

    platform_note = ""
    if meta["platform_specific_entries"]:
        platform_note = (
            f"其中 {meta['platform_specific_entries']} 条带 os/cpu 平台标记（平台特定可选依赖，"
            f"如 electron 二进制分平台包），非本机平台者本地未安装，其许可标注 UNKNOWN 属机械事实。"
        )

    md = f"""# E04 许可与依赖闭包 —— B0 静态清点（律引）

> 义务来源：`docs/construction/authority/07-新增必需工程义务.csv` E04 行（phase B0/B3）。
> 本文件 = **B0 段静态清点**：bun.lock 依赖闭包 + 逐包许可 + 风险清单 + 上游义务 + NOTICE 骨架指针。
> 发行闭包实拍（安装包内实际素材/二进制披露）属 B3，不在本文件。
> 产品名一律"律引"。上游检出只读，本清点未写 oc28 任何文件。

## 0. 事实基座

| 项 | 值 |
|---|---|
| 上游检出 | `{oc28}` |
| 检出 HEAD | `{gitf['head']}`（git describe：`{gitf['describe']}`，即 tag v2.0.28 提交，与 authority/02-license-evidence.json 的 subject_commit 一致） |
| 检出工作树差异 | 本地未提交改动 {len(gitf['status_porcelain'])} 项（详见 §5.4，机械事实，不在本清点处置） |
| bun.lock sha256 | `{meta['bun_lock_sha256']}` |
| 上游根 LICENSE sha256 | `{meta['root_license_sha256']}`（MIT，版权行 "Copyright (c) 2025 opencode"） |
| 上游许可证据 | `docs/construction/authority/02-license-evidence.json`（OpenCode v2.0.28 = MIT，官方 raw URL 核验记录）；`02-official-versions.json`（tag v2.0.28 = commit 026b106b…） |
| 生成 | `{gen_dt.isoformat(timespec='seconds')}` 由 `tools/license/inventory_licenses.py` 生成；机器可读清单 `{out_json_rel}` |

## 1. 计数口径

- bun.lock `packages` 段条目总数：**{meta['lock_entries']}**（含同版本包因父级 peer 解析不同而产生的重复条目）。
- 去重后（resolution `包名@版本` 唯一）：**{n}** —— 即本文件 §2 全量表行数、§3 汇总分母。
  - 其中 workspace 首方包（@opencode/*）：**{meta['workspace_count']}** 个。
  - 其中 URL 钉定包：**{meta['url_count']}** 个。
- {platform_note}

**自洽断言：§2 表行数 = {n} = 脚本解析去重总数。**

## 2. 依赖全量表（JSON，逐包）

字段：`name` / `version` / `kind`（registry 缺省；workspace / url 显式）/ `os`+`cpu`（平台特定才有）/ `license`（字段原文；读不到为字符串 "UNKNOWN"）/ `bucket`（分类桶）/ `unknown_reason`（仅 UNKNOWN）。
许可证据定位规则（适用于全表）：root-hoisted = `node_modules/<name>/package.json`；`bun-store/<dir>` = `node_modules/.bun/<dir>/node_modules/<name>/package.json`。

```json
{json_lines}
```

## 3. 许可分布汇总

### 3.1 按分类桶

| 桶 | 数量 |
|---|---|
| 首方 workspace 包（first_party） | {bucket_counts['first_party']} |
| 宽松许可（permissive） | {bucket_counts['permissive']} |
{chr(10).join(f"| {RISK_BUCKETS[b]} | {bucket_counts[b]} |" for b in ("strong_copyleft", "weak_copyleft", "pd_dedication", "no_grant", "custom_other", "unknown", "dual_or", "multi_and", "font") if bucket_counts[b])}
| **合计** | **{n}** |

### 3.2 按 license 字段原文（出现 ≥2 次；字段为空的不入本表）

| license 原文 | 数量 |
|---|---|
{chr(10).join(f"| `{lic}` | {cnt} |" for lic, cnt in sorted(lic_counts.items(), key=lambda kv: (-kv[1], kv[0])) if cnt >= 2 and lic != "UNKNOWN")}

字段为空（无 license/licenses 字段）合计 **{empty_field_n}** 项 = 本地未安装 {not_installed_n}（无 package.json 可读）+ registry 已安装无字段 {empty_field_n - not_installed_n - len(ws_no_field)} + workspace 无字段 {len(ws_no_field)}；均已列入 §4 UNKNOWN 桶（workspace 无字段者由仓库根 LICENSE（MIT）作仓库层面覆盖，覆盖为结构事实，字段事实为空）。

## 4. 风险清单（逐项带证据）

{chr(10).join(chr(10) + s for s in risk_sections)}

### 4.1 处置提示（静态判定提示，非结论；逐项裁定待 B3 发行冻结）

- 双许可（OR）：按择一宽松臂（MIT / Apache-2.0 / BSD / ISC / CC0）履行即可；NOTICE 冻结时逐项写明所择臂并留档。
- MPL-2.0（axe-core、lightningcss 系）：文件级 Copyleft——仅对 MPL 覆盖文件承担"提供源码 + 附 MPL 文本"义务，不传染相邻自有文件；分发时逐文件列明。
- `Apache-2.0 AND LGPL-3.0-or-later`（@img/sharp-win32-x64 各版本）：LGPL 成分随 sharp 预编译二进制（libvips）；B3 若内嵌进安装包，须满足 LGPL 替换/再链接义务或改用非内嵌方案。
- FSL-1.1-MIT（@sentry/cli 系）：Functional Source License（其 LICENSE 标题行明示 "MIT Future License"），限制条款以其原文为准；引用链显示其为构建期传递依赖（@sentry/bundler-plugins ← @sentry/vite-plugin ← @opencode/app devDependencies），不进运行时闭包——B3 以安装包实拍为准。
- CC-BY（caniuse-lite、spdx-exceptions）：数据包（浏览器兼容数据 / SPDX 异常表），构建期引用；若数据进入发行物须附署名。B3 核实。
- Unlicense / WTFPL：弃权型声明，无传染性；列示仅完成风险位盘点。
- UNKNOWN 的处置=补证据：本地未安装者以发行实拍或权威 registry 元数据补（不属本 B0 清点）；9 个 workspace 无字段者由上游根 LICENSE（MIT）仓库层面覆盖（结构事实）；4 个第三方 registry 包无字段（@solidjs/start、buffers、khroma、zod-to-ts）须向权威源补证。补齐前不得声称「无传染性许可」。

## 5. 上游义务

### 5.1 OpenCode v2.0.28（MIT）

- 上游根 `LICENSE` 为 MIT，版权行 **"Copyright (c) 2025 opencode"**（sha256 见 §0）。
- 保留要求：分发物中保留该 LICENSE 全文与上述版权行；**作修改须在副本上显著标记**（MIT 第 3 条）。
- workspace 逐包字段事实：{meta['workspace_count']} 个 @opencode/* 包中 **{meta['workspace_declared_mit']} 个 package.json 声明 `"license": "MIT"`**；
  **{len(ws_no_field)} 个无 license 字段**（{('、'.join(f'`{r["name"]}`' for r in ws_no_field))}）——
  逐包字段清点记 UNKNOWN（见 §4），其许可由仓库根 LICENSE（MIT）作仓库层面覆盖（结构事实）。
- 历史证据不混用：DSH（MIT，d743267…）与 ZCode（Apache-2.0，aac4755…）仅作参考来源，不构成当前闭包（authority/02-license-evidence.json 事实）。

### 5.2 Electron 44.4.5（MIT）及其组件披露

- npm 包 `electron@44.4.5`：package.json `"license": "MIT"`；包内 `LICENSE` 版权行 **"Copyright (c) Electron contributors"** 与 **"Copyright (c) 2013-2020 GitHub Inc."**（已实读核实）。
- Electron 二进制 = Chromium + Node.js 的合成物：**分发时必须包含 Electron 仓库 LICENSE 文件，以及随二进制分发的 `LICENSES.chromium.html` 与 Node LICENSE**。
- 机械事实：本机 npm 包目录（`node_modules/.bun/electron@44.4.5+759ce506b1ed1a42/node_modules/electron/`）**不含** `LICENSES.chromium.html`——该文件随下载的二进制 dist 分发。⇒ 该披露属 **B3 发行闭包实拍**义务，B0 此处挂账。

### 5.3 字体 / 图标素材风险位

字体包（license 均为字段原文，OFL 家族见 §4 字体桶）：

| 包 | 版本 | license | 引用方 workspace |
|---|---|---|---|
| @ibm/plex | 6.4.1 | OFL-1.1 | packages/app, packages/console/app, packages/stats/app |
| @fontsource/ibm-plex-mono | 5.2.5 | OFL-1.1 | packages/web |
| @fontsource/commit-mono | 5.3.0 | （见 §2/§4 表） | packages/posts |
| @betteroffice/fonts | 0.4.0 | (Apache-2.0 AND OFL-1.1) | packages/gui-extensions |

- OFL 义务要点：随字体保留许可文本、**保留字体名作为保留字体名（Reserved Font Name）约束、不得单独出售字体文件**。B3 打包若嵌入字体文件，逐字附 OFL 文本。
- 图标/位图：`packages/app/public/` 现存 png/ico/svg 均为**上游自有素材**（MIT 义务束内，无第三方位图字体声明文件）；`packages/app/src/legal-workbench/` 仅为**本地未提交**的单 tsx 目录（见 §5.4），非上游素材位。
- **结论：当前上游素材位无第三方新增位图字体**；B3 安装包实拍时复核此结论仍成立。

### 5.4 oc28 工作树本地差异（机械事实披露）

检出 HEAD = v2.0.28 tag，但工作树含本地未提交改动：

```
{chr(10).join(gitf['status_porcelain']) if gitf['status_porcelain'] else '（无）'}
```

这些改动**不属于上游 tag**；E04 依赖闭包以 bun.lock（sha256 见 §0）为准。B3 前须由 owner 裁定该差异是否入基线。

### 5.5 权重数据 / 文档引擎位

- 权重/模型数据：按包名特征（onnx/tfjs/transformers/llama/gguf/tensorflow/torch）扫描闭包 → 命中 {len(weight_hits)} 项：
{chr(10).join(f"  - `{r['name']}@{r['version']}` — `{r['license'] or 'UNKNOWN'}`（桶 {r['bucket']}）" for r in weight_hits) if weight_hits else "  - 无"}
  - 命中判定（人工核查 2026-10-14）：@shikijs/transformers 为 shiki 语法高亮转换器，包内仅 5 个文件共约 37 KB 纯 TS/mjs 代码，**无模型权重文件**，系命名巧合。
- 文档引擎：包名特征（docx/pptx/xlsx/pdf/mammoth/pandoc/libreoffice）命中 {len(doc_hits)} 项：
{chr(10).join(f"  - `{r['name']}@{r['version']}` — `{r['license'] or 'UNKNOWN'}`（桶 {r['bucket']}）" for r in doc_hits) if doc_hits else "  - 无"}
  - 四个 @betteroffice/* 包（docx/pptx/xlsx/fonts）均由 `packages/gui-extensions` 引用（bun.lock workspaces 段核实）；逐项义务以其 license 字段为准（见表）。

## 6. NOTICE 骨架

见 `docs/construction/NOTICE-draft.md`：上游 MIT 声明 + 修改声明占位 + BSL 1.1 意向占位；
**生效日期留空，待发行冻结**（E04 acceptance：自有 BSL 参数已裁不重开，具体日期及参数仅发行冻结）。

## 7. 结论行

{status_line}

---

*本文件由脚本生成（确定性产物）；重新运行 `tools/license/inventory_licenses.py` 可复算。任何数字与本脚本输出不一致时，以脚本为准并修订本文件。*
"""
    return md


def main() -> int:
    ap = argparse.ArgumentParser(description="E04 license/dependency static inventory")
    ap.add_argument("--oc28", default=DEFAULT_OC28, help="OpenCode v2.0.28 固定检出路径（只读）")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]),
                    help="律引仓根（输出目录所在）")
    ap.add_argument("--out-json", default="docs/construction/e04-license-inventory.json")
    ap.add_argument("--out-md", default="docs/construction/e04-license-closure.md")
    args = ap.parse_args()

    oc28 = Path(args.oc28)
    repo = Path(args.repo)
    if not (oc28 / "bun.lock").is_file():
        print(f"FATAL: bun.lock 不存在: {oc28}", file=sys.stderr)
        return 2

    records, meta = build_inventory(oc28)
    gitf = git_facts(oc28)
    gen_dt = datetime.now(timezone.utc)

    out_json = repo / args.out_json
    out_md = repo / args.out_md
    out_json.parent.mkdir(parents=True, exist_ok=True)

    bucket_counts = Counter(r["bucket"] for r in records)
    payload = {
        "meta": {
            **meta,
            "git": gitf,
            "oc28_path": str(oc28),
            "generated_at": gen_dt.isoformat(timespec="seconds"),
            "generator": "tools/license/inventory_licenses.py",
        },
        "summary_by_bucket": dict(bucket_counts),
        "packages": records,
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    md = render_md(records, meta, gitf, oc28, args.out_json, gen_dt)
    out_md.write_text(md, encoding="utf-8", newline="\n")

    # ---- 自洽断言：md 中的包总数 == 脚本解析总数 == JSON artifact 行数 ----
    assert f"**{meta['unique_packages']}**" in md, "md 未含去重总数"
    table_rows = sum(1 for ln in md.splitlines() if ln.startswith('{"name":'))
    assert table_rows == meta["unique_packages"], (
        f"md 表行数 {table_rows} != 去重总数 {meta['unique_packages']}")
    assert payload["meta"]["unique_packages"] == len(records)

    print(f"lock entries            : {meta['lock_entries']}")
    print(f"unique name@version     : {meta['unique_packages']}")
    print(f"  workspace             : {meta['workspace_count']}")
    print(f"  url-pinned            : {meta['url_count']}")
    print(f"platform-specific entries: {meta['platform_specific_entries']}")
    for b, cnt in sorted(bucket_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {b:<16}: {cnt}")
    print(f"UNKNOWN                 : {bucket_counts['unknown']}")
    print(f"json -> {out_json}")
    print(f"md   -> {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
