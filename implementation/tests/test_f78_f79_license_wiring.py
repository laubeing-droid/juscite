# -*- coding: utf-8 -*-
"""F78/F79 许可产品桥接线测试（工单 W5-U01）。

06 V7-78/V7-79（owner=distribution；desktop/selfhost 双实例；acceptance：
F78「授权校验/宽限/离线状态真实；不因服务中断删除数据或伪授权」、F79
「离线许可验签和时钟回拨反例受控；私钥不入发行物」）。产品面＝legal_entry
两冻结方法组：LICENSE_MANAGER_METHODS（license_manager：activate/check/
status）＋LICENSE_VERIFY_METHODS（license_verify：verify_offline/
device_fingerprint/clock_status）。合成签发设施 tools/license_issuer_synth
（裁决 #13-19 合成先行；私钥只在 tools/ 施工业区，运行时生成）。

合同硬点（本测试主战场）：
  - 激活＝F79 验签过闸（信任锚→签名→指纹→时间窗）后持久化；令牌自带
    公钥绝不是信任锚；异钥/篡改/过期/未生效/异设备全部具名拒；
  - 每日校验＝24h 窗内不出网（服务已死仍成功＝零出网证明）；到点真
    HTTP；服务不可达进一次性宽限预算（不展期）；revoked 真实入账；
    任何中断路径零删数据零伪授权；
  - 时钟回拨＝单调水印（HMAC 封印；密钥唯一存 F12 保险库 lvyin.f79/
    clock-watermark-hmac-v1——legacy link F12）：回拨 typed 拒；水印封
    印损坏 fail-closed；回拨时钟下 status 绝不投影 authorized；
  - F30 协调＝出网前读 F30 旗标（armed 且服务端非回环＝具名拒；回环合
    成签发服务 armed 保持可用）；F30 冻结通道闭集零改动（AST 钉）；
  - 桥 fail-closed：未配置 NotConnected 具名（CLI 子进程 exit 3）；封闭
    注册外方法具名拒；私钥不入发行物＝产品树零签名路径（AST 钉）。

全程合成材料（合成许可种子/合成主体/127.0.0.1 回环签发服务，零真实外联）。
"""

from __future__ import annotations

import ast
import base64
import contextlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
from license_verify import LicenseError, _seal  # noqa: E402
import license_issuer_synth as issuer  # noqa: E402

# 合成许可种子（全合成；lic-rev 为撤销样本）
SEED = [
    {"license_key": "JUSCITE-SYNTH-KEY-001", "license_id": "lic-synth-001",
     "subject": "合成律师-甲（wiring）", "days": 365,
     "features": ["desk", "offline"], "revoked": False},
    {"license_key": "JUSCITE-SYNTH-KEY-REV", "license_id": "lic-synth-rev",
     "subject": "合成律师-乙（wiring）", "days": 365,
     "features": [], "revoked": True},
    {"license_key": "JUSCITE-SYNTH-KEY-EXP", "license_id": "lic-synth-exp",
     "subject": "合成律师-丙（wiring）", "days": -1,
     "features": [], "revoked": False},
]


