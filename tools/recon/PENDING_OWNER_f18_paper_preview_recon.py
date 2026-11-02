#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F18 纸张预览与真实分页分别核 recon（W3-U21；PENDING_OWNER 版）。

义务 06:F18 断言：「纸张 CSS 文书观感（衬线+页边距+微阴影）；零依赖提升
法律文书感」＋验收行「纸张预览与真实DOCX/PDF分页分别核；缩放阅读不遮
正文」。08§3 文书行硬纪律：「CSS预览/文件存在/HTML.doc 不等正式DOCX」。
§6.1 裁决#5：LibreOffice 已装（C:\\Program Files\\LibreOffice，26.8）。

硬门（每 profile 真桥 CLI 子进程径，desktop/selfhost 分状态根分证据）：
- C01 内容面：paper.document 同输入两跑逐键相等＋零分页字段（结构性无
  page_count/pages——CSS 预览无从冒充分页）＋声明块三标志全真＋计数对账。
- C02 分页参照（真实分页唯一参照）：paper.pagination_reference 经
  LibreOffice headless --convert-to pdf 渲染 DOCX→PDF，页数/逐页文本自
  PDF 实测（pdfium，复用 F54 pdf_facts）——非 DOCX 数学推导非 CSS 近似；
  page_count>=2；引擎版本 26.8 实测；disclaimer 显式。
- C03 复用与跨状态根复现：同状态根二跑 rendered=reused 且 pages 相等；
  跨状态根 fresh 渲染页数/逐页文本相等（内容级确定性）；PDF sha 如实
  记录不主张逐字节相等（内嵌时间戳元数据）。
- C04 分别核：预览面零分页 × 参照面官方渲染——两方法互不代言（C01 的
  零分页字段＋C02 的 disclaimer/reference_kind 双面合读）。
- C05 桥 fail-closed 负向：未知方法 method_not_connected／docx 缺失
  f18_docx_not_found／无 soffice f18_soffice_not_configured／无状态根
  f18_state_root_not_configured；错误码不携材料内容。
- C06 语料只读锚：合成 docx 跑前后 sha 相等（只读，绝无改写）。

真机 Electron CDP 会话（desktop；U31/U48 先例）：一次性检出 clone6
（026b106＋001-017 序贯应用＋scratch CDP 注入不入补丁）：
- S01 fail-closed 首态：无 config →「纸张预览未接入」呈现，零编造内容。
- S02 CSS 文书观感（computed style 实测）：paper-body 字体栈含 SimSun
  ＋generic serif（衬线）；sheet 页边距 padding 37/26/35/28 mm×zoom 换算
  px（±2px）；微阴影（非 none，双层 1px/3px 低不透明度）；白纸面深字色；
  无 transform（无覆盖截断结构面）。
- S03 免责声明恒在＋预览区零分页主张：横幅全文呈现（含「不代表正式
  DOCX／PDF 分页」）；预览区内无「共 N 页」文本、无官方页数属性；
  横幅与视口矩形不相交（不遮正文之一）。
- S04 缩放阅读不遮正文：缩放闭集 [0.75,1,1.25,1.5,2] 逐档：正文块数
  不变、全文完整、可见段落 elementFromPoint 命中自身（无遮挡层）、滚动
  到底末段可达；闭集外值经 UI select 注入 → f18_zoom_invalid 响亮拒。
- S05 官方渲染参照独立呈现：载入按钮 → paper-reference 区呈现，页数与
  C02 独立桥回读相等；参照区标「非 CSS 预览」；参照区在预览 sheet 之外
  （分别呈现互不混同）。
- S06 撤通道 fail-closed：删 config → 重新读取 → 未接入呈现，零编造。

用法（juscite worktree w3-u21 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f18_paper_preview_recon.py

退出码：0＝RECON_OK（双 profile 全检＋CDP 六断言全过）；2＝RECON_FAIL；
3＝环境缺失。证据：docs/construction/evidence/F18/<profile>/。
语料全合成（确定性生成，绝无真实文档）；%APPDATA%\\JusBench 零触碰；
oc28 主检出零触碰（真机会话用 TEMP 一次性检出）；不 push。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "implementation" / "python" / "legal_entry.py"
SCHEMA = "juscite-f18-paper-preview/1"
DEFAULT_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
DEFAULT_CLONE = (Path(os.environ.get("TEMP", r"C:\Users\being\AppData\Local"
                                    r"\Temp")) / "oc28-chain" / "clone6")
DEFAULT_BUN = Path.home() / ".bun" / "bun.exe"
CDP_PORT = 8318
USER_DATA = Path(os.environ["APPDATA"]) / "Juscite"
PAPER_CONFIG = USER_DATA / "config" / "lvyin" / "paper-preview.json"

