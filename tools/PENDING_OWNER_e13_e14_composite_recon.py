#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W3-U25 E13+E14 复合收口对账——逐行复跑 W2b 已 VERIFIED 面 recon 全集。

工单 W3-U25 验收命令（唯一入口，本工具不新造任何领域语义）：

    python -X utf8 tools/PENDING_OWNER_e13_e14_composite_recon.py
        [--profile desktop --profile selfhost]   # 透传给逐行工具（默认双 profile）
        [--only e13|e14]                          # 只跑单链（默认两链全跑）
        [--list]                                  # 只列登记行不执行

登记纪律（工单明文）：逐行登记 command/cwd/subject/exit——
  - 每行 = 一次真实子进程复跑（本 worktree 根为 cwd，python -X utf8）；
  - subject 记该行覆盖的 acceptance-ledger.csv obligation_id 实例与其
    VERIFIED 首验出处（W2b/W2a 工单），不新造语义；
  - exit 取真实退出码，绝不改写——0=PASS；2=RECON_FAIL（具名）；
    3=BLOCKED_ENV_NAMED（环境缺失）。缺面如实具名，不补 PASS。

链与覆盖（工单原文两链）：
  E13 提案/修订/回流链：
      F47 / F48 / F49 / F46-wps+F52-wps / F17-wps / F50+F51 / F53
  E14 引文-抽取-列-双集链（顺序纪律＝07 E14：引文/支持服务→抽取接线→列→
      租约/generation→双集；F25 行内即租约/generation 竞争负测）：
      F70 / F87 / F82(tabular core) / F25 / F88

聚合判定：链 RECON_OK ⇔ 该链全部行 exit 0。任一行非零 ⇒ 复合退出码 2，
失败行在 JSON/MD 中具名（含 stdout 尾部），不静默不代偿。

边界如实：
  - F46-wps/F52-wps 行复用 W2b-U36 的 recon（其 c16 自建复杂件域保真检在
    2026-10-17 后本机 WPS 上存在预存宿主漂移败相——W2b-U49 A/B 探针实证
    main@e9a1fd4 原工具原面同败。若本跑复现，按真实 exit 记 FAIL_NAMED 并
    注明该在案结论，不补 PASS 不改台账行）。
  - F82 行只复跑 F82-core recon（F82-desktop/selfhost/列/溯源 四实例的
    VERIFIED 面）；F82-复核/重跑/人改（w2b-u31 review-ops 面）不在工单两链
    枚举内，本工具不跑、如实不称覆盖。
  - 各行工具自身写各自的 evidence/Fxx/<profile>/；本工具把本轮新生成的
    证据文件复制进 evidence/E13/<profile>/<face>/ 与 evidence/E14/<profile>/<face>/
    使两目录自足，并写复合 JSON/MD。
  - 台账 E13/E14 两行状态由主控按本证据落账（工单明文），本工具不改台账。

退出码：0 = 所跑行全部 exit 0；1 = 用法错误；2 = 任一行非零（具名）。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

PROFILES = ("desktop", "selfhost")


def profiles_args(names):
    out = []
    for name in names:
        out += ["--profile", name]
    return out


# ---------------------------------------------------------------------- #
# 登记行（subject/expected 摘自 acceptance-ledger.csv 对应 VERIFIED 行）
# ---------------------------------------------------------------------- #

