"""题库相关的 Pydantic 响应模型。

对应 README「API 设计」章节的响应格式。

富文本向后兼容：content / analysis / option.content / article 字段用 str | list
联合类型。当前数据库存的是纯文本（str），直接返回；未来升级为富文本
JSON（InlineTextNode[] / BlockNode[]）后同一模型也能承载，无需改动接口契约。
"""
from typing import Union

from pydantic import BaseModel, Field, field_validator, model_validator

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
    source: str | None = None


class QuestionListResponse(BaseModel):
    items: list[QuestionGroupSummary]
    page: int
    page_size: int
    total: int


class SourceStat(BaseModel):
    """题库批次统计（GET /sources）。"""
    source: str = Field(description="来源标识，如 result_67_validated")
    count: int = Field(description="该批次题组数")


# ========== 写接口输入模型 ==========

VALID_TYPES = {"single_choice", "cloze", "reading"}
VALID_LABELS = {"a", "b", "c", "d"}


class OptionIn(BaseModel):
    label: str = Field(description="选项标签：a/b/c/d")
    content: RichText = Field(description="选项内容")

    @field_validator("label")
    @classmethod
    def _check_label(cls, v):
        if v not in VALID_LABELS:
            raise ValueError(f"选项标签必须是 a/b/c/d，收到 {v!r}")
        return v


class QuestionIn(BaseModel):
    seq: int = Field(default=1, ge=1, description="题组内顺序号")
    content: RichText | None = Field(default=None, description="题干内容")
    marked: str = Field(default="", description="划线词/标记词")
    answer: str = Field(description="正确答案：a/b/c/d")
    analysis: RichText | None = Field(default=None, description="解析文本")
    options: list[OptionIn]

    @field_validator("answer")
    @classmethod
    def _check_answer(cls, v):
        if v not in VALID_LABELS:
            raise ValueError(f"答案必须是 a/b/c/d，收到 {v!r}")
        return v

    @model_validator(mode="after")
    def _check_options(self):
        labels = {o.label for o in self.options}
        if labels != VALID_LABELS:
            raise ValueError(f"选项必须恰好包含 a/b/c/d，收到 {sorted(labels)}")
        return self


class QuestionGroupCreate(BaseModel):
    """创建/全量替换题组的请求体（POST 与 PUT 复用）。"""
    type: str = Field(description="题型：single_choice/cloze/reading")
    article: RichText | None = Field(default=None, description="文章内容，单选题为 null")
    level: str = Field(default="", description="级别：N1~N5")
    exam_date: str = Field(default="", description="考试日期，如 2023-07")
    difficulty: int = Field(default=0, ge=0, le=9, description="难度评级 0-9")
    knowledge_points: list[str] = Field(default_factory=list)
    questions: list[QuestionIn] = Field(min_length=1, description="至少一道子题")

    @field_validator("type")
    @classmethod
    def _check_type(cls, v):
        if v not in VALID_TYPES:
            raise ValueError(f"题型必须是 {sorted(VALID_TYPES)}，收到 {v!r}")
        return v

