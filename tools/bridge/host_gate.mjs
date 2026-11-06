// 【#21 安全层】宿主侧最后闸：路径闸+命令 allowlist 闸（RE-21 增补 §2.7/
// §3.4；MingJuris 机制净室——拒绝码与白名单成员自写）。
// 定位分层（如实声明）：渲染层策略决定「模型被提供什么」，宿主闸是操作
// 系统 irreversible 动作前最后一道——渲染层被攻破或有 bug 不得扩大宿主行
// 为面。本闸**不是沙箱**：文本检查挡的是明显越界（含合同里藏的命令注入），
// 挡不住已运行程序的作恶——所以 shell 档默认关闭+逐条人审（对拍时此为
// 行为边界不是能力承诺）。archive 自报的路径是攻击者输入不是数据。
import { realpathSync, existsSync } from "node:fs";
import { isAbsolute, resolve, sep } from "node:path";

// ── 路径闸（四件套：词法归一+根内判定+符号链接解析+根删除特判）──

const PATH_CODES = new Set(["ok", "path_escape", "symlink_escape", "root_delete"]);

/**
 * 工作区路径闸。词法归一化后必须落在 root 内；delete 目标=root 本身拒；
 * 符号链接存在则解析真实目标，逃出=拒。
 * @returns {ok: boolean, code: string}
 */
export function gateWorkspacePath(root, target, { delete: isDelete = false } = {}) {
  const rootAbs = resolve(String(root ?? ""));
  const targetAbs = resolve(String(target ?? ""));
  // win32 大小写不敏感比对（与桥内 resolveMaterialPath 同口径）。
  const norm = (p) => (process.platform === "win32" ? p.toLowerCase() : p);
  const within = (parent, child) => {
    if (norm(parent) === norm(child)) return false; // 等长=目录本身不算「内」
    const p = parent.endsWith(sep) ? parent : parent + sep;
    return norm(child).startsWith(norm(p));
  };
  if (isDelete && norm(targetAbs) === norm(rootAbs)) {
    return { ok: false, code: "root_delete" }; // 删除工作区根本身=拒
  }
  if (!within(rootAbs, targetAbs) && norm(targetAbs) !== norm(rootAbs)) {
    return { ok: false, code: "path_escape" };
  }
  // 符号链接解析：目标存在则比对真实路径，逃出=拒（不存在=只剩词法判定）。
  if (existsSync(targetAbs)) {
    try {
      const realTarget = realpathSync(targetAbs);
      const realRoot = realpathSync(rootAbs);
      if (!within(realRoot, realTarget) && norm(realTarget) !== norm(realRoot)) {
        return { ok: false, code: "symlink_escape" };
      }
    } catch {
      // realpath 失败（权限/断链）按词法判定结果收口，不静默放行新面。
    }
  }
  return { ok: true, code: "ok" };
}

// ── 命令闸（文本级七连；allowlist 制，成员按我方只读文本工具族自定）──

/** 命令名白名单（只读文本工具族；带路径调用剥到裸名仍须在表内）。 */
const COMMAND_ALLOWLIST = new Set([
  "dir", "type", "cd", "echo", "findstr", "where", "tree", "more",
  "sort", "fc", "comp", "attrib", "date", "time", "hostname", "whoami",
  "cat", "ls", "head", "tail", "grep", "wc", "find", "file", "stat",
  "du", "df", "pwd", "which", "diff", "basename", "dirname",
]);

/** 网络命令（具名拒：请改走应用内数据源工具——检索词出域有专门通道）。 */
const NETWORK_COMMANDS = new Set([
  "curl", "wget", "ssh", "scp", "sftp", "ftp", "telnet", "nc", "netcat",
  "git", "npm", "npx", "pnpm", "yarn", "pip", "pip3", "brew", "apt",
  "apt-get", "choco", "winget", "Invoke-WebRequest", "iwr",
]);

/** 敏感凭据路径片段（命中即拒：命令不该碰凭据与密钥存放处）。 */
const SENSITIVE_FRAGMENTS = [
  ".ssh", ".aws", ".gnupg", ".netrc", ".env", "keychains", "id_rsa",
  "id_ed25519", "credentials", ".kube", ".docker", "authorized_keys",
];

/** 破坏性命令模式。 */
const DESTRUCTIVE_RE =
  /(^|[\s&|;])(rm|rmdir|shred|mkfs(\.\w+)?|dd|fdisk|format|del|erase|rd)\b|sudo\s|chmod\s+-R|chown\s+-R/;

/** 命令替换 / 环境展开（替换会让检查落空——先替换后检查等于没检查）。
 *  bash: $() ${} `；cmd: %VAR% 与延迟展开 !VAR!。 */
