// 【#21 安全层】Allow/Ask/Deny 工具策略决策函数＋「总是允许」审批缓存
// （RE-21 增补 §2.6/§3.2；MingJuris 机制净室——行为等量、码表与文案自写）。
// 立论（行为级转述）：对话框只覆盖到达对话框的调用——一个技能本不该调的
// 工具不应变成用户深夜要答对的问题；deny 不进对话框，把原因（含原因码）
// 回给模型，让模型改口说明需求而不是重试同一调用。
// 判序固定（防模式放行击穿，规格 §3.2）：①删除类→deny(destructive)；
// ②跨事项检索→deny(cross_matter)；③模式分派（yolo 放行除绝对拒绝外全
// 部/always_ask 除技能装载外一律 ask/smart 只读白名单直放）；④shell 三
// 级；⑤写三级；⑥外部源三级；⑦未知工具→ask(unknown_tool)。
// deny 集不受模式放行（模式只影响 ask/allow 的分布）。
// shell 默认=关（2026-10-30 主控裁定）：开关不在本函数内定，经入参
// shellEnabled 注入（桥装配处读设置，设置默认 false，用户可翻）。
// 「总是允许」：按「技能实例+调用签名」双维缓存、绑 policyVersion（策略
// 规则任何变更必须 bump，旧批准随版本失配作废重问）、按会话隔离（会话切
// 换清空）；运行中止时在途审批按 deny 解析，不挂死等一个没人答的对话框。
import { createHash } from "node:crypto";

/** 策略版本：规则任何变更必须 bump。v2=「总是允许」键扩入技能实例维（§3.6）；
 * v3=新增 G6 连接器两工具入只读白名单（施工波三轮·桥健②：本地真源检索腿
 * juscite_statute_check/juscite_case_search——本地法条包+本地 lcr 合成库，零外发，语义=只读）。 */
export const TOOL_POLICY_VERSION = 3;

/** 三档权限模式（默认 smart）。 */
export const PERMISSION_MODES = new Set(["always_ask", "smart", "yolo"]);

/** 原因码闭集（十个，语义一一对应规格 §2.6）。 */
export const REASON_CODES = new Set([
  "read_only", "no_workspace", "writes_files", "external_call",
  "shell_disabled", "permission_not_declared", "destructive",
  "cross_matter", "source_not_enabled", "unknown_tool",
]);

// ── 工具分类表（我方域词；成员按我方工具族自定，规格 §3.1「命名可自定
// 但语义一一对应」）。分类变更=策略规则变更，必须 bump TOOL_POLICY_VERSION。──
/** 删除类（绝对拒绝最先判：任何技能声明了也不行）。 */
const DELETE_TOOLS = new Set([
  "file.delete", "matter.delete", "case.delete", "task.remove",
  "kb.collection.delete", "material.delete", "evidence.delete",
]);
/** 只读白名单（smart 档直放；always_ask 档仍 ask）。 */
const READ_TOOLS = new Set([
  "matter.read", "matter.list", "matter.timeline.read", "matter.board.read",
  "material.read", "material.list", "material.preview",
  "kb.search", "kb.read", "kb.collection.list",
  "statute.read", "statute.list", "manual.read", "manual.search",
  "timeline.read", "graph.read", "conflict.read",
  "audit.read", "tool.audits.list", "citation.verify.read",
  "research.read", "learning.read", "memory.read",
  "calendar.read", "task.list", "case.read", "screen.read",
  // G6 连接器检索腿（v3）：本地法条包核验+本地 lcr 合成库检索——真源均在本地，零外发。
  "juscite_statute_check", "juscite_case_search",
]);
/** 跨事项检索（带他人事项 id=拒，判在模式放行之前——yolo 也拦）。 */
const CROSS_MATTER_TOOLS = new Set(["matter.search", "matter.cross.read"]);
/** shell 执行类。 */
const SHELL_TOOLS = new Set(["bash", "shell.exec", "terminal.run"]);
/** 写文件类。 */
const WRITE_TOOLS = new Set([
  "file.write", "file.edit", "doc.export", "docx.edit", "redline.apply",
  "draft.write", "material.write", "kb.write", "graph.write",
]);
/** 外部数据源类（检索词会发给外部）。 */
const EXTERNAL_TOOLS = new Set([
  "statute.query", "web.search", "mcp.invoke", "connector.query",
]);
/** 技能装载（不是能力调用：always_ask 档也放行）。 */
const LOAD_SKILL_TOOLS = new Set(["load_skill"]);

