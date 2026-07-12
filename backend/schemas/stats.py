"""学习分析相关 Pydantic 模型。"""
from pydantic import BaseModel, Field


class WeakPoint(BaseModel):
    point: str
    wrong_count: int
    total_count: int
    error_rate: float  # 百分比，如 66.7


class WeakPointsResponse(BaseModel):
    items: list[WeakPoint]
    total: int  # 薄弱点总数（未分页前）


class HistoryPoint(BaseModel):
    exam_id: int
    date: str
    level: str
    total: int
    score: int
    accuracy: float  # 百分比


class HistoryResponse(BaseModel):
    points: list[HistoryPoint]


class WrongQuestionsRequest(BaseModel):
    knowledge_point: str | None = Field(default=None, description="按知识点筛选")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class WrongQuestionItem(BaseModel):
    group_id: int
    level: str
    knowledge_points: list[str]
    content: str
    options: dict[str, str]
    correct_answer: str
    analysis: str


class WrongQuestionsResponse(BaseModel):
    items: list[WrongQuestionItem]
    total: int
