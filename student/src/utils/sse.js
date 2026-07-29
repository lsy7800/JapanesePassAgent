/**
 * SSE 连接封装：统一事件分发、错误区分与关闭语义。
 *
 * 为什么不直接用 EventSource：
 * 1. 原生 onerror 不区分「网络断」与「服务端返回了错误」，一律只能提示"连接中断"。
 *    这里用「是否已收到过 done/error 事件」判断流是否正常收尾——正常收尾后触发的
 *    onerror 是 EventSource 重连机制的副作用，应当忽略，不该弹错误。
 * 2. 主动 close() 不会触发任何回调，调用方容易漏掉收尾逻辑（loading 卡死）。
 *    这里让返回的 close() 保证调一次 onClose，把状态复位的责任收回到一处。
 */

/**
 * @param {string} url  SSE 地址（含 query 参数）
 * @param {object} handlers  事件处理器
 *   - onEvent(payload)  收到任意事件（已 JSON.parse）
 *   - onError(detail, kind)  出错。kind: 'server' 服务端推的错误 | 'network' 连接中断
 *   - onClose(reason)  流结束（'done' 正常 | 'error' 出错 | 'abort' 主动取消）
 * @returns {function} close — 主动关闭；已结束时为空操作
 */
export function openSSE(url, { onEvent, onError, onClose } = {}) {
  const es = new EventSource(url)
  // 流是否已收尾：防止 close() 之后 EventSource 自动重连触发的 onerror 误报
  let settled = false

  function finish(reason) {
    if (settled) return
    settled = true
    es.close()
    onClose?.(reason)
  }

  es.onmessage = (e) => {
    let payload
    try {
      payload = JSON.parse(e.data)
    } catch {
      return // 忽略无法解析的帧，不影响后续事件
    }
    if (payload.type === 'error') {
      onError?.(payload.detail || '处理失败', 'server', payload)
      finish('error')
      return
    }
    onEvent?.(payload)
    if (payload.type === 'done') finish('done')
  }

  es.onerror = () => {
    // 正常收尾后的 onerror 是重连副作用，忽略
    if (settled) return
    onError?.('网络连接中断，请检查网络后重试', 'network')
    finish('error')
  }

  return () => finish('abort')
}
