import copy
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

        def _all_th(tr):
            cells = [c for c in tr if c.tag in ("td", "th")]
            return bool(cells) and all(c.tag == "th" for c in cells)

        # 一律按文档顺序取全部 <tr>，不依赖 thead/tbody 容器：
        # 源站的表格结构很不规范——有的把所有行都塞进 <thead>（含纯 <td> 数据行），
        # 有的一行一个 <tbody>（#15 有 6 个 tbody）。按容器取行会漏掉大半数据。
        all_trs = table_el.findall(".//tr")

        # 表头 = 开头连续的「全 th」行；遇到第一个含 td 的行就进数据区。
        cut = 0
        while cut < len(all_trs) and _all_th(all_trs[cut]):
            cut += 1
        if cut:
            lines.append("<thead>" + "".join(_tr_html(tr, True) for tr in all_trs[:cut]) + "</thead>")
        body_trs = all_trs[cut:]

        body = "".join(_tr_html(tr) for tr in body_trs)
        if body:
            lines.append(f"<tbody>{body}</tbody>")

        return '<table class="info-table">' + "".join(lines) + "</table>"

    @staticmethod
    def _unwrap_layout_tables(root):
        """就地拆掉「排版用表格」——即内部还套着表格的外层表。

        源站有的题（如 #9）用一个 1 行 2 列的表把「注意事项」和真正的数据表并排摆放，
        外层表不承载任何语义，只是排版。而嵌套表格有两个害处：
          1. 前端 renderArticle 用非贪婪正则 /<table[\\s\\S]*?<\\/table>/ 抠表格保护，
             遇嵌套会在内层 </table> 处截断，外层剩下的部分被当普通文本转义 → 标签裸露；
          2. 语义上该拆——外层是排版，内层才是数据。
        故把外层表替换成一个 <div>，各单元格内容依次变成 <p>（后续序列化为换行），
        内层真表格留在树里照常处理。反复执行直到不再有嵌套。
        """
        for _ in range(5):  # 防御性上限，正常一两轮即收敛
            nested = [t for t in root.xpath(".//table") if t.xpath(".//table")]
            if not nested:
                return
            for t in nested:
                parent = t.getparent()
                if parent is None:
                    continue
                holder = etree.Element("div")
                # 只取归属于本表的单元格（不含内层表的单元格）
                for cell in t.xpath(".//td|.//th"):
                    owner = cell.xpath("ancestor::table[1]")
                    if not owner or owner[0] is not t:
                        continue
                    para = etree.Element("p")
                    para.text = cell.text
                    for ch in list(cell):
                        para.append(ch)  # 移动子节点（含内层 <table>）
                    holder.append(para)
                holder.tail = t.tail
                parent.replace(t, holder)

    @classmethod
    def _el_text_keep_tables(cls, el):
        """把带边框的块序列化成文本，但**保留其中的表格**为 HTML。

        源站大量题目把 <table> 放在 border-style:solid 的 <div> 里（募集要项、料金表等）。
        若直接用 _el_text() 整块转文本，后代 <table> 的标签会被一并剥掉，表格塌成一行文字。
        这里先把每个后代表格换成哨兵占位符、其余部分照常转文本，最后把占位符还原成表格 HTML。

        前端 renderArticle 先抠出 <table> 保护再处理 【BOX】，所以 BOX 内嵌表格能正常渲染。
        """
        work = copy.deepcopy(el)
        cls._unwrap_layout_tables(work)
        tables = []
        # 哨兵只用字母数字：lxml 文本节点不接受控制字符，且 _el_text 会压缩空白，
        # 纯字母数字的标记能原样穿过序列化。源文是日文，不会与正文冲突。
        for t in reversed(work.xpath(".//table")):
            parent = t.getparent()
            if parent is None:
                continue
            # 无 <tr> 的畸形表当排版框，留在树里按文本序列化（与 _article_text 一致）
            if not t.xpath(".//tr"):
                continue
            tables.append(cls._table_to_html(t))
            holder = etree.Element("span")
            holder.text = f"ZTBLZ{len(tables) - 1}ZENDZ"
            holder.tail = t.tail
            parent.replace(t, holder)

        s = cls._el_text(work)
        # 哨兵两侧补换行，保证表格独占一块、不与相邻文字黏连
        for i, html in enumerate(tables):
            s = s.replace(f"ZTBLZ{i}ZENDZ", f"\n{html}\n")
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    @classmethod
    def _article_text(cls, span_el):
        """序列化 span.con：递归处理所有子元素，直接输出 HTML 表格，其余转文本。"""
        # 先在副本上拆掉排版用的嵌套表格，再遍历——嵌套表格会让前端抠表格的
        # 非贪婪正则截断，且外层表本身无语义。副本避免污染调用方的 DOM。
        span_el = copy.deepcopy(span_el)
        cls._unwrap_layout_tables(span_el)
        parts = []

        def _walk(el):
            tag = el.tag
            style = el.get("style", "")

            if tag == "table":
                # 无 <tr> 的表（源站有畸形写法：<table> 里直接放一个 <td>，
                # 当单元格排版框用，如 #15 的联系方式块）不是表格数据，
                # 按文本处理；否则会产出空的 <table></table>、内容全丢。
                if el.xpath(".//tr"):
                    parts.append(cls._table_to_html(el))
                else:
                    txt = cls._el_text(el)
                    if txt:
                        parts.append(txt)
                return

            if tag in ("h1", "h2", "h3", "h4"):
                txt = " ".join(el.itertext()).replace("\xa0", " ").strip()
                if txt:
                    parts.append(txt)
                return

            if "border-style" in style and "solid" in style:
                # 用保留表格的序列化：该块内常嵌 <table>（料金表/募集要项），
                # 整块转纯文本会把表格标签一并剥掉，表格塌成一行文字。
                parts.append("【BOX】\n" + cls._el_text_keep_tables(el) + "\n【/BOX】")
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
