# -*- coding: utf-8 -*-
"""G6 连接器·类案检索腿（施工波三轮 20261031 · 桥健①）。

真源=legal-cn-cases（lcr 公开 Store：examples 合成夹具种子库，全部为
【合成软件测试，非真实裁判】材料）；零网络零模型。CLI 与 citation_verify_lite
同纪律：子进程一次性，temp JSON 进、JSON 出，缺参具名拒不猜。

  python -X utf8 g6_case_search.py <request.json>
  request = {"db": "...", "fixtures_dir": "...", "query": "...",
             "cause_of_action": [...], "return_num": 6,
             "judge_date_after": "2024-07-01", "retry_no_cause": true}
  stdout  = {"status":"OK","result":{...}} exit 0
          | {"status":"NOT_CONNECTED","code":"..."}          exit 3

机制对拍锚（华宇元典 MCP readable 件 cn-case-retrieval-mcp/cn-yuandian-case-search，
机制等量、文案自写）：
  - return_num 缺省 6；
  - 0 结果重试一次：移除案由过滤＋return_num 扩至 10＋关键词泛化（去限定词）；
  - 输出行带 法院/案号/裁判日期/要点 字段位（合成夹具无法院/案号→null 如实标）；
  - 裁判日期下限过滤（元典=仅 2024-07-01 后民事案件；我方=参数化，缺省同日）。
差异（诚实）：lcr 命中不分级权威/普通（authority_status 恒 CASE_SOURCE_CANDIDATE，
检索结果是来源候选不是事实——lcr 铁律），无余额概念（本地库零成本）。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.environ.get("JUSCITE_G6_LCR_HOME", ""))


def not_connected(code: str) -> None:
    json.dump({"status": "NOT_CONNECTED", "code": code}, sys.stdout, ensure_ascii=False)
    sys.exit(3)


def load_request() -> dict:
    if len(sys.argv) != 2:
        not_connected("usage:g6_case_search.py <request.json>")
    try:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            body = json.load(f)
    except Exception:
        not_connected("request_not_json")
    if not isinstance(body, dict):
        not_connected("request_not_object")
    return body


def ensure_store(db_path: str, fixtures_dir: str):
    from lcr.store import Store  # noqa: PLC0415（延迟导入：缺 lcr 时具名拒而非启动崩）

    fresh = not os.path.exists(db_path)
    store = Store(db_path)
    if fresh:
        canon = os.path.join(fixtures_dir, "canonical.jsonl")
        cards = os.path.join(fixtures_dir, "cards.jsonl")
        if not (os.path.isfile(canon) and os.path.isfile(cards)):
            store.close()
            not_connected("lcr_fixtures_missing:" + fixtures_dir)
        store.ingest_jsonl(canon)
        with open(cards, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    store.put_card(json.loads(line))
    return store


def generalize(query: str) -> str:
    """0 结果重试的关键词泛化：去限定修饰，保留核心词（确定性，非模型）。"""
    drop = ("关于", "下列", "有关", "相应", "该", "上述", "被告", "原告", "案件", "纠纷")
    out = query
    for w in drop:
        out = out.replace(w, " ")
    return " ".join(out.split()) or query


def row_of(store, hit: dict) -> dict:
    """lcr 命中→对拍行形状（法院/案号 夹具缺位=null 如实标，不编造）。"""
    doc = None
    try:
        doc = store.source(hit["doc_id"])
    except Exception:
        doc = None
    return {
        "card_id": hit["card_id"],
        "doc_id": hit["doc_id"],
        "issue_type": hit.get("issue_type", ""),
        "summary": hit.get("summary", ""),
        "court": (doc or {}).get("court") if isinstance(doc, dict) else None,
        "case_number": (doc or {}).get("case_number") if isinstance(doc, dict) else None,
        "judge_date": (doc or {}).get("judge_date") if isinstance(doc, dict) else None,
        "cause": (doc or {}).get("cause") if isinstance(doc, dict) else None,
        "score": hit.get("score"),
        "authority_status": hit.get("authority_status", "CASE_SOURCE_CANDIDATE"),
    }


def search_once(store, query: str, causes, limit: int, after: str | None):
    res = store.search(query, None, limit)
    rows = []
    for hit in res.get("hits", []):
        row = row_of(store, hit)
        if causes and row["cause"] not in causes:
            continue
        if after and (row["judge_date"] or "") < after:
            continue
        rows.append(row)
    return res, rows


def main() -> None:
    body = load_request()
    db = body.get("db")
    fixtures = body.get("fixtures_dir")
    query = body.get("query")
    if not db or not fixtures:
        not_connected("db_and_fixtures_dir_required")
    if not isinstance(query, str) or not query.strip():
        not_connected("query_required")
    causes = body.get("cause_of_action") or []
    if not isinstance(causes, list):
        not_connected("cause_of_action_not_list")
    try:
        limit = int(body.get("return_num") or 6)
    except Exception:
        not_connected("return_num_not_int")
    limit = max(1, min(limit, 20))
    after = body.get("judge_date_after", "2024-07-01")
    retry_on_empty = body.get("retry_no_cause", True)

    try:
        store = ensure_store(db, fixtures)
    except Exception as e:  # lcr 缺失/夹具坏——具名拒，不吞
        not_connected("lcr_store_unavailable:" + str(e)[:120])
    try:
        res, rows = search_once(store, query, causes, limit, after)
        retried = False
        if not rows and retry_on_empty and causes:
            # 机制对拍：0 结果→移除案由过滤＋return_num 扩至 10＋关键词泛化，重试一次
            res, rows = search_once(store, generalize(query), [], max(limit, 10), after)
            retried = True
        result = {
            "schema": "juscite.g6.case_search/1",
            "query": query,
            "cause_filter": causes,
            "judge_date_after": after,
            "return_num": limit,
            "retried_no_cause": retried,
            "hits": rows,
            "hit_count": len(rows),
            "coverage": "lcr Store 合成夹具库（examples 全量两卡），非全量库",
            "authority_note": "命中不分级权威/普通，一律 CASE_SOURCE_CANDIDATE 来源候选",
            "vector_used": bool(res.get("vector_used")),
        }
        json.dump({"status": "OK", "result": result}, sys.stdout, ensure_ascii=False)
    finally:
        store.close()


if __name__ == "__main__":
    main()