LINES = [
    # ---------------- E13 提案/修订/回流链 ----------------
    {
        "line_id": "F47",
        "chain": "E13",
        "tool": "tools/PENDING_OWNER_f47_proposal_bake_recon.py",
        "covers": ["F47-desktop", "F47-selfhost"],
        "first_verified": "W2b-U11（台账 VERIFIED；harness w2b-u11@88bf1757）",
        "assertion": "提案/base/canonical 分开；reject/superseded 区分；确认才登记新干净版本",
    },
    {
        "line_id": "F48",
        "chain": "E13",
        "tool": "tools/PENDING_OWNER_f48_edits_protocol_recon.py",
        "covers": ["F48-desktop", "F48-selfhost"],
        "first_verified": "W2b-U12（台账 VERIFIED；harness w2b-u11 面）",
        "assertion": "流式 edit 唯一 quote 定位；insert/删除真修订；重载 DB 与书签对账以实际文档为准",
    },
    {
        "line_id": "F49",
        "chain": "E13",
        "tool": "tools/PENDING_OWNER_f49_replay_redline_recon.py",
        "covers": ["F49-desktop", "F49-selfhost"],
        "first_verified": "W2b-U14（台账 VERIFIED；产物红线 DOCX consumers=E13-docx-closeout）",
        "assertion": "干净基版与提案 replay 对比产真修订；表格/脚注/编号有内容回读",
    },
    {
        "line_id": "F46-wps+F52-wps",
        "chain": "E13",
        "tool": "tools/PENDING_OWNER_f46_f52_wps_host_recon.py",
        "covers": ["F46-wps", "F52-wps"],
        "evidence_dirs": ["F46", "F52"],
        "first_verified": "W2b-U36（台账 VERIFIED；真 WPS COM KWPS.Application 12.1.0.28802）",
        "assertion": "WPS 宿主原生修订→部分接受/拒绝→重读实际文件→CAS/version 回流；未接受不改 canonical；索引 basis 失效",
        "known_env": "c16 域保真检曾记宿主漂移败相三跑在案（W2b-U49 A/B 探针："
                     "main@e9a1fd4 原工具原面同败）；W3-U35 根因钉定＝同 build "
                     "宿主 open 即重算 DATE 域（缓存 2026-10-16→当日形，指令/"
                     "格式开关逐字保真，探针 evidence/E13/patch-chain/）＝表示形"
                     "漂移非真域丢失，断言已按 W2b-U36 语义合同（指令＋结果文本"
                     "俱在）收敛，缓存字面值不再钉死",
    },
    {
        "line_id": "F17-wps",
        "chain": "E13",
        "tool": "tools/PENDING_OWNER_f17_wps_host_surface_recon.py",
        "covers": ["F17-wps"],
        "first_verified": "W2b-U50（台账 VERIFIED；F17-word NOT_RUN 挂 §6.1 裁决#4 回收点）",
        "assertion": "原生前端栈复用 WPS 宿主面：宿主内承载原生 UI，不建第二 DOCX 编辑器",
    },
    {
        "line_id": "F50+F51",
        "chain": "E13",
        "tool": "tools/PENDING_OWNER_f50_f51_reanchor_verbatim_recon.py",
        "covers": ["F50-desktop", "F50-selfhost", "F51-desktop", "F51-selfhost"],
        "evidence_dirs": ["F50", "F51"],
        "first_verified": "W2b-U13（台账 VERIFIED）",
        "assertion": "插入后按原文重锚仍定位正确；零/多命中不以偏移强改；引用逐字定位成功才改，NOT_FOUND 拒自动修改并给人工入口",
    },
    {
        "line_id": "F53",
        "chain": "E13",
        "tool": "tools/PENDING_OWNER_f53_author_decision_recon.py",
        "covers": ["F53-desktop", "F53-selfhost"],
        "first_verified": "W2b-U49（台账 VERIFIED；harness w2b-u31 只读）",
        "assertion": "修订 author 与真实来源匹配不伪装律师；律师接受带真实决定引用，保对外可见策略",
    },
    # ---------------- E14 引文-抽取-列-双集链 ----------------
    {
        "line_id": "F70-desktop",
        "chain": "E14",
        "tool": "tools/PENDING_OWNER_f70_citation_verifier_recon.py",
        "tool_args": ["--profile", "desktop"],
        "covers": ["F70-desktop"],
        "first_verified": "W2a-U14（台账 VERIFIED；codices 冻结面 v1.1）",
        "assertion": "单引用/全文所有引用逐条范围记账；虚构/失效/误引不能标全核",
    },
    {
        "line_id": "F70-selfhost",
        "chain": "E14",
        "tool": "tools/PENDING_OWNER_f70_citation_verifier_recon.py",
        "tool_args": ["--profile", "selfhost"],
        "covers": ["F70-selfhost"],
        "first_verified": "W2a-U14（台账 VERIFIED；codices 冻结面 v1.1）",
        "assertion": "同 F70-desktop（selfhost profile）",
    },
    {
        "line_id": "F87",
        "chain": "E14",
        "tool": "tools/PENDING_OWNER_f87_extraction_gate_recon.py",
        "covers": ["F87-desktop", "F87-selfhost"],
        "first_verified": "W2b-U02（台账 VERIFIED；顺序纪律：核验服务先于抽取接线）",
        "assertion": "独立核验服务先实现再接抽取；quote 存在不等于命题支持；伪引文/旧版本拒绝；格候选不伪已核",
    },
    {
        "line_id": "F82",
        "chain": "E14",
        "tool": "tools/PENDING_OWNER_f82_tabular_core_recon.py",
        "covers": ["F82-desktop", "F82-selfhost", "F82-列", "F82-溯源"],
        "first_verified": "W2b-U05（台账 VERIFIED；harness w2b-u05@32da892e）",
        "assertion": "列/批量/出处/支持状态；先引用核验服务再接抽取（F82-复核/重跑/人改属 w2b-u31 review-ops 面，不在本链枚举，不称覆盖）",
    },
    {
        "line_id": "F25",
        "chain": "E14",
        "tool": "tools/PENDING_OWNER_f25_lease_generation_recon.py",
        "covers": ["F25-desktop", "F25-selfhost"],
        "first_verified": "W2b-U01（台账 VERIFIED；harness w2b-u01@0d5c79bc）",
        "assertion": "过期租约/旧 generation 迟到结果不覆新结果或人工改格；批量暂停重启续处理；真实并发回读（工单「租约/generation 竞争负测」即本行 C03-C05/C07 负测）",
    },
    {
        "line_id": "F88",
        "chain": "E14",
        "tool": "tools/PENDING_OWNER_f88_dualset_ci_recon.py",
        "covers": ["F88-desktop", "F88-selfhost"],
        "first_verified": "W2b-U03（台账 VERIFIED；黄金集 seed 20261016）",
        "assertion": "可答/应拒双集合评估＋六指标 CI 门；永远拒答不通过；核验器统计不冒独立幻觉率",
    },
]


