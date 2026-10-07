import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir: './tests/ui',
  fullyParallel: true,
  // Software WebGL compilation can monopolize shared CI CPUs.
  workers: 1,
  reporter: [['list'], ['json', {outputFile: 'docs/validation/ui-tests.json'}]],
  use: {baseURL: 'http://127.0.0.1:8000', browserName: 'chromium', reducedMotion: 'reduce', trace: 'retain-on-failure'},
  webServer: {
    command: process.platform === 'win32' ? '.venv\\Scripts\\python.exe -m uvicorn tindabot.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log' : '.venv/bin/python -m uvicorn tindabot.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log',
    url: 'http://127.0.0.1:8000/healthz',
    reuseExistingServer: !process.env.CI,
  },
});
