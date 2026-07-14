from lxml import etree
from crawler.spiders.spider import Spider

class TestType2(Spider):
    # 试题表编号（对方站点的 shitibiao 参数）与抓取题数
    SHITIBIAO = 70
    COUNT = 165

    def parse(self, response):
        html = etree.HTML(response.text)
        if html is None:
            return None
        question = html.xpath("//div[@class='jumbotron']//p//span//text()")
        choice1 = html.xpath("//div[@class='jumbotron']//label[1]//span//text()")
        choice2 = html.xpath("//div[@class='jumbotron']//label[2]//span//text()")
        choice3 = html.xpath("//div[@class='jumbotron']//label[3]//span//text()")
        choice4 = html.xpath("//div[@class='jumbotron']//label[4]//span//text()")
        meta = html.xpath("//form//p//span//text()")
        analysis = html.xpath("//div[@class='jumbotron ']/span//text()")

        # answer/date 取自 meta 末尾两项；结构异常时缺项则跳过该题，避免 IndexError 中断整轮
        if len(meta) < 2:
            print("  ⚠ 页面缺少答案/日期字段，跳过")
            return None
        answer = meta[-2]
        test_date = meta[-1]

        # 直接返回下游校验器（validate.py type_2）所需的字段结构
        return {
            "text": question,
            "choice1": choice1,
            "choice2": choice2,
            "choice3": choice3,
            "choice4": choice4,
            "answer": answer,
            "analysis": analysis,
            "date": test_date,
        }

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")

if __name__ == '__main__':
    from crawler.config import require
    spider = TestType2(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()