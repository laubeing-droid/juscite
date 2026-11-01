// 桥内通用异步任务壳（机制规格-02，律见报表导出轮询状态机等量自写实现，2026-10-28）。
// 状态机：QUEUED → RUNNING → 终态四选一 SUCCEEDED|FAILED|CANCELLED|EXPIRED；终态不可再变
// （EXPIRED 除外，见下）。壳只管状态机与取件，不管各任务自己的活——各功能 register(kind, runner)
// 注册执行函数，runner 通过 ctx.checkpoint() 协作式响应取消（解析器每页/导出器每行调一次）。
// EXPIRED=产物 TTL 过期：无后台清扫线程，读取时惰性翻转并删除产物文件（少养一个常驻件）。
// 软超时不杀任务：客户端轮询耗尽只提示"仍在处理中"，任务在桥内继续跑完照常可取（R2）。
// 重试只对 FAILED 开放（retry_count+1 回 QUEUED）；取消只对 QUEUED/RUNNING 开放（R6）。
// 崩溃扫尾：sweepOnBoot() 把进程死亡遗留的 QUEUED/RUNNING 统一 FAILED(error_code=BRIDGE_RESTART)
// 可重试，不留僵尸 RUNNING（A4）。
// 产物白名单（R5 的等量实现）：result_ref 由壳按 `tasks/<本任务id>/<fileName>` 生成，取件时按库内
// ref 拼路径——不存在"响应塞什么地址就拉什么地址"的面；文件名缺失由调用方按 `{kind}-{id}` 回退（R7）。
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

export class TaskShellError extends Error {
  // code: NOT_FOUND | VALIDATION | INVALID_STATE | CANCELLED
  constructor(code, message) { super(message); this.name = "TaskShellError"; this.code = code; }
}

const TASK_COLS = `id, kind, ref, status, payload_json, result_ref, file_name,
  error_code, error_message, retry_count, artifact_ttl, created_at, started_at, finished_at`;

function nowIso() { return new Date().toISOString(); }

function rowToSummary(r) {
  return {
    id: r.id, kind: r.kind, ref: r.ref, status: r.status,
    payload: JSON.parse(r.payload_json ?? "{}"),
    resultRef: r.result_ref ?? null, fileName: r.file_name ?? null,
    errorCode: r.error_code ?? null, errorMessage: r.error_message ?? null,
    retryCount: r.retry_count, artifactTtl: r.artifact_ttl ?? null,
    createdAt: r.created_at, startedAt: r.started_at ?? null, finishedAt: r.finished_at ?? null,
  };
}

