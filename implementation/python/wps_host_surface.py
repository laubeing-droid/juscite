# -*- coding: utf-8 -*-
"""F17-wps 原生前端栈复用 WPS 宿主面（W2b-U50）：宿主内承载原生 UI，
不建第二 DOCX 编辑器。

义务 06:F17（17 卡；host=wps 实例）断言：「用户已冻结OpenCode原生UI服务
闭包…法律WordWPS编辑独立，不第二DOCX编辑器」。本面＝WPS 宿主侧 UI 承载
面：原生栈投影经 WPS COM 装配进**宿主自身的面板**（Application.CommandBars
临时停靠面板，宿主进程渲染；Temporary=True 会话级即弃，不留用户配置残
留）。真机探针钉定（WPS 12.1.0.28802）：Application.TaskPanes 8 项在
Visible=False 会话形态 Item 即 com_error（内置窗格不可承载自定义内容），
故落点＝面板（CommandBar）；JSAPI 加载项任务窗格需向用户 WPS 配置安装并
重启宿主＝违反会话纪律（不打扰用户现有任务，08§2 末段），具名边界不在
本面。

不第二 DOCX 编辑器（本面结构性保证，AST 可验）：
- 正文渲染/编辑一律宿主自身——本面**零编辑实现**：无 SaveAs/Accept/
  Reject/TypeText/Range 写操作；文档只读打开（Documents.Open ReadOnly）
  读宿主原生 Revisions 后即关（Close(False) 不落盘）；
- 产品侧只投影四类（闭集）：格值（support 状态=U05 tabular 投影闭集）/
  引用（gate 状态=F87 三态闭集）/修订清单（宿主 Revisions，U36 通道）/
  决定引用（U11 提案状态闭集 pending/accepted/rejected/superseded）；
- 闭集外值一律响亮具名拒（014 patch review-ops.ts 投影纪律同款：前端/
  面板不重算不重判，未知状态绝不静默渲染）。

消费已冻结通道（不建第二权威）：
- 会话纪律与修订枚举＝wps_host（W2b-U36 VERIFIED）同进程复用：同一把
  进程内全局锁（wps_host._LOCK——本面会话与 wpshost.review/decide 会话
  串行互斥，COM 限流不打扰用户现有任务）；DispatchEx KWPS.Application
  独立进程绝不附着用户已开窗口＋Visible=False＋finally 必 Quit。
- **附着已开窗口结构性不存在**：本面永不调 GetActiveObject；调用方以
  attach_running/attach_existing 之类参数表达附着意图＝f17wps_attach_
  refused 具名拒。

fail-closed：typed error（f17wps_* 错误码，绝不携材料内容）；未装 WPS
（ProgID 注册表探针缺失）＝f17wps_host_unavailable:no_wps；ProgID 在而
COM 派发拒＝f17wps_host_unavailable:dispatch_refused；pywin32 缺＝
f17wps_host_unavailable:pywin32_missing。面板四区全空＝f17wps_panel_
empty（不空转装配）。宿主回读 Caption 与投影逐条不等＝f17wps_surface_
readback_mismatch（宿主未忠实持有投影即响亮失败）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import uuid
import winreg
from contextlib import contextmanager
from pathlib import Path

import wps_host
from wps_host import WpsHostError

SCHEMA = "juscite-f17-wps-host-surface/1"
# 宿主原生面板（探针 12.1.0.28802 实测：Add/Controls.Add/Caption/回读全通）
BAR_NAME = "LvyinF17Surface"
BAR_POSITION = 4        # msoBarBottom 底部停靠面板
BAR_TEMPORARY = True    # 会话级即弃：宿主进程 Quit 即消失，零用户配置残留
_CONTROL_BUTTON = 1     # msoControlButton

# 投影闭集（014 patch review-ops.ts 投影层同集再声明；测试与源面钉定相等）
# 格值支持状态＝U05 tabular.read 投影闭集
SUPPORT_STATUSES = frozenset({
    "SUPPORTED_CITATION_LEVEL", "UNSUPPORTED_REJECTED",
    "STALE_CELL_ADVANCED", "INVALIDATED", "NO_STAMP",
})
# 决定引用状态＝U11 提案状态机闭集（05§8 提案版本合同）
DECISION_STATES = frozenset({
    "pending", "accepted", "rejected", "superseded",
})
# 引用核验状态＝F87 闸三态闭集（登记即 UNVERIFIED；本面不跑闸不代签）
CITATION_STATUSES = frozenset({
    "UNVERIFIED", "CITATION_VERIFIED", "REJECTED",
})
# 面板行类闭集
SECTION_KINDS = frozenset({"revision", "decision", "grid", "citation"})
# 附着已开窗口意图参数（封闭清单；出现即具名拒，绝不静默忽略）
_ATTACH_KEYS = ("attach_running", "attach_existing", "get_active_object")


class WpsSurfaceError(ValueError):
    """Typed WPS host surface failure; str() is a code, never material."""

    error_code = "f17wps_invalid"


def _fail(code: str) -> WpsSurfaceError:
    return WpsSurfaceError(code)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _progid_registered(progid: str) -> bool:
    """ProgID 注册表探针（HKCR 合并视图）——「WPS 未装」先于派发具名。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + r"\CLSID")
    except OSError:
        return False
    key.Close()
    return True


