import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  base: '/static/',
  build: {
    manifest: true,
    outDir: resolve(__dirname, '../static/dist'),
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'src/main.tsx'),
      },
    },
  },
  server: {
    port: 5173,
    cors: true,
  },
})
