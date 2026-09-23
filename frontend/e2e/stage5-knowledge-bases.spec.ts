import { expect, test } from '@playwright/test'

test('stage 5 knowledge base membership lifecycle works through the browser', async ({ page }) => {
  const uniqueName = `浏览器知识库-${Date.now()}`
  const fileName = `知识库讲义-${Date.now()}.txt`

  await page.goto('/files')
  await page.locator('input[type="file"]').setInputFiles({
    name: fileName,
    mimeType: 'text/plain',
    buffer: Buffer.from(`MindMate knowledge membership browser evidence: ${fileName}`),
  })
  const fileRow = page.locator('tr', { hasText: fileName })
  await expect(fileRow).toBeVisible()
  await expect(fileRow.getByText('已解析')).toBeVisible({ timeout: 10_000 })

  await page.goto('/knowledge-bases')
  await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible()

  await page.getByRole('link', { name: '新建知识库' }).click()
  await page.getByRole('textbox', { name: '知识库名称' }).fill(uniqueName)
  await page.getByRole('textbox', { name: '知识库描述' }).fill('真实 API 浏览器闭环')
  await page.getByRole('button', { name: '创建知识库' }).click()

  await expect(page.getByRole('heading', { name: uniqueName })).toBeVisible()
  await expect(page.getByText('尚未加入任何文件。')).toBeVisible()
  const fileOption = page.locator('label', { hasText: fileName })
  await fileOption.getByRole('checkbox').check()
  await page.getByRole('button', { name: '加入 1 个' }).click()
  await expect(page.getByText(`${fileName}：成员已加入，索引仍待建立。`)).toBeVisible({ timeout: 10_000 })
  const memberRow = page.locator('.member-row', { hasText: fileName })
  await expect(memberRow.getByText('待建立索引')).toBeVisible()
  await expect(memberRow.getByText('索引待建立')).toBeVisible()

  await page.reload()
  await expect(page.locator('.member-row', { hasText: fileName })).toBeVisible()
  await page.getByRole('textbox', { name: '知识库描述' }).fill('已保存的浏览器说明')
  await page.getByRole('button', { name: '保存更改' }).click()
  await page.reload()
  await expect(page.getByRole('textbox', { name: '知识库描述' })).toHaveValue('已保存的浏览器说明')

  await page.getByRole('button', { name: `移出知识库 ${fileName}` }).click()
  await expect(page.locator('.member-row', { hasText: fileName })).not.toBeVisible()
  await page.goto('/files')
  await expect(page.locator('tr', { hasText: fileName })).toBeVisible()
  await page.goto(`/knowledge-bases`)
  await page.getByText(uniqueName).click()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: '移入回收站' }).click()
  await expect(page).toHaveURL(/\/knowledge-bases$/)
  await expect(page.getByText(uniqueName)).not.toBeVisible()

  await page.getByRole('link', { name: '回收站' }).first().click()
  const trashRow = page.locator('.trash-row', { hasText: uniqueName })
  await expect(trashRow).toBeVisible()
  await trashRow.getByRole('button', { name: '恢复知识库' }).click()
  await expect(trashRow).not.toBeVisible()

  await page.goto('/knowledge-bases')
  await expect(page.getByText(uniqueName)).toBeVisible()
})
