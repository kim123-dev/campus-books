# 캠퍼스 중고 교재 거래 게시판

## 프로젝트 목적
같은 학교 학생끼리 전공 교재를 사고파는 웹 서비스. 포트폴리오용이므로
코드 가독성과 구조, README 문서화를 중요하게 다룬다.

## 기술 스택
- 백엔드: Python, FastAPI, SQLAlchemy, Pydantic
- DB: MySQL (개발 중에는 SQLite 사용 가능)
- 인증: JWT (비밀번호는 bcrypt 해시)
- 프론트: 순수 HTML/CSS/JS (fetch로 API 호출)

## 폴더 구조
app/
  main.py
  models/      # SQLAlchemy 모델
  schemas/     # Pydantic 스키마
  routers/     # auth, posts, comments, ...
  services/    # 비즈니스 로직
  core/        # 설정, 보안, DB 연결
static/        # 프론트 파일
tests/

## 코딩 규칙
- 라우터에는 요청/응답 처리만, 로직은 services에 작성
- 모든 API는 Pydantic 스키마로 입력 검증
- 비밀번호, 키 등 비밀값은 .env로 관리하고 커밋 금지
- 함수에는 짧은 한국어 주석(왜 이렇게 했는지 중심)

## 작업 방식
- 한 번에 한 기능씩 구현하고, 구현 전에 변경할 파일 목록을 먼저 알려줄 것
- 기능이 끝나면 실행 방법과 테스트 방법을 알려줄 것
- 내가 요청하지 않은 파일은 수정하지 말 것
