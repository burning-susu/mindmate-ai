import { expect, test } from '@playwright/test'

test('stage 4 file lifecycle works through the browser', async ({ page }) => {
  await page.goto('/files')
  await expect(page.getByRole('heading', { name: '文件' })).toBeVisible()

  await page.getByLabel('新文件夹名称').fill('浏览器审计')
  await page.getByRole('button', { name: '创建文件夹' }).click()
  const folder = page.locator('.folder-row', { hasText: '浏览器审计' })
  await expect(folder).toBeVisible()
  await folder.click()

  await page.locator('input[type=file]').setInputFiles({
    name: 'browser-check.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('MindMate browser stage 4 check', 'utf-8'),
  })
  const fileLink = page.getByRole('link', { name: /browser-check\.txt/ })
  await expect(fileLink).toBeVisible()
  await fileLink.click()
  await expect(page.getByText('MindMate browser stage 4 check')).toBeVisible()

  await page.getByRole('link', { name: '返回文件' }).click()
  const fileRow = page.getByRole('link', { name: /browser-check\.txt/ })
  await page.getByRole('button', { name: '移入回收站 browser-check.txt' }).click()
  await expect(fileRow).not.toBeVisible()
  await page.getByRole('link', { name: '回收站' }).click()
  await expect(page.getByText('browser-check.txt')).toBeVisible()
  await page.getByRole('button', { name: '恢复', exact: true }).click()
  await expect(page.getByText('browser-check.txt')).not.toBeVisible()
})
