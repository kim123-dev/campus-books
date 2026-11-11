// measure.mjs 결과 요약: 화면별 중앙값(본문 표시·FCP·요청 수)과 한 번의 실행에서 나간 요청 목록.
// 사용: node tools/perf/report.mjs <results.json> [실행 번호=1] [first|second|cold]
import { readFileSync } from "node:fs";
const d = JSON.parse(readFileSync(process.argv[2], "utf8"));
const kinds = ["first", "second", "cold"];
const med = (xs) => { const s = xs.filter((x) => x != null).sort((a, b) => a - b); return s.length ? Math.round(s[Math.floor(s.length / 2)]) : null; };
console.log("| 화면 | " + kinds.map((k) => `${k} 본문(ms) | ${k} FCP | ${k} 요청 수(net/304·캐시)`).join(" | "));
for (const name of ["list", "detail", "inbox", "profile"]) {
  const cells = kinds.map((k) => {
    const vs = d.results.map((r) => r[k]?.find((v) => v.name === name)).filter(Boolean);
    const net = vs.map((v) => v.requests.filter((q) => q.durMs > 20).length);
    return `${med(vs.map((v) => v.ready))} | ${med(vs.map((v) => v.fcp))} | ${vs[0]?.requests.length}(${med(net)})`;
  });
  console.log(`| ${name} | ${cells.join(" | ")}`);
}
const run = Number(process.argv[3] ?? 1);
for (const k of process.argv[4] ? [process.argv[4]] : kinds) {
  for (const v of d.results[run][k] ?? []) {
    console.log(`\n## ${k} ${v.name} 본문=${Math.round(v.ready)} TTFB=${Math.round(v.ttfb)} DCL=${Math.round(v.dcl)} FCP=${Math.round(v.fcp)} (${v.href})`);
    for (const q of v.requests) {
      const src = q.src === "disk" ? "디스크" : q.durMs <= 2 && !q.size ? "메모리" : q.status === 304 ? "304" : "네트워크";
      console.log(`${q.startMs}\t${q.durMs}\t${src}\t${q.status}\t${q.size}\t${q.type}\t${q.url.slice(0, 55)}`);
    }
  }
}