// 外部源类工具须声明的权限（声明其任一即可，规格 §2.6 语义）。
const EXTERNAL_PERMISSIONS = new Set([
  "query-legal-database", "mcp", "network",
]);

function out(effect, code, reason) {
  return { effect, code, reason, policyVersion: TOOL_POLICY_VERSION };
}

/**
 * 决策函数（纯函数，规格 §3.2 输入闭集）。
 * @param input {toolName, args, permissionMode?, skillPermissions?, skillId?,
 *   matterId?, sessionMatterId?, workspacePath?, enabledSourceIds?, shellEnabled?}
 * @returns {effect: allow|ask|deny, code, reason, policyVersion}
 */
export function decideToolCall(input) {
  const toolName = String(input?.toolName ?? "");
  const args = input?.args;
  const mode = PERMISSION_MODES.has(input?.permissionMode) ? input.permissionMode : "smart";
  const declared = new Set(Array.isArray(input?.skillPermissions) ? input.skillPermissions.map(String) : []);
  const shellEnabled = input?.shellEnabled === true; // 默认关（主控裁定）
  const workspacePath = typeof input?.workspacePath === "string" ? input.workspacePath : "";
  const enabledSources = new Set(Array.isArray(input?.enabledSourceIds) ? input.enabledSourceIds.map(String) : []);

  // ① 删除类最先判：任何模式、任何声明都拦（绝对拒绝）。
  if (DELETE_TOOLS.has(toolName)) {
    return out("deny", "destructive", "删除类工具一律拒绝：删除是不可逆动作，任何技能声明都不放行");
  }
  // ② 跨事项检索：matterId 非本会话事项即拒，判在模式放行之前（yolo 也拦）。
  if (CROSS_MATTER_TOOLS.has(toolName)) {
    const target = args && typeof args === "object" ? String(args.matterId ?? "") : "";
    const session = String(input?.matterId ?? "");
    if (target && session && target !== session) {
      return out("deny", "cross_matter", `跨事项检索被拒：目标事项不是当前会话事项（当事人数据按事项隔离）`);
    }
  }
  // 技能装载：不是能力调用，全模式放行（always_ask 档唯一例外项）。
  if (LOAD_SKILL_TOOLS.has(toolName)) {
    return out("allow", "read_only", "技能装载不是能力调用，直接放行");
  }
  // ③ 模式分派（yolo/always_ask 在此定档；smart 落到后续工具族三级判）。
  if (mode === "yolo") {
    // yolo 放行除绝对拒绝外全部（①②已判完；后续三级里的 deny 级仍拦——
    // deny 集不受模式放行，见下方各工具族分支）。
    if (READ_TOOLS.has(toolName)) return out("allow", "read_only", "yolo 档：只读工具放行");
    if (SHELL_TOOLS.has(toolName) && !shellEnabled) {
      return out("deny", "shell_disabled", "命令执行开关未打开：shell 工具被拒（开关默认关闭，可在设置中打开）");
    }
    if (SHELL_TOOLS.has(toolName) && !declared.has("shell")) {
      return out("deny", "permission_not_declared", "当前技能清单未声明 shell 权限：开了功能开关也不送给所有技能");
    }
    if (WRITE_TOOLS.has(toolName) && !workspacePath) {
      return out("deny", "no_workspace", "没有工作文件夹：写工具拒绝（写出的文件必须落在受控工作区内）");
    }
    if (WRITE_TOOLS.has(toolName) && !declared.has("write-artifact")) {
      return out("deny", "permission_not_declared", "当前技能清单未声明 write-artifact 权限");
    }
    if (EXTERNAL_TOOLS.has(toolName)) {
      const sourceId = args && typeof args === "object" ? String(args.sourceId ?? "") : "";
      if (sourceId && !enabledSources.has(sourceId)) {
        return out("deny", "source_not_enabled", "外部数据源未启用：未启用的 sourceId 一律拒");
      }
      if (![...EXTERNAL_PERMISSIONS].some((p) => declared.has(p))) {
        return out("deny", "permission_not_declared", "当前技能清单未声明任何外部数据权限（query-legal-database/mcp/network）");
      }
    }
    return out("allow", "unknown_tool", "yolo 档：除绝对拒绝外放行");
  }
  if (mode === "always_ask") {
    // always_ask 档：逐条批（load_skill 已在上方放行）。
    return out("ask", "read_only", "always_ask 档：每次调用逐条确认");
  }
  // smart（默认）：只读白名单直放，其余按工具族三级判。
  if (READ_TOOLS.has(toolName)) {
    return out("allow", "read_only", "只读工具：smart 档直接放行");
  }
  // ④ shell 三级：开关关→deny；开了但未声明→deny；都过→ask（命令在用户
  // 机器上执行且不受工作文件夹限制，须逐条确认）。
  if (SHELL_TOOLS.has(toolName)) {
    if (!shellEnabled) {
      return out("deny", "shell_disabled", "命令执行开关未打开：shell 工具被拒（开关默认关闭，可在设置中打开）");
    }
    if (!declared.has("shell")) {
      return out("deny", "permission_not_declared", "当前技能清单未声明 shell 权限：开了功能开关也不送给所有技能");
    }
    return out("ask", "external_call", "命令将在你的机器上执行且不受工作文件夹限制：须逐条确认");
  }
  // ⑤ 写三级：无工作文件夹→deny；未声明→deny；否则 ask。
  if (WRITE_TOOLS.has(toolName)) {
    if (!workspacePath) {
      return out("deny", "no_workspace", "没有工作文件夹：写工具拒绝（写出的文件必须落在受控工作区内）");
    }
    if (!declared.has("write-artifact")) {
      return out("deny", "permission_not_declared", "当前技能清单未声明 write-artifact 权限");
    }
    return out("ask", "writes_files", "该工具会写入工作区文件：请确认目标与内容");
  }
  // ⑥ 外部源三级：sourceId 未启用→deny；未声明任一外部权限→deny；否则
  // ask（这会把检索词发给外部）。
  if (EXTERNAL_TOOLS.has(toolName)) {
    const sourceId = args && typeof args === "object" ? String(args.sourceId ?? "") : "";
    if (sourceId && !enabledSources.has(sourceId)) {
      return out("deny", "source_not_enabled", "外部数据源未启用：未启用的 sourceId 一律拒");
    }
    if (![...EXTERNAL_PERMISSIONS].some((p) => declared.has(p))) {
      return out("deny", "permission_not_declared", "当前技能清单未声明任何外部数据权限（query-legal-database/mcp/network）");
    }
    return out("ask", "external_call", "该调用会把检索词发送给外部数据源：请确认");
  }
  // ⑦ 未知工具=ask 不=allow：新工具不得因没人分类而自动放行。
  return out("ask", "unknown_tool", "未分类工具：按未分类逐条确认（不自动放行）");
}

