# -*- coding: utf-8 -*-
"""F64 v1.5 产品侧接线测试（工单 W4-U41）：付费通道负测先行＋web-verified 分账。

全部合成材料：P11 付费通道以 127.0.0.1 回环合成 mock 端点实测请求面
（裁决#8-12 负测先行，绝不真打付费服务，真授权后补）；web 兜底段＝
web-verified 声明机制分账断言（web-verified 永不冒数据库核验签名）。
钉定文件缺失/漂移即响亮失败，不静默跳过。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import threading
import unittest
import unittest.mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import statute_validity  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

COMMERCIAL_PATH = Path(
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\tools\commercial_law_mcp.py"
)
COMMERCIAL_SHA256 = (
    "b7b7c1fe1faf57791b84969b1c47cdfcef62b1a3ed97482dbbe09d4204aef0a9"
)

SYNTHETIC_TOKEN = "synthetic-f64-v15-pytest-token"


def load_commercial_module():
    if not COMMERCIAL_PATH.is_file():
        raise FileNotFoundError(
            f"pinned P11 consumer missing at {COMMERCIAL_PATH} "
            "(14-Python入口与施工接线.md P11)")
    digest = hashlib.sha256(COMMERCIAL_PATH.read_bytes()).hexdigest()
    if digest != COMMERCIAL_SHA256:
        raise AssertionError(
            f"pinned commercial_law_mcp.py drifted: sha256 {digest} != "
            f"{COMMERCIAL_SHA256}")
    spec = importlib.util.spec_from_file_location(
        "commercial_law_mcp_v15", COMMERCIAL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _MockMcpHandler(BaseHTTPRequestHandler):
    received: list = []
    mode = "ok"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        params = request.get("params") or {}
        _MockMcpHandler.received.append({
            "authorization": self.headers.get("Authorization", ""),
            "tool": params.get("name"),
            "arguments": params.get("arguments"),
        })
        if _MockMcpHandler.mode == "ok":
            body = {"jsonrpc": "2.0", "id": request.get("id"), "result": {
                "content": [{"type": "text", "text": json.dumps(
                    {"synthetic": True, "echo_tool": params.get("name")})}],
                "isError": False}}
        else:
            body = {"jsonrpc": "2.0", "id": request.get("id"), "error": {
                "code": -32000, "message": "synthetic_mock_auth_denied"}}
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002
        pass


class WebDeclarationSeparateLedgerTest(unittest.TestCase):
    """web-verified 声明机制：与数据库核验分账，永不冒签名。"""

    EVIDENCE = {
        "source_url": "https://mock-web.invalid/synthetic/statute-page",
        "content_sha256": hashlib.sha256(b"synthetic-w4u41").hexdigest(),
        "retrieved_utc": "2026-10-21T00:00:00+00:00",
    }

    def test_basis_web_verified_never_database(self):
        result = legal_entry.call("statute.web_declaration",
                                  dict(self.EVIDENCE), {})
        self.assertEqual(result["verification_basis"],
                         statute_validity.VERIFICATION_BASIS_WEB)
        self.assertNotEqual(result["verification_basis"],
                            statute_validity.VERIFICATION_BASIS_LOCAL_DB)
        self.assertNotEqual(result["verification_basis"],
                            statute_validity.VERIFICATION_BASIS_PAID_DB)
        self.assertFalse(result["signs_current"])

    def test_basis_distinct_from_p11_registry_source_types(self):
        module = load_commercial_module()
        source_types = {"%s_VERIFIED" % name for name in module.PROVIDERS}
        declaration = legal_entry.call("statute.web_declaration",
                                       dict(self.EVIDENCE), {})
        self.assertNotIn(declaration["verification_basis"], source_types)

    def test_declaration_zero_db_signature_keys(self):
        module = load_commercial_module()
        db_keys = {"source_type", "provider_record_id", "provider_url",
                   "provider", "face_sha256", "lccc_face"}
        # 产品面声明的签名键合同与 P11 真实注册表字段一致（引用 FrozenFace
        # 钉定模块存在性），声明键集与之零交。
        self.assertTrue(module.PROVIDERS)
        declaration = legal_entry.call("statute.web_declaration",
                                       dict(self.EVIDENCE), {})
        self.assertEqual(set(declaration) & db_keys, set())
        self.assertEqual(set(declaration)
                         & set(statute_validity.DB_SIGNATURE_KEYS), set())

    def test_missing_evidence_fails_named(self):
        for key in ("source_url", "content_sha256", "retrieved_utc"):
            partial = {k: v for k, v in self.EVIDENCE.items() if k != key}
            with self.assertRaises(NotConnected) as ctx:
                legal_entry.call("statute.web_declaration", partial, {})
            self.assertEqual(
                str(ctx.exception), "web_declaration_evidence_missing:" + key)

    def test_url_scheme_allowlist_and_sha_shape(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("statute.web_declaration",
                             dict(self.EVIDENCE,
                                  source_url="ftp://mock-web.invalid/x"), {})
        self.assertEqual(str(ctx.exception),
                         "web_declaration_url_scheme_not_allowed")
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("statute.web_declaration",
                             dict(self.EVIDENCE, content_sha256="nothex"), {})
        self.assertEqual(str(ctx.exception),
                         "web_declaration_content_sha256_malformed")

    def test_unknown_statute_method_still_not_connected(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("statute.verify", {}, {})
        self.assertIn("method_not_connected", str(ctx.exception))


class PaidChannelNegativeFirstTest(unittest.TestCase):
    """付费通道 v1.5（裁决#8-12 负测先行）：客户端真建＋mock 请求面可达。"""

    @classmethod
    def setUpClass(cls):
        cls.module = load_commercial_module()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _MockMcpHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        _MockMcpHandler.received = []
        _MockMcpHandler.mode = "ok"
        self.env_patch = unittest.mock.patch.dict(
            "os.environ", {cfg["token_env"]: SYNTHETIC_TOKEN
                           for cfg in self.module.PROVIDERS.values()})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def _point_at_mock(self):
        # 内存内覆盖 PROVIDERS url 到回环 mock（盘上钉定文件零触碰——
        # load_commercial_module 每次 setUpClass 复验 sha256）。
        original = {name: self.module.PROVIDERS[name]["url"]
                    for name in self.module.PROVIDERS}
        for name in self.module.PROVIDERS:
            self.module.PROVIDERS[name]["url"] = \
                "http://127.0.0.1:%d/mcp" % self.port
        self.addCleanup(self._restore_urls, original)

    def _restore_urls(self, original):
        for name, url in original.items():
            self.module.PROVIDERS[name]["url"] = url

    def test_client_really_constructed_with_synthetic_token(self):
        for name in self.module.PROVIDERS:
            client = self.module.McpHttpClient(name)
            self.assertIs(type(client), self.module.McpHttpClient)
            self.assertEqual(
                client.headers.get("Authorization"),
                "Bearer " + SYNTHETIC_TOKEN)

    def test_request_surface_reachable_over_loopback_mock(self):
        self._point_at_mock()
        tools = {"YUANDIAN": "yuandian_rh_fg_search",
                 "PKULAW": "search_article"}
        for name, tool in tools.items():
            result = self.module.McpHttpClient(name).call(
                tool, {"synthetic_probe": name})
            parsed = json.loads(result["content"][0]["text"])
            self.assertTrue(parsed["synthetic"])
            self.assertEqual(parsed["echo_tool"], tool)
        self.assertEqual(len(_MockMcpHandler.received), 2)
        for record in _MockMcpHandler.received:
            self.assertEqual(record["authorization"],
                             "Bearer " + SYNTHETIC_TOKEN)
            self.assertIn(record["tool"], set(tools.values()))

    def test_error_envelope_named_failure_never_fabricated(self):
        self._point_at_mock()
        _MockMcpHandler.mode = "error"
        with self.assertRaises(RuntimeError) as ctx:
            self.module.McpHttpClient("YUANDIAN").call(
                "yuandian_rh_fg_search", {})
        self.assertIn("synthetic_mock_auth_denied", str(ctx.exception))

    def test_frozen_file_bytes_untouched_after_mock_run(self):
        self._point_at_mock()
        self.module.McpHttpClient("PKULAW").call("search_article", {})
        digest = hashlib.sha256(COMMERCIAL_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, COMMERCIAL_SHA256)


if __name__ == "__main__":
    unittest.main()
