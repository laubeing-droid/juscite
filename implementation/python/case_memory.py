"""F32 案件级记忆体系（对话蒸馏＋TTL）产品面（W4-U34）。

（产品方法名 memory.extract——「蒸馏」是功能语义词；E23 冻结方法组
禁词纪律不收 distill 词条，公开面命名避开。）

权威：06 F32 行（v1.5·TTL 差异点，2026-10-14 用户裁定）＋17 卡「公开
DTO/权限→既有 command_tx 和 MatterStore/CAS→事务幂等→公开回读；新场景
字段在同 owner 扩不新库」。记忆账主=harness（schema v31
case_memory_entries，六方法封闭注册）；本面只做两件事：

1. 确定性蒸馏（memory.extract）：会话转写 → 记忆候选。正则标记闭集
   （约束/偏好/事实三分类，固定匹配序），零模型零网络零时钟——同输入
   同字节（canonical JSON：sort_keys＋紧凑分隔符，sha256 可复算）。
   候选强制携带来源 ref（host 会话转写 digest，封闭六字段）与
   ttlSeconds（按 kind 冻结表，TTL 必带）。
2. 路由（memory.propose/confirm/revoke/read/effective_list/pending_list）：
   经 legal_entry 封闭 provider dispatch（--memory-json 信封）到 harness
   公开面。确认闸在 harness（memory_confirm 唯一生效转移，须人工决定
   ref）；本面无任何第二写通道。「目标账本不被延后」＝蒸馏与路由对
   E18 goal 账与 E15/E17 账只读消费（候选可钉 goal ref 只读引用），
   绝不写、绝不阻塞、绝不改写其语义。

fail-closed：转写形状出闭集/空转写/未配置桥一律具名拒，绝不 stub 成功。
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA = "juscite-f32-distillation/1"

# 确定性标记闭集（固定匹配序：constraint > preference > fact；每条消息
# 至多产出一个候选＝首个命中规则）。禁模型模糊猜测——工作区红线。
MARKER_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("constraint", re.compile(r"务必|必须|不得|不要|禁止|千万")),
    ("preference", re.compile(r"以后|一律|优先|尽量|偏好")),
    ("fact", re.compile(r"事实[：:]|经核[：:]|已核实[：:]|确认[：:]")),
)

# TTL 冻结表（秒）：按 kind 确定性赋值（90 日/180 日/30 日）。TTL 差异点
# ＝每条记忆必带；生效时钟从人工确认时点起算（harness confirm 面）。
TTL_BY_KIND: dict[str, int] = {
    "fact": 7_776_000,
    "preference": 15_552_000,
    "constraint": 2_592_000,
}

_ROLES = frozenset({"user", "assistant"})
_TEXT_MAX = 2000


class DistillationError(ValueError):
    """具名蒸馏失败（转写形状出闭集等）；绝不静默产出候选。"""


def canonical_bytes(payload: Any) -> bytes:
    """Byte-deterministic canonical JSON（同输入同字节——硬点⑤）。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _validate_transcript(transcript: Any) -> list[dict]:
    if not isinstance(transcript, list) or not transcript:
        raise DistillationError("transcript_invalid:empty_or_not_list")
    for index, message in enumerate(transcript):
        if not isinstance(message, dict) or set(message) != {"role", "text"}:
            raise DistillationError(
                f"transcript_message_fields_not_closed:index={index}")
        if message["role"] not in _ROLES:
            raise DistillationError(f"transcript_role_unknown:index={index}")
        if (not isinstance(message["text"], str) or not message["text"].strip()
                or len(message["text"]) > _TEXT_MAX):
            raise DistillationError(f"transcript_text_invalid:index={index}")
    return transcript