def _serve(seed_rows):
    """回环合成签发服务（127.0.0.1 随机口；随测起停）。"""
    tmp = Path(tempfile.mkdtemp(prefix="f78w_issuer_"))
    state = issuer._IssuerState(seed_rows, tmp / "issuer-state")
    server = ThreadingHTTPServer(("127.0.0.1", 0), issuer._handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, state


def _teardown(server):
    """幂等清理（shutdown 可重入；测试清扫不掩盖断言）。"""
    with contextlib.suppress(Exception):
        server.shutdown()
    with contextlib.suppress(Exception):
        server.server_close()


class _Env:
    """每测独立临时根：license/vault 分根；服务随用随起。"""

    def __init__(self, grace_days=14, pubkeys=None):
        self.tmp = Path(tempfile.mkdtemp(prefix="f78w_env_"))
        self.config = {
            "license_state_root": str(self.tmp / "license"),
            "vault_state_root": str(self.tmp / "vault"),
            "license_grace_days": grace_days,
            "license_trusted_pubkeys": pubkeys if pubkeys is not None else [],
        }

    def with_service(self, state):
        self.config["license_service_url"] = "http://127.0.0.1:%d" % \
            self._port
        return self.config

    def force_due(self):
        """状态外科：把 last_check 拨回 25h 前（越过每日窗；测试专用）。"""
        path = self.config["license_state_root"] + "/license-state.json"
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        data["last_check"]["at_epoch"] = time.time() - 25 * 3600
        data["last_check"]["at_iso"] = "forced-due-by-test"
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                              encoding="utf-8")

    def read_state(self):
        path = self.config["license_state_root"] + "/license-state.json"
        return json.loads(Path(path).read_text(encoding="utf-8"))


