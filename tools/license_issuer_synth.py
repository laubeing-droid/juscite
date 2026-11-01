# -*- coding: utf-8 -*-
"""合成许可签发设施（工单 W5-U01；裁决 #13-19 统一合成先行）。

本文件是**施工/测试设施**，位于 tools/（施工区），不是发行物：
  - F78/F79 真实商业签发私钥与商业服务端按裁决 #13-19「统一合成先行，
    真实设施 v2 商业化时补」；本设施即该裁决的合成替代面＋具名回收点：
    v2 商业化时以真实签发服务/CA 替换本文件，接口形态（POST /v1/activate
    → 离线令牌；POST /v1/check → {status}）保持不变即产品面零改。
  - Ed25519 私钥只在本文件与运行时签发方进程内存/签发方 state 目录存在；
    产品发行树（implementation/）结构性无私钥路径（license_verify.py 只
    PublicKey.verify）。recon 以 git tracked 全文件字节扫描钉死「私钥不
    入发行物」。
  - 令牌形态与产品面合同（lvyin-license-token/1）逐键同源：canonical
    payload JSON bytes ＋ Ed25519 签名；product 面定义见
    implementation/python/license_verify.py（本文件 import 它取 schema
    常量——签发/验签同一合同单一来源，零第二权威）。

CLI（回环合成签发服务）：
  python -X utf8 tools/license_issuer_synth.py --seed seed.json \
      --issuer-state <dir> --host 127.0.0.1 --port 0 --serve
  seed.json：[{"license_key","license_id","subject","days","features",
               "revoked":bool}]（全合成）；服务启动时生成/复用密钥对
  （<issuer-state>/issuer-private-key.b64——只落签发方 state，绝不入
  juscite 仓），/v1/activate 以 license_key 查 seed 换令牌（绑定请求方
  device_fp_hash），/v1/check 按 revoked 种子应答 valid/revoked。
  --print-pubkey：启动时向 stdout 打一行 b64 公钥（recon/测试取作部署
  信任锚 config.license_trusted_pubkeys）。

全合成材料；密钥运行时生成；零真实外联（127.0.0.1 回环）。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

from license_verify import (  # noqa: E402（sys.path 先行）
    ALGORITHM, PAYLOAD_SCHEMA, TOKEN_SCHEMA, _canonical,
)

_ISSUER_PRIV_FILENAME = "issuer-private-key.b64"


def _raw_encoding():
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, PublicFormat, NoEncryption)
    return Encoding, PublicFormat, PrivateFormat, NoEncryption


def generate_keypair() -> tuple[bytes, bytes]:
    """运行时生成 Ed25519 密钥对（合成签发；私钥 32B raw）。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey)
    Encoding, PublicFormat, PrivateFormat, NoEncryption = _raw_encoding()
    priv = Ed25519PrivateKey.generate()
    raw_priv = priv.private_bytes(
        encoding=Encoding.Raw, format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption())
    raw_pub = priv.public_key().public_bytes(
        encoding=Encoding.Raw, format=PublicFormat.Raw)
    return raw_priv, raw_pub


