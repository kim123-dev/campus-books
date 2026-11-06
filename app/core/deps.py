from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import InvalidTokenError, NotAuthenticatedError
from app.core.security import decode_access_token, oauth2_scheme
from app.models import User
from app.services import user_service


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Authorization 헤더의 Bearer 토큰으로 현재 사용자를 찾는다. 실패하면 모두 401."""
    # 헤더가 없거나 Bearer 방식이 아니면 oauth2_scheme이 None을 준다.
    if token is None:
        raise NotAuthenticatedError()

    # 만료·변조·형식 오류는 decode_access_token이 InvalidTokenError로 던진다.
    user_id = decode_access_token(token)

    # 서명이 맞아도 그사이 사용자가 삭제됐을 수 있으므로 DB에서 다시 확인한다.
    user = user_service.get_user_by_id(db, user_id)
    if user is None:
        raise InvalidTokenError()
    return user


# 라우터에서 `current_user: CurrentUser`만 쓰면 되도록 타입 별칭으로 묶어둔다.
CurrentUser = Annotated[User, Depends(get_current_user)]
