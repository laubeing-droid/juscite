# -*- coding: utf-8 -*-
"""#14 引证核验·轻量引擎（RE-14-引证核验.md §32 落码，2026-10-28）。

定位（规格 §3.2 决策与理由）：不 import 冻结 LCCC 线（resolve_effectivity
硬校验 GB/WJBS 编码，轻量包无 GB 码；且全根 md 冷扫在数据增长下不可产品
化）——解析层与同树冻结实现 citation_verifier.py 逐行等量（§2-A 全部；
本仓自有代码非竞品，可复制），数据层换 RE-13 §3.1 轻量法条包
（pack.sqlite3＋content/*.md＋pack.meta，只读消费不写包）。
单一核验权威：#10/#12/#16 等产物流水线若接核验一律复用本方法组，禁第二核验器。

铁律（与冻结线同）：零网络/零写入/零模型（F3）；缺参 fail-closed 先于
数据面加载（C5/B1-B3）；同输入字节级同输出（A10）；全文体量边界
A17=200,000 字符（产品可调参数，显式声明于此）具名拒不静默截断。

效力推导（规格 §3.1 条 1-4，数据缺口=收窄定义）：
  - valid_from NULL/空串＝按已施行消费（RE-13 §3.1 schema 行语义，
    包内留空=包常态）；valid_to 缺失＝取 schema 默认 2099-12-31；
  - 「格式坏」（非空不可解析 YYYY-MM-DD）与同名同窗双版本＝缺口→未知，
    绝不签现行（D3）；施行日当天生效、失效日当天已失效（D2 端点含语义）；
  - 链序键＝publish（对冻结线 SXRQ 键的已声明偏离，规格 §3.1 条 4：
    包内 794/1671 部 valid_from 留空，valid_from 不作链序键）；
  - 到期族细分（规格 §3.1 条 3，两层语义分立，细分态⊆徽章层已废止族）：
    链内后继（本版 valid_to=后继版 valid_from）→已修订＋replacement 具名；
    墓碑 1970-01-01→已废止；其余有限到期→已失效（H2 跨法废止在纯日期
    模型下与自身失效不可区分，词面局限如实标注，decision/code 与冻结线全等）；
    非链同名更新版在库→替代（B8，提示有新版）。状态映射按 B7：
    decision/code/status 三层分立，尚未施行落未知不造第九状态词（38a）。

CLI（规格 §3.3 桥→引擎：子进程一次性，temp JSON 进、JSON 出）：
  python -X utf8 citation_verify_lite.py <method> <request.json>
  request = {"pack_dir": "...", "as_of": "YYYYMMDD", "citation"|"text": ...}
  stdout  = {"status":"OWNER_RESPONSE","business_complete":false,"result":…} exit 0
          | {"status":"NOT_CONNECTED","code":"…"}                        exit 3
引擎自身缺 as_of 拒绝不猜（B1）——as_of 由调用方（桥）注入默认今天（G6）。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys


class NotConnected(Exception):
    """具名拒绝（冻结线 bridge_errors.NotConnected 等量；单文件自持不引依赖）。"""


# ---------------------------------------------------------------------- #
# 状态词汇（八状态＋永不标全核三态；沿用冻结线词表与码表，规格 §2-B7）
# ---------------------------------------------------------------------- #

STATUS_CURRENT = "现行"
STATUS_AMENDED = "已修订"
STATUS_ABOLISHED = "已废止"
STATUS_SUPERSEDED = "替代"
STATUS_FABRICATED = "虚构"
STATUS_EXPIRED = "失效"
STATUS_MISCITED = "误引"
STATUS_UNKNOWN = "未知"

NEVER_FULLY_VERIFIED = (STATUS_FABRICATED, STATUS_EXPIRED, STATUS_MISCITED)

# A17 全文体量边界（产品可调参数，显式声明；超限具名拒不静默截断）。
DOCUMENT_MAX_CHARS = 200_000

# 轻量包数据面名（D6 覆盖声明用；诚实标明数据面为轻量包）。
FACE_NAME = "citation_pack(RE-13 §3.1 light pack)"

SOURCE_CHAIN = ("local", "paid", "web")  # E1 顺序冻结不可跳级

# E2 付费段凭据在位性环境变量（只查在位性，不读值、不发请求）。
PAID_TOKEN_ENV_VARS = ("YUANDIAN_MCP_TOKEN", "PKULAW_MCP_TOKEN")


# ---------------------------------------------------------------------- #
# 确定性引用解析（与冻结实现 citation_verifier.py 逐行等量复制；
# 本仓自有代码非竞品。A1-A16 全部行为的唯一实现。）
# ---------------------------------------------------------------------- #

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def parse_cn_numeral(text: str):
    """中文法定数字→整数（确定性状态机；不认识返回 None 不猜；含千位）。"""
    if not text:
        return None
    total = 0
    current = 0
    saw_digit = False
    for ch in text:
        if ch in _CN_DIGITS:
            current = current * 10 + _CN_DIGITS[ch]
            saw_digit = True
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            if not saw_digit or current == 0:
                current = 1  # 「十」「百」起首＝隐式一
            total += current * unit
            current = 0
            saw_digit = False
        else:
            return None
    return total + current if text else None


_NUMERAL = r"[零一二三四五六七八九十百千]+"
_ARTICLE_RE = re.compile(
    r"第(?P<num>" + _NUMERAL + r")条(?:之(?P<sub>" + _NUMERAL + r"))?")
# 款/项跟随：数字中英皆收（A3 显式对照——条文号仅中文，款项两者皆收）。
_SUBREF_RE = re.compile(
    r"第(?:[一二三四五六七八九十百千零]+|[0-9]+)[款项]")
_QUOTE_OPEN = {"\u201c": "\u201d", "「": "」", "\u300c": "\u300d", '"': '"'}
_SENTENCE_END = "。；\n\r"
_TITLE_RE = re.compile(r"《(?P<title>[^《》\n]{1,120})》")  # A16：{1,120} 超限不成锚


def _strip_decorations(text: str) -> str:
    """确定性装饰剥离：全角空格/空白/markdown 强调与列表符，不改标点文字。"""
    cleaned = []
    for ch in text:
        if ch in ("*", "-", " ", "\u3000", "\t", ">", "#"):
            continue
        cleaned.append(ch)
    return "".join(cleaned)


def split_articles(markdown_text: str) -> dict:
    """真实 md 正文→{条文号: 条文文本} 状态机切分（A15；切分失败返回空）。"""
    if not markdown_text:
        return {}
    lines = markdown_text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":  # frontmatter 剥离
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                start = idx + 1
                break
    article_start = re.compile(r"^(?:-\s*)?\*{0,2}第(" + _NUMERAL +
                               r")条(?:之(" + _NUMERAL + r"))?\*{0,2}")
    heading = re.compile(r"^#{1,6}\s")
    articles: dict = {}
    order: list = []
    current_key = None
    current_lines: list = []
    for line in lines[start:]:
        stripped = line.strip()
        match = article_start.match(stripped) if stripped else None
        if match:
            num = parse_cn_numeral(match.group(1))
            if num is None:
                continue  # 不认识的数字形态：跳过该行，不猜
            if current_key is not None:
                articles[current_key] = "\n".join(current_lines)
            current_key = match.group(0)
            key_num = str(num) + ("之" + match.group(2) if match.group(2) else "")
            current_lines = [line]
            order.append((current_key, key_num, num, match.group(2)))
        elif current_key is not None:
            if heading.match(stripped):  # 章节标题截断
                articles[current_key] = "\n".join(current_lines)
                current_key = None
                current_lines = []
            else:
                current_lines.append(line)
    if current_key is not None:
        articles[current_key] = "\n".join(current_lines)
    result: dict = {}
    for _marker, key_num, num, sub in order:
        text = articles.get(_marker, "")
        result[key_num] = {"number": num, "sub": sub or "", "text": text}
    return result


def _scan_citation_segment(text: str, start: int):
    """引号感知段扫描：段界=引号外句界或下一书名号；引文内句号不断段（A4/A13）。"""
    in_quote = None
    quote = None
    quote_start = -1
    i = start
    length = len(text)
    while i < length:
        ch = text[i]
        if in_quote is not None:
            if ch == in_quote:
                if quote is None:
                    quote = text[quote_start + 1:i]
                in_quote = None
        elif ch in _QUOTE_OPEN:
            in_quote = _QUOTE_OPEN[ch]
            if quote_start < 0:
                quote_start = i
        elif ch in _SENTENCE_END or ch == "《":
            return i, quote
        i += 1
    return length, quote


def parse_citations(text) -> list:
    """全文确定性引用抽取（A1-A14：八字段、span 排序、确定性）。"""
    if not isinstance(text, str) or not text:  # A11 空输入/非字符串→空列表
        return []
    results: list = []
    for title_match in _TITLE_RE.finditer(text):
        title = title_match.group("title")
        seg_end, quote = _scan_citation_segment(text, title_match.end())
        tail = text[title_match.end():seg_end]
        article_matches = list(_ARTICLE_RE.finditer(tail))
        if not article_matches:  # A7 无条文的书名号引用也成条（标题级）
            results.append({
                "span": [title_match.start(), title_match.end()],
                "citation_text": title_match.group(0),
                "title": title,
                "article_ref": None, "article_number": None,
                "article_sub": None, "subrefs": [],
                "quote": quote,
            })
            continue
        cursor = 0
        for art in article_matches:
            ref_text = art.group(0)
            num = parse_cn_numeral(art.group("num"))
            if num is None:  # A8 ASCII 条文号不识别（中文数字状态机拒识）
                continue
            subref_text = ""
            probe = art.end()
            while True:  # A3 款/项跟随（紧邻连续；顿号等分隔不并入）
                sub = _SUBREF_RE.match(tail, probe)
                if not sub:
                    break
                subref_text += sub.group(0)
                probe = sub.end()
            art_abs_end = title_match.end() + probe
            results.append({
                "span": [title_match.start(), art_abs_end],
                "citation_text": title_match.group(0) + tail[art.start():probe],
                "title": title,
                "article_ref": ref_text,
                "article_number": num,
                "article_sub": art.group("sub"),
                "subrefs": subref_text,
                # A6 引文归属段内首个条文；多条文段后续条文不带引文
                "quote": quote if cursor == 0 else None,
            })
            cursor += 1
    results.sort(key=lambda item: item["span"][0])  # A9 按 span 起点排序
    return results


# ---------------------------------------------------------------------- #
# 轻量法条包消费面（只读；RE-13 §3.1 包格式）
# ---------------------------------------------------------------------- #

_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TOMBSTONE = 19700101          # 墓碑（RE-13 H3：expired 语义的纯日期形态）
_DEFAULT_VALID_TO = 20991231   # schema 默认 valid_to '2099-12-31'
_GAP = "GAP"


def _parse_pack_date(value):
    """包内日期 YYYY-MM-DD→YYYYMMDD 整数（确定性）。

    NULL/空串→None（缺省语义：valid_from=已施行、valid_to=2099-12-31，
    均非缺口——规格 §3.1 条 1 收窄定义）；非空不可解析→_GAP（格式坏=缺口）。
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _DATE_RE.match(s)
    if not m:
        return _GAP
    return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3))


