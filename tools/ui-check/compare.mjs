// 두 PC 기록을 비교한다. 사용: node compare.mjs <OUT> <before> <after>
import { readFileSync } from "node:fs";
import { join } from "node:path";
const [OUT, A, B] = process.argv.slice(2);
const a = JSON.parse(readFileSync(join(OUT, `${A}.json`), "utf8"));
const b = JSON.parse(readFileSync(join(OUT, `${B}.json`), "utf8"));
let total = 0;
for (const page of Object.keys(a)) {
  const diffs = [];
  const keys = new Set([...Object.keys(a[page]), ...Object.keys(b[page] ?? {})]);
  // DOM 안에서 감싸는 요소만 바뀐 경우: 위치·모양·글자가 같은 요소끼리 짝지어 "같음"으로 본다.
  // 시각 글자(01:42 → 02:00)는 실행할 때마다 달라지므로 숫자는 같은 것으로 본다.
  const sig = (v) => `${v.box}|${v.style}|${v.text.replace(/\d/g, "0")}`;
  const onlyA = [...keys].filter((k) => !b[page]?.[k]).map((k) => sig(a[page][k]));
  const onlyB = [...keys].filter((k) => !a[page][k]).map((k) => sig(b[page][k]));
  const pool = [...onlyB];
  const unmatchedA = new Set(onlyA.filter((s) => { const i = pool.indexOf(s); if (i >= 0) { pool.splice(i, 1); return false; } return true; }));
  const pool2 = [...onlyA];
  const unmatchedB = new Set(onlyB.filter((s) => { const i = pool2.indexOf(s); if (i >= 0) { pool2.splice(i, 1); return false; } return true; }));
  for (const key of keys) {
    const x = a[page][key], y = b[page]?.[key];
    const short = key.split(">").slice(-2).join(">");
    if (!x) { if (unmatchedB.has(sig(y))) diffs.push(`  + ${short} ${y.box} "${y.text}"`); }
    else if (!y) { if (unmatchedA.has(sig(x))) diffs.push(`  - ${short} ${x.box} "${x.text}"`); }
    else {
      if (x.box !== y.box) diffs.push(`  box ${short}: ${x.box} → ${y.box} "${x.text}"→"${y.text}"`);
      if (x.style !== y.style) diffs.push(`  style ${short}: ${x.style} → ${y.style}`);
    }
  }
  total += diffs.length;
  console.log(`${page}: ${diffs.length === 0 ? "같음" : diffs.length + "곳 다름"}`);
  for (const d of diffs.slice(0, 12)) console.log(d);
}
console.log(`합계 ${total}곳`);
