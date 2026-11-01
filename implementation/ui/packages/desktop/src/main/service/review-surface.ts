import { app, ipcMain } from "electron"
import { existsSync, readFileSync } from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"
import { randomUUID } from "node:crypto"
import { writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"

// F82 复核/单格重跑/人工改格三面桌面通道（W2b-U31）。经产品 Python 桥
// （legal_entry CLI：tabular.read/review_status/review_receipt/cell_rerun/
// cell_history＋harness.review_batch_human_edit）读写 harness 审查账——
// 账本唯一真源在 harness MatterStore；本模块只转发，不缓存不重算（第二
// 权威＝漂移根源）。载荷只含审查账投影（列/格/世代/来源/状态/回执），
// 不含原件路径或身份映射。
//
// 唯一写通道（F84 红线）：复核/重跑/人改按钮的一切写动作都经本通道→
// 产品桥→harness 写权限方法；桌面进程不直写任何账、不开第二通道。
//
// fail-closed：未配置（config 缺失/字段不全/桥脚本缺失）＝IPC 句柄注册
// 但一律回错误码，渲染层 seam 调用失败显示「审查面未接入」，绝不回伪造
// 投影；桥侧具名拒（迟到/旧世代/人改后重跑等）typed 码原样透传（UI 响
// 亮呈现，不静默）。

const TableChannel = "lvyin:review:table" as const
const ReceiptChannel = "lvyin:review:receipt" as const
const RerunChannel = "lvyin:review:rerun" as const
const EditChannel = "lvyin:review:edit" as const
const HistoryChannel = "lvyin:review:history" as const

type ReviewConfig = {
  python?: string
  bridge_entry: string
  review_batch_id: string
  review_matter_id: string
  harness_public_entry: string
  harness_target: string
  harness_state_root?: string
  harness_service_registration?: string
  harness_python?: string
}

function configPath(): string {
  return path.join(app.getPath("userData"), "config", "lvyin", "review.json")
}

function loadConfig(): ReviewConfig | null {
  try {
    const raw = JSON.parse(readFileSync(configPath(), "utf8")) as ReviewConfig
    if (!raw.bridge_entry || !raw.review_batch_id || !raw.review_matter_id
        || !raw.harness_public_entry || !raw.harness_target) {
      return null
    }
    return raw
  } catch {
    return null
  }
}

async function bridgeCall(config: ReviewConfig, method: string,
                          args: unknown): Promise<any> {
  const request = path.join(tmpdir(), `lvyin-review-${randomUUID()}.json`)
  const configCopy = path.join(tmpdir(), `lvyin-review-cfg-${randomUUID()}.json`)
  await writeFile(request, JSON.stringify({ method, args }), "utf8")
  const bridgeConfig: Record<string, unknown> = {
    harness_public_entry: config.harness_public_entry,
    harness_target: config.harness_target,
    harness_python: config.harness_python,
  }
  if (config.harness_state_root) {
    bridgeConfig["harness_state_root"] = config.harness_state_root
  }
  if (config.harness_service_registration) {
    bridgeConfig["harness_service_registration"]
      = config.harness_service_registration
  }
  await writeFile(configCopy, JSON.stringify(bridgeConfig), "utf8")
  const python = config.python ?? "python"
  return new Promise((resolve, reject) => {
    const child = spawn(python, ["-X", "utf8", config.bridge_entry,
      "--request-json", request, "--config", configCopy],
      { stdio: ["ignore", "pipe", "pipe"] })
    let stdout = ""
    child.stdout.on("data", (chunk) => (stdout += chunk))
    child.on("error", reject)
    child.on("close", (code) => {
      try {
        const payload = JSON.parse(stdout)
        if (code === 0 && payload.status === "OWNER_RESPONSE") {
          resolve(payload.result)
        } else {
          reject(new Error(payload.code ?? `bridge_exit_${code}`))
        }
      } catch (failure) {
        reject(failure instanceof Error ? failure
                                     : new Error("bridge_protocol_invalid"))
      }
    })
  })
}

function scopeOf(config: ReviewConfig) {
  return { kind: "matter", matterId: config.review_matter_id }
}

function keyOf(tag: string) {
  // 每次写动作一个新 request id（用户重复点击＝新请求；幂等语义在
  // harness CommandKey 面由账本承担）。
  return { requestId: `ui-${tag}-${Date.now()}-${randomUUID().slice(0, 8)}`,
           targetId: null, expectedRevision: null, inputRefs: [] }
}

function configured(): ReviewConfig | null {
  const config = loadConfig()
  if (!config || !existsSync(config.bridge_entry)) return null
  return config
}

export function startReviewSurface(): void {
  ipcMain.handle(TableChannel, async () => {
    const config = configured()
    if (!config) throw new Error("review_not_configured")
    const scope = scopeOf(config)
    const [read, status] = await Promise.all([
      bridgeCall(config, "tabular.read",
                 { review_batch_id: config.review_batch_id, scope }),
      bridgeCall(config, "tabular.review_status",
                 { review_batch_id: config.review_batch_id, scope }),
    ])
    return { read, status }
  })
  ipcMain.handle(ReceiptChannel, async (_event, rowId: string,
                                        cellId: string, decision: string,
                                        decisionRef: string) => {
    const config = configured()
    if (!config) throw new Error("review_not_configured")
    return bridgeCall(config, "tabular.review_receipt", {
      review_batch_id: config.review_batch_id, row_id: rowId,
      cell_id: cellId,
      receipt: { reviewer: "desktop-reviewer", decision,
                 decisionRef },
      actor_id: "desktop-reviewer", scope: scopeOf(config),
      key: keyOf("receipt"),
    })
  })
  ipcMain.handle(RerunChannel, async (_event, rowId: string,
                                      cellId: string, value: string) => {
    const config = configured()
    if (!config) throw new Error("review_not_configured")
    return bridgeCall(config, "tabular.cell_rerun", {
      review_batch_id: config.review_batch_id, row_id: rowId,
      cell_id: cellId, value, actor_id: "desktop-worker",
      scope: scopeOf(config), key: keyOf("rerun"),
    })
  })
  ipcMain.handle(EditChannel, async (_event, rowId: string,
                                     cellId: string, value: string,
                                     generation: number) => {
    const config = configured()
    if (!config) throw new Error("review_not_configured")
    return bridgeCall(config, "harness.review_batch_human_edit", {
      actor_id: "desktop-lawyer", scope: scopeOf(config),
      key: keyOf("human-edit"), batch_id: config.review_batch_id,
      row_id: rowId,
      cells: [{ cellId, value, generation }],
    })
  })
  ipcMain.handle(HistoryChannel, async (_event, rowId: string,
                                        cellId: string) => {
    const config = configured()
    if (!config) throw new Error("review_not_configured")
    return bridgeCall(config, "tabular.cell_history", {
      review_batch_id: config.review_batch_id, row_id: rowId,
      cell_id: cellId, scope: scopeOf(config),
    })
  })
}