def _as_of_num(as_of: str) -> int:
    return int(as_of)  # 8 位形态闸已过；假日期进窗口比较得确定性结果（B2/S5F）


class CitationPack:
    """轻量法条包只读消费面：标题精确定位（D1）＋包覆盖声明（D6）。"""

    def __init__(self, pack_dir: str):
        if not isinstance(pack_dir, str) or not pack_dir.strip():
            raise NotConnected("citation_pack_not_configured")
        db_path = os.path.join(pack_dir, "pack.sqlite3")
        meta_path = os.path.join(pack_dir, "pack.meta")
        if not os.path.isfile(db_path) or not os.path.isfile(meta_path):
            raise NotConnected("citation_pack_not_configured")
        try:
            with open(meta_path, "r", encoding="utf-8") as fh:  # 只读
                meta = json.load(fh)
            if not isinstance(meta, dict):
                raise ValueError("pack.meta not an object")
        except NotConnected:
            raise
        except Exception as exc:
            raise NotConnected("citation_pack_broken:meta_" + type(exc).__name__) from None
        try:
            self.db = sqlite3.connect(db_path)
            self.db.row_factory = sqlite3.Row  # 行取列名（row["id"] 等）
            self.db.execute("PRAGMA query_only = 1")  # 只读纪律（F3 零写入）
            quick = self.db.execute("PRAGMA quick_check").fetchone()
            if not quick or quick[0] != "ok":
                raise ValueError("quick_check=" + str(quick and quick[0]))
            self.law_count = self.db.execute("SELECT COUNT(*) FROM law").fetchone()[0]
        except NotConnected:
            raise
        except Exception as exc:
            raise NotConnected("citation_pack_broken:sqlite_" + type(exc).__name__) from None
        self.pack_dir = pack_dir
        self.meta_name = str(meta.get("name") or os.path.basename(pack_dir))
        self.meta_hash = str(meta.get("hash") or "")
        self.meta_filesize = meta.get("filesize")

    def close(self) -> None:
        try:
            self.db.close()
        except Exception:
            pass

    def find_by_title(self, title: str) -> list:
        """标题精确定位（D1）：strip 后整串相等；同名多版本全返（publish,id 链序）。"""
        q = title.strip()
        return self.db.execute(
            "SELECT id, name, level, publish, valid_from, valid_to, ver, filename"
            " FROM law WHERE name = ? ORDER BY publish, id", (q,)).fetchall()

    def read_content(self, filename: str):
        """读包内 content/{filename} md 正文；缺失→None（定位失败不猜）。"""
        path = os.path.join(self.pack_dir, "content", filename)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as fh:  # 只读
            return fh.read()

    def coverage(self) -> dict:
        """D6 包覆盖声明：包名/hash＋law 表运行时法条数（法条数不在 pack.meta）。"""
        return {
            "data_face": FACE_NAME,
            "pack_name": self.meta_name,
            "pack_hash": self.meta_hash,
            "law_count": self.law_count,
            "self_collection": "none",
            "note": "本地轻量包精确未命中≠全局不存在；付费/web 段为声明缺口，不自采、不编造",
        }


