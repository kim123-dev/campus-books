from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import ActiveUser
from app.models import PendingImage
from app.schemas.post import PendingImageResponse
from app.services import image_service, pending_image_service

router = APIRouter(prefix="/pending-images", tags=["images"])


# 글쓰기 화면이 사진을 고르는 즉시 한 장씩 올려 두는 곳. 글을 저장할 때 응답의 id를 image_ids로 보낸다.
# 글에 붙지 않은 사진은 24시간 뒤 정리된다.
@router.post(
    "",
    response_model=PendingImageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="임시 사진 올리기 (글에 붙이기 전, JPG·PNG·WebP·HEIC, 25MB)",
    responses={
        401: {"description": "로그인 필요"},
        413: {"description": "25MB 초과"},
        422: {"description": "지원하지 않는 형식, 해상도 초과(JPG 2억·그 밖 5천만 화소), 깨진 사진"},
        429: {"description": "업로드 횟수 제한"},
    },
)
def upload_pending_image(
    current_user: ActiveUser,
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(description="사진 파일 (multipart 필드 이름: file)")],
) -> PendingImage:
    return image_service.add_pending_image(db, current_user, file.file)


@router.delete(
    "/{pending_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="임시 사진 삭제 (글쓰기 화면에서 사진을 뺐을 때)",
    responses={401: {"description": "로그인 필요"}, 404: {"description": "없는 사진 또는 내 사진이 아님"}},
)
def delete_pending_image(
    pending_id: int,
    current_user: ActiveUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    pending_image_service.delete_pending(db, current_user, pending_id)
