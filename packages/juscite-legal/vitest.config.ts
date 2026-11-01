// @juscite/legal 面板族合同测试配置（施工波二轮·可视化B轨 UI 件）。
// 只跑本包 test/ 下纯函数合同测试（零 React 零 DOM，node 环境）；与 packages/ui 的
// UI 合同测试分文件分配置，ci_gate fast 分别跑两套并各自钉死期望数。
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { environment: "node" },
});
