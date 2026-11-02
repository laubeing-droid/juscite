# -*- coding: utf-8 -*-
"""F17-wps 原生前端栈复用 WPS 宿主面 recon（W2b-U50）——宿主内承载原生
UI，不建第二 DOCX 编辑器。

对账对象：产品侧 implementation/python/wps_host_surface.py（legal_entry
冻结方法组 wpssurface.*：available/mount）＋消费链＝
- U36 已 VERIFIED 的 wpshost.* 三方法通道（legal_entry.py WPS_HOST_METHODS：
  available/review/decide）——修订清单真通道消费：面板修订区与
  wpshost.review 同文档输出逐条对账；
- U31 patch 014 原生投影纪律——四类闭集（格值=U05 支持状态/引用=F87
  三态/决定引用=U11 提案状态/修订清单=宿主 Revisions）＋闭集外响亮拒
  ＋投影不重算；
- U14 redline 产物（消费契约 REDLINE_CONSUMERS）——工作文档经产品红线
  面产真修订红线 DOCX（承载面投影宿主所见）。

落点（真机探针钉定 WPS 12.1.0.28802）：WPS 宿主侧 UI 承载面＝Application.
CommandBars 临时停靠面板（宿主进程渲染；Temporary=True 会话级即弃，零用
户配置残留）；Application.TaskPanes 8 项在 Visible=False 会话形态 Item 即
com_error（内置窗格不可承载自定义内容）如实入账；JSAPI 加载项任务窗格需
向用户 WPS 配置安装并重启宿主＝违反会话纪律（08§2 末段：COM 限流不打扰
用户现有任务），具名边界不在本面。

硬红线（全检断言）：宿主会话纪律沿用 U36（DispatchEx KWPS.Application
独立进程绝不附着用户已开窗口＋同一把进程内全局锁 wps_host._LOCK 串行＋
Visible=False＋finally 必 Quit）；不第二 DOCX 编辑器＝正文渲染/编辑一律
宿主自身，产品侧只投影、零独立编辑实现（AST 断言＋红线产物字节不变）；
附着已开窗口尝试＝f17wps_attach_refused 具名拒；WPS 未装（注册表探针）＝
f17wps_host_unavailable:no_wps；COM 派发拒＝f17wps_host_unavailable:
dispatch_refused。

实跑覆盖（每 profile 一轮全链，无参默认双 profile）：
  C01 桥冻结面（方法组闭集＋attach 方法 not_connected＋未配置状态根具名拒）
  → C02 具名负向·无宿主（附着×3/坏载荷×3/闭集外×4 全具名拒，COM 零启动）
  → C03 宿主探针＋承载面能力实测（available：临时面板建→回读→即退）
  → C04 U14 红线产物消费契约（register/replay/compare＋b64 取件双 sha
     复验＋对账双不变式＋consumers 含 W2b-U16-wps-host）
  → C05 通道消费对账（wpshost.review 同文档输出＝面板修订区逐条拼装源）
  → C06 装配·承载·回读（四区投影入宿主 CommandBar 面板；宿主回读
     Caption 逐条相等；sections 闭集计数；source_sha256 相等）
  → C07 确定性＋空面板拒（跨会话同输入同 panel_sha256；干净文档零投影
     ＝f17wps_panel_empty 具名拒不空转装配）
  → C08 宿主负向真拒（未装＝ProgID 注册表探针缺失 no_wps；COM 拒＝
     CLSCTX_INPROC_SERVER 真派发拒绝 dispatch_refused）
  → C09 零编辑字节断言（mount 前后红线产物逐字节不变＋状态根新增仅限
     会话工作目录＋模块 AST 无 SaveAs/Accept/Reject/TypeText/
     GetActiveObject）
  → C10 跨 profile 面板载荷逐字节相等（profile 无关性：末位 profile
     携带，与首位 panel_sha256 相等）

用法：
  python -X utf8 tools/recon/PENDING_OWNER_f17_wps_host_surface_recon.py \
      [--profile desktop] [--profile selfhost]

退出码：0 = 全部 profile RECON_OK；2 = RECON_FAIL；3 = 环境缺失
（WPS/pywin32 任一缺失＝3）。证据：docs/construction/evidence/F17/wps/
JSON＋MD（末位 profile 另写无后缀主档）。
"""
from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
import document_redline as dr  # noqa: E402
import wps_host  # noqa: E402
import wps_host_surface as surface  # noqa: E402
from citation_verifier import parse_citations  # noqa: E402

