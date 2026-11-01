# -*- coding: utf-8 -*-
"""施工波二轮·LPR 尾巴三件① acceptance: calc.interest LPR 数据包取数通道。

只做取数通道：calc.interest 的段年利率改由法源数据包（lpr-history.json +
pack.meta 版本锚）按「不晚于该段起日的最近一期」回填；域级规则（四倍上限/
强制分段/砍头息/复利）不在本面、维持 JC 完整档挂起位（决策台账:69）——
本文件全部数据为工程合成夹具（数值、日期均非官方口径，仅验通道机制），
计算仍整包下沉钉定 JC C01（E21/F104 同一钉定面，sha256 钉定见
test_e21_f104_calc_family.py，此处不重复钉）。

fail-closed 断言：包目录未配置/缺文件/版本不一致/sha256 对账不符/序列外
时点（早于首条公告、晚于末条公告）/选中调整行无该档次（不跨行顶替）/
段内双来源冲突——一律 NotConnected 具名码，绝不产出纸面利率。

本面为进程内方法面（legal_entry.call），不涉任何网络端口。
"""
import hashlib
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry

JC_REPO = Path(
    r"D:\Codex\1.法律工作区\juris-calculus工作区\juris-calculus\.local\worktrees\w2b-u19")

# 运行面钉定（同 test_e21_f104_calc_family.py 纪律）：本 pytest 进程解析到
# 的 compiler_core 必须是钉定波次的 JC 工作树。
if (JC_REPO / "compiler_core" / "calc_families.py").is_file():
    sys.path.insert(0, str(JC_REPO))
    for _name in [m for m in list(sys.modules)
                  if m == "compiler_core" or m.startswith("compiler_core.")]:
        del sys.modules[_name]


def _require_jc_worktree():
    if not (JC_REPO / "compiler_core" / "calc_families.py").is_file():
        raise AssertionError(
            f"pinned JC w2b-u19 worktree missing at {JC_REPO}; "
            "the LPR rate channel cannot be verified end-to-end")


# 全合成数据包（值/日期均非官方口径；两位小数字符串=包真实形状）
SYNTH_PACK_VERSION = "20990101.1"
SYNTH_LPR_RECORDS = [
    {"date": "2020-01-10", "lpr_1y": "9.90", "lpr_5y": "10.10"},
    {"date": "2020-02-10", "lpr_1y": "8.80", "lpr_5y": "9.20"},
    {"date": "2020-03-10", "lpr_1y": "7.70", "lpr_5y": "8.30"},
]
SYNTH_BM_RECORDS = [
    {"date": "1995-07-01", "annual_rate_pct": {
        "within_6m": "11.11", "6m_to_1y": "12.12", "1y_to_3y": "13.13",
        "3y_to_5y": "14.14", "over_5y": "15.15"}},
    {"date": "2015-06-01", "annual_rate_pct": {
        "within_1y": "5.55", "1y_to_5y": "6.66", "over_5y": "7.77"}},
]

_ACTIVE_TMPDIRS = []


def _synth_pack(*, tamper_data=False, meta_version=None):
    """写一份合成 LPR 包到注册过的临时目录，返回其路径。"""
    holder = tempfile.TemporaryDirectory()
    _ACTIVE_TMPDIRS.append(holder)
    pack_dir = Path(holder.name)
    data = {
        "schema_version": "1.0",
        "pack_name": "lpr",
        "pack_version": SYNTH_PACK_VERSION,
        "verified_through": "2099-01-01",
        "rate_unit": "年利率%（字符串两位小数；消费端按 Decimal 解析，禁浮点）",
        "lpr_records": SYNTH_LPR_RECORDS,
        "loan_benchmark_records": SYNTH_BM_RECORDS,
    }
    raw = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    payload = raw.encode("utf-8")
    written = payload
    if tamper_data:  # 数据在 meta 定锚后被改动 → sha256 对账必失败
        written = payload.replace(b'"9.90"', b'"9.91"')
    (pack_dir / "lpr-history.json").write_bytes(written)
    meta = {
        "name": "lpr",
        "pack_version": meta_version or SYNTH_PACK_VERSION,
        "hash": hashlib.sha256(payload).hexdigest(),
        "update": 0,
        "filesize": len(payload),
    }
    (pack_dir / "pack.meta").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return pack_dir


