from lxml import etree
from crawler.spiders.spider import Spider


class TestType3(Spider):
    """shitibiao 71：句子语法1（文法形式判断）。

    题干带括号空「（　）」，四个选项为语法形式（扁平 label/span 列表），无划线词。
    结构上选项抽取与 type_1 一致，但语义是填空选语法，故 marked 应为空。
    """
    SHITIBIAO = 71
    COUNT = 280

    def parse(self, response):
        html = etree.HTML(response.text)
        if html is None:
            return None
        question = html.xpath("//div[@class='jumbotron']//p//span//text()")
        choice = html.xpath("//div[@class='jumbotron']//label/span/text()")
        meta = html.xpath("//form//p//span//text()")
        analysis = html.xpath("//div[@class='jumbotron ']/span//text()")

        # answer/date 取自 meta 末尾两项；结构异常缺项则跳过该题，避免 IndexError 中断整轮
        if len(meta) < 2:
            print("  ⚠ 页面缺少答案/日期字段，跳过")
            return None

        # 返回下游校验器（validate.py type_3）所需字段：扁平 choice、无 under_word
        return {
            "text": question,
            "choice": choice,
            "answer": meta[-2],
            "analysis": analysis,
            "date": meta[-1],
        }

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")


if __name__ == '__main__':
    from crawler.config import require
    spider = TestType3(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()
