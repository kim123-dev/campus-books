class DomainError(Exception):
    """서비스 계층의 업무 예외. 서비스가 HTTP 상태 코드를 몰라도 되게 분리했다."""

    message: str = "요청을 처리할 수 없습니다."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class ConflictError(DomainError):
    """이미 존재하는 데이터와 충돌. main.py에서 409로 변환한다."""


class DuplicateReportError(ConflictError):
    message = "이미 신고한 대상입니다."


class ReportAlreadyResolvedError(ConflictError):
    message = "이미 처리된 신고입니다."


class DuplicateEmailError(ConflictError):
    message = "이미 사용 중인 이메일입니다."


class DuplicateNicknameError(ConflictError):
    message = "이미 사용 중인 닉네임입니다."


class NotFoundError(DomainError):
    """요청한 데이터가 없음. main.py에서 404로 변환한다."""


class PostNotFoundError(NotFoundError):
    message = "게시글을 찾을 수 없습니다."


class UserNotFoundError(NotFoundError):
    message = "사용자를 찾을 수 없습니다."


class ReportNotFoundError(NotFoundError):
    message = "신고를 찾을 수 없습니다."


class ImageNotFoundError(NotFoundError):
    message = "사진을 찾을 수 없습니다."


class ConversationNotFoundError(NotFoundError):
    message = "대화방을 찾을 수 없습니다."


class ForbiddenError(DomainError):
    """로그인은 했지만 권한이 없음. main.py에서 403으로 변환한다."""


class NotPostOwnerError(ForbiddenError):
    message = "본인이 작성한 글만 수정·삭제할 수 있습니다."


class AdminOnlyError(ForbiddenError):
    message = "관리자만 사용할 수 있습니다."


class SuspendedUserError(ForbiddenError):
    # 실제 메시지는 정지 종료 시각을 넣어 만든다. (user_service.suspension_message)
    message = "이용이 정지되었습니다."


class NotConversationParticipantError(ForbiddenError):
    message = "대화에 참여한 사용자만 볼 수 있습니다."


class BadRequestError(DomainError):
    """형식은 맞지만 현재 상태에서 허용되지 않는 요청. main.py에서 400으로 변환한다."""


class TooManyImagesError(BadRequestError):
    message = "사진은 글 하나에 3장까지 올릴 수 있습니다."


class SoldPostNotEditableError(BadRequestError):
    message = "판매 완료된 글은 수정할 수 없습니다."


class InvalidStatusTransitionError(BadRequestError):
    message = "판매 완료된 글은 상태를 변경할 수 없습니다."


class CannotContactOwnPostError(BadRequestError):
    message = "본인 글에는 문의할 수 없습니다."


class SoldPostNotContactableError(BadRequestError):
    message = "판매 완료된 글에는 새로 문의할 수 없습니다."


class CannotWishlistOwnPostError(BadRequestError):
    message = "본인 글은 찜할 수 없습니다."


class SoldPostNotWishlistableError(BadRequestError):
    message = "판매 완료된 글은 새로 찜할 수 없습니다."


class CannotBlockSelfError(BadRequestError):
    message = "자기 자신은 차단할 수 없습니다."


class BlockedUserMessageError(BadRequestError):
    """내가 상대를 차단한 경우. 해제하면 다시 보낼 수 있다는 것까지 알려준다."""

    message = "차단한 사용자에게는 쪽지를 보낼 수 없습니다. 차단을 해제하면 다시 보낼 수 있어요."


class BlockedByUserMessageError(BadRequestError):
    """상대가 나를 차단한 경우. "차단당했다"고 직접 알리지 않는다."""

    message = "이 사용자에게는 쪽지를 보낼 수 없습니다."


class CannotReportOwnPostError(BadRequestError):
    message = "본인 글은 신고할 수 없습니다."


class CannotReportSelfError(BadRequestError):
    message = "자기 자신은 신고할 수 없습니다."


class CannotDeletePostForUserReportError(BadRequestError):
    message = "사용자 신고에는 글 삭제를 할 수 없습니다."


class ReportedPostAlreadyDeletedError(BadRequestError):
    message = "이미 삭제된 글입니다. 기각이나 정지로 처리해 주세요."


class ReportedUserNotFoundError(BadRequestError):
    message = "신고당한 사용자가 없어 정지할 수 없습니다."


class CannotSuspendAdminError(BadRequestError):
    message = "관리자는 정지할 수 없습니다."


class PayloadTooLargeError(DomainError):
    """요청 본문(업로드 파일)이 너무 큼. main.py에서 413으로 변환한다."""


class ImageTooLargeError(PayloadTooLargeError):
    message = "사진은 한 장에 5MB까지 올릴 수 있습니다."


class UnprocessableError(DomainError):
    """형식은 받았지만 내용을 처리할 수 없음(예: 이미지가 아닌 파일). main.py에서 422로 변환한다."""


class UnsupportedImageError(UnprocessableError):
    message = "JPG, PNG, WebP 사진만 올릴 수 있습니다."


class TooManyRequestsError(DomainError):
    """짧은 시간에 요청이 너무 많음. main.py에서 429로 변환한다."""

    # 다시 시도해도 되는 시점(초). 429 응답의 Retry-After 헤더로 알려준다.
    retry_after: int = 1

    def __init__(self, retry_after: int | None = None, message: str | None = None) -> None:
        if retry_after is not None:
            self.retry_after = retry_after
        super().__init__(message)


class MessageRateLimitError(TooManyRequestsError):
    message = "메시지를 너무 빠르게 보내고 있습니다. 잠시 후 다시 시도해 주세요."


class ReportRateLimitError(TooManyRequestsError):
    message = "신고를 너무 많이 하고 있습니다. 잠시 후 다시 시도해 주세요."


class ImageUploadRateLimitError(TooManyRequestsError):
    message = "사진을 너무 많이 올리고 있습니다. 잠시 후 다시 시도해 주세요."


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