def _config(pack_dir=None):
    _require_jc_worktree()
    holder = tempfile.TemporaryDirectory()
    _ACTIVE_TMPDIRS.append(holder)
    tmp_path = Path(holder.name)
    rules = tmp_path / "rules"
    rules.mkdir()
    # JC client 初始化最小合成规则包（与 E21 验收同形；内容纯合成）
    rule_pack = {
        "schema_version": "jc/local-pack/1.0", "pack_version": "1.0.0",
        "sources": [{
            "source_id": "lpr-channel-acceptance", "jurisdiction": "TEST",
            "authority_tier": "official_first_party",
            "issuer": "Acceptance Test Authority", "title": "acceptance-statute",
            "publication_time": "2020-01-01T00:00:00Z",
            "effective_from": "2020-01-01T00:00:00Z",
            "retrieved_at": "2026-08-01T00:00:00Z",
            "locator": {"kind": "uri", "value": "example.invalid/acceptance",
                        "page": None, "span_start": None, "span_end": None},
            "content": ("SYNTHETIC acceptance rule text for engineering "
                        "verification only; no legal effect."),
            "structure_sections": ["ART-1"],
        }],
        "rules": [
            {"rule_id": "acc-base", "jurisdiction": "TEST",
             "governing_law": "acceptance-statute",
             "source_id": "lpr-channel-acceptance", "modality": "OBLIGATION",
             "premises": [{"fact_key": "acc.contract", "required": True}],
             "conclusion": {"value": "applies"},
             "effective_from": "2020-01-01T00:00:00Z"},
        ],
    }
    (rules / "jc-local-pack.json").write_text(
        json.dumps(rule_pack, ensure_ascii=False), encoding="utf-8")
    config = {
        "jc_state_root": str(tmp_path / "state"),
        "jc_rule_roots": [str(rules)],
        "jc_import_path": str(JC_REPO),
    }
    if pack_dir is not None:
        config["lpr_pack_dir"] = str(pack_dir)
    return config


def _interest(payload, config):
    return legal_entry.call("calc.interest", {"input": payload}, config)


