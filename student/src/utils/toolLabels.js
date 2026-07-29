/**
 * Agent 工具名 → 中文进度文案。
 *
 * 后端在调用工具前会推 type:'tool' 事件，而首个回复 token 要等工具内部的 LLM
 * 跑完才来。这段空白期用这些文案告知用户「正在做什么」，避免只有一个转圈。
 * 直接展示英文工具名对学生用户没有意义，故统一映射。
 */
export const TOOL_LABELS = {
  answer_judge: '正在逐句翻译原文并生成解析…',
  analyze_weak_points: '正在汇总错题、归纳薄弱知识点…',
  fetch_questions: '正在检索题库…',
  generate_exam: '正在组卷…',
  explain_grammar: '正在整理语法讲解…',
  recommend_questions: '正在挑选针对性练习题…',
  export_exam: '正在生成可下载的试卷文件…',
}

export function toolLabel(name) {
  return TOOL_LABELS[name] || '正在处理…'
}
