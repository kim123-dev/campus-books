# 모델을 여기서 import해야 Base.metadata에 등록되어 create_all 대상이 된다.
from app.models.block import UserBlock
from app.models.book_alert import MAX_ALERTS_PER_USER, AlertNotification, BookAlert
from app.models.conversation import Conversation, Message
from app.models.post import BookCondition, Post, PostStatus
from app.models.post_image import MAX_IMAGES_PER_POST, PostImage
from app.models.report import Report, ReportAction, ReportReason, ReportStatus, ReportTargetType
from app.models.user import User, UserRole
from app.models.wishlist import Wishlist

__all__ = [
    "MAX_ALERTS_PER_USER",
    "AlertNotification",
    "BookAlert",
    "MAX_IMAGES_PER_POST",
    "BookCondition",
    "Conversation",
    "Message",
    "Post",
    "PostImage",
    "PostStatus",
    "Report",
    "ReportAction",
    "ReportReason",
    "ReportStatus",
    "ReportTargetType",
    "User",
    "UserRole",
    "UserBlock",
    "Wishlist",
]
