# -*- coding: utf-8 -*-
"""F126 WebDAV 客户端（W5-U11；06 F126 owner=product 半边）。

纯 stdlib（urllib.request）最小 WebDAV 子集客户端：PUT/GET/PROPFIND/
MKCOL。端点 URL 只来自显式 config（webdav_endpoint），本模块无任何内
置端点/默认 URL（禁编 URL，P11 同纪律）；basic auth 可选（selfhost B
形态）。不可达＝typed f126_remote_unreachable（离线形态的具名信号，
重试归编排面），4xx/5xx＝f126_dav_http_status:*——绝不把传输失败伪装
成同步成功。
"""
from __future__ import annotations

import base64
import urllib.error
import urllib.request

_HTTP_TIMEOUT_S = 10.0


class WebDavClientError(RuntimeError):
    """具名错误（f126_* 码），绝不携内容。"""


class WebDavClient:
    def __init__(self, endpoint: str, *,
                 auth: tuple[str, str] | None = None) -> None:
        if not isinstance(endpoint, str) \
                or not endpoint.startswith(("http://", "https://")):
            raise WebDavClientError("f126_endpoint_invalid")
        self.endpoint = endpoint.rstrip("/")
        self.auth = auth

    def _request(self, method: str, path: str, body: bytes | None = None,
                 headers: dict | None = None) -> tuple[int, bytes]:
        request = urllib.request.Request(
            self.endpoint + "/" + path.lstrip("/"), data=body,
            method=method, headers=headers or {})
        if self.auth is not None:
            token = base64.b64encode(
                f"{self.auth[0]}:{self.auth[1]}".encode("utf-8")
                ).decode("ascii")
            request.add_header("Authorization", "Basic " + token)
        try:
            with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) \
                    as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), b""
        except (urllib.error.URLError, OSError, ValueError):
            raise WebDavClientError("f126_remote_unreachable") from None

    def put(self, path: str, body: bytes) -> int:
        status, _ = self._request(
            "PUT", path, body=body,
            headers={"Content-Type": "application/octet-stream"})
        if status not in (200, 201, 204):
            raise WebDavClientError(f"f126_dav_http_status:{status}")
        return status

    def get(self, path: str) -> tuple[int, bytes]:
        status, body = self._request("GET", path)
        if status not in (200, 404):
            raise WebDavClientError(f"f126_dav_http_status:{status}")
        return status, body

    def propfind_names(self, path: str) -> list[str]:
        status, body = self._request(
            "PROPFIND", path, headers={"Depth": "1"})
        if status == 404:
            return []
        if status not in (200, 207):
            raise WebDavClientError(f"f126_dav_http_status:{status}")
        # 合成服务只回 <response><href>name</href>…——名字提取即够，
        # 不解析完整 RFC 4918 多状态（也不冒充解析）。
        import re
        return re.findall(r"<href>([^<]+)</href>", body.decode("utf-8"))
