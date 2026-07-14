import json
import time
from pathlib import Path
from http.cookiejar import MozillaCookieJar
from urllib.parse import urljoin
import requests

COOKIE_FILE = Path(__file__).parent.parent.parent / "data" / "cookies.json"

# 网络请求默认超时（秒）
DEFAULT_TIMEOUT = 20


def save_cookies(session: requests.Session) -> None:
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cookies = []
    for cookie in session.cookies:
        cookies.append({
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path,
            "expires": cookie.expires,
            "secure": cookie.secure,
        })
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))


def load_cookies(session: requests.Session) -> bool:
    if not COOKIE_FILE.exists():
        return False
    cookies = json.loads(COOKIE_FILE.read_text())
    now = time.time()
    for c in cookies:
        if c.get("expires") and c["expires"] < now:
            continue
        session.cookies.set(
            c["name"],
            c["value"],
            domain=c.get("domain"),
            path=c.get("path"),
        )
    return True


def is_cookie_valid(session: requests.Session, test_url: str) -> bool:
    try:
        resp = session.get(test_url, allow_redirects=True, timeout=DEFAULT_TIMEOUT)
        # 如果被重定向到登录页，或页面包含登录表单，说明 cookie 无效
        if "login" in resp.url.lower():
            return False
        if "登录" in resp.text or "login" in resp.text.lower():
            return False
        return resp.status_code == 200
    except requests.RequestException:
        return False


def login(session: requests.Session, login_url: str, username: str, password: str,
          verify_url: str | None = None) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "http://account.for-test.cn",
        "Referer": login_url,
    }
    try:
        resp = session.post(
            login_url,
            data={"email": username, "pass": password, "submitted": "TRUE"},
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"登录请求失败: {e}")
        return False

    # 关键：登录失败时服务器同样返回 200 并重新渲染登录页，仅凭状态码无法判断成败。
    # 用受保护页确认确实已登录，成功后才落盘 cookie，避免把无效凭据写进 cookies.json。
    if verify_url is None:
        verify_url = urljoin(login_url, "/index.php")
    if not is_cookie_valid(session, verify_url):
        print("登录校验未通过：账号密码可能有误，或站点结构已变化")
        return False

    save_cookies(session)
    return True


if __name__ == '__main__':
    from crawler.config import SPIDER_BASE_URL, require

    login_url = f"{SPIDER_BASE_URL}/login.php"
    username = require("SPIDER_USERNAME")
    password = require("SPIDER_PASSWORD")
    session = requests.Session()
    ok = login(session, login_url, username, password)
    print("登录成功" if ok else "登录失败")
