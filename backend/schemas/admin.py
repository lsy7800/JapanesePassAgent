"""管理后台相关 Pydantic 模型。"""
from pydantic import BaseModel, Field


class LabelCount(BaseModel):
    """通用「标签 - 数量」对，用于级别/题型分布。"""
    label: str
    count: int


class OverviewResponse(BaseModel):
    total_questions: int          # 题组总数
    total_users: int              # 用户总数
    total_exams: int              # 已提交考试数
    avg_accuracy: float           # 全平台平均正确率（百分比）
    by_level: list[LabelCount]    # 各级别题量
    by_type: list[LabelCount]     # 各题型题量


class UserAdminOut(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: str
    exam_count: int               # 该用户已提交考试数


class UserListResponse(BaseModel):
    items: list[UserAdminOut]
    page: int
    page_size: int
    total: int


class UserUpdateRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(student|admin)$")
    is_active: bool | None = None
