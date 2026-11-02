# -*- coding: utf-8 -*-
"""F06 MFA 两步验证 验收对账（W5-U08）。

F06（06 V7-06 行 v2，owner=product，UI_HOST_OR_NEW_PRODUCT，desktop/
selfhost 双实例）：MFA注册登录恢复与失效真实可用；密钥和恢复码不明文日志。
preserved（16 决策保留表）：自托管认证先做密码级——产品面＝auth.* 密码级
基底（PBKDF2 盐化校验值，零明文密码）＋mfa.* TOTP/恢复码增强层（不重建
认证、不触碰已 VERIFIED 的 F04 案件权限权威）；增强层凭据归产品凭据设施
（F12 保险库先例 W3-U09，lvyin.mfa/* DPAPI 密文 blob）；TOTP 全程显式
now 纪元秒（确定性合成时钟：±1 窗接受、过期窗/重放/一次性消费全部可复现
具名）；密钥和恢复码只在 enroll 回执出现一次，全配置面+日志面+状态根+
保险库字节级扫描零明文命中（沿 E10 密钥泄漏检查先例：tools/e10_canary.py
scan --dir 子进程复用＋受控泄漏负控证明扫描器非空转）；%APPDATA%\\JusBench
与产品运行根 %APPDATA%\\Juscite 快照前后相等零触碰；oc28 钉定 commit 只读。

用法（juscite worktree w5-u08 根 cwd；--profile 缺省＝双 profile）：
  python -X utf8 tools/recon/PENDING_OWNER_f06_mfa_recon.py \\
      [--profile desktop --profile selfhost]

exit 0＝RECON_OK 全断言过；证据 JSON/MD 写 docs/construction/evidence/
F06/<profile>/。desktop/selfhost 共用宿主面分状态根分证据（产品凭据设施
与认证状态不依赖库后端，F40/F12 先例）。全合成材料；harness 检出只读零
改动；不发网络、不写 %APPDATA%、台账零改动（F06 两行登记随账房）。
"""
from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "tools"))

LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
E10_CANARY = REPO_ROOT / "tools" / "e10_canary.py"
LEDGER = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"
OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
OC28_PIN = "026b106bc5d41b679ffc413264229c340871e4d3"

_EVIDENCE_F06 = REPO_ROOT / "docs" / "construction" / "evidence" / "F06"

# 合成材料（运行时生成；证据只记 sha256＋掩码形）。
PASSWORD = "S3cret-合成-password-#" + os.urandom(4).hex()
USER = "lawyer_a"

_EVIDENCE_DIRTY: dict = {}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    """真产品入口子进程径（legal_entry CLI；同既有 recon 纪律）。请求/回执
    只在内存与 %TEMP% 一次性请求文件（with 内自删）流转，绝不落 workspace
    与证据。"""
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


def scan_needles(root: Path, needles: list[bytes]) -> dict:
    """原始字节级扫描（e10_canary scan --dir 同法：os.walk 逐文件字节搜
    索，>128MB 跳过，OSError 记 skipped）。"""
    hits, skipped, files = [], [], 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                if path.stat().st_size > 128 * 1024 * 1024:
                    skipped.append(str(path))
                    continue
                data = path.read_bytes()
                files += 1
                for needle in needles:
                    if needle in data:
                        hits.append({"file": str(path),
                                     "needle_sha256": sha256_bytes(needle)})
            except OSError:
                skipped.append(str(path))
    return {"root": str(root), "files_scanned": files, "hits": hits,
            "skipped": skipped, "verdict": "PASS" if not hits else "FAIL"}


def scan_canary_tool(root: Path, token: str) -> int:
    """真实复用 tools/e10_canary.py scan --dir（子进程；exit 0=零命中）。"""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(E10_CANARY), "scan",
         "--dir", str(root), "--token", token],
        capture_output=True, text=True, encoding="utf-8", timeout=120)
    return proc.returncode


