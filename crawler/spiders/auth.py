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
    """访问受保护页判断当前会话是否已登录。

    可靠信号（经站点实测）：
    - 未登录访问受保护页会被重定向回 login.php；
    - 登录页/未登录页含密码输入表单 name="pass"，已登录页则没有。
    不再用 "登录"/"login" 子串判断——已登录首页也含指向 login.php 的账户链接，会误判。
    """
    try:
        resp = session.get(test_url, allow_redirects=True, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException:
        return False
    if resp.status_code != 200:
        return False
    # 被重定向到登录页 => 未登录
    if "login.php" in resp.url.lower():
        return False
    # 页面仍带登录表单（密码框）=> 未登录
    if 'name="pass"' in resp.text:
        return False
    return True


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
