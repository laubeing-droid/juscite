"""WorkBuddy UI 全量遍历套件 · 核心库（复用 wb_crawl.py 已验证的连接方式）。
用法（阶段脚本 import 本库）：from wb_lib import *；conn() 建连；snap(ws,name) 三件套落盘。
纪律：只读遍历；危险操作（删除/发送/归档）一律不点；弹层用 ESC 撤销。
"""
import json, os, time, base64, pathlib, urllib.request
import websocket

OUT = pathlib.Path(os.environ.get("TEMP", r"C:\Users\being\AppData\Local\Temp")) / "wb-crawl"
OUT.mkdir(parents=True, exist_ok=True)
CDP = "http://127.0.0.1:9333"

def find_ws():
    targets = json.loads(urllib.request.urlopen(CDP + "/json/list", timeout=10).read())
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        raise RuntimeError("no page target")
    # 优先主窗口（WorkBuddy title）
    for t in pages:
        if "WorkBuddy" in (t.get("title") or ""):
            return t
    return pages[0]

def conn(timeout=25):
    """连接主窗口（排除搜索窗等覆盖窗口：搜索窗 innerText 含'输入关键字进行检索'且较短）。"""
    targets = json.loads(urllib.request.urlopen(CDP + "/json/list", timeout=10).read())
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        raise RuntimeError("no page target")
    order = [t for t in pages if "WorkBuddy" in (t.get("title") or "")] or pages
    last_err = None
    for t in order:
        try:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=timeout, suppress_origin=True)
            ws.settimeout(45)
            send(ws, "Page.enable"); send(ws, "Runtime.enable")
            head = ""
            for _ in range(3):
                r = send(ws, "Runtime.evaluate", {"expression": "document.body ? document.body.innerText.slice(0, 200) : ''", "returnByValue": True})
                head = (r.get("result", {}) or {}).get("value") or ""
                if head:
                    break
                time.sleep(0.6)
            if "输入关键字进行检索" in head and "任务 (3)" not in head and "空间 (" not in head:
                ws.close(); continue  # 搜索窗，跳过
            return ws, t
        except Exception as e:
            last_err = e
    raise RuntimeError(f"no main window: {last_err}")

