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
| 单项选择 | 独立题干 + 4 个选项 |
| 完形填空 | 文章中挖空，每空 4 个选项 |
| 阅读理解 | 文章 + N 道问题，每题 4 个选项 |

### 考试级别

N1 ~ N5 全级别（当前题库以 N1 为主）

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
│   │   └── tools.py            # 5 个 Agent 工具（见 Agent 设计）
│   ├── api/
│   │   ├── deps.py             # FastAPI 依赖：get_db / get_current_user / require_admin
│   │   ├── main.py             # FastAPI 应用入口，CORS
│   │   └── routers/
│   │       ├── auth.py         # 注册 / 登录 / /me
│   │       ├── questions.py    # 题库 CRUD
│   │       ├── exams.py        # 组卷 / 做题 / 提交 / 结果 / 历史
│   │       └── agent.py        # 同步对话 + SSE 流式对话
│   ├── schemas/                # Pydantic 模型
│   └── utils/
│       └── security.py         # JWT 签发 / 校验，bcrypt 哈希
│
├── crawler/                    # 数据采集模块
│   ├── config.py               # DB / LLM / 爬虫配置，从 .env 读取
│   ├── db/
│   │   └── schema.sql          # 建表 DDL（含 users / exams / exam_items）
│   ├── spiders/                # 爬虫：登录认证、HTML 解析、写库
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
│       └── views/
│           ├── LoginView.vue   # 登录 + 注册
│           ├── ExamView.vue    # 组卷配置 + 答题
│           ├── ResultView.vue  # 考试结果 + AI 逐题解析 + 薄弱点分析
│           ├── HistoryView.vue # 考试历史列表
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

### ER 关系

```
users  1──N  exams  1──N  exam_items  N──1  question_groups
                                                  │
                                            1──N  questions  1──N  options
```

### question_groups 核心字段

```sql
type             ENUM('single_choice', 'cloze', 'reading')
level            VARCHAR(10)   -- N1~N5
difficulty       TINYINT       -- 0-9
knowledge_points JSON          -- ["条件表达", "て形用法"]
source           VARCHAR(100)  -- 来源批次，如 result_67
source_ref       VARCHAR(100)  -- UNIQUE，幂等去重
```

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
| POST | `/exams/generate` | 智能组卷 | 登录 |
| GET | `/exams/{id}` | 试卷内容（不含答案） | 归属用户 |
| POST | `/exams/{id}/submit` | 提交答案并判分 | 归属用户 |
| GET | `/exams/{id}/result` | 考试结果与解析 | 归属用户 |

POST `/exams/generate` 参数：`level` / `types` / `total_questions` / `difficulty_range` / `time_limit_minutes`

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

基于 LangGraph `create_react_agent`，DeepSeek 作为 LLM，`MemorySaver` 按 `session_id` 保持多轮记忆。

### 工具集

| 工具 | 功能 | 典型触发 |
|------|------|------|
| `fetch_questions` | 按条件检索题库真题 | "给我看几道N2的语法题" |
| `generate_exam` | 智能组卷并落库（含 user_id） | "帮我出一套10题模拟卷" |
| `explain_grammar` | LLM 生成结构化语法讲解 | "讲解一下ば和たら的区别" |
| `answer_judge` | AI 判断作答并给出个性化解析 | "这道题我选了B，为什么不对" |
| `analyze_weak_points` | 查指定试卷错题，聚合薄弱知识点 | "分析我刚才考试的薄弱点" |

### 流式输出

`stream_agent()` 通过 `astream_events(version="v2")` 监听：
- `on_chat_model_stream`：逐 token 推送文字
- `on_tool_start`：工具调用开始时推送工具名和参数

前端用 `EventSource` 连接 SSE 端点，边收边渲染，带闪烁光标。

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

题目已通过爬虫采集并经 LLM 校验，存于 `data/` 目录下的 JSON 文件中。批量入库：

```bash
uv run python -m crawler.spiders.write_to_mysql
```

### 8. 运行测试

后端测试基于 pytest，覆盖安全工具（密码哈希 / JWT）、认证接口、会话持久化与越权校验、题库读接口。

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
- 当前题库全为 N1 单选题（355 题），可继续运行爬虫采集其他级别
