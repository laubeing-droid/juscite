"""Pinned OpenCode v2 HTTP wiring; no Agent loop or legal business logic.

Mutations are NEVER retried automatically. A timeout after a mutation is an
unknown outcome: reconcile the caller's message id against the inbox/history.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

PIN = "2.0.28"

class TransportError(RuntimeError):
    def __init__(self, code: str, uncertain: bool = False):
        self.code, self.uncertain = code, uncertain
        super().__init__(code)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TransportError("redirect_refused")

class Client:
    def __init__(self, base_url: str, *, headers=None, timeout=30, opener=None):
        u = urlsplit(base_url)
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ("", "/"):
            raise ValueError("base_url_must_be_origin_without_credentials")
        if u.scheme == "http" and u.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("remote_requires_https")
        self.url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout
        # Loopback requests must not send service credentials through a proxy.
        handlers = [NoRedirect()]
        if u.hostname in ("localhost", "127.0.0.1", "::1"):
            handlers.append(ProxyHandler({}))
        self.opener = opener or build_opener(*handlers)

    def request(self, method: str, path: str, body=None):
        parsed, _ = self.request_raw(method, path, body)
        return parsed

    def request_raw(self, method: str, path: str, body=None):
        """同 request，但连同响应原始字节一起返回（E05 transcript＝回读原字节）。

        W3-U24 增补：既有 request 行为逐字节不变（现改为薄委托）；变异不重试
        与错误分类保持同源。
        """
        headers = {"Accept": "application/json", **self.headers}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(self.url + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            # Do not print server bodies: they may contain case data or secrets.
            raise TransportError(f"http_{exc.code}", uncertain=method != "GET" and exc.code >= 500) from None
        except (URLError, TimeoutError, OSError):
            raise TransportError("transport_failure", uncertain=method != "GET") from None
        if not raw:
            return None, b""
        try:
            return json.loads(raw), raw
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise TransportError("protocol_response_invalid", uncertain=method != "GET") from None

    def verify_version(self):
        info = self.request("GET", "/api/info")
        value = info.get("data", info) if isinstance(info, dict) else {}
        if not isinstance(value, dict):
            raise TransportError("protocol_response_invalid")
        if value.get("version") != PIN:
            raise TransportError("runtime_version_mismatch")
        return info

    def create(self, request):
        return self.request("POST", "/api/session", request)

    def session(self, sid):
        return self.request("GET", f"/api/session/{quote(sid, safe='')}")

    def prompt(self, sid, request):
        if not isinstance(request.get("text"), str) or not request.get("id"):
            raise ValueError("prompt_requires_text_and_caller_persisted_message_id")
        return self.request("POST", f"/api/session/{quote(sid, safe='')}/prompt", request)

    def interrupt(self, sid):
        return self.request("POST", f"/api/session/{quote(sid, safe='')}/interrupt?resume=false")

    def inbox(self, sid):
        return self.request("GET", f"/api/session/{quote(sid, safe='')}/inbox")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("operation", choices=["info", "create", "get", "prompt", "interrupt", "inbox"])
    p.add_argument("--url", default="http://127.0.0.1:43127")
    p.add_argument("--session")
    p.add_argument("--request-json", type=Path)
    a = p.parse_args()
    headers = {}
    if os.environ.get("JUSBENCH_AGENT_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["JUSBENCH_AGENT_TOKEN"]
    elif os.environ.get("JUSBENCH_AGENT_PASSWORD") and os.environ.get("JUSBENCH_AGENT_USERNAME"):
        raw = (os.environ["JUSBENCH_AGENT_USERNAME"] + ":" + os.environ["JUSBENCH_AGENT_PASSWORD"]).encode()
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    else:
        p.error("service authentication must be provided by product credentials; no secret in argv")
    c = Client(a.url, headers=headers)
    try:
        info = c.verify_version()
        if a.operation == "info": result = info
        elif a.operation == "create":
            if not a.request_json:p.error("create requires --request-json")
            result = c.create(json.loads(a.request_json.read_text(encoding="utf-8-sig")))
        else:
            if not a.session:p.error("operation requires --session")
            if a.operation == "prompt":
                if not a.request_json:p.error("prompt requires --request-json")
                result = c.prompt(a.session, json.loads(a.request_json.read_text(encoding="utf-8-sig")))
            else: result = {"get":c.session,"interrupt":c.interrupt,"inbox":c.inbox}[a.operation](a.session)
        print(json.dumps({"status":"TRANSPORT_RESPONSE","business_complete":False,"response":result}, ensure_ascii=False))
    except TransportError as exc:
        print(json.dumps({"status":"OUTCOME_UNKNOWN" if exc.uncertain else "ERROR","code":exc.code,"business_complete":False}))
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
