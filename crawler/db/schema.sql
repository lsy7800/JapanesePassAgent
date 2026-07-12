-- JLPT 题库三表结构
-- 对应 README「数据库设计」章节：question_groups 1─N questions 1─N options
-- 单选题视为「只含一道子题」的题组，以统一支持完形填空/阅读理解等多子题题型。

CREATE TABLE IF NOT EXISTS question_groups (
    id               INT PRIMARY KEY AUTO_INCREMENT,
    type             ENUM('single_choice', 'cloze', 'reading') NOT NULL COMMENT '题型：单选/完形填空/阅读理解',
    article          TEXT DEFAULT NULL COMMENT '文章内容（完形填空和阅读理解使用，单选题为NULL）',
    level            VARCHAR(10) DEFAULT '' COMMENT '考试级别：N1/N2/N3/N4/N5',
    exam_date        VARCHAR(20) DEFAULT '' COMMENT '考试日期，如 2023-07',
    difficulty       TINYINT DEFAULT 0 COMMENT '难度评级（1-9）',
    knowledge_points JSON DEFAULT NULL COMMENT '知识点标签数组',
    source           VARCHAR(100) DEFAULT '' COMMENT '数据来源标识',
    source_ref       VARCHAR(100) DEFAULT '' COMMENT '来源内唯一标识（如 result_67#1），用于幂等去重',
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
