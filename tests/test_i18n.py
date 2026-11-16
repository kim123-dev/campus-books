"""화면 문구 번역(static/i18n/*.json, js/i18n.js, js/lang-boot.js) 규칙 검사.

사전은 브라우저가 읽는 정적 파일이라, 키가 빠지거나 {변수} 이름이 틀려도 서버 테스트로는 드러나지 않는다.
그래서 파일 내용을 직접 읽어 세 언어가 서로 맞는지, 화면 코드가 쓰는 키가 모두 있는지 확인한다.
"""

import json
import re
from pathlib import Path

import pytest

from app.main import STATIC_DIR

I18N_DIR = STATIC_DIR / "i18n"
LANGS = ["ko", "en", "zh-CN"]
JS_DIR = STATIC_DIR / "js"
HTML_FILES = sorted(STATIC_DIR.glob("*.html"))

PLACEHOLDER = re.compile(r"\{(\w+)\}")
REF = re.compile(r"\{@([\w.]+)\}")
PLURAL_FORMS = {"zero", "one", "two", "few", "many", "other"}


def load(lang: str) -> dict:
    return json.loads((I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def texts(value) -> list[str]:
    """문자열이면 그 하나, 복수형 항목이면 모든 형태의 문장."""
    return [value] if isinstance(value, str) else list(value.values())


def resolve(messages: dict, key: str) -> str:
    """i18n.js처럼 {@키}를 풀어 한국어 문장을 만든다. (복수형이 아닌 항목만)"""
    value = messages[key]
    assert isinstance(value, str), key
    for _ in range(6):
        value = REF.sub(lambda m: messages[m.group(1)], value)
    return value


DICTS = {lang: load(lang) for lang in LANGS}


# ---------- 세 언어 사전이 서로 맞는지 ----------


@pytest.mark.parametrize("lang", LANGS[1:])
def test_dictionaries_have_same_keys(lang: str) -> None:
    ko, other = set(DICTS["ko"]), set(DICTS[lang])
    assert ko - other == set(), f"{lang}.json에 없는 키"
    assert other - ko == set(), f"ko.json에 없는 키"


@pytest.mark.parametrize("lang", LANGS[1:])
def test_placeholders_match_korean(lang: str) -> None:
    # 변수 이름이 다르면 화면에 {count} 같은 글자가 그대로 보인다.
    for key, value in DICTS["ko"].items():
        expected = {name for text in texts(value) for name in PLACEHOLDER.findall(text)}
        for text in texts(DICTS[lang][key]):
            assert set(PLACEHOLDER.findall(text)) == expected, f"{lang}: {key}"


@pytest.mark.parametrize("lang", LANGS)
def test_plural_entries_are_well_formed(lang: str) -> None:
    for key, value in DICTS[lang].items():
        assert isinstance(value, (str, dict)), key
        if isinstance(value, dict):
            # 복수형은 Intl.PluralRules가 고르는 형태 이름만 쓰고, 기본값 other와 고를 기준 {count}가 있어야 한다.
            assert set(value) <= PLURAL_FORMS and "other" in value, key
            assert all("{count}" in text for text in value.values()), key


@pytest.mark.parametrize("lang", LANGS)
def test_references_point_to_existing_text(lang: str) -> None:
    messages = DICTS[lang]
    for key, value in messages.items():
        for text in texts(value):
            for ref in REF.findall(text):
                assert isinstance(messages.get(ref), str), f"{lang}: {key}의 {{@{ref}}}"
    # 순환 참조가 없어 끝까지 풀린다.
    for key, value in messages.items():
        if isinstance(value, str):
            assert "{@" not in resolve(messages, key), f"{lang}: {key}"


def test_no_empty_or_untranslated_korean_text() -> None:
    hangul = re.compile(r"[가-힣]")
    for lang in LANGS:
        for key, value in DICTS[lang].items():
            for text in texts(value):
                assert text.strip(), f"{lang}: {key}가 비어 있음"
                # 가격 단위 "원"은 모든 언어에서 그대로 쓰기로 했다. 그 밖의 한글이 남았으면 번역이 빠진 것이다.
                if lang != "ko":
                    assert not hangul.search(text.replace("원", "")), f"{lang}: {key}에 한국어가 남음"


# ---------- 한국어 사전이 예전 화면 문구와 같은지 ----------

# 1단계에서 코드에서 사전으로 옮긴 문구. 옮기기 전 코드에 있던 그대로다(템플릿의 ${x}는 {x}로).
# 한국어 화면은 번역 기능을 넣기 전과 글자 하나 다르지 않아야 한다.
ORIGINAL_KOREAN = {
    # ui.js
    "enum.status.ON_SALE": "판매 중",
    "enum.status.RESERVED": "예약 중",
    "enum.status.SOLD": "판매 완료",
    "enum.condition.GOOD": "상",
    "enum.condition.FAIR": "중",
    "enum.condition.POOR": "하",
    "term.free": "무료 나눔",
    "format.price": "{price}원",
    "card.condition": "책 상태 {condition}",
    "common.prev": "이전",
    "common.next": "다음",
    "format.page": "{page} / {total} 페이지",
    # auth.js
    "nav.main_aria": "주요 메뉴",
    "notice.reset_by_server": "서버 관리 명령으로",
    "notice.reset_by_question": "본인 확인 질문으로",
    "notice.reset": "비밀번호가 재설정됐어요. ({date}, {how}) 직접 하지 않았다면 바로 비밀번호와 본인 확인 질문을 바꿔 주세요.",
    "common.ok": "확인",
    "term.login": "로그인",
    "term.signup": "회원가입",
    "term.logout": "로그아웃",
    "term.sell": "글쓰기",
    "term.messages": "쪽지",
    "term.me": "내 정보",
    "nav.me_aria": "내 정보, {nickname}님",
    "term.admin": "관리",
    "term.book_alerts": "찾는 교재 알림",
    "term.home": "홈",
    "nav.tab_aria": "하단 메뉴",
    "notice.suspended": "{date}까지 이용이 정지된 상태입니다. 글쓰기·수정·쪽지·찜·신고를 할 수 없어요.",
    "nav.alerts_unread_aria": "찾는 교재 알림, 새 알림 {count}개",
    "nav.messages_unread_aria": "쪽지, 안 읽은 메시지 {count}개",
    # api.js
    "err.network": "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
    "err.generic": "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
    "val.invalid": "입력값을 확인해 주세요.",
    "val.required": "필수 항목입니다.",
    "val.min": "{min} 이상이어야 합니다.",
    "val.max": "{max} 이하여야 합니다.",
    "val.integer": "정수로 입력해 주세요.",
    "val.empty": "내용을 입력해 주세요.",
    "val.min_length": "{count}자 이상 입력해 주세요.",
    "val.max_length": "{count}자 이하로 입력해 주세요.",
    "val.enum": "선택할 수 없는 값입니다.",
    "val.email": "올바른 이메일 형식이 아닙니다.",
    # ---- 2단계 (로그인 전 화면). HTML 문구는 아래 test_html_i18n_marks_match_korean_dictionary가 확인한다.
    # login.js
    "login.joined": "가입이 완료되었습니다. 로그인해 주세요.",
    "login.reset_done": "비밀번호를 바꿨습니다. 새 비밀번호로 로그인해 주세요.",
    "login.submitting": "로그인 중…",
    # signup.js
    "signup.password_mismatch": "비밀번호가 일치하지 않습니다.",
    "signup.submitting": "가입 중…",
    "signup.submit": "가입하기",
    # reset-password.js
    "reset.answer_required": "답을 입력해 주세요.",
    "reset.verifying": "확인 중…",
    "reset.verify": "인증 확인",
    "reset.password_mismatch": "새 비밀번호가 일치하지 않습니다.",
    "reset.submitting": "바꾸는 중…",
    "reset.submit": "비밀번호 바꾸기",
    # index.js
    "term.filter": "필터",
    "home.filter_aria": "필터, {count}개 적용됨",
    "common.loading": "불러오는 중…",
    "home.empty_search": "조건에 맞는 글이 없습니다.",
    "home.empty": "아직 등록된 글이 없습니다.",
    "home.page_empty": "이 페이지에는 글이 없습니다. (전체 {total}개, {pages}페이지까지)",
    "home.total": "총 {count}개",
    # pwa.js ({share}는 공유 아이콘 자리. 예전에는 "Safari 아래쪽의 " + 아이콘 + "공유 → …")
    "pwa.close_aria": "홈 화면 추가 안내 닫기",
    "pwa.aria": "홈 화면에 추가",
    "pwa.title": "홈 화면에 추가하면 앱처럼 쓸 수 있어요",
    "pwa.text": "Safari 아래쪽의 {share}공유 → '홈 화면에 추가'를 누르세요.",
    # security-question.js (질문 9개는 test_static이 서버와 비교한다)
    "sq.placeholder": "질문을 골라 주세요",
    "sq.custom": "직접 만들기",
    "sq.custom_label": "내가 만든 질문",
    "sq.custom_hint": "5~60자. 질문에 답이나 답의 힌트를 넣지 마세요. 친구·가족이 금방 맞힐 수 있는 질문도 피해 주세요.",
    "term.security_question": "본인 확인 질문",
    "sq.hint": "비밀번호를 잊었을 때 이 질문의 답으로 재설정해요.",
    "field.answer": "답",
    "sq.answer_hint": "남이 쉽게 알 수 없는 답으로 정해 주세요. 띄어쓰기와 대소문자는 구분하지 않아요. (공백 빼고 2~20자)",
    "sq.choose": "질문을 골라 주세요.",
    "sq.custom_too_short": "질문을 5자 이상 적어 주세요.",
    "sq.answer_too_short": "답은 공백을 빼고 2자 이상이어야 합니다.",
    "sq.answer_too_long": "답은 공백을 빼고 20자 이하여야 합니다.",
}


@pytest.mark.parametrize("key", sorted(ORIGINAL_KOREAN))
def test_korean_dictionary_matches_previous_text(key: str) -> None:
    assert resolve(DICTS["ko"], key) == ORIGINAL_KOREAN[key]


def test_wrong_password_text_matches_server_message() -> None:
    # 내 정보 화면이 비밀번호 칸 아래에 서버 문장 대신 이 문구를 보여준다. 한국어 화면은 예전과 같아야 한다.
    from app.core.exceptions import WrongPasswordError

    assert DICTS["ko"]["err.wrong_password"] == WrongPasswordError.message


# ---------- 화면 코드가 쓰는 키가 사전에 있는지 ----------


def js_sources() -> dict[str, str]:
    return {path.relative_to(STATIC_DIR).as_posix(): path.read_text(encoding="utf-8") for path in sorted(JS_DIR.rglob("*.js"))}


def test_keys_used_in_js_exist() -> None:
    used = set()
    for name, source in js_sources().items():
        for key in re.findall(r'\bt\(\s*"([^"]+)"', source) + re.findall(r'labelKey: "([^"]+)"', source):
            used.add((name, key))
    assert used, "t(\"...\") 호출을 찾지 못했습니다."
    missing = sorted(f"{name}: {key}" for name, key in used if key not in DICTS["ko"])
    assert not missing, "사전에 없는 키:\n" + "\n".join(missing)


def test_status_messages_exist_for_listed_codes() -> None:
    # api.js는 `err.status.${status}`로 키를 만들어 쓴다. 목록의 상태 코드마다 문장이 있어야 한다.
    source = (JS_DIR / "api.js").read_text(encoding="utf-8")
    codes = re.search(r"const STATUS_MESSAGE_CODES = \[([\d,\s]+)\];", source)
    assert codes
    for code in re.findall(r"\d+", codes.group(1)):
        assert f"err.status.{code}" in DICTS["ko"]


@pytest.mark.parametrize("html", HTML_FILES, ids=lambda path: path.name)
def test_html_i18n_marks_match_korean_dictionary(html: Path) -> None:
    # HTML 원문(한국어)과 한국어 사전이 같아야, 한국어 화면에서 사전을 적용하지 않아도 같은 글자가 보인다.
    text = html.read_text(encoding="utf-8")
    for key, content in re.findall(r'data-i18n="([^"]+)"[^>]*>([^<]*)<', text):
        assert key in DICTS["ko"], f"{html.name}: {key}"
        assert content.strip() == resolve(DICTS["ko"], key), f"{html.name}: {key}"
    for spec in re.findall(r'data-i18n-attr="([^"]+)"', text):
        for pair in spec.split(";"):
            assert pair.split(":")[1].strip() in DICTS["ko"], f"{html.name}: {pair}"
    # 문서 제목: <meta name="i18n-title">의 키가 한국어 사전에서 <title> 원문과 같아야 한다.
    title_key = re.search(r'<meta name="i18n-title" content="([^"]+)" />', text)
    if title_key:
        title = re.search(r"<title>([^<]*)</title>", text).group(1)
        assert resolve(DICTS["ko"], title_key.group(1)) == title, html.name


# ---------- 언어 정하기 (lang-boot.js) ----------

LANG_BOOT = '<script src="/static/js/lang-boot.js"></script>'


@pytest.mark.parametrize("html", HTML_FILES, ids=lambda path: path.name)
def test_every_page_decides_language_before_render(html: Path) -> None:
    head = html.read_text(encoding="utf-8").split("</head>")[0]
    assert LANG_BOOT in head
    # CSS와 모듈보다 먼저 실행돼야 <html lang>과 깜빡임 방지 표시가 처음부터 적용된다.
    assert head.index(LANG_BOOT) < head.index('<script type="module"')
    if '<link rel="stylesheet"' in head:
        assert head.index(LANG_BOOT) < head.index('<link rel="stylesheet"')


def test_lang_boot_and_i18n_share_storage_key() -> None:
    boot = (JS_DIR / "lang-boot.js").read_text(encoding="utf-8")
    i18n = (JS_DIR / "i18n.js").read_text(encoding="utf-8")
    key = re.search(r'var STORAGE_KEY = "([^"]+)";', boot).group(1)
    assert f'const STORAGE_KEY = "{key}";' in i18n


def test_supported_languages_match_dictionaries() -> None:
    i18n = (JS_DIR / "i18n.js").read_text(encoding="utf-8")
    codes = re.findall(r'\{ code: "([^"]+)", name: "[^"]+" \}', i18n)
    assert codes == LANGS
    assert sorted(path.stem for path in I18N_DIR.glob("*.json")) == sorted(LANGS)


def test_language_switch_is_hidden_until_all_pages_are_translated() -> None:
    # 5단계(모든 화면 번역)가 끝나기 전에는 사용자에게 언어 선택을 보여주지 않고, 브라우저 언어도 따르지 않는다.
    # 다 끝나면 이 값을 true로 바꾸고 이 테스트도 함께 고친다.
    boot = (JS_DIR / "lang-boot.js").read_text(encoding="utf-8")
    assert "var LANG_SWITCH_ENABLED = false;" in boot


def test_storage_access_is_guarded() -> None:
    # 사생활 보호 모드 등에서 저장소가 막혀도 동작하도록 localStorage 사용은 모두 try 안에 있다.
    for name in ("lang-boot.js", "i18n.js"):
        source = (JS_DIR / name).read_text(encoding="utf-8")
        for match in re.finditer(r"localStorage\.", source):
            before = source[: match.start()]
            # 가장 가까운 try가 그 뒤의 catch보다 앞에 있어야 한다(= try 블록 안).
            assert before.rfind("try {") > before.rfind("catch"), f"{name}: try 밖의 localStorage"
