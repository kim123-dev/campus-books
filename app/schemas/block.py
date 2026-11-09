from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BlockedUserResponse(BaseModel):
    """차단한 상대. 이메일 등 개인정보는 넣지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str


class BlockResponse(BaseModel):
    """차단 목록의 한 줄."""

    user: BlockedUserResponse
    created_at: datetime


class BlockStatusResponse(BaseModel):
    """차단 응답. 화면이 버튼 상태를 서버 기준으로 맞출 수 있게 결과를 돌려준다."""

    user_id: int
    is_blocked: bool


class BlockListResponse(BaseModel):
    items: list[BlockResponse]
    total: int
    page: int
    size: int
