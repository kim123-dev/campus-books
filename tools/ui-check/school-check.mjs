// 학교 선택 확인: 내 정보의 학교 행(목록에서 고르기, 7일 제한 안내), 글쓰기 기본값·수정·해제, 상세 표시,
// 홈 필터(주소 유지·활성 필터 수·목록 행의 학교 이름), 영어·중국어 375px 넘침.
// 사용: WIDTH=375 tools/ui-check/run.sh school-check
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { api, readSeed, startBrowser } from "./lib.mjs";

const OUT = process.argv[2];
const W = Number(process.env.WIDTH ?? 375);
const seed = readSeed(OUT);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  [${W}] ${name}${detail ? `  (${detail})` : ""}`);

const b = await startBrowser(OUT, { width: W });
const { evaluate, waitUntil, goto, screenshot } = b;
const SCHOOL = "울산과학대학교";
const noHScroll = () => evaluate(`document.documentElement.scrollWidth <= ${W}`);
const settled = "!document.documentElement.hasAttribute('data-i18n-pending')";

try {
  const schools = (await api("GET", "/schools")).body.items;
  check("API: 기본 학교(울산과학대학교)가 시드됨", schools.length === 1 && schools[0].name === SCHOOL, JSON.stringify(schools));
  const schoolId = schools[0].id;
  await goto("/static/index.html");
  await evaluate(`localStorage.setItem("campus-books.token", ${JSON.stringify(seed.buyer_token)})`);

  // ---------- 내 정보: 학교 행 ----------
  await goto("/static/me.html", "!document.getElementById('account').hidden && document.getElementById('school-current').textContent !== ''");
  check("내 정보: 학교 행, 처음엔 '선택 안 함'", (await evaluate("document.getElementById('school-toggle').textContent.replace(/\\s+/g, ' ').trim()")) === "학교 선택 안 함");
  await evaluate("document.getElementById('school-toggle').click()");
  const panel = await evaluate(`(() => {
    const items = [...document.querySelectorAll('.school-options__item')];
    return { open: !document.getElementById('school-panel').hidden, expanded: document.getElementById('school-toggle').getAttribute('aria-expanded'),
      labels: items.map((b) => b.textContent), pressed: items.map((b) => b.getAttribute('aria-pressed')).join(','), tall: items.every((b) => b.getBoundingClientRect().height >= 44) };
  })()`);
  check("내 정보: 누르면 학교 목록(선택 안 함 + 학교), 항목 44px", panel.open && panel.expanded === "true" && panel.labels.join("|") === `선택 안 함|${SCHOOL}` && panel.pressed === "true,false" && panel.tall, JSON.stringify(panel));
  await screenshot(`school-me-open-${W}.png`);
  await evaluate("document.querySelectorAll('.school-options__item')[1].click()");
  await waitUntil(`document.getElementById('school-current').textContent === ${JSON.stringify(SCHOOL)}`);
  const after = await evaluate(`({ notice: document.getElementById('account-notice').textContent, panelHidden: document.getElementById('school-panel').hidden,
    hint: document.getElementById('school-hint').textContent, locked: [...document.querySelectorAll('.school-options__item')].every((b) => b.disabled) })`);
  check("내 정보: 고르면 저장, 행에 학교 이름, 안내", after.notice === "학교를 저장했어요." && after.panelHidden, JSON.stringify(after));
  check("내 정보: 7일 제한 중 안내 + 목록 잠김", /부터 다시 바꿀 수 있어요\.$/.test(after.hint) && after.locked, after.hint);
  await evaluate("document.getElementById('school-toggle').click()");
  await screenshot(`school-me-locked-${W}.png`);
  check("내 정보: 가로 스크롤 없음", await noHScroll());

  // ---------- 글쓰기: 내 학교가 기본값 ----------
  await goto("/static/post-form.html", "!document.getElementById('form-card').hidden");
  const form = await evaluate(`({ value: document.getElementById('school_id').value, label: document.querySelector('label[for=school_id]').textContent,
    options: [...document.getElementById('school_id').options].map((o) => o.textContent).join('|') })`);
  check("글쓰기: '학교 (선택)' 칸, 내 학교가 미리 선택됨", form.value === String(schoolId) && form.label === "학교 (선택)" && form.options === `선택 안 함|${SCHOOL}`, JSON.stringify(form));
  await evaluate(`(() => { const f = document.getElementById('post-form'); f.title.value = '학교 확인용 글'; f.book_title.value = '학교 교재'; f.condition.value = 'GOOD'; f.price.value = '3000'; })()`);
  await evaluate("document.getElementById('school_id').scrollIntoView({ block: 'center' })");
  await screenshot(`school-form-${W}.png`);
  check("글쓰기: 가로 스크롤 없음", await noHScroll());
  await evaluate("document.getElementById('post-form').requestSubmit()");
  await waitUntil("location.pathname === '/static/post.html' && !document.getElementById('post-detail').hidden", 10000);
  const postId = Number(await evaluate("new URLSearchParams(location.search).get('id')"));
  const infoOf = () => evaluate("[...document.querySelectorAll('.post-detail__info dt')].map((dt) => dt.textContent + '=' + dt.nextElementSibling.textContent)");
  check("상세: 학교 표시", (await infoOf()).includes(`학교=${SCHOOL}`), (await infoOf()).join(" / "));

  // 수정: 학교가 선택된 채로 열리고, "선택 안 함"으로 저장하면 해제된다.
  await goto(`/static/post-form.html?id=${postId}`, "!document.getElementById('form-card').hidden && document.getElementById('title').value !== ''");
  check("수정: 글의 학교가 선택된 채로 열림", (await evaluate("document.getElementById('school_id').value")) === String(schoolId));
  await evaluate("document.getElementById('school_id').value = ''; document.getElementById('post-form').requestSubmit()");
  await waitUntil("location.pathname === '/static/post.html' && !document.getElementById('post-detail').hidden", 10000);
  check("수정: '선택 안 함'으로 저장하면 학교 해제", !(await infoOf()).some((s) => s.startsWith("학교=")) && (await api("GET", `/posts/${postId}`)).body.school === null);
  await api("PATCH", `/posts/${postId}`, seed.buyer_token, { school_id: schoolId });

  // ---------- 홈: 학교 필터 ----------
  await goto("/static/index.html", "document.getElementById('school_id').options.length > 1 && !document.getElementById('result-summary').textContent.includes('불러오는 중')");
  await evaluate("document.getElementById('filter-toggle').click()");
  await evaluate(`document.getElementById('school_id').value = '${schoolId}'`);
  await screenshot(`school-home-filter-${W}.png`);
  await evaluate("document.getElementById('filter-form').requestSubmit()");
  await waitUntil(`new URLSearchParams(location.search).get('school_id') === '${schoolId}' && !document.getElementById('result-summary').textContent.includes('불러오는 중') && document.querySelectorAll('.post-card').length > 0`);
  const home = await evaluate(`({ count: document.querySelector('.filter-form__count').textContent, countHidden: document.querySelector('.filter-form__count').hidden,
    cards: document.querySelectorAll('.post-card').length, schools: [...document.querySelectorAll('.post-card__school')].map((n) => n.textContent),
    value: document.getElementById('school_id').value })`);
  const expected = (await api("GET", `/posts?school_id=${schoolId}`)).body.total;
  check("홈: 학교를 고르면 그 학교 글만, 주소에 school_id, 활성 필터 1", home.cards === expected && home.schools.length === home.cards && home.schools.every((s) => s === SCHOOL) && home.count === "1" && !home.countHidden, JSON.stringify(home));
  const smallGrey = await evaluate("(() => { const s = getComputedStyle(document.querySelector('.post-card__school')); return s.fontSize + ' ' + s.color; })()");
  check("홈: 목록 행의 학교 이름은 작은 회색 글씨", smallGrey.startsWith("13px"), smallGrey);
  await b.goto(`/static/index.html?school_id=${schoolId}`, `document.getElementById('school_id').value === '${schoolId}' && document.querySelectorAll('.post-card').length > 0`);
  check("홈: 새로 고쳐도 학교 선택 유지", (await evaluate("document.querySelectorAll('.post-card').length")) === expected);
  await screenshot(`school-home-list-${W}.png`);
  const all = (await api("GET", "/posts?size=50")).body.total;
  check("홈: 학교 없는 글은 '전체'에서만", all > expected, `전체 ${all}, 학교 ${expected}`);
  check("홈: 가로 스크롤 없음", await noHScroll());

  // ---------- 영어·중국어: 번역·넘침 ----------
  for (const lang of ["en", "zh-CN"]) {
    const en = lang === "en";
    await goto(`/static/me.html?lang=${lang}`, `${settled} && document.getElementById('school-current').textContent !== ''`);
    await evaluate("document.getElementById('school-toggle').click()");
    const me = await evaluate(`({ title: document.getElementById('school-title').textContent, none: document.querySelector('.school-options__item').textContent, wide: document.documentElement.scrollWidth > ${W} })`);
    await goto(`/static/post-form.html?lang=${lang}`, `${settled} && !document.getElementById('form-card').hidden`);
    const formLabel = await evaluate(`({ label: document.querySelector('label[for=school_id]').textContent, wide: document.documentElement.scrollWidth > ${W} })`);
    await goto(`/static/index.html?lang=${lang}&school_id=${schoolId}`, `${settled} && document.querySelectorAll('.post-card').length > 0`);
    await evaluate("document.getElementById('filter-toggle').click()");
    const homeLabel = await evaluate(`({ label: document.querySelector('label[for=school_id]').textContent, all: document.querySelector('#school_id option').textContent, wide: document.documentElement.scrollWidth > ${W} })`);
    check(
      `${lang}: 학교 행·글쓰기·홈 필터 번역, 375px 넘침 없음`,
      me.title === (en ? "School" : "学校") && me.none === (en ? "Not set" : "未选择") && formLabel.label === (en ? "School (optional)" : "学校（选填）") &&
        homeLabel.label === (en ? "School" : "学校") && homeLabel.all === (en ? "All" : "全部") && !me.wide && !formLabel.wide && !homeLabel.wide,
      JSON.stringify({ me, formLabel, homeLabel }),
    );
    await screenshot(`school-home-filter-${W}-${lang}.png`);
  }
  check("JS 예외 없음", b.exceptions.length === 0, b.exceptions.join(" / "));
} catch (error) {
  results.push(`ERROR  ${error.stack}`);
} finally {
  writeFileSync(join(OUT, "school-check.txt"), results.join("\n"));
  console.log(results.join("\n"));
  b.close();
}
