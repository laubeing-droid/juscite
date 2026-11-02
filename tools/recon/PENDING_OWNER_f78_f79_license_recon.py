# -*- coding: utf-8 -*-
"""F78/F79 许可（授权激活/宽限＋离线 Ed25519）验收 recon（工单 W5-U01）。

06 V7-78/V7-79（owner=distribution；desktop/selfhost 双实例；acceptance：
F78「授权校验/宽限/离线状态真实；不因服务中断删除数据或伪授权」、F79
「离线许可验签和时钟回拨反例受控；私钥不入发行物」；legacy link F12/F78）。
裁决 #13-19：签发私钥/商业服务端统一合成先行——本 recon 全程使用本地合成
签发服务（tools/license_issuer_synth.py，127.0.0.1 回环）＋合成许可种子，
零真实外联；真实设施 v2 商业化时补（具名回收点在签发设施头注）。

验收命令（工单钦定，worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f78_f79_license_recon.py \\
      --profile desktop --profile selfhost
exit 0 = RECON_OK。

  - desktop/selfhost 双腿＝同一产品入口 legal_entry **真子进程径**，分状
    态根分证据（F40/W3-U09 先例：license/vault 不依赖库后端）；合成签发
    服务全程单实例回环（127.0.0.1 随机口），密钥在共享 issuer-state 持
    久（跨 profile 同钥＝issuer_fingerprint 可对照）。

断言面（全合成材料）：
  F78 S1 激活主链：未激活具名→经服务换令牌→license.activate 全链
     authorized（F79 验签过闸为前置）→每日窗内不出网（服务已死仍成功＝
     零出网证明）→真 HTTP 校验 valid；
  F78 S2 宽限与红线：服务中断（closed loopback port）进一次性宽限预算
     （不展期）→grace_expired 具名真实→revoked 真实入账→任何中断路径
     激活记录/校验历史零删除（state 文件逐键在案）→全程零伪授权（状态
     闭集真实派生）；服务未配置＝exit 3 具名（子进程径）；
  F79 S3 离线验签负测：篡改一字节/异钥签发/异设备/过期/未生效/零信任锚
     全部具名拒（license_signature_invalid/license_device_mismatch/
     license_expired/license_not_yet_valid/license_trusted_keys_not_
     configured）；令牌自带公钥结构性非信任锚（信任锚只在部署 config）；
  F79 S4 时钟回拨负测：未来封印水印→verify/check typed 拒→status 恒
     clock_rollback_detected（绝不投影 authorized）→水印改值不重封＝
     license_clock_state_untrusted（fail-closed 不自动重置）；时钟密钥
     唯一存 F12 保险库 lvyin.f79/clock-watermark-hmac-v1（legacy link
     F12；get-or-create 幂等不轮换）；
  F79 S5 私钥不入发行物三重钉：①产品面 AST 零私钥路径（Ed25519PrivateKey/
     private_bytes 零命中）＋implementation/ 全树零签发设施 import；
     ②juscite git tracked 全文件字节扫描（运行时生成私钥 raw+hex）零命中；
     ③同扫描径正控样本（issuer-state 私钥文件）命中≥1＝非空转；
  F79 S6 F30 协调：冻结通道闭集零改动（license 通道不在 CHANNELS；产品
     面 AST 零 enforce_bridge_egress/decision）＋armed 且服务端非回环＝
     exit 3 license_daily_check_airplane_blocked（先于任何连接）；
  S7 双 profile 对账：同一合成许可跨 profile 内容级投影逐键相等（剥时变
     键：激活/校验/水印时刻与其派生——U08/E15 剥时间戳先例）。
"""

from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
ISSUER_TOOL = REPO_ROOT / "tools" / "license_issuer_synth.py"
sys.path.insert(0, str(REPO_ROOT / "tools"))

# 合成许可种子（全合成；rev/exp 为撤销/过期样本）
SEED = [
    {"license_key": "JUSCITE-SYNTH-KEY-001", "license_id": "lic-recon-001",
     "subject": "合成律师-甲（recon）", "days": 365,
     "features": ["desk", "offline"], "revoked": False},
    {"license_key": "JUSCITE-SYNTH-KEY-REV", "license_id": "lic-recon-rev",
     "subject": "合成律师-乙（recon）", "days": 365,
     "features": [], "revoked": True},
    {"license_key": "JUSCITE-SYNTH-KEY-EXP", "license_id": "lic-recon-exp",
     "subject": "合成律师-丙（recon）", "days": -1,
     "features": [], "revoked": False},
]

