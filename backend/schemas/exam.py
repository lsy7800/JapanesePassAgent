"""考试/组卷相关的 Pydantic 模型。

对应 README「API 设计 - 考试与做题」。
试卷题目（ExamItemOut）刻意不含 answer/analysis，避免作答时泄漏答案；
答案与解析只在提交后的结果（ResultItemOut）中返回。
"""
from typing import Union

from pydantic import BaseModel, Field, field_validator, model_validator

RichText = Union[str, list]
VALID_LABELS = {"a", "b", "c", "d"}
VALID_TYPES = {"single_choice", "cloze", "reading"}


# ========== 组卷请求 ==========

class ExamGenerateRequest(BaseModel):
    level: str | None = Field(default=None, description="目标级别 N1~N5，不传则不限")
    types: list[str] = Field(default_factory=list, description="题型筛选，空表示全部")
    total_questions: int = Field(default=20, ge=1, le=200, description="试卷题目数")
    difficulty_range: list[int] | None = Field(default=None, description="难度区间 [min, max]，各 0-9")
    time_limit_minutes: int = Field(default=0, ge=0, description="限时（分钟），0 不限")

    @field_validator("types")
    @classmethod
    def _check_types(cls, v):
        bad = [t for t in v if t not in VALID_TYPES]
        if bad:
            raise ValueError(f"非法题型 {bad}，合法值 {sorted(VALID_TYPES)}")
        return v

    @field_validator("difficulty_range")
    @classmethod
    def _check_range(cls, v):
        if v is None:
            return v
        if len(v) != 2:
            raise ValueError("difficulty_range 必须是 [min, max] 两个元素")
        lo, hi = v
        if not (0 <= lo <= 9 and 0 <= hi <= 9):
            raise ValueError("难度必须在 0-9 之间")
        if lo > hi:
            raise ValueError("difficulty_range 的 min 不能大于 max")
        return v


# ========== 试卷（作答用，不含答案） ==========

class ExamOptionOut(BaseModel):
    label: str
    content: RichText


class ExamItemOut(BaseModel):
    seq: int = Field(description="题目在试卷中的序号")
    group_id: int
    type: str
    level: str = ""
    content: RichText | None = None
    marked: str = ""
    options: list[ExamOptionOut] = Field(default_factory=list)


class ExamOut(BaseModel):
    id: int
    level: str = ""
    total: int
    time_limit: int = 0
    status: str
    items: list[ExamItemOut] = Field(default_factory=list)


# ========== 提交作答 ==========

class AnswerIn(BaseModel):
    seq: int = Field(ge=1)
    answer: str

    @field_validator("answer")
    @classmethod
    def _check_answer(cls, v):
        if v not in VALID_LABELS:
            raise ValueError(f"答案必须是 a/b/c/d，收到 {v!r}")
        return v


class SubmitRequest(BaseModel):
    answers: list[AnswerIn] = Field(min_length=1, description="逐题作答 [{seq, answer}]")

    @model_validator(mode="after")
    def _unique_seq(self):
        seqs = [a.seq for a in self.answers]
        if len(seqs) != len(set(seqs)):
            raise ValueError("answers 中 seq 不能重复")
        return self


# ========== 结果（含答案与解析） ==========

class ResultItemOut(BaseModel):
    seq: int
    group_id: int
    content: RichText | None = None
    options: list[ExamOptionOut] = Field(default_factory=list)
    user_answer: str | None = None
    correct_answer: str = ""
    is_correct: bool = False
    analysis: RichText | None = None


class ExamResultOut(BaseModel):
    id: int
    level: str = ""
    total: int
    score: int = 0
    status: str
    items: list[ResultItemOut] = Field(default_factory=list)
