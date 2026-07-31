# 后端镜像。多阶段构建：builder 装依赖，运行阶段只带 venv 和源码。
#
# 依赖用 `uv sync --frozen` 安装——pyproject.toml 里所有依赖都是无上界的 `>=`
# （fastapi>=0.115 实际能解析到 0.139），只有走 uv.lock 才是可复现的构建。
# 改了依赖要先 `uv lock` 再重建镜像，否则这里会因 lock 不匹配直接失败。
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# 先只拷依赖清单：源码变动时这层缓存仍然有效
COPY pyproject.toml uv.lock ./
# --no-install-project：此时还没有源码，只装第三方依赖
# --no-dev：跳过 pytest/httpx，运行时不需要
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY backend/ ./backend/
COPY crawler/ ./crawler/
COPY scripts/ ./scripts/

# 再跑一次把项目自身装进 venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.14-slim-bookworm AS runtime

# 非 root 运行：容器逃逸时少一层权限
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/backend /app/backend
COPY --from=builder --chown=app:app /app/crawler /app/crawler
COPY --from=builder --chown=app:app /app/scripts /app/scripts

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV=production

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

# 生产不能带 --reload。
# --timeout-keep-alive 拉长到 120s：Agent 对话和智能组卷是 SSE 长连接，
# ReAct 循环要多轮 DeepSeek 往返，默认 5s 会把流掐断。
# 单 worker 起步；agent 是无状态的模块级单例，要扩就直接加 --workers。
CMD ["uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--timeout-keep-alive", "120", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
