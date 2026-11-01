"""F29 cache partition discipline (W3-U05): stable/volatile context partition
over the SELECTED CORE CACHE (the upstream OpenCode native prompt-cache
lineage), never a second cache engine.

06 row F29 acceptance, mapped:

- 复用选定核心缓存: the lineage key embeds the NATIVE affinity transform —
  oc28 packages/core/src/session/model-request.ts passes the session
  affinity as ``promptCacheKey`` and strips the ``ses_`` prefix from
  ``ses_<64 hex>`` keys (same file, "promptCacheKey:" line). This face
  mirrors that exact transform (native_cache_key) so the product partition
  rides the provider cache lineage the core already establishes. The core's
  shared-prefix instruction ordering (session/context.ts "most to least
  shared ... reusable prompt-cache prefix") is the same discipline this face
  makes contract-checkable; neither upstream mechanism is modified or
  removed (复用原生缓存不删原策略 — recon pins both files verbatim).
- 稳定/变动上下文分区: immutable_segments (frozen rule pack texts, product
  system guidance — byte-stable per version) vs append_segments (case-scoped
  volatile turns, append-only).
- case/model/rule 版本变化正确失效: invalidation is DERIVED, not stored —
  a rule-pack version change folds into the lineage key (and, when the
  frozen rule TEXT is re-versioned, into the prefix bytes too); a model
  change changes only the lineage (provider cache is per-model) and never
  the prefix bytes; a case version change rotates the append partition
  (append is append-only: the previous partition is never rewritten) and
  never touches the prefix or lineage. Identical inputs produce
  byte-identical plans (deterministic).
- IMMUTABLE/APPEND 上下文与前缀指纹: prefix_fingerprint = SHA-256 over the
  canonical serialization of the IMMUTABLE prefix ONLY. Canonical byte
  recipe (exact, documented, order-significant): for each segment in
  declaration order emit ASCII(len(name_utf8)) + b":" + name_utf8 + b"\\0"
  + ASCII(len(text_utf8)) + b":" + text_utf8 + b"\\x1f"; concatenate.
  append_partition_key = SHA-256 over prefix_fingerprint + case_id +
  case_version. lineage_key = SHA-256 over native_cache_key + model +
  prefix_fingerprint.
- 不建第二缓存引擎: this face is PURE DERIVATION — no store, no process-local
  memo, no I/O, no network, no eviction, no TTL. It holds zero cached state
  between calls (the recon AST-checks this and asserts no files appear).
- 不拿宣传命中率当验收: the face reports NO hit-rate/ratio metric anywhere
  (the 03 denominator quotes a competitor's 94.7-98.1% measurement — that is
  a vendor claim, not a JusBench acceptance metric; the ledger states this
  explicitly). The plan output keys are a closed set.
- 预算闸: budget_bytes gates the IMMUTABLE prefix only — the reusable
  cached asset whose size the provider cache budget prices. Overage is a
  named refusal (cache_immutable_budget_exceeded); never silent truncation
  and never auto-eviction of frozen rule text (a frozen prefix must be
  re-versioned by an explicit rule decision, not squeezed by a gate).
  append_bytes and total_bytes are reported ungated (append grows by
  design).

All inputs are synthetic-material-friendly; failures are typed NotConnected
codes that never carry segment text.
"""
from __future__ import annotations

import hashlib

from bridge_errors import NotConnected

FACE_SCHEMA = "lvyin-cache-partition/1"

PLAN_KEYS = frozenset({
    "schema", "partition", "native_cache_key", "prefix_fingerprint",
    "append_partition_key", "lineage_key", "budget",
})

_AFFINITY_PREFIX = "ses_"


def native_cache_key(affinity: str) -> str:
    """Mirror of the upstream promptCacheKey transform (oc28
    packages/core/src/session/model-request.ts: ``ses_<64 hex>`` → strip the
    ``ses_`` prefix, otherwise the affinity passes through verbatim)."""
    if len(affinity) == 68 and affinity.startswith(_AFFINITY_PREFIX) \
            and all(c in "0123456789abcdef" for c in affinity[4:]):
        return affinity[4:]
    return affinity


def _segments(args: dict, key: str) -> list[tuple[str, str]]:
    raw = args.get(key)
    if not isinstance(raw, list):
        raise NotConnected("cache_" + key + "_must_be_list")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"name", "text"}:
            raise NotConnected("cache_segment_shape_invalid:" + key)
        name, text = entry["name"], entry["text"]
        if not isinstance(name, str) or not name or \
                not isinstance(text, str):
            raise NotConnected("cache_segment_field_invalid:" + key)
        if name in seen:
            raise NotConnected("cache_segment_name_duplicate:" + key)
        seen.add(name)
        out.append((name, text))
    return out


