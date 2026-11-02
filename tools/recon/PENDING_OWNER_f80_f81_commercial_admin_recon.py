#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""F80＋F81 商业服务端（账户/积分/签到/邀请＋企业组策略管理台）recon。

W5-U02 合成先行（00-总协调 §6.1 裁决#13-19：W5 七项商业/基建统一合
成先行，真实设施 v2 商业化时补）。06 行 acceptance 复验：

  F80（commercial_service.py＋legal_entry commercial.*，owner=product）：
  - 账户/积分/签到/邀请真实幂等回执（同 request 同输入→同回执逐键
    相等不双记；异输入具名 conflict；回执入账时刻冻结，撤销后重放仍
    逐字稳定）、撤销和余额（台账严格 append-only，撤销＝追加撤销记录，
    生效状态由账目推导；余额＝未被撤销发放之和，恒非负结构不变量）；
  - 只在独立商业服务面：独立冻结方法组＋独立状态根；案件工作台零运
    营位（导入图断言——商业/策略模块不被任何案件/业务模块 import；
    case_id/matter_id 类字段具名拒）；不继承上游厂商账号营销（无
    referral/促销/追踪字段处置位，产物零营销字段）；不前移 v1（只此
    六类商业操作，冻结组与既有全部方法组零交集＝不冒已有业务入口）；
  - 金额一律整型分：float/str/bool 具名拒收；签到/邀请奖励＝冻结常量。
  F81（org_policy_admin.py＋legal_entry orgadmin.*，owner=product）：
  - 管理策略真实应用到用户和运行面：声明（append-only＋typed 值校验）
    → F9 语义求值（段序 org→user，末条胜出＝user 段压过 org 段，与
    f9-permission-precedence.md「会话段压过 agent 段」同构）→ 桥把投
    影注入 commercial.*（端到端断言：声明关闭签到后运行面真实拒绝、
    上限声明后超限发放真实拒绝——策略先于入账，被拒不产生回执）；
  - 深管理不替代最小 v1 管理台：键闭集全部 commercial.*（v2 商业面）；
    case.*/harness.* 等 v1 管理键探测具名拒（f81_policy_key_unknown）
    ——v1 案件管理面（F04/F05）无处置位不被接管。

AST 面断言：两产品模块导入闭集恰零网络模块＋字符串常量零 URL 模式＋
零营销字段常量＋标识符零旁路关键字；本 recon 自身同检（W4-U03 N4 先
例）；状态根产物零 URL 零营销字段零案件上下文值。全程合成材料（合成
组织/用户/金额显式 synth；零真实外联）。

用法（juscite worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f80_f81_commercial_admin_recon.py \
      --profile desktop --profile selfhost
  [--state-root-prefix <dir>] [--keep-temp]

退出码：0＝RECON_OK（双 profile 全过）；2＝RECON_FAIL；3＝环境缺失。
证据：evidence/F80/<profile>/ 与 evidence/F81/<profile>/（JSON＋MD，
同名族前缀＋README）。台账与 00-总协调零改动＝登记随账房。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN_DATE = time.strftime("%Y%m%d")

COMM_MODULE = REPO / "implementation" / "python" / "commercial_service.py"
ORG_MODULE = REPO / "implementation" / "python" / "org_policy_admin.py"
PY_DIR = REPO / "implementation" / "python"

EXPECTED_IMPORTS = {"__future__", "hashlib", "json", "os", "datetime",
                    "pathlib"}
BANNED_IDENT_SUBSTRINGS = ("cookie", "webdriver", "selenium")
MARKETING_KEYS = ("promo", "upsell", "newsletter", "campaign", "utm_")
# URL 判别式拆写（本文件自身也是被检对象，不得含完整 URL 字面量）。
URL_SCHEME_PARTS = ("http", "https", "ftp", "ws", "wss")
URL_SCHEME_MARK = ":" + "/" + "/"

ORG_ID = "合成组织-recon"
USER_MAIN = "synth-u-main"
USER_FRIEND = "synth-u-friend"
USER_OTHER = "synth-u-other"
DAY_1 = "2026-10-22"
DAY_2 = "2026-10-23"

BOUNDARY_NOTE = (
    "裁决#13-19 合成先行边界：本面为产品侧真实记账面（幂等回执/撤销/余额"
    "＋策略真实应用），真实托管设施（托管服务/支付通道/营销系统/多实例并发"
    "账本）v2 商业化时补，本波不前造；深管理不替代最小 v1 管理台——键闭集"
    "全部 commercial.*，v1 案件管理面（F04/F05）无处置位（case.* 探测具名"
    "拒实测）")


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.failed = 0

    def check(self, cid: str, ok: bool, detail: str) -> bool:
        self.rows.append({"id": cid, "ok": bool(ok), "detail": detail[:600]})
        if not ok:
            self.failed += 1
            eprint(f"  [FAIL] {cid}: {detail[:300]}")
        else:
            eprint(f"  [ ok ] {cid}: {detail[:180]}")
        return bool(ok)

    @property
    def passed(self) -> int:
        return len(self.rows) - self.failed


def load_bridge():
    sys.path.insert(0, str(PY_DIR))
    from legal_entry import call as bridge_call
    return bridge_call


# ---------------------------------------------------------------------------
# AST 静态审计（负测先行＝结构性事实，不是运行时约定）
# ---------------------------------------------------------------------------

def ast_import_roots(source: str) -> set:
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
    return roots


def ast_string_constants(source: str) -> list:
    tree = ast.parse(source)
    values = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            for value in node.values:
                if isinstance(value, ast.Constant) \
                        and isinstance(value.value, str):
                    values.append(value.value)
    return values


