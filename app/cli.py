"""서버 관리 명령. 가입·수정 API로는 할 수 없는 일(관리자 지정)을 서버에 접속할 수 있는 사람만 하도록 둔다.

사용 예:
    python -m app.cli make-admin admin@campus.ac.kr
    python -m app.cli reset-password admin@campus.ac.kr   # 비밀번호 분실(관리자 등). 새 비밀번호를 한 번만 보여준다.

.env의 DATABASE_URL이 가리키는 DB를 쓴다. (서버를 끄지 않아도 된다)
"""

import argparse
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import UserNotFoundError
from app.services import password_reset_service, user_service


def make_admin(db: Session, email: str) -> tuple[int, str]:
    """(종료 코드, 안내 문구)를 돌려준다. 출력과 종료는 main이 한다."""
    try:
        changed = user_service.make_admin(db, email)
    except UserNotFoundError:
        return 1, f"'{email}' 이메일로 가입한 사용자가 없습니다."
    if not changed:
        return 0, f"'{email}' 사용자는 이미 관리자입니다. 바꾼 것이 없습니다."
    return 0, f"'{email}' 사용자를 관리자로 지정했습니다. 다시 로그인하지 않아도 바로 적용됩니다."


def reset_password(db: Session, email: str) -> tuple[int, str]:
    """새 비밀번호를 만들어 바꾸고 화면에만 보여준다. 로그·파일·관리 기록에는 비밀번호를 남기지 않는다."""
    try:
        password = password_reset_service.reset_by_server(db, email)
    except UserNotFoundError:
        return 1, f"'{email}' 이메일로 가입한 사용자가 없습니다."
    return 0, (
        f"'{email}' 사용자의 비밀번호를 재설정했습니다. 이 사용자의 기존 로그인은 모두 끊겼습니다.\n"
        f"새 비밀번호: {password}\n"
        "이 비밀번호는 다시 볼 수 없습니다. 본인에게 안전하게 전달하고, 로그인한 뒤 바로 바꾸게 하세요."
    )


def main(argv: Sequence[str] | None = None, session_factory: Callable[[], Session] = SessionLocal) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Campus Books 서버 관리 명령")
    commands = parser.add_subparsers(dest="command", required=True)
    make_admin_parser = commands.add_parser("make-admin", help="가입한 사용자를 관리자로 지정")
    make_admin_parser.add_argument("email", help="관리자로 지정할 사용자의 가입 이메일")
    reset_parser = commands.add_parser("reset-password", help="비밀번호 재설정 (새 비밀번호를 한 번만 보여줌)")
    reset_parser.add_argument("email", help="비밀번호를 재설정할 사용자의 가입 이메일")
    args = parser.parse_args(argv)
    command = {"make-admin": make_admin, "reset-password": reset_password}[args.command]

    try:
        with session_factory() as db:
            code, message = command(db, args.email)
    except OperationalError as error:
        # 기존 dev.db에 role 컬럼을 추가하지 않은 경우 등. README의 "기존 dev.db 업데이트"를 안내한다.
        print(f"DB를 읽지 못했습니다. README의 '기존 dev.db 업데이트'를 확인하세요. ({error.orig})", file=sys.stderr)
        return 1
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
