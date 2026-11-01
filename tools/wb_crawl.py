"""WorkBuddy UI 遍历引擎（CDP 驱动）：枚举导航→逐项点击→截图→抓取可见文本与 DOM 结构。
用法：python -X utf8 wb_crawl.py
输出：/tmp 或 %TEMP%/wb-crawl/<n>-<name>.png + <n>-<name>.dom.txt + crawl-index.json
"""
import json, os, time, base64, pathlib
import websocket

import urllib.request
_targets = json.loads(urllib.request.urlopen("http://127.0.0.1:9333/json/list", timeout=10).read())
_page = next(t for t in _targets if t.get("type") == "page")
WS = _page["webSocketDebuggerUrl"]
OUT = pathlib.Path(os.environ.get("TEMP", r"C:\Users\being\AppData\Local\Temp")) / "wb-crawl"
OUT.mkdir(parents=True, exist_ok=True)

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
    return r.get("result", {}).get("value")

def shot(ws, name):
    r = send(ws, "Page.captureScreenshot", {"format": "png"})
    (OUT / f"{name}.png").write_bytes(base64.b64decode(r["data"]))
    return f"{name}.png"

def dom_text(ws, name, js):
    v = ev(ws, js) or ""
    (OUT / f"{name}.dom.txt").write_text(str(v), encoding="utf-8")
    return str(v)[:200]

ws = websocket.create_connection(WS, timeout=30, suppress_origin=True)
ws.settimeout(20)
send(ws, "Page.enable"); send(ws, "Runtime.enable")
time.sleep(1)

# 0) 当前状态基线
print(dom_text(ws, "000-initial", "document.body.innerText.slice(0, 3000)"))
print(shot(ws, "000-initial"))

# 1) 枚举侧栏可点击项（WorkBuddy 左栏）
nav = ev(ws, """
(() => {
  const items = [];
  document.querySelectorAll('aside *, nav *, [class*=sidebar] *, [class*=rail] *').forEach(el => {
    if (el.children.length === 0 && el.innerText && el.innerText.trim().length > 0 && el.innerText.trim().length < 20) {
      const r = el.getBoundingClientRect();
      if (r.x < 300 && r.width > 0) items.push({tag: el.tagName, cls: (el.className||'').toString().slice(0,60), text: el.innerText.trim(), x: Math.round(r.x), y: Math.round(r.y)});
    }
  });
  return JSON.stringify(items.slice(0, 40));
})()""")
print("NAV ITEMS:", nav)
(OUT / "nav-items.json").write_text(nav or "[]", encoding="utf-8")

# 2) 枚举全页所有按钮/可点击文本（第一层）
allbtn = ev(ws, """
(() => {
  const out = [];
  document.querySelectorAll('button, [role=button], [role=menuitem], [role=tab], a').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && el.innerText && el.innerText.trim()) out.push({t: el.innerText.trim().slice(0,30), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)});
  });
  return JSON.stringify(out.slice(0, 60));
})()""")
(OUT / "buttons-l1.json").write_text(allbtn or "[]", encoding="utf-8")
print("L1 BUTTONS:", allbtn[:400])
ws.close()
print("PHASE1_DONE ->", OUT)