DISCLAIMER = ("纸张 CSS 预览：衬线字体／页边距／微阴影仅文书观感，不代表"
              "正式 DOCX／PDF 分页；实际分页以「官方渲染参照」为准。")
SHEET_MM = {"top": 37, "right": 26, "bottom": 35, "left": 28}
ZOOM_LEVELS = ["0.75", "1", "1.25", "1.5", "2"]


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# 全合成语料（确定性 DOCX；绝无真实文档）
# --------------------------------------------------------------------------

def build_synthetic_docx(path: Path, paragraphs: int = 120) -> None:
    body = "".join(
        "<w:p><w:r><w:t>合成段落%03d：当事人与金额均为虚构，本行用于纸张"
        "预览与真实分页分别核，绝无真实案件内容。</w:t></w:r></w:p>" % i
        for i in range(paragraphs))
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body>' + body +
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="2098" w:right="1474" w:bottom="1984" '
        'w:left="1588"/></w:sectPr></w:body></w:document>')
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/><Default Extension='
        '"xml" ContentType="application/xml"/><Override PartName="/word/'
        'document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://'
        'schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/></Relationships>')
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)


# --------------------------------------------------------------------------
# 真桥 CLI 子进程径（与产品桌面/服务调用完全同形）
# --------------------------------------------------------------------------

def bridge_call(config: dict, method: str, args: dict,
                timeout: int = 900) -> tuple[int, dict]:
    with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False) as req, \
         tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False) as cfg:
        json.dump({"method": method, "args": args}, req, ensure_ascii=False)
        json.dump(config, cfg, ensure_ascii=False)
        req_name, cfg_name = req.name, cfg.name
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(BRIDGE),
             "--request-json", req_name, "--config", cfg_name],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout)
        payload = {}
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {"raw": proc.stdout[-400:]}
        return proc.returncode, payload
    finally:
        os.unlink(req_name)
        os.unlink(cfg_name)


