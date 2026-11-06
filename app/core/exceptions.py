class DomainError(Exception):
    """서비스 계층의 업무 예외. 서비스가 HTTP 상태 코드를 몰라도 되게 분리했다."""

    message: str = "요청을 처리할 수 없습니다."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class ConflictError(DomainError):
    """이미 존재하는 데이터와 충돌. main.py에서 409로 변환한다."""


class DuplicateEmailError(ConflictError):
    message = "이미 사용 중인 이메일입니다."


class DuplicateNicknameError(ConflictError):
    message = "이미 사용 중인 닉네임입니다."