def run_line(entry: dict, profiles, log_dir: Path, timeout_s: int) -> dict:
    tool = REPO_ROOT / entry["tool"]
    cmd = [sys.executable, "-X", "utf8", entry["tool"]]
    cmd += entry.get("tool_args", profiles_args(profiles))
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    t0 = time.monotonic()
    log_path = log_dir / (entry["line_id"].replace("/", "_") + ".log")
    print(f"[composite] RUN {entry['line_id']}: {' '.join(cmd[1:])}", flush=True)
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s)
        exit_code = proc.returncode
        stdout_tail = proc.stdout[-8000:]
        stderr_tail = proc.stderr[-4000:]
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        stdout_tail = (exc.stdout or b"")
        if isinstance(stdout_tail, bytes):
            stdout_tail = stdout_tail.decode("utf-8", "replace")
        stderr_tail = f"TIMEOUT after {timeout_s}s"
    duration_s = round(time.monotonic() - t0, 1)
    log_path.write_text(
        f"# command: {' '.join(cmd)}\n# cwd: {REPO_ROOT}\n# exit: {exit_code}\n\n"
        f"--- stdout (tail) ---\n{stdout_tail}\n--- stderr (tail) ---\n{stderr_tail}\n",
        encoding="utf-8")
    if exit_code == 0:
        verdict = "PASS"
    elif exit_code == 3:
        verdict = "BLOCKED_ENV_NAMED"
    else:
        verdict = "FAIL_NAMED"
    record = {
        "line_id": entry["line_id"],
        "chain": entry["chain"],
        "command": " ".join(cmd),
        "cwd": str(REPO_ROOT),
        "subject": "；".join(entry["covers"]) + f"｜首验 VERIFIED：{entry['first_verified']}",
        "assertion": entry["assertion"],
        "exit": exit_code,
        "verdict": verdict,
        "duration_s": duration_s,
        "started": started,
        "log": str(log_path.relative_to(REPO_ROOT)),
        "known_env_note": entry.get("known_env", ""),
        "stdout_tail": stdout_tail[-2000:],
    }
    print(f"[composite] -> {entry['line_id']} exit={exit_code} verdict={verdict} "
          f"({duration_s}s)", flush=True)
    return record


