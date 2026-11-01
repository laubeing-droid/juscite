---
name: 结案审查助手
description: 律引预装技能（首批）：结案归档审查列模板与执行合同
---

# 结案审查助手（律引预装·首批）

结案阶段以列审查方式核对：裁判结果、费用结算、归档材料、后续事项。
列由审查者逐项填写，金标供对照；本技能不替代律师判断。

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-close-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-close", "batch_id": "brt-f96-preset-close", "expect": {"column_ids": ["outcome", "fees", "archive", "followups"]}}, {"id": "ev-close-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "outcome", "name": "裁判/处理结果", "prompt": "摘录裁判主文或处理结论", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "fees", "name": "费用结算（分）", "prompt": "汇总办案费用，整数分（Decimal 语义）", "format": "decimal-string", "version": "1", "gold": {"kind": "number"}}, {"id": "archive", "name": "归档材料", "prompt": "核对归档材料清单完整性", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "followups", "name": "后续事项", "prompt": "列明履行跟进/执行/上诉等后续事项与期限", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如对手方履行能力调查无数据源接入）：具名缺口待核，绝不编造。
