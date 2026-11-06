from fastapi import FastAPI

app = FastAPI(title="Campus Books", description="캠퍼스 중고 교재 거래 게시판 API")


# 배포/모니터링 시 서버가 살아있는지 DB 없이 빠르게 확인하기 위한 엔드포인트
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
