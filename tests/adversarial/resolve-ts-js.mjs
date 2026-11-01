// Node 的类型剥离不会把 TypeScript 的 .js 说明符改写成旁边的 .ts。
// 只给对抗测试的加载链用，不改生产模块说明符。
export async function resolve(specifier, context, nextResolve) {
  if (typeof specifier === "string" && specifier.endsWith(".js") && !specifier.endsWith(".mjs")) {
    try {
      return await nextResolve(specifier.slice(0, -3) + ".ts", context);
    } catch {
      // 旁边没有 .ts 时保持原说明符。
    }
  }
  return nextResolve(specifier, context);
}