def _refuse_attach(args: dict) -> None:
    """附着已开窗口尝试＝具名拒（结构性永不 GetActiveObject）。"""
    for key in _ATTACH_KEYS:
        if args.get(key):
            raise _fail("f17wps_attach_refused:" + key)


def _decode_docx(args: dict) -> bytes:
    payload = args.get("docx_b64")
    if not isinstance(payload, str) or not payload:
        raise _fail("f17wps_docx_required")
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception:
        raise _fail("f17wps_docx_b64_invalid") from None
    if len(raw) < 4 or raw[:2] != b"PK":
        raise _fail("f17wps_docx_not_a_package")
    return raw


@contextmanager
def _surface_session(state_root: Path, tag: str, launch: dict | None = None):
    """WPS 宿主会话：沿用 U36 纪律，锁＝wps_host._LOCK 同一把全局锁。

    纪律：锁内进、锁内出（与 wpshost.review/decide 会话串行互斥——COM
    限流不打扰用户现有任务）；ProgID 注册表探针缺失＝no_wps 先名于派发；
    DispatchEx 独立进程（绝不附着用户窗口）；Visible=False＋DisplayAlerts=0；
    finally 必 Quit＋CoUninitialize。launch 仅限内部负向驱动（progid/
    clsctx 闭键），公开面恒用 KWPS.Application 正常派发。
    """
    launch = dict(launch or {})
    with wps_host._LOCK:
        progid = launch.get("progid", wps_host.PROGID)
        if not isinstance(progid, str) or not _progid_registered(progid):
            raise _fail("f17wps_host_unavailable:no_wps")
        try:
            pythoncom, client = wps_host._com_modules()
        except WpsHostError:
            raise _fail(
                "f17wps_host_unavailable:pywin32_missing") from None
        pythoncom.CoInitialize()
        try:
            kwargs = {}
            if launch.get("clsctx") is not None:
                kwargs["clsctx"] = launch["clsctx"]
            try:
                app = client.DispatchEx(progid, **kwargs)
            except Exception:
                raise _fail(
                    "f17wps_host_unavailable:dispatch_refused") from None
            work_dir = Path(state_root) / wps_host.STATE_SUBDIR / (
                "surface-" + tag)
            work_dir.mkdir(parents=True, exist_ok=True)
            try:
                app.Visible = False
                try:
                    app.DisplayAlerts = 0
                except Exception:
                    pass  # 旧版无此属性不致命（本面无落盘动作）
                yield app, work_dir
            finally:
                try:
                    app.Quit()
                except Exception:
                    pass
        finally:
            pythoncom.CoUninitialize()


# --------------------------------------------------------------------------
# 投影装配（纯函数；四类闭集校验，闭集外响亮拒）
# --------------------------------------------------------------------------