def _degradation(gap_reasons: list) -> dict:
    """E1-E5 降级链声明：本地已执行；付费/web 本期只留声明面，零跳级零 URL。"""
    paid_missing = [v for v in PAID_TOKEN_ENV_VARS if not os.environ.get(v, "").strip()]
    return {
        "chain": list(SOURCE_CHAIN),
        "policy": "local_first_no_silent_escalation",
        "segments": {
            "local": {"state": "executed", "face": FACE_NAME},
            "paid": {"state": "declared_gap_not_exercised",
                     "gap": "PAID_TOKEN_NOT_CONFIGURED" if paid_missing
                            else "PAID_TOKEN_PRESENT_NOT_EXERCISED_THIS_PHASE"},
            "web": {"state": "declared_gap_not_exercised",
                    "gap": "WEB_FALLBACK_NOT_EXERCISED_THIS_PHASE"},
        },
        "escalated": False,  # E1 本地未命中绝不静默跳级
        "gap_declared": bool(gap_reasons),
        "gap_reasons": list(gap_reasons),
        "url_disclosure": "none",  # E4 全链零 URL 披露
        "note": "本期只执行本地段；付费/web 为具名声明缺口，不跳级、不自采、不编 URL",
    }


# ---------------------------------------------------------------------- #
# 版本/效力推导（规格 §3.1 条 1-4；闸决策三层分立 B7）
# ---------------------------------------------------------------------- #

