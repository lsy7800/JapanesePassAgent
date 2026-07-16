import re
from lxml import etree
from crawler.spiders.spider import Spider


class TestType9(Spider):
    """shitibiao 77：综合理解（統合理解 / reading_integ）。

    特殊结构：**两篇文章 A、B**（同一话题不同立场/角度）+ N 个问句（多为对比设问，如
    「AとBの認識で共通しているのは何か」）。两篇文章同在第一个 jumbotron 的单个 span.con 内，
    以独立段落 <p>A</p> / <p>B</p> 分隔，各自正文在带边框的 <p> 中。第二个 jumbotron 是
    中文解析（只取 jbs[0] 天然排除）。

    与中长篇阅读（type_7/8）同构，复用通用「一篇 N 问」嵌套结构，唯一差异是文章内含 A/B 两段：
    把独立成行的单字标记 A/B 规整为醒目的【文章A】/【文章B】，便于前端分栏渲染与 LLM 校验理解，
    且不误伤正文中的字母。<u>…</u> 仍转【U】…【/U】。无年份的篇跳过。

    产出 {article, questions:[{no,question,choice,answer}]}，直接复用 write_reading_to_mysql
    的入库路径（category=reading_integ）。
    """
    SHITIBIAO = 77
    COUNT = 35

    @staticmethod
    def _is_padding(opts):
        return bool(opts) and any(("勾选" in o or "勾選" in o) for o in opts)

    @classmethod
    def _article_text(cls, span_el):
        """序列化文章：<u> 转下划线标记，<br>/</p> 转换行，去其余标签，
        再把独立成行的单字 A/B 规整为【文章A】/【文章B】。"""
        s = etree.tostring(span_el, encoding="unicode")
        s = re.sub(r"<u\b[^>]*>", "【U】", s, flags=re.I)
        s = re.sub(r"</u\s*>", "【/U】", s, flags=re.I)
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"</p\s*>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"[ \t　\xa0]+", " ", s)
        s = re.sub(r"\n[ \t]*", "\n", s)
        s = re.sub(r"\n{2,}", "\n", s)
        s = s.strip()
        # 仅替换「独占一行的单字 A/B」为分栏标记，不动正文中的字母
        s = re.sub(r"(?m)^[ \t]*A[ \t]*$", "【文章A】", s)
        s = re.sub(r"(?m)^[ \t]*B[ \t]*$", "【文章B】", s)
        return s.strip()

    def parse(self, response):
        html = etree.HTML(response.text)
        if html is None:
            return None

        meta = [x.strip() for x in html.xpath("//form//p//span//text()") if x.strip()]
        # 日期格式形如 2013-12-N1；从后往前找紧凑格式（避免误匹配文中年份/页脚 copyright）。
        date = ""
        for m in reversed(meta):
            if re.search(r"20\d\d\s*[-/]\s*\d{1,2}.{0,4}N[1-5]", m):
                date = m
                break
        if not date:
            print("  ↷ 无年份，跳过不采集")
            return None

        jb = html.xpath("//div[@class='jumbotron']")
        if not jb:
            return None
        jb = jb[0]

        # 真实问数：从 icheck1 起数非占位组，遇占位即止（占位永远在末尾）
        groups = sorted(set(html.xpath("//input[starts-with(@name,'icheck')]/@name")),
                        key=lambda x: int(x[6:]) if x[6:].isdigit() else 0)
        questions = []
        for g in groups:
            opts = [o.strip() for o in html.xpath(
                f"//label[input[@name='{g}']]/span[@class='con']/text()")]
            if self._is_padding(opts) or len(opts) < 2:
                break
            ans = html.xpath(f"//input[@name='{g}' and @checked]/@value")
            qtext = self._question_for(jb, g)
            questions.append({
                "no": int(g[6:]) if g[6:].isdigit() else len(questions) + 1,
                "question": qtext,
                "choice": opts,
                "answer": ans[0] if ans else "",
            })
        if not questions:
            print("  ⚠ 未找到真实小题，跳过")
            return None

        # 文章 = 第一个 jumbotron 的首个直接子 span.con（含 A/B 两篇；问句在其后 p/label 中）
        con = jb.xpath("./span[@class='con']")
        article = self._article_text(con[0]) if con else ""
        if not article:
            print("  ⚠ 文章为空，跳过")
            return None
        if "【文章A】" not in article or "【文章B】" not in article:
            print("  ⚠ 未同时识别到 A/B 两篇，跳过")
            return None

        return {
            "date": date,
            "article": article,
            "n_questions": len(questions),
            "questions": questions,
        }

    @staticmethod
    def _question_for(jb, group_name):
        """取某 icheck 组对应的问句：该组首个 radio 所在 label 之前最近的 <p> 文本。"""
        radios = jb.xpath(f".//input[@name='{group_name}']")
        if not radios:
            return ""
        label = radios[0].getparent()  # <label>
        prev = label.getprevious()
        while prev is not None:
            if prev.tag == "p":
                txt = "".join(prev.itertext())
                txt = re.sub(r"\s+", " ", txt).strip()
                return re.sub(r"^\s*[0-9０-９]+[.．、]\s*", "", txt)
            prev = prev.getprevious()
        return ""

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")


if __name__ == '__main__':
    from crawler.config import require
    spider = TestType9(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()
