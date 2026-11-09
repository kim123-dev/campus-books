"""서버 관리 명령. 가입·수정 API로는 할 수 없는 일(관리자 지정)을 서버에 접속할 수 있는 사람만 하도록 둔다.

사용 예:
    python -m app.cli make-admin admin@campus.ac.kr

.env의 DATABASE_URL이 가리키는 DB를 쓴다. (서버를 끄지 않아도 된다)
"""

import argparse
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import UserNotFoundError
from app.services import user_service


def make_admin(db: Session, email: str) -> tuple[int, str]:
    """(종료 코드, 안내 문구)를 돌려준다. 출력과 종료는 main이 한다."""
    try:
        changed = user_service.make_admin(db, email)
    except UserNotFoundError:
        return 1, f"'{email}' 이메일로 가입한 사용자가 없습니다."
    if not changed:
        return 0, f"'{email}' 사용자는 이미 관리자입니다. 바꾼 것이 없습니다."
    return 0, f"'{email}' 사용자를 관리자로 지정했습니다. 다시 로그인하지 않아도 바로 적용됩니다."


def main(argv: Sequence[str] | None = None, session_factory: Callable[[], Session] = SessionLocal) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Campus Books 서버 관리 명령")
    commands = parser.add_subparsers(dest="command", required=True)
    make_admin_parser = commands.add_parser("make-admin", help="가입한 사용자를 관리자로 지정")
    make_admin_parser.add_argument("email", help="관리자로 지정할 사용자의 가입 이메일")
    args = parser.parse_args(argv)

    try:
        with session_factory() as db:
            code, message = make_admin(db, args.email)
    except OperationalError as error:
        # 기존 dev.db에 role 컬럼을 추가하지 않은 경우 등. README의 "기존 dev.db 업데이트"를 안내한다.
        print(f"DB를 읽지 못했습니다. README의 '기존 dev.db 업데이트'를 확인하세요. ({error.orig})", file=sys.stderr)
        return 1
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
