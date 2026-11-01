// 功能 #10 模板文书起草（RE-10）纯逻辑引擎 —— 零依赖，静态模板资源 + 解析器 + 判定启发式。
// 表达隔离（RE-10 §5）：模板集/案由条目/prompt 全部自写（法律方法结构等量，文案不抄竞品）。
// 对拍口径：目录 40 模板（诉讼 20+非诉 20）；隐藏结构模板 11 案由×(起诉|答辩)；匹配=归一化子串最长优先，不命中不猜。

// ---------- 内部构建器 ----------
function F(id, label, type, extra) {
  return { id, label, type, ...(extra ?? {}) };
}
function T(id, name, category, description, fields, body, legalBasis, icon) {
  return { id, name, category, description, fields, content: body, legalBasis, icon: icon ?? "file-text" };
}

const LF = "《中华人民共和国民事诉讼法》";
const CIVIL_CODE = "《中华人民共和国民法典》";

// ---------- 内置可见目录模板（40：litigation 20 + non-litigation 20） ----------
const LITIGATION_TEMPLATES = [
  T("lt-civil-complaint", "民事起诉状（通用）", "litigation", "一般民事纠纷起诉用", [
    F("plaintiff", "原告", "text"), F("defendant", "被告", "text"), F("claims", "诉讼请求", "textarea"),
    F("facts", "事实与理由", "textarea"), F("court", "受诉法院", "text"), F("evidence", "证据清单", "textarea"),
  ], "# 民事起诉状\n\n## 案号与案由\n案由：{{案由}}\n\n## 当事人信息\n原告：{{原告}}　住所：{{原告住所}}　联系方式：{{原告联系方式}}\n被告：{{被告}}　住所：{{被告住所}}\n\n## 诉讼请求和依据\n{{诉讼请求}}\n\n## 事实和理由\n{{事实与理由}}\n\n## 管辖、保全与其他说明\n本案由{{受诉法院}}管辖。\n\n## 证据清单\n{{证据清单}}\n\n此致\n\n{{受诉法院}}\n\n具状人：{{原告签字或盖章}}\n{{具状日期}}", "依据" + LF + "关于起诉条件的规定", "scale"),
  T("lt-civil-answer", "民事答辩状", "litigation", "被告应诉答辩用", [
    F("respondent", "答辩人", "text"), F("plaintiff", "被答辩人（原告）", "text"), F("defensePoints", "答辩意见", "textarea"),
    F("facts", "事实与理由", "textarea"), F("court", "受诉法院", "text"),
  ], "# 民事答辩状\n\n答辩人：{{答辩人}}\n被答辩人：{{被答辩人（原告）}}\n\n## 案号与案由\n案号：{{案号}}　案由：{{案由}}\n\n## 答辩事项和依据\n{{答辩意见}}\n\n## 事实和理由\n{{事实与理由}}\n\n## 管辖、保全与其他说明\n{{管辖异议说明}}\n\n此致\n\n{{受诉法院}}\n\n答辩人：{{答辩人签字或盖章}}\n{{答辩日期}}", "依据" + LF + "关于答辩期间的规定", "shield"),
  T("lt-civil-appeal", "民事上诉状", "litigation", "不服一审判决上诉用", [
    F("appellant", "上诉人", "text"), F("appellee", "被上诉人", "text"), F("firstCaseNo", "一审判决案号", "text"),
    F("appealRequests", "上诉请求", "textarea"), F("appealGrounds", "上诉理由", "textarea"),
  ], "# 民事上诉状\n\n上诉人：{{上诉人}}\n被上诉人：{{被上诉人}}\n\n## 上诉请求和依据\n{{上诉请求}}\n\n## 事实和理由\n{{上诉理由}}\n\n此致\n\n{{二审法院}}\n\n上诉人：{{上诉人签字或盖章}}\n{{上诉日期}}", "依据" + LF + "关于上诉的规定", "arrow-up-circle"),
  T("lt-counterclaim", "民事反诉状", "litigation", "被告在本诉中提起反诉", [
    F("counterPlaintiff", "反诉原告（本诉被告）", "text"), F("counterDefendant", "反诉被告（本诉原告）", "text"),
    F("counterClaims", "反诉请求", "textarea"), F("counterFacts", "事实与理由", "textarea"),
  ], "# 民事反诉状\n\n反诉原告：{{反诉原告（本诉被告）}}\n反诉被告：{{反诉被告（本诉原告）}}\n\n## 反诉请求和依据\n{{反诉请求}}\n\n## 事实和理由\n{{事实与理由}}\n\n此致\n\n{{受诉法院}}\n\n反诉原告：{{签字或盖章}}\n{{日期}}", "依据" + LF + "关于反诉的规定", "repeat"),
  T("lt-retrial", "再审申请书", "litigation", "对生效裁判申请再审", [
    F("applicant", "再审申请人", "text"), F("effectiveDoc", "生效裁判文号", "text"), F("grounds", "再审事由", "textarea"), F("requests", "再审请求", "textarea"),
  ], "# 再审申请书\n\n再审申请人：{{再审申请人}}\n生效裁判文号：{{生效裁判文号}}\n\n## 再审请求和依据\n{{再审请求}}\n\n## 事实和理由\n{{再审事由}}\n\n此致\n\n{{受理法院}}\n\n申请人：{{签字或盖章}}\n{{日期}}", "依据" + LF + "关于审判监督程序的规定", "rotate-ccw"),
  T("lt-enforcement", "强制执行申请书", "litigation", "生效文书申请强制执行", [
    F("applicant", "申请执行人", "text"), F("respondent", "被执行人", "text"), F("effectiveDoc", "生效法律文书", "text"),
    F("execTarget", "执行标的", "text"), F("execRequests", "执行请求", "textarea"),
  ], "# 强制执行申请书\n\n申请执行人：{{申请执行人}}\n被执行人：{{被执行人}}\n生效法律文书：{{生效法律文书}}\n\n## 执行请求和依据\n{{执行请求}}\n执行标的：{{执行标的}}\n\n## 事实和理由\n{{事实与理由}}\n\n此致\n\n{{执行法院}}\n\n申请执行人：{{签字或盖章}}\n{{日期}}", "依据" + LF + "关于执行程序的规定", "gavel"),
  T("lt-asset-preserve", "财产保全申请书", "litigation", "诉前/诉中财产保全", [
    F("applicant", "申请人", "text"), F("respondent", "被申请人", "text"), F("preserveAssets", "请求保全财产", "textarea"), F("preserveReason", "保全理由", "textarea"),
  ], "# 财产保全申请书\n\n申请人：{{申请人}}\n被申请人：{{被申请人}}\n\n## 保全请求和依据\n请求查封、扣押、冻结被申请人下列财产：\n{{请求保全财产}}\n\n## 事实和理由\n{{保全理由}}\n担保情况：{{担保情况}}\n\n此致\n\n{{受诉法院}}\n\n申请人：{{签字或盖章}}\n{{日期}}", "依据" + LF + "关于财产保全的规定", "lock"),
  T("lt-evidence-preserve", "证据保全申请书", "litigation", "证据可能灭失时申请保全", [
    F("applicant", "申请人", "text"), F("evidenceDesc", "申请保全的证据", "textarea"), F("urgencyReason", "紧急情况说明", "textarea"),
  ], "# 证据保全申请书\n\n申请人：{{申请人}}\n\n## 保全请求和依据\n申请保全的证据：{{申请保全的证据}}\n\n## 事实和理由\n因{{紧急情况说明}}，证据可能灭失或以后难以取得，特申请证据保全。\n\n此致\n\n{{受诉法院}}\n\n申请人：{{签字或盖章}}\n{{日期}}", "依据" + LF + "关于证据保全的规定", "archive"),
  T("lt-advance-exec", "先予执行申请书", "litigation", "追索赡养费/扶养费/劳动报酬等先予执行", [
    F("applicant", "申请人", "text"), F("respondent", "被申请人", "text"), F("advanceItem", "先予执行事项", "textarea"), F("advanceReason", "先予执行理由", "textarea"),
  ], "# 先予执行申请书\n\n申请人：{{申请人}}\n被申请人：{{被申请人}}\n\n## 先予执行请求和依据\n{{先予执行事项}}\n\n## 事实和理由\n{{先予执行理由}}\n\n此致\n\n{{受诉法院}}\n\n申请人：{{签字或盖章}}\n{{日期}}", "依据" + LF + "关于先予执行的规定", "zap"),
  T("lt-jurisdiction-objection", "管辖权异议申请书", "litigation", "对受诉法院管辖提出异议", [
    F("objector", "异议人", "text"), F("caseNo", "案件案号", "text"), F("objectionGrounds", "异议理由", "textarea"),
  ], "# 管辖权异议申请书\n\n异议人：{{异议人}}\n案件案号：{{案件案号}}\n\n## 异议请求和依据\n请求将本案移送有管辖权的法院（{{有管辖权法院}}）审理。\n\n## 事实和理由\n{{异议理由}}\n\n此致\n\n{{受诉法院}}\n\n异议人：{{签字或盖章}}\n{{日期}}", "依据" + LF + "关于管辖的规定", "map-pin"),
  T("lt-criminal-private-prosecution", "刑事自诉状", "litigation", "自诉案件直接向法院起诉", [
    F("privateProsecutor", "自诉人", "text"), F("defendant", "被告人", "text"), F("charges", "控告罪名与事实", "textarea"), F("criminalRequests", "诉讼请求", "textarea"),
  ], "# 刑事自诉状\n\n自诉人：{{自诉人}}\n被告人：{{被告人}}\n\n## 诉讼请求和依据\n{{诉讼请求}}\n\n## 事实和理由\n{{控告罪名与事实}}\n\n## 证据清单\n{{证据清单}}\n\n此致\n\n{{受诉法院}}\n\n自诉人：{{签字或盖章}}\n{{日期}}", "依据《中华人民共和国刑事诉讼法》关于自诉的规定", "alert-triangle"),
  T("lt-criminal-incidental-civil", "刑事附带民事起诉状", "litigation", "刑事案件中附带民事赔偿", [
    F("plaintiff", "附带民事原告人", "text"), F("defendant", "附带民事被告人", "text"), F("compensationClaims", "赔偿请求", "textarea"), F("lossDetail", "损失明细", "textarea"),
  ], "# 刑事附带民事起诉状\n\n附带民事原告人：{{附带民事原告人}}\n附带民事被告人：{{附带民事被告人}}\n\n## 诉讼请求和依据\n{{赔偿请求}}\n\n## 事实和理由\n{{犯罪行为与损失明细}}\n\n此致\n\n{{受诉法院}}\n\n原告人：{{签字或盖章}}\n{{日期}}", "依据《中华人民共和国刑事诉讼法》关于附带民事诉讼的规定", "scale"),
  T("lt-criminal-appeal", "刑事上诉状", "litigation", "不服一审判决刑事上诉", [
    F("appellant", "上诉人", "text"), F("firstDoc", "一审判决", "text"), F("appealRequests", "上诉请求", "textarea"), F("appealGrounds", "上诉理由", "textarea"),
  ], "# 刑事上诉状\n\n上诉人：{{上诉人}}\n一审判决：{{一审判决}}\n\n## 上诉请求和依据\n{{上诉请求}}\n\n## 事实和理由\n{{上诉理由}}\n\n此致\n\n{{二审法院}}\n\n上诉人：{{签字或盖章}}\n{{上诉日期}}", "依据《中华人民共和国刑事诉讼法》关于上诉的规定", "arrow-up-circle"),
  T("lt-criminal-petition", "刑事申诉书", "litigation", "对生效刑事裁判申诉", [
    F("petitioner", "申诉人", "text"), F("effectiveDoc", "生效裁判文号", "text"), F("petitionGrounds", "申诉事由", "textarea"),
  ], "# 刑事申诉书\n\n申诉人：{{申诉人}}\n生效裁判文号：{{生效裁判文号}}\n\n## 申诉请求和依据\n{{申诉请求}}\n\n## 事实和理由\n{{申诉事由}}\n\n此致\n\n{{受理法院}}\n\n申诉人：{{签字或盖章}}\n{{日期}}", "依据《中华人民共和国刑事诉讼法》关于申诉的规定", "rotate-ccw"),
  T("lt-admin-complaint", "行政起诉状", "litigation", "不服行政行为提起行政诉讼", [
    F("plaintiff", "原告", "text"), F("defendant", "被告（行政机关）", "text"), F("adminAct", "被诉行政行为", "textarea"), F("adminRequests", "诉讼请求", "textarea"),
  ], "# 行政起诉状\n\n原告：{{原告}}\n被告：{{被告（行政机关）}}\n\n## 诉讼请求和依据\n{{诉讼请求}}\n\n## 事实和理由\n被诉行政行为：{{被诉行政行为}}\n{{事实与理由}}\n\n此致\n\n{{受诉法院}}\n\n具状人：{{签字或盖章}}\n{{日期}}", "依据《中华人民共和国行政诉讼法》", "landmark"),
  T("lt-admin-answer", "行政答辩状", "litigation", "行政机关应诉答辩", [
    F("respondent", "答辩人（行政机关）", "text"), F("plaintiff", "被答辩人", "text"), F("defensePoints", "答辩意见", "textarea"),
  ], "# 行政答辩状\n\n答辩人：{{答辩人（行政机关）}}\n被答辩人：{{被答辩人}}\n\n## 答辩事项和依据\n{{答辩意见}}\n\n## 事实和理由\n{{事实与理由}}\n\n此致\n\n{{受诉法院}}\n\n答辩人：{{签字或盖章}}\n{{日期}}", "依据《中华人民共和国行政诉讼法》", "shield"),
  T("lt-admin-appeal", "行政上诉状", "litigation", "不服行政一审判决上诉", [
    F("appellant", "上诉人", "text"), F("appellee", "被上诉人", "text"), F("appealRequests", "上诉请求", "textarea"), F("appealGrounds", "上诉理由", "textarea"),
  ], "# 行政上诉状\n\n上诉人：{{上诉人}}\n被上诉人：{{被上诉人}}\n\n## 上诉请求和依据\n{{上诉请求}}\n\n## 事实和理由\n{{上诉理由}}\n\n此致\n\n{{二审法院}}\n\n上诉人：{{签字或盖章}}\n{{日期}}", "依据《中华人民共和国行政诉讼法》", "arrow-up-circle"),
  T("lt-admin-reconsideration", "行政复议申请书", "litigation", "向行政机关申请复议", [
    F("applicant", "申请人", "text"), F("respondent", "被申请人（行政机关）", "text"), F("reconsiderRequests", "复议请求", "textarea"), F("reconsiderGrounds", "复议理由", "textarea"),
  ], "# 行政复议申请书\n\n申请人：{{申请人}}\n被申请人：{{被申请人（行政机关）}}\n\n## 复议请求和依据\n{{复议请求}}\n\n## 事实和理由\n{{复议理由}}\n\n此致\n\n{{复议机关}}\n\n申请人：{{签字或盖章}}\n{{日期}}", "依据《中华人民共和国行政复议法》", "landmark"),
  T("lt-state-compensation", "国家赔偿申请书", "litigation", "国家赔偿申请", [
    F("applicant", "赔偿请求人", "text"), F("organ", "赔偿义务机关", "text"), F("compensationClaims", "赔偿请求", "textarea"), F("damageDetail", "损害事实", "textarea"),
  ], "# 国家赔偿申请书\n\n赔偿请求人：{{赔偿请求人}}\n赔偿义务机关：{{赔偿义务机关}}\n\n## 赔偿请求和依据\n{{赔偿请求}}\n\n## 事实和理由\n{{损害事实}}\n\n此致\n\n{{赔偿义务机关}}\n\n请求人：{{签字或盖章}}\n{{日期}}", "依据《中华人民共和国国家赔偿法》", "scale"),
  T("lt-withdraw-suit", "撤诉申请书", "litigation", "申请撤回起诉", [
    F("applicant", "申请人", "text"), F("caseNo", "案件案号", "text"), F("withdrawReason", "撤诉理由", "textarea"),
  ], "# 撤诉申请书\n\n申请人：{{申请人}}\n案件案号：{{案件案号}}\n\n## 申请事项\n申请撤回对{{被申请人}}的起诉。\n\n## 事实和理由\n{{撤诉理由}}\n\n此致\n\n{{受诉法院}}\n\n申请人：{{签字或盖章}}\n{{日期}}", "依据" + LF + "关于撤诉的规定", "x-circle"),
];
const NL = "《中华人民共和国律师法》";
const NON_LITIGATION_TEMPLATES = [
  T("nl-sale-contract", "买卖合同", "non-litigation", "货物/设备买卖合同", [
    F("seller", "出卖人", "text"), F("buyer", "买受人", "text"), F("subjectMatter", "标的物", "textarea"), F("price", "价款与支付", "textarea"), F("delivery", "交付与验收", "textarea"),
  ], "# 买卖合同\n\n出卖人：{{出卖人}}　买受人：{{买受人}}\n\n## 标的物\n{{标的物}}\n\n## 价款与支付方式\n{{价款与支付}}\n\n## 交付与验收\n{{交付与验收}}\n\n## 违约责任\n{{违约责任}}\n\n出卖人（签章）：{{出卖人签章}}　买受人（签章）：{{买受人签章}}\n{{签订日期}}", "依据" + CIVIL_CODE + "合同编", "file-text"),
  T("nl-lease-contract", "房屋租赁合同", "non-litigation", "住房/商铺租赁", [
    F("lessor", "出租人", "text"), F("lessee", "承租人", "text"), F("premises", "租赁房屋", "textarea"), F("rent", "租金与押金", "text"), F("term", "租赁期限", "text"),
  ], "# 房屋租赁合同\n\n出租人：{{出租人}}　承租人：{{承租人}}\n租赁房屋：{{租赁房屋}}\n租赁期限：{{租赁期限}}　租金：{{租金与押金}}\n\n## 双方权利义务\n{{权利义务条款}}\n\n## 违约责任\n{{违约责任}}\n\n出租人（签章）：{{出租人签章}}　承租人（签章）：{{承租人签章}}\n{{签订日期}}", "依据" + CIVIL_CODE + "合同编", "home"),
  T("nl-loan-contract", "借款合同", "non-litigation", "民间/企业借款合同", [
    F("lender", "出借人", "text"), F("borrower", "借款人", "text"), F("amount", "借款金额", "text"), F("rate", "利率", "text"), F("repayTerm", "还款期限", "text"),
  ], "# 借款合同\n\n出借人：{{出借人}}　借款人：{{借款人}}\n借款金额：{{借款金额}}　利率：{{利率}}\n借款期限：{{借款期限}}　还款方式：{{还款方式}}\n\n## 违约责任\n{{违约责任}}\n\n出借人（签章）：{{出借人签章}}　借款人（签章）：{{借款人签章}}\n{{签订日期}}", "依据" + CIVIL_CODE + "合同编及民间借贷相关司法解释", "file-text"),
  T("nl-labor-contract", "劳动合同", "non-litigation", "建立劳动关系用", [
    F("employer", "用人单位", "text"), F("employee", "劳动者", "text"), F("position", "工作岗位", "text"), F("salary", "劳动报酬", "text"), F("term", "合同期限", "text"),
  ], "# 劳动合同\n\n用人单位：{{用人单位}}　劳动者：{{劳动者}}\n工作岗位：{{工作岗位}}　工作地点：{{工作地点}}\n合同期限：{{合同期限}}　劳动报酬：{{劳动报酬}}\n\n## 社会保险与福利\n{{社会保险条款}}\n\n用人单位（盖章）：{{单位盖章}}　劳动者（签字）：{{劳动者签字}}\n{{签订日期}}", "依据《中华人民共和国劳动合同法》", "briefcase"),
  T("nl-service-contract", "服务合同", "non-litigation", "一般服务类合同", [
    F("provider", "服务方", "text"), F("client", "委托方", "text"), F("scope", "服务内容", "textarea"), F("fee", "服务费用", "text"),
  ], "# 服务合同\n\n服务方：{{服务方}}　委托方：{{委托方}}\n\n## 服务内容与标准\n{{服务内容}}\n\n## 服务费用与支付\n{{服务费用}}\n\n## 违约责任\n{{违约责任}}\n\n服务方（签章）：{{服务方签章}}　委托方（签章）：{{委托方签章}}\n{{签订日期}}", "依据" + CIVIL_CODE + "合同编", "file-text"),
  T("nl-work-contract", "承揽合同", "non-litigation", "加工/定作/修理承揽", [
    F("contractor", "承揽人", "text"), F("client", "定作人", "text"), F("work", "承揽工作", "textarea"), F("remuneration", "报酬", "text"),
  ], "# 承揽合同\n\n承揽人：{{承揽人}}　定作人：{{定作人}}\n\n## 承揽工作内容\n{{承揽工作}}\n\n## 报酬与支付\n{{报酬}}\n\n承揽人（签章）：{{承揽人签章}}　定作人（签章）：{{定作人签章}}\n{{签订日期}}", "依据" + CIVIL_CODE + "合同编", "hammer"),
  T("nl-equity-transfer", "股权转让协议", "non-litigation", "有限责任公司股权转让", [
    F("transferor", "转让方", "text"), F("transferee", "受让方", "text"), F("equity", "转让股权", "textarea"), F("price", "转让价款", "text"),
  ], "# 股权转让协议\n\n转让方：{{转让方}}　受让方：{{受让方}}\n\n## 转让标的\n{{转让股权}}\n\n## 转让价款与支付\n{{转让价款}}\n\n## 交割与变更登记\n{{交割安排}}\n\n转让方（签章）：{{转让方签章}}　受让方（签章）：{{受让方签章}}\n{{签订日期}}", "依据《中华人民共和国公司法》", "share-2"),
  T("nl-nda", "保密协议", "non-litigation", "商业秘密保密约定", [
    F("discloser", "披露方", "text"), F("receiver", "接收方", "text"), F("scope", "保密范围", "textarea"), F("duration", "保密期限", "text"),
  ], "# 保密协议\n\n披露方：{{披露方}}　接收方：{{接收方}}\n\n## 保密范围\n{{保密范围}}\n\n## 保密义务与期限\n{{保密义务条款}}　保密期限：{{保密期限}}\n\n## 违约责任\n{{违约责任}}\n\n披露方（签章）：{{披露方签章}}　接收方（签章）：{{接收方签章}}\n{{签订日期}}", "依据《中华人民共和国反不正当竞争法》", "eye-off"),
  T("nl-power-of-attorney", "授权委托书", "non-litigation", "诉讼/民事授权委托", [
    F("principal", "委托人", "text"), F("attorney", "受托人", "text"), F("authority", "委托权限", "textarea"), F("term", "委托期限", "text"),
  ], "# 授权委托书\n\n委托人：{{委托人}}　受托人：{{受托人}}\n\n## 委托权限\n{{委托权限}}\n\n## 委托期限\n{{委托期限}}\n\n委托人（签字）：{{委托人签字}}\n{{出具日期}}", "依据" + LF + "关于诉讼代理的规定", "pen-tool"),
  T("nl-lawyer-letter", "律师函", "non-litigation", "催告/警告类函件", [
    F("sender", "发函律所与律师", "text"), F("addressee", "收函方", "text"), F("demands", "函告事项", "textarea"), F("deadline", "履行期限", "text"),
  ], "# 律师函\n\n致：{{收函方}}\n\n{{律师事务所}}及{{律师姓名}}受{{委托人}}委托，就{{函告事项}}特函告如下：\n\n{{函件正文}}\n\n请于{{履行期限}}前履行上述义务，否则委托人将依法采取措施维护自身权益。\n\n{{律师事务所}}\n{{律师姓名}}\n{{发函日期}}", "依据" + NL, "mail"),
  T("nl-legal-opinion", "法律意见书", "non-litigation", "专项法律问题分析意见", [
    F("client", "委托人", "text"), F("issue", "咨询事项", "textarea"), F("analysis", "法律分析", "textarea"), F("conclusion", "结论意见", "textarea"),
  ], "# 法律意见书\n\n致：{{委托人}}\n\n## 咨询事项\n{{咨询事项}}\n\n## 法律分析\n{{法律分析}}\n\n## 结论意见\n{{结论意见}}\n\n{{律师事务所}}\n{{律师姓名}}\n{{出具日期}}", "依据" + NL, "book-open"),
  T("nl-demand-letter", "催款函", "non-litigation", "债务催收函件", [
    F("creditor", "催款方", "text"), F("debtor", "欠款方", "text"), F("debtDetail", "欠款明细", "textarea"), F("repayDeadline", "还款期限", "text"),
  ], "# 催款函\n\n致：{{欠款方}}\n\n经核对，贵方尚欠我方款项如下：\n{{欠款明细}}\n\n请于{{还款期限}}前付清上述款项。逾期未付的，我方将依法主张利息及违约责任。\n\n催款方：{{催款方}}\n{{发函日期}}", "依据" + CIVIL_CODE + "合同编", "mail"),
  T("nl-settlement-agreement", "和解协议", "non-litigation", "纠纷一揽子和解", [
    F("partyA", "甲方", "text"), F("partyB", "乙方", "text"), F("disputeSummary", "纠纷概况", "textarea"), F("settlementTerms", "和解条款", "textarea"),
  ], "# 和解协议\n\n甲方：{{甲方}}　乙方：{{乙方}}\n\n## 纠纷概况\n{{纠纷概况}}\n\n## 和解条款\n{{和解条款}}\n\n## 其他约定\n{{其他约定}}\n\n甲方（签章）：{{甲方签章}}　乙方（签章）：{{乙方签章}}\n{{签订日期}}", "依据" + CIVIL_CODE, "handshake"),
  T("nl-divorce-agreement", "离婚协议书", "non-litigation", "登记离婚财产子女安排", [
    F("husband", "男方", "text"), F("wife", "女方", "text"), F("custody", "子女抚养", "textarea"), F("property", "财产分割", "textarea"),
  ], "# 离婚协议书\n\n男方：{{男方}}　女方：{{女方}}\n\n双方自愿离婚，达成如下协议：\n\n## 子女抚养\n{{子女抚养}}\n\n## 财产分割\n{{财产分割}}\n\n## 债权债务\n{{债权债务处理}}\n\n男方（签字）：{{男方签字}}　女方（签字）：{{女方签字}}\n{{签订日期}}", "依据" + CIVIL_CODE + "婚姻家庭编", "users"),
  T("nl-will", "遗嘱", "non-litigation", "个人财产处分遗嘱", [
    F("testator", "立遗嘱人", "text"), F("assets", "财产清单", "textarea"), F("beneficiaries", "受益安排", "textarea"), F("executor", "遗嘱执行人", "text"),
  ], "# 遗嘱\n\n立遗嘱人：{{立遗嘱人}}\n\n本人自愿立此遗嘱，对本人名下财产作如下处分：\n\n## 财产清单\n{{财产清单}}\n\n## 受益安排\n{{受益安排}}\n\n遗嘱执行人：{{遗嘱执行人}}\n\n立遗嘱人（签字）：{{立遗嘱人签字}}\n{{立遗嘱日期}}", "依据" + CIVIL_CODE + "继承编", "scroll"),
  T("nl-company-charter", "公司章程", "non-litigation", "有限责任公司章程", [
    F("company", "公司名称", "text"), F("shareholders", "股东及出资", "textarea"), F("capital", "注册资本", "text"), F("governance", "组织机构", "textarea"),
  ], "# {{公司名称}}章程\n\n## 注册资本与股东\n注册资本：{{注册资本}}\n股东及出资：{{股东及出资}}\n\n## 组织机构\n{{组织机构}}\n\n## 其他条款\n{{其他条款}}\n\n全体股东（签字/盖章）：{{股东签署}}\n{{通过日期}}", "依据《中华人民共和国公司法》", "building"),
  T("nl-shareholder-resolution", "股东会决议", "non-litigation", "股东会会议决议", [
    F("company", "公司名称", "text"), F("meetingDate", "会议时间", "date"), F("resolutions", "决议事项", "textarea"),
  ], "# {{公司名称}}股东会决议\n\n会议时间：{{会议时间}}　会议方式：{{会议方式}}\n出席股东：{{出席股东}}\n\n## 决议事项\n{{决议事项}}\n\n表决结果：{{表决结果}}\n\n全体出席股东（签字/盖章）：{{股东签署}}\n{{决议日期}}", "依据《中华人民共和国公司法》", "building"),
  T("nl-board-resolution", "董事会决议", "non-litigation", "董事会会议决议", [
    F("company", "公司名称", "text"), F("meetingDate", "会议时间", "date"), F("resolutions", "决议事项", "textarea"),
  ], "# {{公司名称}}董事会决议\n\n会议时间：{{会议时间}}　出席董事：{{出席董事}}\n\n## 决议事项\n{{决议事项}}\n\n表决结果：{{表决结果}}\n\n出席董事（签字）：{{董事签署}}\n{{决议日期}}", "依据《中华人民共和国公司法》", "building"),
  T("nl-arbitration-application", "仲裁申请书", "non-litigation", "向仲裁机构申请仲裁", [
    F("applicant", "申请人", "text"), F("respondent", "被申请人", "text"), F("arbitrationRequests", "仲裁请求", "textarea"), F("arbitrationGrounds", "事实与理由", "textarea"),
  ], "# 仲裁申请书\n\n申请人：{{申请人}}　被申请人：{{被申请人}}\n\n## 仲裁请求和依据\n{{仲裁请求}}\n\n## 事实和理由\n{{事实与理由}}\n\n此致\n\n{{仲裁委员会}}\n\n申请人：{{签字或盖章}}\n{{申请日期}}", "依据《中华人民共和国仲裁法》", "gavel"),
  T("nl-breach-notice", "违约告知函", "non-litigation", "合同违约书面告知", [
    F("sender", "告知方", "text"), F("receiver", "违约方", "text"), F("breachDetail", "违约事实", "textarea"), F("remedyDemand", "补救要求", "textarea"),
  ], "# 违约告知函\n\n致：{{违约方}}\n\n贵方在履行{{合同名称}}过程中存在如下违约行为：\n{{违约事实}}\n\n现要求贵方：\n{{补救要求}}\n\n请于{{履行期限}}前完成上述补救，否则我方将依法解除合同并追究违约责任。\n\n告知方：{{告知方}}\n{{发函日期}}", "依据" + CIVIL_CODE + "合同编", "mail"),
];
export const CATALOG_TEMPLATES = [...LITIGATION_TEMPLATES, ...NON_LITIGATION_TEMPLATES];

