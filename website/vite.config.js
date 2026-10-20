import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// base './' so the build works from any folder or sub-path (e.g. GitHub Pages).
export default defineConfig({ plugins: [react(), tailwindcss()], base: './' });
