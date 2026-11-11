import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
export default defineConfig(({ mode }) => {
  if (!['documente', 'portal'].includes(mode)) throw new Error('Alege modul documente sau portal.');
  return {
    root: `${root}${mode}`,
    envDir: root,
    plugins: [react()],
    build: { outDir: `${root}dist/${mode}`, emptyOutDir: true },
    server: { fs: { allow: [root] }, strictPort: true }
  };
});