// ---------- 隐藏结构模板（11 案由 × 起诉|答辩；aliases 首项=canonical） ----------
// 案由取自通用民事案由体系的常用项，诉请/事实要素为法律方法结构自写，不逐字复制竞品条目。
export const HIDDEN_CAUSES = [
  {
    cause: "物业服务合同纠纷",
    aliases: ["物业服务合同纠纷", "物业费纠纷", "物业管理费纠纷"],
    complaint: {
      requests: [
        "判令被告支付拖欠的物业管理费人民币{{欠费金额}}元（计费期间：{{计费期间起}}至{{计费期间止}}）",
        "判令被告支付违约金人民币{{违约金金额}}元（按约定标准自逾期之日起计算至实际清偿之日）",
        "判令被告承担本案全部诉讼费用",
      ],
      facts: [
        "原告与{{被告所属小区业委会或建设单位}}签订《物业服务合同》，约定了服务范围与收费标准",
        "原告依约提供了物业服务，被告自{{欠费起始期}}起未缴纳物业费",
        "原告多次以{{催收方式}}催收，被告至今未履行缴费义务",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告全部诉讼请求",
        "原告提供的物业服务不符合约定标准（{{服务瑕疵事项}}），物业费应当相应减收",
        "原告主张的违约金标准过高，请求予以调减",
      ],
      facts: [
        "被告拒缴物业费系因{{拒缴事由}}，并非恶意拖欠",
        "原告的物业服务存在{{服务瑕疵事项}}，有业主书面反映记录在案",
      ],
    },
  },
  {
    cause: "民间借贷纠纷",
    aliases: ["民间借贷纠纷", "借贷纠纷", "欠款纠纷"],
    complaint: {
      requests: [
        "判令被告偿还借款本金人民币{{借款本金}}元",
        "判令被告支付利息人民币{{利息金额}}元（按{{约定利率}}自{{起息日}}计算至实际清偿之日）",
        "判令被告承担本案诉讼费用",
      ],
      facts: [
        "{{借款发生时间}}，被告因{{借款用途}}向原告借款人民币{{借款本金}}元，出具了借条",
        "原告以{{交付方式}}实际交付借款，被告确认收款",
        "借款到期后，经原告多次催讨，被告仅归还{{已还金额}}元，余款未还",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告全部诉讼请求",
        "原告主张的借款本金与实际交付金额不符，实际收到{{实际收到金额}}元",
        "双方未约定利息或约定不明，原告主张利息缺乏依据",
      ],
      facts: [
        "被告已通过{{还款方式}}归还款项{{已还金额}}元，应予扣减",
        "借条载明的金额包含预扣利息，实际交付金额小于借条载明金额",
      ],
    },
  },
  {
    cause: "机动车交通事故责任纠纷",
    aliases: ["机动车交通事故责任纠纷", "交通事故责任纠纷", "交通事故"],
    complaint: {
      requests: [
        "判令被告赔偿医疗费、误工费、护理费、交通费等损失合计人民币{{损失总额}}元",
        "判令{{保险人（保险公司）}}在交强险及商业三者险责任限额内先行赔付",
        "判令被告承担本案诉讼费用",
      ],
      facts: [
        "{{事故发生时间}}，被告驾驶{{肇事车辆}}在{{事故地点}}与原告发生碰撞，造成原告受伤",
        "交警部门认定被告负{{事故责任认定}}责任",
        "原告就医产生医疗费等各项损失，经鉴定构成{{伤残等级}}",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告超出法律规定与保险责任限额的诉讼请求",
        "原告主张的各项损失金额过高，请求依法核定",
        "事故责任比例认定有误，原告自身存在{{过错情形}}，应减轻被告责任",
      ],
    },
  },
  {
    cause: "劳动争议",
    aliases: ["劳动争议", "劳动纠纷", "劳动合同纠纷"],
    complaint: {
      requests: [
        "确认原告与被告之间存在劳动关系（{{入职时间}}至{{离职时间}}）",
        "判令被告支付拖欠工资人民币{{欠付工资金额}}元",
        "判令被告支付{{经济补偿或赔偿项目}}人民币{{补偿金额}}元",
      ],
      facts: [
        "原告于{{入职时间}}入职被告处，担任{{工作岗位}}，月工资{{月工资}}元",
        "被告自{{欠薪起始月}}起拖欠工资，且存在{{其他违法情形}}",
        "原告已就本案争议申请劳动仲裁，仲裁机构作出{{仲裁裁决文号}}裁决",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告全部诉讼请求",
        "双方劳动关系已于{{劳动关系终止时间}}依法解除，被告不存在违法解除情形",
        "原告主张的工资及补偿计算基数与标准有误",
      ],
      facts: [
        "被告已足额支付原告在职期间工资，有工资发放记录为证",
        "原告严重违反公司规章制度（{{违纪事实}}），被告依法解除劳动合同",
      ],
    },
  },
  {
    cause: "买卖合同纠纷",
    aliases: ["买卖合同纠纷", "货物买卖纠纷", "购销合同纠纷"],
    complaint: {
      requests: [
        "判令被告支付所欠货款人民币{{欠付货款}}元",
        "判令被告支付逾期付款利息/违约金人民币{{违约金金额}}元",
        "判令被告承担本案诉讼费用",
      ],
      facts: [
        "原告与被告于{{签约时间}}签订《买卖合同》，约定原告向被告供应{{标的物}}",
        "原告已按约交付货物，被告签收确认，货款合计{{货款总额}}元",
        "被告仅支付{{已付金额}}元，余款经催收未付",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告全部诉讼请求",
        "原告交付的货物存在质量问题（{{质量瑕疵事项}}），不符合合同约定",
        "被告有权行使先履行抗辩权，拒付货款不构成违约",
      ],
      facts: [
        "被告在验收期内提出书面质量异议，原告未予处理",
        "原告逾期交付货物{{逾期天数}}天，应承担违约责任并抵扣货款",
      ],
    },
  },
  {
    cause: "房屋租赁合同纠纷",
    aliases: ["房屋租赁合同纠纷", "租赁纠纷", "商铺租赁纠纷"],
    complaint: {
      requests: [
        "判令被告支付拖欠租金人民币{{欠付租金}}元",
        "判令解除双方签订的《房屋租赁合同》，被告腾退并返还租赁房屋",
        "判令被告承担违约金及本案诉讼费用",
      ],
      facts: [
        "原告与被告于{{签约时间}}签订《房屋租赁合同》，约定租赁{{租赁房屋}}，月租金{{月租金}}元",
        "被告自{{欠租起始月}}起拖欠租金，经催告仍未支付",
        "被告拖欠租金已超过合同约定的解除条件，原告依法行使解除权",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告全部诉讼请求",
        "租赁房屋存在{{房屋瑕疵事项}}，影响正常使用，被告有权主张减少租金",
        "原告主张的违约金过高，请求依法调减",
      ],
      facts: [
        "被告已支付{{已付租金}}元租金及押金，欠付金额与事实不符",
        "租赁期间房屋漏水等维修问题原告拖延不修，构成违约在先",
      ],
    },
  },
  {
    cause: "离婚纠纷",
    aliases: ["离婚纠纷", "离婚诉讼", "解除婚姻关系"],
    complaint: {
      requests: [
        "判令准予原告与被告离婚",
        "判令婚生子女{{子女姓名}}由原告直接抚养，被告按月支付抚养费人民币{{抚养费金额}}元",
        "依法分割夫妻共同财产（见财产清单）",
      ],
      facts: [
        "原告与被告于{{结婚登记时间}}登记结婚，婚后生育子女{{子女姓名}}",
        "双方因{{感情破裂事由}}致夫妻感情确已破裂，无和好可能",
        "夫妻共同财产包括{{主要共同财产}}，婚后无共同债权债务或已列明",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告的离婚诉讼请求，双方感情尚未破裂",
        "如法院认定应予离婚，婚生子女应由被告直接抚养",
        "原告主张的财产分割方案与实际出资及登记情况不符",
      ],
      facts: [
        "双方矛盾源于家庭琐事，仍有和好可能，不符合感情确已破裂的认定标准",
        "{{主要共同财产}}系被告婚前个人财产或父母出资购买，不应作为共同财产分割",
      ],
    },
  },
  {
    cause: "侵权责任纠纷",
    aliases: ["侵权责任纠纷", "侵权纠纷", "人身侵权"],
    complaint: {
      requests: [
        "判令被告赔偿医疗费、误工费、护理费等损失合计人民币{{损失总额}}元",
        "判令被告支付精神损害抚慰金人民币{{抚慰金金额}}元",
        "判令被告承担本案诉讼费用",
      ],
      facts: [
        "{{侵权行为发生时间}}，被告在{{侵权行为地点}}对原告实施{{侵权行为}}，致原告受伤",
        "原告就医诊断为{{诊断结果}}，产生医疗费等各项费用",
        "被告的侵权行为与原告损害之间存在直接因果关系",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告全部诉讼请求",
        "原告损害系其自身{{自身过错情形}}所致，被告不存在过错",
        "原告主张的赔偿项目与金额缺乏事实与法律依据",
      ],
      facts: [
        "事件起因系原告先行挑衅（{{起因事实}}），被告系正当防卫或反应性行为",
        "原告主张的部分费用与本次事件无关，不属于赔偿范围",
      ],
    },
  },
  {
    cause: "金融借款合同纠纷",
    aliases: ["金融借款合同纠纷", "银行借款纠纷", "贷款纠纷"],
    complaint: {
      requests: [
        "判令被告偿还借款本金人民币{{贷款本金}}元及利息{{利息金额}}元（暂计至{{计算截止日}}，此后按合同约定继续计算）",
        "确认原告对抵押物{{抵押物描述}}享有优先受偿权",
        "判令被告承担本案诉讼费用及原告实现债权的费用",
      ],
      facts: [
        "原告与被告于{{签约时间}}签订《借款合同》，发放贷款{{贷款本金}}元",
        "被告以{{抵押物描述}}提供抵押担保，并办理了抵押登记",
        "被告自{{违约起始期}}起未按期还本付息，构成违约",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告利息、罚息计算中超出法律规定部分",
        "原告主张的复利与罚息重复计算，应予扣除",
        "原告实现债权的费用缺乏票据依据，不应支持",
      ],
      facts: [
        "原告主张的利率折算后超过法律保护上限，超出部分无效",
        "被告已归还{{已还金额}}元，原告未在欠息计算中扣减",
      ],
    },
  },
  {
    cause: "建设工程施工合同纠纷",
    aliases: ["建设工程施工合同纠纷", "工程款纠纷", "建筑施工纠纷"],
    complaint: {
      requests: [
        "判令被告支付拖欠工程款人民币{{欠付工程款}}元",
        "判令被告支付逾期付款利息（自{{应付日期}}起按{{计息标准}}计算至实际清偿之日）",
        "确认原告对案涉工程折价或拍卖价款享有优先受偿权",
      ],
      facts: [
        "原告与被告于{{签约时间}}签订《建设工程施工合同》，承建{{工程项目}}",
        "工程于{{竣工时间}}竣工验收合格并已交付使用",
        "经结算，工程总价款{{结算总价}}元，被告仅支付{{已付金额}}元",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告全部诉讼请求",
        "工程存在质量问题（{{质量缺陷事项}}）尚未修复，付款条件未成就",
        "结算金额应以双方确认的{{结算依据}}为准，原告主张的金额虚高",
      ],
      facts: [
        "工程未经竣工验收即被原告要求使用，责任归属存在争议",
        "原告施工范围变更部分未办理签证手续，不应计入结算",
      ],
    },
  },
  {
    cause: "名誉权纠纷",
    aliases: ["名誉权纠纷", "名誉侵权", "诽谤纠纷"],
    complaint: {
      requests: [
        "判令被告立即停止侵害原告名誉权的行为，删除{{侵权内容载体}}上的侵权内容",
        "判令被告在原发布范围内公开赔礼道歉、消除影响、恢复名誉",
        "判令被告赔偿精神损害抚慰金人民币{{抚慰金金额}}元及维权合理支出",
      ],
      facts: [
        "{{发布时间}}起，被告在{{侵权内容载体}}持续发布针对原告的不实言论",
        "被告发布的言论与事实不符（{{失实要点}}），经{{核实途径}}核实为虚假信息",
        "上述内容被{{传播范围}}转发浏览，致原告社会评价显著降低",
      ],
    },
    answer: {
      requests: [
        "请求依法驳回原告全部诉讼请求",
        "被告发布的内容基本属实（{{属实依据}}），不构成诽谤",
        "被告的言论属正当评价与舆论监督范畴，未超出必要限度",
      ],
      facts: [
        "被告发布内容均有依据（{{依据来源}}），并非捏造事实",
        "原告社会评价降低与其自身行为有关，与被告言论无因果关系",
      ],
    },
  },
];
export const HIDDEN_CAUSE_COUNT = HIDDEN_CAUSES.length;
export function listSupportedCauses() {
  return HIDDEN_CAUSES.map((c) => c.cause);
}

