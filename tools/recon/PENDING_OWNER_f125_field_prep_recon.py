"""F125 案管延伸字段准备 recon（W5-U16）——裁决#21「字段准备先行」。

对账对象（本单新建登记面，非 F125 验收——F125 仍 PENDING_USER_DECISION，
tools/acceptance/registry.py ADJUDICATED_SEGMENT_OK 白名单不含 F125，
台账两行维持 NOT_RUN）：
  implementation/python/f125_case_admin_fields.py ＝ 四域数据字段登记面
  （财务对账/审批用印/归档借阅/审批回避；LawLink 数据模型整段参考，
  authority/06 V7-125 preserved）。断言两层：
  A. 字段面登记齐——四域闭集、字段字典逐键钉定、金额唯一
     minor_units（整分 int，禁 float）、启用总闸结构常量 False；
  B. 公开业务面未启用——桥面 legal_entry.call 对 F125 业务方法名
     method_not_connected（未启用负测·真派发路径）＋legal_entry AST
     零 f125 分派泄漏＋登记面零消费者（implementation/python 全目录
     import 扫描）＋登记面纯声明 AST（零 I/O 零建库零 DDL）。

红线逐字（authority/06 V7-125 python_entry_binding）：
  「record_time/issue_bill/record_payment仅律师账单，不债权回款」——
  登记面零 F08 账单通道标识符（AST Name/Attribute 级），红线名只允许
  出现在携「仅律师账单」边界声明的字符串常量里。

E16 款源账 VERIFIED 零改动回归（裁决#21：真实回款不随它延迟）：
  ①台账 E16 行 status=VERIFIED exit_code=0 零动；②E16 面 juscite 侧
  文件（legal_entry.py／E16 recon 工具）对 main 基线 sha256 逐字节
  相等；③行为级——本单工作树内按 profile 复跑
  tools/recon/PENDING_OWNER_e16_cash_contract_recon.py 单 profile exit 0 且
  verdict=RECON_OK（依赖钉定 harness/JC w2b-u51 worktree＋lh-pg-e08，
  缺环境＝exit 3 如实上报，不假 PASS）。

范围纪律：本单不裁范围只备字段；回收点具名（用户对四域具体范围裁定
后的 F125 v2 施工工单）；06 status=PENDING_USER_DECISION 与
interface_gap=PENDING_SCOPE_NO_ENABLE 从权威 CSV 现读钉定。

profile 说明：字段准备面未启用，故 desktop/selfhost 两部署形态判据
相同（恰恰是「公开面未启用」的结构性含义）；双 profile 各自独立复跑
（含各自 profile 的 E16 行为级复跑与证据落盘），证据分别落
docs/construction/evidence/F125/<profile>/。

用法：
  python -X utf8 tools/recon/PENDING_OWNER_f125_field_prep_recon.py \
      --profile desktop --profile selfhost

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失
（E16 行为级复跑依赖缺失时如实上报）。
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import f125_case_admin_fields as registry  # noqa: E402
from legal_entry import NotConnected, call  # noqa: E402

LEDGER_CSV = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"
AUTHORITY_06 = (REPO_ROOT / "docs" / "construction" / "authority"
                / "06-全量功能施工映射.csv")
CONTRACT_DOC = (REPO_ROOT / "docs" / "construction"
                / "f125-field-prep-contract.md")
E16_RECON_TOOL = (REPO_ROOT / "tools"
                  / "PENDING_OWNER_e16_cash_contract_recon.py")
LEGAL_ENTRY_PY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"

REGISTRY_ID_PINNED = "juscite-f125-field-prep/1"
DOMAIN_NAMES_PINNED = {
    "finance_reconciliation": "财务对账",
    "approval_seal": "审批用印",
    "archive_borrow": "归档借阅",
    "approval_recusal": "审批回避",
}
INTERFACE_GAP_PINNED = "PENDING_SCOPE_NO_ENABLE"
REDLINE_PINNED = (
    "record_time/issue_bill/record_payment仅律师账单，不债权回款")
REDLINE_NAMES = ("record_time", "issue_bill", "record_payment")
REDLINE_CONTEXT = "仅律师账单"

# recon 钉定字段字典：域 → 字段名元组 → (type, required, values|None)。
# note 为描述性文本不入钉定面；names/types/required/闭集值＝合同面。
EXPECTED_FIELDS = {
    "finance_reconciliation": {
        "recon_entry_id": ("id", True, None),
        "matter_ref": ("ref", True, None),
        "entry_kind": ("enum", True, ("receipt_confirm",
                                      "receivable_writeoff",
                                      "invoice_link",
                                      "supplement_agreement",
                                      "finance_correction")),
        "amount_minor": ("minor_units", True, None),
        "currency": ("enum", True, ("CNY",)),
        "occurred_on": ("date", True, None),
        "invoice_ref": ("ref", False, None),
        "agreement_ref": ("ref", False, None),
        "correction_reason": ("text", False, None),
        "evidence_ref": ("ref", True, None),
        "note": ("text", False, None),
    },
    "approval_seal": {
        "approval_id": ("id", True, None),
        "matter_ref": ("ref", True, None),
        "approval_kind": ("enum", True, ("intake", "document", "archive",
                                         "invoicing", "seal")),
        "applicant_ref": ("ref", True, None),
        "approver_ref": ("ref", True, None),
        "authorization_ref": ("ref", False, None),
        "seal_rule_ref": ("ref", False, None),
        "requested_at": ("datetime", True, None),
        "decided_at": ("datetime", False, None),
        "decision": ("enum", False, ("approved", "rejected")),
        "execution_status": ("enum", True, ("pending", "executed",
                                            "failed", "cancelled")),
        "execution_evidence_ref": ("ref", False, None),
        "reason": ("text", False, None),
    },
    "archive_borrow": {
        "archive_id": ("id", True, None),
        "matter_ref": ("ref", True, None),
        "archive_kind": ("enum", True, ("formal_archive",
                                        "supplement_archive",
                                        "review_snapshot")),
        "policy_ref": ("ref", False, None),
        "snapshot_ref": ("ref", False, None),
        "finalized_ref": ("ref", False, None),
        "archived_at": ("date", False, None),
        "borrow_id": ("id", False, None),
        "borrower_ref": ("ref", False, None),
        "borrow_mode": ("enum", False, ("timed_readonly",)),
        "borrow_until": ("datetime", False, None),
        "borrow_status": ("enum", False, ("active", "returned", "expired")),
    },
    "approval_recusal": {
        "recusal_id": ("id", True, None),
        "approval_ref": ("ref", True, None),
        "rule_kind": ("enum", True, ("self_application_bar",)),
        "actor_ref": ("ref", True, None),
        "exception_ref": ("ref", False, None),
        "scope_binding_ref": ("ref", False, None),
        "decided_by_ref": ("ref", True, None),
        "reason": ("text", True, None),
        "decided_at": ("datetime", True, None),
    },
}

# 未启用负测方法名（每域一假想公开方法＋harness 命名空间一假想）。
NOT_ENABLED_METHODS = (
    "f125.finance_recon_read",
    "f125.approval_seal_submit",
    "f125.archive_borrow_request",
    "f125.approval_recusal_decide",
    "harness.f125_case_admin_read",
)

# 单位 footprint 允许面：本单只允许制备四类文件（evidence/F125/ 任意深）。
ALLOWED_PATHS = frozenset({
    "implementation/python/f125_case_admin_fields.py",
    "implementation/tests/test_f125_field_prep_wiring.py",
    "tools/recon/PENDING_OWNER_f125_field_prep_recon.py",
    "docs/construction/f125-field-prep-contract.md",
})
ALLOWED_PREFIXES = ("docs/construction/evidence/F125/",)
FORBIDDEN_PREFIXES = ("implementation/patches/",)
FORBIDDEN_SUFFIXES = (".db", ".sqlite", ".sql", ".sqlite3")

# 登记面纯声明 AST 禁止面。
FORBIDDEN_IMPORTS = frozenset({
    "sqlite3", "subprocess", "socket", "urllib", "urllib.request",
    "http", "http.client", "requests", "pathlib", "os", "shutil",
    "pickle", "ctypes",
})
FORBIDDEN_CALLS = frozenset({
    "open", "eval", "exec", "compile", "__import__", "connect",
    "execute", "executemany", "system", "popen", "remove", "unlink",
    "mkdir", "makedirs", "rename", "replace",
})
FORBIDDEN_IDENTIFIERS = frozenset({
    "sqlite3", "subprocess", "socket", "urlopen", "cursor", "conn",
    "connection", "engine", "session_maker",
})
DDL_PATTERN = ("create table", "insert into", "drop table",
               "alter table", "create index")


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True,
        text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError("git " + " ".join(args) + " failed: "
                           + out.stderr.strip()[:200])
    return out.stdout


class Recon:
    def __init__(self, profile: str):
        self.profile = profile
        self.checks: list[dict] = []
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.env_missing = False

    def step(self, name: str, ok: bool, **facts) -> None:
        self.checks.append({"check": name, "status": "PASS" if ok
                            else "FAIL", **facts})
        print(json.dumps({"check": name, "status": "PASS" if ok
                          else "FAIL", **facts}, ensure_ascii=False),
              flush=True)

    def expect_error(self, name: str, thunk, code_part: str) -> None:
        try:
            thunk()
        except NotConnected as exc:
            self.step(name, code_part in str(exc), code=str(exc)[:160])
            return
        except Exception as exc:  # noqa: BLE001 ——具名败相取证
            self.step(name, False,
                      code=type(exc).__name__ + ":" + str(exc)[:120])
            return
        self.step(name, False, code="expected_NotConnected_no_raise")

    # ---- s01-s03 登记面 ---------------------------------------------
    def registry_face(self) -> None:
        self.step("s01_registry_present",
                  registry.REGISTRY_ID == REGISTRY_ID_PINNED
                  and registry.ENABLED is False,
                  registry_id=registry.REGISTRY_ID,
                  enabled=registry.ENABLED)
        registry_ok = True
        registry_error = ""
        try:
            registry.validate()
        except AssertionError as exc:
            registry_ok = False
            registry_error = str(exc)
        self.step("s01_registry_validate_closed", registry_ok,
                  error=registry_error)
        src = LEGAL_ENTRY_PY.read_text(encoding="utf-8")
        reg_src = (REPO_ROOT / "implementation" / "python"
                   / "f125_case_admin_fields.py").read_text(encoding="utf-8")
        tree = ast.parse(reg_src)
        enabled_literal = [
            isinstance(node.value, ast.Constant)
            and node.value.value is False
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "ENABLED"
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)]
        self.step("s04_enabled_literal_false_assign",
                  any(enabled_literal), literals=enabled_literal)

        actual = {}
        for domain, fields in registry.DOMAIN_FIELDS.items():
            actual[domain] = {
                name: (spec["type"], spec["required"],
                       tuple(spec["values"]) if spec.get("values") else None)
                for name, spec in fields.items()}
        self.step("s02_domain_closed_set_exact",
                  tuple(actual) == registry.DOMAIN_ORDER
                  and set(actual) == set(EXPECTED_FIELDS),
                  domains=list(actual))
        per_domain_equal = {
            d: actual.get(d) == EXPECTED_FIELDS[d]
            for d in EXPECTED_FIELDS}
        field_total = sum(len(v) for v in actual.values())
        self.step("s02_field_dictionary_pinned_equal",
                  all(per_domain_equal.values()) and field_total == 45,
                  per_domain=per_domain_equal, field_total=field_total)
        self.step("s12_domain_names_cn_pinned",
                  dict(registry.DOMAIN_NAMES) == DOMAIN_NAMES_PINNED,
                  names=dict(registry.DOMAIN_NAMES))

        money_fields = [
            d + ":" + n for d, fs in registry.DOMAIN_FIELDS.items()
            for n, spec in fs.items() if spec["type"] == "minor_units"]
        type_closure = registry.FIELD_TYPES
        self.step("s03_money_minor_units_only",
                  money_fields == ["finance_reconciliation:amount_minor"]
                  and not any("float" in t or "double" in t
                              for t in type_closure),
                  money_fields=money_fields,
                  types=sorted(type_closure))
        self.step("s03_currency_closed_cny",
                  registry.DOMAIN_FIELDS["finance_reconciliation"]
                  ["currency"]["values"] == ("CNY",),
                  currency=tuple(registry.DOMAIN_FIELDS
                                 ["finance_reconciliation"]
                                 ["currency"]["values"]))

    # ---- s05-s06 未启用负测＋零泄漏 ---------------------------------
    def not_enabled_negatives(self) -> None:
        for method in NOT_ENABLED_METHODS:
            self.expect_error(
                "s05_not_enabled_refused:" + method,
                lambda m=method: call(m, {"args": {}}, {}),
                "method_not_connected:" + method)

    def zero_leak_ast(self) -> None:
        le_tree = ast.parse(
            LEGAL_ENTRY_PY.read_text(encoding="utf-8"))
        leak = []
        for node in ast.walk(le_tree):
            raw = None
            if isinstance(node, ast.Constant) and isinstance(
                    node.value, str):
                raw = node.value
            elif isinstance(node, (ast.Name, ast.Attribute, ast.arg,
                                   ast.keyword)):
                raw = getattr(node, "id", None) or getattr(
                    node, "attr", None) or getattr(node, "arg", None)
            if raw and "f125" in raw.lower():
                leak.append(raw[:60])
        self.step("s06_legal_entry_zero_f125_ast", not leak,
                  hits=leak[:5])

        py_dir = REPO_ROOT / "implementation" / "python"
        consumers = []
        for py in sorted(py_dir.glob("*.py")):
            text = py.read_text(encoding="utf-8", errors="replace")
            if "f125_case_admin_fields" in text:
                consumers.append(py.name)
        # 桥/产品运行时面零消费；登记面文件自身允许出现本名（自述）。
        self.step("s06_registry_zero_runtime_consumers",
                  set(consumers) <= {"f125_case_admin_fields.py"},
                  consumers=consumers)

        reg_tree = ast.parse(
            (REPO_ROOT / "implementation" / "python"
             / "f125_case_admin_fields.py").read_text(encoding="utf-8"))
        imports = set()
        bad_calls = []
        bad_idents = []
        redline_ident_hits = []
        bad_constants = []
        for node in ast.walk(reg_tree):
            if isinstance(node, ast.Import):
                imports.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
            elif isinstance(node, ast.Call):
                fn = node.func
                fname = (fn.id if isinstance(fn, ast.Name)
                         else fn.attr if isinstance(fn, ast.Attribute)
                         else None)
                if fname in FORBIDDEN_CALLS:
                    bad_calls.append(fname)
            elif isinstance(node, (ast.Name, ast.Attribute)):
                ident = getattr(node, "id", None) or getattr(
                    node, "attr", None)
                if ident in FORBIDDEN_IDENTIFIERS:
                    bad_idents.append(ident)
                if ident in REDLINE_NAMES:
                    redline_ident_hits.append(ident)
            elif isinstance(node, ast.Constant) and isinstance(
                    node.value, str):
                low = node.value.lower()
                if any(p in low for p in DDL_PATTERN):
                    bad_constants.append(node.value[:40])
        real_imports = {i for i in imports if i != "__future__"}
        self.step("s06_registry_pure_declaration_ast",
                  not real_imports and not bad_calls and not bad_idents
                  and not bad_constants,
                  imports=sorted(imports), bad_calls=bad_calls,
                  bad_idents=bad_idents, ddl_hits=bad_constants)

    # ---- s07 红线逐字 ------------------------------------------------
    def billing_redline(self) -> None:
        self.step("s07_meta_redline_verbatim",
                  registry.META["billing_channel_redline"]
                  == REDLINE_PINNED,
                  meta=registry.META["billing_channel_redline"])
        reg_tree = ast.parse(
            (REPO_ROOT / "implementation" / "python"
             / "f125_case_admin_fields.py").read_text(encoding="utf-8"))
        ident_hits = []
        const_bad = []
        for node in ast.walk(reg_tree):
            if isinstance(node, (ast.Name, ast.Attribute)):
                ident = getattr(node, "id", None) or getattr(
                    node, "attr", None)
                if ident in REDLINE_NAMES:
                    ident_hits.append(ident)
            elif isinstance(node, ast.Constant) and isinstance(
                    node.value, str):
                if any(n in node.value for n in REDLINE_NAMES):
                    if REDLINE_CONTEXT not in node.value:
                        const_bad.append(node.value[:60])
        self.step("s07_zero_bill_channel_identifiers",
                  not ident_hits and not const_bad,
                  ident_hits=ident_hits, const_without_context=const_bad)
        # 权威 CSV 现读钉定：06 V7-125 行红线逐字＋status＋interface_gap。
        with open(AUTHORITY_06, encoding="utf-8-sig", newline="") as fh:
            row06 = [r for r in csv.DictReader(fh)
                     if r["v7_id"] == "V7-125"][0]
        self.step("s07_authority06_row_pinned",
                  row06["python_entry_binding"].endswith(REDLINE_PINNED)
                  and row06["status"] == "PENDING_USER_DECISION"
                  and row06["interface_gap"] == INTERFACE_GAP_PINNED
                  and row06["owner"] == "product+harness"
                  and row06["python_entry_ids"] == "P04",
                  status06=row06["status"],
                  interface_gap=row06["interface_gap"],
                  binding06=row06["python_entry_binding"])
        self.step("s10_meta_scope_pins",
                  registry.META["interface_gap"] == INTERFACE_GAP_PINNED
                  and registry.META["no_new_store"] is True
                  and registry.META["second_authority"] is False
                  and "回收点" in registry.META["recovery_point"]
                  and "E16" in registry.META["e16_non_delay"],
                  recovery_point=registry.META["recovery_point"][:80])
        contract = (CONTRACT_DOC.read_text(encoding="utf-8")
                    if CONTRACT_DOC.exists() else "")
        self.step("s10_contract_doc_pins",
                  all(pin in contract for pin in (
                      REDLINE_PINNED, INTERFACE_GAP_PINNED, "回收点",
                      "裁决#21", "E16")),
                  contract=str(CONTRACT_DOC.name) + ":" + str(
                      len(contract)) + "chars")

    # ---- s08-s09 E16 零改动回归 -------------------------------------
    def e16_zero_change(self) -> None:
        with open(LEDGER_CSV, encoding="utf-8-sig", newline="") as fh:
            rows = {r["obligation_id"]: r
                    for r in csv.DictReader(fh)}
        e16 = rows.get("E16", {})
        f125_rows = {k: rows.get("F125-" + p, {}).get("status", "MISSING")
                     for k, p in (("desktop", "desktop"),
                                  ("selfhost", "selfhost"))}
        self.step("s08_e16_ledger_row_verified_untouched",
                  e16.get("status") == "VERIFIED"
                  and e16.get("exit_code") == "0",
                  ledger_status=e16.get("status"),
                  ledger_exit_code=e16.get("exit_code"))
        self.step("s08_f125_ledger_rows_still_not_run",
                  f125_rows == {"desktop": "NOT_RUN",
                                "selfhost": "NOT_RUN"},
                  rows=f125_rows)
        base = git("rev-parse", "main").strip()
        zero_drift = {}
        # e16 recon moved under tools/recon/; main still has the pre-move path.
        pairs = (
            ("implementation/python/legal_entry.py",
             "implementation/python/legal_entry.py"),
            ("tools/recon/PENDING_OWNER_e16_cash_contract_recon.py",
             "tools/PENDING_OWNER_e16_cash_contract_recon.py"),
        )
        for rel, main_rel in pairs:
            head_bytes = (REPO_ROOT / rel).read_bytes()
            main_bytes = git("show", "main:" + main_rel).encode("utf-8")
            zero_drift[rel] = (
                sha256_of(head_bytes) == sha256_of(main_bytes))
        self.step("s08_e16_surfaces_byte_equal_main",
                  all(zero_drift.values()), base_main=base[:12],
                  files=zero_drift)

    def e16_behavioral_rerun(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(E16_RECON_TOOL),
             "--profile", self.profile],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=str(REPO_ROOT))
        if proc.returncode == 3:
            self.env_missing = True
            self.step("s09_e16_behavioral_rerun", False,
                      exit_code=3, note="E16 recon reports env missing",
                      tail=proc.stdout.strip().splitlines()[-1][:160]
                      if proc.stdout.strip() else "")
            return
        verdict = None
        ev = (REPO_ROOT / "docs" / "construction" / "evidence" / "E16"
              / self.profile / "e16_cash_contract_recon.json")
        if ev.exists():
            verdict = json.loads(ev.read_text(encoding="utf-8")).get(
                "verdict")
        self.step("s09_e16_behavioral_rerun",
                  proc.returncode == 0 and verdict == "RECON_OK",
                  exit_code=proc.returncode, verdict=verdict,
                  tool="PENDING_OWNER_e16_cash_contract_recon.py")

    # ---- s11 单位 footprint -----------------------------------------
    def unit_footprint(self) -> None:
        merge_base = git("merge-base", "main", "HEAD").strip()
        out = git("diff", "--name-status", merge_base + "..HEAD")
        touched = [ln.split("\t", 1)[1]
                   for ln in out.splitlines() if ln.strip()]
        rel_norm = [p.replace("\\", "/") for p in touched]
        ok_paths = all(
            p in ALLOWED_PATHS
            or any(p.startswith(pre) for pre in ALLOWED_PREFIXES)
            for p in rel_norm)
        ok_forbidden = not any(
            p.startswith(FORBIDDEN_PREFIXES[0])
            or p.lower().endswith(FORBIDDEN_SUFFIXES)
            for p in rel_norm)
        self.step("s11_unit_footprint_prep_only",
                  ok_paths and ok_forbidden,
                  merge_base=merge_base[:12], touched_count=len(rel_norm),
                  outside=[p for p in rel_norm
                           if p not in ALLOWED_PATHS
                           and not any(p.startswith(pre)
                                       for pre in ALLOWED_PREFIXES)][:5],
                  forbidden=[p for p in rel_norm
                             if p.startswith(FORBIDDEN_PREFIXES[0])
                             or p.lower().endswith(FORBIDDEN_SUFFIXES)])

    def run(self) -> int:
        self.registry_face()
        self.not_enabled_negatives()
        self.zero_leak_ast()
        self.billing_redline()
        self.e16_zero_change()
        self.e16_behavioral_rerun()
        self.unit_footprint()
        failed = [c for c in self.checks if c["status"] != "PASS"]
        if failed:
            print("RECON_FAIL[%s]: %d/%d checks failed: %s" % (
                self.profile, len(failed), len(self.checks),
                ",".join(c["check"] for c in failed)), flush=True)
            return 2
        if self.env_missing:
            return 3
        print("[%s] RECON_OK (%d checks, exit 0)" % (
            self.profile, len(self.checks)), flush=True)
        return 0

    def finish_at(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def write_evidence(profile: str, recon: Recon, exit_code: int) -> Path:
    ev_dir = (REPO_ROOT / "docs" / "construction" / "evidence" / "F125"
              / profile)
    ev_dir.mkdir(parents=True, exist_ok=True)
    finished_at = recon.finish_at()
    verdict = "RECON_OK" if exit_code == 0 else (
        "ENV_MISSING" if exit_code == 3 else "RECON_FAIL")
    doc = {
        "schema": "juscite-f125-field-prep-recon/1",
        "unit": "W5-U16",
        "feature": "F125",
        "profile": profile,
        "verdict": verdict,
        "exit_code": exit_code,
        "started_at": recon.started_at,
        "finished_at": finished_at,
        "registry_id": registry.REGISTRY_ID,
        "enabled": registry.ENABLED,
        "interface_gap": registry.META["interface_gap"],
        "billing_redline": registry.META["billing_channel_redline"],
        "recovery_point": registry.META["recovery_point"],
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
        "checks": recon.checks,
    }
    jpath = ev_dir / "f125-field-prep-recon.json"
    jpath.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    lines = [
        "# F125 案管延伸字段准备 recon（%s）" % profile,
        "",
        "- unit: W5-U16 · profile: %s" % profile,
        "- verdict: **%s** (%d checks, exit %d)" % (
            verdict, len(recon.checks), exit_code),
        "- registry: %s · ENABLED=%s · interface_gap=%s" % (
            registry.REGISTRY_ID, registry.ENABLED,
            registry.META["interface_gap"]),
        "- 红线（06 python_entry_binding 逐字）：%s" % REDLINE_PINNED,
        "- 回收点：%s" % registry.META["recovery_point"],
        "- started: %s · finished: %s" % (recon.started_at, finished_at),
        "",
        "| # | check | status |",
        "|---|---|---|",
    ]
    for i, c in enumerate(recon.checks, 1):
        lines.append("| %d | %s | %s |" % (i, c["check"], c["status"]))
    (ev_dir / "f125-field-prep-recon.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    return jpath


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    overall = 0
    for profile in profiles:
        recon = Recon(profile)
        try:
            code = recon.run()
        except Exception as exc:  # noqa: BLE001 ——环境/意外如实具名
            print("RECON_FAIL[%s]: %s: %s" % (
                profile, type(exc).__name__, str(exc)[:200]), flush=True)
            code = 2
        write_evidence(profile, recon, code)
        if code == 3:
            overall = 3 if overall == 0 else overall
        elif code != 0:
            overall = 2
    if overall == 0:
        print("ACCEPTANCE_EXIT 0 (profiles: %s)" % ",".join(profiles),
              flush=True)
    return overall


if __name__ == "__main__":
    sys.exit(main())
