# -*- coding: utf-8 -*-
"""F46/F52 WPS 宿主自动化半边（W2b-U36）：通道② 产品侧 document-adapter
公开面——真 WPS COM 原生修订（不模拟 DOCX）。

义务 06:F46/F52（17 卡）：「公开 proposal/base refs→宿主原生定位/修订/
比对→部分接受/拒绝→重读实际文件→CAS/version→Harness 正式采用；不模拟
DOCX」＋「Word 与 WPS 真实接受后回读新 CAS/version，未接受不改 canonical」。
本面只做 WPS 半边（§6.1 裁决#4：WPS 先行 Word 后补，回收点 W2-S1/W4-S2，
F46-word/F52-word 保持 NOT_RUN 挂结转）。

通道与纪律（08§2 末段：WPS COM 限流不打扰用户现有任务）：
- 唯一宿主入口＝pywin32 win32com.client.DispatchEx("KWPS.Application")
  （独立进程实例，绝不附着用户已开的 WPS 窗口；实测钉定 WPS
  12.1.0.28802）。进程内全局锁串行化——同一时刻至多一个 COM 会话；
  每会话 Visible=False＋DisplayAlerts=0（杜绝隐形模态挂死），finally
  必 Quit；工作文件落显式状态根（TEMP/配置），绝不写 %APPDATA%\\JusBench。
- 宿主原生修订＝读宿主自己的 Revisions 集合（Type/Author/Date/Range.
  Text），不解析中间量冒充宿主；部分接受/拒绝＝Revision.Accept()/
  Reject() 逐条落真。WPS 修订集合随增删重排——**每动一条后必须重新
  枚举**（快照索引越位在 WPS COM 是挂死不是报错，实测钉定），动作循环
  以「无可再动」为终止条件＋guard 上限。
- 选择器（决定面）封闭：{type: insert|delete|properties|…, text_equals
  |text_contains}；按修订文本确定性匹配，绝不按漂移序号定位。选择器
  命中零修订→wps46_no_revision_matched 具名拒（决定面不得空转）。
- 重读实际文件：SaveAs2 显式 FileFormat=12（docx）到状态根新路径，
  回读**盘上真实字节**（result_docx_b64）——这就是 U11 合同
  formal_decide resultBytesB64 的宿主侧来源（source=user_accept、
  resultSource=host_result_bytes）。
- LibreOffice 只作渲染辅助核（U14 先例），不替代 WPS 主验证（不在本
  模块内，调用方自排）。

fail-closed：typed error（wps46_* 错误码，绝不携材料内容——Revision
文本只在正常响应载荷出现）。未装 pywin32/WPS＝wps46_host_unavailable
具名（不静默降级、不换引擎）。
"""
from __future__ import annotations

import base64
import hashlib
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

SCHEMA = "juscite-f46-wps-host/1"
PROGID = "KWPS.Application"
STATE_SUBDIR = "wps-host"
# Word/WPS 修订类型枚举（封闭映射；未列类型按 type_<n> 透传不猜语义）
REVISION_TYPE_NAMES = {
    1: "insert",
    2: "delete",
    3: "properties",
    4: "paragraph_number",
    5: "display_character",
    6: "reconcile",
    7: "conflict",
    8: "style",
    9: "replace",
    10: "paragraph_property",
    11: "table_property",
    12: "section_property",
    13: "style_definition",
    14: "moved_from",
    15: "moved_to",
}
# 选择器匹配模式闭集
SELECTOR_MODES = frozenset({"equals", "contains"})
# 动作循环守卫（修订条数上限的硬闸——防宿主状态异常时死循环）
_ACTION_GUARD = 10000

_LOCK = threading.Lock()


class WpsHostError(ValueError):
    """Typed WPS host face failure; str() is a code, never material."""

    error_code = "wps46_invalid"


