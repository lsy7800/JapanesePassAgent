# JapanesePassAgent - 日语能力考试智能题库与学习系统

## 目录

- [项目概述](#项目概述)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [架构说明](#架构说明)
- [数据库设计](#数据库设计)
- [API 设计](#api-设计)
- [Agent 设计](#agent-设计)
- [快速启动](#快速启动)
- [注意事项](#注意事项)

---

## 项目概述

JapanesePassAgent 是一套面向日语能力考试（JLPT）的智能题库与学习辅助系统，涵盖从数据采集到在线学习的完整闭环：

1. **题库采集**：自动爬取 JLPT 真题，支持单选题、完形填空、阅读理解三种题型
2. **数据校验**：通过 DeepSeek LLM 对原始题目进行校验、纠错、知识点标注、难度评估
3. **题库管理**：结构化存储到 MySQL，管理员可在后台对题目进行校对和维护
4. **在线考试**：按级别/题型/难度智能组卷，支持计时、自动判分、错题解析
5. **AI 辅导**：基于 LangGraph 的多轮对话 Agent，支持语法讲解、组卷练习、错题分析、薄弱点总结

### 支持题型

| 题型 | 说明 |
|------|------|
| 单项选择 | 独立题干 + 4 个选项（汉字读音、词汇辨析、语法形式、排序等） |
| 完形填空 | 文章中挖空，每空 4 个选项 |
| 阅读理解 | 文章 + N 道问题，每题 4 个选项（短篇/中篇/长篇/论述/综合理解/信息检索） |
| 听力 | 音频 + 设问 + 选项（課題理解 / ポイント理解 / 概要理解 / 即時応答 / 統合理解） |

信息检索题的文章含表格等结构化内容，`article` 字段用一套带语义标记的半成品格式存储，
由前端 `renderArticle()` 翻译成 HTML——格式规范见 [`docs/article-format.md`](docs/article-format.md)。

### 考试级别

N1 ~ N5 全级别（当前题库仅 N1，前端级别选项暂只开放 N1）

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 编程语言 | Python 3.14 |
| 包管理 | uv |
| 数据库 | MySQL 8.x（Docker 本地开发） |
| 数据库驱动 | PyMySQL（DictCursor，无 ORM） |
| 爬虫 | requests + lxml |
| LLM / Agent | DeepSeek API + LangGraph 1.x + langchain-openai |
| 后端框架 | FastAPI 0.139 + uvicorn |
| 认证 | JWT（python-jose）+ bcrypt 5.x |
| 前端（管理后台） | Vite + Vue 3 + Element Plus + Pinia |
| 前端（学生端） | Vite + Vue 3 + Element Plus + Pinia |
| 实时通信 | SSE（Server-Sent Events，astream_events） |

---

## 项目结构

```
JapanesePassAgent/
├── backend/                    # 后端服务
│   ├── agent/
│   │   ├── graph.py            # LangGraph ReAct Agent，run_agent / stream_agent
│   │   └── tools.py            # 7 个 Agent 工具（见 Agent 设计）
│   ├── api/
│   │   ├── deps.py             # FastAPI 依赖：get_db / get_current_user / require_admin
│   │   ├── main.py             # FastAPI 应用入口，CORS
│   │   └── routers/
│   │       ├── auth.py         # 注册 / 登录 / /me
│   │       ├── questions.py    # 题库 CRUD
│   │       ├── exams.py        # 组卷 / 做题 / 提交 / 结果 / 历史 / 导出
│   │       └── agent.py        # 同步对话 + SSE 流式对话
│   ├── services/
│   │   ├── exam_builder.py     # 确定性建卷（抽题、落库）
│   │   ├── exam_planner.py     # LLM 组卷规划（异常自兜底）
│   │   ├── smart_exam.py       # 智能组卷编排，同步与 SSE 两条路径共用
│   │   └── stats_service.py    # 薄弱知识点聚合
│   ├── schemas/                # Pydantic 模型
│   └── utils/
│       └── security.py         # JWT 签发 / 校验，bcrypt 哈希
│
├── crawler/                    # 数据采集模块
│   ├── config.py               # DB / LLM / 爬虫配置，从 .env 读取
│   ├── db/
│   │   ├── schema.sql          # 建表 DDL（含 users / exams / exam_items）
│   │   └── migrate_add_unique_keys.py  # 迁移：补 upsert 所需唯一键（旧库升级用）
│   ├── spiders/                # 爬虫：登录认证、HTML 解析、写库
│   │   └── write_to_mysql.py   # 按 source_ref upsert 入库（幂等，不破坏历史试卷）
│   └── llm/
│       └── validate.py         # LLM 校验与知识点增强
│
├── frontend/                   # 管理后台（端口 5173）
│   └── src/
│       ├── api/                # questions.js / auth.js / http.js（统一 axios + JWT）
│       ├── stores/auth.js      # Pinia auth store，持久化 token
│       ├── router/             # 路由守卫（未登录跳 /login，非 admin 拒绝）
│       └── views/
│           ├── LoginView.vue
│           ├── QuestionList.vue
│           └── QuestionDetail.vue
│
├── student/                    # 学生端（端口 5174）
│   └── src/
│       ├── api/                # exam.js / agent.js / auth.js / http.js
│       ├── stores/auth.js
│       ├── router/             # 路由守卫（未登录跳 /login）
│       ├── utils/
│       │   ├── sse.js          # SSE 封装：错误分类 / 收尾语义（各流式入口共用）
│       │   ├── toolLabels.js   # Agent 工具名 → 中文进度文案
│       │   └── audio.js        # 听力音频 URL 拼接
│       └── views/
│           ├── LoginView.vue   # 登录 + 注册
│           ├── ExamView.vue    # 组卷配置（手动 / AI）+ 答题
│           ├── ResultView.vue  # 考试结果 + AI 逐题解析 + 薄弱点分析
│           ├── HistoryView.vue # 考试历史列表
│           ├── StatsView.vue   # 学习统计
│           └── ChatView.vue    # AI 多轮对话（SSE 流式）
│
├── scripts/
│   └── create_admin.py         # 命令行创建管理员账号
│
├── docker-compose.yml          # MySQL 8 本地开发容器
├── pyproject.toml
└── .env.example
```

---

## 架构说明

```
┌─────────────┐    ┌──────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│  数据采集层   │ -> │  数据处理层   │ -> │  服务层               │ -> │  展示层           │
│  (Crawler)  │    │  (LLM校验)   │    │  (FastAPI + Agent)   │    │  (Vue 3 前端)    │
└─────────────┘    └──────────────┘    └──────────────────────┘    └──────────────────┘
   爬虫 + 解析       DeepSeek 校验        JWT 认证 / 路由              管理后台 :5173
   HTML → JSON       知识点标注           题库 CRUD                    学生端 :5174
   写入 MySQL         难度评估             LangGraph Agent
                                         SSE 流式输出
```

---

## 数据库设计

### 表概览

| 表名 | 说明 |
|------|------|
| `users` | 用户（email / bcrypt 密码 / role） |
| `question_groups` | 题组（题型 / 级别 / 难度 / 知识点 / 来源） |
| `questions` | 子题（题干 / 划线词 / 答案 / 解析） |
| `options` | 选项（a/b/c/d） |
| `exams` | 试卷（user_id / 级别 / 题数 / 限时 / 状态 / 得分） |
| `exam_items` | 试卷题目明细（seq / group_id / user_answer / is_correct） |
| `chat_sessions` | Agent 会话（user_id / 标题 / 时间） |
| `chat_messages` | 会话消息（role / content），多轮记忆的持久化载体 |

### ER 关系

```
users  1──N  exams          1──N  exam_items  N──1  question_groups
   │                                                      │
   └───N  chat_sessions  1──N  chat_messages        1──N  questions  1──N  options
```

`exam_items.group_id` 的外键是 `ON DELETE CASCADE`——删题组会连带删掉引用它的作答记录。
这决定了入库必须用 upsert 而非删后重建，详见「导入题目」一节。

### question_groups 核心字段

```sql
type             ENUM('single_choice', 'cloze', 'reading', 'listening')
category         VARCHAR(30)   -- JLPT 题型 code，见 backend/config/categories.py
article          TEXT          -- 阅读文章 / 听力原文脚本；单选题为 NULL
audio_url        VARCHAR(255)  -- 听力音频相对路径（只存地址，不下载 mp3）
level            VARCHAR(10)   -- N1~N5
exam_date        VARCHAR(20)   -- 场次，如 2017-12-N1
difficulty       TINYINT       -- 0-9
knowledge_points JSON          -- ["条件表达", "て形用法"]
source           VARCHAR(100)  -- 来源批次，如 result_67
source_ref       VARCHAR(100)  -- UNIQUE，幂等去重的依据（upsert 按此列匹配）
```

`questions` 有 `UNIQUE(group_id, seq)`、`options` 有 `UNIQUE(question_id, label)`——
这两个键是子题/选项能 upsert 的前提，缺了就只能删后重建（会打穿历史试卷，见「导入题目」一节）。

---

## API 设计

Base URL: `/api/v1`

### 认证

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/auth/register` | 注册（role 固定为 student） | 公开 |
| POST | `/auth/login` | 登录，返回 JWT | 公开 |
| GET | `/auth/me` | 当前用户信息 | 登录 |

> 管理员账号通过命令行创建：`uv run python -m scripts.create_admin --email x --password y`

### 题库管理

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/sources` | 题库批次列表及题数 | 公开 |
| GET | `/questions` | 题目列表（分页 + 多维筛选） | 公开 |
| GET | `/questions/{id}` | 完整题组（含子题和选项） | 公开 |
| POST | `/questions` | 创建题组 | admin |
| PUT | `/questions/{id}` | 全量替换题组 | admin |
| DELETE | `/questions/{id}` | 删除题组 | admin |

GET `/questions` 支持参数：`type` / `level` / `difficulty_min` / `difficulty_max` / `knowledge_point` / `source` / `page` / `page_size`

### 考试

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/exams` | 当前用户考试历史（已提交，分页） | 登录 |
| POST | `/exams/generate` | 手动组卷（按题型/难度筛选） | 登录 |
| POST | `/exams/smart-generate` | AI 智能组卷（一次性返回） | 登录 |
| GET | `/exams/smart-generate/stream` | AI 智能组卷（SSE，逐阶段推进度） | 登录 |
| GET | `/exams/{id}` | 试卷内容（不含答案） | 归属用户 |
| POST | `/exams/{id}/submit` | 提交答案并判分 | 归属用户 |
| GET | `/exams/{id}/result` | 考试结果与解析 | 归属用户 |
| GET | `/exams/{id}/export` | 导出 Markdown 试卷 | 归属用户 |

POST `/exams/generate` 参数：`level` / `types` / `total_questions` / `difficulty_range` / `time_limit_minutes`

#### AI 智能组卷的两个端点

组卷要串行跑「薄弱点聚合 → LLM 规划 → 抽题落库」，其中 LLM 一步就要 10~30 秒。
POST 版本期间前端只能干等，故另提供 SSE 版本逐阶段推送进度：

```json
{"type": "stage", "key": "weak",      "message": "正在分析你的历史错题与薄弱知识点…"}
{"type": "stage", "key": "weak_done", "message": "已定位薄弱点：细节理解、主旨理解", "weak_count": 62}
{"type": "stage", "key": "plan",      "message": "AI 正在规划组卷方案，通常需要 10~30 秒…"}
{"type": "plan",  "summary": "N1 · 内容理解（短篇） 2 题、中篇 2 题", "rationale": "本卷针对你的薄弱点…"}
{"type": "stage", "key": "build",     "message": "正在从题库抽题、生成试卷…"}
{"type": "done",  "exam_id": 108, "groups": 5, "rationale": "…", "shortfalls": []}
{"type": "error", "code": "no_questions", "detail": "没有符合条件的题目，请调整需求后再试"}
```

要点：
- `plan` 事件在方案确定的那一刻就推出，用户不必等落库即可看到 AI 的组卷思路
- `done.groups` 是**题组数**，不等于可评分子题数（阅读一篇文章可含多问）；
  真实题量由前端随后 `GET /exams/{id}` 取回的 `total` 决定
- 错误在流内以 `error` 事件表达（HTTP 状态码仍是 200，因 SSE 已建立）
- 编排逻辑在 `backend/services/smart_exam.py`，同步与 SSE 两条路径共用同一套步骤实现

### Agent 对话

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/agent/chat` | 同步对话 | 登录 |
| GET | `/agent/stream` | SSE 流式对话（token 通过 query 传递） | 登录 |

SSE 事件格式：
```json
{"type": "token",  "content": "..."}
{"type": "tool",   "name": "fetch_questions", "args": {...}}
{"type": "done",   "session_id": "..."}
{"type": "error",  "detail": "..."}
```

---

## Agent 设计

基于 LangGraph `create_react_agent`，DeepSeek 作为 LLM。多轮记忆持久化在 MySQL
（`chat_sessions` / `chat_messages`），每轮读取该会话历史拼进上下文，不再用进程内
`MemorySaver`——重启或刷新都不丢上下文。

### 工具集

| 工具 | 功能 | 典型触发 |
|------|------|------|
| `fetch_questions` | 按条件检索题库真题 | "给我看几道N2的语法题" |
| `generate_exam` | 智能组卷并落库（含 user_id） | "帮我出一套10题模拟卷" |
| `explain_grammar` | LLM 生成结构化语法讲解 | "讲解一下ば和たら的区别" |
| `answer_judge` | AI 判断作答并给出个性化解析 | "这道题我选了B，为什么不对" |
| `analyze_weak_points` | 查指定试卷错题，聚合薄弱知识点 | "分析我刚才考试的薄弱点" |
| `recommend_questions` | 按薄弱知识点推荐针对性练习题 | "针对我的弱项再练几道" |
| `export_exam` | 把已生成的试卷导出为可下载 Markdown | "把这套卷导出成文件" |

### 流式输出

`stream_agent()` 通过 `astream_events(version="v2")` 监听：
- `on_chat_model_stream`：逐 token 推送文字
- `on_tool_start`：工具调用开始时推送工具名和参数

前端统一走 `student/src/utils/sse.js` 的 `openSSE()` 封装（`chatStream` 与智能组卷共用），
边收边渲染，带闪烁光标。该封装解决了原生 `EventSource` 的三个问题：

| 问题 | 处理 |
|------|------|
| `onerror` 不区分「网络断」与「服务端返回错误」，只能笼统提示"连接中断" | 回调带 `kind` 参数（`'network'` / `'server'`），文案分开 |
| 正常收尾后 `EventSource` 自动重连会再触发一次 `onerror`，误报错误 | 用「是否已收到 done/error」标记压掉收尾后的 `onerror` |
| 主动 `close()` 不触发任何回调，调用方易漏掉状态复位导致 loading 卡死 | 保证 `onClose(reason)` 在正常结束/出错/主动取消时都调用一次 |

**首 token 前的等待反馈**：工具调用（如 `answer_judge`）内部还有一次完整的 LLM 调用，
首个 token 要等它跑完才来。这段空白期用 `tool` 事件驱动进度提示——工具名经
`student/src/utils/toolLabels.js` 映射成中文文案（`answer_judge` → "正在逐句翻译原文并生成解析…"），
配骨架屏；超过 8 秒仍无输出会补一句预期耗时。三处 AI 入口（解析 / 薄弱点分析 / 聊天）
都可随时「停止」，出错时保留已收到的部分内容并给「重试」。

---

## 快速启动

### 前置条件

- Python 3.14，uv
- Docker（运行 MySQL）
- Node.js 18+

### 1. 克隆并安装依赖

```bash
git clone git@github.com:lsy7800/JapanesePassAgent.git
cd JapanesePassAgent
uv sync
```

### 2. 启动 MySQL

```bash
docker-compose up -d
# MySQL 监听 localhost:3307，账号 root/root，库名 jlpt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写 DB_PASSWORD、DEEPSEEK_API_KEY、JWT_SECRET
```

`.env` 必填项：

```env
DB_HOST=localhost
DB_PORT=3307
DB_USER=root
DB_PASSWORD=root
DB_NAME=jlpt

DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

JWT_SECRET=your_random_secret_here
```

### 4. 建表

```bash
mysql -h 127.0.0.1 -P 3307 -u root -proot jlpt < crawler/db/schema.sql
```

### 5. 创建管理员账号

```bash
uv run python -m scripts.create_admin --email admin@example.com --password yourpassword
```

### 6. 启动服务

```bash
# 终端1 - 后端 API
uv run uvicorn backend.api.main:app --reload

# 终端2 - 管理后台 http://localhost:5173
cd frontend && npm install && npm run dev

# 终端3 - 学生端 http://localhost:5174
cd student && npm install && npm run dev
```

### 7. 导入题目（可选）

题目已通过爬虫采集并经 LLM 校验，存于 `data/raw/` 下的 JSON 文件中。批量入库：

```bash
uv run python -m crawler.spiders.write_to_mysql
```

每批数据**只保留一个权威文件**，对应的 `source` / `category` / 入库函数见
[`docs/data-sources.md`](docs/data-sources.md)。**入库只用该清单列出的文件**——同一批曾
存在多个字段完整度不同的版本，误用过一次导致 40 道题选项全丢。

入库是**幂等**的：按 `source_ref` upsert，题组 id 保持稳定，可以放心重跑。只有源数据里
已消失的题组才会被删除，且若它仍被试卷引用会先打印警告。

> **为什么不能改回「删后重建」**：`exam_items.group_id` 的外键是 `ON DELETE CASCADE`，
> 删题组会连带删掉引用它的作答记录，历史试卷变成空壳或缺题。这个坑实际踩过（29 张
> 试卷被打穿）。回归测试见 `tests/test_reingest_idempotent.py`。
>
> 从旧版本升级的库需要先补唯一键（子题/选项的 upsert 依赖它）：
> ```bash
> uv run python -m crawler.db.migrate_add_unique_keys
> ```
> 该脚本幂等，新建库无需执行（`schema.sql` 已含这两个键）。

### 8. 运行测试

后端测试基于 pytest，共 63 项：

| 文件 | 覆盖 |
|------|------|
| `test_security.py` / `test_auth.py` | 密码哈希、JWT 签发校验、注册登录、角色权限 |
| `test_sessions.py` / `test_chat_repo.py` | 会话持久化与越权校验 |
| `test_questions.py` | 题库读接口 |
| `test_cloze_exam.py` / `test_whole_exam.py` | 完形题组卷、整场真题组卷 |
| `test_smart_exam.py` | AI 智能组卷：同步路径 + SSE 阶段序列、冷启动、空题池、规划器异常兜底 |
| `test_reingest_idempotent.py` | 重新入库幂等性、**历史试卷与作答记录不被破坏** |

```bash
uv run pytest
```

> 测试会自动创建独立库 `jlpt_test`（用 `SHOW CREATE TABLE` 从当前库克隆结构，含外键），
> 用完即 `DROP`，**不触碰真实 `jlpt` 数据**；无需联网、不调用 DeepSeek。

---

## 注意事项

- `.env` 已加入 `.gitignore`，不会提交到仓库
- `JWT_SECRET` 生产环境请使用随机长字符串：`openssl rand -hex 32`
- 公开注册接口仅允许注册 `student` 角色，`admin` 只能通过 `scripts/create_admin.py` 创建
- 当前题库全为 **N1**，共 2201 个题组 / 2697 道子题：单选 1085、完形 28 篇（135 空）、
  阅读 310 篇（676 问）、听力 778 组（801 问）。前端级别选项暂只开放 N1，
  其他级别待采集后再放开
- 听力题**只存音频相对路径**（`question_groups.audio_url`），不下载 mp3 文件；
  前端拼可配置的 base 前缀播放
- 重新入库是幂等的（按 `source_ref` upsert），可放心重跑；但注意**别用错入库函数**——
  扁平结构用 `write_listening_to_mysql`，嵌套 `questions` 结构用
  `write_listening_passage_to_mysql`，用错会因解析不出子题而报错中止
