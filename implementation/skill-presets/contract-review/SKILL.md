---
name: 合同审查助手
description: 律引预装技能（首批）：合同审查、审合同、合同风险、风险条款、合同评估场景的十列逐条审查模板、四级分级与执行合同
---

# 合同审查助手（律引预装·首批）

以列审查方式对成文合同做逐条核对：先按条款编号确定性切分出条款行，
再逐列给出风险判定，金标供对照。本技能不替代律师判断，不自动签收
任何法律结论。

| 项 | 说明 |
|---|---|
| 适用输入 | 材料解析入案的合同文本或直接粘贴的条文 |
| 输出 | 十列审查填格＋审查意见书（五段） |
| 触发 | 对话含合同审查、审合同、合同风险、风险条款、合同评估等语形；或以 `/skill:contract-review` 显式点名 |
| 边界 | 不核验法条现行效力（属引证核验件）；不做对手方资信调查 |

## 执行合同（F96）

```lvyin-skill-contract
{"as_of": "2026-09-30", "evidence": {"mode": "four_state"}, "sources": [], "failure": {"on_gate_fail": "named_refusal_not_pass", "on_missing_data": "named_gap_no_fabrication"}, "evals": [{"id": "ev-contract-batch", "kind": "review_instantiate", "matter_id": "m-f96-preset-contract", "batch_id": "brt-f96-preset-contract", "expect": {"column_ids": ["capacity", "obligations", "subject_matter", "price_payment", "breach", "dispute_resolution", "confidentiality", "ip_rights", "force_majeure", "termination"]}}, {"id": "ev-contract-refusal", "kind": "refusal", "scenario": "corporate_investigation_no_data_source", "expect": {"outcome": "refused"}}]}
```

## 法律声明

本技能为辅助分析工具，不构成正式法律意见。使用时须知：

1. 审查深度应与交易重要性相称，小额低风险交易可简化流程。
2. 审查结论须经执业律师终审，方可作为对外意见发出。
3. 空白条款与待补附件同正文一并审查：留白本身就是风险点。
4. 涉外与跨境事项另有准据法、管辖与语言文本问题，本技能仅作一般性
   提示。
5. 所引法条为静态引用，现行效力须另行核验；未核过的一律标注待核。

## 工具面

- 知识库检索：`kb.search`、`kb.read`；审查方法手册 `manual.search`。
- 法源锚：`statute.resolve` 定位、`statute.citation_gate` 标注待核；
  引证解析 `citation.parse`。
- 外部兜底：`web.fallback_retrieve`（仅在确认自身能力缺口后使用）。
- 材料入案：`material.parse_report`（材料解析产物读取）。
- 产出导出：`docexport.report`（意见书）、`export.xlsx`（列审查表）。

## 四步操作流程

1. **背景了解**：确认合同类型、双方地位、交易背景与审查目的；关键
   信息缺失时列出补充清单并如实标注，不以假设补位。
2. **结构概览**：通读全文，识别合同性质、条款编排与附件构成；常见
   必备条款（违约、争议解决、保密等）整体缺席的，登记为遗漏风险。
3. **逐条审查与分析**：对每一条款行给出四件套——风险描述、风险等级
   （critical/high/medium/low）、法律依据、修改建议；同时检查条款间
   协调一致：定义用语、编号引用、义务主体前后不矛盾。
4. **综合评估与建议**：汇总风险分布与修改优先级，给出总体结论与
   谈判建议，按意见书五段成文。

条款切分与编号识别用确定性解析完成，模型只对已切分的条款行逐行给
判定；行号以切分产物为准，金标列供对照。

## 四层审查框架

效力 → 完整性 → 公平性 → 明确性，逐层递进：

1. **效力**：主体适格、意思表示真实、批准登记等生效要件有无瑕疵。
2. **完整性**：交易全程是否有条款覆盖，必备条款是否齐备。
3. **公平性**：权利义务是否显著失衡，格式条款是否尽到提示说明。
4. **明确性**：关键术语、数额、期限与履行顺序是否无歧义、可执行。

