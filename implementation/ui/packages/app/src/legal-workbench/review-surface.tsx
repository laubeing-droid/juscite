import { createResource, createSignal, For, Show } from "solid-js"
import {
  carriedGeneration,
  mergeTable,
  REVIEW_LABELS,
  SUPPORT_LABELS,
  ReviewSurfaceError,
  type ReviewCell,
  type ReviewStatusDoc,
  type ReviewTable,
  type TabularReadDoc,
} from "./review-ops"

// F82 复核/单格重跑/人工改格三面（W2b-U31）：原生 Tabular 审查面投影。
// 数据只经桌面 seam（preload 注入的 window.lvyinReview，背后是产品 Python
// 桥 legal_entry tabular.read/review_status/review_receipt/cell_rerun/
// cell_history＋harness.review_batch_human_edit——审查账唯一真源在 harness
// MatterStore）。本面零第二写通道（F84 红线）：复核/重跑/人改按钮全部经
// seam→产品桥→harness 写权限方法，前端不直写任何账。
//
// fail-closed：seam 缺席＝显示「审查面未接入」不伪造数据；闭集外状态＝
// 响亮报错不静默渲染；写动作失败＝typed 码原样显示（迟到/旧世代/人改后
// 重跑三路具名拒在 UI 即如实呈现）。

export type ReviewHistory = {
  versions?: { generation: number; value?: unknown; source?: string; rowState?: string }[]
  current?: { generation: number; value?: unknown; source?: string }
}

export type ReviewSeam = {
  table(): Promise<{ read: TabularReadDoc; status: ReviewStatusDoc }>
  receipt(rowId: string, cellId: string, decision: string, decisionRef: string): Promise<unknown>
  rerun(rowId: string, cellId: string, value: string): Promise<unknown>
  humanEdit(rowId: string, cellId: string, value: string, generation: number): Promise<unknown>
  history(rowId: string, cellId: string): Promise<ReviewHistory>
}

declare global {
  interface Window {
    lvyinReview?: ReviewSeam
  }
}

const DECISIONS = ["confirmed", "rejected"] as const

