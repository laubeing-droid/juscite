# -*- coding: utf-8 -*-
"""F53 AI 修订作者与人工决定策略面（W2b-U49）：作者声明闭集＋决定引用投影。

义务 06:F53（17 卡；F53-desktop/F53-selfhost 双实例）：「修订author与真实
来源匹配，不默认伪装律师；律师接受有真实决定引用，保对外可见策略」。

三面（本模块＝唯一策略权威；U12/U14/U15 透传 author 先例收拢成策略面）：

- 作者声明闭集（author.policy / author.check）：机器生成修订的 author 是
  声明闭集，与真实产品通道一一绑定——
      redline  → lvyin-redline   （W2b-U14 document_redline，replay 红线）
      edits    → lvyin-edits     （W2b-U12 edits_protocol，流式编辑）
      docxedit → lvyin-docxedit  （W2b-U15 docx_edit，通道①清洁/批注）
  三个机器通道面（document_redline/edits_protocol/docx_edit）在各自 author
  入口经 check_revision_author 过闸：闭集外作者（含律师名）＝
  f53_author_impersonation 具名拒（机器生成不冒律师）；作者与通道错绑＝
  f53_author_channel_mismatch 具名拒。宿主通道（word/wps）的修订作者是
  宿主会话记录的真实操作者身份，不是机器生成，不入本闭集。
- 决定引用投影（author.projection）：『律师决定引用↔修订 author↔提案
  channel』三方可读投影＝对外可见策略。决定权威＝harness formal_decide
  （W2b-U11 已 VERIFIED，本单零 harness 改动）：accept/reject 必带
  reasonRef＋receiptRef（空决定面具名拒），bake 行 proposalRef 携提案
  channel/author、decisionRef 指向真实决定记录。本面经
  HARNESS_FORMAL_PROPOSAL_METHODS 冻结方法组（harness.formal_proposal_list）
  只读提案账，逐行校验三方一致后投影——只读呈现，不建第二账本。
- fail-closed 负向（全具名拒）：机器通道提案 author 闭集外＝
  f53_author_impersonation；accepted/rejected 行缺决定引用＝
  f53_decision_ref_missing；决定引用指向他案提案（decisionRef.proposalId
  ≠ 本行 proposalId）＝f53_cross_proposal_ref_mismatch；提案 channel/
  state 闭集外＝f53_proposal_channel_invalid / f53_proposal_state_invalid。
  投影绝不静默呈现伪造/错位行——任一行违例即整面响亮失败。

fail-closed：typed error（AuthorPolicyError 的 str 只有 f53_* 错误码，
绝不携材料内容）。零状态根（纯策略＋只读投影）；harness 决定面零改动。
"""
from __future__ import annotations

SCHEMA = "juscite-f53-author-policy/1"
PROJECTION_SCHEMA = "juscite-f53-author-decision-projection/1"

# 作者声明闭集：机器生成 author 与真实产品通道绑定（06:F53；17 卡）。
# 值即先例收拢：lvyin-redline＝U14 既有默认（DEFAULT_AUTHOR），lvyin-edits
# 与 lvyin-docxedit＝U12/U15 透传入参的闭集化归一；lvyin-templates＝
# W4-U38 template_drafting（F56 访谈式装配——新机器通道按同一策略过闸，
# F53 投影对模板装配提案可读，闭集外作者仍具名拒）。
# 与 lvyin-docxedit＝U12/U15 透传入参的闭集化归一；lvyin-cross-exam＝
# W4-U51 F120 质证意见生成（cross_exam.py，channel=machine 提案）。
# W5-U14 公开改口（W4-U38/W4-U51 同式）：闭集 5→6，增补
# proofing→lvyin-proofing＝F143 法律写作校对插件（document_proofing，
# 校对候选提案 channel=machine）；既有五绑定逐字不动。
CHANNEL_AUTHORS = {
    "redline": "lvyin-redline",     # W2b-U14 document_redline（replay 红线）
    "edits": "lvyin-edits",         # W2b-U12 edits_protocol（流式编辑）
    "docxedit": "lvyin-docxedit",   # W2b-U15 docx_edit（通道①编辑）
    "templates": "lvyin-templates",  # W4-U38 template_drafting（F56 装配）
    "crossexam": "lvyin-cross-exam",  # W4-U51 F120 质证意见生成
    "proofing": "lvyin-proofing",   # W5-U14 document_proofing（F143 校对）
}
MACHINE_AUTHORS = frozenset(CHANNEL_AUTHORS.values())
_AUTHOR_CHANNEL = {value: key for key, value in CHANNEL_AUTHORS.items()}