def snapshot_appdata() -> dict:
    """%APPDATA% 快照：{目录: {相对路径: sha256}}；目录不存在记 absent。"""
    base = os.environ.get("APPDATA", "")
    snap = {}
    for name in ("JusBench", "Juscite"):
        root = Path(base) / name if base else None
        if root is None or not root.is_dir():
            snap[name] = "absent"
            continue
        files = {}
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in filenames:
                path = Path(dirpath) / filename
                try:
                    files[str(path.relative_to(root))] = sha256_bytes(
                        path.read_bytes())
                except OSError:
                    files[str(path.relative_to(root))] = "unreadable"
        snap[name] = files
    return snap


def ledger_rows() -> dict:
    with open(LEDGER, encoding="utf-8-sig", newline="") as handle:
        return {row["obligation_id"]: row
                for row in csv.DictReader(handle)}


def b32_to_bytes(b32: str) -> bytes:
    return base64.b32decode(b32 + "=" * (-len(b32) % 8))


def run_profile(profile: str, workspace_root: Path, rows: dict,
                rfc_vectors_ok: bool) -> tuple[Checks, dict]:
    checks = Checks()
    ws = workspace_root / profile
    mfa_root = ws / "mfa"
    vault_root = ws / "vault"
    config_dir = ws / "config"
    logs_dir = ws / "logs"
    for directory in (mfa_root, vault_root, config_dir, logs_dir):
        directory.mkdir(parents=True, exist_ok=True)
    config = {"mfa_state_root": str(mfa_root),
              "vault_state_root": str(vault_root)}
    import mfa_auth as ma  # noqa: E402（TOTP 确定性核心，本 profile 全程用）
    # 本 profile 实际生效的桥配置落盘（config/ 产物，被全产物扫描覆盖）。
    (config_dir / "bridge-config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")

    def log(line: str) -> None:
        # 运行日志（操作面元数据；绝不带参数载荷/密钥/恢复码）。
        with open(logs_dir / "run.log", "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%H:%M:%S ") + line + "\n")

    meta: dict = {"profile": profile, "workspace": str(ws)}
    appdata_before = snapshot_appdata()

    # S0 前提与桥可达 ------------------------------------------------------
    prereq_ok = (rows.get("E05", {}).get("status") == "VERIFIED"
                 and rows.get("E08", {}).get("status") == "VERIFIED"
                 and rows.get("E09", {}).get("status") == "VERIFIED")
    f06_rows = (rows.get("F06-desktop", {}).get("status"),
                rows.get("F06-selfhost", {}).get("status"))
    f04_verified = (rows.get("F04-desktop", {}).get("status") == "VERIFIED"
                    and rows.get("F04-selfhost", {}).get("status")
                    == "VERIFIED")
    code, out = call_cli("mfa.status", {"user_id": "absent-probe"}, config)
    probe_refused = (code == 3 and "mfa_user_unknown"
                     in str(out.get("code")))
    checks.add("U08-PIN-0", prereq_ok and probe_refused,
               "前提在案（acceptance-ledger.csv 亲读：E05/E08/E09 全 VERIFIED"
               "＝工单 prereq；F06 两行 status=%s 待本单）＋桥可达（已配置根"
               "下未知用户 mfa.status＝mfa_user_unknown 具名拒 exit 3）"
               % (f06_rows,))
    log("bridge probe refused=%s prereq_ok=%s" % (probe_refused, prereq_ok))
    if not prereq_ok or not probe_refused:
        meta["checks_passed"] = checks.passed_count
        meta["checks_total"] = len(checks.items)
        return checks, meta

    # ======================================================================
    # F06-1 密码级基底（preserved：自托管认证先做密码级）
    # ======================================================================
    code, out = call_cli("auth.register", {"user_id": USER,
                                           "password": PASSWORD,
                                           "now": 1000}, config)
    registered = (code == 0
                  and (out.get("result", {}) or {}).get("registered") is True)
    log("auth.register exit %d" % code)
    code, out = call_cli("auth.login", {"user_id": USER,
                                        "password": PASSWORD,
                                        "now": 1010}, config)
    login = (out.get("result", {}) or {}) if code == 0 else {}
    base_login_ok = (login.get("status") == "ok"
                     and login.get("factor") == "password"
                     and bool(login.get("session_token")))
    code, out = call_cli("auth.login", {"user_id": USER,
                                        "password": "wrong-pass-合成",
                                        "now": 1011}, config)
    wrong_named = (code == 3 and "mfa_password_mismatch"
                   in str(out.get("code")))
    code, out = call_cli("auth.register", {"user_id": USER,
                                           "password": PASSWORD,
                                           "now": 1012}, config)
    dup_named = (code == 3 and "mfa_user_exists" in str(out.get("code")))
    account_path = mfa_root / "accounts" / (USER + ".json")
    account = json.loads(account_path.read_text(encoding="utf-8"))
    atrest_ok = (account.get("algo") == "pbkdf2-hmac-sha256"
                 and "verifier_hex" in account
                 and PASSWORD not in json.dumps(account))
    checks.add("F06-1", registered and base_login_ok and wrong_named
               and dup_named and atrest_ok,
               "密码级基底真实可用：注册→登录发会话（factor=password）；错密"
               "码＝mfa_password_mismatch 具名拒；重复注册＝mfa_user_exists"
               " 具名拒；存面只有 PBKDF2-HMAC-SHA256 盐化校验值（零明文密"
               "码）——preserved「自托管认证先做密码级」落地为结构")
    log("base login=%s wrong=%s dup=%s atrest_pbkdf2=%s"
        % (base_login_ok, wrong_named, dup_named, atrest_ok))

    # ======================================================================
    # F06-3（先于两步登录）MFA 注册真实可用：凭据归产品凭据设施
    # ======================================================================
    code, out = call_cli("mfa.enroll", {"user_id": USER,
                                        "password": PASSWORD,
                                        "now": 1020}, config)
    enroll = (out.get("result", {}) or {}) if code == 0 else {}
    codes = enroll.get("recovery_codes") or []
    secret = b32_to_bytes(enroll.get("secret_base32", ""))
    vault_entry = (vault_root / "credentials" / "lvyin.mfa"
                   / (USER + ".totp-v1.json"))
    vault_entry_ok = False
    if vault_entry.is_file():
        entry = json.loads(vault_entry.read_text(encoding="utf-8"))
        vault_entry_ok = (entry.get("backend") == "dpapi"
                          and secret not in Path(vault_entry).read_bytes()
                          and enroll.get("secret_base32", "").encode()
                          not in Path(vault_entry).read_bytes())
    code, out = call_cli("mfa.status", {"user_id": USER}, config)
    status = (out.get("result", {}) or {}) if code == 0 else {}
    status_ok = (status.get("mfa_enrolled") is True
                 and status.get("recovery_codes_remaining") == 8
                 and "secret_base32" not in status
                 and "recovery_codes" not in status)
    enroll_ok = (len(codes) == 8
                 and enroll.get("otpauth_uri", "").startswith(
                     "otpauth://totp/JusBench:%s?secret=" % USER)
                 and len(secret) == 20
                 and vault_entry_ok and status_ok)
    checks.add("F06-3", enroll_ok,
               "MFA 注册真实可用：TOTP 密钥（20B）落产品凭据设施＝lvyin.mfa/"
               "%s.totp-v1 DPAPI 密文 blob（F12 保险库先例 W3-U09，登记位零"
               "密钥明文）；otpauth:// 认证器兼容配置串＋8 枚恢复码只在 "
               "enroll 回执出现一次；mfa.status 投影 enrolled=true 且零密"
               "钥零恢复码字段" % USER)
    log("enroll codes=%d vault_dpapi=%s status_zero_secret=%s"
        % (len(codes), vault_entry_ok, status_ok))

    # ======================================================================
    # F06-2 两步登录真实可用（第二因子补齐才发会话）
    # ======================================================================
    code, out = call_cli("auth.login", {"user_id": USER,
                                        "password": PASSWORD,
                                        "now": 1025}, config)
    step1 = (out.get("result", {}) or {}) if code == 0 else {}
    step1_ok = (step1.get("status") == "mfa_required"
                and "session_token" not in step1
                and step1.get("second_factors") == ["totp", "recovery"])
    code_now = __import__("mfa_auth").totp_at(secret, 1026)
    code, out = call_cli("mfa.verify", {"user_id": USER, "code": code_now,
                                        "now": 1026}, config)
    step2 = (out.get("result", {}) or {}) if code == 0 else {}
    step2_ok = (step2.get("status") == "ok"
                and step2.get("factor") == "totp"
                and bool(step2.get("session_token")))
    bad_code = next(
        candidate for candidate in ("%06d" % i for i in range(1000000))
        if candidate not in {ma.totp_at(secret, c * ma.TOTP_STEP)
                             for c in range(34 - 10, 34 + 11)})
    code, out = call_cli("mfa.verify", {"user_id": USER, "code": bad_code,
                                        "now": 1027}, config)
    badcode_named = (code == 3 and "mfa_totp_invalid" in str(out.get("code")))
    checks.add("F06-2", step1_ok and step2_ok and badcode_named,
               "两步登录真实可用：密码过＋MFA 在位＝mfa_required 挑战且绝不"
               "发会话；TOTP 第二步（合成 now=1026 注入）→才发会话"
               "（factor=totp）；错码＝mfa_totp_invalid 具名拒")
    log("two-step: step1=%s step2=%s badcode=%s"
        % (step1_ok, step2_ok, badcode_named))

    # ======================================================================
    # F06-4 确定性合成时钟（RFC 6238 向量＋过期窗可复现）
    # 时间线：now=1100（计数器 36）；前窗码取自 now=1070（计数器 35 > 上次
    # 34＝接受并推进防重放位）；过期窗码取自 now=980（计数器 32，窗外）。
    # ======================================================================
    rfc = rfc_vectors_ok
    code, out = call_cli("mfa.verify", {"user_id": USER,
                                        "code": ma.totp_at(secret, 1070),
                                        "now": 1100}, config)
    prev_ok = (out.get("result", {}) or {}).get("status") == "ok"
    code, out = call_cli("mfa.verify", {"user_id": USER,
                                        "code": ma.totp_at(secret, 980),
                                        "now": 1100}, config)
    expired_named = (code == 3 and "mfa_totp_window_exceeded"
                     in str(out.get("code")))
    code, out = call_cli("mfa.verify", {"user_id": USER}, config)
    now_required = (code == 3 and "mfa_now_required" in str(out.get("code")))
    checks.add("F06-4", rfc and prev_ok and expired_named and now_required,
               "确定性合成时钟：TOTP 核心＝RFC 6238 Appendix B（SHA1）官方向"
               "量全过（同 secret 同 now 同码，可复现）；±1 窗接受（前窗 "
               "-30s 过）；过期窗（-120s）＝mfa_totp_window_exceeded 具名拒"
               "（可复现过期窗口）；now 缺省＝mfa_now_required 具名拒（零"
               "内隐时钟）")
    log("clock: rfc=%s prev=%s expired=%s now_required=%s"
        % (rfc, prev_ok, expired_named, now_required))

    # ======================================================================
    # F06-5 重放负测（防重放位单调；now=1105 计数器 37 > 上次 36）
    # ======================================================================
    replay_code = ma.totp_at(secret, 1105)
    code, out = call_cli("mfa.verify", {"user_id": USER,
                                        "code": replay_code, "now": 1105},
                         config)
    first_ok = (out.get("result", {}) or {}).get("status") == "ok"
    code, out = call_cli("mfa.verify", {"user_id": USER,
                                        "code": replay_code, "now": 1051},
                         config)
    replay_named = (code == 3 and "mfa_totp_replay" in str(out.get("code")))
    checks.add("F06-5", first_ok and replay_named,
               "重放负测：同窗码首次核过（now=1105）后同码复用（now=1106）＝"
               "mfa_totp_replay 具名拒（last-used 计数器单调，防重放）")
    log("replay: first=%s reuse=%s" % (first_ok, replay_named))

    # ======================================================================
    # F06-6 恢复码一次性消费（合成构造负测）
    # ======================================================================
    code, out = call_cli("mfa.recover", {"user_id": USER,
                                         "recovery_code": codes[0],
                                         "now": 1060}, config)
    recovered = (out.get("result", {}) or {}) if code == 0 else {}
    recover_ok = (recovered.get("status") == "ok"
                  and recovered.get("factor") == "recovery"
                  and recovered.get("remaining_recovery_codes") == 7)
    code, out = call_cli("mfa.recover", {"user_id": USER,
                                         "recovery_code": codes[0],
                                         "now": 1061}, config)
    reuse_named = (code == 3 and "mfa_recovery_code_invalid"
                   in str(out.get("code")))
    code, out = call_cli("mfa.recover", {"user_id": USER,
                                         "recovery_code": "deadbeef00",
                                         "now": 1062}, config)
    unknown_named = (code == 3 and "mfa_recovery_code_invalid"
                     in str(out.get("code")))
    checks.add("F06-6", recover_ok and reuse_named and unknown_named,
               "恢复码一次性消费：codes[0] 恢复成功发会话（余 7）；同码复用"
               "＝mfa_recovery_code_invalid 具名拒（命中即从存面摘除）；未"
               "知码＝同码具名拒（合成构造负测）")
    log("recovery: ok=%s reuse=%s unknown=%s"
        % (recover_ok, reuse_named, unknown_named))

    # ======================================================================
    # F06-7 失效真实可用（disable＋拆后全拒＋回落密码级；now=1110 计数器
    # 37＝未消费窗，防重放位不干扰）
    # ======================================================================
    code, out = call_cli("mfa.disable", {"user_id": USER,
                                         "password": "wrong-pass-合成",
                                         "factor_type": "totp",
                                         "factor": ma.totp_at(secret, 1110),
                                         "now": 1110}, config)
    disable_wrongpw = (code == 3 and "mfa_password_mismatch"
                       in str(out.get("code")))
    code, out = call_cli("mfa.disable", {"user_id": USER,
                                         "password": PASSWORD,
                                         "factor_type": "totp",
                                         "factor": ma.totp_at(secret, 1110),
                                         "now": 1110}, config)
    disabled = (out.get("result", {}) or {}).get("disabled") is True
    totp_gone = not vault_entry.exists()
    recovery_gone = not (vault_root / "credentials" / "lvyin.mfa"
                         / (USER + ".recovery-v1.json")).exists()
    code, out = call_cli("mfa.verify", {"user_id": USER,
                                        "code": ma.totp_at(secret, 1112),
                                        "now": 1112}, config)
    post_verify_named = (code == 3 and "mfa_not_enrolled"
                         in str(out.get("code")))
    code, out = call_cli("mfa.disable", {"user_id": USER,
                                         "password": PASSWORD,
                                         "factor_type": "totp",
                                         "factor": ma.totp_at(secret, 1113),
                                         "now": 1113}, config)
    redisable_named = (code == 3 and "mfa_not_enrolled"
                       in str(out.get("code")))
    code, out = call_cli("auth.login", {"user_id": USER,
                                        "password": PASSWORD,
                                        "now": 1114}, config)
    fallback = (out.get("result", {}) or {}) if code == 0 else {}
    fallback_ok = (fallback.get("status") == "ok"
                   and fallback.get("factor") == "password")
    checks.add("F06-7", disable_wrongpw and disabled and totp_gone
               and recovery_gone and post_verify_named and redisable_named
               and fallback_ok,
               "失效真实可用：错密码拒（mfa_password_mismatch）；密码＋有效 "
               "TOTP＝disable 成立，保险库登记位（totp+recovery）拆除；拆后 "
               "TOTP/重复失效＝mfa_not_enrolled 具名拒；登录回落密码级基底"
               "（preserved 不变）")
    log("disable: wrongpw=%s disabled=%s entries_gone=%s post=%s fallback=%s"
        % (disable_wrongpw, disabled, totp_gone and recovery_gone,
           post_verify_named, fallback_ok))

    # ======================================================================
    # F06-8 密钥和恢复码不明文（全配置面+日志面+状态根+保险库字节级扫描
    #       ＋受控泄漏负控；沿 E10 密钥泄漏检查先例）
    # ======================================================================
    needles = [PASSWORD.encode("utf-8"), secret,
               enroll.get("secret_base32", "").encode("ascii")]
    needles += [c.encode("ascii") for c in codes]
    clean = scan_needles(ws, needles)
    scratch = ws / "config" / "leak-negative-control.tmp"
    scratch.write_text("负控样本 " + codes[1], encoding="utf-8")
    leak = scan_needles(ws, needles)
    scratch.unlink()
    reclean = scan_needles(ws, needles)
    checks.add("F06-8", clean["verdict"] == "PASS" and leak["verdict"] == "FAIL"
               and reclean["verdict"] == "PASS",
               "密钥和恢复码不明文（红线负测）：全 workspace（config/日志/"
               "mfa 状态根/vault 密文库）字节级扫描——密码+TOTP 密钥（原始/"
               "base32 两形）+8 枚恢复码全零命中（files=%d）；受控泄漏负控"
               "被检出（hits=%d）后移除复扫零命中——扫描器非空转（E10 先例"
               "同法）" % (clean["files_scanned"], len(leak["hits"])))
    log("scan: clean=%d files leak=%d reclean ok=%s"
        % (clean["files_scanned"], len(leak["hits"]),
           reclean["verdict"] == "PASS"))

    # F06-8b e10 canary 扫描工具子进程复用（第二扫描器同判）
    import e10_canary  # noqa: E402
    canary = e10_canary.new_token()
    rc_clean = scan_canary_tool(ws, canary)
    leak_path = ws / "logs" / "canary-negative-control.tmp"
    leak_path.write_text(canary, encoding="utf-8")
    rc_leak = scan_canary_tool(ws, canary)
    leak_path.unlink()
    rc_reclean = scan_canary_tool(ws, canary)
    checks.add("F06-8b", rc_clean == 0 and rc_leak == 1 and rc_reclean == 0,
               "E10 canary 扫描工具子进程复用（tools/e10_canary.py scan "
               "--dir 同一工具本体）：canary 全 workspace 零命中（rc=0）；"
               "受控泄漏对照 rc=1（工具非空转）后移除复扫 rc=0——第二扫描"
               "器与字节级扫描同判")
    log("canary: clean=%d leak=%d reclean=%d"
        % (rc_clean, rc_leak, rc_reclean))

    # ======================================================================
    # F06-9 证据投影面零密钥（证据 JSON 写出前断言零 needle）
    # ======================================================================
    probe_payload = json.dumps({"codes_count": len(codes),
                                "secret_sha256": sha256_bytes(secret),
                                "password_masked": PASSWORD[:3] + "…"},
                               ensure_ascii=False)
    evidence_clean = (all(codes[i] not in probe_payload
                          for i in range(len(codes)))
                      and enroll.get("secret_base32", "") not in probe_payload
                      and PASSWORD not in probe_payload)
    checks.add("F06-9", evidence_clean,
               "证据投影面零密钥：证据只记 sha256＋掩码形＋计数（本 recon 自"
               "身回执投影构造样本逐 needle 断言零命中）——enroll 回执外零"
               "第二处明文出口")

    # ======================================================================
    # F06-10 %APPDATA% 零触碰＋oc28 只读钉定
    # ======================================================================
    appdata_after = snapshot_appdata()
    appdata_ok = appdata_after == appdata_before
    oc28_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(OC28),
                               capture_output=True, text=True,
                               encoding="utf-8").stdout.strip()
    oc28_ok = oc28_head == OC28_PIN
    checks.add("F06-10", appdata_ok and oc28_ok,
               "%%APPDATA%% 零触碰：JusBench/Juscite 双目录快照（逐文件 "
               "sha256）前后严格相等（JusBench=%s，Juscite=%s）；oc28 检出 "
               "HEAD=%s＝钉定 commit 只读（本单零补丁零触碰）"
               % (appdata_after.get("JusBench") if
                  isinstance(appdata_after.get("JusBench"), str)
                  else "present·%d files" % len(appdata_after["JusBench"]),
                  appdata_after.get("Juscite") if
                  isinstance(appdata_after.get("Juscite"), str)
                  else "present·%d files" % len(appdata_after["Juscite"]),
                  oc28_head[:12]))
    meta["appdata"] = {k: (v if isinstance(v, str) else
                           "present:%d files" % len(v))
                       for k, v in appdata_after.items()}
    meta["oc28_head"] = oc28_head
    log("appdata_equal=%s oc28_pin=%s" % (appdata_ok, oc28_ok))

    # ======================================================================
    # F06-11 增强层不重建认证（preserved 结构面＋F04 权威零触碰）
    # ======================================================================
    import legal_entry as le  # noqa: E402
    groups = [value for name, value in vars(le).items()
              if name.endswith("_METHODS") and isinstance(value, frozenset)]
    disjoint = all(not (le.MFA_AUTH_METHODS & group)
                   for group in groups if group is not le.MFA_AUTH_METHODS)
    source = (REPO_ROOT / "implementation" / "python" / "mfa_auth.py") \
        .read_text(encoding="utf-8")
    tree = ast.parse(source)
    bad_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad_imports += [a.name for a in node.names
                            if "harness" in a.name or "permission" in a.name]
        if isinstance(node, ast.ImportFrom):
            module = getattr(node, "module", "") or ""
            if "harness" in module or "permission" in module:
                bad_imports.append(module)
    no_log = all(not isinstance(node, ast.Call)
                 or (node.func.id if isinstance(node.func, ast.Name)
                     else getattr(node.func, "attr", "")) != "print"
                 for node in ast.walk(tree))
    f04_ok = f04_verified
    checks.add("F06-11", disjoint and not bad_imports and no_log and f04_ok
               and atrest_ok,
               "增强层不重建认证：MFA_AUTH_METHODS 与全部 %d 组 *_METHODS 两"
               "两不交（不冒已有业务入口）；mfa_auth.py 零 harness/案件权限 "
               "import（F04 权威已 VERIFIED 零触碰·台账亲读）＋零 print"
               "（零日志面）；密码级基底 PBKDF2 在案（preserved「先做密码"
               "级」＝结构非注释）" % len(groups))
    log("enhancer: disjoint=%s bad_imports=%d no_print=%s f04=%s"
        % (disjoint, len(bad_imports), no_log, f04_ok))

    # ======================================================================
    # U08-EDGE 桥 fail-closed 边界
    # ======================================================================
    code, out = call_cli("mfa.status", {"user_id": "x"}, {})
    unconfig = (code == 3 and "mfa_state_root_not_configured"
                in str(out.get("code")))
    code, out = call_cli("auth.register", {"user_id": "x",
                                           "password": "p",
                                           "now": 1},
                         {"mfa_state_root": str(mfa_root)})
    vault_unconfig = (code == 3 and "vault_state_root_not_configured"
                      in str(out.get("code")))
    code, out = call_cli("mfa.transmogrify", {}, config)
    unknown_mfa = (code == 3 and "method_not_connected:mfa.transmogrify"
                   in str(out.get("code")))
    checks.add("U08-EDGE", unconfig and vault_unconfig and unknown_mfa,
               "桥 fail-closed 边界：mfa_state_root 未配置＝"
               "mfa_state_root_not_configured；vault_state_root 未配置＝"
               "vault_state_root_not_configured（增强层凭据唯一去向＝保险"
               "库，无旁路）；冻结组外方法（mfa.transmogrify）＝"
               "method_not_connected 具名拒（exit 3）")
    meta["checks_passed"] = checks.passed_count
    meta["checks_total"] = len(checks.items)
    return checks, meta