_id = [0]
def send(ws, method, params=None):
    _id[0] += 1
    ws.send(json.dumps({"id": _id[0], "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == _id[0]:
            return msg.get("result", msg)

def ev(ws, js):
    r = send(ws, "Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True})
    res = r.get("result", {})
    if res.get("subtype") == "error" or "exceptionDetails" in r:
        return "«JS-ERR: " + json.dumps(r.get("exceptionDetails", r), ensure_ascii=False)[:300] + "»"
    return res.get("value")

def shot(ws, name, retries=2):
    for i in range(retries + 1):
        try:
            r = send(ws, "Page.captureScreenshot", {"format": "png"})
            (OUT / f"{name}.png").write_bytes(base64.b64decode(r["data"]))
            return f"{name}.png"
        except Exception as e:
            if i == retries:
                print(f"!! shot {name} failed: {e}")
                return None
            time.sleep(2)

def save(name, text, ext="dom.txt"):
    (OUT / f"{name}.{ext}").write_text(str(text if text is not None else ""), encoding="utf-8")

# ---------- 三件套 ----------
def snap(ws, name, extra_js=""):
    """截图 + innerText 全文 + 可点击元素枚举，三件套落盘；返回 innerText 前 400 字符。"""
    shot(ws, name)
    txt = ev(ws, "document.body.innerText") or ""
    save(name, txt)
    els = ev(ws, """
(() => {
  const out = [];
  const seen = new Set();
  document.querySelectorAll('button, [role=button], [role=menuitem], [role=tab], [role=option], [role=menuitemcheckbox], [role=menuitemradio], a, [onclick], input, [contenteditable=true]').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      const t = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 60);
      const key = t + '|' + el.tagName;
      if (seen.has(key)) return; seen.add(key);
      out.push({t, tag: el.tagName, role: el.getAttribute('role') || '', x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), href: (el.getAttribute('href')||'').slice(0,80)});
    }
  });
  return JSON.stringify(out);
})()""")
    save(name, els or "[]", "els.json")
    if extra_js:
        save(name, ev(ws, extra_js) or "", "extra.json")
    return txt[:400]

# ---------- 交互 ----------
def js_click(ws, js, settle=1.2):
    """执行返回元素的 JS 并 click()。js 须返回单个元素或 null。"""
    r = ev(ws, f"(() => {{ const el = ({js}); if (el) {{ el.click(); return 'clicked'; }} return 'not-found'; }})()")
    time.sleep(settle)
    return r

def click_text(ws, text, scope_js="document", nth=0, settle=1.2, exact=False):
    """按可见文本点击（含子文本匹配，取最内层可点击者）。"""
    cond = f"t === {json.dumps(text)}" if exact else f"t.includes({json.dumps(text)})"
    js = f"""
(() => {{
  const root = {scope_js};
  const cands = [];
  root.querySelectorAll('*').forEach(el => {{
    const own = Array.from(el.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
    const t = (own || (el.innerText || '').trim().split('\\n')[0]).trim();
    if ({cond} && t.length < 80) {{
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) cands.push([el, r.width * r.height]);
    }}
  }});
  if (!cands.length) return null;
  cands.sort((a, b) => a[1] - b[1]);
  let el = cands[Math.min({nth}, cands.length - 1)][0];
  el.click();
  return 'clicked:' + (el.innerText || '').trim().slice(0, 40);
}})()"""
    r = ev(ws, js)
    time.sleep(settle)
    return r

def click_xy(ws, x, y, button="left", settle=1.0):
    """Input 域鼠标事件（用于右键菜单/悬停）。"""
    for typ in ("mousePressed", "mouseReleased"):
        send(ws, "Input.dispatchMouseEvent", {"type": typ, "x": int(x), "y": int(y), "button": button, "buttons": 1 if typ == "mousePressed" else 0, "clickCount": 1})
    time.sleep(settle)

def hover_xy(ws, x, y, settle=0.8):
    send(ws, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": int(x), "y": int(y), "button": "none"})
    time.sleep(settle)

def key(ws, keyname, settle=0.5, modifiers=0):
    send(ws, "Input.dispatchKeyEvent", {"type": "keyDown", "key": keyname, "code": keyname, "windowsVirtualKeyCode": {"Escape": 27, "Enter": 13, "ArrowDown": 40, "ArrowUp": 38, "ArrowRight": 39, "ArrowLeft": 37}.get(keyname, 0), "modifiers": modifiers})
    send(ws, "Input.dispatchKeyEvent", {"type": "keyUp", "key": keyname, "code": keyname, "windowsVirtualKeyCode": {"Escape": 27, "Enter": 13, "ArrowDown": 40, "ArrowUp": 38, "ArrowRight": 39, "ArrowLeft": 37}.get(keyname, 0), "modifiers": modifiers})
    time.sleep(settle)

def esc(ws, n=1, settle=0.6):
    for _ in range(n):
        key(ws, "Escape", settle)

def menu_items(ws):
    """抓当前弹出菜单（role=menu / contextmenu / floating）的全部条目文本。"""
    return ev(ws, """
(() => {
  const scopes = document.querySelectorAll('[role=menu], [role=listbox], [class*=menu], [class*=popover], [class*=dropdown], [class*=context], [class*=overlay], [class*=floating], [data-radix-popper-content-wrapper], [role=dialog]');
  const out = [];
  scopes.forEach(s => {
    const r = s.getBoundingClientRect();
    if (r.width <= 0) return;
    s.querySelectorAll('[role=menuitem], [role=option], [role=menuitemcheckbox], [role=menuitemradio], button, [data-radix-collection-item], li').forEach(it => {
      const t = (it.innerText || '').trim();
      const ir = it.getBoundingClientRect();
      if (t && ir.width > 0 && !out.some(o => o.t === t)) out.push({t: t.slice(0, 80), scope: (s.getAttribute('role') || s.className || '').toString().slice(0, 40)});
    });
  });
  return JSON.stringify(out);
})()""")

def body_hash(ws):
    import hashlib
    t = ev(ws, "document.body.innerText") or ""
    return hashlib.md5(t.encode("utf-8")).hexdigest()[:8]