def fresh_evidence_files(component_dir: Path, since: float) -> list:
    out = []
    if not component_dir.is_dir():
        return out
    for path in sorted(component_dir.rglob("*")):
        if path.is_file() and path.stat().st_mtime >= since - 1.0:
            out.append(path)
    return out


def copy_line_evidence(record: dict, entry: dict, since: float) -> list:
    """把本轮各行工具新生成的证据文件复制进 evidence/E13|E14 使其自足。

    行工具实际落点有两族（2026-10-18 本单实测）：evidence/<FXX>/<profile>/
    与 docs/construction/evidence/<FXX>/{<profile>,wps}/（wps 族目录内以
    文件名后缀 .desktop./.selfhost. 区分）。复制时按文件名/父目录归档到
    evidence/<CHAIN>/<profile>/<face>/，无 profile 后缀的主档归 shared/。
    """
    face = entry["line_id"].replace("/", "_")
    chain_root = REPO_ROOT / "evidence" / entry["chain"]
    face_dirs = entry.get("evidence_dirs", [_evidence_face_dir(entry)])
    copied = []
    for face_dir in face_dirs:
        for root in ("evidence", "docs/construction/evidence"):
            src_base = REPO_ROOT / root / face_dir
            if not src_base.is_dir():
                continue
            for path in fresh_evidence_files(src_base, since):
                rel = path.relative_to(src_base)
                parts = rel.parts
                profile = None
                if parts and parts[0] in PROFILES:
                    profile = parts[0]
                    name = "/".join(parts[1:])
                else:
                    leaf = path.name
                    if ".desktop." in leaf:
                        profile, name = "desktop", leaf
                    elif ".selfhost." in leaf:
                        profile, name = "selfhost", leaf
                    else:
                        profile, name = "shared", leaf
                dst = chain_root / profile / face / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dst)
                copied.append(str(dst.relative_to(REPO_ROOT)))
    return copied


def _evidence_face_dir(entry: dict) -> str:
    tool = Path(entry["tool"]).stem.replace("PENDING_OWNER_", "")
    # f46_f52_wps_host_recon -> F46；f50_f51_reanchor_verbatim_recon -> F50；
    # 其余行首 token 即义务 id（f47/f48/f49/f17/f53/f70/f87/f82/f25/f88）
    first = tool.split("_")[0].upper()
    return "F" + first[1:] if first.startswith("F") else first


def write_aggregate(chain: str, records: list, all_copies: list, started: str) -> tuple:
    out_dir = REPO_ROOT / "evidence" / chain
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%S%z")
    ok = all(r["exit"] == 0 for r in records) and records
    verdict = "RECON_OK" if ok else "RECON_NAMED_FAILURES"
    doc = {
        "schema": "juscite-w3u25-composite-recon/1",
        "chain": chain,
        "verdict": verdict,
        "all_pass": bool(ok),
        "started": started,
        "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo_root": str(REPO_ROOT),
        "head": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "lines": records,
        "copied_evidence": all_copies,
        "note": "逐行复跑登记（command/cwd/subject/exit 工单纪律）；两行 E13/E14 "
                "台账状态由主控按本证据落账，本工具不改台账",
    }
    json_path = out_dir / f"{chain.lower()}-composite-recon-{ts}.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    md_path = out_dir / f"{chain.lower()}-composite-recon-{ts}.md"
    md_path.write_text(render_md(doc), encoding="utf-8")
    return json_path, md_path, verdict