export function createTaskShell(db, { artifactsDir, sweepOnBoot = true } = {}) {
  const runners = new Map();   // kind → runner(ctx)
  const live = new Map();      // 运行中任务 id → { cancelled }（进程内取消旗标）
  if (artifactsDir) mkdirSync(artifactsDir, { recursive: true });

  const getRow = db.prepare(`SELECT ${TASK_COLS} FROM async_tasks WHERE id = ?`);

  function markTerminal(id, status, { errorCode = null, errorMessage = null, finishedAt = null } = {}) {
    db.prepare(
      `UPDATE async_tasks SET status = ?, error_code = ?, error_message = ?, finished_at = ? WHERE id = ?`)
      .run(status, errorCode, errorMessage, finishedAt ?? nowIso(), id);
  }

  // 崩溃扫尾（A4）：构造即执行（进程生命周期=一次构造）。
  if (sweepOnBoot) {
    const n = db.prepare(
      `UPDATE async_tasks SET status = 'FAILED', error_code = 'BRIDGE_RESTART',
         error_message = '桥重启导致任务中断，可重试', finished_at = ?
       WHERE status IN ('QUEUED','RUNNING')`).run(nowIso()).changes;
    if (n > 0) console.log(`[task-shell] 崩溃扫尾：${n} 个遗留任务置 FAILED(BRIDGE_RESTART)`);
  }

  async function run(id) {
    const row = getRow.get(id);
    if (!row) return;
    const flag = { cancelled: false };
    live.set(id, flag);
    // 排队期被取消（终态已写）→ 起跑更新零行命中，直接收场不执行 runner
    const started = db.prepare(`UPDATE async_tasks SET status = 'RUNNING', started_at = ? WHERE id = ? AND status = 'QUEUED'`)
      .run(nowIso(), id);
    if (started.changes === 0) { live.delete(id); return; }
    try {
      const runner = runners.get(row.kind);
      if (typeof runner !== "function") throw new TaskShellError("VALIDATION", `未注册的任务类型 ${row.kind}`);
      const artifactDir = artifactsDir ? join(artifactsDir, "tasks", id) : null;
      if (artifactDir) mkdirSync(artifactDir, { recursive: true });   // 每任务产物目录由壳建（白名单形状保证）
      const out = await runner({
        payload: JSON.parse(row.payload_json ?? "{}"),
        artifactDir,
        checkpoint: () => { if (flag.cancelled) throw new TaskShellError("CANCELLED", "任务已被取消"); },
      });
      if (flag.cancelled) throw new TaskShellError("CANCELLED", "任务已被取消");
      const fileName = typeof out?.fileName === "string" && out.fileName.trim() ? out.fileName.trim() : null;
      const resultRef = fileName ? `tasks/${id}/${fileName}` : null;
      db.prepare(`UPDATE async_tasks SET status = 'SUCCEEDED', result_ref = ?, file_name = ?, finished_at = ? WHERE id = ?`)
        .run(resultRef, fileName, nowIso(), id);
    } catch (e) {
      if (e instanceof TaskShellError && e.code === "CANCELLED") {
        markTerminal(id, "CANCELLED", { errorCode: "CANCELLED", errorMessage: "任务已被取消" });
      } else {
        markTerminal(id, "FAILED", {
          errorCode: e instanceof TaskShellError ? e.code : "RUNNER_ERROR",
          errorMessage: String(e?.message ?? e),
        });
      }
    } finally {
      live.delete(id);
    }
  }

  return {
    // 注册任务类型（壳不感知各任务的活）。runner(ctx) → { fileName? }；写产物进 ctx.artifactDir。
    register(kind, runner) { runners.set(kind, runner); },

    // 建任务：入队即回，绝不同步等完成（R1）。
    create(kind, payload = {}, { ref = null, ttlSeconds = null, id = null } = {}) {
      if (typeof kind !== "string" || !kind.trim()) throw new TaskShellError("VALIDATION", "kind 必填");
      if (!runners.has(kind)) throw new TaskShellError("VALIDATION", `未注册的任务类型 ${kind}`);
      if (ttlSeconds != null && (!Number.isInteger(ttlSeconds) || ttlSeconds < 0))
        throw new TaskShellError("VALIDATION", "ttlSeconds 须为非负整数");
      const taskId = id == null || id === "" ? "fgt_" + randomUUID().slice(0, 8) : String(id);
      if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(taskId)) throw new TaskShellError("VALIDATION", "任务 id 形状非法");
      try {
        db.prepare(`INSERT INTO async_tasks (id, kind, ref, status, payload_json, artifact_ttl, created_at)
                    VALUES (?, ?, ?, 'QUEUED', ?, ?, ?)`)
          .run(taskId, kind, ref, JSON.stringify(payload ?? {}), ttlSeconds, nowIso());
      } catch (e) {
        if (e?.code === "ERR_SQLITE_ERROR" && /UNIQUE constraint failed/i.test(String(e?.message ?? ""))) {
          throw new TaskShellError("DUPLICATE", `任务已存在 ${taskId}`);
        }
        throw e;
      }
      setImmediate(() => { void run(taskId); });   // 下一刻起跑：QUEUED 态真实可观测（排队期取消有窗口）
      return this.get(taskId);
    },

    // 查任务：SUCCEEDED 且 TTL 已过 → 惰性翻 EXPIRED 并删产物（无清扫线程，A3）。
    get(id) {
      const r = getRow.get(id);
      if (!r) throw new TaskShellError("NOT_FOUND", `任务不存在 ${id}`);
      if (r.status === "SUCCEEDED" && r.artifact_ttl != null && r.finished_at != null
          && Date.now() >= Date.parse(r.finished_at) + r.artifact_ttl * 1000) {
        if (artifactsDir) rmSync(join(artifactsDir, "tasks", id), { recursive: true, force: true });
        db.prepare(`UPDATE async_tasks SET status = 'EXPIRED', error_code = 'EXPIRED',
                     error_message = '产物已过保留期，重新发起任务获取结果' WHERE id = ?`).run(id);
        return this.get(id);
      }
      return rowToSummary(r);
    },

    list({ limit = 50 } = {}) {
      return db.prepare(`SELECT ${TASK_COLS} FROM async_tasks ORDER BY created_at DESC, id DESC LIMIT ?`)
        .all(Math.min(Math.max(Number(limit) || 50, 1), 200)).map(rowToSummary);
    },

    // 取消：QUEUED 直接终态（run 起跑时见 CANCELLED 不执行）；RUNNING 置旗标，runner 在下一
    // checkpoint 收口（协作式，不杀线程）。终态取消=INVALID_STATE。
    cancel(id) {
      const r = getRow.get(id);
      if (!r) throw new TaskShellError("NOT_FOUND", `任务不存在 ${id}`);
      if (r.status === "QUEUED") {
        markTerminal(id, "CANCELLED", { errorCode: "CANCELLED", errorMessage: "任务已被取消" });
        return this.get(id);
      }
      if (r.status === "RUNNING") {
        const flag = live.get(id);
        if (flag) flag.cancelled = true; // 修复：可选链不能作赋值左侧（node --check SyntaxError），等量改写作者意图「在跑则置旗标」
        return this.get(id);
      }
      throw new TaskShellError("INVALID_STATE", `终态任务不可取消（当前 ${r.status}）`);
    },

    // 重试：仅 FAILED（含 BRIDGE_RESTART）；retry_count+1 回 QUEUED 重新起跑。R6。
    retry(id) {
      const r = getRow.get(id);
      if (!r) throw new TaskShellError("NOT_FOUND", `任务不存在 ${id}`);
      if (r.status !== "FAILED") throw new TaskShellError("INVALID_STATE", `仅 FAILED 可重试（当前 ${r.status}）`);
      db.prepare(`UPDATE async_tasks SET status = 'QUEUED', retry_count = retry_count + 1,
                   error_code = NULL, error_message = NULL, started_at = NULL, finished_at = NULL WHERE id = ?`)
        .run(id);
      void run(id);
      return this.get(id);
    },

    // 取件路径：只认本任务 id 名下的 result_ref（白名单由构造保证，R5）。仅 SUCCEEDED 未过期可取。
    artifactPath(id) {
      const t = this.get(id);   // 走 get：含惰性过期翻转
      if (t.status === "EXPIRED") throw new TaskShellError("INVALID_STATE", "产物已过保留期，请重新发起任务");
      if (t.status !== "SUCCEEDED") throw new TaskShellError("INVALID_STATE", `任务未完成（当前 ${t.status}）`);
      if (!t.resultRef || !t.fileName || !artifactsDir) throw new TaskShellError("INVALID_STATE", "任务无产物文件");
      const abs = join(artifactsDir, t.resultRef);
      if (!existsSync(abs)) throw new TaskShellError("INVALID_STATE", "产物文件缺失");
      return { path: abs, fileName: t.fileName };
    },
  };
}