def canonical_prefix_bytes(segments: list[tuple[str, str]]) -> bytes:
    """Exact canonical serialization of an ordered segment list (recipe in
    the module docstring). Order is part of the frozen-prefix contract."""
    out = bytearray()
    for name, text in segments:
        name_b = name.encode("utf-8")
        text_b = text.encode("utf-8")
        out += str(len(name_b)).encode("ascii") + b":" + name_b + b"\x00"
        out += str(len(text_b)).encode("ascii") + b":" + text_b + b"\x1f"
    return bytes(out)


def prefix_fingerprint(segments: list[tuple[str, str]]) -> tuple[str, int]:
    data = canonical_prefix_bytes(segments)
    return hashlib.sha256(data).hexdigest(), len(data)


def _version_str(args: dict, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise NotConnected("cache_" + key + "_required")
    return value


def _case_fields(args: dict) -> tuple[str, str]:
    case = args.get("case")
    if not isinstance(case, dict) or set(case) != {"case_id", "case_version"}:
        raise NotConnected("cache_case_shape_invalid")
    case_id, case_version = case["case_id"], case["case_version"]
    if not isinstance(case_id, str) or not case_id or \
            not isinstance(case_version, str) or not case_version:
        raise NotConnected("cache_case_field_invalid")
    return case_id, case_version


def _rule_packs(args: dict) -> dict[str, str]:
    packs = args.get("rules")
    if not isinstance(packs, dict):
        raise NotConnected("cache_rules_must_be_object")
    out: dict[str, str] = {}
    for pack_id, version in packs.items():
        if not isinstance(pack_id, str) or not pack_id or \
                not isinstance(version, str) or not version:
            raise NotConnected("cache_rules_entry_invalid")
        out[pack_id] = version
    return out


def _budget(args: dict) -> int | None:
    raw = args.get("budget_bytes")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise NotConnected("cache_budget_bytes_invalid")
    return raw


def plan(args: dict) -> dict:
    """Deterministic partition plan for one context composition. Pure: same
    args → byte-identical output; nothing is stored or cached anywhere."""
    if not isinstance(args, dict):
        raise NotConnected("cache_params_invalid")
    affinity = _version_str(args, "affinity")
    model = _version_str(args, "model")
    case_id, case_version = _case_fields(args)
    rules = _rule_packs(args)
    immutable = _segments(args, "immutable_segments")
    appended = _segments(args, "append_segments")
    budget = _budget(args)

    fp, immutable_bytes = prefix_fingerprint(immutable)
    if budget is not None and immutable_bytes > budget:
        raise NotConnected("cache_immutable_budget_exceeded")
    _, append_bytes = prefix_fingerprint(appended)
    native = native_cache_key(affinity)
    # Rule-pack versions are part of the immutable identity: a pack version
    # bump is a rule-text change by contract, so it must fold into the
    # lineage even if the segment texts above were already regenerated.
    rules_blob = ",".join(pack + "@" + rules[pack] for pack in sorted(rules))
    lineage = hashlib.sha256(
        (native + "\x00" + model + "\x00" + fp + "\x00" + rules_blob)
        .encode("utf-8")).hexdigest()
    append_key = hashlib.sha256(
        (fp + "\x00" + case_id + "\x00" + case_version).encode("utf-8")
    ).hexdigest()
    return {
        "schema": FACE_SCHEMA,
        "partition": {
            "immutable": {"segments": [name for name, _ in immutable],
                          "bytes": immutable_bytes},
            "append": {"segments": [name for name, _ in appended],
                       "bytes": append_bytes,
                       "partition_key": append_key},
        },
        "native_cache_key": native,
        "prefix_fingerprint": fp,
        "append_partition_key": append_key,
        "lineage_key": lineage,
        "budget": {"limit_bytes": budget, "immutable_bytes": immutable_bytes,
                   "append_bytes": append_bytes,
                   "total_bytes": immutable_bytes + append_bytes,
                   "within": True},
    }


def fingerprint(args: dict) -> dict:
    """Prefix fingerprint utility: hash an ordered segment list without the
    full plan (used to pin a composed prefix against a registered value)."""
    if not isinstance(args, dict):
        raise NotConnected("cache_params_invalid")
    segments = _segments(args, "segments")
    fp, size = prefix_fingerprint(segments)
    return {"schema": FACE_SCHEMA, "prefix_fingerprint": fp, "bytes": size}


def cache_partition_call(method: str, args: dict, config: dict) -> dict:
    """Bridge dispatch (legal_entry CACHE_PARTITION_METHODS). The face needs
    no config — pure derivation over the request only."""
    if method == "cache.plan":
        return plan(args)
    if method == "cache.fingerprint":
        return fingerprint(args)
    raise NotConnected("cache_method_not_connected:" + method)