# 提案 channel 闭集（harness F47 FORMAL_PROPOSAL_CHANNELS 同集；投影面
# 闭集守卫用——harness 侧已拒，此处 fail-closed 双保险）。
PROPOSAL_CHANNELS = frozenset({"machine", "word", "wps"})
# 提案 state 闭集（harness F47 FORMAL_PROPOSAL_STATES 同集）。
PROPOSAL_STATES = frozenset({"pending", "accepted", "rejected", "superseded"})
# 有真实决定引用的状态（harness 决定面：accept/reject 必带 decisionRef；
# pending 无决定、superseded 被取代无决定——与人说不分列）。
DECIDED_STATES = frozenset({"accepted", "rejected"})

_HOST_AUTHOR_NOTE = "host_recorded_author"
_MACHINE_OK = "machine_author_ok"


class AuthorPolicyError(ValueError):
    """Typed F53 face failure; str() is a code, never material content."""


def check_revision_author(channel: str, author) -> dict:
    """机器通道修订作者过闸（U12/U14/U15 三个面在各自 author 入口调用）。

    闭集外作者（含律师名）＝f53_author_impersonation；作者与通道错绑＝
    f53_author_channel_mismatch；通道未知＝f53_channel_unknown。返回绑定
    记录（调用方可入提案/清单元数据），绝不改写作者值。"""
    if channel not in CHANNEL_AUTHORS:
        raise AuthorPolicyError("f53_channel_unknown:" + str(channel))
    if not isinstance(author, str) or not author:
        raise AuthorPolicyError("f53_author_required")
    if author not in MACHINE_AUTHORS:
        # 机器生成修订不得署闭集外作者——冒充律师名在此具名拒。
        raise AuthorPolicyError("f53_author_impersonation:" + channel)
    if author != CHANNEL_AUTHORS[channel]:
        raise AuthorPolicyError(
            f"f53_author_channel_mismatch:{author}:{channel}")
    return {"channel": channel, "author": author, "kind": "machine"}


def policy_view() -> dict:
    """author.policy：策略描述（闭集＋绑定＋规则；只读）。"""
    return {
        "schema": SCHEMA,
        "policy": "f53-author-decision/1",
        "machine_channels": {
            channel: {"author": author, "kind": "machine"}
            for channel, author in CHANNEL_AUTHORS.items()},
        "host_channels": sorted(PROPOSAL_CHANNELS - {"machine"}),
        "rules": (
            "machine_channel_author_closed_set",
            "author_channel_binding",
            "no_lawyer_impersonation",
            "accept_requires_real_decision_ref",
            "external_visibility_projection_readonly",
        ),
        "decision_authority": "harness formal_decide (W2b-U11, untouched)",
    }


def _row_author_policy(channel: str, author) -> dict:
    """行级作者策略判定（投影用；只判不抛——违例由投影整体具名拒）。"""
    if channel == "machine":
        binding = _AUTHOR_CHANNEL.get(author)
        if binding is None:
            return {"kind": "machine", "status": "f53_author_impersonation"}
        return {"kind": "machine", "status": _MACHINE_OK,
                "boundChannel": binding}
    return {"kind": "host", "status": _HOST_AUTHOR_NOTE}