def _publish_num(row) -> int:
    """publish 链序键（§3.1 条 4 已声明偏离：publish 不依赖 valid_from）。
    NULL publish 排最前（SQLite ASC 同序，确定性）。"""
    v = row["publish"]
    if v is None or not str(v).strip():
        return 0
    s = str(v).strip()
    m = _DATE_RE.match(s)
    if not m:
        return 0  # 不可解析 publish 不作链序比较依据，排最前（不猜不抛）
    return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3))


def _gate_row(row, rows: list, as_of_num: int) -> dict:
    """单行效力闸（规格 §3.1 条 1-4）。

    decision ∈ {ALLOWED, BLOCKED, UNKNOWN}；到期族细分信号（链内后继/
    墓碑/有限到期/同名更新版）在闸层定码与词面标签，最终状态由
    _status_from_gate 按 B7 映射——三层分立，不造第九状态词。
    """
    gate = {
        "decision": "UNKNOWN", "code": "STATUS_UNKNOWN_FAIL_CLOSED",
        "label": None, "newer_exists": False, "has_successor": False,
        "replacement": None, "replacement_reason": "", "reasons": [],
    }
    vf = _parse_pack_date(row["valid_from"])
    vt = _parse_pack_date(row["valid_to"])
    if vf == _GAP or vt == _GAP:  # D3 格式坏=缺口→未知，绝不签现行
        gate["reasons"] = ["日期字段格式坏（非空但不可解析 YYYY-MM-DD）——fail-closed 未知"]
        return gate
    vt_num = _DEFAULT_VALID_TO if vt is None else vt
    same_others = [r for r in rows if r["id"] != row["id"]]
    gate["newer_exists"] = any(_publish_num(r) > _publish_num(row) for r in same_others)
    if vf is not None and as_of_num < vf:  # §3.1 条 2 尚未施行（BLOCKED）
        gate["decision"] = "BLOCKED"
        gate["code"] = "NOT_YET_IN_FORCE_AT_AS_OF"
        gate["reasons"] = ["施行日 %s 晚于核验时点——尚未施行，落未知（不造第九状态词）"
                           % str(row["valid_from"]).strip()]
        return gate
    if as_of_num >= vt_num:  # §3.1 条 3 到期族细分（失效日当天已失效，D2 端点）
        gate["decision"] = "BLOCKED"
        successor = None
        for r in same_others:
            if r["name"] != row["name"] or _publish_num(r) <= _publish_num(row):
                continue
            vf2 = _parse_pack_date(r["valid_from"])
            if vf2 is None or vf2 == _GAP or vt_num != vf2:
                continue  # 链内后继=本版 valid_to 恰为后继版 valid_from（§3.1 条 3）
            if successor is None or _publish_num(r) > _publish_num(successor):
                successor = r
        if vt_num == _TOMBSTONE:  # 墓碑→已废止（RE-13 H3 等价）
            gate["code"] = "ABOLISHED_NOT_CITABLE"
            gate["reasons"] = ["包内墓碑日期 1970-01-01＝已废止（被废除检索到也不许引）"]
        elif successor is not None:  # 链内后继→已修订＋replacement 具名（比空表强，不触 D4）
            gate["code"] = "SUPERSEDED_NOT_CITABLE"
            gate["label"] = "已修订"
            gate["has_successor"] = True
            gate["replacement"] = "《%s》（施行日 %s）" % (
                successor["name"], str(successor["valid_from"]).strip())
            gate["reasons"] = ["包内修订链在库：本版效力止于 %s，同名后继版已施行——"
                               "被替代版本不许引" % str(row["valid_to"]).strip()]
        elif gate["newer_exists"]:
            gate["code"] = "SUPERSEDED_NOT_CITABLE"
            gate["reasons"] = ["库内存在同名更新版——被替代版本不许引"]
        else:  # 其余有限到期→已失效（36e 词面局限：H2 跨法废止纯日期模型不可区分）
            gate["code"] = "SUPERSEDED_NOT_CITABLE"
            gate["label"] = "已失效"
            gate["replacement"] = "unknown"
            gate["replacement_reason"] = (
                "包内无同名后继修订链；跨法废止在纯日期模型下无被废标记信号，"
                "词面按已失效记账（decision/code 与冻结线全等）")
            gate["reasons"] = ["效力止于 %s 且无同名后继版——有限到期不许引"
                               % str(row["valid_to"]).strip()]
        if gate["replacement"] is None:
            gate["replacement"] = "unknown"
            gate["replacement_reason"] = gate["replacement_reason"] or \
                "包内替代链无具名信号，不编造替代版本"
        return gate
    # §3.1 条 4 窗口内→现行可引（交接日语义由窗口端点自动导出：同日旧版
    # 已失效、新版在窗，恰一 ALLOWED 定版新版，无特判）
    gate["decision"] = "ALLOWED"
    gate["code"] = "CURRENT_IN_FORCE_CITABLE"
    gate["reasons"] = ["核验时点在施行窗口内——现行可引"]
    return gate