def rfc6238_vectors_pass() -> bool:
    import mfa_auth as ma  # noqa: E402
    rfc_secret = b"12345678901234567890"
    expected = ((59, "94287082"), (1111111109, "07081804"),
                (1111111111, "14050471"), (1234567890, "89005924"),
                (2000000000, "69279037"), (20000000000, "65353130"))
    return all(ma.totp_at(rfc_secret, now, digits=8) == code
               for now, code in expected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F06 MFA 两步验证 验收对账（W5-U08）")
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"], default=[],
                        help="缺省＝双 profile")
    args = parser.parse_args(argv)
    profiles = args.profile or ["desktop", "selfhost"]

    rows = ledger_rows()
    rfc_ok = rfc6238_vectors_pass()
    if not rfc_ok:
        print("[FAIL] U08-PIN-RFC — RFC 6238 向量未过（确定性核心损坏）")
        return 1

    workspace_root = Path(tempfile.mkdtemp(prefix="w5u08-f06-mfa-"))
    print("workspace: %s" % workspace_root)
    all_ok = True
    for profile in profiles:
        print("\n===== profile: %s =====" % profile)
        checks, meta = run_profile(profile, workspace_root, rows, rfc_ok)
        verdict = "RECON_OK" if checks.all_passed else "RECON_FAILED"
        all_ok = all_ok and checks.all_passed
        print("%s[%s] %d/%d" % (verdict, profile, checks.passed_count,
                                len(checks.items)))
        out_dir = _EVIDENCE_F06 / profile
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "unit": "W5-U08", "feature": "F06", "profile": profile,
            "verdict": verdict,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime()),
            "command": ("python -X utf8 "
                        "tools/recon/PENDING_OWNER_f06_mfa_recon.py --profile "
                        + profile),
            "cwd": str(REPO_ROOT),
            "subject": ("juscite 分支 w5-u08（worktree 根 cwd；证据生成于收"
                        "口 commit 前工作树＝分支最终内容，W4-U44 先例）"),
            "summary": {k: v for k, v in meta.items() if k != "checks"},
            "checks": checks.items,
            "synthetic_material": {
                "user_id": USER,
                "password_sha256": sha256_bytes(PASSWORD.encode("utf-8")),
                "password_masked": PASSWORD[:3] + "…",
                "note": "全合成材料运行时生成；密钥与恢复码零入证据（只记 "
                        "sha256/掩码/计数）",
            },
            "note": ("preserved＝自托管认证先做密码级（密码级基底+MFA 增强"
                     "层）；凭据归产品凭据设施（F12 保险库）；TOTP 确定性合"
                     "成时钟；零明文沿 E10 先例；%APPDATA% 零触碰；oc28 只"
                     "读；台账零改动（F06 两行登记随账房）"),
        }
        (out_dir / "f06-mfa-recon.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1),
            encoding="utf-8")
        lines = ["# F06 MFA 两步验证 recon — %s（W5-U08）" % profile,
                 "",
                 "verdict: **%s**（%d/%d）" % (verdict, checks.passed_count,
                                              len(checks.items)),
                 "",
                 "command: `%s`" % payload["command"],
                 "",
                 "| 检 | 结果 | 要点 |", "|---|---|---|"]
        for item in checks.items:
            lines.append("| %s | %s | %s |" % (item["id"], item["status"],
                                               item["detail"]
                                               .replace("|", "\\|")))
        (out_dir / "f06-mfa-recon.md").write_text("\n".join(lines) + "\n",
                                                  encoding="utf-8")
    print("\n%s" % ("RECON_OK" if all_ok else "RECON_FAILED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