def _fail(code: str) -> WpsHostError:
    return WpsHostError(code)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _decode_docx(args: dict) -> bytes:
    payload = args.get("docx_b64")
    if not isinstance(payload, str) or not payload:
        raise _fail("wps46_docx_required")
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception:
        raise _fail("wps46_docx_b64_invalid") from None
    if len(raw) < 4 or raw[:2] != b"PK":
        raise _fail("wps46_docx_not_a_package")
    return raw


def _validate_selectors(selectors, field: str) -> list:
    if not isinstance(selectors, list):
        raise _fail("wps46_selectors_invalid:" + field)
    seen = []
    for selector in selectors:
        if not isinstance(selector, dict):
            raise _fail("wps46_selector_invalid:" + field)
        mode = selector.get("mode", "equals")
        if mode not in SELECTOR_MODES:
            raise _fail("wps46_selector_mode_invalid:" + field)
        text = selector.get("text")
        if not isinstance(text, str) or not text:
            raise _fail("wps46_selector_text_invalid:" + field)
        rev_type = selector.get("type")
        if rev_type is not None:
            if not isinstance(rev_type, str) \
                    or rev_type not in set(REVISION_TYPE_NAMES.values()):
                raise _fail("wps46_selector_type_invalid:" + field)
        seen.append({"type": rev_type, "mode": mode, "text": text})
    return seen


def _match(selector: dict, rev_type_name: str, text: str) -> bool:
    if selector["type"] is not None and selector["type"] != rev_type_name:
        return False
    if selector["mode"] == "contains":
        return selector["text"] in text
    return text == selector["text"]


def _com_modules():
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        raise _fail("wps46_host_unavailable:pywin32_missing") from None
    return pythoncom, win32com.client


@contextmanager
def _wps_session(state_root: Path, tag: str):
    """单例串行 WPS COM 会话：独立 DispatchEx 进程，绝不附着用户窗口。

    纪律：锁内进、锁内出（同一时刻至多一个宿主自动化会话）；Visible=
    False＋DisplayAlerts=0；finally 必 Quit——任何异常都不留宿主进程。
    """
    with _LOCK:
        pythoncom, client = _com_modules()
        pythoncom.CoInitialize()
        try:
            app = client.DispatchEx(PROGID)
        except Exception:
            raise _fail("wps46_host_unavailable:dispatch_failed") from None
        work_dir = state_root / STATE_SUBDIR / ("session-" + tag)
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            app.Visible = False
            try:
                app.DisplayAlerts = 0
            except Exception:
                pass  # 旧版无此属性不致命（SaveAs2 显式格式兜底）
            try:
                yield app, work_dir
            finally:
                try:
                    app.Quit()
                except Exception:
                    pass
        finally:
            pythoncom.CoUninitialize()


def _host_info(app) -> dict:
    info = {"progid": PROGID}
    for attr in ("Version", "Build"):
        try:
            info[attr.lower()] = str(getattr(app, attr))
        except Exception:
            info[attr.lower()] = None
    return info


def _enumerate_revisions(doc) -> list:
    """宿主原生修订清单（每条即时取值，不缓存 COM 对象）。"""
    count = doc.Revisions.Count
    out = []
    for index in range(1, count + 1):
        revision = doc.Revisions.Item(index)
        rev_type = int(revision.Type)
        out.append({
            "index": index,
            "type": rev_type,
            "type_name": REVISION_TYPE_NAMES.get(rev_type,
                                                 "type_%d" % rev_type),
            "author": str(revision.Author),
            "date": str(revision.Date),
            "text": str(revision.Range.Text),
        })
    return out


# --------------------------------------------------------------------------
# 公开面三方法（legal_entry 冻结方法组 wpshost.* 唯一入口）
# --------------------------------------------------------------------------

def wps_available() -> dict:
    """环境探针：真启动一次 KWPS.Application 读版本即退。"""
    with _wps_session(Path(__import__("tempfile").gettempdir()),
                      "probe-" + uuid.uuid4().hex[:8]) as (app, _work):
        return {"schema": SCHEMA, "installed": True,
                "host": _host_info(app)}


