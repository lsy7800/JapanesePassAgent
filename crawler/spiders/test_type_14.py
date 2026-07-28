import re
from lxml import etree
from crawler.spiders.test_type_13 import TestType13


class TestType14(TestType13):
    """shitibiao 85：综合理解（統合理解）——一段音频对应 2 个小题。

    与 test_type_13（单设问）的差异：
      - 一个音频页含 2 个 icheck 组（icheck_1、icheck_2），各 4 选项、各有答案；
      - 选项文字在题面 icheck 的 span.con 里（非解析区）；
      - 解析区含听力脚本 + 「質問１…答え：X」「質問２…答え：Y」。
    产出嵌套结构：{id, audio_url, article(脚本), date, questions:[{no,answer,options}, ...]}，
    题干（question）留空——统合理解设问在音频里。入库走多子题听力路径。
    """
    SHITIBIAO = 85
    COUNT = 30

    def parse(self, response):
        html = etree.HTML(response.text)
        if html is None:
            return None

        meta = [x.strip() for x in html.xpath("//form//p//span//text()") if x.strip()]
        date = ""
        for m in reversed(meta):
            if re.search(r"20\d\d\s*[-/]\s*\d{1,2}.{0,4}N[1-5]", m):
                date = m
                break
        if not date:
            print("  ↷ 无年份，跳过不采集")
            return None

        audio = html.xpath("//audio/source/@src")
        audio_url = audio[0].strip() if audio else ""
        if not audio_url:
            print("  ⚠ 无音频，跳过")
            return None

        # 各 icheck 组 = 一个子题；选项文字在题面 span.con，答案取 checked
        groups = sorted(
            set(html.xpath("//input[starts-with(@name,'icheck')]/@name")),
            key=lambda g: int(g.split("_")[1]) if "_" in g and g.split("_")[1].isdigit() else 0,
        )
        if not groups:
            print("  ⚠ 无选项组，跳过")
            return None

        questions = []
        for no, g in enumerate(groups, 1):
            opts = [
                o.strip()
                for o in html.xpath(f"//label[input[@name='{g}']]/span[@class='con']/text()")
            ]
            opts = [o for o in opts if o]
            ans = html.xpath(f"//input[@name='{g}' and @checked]/@value")
            n_opts = len(html.xpath(f"//input[@name='{g}']/@value"))
            if not ans and n_opts == 0:
                continue  # 该组无题
            # 选项文字可能全在音频里（题面/解析区都无文字）→ 选项留空，仅存答案
            options = {self._LETTERS_[i]: opts[i] for i in range(min(len(opts), 4))} if opts else {}
            questions.append({
                "no": no,
                "question": "",            # 统合理解设问在音频里，题干留空
                "options": options,
                "answer": ans[0] if ans else "",
                "analysis": "",            # 由 --listening 审核阶段生成
            })
        if not questions:
            print("  ⚠ 无有效子题，跳过")
            return None

        # 解析区（第二个 jumbotron）：拆出听力脚本 + 各「質問N…」设问文字。
        # 设问文字暂存进子题 question（供审核判断哪个设问对应哪个子题）；入库时再清空。
        script = ""
        setsumon = []
        jbs = html.xpath("//div[contains(@class,'jumbotron')]")
        if len(jbs) >= 2:
            lines = self._jb_lines(jbs[1])
            body = []
            for _, t in lines:
                mq = re.match(r"^\s*質問\s*([0-9０-９一二三四]+)\s*[：:]?\s*(.*)$", t)
                if mq:
                    setsumon.append(mq.group(2).strip())
                    continue
                if re.match(r"^\s*(答え|答案)", t):
                    continue
                body.append(t)
            script = "\n".join(body).strip()
        # 按顺序把设问文字配给子题
        for i, q in enumerate(questions):
            if i < len(setsumon):
                q["question"] = setsumon[i]

        return {
            "date": date,
            "audio_url": audio_url,
            "article": script,
            "questions": questions,
        }

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")


TestType14._LETTERS_ = ["a", "b", "c", "d"]


if __name__ == "__main__":
    from crawler.config import require
    spider = TestType14(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()
