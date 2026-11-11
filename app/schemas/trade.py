from pydantic import BaseModel, ConfigDict


class BuyerCandidateResponse(BaseModel):
    """구매자로 고를 수 있는 사람. 이메일은 노출하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str


class PostBuyerResponse(BaseModel):
    """판매자 화면용 구매자 정보. 판매 완료 창과 구매자 변경 창이 함께 쓴다."""

    # 지금 기록된 구매자. 고르지 않았거나 아직 판매 완료가 아니면 null.
    buyer: BuyerCandidateResponse | None
    # 이 글로 쪽지를 보낸 사람 중 고를 수 있는 사람(최근 대화순). 탈퇴·차단 관계는 뺀다.
    candidates: list[BuyerCandidateResponse]
    # 구매자를 바꾸거나 "선택 안 함"으로 되돌릴 수 있는지. 거래가 있고 후기가 아직 없을 때만 true.
    changeable: bool


class BuyerUpdate(BaseModel):
    """판매 완료된 글의 구매자 변경. null이면 "선택 안 함"으로 되돌린다."""

    model_config = ConfigDict(extra="forbid")

    buyer_id: int | None