def sign_payload(raw_priv: bytes, payload_fields: dict) -> dict:
    """canonical payload bytes ＋ Ed25519 签名 → 令牌信封（合同同源）。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey)
    payload = {"schema": PAYLOAD_SCHEMA, **payload_fields}
    payload_bytes = _canonical(payload)
    signature = Ed25519PrivateKey.from_private_bytes(raw_priv).sign(
        payload_bytes)
    return {"schema": TOKEN_SCHEMA, "algorithm": ALGORITHM,
            "payload_b64": base64.b64encode(payload_bytes).decode("ascii"),
            "signature_b64": base64.b64encode(signature).decode("ascii")}


def issue_for_device(raw_priv: bytes, seed_row: dict,
                     device_fp_hash: str, now: float | None = None) -> dict:
    """按种子行签发绑定设备的令牌（days 合成有效期；not_before=now）。"""
    now = time.time() if now is None else float(now)
    return sign_payload(raw_priv, {
        "license_id": str(seed_row["license_id"]),
        "subject": str(seed_row["subject"]),
        "device_fp_hash": str(device_fp_hash),
        "not_before": repr(now),
        "not_after": repr(now + float(seed_row.get("days", 365)) * 86400.0),
        "features": [str(f) for f in (seed_row.get("features") or [])],
    })


# ---------------------------------------------------------------------- #
# 回环合成签发服务（POST /v1/activate、POST /v1/check）
# ---------------------------------------------------------------------- #

class _IssuerState:
    def __init__(self, seed_rows: list, issuer_state_dir: Path) -> None:
        self.rows = {str(r["license_key"]): r for r in seed_rows}
        self.by_id = {str(r["license_id"]): r for r in seed_rows}
        self.dir = issuer_state_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        priv_path = self.dir / _ISSUER_PRIV_FILENAME
        if priv_path.is_file():
            raw_priv = base64.b64decode(
                priv_path.read_text(encoding="ascii").strip())
        else:
            raw_priv, raw_pub = generate_keypair()
            priv_path.write_text(
                base64.b64encode(raw_priv).decode("ascii") + "\n",
                encoding="ascii")
            (self.dir / "issuer-public-key.b64").write_text(
                base64.b64encode(raw_pub).decode("ascii") + "\n",
                encoding="ascii")
        self.raw_priv = raw_priv
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey)
        Encoding, PublicFormat, _, _ = _raw_encoding()
        self.raw_pub = Ed25519PrivateKey.from_private_bytes(
            raw_priv).public_key().public_bytes(
                encoding=Encoding.Raw, format=PublicFormat.Raw)


def _handler(state: _IssuerState):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802（http.server 契约）
            try:
                length = int(self.headers.get("Content-Length") or 0)
                request = json.loads(self.rfile.read(length)
                                     .decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._json(400, {"code": "license_request_malformed"})
            if self.path == "/v1/activate":
                row = state.rows.get(str(request.get("license_key") or ""))
                if row is None:
                    return self._json(404, {"code": "license_key_unknown"})
                fp = str(request.get("device_fp_hash") or "")
                if len(fp) != 32:
                    return self._json(400, {"code": "device_fp_hash_invalid"})
                return self._json(200, issue_for_device(
                    state.raw_priv, row, fp))
            if self.path == "/v1/check":
                row = state.by_id.get(str(request.get("license_id") or ""))
                if row is None:
                    return self._json(404, {"code": "license_id_unknown"})
                status = "revoked" if row.get("revoked") else "valid"
                return self._json(200, {"status": status})
            return self._json(404, {"code": "endpoint_unknown"})

        def log_message(self, fmt, *args):  # 静音访问日志
            pass
    return Handler


def serve(seed_path: Path, issuer_state_dir: Path, host: str, port: int,
          print_pubkey: bool) -> int:
    seed_rows = json.loads(seed_path.read_text(encoding="utf-8"))
    state = _IssuerState(seed_rows, issuer_state_dir)
    server = ThreadingHTTPServer((host, port), _handler(state))
    if print_pubkey:
        print(base64.b64encode(state.raw_pub).decode("ascii"), flush=True)
    print(json.dumps({"serving": f"http://{host}:{server.server_address[1]}",
                      "ready": True}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True,
                        help="合成许可种子 JSON（license_key→许可字段）")
    parser.add_argument("--issuer-state", type=Path, required=True,
                        help="签发方 state 目录（私钥唯一落盘处，非发行物）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--print-pubkey", action="store_true")
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if not args.serve:
        # 离线一次性模式：签发一枚绑定当前设备指纹的令牌写到 stdout。
        seed_rows = json.loads(args.seed.read_text(encoding="utf-8"))
        state = _IssuerState(seed_rows, args.issuer_state)
        sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
        from license_verify import device_fingerprint
        fp = device_fingerprint()["fingerprint_hash"]
        print(json.dumps(issue_for_device(state.raw_priv, seed_rows[0], fp),
                         ensure_ascii=False))
        return 0
    return serve(args.seed, args.issuer_state, args.host, args.port,
                 args.print_pubkey)


if __name__ == "__main__":
    raise SystemExit(main())
