from lxml import etree
from crawler.spiders.spider import Spider

class TestType1(Spider):
    # 试题表编号（对方站点的 shitibiao 参数）与抓取题数
    SHITIBIAO = 69
    COUNT = 165

    def parse(self, response):
        html = etree.HTML(response.text)
        if html is None:
            return None
        question = html.xpath("//div[@class='jumbotron']//p//span//text()")
        under_word = html.xpath("//div[@class='jumbotron']//p//span//u//text()")
        choice = html.xpath("//div[@class='jumbotron']//label/span/text()")
        meta = html.xpath("//form//p//span//text()")
        analysis = html.xpath("//div[@class='jumbotron ']/span//text()")

        # answer/date 取自 meta 末尾两项；结构异常时缺项则跳过该题，避免 IndexError 中断整轮
        if len(meta) < 2:
            print("  ⚠ 页面缺少答案/日期字段，跳过")
            return None
        answer = meta[-2]
        test_date = meta[-1]

        # 直接返回下游校验器（validate.py type_1）所需的字段结构
        return {
            "text": question,
            "under_word": under_word,
            "choice": choice,
            "answer": answer,
            "analysis": analysis,
            "date": test_date,
        }

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")

if __name__ == '__main__':
    from crawler.config import require
    spider = TestType1(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()