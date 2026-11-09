from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.exceptions import ImageNotFoundError
from app.models import PostImage
from app.schemas.post import PostImageResponse
from app.services import image_service, image_storage

router = APIRouter(tags=["images"])

# 업로드·삭제 API의 공통 에러 응답. Swagger 문서에 보이도록 정리해 둔다.
IMAGE_EDIT_RESPONSES: dict[int | str, dict] = {
    400: {"description": "판매 완료된 글이거나 이미 3장"},
    401: {"description": "로그인 필요"},
    403: {"description": "작성자가 아님"},
    404: {"description": "없는 글 또는 사진"},
}


# 사진은 한 요청에 한 장씩 받는다. 여러 장이면 프론트가 차례로 보내고, 한 장이 실패해도 나머지는 남는다.
@router.post(
    "/posts/{post_id}/images",
    response_model=PostImageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="판매글 사진 올리기 (JPG·PNG·WebP, 5MB, 글당 3장)",
    responses={
        **IMAGE_EDIT_RESPONSES,
        413: {"description": "5MB 초과"},
        422: {"description": "지원하지 않는 형식이거나 깨진 사진"},
        429: {"description": "업로드 횟수 제한"},
    },
)
def upload_post_image(
    post_id: int,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(description="사진 파일 (multipart 필드 이름: file)")],
) -> PostImage:
    return image_service.add_image(db, post_id, current_user, file.file)


@router.delete(
    "/posts/{post_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="판매글 사진 삭제",
    responses=IMAGE_EDIT_RESPONSES,
)
def delete_post_image(
    post_id: int,
    image_id: int,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    image_service.delete_image(db, post_id, image_id, current_user)


# 사진 파일 제공. static/에 두지 않고 이 경로로만 내보내, 서버가 만든 이름 형식만 열고
# 항상 image/webp + nosniff로 보내 브라우저가 내용을 다른 형식(HTML 등)으로 해석하지 않게 한다.
@router.get(
    "/images/{filename}",
    response_class=FileResponse,
    summary="사진 파일",
    responses={404: {"description": "없는 사진"}},
)
def get_image(filename: str) -> FileResponse:
    path = image_storage.path_for(filename)
    if path is None or not path.is_file():
        raise ImageNotFoundError()
    return FileResponse(
        path,
        media_type="image/webp",
        headers={
            "X-Content-Type-Options": "nosniff",
            # 같은 이름에 다른 내용이 들어가는 일이 없으므로(새 사진은 새 이름) 오래 캐시해도 된다.
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
