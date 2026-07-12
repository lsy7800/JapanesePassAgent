import json
import time
from pathlib import Path
from http.cookiejar import MozillaCookieJar
import requests

COOKIE_FILE = Path(__file__).parent.parent.parent / "data" / "cookies.json"


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
        resp = session.get(test_url, allow_redirects=True)
        # 如果被重定向到登录页，或页面包含登录表单，说明 cookie 无效
        if "login" in resp.url.lower():
            return False
        if "登录" in resp.text or "login" in resp.text.lower():
            return False
        return resp.status_code == 200
    except requests.RequestException:
        return False


def login(session: requests.Session, login_url: str, username: str, password: str) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "http://account.for-test.cn",
        "Referer": login_url,
    }
    try:
        resp = session.post(login_url, data={"email": username, "pass": password, "submitted": "TRUE"}, headers=headers)
        save_cookies(session)

        return resp.status_code == 200
    except requests.RequestException:
        return False


if __name__ == '__main__':
    from crawler.config import SPIDER_BASE_URL, require

    login_url = f"{SPIDER_BASE_URL}/login.php"
    username = require("SPIDER_USERNAME")
    password = require("SPIDER_PASSWORD")
    session = requests.Session()
    login(session, login_url, username, password)
