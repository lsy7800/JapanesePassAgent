import re
from lxml import etree
from crawler.spiders.spider import Spider


class TestType6(Spider):
    """shitibiao 74：阅读理解（短篇内容理解 / reading_short）。

    每题 = 一段短文 + 一个问句 + 4 个整句选项（一篇一题）。答案取 icheck 的 checked 值。
    无年份的旧题不采集。部分文章内嵌未闭合的 <div>（告示/邮件排版），故选项一律用
    icheck radio 定位（恒 4 个、value 即选项号），不依赖脆弱的 .//label 层级。
    """
    SHITIBIAO = 74
    COUNT = 150

    # 页面底部控件/操作区文本（脏 HTML 时会被吞入 jumbotron）——遇到即视为正文结束
    _UI_NOISE = ("制作视频", "上一道", "下一道", "提交并返回", "题库修改",
                 "取消修改", "保存上传", "开启题库", "正确答案")
    # 结构损坏的题里，选项会以「1.」「2.」编号泄漏进正文；遇到编号选项行即截断
    _OPT_LINE = re.compile(r"^[1-4][.．、]")

    @classmethod
    def _strip_ui_noise(cls, lines):
        out = []
        for ln in lines:
            if any(k in ln for k in cls._UI_NOISE) or cls._OPT_LINE.match(ln) or ln.strip("¦| 　") == "":
                break
            out.append(ln)
        return out

    @staticmethod
    def _before(a, b):
        """判断节点 a 是否在 b 之前（文档顺序）。用于以首个选项为硬边界截取正文。"""
        for node in a.getroottree().iter():
            if node is a:
                return True
            if node is b:
                return False
        return False

    @staticmethod
    def _block_text(el):
        s = etree.tostring(el, encoding="unicode")
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"</p\s*>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = re.sub(r"[ \t　]+", " ", s)
        s = re.sub(r"\n[ \t]*", "\n", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    def parse(self, response):
        html = etree.HTML(response.text)
        if html is None:
            return None

        # 年份：meta 中匹配 20XX；无则跳过不采集
        meta = [x.strip() for x in html.xpath("//form//p//span//text()") if x.strip()]
        date = next((m for m in meta if re.search(r"20\d\d", m)), "")
        if not date:
            print("  ↷ 无年份，跳过不采集")
            return None

        # 选项：用 icheck radio 定位（恒 4 个，value=选项号）；答案取 checked
        radios = html.xpath("//input[@name='icheck']")
        if len(radios) < 2:
            print("  ⚠ 未找到选项，跳过")
            return None
        options = []
        answer = ""
        for inp in radios:
            label = inp.getparent()  # <label>
            txt = "".join(label.xpath(".//span[@class='con']//text()")).strip()
            options.append(txt)
            if inp.get("checked") is not None:
                answer = inp.get("value", "")
        if not answer:
            # 兜底：checked 缺失时用 meta 倒数第二项（答案数字）
            answer = meta[-2] if len(meta) >= 2 else ""

        # 文章 + 问句：取正文区（第一个选项之前、且不在任何 label 内的 con 文本）。
        # 部分题内嵌未闭合 <div> 会把解析块吞进同一 jumbotron，故用「首个 icheck 之前」
        # 作为硬边界，避免文章/问句混入后面的中文解析。
        jb = html.xpath("//div[@class='jumbotron']")[0]
        first_radio = radios[0]
        labels = jb.xpath(".//label")
        label_nodes = set()
        for l in labels:
            label_nodes.update(l.iter())
        cons = []
        for c in jb.xpath(".//span[@class='con']"):
            if c in label_nodes or (set(c.iterancestors()) & label_nodes):
                continue
            # 只保留出现在第一个选项 radio 之前的正文（文档顺序）
            if c.getparent() is not None and self._before(c, first_radio):
                cons.append(c)
        lines = []
        for c in cons:
            for ln in self._block_text(c).split("\n"):
                if ln.strip():
                    lines.append(ln.strip())
        # 部分脏 HTML 会把页面底部控件文本并入 jumbotron，遇到已知 UI 噪声即截断
        lines = self._strip_ui_noise(lines)
        if not lines:
            print("  ⚠ 未找到文章/问句，跳过")
            return None
        question = lines[-1]
        article = "\n".join(lines[:-1])

        return {
            "date": date,
            "article": article,
            "question": question,
            "choice": options,
            "answer": answer,
        }

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")


if __name__ == '__main__':
    from crawler.config import require
    spider = TestType6(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()
