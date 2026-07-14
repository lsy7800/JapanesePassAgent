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
    DATA_URL = f"{BASE_URL}/jlptshitidata.php"
    DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

    # 每次请求之间的礼貌间隔（秒），避免瞬间轰炸对方服务器被限流/封禁
    REQUEST_DELAY = 1.0
    # 单个请求默认超时（秒），防止个别请求卡死拖垮整轮抓取
    DEFAULT_TIMEOUT = 20

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
        kwargs.setdefault("timeout", self.DEFAULT_TIMEOUT)
        try:
            resp = self.session.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"请求失败: {url}, 错误: {e}")
            return None

    def fetch_post(self, url: str, data: dict | None = None, **kwargs) -> requests.Response | None:
        kwargs.setdefault("timeout", self.DEFAULT_TIMEOUT)
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
        """解析响应内容，由子类实现。

        约定：解析成功返回一条题目 dict（无需含 id，由 crawl 统一补上）；
        解析失败（页面结构异常、字段缺失等）返回 None，让 crawl 跳过该题而非中断整轮。
        """
        raise NotImplementedError("请在子类中实现 parse 方法")

    def crawl(self, *, shitibiao: int, count: int, filename: str, start: int = 1) -> list:
        """通用抓取循环：逐题请求 → parse → 收集，最后统一存盘。

        健壮性保证：
        - 单题请求/解析失败只跳过该题并计入 failed，不会丢掉已抓到的其余题目；
        - 无论中途失败多少，循环结束都会把已成功的题目写入 filename；
        - 每题之间 sleep(REQUEST_DELAY) 礼貌限速。
        """
        if not self.ensure_auth():
            print("认证失败")
            return []

        records: list = []
        failed: list[int] = []

        for index in range(start, start + count):
            print(f"开始解析：{index}")
            try:
                response = self.fetch(
                    url=self.DATA_URL,
                    params={
                        "shitibiaoming": f"t_{shitibiao}",
                        "shitibiao": shitibiao,
                        "tihao": index,
                        "yshipin": 1,
                        "jinru": 0,
                        "yanzheng": 1,
                    },
                )
                if response is None:
                    failed.append(index)
                    continue

                data = self.parse(response)
                if not data:
                    print(f"  ⚠ 第 {index} 题解析为空，跳过")
                    failed.append(index)
                    continue

                data["id"] = index
                records.append(data)
            except Exception as e:  # 单题任何异常都不应中断整轮
                print(f"  ✗ 第 {index} 题异常，跳过: {e}")
                failed.append(index)
            finally:
                time.sleep(self.REQUEST_DELAY)

        self.save_data(filename=filename, data=records)
        summary = f"完成：成功 {len(records)} 题，失败 {len(failed)} 题"
        if failed:
            summary += f"，失败题号: {failed}"
        print(summary)
        return records

    def run(self):
        """爬虫主流程，由子类实现"""
        raise NotImplementedError("请在子类中实现 run 方法")


if __name__ == "__main__":
    username = require("SPIDER_USERNAME")
    password = require("SPIDER_PASSWORD")

    spider = Spider(username, password)
    if spider.ensure_auth():
        spider.run()
