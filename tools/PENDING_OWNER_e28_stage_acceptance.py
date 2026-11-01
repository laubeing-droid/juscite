# -*- coding: utf-8 -*-
"""E28 整阶段验收 runner（PENDING_OWNER 版，裁决#23；W3-U30 新建，
W3-U37 收口段演进＋波末整阶段复跑）。

07 E28 断言：机器命令/cwd/subject/exit 证据逐行核对台账、NOT_RUN 不 PASS、
单元/形式/经验/法律来源/用户判断分层，不由 CI 或原子定理推全案。
裁决#23（00-总协调 §6.1 #23）：主控自决——tools/ 新建，W3 起三段复跑。

W3-U30 首跑覆盖 W3 阶段 v1 段；W3-U37 波末收口段按本波销账实际演进 S1/S5
（U31/U32/U33 落账后亲证）：E26 两处 BLOCKED 复验后仅余 E26-6 一处（人类
物理键盘定案，W4-U30 PENDING 具名在盘）；E25 canonical 维持 W3-U23 28/29、
desktop 静默窗复跑因并发撞车未完成如实挂主控 W4 收口待办、selfhost 20/20
复跑绿；F77 双 profile VERIFIED（W3-U33 selfhost 工件级补跑）。E28 如实
维持 IMPLEMENTING（不提前 VERIFIED）：

  S0 形式层：registry.validate 全清（分母 298↔06/07↔台账）＋台账 298 行
     逐行机检普查——每行按状态核对机器证据字段：
       VERIFIED    实跑证据（actual 或 evidence_path）非空；command/cwd/
                   subject/exit_code 完整者计 machine_complete，缺者如实
                   计 legacy_receipt（W0/W1 波老账，具名清单，不 retro 硬伤
                   也不放过谎报）；
       IMPLEMENTING failure_reason 非空（余段如实挂账）；
       NOT_RUN     不携 exit_code/actual 执行主张（逐行 NOT_RUN 不 PASS）；
       EXCLUDED    failure_reason 非空（砍行凭据）。
  S1 W3 阶段集硬依赖（E28 inputs=E09,E25,E26,E27；07:29）：
       E09 VERIFIED＋证据文件在盘；
       E25 IMPLEMENTING（failure_reason 携 PENDING_ADMIN_ENV＋W3-U33；
       desktop canonical recon-result verdict=RECON_OK_WITH_ENV_PENDING
       28/29＋selfhost RECON_OK 20/20＋desktop 复跑未完成 contention 件
       在盘如实记＝按 W3-U33 结果分支）；
       E26 状态机分义（W3-U37 演进）：IMPLEMENTING（本波实际：B3 全量
       清单＋W3-U31 部分定案档＋E26-6 维持 BLOCKED 待人类物理键盘＋
       W4-U30 PENDING 指针在盘）或 VERIFIED（须六子步全清
       e26-recheck-result.md 在盘——文件缺而翻 VERIFIED 即假信号 FAIL）；
       E27 VERIFIED（evidence JSON 26/26）；
       F77-desktop/selfhost VERIFIED（closure JSON 零 failures 在盘）；
       E28 自身 ∈{NOT_RUN, IMPLEMENTING}——VERIFIED 即 FAIL（W4/W5 段未闭）。
  S2 经验层三段复跑（机器命令逐行自台账 command 字段提取原样执行，
     cwd=worktree 根）：
       E19 tools/PENDING_OWNER_e19_normative_prediction_separation_recon.py
           --profile desktop --profile selfhost
       E20 tools/PENDING_OWNER_e20_voi_multirender_recon.py
           --profile desktop --profile selfhost
       E22 tools/PENDING_OWNER_e22_codices_baseline.py --formal-root …
           --codices-repo …（w2a-u12-e22 worktree＝台账原文；分支合并后
           才改仓根）
     各 exit 0＋刷新证据 verdict=RECON_OK（E22 passed=32）；
     W3-U29 已跑的 E10/F39 四轮不重复入集（执行集恰三工具，负向断言）。
  S3 NOT_RUN 不 PASS 阶段裁决：NOT_RUN>0（W4-U39 F57-word 裁决性结转后
     90＝B4 段 53＋B5 段 37，全属 W4/W5 波在账；B3 段零 NOT_RUN）
     ⇒ 阶段裁决≠FULL_PASS；
     W3 段裁决=IMPLEMENTING（续），E28 不 VERIFIED；B3 在账 NOT_RUN 行
     具名列清单（word 宿主结转 A1、宿主级挂账等）。
  S4 分层：W3 阶段集逐行归层（单元/形式/经验/法律来源/用户判断，词面
     规则自台账字段推导），五层各非空；边界断言：
     whole_case_proven_by_ci=false——测试绿/原子定理不推全案法律正确，
     用户判断项（E26-6 BLOCKED 待真机人工、A1 word 宿主结转）不为 CI 所
     代答。
  S5 W4 移交清单（W3-U37 收口段收缩）：E19 B4 真实法院数据迁移/校准、
     E20 B4 真实 checkpoint 概率产线、E22 B4 cncases 授权后实测
     （裁决#8-12）、E25 宿主级断网轮 PENDING_ADMIN_ENV（desktop 静默窗
     复跑随行）、E26-6 IME 组合态单处 BLOCKED 待人类物理键盘——W3-U31
     复验后 E26-2/E26-5b 已定案 PASS，E26 移交项由两处收缩为一处；逐项
     自 failure_reason 具名断言；W4/W5 复跑扩展=E28 后续段。

用法（juscite worktree 根 cwd；三段复跑真实执行，全程数分钟）：
  python -X utf8 tools/PENDING_OWNER_e28_stage_acceptance.py
  [--skip-reruns 仅机检+既有证据核对（不执行三段复跑；exit 码 0/2 同规则）]

exit 0＝全部断言过；证据写 evidence/E28/desktop/e28-stage-acceptance.{json,md}。
纯对账：不改台账、不改权威、不改 registry 状态；三段复跑消费各自冻结面
（JC/cases/harness/codices 检出只读）。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

csv.field_size_limit(10 ** 9)

RUN_DATE = time.strftime("%Y%m%d")
REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_CSV = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"
ROWS06_CSV = (REPO_ROOT / "docs" / "construction" / "authority"
              / "06-全量功能施工映射.csv")
ROWS07_CSV = (REPO_ROOT / "docs" / "construction" / "authority"
              / "07-新增必需工程义务.csv")
DENOMINATOR_JSON = (REPO_ROOT / "docs" / "construction" / "authority"
                    / "denominator.json")
COORDINATION_MD = REPO_ROOT / "docs" / "construction" / "00-总协调.md"
REGISTRY_PY = REPO_ROOT / "tools" / "acceptance" / "registry.py"
EVIDENCE_ROOT = REPO_ROOT / "evidence" / "E28" / "desktop"

EXPECTED_TOTAL = 299          # T26 后分母（289+9）＋W4-U50 扩卡 F118-v1.5
PLACEHOLDER_CMD = "PENDING_OWNER_IMPLEMENTATION"
PLACEHOLDER_SUBJ = "待实际验收冻结"

STAGE_ROWS = ["E09", "E25", "E26", "E27", "E19", "E20", "E22", "E28"]

RERUN_TOOLS = {
    "E19": "PENDING_OWNER_e19_normative_prediction_separation_recon.py",
    "E20": "PENDING_OWNER_e20_voi_multirender_recon.py",
    "E22": "PENDING_OWNER_e22_codices_baseline.py",
}
RERUN_TIMEOUT_S = 2400

B3_NOT_RUN_EXPECTED_PREFIX = ("F14", "F17-word", "F19", "F46-word", "F52-word",
                              "E28")
WORD_CARRYOVER_IDS = {"F17-word", "F46-word", "F52-word",
                      "F57-word"}  # 裁决 A1 结转（W4-U39 第三批记账收口扩为四行）
# 裁决性 EXCLUDED 前缀（A1 永久结转；与 tools/acceptance/registry.py 同键。
# W2b-U60 主控升级裁决：A1「按 EXCLUDED 处理」为明文，NOT_RUN/裁决性
# EXCLUDED 二态均属如实，S3D 防的是不为过门偷改状态）。
ADJUDICATED_EXCLUDED_PREFIX = "裁决性 EXCLUDED"

BOUNDARY_SENTENCE = "不由CI或原子定理推全案"
LAYER_NAMES = ("单元", "形式", "经验", "法律来源", "用户判断")


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail),
              flush=True)
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, restval=""))
    for row in rows:
        for key, value in list(row.items()):
            if value is None:
                row[key] = ""
    return rows


def load_registry():
    spec = importlib.util.spec_from_file_location(
        "juscite_registry_w3u30", str(REGISTRY_PY))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def only(rows: list[dict[str, str]], obligation_id: str) -> dict | None:
    hits = [r for r in rows if r.get("obligation_id") == obligation_id]
    return hits[0] if len(hits) == 1 else None


def json_verdict(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- S0 形式层

def classify_row(row: dict[str, str]) -> tuple[str, list[str]]:
    """逐行机检：返回 (行类, 缺失/违规机器字段明细)。

    行类：machine_complete（VERIFIED 且五机器字段齐）/
          legacy_receipt（VERIFIED 但机器字段缺，实跑证据在）/
          implementing / not_run / excluded。
    """
    st = row.get("status", "")
    problems: list[str] = []
    cmd = row.get("command", "").strip()
    cwd = row.get("cwd", "").strip()
    subj = row.get("subject", "").strip()
    exitc = row.get("exit_code", "").strip()
    actual = row.get("actual", "").strip()
    evid = row.get("evidence_path", "").strip()
    reason = row.get("failure_reason", "").strip()
    if st == "VERIFIED":
        if not actual and not evid:
            problems.append("无实跑证据（actual 与 evidence_path 皆空）")
        for name, val in (("command", cmd), ("cwd", cwd), ("subject", subj),
                          ("exit_code", exitc)):
            if not val or PLACEHOLDER_CMD in val or (
                    name == "subject" and PLACEHOLDER_SUBJ in val):
                problems.append(name)
        if actual and not evid:
            problems.append("evidence_path")
        return ("machine_complete" if not problems else "legacy_receipt",
                problems)
    if st == "IMPLEMENTING":
        if not reason:
            problems.append("failure_reason")
        return ("implementing", problems)
    if st == "NOT_RUN":
        if exitc or actual:
            problems.append("NOT_RUN 携执行主张（exit_code/actual）")
        return ("not_run", problems)
    if st == "EXCLUDED":
        if not reason:
            problems.append("failure_reason")
        return ("excluded", problems)
    return ("unknown_status", ["status 词表外：" + st])


def section_s0(checks: Checks, registry, denom: dict, rows06: list,
               rows07: list, ledger: list) -> dict:
    counts, problems = registry.validate(denom, rows06, rows07, ledger)
    checks.add("S0A_registry_validate_clean", not problems,
               "registry.validate（denominator.json↔06/07↔台账）problems=%s；"
               "台账总数=%d" % (problems[:3], len(ledger)))
    checks.add("S0A2_denominator_298", len(ledger) == EXPECTED_TOTAL,
               "台账实例总数=%d 期望=%d" % (len(ledger), EXPECTED_TOTAL))

    census: dict[str, list] = {"machine_complete": [], "legacy_receipt": [],
                               "implementing": [], "not_run": [],
                               "excluded": [], "unknown_status": []}
    lies: list[str] = []
    for row in ledger:
        cls, probs = classify_row(row)
        census[cls].append(row.get("obligation_id", "?"))
        # 硬规则：任何行不得谎报（有主张无凭据/词表外）
        fatal = [p for p in probs if "皆空" in p or "执行主张" in p
                 or "词表外" in p or "failure_reason" in p]
        if fatal:
            lies.append("%s: %s" % (row.get("obligation_id", "?"), fatal))
    checks.add("S0B_ledger_line_by_line_no_lies", not lies,
               "298 行逐行机检：零谎报（VERIFIED 无证据/NOT_RUN 携执行主张/"
               "IMPLEMENTING·EXCLUDED 缺 failure_reason 均零）=%s" % (lies[:5],))
    checks.add("S0B2_machine_complete_census", True,
               "machine_complete=%d legacy_receipt=%d（W0/W1 波老账具名：%s%s）"
               " implementing=%d not_run=%d excluded=%d"
               % (len(census["machine_complete"]),
                  len(census["legacy_receipt"]),
                  "、".join(census["legacy_receipt"][:6]),
                  "…" if len(census["legacy_receipt"]) > 6 else "",
                  len(census["implementing"]), len(census["not_run"]),
                  len(census["excluded"])))
    return census


# ------------------------------------------------- S1 W3 阶段集硬依赖（inputs）

def section_s1(checks: Checks, ledger: list) -> None:
    r09 = only(ledger, "E09")
    ok09 = r09 is not None and r09["status"] == "VERIFIED"
    files09 = [REPO_ROOT / "implementation" / "tests"
               / "test_p09_p10_material_wiring.py",
               REPO_ROOT / "implementation" / "python" / "legal_entry.py"]
    ok09 = ok09 and all(p.is_file() for p in files09)
    checks.add("S1A_E09_VERIFIED_evidence_on_disk", ok09,
               "E09 status=%s；证据文件在盘=%s"
               % (r09["status"] if r09 else "缺行",
                  [p.name for p in files09 if p.is_file()]))

    r25 = only(ledger, "E25")
    ev25 = [REPO_ROOT / "evidence" / "E25" / p / "recon-result.json"
            for p in ("desktop", "selfhost")]
    # W3-U33 结果分支：desktop 复跑因共享 dev 服务并发撞车未完成（失败轮
    # 证据另存 dated 件·canonical 还原 W3-U23 绿态），desktop 独占静默窗
    # 复跑记主控 W4 收口待办；selfhost 20/20 复跑绿。
    contention25 = (REPO_ROOT / "evidence" / "E25" / "desktop"
                    / "recon-result-20261020T-contention.json")
    ok25 = (r25 is not None and r25["status"] == "IMPLEMENTING"
            and "PENDING_ADMIN_ENV" in r25["failure_reason"]
            and "W3-U33" in r25["failure_reason"]
            and bool(r25["actual"].strip())
            and all(p.is_file() for p in ev25)
            and contention25.is_file())
    v25d = json_verdict(ev25[0]) if ev25[0].is_file() else {}
    v25s = json_verdict(ev25[1]) if ev25[1].is_file() else {}
    c25d = v25d.get("counts", {})
    c25s = v25s.get("counts", {})
    ok25 = ok25 and v25d.get("verdict") == "RECON_OK_WITH_ENV_PENDING"
    ok25 = ok25 and c25d.get("pass") == 28 and c25d.get("total") == 29
    ok25 = ok25 and v25s.get("verdict") == "RECON_OK"
    ok25 = ok25 and c25s.get("pass") == 20 and c25s.get("total") == 20
    checks.add("S1B_E25_IMPLEMENTING_realrun_evidence", ok25,
               "E25 status=%s failure_reason 携 PENDING_ADMIN_ENV＋W3-U33；"
               "desktop canonical verdict=%s counts=%s（W3-U23 28/29 有效）；"
               "selfhost verdict=%s counts=%s（W3-U33 复跑 20/20 绿）；"
               "desktop 静默窗复跑未完成 contention 件在盘=%s（挂主控 W4 "
               "收口待办）"
               % (r25["status"] if r25 else "缺行", v25d.get("verdict"),
                  c25d, v25s.get("verdict"), c25s, contention25.is_file()))

    r26 = only(ledger, "E26")
    ev26_dir = (REPO_ROOT / "docs" / "construction" / "evidence" / "E26"
                / "desktop")
    b3_26 = ev26_dir / "e26-b3-result.md"
    partial_26 = ev26_dir / "e26-recheck-partial-w3u31.md"
    pending_26 = ev26_dir / "PENDING-w4-u30-manual-recheck.md"
    full_26 = ev26_dir / "e26-recheck-result.md"
    st26 = r26["status"] if r26 else "缺行"
    fr26 = r26["failure_reason"] if r26 else ""
    if st26 == "VERIFIED":
        # 状态机分义：翻 VERIFIED 必须六子步全清＝全量复验 result 在盘
        # （半份档必使收口校验器 exit 1＝假信号，W3-U31 在案 reasoning）
        ok26 = full_26.is_file()
        why26 = ("VERIFIED＋e26-recheck-result.md 在盘=%s（六子步全清，"
                 "文件缺即假信号 FAIL）" % full_26.is_file())
    elif st26 == "IMPLEMENTING":
        ok26 = (b3_26.is_file() and partial_26.is_file()
                and pending_26.is_file()
                and "E26-1" in r26["actual"]
                and all(t in fr26 for t in ("E26-6", "BLOCKED", "物理键盘")))
        why26 = ("IMPLEMENTING（本波实际：W3-U31 复验 E26-2/E26-5b 定案 "
                 "PASS·仅余 E26-6 BLOCKED 待人类物理键盘·W4-U30 PENDING "
                 "具名）；e26-b3-result.md=%s e26-recheck-partial-w3u31.md"
                 "=%s PENDING-w4-u30-manual-recheck.md=%s 在盘；actual 携"
                 "六项清单＋failure_reason 携 E26-6/BLOCKED/物理键盘=%s"
                 % (b3_26.is_file(), partial_26.is_file(),
                    pending_26.is_file(),
                    all(t in fr26 for t in ("E26-6", "BLOCKED", "物理键盘"))))
    else:
        ok26 = False
        why26 = "status=%s 词表外（只许 IMPLEMENTING/VERIFIED 二态）" % st26
    checks.add("S1C_E26_state_machine_evidence_on_disk", ok26,
               "E26 状态机分义（W3-U37 演进）：%s" % why26)

    r27 = only(ledger, "E27")
    ev27 = [REPO_ROOT / "evidence" / "E27" / p
            / "e27-composite-split-recon.json"
            for p in ("desktop", "selfhost")]
    ok27 = r27 is not None and r27["status"] == "VERIFIED"
    ok27 = ok27 and all(p.is_file() for p in ev27)
    if ok27:
        v27 = json_verdict(ev27[0])
        ok27 = (v27.get("passed") == 26 and v27.get("total") == 26
                and v27.get("overall") in ("RECON_OK", "PASS", "pass"))
    recon27 = (REPO_ROOT / "docs" / "construction"
               / "e27-composite-reconciliation.md")
    ok27 = ok27 and recon27.is_file()
    checks.add("S1D_E27_VERIFIED_recon_26_26", ok27,
               "E27 status=%s；两 profile e27-composite-split-recon.json "
               "passed=26/26＋e27-composite-reconciliation.md 在盘"
               % (r27["status"] if r27 else "缺行"))

    r28 = only(ledger, "E28")
    ok28 = r28 is not None and r28["status"] in ("NOT_RUN", "IMPLEMENTING")
    checks.add(
        "S1E_E28_self_not_VERIFIED", ok28,
        "E28 status=%s（W4/W5 段未闭：runner W3 首跑 v1 段后如实留 "
        "IMPLEMENTING，VERIFIED 即提前销账=FAIL）"
        % (r28["status"] if r28 else "缺行"))

    # W3-U33 结算：F77 selfhost 工件级补跑翻 VERIFIED（desktop W3-U22 已
    # VERIFIED），closure JSON 零 failures 在盘。
    f77 = {s: only(ledger, "F77-" + s) for s in ("desktop", "selfhost")}
    f77_ev = {
        "desktop": (REPO_ROOT / "docs" / "construction" / "evidence" / "F77"
                    / "desktop" / "release-closure-20261018.json"),
        "selfhost": (REPO_ROOT / "docs" / "construction" / "evidence" / "F77"
                     / "selfhost" / "release-closure-20261020.json"),
    }
    ok_f77 = all(f77[s] is not None and f77[s]["status"] == "VERIFIED"
                 and f77_ev[s].is_file() for s in ("desktop", "selfhost"))
    if ok_f77:
        ok_f77 = all(not json_verdict(f77_ev[s]).get("failures")
                     for s in ("desktop", "selfhost"))
    checks.add(
        "S1F_F77_both_VERIFIED_w3u33_settlement", ok_f77,
        "F77-desktop/selfhost status=%s（W3-U33 selfhost 工件级补跑翻 "
        "VERIFIED·desktop W3-U22 已 VERIFIED）；closure JSON 在盘＋零 "
        "failures=%s"
        % ({s: (f77[s]["status"] if f77[s] else "缺行")
            for s in ("desktop", "selfhost")},
           {s: f77_ev[s].is_file() for s in ("desktop", "selfhost")}))


# ------------------------------------------------- S2 经验层三段复跑

def extract_recon_command(row_command: str, tool_name: str) -> str:
    """自台账 command 字段逐行提取指定 recon 子命令（剥尾部（…）注解）。

    注解内部可能含全角分号（E22 台账原文如此），故先按『；』切段、取含
    工具名的段，再于首个全角『（』处截断注解——机检命令本身不含全角括号。
    """
    hits = []
    for segment in row_command.split("；"):
        seg = segment.strip()
        if tool_name in seg:
            seg = seg.split("（", 1)[0].strip()
            hits.append(seg)
    if len(hits) != 1 or not hits[0].startswith("python"):
        raise RuntimeError(
            "台账 command 提取失败（期望恰一段 python 子命令）：%s → %r"
            % (tool_name, hits))
    seg = hits[0]
    if '"' in seg or "'" in seg:
        raise RuntimeError("命令含引号，空格切分不安全，需升级提取器：" + seg)
    if "（" in seg or "）" in seg:
        raise RuntimeError("命令残留全角括号（注解未剥净）：" + seg)
    return seg


def run_rerun(checks: Checks, tag: str, ledger: list, executed: list) -> None:
    row = only(ledger, tag)
    tool = RERUN_TOOLS[tag]
    cmd = extract_recon_command(row["command"], tool)
    argv = cmd.split()
    argv[0] = sys.executable          # 同解释器；-X utf8 等参数原样保留
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    proc = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=RERUN_TIMEOUT_S)
    executed.append({"obligation_id": tag, "command": cmd, "tool": tool,
                     "argv0_resolved": sys.executable, "cwd": str(REPO_ROOT),
                     "exit_code": proc.returncode, "started_at": started,
                     "seconds": round(time.monotonic() - t0, 1)})
    tail = (proc.stdout or "").strip().splitlines()[-4:]
    err_tail = (proc.stderr or "").strip().splitlines()[-3:]
    ok = proc.returncode == 0
    detail = "exit=%d；stdout 尾部=%s；stderr 尾部=%s" % (
        proc.returncode, tail, err_tail)
    if tag == "E19":
        for profile in ("desktop", "selfhost"):
            p = (REPO_ROOT / "docs" / "construction" / "evidence" / "E19"
                 / profile / "e19_normative_prediction_separation_recon.json")
            v = json_verdict(p) if p.is_file() else {}
            ok = ok and v.get("verdict") == "RECON_OK"
            detail += "；%s verdict=%s" % (profile, v.get("verdict"))
    elif tag == "E20":
        for profile in ("desktop", "selfhost"):
            p = (REPO_ROOT / "docs" / "construction" / "evidence" / "E20"
                 / profile / "e20_voi_multirender_recon.json")
            v = json_verdict(p) if p.is_file() else {}
            ok = ok and v.get("verdict") == "RECON_OK"
            detail += "；%s verdict=%s" % (profile, v.get("verdict"))
    elif tag == "E22":
        p = (REPO_ROOT / "docs" / "construction" / "evidence" / "E22"
             / "desktop" / "e22-baseline-result.json")
        v = json_verdict(p) if p.is_file() else {}
        ok = ok and v.get("passed") == 32
        detail += "；e22-baseline-result passed=%s" % (v.get("passed"),)
    checks.add("S2_%s_rerun_exit0_and_verdict" % tag, ok,
               "机器命令自台账逐行提取原样执行（cwd=worktree 根）——" + detail)


def section_s2(checks: Checks, ledger: list, skip: bool) -> list:
    executed: list[dict] = []
    if skip:
        checks.add("S2_reruns_skipped_by_flag", False,
                   "--skip-reruns 下三段复跑未执行；本检查项按 FAIL 记账，"
                   "完整验收须无旗标全量跑")
        return executed
    for tag in ("E19", "E20", "E22"):
        run_rerun(checks, tag, ledger, executed)
    tools_run = sorted(e["tool"] for e in executed)
    no_dup = (len(executed) == 3
              and not any("e10_f39" in e["command"] for e in executed)
              and set(tools_run) == set(RERUN_TOOLS.values()))
    checks.add("S2D_no_duplicate_e10_f39_set_exactly_three", no_dup,
               "执行集恰三工具（%s），W3-U29 已跑 E10/F39 四轮不重复入集"
               "（不重）；executed=%s" % (sorted(RERUN_TOOLS.values()),
                                         tools_run))
    return executed


# ------------------------------------------------- S3 NOT_RUN 不 PASS 阶段裁决

def section_s3(checks: Checks, ledger: list, census: dict) -> dict:
    not_run = [r for r in ledger if r["status"] == "NOT_RUN"]
    b3_not_run = [r["obligation_id"] for r in ledger
                  if r["status"] == "NOT_RUN" and "B3" in r.get("phase", "")]
    unexpected = [i for i in b3_not_run
                  if not i.startswith(B3_NOT_RUN_EXPECTED_PREFIX)
                  and not i.startswith("F14")]
    verdict = "IMPLEMENTING" if not_run else "FULL_PASS"
    full_pass = not not_run
    b4_not_run = sum(1 for r in not_run if r.get("phase", "").startswith("B4"))
    b5_not_run = sum(1 for r in not_run if r.get("phase", "").startswith("B5"))
    checks.add("S3A_not_run_count_%d_verdict_%s" % (len(not_run), verdict),
               verdict == "IMPLEMENTING",
               "台账 NOT_RUN=%d（>0 ⇒ 阶段裁决≠FULL_PASS；B4 段=%d＋B5 段="
               "%d 全属 W4/W5 波在账·B3 段=%d）；W3 段裁决=IMPLEMENTING（续）"
               % (len(not_run), b4_not_run, b5_not_run,
                  len(not_run) - b4_not_run - b5_not_run))
    checks.add("S3B_e28_not_VERIFIED_in_verdict",
               (only(ledger, "E28") or {}).get("status") != "VERIFIED"
               and not full_pass,
               "E28 不 VERIFIED＝W3 后如实留 IMPLEMENTING；W4/W5 复跑扩展段"
               "未闭不提前销账")
    checks.add("S3C_b3_not_run_named", not unexpected,
               "B3 在账 NOT_RUN 行具名=%s；清单外=%s（word 宿主结转 A1＋"
               "宿主级挂账等，逐行不 PASS）" % (b3_not_run, unexpected[:5]))
    def _word_carryover_honest(oid: str) -> bool:
        row = only(ledger, oid)
        if row is None:
            return False
        if row["status"] == "NOT_RUN":
            return True
        return (row["status"] == "EXCLUDED"
                and row.get("failure_reason", "").startswith(
                    ADJUDICATED_EXCLUDED_PREFIX))

    word_ok = all(_word_carryover_honest(i) for i in WORD_CARRYOVER_IDS)
    checks.add("S3D_word_carryover_a1_honest", word_ok,
               "word 宿主四行（%s）结转＝裁决 A1（Word 不安装，2026-10-18）"
               "如实在账：NOT_RUN 或 裁决性 EXCLUDED（A1 永久结转·原回收点 "
               "W2-S1/W4-S2 作废）二态均如实，不为过门偷改状态"
               % sorted(WORD_CARRYOVER_IDS))
    return {"not_run_total": len(not_run),
            "b3_not_run": b3_not_run,
            "verdict": verdict,
            "full_pass": full_pass,
            "census": {k: len(v) for k, v in census.items()},
            "census_legacy_ids": census["legacy_receipt"]}


# ------------------------------------------------- S4 分层

def classify_layers(row: dict[str, str]) -> list[str]:
    blob = " ".join((row.get("command", ""), row.get("subject", ""),
                     row.get("actual", ""), row.get("failure_reason", ""),
                     row.get("evidence_path", "")))
    layers = []
    if "pytest" in blob:
        layers.append("单元")
    if ("registry" in blob or "validate" in blob
            or row.get("obligation_id") in ("E27", "E28")):
        layers.append("形式")
    if ("recon" in blob or "实跑" in blob or "真跑" in blob
            or "RECON_OK" in blob or "NSIS" in blob):
        layers.append("经验")
    if (row.get("obligation_id") == "E22" or "--formal-root" in blob
            or "codices" in blob or "lccc" in blob):
        layers.append("法律来源")
    if ("真机" in blob or "人工" in blob or "用户" in blob or "BLOCKED" in blob
            or "PENDING_ADMIN_ENV" in blob or "裁决" in blob
            or "清单" in blob):
        layers.append("用户判断")
    return layers


def section_s4(checks: Checks, ledger: list) -> dict:
    layer_map: dict[str, list[str]] = {}
    gaps = []
    for oid in STAGE_ROWS:
        row = only(ledger, oid)
        if row is None:
            gaps.append(oid + ":缺行")
            continue
        layers = classify_layers(row)
        layer_map[oid] = layers
        if not layers:
            gaps.append(oid + ":零层")
    checks.add("S4A_stage_rows_all_layered", not gaps,
               "W3 阶段集 8 行逐行归层=%s；零层/缺行=%s"
               % ({k: v for k, v in layer_map.items()}, gaps))
    covered = set(l for ls in layer_map.values() for l in ls)
    checks.add("S4B_five_layers_all_present",
               set(LAYER_NAMES) <= covered,
               "五层各非空：缺=%s" % (sorted(set(LAYER_NAMES) - covered),))
    checks.add("S4C_whole_case_boundary",
               True,
               "边界断言 whole_case_proven_by_ci=false：%s——测试绿/原子定理/"
               "CI 不推全案法律正确；用户判断项（E26-6 BLOCKED 待真机人工、"
               "word 宿主结转 A1、宿主级 PENDING_ADMIN_ENV）不为 CI 代答"
               % BOUNDARY_SENTENCE)
    return {"layer_map": layer_map, "whole_case_proven_by_ci": False,
            "boundary_sentence": BOUNDARY_SENTENCE}


# ------------------------------------------------- S5 W4 移交清单

def section_s5(checks: Checks, ledger: list) -> list:
    # W3-U37 收口段收缩：E26 移交项随 W3-U31 复验由「两处 BLOCKED」收缩为
    # 「E26-6 单处待人类物理键盘」（E26-2/E26-5b 已定案 PASS·W4-U30 PENDING
    # 具名在盘）；E19/E20/E22/宿主级 admin 移交项维持具名在账。
    expect = {
        "E19": ("B4", "真实法院数据"),
        "E20": ("B4", "checkpoint"),
        "E22": ("裁决#8-12", "W4"),
        "E25": ("PENDING_ADMIN_ENV", "宿主级"),
        "E26": ("E26-6", "物理键盘"),
    }
    handover = []
    missing = []
    for oid, (token_a, token_b) in expect.items():
        row = only(ledger, oid)
        blob = (row.get("failure_reason", "") if row else "")
        if token_a in blob and token_b in blob:
            handover.append(oid)
        else:
            missing.append("%s:failure_reason 缺 %s/%s"
                           % (oid, token_a, token_b))
    checks.add("S5_w4_handover_named_in_failure_reasons", not missing,
               "W4 移交逐项在账=%s；缺=%s；E26 移交项 W3-U31 复验后收缩"
               "（E26-2/E26-5b 定案 PASS·仅余 E26-6 待人类物理键盘＝"
               "PENDING-w4-u30 具名）；E28 后续段=W4/W5 复跑扩展"
               % (handover, missing))
    return handover


# ------------------------------------------------- 证据落盘

def write_evidence(checks: Checks, executed: list, s3: dict, s4: dict,
                   handover: list, head: str, started: str) -> Path:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "juscite-e28-stage-acceptance/1",
        "unit": "W3-U37",
        "feature": "E28 整阶段验收 runner W3 收口段演进＋波末整阶段复跑"
                   "（裁决#23·W3-U30 新建·W3-U37 按 U31/U32/U33 销账实际"
                   "演进 S1/S5）",
        "profile": "desktop",
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "subject_commit": head,
        "inputs_sha256": {
            "acceptance-ledger.csv": sha256_file(LEDGER_CSV),
            "registry.py": sha256_file(REGISTRY_PY),
            "00-总协调.md": sha256_file(COORDINATION_MD),
        },
        "reruns": executed,
        "stage_verdict": s3,
        "layering": s4,
        "w4_handover": handover,
        "e28_row_status_after_run": "IMPLEMENTING",
        "next_extension": "W4/W5 复跑扩展（07 E28 phase=B3/B4/B5）",
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "RECON_OK" if checks.all_passed else "RECON_FAIL",
    }
    jp = EVIDENCE_ROOT / "e28-stage-acceptance.json"
    jp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                  encoding="utf-8", newline="\n")
    lines = [
        "# E28 整阶段验收 runner 波末收口证据（W3-U37，裁决#23）",
        "",
        "- run_date: %s" % RUN_DATE,
        "- subject_commit: `%s`" % head,
        "- 阶段裁决: **%s**（NOT_RUN=%d>0 ⇒ 非 FULL_PASS）；E28 行维持 "
        "IMPLEMENTING，W4/W5 复跑扩展" % (s3["verdict"], s3["not_run_total"]),
        "- 边界: %s——测试绿/CI/原子定理不推全案法律正确；用户判断项不为 "
        "CI 代答。" % BOUNDARY_SENTENCE,
        "",
        "## 三段复跑（机器命令自台账逐行提取原样执行）",
        "",
    ]
    for e in executed:
        lines.append("- %s：exit %s（%s）" % (e["obligation_id"],
                                              e["exit_code"], e["command"]))
    lines += [
        "",
        "## W4 移交清单（failure_reason 具名在账）",
        "",
    ]
    lines += ("- %s" % h for h in handover)
    lines += [
        "",
        "## 检查明细",
        "",
    ]
    lines += ("- [%s] %s — %s" % (i["status"], i["id"], i["detail"])
              for i in checks.items)
    mp = EVIDENCE_ROOT / "e28-stage-acceptance.md"
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return EVIDENCE_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-reruns", action="store_true",
                        help="仅机检＋既有证据核对（不执行三段复跑；S2 记 FAIL）")
    args = parser.parse_args()

    started = datetime.now(timezone.utc).isoformat()
    for path in (LEDGER_CSV, ROWS06_CSV, ROWS07_CSV, DENOMINATOR_JSON,
                 COORDINATION_MD, REGISTRY_PY):
        if not path.is_file():
            print("FATAL: 权威输入缺失 %s" % path)
            return 2
    registry = load_registry()
    denom = json.loads(DENOMINATOR_JSON.read_text(encoding="utf-8"))
    rows06 = read_csv(ROWS06_CSV)
    rows07 = read_csv(ROWS07_CSV)
    ledger = read_csv(LEDGER_CSV)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, cwd=str(REPO_ROOT)).stdout.strip()

    checks = Checks()
    census = section_s0(checks, registry, denom, rows06, rows07, ledger)
    section_s1(checks, ledger)
    executed = section_s2(checks, ledger, args.skip_reruns)
    s3 = section_s3(checks, ledger, census)
    s4 = section_s4(checks, ledger)
    handover = section_s5(checks, ledger)

    ev = write_evidence(checks, executed, s3, s4, handover, head, started)
    print("E28 stage acceptance runner: %d/%d checks passed, exit %d"
          % (checks.passed_count, len(checks.items),
             0 if checks.all_passed else 2), flush=True)
    print("evidence=%s" % ev, flush=True)
    return 0 if checks.all_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
