# 题库数据源清单

`data/raw/` 下每批数据**只保留一个权威文件**——即当前数据库内容的来源。
中间产物（爬虫原始输出、LLM 校验前的版本、审核报告）已删除，需要时重跑对应流程即可。

> `data/` 在 `.gitignore` 中，不进仓库。本文档是它的索引。

## 为什么要有这份清单

同一批数据曾同时存在 `result_84.json` / `_listened.json` / `_checked.json` 三个版本，
且**字段完整度互不相同**：`_checked` 有 LLM 校验后的解析但 `choice` 为空，
`result_84.json` 反之。曾因此误用文件导致 40 道题的选项全部丢失。

**规则：入库只用本表列出的文件。** 若某批需要重新校验，产出新文件后更新本表并删掉旧的。

## 清单

| 文件 | DB `source` | `category` | 入库函数 | 题组 | 子题 | 选项 |
|------|-------------|-----------|----------|-----:|-----:|-----:|
| `result_67_validated.json` | `result_67_validated` | `kanji_reading` | `write_to_mysql` | 165 | 165 | 660 |
| `result_68_validated.json` | `result_68_validated` | `context` | `write_to_mysql` | 190 | 190 | 760 |
| `result_69_validated.json` | `result_69_validated` | `paraphrase` | `write_to_mysql` | 165 | 165 | 660 |
| `result_70_validated.json` | `result_70_validated` | `usage` | `write_to_mysql` | 165 | 165 | 660 |
| `result_71_validated.json` | `result_71_validated` | `grammar_form` | `write_to_mysql` | 280 | 280 | 1120 |
| `result_72_validated.json` | `result_72_validated` | `grammar_order` | `write_to_mysql` | 120 | 120 | 480 |
| `result_73_validated.json` | `result_73_validated` | `text_grammar` | `write_passage_to_mysql` | 28 | 135 | 540 |
| `result_74_validated.json` | `result_74_validated` | `reading_short` | `write_reading_to_mysql` | 111 | 111 | 444 |
| `result_75_checked.json` | `result_75_validated` | `reading_mid` | `write_reading_to_mysql` | 99 | 277 | 1108 |
| `result_76_checked.json` | `result_76_validated` | `reading_long` | `write_reading_to_mysql` | 22 | 88 | 352 |
| `result_77_checked.json` | `result_77_validated` | `reading_integ` | `write_reading_to_mysql` | 28 | 56 | 224 |
| `result_78_checked.json` | `result_78_validated` | `reading_thesis` | `write_reading_to_mysql` | 22 | 88 | 352 |
| `result_79_checked.json` | `result_79_checked` | `info_search` | `write_reading_to_mysql` | 28 | 56 | 224 |
| `result_80_checked.json` | `result_80` | `task_listening` | `write_listening_to_mysql` | 133 | 133 | 532 |
| `result_81_checked.json` | `result_81` | `point_listening` | `write_listening_to_mysql` | 152 | 152 | 608 |
| `result_82_checked.json` | `result_82` | `summary_listen` | `write_listening_to_mysql` | 130 | 130 | 520 |
| `result_83_checked.json` | `result_83` | `quick_response` | `write_listening_to_mysql` | 300 | 300 | 900 |
| `result_84_checked.json` | `result_84` | `integ_listen` | `write_listening_to_mysql` | 40 | 40 | 160 |
| `result_85_checked.json` | `result_85` | `integ_listen` | `write_listening_passage_to_mysql` | 23 | 46 | 176 |
| **合计** | | | | **2201** | **2697** | **10480** |

注意几处不直观的地方：

- **文件名与 `source` 不一致**：75~78 的文件是 `_checked` 但 `source` 仍是 `_validated`
  （历史遗留，改 `source` 会导致题组 id 变化，进而打穿引用它们的历史试卷，故保持不动）。
- **84 与 85 同为 `integ_listen` 但入库函数不同**：84 是扁平结构（一段音频一问），
  85 是嵌套 `questions` 结构（一段音频多问）。**用错函数会因解析不出子题而报错中止**
  （这是有意的防护，见 `write_to_mysql._prune_questions`）。
- **83 是 3 选项**：即時応答题型本就只有 3 个选项，不是数据缺失。
- **85 有 2 道子题无选项**：源数据本身缺失，非入库问题。
- **84 的题干为空**：源站题干是模型补的、非原题，已按要求清空，`content` 应为空字符串。

## 全量重建

```bash
# 按上表逐批入库；入库是幂等的（按 source_ref upsert），可安全重跑
uv run python -m crawler.spiders.write_to_mysql
```

入库为何必须用 upsert 而非删后重建，见 [README「导入题目」](../README.md#7-导入题目可选)。

已验证：上表 19 个文件能把全库 2697 行**逐字段一致**地重建出来（对比过 `source_ref` +
`seq` 粒度的 `type`/`category`/`level`/`exam_date`/`audio_url`/`article`/`content`/
`answer`/`analysis`/选项集合）。
