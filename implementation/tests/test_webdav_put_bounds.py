# -*- coding: utf-8 -*-
"""F126 合成 WebDAV：PUT 的 Content-Length 必须是有界非负整数。

非数字、负数和超过上限的长度在读体之前拒绝。合法短 PUT 仍可落盘。
"""
from __future__ import annotations

import base64
import http.client
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from webdav_server import SyntheticWebDavServer  # noqa: E402


def _basic(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return "Basic " + token


class WebDavPutBoundsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="f126-put-")
        self.addCleanup(self._tmp.cleanup)
        self.server = SyntheticWebDavServer(
            Path(self._tmp.name), space="lvyin-sync",
            auth=("sync", "secret"))
        self.server.start()
        self.addCleanup(self.server.stop)

    def _conn(self) -> http.client.HTTPConnection:
        return http.client.HTTPConnection(
            "127.0.0.1", self.server.port, timeout=2)

    def _put_length(self, length: str) -> int:
        conn = self._conn()
        conn.putrequest("PUT", "/lvyin-sync/bundles/Abc.bin")
        conn.putheader("Content-Length", length)
        conn.putheader("Authorization", _basic("sync", "secret"))
        conn.endheaders()
        response = conn.getresponse()
        status = response.status
        response.read()
        conn.close()
        return status

    def test_negative_content_length_is_400(self):
        self.assertEqual(self._put_length("-1"), 400)
        self.assertFalse(any(Path(self._tmp.name).rglob("*.bin")))

    def test_non_numeric_content_length_is_400(self):
        self.assertEqual(self._put_length("nope"), 400)
        self.assertFalse(any(Path(self._tmp.name).rglob("*.bin")))

    def test_huge_content_length_is_400(self):
        self.assertEqual(self._put_length("9999999999"), 400)
        self.assertEqual(self._put_length("99999999999"), 400)

    def test_bounded_put_still_writes(self):
        conn = self._conn()
        conn.putrequest("PUT", "/lvyin-sync/bundles/Abc.bin")
        body = b"xyz"
        conn.putheader("Content-Length", str(len(body)))
        conn.putheader("Authorization", _basic("sync", "secret"))
        conn.endheaders()
        conn.send(body)
        response = conn.getresponse()
        self.assertEqual(response.status, 201)
        response.read()
        conn.close()
        stored = Path(self._tmp.name) / "lvyin-sync" / "bundles" / "Abc.bin"
        self.assertEqual(stored.read_bytes(), body)

    def test_wrong_auth_rejected(self):
        conn = self._conn()
        conn.putrequest("PUT", "/lvyin-sync/bundles/Abc.bin")
        conn.putheader("Content-Length", "1")
        conn.putheader("Authorization", _basic("nope", "pe"))
        conn.endheaders()
        conn.send(b"z")
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        response.read()
        conn.close()
        self.assertFalse(any(Path(self._tmp.name).rglob("*.bin")))


if __name__ == "__main__":
    unittest.main()
