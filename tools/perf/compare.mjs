// 두 측정 결과(results.json) 비교: 화면·상황별 본문 표시 시간 중앙값(ms)과 변화량.
// 사용: node tools/perf/compare.mjs <전 results.json> <후 results.json>
// - 측정 결과에 화면별 서비스 워커 여부(controlled)가 있으면, 서비스 워커가 맡았어야 하는 측정 중 맡지 않은 것은 빼고 센다.
//   (새 프로필의 첫 화면은 아직 서비스 워커가 없으므로 그대로 쓴다)
// - 뺀 측정은 표 아래에 화면·상황별로 몇 번인지 따로 보여준다.
import { readFileSync } from "node:fs";

const [beforePath, afterPath] = process.argv.slice(2);
const load = (path) => JSON.parse(readFileSync(path, "utf8"));
const before = load(beforePath);
const after = load(afterPath);
const KINDS = ["first", "second", "cold"];
const KIND_LABELS = { first: "첫 방문", second: "재방문(캐시 유효)", cold: "재방문(브라우저 재시작)" };
const PAGES = ["list", "detail", "inbox", "profile"];
const PAGE_LABELS = { list: "목록", detail: "상세", inbox: "쪽지함", profile: "프로필" };

const median = (xs) => {
  const s = xs.filter((x) => typeof x === "number").sort((a, b) => a - b);
  if (!s.length) return null;
  const mid = Math.floor(s.length / 2);
  return Math.round(s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2);
};

// 서비스 워커가 맡았어야 하는 측정인가: 첫 방문 흐름의 첫 화면(목록)만 예외
const expectsSw = (kind, page) => !(kind === "first" && page === "list");

function collect(data) {
  const values = {};
  const skipped = {};
  for (const run of data.results) {
    for (const kind of KINDS) {
      for (const visit of run[kind] ?? []) {
        const key = `${kind}/${visit.name}`;
        if ("controlled" in visit && expectsSw(kind, visit.name) && visit.controlled !== true) {
          skipped[key] = (skipped[key] ?? 0) + 1;
          continue;
        }
        (values[key] ??= []).push(visit.ready);
      }
    }
  }
  return { values, skipped, total: data.results.length };
}

const b = collect(before);
const a = collect(after);
console.log("| 상황 | 화면 | 전 (ms) | 후 (ms) | 변화 | 후 측정 수 |");
console.log("|---|---|---|---|---|---|");
for (const kind of KINDS) {
  for (const page of PAGES) {
    const key = `${kind}/${page}`;
    const x = median(b.values[key] ?? []);
    const y = median(a.values[key] ?? []);
    const diff = x !== null && y !== null ? `${y - x > 0 ? "+" : ""}${y - x} (${Math.round(((y - x) / x) * 100)}%)` : "-";
    console.log(`| ${KIND_LABELS[kind]} | ${PAGE_LABELS[page]} | ${x ?? "-"} | ${y ?? "-"} | ${diff} | ${(a.values[key] ?? []).length}/${a.total} |`);
  }
}
for (const [label, side] of [["전", b], ["후", a]]) {
  const entries = Object.entries(side.skipped);
  const count = entries.reduce((sum, [, n]) => sum + n, 0);
  console.log(`\n${label}: 서비스 워커가 맡지 않아 뺀 측정 ${count}번${entries.length ? ` (${entries.map(([k, n]) => `${k} ${n}번`).join(", ")})` : ""}`);
}
