"""F30 airplane mode (W3-U05): one-click switch that blocks ALL remote
egress — remote models, connectors, updates, telemetry — while the local
offline read/calc surfaces (E22 codices frozen face, W2a-U13 statute face,
JC calc faces) stay fully usable.

Owner split (17 card + ticket): the upstream app/desktop plane is the
desktop-side landing (implementation/patches/017-f30-airplane-mode.patch:
flag read + service-env propagation + desktop extension-download guard;
verify_patch prestate). THIS module is the product-bridge plane: the flag
state, the closed egress decision table over the E10 egress inventory
(docs/construction/e10-egress-inventory.md §1), and the live gates on the
only bridge dispatch paths that can reach a remote endpoint.

Decision semantics (closed):
- Every channel BLOCKED while the switch is armed (contribution "armed"),
  with the loopback exception for the two endpoint-gated channels: a
  loopback model provider / retriever is LOCAL, and F30 keeps local
  channels alive (本地模型通道 F22 v1 stays usable offline).
- Switch inactive (contribution "inactive"): the two bridge-gated channels
  are ALLOWED (status quo); every other channel reports its standing
  governance via enforcement_kind — never a fake ALLOWED-by-nobody. The one
  standing channel is the models.dev catalog fetch: hard-disabled in the
  product desktop chain regardless of the switch (patch 007 env,
  applied to the oc28 tree), reported contribution "standing".
- Telemetry: the upstream property is no-remote-telemetry at all (E10 #15:
  no posthog/sentry/analytics outbound in cli/core/src; renderer Sentry
  initializes only with a build-time DSN which the product build does not
  inject). The channel row names that property; the recon greps it live.

Flag state: config["airplane_state_root"] directory holding
airplane-mode.json {"enabled": bool, "reason": str|null, "updated_at": iso}.
Missing root or file = switch off (configured=False) — existing faces keep
their exact current behavior; nothing changes until the switch is armed.
The flag file is written atomically (tmp + os.replace). The desktop-side
flag (patch 017) lives in the product config root and is written by the
desktop settings surface; this state root is the bridge-side mirror used by
product deployers and tests — the two share the flag file SHAPE, not the
file.

Live gates wired through this face:
- review_chat.ask (the only bridge face that runs a model round): refuses
  typed (airplane_remote_model_blocked) when armed and the configured chat
  provider is not declared local (config["airplane_local_providers"]).
- case.search over the lcr/1 HTTP retriever: refuses typed
  (airplane_remote_case_retriever_blocked) when armed and cases_url is not
  loopback — refused BEFORE any connection attempt. The local cases-root
  public path (config cases_root) is untouched: case data reads stay
  offline-usable.

Offline read/calc is never gated: statute.*, citation.*, calc.*, number.*,
material parse/OCR state-machine faces have no airplane hooks — they are
local by construction (frozen faces, local JC client, pure functions).

No hit-rate, no percentages: this face reports decisions and mechanism
names only.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

from bridge_errors import NotConnected

FACE_SCHEMA = "lvyin-airplane-mode/1"
FLAG_FILENAME = "airplane-mode.json"

# Closed channel set — one row per E10 egress-inventory class (§1 #1-#11,
# #14; #12/#13 are local-write faces, #15 upstream has no remote telemetry,
# #16-#18 archived). enforcement_kind names WHO enforces; the recon verifies
# each kind by its own means (live refusal / applied oc28 file / patch
# prestate / oc28 grep) and never reads a structural kind as behavioral PASS.
CHANNELS = (
    # (channel, enforcement_kind, endpoint_gated)
    ("model_round_remote", "bridge_gate", True),            # E10 #1
    ("case_retriever_http", "bridge_gate", True),           # product lcr client
    ("model_provider_catalog_fetch", "upstream_env", False),  # E10 #2, patch 007 standing
    ("self_update_check", "upstream_config", False),        # E10 #9
    ("webfetch_tool", "upstream_permission_plane", False),  # E10 #7
    ("websearch_provider", "upstream_permission_plane", False),  # E10 #8
    ("remote_mcp", "upstream_permission_plane", False),     # E10 #5/#6
    ("console_auth_config", "upstream_default_off", False),  # E10 #3/#4 default off
    ("npm_sdk_plugin_install", "upstream_partial", False),  # E10 #10 no single switch
    ("renderer_telemetry_sentry", "upstream_property", False),  # E10 #11/#15
    ("extension_download", "desktop_patch", False),         # E10 #14, patch 017
)

_CHANNEL_IDS = frozenset(c[0] for c in CHANNELS)
_ENDPOINT_GATED = frozenset(c[0] for c in CHANNELS if c[2])
_GATE_CODES = {
    "model_round_remote": "airplane_remote_model_blocked",
    "case_retriever_http": "airplane_remote_case_retriever_blocked",
}

REVIEW_CHAT_PROVIDER = "deepseek-byok"  # review_chat.CHAT_MODEL (裁决③)


def flag(config: dict) -> dict:
    """Read the airplane flag. Missing/unreadable = off (configured False);
    a malformed flag file is a named refusal, never silently off."""
    root = (config or {}).get("airplane_state_root")
    if not root:
        return {"enabled": False, "configured": False, "state_root": None,
                "reason": None, "updated_at": None}
    path = Path(root) / FLAG_FILENAME
    if not path.is_file():
        return {"enabled": False, "configured": False, "state_root": str(root),
                "reason": None, "updated_at": None}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NotConnected("airplane_flag_unreadable:" + type(exc).__name__) from None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("enabled"), bool):
        raise NotConnected("airplane_flag_shape_invalid")
    return {"enabled": parsed["enabled"], "configured": True,
            "state_root": str(root),
            "reason": parsed.get("reason") if isinstance(parsed.get("reason"), str) else None,
            "updated_at": parsed.get("updated_at") if isinstance(parsed.get("updated_at"), str) else None}


def set_flag(args: dict, config: dict) -> dict:
    """Arm/disarm the switch (atomic write). Typed DTO refusals; the state
    root must be configured — the bridge never invents a location."""
    if not isinstance(args, dict) or set(args) - {"enabled", "reason"} \
            or not isinstance(args.get("enabled"), bool):
        raise NotConnected("airplane_set_args_invalid")
    if "reason" in args and (not isinstance(args["reason"], str) or len(args["reason"]) > 500):
        raise NotConnected("airplane_set_reason_invalid")
    root = (config or {}).get("airplane_state_root")
    if not root:
        raise NotConnected("airplane_state_root_not_configured")
    base = Path(root)
    base.mkdir(parents=True, exist_ok=True)
    payload = {"enabled": args["enabled"],
               "reason": args.get("reason"),
               "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tmp = base / (FLAG_FILENAME + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, base / FLAG_FILENAME)
    return status(config)


def _loopback_host(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1", "[::1]")


def endpoint_is_local(url: str) -> bool:
    """Deterministic loopback classification for an http(s) endpoint URL.
    Anything not parseable as http(s) with a loopback host is REMOTE
    (fail-closed: file:/loopback-free schemes are not endpoints here)."""
    if not isinstance(url, str) or not url:
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    return _loopback_host(parts.hostname.lower())


def _provider_is_local(config: dict, provider_id: str | None) -> bool:
    declared = (config or {}).get("airplane_local_providers")
    if not isinstance(declared, list):
        return False
    return isinstance(provider_id, str) and provider_id in declared


def decision(args: dict, config: dict) -> dict:
    """Closed egress decision table. args: {channel, endpoint?, provider_id?}.
    decision ∈ {ALLOWED, BLOCKED}; switch_contribution ∈ {armed, inactive,
    standing} — WHO blocks (or does not), never a merged fake verdict."""
    if not isinstance(args, dict) or set(args) - {"channel", "endpoint", "provider_id"}:
        raise NotConnected("airplane_decision_args_invalid")
    channel = args.get("channel")
    if channel not in _CHANNEL_IDS:
        raise NotConnected("airplane_channel_unknown:" + str(channel))
    kind = next(k for c, k, _ in CHANNELS if c == channel)
    armed = flag(config)["enabled"]
    if channel in _ENDPOINT_GATED:
        if channel == "model_round_remote" and "endpoint" not in args:
            provider_local = _provider_is_local(config, args.get("provider_id")
                                                or REVIEW_CHAT_PROVIDER)
        else:
            endpoint = args.get("endpoint")
            if not isinstance(endpoint, str) or not endpoint:
                raise NotConnected("airplane_endpoint_required:" + channel)
            provider_local = endpoint_is_local(endpoint)
        if armed and not provider_local:
            return {"channel": channel, "decision": "BLOCKED",
                    "reason_code": _GATE_CODES[channel],
                    "enforcement_kind": kind, "switch_contribution": "armed"}
        return {"channel": channel, "decision": "ALLOWED",
                "reason_code": "airplane_loopback_allow" if armed
                else "airplane_off_switch_inactive",
                "enforcement_kind": kind,
                "switch_contribution": "armed" if armed else "inactive"}
    if armed:
        return {"channel": channel, "decision": "BLOCKED",
                "reason_code": "airplane_armed_" + channel + "_blocked",
                "enforcement_kind": kind, "switch_contribution": "armed"}
    if channel == "model_provider_catalog_fetch":
        return {"channel": channel, "decision": "BLOCKED",
                "reason_code": "standing_env_opencode_disable_models_fetch",
                "enforcement_kind": kind, "switch_contribution": "standing"}
    return {"channel": channel, "decision": "ALLOWED",
            "reason_code": "airplane_off_switch_inactive",
            "enforcement_kind": kind, "switch_contribution": "inactive"}


def status(config: dict) -> dict:
    """Flag state + the closed enforcement projection over all channels."""
    state = flag(config)
    return {"schema": FACE_SCHEMA, **state,
            "channels": [{"channel": channel, "enforcement_kind": kind,
                          "endpoint_gated": gated}
                         for channel, kind, gated in CHANNELS]}


def enforce_bridge_egress(config: dict, channel: str,
                          endpoint: str | None = None,
                          provider_id: str | None = None) -> None:
    """Live gate for bridge dispatch paths that can reach a remote endpoint.
    Raises the channel's typed code when the armed decision is BLOCKED.
    Inactive/off → returns silently (faces keep their exact status quo)."""
    args: dict = {"channel": channel}
    if endpoint is not None:
        args["endpoint"] = endpoint
    if provider_id is not None:
        args["provider_id"] = provider_id
    row = decision(args, config)
    if row["decision"] == "BLOCKED" and row["switch_contribution"] == "armed":
        raise NotConnected(row["reason_code"])


def airplane_call(method: str, args: dict, config: dict) -> dict:
    if method == "airplane.status":
        if not isinstance(args, dict) or args:
            raise NotConnected("airplane_status_args_invalid")
        return status(config)
    if method == "airplane.set":
        return set_flag(args, config)
    if method == "airplane.egress_decision":
        return decision(args, config)
    raise NotConnected("airplane_method_not_connected:" + method)
