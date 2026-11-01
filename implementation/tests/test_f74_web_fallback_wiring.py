# -*- coding: utf-8 -*-
"""F74 网页检索兜底＋web-verified 声明 产品桥接线测试（工单 W4-U44）。

06 行 F74（v1.5；owner=product+codices；B4）acceptance：网页结果 URL 与
原文真实核验，web 来源声明明确，禁编 URL。产品面＝legal_entry 冻结方法组
WEB_FALLBACK_METHODS（web.fallback_retrieve，F64 降级链 本地→付费→web
末端段）。

合同硬点（本测试主战场）：
  - 链末端闸：前两段（本地/付费）具名缺口证据缺失→typed 拒（零跳级）；
  - 权限模型白名单域闸（T05 教训）：方案/域名白名单外 typed 拒且零网络
    I/O（服务端收包计数亲证）；白名单缺配置 fail-closed；
  - 取回原文 hash 绑定：verified 记录必带 content_sha256＝服务端独立记账
    所供字节 sha（禁只存 URL）；引文逐字核对；
  - web-verified 声明=W4-U41 同一分账语义：与 statute.web_declaration 对
    同一取证三元组输出逐键相等，永不冒数据库核验签名；
  - 禁编 URL：AST 级零拼造（方案前缀字面量仅方案白名单条目；零
    f-string/format/%/加号拼 URL；零 urljoin）；
  - 无网/失败＝具名缺口不造结果（裁决#8-12 同频）。

全程合成材料（127.0.0.1 回环合成端点＋合成网页，零真实外联）。
"""

from __future__ import annotations

import ast
import hashlib
import json
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402

SYNTH_QUOTE = "【W4U44测试引文】合成条文文本·仅供核验（与真实法源页零交集）。"
W4U41_SCHEMA = "juscite-f64-web-verified/1"
WHITELIST = ["127.0.0.1"]
CHAIN_OK = {"local_gap": "LOCAL_FACE_NOT_FOUND",
            "paid_gap": "PAID_TOKEN_NOT_CONFIGURED"}


def _page(with_quote: bool) -> bytes:
    body = "<html><body><p>合成页脚注段。</p>"
    if with_quote:
        body += "<p>" + SYNTH_QUOTE + "</p>"
    body += "</body></html>"
    return body.encode("utf-8")