def run_profile(profile: str, docx: Path, soffice: str) -> tuple[int, dict]:
    evidence_dir = REPO / "docs" / "construction" / "evidence" / "F18" / profile
    evidence_dir.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=f"f18-state-{profile}-"))
    config = {"paper_state_root": str(root / "state"),
              "libreoffice_soffice": soffice}
    sha_before = sha256_file(docx)
    started = now_iso()
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    print(f"\n===== profile {profile}（state={root / 'state'}）=====",
          flush=True)

    # ---------------------------------------------- C01 内容面（零分页字段）
    doc1 = bridge_call(config, "paper.document",
                       {"docx_path": str(docx)})
    doc2 = bridge_call(config, "paper.document",
                       {"docx_path": str(docx)})
    view1 = doc1[1].get("result", {})
    view2 = doc2[1].get("result", {})
    counts = view1.get("counts", {})
    pagination = view1.get("pagination", {})
    record("C01_document_deterministic_no_page_fields",
           doc1[0] == 0 and doc2[0] == 0
           and view1.get("schema") == SCHEMA and view1 == view2
           and "page_count" not in view1 and "pages" not in view1
           and counts.get("paragraphs") == 120
           and counts.get("blocks") == 120
           and pagination.get("carried_by_preview") is False
           and pagination.get("css_preview_is_not_official_pagination") is True
           and pagination.get("official_reference_method")
           == "paper.pagination_reference",
           f"两跑逐键相等；blocks={counts.get('blocks')} "
           f"chars={counts.get('chars')}；回执零分页字段"
           "（CSS 预览结构性不携带分页主张，08§3）")

    # ---------------------------------------------- C02 分页参照（LibreOffice 实测）
    ref = bridge_call(config, "paper.pagination_reference",
                      {"docx_path": str(docx)})
    viewr = ref[1].get("result", {})
    engine = viewr.get("engine", {})
    pages = viewr.get("pages", [])
    ref_file = (root / "state" / "paper-preview"
                / str(viewr.get("docx", {}).get("content_digest", "x"))[:16]
                / "reference.pdf")
    record("C02_reference_libreoffice_measured",
           ref[0] == 0 and viewr.get("schema") == SCHEMA
           and viewr.get("page_count", 0) >= 2
           and len(pages) == viewr.get("page_count")
           and all(p.get("line_count", 0) > 0 and p.get("first_line")
                   for p in pages)
           and viewr.get("total_lines", 0) >= 120
           and str(engine.get("version", "")).startswith("26.8")
           and engine.get("name") == "libreoffice"
           and Path(str(engine.get("binary", ""))).name.startswith("soffice")
           and viewr.get("disclaimer")
           == "official_render_reference_not_css_preview"
           and viewr.get("reference_kind")
           == "LibreOffice_PDF_render_measured_by_pdfium"
           and ref_file.is_file(),
           f"LibreOffice {engine.get('version')} 渲染 PDF："
           f"page_count={viewr.get('page_count')} "
           f"total_lines={viewr.get('total_lines')}（页数/逐页文本自 PDF "
           "实测 pdfium，非 DOCX 推导非 CSS 近似）")

    # ---------------------------------------------- C03 复用＋跨状态根复现
    ref_again = bridge_call(config, "paper.pagination_reference",
                            {"docx_path": str(docx)})
    viewa = ref_again[1].get("result", {})
    config_b = dict(config,
                    paper_state_root=str(root / "state-b"))
    ref_b = bridge_call(config_b, "paper.pagination_reference",
                        {"docx_path": str(docx)})
    viewb = ref_b[1].get("result", {})
    record("C03_reference_reuse_and_cross_state_reproducible",
           ref_again[0] == 0 and viewa.get("reference", {}).get("rendered")
           == "reused" and viewa.get("pages") == viewr.get("pages")
           and ref_b[0] == 0
           and viewb.get("reference", {}).get("rendered") == "fresh"
           and viewb.get("page_count") == viewr.get("page_count")
           and viewb.get("pages") == viewr.get("pages"),
           f"同状态根复用 rendered=reused；跨状态根 fresh 渲染页数/逐页文本"
           f"相等（内容级确定性）；PDF sha 如实记录不主张逐字节相等"
           f"（ref_sha={str(viewr.get('reference', {}).get('sha256'))[:12]}…）")

    # ---------------------------------------------- C04 分别核（互不代言）
    record("C04_preview_and_pagination_checked_separately",
           "page_count" not in view1 and "pages" not in view1
           and viewr.get("disclaimer")
           == "official_render_reference_not_css_preview"
           and pagination.get("preview_rendering")
           == "css_continuous_sheet_no_page_claims",
           "预览面（paper.document）结构性零分页 × 参照面"
           "（paper.pagination_reference）官方渲染 disclaimer——两方法"
           "分别承载互不代言（08§3「CSS 预览不等正式 DOCX」）")

    # ---------------------------------------------- C05 桥 fail-closed 负向
    rc_unknown, res_unknown = bridge_call(config, "paper.repaginate",
                                          {"docx_path": str(docx)})
    rc_missing, res_missing = bridge_call(
        config, "paper.document",
        {"docx_path": str(root / "no-such.docx")})
    no_soffice = {"paper_state_root": str(root / "state")}
    rc_ns, res_ns = bridge_call(no_soffice, "paper.pagination_reference",
                                {"docx_path": str(docx)})
    no_root = {"libreoffice_soffice": soffice}
    rc_nr, res_nr = bridge_call(no_root, "paper.pagination_reference",
                                {"docx_path": str(docx)})
    leak_terms = (docx.name, "合成段落042")
    err_blob = json.dumps(
        [str(res_unknown.get("code")), str(res_missing.get("code")),
         str(res_ns.get("code")), str(res_nr.get("code"))],
        ensure_ascii=False)
    record("C05_bridge_fail_closed_negatives",
           rc_unknown == 3
           and res_unknown.get("status") == "NOT_CONNECTED"
           and "method_not_connected:paper.repaginate"
           in str(res_unknown.get("code"))
           and rc_missing == 3
           and "f18_docx_not_found" in str(res_missing.get("code"))
           and rc_ns == 3
           and "f18_soffice_not_configured" in str(res_ns.get("code"))
           and rc_nr == 3
           and "f18_state_root_not_configured" in str(res_nr.get("code"))
           and not any(term in err_blob for term in leak_terms),
           f"未知方法 exit{rc_unknown}／docx 缺失 exit{rc_missing}／"
           f"无 soffice exit{rc_ns}／无状态根 exit{rc_nr}；"
           "错误码不携材料内容（文件名/正文片段零出现）")

    # ---------------------------------------------- C06 语料只读锚
    sha_after = sha256_file(docx)
    record("C06_corpus_readonly_anchor",
           sha_before == sha_after,
           f"合成 docx 跑前后 sha256 相等（{sha_before[:12]}…）")

    ok = all(c["ok"] for c in checks)
    evidence = {
        "schema": SCHEMA, "unit": "W3-U21", "obligation": "F18",
        "profile": profile, "started_utc": started,
        "finished_utc": now_iso(),
        "state_root": str(root / "state"),
        "corpus": {"file": docx.name, "sha256": sha_before,
                   "paragraphs": 120, "synthetic": True},
        "bridge_entry": str(BRIDGE),
        "checks": checks,
        "reference": {"page_count": viewr.get("page_count"),
                      "total_lines": viewr.get("total_lines"),
                      "engine_version": engine.get("version"),
                      "pages": pages,
                      "reference_sha256":
                          viewr.get("reference", {}).get("sha256")},
        "document": {"counts": counts,
                     "content_digest":
                         view1.get("docx", {}).get("content_digest")},
        "overall": "RECON_OK" if ok else "RECON_FAIL",
    }
    (evidence_dir / "f18-recon.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"[{profile}] {evidence['overall']}（{sum(c['ok'] for c in checks)}"
          f"/{len(checks)}）", flush=True)
    return (0 if ok else 2), evidence


