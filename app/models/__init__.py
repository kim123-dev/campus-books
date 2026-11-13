# 모델을 여기서 import해야 Base.metadata에 등록되어 create_all 대상이 된다.
from app.models.admin_action import AdminAction, AdminActionType, AdminTargetType
from app.models.banned_email import BannedEmail
from app.models.block import UserBlock
from app.models.book_alert import MAX_ALERTS_PER_USER, AlertNotification, BookAlert
from app.models.conversation import Conversation, ConversationUserState, Message
from app.models.nickname_change import NicknameChange
from app.models.post import BookCondition, Post, PostStatus
from app.models.post_image import MAX_IMAGES_PER_POST, PostImage
from app.models.recovery import PasswordResetAttempt, RecoveryCode
from app.models.report import (
    MessageReportSnapshot,
    Report,
    ReportAction,
    ReportReason,
    ReportStatus,
    ReportTargetType,
)
from app.models.review import Review, ReviewRating
from app.models.trade import Trade
from app.models.user import User, UserRole
from app.models.wishlist import Wishlist

__all__ = [
    "AdminAction",
    "AdminActionType",
    "AdminTargetType",
    "BannedEmail",
    "MAX_ALERTS_PER_USER",
    "AlertNotification",
    "BookAlert",
    "MAX_IMAGES_PER_POST",
    "BookCondition",
    "Conversation",
    "ConversationUserState",
    "Message",
    "MessageReportSnapshot",
    "NicknameChange",
    "PasswordResetAttempt",
    "Post",
    "PostImage",
    "PostStatus",
    "RecoveryCode",
    "Report",
    "ReportAction",
    "ReportReason",
    "ReportStatus",
    "ReportTargetType",
    "Review",
    "ReviewRating",
    "Trade",
    "User",
    "UserRole",
    "UserBlock",
    "Wishlist",
]
