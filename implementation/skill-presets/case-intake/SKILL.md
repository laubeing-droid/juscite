---
name: 接案审查助手
description: 律引预装技能（首批）：接案阶段的委托事项审查列模板与执行合同
---

# 接案审查助手（律引预装·首批）

接案阶段以列审查方式核对委托事项：当事人、案由、管辖、时效、标的额。
列由审查者逐项填写，金标供对照；本技能不替代律师判断，不自动签收任何
法律结论。

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-intake-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-intake", "batch_id": "brt-f96-preset-intake", "expect": {"column_ids": ["parties", "cause", "jurisdiction", "limitation", "claim_amount"]}}, {"id": "ev-intake-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "parties", "name": "当事人", "prompt": "核对委托人与对方当事人主体信息，整数序号留空待填", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "cause", "name": "案由", "prompt": "按受诉法院案由名录填写案由", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "jurisdiction", "name": "管辖", "prompt": "核对约定管辖/法定管辖依据与连接点", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "limitation", "name": "时效", "prompt": "识别请求权基础并计算时效届满日（YYYY-MM-DD）", "format": "date", "version": "1", "gold": {"kind": "date"}}, {"id": "claim_amount", "name": "标的额（分）", "prompt": "填写诉讼标的额，整数分（Decimal 语义）", "format": "decimal-string", "version": "1", "gold": {"kind": "number"}}], "rows": [{"id": "row-1"}, {"id": "row-2"}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如对手方工商背景调查无数据源接入）：具名缺口待核，绝不编造
  企业调查数据。