// ---------- 隐藏模板渲染（节序固定；facts 缺席=整节约去） ----------
// 节序：# 标题 → 案号与案由 → 当事人信息 → 请求/答辩事项和依据 → 事实和理由（有 facts 才出）
//       → 管辖、保全与其他说明 → 证据清单 → 使用要求行 → 尾部（起诉=具状人 / 答辩=答辩人）+日期。
const USAGE_LINE = "使用要求：按上述项目顺序起草；材料未载明的信息以【待核实：具体事项】标注，不得虚构。";
export function renderHiddenTemplate(entry, documentType) {
  const kind = documentType === "complaint" ? entry.complaint : entry.answer;
  const isComplaint = documentType === "complaint";
  const title = (isComplaint ? "民事起诉状（" : "民事答辩状（") + entry.cause + "）";
  const lines = [];
  lines.push("# " + title, "");
  lines.push("## 案号与案由", "案号：{{案号}}", "案由：" + entry.cause, "");
  lines.push("## 当事人信息", "");
  if (isComplaint) {
    lines.push(
      "原告：{{原告姓名或名称}}　住所/住址：{{原告住所}}　联系方式：{{原告联系方式}}",
      "被告：{{被告姓名或名称}}　住所/住址：{{被告住所}}　联系方式：{{被告联系方式}}", "",
    );
  } else {
    lines.push(
      "答辩人：{{答辩人姓名或名称}}　住所/住址：{{答辩人住所}}　联系方式：{{答辩人联系方式}}",
      "被答辩人（原告）：{{原告姓名或名称}}", "",
    );
  }
  lines.push(isComplaint ? "## 诉讼请求和依据" : "## 答辩事项和依据", "");
  (kind.requests ?? []).forEach((r, i) => lines.push((i + 1) + ". " + r));
  lines.push("");
  if (Array.isArray(kind.facts) && kind.facts.length > 0) {
    lines.push("## 事实和理由", "");
    kind.facts.forEach((ft, i) => lines.push((i + 1) + ". " + ft));
    lines.push(
      "",
      isComplaint
        ? "综上，被告的行为已侵害原告合法权益。为维护原告的合法权利，原告依据相关法律规定提起本诉，恳请法院依法支持原告的全部诉讼请求。"
        : "综上，答辩人的答辩意见具有事实与法律依据，恳请法院依法审查并驳回被答辩人的全部诉讼请求。",
      "",
    );
  }
  lines.push("## 管辖、保全与其他说明", "");
  lines.push(
    isComplaint
      ? "本案由{{受理法院}}管辖，管辖依据：{{管辖依据}}。\n如需财产/证据保全：{{保全需求说明}}。"
      : "对本案管辖{{有无异议}}：{{管辖异议说明}}。",
    "",
  );
  lines.push("## 证据清单", "");
  lines.push("1. {{证据一名称}}：拟证明{{证据一证明内容}}", "2. {{证据二名称}}：拟证明{{证据二证明内容}}", "");
  lines.push("> " + USAGE_LINE, "");
  if (isComplaint) {
    lines.push("此致", "", "{{受理法院}}", "", "具状人：{{原告签字或盖章}}", "{{具状日期}}");
  } else {
    lines.push("此致", "", "{{受理法院}}", "", "答辩人：{{答辩人签字或盖章}}", "{{答辩日期}}");
  }
  const srcNo = HIDDEN_CAUSES.indexOf(entry) + 1;
  return {
    id: "hidden-" + srcNo + "-" + documentType,
    name: title,
    documentType,
    sourceFileId: "hidden-cause-" + srcNo,
    cause: entry.cause,
    content: lines.join("\n"),
  };
}

