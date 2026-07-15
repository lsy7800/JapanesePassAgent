import re
from lxml import etree
from crawler.spiders.spider import Spider


class TestType5(Spider):
    """shitibiao 73：文章语法（text_grammar）——一篇文章 + 若干填空小题。

    历史录入用固定模板：一篇文章配 5 个 icheck 组，但真实题数可少于 5，
    多出的子题选项被填成「请勾选1」占位（占位永远在末尾）。真实题数 K =
    非占位的 icheck 组数。无年份的篇不采集。

    输出为嵌套结构：article（空归一化为 （1）…（K）） + questions[]（每题选项/答案/解析）。
    """
    SHITIBIAO = 73
    COUNT = 34

    # 空标记（历史录入不统一）：括号（N）、方括号【N】、下划线 __N__，
    # 数字全/半角均可，可带 -字母后缀（成对空 4-a/4-b）。
    BLANK_RE = re.compile(
        r'[（(]\s*([0-9０-９]+)\s*[-－]?\s*([a-zA-Zａ-ｚＡ-Ｚ])?\s*[）)]'
        r'|[【［]\s*([0-9０-９]+)\s*[-－]?\s*([a-zA-Zａ-ｚＡ-Ｚ])?\s*[】］]'
        r'|[_＿]{1,3}\s*([0-9０-９]+)\s*[-－]?\s*([a-zA-Zａ-ｚＡ-Ｚ])?\s*[_＿]{1,3}'
    )

    @staticmethod
    def _blank_parts(m):
        """从三选一分支的 match 里取出 (数字, 字母后缀)。"""
        num = m.group(1) or m.group(3) or m.group(5)
        suf = m.group(2) or m.group(4) or m.group(6) or ''
        return num, suf

    @staticmethod
    def _is_padding(opts):
        return bool(opts) and any(('勾选' in o or '勾選' in o) for o in opts)

    @staticmethod
    def _block_text(el):
        """把一个节点序列化为纯文本，<br>/</p> 转换行，保留段落结构。"""
        s = etree.tostring(el, encoding='unicode')
        s = re.sub(r'<br\s*/?>', '\n', s, flags=re.I)
        s = re.sub(r'</p\s*>', '\n', s, flags=re.I)
        s = re.sub(r'<[^>]+>', '', s)
        s = re.sub(r'[ \t 　]+', ' ', s)
        s = re.sub(r'\n[ \t]*', '\n', s)
        s = re.sub(r'\n{2,}', '\n', s)
        return s.strip()

    def parse(self, response):
        html = etree.HTML(response.text)
        if html is None:
            return None
        jbs = html.xpath("//div[@class='jumbotron']")
        if not jbs:
            return None

        # 年份/日期：meta 中匹配 20XX；没有则不采集
        meta = [x.strip() for x in html.xpath("//form//p//span//text()") if x.strip()]
        date = next((m for m in meta if re.search(r'20\d\d', m)), '')
        if not date:
            print("  ↷ 无年份，跳过不采集")
            return None

        # 真实题数 K：从 icheck1 起数非占位组，遇占位即止（占位永远在末尾）
        groups = sorted(set(html.xpath("//input[starts-with(@name,'icheck')]/@name")),
                        key=lambda x: int(x[6:]))
        questions = []
        for g in groups:
            opts = [o.strip() for o in html.xpath(
                f"//label[input[@name='{g}']]/span[@class='con']/text()")]
            if self._is_padding(opts):
                break
            ans = html.xpath(f"//input[@name='{g}' and @checked]/@value")
            questions.append({"no": int(g[6:]), "options": opts, "answer": ans[0] if ans else ""})
        if not questions:
            print("  ⚠ 未找到真实小题，跳过")
            return None
        K = len(questions)

        # 文章：第 1 个 jumbotron 的 con；把空按出现顺序归一化为 （1）…（M）
        con = jbs[0].xpath(".//span[@class='con']")
        article = self._block_text(con[0]) if con else ''
        order = []
        for m in self.BLANK_RE.finditer(article):
            num, _ = self._blank_parts(m)
            if num not in order:
                order.append(num)
        remap = {base: i + 1 for i, base in enumerate(order)}

        def _sub(m):
            num, suf = self._blank_parts(m)
            return f'（{remap.get(num, num)}{suf}）'
        article = self.BLANK_RE.sub(_sub, article)
        M = len(order)

        # 解析：第 2 个 jumbotron。历史录入格式不统一（【问题N】/（N）/整篇翻译…），
        # 逐题精确拆分不可靠，故按篇整块存原始解析，留待 LLM 校验阶段结构化到每题。
        analysis = self._block_text(jbs[1]) if len(jbs) > 1 else ''

        return {
            "date": date,
            "article": article,
            "n_questions": K,
            # 归一化到的空数与真实题数不一致 → 文章空标记异常，需人工核对
            "blank_mismatch": (M != K),
            "questions": questions,
            "analysis": analysis,
        }

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")


if __name__ == '__main__':
    from crawler.config import require
    spider = TestType5(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()
