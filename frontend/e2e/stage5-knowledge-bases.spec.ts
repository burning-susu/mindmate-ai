import { expect, test } from '@playwright/test'

test('stage 5 empty knowledge base lifecycle works through the browser', async ({ page }) => {
  const uniqueName = `浏览器知识库-${Date.now()}`
  await page.goto('/knowledge-bases')
  await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible()

  await page.getByRole('link', { name: '新建知识库' }).click()
  await page.getByRole('textbox', { name: '知识库名称' }).fill(uniqueName)
  await page.getByRole('textbox', { name: '知识库描述' }).fill('真实 API 浏览器闭环')
  await page.getByRole('button', { name: '创建知识库' }).click()

  await expect(page.getByRole('heading', { name: uniqueName })).toBeVisible()
  await expect(page.getByText('添加文件与持久索引任务将在下一批开放。')).toBeVisible()
  await page.getByRole('textbox', { name: '知识库描述' }).fill('已保存的浏览器说明')
  await page.getByRole('button', { name: '保存更改' }).click()
  await page.reload()
  await expect(page.getByRole('textbox', { name: '知识库描述' })).toHaveValue('已保存的浏览器说明')

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