// ---------- 匹配算法：query 归一化（小写+去全部空白）→ 别名子串 → 最长别名优先；不命中不猜 ----------
export function normalizeQuery(q) {
  return String(q ?? "").toLowerCase().replace(/\s+/g, "");
}
export function matchCause(query) {
  const nq = normalizeQuery(query);
  if (!nq) return null;
  let best = null;
  for (const entry of HIDDEN_CAUSES) {
    for (const alias of entry.aliases) {
      const na = normalizeQuery(alias);
      if (na && nq.includes(na) && (!best || na.length > best.aliasLength)) {
        best = { entry, alias, aliasLength: na.length };
      }
    }
  }
  return best;
}

// ---------- 解析工具三态（resolve_legal_document_template 等量，命名等价自定） ----------
export function resolveDocumentTemplate({ documentType, query } = {}) {
  const rawType = String(documentType ?? "").trim().toLowerCase();
  let type = null;
  if (rawType === "complaint" || /起诉|诉讼请求|原告/.test(rawType)) type = "complaint";
  else if (rawType === "answer" || /答辩/.test(rawType)) type = "answer";
  if (!type) {
    return { isError: true, reason: "documentType 非法：应为 complaint（起诉）或 answer（答辩），收到：" + (rawType || "（空）").slice(0, 40) };
  }
  const q = String(query ?? "").trim().slice(0, 4000); // query 截断 4000
  const best = matchCause(q);
  if (!best) {
    return {
      matched: false,
      template: null,
      supportedCauses: listSupportedCauses(),
      reason: "未命中内置结构模板（不猜测）。可根据案件材料自主生成结构。",
    };
  }
  return {
    matched: true,
    priority: "embedded-after-user-template",
    template: renderHiddenTemplate(best.entry, type),
    instructions: "仅当用户未提供自定义模板时方可使用本内置模板；起草时保持模板的项目顺序；材料未载明的信息以【待核实：具体事项】标注。用户自定义模板的优先级恒高于本内置模板，不得以内置模板覆盖之。",
  };
}