def _activate_from(env, issuer_state, license_key):
    """经服务真实换令牌→license.activate 全链。"""
    fp = legal_entry.call("license.device_fingerprint", {}, env.config)[
        "fingerprint_hash"]
    req = urllib.request.Request(
        env.config["license_service_url"] + "/v1/activate",
        data=json.dumps({"license_key": license_key,
                         "device_fp_hash": fp}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    token = json.loads(urllib.request.urlopen(req, timeout=10).read())
    return legal_entry.call("license.activate", {"token": token}, env.config), \
        token


def call_license_code(method, args, config):
    """全链调 license 方法，返回桥面 typed 码（NotConnected.code 剥前缀）。

    桥合同：LicenseError → NotConnected("license_failed:"+码)；
    面内 NotConnected/HarnessCommandError 原样透传。"""
    try:
        legal_entry.call(method, args, config)
    except NotConnected as exc:
        code = str(exc)
        return code[len("license_failed:"):] if code.startswith(
            "license_failed:") else code
    raise AssertionError("expected NotConnected, got success")


class F78ActivationFlow(unittest.TestCase):
    """激活与离线验签（F78×F79 主链）。"""

    @classmethod
    def setUpClass(cls):
        cls.server, cls.issuer_state = _serve(SEED)
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_status_not_activated(self):
        env = _Env()
        env.config["license_service_url"] = "http://127.0.0.1:%d" % self.port
        out = legal_entry.call("license.status", {}, env.config)
        self.assertEqual(out["state"], "not_activated")

    def test_activate_authorized_real_chain(self):
        env = _Env()
        env.config["license_service_url"] = "http://127.0.0.1:%d" % self.port
        env.config["license_trusted_pubkeys"] = [
            base64.b64encode(self.issuer_state.raw_pub).decode("ascii")]
        out, _ = _activate_from(env, self.issuer_state, "JUSCITE-SYNTH-KEY-001")
        self.assertEqual(out["state"], "authorized")
        self.assertEqual(out["license_id"], "lic-synth-001")
        self.assertEqual(out["subject"], "合成律师-甲（wiring）")
        self.assertEqual(out["device_fp_hash"],
                         legal_entry.call("license.device_fingerprint", {},
                                          env.config)["fingerprint_hash"])

    def test_verify_offline_valid_projection(self):
        env = _Env()
        env.config["license_service_url"] = "http://127.0.0.1:%d" % self.port
        env.config["license_trusted_pubkeys"] = [
            base64.b64encode(self.issuer_state.raw_pub).decode("ascii")]
        _, token = _activate_from(env, self.issuer_state,
                                  "JUSCITE-SYNTH-KEY-001")
        out = legal_entry.call("license.verify_offline", {"token": token},
                               env.config)
        self.assertTrue(out["valid"])
        self.assertEqual(out["algorithm"], "ed25519")
        self.assertTrue(out["issuer_fingerprint"])

    def test_tampered_payload_refused(self):
        env = _Env()
        env.config["license_service_url"] = "http://127.0.0.1:%d" % self.port
        env.config["license_trusted_pubkeys"] = [
            base64.b64encode(self.issuer_state.raw_pub).decode("ascii")]
        _, token = _activate_from(env, self.issuer_state,
                                  "JUSCITE-SYNTH-KEY-001")
        raw = bytearray(base64.b64decode(token["payload_b64"]))
        raw[10] ^= 0x01  # 改一字节
        bad = dict(token, payload_b64=base64.b64encode(bytes(raw)).decode())
        self.assertEqual(
            call_license_code("license.verify_offline", {"token": bad},
                              env.config), "license_signature_invalid")

    def test_foreign_issuer_refused(self):
        """异钥签发（信任锚外）＝license_signature_invalid；零静默放行。"""
        foreign_server, foreign_state = _serve(SEED[:1])
        try:
            env = _Env(pubkeys=[
                base64.b64encode(self.issuer_state.raw_pub).decode("ascii")])
            foreign_port = foreign_server.server_address[1]
            fp = legal_entry.call("license.device_fingerprint", {},
                                  env.config)["fingerprint_hash"]
            req = urllib.request.Request(
                "http://127.0.0.1:%d/v1/activate" % foreign_port,
                data=json.dumps({"license_key": "JUSCITE-SYNTH-KEY-001",
                                 "device_fp_hash": fp}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            token = json.loads(urllib.request.urlopen(req, timeout=10).read())
            self.assertEqual(
                call_license_code("license.verify_offline", {"token": token},
                                  env.config), "license_signature_invalid")
        finally:
            foreign_server.shutdown()
            foreign_server.server_close()

    def test_device_mismatch_refused(self):
        env = _Env(pubkeys=[
            base64.b64encode(self.issuer_state.raw_pub).decode("ascii")])
        token = issuer.issue_for_device(
            self.issuer_state.raw_priv, SEED[0], "f" * 32)  # 异设备指纹
        self.assertEqual(
            call_license_code("license.verify_offline", {"token": token},
                              env.config), "license_device_mismatch")

    def test_expired_license_refused(self):
        env = _Env(pubkeys=[
            base64.b64encode(self.issuer_state.raw_pub).decode("ascii")])
        token = issuer.issue_for_device(
            self.issuer_state.raw_priv, SEED[2],
            legal_entry.call("license.device_fingerprint", {},
                             env.config)["fingerprint_hash"])
        self.assertEqual(
            call_license_code("license.verify_offline", {"token": token},
                              env.config), "license_expired")

    def test_not_yet_valid_refused(self):
        env = _Env(pubkeys=[
            base64.b64encode(self.issuer_state.raw_pub).decode("ascii")])
        now = time.time()
        token = issuer.sign_payload(self.issuer_state.raw_priv, {
            "license_id": "lic-future", "subject": "合成-未生效",
            "device_fp_hash": legal_entry.call(
                "license.device_fingerprint", {}, env.config)[
                    "fingerprint_hash"],
            "not_before": repr(now + 30 * 86400),
            "not_after": repr(now + 60 * 86400), "features": []})
        self.assertEqual(
            call_license_code("license.verify_offline", {"token": token},
                              env.config), "license_not_yet_valid")

    def test_trusted_keys_missing_refused(self):
        env = _Env()  # 零信任锚
        token = issuer.issue_for_device(
            self.issuer_state.raw_priv, SEED[0], "f" * 32)
        self.assertEqual(
            call_license_code("license.verify_offline", {"token": token},
                              env.config), "license_trusted_keys_not_configured")


class F78DailyCheckGrace(unittest.TestCase):
    """每日校验＋宽限＋中断不删数据不伪授权（每测独立服务实例）。"""

    def _activated_env(self, grace_days=14):
        server, issuer_state = _serve(SEED)
        self.addCleanup(_teardown, server)
        env = _Env(grace_days=grace_days)
        env.config["license_service_url"] = "http://127.0.0.1:%d" % \
            server.server_address[1]
        env.config["license_trusted_pubkeys"] = [
            base64.b64encode(issuer_state.raw_pub).decode("ascii")]
        out, _ = _activate_from(env, issuer_state, "JUSCITE-SYNTH-KEY-001")
        assert out["state"] == "authorized"
        return env, server

    def test_daily_window_no_network(self):
        """24h 窗内不出网：服务已死仍成功＝零出网证明。"""
        env, server = self._activated_env()
        server.shutdown()  # 服务下线
        out = legal_entry.call("license.check", {}, env.config)
        self.assertFalse(out["checked_now"])
        self.assertEqual(out["state"], "authorized")
        self.assertIn("next_check_due_epoch", out)

    def test_service_unreachable_opens_grace_once(self):
        env, server = self._activated_env(grace_days=7)
        env.force_due()
        server.shutdown()
        out = legal_entry.call("license.check", {}, env.config)
        self.assertEqual(out["state"], "grace")
        grace_until = out["grace_until_epoch"]
        self.assertIsNotNone(grace_until)
        # 预算一次性钉定：再查不展期（force due 后二次不可达同预算）
        env.force_due()
        out2 = legal_entry.call("license.check", {}, env.config)
        self.assertEqual(out2["state"], "grace")
        self.assertEqual(out2["grace_until_epoch"], grace_until)
        # 红线：中断未删激活记录（state 完整在案）
        state = env.read_state()
        self.assertIn("activation", state)
        self.assertEqual(state["activation"]["license_id"], "lic-synth-001")
        self.assertEqual(state["last_check"]["result"],
                         "service_unreachable")

    def test_grace_expiry_named_real(self):
        env, server = self._activated_env(grace_days=1)
        env.force_due()
        # 锚拨回 3 天前（宽限 1 天 → 已过期）
        path = Path(env.config["license_state_root"]) / "license-state.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["last_valid_epoch"] = time.time() - 3 * 86400
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        server.shutdown()
        out = legal_entry.call("license.check", {}, env.config)
        self.assertEqual(out["state"], "grace_expired")
        # 状态仍可只读投影（零删除）
        self.assertEqual(legal_entry.call("license.status", {}, env.config)[
            "state"], "grace_expired")

    def test_revoked_real_state_no_deletion(self):
        env, server = self._activated_env()
        env.force_due()
        out = legal_entry.call("license.check", {}, env.config)
        self.assertEqual(out["state"], "authorized")  # lic-001 未撤销
        # 换撤销样本重新激活（同根显式新令牌）
        fp = legal_entry.call("license.device_fingerprint", {},
                              env.config)["fingerprint_hash"]
        req = urllib.request.Request(
            env.config["license_service_url"] + "/v1/activate",
            data=json.dumps({"license_key": "JUSCITE-SYNTH-KEY-REV",
                             "device_fp_hash": fp}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        token = json.loads(urllib.request.urlopen(req, timeout=10).read())
        out2 = legal_entry.call("license.activate", {"token": token},
                                env.config)
        self.assertEqual(out2["state"], "authorized")  # 激活态（未校验）
        env.force_due()
        out3 = legal_entry.call("license.check", {}, env.config)
        self.assertEqual(out3["state"], "revoked")  # 服务端真实撤销入账
        state = env.read_state()
        self.assertIn("activation", state)  # 零删除
        self.assertEqual(state["last_check"]["result"], "revoked")

    def test_service_config_missing_not_connected(self):
        env, _server = self._activated_env()
        del env.config["license_service_url"]
        env.force_due()
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("license.check", {}, env.config)
        self.assertEqual(str(ctx.exception), "license_service_not_configured")

    def test_service_reachable_but_garbage_no_grace(self):
        """可达但应答不识＝typed 拒，状态零动（绝不因此开宽限）。"""
        from http.server import BaseHTTPRequestHandler

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = b"not-json"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                pass
        bad = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=bad.serve_forever, daemon=True).start()
        self.addCleanup(bad.shutdown)
        self.addCleanup(bad.server_close)
        env, _server = self._activated_env()
        env.config["license_service_url"] = \
            "http://127.0.0.1:%d" % bad.server_address[1]
        env.force_due()
        self.assertEqual(
            call_license_code("license.check", {}, env.config),
            "license_service_response_unknown")
        out = legal_entry.call("license.status", {}, env.config)
        self.assertEqual(out["state"], "authorized")  # 状态零动
        self.assertIsNone(out.get("grace_until_epoch"))


class F79ClockAuthority(unittest.TestCase):
    """单调水印＋回拨负测＋F12 保险库复用。"""

    def _establish_watermark(self, env):
        """首次受时操作（建立水印＋保险库密钥）。"""
        from license_verify import now_checked
        return now_checked(env.config)

    def test_watermark_advances_and_rolls_back_refused(self):
        server, issuer_state = _serve(SEED)
        self.addCleanup(_teardown, server)
        env = _Env(pubkeys=[
            base64.b64encode(issuer_state.raw_pub).decode("ascii")])
        env.config["license_service_url"] = "http://127.0.0.1:%d" % \
            server.server_address[1]
        out, token = _activate_from(env, issuer_state,
                                    "JUSCITE-SYNTH-KEY-001")
        self.assertEqual(out["state"], "authorized")
        # 取 F12 保险库密钥，写「未来」封印水印＝时钟被拨回 48h
        from credential_vault import vault_get
        entry = vault_get(env.config["vault_state_root"], "lvyin.f79",
                          "clock-watermark-hmac-v1", "dpapi", reveal=True)
        key = base64.b64decode(entry["secret_b64"])
        wm_path = Path(env.config["license_state_root"]) / \
            "clock-watermark.json"
        future = time.time() + 48 * 3600
        wm_path.write_text(json.dumps(_seal(key, future), ensure_ascii=False),
                           encoding="utf-8")
        self.assertEqual(
            call_license_code("license.verify_offline",
                              {"token": {"schema": "x"}}, env.config),
            "license_clock_rollback_detected")
        # 回拨时钟下 status 绝不投影 authorized（fail-closed）
        out = legal_entry.call("license.status", {}, env.config)
        self.assertEqual(out["state"], "clock_rollback_detected")
        # check 同拒（受时操作统一过闸）
        self.assertEqual(
            call_license_code("license.check", {}, env.config),
            "license_clock_rollback_detected")

    def test_tampered_watermark_untrusted(self):
        env = _Env(pubkeys=[])
        self._establish_watermark(env)
        wm_path = Path(env.config["license_state_root"]) / \
            "clock-watermark.json"
        sealed = json.loads(wm_path.read_text(encoding="utf-8"))
        sealed["watermark_epoch"] = sealed["watermark_epoch"] + 3600  # 改值不重封
        wm_path.write_text(json.dumps(sealed), encoding="utf-8")
        self.assertEqual(
            call_license_code("license.clock_status", {}, env.config),
            "license_clock_state_untrusted")

    def test_clock_key_in_f12_vault_idempotent(self):
        """legacy link F12：密钥唯一存保险库；get-or-create 幂等不轮换。"""
        env = _Env(pubkeys=[])
        self._establish_watermark(env)
        from credential_vault import vault_get
        first = vault_get(env.config["vault_state_root"], "lvyin.f79",
                          "clock-watermark-hmac-v1", "dpapi", reveal=True)
        self._establish_watermark(env)
        second = vault_get(env.config["vault_state_root"], "lvyin.f79",
                           "clock-watermark-hmac-v1", "dpapi", reveal=True)
        self.assertEqual(first["sha256"], second["sha256"])  # 不轮换
        # 命名位在 F12 设施内（非独立钥文件）
        self.assertFalse((Path(env.config["license_state_root"])
                          / "clock.key").exists())

    def test_fingerprint_deterministic_and_masked(self):
        env = _Env(pubkeys=[])
        a = legal_entry.call("license.device_fingerprint", {}, env.config)
        b = legal_entry.call("license.device_fingerprint", {}, env.config)
        self.assertEqual(a["fingerprint_hash"], b["fingerprint_hash"])
        self.assertEqual(len(a["fingerprint_hash"]), 32)
        self.assertIn("winreg.machineguid", a["sources"])
        blob = json.dumps(a)
        self.assertNotIn("MachineGuid-", blob)  # 原始标识永不出面（hash-only）


class F30Coordination(unittest.TestCase):
    """F30 只读旗标协调；冻结通道闭集零改动（AST 钉）。"""

    def test_airplane_armed_blocks_nonloopback(self):
        server, issuer_state = _serve(SEED)
        try:
            env = _Env(pubkeys=[
                base64.b64encode(issuer_state.raw_pub).decode("ascii")])
            env.config["license_service_url"] = "http://127.0.0.1:%d" % \
                server.server_address[1]
            # 先激活（回环服务 armed 可用）
            env2 = _Env(pubkeys=env.config["license_trusted_pubkeys"])
            env2.config["airplane_state_root"] = str(env2.tmp / "airplane")
            airplane_root = Path(env2.config["airplane_state_root"])
            airplane_root.mkdir(parents=True, exist_ok=True)
            (airplane_root / "airplane-mode.json").write_text(
                json.dumps({"enabled": True, "reason": "synth",
                            "updated_at": "now"}), encoding="utf-8")
            env2.config["license_service_url"] = env.config[
                "license_service_url"]
            fp = legal_entry.call("license.device_fingerprint", {},
                                  env2.config)["fingerprint_hash"]
            req = urllib.request.Request(
                env2.config["license_service_url"] + "/v1/activate",
                data=json.dumps({"license_key": "JUSCITE-SYNTH-KEY-001",
                                 "device_fp_hash": fp}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            token = json.loads(urllib.request.urlopen(req, timeout=10).read())
            legal_entry.call("license.activate", {"token": token},
                             env2.config)
            env2.force_due()
            # armed＋服务端此刻仍是回环→放行；拨服务到非回环→具名拒
            env2.config["license_service_url"] = "http://10.9.8.7:59999"
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("license.check", {}, env2.config)
            self.assertEqual(str(ctx.exception),
                             "license_daily_check_airplane_blocked")
        finally:
            server.shutdown()
            server.server_close()

    def test_f30_frozen_table_untouched_ast(self):
        """F30 冻结通道闭集零改动：license_manager 不碰 enforce/decision，
        airplane_mode.CHANNELS 无 license 通道。"""
        src = (ROOT / "python" / "license_manager.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        called = {n.func.id for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name)}
        self.assertNotIn("enforce_bridge_egress", called)
        self.assertNotIn("decision", called)
        import airplane_mode
        self.assertNotIn("license_daily_check",
                         {c[0] for c in airplane_mode.CHANNELS})


class BridgeDiscipline(unittest.TestCase):
    """桥纪律：fail-closed 具名／封闭注册外拒／私钥不入发行物 AST 钉／
    CLI 信封 exit 码。"""

    def test_unwired_license_method_refused(self):
        """封闭注册外 license 方法＝桥口具名拒（组外方法绝不落面）。"""
        env = _Env(pubkeys=[])
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("license.revoke_remote", {}, env.config)
        self.assertEqual(str(ctx.exception),
                         "method_not_connected:license.revoke_remote")

    def test_product_tree_has_no_signing_path(self):
        """私钥不入发行物：产品面零私钥加载/签名路径；签发设施零 import
        （docstring 具名回收点提及不算引用——判据＝AST import/call 面）。"""
        for name in ("license_verify.py", "license_manager.py"):
            src = (ROOT / "python" / name).read_text(encoding="utf-8")
            self.assertNotIn("Ed25519PrivateKey", src, name)
            self.assertNotIn("private_bytes", src, name)
        for py in sorted((ROOT / "python").glob("*.py")):
            src = py.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                for mod in names:
                    self.assertNotIn("license_issuer_synth", mod, py.name)

    def _cli(self, method, args, config):
        req_file = tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                               suffix=".json", delete=False)
        cfg_file = tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                               suffix=".json", delete=False)
        try:
            json.dump({"method": method, "args": args}, req_file,
                      ensure_ascii=False)
            req_file.close()
            json.dump(config, cfg_file, ensure_ascii=False)
            cfg_file.close()
            proc = subprocess.run(
                [sys.executable, "-X", "utf8",
                 str(ROOT / "python" / "legal_entry.py"),
                 "--request-json", req_file.name,
                 "--config", cfg_file.name],
                capture_output=True, text=True, encoding="utf-8",
                timeout=120, cwd=str(REPO_ROOT),
                env={**os.environ,
                     "PYTHONPATH": str(ROOT / "python") + os.pathsep +
                     os.environ.get("PYTHONPATH", "")})
            return proc.returncode, json.loads(proc.stdout)
        finally:
            os.unlink(req_file.name)
            os.unlink(cfg_file.name)

    def test_cli_owner_response_and_not_connected_envelopes(self):
        env = _Env(pubkeys=[])
        code, payload = self._cli("license.status", {}, env.config)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "OWNER_RESPONSE")
        self.assertEqual(payload["result"]["state"], "not_activated")
        # 服务未配置＝NotConnected exit 3 具名（激活后越过每日窗）
        server, issuer_state = _serve(SEED)
        try:
            env.config["license_service_url"] = \
                "http://127.0.0.1:%d" % server.server_address[1]
            env.config["license_trusted_pubkeys"] = [
                base64.b64encode(issuer_state.raw_pub).decode("ascii")]
            _, token = _activate_from(env, issuer_state,
                                      "JUSCITE-SYNTH-KEY-001")
            del env.config["license_service_url"]
            env.force_due()
            code, payload = self._cli("license.check", {}, env.config)
            self.assertEqual(code, 3)
            self.assertEqual(payload["status"], "NOT_CONNECTED")
            self.assertEqual(payload["code"],
                             "license_service_not_configured")
            # 篡改令牌验签＝exit 3 typed 码
            raw = bytearray(base64.b64decode(token["payload_b64"]))
            raw[3] ^= 0xFF
            bad = dict(token,
                       payload_b64=base64.b64encode(bytes(raw)).decode())
            env.config["license_trusted_pubkeys"] = [
                base64.b64encode(issuer_state.raw_pub).decode("ascii")]
            code, payload = self._cli("license.verify_offline",
                                      {"token": bad}, env.config)
            self.assertEqual(code, 3)
            self.assertEqual(payload["code"],
                             "license_failed:license_signature_invalid")
            # 封闭注册外方法＝exit 3 具名（组外方法绝不落 license 面）
            code, payload = self._cli("license.nonexistent", {}, env.config)
            self.assertEqual(code, 3)
            self.assertEqual(payload["code"],
                             "method_not_connected:license.nonexistent")
        finally:
            server.shutdown()
            server.server_close()

    def test_dual_state_roots_independent(self):
        """desktop/selfhost 同构：分状态根互不串（F40 分根先例）。"""
        server, issuer_state = _serve(SEED)
        try:
            env_a = _Env()
            env_b = _Env()
            for env in (env_a, env_b):
                env.config["license_service_url"] = \
                    "http://127.0.0.1:%d" % server.server_address[1]
                env.config["license_trusted_pubkeys"] = [
                    base64.b64encode(issuer_state.raw_pub).decode("ascii")]
            _activate_from(env_a, issuer_state, "JUSCITE-SYNTH-KEY-001")
            sa = legal_entry.call("license.status", {}, env_a.config)
            sb = legal_entry.call("license.status", {}, env_b.config)
            self.assertEqual(sa["state"], "authorized")
            self.assertEqual(sb["state"], "not_activated")  # B 根零串扰
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
