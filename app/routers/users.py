from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ActiveUser, CurrentUser
from app.models import User
from app.schemas.post import PageQuery, PostListResponse, SizeQuery
from app.schemas.user import MeResponse, NicknameUpdate, PasswordChange, TokenResponse, WithdrawRequest
from app.services import account_service, post_service, user_service, wishlist_service

router = APIRouter(prefix="/users", tags=["users"])


# 인증은 CurrentUser 의존성이 처리하고, response_model이 password_hash를 걸러낸다.
# role과 정지 상태는 이 응답에만 넣는다. 다른 사용자에 대한 응답에는 닉네임까지만 나간다.
@router.get(
    "/me",
    response_model=MeResponse,
    summary="내 정보 조회",
    responses={401: {"description": "토큰 없음, 만료·변조된 토큰, 존재하지 않는 사용자"}},
)
def read_me(current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> MeResponse:
    return _me_response(db, current_user)


# 내 정보 화면에서 닉네임을 바꾼다. 정지 중에는 바꿀 수 없다(403). 신고를 받은 뒤 이름을 바꿔 피하지 못하게 하기 위해서다.
@router.patch(
    "/me",
    response_model=MeResponse,
    summary="내 닉네임 변경 (30일에 한 번)",
    responses={
        400: {"description": "지금과 같은 닉네임, 30일 안에 이미 바꿈"},
        401: {"description": "로그인 필요"},
        403: {"description": "이용 정지 중"},
        409: {"description": "다른 사람이 쓰는 닉네임"},
    },
)
def update_me(
    data: NicknameUpdate, current_user: ActiveUser, db: Annotated[Session, Depends(get_db)]
) -> MeResponse:
    return _me_response(db, account_service.change_nickname(db, current_user, data))


def _me_response(db: Session, user: User) -> MeResponse:
    # 기간이 지난 정지는 null로 보여준다. 화면은 이 값이 있을 때만 정지 안내를 띄운다.
    return MeResponse.model_validate(user).model_copy(
        update={
            "suspended_until": user_service.active_suspension_end(user),
            "nickname_changeable_at": account_service.nickname_changeable_at(db, user),
        }
    )


# 내 글 관리 화면용. 판매 완료된 글도 보여야 하므로 상태로 거르지 않는다.
@router.get(
    "/me/posts",
    response_model=PostListResponse,
    summary="내 판매글 목록 (최신순)",
    responses={401: {"description": "로그인 필요"}},
)
def read_my_posts(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> PostListResponse:
    posts, total = post_service.list_posts_by_seller(db, current_user.id, page, size)
    return PostListResponse(items=posts, total=total, page=page, size=size)


# 찜 목록 화면용. 찜해 둔 뒤 판매 완료된 글도 보여준다. (카드에 판매 완료 배지가 붙는다)
@router.get(
    "/me/wishlist",
    response_model=PostListResponse,
    summary="내 찜 목록 (찜한 순서 최신순)",
    responses={401: {"description": "로그인 필요"}},
)
def read_my_wishlist(
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    page: PageQuery = 1,
    size: SizeQuery = 20,
) -> PostListResponse:
    items, total = wishlist_service.list_wishlist(db, current_user, page, size)
    return PostListResponse(items=items, total=total, page=page, size=size)


# 정지 중에도 쓸 수 있게 ActiveUser가 아닌 CurrentUser를 쓴다. (유출이 의심되면 정지 중에도 바꿀 수 있어야 한다)
@router.put(
    "/me/password",
    response_model=TokenResponse,
    summary="비밀번호 변경 (새 액세스 토큰 발급)",
    responses={
        400: {"description": "현재 비밀번호 불일치"},
        401: {"description": "로그인 필요"},
    },
)
def change_my_password(
    data: PasswordChange, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> TokenResponse:
    # 변경 전에 받은 토큰은 모두 무효가 되므로, 지금 기기에서 계속 쓸 새 토큰을 돌려준다.
    return TokenResponse(access_token=account_service.change_password(db, current_user, data))


# DELETE에 본문을 받는 대신 POST로 둔다. 본문이 있는 DELETE는 일부 프록시·클라이언트가 지원하지 않는다.
@router.post(
    "/me/withdraw",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="회원 탈퇴",
    responses={
        400: {"description": "비밀번호 불일치, 관리자 계정"},
        401: {"description": "로그인 필요"},
    },
)
def withdraw_me(
    data: WithdrawRequest, current_user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> Response:
    account_service.withdraw(db, current_user, data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
