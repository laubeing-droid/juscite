# -*- coding: utf-8 -*-
"""F126 合成 WebDAV 服务（W5-U11；06 F126 owner=product 半边；裁决#13-19
「WebDAV 合成先行」——loopback 本地纯 stdlib 合成服务，真实 WebDAV 设施
v2 商业化时补）。

形态（合成端点先行的 F60 裁决#6 同纪律）：
* 只绑 127.0.0.1（loopback），零外发、零真实凭据；basic auth 可选
  （selfhost B 形态开启，桌面单机形态可关）。
* 方法面窄闭集：OPTIONS/PROPFIND/MKCOL/PUT/GET/DELETE——多设备同步
  所需的最小 WebDAV 子集（Class 1 的子集），不冒充完整 RFC 4918。
* 服务端对字节零解释：bundle/manifest 一律不透明 .bin（端到端信封由
  持钥端封/开，服务端永不见明文——本模块就是 recon「服务端侧零明文」
  断言的观察面：access_log 记录每次请求的方法/路径/字节数）。
* URL 只来自显式 config（device_sync.webdav_endpoint），本模块无默认
  端点、不编 URL（P11 同纪律）。

目录形态（自托管 B 形态沿 F02/F08 既有面，不重复建）：
    <root>/<space>/bundles/<sha256-of-envelope>.bin   # 内容寻址不透明
    <root>/<space>/manifests/<device_id>.bin          # 每端各自 manifest
"""
from __future__ import annotations

import base64
import hmac
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

_METHODS = ("OPTIONS", "PROPFIND", "MKCOL", "PUT", "GET", "DELETE")
# 段长上限 199：bundle 落盘名双摘要（bundleId 64 + "." + 信封 sha 64 +
# ".bin"）＝134 字符，device manifest＝≤68；白名单字符＋长度双闸防写穿。
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
# PUT 体上限。负的或非数字 Content-Length 不能交给 rfile.read：read(-1) 会一直读到 EOF。
_MAX_PUT_BYTES = 32 * 1024 * 1024


class SyntheticWebDavError(RuntimeError):
    """具名错误（f126_dav_* 码），绝不携内容。"""


def _segment(value: object, code: str) -> str:
    text = value if isinstance(value, str) else ""
    if not _SAFE_SEGMENT.match(text):
        raise SyntheticWebDavError(code)
    return text


class SyntheticWebDavServer:
    """loopback 合成 WebDAV：start() 拉起 ThreadingHTTPServer（随机空闲
    端口），stop() 关闭；storage_root 下按 space 隔离。"""

    def __init__(self, storage_root, *, space: str = "lvyin-sync",
                 auth: tuple[str, str] | None = None) -> None:
        self.storage_root = Path(storage_root)
        self.space = _segment(space, "f126_dav_space_invalid")
        self.auth = auth
        self.access_log: list[dict] = []
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        server = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # 静默：stderr 可能携路径
                pass

            def _record(self, size: int = 0) -> None:
                with server._lock:
                    server.access_log.append({
                        "method": self.command, "path": self.path,
                        "bytes": int(size),
                    })

            def _authorized(self) -> bool:
                if server.auth is None:
                    return True
                header = self.headers.get("Authorization", "")
                expected = "Basic " + base64.b64encode(
                    f"{server.auth[0]}:{server.auth[1]}".encode("utf-8")
                    ).decode("ascii")
                try:
                    return hmac.compare_digest(header, expected)
                except (TypeError, ValueError):
                    return False

            def _read_limited_body(self) -> bytes | None:
                raw = self.headers.get("Content-Length", "0").strip()
                # 位数先于 int()：超长数字串不必先变成任意精度整数。
                if len(raw) > 10 or not raw.isdigit():
                    return None
                length = int(raw)
                if length > _MAX_PUT_BYTES:
                    return None
                return self.rfile.read(length) if length else b""

            def _reply(self, status: int, body: bytes = b"",
                       content_type: str = "application/octet-stream") -> None:
                self.send_response(status)
                if body:
                    self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("DAV", "1")
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def _target(self):
                """解析请求路径到 storage 内路径：首段＝space（物理目录
                级隔离，多 space 不共盘）；其余逐段白名单字符。越界/上跳
                /非常规段一律 None＝404/403，绝不写穿根。"""
                parsed = urlparse(self.path)
                parts = [segment for segment in
                         unquote(parsed.path).split("/") if segment]
                if not parts or parts[0] != server.space:
                    return None
                current = server.storage_root / server.space
                for part in parts[1:]:
                    if not _SAFE_SEGMENT.match(part):
                        return None
                    current = current / part
                return current

            def do_OPTIONS(self) -> None:
                self.send_response(200)
                self.send_header("Allow", ", ".join(_METHODS))
                self.send_header("Content-Length", "0")
                self.send_header("DAV", "1")
                self.end_headers()

            def do_PROPFIND(self) -> None:
                self._record()
                if not self._authorized():
                    self._reply(401)
                    return
                target = self._target()
                depth = self.headers.get("Depth", "0")
                if target is None:
                    self._reply(404)
                    return
                if target.is_file():
                    self._reply(207, _propfind_file(target))
                    return
                if target.is_dir() and depth == "1":
                    entries = sorted(
                        _propfind_file(child)
                        for child in target.iterdir() if child.is_file())
                    self._reply(207, b"<multistatus>" + b"".join(entries)
                                + b"</multistatus>")
                    return
                self._reply(207 if target.is_dir() else 404)

            def do_MKCOL(self) -> None:
                self._record()
                if not self._authorized():
                    self._reply(401)
                    return
                target = self._target()
                if target is None:
                    self._reply(403)
                    return
                target.mkdir(parents=True, exist_ok=True)
                self._reply(201)

            def do_PUT(self) -> None:
                body = self._read_limited_body()
                if body is None:
                    self.close_connection = True
                    self._record(0)
                    self._reply(400)
                    return
                self._record(len(body))
                if not self._authorized():
                    self._reply(401)
                    return
                target = self._target()
                if target is None or target.is_dir():
                    self._reply(403)
                    return
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                self._reply(201)

            def do_GET(self) -> None:
                self._record()
                if not self._authorized():
                    self._reply(401)
                    return
                target = self._target()
                if target is None or not target.is_file():
                    self._reply(404)
                    return
                self._reply(200, target.read_bytes())

            def do_DELETE(self) -> None:
                self._record()
                if not self._authorized():
                    self._reply(401)
                    return
                target = self._target()
                if target is None or not target.exists():
                    self._reply(404)
                    return
                if target.is_file():
                    target.unlink()
                self._reply(204)

        self._handler = _Handler

    @property
    def port(self) -> int:
        if self._httpd is None:
            raise SyntheticWebDavError("f126_dav_not_started")
        return self._httpd.server_address[1]

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.port}/{self.space}"

    def start(self) -> "SyntheticWebDavServer":
        if self._httpd is not None:
            raise SyntheticWebDavError("f126_dav_already_started")
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler)
        thread = threading.Thread(target=self._httpd.serve_forever,
                                  kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def __enter__(self) -> "SyntheticWebDavServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


def _propfind_file(path: Path) -> bytes:
    return (f"<response><href>{path.name}</href>"
            f"<getcontentlength>{path.stat().st_size}</getcontentlength>"
            f"</response>").encode("utf-8")
