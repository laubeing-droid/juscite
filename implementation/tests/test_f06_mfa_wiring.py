# -*- coding: utf-8 -*-
"""W5-U08 / F06 acceptance: MFA two-step verification (enroll/login/recover/
disable).

06 V7-06 assertion：MFA注册登录恢复与失效真实可用；密钥和恢复码不明文日志。
preserved＝自托管认证先做密码级（auth.* 密码级基底＋mfa.* 增强层，不重建
认证、不触碰 F04 案件权限权威）；凭据归产品凭据设施（F12 保险库，DPAPI
密文）；TOTP 时间显式 now 注入（确定性合成时钟：过期/重放/一次性消费窗口
可复现）；零明文沿 E10 密钥泄漏检查先例（字节级全产物扫描＋受控泄漏负控
证明扫描器非空转）。全部断言走真产品面（legal_entry.call 同径＋真入口子
进程径）；材料全合成，状态根全在 %TEMP%，%APPDATA% 零触碰。
"""
import ast
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))

import credential_vault as cv  # noqa: E402
import legal_entry  # noqa: E402
import mfa_auth as ma  # noqa: E402

REPO_ROOT = HERE.parent
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"

PASSWORD = "S3cret-合成-password-#1"


def _b32_secret(b32: str) -> bytes:
    return base64.b32decode(b32 + "=" * (-len(b32) % 8))


def _fresh_config(tmp: Path) -> dict:
    return {"mfa_state_root": str(tmp / "mfa"),
            "vault_state_root": str(tmp / "vault")}


def _expect_refused(testcase, method, args, config, needle):
    with testcase.assertRaises(legal_entry.NotConnected) as ctx:
        legal_entry.call(method, args, config)
    testcase.assertIn(needle, str(ctx.exception))


def _scan_hits(root: Path, needles: list[bytes]) -> list[str]:
    hits = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            path = Path(dirpath) / filename
            data = path.read_bytes()
            hits += [str(path) for needle in needles if needle in data]
    return hits


def _enrolled(tmp: Path, config: dict, user: str = "lawyer_a"):
    """注册＋enroll 的公共前奏；返回 (enroll 回执, now 基准)。"""
    legal_entry.call("auth.register",
                     {"user_id": user, "password": PASSWORD, "now": 1000},
                     config)
    enroll = legal_entry.call(
        "mfa.enroll", {"user_id": user, "password": PASSWORD, "now": 1020},
        config)
    return enroll


class FrozenGroupTests(unittest.TestCase):
    def test_frozen_method_groups(self):
        self.assertEqual(
            legal_entry.MFA_AUTH_METHODS,
            frozenset({"auth.register", "auth.login", "auth.session",
                       "mfa.enroll", "mfa.verify", "mfa.recover",
                       "mfa.status", "mfa.disable"}))

    def test_group_disjoint_from_all_business_groups(self):
        groups = [value for name, value in vars(legal_entry).items()
                  if name.endswith("_METHODS")
                  and isinstance(value, frozenset)]
        others = [g for g in groups if g is not legal_entry.MFA_AUTH_METHODS]
        self.assertTrue(others)
        for group in others:
            self.assertFalse(legal_entry.MFA_AUTH_METHODS & group,
                             str(group))

    def test_module_ast_zero_logging_zero_appdata(self):
        # 零明文日志的结构面：mfa_auth 零 print/零 logging/零 APPDATA。
        source = (HERE / "python" / "mfa_auth.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (node.func.id if isinstance(node.func, ast.Name)
                        else getattr(node.func, "attr", ""))
                self.assertNotIn(name, {"print", "logging"},
                                 "mfa_auth 面零 print/logging")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                names = [a.name for a in node.names]
                self.assertNotIn("logging", module + ",".join(names))
        self.assertNotIn("APPDATA", source)
        self.assertNotIn("os.environ", source)  # 零环境变量读（状态根全显式）
        # 增强层不重建认证：零 harness/案件权限 import 与调用（F04 权威
        # 零触碰；docstring 提及不算接线）。
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("harness", alias.name)
                    self.assertNotIn("permission", alias.name)
            if isinstance(node, ast.ImportFrom):
                module = getattr(node, "module", "") or ""
                self.assertNotIn("harness", module)
                self.assertNotIn("permission", module)


