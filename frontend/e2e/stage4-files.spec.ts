import { expect, test } from '@playwright/test'

test('stage 4 file lifecycle works through the browser', async ({ page }) => {
  const suffix = Date.now()
  const folderName = `浏览器审计-${suffix}`
  const fileName = `browser-check-${suffix}.txt`
  await page.goto('/files')
  await expect(page.getByRole('heading', { name: '文件' })).toBeVisible()

  await page.getByLabel('新文件夹名称').fill(folderName)
  await page.getByRole('button', { name: '创建文件夹' }).click()
  const folder = page.locator('.folder-row', { hasText: folderName })
  await expect(folder).toBeVisible()
  await folder.click()

  await page.locator('input[type=file]').setInputFiles({
    name: fileName,
    mimeType: 'text/plain',
    buffer: Buffer.from(`MindMate browser stage 4 check ${suffix}`, 'utf-8'),
  })
  const fileLink = page.getByRole('link', { name: fileName })
  await expect(fileLink).toBeVisible()
  await fileLink.click()
  await expect(page.getByText(`MindMate browser stage 4 check ${suffix}`)).toBeVisible()

  await page.getByRole('link', { name: '返回文件' }).click()
  const fileRow = page.getByRole('link', { name: fileName })
  await page.getByRole('button', { name: `移入回收站 ${fileName}` }).click()
  await expect(fileRow).not.toBeVisible()
  await page.getByRole('link', { name: '回收站' }).first().click()
  const trashRow = page.locator('.trash-row', { hasText: fileName })
  await expect(trashRow).toBeVisible()
  await trashRow.getByRole('button', { name: '恢复', exact: true }).click()
  await expect(trashRow).not.toBeVisible()
})