// ---------- 占位符推断补字段（content 中未定义的 {{占位}} 自动补 textarea 字段；已知不重复） ----------
export function withInferredTemplateFields(fields, content) {
  const out = Array.isArray(fields) ? [...fields] : [];
  const known = new Set(out.map((x) => String(x.id ?? x.label ?? "")));
  for (const m of String(content ?? "").matchAll(/\{\{([^{}]+)\}\}/g)) {
    const label = m[1].trim();
    if (!label || known.has(label)) continue;
    known.add(label);
    out.push({ id: label, label, type: "textarea", placeholder: "请填写该占位字段" });
  }
  return out;
}

// ---------- 借贷金额场景检测（借贷关系词+金额词+数字金额 三合一才判，缺一即否） ----------
const LOAN_WORDS = ["借款", "出借", "借贷", "放款", "还款", "还清", "欠款", "借条", "借据", "民间借贷", "本息", "利率"];
const MONEY_WORDS = ["元", "万元", "金额", "利息", "本金", "违约金", "欠款", "利率", "费用", "价款", "租金", "工资", "赔偿金"];
const DIGIT_MONEY_RE = /\d[\d,，]*(?:\.\d+)?\s*(?:万元|亿元|元|万)/;
export function detectLoanMoneyContext(text) {
  const t = String(text ?? "");
  return (
    LOAN_WORDS.some((w) => t.includes(w)) &&
    MONEY_WORDS.some((w) => t.includes(w)) &&
    DIGIT_MONEY_RE.test(t)
  );
}