def _status_from_gate(gate: dict) -> str:
    """B7 闸决策→状态映射（decision/code/status 三层分立，只落八状态词）。

    词面序按规格 §3.1 条 3：链内后继（修订标签）→已修订（replacement
    具名）；非链同名更新版→替代（B8，提示有新版）；墓碑无更新→已废止；
    其余有限到期→已失效。ABOLISHED+更新版→替代（B7 原序）。
    """
    if gate["decision"] == "ALLOWED":
        return STATUS_CURRENT
    code = gate["code"]
    if code == "ABOLISHED_NOT_CITABLE":
        return STATUS_SUPERSEDED if gate["newer_exists"] else STATUS_ABOLISHED
    if code == "SUPERSEDED_NOT_CITABLE":
        if gate["label"] == "已修订":  # §3.1 条 3：链内后继=修订标签，词面优先
            return STATUS_AMENDED
        if gate["newer_exists"]:
            return STATUS_SUPERSEDED
        if gate["label"] == "已失效":
            return STATUS_EXPIRED
        return STATUS_EXPIRED
    # NOT_YET_IN_FORCE / STATUS_UNKNOWN：fail-closed 未知，不签任何现行
    return STATUS_UNKNOWN


def _resolve_version(pack: CitationPack, title: str, as_of_num: int) -> dict:
    """标题→唯一版本行（B5/B6；同名多版本恰一可引定版，并列/全无→未知）。"""
    rows = pack.find_by_title(title)
    if not rows:
        return {"rows": [], "chosen": None, "gate": None, "ambiguous": False}
    if len(rows) == 1:
        # B6 单版本标题无可言歧义：唯一行即所引版本（时点判定交闸）
        chosen = rows[0]
        return {"rows": rows, "chosen": chosen, "gate": _gate_row(chosen, rows, as_of_num),
                "ambiguous": False}
    gates = {r["id"]: _gate_row(r, rows, as_of_num) for r in rows}
    allowed = [r for r in rows if gates[r["id"]]["decision"] == "ALLOWED"]
    if len(allowed) == 1:
        chosen = allowed[0]
    elif len(allowed) > 1:  # D3 同名同窗双版本=缺口→未知
        return {"rows": rows, "chosen": None, "gate": None, "ambiguous": True}
    else:
        # 零可引：取已施行（valid_from 空值按已施行消费）且未到期的链尾版
        # （publish 最大且唯一；§3.1 条 4 已声明键偏离）
        eligible = []
        for r in rows:
            vf = _parse_pack_date(r["valid_from"])
            if vf == _GAP:
                continue  # 格式坏行不参与定版（无法建立已施行事实）
            if vf is None or vf <= as_of_num:
                eligible.append(r)
        if not eligible:
            return {"rows": rows, "chosen": None, "gate": None, "ambiguous": True}
        tail_pub = max(_publish_num(r) for r in eligible)
        tied = [r for r in eligible if _publish_num(r) == tail_pub]
        if len(tied) != 1:
            return {"rows": rows, "chosen": None, "gate": None, "ambiguous": True}
        chosen = tied[0]
    return {"rows": rows, "chosen": chosen, "gate": gates[chosen["id"]],
            "ambiguous": False}


