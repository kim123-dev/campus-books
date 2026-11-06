# 모델을 여기서 import해야 Base.metadata에 등록되어 create_all 대상이 된다.
from app.models.user import User

__all__ = ["User"]
