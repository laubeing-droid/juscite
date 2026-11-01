# -*- coding: utf-8 -*-
"""F100 专家分身/专家商店（W5-U04；06:F100 desktop/selfhost 双实例，B5）。

07/17 卡 F100（owner=manuals+product，entries P02/P04）：专家分身/专家
商店（召唤制知识库 IP）；落点＝Harness manuals/playbook 公开消费＋受控
内容包＋原生技能UI；步骤＝固定内容 hash/权限→公开读取→实际任务消费→
来源回执和验证；不公开私域蒸馏。acceptance＝专家内容授权/来源/适用范
围准确；分身不冒真人实时意见。实现边界：

* 分身＝固定受控内容包（本模块）：卡片携 attribution（authorship 闭集
  synthetic_original/authorized_excerpt；后者必须 attributedTo＋
  authorizationRef，缺失不入店＝授权面缺失 fail-closed）＋applicable
  Scopes（非空声明，适用范围准确）＋内容条目（逐条 sourceRefs C16 ref
  形状＋itemDigest、卡片整体 cardDigest＝canonical JSON 全字段 sha256，
  含正文——任何字节漂移在读取/消费边界具名拒）。
* 分身不冒真人实时意见（结构面，非文案）：grounding 闭集只认
  pinned_pack（任何 live/realtime 形态 grounding 具名拒）＋declares
  RealTime 恒 False（显式 True 具名拒）＋consult 应答恒携 nonLive 声明
  字段；本模块 import 闭集零网络（recon/test AST 钉死）——实时渠道在
  本面结构性不存在，分身只据其钉定包快照应答。
* 授权在消费边界 fail-closed：条目/卡片 scope 闭集 public/firm（三级
  闭集头两级，与 manuals/kb 同名同序）；private 内容结构性不入包
  （f100_private_content_not_bindable＝不公开私域蒸馏：私域内容留在其
  既有受控白名单面，绝不进商店可分发对象）。firm 卡片 store_list/
  store_read/consult 须 authorizedReadScopes 显式携带 firm；传 private
  进授权集＝具名拒（private 永不可授权，kb 同纪律）。
* 商店＝元数据只读货架：store_list/store_read 输出永不含条目正文
  （recon/test 字节级断言）；正文只经 consult 摘录流出（确定性截断），
  逐摘录携 itemRef（含 itemDigest）＋sourceRefs 回溯源。
* 实际任务消费＝确定性词面评分（sha256 桶化字符 n-gram TF 余弦＋词面
  覆盖，F67/F73 同思路；零模型零网络，两跑逐字节同分）。零相关命中＝
  f100_out_of_scope_abstain 具名弃答——分身只答所驻内容范围内问题，
  绝不越界编造（适用范围准确的结构面）。
* 来源回执和验证：consult 回执（cardDigest＋逐命中 itemRef）落盘
  consult-log.jsonl（receiptId＝canonical 回执 sha256 前 16 hex）；verify
  _receipt 从盘上状态全量重算（receiptId 重算＋卡片/条目 digest 重算），
  任何漂移具名拒不假 PASS。
* 版本：experts.jsonl 追加只增不改；同内容重定义幂等（同 revision 同
  digest）；内容变更→revision+1（superseded 携旧版），历史可经
  store_read version 回读（同授权规则）。
* manuals 仓零引擎代码铁律＋不复制第二权威：本模块零 legal_cn_manuals/
  playbook/lcr import——受控内容公开消费只经既有冻结通道（E23
  MANUAL_METHODS 四方法＋HARNESS_PLAYBOOK_METHODS 三方法）；条目
  sourceRefs 是数据（本引擎不解析其指向）。
* 裁决#7/#13-19：本面内容一律工程合成样本；Observer 不启用（legal
  _entry 顶层 persona./observer. 无条件具名拒不动）；安装包不带 manuals
  与 persona 内容（recon 对实物树扫描断言）。

config 键：expert_state_root（必需，缺失 NOT_CONNECTED）。错误码 f100_*
只带工程标识，绝不携卡片正文/查询原文。金额/期限不在本面。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
from typing import Any

EXPERT_CONTRACT = "expert-store/1"
# 卡片/条目 scope 闭集＝三级闭集头两级（public/firm；private 结构性不入
# 包——私域内容不进商店可分发对象，即「不公开私域蒸馏」的包面）。
CARD_SCOPES = ("public", "firm")
PRIVATE_SCOPE = "private"
# grounding 闭集：唯一合法 grounding＝钉定内容包快照。任何「实时/在线」
# 形态（live/realtime/…）都落不进闭集→f100_grounding_kind_refused。
GROUNDING_KINDS = ("pinned_pack",)
# 授权面闭集：synthetic_original（合成原作，不得 attributedTo 真人）；
# authorized_excerpt（经授权摘编，必须 attributedTo＋authorizationRef）。
AUTHORSHIPS = ("synthetic_original", "authorized_excerpt")
# 应答恒携的不冒真人声明（consult 输出 nonLive.statement 逐字）。
NONLIVE_STATEMENT = ("本分身仅据其固定内容包快照应答，不连接任何实时渠道，"
                     "不代表任何真人的实时意见。")

W_VECTOR = 0.6
W_LEXICAL = 0.4
DEFAULT_TOP_K = 3
MAX_TOP_K = 10
EXCERPT_CHARS = 120
VEC_DIMS = 256
EXPERTS_FILE = "experts.jsonl"
CONSULT_FILE = "consult-log.jsonl"
_MAX_ID = 128

_ALLOWED_FIRM = frozenset({"firm"})
_TOKEN_RE = re.compile(r"[一-鿿]+|[a-z0-9]+")
_CJK_RE = re.compile(r"^[一-鿿]+$")
_REF_REQUIRED = ("owner", "kind", "id")


class ExpertStoreError(RuntimeError):
    """typed f100_* 码：只带工程标识，绝不携卡片正文/查询原文。"""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------ 分词/评分 --

def grams(text: str) -> list[str]:
    """确定性分词：CJK 相邻二元组＋拉丁数字连串（F67/F73 同思路）。"""
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


def _lexical_coverage(query_text: str, item_text: str) -> float:
    q = set(grams(query_text))
    if not q:
        return 0.0
    e = set(grams(item_text))
    return len(q & e) / len(q)


def score_components(query_text: str, item_text: str) -> dict:
    """确定性评分分量：向量 0.6＋词法 0.4（两跑逐字节同分）。"""
    return {
        "vector": round(cosine(vectorize(query_text), vectorize(item_text)), 6),
        "lexical": round(_lexical_coverage(query_text, item_text), 6),
    }


def _excerpt(body: str) -> str:
    """确定性摘录：正文前 EXCERPT_CHARS 字符＋越界省略号（正文完整件
    永不出 consult 摘录面——全文留在包内，摘要携 itemDigest 可验）。"""
    if len(body) <= EXCERPT_CHARS:
        return body
    return body[:EXCERPT_CHARS] + "…"


# ------------------------------------------------------------ 校验 --

def _require_str(value: Any, code: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ExpertStoreError(code)
    return value


def _validate_ref(ref: Any) -> dict:
    if not isinstance(ref, dict):
        raise ExpertStoreError("f100_source_ref_invalid")
    for key in _REF_REQUIRED:
        v = ref.get(key)
        if not isinstance(v, str) or not v.strip():
            raise ExpertStoreError("f100_source_ref_invalid")
    out = {k: ref[k] for k in _REF_REQUIRED}
    for key in ("version", "matterId", "digest"):
        # 可选键按提交原样保留（含显式 null）——快照 hash 覆盖提交全形，
        # 客端 canonical 重算可逐字节复现。
        if key in ref:
            if ref[key] is not None and not isinstance(ref[key], str):
                raise ExpertStoreError("f100_source_ref_invalid")
            out[key] = ref[key]
    return out


def _validate_grounding(raw: Any) -> dict:
    """grounding 闭集：只认 pinned_pack；declaresRealTime 恒 False。
    「实时意见」形态在此结构性进不来（具名拒），不是文案约定。"""
    if not isinstance(raw, dict) or "kind" not in raw:
        raise ExpertStoreError("f100_grounding_invalid")
    kind = raw["kind"]
    if not isinstance(kind, str) or not kind:
        raise ExpertStoreError("f100_grounding_invalid")
    if kind not in GROUNDING_KINDS:
        raise ExpertStoreError("f100_grounding_kind_refused:" + kind)
    unknown = set(raw) - {"kind", "declaresRealTime"}
    if unknown:
        raise ExpertStoreError("f100_grounding_invalid")
    if "declaresRealTime" in raw:
        flag = raw["declaresRealTime"]
        if not isinstance(flag, bool):
            raise ExpertStoreError("f100_grounding_invalid")
        if flag:
            raise ExpertStoreError("f100_realtime_claim_refused")
    return {"kind": kind, "declaresRealTime": False}


def _validate_attribution(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ExpertStoreError("f100_card_invalid")
    authorship = raw.get("authorship")
    if authorship not in AUTHORSHIPS:
        raise ExpertStoreError("f100_authorization_invalid")
    attributed_to = raw.get("attributedTo")
    authorization_ref = raw.get("authorizationRef")
    if authorship == "synthetic_original":
        # 合成原作不得挂真人署名/授权凭据（挂了＝自相矛盾具名拒）。
        if attributed_to or authorization_ref:
            raise ExpertStoreError("f100_attribution_conflict")
    else:  # authorized_excerpt：授权/来源缺一不入店（授权面准确）。
        if not isinstance(attributed_to, str) or not attributed_to.strip():
            raise ExpertStoreError("f100_authorization_missing")
        if not isinstance(authorization_ref, str) \
                or not authorization_ref.strip():
            raise ExpertStoreError("f100_authorization_missing")
    out = {"authorship": authorship}
    for key in ("attributedTo", "authorizationRef"):
        if raw.get(key) is not None:
            out[key] = raw[key]
    return out


def _validate_item(raw: Any, index: int) -> dict:
    if not isinstance(raw, dict):
        raise ExpertStoreError("f100_card_invalid")
    item: dict[str, Any] = {"itemId": "it-%d" % (index + 1)}
    item["title"] = _require_str(raw.get("title"), "f100_card_invalid")
    item["body"] = _require_str(raw.get("body"), "f100_card_invalid")
    scope = raw.get("readScope")
    if scope == PRIVATE_SCOPE:
        # private 内容不入包＝商店可分发对象零私域内容（不公开私域
        # 蒸馏的包面；私域留在 manuals/kb 各自受控白名单）。
        raise ExpertStoreError("f100_private_content_not_bindable")
    if scope not in CARD_SCOPES:
        raise ExpertStoreError("f100_card_invalid")
    item["readScope"] = scope
    source_refs = raw.get("sourceRefs")
    if not isinstance(source_refs, list) or not source_refs:
        raise ExpertStoreError("f100_card_invalid")
    item["sourceRefs"] = [_validate_ref(r) for r in source_refs]
    topics = raw.get("topics", [])
    if not isinstance(topics, list) or any(
            not isinstance(t, str) or not t for t in topics):
        raise ExpertStoreError("f100_card_invalid")
    item["topics"] = list(topics)
    return item


def validate_card_args(args: dict) -> dict:
    """expert.define 字段校验（B0 冻结形）：分身卡五段全 Required。"""
    if not isinstance(args, dict):
        raise ExpertStoreError("f100_card_invalid")
    expert_id = _require_str(args.get("expertId"), "f100_card_invalid")
    if len(expert_id) > _MAX_ID:
        raise ExpertStoreError("f100_card_invalid")
    meta: dict[str, Any] = {"expertId": expert_id}
    meta["displayName"] = _require_str(args.get("displayName"),
                                       "f100_card_invalid")
    meta["grounding"] = _validate_grounding(args.get("grounding"))
    meta["attribution"] = _validate_attribution(args.get("attribution"))
    scopes = args.get("applicableScopes")
    if not isinstance(scopes, list) or not scopes or any(
            not isinstance(s, str) or not s.strip() for s in scopes):
        # 适用范围声明是卡片准入要件（缺失不入店＝适用范围准确）。
        raise ExpertStoreError("f100_scope_declaration_required")
    meta["applicableScopes"] = list(scopes)
    items = args.get("items")
    if not isinstance(items, list) or not items:
        raise ExpertStoreError("f100_card_invalid")
    meta["items"] = [_validate_item(raw, i) for i, raw in enumerate(items)]
    return meta


# ------------------------------------------------------------ 快照 hash --

def item_view(item: dict) -> dict:
    """条目内容视图（canonical JSON 键序稳定；不含 itemId——编号不入
    hash，内容变才变）。"""
    return {k: item[k] for k in ("title", "body", "readScope",
                                 "sourceRefs", "topics")}


def item_digest(item: dict) -> str:
    return sha256_hex(canonical_json(item_view(item)))


def card_view(meta: dict) -> dict:
    """卡片内容视图（含全部条目正文——任何字节漂移都在重算边界现形）。
    itemId 不入视图：编号是位置元数据非内容（item_view 同口径），客端
    对提交原形 canonical 重算可与引擎逐字相等。"""
    view = {k: meta[k] for k in ("displayName", "grounding", "attribution",
                                 "applicableScopes")}
    view["items"] = [{k: v for k, v in item.items() if k != "itemId"}
                     for item in meta["items"]]
    return view


def card_digest(meta: dict) -> str:
    return sha256_hex(canonical_json(card_view(meta)))


def card_scope(meta: dict) -> str:
    return "firm" if any(i["readScope"] == "firm"
                         for i in meta["items"]) else "public"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------ 存储 --

class ExpertStore:
    def __init__(self, state_root: str | None) -> None:
        if not state_root:
            raise ExpertStoreError("f100_state_root_not_configured")
        self.state_root = str(state_root)
        self._cards_path = os.path.join(self.state_root, EXPERTS_FILE)
        self._consult_path = os.path.join(self.state_root, CONSULT_FILE)

    # -- 存取 --

    def _load(self) -> list[dict]:
        if not os.path.isfile(self._cards_path):
            return []
        rows = []
        with open(self._cards_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def _latest(self) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for row in self._load():
            eid = row["expertId"]
            if eid not in latest or row["revision"] > latest[eid]["revision"]:
                latest[eid] = row
        return latest

    def _row(self, expert_id: str, revision: int | None) -> dict | None:
        if revision is None:
            return self._latest().get(expert_id)
        for row in self._load():
            if row["expertId"] == expert_id and row["revision"] == revision:
                return row
        return None

    def _append(self, row: dict) -> None:
        os.makedirs(self.state_root, exist_ok=True)
        with open(self._cards_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True)
                         + "\n")

    def _log_consult(self, receipt: dict) -> str:
        receipt_id = sha256_hex(canonical_json(receipt))[:16]
        os.makedirs(self.state_root, exist_ok=True)
        with open(self._consult_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"receiptId": receipt_id, **receipt},
                                    ensure_ascii=False, sort_keys=True) + "\n")
        return receipt_id

    @staticmethod
    def _card_ref(row: dict) -> dict:
        return {"owner": "expert", "kind": "expert-card",
                "id": row["expertId"], "version": str(row["revision"]),
                "digest": row["cardDigest"]}

    @staticmethod
    def _item_ref(row: dict, item: dict) -> dict:
        return {"owner": "expert", "kind": "expert-item",
                "id": row["expertId"], "version": str(row["revision"]),
                "itemId": item["itemId"], "digest": item_digest(item)}

    @staticmethod
    def _authorized(args: dict) -> set[str]:
        scopes = args.get("authorizedReadScopes", [])
        if not isinstance(scopes, list) or any(
                not isinstance(s, str) for s in scopes):
            raise ExpertStoreError("f100_params_invalid")
        if PRIVATE_SCOPE in scopes:
            # private 永不可授权（不公开私域蒸馏；kb/manuals 同纪律）。
            raise ExpertStoreError(
                "f100_scope_mismatch:private_never_authorizable")
        unknown = set(scopes) - _ALLOWED_FIRM
        if unknown:
            raise ExpertStoreError("f100_params_invalid")
        return {"public"} | (set(scopes) & _ALLOWED_FIRM)

    def _load_card(self, args: dict, authorized: set[str]) -> dict:
        expert_id = _require_str(args.get("expertId"), "f100_ref_not_found")
        version = args.get("version")
        if version is None:
            row = self._row(expert_id, None)
        else:
            if isinstance(version, str) and version.isdigit():
                version = int(version)
            if isinstance(version, bool) or not isinstance(version, int):
                raise ExpertStoreError("f100_params_invalid")
            row = self._row(expert_id, version)
        if row is None:
            raise ExpertStoreError("f100_ref_not_found")
        meta = row["card"]
        # 快照逐次重算：包内容或卡片 hash 漂移一律具名拒（fail-closed）。
        if card_digest(meta) != row["cardDigest"]:
            raise ExpertStoreError("f100_card_digest_mismatch")
        if card_scope(meta) not in authorized:
            raise ExpertStoreError("f100_scope_mismatch")
        return row

    # -- expert.define（固定内容 hash/权限）--

    def define(self, args: dict) -> dict:
        meta = validate_card_args(args)
        expert_id = meta.pop("expertId")
        digest = card_digest(meta)
        latest = self._latest().get(expert_id)
        if latest is not None and latest["cardDigest"] == digest:
            return {"cardRef": self._card_ref(latest), "cardDigest": digest,
                    "revision": latest["revision"], "revised": False,
                    "cardScope": card_scope(latest["card"]),
                    "expertContract": EXPERT_CONTRACT}
        revision = (latest["revision"] + 1) if latest is not None else 1
        row = {"expertId": expert_id, "revision": revision,
               "cardDigest": digest, "recordedAt": _now_iso(),
               "card": meta}
        self._append(row)
        out = {"cardRef": self._card_ref(row), "cardDigest": digest,
               "revision": revision, "revised": True,
               "cardScope": card_scope(meta),
               "expertContract": EXPERT_CONTRACT}
        if latest is not None:
            out["superseded"] = {"revision": latest["revision"],
                                 "cardDigest": latest["cardDigest"]}
        return out

    # -- expert.store_list（公开读取·元数据货架）--

    @staticmethod
    def _card_listing(row: dict) -> dict:
        meta = row["card"]
        return {"expertId": row["expertId"], "revision": row["revision"],
                "cardDigest": row["cardDigest"],
                "displayName": meta["displayName"],
                "cardScope": card_scope(meta),
                "grounding": meta["grounding"],
                "authorship": meta["attribution"]["authorship"],
                "attributedTo": meta["attribution"].get("attributedTo"),
                "applicableScopes": meta["applicableScopes"],
                "itemCount": len(meta["items"]),
                "recordedAt": row["recordedAt"]}

    def store_list(self, args: dict) -> dict:
        if not isinstance(args, dict):
            raise ExpertStoreError("f100_params_invalid")
        authorized = self._authorized(args)
        cards = [self._card_listing(row)
                 for eid, row in sorted(self._latest().items())
                 if card_scope(row["card"]) in authorized]
        return {"expertContract": EXPERT_CONTRACT,
                "authorizedReadScopes": sorted(authorized),
                "storeSize": len(cards), "cards": cards}

    # -- expert.store_read（公开读取·单卡元数据，正文永不出货架）--

    def store_read(self, args: dict) -> dict:
        if not isinstance(args, dict):
            raise ExpertStoreError("f100_params_invalid")
        row = self._load_card(args, self._authorized(args))
        meta = row["card"]
        return {"expertContract": EXPERT_CONTRACT,
                "cardRef": self._card_ref(row),
                "displayName": meta["displayName"],
                "cardScope": card_scope(meta),
                "grounding": meta["grounding"],
                "attribution": meta["attribution"],
                "applicableScopes": meta["applicableScopes"],
                "items": [{"itemId": i["itemId"], "title": i["title"],
                           "itemDigest": item_digest(i),
                           "readScope": i["readScope"],
                           "sourceRefs": i["sourceRefs"],
                           "topics": i["topics"]}
                          for i in meta["items"]],
                "recordedAt": row["recordedAt"]}

    # -- expert.consult（实际任务消费＋来源回执）--

    def consult(self, args: dict) -> dict:
        if not isinstance(args, dict):
            raise ExpertStoreError("f100_params_invalid")
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ExpertStoreError("f100_query_required")
        top_k = args.get("topK", DEFAULT_TOP_K)
        if isinstance(top_k, bool) or not isinstance(top_k, int) \
                or not (1 <= top_k <= MAX_TOP_K):
            raise ExpertStoreError("f100_params_invalid")
        row = self._load_card(args, self._authorized(args))
        meta = row["card"]
        hits = []
        for item in meta["items"]:
            text = item["title"] + "\n" + item["body"] + "\n" \
                + " ".join(item["topics"])
            components = score_components(query, text)
            relevance = round(W_VECTOR * components["vector"]
                              + W_LEXICAL * components["lexical"], 6)
            if relevance <= 0.0 or components["lexical"] <= 0.0:
                # 零词面重叠不入命中（sha256 桶化向量在小语料上有桶撞，
                # 词面闸兜底：与钉定包零共同 n-gram＝不在分身范围内，
                # 桶撞噪声不构成「在范围内」）。
                continue
            hits.append({
                "itemRef": self._item_ref(row, item),
                "title": item["title"],
                "excerpt": _excerpt(item["body"]),
                "readScope": item["readScope"],
                "sourceRefs": item["sourceRefs"],
                "score": {"relevance": relevance,
                          "vector": components["vector"],
                          "lexical": components["lexical"]},
            })
        if not hits:
            # 具名弃答：分身只答其钉定内容范围内的问题，绝不越界编造
            # （适用范围准确的结构面；弃答码不带查询原文）。
            raise ExpertStoreError("f100_out_of_scope_abstain")
        hits.sort(key=lambda h: (-h["score"]["relevance"],
                                 h["itemRef"]["itemId"]))
        hits = hits[:top_k]
        receipt = {
            "kind": "expert-consult-receipt", "at": _now_iso(),
            "expertId": row["expertId"], "revision": row["revision"],
            "cardDigest": row["cardDigest"],
            "querySha256": sha256_hex(query.encode("utf-8")),
            "hitCount": len(hits),
            "items": [h["itemRef"] for h in hits],
        }
        receipt_id = self._log_consult(receipt)
        return {"expertContract": EXPERT_CONTRACT,
                "cardRef": self._card_ref(row),
                "displayName": meta["displayName"],
                "grounding": {"kind": meta["grounding"]["kind"],
                              "packVersion": row["revision"],
                              "cardDigest": row["cardDigest"]},
                "nonLive": {"declaresRealTime": False,
                            "statement": NONLIVE_STATEMENT},
                "applicableScopes": meta["applicableScopes"],
                "hits": hits,
                "receiptId": receipt_id}

    # -- expert.verify_receipt（来源回执和验证）--

    def verify_receipt(self, args: dict) -> dict:
        if not isinstance(args, dict):
            raise ExpertStoreError("f100_params_invalid")
        receipt_id = _require_str(args.get("receiptId"),
                                  "f100_receipt_not_found")
        if not os.path.isfile(self._consult_path):
            raise ExpertStoreError("f100_receipt_not_found")
        found = None
        with open(self._consult_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("receiptId") == receipt_id:
                    found = entry
                    break
        if found is None:
            raise ExpertStoreError("f100_receipt_not_found")
        receipt = {k: v for k, v in found.items() if k != "receiptId"}
        if sha256_hex(canonical_json(receipt))[:16] != receipt_id:
            raise ExpertStoreError("f100_receipt_tampered")
        row = self._row(receipt["expertId"], receipt["revision"])
        if row is None or card_digest(row["card"]) != receipt["cardDigest"]:
            raise ExpertStoreError(
                "f100_receipt_verify_failed:card_digest_drift")
        by_id = {i["itemId"]: i for i in row["card"]["items"]}
        if len(receipt["items"]) != receipt["hitCount"]:
            raise ExpertStoreError(
                "f100_receipt_verify_failed:item_set_drift")
        for ref in receipt["items"]:
            item = by_id.get(ref.get("itemId"))
            if item is None or item_digest(item) != ref.get("digest"):
                raise ExpertStoreError(
                    "f100_receipt_verify_failed:item_digest_drift:"
                    + str(ref.get("itemId")))
        return {"expertContract": EXPERT_CONTRACT,
                "receiptId": receipt_id, "verdict": "PASS",
                "cardRef": self._card_ref(row),
                "cardDigest": row["cardDigest"],
                "hitCount": receipt["hitCount"],
                "items": receipt["items"],
                "verifiedAt": _now_iso()}


# ------------------------------------------------------------ 桥入口 --

def expert_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组 EXPERT_METHODS 五方法分发；未配置根/未知
    方法绝不 stub 成功。"""
    if method not in ("expert.define", "expert.store_list",
                      "expert.store_read", "expert.consult",
                      "expert.verify_receipt"):
        raise ExpertStoreError("f100_method_not_in_frozen_list:" + method)
    store = ExpertStore(config.get("expert_state_root"))
    if method == "expert.define":
        return store.define(args)
    if method == "expert.store_list":
        return store.store_list(args)
    if method == "expert.store_read":
        return store.store_read(args)
    if method == "expert.consult":
        return store.consult(args)
    return store.verify_receipt(args)