const SUBSTITUTION_RE = /\$\(|\$\{|`|%[^%\r\n]+%|![^!\r\n]+!/;

/** find 用这些开关执行命令或删除，白名单只放行了 find 本身。 */
const FIND_EXEC_FLAGS = new Set(["-exec", "-execdir", "-ok", "-okdir", "-delete"]);

/** 输出重定向（含无空格的 `>`、`1>`/`2>`，以及引号包住的目标）。 */
const REDIRECT_RE = />{1,2}\s*("[^"]*"|'[^']*'|\S+)/g;

const COMMAND_CODES = new Set([
  "ok", "shell_disabled", "command_substitution", "sensitive_path",
  "destructive", "command_not_allowed", "network_command", "arg_path_escape",
  "redirect_escape", "empty_command",
]);

function unquoteToken(token) {
  const t = String(token ?? "");
  if (t.length >= 2) {
    const a = t[0];
    const b = t[t.length - 1];
    if ((a === "\"" && b === "\"") || (a === "'" && b === "'")) return t.slice(1, -1);
  }
  return t;
}

function bareCommand(token) {
  // 剥路径：/usr/bin/curl → curl；C:\Windows\system32\cmd.exe → cmd
  const base = unquoteToken(token).split(/[\\/]/).pop() ?? "";
  return base.replace(/\.(exe|cmd|bat|com|ps1)$/i, "").toLowerCase();
}

function pathLike(token) {
  return /[/\\]/.test(token) || isAbsolute(token) || /^\.{1,2}$/.test(token) || token.split(/[/\\]/).includes("..");
}

/** 命令文本里的 \\ 与 / 都是分隔符（cmd 文本在 POSIX 上跑闸也要认反斜杠）。 */
function normalizeShellPath(token) {
  return process.platform === "win32" ? token : token.replace(/\\/g, "/");
}

function rejectEscapingPath(token, workspaceRoot, segment, code) {
  if (!workspaceRoot || !pathLike(token)) return null;
  const target = resolve(workspaceRoot, normalizeShellPath(token));
  const g = gateWorkspacePath(workspaceRoot, target);
  if (!g.ok) return { ok: false, code, segment };
  return null;
}

/**
 * 宿主命令闸（文本级，不信任调用方）。判序：shell 关⇒拒→分段（; / & / && /
 * || / | / 换行）逐段验→命令替换或环境展开⇒拒→敏感片段⇒拒→破坏性模式⇒拒→
 * 网络命令具名拒→命令名白名单→参数内路径 token 过路径闸→重定向目标过写闸。
 * @param {string} commandLine
 * @param {{shellEnabled?: boolean, workspaceRoot?: string}} options
 * @returns {ok, code, segment?}
 */
export function gateCommand(commandLine, { shellEnabled = false, workspaceRoot = "" } = {}) {
  if (shellEnabled !== true) {
    return { ok: false, code: "shell_disabled", segment: "" };
  }
  const line = String(commandLine ?? "");
  if (!line.trim()) return { ok: false, code: "empty_command", segment: "" };
  // 分段链式：cmd 的 & 与 bash 的 ;/&&/||/|/换行都要切开逐段验（链式不豁免任何一段）。
  // && 必须写在单个 & 前面，否则 a && b 会被切成两段以 & 开头的残段。
  const segments = line.split(/;|&&|&|\|\||\||\r?\n/).map((s) => s.trim()).filter(Boolean);
  for (const segment of segments) {
    // ① 命令替换 / 环境展开：替换结果未定，检查必然落空——拒。
    if (SUBSTITUTION_RE.test(segment)) {
      return { ok: false, code: "command_substitution", segment };
    }
    // ② 敏感凭据路径片段：命令不该指向凭据存放处。
    const lower = segment.toLowerCase();
    if (SENSITIVE_FRAGMENTS.some((frag) => lower.includes(frag))) {
      return { ok: false, code: "sensitive_path", segment };
    }
    // ③ 破坏性模式。
    if (DESTRUCTIVE_RE.test(segment)) {
      return { ok: false, code: "destructive", segment };
    }
    // 重定向目标按写闸过（无空格的 >、n>、引号目标都要先剥引号再归一）。
    if (workspaceRoot) {
      REDIRECT_RE.lastIndex = 0;
      let redirect;
      while ((redirect = REDIRECT_RE.exec(segment)) !== null) {
        const target = unquoteToken(redirect[1]);
        // 重定向目标一律按工作区写闸（相对名也要归一进根内；>&1 这类描述符复制拒）。
        if (!target || target.startsWith("&")) {
          return { ok: false, code: "redirect_escape", segment };
        }
        const g = gateWorkspacePath(workspaceRoot, resolve(workspaceRoot, normalizeShellPath(target)));
        if (!g.ok) return { ok: false, code: "redirect_escape", segment };
      }
    }
    // 命令名与参数逐 token。
    const tokens = segment.split(/\s+/);
    const cmd = bareCommand(tokens[0] ?? "");
    // ④ 网络命令具名拒（检索词出域走应用内数据源工具，不走 shell）。
    if (NETWORK_COMMANDS.has(cmd)) {
      return { ok: false, code: "network_command", segment };
    }
    // ⑤ 命令名必须在白名单内（allowlist 制：没人分类的命令默认拒）。
    if (!COMMAND_ALLOWLIST.has(cmd)) {
      return { ok: false, code: "command_not_allowed", segment };
    }
    // find -exec/-ok/-delete 会在白名单命令名之下执行或删除任意目标。
    if (cmd === "find" && tokens.some((token) => FIND_EXEC_FLAGS.has(token.toLowerCase()))) {
      return { ok: false, code: "command_not_allowed", segment };
    }
    // ⑥ 参数里的路径 token 也过路径闸（cat ../../.ssh/id_rsa 被参数闸拦
    // ——敏感片段已在②拦；此处拦的是越出工作区的普通路径）。
    // 开关里 `=` 后的路径同样要查（--output=../x 以前因「以 - 开头」被整段跳过）。
    if (workspaceRoot) {
      for (const token of tokens.slice(1)) {
        const t = unquoteToken(token);
        if (t.startsWith("-")) {
          const eq = t.indexOf("=");
          if (eq === -1) continue;
          const escaped = rejectEscapingPath(unquoteToken(t.slice(eq + 1)), workspaceRoot, segment, "arg_path_escape");
          if (escaped) return escaped;
          continue;
        }
        const escaped = rejectEscapingPath(t, workspaceRoot, segment, "arg_path_escape");
        if (escaped) return escaped;
      }
    }
  }
  return { ok: true, code: "ok", segment: "" };
}

export const HOST_GATE_CODES = { path: PATH_CODES, command: COMMAND_CODES };
