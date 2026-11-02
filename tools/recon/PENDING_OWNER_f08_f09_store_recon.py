"""F08/F09 material-store reconciliation against the live harness entry (W2a-U05).

对账对象：harness 分支 w2a-u05（基于 w1-u07@0a2e6c92 的 F08 施工分支）的
public_entry --materials-json 封闭径——与产品桥（legal_entry → 子进程
public_entry）完全同一条链；anonymizer 分支 w2a-u05 的 overlay_service 同
进程面。全部合成材料：临时状态根、合成 matter/文档/覆盖层字符串；两检出
零字节改动（只运行其代码，git 只读命令核对分支）。

实跑覆盖（PENDING_OWNER_F08_F09_store_recon）：
  F08：register_material（CAS 原件＋candidate）→ 幂等重放/异内容冲突/已用
  id 拒 → add_material_revision（版本副本）→ 旧 revision 逐字节回读 → 跨案
  引用拒绝（他案 scope／DTO matterId 不一致）→ 准入（HarnessUnits 种子）
  → CAS 篡改 fail-closed → 文件目录投影删除重建/篡改后业务回读不变
  （目录只组织材料，MatterStore 唯一业务真源）。
  F09：P10 deidentify 同进程 → overlay_register → user_overrides 覆盖层成
  新 revision → 旧件回读 → 原件字节跨修订不变 → 覆盖层带回可捕获 PII 拒 →
  原件被改写拒；合格引用交消费：sanitized 视图入 harness 材料真源（原件
  表面不出现在 harness CAS 任何 blob——原件不出域红线实测）。
  桥负向：未配置 NOT_CONNECTED／未知方法 method_not_connected。

用法：
  python -X utf8 tools/recon/PENDING_OWNER_f08_f09_store_recon.py [--harness-root <path>] [--anonymizer-root <path>] [--json]

退出码：0 = RECON_OK；1 = RECON_FAIL；3 = RECON_BLOCKED。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo\.local\worktrees\w2a-u05")
DEFAULT_ANONYMIZER_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-cn-anonymizer工作区\legal-cn-anonymizer")

MATTER = "m-f08-recon"
MATTER_OTHER = "m-f08-other"
SCOPE = {"kind": "matter", "matterId": MATTER}
SCOPE_OTHER = {"kind": "matter", "matterId": MATTER_OTHER}

# 合成原文（含规则层可捕获 PII——只存在于 anonymizer 侧，绝不能进 harness）。
SYN_ORIGINAL = (
    "委托代理合同（F09 合成材料）。\n"
    "委托人：周测敏（测试用合成身份，身份证11010119900307867X，"
    "电话13700009999，邮箱zhoubin@example.com）。\n"
    "代理费123,456.78元，2026年10月15日签订于北京市海淀区。\n"
)
ORIGINAL_SURFACES = ("周测敏", "11010119900307867X", "13700009999",
                     "zhoubin@example.com")


def key(request_id):
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


class Recon:
    def __init__(self, harness_root: Path, anonymizer_root: Path):
        self.harness_root = harness_root
        self.anonymizer_root = anonymizer_root
        self.checks: list[dict] = []

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part, error=HarnessCommandError):
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc))
            return
        raise AssertionError(name + ": no typed error raised")

    def call(self, config, method, args):
        return legal_entry.call(method, args, config)

    def git(self, root: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True).strip()

    def run(self) -> int:
        temporary = tempfile.TemporaryDirectory()
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        store = MatterStore(state_root)
        store.create_matter(MATTER, "cas://profile-f08-recon")
        store.create_matter(MATTER_OTHER, "cas://profile-f08-recon")

        config = {
            "harness_public_entry":
                str(self.harness_root / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 90,
        }

        # 0. 分支核对（git 只读）：harness w2a-u05 基于 w1-u07；anonymizer
        #    安装面在 w2a-u05。
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref", "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w1-u07")
        self.step("harness_branch", branch == "w2a-u05", branch=branch)
        self.step("harness_base", base.startswith("0a2e6c92"), base=base)
        from legal_anonymizer.application import overlay_service
        anonymizer_branch = self.git(
            self.anonymizer_root, "rev-parse", "--abbrev-ref", "HEAD")
        overlay_file = Path(overlay_service.__file__).resolve()
        under_anonymizer = str(overlay_file).startswith(
            str(self.anonymizer_root.resolve()))
        self.step("anonymizer_branch", anonymizer_branch == "w2a-u05",
                  branch=anonymizer_branch, overlay_module=str(overlay_file))
        self.step("overlay_module_from_repo", under_anonymizer)

        # 1. F08 原件登记（真 public_entry --materials-json）。
        doc_v1 = "委托代理合同（F08 对账合成 v1）。\n代理费123,456.78元。\n".encode("utf-8")
        doc_v2 = "委托代理合同（F08 对账合成 v2，校对后）。\n代理费123,456.78元。\n".encode("utf-8")
        registered = self.call(config, "harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rm-1"),
            "material": {"id": "mat-contract-recon", "kind": "digital_text",
                         "title": "委托代理合同（对账合成）",
                         "bytesB64": b64(doc_v1)}})
        self.step("register_material_revision1",
                  registered["revision"] == 1
                  and registered["admission"] == "candidate"
                  and registered["sha256"] == hashlib.sha256(doc_v1).hexdigest()
                  and registered["casRef"].startswith("cas://"),
                  sha256=registered["sha256"])

        # 2. 幂等重放＝同回执；异内容同 key＝冲突。
        replay = self.call(config, "harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rm-1"),
            "material": {"id": "mat-contract-recon", "kind": "digital_text",
                         "title": "委托代理合同（对账合成）",
                         "bytesB64": b64(doc_v1)}})
        self.step("idempotent_replay_same_receipt",
                  replay == registered)
        self.expect_error("same_key_different_bytes_conflict", lambda: self.call(
            config, "harness.register_material", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rm-1"),
                "material": {"id": "mat-contract-recon", "kind": "digital_text",
                             "title": "委托代理合同（对账合成）",
                             "bytesB64": b64(doc_v2)}}), "idempotency_conflict")

        # 3. 已用 id 新 key＝拒绝（不复活不覆写）。
        self.expect_error("used_id_new_key_refused", lambda: self.call(
            config, "harness.register_material", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rm-2"),
                "material": {"id": "mat-contract-recon", "kind": "digital_text",
                             "title": "同名（对账合成）", "bytesB64": b64(doc_v2)}}
        ), "material_id_conflict")

        # 4. 版本副本：rev2；旧 rev1 逐字节回读（CAS 摘要随读必验）。
        added = self.call(config, "harness.add_material_revision", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("ar-1"),
            "revision": {"materialId": "mat-contract-recon",
                         "bytesB64": b64(doc_v2), "note": "校对后（对账合成）"}})
        old = self.call(config, "harness.read_material",
                        {"scope": SCOPE, "material_id": "mat-contract-recon",
                         "revision": 1})
        new = self.call(config, "harness.read_material",
                        {"scope": SCOPE, "material_id": "mat-contract-recon",
                         "revision": 2})
        self.step("revision_copy_old_readable_back",
                  added["revision"] == 2 and added["baseRevision"] == 1
                  and base64.b64decode(old["bytesB64"]) == doc_v1
                  and base64.b64decode(new["bytesB64"]) == doc_v2
                  and old["casRef"] != new["casRef"]
                  and old["sha256"] == hashlib.sha256(doc_v1).hexdigest())

        # 5. 跨案引用拒绝：他案 scope 读/改＝not found；DTO 带他案 matterId＝mismatch。
        self.expect_error("cross_matter_read_refused", lambda: self.call(
            config, "harness.read_material",
            {"scope": SCOPE_OTHER, "material_id": "mat-contract-recon"}),
            "material_not_found")
        self.expect_error("cross_matter_revision_refused", lambda: self.call(
            config, "harness.add_material_revision", {
                "actor_id": "recon-lawyer-2", "scope": SCOPE_OTHER,
                "key": key("ar-other"),
                "revision": {"materialId": "mat-contract-recon",
                             "bytesB64": b64(doc_v2)}}), "material_not_found")
        self.expect_error("cross_matter_dto_refused", lambda: self.call(
            config, "harness.register_material", {
                "actor_id": "recon-lawyer-2", "scope": SCOPE_OTHER,
                "key": key("rm-x"),
                "material": {"id": "mat-x", "kind": "digital_text",
                             "matterId": MATTER,
                             "title": "跨案（对账合成）", "bytesB64": b64(doc_v1)}}
        ), "material_matter_mismatch")

        # 6. 准入链（HarnessUnits 种子径，与 harness 测试同链）。
        from legal_harness.business.units import HarnessUnits
        HarnessUnits(store).decide_materials(
            "recon-lawyer", SCOPE, key("dm-1"),
            [{"owner": "harness", "kind": "material",
              "id": "mat-contract-recon", "version": "2",
              "matterId": MATTER}],
            {"action": "accept",
             "reasonRef": {"owner": "harness", "kind": "reason",
                           "id": "r-recon", "version": "1", "matterId": MATTER},
             "receiptRef": {"owner": "harness", "kind": "receipt",
                            "id": "rc-recon", "version": "1",
                            "matterId": MATTER}})
        listing = self.call(config, "harness.list_materials", {"scope": SCOPE})
        revisions = listing["materials"][0]["revisions"]
        self.step("admission_chain_list_readback",
                  [r["revision"] for r in revisions] == [1, 2]
                  and revisions[-1]["admission"] == "accepted"
                  and revisions[0]["admission"] == "candidate"
                  and listing["materialCount"] == 1)

        # 7. 原件只读负向：CAS blob 被外部篡改→读必报错；还原后照常。
        blob = (state_root / "artifacts" / "sha256"
                / old["sha256"][:2] / old["sha256"])
        original_bytes = blob.read_bytes()
        try:
            blob.write_bytes(b"tampered")
            self.expect_error("tampered_cas_blob_fails_closed", lambda: self.call(
                config, "harness.read_material",
                {"scope": SCOPE, "material_id": "mat-contract-recon",
                 "revision": 1}), "cas_artifact_corrupt")
        finally:
            blob.write_bytes(original_bytes)
        restored = self.call(config, "harness.read_material",
                             {"scope": SCOPE, "material_id": "mat-contract-recon",
                              "revision": 1})
        self.step("restored_blob_reads_identical",
                  base64.b64decode(restored["bytesB64"]) == doc_v1)

        # 8. 目录只组织材料：投影目录删除重建/篡改，业务回读不变。
        workspace = Path(temporary.name) / "cases" / MATTER / "materials"
        def project() -> dict[str, str]:
            workspace.mkdir(parents=True, exist_ok=True)
            digest = {}
            for row in revisions:
                payload = self.call(config, "harness.read_material", {
                    "scope": SCOPE, "material_id": "mat-contract-recon",
                    "revision": row["revision"]})
                target = workspace / f"mat-contract-recon.r{row['revision']}.txt"
                content = base64.b64decode(payload["bytesB64"])
                target.write_bytes(content)
                digest[f"r{row['revision']}"] = hashlib.sha256(content).hexdigest()
            return digest
        first_projection = project()
        import shutil

        shutil.rmtree(workspace)
        rebuilt_projection = project()
        self.step("directory_rebuild_same_projection",
                  rebuilt_projection == first_projection
                  and set(rebuilt_projection) == {"r1", "r2"})
        (workspace / "mat-contract-recon.r1.txt").write_bytes(
            "目录被篡改（对账）".encode("utf-8"))
        after_tamper = self.call(config, "harness.read_material", {
            "scope": SCOPE, "material_id": "mat-contract-recon", "revision": 1})
        self.step("tampered_directory_business_unchanged",
                  base64.b64decode(after_tamper["bytesB64"]) == doc_v1)

        # 9. F09：同进程 P10 → 覆盖层新 revision → 旧件回读；原件字节不变。
        from legal_anonymizer.config import Config
        from legal_anonymizer.pipeline import deidentify
        overlay_config = {
            "anonymizer_contract": "p09/p10",
            "overlay_state_root": str(Path(temporary.name) / "overlay-state"),
        }
        original_file = Path(temporary.name) / "originals" / "contract.txt"
        original_file.parent.mkdir(parents=True)
        original_file.write_text(SYN_ORIGINAL, encoding="utf-8")
        original_digest = hashlib.sha256(original_file.read_bytes()).hexdigest()
        sanitized = deidentify(SYN_ORIGINAL, Config(
            use_llm=False, critic=False, policy="balanced", locale="zh")).text
        registered_overlay = self.call(overlay_config, "material.overlay_register", {
            "matterId": MATTER, "documentId": "doc-contract-recon",
            "original_path": str(original_file), "sanitized_text": sanitized})
        start = sanitized.index("周测敏")
        overlay_result = self.call(overlay_config, "material.overlay_apply", {
            "matterId": MATTER, "documentId": "doc-contract-recon",
            "user_overrides": [
                {"op": "redact_span", "start": start,
                 "end": start + len("周测敏"), "replacement": "PERSON_1"}]})
        old_view = self.call(overlay_config, "material.overlay_read", {
            "matterId": MATTER, "documentId": "doc-contract-recon", "revision": 1})
        new_view = self.call(overlay_config, "material.overlay_read", {
            "matterId": MATTER, "documentId": "doc-contract-recon", "revision": 2})
        self.step("overlay_new_revision_old_readable",
                  registered_overlay["revision"] == 1
                  and overlay_result["revision"] == 2
                  and overlay_result["baseRevision"] == 1
                  and old_view["text"] == sanitized
                  and "PERSON_1" in new_view["text"]
                  and "周测敏" not in new_view["text"]
                  and "originalPath" not in overlay_result)
        self.step("original_bytes_unchanged",
                  hashlib.sha256(original_file.read_bytes()).hexdigest()
                  == original_digest
                  == overlay_result["originalSha256"])

        # 10. F09 负向：覆盖层带回可捕获 PII＝拒；原件被改写＝拒。
        self.expect_error("overlay_carries_pii_refused", lambda: self.call(
            overlay_config, "material.overlay_apply", {
                "matterId": MATTER, "documentId": "doc-contract-recon",
                "user_overrides": [
                    {"op": "replace_text", "find": "委托人",
                     "replace": "委托人13700009999"}]}),
            "overlay_introduces_catchable_pii", error=NotConnected)
        original_file.write_text(SYN_ORIGINAL + "\n（被外部改动）", encoding="utf-8")
        self.expect_error("mutated_original_refused", lambda: self.call(
            overlay_config, "material.overlay_apply", {
                "matterId": MATTER, "documentId": "doc-contract-recon",
                "user_overrides": [
                    {"op": "replace_text", "find": "委托人",
                     "replace": "委托方"}]}),
            "overlay_original_mutated", error=NotConnected)
        original_file.write_text(SYN_ORIGINAL, encoding="utf-8")

        # 11. 合格引用交消费：只有覆盖层修订后的**合格视图**（人名已覆盖、
        # 复扫通过）入 harness 真源；覆盖前 base 视图（规则层诚实残留
        # 人名、REVIEW_REQUIRED 门控）留在 anonymizer 内不入域。原件表面
        # 零入 harness CAS（原件不出域红线实测）。
        handover = self.call(config, "harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rm-f09"),
            "material": {"id": "mat-f09-view-recon", "kind": "digital_text",
                         "title": "脱敏视图（F09 对账合成）",
                         "bytesB64": b64(new_view["text"].encode("utf-8"))}})
        stored = self.call(config, "harness.read_material", {
            "scope": SCOPE, "material_id": "mat-f09-view-recon", "revision": 1})
        self.step("handover_sanitized_view_roundtrip",
                  handover["revision"] == 1
                  and base64.b64decode(stored["bytesB64"]).decode("utf-8")
                  == new_view["text"])
        leaked: list[str] = []
        for blob_file in (state_root / "artifacts" / "sha256").glob("*/*"):
            if not blob_file.is_file():
                continue
            content = blob_file.read_bytes().decode("utf-8", errors="ignore")
            for surface in ORIGINAL_SURFACES:
                if surface in content:
                    leaked.append(f"{blob_file.name}:{surface[:3]}***")
        self.step("original_surfaces_never_reach_harness_cas", not leaked,
                  leaked=leaked)

        # 12. 桥 fail-closed 负向。
        self.expect_error("bridge_unconfigured_not_connected", lambda: self.call(
            {}, "harness.list_materials", {"scope": SCOPE}),
            "harness_public_entry_not_configured", error=NotConnected)
        self.expect_error("unknown_method_refused", lambda: self.call(
            config, "harness.material_delete", {"scope": SCOPE}),
            "method_not_connected", error=NotConnected)

        temporary.cleanup()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness-root", type=Path, default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--anonymizer-root", type=Path,
                        default=DEFAULT_ANONYMIZER_ROOT)
    parser.add_argument("--json", action="store_true",
                        help="append a machine-readable summary block")
    args = parser.parse_args()
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:", args.harness_root)
        return 3
    recon = Recon(args.harness_root, args.anonymizer_root)
    try:
        code = recon.run()
    except (AssertionError, HarnessCommandError, NotConnected) as error:
        print("RECON_FAIL:", error)
        if args.json:
            print(json.dumps({"summary": "RECON_FAIL", "checks": recon.checks},
                             ensure_ascii=False, indent=1))
        return 1
    print(f"RECON_OK, {len(recon.checks)} checks all PASS")
    if args.json:
        print(json.dumps({"summary": "RECON_OK", "checks": recon.checks,
                          "matter": MATTER},
                         ensure_ascii=False, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
