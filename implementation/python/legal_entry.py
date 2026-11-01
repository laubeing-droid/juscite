"""Product Python bridge entry (E09 wiring, W1-U03 / P01 + W1-U01 / E07): frozen method
whitelist over public Python surfaces only; no successful stub, no arbitrary
import/getattr. The JC wiring consumes the pinned juris-calculus checkout
read-only (14-Python入口证据.csv P01): create_local_client plus the four
local faces local_case_bundle / evaluate_harness_bundle / local_read_run /
local_horn_subject_state, and the mandated delivery read-back pair
business_delivery_documents / verify_business_delivery (evaluate 后 owner 回读).
A bundle must be built and evaluated on one client instance (the local
resolver overlay is per-client), so jc.evaluate takes bundle kwargs and does
both in one call; a bundle JSON produced by another process is not
re-admittable. Missing config or unknown methods fail NOT_CONNECTED (exit 3);
JC-side failures surface as JC_FAILURE with a named code (exit 4), never a
fake OWNER_RESPONSE. Delivery file bytes cross the JSON boundary as base64.

E07 goal-ledger wiring (W1-U01): harness.* goal methods dispatch through the
harness public_entry --goal-json closed path (resolve_provider_method behind
the only mechanical entrypoint) via a subprocess — the product never imports
harness internals and never keeps a second goal ledger. Must be deployed with
product-side matter/user authorization before UI exposure.

F118 schedule-loop wiring (W1-U07): harness.schedule_event / schedule_list /
schedule_cancel / reminder_report ride the same closed provider dispatch via
the --schedule-json envelope (separate surface, same fail-closed discipline;
harness docs/f118-schedule-contract.md). The desktop-notification trigger and
delivery reporting live in f118_scheduler.py; this file only routes.

F25 batch-review write-guard wiring (W2b-U01): the harness.review_batch_*
method group (row lease + generation guard + post-claim snapshots; harness
docs/f25-lease-generation-contract.md) rides the same closed provider dispatch
via the --reviewbatch-json envelope. This file only routes — all lease and
generation truth stays in the harness public face; late results (expired
lease / stale generation) surface their typed codes and never overwrite
newer results or human cell edits.

E15 path & new-evidence contract wiring (W2b-U23): the harness.path_candidate_*
/ assessment_delta_* / branch_projection_* method group (harness
docs/e15-path-evidence-contract.md) rides the same closed provider dispatch
via the --pathevidence-json envelope. This file only routes — path
candidates stay proposals until a lawyer adopts (adoption registers the
issue through the frozen narrow issue fields, never a widened payload),
assessment deltas without basis stay undetermined (no fake support), and
branch projections are verbatim transcriptions of the JC public exit (empty
branchRefs = that run has no branches; the bridge never manufactures them).

F50 re-anchor + F51 verbatim gate wiring (W2b-U13): the anchor.* method
group (register/locate/gate_edit/manual_queue/read) over the product-side
document_anchor face. Positioning is always re-derived by exact substring
search of the quoted original text in the current text (no folding, case
sensitive, overlaps counted) — stored spans are registration-time
provenance only and never converted into new positions; zero/multiple hits
return no position fields at all. Edits ride the same verbatim gate: a
single hit is the only path to PROCEED, NOT_FOUND/AMBIGUOUS refuse the
auto edit and enqueue a manual entry (quote + proposed replacement + named
reason, append-only); nearest-match code does not exist in the face.

F45 channel-1 agent CLI direct document edit (W2b-U15): the docxedit.*
method group routes to the product-side docx_edit document-adapter. apply
reads the base bytes from the harness material at a pinned base_revision
(CAS-verified readback), deterministically generates BOTH a clean DOCX and
an annotated-revision DOCX (w:ins/w:del tracked changes plus w:comment
annotations; pure Python, no host automation — channel 2 is U16), passes
the independent lxml-based fidelity gate before anything is persisted, and
registers the result through the U11 contract: add_material_revision
(source=assistant_edit from the F114 closed set) plus formal_propose
(channel=machine, quotes derived from the edit set). Outputs are
append-only (old drafts are never overwritten); the same request id
replays idempotently.

E17 evidence-attempt wiring (W2b-U25): the harness.evidence_attempt_*
method group (harness docs/e17-evidence-attempt-contract.md) rides the same
closed provider dispatch via the --evidenceattempt-json envelope. This file
only routes — the ledger truth (application/receipt/resolution/cost events,
open/closed rounds, coverage-by-distinct-item, proof gap) stays in the
harness public face; coverage is never a file count, no application means
not executed and no receipt means not obtained, true refusals and overdue
outcomes must carry sources, and closing a round never checks off the proof
gap (task completion and proof gap are presented separately).

F82 review-ops wiring (W2b-U31): the harness.review_receipt_* /
review_cell_rerun / review_cell_history method group (harness docs/
f82-review-ops-contract.md) rides the same closed provider dispatch via the
--reviewbatch-json envelope, plus the product tabular.* review-ops group
(tabular_review_ops.py): review receipts carry reviewer + decision ref and
never touch the machine molecules (E11 precedent); a single-cell rerun is
lease-per-row / cell-granularity new generation with the three named
refusals (late lease / stale generation / rerun-after-human-edit never
overwrites a human cell); old cell values stay readable along the F25
revision chain. Human cell edits ride the existing
harness.review_batch_human_edit write-permission method — the UI never
gets a second write channel.

F29 cache partition discipline (W3-U05): cache.plan / cache.fingerprint —
the partition/fingerprint/lineage derivation over the SELECTED CORE CACHE
(the upstream native promptCacheKey lineage + shared-prefix ordering, both
pinned unmodified by the recon). Pure derivation, zero storage: no second
cache engine is created and the upstream cache policy is untouched. The
face reports no hit-rate metric — the advertised rates in the source
blueprint are a vendor claim, never a JusBench acceptance criterion
(ledger states this explicitly on the F29 rows).

F30 airplane mode (W3-U05): airplane.status / airplane.set /
airplane.egress_decision — the one-click offline posture. Upstream
app/desktop landing = implementation/patches/017 (flag read + service-env
propagation + desktop extension-download guard, verify_patch prestate);
this bridge plane owns the flag state, the closed egress decision table
over the E10 egress inventory, and the two LIVE gates on dispatch paths
that can reach a remote endpoint (review_chat model round, lcr case
retriever — refused before any connection). Offline read/calc (E22 codices
frozen face, statute face, JC calc faces) is never gated.

E16 cash-contract wiring (W2b-U51): two frozen groups. The harness.cash_*
method group (entitlement/source/transfer/outflow/allocation/balance; the
DEDICATED creditor cash ledger, harness docs/e16-cash-contract.md) rides
the closed provider dispatch via the --cashcontract-json envelope — it
NEVER routes a case receivable through harness.record_payment (the F08
bill channel is bill-linked firm billing; the harness refuses it typed).
The cash.balance / cash.allocate group goes through the pinned P01
JCClient surface (jc-cash-contract/1): money is integer minor end-to-end
(float inputs refused typed), every balance answer carries the five-column
net vector (source_total | client_gross | outflow | client_net |
court_held), same-source dedup is structural (one realityKey = one source;
the Q→client transfer moves HOLDING and never mints a second source, so
source180k never becomes 230k), and a sheet is sealed only after the
independent checker agrees. The JC receipt refs (cashBalanceRef /
cashAllocationRef, owner=jc + sha256 digest) are what the harness ledger
rows pin back — transfer/outflow/allocation events require them; the
bridge only transcribes, never fabricates.

F123 signed-export manifest wiring (W4-U54): three frozen groups over the
tamper-evident export face (06 F123 v1.5, owner=harness+product). The
signer (signed_export.export_*) hashes every exported file, signs the
canonical manifest with HMAC-SHA256 (key = random 32 bytes living ONLY in
the product's local state signing.secret — manifests, ledger rows and
receipts carry the keyFingerprint, never the key), and the export is not
complete until harness.export_record_create pins manifest_sha256 +
file_set_digest (both independently recomputed by the ledger) — no ledger
receipt, no export. Verification is a DIFFERENT code path
(export_manifest_checker.export.verify — zero import of the signer,
walks the actual directory, localizes all three tamper forms to the
specific file); the checker never signs and the ledger never verifies.
Exposure probes ride the same face: export.secret_exposure_scan (F41
batch_secret_exposure method) plus the recon-side release-artifact byte
scan (W3-U33 F77 method).

F78/F79 licensing wiring (W5-U01): two frozen groups over the distribution
license faces (06 V7-78/V7-79, owner=distribution; desktop/selfhost).
license.activate installs an offline license token after F79 verification
(Ed25519 signature over canonical payload bytes against deployment trust
anchors config.license_trusted_pubkeys — the token never carries its own
trust anchor — plus device fingerprint binding and validity window);
license.check is the daily revalidation against config.license_service_url
(at most one network check per 24h window; an unreachable service opens a
one-time grace budget anchored at the last valid check — never extended,
never faked; revoked is recorded as the real state); license.status
projects the closed state set (not_activated/authorized/grace/grace_expired/
revoked/license_expired/clock_rollback_detected) strictly from persisted
facts — service interruption never deletes data and never projects
authorized. license.verify_offline / license.device_fingerprint /
license.clock_status are the F79 face; license_verify.now_checked is the
single clock authority for the whole license domain: a monotonic watermark
(sealed with an HMAC key stored in the F12 vault, lvyin.f79/
clock-watermark-hmac-v1) refuses clock rollback typed before any license
decision. The issuing private key exists ONLY in the construction-side
synthetic issuer (tools/license_issuer_synth.py, adjudication #13-19
synthetic-first, named recycle point for the v2 commercial facility) — the
product faces structurally carry verification paths only.

F06 MFA two-step verification wiring (W5-U08): the auth.* / mfa.* frozen
group over the product-side mfa_auth face (06 V7-06 v2, owner=product,
UI_HOST_OR_NEW_PRODUCT). Preserved decision honored as structure: the
password-level base (auth.register/auth.login, PBKDF2 verifiers only) is
the on-prem auth floor (自托管部署形态) and TOTP/recovery codes ride it as an
enhancement layer — no second identity authority is created and the F04
case-permission face (already VERIFIED) is untouched. MFA credentials
(TOTP key, recovery-code salted hashes) live ONLY in the F12 credential
vault (lvyin.mfa/* DPAPI blobs); every TOTP path takes an explicit `now`
epoch (deterministic synthetic clock: expiry/replay/consumed windows are
reproducible); secrets and recovery codes never appear in any persisted
surface or log (byte-level zero-plaintext scan is part of acceptance).

F137 scheduled agent tasks (W5-U12): the f137.* frozen group over the
product-side f137_scheduled_tasks face (06 V7-137 v2, owner=product,
UI_HOST_OR_NEW_PRODUCT). The acceptance vector「v2才启用具体定时任务，
时区/授权/失败/停止/幂等实际验证；不同于v1持续任务故障恢复」lands as
structure: a literal-True config stage gate (v2 only), a per-task explicit
authorization established in the same creation command (grantId bound
once, following the VERIFIED F24/F26 owner-unique face), deterministic
zoneinfo schedule math with an injected clock (DST/month-end edges
reproducible, zero floating-point time), idempotent fire receipts (same
scheduled instant never launches twice), named cancellation that stops
further launches (in-flight interrupt rides the F23 stop endpoint), and
crash-unknown occurrences that fail closed until an explicit human
reconcile. Tasks fire through the existing core loop only (one
create+prompt per occurrence; completion bookkeeping stays with the F23
server-owned face) — no second agent loop, no overlap with the VERIFIED
F118 reminder loop (this face never reads the harness schedule nor
creates reminders).

F141 comment-permission + F142 approval-flow wiring (W5-U13; v2; owner=
harness+product; harness docs/f141-f142-collab-lifecycle-contract.md,
schema v37 three ledgers): three frozen groups. HARNESS_COLLABDOC_METHODS
rides --collabdoc-json: the P04 note/review-round pair reused zero-change
plus the comment contract — writes pass the live F04 read gate in the same
transaction (revocation lands immediately), every comment pins a REAL F08
material revision (no "latest" auto-follow), and the shared-reader path
rides the F05 share token with an EXACT (materialId, revision) binding;
projections carry refs/sha and comments, never original bytes.
HARNESS_APPROVAL_METHODS rides --approval-json: approval rounds anchor the
prepare_formal preparation manifest (sha verified present in the CAS); the
only channel recording a decision is the explicit decide call under the
live manage gate — the login-free approval page is a limited-scope
read-only projection and never records anything (采用后实记); page tokens
are sha256 at rest and revocation is immediately effective.
HARNESS_FORMAL_LIFECYCLE_METHODS rides the existing P02
--prepare-formal-json/--commit-formal-json envelopes via a passthrough
service entry (the field-closed contract lives harness-side; zero change
to the commit_formal terminal surface — v1 files finalize exactly as
before, never waiting on v2 approvals). The bridge only routes; every
truth check stays harness-side. Unknown or unconfigured never stub
success.

"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from base64 import b64decode, b64encode
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from opencode_http import TransportError
from bridge_errors import HarnessCommandError, NotConnected, SessionRejected  # noqa: F401 (re-export)
import atrest_key as atrest_key_module  # F10 at-rest 密钥供给面（W4-U32）

# E07 goal surface only (e07-goal-contract §2). The remaining HARNESS_PROVIDER_
# METHODS stay unwired here until their obligation (E09) lands — unknown or
# unconnected methods fail closed, they never stub success.
HARNESS_GOAL_METHODS = frozenset({
    "harness.save_goal", "harness.revoke_goal", "harness.get_goal",
    "harness.list_goals", "harness.decide_goal_plan", "harness.adopt_goal_task",
    "harness.pause_goal", "harness.resume_goal", "harness.list_goal_pauses",
    "harness.read_goal_basis",
})

# E18 客户目标与策略 basis（W2b-U52；harness docs/e18-strategy-basis-
# contract.md）：HARNESS_GOAL_METHODS 同族新组——策略依赖账六方法走
# 同一封闭 public_entry provider dispatch（--strategybasis-json 信封，
# 独立成面供产品桥分别枚举）。策略行钉 goal 版本引用（T16 goal 账唯
# 一权威，伪造/漂移具名拒）；三门（事实/法律/策略）分别判定，请求携
# 带总分/合并字段即 strategy_combined_verdict_refused；硬约束违反由账
# 本把 overall 推导为 fail，不得被其他维度总分掩盖；评估行必带 JC 评
# 估回执 ref（owner=jc，经 STRATEGY_BASIS_JC_METHODS 的
# jc.strategy_evaluate 取得）；依赖时效三分判＝读取投影：goal-only 变
# 更（fact/law 同版）→策略门 STALE 而事实/法律门各自独立。现组零动；
# 未配置/未知方法绝不 stub 成功。
HARNESS_STRATEGY_METHODS = frozenset({
    "harness.strategy_basis_register", "harness.strategy_basis_evaluate",
    "harness.strategy_basis_read", "harness.strategy_basis_list",
    "harness.strategy_evaluation_read", "harness.strategy_evaluation_list",
})

# E20 VOI 和多解释实际支持（W2b-U53；harness docs/e20-voi-contract.md）：
# HARNESS_STRATEGY_METHODS 同族新组——VOI 请求/回执账四方法走同一封闭
# public_entry provider dispatch（--voi-json 信封，独立成面供产品桥分
# 别枚举）。VOI 请求＝信息集分区/合法行动集/概率效用成本输入闭集四件
# 全齐才收（缺一具名拒）；概率证据只收 owner=jc 的登记回执 ref（裸数
# 字概率结构性进不来）；回执只转录 JC voi-analysis 回执（voiKnown 派生
# supported，harness 只转录不重算不造数值）；未支持＝具名 NOT_COMPLETE
# （值恒 null 不填 PASS）。现组零动；未配置/未知方法绝不 stub 成功。
HARNESS_VOI_METHODS = frozenset({
    "harness.voi_request_register", "harness.voi_receipt_record",
    "harness.voi_read", "harness.voi_list",
})

# F24 durable run 事件账（W3-U03；harness 分支 w3-u03 schema v24）：
# HARNESS_VOI_METHODS 同族新组——run 事件账四方法走同一封闭 public_entry
# provider dispatch（--runledger-json 信封，独立成面供产品桥分别枚举）。
# 业务 run 账主=harness（owner 唯一）；同键重放异内容＝
# run_event_key_conflict 具名拒（e07_live_recon core session inbox
# HTTP 409 同语义在 harness 账本的落点）；终局事件必须钉 owner 链
# terminal_results 回执——宿主（Host）只有投影/游标/批准恢复元数据，
# 不另造业务终局；乐观锁 expectedHeadSeq；SSE cursor 游标投影。现组
# 零动；未配置/未知方法绝不 stub 成功。
HARNESS_RUN_LEDGER_METHODS = frozenset({
    "harness.run_event_append", "harness.run_events_read",
    "harness.run_projection_read", "harness.run_list",
})

# F26 工具治理账（W3-U03；harness 分支 w3-u03 schema v24）：治理合同
# 声明（revision 只追加、denyByDefault 必须 literal True＝T07
# legal-review 尾置 deny 配置面同款纪律）＋deny-closed 判定面三方法走
# 同一封闭 public_entry provider dispatch（--toolgov-json 信封，独立成
# 面供产品桥分别枚举）。未广告/未授权工具、读写越区、执行越档、skill
# 黑名单一律具名 deny；执行后端=core 权限求值（唯一强制点），本面是宿
# 主配置必须与之符合的可审计合同。现组零动；未配置/未知方法绝不 stub
# 成功。
HARNESS_TOOL_GOVERNANCE_METHODS = frozenset({
    "harness.tool_governance_register", "harness.tool_governance_read",
    "harness.tool_governance_decide",
})

# F122 利益冲突查重（W4-U53；06 F122 v1.5，owner=product+harness，P04
# 收案前合规小件「规则匹配即可」）：conflict 面 harness 账本半边桥——
# 九方法走同一封闭 public_entry provider dispatch（--conflict-json 信封，
# 独立成面；harness docs/f122-conflict-check-contract.md）。账本级硬点：
# 真实匹配＝确定性规则匹配（主体名/别名/曾用名精确+受控规范化——零模糊
# 语义，LegalTech 约束 1）；命中＝冲突候选账 append-only；解除＝人工决定
# 面（decision_ref 必带＝E24 F62 人审确认闸同构：未审不入库）留范围记录
# （谁/何时/基于什么范围）；别名/曾用名维护留版本（变更后历史匹配不追
# 溯改写）。检索在脱敏域内进行（查询名原样透传 harness store，返回仅投
# 影在域事实——原文名不出 anonymizer 映射，本组零 anonymizer 导入）。
# 本文件只路由——匹配/候选/解除账本真源全部在 harness 公开面；W09
# contacts.* 既有面零改动不重建。
CONFLICT_CHECK_METHODS = frozenset({
    "harness.conflict_case_party_attach", "harness.conflict_case_party_list",
    "harness.conflict_alias_record", "harness.conflict_alias_revoke",
    "harness.conflict_alias_list", "harness.conflict_check",
    "harness.conflict_release", "harness.conflict_candidates_list",
    "harness.conflict_candidate_read",
})

# F113 案件/项目/案号稳定身份＋散件归案（W3-U06；harness docs/
# f113-case-anchor-contract.md）：HARNESS_VOI_METHODS 同族新组——案件
# 锚点账六方法走同一封闭 public_entry provider dispatch（
# --caseanchor-json 信封，独立成面供产品桥分别枚举）。identity_kind
# 闭集 litigation/non_litigation/project；案号可选（非诉无案号合法
# ——结构性不强制；诉前未获号亦合法）；案号确定性归一后 sha256=
# case_number_digest，同一归一号至多钉一个案件 current 锚点（跨案件
# 同号 case_number_anchor_conflict 具名拒；改号=追加 revision 旧行
# current=0 不删）；case_number_resolve=案号→唯一案件锚点稳定解析；
# case_anchor_attach/list/item_read=散件归案锚点账（item_digest 钉
# 内容 sha256＋item_ref 互钉，同件归同案幂等）。现组零动；未配置/
# 未知方法绝不 stub 成功。
HARNESS_CASE_ANCHOR_METHODS = frozenset({
    "harness.case_identity_register", "harness.case_identity_read",
    "harness.case_number_resolve", "harness.case_anchor_attach",
    "harness.case_anchor_list", "harness.case_anchor_item_read",
})

# F118 schedule loop (W1-U07; harness docs/f118-schedule-contract.md §2):
# schedule_event / schedule_list / schedule_cancel / reminder_report over the
# same closed public_entry provider dispatch (--schedule-json envelope). Same
# fail-closed discipline: unknown or unconfigured methods never stub success.
HARNESS_SCHEDULE_METHODS = frozenset({
    "harness.schedule_event", "harness.schedule_list",
    "harness.schedule_cancel", "harness.reminder_report",
})

# F32 案件级记忆（W4-U34；harness schema v31 case_memory_entries；v1.5·
# TTL 差异点，2026-10-14 用户裁定）：记忆账六方法走同一封闭 public_entry
# provider dispatch（--memory-json 信封，独立成面供产品桥分别枚举）。
# 确认闸＝唯一通往生效的转移（proposed 永不进生效投影）；每条记忆强制
# 携带来源 ref＋TTL；TTL 过期与显式撤销在回读面真实消失（账行只追加可
# 审计）。「目标账本不被延后」＝本面与 E18 goal 账/E15/E17 账零写交叉
# （只读消费），goal 写路径对记忆零依赖零等待。现组零动；未配置/未知
# 方法绝不 stub 成功。
HARNESS_MEMORY_METHODS = frozenset({
    "harness.memory_propose", "harness.memory_confirm", "harness.memory_revoke",
    "harness.memory_read", "harness.memory_effective_list",
    "harness.memory_pending_list",
})

# F32 产品面（W4-U34；产品面 case_memory.py）：七方法——memory.extract
# （确定性蒸馏：会话转写→候选，正则标记闭集固定序，同输入同字节；产品
# 公开面命名避开 E23 冻结组禁词 distill——禁词纪律不豁免）＋
# propose/confirm/revoke/read/effective_list/pending_list 薄路由（确认闸
# 等真值语义全在 harness 面复制零份）。
MEMORY_METHODS = frozenset({
    "memory.extract", "memory.propose", "memory.confirm", "memory.revoke",
    "memory.read", "memory.effective_list", "memory.pending_list",
})

# F115 案件看板 v1 基础投影（W3-U20；harness w3-u20 分支合同）：只读聚合
# 投影一方法走同一封闭 public_entry provider dispatch（--dashboard-json
# 信封，独立成面供产品桥分别枚举）。在办×待办×日程×E15/E16/E17/E18 账面
# 摘要逐项转录既有公开方法回执（不造第二真源）；无写路径、不投影提醒派
# 发队列（F118 调度器独占）、零封皮断言（F115-v1.5/B4）。未配置/未知方法
# 绝不 stub 成功。
HARNESS_DASHBOARD_METHODS = frozenset({
    "harness.dashboard_read",
})

# F116 案件域分类（W3-U20；harness w3-u20 分支合同）：域字段账两方法走
# 同一封闭 public_entry provider dispatch（--casedomain-json 信封）。四值
# 闭集（诉讼/执行/非诉/刑事）＋显式 null=未分类；coverage 恒带
# exhaustiveClaim=false——分类不冒全域规则完备；写侧过 F04 案件写门。
HARNESS_CASE_DOMAIN_METHODS = frozenset({
    "harness.case_domain_declare", "harness.case_domain_read",
})

# F115-v1.5 案卷封皮全展开＋F116-v1.5 域分类分模块页面（W4-U49；harness
# w4-u49 分支合同）：只读两方法走封闭 public_entry provider dispatch
# （--cover-json/--module-json 信封，独立成面）。封皮字段全部绑定案件账
# 真实回读（F113/F116/F04/W08/待办/日程/E15-E18 转录——不造展示假字
# 段）；模块页＝看板 domainFilter 同一次投影（四具名域开页，unclassified
# 是筛选归纳表示值不是模块页；coverage 恒 exhaustiveClaim=false）。无写
# 路径、不投影提醒派发队列（F118 调度器独占）。未配置/未知方法绝不 stub
# 成功。
HARNESS_COVER_METHODS = frozenset({"harness.cover_read"})
HARNESS_MODULE_METHODS = frozenset({"harness.module_read"})

# F115/F116 产品面（W3-U20 v1＋W4-U49 v1.5；产品面 dashboard_projection.
# py）：五方法——dashboard.read（唯一只读取数入口＋渲染侧形状守卫：域值/
# 生命周期闭集、提醒派发键与封皮键出现具名拒、exhaustiveClaim=true 具名
# 拒）＋dashboard.domain_declare/domain_read（显式声明才有域，无自动分类
# 推断方法）＋dashboard.cover_read/module_read（v1.5 封皮/分模块页薄转发
# ＋形状守卫）。未配置/未知方法绝不 stub 成功。
DASHBOARD_METHODS = frozenset({
    "dashboard.read", "dashboard.domain_declare", "dashboard.domain_read",
    "dashboard.cover_read", "dashboard.module_read",
})

# F04/F92 案件权限 user/org/role（W3-U07；harness
# docs/f04-f92-case-permission-contract.md）：管理四方法走 --caseperm-json
# 封闭信封（独立成面供产品桥分别枚举）。优先级语义按
# f9-permission-precedence.md（T18 已 VERIFIED）账本落点：role→org→user
# 段序末条胜出＋org veto 只压 deny 永不放行＋规则段 deny 短路 veto＋受管
# 案无匹配 fail-closed。四类门（read/write/events/export/manage）不注册
# 独立方法——读/写/事件流/导出在各既有公开面内逐操作同事务验权（不建第
# 二执行通道）；管理动作武装（规则/veto 存在）后须 manage。未配置/未知
# 方法绝不 stub 成功。
HARNESS_CASE_PERMISSION_METHODS = frozenset({
    "harness.case_member_declare", "harness.case_permission_rule",
    "harness.case_permission_veto", "harness.case_permission_read",
})

# F05 协作面完整化（W4-U31；harness docs/f05-collab-surface-contract.md）：
# HARNESS_CASE_PERMISSION_METHODS 同族新组——org 邀请/email 直授 RBAC/
# 分享 token/升级弃权档案十一方法走同一封闭 public_entry provider dispatch
# （--collab-json 信封，独立成面供产品桥分别枚举）。「邀请/直授/撤权按角
# 色落真实权限」＝harness 侧 F04 求值 roster 回落（case_members 案行优先
# 零漂移）；「旧分享token失效且无越权文档」＝成员撤权同事务级联 token
# revoked＋解析按当下活体权限求值。本面零出站通道（无邮件投递）；产品 UI
# 投影挂后续 oc28 patch 工单（F04 同先例）。未配置/未知方法绝不 stub 成功。
HARNESS_COLLAB_METHODS = frozenset({
    "harness.collab_invite_create", "harness.collab_invite_accept",
    "harness.collab_invite_revoke", "harness.collab_grant_direct",
    "harness.collab_member_revoke", "harness.collab_member_read",
    "harness.collab_share_token_issue", "harness.collab_share_token_resolve",
    "harness.collab_share_token_revoke",
    "harness.collab_upgrade_waiver_record",
    "harness.collab_upgrade_waiver_read",
})

# F141 评论权限合同＋F142 审批流（W5-U13；v2；owner=harness+product；
# harness docs/f141-f142-collab-lifecycle-contract.md；schema v37 三账）。
# HARNESS_COLLABDOC_METHODS 五方法走 --collabdoc-json 封闭信封：P04
# save_case_note/start_review_round 既有 v1 语义零改动复用（17 卡
# STATIC_REUSE）＋F141 评论三方法（写路径作者实时过 F04 read 门＝撤权即
# 时生效 F04/F92 先例；评论显式钉 F08 材料链真实 revision——无『最新版』
# 自动跟随；被分享者读路径＝F05 分享 token 承载且 (materialId, revision)
# 逐字绑定——越权对象/越权版本具名拒；投影键闭集无原件字节＝不越权原
# 件）。HARNESS_APPROVAL_METHODS 七方法走 --approval-json：审批轮锚定
# prepare_formal preparation 清单（sha 真实在 CAS）；决定唯一入账通道＝
# 显式 decide（manage 门；免登录审批页只读不扩权——浏览零记账＝采用后
# 实记）；页 token 只存 sha256、permitted_scope 闭集单值 approval_view、
# 撤销立失效。HARNESS_FORMAL_LIFECYCLE_METHODS 两方法走 P02 既有
# --prepare-formal-json/--commit-formal-json 信封（字段闭集合同在
# harness ApplicationService；与 commit_formal 终局面零改动——v1 已有
# 文件终局不得等 v2，审批不门控既有终局路径）。桥只路由不解释——求值
# 真值校验全部在 harness 面。未配置/未知方法绝不 stub 成功。
HARNESS_COLLABDOC_METHODS = frozenset({
    "harness.start_review_round", "harness.save_case_note",
    "harness.collab_doc_comment_save", "harness.collab_doc_comment_read",
    "harness.collab_doc_comment_shared_read",
})

HARNESS_APPROVAL_METHODS = frozenset({
    "harness.formal_approval_open", "harness.formal_approval_page_issue",
    "harness.formal_approval_page_view", "harness.formal_approval_decide",
    "harness.formal_approval_page_revoke", "harness.formal_approval_read",
    "harness.formal_approval_list",
})

HARNESS_FORMAL_LIFECYCLE_METHODS = frozenset({
    "harness.prepare_formal", "harness.commit_formal",
})

# F121 案件时间线 chronology（W4-U52；v1.5；owner=product+harness）：
# 两组四方法面。HARNESS_CHRONOLOGY_METHODS＝harness 事件账五方法走
# --chronology-json 封闭信封（来源 ref＋确认闸＋未知时点 unknown 档表
# 级 CHECK＋修改必带显式失效标记＋object_dependencies 钉定对账）。产
# 品本地面 CHRONOLOGY_METHODS＝chronology.extract（确定性抽取：正则＋
# 状态机，LegalTech 红线 1 严禁模型猜日期；候选不入账——入账唯一通道
# ＝harness.chronology_event_record 落账即 unconfirmed）＋
# chronology.deadline_anchor（D01 期限计算锚守卫：锚日期只能来自
# confirmed 且依赖不 STALE 的事件——事件修改触发依赖失效后下游必须
# 显式重锚；只读联动绝不写程序期限账）。业务事件分类＝纯标签闭集不触
# 发 JC 计算。未配置/未知方法绝不 stub 成功。
HARNESS_CHRONOLOGY_METHODS = frozenset({
    "harness.chronology_event_record", "harness.chronology_event_confirm",
    "harness.chronology_event_read", "harness.chronology_axis",
    "harness.chronology_invalidations_list",
})

CHRONOLOGY_METHODS = frozenset({
    "chronology.extract", "chronology.deadline_anchor",
})

# F08 material store (W2a-U05; harness docs/f08-material-store-contract.md):
# register_material / add_material_revision / read_material / list_materials
# over the same closed public_entry provider dispatch (--materials-json
# envelope). MatterStore is the only business truth source; originals are
# read-only CAS blobs; revisions are append-only copies; cross-matter refs are
# refused. Unknown or unconfigured methods never stub success.
# F114 (W2a-U06; harness docs/f114-version-source-contract.md): the P04 face
# propose_materials / decide_materials / withdraw_material rides the same
# envelope — five true version sources (upload/assistant_edit/user_accept/
# reject/generated, never interchangeable), byte readback per revision, and
# user_accept/reject backed by real decision records with version forking.
HARNESS_MATERIAL_METHODS = frozenset({
    "harness.register_material", "harness.add_material_revision",
    "harness.read_material", "harness.list_materials",
    "harness.propose_materials", "harness.decide_materials",
    "harness.withdraw_material",
})

# F25 生成租约三件套（W2b-U01；harness docs/f25-lease-generation-contract.md）：
# DB 行级租约＋generation_id 写守卫＋claim 后快照——批量审查写守卫底座
# （线1，E14 收口引用其证据）。十方法走同一封闭 public_entry provider
# dispatch（--reviewbatch-json 信封，独立成面供产品桥分别枚举）。迟到结果
# （过期租约/旧 generation）一律具名拒，不覆新结果或人工改格；批量暂停
# 只是停发新租约（resume 显式续跑），状态在 MatterStore（SQLite/PG 同
# 合同）进程重启即续。未配置/未知方法绝不 stub 成功。
HARNESS_BATCH_REVIEW_METHODS = frozenset({
    "harness.review_batch_create", "harness.review_batch_claim",
    "harness.review_batch_submit", "harness.review_batch_human_edit",
    "harness.review_batch_release", "harness.review_batch_pause",
    "harness.review_batch_resume", "harness.review_batch_read",
    "harness.review_batch_claim_log", "harness.review_batch_list",
})

# F47 提案/bake 不变式（W2b-U11；harness docs/f47-proposal-bake-contract.md）：
# canonical 永远干净态＋提案状态机（pending/accepted/rejected/superseded，
# reject＝人说不、superseded＝被取代，分列不混）。四方法走同一封闭
# public_entry provider dispatch（--formalproposal-json 信封，独立成面供
# 产品桥分别枚举）。提案/base/canonical 三分分开（提案行永不落版本链）；
# base 漂移具名拒不猜改；确认（formal_decide accept）才登记新干净版本
# （source=user_accept ∈ F114 闭集；resultBytesB64＝宿主部分接受后重读
# 实际文件回流 CAS 新版本）；拒绝/被取代一字不动 canonical。未配置/
# 未知方法绝不 stub 成功。
HARNESS_FORMAL_PROPOSAL_METHODS = frozenset({
    "harness.formal_propose", "harness.formal_decide",
    "harness.formal_proposal_read", "harness.formal_proposal_list",
})

# E15 路径与新证据公开合同（W2b-U23；harness docs/e15-path-evidence-
# contract.md）：PathCandidate / AssessmentDelta / BranchProjection 三账
# 十方法走同一封闭 public_entry provider dispatch（--pathevidence-json
# 信封，独立成面供产品桥分别枚举）。issue 窄字段闭集不变——路径候选/
# 采用决定/新证据重评/JC 分支投影是独立公开合同；未采用候选永不改正式
# 请求（只有 path_candidate_decide(adopt) 同一事务经窄字段登记 issue）；
# branchRefs 由 JC 公开出口原样转录，空＝该 run 无分支显式标记，不由
# 前端制造；重评无依据不得签变化项（未知不伪支持）。未配置/未知方法
# 绝不 stub 成功。
HARNESS_PATH_EVIDENCE_METHODS = frozenset({
    "harness.path_candidate_register", "harness.path_candidate_decide",
    "harness.path_candidate_read", "harness.path_candidate_list",
    "harness.assessment_delta_record", "harness.assessment_delta_read",
    "harness.assessment_delta_list",
    "harness.branch_projection_record", "harness.branch_projection_read",
    "harness.branch_projection_list",
})

# F82 Tabular 窄版闭环核心（W2b-U05；harness docs/f82-tabular-core-contract.md
# ＋产品面 tabular_review.py）：harness.review_columns_*（列合同：金标入账）
# ＋review_support_*（格支持账：核验戳/失效/投影）五方法，复用 F25
# --reviewbatch-json 信封（review-batch 域同信封扩展，方法组各自冻结枚举）。
# 支持戳只记已过闸结论（核验经 U02 extraction.gate 面）；出处逐条入账且
# provenance 钉页文本 sha256；失效＝追加条目（投影 STALE/INVALIDATED），
# 历史不删。未配置/未知方法绝不 stub 成功。
HARNESS_TABULAR_METHODS = frozenset({
    "harness.review_columns_define", "harness.review_columns_read",
    "harness.review_support_record", "harness.review_support_invalidate",
    "harness.review_support_read",
})

# F82 复核/单格重跑/旧值历史 harness 面（W2b-U31；harness docs/f82-
# review-ops-contract.md）：复核回执账（机器分子不动——E11 先例：回执带
# reviewer＋决定 ref，不代签格值/generation/支持戳）＋复核状态投影＋
# 单格重跑（以行为租约、格为粒度新 generation；迟到/旧 generation/人改
# 后重跑三路具名拒不覆人改）＋旧值历史（沿 F25 版本链）。复用 F25
# --reviewbatch-json 信封（review-batch 域同信封扩展，方法组各自冻结
# 枚举）。人工改格＝既有 HARNESS_BATCH_REVIEW_METHODS 的 human_edit
# （本组不重复注册）。未配置/未知方法绝不 stub 成功。
HARNESS_REVIEW_OPS_METHODS = frozenset({
    "harness.review_receipt_record", "harness.review_receipt_read",
    "harness.review_cell_rerun", "harness.review_cell_history",
})

# E17 取证范围与部分失败（W2b-U25；harness docs/e17-evidence-attempt-
# contract.md）：EvidenceAttempt 账八方法走同一封闭 public_entry provider
# dispatch（--evidenceattempt-json 信封，独立成面供产品桥分别枚举）。
# 覆盖按 distinct 请求项投影（10 请求得 4 含 1 不利＝4/10，不用文件数）；
# 没有实际申请不能记已执行、没有实际收件不能记取得；6 未回应保持未知；
# 真拒绝与超期必带来源；不利材料 adverseMaterialRefs 供场景二重评（E15
# assessment_delta）消费；同 4 项重发/重导不变 8/10、费用幂等不双计；
# 关闭＝律师决定面（允许停止/替代），任务完成与证明缺口分别呈现。
# 未配置/未知方法绝不 stub 成功。
HARNESS_EVIDENCE_ATTEMPT_METHODS = frozenset({
    "harness.evidence_attempt_register", "harness.evidence_attempt_apply",
    "harness.evidence_attempt_receipt", "harness.evidence_attempt_resolve",
    "harness.evidence_attempt_cost", "harness.evidence_attempt_close",
    "harness.evidence_attempt_read", "harness.evidence_attempt_list",
})

# F117 案件内任务/待办（W3-U08；06 F117「待办建议/采用/执行/完成真状态；
# 每任务终局owner与结果绑定」；harness docs/f117-f124-todo-loose-contract.md）：
# tasks.* 五方法走同一封闭 public_entry provider dispatch（--tasks-json 信
# 封，独立成面供产品桥分别枚举）。建议账（suggest/proposal_decide/
# proposal_list）只记建议与决定——采用才落 derived_tasks 既有任务账（不
# 造第二任务账）；tasks.list/tasks.decide（含 F117 新增 start/complete 真
# 状态动作）为同一方法族。完成必带终局 owner（_REF_OWNERS 闭集）与结果
# 绑定（在案 kind 回账验证）；done 终局。未配置/未知方法绝不 stub 成功。
HARNESS_TASK_METHODS = frozenset({
    "tasks.suggest", "tasks.proposal_decide", "tasks.proposal_list",
    "tasks.list", "tasks.decide",
})

# F124 散件文档处理（W3-U08；06 F124「不建案即可处理文档，后归案身份/版
# 本/审阅记录不丢」；同合同文档）：harness.loose_* 六方法走同一封闭
# public_entry provider dispatch（--loosedocs-json 信封，独立成面）。散件
# 三账 matter-less（零案号合法的结构面）；版本字节进同一 CAS；归案
# （loose_file）＝同一事务落 F113 case_anchors 锚点账＋F08 材料链
# revision 1＋散件行冻结（归案前版本/审阅链原样可回读；归案后版本演进
# 唯一走 F08/F114 材料链——不造第二版本源）。未配置/未知方法绝不 stub。
HARNESS_LOOSE_DOC_METHODS = frozenset({
    "harness.loose_register", "harness.loose_add_revision",
    "harness.loose_record_review", "harness.loose_read",
    "harness.loose_list", "harness.loose_file",
})

# E16 款源/转移/退款/分配/余额（W2b-U51；07 E16＋05 §9.5 六公开合同＋
# 08§3 五场景行「款源180k」；harness docs/e16-cash-contract.md）：
# harness.cash_* 六方法走同一封闭 public_entry provider dispatch
# （--cashcontract-json 信封，独立成面供产品桥分别枚举）。结构性分账
# ——债权案件现金绝不借 F08 record_payment 账单通道（billId 语义不存
# 在即具名拒）；现实同源去重＝reality_key UNIQUE（同源款两路来账不得
# 双计）；持有转移必钉既有款源（source_total 恒 180000 不得 230000）；
# 转移/流出/分配行必带 JC 计算回执 ref（owner=jc sha256，本桥只转录
# 不制造）；减免不是实付、改判不是退款；余额投影恒带五列净额向量。
# F125 待裁零字段；VOI 属 E20 零字段。未配置/未知方法绝不 stub 成功。
HARNESS_CASH_METHODS = frozenset({
    "harness.cash_entitlement_register", "harness.cash_source_register",
    "harness.cash_transfer_record", "harness.cash_outflow_record",
    "harness.cash_allocation_record", "harness.cash_balance_read",
})

# E16 款源/余额 JC 确定性计算面（W2b-U51；jc-cash-contract/1）：经 P01
# JCClient（create_local_client 同一钉定公开面）消费 JC cash 面。
# cash.balance＝五列净额向量（source_total/client_gross/outflow/
# client_net/court_held 恒为答案形状，无只回总数形态）＋独立 checker
# 列代数守恒重导不同意不盖章；cash.allocate＝分配算术认证（每款源不
# 超额、生效集=每 id 最高 revision 同一部分永不重复分；规则法源名义由
# 调用方 ruleBasis 具名声明）。金额整分端到端（float/string/bool 入参
# cash_amount_not_minor_units 具名拒）；同源去重结构性（同 realityKey
# 两路来账 cash_source_reality_duplicate 拒）；超额只上报绝不自动造退
# 款；法律效果分离（declared|pending_review 原样携带不推导）。config
# 复用 P01 同域键 jc_state_root/jc_import_path/jc_rule_roots；JC 侧
# typed 拒绝以 JC_FAILURE 携码（exit 4）回传。
CASH_CONTRACT_METHODS = frozenset({
    "cash.balance", "cash.allocate",
})

# F82 Tabular 产品面（W2b-U05）：tabular.read（列三元组投影：列名/金标/
# 值＋支持状态＋goldMatch 确定性对照）/ tabular.support_stamp（E14 接线点：
# U02 闸跑结论转录进 harness 格支持账——UNVERIFIED 拒盖章）/ tabular.invalidate
# （失效登记薄透传，理由闭集权威在 harness）/ tabular.audit（溯源：材料侧
# 页文本 sha＋引用在页内，法规侧同面复验一致）。编排与投影，零第二核验器
# 零第二材料真源；命题恒不代签。
TABULAR_METHODS = frozenset({
    "tabular.read", "tabular.support_stamp", "tabular.invalidate",
    "tabular.audit",
})

# F82 三面产品方法组（W2b-U31；产品面 tabular_review_ops.py）：
# tabular.review_receipt（复核回执登记薄透传：reviewer＋决定 ref）/
# tabular.review_status（复核状态投影只读）/ tabular.cell_rerun（单格重跑
# 编排 claim→rerun→release——行租约为授权、格为粒度新 generation，三路
# 具名拒不覆人改；人改格必经写权限方法不建第二写通道＝F84 红线）/
# tabular.cell_history（旧值历史回读＝失效回读值侧）。编排与透传，零第二
# 账本；人工改格走既有 harness.review_batch_human_edit（F25 组）。
TABULAR_REVIEW_OPS_METHODS = frozenset({
    "tabular.review_receipt", "tabular.review_status",
    "tabular.cell_rerun", "tabular.cell_history",
})

# F84 review 内嵌聊天产品方法组（W2b-U48；产品面 review_chat.py）：
# review_chat.ask（只读提问）——聊天上下文＝tabular.read×review_status
# 合并投影＋支持戳引用（只含当前可见真实格值＋引用＋复核状态，绝不携带
# 原件/身份映射）；模型轮次走产品服务 DeepSeek BYOK（裁决③），模型不可
# 用具名不伪输出；聊天侧零写通道（改格必经写权限方法＝F84 红线即面即守
# ，人工改格仍走 F25 review_batch_human_edit＋F92 行级权限面）。
REVIEW_CHAT_METHODS = frozenset({
    "review_chat.ask",
})

# #43 订阅型推理引擎产品方法组（RE-43；产品面 subscription_engine.py）：
# subscription.*（SIWC OAuth 登录/刷新/撤销/模型列表/对话轮/回落 API Key/
# Codex 交接）——令牌只进 credential_vault DPAPI 密文，index 零令牌字节；
# Claude 订阅族整族划出（2026-10-30 用户裁决，非 OAuth 交接）。
SUBSCRIPTION_METHODS = frozenset({
    "subscription.status",
    "subscription.login_begin",
    "subscription.login_callback",
    "subscription.refresh",
    "subscription.logout",
    "subscription.models",
    "subscription.chat",
    "subscription.codex_handover",
})

# F83 合同列预设产品方法组（W3-U15；06:F83 双实例，17 卡 owner=product；
# 产品面 column_presets.py）：column_preset.read（冻结预设只读——字段层
# {id,name,gold} 与 format 层 {id,format} 严格分离，字段定义携 format 键
# 即具名拒；12 列每列必有金标）/ column_preset.apply（冻结预设申报进既
# 有批——join 只发生在申报边界，列集合冻结/异内容冲突判定唯一在
# harness review_columns_define，columns_not_frozen/review_columns_conflict
# 具名拒原样上浮，本面不建第二列权威）/ column_preset.values（填充投影：
# 缺值/多值/未知恒 value=None＋具名 fill，绝不编造占位值；number 金标列
# 单提及不可 Decimal 解析＝未知不落格——金额纪律）。零自有持久化。
COLUMN_PRESET_METHODS = frozenset({
    "column_preset.read", "column_preset.apply", "column_preset.values",
})

# F85 结果导出 Excel 产品方法组（W3-U15；06:F85 双实例，依赖 F82/F87；
# 产品面 excel_export.py）：export.xlsx（tabular.read×
# harness.review_support_read 同源投影→确定性 XLSX）——真实格值（内部
# 引文标记 ⟦引:…⟧ 剥除后，剥除只删标记跨度）与可审引用列一致：引用列
# 只来自该格支持戳（F87 闸三态＋F70 状态＋doc/page/sha256 出处）与未入
# 戳被剥标记（UNVERIFIED 具名，出处具名缺席）——绝不伪已核不编出处；
# 缺值＝空格不伪填；标记壳残留具名拒；float 值具名拒（金额纪律）；纯
# 标准库最小 OOXML＋zip 项时间戳钉定＝同输入两跑同字节；字节 base64
# 回传零自有持久化。
EXCEL_EXPORT_METHODS = frozenset({
    "export.xlsx",
})

# F64(v1) local-first source strategy + F69 statute validity (W2a-U13):
# statute.source_strategy / statute.resolve / statute.citation_gate over the
# E22-frozen lccc_consumer public face only (config codices_import_path +
# codices_formal_root). v1 executes the local segment alone; the paid/web
# segments are named declared gaps (measured in F64-v1.5/B4) — no silent
# escalation, no self-collection, no URL fabrication. Missing date/code or
# any face conflict fails closed (UNKNOWN, never signs current); abolished/
# superseded statutes retrieved are still not citable.
# W4-U41 adds statute.web_declaration (F64 v1.5 acceptance, web fallback):
# a declaration-only face turning caller-supplied web evidence facts into a
# web_verified ledger entry — zero network, no fetch, verification basis
# separate from the database verifications (web-verified never impersonates
# a database verification signature).
STATUTE_METHODS = frozenset({
    "statute.source_strategy", "statute.resolve", "statute.citation_gate",
    "statute.web_declaration",
})

# F74 web search fallback (W4-U44; 06 row F74, v1.5, owner=product+codices):
# web.fallback_retrieve — the tail segment of the frozen F64 degradation
# chain (local→paid→web), opened only with named gap proofs from both prior
# segments (chain.local_gap/chain.paid_gap). The request surface runs the
# permission-model whitelist gate FIRST (scheme + domain whitelist, typed
# rejection outside — T05 lesson: CodeMode web fetch had no gate); result
# URLs are transcribed verbatim from the search response (zero URL
# fabrication at AST level); every verified record fetches the original
# bytes and binds their sha256 (URL-only ledger records cannot exist), and
# the quote must match the retrieved text verbatim. The web_verified
# declaration comes ONLY from the W4-U41 statute_validity.declare_web_verified
# face (same ledger semantics as statute.web_declaration — web-verified
# never impersonates a database verification). No network / unauthorized /
# non-200 / quote mismatch → named gaps, never fabricated results
# (ruling #8-12 same family).
WEB_FALLBACK_METHODS = frozenset({
    "web.fallback_retrieve",
})

# F70 citation verifier (W2a-U14): citation.parse / citation.verify /
# citation.verify_document. Deterministic citation parsing (regex + state
# machine, workspace constraint 1 — no model guessing); version/effect/
# timepoint go through the W2a-U13 statute_validity face (statute.* above,
# same frozen lccc_consumer); title→WJBS via the face v1.1 find_by_title
# and quote localization via read_markdown_text on the real carrier. Every
# citation is accounted per-item with its own status; fabricated/expired/
# mis-cited citations never verify, and no document-level PASS verdict is
# produced (06 row F70 acceptance).
CITATION_METHODS = frozenset({
    "citation.parse", "citation.verify", "citation.verify_document",
})

# F87 引文核验接抽取路径强制闸（W2b-U02）：extraction.register / gate /
# candidates / candidate。闸而非第二核验器——版本/效力/时点/取文/引文
# 支持全复用上面 W2a-U14 已 VERIFIED 的 citation.*（其法源消费经 E22
# 冻结面 v1.1）；本组只做抽取候选（格候选）的闸政策映射与记账。
# 候选入册即具名 UNVERIFIED；登记面拒绝一切闸状态字段（无伪造旁路）；
# gate_status 只能经 extraction.gate 转移，且闸跑前置复验法源面
# sha256 钉定（config.codices_face_sha256，漂移即响亮失败）。quote
# 存在不等于命题支持：proposition_support 恒不代签；伪引文/旧版本/
# 误引/虚构/未知候选一律 REJECTED 理由具名（06 行 F87 acceptance）。
EXTRACTION_GATE_METHODS = frozenset({
    "extraction.register", "extraction.gate",
    "extraction.candidates", "extraction.candidate",
})

# F88 可答/应拒双集合评估＋六指标 CI 门（W2b-U03）: f88.evaluate /
# f88.control_evaluate. Evaluation-only surface — consumes the SAME F70
# citation verification core (citation_verifier.citation_call) through the
# frozen method path, never a second verification authority. Six metrics
# adapted from the judicex gold_runner threshold table (blueprint L13) with
# thresholds preserved; dual-set rates (answerable coverage + should-refuse
# rejection) share reported denominators; always-refuse and answer-everything
# controls must both FAIL the gate; hallucination is scored against golden
# labels only, never against verifier self-reported statistics (06 row F88).
F88_METHODS = frozenset({
    "f88.evaluate", "f88.control_evaluate",
})

# F91 abstain 反修复＋operational 模式（W4-U46；06 行 F91，v1.5，owner=
# product+harness）：abstain.record/read/list＝拒答具名入账（防 fail-closed
# 被当『动不动拒绝用』：有账可查有因可读；08§4 未知关键输入仍阻断正式
# 结论——拒答面不松动）；abstain.repair_submit＝误拒纠正（覆盖充分性判
# 定绑定可具名证据——纠正候选引用逐条经 W2a-U14 citation 面确定性核验，
# 不模型自评；重过闸=结构断言：纠正产物走同一 extraction.register→
# extraction.gate 路径真调 F70，未过闸永不交付）；operational.deliver＝
# 操作性任务照常交付（不经法律闸，产物恒带『非法律结论』边界标记，携
# 带法律结论字段具名拒）。状态根 config.abstain_state_root；闸面复用
# extraction_gate_state_root/codices_*（F87 同钉定纪律）。
ABSTAIN_OPERATIONAL_METHODS = frozenset({
    "abstain.record", "abstain.read", "abstain.list",
    "abstain.repair_submit", "operational.deliver",
})

# F91 harness 账本半边桥（W4-U46；legal-harness 战役分支 abstain_events
# 账 v32）：harness.abstain_event_record/read/list 经 public_entry
# --abstain-json 信封。账本级结构断言：repair_gate_* 事件必带产品 F87
# 闸凭据（gateRef 封闭四字段）——没有重过闸凭据的纠正确认不能入账；
# operational_delivered 必带 boundaryMark=NON_LEGAL_CONCLUSION。
HARNESS_ABSTAIN_METHODS = frozenset({
    "harness.abstain_event_record", "harness.abstain_read",
    "harness.abstain_list",
})

# E12 全量材料解析（W2a-U02）：anonymizer material_parse_service 同进程公开面。
# 登记只取语料身份字段（金标结构性不读）；信号闭集分别计数（失败/空识别/
# 未读/低置信，不凭文件存在已读）；跨页表阅读序组装；页号 bbox 版本链
# （engine/human，重抽不删版本）；人改不覆（重扫永不覆盖 human 版本）；
# 局部恢复（每页原子提交，process 重入不重不漏）。state 根经
# config.material_parse_state_root；语料只读（页字节 sha 不符=拒解析）。
MATERIAL_PARSE_METHODS = frozenset({
    "material.parse_register", "material.parse_process",
    "material.parse_pending", "material.parse_report",
    "material.parse_page", "material.parse_human_edit",
    "material.parse_reparse", "material.parse_tables",
})

# F40 OCR 级联四端口（W2a-U03；06:F40 PaddleOCR 基础线＋MinerU/Paddle-VL/
# PP-OCRv6/MiniCPM-V 预留）：anonymizer ocr_ports_service 同进程公开面。
# 每端口 capability 具名报告，未安装如实标注（探针实测；PROBE_FAILED 与
# NOT_INSTALLED 严格区分，不装样子）；基础线经钉定解释器 worker 子进程真跑
# （GPU fail-closed 无 CPU 回退、模型缓存缺失绝不运行时下载）出真实页块/
# 表格（跨页阅读序与行列对应复用 E12 组装）。state 根经
# config.ocr_ports_state_root；解释器经 config.ocr_baseline_interpreter；
# 语料只读（页字节 sha 不符=拒跑）。
OCR_PORTS_METHODS = frozenset({
    "ocr.ports", "ocr.baseline_register", "ocr.baseline_run",
    "ocr.baseline_pending", "ocr.baseline_report", "ocr.baseline_tables",
    "ocr.baseline_page",
})

# F41 OCR 批量工程（W2a-U16；06:F41 串行限流/进度事件/单文档重抽/过期报告
# 签名）：anonymizer ocr_batch_service 同进程公开面（批量编排单一权威；
# 引擎权威仍=F40 worker 钉定解释器子进程，GPU fail-closed·模型 sha256
# 钉定·绝不运行时下载）。并发=1 纪律＋文档间显式限流窗；进度事件单调
# 落盘可回读；取消留已完成件＋pending 可续；单文档重抽出新版本不删旧版本
# 不重写原件；过期报告签名验签仍过（密钥只存 state 不进产物）。state 根
# 与解释器复用 F40 同域配置键（ocr_ports_state_root/ocr_baseline_interpreter）。
OCR_BATCH_METHODS = frozenset({
    "ocr.batch_register", "ocr.batch_run", "ocr.batch_cancel",
    "ocr.batch_status", "ocr.batch_events", "ocr.batch_pending",
    "ocr.batch_redraw", "ocr.batch_report", "ocr.batch_verify_reports",
    "ocr.batch_doc_version", "ocr.batch_secret_exposure",
})

# F42 印章/PS 疑似视觉检测（W4-U35；06:F42 v1.5「疑似印章/视觉异常可回原图
# 且标检测局限；不签真伪鉴定」，依赖视觉模型随 F40 级联入）：anonymizer
# stamp_visual_service 同进程公开面（W4-U21 交付）。检测＝worker 子进程跑在
# F40 同款钉定解释器内（GPU fail-closed 无 CPU 回退·模型缓存 sha256 钉定·
# 绝不运行时下载，W2a-U03/W2a-U16 先例）；疑似区域（bbox/conf/几何色度量/
# 区域内文字线索）＋检测局限声明随每页记录落盘；原图回读＝只读原件映射
# （现场复验原件字节 sha256，不符=typed 拒读；原件字节绝不复制绝不出域，
# E12/F40 红线）；不签真伪＝结论词闭集 {suspected, not_detected}（结构性
# 闭集；conclusion_scan 对全部产物做禁形结构断言，命中即拒交）；低置信/
# 失败不假成功（E11 语义：错误页 verdict=None 记错误码入分母，不进完成
# 分子）。state 根与解释器复用 F40/F41 同域配置键（ocr_ports_state_root/
# ocr_baseline_interpreter）。
STAMP_METHODS = frozenset({
    "stamp.register", "stamp.run", "stamp.pending", "stamp.report",
    "stamp.page", "stamp.original", "stamp.limitation",
    "stamp.conclusion_scan",
})

# F86 前后端阅读序同源（W2a-U07；06:F86 python_entry_binding＝原生
# OpenCode UI/host）：reading_order 规范面——从 E12 解析产物
# （material.parse_* 同一来源）组装唯一规范阅读序文档；前端阅读面（patch
# 013 桌面 seam）与后端解析序都消费本文档，不复制第二推导。高亮三类
# page_segment/table/ocr（引用命中属 E14 接线/W2b）。命中解析不到=typed
# error 响亮失败（引文高亮静默失败预防针），批次未处理完拒出文档。
READING_ORDER_METHODS = frozenset({
    "reading.document", "reading.hits",
})

# E11/F37 脱敏资格闸与人审覆盖（W2a-U09）：anonymizer review_gate_service
# 同进程公开面。资格闸＝机器事实（manifest qualified＋运行时实测），与人审
# 回执互不代言；分子分母：分母只认调用方金标、分子只认识别栈真实检出，
# ratio=None＝未测（不造 0），检出未对上金标单列 detection_only；人审
# 覆盖分母独立于自动性能分母；三类永不回填（id_card/phone/
# personal_address）在 owner 强制。终字节复扫与假名只在 owner——本桥只回
# 聚合结果，绝不回 surface/映射/原件路径（material.deidentify 同红线）。
# matter 级方法 state 根经 config.review_gate_state_root。
REVIEW_GATE_METHODS = frozenset({
    "review.qualification", "review.rule_classes",
    "review.class_coverage", "review.human_coverage",
    "review.never_backfill",
})

# F38 附件文件闸＋F44 脱敏硬红线（W2a-U15）：anonymizer
# attachment_gate_service 同进程公开面。闸链＝OCR（F40 基础线证据）→资格
# （E11 面）→签名人审范围决定→像素烧入（raster_redactor）→最终字节复扫
# （结构面＋OCR 面）→裁决绑定最终附件 sha256（字节变即裁决失效）→授权/
# 拒发。未通过一律不能外发：拒绝理由具名（低置信/失败不中断为假成功）。
# 三重 fail-closed：anonymizer_contract＋attachment_gate_state_root（gate/
# authorize）或路径参数（scan）＋typed error 只带类型/码不带材料。响应只回
# 计数/哈希/状态，surface/原件路径/身份映射绝不回传（06:F38 acceptance
# 「OCR人审烧入复扫绑定最终附件字节；未通过一律不能外发」；F44
# acceptance「黑框/隐藏文本/元数据/图片残留反例全部复扫拒发」）。
ATTACHMENT_GATE_METHODS = frozenset({
    "attachment.scan", "attachment.gate", "attachment.authorize",
})

# F43 脱敏策略预设三套（W4-U36；06:F43 owner=anonymizer B4，python_entries
# P09,P10；v1 先做内部分析单策略+假名映射——preserved）：对外发送（最严）/
# 内部分析/公开发布三预设一一绑定三个出域 scope。落 W2a-U15 既有公开面扩展
# 不建第二权威：脱敏本体＝既有 attachment_gate_service 闸链（gate/authorize
# 各加 opt-in 参数，缺省 v1 字节不变）与 mapping.Vault 假名权威（每案共享
# 假名库：一案一图跨策略一致，分案结构性隔离不串案）。authorize_egress 在
# W2a-U15 字节绑定（裁决绑定烧入 sha256，字节变即裁决失效）全部通过后追加
# 策略裁决：未绑策略旧裁决不自动沿用 / scope 不符拒 / 策略指纹变更拒——
# 策略变更＝旧授权失效重审的结构保证（重审＝按当前策略重走闸门，人审在新
# 策略下重签）。响应只回 token/计数/哈希/状态/拒绝理由，surface/映射表/
# 原件路径绝不回传。
REDACTION_PRESET_METHODS = frozenset({
    "redaction.presets",             # 注册表＋各 scope 活动配置指纹（只读）
    "redaction.deidentify_matter",   # P10 pipeline＋每案共享假名库
    "redaction.pseudonym_resolve",   # 裸解析（token-only，零 surface 回显）
    "redaction.rehydrate_matter",    # 本案反向还原（跨案结构性不可达）
})

# F61 微信生态采集按 ID 分批收口（W3-U13；06 行 F61，python_entries
# P09,P10）：wechat_collection 批次编排与出处账面——授权账（显式登记
# 才可采）→批次采集（text 件经 material.deidentify＝P10 既有 pipeline；
# pdf 附件件经 attachment.gate＝F38/F44 既有闸，不复制第二权威）→出处
# 保存（导出件/采集产物双 sha256 绑定＋闸裁决引用）→投影回读。负测
# 先行（裁决#6 微信批次合成先行＋裁决#8-12 禁编 URL）：字段闭集外
# （url/cookie 等采集旁路字段）typed 具名拒；未授权 ID＝
# UNKNOWN_NOT_AUTHORIZED 且出处/采集/闸三值恒 None（UNKNOWN 不是 0）；
# 幂等回流＝同批次同输入重放同回执、异输入具名 conflict。state 根经
# config.collection_state_root；条目投影只带计数/哈希/状态，原文/映射/
# surface/原件路径绝不回传。
WECHAT_COLLECTION_METHODS = frozenset({
    "collection.authorize", "collection.batch", "collection.batch_read",
})

# F63 快递查询/EMS 取证（W4-U40 负测先行；06 行 F63 owner=product）：
# ems.action_authorize / ems.evidence_query / ems.evidence_read——授权账
# （E24 形态：律师显式授权外部动作，append-only 幂等重放，scope 闭集
# ems_official_api_query 类别名零 URL）→ token 在位性（缺→具名缺口
# PAID_TOKEN_NOT_CONFIGURED 不自采，W2a-U13 先例同码）→ 查询封存（轨迹/
# 凭证只从真实回执转录：凭证绑定取证时间＋来源水印 provider＋回执
# sha256；失败不编轨迹——transport 异常/回执残缺值恒 None）。裁决
# #8-12 禁编 URL：本波产品桥无 EMS 适配器可注入（端点未定），已授权＋
# token 在位也只会得到 ADAPTER_ABSENT 具名缺口——未授权/未接线态真实
# 调用路径结构性不可达（客户端未建不可能自采）。费用只收整型分（E21
# 消费面纪律）；E17 语义＝有凭据（真实回执）才记取得。state 根经
# config.ems_evidence_state_root。
EMS_EVIDENCE_METHODS = frozenset({
    "ems.action_authorize", "ems.evidence_query", "ems.evidence_read",
})

# F144 企业查询/对手背景调查（W4-U40 负测先行；06 行 F144 owner=product；
# 2026-10-13 用户拍板：走 MCP 连接器接入企查查/天眼查，不自采数据，
# WorkBuddy 连接器市场实证该形态；13 件套全量 v2=F144-v2 归 W5 不前造）：
# enterprise.connector_status / enterprise.diligence_query /
# enterprise.diligence_read——提供商闭集类别名 qcc_mcp/tyc_mcp（零 URL，
# 连接器形态端点由用户 MCP 配置提供）；缺 Token→具名缺口
# PAID_TOKEN_NOT_CONFIGURED 不自采不编数据（值恒 None 非 {}）；会话工厂
# 未接线→CONNECTOR_SESSION_ABSENT（客户端未建不可能自采）；回执转录
# 绑定 出处（provider 闭集）/时间（retrieved_at）/额度（quota_remaining，
# 05:149 来源时点额度可见）＋载荷 sha256 水印。裁决#8-12 禁编 URL/
# 失败不造假同上。state 根经 config.enterprise_connector_state_root。
ENTERPRISE_CONNECTOR_METHODS = frozenset({
    "enterprise.connector_status", "enterprise.diligence_query",
    "enterprise.diligence_read",
})
# F80 自有商业账户/积分/签到/邀请（W5-U02 合成先行；06 行 V7-80
# owner=product B5，prereq E04/E07/E25 全 VERIFIED；裁决#13-19 商业服务
# 端合成先行）：commercial.account_open / credit_grant / checkin /
# invite_issue / invite_redeem / revoke / balance_read——真实幂等回执、
# 撤销和余额（append-only 台账＋整型分纪律＋幂等键＝输入 digest）。
# 红线：只在独立商业服务面（独立状态根 commercial_state_root＋独立
# 冻结组），案件工作台零运营位（本组不被任何案件/业务模块挂载，字段
# 闭集拒 case/matter 类字段）；不继承上游厂商账号营销（无
# referral/促销/追踪字段处置位）；不前移 v1（只此六类商业操作，与既有
# 全部方法组零交集＝不冒已有业务入口，06 binding
# UI_HOST_OR_NEW_PRODUCT）。F81 策略真实应用链：org_policy_state_root
# 配置时，credit_grant/checkin 经桥注入 org_policy_admin 求值投影
# ——声明即时改变运行面行为。
COMMERCIAL_METHODS = frozenset({
    "commercial.account_open", "commercial.credit_grant",
    "commercial.checkin", "commercial.invite_issue",
    "commercial.invite_redeem", "commercial.revoke",
    "commercial.balance_read",
})
# F81 企业组策略/深度管理台（W5-U02 合成先行；06 行 V7-81 owner=product
# B5，prereq E04/E07/E25 全 VERIFIED）：orgadmin.policy_declare /
# policy_read / policy_apply——append-only 策略账＋F9 语义求值（段序
# org→user，同段声明序 findLast 末条胜出＝user 段压过 org 段）＋应用
# 回执；真实应用＝桥把求值投影注入 commercial.*（F80 运行面行为真实
# 改变，recon/test 端到端断言）。红线：深管理不替代最小 v1 管理台——
# 键闭集全部 commercial.*（v2 商业面）；案件/材料/harness 等 v1 管理
# 面（F04 案件权限规则/veto 账、F05 协作面）无处置位，键闭集外具名拒
# （case.* 探测负测）；state 根经 config.org_policy_state_root。
ORG_ADMIN_METHODS = frozenset({
    "orgadmin.policy_declare", "orgadmin.policy_read",
    "orgadmin.policy_apply",
})

# F144-v2 企业尽调技能包 13 件全量（W5-U15 合成施工；06 source_stage 拍板
# 文「13 件套全量 v2」＝t26 拆分子实例 F144-v2/B5；13 件清单唯一权威＝
# zhiexa-skill-market.md §1「启信宝 13 件套」，03-功能分母 F144 引）：
# dossier13.pack_read / dossier13.run_dossier / dossier13.dossier_read——
# 件目录 13/13 全量闭集（中文名逐字照抄权威清单）＋件执行（唯一数据通道
# ＝enterprise_connector.diligence_query，W4-U40 冻结面；凭证/seal 逐字
# 承连接器产物零第二权威；W4-U40 九条负测纪律全继承：闭集零 URL／缺
# token PAID_TOKEN_NOT_CONFIGURED 不自采不编数据／SESSION_ABSENT 结构性
# 不可达／失败三路 data-credential 恒 None／旁路字段具名拒＋恰一查询键／
# 幂等回流）。state 根经 config.dossier13_state_root。
DOSSIER13_METHODS = frozenset({
    "dossier13.pack_read", "dossier13.run_dossier",
    "dossier13.dossier_read",
})
# F72 人民法院案例库官方分层接入（W4-U42；06:F72 owner=codices+cases+product
# B4，17 卡 entries P08/P11；裁决#8-12 负测先行）：caselib.register＝licensed
# 语料承载登记（语料许可门在 cases 侧强制，产品面只转录不放宽）；
# caselib.search＝必走 case.search 公开面（F68 顺序宪法＋回执审计在桥强制，
# 调用方不可退订），对 caseLibrary additive 块做 E19 同频戳审计（相关度非
# 概率/命题不代签/分是十进制文本；probability 形字段具名拒），产品投影盖
# scoreSemantics 常量戳（retrievalScoreIsNotWinRate 族）；caselib.tier＝
# 指导性/入库/普通裁判三分层逐条回读（官方 tier 闭集 guiding_case/
# included_case；普通裁判=具名来源分类维度绝不写入官方 tier；web 页面声明
# 只能作 provenance 备注——不因官方网页就签分层；无来源=unknown 具名）。
# 裁决#8-12：本构建未获案例库 API 授权——配置域零端点/零 URL 键（W4-U03
# N2「授权形态 NOT_IMPLEMENTED_PENDING_W4 零预造端点」同口径），未授权=
# 梯子 skipped/not_authorized＋caseLibrary 块缺席（绝不补造），live
# transport 具名缺席（授权后补联测，回收点具名）。config 键 cases_root＋
# cases_import_path（钉定 cases 检出）＋caselib_dataset_version（search/tier
# 必配 pin，冲突具名拒）；缺配置＝NOT_CONNECTED（exit 3），typed 错误只携
# caselib_* 错误码不携材料内容。
COURT_CASE_LIBRARY_METHODS = frozenset({
    "caselib.register", "caselib.search", "caselib.tier",
})

# F89 数字三分类豁免（W2b-U04；06:F89 jc+product，python_entries P01）：
# number.classify＝确定性三分类（number_classifier 正则＋状态机，零模型
# 参与——不把 LLM 分类叫确定性）；number.verify_amount＝事实金额值经
# JC 公开求值（P01 冻结面 jc.evaluate → jc-harness-local/1 business
# task，JC 侧 Fraction 精确＝产品侧 Decimal 全程无浮点），错误算式反例
# ＝MISMATCH 具名拒绝；歧义必须待核（UNKNOWN 不伪填不猜）；保原三分类
# 豁免结构（fact_amount→jc_amount_evaluation / rule_number→rule_borne /
# negative_semantics→polarity_bounded / unknown→pending_review）。
# classify 纯函数无配置；verify_amount 需 jc_* 配置（同 jc.evaluate）。
NUMBER_METHODS = frozenset({
    "number.classify", "number.verify_amount",
})

# F54 PDF→docx 转换候选与保真检查（W2b-U17；06:F54「LibreOffice 优先」＋
# §6.1 裁决#5 LibreOffice 已装）：产品侧 pdf_conversion 公开面（document-
# adapter）。保存原PDF和转换候选双留存（original.pdf sha256 钉定不覆盖＋
# candidates append-only）；纯文本重建明确损失（闭集标注）；实际版面/表/
# 页眉脚对照五维实测（auto_fidelity_claimed 恒 false，未保真标 loss）；
# LibreOffice 优先＝唯一自动转换器（soffice --headless --infilter=
# writer_pdf_import --convert-to docx:MS Word 2007 XML，确定性 CLI 非模型，
# 未安装/失败 fail-closed 绝不静默换引擎）。转换候选清单即 W2b-U14 红线
# 管线消费契约（redline 块 editable_text/route）。配置键
# conversion_state_root＋libreoffice_soffice；错误码不携材料内容。
CONVERSION_METHODS = frozenset({
    "conversion.engine", "conversion.convert", "conversion.rebuild",
    "conversion.report", "conversion.list", "conversion.candidate",
})

# F18 纸张 CSS 文书观感（W3-U21；06:F18「纸张 CSS 文书观感（衬线+页边距+
# 微阴影）」＋验收行「纸张预览与真实DOCX/PDF分页分别核；缩放阅读不遮正文」
# ＋08§3 文书行「CSS预览/文件存在/HTML.doc 不等正式DOCX」）：产品侧
# paper_preview 公开面（document-adapter 家族）。两方法分别承载互不代言：
# paper.document＝预览内容面（确定性抽取，回执零分页字段——CSS 预览结构性
# 不携带分页主张）；paper.pagination_reference＝真实分页唯一参照面
# （LibreOffice headless --convert-to pdf 渲染 DOCX→PDF，页数/逐页文本自
# PDF 实测 pdfium——非 DOCX 数学推导非 CSS 近似；soffice.com 阻塞二进制
# 沿用 F54 实测钉定，UserInstallation 隔离于状态根绝不写 %APPDATA%）。
# 配置键 paper_state_root＋libreoffice_soffice（F54 共用）；错误码 f18_*
# 不携材料内容。
PAPER_METHODS = frozenset({
    "paper.document", "paper.pagination_reference",
})

# F49 干净基版与提案 replay 对比产真修订红线（W2b-U14；06:F49
# 「compareDocuments 差量，非会话内打标」＋17 卡「干净基版与提案replay
# 对比产真修订；表格/脚注/编号有内容回读」）：产品侧 document_redline
# 公开面（document-adapter）。提案 replay 与渲染解耦（封闭算子集确定性
# 重放成独立在盘工件）→ 对盘上两份真实文件做 compareDocuments 差量产
# 真 OOXML 修订标记（w:ins/w:del/delText/段标记/trPr/w:pPrChange）；
# 对账双不变式（accept_all==replay、reject_all==baseline 四类事实）不过
# 不出红线；修订清单自产物红线 DOCX 回读（内容回读）。干净基版闸：既有
# 修订标记/文本框图形域等模型外构件具名拒不静默丢。产物红线 DOCX 供
# W2b-U16 WPS 宿主验证与 E13 收口消费（b64 取件）。配置键
# redline_state_root；错误码不携材料内容。
REDLINE_METHODS = frozenset({
    "redline.register", "redline.replay", "redline.compare",
    "redline.report", "redline.list", "redline.redline",
})

# F55 独立文档对比（W4-U37；06:F55「两份实际文件本地对比与变更清单对应，
# PDF/DOCX范围有明确支持」＋17 卡 target=新产品 document-adapter，entries
# P02,P04）：产品侧 document_compare 公开面（document-adapter 家族）。
# 两实际文件确定性差量（F49 compareDocuments 差量纪律复用——_align 纯函数
# 复用，不模型猜测）；变更清单逐项对应＝硬门（双射/覆盖/双侧文本三不变
# 式不过不出清单）；支持矩阵显式声明（docx_docx / pdf_pdf 闭集，跨类与其
# 他格式 f55_mode_unsupported 具名拒）；DOCX 分段模型外（编号/修订标记/
# 样式/页眉脚/域）显式声明，零可见差量而模型外有差＝具名拒不假「无变化」；
# 双留存 sha256 钉定＋append-only；payload_digest 跨 profile 确定性。
# 宿主原生双栏/三窗格 UI 不在本面（本面交付窗格行投影数据）。配置键
# doccompare_state_root；错误码 f55_* 不携材料内容。
DOCCOMPARE_METHODS = frozenset({
    "doccompare.compare", "doccompare.report", "doccompare.list",
})

# F58 红线/对比产物导出 PDF（W4-U37；06:F58「真实红线/对比PDF可阅读打印
# 并保变更范围；失败不交空PDF」＋17 卡 target=新产品 document-adapter，
# entries P02,P04；随 F55 立项同单）：产品侧 document_export 公开面
# （document-adapter 家族）。LibreOffice headless 真渲染（--convert-to
# pdf；soffice.com 阻塞二进制＋Writer 原生打开两坑沿 W2b-U17/W3-U21 实测
# 钉定；UserInstallation 隔离于状态根不写 %APPDATA%）；红线源经 U14 已
# VERIFIED redline.redline b64 面取件（不复制第二真源）、对比源经 F55
# doccompare.report；保变更范围＝硬门（PDF 文本层实测逐变更项双侧核对，
# 编号类无文本侧如实 not_text_verifiable 不入分母）；可阅读打印硬门
# （页数≥1＋文本行≥1）；失败/空页/零字节＝typed 拒且清除半成品（失败不
# 交空 PDF）。配置键 docexport_state_root＋libreoffice_soffice（F54 共用）
# ＋redline_state_root/doccompare_state_root（源面同域）；错误码 f58_*
# 不携材料内容。
DOC_EXPORT_METHODS = frozenset({
    "docexport.pdf", "docexport.report", "docexport.list",
})

# F143 法律写作校对插件（一致性/术语，定位原文可接受拒绝）（W5-U14；
# 06:V7-143＋17 卡 owner=document-adapter+product，entries P02,P04）：产品
# 侧 document_proofing 公开面（document-adapter 家族）。验收向量逐字：
# 「一致性/术语校对定位原文且可接受拒绝；不同语义不自动合并」。定位沿
# F50/F51 引用原文重锚定纪律（W2b-U13）：quote＝所在段全文逐字重搜，禁
# 偏移换算（trace span 只是溯源事实，应用时一律现场重搜）、不就近匹配
# （模糊匹配代码结构性缺席）；多命中＝needs_review 零位置字段留人。
# 合并红线：仅限逐条确定性同语义判定（rule/match/suggestion 全同且逐条
# 唯一定位才并入同候选）；不同规则重叠 span 建议不同＝conflict 候选各自
# 独立呈现，同受时 propose 具名拒不代选（语义冲突必须留人）。术语表/
# 一致性规则＝合成冻结清单（RULESET_SHA256 钉定）。候选→人审决定账
# （append-only，可接受拒绝）→F49 封闭算子集确定性重放出真实更正
# DOCX（不模拟 DOCX，非文本部件逐字节保真）；Harness 正式采用走 F47
# 既有 formal_propose/formal_decide 面（本面零复制第二账本）。配置键
# proofing_state_root；错误码 f143_* 不携材料内容。
PROOFING_METHODS = frozenset({
    "proofing.register", "proofing.ruleset_read", "proofing.scan",
    "proofing.candidates", "proofing.decide", "proofing.propose",
    "proofing.proposal_read", "proofing.read_document", "proofing.list",
})

# F48 <edits> 流式协议＋卡片状态机＋DB/书签双持久化（W2b-U12；06:F48
# P02,P04「document-adapter 新模块，纯 Python DOCX 处理」）：产品侧
# edits_protocol 公开面（document-adapter，F54 conversion.* 同族）。流式
# edit 唯一 quote 定位（零/多命中具名拒不猜改）；insert/删除真修订
# （OOXML w:ins/w:del——replace 恒落两个独立修订元素＝office-js#5188 规避，
# 删除侧文本证据从实际文档 w:delText 回读，非会话内打标）；重载后 DB 与
# 书签双持久化对账（以实际文档为准）；apply 后重读实际文件回流（harness
# formal_propose/formal_decide 面 CAS/version 正式采用）。配置键
# edits_state_root；错误码 f48_* 不携材料内容。
EDITS_METHODS = frozenset({
    "edits.register", "edits.stream_open", "edits.stream_push",
    "edits.stream_close", "edits.locate", "edits.apply",
    "edits.read_document", "edits.reconcile", "edits.cards",
})

# F45 通道① agent CLI 直改文档（W2b-U15；06:F45 P02/P03/P04）：docxedit.*
# 四方法——产品侧 docx_edit document-adapter 公开面（apply/outputs/output/
# verify）。apply 单一条流：原稿经 harness.read_material（base_revision
# 钉定、CAS 随读必验）回读→纯 Python 确定性生成清洁版＋批注修订版两个
# 真实完整 DOCX（w:ins/w:del＋w:comment；零模型零宿主自动化）→独立保真
# 检查器（python-docx/lxml 不同算路）八维硬门不过即拒→经 U11 合同登记
# harness 正式材料版本：add_material_revision(source=assistant_edit∈F114
# 闭集)＋formal_propose(channel=machine, quotes=编辑定位集) pending。
# 产物 append-only（旧稿不覆）；同 request id 重放幂等。Word/WPS 宿主
# 自动化（通道②）不在本组（U16）。config：docx_edit_state_root＋harness_*
# 同域键；未配置/未知方法绝不 stub 成功。
DOCX_EDIT_METHODS = frozenset({
    "docxedit.apply", "docxedit.outputs",
    "docxedit.output", "docxedit.verify",
})

# F56 文书模板起草（W4-U38；06:F56 owner=product+harness B4，P04
# binding=templates.register/render/save_answers）：产品侧
# template_drafting 公开面（document-adapter 家族，F45 docx_edit/F54
# conversion 同族）。访谈式三段：templates.interview（变量问询——变量
# 清单自模板内容控件确定性提取，模板字节经 harness CAS 随读必验）→
# templates.save_answers（填充——答案账 append-only，缺变量/多变量/
# 类型不符具名拒不发明值，金额十进制串禁浮点）→ templates.render
# （装配——结构/视觉具名硬门〔E13 模板结构视觉段承接：控件外结构/
# style/numbering/section/外链/隐私/占位残留/独立 lxml 检查器〕→ 经
# U11 合同入 harness 正式材料版本链 add_material_revision
# source=assistant_edit∈F114 闭集＋formal_propose channel=machine
# author=lvyin-templates）。模板库 templates.register＝版本＋授权元数据
# append-only（v1=harness.register_material upload 律师自备外部文件；
# vN+1=add_material_revision 缺省 upload；缺授权 f56_license_required
# 拒）。模板/答案/装配三账同输入两跑同字节（零时钟零随机）。config：
# templates_state_root＋harness_* 同域键；错误码 f56_* 不携材料内容。
TEMPLATES_METHODS = frozenset({
    "templates.register", "templates.list", "templates.template",
    "templates.interview", "templates.save_answers", "templates.answers",
    "templates.render", "templates.renderings",
})

# F62 法院来件 OCR 入库链（W3-U14；06:F62 acceptance「法院来件附件OCR及
# 送达候选人审入库；重复短信幂等」；17 卡「既有 command_tx 和
# MatterStore/CAS 承接入库……新场景字段在同owner扩不新库」）：产品侧
# court_inbound 公开面——短信登记（确定性解析＋附件 sha 钉定）→入件跑批
# （复用 ocr.batch_*＝F41 已 VERIFIED 公开面，引擎权威=F40 worker 钉定
# 解释器 GPU fail-closed·绝不运行时下载）→阅读候选提取（正则确定性，
# LegalTech 约束 1 禁模型猜测；候选非事实，人审前不入正式账＝E24 纪律
# 「送达事实不由上传日补」）→律师逐候选确认→入库
# harness.register_material（F08 MatterStore/CAS，CommandKey 按
# (matter,sms,内容sha) 派生＝重复短信全链幂等：同 id 异内容具名拒／同
# 内容异 id 去重回既有账）。幂等三层面各有独立负向：短信账/F41 批/harness
# 材料。边界如实：06 卡「AI 阅读」步 v1 落为确定性结构化阅读（模型辅助
# 阅读不在 F62 acceptance 文本内，模型轮次纪律沿 §2.1）；E17 取证账、
# E21 期限计算、F118 提醒、E24 外部发送零触；附件原件字节不出 OCR 状态
# 根域（入库材料=OCR 文本衍生物＋溯源）。config：court_inbound_state_root
# ＋ocr.*/harness.* 同域键；未配置/未知方法绝不 stub 成功；错误码 f62_*
# 不携材料内容。
COURT_INBOUND_METHODS = frozenset({
    "court_inbound.sms_receive", "court_inbound.inbound_run",
    "court_inbound.candidate_review", "court_inbound.intake",
    "court_inbound.read", "court_inbound.list",
})

# F46/F52 WPS 宿主自动化半边（W2b-U36；06:F46/F52 17 卡「公开 proposal/
# base refs→宿主原生定位/修订/比对→部分接受/拒绝→重读实际文件→CAS/
# version→Harness 正式采用；不模拟DOCX」＋「Word 与 WPS 真实接受后回读新
# CAS/version，未接受不改 canonical」）：产品侧 wps_host 公开面（document-
# adapter，通道②）。真 WPS COM（pywin32 DispatchEx KWPS.Application 独立
# 进程，绝不附着用户已开窗口；进程内全局锁串行限流——08§2 末段不打扰
# 用户现有任务）三方法：available＝环境探针；review＝宿主打开实际 DOCX
# 读**宿主原生** Revisions 集合（含表/脚注面，宿主口径不解析中间量冒
# 充）；decide＝封闭选择器逐条 Accept/Reject（每动一条重新枚举——WPS
# 修订集合随增删重排，快照索引越位是挂死不是报错，实测钉定）→SaveAs2
# 显式 docx→重读盘上真实字节回流（＝U11 合同 formal_decide resultBytesB64
# 宿主侧来源，source=user_accept/resultSource=host_result_bytes）＋同
# 会话重开核对修订状态（重载回流）。WPS 半边 only——F46-word/F52-word
# 保持 NOT_RUN（§6.1 裁决#4 WPS 先行 Word 后补，回收点 W2-S1/W4-S2）；
# LibreOffice 仅渲染辅助核（U14 先例）不在此面不替代 WPS 主验证。配置键
# wps_host_state_root（available 无需配置）；错误码 wps46_* 不携材料内容。
WPS_HOST_METHODS = frozenset({
    "wpshost.available", "wpshost.review", "wpshost.decide",
})

# RE-37 合同起草·评分门（施工波 2026-10-30 单元 #37；规格=
# docs/RE规格库/RE-37-合同起草评分门.md，对齐识律 law-bench MIT）：
# 产品侧 contract_gate 公开面——条款库三源（base/tagged/custom 13 字段
# 语义+幂等 upsert+受控词表+逐维 tag_review 准入门）→装配（逐节覆盖
# custom>tagged>base+扩展节+coherence 三条门 fail-closed）→填槽
# （fill_cache 六元组键+确定性机检）→rubric 评分门（all-pass 二值、
# 每规则独立 judge、瞬态退避不计 FAIL、评估快照）→自愈管线
# （improve 两类动作分权：本轮排除/建议仅记录；共享条款库只读）→
# learn/tag 迭代慢回路 + A-B compare（drafter-only）。交付语义＝all_pass
# 与耗尽同末态出稿，gate_status=passed|exhausted 强制随行（exhausted
# 具名「未过关」，只有 passed 可表述已过关）。起草≠审查（RE-12 衔接
# 面五条）：判定语汇 pass/fail 与 #12 四级风险分级零混用、单向送审、
# law_refs 静态归集只标注不裁决。LLM 经进程内 seam 注入
# （config contract_gate_llm，会话技能循环面/单测注入；CLI 无 seam=
# LLM 方法 typed 拒）；存储落文件账（contract_gate_state_root）。
# config：contract_gate_state_root（＋LLM seam 键）；错误码 cg37_*。
CONTRACT_GATE_METHODS = frozenset({
    "contract_gate.clause_upsert", "contract_gate.clause_list",
    "contract_gate.clause_get", "contract_gate.clause_delete_auto",
    "contract_gate.clause_review_tag", "contract_gate.clause_bulk_review",
    "contract_gate.review_queue", "contract_gate.tag_dim_register",
    "contract_gate.assemble",
    "contract_gate.rubric_list", "contract_gate.rubric_get",
    "contract_gate.rubric_create", "contract_gate.rubric_update",
    "contract_gate.rubric_delete", "contract_gate.criterion_add",
    "contract_gate.criterion_update", "contract_gate.criterion_delete",
    "contract_gate.criterion_reorder",
    "contract_gate.evaluate", "contract_gate.run_list",
    "contract_gate.run_get", "contract_gate.dashboard",
    "contract_gate.pipeline", "contract_gate.pipeline_list",
    "contract_gate.pipeline_get",
    "contract_gate.compare_run", "contract_gate.compare_list",
    "contract_gate.compare_get", "contract_gate.compare_matrix",
    "contract_gate.run_draft", "contract_gate.drafter_create",
    "contract_gate.drafter_list", "contract_gate.drafter_get",
    "contract_gate.drafter_delete",
    "contract_gate.learn", "contract_gate.iteration_analyze",
    "contract_gate.iteration_apply", "contract_gate.retag_suggest",
    "contract_gate.retag_apply", "contract_gate.master_regenerate",
})

# F17-wps 原生前端栈复用 WPS 宿主面（W2b-U50；06:F17「用户已冻结OpenCode
# 原生UI服务闭包…法律WordWPS编辑独立，不第二DOCX编辑器」host=wps 实例）：
# 产品侧 wps_host_surface 公开面（document-adapter 家族）。WPS 宿主侧 UI
# 承载面＝原生栈投影经 WPS COM 装配进宿主自身 CommandBar 临时停靠面板
# （Temporary=True 会话级即弃；真机探针钉定 12.1.0.28802：Application.
# TaskPanes 内置窗格本会话形态不可承载自定义内容，JSAPI 加载项需装用户
# 配置并重启宿主＝违反会话纪律，具名边界）。硬红线：宿主会话纪律沿用
# U36（DispatchEx 独立进程绝不附着用户已开窗口＋同一把进程内全局锁串行
# ＋Visible=False＋finally 必 Quit）；不第二 DOCX 编辑器＝正文渲染/编辑
# 一律宿主自身，产品侧只投影四类闭集（格值=U05 支持状态/引用=F87 三态/
# 修订清单=宿主 Revisions（U36 通道同源枚举）/决定引用=U11 提案状态闭
# 集），零独立编辑实现（AST 可验：无 SaveAs/Accept/Reject/TypeText）；
# 附着已开窗口尝试＝f17wps_attach_refused 具名拒（GetActiveObject 结构
# 性缺席）；闭集外状态响亮拒（014 patch review-ops.ts 投影纪律同款）。
# 配置键沿用 wps_host_state_root（available 无需配置）；错误码 f17wps_*
# 不携材料内容。
WPS_SURFACE_METHODS = frozenset({
    "wpssurface.available", "wpssurface.mount",
})

# F53 AI 修订作者与人工决定策略面（W2b-U49；06:F53「修订author与真实来源
# 匹配，不默认伪装律师；律师接受有真实决定引用，保对外可见策略」）：产品侧
# author_policy 同进程公开面（零状态根）。作者声明闭集与真实通道绑定——
# 机器生成 author∈{lvyin-redline,lvyin-edits,lvyin-docxedit} 分别绑定
# redline/edits/docxedit 三通道（U12/U14/U15 透传 author 先例收拢成策略面，
# 三面在各自 author 入口过闸；冒充律师名＝f53_author_impersonation 具名拒）；
# author.projection＝『律师决定引用↔修订 author↔提案 channel』三方可读投影
# ＝对外可见策略，经 HARNESS_FORMAL_PROPOSAL_METHODS 冻结组只读提案账——
# 决定权威＝harness formal_decide（U11 已 VERIFIED：accept 必带
# reasonRef/receiptRef，空决定面具名拒），本单零 harness 改动。伪造 author/
# 决定引用缺失/跨提案引用错位 全具名拒；投影只读呈现（patch 015 与 U31
# patch 014 同族 config 门禁 seam）。
AUTHOR_POLICY_METHODS = frozenset({
    "author.policy", "author.check", "author.projection",
})

# F12 凭据保险库（W3-U09；06:F12 双实例「真实BYOK经DPAPI/keyring读写；
# 配置和日志不露key；缺解密不明文降级」）：产品侧 credential_vault 同进程
# 公开面。唯一持久化＝vault_state_root 下 DPAPI 密文 blob（CryptProtectData
# 当前用户作用域；keyring 后端显式选择、未装＝具名拒不静默降级）；put/get
# 真实写读（get 默认只回 sha256+掩码形，显式 reveal 才回 secret_b64）；
# 缺解密＝typed vault_decrypt_failed，结构性不存在明文回退路径。测试键
# DeepSeek 形（sk-+32hex）运行时生成，不入 git 不入证据。
VAULT_METHODS = frozenset({
    "vault.status", "vault.put", "vault.get", "vault.delete", "vault.list",
})

# F10 案件库 at-rest 密钥供给（W4-U32；06:F10 双实例「加密持久状态和CAS可
# 恢复；无密钥不可读且不明文降级」）：产品侧 atrest_key 同进程公开面。
# 不造第二凭据体系：唯一持久化＝既有 F12 保险库登记位 lvyin.f10/
# atrest-aes-256-gcm-v1（DPAPI 密文 blob）；provision=get-or-create 幂等，
# 回执零密钥字节（sha256+掩码形）；加密态（config.f10_atrest=on）取钥唯一
# 通道＝保险库解密，取不到＝typed f10_atrest_key_not_provisioned 拒——
# 绝不静默明文落盘。加密本体在 harness EncryptedCASStore 与 anonymizer
# atrest 面（各走其仓分支），本面只管密钥供给与 material.parse_* 取钥。
ATREST_METHODS = frozenset({
    "atrest.status", "atrest.provision",
})

# F07 产品审计 HMAC 完整性（W3-U09；06:F07 双实例「产品审计HMAC完整性，
# 密钥归产品凭据设施；不恢复Harness已拆部署签章总闸；篡改/截断/重放检测，
# 摘要不含原件/身份/秘密」）：产品侧 audit_hmac 同进程公开面——HMAC-SHA256
# append-only 链；唯一取钥通道＝credential_vault（F12，lvyin.audit/
# hmac-sha256-v1），设施未配置/未登记＝typed 拒，无独立钥文件无派生回退；
# 事件闭集＝扁平小元数据（原件/身份/秘密结构性进不了链，只以 digest/ref
# 在场）；harness 侧为既有静态复用（W25 audit_chain SHA256 链＋audit.read/
# verify/export），本组零 harness 改动、绝不恢复 stage B 已拆的
# activation/deployment/sealed-signature 总闸（审计面是证据账非业务闸）。
AUDIT_HMAC_METHODS = frozenset({
    "audit.append", "audit.verify", "audit.read", "audit.export",
})

# F06 MFA 两步验证（W5-U08；06 V7-06 v2 owner=product，UI_HOST_OR_NEW_
# PRODUCT，desktop/selfhost 双实例「MFA注册登录恢复与失效真实可用；密钥
# 和恢复码不明文日志」）：产品侧 mfa_auth 同进程公开面。preserved＝自托管
# 认证先做密码级：auth.register/auth.login 为密码级最小身份面（PBKDF2
# 盐化校验值，零明文密码），TOTP/恢复码为增强层不重建认证、不替代 F04
# 案件权限权威（已 VERIFIED，零改动）。增强层凭据归产品凭据设施（F12 保
# 险库先例 W3-U09）：TOTP 密钥/恢复码盐化哈希＝lvyin.mfa/* DPAPI 密文
# blob；TOTP 全程显式 now 纪元秒（确定性合成时钟：过期/重放/已消费窗口
# 可复现）；恢复码一次性消费；明文只进 enroll 回执一次，持久化面与日志
# 结构性零明文（验收含全产物字节级零明文扫描，沿 E10 先例）。
MFA_AUTH_METHODS = frozenset({
    "auth.register", "auth.login", "auth.session",
    "mfa.enroll", "mfa.verify", "mfa.recover", "mfa.status", "mfa.disable",
})
# F137 定时 Agent 任务（W5-U12；06 V7-137 v2 owner=product，UI_HOST_OR_NEW_
# PRODUCT，desktop/selfhost 双实例「v2才启用具体定时任务，时区/授权/失败/
# 停止/幂等实际验证；不同于v1持续任务故障恢复」）：产品侧 f137_scheduled_
# tasks 同进程公开面。v2 闸门＝config["f137_v2_scheduled_tasks"] 必须
# literal True（deny-closed 同 F26 denyByDefault 纪律）；每任务显式授权块
# 同命令一次性建立（grantId 一次性绑定，沿 F24/F26 owner 唯一面）；fireKey
# 幂等回执不双跑；取消即停具名；时区/夏令时/月末＝zoneinfo 确定性合成时
# 钟（显式 now 注入，禁浮点时间运算）。本组零 harness 方法、零 run/goal/
# reminder/terminal 形态——任务执行只经既有 core loop（opencode
# create+prompt 各一次入队，完成记账归 F23 面），不创第二 Agent loop；
# 与 F118 提醒派发环不重复逻辑（本面不读 harness 日程、不生成提醒）。
SCHEDULED_TASK_METHODS = frozenset({
    "f137.task_create", "f137.task_read", "f137.task_list",
    "f137.task_cancel", "f137.task_unsuspend",
    "f137.run_due_round", "f137.reconcile_unknown",
})

# F11 备份恢复（W3-U11；06:F11 backup_sets+restore_jobs 每日自动+口令加密，
# owner=harness+product+anonymizer，desktop/selfhost 双实例）：产品侧
# backup_restore 备份编排公开面（backup_state_root＋backup_targets＋
# backup_passphrase 配置域）。五方法：backup.create（一致备份＋口令加密
# 落包＋backup_sets 账行）/ backup.restore（独立目录恢复＋restore_jobs
# 账行）/ backup.reconcile（结构对账）/ backup.sets / backup.schedule
# （每日 due 计算，显式 now 入参）。harness 腿只消费 E08 既有
# MatterStore.backup()/restore() 与 PgMatterStore.backup()/restore_pg()
# owner 公开面（config.harness_import_path 钉定检出；验收工具 sha256 钉
# 定漂移响亮拒——P01/cases 先例），不自实现第二套存储快照；坏包不覆盖
# 现根（先全量验包后落位；恢复目标=独立目录且绝不与声明现根重叠）；
# 口令加密 PBKDF2→Fernet（cryptography 缺席 f11_crypto_unavailable 具名
# 拒不降级明文）；金额/对象/引用语义验真由验收对账工具经真产品入口在
# 恢复根重放公开面读数（金额整分零浮点）。响应只回计数/摘要/路径——
# 原件与身份映射内容绝不经本桥回传。
BACKUP_METHODS = frozenset({
    "backup.create", "backup.restore", "backup.reconcile",
    "backup.sets", "backup.schedule",
})

# F78 授权激活＋每日校验＋宽限期（W5-U01；06:V7-78 双实例「授权校验/宽限/
# 离线状态真实；不因服务中断删除数据或伪授权」，owner=distribution）：
# 产品侧 license_manager 同进程公开面。激活＝F79 验签过闸后持久化激活记
# 录；每日校验＝24h 窗内不出网、到点真 HTTP，服务不可达进一次性宽限预算
# （锚=最近 valid，绝不展期绝不伪造），revoked 真实入账；状态闭集真实派
# 生，回拨时钟下绝不投影 authorized；本文件零删除路径。F30 协调＝出网前
# 读 F30 旗标（armed 且服务端非回环＝具名拒，回环合成签发服务保持可用；
# F30 冻结通道闭集零改动，F74 自带闸先例）。
LICENSE_MANAGER_METHODS = frozenset({
    "license.activate", "license.check", "license.status",
})

# F79 离线 Ed25519 许可＋设备指纹＋防时钟回拨（W5-U01；06:V7-79 双实例
# 「离线许可验签和时钟回拨反例受控；私钥不入发行物」）：产品侧
# license_verify 同进程公开面。离线令牌 Ed25519 验签只对部署面信任锚
# （config.license_trusted_pubkeys；令牌自带公钥绝不是信任锚）＋设备指纹
# 绑定（MachineGuid 派生 sha256 截断，原始标识永不出面）＋时间窗；单调
# 时钟水印（HMAC 封印，密钥唯一存既有 F12 保险库 lvyin.f79/
# clock-watermark-hmac-v1——legacy link F12 复用）＝授权域唯一时钟权威，
# 回拨 typed 拒、水印封印损坏 fail-closed 绝不自动重置。签发私钥只在
# tools/license_issuer_synth.py（施工/测试设施；裁决#13-19 合成先行＋v2
# 具名回收点），发行树结构性零私钥路径（本组只 PublicKey.verify）。
LICENSE_VERIFY_METHODS = frozenset({
    "license.verify_offline", "license.device_fingerprint",
    "license.clock_status",
})

# F94 技能目录分发链＋F95 cat-xierluo zip 直装兼容（W3-U17；06:F94/F95 各
# desktop/selfhost 双实例）：产品侧 skill_catalog 同进程公开面。
# F94＝「pin commit/hash 的社区技能目录可离线安装和回滚；商用内容不混广
# 场」：git_local 源＝独立仓钉 40-hex commit（git archive 离线取树，源仓只
# 读零改动；仓根 catalog.json 必须声明 {catalog_id, channel}）→ 内容寻址
# 全量替换安装（manifest 逐文件 sha256，schema juscite-f94-skill-catalog/1；
# store/<manifest_sha256>/ 不可变＋skills/ 活动面）→ rollback 沿 history
# 回退上一 install（首 install 无前可回 typed 拒，不乒乓）→ pack/bundle＝
# 桌面离线捆绑（确定性 zip，另一状态根 bundle 源安装零网络，manifest 摘要
# 与源安装相等）。渠道闭集 public/controlled 物理分根：manifest.channel 或
# 仓内声明必须＝目标渠道（受控包装进 public 槽＝f94_channel_mismatch）；
# 面上无任何跨渠道搬运方法。受控内容（manuals/playbook）按 §6.1 裁决#7 合
# 成样本先行，本面不公开蒸馏、原件不出域。
# F95＝「zip 预检路径/权限/来源，格式兼容真安装运行；不信任任意脚本」：
# skill.zip.inspect/install（cat-xierluo 社区 zip 直装，渠道恒 public）——
# 预检一票否决（路径＝上游 isSafeRelativePath 同族＋控制字符/驱动器/保留
# 设备名加固；非普通文件条目拒；setuid/setgid/sticky 拒；重复条目拒；解压
# 预算上限拒），source {url, sha256} 必须声明且与 zip 字节全等；格式兼容
# ＝≥1 个上游可加载技能（SKILL.md frontmatter 契约镜像 oc28 pin
# 026b106bc5d41b679ffc413264229c340871e4d3 config/plugin/skill-file.ts），
# 安装后 skill.catalog.read 的 runtime_projection＝上游 toModelOutput 逐字
# 节同形（真安装运行的消费合同）；不信任任意脚本＝zip 内容仅作数据零执行
# （脚本文件惰性列入 receipt.scripts）。技能目录格式兼容原生 loader：skills/
# 布局可直接作 config skills 目录源。
# config 键 skill_catalog_state_root（未配置=fail-closed NOT_CONNECTED）；
# typed error（SkillCatalogError 的 str 只有 f94_*/f95_* 错误码）透传，
# 其他异常只带类型名——材料内容永不进入错误码。
SKILL_CATALOG_METHODS = frozenset({
    "skill.catalog.install", "skill.catalog.rollback",
    "skill.catalog.verify", "skill.catalog.read", "skill.catalog.pack",
})

SKILL_ZIP_METHODS = frozenset({
    "skill.zip.install", "skill.zip.inspect",
})


# E21 规则族与计算分母冻结＋F104 具名九计算族首批（W2b-U19）：经 P01
# JCClient（create_local_client 同一钉定公开面）消费 JC calc 族公开口。
# 九槽=6 具名域＋3 具名 scope gap（CALC_SCOPE_U0x_NAME_UNKNOWN——未命名槽
# 不凑数，不得以工具箱 7 件或 F108 金额大写/F109 赔偿填槽）；C02 期限族经
# 既有 register_event/calculate_deadlines 入口消费，不另造第二权威。公开
# 方法/规则版本/输入范围在 JC registry 冻结（calc-families/1，rule pack
# 具名官方来源）；金额 Decimal 全程、整数分输出、独立 checker 同输入同
# 输出（checker 不同意不盖章）；unsupported 具名缺口（U01-U03/BAC/复利/
# 叠加减半等）以 typed 错误回传，非纸面答案。config 复用 P01 同域键
# jc_state_root/jc_import_path/jc_rule_roots。
#
# 同族扩展（W2b-U54，F105+F106）：calc.rule_base_recon＝官方规则基准对拍
# （MatterVibe 只是差异发现不是真值——对拍报告差异仅陈述不裁真伪、无
# pass/fail，竞品错值不改 JC 输出、北仲 RULE_PACK_ABSENT 缺口不被竞品表
# 填塞）；calc.calendar_account/calc.calendar_due_date＝日历版本账
# （2025/2026 全国假日＋调休补班表内嵌全带官方文号与版本串回读；次日起算
# 语义；超范围年份→结构化 UNKNOWN 零日期，绝不用已有表外推）。
#
# 同族扩展（W4-U48，F109）：calc.damages＝C07 赔偿金（人损/交通/工伤，
# v1.5 首批扩充——不进 v1 首批九个，不填 U01-U03 scope gap；registry 十槽
# 结构上扩走 JC v1_5_families，九槽冻结字段不动）。地域年度基数精确
# (region, year) 匹配，未装档位 rule_pack_absent typed 拒——不拿旧年度
# 标准或缺值补 0；工资规则前提缺失 typed 拒；金额 Decimal 全程整数分。
CALC_FAMILY_METHODS = frozenset({
    "calc.registry",
    "calc.interest",            # C01 阶梯利息
    "calc.court_fee",           # C03 诉讼费
    "calc.preservation_fee",    # C04 财产保全费
    "calc.contingency_fee",     # C05 风险代理费
    "calc.arbitration_fee",     # C06 仲裁费
    "calc.rule_base_recon",     # F105 官方规则基准对拍（W2b-U54）
    "calc.calendar_account",    # F106 日历版本账（W2b-U54）
    "calc.calendar_due_date",   # F106 版本化届满日（W2b-U54）
    "calc.damages",             # C07 赔偿金（F109 v1.5，W4-U48）
})

# F112 规则包版本化治理＋参数历史回放（W2b-U56；06:F112 双实例）：
# calc.* 同族 governance 方法——经 P01 JCClient（create_local_client 同一
# 钉定公开面）消费 JC 规则包版本账公开口（compiler_core.rule_pack_ledger，
# jc-rule-pack-ledger/1，append-only）。calc.rule_pack_ledger＝账只读回读
# （每包版本行：参数集+摘要/官方 locator+retrieved/生效与登记双时点戳/
# 封存确定性输出样本）；calc.rule_pack_replay＝参数历史回放对账（现行/
# 指定版本/任一在界 as_of 经同一计算器重算，封存样本 digest 全等＝「与
# 当时一致的输出」；as_of 越界/选择器歧义/未知版本 typed 拒）；
# calc.rule_pack_delta＝同输入跨两参数集输出差异归因（toVersion 账内版本
# 或 candidateParams 登记前提案演算；delta 行为唯一归因；无参数变化提案
# rule_pack_version_no_param_change 拒＝配置改动不变输出不得报成功）。
# 登记真实配置变更是 JC 侧代码评审的账本扩展（append-only 账），本桥无
# 写口。config 复用 P01 同域键 jc_state_root/jc_import_path/jc_rule_roots；
# JC typed 拒绝以 JC_FAILURE 携码（exit 4）回传。
RULE_PACK_GOVERNANCE_METHODS = frozenset({
    "calc.rule_pack_ledger",
    "calc.rule_pack_replay",
    "calc.rule_pack_delta",
})

# F90 规则集/Playbook 审查（W4-U45；06:F90 F90-desktop/selfhost 双实例；
# entries P04/P01）：calc.* 同族 review 方法——经 P01 JCClient（
# create_local_client 同一钉定公开面）消费 JC 固定 playbook 审查面
# （compiler_core.playbook_review，playbook-review/1——W4-U25 JC owner
# 扩展：逐条 risk/basis/deviation 三元判定钉规则版本 locator+retrieved
# ＝E21 冻结规则包；候选规则窄投影不进事实链；NOT_CHECKED 留存 unknown
# 缺值不补 0；封章＝独立 checker 不同算路复核同意，不同意 typed 拒）。
# playbook.registry＝程序冻结文档只读；playbook.review＝一次封章审查
# （回执逐字转录＋candidates 块自动入产品候选账——E15 path_candidates
# 窄字段闭集同构）；playbook.candidates/adopt＝候选账投影与显式
# decide（唯一通道，adopt|reject 必带 decisionRef）；playbook.deviations_
# record＝偏差行经 HARNESS_PLAYBOOK_METHODS 落 harness 偏差账（P04）。
# 产品面=implementation/python/playbook_review.py（候选账状态根
# playbook_state_root）；config 复用 P01 同域键 jc_state_root/
# jc_import_path/jc_rule_roots；JC typed 拒以 JC_FAILURE 携码（exit 4）
# 回传；UI 仅调用/展示（本面不建 UI）。
PLAYBOOK_REVIEW_METHODS = frozenset({
    "playbook.registry",
    "playbook.review",
    "playbook.candidates",
    "playbook.adopt",
    "playbook.deviations_record",
})

# F90 P04 leg（W4-U45）：workflow provider playbook 三方法走 --goal-json
# 封闭信封（generic provider dispatch，resolve_provider_method 白名单；
# harness 侧 units.py select_playbook/read_playbook/record_deviation 自
# W09 即在册）。F90 偏差账落点＝record_deviation（observation_ref 钉 jc
# 封章回执 ref＋行 entryId，deterministic requestId 重放安全）；selection/
# read 两方法同组冻结供调用（F90 审查前固定 playbook 选择与回读）。现组
# 零动；未配置/未知方法绝不 stub 成功。
HARNESS_PLAYBOOK_METHODS = frozenset({
    "harness.select_playbook",
    "harness.read_playbook",
    "harness.record_deviation",
})

def _rule_pack_governance_call(method, args, config):
    """F112 rule-pack governance bridge (W2b-U56): dispatch through the
    pinned P01 JCClient surface only. Read-only faces (ledger readback,
    replay reconciliation, delta attribution); missing jc config fails
    NOT_CONNECTED (exit 3); JC-side typed refusals (rewrite, locator
    missing, no-param change, as_of out of range) surface as JC_FAILURE
    carrying the JC code (exit 4) — never a fabricated reconciliation."""
    if not isinstance(args, dict):
        raise NotConnected("rule_pack_governance_params_invalid")
    client = _jc_client(config)
    if method == "calc.rule_pack_ledger":
        return _jc(client.rule_pack_ledger)
    matter_id = args.get("matter_id") or args.get("matterId") or "unscoped"
    payload = args.get("input")
    body = {"matterId": str(matter_id),
            "packId": str(args.get("pack_id") or args.get("packId") or ""),
            "family": str(args.get("family") or "")}
    if not isinstance(payload, dict):
        raise NotConnected("rule_pack_governance_input_required")
    body["input"] = payload
    if method == "calc.rule_pack_replay":
        if args.get("pack_version") or args.get("packVersion"):
            body["packVersion"] = args.get("pack_version") or args.get("packVersion")
        if args.get("as_of") or args.get("asOf"):
            body["asOf"] = args.get("as_of") or args.get("asOf")
        return _jc(lambda: client.rule_pack_replay(body))
    if args.get("to_version") is not None or args.get("toVersion") is not None:
        body["toVersion"] = args.get("to_version") if args.get("to_version") is not None else args.get("toVersion")
    if args.get("candidate_params") is not None or args.get("candidateParams") is not None:
        body["candidateParams"] = (args.get("candidate_params") if args.get("candidate_params") is not None
                                   else args.get("candidateParams"))
    return _jc(lambda: client.rule_pack_delta(body))

# F107 具名 14 程序期限预设逐名绑定（W2b-U55；06:F107 双实例）：经 P01
# JCClient（create_local_client 同一钉定公开面）消费 JC 逐名绑定面
# （compiler_core.deadline_presets，jc-deadline-preset-binding/1——W2b-U19
# 冻结 14 预设 D01-D14 之上的逐名四要素绑定：JC 合同=版本化规则注册表
# 调用时解析（漂移具名拒）；送达起算条件=逐名具名；官方时点=法条+条号+
# 引文（经 E22 冻结面语料核对转录，recon 只读复验）；假期范围=消费
# W2b-U54 F106 日历版本账（calendar_years 声明→版本化年度包供给冻结
# 期限引擎；超范围年份→结构化 UNKNOWN 零日期）。冻结分布不变：9
# RULE_MAPPED＋3 PARTIAL＋D07 UNKNOWN＋D14 CONTRACT_UNKNOWN——缺支持的
# 预设以冻结状态具名拒不硬造固定加天；程序事件闭集（任意业务事件
# deadline_preset_event_kind_not_in_preset 拒）；now 必填＝同输入同回执。
# calc.deadline_preset_evaluate 回执经 _register_json 登记 evaluationRef
# owner=jc。config 复用 P01 同域键 jc_state_root/jc_import_path/
# jc_rule_roots；JC typed 拒绝以 JC_FAILURE 携码（exit 4）回传。
DEADLINE_PRESET_METHODS = frozenset({
    "calc.deadline_presets",
    "calc.deadline_preset_evaluate",
})

def _deadline_preset_call(method, args, config):
    """F107 deadline-preset bridge (W2b-U55): dispatch through the pinned
    P01 JCClient surface only. The binding face is read-only; missing jc
    config fails NOT_CONNECTED (exit 3); JC-side typed refusals (frozen
    UNKNOWN/CONTRACT_UNKNOWN presets, arbitrary business events, missing
    now, out-of-range calendar packs) surface as JC_FAILURE carrying the
    JC code (exit 4) or the structured UNKNOWN receipt — never a fabricated
    fixed-day answer."""
    if not isinstance(args, dict):
        raise NotConnected("deadline_preset_params_invalid")
    client = _jc_client(config)
    if method == "calc.deadline_presets":
        return _jc(client.deadline_presets)
    matter_id = args.get("matter_id") or args.get("matterId") or "unscoped"
    body = {key: value for key, value in args.items()
            if key not in ("matter_id", "matterId")}
    return _jc(lambda: client.deadline_preset_evaluate(
        {"matterId": str(matter_id), **body}))

# F108 金额大写转换（W2b-U55；06:F108 双实例）：经 P01 JCClient 消费 JC
# 纯函数（compiler_core.amount_words，jc-amount-words/1）。金额大写规范
# 边界、分位/零/负数/上限正确，数值来源不变——入参闭集=整数分或 Decimal
# ≤2 位小数（桥面 JSON 只携带 value_minor 整数分或 value 定点串；float
# 具名拒＝F89 纪律）；零元整/组间零一个/角空分有补零/负数「负」前缀
# 不静默/上限 9999万亿…9999元.99 分具名拒；回执回带 value_minor＝只转
# 换不改值（recon 以独立逆解析器逐夹具回读钉死）。回执经 _register_json
# 登记 amountWordsRef owner=jc。config 复用 P01 同域键；JC typed 拒绝以
# JC_FAILURE 携码（exit 4）回传。
AMOUNT_WORDS_METHODS = frozenset({
    "calc.amount_words",
})

def _amount_words_call(method, args, config):
    """F108 amount-words bridge (W2b-U55): dispatch through the pinned
    P01 JCClient surface only. Missing jc config fails NOT_CONNECTED
    (exit 3); JC-side typed refusals (float input, beyond-cent precision,
    upper limit) surface as JC_FAILURE carrying the JC code (exit 4) —
    the value source is never altered by the conversion."""
    if not isinstance(args, dict):
        raise NotConnected("amount_words_params_invalid")
    client = _jc_client(config)
    matter_id = args.get("matter_id") or args.get("matterId") or "unscoped"
    body = {key: value for key, value in args.items()
            if key not in ("matter_id", "matterId")}
    if not body:
        raise NotConnected("amount_words_value_required")
    return _jc(lambda: client.amount_words({"matterId": str(matter_id), **body}))

# F29 缓存分区纪律（W3-U05；06:F29 双实例）：cache.plan / cache.fingerprint。
# 复用选定核心缓存＝lineage 内嵌上游原生 promptCacheKey 仿射变换（oc28
# model-request.ts ses_ 前缀剥离，recon 钉定原文）；稳定/变动上下文分区＋
# IMMUTABLE/APPEND 与前缀指纹（sha256 规范字节序）；case/model/rule 版本
# 变化推导式正确失效（规则→前缀+lineage 变、模型→仅 lineage 变、案件→
# 仅 APPEND 分区轮换，前缀字节恒不动）；预算闸只闸 IMMUTABLE 前缀，超额
# 具名拒不静默截断。纯推导零存储——不建第二缓存引擎（AST 可验），上游
# 原生缓存策略零改动（复用原生缓存不删原策略）。不拿宣传命中率当验收：
# 面输出键闭集，无任何命中率/比值字段（源蓝图 94.7-98.1% 是竞品宣传值，
# 非本产品实测，台账 F29 行明示）。纯面无 config 依赖。
CACHE_PARTITION_METHODS = frozenset({
    "cache.plan", "cache.fingerprint",
})

# F30 飞行模式（W3-U05；06:F30 双实例；17 卡上游 app/desktop owner 落点＝
# implementation/patches/017 prestate）：airplane.status / airplane.set /
# airplane.egress_decision。一键禁出站闭集决策表＝E10 出口清册 11 通道行
# （enforcement_kind 具名谁执法：bridge_gate 活闸两通道 live 验证／
# upstream_env·config·permission_plane·default_off·partial·property·
# desktop_patch 结构验证——recon 各按其手段核，绝不把结构面读成行为
# PASS）。活闸：review_chat.ask 模型轮（armed＋provider 非本地声明→
# airplane_remote_model_blocked，在会话创建前拒不建会话）；case.search
# lcr/1 HTTP 检索（armed＋非回环 cases_url→airplane_remote_case_retriever_
# blocked，连接前置拒）。离线读算永不设闸：statute.*/citation.*/calc.*/
# number.* 等本地冻结面原样可用（E22/W2a-U13/JC 本地面）。armed 前一切
# 面行为与现状逐字节相同（缺 state root＝未启用）。
AIRPLANE_METHODS = frozenset({
    "airplane.status", "airplane.set", "airplane.egress_decision",
})

# F27 提示注入防御（W3-U04；06:F27＋17 卡「恶意材料/skill 提示不能变 system
# 权威或扩大权限；原证据内容保真；保 spotlighting nonce 及摄取期注入扫描」）：
# 产品面 injection_defense 同进程公开面（纯确定性函数：正则/状态机，零模型
# 零网络零 I/O——F89 确定性纪律同款）。injection.scan＝摄取期注入扫描（闭集
# 四族 AUTHORITY_OVERRIDE/PERMISSION_EXPANSION/SKILL_DIRECTIVE/MARKER_SPOOFING
# ，只回偏移与规则 id 绝不回传命中文本——扫描报告不得成为第二注入通道）；
# injection.envelope＝spotlighting nonce 信封（逐信封随机 nonce，载荷逐字节
# 保真；载荷自带信封标记语法＝f27_marker_in_payload 具名拒，逃逸结构性不
# 收）；injection.verify＝标记/nonce 配对/摘要/原文回读四重核验（篡改具名
# 拒）；injection.assemble＝权威边界装配——system 段只装可信模板且逐块断言
# 零不可信字节（f27_untrusted_in_system_section 具名拒＝注入文本不能变
# system 权威），全部不可信内容只落 data 段 nonce 信封内。本面零权限语义
# （AST 可验）：扩权限在结构上不是提示词能做的事——权限真源=F-9 守卫＋产品
# policies veto（e07_coordinator）与 harness 工具治理账（F26），永不在提示
# 文本。纯函数无配置；未知方法绝不 stub 成功。
INJECTION_DEFENSE_METHODS = frozenset({
    "injection.scan", "injection.envelope",
    "injection.verify", "injection.assemble",
})

def _injection_call(method, args, config):
    """F27 injection-defense bridge (W3-U04): in-process deterministic face.
    Typed refusals (closed families, marker escape, digest mismatch,
    untrusted-in-system) surface as NOT_CONNECTED carrying the bare f27_*
    code — never payload content."""
    from injection_defense import InjectionFaceError, face_call
    try:
        return face_call(method, args)
    except InjectionFaceError as exc:
        raise NotConnected("injection_face_failed:" + str(exc)) from None
    except Exception as exc:
        raise NotConnected("injection_face_failed:" + type(exc).__name__) from None

# F31 MCP 连接器＋四档暴露策略（W4-U33；06:F31「MCP四暴露策略真实约束
# 发现/调用；凭据隔离，远端响应不得扩权」）。mcp.* 确定性公开面：register
# （登记台账，需 mcp_state_root）／compile（四档→oc28 v2.0.28 原生面工件，
# 凭据只持 ref）／materialize（plan+secrets→服务配置文件，凭据明文唯一
# 落点，缺 secret typed 拒不降级）／response_guard（远端响应恒数据面，
# 无信任开关通道）／invoke_policy（四档×双面真值表，法律 profile execute
# 全禁语义在案）。绝不建第二 Agent loop、不直连服务改状态——活体消费走
# oc28 原生通道。未知方法绝不 stub 成功。
MCP_CONNECTOR_METHODS = frozenset({
    "mcp.register", "mcp.compile", "mcp.materialize",
    "mcp.response_guard", "mcp.invoke_policy",
})

def _mcp_connector_call(method, args, config):
    """F31 mcp bridge (W4-U33): in-process deterministic face.
    Typed refusals (unknown tier, unresolved credential ref, shape
    errors) surface as NOT_CONNECTED carrying the bare mcp_* code."""
    from mcp_connector import McpFaceError, face_call
    try:
        return face_call(method, args, config)
    except McpFaceError as exc:
        raise NotConnected("mcp_face_failed:" + str(exc)) from None
    except Exception as exc:
        raise NotConnected("mcp_face_failed:" + type(exc).__name__) from None

# F28 单 agent 循环预算（W3-U04；06:F28「轮数+token 预算闸+超限收敛工具面」
# ＋05:37 机械暂停紧箍咒）：产品面 turn_budget 同进程公开面（确定性评估，
# 金额整分端到端——float 成本 f28_cost_not_minor_units 具名拒）。budget.
# evaluate＝无状态面：逐轮记录（tokens/cost_minor/elapsed_s/failure_code）
# 确定性评估四闭集边界（PAUSE_REASONS 同一闭集，F28 零新增边界名）——
# 轮数上限可不设（round_cap=None 一等合法：轮数永不单独触发暂停；已设轮数
# 上限耗尽=BUDGET_LIMIT rounds 形）；次数无限≠费用无限（token/费用/时间
# 上限仍收敛）；不无限撞同一失败（max_identical_failures 连续同签名失败
# →NO_PROGRESS）；授权/法律缺口（permission* 失败码→PERMISSION_MISSING
# 即时）。超限收敛工具面=budget.projection（policy/consumed/caps 状态投
# 影，resume 显式通道回显）；有闸协调器把超限判定经 harness.pause_goal 写
# 真实 goal 账（boundary+triggerValue+时间入账可回读），下一轮 preflight
# 即 blocked——收敛落账面在 harness（T16 目标账），账本事实重启存活；本面
# meter 为 episode 内存态如实声明。纯函数无配置；未知方法绝不 stub 成功。
BUDGET_METHODS = frozenset({
    "budget.evaluate", "budget.projection",
})

def _budget_call(method, args, config):
    """F28 turn-budget bridge (W3-U04): in-process deterministic face.
    Typed refusals (unknown policy fields, float cost, invalid records)
    surface as NOT_CONNECTED carrying the bare f28_* code."""
    from turn_budget import BudgetError, face_call
    try:
        return face_call(method, args)
    except BudgetError as exc:
        raise NotConnected("budget_face_failed:" + str(exc)) from None
    except Exception as exc:
        raise NotConnected("budget_face_failed:" + type(exc).__name__) from None
# E23 受控内容消费·读侧桥（W3-U19；07 E23 owner=manuals+persona+harness，
# B1 段＋05:238「运行时只做既有受控消费」）：manual.* 四方法与 manuals 仓
# legal_cn_manuals.consumer 读侧白名单（manual.open/search/read/version，
# lccc_consumer 同款形态）一一对应——本桥只转发，不造第二消费者、不复制
# 内容权威。消费面离线确定性（内存匹配），trust/readScope 随回执如实携带；
# private 记录永不出走读侧白名单（scope_mismatch 具名拒＝不公开蒸馏的
# 结构面）。读取回执（C16 使用记录）落 manuals 仓自家 delivery log。
# config 键：manuals_contract（=lh-distill-ingest/1，取自钉定模块常量）、
# manuals_import_path（钉定 manuals 仓 src 目录，只读导入）、
# manuals_packs_root（packs 状态根）。未配置/未知方法绝不 stub 成功。
# 方法组冻结＝纯读侧四方法：无 publish/enable/distill/observe 写面——
# 消费动作不自动改路由 prompt、不自动启用规则发布（E23 断言面，负测见
# PENDING_OWNER_e23_controlled_content_recon.py）；Observer 建议待用户
# （裁决#7：不启用），persona 为可选件（仓缺失时系统仍完整可用）。
MANUAL_METHODS = frozenset({
    "manual.open", "manual.search", "manual.read", "manual.version",
})

# F73 用户自建知识库 RAG（W4-U43；06:F73 desktop/selfhost 双实例·B4·
# owner=manuals+product·entries P02/P04）：经验文集/所内知识按授权/快照/
# 出处检索＋质量评分＋过期治理＋分案隔离。产品面引擎 kb_rag.py（实现
# 细节见其模块头）：条目带 readScope 三级闭集＋entryDigest 内容快照
# sha256＋sourceRefs 出处（C16 ref 形状）；private 永不可授权/永不出读
# 侧白名单（不公开私域蒸馏）；受控内容包只经既有受控通道——本组与
# MANUAL_METHODS 正交，绝不经本组读 manuals 正文（kb_rag 零
# legal_cn_manuals import＝manuals 仓零引擎代码铁律＋不复制第二权威）；
# 向量底座为 f71_hybrid/1 接口级复用（非硬 DAG，零 lcr/cases import）。
# config 键：kb_state_root（必需）；kb_backend（可选，未知值具名拒）。
KB_METHODS = frozenset({
    "kb.entry_put", "kb.search", "kb.read", "kb.stats",
})

# F100 专家分身/专家商店（W5-U04；06:F100 desktop/selfhost 双实例·B5·
# owner=manuals+product·entries P02/P04）：分身＝固定受控内容包（卡片
# 全字段快照 sha256＋逐条目 digest；private 内容结构性不入包＝不公开
# 私域蒸馏）；商店＝元数据只读货架（store_list/store_read 永不携条目
# 正文）。17 卡四步对齐：固定内容 hash/权限（define 钉 digest/授权/
# 适用范围声明）→公开读取（store_list/store_read 授权 fail-closed）→
# 实际任务消费（consult 确定性词面评分·零模型零网络·零相关即具名弃
# 答）→来源回执和验证（consult 回执落盘＋verify_receipt 全量重算，漂
# 移具名拒不假 PASS）。分身不冒真人实时意见＝结构面：grounding 闭集只
# 认 pinned_pack（任何 live/realtime 形具名拒）＋declaresRealTime 恒
# False（True 具名拒）＋应答恒携不冒真人声明；授权面闭集 synthetic
# _original/authorized_excerpt（后者必须 attributedTo+authorizationRef，
# 缺失不入店）。方法组冻结五方法：无 publish/enable/distill/observe
# 写面；受控内容公开消费只经既有冻结通道（E23 MANUAL_METHODS 四方法＋
# HARNESS_PLAYBOOK_METHODS 三方法）——expert_store 零 legal_cn_manuals/
# playbook import（不复制第二权威）。裁决#7/#13-19：内容一律合成样本；
# Observer 不启用（顶层 persona./observer. 具名拒不动）。config 键：
# expert_state_root（必需）。
EXPERT_METHODS = frozenset({
    "expert.define", "expert.store_list", "expert.store_read",
    "expert.consult", "expert.verify_receipt",
})

def _manual_call(method, args, config):
    """E23 controlled-content read-side bridge (W3-U19): dispatch to the
    pinned manuals checkout's ManualsConsumer (the only read-side
    whitelist). Missing config fails NOT_CONNECTED (exit 3); manuals-side
    typed refusals (scope_mismatch / ref_not_found / query_invalid /
    cursor_expired / ref_version_unavailable) surface as NOT_CONNECTED
    carrying the manuals code — never a fabricated body, and error text
    carries only the provider code, never record content."""
    if not isinstance(args, dict):
        raise NotConnected("manual_params_invalid")
    if config.get("manuals_contract") != "lh-distill-ingest/1":
        raise NotConnected("manuals_lh_distill_ingest_1_not_configured")
    import_path = config.get("manuals_import_path")
    if not import_path or not os.path.isdir(import_path):
        raise NotConnected("manuals_import_path_missing")
    if import_path not in sys.path:
        sys.path.insert(0, import_path)
    try:
        from legal_cn_manuals.consumer import ManualsConsumer
        from legal_cn_manuals.errors import ProviderError
    except ImportError as exc:
        raise NotConnected("legal_cn_manuals_not_importable:" + str(exc)) from None
    packs_root = config.get("manuals_packs_root")
    if not packs_root:
        raise NotConnected("manuals_packs_root_not_configured")
    consumer = ManualsConsumer(packs_root)
    op = method.split(".", 1)[1]
    try:
        if op == "open":
            return consumer.open(scope=args["scope"], pack_id=args["pack_id"],
                                 version=args["version"])
        if op == "search":
            return consumer.search(
                scope=args["scope"], packRef=args["packRef"],
                query=args.get("query", ""),
                routeKeys=args.get("routeKeys", []),
                includeHeld=bool(args.get("includeHeld", False)),
                cursor=args.get("cursor"), filters=args.get("filters"))
        if op == "read":
            return consumer.read(scope=args["scope"],
                                 record_ref=args["record_ref"])
        # manual.version
        return consumer.version(scope=args["scope"], pack_id=args["pack_id"],
                                version=args.get("version"))
    except ProviderError as exc:
        raise NotConnected("manuals_provider_" + str(exc.code)) from None

# F59 立案材料准备/提交包（W3-U12；06:F59 desktop/selfhost 双实例；17 卡
# 人工确认制）：产品面 submission_package.submission_call——可读提交包确
# 定性渲染（同输入同字节，无时钟）＋律师确认显式 confirm 闸（非 True=
# f59_confirmation_flag_required 具名拒）＋harness 两账六方法转发（清单
# 声明账/包时点对账账——材料映射回 F08 材料链头版、缺件具名、律师确认=
# 包行内决定面）。绝不实际对外提交：本组零出站通道（模块导入闭集零网络
# ——wiring AST 钉死），对外提交动作在本面与 harness 面都结构性不存在，
# 投影恒带 submissionChannel='none'。config 复用 harness 桥同域键；
# selfhost recon 经 harness_call 注入直连同封闭注册。
SUBMISSION_PACKAGE_METHODS = frozenset({
    "submission.checklist_define",
    "submission.checklist_read",
    "submission.package_build",
    "submission.package_confirm",
    "submission.package_read",
    "submission.package_list",
})

# F60 内部事件幂等同步外部日历（W3-U12；06:F60 desktop/selfhost 双实例；
# 裁决#6 滴答/飞书合成端点先行，真实 OAuth 授权后补联测）：产品面
# calendar_sync.calendar_sync_call——编排＝推送前 harness 守门登记（JC
# 期限回执互钉 owner=jc＋回执形态自洽，拒绝则零出站流量）→HTTP 推送→
# 结果回记→投影回读（legalDueDate 与外部状态分列）；外部回流拉取逐事件
# 入账（requestId 由 externalEventId 派生＝重复拉取幂等）；冲突律师决定
# 显式 confirm 闸。期限值永不重算（消费 F107 冻结引擎回执＋F106 日历账，
# 均 VERIFIED）；取消/改期冲突回流不自动更改法律期限（harness 期限列无
# UPDATE 路径，改期唯一通道=新 sync 行＋新 JC 回执）。端点 URL 只来自显
# 式 config（calendar_sync_endpoints），未配置目标 NotConnected 具名拒，
# 无内置端点/默认 URL（禁编 URL，P11 同纪律）。
CALENDAR_SYNC_METHODS = frozenset({
    "calendar.sync_event",
    "calendar.pull_external",
    "calendar.resolve_conflict",
    "calendar.sync_read",
    "calendar.sync_list",
})

# F59/F60 harness 账面方法组（W3-U12；--submission-json/--calsync-json 信
# 封独立成面）：清单/包两账六方法＋日历同步两账六方法。产品面（上面两
# 组）经 legal_entry.call 消费本组（缺省派发器）；recon 负向直接点名本组。
HARNESS_SUBMISSION_METHODS = frozenset({
    "harness.submission_checklist_define",
    "harness.submission_checklist_read",
    "harness.submission_package_generate",
    "harness.submission_package_confirm",
    "harness.submission_package_read",
    "harness.submission_package_list",
})

HARNESS_CALENDAR_SYNC_METHODS = frozenset({
    "harness.calendar_sync_register",
    "harness.calendar_sync_record_result",
    "harness.calendar_external_event_record",
    "harness.calendar_sync_resolve",
    "harness.calendar_sync_read",
    "harness.calendar_sync_list",
})

# F126 多设备同步（W5-U11；06 F126「多设备同步（WebDAV 端到端加密）」，
# owner=harness+product 双实例 desktop/selfhost；裁决#13-19 WebDAV 合成
# 先行）：产品面 sync.* 五方法（编排＝传输与重试驱动，见 device_sync）；
# harness 账本七方法分两组——密钥面四方法（bundle build/ingest＋
# manifest seal/open，sync key 只经 owner API in-process 通道，E06 环境
# 合同不动、public_entry 密钥通道不接线＝F10 同构边界）＋无钥读三方法
# （state/object/journal replay，--sync-json 封闭信封子进程，投影与回放
# 对账面）。
SYNC_METHODS = frozenset({
    "sync.push",
    "sync.pull",
    "sync.state",
    "sync.object_read",
    "sync.journal_replay",
})

HARNESS_SYNC_KEYED_METHODS = frozenset({
    "harness.sync_bundle_build",
    "harness.sync_bundle_ingest",
    "harness.sync_manifest_seal",
    "harness.sync_manifest_open",
})

HARNESS_SYNC_READ_METHODS = frozenset({
    "harness.sync_state_read",
    "harness.sync_object_read",
    "harness.sync_journal_replay",
})

# F119 证据目录＋F120 质证意见（W4-U51）：证据→质证链的 harness 账本
# 半边九方法，走 --evidencechain-json 封闭信封（独立成面）。目录只能从
# 在账证据生成（证据钉 F08 材料链真实 revision）；媒体加工留痕可回读；
# 质证逐条主张强制绑证据 ref＋反方观点 ref，带法条引用的主张必带产品
# 面 F87 闸凭据（CITATION_VERIFIED）。生成产物（目录/意见 docx）与提
# 案/决定人审合同在产品面/既有面——本桥只路由不解释。
HARNESS_EVIDENCE_CHAIN_METHODS = frozenset({
    "harness.evidence_register",
    "harness.evidence_read",
    "harness.evidence_list",
    "harness.evidence_media_op_record",
    "harness.evidence_media_op_read",
    "harness.evidence_media_op_list",
    "harness.cross_exam_draft_record",
    "harness.cross_exam_read",
    "harness.cross_exam_list",
})

EVIDENCECAT_METHODS = frozenset({
    "evidencecat.generate", "evidencecat.read", "evidencecat.list",
    "evidencecat.media_probe", "evidencecat.media_process",
    "evidencecat.media_read",
})

CROSSEXAM_METHODS = frozenset({
    "crossexam.generate", "crossexam.decide", "crossexam.read",
})
# F123 导出签名清单（W4-U54；06 F123 v1.5 owner=harness+product）三冻结
# 组：①harness.export_* 账面六方法（--exportledger-json 信封独立成面；
# harness docs/f123-signed-export-contract.md——签发账＋验签回执账，账本
# 侧独立重算 manifest_sha256/file_set_digest 过账，manifest 全库 UNIQUE，
# PASS/TAMPERED 与 findings 互斥绑定）；②export.* 签发面四方法（signed_
# export.py 签发器——逐文件 sha256＋清单 HMAC-SHA256 签名＋过账才回执；
# export.secret_exposure_scan＝F41 batch_secret_exposure 同法全产物扫
# 描）；③export.verify 独立验证器（export_manifest_checker.py——与签发
# 器不同代码路径，calc_checker 独立算路先例：零 import 签发器、遍历实际
# 目录独立重算、三形态篡改定位到具体文件）。密钥只存本机 state
# （signed_export_state_root 下 signing.secret，F41 同法），清单/账本/
# 回执只携 keyFingerprint 指纹——私钥不出包（recon 另做发行物字节扫
# 描：W3-U33 F77 工件字节扫描同法）。
HARNESS_EXPORT_LEDGER_METHODS = frozenset({
    "harness.export_record_create",
    "harness.export_record_read",
    "harness.export_record_list",
    "harness.export_verification_record",
    "harness.export_verification_read",
    "harness.export_verification_list",
})

EXPORT_MANIFEST_METHODS = frozenset({
    "export.package",
    "export.package_read",
    "export.package_list",
    "export.secret_exposure_scan",
})

EXPORT_CHECKER_METHODS = frozenset({
    "export.verify",
})

# F34 v2 高级对抗评审编排（W5-U06；06 V7-34 owner=product+harness）两冻
# 结组：①ADV_ORCH_METHODS——产品编排器 f34_adv_orchestrator（声明式计
# 划不固定五步＋按需真会话逐步执行 F23 server-owned 语义＋异构复核第二
# 模型合成先行，裁决#13-19 不同应答形态离线注入）；②HARNESS_ADV_
# METHODS——harness.adv_* 账面五方法走 --advorch-json 信封独立成面
# （计划账＋逐步真会话回执账；review 行模型身份互异账本级断言）。账本
# 合同唯一权威＝legal-harness docs/f34-adv-orchestration-contract.md。
# v1 五角色（E05/T12 VERIFIED）零回退零延期——本组只做 v2 增量。
ADV_ORCH_METHODS = frozenset({
    "adv.plan_register", "adv.plan_read", "adv.plan_list",
    "adv.steps_read", "adv.run",
})

HARNESS_ADV_METHODS = frozenset({
    "harness.adv_plan_register", "harness.adv_plan_read",
    "harness.adv_plan_list", "harness.adv_step_record",
    "harness.adv_steps_read",
})

_CALC_FAMILY_SLOT_BY_METHOD = {
    "calc.interest": "C01",
    "calc.court_fee": "C03",
    "calc.preservation_fee": "C04",
    "calc.contingency_fee": "C05",
    "calc.arbitration_fee": "C06",
    "calc.damages": "C07",      # F109 赔偿金（v1.5 首批扩充，W4-U48）
}

# LPR 取数通道（施工波二轮·LPR 尾巴三件①，20261030）：calc.interest 的年利率
# 数值改读法源数据包 docs/法源数据包/LPR/（lpr-history.json＋pack.meta 版本锚；
# 首载按 pack.meta.hash 对数据文件 sha256 对账=该包 README 使用边界 4，对齐
# RE-13 §3.1 法条包先例）。只做取数通道，零裁定：逐段按「不晚于该段起日的
# 最近一期」在调用方显式指定的序列/档次键内取值（查找规则=方法组
# 借贷-LPR查找规则.md 第 1 条）；「同期」对应哪一档=法律适用判断，归方法组
# 借贷-法律适用与三时段判定件，本桥不代判；域级规则（四倍上限/强制分段/
# 砍头息/复利）维持 JC 完整档挂起位（docs/决策台账.md:69），计算仍在 JC C01
# （rate_source 只记录来源，费率合法性 JC 侧不裁）。
# fail-closed：config 键 lpr_pack_dir 未配置/包文件缺失/meta 与数据
# pack_version 不一致/sha256 对账不符=typed 拒（包不可用，不静默用残包）；
# LPR 序列所需时点早于首条公告或晚于末条公告=typed 拒——拒绝外推、拒绝
# 相邻期次顶替、拒绝静默延展上一报价；旧贷款基准利率为调整表语义（末次
# 调整持续有效至下一次调整），段起日只按下界取最近一次调整、所用调整日随
# rate_channel 逐段回传供核对；档次键在某调整行缺失（2014-11-22 简并前后
# 档次异构）=该行无此档，选中即查无 typed 拒。单位换算=包内年利率%字符串
# （两位小数）→ C01 年利率小数，Decimal 精确 /100 禁浮点；既有 agreement
# 面（无 rate_request）零改动。
_LPR_PACK_LPR_SERIES = ("lpr_1y", "lpr_5y")
_LPR_PACK_BENCHMARK_SERIES = (
    "within_6m", "6m_to_1y", "1y_to_3y", "3y_to_5y", "over_5y",
    "within_1y", "1y_to_5y",   # 2014-11-22 起简并三档（包内官方表注原文）
)

def _lpr_pct_to_fraction(value_pct):
    """包内年利率%（如 "3.00"）→ C01 年利率小数（"0.03"；Decimal 精确除）。"""
    try:
        return str(Decimal(value_pct) / Decimal(100))
    except (InvalidOperation, ValueError):
        raise NotConnected("lpr_pack_value_invalid:" + str(value_pct)) from None

def _lpr_pack_rate_channel(payload, config):
    """calc.interest LPR 取数通道（口径见上注）。返回 (jc_payload, channel)：
    无 rate_request 时 (payload, None) 原样透传；有则逐段解析包内利率并回传
    取数凭据（rate_channel，随计算书附加）。rate_request 不进 JC 面；段内
    只回填 annual_rate，来源经 rate_source 记录（JC C01 既有字段）。所有
    拒绝均为 NotConnected 具名码，绝不产出纸面利率。"""
    request = payload.get("rate_request")
    if request is None:
        return payload, None
    if not isinstance(request, dict):
        raise NotConnected("lpr_rate_request_invalid")
    if request.get("source") != "lpr_pack":
        raise NotConnected("lpr_rate_source_unknown:" + str(request.get("source")))
    series = request.get("series")
    if series not in _LPR_PACK_LPR_SERIES + _LPR_PACK_BENCHMARK_SERIES:
        raise NotConnected("lpr_rate_series_unknown:" + str(series))
    pack_dir = config.get("lpr_pack_dir")
    if not pack_dir:
        raise NotConnected("lpr_pack_dir_not_configured")
    data_path = os.path.join(pack_dir, "lpr-history.json")
    meta_path = os.path.join(pack_dir, "pack.meta")
    if not (os.path.isfile(data_path) and os.path.isfile(meta_path)):
        raise NotConnected("lpr_pack_files_missing:" + str(pack_dir))
    try:
        with open(meta_path, "r", encoding="utf-8") as handle:
            meta = json.load(handle)
    except (OSError, ValueError):
        raise NotConnected("lpr_pack_meta_unreadable") from None
    meta_hash = str(meta.get("hash") or "")
    pack_version = str(meta.get("pack_version") or "")
    if not meta_hash or not pack_version:
        raise NotConnected("lpr_pack_meta_incomplete")
    with open(data_path, "rb") as handle:
        if hashlib.sha256(handle.read()).hexdigest() != meta_hash:
            raise NotConnected("lpr_pack_hash_mismatch:" + pack_version)
    try:
        with open(data_path, "r", encoding="utf-8") as handle:
            pack = json.load(handle)
    except (OSError, ValueError):
        raise NotConnected("lpr_pack_data_unreadable") from None
    if str(pack.get("pack_version") or "") != pack_version:
        raise NotConnected("lpr_pack_version_mismatch")
    if series in _LPR_PACK_LPR_SERIES:
        parsed = []
        for row in pack.get("lpr_records") or []:
            if not isinstance(row, dict):
                raise NotConnected("lpr_pack_row_invalid:" + series)
            record_date, value = row.get("date"), row.get(series)
            if not (isinstance(record_date, str) and isinstance(value, str) and value):
                raise NotConnected("lpr_pack_row_invalid:" + series)
            try:
                parsed.append((date.fromisoformat(record_date), record_date, value))
            except ValueError:
                raise NotConnected("lpr_pack_row_invalid:" + series) from None
    else:
        # 基准利率行按整行取（档次表逐行异构）；档次有无在选中行内判定，
        # 不跨行拿旧档次值顶替（2014-11-22 简并前后的档次集不同）。
        parsed = []
        for row in pack.get("loan_benchmark_records") or []:
            if not isinstance(row, dict) or not isinstance(row.get("annual_rate_pct"), dict):
                raise NotConnected("lpr_pack_row_invalid:" + series)
            record_date = row.get("date")
            if not isinstance(record_date, str):
                raise NotConnected("lpr_pack_row_invalid:" + series)
            try:
                parsed.append((date.fromisoformat(record_date), record_date,
                               row["annual_rate_pct"]))
            except ValueError:
                raise NotConnected("lpr_pack_row_invalid:" + series) from None
    parsed.sort(key=lambda row: row[0])
    if not parsed:
        raise NotConnected("lpr_pack_series_empty:" + series)
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise NotConnected("lpr_rate_segments_required")
    benchmark = series in _LPR_PACK_BENCHMARK_SERIES
    resolved = []
    for index, segment in enumerate(segments):
        tag = series + ":" + str(index)
        if not isinstance(segment, dict) or segment.get("annual_rate") is not None:
            raise NotConnected("lpr_rate_segment_invalid:" + tag)
        start_raw = segment.get("start_date")
        try:
            segment_start = date.fromisoformat(str(start_raw))
        except ValueError:
            raise NotConnected("lpr_rate_segment_date_invalid:" + tag) from None
        hit = None
        for candidate in parsed:
            if candidate[0] > segment_start:
                break
            hit = candidate
        if hit is None:
            raise NotConnected("lpr_rate_not_in_pack:" + tag + ":" + str(start_raw))
        if benchmark:
            # 选中最近一次调整行后当场判定档次有无：该行无此档=查无
            # （简并取消的档次不回捞旧行值顶替）；调整表语义=末次调整持续
            # 有效至下一次调整，故段起日晚于末行不拒（调整日随凭据回传）。
            value_pct = hit[2].get(series)
            if not (isinstance(value_pct, str) and value_pct):
                raise NotConnected("lpr_rate_not_in_pack:" + tag + ":" + str(start_raw))
        else:
            # LPR 月度报价：晚于末条公告=UNKNOWN（不外推不延展不顶替）
            if segment_start > parsed[-1][0]:
                raise NotConnected("lpr_rate_not_in_pack:" + tag + ":" + str(start_raw))
            value_pct = hit[2]
        resolved.append((hit[1], value_pct))
    rate_source = "lpr_pack/" + series + "@pack:" + pack_version
    declared = payload.get("rate_source")
    if declared is not None and declared != rate_source:
        raise NotConnected("lpr_rate_source_conflict:" + str(declared))
    filled = {key: value for key, value in payload.items() if key != "rate_request"}
    filled["segments"] = [dict(segment) for segment in segments]
    for segment, (record_date_text, value_pct) in zip(filled["segments"], resolved):
        segment["annual_rate"] = _lpr_pct_to_fraction(value_pct)
    filled["rate_source"] = rate_source
    channel = {
        "pack": "lpr",
        "pack_version": pack_version,
        "series": series,
        "verified_through": pack.get("verified_through"),
        "sha256_verified": True,
        "segments": [{"segment": index + 1, "record_date": record_date_text,
                      "annual_rate_pct": value_pct,
                      "annual_rate": _lpr_pct_to_fraction(value_pct)}
                     for index, (record_date_text, value_pct) in enumerate(resolved)],
    }
    return filled, channel

def _calc_family_call(method, args, config):
    """E21/F104 calc-family bridge (W2b-U19; F105/F106 extension W2b-U54):
    dispatch through the pinned P01 JCClient surface only. Unknown methods
    never reach a calculator; missing jc config fails NOT_CONNECTED
    (exit 3); JC-side typed refusals (scope gaps, absent rule packs,
    refused boundaries, checker disagreement, malformed calendar input)
    surface as JC_FAILURE carrying the JC code (exit 4) — never a
    fabricated numeric answer. The F105 recon report is a statement-only
    document (no verdict field); the F106 calendar face answers
    out-of-range years with a structured UNKNOWN receipt carrying no
    date."""
    if not isinstance(args, dict):
        raise NotConnected("calc_family_params_invalid")
    client = _jc_client(config)
    matter_id = args.get("matter_id") or args.get("matterId") or "unscoped"
    if method == "calc.registry":
        return _jc(client.calc_families)
    if method == "calc.rule_base_recon":
        # 对拍是固定报告：任何额外键都由 JC 侧 typed 拒（recon_request_unknown_field）
        return _jc(lambda: client.rule_base_recon(
            {"matterId": str(matter_id),
             **{k: v for k, v in args.items()
                if k not in ("matter_id", "matterId")}}))
    if method in ("calc.calendar_account", "calc.calendar_due_date"):
        request = args.get("request")
        if not isinstance(request, dict):
            raise NotConnected("calc_calendar_request_required")
        runner = (client.calendar_account if method == "calc.calendar_account"
                  else client.calendar_due_date)
        return _jc(lambda: runner({"matterId": str(matter_id), **request}))
    slot = _CALC_FAMILY_SLOT_BY_METHOD[method]
    payload = args.get("input")
    if not isinstance(payload, dict):
        raise NotConnected("calc_family_input_required")
    if method == "calc.interest":
        # LPR 取数通道（施工波二轮·尾巴三件①）：包内利率回填仍在桥侧，
        # 计算照旧整包下沉 JC C01，取数凭据随计算书附加。
        payload, rate_channel = _lpr_pack_rate_channel(payload, config)
        result = _jc(lambda: client.calculate_family({
            "family": slot, "matterId": str(matter_id), "input": payload}))
        if rate_channel is not None and isinstance(result, dict):
            result["rate_channel"] = rate_channel
        return result
    return _jc(lambda: client.calculate_family({
        "family": slot, "matterId": str(matter_id), "input": payload}))

# F50 引用原文重锚定＋F51 引用前逐字核验（W2b-U13；06:F50/F51
# document-adapter，确定性解析红线）：产品侧 document_anchor 公开面。
# 锚＝原文逐字引文；定位唯一来源＝quote 在当前文本的精确子串搜索
# （零折叠零规范化、大小写不折叠、重叠命中计数）——禁偏移换算：登记
# span 只是溯源事实，locate 永不用它推算新位置，插入/删除后一律重搜；
# 零/多命中响应零位置字段（不以偏移强改）。F51 改动闸：逐字定位唯一
# 命中才 PROCEED（span＋proposed_text，宿主原生应用；不落 CAS/版本，
# 修订线属 W2b-U14 不前造）；NOT_FOUND/AMBIGUOUS 拒自动修改并落人工
# 入口（quote＋拟改文＋具名理由，append-only 幂等）；不就近匹配＝模糊
# 匹配代码结构性缺席。无 replacement＝纯核验（引用呈现闸，NOT_FOUND
# 禁呈现）。配置键 anchor_state_root；错误码不携材料内容。
ANCHOR_METHODS = frozenset({
    "anchor.register", "anchor.locate", "anchor.gate_edit",
    "anchor.manual_queue", "anchor.read",
})

# E19 参考/经验/预测隔离（W2b-U27；07:E19 cases+jc，deps E15/E22＋04§1/
# §8）：经 P01 JCClient 同一钉定公开面消费 JC 用途分离核心
# （compiler_core.prediction_separation，schema jc-prediction-separation/1）。
# prediction.declare＝法院材料用途声明（九字段闭集；用途三闭集
# normative_reference|empirical_population|prediction_sample——声明面
# 结构性永不产出样本成员资格）；prediction.readiness＝目标法院预测
# readiness 审计（样本框显式 admittedRowIds admission；normative 材料
# 显式 admission 也拒；八维证据缺一即具名 missingScopes＋probability
# 恒 null——无模型不造概率，默认 50%/风险参数 1/法院统一胜率三类
# 编造形态 typed 拒）；prediction.retrieval_guard＝检索分盖
# 非胜率戳（塞进概率字段即 retrieval_score_used_as_win_rate 拒）。
# W4-U55 B4 段增 prediction.calibration_transfer＝时间/辖区迁移校准
# 计算框架真跑（合成出处闭集：synthetic_mechanism_demo 回执盖
# usableAsRealCalibrationEvidence=false——合成回执永不清除真实目标法院
# readiness 的迁移/校准两维证据；authorized_real_court_data 无非空
# authorizationRef 即 real_court_data_authorization_missing typed 拒，
# 裁决#8-12 授权族 fail-closed 不编造；回执 probability 恒 null）。
# cases 仓只读引用零改动（lcr 公开面检索分属 cases 域，本桥不造第二
# 权威）。config 复用 P01 同域键 jc_state_root/jc_import_path/
# jc_rule_roots；JC 侧 typed 拒绝以 JC_FAILURE携码（exit 4）回传。
PREDICTION_SEPARATION_METHODS = frozenset({
    "prediction.declare",
    "prediction.readiness",
    "prediction.retrieval_guard",
    "prediction.calibration_transfer",
})

# E20 VOI 和多解释实际支持（W2b-U53；07 E20 B2 段）：经 P01 JCClient
# 同一钉定公开面消费 JC 信息价值分析核心（compiler_core/voi_analysis，
# schema jc-voi-analysis/1）。jc.voi_analyze＝信息集分区/合法行动集/
# 概率效用成本输入闭集；概率永不作为请求输入——probabilitySource 只收
# E19 readiness 回执 ref（predictionKnown 必 true）＋checkpoint 面概率
# 回执 ref 两枚 owner=jc；readiness 缺口＝具名 unavailable 回执（值恒
# null，不造 0.5/风险参数 1/统一胜率——E19 同源编造扫描）；期望值精确
# 有理数。多解释分支沿 argument graph 公开出口实际转录（branchRefs
# owner=jc，E15 branch_projection 合同）。config 复用 P01 同域键
# jc_state_root/jc_import_path/jc_rule_roots；JC 侧 typed 拒以
# JC_FAILURE 携码（exit 4）回传。
# W4-U56 B4 段增 jc.checkpoint_line＝checkpoint 登记/校准证据绑定的生产
# 流水线（真实训练 checkpoint 文档＋评估文档互证 → probability-prediction
# 概率回执＋readiness 八维审计可消费的校准证据行；数据侧四维绝不产线
# 生产——真实法院数据属授权族 fail-closed；synthetic_mechanism_demo 回执
# 盖 usableForRealCasePrediction=false；无 checkpoint＝具名
# model_not_available 值恒 null；wholeCaseProof.provenByLine=false——
# 08§4 全案证明不由产线/CI/原子定理推）。
VOI_ANALYSIS_METHODS = frozenset({
    "jc.voi_analyze",
    "jc.checkpoint_line",
})

# F93 SKILL.md 通道三执行语义（W3-U16；06:F93「SKILL.md 通道+三种执行语义
# （聊天注入/实例化 review/调用计算器）」＋台账「三语义真实，禁无必要
# DAG 引擎」）：产品面 skill_semantics（SKILL 通道唯一产品执行面；UI 仅
# 调用/展示）。skill.read＝来源解析（id 规则同上游原生通道，全文 sha256
# 溯源）；skill.review_instantiate＝列模板恰一块 → 既有 harness
# review_batch_create＋review_columns_define（F25/F82 底座，零第二列权
# 威）；skill.calculate＝计算步骤块恰一块 → 既有 calc.* 五族槽位（P01
# JCClient 同一钉定公开面；JC typed 拒绝 JC_FAILURE 携码 exit 4 原样上
# 浮，绝不造数）。无图无引擎无编排（导入闭集 AST 钉定——禁无必要 DAG）。
# config：instantiate 复用 harness_* 同域键；calculate 复用 P01 同域键
# jc_state_root/jc_import_path/jc_rule_roots。
# RE-12 对拍 T9（B15/B16 等量）技能轮工具白名单：辖内＝技能可声明的工具
# 族方法并集（kb/manual/statute/web/citation/material/docexport/export
# 八族，与 preset 工具面声明域同界）。skill.route.decide 下发本轮 loaded
# 技能声明工具并集（allowed_tools），宿主经 config["skill_tool_policy"]
# 把并集交回 call() 漏斗逐调用把关——未授权工具族方法调用具名拒
# f98_tool_not_allowed:*（竞品 /active tool policy/ 语义等量，自家具名
# 码）；键形坏＝f98_tool_policy_invalid（fail-closed）。零触发/非技能轮
# 不设键＝不设防（B49 空态回合照常执行）。基础设施面（路由/守门/
# harness/JC/case 等非工具族）不入辖。
SKILL_TOOL_GOVERNED_METHODS = frozenset(
    KB_METHODS | MANUAL_METHODS | STATUTE_METHODS | WEB_FALLBACK_METHODS
    | CITATION_METHODS | MATERIAL_PARSE_METHODS | DOC_EXPORT_METHODS
    | EXCEL_EXPORT_METHODS)

SKILL_METHODS = frozenset({
    "skill.read", "skill.review_instantiate", "skill.calculate",
})

# F96 技能执行合同守门（W3-U18；06:F96「技能执行合同+验收格式（fail-
# closed 门禁/证据四态/时点门禁/法源登记表/自带 evals）」＋台账「技能自带
# 证据/法源/时点/失败合同和 evals 真实守门；未核不签 PASS」＋08§3 引证
# 矩阵「测试绿≠内容通过」同构）：产品面 skill_gate——SKILL.md 恰一块
# lvyin-skill-contract 合同 → validate（闭集校验）/run（自带 evals 经既有
# skill.calculate/skill.review_institute/statute.citation_gate 真跑＋
# sources 经 statute.resolve 逐条真核验 → 回执 PASS|NOT_PASS）/verify_
# receipt（四态裁决：无回执=UNVERIFIED 不签 PASS；技能字节变=STALE 不签
# PASS）。config：evals 复用 harness/jc/codices 同域键（无新增配置面）。
SKILL_GATE_METHODS = frozenset({
    "skill.gate.validate", "skill.gate.run", "skill.gate.verify_receipt",
})

# F98 技能自动路由引擎（W4-U47；06:F98「触发评分/预算装填/activeLimit」
# ＋台账「显式调用优先，自动路由预算/activeLimit 可核，材料注入不借机启
# skill」＋preserved「v1 显式调用为主，自动路由随后」）：产品面
# skill_routing——skill.route.decide＝显式径（结构上先于评分返回，无条件
# 装填＝原生显式语义）/自动径（候选池逐字镜像 oc28 instructions.ts:76 原
# 生过滤器 description∧autoinvoke!==false；确定性整数触发评分带具名评分
# 依据 ref；合格数>activeLimit＝typed 拒不静默裁剪；预算按序装填、装不
# 下具名 deferred 零静默丢弃）；materials 绝不入评分器（F27 同频扫描，
# 家族命中 quarantine 留痕＝注入内容含触发词不引发自动路由）；每次路由
# 恰一决策留痕（零内容：query 只入 sha；digest 复核可审计可重放）。
# skill.route.log＝留痕读取（逐条 digest 复核，篡改 typed 拒）。候选与
# 投影唯一来源＝既有 F94 目录公开面 skill.catalog.read（零第二目录权
# 威）。config：skill_routing_state_root（留痕根）＋skill_catalog_state_
# root（F94 同域键，无新增配置语义）。
SKILL_ROUTING_METHODS = frozenset({
    "skill.route.decide", "skill.route.log",
})

# F99 技能市场双边生态（W5-U09；06:V7-99「创作者/审核/分发/排行流程采用
# 后真生效，恶意包不能入活动目录」；owner=product；UI_HOST_OR_NEW_
# PRODUCT＝发行商业新义务独立模块，不冒已有业务入口）：产品面
# skill_marketplace——创作者 submit（F95 预检收件，结构性无自动过审出
# 口）→审核 review_decide（fail-closed 全清单：脚本零容忍＋F27 注入扫
# 描＋F96 合同 validate；未过审具名 findings 绝不落入活动目录）→分发
# adopt（真实决定引用 decision_ref.review_id 必须解析到本账 approved 行；
# 市场目录树按采用事件重放提交包真实字节→确定性 bundle 经 F94 bundle
# 源真安装到 public 广场活动面）→排行 rankings（本地真实采用事件派生；
# 合成服务面 synthetic_local，真实商业排行服务随 v2 商业化补——§6.1 裁
# 决#13-19）＋付费墙 purchase/entitlement（合成服务面；金额整数分禁浮
# 点；price>0 未购=adopt typed 拒 f99_paywall_required）＋list 审计投
# 影。config：skill_marketplace_state_root（本面）＋skill_catalog_state_
# root（F94 同域键 adopt 安装目标）。
SKILL_MARKETPLACE_METHODS = frozenset({
    "market.submit", "market.review_decide", "market.adopt",
    "market.rankings", "market.purchase", "market.entitlement",
    "market.list",
})
# F101 agent/skill-builder（W5-U10；06:V7-101「自建skill/agent生成候选，
# 经预检和用户采用再执行，无自动扩权」＋17 卡「不创第二Agent loop」＋
# source_rationale「生态成熟后的元层」——本面＝候选/预检/采用合同面，不
# 建运行时新执行通道）：产品面 skill_builder。skill.builder.propose＝候
# 选生成对话轮入账（首轮必须 user；合成候选注入＝结构断言离线可跑，真
# 实模型轮次为对话层增强路径非门）；skill.builder.precheck＝预检（skill
# 复用既有 F96 skill.gate.validate 零第二合同权威；agent 无自动扩权闸
# ——permissions 只准 ask/deny 收窄，allow 规则 typed 拒）；
# skill.builder.adopt＝用户采用（adoption.by 逐字 "user"，非用户通道
# f101_adopt_requires_user；skill 经既有 F95 skill.zip.install 分发链真
# 安装零第二目录权威；agent 声明物化零运行时零 loop）；skill.builder.
# read＝真实回读（逐条 digest 复核）。红线：候选态永不直执行——本面零
# 执行方法零执行面引用（AST/字面量钉定），执行唯一通道＝F96 门禁对已安
# 装技能。config：skill_builder_state_root（留痕根）。
SKILL_BUILDER_METHODS = frozenset({
    "skill.builder.propose", "skill.builder.precheck",
    "skill.builder.adopt", "skill.builder.read",
})

# RE-21 增补·技能安装安全层（2026-10-30；规格=docs/RE规格库/RE-21-技能
# 安装-增补-安全层.md，MingJuris 737ef85 机制净室零复制）：声明式包
# （skill.json+sha256）安全安装链——清单九必填字段闭集一次全报（拒改不
# 修复）/安装+加载双点 SHA-256（入口不符=拒装零残留；加载重验磁盘被改
# =拒载，F96 STALE 同构）/七信号装前内容扫描（warnings 随包 traveling，
# 非空⇒enabled=0+告知；shell 内容未声明 shell 权限=具名缺口警告）/许可
# 证三闸（来源登记逐源钉 license_status；restricted/unknown 不内置、非
# compatible 不装、connector 不当技能跑——G6 连接器名单只留档不接线）/
# 版本层布局 packages/<id>/<version>/（同版本替换+多版本并存）/卸载不
# 删行（安装史留档+删目录前 install_path 包根内校验）。zip 边界唯一权威
# =既有 F95 precheck（复用不复制），另叠安全层三上限 5MB/20MB/200 文件。
# 通道归属（RE-21 增补 §3.0 裁定）：catzip 第 1 轮面维持既有装卸不进入
# 本链；catzip 已装 user 技能迁版本层=待主控。config：skill_security_
# state_root（本面）＋skill_security_app_version（可选，缺省=版本未知
# 跳过兼容检查）。六命令=skill.secure.inspect/install/list/read/
# set_active/uninstall。
SKILL_SECURITY_METHODS = frozenset({
    "skill.secure.inspect", "skill.secure.install", "skill.secure.list",
    "skill.secure.read", "skill.secure.set_active",
    "skill.secure.uninstall",
})

def _voi_analysis_call(method, args, config):
    """E20 VOI bridge (W2b-U53): dispatch through the pinned P01 JCClient
    surface only. Unknown methods never reach the VOI core; missing jc
    config fails NOT_CONNECTED (exit 3); JC-side typed refusals (closed
    set, non-minor payoffs, placeholder probabilities) surface as
    JC_FAILURE carrying the JC code (exit 4).

    The JC artifact resolver is process-local by design, so the two
    probability-evidence receipts are (re)built inside THIS call on the
    SAME client: readiness is the E19 readiness request payload — really
    run through client.prediction_readiness (its receipt is registered
    owner=jc, named gaps stay named); checkpointProbability is the
    checkpoint-face probability receipt payload the caller transcribed
    from the checkpoint face (kind/checkpointId/perStateProbabilities
    are re-validated by the VOI core; with no checkpoint the caller
    cannot supply one and a complete-evidence call is refused named
    voi_checkpoint_receipt_required — never a fabricated number, never a
    silent unavailable)."""
    if not isinstance(args, dict):
        raise NotConnected("voi_analysis_params_invalid")
    client = _jc_client(config)
    matter_id = args.get("matter_id") or args.get("matterId") or "unscoped"
    if method == "jc.checkpoint_line":
        # W4-U56 B4 段：产线请求原样透传（checkpoint/evaluation/
        # worldStates/perStateProbabilities/boundEvidence/dataProvenance
        # 闭集由 JC 核心校验）；JC typed 拒（闭集/泄漏/授权缺一/编造
        # 形态）以 JC_FAILURE 携码（exit 4）原样上浮，绝不造数。
        payload = args.get("request") if isinstance(
            args.get("request"), dict) else {}
        return _jc(lambda: client.checkpoint_line(
            {"matterId": str(matter_id), **payload}))
    request = args.get("request") if isinstance(args.get("request"), dict) else {}
    request = {key: value for key, value in request.items()
               if key != "matterId"}
    readiness = args.get("readiness")
    if not isinstance(readiness, dict):
        raise NotConnected("voi_readiness_payload_required")
    checkpoint = args.get("checkpointProbability")
    if checkpoint is not None and not isinstance(checkpoint, dict):
        raise NotConnected("voi_checkpoint_payload_invalid")

    def _run():
        ready = client.prediction_readiness({
            "matterId": str(matter_id), **readiness})
        if ready.get("predictionKnown") is True and checkpoint is None:
            # 证据齐全但没有 checkpoint 概率回执＝无法算 VOI——具名拒，
            # 不静默 unavailable 也不造数。
            raise JCMethodFailure("voi_checkpoint_receipt_required")
        checkpoint_ref = None
        if checkpoint is not None:
            checkpoint_ref = client._register_json(
                "probability-prediction", checkpoint, scope=str(matter_id))
        return client.voi_analyze({
            "matterId": str(matter_id), **request,
            "probabilitySource": {
                "readinessRef": ready["readinessRef"],
                "checkpointPredictionRef": (
                    client._wire_ref(checkpoint_ref, matter_id=str(matter_id))
                    if checkpoint_ref is not None else {"owner": "jc"}),
            }})
    return _jc(_run)

def _cash_contract_call(method, args, config):
    """E16 cash-contract bridge (W2b-U51): dispatch through the pinned
    P01 JCClient surface only. Unknown methods never reach the cash face;
    missing jc config fails NOT_CONNECTED (exit 3); JC-side typed refusals
    (same-source duplicates, transfer-as-second-source, composition
    mixing, float inputs, allocation caps) surface as JC_FAILURE carrying
    the JC code (exit 4) — never a fabricated number. Every balance
    answer carries the full five-column net vector; the receipt refs
    (owner=jc + sha256) are what the harness cash ledger rows pin."""
    if not isinstance(args, dict):
        raise NotConnected("cash_contract_params_invalid")
    matter_id = args.get("matter_id") or args.get("matterId") or "unscoped"
    if method == "cash.balance":
        events = args.get("events") or {}
        if not isinstance(events, dict):
            raise NotConnected("cash_balance_input_required")
        client = _jc_client(config)
        return _jc(lambda: client.cash_balance({
            "matterId": str(matter_id), **events}))
    payload = args.get("request") or args.get("events") or {}
    if not isinstance(payload, dict) or not payload:
        raise NotConnected("cash_allocate_input_required")
    client = _jc_client(config)
    return _jc(lambda: client.cash_allocate({
        "matterId": str(matter_id), **payload}))

# E18 策略 basis 评估消费口（W2b-U52；07 E18 harness+jc）：经 P01
# JCClient 同一钉定公开面消费 JC 三门评估核心（compiler_core/
# strategy_basis，schema jc-strategy-basis-sheet/1）。jc.strategy_evaluate
# ＝三门（事实/法律/策略）分别判定＋硬约束逐条，overall 由 AND 推导
# 不收请求携带的合并/总分字段（携带即 strategy_combined_verdict_refused
# typed 拒），回执经 _register_json 登记 strategyBasisRef owner=jc
# sha256——harness 策略账 jcEvaluationRef 的合法来源（harness 只转录
# 不制造）。config 复用 P01 同域键 jc_state_root/jc_import_path/
# jc_rule_roots；JC 侧 typed 拒绝以 JC_FAILURE 携码（exit 4）回传。
STRATEGY_BASIS_JC_METHODS = frozenset({
    "jc.strategy_evaluate",
})

def _strategy_basis_jc_call(method, args, config):
    """E18 strategy-basis bridge (W2b-U52): dispatch through the pinned
    P01 JCClient surface only. Unknown methods never reach the evaluation
    core; missing jc config fails NOT_CONNECTED (exit 3); JC-side typed
    refusals (gate missing / combined verdict / constraint coverage)
    surface as JC_FAILURE carrying the JC code (exit 4)."""
    if not isinstance(args, dict):
        raise NotConnected("strategy_basis_params_invalid")
    client = _jc_client(config)
    matter_id = args.get("matter_id") or args.get("matterId") or "unscoped"
    payload = args.get("request") if isinstance(args.get("request"), dict) else args
    # 原样透传（仅剥 matterId，由 client 回填）：闭集外/总分字段不在桥上
    # 洗白——strategy_combined_verdict_refused 等具名拒必须在 JC 面成立。
    payload = {key: value for key, value in payload.items()
               if key != "matterId"}
    if not payload:
        raise NotConnected("strategy_basis_input_required")
    return _jc(lambda: client.strategy_evaluate({
        "matterId": str(matter_id), **payload}))

def _prediction_separation_call(method, args, config):
    """E19 use-separation bridge (W2b-U27): dispatch through the pinned
    P01 JCClient surface only. Unknown methods never reach the separation
    core; missing jc config fails NOT_CONNECTED (exit 3); JC-side typed
    refusals (closed-set, use-conflict, placeholder, win-rate misuse)
    surface as JC_FAILURE carrying the JC code (exit 4). The receipts
    never carry a probability — an actual probability stays on the
    checkpoint face with its named model_not_available absence."""
    if not isinstance(args, dict):
        raise NotConnected("prediction_separation_params_invalid")
    client = _jc_client(config)
    matter_id = args.get("matter_id") or args.get("matterId") or "unscoped"
    if method == "prediction.declare":
        return _jc(lambda: client.declare_reference_uses({
            "matterId": str(matter_id),
            "records": args.get("records")}))
    if method == "prediction.readiness":
        payload = args.get("request") or {}
        if not isinstance(payload, dict):
            raise NotConnected("prediction_readiness_input_required")
        return _jc(lambda: client.prediction_readiness({
            "matterId": str(matter_id), **payload}))
    if method == "prediction.calibration_transfer":
        payload = args.get("request") or {}
        if not isinstance(payload, dict):
            raise NotConnected("prediction_calibration_input_required")
        return _jc(lambda: client.prediction_calibration_transfer({
            "matterId": str(matter_id), **payload}))
    payload = args.get("request") if isinstance(args.get("request"), dict) else args
    payload = {key: value for key, value in payload.items()
               if key in ("hits", "datasetVersion", "indexVersion")}
    if not isinstance(payload.get("hits"), (list, tuple)):
        raise NotConnected("prediction_guard_input_required")
    return _jc(lambda: client.retrieval_score_guard({
        "matterId": str(matter_id), **payload}))

def _execute(argv, env, timeout):
    # Module-level seam: unit tests substitute this instead of spawning.
    return subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", env=env, timeout=timeout)

def _harness_goal(method, args, config):
    return _harness_provider_entry(method, args, config, flag="goal-json", surface="goal")


def _harness_provider_entry(method, args, config, *, flag: str, surface: str):
    """Closed public_entry provider dispatch shared by the goal (E07) and
    schedule (F118) envelopes. Unknown/unconfigured fails NotConnected; ledger
    errors surface as HarnessCommandError with the typed UnitsError code."""
    entry = config.get("harness_public_entry")
    if not entry:
        raise NotConnected("harness_public_entry_not_configured")
    target = config.get("harness_target")
    if not target:
        raise NotConnected("harness_target_not_configured")
    env = {k: v for k, v in os.environ.items()}
    if config.get("harness_state_root"):
        env["LH_LEGAL_STATE_ROOT"] = str(config["harness_state_root"])
    if config.get("harness_service_registration"):
        env["LH_OPENCODE_SERVICE_REGISTRATION"] = str(config["harness_service_registration"])
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", prefix=f"{surface}-json-", delete=False)
    try:
        json.dump({"method": method, "params": args}, handle, ensure_ascii=False)
        handle.close()
        argv = [config.get("harness_python") or sys.executable, "-X", "utf8",
                str(entry), f"--{flag}", handle.name, "--target", target]
        try:
            proc = _execute(argv, env, float(config.get("harness_timeout", 60)))
        except subprocess.TimeoutExpired:
            # Ledger writes are CommandKey-idempotent: retrying the SAME
            # request id replays safely; blind retry with a NEW id does not.
            raise HarnessCommandError("harness_entry_timeout") from None
        try:
            payload = json.loads(proc.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # stderr is never surfaced: it may carry case material.
            raise HarnessCommandError("harness_entry_protocol_invalid") from None
        if proc.returncode == 0 and isinstance(payload, dict) \
                and payload.get("surface") == surface:
            return payload.get("result")
        code = payload.get("error") if isinstance(payload, dict) else None
        raise HarnessCommandError(code or "harness_entry_failed")
    finally:
        os.unlink(handle.name)

def _harness_service_entry(args, config, *, flag: str, surface: str):
    """P02 ApplicationService envelopes (--prepare-formal-json /
    --commit-formal-json; F142 W5-U13): the request dict rides as-is — the
    field-closed contract lives harness-side (service.py). The response has
    no surface envelope; exit 0 carries the terminal/NEEDS_* status dict,
    exit 1 carries a FAIL envelope. Unknown/unconfigured fails NotConnected;
    non-JSON stdout (e.g. an untyped FinalizationError traceback) surfaces
    as harness_entry_protocol_invalid, never a fake success."""
    entry = config.get("harness_public_entry")
    if not entry:
        raise NotConnected("harness_public_entry_not_configured")
    target = config.get("harness_target")
    if not target:
        raise NotConnected("harness_target_not_configured")
    env = {k: v for k, v in os.environ.items()}
    if config.get("harness_state_root"):
        env["LH_LEGAL_STATE_ROOT"] = str(config["harness_state_root"])
    if config.get("harness_service_registration"):
        env["LH_OPENCODE_SERVICE_REGISTRATION"] = str(config["harness_service_registration"])
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", prefix=f"{surface}-json-",
        delete=False)
    try:
        json.dump(args, handle, ensure_ascii=False)
        handle.close()
        argv = [config.get("harness_python") or sys.executable, "-X", "utf8",
                str(entry), f"--{flag}", handle.name, "--target", target]
        try:
            proc = _execute(argv, env, float(config.get("harness_timeout", 60)))
        except subprocess.TimeoutExpired:
            raise HarnessCommandError("harness_entry_timeout") from None
        try:
            payload = json.loads(proc.stdout)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # stderr is never surfaced: it may carry case material.
            raise HarnessCommandError("harness_entry_protocol_invalid") from None
        if proc.returncode == 0 and isinstance(payload, dict) \
                and payload.get("status") != "FAIL":
            return payload
        code = payload.get("error") if isinstance(payload, dict) else None
        raise HarnessCommandError(code or "harness_entry_failed")
    finally:
        os.unlink(handle.name)


class CaseProviderError(RuntimeError):
    """Named error from the frozen case public face; the provider code is preserved."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

