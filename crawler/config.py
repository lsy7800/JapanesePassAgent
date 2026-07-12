"""集中管理配置，从项目根目录的 .env 文件加载环境变量。

无第三方依赖：自行解析 .env，避免引入 python-dotenv。
已存在于系统环境中的变量优先，不会被 .env 覆盖。
"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def _load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # 系统环境变量优先
        os.environ.setdefault(key, value)


_load_env()


def get(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"缺少必要的环境变量: {name}。请复制 .env.example 为 .env 并填写。"
        )
    return value


# ========== 数据库配置 ==========
DB_CONFIG = {
    "host": get("DB_HOST", "localhost"),
    "port": int(get("DB_PORT", "3306")),
    "user": get("DB_USER", "root"),
    "password": get("DB_PASSWORD", ""),
    "database": get("DB_NAME", "jlpt"),
    "charset": "utf8mb4",
}

# ========== LLM 配置 ==========
DEEPSEEK_API_URL = get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = get("DEEPSEEK_MODEL", "deepseek-chat")

# ========== 爬虫配置 ==========
SPIDER_BASE_URL = get("SPIDER_BASE_URL", "http://account.for-test.cn")

# ========== 服务配置 ==========
API_HOST = get("API_HOST", "0.0.0.0")
API_PORT = int(get("API_PORT", "8000"))