def _git(*args: str) -> str:
    try:
        proc = subprocess.run(["git", *args], cwd=str(REPO_ROOT),
                              capture_output=True, text=True, encoding="utf-8",
                              timeout=30)
        return proc.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"git_error:{exc}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", action="append", choices=PROFILES,
                        dest="profiles")
    parser.add_argument("--only", choices=("e13", "e14"), default=None)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--timeout", type=int, default=7200,
                        help="每行子进程超时秒数（默认 7200）")
    args = parser.parse_args(argv)
    profiles = tuple(args.profiles) if args.profiles else PROFILES

    if args.list:
        for entry in LINES:
            if args.only and entry["chain"] != args.only.upper():
                continue
            print(f"{entry['chain']}\t{entry['line_id']}\t{entry['tool']}\t"
                  f"{','.join(entry['covers'])}")
        return 0

    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    t0 = time.monotonic()
    log_dir = REPO_ROOT / "evidence" / "E13" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "evidence" / "E14" / "logs").mkdir(parents=True, exist_ok=True)

    selected = [e for e in LINES if not args.only or e["chain"] == args.only.upper()]
    results = []
    copies = []
    for entry in selected:
        since = time.time()
        record = run_line(entry, profiles, log_dir, args.timeout)
        record["copied_evidence"] = copy_line_evidence(record, entry, since)
        copies.extend(record["copied_evidence"])
        results.append(record)

    chains = {}
    for chain in ("E13", "E14"):
        chain_records = [r for r in results if r["chain"] == chain]
        if not chain_records:
            continue
        json_path, md_path, verdict = write_aggregate(
            chain, chain_records, [c for r in chain_records for c in r["copied_evidence"]],
            started)
        chains[chain] = {"verdict": verdict, "json": str(json_path.relative_to(REPO_ROOT)),
                         "md": str(md_path.relative_to(REPO_ROOT))}
    total_s = round(time.monotonic() - t0, 1)
    print("=" * 72)
    for chain, info in chains.items():
        print(f"{chain}: {info['verdict']}  evidence={info['json']}")
    print(f"total {total_s}s, lines={len(results)}")
    all_ok = all(r["exit"] == 0 for r in results) and results
    return 0 if all_ok else 2


def render_md(doc: dict) -> str:
    lines = [
        f"# W3-U25 {doc['chain']} 复合收口对账（{doc['verdict']}）",
        "",
        f"- branch/head：`{doc['branch']}` @ `{doc['head'][:12]}`",
        f"- 起止：{doc['started']} → {doc['finished']}",
        f"- 判定：{doc['verdict']}（链 RECON_OK ⇔ 全部行 exit 0；缺面/败相具名，不补 PASS）",
        "",
        "| 行 | command | subject | exit | verdict |",
        "|---|---|---|---|---|",
    ]
    for r in doc["lines"]:
        lines.append(f"| {r['line_id']} | `{r['command']}` | {r['subject']} "
                     f"| {r['exit']} | {r['verdict']} |")
    lines += ["", "## 逐行尾部输出（stdout 尾 2000 字符，全量见 logs/）", ""]
    for r in doc["lines"]:
        lines.append(f"### {r['line_id']}（exit={r['exit']} {r['verdict']}，{r['duration_s']}s）")
        if r.get("known_env_note"):
            lines.append(f"- 在案环境注记：{r['known_env_note']}")
        lines.append("```")
        lines.append(r["stdout_tail"].strip() or "(空)")
        lines.append("```")
    lines += ["", "## 本轮复制进本目录的行证据", ""]
    for c in doc["copied_evidence"]:
        lines.append(f"- {c}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
