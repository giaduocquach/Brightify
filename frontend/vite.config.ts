import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Built assets are served by FastAPI from ../static_spa/.
// In dev, /api is proxied to the running FastAPI server on :8000.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: '../static_spa',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
