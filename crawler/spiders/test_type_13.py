import re
from lxml import etree
from crawler.spiders.test_type_12 import TestType12


class TestType13(TestType12):
    """shitibiao 82：听力题（概要理解类）。

    与 test_type_12（課題理解 80/81）的差异：
      - 选项文字**不印在题面**（题目区 icheck 的 span.con 为空），
        而在「解析如下」区（第二个 jumbotron）末尾以「1、…2、…」列出（半角/全角数字混用）。
      - 因此选项、脚本、设问都从解析区（jumbotron[1]）提取；答案仍取题面 icheck 的 checked。
    解析区结构（<br> 分隔）：
      [b]场景导语[/b] → 听力脚本行… → [b]设问[/b] → 「N、选项」×4 → 答え：N
    """
    SHITIBIAO = 82
    COUNT = 130

    # 行首选项编号：半角/全角数字，后接可选分隔符（顿号/逗号/句点，也可能无分隔符直接跟文字）。
    # 仅在设问（第二个 <b>）之后匹配，故脚本中以数字开头的行不会被误当选项。
    _OPT_LINE = re.compile(r'^\s*([1-4１-４])\s*[、，,。．.]?\s*(.+?)\s*$')

    @staticmethod
    def _jb_lines(jb):
        """把 jumbotron 内容按 <br>/<p> 拆成行，保留 <b> 标记信息。返回 [(is_bold, text)]。"""
        raw = etree.tostring(jb, encoding="unicode")
        raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
        raw = re.sub(r"</p\s*>", "\n", raw, flags=re.I)
        raw = raw.replace("\xa0", " ")
        # 用占位符标出 <b>…</b>
        raw = re.sub(r"<b\b[^>]*>", "\x01", raw, flags=re.I)
        raw = re.sub(r"</b\s*>", "\x02", raw, flags=re.I)
        raw = re.sub(r"<[^>]+>", "", raw)
        lines = []
        for ln in raw.split("\n"):
            is_bold = "\x01" in ln
            ln = ln.replace("\x01", "").replace("\x02", "")
            ln = re.sub(r"[ \t　]+", " ", ln).strip()
            if ln:
                lines.append((is_bold, ln))
        return lines

    def parse(self, response):
        html = etree.HTML(response.text)
        if html is None:
            return None

        # 日期（无年份则不采集，与父类一致）
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

        # 答案：题面 icheck 的 checked
        ans = html.xpath("//input[starts-with(@name,'icheck') and @checked]/@value")
        answer = ans[0] if ans else ""

        jbs = html.xpath("//div[contains(@class,'jumbotron')]")
        if len(jbs) < 2:
            print("  ⚠ 无解析区，跳过")
            return None
        lines = self._jb_lines(jbs[1])
        if not lines:
            return None

        # 82 解析区存在多种中日对照排版，需归一化到「只剩日语原文段」：
        #  变体A：日语正文 + 「参考译文/参考訳」+ 中文译文  → 取分界前
        #  变体B：中文解析/译文 + 「原文」+ 日语正文        → 取「原文」分界后
        # 「原文」优先（它显式标出日语段起点）；否则用「参考译文」截掉其后的中文。
        def _is_marker(t, *kw):
            # 容忍行首间隔号/空格/项目符号（如「·参考译文」「 原文」）
            s = re.sub(r"^[\s·・:：\-—*]+", "", t)
            return any(s.startswith(k) for k in kw)
        gen_idx = next((i for i, (_, t) in enumerate(lines) if _is_marker(t, "原文")), None)
        if gen_idx is not None:
            lines = lines[gen_idx + 1:]
        else:
            cut = next((i for i, (_, t) in enumerate(lines)
                        if _is_marker(t, "参考译文", "参考訳", "翻译", "翻訳")), None)
            if cut is not None:
                lines = lines[:cut]
        if not lines:
            return None

        bold_idx = [i for i, (b, _) in enumerate(lines) if b]

        # 选项：定位连续编号 1→2→3→4 的四行（编号无分隔符时也匹配）。
        # 用「连续序号」而非「任意数字开头行」，可排除脚本里孤立以数字开头的句子
        # （如独白中的「1970年代になると…」不会跟着 2/3/4 行，故不被误判为选项）。
        def _norm_num(ch):
            return {"1": 1, "2": 2, "3": 3, "4": 4, "１": 1, "２": 2, "３": 3, "４": 4}.get(ch)

        choice, opt_idx = [], []
        for start in range(len(lines)):
            m = self._OPT_LINE.match(lines[start][1])
            if not m or _norm_num(m.group(1)) != 1:
                continue
            # 从「1」行起，连续收集紧邻的选项格式行，直到遇到非选项行即停。
            # 不强制序号严格 1,2,3,4——源站偶有录入错误（如 1、3、3、4），但选项总是紧邻的连续行；
            # 而脚本里孤立的数字开头句（如「1970年代…」）后面不会紧跟更多选项格式行，故不会凑够 4 行。
            run = [(start, m.group(2).strip())]
            for j in range(start + 1, len(lines)):
                mj = self._OPT_LINE.match(lines[j][1])
                if mj and _norm_num(mj.group(1)) is not None:
                    run.append((j, mj.group(2).strip()))
                    if len(run) >= 4:
                        break
                else:
                    break
            if len(run) >= 3:  # 紧邻的 3~4 个编号行，认定为选项区
                opt_idx = [i for i, _ in run]
                choice = [t for _, t in run]
                break
        if len(choice) < 2:
            print("  ⚠ 选项不足，跳过")
            return None
        choice = choice[:4]
        first_opt = opt_idx[0]

        # 设问：选项之前的最后一个非对话、非答案行（有 <b> 时优先取第二个 <b>）
        q_idx = None
        if len(bold_idx) >= 2:
            q_idx = bold_idx[1]
        else:
            for i in range(first_opt - 1, 0, -1):
                txt = lines[i][1]
                if txt.startswith("答え") or txt.startswith("答案"):
                    continue
                q_idx = i
                break
        question_tail = lines[q_idx][1] if q_idx is not None else ""

        # 导语（题干开头）：第一行（有 <b> 时取第一个 <b>）
        intro = lines[bold_idx[0]][1] if bold_idx else lines[0][1]

        # 脚本：导语之后到设问之前的对话行（排除选项、答案行）
        script_end = q_idx if q_idx is not None else first_opt
        script_lines = []
        for i in range(1, script_end):
            txt = lines[i][1]
            if txt.startswith("答え") or txt.startswith("答案"):
                continue
            script_lines.append(txt)
        # 题干 = 导语 + 设问
        question = intro
        if question_tail and question_tail != intro:
            question = f"{intro}\n{question_tail}" if intro else question_tail

        return {
            "date": date,
            "audio_url": audio_url,
            "question": question,
            "article": "\n".join(script_lines).strip(),
            "choice": choice,
            "answer": answer,
            "analysis": "",  # 82 题面无答案说明，解析由 --listening 审核阶段生成
        }

    def run(self):
        self.crawl(shitibiao=self.SHITIBIAO, count=self.COUNT, filename=f"result_{self.SHITIBIAO}.json")


if __name__ == "__main__":
    from crawler.config import require
    spider = TestType13(username=require("SPIDER_USERNAME"), password=require("SPIDER_PASSWORD"))
    spider.run()
