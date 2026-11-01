# -*- coding: utf-8 -*-
"""F82 审查面真机 Electron CDP 会话驱动（W2b-U31；U07 先例）。

一次性检出（scratch clone @026b106＋patches 001-014＋scratch CDP 注入，
不入 patch 014）。链路：Electron 主进程 review-surface 桥服务（config
门禁）→产品桥 legal_entry CLI→harness public_entry→SQLite MatterStore。

断言（UI 触发→harness 落账→回读三段）：
  S01 审查面渲染：表格 8 格（4 行×2 列）DOM 就位（[data-review-cell]）
  S02 复核（UI 按钮→回执落账）：reviewStatus 翻转 REVIEWED_CONFIRMED
      ＋harness review_receipt_read 独立回读对上（UI+公开面双证据）
  S03 单格重跑（UI 按钮→claim→rerun→release 落账）：值/世代/来源更新
      ＋rowState=pending＋harness review_batch_read 对上
  S04 人工改格（UI 按钮→human_edit 落账）：source=human＋harness 对上
  S05 人改后重跑响亮拒：UI 点击→typed 码 review_rerun_human_cell 呈现
      ＋人改值保全（harness 回读）
  S06 履历回读（UI 按钮→cell_history）：旧值历史呈现
  S07 harness 落账独立对账：UI 会话产生的全部写经 public_entry CLI
      回读（回执 2 条/重跑 gen/人改值/历史三代）

证据：docs/construction/evidence/F82/desktop/f82-review-surface-electron.png
＋f82-review-ops-cdp-readback.json。会话毕杀 Electron＋删临时 config。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(r"D:\Codex\1.法律工作区\jusbench工作区\juscite\.local\worktrees\w2b-u31")
HARNESS_ROOT = Path(r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo\.local\worktrees\w2b-u31")
CLONE = Path(os.environ["TEMP"]) / "oc28-chain" / "clone3"
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
PUBLIC_ENTRY = HARNESS_ROOT / "tools/workflow-tools/harness/public_entry.py"

MATTER = "desktop-review"
BATCH = "brt-f82-desktop"
SCOPE = {"kind": "matter", "matterId": MATTER}
CDP_PORT = 8317
USER_DATA = Path(os.environ["APPDATA"]) / "Juscite"

COLUMNS = [
    {"id": "amount", "name": "合同金额", "format": "decimal-string",
     "version": "1", "gold": {"kind": "number", "expect": "123456.78"}},
    {"id": "cited", "name": "法律依据", "format": "text", "version": "1",
     "gold": {"kind": "text"}},
]


def command_key(request_id: str) -> dict:
    return {"requestId": "cdp-" + request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def harness_call(method: str, params: dict, state_root: Path) -> dict:
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "params": params}, handle,
                  ensure_ascii=False)
        handle.close()
        env = dict(os.environ)
        env["LH_LEGAL_STATE_ROOT"] = str(state_root)
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(PUBLIC_ENTRY),
             "--reviewbatch-json", handle.name, "--target", "opencode"],
            capture_output=True, text=True, encoding="utf-8", env=env,
            timeout=180, cwd=str(HARNESS_ROOT))
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"_stdout": proc.stdout[-400:],
                    "_stderr": proc.stderr[-200:], "_exit": proc.returncode}
    finally:
        os.unlink(handle.name)


def prepare_state(state_root: Path, registration: Path) -> None:
    sys.path.insert(0, str(HARNESS_ROOT / "src"))
    from legal_harness.state.matter_store import MatterStore
    MatterStore(state_root).create_matter(MATTER, "cas://profile-f82-desktop")
    results = []
    results.append(harness_call("harness.review_batch_create", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rb1"),
        "batch": {"id": BATCH, "title": "F82 审查面（桌面真机合成）",
                  "columns": [{"id": c["id"], "name": c["name"]}
                              for c in COLUMNS],
                  "rows": [{"id": "row-%d" % i,
                            "cells": {"amount": None, "cited": None}}
                           for i in range(1, 5)]}}, state_root))
    results.append(harness_call("harness.review_columns_define", {
        "actor_id": "lawyer-1", "scope": SCOPE, "key": command_key("rc1"),
        "batch_id": BATCH, "columns": COLUMNS}, state_root))
    for result in results:
        if not isinstance(result, dict) or "result" not in result:
            raise SystemExit("FATAL: 状态准备失败：%s" % result)


def write_config(state_root: Path, registration: Path) -> Path:
    config_path = USER_DATA / "config" / "lvyin" / "review.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "python": sys.executable,
        "bridge_entry": str(LEGAL_ENTRY),
        "review_batch_id": BATCH,
        "review_matter_id": MATTER,
        "harness_public_entry": str(PUBLIC_ENTRY),
        "harness_target": "opencode",
        "harness_state_root": str(state_root),
        "harness_service_registration": str(registration),
        "harness_python": sys.executable,
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    return config_path


class Cdp:
    """极小 CDP 客户端（Runtime.evaluate / Page.captureScreenshot）。"""

    def __init__(self, ws_url: str):
        import websocket  # websocket-client
        self.conn = websocket.create_connection(ws_url, timeout=30)
        self.seq = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.seq += 1
        self.conn.send(json.dumps({"id": self.seq, "method": method,
                                   "params": params or {}}))
        while True:
            message = json.loads(self.conn.recv())
            if message.get("id") == self.seq:
                return message

    def evaluate(self, expression: str, await_promise: bool = False):
        result = self.call("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": await_promise})
        value = result.get("result", {}).get("result", {})
        if value.get("type") == "undefined":
            return None
        if value.get("type") == "string" and "subtype" not in value:
            return value.get("value")
        return value.get("value")

    def screenshot(self, path: str) -> None:
        shot = self.call("Page.captureScreenshot",
                         {"format": "png"})["result"]["data"]
        import base64
        Path(path).write_bytes(base64.b64decode(shot))


def wait_for_port(port: int, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json" % port, timeout=2) as response:
                targets = json.loads(response.read().decode("utf-8"))
                pages = [t for t in targets if t.get("type") == "page"]
                if pages:
                    return pages[0]
        except Exception:
            time.sleep(1.0)
    raise SystemExit("FATAL: CDP 端口 %d 超时未就绪" % port)


JS_OPEN_PANEL = """(() => {
  const buttons = [...document.querySelectorAll('button')];
  const toggle = buttons.find(b => b.textContent && (b.textContent.includes('Tabular 审查面') || b.textContent.includes('收起审查面')));
  if (!toggle) return 'toggle-not-found';
  if (toggle.textContent.includes('Tabular 审查面')) toggle.click();
  return 'opened';
})()"""


def js_wait(selector: str, timeout_ms: int = 20000) -> str:
    return (
        "new Promise(resolve => {const t0=Date.now();"
        "const tick=()=>{const el=document.querySelector('%s');"
        "if(el)resolve(true);else if(Date.now()-t0>%d)resolve(false);"
        "else setTimeout(tick,120)};tick()})" % (selector, timeout_ms))


def js_set_input(selector: str, value: str) -> str:
    return (
        "(() => {const el=document.querySelector('%s');"
        "if(!el) return 'input-not-found';"
        "const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLInputElement.prototype,'value').set;"
        "setter.call(el,%s);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "return 'set';})()" % (selector, json.dumps(value)))


def js_click_cell_action(cell: str, action: str) -> str:
    selector = '[data-review-cell="' + cell + '"]'
    return (
        "(() => {const row=document.querySelector(%s);"
        "if(!row) return 'cell-not-found';"
        "const btn=row.querySelector('[data-review-action=\"%s\"]');"
        "if(!btn) return 'button-not-found';btn.click();return 'clicked';})()"
        % (json.dumps(selector), action))


def js_attr(selector: str, attr: str) -> str:
    return (
        "(() => {const el=document.querySelector('%s');"
        "return el ? el.getAttribute('%s') : null;})()" % (selector, attr))


def js_text(selector: str) -> str:
    return ("(() => {const el=document.querySelector('%s');"
            "return el ? el.textContent : null;})()" % selector)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    temporary = tempfile.TemporaryDirectory(prefix="f82-cdp-")
    state_root = Path(temporary.name) / "state"
    state_root.mkdir(parents=True)
    registration = Path(temporary.name) / "service-local.json"
    registration.write_text(json.dumps(
        {"url": "http://127.0.0.1:1", "password": "synthetic-cdp"}),
        encoding="utf-8")
    prepare_state(state_root, registration)
    config_path = write_config(state_root, registration)
    print("[setup] state=%s config=%s" % (state_root, config_path), flush=True)

    # 启动 Electron（scratch 检出 dev 径；CDP 注入已在 scratch main）。
    env = dict(os.environ)
    env["LVYIN_CDP_PORT"] = str(CDP_PORT)
    def _port_open() -> bool:
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json" % CDP_PORT, timeout=2):
                return True
        except Exception:
            return False

    electron = None
    if not _port_open():
            electron = subprocess.Popen(
            [r"C:\Users\being\.bun\bun.exe", "run", "dev:desktop"],
            cwd=str(CLONE), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    readback: dict = {"cdpPort": CDP_PORT, "batch": BATCH, "matter": MATTER}
    try:
        page = wait_for_port(CDP_PORT)
        cdp = Cdp(page["webSocketDebuggerUrl"])
        time.sleep(6)   # 等渲染层稳定（首屏与 seam 注入）

        # S01 面板打开与表格渲染
        opened = cdp.evaluate(JS_OPEN_PANEL)
        rendered = cdp.evaluate(
            js_wait('[data-testid="review-table"]'), await_promise=True)
        cell_count = cdp.evaluate(
            "document.querySelectorAll('[data-review-cell]').length")
        not_connected = cdp.evaluate(
            "!!document.querySelector('[data-testid=\"review-not-connected\"]')")
        meta = cdp.evaluate(js_text('[data-testid="review-table-meta"]'))
        readback["S01_panel"] = {
            "opened": opened, "rendered": rendered,
            "cellCount": cell_count, "notConnected": not_connected,
            "meta": meta}
        print("[S01] panel=%s cells=%s meta=%s notConnected=%s"
              % (opened, cell_count, meta, not_connected), flush=True)

        # S02 复核（UI 按钮→回执落账→回读）
        cdp.evaluate(js_set_input('[data-testid="review-decision-ref"]',
                                  "note-cdp-1"))
        cdp.evaluate(js_click_cell_action("row-1:amount", "receipt"))
        time.sleep(4)
        status_attr = cdp.evaluate(js_attr(
            '[data-review-cell="row-1:amount"]', "data-review-status"))
        notice = cdp.evaluate(js_text('[data-testid="review-notice"]'))
        ledger_receipt = harness_call("harness.review_receipt_read", {
            "scope": SCOPE, "batch_id": BATCH, "row_id": "row-1",
            "cell_id": "amount"}, state_root)
        readback["S02_receipt"] = {
            "domStatus": status_attr, "notice": notice,
            "ledger": ledger_receipt.get("result", {}).get("projections")}
        print("[S02] dom=%s notice=%s" % (status_attr, notice), flush=True)

        # S03 单格重跑（UI 按钮→编排落账）
        cdp.evaluate(js_set_input('[data-testid="review-rerun-value"]',
                                  "888,888.00 元"))
        cdp.evaluate(js_click_cell_action("row-2:amount", "rerun"))
        time.sleep(6)
        value_2 = cdp.evaluate(
            "document.querySelector('[data-review-cell=\"row-2:amount\"] [data-testid=\"review-cell-value\"]').textContent")
        gen_2 = cdp.evaluate(js_attr(
            '[data-review-cell="row-2:amount"]', "data-review-generation"))
        state_2 = cdp.evaluate(js_attr(
            '[data-review-cell="row-2:amount"]', "data-review-row-state"))
        ledger_row2 = harness_call("harness.review_batch_read", {
            "scope": SCOPE, "batch_id": BATCH, "row_id": "row-2"},
            state_root)
        readback["S03_rerun"] = {
            "domValue": value_2, "domGeneration": gen_2,
            "domRowState": state_2,
            "ledgerCell": (ledger_row2.get("result", {})
                           .get("row", {}).get("cells", {}).get("amount")),
            "ledgerRowState": (ledger_row2.get("result", {})
                               .get("row", {}).get("state"))}
        print("[S03] dom=%s gen=%s rowState=%s"
              % (value_2, gen_2, state_2), flush=True)

        # S04 人工改格（UI 按钮→human_edit 落账；F84 红线：唯一写通道）
        cdp.evaluate(js_set_input('[data-testid="review-edit-value"]',
                                  "人改核正值 9 元"))
        cdp.evaluate(js_click_cell_action("row-3:amount", "human-edit"))
        time.sleep(4)
        value_3 = cdp.evaluate(
            "document.querySelector('[data-review-cell=\"row-3:amount\"] [data-testid=\"review-cell-value\"]').textContent")
        source_3 = cdp.evaluate(js_attr(
            '[data-review-cell="row-3:amount"]', "data-review-source"))
        ledger_row3 = harness_call("harness.review_batch_read", {
            "scope": SCOPE, "batch_id": BATCH, "row_id": "row-3"},
            state_root)
        readback["S04_human_edit"] = {
            "domValue": value_3, "domSource": source_3,
            "ledgerCell": (ledger_row3.get("result", {})
                           .get("row", {}).get("cells", {}).get("amount"))}
        print("[S04] dom=%s source=%s" % (value_3, source_3), flush=True)

        # S05 人改后重跑响亮拒（typed 码 UI 呈现；人改值保全）
        cdp.evaluate(js_set_input('[data-testid="review-rerun-value"]',
                                  "迟到重跑 777 元"))
        cdp.evaluate(js_click_cell_action("row-3:amount", "rerun"))
        time.sleep(5)
        error_text = cdp.evaluate(js_text('[data-testid="review-error"]'))
        value_3_after = cdp.evaluate(
            "document.querySelector('[data-review-cell=\"row-3:amount\"] [data-testid=\"review-cell-value\"]').textContent")
        readback["S05_rerun_refused"] = {
            "errorText": error_text, "domValueAfter": value_3_after}
        print("[S05] error=%s valueAfter=%s"
              % (error_text, value_3_after), flush=True)

        # S06 履历回读（UI 按钮→cell_history）
        cdp.evaluate(js_click_cell_action("row-2:amount", "history"))
        time.sleep(4)
        history_text = cdp.evaluate(js_text('[data-testid="review-history"]'))
        readback["S06_history"] = {"dom": history_text}
        print("[S06] history=%s" % (history_text or "")[:120], flush=True)

        # S07 harness 独立对账（公开面 CLI 全量回读）
        ledger_receipts = harness_call("harness.review_receipt_read", {
            "scope": SCOPE, "batch_id": BATCH}, state_root)
        ledger_history = harness_call("harness.review_cell_history", {
            "scope": SCOPE, "batch_id": BATCH, "row_id": "row-2",
            "cell_id": "amount"}, state_root)
        readback["S07_ledger"] = {
            "receiptCounts": ledger_receipts.get("result", {}).get("counts"),
            "row2HistoryVersions": [
                {"generation": v.get("generation"), "value": v.get("value"),
                 "source": v.get("source")}
                for v in ledger_history.get("result", {}).get("versions", [])]}

        # 截图
        shot_dir = (REPO_ROOT / "docs/construction/evidence/F82/desktop")
        shot_dir.mkdir(parents=True, exist_ok=True)
        cdp.screenshot(str(shot_dir / "f82-review-surface-electron.png"))
        readback["screenshot"] = "f82-review-surface-electron.png"

        # 判定
        def ok(name: bool) -> str:
            return "PASS" if name else "FAIL"
        verdicts = {
            "S01_panel_rendered": ok(
                opened == "opened" and rendered is True and cell_count == 8
                and not not_connected and meta and BATCH in meta),
            "S02_receipt_ui_and_ledger": ok(
                status_attr == "REVIEWED_CONFIRMED"
                and readback["S02_receipt"]["ledger"]
                and readback["S02_receipt"]["ledger"][0][
                    "reviewStatus"] == "REVIEWED_CONFIRMED"),
            "S03_rerun_ui_and_ledger": ok(
                value_2 == "888,888.00 元" and gen_2 == "1"
                and state_2 == "pending"
                and readback["S03_rerun"]["ledgerCell"].get("generation") == 1
                and readback["S03_rerun"]["ledgerRowState"] == "pending"),
            "S04_human_edit_ui_and_ledger": ok(
                value_3 == "人改核正值 9 元" and source_3 == "human"
                and readback["S04_human_edit"]["ledgerCell"].get(
                    "source") == "human"),
            "S05_rerun_after_human_loud_refusal": ok(
                error_text and "review_rerun_human_cell" in error_text
                and value_3_after == "人改核正值 9 元"),
            "S06_history_readable": ok(
                history_text and "gen 0" in history_text
                and "gen 1" in history_text),
            "S07_ledger_independent_readback": ok(
                readback["S07_ledger"]["receiptCounts"] == {
                    "REVIEWED_CONFIRMED": 1, "REVIEWED_REJECTED": 0,
                    "NOT_REVIEWED": 7}
                and [v["generation"]
                     for v in readback["S07_ledger"]["row2HistoryVersions"]]
                == [0, 1]),
        }
        readback["verdicts"] = verdicts
        readback["overall"] = ("PASS" if all(
            v == "PASS" for v in verdicts.values()) else "FAIL")
        (shot_dir / "f82-review-ops-cdp-readback.json").write_text(
            json.dumps(readback, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print("CDP_%s %s" % (readback["overall"], verdicts), flush=True)
        return 0 if readback["overall"] == "PASS" else 1
    finally:
        if electron is not None:
            try:
                electron.kill()
            except Exception:
                pass
            subprocess.run(["taskkill", "/F", "/T", "/PID",
                            str(electron.pid)], capture_output=True)
        try:
            config_path.unlink()
            print("[cleanup] config removed", flush=True)
        except FileNotFoundError:
            pass
        temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
