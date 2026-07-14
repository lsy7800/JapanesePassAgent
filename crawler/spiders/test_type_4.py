from lxml import etree
from crawler.spiders.spider import Spider


class TestType4(Spider):
    """shitibiao 72：句子语法2（文の組み立て / 排序题）。

    题干含 4 个连续空位（原页面用 <u> 标注），其中一个为 ★（本库固定第 3 个）。
    四个选项是待排序的句子碎片，答案 = ★ 处应填的选项号（取自 meta[-2]）。

    采用「方式 B」：content 存成可读句子，把 4 个 <u> 归一化为空位标记，
    普通空写作「＿＿」、★ 空写作「＿★＿」，前后段文本原样保留。
    这样既能被 LLM 校验/向量化当作自然句处理，前端也可按标记 split 成结构化槽位渲染。
    """
    SHITIBIAO = 72
    COUNT = 120

    BLANK = "＿＿"
    BLANK_STAR = "＿★＿"

    def parse(self, response):
        html = etree.HTML(response.text)
        if html is None:
            return None

        spans = html.xpath("//div[@class='jumbotron']//p/span")
        choice = html.xpath("//div[@class='jumbotron']//label/span/text()")
        meta = html.xpath("//form//p//span//text()")
        analysis = html.xpath("//div[@class='jumbotron ']/span//text()")

        if not spans or len(meta) < 2:
            print("  ⚠ 页面缺少题干/答案字段，跳过")
            return None

        span = spans[0]
        blanks = span.findall("u")
        if len(blanks) < 2:
            print("  ⚠ 题干未找到排序空位，跳过")
            return None

        # 重建题干：前段文本 + 各空位标记（★ 保留）+ 段间/末尾文本
        text = (span.text or "").strip()
        n = len(blanks)
        for i, u in enumerate(blanks):
            u_content = "".join(u.itertext())
            marker = self.BLANK_STAR if "★" in u_content else self.BLANK
            text += " " + marker
            tail = (u.tail or "").strip()
            if tail:  # 段间为全角空格（strip 后为空）→ 跳过；末尾为后段文本 → 保留
                text += " " + tail

        return {
            "text": text,
            "choice": [c.strip() for c in choice],
            "answer": meta[-2].strip(),
            "analysis": analysis,
            "date": meta[-1].strip(),
        }

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")


if __name__ == '__main__':
    from crawler.config import require
    spider = TestType4(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()