def wps_review(state_root: Path, args: dict) -> dict:
    """宿主打开实际 DOCX→读宿主原生 Revisions 集合（含表/脚注面修订）。"""
    raw = _decode_docx(args)
    with _wps_session(Path(state_root),
                      "review-" + uuid.uuid4().hex[:8]) as (app, work_dir):
        source = work_dir / "review.docx"
        source.write_bytes(raw)
        doc = app.Documents.Open(str(source), False, True)
        try:
            revisions = _enumerate_revisions(doc)
            return {
                "schema": SCHEMA,
                "source_sha256": _sha256_bytes(raw),
                "revision_count": len(revisions),
                "revisions": revisions,
                "host": _host_info(app),
            }
        finally:
            doc.Close(False)


def wps_decide(state_root: Path, args: dict) -> dict:
    """宿主部分接受/拒绝→SaveAs2→重读盘上真实字节回流。

    选择器决定面：accept/reject 各为封闭选择器列表；逐轮重新枚举宿主
    修订集合（WPS 集合随增删重排，快照索引越位是挂死不是报错——实测
    钉定），命中即动，直到无可再动。两列表命中同一修订时 accept 先问。
    """
    raw = _decode_docx(args)
    accept = _validate_selectors(args.get("accept") or [], "accept")
    reject = _validate_selectors(args.get("reject") or [], "reject")
    if not accept and not reject:
        raise _fail("wps46_decide_empty")
    with _wps_session(Path(state_root),
                      "decide-" + uuid.uuid4().hex[:8]) as (app, work_dir):
        source = work_dir / "decide.docx"
        source.write_bytes(raw)
        doc = app.Documents.Open(str(source), False, False)
        try:
            acted_accept: list[str] = []
            acted_reject: list[str] = []
            guard = 0
            while True:
                guard += 1
                if guard > _ACTION_GUARD:
                    raise _fail("wps46_action_loop_guard")
                count = doc.Revisions.Count
                acted = False
                for index in range(1, count + 1):
                    revision = doc.Revisions.Item(index)
                    rev_type = int(revision.Type)
                    type_name = REVISION_TYPE_NAMES.get(
                        rev_type, "type_%d" % rev_type)
                    text = str(revision.Range.Text)
                    if any(_match(s, type_name, text) for s in accept):
                        revision.Accept()
                        acted_accept.append(text)
                        acted = True
                        break
                    if any(_match(s, type_name, text) for s in reject):
                        revision.Reject()
                        acted_reject.append(text)
                        acted = True
                        break
                if not acted:
                    break
            if not acted_accept and not acted_reject:
                raise _fail("wps46_no_revision_matched")
            out_path = work_dir / "result.docx"
            doc.SaveAs2(str(out_path), 12)  # 12 = wdFormatXMLDocument(.docx)
            doc.Close(False)
            result_raw = out_path.read_bytes()
            # 重载回流：同一宿主会话内再开实际结果文件核对修订状态
            doc2 = app.Documents.Open(str(out_path), False, True)
            try:
                remaining = _enumerate_revisions(doc2)
            finally:
                doc2.Close(False)
            return {
                "schema": SCHEMA,
                "source_sha256": _sha256_bytes(raw),
                "result_sha256": _sha256_bytes(result_raw),
                "result_docx_b64": base64.b64encode(result_raw)
                    .decode("ascii"),
                "acted_accept": acted_accept,
                "acted_reject": acted_reject,
                "remaining_count": len(remaining),
                "remaining_revisions": remaining,
                "host": _host_info(app),
            }
        except WpsHostError:
            raise
        except Exception as exc:
            raise _fail("wps46_host_failed:" + type(exc).__name__) from None


def wps_host_call(method: str, args: dict, config: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("wps46_params_invalid")
    if method == "wpshost.available":
        return wps_available()
    state_root = config.get("wps_host_state_root")
    if not state_root:
        raise _fail("wps46_state_root_not_configured")
    if method == "wpshost.review":
        return wps_review(Path(state_root), args)
    if method == "wpshost.decide":
        return wps_decide(Path(state_root), args)
    raise _fail("wps46_method_unknown")
