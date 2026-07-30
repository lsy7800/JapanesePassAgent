/**
 * 高度展开/收起过渡的 <transition> JS 钩子。
 *
 * 为什么需要 JS：折叠内容的高度不固定（答题卡随题数 5~60+，错题详情随选项与解析长短），
 * 纯 CSS 只能用 max-height 猜一个上限，实际高度远小于上限时动画会"提前跑完"，
 * 观感是先快后停。这里在钩子里量出 scrollHeight，做真正的 0 ↔ h 过渡。
 *
 * 用法：
 *   <transition name="foo" @enter="collapseEnter" @leave="collapseLeave">
 *     <div v-if="open" class="foo-collapse">…</div>
 *   </transition>
 * 配套 CSS 需要 overflow:hidden 与 height 的 transition（见各视图的 .*-collapse）。
 */

// transitionend 兜底超时。必须大于 --dur-base(200ms) 才不会截断正常动画。
const FALLBACK_MS = 400

/**
 * 等自身的 height 过渡结束后清掉内联高度并放行 done()。
 *
 * 带超时兜底：done() 没被调用时，离场元素永远留在 DOM 里（不只是动画不好看，
 * 是功能性 bug）。而 transitionend 并非总会到——例如系统开了「减弱动态效果」，
 * 全局 transition-duration 被压到 0.01ms，或元素在动画途中被隐藏。
 */
function afterHeight(el, done) {
  let settled = false

  const finish = () => {
    if (settled) return // transitionend 与超时二者只生效一次
    settled = true
    clearTimeout(timer)
    el.removeEventListener('transitionend', onEnd)
    el.style.height = ''
    done()
  }

  const onEnd = (e) => {
    // 只认自己身上的 height —— 子元素冒泡上来的过渡会提前触发 done()
    if (e.target !== el || e.propertyName !== 'height') return
    finish()
  }

  const timer = setTimeout(finish, FALLBACK_MS)
  el.addEventListener('transitionend', onEnd)
}

export function collapseEnter(el, done) {
  el.style.height = '0px'
  void el.offsetHeight // 强制回流，否则浏览器把 0 → h 合并成一帧，看不到动画
  el.style.height = `${el.scrollHeight}px`
  afterHeight(el, done)
}

export function collapseLeave(el, done) {
  el.style.height = `${el.scrollHeight}px`
  void el.offsetHeight
  el.style.height = '0px'
  afterHeight(el, done)
}
