import { createRequire } from "node:module";
import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// react/react-dom 别名钉到同一物理目录（非符号链 id）：@juscite/legal 面板源（树内自有包）
// 经 vitest 变换载入时其 `import "react"` 停在根符号链 id，而 @testing-library/react 的
// react-dom 走 node require 实体 id——同一文件双实例，面板 useState 全数崩
// （2026-10-30 #43 消费面合同测试实测）。别名归一后单实例。
// 解析走 node 的包查找再 realpath：.npmrc 是 node-linker=hoisted（没有
// node_modules/.pnpm/react@<ver> 这层），孤立 linker 下 realpath 仍落到 store 实体。
const require = createRequire(import.meta.url);
function packageDir(name: string) {
  return realpathSync(require.resolve(`${name}/package.json`)).replace(/[/\\]package\.json$/, "");
}
const reactReal = packageDir("react");
const reactDomReal = packageDir("react-dom");

export default defineConfig({
  resolve: {
    alias: [
      { find: "@", replacement: fileURLToPath(new URL("./src", import.meta.url)) },
      { find: /^react$/, replacement: reactReal },
      { find: /^react-dom$/, replacement: reactDomReal },
    ],
  },
});