SEED_MARKER = "W2b-U50"
MATTER = "m-f17wps-recon"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS

CITE_SENTENCE = "本段引用《合成数据安全法》第三条作为合成引文锚。"
BODY_P0 = "U50 合成正文首段：红线提案替换对象。"
BODY_P1 = "U50 合成正文第二段：与提案无涉。"
P0_NEW = "U50 红线接受组新文：宿主面板修订区投影此修订。"

AUTHOR = "lvyin-redline"
DATE = "2026-10-17T00:00:00Z"


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------
# 全合成语料（干净基版：U14 红线闸要求无既有修订标记）
# --------------------------------------------------------------------------

def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def build_baseline_docx() -> bytes:
    """全合成干净基版 DOCX（确定性：无时钟无随机，同输入字节级同输出）。"""
    body = [
        f"<w:p><w:r><w:t>{_esc(CITE_SENTENCE)}</w:t></w:r></w:p>",
        f"<w:p><w:r><w:t>{_esc(BODY_P0)}</w:t></w:r></w:p>",
        f"<w:p><w:r><w:t>{_esc(BODY_P1)}</w:t></w:r></w:p>",
        "<w:p><w:r><w:t>U50 合成表格行。</w:t></w:r></w:p>",
    ]
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:document xmlns:w="{W_NS}"><w:body>'
        + "".join(body) + "</w:body></w:document>")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types">'
        '<Default Extension="rels" ContentType="application/vnd.'
        'openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document'
        '.main+xml"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/></Relationships>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in (("[Content_Types].xml", content_types),
                              ("_rels/.rels", rels),
                              ("word/document.xml", document)):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload.encode("utf-8"))
    return buffer.getvalue()


