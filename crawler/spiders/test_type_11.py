import re
from lxml import etree
from crawler.spiders.spider import Spider


class TestType11(Spider):
    """shitibiao 79：信息检索（情報検索 / info_search）。

    结构：span.con 内含结构化 HTML（<table> 或带边框 <div>/<p>），固定 2 个 icheck 组。
    转换策略：
      - <table>        → HTML 表格（保留 rowspan/colspan 及格内换行，直接存 HTML）
      - <div/p> border → 【BOX】...【/BOX】文本块
      - <h1>/<h2>/<h3> → 标题文本行
      - <u>            → 【U】...【/U】
      - <br>/<p>       → 换行
      - 其余标签        → 剥离
    article 字段存储 HTML 片段，前端 v-html 直接渲染。
    产出通用「一篇 N 问」嵌套结构，复用 write_reading_to_mysql 入库路径。
    """
    SHITIBIAO = 79
    COUNT = 35

    # ── HTML → 序列化工具 ─────────────────────────────────────────────

    @staticmethod
    def _el_text(el):
        """序列化单个元素为纯文本：<u>→标记，<br>/<p>→换行，其余标签剥离。"""
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
    def _table_to_html(cls, table_el):
        """把 <table> 序列化为带样式类的 HTML，保留 rowspan/colspan 及格内 <br>。"""
        def _cell_inner(td):
            s = etree.tostring(td, encoding="unicode")
            # 剥除外层 <td>/<th> 标签，只保留内容
            s = re.sub(r"^<t[dh][^>]*>", "", s, flags=re.I)
            s = re.sub(r"</t[dh]\s*>$", "", s.rstrip(), flags=re.I)
            s = re.sub(r"<u\b[^>]*>", "【U】", s, flags=re.I)
            s = re.sub(r"</u\s*>", "【/U】", s, flags=re.I)
            s = re.sub(r"<br\s*/?>", "<br>", s, flags=re.I)
            s = re.sub(r"</?p[^>]*>", "", s, flags=re.I)
            s = re.sub(r"<[^>]+>", "", s)
            s = re.sub(r"[ \t　\xa0]+", " ", s)
            return s.strip()

        def _td_attrs(td):
            attrs = ""
            if td.get("rowspan"): attrs += f' rowspan="{td.get("rowspan")}"'
            if td.get("colspan"): attrs += f' colspan="{td.get("colspan")}"'
            return attrs

        def _tr_html(tr, in_head=False):
            cells = []
            for td in tr:
                tag = "th" if (td.tag == "th" or in_head) else "td"
                cells.append(f"<{tag}{_td_attrs(td)}>{_cell_inner(td)}</{tag}>")
            return "<tr>" + "".join(cells) + "</tr>"

        lines = []
        cap = table_el.find(".//caption")
        if cap is not None:
            txt = "".join(cap.itertext()).replace("\xa0", " ").strip()
            if txt:
                lines.append(f"<caption>{txt}</caption>")

        thead = table_el.find(".//thead")
        tbody = table_el.find(".//tbody")
        all_trs = table_el.findall(".//tr")

        if thead is not None:
            lines.append("<thead>" + "".join(_tr_html(tr, True) for tr in thead.findall(".//tr")) + "</thead>")
            body_trs = tbody.findall(".//tr") if tbody is not None else []
        else:
            first = all_trs[0] if all_trs else None
            if first is not None and all(td.tag == "th" for td in first):
                lines.append("<thead>" + _tr_html(first, True) + "</thead>")
                body_trs = all_trs[1:]
            else:
                body_trs = all_trs

        body = "".join(_tr_html(tr) for tr in body_trs)
        if body:
            lines.append(f"<tbody>{body}</tbody>")

        return '<table class="info-table">' + "".join(lines) + "</table>"

    @classmethod
    def _article_text(cls, span_el):
        """序列化 span.con：递归处理所有子元素，直接输出 HTML 表格，其余转文本。"""
        parts = []

        def _walk(el):
            tag = el.tag
            style = el.get("style", "")

            if tag == "table":
                parts.append(cls._table_to_html(el))
                return

            if tag in ("h1", "h2", "h3", "h4"):
                txt = " ".join(el.itertext()).replace("\xa0", " ").strip()
                if txt:
                    parts.append(txt)
                return

            if "border-style" in style and "solid" in style:
                parts.append("【BOX】\n" + cls._el_text(el) + "\n【/BOX】")
                return

            # 普通元素：先输出自身直接文本，再递归子元素
            direct = (el.text or "").replace("\xa0", " ").strip()
            if direct:
                parts.append(direct)
            for ch in el:
                _walk(ch)
                tail = (ch.tail or "").replace("\xa0", " ").strip()
                if tail:
                    parts.append(tail)

        direct = (span_el.text or "").replace("\xa0", " ").strip()
        if direct:
            parts.append(direct)
        for ch in span_el:
            _walk(ch)
            tail = (ch.tail or "").replace("\xa0", " ").strip()
            if tail:
                parts.append(tail)

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
