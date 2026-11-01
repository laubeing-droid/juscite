# -*- coding: utf-8 -*-
"""W4-U32 / F10 案件库 at-rest 加密——产品面接线验收。

06 F10（加密持久状态和 CAS 可恢复；无密钥不可读且不明文降级）的产品半边：

* atrest.status / atrest.provision 冻结方法组（in-process 同 legal_entry.call
  同径）：provision=get-or-create 幂等（不轮换不重写）；回执零密钥字节
  （sha256+掩码形）；唯一持久化＝F12 保险库登记位 lvyin.f10/
  atrest-aes-256-gcm-v1（DPAPI blob），登记文件与回执零明文密钥。
* material.parse_* 加密态（config.f10_atrest=on）：密钥经保险库解密随调用
  交给 anonymizer 页载荷信封面（conftest 钉定同波 w4-u32 anonymizer 分支）
  ——盘上页文件＝信封（无密钥直读不可读），带钥回读可恢复；零明文降级：
  未 provision 时 parse_process typed 拒且零明文文件落盘。
* v1 缺省 off＝明文 JSON 形态字节不变（权限闸+假名 preserved）。
* 密钥不落库不明文日志：vault/parse state 全树扫描密钥字节零命中；
  回执只带掩码形。材料全合成（白页 BLANK 快路径零引擎负载）。
"""
import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))

import atrest_key as ak  # noqa: E402
import credential_vault as cv  # noqa: E402
import legal_entry  # noqa: E402

from bridge_errors import NotConnected  # noqa: E402


def _white(w: int = 992, h: int = 1403) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (w, h), 255).save(buf, format="PNG")
    return buf.getvalue()