def plain_text(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    out = []
    for el in root.iter(W + "t"):
        out.append(el.text or "")
    return "".join(out)


# --------------------------------------------------------------------------
# Recon 驱动
# --------------------------------------------------------------------------

class Recon:
    def __init__(self, state_root: Path, profile: str, shared: dict):
        self.state_root = state_root
        self.profile = profile
        self.shared = shared  # {profile: panel_sha256} 跨 profile 对比
        self.product_config = {"wps_host_state_root": str(state_root)}
        self.checks: list[dict] = []

    def step(self, name, ok, **facts):
        entry = {"check": name, "profile": self.profile,
                 "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part,
                     error=(NotConnected, surface.WpsSurfaceError)):
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc))
            return str(exc)
        raise AssertionError(name + ": no typed error raised")

    # -- 调用面 ------------------------------------------------------------
    def bridge(self, method: str, args: dict) -> dict:
        return legal_entry.call(method, args, self.product_config)

    def redline(self, method: str, args: dict) -> dict:
        return dr.redline_call(method, args, {"redline_state_root": str(
            self.state_root / "redline")})

    def _tree_snapshot(self, root: Path) -> dict:
        out = {}
        for path in sorted(root.rglob("*")):
            if path.is_file():
                out[str(path.relative_to(root))] = sha256_bytes(
                    path.read_bytes())
        return out

    # ------------------------------------------------------------------
    def flow(self):
        # ---- C01 桥冻结面
        self.step(
            "c01_bridge_method_group_frozen",
            legal_entry.WPS_SURFACE_METHODS == frozenset({
                "wpssurface.available", "wpssurface.mount"})
            and legal_entry.WPS_HOST_METHODS == frozenset({
                "wpshost.available", "wpshost.review", "wpshost.decide"}))
        self.expect_error(
            "c01_attach_method_not_connected",
            lambda: self.bridge("wpssurface.attach", {}),
            "method_not_connected:wpssurface.attach")
        self.expect_error(
            "c01_unconfigured_state_root_named",
            lambda: legal_entry.call("wpssurface.mount",
                                     {"docx_b64": b64(b"PK\x03\x04")}, {}),
            "f17wps_state_root_not_configured")

        # ---- C02 具名负向·无宿主（COM 零启动）
        payload = b64(build_baseline_docx())
        for key in ("attach_running", "attach_existing", "get_active_object"):
            self.expect_error(
                "c02_attach_refused_" + key,
                lambda key=key: self.bridge(
                    "wpssurface.mount", {"docx_b64": payload, key: True}),
                "f17wps_attach_refused:" + key)
        for label, args, code in (
                ("missing", {"decision_items": []}, "f17wps_docx_required"),
                ("corrupt", {"docx_b64": "not-base64!!"},
                 "f17wps_docx_b64_invalid"),
                ("notpkg", {"docx_b64": b64(b"JUNKFILE")},
                 "f17wps_docx_not_a_package")):
            self.expect_error(
                "c02_bad_payload_" + label,
                lambda args=args: self.bridge("wpssurface.mount", args),
                code)
        ref = {"owner": "harness", "kind": "proposal", "id": "fp-1",
               "version": "1"}
        for label, extra, code in (
                ("decision_state", {"decision_items": [
                    {"ref": ref, "state": "approved"}]},
                 "f17wps_decision_state_invalid:approved"),
                ("grid_support", {"grid_items": [
                    {"ref": ref, "cell": "[1,2]", "value": "1",
                     "support": "VERIFIED"}]},
                 "f17wps_grid_support_invalid:VERIFIED"),
                ("citation_status", {"citation_items": [
                    {"ref": ref, "quote": "引文", "status": "VERIFIED"}]},
                 "f17wps_citation_status_invalid:VERIFIED"),
                ("ref_short", {"decision_items": [
                    {"ref": {"owner": "harness", "kind": "proposal"},
                     "state": "pending"}]},
                 "f17wps_ref_invalid:decision")):
            self.expect_error(
                "c02_closed_set_" + label,
                lambda extra=extra: self.bridge(
                    "wpssurface.mount", dict({"docx_b64": payload}, **extra)),
                code)

        # ---- C03 宿主探针＋承载面能力实测
        probe = self.bridge("wpssurface.available", {})
        self.step(
            "c03_surface_available_carrier_probe",
            probe.get("installed") is True
            and probe["host"]["version"] is not None
            and probe["carrier"]["kind"] == "commandbar"
            and probe["carrier"]["temporary"] is True
            and probe["carrier"]["probe_readback_equal"] is True,
            host=probe.get("host"), carrier=probe.get("carrier"))

        # ---- C04 U14 红线产物消费契约
        baseline = build_baseline_docx()
        reg = self.redline("redline.register", {
            "document_id": "d-u50", "docx_b64": b64(baseline),
            "matter_id": MATTER})
        rep = self.redline("redline.replay", {
            "document_id": "d-u50",
            "proposal": {"ops": [{"op": "body.replace_text", "index": 1,
                                  "text": P0_NEW}],
                         "author": AUTHOR, "authored_utc": DATE}})
        cmp = self.redline("redline.compare", {
            "document_id": "d-u50", "proposal_id": rep["proposal_id"]})
        fetched = self.redline("redline.redline", {
            "redline_id": cmp["redline_id"]})
        redline_bytes = base64.b64decode(fetched["docx_b64"])
        self.step(
            "c04_redline_product_contract",
            fetched["sha256"] == cmp["redline"]["sha256"]
            and sha256_bytes(redline_bytes) == fetched["sha256"]
            and cmp["reconciliation"] == {
                "accept_all_equals_replay": True,
                "reject_all_equals_baseline": True,
                "readback_content_complete": True}
            and "W2b-U16-wps-host" in fetched["consumers"]
            and reg["baseline"]["sha256"] == sha256_bytes(baseline),
            redline_id=cmp["redline_id"], sha256=fetched["sha256"][:16])

        # ---- C05 通道消费对账（wpshost.review＝修订区唯一拼装源）
        review = self.bridge("wpshost.review", {
            "docx_b64": b64(redline_bytes)})
        expected_revision_captions = [
            "[修订]%d·%s·%s·%s" % (rev["index"], rev["type_name"],
                                   rev["author"], rev["text"])
            for rev in review["revisions"]]
        self.step(
            "c05_channel_crosscheck_review",
            review["revision_count"] > 0
            and all(rev["author"] == AUTHOR
                    for rev in review["revisions"]),
            host_count=review["revision_count"])

        # ---- C06 装配·承载·回读（四区投影）
        citations_parsed = parse_citations(plain_text(baseline))
        citation_items = [{
            "ref": {"owner": "juscite", "kind": "citation",
                    "id": "cit-u50-%d" % index, "version": "1"},
            "quote": item["citation_text"],
            "status": "UNVERIFIED",  # F87：登记即 UNVERIFIED；闸不在本面跑
        } for index, item in enumerate(citations_parsed, 1)]
        mount_args = {
            "docx_b64": b64(redline_bytes),
            "decision_items": [
                {"ref": {"owner": "harness", "kind": "proposal",
                         "id": "fp-u50", "version": "1"},
                 "state": "pending"}],
            "grid_items": [
                {"ref": {"owner": "harness", "kind": "cell", "id": "c-1-2",
                         "version": "1"},
                 "cell": "[1,2]", "value": "1,234,567.89",
                 "support": "NO_STAMP"}],
            "citation_items": citation_items,
        }
        snapshot_before = self._tree_snapshot(self.state_root)
        out = self.bridge("wpssurface.mount", mount_args)
        revision_captions = [line["caption"]
                             for line in out["panel"]["lines"]
                             if line["kind"] == "revision"]
        self.step(
            "c06_mount_projection_readback",
            out["panel"]["readback_equal"] is True
            and out["source_sha256"] == sha256_bytes(redline_bytes)
            and revision_captions == expected_revision_captions
            and out["sections"] == {
                "revision": review["revision_count"], "decision": 1,
                "grid": 1, "citation": len(citation_items)}
            and out["panel"]["temporary"] is True,
            controls=out["panel"]["controls"],
            sections=out["sections"],
            panel_sha256=out["panel"]["panel_sha256"][:16],
            citations_parsed=len(citations_parsed))

        # ---- C07 确定性＋空面板拒
        again = self.bridge("wpssurface.mount", mount_args)
        self.step(
            "c07_panel_deterministic_across_sessions",
            again["panel"]["panel_sha256"]
            == out["panel"]["panel_sha256"],
            panel_sha256=out["panel"]["panel_sha256"][:16])
        self.shared[self.profile] = out["panel"]["panel_sha256"]
        clean_args = {"docx_b64": b64(baseline)}
        self.expect_error(
            "c07_empty_panel_named_refusal",
            lambda: self.bridge("wpssurface.mount", clean_args),
            "f17wps_panel_empty")

        # ---- C08 宿主负向真拒（未装/COM 拒）
        self.expect_error(
            "c08_no_wps_named_real_registry",
            lambda: _run_no_wps_negative(self.state_root),
            "f17wps_host_unavailable:no_wps")
        self.expect_error(
            "c08_dispatch_refused_real_com",
            lambda: _run_dispatch_refused_negative(self.state_root),
            "f17wps_host_unavailable:dispatch_refused")

        # ---- C09 零编辑字节断言（不第二 DOCX 编辑器）
        snapshot_after = self._tree_snapshot(self.state_root)
        new_files = set(snapshot_after) - set(snapshot_before)
        session_prefix = os.sep.join(("wps-host", "surface-mount-"))
        non_session_new = {
            key for key in new_files
            if not key.startswith(session_prefix)}
        source = (REPO_ROOT / "implementation" / "python"
                  / "wps_host_surface.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"SaveAs", "SaveAs2", "Accept", "Reject", "TypeText",
                     "GetActiveObject"}
        ast_hits = [
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in forbidden]
        redline_store_after = {
            key: value for key, value in snapshot_after.items()
            if key.startswith("redline")}
        redline_store_before = {
            key: value for key, value in snapshot_before.items()
            if key.startswith("redline")}
        self.step(
            "c09_zero_edit_byte_assertion",
            non_session_new == set()
            and redline_store_after == redline_store_before
            and ast_hits == [],
            new_non_session_files=sorted(non_session_new)[:5],
            ast_hits=ast_hits,
            redline_store_files=len(redline_store_after))

    # -- 跨 profile（末位 profile 携带） -----------------------------------
    def cross_profile(self, profiles_run: list):
        if self.profile != profiles_run[-1] or len(profiles_run) < 2:
            return
        first_sha = self.shared.get(profiles_run[0])
        self.step(
            "c10_cross_profile_payload_equal",
            first_sha is not None
            and self.shared.get(self.profile) == first_sha,
            first_profile=profiles_run[0],
            panel_sha256=(first_sha or "")[:16])


