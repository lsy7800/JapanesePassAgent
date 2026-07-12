import json
import time
from pathlib import Path
from typing import Any, Callable
import requests

from crawler.config import SPIDER_BASE_URL, require
from crawler.spiders.auth import login, load_cookies, save_cookies, is_cookie_valid


class Spider:
    BASE_URL = SPIDER_BASE_URL
    LOGIN_URL = f"{BASE_URL}/login.php"
    DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

    def __init__(self, username: str, password: str):
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)

    def ensure_auth(self) -> bool:
        if load_cookies(self.session) and is_cookie_valid(self.session, self.BASE_URL + "/index.php"):
            print("Cookie有效，跳过登录")
            return True
        print("Cookie无效或不存在，开始登录...")
        if login(self.session, self.LOGIN_URL, self.username, self.password):
            print("登录成功")
            return True
        print("登录失败")
        return False

    def fetch(self, url: str, **kwargs) -> requests.Response | None:
        try:
            resp = self.session.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"请求失败: {url}, 错误: {e}")
            return None

    def fetch_post(self, url: str, data: dict | None = None, **kwargs) -> requests.Response | None:
        try:
            resp = self.session.post(url, data=data, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"POST请求失败: {url}, 错误: {e}")
            return None

    def save_data(self, filename: str, data: Any) -> Path:
        filepath = self.DATA_DIR / filename
        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"数据已保存: {filepath}")
        return filepath

    def load_data(self, filename: str) -> Any | None:
        filepath = self.DATA_DIR / filename
        if filepath.exists():
            return json.loads(filepath.read_text())
        return None

    def parse(self, response: requests.Response) -> Any:
        """解析响应内容，由子类实现"""
        raise NotImplementedError("请在子类中实现 parse 方法")

    def run(self):
        """爬虫主流程，由子类实现"""
        raise NotImplementedError("请在子类中实现 run 方法")


if __name__ == "__main__":
    username = require("SPIDER_USERNAME")
    password = require("SPIDER_PASSWORD")

    spider = Spider(username, password)
    if spider.ensure_auth():
        spider.run()
