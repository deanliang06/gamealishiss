import { defineConfig } from '@playwright/test';
import path from 'node:path';
const root = path.resolve(import.meta.dirname, '..');
const python = process.env.TEST_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
export default defineConfig({
  testDir: './e2e', timeout: 60000, fullyParallel: false, workers: 1,
  reporter: [['list']],
  use: { baseURL: 'http://localhost:5173', channel: process.platform === 'win32' ? 'chrome' : undefined, headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: [
    { command: `"${python}" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1`, cwd: root, url: 'http://127.0.0.1:8000/api/health', env: { GAME_PROVIDER: 'demo', ALLOWED_ORIGINS: 'http://localhost:5173,http://localhost:8000' }, reuseExistingServer: false },
    { command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173', url: 'http://localhost:5173', reuseExistingServer: false },
  ],
});