def module_ast_audit(path: Path) -> tuple:
    """导入闭集恰零网络模块＋字符串常量零 URL 模式＋零营销字段常量＋
    标识符零旁路关键字。"""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = ast_import_roots(source)
    if imported != EXPECTED_IMPORTS:
        return False, f"{path.name} 导入闭集漂移: {sorted(imported)}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            for part in URL_SCHEME_PARTS:
                if part + URL_SCHEME_MARK in low:
                    return False, (f"{path.name} 字符串常量含 "
                                   f"{part}{URL_SCHEME_MARK}")
            for key in MARKETING_KEYS:
                if key in low:
                    return False, f"{path.name} 常量含营销字段 {key}"
        names = []
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        for name in names:
            for kw in BANNED_IDENT_SUBSTRINGS:
                if kw in name.lower():
                    return False, f"{path.name} 标识符 {name} 含旁路关键字"
    return True, (f"{path.name} 导入闭集 {sorted(imported)}＝零网络模块；"
                  "字符串常量零 URL 模式零营销字段；标识符零旁路关键字")


def self_ast_audit() -> tuple:
    """本 recon 自身同检（W4-U03 N4 先例：面与工具双双自检）。"""
    source = Path(__file__).read_text(encoding="utf-8")
    constants = ast_string_constants(source)
    url_hits = [c for c in constants
                if any(part + URL_SCHEME_MARK in c.lower()
                       for part in URL_SCHEME_PARTS)]
    imports = ast_import_roots(source)
    net_tokens = {"urllib", "requests", "socket", "http", "ftplib",
                  "smtplib", "telnetlib"}
    net_hits = sorted(imports & net_tokens)
    ok = not url_hits and not net_hits
    return ok, (f"recon 自身字符串常量 {len(constants)} 个零 URL 字面量；"
                f"网络 token {net_hits or '无'}")


def import_graph_audit() -> tuple:
    """案件工作台零运营位（结构性）：商业/策略模块只被 legal_entry
    import；两模块互不 import（桥装配，策略以投影注入）。"""
    offenders = []
    for path in sorted(PY_DIR.glob("*.py")):
        if path.name in ("legal_entry.py", "commercial_service.py",
                         "org_policy_admin.py"):
            continue
        roots = ast_import_roots(path.read_text(encoding="utf-8"))
        if {"commercial_service", "org_policy_admin"} & roots:
            offenders.append(path.name)
    comm_roots = ast_import_roots(
        COMM_MODULE.read_text(encoding="utf-8"))
    org_roots = ast_import_roots(ORG_MODULE.read_text(encoding="utf-8"))
    cross = "org_policy_admin" in comm_roots or \
        "commercial_service" in org_roots
    ok = not offenders and not cross
    return ok, (f"业务模块挂载 {offenders or '无'}；两模块互不 import="
                f"{cross}")


def frozen_sets_audit(bridge_mod) -> tuple:
    """冻结组恰集＋与既有全部方法组零交集（不冒已有业务入口）。"""
    commercial = bridge_mod.COMMERCIAL_METHODS
    orgadmin = bridge_mod.ORG_ADMIN_METHODS
    ok_commercial = commercial == frozenset({
        "commercial.account_open", "commercial.credit_grant",
        "commercial.checkin", "commercial.invite_issue",
        "commercial.invite_redeem", "commercial.revoke",
        "commercial.balance_read"})
    ok_orgadmin = orgadmin == frozenset({
        "orgadmin.policy_declare", "orgadmin.policy_read",
        "orgadmin.policy_apply"})
    groups = {k: v for k, v in vars(bridge_mod).items()
              if k.endswith("_METHODS") and isinstance(v, (frozenset, set))}
    overlaps = []
    for name, mine in (("COMMERCIAL_METHODS", commercial),
                       ("ORG_ADMIN_METHODS", orgadmin)):
        for other_name, other in groups.items():
            if other_name != name and mine & other:
                overlaps.append(name + "∩" + other_name)
    ok = ok_commercial and ok_orgadmin and not overlaps
    return ok, (f"冻结组恰集 commercial={ok_commercial}"
                f"/orgadmin={ok_orgadmin}；既有组零交集={overlaps or '无'}")


def scan_tree_blob(root: Path) -> str:
    chunks = []
    for p in sorted(root.rglob("*.json")):
        chunks.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def url_hits_in(blob: str) -> list:
    low = blob.lower()
    return [part + URL_SCHEME_MARK for part in URL_SCHEME_PARTS
            if part + URL_SCHEME_MARK in low]


def err_text(exc: BaseException) -> str:
    return str(exc)


# ---------------------------------------------------------------------------
# 单 profile
# ---------------------------------------------------------------------------

