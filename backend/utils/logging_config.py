"""日志配置：统一输出到 stdout，由容器运行时收集。

之前后端完全没有日志——Agent 异常只把 str(e) 推给浏览器，服务端不留任何痕迹，
线上出问题无从排查，登录和改权限也没有审计记录。

生产输出单行 JSON（便于日志系统解析），开发输出人类可读文本。
两种格式都不落文件：容器里写文件需要挂卷且会涨满磁盘，stdout 交给
docker logs / 日志采集器是更省心的做法。

**绝不能记录的东西**：SSE 的 JWT 走 query string（EventSource 不能设自定义头），
token 有效期 7 天。access 日志里的 query 必须先经 redact_query() 脱敏。
"""
import json
import logging
import sys
from urllib.parse import parse_qsl, urlencode

from crawler.config import IS_PRODUCTION, get

# query string 里需要脱敏的参数名（小写比较）
_SENSITIVE_PARAMS = {"token", "access_token", "password", "api_key", "secret"}

# LogRecord 的内置字段，JSON 格式化时要跳过，只保留 extra 传进来的自定义键
_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


def redact_query(query: str) -> str:
    """把 query string 里的敏感参数值换成 ***。

    用于 access 日志：SSE 端点会把 JWT 放在 ?token=...，原样记录等于把
    7 天有效期的凭证写进日志文件。
    """
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    if not pairs:
        return query
    return urlencode(
        [(k, "***" if k.lower() in _SENSITIVE_PARAMS else v) for k, v in pairs]
    )


class JsonFormatter(logging.Formatter):
    """单行 JSON，供日志采集器解析。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # extra=... 传进来的自定义字段（request_id / user_id / path 等）
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """开发用：人类可读，把关键 extra 字段附在行尾。"""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _RESERVED and not k.startswith("_")
        }
        if extras:
            base += "  " + " ".join(f"{k}={v}" for k, v in extras.items())
        return base


def setup_logging() -> None:
    """配置根 logger。幂等：重复调用不会叠加 handler。"""
    level_name = (get("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    # 幂等：清掉自己上次装的 handler（reload / 多次 import 时不重复输出）
    for h in list(root.handlers):
        if getattr(h, "_jlpt_handler", False):
            root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if IS_PRODUCTION else TextFormatter())
    handler._jlpt_handler = True  # 标记，便于幂等清理
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn 自己的 access 日志与我们的 access 中间件重复，且它不脱敏 query
    # （SSE 的 token 会原样打进去），关掉它只留我们的。
    logging.getLogger("uvicorn.access").disabled = True
    # uvicorn.error 记的是启动/关闭等生命周期信息，保留但交给根 handler
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    # 第三方库降噪：httpx 每次 LLM 调用都会 INFO 一行请求日志
    for noisy in ("httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