# Authority 14-Python入口与施工接线.md §1: the old /v1 HTTP face does not
# automatically equal the frozen v4 provider contract; prefer the existing
# CasePublicService public face (P08) bound to dataset/indexVersion.
_CASE_PUBLIC_METHODS = ("case.search", "case.read", "case.stats", "case.comparison")

def _call_case_public(method, args, config):
    # F68 检索顺序宪法（W2b-U57）：梯子/回执唯一权威在 cases 公开面，
    # 桥只强制携带并审计回执，不复制梯子常量（防漂移）。
    import_path = config.get("cases_import_path")
    if import_path:
        import_path = str(import_path)  # 边界归一：config 可能来自进程内 dict（Path 对象）
        if not os.path.isdir(import_path):
            raise NotConnected("cases_import_path_missing:" + import_path)
        if import_path not in sys.path:
            sys.path.insert(0, import_path)
    from lcr.public_facade import CasePublicService, CaseBridgeError
    try:
        from lcr.public_facade import (SCHEMA_RETRIEVAL_ORDER, RETRIEVAL_CONSTITUTION,
                                       RETRIEVAL_SOURCES, RETRIEVAL_UNTRIED_REASONS)
    except ImportError as exc:
        # F68：提供方先于顺序宪法（钉定基检出即如此）——桥绝不静默放行无回执检索。
        raise NotConnected("cases_public_facade_missing_retrieval_order:" + str(exc)) from None
    dataset_pin = config["cases_dataset_version"]
    index_pin = config.get("cases_index_version")  # None = text-only pin; the public
    body = dict(args)                              # face echoes the active index then.
    for key, pin in (("datasetVersion", dataset_pin), ("indexVersion", index_pin)):
        if body.get(key, pin) != pin:
            raise ValueError("cases_binding_conflict:" + key)
        body[key] = pin
    if method == "case.search":
        # 产品面强制顺序账：execution 恒携带，调用方不可退订；调用方若塞 order
        # 重排，由公开面 search_order_violation 具名拒后原样透传。
        execution = body.get("execution")
        body["execution"] = dict(execution) if isinstance(execution, dict) else {}
    # F71 混合检索（W4-U02）：请求 opt-in execution.hybrid 时，提供方必须支持
    # 混合面且响应必须带 hybrid 回执。预扩展检出（无 SCHEMA_HYBRID 的旧提供方）
    # →具名拒不静默降级为普通检索；常量唯一权威仍在提供方（桥只 import 使用）。
    hybrid_requested = (method == "case.search"
                        and body["execution"].get("hybrid") is not None
                        and body["execution"].get("hybrid") is not False)
    schema_hybrid = None
    if hybrid_requested:
        try:
            from lcr.public_facade import SCHEMA_HYBRID
            from lcr.hybrid_search import HYBRID_CHANNELS
        except ImportError as exc:
            raise NotConnected(
                "cases_public_facade_missing_hybrid_receipt:" + str(exc)) from None
        schema_hybrid = (SCHEMA_HYBRID, HYBRID_CHANNELS)
    svc = CasePublicService(config["cases_root"])
    try:
        result = {"case.search": svc.search, "case.read": svc.read,
                  "case.stats": svc.stats, "case.comparison": svc.comparison}[method](body)
    except CaseBridgeError as exc:
        raise CaseProviderError(exc.code, str(exc)) from exc
    if method == "case.search":
        _audit_retrieval_order(result, SCHEMA_RETRIEVAL_ORDER, RETRIEVAL_CONSTITUTION,
                               RETRIEVAL_SOURCES, RETRIEVAL_UNTRIED_REASONS,
                               bool(body["execution"].get("requireExhaustive", False)))
        if hybrid_requested:
            _audit_hybrid_receipt(result, schema_hybrid[0], schema_hybrid[1])
    return result

