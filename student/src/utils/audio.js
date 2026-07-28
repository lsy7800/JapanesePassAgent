// 听力音频 URL 拼接：数据库只存相对路径（如 mp3/n1/tiku79/n1tiku79-01.mp3），
// 播放时拼上可配置的 base 前缀。上线迁移到对象存储时只改 .env 的 VITE_AUDIO_BASE_URL。
const AUDIO_BASE = (import.meta.env.VITE_AUDIO_BASE_URL || '').replace(/\/+$/, '')

export function audioUrl(relPath) {
  if (!relPath) return ''
  // 已是完整 URL 则原样返回（兼容将来直接存全链接的情况）
  if (/^https?:\/\//i.test(relPath)) return relPath
  const rel = String(relPath).replace(/^\/+/, '')
  return AUDIO_BASE ? `${AUDIO_BASE}/${rel}` : `/${rel}`
}
