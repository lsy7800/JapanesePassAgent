"""题库相关的 Pydantic 响应模型。

对应 README「API 设计」章节的响应格式。

富文本向后兼容：content / analysis / option.content / article 字段用 str | list
联合类型。当前数据库存的是纯文本（str），直接返回；未来升级为富文本
JSON（InlineTextNode[] / BlockNode[]）后同一模型也能承载，无需改动接口契约。
"""
from typing import Union

from pydantic import BaseModel, Field

# 富文本字段：当前为纯文本 str，未来可为富文本节点数组
RichText = Union[str, list]


class OptionOut(BaseModel):
    label: str = Field(description="选项标签：a/b/c/d")
    content: RichText = Field(description="选项内容")


class QuestionOut(BaseModel):
    seq: int = Field(description="题组内顺序号，单选题固定为 1")
    content: RichText | None = Field(default=None, description="题干内容")
    marked: str = Field(default="", description="划线词/标记词")
    answer: str = Field(description="正确答案：a/b/c/d")
    analysis: RichText | None = Field(default=None, description="解析文本")
    options: list[OptionOut] = Field(default_factory=list)


class QuestionGroupOut(BaseModel):
    """完整题组，含所有子题和选项（GET /questions/{group_id}）。"""
    id: int
    type: str = Field(description="题型：single_choice/cloze/reading")
    article: RichText | None = Field(default=None, description="文章内容，单选题为 null")
    level: str = Field(default="", description="级别：N1~N5")
    exam_date: str = Field(default="", description="考试日期，如 2023-07")
    difficulty: int = Field(default=0, description="难度评级 1-9")
    knowledge_points: list[str] = Field(default_factory=list)
    questions: list[QuestionOut] = Field(default_factory=list)


class QuestionGroupSummary(BaseModel):
    """题组摘要，用于列表接口（不含子题与选项）。"""
    id: int
    type: str
    level: str = ""
    exam_date: str = ""
    difficulty: int = 0
    knowledge_points: list[str] = Field(default_factory=list)


class QuestionListResponse(BaseModel):
    items: list[QuestionGroupSummary]
    page: int
    page_size: int
    total: int