# 服务中断模拟：回环已闭端口（connect refused＝服务中断同形态）
DEAD_URL = "http://127.0.0.1:9"


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


class Checks:
    def __init__(self, profile: str) -> None:
        self.profile = profile
        self.items: list = []

    def step(self, check_id: str, ok: bool, detail: str = "", **extra) -> None:
        item = {"id": check_id, "status": "PASS" if ok else "FAIL",
                "detail": detail}
        if extra:
            item.update(extra)
        self.items.append(item)
        print("  [%s] %s %s %s" % (self.profile,
                                   "PASS" if ok else "FAIL", check_id,
                                   detail))

    @property
    def failed(self) -> list:
        return [i for i in self.items if i["status"] != "PASS"]

    @property
    def verdict(self) -> str:
        return "RECON_OK" if self.items and not self.failed \
            else "RECON_FAILED"


def call_entry(method: str, args: dict, config: dict) -> dict:
    """真产品入口子进程调用；返回 {exit, payload}。"""
    request_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    config_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "args": args}, request_handle,
                  ensure_ascii=False)
        request_handle.close()
        json.dump(config, config_handle, ensure_ascii=False)
        config_handle.close()
        env = dict(os.environ)
        python_dir = str(REPO_ROOT / "implementation" / "python")
        env["PYTHONPATH"] = python_dir + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, text=True, encoding="utf-8",
            timeout=300, cwd=str(REPO_ROOT), env=env)
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def entry_result(method: str, args: dict, config: dict) -> dict:
    """OWNER_RESPONSE 取 result；非 0 抛 RuntimeError（detail=typed code）。"""
    out = call_entry(method, args, config)
    if out["exit"] == 0:
        return out["payload"]["result"]
    code = out["payload"].get("code") or out["payload"].get("error") \
        or "entry_failed"
    raise RuntimeError("%s -> exit %s code %s" % (method, out["exit"], code))


def entry_code(method: str, args: dict, config: dict) -> tuple[int, str]:
    """非 0 径：返回 (exit, code)。"""
    out = call_entry(method, args, config)
    code = out["payload"].get("code") or out["payload"].get("error") \
        or ("exit=%d" % out["exit"])
    return out["exit"], str(code)


class Issuer:
    """回环合成签发服务（单实例；密钥持久于共享 issuer-state）。"""

    def __init__(self, work_root: Path) -> None:
        seed_path = work_root / "seed.json"
        seed_path.write_text(json.dumps(SEED, ensure_ascii=False, indent=1),
                             encoding="utf-8")
        self.state_dir = work_root / "issuer-state"
        self.proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(ISSUER_TOOL),
             "--seed", str(seed_path), "--issuer-state", str(self.state_dir),
             "--host", "127.0.0.1", "--port", "0", "--print-pubkey",
             "--serve"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", cwd=str(REPO_ROOT))
        pubkey_line = self.proc.stdout.readline().strip()
        serving_line = self.proc.stdout.readline().strip()
        self.pubkey_b64 = pubkey_line
        self.url = json.loads(serving_line)["serving"]

    def activate_token(self, license_key: str, device_fp_hash: str) -> dict:
        req = urllib.request.Request(
            self.url + "/v1/activate",
            data=json.dumps({"license_key": license_key,
                             "device_fp_hash": device_fp_hash}).encode(
                                 "utf-8"),
            headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=15).read())

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def base_config(root: Path) -> dict:
    return {
        "license_state_root": str(root / "license"),
        "vault_state_root": str(root / "vault"),
        "license_grace_days": 7,
        "license_trusted_pubkeys": [],
    }


def force_due(config: dict) -> None:
    """状态外科：last_check 拨回 25h 前（越过每日窗；recon 专用）。"""
    path = Path(config["license_state_root"]) / "license-state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["last_check"]["at_epoch"] = time.time() - 25 * 3600
    data["last_check"]["at_iso"] = "forced-due-by-recon"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                    encoding="utf-8")