def _audit_retrieval_order(result, schema, constitution, ladder, untried_reasons,
                           require_exhaustive):
    """F68 桥级回执审计：缺回执/重排/本地未试/理由出闭集/回声不一致一律具名拒。"""
    def reject(code, detail):
        raise CaseProviderError(code, detail)
    receipt = result.get("retrievalOrder") if isinstance(result, dict) else None
    if not isinstance(receipt, dict):
        reject("case_search_order_receipt_missing",
               "case.search returned hits without the retrieval-order ledger")
    if receipt.get("schema") != schema:
        reject("case_search_order_receipt_invalid",
               "retrievalOrder.schema=%r want %r" % (receipt.get("schema"), schema))
    if receipt.get("constitution") != constitution:
        reject("case_search_order_receipt_invalid",
               "retrievalOrder.constitution=%r want %r" % (receipt.get("constitution"), constitution))
    sources = receipt.get("sources")
    if not isinstance(sources, list) or [s.get("sourceId") for s in sources] != [s["sourceId"] for s in ladder]:
        reject("case_search_order_receipt_invalid",
               "receipt ladder %r does not match the constitution order" % (sources,))
    local = sources[0]
    if local.get("tier") != "local_free" or local.get("status") != "tried" or local.get("reason") is not None:
        reject("case_search_order_receipt_invalid",
               "local free source must run first and be tried; got %r" % local)
    untried, failed = [], []
    for entry in sources[1:]:
        if entry.get("feeRequired") is not True:
            reject("case_search_order_receipt_invalid",
                   "paid entry without feeRequired: %r" % entry)
        status, reason = entry.get("status"), entry.get("reason")
        if status == "tried":
            if reason is not None:
                reject("case_search_order_receipt_invalid",
                       "tried entry carries a reason: %r" % entry)
            continue
        if status not in ("failed", "skipped"):
            reject("case_search_order_receipt_invalid",
                   "paid status outside tried/failed/skipped: %r" % entry)
        if reason not in untried_reasons:
            reject("case_search_order_receipt_invalid",
                   "untried reason outside the closed set: %r" % (reason,))
        untried.append(entry["sourceId"])
        if status == "failed":
            failed.append(entry["sourceId"])
    if require_exhaustive and not receipt.get("hitsExhaustive"):
        reject("case_search_order_receipt_invalid",
               "requireExhaustive echoed but receipt claims hitsExhaustive=%r"
               % receipt.get("hitsExhaustive"))
    hits_empty = isinstance(result.get("hits"), list) and not result["hits"]
    want_zero_authoritative = bool(not untried and not failed and hits_empty)
    if receipt.get("zeroHitAuthoritative") != want_zero_authoritative:
        reject("case_search_order_receipt_invalid",
               "zeroHitAuthoritative=%r does not match the audited receipt state (want %r)"
               % (receipt.get("zeroHitAuthoritative"), want_zero_authoritative))