// ---------- 终稿条件式金额机检（"如核实…则调整为…"涉金额窗口 → issue；非金额条件句不拦） ----------
const HEDGE_RE = /如(?:经?核实|经?查明|确认|查证)[^。；\n]{0,60}?(?:则|应当|应|将)(?:调整|改[为写定]|变更|降低|减少|扣除)[^。；\n]{0,60}/g;
export function checkConditionalMoneyHedges(text) {
  const t = String(text ?? "");
  const issues = [];
  for (const m of t.matchAll(HEDGE_RE)) {
    const window = t.slice(Math.max(0, m.index - 60), m.index + m[0].length + 60);
    if (MONEY_WORDS.some((w) => window.includes(w)) || DIGIT_MONEY_RE.test(window)) {
      issues.push({ index: m.index, snippet: m[0].slice(0, 60) });
    }
  }
  return issues;
}

// ---------- 文书判定启发式（标题正则+结构标记计数；过程性开场白不算正文） ----------
const TITLE_RE = /(?:民事|刑事|行政)[^\n]{0,10}?(?:起诉状|答辩状|上诉状|反诉状|申诉书|申请书)|自诉状|法律意见书|律师函|代理词|催款函|授权委托书|(?:买卖|租赁|借款|劳动|服务|承揽|保密|和解|离婚)[^\n]{0,6}?(?:合同|协议)|遗嘱|公司章程|股东会决议|董事会决议|仲裁申请书/;
const MARKER_RES = [
  /^[一二三四五六七八九十]+、/m, /诉讼请求/, /事实与?理由/, /此致/, /答辩人[：:]/,
  /原告[：:]/, /被告[：:]/, /证据清单/, /具状人/, /第[一二三四五六七八九十百\d]+条/,
];
const PROCESS_LINE_RE = /^(?:好的?[,，。！!]?|当然[,，]?|收到[,，]?|我将|我会|我正在|正在|接下来|让我|我来|首先我|下面我|基于以上|综上分析)[^\n]{0,100}$/;
export function stripProcessPreamble(text) {
  const lines = String(text ?? "").split(/\r?\n/);
  let i = 0;
  let seenTitle = false;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) { i++; continue; }
    if (TITLE_RE.test(line)) { seenTitle = true; break; }
    if (PROCESS_LINE_RE.test(line) && !seenTitle) { i++; continue; }
    break;
  }
  return lines.slice(i).join("\n");
}
// 完整=标题+（≥100 字或标记≥1）；或 ≥220 字+标记≥2；partial=仅有标题，或 ≥120 字+标记≥1。
export function looksLikeLegalDocument(text) {
  const t = stripProcessPreamble(String(text ?? ""));
  const len = t.replace(/\s/g, "").length;
  if (!len) return "none";
  const hasTitle = TITLE_RE.test(t);
  const markers = MARKER_RES.filter((re) => re.test(t)).length;
  if (hasTitle && (len >= 100 || markers >= 1)) return "complete";
  if (len >= 220 && markers >= 2) return "complete";
  if (hasTitle || (len >= 120 && markers >= 1)) return "partial";
  return "none";
}