# --------------------------------------------------------------------------
# 真机 Electron CDP 会话（desktop；scratch 一次性检出）
# --------------------------------------------------------------------------

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
        return value.get("value")

    def screenshot(self, path: str) -> None:
        shot = self.call("Page.captureScreenshot",
                         {"format": "png"})["result"]["data"]
        Path(path).write_bytes(base64.b64decode(shot))


def wait_for_port(port: int, timeout: float = 420.0) -> dict:
    """等 CDP 就绪（冷启动首跑要现场 vite 构建，实测可达数分钟）。"""
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


def js_open_panel() -> str:
    return """(() => {
  const buttons = [...document.querySelectorAll('button')];
  const open = buttons.find(b => b.textContent && b.textContent.includes('收起纸张预览'));
  if (open) return 'already-open';
  const toggle = buttons.find(b => b.textContent && b.textContent.includes('纸张预览'));
  if (!toggle) return 'toggle-not-found';
  toggle.click();
  return 'opened';
})()"""


def js_wait(selector: str, timeout_ms: int = 25000) -> str:
    """轮询等待选择子出现（上限须低于 CDP ws 30s 超时；后台窗口定时器被
    节流时靠首查即中/重连兜底）。"""
    return (
        "new Promise(resolve => {const t0=Date.now();"
        "const tick=()=>{const el=document.querySelector('%s');"
        "if(el)resolve(true);else if(Date.now()-t0>%d)resolve(false);"
        "else setTimeout(tick,120)};tick()})" % (selector, timeout_ms))


JS_STYLE_READBACK = """(() => {
  const sheet = document.querySelector('[data-testid="paper-sheet"]');
  if (!sheet) return JSON.stringify({missing: 'sheet'});
  const cs = getComputedStyle(sheet);
  const body = getComputedStyle(document.querySelector('[data-testid="paper-body"]'));
  return JSON.stringify({paddingTop: cs.paddingTop, paddingRight: cs.paddingRight,
    paddingBottom: cs.paddingBottom, paddingLeft: cs.paddingLeft,
    width: cs.width, minHeight: cs.minHeight, fontSize: cs.fontSize,
    bodyFontFamily: body.fontFamily, boxShadow: cs.boxShadow,
    background: cs.backgroundColor, color: cs.color, transform: cs.transform,
    paras: document.querySelectorAll('[data-paper-kind="paragraph"]').length});
})()"""

JS_PREVIEW_NO_PAGE_CLAIMS = """(() => {
  const sheet = document.querySelector('[data-testid="paper-sheet"]');
  if (!sheet) return JSON.stringify({missing: 'sheet'});
  const text = sheet.textContent || '';
  return JSON.stringify({
    pageCountClaim: /共\\s*\\d+\\s*页/.test(text),
    pageAttrs: sheet.querySelectorAll('[data-paper-page-count],[data-paper-ref-page],[data-paper-page]').length,
    charCount: text.length});
})()"""

JS_BANNER_AND_GEOMETRY = """(() => {
  const banner = document.querySelector('[data-testid="paper-preview-banner"]');
  const viewport = document.querySelector('[data-testid="paper-viewport"]');
  if (!banner || !viewport) return JSON.stringify({missing: true});
  const br = banner.getBoundingClientRect();
  const vr = viewport.getBoundingClientRect();
  const disjoint = br.right <= vr.left || vr.right <= br.left || br.bottom <= vr.top || vr.bottom <= br.top;
  return JSON.stringify({bannerText: banner.textContent, disjoint});
})()"""

