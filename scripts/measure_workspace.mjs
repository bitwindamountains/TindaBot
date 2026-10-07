// Synthetic local baseline only. This does not certify physical-device performance.
import {chromium} from '@playwright/test';
import {writeFileSync} from 'node:fs';

const browser = await chromium.launch();
try {
  const page = await browser.newPage({viewport: {width: 390, height: 844}});
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setCPUThrottlingRate', {rate: 4});
  await page.addInitScript(() => {
    window.longTasks = [];
    new PerformanceObserver(list => {
      window.longTasks.push(...list.getEntries().map(e => ({start_ms: e.startTime, duration_ms: e.duration})));
    }).observe({type: 'longtask', buffered: true});
  });
  await page.goto('http://127.0.0.1:8000/', {waitUntil: 'networkidle'});
  await page.getByRole('heading', {name: 'A good day to grow.'}).waitFor();
  const load = await page.evaluate(() => ({
    dom_content_loaded_ms: performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd,
    transferred_bytes: performance.getEntriesByType('resource').reduce((n, e) => n + e.transferSize, 0),
    long_tasks: window.longTasks,
    horizontal_overflow: document.documentElement.scrollWidth > innerWidth,
  }));
  const start = performance.now();
  await page.getByRole('button', {name: 'Inventory', exact: true}).click();
  await page.getByRole('heading', {name: 'Good things in stock.'}).waitFor();
  const report = {
    scope: 'One localhost Chromium sample, 390x844 viewport, 4x CPU slowdown; includes test-runner latency; not a physical mobile or network test',
    ...load, inventory_interaction_ms: performance.now() - start,
  };
  writeFileSync('docs/validation/workspace-performance.json', JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report));
} finally { await browser.close(); }
