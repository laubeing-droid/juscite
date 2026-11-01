# -*- coding: utf-8 -*-
"""W3-U23 · F02-selfhost 最小管理台（stdlib-only，容器内运行）。

06:F02「自托管 docker-compose 形态（Postgres+最小管理台）」的 v1 入口：
HTTP 面把 harness HarnessUnits 公开方法的封闭子集暴露给宿主验收驱动，
直连 harness E08 既有 lh-pg-e08（PgMatterStore，org 隔离=同库一 schema）。

纪律：
- 纯标准库（harness 为零第三方依赖；容器 python:3.12-alpine 直接跑）。
- 方法白名单=封闭表，表外方法 404 具名拒（fail-closed，不冒成功）。
- 只回传公开回执；不落任何原件/凭据日志。
- 每请求一 store 实例（ThreadingHTTPServer 下不共享连接）。
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HARNESS_SRC = "/harness/src"
if HARNESS_SRC not in sys.path:
    sys.path.insert(0, HARNESS_SRC)

PG_DSN = os.environ["LH_F02_PG_DSN"]
PG_SCHEMA = os.environ["LH_F02_SCHEMA"]

from legal_harness.state import pg_wire  # noqa: E402
from legal_harness.state.pg_store import PgMatterStore  # noqa: E402
from legal_harness.business.units import HarnessUnits  # noqa: E402

STATE_ROOT = Path("/state")  # 容器内占位根（PG 形态下状态真源在 PG schema）


def _store() -> HarnessUnits:
    return HarnessUnits(PgMatterStore(STATE_ROOT, dsn=PG_DSN, schema=PG_SCHEMA))


# ---- 封闭方法表（显式适配，无反射魔法） --------------------------------

def m_create_matter(a):
    return _store().create_matter(a["actor_id"], a["scope"], a["key"],
                                  a["profile_ref"], a["intake_ref"])


def m_register_material(a):
    return _store().register_material(a["actor_id"], a["scope"], a["key"],
                                      a["material"])


def m_add_material_revision(a):
    return _store().add_material_revision(a["actor_id"], a["scope"], a["key"],
                                          a["revision"])


def m_decide_materials(a):
    return _store().decide_materials(a["actor_id"], a["scope"], a["key"],
                                     a["material_refs"], a["decision"])


def m_read_material(a):
    return _store().read_material(a["scope"], a["material_id"],
                                  a.get("revision"),
                                  actor_id=a.get("actor_id"))


def m_list_materials(a):
    return _store().list_materials(a["scope"], actor_id=a.get("actor_id"))


def m_cash_entitlement_register(a):
    return _store().cash_entitlement_register(a["actor_id"], a["scope"],
                                              a["key"], a["entitlement"])


def m_cash_source_register(a):
    return _store().cash_source_register(a["actor_id"], a["scope"], a["key"],
                                         a["source"])


def m_cash_balance_read(a):
    return _store().cash_balance_read(a["scope"], as_of=a.get("as_of"))


def m_case_member_declare(a):
    return _store().case_member_declare(a["actor_id"], a["scope"], a["key"],
                                        a["members"], a.get("note"))


def m_case_permission_rule(a):
    return _store().case_permission_rule(a["actor_id"], a["scope"], a["key"],
                                         a["rules"], a.get("note"))


def m_case_permission_veto(a):
    return _store().case_permission_veto(a["actor_id"], a["scope"], a["key"],
                                         a["vetoes"], a.get("note"))


def m_case_permission_read(a):
    return _store().case_permission_read(a["scope"], a.get("actor_id"))


METHODS = {
    "harness.create_matter": m_create_matter,
    "harness.register_material": m_register_material,
    "harness.add_material_revision": m_add_material_revision,
    "harness.decide_materials": m_decide_materials,
    "harness.read_material": m_read_material,
    "harness.list_materials": m_list_materials,
    "harness.cash_entitlement_register": m_cash_entitlement_register,
    "harness.cash_source_register": m_cash_source_register,
    "harness.cash_balance_read": m_cash_balance_read,
    "harness.case_member_declare": m_case_member_declare,
    "harness.case_permission_rule": m_case_permission_rule,
    "harness.case_permission_veto": m_case_permission_veto,
    "harness.case_permission_read": m_case_permission_read,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "lh-f02-selfhost/1"

    def log_message(self, fmt, *args):  # 静默访问日志（证据只落验收工具）
        pass

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            try:
                parsed = pg_wire.parse_dsn(PG_DSN)
                conn = pg_wire.PgConnection(
                    host=parsed["host"], port=parsed["port"],
                    dbname=parsed["dbname"], user=parsed["user"],
                    password=parsed["password"], schema=PG_SCHEMA)
                try:
                    row = conn.execute("SELECT version()").fetchone()
                    version = str(row[0]).split()[1] if row else "unknown"
                finally:
                    conn.close()
                self._json(200, {"ok": True, "schema": PG_SCHEMA,
                                 "pg": version, "methods": len(METHODS)})
            except Exception as exc:  # noqa: BLE001 — 健康面如实报故障
                self._json(503, {"ok": False, "schema": PG_SCHEMA,
                                 "error": f"{type(exc).__name__}"})
            return
        self._json(404, {"error": "f02_route_not_found"})

    def do_POST(self):
        if self.path != "/call":
            self._json(404, {"error": "f02_route_not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            method = request.get("method")
            args = request.get("args") or {}
            handler = METHODS.get(method)
            if handler is None:
                self._json(404, {"error": "f02_method_not_allowed",
                                 "method": method})
                return
            self._json(200, {"ok": True, "result": handler(args)})
        except Exception as exc:  # noqa: BLE001 — typed 错误码透传（如
            # case_permission_denied / material_id_conflict），其余带类型名
            self._json(409, {"ok": False,
                             "error": str(exc) or type(exc).__name__,
                             "type": type(exc).__name__})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
