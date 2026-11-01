---
name: 建设工程审阅
description: 律引预装技能（RE-12）：建设工程合同域专项——工期、质量、结算调价、签证变更与保修的逐条审阅
---

# 建设工程审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 承包人进行工程建设、发包人支付价款的施工类合同；
- 施工总承包/专业分包/劳务分包的层级安排；
- 装饰装修、市政配套等按工程量计价的建设类合同。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 工期与进度（开竣工日、顺延事由、赶工）
- 质量与验收（标准、隐蔽工程、竣工验收）
- 价款与结算（计价方式、调价、支付节点）
- 签证与变更（程序、权限、计价连带）
- 安全文明施工（责任、保险）
- 保修与缺陷责任（范围、期限、金）

## 域专项审查重点

- 签证变更程序是否可执行：签证权限人、时限、逾期视同认可条款逐项核；
- 计价方式与调价条款咬合：固定价/可调价/成本加酬金对应的风险分配；
- 隐蔽工程中间验收与复工条件，未验收即覆盖的责任划分；
- 竣工结算报送与答复期限及逾期未答复的后果约定；
- 垫资条款与利息约定单独标注。

## 域法源锚（静态引用·效力待核）

- 《民法典》建设工程合同章（第 788 条起）——勘察设计施工、隐蔽工程验收、建设工程价款优先受偿等规则；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 开工日期与施工许可日期不一致导致工期起算争议；
- 变更只有口头指令无签证程序，结算无据；
- 质量保证金返还期限与缺陷责任期不咬合；
- 转包/违法分包安排导致合同效力与责任主体存疑。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "schedule", "name": "工期进度", "prompt": "核对开竣工日期、顺延事由与赶工安排", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "work_quality", "name": "工程质量", "prompt": "核对验收标准、隐蔽工程程序与整改责任", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "settlement", "name": "结算调价", "prompt": "摘录计价方式、调价触发与结算答复期限", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "change_visa", "name": "签证变更", "prompt": "核对签证权限、程序时限与计价连带", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "warranty", "name": "保修责任", "prompt": "核对保修范围、期限与保证金返还安排", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domconstr-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-constr", "batch_id": "brt-f96-preset-dom-constr", "expect": {"column_ids": ["change_visa", "schedule", "settlement", "warranty", "work_quality"]}}, {"id": "ev-domconstr-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