# ---------------------------------------------------------------------- #
# 支持核验＋引用回读（B9-B12；与冻结 _support_check 逐行为等量）
# ---------------------------------------------------------------------- #

def _support_check(pack: CitationPack, parsed: dict, chosen_row) -> dict:
    support = {
        "article_located": False,
        "article_text": None,
        "quote_in_article": None,
        "quote_in_document": None,
        "text_carrier": None,
    }
    if chosen_row is None:
        return support
    markdown_text = pack.read_content(chosen_row["filename"])
    if markdown_text is None:
        return support
    support["text_carrier"] = chosen_row["filename"]  # 包内相对载体路径（B12）
    articles = split_articles(markdown_text)
    normalized_doc = _strip_decorations(markdown_text)
    if parsed.get("article_number") is None:
        # 无条文引用：文档级载体在位即回读，定位停在标题级
        support["document_text_present"] = True
        return support
    key = str(parsed["article_number"]) + (
        "之" + parsed["article_sub"] if parsed.get("article_sub") else "")
    article = articles.get(key)
    if article is None:
        return support
    support["article_located"] = True
    support["article_text"] = article["text"].strip()
    if not parsed.get("quote"):
        return support
    support["quote_in_article"] = (_strip_decorations(parsed["quote"])
                                   in _strip_decorations(article["text"]))
    support["quote_in_document"] = (_strip_decorations(parsed["quote"])
                                    in normalized_doc)
    return support


# ---------------------------------------------------------------------- #
# 单条核验（B1-B16）
# ---------------------------------------------------------------------- #

