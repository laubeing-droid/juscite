"""W2a-U15 / F38+F44 附件闸桥面测试：冻结方法组、fail-closed 配置面、
最终字节复扫（F44 反例拒发）与授权绑定经桥同进程闭环（anonymizer 仓
w2a-u15 分支 attachment_gate_service 公开面）。

真 OCR 材料化与双 profile 验收由 tools/PENDING_OWNER_f38_f44_attachment_gate_recon.py
承担；此处为引擎无关的桥面合同（全部合成材料）。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))

_SRC = os.environ.get("JUSCITE_ANONYMIZER_SRC")
if not _SRC:
    # 同波 worktree 相对推断（与 recon 工具同式）：裸跑验收命令也能命中
    # w2a-u15 分支源，而非全局 .pth 指向的其他分支检出。
    # 向上搜索而非固定深度（W2a-U17 合并时公开改口：parents[7] 仅在 worktree
    # 布局成立，主仓树浅两层收集即 IndexError；两布局命中同一目标路径）。
    _root = next((_p for _p in Path(__file__).resolve().parents
                  if (_p / "legal-cn-anonymizer工作区").is_dir()), None)
    _guess = (_root / "legal-cn-anonymizer工作区"
              / "legal-cn-anonymizer" / ".local" / "worktrees" / "w4-u32"
              / "src") if _root else None
    if _guess and (_guess / "legal_anonymizer" / "application"
                   / "attachment_gate_service.py").is_file():
        _SRC = str(_guess)
if _SRC:
    sys.path.insert(0, _SRC)

_ags = None
try:
    from legal_anonymizer.application import (
        attachment_gate_service as _ags,
    )
except ImportError:                                    # pragma: no cover
    _ags = None
if _ags is None and _SRC:
    # 全套跑时字母序更早的测试可能已把其他分支检出缓存进 sys.modules；
    # 逐出后按本文件的钉定路径重导入（保持本桥面测试对 w2a-u15 面封闭）。
    import importlib
    for _mod in [m for m in sys.modules if m == "legal_anonymizer"
                 or m.startswith("legal_anonymizer.")]:
        del sys.modules[_mod]
    try:
        _ags = importlib.import_module(
            "legal_anonymizer.application.attachment_gate_service")
    except ImportError:                                # pragma: no cover
        _ags = None

from legal_entry import call, NotConnected, ATTACHMENT_GATE_METHODS

PHONE = "13700005555"
ID_CARD = "110101199003078670"


def _cfg(**extra):
    config = {"anonymizer_contract": "p09/p10"}
    config.update(extra)
    return config


def _serialize_pdf(bodies: dict[int, bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in sorted(bodies):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + bodies[num] + b"\nendobj\n"
    size = max(bodies) + 1
    xref = len(out)
    out += f"xref\n0 {size}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, size):
        if num in offsets:
            out += f"{offsets[num]:010d} 00000 n \n".encode()
        else:
            out += b"0000000000 65535 f \n"
    out += (f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n"
            f"%%EOF\n").encode()
    return bytes(out)


def _blackbox_pdf() -> bytes:
    content = ("\n".join([
        "BT /F1 12 Tf 0 0 0 rg",
        "1 0 0 1 40 760 Td (synthetic benign header) Tj",
        f"1 0 0 1 40 700 Td (tel {PHONE}) Tj",
        f"1 0 0 1 40 670 Td (id {ID_CARD}) Tj",
        "ET",
        "0 0 0 rg 36 662 300 52 re f",
    ])).encode()
    return _serialize_pdf({
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 6 0 R >> >> /Contents 5 0 R >>"),
        5: (f"<< /Length {len(content)} >>\nstream\n").encode()
           + content + b"\nendstream",
        6: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    })


def _clean_image_pdf(tmp: Path) -> bytes:
    import io
    import zlib

    from PIL import Image
    img = Image.new("L", (200, 260), 255)
    comp = zlib.compress(img.tobytes())
    content = b"q 200 0 0 260 0 0 cm /Im0 Do Q"
    return _serialize_pdf({
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 260] "
            b"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>"),
        4: (f"<< /Type /XObject /Subtype /Image /Width 200 /Height 260 "
            f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter "
            f"/FlateDecode /Length {len(comp)} >>\nstream\n").encode()
           + comp + b"\nendstream",
        5: (f"<< /Length {len(content)} >>\nstream\n").encode()
           + content + b"\nendstream",
    })


@unittest.skipIf(_ags is None, "anonymizer w2a-u15 src not importable")
def _pin_face():
    """运行时钉定本波面。全套单进程内多波桥测试共存（U16 batch 面与 U15
    attachment 面基于 anonymizer 平行分支、互不含对方模块），后导入波次的
    模块级钉定会改写 sys.modules；本文件测试类 setUpClass 重钉回 w2a-u15，
    保证 legal_entry 桥内延迟 import 恒命中本波面（W2a-U16 合并时补）。"""
    sys.path.insert(0, _SRC)  # 本波面提到 path 最前（他波后插入者会压前）
    if not _SRC:
        return None
    import importlib
    for m in [m for m in sys.modules if m == "legal_anonymizer"
              or m.startswith("legal_anonymizer.")]:
        del sys.modules[m]
    return importlib.import_module(
        "legal_anonymizer.application.attachment_gate_service")


class F38F44BridgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_face()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.blackbox = self.tmp / "ce_blackbox.pdf"
        self.blackbox.write_bytes(_blackbox_pdf())
        self.clean = self.tmp / "clean.pdf"
        self.clean.write_bytes(_clean_image_pdf(self.tmp))

    def tearDown(self):
        self._tmp.cleanup()

    def test_frozen_method_group(self):
        self.assertEqual(ATTACHMENT_GATE_METHODS, frozenset({
            "attachment.scan", "attachment.gate", "attachment.authorize"}))

    def test_unknown_method_stays_not_connected(self):
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:attachment.explode"):
            call("attachment.explode", {}, _cfg())

    def test_fail_closed_config(self):
        with self.assertRaisesRegex(
                NotConnected, "anonymizer_p09_p10_not_configured"):
            call("attachment.scan", {"pdf_path": "x.pdf"}, {})
        with self.assertRaisesRegex(
                NotConnected, "attachment_scan_path_required"):
            call("attachment.scan", {}, _cfg())
        for args in ({"matter_id": "m"}, {"attachment_id": "a"}):
            with self.assertRaisesRegex(
                    NotConnected,
                    "attachment_gate_matter_id_required|"
                    "attachment_gate_attachment_id_required"):
                call("attachment.authorize", args,
                     _cfg(attachment_gate_state_root=str(self.tmp / "st")))
        with self.assertRaisesRegex(
                NotConnected, "attachment_gate_state_root_not_configured"):
            call("attachment.authorize",
                 {"matter_id": "m", "attachment_id": "a"}, _cfg())
        with self.assertRaisesRegex(
                NotConnected, "attachment_gate_params_invalid"):
            call("attachment.scan", "not-a-dict", _cfg())

    def test_gate_needs_ocr_face_config(self):
        with self.assertRaisesRegex(
                NotConnected, "ocr_ports_state_root_not_configured"):
            call("attachment.gate",
                 {"matter_id": "m", "attachment_id": "a",
                  "source_pdf": str(self.clean)},
                 _cfg(attachment_gate_state_root=str(self.tmp / "st")))
        with self.assertRaisesRegex(
                NotConnected, "ocr_baseline_interpreter_not_configured"):
            call("attachment.gate",
                 {"matter_id": "m", "attachment_id": "a",
                  "source_pdf": str(self.clean)},
                 _cfg(attachment_gate_state_root=str(self.tmp / "st"),
                      ocr_ports_state_root=str(self.tmp / "ocr")))

    def test_scan_blackbox_rejected_through_bridge(self):
        report = call("attachment.scan",
                      {"pdf_path": str(self.blackbox)}, _cfg())
        self.assertEqual(report["status"], "rejected")
        self.assertIn("text_layer_present", report["reasons"])
        self.assertIn("text_layer_pii", report["reasons"])
        # F44 硬红线：surface 绝不回传
        blob = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(PHONE, blob)
        self.assertNotIn(ID_CARD, blob)

    def test_scan_clean_image_only(self):
        report = call("attachment.scan",
                      {"pdf_path": str(self.clean)}, _cfg())
        self.assertEqual(report["status"], "clean", report["findings"])

    def test_scan_unreadable_source_fail_closed(self):
        missing = self.tmp / "missing.pdf"
        with self.assertRaisesRegex(
                NotConnected,
                "attachment_gate_failed:attachment_source_unreadable"):
            call("attachment.scan", {"pdf_path": str(missing)}, _cfg())

    def test_authorize_no_verdict_refused(self):
        out = call("attachment.authorize",
                   {"matter_id": "m-none", "attachment_id": "a-none"},
                   _cfg(attachment_gate_state_root=str(self.tmp / "st")))
        self.assertEqual(out["decision"], "REFUSED")
        self.assertEqual(out["reason"], "no_verdict")
        self.assertFalse(out["egress_authorized"])
        self.assertEqual(out["never_backfill_kinds"],
                         ["id_card", "phone", "personal_address"])

    def test_gate_without_decision_refused_not_fake_success(self):
        # OCR 证据缺失＝闸链第一步即具名拒绝（不假成功；无 OCR 状态面）
        out = call("attachment.gate",
                   {"matter_id": "m1", "attachment_id": "att1",
                    "source_pdf": str(self.clean)},
                   _cfg(attachment_gate_state_root=str(self.tmp / "st"),
                        ocr_ports_state_root=str(self.tmp / "ocr"),
                        ocr_baseline_interpreter="nonexistent.exe"))
        self.assertEqual(out["verdict"], "REFUSED")
        self.assertEqual(out["reasons"], ["ocr_evidence_required"])

    def test_responses_carry_no_material_paths(self):
        report = call("attachment.scan",
                      {"pdf_path": str(self.blackbox)}, _cfg())
        blob = json.dumps(report, ensure_ascii=False)
        # 原件路径不回传（红线：原件与身份映射不出 anonymizer 面之投影纪律）
        self.assertNotIn(str(self.blackbox), blob)
        self.assertNotIn("pdf_path", blob)


if __name__ == "__main__":
    unittest.main()
