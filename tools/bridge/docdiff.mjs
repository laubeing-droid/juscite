// 功能 #25 文档对比（施工单-03 任务四）：确定性行级 diff。
// 纯 Node 零依赖；Myers O((N+M)D) + 公共前后缀修剪 + 步数封顶降级整段替换。
// 法律工作区约束：对比一律确定性算法产出，不靠模型猜；hunk 分类（增/删/改）供变更清单。
const MAX_D = 2000; // 编辑图最大步数：超过即抛由上层降级（两份几乎全异的大文档不卡死）

export function splitLines(text) {
  return String(text ?? "").split(/\r\n|\r|\n/);
}

// op: {t:"=",a,b,text} | {t:"-",a,text} | {t:"+",b,text}（行号均 0 基）
export function diffOps(aLines, bLines) {
  const n = aLines.length, m = bLines.length;
  let pre = 0;
  while (pre < n && pre < m && aLines[pre] === bLines[pre]) pre++;
  let suf = 0;
  while (suf < n - pre && suf < m - pre && aLines[n - 1 - suf] === bLines[m - 1 - suf]) suf++;
  const ops = [];
  for (let i = 0; i < pre; i++) ops.push({ t: "=", a: i, b: i, text: aLines[i] });
  const aMid = aLines.slice(pre, n - suf), bMid = bLines.slice(pre, m - suf);
  if (aMid.length === 0 && bMid.length > 0) {
    bMid.forEach((text, j) => ops.push({ t: "+", b: pre + j, text }));
  } else if (bMid.length === 0 && aMid.length > 0) {
    aMid.forEach((text, i) => ops.push({ t: "-", a: pre + i, text }));
  } else if (aMid.length > 0 && bMid.length > 0) {
    let mid;
    try {
      mid = myers(aMid, bMid);
    } catch (e) {
      if (!/^diff_d_limit/.test(String(e?.message ?? e))) throw e;
      // 降级：编辑图超界（几乎全异的超大对比）→ 整段替换，诚实标注，不挂死
      mid = [
        ...aMid.map((text, i) => ({ t: "-", a: i, text })),
        ...bMid.map((text, j) => ({ t: "+", b: j, text })),
      ];
    }
    for (const o of mid) {
      if (o.t === "=") ops.push({ t: "=", a: pre + o.a, b: pre + o.b, text: o.text });
      else if (o.t === "-") ops.push({ t: "-", a: pre + o.a, text: o.text });
      else ops.push({ t: "+", b: pre + o.b, text: o.text });
    }
  }
  for (let k = 0; k < suf; k++) {
    ops.push({ t: "=", a: n - suf + k, b: m - suf + k, text: aLines[n - suf + k] });
  }
  return ops;
}

// hunk 分类：紧邻的删块+增块并成一段"改"；纯增="增"；纯删="删"。
// 形状：{type,aStart,aCount,bStart,bCount,oldText,newText}（行号 0 基；aStart=受影响旧文首行，
// 纯增时 aCount=0 且 aStart=插入位置之前所在旧行号）。
export function buildHunks(ops) {
  const hunks = [];
  let i = 0;
  while (i < ops.length) {
    if (ops[i].t === "=") { i++; continue; }
    const dels = [], adds = [];
    while (i < ops.length && ops[i].t === "-") { dels.push(ops[i]); i++; }
    while (i < ops.length && ops[i].t === "+") { adds.push(ops[i]); i++; }
    const oldText = dels.map((o) => o.text).join("\n");
    const newText = adds.map((o) => o.text).join("\n");
    if (dels.length && adds.length) {
      hunks.push({ type: "mod", aStart: dels[0].a, aCount: dels.length, bStart: adds[0].b, bCount: adds.length, oldText, newText });
    } else if (dels.length) {
      hunks.push({ type: "del", aStart: dels[0].a, aCount: dels.length, bStart: adds[0]?.b ?? 0, bCount: 0, oldText, newText: "" });
    } else {
      hunks.push({ type: "add", aStart: adds[0].b, aCount: 0, bStart: adds[0].b, bCount: adds.length, oldText: "", newText });
    }
  }
  return hunks;
}

export function diffStats(totalOld, totalNew, hunks) {
  let added = 0, deleted = 0, modified = 0, changedNew = 0, changedOld = 0;
  for (const h of hunks) {
    if (h.type === "add") { added++; changedNew += h.bCount; }
    else if (h.type === "del") { deleted++; changedOld += h.aCount; }
    else { modified++; changedNew += h.bCount; changedOld += h.aCount; }
  }
  return { added, deleted, modified, unchangedOld: totalOld - changedOld, unchangedNew: totalNew - changedNew };
}

// 标准 Myers（贪心 + 全量 trace 回溯）。trace 按轮存 k∈[-d,d] 切片，内存 O(D²)。
function myers(a, b) {
  const n = a.length, m = b.length, max = n + m;
  if (max === 0) return [];
  const off = max;
  const v = new Int32Array(2 * max + 1);
  const trace = [];
  let dFound = -1;
  for (let d = 0; d <= Math.min(max, MAX_D); d++) {
    trace.push(v.slice(off - d, off + d + 1)); // 本轮起点快照（即上轮结果）
    for (let k = -d; k <= d; k += 2) {
      let x;
      if (k === -d || (k !== d && v[off + k - 1] < v[off + k + 1])) x = v[off + k + 1];
      else x = v[off + k - 1] + 1;
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) { x++; y++; }
      v[off + k] = x;
      if (x >= n && y >= m) { dFound = d; break; }
    }
    if (dFound >= 0) break;
  }
  if (dFound < 0) throw new Error("diff_d_limit");
  const out = [];
  let x = n, y = m;
  for (let d = dFound; d >= 1; d--) {
    const snap = trace[d]; // 覆盖 k∈[-d,d]，偏移 d
    const k = x - y;
    let prevK;
    if (k === -d || (k !== d && snap[k - 1 + d] < snap[k + 1 + d])) prevK = k + 1;
    else prevK = k - 1;
    const prevX = snap[prevK + d], prevY = prevX - prevK;
    while (x > prevX && y > prevY) { x--; y--; out.push({ t: "=", a: x, b: y, text: a[x] }); }
    if (x === prevX) { y--; out.push({ t: "+", b: y, text: b[y] }); }
    else { x--; out.push({ t: "-", a: x, text: a[x] }); }
  }
  while (x > 0 && y > 0 && a[x - 1] === b[y - 1]) { x--; y--; out.push({ t: "=", a: x, b: y, text: a[x] }); }
  while (x > 0) { x--; out.push({ t: "-", a: x, text: a[x] }); }
  while (y > 0) { y--; out.push({ t: "+", b: y, text: b[y] }); }
  out.reverse();
  return out;
}