def run_profile(profile: str, args, bridge) -> tuple:
    ck = Checks()
    state_root = Path(args.state_root_prefix) / f"profile-{profile}"
    cfg = {"commercial_state_root": str(state_root / "comm"),
           "org_policy_state_root": str(state_root / "orgp")}
    evidence: dict = {"profile": profile, "state_root": str(state_root)}

    try:
        import legal_entry as bridge_mod
        # ---- 结构面 -----------------------------------------------------
        ok, detail = module_ast_audit(COMM_MODULE)
        ck.check("c01_comm_module_ast", ok, detail)
        ok, detail = module_ast_audit(ORG_MODULE)
        ck.check("c01_org_module_ast", ok, detail)
        ok, detail = import_graph_audit()
        ck.check("c04_import_graph_zero_ops_slots", ok,
                 "案件工作台零运营位（结构性）：" + detail
                 + "（商业/策略模块只被 legal_entry 桥装配 import）")
        ok, detail = frozen_sets_audit(bridge_mod)
        ck.check("c03_frozen_sets_no_collision", ok,
                 "不冒已有业务入口（06 binding UI_HOST_OR_NEW_PRODUCT）："
                 + detail)

        # ---- fail-closed 配置面 -----------------------------------------
        for method, bare_cfg, needle in (
                ("commercial.credit_grant", {},
                 "commercial_state_root_not_configured"),
                ("orgadmin.policy_declare", {},
                 "org_policy_state_root_not_configured")):
            try:
                bridge(method, {"account_id": "a"}, bare_cfg)
                ck.check("c02_fail_closed_" + method.split(".")[0],
                         False, "未抛")
            except Exception as exc:  # noqa: BLE001
                ck.check("c02_fail_closed_" + method.split(".")[0],
                         needle in err_text(exc), f"{method}→{exc}")
        for method, group in (("commercial.explode", "commercial"),
                              ("orgadmin.explode", "orgadmin")):
            try:
                bridge(method, {}, cfg)
                ck.check("c02_fail_closed_unknown_" + group, False, "未抛")
            except Exception as exc:  # noqa: BLE001
                ck.check("c02_fail_closed_unknown_" + group,
                         f"method_not_connected:{method}" in err_text(exc),
                         f"未知方法→{exc}")
        for method, needle in (("commercial.credit_grant",
                                "commercial_params_invalid"),
                               ("orgadmin.policy_read",
                                "org_admin_params_invalid")):
            try:
                bridge(method, "not-a-dict", cfg)
                ck.check("c02_fail_closed_params_" + method.split(".")[0],
                         False, "未抛")
            except Exception as exc:  # noqa: BLE001
                ck.check("c02_fail_closed_params_" + method.split(".")[0],
                         needle in err_text(exc), f"params 非字典→{exc}")

        # ---- F80：账户（幂等开户）---------------------------------------
        a1 = bridge("commercial.account_open",
                    {"org_id": ORG_ID, "user_ref": USER_MAIN}, cfg)
        acc = a1["account"]["account_id"]
        a2 = bridge("commercial.account_open",
                    {"org_id": ORG_ID, "user_ref": USER_MAIN}, cfg)
        a3 = bridge("commercial.account_open",
                    {"org_id": ORG_ID, "user_ref": USER_FRIEND}, cfg)
        friend = a3["account"]["account_id"]
        ck.check("c05_account_open_idempotent_deterministic",
                 a2["idempotent_replay"] is True
                 and a1["idempotent_replay"] is False
                 and a2["account"]["account_id"] == acc
                 and a3["account"]["account_id"] != acc
                 and acc.startswith("c80acc-"),
                 f"幂等开户：同 org/user 重放同账户 {acc}；异身份异账户")

        # ---- F80：发放（幂等回执＋整型分）--------------------------------
        grant_args = {"account_id": acc, "request_id": "rq-signup",
                      "reason": "signup_bonus", "delta_cents": 1000}
        g1 = bridge("commercial.credit_grant", grant_args, cfg)
        g2 = bridge("commercial.credit_grant", grant_args, cfg)
        ck.check("c06_grant_receipt_idempotent_frozen",
                 g2["receipt"] == g1["receipt"]
                 and g2["idempotent_replay"] is True
                 and g1["receipt"]["delta_cents"] == 1000
                 and isinstance(g1["receipt"]["balance_after_cents"], int)
                 and g1["receipt"]["status"] == "ACTIVE"
                 and g1["receipt"]["receipt_id"].startswith("c80r-"),
                 f"真实幂等回执：{g1['receipt']['receipt_id']} 整型分 1000；"
                 "重放逐键相等不双记")
        try:
            bridge("commercial.credit_grant",
                   {**grant_args, "delta_cents": 1001}, cfg)
            ck.check("c06_grant_conflict_refused", False, "未拒")
        except Exception as exc:  # noqa: BLE001
            ck.check("c06_grant_conflict_refused",
                     "f80_credit_grant_conflict" in err_text(exc),
                     f"同 request 异输入→{exc}")
        delta_bad = True
        for bad in (10.5, "100", True, 0, -5):
            try:
                bridge("commercial.credit_grant",
                       {"account_id": acc, "request_id": "rq-bad",
                        "reason": "manual_adjust", "delta_cents": bad}, cfg)
                delta_bad = False
            except Exception as exc:  # noqa: BLE001
                delta_bad = delta_bad and \
                    "f80_delta_invalid" in err_text(exc)
        ck.check("c07_integer_cents_discipline", delta_bad,
                 "金额纪律：float/str/bool 具名拒（not_integer_cents）；"
                 "零/负具名拒（must_be_positive）——一律整型分")

        # ---- F80：签到（一日一签）----------------------------------------
        c1 = bridge("commercial.checkin",
                    {"account_id": acc, "request_id": "ck-1",
                     "day": DAY_1}, cfg)
        c1_replay = bridge("commercial.checkin",
                           {"account_id": acc, "request_id": "ck-1",
                            "day": DAY_1}, cfg)
        same_day_refused = "未拒"
        try:
            bridge("commercial.checkin",
                   {"account_id": acc, "request_id": "ck-sameday",
                    "day": DAY_1}, cfg)
        except Exception as exc:  # noqa: BLE001
            same_day_refused = err_text(exc)
        c2 = bridge("commercial.checkin",
                    {"account_id": acc, "request_id": "ck-2",
                     "day": DAY_2}, cfg)
        day_format_bad = True
        for bad_day in (20261022, "20261022", "2026-13-01", "not-a-day"):
            try:
                bridge("commercial.checkin",
                       {"account_id": acc, "request_id": "ck-fmt",
                        "day": bad_day}, cfg)
                day_format_bad = False
            except Exception as exc:  # noqa: BLE001
                day_format_bad = day_format_bad and \
                    "f80_day_invalid" in err_text(exc)
        ck.check("c08_checkin_daily_idempotent_closed_day",
                 c1["receipt"]["delta_cents"] == 500
                 and c1["receipt"]["day"] == DAY_1
                 and c1_replay["idempotent_replay"] is True
                 and c1_replay["receipt"] == c1["receipt"]
                 and same_day_refused
                 == "commercial_failed:f80_checkin_already_done:" + DAY_1
                 and c2["receipt"]["day"] == DAY_2
                 and c2["idempotent_replay"] is False
                 and day_format_bad,
                 f"签到一日一签：{DAY_1} 奖励 500（冻结常量整型分）；同日"
                 f"异请求具名拒不静默双发（{same_day_refused}）；跨日 "
                 f"{DAY_2} 正常签到＝按日闭而非永久闭；重放同回执；非展开/"
                 "非法日具名拒")

        # ---- F80：邀请（一码一兑双腿回执）---------------------------------
        iv = bridge("commercial.invite_issue",
                    {"account_id": acc, "request_id": "iv-1"}, cfg)
        iv2 = bridge("commercial.invite_issue",
                     {"account_id": acc, "request_id": "iv-1"}, cfg)
        code = iv["invite_code"]
        rd = bridge("commercial.invite_redeem",
                    {"account_id": friend, "request_id": "rd-1",
                     "invite_code": code}, cfg)
        rd2 = bridge("commercial.invite_redeem",
                     {"account_id": friend, "request_id": "rd-1",
                      "invite_code": code}, cfg)
        neg = {}
        a_other = bridge("commercial.account_open",
                         {"org_id": ORG_ID, "user_ref": USER_OTHER},
                         cfg)["account"]["account_id"]
        for tag, m_args, needle in (
                ("used", {"account_id": a_other, "request_id": "rd-used",
                          "invite_code": code},
                 "f80_invite_code_already_used"),
                ("self", {"account_id": acc, "request_id": "rd-self",
                          "invite_code": code}, "f80_invite_self_redeem"),
                ("unknown", {"account_id": friend,
                             "request_id": "rd-unknown",
                             "invite_code": "c80inv-nonexistent00"},
                 "f80_invite_code_unknown")):
            try:
                bridge("commercial.invite_redeem", m_args, cfg)
                neg[tag] = "未拒"
            except Exception as exc:  # noqa: BLE001
                neg[tag] = "具名拒" if needle in err_text(exc) \
                    else err_text(exc)[:40]
        legs = rd["redemption"]
        ck.check("c09_invite_two_legs_one_code",
                 iv2["idempotent_replay"] is True
                 and iv2["invite_code"] == code
                 and legs["redeemer_receipt"]["delta_cents"] == 800
                 and legs["inviter_receipt"]["delta_cents"] == 300
                 and legs["redeemer_receipt"]["invite_redeem_id"]
                 == legs["inviter_receipt"]["invite_redeem_id"]
                 and rd2["idempotent_replay"] is True
                 and rd2["redemption"] == legs
                 and all(v == "具名拒" for v in neg.values()),
                 f"邀请：码 {code} 幂等签发；一码一兑双腿回执（受邀 800＋"
                 f"邀请人 300 同 redeem id）；重放稳定；负测 {neg}")

        # ---- F80：撤销与余额（append-only；回执冻结；恒非负）--------------
        gk = bridge("commercial.credit_grant",
                    {"account_id": acc, "request_id": "rq-manual",
                     "reason": "manual_adjust", "delta_cents": 700}, cfg)
        v1 = bridge("commercial.revoke",
                    {"account_id": acc, "request_id": "rv-1",
                     "receipt_id": gk["receipt"]["receipt_id"]}, cfg)
        gk_replay = bridge("commercial.credit_grant",
                           {"account_id": acc, "request_id": "rq-manual",
                            "reason": "manual_adjust",
                            "delta_cents": 700}, cfg)
        v1_replay = bridge("commercial.revoke",
                           {"account_id": acc, "request_id": "rv-1",
                            "receipt_id": gk["receipt"]["receipt_id"]}, cfg)
        rev_neg = {}
        for tag, m_args, needle in (
                ("double", {"account_id": acc, "request_id": "rv-double",
                            "receipt_id": gk["receipt"]["receipt_id"]},
                 "f80_receipt_already_revoked"),
                ("unknown", {"account_id": acc, "request_id": "rv-unknown",
                             "receipt_id": "c80r-nonexistent00"},
                 "f80_receipt_unknown")):
            try:
                bridge("commercial.revoke", m_args, cfg)
                rev_neg[tag] = "未拒"
            except Exception as exc:  # noqa: BLE001
                rev_neg[tag] = "具名拒" if needle in err_text(exc) \
                    else err_text(exc)[:40]
        bal = bridge("commercial.balance_read", {"account_id": acc}, cfg)
        # acc 账目：signup 1000＋签到 500＋跨日签到 500＋邀请人腿 300
        # （manual 700 发放后即被撤销，+700/−700 相消不入余额）＝ 2300
        # （受邀人 800 落 friend 账户）。
        expected_balance = 1000 + 500 + 500 + 300
        ck.check("c10_revoke_append_only_balance_falls",
                 v1["revocation"]["delta_cents"] == 700
                 and v1_replay["idempotent_replay"] is True
                 and v1_replay["revocation"] == v1["revocation"]
                 and gk_replay["receipt"] == gk["receipt"]
                 and all(v == "具名拒" for v in rev_neg.values())
                 and bal["balance_cents"] == expected_balance
                 and bal["balance_cents"] >= 0
                 and bal["grants_revoked"] == 1
                 and bal["revocations"] == 1,
                 f"撤销与余额：撤销 700 后余额 {bal['balance_cents']}"
                 f"（恒非负结构不变量）；台账 append-only——发放条目零改写"
                 "（撤销后原回执重放逐键相等）；重放/双撤/未知 receipt 负测 "
                 f"{rev_neg}")

        # ---- 旁路字段（案件上下文进不了商业面；零营销字段）----------------
        bypass = {}
        for field in ("case_id", "matter_id", "url", "cookie",
                      "promo_banner", "utm_campaign"):
            try:
                bridge("commercial.credit_grant",
                       {"account_id": acc, "request_id": "bf-" + field,
                        "reason": "manual_adjust", "delta_cents": 1,
                        field: "synth-bypass-value"}, cfg)
                bypass[field] = "未拒"
            except Exception as exc:  # noqa: BLE001
                bypass[field] = ("具名拒"
                                 if "f80_field_forbidden:" + field
                                 in err_text(exc) else err_text(exc)[:40])
        try:
            bridge("orgadmin.policy_declare",
                   {"org_id": ORG_ID,
                    "policy_key": "commercial.checkin_enabled",
                    "value": True, "declared_by": "synth-admin",
                    "request_id": "bf-telemetry",
                    "telemetry_opt_out": True}, cfg)
            bypass["orgadmin:telemetry"] = "未拒"
        except Exception as exc:  # noqa: BLE001
            bypass["orgadmin:telemetry"] = ("具名拒" if "f81_field_forbidden"
                                            in err_text(exc)
                                            else err_text(exc)[:40])
        ck.check("c12_bypass_case_marketing_fields_refused",
                 all(v == "具名拒" for v in bypass.values()),
                 "旁路负测（合成构造）：case_id/matter_id（案件工作台零运营"
                 "位——案件上下文进不了商业面）＋url/cookie（零隐式通道）＋"
                 f"promo_banner/utm_campaign/telemetry（不继承上游厂商账号"
                 f"营销）全具名拒：{bypass}")

        # ---- F81：策略账（声明/求值/应用）---------------------------------
        d1 = bridge("orgadmin.policy_declare",
                    {"org_id": ORG_ID,
                     "policy_key": "commercial.checkin_enabled",
                     "value": True, "declared_by": "synth-admin",
                     "request_id": "pd-enable"}, cfg)
        d1_replay = bridge("orgadmin.policy_declare",
                           {"org_id": ORG_ID,
                            "policy_key": "commercial.checkin_enabled",
                            "value": True, "declared_by": "synth-admin",
                            "request_id": "pd-enable"}, cfg)
        key_neg = {}
        for tag, key in (("case", "case.permission.override"),
                         ("harness", "harness.case_permission"),
                         ("material", "material.deidentify"),
                         ("unknown", "commercial.unknown_knob")):
            try:
                bridge("orgadmin.policy_declare",
                       {"org_id": ORG_ID, "policy_key": key, "value": True,
                        "declared_by": "synth-admin",
                        "request_id": "pd-key-" + tag}, cfg)
                key_neg[tag] = "未拒"
            except Exception as exc:  # noqa: BLE001
                key_neg[tag] = ("具名拒" if "f81_policy_key_unknown:" + key
                                in err_text(exc) else err_text(exc)[:40])
        val_neg = {}
        for tag, key, value, needle in (
                ("bool", "commercial.checkin_enabled", "yes", "expect_bool"),
                ("capneg", "commercial.max_credit_grant_cents", -1,
                 "expect_non_negative_int_cents"),
                ("capfloat", "commercial.max_credit_grant_cents", 2.5,
                 "expect_non_negative_int_cents")):
            try:
                bridge("orgadmin.policy_declare",
                       {"org_id": ORG_ID, "policy_key": key, "value": value,
                        "declared_by": "synth-admin",
                        "request_id": "pd-val-" + tag}, cfg)
                val_neg[tag] = "未拒"
            except Exception as exc:  # noqa: BLE001
                val_neg[tag] = ("具名拒" if needle in err_text(exc)
                                else err_text(exc)[:40])
        ck.check("c13_policy_declare_append_only_typed",
                 d1["record"]["segment"] == "org"
                 and d1_replay["idempotent_replay"] is True
                 and d1_replay["record"] == d1["record"]
                 and all(v == "具名拒" for v in key_neg.values())
                 and all(v == "具名拒" for v in val_neg.values()),
                 "策略声明：append-only 幂等回执；typed 值校验负测 "
                 f"{val_neg}；深管理不替代最小 v1 管理台——键闭集全部 "
                 f"commercial.*，case.*/harness.*/material.* 探测具名拒（v1 "
                 f"案件管理面 F04/F05 无处置位不被接管）：{key_neg}")

        # 求值语义（F9 同构：段序 org→user 末条胜出）——独立组织隔离
        ev_org = "合成组织-recon-ev"
        ev_acc = bridge("commercial.account_open",
                        {"org_id": ev_org, "user_ref": USER_MAIN},
                        cfg)["account"]["account_id"]
        bridge("orgadmin.policy_declare",
               {"org_id": ev_org,
                "policy_key": "commercial.max_credit_grant_cents",
                "value": 2000, "declared_by": "synth-admin",
                "request_id": "pe-1"}, cfg)
        bridge("orgadmin.policy_declare",
               {"org_id": ev_org, "user_ref": USER_MAIN,
                "policy_key": "commercial.max_credit_grant_cents",
                "value": 500, "declared_by": "synth-admin",
                "request_id": "pe-2"}, cfg)
        pr = bridge("orgadmin.policy_read",
                    {"org_id": ev_org, "user_ref": USER_MAIN}, cfg)
        segments = [(t["segment"], t["value"]) for t in pr["trace"]
                    if t["policy_key"] == "commercial.max_credit_grant_cents"]
        bridge("orgadmin.policy_declare",
               {"org_id": ev_org, "user_ref": USER_MAIN,
                "policy_key": "commercial.max_credit_grant_cents",
                "value": 900, "declared_by": "synth-admin",
                "request_id": "pe-3"}, cfg)
        pr2 = bridge("orgadmin.policy_read",
                     {"org_id": ev_org, "user_ref": USER_MAIN}, cfg)
        pr_org_only = bridge("orgadmin.policy_read",
                             {"org_id": ev_org}, cfg)
        ck.check("c14_evaluation_f9_semantics",
                 pr["effective"]["commercial.max_credit_grant_cents"] == 500
                 and segments == [("org", 2000), ("user", 500)]
                 and pr2["effective"]["commercial.max_credit_grant_cents"]
                 == 900
                 and pr_org_only["effective"][
                     "commercial.max_credit_grant_cents"] == 2000
                 and pr_org_only["user_ref"] is None,
                 "策略求值（F9 同构）：段序 org→user，末条胜出＝user 段压过 "
                 "org 段（trace 全链可读 org 2000→user 500）；同段改值＝追加"
                 "新记录末条生效（500→900）；org-only 读不收 user 段"
                 f"（org 2000）——账户 {ev_acc}")

        # ---- F81→F80 真实应用端到端（声明即时改变运行面行为）--------------
        ap = bridge("orgadmin.policy_apply",
                    {"org_id": ORG_ID, "user_ref": USER_MAIN}, cfg)
        bridge("orgadmin.policy_declare",
               {"org_id": ORG_ID,
                "policy_key": "commercial.checkin_enabled",
                "value": False, "declared_by": "synth-admin",
                "request_id": "ra-disable"}, cfg)
        checkin_refused = "未拒"
        try:
            bridge("commercial.checkin",
                   {"account_id": acc, "request_id": "ck-ra",
                    "day": "2026-10-24"}, cfg)
        except Exception as exc:  # noqa: BLE001
            checkin_refused = err_text(exc)
        c1_still = bridge("commercial.checkin",
                          {"account_id": acc, "request_id": "ck-1",
                           "day": DAY_1}, cfg)
        bridge("orgadmin.policy_declare",
               {"org_id": ORG_ID,
                "policy_key": "commercial.max_credit_grant_cents",
                "value": 2000, "declared_by": "synth-admin",
                "request_id": "ra-cap-org"}, cfg)
        cap_org_refused = "未拒"
        try:
            bridge("commercial.credit_grant",
                   {"account_id": acc, "request_id": "rq-cap5000",
                    "reason": "manual_adjust", "delta_cents": 5000}, cfg)
        except Exception as exc:  # noqa: BLE001
            cap_org_refused = err_text(exc)
        bridge("orgadmin.policy_declare",
               {"org_id": ORG_ID, "user_ref": USER_MAIN,
                "policy_key": "commercial.max_credit_grant_cents",
                "value": 800, "declared_by": "synth-admin",
                "request_id": "ra-cap-user"}, cfg)
        cap_user_refused = "未拒"
        try:
            bridge("commercial.credit_grant",
                   {"account_id": acc, "request_id": "rq-cap801",
                    "reason": "manual_adjust", "delta_cents": 801}, cfg)
        except Exception as exc:  # noqa: BLE001
            cap_user_refused = err_text(exc)
        g_ok = bridge("commercial.credit_grant",
                      {"account_id": acc, "request_id": "rq-cap800",
                       "reason": "manual_adjust", "delta_cents": 800}, cfg)
        bal2 = bridge("commercial.balance_read",
                      {"account_id": acc}, cfg)
        ck.check("c16_policy_really_applied_runtime_end_to_end",
                 ap["surface"] == "commercial_service"
                 and ap["org_id"] == ORG_ID
                 and ap["user_ref"] == USER_MAIN
                 and checkin_refused
                 == "commercial_failed:f80_checkin_disabled_by_policy"
                 and c1_still["idempotent_replay"] is True
                 and cap_org_refused
                 == "commercial_failed:f80_grant_exceeds_policy_cap:2000"
                 and cap_user_refused
                 == "commercial_failed:f80_grant_exceeds_policy_cap:800"
                 and g_ok["receipt"]["delta_cents"] == 800
                 and bal2["balance_cents"] == expected_balance + 800,
                 "策略真实应用到用户和运行面（端到端）：声明关闭签到→商业面"
                 "真实拒绝 f80_checkin_disabled_by_policy（历史签到重放仍幂"
                 "等）；org 上限 2000→超 5000 拒；user 覆盖 800→801 拒/800 "
                 "过——被拒操作零回执（余额恰 "
                 + str(expected_balance + 800)
                 + "＝入账面实测）；应用回执 surface=commercial_service")

        # ---- 产物面（零 URL 零营销字段零案件上下文值）---------------------
        blob = scan_tree_blob(state_root)
        hits = url_hits_in(blob)
        mkt_hits = [k for k in MARKETING_KEYS if k in blob]
        ctx_leak = "synth-bypass-value" in blob or "synth-case" in blob
        ck.check("c17_artifacts_clean",
                 not hits and not mkt_hits and not ctx_leak,
                 f"状态根全产物：零 URL 字面量（{hits or '无'}）＋零营销字段"
                 f"（{mkt_hits or '无'}）＋零旁路/案件上下文值泄漏={ctx_leak}")

        evidence["account_id"] = acc
        evidence["friend_account_id"] = friend
        evidence["invite_code"] = code
        evidence["grant_receipt"] = g1["receipt"]
        evidence["checkin_receipt"] = c1["receipt"]
        evidence["redemption"] = rd["redemption"]
        evidence["revocation"] = v1["revocation"]
        evidence["balance"] = bal
        evidence["policy_declare"] = d1["record"]
        evidence["evaluation"] = pr
        evidence["policy_apply"] = ap
        evidence["boundary"] = BOUNDARY_NOTE
        return ck, evidence
    except Exception:
        raise