def _require_ref(item: dict, where: str) -> dict:
    ref = item.get("ref")
    if not isinstance(ref, dict):
        raise _fail("f17wps_ref_invalid:" + where)
    for field in ("owner", "kind", "id", "version"):
        value = ref.get(field)
        if not isinstance(value, str) or not value:
            raise _fail("f17wps_ref_invalid:" + where)
    return ref


def _validate_decisions(items) -> list:
    if not isinstance(items, list):
        raise _fail("f17wps_decisions_invalid")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise _fail("f17wps_decision_item_invalid")
        ref = _require_ref(item, "decision")
        state = item.get("state")
        if state not in DECISION_STATES:
            raise _fail("f17wps_decision_state_invalid:%s"
                        % str(state)[:40])
        out.append({"kind": "decision", "ref": ref, "state": state})
    return out


def _validate_grids(items) -> list:
    if not isinstance(items, list):
        raise _fail("f17wps_grids_invalid")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise _fail("f17wps_grid_item_invalid")
        ref = _require_ref(item, "grid")
        cell = item.get("cell")
        if not isinstance(cell, str) or not cell:
            raise _fail("f17wps_grid_cell_invalid")
        value = item.get("value")
        if not isinstance(value, str):
            raise _fail("f17wps_grid_value_invalid")
        support = item.get("support")
        if support not in SUPPORT_STATUSES:
            raise _fail("f17wps_grid_support_invalid:%s"
                        % str(support)[:40])
        out.append({"kind": "grid", "ref": ref, "cell": cell,
                    "value": value, "support": support})
    return out


def _validate_citations(items) -> list:
    if not isinstance(items, list):
        raise _fail("f17wps_citations_invalid")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise _fail("f17wps_citation_item_invalid")
        ref = _require_ref(item, "citation")
        quote = item.get("quote")
        if not isinstance(quote, str) or not quote:
            raise _fail("f17wps_citation_quote_invalid")
        status = item.get("status")
        if status not in CITATION_STATUSES:
            raise _fail("f17wps_citation_status_invalid:%s"
                        % str(status)[:40])
        out.append({"kind": "citation", "ref": ref, "quote": quote,
                    "status": status})
    return out


def _panel_lines(revisions: list, decisions: list, grids: list,
                 citations: list) -> list:
    """面板行＝四类投影的确定性拼装（同输入同序同文；不重算任何值）。"""
    lines = []
    for rev in revisions:
        lines.append({
            "kind": "revision",
            "caption": "[修订]%d·%s·%s·%s" % (
                rev["index"], rev["type_name"], rev["author"], rev["text"]),
        })
    for item in decisions:
        ref = item["ref"]
        lines.append({
            "kind": "decision",
            "caption": "[决定]%s·%s:%s:%s@v%s" % (
                item["state"], ref["owner"], ref["kind"], ref["id"],
                ref["version"]),
        })
    for item in grids:
        ref = item["ref"]
        lines.append({
            "kind": "grid",
            "caption": "[格值]%s=%s·支持=%s·%s:%s@v%s" % (
                item["cell"], item["value"], item["support"], ref["owner"],
                ref["id"], ref["version"]),
        })
    for item in citations:
        ref = item["ref"]
        lines.append({
            "kind": "citation",
            "caption": "[引用]%s·%s·%s:%s@v%s" % (
                item["status"], item["quote"], ref["owner"], ref["id"],
                ref["version"]),
        })
    return lines


