"""사진 파일을 디스크에 쓰고 지우는 일만 맡는다.

글 서비스(글 삭제 시 파일 정리)와 사진 서비스(업로드·삭제)가 함께 쓰므로,
두 서비스가 서로를 불러오는 순환 참조를 피하려고 따로 떼어 두었다.
"""

import logging
import re
import secrets
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 서버가 만든 이름만 허용한다. 이 형식이 아니면 디스크를 찾지 않으므로 "../" 같은 경로 조작이 통하지 않는다.
FILENAME_PATTERN = re.compile(r"[0-9a-f]{32}(_thumb)?\.webp")
IMAGE_SUBDIR = "posts"


def get_image_dir() -> Path:
    """사진 폴더. 테스트는 이 함수를 바꿔 끼워 임시 폴더를 쓴다."""
    return Path(get_settings().UPLOAD_DIR) / IMAGE_SUBDIR


def new_filenames() -> tuple[str, str]:
    """(원본, 썸네일) 파일 이름. 원본 파일 이름은 쓰지 않고 추측할 수 없는 임의 값으로 만든다."""
    token = secrets.token_hex(16)
    return f"{token}.webp", f"{token}_thumb.webp"


def is_valid_filename(name: str) -> bool:
    return FILENAME_PATTERN.fullmatch(name) is not None


def path_for(name: str) -> Path | None:
    """이름이 형식에 맞을 때만 경로를 돌려준다."""
    return get_image_dir() / name if is_valid_filename(name) else None


def write_files(files: dict[str, bytes]) -> None:
    """여러 파일을 쓴다. 하나라도 실패하면 이미 쓴 것을 지우고 예외를 다시 던진다."""
    directory = get_image_dir()
    directory.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    try:
        for name, data in files.items():
            # "xb": 같은 이름이 이미 있으면 덮어쓰지 않고 실패한다. (임의 이름이라 사실상 일어나지 않는다)
            with open(directory / name, "xb") as file:
                file.write(data)
            written.append(name)
    except Exception:
        remove_files(written)
        raise


def remove_files(names: list[str]) -> None:
    """파일을 지운다. DB는 이미 커밋된 뒤라, 실패해도 요청을 실패시키지 않고 기록만 남긴다."""
    for name in names:
        path = path_for(name)
        if path is None:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("사진 파일을 지우지 못했습니다: %s", path, exc_info=True)