def _audit_hybrid_receipt(result, schema_hybrid, hybrid_channels):
    """F71 桥级混合回执审计（W4-U02）：请求 hybrid 时响应必须携真实混合回执。

    缺回执/schema 不符/通道缺失或未实跑/盖戳缺失/外部全库 UNKNOWN 缺失
    一律具名拒——桥不吞混合检索的法律来源边界。
    """
    def reject(code, detail):
        raise CaseProviderError(code, detail)
    receipt = result.get("hybrid") if isinstance(result, dict) else None
    if not isinstance(receipt, dict):
        reject("case_search_hybrid_receipt_missing",
               "case.search answered a hybrid request without the hybrid receipt")
    if receipt.get("schema") != schema_hybrid:
        reject("case_search_hybrid_receipt_invalid",
               "hybrid.schema=%r want %r" % (receipt.get("schema"), schema_hybrid))
    identity = receipt.get("hybridIndexVersion")
    if not isinstance(identity, str) or not identity.startswith("hybrid:"):
        reject("case_search_hybrid_receipt_invalid",
               "hybridIndexVersion=%r is not a content-addressed hybrid identity"
               % (identity,))
    channels = receipt.get("channels")
    if not isinstance(channels, list) or \
            [c.get("channelId") for c in channels] != [c["channelId"] for c in hybrid_channels]:
        reject("case_search_hybrid_receipt_invalid",
               "hybrid channels %r do not match the provider channel set"
               % (channels,))
    for entry in channels:
        if entry.get("tried") is not True:
            reject("case_search_hybrid_receipt_invalid",
                   "channel %r did not really run" % entry.get("channelId"))
    stamps = receipt.get("scoreSemantics")
    if not isinstance(stamps, dict) or stamps.get("retrievalScoreIsNotWinRate") is not True \
            or stamps.get("notAPopulationSample") is not True or stamps.get("probability") is not None:
        reject("case_search_hybrid_receipt_invalid",
               "relevance-is-not-probability stamps missing or altered: %r" % (stamps,))
    external = receipt.get("externalCorpus")
    if not isinstance(external, dict) or external.get("status") != "UNKNOWN" \
            or external.get("value") is not None:
        # 裁决#8-12：未授权外部全库＝UNKNOWN 值 None 非 0；0 会冒充已测全库。
        reject("case_search_hybrid_receipt_invalid",
               "externalCorpus must stay UNKNOWN with value None (negative-test-first): %r"
               % (external,))
    coverage = receipt.get("coverage")
    if not isinstance(coverage, dict) or not isinstance(coverage.get("documents"), int) \
            or coverage.get("documents") < 1 or not isinstance(coverage.get("months"), int) \
            or coverage.get("months") < 1:
        reject("case_search_hybrid_receipt_invalid",
               "coverage must carry the honest month/document denominators: %r" % (coverage,))


