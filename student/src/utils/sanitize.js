/**
 * v-html 消毒。所有 v-html 的内容都必须先过这里。
 *
 * 为什么需要：marked 默认不过滤 HTML，题目文章 / LLM 输出里的 <script>、
 * <img onerror=...> 会原样进 DOM。而 token 存在 localStorage（有效期 7 天），
 * 一次 XSS 就等于拿到长效凭证。
 *
 * 两个入口，白名单严格程度不同：
 * - sanitizeMd()      给 marked 输出用（AI 回复、解析），允许常见 Markdown 标签
 * - sanitizeArticle() 给题目文章用，额外允许 <table> 系列（info_search 题型的
 *                     原始 HTML 表格），但仍禁掉事件属性和 javascript: 链接
 */
import DOMPurify from 'dompurify'

// Markdown 渲染结果需要的标签
const MD_TAGS = [
  'p', 'br', 'hr', 'span', 'div',
  'strong', 'b', 'em', 'i', 'u', 's', 'del', 'mark', 'small', 'sub', 'sup',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li', 'dl', 'dt', 'dd',
  'blockquote', 'pre', 'code',
  'a',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col',
]

// class 要保留：题干渲染依赖 .marked-word / .cloze-blank / .info-box 等样式钩子
const MD_ATTRS = ['class', 'href', 'title', 'target', 'rel', 'colspan', 'rowspan', 'align', 'start']

/** marked 输出消毒（AI 回复、AI 解析）。 */
export function sanitizeMd(html) {
  if (html == null) return ''
  return DOMPurify.sanitize(String(html), {
    ALLOWED_TAGS: MD_TAGS,
    ALLOWED_ATTR: MD_ATTRS,
    // 禁掉 data:/javascript: 之类的协议，只放行安全链接
    ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
    // 不允许任何 on* 事件属性（DOMPurify 默认就会拦，这里显式表达意图）
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick'],
  })
}

/**
 * 题目文章消毒。
 *
 * renderArticle() 已经把纯文本转义过，但它会刻意放行 DB 里存的 <table>
 * 原始 HTML（info_search 题型），那部分未经任何过滤——所以最终结果仍要过这里。
 */
export function sanitizeArticle(html) {
  if (html == null) return ''
  return DOMPurify.sanitize(String(html), {
    ALLOWED_TAGS: MD_TAGS,
    ALLOWED_ATTR: MD_ATTRS,
    ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick'],
  })
}

/**
 * 题干消毒。
 *
 * renderContent() 自己做了完整转义再插入固定标签，本身是安全的；
 * 这里作为纵深防御兜一层，成本可忽略。
 */
export function sanitizeContent(html) {
  if (html == null) return ''
  return DOMPurify.sanitize(String(html), {
    ALLOWED_TAGS: ['span', 'u', 'br', 'i', 'div', 'b', 'strong', 'em'],
    ALLOWED_ATTR: ['class'],
  })
}
