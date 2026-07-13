-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id              INT PRIMARY KEY AUTO_INCREMENT,
    email           VARCHAR(255) NOT NULL COMMENT '邮箱（登录账号）',
    hashed_password VARCHAR(255) NOT NULL COMMENT 'bcrypt 哈希密码',
    role            ENUM('student', 'admin') NOT NULL DEFAULT 'student',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否启用；停用后禁止登录',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- JLPT 题库三表结构
-- 对应 README「数据库设计」章节：question_groups 1─N questions 1─N options
-- 单选题视为「只含一道子题」的题组，以统一支持完形填空/阅读理解等多子题题型。

CREATE TABLE IF NOT EXISTS question_groups (
    id               INT PRIMARY KEY AUTO_INCREMENT,
    type             ENUM('single_choice', 'cloze', 'reading') NOT NULL COMMENT '题型：单选/完形填空/阅读理解',
    category         VARCHAR(30) DEFAULT NULL COMMENT 'JLPT 题型 code（见 backend/config/categories.py），如 kanji_reading/context',
    article          TEXT DEFAULT NULL COMMENT '文章内容（完形填空和阅读理解使用，单选题为NULL）',
    level            VARCHAR(10) DEFAULT '' COMMENT '考试级别：N1/N2/N3/N4/N5',
    exam_date        VARCHAR(20) DEFAULT '' COMMENT '考试日期，如 2023-07',
    difficulty       TINYINT DEFAULT 0 COMMENT '难度评级（1-9）',
    knowledge_points JSON DEFAULT NULL COMMENT '知识点标签数组',
    source           VARCHAR(100) DEFAULT NULL COMMENT '数据来源标识',
    source_ref       VARCHAR(100) DEFAULT NULL COMMENT '来源内唯一标识（如 result_67#1），用于幂等去重；API 手动创建时为 NULL',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_source_ref (source_ref)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='题组表';

CREATE TABLE IF NOT EXISTS questions (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    group_id    INT NOT NULL COMMENT '关联的题组ID',
    seq         INT NOT NULL DEFAULT 1 COMMENT '在题组内的顺序号（单选题固定为1）',
    content     TEXT DEFAULT NULL COMMENT '题干内容（完形填空此字段为空，阅读理解有具体问题）',
    marked      VARCHAR(255) DEFAULT '' COMMENT '划线词/标记词',
    answer      VARCHAR(10) NOT NULL DEFAULT '' COMMENT '正确答案：a/b/c/d',
    analysis    TEXT DEFAULT NULL COMMENT '解析文本',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_group_id (group_id),
    FOREIGN KEY (group_id) REFERENCES question_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='子题表';

CREATE TABLE IF NOT EXISTS options (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    question_id INT NOT NULL COMMENT '关联的子题ID',
    label       CHAR(1) NOT NULL COMMENT '选项标签：a/b/c/d',
    content     VARCHAR(500) NOT NULL DEFAULT '' COMMENT '选项内容',
    INDEX idx_question_id (question_id),
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='选项表';

-- 考试试卷表：一次组卷生成一条记录
CREATE TABLE IF NOT EXISTS exams (
    id           INT PRIMARY KEY AUTO_INCREMENT,
    user_id      INT DEFAULT NULL COMMENT '出题用户ID，NULL 表示匿名/Agent组卷',
    level        VARCHAR(10) DEFAULT '' COMMENT '组卷时的目标级别',
    total        INT NOT NULL DEFAULT 0 COMMENT '试卷题目数',
    time_limit   INT DEFAULT 0 COMMENT '限时（分钟），0 为不限',
    status       ENUM('created', 'submitted') NOT NULL DEFAULT 'created' COMMENT '状态：待作答/已提交',
    score        INT DEFAULT NULL COMMENT '得分（提交后写入，等于答对题数）',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP NULL DEFAULT NULL,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考试试卷表';

-- 试卷题目与作答表：判分以题组为单位（当前均单选题，取题组首道子题答案比对；
-- 多子题题型如完形/阅读后续扩展时需细化到子题级）
CREATE TABLE IF NOT EXISTS exam_items (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    exam_id     INT NOT NULL COMMENT '关联试卷ID',
    seq         INT NOT NULL COMMENT '题目在试卷中的序号',
    group_id    INT NOT NULL COMMENT '关联 question_groups.id',
    user_answer VARCHAR(10) DEFAULT NULL COMMENT '用户作答 a/b/c/d（提交后写入）',
    is_correct  TINYINT DEFAULT NULL COMMENT '是否正确（提交后写入）',
    INDEX idx_exam (exam_id),
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES question_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='试卷题目与作答表';