export function ReviewSurface() {
  const seam = () => window.lvyinReview
  const [notice, setNotice] = createSignal("")
  const [error, setError] = createSignal("")
  const [busy, setBusy] = createSignal(false)
  const [decision, setDecision] = createSignal<string>("confirmed")
  const [decisionRef, setDecisionRef] = createSignal("")
  const [newValue, setNewValue] = createSignal("")
  const [editValue, setEditValue] = createSignal("")
  const [history, setHistory] = createSignal<ReviewHistory | null>(null)

  const [doc, { refetch }] = createResource(async (): Promise<ReviewTable | null> => {
    const s = seam()
    if (!s) return null
    const { read, status } = await s.table()
    return mergeTable(read, status)
  })

  function cellKey(rowId: string, cellId: string) {
    return rowId + ":" + cellId
  }

  async function run(action: string, fn: () => Promise<unknown>) {
    setError("")
    setNotice("")
    setBusy(true)
    try {
      await fn()
      setNotice(action + " 已落账（经产品桥→harness）；重新读取中。")
      await refetch()
    } catch (failure) {
      const code = failure instanceof Error ? failure.message : String(failure)
      setError(action + "失败（" + code + "）——不静默：typed 码原样呈现。")
    } finally {
      setBusy(false)
    }
  }

  const doReceipt = (rowId: string, cell: ReviewCell) =>
    run("复核回执", () => {
      const ref = decisionRef().trim()
      if (!ref) throw new ReviewSurfaceError("f82_decision_ref_required")
      return seam()!.receipt(rowId, cell.columnId, decision(), ref)
    })

  const doRerun = (rowId: string, cell: ReviewCell) =>
    run("单格重跑", () => {
      const value = newValue().trim()
      if (!value) throw new ReviewSurfaceError("f82_rerun_value_required")
      return seam()!.rerun(rowId, cell.columnId, value)
    })

  const doHumanEdit = (rowId: string, cell: ReviewCell) =>
    run("人工改格", () => {
      const value = editValue().trim()
      if (!value) throw new ReviewSurfaceError("f82_edit_value_required")
      return seam()!.humanEdit(rowId, cell.columnId, value, carriedGeneration(cell))
    })

  const doHistory = (rowId: string, cell: ReviewCell) =>
    run("履历回读", async () => {
      const result = await seam()!.history(rowId, cell.columnId)
      setHistory({ ...result, cellKey: cellKey(rowId, cell.columnId) } as ReviewHistory & { cellKey: string })
    })

  return (
    <section class="border-b border-current/15 p-3" aria-label="Tabular 审查面" data-testid="review-surface">
      <div class="flex flex-wrap items-center gap-3">
        <strong>Tabular 审查面</strong>
        <span class="text-xs opacity-70">复核／单格重跑／人工改格——全部经产品桥（唯一写通道）</span>
        <button type="button" class="rounded border border-current/20 px-2 py-1" onClick={() => void refetch()}>
          重新读取
        </button>
        <Show when={doc()}>
          {(table) => (
            <span class="text-xs opacity-60" data-testid="review-table-meta">
              {table().batchId} · {table().batchStatus} · {table().rows.length} 行
            </span>
          )}
        </Show>
      </div>
      <Show
        when={seam() && !doc.loading}
        fallback={
          <p class="mt-2 text-xs opacity-70" data-testid="review-not-connected">
            审查面未接入（桌面桥未配置）。接入后此处按 harness 审查账投影显示复核表；未接入时不显示任何编造数据。
          </p>
        }
      >
        <Show when={doc()}>
          {(table) => (
            <>
              <div class="mt-3 flex flex-wrap items-end gap-2" role="group" aria-label="写动作参数">
                <label class="flex flex-col gap-1 text-xs">复核决定
                  <select
                    class="rounded border border-current/20 bg-transparent p-1"
                    data-testid="review-decision-select"
                    value={decision()}
                    onChange={(event) => setDecision(event.currentTarget.value)}
                  >
                    <For each={DECISIONS}>{(item) => <option value={item}>{REVIEW_LABELS[item === "confirmed" ? "REVIEWED_CONFIRMED" : "REVIEWED_REJECTED"]}</option>}</For>
                  </select>
                </label>
                <label class="flex flex-col gap-1 text-xs">决定 ref（必填）
                  <input
                    class="w-48 rounded border border-current/20 bg-transparent p-1"
                    data-testid="review-decision-ref"
                    value={decisionRef()}
                    onInput={(event) => setDecisionRef(event.currentTarget.value)}
                  />
                </label>
                <label class="flex flex-col gap-1 text-xs">重跑值（合成）
                  <input
                    class="w-40 rounded border border-current/20 bg-transparent p-1"
                    data-testid="review-rerun-value"
                    value={newValue()}
                    onInput={(event) => setNewValue(event.currentTarget.value)}
                  />
                </label>
                <label class="flex flex-col gap-1 text-xs">人工改格值
                  <input
                    class="w-40 rounded border border-current/20 bg-transparent p-1"
                    data-testid="review-edit-value"
                    value={editValue()}
                    onInput={(event) => setEditValue(event.currentTarget.value)}
                  />
                </label>
              </div>
              <p class="mt-1 text-xs" role="status" aria-live="polite" data-testid="review-notice">{notice()}</p>
              <p class="mt-1 text-xs text-red-500" role="alert" data-testid="review-error">{error()}</p>
              <div class="mt-2 max-h-[42vh] overflow-auto">
                <table class="w-full border-collapse text-xs" data-testid="review-table">
                  <thead>
                    <tr class="border-b border-current/20 text-left">
                      <th class="p-1">行</th>
                      <th class="p-1">列</th>
                      <th class="p-1">值</th>
                      <th class="p-1">世代/来源</th>
                      <th class="p-1">支持状态</th>
                      <th class="p-1">复核状态</th>
                      <th class="p-1">金标</th>
                      <th class="p-1">动作（经产品桥）</th>
                    </tr>
                  </thead>
                  <tbody>
                    <For each={table().rows}>
                      {(row) => (
                        <For each={row.cells}>
                          {(cell) => (
                            <tr
                              class="border-b border-current/10"
                              data-testid="review-cell-row"
                              data-review-cell={cellKey(row.rowId, cell.columnId)}
                              data-review-row-state={row.rowState}
                              data-review-support={cell.supportStatus}
                              data-review-status={cell.reviewStatus}
                              data-review-generation={cell.cellGeneration}
                              data-review-source={cell.cellSource}
                            >
                              <td class="p-1 align-top">{row.rowId}</td>
                              <td class="p-1 align-top">{cell.columnId}</td>
                              <td class="p-1 align-top" data-testid="review-cell-value">{String(cell.value ?? "∅")}</td>
                              <td class="p-1 align-top">gen {cell.cellGeneration} · {cell.cellSource}</td>
                              <td class="p-1 align-top">{SUPPORT_LABELS[cell.supportStatus]}</td>
                              <td class="p-1 align-top">{REVIEW_LABELS[cell.reviewStatus]}</td>
                              <td class="p-1 align-top">
                                {cell.goldMatch === true ? "对上" : cell.goldMatch === false ? "未对上（" + (cell.goldMatchReason ?? "") + "）" : "不可对照"}
                              </td>
                              <td class="p-1 align-top">
                                <span class="flex flex-wrap gap-1">
                                  <button type="button" disabled={busy()} class="rounded border border-current/20 px-1" data-review-action="receipt" onClick={() => void doReceipt(row.rowId, cell)}>复核</button>
                                  <button type="button" disabled={busy()} class="rounded border border-current/20 px-1" data-review-action="rerun" onClick={() => void doRerun(row.rowId, cell)}>重跑</button>
                                  <button type="button" disabled={busy()} class="rounded border border-current/20 px-1" data-review-action="human-edit" onClick={() => void doHumanEdit(row.rowId, cell)}>人工改格</button>
                                  <button type="button" disabled={busy()} class="rounded border border-current/20 px-1" data-review-action="history" onClick={() => void doHistory(row.rowId, cell)}>履历</button>
                                </span>
                              </td>
                            </tr>
                          )}
                        </For>
                      )}
                    </For>
                  </tbody>
                </table>
              </div>
              <Show when={history()}>
                {(h) => (
                  <div class="mt-2 rounded border border-current/15 p-2 text-xs" data-testid="review-history" data-history-cell={(h() as ReviewHistory & { cellKey?: string }).cellKey}>
                    <strong>格履历（{(h() as ReviewHistory & { cellKey?: string }).cellKey}）</strong>
                    <ol class="mt-1">
                      <For each={h().versions ?? []}>
                        {(version) => (
                          <li data-history-generation={version.generation}>
                            gen {version.generation} · {version.source} · {String(version.value ?? "∅")} · 行态 {version.rowState}
                          </li>
                        )}
                      </For>
                    </ol>
                  </div>
                )}
              </Show>
            </>
          )}
        </Show>
      </Show>
    </section>
  )
}
