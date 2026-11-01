---
name: 通用交易审阅
description: 律引预装技能（RE-12）：合同类型不明或跨域交易时的通用审阅入口——类型判定、核心条款清单、通用法源锚与域风险骨架
---

# 通用交易审阅（律引预装·RE-12）

本包是合同审查家族的域专项件：在主审查技能（`contract-review`）的
四步流程与十列模板之上，就本域合同做条款清单、审查重点与法源锚的
定向补充。本技能不替代律师判断，不自动签收任何法律结论。

## 适用合同类型判定

满足任一特征即适用本包：

- 文本显示的是双务有偿交易，但难以归入买卖/租赁/服务/开发等典型域；
- 混合型协议（如框架协议＋订单）需要先立通用骨架再分流；
- 交易要素残缺，先按通用清单盘点缺什么再决定专项深评。

不匹配时改用 `contract-domain-general` 通用入口，或按主审查技能的
十大维度做通用审。

## 域核心条款清单

- 主体与签署（资格、权限、签署人）
- 标的与范围（交易什么、边界在哪）
- 对价与支付（数额、币种、节点、票据）
- 履行安排（期限、地点、顺序、验收）
- 违约与救济（情形、责任、计算、上限）
- 争议解决与适用法律

## 域专项审查重点

- 先用四层框架过一遍：效力→完整性→公平性→明确性；
- 对无法归域的条款，标注「域归属待定」，不强行套用专项规则；
- 完成通用审后，按条文章节特征建议改用对应域包复审。

## 域法源锚（静态引用·效力待核）

- 《民法典》合同编通则（第 463 条起）——合同订立、效力、履行、保全、变更转让、终止的通用规则；
- 以上为静态引用，现行效力核验属引证核验件，未核前标注待核。

## 域风险清单骨架

高频风险点（逐条核对，命中即入列并按四件套登记）：

- 必备条款整体缺失（无违约/争议解决条款的交易）；
- 对价与义务明显不对称且无对价说明；
- 签署主体与正文当事方名称不一致；
- 期限、数额等关键要素留白。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "parties", "name": "主体", "prompt": "核对缔约主体资格、签署权限与当事方名称一致性", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "subject", "name": "标的", "prompt": "核对交易标的范围与边界描述是否可执行", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "consideration", "name": "对价", "prompt": "摘录价款数额（整数分）、支付方式与节点", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "breach", "name": "违约", "prompt": "核对违约情形、责任形式与计算方式", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "dispute", "name": "争议", "prompt": "核对争议解决方式、管辖连接点与适用法律", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-domgeneral-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-dom-general", "batch_id": "brt-f96-preset-dom-general", "expect": {"column_ids": ["breach", "consideration", "dispute", "parties", "subject"]}}, {"id": "ev-domgeneral-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如登记公示信息无数据源接入）：具名缺口待核，绝不编造。