class Rfc6238DeterminismTests(unittest.TestCase):
    """TOTP 核心确定性：RFC 6238 Appendix B（SHA1）官方测试向量。"""

    RFC_SECRET = b"12345678901234567890"

    def test_rfc6238_vectors_8digit(self):
        for now, expected in ((59, "94287082"), (1111111109, "07081804"),
                              (1111111111, "14050471"),
                              (1234567890, "89005924"),
                              (2000000000, "69279037"),
                              (20000000000, "65353130")):
            self.assertEqual(ma.totp_at(self.RFC_SECRET, now, digits=8),
                             expected, now)

    def test_rfc6238_vectors_6digit_synthetic_clock(self):
        # 6 位（本面档位）＝同截断对 10^6 取模（8 位码末 6 位）；同 now
        # 复算逐字相等（确定性）。
        for now, expected in ((59, "287082"), (1111111109, "081804"),
                              (1234567890, "005924")):
            self.assertEqual(ma.totp_at(self.RFC_SECRET, now), expected)
        self.assertEqual(ma.totp_at(self.RFC_SECRET, 59),
                         ma.totp_at(self.RFC_SECRET, 59))


class PasswordBaseTests(unittest.TestCase):
    """密码级基底（preserved：自托管认证先做密码级）。"""

    def test_register_login_session_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _fresh_config(Path(tmp))
            out = legal_entry.call("auth.register",
                                   {"user_id": "lawyer_a",
                                    "password": PASSWORD, "now": 1000},
                                   config)
            self.assertTrue(out["registered"])
            login = legal_entry.call("auth.login",
                                     {"user_id": "lawyer_a",
                                      "password": PASSWORD, "now": 1010},
                                     config)
            self.assertEqual(login["status"], "ok")
            self.assertEqual(login["factor"], "password")
            self.assertTrue(login["session_token"])
            read = legal_entry.call("auth.session",
                                    {"session_token": login["session_token"],
                                     "now": 1011}, config)
            self.assertEqual(read["user_id"], "lawyer_a")
            # 过期（合成时钟推进过 TTL）＝具名拒。
            _expect_refused(self, "auth.session",
                            {"session_token": login["session_token"],
                             "now": 1010 + ma.SESSION_TTL_SECONDS}, config,
                            "mfa_session_expired")
            # 错密码／重复注册／未知用户／缺 now 全具名拒。
            _expect_refused(self, "auth.login",
                            {"user_id": "lawyer_a", "password": "wrong",
                             "now": 1012}, config, "mfa_password_mismatch")
            _expect_refused(self, "auth.register",
                            {"user_id": "lawyer_a", "password": PASSWORD,
                             "now": 1013}, config, "mfa_user_exists")
            _expect_refused(self, "auth.login",
                            {"user_id": "nobody", "password": PASSWORD,
                             "now": 1014}, config, "mfa_user_unknown")
            _expect_refused(self, "auth.register",
                            {"user_id": "lawyer_a", "password": PASSWORD},
                            config, "mfa_now_required")
            # 存面只有 PBKDF2 盐化校验值，零明文密码。
            account = json.loads(
                (Path(tmp) / "mfa" / "accounts" / "lawyer_a.json")
                .read_text(encoding="utf-8"))
            self.assertEqual(account["algo"], ma.PBKDF2_ALGO)
            self.assertNotIn(PASSWORD, json.dumps(account))

    def test_unconfigured_state_roots_fail_closed(self):
        _expect_refused(self, "mfa.status", {"user_id": "x"}, {},
                        "mfa_state_root_not_configured")
        with tempfile.TemporaryDirectory() as tmp:
            config = {"mfa_state_root": str(Path(tmp) / "mfa")}
            _expect_refused(self, "mfa.status", {"user_id": "x"}, config,
                            "vault_state_root_not_configured")

    def test_unknown_mfa_method_refused(self):
        _expect_refused(self, "mfa.transmogrify", {}, {"mfa_state_root": "x",
                                                       "vault_state_root": "y"},
                        "method_not_connected:mfa.transmogrify")


