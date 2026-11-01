---
name: 技术开发审阅
description: 律引预装技能（RE-12）：技术开发合同域专项——开发节点、成果知识产权、验收交付与保密的逐条审阅
---

# 技术开发审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 新技术/新产品/新工艺的研究开发安排（委托或合作开发）；
- 软件开发、系统集成等以技术成果为标的的开发合同；
- 技术开发与许可、转让组合的混合安排。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 开发内容与技术指标（功能清单、性能参数）
- 计划与节点（里程碑、延期处理）
- 开发经费与报酬（支付节点、超支承担）
- 成果归属（专利/软件著作权/技术秘密）
- 验收与交付（测试标准、源代码、文档）
- 保密与后续改进（范围、期限、改进归属）

## 域专项审查重点

- 技术指标必须可测：无量化参数的验收条款标注待补；
- 成果归属默认规则与约定不一致时的约定优先表述；
- 源代码与文档交付范围（含注释、构建脚本与否）逐项列明；
- 背景知识产权与前景知识产权分别定义；
- 技术秘密保护期限与保密义务存续期区分。

## 域法源锚（静态引用·效力待核）

- 《民法典》技术合同章（第 843 条起；技术开发合同第 851 条起）——成果归属、风险负担、验收等规则；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 验收仅以「运行正常」表述，无可复现测试用例；
- 成果归属未约定或与付款进度脱钩；
- 延期违约金与开发费上限不匹配（失衡标注）；
- 保密义务无期限或过宽至公共信息。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "milestone", "name": "开发节点", "prompt": "核对里程碑、交付物与延期处理安排", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "ip_ownership", "name": "成果权属", "prompt": "核对专利/著作权/技术秘密归属与背景知识产权划分", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "acceptance", "name": "验收交付", "prompt": "核对量化指标、测试程序与源码文档交付范围", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "confidential", "name": "保密", "prompt": "核对保密范围、期限与例外情形", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domtechdev-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-techdev", "batch_id": "brt-f96-preset-dom-techdev", "expect": {"column_ids": ["acceptance", "confidential", "ip_ownership", "milestone"]}}, {"id": "ev-domtechdev-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