def _run_no_wps_negative(state_root: Path) -> None:
    """真注册表负向：未装 ProgID → no_wps 具名拒（注册表查询真跑；
    KWPS.Application 在装作对照——拒因是探针缺失而非派发）。"""
    assert not surface._progid_registered("KWPS.NotInstalled.Application")
    assert surface._progid_registered(wps_host.PROGID)
    with surface._surface_session(
            state_root, "neg",
            launch={"progid": "KWPS.NotInstalled.Application"}):
        pass  # 不可达：会话入口必抛 no_wps（expect_error 由异常驱动）


def _run_dispatch_refused_negative(state_root: Path) -> None:
    """真 COM 拒：已注册 ProgID 在仅进程内类上下文下派发必拒（KWPS 为
    本地服务器，无进程内类——真 COM 拒绝非模拟；零网络零宿主启动）。"""
    import pythoncom
    with surface._surface_session(
            state_root, "neg",
            launch={"clsctx": pythoncom.CLSCTX_INPROC_SERVER}):
        pass  # 不可达：DispatchEx 必拒 → dispatch_refused


# --------------------------------------------------------------------------
# profile 驱动
# --------------------------------------------------------------------------

os_sep = "\\"


def run_profile(profile: str, shared: dict, profiles_run: list) -> tuple:
    temporary = tempfile.TemporaryDirectory(prefix="juscite-u50-" + profile)
    state_root = Path(temporary.name) / "state"
    state_root.mkdir(parents=True)
    recon = Recon(state_root, profile, shared)
    try:
        print(f"[profile {profile}] "
              + ("legal_entry bridge isolated state root"
                 if profile == "desktop" else
                 "surface public face direct (state root isolated)"),
              flush=True)
        recon.flow()
        recon.cross_profile(profiles_run)
        return recon, 0
    except Exception as error:  # noqa: BLE001 - keep partial checks
        print(f"RECON_FAIL[{profile}]: {error}", flush=True)
        recon.checks.append({"check": "recon_driver", "profile": profile,
                             "status": "FAIL", "error": str(error)[:400]})
        return recon, 2
    finally:
        # 检查已记录后再清理临时根（证据在 checks 里，文件不留）
        with contextlib.suppress(Exception):
            temporary.cleanup()