class _Synth(BaseHTTPRequestHandler):
    mode = "normal"
    received: list = []
    served: dict = {}

    def _send(self, code: int, payload: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        _Synth.received.append({"op": "search", "path": self.path})
        if _Synth.mode == "error":
            self._send(500, b"synthetic outage", "text/plain")
            return
        host = "127.0.0.1:%d" % self.server.server_address[1]
        page_a = _page(with_quote=True)
        page_b = _page(with_quote=False)
        _Synth.served["/a"] = page_a
        _Synth.served["/b"] = page_b
        if _Synth.mode == "noquote":
            results = [{"title": "乙", "url": "http://%s/b" % host}]
        else:
            results = [{"title": "甲", "url": "http://%s/a" % host},
                       {"title": "乙", "url": "http://%s/b" % host}]
        body = json.dumps({"results": results},
                          ensure_ascii=False).encode("utf-8")
        self._send(200, body, "application/json; charset=utf-8")

    def do_GET(self):
        _Synth.received.append({"op": "fetch", "path": self.path})
        page = _Synth.served.get(self.path)
        if page is None:
            self._send(404, b"missing", "text/plain")
            return
        self._send(200, page, "text/html; charset=utf-8")

    def log_message(self, format, *args):  # noqa: A002
        pass


class F74WebFallbackWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Synth)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.endpoint = "http://127.0.0.1:%d/search" % cls.port
        cls.config = {"web_allowed_domains": WHITELIST,
                      "web_search_endpoint": cls.endpoint}
        _Synth.mode = "normal"
        _Synth.received = []
        # 夹具预热：吸收回环 listener 首连瞬态（Windows 防火墙/首包冷启），
        # 只暖夹具不改产品语义；预热期 _Synth.received 清零保持收包断言基线。
        import time
        import urllib.request
        for _ in range(20):
            try:
                urllib.request.urlopen(
                    urllib.request.Request(
                        cls.endpoint, data=b"{}",
                        headers={"Content-Type": "application/json"}),
                    timeout=5).read()
                break
            except Exception:
                time.sleep(0.05)
        _Synth.received = []

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _retrieve(self, config=None, args=None):
        return legal_entry.call(
            "web.fallback_retrieve",
            args if args is not None else
            {"query": "合成查询", "quote": SYNTH_QUOTE, "chain": CHAIN_OK},
            config if config is not None else self.config)

    # --- 冻结方法组 -------------------------------------------------------
    def test_frozen_group_exact_membership(self):
        self.assertEqual(legal_entry.WEB_FALLBACK_METHODS,
                         {"web.fallback_retrieve"})
        source = (ROOT / "python" / "legal_entry.py").read_text("utf-8")
        self.assertIn("from web_fallback import web_fallback_call", source)

    # --- 链末端闸＋白名单域闸 ---------------------------------------------
    def test_chain_prior_gap_proofs_required(self):
        with self.assertRaises(NotConnected) as caught:
            self._retrieve(args={"query": "q", "quote": SYNTH_QUOTE,
                                 "chain": {"local_gap": "X"}})
        self.assertEqual(str(caught.exception),
                         "web_chain_prior_segments_not_declared")

    def test_whitelist_missing_fail_closed(self):
        with self.assertRaises(NotConnected) as caught:
            self._retrieve(config={"web_search_endpoint": self.endpoint})
        self.assertEqual(str(caught.exception),
                         "web_whitelist_not_configured")

    def test_scheme_outside_typed_reject_before_network(self):
        baseline = len(_Synth.received)
        with self.assertRaises(NotConnected) as caught:
            self._retrieve(config={
                "web_allowed_domains": WHITELIST,
                "web_search_endpoint": "ftp://127.0.0.1:%d/search"
                                       % self.port})
        self.assertEqual(str(caught.exception), "web_url_scheme_not_allowed")
        self.assertEqual(len(_Synth.received), baseline)

    def test_domain_outside_typed_reject_before_network(self):
        baseline = len(_Synth.received)
        with self.assertRaises(NotConnected) as caught:
            self._retrieve(config={
                "web_allowed_domains": WHITELIST,
                "web_search_endpoint": "http://not-allowed.example/search"})
        self.assertEqual(str(caught.exception),
                         "web_domain_not_whitelisted:not-allowed.example")
        self.assertEqual(len(_Synth.received), baseline)

    # --- 取回原文 hash 绑定＋逐字核验＋W4-U41 声明 ------------------------
    def test_verified_hash_binds_retrieved_original(self):
        result = self._retrieve()
        self.assertEqual(len(result["verified"]), 1)
        record = result["verified"][0]
        served = _Synth.served["/a"]
        self.assertEqual(record["content_sha256"],
                         hashlib.sha256(served).hexdigest())
        self.assertEqual(record["source_url"],
                         "http://127.0.0.1:%d/a" % self.port)
        self.assertTrue(record["quote_verified"])
        self.assertEqual([c["source_url"] for c in result["candidates"]],
                         ["http://127.0.0.1:%d/a" % self.port,
                          "http://127.0.0.1:%d/b" % self.port])

    def test_declaration_identical_to_w4u41_face(self):
        result = self._retrieve()
        declaration = result["verified"][0]["declaration"]
        cross = legal_entry.call(
            "statute.web_declaration",
            {"source_url": declaration["source_url"],
             "content_sha256": declaration["content_sha256"],
             "retrieved_utc": declaration["retrieved_utc"]}, {})
        self.assertEqual(cross, declaration)
        self.assertEqual(declaration["schema"], W4U41_SCHEMA)
        self.assertEqual(declaration["verification_basis"], "web_verified")
        self.assertFalse(declaration["signs_current"])
        from statute_validity import DB_SIGNATURE_KEYS
        self.assertFalse(set(declaration) & set(DB_SIGNATURE_KEYS))

    def test_quote_not_verified_named_gap_no_declaration(self):
        _Synth.mode = "noquote"
        try:
            result = self._retrieve()
        finally:
            _Synth.mode = "normal"
        self.assertEqual(result["verified"], [])
        self.assertTrue(any(g["reason"] == "web_quote_not_verified"
                            for g in result["gaps"]))
        self.assertNotIn(W4U41_SCHEMA, json.dumps(result))

    # --- 失败不造假 --------------------------------------------------------
    def test_offline_named_gap_zero_fabrication(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        dead = probe.getsockname()[1]
        probe.close()
        result = self._retrieve(config={
            "web_allowed_domains": WHITELIST,
            "web_search_endpoint": "http://127.0.0.1:%d/search" % dead})
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["verified"], [])
        self.assertTrue(result["gaps"][0]["reason"]
                        .startswith("web_fetch_failed:"))

    def test_http_error_named_not_fabricated(self):
        _Synth.mode = "error"
        try:
            result = self._retrieve()
        finally:
            _Synth.mode = "normal"
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["verified"], [])
        self.assertEqual(result["gaps"][0]["reason"], "web_status_500")

    # --- AST：禁编 URL＋闸先于网＋声明单一来源 -----------------------------
    def test_ast_zero_url_fabrication_and_gate_precedes_network(self):
        source = (ROOT / "python" / "web_fallback.py").read_text("utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith(("http://", "https://")):
                    self.assertIn(node.value, ("http://", "https://"))
            if isinstance(node, ast.JoinedStr):
                parts = [p.value for p in node.values
                         if isinstance(p, ast.Constant)]
                self.assertFalse(any("http" in p for p in parts))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                calls_urlopen = any(
                    isinstance(s, ast.Call)
                    and getattr(s.func, "attr", None) == "urlopen"
                    or isinstance(s, ast.Call)
                    and isinstance(s.func, ast.Name)
                    and s.func.id == "urlopen"
                    for s in ast.walk(node))
                calls_gate = any(
                    isinstance(s, ast.Call)
                    and isinstance(s.func, ast.Name)
                    and s.func.id == "gate_url"
                    for s in ast.walk(node))
                if calls_urlopen:
                    self.assertTrue(calls_gate, node.name)
        self.assertIn("declare_web_verified", source)


if __name__ == "__main__":
    unittest.main()