class JCMethodFailure(RuntimeError):
    pass

JC_METHODS = (
    "jc.case_bundle",
    "jc.evaluate",
    "jc.read_run",
    "jc.horn_subject_state",
    "jc.business_delivery_documents",
    "jc.verify_business_delivery",
)

def _jc_client(config):
    if not config.get("jc_state_root"):
        raise NotConnected("jc_state_root_not_configured")
    import_path = config.get("jc_import_path")
    if import_path:
        if not os.path.isdir(import_path):
            raise NotConnected("jc_import_path_missing:"+str(import_path))
        if import_path not in sys.path:
            sys.path.insert(0, import_path)
    try:
        from compiler_core.client import create_local_client
    except ImportError as exc:
        raise NotConnected("compiler_core_not_importable:"+str(exc)) from None
    return create_local_client(config["jc_state_root"], tuple(config.get("jc_rule_roots") or ()))

def _jc(fn):
    try:
        return fn()
    except (NotConnected, JCMethodFailure):
        raise
    except Exception as exc:
        code = getattr(exc, "code", None) or type(exc).__name__
        raise JCMethodFailure(f"jc_error:{code}:{type(exc).__name__}:{exc}") from exc

def call(method, args, config):
    # E23（W3-U19）具名缺省面：persona 为可选件（persona 仓缺失时系统仍
    # 完整可用；persona 命名空间待登记，绝不造消费者），Observer 建议
    # 待用户（裁决#7：不启用）——两者任何方法无条件具名拒，任何配置
    # 都不能启用。
    if method.startswith("persona."):
        raise NotConnected("persona_optional_component_not_wired")
    if method.startswith("observer."):
        raise NotConnected("observer_not_enabled_pending_user_decision")
    # RE-12 对拍 T9：技能轮工具白名单（宿主经 F98 decide allowed_tools
    # 下发回设；辖内族与语义见 SKILL_TOOL_GOVERNED_METHODS 注）。
    tool_policy = config.get("skill_tool_policy")
    if tool_policy is not None:
        allowed_tools = tool_policy.get("allowed_tools") \
            if isinstance(tool_policy, dict) else None
        if not isinstance(tool_policy, dict) \
                or set(tool_policy) != {"allowed_tools"} \
                or not isinstance(allowed_tools, list) \
                or not all(isinstance(t, str) and t
                           for t in allowed_tools):
            raise NotConnected("f98_tool_policy_invalid")
        if method in SKILL_TOOL_GOVERNED_METHODS \
                and method not in set(allowed_tools):
            raise NotConnected("f98_tool_not_allowed:" + method)
    if method in _CASE_PUBLIC_METHODS and config.get("cases_root") and config.get("cases_dataset_version"):
        return _call_case_public(method, args, config)
    if method == "case.search":
        if config.get("cases_contract") != "lcr/1" or not config.get("cases_url"):
            raise NotConnected("cases_lcr1_http_not_configured;v4_provider_requires_separate_binding")
        # F30 airplane gate (W3-U05): remote retriever refused BEFORE any
        # connection attempt while the switch is armed; loopback stays alive.
        from airplane_mode import enforce_bridge_egress
        enforce_bridge_egress(config, "case_retriever_http",
                              endpoint=config["cases_url"])
        from lcr.client import RetrieverClient
        return RetrieverClient(config["cases_url"]).search(args["query"], args.get("query_card"), args.get("limit",20))
    if method in JC_METHODS:
        client = _jc_client(config)
        if method == "jc.case_bundle":
            return _jc(lambda: client.local_case_bundle(**args).to_dict())
        if method == "jc.evaluate":
            bundle_args = dict(args.get("bundle") or {})
            if not bundle_args.get("case_id"):
                raise JCMethodFailure("jc_error:MISSING_CASE_ID:bundle.case_id is required")
            issue_queries = args.get("issue_queries", [])
            def _run():
                bundle = client.local_case_bundle(**bundle_args)
                return client.evaluate_harness_bundle(
                    bundle, case_id=bundle_args["case_id"], issue_queries=issue_queries)
            return _jc(_run)
        if method == "jc.read_run":
            return _jc(lambda: client.local_read_run(args["run_identity_ref"]))
        if method == "jc.horn_subject_state":
            return _jc(lambda: client.local_horn_subject_state(args["run_identity_ref"]))
        if method == "jc.business_delivery_documents":
            def _docs():
                docs = client.business_delivery_documents(
                    run_identity_ref=args["run_identity_ref"],
                    business_task_id=args["business_task_id"])
                return {name: b64encode(payload).decode("ascii") for name, payload in docs.items()}
            return _jc(_docs)
        if method == "jc.verify_business_delivery":
            def _verify():
                artifacts = {name: b64decode(payload) for name, payload in args["artifacts"].items()}
                return client.verify_business_delivery(
                    run_identity_ref=args["run_identity_ref"],
                    business_task_id=args["business_task_id"],
                    selected_input_ref=args["selected_input_ref"],
                    artifacts=artifacts)
            return _jc(_verify)
    if method in PREDICTION_SEPARATION_METHODS:
        return _prediction_separation_call(method, args, config)
    if method in VOI_ANALYSIS_METHODS:
        return _voi_analysis_call(method, args, config)
    if method in CASH_CONTRACT_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("cash_contract_params_invalid")
        return _cash_contract_call(method, args, config)
    if method in STRATEGY_BASIS_JC_METHODS:
        return _strategy_basis_jc_call(method, args, config)
    if method.startswith("jc."):
        raise NotConnected("jc_method_not_in_frozen_list:"+method+";see_JC_METHODS")
    if method in ("material.deidentify", "material.roundtrip",
                  "material.overlay_register", "material.overlay_apply",
                  "material.overlay_read", "material.overlay_list"):
        return _material_call(method, args, config)
    if method in MATERIAL_PARSE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("material_parse_params_invalid")
        return _material_parse_call(method, args, config)
    if method in OCR_PORTS_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("ocr_ports_params_invalid")
        return _ocr_ports_call(method, args, config)
    if method in OCR_BATCH_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("ocr_batch_params_invalid")
        return _ocr_batch_call(method, args, config)
    if method in STAMP_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("stamp_params_invalid")
        return _stamp_call(method, args, config)
    if method in READING_ORDER_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("reading_order_params_invalid")
        return _reading_order_call(method, args, config)
    if method in REVIEW_GATE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("review_gate_params_invalid")
        return _review_gate_call(method, args, config)
    if method in ATTACHMENT_GATE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("attachment_gate_params_invalid")
        return _attachment_gate_call(method, args, config)
    if method in REDACTION_PRESET_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("redaction_preset_params_invalid")
        return _redaction_preset_call(method, args, config)
    if method in EMS_EVIDENCE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("ems_evidence_params_invalid")
        return _ems_evidence_call(method, args, config)
    if method in ENTERPRISE_CONNECTOR_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("enterprise_connector_params_invalid")
        return _enterprise_connector_call(method, args, config)
    if method in COMMERCIAL_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("commercial_params_invalid")
        return _commercial_call(method, args, config)
    if method in ORG_ADMIN_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("org_admin_params_invalid")
        return _org_admin_call(method, args, config)
    if method in DOSSIER13_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("dossier13_params_invalid")
        return _dossier13_call(method, args, config)
    if method in WECHAT_COLLECTION_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("wechat_collection_params_invalid")
        return _wechat_collection_call(method, args, config)
    if method in COURT_CASE_LIBRARY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("caselib_args_invalid")
        return _court_case_library_call(method, args, config)
    if method in NUMBER_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("number_params_invalid")
        return _number_call(method, args, config)
    if method in INJECTION_DEFENSE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("injection_params_invalid")
        return _injection_call(method, args, config)
    if method in MCP_CONNECTOR_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("mcp_params_invalid")
        return _mcp_connector_call(method, args, config)
    if method in BUDGET_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("budget_params_invalid")
        return _budget_call(method, args, config)
    if method in CONVERSION_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("conversion_params_invalid")
        return _conversion_call(method, args, config)
    if method in PAPER_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("paper_params_invalid")
        return _paper_call(method, args, config)
    if method in ANCHOR_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("anchor_params_invalid")
        return _anchor_call(method, args, config)
    if method in REDLINE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("redline_params_invalid")
        return _redline_call(method, args, config)
    if method in DOCCOMPARE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("doccompare_params_invalid")
        return _doccompare_call(method, args, config)
    if method in DOC_EXPORT_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("docexport_params_invalid")
        return _docexport_call(method, args, config)
    if method in PROOFING_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("proofing_params_invalid")
        return _proofing_call(method, args, config)

    if method in EDITS_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("edits_params_invalid")
        return _edits_call(method, args, config)
    if method in WPS_HOST_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("wps_host_params_invalid")
        return _wps_host_call(method, args, config)
    if method in BACKUP_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("backup_params_invalid")
        return _backup_call(method, args, config)
    if method in WPS_SURFACE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("wps_surface_params_invalid")
        return _wps_surface_call(method, args, config)
    if method in AUTHOR_POLICY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("author_policy_params_invalid")
        from author_policy import author_policy_call, AuthorPolicyError
        try:
            return author_policy_call(method, args, config)
        except (NotConnected, HarnessCommandError):
            # 桥既有 typed 错误（未配置/账面失败）原样透传，不二次包裹。
            raise
        except AuthorPolicyError as exc:
            # typed f53_* 码透传，绝不携材料内容（同 document-adapter 基线）。
            raise NotConnected("author_policy_failed:" + str(exc)) from None
        except Exception as exc:
            raise NotConnected("author_policy_failed:"
                               + type(exc).__name__) from None
    if method in DASHBOARD_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("dashboard_params_invalid")
        from dashboard_projection import dashboard_call, DashboardProjectionError
        try:
            return dashboard_call(method, args, config)
        except (NotConnected, HarnessCommandError):
            # 桥既有 typed 错误（未配置/账面失败）原样透传，不二次包裹。
            raise
        except DashboardProjectionError as exc:
            # typed f115_*/f116_* 码透传，绝不携材料内容。
            raise NotConnected("dashboard_projection_failed:" + str(exc)) from None
        except Exception as exc:
            raise NotConnected("dashboard_projection_failed:"
                               + type(exc).__name__) from None
    if method in SKILL_CATALOG_METHODS or method in SKILL_ZIP_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("skill_catalog_params_invalid")
        from skill_catalog import catalog_call, SkillCatalogError
        try:
            return catalog_call(method, args, config)
        except SkillCatalogError as exc:
            # typed f94_*/f95_* 码透传，绝不携材料内容（document-adapter 基线）。
            raise NotConnected("skill_catalog_failed:" + str(exc)) from None
        except (NotConnected, HarnessCommandError):
            raise
        except Exception as exc:
            raise NotConnected("skill_catalog_failed:"
                               + type(exc).__name__) from None
    if method in SYNC_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("sync_params_invalid")
        from device_sync import device_sync_call
        return device_sync_call(method, args, config)
    if method in HARNESS_SYNC_KEYED_METHODS:
        # F126 密钥面：sync key 绝不进 JSON 请求文件/argv（F10 同构边界）
        # ——in-process owner API（封闭注册）直连，state root 由 config。
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        from device_sync import default_harness_call
        return default_harness_call(config)(method, args)
    if method in HARNESS_SYNC_READ_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="sync-json", surface="sync")
    if method in HARNESS_GOAL_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_goal(method, args, config)
    if method in HARNESS_STRATEGY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="strategybasis-json",
                                       surface="strategybasis")
    if method in HARNESS_VOI_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="voi-json",
                                       surface="voi")
    if method in HARNESS_RUN_LEDGER_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="runledger-json",
                                       surface="runledger")
    if method in HARNESS_TOOL_GOVERNANCE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="toolgov-json",
                                       surface="toolgov")
    if method in HARNESS_CASE_ANCHOR_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="caseanchor-json",
                                       surface="caseanchor")
    if method in CONFLICT_CHECK_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("conflict_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="conflict-json",
                                       surface="conflict")
    if method in HARNESS_SCHEDULE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="schedule-json", surface="schedule")
    if method in HARNESS_DASHBOARD_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="dashboard-json", surface="dashboard")
    if method in HARNESS_CASE_DOMAIN_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="casedomain-json", surface="casedomain")
    if method in HARNESS_COVER_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="cover-json", surface="cover")
    if method in HARNESS_MODULE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="module-json", surface="module")
    if method in HARNESS_CASE_PERMISSION_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="caseperm-json",
                                       surface="caseperm")
    if method in HARNESS_COLLAB_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="collab-json",
                                       surface="collab")
    if method in HARNESS_COLLABDOC_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="collabdoc-json",
                                       surface="collabdoc")
    if method in HARNESS_APPROVAL_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="approval-json",
                                       surface="approval")
    if method in HARNESS_FORMAL_LIFECYCLE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        # P02 ApplicationService envelopes: the request dict rides as-is
        # (field-closed contract lives harness-side; F142 W5-U13).
        flag = ("prepare-formal-json"
                if method == "harness.prepare_formal"
                else "commit-formal-json")
        return _harness_service_entry(args, config,
                                      flag=flag,
                                      surface="formallifecycle")
    if method in HARNESS_CHRONOLOGY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="chronology-json",
                                       surface="chronology")
    if method in CHRONOLOGY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("chronology_params_invalid")
        from chronology import chronology_call
        return chronology_call(method, args, config)
    if method in HARNESS_MATERIAL_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="materials-json", surface="materials")
    if method in HARNESS_BATCH_REVIEW_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="reviewbatch-json", surface="reviewbatch")
    if method in HARNESS_FORMAL_PROPOSAL_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="formalproposal-json", surface="formalproposal")
    if method in HARNESS_PATH_EVIDENCE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="pathevidence-json", surface="pathevidence")
    if method in HARNESS_TABULAR_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="reviewbatch-json", surface="reviewbatch")
    if method in HARNESS_REVIEW_OPS_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="reviewbatch-json", surface="reviewbatch")
    if method in HARNESS_EVIDENCE_ATTEMPT_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="evidenceattempt-json", surface="evidenceattempt")
    if method in HARNESS_TASK_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="tasks-json", surface="tasks")
    if method in HARNESS_LOOSE_DOC_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="loosedocs-json", surface="loosedocs")
    if method in HARNESS_MEMORY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="memory-json", surface="memory")
    if method in MEMORY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("memory_params_invalid")
        from case_memory import memory_call
        return memory_call(method, args, config)
    if method in HARNESS_CASH_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="cashcontract-json", surface="cashcontract")
    if method in HARNESS_SUBMISSION_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="submission-json",
                                       surface="submission")
    if method in HARNESS_CALENDAR_SYNC_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="calsync-json",
                                       surface="calsync")
    if method in HARNESS_EVIDENCE_CHAIN_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="evidencechain-json",
                                       surface="evidencechain")
    if method in EVIDENCECAT_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("evidencecat_params_invalid")
        from evidence_catalog import evidence_catalog_call, \
            EvidenceCatalogError
        try:
            return evidence_catalog_call(method, args, config)
        except EvidenceCatalogError as exc:
            # typed f119_* 码透传（错误码只带工程标识，绝不携材料内容）。
            raise NotConnected("evidencecat_failed:" + str(exc)) from None
    if method in CROSSEXAM_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("crossexam_params_invalid")
        from cross_exam import cross_exam_call, CrossExamError
        try:
            return cross_exam_call(method, args, config)
        except CrossExamError as exc:
            # typed crossexam_* 码透传（错误码只带工程标识，绝不携材料内容）。
            raise NotConnected("crossexam_failed:" + str(exc)) from None
    if method in HARNESS_EXPORT_LEDGER_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="exportledger-json",
                                       surface="exportledger")
    if method in TABULAR_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("tabular_params_invalid")
        from tabular_review import tabular_call
        return tabular_call(method, args, config)
    if method in TABULAR_REVIEW_OPS_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("tabular_review_ops_params_invalid")
        from tabular_review_ops import review_ops_call
        return review_ops_call(method, args, config)
    if method in REVIEW_CHAT_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("review_chat_params_invalid")
        from review_chat import review_chat_call
        return review_chat_call(method, args, config)
    if method in SUBSCRIPTION_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("subscription_params_invalid")
        from subscription_engine import (
            SubscriptionError, subscription_call)
        try:
            return subscription_call(method, args, config)
        except SubscriptionError as exc:
            # typed siwc_* 码透传（vault_failed 同法），零密钥材料。
            raise NotConnected("subscription_failed:" + str(exc)) from None
    if method in SKILL_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("skill_params_invalid")
        from skill_semantics import skill_call, SkillSemanticsError
        try:
            return skill_call(method, args, config)
        except SkillSemanticsError as exc:
            # typed f93_* 码透传（错误码只带工程标识，绝不携材料内容）。
            raise NotConnected("skill_failed:" + str(exc)) from None
    if method in SKILL_GATE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("skill_gate_params_invalid")
        from skill_gate import gate_call, SkillGateError
        try:
            return gate_call(method, args, config)
        except SkillGateError as exc:
            # typed f96_* 码透传（错误码只带工程标识，绝不携材料内容）。
            raise NotConnected("skill_gate_failed:" + str(exc)) from None
    if method in SKILL_ROUTING_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("skill_routing_params_invalid")
        from skill_routing import routing_call, SkillRoutingError
        try:
            return routing_call(method, args, config)
        except SkillRoutingError as exc:
            # typed f98_* 码透传（错误码只带工程标识，绝不携材料内容）。
            raise NotConnected("skill_routing_failed:" + str(exc)) from None
    if method in SKILL_MARKETPLACE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("skill_marketplace_params_invalid")
        from skill_marketplace import marketplace_call, SkillMarketplaceError
        try:
            return marketplace_call(method, args, config)
        except SkillMarketplaceError as exc:
            # typed f99_* 码透传（错误码只带工程标识，绝不携材料内容）。
            raise NotConnected("skill_marketplace_failed:" + str(exc)) from None
    if method in SKILL_BUILDER_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("skill_builder_params_invalid")
        from skill_builder import builder_call, SkillBuilderError
        try:
            return builder_call(method, args, config)
        except SkillBuilderError as exc:
            # typed f101_* 码透传（错误码只带工程标识，绝不携材料内容）。
            raise NotConnected("skill_builder_failed:" + str(exc)) from None
    if method in SKILL_SECURITY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("skill_security_params_invalid")
        from skill_security import security_call, SkillSecurityError
        try:
            return security_call(method, args, config)
        except SkillSecurityError as exc:
            # typed s21_* 码透传（含 F95 透传前缀；错误码只带工程标识，
            # 绝不携材料内容）。
            raise NotConnected("skill_security_failed:" + str(exc)) from None
    if method in VAULT_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("vault_params_invalid")
        from credential_vault import vault_call, VaultError
        try:
            return vault_call(method, args, config)
        except VaultError as exc:
            # typed vault_* 码透传＝缺解密不明文降级（F12），不二次包裹。
            raise NotConnected("vault_failed:" + str(exc)) from None
        except Exception as exc:
            raise NotConnected("vault_failed:" + type(exc).__name__) from None
    if method in ATREST_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("atrest_params_invalid")
        from atrest_key import atrest_key_call, AtrestKeyError
        try:
            return atrest_key_call(method, args, config)
        except AtrestKeyError as exc:
            # typed f10_*/vault_* 码透传（缺设施/未配置具名），零密钥字节。
            raise NotConnected("atrest_failed:" + str(exc)) from None
        except Exception as exc:
            raise NotConnected("atrest_failed:" + type(exc).__name__) from None
    if method in AUDIT_HMAC_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("audit_hmac_params_invalid")
        from audit_hmac import audit_hmac_call, AuditHmacError
        try:
            return audit_hmac_call(method, args, config)
        except AuditHmacError as exc:
            # typed audit_* 码透传（篡改/截断/重放/缺钥具名），材料不进码。
            raise NotConnected("audit_hmac_failed:" + str(exc)) from None
        except Exception as exc:
            raise NotConnected("audit_hmac_failed:"
                               + type(exc).__name__) from None
    if method in LICENSE_MANAGER_METHODS or method in LICENSE_VERIFY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("license_params_invalid")
        from license_verify import LicenseError
        try:
            if method in LICENSE_VERIFY_METHODS:
                from license_verify import license_verify_call
                return license_verify_call(method, args, config)
            from license_manager import license_manager_call
            return license_manager_call(method, args, config)
        except (NotConnected, HarnessCommandError):
            # 面内既有 typed 桥错（服务未配置/F30 拦截）原样透传，
            # 不二次包裹（author_policy 同式）。
            raise
        except LicenseError as exc:
            # typed license_* 码透传（验签/指纹/回拨/宽限/服务具名），
            # 零密钥字节零令牌原文。
            raise NotConnected("license_failed:" + str(exc)) from None
        except Exception as exc:
            raise NotConnected("license_failed:" + type(exc).__name__) from None
    if method in MFA_AUTH_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("mfa_params_invalid")
        from mfa_auth import mfa_auth_call, MfaAuthError
        try:
            return mfa_auth_call(method, args, config)
        except MfaAuthError as exc:
            # typed mfa_*/vault_* 码透传（错码/过期/重放/已消费/缺设施具
            # 名），材料与凭据内容永不进入错误码。
            raise NotConnected("mfa_failed:" + str(exc)) from None
        except Exception as exc:
            raise NotConnected("mfa_failed:" + type(exc).__name__) from None
    if method in SCHEDULED_TASK_METHODS:
        # v2 闸门先于一切：config 键必须 literal True（False/缺失/真值
        # 字符串全拒——deny-closed）。
        if config.get("f137_v2_scheduled_tasks") is not True:
            raise NotConnected("f137_stage_gate_v2_required")
        if not isinstance(args, dict):
            raise NotConnected("f137_params_invalid")
        from f137_scheduled_tasks import f137_call, ScheduledTaskError
        try:
            return f137_call(method, args, config)
        except ScheduledTaskError as exc:
            # typed f137_* 码透传（v2 闸门/授权/时区/幂等/停止/未知具名），
            # 任务提示文本与会话内容永不进错误码。
            raise NotConnected("f137_refused:" + str(exc)) from None
        except Exception as exc:
            raise NotConnected("f137_failed:" + type(exc).__name__) from None
    if method in COLUMN_PRESET_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("column_preset_params_invalid")
        from column_presets import column_preset_call
        return column_preset_call(method, args, config)
    if method in EXCEL_EXPORT_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("export_params_invalid")
        from excel_export import export_call
        return export_call(method, args, config)
    if method in STATUTE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("statute_params_invalid")
        from statute_validity import statute_call
        return statute_call(method, args, config)
    if method in WEB_FALLBACK_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("web_fallback_params_invalid")
        from web_fallback import web_fallback_call
        return web_fallback_call(method, args, config)
    if method in CITATION_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("citation_params_invalid")
        from citation_verifier import citation_call
        return citation_call(method, args, config)
    if method in EXTRACTION_GATE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("extraction_params_invalid")
        from extraction_gate import extraction_call
        return extraction_call(method, args, config)
    if method in ABSTAIN_OPERATIONAL_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("abstain_params_invalid")
        from abstain_operational import abstain_operational_call
        return abstain_operational_call(method, args, config)
    if method in HARNESS_ABSTAIN_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="abstain-json", surface="abstain")
    if method in F88_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("f88_params_invalid")
        from f88_dualset_ci import f88_call
        return f88_call(method, args, config)
    if method in CALC_FAMILY_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("calc_family_params_invalid")
        return _calc_family_call(method, args, config)
    if method in RULE_PACK_GOVERNANCE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("rule_pack_governance_params_invalid")
        return _rule_pack_governance_call(method, args, config)
    if method in DEADLINE_PRESET_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("deadline_preset_params_invalid")
        return _deadline_preset_call(method, args, config)
    if method in AMOUNT_WORDS_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("amount_words_params_invalid")
        return _amount_words_call(method, args, config)
    if method in PLAYBOOK_REVIEW_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("playbook_params_invalid")
        from playbook_review import playbook_call
        return playbook_call(method, args, config)
    if method in HARNESS_PLAYBOOK_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_playbook_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="goal-json", surface="goal")
    if method in CACHE_PARTITION_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("cache_partition_params_invalid")
        from cache_partition import cache_partition_call
        return cache_partition_call(method, args, config)
    if method in AIRPLANE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("airplane_params_invalid")
        from airplane_mode import airplane_call
        return airplane_call(method, args, config)
    if method in MANUAL_METHODS:
        return _manual_call(method, args, config)
    if method in KB_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("kb_params_invalid")
        from kb_rag import kb_call, KbRagError
        try:
            return kb_call(method, args, config)
        except KbRagError as exc:
            # typed kb_* 码透传（错误码只带工程标识，绝不携条目正文/
            # 查询原文），缺根/未知后端/越权/漂移一律 NOT_CONNECTED。
            raise NotConnected("kb_failed:" + str(exc)) from None
    if method in EXPERT_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("expert_params_invalid")
        from expert_store import expert_call, ExpertStoreError
        try:
            return expert_call(method, args, config)
        except ExpertStoreError as exc:
            # typed f100_* 码透传（错误码只带工程标识，绝不携卡片正文/
            # 查询原文），缺根/越权/漂移/越界弃答一律 NOT_CONNECTED。
            raise NotConnected("expert_failed:" + str(exc)) from None
    if method in SUBMISSION_PACKAGE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("submission_package_params_invalid")
        from submission_package import submission_call, SubmissionPackageError
        try:
            return submission_call(method, args, config)
        except (NotConnected, HarnessCommandError):
            # 桥既有 typed 错误（未配置/账面失败）原样透传，不二次包裹。
            raise
        except SubmissionPackageError as exc:
            raise NotConnected("submission_package_failed:" + str(exc)) \
                from None
    if method in CALENDAR_SYNC_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("calendar_sync_params_invalid")
        from calendar_sync import calendar_sync_call, CalendarSyncError
        try:
            return calendar_sync_call(method, args, config)
        except (NotConnected, HarnessCommandError):
            raise
        except CalendarSyncError as exc:
            raise NotConnected("calendar_sync_failed:" + str(exc)) from None
    if method in EXPORT_MANIFEST_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("export_manifest_params_invalid")
        from signed_export import export_call, SignedExportError
        try:
            return export_call(method, args, config)
        except (NotConnected, HarnessCommandError):
            # 桥既有 typed 错误（未配置/账面 f123_* 具名码）原样透传，
            # 不二次包裹——账面拒不静默。
            raise
        except SignedExportError as exc:
            raise NotConnected("export_manifest_failed:" + str(exc)) from None
        except Exception as exc:  # 失败面只带类型名，绝不携材料/密钥内容。
            raise NotConnected("export_manifest_failed:"
                               + type(exc).__name__) from None
    if method in EXPORT_CHECKER_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("export_checker_params_invalid")
        from export_manifest_checker import checker_call, \
            ExportManifestCheckError
        try:
            return checker_call(method, args, config)
        except ExportManifestCheckError as exc:
            # 独立验证器 typed 码（f123chk_*）透传——验证路径与签发路径
            # 错误面同纪律：只携工程标识。
            raise NotConnected("export_checker_failed:" + str(exc)) from None
        except Exception as exc:
            raise NotConnected("export_checker_failed:"
                               + type(exc).__name__) from None
    if method in HARNESS_ADV_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("harness_adv_params_invalid")
        return _harness_provider_entry(method, args, config,
                                       flag="advorch-json",
                                       surface="advorch")
    if method in ADV_ORCH_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("adv_params_invalid")
        from f34_adv_orchestrator import adv_call, AdvOrchestrationError
        try:
            return adv_call(method, args, config)
        except AdvOrchestrationError as exc:
            # typed f34_* 具名拒/具名缺口走 HARNESS_FAIL 通道（exit 1，
            # 码原样透传零吞）；传输层 TransportError 原样上抛（exit 2
            # 保 OUTCOME_UNKNOWN 语义）。
            raise HarnessCommandError(str(exc)) from None
    if method in DOCX_EDIT_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("docx_edit_params_invalid")
        from docx_edit import docx_edit_call
        return docx_edit_call(method, args, config)
    if method in TEMPLATES_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("templates_params_invalid")
        from template_drafting import templates_call
        return templates_call(method, args, config)
    if method in COURT_INBOUND_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("court_inbound_params_invalid")
        from court_inbound import court_inbound_call
        return court_inbound_call(method, args, config)
    if method in CONTRACT_GATE_METHODS:
        if not isinstance(args, dict):
            raise NotConnected("contract_gate_params_invalid")
        from contract_gate import contract_gate_call
        return contract_gate_call(method, args, config)
    if method == "session.create":
        # F-9 收尾（T18 定论）：会话创建入口 fail-closed 权限校验后再透传。
        from e07_coordinator import create_public_session
        return create_public_session(args, config)
    # WorkBuddy composition is deliberately not exposed as OpenCode.
    raise NotConnected("method_not_connected:" + method)