def panel_sha256(lines: list) -> str:
    """面板载荷指纹（canonical JSON；不含宿主信息与时钟→跨会话/跨
    profile 确定性）。"""
    payload = json.dumps(lines, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return _sha256_bytes(payload.encode("utf-8"))


def _bar_readback(bar) -> list:
    return [str(bar.Controls.Item(index).Caption)
            for index in range(1, bar.Controls.Count + 1)]


# --------------------------------------------------------------------------
# 公开面两方法（legal_entry 冻结方法组 wpssurface.* 唯一入口）
# --------------------------------------------------------------------------

def surface_available(args: dict) -> dict:
    """环境探针＋承载面能力实测：真启动独立进程，建临时面板带回读即退。"""
    with _surface_session(tempfile.gettempdir(),
                          "probe-" + uuid.uuid4().hex[:8]) as (app, _work):
        probe_name = BAR_NAME + "Probe"
        probe_caption = "律引·承载面探针"
        bar = app.CommandBars.Add(probe_name, BAR_POSITION, False,
                                  BAR_TEMPORARY)
        control = bar.Controls.Add(_CONTROL_BUTTON)
        control.Caption = probe_caption
        bar.Visible = True
        readback_equal = _bar_readback(bar) == [probe_caption]
        try:
            bar.Delete()
        except Exception:
            pass  # Temporary 面板随宿主进程 Quit 即消失，删除失败不致命
        if not readback_equal:
            raise _fail("f17wps_carrier_probe_failed")
        return {
            "schema": SCHEMA,
            "installed": True,
            "host": wps_host._host_info(app),
            "carrier": {"kind": "commandbar", "bar": probe_name,
                        "position": BAR_POSITION, "temporary": BAR_TEMPORARY,
                        "probe_readback_equal": True},
        }


def surface_mount(state_root: Path, args: dict) -> dict:
    """装配投影→宿主原生面板承载→宿主回读核对（单会话；投影零编辑）。

    流程：闭集校验（COM 前，非法即具名拒）→ 会话内只读打开工作文档读
    宿主原生 Revisions（U36 通道同源枚举）→ 纯函数拼装面板行 → 宿主
    CommandBar 临时面板逐行承载 → 宿主回读 Caption 逐条核对（不等即
    f17wps_surface_readback_mismatch）→ 返回载荷指纹与四区计数。全程
    不产生任何文档写入：正文渲染/编辑一律宿主自身。
    """
    raw = _decode_docx(args)
    decisions = _validate_decisions(args.get("decision_items") or [])
    grids = _validate_grids(args.get("grid_items") or [])
    citations = _validate_citations(args.get("citation_items") or [])
    with _surface_session(Path(state_root),
                          "mount-" + uuid.uuid4().hex[:8]) as (app, work_dir):
        source = work_dir / "surface.docx"
        source.write_bytes(raw)
        doc = app.Documents.Open(str(source), False, True)  # 只读打开
        try:
            revisions = wps_host._enumerate_revisions(doc)
        finally:
            doc.Close(False)  # 不保存（Close(False)＝零落盘）
        lines = _panel_lines(revisions, decisions, grids, citations)
        if not lines:
            raise _fail("f17wps_panel_empty")
        bar = app.CommandBars.Add(BAR_NAME, BAR_POSITION, False,
                                  BAR_TEMPORARY)
        for line in lines:
            control = bar.Controls.Add(_CONTROL_BUTTON)
            control.Caption = line["caption"]
        bar.Visible = True
        if _bar_readback(bar) != [line["caption"] for line in lines]:
            raise _fail("f17wps_surface_readback_mismatch")
        sections = {kind: 0 for kind in SECTION_KINDS}
        for line in lines:
            sections[line["kind"]] += 1
        return {
            "schema": SCHEMA,
            "source_sha256": _sha256_bytes(raw),
            "revision_count": len(revisions),
            "sections": sections,
            "panel": {
                "bar": BAR_NAME, "position": BAR_POSITION,
                "temporary": BAR_TEMPORARY, "controls": len(lines),
                "lines": lines, "readback_equal": True,
                "panel_sha256": panel_sha256(lines),
            },
            "host": wps_host._host_info(app),
        }


def surface_call(method: str, args: dict, config: dict) -> dict:
    if not isinstance(args, dict):
        raise _fail("f17wps_params_invalid")
    _refuse_attach(args)
    if method == "wpssurface.available":
        return surface_available(args)
    state_root = config.get("wps_host_state_root")
    if not state_root:
        raise _fail("f17wps_state_root_not_configured")
    if method == "wpssurface.mount":
        return surface_mount(Path(state_root), args)
    raise _fail("f17wps_method_unknown")
