/**
 * v-html 消毒的 XSS 回归测试。
 *
 * 背景：token 存在 localStorage 且有效期 7 天，一次 XSS 就等于拿到长效凭证。
 * 注入源有两处真实路径：
 *  - 题库文章/题干（DB 内容，renderArticle 会刻意放行 <table> 原始 HTML）
 *  - LLM 输出（AI 回复、AI 解析），经 marked.parse 后本就不过滤 HTML
 */
import { describe, expect, it } from 'vitest'

import { sanitizeArticle, sanitizeContent, sanitizeMd } from './sanitize'

// 典型 XSS 载荷。每条都必须被消毒掉可执行部分。
const PAYLOADS = [
  '<script>alert(1)</script>',
  '<img src=x onerror="alert(1)">',
  '<svg onload="alert(1)">',
  '<iframe src="javascript:alert(1)"></iframe>',
  '<a href="javascript:alert(1)">click</a>',
  '<body onload="alert(1)">',
  '<div onclick="alert(1)">x</div>',
  '<input onfocus="alert(1)" autofocus>',
  '<object data="javascript:alert(1)"></object>',
  '<embed src="javascript:alert(1)">',
  '<form action="javascript:alert(1)"><button>go</button></form>',
  '<math><mtext><script>alert(1)</script></mtext></math>',
  '<style>body{background:url("javascript:alert(1)")}</style>',
]

/** 断言产物里没有可执行残留。 */
function expectInert(out) {
  const lower = out.toLowerCase()
  expect(lower).not.toContain('<script')
  expect(lower).not.toContain('javascript:')
  expect(lower).not.toContain('onerror')
  expect(lower).not.toContain('onload')
  expect(lower).not.toContain('onclick')
  expect(lower).not.toContain('onfocus')
  expect(lower).not.toContain('<iframe')
  expect(lower).not.toContain('<object')
  expect(lower).not.toContain('<embed')
  expect(lower).not.toContain('<style')
}

describe.each([
  ['sanitizeMd', sanitizeMd],
  ['sanitizeArticle', sanitizeArticle],
  ['sanitizeContent', sanitizeContent],
])('%s 拦截 XSS', (_name, fn) => {
  it.each(PAYLOADS)('消毒 %s', (payload) => {
    expectInert(fn(payload))
  })

  it('处理 null/undefined 不抛错', () => {
    expect(fn(null)).toBe('')
    expect(fn(undefined)).toBe('')
  })
})

describe('sanitizeMd 保留正常 Markdown 渲染结果', () => {
  it('保留基本格式标签', () => {
    const out = sanitizeMd(
      '<p>这是 <strong>加粗</strong> 和 <em>斜体</em></p><ul><li>项目</li></ul>'
    )
    expect(out).toContain('<strong>')
    expect(out).toContain('<em>')
    expect(out).toContain('<li>')
    expect(out).toContain('这是')
  })

  it('保留代码块与表格（AI 讲解语法常用）', () => {
    const out = sanitizeMd('<pre><code>ですます</code></pre><table><tr><td>格</td></tr></table>')
    expect(out).toContain('<code>')
    expect(out).toContain('<td>')
  })

  it('保留 https 链接但去掉 javascript: 链接', () => {
    expect(sanitizeMd('<a href="https://example.com">ok</a>')).toContain('href="https://example.com"')
    const bad = sanitizeMd('<a href="javascript:alert(1)">bad</a>')
    expect(bad).not.toContain('javascript:')
    // 文本内容仍保留，只是链接失效
    expect(bad).toContain('bad')
  })

  it('日文与中文内容不被破坏', () => {
    const out = sanitizeMd('<p>この文章は正しく表示されます。「かっこ」も。</p>')
    expect(out).toContain('この文章は正しく表示されます')
    expect(out).toContain('「かっこ」')
  })
})

describe('sanitizeArticle 保留题目渲染需要的结构', () => {
  it('保留 info_search 题型的表格', () => {
    const out = sanitizeArticle(
      '<table><thead><tr><th>時間</th></tr></thead><tbody><tr><td>9:00</td></tr></tbody></table>'
    )
    expect(out).toContain('<table>')
    expect(out).toContain('<th>')
    expect(out).toContain('9:00')
  })

  it('保留 class 钩子（样式依赖它）', () => {
    const out = sanitizeArticle('<span class="cloze-blank">（1）</span>')
    expect(out).toContain('class="cloze-blank"')
  })

  it('表格里夹带的事件属性会被剥掉，表格本身保留', () => {
    const out = sanitizeArticle('<table><tr><td onclick="alert(1)">x</td></tr></table>')
    expect(out).toContain('<table>')
    expect(out.toLowerCase()).not.toContain('onclick')
  })

  it('下划线与 info-box 标记保留', () => {
    const out = sanitizeArticle(
      '<u class="reading-underline">下線部</u><div class="info-box">枠</div>'
    )
    expect(out).toContain('reading-underline')
    expect(out).toContain('info-box')
  })
})

describe('sanitizeContent 只允许题干需要的极少标签', () => {
  it('保留划线词与排序题槽位', () => {
    const out = sanitizeContent(
      '<u class="marked-word">言葉</u><span class="sort-slot sort-slot--star"><i>★</i></span>'
    )
    expect(out).toContain('marked-word')
    expect(out).toContain('sort-slot')
    expect(out).toContain('★')
  })

  it('剥掉题干里不该出现的标签，但保留文字', () => {
    const out = sanitizeContent('<table><tr><td>不该有表格</td></tr></table>')
    expect(out).not.toContain('<table')
    expect(out).toContain('不该有表格')
  })
})

describe('绕过技巧', () => {
  it('大小写混写的事件属性', () => {
    expectInert(sanitizeArticle('<IMG SRC=x OnErRoR="alert(1)">'))
  })

  it('实体编码的 javascript: 协议', () => {
    const out = sanitizeMd('<a href="&#106;avascript:alert(1)">x</a>')
    expect(out.toLowerCase()).not.toContain('javascript:')
  })

  it('嵌套畸形标签', () => {
    expectInert(sanitizeMd('<<script>script>alert(1)<</script>/script>'))
  })

  it('data: URI 图片不放行（可承载脚本）', () => {
    const out = sanitizeMd('<img src="data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==">')
    expect(out).not.toContain('data:text/html')
  })
})