// ---------- 对话内文件交付合同·文书重叠部分（RE-10 §2 H8/H9；参考文献条数/法条存在=调研面，归 #16/#18 对拍） ----------
// 锚点机提取：确定性正则（LegalTech 约束：字数/章节/案号禁模型猜）；提取不到=无锚点=不注入不机检，不阻塞交付。
function cnNumToInt(s) {
  if (/^\d+$/.test(s)) return parseInt(s, 10);
  const DIG = { "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9 };
  let total = 0, section = 0, digit = null;
  for (const ch of s) {
    if (ch in DIG) { digit = DIG[ch]; section += digit; }
    else if (ch === "十") { total += (digit ?? 1) * 10; digit = null; section = 0; }
    else if (ch === "百") { total += (digit ?? 1) * 100; digit = null; section = 0; }
    else if (ch === "千") { total += (digit ?? 1) * 1000; digit = null; section = 0; }
    else return NaN;
  }
  return total + section;
}
export function extractDeliveryAnchors(prompt) {
  const t = String(prompt ?? "");
  const anchors = { minChars: 0, requiredSections: [], caseNos: [], hasAny: false };
  const mLen = /(?:不少于|不得少于|至少)\s*([0-9零一二两三四五六七八九十百千]{1,8})\s*(?:个)?字/.exec(t);
  if (mLen) {
    const n = cnNumToInt(mLen[1]);
    if (Number.isFinite(n) && n > 0 && n <= 100000) anchors.minChars = n;
  }
  // 必需章节：包含/包括/写明引出的子句内，收全部引号节名（「」『』""）；引号内只按顿号拆（和/与/及常见于节名，不拆）；
  for (const m of t.matchAll(/(?:包含|包括|写明)([^。\n；]{0,80})/g)) {
    for (const q of m[1].matchAll(/[「『"]([^「」』"]{2,40})[」』"]/g)) {
      for (const part of q[1].split(/、/)) {
        const sec = part.trim();
        if (sec.length >= 2 && sec.length <= 16 && !anchors.requiredSections.includes(sec)) anchors.requiredSections.push(sec);
      }
    }
  }
  // 案号锚点：用户明写的具体案号原样要求写入文书（缺号不出——不猜造号）
  for (const m of t.matchAll(/[(（]\s*20\d{2}\s*[）)][^\s，。；、）)]{1,24}?号/g)) {
    const no = m[0].trim();
    if (!anchors.caseNos.includes(no)) anchors.caseNos.push(no);
  }
  anchors.hasAny = anchors.minChars > 0 || anchors.requiredSections.length > 0 || anchors.caseNos.length > 0;
  return anchors;
}
// 终稿逐项机检：字数下限/必需章节/案号在文/禁占位符（唯一合法占位=【待核实：具体事项】）。
// 返回逐项结果数组（ok+label+detail），由调用侧决定如何呈现；不抛异常不阻塞交付。
const FORBIDDEN_PLACEHOLDER_RE = /待补充|待填写|请填写|【占位|TODO|TBD|\{\{[^{}\n]+\}\}/;
export function validateDeliveryContent(content, anchors) {
  const t = String(content ?? "");
  const results = [];
  const push = (ok, label, detail) => results.push({ ok, label, detail });
  if (anchors?.minChars > 0) {
    const len = t.replace(/\s/g, "").length;
    push(len >= anchors.minChars, "字数下限 ≥" + anchors.minChars + " 字", "实测 " + len + " 字");
  }
  for (const sec of anchors?.requiredSections ?? []) {
    push(t.includes(sec), "必需章节「" + sec + "」", t.includes(sec) ? "已检出" : "未检出");
  }
  for (const no of anchors?.caseNos ?? []) {
    push(t.includes(no), "案号 " + no + " 写入文书", t.includes(no) ? "已检出" : "未检出");
  }
  const bad = FORBIDDEN_PLACEHOLDER_RE.exec(t);
  push(!bad, "禁占位符（唯一合法占位=【待核实：具体事项】）", bad ? "命中禁用占位：" + bad[0].slice(0, 20) : "未命中");
  return results;
}
// H9 事实忠实度指令（文件交付路径注入；文案自写）。
export const FACT_FIDELITY_BLOCK = [
  "【事实忠实度（交付合同）】",
  "1. 只有用户明确提供、附件/材料明确记载、工具已核验的内容可写成既成事实；其余不得写成确定结论；",
  "2. 材料未载明且无法唯一推出的信息，以【待核实：具体事项】标注，不得虚构补位；",
  "3. 交付前自查：当事人主语有无写反、金额与材料记载是否一致、时间先后是否成立；发现即改正后交付。",
].join("\n");

// ---------- 五阶段工作流（浮窗展示；事件驱动非真实编排） ----------
export const WORKFLOW_STAGES = [
  { key: "materials", label: "理解材料" },
  { key: "analysis", label: "归纳争议" },
  { key: "research", label: "法律调研" },
  { key: "argumentation", label: "研究论证" },
  { key: "drafting", label: "撰写文书" },
];
// 工具/内部步骤名 → 目标阶段（关键词映射；其余归 analysis）
export function stageKeyOfToolLabel(label) {
  const s = String(label ?? "");
  if (/材料|读文件|读取|知识/.test(s)) return "materials";
  if (/法条|案例|检索|搜索|调研|核验/.test(s)) return "research";
  if (/撰写|正文|起草/.test(s)) return "drafting";
  return "analysis";
}

// ---------- 材料预算：总 24 万字按份数均摊（每份下限 1.2 万）；头45%/中30%/尾25% 保序截取+两处显式省略标注 ----------
export const MATERIAL_BUDGET_TOTAL = 240000;
export const MATERIAL_BUDGET_FLOOR = 12000;
export const PASTE_CASE_BUDGET = 80000;
function escapeFence(s) {
  return String(s ?? "").replace(/```/g, "``\u200b`"); // 围栏转义防注入：材料内的 ``` 不闭合围栏
}
export function budgetMaterialText(text, per) {
  const t = String(text ?? "");
  if (t.length <= per) return { body: t, truncated: false, omitted: 0 };
  const head = Math.floor(per * 0.45);
  const mid = Math.floor(per * 0.30);
  const tail = Math.floor(per * 0.25);
  const midStart = Math.floor((t.length - mid) / 2);
  const body =
    t.slice(0, head) +
    "\n……（此处省略 " + (midStart - head) + " 字）……\n" +
    t.slice(midStart, midStart + mid) +
    "\n……（此处省略 " + (t.length - (midStart + mid) - tail) + " 字）……\n" +
    t.slice(t.length - tail);
  return { body, truncated: true, omitted: t.length - per };
}
export function buildMaterialBlocks(materials, { total = MATERIAL_BUDGET_TOTAL, floor = MATERIAL_BUDGET_FLOOR } = {}) {
  const list = (Array.isArray(materials) ? materials : []).filter((m) => m && typeof m.text === "string" && m.text.length > 0);
  if (!list.length) return [];
  const per = Math.max(floor, Math.floor(total / list.length));
  return list.map((m, idx) => {
    const r = budgetMaterialText(m.text, per);
    return {
      name: String(m.name ?? "材料" + (idx + 1)),
      budget: per,
      truncated: r.truncated,
      omitted: r.omitted,
      body: escapeFence(r.body),
    };
  });
}

// ---------- 借贷金额台账指令块（条件注入） ----------
export const MONEY_LEDGER_BLOCK = [
  "【金额与现金流台账（借贷场景附加要求）】",
  "1. 对材料中出现的每一笔资金往来进行台账式登记：时间、付款方、收款方、金额、用途、对应凭证；",
  "2. 预扣利息（砍头息）一次性处理：本金按实际交付金额认定，不得将预扣利息计入本金；",
  "3. 已还款项按法定抵充顺序处理：先抵实现债权的费用，再抵利息，最后抵本金；",
  "4. 利率表述不得超出法律保护上限（一年期贷款市场报价利率四倍），超出部分不写入诉讼请求；",
  "5. 材料中相互冲突的金额，一律不得作为确定金额写入诉请，应以【待核实：具体事项】标注并列出冲突点。",
].join("\n");

// ---------- 事实核验指令块（恒注入） ----------
export const FACT_VERIFICATION_BLOCK = [
  "【事实核验要求（每份文书必须执行）】",
  "1. 关键事实逐项标注三态来源：材料明确记载 / 可由材料唯一推出 / 待核实；",
  "2. 引用法条须注明来源；未经检索核验的法条必须标注\"依据未核验\"，不得伪装成已核实；",
  "3. 材料中相互冲突的事实，不得写入确定性结论，应列明冲突点并以待核实标注；",
  "4. 禁止使用\"如核实某事实则调整为某表述\"式的条件式二选一写法——每处事实只写一种确定表述；",
  "5. 核验以不阻塞交付为原则：核实不了的事项标注待核实，不得因此拒绝产出文书。",
].join("\n");

// ---------- 生成 prompt 装配（十一要素，章节顺序保留语义，文案全自写） ----------
export const TEMPLATE_REF_BUDGET = 3000; // 模板结构参考截 3000 字
export function assembleGenerationPrompt(opts) {
  const {
    templateName, templateContent, documentTypeName, fieldValues = {}, ourParty = "",
    materials = [], pastedCase = "", instructions = "", hasUserTemplate = false,
    legalResearchAvailable = false, templateIsHidden = false,
  } = opts;
  const blocks = [];

  // 1 任务定性
  blocks.push("【任务】你正在法律工作台内生成一份法律文书。这是一次内联文本产出任务：所有偏好已在下方给出或按默认处理，不要再向用户追问任何问题，直接产出文书全文。");

  // 2 我方立场确认（三级回退）
  const party = String(ourParty || "").trim();
  blocks.push(
    "【我方立场】本次文书代表的当事人（我方主体）按以下顺序确定：\n" +
    "1) 用户明确填写的我方主体：" + (party || "（未填写）") + "；\n" +
    "2) 未填写时，从案件材料中识别我方代理的当事人并采用之；\n" +
    "3) 仍不能确定的，在文书中以【待核实：我方主体】标注，且不得将立场写反。",
  );

  // 3 用户要求落实
  blocks.push("【用户要求】用户在下文给出的补充要求具有最高优先级：不得违背用户明确的立场与主张，不得篡改用户或材料载明的事实，不得擅自增删当事人主张。");

  // 4 材料理解与争议归纳
  blocks.push("【材料与争议】先通读全部材料，归纳：①当事人之间法律关系的性质；②双方争议焦点（逐项列出）；③对我方有利与不利的事实各有哪些。归纳结果体现在文书的说理结构中，不必单独输出归纳过程。");

  // 5 模板选择合同（三段式优先级）
  blocks.push(
    "【模板优先级】按以下顺序确定文书结构：\n" +
    "① 用户上传或提供的自定义模板（最高优先，在场时必须遵循，禁止改用其他结构）；\n" +
    (templateIsHidden
      ? "② 本次已为你匹配到内置结构模板（见下方\"模板结构参考\"），当前无用户模板时按其项目顺序起草；\n"
      : "② 起诉状/答辩状类文书可调用内置结构模板解析（若不可用，视为无模板，不阻塞起草）；\n") +
    "③ 均不可用时，按法律文书通行结构自主组织，并自行核验要素完整。" +
    (hasUserTemplate ? "\n当前状态：用户自定义模板在场（最高优先生效）。" : "\n当前状态：无用户自定义模板。"),
  );

  // 6 按需法律调研
  blocks.push(
    "【法律调研】" + (legalResearchAvailable
      ? "法条检索通道可用：对文书引用的每一处法条，先检索核验其现行效力与条文内容，再行引用。"
      : "法条检索通道当前不可用：仅引用你有把握的法律依据，并对每一处引用标注\"依据未核验\"。") +
    " 调研不足不影响交付：标注后继续完成文书。",
  );

  // 7 撰写规则
  blocks.push(
    "【撰写规则】\n" +
    "1. 信息采用四级优先：用户明确填写 > 材料明确记载 > 可由材料唯一推出 > 缺失；\n" +
    "2. 空字段≠事实缺失：对每个空字段，先在全部材料中检索同义或相关信息，能找到即采用；\n" +
    "3. 严禁把工作退回用户：禁止输出\"待核实：请填写\"\"请用户补充\"之类提示语；\n" +
    "4. 只有经上述检索后确实缺失的信息，才允许以【待核实：具体事项】标注——这是全文唯一合法的占位形式；\n" +
    "5. 金额一律使用确定数字表述，禁止小写遗漏、禁止\"约若干元\"式模糊（除非材料本身如此）。",
  );

  // 8 事实核验指令块
  blocks.push(FACT_VERIFICATION_BLOCK);

  // 9 条件注入：借贷金额台账
  const moneyScene = detectLoanMoneyContext(
    JSON.stringify(fieldValues) + "\n" + pastedCase + "\n" + materials.map((m) => m.text ?? "").join("\n"),
  );
  if (moneyScene) blocks.push(MONEY_LEDGER_BLOCK);

  // 10 结构化上下文
  const ctx = [];
  ctx.push("【目标文书】" + (templateName || documentTypeName || "法律文书"));
  ctx.push("【预设法律依据】" + (opts.legalBasis || "（未预设，按调研结果引用）"));
  const filled = Object.entries(fieldValues).filter(([, v]) => String(v ?? "").trim());
  ctx.push(
    "【已填字段】\n" + (filled.length
      ? filled.map(([k, v]) => "- " + k + "：" + String(v)).join("\n")
      : "（用户未预填任何字段，全部按撰写规则从材料中取材）"),
  );
  if (party) ctx.push("【我方主体】" + party);
  if (instructions) ctx.push("【用户补充要求】" + String(instructions).slice(0, 5000));
  const matBlocks = buildMaterialBlocks(materials);
  if (matBlocks.length) {
    ctx.push(
      "【案件材料（共 " + matBlocks.length + " 份，超长材料按头/中/尾保留并标注省略）】\n" +
      matBlocks.map((b) =>
        "--- 材料：" + b.name + "（预算 " + b.budget + " 字" + (b.truncated ? "，已省略 " + b.omitted + " 字" : "") + "）---\n```\n" + b.body + "\n```",
      ).join("\n"),
    );
  }
  if (pastedCase) ctx.push("【用户粘贴案情】\n```\n" + escapeFence(String(pastedCase).slice(0, PASTE_CASE_BUDGET)) + (pastedCase.length > PASTE_CASE_BUDGET ? "\n……（粘贴内容超长，已截断）" : "") + "\n```");
  if (templateContent) ctx.push("【模板结构参考】\n```\n" + escapeFence(String(templateContent).slice(0, TEMPLATE_REF_BUDGET)) + "\n```");
  blocks.push(ctx.join("\n\n"));

  // 11 输出格式令
  blocks.push("【输出格式】直接输出完整的 Markdown 文书正文，以文书标题开头。不要输出任何前言、过程说明、调研摘要、代码块围栏之外的解释内容。全文只允许【待核实：具体事项】一种占位形式。");

  return blocks.join("\n\n");
}

// ---------- 完成结算：双通道候选（流式累计 / 落库回捞）取最后一个过判定者；借贷场景条件式金额 → partial ----------
export function settleGeneration({ streamedText, recoveredText, contextText }) {
  const candidates = [streamedText, recoveredText].filter((t) => typeof t === "string" && t.trim());
  let content = null;
  let verdict = "none";
  for (const c of candidates) {
    const v = looksLikeLegalDocument(c);
    if (v !== "none") { content = stripProcessPreamble(c).trim(); verdict = v; }
  }
  if (!content) {
    return { ok: false, verdict: "error", content: "", notice: "", reason: "生成已结束，但未返回可用文书正文" };
  }
  let notice = "";
  if (verdict !== "error" && detectLoanMoneyContext(String(contextText ?? "")) && checkConditionalMoneyHedges(content).length > 0) {
    verdict = "partial";
    notice = "诉请金额仍需核对：终稿包含\"如核实…则调整为…\"式条件表述，请人工复核金额后再定稿。";
  }
  return { ok: true, verdict, content, notice, reason: "" };
}