def distill(transcript: list[dict], *, session_id: str, matter_id: str) -> dict:
    """确定性蒸馏：会话转写 → 记忆候选（同输入同字节）。

    每条候选：确定性 id（转写摘要前缀＋消息序号）、kind（首条命中规则）、
    全文 text、按 kind 冻结 TTL、来源 ref（host 会话转写 digest 封闭六字
    段）。产出即候选（proposed 形态的原料）——生效唯一通道是 harness
    确认闸，本面从不签发生效记忆。
    """
    _validate_transcript(transcript)
    if not isinstance(session_id, str) or not session_id.strip():
        raise DistillationError("session_id_invalid")
    if not isinstance(matter_id, str) or not matter_id.strip():
        raise DistillationError("matter_id_invalid")
    transcript_sha256 = hashlib.sha256(canonical_bytes(transcript)).hexdigest()
    source_ref = {"owner": "host", "kind": "session_transcript",
                  "id": session_id, "version": "1", "matterId": matter_id,
                  "digest": transcript_sha256}
    candidates: list[dict] = []
    for index, message in enumerate(transcript):
        for kind, pattern in MARKER_RULES:  # 固定匹配序＝确定性分类
            if pattern.search(message["text"]):
                candidates.append({
                    "candidateId": f"mem-{transcript_sha256[:16]}-{index:04d}",
                    "kind": kind,
                    "text": message["text"],
                    "ttlSeconds": TTL_BY_KIND[kind],
                    "sourceRef": dict(source_ref),
                    "messageIndex": index,
                })
                break
    return {
        "schema": SCHEMA,
        "sessionId": session_id,
        "matterId": matter_id,
        "transcriptSha256": transcript_sha256,
        "candidateCount": len(candidates),
        "candidates": candidates,
    }


def to_harness_memory(candidate: dict) -> dict:
    """蒸馏候选 → harness 记忆载荷闭集 {memoryId, content, sourceRef,
    ttlSeconds}（harness _memory_validate 闭集校验；messageIndex 等蒸馏
    报告字段不出产品面）。"""
    return {"memoryId": candidate["candidateId"],
            "content": {"kind": candidate["kind"], "text": candidate["text"]},
            "sourceRef": candidate["sourceRef"],
            "ttlSeconds": candidate["ttlSeconds"]}


def memory_call(method: str, args: dict, config: dict):
    """memory.* 产品方法组入口（legal_entry 封闭派发：未知方法在 call()
    处已 method_not_connected，不进本面）。extract 本地确定性执行；其余
    薄路由到 harness --memory-json 信封（真值校验全在 harness 面——确认
    闸/TTL/撤销语义不在产品侧复制）。"""
    if not isinstance(args, dict):
        raise DistillationError("memory_params_invalid")
    if method == "memory.extract":
        return distill(args["transcript"], session_id=args["sessionId"],
                       matter_id=args["matterId"])
    from legal_entry import _harness_provider_entry
    if method == "memory.propose":
        surface_args = {"actor_id": args["actor_id"], "scope": args["scope"],
                        "key": args["key"],
                        "memory": to_harness_memory(args["candidate"])}
    elif method == "memory.confirm":
        surface_args = {"actor_id": args["actor_id"], "scope": args["scope"],
                        "key": args["key"],
                        "confirmation": {"memoryId": args["memoryId"],
                                         "decisionRef": args["decisionRef"]}}
    elif method == "memory.revoke":
        surface_args = {"actor_id": args["actor_id"], "scope": args["scope"],
                        "key": args["key"],
                        "revocation": {"memoryId": args["memoryId"],
                                       "reasonRef": args["reasonRef"]}}
    elif method == "memory.read":
        surface_args = {"scope": args["scope"],
                        "memory_id": args["memoryId"],
                        "revision": args.get("revision")}
    elif method == "memory.effective_list":
        surface_args = {"scope": args["scope"]}
    else:  # memory.pending_list
        surface_args = {"scope": args["scope"]}
    return _harness_provider_entry("harness.memory_" + method.split(".", 1)[1],
                                   surface_args, config, flag="memory-json",
                                   surface="memory")
