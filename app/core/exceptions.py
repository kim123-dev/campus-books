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


class NotFoundError(DomainError):
    """요청한 데이터가 없음. main.py에서 404로 변환한다."""


class PostNotFoundError(NotFoundError):
    message = "게시글을 찾을 수 없습니다."


class AuthenticationError(DomainError):
    """인증 실패. main.py에서 401로 변환한다."""


class InvalidCredentialsError(AuthenticationError):
    # 이메일이 없는 경우와 비밀번호가 틀린 경우를 같은 메시지로 처리해,
    # 어떤 이메일이 가입되어 있는지 알아낼 수 없게 한다.
    message = "이메일 또는 비밀번호가 올바르지 않습니다."


class NotAuthenticatedError(AuthenticationError):
    # 토큰 자체가 없는 경우. 토큰 오류와 메시지를 나눠 프론트가 안내를 구분할 수 있게 한다.
    message = "로그인이 필요합니다."


class InvalidTokenError(AuthenticationError):
    message = "인증 정보가 유효하지 않거나 만료되었습니다."
