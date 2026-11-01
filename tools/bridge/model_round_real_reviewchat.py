# -*- coding: utf-8 -*-
"""桥真模型轮·review_chat.py 面真轮探针（2026-10-30，施工波二轮）。

上轮（docs/evidence/施工波-20261030/桥-增强三式.md 诚实边界 §四.1）式一/式二
全为替身合成；本轮 oc28(:43127) 常驻活着，打真模型轮。本探针＝review_chat.ask
真实径：上下文三投影仍为合成夹具（test_f84_review_chat_wiring 同形，合成材料，
非真实案件），service_client/create_public_session/prompt 全走真实产品服务
（opencode_registration 注册文件；凭据运行时读取，不打印不落盘）。

探针的产物是如实记录：真回答＝REVIEWCHAT_REAL_ROUND_PASS；typed 拒＝
REVIEWCHAT_REAL_ROUND_TYPED_REFUSAL:<code>（同样 exit 0——typed 拒是合法观测
结果，不许装绿也不算探针失败）。oc28(:43127) 只经公开 HTTP API 只读/对话，
绝不重启不杀（勿动勿杀红线）。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "implementation" / "python"))
sys.path.insert(0, str(ROOT / "implementation" / "tests"))

import review_chat  # noqa: E402
import test_f84_review_chat_wiring as base  # noqa: E402

REGISTRATION = Path.home() / "AppData" / "Roaming" / "Juscite" / "state" \
    / "opencode" / "service-local.json"
BATCH = "brt-real-round"
SCOPE = {"kind": "matter", "matterId": "m-real-round"}

CONFIG = {
    "opencode_registration": str(REGISTRATION),
    # 会话注册表落一次性临时合成根：零产品状态根触碰。
    "review_chat_state_root": tempfile.mkdtemp(prefix="review-chat-real-"),
    "harness_python": sys.executable,
}


def main() -> int:
    print("face:", review_chat.REVIEW_CHAT_FACE_NOTE)
    print("registry_root:", CONFIG["review_chat_state_root"])
    if not REGISTRATION.exists():
        print("REVIEWCHAT_REAL_ROUND_NO_REGISTRATION:", str(REGISTRATION))
        return 0
    docs = {
        "tabular.read": base.tabular_read_doc(),
        "tabular.review_status": base.review_status_doc(),
        "harness.review_support_read": base.support_read_doc(),
    }
    calls: list = []

    def _fake(method, args, config):
        calls.append(method)
        return docs[method]

    with unittest.mock.patch.object(review_chat, "_harness_call", _fake):
        try:
            answer = review_chat.review_chat_ask({
                "review_batch_id": BATCH,
                "question": "真模型轮探针（合成材料，非真实案件）：合同金额列"
                            "的当前值是多少？只回答值本身。",
                "scope": SCOPE,
            }, CONFIG)
        except Exception as exc:  # 探针如实记录 typed 拒（不装绿不吞栈）。
            code = getattr(exc, "code", None) or str(exc)
            print("outcome: TYPED_REFUSAL")
            print("exc_type:", type(exc).__name__)
            print("code:", code)
            print("uncertain:", getattr(exc, "uncertain", None))
            print("harness_calls:", calls)
            reg = review_chat._registry_file(CONFIG)
            print("registry_file_exists:", bool(reg and reg.exists()))
            print("REVIEWCHAT_REAL_ROUND_TYPED_REFUSAL:" + str(code))
            return 0
    print("outcome: ANSWER")
    print("sessionRef:", answer.get("sessionRef"))
    print("continuity:", json.dumps(answer.get("continuity"), ensure_ascii=False))
    print("reply_head:", (answer.get("reply") or "")[:120].replace("\n", " "))
    print("harness_calls:", calls)
    reg = review_chat._registry_file(CONFIG)
    print("registry_file_exists:", bool(reg and reg.exists()))
    print("REVIEWCHAT_REAL_ROUND_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