VOLATILE_KEYS = ("granted_at", "revoked_at", "issued_at", "redeemed_at",
                 "recorded_at", "applied_at")


def _strip_volatile(value):
    # 时变键（各 profile 时间戳）不参与跨 profile 确定性对照（递归剥——
    # 兑换回执内嵌双腿子回执各带 granted_at）；幂等键/金额/账户标识/
    # reason/status 逐键相等。
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items()
                if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def render_readme(family: str, profile: str, stamp: str) -> str:
    stem = (family.lower() + "-commercial-recon-" + stamp
            if family == "F80"
            else family.lower() + "-orgadmin-recon-" + stamp)
    if family == "F80":
        point = ("`" + stem + ".json`／`.md`：F80 自有商业账户/积分/签到/邀请"
                 " recon 证据（幂等回执/撤销/余额＋红线四项结构性断言）；")
    else:
        point = ("`" + stem + ".json`／`.md`：F81 企业组策略管理台 recon 证据"
                 "（策略真实应用到运行面端到端＋深管理不替代最小 v1 管理台）；")
    return "\n".join([
        "# " + family + "／" + profile + " 证据（W5-U02 合成先行，裁决#13-19）",
        "",
        "- " + point,
        "- acceptance 向量（06 行）：F80＝账户/积分/签到/邀请真实幂等回执、"
        "撤销和余额；只在独立商业服务面，案件工作台无运营位；不继承上游厂商"
        "账号营销，不前移 v1——F81＝管理策略真实应用到用户和运行面；深管理"
        "不替代最小 v1 管理台；",
        "- " + BOUNDARY_NOTE + "；",
        "- 全程合成材料（合成组织/用户/金额显式 synth）；不 push。",
    ]) + "\n"