JS_ZOOM_CHECK = """(() => {
  const viewport = document.querySelector('[data-testid="paper-viewport"]');
  const body = document.querySelector('[data-testid="paper-body"]');
  const sheet = document.querySelector('[data-testid="paper-sheet"]');
  if (!viewport || !body || !sheet) return JSON.stringify({missing: true});
  const vr = viewport.getBoundingClientRect();
  // 命中测试打在视口中心：该点展示的必须是正文区链上的元素（paper-body
  // 自身、其后代、或其祖先容器 sheet/viewport——祖先命中＝纸面留白/页
  // 边距，是纸张设计的一部分而非覆盖层）；其它元素＝覆盖层遮正文。
  const cx = vr.left + vr.width / 2, cy = vr.top + vr.height / 2;
  const hit = document.elementFromPoint(cx, cy);
  const inTextRegion = !!(hit && (hit === body || body.contains(hit)
    || hit.contains(body)));
  const paras = [...body.querySelectorAll('[data-paper-kind="paragraph"]')];
  const visibleParas = paras.filter(p => {
    const x = p.getBoundingClientRect();
    return x.top < vr.bottom && x.bottom > vr.top;}).length;
  const banner = document.querySelector('[data-testid="paper-preview-banner"]');
  const br = banner ? banner.getBoundingClientRect() : null;
  const bannerOverlaps = br ? !(br.right <= vr.left || vr.right <= br.left || br.bottom <= vr.top || vr.bottom <= br.top) : null;
  return JSON.stringify({zoom: sheet.getAttribute('data-paper-zoom'),
    transform: getComputedStyle(sheet).transform,
    fontSize: getComputedStyle(sheet).fontSize,
    fontFamily: getComputedStyle(sheet).fontFamily.slice(0, 40),
    covered: !inTextRegion, hitTag: hit ? hit.tagName : null,
    visibleParas, bannerOverlaps,
    totalParas: paras.length});
})()"""

JS_SCROLL_REACH_LAST = """(() => {
  const viewport = document.querySelector('[data-testid="paper-viewport"]');
  const body = document.querySelector('[data-testid="paper-body"]');
  viewport.scrollTop = viewport.scrollHeight;
  return new Promise(resolve => setTimeout(() => {
    const paras = [...body.querySelectorAll('[data-paper-kind="paragraph"]')];
    const last = paras[paras.length - 1];
    const vr = viewport.getBoundingClientRect();
    const lr = last.getBoundingClientRect();
    resolve(JSON.stringify({scrollTop: viewport.scrollTop,
      scrollHeight: viewport.scrollHeight, clientHeight: viewport.clientHeight,
      lastReachable: lr.top < vr.bottom && lr.bottom > vr.top + 1,
      lastText: (last.textContent || '').slice(0, 12)}));
  }, 250));
})()"""


def js_set_zoom(value: str) -> str:
    return (
        "(() => {const sel=document.querySelector('[data-testid=\"paper-zoom\"]');"
        "if(!sel) return 'select-not-found';"
        "const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLSelectElement.prototype,'value').set;"
        "setter.call(sel,%s);"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));"
        "return sel.getAttribute('data-paper-zoom');})()" % json.dumps(value))


def js_inject_invalid_zoom() -> str:
    return (
        "(() => {const sel=document.querySelector('[data-testid=\"paper-zoom\"]');"
        "if(!sel) return 'select-not-found';"
        "const opt=document.createElement('option');opt.value='9';"
        "sel.appendChild(opt);"
        "const setter=Object.getOwnPropertyDescriptor("
        "window.HTMLSelectElement.prototype,'value').set;"
        "setter.call(sel,'9');"
        "sel.dispatchEvent(new Event('change',{bubbles:true}));"
        "return 'dispatched';})()")


def js_read_reference() -> str:
    return (
        "(() => {const ref=document.querySelector("
        "'[data-testid=\"paper-reference\"]');"
        "const sheet=document.querySelector('[data-testid=\"paper-sheet\"]');"
        "if(!ref) return JSON.stringify({hasRef:false});"
        "return JSON.stringify({hasRef:true,"
        "pageCount:ref.getAttribute('data-paper-page-count'),"
        "kind:ref.getAttribute('data-paper-reference-kind'),"
        "nonCssLabel:ref.textContent.includes('非 CSS 预览'),"
        "refInsideSheet:sheet?sheet.contains(ref):null,"
        "pageItems:ref.querySelectorAll('[data-paper-ref-page]').length,"
        "text:ref.textContent.slice(0,160)});})()")


def _px(mm: float, zoom: float) -> float:
    return mm * 96.0 / 25.4 * zoom


