# 모델을 여기서 import해야 Base.metadata에 등록되어 create_all 대상이 된다.
from app.models.block import UserBlock
from app.models.conversation import Conversation, Message
from app.models.post import BookCondition, Post, PostStatus
from app.models.post_image import MAX_IMAGES_PER_POST, PostImage
from app.models.report import Report, ReportReason, ReportStatus, ReportTargetType
from app.models.user import User
from app.models.wishlist import Wishlist

__all__ = [
    "MAX_IMAGES_PER_POST",
    "BookCondition",
    "Conversation",
    "Message",
    "Post",
    "PostImage",
    "PostStatus",
    "Report",
    "ReportReason",
    "ReportStatus",
    "ReportTargetType",
    "User",
    "UserBlock",
    "Wishlist",
]