def _material_overlay_projection(record):
    """F09 bridge projection: anonymizer-internal fields (originalPath) never
    cross — only the digest binding and revision lineage do."""
    return {key: record.get(key) for key in (
        "matterId", "documentId", "revision", "origin", "originalSha256",
        "textSha256", "overridesDigest", "appliedOps", "baseRevision",
        "recordedAt")}


def _material_overlay(method, args, config):
    """F09 overlay wiring (W2a-U05): 原件字节不变＋user_overrides_json 覆盖层
    形成新 revision 并可回读旧件（anonymizer overlay_service，同进程调用）。

    The overlay lands on the SANITIZED view only; the original file stays a
    read-only snapshot inside the anonymizer area (sha256 re-verified on every
    revision) and the identity mapping (Vault) is never in scope here. Bridge
    responses never carry originalPath — a pointer to where originals live is
    anonymizer-internal. Failures surface the type only, never material
    content (same red line as the deidentify face).
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    overlay_root = config.get("overlay_state_root")
    if not overlay_root:
        raise NotConnected("overlay_state_root_not_configured")
    matter_id = args.get("matterId")
    document_id = args.get("documentId")
    if not isinstance(matter_id, str) or not matter_id \
            or not isinstance(document_id, str) or not document_id:
        raise NotConnected("overlay_document_required")
    from legal_anonymizer.application import overlay_service
    from pathlib import Path as _Path
    try:
        if method == "material.overlay_register":
            record = overlay_service.register_document(
                _Path(overlay_root), matter_id, document_id,
                _Path(args["original_path"]), args["sanitized_text"])
        elif method == "material.overlay_apply":
            record = overlay_service.apply_overlay(
                _Path(overlay_root), matter_id, document_id,
                args.get("user_overrides"))
        elif method == "material.overlay_read":
            payload = overlay_service.read_revision(
                _Path(overlay_root), matter_id, document_id, args["revision"])
            return {"record": _material_overlay_projection(payload["record"]),
                    "text": payload["text"]}
        else:  # material.overlay_list
            listing = overlay_service.list_revisions(
                _Path(overlay_root), matter_id, document_id)
            return {"matterId": listing["matterId"],
                    "documentId": listing["documentId"],
                    "currentRevision": listing["currentRevision"],
                    "revisions": [_material_overlay_projection(r)
                                  for r in listing["revisions"]]}
    except KeyError as exc:
        raise NotConnected(f"overlay_fields_missing:{exc.args[0]}") from None
    except (ValueError, OSError) as exc:
        # Service-typed OverlayError str() is the specific code and the
        # service guarantees no surfaces in it; any other ValueError/OSError
        # degrades to the type name only — material never enters the code.
        detail = str(exc) if isinstance(exc, overlay_service.OverlayError) \
            else type(exc).__name__
        raise NotConnected(f"material_overlay_failed:{detail}") from None
    return _material_overlay_projection(record)


def _material_call(method, args, config):
    """P09/P10 material entry wiring (E09 early wiring, work order W1-U05).

    Same-process calls into the pinned anonymizer entries
    (14-Python入口证据.csv P09 cli.py:660 main / P10 pipeline.py:55,118):
    deidentify/rehydrate run inside this one call frame so the identity
    mapping (Vault) never leaves it — not persisted product-side, not put
    into logs, exceptions or receipts. Only Result.text (the sanitized,
    egress-bound form) and non-sensitive aggregates are returned. A
    standalone material.rehydrate is therefore structurally impossible and
    stays method_not_connected (no placeholder success).

    Rules provider preferred (Config use_llm=False -> provider "null"); the
    local model face is NOT faked: model_layer_requested stays False and
    review_required is True while NER qualification is unmet — REVIEW_REQUIRED
    semantics preserved for E11 deepening.
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    if method.startswith("material.overlay_"):
        return _material_overlay(method, args, config)
    text = args.get("text")
    if not isinstance(text, str) or not text:
        raise NotConnected("material_text_required")
    from legal_anonymizer.config import Config
    from legal_anonymizer.pipeline import deidentify, rehydrate
    material_config = Config(use_llm=False, critic=False,
                             policy=args.get("policy", "balanced"),
                             locale=args.get("locale", "zh"))
    try:
        material_config = material_config.validate()
        result = deidentify(text, material_config)
        report = result.report
        response = {
            "sanitized_text": result.text,
            "review_required": not (report.llm_requested and report.llm_ok),
            "model_layer_requested": report.llm_requested,
            "provider_name": report.provider_name,
            "policy": report.policy,
            "counts": {
                "token_total": report.token_total,
                "occurrence_total": report.occurrence_total,
                "regex_total": report.regex_total,
                "categories": dict(report.category_counts),
            },
        }
        if method == "material.roundtrip":
            response["roundtrip_restored"] = (
                rehydrate(result.text, result.vault) == text)
    except ValueError:
        # Config-level rejection (e.g. unknown policy). No material content
        # in the code string.
        raise NotConnected("material_config_invalid") from None
    except Exception as exc:
        # Red line: originals/mappings must never enter exceptions or
        # receipts — surface the failure type only, never the message.
        raise NotConnected("material_pipeline_failed:" + type(exc).__name__) from None
    return response