def verify_citation(parsed: dict, pack=None, pack_dir=None) -> dict:
    """单条引用核验。返回逐条范围记账记录（B 全段字段）。"""
    as_of = parsed.get("as_of")
    if as_of is None:  # B1 缺时点不默认任何时点（先于数据面）
        raise NotConnected("citation_as_of_required_fail_closed")
    if not isinstance(as_of, str) or not re.match(r"^\d{8}$", as_of):  # B2 形态闸
        raise NotConnected("citation_as_of_must_be_yyyymmdd")
    title = parsed.get("title")
    if not isinstance(title, str) or not title:
        raise NotConnected("citation_title_required")
    if pack is None:
        pack = CitationPack(pack_dir)
    as_of_num = _as_of_num(as_of)

    record = {
        "citation_text": parsed.get("citation_text"),
        "title": title,
        "article_ref": parsed.get("article_ref"),
        "article_number": parsed.get("article_number"),
        "quote": parsed.get("quote"),
        "identifier": None,
        "status": STATUS_UNKNOWN,
        "decision": None,
        "code": None,
        "reasons": [],
        "scope": [],
        "verified_scoped": False,
        "support": None,
        "replacement": None,
        "replacement_reason": "",
        "degradation": None,
    }

    resolution = _resolve_version(pack, title, as_of_num)
    rows = resolution["rows"]
    if not rows:
        # B4/D6 本地包未命中：虚构＋覆盖缺口声明＋self_collection=none＋零 URL
        record["status"] = STATUS_FABRICATED
        record["code"] = "PACK_TITLE_MISS"
        record["reasons"] = [
            "本地法条包标题精确匹配未命中（%s，laws=%d）" % (pack.meta_name, pack.law_count),
            "本地未命中≠全局不存在；付费/web 段为声明缺口，不据此自采、不编造",
        ]
        record["degradation"] = _degradation(["PACK_TITLE_MISS"])
        record["scope"] = ["title_lookup:pack_exact_miss"]
        record["verified_scoped"] = False
        return record

    if resolution["ambiguous"]:
        record["code"] = "VERSION_UNRESOLVED_FAIL_CLOSED"
        record["reasons"] = ["多版本且无可引版本/施行时点不可定——不猜版本"]
        record["scope"] = ["title_lookup:hit", "version_resolution:ambiguous"]
        record["verified_scoped"] = False
        return record

    chosen = resolution["chosen"]
    gate = resolution["gate"]
    record["identifier"] = chosen["id"]
    record["decision"] = gate["decision"]
    record["code"] = gate["code"]
    record["reasons"] = list(gate["reasons"])
    record["replacement"] = gate["replacement"]
    record["replacement_reason"] = gate["replacement_reason"]

    status = _status_from_gate(gate)
    support = _support_check(pack, parsed, chosen)

    # B10/B11 误引只在可引（现行）版本判定；其余状态如实记定位事实
    if status == STATUS_CURRENT:
        scope = ["title_lookup:hit", "version:resolved",
                 "effect:%s" % gate["code"]]
        if parsed.get("article_number") is not None:
            if not support["article_located"]:
                status = STATUS_MISCITED
                record["code"] = "ARTICLE_NOT_IN_REAL_TEXT"
                record["reasons"].append(
                    "真实取文定位失败：包内正文无此条文号（或无文本载体）——引用条文不存在于真实文本，判误引")
            elif parsed.get("quote"):
                if support["quote_in_article"]:
                    scope.append("quote:supported_in_located_article")
                else:
                    status = STATUS_MISCITED
                    record["code"] = ("QUOTE_MISATTRIBUTED"
                                      if support["quote_in_document"]
                                      else "QUOTE_NOT_IN_REAL_TEXT")
                    record["reasons"].append(
                        "引文不在所引条文真实正文中"
                        + ("（存在于同法文中他处＝张冠李戴）" if support["quote_in_document"]
                           else "（同法全文亦无＝伪引文）"))
        record["scope"] = scope
    else:
        record["scope"] = ["title_lookup:hit", "version:resolved",
                           "effect:%s" % gate["code"],
                           "support_check:not_applicable_non_citable"]

    record["status"] = status
    record["support"] = support
    # B13 三块与（冻结判定式等量）：状态=现行 ∧（无条文号∨定位成功）∧（无引文∨引文在条文内）
    record["verified_scoped"] = (
        status == STATUS_CURRENT
        and (parsed.get("article_number") is None
             or support["article_located"])
        and (not parsed.get("quote")
             or support["quote_in_article"] is True)
    )
    return record


