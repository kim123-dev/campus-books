# 배포용 이미지. Railway가 이 파일을 자동으로 찾아 빌드한다.
# 로컬 개발과 같은 파이썬 버전을 써서 "내 컴퓨터에선 되는데" 문제를 줄인다.
FROM python:3.14-slim

# .pyc를 만들지 않고, 로그를 버퍼 없이 바로 내보내 Railway 로그 화면에 즉시 보이게 한다.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성을 먼저 설치해, 코드만 바뀐 배포에서는 이 단계를 캐시로 건너뛴다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

# root로 실행한다. Railway 볼륨은 root 소유로 붙어서, 다른 사용자로 바꾸면 사진을 저장하지 못한다.
# PORT는 Railway가 넣어 준다. 프록시(HTTPS 종료) 뒤에 있으므로 X-Forwarded-* 헤더를 믿게 한다.
# exec로 uvicorn을 1번 프로세스로 만들어, 재배포 시 종료 신호를 바로 받고 깔끔하게 끝나게 한다.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
