from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RefreshToken(Base):
    """앱(안드로이드)의 로그인 유지용 갱신 토큰. 웹은 쓰지 않는다(웹은 지금처럼 액세스 토큰만).

    - 토큰 원문은 저장하지 않고 SHA-256 해시만 저장한다. DB가 유출돼도 토큰으로 쓸 수 없다.
    - 쓸 때마다 새 토큰으로 바꾼다(교체). 이미 바꾼(또는 폐기한) 토큰이 다시 오면 훔친 토큰으로 보고
      그 사용자의 갱신 토큰을 모두 폐기한다(재사용 감지).
    - 발급 당시 비밀번호 지문을 함께 저장한다. 비밀번호가 바뀌었으면(변경·재설정·탈퇴) 폐기 처리를 빠뜨린 경로가
      있더라도 갱신이 거절된다. (액세스 토큰의 pwd와 같은 방식)
    users 테이블에 컬럼을 더하지 않으려고 새 테이블로 둔다. (운영 DB는 create_all만 쓴다)
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 사용자의 토큰을 모두 폐기할 때 찾으므로 index를 둔다.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 토큰 원문의 SHA-256(hex). 갱신 요청에서 이 값으로 찾는다.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # 발급 당시 비밀번호 지문(security.password_fingerprint).
    password_fingerprint: Mapped[str] = mapped_column(String(32))
    # 앱이 보낸 기기 이름(선택). 나중에 "로그인한 기기" 화면에 쓸 수 있다.
    device_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # 새 토큰으로 바꾼 시각. 값이 있으면 이 토큰은 다시 쓸 수 없다(다시 오면 재사용).
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 이 토큰을 바꿔 발급한 새 토큰. 교체 흐름을 추적할 때 쓴다.
    replaced_by_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 로그아웃·비밀번호 변경·탈퇴·재사용 감지로 폐기한 시각.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
