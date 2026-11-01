---
name: 律引计算助手
description: 律引预装技能（首批）：计算步骤块经 JC 公开面真实计算与执行合同
---

# 律引计算助手（律引预装·首批）

计算技能：计算步骤声明经既有 calc.* 冻结方法组（P01 JCClient 同一钉定
公开面）真实计算；JC typed 拒绝原样上浮，绝不造数；金额一律 Decimal/整
数分。rule/calendar 版本以 JC registry 调用时解析为准。

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-calc-leapday", "kind": "calculation", "matter_id": "m-f96-preset-calc", "input": {"principal_minor": 365000, "segments": [{"start_date": "2024-02-28", "end_date": "2024-03-01", "annual_rate": "0.01"}]}, "expect": {"amount_minor": 20}}, {"id": "ev-calc-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 计算步骤块

```lvyin-calc-step
{"method": "calc.interest", "rule_version": "lvyin-presets-batch1 声明面（JC registry 调用时解析）", "calendar_version": "lvyin-presets-batch1 声明面（JC 2026 版本包声明面）", "input_domain": ["principal_minor", "segments"]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据：具名缺口待核，绝不编造计算输入或结果。
