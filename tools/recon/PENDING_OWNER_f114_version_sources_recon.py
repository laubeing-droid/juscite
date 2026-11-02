"""F114 version-source reconciliation against the live harness entry (W2a-U06).

对账对象：harness 分支 w2a-u06（基于 w2a-u05@a2c5376f＝F08 材料真源与版本）
的 public_entry --materials-json 封闭径——与产品桥（legal_entry → 子进程
public_entry）完全同一条链。全部合成材料：临时状态根、合成 matter/文档
字节；harness 检出零字节改动（只运行其代码，git 只读命令核对分支）。

实跑覆盖（PENDING_OWNER_F114_version_sources_recon）：
  五 source 真值：register（rev1 恒 upload，DTO 无 source 字段可声明）→
  AI 提案（assistant_edit）→ 伪装负向（user_accept/reject 自封拒、闭集外
  拒）→ P04 decide_materials accept＝分版本记录（user_accept 行与提案同
  字节、同 CAS ref、来源不同）→ AI 再提 → reject＝版本分叉（fork 行携带
  存续字节、被拒提案保留可回读、后续 upload 建立在 fork 行）→ 决定记录
  DB 级 join（每条 user_accept/reject 行 100% 对上真实 material_decisions
  行）→ 文件字节可回读（全 revision 逐行 sha256/casRef 复算）→ CAS 篡改
  fail-closed → upload 头决定不产生新版本来源行 → P04 withdraw_material →
  P04 propose_materials（harness-owner 清单面，来源照实投影）。
  桥负向：未配置 NOT_CONNECTED／未知方法 method_not_connected。

用法：
  python -X utf8 tools/PENDING_OWNER_f114_version_sources_recon.py [--harness-root <path>] [--json]

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

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo\.local\worktrees\w2a-u06")

MATTER = "m-f114-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
MATERIAL = "mat-contract-f114"

# 合成文档字节（用户原件 / AI 修订提案 / AI 第二轮提案 / 用户改后上传）。
DOC_V1 = "委托代理合同（F114 对账合成 v1，用户上传）。\n代理费123,456.78元。\n".encode("utf-8")
DOC_AI_1 = "委托代理合同（F114 对账合成 AI 修订提案 1）。\n代理费123,456.78元。\n".encode("utf-8")
DOC_AI_2 = "委托代理合同（F114 对账合成 AI 修订提案 2）。\n代理费123,456.78元。\n".encode("utf-8")
DOC_V2_USER = "委托代理合同（F114 对账合成 v2，用户改后上传）。\n".encode("utf-8")

FIVE_SOURCES = {"upload", "assistant_edit", "user_accept", "reject", "generated"}
DECISION_SOURCES = {"user_accept", "reject"}


def key(request_id):
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def material_ref(version):
    return {"owner": "harness", "kind": "material", "id": MATERIAL,
            "version": str(version), "matterId": MATTER}


def decision(action, suffix):
    return {
        "action": action,
        "reasonRef": {"owner": "harness", "kind": "reason",
                      "id": f"r-f114-{suffix}", "version": "1",
                      "matterId": MATTER},
        "receiptRef": {"owner": "harness", "kind": "receipt",
                       "id": f"rc-f114-{suffix}", "version": "1",
                       "matterId": MATTER},
    }


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
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

    def query(self, store, sql, params):
        import contextlib
        import sqlite3
        with contextlib.closing(store._connect()) as connection:
            rows = connection.execute(sql, params).fetchall()
        return [dict(row) if isinstance(row, sqlite3.Row) else row
                for row in rows]

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
        store.create_matter(MATTER, "cas://profile-f114-recon")

        config = {
            "harness_public_entry":
                str(self.harness_root / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 90,
        }

        # 0. 分支核对（git 只读）：harness w2a-u06 基于 w2a-u05。
        branch = self.git(self.harness_root, "rev-parse", "--abbrev-ref", "HEAD")
        base = self.git(self.harness_root, "merge-base", "HEAD", "w2a-u05")
        self.step("harness_branch", branch == "w2a-u06", branch=branch)
        self.step("harness_base", base.startswith("a2c5376f"), base=base)

        # 1. register：revision 1 恒 upload（真值由构造，DTO 无 source 字段）。
        registered = self.call(config, "harness.register_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rm-1"),
            "material": {"id": MATERIAL, "kind": "digital_text",
                         "title": "委托代理合同（F114 对账合成）",
                         "bytesB64": b64(DOC_V1)}})
        self.step("register_revision1_source_upload",
                  registered["revision"] == 1
                  and registered["source"] == "upload"
                  and registered["sha256"] == hashlib.sha256(DOC_V1).hexdigest()
                  and registered["casRef"].startswith("cas://"),
                  source=registered["source"], sha256=registered["sha256"])
        self.expect_error("register_dto_source_field_refused", lambda: self.call(
            config, "harness.register_material", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("rm-bad"),
                "material": {"id": "mat-other", "kind": "digital_text",
                             "title": "伪装负向（对账合成）",
                             "bytesB64": b64(DOC_V1), "source": "assistant_edit"}},
            ), "fields_not_closed")

        # 2. AI 修订提案：rev2 source=assistant_edit；字节回读逐字节相同。
        proposal = self.call(config, "harness.add_material_revision", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("ar-1"),
            "revision": {"materialId": MATERIAL, "bytesB64": b64(DOC_AI_1),
                         "source": "assistant_edit"}})
        proposal_read = self.call(config, "harness.read_material",
                                  {"scope": SCOPE, "material_id": MATERIAL,
                                   "revision": 2})
        self.step("ai_proposal_source_truthful_bytes_back",
                  proposal["revision"] == 2
                  and proposal["source"] == "assistant_edit"
                  and base64.b64decode(proposal_read["bytesB64"]) == DOC_AI_1
                  and proposal_read["source"] == "assistant_edit")

        # 3. 伪装负向：决定来源不可自封；枚举闭集外拒。
        for claimed in ("user_accept", "reject"):
            self.expect_error(
                f"self_declared_{claimed}_refused",
                lambda claimed=claimed: self.call(
                    config, "harness.add_material_revision", {
                        "actor_id": "recon-lawyer", "scope": SCOPE,
                        "key": key(f"ar-bad-{claimed}"),
                        "revision": {"materialId": MATERIAL,
                                     "bytesB64": b64(DOC_AI_2),
                                     "source": claimed}}),
                "material_source_not_writable")
        self.expect_error("source_outside_enum_refused", lambda: self.call(
            config, "harness.add_material_revision", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("ar-bad-enum"),
                "revision": {"materialId": MATERIAL, "bytesB64": b64(DOC_AI_2),
                             "source": "lawyer_edit"}}), "material_source_invalid")

        # 4. P04 decide accept＝分版本记录：rev3 user_accept 与提案同字节
        #    同 CAS ref、来源不同；同 key 重放不双写。
        accepted = self.call(config, "harness.decide_materials", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dm-acc"),
            "material_refs": [material_ref(2)],
            "decision": decision("accept", "acc")})
        replay = self.call(config, "harness.decide_materials", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dm-acc"),
            "material_refs": [material_ref(2)],
            "decision": decision("accept", "acc")})
        accepted_row = self.call(config, "harness.read_material",
                                 {"scope": SCOPE, "material_id": MATERIAL,
                                  "revision": 3})
        self.step("accept_forks_user_accept_revision",
                  accepted["versionRefs"][0]["version"] == "3"
                  and accepted_row["source"] == "user_accept"
                  and accepted_row["sha256"] == proposal["sha256"]
                  and accepted_row["casRef"] == proposal["casRef"]
                  and base64.b64decode(accepted_row["bytesB64"]) == DOC_AI_1
                  and accepted_row["admission"] == "accepted"
                  and accepted_row["decisionRef"]["action"] == "accept")
        self.step("accept_replay_no_double_append",
                  replay["receipt"] == accepted["receipt"])

        # 5. 决定记录 DB 级 join：rev3 decisionId → 真实 material_decisions 行。
        decision_id = accepted_row["decisionRef"]["decisionId"]
        rows = self.query(store,
                          "SELECT * FROM material_decisions WHERE decision_id=?",
                          (decision_id,))
        self.step("user_accept_backed_by_real_decision_row",
                  len(rows) == 1 and rows[0]["decision"] == "accept"
                  and rows[0]["material_revision"] == 2
                  and "rc-f114-acc" in rows[0]["decision_ref"],
                  decision_id=decision_id)

        # 6. AI 第二轮提案 → P04 decide reject＝版本分叉：fork 行携带存续
        #    字节（已接受的 user_accept 内容），被拒提案保留可回读。
        proposal2 = self.call(config, "harness.add_material_revision", {
            "actor_id": "recon-assistant", "scope": SCOPE, "key": key("ar-2"),
            "revision": {"materialId": MATERIAL, "bytesB64": b64(DOC_AI_2),
                         "source": "assistant_edit"}})
        rejected = self.call(config, "harness.decide_materials", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dm-rej"),
            "material_refs": [material_ref(4)],
            "decision": decision("reject", "rej")})
        fork_row = self.call(config, "harness.read_material",
                             {"scope": SCOPE, "material_id": MATERIAL,
                              "revision": 5})
        rejected_proposal = self.call(config, "harness.read_material",
                                      {"scope": SCOPE, "material_id": MATERIAL,
                                       "revision": 4})
        self.step("reject_forks_to_surviving_bytes",
                  rejected["versionRefs"][0]["version"] == "5"
                  and fork_row["source"] == "reject"
                  and base64.b64decode(fork_row["bytesB64"]) == DOC_AI_1
                  and fork_row["sha256"] == accepted_row["sha256"]
                  and rejected_proposal["admission"] == "rejected"
                  and rejected_proposal["source"] == "assistant_edit"
                  and base64.b64decode(rejected_proposal["bytesB64"]) == DOC_AI_2
                  and fork_row["decisionRef"]["action"] == "reject")
        rows = self.query(store,
                          "SELECT * FROM material_decisions WHERE decision_id=?",
                          (fork_row["decisionRef"]["decisionId"],))
        self.step("reject_backed_by_real_decision_row",
                  len(rows) == 1 and rows[0]["decision"] == "reject"
                  and rows[0]["material_revision"] == 4)

        # 7. 版本分叉后手：后续 upload 建立在 fork 行（头＝5）不在被拒提案上。
        after = self.call(config, "harness.add_material_revision", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("ar-after"),
            "revision": {"materialId": MATERIAL, "bytesB64": b64(DOC_V2_USER)}})
        self.step("next_revision_builds_on_fork_row",
                  after["baseRevision"] == 5 and after["source"] == "upload"
                  and base64.b64decode(
                      self.call(config, "harness.read_material",
                                {"scope": SCOPE, "material_id": MATERIAL,
                                 "revision": 6})["bytesB64"]) == DOC_V2_USER)

        # 8. upload 头决定＝只记决定不产生新版本来源行。
        upload_decided = self.call(config, "harness.decide_materials", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("dm-acc-u"),
            "material_refs": [material_ref(6)],
            "decision": decision("accept", "accu")})
        self.step("upload_head_accept_no_new_version_source",
                  upload_decided["versionRefs"] == [])

        # 9. 文件字节可回读（CAS hash 全链）：逐 revision 复算。
        listing = self.call(config, "harness.list_materials",
                            {"scope": SCOPE})
        revisions = listing["materials"][0]["revisions"]
        chain_ok = True
        for row in revisions:
            read = self.call(config, "harness.read_material",
                             {"scope": SCOPE, "material_id": MATERIAL,
                              "revision": row["revision"]})
            content = base64.b64decode(read["bytesB64"])
            chain_ok = chain_ok and row["revision"] == read["revision"] \
                and hashlib.sha256(content).hexdigest() == read["sha256"] \
                and read["casRef"] == f"cas://{read['sha256']}" \
                and read["bytesLength"] == len(content)
        sources = [row["source"] for row in revisions]
        self.step("all_revisions_bytes_readable_hash_match", chain_ok,
                   revisions=len(revisions))
        self.step("source_chain_sequence",
                  sources == ["upload", "assistant_edit", "user_accept",
                              "assistant_edit", "reject", "upload"],
                  sources=sources)
        self.step("sources_within_five_enum",
                  set(sources) <= FIVE_SOURCES)

        # 10. DB 级扫描：每条决定来源行 100% join 真实决定行（合同级真实
        #     决定记录），且全库 source 无枚举外值。
        material_rows = self.query(
            store,
            "SELECT revision, material_json FROM material_candidates"
            " WHERE matter_id=?", (MATTER,))
        decision_rows = {
            row["decision_id"]: row for row in self.query(
                store,
                "SELECT * FROM material_decisions WHERE matter_id=?", (MATTER,))}
        decision_sourced, enum_ok = [], True
        for row in material_rows:
            payload = json.loads(row["material_json"])
            source = payload.get("source", "upload")
            enum_ok = enum_ok and source in FIVE_SOURCES
            if source in DECISION_SOURCES:
                decision_sourced.append((row["revision"], source, payload))
        join_ok = all(
            payload["decisionRef"]["decisionId"] in decision_rows
            and decision_rows[payload["decisionRef"]["decisionId"]][
                "material_revision"] == payload["decisionRef"]["decidedRevision"]
            for _, _, payload in decision_sourced)
        self.step("every_decision_source_joins_real_decision",
                  join_ok and enum_ok and len(decision_sourced) == 2,
                  decision_sourced=len(decision_sourced))

        # 11. CAS 篡改 fail-closed（fork 行 blob）＋还原后照常。
        blob_path = (state_root / "artifacts" / "sha256"
                     / fork_row["sha256"][:2] / fork_row["sha256"])
        original_blob = blob_path.read_bytes()
        try:
            blob_path.write_bytes(b"tampered-by-recon")
            self.expect_error("tampered_fork_blob_read_fails_closed",
                              lambda: self.call(
                                  config, "harness.read_material",
                                  {"scope": SCOPE, "material_id": MATERIAL,
                                   "revision": 5}),
                              "cas_artifact_corrupt", error=HarnessCommandError)
        finally:
            blob_path.write_bytes(original_blob)
        restored = self.call(config, "harness.read_material",
                             {"scope": SCOPE, "material_id": MATERIAL,
                              "revision": 5})
        self.step("restored_blob_readable_back",
                  base64.b64decode(restored["bytesB64"]) == DOC_AI_1)

        # 12. P04 withdraw_material：头行 withdrawn，来源不改。
        withdrawn = self.call(config, "harness.withdraw_material", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("wm-1"),
            "material_ref": material_ref(6),
            "decision": decision("withdraw", "wd")})
        withdrawn_row = self.call(config, "harness.read_material",
                                  {"scope": SCOPE, "material_id": MATERIAL,
                                   "revision": 6})
        self.step("withdraw_marks_head_source_unchanged",
                  "invalidatedRefs" in withdrawn
                  and withdrawn_row["admission"] == "withdrawn"
                  and withdrawn_row["source"] == "upload")

        # 13. P04 propose_materials（harness-owner 清单面）：来源照实投影。
        proposed = self.call(config, "harness.propose_materials", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("pm-1"),
            "bundle_ref": {"owner": "harness", "kind": "sanitized-bundle",
                           "id": "b-f114", "version": "1"},
            "manifest_ref": {"owner": "harness", "kind": "source-manifest",
                             "id": "sm-f114", "version": "1"}})
        proposed_sources = sorted({
            m.get("source", "upload") for m in proposed["materials"]})
        self.step("propose_lists_true_sources",
                  proposed_sources == ["upload"]
                  and any(m["id"] == MATERIAL for m in proposed["materials"]),
                  sources=proposed_sources)

        # 14. 桥负向：未配置 NOT_CONNECTED／未知方法（改来源伪方法）拒。
        try:
            legal_entry.call("harness.decide_materials", {"scope": SCOPE}, {})
            raise AssertionError("bridge_unconfigured_not_connected")
        except NotConnected as exc:
            self.step("bridge_unconfigured_not_connected",
                      "harness_public_entry_not_configured" in str(exc))
        try:
            legal_entry.call("harness.material_set_source",
                             {"scope": SCOPE}, config)
            raise AssertionError("bridge_unknown_method_refused")
        except NotConnected as exc:
            self.step("bridge_unknown_method_refused",
                      "method_not_connected" in str(exc))

        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness-root", type=Path, default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--json", action="store_true",
                        help="append a machine-readable summary block")
    args = parser.parse_args()
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:", args.harness_root)
        return 3
    recon = Recon(args.harness_root)
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
