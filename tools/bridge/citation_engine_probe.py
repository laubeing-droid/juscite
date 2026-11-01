# -*- coding: utf-8 -*-
"""#14 引证核验·引擎合成自测探针（RE-14 §3.5 施工随件，件2）。

全合成材料（合成法条包+合成文本），不依赖真实法条内容正确性（规格 §5：
轻量包文本正确性不在验收范围）。覆盖：
  - 解析针组 P1-P15＋P3b/P3c/P5b/P11b＋A11/A16（§2-A 全部确定性边界）；
  - 单条 12 态针（虚构/伪引文/张冠李戴/条文号不存在/已废止/已修订/失效/
    替代/同名现行/尚未施行/多版本不可定/真引文全过）＋36a 空值语义针＋
    36b 交接日针＋格式坏针（§3.1 条 1-4）；
  - 全文记账 6 引用 6 状态针＋C4 结构断言＋C2 同法互不覆盖＋G14 零引用针；
  - S5 fail-closed 针（缺包/缺 as_of/未知方法/缺 text/7 位残形/8 位假日期
    过闸/体量超限/恰一条数）＋B15 反例三拒＋F2 出口码合同；
  - AST 零网络/零写/零模型扫描针（F3，recon S3E 同款纪律）。

用法：python -X utf8 tools/bridge/citation_engine_probe.py
单命令 exit 0/1，末行 CITATION_ENGINE_PROBE_PASS 可判。
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(HERE, "..", "..", "implementation", "python",
                      "citation_verify_lite.py")
ENGINE = os.path.normpath(ENGINE)
sys.path.insert(0, os.path.dirname(ENGINE))
import citation_verify_lite as cv  # noqa: E402  （解析针直调；CLI 针走子进程）

PASS = 0
FAIL = 0


def ok(n, msg):
    global PASS
    PASS += 1
    print("[citation-engine-probe] %d: OK %s" % (n, msg))


def fail(n, msg, detail=""):
    global FAIL
    FAIL += 1
    print("[citation-engine-probe] %d: FAIL %s%s" % (n, msg, ("\n  " + str(detail)) if detail else ""))


def check(n, cond, msg, detail=""):
    if cond:
        ok(n, msg)
    else:
        fail(n, msg, detail)


def run_engine(method, payload):
    """子进程一次性：temp JSON 进、JSON 出（与桥同纪律，F2 出口码合同）。"""
    req = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                      encoding="utf-8")
    json.dump(payload, req, ensure_ascii=False)
    req.close()
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", ENGINE, method, req.name],
            capture_output=True, timeout=120)
        out = proc.stdout.decode("utf-8", "replace").strip()
        try:
            envelope = json.loads(out)
        except Exception:
            envelope = None
        return proc.returncode, envelope, out, proc.stderr.decode("utf-8", "replace")
    finally:
        try:
            os.unlink(req.name)
        except OSError:
            pass


# ---------------------------------------------------------------------- #
# 合成法条包（temp；pack.meta 四字段齐；content md 全部合成文本）
# ---------------------------------------------------------------------- #

def build_synthetic_pack(root):
    laws = [
        # (id, name, publish, valid_from, valid_to, ver, filename)
        ("a1", "甲法", "2000-01-01", "", "2099-12-31", 1, "甲法.md"),
        ("f1", "废止法", "1990-01-01", "1990-01-01", "1970-01-01", 1, "废止法.md"),
        ("c1", "链修订法", "2010-01-01", "2010-01-01", "2020-01-01", 2, "链修订法(2010).md"),
        ("c2", "链修订法", "2019-06-01", "2020-01-01", "2099-12-31", 2, "链修订法(2019).md"),
        ("e1", "失效法", "2000-01-01", "2000-01-01", "2015-06-30", 1, "失效法.md"),
        ("n1", "未施行法", "2026-01-01", "2099-06-01", "2099-12-31", 1, "未施行法.md"),
        ("w1", "双窗法", "2001-01-01", "2001-01-01", "2099-12-31", 1, "双窗法.md"),
        ("w2", "双窗法", "2002-01-01", "2002-01-01", "2099-12-31", 1, "双窗法.md"),
        ("l1", "松更新法", "2005-01-01", "2000-01-01", "2010-01-01", 2, "松更新法(2005).md"),
        ("l2", "松更新法", "2012-05-01", "2012-01-01", "2099-12-31", 2, "松更新法(2012).md"),
        ("g1", "格式坏法", "2020-01-01", "2020年生效", "2099-12-31", 1, "格式坏法.md"),
        ("m1", "空施法", "2001-01-01", "", "2099-12-31", 1, "空施法.md"),
        ("h1", "交接法", "2015-01-01", "2015-01-01", "2020-01-01", 2, "交接法(2015).md"),
        ("h2", "交接法", "2019-12-01", "2020-01-01", "2099-12-31", 2, "交接法(2019).md"),
    ]
    contents = {
        "甲法.md": "# 甲法\n\n2000年1月1日 合成通过\n\n<!-- INFO END -->\n\n"
                   "第一条 合成甲法第一条正文，供引文支持核验的锚句在此：青山不改水长流。\n\n"
                   "第二条 合成甲法第二条正文，张冠李戴针的引文取自本条：绿水长流山又青。\n\n"
                   "第三条 合成甲法第三条正文。\n",
        "废止法.md": "# 废止法\n\n<!-- INFO END -->\n\n第一条 已废止法律合成正文。\n",
        "链修订法(2010).md": "# 链修订法\n\n<!-- INFO END -->\n\n第一条 二零一零版合成正文（旧版）。\n",
        "链修订法(2019).md": "# 链修订法\n\n<!-- INFO END -->\n\n第一条 二零一九版合成正文（新版）。\n",
        "失效法.md": "# 失效法\n\n<!-- INFO END -->\n\n第一条 已失效法律合成正文。\n",
        "未施行法.md": "# 未施行法\n\n<!-- INFO END -->\n\n第一条 尚未施行的合成正文。\n",
        "双窗法.md": "# 双窗法\n\n<!-- INFO END -->\n\n第一条 同窗冲突合成正文。\n",
        "松更新法(2005).md": "# 松更新法\n\n<!-- INFO END -->\n\n第一条 松更新旧版合成正文。\n",
        "松更新法(2012).md": "# 松更新法\n\n<!-- INFO END -->\n\n第一条 松更新新版合成正文。\n",
        "格式坏法.md": "# 格式坏法\n\n<!-- INFO END -->\n\n第一条 格式坏合成正文。\n",
        "空施法.md": "# 空施法\n\n<!-- INFO END -->\n\n第一条 空施行日合成正文。\n",
        "交接法(2015).md": "# 交接法\n\n<!-- INFO END -->\n\n第一条 交接旧版合成正文。\n",
        "交接法(2019).md": "# 交接法\n\n<!-- INFO END -->\n\n第一条 交接新版合成正文。\n",
    }
    os.makedirs(os.path.join(root, "content"), exist_ok=True)
    db = sqlite3.connect(os.path.join(root, "pack.sqlite3"))
    db.execute("CREATE TABLE law (id TEXT PRIMARY KEY, name TEXT NOT NULL, subtitle TEXT,"
               " level TEXT NOT NULL, category_id TEXT, publish TEXT, valid_from TEXT DEFAULT '',"
               " valid_to TEXT DEFAULT '2099-12-31', ver INTEGER NOT NULL DEFAULT 1,"
               " tags TEXT NOT NULL DEFAULT '[]', filename TEXT NOT NULL,"
               " order_num INTEGER NOT NULL DEFAULT 0)")
    db.execute("CREATE TABLE category (id TEXT PRIMARY KEY, name TEXT NOT NULL, folder TEXT,"
               " is_subfolder INTEGER NOT NULL DEFAULT 0, \"group\" TEXT,"
               " sort_order INTEGER NOT NULL DEFAULT 0)")
    for row in laws:
        db.execute("INSERT INTO law (id, name, level, publish, valid_from, valid_to, ver,"
                   " filename) VALUES (?,?,?,?,?,?,?,?)",
                   (row[0], row[1], "法律", row[2], row[3], row[4], row[5], row[6]))
    db.commit()
    db.close()
    for name, text in contents.items():
        with open(os.path.join(root, "content", name), "w", encoding="utf-8") as fh:
            fh.write(text)
    with open(os.path.join(root, "pack.meta"), "w", encoding="utf-8") as fh:
        json.dump({"name": "synthetic-probe", "hash": "0" * 64, "update": 0,
                   "filesize": 4096}, fh, ensure_ascii=False)


def verify_one(citation, as_of, pack_dir):
    code, env, out, err = run_engine("citation.verify", {
        "citation": citation, "as_of": as_of, "pack_dir": pack_dir})
    return code, env


# ---------------------------------------------------------------------- #
# 探针主体
# ---------------------------------------------------------------------- #

def main() -> int:
    n = 0
    if not os.path.isfile(ENGINE):
        print("[citation-engine-probe] engine missing: %s" % ENGINE)
        return 1

    # ── 解析针组（直调纯函数；§1.4-2 同集＋历轮增补边界）──
    r = cv.parse_citations("《甲法》第一千二百六十条")
    n += 1
    check(n, r and r[0]["article_number"] == 1260, "P1 中文数字千位（一千二百六十=1260）", r)
    r = cv.parse_citations("参照《甲法》的规定处理")
    n += 1
    check(n, len(r) == 1 and r[0]["article_number"] is None and r[0]["title"] == "甲法",
          "P2 标题级引用成条（无条文）", r)
    r = cv.parse_citations("《甲法》第三条第二款")
    n += 1
    check(n, r[0]["article_number"] == 3 and r[0]["subrefs"] == "第二款",
          "P3 款项跟随（连续并入原文保留）", r)
    r = cv.parse_citations("《甲法》第三条第3款")
    n += 1
    check(n, r[0]["subrefs"] == "第3款", "P3c 款项数字中英皆收（A3 显式对照）", r)
    r = cv.parse_citations("《甲法》第三条、第四款")
    n += 1
    check(n, r[0]["subrefs"] == "" and r[0]["article_number"] == 3,
          "P3b 顿号非连续款项不并入（确定性不猜）", r)
    r = cv.parse_citations("《刑法》第一百八十六条之一")
    n += 1
    check(n, r[0]["article_number"] == 186 and r[0]["article_sub"] == "一",
          "P4 之一子条", r)
    r = cv.parse_citations("《甲法》第一条“引文里有句号。还有分号；都不断段。”")
    n += 1
    check(n, r[0]["quote"] == "引文里有句号。还有分号；都不断段。",
          "P5 引文内句号/分号不断段", r)
    text_p5b = "《甲法》第一条“引《乙条例》第二条之句。”"
    r = cv.parse_citations(text_p5b)
    n += 1
    # 冻结等量形态（第 9 轮 P5b 实测原话）：外层甲法·第一条携完整引文＋
    # 外层段内第二条（引文内条文号被条文正则独立捕获，同锚另成记录）＋
    # 嵌套《乙条例》第二条独立成条（quote=None）——三层并存核验覆盖只增不减。
    check(n, len(r) == 3
          and r[0]["title"] == "甲法" and r[0]["article_number"] == 1
          and r[0]["quote"] == "引《乙条例》第二条之句。"
          and r[1]["title"] == "甲法" and r[1]["article_number"] == 2
          and r[1]["quote"] is None
          and r[2]["title"] == "乙条例" and r[2]["article_number"] == 2
          and r[2]["quote"] is None,
          "P5b 引文内书名号不断段且独立成锚（3 记录形态，冻结等量）", json.dumps(r, ensure_ascii=False))
    r = cv.parse_citations("《甲法》第一条“未闭合引文")
    n += 1
    check(n, r[0]["quote"] is None, "P6/A5 引号未闭合 quote=None 不猜", r)
    r = cv.parse_citations("《甲法》第123条")
    n += 1
    check(n, len(r) == 1 and r[0]["article_number"] is None,
          "P7/A8 ASCII 条文号不识别→降级标题级", r)
    r = cv.parse_citations("《甲法》第一条、第三条都有引文“共引”。")
    n += 1
    check(n, len(r) == 2 and r[0]["quote"] == "共引" and r[1]["quote"] is None,
          "P8/A6 同段多条文引文只归首条", r)
    text_span = "前缀《甲法》第三条后缀"
    r = cv.parse_citations(text_span)
    n += 1
    check(n, r[0]["span"] == [2, 9]
          and text_span[r[0]["span"][0]:r[0]["span"][1]] == r[0]["citation_text"],
          "P9/A9 span 码点口径＋原文回切真", (r[0]["span"], r[0]["citation_text"]))
    b1 = json.dumps(cv.parse_citations("《甲法》第二条《乙法》第一条"), ensure_ascii=False)
    b2 = json.dumps(cv.parse_citations("《甲法》第二条《乙法》第一条"), ensure_ascii=False)
    n += 1
    check(n, b1 == b2, "P10/P15/A10 同输入 JSON 字节级一致（确定性）")
    md = ("---\ntitle: x\n---\n# 章\n\n- **第一条** 装饰条文起点。\n  续行并入。\n\n"
          "## 第二章\n\n第二条 章节截断前最后一条。\n")
    arts = cv.split_articles(md)
    n += 1
    check(n, "1" in arts and "2" in arts and "装饰条文起点。" in arts["1"]["text"]
          and "续行并入" in arts["1"]["text"]
          and "第二章" not in arts["2"]["text"],
          "P11/A15 md 切分（frontmatter/装饰/续行/章节截断）", list(arts))
    n += 1
    check(n, cv.split_articles("") == {}, "P11b 切分空输入返回空（不猜）")
    n += 1
    check(n, cv._strip_decorations("- **第一条**\t正文#注") == "第一条正文注",
          "P12 装饰剥离（只删承载装饰）")
    n += 1
    check(n, cv.parse_citations("") == [] and cv.parse_citations(None) == []
          and cv.parse_citations(123) == [],
          "P13/A11 空输入/非字符串→空列表（不抛不猜）")
    r = cv.parse_citations("《甲法》 第一条")
    n += 1
    check(n, r[0]["article_number"] == 1, "P14/A14 书名号与条文号间空白容忍", r)
    long_title = "《" + "甲" * 121 + "》第一条"
    n += 1
    check(n, cv.parse_citations(long_title) == [],
          "A16 标题超 120 字不成锚（不截断不猜）")
    n += 1
    check(n, cv.parse_citations("《》第一条") == [], "A16 空书名号不成锚")

    # ── 合成包 ──
    pack_root = tempfile.mkdtemp(prefix="juscite-cite-probe-")
    try:
        build_synthetic_pack(pack_root)

        # 单条 12 态针（子进程 CLI 径：F2 出口码＋信封实形同步验收）
        code, env = verify_one("《甲法》第一条“青山不改水长流。”", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, code == 0 and env and env["status"] == "OWNER_RESPONSE"
              and env["business_complete"] is False and res
              and res["status"] == "现行" and res["code"] == "CURRENT_IN_FORCE_CITABLE"
              and res["verified_scoped"] is True
              and (res["support"] or {}).get("article_located") is True
              and "青山不改水长流" in (res["support"] or {}).get("article_text", "")
              and (res["support"] or {}).get("text_carrier") == "甲法.md",
              "态1 真引文全过（现行＋定位＋引文在条文＋回读）", json.dumps(env, ensure_ascii=False)[:300])
        code, env = verify_one("《甲法》", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "现行" and res["verified_scoped"] is True
              and (res["support"] or {}).get("article_located") is False,
              "态2 同名现行（标题级，定位停标题层）", res and res["status"])
        code, env = verify_one("《甲法》第九百九十九条", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "误引" and res["code"] == "ARTICLE_NOT_IN_REAL_TEXT"
              and res["verified_scoped"] is False,
              "态3 条文号不存在→误引（B9 具名码）", res and res["code"])
        code, env = verify_one("《甲法》第一条“此句全文不存在。”", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "误引" and res["code"] == "QUOTE_NOT_IN_REAL_TEXT",
              "态4 伪引文→误引（B10 具名码）", res and res["code"])
        code, env = verify_one("《甲法》第一条“绿水长流山又青。”", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "误引" and res["code"] == "QUOTE_MISATTRIBUTED"
              and (res["support"] or {}).get("quote_in_document") is True,
              "态5 张冠李戴（引文在文中他处）", res and res["code"])
        code, env = verify_one("《废止法》第一条", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "已废止" and res["code"] == "ABOLISHED_NOT_CITABLE"
              and res["decision"] == "BLOCKED" and res["verified_scoped"] is False
              and res["support"] and res["support"]["article_located"] is True,
              "态6 已废止（墓碑；不可引版仍如实回读定位事实 B11）",
              json.dumps(res, ensure_ascii=False)[:200])
        # 已修订：链内后继闸级针。结构性说明——良构链下解析定版永不选中链中已废
        # 旧版（旧版失效日=新版施行日，旧版到期 ⟺ 新版可引，恰一 ALLOWED 即新版；
        # 交接日语义同日引新版），故该词面经闸/映射真函数＋合成行验收（数据与
        # 判定全真，仅不经端到端定版，不冒端到端）。
        rows = cv.CitationPack(pack_root).find_by_title("链修订法")
        as_of_num = cv._as_of_num("20210101")
        gate = cv._gate_row(rows[0], rows, as_of_num)
        n += 1
        check(n, gate["code"] == "SUPERSEDED_NOT_CITABLE" and gate["label"] == "已修订"
              and gate["has_successor"] is True
              and gate["replacement"] == "《链修订法》（施行日 2020-01-01）"
              and cv._status_from_gate(gate) == "已修订"
              and cv._gate_row(rows[1], rows, as_of_num)["decision"] == "ALLOWED",
              "态7 已修订（链内后继＋replacement 具名；B7 三层分立）",
              json.dumps(gate, ensure_ascii=False))
        code, env = verify_one("《失效法》第一条", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "失效" and res["code"] == "SUPERSEDED_NOT_CITABLE"
              and res["replacement"] == "unknown" and res["replacement_reason"]
              and res["verified_scoped"] is False,
              "态8 失效（有限到期；36e 词面局限＋D4 replacement unknown 具名）",
              res and res["replacement_reason"])
        code, env = verify_one("《松更新法》第一条", "20110601", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "替代"
              and res["code"] == "SUPERSEDED_NOT_CITABLE",
              "态9 替代（非链同名更新版在库，B8）", res and res["status"])
        code, env = verify_one("《链修订法》第一条", "20150601", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "现行" and res["identifier"] == "c1",
              "态10 同名现行（时点回到旧版窗口→旧版即所引版本 B6）",
              (res or {}).get("identifier"))
        code, env = verify_one("《未施行法》第一条", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "未知" and res["decision"] == "BLOCKED"
              and res["code"] == "NOT_YET_IN_FORCE_AT_AS_OF",
              "态11 尚未施行→未知（38a 三层分立不造第九词）",
              json.dumps(res, ensure_ascii=False)[:160])
        code, env = verify_one("《双窗法》第一条", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "未知"
              and res["code"] == "VERSION_UNRESOLVED_FAIL_CLOSED",
              "态12 多版本同窗不可定→未知（D3 不签现行）", res and res["code"])
        # 36a 空值语义针
        code, env = verify_one("《空施法》第一条", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "现行",
              "36a valid_from 空＝已施行消费（不判未知）", res and res["status"])
        code, env = verify_one("《格式坏法》第一条", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "未知"
              and res["code"] == "STATUS_UNKNOWN_FAIL_CLOSED",
              "36a 格式坏＝缺口→未知不签现行（D3 收窄定义）", res and res["code"])
        # 36b 交接日针
        code, env = verify_one("《交接法》第一条", "20200101", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, res and res["status"] == "现行" and res["identifier"] == "h2",
              "36b 交接日当天旧废新行、同日引新版（窗口端点自动导出）",
              (res or {}).get("identifier"))
        # B2/S5F 8 位假日期过形态闸进窗口比较（确定性结果）
        code, env = verify_one("《甲法》", "20261332", pack_root)
        n += 1
        res = env.get("result") if env else None
        check(n, code == 0 and res and res["status"] == "现行",
              "S5F 8 位假日期 20261332 过形态闸（不验日历，窗口比较确定性）",
              json.dumps(env, ensure_ascii=False)[:160])
        # D6 覆盖声明针
        code, env = verify_one("《不存在法》第一条", "20261028", pack_root)
        n += 1
        res = env.get("result") if env else None
        cov = (res or {}).get("degradation") and res or None
        check(n, res and res["status"] == "虚构" and res["code"] == "PACK_TITLE_MISS"
              and res["verified_scoped"] is False
              and res["degradation"] and res["degradation"]["escalated"] is False
              and res["degradation"]["chain"] == ["local", "paid", "web"],
              "B4/D6 虚构＋覆盖缺口声明＋零跳级（E1）", res and res["code"])
        n += 1
        check(n, cov is not None and cov["scope"] == ["title_lookup:pack_exact_miss"],
              "B4 scope 记账（title_lookup 段）", (res or {}).get("scope"))
        # E4 零 URL 披露（虚构记录全序列化不含 http 字样）
        n += 1
        check(n, "http" not in json.dumps(res, ensure_ascii=False).lower(),
              "E4 虚构/缺口记录零 URL 披露")

        # 全文记账针：6 引用 6 状态＋C2 同法互不覆盖＋C4 结构断言
        doc_text = ("依据《甲法》第一条。另见《甲法》第九百九十九条。《废止法》第一条"
                    "《未施行法》第一条《不存在法》第一条《双窗法》第一条均不引。")
        code, env, _out, _err = run_engine("citation.verify_document", {
            "text": doc_text, "as_of": "20261028", "pack_dir": pack_root})
        res = env.get("result") if env else None
        cites = (res or {}).get("citations") or []
        summary = (res or {}).get("summary") or {}
        n += 1
        check(n, code == 0 and len(cites) == 6
              and [c["index"] for c in cites] == [0, 1, 2, 3, 4, 5],
              "C1 全文逐条独立记账（index 一一对应）", summary.get("by_status"))
        st = [c["status"] for c in cites]
        n += 1
        check(n, st == ["现行", "误引", "已废止", "未知", "虚构", "未知"],
              "C2 六引用六状态并存互不覆盖（同法两条亦然）", st)
        n += 1
        check(n, all(k not in summary for k in
                     ("document_pass", "all_verified", "overall", "pass")),
              "C4 无文档级 PASS 笼统字段（好坏文档均无）", list(summary))
        n += 1
        check(n, summary.get("accounting") == "per_citation_scoped"
              and summary.get("total") == 6
              and summary.get("not_fully_verifiable_statuses")
              == list(cv.NEVER_FULLY_VERIFIED)
              and isinstance(summary.get("by_status"), dict),
              "C3 summary 仅计数与缺口声明形态", json.dumps(summary, ensure_ascii=False)[:200])
        n += 1
        check(n, all(c["verified_scoped"] is False for c in cites
                     if c["status"] in cv.NEVER_FULLY_VERIFIED),
              "B15 反例三拒（虚构/失效/误引 verified_scoped 恒 False）",
              [(c["status"], c["verified_scoped"]) for c in cites])
        # G14 零引用针（有包、无引用文本）
        code, env, _o, _e = run_engine("citation.verify_document", {
            "text": "本段完全没有任何书名号引用。", "as_of": "20261028",
            "pack_dir": pack_root})
        res = env.get("result") if env else None
        n += 1
        check(n, code == 0 and res and res["citations"] == []
              and res["summary"]["total"] == 0
              and res["summary"]["accounting"] == "per_citation_scoped",
              "G14/38g 零引用：exit 0＋citations=[]＋total=0（与预执行空态分立的引擎事实）",
              json.dumps(env, ensure_ascii=False)[:200])

        # ── S5 fail-closed 针（先于数据面；F2 出口码合同）──
        code, env = verify_one("《甲法》第一条", "20261028",
                               os.path.join(pack_root, "no-such-pack"))
        n += 1
        check(n, code == 3 and env and env["status"] == "NOT_CONNECTED"
              and env["code"] == "citation_pack_not_configured",
              "S5A 包未配置→exit 3 具名拒不静默降级（D5）", env)
        code, env, _o, _e = run_engine("citation.verify", {"citation": "《甲法》第一条",
                                                   "pack_dir": pack_root})
        n += 1
        check(n, code == 3 and env and env["code"] == "citation_as_of_required_fail_closed",
              "B1/S5A2 缺 as_of 先于数据面拒（不默认任何时点）", env)
        code, env, _o, _e = run_engine("citation.verify", {"citation": "《甲法》第一条"})
        n += 1
        check(n, code == 3 and env and env["code"] == "citation_as_of_required_fail_closed",
              "B1 包也缺时 as_of 码仍先行（校验序 C5/B1-B3）", env)
        code, env, _o, _e = run_engine("citation.check_all", {"text": "x", "as_of": "20261028",
                                                      "pack_dir": pack_root})
        n += 1
        check(n, code == 3 and env and env["code"] == "method_not_connected:citation.check_all",
              "S5B 未知方法具名拒（F1 未列不落）", env)
        code, env, _o, _e = run_engine("citation.verify_document", {"as_of": "20261028",
                                                            "pack_dir": pack_root})
        n += 1
        check(n, code == 3 and env and env["code"] == "citation_document_text_required",
              "S5C 缺 text 同码具名拒（C5）", env)
        code, env, _o, _e = run_engine("citation.verify_document", {"text": "", "as_of": "20261028",
                                                            "pack_dir": pack_root})
        n += 1
        check(n, code == 3 and env and env["code"] == "citation_document_text_required",
              "C5 空串与缺失同码同拒", env)
        code, env = verify_one("《甲法》第一条", "2026102", pack_root)
        n += 1
        check(n, code == 3 and env and env["code"] == "citation_as_of_must_be_yyyymmdd",
              "S5E 7 位残形先于数据面拒", env)
        code, env, _o, _e = run_engine("citation.verify_document", {
            "text": "字" * (cv.DOCUMENT_MAX_CHARS + 1), "as_of": "20261028",
            "pack_dir": pack_root})
        n += 1
        check(n, code == 3 and env and env["code"] == "citation_document_too_large",
              "A17 体量超限具名拒不静默截断", env)
        code, env = verify_one("全文没有引用。", "20261028", pack_root)
        n += 1
        check(n, code == 3 and env
              and env["code"] == "citation_exactly_one_expected_got:0",
              "B3 解析 0 条具名拒并回报实际条数", env)
        code, env = verify_one("《甲法》第一条《乙法》第二条", "20261028", pack_root)
        n += 1
        check(n, code == 3 and env
              and env["code"] == "citation_exactly_one_expected_got:2",
              "B3 解析 2 条具名拒并回报实际条数", env)
        # D：parse 零数据面成功（无 pack_dir）
        code, env, _o, _e = run_engine("citation.parse", {"text": "《甲法》第一条"})
        n += 1
        check(n, code == 0 and env and env["status"] == "OWNER_RESPONSE"
              and env["result"]["citations"][0]["article_number"] == 1,
              "S5D parse 零数据面成功（OWNER_RESPONSE 信封实形）", env)

        # AST 零网络/零写/零模型扫描针（F3；recon S3E 同款）
        with open(ENGINE, "r", encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        imports = set()
        bad_open = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imports.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name == "open" and node.args:
                    mode_arg = None
                    if len(node.args) >= 2:
                        mode_arg = node.args[1]
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            mode_arg = kw.value
                    if mode_arg is not None and isinstance(mode_arg, ast.Constant) \
                            and isinstance(mode_arg.value, str) \
                            and any(ch in mode_arg.value for ch in ("w", "a", "+", "x")):
                        bad_open.append(getattr(node, "lineno", -1))
        allowed_imports = {"json", "os", "re", "sqlite3", "sys", "__future__"}
        n += 1
        check(n, imports <= allowed_imports,
              "F3 AST 零网络零模型 import（实得 %s）" % sorted(imports))
        n += 1
        check(n, not bad_open, "F3 AST 零写模式 open（行 %s）" % bad_open)
        n += 1
        check(n, not ({"random", "secrets"} & imports),
              "F3 AST 零随机源（无 random/secrets）")
        n += 1
        check(n, "socket" not in src and "urllib" not in src and "requests" not in src,
              "F3 源面零网络字样")
    finally:
        shutil.rmtree(pack_root, ignore_errors=True)

    print("[citation-engine-probe] PASS=%d FAIL=%d" % (PASS, FAIL))
    if FAIL:
        print("[citation-engine-probe] CITATION_ENGINE_PROBE_FAIL")
        return 1
    print("[citation-engine-probe] CITATION_ENGINE_PROBE_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