class LprPackRateChannelTests(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        while _ACTIVE_TMPDIRS:
            _ACTIVE_TMPDIRS.pop().cleanup()

    # ---- 既有 agreement 面零改动 ------------------------------------

    def test_no_rate_request_passthrough_unchanged(self):
        config = _config()  # 不配 lpr_pack_dir：无 rate_request 时不得触包
        sheet = _interest({
            "principal_minor": 10_000_000,
            "segments": [{"start_date": "2020-01-01", "end_date": "2021-01-01",
                          "annual_rate": "0.01"}],
            "rate_source": "agreement",
        }, config)
        self.assertEqual(sheet["family"], "C01")
        self.assertEqual(sheet["rate_source"], "agreement")
        self.assertNotIn("rate_channel", sheet)
        self.assertEqual(sheet["segments"][0]["annual_rate"], "0.01")

    # ---- LPR 序列取数：最近一期 + 边界 + 凭据 -----------------------

    def test_lpr_series_latest_at_or_before_segment_start(self):
        config = _config(_synth_pack())
        sheet = _interest({
            "principal_minor": 10_000_000,
            "segments": [
                {"start_date": "2020-01-10", "end_date": "2020-02-10"},
                {"start_date": "2020-02-10", "end_date": "2020-03-10"},
                {"start_date": "2020-03-10", "end_date": "2020-04-01"},
            ],
            "rate_request": {"source": "lpr_pack", "series": "lpr_1y"},
        }, config)
        # 段起日=公告日含当天；段起落在两公告之间→沿用最近上一期
        rates = [row["annual_rate"] for row in sheet["segments"]]
        self.assertEqual(rates, ["0.099", "0.088", "0.077"])
        channel = sheet["rate_channel"]
        self.assertEqual(channel["pack_version"], SYNTH_PACK_VERSION)
        self.assertTrue(channel["sha256_verified"])
        self.assertEqual(channel["series"], "lpr_1y")
        self.assertEqual(
            [(row["record_date"], row["annual_rate_pct"], row["annual_rate"])
             for row in channel["segments"]],
            [("2020-01-10", "9.90", "0.099"),
             ("2020-02-10", "8.80", "0.088"),
             ("2020-03-10", "7.70", "0.077")])
        self.assertEqual(sheet["rate_source"],
                         "lpr_pack/lpr_1y@pack:" + SYNTH_PACK_VERSION)
        # rate_request 不下渗 JC 面
        self.assertNotIn("rate_request", sheet)

    def test_lpr_series_end_to_end_interest_exact(self):
        config = _config(_synth_pack())
        sheet = _interest({
            "principal_minor": 36_500_000,
            "segments": [{"start_date": "2020-01-10", "end_date": "2021-01-10"}],
            "rate_request": {"source": "lpr_pack", "series": "lpr_1y"},
        }, config)
        # 2020 为闰年：2020-01-10→2021-01-10=366 天（ACT/365 计息天数）；
        # 36,500,000×0.099×366/365 = 9,900×366 = 3,623,400 minor（整数，无舍入）
        self.assertEqual(sheet["segments"][0]["days"], 366)
        self.assertEqual(sheet["segments"][0]["annual_rate"], "0.099")
        # 精确值带除法尾标度（"3623400.000"），数值全等即整数、无舍入
        self.assertEqual(Decimal(sheet["interest_minor_exact"]),
                         Decimal("3623400"))
        self.assertEqual(sheet["amount_minor"], 3623400)

    def test_lpr_series_before_first_record_refused(self):
        config = _config(_synth_pack())
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({
                "principal_minor": 10_000_000,
                "segments": [{"start_date": "2020-01-05",
                              "end_date": "2020-02-05"}],
                "rate_request": {"source": "lpr_pack", "series": "lpr_1y"},
            }, config)
        self.assertIn("lpr_rate_not_in_pack", str(ctx.exception))

    def test_lpr_series_after_last_record_refused_no_extension(self):
        config = _config(_synth_pack())
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({
                "principal_minor": 10_000_000,
                "segments": [{"start_date": "2020-04-10",
                              "end_date": "2020-05-10"}],
                "rate_request": {"source": "lpr_pack", "series": "lpr_1y"},
            }, config)
        self.assertIn("lpr_rate_not_in_pack", str(ctx.exception))

    # ---- 旧基准利率：调整表语义 + 档次异构 --------------------------

    def test_benchmark_five_bracket_row_resolution(self):
        config = _config(_synth_pack())
        sheet = _interest({
            "principal_minor": 5_000_000,
            "segments": [{"start_date": "2010-01-01", "end_date": "2011-01-01"}],
            "rate_request": {"source": "lpr_pack", "series": "within_6m"},
        }, config)
        # 最近一次调整=1995-07-01 五档行 within_6m=11.11 → 0.1111
        self.assertEqual(sheet["segments"][0]["annual_rate"], "0.1111")
        provenance = sheet["rate_channel"]["segments"][0]
        self.assertEqual(provenance["record_date"], "1995-07-01")
        self.assertEqual(provenance["annual_rate_pct"], "11.11")
        self.assertEqual(sheet["rate_source"],
                         "lpr_pack/within_6m@pack:" + SYNTH_PACK_VERSION)

    def test_benchmark_adjustment_table_semantics_and_provenance(self):
        config = _config(_synth_pack())
        # 两段分两张计算书（JC C01 要求分段连续，跨 80 年不能同书）：
        # 各自最近一次调整=2015-06-01 三档行 within_1y=5.55 → 0.0555；
        # 2098 段仍取该行＝调整表语义（末次调整持续有效至下一次调整），
        # 所用调整日随 rate_channel 回传供核对（非静默）。
        request = {"source": "lpr_pack", "series": "within_1y"}
        sheet = _interest({
            "principal_minor": 5_000_000,
            "segments": [{"start_date": "2016-01-01", "end_date": "2017-01-01"}],
            "rate_request": dict(request),
        }, config)
        self.assertEqual(sheet["segments"][0]["annual_rate"], "0.0555")
        self.assertEqual(sheet["rate_channel"]["segments"][0]["record_date"],
                         "2015-06-01")
        sheet = _interest({
            "principal_minor": 5_000_000,
            "segments": [{"start_date": "2098-01-01", "end_date": "2098-07-01"}],
            "rate_request": dict(request),
        }, config)
        self.assertEqual(sheet["segments"][0]["annual_rate"], "0.0555")
        self.assertEqual(sheet["rate_channel"]["segments"][0]["record_date"],
                         "2015-06-01")

    def test_benchmark_bracket_absent_at_selected_row_refused(self):
        config = _config(_synth_pack())
        base = {"principal_minor": 5_000_000}
        # 2016 段最近调整=三档行，无 within_6m（简并取消）→ 查无 typed 拒，
        # 不回捞 1995 五档行旧值顶替
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({**base,
                       "segments": [{"start_date": "2016-01-01",
                                     "end_date": "2016-06-01"}],
                       "rate_request": {"source": "lpr_pack",
                                        "series": "within_6m"}}, config)
        self.assertIn("lpr_rate_not_in_pack", str(ctx.exception))
        # 1996 段最近调整=五档行，无 within_1y（简并前未设立）→ 查无 typed 拒
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({**base,
                       "segments": [{"start_date": "1996-01-01",
                                     "end_date": "1996-06-01"}],
                       "rate_request": {"source": "lpr_pack",
                                        "series": "within_1y"}}, config)
        self.assertIn("lpr_rate_not_in_pack", str(ctx.exception))
        # 1990 段早于首条调整 → 查无 typed 拒
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({**base,
                       "segments": [{"start_date": "1990-01-01",
                                     "end_date": "1990-06-01"}],
                       "rate_request": {"source": "lpr_pack",
                                        "series": "within_1y"}}, config)
        self.assertIn("lpr_rate_not_in_pack", str(ctx.exception))

    # ---- fail-closed：包不可用/形状/冲突 ----------------------------

    def test_hash_mismatch_refused(self):
        config = _config(_synth_pack(tamper_data=True))
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({
                "principal_minor": 10_000_000,
                "segments": [{"start_date": "2020-01-10",
                              "end_date": "2020-02-10"}],
                "rate_request": {"source": "lpr_pack", "series": "lpr_1y"},
            }, config)
        self.assertIn("lpr_pack_hash_mismatch", str(ctx.exception))

    def test_pack_dir_unconfigured_and_missing_files(self):
        payload = {
            "principal_minor": 10_000_000,
            "segments": [{"start_date": "2020-01-10", "end_date": "2020-02-10"}],
            "rate_request": {"source": "lpr_pack", "series": "lpr_1y"},
        }
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest(payload, _config(None))
        self.assertIn("lpr_pack_dir_not_configured", str(ctx.exception))

        holder = tempfile.TemporaryDirectory()
        _ACTIVE_TMPDIRS.append(holder)
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest(payload, _config(Path(holder.name)))
        self.assertIn("lpr_pack_files_missing", str(ctx.exception))

    def test_meta_data_version_mismatch_refused(self):
        config = _config(_synth_pack(meta_version="20990101.2"))
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({
                "principal_minor": 10_000_000,
                "segments": [{"start_date": "2020-01-10",
                              "end_date": "2020-02-10"}],
                "rate_request": {"source": "lpr_pack", "series": "lpr_1y"},
            }, config)
        self.assertIn("lpr_pack_version_mismatch", str(ctx.exception))

    def test_unknown_source_series_and_double_source_segment(self):
        config = _config(_synth_pack())
        base = {"principal_minor": 10_000_000,
                "segments": [{"start_date": "2020-01-10",
                              "end_date": "2020-02-10"}]}
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({**base, "rate_request": {"source": "ecb",
                                                "series": "lpr_1y"}}, config)
        self.assertIn("lpr_rate_source_unknown", str(ctx.exception))
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({**base, "rate_request": {"source": "lpr_pack",
                                                "series": "euribor"}}, config)
        self.assertIn("lpr_rate_series_unknown", str(ctx.exception))
        # 段内双来源：段已带 annual_rate 又请求包取数=typed 拒（单一真源）
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({**base, "segments": [
                {"start_date": "2020-01-10", "end_date": "2020-02-10",
                 "annual_rate": "0.01"}],
                "rate_request": {"source": "lpr_pack", "series": "lpr_1y"}},
                config)
        self.assertIn("lpr_rate_segment_invalid", str(ctx.exception))
        # 显式 rate_source 与通道计算值不一致=typed 拒
        with self.assertRaises(legal_entry.NotConnected) as ctx:
            _interest({**base, "rate_source": "agreement",
                       "rate_request": {"source": "lpr_pack",
                                        "series": "lpr_1y"}}, config)
        self.assertIn("lpr_rate_source_conflict", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
