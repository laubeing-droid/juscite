# -*- coding: utf-8 -*-
"""F88 可答/应拒双集合评估＋六指标 CI 门验收对账（PENDING_OWNER 版，工单 W2b-U03）。

06 行 F88 acceptance 全断言走真产品入口：
  - 黄金集＝tools/e12_corpus_gen.py --citations 产物（全合成，seed 钉定
    20261016，双集合共同分母；标题全部含「合成」，as_of 钉定常量）；
  - 评估＝legal_entry f88.* 冻结方法组（子进程径）——消费 F70 同源核验面
    （citation_verifier→statute_validity→E22 冻结面 lccc_consumer v1.1，
    sha256 钉定漂移即响亮失败），不复制第二核验权威；
  - 六指标（judicex gold_runner 阈值表逐名适配，阈值原样）＋双集合率
    共同报告分母；永远拒答不通过（refuse_all 控制组门必 FAIL）；全答
    也不通过（answer_all 控制组门必 FAIL）；核验器统计不冒独立幻觉率
    （answer_all 自带诱饵自报 0.0，评估照实报 15/27）；双集合不替删原
    指标（six_metrics 键恒为源六名）。

分段（每 profile 各跑一遍，证据分目录落盘）：
  C01 黄金集生成确定性：同 seed 两跑逐文件同字节＋摘要相同＋异 seed 摘要不同
  C02 全合成红线：合成面标题全部含「合成」＋真实正式表（在盘时）无一命中
  C03 双集合分母对账：可答 12/应拒 15/共同 27 与逐条计数一致
  C04 六指标真跑全过阈值＋每指标 ci95 在报告
  C05 双集合率：可答覆盖 12/12＋应拒拒绝 15/15＋共同分母 27 在报告
  C06 永远拒答不通过：refuse_all 门 FAIL＋可答覆盖=0
  C07 全答也不通过：answer_all 门 FAIL＋假引率超阈
  C08 核验器统计不冒独立幻觉率：诱饵 0.0 vs 评估 15/27＋真跑分母=被肯定数
  C09 原六指标保全：six_metrics 恰为源六名＋阈值原样＋mean_confidence 具名排除
  C10 真核验面单点复核：citation.verify 子进程径回读 ans-0001 引文片段
  C11 CI 门退出码：模块 CLI 真跑 exit 0；两控制组 exit 1
  C12 桥 fail-closed：空配置/未知方法/未知控制 exit 3 具名
  C13 冻结面钉定：lccc_consumer.py v1.1 sha256 与 F70 同 pin
  C14 黄金集只读锚：评估前后黄金集摘要不变（只读消费）

用法（juscite worktree w2b-u03 根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f88_dualset_ci_recon.py --profile desktop --profile selfhost
  [--codices-repo <含 v1.1 lccc_consumer.py 目录>] [--real-formal-root <真实正式目录>]
  [--evidence-root evidence/F88]

exit 0＝全部 profile 全部断言过（RECON_OK）；证据 JSON 写 <root>/<profile>/。
只读消费；不发任何网络请求；不写正式目录；黄金集落临时根不入 git。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    csv.field_size_limit(10 ** 9)
except OverflowError:  # 平台上限低于 1e9（与 lccc_consumer 同式）
    csv.field_size_limit(2 ** 31 - 1)

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGAL_ENTRY = REPO_ROOT / "implementation" / "python" / "legal_entry.py"
F88_MODULE = REPO_ROOT / "implementation" / "python" / "f88_dualset_ci.py"
GENERATOR = REPO_ROOT / "tools" / "e12_corpus_gen.py"

DEFAULT_CODICES_REPO = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区"
    r"\legal-cn-core-codices-repo\.local\worktrees\w2a-u14"
)
DEFAULT_REAL_FORMAL_ROOT = (
    r"D:\Codex\1.法律工作区\legal-cn-core-codices工作区\legal-cn-core-codices"
)
LCCC_V11_SHA256 = (
    "55eea7c27e08d6b236b7ab7a83810c86ee0898c335c4668d875a492775db863a"
)
F88_SEED = 20261016

SOURCE_SIX = ("domain_route_accuracy", "hallucination_rate",
              "citation_accuracy", "false_citation_rate",
              "excerpt_recall", "status_accuracy")
SOURCE_THRESHOLDS = {"domain_route_accuracy": 0.90,
                     "hallucination_rate": 0.10,
                     "citation_accuracy": 0.80,
                     "false_citation_rate": 0.05,
                     "excerpt_recall": 0.60,
                     "status_accuracy": 0.80}


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append(
            {"id": check_id, "status": "PASS" if ok else "FAIL",
             "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail))
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "e12_corpus_gen_f88_recon", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call_entry(method: str, args: dict, config: dict) -> dict:
    request_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    config_handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False)
    try:
        json.dump({"method": method, "args": args}, request_handle,
                  ensure_ascii=False)
        request_handle.close()
        json.dump(config, config_handle, ensure_ascii=False)
        config_handle.close()
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(LEGAL_ENTRY),
             "--request-json", request_handle.name,
             "--config", config_handle.name],
            capture_output=True, text=True, encoding="utf-8",
            timeout=600, cwd=str(REPO_ROOT))
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_raw": proc.stdout[-500:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(request_handle.name)
        os.unlink(config_handle.name)


def run_cli(golden_path: str, config: dict, extra: list[str]) -> dict:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(F88_MODULE),
         "--golden", golden_path,
         "--codices-import-path", config["codices_import_path"],
         "--codices-formal-root", config["codices_formal_root"]] + extra,
        capture_output=True, text=True, encoding="utf-8",
        timeout=600, cwd=str(REPO_ROOT))
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"_raw": proc.stdout[-300:]}
    return {"exit": proc.returncode, "payload": payload}


def run_profile(profile: str, codices_repo: str,
                real_formal_root: str | None,
                evidence_root: str) -> dict:
    print("=== profile=%s ===" % profile)
    checks = Checks()
    gen = load_generator()

    # 黄金集两跑（确定性）＋正式评估用根
    dir_a = Path(tempfile.mkdtemp(prefix="f88-recon-a-"))
    dir_b = Path(tempfile.mkdtemp(prefix="f88-recon-b-"))
    dir_c = Path(tempfile.mkdtemp(prefix="f88-recon-c-"))
    ra = gen.build_citations(dir_a, F88_SEED)
    rb = gen.build_citations(dir_b, F88_SEED)
    rc = gen.build_citations(dir_c, F88_SEED + 1)

    files_a = sorted(p.relative_to(dir_a).as_posix()
                     for p in dir_a.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(dir_b).as_posix()
                     for p in dir_b.rglob("*") if p.is_file())
    byte_equal = all(
        (dir_a / rel).read_bytes() == (dir_b / rel).read_bytes()
        for rel in files_a) and files_a == files_b
    checks.add(
        "C01_golden_deterministic_same_seed",
        byte_equal and ra["digest"] == rb["digest"]
        and ra["digest"] != rc["digest"] and len(files_a) >= 15,
        "同 seed 两跑 %d 文件逐字节相同＋摘要 %s… 相同；异 seed 摘要不同"
        % (len(files_a), ra["digest"][:12]))

    golden = json.loads((dir_a / "f88_golden_set.json")
                        .read_text(encoding="utf-8-sig"))
    all_synthetic = all("合成" in s["title"] for s in golden["statutes"])
    face_titles = {s["title"] for s in golden["statutes"]}
    fab_not_in_face = all(f not in face_titles
                          for f in golden["fabricated_titles"])
    real_miss = None
    if real_formal_root and os.path.isfile(
            os.path.join(real_formal_root, "legal_documents.csv")):
        with open(os.path.join(real_formal_root, "legal_documents.csv"),
                  "r", encoding="utf-8-sig", newline="") as handle:
            real_titles = {row["BT"].strip()
                           for row in csv.DictReader(handle) if row.get("BT")}
        real_miss = sorted(face_titles & real_titles)
        checks.add(
            "C02_all_synthetic_titles",
            all_synthetic and fab_not_in_face and not real_miss,
            "合成面 %d 标题全部含「合成」；虚构标题不在合成面；真实正式表"
            "（在盘 %d 标题）与合成面交集=%s"
            % (len(face_titles), len(real_titles), real_miss or "空"))
    else:
        checks.add(
            "C02_all_synthetic_titles", all_synthetic and fab_not_in_face,
            "合成面 %d 标题全部含「合成」；虚构标题不在合成面；真实正式表"
            "不在盘（real_formal_root=%s）——跨表复核该子项未跑"
            % (len(face_titles), real_formal_root))

    counts = golden["counts"]
    per_set = {"answerable": 0, "refuse": 0}
    for item in golden["items"]:
        per_set[item["set"]] += 1
    checks.add(
        "C03_dualset_denominators",
        counts == {"answerable": per_set["answerable"],
                   "refuse": per_set["refuse"],
                   "common": per_set["answerable"] + per_set["refuse"]}
        and counts["answerable"] == 12 and counts["refuse"] == 15
        and counts["common"] == 27
        and golden["fixed_as_of"] == "20261016",
        "可答 %d／应拒 %d／共同 %d（逐条计数与清单一致）；as_of 钉定 %s"
        % (counts["answerable"], counts["refuse"], counts["common"],
           golden["fixed_as_of"]))

    config = {"codices_import_path": codices_repo,
              "codices_formal_root": str(dir_a / "codices_face")}
    golden_path = str(dir_a / "f88_golden_set.json")

    real = call_entry("f88.evaluate", {"golden_path": golden_path}, config)
    report = real["payload"].get("result", {}) if real["exit"] == 0 else {}
    six = report.get("six_metrics", {})
    six_ok = (real["exit"] == 0
              and set(six) == set(SOURCE_SIX)
              and all(six[n]["pass"] for n in SOURCE_SIX)
              and all("ci95_wilson" in six[n] and len(six[n]["ci95_wilson"]) == 2
                      for n in SOURCE_SIX))
    checks.add(
        "C04_six_metrics_pass_with_ci",
        six_ok,
        "真跑（legal_entry f88.evaluate 子进程径）六指标：%s"
        % json.dumps({n: six.get(n, {}).get("value") for n in SOURCE_SIX}))

    dual = report.get("dualset", {})
    cov = dual.get("answerable_coverage_correct", {})
    rej = dual.get("refuse_correct_rejection", {})
    checks.add(
        "C05_dualset_rates_common_denominator",
        real["exit"] == 0
        and (cov.get("numerator"), cov.get("denominator")) == (12, 12)
        and (rej.get("numerator"), rej.get("denominator")) == (15, 15)
        and cov.get("common_denominator") == 27
        and rej.get("common_denominator") == 27
        and dual.get("denominators") == {"answerable_set": 12,
                                         "refuse_set": 15, "common": 27},
        "可答覆盖 %s/%s＋应拒拒绝 %s/%s＋共同分母 27 同报"
        % (cov.get("numerator"), cov.get("denominator"),
           rej.get("numerator"), rej.get("denominator")))

    refuse_ctrl = call_entry(
        "f88.control_evaluate",
        {"golden_path": golden_path, "control": "refuse_all"}, config)
    rc_rep = refuse_ctrl["payload"].get("result", {}) if refuse_ctrl["exit"] == 0 else {}
    rc_cov = rc_rep.get("dualset", {}).get("answerable_coverage_correct", {})
    checks.add(
        "C06_refuse_all_fails_gate",
        refuse_ctrl["exit"] == 0
        and rc_rep.get("gate", {}).get("passed") is False
        and rc_rep.get("gate", {}).get("exit_code") == 1
        and rc_cov.get("value") == 0.0
        and (rc_cov.get("numerator"), rc_cov.get("denominator")) == (0, 12)
        and "answerable_coverage_correct" in rc_rep.get("gate", {}).get("failures", []),
        "永远拒答：可答覆盖=%s（0/12），门 FAIL（%s）——拒答率不是越高越好"
        % (rc_cov.get("value"),
           ",".join(rc_rep.get("gate", {}).get("failures", [])[:3])))

    ans_ctrl = call_entry(
        "f88.control_evaluate",
        {"golden_path": golden_path, "control": "answer_all"}, config)
    aa_rep = ans_ctrl["payload"].get("result", {}) if ans_ctrl["exit"] == 0 else {}
    aa_fc = aa_rep.get("six_metrics", {}).get("false_citation_rate", {})
    aa_rej = aa_rep.get("dualset", {}).get("refuse_correct_rejection", {})
    checks.add(
        "C07_answer_all_fails_gate",
        ans_ctrl["exit"] == 0
        and aa_rep.get("gate", {}).get("passed") is False
        and aa_fc.get("value", 0.0) > SOURCE_THRESHOLDS["false_citation_rate"]
        and (aa_rej.get("numerator"), aa_rej.get("denominator")) == (0, 15),
        "全答也不通过：假引率 %s（%s/%s）超阈 0.05，应拒拒绝 0/15，门 FAIL"
        % (aa_fc.get("value"), aa_fc.get("numerator"),
           aa_fc.get("denominator")))

    aa_halluc = aa_rep.get("six_metrics", {}).get("hallucination_rate", {})
    real_halluc = six.get("hallucination_rate", {})
    decoy_ignored = (
        aa_halluc.get("numerator") == 15 and aa_halluc.get("denominator") == 27
        and abs(aa_halluc.get("value", -1) - 15 / 27) < 1e-5
        and aa_halluc.get("basis")
        == "golden_labels_only_verifier_self_stats_ignored"
        and real_halluc.get("numerator") == 0
        and real_halluc.get("denominator") == 12)
    checks.add(
        "C08_verifier_self_stats_not_hallucination",
        decoy_ignored,
        "answer_all 自报诱饵 hallucination=0.0，评估照实报 15/27=%.4f"
        "（basis=golden_labels_only）；真跑分母=被肯定断言数 0/12——"
        "幻觉率只由黄金标签对账，绝不读核验器自报统计" % aa_halluc.get("value"))

    thresholds_ok = all(
        six.get(n, {}).get("threshold") == SOURCE_THRESHOLDS[n]
        for n in SOURCE_SIX)
    excluded = report.get("excluded_from_source_table", {})
    checks.add(
        "C09_six_metrics_preserved_dualset_additive",
        set(six) == set(SOURCE_SIX) and thresholds_ok
        and "mean_confidence" in excluded
        and "mean_confidence" not in six
        and set(dual) >= {"answerable_coverage_correct",
                          "refuse_correct_rejection", "denominators"},
        "six_metrics 恰为源六名＋阈值原样（0.90/0.10/0.80/0.05/0.60/0.80）；"
        "mean_confidence 具名排除不静默；双集合为附加字段（%s）不替删原指标"
        % ",".join(sorted(set(dual) - {"answerable_coverage_correct",
                                       "refuse_correct_rejection",
                                       "denominators", "note"}) or ["-"]))

    spot = call_entry(
        "citation.verify",
        {"citation": "《中华人民共和国合成数据保护法》第一条规定："
                     "“为了规范合成数据处理活动，保护合成数据权益，制定本法。”",
         "as_of": "20261016"}, config)
    spot_rec = spot["payload"].get("result", {}) if spot["exit"] == 0 else {}
    article_text = (spot_rec.get("support") or {}).get("article_text") or ""
    checks.add(
        "C10_same_source_face_single_spot_check",
        spot["exit"] == 0 and spot_rec.get("status") == "现行"
        and spot_rec.get("verified_scoped") is True
        and "规范合成数据处理活动" in article_text,
        "citation.verify 子进程径（f88.evaluate 消费的同源核验面）真回读："
        "status=%s quote_in_article=%s article_text 含期望片段"
        % (spot_rec.get("status"),
           (spot_rec.get("support") or {}).get("quote_in_article")))

    cli_real = run_cli(golden_path, config, [])
    cli_refuse = run_cli(golden_path, config, ["--control", "refuse_all"])
    cli_answer = run_cli(golden_path, config, ["--control", "answer_all"])
    checks.add(
        "C11_ci_gate_exit_codes",
        cli_real["exit"] == 0
        and cli_real["payload"].get("gate", {}).get("passed") is True
        and cli_refuse["exit"] == 1 and cli_answer["exit"] == 1,
        "模块 CLI（CI 门）：真跑 exit 0／refuse_all exit %s／answer_all "
        "exit %s——任一阈值不达→非零退出（judicex gold_runner 门语义）"
        % (cli_refuse["exit"], cli_answer["exit"]))

    bad_cfg = call_entry("f88.evaluate", {"golden_path": golden_path}, {})
    bad_cfg_code = bad_cfg["payload"].get("code")
    unknown_method = call_entry("f88.run_all", {"golden_path": golden_path},
                                config)
    unknown_ctrl = call_entry(
        "f88.control_evaluate",
        {"golden_path": golden_path, "control": "half"}, config)
    checks.add(
        "C12_bridge_fail_closed_exit3",
        bad_cfg["exit"] == 3 and bad_cfg_code == "codices_import_path_not_configured"
        and unknown_method["exit"] == 3
        and "method_not_connected" in str(unknown_method["payload"].get("code"))
        and unknown_ctrl["exit"] == 3
        and str(unknown_ctrl["payload"].get("code"))
        .startswith("f88_control_unknown:"),
        "空配置→%s；f88.run_all→%s；control=half→%s（全 exit 3 具名）"
        % (bad_cfg_code, unknown_method["payload"].get("code"),
           unknown_ctrl["payload"].get("code")))

    lccc_path = os.path.join(codices_repo, "lccc_consumer.py")
    checks.add(
        "C13_frozen_face_v11_pinned",
        os.path.isfile(lccc_path)
        and sha256_file(lccc_path) == LCCC_V11_SHA256,
        "lccc_consumer.py v1.1 sha256=%s（与 F70 同 pin；漂移即响亮失败）"
        % LCCC_V11_SHA256[:16])

    digest_before = ra["digest"]
    gen_digest_after = gen.citations_digest(dir_a, {"schema": gen.CIT_SCHEMA,
                                                    "seed": F88_SEED,
                                                    "mode": "citations"})
    checks.add(
        "C14_golden_readonly_anchor",
        digest_before == gen_digest_after
        == (dir_a / "f88_citations_digest.txt").read_text(
            encoding="ascii").split("  ")[0],
        "评估/控制组/CLI 全部跑完后黄金集摘要不变（%s…，只读消费）"
        % digest_before[:12])

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO_ROOT)).stdout.strip()
    evidence = {
        "run_scope": "W2b-U03 F88 dual-set + six-metric CI gate",
        "profile": profile,
        "command": "python -X utf8 %s --profile %s" % (sys.argv[0], profile),
        "cwd": str(REPO_ROOT),
        "subject_commit": commit,
        "golden": {"seed": F88_SEED, "digest": ra["digest"],
                   "counts": counts, "fixed_as_of": golden["fixed_as_of"],
                   "face_root": str(dir_a / "codices_face")},
        "frozen_face": {"lccc_consumer.py(v1.1)": sha256_file(lccc_path)},
        "real_run": {"gate": report.get("gate"),
                     "six_metrics": six,
                     "dualset": {k: dual.get(k) for k in
                                 ("answerable_coverage_correct",
                                  "refuse_correct_rejection",
                                  "denominators")}},
        "controls": {
            "refuse_all": {"gate": rc_rep.get("gate"),
                           "answerable_coverage": rc_cov},
            "answer_all": {"gate": aa_rep.get("gate"),
                           "hallucination": aa_halluc,
                           "false_citation_rate": aa_fc},
        },
        "cli_exits": {"real": cli_real["exit"],
                      "refuse_all": cli_refuse["exit"],
                      "answer_all": cli_answer["exit"]},
        "checks": checks.items,
        "passed": checks.passed_count,
        "total": len(checks.items),
        "overall": "PASS" if checks.all_passed else "FAIL",
    }
    out_dir = REPO_ROOT / evidence_root / profile
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "f88-dualset-ci-recon.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print("--- profile=%s: %d/%d checks" % (profile, checks.passed_count,
                                            len(checks.items)))
    return {"profile": profile, "checks": checks,
            "evidence": str(out_dir / "f88-dualset-ci-recon.json")}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", required=True,
                        choices=("desktop", "selfhost"),
                        help="验收 profile（可多次：--profile desktop "
                             "--profile selfhost）")
    parser.add_argument("--codices-repo", default=DEFAULT_CODICES_REPO)
    parser.add_argument("--real-formal-root", default=DEFAULT_REAL_FORMAL_ROOT)
    parser.add_argument("--evidence-root", default="evidence/F88")
    args = parser.parse_args()

    lccc_path = os.path.join(args.codices_repo, "lccc_consumer.py")
    if not os.path.isfile(lccc_path):
        print("FATAL: lccc_consumer.py 不在 %s（E22 冻结面 v1.1）"
              % args.codices_repo)
        return 2
    if sha256_file(lccc_path) != LCCC_V11_SHA256:
        print("FATAL: 冻结面 v1.1 lccc_consumer.py sha256 漂移")
        return 2

    results = [run_profile(profile, args.codices_repo,
                           args.real_formal_root, args.evidence_root)
               for profile in args.profile]
    all_ok = all(r["checks"].all_passed for r in results)
    print("---")
    print("RECON_%s %s — profiles=%s"
          % ("OK" if all_ok else "FAIL",
             "/".join("%s %d/%d" % (r["profile"], r["checks"].passed_count,
                                    len(r["checks"].items)) for r in results),
             ",".join(args.profile)))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
