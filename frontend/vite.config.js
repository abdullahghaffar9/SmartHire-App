/**
 * vite.config.js - Vite Build & Dev Server Configuration
 *
 * Configures Vite for both local development (hot-reload on port 5173)
 * and optimized production builds with manual vendor chunk splitting.
 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  // Register the React plugin for JSX transformation and fast refresh
  plugins: [react()],
  server: {
    // Listen on all interfaces so the dev server is reachable in Docker/CI
    host: '0.0.0.0',
    port: 5173,
    // Automatically open the browser on server start
    open: true,
  },
  build: {
    // Production build optimization: target modern JS for smaller output
    target: 'esnext',
    minify: 'terser',
    // Disable sourcemaps in production to avoid leaking source code
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          // Split vendor bundles so browsers can cache them separately
          'react-vendor': ['react', 'react-dom'],
          'animation-vendor': ['framer-motion'],
          'icons-vendor': ['lucide-react'],
        },
      },
    },
  },
  // Only expose env vars prefixed with VITE_ to the client bundle
  envPrefix: 'VITE_',
});
