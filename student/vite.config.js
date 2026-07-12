import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    proxy: {
      // SSE 流式端点：禁用响应缓冲，确保 token 逐块推送到浏览器
      '/api/v1/agent/stream': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: false,
        configure(proxy) {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['x-accel-buffering'] = 'no'
          })
        },
      },
      // 其余 API
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