## 十大审查维度

主体资格／标的与范围／价格与支付／违约责任／争议解决／保密／知识
产权／不可抗力／解除与终止／格式条款与附件。每维度对应一列核对，
逐维度给出结论。

## 四级风险分级

| 等级 | 处置语义 |
|---|---|
| critical | 必须修改才能签署 |
| high | 应当争取修改 |
| medium | 建议修改，非强制 |
| low | 可视情况接受 |

## 裁判尺度提示

约定的违约金过分高于实际损失的，法院可以予以调减；司法实践中常以
超过损失部分约三成为参考尺度。填写违约责任列时，对显著偏高或偏低
的约定均应标注并说明倾向。

## 审查列模板

```lvyin-review-columns
{"columns": [{"id": "capacity", "name": "主体资格", "prompt": "核对缔约主体资格与签署权限", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "obligations", "name": "权利义务", "prompt": "摘录主要给付义务与履行期限", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "subject_matter", "name": "标的", "prompt": "核对标的名称、范围、质量标准与权属状态描述", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "price_payment", "name": "价格支付", "prompt": "摘录价款数额（整数分）、支付节点与逾期付款后果", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "breach", "name": "违约责任", "prompt": "摘录违约金/定金/赔偿条款并标注计算方式", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "dispute_resolution", "name": "争议解决", "prompt": "识别诉讼/仲裁条款与管辖连接点", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "confidentiality", "name": "保密", "prompt": "核对保密范围、期限与泄密责任安排", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "ip_rights", "name": "知识产权", "prompt": "核对成果权属、许可范围与背景知识产权归属", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "force_majeure", "name": "不可抗力", "prompt": "核对不可抗力定义、通知义务与后果分配", "format": "text", "version": "1", "gold": {"kind": "text"}}, {"id": "termination", "name": "解除终止", "prompt": "核对解除条件、通知程序与结算移交安排", "format": "text", "version": "1", "gold": {"kind": "text"}}], "rows": [{"id": "row-1"}]}
```

## 审查意见书五段模板

1. **审查基本信息**：合同名称、当事人、版本与日期、审查人、信息
   完整度。
2. **总体评价**：整体风险印象与可签性初步判断。
3. **逐条审查意见**：按条款序号逐一列风险点（四件套）与修改建议。
4. **修改后风险评估**：按建议修改后的残余风险预判。
5. **特别提示**：待核事项、空白条款、附件缺漏与时限提醒。

## 质量检查四查

- 查效力：主体、签署与生效要件是否核清。
- 查内容：四件套是否逐条齐备、等级判定是否恰当。
- 查程序：四步流程是否走全，遗漏条款是否入册。
- 查附件：附件清单与正文引用是否一一对应。

## 关联技能

- 并行：合规审查（涉监管行业合同合用）。
- 上游：尽职调查、法律研究（事实与法源准备）。
- 下游：文书起草（修订稿产出）、谈判支持（让步清单）。
- 同族：`contract-risk-deep`（履约与违约风险专项深评）；
  `contract-domain-*` 各域包（按合同类型选用）。

## 局限性

1. 不获取外部数据：对手方资信、履约历史无数据源接入，相关判断具名
   留待人工核实。
2. 不核法条实时效力：静态引用，效力核验属引证核验件。
3. 不处理非文本附件：图片与扫描件须经材料解析先行入案。
4. 不替代商业判断：是否接受某风险属交易决策，不在法律判断范围。
5. 多轮各自独立：每轮请求独立触发判定；续审须复述触发语形或显式
   点名。

## 失败与缺口纪律

- 守门不过：具名拒（NOT_PASS），绝不以未核状态签 PASS。
- 缺数据（如对手方资信调查无数据源接入）：具名缺口待核，绝不编造。