# ---------------------------------------------------------------------- #
# 全文逐条记账（C1-C5）
# ---------------------------------------------------------------------- #

def verify_document(text, as_of, pack_dir) -> dict:
    """全文所有引用逐条范围记账。无文档级 PASS 笼统结论（C4）。"""
    if not isinstance(text, str) or not text:  # C5 缺失或空串同码同拒
        raise NotConnected("citation_document_text_required")
    if as_of is None:
        raise NotConnected("citation_as_of_required_fail_closed")
    if not isinstance(as_of, str) or not re.match(r"^\d{8}$", as_of):
        raise NotConnected("citation_as_of_must_be_yyyymmdd")
    if len(text) > DOCUMENT_MAX_CHARS:  # A17 体量边界：具名拒不静默截断
        raise NotConnected("citation_document_too_large")
    pack = CitationPack(pack_dir)
    try:
        parsed_items = parse_citations(text)
        records = []
        for index, parsed in enumerate(parsed_items):  # C1 每引用独立记账
            parsed = dict(parsed)
            parsed["as_of"] = as_of
            record = verify_citation(parsed, pack=pack)
            record["index"] = index
            record["span"] = parsed["span"]
            records.append(record)
    finally:
        pack.close()
    by_status: dict = {}
    for record in records:
        by_status[record["status"]] = by_status.get(record["status"], 0) + 1
    summary = {
        "total": len(records),
        "by_status": by_status,
        "not_fully_verifiable_statuses": list(NEVER_FULLY_VERIFIED),
        "accounting": "per_citation_scoped",
        "note": "逐条范围记账——不产文档级笼统结论；虚构/失效/误引任一在册即该条不标全核",
        "data_face": FACE_NAME,
        "source_chain": list(SOURCE_CHAIN),
    }
    return {"citations": records, "summary": summary}


# ---------------------------------------------------------------------- #
# 冻结方法组分发（F1：恰三方法，未列具名拒）
# ---------------------------------------------------------------------- #

def citation_call(method: str, args: dict) -> dict:
    if method == "citation.parse":  # 零数据面：解析不触包
        return {"citations": parse_citations(args.get("text"))}
    if method == "citation.verify":
        citation = args.get("citation")
        if not isinstance(citation, str) or not citation.strip():
            raise NotConnected("citation_text_required")
        parsed_items = parse_citations(citation)
        if len(parsed_items) != 1:  # B3 非恰一条具名拒并回报实际条数
            raise NotConnected(
                "citation_exactly_one_expected_got:%d" % len(parsed_items))
        parsed = dict(parsed_items[0])
        parsed["as_of"] = args.get("as_of")
        return verify_citation(parsed, pack_dir=args.get("pack_dir"))
    if method == "citation.verify_document":
        return verify_document(args.get("text"), args.get("as_of"),
                               args.get("pack_dir"))
    raise NotConnected("method_not_connected:" + method)


# ---------------------------------------------------------------------- #
# CLI：temp JSON 进、JSON 出（exit 0=OWNER_RESPONSE / exit 3=NOT_CONNECTED）
# ---------------------------------------------------------------------- #

def main(argv: list) -> int:
    if len(argv) != 3:
        print(json.dumps({"status": "NOT_CONNECTED",
                          "code": "usage_method_and_request_file_required"},
                         ensure_ascii=False))
        return 3
    method, req_path = argv[1], argv[2]
    try:
        with open(req_path, "r", encoding="utf-8") as fh:  # 只读
            args = json.load(fh)
    except Exception:
        print(json.dumps({"status": "NOT_CONNECTED", "code": "request_not_json"},
                         ensure_ascii=False))
        return 3
    if not isinstance(args, dict):
        print(json.dumps({"status": "NOT_CONNECTED", "code": "request_not_json"},
                         ensure_ascii=False))
        return 3
    try:
        result = citation_call(method, args)
    except NotConnected as exc:
        print(json.dumps({"status": "NOT_CONNECTED", "code": str(exc)},
                         ensure_ascii=False))
        return 3
    print(json.dumps({"status": "OWNER_RESPONSE", "business_complete": False,
                      "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