// ── 「总是允许」审批缓存（按「技能实例+调用签名」、绑 policyVersion、按会话隔离）──
// 跨通道继承规则（RE-21 增补 §3.6 定稿，2026-10-31；TOOL_POLICY_VERSION v2）：
// 1. 缓存只作用于 ask 级决策；deny 级（destructive/cross_matter/permission_
//    not_declared/no_workspace/source_not_enabled/shell_disabled）逐调用按
//    当前技能声明+当前通道判——「总是允许」永不携带权限授予：无声明通道
//    （catzip 形/零声明迁移件）到不了 ask，也就继承不到任何记忆。
// 2. 记忆键=（技能实例, 工具, 参数签名）三维：技能实例不同（跨技能/跨通
//    道/跨版本——安全层 package_id@version、catzip 名、无上下文="" 各为独立
//    实例）一律不继承——用户批的是「这个技能实例的这个操作」。
// 3. 三态分离（installed/enabled/hired）下不追溯清缓存：停用/卸载的技能
//    不再发起调用，其记忆自然不可达；同实例同会话重新启用旧记忆仍有效
//    （policyVersion 仍把关）。

function callSignature(toolName, args, skillKey) {
  // 稳定序列化：键排序后的确定性 JSON 摘要——同调用同签名，参数变=新签名；
  // 技能实例进签名前缀（skillKey 缺省 ""=无技能上下文的匿名作用域）。
  const stable = (v) => {
    if (v === null || typeof v !== "object") return JSON.stringify(v) ?? "null";
    if (Array.isArray(v)) return "[" + v.map(stable).join(",") + "]";
    return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + stable(v[k])).join(",") + "}";
  };
  return createHash("sha256")
    .update(String(skillKey ?? "") + "\u0000" + toolName + "\u0000" + stable(args))
    .digest("hex").slice(0, 16);
}

