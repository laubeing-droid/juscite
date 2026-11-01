# -*- coding: utf-8 -*-
"""#43 订阅型推理引擎合成全链自测（RE-43 §3.7 覆盖清单；2026-10-30）。

全部合成材料：环回假授权服务器+假 API 服务（127.0.0.1 隔离端口 3090 起），
**不碰真 OpenAI 端点**（规格 §3.7；SIWC=OpenAI 预览协议，服务端行为本地不
可实证=规格 UNKNOWN-1，本测试钉的是我方引擎状态机与守卫序）。真 RS256 签
名/验签（cryptography 本机在位）。

覆盖（规格 §3.7 逐条）：
  ①登录全链（PKCE S256 对账/state 窗/一次性/hostId/scope 钉定/动态 client
    回填/令牌只进 vault·index 零令牌字节）；
  ②id_token 校验七负例（签名/iss/aud/exp(-5s)/iat/nonce/sub）；
  ③刷新串行+节流+整组替换；
  ④终态失效清凭证 vs 网络故障（5xx 不确定结局）不清凭证；
  ⑤退出撤销（5xx 续试 3 止/4xx 即止/清本地留映射）；
  ⑥401 强刷重试一次/503 退避两试；
  ⑦用量上限→回落 API Key（vault 取键、backend 留痕、原因码具名）+三查
    负例（未登录/需重登/未开套餐）+未配回落具名拒不伪答；
  ⑧Codex 交接路 env 注入（令牌不经命令行）+Windows .cmd shim 解析。
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
import threading
import time
import unittest
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import subscription_engine as se  # noqa: E402
from credential_vault import VaultError, vault_get, vault_put  # noqa: E402

# ── 合成 RSA 密钥与 JWKS（真签名真验签） ──
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402

KID = "synth-siwc-key-1"
_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_WRONG_PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64url_int(value: int) -> str:
    size = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(
        value.to_bytes(size, "big")).decode("ascii").rstrip("=")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


_PUB = _PRIVATE.public_key().public_numbers()
JWKS = {"keys": [{"kty": "RSA", "alg": "RS256", "use": "sig", "kid": KID,
                  "n": _b64url_int(_PUB.n), "e": _b64url_int(_PUB.e)}]}


def sign_id_token(claims: dict, *, key=None, kid: str = KID,
                  alg: str = "RS256") -> str:
    key = key or _PRIVATE  # alg 伪造负例：签名仍用 RSA，头改不支持算法
    header = {"alg": alg, "kid": kid, "typ": "JWT"}
    signing_input = (_b64url(json.dumps(header).encode())
                     + "." + _b64url(json.dumps(claims).encode()))
    if alg == "RS256":
        signature = key.sign(signing_input.encode(), padding.PKCS1v15(),
                             hashes.SHA256())
    else:  # alg 拒绝负例：伪造不支持的算法头
        signature = key.sign(signing_input.encode(), padding.PKCS1v15(),
                             hashes.SHA256())
    return signing_input + "." + _b64url(signature)


# ── 环回假服务（隔离端口 3090 起） ──────────────────────────────────────

def _pick_port(start: int) -> int:
    for port in range(start, start + 40):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), _Silent)
            server.server_close()
            return port
        except OSError:
            continue
    raise RuntimeError("no free port from %d" % start)


class _Silent(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 零日志（凭据纪律同面：测试服务也不打印）
        pass

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            return {}

    def _reply(self, status: int, body: dict | None = None,
               headers: dict | None = None):
        payload = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)


class FakeAuthHandler(_Silent):
    """假授权服务器：/oauth/token（授权码+刷新两类 grant）、/.well-known/
    jwks.json、/oauth/revoke。行为按 server 脚本可控。"""

    def do_GET(self):
        if urlparse(self.path).path == "/.well-known/jwks.json":
            return self._reply(200, JWKS)
        return self._reply(404, {"error": "not_found"})

    def do_POST(self):
        server = self.server
        path = urlparse(self.path).path
        body = self._read_json()
        if path == "/oauth/token":
            if body.get("grant_type") == "authorization_code":
                server.exchange_bodies.append(dict(body))
                expect = server.expect.get(str(body.get("code") or ""))
                if expect is None:
                    return self._reply(400, {"error": "invalid_grant"})
                return self._reply(200, expect["response"])
            server.refresh_calls.append(dict(body))
            server.refresh_concurrent += 1
            server.refresh_max_concurrent = max(
                server.refresh_max_concurrent, server.refresh_concurrent)
            try:
                if server.refresh_delay:
                    time.sleep(server.refresh_delay)
                script = server.refresh_script.popleft() \
                    if server.refresh_script else "ok"
                if script in (503, 500):
                    return self._reply(script, {"error": "server_error"})
                if script == "terminal":
                    return self._reply(400, {"error": "invalid_grant"})
                if script == "invalid_client":
                    return self._reply(401, {"error": "invalid_client"})
                if script == "other":
                    return self._reply(400, {"error": "scope_too_big"})
                return self._reply(200, {
                    "client_id": "srv-client-1",
                    "access_token": "synth-access-"
                    + _b64url(str(len(server.refresh_calls)).encode()),
                    "refresh_token": "synth-refresh-"
                    + _b64url(str(len(server.refresh_calls)).encode()),
                    "id_token": sign_id_token({
                        "iss": server.auth_base, "aud": "srv-client-1",
                        "exp": time.time() + 600, "iat": time.time(),
                        "nonce": "unused-refresh", "sub": "synth-sub-1",
                        "email": "lawyer@synth.example"}),
                    "scope": se.SCOPES,
                    "expires_in": server.refresh_expires_in,
                })
            finally:
                server.refresh_concurrent -= 1
        if path == "/oauth/revoke":
            server.revoke_calls.append(1)
            script = server.revoke_script.popleft() \
                if server.revoke_script else [200]
            status = script[0] if isinstance(script, tuple) else script
            return self._reply(status, {} if status == 200
                               else {"error": "revoke_failed"})
        return self._reply(404, {"error": "not_found"})


class FakeApiHandler(_Silent):
    """假订阅 API：/models、/responses（脚本化行为队列）；假回落 API：
    /chat/completions。"""

    def do_GET(self):
        server = self.server
        path = urlparse(self.path).path
        if path == "/models":
            token = (self.headers.get("Authorization") or "")
            if token not in server.known_tokens:
                return self._reply(401, {"error": "bad_token"})
            return self._reply(200, {"data": [
                {"slug": "gpt-synth-pro", "visible": True},
                {"slug": "gpt-synth-mini", "visible": True},
                {"slug": "gpt-hidden", "visible": False},
            ]})
        return self._reply(404, {"error": "not_found"})

    def do_POST(self):
        server = self.server
        path = urlparse(self.path).path
        body = self._read_json()
        if path == "/responses":
            server.responses_calls.append(dict(body))
            step = server.responses_script.popleft() \
                if server.responses_script else "ok"
            if step == "401":
                return self._reply(401, {"error": {"type": "bad_token"}})
            if step == 503:
                return self._reply(503, {"error": {"type": "overloaded"}})
            if step == "usage_limit":
                return self._reply(429, {"error": {
                    "type": se.USAGE_LIMIT_WIRE_CODE}})
            return self._reply(200, {
                "id": "resp-synth-" + str(len(server.responses_calls)),
                "request_id": "req-synth-"
                + str(len(server.responses_calls)),
                "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": "合成订阅回答"}]}],
            })
        if path == "/chat/completions":
            server.fallback_calls.append({
                "authorization": self.headers.get("Authorization"),
                "body": body})
            if (self.headers.get("Authorization")
                    != "Bearer synth-fallback-key"):
                return self._reply(401, {"error": {"type": "bad_key"}})
            return self._reply(200, {
                "id": "fb-synth-1",
                "choices": [{"message": {"content": "合成回落回答"}}]})
        return self._reply(404, {"error": "not_found"})


AUTH_PORT = _pick_port(3090)
API_PORT = _pick_port(3092)
AUTH_BASE = "http://127.0.0.1:%d" % AUTH_PORT
API_BASE = "http://127.0.0.1:%d" % API_PORT

_auth_server = ThreadingHTTPServer(("127.0.0.1", AUTH_PORT), FakeAuthHandler)
_api_server = ThreadingHTTPServer(("127.0.0.1", API_PORT), FakeApiHandler)
for _server, _attrs in (
        (_auth_server, {"auth_base": AUTH_BASE, "expect": {},
                        "exchange_bodies": [], "refresh_calls": [],
                        "refresh_concurrent": 0, "refresh_max_concurrent": 0,
                        "refresh_delay": 0.0, "refresh_script": deque(),
                        "refresh_expires_in": 3600, "revoke_calls": [],
                        "revoke_script": deque()}),
        (_api_server, {"known_tokens": set(), "responses_script": deque(),
                       "responses_calls": [], "fallback_calls": []})):
    for _key, _value in _attrs.items():
        setattr(_server, _key, _value)
    threading.Thread(target=_server.serve_forever, daemon=True).start()


def _reset_servers():
    _auth_server.expect.clear()
    _auth_server.exchange_bodies.clear()
    _auth_server.refresh_calls.clear()
    _auth_server.refresh_script.clear()
    _auth_server.refresh_expires_in = 3600
    _auth_server.refresh_delay = 0.0
    _auth_server.refresh_max_concurrent = 0
    _auth_server.revoke_calls.clear()
    _auth_server.revoke_script.clear()
    _api_server.known_tokens.clear()
    _api_server.responses_script.clear()
    _api_server.responses_calls.clear()
    _api_server.fallback_calls.clear()


def _issue_access(token: str) -> str:
    """把令牌登记为 API 已知（假服务的Bearer 有效性面）。"""
    _api_server.known_tokens.add("Bearer " + token)
    return token


def _register_code(*, nonce: str, sub: str = "synth-sub-1",
                   client_id: str = "srv-client-1",
                   claims=None, scope: str = se.SCOPES,
                   expires_in: int = 3600, code: str = "synth-code") -> str:
    payload = {
        "iss": AUTH_BASE, "aud": client_id,
        "exp": time.time() + 600, "iat": time.time(),
        "nonce": nonce, "sub": sub, "email": "lawyer@synth.example"}
    payload.update(claims or {})
    _auth_server.expect[code] = {"response": {
        "client_id": client_id,
        "access_token": _issue_access("synth-access-initial"),
        "refresh_token": "synth-refresh-initial",
        "id_token": sign_id_token(payload),
        "scope": scope, "expires_in": expires_in,
    }}
    return code


FALLBACK = {"kind": "openai-compat", "api_base": API_BASE,
            "model": "deepseek-synth", "name": "deepseek-byok",
            "key_vault": {"service": "juscite.test", "account": "fb-key"}}


class SubscriptionTestCase(unittest.TestCase):
    def setUp(self):
        _reset_servers()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = {"vault_state_root": self.tmp.name,
                       "harness_state_root": self.tmp.name,
                       "siwc_auth_base": AUTH_BASE,
                       "siwc_api_base": API_BASE,
                       "siwc_backoff_schedule": (0.0, 0.0)}
        vault_put(self.tmp.name, FALLBACK["key_vault"]["service"],
                  FALLBACK["key_vault"]["account"],
                  b"synth-fallback-key")

    def login(self, **kwargs) -> dict:
        begin = se.subscription_login_begin({"redirect_port": 3099},
                                            self.config)
        query = parse_qs(urlparse(begin["authorizationUrl"]).query)
        code = _register_code(nonce=query["nonce"][0], **kwargs)
        return se.subscription_login_callback(
            {"code": code, "state": begin["state"]}, self.config)

    def index_text(self) -> str:
        return (Path(self.tmp.name) / "siwc" / "index.json").read_text(
            encoding="utf-8")

    def tokens_record(self, sub: str) -> dict:
        out = vault_get(self.tmp.name, se.VAULT_SERVICE, sub, reveal=True)
        return json.loads(base64.b64decode(out["secret_b64"]))


class LoginChainTests(SubscriptionTestCase):
    def test_full_chain_tokens_only_in_vault(self) -> None:
        """①登录全链：PKCE/hostId/scope/动态 client/令牌只进 vault。"""
        begin = se.subscription_login_begin({"redirect_port": 3099},
                                            self.config)
        url = urlparse(begin["authorizationUrl"])
        query = parse_qs(url.query)
        self.assertEqual(url.path, "/authorize")
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["scope"], [se.SCOPES])
        self.assertIn(se.PLAN_USAGE_SCOPE, query["scope"][0].split())
        self.assertTrue(query["state"][0] and query["nonce"][0])
        self.assertTrue(query[se.HOST_ID_PARAM][0].startswith("urn:uuid:"))
        self.assertEqual(begin["expiresIn"], 600)
        code = _register_code(nonce=query["nonce"][0])
        result = se.subscription_login_callback(
            {"code": code, "state": begin["state"]}, self.config)
        # PKCE 对账：code_verifier 的 S256 == authorizationUrl 挑战值。
        exchange = _auth_server.exchange_bodies[0]
        digest = base64.urlsafe_b64encode(hashlib.sha256(
            exchange["code_verifier"].encode()).digest()
        ).decode("ascii").rstrip("=")
        self.assertEqual(digest, query["code_challenge"][0])
        # 动态 client 回填：id_token aud/账号绑定均以服务器值为准。
        self.assertEqual(result["account"]["sub"], "synth-sub-1")
        self.assertTrue(result["account"]["planUsage"])
        self.assertEqual(result["defaultModel"], "gpt-synth-mini")  # 首项
        self.assertEqual(result["models"],
                         ["gpt-synth-mini", "gpt-synth-pro"])  # visible 过滤
        # 令牌只进 vault（DPAPI 解密回读），index 零令牌字节。
        record = self.tokens_record("synth-sub-1")
        self.assertEqual(record["schema"], se.TOKENS_SCHEMA)
        self.assertIn("synth-access", record["access_token"])
        index_text = self.index_text()
        self.assertNotIn("synth-access", index_text)
        self.assertNotIn("synth-refresh", index_text)
        self.assertNotIn("access_token", index_text)
        status = se.subscription_status({}, self.config)
        self.assertTrue(status["available"])
        self.assertEqual(status["activeSub"], "synth-sub-1")

    def test_id_token_seven_negatives(self) -> None:
        """②id_token 七负例（签名/alg/iss/aud/exp/iat/nonce/sub）。"""
        wrong_key = rsa.generate_private_key(public_exponent=65537,
                                             key_size=2048)

        def claims_ok(nonce: str) -> dict:
            return {"iss": AUTH_BASE, "aud": "srv-client-1",
                    "exp": time.time() + 600, "iat": time.time(),
                    "nonce": nonce, "sub": "synth-sub-1"}

        def attempt(want_code: str, claims_for, *, key=None,
                    alg: str = "RS256") -> None:
            begin = se.subscription_login_begin({"redirect_port": 3099},
                                                self.config)
            nonce = parse_qs(urlparse(
                begin["authorizationUrl"]).query)["nonce"][0]
            _auth_server.expect["synth-code"] = {"response": {
                "client_id": "srv-client-1",
                "access_token": _issue_access("synth-access-x"),
                "refresh_token": "synth-refresh-x",
                "id_token": sign_id_token(claims_for(nonce), key=key,
                                          alg=alg),
                "scope": se.SCOPES, "expires_in": 3600}}
            with self.assertRaises(se.SubscriptionError) as caught:
                se.subscription_login_callback(
                    {"code": "synth-code", "state": begin["state"]},
                    self.config)
            self.assertEqual(str(caught.exception), want_code)

        attempt("siwc_id_token_signature_invalid", claims_ok,
                key=wrong_key)
        attempt("siwc_id_token_alg_rejected", claims_ok, alg="HS256")
        attempt("siwc_id_token_iss_mismatch",
                lambda n: dict(claims_ok(n), iss="https://evil.example"))
        attempt("siwc_id_token_aud_mismatch",
                lambda n: dict(claims_ok(n), aud="other-app"))
        attempt("siwc_id_token_expired",
                lambda n: dict(claims_ok(n), exp=time.time() - 10))
        attempt("siwc_id_token_iat_invalid",
                lambda n: dict(claims_ok(n), iat=time.time() + 60))
        attempt("siwc_id_token_nonce_mismatch",
                lambda n: dict(claims_ok(n), nonce="WRONG-" + n))
        attempt("siwc_id_token_sub_missing",
                lambda n: dict(claims_ok(n), sub=""))

    def test_state_window_and_one_time(self) -> None:
        """③state 对账/10 分钟窗过期/一次性核销。"""
        with self.assertRaises(se.SubscriptionError) as caught:
            se.subscription_login_callback(
                {"code": "c", "state": "no-such-state"}, self.config)
        self.assertEqual(str(caught.exception), "siwc_state_mismatch")
        begin = se.subscription_login_begin({"redirect_port": 3099},
                                            self.config)
        nonce = parse_qs(urlparse(
            begin["authorizationUrl"]).query)["nonce"][0]
        code = _register_code(nonce=nonce)
        real_now = se._now
        se._now = lambda: real_now() + 601.0
        try:
            with self.assertRaises(se.SubscriptionError) as caught:
                se.subscription_login_callback(
                    {"code": code, "state": begin["state"]}, self.config)
            self.assertEqual(str(caught.exception),
                             "siwc_login_window_expired")
        finally:
            se._now = real_now
        begin2 = se.subscription_login_begin({"redirect_port": 3099},
                                             self.config)
        nonce2 = parse_qs(urlparse(
            begin2["authorizationUrl"]).query)["nonce"][0]
        code2 = _register_code(nonce=nonce2, code="synth-code-2")
        first = se.subscription_login_callback(
            {"code": code2, "state": begin2["state"]}, self.config)
        self.assertEqual(first["account"]["sub"], "synth-sub-1")
        with self.assertRaises(se.SubscriptionError) as caught:  # 一次性
            se.subscription_login_callback(
                {"code": code2, "state": begin2["state"]}, self.config)
        self.assertEqual(str(caught.exception), "siwc_state_mismatch")

    def test_client_account_switch_rejected(self) -> None:
        """同 client_id 换账号拒。"""
        self.login(sub="synth-sub-1")
        begin = se.subscription_login_begin({"redirect_port": 3099},
                                            self.config)
        nonce = parse_qs(urlparse(
            begin["authorizationUrl"]).query)["nonce"][0]
        code = _register_code(nonce=nonce, sub="synth-sub-2",
                              code="synth-code-b")
        with self.assertRaises(se.SubscriptionError) as caught:
            se.subscription_login_callback(
                {"code": code, "state": begin["state"]}, self.config)
        self.assertEqual(str(caught.exception),
                         "siwc_client_account_switch_rejected")


class RefreshLogoutTests(SubscriptionTestCase):
    def _set_token_ttl(self, seconds: float) -> None:
        record = self.tokens_record("synth-sub-1")
        record["expires_at"] = time.time() + seconds
        vault_put(self.tmp.name, se.VAULT_SERVICE, "synth-sub-1",
                  json.dumps(record).encode("utf-8"))

    def test_refresh_serial_throttle_replacement(self) -> None:
        """③刷新：阈值触发/整组替换/同账号串行/失败节流先用着。"""
        _auth_server.refresh_expires_in = 60  # 登录内 models 首刷即短寿命
        self.login(expires_in=100)  # <120s → 登录中 models 即触发首刷
        self.assertGreaterEqual(len(_auth_server.refresh_calls), 1)
        record = self.tokens_record("synth-sub-1")
        self.assertNotEqual(record["access_token"], "synth-access-initial")
        # 串行：慢刷新下两线程并发 → 服务器最大并发 1（refresh token 轮换
        # 并发刷=作废风险，规格 §2.1#6）。
        _auth_server.refresh_delay = 0.3
        self._set_token_ttl(100)  # 仍 <120s 每取必刷
        before = len(_auth_server.refresh_calls)
        threads = [threading.Thread(
            target=lambda: se.subscription_refresh({}, self.config))
            for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(_auth_server.refresh_max_concurrent, 1)
        self.assertEqual(len(_auth_server.refresh_calls), before + 2)
        # 节流：5xx 不确定结局后 60s 内不重锤——令牌仍有余量先用手头的。
        _auth_server.refresh_delay = 0.0
        _auth_server.refresh_expires_in = 3600
        self._set_token_ttl(100)
        _auth_server.refresh_script.append(503)
        with self.assertRaises(se.SubscriptionError) as caught:
            se.subscription_refresh({}, self.config)
        self.assertTrue(str(caught.exception).startswith(
            "siwc_refresh_unreachable"))
        after_fail = len(_auth_server.refresh_calls)
        record = se.subscription_refresh({}, self.config)  # 节流跳过刷新
        self.assertEqual(len(_auth_server.refresh_calls), after_fail)
        self.assertGreater(record["expiresAt"], time.time() + 60)

    def test_terminal_clears_network_keeps(self) -> None:
        """④终态失效清凭证+需重登；5xx（不确定结局）不清凭证。"""
        self.login()
        self._set_token_ttl(100)  # 剩余<120s → 下一次取令牌必走刷新
        _auth_server.refresh_script.append("terminal")
        with self.assertRaises(se.SubscriptionError) as caught:
            se.subscription_refresh({}, self.config)
        self.assertEqual(str(caught.exception),
                         "siwc_terminal_invalidated:invalid_grant")
        with self.assertRaises(VaultError):  # 凭证已清
            vault_get(self.tmp.name, se.VAULT_SERVICE, "synth-sub-1")
        status = se.subscription_status({}, self.config)
        self.assertTrue(status["accounts"][0]["needsLogin"])
        self.assertIn("srv-client-1", self.index_text())  # 映射保留
        # 5xx 不清凭证。
        self.login()
        self._set_token_ttl(100)
        _auth_server.refresh_script.append(503)
        with self.assertRaises(se.SubscriptionError):
            se.subscription_refresh({}, self.config)
        self.assertIn("access_token", self.tokens_record("synth-sub-1"))

    def test_logout_revoke_retry_and_cleanup(self) -> None:
        """⑤撤销：5xx 续试 3 止（成）+4xx 即止；清本地留映射。"""
        self.login()
        _auth_server.revoke_script.extend([503, 503, 200])
        out = se.subscription_logout({"sub": "synth-sub-1"}, self.config)
        self.assertTrue(out["revoked"])
        self.assertEqual(out["attempts"], 3)
        self.assertEqual(len(_auth_server.revoke_calls), 3)
        with self.assertRaises(VaultError):
            vault_get(self.tmp.name, se.VAULT_SERVICE, "synth-sub-1")
        self.assertIn("synth-sub-1", self.index_text())  # 账号映射保留
        # 4xx 即止。
        self.login()
        _auth_server.revoke_script.append(400)
        out = se.subscription_logout({"sub": "synth-sub-1"}, self.config)
        self.assertFalse(out["revoked"])
        self.assertEqual(out["attempts"], 1)
        with self.assertRaises(VaultError):
            vault_get(self.tmp.name, se.VAULT_SERVICE, "synth-sub-1")


class ChatFallbackTests(SubscriptionTestCase):
    def chat_args(self, **kwargs):
        args = {"input": "合成问题", "model": "gpt-synth-pro"}
        args.update(kwargs)
        return args

    def test_401_force_refresh_retry_once(self) -> None:
        """⑥401=强制刷新重试一次（刷新 grant 真发生，重试即成功）。"""
        self.login()
        _api_server.responses_script.append("401")
        _api_server.responses_script.append("ok")
        out = se.subscription_chat(self.chat_args(), self.config)
        self.assertEqual(out["replyText"], "合成订阅回答")
        self.assertEqual(out["backend"], "chatgpt-sub:synth-sub-1")
        self.assertFalse(out["fallbackUsed"])
        self.assertTrue(str(_auth_server.refresh_calls[-1][
            "refresh_token"]).startswith("synth-refresh"))
        # 第二问不带 401 脚本 → 直接成功（刷新后的令牌已登记）。
        out2 = se.subscription_chat(self.chat_args(), self.config)
        self.assertEqual(out2["replyText"], "合成订阅回答")

    def test_503_backoff_two_retries(self) -> None:
        """⑥503 退避重试两试后成功。"""
        self.login()
        _api_server.responses_script.extend([503, 503])
        out = se.subscription_chat(self.chat_args(), self.config)
        self.assertEqual(out["replyText"], "合成订阅回答")
        self.assertEqual(len(_api_server.responses_calls), 3)

    def test_usage_limit_falls_back_with_ledger_marker(self) -> None:
        """⑦用量上限→回落 API Key：vault 取键/backend 留痕/原因码。"""
        self.login()
        _api_server.responses_script.append("usage_limit")
        out = se.subscription_chat(self.chat_args(fallback=FALLBACK),
                                   self.config)
        self.assertTrue(out["fallbackUsed"])
        self.assertEqual(out["fallbackReason"], "subscription_usage_limit")
        self.assertEqual(out["backend"], "api-key:deepseek-byok")
        self.assertEqual(out["replyText"], "合成回落回答")
        self.assertEqual(len(_api_server.fallback_calls), 1)
        self.assertEqual(_api_server.fallback_calls[0]["authorization"],
                         "Bearer synth-fallback-key")

    def test_three_check_negatives_and_no_fabrication(self) -> None:
        """⑦三查负例（未登录/需重登/未开套餐）+未配回落具名拒不伪答。"""
        out = se.subscription_chat(self.chat_args(fallback=FALLBACK),
                                   self.config)
        self.assertEqual(out["fallbackReason"], "siwc_not_logged_in")
        self.assertEqual(_api_server.fallback_calls[-1]["body"]["model"],
                         "deepseek-synth")
        self.login()
        se.subscription_logout({"sub": "synth-sub-1"}, self.config)
        out = se.subscription_chat(self.chat_args(fallback=FALLBACK),
                                   self.config)
        self.assertEqual(out["fallbackReason"], "siwc_needs_relogin")
        # 未开套餐：scope 无套餐用量位。
        self.login(scope="openid profile email offline_access")
        _api_server.responses_script.clear()
        out = se.subscription_chat(self.chat_args(fallback=FALLBACK),
                                   self.config)
        self.assertEqual(out["fallbackReason"], "siwc_plan_usage_absent")
        # 未配回落且订阅不可用＝具名拒，绝不伪答。
        with self.assertRaises(se.SubscriptionError) as caught:
            se.subscription_chat(self.chat_args(), self.config)
        self.assertEqual(str(caught.exception), "siwc_plan_usage_absent")


class HandoverTests(SubscriptionTestCase):
    def test_codex_handover_env_and_cmd_shim(self) -> None:
        """⑧交接：令牌只进 env 不进命令行；.cmd shim 解析出 js 入口。"""
        self.login()
        fixture_dir = Path(self.tmp.name) / "bin"
        (fixture_dir / "node_modules" / "codex" / "bin").mkdir(parents=True)
        target = fixture_dir / "node_modules" / "codex" / "bin" / "codex.js"
        target.write_text("// synth codex entry\n", encoding="utf-8")
        wrapper = fixture_dir / "codex.cmd"
        wrapper.write_text(
            '@ECHO off\r\nIF EXIST "%~dp0\\node.exe" (\r\n'
            '  SET "_prog=%~dp0\\node.exe"\r\n)\r\n'
            '"%_prog%"  "%~dp0\\node_modules\\codex\\bin\\codex.js" %*\r\n',
            encoding="utf-8")
        out = se.subscription_codex_handover(
            {"codex_path": str(wrapper)}, self.config)
        self.assertEqual(out["origin"], "shim-node")
        self.assertEqual(len(out["command"]), 2)  # node + 目标脚本
        self.assertTrue(out["command"][0].lower().endswith("node.exe"))
        self.assertEqual(Path(out["command"][1]), target)
        self.assertEqual(out["providerConfig"]["configArgs"]["wire_api"],
                         "responses")
        self.assertEqual(out["providerConfig"]["configArgs"]["base_url"],
                         API_BASE)
        token = self.tokens_record("synth-sub-1")["access_token"]
        self.assertEqual(out["env"][se.HANDOVER_ENV_KEY], token)
        self.assertFalse(any(token in part for part in out["command"]))
        # 令牌余量不足 15 分钟＝交接拒（长轮余量守卫；余量 300s≥120s
        # 不触发刷新，直接走余量判定）。
        record = self.tokens_record("synth-sub-1")
        record["expires_at"] = time.time() + 300
        vault_put(self.tmp.name, se.VAULT_SERVICE, "synth-sub-1",
                  json.dumps(record).encode("utf-8"))
        with self.assertRaises(se.SubscriptionError) as caught:
            se.subscription_codex_handover(
                {"codex_path": str(wrapper)}, self.config)
        self.assertEqual(str(caught.exception),
                         "siwc_handover_token_short_lived")


class SourceDisciplineTests(SubscriptionTestCase):
    def test_engine_source_zero_logging_and_legal_entry_dispatch(self):
        """红线：引擎源零 print/零 logging（令牌不进日志）；legal_entry
        分发+typed 码透传。"""
        import legal_entry
        source = (ROOT / "python" / "subscription_engine.py").read_text(
            encoding="utf-8")
        self.assertNotIn("print(", source)
        self.assertNotIn("import logging", source)
        self.assertEqual(legal_entry.SUBSCRIPTION_METHODS,
                         se.SUBSCRIPTION_METHODS)
        out = legal_entry.call("subscription.status", {}, self.config)
        self.assertEqual(out["engine"], se.ENGINE_ID)
        with self.assertRaises(legal_entry.NotConnected) as caught:
            legal_entry.call("subscription.login_callback",
                             {"code": "c", "state": "s"}, self.config)
        self.assertIn("subscription_failed:siwc_state_mismatch",
                      str(caught.exception))


if __name__ == "__main__":
    unittest.main()