def write_evidence(recon: Recon, started: str, code: int,
                   profiles_run: list) -> list[Path]:
    out = []
    finished = datetime.now(timezone.utc).isoformat()
    evidence_dir = REPO_ROOT / "docs" / "construction" / "evidence" / "F17" \
        / "wps"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "juscite-f17-wps-host-surface-recon/1",
        "unit": "W2b-U50", "feature": "F17", "host": "wps",
        "profile": recon.profile, "profiles_run": profiles_run,
        "verdict": "RECON_OK" if code == 0 else "RECON_FAIL",
        "started_at": started, "finished_at": finished,
        "carrier": "Application.CommandBars temporary docked panel "
                   "(host-rendered; Temporary=True session-scoped); "
                   "Application.TaskPanes builtin panes not content-"
                   "hostable in headless session (Item com_error, probed "
                   "12.1.0.28802); JSAPI addin taskpane = named boundary "
                   "(requires user-config install + host restart, "
                   "violates session discipline 08 s2)",
        "no_second_docx_editor": "host renders/edits body; product "
                                 "projects four closed sections only "
                                 "(grid/citation/revision/decision); zero "
                                 "edit implementation (AST-asserted + "
                                 "byte-identical redline store)",
        "session_discipline": "U36 reuse: DispatchEx KWPS.Application "
                              "independent process (never attach to user "
                              "windows; GetActiveObject structurally "
                              "absent + attach args named-refused) + "
                              "shared wps_host._LOCK serial + Visible="
                              "False + finally Quit",
        "word_side": "NOT_RUN (kept for W2-S1/W4-S2 per ruling #4; "
                     "F17-word stays NOT_RUN)",
        "checks": recon.checks,
        "check_count": len(recon.checks),
        "failed": [c["check"] for c in recon.checks
                   if c["status"] != "PASS"],
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=1)
    stem = "f17_wps_host_surface_recon"
    (evidence_dir / f"{stem}.{recon.profile}.json").write_text(
        payload + "\n", encoding="utf-8")
    if recon.profile == profiles_run[-1]:
        (evidence_dir / f"{stem}.json").write_text(
            payload + "\n", encoding="utf-8")
    lines = [f"# F17 WPS 宿主承载面 recon（wps·{recon.profile}）", "",
             f"- unit: W2b-U50 · feature: F17 · host: wps"
             f" · profile: {recon.profile}",
             f"- verdict: **{summary['verdict']}**"
             f" ({len(recon.checks)} checks, exit {code})",
             f"- 承载面：宿主原生 CommandBar 临时面板（宿主渲染；Temporary"
             f" 会话级即弃）；TaskPanes 内置窗格本会话形态不可承载（探针实"
             f"测 com_error）；JSAPI 加载项＝具名边界（需装用户配置＋重启宿"
             f"主，违反 08§2 会话纪律）",
             "- 不第二 DOCX 编辑器：正文渲染/编辑一律宿主自身；产品侧只投"
             "影四类闭集；零编辑实现（AST＋红线产物字节不变双断言）",
             "- 会话纪律沿用 U36：DispatchEx 独立进程绝不附着用户窗口＋同"
             "一把进程内全局锁串行＋Visible=False＋finally 必 Quit；附着尝"
             "试 f17wps_attach_refused 具名拒",
             f"- Word 半边：NOT_RUN（§6.1 裁决#4，回收点 W2-S1/W4-S2；"
             f"F17-word 维持 NOT_RUN）",
             f"- profiles: {', '.join(profiles_run)}",
             f"- started: {started} · finished: {finished}",
             "",
             "| # | check | status |",
             "|---|---|---|"]
    for index, check in enumerate(recon.checks, 1):
        lines.append(f"| {index} | {check['check']} | {check['status']} |")
    lines += ["", "全部合成材料；真 WPS COM 会话（KWPS.Application 独立进"
                  "程·串行限流·用毕即退）。"]
    (evidence_dir / f"{stem}.{recon.profile}.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    if recon.profile == profiles_run[-1]:
        (evidence_dir / f"{stem}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
    out.append(evidence_dir)
    return out


PROFILES = ["desktop", "selfhost"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"])
    args = parser.parse_args()
    profiles = args.profile or list(PROFILES)
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except ImportError:
        print("RECON_BLOCKED: pywin32 missing (WPS host face unavailable)")
        return 3
    probe = wps_host.wps_available()
    if not probe.get("installed"):
        print("RECON_BLOCKED: KWPS.Application unavailable")
        return 3
    print("[host] WPS probe:", json.dumps(probe, ensure_ascii=False),
          flush=True)
    failures = 0
    shared: dict = {}
    for profile in profiles:
        started = datetime.now(timezone.utc).isoformat()
        recon, code = run_profile(profile, shared, profiles)
        evidence_dirs = write_evidence(recon, started, code, profiles)
        verdict = "RECON_OK" if code == 0 else "RECON_FAIL"
        print(f"[{profile}] {verdict} ({len(recon.checks)} checks,"
              f" exit {code}) evidence={[str(p) for p in evidence_dirs]}",
              flush=True)
        if code != 0:
            failures += 1
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