/**
 * 会话级审批缓存。entries 为 Map（签名→{decision, policyVersion}）——
 * 保留为可检视属性，供测试模拟「策略版本升级后的旧批准」。
 * check/remember/markPending 第三参 skillKey=技能实例标识（安全层
 * package_id@version / catzip 技能名 / 缺省 ""=匿名作用域）。
 */
export function createApprovalCache({ policyVersion = TOOL_POLICY_VERSION } = {}) {
  const entries = new Map();      // 签名 → { decision: "always", policyVersion }
  const pending = new Map();      // 签名 → { toolName, args, code, reason }
  return {
    entries,
    /** ask 决策后查缓存：命中「总是允许」且版本一致→"allow"；版本失配→
     * 旧批准作废删除、返回 null（重问）。skillKey 不同=另一实例的记忆，
     * 天然查不中（不继承）。 */
    check(toolName, args, skillKey) {
      const sig = callSignature(toolName, args, skillKey);
      const hit = entries.get(sig);
      if (!hit) return null;
      if (hit.policyVersion !== policyVersion) {
        entries.delete(sig); // 版本老化：策略升了，旧批准作废重问
        return null;
      }
      return hit.decision === "always" ? "allow" : null;
    },
    /** 记住用户决定（"always" 进缓存；"allow" 一次性不缓存；"deny" 不进）。 */
    remember(toolName, args, userDecision, skillKey) {
      if (userDecision !== "always") return false;
      entries.set(callSignature(toolName, args, skillKey), { decision: "always", policyVersion });
      pending.delete(callSignature(toolName, args, skillKey));
      return true;
    },
    /** 登记一条在途审批（ask 已发出、还没人答）。 */
    markPending(toolName, args, meta, skillKey) {
      pending.set(callSignature(toolName, args, skillKey), {
        toolName, args,
        code: String(meta?.code ?? "unknown_tool"),
        reason: String(meta?.reason ?? ""),
      });
    },
    /** 运行中止：在途审批一律按 deny 解析（不挂死等没人答的对话框），
     * 返回被解析为 deny 的审批列表供审计入账。 */
    abortPending() {
      const aborted = [...pending.values()];
      pending.clear();
      return aborted;
    },
    /** 会话切换清空（记忆按会话隔离）。 */
    reset() {
      entries.clear();
      pending.clear();
    },
  };
}
