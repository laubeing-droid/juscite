// 功能 #28 桌宠 · AI 工具面 juscite_pet（RE-28 §3.2 驱动流 2；行为等量 A19-A23）。
// 合同全落：入参 {macro} strict 八枚举；入参非法不抛错返回 VALIDATION_FAILED（A20）；
// 宿主调用 20s 超时降级 PET_UNAVAILABLE 不抛（A23）；结果文本两态（A21，措辞自写）；
// 回执卡片 {card:'pet',macro,status}（A22 形状）。
// 模型侧注册面=oc28 上游运行时（#20 同款边界：不在自家仓伪造上游工具环），
// 本模块为壳侧可执行工具件，接线点随上游工具面开放即挂。
// 免审批 visual 类（A19）：桌宠动作无破坏面，进入本模块即执行、无需人工确认。

import { compileMacroSequence, type PetSequenceResult } from "./admission.js";
import { PET_MACRO_CATALOG, PET_MACRO_IDS, type PetMacroId } from "./motions.js";

export const PET_TOOL_NAME = "juscite_pet";
/** 宿主调用超时（A23：20s 超时降级 PET_UNAVAILABLE）。 */
export const PET_HOST_TIMEOUT_MS = 20_000;

export interface PetToolReceipt {
  card: "pet";
  macro: PetMacroId;
  status: "completed" | "interrupted" | "failed";
}

export interface PetToolResult {
  text: string;
  isError: false;
  details: {
    macro: PetMacroId;
    status: PetToolReceipt["status"];
    code?: string;
    card: PetToolReceipt;
  };
}

export interface PetToolDeps {
  /** 序列执行入口（PetAdmissionController.execute）。 */
  executeSequence: (params: unknown) => Promise<PetSequenceResult>;
  /** 可注入时钟（合成自测用）；默认 setTimeout。 */
  schedule?: (fn: () => void, ms: number) => () => void;
}

export interface PetTool {
  name: typeof PET_TOOL_NAME;
  /** 工具描述（自写措辞，表达隔离）。 */
  description: string;
  /** 入参 schema（strict 八枚举，等量 A19 形状）。 */
  inputSchema: {
    type: "object";
    additionalProperties: false;
    required: ["macro"];
    properties: { macro: { type: "string"; enum: readonly PetMacroId[] } };
  };
  execute(rawInput: unknown): Promise<PetToolResult>;
}

function settleResult(macro: PetMacroId, result: PetSequenceResult): PetToolResult {
  const status = result.status;
  const completed = status === "completed";
  const text = completed ? `桌宠动作完成：${macro}` : `桌宠动作未完成：${macro}`;
  return {
    text,
    isError: false,
    details: {
      macro,
      status,
      ...(status === "failed" ? { code: result.code } : {}),
      ...(status === "interrupted" ? { code: result.reasonCode } : {}),
      card: { card: "pet", macro, status },
    },
  };
}

export function createPetTool(deps: PetToolDeps): PetTool {
  const schedule =
    deps.schedule ??
    ((fn: () => void, ms: number) => {
      const t = setTimeout(fn, ms);
      return () => clearTimeout(t);
    });
  return {
    name: PET_TOOL_NAME,
    description:
      "让桌面的桌宠伙伴播一段状态小动画，向用户传达陪伴情绪：thinking=在想方案、working=在干活、awaitApproval=等你确认、celebrate=办成了、sad=遇到了问题、curious=好奇张望、explain=讲解中、returnHome=回到窝里。",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      required: ["macro"],
      properties: { macro: { type: "string", enum: PET_MACRO_IDS } },
    },
    async execute(rawInput: unknown): Promise<PetToolResult> {
      // 入参非法不抛错（A20）：返回 VALIDATION_FAILED 文本结果。
      const macro =
        typeof rawInput === "object" && rawInput !== null
          ? (rawInput as { macro?: unknown }).macro
          : undefined;
      if (typeof macro !== "string" || !(PET_MACRO_IDS as readonly string[]).includes(macro)) {
        const fallback: PetMacroId = "thinking";
        return {
          text: `桌宠动作未完成：入参无效（macro 必须是 ${PET_MACRO_IDS.join("/")} 之一）`,
          isError: false,
          details: {
            macro: fallback,
            status: "failed",
            code: "VALIDATION_FAILED",
            card: { card: "pet", macro: fallback, status: "failed" },
          },
        };
      }
      const macroId = macro as PetMacroId;
      return await new Promise<PetToolResult>((resolve) => {
        let done = false;
        let cancelTimer: (() => void) | null = null;
        const finish = (result: PetToolResult) => {
          if (done) return;
          done = true;
          cancelTimer?.();
          resolve(result);
        };
        cancelTimer = schedule(() => {
          finish({
            text: `桌宠动作未完成：${macroId}`,
            isError: false,
            details: {
              macro: macroId,
              status: "failed",
              code: "PET_UNAVAILABLE",
              card: { card: "pet", macro: macroId, status: "failed" },
            },
          });
        }, PET_HOST_TIMEOUT_MS);
        deps
          .executeSequence(compileMacroSequence(macroId))
          .then((result) => finish(settleResult(macroId, result)))
          .catch(() =>
            finish({
              text: `桌宠动作未完成：${macroId}`,
              isError: false,
              details: {
                macro: macroId,
                status: "failed",
                code: "PET_UNAVAILABLE",
                card: { card: "pet", macro: macroId, status: "failed" },
              },
            }),
          );
      });
    },
  };
}