def decision_projection(listing: dict, matter_id: str,
                        material_id: str) -> dict:
    """三方投影（纯函数）：harness.formal_proposal_list 载荷 → 『律师决定
    引用↔修订 author↔提案 channel』可读投影。任一行违例＝整面具名拒
    （fail-closed，绝不静默呈现伪造/错位行）。"""
    if not isinstance(listing, dict) or not isinstance(
            listing.get("proposals"), list) \
            or not isinstance(listing.get("canonical"), dict):
        raise AuthorPolicyError("f53_listing_invalid")
    rows = []
    for proposal in listing["proposals"]:
        if not isinstance(proposal, dict):
            raise AuthorPolicyError("f53_listing_invalid")
        proposal_id = proposal.get("proposalId")
        channel = proposal.get("channel")
        author = proposal.get("author")
        state = proposal.get("state")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise AuthorPolicyError("f53_proposal_id_missing")
        if channel not in PROPOSAL_CHANNELS:
            raise AuthorPolicyError(
                f"f53_proposal_channel_invalid:{proposal_id}")
        if state not in PROPOSAL_STATES:
            raise AuthorPolicyError(
                f"f53_proposal_state_invalid:{proposal_id}")
        # 负向一：机器通道提案冒充律师名（闭集外作者）。
        row_policy = _row_author_policy(channel, author)
        if row_policy["status"] == "f53_author_impersonation":
            raise AuthorPolicyError(
                f"f53_author_impersonation:{proposal_id}")
        decision = proposal.get("decisionRef")
        # 负向二：决定态行缺真实决定引用（律师接受必带决定引用）。
        if state in DECIDED_STATES:
            if not isinstance(decision, dict) or not decision.get(
                    "decisionId") or not decision.get("receiptRef"):
                raise AuthorPolicyError(
                    f"f53_decision_ref_missing:{proposal_id}")
            # 负向三：跨提案引用错位（决定引用指向别的提案）。
            ref_proposal = decision.get("proposalId")
            if ref_proposal is not None and ref_proposal != proposal_id:
                raise AuthorPolicyError(
                    "f53_cross_proposal_ref_mismatch:"
                    f"{ref_proposal}:{proposal_id}")
        elif decision is not None:
            # pending/superseded 行不该有决定（无决定被取代＝superseded，
            # 与人说不分列——harness 决定面保证；投影面 fail-closed 守卫）。
            raise AuthorPolicyError(
                f"f53_decision_on_undecided:{proposal_id}")
        rows.append({
            "proposalId": proposal_id,
            "seq": proposal.get("seq"),
            "state": state,
            "channel": channel,
            "author": author,
            "authorPolicy": row_policy,
            "decision": decision,
            "bakedRevision": proposal.get("bakedRevision"),
            "supersededBy": proposal.get("supersededBy"),
            "decidedAt": proposal.get("decidedAt"),
        })
    return {
        "schema": PROJECTION_SCHEMA,
        "matterId": matter_id,
        "materialId": material_id,
        "canonical": {
            "revision": listing["canonical"].get("revision"),
            "source": listing["canonical"].get("source"),
            "sha256": listing["canonical"].get("sha256"),
        },
        "rows": rows,
        "visibility": {
            "authorVisible": True,       # 修订作者（机器闭集/宿主记录）对外可见
            "decisionVisible": True,     # 律师决定引用对外可见
            "policy": "f53-external-visibility/1",
        },
    }


def author_policy_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry author.* 唯一分发（fail-closed 同基线；零状态根）。"""
    if method == "author.policy":
        return policy_view()
    if method == "author.check":
        if not isinstance(args, dict):
            raise AuthorPolicyError("f53_params_invalid")
        return check_revision_author(args.get("channel"), args.get("author"))
    if method == "author.projection":
        if not isinstance(args, dict):
            raise AuthorPolicyError("f53_params_invalid")
        matter_id = args.get("matter_id") or args.get("matterId")
        material_id = args.get("material_id") or args.get("materialId")
        if not isinstance(matter_id, str) or not matter_id \
                or not isinstance(material_id, str) or not material_id:
            raise AuthorPolicyError("f53_material_ref_required")
        scope = args.get("scope") or {"kind": "matter", "matterId": matter_id}
        listing = _harness_call("harness.formal_proposal_list", {
            "scope": scope, "material_id": material_id}, config)
        return decision_projection(listing, matter_id, material_id)
    raise AuthorPolicyError("f53_method_unknown:" + method)


def _harness_call(method: str, args: dict, config: dict) -> dict:
    """harness 公开面分派 seam（默认＝legal_entry.call 冻结方法组；只读
    消费 HARNESS_FORMAL_PROPOSAL_METHODS，零 harness 改动）。"""
    import legal_entry
    return legal_entry.call(method, args, config)
