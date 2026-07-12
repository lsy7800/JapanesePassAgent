from lxml import etree
from crawler.spiders.spider import Spider

class TestType1(Spider):

    def parse(self, response):
        html = etree.HTML(response.text)
        question = html.xpath("//div[@class='jumbotron']//p//span//text()")
        under_word = html.xpath("//div[@class='jumbotron']//p//span//u//text()")
        choice = html.xpath("//div[@class='jumbotron']//label/span/text()")
        answer = html.xpath("//form//p//span//text()")[-2]
        test_date = html.xpath("//form//p//span//text()")[-1]
        analysis = html.xpath("//div[@class='jumbotron ']/span//text()")
        print(question, under_word, choice, answer, test_date, analysis)
        return {
            "question": question,
            "under_word": under_word,
            "choice": choice,
            "answer": answer,
            "analysis": analysis,
            "test_date": test_date
        }


    def run(self):
        if not self.ensure_auth():
            print("认证失败")
            return

        data_class = []

        for index in range(1, 166):
            print(f"开始解析：{index}")
            response = self.fetch(
                url="http://account.for-test.cn/jlptshitidata.php",
                params={
                    "shitibiaoming":"t_69",
                    "shitibiao": 69,
                    "tihao": index,
                    "yshipin": 1,
                    "jinru":0,
                    "yanzheng":1
                }
            )
            if response is None:
                return

            data = self.parse(response)
            if data is None:
                print("数据解析失败")
                return

            data_class.append({
                "id": index,
                "text": data["question"],
                "under_word": data["under_word"],
                "choice": data["choice"],
                "answer": data["answer"],
                "analysis": data["analysis"],
                "date": data["test_date"]

            })

        self.save_data(filename="result_69.json", data=data_class)

if __name__ == '__main__':
    from crawler.config import require
    spider = TestType1(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()