class TwoStepLoginTests(unittest.TestCase):
    def test_enroll_then_two_step_login(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _fresh_config(Path(tmp))
            enroll = _enrolled(Path(tmp), config)
            self.assertEqual(enroll["recovery_count"], 8)
            self.assertEqual(len(enroll["recovery_codes"]), 8)
            self.assertTrue(enroll["otpauth_uri"].startswith(
                "otpauth://totp/JusBench:lawyer_a?secret="))
            secret = _b32_secret(enroll["secret_base32"])
            self.assertEqual(len(secret), ma._TOTP_SECRET_BYTES)
            status = legal_entry.call("mfa.status",
                                      {"user_id": "lawyer_a"}, config)
            self.assertTrue(status["mfa_enrolled"])
            self.assertEqual(status["recovery_codes_remaining"], 8)
            # 第一步：密码过但已注册 MFA＝mfa_required 且绝不发会话。
            login = legal_entry.call("auth.login",
                                     {"user_id": "lawyer_a",
                                      "password": PASSWORD, "now": 1025},
                                     config)
            self.assertEqual(login["status"], "mfa_required")
            self.assertNotIn("session_token", login)
            # 第二步：TOTP（合成 now 注入）→才发会话。
            code = ma.totp_at(secret, 1026)
            verify = legal_entry.call("mfa.verify",
                                      {"user_id": "lawyer_a", "code": code,
                                       "now": 1026}, config)
            self.assertEqual(verify["status"], "ok")
            self.assertEqual(verify["factor"], "totp")
            self.assertTrue(verify["session_token"])
            # 错码具名拒。
            _expect_refused(self, "mfa.verify",
                            {"user_id": "lawyer_a", "code": "000000",
                             "now": 1027}, config, "mfa_totp_invalid")

    def test_totp_window_replay_expiry_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _fresh_config(Path(tmp))
            enroll = _enrolled(Path(tmp), config)
            secret = _b32_secret(enroll["secret_base32"])
            # 前一窗（-30s）在 ±1 容差内接受。
            prev = legal_entry.call(
                "mfa.verify", {"user_id": "lawyer_a",
                               "code": ma.totp_at(secret, 1026 - 30),
                               "now": 1026}, config)
            self.assertEqual(prev["status"], "ok")
            # 同窗重放＝具名拒（防重放位单调）。
            _expect_refused(self, "mfa.verify",
                            {"user_id": "lawyer_a",
                             "code": ma.totp_at(secret, 1026 - 30),
                             "now": 1026}, config, "mfa_totp_replay")
            # 过期窗（-120s，窗外）＝具名拒（可复现过期窗口）。
            _expect_refused(self, "mfa.verify",
                            {"user_id": "lawyer_a",
                             "code": ma.totp_at(secret, 1026 - 120),
                             "now": 1026}, config, "mfa_totp_window_exceeded")

    def test_recovery_code_one_time_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _fresh_config(Path(tmp))
            enroll = _enrolled(Path(tmp), config)
            codes = enroll["recovery_codes"]
            recovered = legal_entry.call(
                "mfa.recover", {"user_id": "lawyer_a",
                                "recovery_code": codes[0], "now": 1030},
                config)
            self.assertEqual(recovered["status"], "ok")
            self.assertEqual(recovered["factor"], "recovery")
            self.assertEqual(recovered["remaining_recovery_codes"], 7)
            # 一次性消费：复用同一枚＝具名拒；未消耗余码仍可用。
            _expect_refused(self, "mfa.recover",
                            {"user_id": "lawyer_a",
                             "recovery_code": codes[0], "now": 1031},
                            config, "mfa_recovery_code_invalid")
            again = legal_entry.call(
                "mfa.recover", {"user_id": "lawyer_a",
                                "recovery_code": codes[1], "now": 1032},
                config)
            self.assertEqual(again["remaining_recovery_codes"], 6)
            _expect_refused(self, "mfa.recover",
                            {"user_id": "lawyer_a",
                             "recovery_code": "deadbeef00", "now": 1033},
                            config, "mfa_recovery_code_invalid")

    def test_disable_invalidate_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _fresh_config(Path(tmp))
            enroll = _enrolled(Path(tmp), config)
            secret = _b32_secret(enroll["secret_base32"])
            vault_entry = (Path(tmp) / "vault" / "credentials"
                           / ma.MFA_VAULT_SERVICE
                           / ("lawyer_a" + ma._TOTP_ACCOUNT_SUFFIX + ".json"))
            self.assertTrue(vault_entry.is_file())
            # 错密码／错因子／缺因子类型全具名拒，登记位不动。
            _expect_refused(self, "mfa.disable",
                            {"user_id": "lawyer_a", "password": "wrong",
                             "factor_type": "totp",
                             "factor": ma.totp_at(secret, 1040), "now": 1040},
                            config, "mfa_password_mismatch")
            _expect_refused(self, "mfa.disable",
                            {"user_id": "lawyer_a", "password": PASSWORD,
                             "factor_type": "totp", "factor": "000000",
                             "now": 1040}, config, "mfa_totp_invalid")
            _expect_refused(self, "mfa.disable",
                            {"user_id": "lawyer_a", "password": PASSWORD,
                             "factor_type": "eyeball", "factor": "x",
                             "now": 1040}, config, "mfa_factor_type_invalid")
            self.assertTrue(vault_entry.is_file())
            # 密码＋有效第二因子＝失效成立。
            disabled = legal_entry.call(
                "mfa.disable", {"user_id": "lawyer_a", "password": PASSWORD,
                                "factor_type": "totp",
                                "factor": ma.totp_at(secret, 1041),
                                "now": 1041}, config)
            self.assertTrue(disabled["disabled"])
            # 拆后：TOTP/恢复码/重复失效全具名拒；保险库登记位拆除。
            _expect_refused(self, "mfa.verify",
                            {"user_id": "lawyer_a",
                             "code": ma.totp_at(secret, 1042), "now": 1042},
                            config, "mfa_not_enrolled")
            _expect_refused(self, "mfa.recover",
                            {"user_id": "lawyer_a",
                             "recovery_code": enroll["recovery_codes"][2],
                             "now": 1043}, config, "mfa_not_enrolled")
            _expect_refused(self, "mfa.disable",
                            {"user_id": "lawyer_a", "password": PASSWORD,
                             "factor_type": "totp",
                             "factor": ma.totp_at(secret, 1044), "now": 1044},
                            config, "mfa_not_enrolled")
            self.assertFalse(vault_entry.exists())
            recovery_entry = (Path(tmp) / "vault" / "credentials"
                              / ma.MFA_VAULT_SERVICE
                              / ("lawyer_a"
                                 + ma._RECOVERY_ACCOUNT_SUFFIX + ".json"))
            self.assertFalse(recovery_entry.exists())
            # 登录回落密码级基底（preserved 不变）。
            login = legal_entry.call("auth.login",
                                     {"user_id": "lawyer_a",
                                      "password": PASSWORD, "now": 1045},
                                     config)
            self.assertEqual((login["status"], login["factor"]),
                             ("ok", "password"))


class ZeroPlaintextTests(unittest.TestCase):
    """密钥和恢复码不明文日志（沿 E10 字节级扫描先例＋负控）。"""

    def test_full_flow_zero_plaintext_in_all_persisted_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _fresh_config(Path(tmp))
            # config 面落盘（被扫描覆盖）。
            config_dir = Path(tmp) / "config"
            config_dir.mkdir()
            (config_dir / "bridge-config.json").write_text(
                json.dumps(config), encoding="utf-8")
            # 日志面落盘（运行日志＝操作元数据；被扫描覆盖）。
            logs_dir = Path(tmp) / "logs"
            logs_dir.mkdir()
            (logs_dir / "run.log").write_text(
                "auth.register exit 0\nmfa.enroll exit 0\nmfa.verify exit 0\n",
                encoding="utf-8")
            enroll = _enrolled(Path(tmp), config)
            secret = _b32_secret(enroll["secret_base32"])
            legal_entry.call("auth.login",
                             {"user_id": "lawyer_a", "password": PASSWORD,
                              "now": 1025}, config)
            legal_entry.call("mfa.verify",
                             {"user_id": "lawyer_a",
                              "code": ma.totp_at(secret, 1026), "now": 1026},
                             config)
            legal_entry.call("mfa.recover",
                             {"user_id": "lawyer_a",
                              "recovery_code": enroll["recovery_codes"][0],
                              "now": 1030}, config)
            needles = [PASSWORD.encode("utf-8"), secret,
                       enroll["secret_base32"].encode("ascii")]
            needles += [c.encode("ascii") for c in enroll["recovery_codes"]]
            hits = _scan_hits(Path(tmp), needles)
            self.assertEqual(hits, [])
            # 受控泄漏负控：故意落一针证明扫描器非空转，移除后复扫零命中。
            leak = Path(tmp) / "logs" / "leak-negative-control.tmp"
            leak.write_text(enroll["recovery_codes"][1], encoding="utf-8")
            self.assertEqual(len(_scan_hits(Path(tmp), needles)), 1)
            leak.unlink()
            self.assertEqual(_scan_hits(Path(tmp), needles), [])

    def test_enroll_evidence_payload_zero_secret(self):
        # 证据/回执投影面纪律：status 面零 secret_base32 零恢复码。
        with tempfile.TemporaryDirectory() as tmp:
            config = _fresh_config(Path(tmp))
            enroll = _enrolled(Path(tmp), config)
            status = legal_entry.call("mfa.status",
                                      {"user_id": "lawyer_a"}, config)
            self.assertNotIn("secret_base32", status)
            self.assertNotIn("recovery_codes", status)
            self.assertNotIn("otpauth_uri", status)
            for code in enroll["recovery_codes"]:
                self.assertNotIn(code, json.dumps(status))


class BridgeSubprocessTests(unittest.TestCase):
    """真产品入口子进程径（legal_entry CLI；同既有 recon 纪律）。"""

    def test_two_step_login_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _fresh_config(Path(tmp))
            req = Path(tmp) / "request.json"
            cfg = Path(tmp) / "config.json"

            def call_cli(method, args):
                req.write_text(json.dumps({"method": method, "args": args}),
                               encoding="utf-8")
                cfg.write_text(json.dumps(config), encoding="utf-8")
                proc = subprocess.run(
                    [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
                     "--request-json", str(req), "--config", str(cfg)],
                    capture_output=True, text=True, encoding="utf-8",
                    timeout=120)
                payload = json.loads(proc.stdout)
                return proc.returncode, payload

            code, out = call_cli("auth.register",
                                 {"user_id": "cli_user",
                                  "password": PASSWORD, "now": 2000})
            self.assertEqual((code, out["status"]), (0, "OWNER_RESPONSE"))
            code, out = call_cli("mfa.enroll",
                                 {"user_id": "cli_user",
                                  "password": PASSWORD, "now": 2010})
            self.assertEqual(code, 0)
            secret = _b32_secret(out["result"]["secret_base32"])
            code, out = call_cli("auth.login",
                                 {"user_id": "cli_user",
                                  "password": PASSWORD, "now": 2020})
            self.assertEqual((code, out["result"]["status"]),
                             (0, "mfa_required"))
            code, out = call_cli("mfa.verify",
                                 {"user_id": "cli_user",
                                  "code": ma.totp_at(secret, 2020),
                                  "now": 2020})
            self.assertEqual((code, out["result"]["status"]), (0, "ok"))
            # 桥配置落盘面零 secret（CLI 径同一断言）。
            self.assertNotIn(PASSWORD, cfg.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
