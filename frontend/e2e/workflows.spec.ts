import { test, expect, type Page } from '@playwright/test';

async function login(page: Page, role = 'admin') {
  await page.goto('/login');
  await page.getByLabel('Email address').fill(`${role}@logsentinel.example.com`);
  await page.getByLabel('Password', { exact: true }).fill('Sentinel-Demo-2026!');
  await page.getByRole('button', { name: 'Sign in to workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Security overview' })).toBeVisible();
}

test('dashboard supports both themes, responsive navigation and all main routes', async ({
  page,
}) => {
  // Thirteen full route visits, theme persistence and a second viewport share this test.
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await login(page);
  await expect(page.getByText('Total events', { exact: true })).toBeVisible();
  await page.screenshot({ path: '../artifacts/dashboard-dark.png', fullPage: true });
  await page.getByRole('button', { name: 'Switch to light mode' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.screenshot({ path: '../artifacts/dashboard-light.png', fullPage: true });
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  for (const [path, heading] of [
    ['/events', 'Events explorer'],
    ['/alerts', 'Alert inbox'],
    ['/investigations', 'Investigations'],
    ['/sources', 'Log sources'],
    ['/parsers', 'Parser lab'],
    ['/rules', 'Detection rules'],
    ['/analytics', 'Security analytics'],
    ['/reports', 'Reports & exports'],
    ['/notifications', 'Notifications'],
    ['/profile', 'Your profile'],
    ['/security', 'Security settings'],
    ['/audit', 'Audit trail'],
    ['/settings', 'Administration'],
  ]) {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    await expect(page.getByRole('alert').filter({ hasText: 'We couldn’t load' })).toHaveCount(0);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Events explorer' })).toBeVisible();
  await page.getByRole('link', { name: 'Events explorer' }).click();
  await expect(page.getByRole('heading', { name: 'Events explorer' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: '../artifacts/explorer-mobile.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('administrator creates workspace, source, imports logs and completes an investigation', async ({
  page,
}) => {
  await login(page);
  await page.goto('/settings');
  await page.getByRole('button', { name: 'New workspace' }).click();
  await page.getByLabel('Workspace name', { exact: true }).fill('Browser verification');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await page.getByLabel('Current workspace').selectOption({ label: 'Browser verification' });
  await page.goto('/sources/new');
  await page.getByLabel('Source name', { exact: true }).fill('Browser auth source');
  await page.getByLabel('Source type').selectOption('linux_auth');
  await page.getByRole('combobox', { name: 'Parser', exact: true }).selectOption('json');
  await page.getByRole('button', { name: 'Connect source', exact: true }).click();
  await page.getByRole('button', { name: 'Import logs', exact: true }).click();
  const events = Array.from({ length: 8 }, (_, index) =>
    JSON.stringify({
      timestamp: new Date(Date.now() - index * 1000).toISOString(),
      message: 'Browser sample password=never-export-this',
      event_type: 'login_failed',
      category: 'authentication',
      ip: '192.0.2.88',
      username: 'synthetic-account',
    }),
  ).join('\n');
  await page
    .getByLabel('Log file', { exact: true })
    .setInputFiles({ name: 'browser.jsonl', mimeType: 'text/plain', buffer: Buffer.from(events) });
  await page.getByRole('button', { name: 'Preview & validate', exact: true }).click();
  await expect(page.getByText('Redacted preview · no events imported')).toBeVisible();
  await page.getByRole('button', { name: 'Import log file', exact: true }).click();
  await expect(page.getByText('completed', { exact: true }).first()).toBeVisible({
    timeout: 20000,
  });
  await page.goto('/events');
  await expect(page.getByText('8 matching events')).toBeVisible();
  await expect(page.locator('main')).not.toContainText('never-export-this');
  await page.goto('/alerts');
  await page.getByRole('link', { name: 'Failed login burst', exact: true }).first().click();
  await expect(page.getByRole('heading', { name: 'Why this was flagged' })).toBeVisible();
  await page
    .getByLabel('Your investigation note')
    .fill('Verified synthetic test activity. No response action required.');
  await page.getByRole('button', { name: 'Add note', exact: true }).click();
  await expect(
    page.getByText('Verified synthetic test activity. No response action required.'),
  ).toBeVisible();
  await page.getByRole('combobox', { name: 'Status', exact: true }).selectOption('RESOLVED');
  await page.getByLabel('Resolution reason').fill('Authorized browser verification');
  await page.getByRole('button', { name: 'Update investigation' }).click();
  await expect(page.getByText('RESOLVED', { exact: true }).first()).toBeVisible();
  await page.goto('/reports');
  await page.getByRole('button', { name: 'Create report', exact: true }).first().click();
  await page.getByLabel('Report title').fill('Browser report');
  await page.getByRole('button', { name: 'Generate report' }).click();
  const downloadButton = page.getByRole('button', { name: 'Download', exact: true }).first();
  await expect(downloadButton).toBeEnabled({ timeout: 20000 });
  const downloadPromise = page.waitForEvent('download');
  await downloadButton.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain('.json');
});

test('viewer can read evidence and cannot mutate sources, rules or reports', async ({ page }) => {
  await login(page, 'viewer');
  await page.goto('/sources');
  await expect(page.getByRole('button', { name: 'Import logs' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Add log source' })).toHaveCount(0);
  await page.goto('/rules');
  await expect(page.getByRole('link', { name: 'Create rule' })).toHaveCount(0);
  await page.goto('/settings');
  await expect(page.getByRole('alert')).toContainText('administrators');
});

test('parser lab validates malformed lines and redacts secret samples', async ({ page }) => {
  await login(page, 'analyst');
  await page.goto('/parsers');
  await page.getByRole('button', { name: 'Load synthetic sample' }).click();
  await page.getByRole('button', { name: 'Test parser' }).click();
  await expect(page.locator('pre')).toContainText('[REDACTED]');
  await expect(page.locator('pre')).not.toContainText('secret-example');
  await page.getByLabel('Log sample').fill('{malformed-json');
  await page.getByRole('button', { name: 'Test parser' }).click();
  await expect(page.locator('pre')).toContainText('"parsed": false');
});

test('public privacy, terms and recovery routes work without authentication', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Clarity in every log');
  await page.getByRole('link', { name: 'Privacy notice' }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Your logs. Your control.');
  await page.goto('/terms');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Responsible use, by design.');
  await page.goto('/forgot-password');
  await page.getByLabel('Email address').fill('unknown@example.com');
  await page.getByRole('button', { name: 'Send recovery link' }).click();
  await expect(page.getByRole('status')).toContainText('If the account exists');
});
