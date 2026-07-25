import re
from lxml import etree
from crawler.spiders.spider import Spider


class TestType11(Spider):
    """shitibiao 79：信息检索（情報検索 / info_search）。

    结构：span.con 内含结构化 HTML（<table> 或带边框 <div>/<p>），固定 2 个 icheck 组。
    转换策略：
      - <table>           → Markdown 表格（| col | col |）
      - <div/p> border    → 【BOX】...【/BOX】文本块
      - <u>               → 【U】...【/U】
      - <br>/<p>          → 换行
      - 其余标签           → 剥离
    产出通用「一篇 N 问」嵌套结构，复用 write_reading_to_mysql 入库路径。
    """
    SHITIBIAO = 79
    COUNT = 35

    # ── HTML → 纯文本工具 ──────────────────────────────────────────────

    @staticmethod
    def _el_text(el):
        """序列化单个元素：<u>→标记，<br>/<p>→换行，其余标签剥离。"""
        s = etree.tostring(el, encoding="unicode")
        s = re.sub(r"<u\b[^>]*>", "【U】", s, flags=re.I)
        s = re.sub(r"</u\s*>", "【/U】", s, flags=re.I)
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"</p\s*>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"[ \t　\xa0]+", " ", s)
        s = re.sub(r"\n[ \t]*", "\n", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    @classmethod
    def _table_to_md(cls, table_el):
        """把 <table> 转成 Markdown 表格。"""
        lines = []
        cap = table_el.find(".//caption")
        if cap is not None:
            txt = "".join(cap.itertext()).replace("\xa0", " ").strip()
            if txt:
                lines.append(f"【{txt}】")

        thead = table_el.find(".//thead")
        tbody = table_el.find(".//tbody")
        header_rows = thead.findall(".//tr") if thead is not None else []
        body_rows = tbody.findall(".//tr") if tbody is not None else table_el.findall(".//tr")

        def _cells(tr):
            return [
                "".join(td.itertext()).replace("\n", " ").replace("\xa0", " ").strip()
                for td in (tr.findall("th") + tr.findall("td"))
            ]

        if header_rows:
            hcells = _cells(header_rows[0])
            lines.append("| " + " | ".join(hcells) + " |")
            lines.append("| " + " | ".join(["---"] * len(hcells)) + " |")
            for tr in header_rows[1:]:
                lines.append("| " + " | ".join(_cells(tr)) + " |")
        for tr in body_rows:
            cells = _cells(tr)
            if any(cells):
                lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)

    @classmethod
    def _article_text(cls, span_el):
        """序列化 span.con：table→MD，border 元素→【BOX】，其余→文本。"""
        parts = []
        for ch in span_el:
            tag = ch.tag
            style = ch.get("style", "")
            if tag == "table":
                parts.append(cls._table_to_md(ch))
            elif "border-style" in style and "solid" in style:
                parts.append("【BOX】\n" + cls._el_text(ch) + "\n【/BOX】")
            else:
                txt = cls._el_text(ch)
                if txt:
                    parts.append(txt)
        # span 自身也可能有 tail text（少见）
        result = "\n".join(p for p in parts if p)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    # ── 解析 ────────────────────────────────────────────────────────────

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

        jb = html.xpath("//div[@class='jumbotron']")
        if not jb:
            return None
        jb = jb[0]

        # 固定 2 个 icheck 组
        groups = sorted(
            set(html.xpath("//input[starts-with(@name,'icheck')]/@name")),
            key=lambda x: int(x[6:]) if x[6:].isdigit() else 0,
        )
        questions = []
        for g in groups:
            opts = [
                o.strip()
                for o in html.xpath(f"//label[input[@name='{g}']]/span[@class='con']/text()")
            ]
            if len(opts) < 2:
                continue
            ans = html.xpath(f"//input[@name='{g}' and @checked]/@value")
            qtext = self._question_for(jb, g)
            questions.append({
                "no": int(g[6:]) if g[6:].isdigit() else len(questions) + 1,
                "question": qtext,
                "choice": opts,
                "answer": ans[0] if ans else "",
            })
        if not questions:
            print("  ⚠ 未找到小题，跳过")
            return None

        con = jb.xpath("./span[@class='con']")
        article = self._article_text(con[0]) if con else ""
        if not article:
            print("  ⚠ 文章为空，跳过")
            return None

        return {
            "date": date,
            "article": article,
            "n_questions": len(questions),
            "questions": questions,
        }

    @staticmethod
    def _question_for(jb, group_name):
        radios = jb.xpath(f".//input[@name='{group_name}']")
        if not radios:
            return ""
        label = radios[0].getparent()
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


if __name__ == "__main__":
    from crawler.config import require
    spider = TestType11(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()