def _material_parse_call(method, args, config):
    """E12 全量材料解析桥（W2a-U02）：anonymizer material_parse_service
    同进程调用（anonymizer 仓 w2a-u02 分支公开面）。

    纪律与 P09/P10 面一致：未配置合同/状态根=fail-closed NOT_CONNECTED；
    服务端 typed error（MaterialParseError 的 str 只有错误码）原样透传，
    其他异常只带类型名——材料内容永不进入错误码。语料只读：登记与逐页
    处理均复验页字节 sha256，不符=UNREAD_FAILED 拒解析，绝不改写原件。

    F10（W4-U32）：config.f10_atrest=on＝加密态——密钥经 atrest_key 面从
    F12 保险库解密取出，随调用交给 anonymizer 页载荷信封面（无密钥直读
    不可读；零明文降级：取不到钥=typed f10_atrest_key_not_provisioned 拒，
    绝不静默明文落盘）。缺省 off＝v1 行为字节不变。
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    state_root = config.get("material_parse_state_root")
    if not state_root:
        raise NotConnected("material_parse_state_root_not_configured")
    from legal_anonymizer.application import material_parse_service

    def _atrest_key():
        """加密态取钥（仅页载荷方法）：取不到＝typed 拒零明文降级。
        register/pending 不落页载荷，不取钥（加密态登记仍可用）。"""
        if not atrest_key_module.atrest_enabled(config):
            return None
        try:
            return atrest_key_module.resolve_atrest_key(config)
        except atrest_key_module.AtrestKeyError as exc:
            raise NotConnected("atrest_failed:" + str(exc)) from None

    def _batch_id():
        batch_id = args.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id:
            raise NotConnected("material_parse_batch_id_required")
        return batch_id

    try:
        if method == "material.parse_register":
            corpus_root = args.get("corpus_root")
            if not isinstance(corpus_root, str) or not corpus_root:
                raise NotConnected("material_parse_corpus_root_required")
            return material_parse_service.register_batch(
                Path(state_root), Path(corpus_root))
        if method == "material.parse_process":
            return material_parse_service.process_pages(
                Path(state_root), _batch_id(), args.get("pages"),
                atrest_key=_atrest_key())
        if method == "material.parse_pending":
            return {"pending": material_parse_service.pending_pages(
                Path(state_root), _batch_id())}
        if method == "material.parse_report":
            return material_parse_service.batch_report(
                Path(state_root), _batch_id(), atrest_key=_atrest_key())
        if method == "material.parse_page":
            return material_parse_service.read_page(
                Path(state_root), _batch_id(),
                args.get("doc_id"), args.get("page"), atrest_key=_atrest_key())
        if method == "material.parse_human_edit":
            return material_parse_service.human_edit(
                Path(state_root), _batch_id(),
                args.get("doc_id"), args.get("page"),
                args.get("page_no_text"), atrest_key=_atrest_key())
        if method == "material.parse_reparse":
            return material_parse_service.reparse_page(
                Path(state_root), _batch_id(),
                args.get("doc_id"), args.get("page"), atrest_key=_atrest_key())
        return material_parse_service.table_rows(          # parse_tables
            Path(state_root), _batch_id(), args.get("doc_id"),
            atrest_key=_atrest_key())
    except NotConnected:
        raise
    except material_parse_service.MaterialParseError as exc:
        raise NotConnected("material_parse_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("material_parse_failed:" + type(exc).__name__) from None

def _ocr_ports_call(method, args, config):
    """F40 OCR 级联四端口桥（W2a-U03）：anonymizer ocr_ports_service
    同进程调用（anonymizer 仓 w2a-u03 分支公开面）。

    纪律与 material.parse_* 面一致：未配置合同/状态根=fail-closed
    NOT_CONNECTED；服务端 typed error（OcrPortsError 的 str 只有错误码）
    原样透传，其他异常只带类型名——材料内容永不进入错误码。语料只读：
    登记与跑批均复验页字节 sha256，不符=拒跑 fail-closed。ocr.ports 探针
    报告按调用方传入的 interpreter 实测，未安装如实标注不装样子。
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    from legal_anonymizer.application import ocr_ports_service as ops

    def _interpreter():
        interp = config.get("ocr_baseline_interpreter")
        if not isinstance(interp, str) or not interp:
            raise NotConnected("ocr_baseline_interpreter_not_configured")
        return interp

    def _state_root():
        root = config.get("ocr_ports_state_root")
        if not root:
            raise NotConnected("ocr_ports_state_root_not_configured")
        return Path(root)

    def _run_id():
        run_id = args.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise NotConnected("ocr_ports_run_id_required")
        return run_id

    try:
        if method == "ocr.ports":
            return ops.ports_report(args.get("interpreter")
                                    or _interpreter())
        if method == "ocr.baseline_register":
            corpus_root = args.get("corpus_root")
            if not isinstance(corpus_root, str) or not corpus_root:
                raise NotConnected("ocr_ports_corpus_root_required")
            return ops.baseline_register(_state_root(), Path(corpus_root),
                                         _interpreter())
        if method == "ocr.baseline_run":
            # W2a-U18：args["isolation"]="restricted_token" 透传（anonymizer
            # 受限令牌接线面）；未传＝按旧调用形（既有行为/旧 anonymizer 树
            # 逐字节兼容），闭集校验在服务侧 typed fail-closed。
            if args.get("isolation"):
                return ops.baseline_run(_state_root(), _run_id(),
                                        args.get("pages"),
                                        interpreter=_interpreter(),
                                        isolation=args["isolation"])
            return ops.baseline_run(_state_root(), _run_id(),
                                    args.get("pages"),
                                    interpreter=_interpreter())
        if method == "ocr.baseline_pending":
            return {"pending": ops.baseline_pending(_state_root(), _run_id())}
        if method == "ocr.baseline_report":
            return ops.baseline_report(_state_root(), _run_id())
        if method == "ocr.baseline_page":
            return ops.baseline_page(_state_root(), _run_id(),
                                     args.get("doc_id"), args.get("page"))
        return ops.baseline_tables(               # baseline_tables
            _state_root(), _run_id(), args.get("doc_id"))
    except NotConnected:
        raise
    except ops.OcrPortsError as exc:
        raise NotConnected("ocr_ports_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("ocr_ports_failed:" + type(exc).__name__) from None

def _ocr_batch_call(method, args, config):
    """F41 OCR 批量工程桥（W2a-U16）：anonymizer ocr_batch_service
    同进程调用（anonymizer 仓 w2a-u16 分支公开面）。

    纪律与 ocr.* 面一致：未配置合同/状态根/解释器=fail-closed
    NOT_CONNECTED；服务端 typed error（OcrBatchError 的 str 只有错误码）
    原样透传，其他异常只带类型名——材料内容永不进入错误码。批量面复用
    F40 同域配置键；进度面＝公开面回读（桌面真机进度 UI 不前造）。
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    from legal_anonymizer.application import ocr_batch_service as obs

    def _interpreter():
        interp = config.get("ocr_baseline_interpreter")
        if not isinstance(interp, str) or not interp:
            raise NotConnected("ocr_baseline_interpreter_not_configured")
        return interp

    def _state_root():
        root = config.get("ocr_ports_state_root")
        if not root:
            raise NotConnected("ocr_ports_state_root_not_configured")
        return Path(root)

    def _batch_id():
        batch_id = args.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id:
            raise NotConnected("ocr_batch_id_required")
        return batch_id

    def _after_seq():
        seq = args.get("after_seq", 0)
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
            raise NotConnected("ocr_batch_after_seq_invalid")
        return seq

    try:
        if method == "ocr.batch_register":
            corpus_root = args.get("corpus_root")
            if not isinstance(corpus_root, str) or not corpus_root:
                raise NotConnected("ocr_batch_corpus_root_required")
            gap = args.get("min_doc_gap_s", 0.0)
            return obs.batch_register(_state_root(), Path(corpus_root),
                                      _interpreter(),
                                      min_doc_gap_s=gap)
        if method == "ocr.batch_run":
            return obs.batch_run(_state_root(), _batch_id(),
                                 interpreter=_interpreter())
        if method == "ocr.batch_cancel":
            return obs.batch_cancel(_state_root(), _batch_id())
        if method == "ocr.batch_status":
            return obs.batch_status(_state_root(), _batch_id())
        if method == "ocr.batch_events":
            return obs.batch_events(_state_root(), _batch_id(),
                                    after_seq=_after_seq())
        if method == "ocr.batch_pending":
            return obs.batch_pending(_state_root(), _batch_id())
        if method == "ocr.batch_redraw":
            doc_id = args.get("doc_id")
            if not isinstance(doc_id, str) or not doc_id:
                raise NotConnected("ocr_batch_doc_id_required")
            return obs.batch_redraw(_state_root(), _batch_id(), doc_id,
                                    interpreter=_interpreter())
        if method == "ocr.batch_report":
            return obs.batch_report(_state_root(), _batch_id())
        if method == "ocr.batch_verify_reports":
            return obs.batch_verify_reports(_state_root(), _batch_id())
        if method == "ocr.batch_doc_version":
            doc_id = args.get("doc_id")
            if not isinstance(doc_id, str) or not doc_id:
                raise NotConnected("ocr_batch_doc_id_required")
            version = args.get("version")
            if version is not None and (isinstance(version, bool)
                                        or not isinstance(version, int)):
                raise NotConnected("ocr_batch_version_invalid")
            return obs.batch_doc_version(_state_root(), _batch_id(), doc_id,
                                         version=version)
        return obs.batch_secret_exposure(_state_root(), _batch_id())
    except NotConnected:
        raise
    except obs.OcrBatchError as exc:
        raise NotConnected("ocr_batch_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("ocr_batch_failed:" + type(exc).__name__) from None

def _stamp_call(method, args, config):
    """F42 印章/PS 疑似视觉检测桥（W4-U35）：anonymizer stamp_visual_service
    同进程调用（anonymizer 仓 w4-u21 分支公开面，W4-U21 交付）。

    纪律与 ocr.* 面一致：未配置合同/状态根/解释器=fail-closed
    NOT_CONNECTED；服务端 typed error（StampVisualError 的 str 只有错误码）
    原样透传，其他异常只带类型名——材料内容永不进入错误码。检测＝钉定
    解释器 worker 子进程（GPU fail-closed·模型 sha256 钉定·绝不运行时
    下载）；原图回读=只读映射（bytes 恒不出域）；结论词闭集
    {suspected, not_detected}（不签真伪鉴定，结构性）；页号参数
    bool/int 闭面校验先于服务调用。
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    from legal_anonymizer.application import stamp_visual_service as svs

    def _interpreter():
        interp = config.get("ocr_baseline_interpreter")
        if not isinstance(interp, str) or not interp:
            raise NotConnected("stamp_interpreter_not_configured")
        return interp

    def _state_root():
        root = config.get("ocr_ports_state_root")
        if not root:
            raise NotConnected("stamp_state_root_not_configured")
        return Path(root)

    def _run_id():
        run_id = args.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise NotConnected("stamp_run_id_required")
        return run_id

    def _doc_id():
        doc_id = args.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id:
            raise NotConnected("stamp_doc_id_required")
        return doc_id

    def _page():
        page = args.get("page")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise NotConnected("stamp_page_invalid")
        return page

    def _corpus_root():
        corpus_root = args.get("corpus_root")
        if not isinstance(corpus_root, str) or not corpus_root:
            raise NotConnected("stamp_corpus_root_required")
        return Path(corpus_root)

    try:
        if method == "stamp.register":
            return svs.stamp_register(_state_root(), _corpus_root(),
                                      _interpreter())
        if method == "stamp.run":
            return svs.stamp_run(_state_root(), _run_id(),
                                 pages=args.get("pages"),
                                 interpreter=_interpreter())
        if method == "stamp.pending":
            return {"pending": svs.stamp_pending(_state_root(), _run_id())}
        if method == "stamp.report":
            return svs.stamp_report(_state_root(), _run_id())
        if method == "stamp.page":
            return svs.stamp_page(_state_root(), _run_id(), _doc_id(),
                                  _page())
        if method == "stamp.original":
            return svs.stamp_original(_state_root(), _run_id(), _doc_id(),
                                      _page())
        if method == "stamp.limitation":
            return svs.stamp_limitation()
        return svs.stamp_conclusion_scan(_state_root(), _run_id())
    except NotConnected:
        raise
    except svs.StampVisualError as exc:
        raise NotConnected("stamp_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("stamp_failed:" + type(exc).__name__) from None


def _reading_order_call(method, args, config):
    """F86 阅读序同源桥（W2a-U07）：reading_order 规范面，同进程调用。

    纪律与 material.parse_* 面一致：未配置合同/状态根=fail-closed
    NOT_CONNECTED；typed error（ReadingOrderError 的 str 只有错误码）原样
    透传，其他异常只带类型名——材料内容永不进入错误码。数据面只读
    material_parse_service 解析产物（同源：前端阅读面消费同一文档）。
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    try:
        from reading_order import ReadingOrderError, call as reading_call
    except ImportError as exc:
        raise NotConnected("reading_order_not_importable:"
                           + type(exc).__name__) from None
    try:
        return reading_call(method, args, config)
    except NotConnected:
        raise
    except ReadingOrderError as exc:
        # typed error 的 str() 只有错误码（静默失败预防针：响亮失败面）
        raise NotConnected("reading_order_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("reading_order_failed:" + type(exc).__name__) from None
def _review_gate_call(method, args, config):
    """E11/F37 资格闸桥（W2a-U09）：anonymizer review_gate_service
    同进程调用（anonymizer 仓 w2a-u09 分支公开面）。

    纪律与 material.parse_*/ocr.* 面一致：未配置合同=fail-closed
    NOT_CONNECTED；失败面只带类型名——材料内容（金标 surface、词典值）
    永不进入错误码。响应只回聚合（计数/资格/别名 kind），绝不回 surface。
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    from legal_anonymizer.application import review_gate_service as rgs

    def _state_root():
        root = config.get("review_gate_state_root")
        if not root:
            raise NotConnected("review_gate_state_root_not_configured")
        return Path(root)

    try:
        if method == "review.qualification":
            return rgs.qualification_report()
        if method == "review.rule_classes":
            return {"inventory": rgs.rule_class_inventory()}
        if method == "review.class_coverage":
            texts = args.get("texts")
            gold = args.get("gold")
            if not isinstance(texts, list) or not all(
                    isinstance(t, str) for t in texts):
                raise NotConnected("review_gate_texts_invalid")
            if not isinstance(gold, list):
                raise NotConnected("review_gate_gold_invalid")
            dictionary = args.get("dictionary")
            if dictionary is not None and not isinstance(dictionary, dict):
                raise NotConnected("review_gate_dictionary_invalid")
            stack = args.get("stack", "production")
            if stack not in ("production", "rules"):
                raise NotConnected("review_gate_stack_invalid")
            return rgs.measure_class_coverage(
                texts, gold, dictionary=dictionary, stack=stack)
        if method == "review.human_coverage":
            matter_ids = args.get("matter_ids")
            if not isinstance(matter_ids, list) or not all(
                    isinstance(m, str) for m in matter_ids):
                raise NotConnected("review_gate_matter_ids_invalid")
            out_dirs = args.get("out_dirs")
            if out_dirs is not None and not isinstance(out_dirs, dict):
                raise NotConnected("review_gate_out_dirs_invalid")
            return rgs.human_review_coverage(
                _state_root(), matter_ids, out_dirs=out_dirs)
        # review.never_backfill
        matter_id = args.get("matter_id")
        if not isinstance(matter_id, str) or not matter_id:
            raise NotConnected("review_gate_matter_id_required")
        return rgs.never_backfill_report(_state_root(), matter_id)
    except NotConnected:
        raise
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("review_gate_failed:" + type(exc).__name__) from None

def _attachment_gate_call(method, args, config):
    """F38/F44 附件闸桥（W2a-U15）：anonymizer attachment_gate_service
    同进程调用（anonymizer 仓 w2a-u15 分支公开面）。

    纪律与 review.*/ocr.* 面一致：未配置合同/状态根=fail-closed
    NOT_CONNECTED；owner 面 typed error（AttachmentGateError.code 冻结
    信封）透传码，其他异常只带类型名——材料内容永不进入错误码。响应只回
    计数/哈希/状态/拒绝理由，绝不回 surface 或原件路径。
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    from legal_anonymizer.application import attachment_gate_service as ags

    def _state_root():
        root = config.get("attachment_gate_state_root")
        if not root:
            raise NotConnected("attachment_gate_state_root_not_configured")
        return Path(root)

    try:
        if method == "attachment.scan":
            path = args.get("pdf_path")
            if not isinstance(path, str) or not path:
                raise NotConnected("attachment_scan_path_required")
            report = ags.scan_final_bytes(path)
            return {k: report[k] for k in (
                "schema", "scanProfile", "sha256", "byteLength", "pages",
                "status", "reasons", "findings", "coverage")}
        if method == "attachment.gate":
            request = {
                "matter_id": args.get("matter_id"),
                "attachment_id": args.get("attachment_id"),
                "source_pdf": args.get("source_pdf"),
                "ocr": args.get("ocr"),
                "human_decision": args.get("human_decision"),
                "gold": args.get("gold"),
            }
            request = {k: v for k, v in request.items() if v is not None}
            if args.get("dpi") is not None:
                request["dpi"] = args["dpi"]
            policy = args.get("policy")   # F43：opt-in 策略预设（缺省 v1）
            if policy is not None and (
                    not isinstance(policy, str)
                    or policy not in ("external_send", "internal_analysis",
                                      "public_release")):
                raise NotConnected("attachment_gate_policy_invalid")
            ocr_root = config.get("ocr_ports_state_root")
            interpreter = config.get("ocr_baseline_interpreter")
            if not ocr_root:
                raise NotConnected("ocr_ports_state_root_not_configured")
            if not interpreter:
                raise NotConnected("ocr_baseline_interpreter_not_configured")
            # F43 参数仅在调用方显式携带时透传（W2a-U18 先例：恒传关键字
            # 对旧树旧签名 TypeError——缺省必须走 v1 原调用形）。
            new_args = {"policy": policy} if policy is not None else {}
            return ags.run_attachment_gate(
                _state_root(), request,
                ocr_state_root=ocr_root, interpreter=interpreter, **new_args)
        # attachment.authorize
        matter_id = args.get("matter_id")
        attachment_id = args.get("attachment_id")
        if not isinstance(matter_id, str) or not matter_id:
            raise NotConnected("attachment_gate_matter_id_required")
        if not isinstance(attachment_id, str) or not attachment_id:
            raise NotConnected("attachment_gate_attachment_id_required")
        egress_scope = args.get("egress_scope")  # F43：opt-in 出域 scope
        if egress_scope is not None and (
                not isinstance(egress_scope, str)
                or egress_scope not in ("external_send", "internal_analysis",
                                        "public_release")):
            raise NotConnected("attachment_gate_egress_scope_invalid")
        # 同上：仅在显式携带时透传，缺省保持 v1 原调用形（旧树兼容）。
        if egress_scope is not None:
            return ags.authorize_egress(_state_root(), matter_id,
                                        attachment_id,
                                        egress_scope=egress_scope)
        return ags.authorize_egress(_state_root(), matter_id, attachment_id)
    except NotConnected:
        raise
    except ags.AttachmentGateError as exc:
        # owner 冻结信封码（schema/未登记/源不可读），码不含材料内容
        raise NotConnected("attachment_gate_failed:" + exc.code) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("attachment_gate_failed:" + type(exc).__name__) from None

def _redaction_preset_call(method, args, config):
    """F43 脱敏策略预设桥（W4-U36）：anonymizer redaction_presets_service
    同进程调用（owner 仓 w4-u36 分支公开面；落 attachment_gate_service＋
    mapping.Vault 既有权威扩展，不建第二权威）。

    纪律与 attachment.* 面一致：未配置合同/状态根=fail-closed
    NOT_CONNECTED；owner typed error（RedactionPresetError.code 冻结信封）
    透传码，其他异常只带类型名——材料内容/surface/映射表永不进入错误码
    或响应（deidentify_matter 响应的 sanitized_text 本身即出域形态；
    pseudonym_resolve 只回 token 串按输入序对位）。"""
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    from legal_anonymizer.application import redaction_presets_service as rps

    root = config.get("attachment_gate_state_root")
    if not root:
        raise NotConnected("attachment_gate_state_root_not_configured")
    state_root = Path(root)

    def _preset():
        preset = args.get("preset")
        if not isinstance(preset, str) or preset not in (
                "external_send", "internal_analysis", "public_release"):
            raise NotConnected("redaction_preset_invalid")
        return preset

    def _matter():
        matter_id = args.get("matter_id")
        if not isinstance(matter_id, str) or not matter_id:
            raise NotConnected("redaction_preset_matter_id_required")
        return matter_id

    try:
        if method == "redaction.presets":
            return rps.preset_registry(state_root)
        if method == "redaction.deidentify_matter":
            text = args.get("text")
            if not isinstance(text, str) or not text:
                raise NotConnected("redaction_preset_text_required")
            return rps.deidentify_matter(state_root, _matter(), _preset(),
                                         text)
        if method == "redaction.pseudonym_resolve":
            items = args.get("items")
            if not isinstance(items, list) or not items:
                raise NotConnected("redaction_preset_items_invalid")
            return rps.resolve_pseudonyms(state_root, _matter(), _preset(),
                                          items)
        # redaction.rehydrate_matter
        text = args.get("text")
        if not isinstance(text, str) or not text:
            raise NotConnected("redaction_preset_text_required")
        return rps.rehydrate_matter(state_root, _matter(), _preset(), text)
    except NotConnected:
        raise
    except rps.RedactionPresetError as exc:
        # owner 冻结信封码（invalid/config_invalid/no_map），码不含材料内容
        raise NotConnected("redaction_preset_failed:" + exc.code) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("redaction_preset_failed:" + type(exc).__name__) from None

def _wechat_collection_call(method, args, config):
    """F61 微信批次采集桥（W3-U13）：wechat_collection 编排面＋回调注入。

    编排面零 anonymizer import；材料化与过闸经本桥既有公开面注入：
    materialize_text＝_material_call("material.deidentify")（P10 既有
    pipeline）；gate_pdf＝_attachment_gate_call("attachment.gate")（F38/F44
    既有闸）。fail-closed 同基线：未配置合同/状态根＝NOT_CONNECTED；
    owner typed code（CollectionError.code 冻结闭集）透传，其他异常只带
    类型名——导出原文/脱敏映射/附件 surface/原件路径永不进入错误码与回执。
    """
    if config.get("anonymizer_contract") != "p09/p10":
        raise NotConnected("anonymizer_p09_p10_not_configured")
    collection_root = config.get("collection_state_root")
    if not collection_root:
        raise NotConnected("collection_state_root_not_configured")
    from pathlib import Path as _Path
    from wechat_collection import (CollectionError, authorize_ids,
                                   read_batch, run_batch)

    try:
        if method == "collection.authorize":
            return authorize_ids(_Path(collection_root), args)
        if method == "collection.batch":
            def _materialize_text(text):
                return _material_call("material.deidentify",
                                      {"text": text}, config)

            def _gate_pdf(request):
                return _attachment_gate_call("attachment.gate",
                                             request, config)

            return run_batch(_Path(collection_root), args,
                             materialize_text=_materialize_text,
                             gate_pdf=_gate_pdf)
        # collection.batch_read
        return read_batch(_Path(collection_root), args)
    except NotConnected:
        raise
    except CollectionError as exc:
        # owner 冻结码闭集（f61_*），码不含材料内容。
        raise NotConnected("collection_failed:" + exc.code) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("collection_failed:" + type(exc).__name__) from None

def _ems_evidence_call(method, args, config):
    """F63 EMS 取证桥（W4-U40）：ems_evidence 授权账＋查询封存面。

    裁决#8-12 禁编 URL：本波产品桥无 EMS 适配器可注入（官方 API 端点
    属授权未落地后的适配器工单，端点禁编）——evidence_query 恒以
    transport=None 调用，已授权＋token 在位也只会得到 ADAPTER_ABSENT
    具名缺口，未授权/未接线态真实调用路径结构性不可达（客户端未建不
    可能自采）。fail-closed 同基线：状态根未配置＝NOT_CONNECTED；owner
    typed code（EmsEvidenceError.code 冻结闭集 f63_*）透传，其他异常只
    带类型名——回执原文/token 值/URL 永不进入错误码与回执。
    """
    ems_root = config.get("ems_evidence_state_root")
    if not ems_root:
        raise NotConnected("ems_evidence_state_root_not_configured")
    from pathlib import Path as _Path
    from ems_evidence import (EmsEvidenceError, authorize_action,
                              read_query, run_query)

    try:
        if method == "ems.action_authorize":
            return authorize_action(_Path(ems_root), args)
        if method == "ems.evidence_query":
            # transport 恒 None＝本波适配器缺席（负测先行结构性事实）。
            return run_query(_Path(ems_root), args, transport=None)
        # ems.evidence_read
        return read_query(_Path(ems_root), args)
    except NotConnected:
        raise
    except EmsEvidenceError as exc:
        raise NotConnected("ems_evidence_failed:" + exc.code) from None
    except Exception as exc:
        raise NotConnected("ems_evidence_failed:"
                           + type(exc).__name__) from None


def _enterprise_connector_call(method, args, config):
    """F144 企业尽调 MCP 连接器桥（W4-U40）：enterprise_connector 状态面
    ＋尽调查询账。

    连接器形态（2026-10-13 用户拍板）：企业数据走 MCP 连接器接入，不自
    采。裁决#8-12 禁编 URL：本波产品桥无已配置 MCP 连接器可注入（真实
    接入属授权后配置）——diligence_query 恒以 session_factory=None 调用
    ，token 在位也只会得到 SESSION_ABSENT 具名缺口，未授权/未接线态真
    实调用路径结构性不可达（客户端未建不可能自采）；缺 Token→具名缺口
    PAID_TOKEN_NOT_CONFIGURED 不自采或编数据（值恒 None 非 {}）。fail-
    closed 同基线：状态根未配置＝NOT_CONNECTED；owner typed code（
    EnterpriseConnectorError.code 冻结闭集 f144_*）透传，其他异常只带
    类型名——企业数据原文/token 值/URL 永不进入错误码与回执。
    """
    ent_root = config.get("enterprise_connector_state_root")
    if not ent_root:
        raise NotConnected("enterprise_connector_state_root_not_configured")
    from pathlib import Path as _Path
    from enterprise_connector import (EnterpriseConnectorError,
                                      connector_status, diligence_query,
                                      read_query)

    try:
        if method == "enterprise.connector_status":
            return connector_status()
        if method == "enterprise.diligence_query":
            # session_factory 恒 None＝本波连接器未配置（负测先行结构性
            # 事实；真实会话通道属授权后补联测回收点）。
            return diligence_query(_Path(ent_root), args,
                                   session_factory=None)
        # enterprise.diligence_read
        return read_query(_Path(ent_root), args)
    except NotConnected:
        raise
    except EnterpriseConnectorError as exc:
        raise NotConnected("enterprise_connector_failed:"
                           + exc.code) from None
    except Exception as exc:
        raise NotConnected("enterprise_connector_failed:"
                           + type(exc).__name__) from None


def _commercial_policy(config, comm_root, args) -> dict:
    """F81→F80 真实应用装配：按账户 (org,user) 求值策略投影。

    org_policy_state_root 未配置＝无策略（商业面默认开放，冻结常量
    语义）；账户未落账时返回空投影——身份错误由商业模块具名拒
    （f80_account_unknown），策略装配不抢身份错误。
    """
    org_root = config.get("org_policy_state_root")
    if not org_root:
        return {}
    from pathlib import Path as _Path
    from commercial_service import (CommercialServiceError,
                                    account_identity)
    from org_policy_admin import evaluate, load_ledger
    account_id = args.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        return {}
    try:
        org_id, user_ref = account_identity(comm_root, account_id)
    except CommercialServiceError:
        return {}
    return evaluate(load_ledger(_Path(org_root)), org_id,
                    user_ref)["effective"]


def _commercial_call(method, args, config):
    """F80 商业服务面桥（W5-U02）：commercial_service 独立商业账。

    独立商业服务面（06 V7-80）：独立状态根 commercial_state_root；
    案件工作台零运营位＝本组只此六类商业操作＋字段闭集外具名拒。
    裁决#13-19 合成先行：零网络零 URL，真实托管设施 v2 商业化时补。
    F81 真实应用链：credit_grant/checkin 经 _commercial_policy 注入
    求值投影——策略声明即时改变运行面行为。fail-closed 基线：状态根
    未配置＝NOT_CONNECTED；owner typed code（CommercialServiceError
    .code 冻结闭集 f80_*）透传，其他异常只带类型名——金额/身份原文
    永不进入错误码与回执。
    """
    comm_root = config.get("commercial_state_root")
    if not comm_root:
        raise NotConnected("commercial_state_root_not_configured")
    from pathlib import Path as _Path
    from commercial_service import (CommercialServiceError, account_open,
                                    balance_read, checkin, credit_grant,
                                    invite_issue, invite_redeem, revoke)

    try:
        if method == "commercial.account_open":
            return account_open(_Path(comm_root), args)
        if method == "commercial.balance_read":
            return balance_read(_Path(comm_root), args)
        if method == "commercial.invite_issue":
            return invite_issue(_Path(comm_root), args)
        if method == "commercial.invite_redeem":
            return invite_redeem(_Path(comm_root), args)
        if method == "commercial.revoke":
            return revoke(_Path(comm_root), args)
        # credit_grant / checkin：F81 策略注入（真实应用到运行面）。
        policy = _commercial_policy(config, _Path(comm_root), args)
        if method == "commercial.credit_grant":
            return credit_grant(_Path(comm_root), args, policy=policy)
        return checkin(_Path(comm_root), args, policy=policy)
    except NotConnected:
        raise
    except CommercialServiceError as exc:
        raise NotConnected("commercial_failed:" + exc.code) from None
    except Exception as exc:
        raise NotConnected("commercial_failed:"
                           + type(exc).__name__) from None


def _org_admin_call(method, args, config):
    """F81 企业组策略管理台桥（W5-U02）：org_policy_admin 策略账＋求值
    ＋应用回执。

    深管理不替代最小 v1 管理台（06 V7-81）：键闭集全部 commercial.*
    （v2 商业面）；案件/材料/harness 等 v1 管理面无处置位——键闭集外
    具名拒（f81_policy_key_unknown，case.* 探测负测在 recon/test）。
    fail-closed 同基线：状态根未配置＝NOT_CONNECTED；owner typed code
    （OrgPolicyError.code 冻结闭集 f81_*）透传，其他异常只带类型名。
    """
    org_root = config.get("org_policy_state_root")
    if not org_root:
        raise NotConnected("org_policy_state_root_not_configured")
    from pathlib import Path as _Path
    from org_policy_admin import (OrgPolicyError, policy_apply,
                                  policy_declare, policy_read)

    try:
        if method == "orgadmin.policy_declare":
            return policy_declare(_Path(org_root), args)
        if method == "orgadmin.policy_read":
            return policy_read(_Path(org_root), args)
        return policy_apply(_Path(org_root), args)
    except NotConnected:
        raise
    except OrgPolicyError as exc:
        raise NotConnected("org_policy_failed:" + exc.code) from None
    except Exception as exc:
        raise NotConnected("org_policy_failed:"
                           + type(exc).__name__) from None


def _dossier13_call(method, args, config):
    """F144-v2 企业尽调技能包桥（W5-U15）：13 件全量目录＋件执行＋回读。

    唯一数据通道＝enterprise_connector（W4-U40 冻结面）；本桥 run 恒以
    session_factory=None 调用（连接器形态：真实 MCP 会话通道属授权后补
    联测回收点，挂 F144-desktop/selfhost——W5-U19 守账，不并单），token
    在位也只会得到 SESSION_ABSENT 具名缺口＝真实调用路径结构性不可达。
    fail-closed 同基线：状态根未配置＝NOT_CONNECTED；d13_* typed code 透
    传；连接器 f144_* typed code 原样透传（enterprise_connector_failed:
    前缀）；其他异常只带类型名——企业数据原文/token 值/URL 永不进入错
    误码与档案投影。
    """
    d13_root = config.get("dossier13_state_root")
    if not d13_root:
        raise NotConnected("dossier13_state_root_not_configured")
    from pathlib import Path as _Path
    from dossier13 import (Dossier13Error, pack_read, read_dossier,
                           run_dossier)

    try:
        if method == "dossier13.pack_read":
            return pack_read()
        if method == "dossier13.run_dossier":
            return run_dossier(_Path(d13_root), args, session_factory=None)
        # dossier13.dossier_read
        return read_dossier(_Path(d13_root), args)
    except NotConnected:
        raise
    except Dossier13Error as exc:
        raise NotConnected("dossier13_failed:" + exc.code) from None
    except Exception as exc:
        raise NotConnected("dossier13_failed:"
                           + type(exc).__name__) from None


def _court_case_library_call(method, args, config):
    """F72 法院案例库桥（W4-U42）：court_case_library 产品面＋P08 梯子强制。

    caselib.search 经 court_case_library.search_through_bridge 回调
    _call_case_public（梯子/回执唯一权威在 cases 公开面，产品桥强制携带并
    审计）；register/tier 走钉定检出的 lcr.caselib 承载面。fail-closed 同
    基线：缺 cases_root/cases_import_path/caselib_dataset_version＝
    NOT_CONNECTED；typed CaseLibraryError（str() 仅 caselib_* 冻结码，两侧
    闭集）只透码不透消息——docId/查询文本等材料内容永不进入错误码。
    """
    from court_case_library import CaseLibraryError
    from court_case_library import call as _caselib_call
    try:
        return _caselib_call(method, args, config)
    except (NotConnected, CaseProviderError):
        # CaseProviderError＝cases 公开面/梯子的具名拒（query_invalid 等闭集
        # 码），原样上浮由 main 映射 CASE_ERROR（exit 4），绝不折损码。
        raise
    except CaseLibraryError as exc:
        # 冻结码闭集（caselib_*，cases 承载侧与产品面双侧闭集），码不含材料。
        raise NotConnected("caselib_failed:" + exc.code) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("caselib_failed:" + type(exc).__name__) from None

def _number_call(method, args, config):
    """F89 数字三分类豁免桥（W2b-U04）：number.classify 纯确定性分类；
    number.verify_amount 金额值经 JC 公开求值（P01 jc.evaluate 同一
    client 构造路径与 fail-closed 纪律；JC 侧失败面=JCMethodFailure
    exit 4，绝不假 OWNER_RESPONSE）。金额入参 float 一律拒收（Decimal
    全程红线）；typed error 只带码不带材料内容。
    """
    from number_classifier import (
        NumberFaceError, amount_verdict, build_amount_task,
        classify_document, parse_amount_text,
    )
    try:
        if method == "number.classify":
            text = args.get("text")
            if not isinstance(text, str) or not text:
                raise NotConnected("number_classify_text_required")
            return classify_document(text)
        # number.verify_amount
        principal = parse_amount_text(args.get("principal"), "principal")
        claimed = parse_amount_text(args.get("claimed_balance"),
                                    "claimed_balance")
        from number_classifier import canonical_date
        as_of = canonical_date(args.get("as_of"), "as_of")
        due_day = canonical_date(args.get("due_day"), "due_day")
        date_anchor_used = (args.get("as_of") is None
                            and args.get("due_day") is None)
        payments_raw = args.get("payments") or []
        if not isinstance(payments_raw, list):
            raise NotConnected("number_face_failed:payments_invalid")
        payments = []
        for item in payments_raw:
            if not isinstance(item, dict):
                raise NotConnected("number_face_failed:payment_invalid")
            payment_id = item.get("payment_id")
            if not isinstance(payment_id, str) or not payment_id:
                raise NotConnected("number_face_failed:payment_id_required")
            payments.append({
                "payment_id": payment_id,
                "amount": parse_amount_text(item.get("amount"),
                                            "payment:" + payment_id),
                "event_day": canonical_date(item.get("event_day"),
                                             "event_day:" + payment_id),
            })
        task = build_amount_task(principal=principal, payments=payments,
                                 as_of=as_of, due_day=due_day)
        client = _jc_client(config)
        case_id = "f89-amount-verification"
        def _run():
            bundle = client.local_case_bundle(
                case_id=case_id,
                decision_time=as_of + "T00:00:00Z",
                business_tasks=[task])
            return client.evaluate_harness_bundle(
                bundle, case_id=case_id, issue_queries=[])
        result = _jc(_run)
        return amount_verdict(result, claimed=claimed, principal=principal,
                              payments=payments, as_of=as_of,
                              due_day=due_day,
                              date_anchor_used=date_anchor_used)
    except NumberFaceError as exc:
        raise NotConnected("number_face_failed:" + str(exc)) from None
    except (NotConnected, JCMethodFailure):
        raise
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("number_face_failed:" + type(exc).__name__) from None

def _conversion_call(method, args, config):
    """F54 PDF→docx 转换候选桥（W2b-U17）：产品侧 pdf_conversion 同进程
    公开面（document-adapter）。

    纪律与 citation.*/statute.* 产品面一致：未配置状态根/soffice=
    fail-closed NOT_CONNECTED；typed error（ConversionError 的 str 只有
    f54_* 错误码）透传，其他异常只带类型名——材料内容永不进入错误码。
    响应不回绝对路径（engine.binary 只回文件名），候选字节经
    conversion.candidate base64 取件。
    """
    from pdf_conversion import conversion_call, ConversionError
    try:
        return conversion_call(method, args, config)
    except ConversionError as exc:
        raise NotConnected("conversion_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("conversion_failed:" + type(exc).__name__) from None

def _paper_call(method, args, config):
    """F18 纸张预览桥（W3-U21）：产品侧 paper_preview 同进程公开面
    （document-adapter 家族）。

    纪律与 conversion.* 产品面一致：未配置状态根/soffice=fail-closed
    NOT_CONNECTED；typed error（PaperError 的 str 只有 f18_* 错误码）透传，
    其他异常只带类型名——材料内容永不进入错误码。paper.document 回执零
    分页字段（CSS 预览结构性不携带分页主张，08§3 文书行）；真实分页唯一
    参照＝paper.pagination_reference（LibreOffice 渲染 PDF 实测）。
    """
    from paper_preview import paper_call, PaperError
    try:
        return paper_call(method, args, config)
    except PaperError as exc:
        raise NotConnected("paper_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("paper_failed:" + type(exc).__name__) from None

def _anchor_call(method, args, config):
    """F50 重锚定＋F51 逐字闸桥（W2b-U13）：产品侧 document_anchor 同进程
    公开面（document-adapter）。

    纪律与 conversion.* 产品面一致：未配置状态根=fail-closed
    NOT_CONNECTED；typed error（AnchorError 的 str 只有 f50_*/f51_*
    错误码）透传，其他异常只带类型名——材料内容（quote/文本）永不进入
    错误码，只出现在正常结果与人工入口账里。
    """
    from document_anchor import anchor_call, AnchorError
    try:
        return anchor_call(method, args, config)
    except AnchorError as exc:
        raise NotConnected("anchor_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("anchor_failed:" + type(exc).__name__) from None

def _redline_call(method, args, config):
    """F49 replay 红线桥（W2b-U14）：产品侧 document_redline 同进程公开面
    （document-adapter）。

    纪律与 conversion.* 产品面一致：未配置状态根=fail-closed
    NOT_CONNECTED；typed error（RedlineError 的 str 只有 f49_* 错误码）
    透传，其他异常只带类型名——材料内容永不进入错误码。红线字节经
    redline.redline base64 取件（W2b-U16 WPS 宿主验证与 E13 收口消费）。
    """
    from document_redline import redline_call, RedlineError
    try:
        return redline_call(method, args, config)
    except RedlineError as exc:
        raise NotConnected("redline_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("redline_failed:" + type(exc).__name__) from None

def _proofing_call(method, args, config):
    """F143 法律写作校对桥（W5-U14）：产品侧 document_proofing 同进程公开
    面（document-adapter 家族）。

    纪律与 conversion.*/redline.*/doccompare.* 产品面一致：未配置状态根=
    fail-closed NOT_CONNECTED；typed error（ProofingError 的 str 只有
    f143_* 错误码）透传，其他异常只带类型名——材料内容永不进入错误码。
    校对候选/决定账/提案与更正 DOCX 经本桥取件；Harness 正式采用
    （formal_propose/formal_decide）走既有 HARNESS_FORMAL_PROPOSAL_METHODS
    面，本桥零复制第二账本。
    """
    from document_proofing import proofing_call, ProofingError
    try:
        return proofing_call(method, args, config)
    except ProofingError as exc:
        raise NotConnected("proofing_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("proofing_failed:" + type(exc).__name__) from None

def _doccompare_call(method, args, config):
    """F55 独立文档对比桥（W4-U37）：产品侧 document_compare 同进程公开面
    （document-adapter 家族）。

    纪律与 conversion.*/redline.* 产品面一致：未配置状态根=fail-closed
    NOT_CONNECTED；typed error（DocCompareError 的 str 只有 f55_* 错误码）
    透传，其他异常只带类型名——材料内容永不进入错误码。变更清单/窗格行
    只出现在正常回执与 comparison.json（docexport 对比源经
    doccompare.report 取件，不复制第二真源）。
    """
    from document_compare import doccompare_call, DocCompareError
    try:
        return doccompare_call(method, args, config)
    except DocCompareError as exc:
        raise NotConnected("doccompare_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("doccompare_failed:" + type(exc).__name__) from None

def _docexport_call(method, args, config):
    """F58 红线/对比产物导出 PDF 桥（W4-U37）：产品侧 document_export 同
    进程公开面（document-adapter 家族）。

    纪律与 conversion.*/paper.* 产品面一致：未配置状态根/soffice=
    fail-closed NOT_CONNECTED；typed error（DocExportError 的 str 只有
    f58_* 错误码）透传，其他异常只带类型名——材料内容永不进入错误码。
    红线源经 U14 redline.redline b64 面取件；失败不交空 PDF（半成品导出
    目录整体清除）。
    """
    from document_export import docexport_call, DocExportError
    try:
        return docexport_call(method, args, config)
    except DocExportError as exc:
        raise NotConnected("docexport_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("docexport_failed:" + type(exc).__name__) from None

def _edits_call(method, args, config):
    """F48 <edits> 流式协议桥（W2b-U12）：产品侧 edits_protocol 同进程
    公开面（document-adapter，F54 conversion.* 同族）。

    纪律与 conversion.* 产品面一致：未配置状态根=fail-closed
    NOT_CONNECTED；typed error（EditsError 的 str 只有 f48_* 错误码或
    LOCATE_REASONS 卡级码）透传，其他异常只带类型名——材料内容永不进入
    错误码。文档字节经 edits.read_document base64 取件（宿主结果回流）。
    """
    from edits_protocol import edits_call, EditsError
    try:
        return edits_call(method, args, config)
    except EditsError as exc:
        raise NotConnected("edits_failed:" + str(exc)) from None
    except Exception as exc:
        # 同红线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("edits_failed:" + type(exc).__name__) from None

def _wps_host_call(method, args, config):
    """F46/F52 WPS 宿主半边桥（W2b-U36）：产品侧 wps_host 同进程公开面
    （document-adapter，通道②）。

    纪律与 edits.* 产品面一致：未配置状态根（review/decide）=fail-closed
    NOT_CONNECTED；typed error（WpsHostError 的 str 只有 wps46_* 错误码）
    透传，其他异常只带类型名——材料内容永不进入错误码。宿主结果字节经
    wpshost.decide 的 result_docx_b64 回流（harness formal_decide
    resultBytesB64 宿主侧来源）。
    """
    from wps_host import wps_host_call, WpsHostError
    try:
        return wps_host_call(method, args, config)
    except WpsHostError as exc:
        raise NotConnected("wps_host_failed:" + str(exc)) from None
    except Exception as exc:
        # 同基线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("wps_host_failed:" + type(exc).__name__) from None

def _wps_surface_call(method, args, config):
    """F17-wps WPS 宿主承载面桥（W2b-U50）：产品侧 wps_host_surface 同
    进程公开面（document-adapter 家族）。

    纪律同 _wps_host_call：未配置状态根（mount）=fail-closed NOT_CONNECTED；
    typed error（WpsSurfaceError 的 str 只有 f17wps_* 错误码）透传，其他
    异常只带类型名——材料内容永不进入错误码。投影只读：本桥不产生任何
    文档写入（零编辑实现），面板承载在宿主自身 UI。
    """
    from wps_host_surface import surface_call, WpsSurfaceError
    try:
        return surface_call(method, args, config)
    except WpsSurfaceError as exc:
        raise NotConnected("wps_surface_failed:" + str(exc)) from None
    except Exception as exc:
        # 同基线：失败面只带类型名，绝不携材料内容。
        raise NotConnected("wps_surface_failed:" + type(exc).__name__) from None

def _backup_call(method, args, config):
    """F11 backup bridge (W3-U11): product-side backup_restore face, same
    fail-closed convention as the document-adapter family — unconfigured
    state root/passphrase/targets fail NOT_CONNECTED; typed BackupError
    (str() is an f11_* code only) is transcribed verbatim; any other
    failure surfaces the exception type name, never material content."""
    from backup_restore import backup_call, BackupError
    try:
        return backup_call(method, args, config)
    except BackupError as exc:
        raise NotConnected("backup_failed:" + str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        # 同红线：失败面只带类型名，绝不携材料/映射内容。
        raise NotConnected("backup_failed:" + type(exc).__name__) from None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--request-json",type=Path,required=True)
    p.add_argument("--config",type=Path,required=True)
    a=p.parse_args()
    request=json.loads(a.request_json.read_text(encoding="utf-8-sig"))
    config=json.loads(a.config.read_text(encoding="utf-8-sig"))
    try:
        result=call(request["method"],request.get("args",{}),config)
        print(json.dumps({"status":"OWNER_RESPONSE","business_complete":False,"result":result},ensure_ascii=False,default=str))
        return 0
    except (NotConnected,ImportError) as exc:
        print(json.dumps({"status":"NOT_CONNECTED","code":str(exc),"business_complete":False},ensure_ascii=False))
        return 3
    except CaseProviderError as exc:
        print(json.dumps({"status":"CASE_ERROR","code":exc.code,"message":str(exc),"business_complete":False},ensure_ascii=False))
        return 4
    except JCMethodFailure as exc:
        print(json.dumps({"status":"JC_FAILURE","code":str(exc),"business_complete":False},ensure_ascii=False))
        return 4
    except HarnessCommandError as exc:
        print(json.dumps({"status":"HARNESS_FAIL","code":str(exc),"business_complete":False},ensure_ascii=False))
        return 1
    except SessionRejected as exc:
        print(json.dumps({"status":"SESSION_REJECTED","code":str(exc),"business_complete":False},ensure_ascii=False))
        return 2
    except ValueError as exc:
        print(json.dumps({"status":"INVALID_REQUEST","code":str(exc),"business_complete":False},ensure_ascii=False))
    except TransportError as exc:
        print(json.dumps({"status":"OUTCOME_UNKNOWN" if exc.uncertain else "ERROR","code":exc.code,"business_complete":False}))
        return 2
    return 2

if __name__=="__main__":
    # 脚本执行经同一模块副本跑 main（import legal_entry＝sys.modules 复用
    # 同一模块对象）：skill_semantics/review_chat 等产品面嵌套
    # legal_entry.call 时拿到的 JCMethodFailure/HarnessCommandError 与
    # main 的 except 是同一个类——exit 3/4 异常映射不因 __main__/模块双
    # 身份而漏接（漏接＝异常逃逸进程崩，stdout 空）。
    import legal_entry as _entry
    raise SystemExit(_entry.main())
