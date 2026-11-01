// 验证修复终点：createComposerSubmissionConfig(桥 view 派生的 draftConfig) !== null
import { createComposerSubmissionConfig } from "../../packages/ui/src/v4/composer/composerSubmissionConfig.js";
const r = await fetch("http://localhost:3030/x").catch(() => null); // noop warm
const view = {
  revision: 1,
  providers: [{ providerId: "deepseek", providerName: "DeepSeek（合成）", models: [{ modelId: "deepseek-chat", config: { optionSpecs: { reasoningLevel: { values: ["off", "on"], map: "{}" } } } }] }],
  effectiveSelection: { providerId: "deepseek", modelId: "deepseek-chat", options: { reasoningLevel: "on" } },
};
// useDraftConfigControl 派生：modelSelection=effectiveSelection（view 在场时）
const draftConfig = { mode: "build", planEnabled: false, modelSelection: view.effectiveSelection, provider: "deepseek", model: "deepseek-chat", thought: "on" };
const result = createComposerSubmissionConfig(draftConfig as never, view as never);
console.log(result ? "SUBMISSION_READY_PASS " + JSON.stringify(result.mode) + " " + JSON.stringify(result.modelSelection) : "SUBMISSION_READY_FAIL(null)");
process.exit(result ? 0 : 1);
