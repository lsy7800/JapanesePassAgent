"""智能组卷的编排层：把「薄弱点聚合 → LLM 规划 → 确定性建卷」三步串起来。

提供两种驱动方式，共用同一套步骤实现，避免逻辑分叉：
- run_smart_exam()     同步执行全流程，供 POST /exams/smart-generate 使用
- stream_smart_exam()  异步生成器，逐阶段 yield 事件，供 SSE 端点使用

阶段化反馈的意义：LLM 规划通常要十几秒，期间前端只能干等。逐阶段推送让用户
看到「在分析薄弱点 / 在规划 / 方案是什么 / 在抽题」，并能在方案确定的那一刻
就先读到 rationale，而不必等整卷落库。

耗时步骤（DB 聚合、LLM 调用、抽题落库）都是同步阻塞的，在异步路径里统一用
asyncio.to_thread 丢到线程池，避免占住事件循环拖慢其他请求。
"""
import asyncio
from contextlib import contextmanager
from typing import AsyncGenerator

from backend.config.categories import category_name, get_categories
from backend.db.chat_repo import open_conn
from backend.services.exam_builder import build_exam
from backend.services.exam_planner import plan_exam
from backend.services.stats_service import compute_weak_points

# 规划时喂给 LLM 的薄弱点条数上限（太多会稀释提示重点）
WEAK_LIMIT = 8


class NoQuestionsError(Exception):
    """题池为空，无法组卷。路由层转 422。"""


@contextmanager
def _reuse(conn):
    """把已有连接包装成与 open_conn 相同的上下文协议，并提交/回滚该连接。

    同步路径必须复用请求连接：在 REPEATABLE READ 下，另开连接提交的新试卷不在请求
    连接既有的读快照里，随后 _build_exam 会查不到刚建的卷而 404。
    """
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _load_weak(user_id: int, conn=None) -> list[dict]:
    src = _reuse(conn) if conn is not None else open_conn()
    with src as c:
        with c.cursor() as cur:
            return compute_weak_points(cur, user_id)


def _available_categories(level: str | None) -> list[dict]:
    return [
        {"code": c["code"], "name": c["name"]}
        for c in get_categories(level=level, examable_only=True)
    ]


def _plans_from(plan: dict) -> list[tuple[str | None, int]]:
    """把 LLM 方案转成 build_exam 的 plans 参数。

    有题型配额时逐题型一段；否则单池按总题数抽（整场模式靠 exam_date 收窄）。
    """
    quotas = plan.get("category_quotas")
    if quotas:
        return [(code, cnt) for code, cnt in quotas.items()]
    return [(None, plan["total_questions"])]


def _build(plan: dict, time_limit: int, user_id: int, conn=None) -> dict:
    """按方案抽题落库，返回 build_exam 结果。题池为空时抛 NoQuestionsError。"""
    src = _reuse(conn) if conn is not None else open_conn()
    with src as c:
        with c.cursor() as cur:
            result = build_exam(
                cur,
                level=plan["level"],
                plans=_plans_from(plan),
                difficulty_min=plan.get("difficulty_min"),
                difficulty_max=plan.get("difficulty_max"),
                time_limit=time_limit,
                user_id=user_id,
                exam_date=plan.get("exam_date"),
                unlimited=plan.get("whole_exam", False),
            )
            if not result["exam_id"]:
                # 抛出后 open_conn 回滚，不留半张空卷
                raise NoQuestionsError("没有符合条件的题目，请调整需求后再试")
            return result


def _plan_summary(plan: dict) -> str:
    """把方案压成一行人话，供前端在「方案已确定」阶段展示。"""
    quotas = plan.get("category_quotas")
    if quotas:
        parts = [f"{category_name(code)} {cnt} 题" for code, cnt in quotas.items()]
        body = "、".join(parts)
    else:
        body = f"共 {plan['total_questions']} 题"
    bits = [plan.get("level") or "N1", body]
    if plan.get("exam_date"):
        bits.insert(1, f"{plan['exam_date']} 真题")
    return " · ".join(bits)


def run_smart_exam(
    requirement: str, level: str | None, time_limit: int, user_id: int, conn=None
) -> dict:
    """同步全流程，返回 {plan, exam_id, total, shortfalls}。

    conn: 调用方的请求连接。传入则复用（同一读快照，随后能查到刚建的卷）；
    不传则自开连接，供脱离请求上下文的场景使用。
    """
    weak = _load_weak(user_id, conn)
    plan = plan_exam(requirement, weak[:WEAK_LIMIT], level, _available_categories(level))
    result = _build(plan, time_limit, user_id, conn)
    return {"plan": plan, **result}


async def stream_smart_exam(
    requirement: str, level: str | None, time_limit: int, user_id: int
) -> AsyncGenerator[dict, None]:
    """逐阶段 yield 事件 dict，供路由包装成 SSE。

    事件序列（正常路径）：
      stage(weak) → stage(plan) → plan(方案+rationale) → stage(build) → done(exam_id)
    异常路径以 error 事件收尾（含 code：no_questions / internal）。
    """
    try:
        yield {"type": "stage", "key": "weak", "message": "正在分析你的历史错题与薄弱知识点…"}
        weak = await asyncio.to_thread(_load_weak, user_id)

        top = [w["point"] for w in weak[:3]]
        yield {
            "type": "stage",
            "key": "weak_done",
            "message": (
                f"已定位薄弱点：{'、'.join(top)}" if top
                else "暂无历史错题记录，将按该级别均衡出题"
            ),
            "weak_count": len(weak),
        }

        yield {"type": "stage", "key": "plan", "message": "AI 正在规划组卷方案，通常需要 10~30 秒…"}
        available = _available_categories(level)
        plan = await asyncio.to_thread(
            plan_exam, requirement, weak[:WEAK_LIMIT], level, available
        )

        # 方案一确定就先把 rationale 推给前端，用户不必等落库
        yield {
            "type": "plan",
            "summary": _plan_summary(plan),
            "rationale": plan["rationale"],
        }

        yield {"type": "stage", "key": "build", "message": "正在从题库抽题、生成试卷…"}
        result = await asyncio.to_thread(_build, plan, time_limit, user_id)

        # groups 是题组数，不等于可评分子题数（阅读一篇文章可含多问）；
        # 真实题量由前端随后 GET /exams/{id} 取回的 total 决定，此处仅作进度信息。
        yield {
            "type": "done",
            "exam_id": result["exam_id"],
            "groups": result["total"],
            "rationale": plan["rationale"],
            "shortfalls": result["shortfalls"],
        }
    except NoQuestionsError as e:
        yield {"type": "error", "code": "no_questions", "detail": str(e)}
    except Exception as e:
        yield {"type": "error", "code": "internal", "detail": f"组卷失败：{e}"}
