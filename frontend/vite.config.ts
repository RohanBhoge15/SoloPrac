import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'robots.txt'],
      manifest: {
        name: 'SoloPrac AI — Clinical Operating System',
        short_name: 'SoloPrac',
        description: 'AI-powered clinical operating system for solo medical practitioners',
        theme_color: '#1e40af',
        background_color: '#0f172a',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/localhost:8000\/api\/v1\/health/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-health',
              expiration: { maxEntries: 1, maxAgeSeconds: 60 },
            },
          },
          {
            urlPattern: /\/api\/v1\/(health|specialities|public)/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 300 },
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // P2.19 — Manual chunks so vendor libs end up in their own long-lived
  // vendor chunks that survive app-code redeploys — great for repeat visitors.
  // Only libs that are actually in package.json belong here; naming a package
  // that isn't installed makes rollup treat it as a missing entry module and
  // aborts the build.
  build: {
    target: 'es2022',
    sourcemap: false,
    cssCodeSplit: true,
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'tanstack': ['@tanstack/react-query'],
          'motion': ['framer-motion'],
          'icons': ['lucide-react'],
        },
      },
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    // Vite 5 rejects requests with a Host header not in this allowlist.
    // In docker the browser (or another container) reaches us as `frontend:5173`;
    // from the host machine it's `localhost` / `127.0.0.1`. `true` disables the check
    // — safe for a dev-only server that is never exposed publicly.
    allowedHosts: true,
    // Windows-host + Linux-container filesystem events don't propagate through
    // Docker Desktop reliably. Poll instead so HMR catches edits without a restart.
    // 300ms is a fine trade-off: barely noticeable CPU, sub-second HMR.
    watch: {
      usePolling: true,
      interval: 300,
    },
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      '/ws': {
        target: process.env.VITE_PROXY_TARGET || 'http://localhost:8000',
        ws: true,
      },
    },
  },
})