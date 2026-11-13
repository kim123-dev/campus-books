# 헤드리스 UI 확인

헤드리스 Chrome을 DevTools 프로토콜로 직접 움직여 화면을 확인하는 스크립트입니다. npm 패키지는 따로 설치하지 않아도 됩니다.
실행할 때마다 임시 DB와 확인용 서버(기본 포트 8001)를 새로 띄우기 때문에 `dev.db`와 `uploads/`는 건드리지 않습니다.

## 준비

- Node.js 22 이상 (내장 `fetch`·`WebSocket` 사용)
- Google Chrome
- 저장소 루트에 `venv`와 `requirements.txt` 패키지 설치
- Windows에서는 Git Bash로 실행

## 실행

저장소 루트에서 실행합니다.

```bash
# 확인 하나 (기본 폭 375px)
tools/ui-check/run.sh mobile-check

# 폭 바꾸기
WIDTH=390 tools/ui-check/run.sh mobile-check

# 목록 화면은 모바일과 PC 둘 다
tools/ui-check/run.sh home-check
WIDTH=1280 tools/ui-check/run.sh home-check

# PC 화면 비교: 변경 전 기록 → 변경 후 기록 → 비교
tools/ui-check/run.sh pc-snapshot before
tools/ui-check/run.sh pc-snapshot after
node tools/ui-check/compare.mjs tools/ui-check/out before after
```

| 스크립트 | 확인 내용 |
|---|---|
| `mobile-check` | 모바일 탭 바, 목록·카드(로그인 상태 첫 화면 4장 이상), 터치 영역 44px, 글자 16px, 상세 갤러리, 대화 키보드 |
| `home-check` | 목록 화면(375·1280px): 비로그인 배너(문구·버튼·그림 크기)와 로그인 띠(`<html data-signed-in>`, 높이), 배너·페이지 전체 밀림(CLS), 한 줄 검색과 필터 펼치기, 글이 없을 때 "첫 교재 올리기"와 로그인 거쳐 글쓰기로 |
| `ui-check` | 쪽지(대화) 화면 |
| `photo-check` | 사진 업로드 (고르는 즉시 임시 사진으로 올리기, 개수 제한, 형식 오류, 올리기 실패·다시 시도, 진행률, 올리는 중에 저장, 휴대폰 사진) |
| `wish-check` | 찜하기 |
| `safety-check` | 신고·차단 |
| `admin-check` | 신고 관리, 이용 정지, `make-admin` CLI |
| `trade-check` | 판매 완료 때 구매자 고르기(후보·선택 안 함·고르지 않으면 안내), 구매자 줄, 구매자 변경과 선택 안 함으로 되돌리기 |
| `review-check` | 쪽지 화면의 후기 남기기, 프로필(매너 점수·글·후기), 후기 신고, 관리자 후기 숨김 |
| `pwa-check` | 홈 화면 설치 안내, 서비스 워커 캐시 |
| `pc-snapshot` | PC(1280px) 화면의 요소 위치·스타일 기록 (`compare.mjs`로 비교) |

결과는 `tools/ui-check/out/`에 쌓입니다(`<이름>-<폭>.txt`, 스크린샷, 서버 로그). 이 폴더는 커밋하지 않습니다.

## 환경 변수 (모두 선택)

| 이름 | 기본값 | 설명 |
|---|---|---|
| `WIDTH` | `375` | 화면 폭 (768 미만이면 모바일로, 이상이면 PC로 띄움: `home-check`) |
| `UI_CHECK_OUT` | `tools/ui-check/out` | 결과·임시 DB 폴더 |
| `UI_CHECK_PORT` | `8001` | 확인용 서버 포트 |
| `CHROME_PATH` | OS별 기본 설치 경로 | Chrome 실행 파일 |
| `CDP_PORT` | `9333` | Chrome 원격 디버깅 포트 |
| `PYTHON` | `venv`의 python | 서버·시드에 쓸 파이썬 |

`SECRET_KEY`는 실행할 때마다 임의로 만들기 때문에 따로 설정할 필요가 없습니다. 테스트 계정은 `seed.py`가 매번 새로 만듭니다.
