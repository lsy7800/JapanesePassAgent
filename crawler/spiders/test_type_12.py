import re
from lxml import etree
from crawler.spiders.spider import Spider


class TestType12(Spider):
    """shitibiao 80~86：听力题（課題理解 / task_listening 等听力题型）。

    结构：每题一段 mp3 + 一道单选。
      - <audio><source src="mp3/..."> → 音频相对路径（只存 URL，不下载文件）
      - span.con 内 <b> 首项      → 设问（题干）
      - span.con 内 <br> 分隔的对话行 → 听力原文脚本（存 article）
      - icheck 选项组             → 4 个选项 + checked 答案
      - 末尾「答え：N …」         → 答案说明（存 analysis）
    音频 URL 存相对路径（如 mp3/n1/tiku79/n1tiku79-01.mp3），前端播放时拼可配置的 base 前缀，
    便于后期把音频迁移到对象存储时只改配置、不动数据库。
    产出「一段音频一问」的扁平结构，article 存原文脚本供播完后对照。
    """
    SHITIBIAO = 80
    COUNT = 80

    @staticmethod
    @staticmethod
    def _con_lines(con_el):
        """把 span.con 内容按 <br>/<p> 拆行，保留 <b> 标记信息，返回 [(is_bold, text)]。"""
        raw = etree.tostring(con_el, encoding="unicode")
        raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
        raw = re.sub(r"</p\s*>", "\n", raw, flags=re.I)
        raw = re.sub(r"<b\b[^>]*>", "\x01", raw, flags=re.I)
        raw = re.sub(r"</b\s*>", "\x02", raw, flags=re.I)
        raw = re.sub(r"<[^>]+>", "", raw)
        raw = raw.replace("\xa0", " ")
        out = []
        for ln in raw.split("\n"):
            is_bold = "\x01" in ln
            ln = ln.replace("\x01", "").replace("\x02", "")
            ln = re.sub(r"[ \t　]+", " ", ln).strip()
            if ln:
                out.append((is_bold, ln))
        return out

    @classmethod
    def _normalize_lines(cls, con_el):
        """归一化到只剩日语原文段的行列表。

        部分题（80 后段 id≥109、81 后段 id≥123 等）解析区为中日对照：
          「翻译」中文段 + 「原文」日语段。取「原文」分界之后；无分界则原样。
        """
        lines = cls._con_lines(con_el)

        def _marker(t, *kw):
            # 容忍行首的间隔号/空格/项目符号（如「·参考译文」「 原文」）
            s = re.sub(r"^[\s·・:：\-—*]+", "", t)
            return any(s.startswith(k) for k in kw)

        gen = next((i for i, (_, t) in enumerate(lines) if _marker(t, "原文")), None)
        if gen is not None:
            return lines[gen + 1:]
        cut = next((i for i, (_, t) in enumerate(lines)
                    if _marker(t, "翻译", "参考译文", "参考訳", "翻訳")), None)
        if cut is not None:
            return lines[:cut]
        return lines

    @staticmethod
    def _content_lines(lines):
        """去掉答案行后的行列表（保留 <b> 标记）。"""
        return [(b, t) for b, t in lines
                if not re.match(r"^\s*答え|^\s*答案", t)]

    @classmethod
    def _split_body(cls, con_el):
        """把归一化后的日语段切成 (题干, 脚本行列表)。兼容三种结构：

        - 有 <b>：<b> 行是导语/设问 → 题干；非 <b> 行是脚本（对话或独白）。
        - 无 <b>（中日对照题）：日语段结构固定为「导语[+设问] → 正文… → 设问重复」，
          不依赖说话人冒号（独白型如讲座/通知无冒号）。取首行为题干、末行为设问重复丢弃、
          中间为脚本；仅一两行时全部归题干、脚本为空。
        """
        lines = cls._content_lines(cls._normalize_lines(con_el))
        if not lines:
            return "", []
        if any(b for b, _ in lines):
            intro = next((t for b, t in lines if b), "")
            script = [t for b, t in lines if not b]
            return intro, script
        # 无 <b>：位置规则
        texts = [t for _, t in lines]
        if len(texts) <= 2:
            return "\n".join(texts), []
        intro_parts = [texts[0]]
        body = texts[1:]
        # 三段式「导语 → 设问 → 正文…」：第2行是设问句则并入题干
        if len(body) >= 2 and cls._looks_like_question(body[0]):
            intro_parts.append(body[0])
            body = body[1:]
        # 末行常是设问重复 → 丢弃
        if len(body) >= 2 and cls._looks_like_question(body[-1]):
            body = body[:-1]
        return "\n".join(intro_parts), body

    @staticmethod
    def _looks_like_question(line):
        """判断是否设问句（以「か」「か？」「ますか」等结尾）。"""
        return bool(re.search(r"(か|か？|ますか|ですか|でしょうか)[。\.]?$", line.strip()))

    @classmethod
    def _script_text(cls, con_el):
        """听力原文脚本：日语段正文（去导语/设问/答案行），兼容对话与独白。"""
        _, script = cls._split_body(con_el)
        return "\n".join(script).strip()

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

        jb = html.xpath("//div[@class='jumbotron']")
        if not jb:
            return None
        jb = jb[0]

        groups = sorted(
            set(html.xpath("//input[starts-with(@name,'icheck')]/@name")),
            key=lambda x: int(x[6:]) if x[6:].isdigit() else 0,
        )
        if not groups:
            print("  ⚠ 未找到选项组，跳过")
            return None
        g = groups[0]
        opts = [
            o.strip()
            for o in html.xpath(f"//label[input[@name='{g}']]/span[@class='con']/text()")
        ]
        if len(opts) < 2:
            print("  ⚠ 选项不足，跳过")
            return None
        ans = html.xpath(f"//input[@name='{g}' and @checked]/@value")

        con = jb.xpath(".//span[@class='con']")
        if not con:
            print("  ⚠ 正文为空，跳过")
            return None
        con = con[0]

        # 题干 + 听力脚本：统一由 _split_body 切分（兼容 <b>/无<b>、对话/独白）
        question, script_lines = self._split_body(con)
        script = "\n".join(script_lines).strip()

        # 答案说明行（答え：…）
        analysis = ""
        for line in "".join(con.itertext()).split("\n"):
            line = line.strip()
            if line.startswith("答え") or line.startswith("答案"):
                analysis = line
                break

        if not question:
            # 设问缺失时用脚本首行兜底，避免空题干
            question = script.split("\n")[0] if script else ""

        return {
            "date": date,
            "audio_url": audio_url,
            "question": question,
            "article": script,
            "choice": opts,
            "answer": ans[0] if ans else "",
            "analysis": analysis,
        }

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")


if __name__ == "__main__":
    from crawler.config import require
    spider = TestType12(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()
