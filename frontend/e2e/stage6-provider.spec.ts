import { expect, test } from '@playwright/test'

test('AI 服务设置页完成安全配置流程且不会自动探测', async ({ page }) => {
  const fixtureKey = `stage6-browser-fixture-${Date.now()}`
  await page.goto('/settings')

  await page.evaluate(async () => {
    await fetch('/api/v1/system/session', { method: 'POST' })
    await fetch('/api/v1/ai/provider/key', { method: 'DELETE', headers: { 'Idempotency-Key': crypto.randomUUID() } })
  })
  await page.reload()

  await expect(page.getByRole('heading', { name: '设置' })).toBeVisible()
  await expect(page.getByText('未配置')).toBeVisible()
  const testButton = page.getByRole('button', { name: '测试连接' })
  await expect(testButton).toBeDisabled()

  await page.getByLabel('DeepSeek API Key').fill(fixtureKey)
  await page.getByRole('button', { name: '保存 Key' }).click()
  await expect(page.getByLabel('DeepSeek API Key')).toHaveValue('')
  await expect(page.getByText('已配置')).toBeVisible()
  await expect(testButton).toBeDisabled()

  await page.getByRole('checkbox', { name: /固定测试文本/ }).check()
  await expect(testButton).toBeEnabled()
  expect(await page.evaluate(() => performance.getEntriesByType('resource').some((entry) => entry.name.includes('api.deepseek.com')))).toBe(false)

  await page.getByRole('button', { name: '删除本地 Key' }).click()
  await expect(page.getByText('未配置')).toBeVisible()
  await expect(testButton).toBeDisabled()
})
