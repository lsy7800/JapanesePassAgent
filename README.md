# JapanesePassAgent - 日语能力考试智能题库与 Agent 系统

## 目录

- [项目概述](#项目概述)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [架构说明](#架构说明)
- [数据库设计](#数据库设计)
- [富文本 JSON 方案](#富文本-json-方案)
- [API 设计](#api-设计)
- [Agent 设计](#agent-设计)
- [部署说明](#部署说明)

---

## 项目概述

JapanesePassAgent 是一套面向日语能力考试（JLPT）的智能题库与学习辅助系统。项目涵盖以下核心能力：

1. **题库采集**：从在线考试平台自动爬取 JLPT 真题，支持多种题型解析
2. **数据校验**：通过 LLM（DeepSeek）对采集的原始题目进行智能校验、纠错、解析增强
3. **题库管理**：结构化存储到 MySQL，支持按题型 / 难度 / 知识点检索
4. **智能 Agent**：基于 LLM 的日语考试辅助 Agent，提供组卷、做题、判题、错题分析、知识点讲解等能力

### 支持题型

| 题型 | 说明 | 示例 |
|------|------|------|
| **单项选择题** | 单独的题干 + 4 个选项，选择唯一正确答案 | 词汇读音题、语法填空题 |
| **完形填空** | 一篇文章中挖空，每空 4 个选项（题干为空，答案依据上下文） | 文章中的语法 / 词汇填空 |
| **阅读理解** | 一篇文章 + N 道问题，每题 4 个选项（题干有具体问题内容，题数不固定） | 长文阅读、信息检索 |

### 考试级别

支持 JLPT N1 ~ N5 全级别题库。

---

## 技术栈

| 类别 | 技术 |
|------|------|
| 编程语言 | Python 3.14 |
| 包管理 | uv |
| 数据库 | MySQL 8.x |
| ORM / 数据库驱动 | PyMySQL |
| 爬虫 | requests + lxml |
| LLM | DeepSeek API |
| Agent 框架 | LangGraph（规划中） |
| 后端框架 | FastAPI（规划中） |
| 前端 | 待定（规划中） |

---

## 项目结构

```
JapanesePassAgent/
├── main.py                  # 项目入口
├── pyproject.toml           # 项目配置与依赖
├── uv.lock                  # 依赖锁文件
├── .python-version          # Python 版本 (3.14)
│
├── backend/                 # 后端服务
│   ├── api/                 # API 路由层
│   └── schemas/             # 数据模型 / 校验
│
├── crawler/                 # 数据采集模块
│   ├── __init__.py
│   ├── spiders/             # 爬虫实现
│   │   ├── spider.py        # 爬虫基类（认证、请求、数据保存）
│   │   ├── auth.py          # 登录认证与 Cookie 管理
│   │   ├── test_type_1.py   # 题型一爬虫（单选题）
│   │   ├── test_type_2.py   # 题型二爬虫（完形填空 / 阅读理解）
│   │   └── write_to_mysql.py # 数据写入 MySQL
│   └── llm/
│       └── validate.py      # LLM 题目校验与增强
│
├── data/                    # 数据目录
│   ├── cookies.json         # 登录态 Cookie 缓存
│   └── raw/                 # 爬取的原始 JSON 数据
│       ├── result_XX.json           # 原始爬取数据
│       └── result_XX_validated.json # LLM 校验后数据
│
└── frontend/                # 前端应用
    └── src/                 # 前端源码
```

---

## 架构说明

系统整体分为 4 层，数据从左向右流动：

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  数据采集层   │ -> │  数据处理层    │ -> │  服务层       │ -> │  展示层       │
│  (Crawler)   │    │  (LLM校验)    │    │  (API+Agent) │    │  (Frontend)  │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
      │                   │                   │                   │
   爬虫采集           DeepSeek校验        FastAPI路由           用户界面
   Cookie管理         格式标准化          Agent编排             做题交互
   HTML解析           知识点提取          题库查询              成绩展示
   JSON存储           难度评估            智能组卷              错题回顾
```

### 数据流

```
在线考试平台 ──爬虫──> raw JSON ──LLM校验──> validated JSON ──写入──> MySQL
                                                                      │
用户 <──前端──< API响应 <──FastAPI──< Agent/服务 <──查询──────────────────┘
```

### 模块职责

| 模块 | 职责 |
|------|------|
| `crawler/spiders/spider.py` | 爬虫基类，提供认证、HTTP 请求、数据保存等基础能力 |
| `crawler/spiders/auth.py` | 登录认证、Cookie 持久化与有效性检测 |
| `crawler/spiders/test_type_*.py` | 各题型专用爬虫，负责 HTML 解析与数据提取 |
| `crawler/llm/validate.py` | 调用 DeepSeek 对原始题目进行校验、纠错、格式标准化、知识点标注 |
| `crawler/spiders/write_to_mysql.py` | 将校验后的 JSON 数据批量写入 MySQL |
| `backend/api/` | RESTful API 路由（规划中） |
| `backend/schemas/` | Pydantic 数据模型（规划中） |

---

## 数据库设计

采用 **三表结构** 设计，将原本扁平化的单表拆分为 `question_groups`、`questions`、`options` 三张表，以统一支持所有题型。

### ER 关系图

```
question_groups  1 ──── N  questions  1 ──── N  options
   (题组/大题)              (子题)                (选项)
```

### 表结构

#### 1. question_groups（题组表）

每一道大题对应一条记录。单选题也视为只含一道子题的题组。

```sql
CREATE TABLE question_groups (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    type            ENUM('single_choice', 'cloze', 'reading') NOT NULL COMMENT '题型：单选/完形填空/阅读理解',
    article         TEXT DEFAULT NULL COMMENT '文章内容（完形填空和阅读理解使用，单选题为NULL）',
    level           VARCHAR(10) DEFAULT '' COMMENT '考试级别：N1/N2/N3/N4/N5',
    exam_date       VARCHAR(20) DEFAULT '' COMMENT '考试日期，如 2023-07',
    difficulty      TINYINT DEFAULT 0 COMMENT '难度评级（1-9）',
    knowledge_points JSON DEFAULT NULL COMMENT '知识点标签数组',
    source          VARCHAR(100) DEFAULT '' COMMENT '数据来源标识',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='题组表';
```

#### 2. questions（子题表）

每道具体的小题对应一条记录。

```sql
CREATE TABLE questions (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    group_id        INT NOT NULL COMMENT '关联的题组ID',
    seq             INT NOT NULL DEFAULT 1 COMMENT '在题组内的顺序号（单选题固定为1）',
    content         TEXT DEFAULT NULL COMMENT '题干内容（完形填空此字段为空，阅读理解有具体问题）',
    marked          VARCHAR(255) DEFAULT '' COMMENT '划线词/标记词',
    answer          VARCHAR(10) NOT NULL DEFAULT '' COMMENT '正确答案：a/b/c/d',
    analysis        TEXT DEFAULT NULL COMMENT '解析文本',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_group_id (group_id),
    FOREIGN KEY (group_id) REFERENCES question_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='子题表';
```

#### 3. options（选项表）

每个选项对应一条记录。

```sql
CREATE TABLE options (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    question_id     INT NOT NULL COMMENT '关联的子题ID',
    label           CHAR(1) NOT NULL COMMENT '选项标签：a/b/c/d',
    content         VARCHAR(500) NOT NULL DEFAULT '' COMMENT '选项内容',
    INDEX idx_question_id (question_id),
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='选项表';
```

### 题型数据映射

#### 单选题

```
question_groups: { type: 'single_choice', article: NULL, level: 'N1', ... }
    └── questions: { seq: 1, content: '検討の結果、この計画は___ことになりました。', marked: '見合わせる', answer: 'd' }
            ├── options: { label: 'a', content: '承認する' }
            ├── options: { label: 'b', content: '実施する' }
            ├── options: { label: 'c', content: '変更する' }
            └── options: { label: 'd', content: '中止する' }
```

#### 完形填空

```
question_groups: { type: 'cloze', article: '昨日、友人と___に行った。...', level: 'N2', ... }
    ├── questions: { seq: 1, content: NULL, answer: 'b' }  -- 完形填空题干为空
    │       ├── options: { label: 'a', content: '...' }
    │       ├── options: { label: 'b', content: '...' }
    │       ├── options: { label: 'c', content: '...' }
    │       └── options: { label: 'd', content: '...' }
    ├── questions: { seq: 2, content: NULL, answer: 'a' }
    │       └── ... (4 个选项)
    └── ... (最多10道子题)
```

#### 阅读理解

```
question_groups: { type: 'reading', article: '日本の教育制度について...', level: 'N1', ... }
    ├── questions: { seq: 1, content: '筆者が最も言いたいことは何か。', answer: 'c' }
    │       └── ... (4 个选项)
    ├── questions: { seq: 2, content: 'この文章のタイトルとして最も適切なものは...', answer: 'a' }
    │       └── ... (4 个选项)
    └── ... (子题数量不固定)
```

### 常用查询示例

```sql
-- 获取一道完整的单选题（含选项）
SELECT qg.type, qg.level, q.content, q.marked, q.answer, q.analysis,
       o.label, o.content AS option_content
FROM question_groups qg
JOIN questions q ON q.group_id = qg.id
JOIN options o ON o.question_id = q.id
WHERE qg.id = 1
ORDER BY q.seq, o.label;

-- 按知识点检索题目
SELECT qg.id, qg.type, qg.level, qg.difficulty
FROM question_groups qg
WHERE JSON_CONTAINS(qg.knowledge_points, '"条件表达"');

-- 按难度和级别筛选题目用于组卷
SELECT qg.id, qg.type, COUNT(q.id) AS question_count
FROM question_groups qg
JOIN questions q ON q.group_id = qg.id
WHERE qg.level = 'N1' AND qg.difficulty BETWEEN 3 AND 6
GROUP BY qg.id
ORDER BY RAND()
LIMIT 20;
```

---

## 富文本 JSON 方案

### 背景

题干（question content）和文章（passage/article）中可能包含需要特殊展示的富文本元素，例如：

- **题干**：下划线标记词、加粗关键词、高亮重点等
- **文章**：加粗、下划线、表格（如对比信息、时间表）等

为统一前后端对富文本的渲染，采用自定义的 **行内标记 + 块级元素** JSON 结构，无需引入第三方富文本编辑器依赖。

### 设计原则

1. **纯 JSON 结构**：不使用 HTML 字符串，前后端均通过 JSON 解析渲染
2. **行内标记优先**：大部分场景通过行内标记数组（`marks`）实现，结构扁平、易解析
3. **块级扩展**：文章中的表格等复杂元素通过独立的块级节点（`type: "table"`）表示
4. **向后兼容**：纯文本可直接表示为字符串，无需包裹在 JSON 结构中；解析时可兼容两种格式

### JSON Schema 定义

#### 1. 行内文本节点（InlineTextNode）

用于题干、选项、解析等字段的富文本表示。

```typescript
// 行内文本片段
interface InlineTextNode {
  type: "text";           // 节点类型：固定为 "text"
  content: string;        // 文本内容
  marks?: Mark[];         // 文本标记（可选，默认无标记）
}

// 标记类型
type Mark =
  | { type: "bold" }                                    // 加粗
  | { type: "underline" }                               // 下划线
  | { type: "highlight", color?: string }               // 高亮（可指定颜色，默认黄色）
  | { type: "ruby", reading: string }                   // 注音（假名注音）
  | { type: "blank", answer?: string }                  // 挖空（用于完形填空展示）
  | { type: "strikethrough" }                           // 删除线
  ;
```

**示例**：

```json
// 题干：标记词带下划线
[
  { "type": "text", "content": "もう少しアイディアを" },
  { "type": "text", "content": "練って", "marks": [{ "type": "underline" }] },
  { "type": "text", "content": "からお話しします。" }
]

// 带假名注音的词汇题
[
  { "type": "text", "content": "契約", "marks": [{ "type": "ruby", "reading": "けいやく" }] },
  { "type": "text", "content": "の内容については、こちらの書類をご覧ください。" }
]

// 完形填空中的挖空展示
[
  { "type": "text", "content": "昨日、友人と" },
  { "type": "text", "content": "　　　", "marks": [{ "type": "blank" }] },
  { "type": "text", "content": "に行った。" }
]
```

#### 2. 块级文档节点（BlockNode）

用于文章（article）字段，支持混合文本段落与表格。

```typescript
// 文档由多个块级节点组成
type BlockNode = TextBlockNode | TableNode;

// 文本块节点（段落）
interface TextBlockNode {
  type: "paragraph";
  content: InlineTextNode[];   // 段落内的行内文本节点
}

// 表格节点
interface TableNode {
  type: "table";
  header?: TableRow;            // 表头（可选）
  rows: TableRow[];             // 表格数据行
}

// 表格行
type TableRow = InlineTextNode[][];  // 每个单元格为一组行内文本节点
```

**示例**：

```json
// 文章示例（包含段落 + 表格）
[
  {
    "type": "paragraph",
    "content": [
      { "type": "text", "content": "以下は" },
      { "type": "text", "content": "日本の祝日", "marks": [{ "type": "bold" }] },
      { "type": "text", "content": "の一覧である。" }
    ]
  },
  {
    "type": "table",
    "header": [
      [{ "type": "text", "content": "日付", "marks": [{ "type": "bold" }] }],
      [{ "type": "text", "content": "祝日名", "marks": [{ "type": "bold" }] }],
      [{ "type": "text", "content": "説明", "marks": [{ "type": "bold" }] }]
    ],
    "rows": [
      [
        [{ "type": "text", "content": "1月1日" }],
        [{ "type": "text", "content": "元日" }],
        [{ "type": "text", "content": "年の初めを祝う日" }]
      ],
      [
        [{ "type": "text", "content": "1月第2月曜日" }],
        [{ "type": "text", "content": "成人の日" }],
        [{ "type": "text", "content": "大人になったことを自覚し、励みとする日" }]
      ]
    ]
  },
  {
    "type": "paragraph",
    "content": [
      { "type": "text", "content": "上記のように、" },
      { "type": "text", "content": "成人の日", "marks": [{ "type": "underline" }] },
      { "type": "text", "content": "は1月に移動した。" }
    ]
  }
]
```

### 各字段富文本支持

| 字段 | 所属表 | 富文本格式 | 说明 |
|------|--------|-----------|------|
| `article` | question_groups | `BlockNode[]` | 文章内容，支持段落 + 表格 |
| `content` | questions | `InlineTextNode[]` | 题干，支持下划线、加粗、高亮等 |
| `content` | options | `InlineTextNode[]` | 选项内容，支持加粗、注音等 |
| `analysis` | questions | `InlineTextNode[]` | 解析文本，支持加粗关键词等 |

### 数据库存储变更

将原 `TEXT` 字段改为 `JSON` 类型以存储富文本结构：

```sql
-- question_groups 表
ALTER TABLE question_groups
    MODIFY COLUMN article JSON DEFAULT NULL COMMENT '文章内容（富文本JSON，BlockNode[]格式）';

-- questions 表
ALTER TABLE questions
    MODIFY COLUMN content JSON DEFAULT NULL COMMENT '题干内容（富文本JSON，InlineTextNode[]格式）',
    MODIFY COLUMN analysis JSON DEFAULT NULL COMMENT '解析文本（富文本JSON，InlineTextNode[]格式）';

-- options 表
ALTER TABLE options
    MODIFY COLUMN content JSON DEFAULT NULL COMMENT '选项内容（富文本JSON，InlineTextNode[]格式）';
```

### 向后兼容策略

为保证已有纯文本数据的兼容性，读写时采用以下策略：

1. **写入时**：如果内容不含任何富文本标记，可直接存储纯字符串（JSON 标量）
2. **读取时**：解析层统一判断 —— 若为字符串则自动包裹为单节点数组，若为数组则直接使用
3. **迁移时**：已有数据无需立即转换，在后续编辑时逐步升级为富文本格式

```python
# 伪代码示例：向后兼容解析
def parse_rich_text(raw) -> list[InlineTextNode]:
    if isinstance(raw, str):
        return [{"type": "text", "content": raw}]
    return raw  # 已经是 InlineTextNode[]
```

### 前端渲染建议

前端可根据节点类型进行组件映射：

| 节点/标记 | 渲染方式 |
|-----------|---------|
| `InlineTextNode` (无 marks) | 普通 `<span>` |
| `mark: bold` | `<strong>` 或 `font-weight: bold` |
| `mark: underline` | `<u>` 或 `border-bottom` |
| `mark: highlight` | `<mark>` 或 `background-color` |
| `mark: ruby` | `<ruby><rb>content</rb><rp>(</rp><rt>reading</rt><rp>)</rp></ruby>` |
| `mark: blank` | 下划线空格或输入框占位符 |
| `mark: strikethrough` | `<s>` 或 `text-decoration: line-through` |
| `BlockNode: paragraph` | `<p>` 段落 |
| `BlockNode: table` | `<table>` 表格组件 |

---

## API 设计

后端基于 FastAPI 构建，提供 RESTful API。

### 基础路径

```
Base URL: /api/v1
```

### 题库管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/questions` | 题目列表（支持分页、筛选） |
| GET | `/questions/{group_id}` | 获取完整题组（含所有子题和选项） |
| POST | `/questions` | 创建题组 |
| PUT | `/questions/{group_id}` | 更新题组 |
| DELETE | `/questions/{group_id}` | 删除题组 |

#### GET /questions 查询参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `type` | string | 题型筛选：`single_choice` / `cloze` / `reading` |
| `level` | string | 级别筛选：`N1` ~ `N5` |
| `difficulty_min` | int | 最低难度 |
| `difficulty_max` | int | 最高难度 |
| `knowledge_point` | string | 知识点关键词 |
| `page` | int | 页码（默认 1） |
| `page_size` | int | 每页数量（默认 20） |

#### GET /questions/{group_id} 响应示例

```json
{
  "id": 1,
  "type": "single_choice",
  "article": null,
  "level": "N1",
  "exam_date": "2010-12",
  "difficulty": 4,
  "knowledge_points": ["动词读音", "訓読み"],
  "questions": [
    {
      "seq": 1,
      "content": [
        { "type": "text", "content": "もう少しアイディアを" },
        { "type": "text", "content": "練って", "marks": [{ "type": "underline" }] },
        { "type": "text", "content": "からお話しします。" }
      ],
      "marked": "練って",
      "answer": "d",
      "analysis": "【答案解析】正确答案是d。",
      "options": [
        { "label": "a", "content": [{ "type": "text", "content": "はずって" }] },
        { "label": "b", "content": [{ "type": "text", "content": "つのって" }] },
        { "label": "c", "content": [{ "type": "text", "content": "ほって" }] },
        { "label": "d", "content": [{ "type": "text", "content": "ねって" }] }
      ]
    }
  ]
}
```

### 考试与做题

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/exams/generate` | 智能组卷（按级别、题型、难度自动生成试卷） |
| GET | `/exams/{exam_id}` | 获取试卷内容 |
| POST | `/exams/{exam_id}/submit` | 提交答案并判分 |
| GET | `/exams/{exam_id}/result` | 获取考试结果与解析 |

#### POST /exams/generate 请求示例

```json
{
  "level": "N1",
  "types": ["single_choice", "cloze", "reading"],
  "total_questions": 30,
  "difficulty_range": [3, 7],
  "time_limit_minutes": 60
}
```

### 学习与分析

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stats/weak-points` | 获取用户薄弱知识点统计 |
| GET | `/stats/history` | 获取做题历史记录 |
| POST | `/review/wrong-questions` | 获取错题集（支持按知识点分组） |

### Agent 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/agent/chat` | 与 Agent 对话（问答、讲解、做题） |
| WebSocket | `/agent/ws` | Agent 实时对话（流式输出） |

#### POST /agent/chat 请求示例

```json
{
  "message": "请帮我讲解一下「ば」和「たら」的区别",
  "session_id": "optional-session-id",
  "context": {
    "current_question_id": 42
  }
}
```

---

## Agent 设计

### 整体架构

基于 LangGraph 构建有状态的多轮对话 Agent，通过工具调用实现各项功能。

```
                         ┌──────────────┐
                         │  用户输入     │
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │  Agent Router │  ← LLM 意图识别
                         └──────┬───────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                  │
      ┌───────▼──────┐  ┌──────▼───────┐  ┌──────▼───────┐
      │  做题模式     │  │  讲解模式     │  │  分析模式     │
      │  ExamTool    │  │  TeachTool   │  │  AnalysisTool│
      └───────┬──────┘  └──────┬───────┘  └──────┬───────┘
              │                │                  │
      ┌───────▼──────────────────────────────────▼───────┐
      │                  MySQL 题库                       │
      └──────────────────────────────────────────────────┘
```

### Agent Tools（工具集）

| 工具名 | 功能 | 输入 | 输出 |
|--------|------|------|------|
| `QuestionFetcher` | 从题库获取题目 | 级别、题型、难度范围 | 题目数据 |
| `ExamGenerator` | 智能组卷 | 考试配置参数 | 完整试卷 |
| `AnswerJudger` | 判断答案正误 | 用户答案、正确答案 | 正误结果 + 解析 |
| `GrammarExplainer` | 语法知识点讲解 | 语法点名称或题目上下文 | 详细讲解 |
| `WeakPointAnalyzer` | 薄弱项分析 | 用户做题历史 | 薄弱知识点报告 |
| `QuestionRecommender` | 题目推荐 | 用户薄弱点 | 针对性练习题 |

### Agent State（状态管理）

Agent 使用 LangGraph 的状态图管理对话状态：

```python
class AgentState(TypedDict):
    messages: list[BaseMessage]       # 对话历史
    current_mode: str                 # 当前模式: exam / teach / analysis / chat
    exam_session: dict | None         # 当前考试会话
    user_answers: list[dict]          # 用户本次作答记录
    weak_points: list[str]            # 识别出的薄弱知识点
```

### 对话流程示例

```
用户: 帮我出一套 N1 的模拟题，20道选择题
Agent: [调用 ExamGenerator] 好的，已为您生成一套 N1 模拟试卷，包含20道选择题...
       第1题：もう少しアイディアを___からお話しします。
       A. はずって  B. つのって  C. ほって  D. ねって

用户: D
Agent: [调用 AnswerJudger] 正确！「練る」读作「ねる」，意为推敲、锤炼。
       第2题：...

用户: 这道题为什么不能选 A？
Agent: [调用 GrammarExplainer] 选项 A「はずって」...（详细讲解）

用户: 我做完了，帮我分析一下
Agent: [调用 WeakPointAnalyzer] 本次测试结果：正确率 75%（15/20）
       薄弱知识点：动词读音（错 3 题）、条件表达（错 2 题）
       建议重点复习：訓読み 规则、ば/たら/なら 的区别
```

### Prompt 设计原则

1. **System Prompt**：设定 Agent 为 JLPT 考试辅导专家身份，熟悉 N1~N5 各级别考纲
2. **Few-shot 示例**：内置日语语法讲解的标准格式示例
3. **工具描述**：每个工具附带清晰的功能描述，帮助 LLM 准确选择工具
4. **输出约束**：题目展示时使用统一格式，解析遵循「答案解析 + 错项分析」结构

---

## 部署说明

### 环境要求

- Python >= 3.14
- MySQL >= 8.0
- uv（Python 包管理器）

### 安装步骤

#### 1. 克隆项目

```bash
git clone <repo-url>
cd JapanesePassAgent
```

#### 2. 安装依赖

```bash
# 安装 uv（如尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装项目依赖
uv sync
```

#### 3. 配置 MySQL

创建数据库：

```sql
CREATE DATABASE jlpt DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

执行建表 SQL（参考上方[数据库设计](#数据库设计)中的三张表 DDL）：

```bash
mysql -u root -p jlpt < crawler/db/schema.sql
```

> 也可跳过此步——`write_to_mysql` 首次运行时会自动执行 `schema.sql` 建表。

#### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
# 数据库配置
DB_HOST=localhost
DB_PORT=3307
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=jlpt

# LLM API 配置
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions

# 服务配置
API_HOST=0.0.0.0
API_PORT=8000
```

> **安全提示**：请勿将 `.env` 文件提交到版本控制。确保 `.gitignore` 中包含 `.env`。

#### 5. 数据采集（可选）

```bash
# 运行爬虫采集题目
uv run python -m crawler.spiders.test_type_1

# LLM 校验与增强
uv run python -m crawler.llm.validate --type type_1 --input data/raw/result_69.json --output data/raw/result_69_validated.json

# 写入 MySQL
uv run python -m crawler.spiders.write_to_mysql
```

#### 6. 启动服务

```bash
# 启动后端 API
uv run uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker 部署（规划中）

```yaml
# docker-compose.yml
version: '3.8'
services:
  db:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
      MYSQL_DATABASE: jlpt
    ports:
      - "3307:3306"
    volumes:
      - mysql_data:/var/lib/mysql

  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      - db
    env_file:
      - .env

volumes:
  mysql_data:
```

---

## License

MIT