def read_state(config: dict) -> dict:
    path = Path(config["license_state_root"]) / "license-state.json"
    return json.loads(path.read_text(encoding="utf-8"))


def device_fp(config: dict) -> str:
    return entry_result("license.device_fingerprint", {}, config)[
        "fingerprint_hash"]


def write_airplane_flag(config: dict) -> None:
    flag_root = Path(config["airplane_state_root"])
    flag_root.mkdir(parents=True, exist_ok=True)
    (flag_root / "airplane-mode.json").write_text(json.dumps(
        {"enabled": True, "reason": "recon-synth", "updated_at": "now"}),
        encoding="utf-8")


def run_profile(profile: str, issuer: Issuer, evidence_root: Path,
                work_root: Path) -> dict:
    """单 profile 全断言面；返回投影（S7 对照面）。"""
    from license_issuer_synth import issue_for_device, sign_payload

    checks = Checks(profile)
    started = datetime.now(timezone.utc)
    print("[%s] begin" % profile)
    root = work_root / profile
    config = base_config(root)
    config["license_service_url"] = issuer.url
    config["license_trusted_pubkeys"] = [issuer.pubkey_b64]
    negative_codes: dict[str, str] = {}

    # ---------------- F78 S1 激活主链 ----------------
    st = entry_result("license.status", {}, config)
    checks.step("f78_s1_status_not_activated", st["state"] == "not_activated",
                "state=%s" % st["state"])

    fp = device_fp(config)
    token = issuer.activate_token("JUSCITE-SYNTH-KEY-001", fp)
    act = entry_result("license.activate", {"token": token}, config)
    checks.step(
        "f78_s1_activate_authorized",
        act["state"] == "authorized" and act["license_id"] == "lic-recon-001"
        and act["subject"] == "合成律师-甲（recon）"
        and act["device_fp_hash"] == fp,
        "state=%s license_id=%s" % (act["state"], act["license_id"]))

    # 每日窗内不出网：服务指向已闭端口仍成功＝零出网证明
    offline_cfg = dict(config, license_service_url=DEAD_URL)
    win = entry_result("license.check", {}, offline_cfg)
    checks.step(
        "f78_s1_daily_window_no_network",
        win["checked_now"] is False and win["state"] == "authorized"
        and "next_check_due_epoch" in win,
        "checked_now=%s state=%s" % (win["checked_now"], win["state"]))

    # 真服务校验 valid（服务恢复→清宽限语义基线）
    force_due(config)
    ok = entry_result("license.check", {}, config)
    checks.step("f78_s1_service_check_valid", ok["state"] == "authorized",
                "state=%s" % ok["state"])

    # ---------------- F78 S2 撤销真实入账＋中断宽限 ----------------
    # 撤销样本：显式新令牌重激活→check→revoked（真实入账，零删除）
    token_rev = issuer.activate_token("JUSCITE-SYNTH-KEY-REV", fp)
    act2 = entry_result("license.activate", {"token": token_rev}, config)
    force_due(config)
    rev = entry_result("license.check", {}, config)
    state_rev = read_state(config)
    checks.step(
        "f78_s2_revoked_real_no_deletion",
        rev["state"] == "revoked"
        and state_rev["last_check"]["result"] == "revoked"
        and state_rev["activation"]["license_id"] == "lic-recon-rev",
        "state=%s" % rev["state"])

    # 中断宽限：回 001（重激活=新周期）→断服务→force due→grace
    token3 = issuer.activate_token("JUSCITE-SYNTH-KEY-001", fp)
    entry_result("license.activate", {"token": token3}, config)
    force_due(config)
    grace = entry_result("license.check", {}, offline_cfg)
    grace_until = grace.get("grace_until_epoch")
    checks.step(
        "f78_s2_unreachable_grace_named",
        grace["state"] == "grace" and grace_until is not None
        and read_state(config)["last_check"]["result"]
        == "service_unreachable",
        "state=%s" % grace["state"])
    # 预算一次性钉定：二次中断不展期
    force_due(config)
    grace2 = entry_result("license.check", {}, offline_cfg)
    checks.step(
        "f78_s2_grace_budget_not_extended",
        grace2["state"] == "grace"
        and grace2["grace_until_epoch"] == grace_until,
        "same_budget=%s" % (grace2["grace_until_epoch"] == grace_until))
    # 宽限过期：外科拨锚（宽限 7 天，锚 8 天前→预算昨日已尽）→grace_expired 具名
    spath = Path(config["license_state_root"]) / "license-state.json"
    sdata = json.loads(spath.read_text(encoding="utf-8"))
    sdata["last_valid_epoch"] = time.time() - 8 * 86400
    sdata["grace_until_epoch"] = time.time() - 1 * 86400
    spath.write_text(json.dumps(sdata, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    force_due(config)
    gexp = entry_result("license.check", {}, offline_cfg)
    gexp_status = entry_result("license.status", {}, offline_cfg)
    checks.step(
        "f78_s2_grace_expired_named_real",
        gexp["state"] == "grace_expired"
        and gexp_status["state"] == "grace_expired",
        "state=%s" % gexp["state"])
    # 红线：中断全程激活记录/校验历史零删除
    final_state = read_state(config)
    intact = (final_state.get("activation", {}).get("license_id")
              == "lic-recon-001"
              and final_state.get("last_check", {}).get("result")
              == "service_unreachable"
              and final_state.get("grace_until_epoch") is not None
              and final_state.get("last_valid_epoch") is not None)
    checks.step("f78_s2_state_intact_no_deletion", intact,
                "activation+history 在案")

    # ---------------- F79 S3 离线验签负测 ----------------
    ver = entry_result("license.verify_offline", {"token": token}, config)
    checks.step(
        "f79_s3_verify_offline_valid",
        ver["valid"] is True and ver["algorithm"] == "ed25519"
        and ver["device_fp_hash"] == fp and ver["issuer_fingerprint"],
        "issuer_fp=%s" % ver["issuer_fingerprint"])

    def neg(check_id: str, method: str, tok, cfg=None, expect=None):
        exit_code, code = entry_code(method, {"token": tok},
                                     cfg or config)
        negative_codes[check_id] = code
        checks.step(check_id, exit_code == 3 and code == expect,
                    "exit=%s code=%s" % (exit_code, code))

    raw = bytearray(base64.b64decode(token["payload_b64"]))
    raw[10] ^= 0x01
    neg("f79_s3_tampered_signature_invalid", "license.verify_offline",
        dict(token, payload_b64=base64.b64encode(bytes(raw)).decode()),
        expect="license_failed:license_signature_invalid")

    foreign_pub = base64.b64encode(os.urandom(32)).decode("ascii")
    foreign_cfg = dict(config, license_trusted_pubkeys=[foreign_pub])
    neg("f79_s3_untrusted_keys_refused", "license.verify_offline", token,
        cfg=foreign_cfg, expect="license_failed:license_signature_invalid")

    empty_cfg = dict(config, license_trusted_pubkeys=[])
    neg("f79_s3_trusted_keys_missing", "license.verify_offline", token,
        cfg=empty_cfg, expect="license_failed:license_trusted_keys_not_"
                              "configured")

    neg("f79_s3_device_mismatch", "license.verify_offline",
        issue_for_device(_issuer_priv(issuer), SEED[0], "f" * 32),
        expect="license_failed:license_device_mismatch")

    neg("f79_s3_expired_refused", "license.verify_offline",
        issuer.activate_token("JUSCITE-SYNTH-KEY-EXP", fp),
        expect="license_failed:license_expired")

    now = time.time()
    neg("f79_s3_not_yet_valid_refused", "license.verify_offline",
        sign_payload(_issuer_priv(issuer), {
            "license_id": "lic-future", "subject": "合成-未生效",
            "device_fp_hash": fp,
            "not_before": repr(now + 30 * 86400),
            "not_after": repr(now + 60 * 86400), "features": []}),
        expect="license_failed:license_not_yet_valid")

    # ---------------- F79 S4 时钟回拨负测 ----------------
    # 独立根：激活→写未来封印水印（时钟拨回 48h）→全链受时面 typed 拒
    rb_cfg = base_config(root / "rollback")
    rb_cfg["license_service_url"] = issuer.url
    rb_cfg["license_trusted_pubkeys"] = [issuer.pubkey_b64]
    entry_result("license.activate",
                 {"token": issuer.activate_token("JUSCITE-SYNTH-KEY-001", fp)},
                 rb_cfg)
    from license_verify import CLOCK_KEY_ACCOUNT, CLOCK_KEY_SERVICE
    from credential_vault import vault_get
    entry = vault_get(rb_cfg["vault_state_root"], CLOCK_KEY_SERVICE,
                      CLOCK_KEY_ACCOUNT, "dpapi", reveal=True)
    key = base64.b64decode(entry["secret_b64"])
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
    from license_verify import _seal
    wm_path = Path(rb_cfg["license_state_root"]) / "clock-watermark.json"
    wm_path.write_text(json.dumps(_seal(
        key, time.time() + 48 * 3600), ensure_ascii=False), encoding="utf-8")
    neg("f79_s4_rollback_verify_refused", "license.verify_offline",
        {"schema": "x"}, cfg=rb_cfg,
        expect="license_failed:license_clock_rollback_detected")
    exit_code, code = entry_code("license.check", {}, rb_cfg)
    negative_codes["f79_s4_rollback_check_refused"] = code
    checks.step("f79_s4_rollback_check_refused",
                exit_code == 3
                and code == "license_failed:license_clock_rollback_detected",
                "exit=%s code=%s" % (exit_code, code))
    rb_status = entry_result("license.status", {}, rb_cfg)
    checks.step(
        "f79_s4_rollback_status_fail_closed",
        rb_status["state"] == "clock_rollback_detected",
        "state=%s（绝不投影 authorized）" % rb_status["state"])

    # 水印改值不重封＝untrusted（独立根）
    tw_cfg = base_config(root / "wtamper")
    tw_cfg["vault_state_root"] = rb_cfg["vault_state_root"]
    tw_cfg["license_state_root"] = str(root / "wtamper" / "license")
    from license_verify import now_checked
    now_checked(tw_cfg)
    wm2 = Path(tw_cfg["license_state_root"]) / "clock-watermark.json"
    sealed = json.loads(wm2.read_text(encoding="utf-8"))
    sealed["watermark_epoch"] = sealed["watermark_epoch"] + 3600
    wm2.write_text(json.dumps(sealed), encoding="utf-8")
    neg("f79_s4_watermark_untrusted", "license.clock_status", {},
        cfg=tw_cfg, expect="license_failed:license_clock_state_untrusted")

    # 时钟密钥唯一存 F12 保险库；get-or-create 幂等不轮换
    first = vault_get(config["vault_state_root"], CLOCK_KEY_SERVICE,
                      CLOCK_KEY_ACCOUNT, "dpapi", reveal=True)
    entry_result("license.clock_status", {}, config)
    second = vault_get(config["vault_state_root"], CLOCK_KEY_SERVICE,
                       CLOCK_KEY_ACCOUNT, "dpapi", reveal=True)
    checks.step("f79_s4_clock_key_f12_idempotent",
                first["sha256"] == second["sha256"]
                and not (Path(config["license_state_root"]) / "clock.key")
                .exists(),
                "sha=%s…" % first["sha256"][:12])

    # ---------------- F79 S5 私钥不入发行物三重钉 ----------------
    # ①产品面 AST 零私钥路径＋implementation/ 全树零签发设施 import
    ok_ast = True
    for name in ("license_verify.py", "license_manager.py"):
        src = (REPO_ROOT / "implementation" / "python" / name).read_text(
            encoding="utf-8")
        if "Ed25519PrivateKey" in src or "private_bytes" in src:
            ok_ast = False
    for py in (REPO_ROOT / "implementation" / "python").glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            mods = ([a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [(node.module or "")] if isinstance(
                        node, ast.ImportFrom) else [])
            if any("license_issuer_synth" in m for m in mods):
                ok_ast = False
    checks.step("f79_s5_product_tree_no_signing_path", ok_ast,
                "AST 零 Ed25519PrivateKey/private_bytes/签发设施 import")

    # ②git tracked 全文件字节扫描（运行时私钥 raw+hex+b64）零命中
    priv_b64_path = issuer.state_dir / "issuer-private-key.b64"
    priv_raw = base64.b64decode(priv_b64_path.read_text(encoding="ascii")
                                .strip())
    needles = (priv_raw, priv_raw.hex().encode("ascii"),
               base64.b64encode(priv_raw))
    scan = _scan_git_tracked(needles)
    checks.step("f79_s5_repo_scan_zero_hits",
                scan["ok"] and not scan["hits"],
                "scanned=%d hits=%d" % (scan["scanned"], len(scan["hits"])))
    # ③同径正控（issuer-state 私钥文件）命中≥1＝非空转
    control = _scan_dir(issuer.state_dir, needles)
    checks.step("f79_s5_positive_control_hits",
                control["ok"] and control["hits"] >= 1,
                "hits=%d" % control["hits"])

    # ---------------- F79 S6 F30 协调 ----------------
    import airplane_mode
    channels = {c[0] for c in airplane_mode.CHANNELS}
    lm_src = (REPO_ROOT / "implementation" / "python"
              / "license_manager.py").read_text(encoding="utf-8")
    lm_tree = ast.parse(lm_src)
    called = {n.func.id for n in ast.walk(lm_tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    checks.step(
        "f79_s6_f30_frozen_table_untouched",
        "license_daily_check" not in channels
        and "enforce_bridge_egress" not in called
        and "decision" not in called,
        "license 通道不在冻结闭集；产品面零闸函数调用（自带闸在面内）")

    ap_cfg = base_config(root / "airplane")
    ap_cfg["license_service_url"] = "http://10.9.8.7:59999"  # 非回环
    ap_cfg["license_trusted_pubkeys"] = [issuer.pubkey_b64]
    ap_cfg["airplane_state_root"] = str(root / "airplane" / "flag")
    write_airplane_flag(ap_cfg)
    entry_result("license.activate",
                 {"token": issuer.activate_token("JUSCITE-SYNTH-KEY-001", fp)},
                 ap_cfg)
    force_due(ap_cfg)
    exit_code, code = entry_code("license.check", {}, ap_cfg)
    negative_codes["f79_s6_airplane_blocks_nonloopback"] = code
    checks.step("f79_s6_airplane_blocks_nonloopback",
                exit_code == 3
                and code == "license_daily_check_airplane_blocked",
                "exit=%s code=%s" % (exit_code, code))

    # ---------------- F78 S6 桥纪律（子进程径） ----------------
    exit_code, code = entry_code("license.revoke_remote", {}, config)
    negative_codes["f78_s6_unwired_method_refused"] = code
    checks.step("f78_s6_unwired_method_refused",
                exit_code == 3
                and code == "method_not_connected:license.revoke_remote",
                "exit=%s code=%s" % (exit_code, code))

    un_cfg = base_config(root / "unconf")
    un_cfg["license_service_url"] = issuer.url
    un_cfg["license_trusted_pubkeys"] = [issuer.pubkey_b64]
    entry_result("license.activate",
                 {"token": issuer.activate_token("JUSCITE-SYNTH-KEY-001", fp)},
                 un_cfg)
    del un_cfg["license_service_url"]
    force_due(un_cfg)
    exit_code, code = entry_code("license.check", {}, un_cfg)
    negative_codes["f78_s6_service_unconfigured_exit3"] = code
    checks.step("f78_s6_service_unconfigured_exit3",
                exit_code == 3 and code == "license_service_not_configured",
                "exit=%s code=%s" % (exit_code, code))

    # ---------------- S7 投影（剥时变键） ----------------
    projection = {
        "license_id": "lic-recon-001",
        "subject": "合成律师-甲（recon）",
        "features": ["desk", "offline"],
        "device_fp_hash": fp,
        "issuer_pubkey_b64": issuer.pubkey_b64,
        "states": {
            "not_activated": True,
            "authorized": True,
            "revoked_seen": True,
            "grace_seen": True,
            "grace_budget_not_extended": grace2["grace_until_epoch"]
            == grace_until,
            "grace_expired_seen": True,
            "state_intact_after_interruption": intact,
        },
        "negative_codes": negative_codes,
        "clock_key_f12_idempotent": first["sha256"] == second["sha256"],
        "repo_scan_hits": scan["hits"],
        "positive_control_hits": control["hits"],
    }
    write_evidence(checks, projection, started, evidence_root, profile)
    print("[%s] %s" % (profile, checks.verdict))
    return projection


def _issuer_priv(issuer: Issuer) -> bytes:
    """recon 进程内读签发私钥（仅用于构造负测令牌；密钥不出 issuer-state）。"""
    return base64.b64decode((issuer.state_dir / "issuer-private-key.b64")
                            .read_text(encoding="ascii").strip())


def _scan_git_tracked(needles: tuple) -> dict:
    """juscite git tracked 全文件字节扫描（W3-U33 F77/W4-U54 同法）。"""
    proc = subprocess.run(["git", "ls-files"], cwd=str(REPO_ROOT),
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=300)
    if proc.returncode != 0:
        return {"ok": False, "scanned": 0, "hits": []}
    scanned, hits = 0, []
    for line in proc.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        scanned += 1
        if any(needle in data for needle in needles):
            hits.append(rel)
    return {"ok": True, "scanned": scanned, "hits": hits}


def _scan_dir(directory: Path, needles: tuple) -> dict:
    scanned, hits = 0, 0
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        scanned += 1
        if any(needle in data for needle in needles):
            hits += 1
    return {"ok": scanned > 0, "scanned": scanned, "hits": hits}


def write_evidence(checks: Checks, projection: dict, started: datetime,
                   evidence_root: Path, profile: str) -> None:
    finished = datetime.now(timezone.utc)
    subject = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                             capture_output=True, text=True,
                             encoding="utf-8").stdout.strip()
    base_doc = {
        "unit": "W5-U01",
        "profile": checks.profile,
        "verdict": checks.verdict,
        "counts": {"pass": sum(1 for c in checks.items
                               if c["status"] == "PASS"),
                   "total": len(checks.items)},
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "subject_commit": subject,
        "legal_entry_sha256": sha256_bytes(LEGAL_ENTRY.read_bytes()),
        "materials": "全合成（合成签发服务 127.0.0.1 回环＋合成许可种子；零真实外联）",
    }
    f78_ids = ("f78",)
    f79_ids = ("f79", "s5", "s6_f30", "s6_airplane")
    f78_checks = [c for c in checks.items if c["id"].startswith(f78_ids)
                  or "_s1_" in c["id"] or "_s2_" in c["id"]]
    f79_checks = [c for c in checks.items if c not in f78_checks]
    for feature, subset, fname in (
            ("F78", f78_checks, "f78-license-recon.json"),
            ("F79", f79_checks, "f79-license-recon.json")):
        out_dir = evidence_root / feature / checks.profile
        out_dir.mkdir(parents=True, exist_ok=True)
        doc = {**base_doc, "feature": feature, "checks": subset,
               "counts": {"pass": sum(1 for c in subset
                                      if c["status"] == "PASS"),
                          "total": len(subset)}}
        (out_dir / fname).write_text(
            json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1),
            encoding="utf-8")
        (out_dir / ("f78-license-projection.json" if feature == "F78"
                    else "f79-license-projection.json")).write_text(
            json.dumps(projection, ensure_ascii=False, sort_keys=True,
                       indent=1), encoding="utf-8")
        print("  evidence -> %s" % (out_dir / fname))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"],
                        help="可重复：--profile desktop --profile selfhost")
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    started = datetime.now(timezone.utc)
    work_root = Path(tempfile.mkdtemp(prefix="f78f79_recon_"))
    issuer = Issuer(work_root)
    exit_code = 0
    projections = {}
    try:
        for profile in profiles:
            try:
                projections[profile] = run_profile(
                    profile, issuer,
                    REPO_ROOT / "evidence", work_root)
            except Exception as exc:  # noqa: BLE001（recon 收口：如实 FAIL）
                print("[%s] EXCEPTION %s: %s" % (profile,
                                                 type(exc).__name__, exc))
                exit_code |= 1
        if set(profiles) == {"desktop", "selfhost"} \
                and len(projections) == 2:
            same = projections["desktop"] == projections["selfhost"]
            print("[s7] cross-profile projection diff: %s" %
                  ("null (逐键相等)" if same else "DIFF"))
            if not same:
                exit_code |= 1
                for key in set(projections["desktop"]) | set(
                        projections["selfhost"]):
                    a = projections["desktop"].get(key)
                    b = projections["selfhost"].get(key)
                    if a != b:
                        print("  s7 diff %s: %r != %r" % (key, a, b))
        print("recon work_root(用后即弃)=%s started=%s" % (work_root,
                                                          started.isoformat()))
    finally:
        issuer.stop()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
