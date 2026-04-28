import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const IDEA_LAB_API_URL = 'http://ec2-13-211-172-12.ap-southeast-2.compute.amazonaws.com:7860/api'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: IDEA_LAB_API_URL.replace(/\/api\/?$/, ''),
        changeOrigin: true,
      },
    },
  },
})
