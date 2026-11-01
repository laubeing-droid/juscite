# -*- coding: utf-8 -*-
"""F73 用户自建知识库 RAG（W4-U43；06:F73 desktop/selfhost 双实例，B4）。

07/17 卡 F73（owner=manuals+product，entries P02/P04）：用户自建知识库
（经验文集/所内知识）按 授权/快照/出处 检索，质量评分与过期治理真实，
分案隔离不串案；步骤=固定内容 hash/权限→公开读取→实际任务消费→来源
回执和验证；不公开私域蒸馏。实现边界：

* 产品面引擎（本模块）：条目带 readScope（授权范围，三级闭集
  public/firm/private，与 manuals contracts READ_SCOPES 同名同序）＋
  entryDigest（内容快照 sha256，canonical JSON 全字段）＋sourceRefs
  （出处，C16 ref 形状 {owner,kind,id,version,matterId,digest}——检索
  命中可回溯源文档，refs 是数据，本引擎不解析其指向）。
* 授权在消费边界 fail-closed：public 恒可见；firm 须 authorizedReadScopes
  显式携带；private 任何形式都不可授权（传 private 进授权集＝具名拒），
  search 不命中、read 具名拒——不公开私域蒸馏的结构面（manuals
  「private 不出读侧白名单」同纪律）。
* 质量评分真实：qualityScore∈[0,1] 入快照；有效分＝relevance×
  (0.5+0.5×quality)×stalenessFactor，逐因子在命中分与回执中具名回显。
* 过期治理真实：lastVerified+freshnessWindowDays 过期（或未验证）→
  命中带 stale/staleReason 标记×降权 0.5，绝不静默混入；回执记 staleCount。
* 分案隔离：条目 matterId 绑案；检索只见 全局（无绑案）∪ 本案条目，
  跨案结构性不可见；绑案条目在全局检索中同样不可见。
* 向量底座＝接口级复用 F71 混合检索层：检索合同名 f71_hybrid/1，
  后端经注册表注入（config kb_backend）；06 prereq 未列 F71＝非硬 DAG，
  本模块零 lcr/cases import（互锁结构性不存在）。缺省后端
  local-deterministic-v1＝确定性本地实现（sha256 桶化字符 n-gram TF
  余弦＋CJK 相邻二元组/拉丁数字连串词面覆盖，F67 分词同思路）——如实
  自报 backendId，不冒神经向量模型。
* manuals 仓零引擎代码铁律：本模块零 legal_cn_manuals import——受控
  内容包只经既有受控通道（E23 冻结 manual.* 读侧四方法，不复制第二
  权威）；安装包不带 manuals/persona 内容由 recon 对实物树扫描断言。
* 状态：JSONL 追加（entries.jsonl/usage-log.jsonl，state_root 自家
  两个文件名常量），快照推进只增不改；read 逐次重算 digest，漂移＝
  kb_digest_mismatch 具名拒（fail-closed）。

config 键：kb_state_root（必需，缺失 NOT_CONNECTED）；kb_backend（可
选，未知值具名拒不静默回落）。全合成材料验收；零网络（import 闭集
AST 断言见 recon/test）；金额/期限不在本面。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
from typing import Any

KB_CONTRACT = "kb-rag/1"
# 接口级复用 F71 混合检索层：只命名接口，不 import 其实现（F71 行
# cases+product 在账 NOT_RUN＝非硬 DAG；其后端就绪可注册替换本实现）。
KB_RETRIEVAL_CONTRACT = "f71_hybrid/1"
LOCAL_BACKEND_ID = "local-deterministic-v1"
READ_SCOPES = ("public", "firm", "private")
PRIVATE_SCOPE = "private"
W_VECTOR = 0.6
W_LEXICAL = 0.4
QUALITY_BASE = 0.5
STALENESS_FACTOR = 0.5
DEFAULT_TOP_K = 5
MAX_TOP_K = 20
VEC_DIMS = 256
ENTRIES_FILE = "entries.jsonl"
USAGE_FILE = "usage-log.jsonl"

_ALLOWED_FIRM = frozenset({"firm"})

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REF_REQUIRED = ("owner", "kind", "id")


class KbRagError(RuntimeError):
    """typed kb_* 码：只带工程标识，绝不携条目正文/查询原文。"""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------ 分词/向量 --

_TOKEN_RE = re.compile(r"[一-鿿]+|[a-z0-9]+")
_CJK_RE = re.compile(r"^[一-鿿]+$")


def grams(text: str) -> list[str]:
    """确定性分词：CJK 相邻二元组＋拉丁数字连串（F67 自建分词同思路）。"""
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        tok = m.group(0)
        if _CJK_RE.match(tok):
            if len(tok) == 1:
                out.append(tok)
            else:
                out.extend(tok[i:i + 2] for i in range(len(tok) - 1))
        else:
            out.append(tok)
    return out


def vectorize(text: str) -> list[float]:
    vec = [0.0] * VEC_DIMS
    for gram in grams(text):
        slot = int.from_bytes(
            hashlib.sha256(gram.encode("utf-8")).digest()[:8], "big")
        vec[slot % VEC_DIMS] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _lexical_coverage(query_text: str, entry_text: str) -> float:
    q = set(grams(query_text))
    if not q:
        return 0.0
    e = set(grams(entry_text))
    return len(q & e) / len(q)


class LocalDeterministicBackend:
    """缺省确定性后端：sha256 桶化字符 n-gram TF 余弦（向量分量）＋
    词面覆盖率（词法分量）。零网络零模型，两跑逐字节同分。"""

    backend_id = LOCAL_BACKEND_ID

    def score_components(self, query_text: str, entry_text: str) -> dict:
        return {
            "vector": round(cosine(vectorize(query_text), vectorize(entry_text)), 6),
            "lexical": round(_lexical_coverage(query_text, entry_text), 6),
        }


BACKENDS = {cls.backend_id: cls for cls in (LocalDeterministicBackend,)}


# ------------------------------------------------------------ 快照/新鲜度 --

def content_view(meta: dict) -> dict:
    """参与内容快照 hash 的全字段视图（canonical JSON 键序稳定）。"""
    return {k: meta.get(k) for k in (
        "title", "body", "readScope", "qualityScore", "lastVerified",
        "freshnessWindowDays", "matterId", "sourceRefs", "topics")}


def entry_digest(meta: dict) -> str:
    return sha256_hex(canonical_json(content_view(meta)))


def _today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def staleness(meta: dict, today: dt.date | None = None) -> tuple[bool, str | None]:
    """过期治理：过期=freshness_expired；未验证=freshness_unknown；
    两者都降权＋标记，绝不静默混入。"""
    today = today or _today()
    lv = meta.get("lastVerified")
    window = meta.get("freshnessWindowDays")
    if not lv or window is None:
        return True, "freshness_unknown"
    verified = dt.date.fromisoformat(lv)
    if (today - verified).days > int(window):
        return True, "freshness_expired"
    return False, None


# ------------------------------------------------------------ 校验 --

def _require_str(value: Any, code: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise KbRagError(code)
    return value


def _validate_ref(ref: Any) -> dict:
    if not isinstance(ref, dict):
        raise KbRagError("kb_source_ref_invalid")
    for key in _REF_REQUIRED:
        v = ref.get(key)
        if not isinstance(v, str) or not v.strip():
            raise KbRagError("kb_source_ref_invalid")
    out = {k: ref[k] for k in _REF_REQUIRED}
    for key in ("version", "matterId", "digest"):
        # 可选键按提交原样保留（含显式 null）——快照 hash 覆盖提交全形，
        # 客端 canonical 重算可逐字节复现。
        if key in ref:
            if ref[key] is not None and not isinstance(ref[key], str):
                raise KbRagError("kb_source_ref_invalid")
            out[key] = ref[key]
    return out


def validate_entry_args(args: dict) -> dict:
    """entry_put 字段校验：出处（sourceRefs）必需——条目不带出处不入库。"""
    if not isinstance(args, dict):
        raise KbRagError("kb_entry_invalid")
    meta: dict[str, Any] = {}
    meta["kbId"] = _require_str(args.get("kbId"), "kb_entry_invalid")
    if len(meta["kbId"]) > 128:
        raise KbRagError("kb_entry_invalid")
    meta["title"] = _require_str(args.get("title"), "kb_entry_invalid")
    meta["body"] = _require_str(args.get("body"), "kb_entry_invalid")
    scope = args.get("readScope")
    if scope not in READ_SCOPES:
        raise KbRagError("kb_entry_invalid")
    meta["readScope"] = scope
    quality = args.get("qualityScore")
    if isinstance(quality, bool) or not isinstance(quality, (int, float)) \
            or not (0.0 <= float(quality) <= 1.0):
        raise KbRagError("kb_entry_invalid")
    meta["qualityScore"] = float(quality)
    last_verified = args.get("lastVerified")
    if last_verified is not None:
        if not isinstance(last_verified, str) or not _DATE_RE.match(last_verified):
            raise KbRagError("kb_entry_invalid")
        dt.date.fromisoformat(last_verified)  # 真日历日（ ValueError 具名拒）
    meta["lastVerified"] = last_verified
    window = args.get("freshnessWindowDays")
    if window is not None:
        if isinstance(window, bool) or not isinstance(window, int) or window < 0:
            raise KbRagError("kb_entry_invalid")
    meta["freshnessWindowDays"] = window
    matter_id = args.get("matterId")
    if matter_id is not None:
        _require_str(matter_id, "kb_entry_invalid")
    meta["matterId"] = matter_id
    source_refs = args.get("sourceRefs")
    if not isinstance(source_refs, list) or not source_refs:
        raise KbRagError("kb_entry_invalid")
    meta["sourceRefs"] = [_validate_ref(r) for r in source_refs]
    topics = args.get("topics", [])
    if not isinstance(topics, list) or any(
            not isinstance(t, str) or not t for t in topics):
        raise KbRagError("kb_entry_invalid")
    meta["topics"] = list(topics)
    return meta


# ------------------------------------------------------------ 存储 --

class KbStore:
    def __init__(self, state_root: str | None, backend_id: str | None = None) -> None:
        if not state_root:
            raise KbRagError("kb_state_root_not_configured")
        self.state_root = str(state_root)
        backend_cls = BACKENDS.get(backend_id or LOCAL_BACKEND_ID)
        if backend_cls is None:
            raise KbRagError("kb_backend_unknown:" + str(backend_id))
        self.backend_id = backend_cls.backend_id
        self.backend = backend_cls()
        self._entries_path = os.path.join(self.state_root, ENTRIES_FILE)
        self._usage_path = os.path.join(self.state_root, USAGE_FILE)

    # -- 存取 --

    def _load(self) -> list[dict]:
        if not os.path.isfile(self._entries_path):
            return []
        rows = []
        with open(self._entries_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def _latest(self) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for row in self._load():
            kb_id = row["kbId"]
            if kb_id not in latest or row["revision"] > latest[kb_id]["revision"]:
                latest[kb_id] = row
        return latest

    def _revision(self, kb_id: str, revision: int) -> dict | None:
        for row in self._load():
            if row["kbId"] == kb_id and row["revision"] == revision:
                return row
        return None

    def _append(self, row: dict) -> None:
        os.makedirs(self.state_root, exist_ok=True)
        with open(self._entries_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def _log_usage(self, receipt: dict) -> str:
        receipt_id = sha256_hex(canonical_json(receipt))[:16]
        os.makedirs(self.state_root, exist_ok=True)
        with open(self._usage_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"receiptId": receipt_id, **receipt},
                                    ensure_ascii=False, sort_keys=True) + "\n")
        return receipt_id

    @staticmethod
    def _ref(row: dict) -> dict:
        return {"owner": "kb", "kind": "kb-record", "id": row["kbId"],
                "version": str(row["revision"]),
                "matterId": row["content"].get("matterId"),
                "digest": row["entryDigest"]}

    # -- kb.entry_put --

    def entry_put(self, args: dict) -> dict:
        meta = validate_entry_args(args)
        kb_id = meta.pop("kbId")
        digest = entry_digest(meta)
        latest = self._latest().get(kb_id)
        if latest is not None and latest["entryDigest"] == digest:
            return {"entryRef": self._ref(latest), "entryDigest": digest,
                    "revision": latest["revision"], "revised": False,
                    "kbContract": KB_CONTRACT}
        revision = (latest["revision"] + 1) if latest is not None else 1
        row = {"kbId": kb_id, "revision": revision, "entryDigest": digest,
               "recordedAt": _now_iso(), "content": meta}
        self._append(row)
        out = {"entryRef": self._ref(row), "entryDigest": digest,
               "revision": revision, "revised": True,
               "kbContract": KB_CONTRACT}
        if latest is not None:
            out["superseded"] = {"revision": latest["revision"],
                                 "entryDigest": latest["entryDigest"]}
        return out

    # -- kb.search --

    def search(self, args: dict) -> dict:
        if not isinstance(args, dict):
            raise KbRagError("kb_params_invalid")
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise KbRagError("kb_query_required")
        matter_id = args.get("matterId")
        if matter_id is not None:
            _require_str(matter_id, "kb_matter_invalid")
        scopes = args.get("authorizedReadScopes", [])
        if not isinstance(scopes, list) or any(not isinstance(s, str) for s in scopes):
            raise KbRagError("kb_params_invalid")
        if PRIVATE_SCOPE in scopes:
            # private 永不可授权：不公开私域蒸馏的结构面。
            raise KbRagError("kb_scope_mismatch:private_never_authorizable")
        unknown = set(scopes) - _ALLOWED_FIRM
        if unknown:
            raise KbRagError("kb_params_invalid")
        authorized = {"public"} | (set(scopes) & _ALLOWED_FIRM)
        top_k = args.get("topK", DEFAULT_TOP_K)
        if isinstance(top_k, bool) or not isinstance(top_k, int) \
                or not (1 <= top_k <= MAX_TOP_K):
            raise KbRagError("kb_params_invalid")
        today = _today()
        hits = []
        for row in sorted(self._latest().values(), key=lambda r: r["kbId"]):
            meta = row["content"]
            if meta["readScope"] not in authorized:
                continue
            entry_matter = meta.get("matterId")
            # 分案隔离：只见 全局（无绑案）∪ 本案；跨案结构性不可见。
            if matter_id is None:
                if entry_matter is not None:
                    continue
            elif entry_matter is not None and entry_matter != matter_id:
                continue
            text = meta["title"] + "\n" + meta["body"] + "\n" + " ".join(meta["topics"])
            components = self.backend.score_components(query, text)
            relevance = round(W_VECTOR * components["vector"]
                              + W_LEXICAL * components["lexical"], 6)
            if relevance <= 0.0:
                continue  # 零相关不入命中（伪零命中无意义）
            quality_factor = round(
                QUALITY_BASE + (1.0 - QUALITY_BASE) * meta["qualityScore"], 6)
            stale, stale_reason = staleness(meta, today)
            staleness_factor = STALENESS_FACTOR if stale else 1.0
            effective = round(relevance * quality_factor * staleness_factor, 6)
            hits.append({
                "entryRef": self._ref(row),
                "title": meta["title"],
                "readScope": meta["readScope"],
                "sourceRefs": meta["sourceRefs"],
                "score": {"relevance": relevance,
                          "vector": components["vector"],
                          "lexical": components["lexical"],
                          "qualityFactor": quality_factor,
                          "stalenessFactor": staleness_factor,
                          "effective": effective},
                "stale": stale,
                "staleReason": stale_reason,
            })
        hits.sort(key=lambda h: (-h["score"]["effective"],
                                 h["entryRef"]["id"]))
        hits = hits[:top_k]
        # staleCount＝回执可验口径：返回命中中的过期条数（消费方可从
        # 响应逐条复核），不是候选全集口径。
        stale_count = sum(1 for h in hits if h["stale"])
        receipt = {
            "kind": "kb-search-receipt", "at": _now_iso(),
            "querySha256": sha256_hex(query.encode("utf-8")),
            "matterId": matter_id,
            "backend": self.backend_id,
            "retrievalContract": KB_RETRIEVAL_CONTRACT,
            "weights": {"vector": W_VECTOR, "lexical": W_LEXICAL,
                        "qualityBase": QUALITY_BASE,
                        "staleness": STALENESS_FACTOR},
            "hitCount": len(hits), "staleCount": stale_count,
            "hits": [h["entryRef"] for h in hits],
        }
        receipt_id = self._log_usage(receipt)
        return {"kbContract": KB_CONTRACT,
                "retrievalContract": KB_RETRIEVAL_CONTRACT,
                "backend": self.backend_id,
                "matterId": matter_id,
                "authorizedReadScopes": sorted(authorized),
                "hits": hits,
                "staleCount": stale_count,
                "receiptId": receipt_id}

    # -- kb.read --

    def read(self, args: dict) -> dict:
        if not isinstance(args, dict):
            raise KbRagError("kb_params_invalid")
        kb_id = _require_str(args.get("kbId"), "kb_ref_not_found")
        version = args.get("version")
        if version is None:
            row = self._latest().get(kb_id)
        else:
            if isinstance(version, str) and version.isdigit():
                version = int(version)
            if isinstance(version, bool) or not isinstance(version, int):
                raise KbRagError("kb_params_invalid")
            row = self._revision(kb_id, version)
        if row is None:
            raise KbRagError("kb_ref_not_found")
        meta = row["content"]
        if meta["readScope"] == PRIVATE_SCOPE:
            # private 不出读侧白名单（manuals 同纪律；不公开私域蒸馏）。
            raise KbRagError("kb_scope_mismatch:private_never_leaves_read_whitelist")
        # 快照逐次重算：内容或快照 hash 漂移一律具名拒（fail-closed）。
        if entry_digest(meta) != row["entryDigest"]:
            raise KbRagError("kb_digest_mismatch")
        stale, stale_reason = staleness(meta)
        receipt = {
            "kind": "kb-read-receipt", "at": _now_iso(),
            "ref": self._ref(row),
            "sourceRefs": meta["sourceRefs"],
            "readScope": meta["readScope"],
        }
        receipt_id = self._log_usage(receipt)
        return {"kbContract": KB_CONTRACT,
                "body": meta["body"],
                "title": meta["title"],
                "entryRef": self._ref(row),
                "readScope": meta["readScope"],
                "sourceRefs": meta["sourceRefs"],
                "qualityScore": meta["qualityScore"],
                "trust": {"lastVerified": meta["lastVerified"],
                          "freshnessWindowDays": meta["freshnessWindowDays"],
                          "stale": stale, "staleReason": stale_reason},
                "receiptId": receipt_id}

    # -- kb.stats --

    def stats(self) -> dict:
        latest = self._latest()
        by_scope: dict[str, int] = {s: 0 for s in READ_SCOPES}
        stale_count = 0
        matter_bound = 0
        for row in latest.values():
            meta = row["content"]
            by_scope[meta["readScope"]] += 1
            if staleness(meta)[0]:
                stale_count += 1
            if meta.get("matterId"):
                matter_bound += 1
        return {"kbContract": KB_CONTRACT,
                "retrievalContract": KB_RETRIEVAL_CONTRACT,
                "backend": self.backend_id,
                "entryCount": len(latest),
                "revisionCount": len(self._load()),
                "byScope": by_scope,
                "staleCount": stale_count,
                "matterBoundCount": matter_bound}


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------ 桥入口 --

def kb_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组 KB_METHODS 四方法分发；未配置根/未知方法
    绝不 stub 成功。"""
    if method not in ("kb.entry_put", "kb.search", "kb.read", "kb.stats"):
        raise KbRagError("kb_method_not_in_frozen_list:" + method)
    store = KbStore(config.get("kb_state_root"), config.get("kb_backend"))
    if method == "kb.entry_put":
        return store.entry_put(args)
    if method == "kb.search":
        return store.search(args)
    if method == "kb.read":
        return store.read(args)
    return store.stats()
