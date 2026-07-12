from lxml import etree
from crawler.spiders.spider import Spider

class TestType2(Spider):

    def parse(self, response):
        html = etree.HTML(response.text)
        question = html.xpath("//div[@class='jumbotron']//p//span//text()")
        choice1 = html.xpath("//div[@class='jumbotron']//label[1]//span//text()")
        choice2 = html.xpath("//div[@class='jumbotron']//label[2]//span//text()")
        choice3 = html.xpath("//div[@class='jumbotron']//label[3]//span//text()")
        choice4 = html.xpath("//div[@class='jumbotron']//label[4]//span//text()")
        answer = html.xpath("//form//p//span//text()")[-2]
        test_date = html.xpath("//form//p//span//text()")[-1]
        analysis = html.xpath("//div[@class='jumbotron ']/span//text()")
        print(question, choice1, choice2, choice3, choice4, answer, test_date, analysis)
        return {
            "question": question,
            "choice1": choice1,
            "choice2": choice2,
            "choice3": choice3,
            "choice4": choice4,
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
                    "shitibiaoming":"t_70",
                    "shitibiao": 70,
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
                "choice1": data["choice1"],
                "choice2": data["choice2"],
                "choice3": data["choice3"],
                "choice4": data["choice4"],
                "answer": data["answer"],
                "analysis": data["analysis"],
                "date": data["test_date"]
            })

        self.save_data(filename="result_70.json", data=data_class)

if __name__ == '__main__':
    from crawler.config import require
    spider = TestType2(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()