def _write_corpus(root: Path, pages: list[bytes]) -> Path:
    corpus = root / "corpus"
    (corpus / "pages" / "doc_0001").mkdir(parents=True)
    page_files = []
    for i, payload in enumerate(pages):
        rel = f"pages/doc_0001/p{i + 1:04d}.png"
        (corpus / rel).write_bytes(payload)
        page_files.append({"page": i + 1, "kind": "TEXT", "png": rel,
                           "sha256": hashlib.sha256(payload).hexdigest(),
                           "bytes": len(payload)})
    manifest = {"schema": "juscite-e12-corpus/1", "seed": 7,
                "pages": len(pages),
                "documents": [{"doc_id": "doc_0001", "doc_code": "SJ-0001",
                               "page_count": len(pages),
                               "pdf": "docs/doc_0001.pdf",
                               "pdf_bytes": 1, "pdf_sha256": "0" * 64,
                               "page_files": page_files}]}
    (corpus / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return corpus


def _page_file(state_root: Path, batch_id: str, page: int) -> Path:
    return (Path(state_root) / "material-parse" / batch_id / "pages"
            / "doc_0001" / f"p{page:04d}.json")


class F10AtrestWiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="juscite-f10-wiring-"))
        self.vault_root = self.tmp / "vault"
        self.state_root = self.tmp / "state"
        self.config = {"anonymizer_contract": "p09/p10",
                       "material_parse_state_root": str(self.state_root),
                       "vault_state_root": str(self.vault_root)}
        self.corpus = _write_corpus(self.tmp, [_white(), _white()])

    # ------------------------------------------------------------- 方法组
    def test_frozen_method_group_disjoint(self):
        self.assertEqual(legal_entry.ATREST_METHODS,
                         frozenset({"atrest.status", "atrest.provision"}))
        groups = [v for k, v in vars(legal_entry).items()
                  if k.endswith("_METHODS") and isinstance(v, frozenset)]
        for group in groups:
            if group is legal_entry.ATREST_METHODS:
                continue
            self.assertFalse(legal_entry.ATREST_METHODS & group)

    # ------------------------------------------------------- 密钥供给面
    def test_status_unprovisioned_and_unconfigured(self):
        status = legal_entry.call("atrest.status", {}, self.config)
        self.assertFalse(status["provisioned"])
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("atrest.status", {}, {"f10_atrest": "on"})
        self.assertIn("vault_state_root_not_configured", str(caught.exception))

    def test_provision_idempotent_and_vault_blob_only(self):
        first = legal_entry.call("atrest.provision", {}, self.config)
        self.assertTrue(first["created"]) and self.assertTrue(first["provisioned"])
        self.assertIn("key_sha256", first) and self.assertIn("masked", first)
        second = legal_entry.call("atrest.provision", {}, self.config)
        self.assertFalse(second["created"])                    # 幂等不轮换
        self.assertEqual(first["key_sha256"], second["key_sha256"])
        # 回执零密钥字节
        raw_key = ak.resolve_atrest_key(self.config)
        self.assertNotIn(base64.b64encode(raw_key).decode(), json.dumps(first))
        self.assertNotIn(raw_key.hex(), json.dumps(first))
        # 唯一持久化＝F12 登记 DPAPI blob；登记文件零明文密钥
        entry_path = (self.vault_root / "credentials" / ak.ATREST_KEY_SERVICE
                      / (ak.ATREST_KEY_ACCOUNT + ".json"))
        self.assertTrue(entry_path.is_file())
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        self.assertEqual(entry["backend"], "dpapi")
        self.assertNotIn(raw_key, entry_path.read_bytes())     # 密钥不落盘
        # 解密取钥与登记 sha 一致、长度 32
        self.assertEqual(hashlib.sha256(raw_key).hexdigest(), first["key_sha256"])
        self.assertEqual(len(raw_key), 32)

    def test_resolve_without_provision_typed(self):
        with self.assertRaises(ak.AtrestKeyError) as caught:
            ak.resolve_atrest_key(self.config)
        self.assertEqual(str(caught.exception), "f10_atrest_key_not_provisioned")

    # --------------------------------------------------- material 加密态
    def test_material_encrypted_via_bridge(self):
        cfg = dict(self.config, f10_atrest="on")
        # 零明文降级：未 provision 时加密态 process=typed 拒且零文件落盘
        reg = legal_entry.call("material.parse_register",
                               {"corpus_root": str(self.corpus)}, cfg)
        batch_id = reg["batch_id"]
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("material.parse_process", {"batch_id": batch_id},
                             cfg)
        self.assertIn("f10_atrest_key_not_provisioned", str(caught.exception))
        self.assertFalse((self.state_root / "material-parse" / batch_id
                          / "pages").exists())
        # provision 后全链加密态
        legal_entry.call("atrest.provision", {}, cfg)
        summary = legal_entry.call("material.parse_process",
                                   {"batch_id": batch_id}, cfg)
        self.assertEqual(summary["processed"], 2)
        from legal_anonymizer.security import atrest_crypto
        for page in (1, 2):
            raw = _page_file(self.state_root, batch_id, page).read_bytes()
            self.assertEqual(raw[:8], atrest_crypto.MAGIC)     # 盘上＝信封
            self.assertNotIn(b'"signal"', raw)                 # 明文特征零命中
        record = legal_entry.call(
            "material.parse_page",
            {"batch_id": batch_id, "doc_id": "doc_0001", "page": 1}, cfg)
        self.assertEqual(record["signal"], "BLANK")
        report = legal_entry.call("material.parse_report",
                                  {"batch_id": batch_id}, cfg)
        self.assertEqual(report["completed"], 2)
        # 密钥不落库：parse state 全树扫描密钥字节零命中
        key = ak.resolve_atrest_key(cfg)
        hits = [str(p) for p in self.state_root.rglob("*")
                if p.is_file() and key in p.read_bytes()]
        self.assertEqual(hits, [])

    def test_material_v1_default_off_unchanged(self):
        reg = legal_entry.call("material.parse_register",
                               {"corpus_root": str(self.corpus)}, self.config)
        summary = legal_entry.call("material.parse_process",
                                   {"batch_id": reg["batch_id"]}, self.config)
        self.assertEqual(summary["processed"], 2)
        raw = _page_file(self.state_root, reg["batch_id"], 1).read_bytes()
        self.assertEqual(raw[:1], b"{")                        # v1 明文 JSON
        json.loads(raw)                                        # 可解码


if __name__ == "__main__":
    unittest.main()