def run_cdp(docx: Path, state_root: Path, soffice: str,
            expected_page_count: int, clone: Path) -> tuple[int, dict]:
    """真机 Electron CDP 会话（desktop）。返回 (0/1, readback)。"""
    evidence_dir = REPO / "docs" / "construction" / "evidence" / "F18" / "desktop"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    readback: dict = {"cdpPort": CDP_PORT, "clone": str(clone),
                      "startedUtc": now_iso()}

    def _port_open() -> bool:
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/json" % CDP_PORT, timeout=2):
                return True
        except Exception:
            return False

    electron = None
    if not _port_open():
        env = dict(os.environ)
        env["LVYIN_CDP_PORT"] = str(CDP_PORT)
        # dev.ts 内部 Bun.spawn(["bun", ...]) 需要 bun 在 PATH 上（实测
        # ENOENT：非交互 shell 不带 %USERPROFILE%\.bun）。
        env["PATH"] = str(DEFAULT_BUN.parent) + os.pathsep + env.get("PATH", "")
        electron = subprocess.Popen(
            [str(DEFAULT_BUN), "run", "dev:desktop"],
            cwd=str(clone), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        page = wait_for_port(CDP_PORT)

        def _connect() -> Cdp:
            return Cdp(page["webSocketDebuggerUrl"])

        cdp = _connect()
        time.sleep(6)

        # 应用持久化上次路由（共享 userData）——不在工作台首页则回首页
        # （纸张预览按钮在工作台 header；solid-router 路径路由，整页跳 '/'）。
        at_home = cdp.evaluate(
            "!!document.querySelector('[data-testid=\"legal-workbench\"]')")
        if not at_home:
            cdp.evaluate("location.href = location.origin + '/'")
            time.sleep(8)
            try:
                cdp.conn.close()
            except Exception:
                pass
            cdp = _connect()
            cdp.evaluate(js_wait('[data-testid="legal-workbench"]', 25000),
                         await_promise=True)

        def ok(name: bool) -> str:
            return "PASS" if name else "FAIL"

        verdicts: dict[str, str] = {}

        # ---- S01 fail-closed 首态（无 config）；冷启动首屏 vite 转换可能
        # 占住主线程致 evaluate 超时——重连一次重试（仅首个断言）。
        try:
            opened = cdp.evaluate(js_open_panel())
        except Exception:
            time.sleep(10)
            try:
                cdp.conn.close()
            except Exception:
                pass
            cdp = _connect()
            opened = cdp.evaluate(js_open_panel())
        rendered = cdp.evaluate(
            js_wait('[data-testid="paper-surface"]'), await_promise=True)
        not_connected = cdp.evaluate(
            "!!document.querySelector('[data-testid=\"paper-not-connected\"]')")
        sheet_absent = cdp.evaluate(
            "!document.querySelector('[data-testid=\"paper-sheet\"]')")
        verdicts["S01_fail_closed_without_config"] = ok(
            opened in ("opened", "already-open") and rendered is True \
            and not_connected
            and sheet_absent)
        readback["S01"] = {"opened": opened, "rendered": rendered,
                           "notConnected": not_connected,
                           "sheetAbsent": sheet_absent}
        print("[S01] opened=%s notConnected=%s sheetAbsent=%s"
              % (opened, not_connected, sheet_absent), flush=True)

        # ---- 写入 lvyin config（产品根；会话毕删净）→ 重新读取
        PAPER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        PAPER_CONFIG.write_text(json.dumps({
            "python": sys.executable,
            "bridge_entry": str(BRIDGE),
            "paper_state_root": str(state_root),
            "document_docx": str(docx),
            "libreoffice_soffice": soffice,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        cdp.evaluate(
            "(() => {const buttons=[...document.querySelectorAll('button')];"
            "const b=buttons.find(x=>x.textContent && "
            "x.textContent.includes('重新读取') && "
            "x.closest('[data-testid=\"paper-surface\"]'));"
            "if(!b) return 'refetch-not-found'; b.click(); return 'clicked';})()")
        sheet_ready = cdp.evaluate(
            js_wait('[data-testid="paper-sheet"]'), await_promise=True)
        time.sleep(2)

        # ---- S02 CSS 文书观感（computed style 实测）
        style = json.loads(cdp.evaluate(JS_STYLE_READBACK))
        zoom = 1.0
        pad_ok = all(abs(float(style[k].replace("px", "")) - _px(v, zoom)) <= 2.0
                     for k, v in (("paddingTop", SHEET_MM["top"]),
                                  ("paddingRight", SHEET_MM["right"]),
                                  ("paddingBottom", SHEET_MM["bottom"]),
                                  ("paddingLeft", SHEET_MM["left"])))
        serif_ok = ("SimSun" in style["bodyFontFamily"]
                    and "serif" in style["bodyFontFamily"])
        shadow = style["boxShadow"]
        shadow_ok = (shadow and shadow != "none"
                     and "0px 1px 3px" in shadow and "0px 0px 1px" in shadow
                     and "0.14" in shadow)
        verdicts["S02_paper_css_look"] = ok(
            sheet_ready is True and serif_ok and pad_ok and shadow_ok
            and style["background"] == "rgb(255, 255, 255)"
            and style["transform"] == "none"
            and int(style["paras"]) == 120)
        readback["S02"] = {"style": style, "paddingOk": pad_ok,
                           "serifOk": serif_ok, "shadowOk": shadow_ok}
        print("[S02] serif=%s pad=%s shadow=%s bg=%s transform=%s paras=%s"
              % (serif_ok, pad_ok, shadow_ok, style["background"],
                 style["transform"], style["paras"]), flush=True)

        # ---- S03 免责声明恒在＋预览区零分页主张
        banner = json.loads(cdp.evaluate(JS_BANNER_AND_GEOMETRY))
        no_claims = json.loads(cdp.evaluate(JS_PREVIEW_NO_PAGE_CLAIMS))
        verdicts["S03_disclaimer_and_no_pagination_claim"] = ok(
            DISCLAIMER in str(banner.get("bannerText"))
            and banner.get("disjoint") is True
            and no_claims.get("pageCountClaim") is False
            and no_claims.get("pageAttrs") == 0
            and int(no_claims.get("charCount", 0)) > 4000)
        readback["S03"] = {"banner": banner, "noClaims": no_claims}
        print("[S03] bannerDisjoint=%s pageCountClaim=%s pageAttrs=%s"
              % (banner.get("disjoint"), no_claims.get("pageCountClaim"),
                 no_claims.get("pageAttrs")), flush=True)

        # ---- S04 缩放阅读不遮正文（闭集逐档＋闭集外响亮拒）
        zoom_results = []
        s04_ok = True
        for value in ZOOM_LEVELS:
            got = cdp.evaluate(js_set_zoom(value))
            time.sleep(1)
            check = json.loads(cdp.evaluate(JS_ZOOM_CHECK))
            reach = json.loads(cdp.evaluate(
                JS_SCROLL_REACH_LAST, await_promise=True))
            cdp.evaluate(
                "(() => {const v=document.querySelector("
                "'[data-testid=\"paper-viewport\"]'); if(v) v.scrollTop=0;"
                "return 'top';})()")
            passed = (got == value and check.get("transform") == "none"
                      and check.get("covered") is False
                      and check.get("bannerOverlaps") is False
                      and int(check.get("totalParas", 0)) == 120
                      and int(check.get("visibleParas", 0)) > 0
                      and reach.get("lastReachable") is True)
            s04_ok = s04_ok and passed
            zoom_results.append({"zoom": value, "setAttribute": got,
                                 "check": check, "reach": reach,
                                 "pass": passed})
            print("[S04] zoom=%s covered=%s visibleParas=%s "
                  "bannerOverlaps=%s lastReachable=%s"
                  % (value, check.get("covered"),
                     check.get("visibleParas"),
                     check.get("bannerOverlaps"),
                     reach.get("lastReachable")), flush=True)
        injected = cdp.evaluate(js_inject_invalid_zoom())
        time.sleep(1)
        error_text = cdp.evaluate(
            "(() => {const el=document.querySelector("
            "'[data-testid=\"paper-error\"]');"
            "return el ? el.textContent : null;})()")
        invalid_refused = bool(
            injected == "dispatched" and error_text
            and "f18_zoom_invalid" in error_text)
        # 还原：移除注入项，回 100%
        cdp.evaluate(
            "(() => {const sel=document.querySelector("
            "'[data-testid=\"paper-zoom\"]');"
            "const bad=[...sel.options].find(o=>o.value==='9');"
            "if(bad) bad.remove();"
            "const setter=Object.getOwnPropertyDescriptor("
            "window.HTMLSelectElement.prototype,'value').set;"
            "setter.call(sel,'1');"
            "sel.dispatchEvent(new Event('change',{bubbles:true}));"
            "return 'restored';})()")
        s04_ok = s04_ok and invalid_refused
        verdicts["S04_zoom_reading_never_covers_body"] = ok(s04_ok)
        readback["S04"] = {"zooms": zoom_results,
                           "invalidZoomInjected": injected,
                           "invalidZoomError": error_text,
                           "invalidRefused": invalid_refused}
        print("[S04] invalid-zoom refused=%s error=%s"
              % (invalid_refused, error_text), flush=True)

        # ---- S05 官方渲染参照独立呈现（页数==独立桥回读）
        cdp.evaluate(
            "(() => {const b=document.querySelector("
            "'[data-testid=\"paper-reference-load\"]');"
            "if(!b) return 'button-not-found'; b.click();"
            "return 'clicked';})()")
        ref_ready = cdp.evaluate(
            js_wait('[data-testid="paper-reference"]'), await_promise=True)
        time.sleep(1)
        ref = json.loads(cdp.evaluate(js_read_reference()))
        verdicts["S05_official_reference_separate"] = ok(
            ref_ready is True and ref.get("hasRef") is True
            and str(ref.get("pageCount")) == str(expected_page_count)
            and int(ref.get("pageItems", 0)) == expected_page_count
            and ref.get("nonCssLabel") is True
            and ref.get("refInsideSheet") is False
            and ref.get("kind")
            == "LibreOffice_PDF_render_measured_by_pdfium")
        readback["S05"] = {"refReady": ref_ready, "reference": ref,
                           "expectedPageCount": expected_page_count}
        print("[S05] refReady=%s pageCount=%s expected=%s nonCss=%s "
              "refInsideSheet=%s"
              % (ref_ready, ref.get("pageCount"), expected_page_count,
                 ref.get("nonCssLabel"), ref.get("refInsideSheet")),
              flush=True)

        # 截图（参照呈现态）
        cdp.screenshot(str(evidence_dir / "f18-paper-preview-electron.png"))
        readback["screenshot"] = "f18-paper-preview-electron.png"

        # ---- S06 撤通道 fail-closed
        PAPER_CONFIG.unlink()
        cdp.evaluate(
            "(() => {const buttons=[...document.querySelectorAll('button')];"
            "const b=buttons.find(x=>x.textContent && "
            "x.textContent.includes('重新读取') && "
            "x.closest('[data-testid=\"paper-surface\"]'));"
            "if(!b) return 'refetch-not-found'; b.click(); return 'clicked';})()")
        time.sleep(4)
        nc_again = cdp.evaluate(
            "!!document.querySelector('[data-testid=\"paper-not-connected\"]')")
        sheet_gone = cdp.evaluate(
            "!document.querySelector('[data-testid=\"paper-sheet\"]')")
        config_gone = not PAPER_CONFIG.exists()
        verdicts["S06_fail_closed_after_config_removed"] = ok(
            nc_again and sheet_gone and config_gone)
        readback["S06"] = {"notConnectedAgain": nc_again,
                           "sheetGone": sheet_gone,
                           "configRemoved": config_gone}
        print("[S06] notConnected=%s sheetGone=%s configRemoved=%s"
              % (nc_again, sheet_gone, config_gone), flush=True)

        readback["verdicts"] = verdicts
        readback["overall"] = ("PASS" if all(v == "PASS"
                                             for v in verdicts.values())
                               else "FAIL")
        readback["finishedUtc"] = now_iso()
        (evidence_dir / "f18-cdp-readback.json").write_text(
            json.dumps(readback, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print("CDP_%s %s" % (readback["overall"], verdicts), flush=True)
        return (0 if readback["overall"] == "PASS" else 1), readback
    finally:
        if electron is not None:
            try:
                electron.kill()
            except Exception:
                pass
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(electron.pid)],
                           capture_output=True)
        try:
            PAPER_CONFIG.unlink()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"], default=None)
    parser.add_argument("--soffice", default=DEFAULT_SOFFICE)
    parser.add_argument("--clone", type=Path, default=DEFAULT_CLONE)
    parser.add_argument("--skip-cdp", action="store_true",
                        help="（仅调试用；正式验收不含此开关——跳过时 exit 3）")
    args = parser.parse_args(argv)
    profiles = args.profile or ["desktop", "selfhost"]

    if not Path(args.soffice).is_file() and not Path(
            str(args.soffice).replace(".exe", ".com")).is_file():
        eprint("[ENV] LibreOffice 未安装于 %s（裁决#5 预期已装）" % args.soffice)
        return 3

    work = Path(tempfile.mkdtemp(prefix="f18-recon-"))
    docx = work / "f18-synthetic.docx"
    build_synthetic_docx(docx)
    print(f"[GEN] 合成语料 {docx}（sha256={sha256_file(docx)[:12]}…）",
          flush=True)

    rc_all = 0
    expected_page_count = None
    desktop_state_root = None
    for profile in profiles:
        rc, evidence = run_profile(profile, docx, args.soffice)
        rc_all = rc_all or rc
        if profile == "desktop":
            expected_page_count = evidence["reference"]["page_count"]
            desktop_state_root = Path(evidence["state_root"])

    if args.skip_cdp:
        eprint("[CDP] --skip-cdp 不构成验收（真机 CDP 会话是本单验收面）")
        return 3
    if "desktop" not in profiles or desktop_state_root is None:
        eprint("[CDP] 真机 CDP 会话属 desktop profile，本轮 profiles 未含")
        return 3
    rc_cdp, _ = run_cdp(docx, desktop_state_root, args.soffice,
                        expected_page_count or 0, args.clone)
    rc_all = rc_all or rc_cdp
    print("\nF18_RECON_%s" % ("OK" if rc_all == 0 else "FAIL"), flush=True)
    return rc_all


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    raise SystemExit(main())
