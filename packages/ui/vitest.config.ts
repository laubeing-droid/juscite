import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// react/react-dom 别名钉到 pnpm 实体路径（非符号链 id）：@juscite/legal 面板源（树内自有包）
// 经 vitest 变换载入时其 `import "react"` 停在根符号链 id，而 @testing-library/react 的
// react-dom 走 node require 实体 id——同一文件双实例，面板 useState 全数崩
// （2026-10-30 #43 消费面合同测试实测）。别名归一后单实例；升版时随 pnpm store 目录同步。
const reactReal = fileURLToPath(new URL("../../node_modules/.pnpm/react@19.2.7/node_modules/react", import.meta.url));
const reactDomReal = fileURLToPath(new URL("../../node_modules/.pnpm/react-dom@19.2.7_react@19.2.7/node_modules/react-dom", import.meta.url));

export default defineConfig({
  resolve: {
    alias: [
      { find: "@", replacement: fileURLToPath(new URL("./src", import.meta.url)) },
      { find: /^react$/, replacement: reactReal },
      { find: /^react-dom$/, replacement: reactDomReal },
    ],
  },
});
