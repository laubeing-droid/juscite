---
name: 法院来件助手
description: 律引预装技能（首批）：法院来件核对列模板与执行合同
---

# 法院来件助手（律引预装·首批）

收到法院来件（传票/通知/裁定等）以列审查方式核对：案号、当事人、事项、
期限、材料清单。列由审查者逐项填写，金标供对照；期限事项另行走确定性
日历面，本技能不产生程序期限。

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-court-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-court", "batch_id": "brt-f96-preset-court", "expect": {"column_ids": ["case_no", "parties", "matter", "deadline", "documents"]}}, {"id": "ev-court-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "case_no", "name": "案号", "prompt": "按来件原文摘录案号（正则核对年度与法院代字）", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "parties", "name": "当事人", "prompt": "摘录来件载明的当事人及诉讼地位", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "matter", "name": "事项", "prompt": "摘录传票/通知事项（开庭/举证/谈话等）", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "deadline", "name": "期限", "prompt": "摘录来件载明的期限（YYYY-MM-DD）", "format": "date", "version": "1", "gold": {"kind": "date"}}, {"id": "documents", "name": "材料清单", "prompt": "列明来件要求提交的材料", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如对手方背景调查无数据源接入）：具名缺口待核，绝不编造。