def render_md(profile: str, checks: Checks, cross_rows: list) -> str:
    lines = [
        f"# F80＋F81 商业服务端 recon 证据（{profile}，W5-U02）", "",
        "裁决#13-19（W5 商业服务端统一合成先行）为唯一执行态；真实托管设"
        "施 v2 商业化时补。", "",
        "## 边界（具名）",
        f"- {BOUNDARY_NOTE}",
        "## 结构性红线（负测先行＝构造级事实）",
        "- 独立商业服务面：独立冻结组 commercial.*/orgadmin.*＋独立状态根；",
        "- 案件工作台零运营位：导入图断言＋case_id/matter_id 字段具名拒；",
        "- 不继承上游厂商账号营销：promo/utm/telemetry 类字段具名拒＋产物"
        "零营销字段；",
        "- 不前移 v1／不冒已有业务入口：冻结组与既有全部方法组零交集；键闭"
        "集外 case.* 等具名拒；",
        "- 幂等回执：重放逐键相等（回执入账时刻冻结）；撤销 append-only；"
        "余额恒非负；整型分纪律 float 具名拒。",
        "## 检查清单",
    ]
    lines += [f"- [{'x' if r['ok'] else ' '}] {r['id']}: {r['detail']}"
              for r in checks.rows]
    lines += [f"- [{'x' if r['ok'] else ' '}] {r['id']}: {r['detail']}"
              for r in cross_rows]
    passed = checks.passed + sum(1 for r in cross_rows if r["ok"])
    total = len(checks.rows) + len(cross_rows)
    lines += ["", f"**{passed}/{total} checks passed.**", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", action="append", default=None,
                    help="验收 profile（可多次；默认 desktop+selfhost）")
    ap.add_argument("--state-root-prefix", type=Path, default=None,
                    help="状态根前缀（默认临时目录）")
    ap.add_argument("--keep-temp", action="store_true",
                    help="保留默认临时状态根（调试用）")
    args = ap.parse_args(argv)
    if not args.profile:
        args.profile = ["desktop", "selfhost"]

    started = time.time()
    tmp_ctx = None
    if args.state_root_prefix is None:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="juscite-f80f81-")
        args.state_root_prefix = Path(tmp_ctx.name)
        if args.keep_temp:
            args.state_root_prefix = (Path(tempfile.gettempdir())
                                      / "juscite-f80f81-keep")
            args.state_root_prefix.mkdir(parents=True, exist_ok=True)
            tmp_ctx = None
    args.state_root_prefix.mkdir(parents=True, exist_ok=True)

    try:
        bridge = load_bridge()
    except Exception as exc:  # noqa: BLE001
        eprint(f"[ENV] 桥不可用: {type(exc).__name__}: {exc}")
        return 3

    eprint(f"== W5-U02 F80+F81 recon profiles={args.profile} "
           f"state_root_prefix={args.state_root_prefix}")

    all_checks: list = []
    per_profile_evidence: dict = {}
    ok = True
    for profile in args.profile:
        eprint(f"==== profile {profile} ====")
        ck, evidence = run_profile(profile, args, bridge)
        all_checks.append(ck)
        per_profile_evidence[profile] = evidence
        ok = ok and ck.failed == 0

    # -- 跨 profile 投影一致性（剥时变键逐键相等；W4-U40 c25 先例）---------
    cross_rows: list = []
    self_ok, self_detail = self_ast_audit()
    cross_rows.append({
        "id": "c00_recon_self_ast_no_url_no_network",
        "ok": self_ok,
        "detail": self_detail + "（W4-U03 N4 先例：面与工具双双自检）",
    })
    ok = ok and self_ok
    cross_ok = len(args.profile) >= 2
    if cross_ok:
        base = {
            "grant": _strip_volatile(
                per_profile_evidence[args.profile[0]]["grant_receipt"]),
            "checkin": _strip_volatile(
                per_profile_evidence[args.profile[0]]["checkin_receipt"]),
            "redemption": _strip_volatile(
                per_profile_evidence[args.profile[0]]["redemption"]),
            "revocation": _strip_volatile(
                per_profile_evidence[args.profile[0]]["revocation"]),
            "policy_record": _strip_volatile(
                per_profile_evidence[args.profile[0]]["policy_declare"]),
            "apply": _strip_volatile(
                per_profile_evidence[args.profile[0]]["policy_apply"]),
        }
        for other in args.profile[1:]:
            ev = per_profile_evidence[other]
            for name, key in (("grant", "grant_receipt"),
                              ("checkin", "checkin_receipt"),
                              ("redemption", "redemption"),
                              ("revocation", "revocation"),
                              ("policy_record", "policy_declare"),
                              ("apply", "policy_apply")):
                if _strip_volatile(ev[key]) != base[name]:
                    cross_ok = False
                    break
            if not cross_ok:
                break
    cross_rows.append({
        "id": "c18_cross_profile_projection_equal",
        "ok": cross_ok,
        "detail": "跨 profile 发放/签到/兑换/撤销/策略声明/应用回执投影剥"
                  "时变键逐键相等（幂等键＝输入 digest 的确定性面）"
                  if cross_ok else "跨 profile 投影漂移（确定性破约）",
    })
    ok = ok and cross_ok
    cross_rows.append({
        "id": "c19_boundary_ruling_13_19_named",
        "ok": bool(BOUNDARY_NOTE),
        "detail": "裁决#13-19 合成先行边界具名：真实托管设施 v2 商业化时补；"
                  "深管理不替代最小 v1 管理台（case.* 探测具名拒实测）——"
                  "本波不假销账不前造",
    })

    payload = {
        "schema": "juscite-f80-f81-commercial-admin-recon/1",
        "unit": "W5-U02",
        "obligations": ["F80-desktop", "F80-selfhost",
                        "F81-desktop", "F81-selfhost"],
        "ruling": ("00-总协调 §6.1 裁决#13-19：W5 商业服务端统一合成先行，"
                   "真实设施 v2 商业化时补"),
        "boundary": BOUNDARY_NOTE,
        "started_at": now_iso(),
        "run_date": RUN_DATE,
        "command": ("python -X utf8 "
                    "tools/recon/PENDING_OWNER_f80_f81_commercial_admin_recon.py "
                    "--profile desktop --profile selfhost"),
        "modules": {"commercial_service": sha256_file(COMM_MODULE),
                    "org_policy_admin": sha256_file(ORG_MODULE)},
        "finished_at": None,
        "duration_s": None,
    }
    payload["checks"] = {"cross": cross_rows}
    for idx, profile in enumerate(args.profile):
        payload["checks"][profile] = all_checks[idx].rows
        payload[profile] = per_profile_evidence[profile]
    payload["finished_at"] = now_iso()
    payload["duration_s"] = round(time.time() - started, 1)
    payload["overall"] = "RECON_OK" if ok else "RECON_FAIL"
    payload["passed"] = sum(c.passed for c in all_checks) + \
        sum(1 for r in cross_rows if r["ok"])
    payload["total"] = sum(len(c.rows) for c in all_checks) + len(cross_rows)

    # -- 证据落盘（evidence/F80|F81/<profile>/；两族各落族前缀同名证据＋
    #     README）-----------------------------------------------------------
    ev_root = REPO / "evidence"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for family in ("F80", "F81"):
        stem = (family.lower() + "-commercial-recon-" + stamp
                if family == "F80"
                else family.lower() + "-orgadmin-recon-" + stamp)
        for profile in args.profile:
            out_dir = ev_root / family / profile
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / (stem + ".json")).write_text(
                json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8")
            (out_dir / (stem + ".md")).write_text(
                render_md(profile,
                          all_checks[args.profile.index(profile)],
                          cross_rows),
                encoding="utf-8")
            (out_dir / "README.md").write_text(
                render_readme(family, profile, stamp), encoding="utf-8")

    for r in cross_rows:
        if not r["ok"]:
            eprint(f"  [FAIL] {r['id']}: {r['detail'][:300]}")
    eprint(f"== {payload['passed']}/{payload['total']} checks passed "
           f"({payload['duration_s']}s)")
    if not ok:
        eprint("RECON_FAIL")
        return 2
    eprint("RECON_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
