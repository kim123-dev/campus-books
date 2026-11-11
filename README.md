# Campus Books

같은 학교 학생끼리 전공 교재를 사고파는 **중고 교재 거래 게시판(API + 웹 화면)**입니다.

회원가입과 JWT 로그인, 비밀번호 변경·회원 탈퇴, 판매글 작성·조회·수정·삭제, 판매 상태 관리, 교재 검색·필터, 교재 사진, 찜하기, 찾는 교재 알림, 구매자와 판매자의 1:1 쪽지, 신고·차단, 관리자 신고 처리를 제공합니다.
순수 HTML/CSS/JS로 만든 웹 화면 12개가 함께 들어 있어, 서버만 켜면 브라우저에서 바로 사용할 수 있습니다. 휴대폰 화면에 맞춘 모바일 레이아웃과, 홈 화면에 추가해 앱처럼 쓰는 PWA도 지원합니다.
포트폴리오 프로젝트로, 기능 수보다 **계층 분리, 입력 검증, 권한 처리, 테스트**를 꼼꼼하게 다루는 데 집중했습니다.

## 목차

1. [문제 정의](#문제-정의)
2. [주요 기능](#주요-기능)
3. [기술 스택](#기술-스택)
4. [프로젝트 구조](#프로젝트-구조)
5. [프론트엔드](#프론트엔드)
6. [데이터 모델](#데이터-모델)
7. [실행 방법](#실행-방법)
8. [배포 (Railway)](#배포-railway)
9. [API 목록](#api-목록)
10. [상태 전이 규칙](#상태-전이-규칙)
11. [설계 결정과 트레이드오프](#설계-결정과-트레이드오프)
12. [테스트](#테스트)
13. [향후 개선 계획](#향후-개선-계획)

---

## 문제 정의

### 제가 겪은 불편

수업을 듣다 보면 교재가 꼭 필요한 과목이 있습니다. 하지만 새 교재는 가격이 부담스러워 구매하기가 꺼려졌습니다.

그래서 중고 교재를 구해 보려고 했습니다.

- **선배에게 직접 문의**: 아는 선배가 많지 않아 구하기 어려웠습니다.
- **에브리타임 이용**: 중고 교재 거래가 중심인 서비스가 아니어서 원하는 교재를 찾기 어려웠습니다.

결국 비싼 새 교재를 샀고, 얼마 쓰지 못한 채 책장에 넣어 두게 되었습니다.
다시 팔고 싶어도 마땅한 거래 창구가 없어 판매 또한 쉽지 않았습니다.

즉 교재를 **구하는 입장과 파는 입장 모두**에서 불편을 겪었습니다.

### 기존 거래 방식의 문제

같은 수업을 다음 학기에 듣는 학생에게 넘기면 양쪽 모두 이득이지만, 이런 거래는 보통 단체 채팅방이나 커뮤니티 게시판에서 이루어집니다.
이런 곳에서는 다음과 같은 문제가 생기기 쉽습니다.

- **찾기 어렵다**: 글이 대화나 다른 게시글에 묻혀서 과목명이나 교재명으로 검색하기 어렵습니다.
- **상태를 알 수 없다**: 이미 팔렸거나 예약된 책인지 글만 보고는 알기 어렵습니다.
- **정보가 제각각이다**: 가격, 책 상태, 과목명 같은 정보가 글마다 다른 형식으로 적혀 있습니다.

### 목표

그래서 이 프로젝트는 다음을 목표로 합니다.

- 교재명, 과목명, 가격대, 판매 상태로 **검색과 필터**를 할 수 있게 한다.
- 판매 상태(판매 중 / 예약 중 / 판매 완료)를 **명확한 규칙**으로 관리한다.
- 판매글 정보를 **정해진 형식**(교재명, 과목명, 책 상태, 가격)으로 받는다.

## 주요 기능

| 기능 | 내용 |
|---|---|
| 회원 | 회원가입, 로그인(JWT 발급), 내 정보 조회 |
| 비밀번호 변경 | 현재 비밀번호 확인(틀리면 400) 후 가입과 같은 규칙으로 변경. 변경 전에 발급된 토큰은 모든 기기에서 무효가 되고, 지금 기기에는 새 토큰을 바로 발급 |
| 회원 탈퇴 | 비밀번호 재확인, 확인 창 두 번. 내 글·사진 파일·찜·차단은 삭제, 쪽지 대화방과 신고 기록은 남기고 상대 화면에는 "탈퇴한 사용자"로 표시. 관리자 계정은 탈퇴 불가(400) |
| 판매글 작성·조회 | 작성, 목록(최신순, 페이지네이션), 상세, 내 글 목록 |
| 판매글 관리 | 일부 필드 수정, 판매 상태 변경, 삭제 (모두 작성자만 가능) |
| 검색·필터 | 검색어(제목·교재명·과목명), 상태, 과목명, 가격대 |
| 교재 사진 | 글당 최대 3장(JPG·PNG·WebP, 장당 5MB). 서버가 WebP로 다시 인코딩해 위치 정보(GPS) 등 메타데이터를 지우고, 목록용 썸네일을 함께 만듭니다 |
| 연락 방법 | 판매글에 카카오 오픈채팅 링크(선택) 등록, 상세 화면에서 로그인한 사용자에게만 표시 |
| 찜하기 | 목록 카드·상세의 하트로 찜 추가·해제, 찜 목록(찜한 순서 최신순, 판매 완료 글은 배지와 함께 유지). 내 글은 찜 불가 |
| 찾는 교재 알림 | 키워드(교재명·과목명 부분 일치)와 최대 가격(선택)을 사용자당 10개까지 등록. 조건에 맞는 판매 중인 새 글(또는 수정으로 새로 맞게 된 글)이 올라오면 알림. 내 글·차단한 사용자의 글 제외, 같은 글은 한 번만. 헤더 종 아이콘의 안 읽은 수 배지와 알림 화면 |
| 1:1 쪽지 | 판매글 문의 시작, 쪽지함(최신 메시지순, 안 읽은 개수), 대화 화면(새 메시지 자동 확인, 이전 메시지 불러오기), 읽음 처리, 도배 방지 |
| 차단 | 상세·대화 화면에서 사용자 차단. 서로 쪽지를 보낼 수 없고(양방향), 차단한 사용자의 글은 내 목록에서 숨김. 차단 목록 화면에서 해제. 상대에게는 알리지 않음 |
| 신고 | 글·사용자 신고(사유 5가지, 기타는 설명 필수). 같은 대상 중복 신고 409, 1시간 5회 제한. 신고자는 상대에게 드러나지 않음 |
| 신고 처리 (관리자) | 관리자 전용 신고 관리 화면. 미처리 우선 목록, 기각·글 삭제·기간 정지(1~365일) 처리와 처리 기록(누가·언제·어떤 조치·메모). 같은 사용자의 미처리 신고 함께 처리. 관리자는 서버 CLI로만 지정 |
| 이용 정지 | 정지된 사용자는 로그인 403("11월 16일 14:00까지 이용이 정지되었습니다."), 이미 받은 토큰으로도 쓰기 요청 403. 읽기·차단은 허용. 기간이 지나면 자동 해제 |
| 웹 화면 (12개) | 목록·검색, 상세(상태 변경·삭제·문의·찜·신고·차단), 작성·수정, 로그인, 회원가입, 내 글(비밀번호 변경·회원 탈퇴), 찜 목록, 찾는 교재 알림, 차단 목록, 쪽지함, 대화, 신고 관리(관리자) |
| 모바일 화면 | 768px 미만에서 하단 탭 바, 한 줄 검색 + 접는 필터, 가로형 카드, 상세 사진 좌우 넘기기와 하단 고정 연락 바, 대화 화면 키보드 대응. PC 화면은 그대로 |
| 홈 화면 앱 (PWA) | 홈 화면에 추가하면 주소창 없이 앱처럼 열림. 서비스 워커가 정적 파일만 캐시. 아이폰 Safari에는 "공유 → 홈 화면에 추가" 안내를 한 번 보여줌 |
| 배포 | Railway에 배포됨. Dockerfile + Railway 설정 코드 `.railway/railway.ts`(헬스 체크·재시작·볼륨), PostgreSQL, 사진용 영구 볼륨. 운영 모드에서는 API 문서를 끄고 잘못된 설정이면 시작하지 않음 ([배포](#배포-railway)) |

## 기술 스택

| 분류 | 기술 | 선택 이유 |
|---|---|---|
| 언어 | Python 3.14.7 | 개발과 테스트에 사용한 버전 |
| 웹 프레임워크 | FastAPI | 타입 힌트 기반 입력 검증과 Swagger 문서 자동 생성 |
| ORM | SQLAlchemy 2.x | 타입이 지정된 `Mapped` 모델, SQLite와 PostgreSQL을 같은 코드로 지원 |
| 검증 | Pydantic v2 | 요청 형식 오류를 서비스 로직에 닿기 전에 422로 차단 |
| DB | SQLite (개발) / PostgreSQL (운영, Railway) | 개발 중에는 설치 없이 실행하고, 운영에서는 `DATABASE_URL`만 교체. 드라이버는 psycopg 3 |
| 이미지 | Pillow 12.3.0 | 실제 내용으로 형식 확인, 다시 인코딩(메타데이터 제거), 크기 조정 |
| 인증 | PyJWT, bcrypt | 서버에 세션을 저장하지 않는 토큰 인증, 솔트가 포함된 비밀번호 해시 |
| 프론트 | HTML/CSS/JS (ES 모듈, 빌드 도구 없음) | 별도 서버 없이 FastAPI가 정적 파일로 서빙하고, fetch로 API 호출 |
| 테스트 | pytest, httpx (TestClient), pytest-xdist | API를 실제 요청처럼 호출하는 통합 테스트, CPU 코어 수만큼 병렬 실행 |
| 배포 | Docker, Railway | 같은 이미지로 어디서나 실행, Git 연결만으로 빌드·배포와 관리형 PostgreSQL·볼륨 제공 |

글꼴: [Pretendard](https://github.com/orioncactus/pretendard) v1.3.9 (Regular·SemiBold·Bold), SIL Open Font License 1.1 ([`static/fonts/OFL-Pretendard.txt`](static/fonts/OFL-Pretendard.txt)). 공식 배포본의 서브셋 woff2를 수정 없이 `static/fonts/`에서 직접 제공합니다.

## 프로젝트 구조

```
campus-books/
├── app/
│   ├── main.py            # 앱 생성, 라우터 등록, 업무 예외 → HTTP 응답 변환
│   ├── cli.py             # 서버 관리 명령 (python -m app.cli make-admin 이메일)
│   ├── core/
│   │   ├── config.py      # .env 설정 (pydantic-settings)
│   │   ├── database.py    # 엔진, 세션, Base
│   │   ├── security.py    # 비밀번호 해시, JWT 발급·검증, 토큰의 비밀번호 지문
│   │   ├── deps.py        # 로그인 사용자 의존성 (CurrentUser, 정지 검사 ActiveUser, 관리자 AdminUser)
│   │   └── exceptions.py  # 업무 예외 (DomainError 계층)
│   ├── models/            # SQLAlchemy 모델 (User, Post, PostImage, Wishlist, Conversation, Message, UserBlock, Report, BookAlert, AlertNotification)
│   ├── schemas/           # Pydantic 요청·응답 스키마
│   ├── routers/           # auth, users, posts, images, wishlist, conversations, blocks, reports, admin, alerts
│   └── services/          # 업무 로직 (사진: image_service 검사·인코딩, image_storage 파일 쓰기·지우기,
│                          #   계정: account_service 비밀번호 변경·탈퇴, 알림: alert_service 조건·매칭·알림)
├── static/                # 프론트엔드 (아래 "프론트엔드" 참고)
│   ├── index.html, post.html, post-form.html, login.html, signup.html, my-posts.html,
│   │   wishlist.html, alerts.html, blocks.html, conversations.html, chat.html, admin.html
│   ├── css/style.css
│   ├── img/               # book-placeholder.svg(사진 없는 글의 기본 그림), 앱 아이콘(icon.svg, 192·512px, apple-touch-icon 180px)
│   ├── manifest.json      # 홈 화면 앱 정보 (이름, standalone, 테마색, 아이콘)
│   ├── sw.js              # 서비스 워커 (정적 파일 캐시, 버전 키)
│   └── js/
│       ├── api.js         # fetch 래퍼, 에러를 {status, message, fieldErrors}로 통일
│       ├── token.js       # 토큰 보관(localStorage)만 담당
│       ├── auth.js        # 공통 헤더, 로그인 후 돌아갈 주소, 로그아웃
│       ├── ui.js          # 카드·페이지 버튼·날짜 형식 등 공통 화면 부품
│       ├── wishlist-button.js  # 찜 하트 버튼 (목록·상세·찜 목록이 함께 씀)
│       ├── safety.js      # 신고 창(<dialog>)과 차단 확인·안내 문구 (상세·대화가 함께 씀)
│       ├── pwa.js         # 서비스 워커 등록, 아이폰 Safari 설치 안내 (모든 화면이 불러옴)
│       └── pages/         # 화면별 스크립트 (화면 1개 = 파일 1개)
├── tests/
├── tools/ui-check/       # 헤드리스 Chrome 화면 확인 스크립트 (run.sh, 화면별 *-check.mjs)
├── uploads/               # 올린 사진 (서버가 만듦, .gitignore 대상, static/ 밖)
├── Dockerfile             # 배포 이미지 (python:3.14-slim, uvicorn)
├── .railway/railway.ts    # Railway 설정 코드 (빌드·헬스 체크·재시작·볼륨)
├── package.json           # railway.ts용 Railway SDK (개발 의존성만)
├── .dockerignore          # .env·DB·사진·테스트를 이미지에서 제외
├── .env.example
└── requirements.txt
```

### 계층 구조

```mermaid
flowchart LR
    Client -->|HTTP| Router
    Router -->|검증된 스키마| Service
    Service --> Model
    Model --> DB[(SQLite / PostgreSQL)]
    Service -.->|DomainError| Handler[main.py 예외 핸들러]
    Handler -.->|400/401/403/404/409/413/422/429| Client
```

- **Router**: 요청을 받아 서비스에 넘기고 응답 형식(`response_model`)만 정합니다.
- **Service**: 업무 규칙(권한, 상태 전이, 검색 조건)을 처리합니다. HTTP 상태 코드를 알지 못하고, 실패하면 `PostNotFoundError` 같은 업무 예외를 던집니다.
- **main.py**: 업무 예외를 HTTP 응답으로 바꾸는 일을 한 곳에서 맡습니다. 그래서 서비스 코드가 HTTP와 분리되고, 에러 응답 형식이 `{"detail": "..."}`로 통일됩니다.

| 예외 (기반 클래스) | HTTP 상태 |
|---|---|
| `BadRequestError` | 400 |
| `AuthenticationError` | 401 (`WWW-Authenticate: Bearer` 헤더 포함) |
| `ForbiddenError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |
| `PayloadTooLargeError` | 413 (사진 5MB 초과) |
| `UnprocessableError` | 422 (지원하지 않는 사진 형식, 깨진 파일) |
| `TooManyRequestsError` | 429 (`Retry-After` 헤더 포함) |

## 프론트엔드

서버를 실행한 뒤 http://127.0.0.1:8000/ 에 접속하면 목록 화면(`/static/index.html`)으로 이동합니다. 별도 설치나 빌드는 필요 없습니다.

### 화면 구성

| 화면 | 주소 | 로그인 필요 | 주요 동작 |
|---|---|---|---|
| 목록 | `/static/index.html` | | 검색어·상태·과목명·가격대 검색, 페이지 이동, 카드마다 첫 사진 썸네일(없으면 기본 그림), 찜 하트(내 글 제외), 아이폰 Safari 설치 안내(처음 한 번) |
| 상세 | `/static/post.html?id={id}` | 연락·상태 변경·삭제·찜·신고·차단만 🔒 | 사진(작은 사진을 누르면 넘어감, 모바일은 손가락으로 넘기고 "2 / 3" 표시), 찜 하트(내 글 제외), 글 내용 확인, 쪽지 문의·오픈채팅 연락 버튼(로그인 시, 내 글·판매 완료 글 제외), 작성자에게만 상태 변경·수정·삭제 버튼 표시, 맨 아래 "이 글 신고"·"판매자 차단(해제)"(로그인 시, 내 글 제외) |
| 작성·수정 | `/static/post-form.html` | 🔒 | 판매글 작성, 기존 글 수정 (`?id=`가 있으면 수정), 사진 고르기·미리보기·빼기(최대 3장) |
| 로그인 | `/static/login.html` | | 로그인 후 원래 보던 화면으로 복귀 |
| 회원가입 | `/static/signup.html` | | 필드별 오류 메시지 표시 |
| 내 글 | `/static/my-posts.html` | 🔒 | 내 정보, 판매 완료를 포함한 내 글 목록, 찾는 교재 알림·차단 목록으로 가는 버튼, 비밀번호 변경(현재 비밀번호·새 비밀번호·확인) 폼, 회원 탈퇴(비밀번호 확인 + 확인 창 두 번, 관리자에게는 버튼 없음) |
| 찜 목록 | `/static/wishlist.html` | 🔒 | 찜한 글(찜한 순서 최신순, 판매 완료 포함), 목록과 같은 카드, 하트로 해제, 페이지 이동 |
| 찾는 교재 알림 | `/static/alerts.html` | 🔒 | 위: 찾는 교재 등록(키워드·최대 가격), 내 조건 목록("3/10"), 조건별 "지금 있는 글 검색"·삭제. 아래: 받은 알림 카드(키워드, 글 제목·교재명·현재 판매 상태·가격, 새 알림 강조), 페이지 이동. 목록을 그린 뒤 모두 읽음 처리 |
| 차단 목록 | `/static/blocks.html` | 🔒 | 내가 차단한 사용자(차단한 순서 최신순, 닉네임과 날짜만), 차단 해제, 페이지 이동 |
| 쪽지함 | `/static/conversations.html` | 🔒 | 내 대화방 목록(상대 닉네임, 글 제목 또는 "삭제된 글", 마지막 메시지, 안 읽은 개수), 페이지 이동 |
| 대화 | `/static/chat.html?id={id}` | 🔒 | 메시지 보기·보내기, 5초마다 새 메시지 확인, 위로 스크롤하면 이전 메시지, 429 시 남은 시간 표시, 개인정보 주의 안내, 상대 신고·차단(해제), 차단 관계·이용 정지·상대 탈퇴면 입력창 잠금과 이유 안내(탈퇴한 상대는 "탈퇴한 사용자"로 표시하고 신고·차단 버튼 없음), 모바일은 키보드가 올라와도 입력창이 보이게 화면 높이를 맞춤 |
| 신고 관리 | `/static/admin.html` | 🔒 관리자 | 미처리·처리됨·전체 탭, 신고 카드(사유, 설명, 신고 시점 글 사본, 신고자 → 대상, 대상의 다른 미처리 신고 수), 조치 선택(기각·글 삭제·기간 정지 1/3/7/30일)과 메모, 확인 창 후 처리, 처리된 카드는 흐리게 + 처리 기록 |

<!-- 스크린샷: 상세·내 글 화면은 docs/screenshots/ 에 이미지를 추가한 뒤 해당 줄의 주석을 푸세요 -->
![목록 화면](docs/screenshots/list.png)

<!-- ![상세 화면](docs/screenshots/detail.png) -->

![작성·수정 화면](docs/screenshots/form.png)

![로그인 화면](docs/screenshots/login.png)

![회원가입 화면](docs/screenshots/signup.png)

<!-- ![내 글 화면](docs/screenshots/my-posts.png) -->

### 모바일 화면 (768px 미만)

휴대폰에서 쓰기 편하도록 768px 미만에서만 바뀌는 규칙을 `style.css`의 한 구역(`@media (max-width: 767.98px)`)에 모았습니다. 768px 이상(PC)은 그대로입니다.

| 항목 | 내용 |
|---|---|
| 하단 탭 바 | 로그인 메뉴 대신 화면 아래 고정 탭 바(홈·찜·글쓰기·쪽지·내 정보). 쪽지 탭에 안 읽은 수 배지. "관리"·"로그아웃"은 내 정보(내 글 화면) 안으로. 로그인·회원가입 링크는 헤더에 남김. 찾는 교재 알림 종은 탭을 늘리지 않고 헤더 오른쪽에 둠 |
| 탭 바가 없는 화면 | 상세·대화·글쓰기·로그인·회원가입 (`<body data-tab-bar="off">`). 화면 아래를 연락 바·입력창·긴 폼이 쓰기 때문 |
| 목록 검색 | 한 줄 검색창 + 검색·"필터" 버튼. 필터를 누르면 상태·과목명·가격 칸이 펼쳐짐. 걸려 있는 조건 수를 버튼에 표시("필터 2"), 접힌 칸에 오류가 나면 자동으로 펼침 |
| 카드 | 사진(96px)을 왼쪽에 둔 가로형. 카드 높이 약 330px → 120~140px로 줄어 한 화면에 3~4장. 목록·찜 목록·내 글이 같은 카드 |
| 누르는 곳 | 버튼·링크·탭은 44px 이상 (문장 안의 링크는 예외) |
| 글자 | 본문 16px 이상. 상태 배지·날짜·글자 수·탭 이름만 12~14px |
| 입력칸 | 16px 이상. iOS Safari는 16px보다 작은 입력칸에 포커스하면 화면을 확대하기 때문 |
| iPhone 아래 막대 | `viewport-fit=cover` + `env(safe-area-inset-bottom)`만큼 탭 바·연락 바 아래를 띄움 |
| 상세: 사진 | 손가락으로 좌우로 넘기고(CSS `scroll-snap`), 사진 오른쪽 아래에 "2 / 3" 표시. 작은 사진 버튼도 남아 있어 누르면 그 사진으로 넘어가고, 넘긴 사진과 눌린 버튼(`aria-pressed`)이 항상 같음 |
| 상세: 하단 연락 바 | 찜 하트 · 가격 · "쪽지로 문의하기"를 화면 아래에 고정해, 긴 설명을 읽다가도 바로 문의. 비로그인은 "로그인하고 문의하기". 내 글·판매 완료 글·차단한 판매자의 글에는 없음. 오픈채팅 버튼은 375px 한 줄에 들어가지 않아 글 영역에 남김 |
| 대화: 키보드 | 키보드가 올라와도 입력창과 마지막 메시지가 보이게, 대화 화면 높이를 실제로 보이는 높이(`visualViewport.height`)에 맞춤. 안드로이드 Chrome용으로 `interactive-widget=resizes-content`도 둠. 입력 중에는 헤더·"← 쪽지함"·신고/차단 줄을 접고 개인정보 안내를 한 줄로 줄임. 보내기 버튼은 입력창 오른쪽 |
| 대화: 보내기 | 보내기 버튼이 `pointerdown`·`mousedown` 기본 동작을 막아 포커스를 가져가지 않음. 눌러도 키보드가 내려갔다 올라오지 않음 |

아이폰 Safari에서 찍은 화면 (긴 변 1200px로 줄임):

| 목록 | 필터 펼침 | 글쓰기 | 찜 목록 |
|---|---|---|---|
| <img src="docs/screenshots/mobile-list.png" alt="모바일 목록 화면: 한 줄 검색창, 가로형 카드, 하단 탭 바" width="200" /> | <img src="docs/screenshots/mobile-filter.png" alt="모바일 목록 화면에서 필터를 펼친 모습" width="200" /> | <img src="docs/screenshots/mobile-form.png" alt="모바일 글쓰기 화면" width="200" /> | <img src="docs/screenshots/mobile-wishlist.png" alt="모바일 찜 목록 화면" width="200" /> |

- 모바일 기준 폭은 CSS와 JS(`ui.js`의 `MOBILE_QUERY`)에 같은 값으로 두고, 테스트로 같은지 확인합니다. 화면별 스크립트는 폭을 직접 적지 않고 `MOBILE_QUERY`만 씁니다.
- 연락 바의 하트와 문의 버튼은 새로 만들지 않고 글 영역에서 **옮겨 옵니다.** 같은 버튼이 두 벌이면 찜 상태·에러 문구를 두 곳에서 맞춰야 하기 때문입니다. 폭이 768px을 넘나들면(`matchMedia`) 원래 자리로 되돌립니다. 그래서 이 버튼을 찾는 코드는 위치 대신 id(`#inquiry-button`)로 찾습니다.
- 사진은 PC와 모바일이 같은 구조(사진을 가로로 이어 붙인 줄)이고, PC만 그 줄의 스크롤을 막아 작은 사진 버튼으로 넘깁니다. 대신 PC도 사진을 처음에 모두 받습니다.
- 헤드리스 Chrome으로 375·390·430px(아이폰 폭)에서 화면마다 가로 스크롤, 누르는 곳 크기, 글자·입력칸 크기를 검사하고, PC(1280px) 화면의 모든 요소 위치·크기가 바뀌지 않았는지 변경 전후를 비교했습니다.
- 상세·대화는 375px에서 터치 이벤트로 사진 넘기기·하트·문의·보내기를 확인했고, 키보드는 보이는 높이를 400px로 줄여 흉내 냈습니다. 실제 iOS·안드로이드 키보드 동작은 기기마다 다를 수 있습니다.

### 홈 화면 앱 (PWA)

홈 화면에 추가하면 주소창 없이 앱처럼 열립니다(`display: standalone`). 서비스 워커는 **https 주소나 `localhost`에서만** 동작하므로, 휴대폰으로 확인할 때는 https 주소로 접속해야 합니다.

| 기기 | 설치 방법 |
|---|---|
| 아이폰·아이패드 (Safari) | 아래쪽 공유 버튼 → "홈 화면에 추가". 목록 화면에 처음 한 번 이 안내가 뜨고, 닫으면 다시 뜨지 않음(localStorage에 기록). 이미 홈 화면 앱으로 열었으면 표시하지 않음 |
| 안드로이드 (Chrome) | 주소창 메뉴(⋮) → "앱 설치" 또는 "홈 화면에 추가" |
| PC (Chrome·Edge) | 주소창 오른쪽의 설치 아이콘 |

- **앱 정보**: `static/manifest.json` (이름 "Campus Books", 시작 주소 `/static/index.html`, 테마색은 포인트 보라 `#5b3fd6`, 아이콘 192·512px). 아이콘은 기본 그림의 책 모양을 보라 바탕에 올린 `icon.svg`에서 만들었고, 안드로이드가 원·둥근 사각형으로 잘라도 책이 잘리지 않게 가운데 80% 안에 두었습니다.
- **아이폰**: iOS는 manifest 아이콘 대신 `apple-touch-icon`(180px)과 `apple-mobile-web-app-*` meta 태그를 씁니다. 모든 HTML에 manifest와 함께 넣었습니다.
- 아이폰 설치 안내는 iOS Safari에서만 보여줍니다. 아이폰의 Chrome·Firefox 등은 메뉴가 달라 문구가 맞지 않기 때문입니다.

**서비스 워커 캐시 범위** (`static/sw.js`, 이유는 [설계 결정 17번](#17-pwa-캐시는-정적-파일만))

| 요청 | 처리 |
|---|---|
| `/static/`의 HTML·CSS·JS·`manifest.json` | 네트워크 먼저, 연결이 안 될 때만 캐시. 화면 주소의 `?id=` 같은 값은 빼고 경로로 저장 |
| `/static/fonts/`, `/static/img/` | 캐시 먼저 (거의 바뀌지 않고 큼) |
| API(`/posts`, `/conversations`, `/users`, `/admin` 등), 사진(`/images`) | **캐시하지 않음.** 서비스 워커가 건드리지 않고 브라우저가 그대로 요청 |
| GET이 아닌 요청, 다른 사이트 | 건드리지 않음 |

- 설치할 때 기본 틀(목록 HTML, CSS, manifest, 아이콘)만 미리 받고, 나머지는 처음 열 때 담깁니다.
- **새 버전 배포**: `sw.js`의 `VERSION`을 바꾸면 브라우저가 새 서비스 워커를 설치하고, 켜지면서 이전 버전 캐시(`campus-books-static-이전버전`)를 모두 지웁니다. HTML·CSS·JS는 네트워크를 먼저 쓰므로 버전을 안 바꿔도 새 코드가 보이지만, **글꼴·아이콘을 바꿨다면 반드시 버전을 올려야** 사용자 기기에 반영됩니다.

### 구조

- **화면마다 HTML 1개와 스크립트 1개**(`js/pages/*.js`)를 둡니다. 공통 부품은 `ui.js`, 공통 헤더와 로그인 처리는 `auth.js`에 모았습니다.
- **API 호출은 `api.js`로만** 합니다. 토큰을 헤더에 넣고, 서버 에러를 `ApiError`(`status`, `message`, `fieldErrors`)로 바꿔 화면마다 같은 방식으로 처리합니다. 401을 받으면 토큰을 지웁니다.
- **토큰 접근은 `token.js`로만** 합니다. 저장 위치를 바꿀 때 이 파일 하나만 고치면 됩니다.
- **검색 조건과 페이지 번호는 주소창에 저장**합니다(`?q=...&page=2`). 새로고침, 뒤로 가기, 링크 공유에도 같은 결과가 나옵니다.
- 로그인이 필요한 화면에 로그아웃 상태로 들어오면 로그인 화면으로 보내고, 로그인 후 원래 주소로 돌려보냅니다.
- **사진은 글을 저장한 뒤 한 장씩 따로 올립니다.** 글(JSON) 저장 → 뺀 사진 삭제 → 새 사진 업로드 순서입니다. 지우기를 먼저 해야 "3장 중 1장 바꾸기"가 3장 제한에 걸리지 않습니다. 사진 일부가 실패하면 글은 이미 저장된 상태이므로 화면을 수정 모드(`?id=`)로 바꾸고 "글은 저장됐지만 사진 1장을 처리하지 못했습니다: (서버 메시지)"를 보여줍니다. 다시 저장해도 글이 두 번 생기지 않습니다.
- 사진을 고르면 형식·크기·장수를 먼저 확인해 걸린 파일만 빼고 이유를 보여줍니다. 최종 검사는 서버가 합니다. 이 기준값이 서버와 같은지 테스트로 확인합니다.
- **찜 하트**는 로그인하지 않아도 보이고, 누르면 로그인 화면으로 갔다가 돌아옵니다. 내 글에는 없고, 판매 완료된 글에는 찜해 둔 경우에만(해제할 수 있게) 보입니다. 누르면 응답이 올 때까지 잠그고 성공한 뒤에 하트를 바꿉니다. 실패하면 화면 아래에 서버 메시지를 잠깐 띄웁니다.
- 찜 목록에서 하트를 눌러 해제해도 카드는 새로고침 전까지 그 자리에 남습니다. 실수로 눌렀을 때 다시 찜할 수 있고, 목록이 갑자기 밀리지 않습니다.
- **신고 창**은 브라우저 기본 `<dialog>`(`showModal`)로 띄웁니다. Esc로 닫히고 열린 동안 뒤 화면은 누를 수 없습니다. 사유를 고르지 않았거나 "기타"인데 설명이 없으면 보내기 전에 알려주고, 409(이미 신고)·429(횟수 제한)는 창을 닫지 않고 서버 메시지를 보여줍니다. 사유 목록과 설명 글자 수가 서버와 같은지 테스트로 확인합니다.
- **차단**은 브라우저 확인 창으로 무엇이 달라지는지(서로 쪽지 불가, 글 숨김, 차단 목록 위치)를 알려준 뒤 진행합니다. 완료 안내에는 "차단 목록은 내 글 화면에서 확인·해제할 수 있어요."와 내 글 화면 링크를 붙입니다. 차단 후에는 서버에서 글·대화방 정보를 다시 받아 문의 버튼·하트·입력창을 서버 상태에 맞춥니다.
- 대화 중에 상대가 나를 차단하면 다음 전송이 400으로 막히고, 화면은 대화방 정보를 다시 받아 입력창을 잠급니다. 이때 안내는 "이 사용자에게는 쪽지를 보낼 수 없습니다."로, 누가 차단했는지 말하지 않습니다.
- 로그인하면 헤더의 "쪽지" 옆에 안 읽은 쪽지 수가 보입니다. 헤더를 먼저 그리고 숫자는 따로 불러와, 숫자 요청이 늦어도 화면이 늦게 뜨지 않습니다.
- **찾는 교재 알림 종**은 헤더 메뉴(`nav`) 밖, 헤더 오른쪽에 둡니다. 모바일에서는 로그인 메뉴가 숨겨지고(하단 탭 바가 대신) 탭 바는 이미 5칸이라, PC와 모바일 모두에서 보이는 자리를 골랐습니다. 안 읽은 알림 수는 쪽지 배지와 같은 방식(99+, 화면 낭독기용 링크 이름)으로 따로 불러옵니다. 알림 화면은 목록을 그린 **뒤에** 모두 읽음 처리하므로, 이번에 처음 보는 알림은 강조된 채 남고 배지만 사라집니다.
- **비밀번호 변경**에 성공하면 응답으로 받은 새 토큰을 바로 저장합니다. 서버가 변경 전 토큰을 모두 무효로 만들기 때문에, 바꾸지 않으면 다음 요청에서 로그아웃됩니다. 현재 비밀번호가 틀리면(400) 공통 영역이 아니라 그 칸 아래에 메시지를 보여줍니다.
- **회원 탈퇴**는 되돌릴 수 없어 비밀번호를 받은 뒤 확인 창을 두 번 띄웁니다. 성공하면 토큰을 지우고 완료 안내 후 목록 화면으로 이동합니다(`location.replace`).
- **관리자**에게만 헤더에 "관리" 링크가 보입니다. 헤더가 원래 부르는 `/users/me`의 `role`로 판단하므로 요청이 늘지 않습니다. 관리자가 아닌 사람이 `admin.html` 주소로 들어오면 목록 화면으로 보냅니다(`location.replace`라 뒤로 가기로 돌아오지 않음). 링크·화면을 숨기는 것은 편의일 뿐이고, 실제 권한 검사는 서버가 `/admin` API마다 합니다.
- **이용 정지 중**이면 모든 화면의 헤더 아래에 "○월 ○일 ○○:○○까지 이용이 정지된 상태입니다" 안내가 뜹니다. 쓰기 버튼을 눌러 403을 받고 나서야 알게 되지 않도록 하기 위해서입니다. 대화 화면은 입력창을 잠그고 같은 안내를 보여줍니다.

## 데이터 모델

```mermaid
erDiagram
    users ||--o{ posts : "판매"
    posts ||--o{ post_images : "사진 (최대 3장)"
    posts |o--o{ conversations : "문의 (글 삭제 시 NULL)"
    users ||--o{ conversations : "구매자 / 판매자"
    conversations ||--o{ messages : "포함"
    users ||--o{ messages : "보냄"
    users ||--o{ wishlists : "찜"
    posts ||--o{ wishlists : "찜됨 (글 삭제 시 함께 삭제)"
    users ||--o{ user_blocks : "차단함 (blocker)"
    users ||--o{ user_blocks : "차단당함 (blocked)"
    users |o--o{ reports : "신고함 (탈퇴 시 NULL)"
    users |o--o{ reports : "신고당함 (탈퇴 시 NULL)"
    users |o--o{ reports : "처리함 (관리자, 삭제 시 NULL)"
    users ||--o{ book_alerts : "찾는 교재 (최대 10개)"
    users ||--o{ alert_notifications : "받은 알림"
    posts ||--o{ alert_notifications : "알림 대상 (글 삭제 시 함께 삭제)"

    users {
        int id PK
        string email UK "최대 255자, 소문자로 저장"
        string password_hash "bcrypt"
        string nickname UK "2~30자"
        datetime created_at "DB 시간"
        string role "USER / ADMIN, 기본 USER, CLI로만 변경"
        datetime suspended_until "NULL 가능, 정지 종료 시각(UTC)"
    }

    book_alerts {
        int id PK
        int user_id FK "index"
        string keyword "2~100자, 교재명·과목명 부분 일치"
        int max_price "NULL이면 가격 무관, 이하(포함)"
        datetime created_at "DB 시간"
    }

    alert_notifications {
        int id PK
        int user_id FK "(user_id, post_id) unique, (user_id, created_at) index"
        int post_id FK "index"
        string keyword "알림을 만든 키워드 사본"
        datetime created_at "DB 시간"
        datetime read_at "NULL이면 안 읽음"
    }

    posts {
        int id PK
        int seller_id FK "index"
        string title "1~100자"
        string book_title "교재명, 1~200자"
        string course_name "과목명, 선택, 최대 100자"
        string condition "GOOD / FAIR / POOR"
        int price "0 ~ 10,000,000"
        text description "선택, 최대 2000자"
        string open_chat_url "선택, 최대 200자, https://open.kakao.com/ 로 시작"
        string status "ON_SALE / RESERVED / SOLD"
        datetime created_at "index, 최신순 정렬용"
        datetime updated_at "수정 시 자동 갱신"
    }

    post_images {
        int id PK
        int post_id FK "index, 글 삭제 시 함께 삭제"
        int slot "0~2, (post_id, slot) unique, 보여주는 순서"
        string filename "서버가 만든 이름 (32자리 16진수).webp"
        string thumb_filename "같은 이름_thumb.webp"
        datetime created_at "DB 시간, 업로드 횟수 제한에 사용"
    }

    conversations {
        int id PK
        int post_id FK "NULL 가능, (post_id, buyer_id) unique"
        int buyer_id FK "index"
        int seller_id FK "index, 글이 지워져도 권한 검사용"
        datetime created_at "DB 시간"
        datetime last_message_at "index, 최신 메시지순 정렬"
        int last_message_id "같은 초 정렬 보조, 마지막 메시지 조회"
    }

    wishlists {
        int user_id PK "FK, (user_id, post_id) 기본 키 = 같은 글은 한 번만"
        int post_id PK "FK, index (글 삭제 때 찾기)"
        datetime created_at "DB 시간, (user_id, created_at) index"
    }

    user_blocks {
        int blocker_id PK "FK, (blocker_id, blocked_id) 기본 키 = 한 번만"
        int blocked_id PK "FK, index (나를 차단했는지 찾기)"
        datetime created_at "DB 시간, CHECK blocker_id <> blocked_id"
    }

    reports {
        int id PK
        int reporter_id FK "NULL 가능, (reporter_id, created_at) index"
        string target_type "POST / USER"
        int target_id "글 또는 사용자 id, FK 없음, (reporter_id, target_type, target_id) unique"
        int reported_user_id FK "NULL 가능, index, 글 신고면 작성자"
        string reason "SPAM / FRAUD / ABUSE / INAPPROPRIATE / OTHER"
        text description "선택(OTHER는 필수), 최대 500자"
        string post_title_snapshot "글 신고 시점의 제목 사본"
        text post_content_snapshot "글 신고 시점의 설명 사본"
        string status "PENDING / RESOLVED, (status, created_at) index"
        datetime created_at "DB 시간"
        string action "처리 후: DISMISS / DELETE_POST / SUSPEND"
        text resolution_note "처리 메모, 선택, 최대 500자"
        int resolved_by_id FK "처리한 관리자, 삭제 시 NULL"
        datetime resolved_at "DB 시간"
        int resolved_with_report_id "다른 신고와 함께 처리됐으면 그 신고 번호"
    }

    messages {
        int id PK
        int conversation_id FK "(conversation_id, id) index"
        int sender_id FK "(sender_id, created_at) index, 도배 검사"
        text content "1~1000자"
        datetime created_at "DB 시간"
        datetime read_at "NULL이면 안 읽음"
    }
```

- `condition`과 `status`는 DB 고유 ENUM 대신 **문자열 컬럼 + 값 검사**로 저장합니다. SQLite와 PostgreSQL에서 똑같이 동작하게 하기 위해서입니다.
- 사진 파일은 DB가 아니라 `UPLOAD_DIR/posts/`에 두고, DB에는 서버가 만든 파일 이름만 저장합니다. 사용자가 올린 원래 파일 이름은 저장하지 않습니다.
- 글당 3장 제한은 서비스 검사와 함께 `(post_id, slot)` unique + `slot` 0~2 CHECK 제약으로 DB에서도 막습니다. 동시에 올려도 3장을 넘지 않습니다.
- 신고의 `target_id`에는 FK를 걸지 않았습니다. 글이 삭제되면 행이 지워지지만 신고 기록은 남아야 하기 때문입니다. 대신 신고 시점의 글 제목·설명을 사본으로 저장합니다([설계 결정 14번](#14-신고차단-저장만-하는-신고-상대에게-알리지-않는-차단)).
- `created_at`과 `updated_at`은 앱 서버 시간이 아니라 DB 시간을 씁니다. `updated_at`은 값이 실제로 바뀐 경우에만 갱신됩니다.
- 회원 탈퇴는 `users` 행을 지우지 않고 이메일·닉네임·비밀번호를 지운 "탈퇴 표시" 행으로 남깁니다. `password_hash`가 `!withdrawn`이면 탈퇴한 계정입니다([설계 결정 19번](#19-회원-탈퇴-사용자-행은-지우지-않고-익명화)).
- 알림의 `(user_id, post_id)` unique 제약으로, 조건이 여러 개 맞거나 글 수정으로 다시 매칭해도 한 사람에게 같은 글 알림은 하나만 생깁니다.

## 실행 방법

### 1. 설치

```bash
git clone https://github.com/kim123-dev/campus-books.git
cd campus-books

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env.example`을 복사해 `.env`를 만듭니다. `.env`는 `.gitignore`에 포함되어 있어 커밋되지 않습니다.

```bash
cp .env.example .env
```

`SECRET_KEY`는 반드시 바꿔야 합니다. HS256 서명에는 **32바이트 이상**의 키를 권장합니다.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

| 변수 | 기본값 | 설명 |
|---|---|---|
| `ENVIRONMENT` | `development` | `production`이면 API 문서를 끄고 운영 설정을 검사합니다([배포](#배포-railway)) |
| `DATABASE_URL` | `sqlite:///./dev.db` | 운영에서는 PostgreSQL 주소(`postgresql://…`, 드라이버는 자동으로 psycopg로 바뀜) |
| `SECRET_KEY` | (없음, 필수) | JWT 서명 키. 기본값이 없어서, 설정하지 않으면 서버가 시작되지 않습니다 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | 액세스 토큰 유효 시간(분) |
| `UPLOAD_DIR` | `./uploads` | 사진 저장 폴더. 사진은 그 아래 `posts/`에 저장됩니다. `static/` 밖에 두어야 합니다 |
| `BCRYPT_ROUNDS` | `12` | 비밀번호 해시 작업 비용(4~31). 운영에서는 기본값을 그대로 쓰세요. 테스트에서만 4로 낮춥니다 |

### 3. 서버 실행

```bash
uvicorn app.main:app --reload
```

- 서버가 시작될 때 테이블이 없으면 자동으로 만듭니다(`create_all`). 이미 있는 테이블에 컬럼을 추가하지는 않습니다(아래 참고).
  - 쪽지 기능의 `conversations`, `messages`, 사진의 `post_images`, 찜의 `wishlists`, 차단의 `user_blocks`, 신고의 `reports`, 찾는 교재 알림의 `book_alerts`, `alert_notifications`는 새 테이블이라 기존 `dev.db`에서도 서버를 켜면 자동으로 생깁니다. 별도 작업이 필요 없습니다.
  - 사진 폴더(`uploads/posts/`)는 첫 업로드 때 자동으로 만들어집니다.
- 웹 화면: http://127.0.0.1:8000/
- API 문서: http://127.0.0.1:8000/docs (개발 모드에서만. 운영 모드에서는 꺼집니다)
- `/docs` 오른쪽 위의 **Authorize** 버튼에 가입한 이메일(username 칸)과 비밀번호를 넣으면, 로그인이 필요한 API를 바로 호출할 수 있습니다.

### 4. 기존 `dev.db` 업데이트 (오픈채팅 링크 추가 전에 만든 DB)

`create_all`은 없는 테이블만 만들고, 이미 있는 `posts` 테이블에 새 컬럼을 추가하지 않습니다.
그래서 `open_chat_url` 컬럼이 생기기 전에 만든 `dev.db`를 그대로 쓰면 글 조회가 `no such column` 오류(500)로 실패합니다.
아래처럼 한 번만 백업하고 컬럼을 추가하면 기존 데이터를 유지한 채 사용할 수 있습니다. 비워도 되는 컬럼이라 기존 글은 링크 없이(`NULL`) 남습니다.

```bash
# 1. 백업 (*.bak은 .gitignore에 포함되어 커밋되지 않습니다)
cp dev.db dev.db.bak

# 2. 컬럼 추가 (sqlite3 명령이 없으면 아래 python 한 줄을 사용)
sqlite3 dev.db "ALTER TABLE posts ADD COLUMN open_chat_url VARCHAR(200);"
python -c "import sqlite3; c = sqlite3.connect('dev.db'); c.execute('ALTER TABLE posts ADD COLUMN open_chat_url VARCHAR(200)'); c.commit()"
```

- 이미 컬럼이 있으면 `duplicate column name` 오류가 나며 아무것도 바뀌지 않습니다.
- 데이터가 필요 없다면 `dev.db`를 지우고 서버를 다시 켜도 됩니다. 테이블이 새 구조로 만들어집니다.
- 이런 수동 작업을 없애려면 마이그레이션 도구(Alembic)가 필요합니다([향후 개선 계획 2번](#향후-개선-계획)).

### 5. 기존 `dev.db` 업데이트 (관리자·신고 처리 추가 전에 만든 DB)

관리자 기능은 이미 있는 `users`, `reports` 테이블에 컬럼을 추가합니다. 4번과 같은 이유로, 그 전에 만든 `dev.db`는 아래처럼 한 번 백업하고 컬럼을 추가해야 합니다. 이 작업 없이 서버를 켜면 로그인·신고 등이 `no such column` 오류(500)로 실패하고, 관리자 지정 CLI는 "DB를 읽지 못했습니다"라고 안내합니다.

```bash
# 1. 백업
cp dev.db dev.db.before-admin.bak

# 2. 컬럼·인덱스 추가 (python으로 한 번에)
python - <<'EOF'
import sqlite3
con = sqlite3.connect("dev.db")
with con:
    for sql in [
        "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'USER'",
        "ALTER TABLE users ADD COLUMN suspended_until DATETIME",
        "ALTER TABLE reports ADD COLUMN action VARCHAR(20)",
        "ALTER TABLE reports ADD COLUMN resolution_note TEXT",
        "ALTER TABLE reports ADD COLUMN resolved_by_id INTEGER REFERENCES users (id) ON DELETE SET NULL",
        "ALTER TABLE reports ADD COLUMN resolved_at DATETIME",
        "ALTER TABLE reports ADD COLUMN resolved_with_report_id INTEGER",
        "CREATE INDEX ix_reports_status_created ON reports (status, created_at)",
    ]:
        con.execute(sql)
EOF
```

- 기존 사용자는 모두 일반 사용자(`USER`), 정지 없음(`NULL`)으로 남고, 기존 신고는 모두 미처리(`PENDING`)로 보입니다.
- 컬럼을 **코드보다 먼저** 추가해도 괜찮습니다. 예전 코드는 모르는 컬럼을 무시하므로, `--reload`로 서버를 켜 둔 채 작업해도 오류가 나지 않습니다.
- Windows PowerShell처럼 `<<'EOF'`를 쓸 수 없으면, 위 목록을 `.py` 파일로 저장해 `python 파일이름.py`로 실행하세요.

### 6. 관리자 지정

관리자는 가입 화면이나 API로 만들 수 없습니다. 먼저 일반 회원으로 가입한 뒤, **서버에서** 다음 명령을 실행합니다.

```bash
python -m app.cli make-admin admin@campus.ac.kr
```

- `.env`의 `DATABASE_URL`이 가리키는 DB를 바꿉니다. 서버를 끄지 않아도 되고, 다시 로그인하지 않아도 바로 적용됩니다(권한을 토큰이 아니라 요청마다 DB에서 읽기 때문).
- 가입하지 않은 이메일이면 종료 코드 1과 함께 "가입한 사용자가 없습니다"를 출력합니다. 이미 관리자면 아무것도 바꾸지 않습니다.
- 관리자 해제 명령은 아직 없습니다([향후 개선 계획](#향후-개선-계획)).
- 배포한 서버에서 지정하는 방법은 [배포 후 관리자 지정](#배포-후-관리자-지정)을 보세요.

## 배포 (Railway)

> 배포 주소: **https://campus-books-production.up.railway.app**

[Railway](https://railway.com)에 GitHub 저장소를 연결해 배포하도록 구성했습니다. 앱 서비스 하나, PostgreSQL 서비스 하나, 사진용 볼륨 하나로 이루어집니다.

```mermaid
flowchart LR
    User["브라우저 · 홈 화면 앱"] -->|HTTPS| Proxy["Railway 프록시"]
    Proxy -->|"HTTP, PORT"| App["앱 컨테이너<br/>Dockerfile · uvicorn"]
    App --> PG[("PostgreSQL 서비스")]
    App --> Vol[("볼륨 /data<br/>사진: /data/uploads")]
```

### 구성 파일

| 파일 | 내용 |
|---|---|
| `Dockerfile` | `python:3.14-slim`(개발과 같은 버전). 의존성을 먼저 설치해 코드만 바뀐 배포는 캐시로 빨리 빌드. `app/`, `static/`만 복사. `uvicorn`을 `exec`로 실행해 재배포 종료 신호를 바로 받음. 포트는 Railway가 넣는 `PORT`를 씀 |
| `.railway/railway.ts` | Railway 설정을 코드로 관리(IaC). Dockerfile로 빌드, 헬스 체크 `GET /health`(100초), 실패 시 재시작(최대 10번), 볼륨 `campus-books-volume`을 `/data`에 연결. 환경 변수는 관리하지 않음(`unmanaged`) |
| `.dockerignore` | `.env`, `*.db`, `*.bak`, `uploads/`, `tests/`, `docs/`, `.git/` 등을 이미지에서 제외. 비밀값·로컬 DB·사용자 사진이 이미지에 섞이지 않게 함 |

- 프록시(HTTPS 종료) 뒤에서 동작하므로 `--proxy-headers --forwarded-allow-ips='*'`로 `X-Forwarded-*` 헤더를 믿게 했습니다. 그래야 리다이렉트 주소가 `https://`로 만들어집니다.
- 컨테이너는 root로 실행합니다. Railway 볼륨이 root 소유로 붙어서, 다른 사용자로 바꾸면 사진을 저장하지 못하기 때문입니다.

### Railway 설정 코드 (`railway.ts`)

예전에는 `railway.json`(Config as Code)을 썼지만, 이 방식은 2026-12-01부터 읽히지 않아 `.railway/railway.ts`로 옮겼습니다. Railway는 배포할 때 `.railway/`를 읽지 않으므로, 바꾼 내용은 CLI로 직접 반영해야 합니다.

```bash
npm install                 # railway.ts가 쓰는 Railway SDK 설치
railway config plan         # 바뀔 내용 미리보기 (destructive 0건인지 확인)
railway config apply        # 실제 반영
```

- **Windows(Git Bash)에서 plan이 "CLI 5.42.1 이상 필요"로 실패할 때:** SDK가 `$_` 경로로 CLI 버전을 다시 확인하는데, `railway` 셸 래퍼를 거치면 이 경로가 실행할 수 없는 값이 됩니다. exe를 직접 실행하고 그 경로를 넘깁니다.
  ```bash
  R="$(npm root -g)/@railway/cli/bin/railway.exe"; _="$(cygpath -w "$R")" "$R" config plan
  ```
- **대시보드 Builder를 직접 `Dockerfile`로 맞춘 이유:** railway.json의 값은 그 배포에만 쓰이고 서비스 설정에는 저장되지 않아, 대시보드에는 기본값 Railpack이 남아 있었습니다. apply는 IaC 쪽 값만 바꾸므로, railway.json을 지우기 전에 대시보드에서 Builder를 Dockerfile로 맞추고 첫 배포가 Dockerfile로 빌드되는지 확인했습니다.
- **plan에 재시작 정책 변경이 계속 남는 이유:** `ON_FAILURE`/최대 10번은 Railway 기본값이라 IaC 쪽에서는 빈 값(null)으로 읽힙니다. 그래서 apply 뒤에도 plan이 `null → ON_FAILURE`, `null → 10`을 보여 줍니다. 실제 서비스와 배포에는 이미 적용돼 있어 무시해도 됩니다. 이 두 줄 외의 변경이 나오면 확인합니다.
- **볼륨은 region(`sfo`)과 크기(500MB)까지 적어 둡니다.** 빼면 plan이 볼륨 연결을 떼거나 값을 지우려 합니다(destructive).

### 배포 순서

1. Railway에서 새 프로젝트를 만들고 GitHub 저장소를 연결합니다. 서비스 Settings의 Builder를 `Dockerfile`로 둡니다. 빌드·헬스 체크·재시작 설정은 `railway config apply`로 반영합니다([Railway 설정 코드](#railway-설정-코드-railwayts)).
2. 같은 프로젝트에 **PostgreSQL** 서비스를 추가합니다.
3. 앱 서비스에 **볼륨**을 추가하고 마운트 경로를 `/data`로 둡니다. 사진은 그 아래 `/data/uploads/posts/`에 저장됩니다. 컨테이너 디스크는 재배포 때 초기화되므로 볼륨이 없으면 사진이 사라집니다.
4. 앱 서비스의 **Variables**에 아래 환경 변수를 넣습니다.
5. **Networking**에서 도메인을 만들면 https 주소가 생깁니다. 서비스 워커(PWA)는 https에서만 동작하므로 이 주소로 접속합니다.
6. 첫 배포가 뜨면 테이블은 `create_all`이 자동으로 만듭니다. 가입한 뒤 [관리자를 지정](#배포-후-관리자-지정)합니다.

| 변수 | 값 | 설명 |
|---|---|---|
| `ENVIRONMENT` | `production` | 운영 모드 (아래 표) |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | PostgreSQL 서비스의 주소를 참조. `postgres://`·`postgresql://`는 `postgresql+psycopg://`로 자동 변환 |
| `SECRET_KEY` | 32자 이상 임의 값 | `python -c "import secrets; print(secrets.token_urlsafe(32))"`로 만듭니다. 코드·저장소에는 두지 않습니다 |
| `UPLOAD_DIR` | `/data/uploads` | 볼륨 안의 사진 폴더 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | (선택) `60` | 토큰 유효 시간(분) |

`PORT`는 Railway가 넣어 주므로 따로 설정하지 않습니다.

### 운영 모드 (`ENVIRONMENT=production`)

| 항목 | 동작 |
|---|---|
| API 문서 | `/docs`, `/redoc`, `/openapi.json`을 끕니다(404). 누구나 전체 API 구조를 훑어보지 못하게 하기 위해서입니다. 개발 모드에서는 그대로 켜져 있습니다 |
| DB 확인 | `DATABASE_URL`이 SQLite면 **서버가 시작되지 않습니다.** 배포 서버의 디스크는 재배포 때 초기화되어 SQLite 파일이 통째로 사라지기 때문입니다 |
| 키 확인 | `SECRET_KEY`가 32자보다 짧으면 **서버가 시작되지 않습니다.** 짧은 키는 JWT 위조를 막기 어렵습니다 |

설정을 빠뜨린 채 떠서 데이터가 사라지거나 토큰이 위조되는 것보다, 시작 단계에서 멈추는 쪽이 안전하다고 보았습니다. 이 검사는 `test_production_settings.py`가 확인합니다.

### 배포 후 관리자 지정

관리자는 웹으로 만들 수 없고 서버 CLI로만 지정합니다([설계 결정 15번](#15-관리자-cli로만-지정-라우터-단위-권한-검사-정지는-요청마다-확인)). 먼저 배포된 사이트에서 일반 회원으로 가입한 뒤, 다음 중 한 가지로 실행합니다.

```bash
# 방법 1: Railway CLI로 실행 중인 앱 컨테이너에 접속해 실행 (컨테이너의 DATABASE_URL을 그대로 씀)
railway ssh
python -m app.cli make-admin admin@campus.ac.kr

# 방법 2: 내 컴퓨터에서 운영 DB를 가리켜 실행
# PostgreSQL 서비스 Variables의 외부 접속 주소(DATABASE_PUBLIC_URL)를 씁니다.
DATABASE_URL="postgresql://…(외부 접속 주소)" python -m app.cli make-admin admin@campus.ac.kr
```

- 다시 로그인하지 않아도 바로 적용됩니다(권한을 토큰이 아니라 요청마다 DB에서 읽기 때문).
- 방법 2는 운영 DB 주소가 내 컴퓨터의 셸 기록에 남을 수 있으므로, 실행 뒤 기록을 지우거나 방법 1을 권장합니다.

### 운영에서 주의할 점

- **스키마 변경**: `create_all`은 새 테이블만 만들고 기존 테이블의 컬럼은 바꾸지 않습니다. 새 테이블만 추가한 기능(쪽지, 찜, 차단, 신고, 찾는 교재 알림)은 그대로 배포하면 되지만, 기존 테이블에 컬럼을 추가하면 PostgreSQL에도 `ALTER TABLE`을 직접 실행해야 합니다. Alembic 도입이 다음 과제입니다([향후 개선 계획 2번](#향후-개선-계획)).
- **인스턴스 수**: 볼륨은 서비스 하나에만 붙으므로 앱은 한 대로 운영합니다. 도배·신고·업로드 횟수 제한은 DB 기준이라 여러 대로 늘려도 동작하지만, 사진 저장은 오브젝트 스토리지로 옮긴 뒤에 늘릴 수 있습니다.
- **백업**: PostgreSQL과 볼륨(사진)은 따로 백업해야 합니다.

## API 목록

총 38개입니다. 🔒 표시는 `Authorization: Bearer <토큰>` 헤더가 필요한 API이고, 🔒✋는 이용 정지 중이면 403인 쓰기 API, 🔒👑는 관리자 전용 API입니다.

| 메서드 | 경로 | 인증 | 설명 | 성공 | 주요 실패 |
|---|---|---|---|---|---|
| GET | `/health` | | 서버 상태 확인 | 200 | |
| POST | `/auth/signup` | | 회원가입 | 201 | 409 이메일·닉네임 중복, 422 |
| POST | `/auth/login` | | 로그인 (form: `username`=이메일, `password`) | 200 | 401, 403 이용 정지, 422 |
| GET | `/users/me` | 🔒 | 내 정보 조회 (`role`, `suspended_until`은 이 응답에만) | 200 | 401 |
| GET | `/users/me/posts` | 🔒 | 내 판매글 목록 (모든 상태, 최신순) | 200 | 401, 422 |
| GET | `/users/me/wishlist` | 🔒 | 내 찜 목록 (찜한 순서 최신순, 판매 완료 포함) | 200 | 401, 422 |
| PUT | `/users/me/password` | 🔒 | 비밀번호 변경 (새 액세스 토큰 발급, 이전 토큰은 모두 무효) | 200 | 400 현재 비밀번호 불일치, 401, 422 |
| POST | `/users/me/withdraw` | 🔒 | 회원 탈퇴 (본문 `{"password": …}`) | 204 | 400 비밀번호 불일치·관리자, 401, 422 |
| GET | `/users/me/alerts` | 🔒 | 내 찾는 교재 조건 목록 (`max_count` 포함) | 200 | 401 |
| POST | `/users/me/alerts` | 🔒✋ | 찾는 교재 등록 | 201 | 400 개수 초과, 401, 409 같은 키워드, 422 |
| DELETE | `/users/me/alerts/{alert_id}` | 🔒 | 찾는 교재 삭제 (받은 알림은 남음) | 204 | 401, 404 없거나 남의 조건 |
| GET | `/users/me/blocks` | 🔒 | 내가 차단한 사용자 목록 (차단한 순서 최신순) | 200 | 401, 422 |
| POST | `/users/{user_id}/block` | 🔒 | 차단 (이미 차단했으면 그대로) | 201 / 200 | 400 자기 자신, 401, 404 |
| DELETE | `/users/{user_id}/block` | 🔒 | 차단 해제 (차단하지 않은 사용자여도 성공) | 204 | 401, 404 |
| POST | `/users/{user_id}/reports` | 🔒✋ | 사용자 신고 | 201 | 400 자기 자신, 401, 404, 409 중복, 422, 429 |
| POST | `/posts` | 🔒✋ | 판매글 작성 (상태는 항상 `ON_SALE`로 시작) | 201 | 401, 422 |
| GET | `/posts` | 선택 | 판매글 목록 (검색·필터, 최신순, `is_wishlisted`는 로그인 시에만, 로그인 시 내가 차단한 사용자의 글 제외) | 200 | 422 |
| GET | `/posts/{post_id}` | 선택 | 판매글 상세 (`open_chat_url`·`is_wishlisted`·`is_seller_blocked`는 로그인 시에만) | 200 | 404 |
| PATCH | `/posts/{post_id}` | 🔒✋ | 판매글 수정 (보낸 필드만) | 200 | 400 판매 완료, 401, 403, 404, 422 |
| PATCH | `/posts/{post_id}/status` | 🔒✋ | 판매 상태 변경 | 200 | 400 전이 불가, 401, 403, 404, 422 |
| DELETE | `/posts/{post_id}` | 🔒✋ | 판매글 삭제 (쪽지 대화방은 남음, 사진은 파일까지 삭제) | 204 | 401, 403, 404 |
| POST | `/posts/{post_id}/images` | 🔒✋ | 사진 1장 올리기 (multipart, 필드 이름 `file`) | 201 | 400 판매 완료·이미 3장, 401, 403, 404, 413 5MB 초과, 422 형식, 429 |
| DELETE | `/posts/{post_id}/images/{image_id}` | 🔒✋ | 사진 삭제 (파일도 삭제) | 204 | 400 판매 완료, 401, 403, 404 |
| GET | `/images/{filename}` | | 사진 파일 (`image/webp`) | 200 | 404 |
| POST | `/posts/{post_id}/wishlist` | 🔒✋ | 찜하기 (이미 찜했으면 그대로) | 201 / 200 | 400 본인 글·판매 완료 글에 새 찜, 401, 404 |
| DELETE | `/posts/{post_id}/wishlist` | 🔒✋ | 찜 해제 (찜하지 않은 글이어도 성공) | 204 | 401, 404 |
| POST | `/posts/{post_id}/reports` | 🔒✋ | 글 신고 | 201 | 400 본인 글, 401, 404, 409 중복, 422, 429 |
| POST | `/posts/{post_id}/conversations` | 🔒✋ | 문의 시작 (이미 있으면 기존 대화방) | 201 / 200 | 400 본인 글·판매 완료·차단 관계(새 방만), 401, 404 |
| GET | `/conversations` | 🔒 | 내 대화방 목록 (최신 메시지순) | 200 | 401, 422 |
| GET | `/conversations/unread-count` | 🔒 | 안 읽은 쪽지 수 (헤더 배지용) | 200 | 401 |
| GET | `/conversations/{conversation_id}` | 🔒 | 대화방 정보 (`can_send`·`blocked_by_me` 포함) | 200 | 401, 403, 404 |
| GET | `/conversations/{conversation_id}/messages` | 🔒 | 메시지 목록 (조회 시 상대 메시지 읽음 처리) | 200 | 401, 403, 404, 422 |
| POST | `/conversations/{conversation_id}/messages` | 🔒✋ | 메시지 전송 | 201 | 400 차단 관계·탈퇴한 상대, 401, 403, 404, 422, 429 도배 |
| GET | `/notifications` | 🔒 | 찾는 교재 알림 목록 (최신순, 페이지네이션, 차단한 판매자 글 제외) | 200 | 401, 422 |
| GET | `/notifications/unread-count` | 🔒 | 안 읽은 알림 수 (헤더 종 배지용) | 200 | 401 |
| POST | `/notifications/read-all` | 🔒 | 알림 모두 읽음 | 204 | 401 |
| GET | `/admin/reports` | 🔒👑 | 신고 목록 (미처리 먼저, 최신순, `status` 필터, 페이지네이션) | 200 | 401, 403, 422 |
| POST | `/admin/reports/{report_id}/resolve` | 🔒👑 | 신고 처리 (기각·글 삭제·기간 정지) | 200 | 400 조치 규칙 위반, 401, 403, 404, 409 이미 처리, 422 |

🔒✋ API는 이용 정지 중이면 위 실패 코드보다 먼저 **403** "○월 ○일 ○○:○○까지 이용이 정지되었습니다."를 돌려줍니다([이용 정지](#이용-정지)).

### 목록 쿼리 파라미터 (`GET /posts`)

| 파라미터 | 형식 | 설명 |
|---|---|---|
| `q` | 문자열, 최대 100자 | 제목·교재명·과목명 중 하나라도 **부분 일치**. 대소문자 무시. `%`, `_`, `\`는 일반 글자로 처리 |
| `status` | `ON_SALE` / `RESERVED` / `SOLD` | 판매 상태. 보내지 않으면 전체 |
| `course_name` | 문자열, 최대 100자 | 과목명 **정확히 일치**. 앞뒤 공백 제거, 대소문자 무시 |
| `min_price` | 0 ~ 10,000,000 | 최소 가격 (포함) |
| `max_price` | 0 ~ 10,000,000 | 최대 가격 (포함). `min_price`보다 작으면 422 |
| `page` | 1 이상, 기본 1 | 페이지 번호 |
| `size` | 1 ~ 100, 기본 20 | 페이지당 글 수 |

- 여러 조건을 보내면 모두 AND로 묶입니다. `q`나 `course_name`에 빈 값을 보내면 조건이 없는 것으로 봅니다.
- `/users/me/posts`는 `page`, `size`만 지원합니다.

예시 요청:

```
GET /posts?q=자료구조&status=ON_SALE&min_price=10000&max_price=20000&page=1&size=10
```

응답 형식 (`total`은 조건에 맞는 전체 글 수):

```json
{
  "items": [
    {
      "id": 1,
      "title": "자료구조 교재 팝니다",
      "book_title": "C언어로 쉽게 풀어쓴 자료구조",
      "course_name": "자료구조",
      "condition": "GOOD",
      "price": 15000,
      "description": "필기 거의 없어요.",
      "status": "ON_SALE",
      "seller": { "id": 3, "nickname": "책벌레" },
      "thumbnail_url": null,
      "is_wishlisted": false,
      "created_at": "2026-11-06T10:00:00",
      "updated_at": "2026-11-06T10:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10
}
```

판매자 정보는 `id`와 `nickname`만 보여주고, 이메일은 노출하지 않습니다.

### 오픈채팅 링크 (`open_chat_url`)

작성(`POST /posts`)과 수정(`PATCH /posts/{post_id}`)에서 선택으로 보낼 수 있습니다.

| 규칙 | 내용 |
|---|---|
| 허용 형식 | `https://open.kakao.com/`으로 시작하고, 뒤에 영문·숫자와 `. _ ~ - / ? = & %`만 있는 주소 |
| 거절 (422) | `javascript:`, `data:`, `http://`, 다른 도메인(`open.kakao.com.evil.com` 포함), 따옴표·꺾쇠·공백·역슬래시가 섞인 주소, 201자 이상 |
| 빈 값 | `""`, 공백만, `null`은 "링크 없음"으로 저장. 수정에서 보내면 링크가 지워집니다 |
| 응답 범위 | 상세·작성·수정·상태 변경 응답에만 포함. 목록과 내 글 목록 응답에는 없습니다 |
| 공개 범위 | `GET /posts/{post_id}`는 로그인 없이도 볼 수 있지만, 토큰이 없거나 잘못·만료되었으면 `open_chat_url`을 `null`로 응답합니다 (401이 아님) |

### 사진

| 규칙 | 내용 |
|---|---|
| 형식 | JPG, PNG, WebP. 확장자나 `Content-Type`이 아니라 **파일 내용**을 Pillow로 열어 판단합니다. `.jpg`로 이름만 바꾼 텍스트, 앞부분만 JPEG처럼 꾸민 파일, 중간에 잘린 사진은 422. PNG를 `.jpg`라는 이름으로 올리면 내용이 PNG이므로 받습니다 |
| 크기 | 장당 5MB. `Content-Length`가 크면 본문을 받기 전에 413, 헤더가 없어도 서비스가 읽으면서 5MB를 넘는 순간 멈추고 413 |
| 해상도 | 4천만 픽셀 초과는 422. 작은 파일이 풀면 거대한 이미지가 되어 메모리를 다 쓰는 공격(decompression bomb)을 막습니다 |
| 장수 | 글당 3장. 4번째는 400. 지운 칸은 다음 업로드가 다시 씁니다 |
| 저장 | WebP로 다시 인코딩. 상세용(긴 변 1600px)과 썸네일(긴 변 400px) 2개 파일. 휴대폰 사진의 회전 정보는 픽셀에 반영한 뒤 메타데이터를 지웁니다. 투명 PNG는 투명도를 유지합니다 |
| 업로드 횟수 | 한 사용자가 10분에 20장까지. 넘으면 429 (`Retry-After: 600`). 기준은 `image_service.IMAGE_UPLOAD_RATE_LIMIT` 하나로 바꿉니다 |
| 판매 완료 | 판매 완료된 글은 내용처럼 사진도 추가·삭제할 수 없습니다(400) |
| 삭제 | 사진 삭제·글 삭제 모두 DB를 먼저 커밋하고 파일을 지웁니다. 파일 삭제가 실패해도 요청은 성공하고 로그만 남깁니다 |

응답에서 사진은 다음과 같이 보입니다.

- 상세(`GET /posts/{id}`): `"images": [{"id": 3, "url": "/images/3f9c…e1.webp", "thumbnail_url": "/images/3f9c…e1_thumb.webp"}]` (보여주는 순서대로)
- 목록·내 글 목록: 글마다 첫 사진의 `"thumbnail_url"` 하나 (사진이 없으면 `null`). 목록에는 사진 목록 전체를 싣지 않습니다.

판정 순서: 401 → 404 글 없음 → 403 작성자 아님 → 400 판매 완료 → 400 이미 3장 → 429 횟수 제한 → 413 크기 → 422 형식. 디코딩처럼 무거운 일은 싼 검사를 모두 통과한 뒤에 합니다.

### 1:1 쪽지

구매자가 판매글에서 문의를 시작하면 대화방이 생기고, 그 방의 구매자와 판매자만 조회·전송할 수 있습니다.

| 규칙 | 내용 |
|---|---|
| 대화방 수 | 같은 글·같은 구매자의 대화방은 하나. 다시 요청하면 기존 방을 200으로 돌려줍니다 (DB unique 제약 + 동시 요청 시 기존 방 반환) |
| 문의 불가 | 본인 글(400), 판매 완료된 글에 **새** 문의(400). 판매 완료 전에 만든 방은 계속 쓸 수 있고, 예약 중인 글은 문의할 수 있습니다 |
| 권한 | 방이 없으면 404, 구매자·판매자가 아니면 403. 글이 삭제되어도 그대로 적용됩니다 |
| 메시지 내용 | 앞뒤 공백을 지운 뒤 1~1000자. 공백만 있으면 422. 문장 사이 줄바꿈은 유지 |
| 읽음 처리 | 메시지 목록을 조회하면, 그 방에서 상대가 보낸 안 읽은 메시지 **전체**의 `read_at`을 채웁니다 |
| 도배 방지 | 같은 사용자가 최근 **10초 안에 5개**를 보냈으면 429 (`Retry-After: 10`). 대화방과 상관없이 셉니다 |
| 개인정보 | 상대 정보는 `id`와 `nickname`만. 이메일은 어떤 응답에도 없습니다 |
| 상대 탈퇴 | 대화방과 메시지는 남습니다. 상대는 `nickname: "탈퇴한 사용자"`, `withdrawn: true`로 보이고, `can_send`가 `false`, 전송은 400 "탈퇴한 사용자에게는 쪽지를 보낼 수 없습니다." |

대화방 응답 (목록 항목과 대화방 정보가 같은 형식, `post`는 글이 삭제되면 `null`):

```json
{
  "id": 7,
  "post": { "id": 1, "title": "자료구조 교재 팝니다", "status": "ON_SALE" },
  "partner": { "id": 3, "nickname": "책벌레", "withdrawn": false },
  "my_role": "BUYER",
  "last_message": { "content": "네, 아직 있어요", "is_mine": false, "created_at": "2026-11-09T10:05:00" },
  "unread_count": 1,
  "created_at": "2026-11-09T10:00:00",
  "last_message_at": "2026-11-09T10:05:00"
}
```

메시지 목록은 페이지 번호 대신 **메시지 id 커서**를 씁니다. 응답은 `{"items": [...], "has_more": true}`이고, `items`는 오래된 것부터 정렬됩니다.

| 파라미터 | 설명 |
|---|---|
| (없음) | 최근 `limit`개 |
| `before_id` | 이 id보다 오래된 메시지 `limit`개 (위로 스크롤해 이전 대화 보기) |
| `after_id` | 이 id보다 새 메시지 `limit`개 (새 메시지 확인) |
| `limit` | 1 ~ 100, 기본 50 |

`before_id`와 `after_id`를 함께 보내면 422입니다.

### 찜

| 규칙 | 내용 |
|---|---|
| 중복 | 같은 글은 한 번만. 다시 찜하면 200으로 그대로 성공합니다 (DB 기본 키 + 동시 요청 시 기존 찜으로 처리) |
| 해제 | 찜하지 않은 글을 해제해도 204. 같은 요청을 여러 번 보내도 결과가 같습니다 |
| 찜 불가 | 본인 글(400), 판매 완료된 글에 **새** 찜(400). 찜해 둔 뒤 판매 완료되면 목록에 남고 해제할 수 있습니다. 예약 중인 글은 찜할 수 있습니다 |
| 찜 여부 | 목록·상세 응답의 `is_wishlisted`. 로그인했으면 `true`/`false`, 로그인하지 않았거나 토큰이 잘못되었으면 `null`. 내 글 목록에서는 `null` |
| 찜 목록 순서 | 찜한 시각 최신순. 같은 초에 찜한 글은 글 번호가 큰 글이 먼저 |
| 글 삭제 | 글을 지우면 그 글의 찜도 모두 지워집니다 |
| 개인정보 | 찜 개수나 누가 찜했는지는 어떤 응답에도 없습니다 |

판정 순서: 401 → 422 → 404 글 없음 → 400 내 글 → (이미 찜했으면 200) → 400 판매 완료 글에 새 찜.

### 찾는 교재 알림

등록 요청: `{"keyword": "자료구조", "max_price": 15000}` (`max_price`는 선택)

| 규칙 | 내용 |
|---|---|
| 키워드 | 앞뒤 공백을 지운 뒤 2~100자. 1글자는 너무 많은 글에 걸려 422 |
| 최대 가격 | 선택, 0~10,000,000 정수(strict). 없으면 가격과 상관없이 알림 |
| 개수 | 사용자당 10개. 11번째는 400 "찾는 교재는 최대 10개까지 등록할 수 있습니다." |
| 중복 | 같은 사람이 대소문자만 다른 같은 키워드를 등록하면 409. 다른 사람끼리는 같은 키워드 가능 |
| 매칭 | 키워드가 글의 **교재명이나 과목명**에 들어 있으면(부분 일치, 대소문자 무시, `%`·`_`는 글자 그대로) 맞음. **글 제목은 보지 않음**. 가격은 `max_price` 이하(포함) |
| 알림 대상 | **판매 중(`ON_SALE`)인 글만**. 내 글과 내가 차단한 사용자의 글은 제외 |
| 알림 시점 | 새 글 작성 때, 그리고 수정으로 교재명·과목명·가격이 바뀌었을 때(새로 맞게 된 사람만). 제목·설명만 바꾼 수정은 다시 매칭하지 않음. 예약 중인 글은 수정으로 조건에 맞아도 알림 없음 |
| 중복 알림 | 한 사람에게 같은 글 알림은 하나(조건 여러 개가 맞으면 먼저 등록한 조건의 키워드로) |
| 이전 글 | 조건을 등록하기 전에 올라온 글은 알림 대상이 아닙니다. 화면의 "지금 있는 글 검색"이 같은 조건의 목록 검색(`?q=…&max_price=…`)을 엽니다 |
| 읽음 | `POST /notifications/read-all`로 모두 읽음. 화면은 목록을 그린 뒤 부릅니다 |
| 차단 | 알림을 받은 뒤 판매자를 차단하면 그 알림은 목록과 안 읽은 수에서 빠집니다 |
| 정리 | 글이 삭제되면 그 글의 알림도 삭제. 조건을 지워도 받은 알림은 남음(키워드 사본). 탈퇴하면 조건과 알림 모두 삭제 |

알림 응답 항목:

```json
{
  "id": 4,
  "keyword": "자료구조",
  "post": { "id": 12, "title": "자료구조 교재 팝니다", "book_title": "C언어로 쉽게 풀어쓴 자료구조",
            "course_name": "자료구조", "price": 15000, "status": "ON_SALE", "thumbnail_url": null },
  "created_at": "2026-11-10T20:43:00",
  "read_at": null
}
```

`post.status`는 알림 당시가 아니라 **지금** 상태입니다(알림 뒤 예약·판매 완료될 수 있음).

### 차단

| 규칙 | 내용 |
|---|---|
| 쪽지 | 둘 중 한 명이라도 상대를 차단했으면 **새 문의 시작과 메시지 전송이 400**입니다(양방향). 이미 있는 대화방은 문의 시작 요청에 그대로 돌려주고, 지난 메시지도 계속 볼 수 있습니다 |
| 안내 문구 | 내가 차단한 경우 "차단한 사용자에게는 쪽지를 보낼 수 없습니다. 차단을 해제하면 다시 보낼 수 있어요.", 상대가 나를 차단한 경우 "이 사용자에게는 쪽지를 보낼 수 없습니다." (누가 차단했는지 말하지 않음) |
| 목록 | 로그인한 사용자의 `GET /posts`에서 **내가 차단한** 사용자의 글만 빠집니다(한쪽 방향). 나를 차단한 사람의 글은 그대로 보입니다. 같은 쿼리 안의 하위 쿼리로 걸러 쿼리 수가 늘지 않습니다 |
| 상세 | 차단한 사용자의 글도 주소로 열 수 있고, `is_seller_blocked: true`로 알려줍니다. 화면은 문의 버튼·하트 대신 "차단 해제"를 보여줍니다 |
| 대화방 정보 | `GET /conversations/{id}`와 문의 시작 응답에 `can_send`(둘 다 차단하지 않았을 때만 `true`)와 `blocked_by_me`가 있습니다. 대화방 목록에는 넣지 않았습니다 |
| 찜 | 차단과 상관없이 그대로 둡니다. 찜 목록에서도 빠지지 않습니다 |
| 중복·해제 | 다시 차단하면 200으로 그대로 성공, 차단하지 않은 사용자를 해제해도 204 |
| 개인정보 | 차단 목록에는 상대의 `id`·`nickname`과 차단 시각만 있습니다. 누가 나를 차단했는지는 어떤 응답에도 없습니다 |

판정 순서: 401 → 404 사용자 없음 → 400 자기 자신.

### 신고

| 규칙 | 내용 |
|---|---|
| 요청 | `{"reason": "FRAUD", "description": "선입금을 요구해요"}`. 사유는 `SPAM`(광고·도배), `FRAUD`(사기 의심), `ABUSE`(욕설·괴롭힘), `INAPPROPRIATE`(부적절한 글·물품), `OTHER`(기타) |
| 설명 | 선택, 앞뒤 공백을 지운 뒤 최대 500자. `OTHER`는 설명이 없으면 422 "기타 사유는 설명을 입력해 주세요." |
| 응답 | 201 `{"id": 1, "created_at": "..."}`. 처리 결과나 대상 정보는 돌려주지 않습니다 |
| 중복 | 같은 사람이 같은 대상(글 또는 사용자)을 두 번 신고하면 409 "이미 신고한 대상입니다." (DB unique 제약). 글 신고와 그 글 작성자 신고는 다른 대상입니다 |
| 횟수 제한 | 한 사람이 **1시간에 5건**(글·사용자 신고 합산)을 넘으면 429 (`Retry-After: 3600`). 중복 신고는 횟수 제한보다 먼저 409로 알려줍니다 |
| 신고 불가 | 본인 글(400), 자기 자신(400) |
| 저장 | 접수된 신고는 `PENDING`이고, 관리자가 처리하면 `RESOLVED`가 됩니다([관리자 신고 처리](#관리자-신고-처리)). 글 신고는 신고 시점의 제목·설명 사본을 남겨, 글이 삭제되어도 관리자가 내용을 확인할 수 있습니다 |
| 비공개 | 신고당한 사람의 어떤 응답에도 신고 여부나 신고자가 드러나지 않습니다(신고 전후 응답이 같은지 테스트로 확인) |

판정 순서: 401 → 403 이용 정지 → 422 → 404 대상 없음 → 400 본인 글·자기 자신 → 409 중복 → 429 횟수 제한.

### 관리자 신고 처리

`/admin`으로 시작하는 API는 모두 관리자만 쓸 수 있습니다. 로그인하지 않았으면 401, 일반 사용자면 403 "관리자만 사용할 수 있습니다."입니다. 이 검사는 신고를 찾기 전에 하므로, 일반 사용자가 신고 번호로 신고가 있는지 알아낼 수 없습니다.

**목록** (`GET /admin/reports?status=PENDING&page=1&size=20`)

| 항목 | 내용 |
|---|---|
| 정렬 | 미처리 먼저, 그 안에서 최신순 |
| `status` | `PENDING`(미처리) / `RESOLVED`(처리됨) / 생략하면 전체 |
| 항목마다 | 사유, 설명, 글 사본, `post_exists`(글이 아직 있는지), 신고자·피신고자 닉네임, 피신고자의 정지 종료 시각, 처리 기록(`resolution`), `other_pending_count`(같은 피신고자의 다른 미처리 신고 수) |
| 개인정보 | 사용자는 `id`·`nickname`만. 이메일은 없습니다 |
| 쿼리 수 | 신고 수와 상관없이 4번(개수, 목록·사용자 JOIN, 남은 글, 피신고자별 미처리 수). 관리자 확인 쿼리 제외 |

**처리** (`POST /admin/reports/{id}/resolve`)

```json
{"action": "SUSPEND", "suspend_days": 7, "note": "선입금 요구 반복", "include_same_user": true}
```

| 조치 | 효과 |
|---|---|
| `DISMISS` (기각) | 조치 없이 처리 완료로 기록 |
| `DELETE_POST` (글 삭제) | 글 신고에만. 작성자 삭제와 같은 규칙으로 지움(찜 삭제, 사진 파일 삭제, 대화방은 남김). 신고의 글 사본은 그대로 남음. **같은 글의 다른 미처리 신고도 자동으로 함께 처리** |
| `SUSPEND` (기간 정지) | `suspend_days` 1~365일 필수. 이미 더 늦게 끝나는 정지가 있으면 그 시각을 유지(정지 기간이 줄지 않음). 관리자는 정지할 수 없음 |

| 규칙 | 내용 |
|---|---|
| 함께 처리 | `include_same_user: true`면 같은 피신고자의 미처리 신고를 모두 같은 조치로 기록하고, 각 기록에 `resolved_with_report_id`를 남깁니다. `DISMISS`·`SUSPEND`에서만 쓸 수 있고 `DELETE_POST`와 함께 보내면 422입니다 |
| 처리 기록 | `action`, `resolution_note`(공백만이면 없음), `resolved_by_id`, `resolved_at`(DB 시간)을 같은 신고 행에 저장 |
| 중복 처리 | 이미 처리된 신고는 409 "이미 처리된 신고입니다." 두 관리자가 동시에 처리해도 `UPDATE … WHERE status='PENDING'`으로 한쪽만 성공합니다 |
| 응답 | `{"action": "SUSPEND", "resolved_ids": [3, 5, 8], "suspended_until": "..."}`. 첫 번호가 요청한 신고, 나머지는 함께 처리된 신고 |
| 400 | 사용자 신고에 글 삭제, 이미 삭제된 글, 관리자 정지, 피신고자 없음(탈퇴) |

판정 순서: 401 → 403 관리자 아님 → 422 → 404 신고 없음 → 409 이미 처리 → 400 조치 규칙 위반.

### 비밀번호 변경·회원 탈퇴

**비밀번호 변경** (`PUT /users/me/password`): `{"current_password": "…", "new_password": "…"}`

| 규칙 | 내용 |
|---|---|
| 현재 비밀번호 | 틀리면 400 "현재 비밀번호가 올바르지 않습니다." 로그인한 상태의 본인 확인 실패라 401(로그인 풀림)이 아니라 400입니다 |
| 새 비밀번호 | 가입과 같은 규칙(8~64자, 72바이트 이하). 같은 검증 코드를 함께 씁니다 |
| 토큰 | 응답으로 새 `access_token`을 줍니다. **변경 전에 발급된 토큰은 모든 기기에서 401**이 됩니다([설계 결정 18번](#18-토큰의-비밀번호-지문-비밀번호를-바꾸면-이전-토큰은-모두-무효)) |
| 정지 중 | 정지 중에도 바꿀 수 있습니다. 유출이 의심되면 바로 바꿔야 하기 때문입니다 |

**회원 탈퇴** (`POST /users/me/withdraw`): `{"password": "…"}`

| 규칙 | 내용 |
|---|---|
| 확인 | 토큰만 훔친 사람이 계정을 지우지 못하게 비밀번호를 다시 받습니다. 틀리면 400 |
| 관리자 | 400 "관리자 계정은 탈퇴할 수 없습니다." 관리자가 모두 탈퇴하면 신고를 처리할 사람이 없어집니다 |
| 결과 | 204. 이후 같은 이메일로 로그인하면 401, 이전 토큰도 401. 같은 이메일·닉네임으로 다시 가입할 수 있습니다 |
| 지우는 것·남기는 것 | [설계 결정 19번](#19-회원-탈퇴-사용자-행은-지우지-않고-익명화)의 표 참고 |
| 탈퇴한 사용자 | 다른 사람 화면에는 "탈퇴한 사용자". 차단·신고 대상으로 찾으면 404 |

판정 순서: 401 → 422 → 400 관리자 → 400 비밀번호 불일치. POST로 둔 이유는 본문이 있는 DELETE를 지원하지 않는 프록시·클라이언트가 있기 때문입니다.

### 이용 정지

| 규칙 | 내용 |
|---|---|
| 로그인 | 비밀번호가 **맞은 뒤에만** 정지 여부를 검사해 403. 비밀번호가 틀리면 평소와 같은 401이라, 비밀번호를 모르는 사람은 정지 사실을 알 수 없습니다 |
| 쓰기 (403) | 글 작성·수정·상태 변경·삭제, 사진 올리기·삭제, 찜·찜 해제, 문의 시작, 메시지 전송, 글·사용자 신고, 찾는 교재 등록. **정지 전에 받은 토큰도** 요청마다 DB의 정지 상태를 확인해 막습니다 |
| 허용 | 모든 조회(목록, 상세, 내 글, 찜 목록, 쪽지함, 지난 대화, 찾는 교재·알림, `/users/me`)와 차단·차단 해제, 찾는 교재 삭제·알림 읽음, 비밀번호 변경, 회원 탈퇴. 정지된 사람도 상황을 파악하고, 원치 않는 연락은 막고, 계정을 지킬 수 있어야 하기 때문입니다 |
| 메시지 | 한국 시간으로 "11월 16일 14:00까지 이용이 정지되었습니다." 해가 다르면 연도도 붙입니다 |
| 자동 해제 | 별도 작업 없이 요청마다 `suspended_until > 지금`을 비교합니다. 종료 시각이 지나면 다음 요청부터 바로 쓸 수 있고, `/users/me`의 `suspended_until`은 `null`이 됩니다 |
| 정지된 사람의 글 | 목록에 그대로 보입니다(숨김은 향후 개선 계획) |

### 에러 응답

모든 에러는 `{"detail": ...}` 형식입니다. 422는 FastAPI 기본 형식(필드별 오류 목록)을 따릅니다.

수정·삭제 API는 다음 순서로 판정하므로, 여러 문제가 겹치면 앞의 에러가 반환됩니다.

```
401 로그인 안 됨 → 403 이용 정지 → 422 요청 형식 오류 → 404 글 없음 → 403 작성자 아님 → 400 상태 규칙 위반
```

쪽지 API도 같은 순서입니다: 401 → 403 이용 정지(전송만) → 422 → 404 대화방 없음 → 403 참여자 아님 → 400 차단 관계 → 429 도배.

이용 정지를 형식 검사(422)보다 먼저 알려주는 이유는, 형식을 고쳐 다시 보내도 어차피 막히기 때문입니다.

## 상태 전이 규칙

```mermaid
stateDiagram-v2
    [*] --> ON_SALE : 글 작성
    ON_SALE --> RESERVED : 예약
    RESERVED --> ON_SALE : 예약 취소
    ON_SALE --> SOLD : 판매 완료
    RESERVED --> SOLD : 판매 완료
    SOLD --> SOLD : 같은 상태 (멱등)
```

| 현재 \ 변경 | ON_SALE | RESERVED | SOLD |
|---|---|---|---|
| **ON_SALE** | 200 (변화 없음) | 200 | 200 |
| **RESERVED** | 200 | 200 (변화 없음) | 200 |
| **SOLD** | **400** | **400** | 200 (변화 없음) |

- **같은 상태로의 변경은 멱등**입니다. 네트워크 오류로 같은 요청을 다시 보내도 에러가 나지 않고, 값이 바뀌지 않으므로 `updated_at`도 그대로입니다.
- **SOLD는 마지막 상태**입니다. 다른 상태로 되돌릴 수 없습니다.
- 상태는 상태 변경 API로만 바꿀 수 있습니다. 작성·수정 요청에 `status`를 넣으면 422입니다.
- SOLD 글은 **내용 수정도 불가(400)**하지만 **삭제는 가능**합니다.
- 규칙은 `app/services/post_service.py`의 `ALLOWED_TRANSITIONS` 표 한 곳에서 관리합니다.
- 상세 화면의 상태 변경 버튼은 `static/js/pages/post.js`에 있는 같은 이름의 표로 정하고, 두 표가 같은지 테스트로 확인합니다([설계 결정 6번](#6-프론트서버-상태-규칙표-일치-테스트)).

## 설계 결정과 트레이드오프

### 1. 계정 존재 여부 노출

| | 내용 |
|---|---|
| **결정** | 로그인 실패는 이메일이 없는 경우와 비밀번호가 틀린 경우 모두 `"이메일 또는 비밀번호가 올바르지 않습니다."`(401)로 응답합니다. 회원가입에서 이메일이 중복되면 `"이미 사용 중인 이메일입니다."`(409)로 응답합니다. |
| **이유** | 로그인 API로 가입된 이메일을 하나씩 확인해 보는 공격을 막습니다. 반면 회원가입에서는 사용자가 왜 가입이 안 되는지 알아야 다음 행동(로그인, 다른 이메일 사용)을 할 수 있습니다. |
| **트레이드오프** | 회원가입 API를 통해서는 특정 이메일의 가입 여부를 알아낼 수 있습니다. 사용성을 위해 이 위험을 감수했고, 요청 횟수 제한과 이메일 인증 방식 가입으로 보완할 계획입니다([향후 개선 계획](#향후-개선-계획)). |

같은 관점에서, 남의 글을 수정·삭제하려 하면 404가 아니라 **403**을 반환합니다. 판매글은 누구나 조회할 수 있는 공개 데이터라서 글이 있다는 사실을 숨길 이유가 없고, 403이 원인을 더 정확하게 알려주기 때문입니다.

### 2. Hard delete

| | 내용 |
|---|---|
| **결정** | 글을 삭제하면 DB 행을 실제로 지우고 204를 반환합니다. 삭제한 글은 다시 조회하면 404입니다. |
| **이유** | 모든 조회 쿼리에 "삭제되지 않은 글" 조건을 붙일 필요가 없어 코드가 단순합니다. 사용자가 지운 내용이 서버에 남지 않습니다. |
| **트레이드오프** | 거래 이력과 분쟁·신고 대응 자료가 사라지고, 실수로 지운 글을 되살릴 수 없습니다. 거래 후기나 신고 기능이 생기면 soft delete를 다시 검토합니다. |

### 3. SOLD 글 수정 불가

| | 내용 |
|---|---|
| **결정** | 판매 완료된 글에 `PATCH /posts/{id}`를 보내면 `"판매 완료된 글은 수정할 수 없습니다."`(400)를 반환합니다. 빈 본문 `{}`도 400입니다. 삭제는 허용합니다. |
| **이유** | 거래가 끝난 뒤 가격이나 책 상태를 바꾸면 거래 당시의 정보와 달라져 분쟁의 원인이 될 수 있습니다. 빈 본문도 막은 것은 "SOLD 글에는 수정 API를 쓸 수 없다"는 규칙을 예외 없이 단순하게 유지하기 위해서입니다. |
| **트레이드오프** | 판매 후 오타 같은 사소한 실수도 고칠 수 없습니다. 판매자가 글을 정리하고 싶을 때를 위해 삭제는 허용했습니다. |

### 4. 토큰을 localStorage에 저장

| | 내용 |
|---|---|
| **결정** | 로그인 토큰을 브라우저의 localStorage에 저장하고, 요청할 때 `Authorization: Bearer` 헤더로 보냅니다. |
| **이유** | 새 탭을 열거나 새로고침해도 로그인이 유지됩니다. 쿠키를 쓰지 않으므로 CSRF 대책이 따로 필요 없고, 서버의 Bearer 인증을 그대로 쓸 수 있습니다. |
| **트레이드오프** | XSS 취약점이 생기면 악성 스크립트가 토큰을 읽어 갈 수 있습니다. 그래서 XSS가 생길 여지 자체를 줄였습니다. 화면에 값을 넣을 때는 항상 `textContent`와 `createElement`만 쓰고, `static/js`의 모든 파일에 `innerHTML`, `outerHTML`, `insertAdjacentHTML`이 없는지 테스트로 검사합니다. 근본적인 해결책은 HttpOnly 쿠키입니다([향후 개선 계획](#향후-개선-계획)). |

### 5. 로그아웃은 토큰 삭제만

| | 내용 |
|---|---|
| **결정** | 로그아웃하면 브라우저에 저장된 토큰만 지웁니다. 서버에는 로그아웃 API가 없습니다. |
| **이유** | JWT는 서버가 로그인 상태를 저장하지 않는 방식이라, 토큰을 지우면 그 브라우저에서는 더 이상 인증 요청을 보낼 수 없습니다. |
| **한계** | 서버가 이미 발급한 토큰을 무효화할 수 없습니다. 토큰이 유출되면 로그아웃한 뒤에도 만료 시간(기본 60분)까지는 그 토큰으로 요청할 수 있습니다. 유출이 의심되어 **비밀번호를 바꾸는 경우에는** 토큰의 비밀번호 지문으로 이전 토큰을 모두 끊습니다([설계 결정 18번](#18-토큰의-비밀번호-지문-비밀번호를-바꾸면-이전-토큰은-모두-무효)). 일반 로그아웃은 리프레시 토큰과 짧은 액세스 토큰 만료로 보완할 계획입니다. |

### 6. 프론트·서버 상태 규칙표 일치 테스트

| | 내용 |
|---|---|
| **결정** | 상세 화면은 상태 변경 버튼을 고르기 위해 전이표(`ALLOWED_TRANSITIONS`)를 따로 갖고 있습니다. 테스트가 `post.js`에서 이 표를 읽어 서버의 표와 같은지 비교합니다. |
| **이유** | 서버 규칙만 바뀌고 프론트를 놓치면, 누르면 400이 나는 버튼이 보이거나 필요한 버튼이 사라집니다. 두 표가 어긋나면 테스트가 바로 실패하므로 배포 전에 알 수 있습니다. |
| **트레이드오프** | JS 파일을 정규식으로 읽으므로 상수의 이름이나 모양이 바뀌면 테스트가 실패합니다. 비교 없이 조용히 통과하지 않도록 의도한 동작입니다. 서버가 표를 API로 내려주는 방식도 있지만, 화면마다 요청이 하나 늘어납니다. |

### 7. 오픈채팅 링크는 로그인한 사용자에게만

| | |
|---|---|
| **결정** | 상세 API는 로그인 없이 볼 수 있게 두되, 토큰이 없거나 잘못·만료된 요청이면 `open_chat_url`만 `null`로 비워 응답합니다. 화면은 "로그인하면 연락 방법을 볼 수 있어요"와 로그인 링크(돌아올 주소 포함)를 보여줍니다. |
| **이유** | 링크를 아무나 볼 수 있으면 크롤러가 모아 스팸을 보낼 수 있습니다. 화면에서만 숨기면 API로 바로 보이므로 서버가 응답에서 뺍니다. 오래된 토큰 때문에 글 자체를 못 보는 일이 없도록 401 대신 링크만 비웁니다. |
| **트레이드오프** | 같은 주소인데 로그인 여부에 따라 응답이 달라서, 응답을 캐시할 때 주의해야 합니다. 또 지금은 아무 이메일로나 가입할 수 있어 "로그인한 사용자"가 곧 "같은 학교 학생"은 아닙니다([향후 개선 계획 1번](#향후-개선-계획)). |

링크 형식은 서버가 1차로 검사하고(422), 화면도 `https://open.kakao.com/`으로 시작할 때만 링크를 만들어 `javascript:` 같은 주소가 `href`에 들어가지 않게 한 번 더 막습니다. 링크는 `target="_blank"`와 `rel="noopener noreferrer"`로 열어, 열린 페이지가 원래 탭을 조작하지 못하게 합니다.

### 8. 쪽지: 글이 삭제되어도 대화방은 남긴다

| | |
|---|---|
| **결정** | 글을 삭제하면 대화방의 `post_id`만 `NULL`로 바꾸고 대화방과 메시지는 남깁니다. 목록에서는 `post: null`로 보입니다. 대화방에 `seller_id`를 따로 저장해, 글이 없어도 권한 검사가 됩니다. |
| **이유** | 함께 지우면 구매자가 예고 없이 대화를 잃고, 판매자가 글을 지워 대화 기록을 없앨 수 있습니다. 거래 분쟁 때 기록이 필요합니다. |
| **트레이드오프** | FK에 `ondelete="SET NULL"`을 두었지만 SQLite는 FK를 검사하지 않아서, 글 삭제 서비스에서 직접 `NULL`로 바꿉니다. 글 제목은 남지 않으므로, 삭제된 글의 대화방은 상대 닉네임으로만 구분됩니다. |

### 9. 쪽지: 커서 페이지네이션, 조회 시 읽음 처리, DB 기준 도배 방지

| | |
|---|---|
| **커서** | 쪽지는 새 메시지가 계속 추가되므로, 페이지 번호 방식이면 페이지 경계가 밀려 중복·누락이 생깁니다. 메시지 id를 기준으로 이전(`before_id`)이나 이후(`after_id`)를 가져옵니다. |
| **읽음 처리** | 메시지 목록 GET이 읽음 처리까지 합니다. GET에 부수 효과가 생기는 대신, 화면이 별도 요청 없이 "열면 읽음"을 구현할 수 있습니다. 응답 페이지 밖의 안 읽은 메시지도 함께 읽음 처리해 규칙을 단순하게 했습니다. |
| **도배 방지** | 최근 10초 동안 보낸 메시지 수를 DB에서 셉니다. 새 라이브러리가 필요 없고, 서버를 재시작하거나 여러 대로 늘려도 같은 기준으로 동작합니다. 앱 서버 시간 대신 DB 시간을 기준으로 비교합니다. 기준은 `conversation_service.MESSAGE_RATE_LIMIT` 하나로 바꿀 수 있습니다. 메시지마다 쿼리가 한 번 늘어나며, 트래픽이 커지면 Redis 같은 저장소로 옮기는 것을 검토합니다. |
| **목록 정렬** | 대화방에 `last_message_at`과 `last_message_id`를 따로 저장해, 하위 쿼리 없이 인덱스로 최신 메시지순 정렬을 합니다. SQLite는 시간을 초 단위로 저장하므로 같은 초의 메시지는 `last_message_id`로 순서를 정합니다. 목록 요청 하나에 쿼리는 방 수와 상관없이 5번입니다(로그인 사용자, 개수, 방·글·상대 JOIN, 마지막 메시지, 안 읽은 개수). |

### 10. 쪽지 화면: 폴링으로 새 메시지 확인

| | |
|---|---|
| **결정** | 대화 화면은 5초마다 `after_id`로 새 메시지를 확인합니다. `setInterval` 대신 응답이 온 뒤 다음 요청을 예약해 요청이 겹치지 않게 하고, 탭이 숨겨지면 멈췄다가 다시 보이면 바로 확인합니다. 연결이 불안정하면 15초 간격으로 늦춥니다. |
| **이유** | 지금 구조(동기 FastAPI + SQLite)에 서버 변경 없이 붙일 수 있고, 테스트하기 쉽습니다. 메시지는 id로 모아 두어 전송 응답과 폴링이 같은 메시지를 줘도 한 번만 그립니다. |
| **트레이드오프** | 새 메시지가 최대 5초 늦게 보이고, 대화 화면을 연 사람마다 5초에 요청 1번이 생깁니다. 사용자가 늘면 WebSocket으로 바꿀 계획입니다([향후 개선 계획](#향후-개선-계획)). |

그 밖의 화면 처리:
- 맨 아래를 보고 있을 때만 새 메시지를 따라 내려가고, 위쪽 이전 대화를 읽는 중이면 위치를 두고 "새 메시지 ↓" 버튼을 띄웁니다.
- 이전 메시지를 위에 붙인 뒤 늘어난 높이만큼 스크롤을 보정해, 보던 위치가 튀지 않게 합니다.
- Enter는 보내기, Shift+Enter는 줄바꿈입니다. 한글 조합 중인 Enter(`isComposing`)는 무시해 마지막 글자가 두 번 가지 않게 하고, 터치 화면에서는 Enter를 줄바꿈으로 둡니다.
- 429를 받으면 서버 메시지와 `Retry-After` 초를 보여주고, 그동안 보내기 버튼을 잠그며 입력한 내용은 남겨 둡니다.
- 내가 보낸 메시지의 "읽음" 표시는 넣지 않았습니다. `after_id` 폴링은 새 메시지만 받아 예전 메시지의 `read_at` 변화를 알 수 없어서, 화면을 연 시점 값만 보여주면 틀린 "안 읽음"이 남기 때문입니다.

### 11. 사진: 다시 인코딩으로 메타데이터(GPS) 제거

| | |
|---|---|
| **결정** | 올라온 파일을 그대로 저장하지 않고, Pillow로 픽셀을 읽어 **WebP로 새로 인코딩**합니다. 인코딩 전에 EXIF·XMP·ICC 같은 부가 정보(`info`)를 비워, 새 파일에는 픽셀만 남습니다. |
| **이유** | 휴대폰 사진의 EXIF에는 **찍은 위치(GPS 위도·경도)**, 시각, 기기 정보가 들어 있습니다. 기숙사나 자취방에서 교재를 찍어 올리면 사는 곳이 그대로 공개됩니다. 사용자가 이를 알고 지우기를 기대할 수 없으므로 서버가 지웁니다. 또 원본 바이트를 그대로 저장하면 이미지 뒤에 덧붙인 스크립트나 다른 파일(폴리글랏 파일)도 함께 저장·배포되는데, 새로 인코딩하면 실제 픽셀 말고는 아무것도 따라가지 않습니다. 형식이 하나(WebP)로 통일되고 크기도 줄어 목록 화면이 가벼워집니다. |
| **트레이드오프** | 업로드마다 디코딩·인코딩에 CPU를 씁니다. 그래서 크기·해상도 제한과 업로드 횟수 제한(10분 20장)을 두었습니다. 다시 압축하므로 원본보다 화질이 조금 떨어지고(품질 85), 색 프로필(ICC)을 버려 일부 사진의 색감이 약간 달라질 수 있습니다. 회전 정보도 메타데이터라서, 지우기 전에 픽셀을 실제로 돌려 둡니다. 테스트가 GPS를 넣은 JPEG을 올린 뒤 저장된 파일에 EXIF가 없는지 확인합니다. |

### 12. 사진: 전용 경로로 이미지 제공

| | |
|---|---|
| **결정** | 사진은 `static/` 밖의 `UPLOAD_DIR`에 저장하고, `GET /images/{filename}` 한 경로로만 내려줍니다. 파일 이름은 서버가 만든 `32자리 16진수(_thumb).webp` 형식만 받고, 그 밖의 이름은 디스크를 찾아보지도 않고 404입니다. 응답은 항상 `Content-Type: image/webp`와 `X-Content-Type-Options: nosniff`를 붙입니다. |
| **이유** | 업로드 폴더를 `StaticFiles`로 열면 확장자에 따라 형식이 정해지고, 폴더에 무엇이 들어가든 그대로 배포됩니다. 전용 경로는 ① 정해진 이름 형식만 열어 `../.env` 같은 **경로 조작이 원천적으로 통하지 않고**, ② 브라우저가 내용을 HTML·스크립트로 짐작해 실행하지 않도록(`nosniff`) **형식을 고정**하며, ③ 사용자가 올린 파일과 앱의 화면 파일(`static/`)이 섞이지 않게 합니다. 이름은 추측할 수 없는 임의 값이라, 남의 사진 주소를 번호로 훑어볼 수도 없습니다. 같은 이름에 다른 내용이 들어가는 일이 없으므로 1년 캐시(`immutable`)를 걸었습니다. |
| **트레이드오프** | 파일 전송을 앱 서버(파이썬)가 맡으므로 nginx나 CDN이 바로 주는 것보다 느립니다. 사용자가 늘면 같은 규칙(이름 형식, 헤더)을 유지한 채 오브젝트 스토리지 + CDN으로 옮길 계획입니다. 사진 자체는 로그인 없이 볼 수 있습니다(판매글처럼 공개 정보로 봄). |

### 13. 찜: 토글 대신 POST·DELETE, 찜 여부는 목록 응답에

| | |
|---|---|
| **결정** | 찜 추가는 `POST`(이미 있으면 200), 해제는 `DELETE`(없어도 204)로 나눴습니다. 하트 상태는 목록·상세 응답의 `is_wishlisted`로 내려주고, 로그인한 사용자의 목록 요청에서만 "이 페이지 글 중 내가 찜한 글"을 쿼리 한 번으로 찾습니다. |
| **이유** | 토글 API는 더블클릭이나 네트워크 재시도 때 상태가 거꾸로 뒤집힙니다. POST·DELETE는 같은 요청을 몇 번 보내도 결과가 같아, 화면이 서버 상태를 믿고 하트를 그릴 수 있습니다. 찜 여부를 응답에 넣으면 화면마다 "내 찜 id 전체"를 따로 받아오는 요청이 필요 없고, 찜이 많아져도 응답 크기가 그대로입니다. |
| **트레이드오프** | 로그인한 목록 요청은 쿼리가 1번 늘어 3번(개수 + 목록 + 찜 여부, 로그인 사용자 확인 제외)입니다. 비로그인 목록은 2번 그대로입니다. 같은 주소인데 로그인 여부에 따라 응답이 달라 캐시할 때 주의해야 합니다(오픈채팅 링크와 같은 사정). |

카드는 전체가 링크(`<a>`)라 그 안에 버튼을 넣으면 HTML 규칙에 어긋나고 화면 낭독기·키보드 동작이 꼬입니다. 그래서 하트 버튼은 링크 옆(같은 `<li>` 안)에 두고 CSS로 사진 오른쪽 위에 겹쳤습니다. 버튼 이름에 글 제목을 넣어("자료구조 교재 팝니다 찜하기") 여러 카드 중 어떤 글의 버튼인지 알 수 있게 했습니다.

### 14. 신고·차단: 저장만 하는 신고, 상대에게 알리지 않는 차단

| | |
|---|---|
| **결정** | 차단은 쪽지를 **양방향**으로 막고, 목록에서는 **내가 차단한** 사람의 글만 숨깁니다. 상대가 나를 차단한 경우 안내 문구에 "차단"이라는 말을 쓰지 않습니다. 신고는 DB에 저장만 하고, 같은 대상 중복을 409로 막고 1시간 5건으로 제한합니다. 글 신고는 제목·설명 사본을 함께 저장합니다. |
| **이유** | 쪽지를 한쪽만 막으면 차단당한 사람이 계속 메시지를 보낼 수 있어 차단의 의미가 없습니다. 반대로 "상대가 나를 차단했다"를 알려주면 보복이나 다른 계정으로 접근하는 계기가 되므로 알리지 않습니다. 신고 사본은 신고당한 사람이 글을 지워 증거를 없애는 것을 막습니다. 중복 방지와 횟수 제한은 신고를 괴롭힘 수단으로 쓰거나 관리자 확인 목록을 도배하는 것을 줄입니다. |
| **트레이드오프** | 상대가 나를 차단해도 그 사람의 글은 내 목록에 보이고 상세도 열 수 있습니다. 문의를 누르면 400 안내가 나와, 눈치 빠른 사용자는 차단을 짐작할 수 있습니다. 완전히 숨기려면 상대 글까지 감춰야 해서 오히려 차단 사실이 더 드러나므로 이 정도로 두었습니다. 신고 사본은 개인정보가 담긴 글이 지워진 뒤에도 남으므로, 관리자 화면을 만들 때 보관 기간을 정해야 합니다. |

외래 키 규칙: 차단(`user_blocks`)은 사용자가 탈퇴하면 함께 지워지도록 `CASCADE`, 신고(`reports`)는 기록을 남기도록 `SET NULL`로 정했습니다. 다만 SQLite는 기본 설정에서 외래 키 동작을 실행하지 않고, 탈퇴는 사용자 행을 지우지 않으므로([설계 결정 19번](#19-회원-탈퇴-사용자-행은-지우지-않고-익명화)) 차단 행 삭제와 신고의 사용자 id 비우기는 `account_service.withdraw`가 직접 합니다.

### 15. 관리자: CLI로만 지정, 라우터 단위 권한 검사, 정지는 요청마다 확인

| | |
|---|---|
| **결정** | 관리자는 `users.role` 컬럼 하나로 구분하고, 서버의 CLI(`python -m app.cli make-admin`)로만 지정합니다. 가입 요청에 `role` 같은 모르는 필드를 넣으면 422입니다. 관리자 검사는 `/admin` 라우터 전체에 의존성으로 걸고, 테스트가 앱에서 `/admin`으로 시작하는 **모든 경로를 자동으로 찾아** 401·403을 확인합니다. 정지는 토큰에 넣지 않고 쓰기 요청마다 DB의 `suspended_until`을 확인합니다. |
| **이유** | 관리자를 만드는 API가 있으면 그 API 자체가 공격 대상이 됩니다. 서버에 접속할 수 있는 사람만 지정하게 하면 웹으로는 관리자가 될 길이 없습니다. 가입에서 모르는 필드를 조용히 무시하면 `role`이 통했는지 알 수 없으므로 거절해 분명히 합니다. 권한 검사를 API마다 적으면 새 API에서 빠뜨리기 쉬워 라우터 단위로 걸었고, 빠뜨려도 테스트가 실패합니다. 정지를 토큰에 넣으면 이미 발급된 토큰이 만료될 때까지 정지가 적용되지 않습니다. |
| **트레이드오프** | 관리자 지정·해제에 서버 접속이 필요합니다(해제 명령은 아직 없음). 가입의 `extra="forbid"`로 예전에는 무시되던 모든 추가 필드가 422가 됩니다(가입 화면은 정해진 3개 필드만 보냄). 쓰기 요청은 이미 로그인 사용자를 DB에서 읽고 있어 정지 확인에 쿼리가 늘지 않습니다. 정지 기록은 마지막 종료 시각만 남고 이력은 없습니다. |

관리 화면은 처리 전에 무엇이 바뀌는지(지울 글 제목, 정지 일수, 함께 처리할 건수)를 확인 창으로 보여주고, 처리 뒤에는 함께 처리된 카드도 바뀌므로 목록을 서버에서 다시 받아 그립니다. 다른 관리자가 먼저 처리했으면(409) 카드 안에 서버 메시지를 보여줍니다.

### 16. 토큰이 탭끼리 공유되어 생기는 문제와 대응

| | |
|---|---|
| **문제** | 토큰은 localStorage에 있어 같은 브라우저의 모든 탭이 같은 값을 봅니다. A 계정으로 대화 화면을 열어 둔 채 다른 탭에서 B 계정으로 로그인하면, 열려 있던 대화 화면이 모르는 사이에 B의 토큰으로 폴링·전송합니다. 서버는 B 기준으로 `is_mine`을 계산하므로 **상대 메시지가 내 말풍선으로 그려지고**, 그 화면에서 보낸 메시지는 **B 이름으로 전송**됩니다. |
| **대응** | 대화 화면은 열 때의 토큰을 기억하고(`sessionToken`), 요청 전후마다 지금 토큰과 비교합니다. 다른 탭의 변경은 `storage` 이벤트(`token.js`의 `onTokenChangedInOtherTab`)로 바로 알아챕니다. 다르면 폴링과 전송을 멈추고 "다른 탭에서 로그인 상태가 바뀌어 이 대화를 멈췄습니다. 새로고침하면 지금 로그인한 계정으로 다시 열립니다."를 보여줍니다. 요청 중에 바뀌었으면 받은 응답도 그리지 않습니다. |
| **트레이드오프** | 계속 요청을 보내는 대화 화면만 막았습니다. 다른 화면은 한 번 그린 뒤 버튼을 누를 때만 요청하므로, 다른 탭에서 계정을 바꾸면 그 화면의 다음 동작(찜, 글 수정 등)은 바뀐 계정으로 처리됩니다. 권한 검사는 서버가 하므로 남의 글을 고칠 수는 없지만, 헤더의 닉네임은 새로고침 전까지 예전 계정으로 보일 수 있습니다. 탭마다 다른 계정을 쓰려면 sessionStorage를 써야 하는데, 그러면 새 탭마다 다시 로그인해야 해서 고르지 않았습니다. |

### 17. PWA 캐시는 정적 파일만

| | |
|---|---|
| **결정** | 서비스 워커는 `/static/` 아래 정적 파일만 캐시하고, API 응답과 사진(`/images`)은 캐시하지 않습니다. `/static/` 밖의 요청은 아예 가로채지 않습니다. HTML·CSS·JS는 네트워크를 먼저 쓰고, 글꼴·그림만 캐시를 먼저 씁니다. 캐시 이름에 버전 키를 넣어 새 버전이 켜지면 이전 캐시를 지웁니다. |
| **이유** | 글 상태·쪽지·찜은 늘 최신이어야 하는데, API를 캐시하면 팔린 글이 판매 중으로 보이거나 새 쪽지가 안 보일 수 있습니다. 또 API 응답에는 로그인한 사용자의 쪽지 같은 개인 데이터가 있어, 기기 캐시에 남으면 로그아웃한 뒤나 같은 기기를 쓰는 다른 사람에게 보일 수 있습니다. 사진은 글이 삭제되면 서버에서도 지우므로 캐시에 남기지 않습니다. 화면 코드를 네트워크 먼저로 둔 것은, 캐시 먼저면 배포 직후 옛 JS와 새 API가 섞여 동작할 수 있기 때문입니다. |
| **트레이드오프** | 오프라인에서는 한 번 본 화면의 틀만 열리고 글·쪽지는 보이지 않습니다(목록이 "서버에 연결할 수 없습니다"를 보여줌). 화면 코드를 네트워크 먼저로 두어 캐시가 첫 화면 속도를 크게 줄이지는 못합니다. 글꼴·아이콘을 바꾸고 버전을 올리지 않으면 사용자 기기에 옛 파일이 남습니다. |

### 18. 토큰의 비밀번호 지문: 비밀번호를 바꾸면 이전 토큰은 모두 무효

| | |
|---|---|
| **결정** | 액세스 토큰에 `pwd` 클레임으로 **비밀번호 지문**(현재 `password_hash`의 SHA-256 앞 16자)을 넣습니다. 요청마다 로그인 사용자를 DB에서 읽을 때 지금 해시로 지문을 다시 계산해, 토큰의 값과 다르면 401입니다. 비밀번호를 바꾸면 해시가 바뀌므로 **그 전에 발급된 토큰은 모든 기기에서 즉시 무효**가 되고, 변경 응답으로 받은 새 토큰만 쓸 수 있습니다. 지문이 없는 토큰(이 기능 전에 발급)도 거절합니다. |
| **이유** | 비밀번호를 바꾸는 흔한 이유는 유출 의심입니다. 이미 빼앗긴 토큰이 만료(60분)까지 살아 있으면 비밀번호를 바꾼 의미가 줄어듭니다. 그래서 [설계 결정 5번](#5-로그아웃은-토큰-삭제만)의 한계("서버가 발급한 토큰을 무효화할 수 없음")를 **비밀번호 변경 상황에서는** 해결했습니다. 토큰 차단 목록 테이블이나 `users`의 `token_version` 컬럼 없이 되는 가장 단순한 방법입니다. 마이그레이션 도구가 없어 기존 테이블에 컬럼을 더하면 수동 `ALTER`가 필요한데, 이 방법은 스키마를 바꾸지 않습니다. 사용자 행은 원래 요청마다 읽으므로 쿼리도 늘지 않습니다. bcrypt는 매번 새 솔트를 쓰므로 같은 비밀번호로 "바꿔도" 지문이 바뀌고, 탈퇴도 해시를 바꾸므로 탈퇴한 계정의 토큰이 함께 무효가 됩니다. |
| **트레이드오프** | 다른 기기는 모두 로그아웃되며 "이 기기만 끊기" 같은 선택은 없습니다. 일반 로그아웃은 여전히 토큰을 끊지 못합니다. 지문은 해시의 해시 일부라 토큰을 열어 봐도 비밀번호를 알 수 없지만, 토큰이 조금 길어집니다. 이 기능을 배포하면 이미 로그인해 있던 사용자는 한 번 다시 로그인해야 합니다. 요청마다 SHA-256을 한 번 계산합니다(bcrypt가 아니라 비용은 작음). |

### 19. 회원 탈퇴: 사용자 행은 지우지 않고 익명화

| | |
|---|---|
| **결정** | 탈퇴하면 `users` 행을 지우지 않고 개인정보를 지운 "탈퇴 표시"로 바꿉니다. 이메일은 `withdrawn-(임의 값)@withdrawn.invalid`, 닉네임은 `withdrawn-(임의 값)`, `password_hash`는 bcrypt 형식이 아닌 `!withdrawn`(어떤 비밀번호와도 일치하지 않음), 정지 시각은 비웁니다. 다른 사람에게는 닉네임 대신 "탈퇴한 사용자"로 보여주고, 사용자 조회(`get_user_by_id`)는 탈퇴한 계정을 없는 사람으로 돌려줘 인증은 401, 차단·신고 대상은 404가 됩니다. |
| **이유** | 대화방의 `buyer_id`·`seller_id`와 메시지의 `sender_id`가 `users`를 **NOT NULL 외래 키**로 가리킵니다. 행을 지우면 외래 키를 실제로 검사하는 **PostgreSQL(운영)에서 삭제가 실패**합니다. SQLite(개발·테스트)는 기본 설정에서 외래 키를 검사하지 않아 이 문제를 놓치기 쉽습니다. 컬럼을 NULL 허용 + `SET NULL`로 바꾸려면 기존 테이블 구조를 바꿔야 하는데 `create_all`은 반영하지 않습니다. 익명화는 스키마를 바꾸지 않고 개발과 운영에서 똑같이 동작합니다. 대화 기록은 남은 사람의 거래 분쟁 대비 기록이라 지우지 않습니다. |
| **트레이드오프** | 탈퇴한 사용자 행이 계속 쌓입니다(개인정보는 없음). 탈퇴 여부를 특별한 해시 값으로 판단해 `deleted_at` 같은 컬럼보다 덜 명시적입니다. Alembic을 도입하면 컬럼으로 옮길 후보입니다. 내가 보낸 쪽지 내용은 상대 화면에 남습니다(탈퇴 화면 안내 문구에 적어 둠). |

| 데이터 | 탈퇴 후 |
|---|---|
| 사용자 행 | **남음** (이메일·닉네임·비밀번호를 지운 탈퇴 표시. 같은 이메일·닉네임으로 다시 가입 가능) |
| 내 판매글 | **삭제** (글 삭제와 같은 규칙: 다른 사람의 찜과 찾는 교재 알림도 삭제, 대화방의 글 연결은 끊음) |
| 사진 파일 | **삭제** (DB 커밋 뒤에 디스크에서 지움) |
| 내 찜 | **삭제** |
| 차단 (내가 한 것, 나를 한 것) | **삭제** |
| 찾는 교재 조건과 받은 알림 | **삭제** |
| 쪽지 대화방·메시지 | **남음** (상대 화면에 "탈퇴한 사용자", 새 메시지 전송 불가) |
| 신고 기록 | **남음** (내가 한 신고·나를 대상으로 한 신고 모두. 신고자·피신고자 id만 비우고, 관리 화면에는 "(탈퇴한 사용자)") |
| 발급된 토큰 | **무효** (비밀번호 해시가 바뀌어 지문이 달라짐, [18번](#18-토큰의-비밀번호-지문-비밀번호를-바꾸면-이전-토큰은-모두-무효)) |

SQLite는 외래 키 동작(`CASCADE`, `SET NULL`)을 실행하지 않으므로 위 정리는 모두 `account_service.withdraw`가 한 트랜잭션 안에서 직접 합니다. 관리자는 탈퇴할 수 없습니다(신고를 처리할 사람이 사라지지 않게).

### 20. 찾는 교재 알림: 검색 SQL을 재사용하지 않는 역방향 매칭

| | |
|---|---|
| **결정** | 새 글이 저장될 때(또는 수정으로 교재명·과목명·가격이 바뀔 때) 가격·본인 글·차단·이미 받은 알림 조건은 **SQL로 먼저 좁히고**, 남은 조건의 키워드만 파이썬에서 `keyword.lower() in 교재명·과목명.lower()`로 확인합니다. 글을 `flush`해 번호를 받은 뒤 **같은 트랜잭션에서** 알림 행을 만들고 한 번에 커밋합니다. 알림은 **판매 중(`ON_SALE`)인 글에만** 만듭니다. |
| **이유** | 검색은 "키워드 하나 → 그 키워드를 포함한 글들"이라 글 컬럼에 `LIKE '%키워드%'`를 겁니다. 알림은 방향이 반대인 "글 하나 → 이 글에 들어 있는 키워드들"입니다. SQL로 하려면 저장된 키워드 컬럼을 패턴으로 써야 하고(`:교재명 LIKE '%' || keyword || '%'`), 키워드 안의 `%`·`_`·`\`를 SQL 안에서 이스케이프해야 해 DB마다 문법이 갈리고 읽기 어렵습니다. 파이썬 문자열 비교에는 와일드카드가 없어 이스케이프가 필요 없습니다. 후보는 SQL에서 이미 줄였고 사용자당 10개라 비교할 수가 적습니다. 한 트랜잭션이라 글만 저장되고 알림이 빠지거나 그 반대가 생기지 않고, 백그라운드 작업이 없어 테스트가 단순합니다. 예약 중·판매 완료 글은 지금 살 수 없어 알림이 헛걸음이 되므로 판매 중인 글만 알립니다. |
| **같은 결과 보장** | 매칭 의미가 검색(SQL)과 알림(파이썬) 두 곳에 있으므로, 검색 테스트와 같은 성질(부분 일치, 영어 대소문자 무시, `%`·`_`가 와일드카드로 동작하지 않음, 가격 경계 포함)을 알림 테스트에서도 같은 입력으로 확인합니다(`test_alert_notifications.py`). 한쪽 규칙만 바뀌면 테스트가 실패합니다. |
| **트레이드오프** | 글 작성 요청 시간에 매칭이 들어갑니다. 조건이 아주 많아지면 작업 큐로 옮겨야 합니다. 조건을 등록하기 전에 올라온 글은 알리지 않습니다("지금 있는 글 검색" 링크로 보완). 예약 중에서 판매 중으로 돌아온 글은 다시 알리지 않습니다. SQLite의 `lower()`는 ASCII만 바꾸고 파이썬은 유니코드 전체를 바꿔, 일부 라틴 문자(É 등)에서 결과가 다를 수 있습니다(한글은 대소문자가 없어 영향 없음). 같은 글을 동시에 두 번 수정하면 unique 제약으로 한 요청이 실패할 수 있어 다시 시도해야 합니다. |

중복 알림은 `(user_id, post_id)` unique 제약과 "이미 이 글로 알림을 받은 사람 제외" 조건으로 막습니다. 그래서 글을 수정할 때 다시 매칭해도 **새로 조건에 맞게 된 사람만** 알림을 받습니다. 글 제목은 매칭하지 않습니다. "운영체제 말고 자료구조 팝니다" 같은 제목 때문에 엉뚱한 알림이 가지 않게 하기 위해서입니다.

### 그 밖의 결정

| 결정 | 이유 |
|---|---|
| 가입·작성·수정·신고 처리 요청에서 모르는 필드는 422 (`extra="forbid"`) | `status`나 `role`을 보냈는데 조용히 무시되면 클라이언트가 실수를 알 수 없습니다 |
| 가격은 strict 정수 (`"15000"`, `1500.5` 거절) | 문자열이나 실수가 자동 변환되며 생기는 오해를 막습니다 |
| PATCH는 보낸 필드만 반영 (`exclude_unset`) | 보내지 않은 필드를 null로 덮어쓰지 않습니다. 필수 필드에 명시적으로 null을 보내면 422 |
| 최신순 정렬은 `created_at DESC, id DESC` | SQLite는 시간을 초 단위로 저장해 같은 초에 쓴 글의 순서가 섞일 수 있습니다 |
| 목록에서 판매자를 JOIN으로 함께 조회 | 글마다 판매자 조회 쿼리가 나가는 N+1 문제를 막습니다. 목록 요청 하나에 쿼리 2번(개수 + 목록) |
| 목록 썸네일은 글 SELECT 안의 하위 쿼리로 | 첫 사진의 썸네일 이름을 `column_property`(스칼라 하위 쿼리)로 함께 읽어, 사진이 생겨도 목록 쿼리가 2번 그대로입니다 |
| 사진 업로드는 한 요청에 한 장 | 한 장이 실패해도 나머지는 저장되고, 어떤 사진이 왜 실패했는지 화면이 정확히 알려줄 수 있습니다 |
| 사진 파일을 먼저 쓰고 DB를 커밋 | DB 기록이 실패하면 방금 쓴 파일을 지워 주인 없는 파일을 남기지 않습니다. 삭제는 반대로 DB를 먼저 커밋한 뒤 파일을 지웁니다 |
| 검색어의 `%`, `_`, `\` 이스케이프 | `q=100%`가 "1000원"까지 찾는 식으로 와일드카드처럼 동작하는 것을 막습니다 |
| 비밀번호를 글자 수와 바이트 수로 함께 제한 | bcrypt는 72바이트까지만 처리하는데, 한글은 한 글자가 3바이트라 64자 제한만으로는 부족합니다 |
| JWT 검증 시 알고리즘을 HS256으로 고정 | `alg: none`처럼 헤더의 알고리즘을 바꿔치기하는 공격을 막습니다 |

## 테스트

```bash
# Windows
venv\Scripts\python -m pytest -q
# macOS / Linux
python -m pytest -q

# 한 프로세스로 실행 (디버깅할 때, print·breakpoint 확인용)
python -m pytest -q -n 0
```

- **병렬 실행이 기본**입니다. `pytest.ini`의 `-n auto`로 CPU 코어 수만큼 워커 프로세스를 띄워 나눠 실행합니다(pytest-xdist).
  - 인메모리 SQLite는 프로세스 메모리 안에만 있어 워커마다 DB가 따로 생기고, 사진 폴더도 테스트마다(워커 이름이 들어간) 다른 임시 폴더라 워커끼리 섞이지 않습니다. 이 격리는 `test_test_settings.py`에서 확인합니다.
- **테스트에서만 bcrypt 비용을 4로 낮춥니다**(`conftest.py`가 `BCRYPT_ROUNDS=4`를 넣음). 가입·로그인을 거치는 테스트가 많아 기본값 12로는 해시 계산이 시간 대부분을 차지했습니다. 운영 기본값은 12 그대로이고, 검증은 해시에 적힌 비용을 따르므로 이 값을 바꿔도 기존 사용자의 로그인에는 영향이 없습니다.
- 실행 시간(8코어 PC): 기존 약 5분 43초(580개) → bcrypt 비용 4로 약 29초(589개) → 병렬 실행까지 약 15~22초. 지금 778개는 약 18~20초입니다.
- `.env` 없이도 실행됩니다. 테스트용 `SECRET_KEY`와 **인메모리 SQLite**를 쓰므로 개발용 `dev.db`를 건드리지 않습니다.
- `dependency_overrides`로 앱의 DB 세션을 테스트 세션으로 바꾸고, 테스트마다 테이블을 새로 만들어 테스트끼리 데이터가 섞이지 않습니다.
- 실제 회원가입·로그인 API로 토큰을 받아 사용하므로, 인증 흐름 전체가 함께 검증됩니다.
- 사진 폴더는 테스트마다 임시 폴더로 바꿔 끼우므로(`conftest.py`의 `image_dir`), 프로젝트의 `uploads/`에 파일이 남지 않습니다.

**27개 파일, 778개 테스트 케이스** (`pytest.mark.parametrize`로 펼쳐진 개수 기준, `pytest --collect-only`로 센 값)

| 파일 | 케이스 수 | 범위 |
|---|---|---|
| `test_health.py` | 1 | 서버 상태 확인 |
| `test_auth_signup.py` | 19 | 가입 성공, bcrypt 해시 저장, 이메일 대소문자 통일, 중복 409, 비밀번호 길이·72바이트 경계, 입력 검증 |
| `test_auth_login.py` | 18 | 로그인 성공, 없는 이메일과 틀린 비밀번호의 같은 401, 토큰 만료 시간, 토큰 만료·변조·`alg: none` 거절 |
| `test_account.py` | 10 | 비밀번호 변경: 현재 비밀번호 틀림 400(아무것도 안 바뀜), 변경 후 새 비밀번호로만 로그인, 이전 토큰 401·새 토큰 200, 가입 규칙 422. 회원 탈퇴: 비밀번호 틀림 400, 탈퇴 후 로그인·토큰 401, 관리자 400, 글·사진 파일 삭제, 대화방 보존과 상대 화면의 "탈퇴한 사용자"·전송 400, 찜·차단 삭제와 신고 보존(id 비움), 탈퇴한 사용자 차단 404, 같은 이메일 재가입 |
| `test_users_me.py` | 12 | 토큰 없음·만료·변조·`alg: none`·다른 키 서명, 없는 사용자, 응답 필드(`role`·`suspended_until` 포함) |
| `test_posts_create.py` | 31 | 작성, 비로그인 401, 가격·필수 필드·`condition`·`status` 검증, 글자 수 경계값 |
| `test_posts_read.py` | 25 | 상세·404, 최신순 정렬, 닉네임 표시, N+1 방지, 페이지네이션 경계값 |
| `test_users_me_posts.py` | 8 | 내 글만 조회, 401, 페이지네이션 |
| `test_posts_update.py` | 37 | 일부 수정, 빈 본문, null 처리, SOLD 글 400, `updated_at`, 401/403/404 |
| `test_posts_status.py` | 24 | 전이표 9칸 전부, 멱등성, 401/403/404/422 |
| `test_posts_delete.py` | 11 | 204, 실제 행 삭제, 목록에서 제거, SOLD 글 삭제, 401/403/404 |
| `test_posts_search.py` | 52 | 필터별·조합 검색, 특수문자, 가격 경계값, 결과 없음, 필터 + 페이지네이션의 `total` |
| `test_posts_open_chat.py` | 71 | 오픈채팅 링크 허용·거절 주소(`javascript:`, 다른 도메인, 따옴표 등), 길이 경계값, 수정·삭제, 토큰 없음·만료·변조·정상 로그인별 상세 응답, 목록 미포함, XSS 시도 문자열 |
| `test_conversations.py` | 34 | 문의 시작 201·중복 시 200, 동시 요청 시 기존 방 반환, DB unique 제약, 본인 글·판매 완료 글 400, 401/403/404, 상대 정보만 노출(이메일 없음), 최신 메시지순 정렬, 페이지네이션, 글 삭제 후 대화방 보존, 목록 쿼리 수, 전체 안 읽은 개수와 경로 충돌 없음 |
| `test_messages.py` | 49 | 전송·조회 권한(제3자 403, 비로그인 401), 공백만·길이 경계값(1, 1000, 1001), 읽음 처리와 안 읽은 개수, 커서 페이지네이션(`before_id`·`after_id`·`has_more`), 도배 방지 429와 시간 경과 후 해제 |
| `test_post_images.py` | 43 | JPG·PNG·WebP 업로드와 WebP 재인코딩·크기 조정, GPS·EXIF 제거, 회전 반영, 투명도 유지, 서버가 만든 파일 이름, GIF·BMP·이름만 바꾼 텍스트·가짜 JPEG 헤더·잘린 파일 422, 5MB 초과 413, 픽셀 폭탄 422, 401/403/404, 판매 완료 400, 4번째 400, 업로드 횟수 429, 사진·글 삭제 시 파일 삭제, DB 실패 시 파일 정리, 목록 썸네일과 쿼리 수, `nosniff` 헤더, 경로 조작 404 |
| `test_book_alerts.py` | 14 | 등록·목록·삭제, 키워드 공백 제거, 최대 가격 선택, 11번째 400, 대소문자만 다른 중복 409, 다른 사용자는 같은 키워드 가능, 1글자·공백·101자·음수·문자열 가격·모르는 필드 422, 남의 조건 삭제 404, 401, 정지 중 등록 403·목록 허용 |
| `test_alert_notifications.py` | 27 | 교재명·과목명 부분 일치, 영어 대소문자 무시, `%`·`_` 글자 그대로(와일드카드 아님), 제목만 맞으면 알림 없음, 최대 가격 경계 포함·상한 없음, 내 글 제외, 차단한 판매자 제외·나중에 차단하면 목록·개수에서 제외, 조건 2개가 맞아도 알림 1개, 여러 사용자 각각 알림, 수정으로 새로 맞으면 알림·다시 수정해도 중복 없음, 가격 인하로 맞으면 알림, 제목만 수정하면 다시 매칭 안 함, **예약 중인 글 수정은 알림 없음**, 안 읽은 수·모두 읽음, 최신순·글 요약, 남의 알림 비공개, 글 삭제 시 알림 삭제, 조건 삭제해도 받은 알림 유지, 탈퇴 시 정리, 401 |
| `test_wishlist.py` | 36 | 찜 201·중복 200(행 1개)·DB 중복 거절, 해제 204·찜 안 한 글 해제 204, 401/404, 내 글 400, 판매 완료 글 새 찜 400·찜해 둔 글은 목록에 남음, 다른 사용자 찜과 분리, 글 삭제 시 찜 삭제, 찜한 순서 정렬·같은 초 정렬, 페이지네이션과 `total`, size 경계값, 목록·상세의 `is_wishlisted`(비로그인 `null`), 쿼리 수 |
| `test_blocks.py` | 35 | 차단 201·중복 200(행 1개), 해제 204·차단 안 한 사용자 해제 204, 자기 자신 400·DB CHECK 제약, 401/404, 차단 목록(이메일 없음, 나를 차단한 사람은 안 보임, 최신순·페이지네이션·size 경계값), 쪽지 전송·새 문의 양방향 400과 저장 안 됨, 해제 후 다시 전송, 지난 메시지 조회 가능, 기존 대화방 반환, 대화방 정보의 `can_send`·`blocked_by_me`, 목록 숨김(검색·필터 조합, 한쪽 방향, 비로그인 영향 없음, 해제 후 다시 보임), 목록 쿼리 수 그대로, 상세의 `is_seller_blocked` |
| `test_reports.py` | 30 | 사유 5가지 접수, 글 신고 사본 저장, 사용자 신고, 기타 사유 설명 필수, 설명 500자 경계값·공백 제거, 잘못된 본문 422, 401/404, 본인 글·자기 자신 400, 중복 409(사유를 바꿔도), 글·사용자 신고는 다른 대상, 횟수 제한 429와 `Retry-After`·시간 경과 후 해제·사용자별 분리, 글 삭제 후 신고 보존, 신고당한 사람의 응답 변화 없음 |
| `test_admin_auth.py` | 23 | 앱의 모든 `/admin` 경로를 자동으로 찾아 비로그인 401·일반 사용자 403, 403이 404·422보다 먼저, 가입에 `role`·모르는 필드 422, 새 사용자는 USER, 글 수정에 사용자 필드 422, 로그인 form의 `role` 무시, `role`은 `/users/me`에만(목록·상세·대화·차단 목록에 없음), CLI 지정·이미 관리자·없는 이메일·인자 없음 |
| `test_admin_reports.py` | 36 | 목록 필드와 이메일 없음, 미처리 우선·최신순, 상태 필터·페이지네이션, 잘못된 파라미터 422, 쿼리 수 고정, 기각 기록·목록의 처리 기록·공백 메모, 글 삭제 시 사진·찜 삭제와 대화방·사본 보존, 같은 글 신고 자동 함께 처리, 사용자 신고에 글 삭제 400, 이미 삭제된 글 400, 정지 종료 시각과 쓰기 403, 더 긴 정지 유지, 관리자 정지 400, 같은 사용자 함께 처리와 다른 사용자 분리, 잘못된 본문 422, 정지 일수 경계값, 404, 중복 처리 409(함께 처리된 신고 포함) |
| `test_suspension.py` | 15 | 정지된 사용자 로그인 403과 한국 시간 메시지(연도 포함), 틀린 비밀번호는 401(정지 사실 숨김), 기간 후 로그인, 메시지 형식(같은 해·해 바뀜), 이미 받은 토큰으로 쓰기 API 12개 모두 403, 422보다 먼저 403, 정지 중 요청으로 아무것도 안 바뀜, 기존 대화방 전송 403·조회 가능, 읽기 허용, `/users/me`의 정지 종료 시각, 차단·해제 허용, 자동 해제, 경계 시각 |
| `test_production_settings.py` | 9 | `postgres://`·`postgresql://` 주소의 psycopg 드라이버 변환, SQLite 주소 유지, 개발 모드 기본값, 운영 모드에서 올바른 설정 통과·SQLite 거절·짧은 `SECRET_KEY` 거절, 운영에서 `/docs` 꺼짐·개발에서 켜짐 |
| `test_test_settings.py` | 9 | 테스트의 bcrypt 비용 4(해시 형식 `$2b$04$`로 확인)와 운영 기본값 12, 다른 비용으로 만든 해시 검증, 잘못된 비용 값 거절, 인메모리 DB와 워커별 임시 사진 폴더 |
| `test_static.py` | 99 | 정적 파일 서빙(쪽지함·대화·찜 목록·찾는 교재 알림·차단 목록·신고 관리 화면 포함)과 MIME 타입, 헤더의 찜 링크·관리자 전용 "관리" 링크, 내 글 화면의 차단 목록 링크, 신고 사유·설명 글자 수의 프론트·서버 일치, 기본 그림·사진 입력칸, 사진 장수·크기 기준의 프론트·서버 일치, 대화 화면 개인정보 안내, `/` 리다이렉트, API와의 공존, JS 파일별 `innerHTML` 계열 사용 금지, 프론트·서버 전이표 일치, 오픈채팅 링크의 `rel`·`target`과 허용 접두사 일치, 모바일 기준 폭의 JS·CSS 일치, 화면별 `viewport-fit=cover`·탭 바 끄기, 탭 바 링크, 모바일 입력칸 16px, 화면별 JS의 공통 기준 폭 사용, 대화 화면 키보드 대응(`interactive-widget`·`visualViewport`)과 보내기 버튼 포커스 유지, 사진 넘기기는 모바일에서만, manifest(이름·standalone·시작 주소·테마색과 CSS 포인트 색 일치)와 아이콘 PNG 실제 크기, 화면별 manifest·apple meta 태그·서비스 워커 등록, 서비스 워커 캐시 범위(`/static/`만, 미리 받는 파일이 실제로 있음)와 버전 키, 설치 안내 표시 조건 |

## 향후 개선 계획

1. **초대 코드 방식 가입 제한**: 지금은 아무 이메일로나 가입할 수 있어서 "같은 학교 학생끼리"라는 목표를 아직 보장하지 못합니다. 학교에서 학생 이메일을 따로 발급하지 않아 학교 도메인(`@학교.ac.kr`)으로 제한할 수 없으므로, 학과·동아리 단위로 배포한 **초대 코드**가 있어야 가입할 수 있게 합니다. 가장 우선순위가 높은 과제입니다.
   - 코드마다 사용 횟수와 만료일을 두어, 코드가 밖으로 퍼져도 피해를 줄입니다.
   - 관리자가 코드를 만들고 끄는 기능과, 어떤 코드로 가입했는지 기록을 함께 둡니다(문제가 생긴 코드의 가입자 확인).
   - 관리자 승인 방식은 확인이 정확하지만 관리자의 일이 늘고 승인까지 기다려야 해서 고르지 않았습니다.
2. **운영 보강**: Railway 배포(Dockerfile, PostgreSQL, 볼륨, 운영 모드)와 설정의 코드 관리(`.railway/railway.ts`)는 마쳤습니다([배포](#배포-railway)). 남은 일은 다음과 같습니다.
   - **Alembic 마이그레이션**: 지금은 `create_all`이라 기존 테이블의 컬럼 변경이 반영되지 않아, 개발 DB에는 README의 수동 명령을, 운영 PostgreSQL에는 직접 `ALTER`를 실행해야 합니다. 탈퇴 표시를 `deleted_at` 컬럼으로 옮기는 일도 이때 함께 합니다([설계 결정 19번](#19-회원-탈퇴-사용자-행은-지우지-않고-익명화)).
   - 직접 정한 도메인 연결(지금은 Railway 기본 주소), PostgreSQL과 사진 볼륨의 정기 백업, 로그·오류 모니터링
   - **CI**: GitHub Actions에서 push마다 테스트를 자동 실행
3. **거래 후기·매너 평가**: 판매 완료된 거래의 두 사람이 서로 한 번씩 후기(점수와 짧은 글)를 남기고, 프로필에 매너 점수를 보여줍니다.
   - 지금은 "누구와 거래했는지"가 기록되지 않으므로, 판매 완료로 바꿀 때 대화방의 구매자 중 거래 상대를 고르게 해야 합니다. 대화방이 있는 사람만 후기를 쓸 수 있게 하면 아무나 후기를 다는 것을 막을 수 있습니다.
   - 후기가 붙은 글은 지우면 근거가 사라지므로, 이때 글 삭제를 soft delete로 바꿀지 다시 검토합니다([설계 결정 2번](#2-hard-delete)). 신고는 글 사본을 따로 저장해 hard delete를 유지했습니다.
4. **ISBN 자동 입력**: 글쓰기에서 ISBN(바코드 촬영 또는 직접 입력)으로 교재명·저자·출판사·정가를 채웁니다. 외부 도서 검색 API를 쓰므로 API 키는 서버 환경 변수로만 두고, 같은 ISBN 응답은 캐시해 호출 수를 줄입니다. 글에 ISBN을 저장하면 같은 교재를 정확히 묶을 수 있어 아래 시세 기능의 바탕이 됩니다.
5. **같은 교재 시세**: 같은 교재(ISBN, 없으면 정규화한 교재명)의 최근 판매 완료 가격 범위와 중앙값을 글쓰기·상세 화면에 보여줘, 판매자는 값을 정하기 쉽고 구매자는 비싼지 판단할 수 있게 합니다. 판매 완료로 표시한 가격이 실제 거래가와 다를 수 있고, 거래가 적으면 숫자가 오해를 낳으므로 표본이 몇 건 이상일 때만 보여줍니다.
6. **비밀번호 재설정 (이메일 발송)**: 지금은 로그인한 상태에서만 비밀번호를 바꿀 수 있어, 잊어버리면 방법이 없습니다.
   - 이메일로 일회용 재설정 링크를 보냅니다. 링크 토큰은 짧게 만료시키고, DB에는 해시만 저장하며 한 번 쓰면 폐기합니다.
   - 가입하지 않은 이메일에도 같은 응답("메일을 보냈습니다")을 줘 가입 여부를 드러내지 않고([설계 결정 1번](#1-계정-존재-여부-노출)), 요청 횟수를 제한합니다.
   - 재설정하면 비밀번호 해시가 바뀌므로 기존 토큰은 지문 방식으로 자동으로 끊깁니다([설계 결정 18번](#18-토큰의-비밀번호-지문-비밀번호를-바꾸면-이전-토큰은-모두-무효)). 메일 발송 서비스와 발신 도메인 설정이 필요합니다.
7. **웹 푸시 알림**: 지금 찾는 교재 알림과 새 쪽지는 사이트를 열어야 헤더 배지로 보입니다. Web Push(VAPID 키, 서비스 워커의 `push` 이벤트)로 화면을 닫아도 휴대폰 알림으로 받게 합니다.
   - 기기별 구독 정보를 저장하는 테이블과, 알림 권한을 묻는 시점(처음 찾는 교재를 등록할 때처럼 이유가 분명한 때)이 필요합니다.
   - 아이폰은 홈 화면에 추가한 PWA(iOS 16.4 이상)에서만 웹 푸시를 받을 수 있습니다.
   - 찾는 교재 알림은 이미 DB에 쌓이므로, 알림 행을 만든 뒤 푸시를 보내는 단계만 더하면 됩니다. 이때 글 작성 요청이 느려지지 않게 발송은 작업 큐로 뺍니다.
8. **Flutter 안드로이드 앱 (별도 저장소 예정)**: 이 서버의 API를 그대로 쓰는 안드로이드 앱을 Flutter로 만듭니다. 웹(PWA)과 같은 API를 쓰므로 서버는 크게 바뀌지 않지만, 다음이 필요합니다.
   - 새 쪽지와 찾는 교재 알림의 푸시 알림(FCM)과 기기 토큰 저장 API (7번 웹 푸시와 구독 저장 구조를 함께 설계)
   - 리프레시 토큰(앱은 오래 로그인 상태를 유지하므로), API 버전 표기(`/v1`)로 앱과 서버 배포 시점 분리
   - ISBN 자동 입력의 바코드 촬영은 앱에서 카메라를 쓰기 쉬워 함께 넣기 좋습니다.
9. **HttpOnly 쿠키 전환**: 토큰을 JS가 읽을 수 없는 HttpOnly 쿠키로 옮겨, XSS가 생겨도 토큰을 탈취할 수 없게 합니다. 대신 쿠키는 자동으로 전송되므로 SameSite 설정과 CSRF 토큰 같은 대책을 함께 넣어야 합니다([설계 결정 4번](#4-토큰을-localstorage에-저장)).
10. **작성 중 토큰 만료 시 입력 내용 보존**: 지금은 글을 저장하는 순간 토큰이 만료되어 401이 나면 로그인 화면으로 이동하면서 입력한 내용이 사라집니다. 이동 전에 입력 내용을 sessionStorage에 임시 저장하고, 로그인 후 돌아오면 복원할 계획입니다.
11. **내 글 상태별 필터와 개수**: 내 글 화면에 "판매 중 3 · 예약 중 1 · 판매 완료 5" 같은 탭을 넣습니다. 서버의 `/users/me/posts`에 `status` 파라미터와 상태별 개수 응답도 함께 추가해야 합니다.
12. **보안 강화**: 로그인·회원가입·비밀번호 변경 요청 횟수 제한. 비밀번호 변경 때의 토큰 무효화는 들어갔고([설계 결정 18번](#18-토큰의-비밀번호-지문-비밀번호를-바꾸면-이전-토큰은-모두-무효)), 일반 로그아웃의 한계는 리프레시 토큰으로 보완합니다([설계 결정 5번](#5-로그아웃은-토큰-삭제만)).
13. **사진 정리 작업**: 서버가 파일을 쓴 직후 꺼지거나 파일 삭제가 실패하면, DB에 없는 파일이 `uploads/`에 남을 수 있습니다. DB에 없는 파일을 찾아 지우는 정리 스크립트를 주기적으로 돌릴 계획입니다.
14. **검색 성능**: `%검색어%` 검색은 일반 인덱스를 쓰지 못하므로, 데이터가 늘면 PostgreSQL의 `pg_trgm`(삼중 문자) 인덱스를 검토합니다.
15. **신고 처리 보완**: 신고 처리 화면과 기간 정지는 들어갔습니다. 남은 일은 다음과 같습니다.
    - 정지·글 삭제를 당사자에게 알리기 (지금은 로그인·쓰기 때 403 메시지로만 알게 됨). 찾는 교재 알림의 알림 목록을 일반 알림으로 넓혀 함께 쓸 수 있습니다
    - 관리자 해제·정지 해제 CLI, 정지 이력 테이블 (지금은 마지막 정지 종료 시각만 남음)
    - 정지된 사용자의 글을 목록에서 숨길지 결정
    - 신고된 쪽지를 관리자가 확인하는 방법, 신고 사본의 보관 기간
16. **쪽지 읽음 표시**: 내가 보낸 메시지에 "읽음"을 보여줍니다. 서버는 이미 `read_at`을 주므로, 폴링 때 상대가 마지막으로 읽은 메시지 id를 함께 받는 방식으로 화면이 최신 상태를 알 수 있게 하면 됩니다.
17. **WebSocket 전환 (폴링 대체)**: 지금은 대화 화면이 5초마다 새 메시지를 묻습니다. WebSocket으로 서버가 새 메시지와 읽음 변화를 바로 보내 주면 지연이 없어지고 빈 요청도 줄어듭니다. 서버가 여러 대일 때를 위해 Redis Pub/Sub 같은 메시지 전달 계층도 함께 필요합니다.
18. **사진 업로드 기록 테이블**: 지금 업로드 횟수 제한은 남아 있는 사진만 세므로, 올렸다 지우기를 반복하면 덜 셉니다. 업로드 기록을 따로 저장하면 정확하게 셀 수 있습니다. 사용자가 늘면 사진 저장도 오브젝트 스토리지 + CDN으로 옮깁니다([설계 결정 12번](#12-사진-전용-경로로-이미지-제공)).
19. **찜 알림과 상한**: 찜한 글의 가격이 내리거나 판매 완료되면 알려주는 기능을 검토합니다. 찾는 교재 알림의 알림 목록·배지를 그대로 쓸 수 있습니다. 지금은 같은 글을 한 번만 찜할 수 있어 데이터가 끝없이 늘지는 않으므로 찜 수 상한과 요청 횟수 제한은 넣지 않았습니다. 악용이 보이면 함께 넣습니다.
